from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.services.collector_types import CollectedFinding
from app.services.policies import RULES

EVIDENCE_SCHEMA_VERSION = 1

RULE_PARAMETER_KEYS: dict[str, tuple[str, ...]] = {
    "ebs_unattached": ("minimum_age_days", "minimum_monthly_savings_usd"),
    "eip_unassociated": ("monthly_cost_usd", "minimum_monthly_savings_usd"),
    "snapshot_retention": (
        "retention_days",
        "preserve_last_per_volume",
        "preserve_ami_snapshots",
        "minimum_monthly_savings_usd",
    ),
    "ec2_stopped_with_ebs": (
        "minimum_stopped_days",
        "include_unknown_stop_time",
        "minimum_monthly_savings_usd",
    ),
    "ec2_nonprod_outside_hours": (
        "timezone",
        "business_days",
        "business_hours_start",
        "business_hours_end",
        "environment_tag_keys",
        "nonproduction_values",
    ),
    "load_balancer_no_traffic": (
        "lookback_days",
        "minimum_age_days",
        "maximum_requests",
        "maximum_processed_bytes",
        "estimated_base_monthly_cost_usd",
    ),
    "rds_nonprod_idle": (
        "lookback_days",
        "maximum_average_cpu_percent",
        "maximum_connections",
        "environment_tag_keys",
        "nonproduction_values",
    ),
    "missing_required_tags": ("required_tags", "resource_types"),
    "cost_growth_anomaly": (
        "baseline_days",
        "comparison_days",
        "minimum_growth_percent",
        "minimum_delta_usd",
        "minimum_current_spend_usd",
    ),
}


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else round(float(value), 4)
    return None


def _money(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else round(float(number), 2)


def _metric(
    key: str,
    label: str,
    value: Any,
    unit: str | None = None,
    *,
    kind: str = "observed",
) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "kind": kind,
    }


def _criterion(
    key: str,
    label: str,
    observed_value: Any,
    operator: str,
    threshold_value: Any,
    unit: str | None = None,
) -> dict[str, Any] | None:
    if threshold_value is None:
        return None
    return {
        "key": key,
        "label": label,
        "observed_value": observed_value,
        "operator": operator,
        "threshold_value": threshold_value,
        "unit": unit,
    }


def _compact(items: list[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [item for item in items if item is not None]


def _rule_info(rule_key: str, policy: dict[str, Any] | None) -> dict[str, str]:
    definition = RULES.get(rule_key)
    return {
        "key": rule_key,
        "name": str((policy or {}).get("name") or (definition.name if definition else rule_key)),
        "description": str(
            (policy or {}).get("description")
            or (definition.description if definition else "Regra determinística do DeepOps.")
        ),
    }


def _policy_config(
    policy: dict[str, Any] | None,
    legacy_evidence: dict[str, Any],
) -> dict[str, Any]:
    if policy is not None:
        config = policy.get("config")
        return dict(config) if isinstance(config, dict) else {}
    config = legacy_evidence.get("policy_config")
    return dict(config) if isinstance(config, dict) else {}


def _parameters(rule_key: str, config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: config[key]
        for key in RULE_PARAMETER_KEYS.get(rule_key, ())
        if key in config
    }


def _environment_tags(
    tags: Any,
    config: dict[str, Any],
) -> dict[str, str]:
    if not isinstance(tags, dict):
        return {}
    wanted = {str(key).lower() for key in config.get("environment_tag_keys", [])}
    return {
        str(key): str(value)
        for key, value in tags.items()
        if str(key).lower() in wanted
    }


def _required_tag_evidence(
    current_tags: Any,
    required_tags: Any,
) -> dict[str, str]:
    if not isinstance(current_tags, dict) or not isinstance(required_tags, list):
        return {}
    current_by_lower = {
        str(key).lower(): (str(key), str(value))
        for key, value in current_tags.items()
    }
    result: dict[str, str] = {}
    for required in required_tags:
        item = current_by_lower.get(str(required).lower())
        if item:
            result[item[0]] = item[1]
    return result


def _base(
    *,
    rule_key: str,
    policy: dict[str, Any] | None,
    summary: str,
    metrics: list[dict[str, Any] | None],
    criteria: list[dict[str, Any] | None],
    details: dict[str, Any],
    parameters: dict[str, Any],
    source: str,
    notes: list[str] | None = None,
    contributors: list[dict[str, Any]] | None = None,
    evaluated_at: datetime | str | None = None,
) -> dict[str, Any]:
    if isinstance(evaluated_at, datetime):
        evaluated_at = evaluated_at.astimezone(UTC).isoformat()
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "summary": summary,
        "metrics": _compact(metrics),
        "criteria": _compact(criteria),
        "details": details,
        "parameters": parameters,
        "rule": _rule_info(rule_key, policy),
        "source": source,
        "notes": notes or [],
        "contributors": contributors or [],
        "evaluated_at": evaluated_at,
    }


def build_evidence(
    *,
    rule_key: str,
    service: str,
    region: str,
    resource_id: str,
    resource_name: str | None,
    title: str,
    description: str,
    raw_evidence: dict[str, Any] | None,
    current_monthly_cost: Decimal | float | int | str,
    estimated_monthly_savings: Decimal | float | int | str,
    policy: dict[str, Any] | None = None,
    evaluated_at: datetime | str | None = None,
) -> dict[str, Any]:
    raw = dict(raw_evidence or {})
    if raw.get("schema_version") == EVIDENCE_SCHEMA_VERSION and all(
        key in raw for key in ("summary", "metrics", "details", "rule")
    ):
        return raw

    config = _policy_config(policy, raw)
    parameters = _parameters(rule_key, config)
    current_cost = _money(current_monthly_cost)
    savings = _money(estimated_monthly_savings)
    details: dict[str, Any] = {
        "resource_id": resource_id,
        "resource_name": resource_name,
        "service": service,
        "region": region,
    }
    metrics: list[dict[str, Any] | None] = []
    criteria: list[dict[str, Any] | None] = []
    notes: list[str] = []
    contributors: list[dict[str, Any]] = []
    summary = description or title
    source = "AWS inventory"

    if rule_key == "ebs_unattached":
        state = raw.get("state")
        size = _number(raw.get("size_gib"))
        age = _number(raw.get("age_days"))
        volume_type = raw.get("volume_type")
        summary = "O volume EBS está disponível e sem anexação."
        if age is not None:
            summary += f" Ele existe há {age} dias; esse período é contado desde a criação."
        if current_cost is not None:
            summary += f" O custo mensal de armazenamento é estimado em US$ {current_cost:.2f}."
        metrics.extend(
            [
                _metric("age_days", "Idade desde a criação", age, "days"),
                _metric("storage_gib", "Armazenamento", size, "GiB"),
                _metric(
                    "estimated_monthly_cost",
                    "Custo mensal estimado",
                    current_cost,
                    "USD_MONTH",
                    kind="estimate",
                ),
            ]
        )
        criteria.extend(
            [
                _criterion(
                    "minimum_age_days",
                    "Idade mínima",
                    age,
                    ">=",
                    config.get("minimum_age_days"),
                    "days",
                ),
                _criterion(
                    "minimum_monthly_savings_usd",
                    "Economia mensal mínima",
                    savings,
                    ">=",
                    config.get("minimum_monthly_savings_usd"),
                    "USD_MONTH",
                ),
            ]
        )
        details.update(
            {
                "state": state,
                "volume_type": volume_type,
                "size_gib": size,
                "created_at": raw.get("created_at"),
            }
        )
        notes.append(
            "A idade disponível é a idade do volume desde a criação; "
            "o DeepOps não possui a data de desanexação."
        )

    elif rule_key == "eip_unassociated":
        summary = (
            "O endereço IPv4 público está alocado, mas não possui associação "
            "a instância ou interface de rede."
        )
        if current_cost is not None:
            summary += f" O custo mensal configurado é estimado em US$ {current_cost:.2f}."
        metrics.append(
            _metric(
                "estimated_monthly_cost",
                "Custo mensal estimado",
                current_cost,
                "USD_MONTH",
                kind="estimate",
            )
        )
        criteria.extend(
            [
                _criterion(
                    "association",
                    "Associação",
                    0,
                    "=",
                    0,
                    "associations",
                ),
                _criterion(
                    "minimum_monthly_savings_usd",
                    "Economia mensal mínima",
                    savings,
                    ">=",
                    config.get("minimum_monthly_savings_usd"),
                    "USD_MONTH",
                ),
            ]
        )
        details.update(
            {
                "public_ip": raw.get("public_ip"),
                "allocation_id": raw.get("allocation_id"),
                "domain": raw.get("domain"),
            }
        )
        notes.append(
            "O coletor atual não registra há quanto tempo o endereço permanece sem associação."
        )

    elif rule_key == "snapshot_retention":
        age = _number(raw.get("age_days"))
        retention = _number(raw.get("retention_days") or config.get("retention_days"))
        excess = age - retention if age is not None and retention is not None else None
        size = _number(raw.get("volume_size_gib"))
        summary = "O snapshot ultrapassou a retenção configurada."
        if age is not None and retention is not None:
            summary = (
                f"O snapshot tem {age} dias, {max(0, excess or 0)} dias acima da retenção "
                f"de {retention} dias."
            )
        metrics.extend(
            [
                _metric("age_days", "Idade do snapshot", age, "days"),
                _metric("retention_excess_days", "Excesso de retenção", excess, "days"),
                _metric("source_volume_gib", "Tamanho do volume de origem", size, "GiB"),
                _metric(
                    "estimated_monthly_cost_upper_bound",
                    "Custo mensal estimado (limite superior)",
                    current_cost,
                    "USD_MONTH",
                    kind="estimate",
                ),
            ]
        )
        criteria.append(
            _criterion("retention_days", "Retenção configurada", age, ">", retention, "days")
        )
        details.update(
            {
                "source_volume_id": raw.get("volume_id"),
                "started_at": raw.get("started_at"),
                "age_days": age,
                "retention_days": retention,
            }
        )
        notes.append(
            "O custo é um limite superior baseado no tamanho do volume de origem; "
            "snapshots EBS são incrementais."

        )

    elif rule_key == "ec2_stopped_with_ebs":
        stopped_days = _number(raw.get("stopped_days"))
        volumes = raw.get("volumes") if isinstance(raw.get("volumes"), list) else []
        total_gib = sum(
            float(item.get("size_gib") or 0)
            for item in volumes
            if isinstance(item, dict)
        )
        total_gib_value: int | float = (
            int(total_gib) if total_gib.is_integer() else round(total_gib, 2)
        )
        volume_count = len(volumes)
        if stopped_days is None:
            summary = (
                f"A instância está parada e mantém {volume_count} volume(s) EBS cobrados. "
                "A duração da parada não pôde ser confirmada pela evidência coletada."
            )
        else:
            summary = (
                f"A instância está parada há {stopped_days} dias e mantém {volume_count} "
                f"volume(s) EBS, totalizando {total_gib_value} GiB."
            )
        if current_cost is not None:
            summary += f" O armazenamento é estimado em US$ {current_cost:.2f}/mês."
        metrics.extend(
            [
                _metric("stopped_days", "Tempo parada", stopped_days, "days"),
                _metric("volume_count", "Volumes associados", volume_count, "volumes"),
                _metric("storage_gib", "Armazenamento associado", total_gib_value, "GiB"),
                _metric(
                    "estimated_monthly_storage_cost",
                    "Custo mensal estimado dos volumes",
                    current_cost,
                    "USD_MONTH",
                    kind="estimate",
                ),
            ]
        )
        criteria.extend(
            [
                _criterion(
                    "minimum_stopped_days",
                    "Tempo mínimo parada",
                    stopped_days,
                    ">=",
                    config.get("minimum_stopped_days"),
                    "days",
                ),
                _criterion(
                    "minimum_monthly_savings_usd",
                    "Economia mensal mínima",
                    savings,
                    ">=",
                    config.get("minimum_monthly_savings_usd"),
                    "USD_MONTH",
                ),
            ]
        )
        details.update(
            {
                "state": raw.get("state") or "stopped",
                "instance_type": raw.get("instance_type"),
                "stopped_at": raw.get("stopped_at"),
                "volumes": [
                    {
                        "volume_id": item.get("volume_id"),
                        "size_gib": item.get("size_gib"),
                        "type": item.get("type"),
                    }
                    for item in volumes
                    if isinstance(item, dict)
                ],
            }
        )
        if stopped_days is None:
            notes.append(
                "O StateTransitionReason não forneceu um horário de parada confiável; "
                "nenhum número de dias foi inferido."

            )

    elif rule_key == "ec2_nonprod_outside_hours":
        environment_tags = _environment_tags(raw.get("tags"), config)
        observed_at_value = raw.get("observed_at") or raw.get("evaluated_at") or evaluated_at
        summary = (
            "A instância não produtiva foi observada em execução fora da janela de expediente "
            "configurada."
        )
        metrics.extend(
            [
                _metric(
                    "estimated_monthly_running_cost",
                    "Custo mensal estimado se permanecer ligada",
                    current_cost,
                    "USD_MONTH",
                    kind="projection",
                ),
                _metric(
                    "estimated_monthly_offhours_savings",
                    "Economia potencial estimada",
                    savings,
                    "USD_MONTH",
                    kind="estimate",
                ),
            ]
        )
        observed_local_time = raw.get("observed_local_time")
        configured_window = (
            f"{config.get('business_hours_start', 'unknown')}–"
            f"{config.get('business_hours_end', 'unknown')} "
            f"({config.get('timezone', 'UTC')})"
        )
        criteria.append(
            _criterion(
                "business_hours",
                "Janela de expediente",
                observed_local_time,
                "outside",
                configured_window,
            )
        )
        details.update(
            {
                "state": raw.get("state") or "running",
                "instance_type": raw.get("instance_type"),
                "observed_at": observed_at_value,
                "observed_local_time": observed_local_time,
                "environment_tags": environment_tags,
            }
        )
        notes.append(
            "O achado representa o estado no instante da coleta; ele não prova quantas "
            "horas a instância permaneceu ligada fora do expediente."

        )

    elif rule_key == "load_balancer_no_traffic":
        source = "AWS inventory + Amazon CloudWatch"
        metric_name = str(raw.get("metric") or "traffic")
        total = _number(raw.get("metric_total"))
        datapoints = _number(raw.get("datapoint_count"))
        lookback = _number(raw.get("lookback_days") or config.get("lookback_days"))
        threshold = (
            config.get("maximum_processed_bytes")
            if metric_name == "ProcessedBytes"
            else config.get("maximum_requests")
        )
        unit = "bytes" if metric_name == "ProcessedBytes" else "requests"
        confirmed_total = None if datapoints == 0 else total
        if datapoints == 0:
            summary = (
                f"O CloudWatch não retornou amostras de {metric_name} no período analisado. "
                "O recurso foi sinalizado para validação, mas ausência de tráfego "
                "não está confirmada."

            )
        elif total == 0:
            summary = f"O CloudWatch registrou zero {unit} no período analisado de {lookback} dias."
        else:
            summary = (
                f"O CloudWatch registrou {total} {unit} em {lookback} dias, valor dentro do "
                f"limite configurado de {threshold}."
            )
        metrics.extend(
            [
                _metric("traffic_total", "Tráfego observado", confirmed_total, unit),
                _metric("datapoint_count", "Amostras retornadas", datapoints, "datapoints"),
                _metric("lookback_days", "Período analisado", lookback, "days"),
                _metric(
                    "estimated_monthly_cost",
                    "Custo mensal estimado",
                    current_cost,
                    "USD_MONTH",
                    kind="estimate",
                ),
            ]
        )
        criteria.append(
            _criterion(
                "traffic_threshold",
                "Limite de tráfego",
                confirmed_total,
                "<=",
                threshold,
                unit,
            )
        )
        details.update(
            {
                "load_balancer_type": raw.get("type"),
                "metric": metric_name,
                "created_at": raw.get("created_at"),
                "datapoint_count": datapoints,
            }
        )
        if datapoints == 0:
            notes.append(
                "Sem datapoints do CloudWatch, o DeepOps não trata tráfego zero "
                "como fato comprovado."

            )

    elif rule_key == "rds_nonprod_idle":
        source = "AWS inventory + Amazon CloudWatch"
        cpu = _number(raw.get("average_cpu_percent"))
        connections = _number(raw.get("maximum_connections"))
        lookback = _number(raw.get("lookback_days") or config.get("lookback_days"))
        environment_tags = _environment_tags(raw.get("tags"), config)
        summary = (
            f"O banco não produtivo apresentou CPU média de {cpu}% e máximo de "
            f"{connections} conexão(ões) no período de {lookback} dias."
            if cpu is not None and connections is not None
            else description
        )
        metrics.extend(
            [
                _metric("average_cpu_percent", "CPU média", cpu, "%"),
                _metric("maximum_connections", "Máximo de conexões", connections, "connections"),
                _metric("lookback_days", "Período analisado", lookback, "days"),
                _metric(
                    "estimated_monthly_cost",
                    "Custo mensal estimado",
                    current_cost,
                    "USD_MONTH",
                    kind="estimate",
                ),
            ]
        )
        criteria.extend(
            [
                _criterion(
                    "maximum_average_cpu_percent",
                    "Limite de CPU média",
                    cpu,
                    "<=",
                    config.get("maximum_average_cpu_percent"),
                    "%",
                ),
                _criterion(
                    "maximum_connections",
                    "Limite de conexões",
                    connections,
                    "<=",
                    config.get("maximum_connections"),
                    "connections",
                ),
            ]
        )
        details.update(
            {
                "engine": raw.get("engine"),
                "instance_class": raw.get("instance_class"),
                "environment_tags": environment_tags,
                "cpu_datapoint_count": raw.get("cpu_datapoint_count"),
                "connection_datapoint_count": raw.get("connection_datapoint_count"),
            }
        )
        notes.append(
            "O analyzer atual não coleta I/O para esta regra; nenhum valor de I/O é inferido."
        )

    elif rule_key == "missing_required_tags":
        missing = raw.get("missing_tags") if isinstance(raw.get("missing_tags"), list) else []
        required = (
            config.get("required_tags")
            if isinstance(config.get("required_tags"), list)
            else []
        )
        current = raw.get("current_tags") or raw.get("tags")
        found = _required_tag_evidence(current, required)
        summary = (
            f"O recurso não possui {len(missing)} tag(s) obrigatória(s): "
            + ", ".join(str(item) for item in missing)
            + "."
            if missing
            else description
        )
        metrics.append(
            _metric(
                "missing_tag_count",
                "Tags obrigatórias ausentes",
                len(missing),
                "tags",
            )
        )
        details.update(
            {
                "required_tags": required,
                "required_tags_found": found,
                "missing_tags": missing,
            }
        )
        criteria.append(
            _criterion(
                "required_tags",
                "Tags obrigatórias presentes",
                len(required) - len(missing),
                "=",
                len(required),
                "tags",
            )
        )
        notes.append(
            "Somente tags relevantes para a política são preservadas na evidência estruturada."
        )

    elif rule_key == "cost_growth_anomaly":
        source = "AWS Cost Explorer · UnblendedCost"
        baseline = _money(raw.get("baseline_equivalent_usd"))
        current = _money(raw.get("current_spend_usd"))
        delta = _money(raw.get("delta_usd"))
        growth = _number(raw.get("growth_percent"))
        baseline_days = _number(raw.get("baseline_period_days") or config.get("baseline_days"))
        comparison_days = _number(
            raw.get("comparison_period_days") or config.get("comparison_days")
        )
        if baseline is not None and current is not None and delta is not None:
            growth_text = f" ({growth:.1f}%)" if isinstance(growth, (int, float)) else ""
            summary = (
                f"O custo de {service} em {region} aumentou de US$ {baseline:.2f} esperados "
                f"para US$ {current:.2f} no período atual, variação de "
                f"+US$ {delta:.2f}{growth_text}."

            )
        metrics.extend(
            [
                _metric("previous_period_cost", "Custo esperado no período", baseline, "USD"),
                _metric("current_period_cost", "Custo no período atual", current, "USD"),
                _metric("absolute_cost_change", "Variação absoluta", delta, "USD"),
                _metric("cost_growth_percent", "Variação percentual", growth, "%"),
                _metric("baseline_period_days", "Período de referência", baseline_days, "days"),
                _metric("comparison_period_days", "Período atual", comparison_days, "days"),
            ]
        )
        criteria.extend(
            [
                _criterion(
                    "minimum_growth_percent",
                    "Crescimento mínimo",
                    growth,
                    ">=",
                    raw.get("minimum_growth_percent", config.get("minimum_growth_percent")),
                    "%",
                ),
                _criterion(
                    "minimum_delta_usd",
                    "Variação mínima",
                    delta,
                    ">=",
                    raw.get("minimum_delta_usd", config.get("minimum_delta_usd")),
                    "USD",
                ),
                _criterion(
                    "minimum_current_spend_usd",
                    "Custo atual mínimo",
                    current,
                    ">=",
                    raw.get("minimum_current_spend_usd", config.get("minimum_current_spend_usd")),
                    "USD",
                ),
            ]
        )
        details.update(
            {
                "baseline_start": raw.get("baseline_start"),
                "baseline_end_exclusive": raw.get("baseline_end_exclusive"),
                "comparison_start": raw.get("comparison_start"),
                "comparison_end_exclusive": raw.get("comparison_end_exclusive"),
                "baseline_total_usd": _money(raw.get("baseline_total_usd")),
                "metric": raw.get("metric") or "UnblendedCost",
                "estimated": bool(raw.get("estimated")),
                "breakdown_status": raw.get("breakdown_status"),
            }
        )
        if isinstance(raw.get("cost_contributors"), list):
            for item in raw["cost_contributors"][:5]:
                if not isinstance(item, dict):
                    continue
                usage_type = item.get("usage_type")
                contribution = _money(item.get("delta_usd"))
                if usage_type is None or contribution is None:
                    continue
                contributors.append(
                    {
                        "key": str(usage_type),
                        "label": str(usage_type),
                        "previous_value": _money(item.get("baseline_equivalent_usd")),
                        "current_value": _money(item.get("current_spend_usd")),
                        "delta": contribution,
                        "unit": "USD",
                    }
                )
        notes.append(
            "O custo esperado é normalizado para o mesmo número de dias do período atual. "
            "Crescimento de custo não equivale automaticamente a desperdício."

        )
        if raw.get("estimated") is True or raw.get("breakdown_estimated") is True:
            notes.append("A AWS marcou parte dos dados de custo como estimada.")
        if raw.get("breakdown_status") == "unavailable":
            notes.append(
                "O detalhamento opcional por tipo de uso não pôde ser consultado nesta coleta."
            )

    else:
        # Compatibility path for an analyzer that has not adopted the Stage 6 contract yet.
        safe_details = {
            key: value
            for key, value in raw.items()
            if key not in {"policy_config", "tags", "user_data", "credentials", "token", "secret"}
        }
        details.update(safe_details)
        notes.append(
            "Este analyzer ainda não possui um mapeamento especializado de explicabilidade; "
            "apenas evidências persistidas são exibidas."

        )

    return _base(
        rule_key=rule_key,
        policy=policy,
        summary=summary,
        metrics=metrics,
        criteria=criteria,
        details=details,
        parameters=parameters,
        source=source,
        notes=notes,
        contributors=contributors,
        evaluated_at=raw.get("evaluated_at") or evaluated_at,
    )


def build_collected_finding_evidence(
    finding: CollectedFinding,
    policy: dict[str, Any],
    *,
    evaluated_at: datetime,
) -> dict[str, Any]:
    return build_evidence(
        rule_key=finding.rule_key,
        service=finding.service,
        region=finding.region,
        resource_id=finding.resource_id,
        resource_name=finding.resource_name,
        title=finding.title,
        description=finding.description,
        raw_evidence=finding.evidence,
        current_monthly_cost=finding.current_monthly_cost,
        estimated_monthly_savings=finding.estimated_monthly_savings,
        policy=policy,
        evaluated_at=evaluated_at,
    )


def normalize_persisted_evidence(
    *,
    rule_key: str,
    service: str,
    region: str,
    resource_id: str,
    resource_name: str | None,
    title: str,
    description: str,
    evidence: dict[str, Any] | None,
    current_monthly_cost: Decimal | float | int | str,
    estimated_monthly_savings: Decimal | float | int | str,
) -> dict[str, Any]:
    return build_evidence(
        rule_key=rule_key,
        service=service,
        region=region,
        resource_id=resource_id,
        resource_name=resource_name,
        title=title,
        description=description,
        raw_evidence=evidence,
        current_monthly_cost=current_monthly_cost,
        estimated_monthly_savings=estimated_monthly_savings,
    )
