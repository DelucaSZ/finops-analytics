from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from app.services import collectors
from app.services.collector_types import CollectedFinding


class FixedTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 22, 12, tzinfo=UTC)


def cost_day(day, entries, estimated=False):
    return {
        "TimePeriod": {"Start": day, "End": day},
        "Estimated": estimated,
        "Groups": [
            {"Keys": keys, "Metrics": {"UnblendedCost": {"Amount": str(amount), "Unit": "USD"}}}
            for keys, amount in entries
        ],
    }


@pytest.fixture
def ce(monkeypatch):
    monkeypatch.setattr(collectors, "datetime", FixedTime)
    return Mock()


def scan(ce, config=None):
    session = Mock()
    session.client.return_value = ce
    return collectors.collect_cost_growth_anomalies(session, "global", config or {})


def test_cost_evidence_normalizes_periods_and_paginates_both_queries(ce):
    ce.get_cost_and_usage.side_effect = [
        {
            "ResultsByTime": [cost_day("2026-08-18", [(["EC2 - Other", "us-east-1"], 280)])],
            "NextPageToken": "main-page-2",
        },
        {"ResultsByTime": [cost_day("2026-09-15", [(["EC2 - Other", "us-east-1"], 210)], True)]},
        {
            "ResultsByTime": [
                cost_day("2026-08-18", [(["EBS:VolumeUsage.gp3"], 240), (["DataTransfer"], 40)])
            ],
            "NextPageToken": "detail-page-2",
        },
        {
            "ResultsByTime": [
                cost_day("2026-09-15", [(["EBS:VolumeUsage.gp3"], 205), (["DataTransfer"], 5)])
            ]
        },
    ]
    (finding,) = scan(ce)
    e = finding.evidence
    assert e["baseline_total_usd"] == 280
    assert e["baseline_equivalent_usd"] == 70  # 280 / 28 * 7
    assert e["current_spend_usd"] == 210
    assert e["delta_usd"] == 140
    assert e["growth_percent"] == 200
    assert e["baseline_start"] == "2026-08-18"
    assert e["baseline_end_exclusive"] == e["comparison_start"] == "2026-09-15"
    assert e["comparison_end_exclusive"] == "2026-09-22"
    assert e["estimated"] is True
    assert e["minimum_growth_percent"] == 30
    assert e["cost_contributors"] == [
        {
            "usage_type": "EBS:VolumeUsage.gp3",
            "baseline_equivalent_usd": 60,
            "current_spend_usd": 205,
            "delta_usd": 145,
        }
    ]
    calls = [call.kwargs for call in ce.get_cost_and_usage.call_args_list]
    assert calls[1] == {**calls[0], "NextPageToken": "main-page-2"}
    assert calls[3] == {**calls[2], "NextPageToken": "detail-page-2"}
    assert calls[2]["Filter"] == {
        "And": [
            {"Dimensions": {"Key": "SERVICE", "Values": ["EC2 - Other"]}},
            {"Dimensions": {"Key": "REGION", "Values": ["us-east-1"]}},
        ]
    }
    assert calls[2]["TimePeriod"] == calls[0]["TimePeriod"]
    assert finding.estimated_monthly_savings == 0


@pytest.mark.parametrize("baseline", [0, -28])
def test_nonpositive_baseline_has_no_fabricated_percentage(ce, baseline):
    ce.get_cost_and_usage.side_effect = [
        {
            "ResultsByTime": [
                cost_day("2026-08-18", [(["RDS", ""], baseline)]),
                cost_day("2026-09-15", [(["RDS", ""], 100)]),
            ]
        },
        {"ResultsByTime": []},
    ]
    (finding,) = scan(ce)
    assert finding.evidence["growth_percent"] is None
    assert "999" not in finding.description
    assert finding.region == "global"
    assert ce.get_cost_and_usage.call_args.kwargs["Filter"]["And"][1]["Dimensions"]["Values"] == [
        ""
    ]


def test_optional_breakdown_failure_keeps_primary_evidence(ce):
    ce.get_cost_and_usage.side_effect = [
        {"ResultsByTime": [cost_day("2026-09-15", [(["RDS", "us-east-1"], 600)])]},
        ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "GetCostAndUsage"
        ),
    ]
    (finding,) = scan(ce)
    assert finding.evidence["current_spend_usd"] == 600
    assert finding.evidence["breakdown_status"] == "unavailable"
    assert finding.evidence["cost_contributors"] == []
    assert finding.severity == "high"


@pytest.mark.parametrize(
    "config",
    [
        {"minimum_delta_usd": 200},
        {"minimum_current_spend_usd": 300},
        {"minimum_growth_percent": 250},
    ],
)
def test_no_breakdown_query_for_items_below_policy_thresholds(ce, config):
    ce.get_cost_and_usage.return_value = {
        "ResultsByTime": [
            cost_day("2026-08-18", [(["EC2", "us-east-1"], 280)]),
            cost_day("2026-09-15", [(["EC2", "us-east-1"], 210)]),
        ]
    }
    assert scan(ce, config) == []
    assert ce.get_cost_and_usage.call_count == 1


def test_primary_failure_is_not_treated_as_empty_success(ce):
    ce.get_cost_and_usage.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Denied"}}, "GetCostAndUsage"
    )
    with pytest.raises(ClientError):
        scan(ce)


def test_policy_evidence_is_a_snapshot_not_a_reference(monkeypatch):
    item = CollectedFinding("ebs_unattached", "EC2/EBS", "us-east-1", "vol-1", "EBS", "Available")
    monkeypatch.setitem(collectors.COLLECTORS, "ebs_unattached", lambda *_: [item])
    config = {"minimum_age_days": 7, "monthly_price_per_gb": {"gp3": 0.08}}
    findings, errors, failed = collectors.run_collectors(
        Mock(),
        ["us-east-1"],
        [
            {
                "rule_key": "ebs_unattached",
                "enabled": True,
                "implemented": True,
                "config": config,
            }
        ],
    )
    config["minimum_age_days"] = 90
    config["monthly_price_per_gb"]["gp3"] = 1
    assert not errors and not failed
    assert findings[0].evidence["policy_config"] == {
        "minimum_age_days": 7,
        "monthly_price_per_gb": {"gp3": 0.08},
    }
    assert findings[0].evidence["evaluated_at"]
