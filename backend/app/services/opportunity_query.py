from dataclasses import dataclass
from math import ceil

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, defer, load_only

from app.core.cloud import CloudProvider
from app.core.config import settings
from app.models.account import AwsAccount, CloudAccount
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.opportunity_evidence import normalize_persisted_evidence
from app.services.retention import retention_cutoff


@dataclass(frozen=True)
class OpportunityFilters:
    provider: str | None = None
    account_id: str | None = None
    region: str | None = None
    service: str | None = None
    resource_type: str | None = None
    status: str | None = None
    severity: str | None = None
    rule: str | None = None
    collection_run_id: str | None = None
    resource_id: str | None = None
    search: str | None = None
    current: bool = False


def _account_join():
    return and_(
        Finding.provider == CloudAccount.provider,
        Finding.account_id == CloudAccount.native_account_id,
    )


def _apply_filters(statement, filters: OpportunityFilters, *, include_status: bool = True):
    if filters.provider:
        statement = statement.where(Finding.provider == filters.provider.lower())
    if filters.account_id:
        account_match = Finding.account_id == filters.account_id
        # Temporary compatibility for callers that still send the old integer AWS PK.
        if not filters.provider or filters.provider.lower() == CloudProvider.AWS.value:
            account_match = or_(
                account_match,
                and_(
                    Finding.provider == CloudProvider.AWS.value,
                    select(AwsAccount.id)
                    .join(CloudAccount, AwsAccount.cloud_account_id == CloudAccount.id)
                    .where(
                        CloudAccount.provider == CloudProvider.AWS.value,
                        CloudAccount.native_account_id == Finding.account_id,
                        cast(AwsAccount.id, String) == filters.account_id,
                    )
                    .correlate(Finding)
                    .exists(),
                ),
            )
        statement = statement.where(account_match)
    if filters.region:
        statement = statement.where(Finding.region == filters.region)
    if filters.service:
        statement = statement.where(Finding.service == filters.service)
    if filters.resource_type:
        statement = statement.where(Finding.resource_type == filters.resource_type)
    if include_status and filters.status:
        statement = statement.where(Finding.status == filters.status)
    if filters.severity:
        statement = statement.where(Finding.severity == filters.severity)
    if filters.rule:
        statement = statement.where(Finding.rule_key == filters.rule)
    if filters.resource_id:
        statement = statement.where(Finding.resource_id == filters.resource_id)
    if filters.collection_run_id:
        observed_in_run = (
            select(OpportunityObservation.id)
            .where(
                OpportunityObservation.opportunity_id == Finding.id,
                OpportunityObservation.collection_run_id == filters.collection_run_id,
            )
            .exists()
        )
        statement = statement.where(observed_in_run)
    if filters.current:
        latest_success_run = (
            select(CollectionRun.id)
            .where(
                CollectionRun.provider == Finding.provider,
                CollectionRun.account_id == Finding.account_id,
                CollectionRun.status == "SUCCESS",
            )
            .order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc())
            .limit(1)
            .correlate(Finding)
            .scalar_subquery()
        )
        observed_in_current_run = (
            select(OpportunityObservation.id)
            .where(
                OpportunityObservation.opportunity_id == Finding.id,
                OpportunityObservation.collection_run_id == latest_success_run,
            )
            .exists()
        )
        statement = statement.where(observed_in_current_run)
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        statement = statement.where(
            or_(
                Finding.resource_id.ilike(pattern),
                Finding.resource_name.ilike(pattern),
                Finding.resource_type.ilike(pattern),
                Finding.title.ilike(pattern),
                Finding.description.ilike(pattern),
                Finding.rule_key.ilike(pattern),
                Finding.service.ilike(pattern),
            )
        )
    return statement


def _order_expression(sort: str):
    if sort == "estimated_savings":
        return Finding.estimated_monthly_savings
    if sort == "severity":
        return case(
            (Finding.severity == "high", 3),
            (Finding.severity == "medium", 2),
            (Finding.severity == "low", 1),
            else_=0,
        )
    return getattr(Finding, sort)


def _page_meta(total: int, page: int, page_size: int) -> dict[str, int]:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


def serialize_list_item(
    finding: Finding,
    account: CloudAccount | None,
    aws_configuration: AwsAccount | None,
) -> dict:
    return {
        "id": finding.id,
        "fingerprint": finding.fingerprint,
        "provider": finding.provider,
        "account_id": finding.account_id,
        "account_name": account.name if account else None,
        "legacy_account_id": aws_configuration.id if aws_configuration else None,
        "rule_key": finding.rule_key,
        "service": finding.service,
        "region": finding.region,
        "resource_id": finding.resource_id,
        "resource_name": finding.resource_name,
        "resource_type": finding.resource_type,
        "provider_metadata": finding.provider_metadata or {},
        "title": finding.title,
        "description": finding.description,
        "current_monthly_cost": finding.current_monthly_cost,
        "estimated_monthly_savings": finding.estimated_monthly_savings,
        "currency": finding.currency,
        "confidence": finding.confidence,
        "severity": finding.severity,
        "status": finding.status,
        "presence_status": finding.presence_status,
        "missing_since_at": finding.missing_since_at,
        "resolved_externally_at": finding.resolved_externally_at,
        "first_seen_at": finding.first_seen_at,
        "last_seen_at": finding.last_seen_at,
        "total_occurrence_count": finding.total_occurrence_count,
        "needs_review": finding.needs_review,
    }


def list_opportunities(
    db: Session,
    filters: OpportunityFilters,
    *,
    page: int,
    page_size: int,
    sort: str,
    order: str,
) -> dict:
    base = (
        select(Finding, CloudAccount, AwsAccount)
        .outerjoin(CloudAccount, _account_join())
        .outerjoin(AwsAccount, AwsAccount.cloud_account_id == CloudAccount.id)
        .options(
            defer(Finding.evidence, raiseload=True),
            defer(Finding.treatment_note, raiseload=True),
            defer(Finding.rejection_note, raiseload=True),
            load_only(CloudAccount.id, CloudAccount.name, raiseload=True),
            load_only(AwsAccount.id, raiseload=True),
        )
    )
    base = _apply_filters(base, filters)
    count_query = select(func.count()).select_from(Finding)
    count_query = _apply_filters(count_query, filters)
    total = db.scalar(count_query) or 0

    order_expression = _order_expression(sort)
    ordering = order_expression.desc() if order == "desc" else order_expression.asc()
    statement = base.order_by(ordering, Finding.id.asc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(statement).all()
    return {
        "items": [
            serialize_list_item(finding, account, aws_configuration)
            for finding, account, aws_configuration in rows
        ],
        **_page_meta(total, page, page_size),
    }


def opportunity_stats(db: Session, filters: OpportunityFilters) -> dict[str, int]:
    statement = select(Finding.status, func.count()).select_from(Finding).group_by(Finding.status)
    statement = _apply_filters(statement, filters, include_status=False)
    counts = {status: count for status, count in db.execute(statement).all()}
    return {
        "open": counts.get("open", 0),
        "treated": counts.get("treated", 0),
        "rejected": counts.get("rejected", 0),
    }


def opportunity_options(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> dict:
    provider = provider.lower() if provider else None
    providers = list(db.scalars(select(Finding.provider).distinct().order_by(Finding.provider)))

    account_statement = (
        select(Finding.provider, Finding.account_id, CloudAccount.name)
        .select_from(Finding)
        .outerjoin(CloudAccount, _account_join())
        .distinct()
    )
    if provider:
        account_statement = account_statement.where(Finding.provider == provider)
    if search:
        pattern = f"%{search.strip()}%"
        account_statement = account_statement.where(
            or_(Finding.account_id.ilike(pattern), CloudAccount.name.ilike(pattern))
        )
    account_rows = db.execute(
        account_statement.order_by(Finding.provider, Finding.account_id).limit(limit)
    ).all()

    dimension_filters = []
    if provider:
        dimension_filters.append(Finding.provider == provider)
    if account_id:
        dimension_filters.append(Finding.account_id == account_id)

    def distinct_values(column):
        statement = select(column).where(column.is_not(None), *dimension_filters).distinct()
        return list(db.scalars(statement.order_by(column)))

    return {
        "providers": providers,
        "accounts": [
            {
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.name,
            }
            for row in account_rows
        ],
        "regions": distinct_values(Finding.region),
        "services": distinct_values(Finding.service),
        "resource_types": distinct_values(Finding.resource_type),
        "rules": distinct_values(Finding.rule_key),
    }


def _structured_evidence(
    finding: Finding,
    *,
    evidence: dict,
    current_monthly_cost,
    estimated_monthly_savings,
) -> dict:
    return normalize_persisted_evidence(
        rule_key=finding.rule_key,
        service=finding.service,
        region=finding.region,
        resource_id=finding.resource_id,
        resource_name=finding.resource_name,
        title=finding.title,
        description=finding.description,
        evidence=evidence,
        current_monthly_cost=current_monthly_cost,
        estimated_monthly_savings=estimated_monthly_savings,
        provider=finding.provider,
    )


def _serialize_observation(
    finding: Finding,
    observation: OpportunityObservation,
    run: CollectionRun,
) -> dict:
    return {
        "id": observation.id,
        "collection_run_id": observation.collection_run_id,
        "observed_at": observation.observed_at,
        "severity": observation.severity,
        "current_monthly_cost": observation.current_monthly_cost,
        "estimated_monthly_savings": observation.estimated_monthly_savings,
        "currency": observation.currency,
        "confidence": observation.confidence,
        "provider_metadata": observation.provider_metadata or {},
        "evidence": _structured_evidence(
            finding,
            evidence=observation.evidence,
            current_monthly_cost=observation.current_monthly_cost,
            estimated_monthly_savings=observation.estimated_monthly_savings,
        ),
        "collection_provider": run.provider,
        "collection_account_id": run.account_id,
        "collection_started_at": run.started_at,
        "collection_finished_at": run.finished_at,
        "collection_status": run.status,
    }


def get_opportunity(db: Session, opportunity_id: str) -> dict | None:
    row = db.execute(
        select(Finding, CloudAccount, AwsAccount)
        .outerjoin(CloudAccount, _account_join())
        .outerjoin(AwsAccount, AwsAccount.cloud_account_id == CloudAccount.id)
        .where(Finding.id == opportunity_id)
    ).one_or_none()
    if row is None:
        return None
    finding, account, aws_configuration = row

    latest_row = db.execute(
        select(OpportunityObservation, CollectionRun)
        .join(CollectionRun, OpportunityObservation.collection_run_id == CollectionRun.id)
        .where(OpportunityObservation.opportunity_id == opportunity_id)
        .order_by(
            OpportunityObservation.observed_at.desc(),
            OpportunityObservation.id.desc(),
        )
        .limit(1)
    ).one_or_none()
    latest_observation = (
        _serialize_observation(finding, latest_row[0], latest_row[1]) if latest_row else None
    )
    latest_evidence = (
        latest_observation["evidence"]
        if latest_observation
        else _structured_evidence(
            finding,
            evidence=finding.evidence,
            current_monthly_cost=finding.current_monthly_cost,
            estimated_monthly_savings=finding.estimated_monthly_savings,
        )
    )
    return serialize_list_item(finding, account, aws_configuration) | {
        "scan_id": finding.scan_id,
        "treated_at": finding.treated_at,
        "treated_by": finding.treated_by,
        "treatment_note": finding.treatment_note,
        "rejected_at": finding.rejected_at,
        "rejected_by": finding.rejected_by,
        "rejection_reason": finding.rejection_reason,
        "rejection_note": finding.rejection_note,
        "rule": latest_evidence["rule"],
        "latest_observation": latest_observation,
        "latest_evidence": latest_evidence,
    }


def observation_history(
    db: Session,
    opportunity_id: str,
    *,
    page: int,
    page_size: int,
) -> dict | None:
    finding = db.get(Finding, opportunity_id)
    if finding is None:
        return None
    retained_total = (
        db.scalar(
            select(func.count())
            .select_from(OpportunityObservation)
            .where(OpportunityObservation.opportunity_id == opportunity_id)
        )
        or 0
    )
    rows = db.execute(
        select(OpportunityObservation, CollectionRun)
        .join(CollectionRun, OpportunityObservation.collection_run_id == CollectionRun.id)
        .where(OpportunityObservation.opportunity_id == opportunity_id)
        .order_by(
            OpportunityObservation.observed_at.desc(),
            OpportunityObservation.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [_serialize_observation(finding, observation, run) for observation, run in rows]
    historical_total = max(int(finding.total_occurrence_count or 0), int(retained_total))
    return {
        "items": items,
        **_page_meta(retained_total, page, page_size),
        "retained_total": int(retained_total),
        "total_occurrence_count": historical_total,
        "history_complete": int(retained_total) >= historical_total,
        "retention_enabled": settings.retention_enabled,
        "retention_days": settings.opportunity_observation_retention_days,
        "retention_cutoff": retention_cutoff(days=settings.opportunity_observation_retention_days),
    }


def status_history(
    db: Session,
    opportunity_id: str,
    *,
    page: int,
    page_size: int,
) -> dict | None:
    if db.get(Finding, opportunity_id) is None:
        return None
    total = (
        db.scalar(
            select(func.count())
            .select_from(OpportunityStatusHistory)
            .where(OpportunityStatusHistory.opportunity_id == opportunity_id)
        )
        or 0
    )
    rows = db.execute(
        select(OpportunityStatusHistory, User.name)
        .outerjoin(User, OpportunityStatusHistory.changed_by == User.id)
        .where(OpportunityStatusHistory.opportunity_id == opportunity_id)
        .order_by(
            OpportunityStatusHistory.changed_at.desc(),
            OpportunityStatusHistory.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "id": history.id,
            "from_status": history.from_status,
            "to_status": history.to_status,
            "action": history.action,
            "reason": history.reason,
            "note": history.note,
            "changed_by": history.changed_by,
            "changed_by_name": changed_by_name,
            "changed_at": history.changed_at,
        }
        for history, changed_by_name in rows
    ]
    return {"items": items, **_page_meta(total, page, page_size)}
