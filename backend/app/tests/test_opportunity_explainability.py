from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.services.collector_types import CollectedFinding
from app.services.opportunity_explainability import build_opportunity_evidence
from app.services.policies import RULES

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def finding(rule_key: str, evidence: dict, *, service: str = "EC2") -> CollectedFinding:
    return CollectedFinding(
        rule_key=rule_key,
        service=service,
        region="sa-east-1",
        resource_id="resource-1",
        resource_name="resource-name",
        title="Finding",
        description="Raw analyzer description",
        evidence=evidence,
        current_monthly_cost=Decimal("42.31"),
        estimated_monthly_savings=Decimal("42.31"),
        confidence="high",
        severity="medium",
    )


def policy(rule_key: str) -> dict:
    return {"rule_key": rule_key, "config": RULES[rule_key].config}


@pytest.mark.parametrize(
    ("rule_key", "raw", "expected_metric"),
    [
        (
            "ebs_unattached",
            {
                "state": "available",
                "size_gib": 500,
                "volume_type": "gp3",
                "created_at": "2026-09-01T00:00:00+00:00",
                "age_days": 24,
                "tags": {"Password": "must-not-be-persisted"},
            },
            "size",
        ),
        (
            "eip_unassociated",
            {
                "public_ip": "203.0.113.10",
                "allocation_id": "eipalloc-1",
                "domain": "vpc",
            },
            "estimated_monthly_cost",
        ),
        (
            "snapshot_retention",
            {
                "volume_id": "vol-1",
                "volume_size_gib": 100,
                "started_at": "2026-06-01T00:00:00+00:00",
                "age_days": 116,
                "retention_days": 90,
            },
            "retention_excess",
        ),
        (
            "ec2_stopped_with_ebs",
            {
                "instance_type": "m6i.large",
                "stopped_at": "2026-09-08T00:00:00+00:00",
                "stopped_days": 17,
                "volumes": [
                    {"volume_id": "vol-1", "size_gib": 300, "type": "gp3"},
                    {"volume_id": "vol-2", "size_gib": 200, "type": "gp3"},
                ],
            },
            "storage",
        ),
        (
            "ec2_nonprod_outside_hours",
            {
                "instance_type": "t3.large",
                "launched_at": "2026-09-01T00:00:00+00:00",
                "timezone": "America/Sao_Paulo",
                "business_hours_start": "08:00",
                "business_hours_end": "19:00",
                "tags": {
                    "Environment": "dev",
                    "Password": "must-not-be-persisted",
                },
            },
            "estimated_monthly_cost",
        ),
        (
            "load_balancer_no_traffic",
            {
                "type": "application",
                "metric": "RequestCount",
                "metric_total": 0,
                "datapoint_count": 7,
                "lookback_days": 7,
                "created_at": "2026-08-01T00:00:00+00:00",
            },
            "traffic_total",
        ),
        (
            "rds_nonprod_idle",
            {
                "engine": "postgres",
                "instance_class": "db.t3.medium",
                "average_cpu_percent": 2.1,
                "maximum_connections": 1,
                "lookback_days": 7,
                "tags": {
                    "Environment": "hml",
                    "ConnectionString": "must-not-be-persisted",
                },
            },
            "average_cpu",
        ),
        (
            "missing_required_tags",
            {
                "missing_tags": ["Owner"],
                "current_tags": {
                    "Environment": "Production",
                    "Secret": "must-not-be-persisted",
                },
            },
            "missing_tag_count",
        ),
        (
            "cost_growth_anomaly",
            {
                "baseline_period_days": 28,
                "comparison_period_days": 7,
                "baseline_equivalent_usd": 3190,
                "current_spend_usd": 4820,
                "delta_usd": 1630,
                "growth_percent": 51.1,
                "baseline_start": "2026-08-21",
                "baseline_end_exclusive": "2026-09-18",
                "comparison_start": "2026-09-18",
                "comparison_end_exclusive": "2026-09-25",
                "baseline_total_usd": 12760,
                "breakdown_status": "available",
                "estimated": False,
                "cost_contributors": [
                    {
                        "usage_type": "BoxUsage",
                        "baseline_equivalent_usd": 1200,
                        "current_spend_usd": 2080,
                        "delta_usd": 880,
                    }
                ],
            },
            "percent_change",
        ),
    ],
)
def test_each_current_analyzer_builds_structured_evidence(
    rule_key,
    raw,
    expected_metric,
):
    result = build_opportunity_evidence(
        finding(
            rule_key,
            raw,
            service="Amazon EC2" if rule_key == "cost_growth_anomaly" else "EC2",
        ),
        policy(rule_key),
        evaluated_at=NOW,
    )

    assert result["schema_version"] == 1
    assert result["summary"]
    assert result["rule"]["key"] == rule_key
    assert result["rule"]["name"] != rule_key
    assert result["rule"]["description"]
    assert result["source"]["evaluated_at"] == NOW.isoformat()
    assert any(metric["key"] == expected_metric for metric in result["metrics"])
    assert "policy_config" not in result
    assert "must-not-be-persisted" not in str(result)


def test_unknown_ec2_stop_time_is_not_invented():
    result = build_opportunity_evidence(
        finding(
            "ec2_stopped_with_ebs",
            {
                "instance_type": "m6i.large",
                "stopped_at": None,
                "stopped_days": None,
                "volumes": [{"volume_id": "vol-1", "size_gib": 100, "type": "gp3"}],
            },
        ),
        policy("ec2_stopped_with_ebs"),
        evaluated_at=NOW,
    )

    stopped_days = next(metric for metric in result["metrics"] if metric["key"] == "stopped_days")
    assert stopped_days["value"] is None
    assert "não confirmado" in result["summary"]
    assert result["limitations"]


def test_load_balancer_without_datapoints_does_not_claim_zero_traffic():
    result = build_opportunity_evidence(
        finding(
            "load_balancer_no_traffic",
            {
                "type": "application",
                "metric": "RequestCount",
                "metric_total": 0,
                "datapoint_count": 0,
                "lookback_days": 7,
            },
        ),
        policy("load_balancer_no_traffic"),
        evaluated_at=NOW,
    )

    assert "não está confirmada" in result["summary"]
    assert "prova de tráfego zero" in result["limitations"][0]


def test_cost_growth_preserves_periods_thresholds_and_contributors():
    raw = {
        "baseline_period_days": 28,
        "comparison_period_days": 7,
        "baseline_equivalent_usd": 3190,
        "current_spend_usd": 4820,
        "delta_usd": 1630,
        "growth_percent": 51.1,
        "baseline_start": "2026-08-21",
        "baseline_end_exclusive": "2026-09-18",
        "comparison_start": "2026-09-18",
        "comparison_end_exclusive": "2026-09-25",
        "baseline_total_usd": 12760,
        "breakdown_status": "available",
        "estimated": False,
        "cost_contributors": [
            {
                "usage_type": "EC2:BoxUsage",
                "baseline_equivalent_usd": 1200,
                "current_spend_usd": 2080,
                "delta_usd": 880,
            }
        ],
    }
    result = build_opportunity_evidence(
        finding("cost_growth_anomaly", raw, service="Amazon EC2"),
        policy("cost_growth_anomaly"),
        evaluated_at=NOW,
    )

    assert result["details"]["baseline_period"]["start"] == "2026-08-21"
    assert result["details"]["current_period"]["spend_usd"] == 4820
    assert result["details"]["contributors"][0]["delta"] == 880
    assert {criterion["key"] for criterion in result["rule"]["criteria"]} >= {
        "minimum_growth_percent",
        "minimum_delta_usd",
        "minimum_current_spend_usd",
    }


def test_decision_parameters_are_a_snapshot():
    config = {
        **RULES["ebs_unattached"].config,
        "monthly_price_per_gb": {"gp3": 0.08},
    }
    result = build_opportunity_evidence(
        finding(
            "ebs_unattached",
            {
                "state": "available",
                "size_gib": 100,
                "volume_type": "gp3",
                "age_days": 30,
            },
        ),
        {"rule_key": "ebs_unattached", "config": config},
        evaluated_at=NOW,
    )
    config["minimum_age_days"] = 90
    config["monthly_price_per_gb"]["gp3"] = 1

    assert result["decision_parameters"]["minimum_age_days"] == 7
    assert result["decision_parameters"]["monthly_price_per_gb"]["gp3"] == 0.08
