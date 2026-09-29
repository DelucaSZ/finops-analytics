from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.schemas.collection import CollectionRunRead
from app.services.collection_errors import sanitize_collection_error


@dataclass(frozen=True)
class CollectionFilters:
    provider: str | None = None
    account_id: str | None = None
    status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    analyzer_version: str | None = None


def utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)


def apply_filters(statement, filters: CollectionFilters):
    for field in ("provider", "account_id", "status", "analyzer_version"):
        value = getattr(filters, field)
        if value:
            statement = statement.where(getattr(CollectionRun, field) == value)
    if filters.date_from:
        statement = statement.where(CollectionRun.started_at >= utc(filters.date_from))
    if filters.date_to:
        statement = statement.where(CollectionRun.started_at < utc(filters.date_to))
    return statement


def account_join():
    # Name enrichment only: unknown providers/accounts remain visible through the LEFT JOIN.
    return and_(
        CollectionRun.provider == CloudAccount.provider,
        CollectionRun.account_id == CloudAccount.native_account_id,
    )


def base_query():
    return (
        select(CollectionRun, CloudAccount.name, Scan.status.label("scan_status"))
        .outerjoin(CloudAccount, account_join())
        .outerjoin(Scan, CollectionRun.scan_id == Scan.id)
    )


def serialize_item(row) -> dict:
    run, account_name, scan_status = row
    return {
        **CollectionRunRead.model_validate(run).model_dump(),
        "account_name": account_name,
        "duration_seconds": max(0, (utc(run.finished_at) - utc(run.started_at)).total_seconds())
        if run.finished_at
        else None,
        # Legacy collectors never measured resources: zero means unavailable.
        "resources_analyzed_available": run.resources_analyzed > 0,
        "has_warnings": scan_status == "completed_with_warnings",
    }


def list_collections(db, filters, *, page, page_size, sort, order, offset=None):
    count = db.scalar(apply_filters(select(func.count()).select_from(CollectionRun), filters)) or 0
    expression = getattr(CollectionRun, sort)
    ordering = expression.desc() if order == "desc" else expression.asc()
    rows = db.execute(
        apply_filters(base_query(), filters)
        .order_by(ordering, CollectionRun.id.asc())
        .offset((page - 1) * page_size if offset is None else offset)
        .limit(page_size)
    ).all()
    summary = None
    if filters.provider and filters.account_id and offset is None:
        scope = CollectionFilters(provider=filters.provider, account_id=filters.account_id)
        latest = apply_filters(base_query(), scope).order_by(
            CollectionRun.started_at.desc(), CollectionRun.id.asc()
        )
        last_run = db.execute(latest.limit(1)).first()
        last_success = db.execute(latest.where(CollectionRun.status == "SUCCESS").limit(1)).first()
        summary = {
            "latest_run": serialize_item(last_run) if last_run else None,
            "latest_success": serialize_item(last_success) if last_success else None,
        }
    return {
        "items": [serialize_item(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": count,
        "total_pages": ceil(count / page_size),
        "account_summary": summary,
    }


def get_collection(db: Session, collection_id: str) -> dict | None:
    row = db.execute(
        base_query().add_columns(Scan.error, Scan.trigger).where(CollectionRun.id == collection_id)
    ).first()
    if row is None:
        return None
    observed = (
        db.scalar(
            select(func.count())
            .select_from(OpportunityObservation)
            .where(OpportunityObservation.collection_run_id == collection_id)
        )
        or 0
    )
    return {
        **serialize_item(row[:3]),
        "opportunities_observed": observed,
        "warning_detail": sanitize_collection_error(row.error)
        if row.scan_status == "completed_with_warnings"
        else None,
        "trigger": row.trigger,
    }


def collection_options(db, *, provider, search, limit):
    providers = list(
        db.scalars(select(CollectionRun.provider).distinct().order_by(CollectionRun.provider))
    )
    statement = (
        select(CollectionRun.provider, CollectionRun.account_id, CloudAccount.name)
        .outerjoin(CloudAccount, account_join())
        .distinct()
    )
    if provider:
        statement = statement.where(CollectionRun.provider == provider)
    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(CollectionRun.account_id.ilike(pattern), CloudAccount.name.ilike(pattern))
        )
    rows = db.execute(
        statement.order_by(CollectionRun.provider, CollectionRun.account_id).limit(limit + 1)
    ).all()
    return {
        "providers": providers,
        "accounts": [
            {"provider": p, "account_id": a, "account_name": n} for p, a, n in rows[:limit]
        ],
        "has_more_accounts": len(rows) > limit,
    }
