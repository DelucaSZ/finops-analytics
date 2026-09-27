from __future__ import annotations

from decimal import Decimal

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan


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
        .cte("dashboard_current_observations")
    )
    return latest_valid, current


def _account_name_join(current):
    return and_(
        current.c.provider == "aws",
        current.c.account_id == AwsAccount.aws_account_id,
    )


def _recent_pairs(*, provider: str | None, account_id: str | None):
    ranked = _ranked_runs(
        provider=provider,
        account_id=account_id,
        successful_only=True,
        name="dashboard_comparison_ranked",
    )
    target = ranked.alias("dashboard_target_run")
    baseline = ranked.alias("dashboard_baseline_run")
    return (
        select(
            target.c.provider.label("provider"),
            target.c.account_id.label("account_id"),
            target.c.run_id.label("target_run_id"),
            target.c.started_at.label("target_started_at"),
            target.c.analyzer_version.label("target_rules_version"),
            baseline.c.run_id.label("baseline_run_id"),
            baseline.c.started_at.label("baseline_started_at"),
            baseline.c.analyzer_version.label("baseline_rules_version"),
        )
        .select_from(target)
        .outerjoin(
            baseline,
            and_(
                baseline.c.provider == target.c.provider,
                baseline.c.account_id == target.c.account_id,
                baseline.c.run_rank == 2,
            ),
        )
        .where(target.c.run_rank == 1)
        .cte("dashboard_recent_pairs")
    )


def _recent_changes(db: Session, *, provider: str | None, account_id: str | None) -> dict:
    pairs = _recent_pairs(provider=provider, account_id=account_id)
    metadata = db.execute(
        select(
            func.count().label("total_scopes"),
            func.count(case((pairs.c.baseline_run_id.is_not(None), 1))).label(
                "comparable_scopes"
            ),
            func.count(case((pairs.c.baseline_run_id.is_(None), 1))).label(
                "scopes_without_baseline"
            ),
            func.count(
                case(
                    (
                        and_(
                            pairs.c.baseline_run_id.is_not(None),
                            pairs.c.baseline_rules_version.is_not(None),
                            pairs.c.target_rules_version.is_not(None),
                            pairs.c.baseline_rules_version != pairs.c.target_rules_version,
                        ),
                        1,
                    )
                )
            ).label("rules_version_changed_scopes"),
            func.count(
                case(
                    (
                        and_(
                            pairs.c.baseline_run_id.is_not(None),
                            or_(
                                pairs.c.baseline_rules_version.is_(None),
                                pairs.c.target_rules_version.is_(None),
                            ),
                        ),
                        1,
                    )
                )
            ).label("rules_version_unknown_scopes"),
        ).select_from(pairs)
    ).one()

    target_observation = aliased(OpportunityObservation, name="dashboard_target_observation")
    baseline_probe = aliased(OpportunityObservation, name="dashboard_baseline_probe")
    baseline_exists = (
        select(baseline_probe.id)
        .where(
            baseline_probe.collection_run_id == pairs.c.baseline_run_id,
            baseline_probe.opportunity_id == target_observation.opportunity_id,
        )
        .exists()
    )
    new_count = (
        db.scalar(
            select(func.count())
            .select_from(target_observation)
            .join(pairs, target_observation.collection_run_id == pairs.c.target_run_id)
            .where(
                pairs.c.baseline_run_id.is_not(None),
                ~baseline_exists,
            )
        )
        or 0
    )

    baseline_observation = aliased(OpportunityObservation, name="dashboard_baseline_observation")
    target_probe = aliased(OpportunityObservation, name="dashboard_target_probe")
    target_exists = (
        select(target_probe.id)
        .where(
            target_probe.collection_run_id == pairs.c.target_run_id,
            target_probe.opportunity_id == baseline_observation.opportunity_id,
        )
        .exists()
    )
    no_longer_detected = (
        db.scalar(
            select(func.count())
            .select_from(baseline_observation)
            .join(pairs, baseline_observation.collection_run_id == pairs.c.baseline_run_id)
            .where(
                pairs.c.baseline_run_id.is_not(None),
                ~target_exists,
            )
        )
        or 0
    )

    return {
        "new": int(new_count),
        "no_longer_detected": int(no_longer_detected),
        # Etapa 8 classifica CHANGED por diff semântico de evidence. Consolidar isso aqui
        # exigiria carregar snapshots/evidence de todas as contas; não aproximamos a métrica.
        "changed": None,
        "changed_available": False,
        "comparable_scopes": int(metadata.comparable_scopes or 0),
        "scopes_without_baseline": int(metadata.scopes_without_baseline or 0),
        "rules_version_changed_scopes": int(metadata.rules_version_changed_scopes or 0),
        "rules_version_unknown_scopes": int(metadata.rules_version_unknown_scopes or 0),
    }


def dashboard_summary(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> dict:
    latest_valid, current = _current_observations(provider=provider, account_id=account_id)

    valid_scope_count = db.scalar(select(func.count()).select_from(latest_valid)) or 0

    totals = db.execute(
        select(
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
            ).label("estimated_monthly_savings"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
    ).one()

    severity_rows = db.execute(
        select(current.c.severity, func.count(func.distinct(Finding.id)))
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .where(Finding.status == "open")
        .group_by(current.c.severity)
    ).all()
    by_severity = {str(severity): int(count) for severity, count in severity_rows}

    provider_rows = db.execute(
        select(
            current.c.provider,
            func.count(func.distinct(Finding.id)).label("open"),
            func.coalesce(
                func.sum(current.c.estimated_monthly_savings), Decimal("0")
            ).label("estimated_monthly_savings"),
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
            AwsAccount.name,
            func.count(func.distinct(Finding.id)).label("open"),
            func.coalesce(
                func.sum(current.c.estimated_monthly_savings), Decimal("0")
            ).label("estimated_monthly_savings"),
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .outerjoin(AwsAccount, _account_name_join(current))
        .where(Finding.status == "open")
        .group_by(current.c.provider, current.c.account_id, AwsAccount.name)
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
            AwsAccount.name,
            current.c.collection_run_id,
            current.c.severity,
            current.c.estimated_monthly_savings,
        )
        .select_from(current)
        .join(Finding, Finding.id == current.c.opportunity_id)
        .outerjoin(AwsAccount, _account_name_join(current))
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
            "open": int(totals.open or 0),
            "treated": int(totals.treated or 0),
            "rejected": int(totals.rejected or 0),
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
            # O schema atual da Etapa 8 define esta métrica em USD/mês. A resposta usa
            # uma lista por moeda para não cristalizar a arquitetura em um total único.
            "totals": [
                {
                    "currency": "USD",
                    "amount": totals.estimated_monthly_savings or Decimal("0"),
                }
            ],
        },
        "by_provider": [
            {
                "provider": row.provider,
                "open": int(row.open),
                "estimated_monthly_savings": row.estimated_monthly_savings,
                "currency": "USD",
            }
            for row in provider_rows
        ],
        "by_account": [
            {
                "provider": row.provider,
                "account_id": row.account_id,
                "account_name": row.name,
                "open": int(row.open),
                "estimated_monthly_savings": row.estimated_monthly_savings,
                "currency": "USD",
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
                "currency": "USD",
            }
            for row in top_rows
        ],
        "recent_changes": recent_changes,
    }


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


def collection_health(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
    limit: int = 8,
) -> dict:
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
            func.count(
                case((joined.c.valid_scan_status == "completed_with_warnings", 1))
            ).label("valid_with_warnings"),
            func.max(joined.c.valid_started_at).label("newest_valid_at"),
            func.min(joined.c.valid_started_at).label("oldest_valid_at"),
        ).select_from(joined)
    ).one()

    account_join = and_(
        joined.c.provider == "aws",
        joined.c.account_id == AwsAccount.aws_account_id,
    )
    rows = db.execute(
        select(joined, AwsAccount.name.label("account_name"))
        .select_from(joined)
        .outerjoin(AwsAccount, account_join)
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
            AwsAccount.name.label("account_name"),
            joined.c.valid_started_at,
        )
        .select_from(joined)
        .outerjoin(AwsAccount, account_join)
        .where(joined.c.valid_id.is_not(None))
        .order_by(joined.c.valid_started_at.asc(), joined.c.provider, joined.c.account_id)
        .limit(1)
    ).first()

    return {
        "scope": {
            "provider": provider.lower() if provider else None,
            "account_id": account_id,
        },
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
