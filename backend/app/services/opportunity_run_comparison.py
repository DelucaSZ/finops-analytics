from __future__ import annotations

import base64
import json
import zlib
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

_COMPARISON_CONTEXT_VERSION = 1
_MAX_CONTEXT_LENGTH = 8192
_MAX_CONTEXT_TARGETS = 500


class ComparisonContextError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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


@dataclass(frozen=True)
class DashboardComparisonSnapshot:
    contexts: tuple[OpportunityRunContext, ...]
    comparable_accounts: int
    accounts_without_baseline: int
    rules_version_changed: bool
    rules_version_unknown: bool
    partial_coverage: bool
    comparison_context: str | None


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


def comparison_condition(
    contexts: tuple[OpportunityRunContext, ...],
    discovery_type: DiscoveryType,
):
    conditions = [
        condition
        for context in contexts
        if (condition := _classification_condition(context, discovery_type)) is not None
    ]
    if not conditions:
        return None
    return or_(*conditions)


def _count(db: Session, condition, *, operational_only: bool = False) -> int:
    if condition is None:
        return 0
    statement = select(func.count()).select_from(Finding).where(condition)
    if operational_only:
        statement = statement.where(Finding.status != "rejected", Finding.archived_at.is_(None))
    return int(db.scalar(statement) or 0)


def _latest_success_targets(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> tuple[CollectionRun, ...]:
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
    ranked_cte = ranked.cte("dashboard_comparison_success_ranked")
    return tuple(
        db.scalars(
            select(CollectionRun)
            .join(ranked_cte, CollectionRun.id == ranked_cte.c.run_id)
            .where(ranked_cte.c.run_rank == 1)
            .order_by(CollectionRun.provider, CollectionRun.account_id)
        )
    )


def _encode_target_ids(target_ids: tuple[str, ...]) -> str | None:
    if not target_ids:
        return None
    payload = json.dumps(
        {"v": _COMPARISON_CONTEXT_VERSION, "targets": list(target_ids)},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    token = base64.urlsafe_b64encode(zlib.compress(payload, level=9)).decode("ascii").rstrip("=")
    if len(token) > _MAX_CONTEXT_LENGTH:
        raise ComparisonContextError(
            "CONTEXT_TOO_LARGE",
            "O contexto da comparação excedeu o limite seguro para uma URL compartilhável.",
        )
    return token


def decode_comparison_context(token: str) -> tuple[str, ...]:
    if not token or len(token) > _MAX_CONTEXT_LENGTH:
        raise ComparisonContextError("INVALID_CONTEXT", "Contexto de comparação inválido.")
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(zlib.decompress(base64.urlsafe_b64decode(padded)).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error) as exc:
        raise ComparisonContextError("INVALID_CONTEXT", "Contexto de comparação inválido.") from exc
    if payload.get("v") != _COMPARISON_CONTEXT_VERSION:
        raise ComparisonContextError("INVALID_CONTEXT_VERSION", "Versão de contexto não suportada.")
    target_ids = payload.get("targets")
    if not isinstance(target_ids, list) or not target_ids or len(target_ids) > _MAX_CONTEXT_TARGETS:
        raise ComparisonContextError("INVALID_CONTEXT", "Contexto de comparação inválido.")
    normalized: list[str] = []
    for value in target_ids:
        if not isinstance(value, str) or not value or len(value) > 64:
            raise ComparisonContextError("INVALID_CONTEXT", "Contexto de comparação inválido.")
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def resolve_comparison_context(
    db: Session,
    token: str,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> tuple[OpportunityRunContext, ...]:
    target_ids = decode_comparison_context(token)
    targets = {
        run.id: run
        for run in db.scalars(select(CollectionRun).where(CollectionRun.id.in_(target_ids)))
    }
    if len(targets) != len(target_ids):
        raise ComparisonContextError("INVALID_CONTEXT", "Uma ou mais coletas do contexto não existem.")

    contexts: list[OpportunityRunContext] = []
    for target_id in target_ids:
        target = targets[target_id]
        if provider and target.provider != provider.lower():
            raise ComparisonContextError("SCOPE_MISMATCH", "O contexto não pertence ao provider informado.")
        if account_id and target.account_id != account_id:
            raise ComparisonContextError("SCOPE_MISMATCH", "O contexto não pertence à conta informada.")
        context = resolve_run_context(db, target)
        if context.reason in {"TARGET_OBSERVATIONS_EXPIRED", "BASELINE_OBSERVATIONS_EXPIRED"}:
            raise ComparisonContextError(
                "CONTEXT_EXPIRED",
                "Os detalhes desta comparação não estão mais disponíveis devido à política de retenção.",
            )
        if not context.comparable or context.baseline is None:
            raise ComparisonContextError(
                "CONTEXT_UNAVAILABLE",
                "A comparação registrada neste link não está mais disponível.",
            )
        contexts.append(context)
    return tuple(contexts)


def dashboard_comparison_snapshot(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> DashboardComparisonSnapshot:
    targets = _latest_success_targets(db, provider=provider, account_id=account_id)
    contexts: list[OpportunityRunContext] = []
    accounts_without_baseline = 0
    rules_version_unknown = False
    partial_coverage = False
    for target in targets:
        context = resolve_run_context(db, target)
        partial_coverage = partial_coverage or context.partial_coverage
        if context.comparable and context.baseline is not None:
            contexts.append(context)
            rules_version_unknown = rules_version_unknown or context.rules_version_changed is None
        else:
            accounts_without_baseline += 1

    frozen_contexts = tuple(contexts)
    return DashboardComparisonSnapshot(
        contexts=frozen_contexts,
        comparable_accounts=len(frozen_contexts),
        accounts_without_baseline=accounts_without_baseline,
        rules_version_changed=any(context.rules_version_changed is True for context in frozen_contexts),
        rules_version_unknown=rules_version_unknown,
        partial_coverage=partial_coverage,
        comparison_context=_encode_target_ids(tuple(context.target.id for context in frozen_contexts)),
    )


def dashboard_new_since_previous(
    db: Session,
    *,
    provider: str | None = None,
    account_id: str | None = None,
) -> dict:
    snapshot = dashboard_comparison_snapshot(db, provider=provider, account_id=account_id)
    new_condition = comparison_condition(snapshot.contexts, "new_vs_previous")
    first_seen_condition = comparison_condition(snapshot.contexts, "first_seen")
    reappeared_condition = comparison_condition(snapshot.contexts, "reappeared")
    return {
        "count": _count(db, new_condition, operational_only=True),
        "first_seen_count": _count(db, first_seen_condition, operational_only=True),
        "reappeared_count": _count(db, reappeared_condition, operational_only=True),
        "comparable_accounts": snapshot.comparable_accounts,
        "accounts_without_baseline": snapshot.accounts_without_baseline,
        "rules_version_changed": snapshot.rules_version_changed,
        "rules_version_unknown": snapshot.rules_version_unknown,
        "partial_coverage": snapshot.partial_coverage,
        "comparison_context": snapshot.comparison_context,
    }


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
