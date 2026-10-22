from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer, load_only

from app.models.account import AwsAccount, CloudAccount
from app.models.finding import Finding
from app.services.opportunity_query import (
    OpportunityFilters,
    _account_join,
    _apply_filters,
    _order_expression,
    _page_meta,
    serialize_list_item,
)
from app.services.opportunity_run_comparison import (
    DiscoveryType,
    OpportunityRunContext,
    comparison_condition,
)


def _comparison_base(
    statement,
    filters: OpportunityFilters,
    contexts: tuple[OpportunityRunContext, ...],
    discovery_type: DiscoveryType,
):
    condition = comparison_condition(contexts, discovery_type)
    if condition is None:
        return statement.where(False)
    # comparison_context represents the operational KPI universe. Later filters can
    # narrow this set, but they must never broaden it back to rejected/archived rows.
    statement = statement.where(
        condition,
        Finding.status != "rejected",
        Finding.archived_at.is_(None),
    )
    return _apply_filters(statement, filters)


def list_dashboard_comparison_opportunities(
    db: Session,
    filters: OpportunityFilters,
    contexts: tuple[OpportunityRunContext, ...],
    *,
    discovery_type: DiscoveryType,
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
    base = _comparison_base(base, filters, contexts, discovery_type)
    count_query = _comparison_base(
        select(func.count()).select_from(Finding),
        filters,
        contexts,
        discovery_type,
    )
    total = int(db.scalar(count_query) or 0)

    order_expression = _order_expression(sort)
    ordering = order_expression.desc() if order == "desc" else order_expression.asc()
    rows = db.execute(
        base.order_by(ordering, Finding.id.asc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            serialize_list_item(finding, account, aws_configuration)
            for finding, account, aws_configuration in rows
        ],
        **_page_meta(total, page, page_size),
    }


def dashboard_comparison_stats(
    db: Session,
    filters: OpportunityFilters,
    contexts: tuple[OpportunityRunContext, ...],
    *,
    discovery_type: DiscoveryType,
) -> dict[str, int]:
    statement = select(Finding.status, func.count()).select_from(Finding).group_by(Finding.status)
    condition = comparison_condition(contexts, discovery_type)
    if condition is None:
        return {"open": 0, "treated": 0, "rejected": 0}
    statement = statement.where(
        condition,
        Finding.status != "rejected",
        Finding.archived_at.is_(None),
    )
    statement = _apply_filters(statement, filters, include_status=False)
    counts = {status: int(count) for status, count in db.execute(statement).all()}
    return {
        "open": counts.get("open", 0),
        "treated": counts.get("treated", 0),
        "rejected": 0,
    }
