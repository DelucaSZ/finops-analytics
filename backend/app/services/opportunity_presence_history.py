from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.collection_run import CollectionRun
from app.models.collection_scope_execution import CollectionScopeExecution
from app.models.finding import Finding
from app.models.opportunity_presence_history import OpportunityPresenceHistory


def presence_history(
    db: Session,
    opportunity_id: str,
    *,
    page: int,
    page_size: int,
) -> dict | None:
    """Return immutable technical presence events without loading them on opportunity listings."""

    if db.get(Finding, opportunity_id) is None:
        return None

    total = (
        db.scalar(
            select(func.count())
            .select_from(OpportunityPresenceHistory)
            .where(OpportunityPresenceHistory.opportunity_id == opportunity_id)
        )
        or 0
    )
    rows = db.execute(
        select(
            OpportunityPresenceHistory,
            CollectionRun.provider,
            CollectionRun.account_id,
            CollectionRun.started_at,
            CollectionScopeExecution.region,
            CollectionScopeExecution.rule_key,
        )
        .outerjoin(
            CollectionRun,
            OpportunityPresenceHistory.collection_run_id == CollectionRun.id,
        )
        .outerjoin(
            CollectionScopeExecution,
            OpportunityPresenceHistory.collection_scope_execution_id == CollectionScopeExecution.id,
        )
        .where(OpportunityPresenceHistory.opportunity_id == opportunity_id)
        .order_by(
            OpportunityPresenceHistory.occurred_at.desc(),
            OpportunityPresenceHistory.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    items = [
        {
            "id": history.id,
            "from_status": history.from_status,
            "to_status": history.to_status,
            "reason": history.reason,
            "occurred_at": history.occurred_at,
            "missing_count": history.missing_count,
            "missing_threshold": history.missing_threshold,
            "collection_run_id": history.collection_run_id,
            "collection_scope_execution_id": history.collection_scope_execution_id,
            "collection_provider": provider,
            "collection_account_id": account_id,
            "collection_started_at": started_at,
            "scope_region": scope_region,
            "scope_rule_key": scope_rule_key,
            "context": history.context or {},
        }
        for history, provider, account_id, started_at, scope_region, scope_rule_key in rows
    ]
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }
