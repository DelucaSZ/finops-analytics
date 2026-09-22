from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.config import settings
from app.models.finding import Finding
from app.services.ai import AIProviderError, explain_finding


def test_ai_explanation_requires_explicit_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ai_provider", "disabled")
    finding = Finding(
        fingerprint="a" * 64,
        scan_id="scan-id",
        account_id=1,
        rule_key="ebs_unattached",
        service="EC2/EBS",
        region="sa-east-1",
        resource_id="vol-123",
        title="Volume EBS sem anexação",
        description="Volume sem anexação.",
        evidence={},
        current_monthly_cost=Decimal("8.00"),
        estimated_monthly_savings=Decimal("8.00"),
        confidence="medium",
        severity="low",
        status="open",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    with pytest.raises(AIProviderError):
        explain_finding(finding)
