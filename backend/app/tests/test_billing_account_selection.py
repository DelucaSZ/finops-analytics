from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.billing import (
    AwsBillingApiRequest,
    AwsBillingRequest,
    BillingGranularity,
    BillingGroupBy,
    BillingMetric,
)
from app.services.aws_billing import AwsBillingService, BillingQueryCache


def _api_payload(**overrides):
    payload = {
        "account_ids": [1],
        "start_date": date(2026, 10, 1),
        "end_date": date(2026, 10, 2),
    }
    payload.update(overrides)
    return payload


def test_billing_api_rejects_empty_account_selection():
    with pytest.raises(ValidationError) as error:
        AwsBillingApiRequest(**_api_payload(account_ids=[]))

    assert "account_ids" in str(error.value)


def test_billing_api_requires_explicit_account_ids():
    payload = _api_payload()
    payload.pop("account_ids")

    with pytest.raises(ValidationError) as error:
        AwsBillingApiRequest(**payload)

    assert "account_ids" in str(error.value)


def test_billing_service_never_expands_empty_account_ids_to_all_accounts():
    aws_called = False

    class _EmptyDb:
        def scalars(self, _statement):
            return []

    def session_factory(_configuration):
        nonlocal aws_called
        aws_called = True
        raise AssertionError("AWS Cost Explorer must not be called for an empty selection")

    # model_construct deliberately bypasses Pydantic validation to prove the service
    # itself has no implicit empty-list => all-accounts fallback.
    request = AwsBillingRequest.model_construct(
        account_ids=[],
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 2),
        granularity=BillingGranularity.DAILY,
        metric=BillingMetric.AMORTIZED_COST,
        group_by=BillingGroupBy.NONE,
        exclude_record_types=["Credit"],
    )
    response = AwsBillingService(
        _EmptyDb(),
        cache=BillingQueryCache(),
        session_factory=session_factory,
        today_factory=lambda: date(2026, 10, 16),
    ).summary(request)

    assert response.totals == []
    assert aws_called is False
