from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.finding import Finding
from app.services import dashboard as dashboard_service

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
    account_join = (current.c.provider == CloudAccount.provider) & (
        current.c.account_id == CloudAccount.native_account_id
    )
    rows = db.execute(
        select(
            current.c.provider,
            current.c.account_id,
            CloudAccount.name.label("account_name"),
            current.c.currency,
            func.count(func.distinct(Finding.id)).label("open"),
            func.coalesce(func.sum(current.c.estimated_monthly_savings), Decimal("0")).label(
                "amount"
            ),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .outerjoin(CloudAccount, account_join)
        .where(Finding.status == "open")
        .group_by(
            current.c.provider,
            current.c.account_id,
            CloudAccount.name,
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
                "open": 0,
                "savings": {},
            },
        )
        item["open"] += int(row.open or 0)
        _append_money(item["savings"], row.currency, row.amount)

    ranked = sorted(
        grouped.values(),
        key=lambda value: (-value["open"], value["provider"], value["account_id"]),
    )[:limit]
    return [
        {
            **{key: value for key, value in item.items() if key != "savings"},
            "estimated_monthly_savings": None,
            "currency": None,
            "savings": _money_rows(item["savings"]),
        }
        for item in ranked
    ]


def _dimension_distribution(
    db: Session,
    current,
    *,
    dimension,
    key_name: str,
    limit: int = 5,
) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            dimension.label("dimension_key"),
            current.c.currency,
            func.count(func.distinct(Finding.id)).label("open"),
            func.coalesce(func.sum(current.c.estimated_monthly_savings), Decimal("0")).label(
                "amount"
            ),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .where(Finding.status == "open")
        .group_by(dimension, current.c.currency)
    ).all()

    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        value = str(row.dimension_key or "unknown")
        item = grouped.setdefault(value, {key_name: value, "open": 0, "savings": {}})
        item["open"] += int(row.open or 0)
        _append_money(item["savings"], row.currency, row.amount)

    ranked = sorted(grouped.values(), key=lambda value: (-value["open"], value[key_name]))[:limit]
    return [
        {
            key_name: item[key_name],
            "open": item["open"],
            "savings": _money_rows(item["savings"]),
        }
        for item in ranked
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
