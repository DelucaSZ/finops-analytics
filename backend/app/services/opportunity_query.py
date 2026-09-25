from dataclasses import dataclass
from math import ceil
from typing import Any

from sqlalchemy import String, case, cast, false, func, or_, select
from sqlalchemy.orm import Session

from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.policies import RULES


@dataclass(frozen=True)
class OpportunityFilters:
    provider: str | None = None
    account_id: str | None = None
    region: str | None = None
    status: str | None = None
    severity: str | None = None
    rule: str | None = None
    collection_run_id: str | None = None
    resource_id: str | None = None
    search: str | None = None


def _apply_filters(statement, filters: OpportunityFilters, *, include_status: bool = True):
    if filters.provider and filters.provider.lower() != "aws":
        statement = statement.where(false())
    if filters.account_id:
        statement = statement.where(
            or_(
                AwsAccount.aws_account_id == filters.account_id,
                cast(AwsAccount.id, String) == filters.account_id,
            )
        )
    if filters.region:
        statement = statement.where(Finding.region == filters.region)
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
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        statement = statement.where(
            or_(
                Finding.resource_id.ilike(pattern),
                Finding.resource_name.ilike(pattern),
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


def serialize_list_item(finding: Finding, account: AwsAccount) -> dict[str, Any]:
    return {
        "id": finding.id,
        "fingerprint": finding.fingerprint,
        "provider": "aws",
        "account_id": account.aws_account_id,
        "account_name": account.name,
        "legacy_account_id": account.id,
        "rule_key": finding.rule_key,
        "service": finding.service,
        "region": finding.region,
        "resource_id": finding.resource_id,
        "resource_name": finding.resource_name,
        "title": finding.title,
        "description": finding.description,
        "current_monthly_cost": finding.current_monthly_cost,
        "estimated_monthly_savings": finding.estimated_monthly_savings,
        "confidence": finding.confidence,
        "severity": finding.severity,
        "status": finding.status,
        "first_seen_at": finding.first_seen_at,
        "last_seen_at": finding.last_seen_at,
        "needs_review": finding.needs_review,
    }


def _serialize_observation(
    observation: OpportunityObservation,
    run: CollectionRun,
) -> dict[str, Any]:
    return {
        "id": observation.id,
        "collection_run_id": observation.collection_run_id,
        "observed_at": observation.observed_at,
        "severity": observation.severity,
        "current_monthly_cost": observation.current_monthly_cost,
        "estimated_monthly_savings": observation.estimated_monthly_savings,
        "confidence": observation.confidence,
        "evidence": observation.evidence,
        "collection_provider": run.provider,
        "collection_account_id": run.account_id,
        "collection_started_at": run.started_at,
        "collection_finished_at": run.finished_at,
        "collection_status": run.status,
    }


def _latest_observation(
    db: Session,
    opportunity_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        select(OpportunityObservation, CollectionRun)
        .join(CollectionRun, OpportunityObservation.collection_run_id == CollectionRun.id)
        .where(OpportunityObservation.opportunity_id == opportunity_id)
        .order_by(OpportunityObservation.observed_at.desc(), OpportunityObservation.id)
        .limit(1)
    ).one_or_none()
    if row is None:
        return None
    observation, run = row
    return _serialize_observation(observation, run)


def _rule_explanation(rule_key: str, evidence: dict[str, Any]) -> dict[str, Any]:
    structured_rule = evidence.get("rule")
    if (
        evidence.get("schema_version") == 1
        and isinstance(structured_rule, dict)
        and structured_rule.get("key")
        and structured_rule.get("name")
    ):
        return structured_rule

    definition = RULES.get(rule_key)
    return {
        "key": rule_key,
        "name": definition.name if definition else rule_key,
        "description": definition.description if definition else "",
        "criteria": [],
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
    base = select(Finding, AwsAccount).join(AwsAccount, Finding.account_id == AwsAccount.id)
    base = _apply_filters(base, filters)
    count_query = (
        select(func.count())
        .select_from(Finding)
        .join(AwsAccount, Finding.account_id == AwsAccount.id)
    )
    count_query = _apply_filters(count_query, filters)
    total = db.scalar(count_query) or 0

    order_expression = _order_expression(sort)
    ordering = order_expression.desc() if order == "desc" else order_expression.asc()
    statement = base.order_by(ordering, Finding.id.asc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    rows = db.execute(statement).all()
    return {
        "items": [serialize_list_item(finding, account) for finding, account in rows],
        **_page_meta(total, page, page_size),
    }


def opportunity_stats(db: Session, filters: OpportunityFilters) -> dict[str, int]:
    statement = (
        select(Finding.status, func.count())
        .join(AwsAccount, Finding.account_id == AwsAccount.id)
        .group_by(Finding.status)
    )
    statement = _apply_filters(statement, filters, include_status=False)
    counts = {status: count for status, count in db.execute(statement).all()}
    return {
        "open": counts.get("open", 0),
        "treated": counts.get("treated", 0),
        "rejected": counts.get("rejected", 0),
    }


def get_opportunity(db: Session, opportunity_id: str) -> dict | None:
    row = db.execute(
        select(Finding, AwsAccount)
        .join(AwsAccount, Finding.account_id == AwsAccount.id)
        .where(Finding.id == opportunity_id)
    ).one_or_none()
    if row is None:
        return None

    finding, account = row
    latest_observation = _latest_observation(db, opportunity_id)
    latest_evidence = (
        latest_observation["evidence"] if latest_observation is not None else finding.evidence or {}
    )
    return serialize_list_item(finding, account) | {
        "scan_id": finding.scan_id,
        "evidence": finding.evidence or {},
        "latest_observation": latest_observation,
        "rule": _rule_explanation(finding.rule_key, latest_evidence),
        "treated_at": finding.treated_at,
        "treated_by": finding.treated_by,
        "treatment_note": finding.treatment_note,
        "rejected_at": finding.rejected_at,
        "rejected_by": finding.rejected_by,
        "rejection_reason": finding.rejection_reason,
        "rejection_note": finding.rejection_note,
    }


def observation_history(
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
            .select_from(OpportunityObservation)
            .where(OpportunityObservation.opportunity_id == opportunity_id)
        )
        or 0
    )
    rows = db.execute(
        select(OpportunityObservation, CollectionRun)
        .join(CollectionRun, OpportunityObservation.collection_run_id == CollectionRun.id)
        .where(OpportunityObservation.opportunity_id == opportunity_id)
        .order_by(OpportunityObservation.observed_at.desc(), OpportunityObservation.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [_serialize_observation(observation, run) for observation, run in rows],
        **_page_meta(total, page, page_size),
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
