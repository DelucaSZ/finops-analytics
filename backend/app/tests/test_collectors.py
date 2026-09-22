from datetime import UTC, datetime

from app.services.collectors import (
    _missing_tags,
    _outside_business_hours,
    _stopped_at,
    _tags_to_dict,
    collect_ebs_unattached,
)


def test_tags_to_dict() -> None:
    assert _tags_to_dict([{"Key": "Name", "Value": "web01"}]) == {"Name": "web01"}
    assert _tags_to_dict(None) == {}


def test_extract_stopped_at_from_state_transition_reason() -> None:
    instance = {"StateTransitionReason": "User initiated (2026-09-01 14:30:00 GMT)"}
    assert _stopped_at(instance) == datetime(2026, 9, 1, 14, 30, tzinfo=UTC)


def test_unknown_stop_time_returns_none() -> None:
    assert _stopped_at({"StateTransitionReason": "Server.SpotInstanceTermination"}) is None


def test_outside_business_hours_uses_configured_timezone() -> None:
    config = {
        "timezone": "America/Sao_Paulo",
        "business_days": [1, 2, 3, 4, 5],
        "business_hours_start": "08:00",
        "business_hours_end": "19:00",
    }
    # Monday, 09:00 in Sao Paulo.
    assert _outside_business_hours(config, datetime(2026, 9, 14, 12, 0, tzinfo=UTC)) is False
    # Monday, 21:00 in Sao Paulo.
    assert _outside_business_hours(config, datetime(2026, 9, 15, 0, 0, tzinfo=UTC)) is True


def test_missing_tags_is_case_insensitive() -> None:
    assert _missing_tags({"environment": "prod"}, ["Environment", "Owner"]) == ["Owner"]


class FakePaginator:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages

    def paginate(self, **_: object) -> list[dict]:
        return self.pages


class FakeEc2:
    def get_paginator(self, _: str) -> FakePaginator:
        return FakePaginator(
            [
                {
                    "Volumes": [
                        {
                            "VolumeId": "vol-123",
                            "State": "available",
                            "Size": 100,
                            "VolumeType": "gp3",
                            "CreateTime": datetime(2026, 1, 1, tzinfo=UTC),
                            "Tags": [{"Key": "Name", "Value": "orphan"}],
                        }
                    ]
                }
            ]
        )


class FakeSession:
    def client(self, *_: object, **__: object) -> FakeEc2:
        return FakeEc2()


def test_unattached_ebs_estimates_configured_monthly_cost() -> None:
    findings = collect_ebs_unattached(
        FakeSession(),  # type: ignore[arg-type]
        "sa-east-1",
        {
            "minimum_age_days": 7,
            "minimum_monthly_savings_usd": 1,
            "monthly_price_per_gb": {"gp3": 0.08},
            "excluded_tag_keys": [],
        },
    )
    assert len(findings) == 1
    assert str(findings[0].estimated_monthly_savings) == "8.00"
    assert findings[0].resource_id == "vol-123"
