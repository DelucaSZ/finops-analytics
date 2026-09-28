from __future__ import annotations

import logging
from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session, aliased

from app.db.base import utcnow
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.dashboard_summary import DashboardAccountSummary
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.collection_comparison import previous_comparable_run

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
        .where(OpportunityObservation.collection_run_id == target.id)
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
    baseline = previous_comparable_run(db, target)
    if baseline is None:
        return {
            "baseline_collection_run_id": None,
            "new_count": 0,
            "no_longer_detected_count": 0,
            "has_baseline": False,
            "rules_version_changed": False,
            "rules_version_unknown": False,
        }

    target_observation = aliased(OpportunityObservation, name="summary_target_observation")
    baseline_probe = aliased(OpportunityObservation, name="summary_baseline_probe")
    baseline_exists = (
        select(baseline_probe.id)
        .where(
            baseline_probe.collection_run_id == baseline.id,
            baseline_probe.opportunity_id == target_observation.opportunity_id,
        )
        .exists()
    )
    new_count = (
        db.scalar(
            select(func.count())
            .select_from(target_observation)
            .where(
                target_observation.collection_run_id == target.id,
                ~baseline_exists,
            )
        )
        or 0
    )

    baseline_observation = aliased(OpportunityObservation, name="summary_baseline_observation")
    target_probe = aliased(OpportunityObservation, name="summary_target_probe")
    target_exists = (
        select(target_probe.id)
        .where(
            target_probe.collection_run_id == target.id,
            target_probe.opportunity_id == baseline_observation.opportunity_id,
        )
        .exists()
    )
    no_longer_detected_count = (
        db.scalar(
            select(func.count())
            .select_from(baseline_observation)
            .where(
                baseline_observation.collection_run_id == baseline.id,
                ~target_exists,
            )
        )
        or 0
    )

    rules_unknown = baseline.analyzer_version is None or target.analyzer_version is None
    rules_changed = bool(not rules_unknown and baseline.analyzer_version != target.analyzer_version)
    return {
        "baseline_collection_run_id": baseline.id,
        "new_count": int(new_count),
        "no_longer_detected_count": int(no_longer_detected_count),
        "has_baseline": True,
        "rules_version_changed": rules_changed,
        "rules_version_unknown": rules_unknown,
    }


def calculate_account_summary(db: Session, target: CollectionRun) -> dict:
    if target.status != CollectionRunStatus.SUCCESS:
        raise ValueError("Dashboard summaries can only be built from successful collections")
    return _current_metrics(db, target) | _comparison_metrics(db, target)


def _persist(
    db: Session,
    target: CollectionRun,
    values: dict,
) -> DashboardAccountSummary:
    identity = {"provider": target.provider, "account_id": target.account_id}
    summary = db.get(DashboardAccountSummary, identity)
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
    if collection_run_id is None:
        target = _latest_successful_run(db, provider=provider, account_id=account_id)
    else:
        target = db.get(CollectionRun, collection_run_id)
        if target is None:
            raise ValueError(f"CollectionRun {collection_run_id} does not exist")
        if target.provider != provider or target.account_id != account_id:
            raise ValueError("CollectionRun does not belong to the requested provider/account")
        if target.status != CollectionRunStatus.SUCCESS:
            raise ValueError("CollectionRun is not successful")

    if target is None:
        existing = db.get(
            DashboardAccountSummary,
            {"provider": provider, "account_id": account_id},
        )
        if existing is not None:
            db.delete(existing)
            db.flush()
        return None

    return _persist(db, target, calculate_account_summary(db, target))


def refresh_account_summary_after_lifecycle(
    db: Session,
    *,
    provider: str,
    account_id: str,
) -> DashboardAccountSummary | None:
    provider = provider.lower()
    target = _latest_successful_run(db, provider=provider, account_id=account_id)
    if target is None:
        return None

    summary = db.get(
        DashboardAccountSummary,
        {"provider": provider, "account_id": account_id},
    )
    if summary is None or summary.collection_run_id != target.id:
        return rebuild_account_summary(
            db,
            provider=provider,
            account_id=account_id,
            collection_run_id=target.id,
        )

    values = _current_metrics(db, target)
    summary.open_count = values["open_count"]
    summary.treated_count = values["treated_count"]
    summary.rejected_count = values["rejected_count"]
    summary.severity_counts = dict(values["severity_counts"])
    summary.financial = dict(values["financial"])
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
        _persist(db, target, calculate_account_summary(db, target))
        rebuilt += 1
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
