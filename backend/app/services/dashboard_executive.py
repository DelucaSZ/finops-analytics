from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.finding import Finding
from app.services import dashboard as dashboard_service
from app.services.opportunity_run_comparison import dashboard_new_since_previous

_SEVERITY_WEIGHT = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _money_rows(values: dict[str, Decimal]) -> list[dict[str, object]]:
    return [{"currency": currency, "amount": amount} for currency, amount in sorted(values.items())]


def _append_money(
    target: dict[str, Decimal],
    currency: str | None,
    amount: Decimal | None,
) -> None:
    if not currency:
        return
    target[currency] = target.get(currency, Decimal("0")) + Decimal(str(amount or 0))


def _provider_distribution(db: Session, current) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            current.c.provider,
            current.c.currency,
            func.count(func.distinct(Finding.id)).label("open"),
            func.coalesce(func.sum(current.c.estimated_monthly_savings), Decimal("0")).label(
                "amount"
            ),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .where(Finding.status == "open")
        .group_by(current.c.provider, current.c.currency)
    ).all()

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        item = grouped.setdefault(
            row.provider,
            {"provider": row.provider, "open": 0, "savings": {}},
        )
        item["open"] += int(row.open or 0)
        _append_money(item["savings"], row.currency, row.amount)

    return [
        {
            "provider": item["provider"],
            "open": item["open"],
            "estimated_monthly_savings": None,
            "currency": None,
            "savings": _money_rows(item["savings"]),
        }
        for item in sorted(
            grouped.values(),
            key=lambda value: (-value["open"], value["provider"]),
        )
    ]


def _account_distribution(db: Session, current, *, limit: int = 10) -> list[dict[str, object]]:
    open_count = func.count(func.distinct(Finding.id))
    top_accounts = (
        select(
            current.c.provider.label("provider"),
            current.c.account_id.label("account_id"),
            open_count.label("open"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .where(Finding.status == "open")
        .group_by(current.c.provider, current.c.account_id)
        .order_by(open_count.desc(), current.c.provider, current.c.account_id)
        .limit(limit)
        .cte("dashboard_top_accounts")
    )
    account_join = (top_accounts.c.provider == CloudAccount.provider) & (
        top_accounts.c.account_id == CloudAccount.native_account_id
    )
    current_join = (current.c.provider == top_accounts.c.provider) & (
        current.c.account_id == top_accounts.c.account_id
    )
    rows = db.execute(
        select(
            top_accounts.c.provider,
            top_accounts.c.account_id,
            CloudAccount.name.label("account_name"),
            top_accounts.c.open,
            current.c.currency,
            func.coalesce(func.sum(current.c.estimated_monthly_savings), Decimal("0")).label(
                "amount"
            ),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .join(top_accounts, current_join)
        .outerjoin(CloudAccount, account_join)
        .where(Finding.status == "open")
        .group_by(
            top_accounts.c.provider,
            top_accounts.c.account_id,
            CloudAccount.name,
            top_accounts.c.open,
            current.c.currency,
        )
        .order_by(
            top_accounts.c.open.desc(),
            top_accounts.c.provider,
            top_accounts.c.account_id,
            current.c.currency,
        )
    ).all()

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        key = (row.provider, row.account_id)
        item = grouped.setdefault(
            key,
            {
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.account_name,
                "open": int(row.open or 0),
                "savings": {},
            },
        )
        _append_money(item["savings"], row.currency, row.amount)

    return [
        {
            **{key: value for key, value in item.items() if key != "savings"},
            "estimated_monthly_savings": None,
            "currency": None,
            "savings": _money_rows(item["savings"]),
        }
        for item in grouped.values()
    ]


def _dimension_distribution(
    db: Session,
    current,
    *,
    dimension,
    key_name: str,
    limit: int = 5,
) -> list[dict[str, object]]:
    open_count = func.count(func.distinct(Finding.id))
    top_dimensions = (
        select(
            dimension.label("dimension_key"),
            open_count.label("open"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .where(Finding.status == "open")
        .group_by(dimension)
        .order_by(open_count.desc(), dimension)
        .limit(limit)
        .cte(f"dashboard_top_{key_name}")
    )
    rows = db.execute(
        select(
            top_dimensions.c.dimension_key,
            top_dimensions.c.open,
            current.c.currency,
            func.coalesce(func.sum(current.c.estimated_monthly_savings), Decimal("0")).label(
                "amount"
            ),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .join(top_dimensions, dimension == top_dimensions.c.dimension_key)
        .where(Finding.status == "open")
        .group_by(
            top_dimensions.c.dimension_key,
            top_dimensions.c.open,
            current.c.currency,
        )
        .order_by(
            top_dimensions.c.open.desc(),
            top_dimensions.c.dimension_key,
            current.c.currency,
        )
    ).all()

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        value = str(row.dimension_key or "unknown")
        item = grouped.setdefault(
            value,
            {key_name: value, "open": int(row.open or 0), "savings": {}},
        )
        _append_money(item["savings"], row.currency, row.amount)

    return [
        {
            key_name: item[key_name],
            "open": item["open"],
            "savings": _money_rows(item["savings"]),
        }
        for item in grouped.values()
    ]


def _severity_distribution(db: Session, current) -> dict[str, int]:
    rows = db.execute(
        select(
            func.lower(current.c.severity).label("severity"),
            func.count(func.distinct(Finding.id)).label("count"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .where(Finding.status == "open")
        .group_by(func.lower(current.c.severity))
    ).all()
    result = {"critical": 0, "high": 0, "medium": 0, "low": 0, "other": 0}
    for row in rows:
        severity = row.severity or "other"
        if severity not in result:
            severity = "other"
        result[severity] += int(row.count or 0)
    return result


def _top_opportunities(db: Session, current, *, limit: int = 10) -> list[dict[str, object]]:
    severity_order = case(
        *[
            (func.lower(current.c.severity) == severity, weight)
            for severity, weight in _SEVERITY_WEIGHT.items()
        ],
        else_=0,
    )
    account_join = (current.c.provider == CloudAccount.provider) & (
        current.c.account_id == CloudAccount.native_account_id
    )
    ranked = (
        select(
            Finding.id,
            Finding.title,
            Finding.rule_key,
            Finding.service,
            Finding.resource_id,
            Finding.resource_name,
            Finding.region,
            current.c.provider,
            current.c.account_id,
            CloudAccount.name.label("account_name"),
            current.c.collection_run_id,
            current.c.severity,
            current.c.estimated_monthly_savings,
            current.c.currency,
            func.row_number()
            .over(
                partition_by=current.c.currency,
                order_by=(
                    current.c.estimated_monthly_savings.desc(),
                    severity_order.desc(),
                    Finding.id,
                ),
            )
            .label("currency_rank"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .outerjoin(CloudAccount, account_join)
        .where(Finding.status == "open")
        .cte("dashboard_executive_top")
    )
    rows = db.execute(
        select(ranked)
        .where(ranked.c.currency_rank <= limit)
        .order_by(ranked.c.currency_rank, ranked.c.currency, ranked.c.id)
        .limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "rule_key": row.rule_key,
            "service": row.service,
            "resource_id": row.resource_id,
            "resource_name": row.resource_name,
            "region": row.region,
            "provider": row.provider,
            "account_id": row.account_id,
            "account_name": row.account_name,
            "collection_run_id": row.collection_run_id,
            "severity": row.severity,
            "estimated_monthly_savings": row.estimated_monthly_savings,
            "currency": row.currency,
        }
        for row in rows
    ]


def executive_dashboard_summary(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> dict[str, object]:
    """Return the business-facing summary without collection-health coupling."""

    payload = dashboard_service.dashboard_summary(db, provider=provider, account_id=account_id)
    latest_valid, current = dashboard_service._current_observations(
        provider=provider,
        account_id=account_id,
    )

    # Task 24.12: calculate the KPI and its navigation context atomically from the
    # same comparison service. Persisted dashboard aggregates remain useful for the
    # other metrics, but they are no longer the source of truth for this KPI.
    new_details = dashboard_new_since_previous(db, provider=provider, account_id=account_id)
    payload["opportunities"]["new_since_previous"] = new_details["count"]
    payload["opportunities"]["new_since_previous_details"] = new_details
    payload["recent_changes"]["new"] = new_details["count"]
    payload["recent_changes"]["comparable_scopes"] = new_details["comparable_accounts"]
    payload["recent_changes"]["scopes_without_baseline"] = new_details["accounts_without_baseline"]

    payload["data_updated_at"] = db.scalar(select(func.max(latest_valid.c.started_at)))
    payload["severity"] = _severity_distribution(db, current)
    payload["by_provider"] = _provider_distribution(db, current)
    payload["by_account"] = _account_distribution(db, current)
    payload["by_service"] = _dimension_distribution(
        db,
        current,
        dimension=Finding.service,
        key_name="service",
    )
    payload["by_rule"] = _dimension_distribution(
        db,
        current,
        dimension=Finding.rule_key,
        key_name="rule_key",
    )
    payload["top_opportunities"] = _top_opportunities(db, current)
    return payload
