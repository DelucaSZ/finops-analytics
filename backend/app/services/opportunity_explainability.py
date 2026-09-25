from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.services.collector_types import CollectedFinding
from app.services.policies import RULES

EVIDENCE_SCHEMA_VERSION = 1


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return value
    return None


def _money(value: Decimal | float | int | str) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def _metric(
    key: str,
    label: str,
    value: Any,
    *,
    unit: str | None = None,
    currency: str | None = None,
    kind: str = "observed",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "currency": currency,
        "kind": kind,
    }


def _criterion(
    key: str,
    label: str,
    value: Any,
    *,
    operator: str | None = None,
    unit: str | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "operator": operator,
        "value": value,
        "unit": unit,
        "currency": currency,
    }


def _estimated_cost(finding: CollectedFinding) -> dict[str, Any]:
    return _metric(
        "estimated_monthly_cost",
        "Custo mensal estimado",
        _money(finding.current_monthly_cost),
        unit="month",
        currency="USD",
        kind="estimate",
    )


def _estimated_savings(finding: CollectedFinding) -> dict[str, Any]:
    return _metric(
        "estimated_monthly_savings",
        "Economia potencial estimada",
        _money(finding.estimated_monthly_savings),
        unit="month",
        currency="USD",
        kind="estimate",
    )


def _rule(rule_key: str, criteria: list[dict[str, Any]]) -> dict[str, Any]:
    definition = RULES.get(rule_key)
    return {
        "key": rule_key,
        "name": definition.name if definition else rule_key,
        "description": definition.description if definition else "",
        "criteria": criteria,
    }


def _relevant_tags(tags: dict[str, Any], keys: list[str]) -> dict[str, str]:
    normalized = {key.lower(): (key, value) for key, value in tags.items()}
    result: dict[str, str] = {}
    for configured in keys:
        match = normalized.get(configured.lower())
        if match is not None:
            result[match[0]] = str(match[1])
    return result


def _payload(
    finding: CollectedFinding,
    *,
    summary: str,
    metrics: list[dict[str, Any]],
    details: dict[str, Any],
    criteria: list[dict[str, Any]],
    decision_parameters: dict[str, Any],
    system: str,
    evaluated_at: datetime,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "summary": summary,
        "metrics": metrics,
        "details": details,
        "rule": _rule(finding.rule_key, criteria),
        "decision_parameters": decision_parameters,
        "source": {
            "provider": "aws",
            "system": system,
            "evaluated_at": evaluated_at.astimezone(UTC).isoformat(),
        },
        "limitations": limitations or [],
    }


def _ebs_unattached(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    age_days = _number(raw.get("age_days"))
    size_gib = _number(raw.get("size_gib"))
    volume_type = raw.get("volume_type")
    size_text = f", possui {size_gib:g} GiB" if size_gib is not None else ""
    age_text = f" e foi criado há {age_days:g} dias" if age_days is not None else ""
    summary = (
        f"O volume {finding.resource_id} está disponível e sem anexação"
        f"{size_text}{age_text}. O custo mensal estimado de armazenamento é "
        f"US$ {_money(finding.current_monthly_cost):.2f}."
    )
    return _payload(
        finding,
        summary=summary,
        metrics=[
            _metric("volume_type", "Tipo do volume", volume_type),
            _metric("size", "Capacidade", size_gib, unit="GiB"),
            _metric("age_since_creation", "Idade desde a criação", age_days, unit="days"),
            _estimated_cost(finding),
            _estimated_savings(finding),
        ],
        details={
            "state": raw.get("state"),
            "volume_type": volume_type,
            "created_at": raw.get("created_at"),
        },
        criteria=[
            _criterion(
                "minimum_age_days",
                "Idade mínima desde a criação",
                config.get("minimum_age_days"),
                operator=">=",
                unit="days",
            ),
            _criterion(
                "minimum_monthly_savings_usd",
                "Economia mensal mínima estimada",
                config.get("minimum_monthly_savings_usd"),
                operator=">=",
                unit="month",
                currency="USD",
            ),
        ],
        decision_parameters={
            "minimum_age_days": config.get("minimum_age_days"),
            "minimum_monthly_savings_usd": config.get("minimum_monthly_savings_usd"),
            "monthly_price_per_gb": {
                str(volume_type): config.get("monthly_price_per_gb", {}).get(volume_type)
            }
            if volume_type
            else {},
        },
        system="AWS EC2/EBS inventory",
        evaluated_at=evaluated_at,
        limitations=[
            "A idade é calculada desde a criação do volume; esta coleta não informa "
            "quando ele foi desanexado."
        ],
    )


def _eip_unassociated(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    return _payload(
        finding,
        summary=(
            f"O Elastic IP {raw.get('public_ip') or finding.resource_id} está alocado, "
            "mas não está associado a instância nem interface de rede. "
            f"O custo mensal configurado é estimado em "
            f"US$ {_money(finding.current_monthly_cost):.2f}."
        ),
        metrics=[
            _metric("public_ip", "Elastic IP", raw.get("public_ip")),
            _estimated_cost(finding),
            _estimated_savings(finding),
        ],
        details={
            "public_ip": raw.get("public_ip"),
            "allocation_id": raw.get("allocation_id"),
            "domain": raw.get("domain"),
        },
        criteria=[
            _criterion("association", "Associação", "ausente", operator="="),
            _criterion(
                "minimum_monthly_savings_usd",
                "Economia mensal mínima estimada",
                config.get("minimum_monthly_savings_usd"),
                operator=">=",
                unit="month",
                currency="USD",
            ),
        ],
        decision_parameters={
            "monthly_cost_usd": config.get("monthly_cost_usd"),
            "minimum_monthly_savings_usd": config.get("minimum_monthly_savings_usd"),
        },
        system="AWS EC2/VPC inventory",
        evaluated_at=evaluated_at,
        limitations=["Esta coleta não registra há quanto tempo o endereço está sem associação."],
    )


def _snapshot_retention(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    age_days = _number(raw.get("age_days"))
    retention_days = _number(raw.get("retention_days"))
    excess_days = (
        age_days - retention_days if age_days is not None and retention_days is not None else None
    )
    summary = finding.description
    if age_days is not None and retention_days is not None and excess_days is not None:
        summary = (
            f"O snapshot {finding.resource_id} tem {age_days:g} dias e excede a retenção "
            f"aplicada de {retention_days:g} dias em {excess_days:g} dias."
        )
    return _payload(
        finding,
        summary=summary,
        metrics=[
            _metric("age", "Idade do snapshot", age_days, unit="days"),
            _metric("retention_excess", "Excesso sobre a retenção", excess_days, unit="days"),
            _metric(
                "source_volume_size",
                "Tamanho do volume de origem",
                raw.get("volume_size_gib"),
                unit="GiB",
            ),
            _estimated_cost(finding),
            _estimated_savings(finding),
        ],
        details={
            "volume_id": raw.get("volume_id"),
            "started_at": raw.get("started_at"),
        },
        criteria=[
            _criterion(
                "retention_days",
                "Retenção configurada",
                config.get("retention_days"),
                operator=">",
                unit="days",
            ),
            _criterion(
                "preserve_last_per_volume",
                "Snapshots recentes preservados por volume",
                config.get("preserve_last_per_volume"),
                operator="preserve",
            ),
            _criterion(
                "preserve_ami_snapshots",
                "Preservar snapshots usados por AMIs",
                config.get("preserve_ami_snapshots"),
                operator="=",
            ),
        ],
        decision_parameters={
            "retention_days": config.get("retention_days"),
            "preserve_last_per_volume": config.get("preserve_last_per_volume"),
            "preserve_ami_snapshots": config.get("preserve_ami_snapshots"),
            "monthly_price_per_gb": config.get("monthly_price_per_gb"),
        },
        system="AWS EC2/EBS inventory",
        evaluated_at=evaluated_at,
        limitations=[
            "A estimativa financeira é um limite superior baseado no tamanho do volume "
            "de origem; snapshots EBS são incrementais."
        ],
    )


def _stopped_ec2(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    volumes = raw.get("volumes") if isinstance(raw.get("volumes"), list) else []
    total_gib = sum(
        float(volume.get("size_gib") or 0) for volume in volumes if isinstance(volume, dict)
    )
    stopped_days = _number(raw.get("stopped_days"))
    duration = (
        f"há {stopped_days:g} dias"
        if stopped_days is not None
        else "com tempo de parada não confirmado"
    )
    summary = (
        f"A instância {finding.resource_id} está parada {duration} e mantém "
        f"{len(volumes)} volume(s) EBS, totalizando {total_gib:g} GiB. "
        f"O custo mensal estimado desses volumes é "
        f"US$ {_money(finding.current_monthly_cost):.2f}."
    )
    return _payload(
        finding,
        summary=summary,
        metrics=[
            _metric("stopped_days", "Tempo parada", stopped_days, unit="days"),
            _metric("volume_count", "Volumes associados", len(volumes), unit="volumes"),
            _metric("storage", "Armazenamento associado", total_gib, unit="GiB"),
            _estimated_cost(finding),
            _estimated_savings(finding),
        ],
        details={
            "state": "stopped",
            "instance_type": raw.get("instance_type"),
            "stopped_at": raw.get("stopped_at"),
            "volume_ids": [
                volume.get("volume_id")
                for volume in volumes
                if isinstance(volume, dict) and volume.get("volume_id")
            ],
            "volumes": [
                {
                    "volume_id": volume.get("volume_id"),
                    "size_gib": volume.get("size_gib"),
                    "type": volume.get("type"),
                }
                for volume in volumes
                if isinstance(volume, dict)
            ],
        },
        criteria=[
            _criterion(
                "minimum_stopped_days",
                "Tempo mínimo parada",
                config.get("minimum_stopped_days"),
                operator=">=",
                unit="days",
            ),
            _criterion(
                "minimum_monthly_savings_usd",
                "Economia mensal mínima estimada",
                config.get("minimum_monthly_savings_usd"),
                operator=">=",
                unit="month",
                currency="USD",
            ),
        ],
        decision_parameters={
            "minimum_stopped_days": config.get("minimum_stopped_days"),
            "include_unknown_stop_time": config.get("include_unknown_stop_time"),
            "minimum_monthly_savings_usd": config.get("minimum_monthly_savings_usd"),
            "monthly_price_per_gb": {
                str(volume.get("type")): config.get("monthly_price_per_gb", {}).get(
                    volume.get("type")
                )
                for volume in volumes
                if isinstance(volume, dict) and volume.get("type")
            },
        },
        system="AWS EC2/EBS inventory",
        evaluated_at=evaluated_at,
        limitations=(
            ["O instante de parada não pôde ser obtido; a duração não foi inferida."]
            if stopped_days is None
            else []
        ),
    )


def _nonprod_ec2(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    environment_keys = [str(key) for key in config.get("environment_tag_keys", [])]
    tags = raw.get("tags") if isinstance(raw.get("tags"), dict) else {}
    timezone = raw.get("timezone") or config.get("timezone")
    start = raw.get("business_hours_start") or config.get("business_hours_start")
    end = raw.get("business_hours_end") or config.get("business_hours_end")
    environment = _relevant_tags(tags, environment_keys)
    environment_display = [f"{key}={value}" for key, value in environment.items()]
    return _payload(
        finding,
        summary=(
            f"A instância não produtiva {finding.resource_id} estava em execução no momento "
            f"da coleta, fora da janela de {start} a {end} ({timezone})."
        ),
        metrics=[
            _metric("environment", "Ambiente observado", environment_display),
            _metric(
                "observed_at",
                "Horário observado",
                evaluated_at.astimezone(UTC).isoformat(),
            ),
            _estimated_cost(finding),
            _estimated_savings(finding),
        ],
        details={
            "state": "running",
            "instance_type": raw.get("instance_type"),
            "launched_at": raw.get("launched_at"),
            "observed_environment_tags": environment,
            "observed_at": evaluated_at.astimezone(UTC).isoformat(),
        },
        criteria=[
            _criterion("timezone", "Fuso horário", timezone, operator="="),
            _criterion("business_hours_start", "Início do expediente", start, operator="window"),
            _criterion("business_hours_end", "Fim do expediente", end, operator="window"),
            _criterion(
                "business_days",
                "Dias de expediente (ISO)",
                config.get("business_days"),
                operator="in",
            ),
            _criterion(
                "nonproduction_values",
                "Valores reconhecidos como não produtivos",
                config.get("nonproduction_values"),
                operator="in",
            ),
        ],
        decision_parameters={
            "timezone": timezone,
            "business_days": config.get("business_days"),
            "business_hours_start": start,
            "business_hours_end": end,
            "environment_tag_keys": environment_keys,
            "nonproduction_values": config.get("nonproduction_values"),
            "estimated_hourly_cost_by_instance_type": {
                str(raw.get("instance_type")): config.get(
                    "estimated_hourly_cost_by_instance_type", {}
                ).get(raw.get("instance_type"))
            }
            if raw.get("instance_type")
            else {},
        },
        system="AWS EC2 inventory",
        evaluated_at=evaluated_at,
        limitations=[
            "A evidência comprova o estado no instante da coleta; não comprova quantas "
            "horas a instância permaneceu ligada fora da janela."
        ],
    )


def _load_balancer(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    datapoints = _number(raw.get("datapoint_count"))
    total = _number(raw.get("metric_total"))
    metric_name = str(raw.get("metric") or "")
    is_bytes = metric_name == "ProcessedBytes"
    threshold = (
        config.get("maximum_processed_bytes") if is_bytes else config.get("maximum_requests")
    )
    unit = "bytes" if is_bytes else "requests"
    if datapoints == 0:
        summary = (
            f"O CloudWatch não retornou amostras de {metric_name or 'tráfego'} para "
            f"{finding.resource_id} na janela analisada. A ausência de tráfego não "
            "está confirmada."
        )
        limitations = [
            "Zero datapoints não é tratado como prova de tráfego zero; valide a "
            "disponibilidade da métrica antes de agir."
        ]
    else:
        summary = finding.description
        if total is not None:
            summary = (
                f"O Load Balancer {finding.resource_name or finding.resource_id} registrou "
                f"{total:g} {unit} nos últimos {raw.get('lookback_days')} dias, dentro "
                f"do limite configurado de {threshold}."
            )
        limitations = []
    return _payload(
        finding,
        summary=summary,
        metrics=[
            _metric("traffic_total", "Tráfego observado", total, unit=unit),
            _metric("datapoints", "Amostras retornadas", datapoints, unit="datapoints"),
            _metric("lookback", "Período analisado", raw.get("lookback_days"), unit="days"),
            _estimated_cost(finding),
            _estimated_savings(finding),
        ],
        details={
            "load_balancer_type": raw.get("type"),
            "metric": metric_name,
            "created_at": raw.get("created_at"),
        },
        criteria=[
            _criterion(
                "traffic_threshold",
                "Limite de tráfego",
                threshold,
                operator="<=",
                unit=unit,
            ),
            _criterion(
                "minimum_age_days",
                "Idade mínima do Load Balancer",
                config.get("minimum_age_days"),
                operator=">=",
                unit="days",
            ),
        ],
        decision_parameters={
            "lookback_days": config.get("lookback_days"),
            "minimum_age_days": config.get("minimum_age_days"),
            "maximum_requests": config.get("maximum_requests"),
            "maximum_processed_bytes": config.get("maximum_processed_bytes"),
            "estimated_base_monthly_cost_usd": config.get("estimated_base_monthly_cost_usd"),
        },
        system="AWS ELB inventory + Amazon CloudWatch",
        evaluated_at=evaluated_at,
        limitations=limitations,
    )


def _rds_idle(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    environment_keys = [str(key) for key in config.get("environment_tag_keys", [])]
    tags = raw.get("tags") if isinstance(raw.get("tags"), dict) else {}
    return _payload(
        finding,
        summary=(
            f"O RDS {finding.resource_id} apresentou CPU média de "
            f"{raw.get('average_cpu_percent')}% e máximo de "
            f"{raw.get('maximum_connections')} conexão(ões) na janela de "
            f"{raw.get('lookback_days')} dias, dentro dos limites aplicados."
        ),
        metrics=[
            _metric("instance_class", "Classe", raw.get("instance_class")),
            _metric("average_cpu", "CPU média", raw.get("average_cpu_percent"), unit="%"),
            _metric(
                "maximum_connections",
                "Máximo de conexões",
                raw.get("maximum_connections"),
                unit="connections",
            ),
            _metric("lookback", "Período analisado", raw.get("lookback_days"), unit="days"),
            _estimated_cost(finding),
            _estimated_savings(finding),
        ],
        details={
            "engine": raw.get("engine"),
            "instance_class": raw.get("instance_class"),
            "observed_environment_tags": _relevant_tags(tags, environment_keys),
        },
        criteria=[
            _criterion(
                "maximum_average_cpu_percent",
                "CPU média máxima",
                config.get("maximum_average_cpu_percent"),
                operator="<=",
                unit="%",
            ),
            _criterion(
                "maximum_connections",
                "Máximo de conexões permitido",
                config.get("maximum_connections"),
                operator="<=",
                unit="connections",
            ),
            _criterion(
                "lookback_days",
                "Período analisado",
                config.get("lookback_days"),
                operator="=",
                unit="days",
            ),
        ],
        decision_parameters={
            "lookback_days": config.get("lookback_days"),
            "maximum_average_cpu_percent": config.get("maximum_average_cpu_percent"),
            "maximum_connections": config.get("maximum_connections"),
            "environment_tag_keys": environment_keys,
            "nonproduction_values": config.get("nonproduction_values"),
            "estimated_monthly_cost_by_instance_class": {
                str(raw.get("instance_class")): config.get(
                    "estimated_monthly_cost_by_instance_class", {}
                ).get(raw.get("instance_class"))
            }
            if raw.get("instance_class")
            else {},
        },
        system="AWS RDS inventory + Amazon CloudWatch",
        evaluated_at=evaluated_at,
        limitations=[
            "A regra atual usa CPU e conexões. I/O não é coletado nesta versão e não "
            "participa da decisão."
        ],
    )


def _missing_tags(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    required = [str(key) for key in config.get("required_tags", [])]
    current = raw.get("current_tags") if isinstance(raw.get("current_tags"), dict) else {}
    missing = [str(key) for key in raw.get("missing_tags", [])]
    found = _relevant_tags(current, required)
    found_display = [f"{key}={value}" for key, value in found.items()]
    return _payload(
        finding,
        summary=(
            f"O recurso {finding.resource_name or finding.resource_id} não possui "
            f"{len(missing)} tag(s) obrigatória(s): {', '.join(missing)}."
        ),
        metrics=[
            _metric("missing_tags", "Tags ausentes", missing),
            _metric("found_required_tags", "Tags encontradas", found_display),
            _metric(
                "missing_tag_count",
                "Tags obrigatórias ausentes",
                len(missing),
                unit="tags",
            ),
            _metric("required_tag_count", "Tags obrigatórias", len(required), unit="tags"),
        ],
        details={
            "required_tags": required,
            "found_required_tags": found,
            "missing_tags": missing,
        },
        criteria=[
            _criterion(
                "required_tags",
                "Tags obrigatórias",
                required,
                operator="contains_keys",
            )
        ],
        decision_parameters={
            "required_tags": required,
            "resource_types": config.get("resource_types"),
        },
        system="AWS resource inventory",
        evaluated_at=evaluated_at,
    )


def _cost_growth(
    finding: CollectedFinding,
    config: dict[str, Any],
    evaluated_at: datetime,
) -> dict[str, Any]:
    raw = finding.evidence
    baseline = _number(raw.get("baseline_equivalent_usd"))
    current = _number(raw.get("current_spend_usd"))
    delta = _number(raw.get("delta_usd"))
    growth = _number(raw.get("growth_percent"))
    is_estimated = raw.get("estimated") is True
    summary = finding.description
    if baseline is not None and current is not None and delta is not None:
        percent = f" ({growth:.1f}%)" if growth is not None else ""
        cost_label = "O custo estimado" if is_estimated else "O custo"
        summary = (
            f"{cost_label} de {finding.service} em {finding.region} passou de "
            f"US$ {baseline:.2f} esperados para US$ {current:.2f} no período atual, "
            f"uma variação de +US$ {delta:.2f}{percent}."
        )
    contributors = [
        {
            "dimension": "usage_type",
            "name": item.get("usage_type"),
            "previous_value": item.get("baseline_equivalent_usd"),
            "current_value": item.get("current_spend_usd"),
            "delta": item.get("delta_usd"),
            "currency": "USD",
        }
        for item in raw.get("cost_contributors", [])
        if isinstance(item, dict)
    ]
    limitations = [
        "O aumento de custo não é tratado automaticamente como desperdício; a regra "
        "não estima economia potencial."
    ]
    if raw.get("estimated") is True or raw.get("breakdown_estimated") is True:
        limitations.append(
            "A AWS marcou dados do período como estimados; os valores podem ser revisados."
        )
    if raw.get("breakdown_status") == "unavailable":
        limitations.append(
            "O detalhamento por tipo de uso não ficou disponível nesta coleta; a "
            "comparação por serviço e região permanece válida."
        )
    current_cost_label = (
        "Custo estimado no período atual" if is_estimated else "Custo observado no período atual"
    )
    change_label = "Variação absoluta estimada" if is_estimated else "Variação absoluta"
    return _payload(
        finding,
        summary=summary,
        metrics=[
            _metric("previous_cost", "Custo esperado no período atual", baseline, currency="USD"),
            _metric(
                "current_cost",
                current_cost_label,
                current,
                currency="USD",
                kind="estimate" if is_estimated else "observed",
            ),
            _metric(
                "absolute_change",
                change_label,
                delta,
                currency="USD",
                kind="estimate" if is_estimated else "observed",
            ),
            _metric("percent_change", "Variação percentual", growth, unit="%"),
        ],
        details={
            "baseline_period": {
                "start": raw.get("baseline_start"),
                "end_exclusive": raw.get("baseline_end_exclusive"),
                "days": raw.get("baseline_period_days"),
                "total_usd": raw.get("baseline_total_usd"),
                "normalized_equivalent_usd": raw.get("baseline_equivalent_usd"),
            },
            "current_period": {
                "start": raw.get("comparison_start"),
                "end_exclusive": raw.get("comparison_end_exclusive"),
                "days": raw.get("comparison_period_days"),
                "spend_usd": raw.get("current_spend_usd"),
            },
            "contributors": contributors,
            "breakdown_status": raw.get("breakdown_status"),
            "estimated": bool(raw.get("estimated")),
        },
        criteria=[
            _criterion(
                "minimum_growth_percent",
                "Crescimento mínimo",
                config.get("minimum_growth_percent"),
                operator=">=",
                unit="%",
            ),
            _criterion(
                "minimum_delta_usd",
                "Aumento mínimo",
                config.get("minimum_delta_usd"),
                operator=">=",
                currency="USD",
            ),
            _criterion(
                "minimum_current_spend_usd",
                "Custo mínimo no período atual",
                config.get("minimum_current_spend_usd"),
                operator=">=",
                currency="USD",
            ),
        ],
        decision_parameters={
            "baseline_days": config.get("baseline_days"),
            "comparison_days": config.get("comparison_days"),
            "minimum_growth_percent": config.get("minimum_growth_percent"),
            "minimum_delta_usd": config.get("minimum_delta_usd"),
            "minimum_current_spend_usd": config.get("minimum_current_spend_usd"),
        },
        system="AWS Cost Explorer · UnblendedCost",
        evaluated_at=evaluated_at,
        limitations=limitations,
    )


_BUILDERS = {
    "ebs_unattached": _ebs_unattached,
    "eip_unassociated": _eip_unassociated,
    "snapshot_retention": _snapshot_retention,
    "ec2_stopped_with_ebs": _stopped_ec2,
    "ec2_nonprod_outside_hours": _nonprod_ec2,
    "load_balancer_no_traffic": _load_balancer,
    "rds_nonprod_idle": _rds_idle,
    "missing_required_tags": _missing_tags,
    "cost_growth_anomaly": _cost_growth,
}


def build_opportunity_evidence(
    finding: CollectedFinding,
    policy: dict[str, Any],
    *,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    evaluated_at = evaluated_at or datetime.now(UTC)
    config = policy.get("config") if isinstance(policy.get("config"), dict) else {}
    builder = _BUILDERS.get(finding.rule_key)
    if builder is None:
        payload = _payload(
            finding,
            summary=finding.description,
            metrics=[],
            details={},
            criteria=[],
            decision_parameters={},
            system="AWS resource analysis",
            evaluated_at=evaluated_at,
            limitations=["Este analyzer ainda não possui contrato de explicabilidade específico."],
        )
    else:
        payload = builder(finding, config, evaluated_at)
    return deepcopy(payload)
