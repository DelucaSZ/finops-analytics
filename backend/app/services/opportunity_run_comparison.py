from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.collection_scope_execution import (
    CollectionScopeExecution,
    CollectionScopeExecutionStatus,
)
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.collection_comparison import previous_comparable_run
from app.services.collection_errors import sanitize_collection_error

DiscoveryType = Literal[
    "observed",
    "first_seen",
    "new_vs_previous",
    "reappeared",
    "continued",
    "no_longer_detected",
]


@dataclass(frozen=True)
class OpportunityRunContext:
    target: CollectionRun
    baseline: CollectionRun | None
    comparable: bool
    reason: str | None
    rules_version_changed: bool | None
    partial_coverage: bool
    coverage: dict[str, int]
    scope_issues: tuple[dict, ...]


def _observed_in(run_id: str):
    return (
        select(OpportunityObservation.id)
        .where(
            OpportunityObservation.opportunity_id == Finding.id,
            OpportunityObservation.collection_run_id == run_id,
        )
        .correlate(Finding)
        .exists()
    )


def _covered_by_target(target: CollectionRun):
    return (
        select(CollectionScopeExecution.id)
        .where(
            CollectionScopeExecution.collection_run_id == target.id,
            CollectionScopeExecution.provider == Finding.provider,
            CollectionScopeExecution.account_id == Finding.account_id,
            CollectionScopeExecution.rule_key == Finding.rule_key,
            CollectionScopeExecution.status == CollectionScopeExecutionStatus.SUCCESS,
            or_(Finding.region.is_(None), CollectionScopeExecution.region == Finding.region),
        )
        .correlate(Finding)
        .exists()
    )


def _scope_coverage(db: Session, target: CollectionRun) -> tuple[dict[str, int], tuple[dict, ...]]:
    rows = list(
        db.scalars(
            select(CollectionScopeExecution)
            .where(CollectionScopeExecution.collection_run_id == target.id)
            .order_by(
                CollectionScopeExecution.provider,
                CollectionScopeExecution.account_id,
                CollectionScopeExecution.region,
                CollectionScopeExecution.rule_key,
            )
        )
    )
    counts = {"SUCCESS": 0, "FAILED": 0, "SKIPPED": 0}
    issues: list[dict] = []
    for scope in rows:
        status = str(scope.status)
        counts[status] = counts.get(status, 0) + 1
        if status != CollectionScopeExecutionStatus.SUCCESS:
            issues.append(
                {
                    "provider": scope.provider,
                    "account_id": scope.account_id,
                    "region": scope.region,
                    "service": scope.service,
                    "rule_key": scope.rule_key,
                    "status": status,
                    "error_detail": sanitize_collection_error(scope.error_detail),
                }
            )
    return (
        {
            "total_scopes": len(rows),
            "successful_scopes": counts.get("SUCCESS", 0),
            "failed_scopes": counts.get("FAILED", 0),
            "skipped_scopes": counts.get("SKIPPED", 0),
            "comparable_scopes": counts.get("SUCCESS", 0),
        },
        tuple(issues),
    )


def _rules_version_changed(
    baseline: CollectionRun | None,
    target: CollectionRun,
) -> bool | None:
    if baseline is None:
        return None
    if baseline.analyzer_version is None or target.analyzer_version is None:
        return None
    return baseline.analyzer_version != target.analyzer_version


def resolve_run_context(db: Session, target: CollectionRun) -> OpportunityRunContext:
    coverage, scope_issues = _scope_coverage(db, target)
    partial_coverage = coverage["successful_scopes"] < coverage["total_scopes"]

    if target.status != CollectionRunStatus.SUCCESS:
        return OpportunityRunContext(
            target=target,
            baseline=None,
            comparable=False,
            reason="TARGET_NOT_SUCCESSFUL",
            rules_version_changed=None,
            partial_coverage=partial_coverage,
            coverage=coverage,
            scope_issues=scope_issues,
        )
    if not target.detailed_observations_available:
        return OpportunityRunContext(
            target=target,
            baseline=None,
            comparable=False,
            reason="TARGET_OBSERVATIONS_EXPIRED",
            rules_version_changed=None,
            partial_coverage=partial_coverage,
            coverage=coverage,
            scope_issues=scope_issues,
        )

    baseline = previous_comparable_run(db, target)
    if baseline is None:
        return OpportunityRunContext(
            target=target,
            baseline=None,
            comparable=False,
            reason="NO_BASELINE",
            rules_version_changed=None,
            partial_coverage=partial_coverage,
            coverage=coverage,
            scope_issues=scope_issues,
        )
    if not baseline.detailed_observations_available:
        return OpportunityRunContext(
            target=target,
            baseline=baseline,
            comparable=False,
            reason="BASELINE_OBSERVATIONS_EXPIRED",
            rules_version_changed=_rules_version_changed(baseline, target),
            partial_coverage=partial_coverage,
            coverage=coverage,
            scope_issues=scope_issues,
        )

    return OpportunityRunContext(
        target=target,
        baseline=baseline,
        comparable=True,
        reason=None,
        rules_version_changed=_rules_version_changed(baseline, target),
        partial_coverage=partial_coverage,
        coverage=coverage,
        scope_issues=scope_issues,
    )


def _classification_condition(context: OpportunityRunContext, discovery_type: DiscoveryType):
    target_observed = _observed_in(context.target.id)
    if discovery_type == "observed":
        return target_observed
    if discovery_type == "first_seen":
        return and_(
            target_observed,
            Finding.first_seen_collection_run_id == context.target.id,
        )

    if context.baseline is None or not context.comparable:
        return None
    baseline_observed = _observed_in(context.baseline.id)
    if discovery_type == "continued":
        return and_(target_observed, baseline_observed)
    if discovery_type == "new_vs_previous":
        return and_(target_observed, ~baseline_observed)
    if discovery_type == "reappeared":
        return and_(
            target_observed,
            ~baseline_observed,
            Finding.first_seen_collection_run_id.is_not(None),
            Finding.first_seen_collection_run_id != context.target.id,
        )
    if discovery_type == "no_longer_detected":
        return and_(
            baseline_observed,
            ~target_observed,
            _covered_by_target(context.target),
        )
    raise ValueError(f"Unsupported discovery_type: {discovery_type}")


def _count(db: Session, condition, *, operational_only: bool = False) -> int:
    statement = select(func.count()).select_from(Finding).where(condition)
    if operational_only:
        statement = statement.where(Finding.status != "rejected", Finding.archived_at.is_(None))
    return int(db.scalar(statement) or 0)


def _run_reference(run: CollectionRun | None) -> dict | None:
    if run is None:
        return None
    return {
        "id": run.id,
        "provider": run.provider,
        "account_id": run.account_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "analyzer_version": run.analyzer_version,
        "detailed_observations_available": run.detailed_observations_available,
    }


def _comparison_status(context: OpportunityRunContext) -> str:
    if context.target.status == CollectionRunStatus.RUNNING:
        return "RUNNING"
    if context.target.status == CollectionRunStatus.FAILED:
        return "FAILED"
    if context.reason in {"TARGET_OBSERVATIONS_EXPIRED", "BASELINE_OBSERVATIONS_EXPIRED"}:
        return "EXPIRED"
    if context.reason == "NO_BASELINE":
        return "NO_BASELINE"
    if context.comparable and context.partial_coverage:
        return "PARTIAL"
    if context.comparable:
        return "COMPARABLE"
    return "UNAVAILABLE"


def opportunity_run_changes(db: Session, target: CollectionRun) -> dict:
    context = resolve_run_context(db, target)

    if target.detailed_observations_available:
        observed_condition = _classification_condition(context, "observed")
        first_seen_condition = _classification_condition(context, "first_seen")
        observed = _count(db, observed_condition)
        first_seen = _count(db, first_seen_condition)
    else:
        # Preserve the known aggregate instead of returning a misleading zero after retention purge.
        observed = target.opportunities_found
        first_seen = 0

    summary = {
        "observed": observed,
        "first_seen": first_seen,
        "new_vs_previous": 0,
        "reappeared": 0,
        "continued": 0,
        "no_longer_detected": 0,
        "operational_new_vs_previous": 0,
    }
    if context.comparable:
        for discovery_type in (
            "new_vs_previous",
            "reappeared",
            "continued",
            "no_longer_detected",
        ):
            condition = _classification_condition(context, discovery_type)
            summary[discovery_type] = _count(db, condition)
        new_condition = _classification_condition(context, "new_vs_previous")
        summary["operational_new_vs_previous"] = _count(db, new_condition, operational_only=True)

    warnings: list[dict[str, str]] = []
    if context.rules_version_changed is True:
        warnings.append(
            {
                "code": "RULES_VERSION_CHANGED",
                "message": (
                    "Esta comparação utiliza coletas com versões de regras diferentes; "
                    "parte das diferenças pode ter sido causada por mudanças nos analyzers."
                ),
            }
        )
    elif context.baseline is not None and context.rules_version_changed is None:
        warnings.append(
            {
                "code": "RULES_VERSION_UNAVAILABLE",
                "message": "Não foi possível confirmar igualdade da analyzer_version.",
            }
        )
    if context.partial_coverage:
        warnings.append(
            {
                "code": "PARTIAL_COVERAGE",
                "message": (
                    f"{context.coverage['failed_scopes']} scope(s) falharam e "
                    f"{context.coverage['skipped_scopes']} foram ignorados. "
                    "no_longer_detected considera somente scopes com cobertura autoritativa."
                ),
            }
        )

    return {
        "collection_run_id": target.id,
        "status": target.status,
        "comparison_status": _comparison_status(context),
        "baseline_run_id": context.baseline.id if context.baseline else None,
        "baseline": _run_reference(context.baseline),
        "comparable": context.comparable,
        "reason": context.reason,
        "target_details_available": target.detailed_observations_available,
        "comparison_details_available": context.comparable,
        "rules_version_changed": context.rules_version_changed,
        "partial_coverage": context.partial_coverage,
        "coverage": context.coverage,
        "scope_issues": list(context.scope_issues),
        "summary": summary,
        "warnings": warnings,
    }


def list_run_opportunities(
    db: Session,
    target: CollectionRun,
    *,
    discovery_type: DiscoveryType,
    page: int,
    page_size: int,
    status: str | None = None,
    include_archived: bool = False,
) -> dict:
    context = resolve_run_context(db, target)
    condition = _classification_condition(context, discovery_type)
    if context.reason == "TARGET_OBSERVATIONS_EXPIRED":
        condition = None
    if condition is None:
        return {
            "collection_run_id": target.id,
            "baseline_run_id": context.baseline.id if context.baseline else None,
            "comparable": context.comparable,
            "reason": context.reason,
            "discovery_type": discovery_type,
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "total_pages": 0,
        }

    filtered = select(Finding).where(condition)
    count_statement = select(func.count()).select_from(Finding).where(condition)
    if status:
        filtered = filtered.where(Finding.status == status)
        count_statement = count_statement.where(Finding.status == status)
    if not include_archived:
        filtered = filtered.where(Finding.archived_at.is_(None))
        count_statement = count_statement.where(Finding.archived_at.is_(None))

    total = int(db.scalar(count_statement) or 0)
    findings = list(
        db.scalars(
            filtered.order_by(Finding.last_seen_at.desc(), Finding.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    items = [
        {
            "id": finding.id,
            "fingerprint": finding.fingerprint,
            "provider": finding.provider,
            "account_id": finding.account_id,
            "rule_key": finding.rule_key,
            "service": finding.service,
            "region": finding.region,
            "resource_id": finding.resource_id,
            "resource_name": finding.resource_name,
            "resource_type": finding.resource_type,
            "title": finding.title,
            "severity": finding.severity,
            "status": finding.status,
            "presence_status": finding.presence_status,
            "first_seen_at": finding.first_seen_at,
            "last_seen_at": finding.last_seen_at,
            "first_seen_collection_run_id": finding.first_seen_collection_run_id,
            "last_seen_collection_run_id": finding.last_seen_collection_run_id,
            "archived_at": finding.archived_at,
        }
        for finding in findings
    ]
    return {
        "collection_run_id": target.id,
        "baseline_run_id": context.baseline.id if context.baseline else None,
        "comparable": context.comparable,
        "reason": context.reason,
        "discovery_type": discovery_type,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }
