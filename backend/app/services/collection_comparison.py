from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import ceil
from types import SimpleNamespace
from typing import Any, Literal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased

from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.opportunity_evidence import normalize_persisted_evidence

ComparisonCategory = Literal["NEW", "PERSISTENT", "NO_LONGER_DETECTED", "CHANGED"]

NATURAL_EVOLUTION_METRICS = {
    "age_days",
    "retention_excess_days",
    "stopped_days",
    "lookback_days",
    "datapoint_count",
    "baseline_period_days",
    "comparison_period_days",
}

RELEVANT_DETAIL_KEYS: dict[str, tuple[str, ...]] = {
    "ebs_unattached": ("state", "volume_type"),
    "eip_unassociated": (),
    "snapshot_retention": (),
    "ec2_stopped_with_ebs": ("state", "instance_type", "volumes"),
    "ec2_nonprod_outside_hours": ("state", "instance_type", "environment_tags"),
    "load_balancer_no_traffic": ("load_balancer_type", "metric"),
    "rds_nonprod_idle": ("engine", "instance_class", "environment_tags"),
    "missing_required_tags": ("missing_tags", "required_tags_found"),
    "cost_growth_anomaly": ("metric", "estimated", "breakdown_status"),
}


class CollectionComparisonError(ValueError):
    def __init__(self, message: str, *, code: str = "INVALID_COMPARISON"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ObservationContext:
    finding: Finding
    observation: OpportunityObservation


def _page_meta(total: int, page: int, page_size: int) -> dict[str, int]:
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": ceil(total / page_size) if total else 0,
    }


def _semantic_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return {
            str(key): _semantic_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        normalized = [_semantic_value(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, default=str),
        )
    return str(value)


def _same(left: Any, right: Any) -> bool:
    return _semantic_value(left) == _semantic_value(right)


def _evidence(context: ObservationContext) -> dict[str, Any]:
    finding = context.finding
    observation = context.observation
    return normalize_persisted_evidence(
        rule_key=finding.rule_key,
        service=finding.service,
        region=finding.region,
        resource_id=finding.resource_id,
        resource_name=finding.resource_name,
        title=finding.title,
        description=finding.description,
        evidence=observation.evidence,
        current_monthly_cost=observation.current_monthly_cost,
        estimated_monthly_savings=observation.estimated_monthly_savings,
        provider=finding.provider,
    )


def _change(
    changes: list[dict[str, Any]],
    change_types: set[str],
    *,
    change_type: str,
    label: str,
    baseline: Any,
    target: Any,
    unit: str | None = None,
) -> None:
    changes.append(
        {
            "type": change_type,
            "label": label,
            "baseline": baseline,
            "target": target,
            "unit": unit,
        }
    )
    change_types.add(change_type)


def _metric_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for metric in evidence.get("metrics", []):
        if not isinstance(metric, dict) or not metric.get("key"):
            continue
        key = str(metric["key"])
        if key in NATURAL_EVOLUTION_METRICS:
            continue
        if metric.get("unit") == "USD_MONTH":
            continue
        result[key] = {
            "label": metric.get("label") or key,
            "value": metric.get("value"),
            "unit": metric.get("unit"),
            "kind": metric.get("kind"),
        }
    return result


def _criterion_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for criterion in evidence.get("criteria", []):
        if not isinstance(criterion, dict) or not criterion.get("key"):
            continue
        key = str(criterion["key"])
        result[key] = {
            "label": criterion.get("label") or key,
            "operator": criterion.get("operator"),
            "threshold_value": criterion.get("threshold_value"),
            "unit": criterion.get("unit"),
        }
    return result


def _contributor_map(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for contributor in evidence.get("contributors", []):
        if not isinstance(contributor, dict) or not contributor.get("key"):
            continue
        key = str(contributor["key"])
        result[key] = {
            "label": contributor.get("label") or key,
            "previous_value": contributor.get("previous_value"),
            "current_value": contributor.get("current_value"),
            "delta": contributor.get("delta"),
            "unit": contributor.get("unit"),
        }
    return result


def compare_observations(
    baseline: ObservationContext,
    target: ObservationContext,
) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    change_types: set[str] = set()
    before = baseline.observation
    after = target.observation

    if before.severity != after.severity:
        _change(
            changes,
            change_types,
            change_type="severity",
            label="Severidade",
            baseline=before.severity,
            target=after.severity,
        )

    if before.confidence != after.confidence:
        _change(
            changes,
            change_types,
            change_type="confidence",
            label="Confiança",
            baseline=before.confidence,
            target=after.confidence,
        )

    if before.currency != after.currency:
        _change(
            changes,
            change_types,
            change_type="currency",
            label="Moeda",
            baseline=before.currency,
            target=after.currency,
        )
    else:
        money_unit = f"{after.currency}_MONTH"
        if before.current_monthly_cost != after.current_monthly_cost:
            _change(
                changes,
                change_types,
                change_type="financial_impact",
                label="Custo mensal observado",
                baseline=before.current_monthly_cost,
                target=after.current_monthly_cost,
                unit=money_unit,
            )

        if before.estimated_monthly_savings != after.estimated_monthly_savings:
            _change(
                changes,
                change_types,
                change_type="financial_impact",
                label="Economia potencial estimada",
                baseline=before.estimated_monthly_savings,
                target=after.estimated_monthly_savings,
                unit=money_unit,
            )

    if before.evidence == after.evidence:
        return {"changed": bool(changes), "change_types": sorted(change_types), "changes": changes}

    baseline_evidence = _evidence(baseline)
    target_evidence = _evidence(target)

    before_metrics = _metric_map(baseline_evidence)
    after_metrics = _metric_map(target_evidence)
    for key in sorted(set(before_metrics) | set(after_metrics)):
        old = before_metrics.get(key)
        new = after_metrics.get(key)
        if not _same(old, new):
            _change(
                changes,
                change_types,
                change_type="evidence",
                label=(new or old or {}).get("label", key),
                baseline=old["value"] if old else None,
                target=new["value"] if new else None,
                unit=(new or old or {}).get("unit"),
            )

    before_criteria = _criterion_map(baseline_evidence)
    after_criteria = _criterion_map(target_evidence)
    for key in sorted(set(before_criteria) | set(after_criteria)):
        old = before_criteria.get(key)
        new = after_criteria.get(key)
        old_semantic = (
            {
                "operator": old.get("operator"),
                "threshold_value": old.get("threshold_value"),
                "unit": old.get("unit"),
            }
            if old
            else None
        )
        new_semantic = (
            {
                "operator": new.get("operator"),
                "threshold_value": new.get("threshold_value"),
                "unit": new.get("unit"),
            }
            if new
            else None
        )
        if not _same(old_semantic, new_semantic):
            _change(
                changes,
                change_types,
                change_type="threshold",
                label=(new or old or {}).get("label", key),
                baseline=old_semantic,
                target=new_semantic,
                unit=(new or old or {}).get("unit"),
            )

    before_parameters = baseline_evidence.get("parameters", {})
    after_parameters = target_evidence.get("parameters", {})
    if not _same(before_parameters, after_parameters):
        _change(
            changes,
            change_types,
            change_type="parameters",
            label="Parâmetros relevantes da regra",
            baseline=before_parameters,
            target=after_parameters,
        )

    before_contributors = _contributor_map(baseline_evidence)
    after_contributors = _contributor_map(target_evidence)
    if not _same(before_contributors, after_contributors):
        _change(
            changes,
            change_types,
            change_type="evidence",
            label="Contribuidores da análise",
            baseline=before_contributors,
            target=after_contributors,
        )

    detail_keys = RELEVANT_DETAIL_KEYS.get(target.finding.rule_key, ())
    before_details = baseline_evidence.get("details", {})
    after_details = target_evidence.get("details", {})
    for key in detail_keys:
        old = before_details.get(key)
        new = after_details.get(key)
        if not _same(old, new):
            _change(
                changes,
                change_types,
                change_type="evidence",
                label=key.replace("_", " ").capitalize(),
                baseline=old,
                target=new,
            )

    return {
        "changed": bool(changes),
        "change_types": sorted(change_types),
        "changes": changes,
    }


def _validate_run(run: CollectionRun, *, role: str) -> None:
    if run.status != CollectionRunStatus.SUCCESS:
        raise CollectionComparisonError(
            f"A coleta {role} não foi concluída com sucesso.",
            code="COLLECTION_NOT_SUCCESSFUL",
        )


def validate_comparable_runs(baseline: CollectionRun, target: CollectionRun) -> None:
    _validate_run(baseline, role="baseline")
    _validate_run(target, role="target")
    if baseline.id == target.id:
        raise CollectionComparisonError(
            "Selecione duas coletas diferentes.",
            code="SAME_COLLECTION",
        )
    if baseline.provider.lower() != target.provider.lower():
        raise CollectionComparisonError(
            "As coletas pertencem a providers diferentes.",
            code="DIFFERENT_PROVIDER",
        )
    if baseline.account_id != target.account_id:
        raise CollectionComparisonError(
            "As coletas pertencem a contas diferentes.",
            code="DIFFERENT_ACCOUNT",
        )
    if baseline.scope and target.scope and not _same(baseline.scope, target.scope):
        raise CollectionComparisonError(
            "As coletas possuem escopos conhecidos diferentes.",
            code="DIFFERENT_SCOPE",
        )
    if baseline.started_at >= target.started_at:
        raise CollectionComparisonError(
            "A baseline precisa ser anterior à coleta atual.",
            code="BASELINE_NOT_EARLIER",
        )


def compatible_baselines(
    db: Session,
    target: CollectionRun,
    *,
    limit: int = 100,
) -> list[CollectionRun]:
    _validate_run(target, role="target")
    statement = (
        select(CollectionRun)
        .where(
            CollectionRun.id != target.id,
            CollectionRun.status == CollectionRunStatus.SUCCESS,
            CollectionRun.provider == target.provider,
            CollectionRun.account_id == target.account_id,
            CollectionRun.started_at < target.started_at,
        )
        .order_by(CollectionRun.started_at.desc(), CollectionRun.id.desc())
    )
    compatible: list[CollectionRun] = []
    for candidate in db.scalars(statement.execution_options(yield_per=100)):
        if target.scope and candidate.scope and not _same(candidate.scope, target.scope):
            continue
        compatible.append(candidate)
        if len(compatible) >= limit:
            break
    return compatible


def previous_comparable_run(db: Session, target: CollectionRun) -> CollectionRun | None:
    runs = compatible_baselines(db, target, limit=1)
    return runs[0] if runs else None


def _run_metadata(run: CollectionRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "provider": run.provider,
        "account_id": run.account_id,
        "scope": run.scope or {},
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "rules_version": run.analyzer_version,
    }


def _rules_warning(
    baseline: CollectionRun,
    target: CollectionRun,
) -> dict[str, str] | None:
    if baseline.analyzer_version and target.analyzer_version:
        if baseline.analyzer_version == target.analyzer_version:
            return None
        return {
            "code": "RULES_VERSION_CHANGED",
            "message": (
                "As duas coletas utilizaram versões diferentes das regras/analyzers. "
                f"Anterior: {baseline.analyzer_version}. Atual: {target.analyzer_version}. "
                "A classificação continua baseada nas observations e a mudança de versão "
                "pode explicar parte das diferenças."
            ),
        }
    return {
        "code": "RULES_VERSION_UNAVAILABLE",
        "message": (
            "Uma ou ambas as coletas não registraram analyzer_version. "
            "A comparação continua baseada nas observations, mas não é possível confirmar "
            "se o conjunto de regras permaneceu idêntico."
        ),
    }


def _scope_warning(
    baseline: CollectionRun | None,
    target: CollectionRun,
) -> dict[str, str] | None:
    if baseline is not None and baseline.scope and target.scope:
        return None
    return {
        "code": "SCOPE_METADATA_UNAVAILABLE",
        "message": (
            "Uma ou ambas as coletas não possuem snapshot histórico de escopo. "
            "A comparabilidade foi validada por provider e conta; mudanças antigas "
            "de configuração podem afetar o resultado."
        ),
    }


# Explicit projections exclude Finding.evidence, provider metadata and decision notes.
_FINDING_FIELDS = (
    "id",
    "fingerprint",
    "title",
    "description",
    "rule_key",
    "service",
    "region",
    "provider",
    "resource_id",
    "resource_name",
    "resource_type",
    "status",
    "first_seen_at",
)
_OBSERVATION_FIELDS = (
    "observed_at",
    "severity",
    "current_monthly_cost",
    "estimated_monthly_savings",
    "confidence",
    "currency",
    "evidence",
)


def _projection(model, fields, prefix):
    return [getattr(model, field).label(prefix + field) for field in fields]


def _context(row, prefix):
    return ObservationContext(
        finding=SimpleNamespace(**{key: row["finding_" + key] for key in _FINDING_FIELDS}),
        observation=SimpleNamespace(**{key: row[prefix + key] for key in _OBSERVATION_FIELDS}),
    )


def _comparison_query(baseline_id, target_id, *, shared, category=None):
    before = aliased(OpportunityObservation)
    after = aliased(OpportunityObservation)
    if shared:
        return (
            select(
                *_projection(Finding, _FINDING_FIELDS, "finding_"),
                *_projection(before, _OBSERVATION_FIELDS, "before_"),
                *_projection(after, _OBSERVATION_FIELDS, "after_"),
            )
            .select_from(before)
            .join(
                after,
                and_(
                    after.opportunity_id == before.opportunity_id,
                    after.collection_run_id == target_id,
                ),
            )
            .join(Finding, Finding.id == before.opportunity_id)
            .where(before.collection_run_id == baseline_id)
            .order_by(Finding.id)
        )
    run_id, other_id = (target_id, baseline_id) if category == "NEW" else (baseline_id, target_id)
    return (
        select(
            *_projection(Finding, _FINDING_FIELDS, "finding_"),
            *_projection(before, _OBSERVATION_FIELDS, "observation_"),
        )
        .select_from(before)
        .join(Finding, Finding.id == before.opportunity_id)
        .where(
            before.collection_run_id == run_id,
            ~select(after.id)
            .where(
                after.collection_run_id == other_id, after.opportunity_id == before.opportunity_id
            )
            .exists(),
        )
        .order_by(Finding.id)
    )


def _snapshot(context: ObservationContext | None) -> dict[str, Any] | None:
    if context is None:
        return None
    observation = context.observation
    evidence = _evidence(context)
    return {
        "observed_at": observation.observed_at,
        "severity": observation.severity,
        "current_monthly_cost": observation.current_monthly_cost,
        "estimated_monthly_savings": observation.estimated_monthly_savings,
        "confidence": observation.confidence,
        "currency": observation.currency,
        "evidence_summary": evidence.get("summary"),
    }


def _item(
    category: ComparisonCategory,
    baseline: ObservationContext | None,
    target: ObservationContext | None,
    diff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = target or baseline
    if context is None:
        raise RuntimeError("Comparison item requires at least one observation")
    finding = context.finding
    diff = diff or {"change_types": [], "changes": []}
    return {
        "category": category,
        "opportunity_id": finding.id,
        "fingerprint": finding.fingerprint,
        "title": finding.title,
        "rule_key": finding.rule_key,
        "service": finding.service,
        "region": finding.region,
        "resource_id": finding.resource_id,
        "resource_name": finding.resource_name,
        "resource_type": finding.resource_type,
        "lifecycle_status": finding.status,
        "first_seen_at": finding.first_seen_at,
        "baseline": _snapshot(baseline),
        "target": _snapshot(target),
        "change_types": diff["change_types"],
        "changes": diff["changes"],
    }


def _financial_summary(rows, baseline_id, target_id):
    currencies = {row.currency for row in rows if row.currency}
    if len(currencies) > 1:
        return None, {
            "code": "MULTIPLE_CURRENCIES",
            "message": (
                "A comparação contém mais de uma moeda. O DeepOps não soma valores "
                "de moedas diferentes sem conversão explícita."
            ),
        }
    currency = next(iter(currencies), "USD")
    baseline_total = sum(
        (row.amount for row in rows if row.collection_run_id == baseline_id), Decimal("0")
    )
    target_total = sum(
        (row.amount for row in rows if row.collection_run_id == target_id), Decimal("0")
    )
    if baseline_total == 0 and target_total == 0:
        return None, None
    delta = target_total - baseline_total
    delta_percent = (
        (delta / baseline_total * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        if baseline_total != 0
        else None
    )
    return {
        "metric": "estimated_monthly_savings",
        "label": "Economia potencial estimada",
        "currency": currency,
        "period": "month",
        "baseline_total": baseline_total,
        "target_total": target_total,
        "delta": delta,
        "delta_percent": delta_percent,
    }, None


def compare_collection_runs(
    db: Session,
    target: CollectionRun,
    *,
    baseline: CollectionRun | None,
    category: ComparisonCategory,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    _validate_run(target, role="target")
    if baseline is None:
        baseline = previous_comparable_run(db, target)
    if baseline is None:
        return {
            "available": False,
            "reason": "NO_BASELINE",
            "message": (
                "Esta é a primeira coleta bem-sucedida disponível para este provider e conta. "
                "Não existe uma coleta anterior para comparação."
            ),
            "baseline": None,
            "target": _run_metadata(target),
            "summary": None,
            "financial_summary": None,
            "rules_version_warning": None,
            "warnings": [warning for warning in [_scope_warning(None, target)] if warning],
            "category": category,
            "items": [],
            **_page_meta(0, page, page_size),
        }

    validate_comparable_runs(baseline, target)

    # Counts and money are reduced by the database; at most one row per run/currency.
    totals = db.execute(
        select(
            OpportunityObservation.collection_run_id,
            OpportunityObservation.currency,
            func.count().label("count"),
            func.sum(OpportunityObservation.estimated_monthly_savings).label("amount"),
        )
        .join(Finding, Finding.id == OpportunityObservation.opportunity_id)
        .where(OpportunityObservation.collection_run_id.in_([baseline.id, target.id]))
        .group_by(OpportunityObservation.collection_run_id, OpportunityObservation.currency)
    ).all()
    baseline_total = sum(row.count for row in totals if row.collection_run_id == baseline.id)
    target_total = sum(row.count for row in totals if row.collection_run_id == target.id)
    shared_total = changed_total = selected_total = 0
    items = []
    start = (page - 1) * page_size
    # Semantic evidence comparison cannot be replaced by raw JSON equality. Stream only
    # the SQL intersection, retaining the requested page rather than every ID and diff.
    rows = db.execute(
        _comparison_query(baseline.id, target.id, shared=True).execution_options(yield_per=200)
    ).mappings()
    try:
        for row in rows:
            before, after = _context(row, "before_"), _context(row, "after_")
            diff = compare_observations(before, after)
            shared_total += 1
            changed_total += int(diff["changed"])
            row_category = "CHANGED" if diff["changed"] else "PERSISTENT"
            if category == row_category:
                if start <= selected_total < start + page_size:
                    items.append(_item(category, before, after, diff))
                selected_total += 1
    finally:
        rows.close()

    counts = {
        "NEW": target_total - shared_total,
        "NO_LONGER_DETECTED": baseline_total - shared_total,
        "PERSISTENT": shared_total - changed_total,
        "CHANGED": changed_total,
    }
    if category in {"NEW", "NO_LONGER_DETECTED"}:
        rows = db.execute(
            _comparison_query(baseline.id, target.id, shared=False, category=category)
            .offset(start)
            .limit(page_size)
        ).mappings()
        for row in rows:
            context = _context(row, "observation_")
            items.append(
                _item(
                    category,
                    context if category == "NO_LONGER_DETECTED" else None,
                    context if category == "NEW" else None,
                )
            )

    financial_summary, currency_warning = _financial_summary(totals, baseline.id, target.id)
    warnings = [
        warning
        for warning in [
            _scope_warning(baseline, target),
            currency_warning,
        ]
        if warning
    ]

    return {
        "available": True,
        "reason": None,
        "message": None,
        "baseline": _run_metadata(baseline),
        "target": _run_metadata(target),
        "summary": {
            "baseline_total": baseline_total,
            "target_total": target_total,
            "new": counts["NEW"],
            "persistent": counts["PERSISTENT"],
            "no_longer_detected": counts["NO_LONGER_DETECTED"],
            "changed": counts["CHANGED"],
        },
        "financial_summary": financial_summary,
        "rules_version_warning": _rules_warning(baseline, target),
        "warnings": warnings,
        "category": category,
        "items": items,
        **_page_meta(counts[category], page, page_size),
    }
