from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.dashboard_summary import DashboardAccountSummary
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.services.dashboard_aggregation import rebuild_account_summary
from app.services.opportunity_run_comparison import opportunity_run_changes
from app.services.provider_capabilities import ProviderOperation, providers_supporting

logger = logging.getLogger("deepops.dashboard")


def _scope(statement, *, provider: str | None, account_id: str | None):
    if provider:
        statement = statement.where(CollectionRun.provider == provider.lower())
    if account_id:
        statement = statement.where(CollectionRun.account_id == account_id)
    return statement


def _ranked_runs(
    *,
    provider: str | None,
    account_id: str | None,
    successful_only: bool,
    name: str,
):
    statement = select(
        CollectionRun.id.label("run_id"),
        CollectionRun.scan_id.label("scan_id"),
        CollectionRun.provider.label("provider"),
        CollectionRun.account_id.label("account_id"),
        CollectionRun.started_at.label("started_at"),
        CollectionRun.finished_at.label("finished_at"),
        CollectionRun.status.label("status"),
        CollectionRun.analyzer_version.label("analyzer_version"),
        func.row_number()
        .over(
            partition_by=(CollectionRun.provider, CollectionRun.account_id),
            order_by=(CollectionRun.started_at.desc(), CollectionRun.id.desc()),
        )
        .label("run_rank"),
    )
    statement = _scope(statement, provider=provider, account_id=account_id)
    if successful_only:
        statement = statement.where(CollectionRun.status == CollectionRunStatus.SUCCESS)
    return statement.cte(name)


def _latest_success_runs(*, provider: str | None, account_id: str | None):
    ranked = _ranked_runs(
        provider=provider,
        account_id=account_id,
        successful_only=True,
        name="dashboard_success_ranked",
    )
    return (
        select(
            ranked.c.run_id,
            ranked.c.scan_id,
            ranked.c.provider,
            ranked.c.account_id,
            ranked.c.started_at,
            ranked.c.finished_at,
            ranked.c.status,
            ranked.c.analyzer_version,
        )
        .where(ranked.c.run_rank == 1)
        .cte("dashboard_latest_valid")
    )


def _current_observations(*, provider: str | None, account_id: str | None):
    latest_valid = _latest_success_runs(provider=provider, account_id=account_id)
    current = (
        select(
            OpportunityObservation.opportunity_id.label("opportunity_id"),
            OpportunityObservation.collection_run_id.label("collection_run_id"),
            OpportunityObservation.severity.label("severity"),
            OpportunityObservation.current_monthly_cost.label("current_monthly_cost"),
            OpportunityObservation.estimated_monthly_savings.label("estimated_monthly_savings"),
            OpportunityObservation.currency.label("currency"),
            OpportunityObservation.confidence.label("confidence"),
            latest_valid.c.provider.label("provider"),
            latest_valid.c.account_id.label("account_id"),
            latest_valid.c.started_at.label("collection_started_at"),
            latest_valid.c.analyzer_version.label("analyzer_version"),
        )
        .join(
            latest_valid,
            OpportunityObservation.collection_run_id == latest_valid.c.run_id,
        )
        .join(Finding, Finding.id == OpportunityObservation.opportunity_id)
        .where(Finding.archived_at.is_(None))
        .cte("dashboard_current_observations")
    )
    return latest_valid, current


def _account_name_join(current):
    return and_(
        current.c.provider == CloudAccount.provider,
        current.c.account_id == CloudAccount.native_account_id,
    )


def _recent_changes(db: Session, *, provider: str | None, account_id: str | None) -> dict:
    latest_valid = _latest_success_runs(provider=provider, account_id=account_id)
    targets = list(
        db.scalars(
            select(CollectionRun)
            .join(latest_valid, CollectionRun.id == latest_valid.c.run_id)
            .order_by(CollectionRun.provider, CollectionRun.account_id)
        )
    )

    new_count = 0
    no_longer_detected = 0
    comparable_scopes = 0
    scopes_without_baseline = 0
    rules_version_changed_scopes = 0
    rules_version_unknown_scopes = 0

    for target in targets:
        changes = opportunity_run_changes(db, target)
        summary = changes["summary"]
        new_count += int(summary["operational_new_vs_previous"])
        no_longer_detected += int(summary["no_longer_detected"])
        comparable_scopes += int(bool(changes["comparable"]))
        scopes_without_baseline += int(changes["baseline_run_id"] is None)
        rules_version_changed_scopes += int(changes["rules_version_changed"] is True)
        rules_version_unknown_scopes += int(
            changes["baseline_run_id"] is not None
            and changes["rules_version_changed"] is None
        )

    return {
        "new": new_count,
        "no_longer_detected": no_longer_detected,
        # Etapa 8 classifica CHANGED por diff semântico de evidence. Consolidar isso aqui
        # exigiria carregar snapshots/evidence de todas as contas; não aproximamos a métrica.
        "changed": None,
        "changed_available": False,
        "comparable_scopes": comparable_scopes,
        "scopes_without_baseline": scopes_without_baseline,
        "rules_version_changed_scopes": rules_version_changed_scopes,
        "rules_version_unknown_scopes": rules_version_unknown_scopes,
    }


def _dashboard_summary_direct(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> dict:
    latest_valid, current = _current_observations(provider=provider, account_id=account_id)

    valid_scope_count = db.scalar(select(func.count()).select_from(latest_valid)) or 0

    summary_rows = db.execute(
        select(
            current.c.currency,
            *[
                func.count(
                    case((and_(Finding.status == "open", current.c.severity == level), 1))
                ).label(f"severity_{level}")
                for level in ("high", "medium", "low")
            ],
            func.count(
                case(
                    (
                        and_(
                            Finding.status == "open",
                            current.c.severity.not_in(["high", "medium", "low"]),
                        ),
                        1,
                    )
                )
            ).label("severity_other"),
            func.count(
                func.distinct(case((Finding.status == "open", Finding.id), else_=None))
            ).label("open"),
            func.count(
                func.distinct(case((Finding.status == "treated", Finding.id), else_=None))
            ).label("treated"),
            func.count(
                func.distinct(case((Finding.status == "rejected", Finding.id), else_=None))
            ).label("rejected"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Finding.status == "open",
                            current.c.estimated_monthly_savings,
                        ),
                        else_=Decimal("0"),
                    )
                ),
                Decimal("0"),
            ).label("amount"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .group_by(current.c.currency)
        .order_by(current.c.currency)
    ).all()
    lifecycle_totals = {
        "open": sum(int(row.open or 0) for row in summary_rows),
        "treated": sum(int(row.treated or 0) for row in summary_rows),
        "rejected": sum(int(row.rejected or 0) for row in summary_rows),
    }
    financial_rows = [row for row in summary_rows if row.open]

    # Only grouped currency rows are reduced here, never individual opportunities.
    by_severity = {
        level: sum(int(getattr(row, f"severity_{level}") or 0) for row in summary_rows)
        for level in ("high", "medium", "low", "other")
    }

    provider_rows = db.execute(
        select(
            current.c.provider,
            func.count(func.distinct(Finding.id)).label("open"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .where(Finding.status == "open")
        .group_by(current.c.provider)
        .order_by(func.count(func.distinct(Finding.id)).desc(), current.c.provider)
    ).all()

    account_rows = db.execute(
        select(
            current.c.provider,
            current.c.account_id,
            CloudAccount.name,
            func.count(func.distinct(Finding.id)).label("open"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .outerjoin(CloudAccount, _account_name_join(current))
        .where(Finding.status == "open")
        .group_by(current.c.provider, current.c.account_id, CloudAccount.name)
        .order_by(
            func.count(func.distinct(Finding.id)).desc(),
            current.c.provider,
            current.c.account_id,
        )
        .limit(8)
    ).all()

    severity_order = case(
        (current.c.severity == "high", 3),
        (current.c.severity == "medium", 2),
        (current.c.severity == "low", 1),
        else_=0,
    )
    top_rows = db.execute(
        select(
            Finding.id,
            Finding.title,
            Finding.rule_key,
            Finding.resource_id,
            Finding.resource_name,
            Finding.region,
            current.c.provider,
            current.c.account_id,
            CloudAccount.name,
            current.c.collection_run_id,
            current.c.severity,
            current.c.estimated_monthly_savings,
            current.c.currency,
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .outerjoin(CloudAccount, _account_name_join(current))
        .where(Finding.status == "open")
        .order_by(
            current.c.estimated_monthly_savings.desc(),
            severity_order.desc(),
            Finding.id,
        )
        .limit(5)
    ).all()

    recent_changes = _recent_changes(db, provider=provider, account_id=account_id)

    return {
        "scope": {
            "provider": provider.lower() if provider else None,
            "account_id": account_id,
            "valid_scope_count": int(valid_scope_count),
            "has_current_data": bool(valid_scope_count),
        },
        "opportunities": {
            "open": lifecycle_totals["open"],
            "treated": lifecycle_totals["treated"],
            "rejected": lifecycle_totals["rejected"],
            "new_since_previous": recent_changes["new"],
        },
        "severity": {
            "high": by_severity.get("high", 0),
            "medium": by_severity.get("medium", 0),
            "low": by_severity.get("low", 0),
            "other": sum(
                count
                for severity, count in by_severity.items()
                if severity not in {"high", "medium", "low"}
            ),
        },
        "financial": {
            "metric": "estimated_monthly_savings",
            "label": "Economia potencial estimada",
            "period": "month",
            "totals": [
                {
                    "currency": row.currency,
                    "amount": row.amount,
                }
                for row in financial_rows
            ],
        },
        "by_provider": [
            {
                "provider": row.provider,
                "open": int(row.open),
                "estimated_monthly_savings": None,
                "currency": None,
            }
            for row in provider_rows
        ],
        "by_account": [
            {
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.name,
                "open": int(row.open),
                "estimated_monthly_savings": None,
                "currency": None,
            }
            for row in account_rows
        ],
        "top_opportunities": [
            {
                "id": row.id,
                "title": row.title,
                "rule_key": row.rule_key,
                "resource_id": row.resource_id,
                "resource_name": row.resource_name,
                "region": row.region,
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.name,
                "collection_run_id": row.collection_run_id,
                "severity": row.severity,
                "estimated_monthly_savings": row.estimated_monthly_savings,
                "currency": row.currency,
            }
            for row in top_rows
        ],
        "recent_changes": recent_changes,
    }


def _persisted_summary_rows(
    db: Session,
    *,
    provider: str | None,
    account_id: str | None,
):
    latest_valid = _latest_success_runs(provider=provider, account_id=account_id)
    summary = DashboardAccountSummary
    return db.execute(
        select(
            latest_valid.c.run_id.label("expected_run_id"),
            latest_valid.c.provider.label("provider"),
            latest_valid.c.account_id.label("account_id"),
            summary.collection_run_id.label("summary_run_id"),
            summary.open_count.label("open_count"),
            summary.treated_count.label("treated_count"),
            summary.rejected_count.label("rejected_count"),
            summary.severity_counts.label("severity_counts"),
            summary.financial.label("financial"),
            summary.new_count.label("new_count"),
            summary.no_longer_detected_count.label("no_longer_detected_count"),
            summary.has_baseline.label("has_baseline"),
            summary.rules_version_changed.label("rules_version_changed"),
            summary.rules_version_unknown.label("rules_version_unknown"),
            summary.updated_at.label("summary_updated_at"),
            CloudAccount.name.label("account_name"),
        )
        .select_from(latest_valid)
        .outerjoin(
            summary,
            and_(
                summary.provider == latest_valid.c.provider,
                summary.account_id == latest_valid.c.account_id,
            ),
        )
        .outerjoin(
            CloudAccount,
            and_(
                latest_valid.c.provider == CloudAccount.provider,
                latest_valid.c.account_id == CloudAccount.native_account_id,
            ),
        )
        .order_by(latest_valid.c.provider, latest_valid.c.account_id)
    ).all()


def _top_current_opportunities(
    db: Session,
    *,
    provider: str | None,
    account_id: str | None,
) -> list[dict]:
    _, current = _current_observations(provider=provider, account_id=account_id)
    severity_order = case(
        (current.c.severity == "high", 3),
        (current.c.severity == "medium", 2),
        (current.c.severity == "low", 1),
        else_=0,
    )
    rows = db.execute(
        select(
            Finding.id,
            Finding.title,
            Finding.rule_key,
            Finding.resource_id,
            Finding.resource_name,
            Finding.region,
            current.c.provider,
            current.c.account_id,
            CloudAccount.name,
            current.c.collection_run_id,
            current.c.severity,
            current.c.estimated_monthly_savings,
            current.c.currency,
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .outerjoin(CloudAccount, _account_name_join(current))
        .where(Finding.status == "open")
        .order_by(
            current.c.estimated_monthly_savings.desc(),
            severity_order.desc(),
            Finding.id,
        )
        .limit(5)
    ).all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "rule_key": row.rule_key,
            "resource_id": row.resource_id,
            "resource_name": row.resource_name,
            "region": row.region,
            "provider": row.provider,
            "account_id": row.account_id,
            "account_name": row.name,
            "collection_run_id": row.collection_run_id,
            "severity": row.severity,
            "estimated_monthly_savings": row.estimated_monthly_savings,
            "currency": row.currency,
        }
        for row in rows
    ]


def _dashboard_summary_from_persisted_rows(
    db: Session,
    rows,
    *,
    provider: str | None,
    account_id: str | None,
) -> dict:
    lifecycle = {"open": 0, "treated": 0, "rejected": 0}
    severity = {"high": 0, "medium": 0, "low": 0, "other": 0}
    money: dict[str, Decimal] = {}
    providers: dict[str, int] = {}

    for row in rows:
        lifecycle["open"] += int(row.open_count or 0)
        lifecycle["treated"] += int(row.treated_count or 0)
        lifecycle["rejected"] += int(row.rejected_count or 0)
        for level in severity:
            severity[level] += int((row.severity_counts or {}).get(level, 0))
        for total in (row.financial or {}).get("totals", []):
            currency = str(total["currency"])
            money[currency] = money.get(currency, Decimal("0")) + Decimal(str(total["amount"]))
        if row.open_count:
            providers[row.provider] = providers.get(row.provider, 0) + int(row.open_count)

    by_account = sorted(
        (
            {
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.account_name,
                "open": int(row.open_count),
                "estimated_monthly_savings": None,
                "currency": None,
            }
            for row in rows
            if row.open_count
        ),
        key=lambda item: (-item["open"], item["provider"], item["account_id"]),
    )[:8]

    recent_changes = {
        "new": sum(int(row.new_count or 0) for row in rows),
        "no_longer_detected": sum(int(row.no_longer_detected_count or 0) for row in rows),
        "changed": None,
        "changed_available": False,
        "comparable_scopes": sum(bool(row.has_baseline) for row in rows),
        "scopes_without_baseline": sum(not bool(row.has_baseline) for row in rows),
        "rules_version_changed_scopes": sum(bool(row.rules_version_changed) for row in rows),
        "rules_version_unknown_scopes": sum(bool(row.rules_version_unknown) for row in rows),
    }

    return {
        "scope": {
            "provider": provider.lower() if provider else None,
            "account_id": account_id,
            "valid_scope_count": len(rows),
            "has_current_data": bool(rows),
        },
        "opportunities": {
            "open": lifecycle["open"],
            "treated": lifecycle["treated"],
            "rejected": lifecycle["rejected"],
            "new_since_previous": recent_changes["new"],
        },
        "severity": severity,
        "financial": {
            "metric": "estimated_monthly_savings",
            "label": "Economia potencial estimada",
            "period": "month",
            "totals": [
                {"currency": currency, "amount": amount}
                for currency, amount in sorted(money.items())
            ],
        },
        "by_provider": [
            {
                "provider": provider_name,
                "open": open_count,
                "estimated_monthly_savings": None,
                "currency": None,
            }
            for provider_name, open_count in sorted(
                providers.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
        "by_account": by_account,
        "top_opportunities": _top_current_opportunities(
            db,
            provider=provider,
            account_id=account_id,
        ),
        "recent_changes": recent_changes,
    }


def dashboard_summary(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> dict:
    rows = _persisted_summary_rows(db, provider=provider, account_id=account_id)
    stale = [row for row in rows if row.summary_run_id != row.expected_run_id]
    if stale:
        try:
            for row in stale:
                rebuild_account_summary(
                    db,
                    provider=row.provider,
                    account_id=row.account_id,
                    collection_run_id=row.expected_run_id,
                )
            db.commit()
            rows = _persisted_summary_rows(db, provider=provider, account_id=account_id)
        except Exception:
            db.rollback()
            logger.exception(
                "Dashboard summary repair failed provider=%s account_id=%s; using source fallback",
                provider,
                account_id,
            )
            return _dashboard_summary_direct(
                db,
                provider=provider,
                account_id=account_id,
            )

    if any(row.summary_run_id != row.expected_run_id for row in rows):
        return _dashboard_summary_direct(
            db,
            provider=provider,
            account_id=account_id,
        )
    try:
        return _dashboard_summary_from_persisted_rows(
            db,
            rows,
            provider=provider,
            account_id=account_id,
        )
    except (KeyError, TypeError, ValueError):
        logger.exception(
            "Dashboard summary payload invalid provider=%s account_id=%s; using source fallback",
            provider,
            account_id,
        )
        return _dashboard_summary_direct(
            db,
            provider=provider,
            account_id=account_id,
        )


def _health_base(*, provider: str | None, account_id: str | None):
    execution_ranked = _ranked_runs(
        provider=provider,
        account_id=account_id,
        successful_only=False,
        name="dashboard_execution_ranked",
    )
    valid_ranked = _ranked_runs(
        provider=provider,
        account_id=account_id,
        successful_only=True,
        name="dashboard_health_valid_ranked",
    )
    execution = (
        select(execution_ranked)
        .where(execution_ranked.c.run_rank == 1)
        .cte("dashboard_latest_execution")
    )
    valid = (
        select(valid_ranked)
        .where(valid_ranked.c.run_rank == 1)
        .cte("dashboard_health_latest_valid")
    )
    return execution, valid


def _collection_coverage(
    db: Session,
    *,
    provider: str | None,
    account_id: str | None,
) -> dict:
    supported_providers = providers_supporting(ProviderOperation.MANUAL_COLLECTION)
    supported = CloudAccount.provider.in_(supported_providers)
    enabled = CloudAccount.enabled.is_(True)
    has_execution = (
        select(CollectionRun.id)
        .where(
            CollectionRun.provider == CloudAccount.provider,
            CollectionRun.account_id == CloudAccount.native_account_id,
        )
        .exists()
    )

    statement = select(
        func.count().label("registered_accounts"),
        func.count(case((enabled, 1))).label("enabled_accounts"),
        func.count(case((supported, 1))).label("collection_supported_accounts"),
        func.count(case((and_(supported, enabled), 1))).label("collection_eligible_accounts"),
        func.count(case((and_(supported, enabled, ~has_execution), 1))).label(
            "eligible_without_execution"
        ),
    ).select_from(CloudAccount)
    if provider:
        statement = statement.where(CloudAccount.provider == provider.lower())
    if account_id:
        statement = statement.where(CloudAccount.native_account_id == account_id)

    row = db.execute(statement).one()
    registered = int(row.registered_accounts or 0)
    enabled_count = int(row.enabled_accounts or 0)
    supported_count = int(row.collection_supported_accounts or 0)
    return {
        "registered_accounts": registered,
        "enabled_accounts": enabled_count,
        "disabled_accounts": registered - enabled_count,
        "collection_supported_accounts": supported_count,
        "collection_eligible_accounts": int(row.collection_eligible_accounts or 0),
        "collection_unsupported_accounts": registered - supported_count,
        "eligible_without_execution": int(row.eligible_without_execution or 0),
    }


def collection_health(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
    limit: int = 8,
) -> dict:
    coverage = _collection_coverage(db, provider=provider, account_id=account_id)
    execution, valid = _health_base(provider=provider, account_id=account_id)
    execution_scan = aliased(Scan, name="dashboard_execution_scan")
    valid_scan = aliased(Scan, name="dashboard_valid_scan")

    joined = (
        select(
            execution.c.run_id.label("execution_id"),
            execution.c.provider,
            execution.c.account_id,
            execution.c.started_at.label("execution_started_at"),
            execution.c.finished_at.label("execution_finished_at"),
            execution.c.status.label("execution_status"),
            execution_scan.status.label("execution_scan_status"),
            valid.c.run_id.label("valid_id"),
            valid.c.started_at.label("valid_started_at"),
            valid.c.finished_at.label("valid_finished_at"),
            valid.c.analyzer_version.label("valid_rules_version"),
            valid_scan.status.label("valid_scan_status"),
        )
        .select_from(execution)
        .outerjoin(
            valid,
            and_(
                valid.c.provider == execution.c.provider,
                valid.c.account_id == execution.c.account_id,
            ),
        )
        .outerjoin(execution_scan, execution.c.scan_id == execution_scan.id)
        .outerjoin(valid_scan, valid.c.scan_id == valid_scan.id)
        .cte("dashboard_health_joined")
    )

    aggregate = db.execute(
        select(
            func.count().label("total_scopes"),
            func.count(case((joined.c.valid_id.is_not(None), 1))).label("valid_scopes"),
            func.count(case((joined.c.execution_status == "FAILED", 1))).label(
                "failed_latest_execution"
            ),
            func.count(case((joined.c.execution_status == "RUNNING", 1))).label(
                "running_latest_execution"
            ),
            func.count(case((joined.c.execution_status == "SUCCESS", 1))).label(
                "successful_latest_execution"
            ),
            func.count(case((joined.c.valid_scan_status == "completed_with_warnings", 1))).label(
                "valid_with_warnings"
            ),
            func.max(joined.c.valid_started_at).label("newest_valid_at"),
            func.min(joined.c.valid_started_at).label("oldest_valid_at"),
        ).select_from(joined)
    ).one()

    account_join = and_(
        joined.c.provider == CloudAccount.provider,
        joined.c.account_id == CloudAccount.native_account_id,
    )
    rows = db.execute(
        select(joined, CloudAccount.name.label("account_name"))
        .select_from(joined)
        .outerjoin(CloudAccount, account_join)
        .order_by(
            case(
                (joined.c.execution_status == "FAILED", 0),
                (joined.c.execution_status == "RUNNING", 1),
                (joined.c.valid_id.is_(None), 2),
                else_=3,
            ),
            joined.c.valid_started_at.asc(),
            joined.c.provider,
            joined.c.account_id,
        )
        .limit(limit)
    ).all()

    oldest = db.execute(
        select(
            joined.c.provider,
            joined.c.account_id,
            CloudAccount.name.label("account_name"),
            joined.c.valid_started_at,
        )
        .select_from(joined)
        .outerjoin(CloudAccount, account_join)
        .where(joined.c.valid_id.is_not(None))
        .order_by(joined.c.valid_started_at.asc(), joined.c.provider, joined.c.account_id)
        .limit(1)
    ).first()

    return {
        "scope": {
            "provider": provider.lower() if provider else None,
            "account_id": account_id,
        },
        "coverage": coverage,
        "total_scopes": int(aggregate.total_scopes or 0),
        "valid_scopes": int(aggregate.valid_scopes or 0),
        "latest_execution": {
            "failed": int(aggregate.failed_latest_execution or 0),
            "running": int(aggregate.running_latest_execution or 0),
            "success": int(aggregate.successful_latest_execution or 0),
        },
        "valid_with_warnings": int(aggregate.valid_with_warnings or 0),
        "newest_valid_at": aggregate.newest_valid_at,
        "oldest_valid_at": aggregate.oldest_valid_at,
        "oldest_valid_scope": (
            {
                "provider": oldest.provider,
                "account_id": oldest.account_id,
                "account_name": oldest.account_name,
                "started_at": oldest.valid_started_at,
            }
            if oldest
            else None
        ),
        # Não existe política de atraso persistida no domínio atual.
        "stale_policy_configured": False,
        "items": [
            {
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.account_name,
                "latest_execution": {
                    "id": row.execution_id,
                    "status": row.execution_status,
                    "started_at": row.execution_started_at,
                    "finished_at": row.execution_finished_at,
                    "has_warnings": row.execution_scan_status == "completed_with_warnings",
                },
                "latest_valid": (
                    {
                        "id": row.valid_id,
                        "status": "SUCCESS",
                        "started_at": row.valid_started_at,
                        "finished_at": row.valid_finished_at,
                        "rules_version": row.valid_rules_version,
                        "has_warnings": row.valid_scan_status == "completed_with_warnings",
                    }
                    if row.valid_id
                    else None
                ),
            }
            for row in rows
        ],
    }
