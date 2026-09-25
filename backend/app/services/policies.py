from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.policy import Policy


@dataclass(frozen=True)
class RuleDefinition:
    key: str
    name: str
    description: str
    implemented: bool
    enabled: bool
    config: dict[str, Any]


EBS_PRICES = {"gp2": 0.10, "gp3": 0.08, "io1": 0.125, "io2": 0.125, "st1": 0.045, "sc1": 0.015}

RULES: dict[str, RuleDefinition] = {
    "ebs_unattached": RuleDefinition(
        key="ebs_unattached",
        name="Volumes EBS sem anexação",
        description="Localiza volumes disponíveis que continuam gerando cobrança.",
        implemented=True,
        enabled=True,
        config={
            "minimum_age_days": 7,
            "minimum_monthly_savings_usd": 1,
            "monthly_price_per_gb": EBS_PRICES,
            "excluded_tag_keys": ["nuvemiq:ignore", "do-not-delete"],
        },
    ),
    "eip_unassociated": RuleDefinition(
        key="eip_unassociated",
        name="Elastic IP sem associação",
        description="Identifica endereços IPv4 públicos alocados e não associados.",
        implemented=True,
        enabled=True,
        config={
            "monthly_cost_usd": 3.65,
            "minimum_monthly_savings_usd": 1,
            "excluded_tag_keys": ["nuvemiq:ignore"],
        },
    ),
    "snapshot_retention": RuleDefinition(
        key="snapshot_retention",
        name="Snapshots fora da retenção",
        description="Encontra snapshots antigos fora da política de retenção.",
        implemented=True,
        enabled=True,
        config={
            "retention_days": 90,
            "preserve_last_per_volume": 3,
            "preserve_ami_snapshots": True,
            "monthly_price_per_gb": 0.05,
            "minimum_monthly_savings_usd": 1,
            "excluded_tag_keys": ["nuvemiq:ignore", "retention:keep"],
        },
    ),
    "ec2_stopped_with_ebs": RuleDefinition(
        key="ec2_stopped_with_ebs",
        name="EC2 desligada mantendo EBS",
        description="Aponta instâncias paradas que mantêm volumes cobrados.",
        implemented=True,
        enabled=True,
        config={
            "minimum_stopped_days": 7,
            "include_unknown_stop_time": True,
            "minimum_monthly_savings_usd": 1,
            "monthly_price_per_gb": EBS_PRICES,
            "excluded_tag_keys": ["nuvemiq:ignore"],
        },
    ),
    "ec2_nonprod_outside_hours": RuleDefinition(
        key="ec2_nonprod_outside_hours",
        name="EC2 não produtiva fora do expediente",
        description="Detecta instâncias não produtivas ligadas fora da janela definida.",
        implemented=True,
        enabled=True,
        config={
            "timezone": "America/Sao_Paulo",
            "business_days": [1, 2, 3, 4, 5],
            "business_hours_start": "08:00",
            "business_hours_end": "19:00",
            "environment_tag_keys": ["Environment", "Ambiente"],
            "nonproduction_values": ["dev", "development", "hml", "homolog", "test", "qa"],
            "excluded_tag_keys": ["nuvemiq:ignore"],
            "estimated_hourly_cost_by_instance_type": {},
        },
    ),
    "load_balancer_no_traffic": RuleDefinition(
        key="load_balancer_no_traffic",
        name="Load Balancer sem tráfego",
        description="Avalia balanceadores sem requisições ou bytes processados.",
        implemented=True,
        enabled=True,
        config={
            "lookback_days": 7,
            "minimum_age_days": 7,
            "maximum_requests": 0,
            "maximum_processed_bytes": 0,
            "estimated_base_monthly_cost_usd": 16.43,
            "excluded_tag_keys": ["nuvemiq:ignore"],
        },
    ),
    "rds_nonprod_idle": RuleDefinition(
        key="rds_nonprod_idle",
        name="RDS não produtivo ocioso",
        description="Cruza CPU e conexões para localizar bancos não produtivos ociosos.",
        implemented=True,
        enabled=True,
        config={
            "lookback_days": 7,
            "maximum_average_cpu_percent": 5,
            "maximum_connections": 1,
            "environment_tag_keys": ["Environment", "Ambiente"],
            "nonproduction_values": ["dev", "development", "hml", "homolog", "test", "qa"],
            "estimated_monthly_cost_by_instance_class": {},
            "excluded_tag_keys": ["nuvemiq:ignore"],
        },
    ),
    "missing_required_tags": RuleDefinition(
        key="missing_required_tags",
        name="Recursos sem tags obrigatórias",
        description="Valida tags de ambiente, responsável e outras chaves corporativas.",
        implemented=True,
        enabled=True,
        config={
            "required_tags": ["Environment", "Owner"],
            "resource_types": ["ec2", "ebs", "rds", "load-balancer"],
            "excluded_tag_keys": ["nuvemiq:ignore"],
        },
    ),
    "cost_growth_anomaly": RuleDefinition(
        key="cost_growth_anomaly",
        name="Crescimentos anormais de custo",
        description="Compara conta, serviço e região com a linha de base histórica.",
        implemented=True,
        enabled=True,
        config={
            "baseline_days": 28,
            "comparison_days": 7,
            "minimum_growth_percent": 30,
            "minimum_delta_usd": 50,
            "minimum_current_spend_usd": 20,
        },
    ),
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def get_policy_row(
    db: Session, rule_key: str, scope: str, account_id: int | None = None
) -> Policy | None:
    statement = select(Policy).where(Policy.rule_key == rule_key, Policy.scope == scope)
    if account_id is None:
        statement = statement.where(Policy.account_id.is_(None))
    else:
        statement = statement.where(Policy.account_id == account_id)
    return db.scalar(statement)


def get_effective_policy(db: Session, rule_key: str, account_id: int | None = None) -> dict:
    definition = RULES[rule_key]
    enabled = definition.enabled
    config = deepcopy(definition.config)
    override_fields: list[str] = []

    global_policy = get_policy_row(db, rule_key, "global")
    if global_policy:
        enabled = global_policy.enabled if global_policy.enabled is not None else enabled
        config = deep_merge(config, global_policy.config or {})

    account_policy = None
    if account_id is not None:
        account_policy = get_policy_row(db, rule_key, "account", account_id)
        if account_policy:
            enabled = account_policy.enabled if account_policy.enabled is not None else enabled
            config = deep_merge(config, account_policy.config or {})
            override_fields = sorted((account_policy.config or {}).keys())
            if account_policy.enabled is not None:
                override_fields.insert(0, "enabled")

    return {
        "rule_key": definition.key,
        "name": definition.name,
        "description": definition.description,
        "implemented": definition.implemented,
        "enabled": enabled,
        "config": config,
        "inherited": account_policy is None,
        "override_fields": override_fields,
    }


def list_effective_policies(db: Session, account_id: int | None = None) -> list[dict]:
    return [get_effective_policy(db, key, account_id) for key in RULES]


def upsert_policy(
    db: Session,
    *,
    rule_key: str,
    scope: str,
    account_id: int | None,
    enabled: bool | None,
    config: dict,
) -> Policy:
    if rule_key not in RULES:
        raise KeyError(rule_key)
    policy = get_policy_row(db, rule_key, scope, account_id)
    if policy is None:
        policy = Policy(
            scope=scope,
            account_id=account_id,
            rule_key=rule_key,
            enabled=enabled,
            config=config,
        )
        db.add(policy)
    else:
        policy.enabled = enabled
        policy.config = config
    db.commit()
    db.refresh(policy)
    return policy


def serialize_catalog() -> list[dict]:
    return [asdict(rule) for rule in RULES.values()]
