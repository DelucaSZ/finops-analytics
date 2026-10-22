from __future__ import annotations

import logging
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.dashboard_summary import DashboardAccountSummary
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.opportunity_run_comparison import opportunity_run_changes

logger = logging.getLogger("deepops.dashboard_summary")

_OPEN = "open"
_TREATED = "treated"
_REJECTED = "rejected"
_SEVERITIES = ("high", "medium", "low")


def _latest_successful_run(
    db: Session,
    *,
    provider: str,
    account_id: str,
) -> CollectionRun | None:
    return db.scalar(
        select(CollectionRun)
        .where(
            CollectionRun.status == CollectionRunStatus.SUCCESS,
            CollectionRun.provider == provider.lower(),
            CollectionRun.account_id == account_id,
        )
        .order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc())
        .limit(1)
    )


def _current_metrics(db: Session, target: CollectionRun) -> dict:
    rows = db.execute(
        select(
            OpportunityObservation.currency,
            func.count(case((Finding.status == _OPEN, 1))).label("open"),
            func.count(case((Finding.status == _TREATED, 1))).label("treated"),
            func.count(case((Finding.status == _REJECTED, 1))).label("rejected"),
            *[
                func.count(
                    case(
                        (
                            and_(
                                Finding.status == _OPEN,
                                OpportunityObservation.severity == severity,
                            ),
                            1,
                        )
                    )
                ).label(f"severity_{severity}")
                for severity in _SEVERITIES
            ],
            func.count(
                case(
                    (
                        and_(
                            Finding.status == _OPEN,
                            OpportunityObservation.severity.not_in(_SEVERITIES),
                        ),
                        1,
                    )
                )
            ).label("severity_other"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            Finding.status == _OPEN,
                            OpportunityObservation.estimated_monthly_savings,
                        ),
                        else_=Decimal("0"),
                    )
                ),
                Decimal("0"),
            ).label("amount"),
        )
        .select_from(OpportunityObservation)
        .join(Finding, Finding.id == OpportunityObservation.opportunity_id)
        .where(
            OpportunityObservation.collection_run_id == target.id,
            Finding.archived_at.is_(None),
        )
        .group_by(OpportunityObservation.currency)
        .order_by(OpportunityObservation.currency)
    ).all()

    severity_counts = {
        severity: sum(int(getattr(row, f"severity_{severity}") or 0) for row in rows)
        for severity in _SEVERITIES
    }
    severity_counts["other"] = sum(int(row.severity_other or 0) for row in rows)

    financial_totals = [
        {
            "currency": row.currency,
            "amount": format(Decimal(row.amount or 0), "f"),
        }
        for row in rows
        if int(row.open or 0) > 0
    ]

    return {
        "open_count": sum(int(row.open or 0) for row in rows),
        "treated_count": sum(int(row.treated or 0) for row in rows),
        "rejected_count": sum(int(row.rejected or 0) for row in rows),
        "severity_counts": severity_counts,
        "financial": {
            "metric": "estimated_monthly_savings",
            "period": "month",
            "totals": financial_totals,
        },
    }


def _comparison_metrics(db: Session, target: CollectionRun) -> dict:
    changes = opportunity_run_changes(db, target)
    summary = changes["summary"]
    baseline_run_id = changes["baseline_run_id"]
    comparable = bool(changes["comparable"])
    rules_version_changed = changes["rules_version_changed"]
    return {
        "baseline_collection_run_id": baseline_run_id,
        "new_count": int(summary["operational_new_vs_previous"] if comparable else 0),
        "no_longer_detected_count": int(summary["no_longer_detected"] if comparable else 0),
        "has_baseline": comparable,
        "rules_version_changed": rules_version_changed is True,
        "rules_version_unknown": baseline_run_id is not None and rules_version_changed is None,
    }


def calculate_account_summary(db: Session, target: CollectionRun) -> dict:
    if target.status != CollectionRunStatus.SUCCESS:
        raise ValueError("Dashboard summaries can only be built from successful collections")
    return _current_metrics(db, target) | _comparison_metrics(db, target)


def _persist(
    db: Session,
    target: CollectionRun,
    values: dict,
    *,
    summary: DashboardAccountSummary | None = None,
) -> DashboardAccountSummary:
    identity = {"provider": target.provider, "account_id": target.account_id}
    if summary is None:
        summary = DashboardAccountSummary(**identity, collection_run_id=target.id)
        db.add(summary)

    summary.collection_run_id = target.id
    summary.baseline_collection_run_id = values["baseline_collection_run_id"]
    summary.open_count = values["open_count"]
    summary.treated_count = values["treated_count"]
    summary.rejected_count = values["rejected_count"]
    summary.severity_counts = dict(values["severity_counts"])
    summary.financial = dict(values["financial"])
    summary.new_count = values["new_count"]
    summary.no_longer_detected_count = values["no_longer_detected_count"]
    summary.has_baseline = values["has_baseline"]
    summary.rules_version_changed = values["rules_version_changed"]
    summary.rules_version_unknown = values["rules_version_unknown"]
    summary.updated_at = utcnow()
    db.flush()

    logger.info(
        "Dashboard summary rebuilt provider=%s account_id=%s collection_run_id=%s",
        target.provider,
        target.account_id,
        target.id,
    )
    return summary


def rebuild_account_summary(
    db: Session,
    *,
    provider: str,
    account_id: str,
    collection_run_id: str | None = None,
) -> DashboardAccountSummary | None:
    provider = provider.lower()
    identity = {"provider": provider, "account_id": account_id}
    # The persisted row is also the scope mutex. Serializing rebuilds prevents two
    # lifecycle decisions or a CollectionRun completion from publishing stale counts.
    summary = db.scalar(
        select(DashboardAccountSummary)
        .where(
            DashboardAccountSummary.provider == provider,
            DashboardAccountSummary.account_id == account_id,
        )
        .with_for_update()
    )
    target = _latest_successful_run(db, provider=provider, account_id=account_id)

    if target is None:
        if collection_run_id is not None:
            requested = db.get(CollectionRun, collection_run_id)
            if requested is None:
                raise ValueError(f"CollectionRun {collection_run_id} does not exist")
            if requested.provider != provider or requested.account_id != account_id:
                raise ValueError("CollectionRun does not belong to the requested provider/account")
            raise ValueError("CollectionRun is not successful")
        if summary is not None:
            db.delete(summary)
            db.flush()
        return None

    if collection_run_id is not None and target.id != collection_run_id:
        requested = db.get(CollectionRun, collection_run_id)
        if requested is None:
            raise ValueError(f"CollectionRun {collection_run_id} does not exist")
        if requested.provider != provider or requested.account_id != account_id:
            raise ValueError("CollectionRun does not belong to the requested provider/account")
        if requested.status != CollectionRunStatus.SUCCESS:
            raise ValueError("CollectionRun is not successful")
        raise ValueError(
            "CollectionRun is not the latest successful collection for this provider/account"
        )

    if summary is not None and (
        summary.provider != identity["provider"] or summary.account_id != identity["account_id"]
    ):
        raise RuntimeError("Locked dashboard summary identity changed unexpectedly")
    return _persist(
        db,
        target,
        calculate_account_summary(db, target),
        summary=summary,
    )


def refresh_account_summary_after_lifecycle(
    db: Session,
    *,
    provider: str,
    account_id: str,
) -> DashboardAccountSummary | None:
    provider = provider.lower()
    summary = db.scalar(
        select(DashboardAccountSummary)
        .where(
            DashboardAccountSummary.provider == provider,
            DashboardAccountSummary.account_id == account_id,
        )
        .with_for_update()
    )
    # Resolve the target after acquiring the summary lock so a concurrent refresh that
    # completed while we waited is visible to this transaction.
    target = _latest_successful_run(db, provider=provider, account_id=account_id)
    if target is None:
        return None

    if summary is None or summary.collection_run_id != target.id:
        return rebuild_account_summary(
            db,
            provider=provider,
            account_id=account_id,
            collection_run_id=target.id,
        )

    # Lifecycle changes and the derived aggregate commit atomically in the caller.
    # The shared comparison service also keeps rejected suppression consistent.
    values = _current_metrics(db, target) | _comparison_metrics(db, target)
    summary.baseline_collection_run_id = values["baseline_collection_run_id"]
    summary.open_count = values["open_count"]
    summary.treated_count = values["treated_count"]
    summary.rejected_count = values["rejected_count"]
    summary.severity_counts = dict(values["severity_counts"])
    summary.financial = dict(values["financial"])
    summary.new_count = values["new_count"]
    summary.no_longer_detected_count = values["no_longer_detected_count"]
    summary.has_baseline = values["has_baseline"]
    summary.rules_version_changed = values["rules_version_changed"]
    summary.rules_version_unknown = values["rules_version_unknown"]
    summary.updated_at = utcnow()
    db.flush()
    logger.info(
        "Dashboard summary lifecycle refresh provider=%s account_id=%s collection_run_id=%s",
        provider,
        account_id,
        target.id,
    )
    return summary


def refresh_summaries_for_findings(
    db: Session,
    findings: Iterable[Finding],
) -> int:
    scopes = sorted({(finding.provider, finding.account_id) for finding in findings})
    if not scopes:
        return 0
    # Lifecycle changes and the derived aggregate commit atomically in the caller.
    db.flush()
    for provider, account_id in scopes:
        refresh_account_summary_after_lifecycle(
            db,
            provider=provider,
            account_id=account_id,
        )
    return len(scopes)


def _latest_successful_runs(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> list[CollectionRun]:
    ranked = select(
        CollectionRun.id.label("run_id"),
        func.row_number()
        .over(
            partition_by=(CollectionRun.provider, CollectionRun.account_id),
            order_by=(CollectionRun.started_at.desc(), CollectionRun.id.desc()),
        )
        .label("run_rank"),
    ).where(CollectionRun.status == CollectionRunStatus.SUCCESS)
    if provider:
        ranked = ranked.where(CollectionRun.provider == provider.lower())
    if account_id:
        ranked = ranked.where(CollectionRun.account_id == account_id)
    ranked = ranked.cte("dashboard_backfill_ranked")
    return list(
        db.scalars(
            select(CollectionRun)
            .join(ranked, ranked.c.run_id == CollectionRun.id)
            .where(ranked.c.run_rank == 1)
            .order_by(CollectionRun.provider, CollectionRun.account_id)
        )
    )


def backfill_dashboard_summaries(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
    commit_every: int | None = None,
) -> int:
    targets = _latest_successful_runs(db, provider=provider, account_id=account_id)
    rebuilt = 0
    for target in targets:
        summary = rebuild_account_summary(
            db,
            provider=target.provider,
            account_id=target.account_id,
        )
        rebuilt += int(summary is not None)
        if commit_every and rebuilt % commit_every == 0:
            db.commit()
    return rebuilt


def summary_matches_source(
    db: Session,
    *,
    provider: str,
    account_id: str,
) -> bool:
    target = _latest_successful_run(
        db,
        provider=provider.lower(),
        account_id=account_id,
    )
    summary = db.get(
        DashboardAccountSummary,
        {"provider": provider.lower(), "account_id": account_id},
    )
    if target is None:
        return summary is None
    if summary is None or summary.collection_run_id != target.id:
        return False

    expected = calculate_account_summary(db, target)
    return all(
        (
            summary.open_count == expected["open_count"],
            summary.treated_count == expected["treated_count"],
            summary.rejected_count == expected["rejected_count"],
            summary.severity_counts == expected["severity_counts"],
            summary.financial == expected["financial"],
            summary.baseline_collection_run_id == expected["baseline_collection_run_id"],
            summary.new_count == expected["new_count"],
            summary.no_longer_detected_count == expected["no_longer_detected_count"],
            summary.has_baseline == expected["has_baseline"],
            summary.rules_version_changed == expected["rules_version_changed"],
            summary.rules_version_unknown == expected["rules_version_unknown"],
        )
    )
