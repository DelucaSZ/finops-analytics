from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.collector_types import CollectedFinding
from app.services.opportunity_evidence import build_collected_finding_evidence
from app.services.policies import RULES

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def policy(rule_key: str) -> dict:
    rule = RULES[rule_key]
    return {
        "rule_key": rule.key,
        "name": rule.name,
        "description": rule.description,
        "config": deepcopy(rule.config),
    }


def finding(rule_key: str, evidence: dict, *, cost: str = "42.00", savings: str = "42.00"):
    return CollectedFinding(
        rule_key=rule_key,
        service="EC2" if rule_key != "rds_nonprod_idle" else "RDS",
        region="sa-east-1",
        resource_id="resource-1",
        resource_name="test-resource",
        title="Test",
        description="Deterministic description",
        evidence=evidence,
        current_monthly_cost=Decimal(cost),
        estimated_monthly_savings=Decimal(savings),
        confidence="high",
        severity="medium",
    )


CASES = {
    "ebs_unattached": {
        "state": "available",
        "size_gib": 500,
        "volume_type": "gp3",
        "created_at": "2026-09-01T00:00:00+00:00",
        "age_days": 24,
        "tags": {"Name": "orphan", "secret-looking": "must-not-be-copied"},
    },
    "eip_unassociated": {
        "public_ip": "203.0.113.10",
        "allocation_id": "eipalloc-123",
        "domain": "vpc",
        "tags": {"Name": "unused-ip"},
    },
    "snapshot_retention": {
        "volume_id": "vol-123",
        "volume_size_gib": 200,
        "started_at": "2026-05-01T00:00:00+00:00",
        "age_days": 147,
        "retention_days": 90,
        "tags": {},
    },
    "ec2_stopped_with_ebs": {
        "state": "stopped",
        "instance_type": "m6i.large",
        "stopped_at": "2026-09-08T12:00:00+00:00",
        "stopped_days": 17,
        "volumes": [
            {"volume_id": "vol-a", "size_gib": 200, "type": "gp3"},
            {"volume_id": "vol-b", "size_gib": 300, "type": "gp3"},
        ],
        "tags": {"Environment": "prod"},
    },
    "ec2_nonprod_outside_hours": {
        "state": "running",
        "instance_type": "t3.large",
        "observed_at": NOW.isoformat(),
        "observed_local_time": "2026-09-25T09:00:00-03:00",
        "timezone": "America/Sao_Paulo",
        "business_hours_start": "08:00",
        "business_hours_end": "19:00",
        "tags": {"Environment": "dev", "Owner": "platform"},
    },
    "load_balancer_no_traffic": {
        "type": "application",
        "metric": "RequestCount",
        "metric_total": 0,
        "datapoint_count": 7,
        "lookback_days": 7,
        "created_at": "2026-08-01T00:00:00+00:00",
        "tags": {},
    },
    "rds_nonprod_idle": {
        "engine": "postgres",
        "instance_class": "db.t4g.medium",
        "average_cpu_percent": 2.1,
        "maximum_connections": 1,
        "lookback_days": 7,
        "tags": {"Environment": "hml", "Owner": "db-team"},
    },
    "missing_required_tags": {
        "missing_tags": ["Owner"],
        "current_tags": {"Environment": "Production", "InternalNote": "do-not-store"},
    },
    "cost_growth_anomaly": {
        "baseline_period_days": 28,
        "comparison_period_days": 7,
        "baseline_equivalent_usd": 3190.0,
        "current_spend_usd": 4820.0,
        "delta_usd": 1630.0,
        "growth_percent": 51.1,
        "baseline_start": "2026-08-21",
        "baseline_end_exclusive": "2026-09-18",
        "comparison_start": "2026-09-18",
        "comparison_end_exclusive": "2026-09-25",
        "baseline_total_usd": 12760.0,
        "minimum_growth_percent": 30,
        "minimum_delta_usd": 50,
        "minimum_current_spend_usd": 20,
        "source": "AWS Cost Explorer",
        "metric": "UnblendedCost",
        "estimated": False,
        "breakdown_status": "available",
        "cost_contributors": [
            {
                "usage_type": "BoxUsage:m6i.large",
                "baseline_equivalent_usd": 1000.0,
                "current_spend_usd": 1880.0,
                "delta_usd": 880.0,
            },
            {
                "usage_type": "RDS:Multi-AZ",
                "baseline_equivalent_usd": 700.0,
                "current_spend_usd": 1210.0,
                "delta_usd": 510.0,
            },
        ],
    },
}


@pytest.mark.parametrize("rule_key", sorted(CASES))
def test_every_current_analyzer_produces_structured_evidence(rule_key: str) -> None:
    item = finding(rule_key, deepcopy(CASES[rule_key]))
    evidence = build_collected_finding_evidence(item, policy(rule_key), evaluated_at=NOW)

    assert evidence["schema_version"] == 1
    assert evidence["summary"]
    assert evidence["rule"]["key"] == rule_key
    assert evidence["rule"]["name"] == RULES[rule_key].name
    assert isinstance(evidence["metrics"], list)
    assert isinstance(evidence["criteria"], list)
    assert isinstance(evidence["details"], dict)
    assert isinstance(evidence["parameters"], dict)
    assert "policy_config" not in evidence
    assert "tags" not in evidence["details"]


def test_stopped_ec2_preserves_real_storage_and_cost_metrics() -> None:
    evidence = build_collected_finding_evidence(
        finding("ec2_stopped_with_ebs", deepcopy(CASES["ec2_stopped_with_ebs"])),
        policy("ec2_stopped_with_ebs"),
        evaluated_at=NOW,
    )
    metrics = {item["key"]: item for item in evidence["metrics"]}
    assert metrics["stopped_days"]["value"] == 17
    assert metrics["storage_gib"]["value"] == 500
    assert metrics["estimated_monthly_storage_cost"]["value"] == 42.0
    assert evidence["details"]["state"] == "stopped"
    assert [item["volume_id"] for item in evidence["details"]["volumes"]] == ["vol-a", "vol-b"]


def test_unknown_stopped_duration_is_not_invented() -> None:
    raw = deepcopy(CASES["ec2_stopped_with_ebs"])
    raw["stopped_days"] = None
    raw["stopped_at"] = None
    evidence = build_collected_finding_evidence(
        finding("ec2_stopped_with_ebs", raw),
        policy("ec2_stopped_with_ebs"),
        evaluated_at=NOW,
    )
    metrics = {item["key"]: item for item in evidence["metrics"]}
    assert "stopped_days" not in metrics
    assert "não pôde ser confirmada" in evidence["summary"]
    assert any("nenhum número de dias" in note for note in evidence["notes"])


def test_load_balancer_without_datapoints_does_not_claim_zero_traffic() -> None:
    raw = deepcopy(CASES["load_balancer_no_traffic"])
    raw["datapoint_count"] = 0
    evidence = build_collected_finding_evidence(
        finding("load_balancer_no_traffic", raw),
        policy("load_balancer_no_traffic"),
        evaluated_at=NOW,
    )
    assert "ausência de tráfego não está confirmada" in evidence["summary"]
    assert any("não trata tráfego zero" in note for note in evidence["notes"])


def test_cost_growth_exposes_period_values_thresholds_and_contributors() -> None:
    item = finding(
        "cost_growth_anomaly",
        deepcopy(CASES["cost_growth_anomaly"]),
        cost="20657.14",
        savings="0",
    )
    item.service = "Amazon Elastic Compute Cloud - Compute"
    evidence = build_collected_finding_evidence(
        item,
        policy("cost_growth_anomaly"),
        evaluated_at=NOW,
    )
    metrics = {metric["key"]: metric for metric in evidence["metrics"]}
    criteria = {criterion["key"]: criterion for criterion in evidence["criteria"]}

    assert metrics["previous_period_cost"]["value"] == 3190.0
    assert metrics["current_period_cost"]["value"] == 4820.0
    assert metrics["absolute_cost_change"]["value"] == 1630.0
    assert metrics["cost_growth_percent"]["value"] == 51.1
    assert criteria["minimum_growth_percent"]["threshold_value"] == 30
    assert evidence["contributors"][0]["delta"] == 880.0
    assert "desperdício" in evidence["notes"][0]


def test_missing_tags_keeps_only_policy_relevant_tag_values() -> None:
    evidence = build_collected_finding_evidence(
        finding("missing_required_tags", deepcopy(CASES["missing_required_tags"]), cost="0", savings="0"),
        policy("missing_required_tags"),
        evaluated_at=NOW,
    )
    assert evidence["details"]["required_tags"] == ["Environment", "Owner"]
    assert evidence["details"]["required_tags_found"] == {"Environment": "Production"}
    assert evidence["details"]["missing_tags"] == ["Owner"]
    assert "InternalNote" not in str(evidence["details"])
