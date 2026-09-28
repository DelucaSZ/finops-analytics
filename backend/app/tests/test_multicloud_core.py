from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.collection_run import CollectionRun
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.collection_comparison import (
    CollectionComparisonError,
    validate_comparable_runs,
)
from app.services.dashboard import dashboard_summary
from app.services.opportunity_evidence import normalize_persisted_evidence
from app.services.opportunity_fingerprint import build_opportunity_fingerprint
from app.services.opportunity_query import OpportunityFilters, list_opportunities

NOW = datetime(2026, 9, 27, 20, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'multicloud.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _finding(
    *,
    opportunity_id: str,
    provider: str,
    account_id: str,
    region: str | None,
    resource_id: str,
    service: str,
    resource_type: str,
) -> Finding:
    return Finding(
        id=opportunity_id,
        fingerprint=build_opportunity_fingerprint(
            provider=provider,
            account_id=account_id,
            region=region,
            scope=service,
            resource_id=resource_id,
            rule_id="idle_resource",
        ),
        scan_id=None,
        provider=provider,
        account_id=account_id,
        rule_key="idle_resource",
        service=service,
        region=region,
        resource_id=resource_id,
        resource_name=f"{provider}-resource",
        resource_type=resource_type,
        provider_metadata={"native_id": resource_id},
        title="Idle resource",
        description="Fixture provider-neutral",
        evidence={"metric": "idle"},
        current_monthly_cost=Decimal("25.00"),
        estimated_monthly_savings=Decimal("10.00"),
        currency="USD",
        confidence="high",
        severity="medium",
        status="open",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )


def test_core_persists_and_queries_non_aws_opportunity_without_aws_account(db):
    run = CollectionRun(
        id="oci-run",
        provider="oci",
        account_id="ocid1.tenancy.oc1..example",
        scope={"regions": ["sa-saopaulo-1"]},
        started_at=NOW,
        finished_at=NOW + timedelta(minutes=1),
        status="SUCCESS",
    )
    finding = _finding(
        opportunity_id="oci-opportunity",
        provider="oci",
        account_id="ocid1.tenancy.oc1..example",
        region="sa-saopaulo-1",
        resource_id="ocid1.instance.oc1.sa-saopaulo-1.example",
        service="Compute",
        resource_type="Compute Instance",
    )
    db.add_all([run, finding])
    db.flush()
    db.add(
        OpportunityObservation(
            opportunity_id=finding.id,
            collection_run_id=run.id,
            observed_at=NOW,
            severity="medium",
            current_monthly_cost=Decimal("25.00"),
            estimated_monthly_savings=Decimal("10.00"),
            currency="USD",
            confidence="high",
            provider_metadata={
                "ocid": finding.resource_id,
                "compartment_id": "ocid1.compartment.x",
            },
            evidence={"metric": "idle"},
        )
    )
    db.commit()

    result = list_opportunities(
        db,
        OpportunityFilters(
            provider="oci",
            account_id="ocid1.tenancy.oc1..example",
            region="sa-saopaulo-1",
        ),
        page=1,
        page_size=50,
        sort="last_seen_at",
        order="desc",
    )
    assert result["total"] == 1
    item = result["items"][0]
    assert item["provider"] == "oci"
    assert item["account_id"] == "ocid1.tenancy.oc1..example"
    assert item["account_name"] is None
    assert item["legacy_account_id"] is None
    assert item["resource_type"] == "Compute Instance"
    assert item["provider_metadata"]["native_id"].startswith("ocid1.instance")


def test_global_resource_does_not_require_aws_region_or_scan(db):
    finding = _finding(
        opportunity_id="azure-global",
        provider="azure",
        account_id="00000000-0000-0000-0000-000000000001",
        region=None,
        resource_id="/subscriptions/example/resourceGroups/rg/providers/test/global",
        service="Resource Manager",
        resource_type="Global Resource",
    )
    db.add(finding)
    db.commit()
    assert finding.region is None
    assert finding.scan_id is None
    assert finding.account_id.startswith("00000000-")


def test_fingerprint_keeps_aws_v1_stable_and_separates_providers():
    aws = build_opportunity_fingerprint(
        provider="aws",
        account_id="123456789012",
        region="sa-east-1",
        scope="EC2",
        resource_id="i-abc",
        rule_id="ec2_stopped",
    )
    oci = build_opportunity_fingerprint(
        provider="oci",
        account_id="123456789012",
        region="sa-east-1",
        scope="EC2",
        resource_id="i-abc",
        rule_id="ec2_stopped",
    )
    assert aws == "1397112240f8c73de40af1f5f4e1fb8e4083939195a5de4c9541f292e1836390"
    assert oci != aws


def test_comparison_rejects_cross_provider_and_known_scope_mismatch():
    baseline = CollectionRun(
        id="baseline",
        provider="aws",
        account_id="same",
        scope={"regions": ["sa-east-1"]},
        started_at=NOW,
        finished_at=NOW,
        status="SUCCESS",
    )
    cross_provider = CollectionRun(
        id="oci-target",
        provider="oci",
        account_id="same",
        scope={"regions": ["sa-east-1"]},
        started_at=NOW + timedelta(days=1),
        finished_at=NOW + timedelta(days=1),
        status="SUCCESS",
    )
    with pytest.raises(CollectionComparisonError) as exc:
        validate_comparable_runs(baseline, cross_provider)
    assert exc.value.code == "DIFFERENT_PROVIDER"

    different_scope = CollectionRun(
        id="aws-target",
        provider="aws",
        account_id="same",
        scope={"regions": ["us-east-1"]},
        started_at=NOW + timedelta(days=1),
        finished_at=NOW + timedelta(days=1),
        status="SUCCESS",
    )
    with pytest.raises(CollectionComparisonError) as exc:
        validate_comparable_runs(baseline, different_scope)
    assert exc.value.code == "DIFFERENT_SCOPE"


def test_home_aggregates_multiple_providers_without_aws_account_rows(db):
    fixtures = [
        (
            "aws",
            "123456789012",
            "sa-east-1",
            "i-1",
            "EC2",
            "EC2 Instance",
        ),
        (
            "oci",
            "ocid1.tenancy.example",
            "sa-saopaulo-1",
            "ocid1.instance.example",
            "Compute",
            "Compute Instance",
        ),
    ]
    for index, (
        provider,
        account_id,
        region,
        resource_id,
        service,
        resource_type,
    ) in enumerate(fixtures):
        run = CollectionRun(
            id=f"run-{provider}",
            provider=provider,
            account_id=account_id,
            scope={"regions": [region]},
            started_at=NOW,
            finished_at=NOW + timedelta(minutes=1),
            status="SUCCESS",
        )
        finding = _finding(
            opportunity_id=f"opp-{provider}",
            provider=provider,
            account_id=account_id,
            region=region,
            resource_id=resource_id,
            service=service,
            resource_type=resource_type,
        )
        finding.estimated_monthly_savings = Decimal(str(10 + index * 5))
        db.add_all([run, finding])
        db.flush()
        db.add(
            OpportunityObservation(
                opportunity_id=finding.id,
                collection_run_id=run.id,
                observed_at=NOW,
                severity="medium",
                current_monthly_cost=Decimal("25"),
                estimated_monthly_savings=finding.estimated_monthly_savings,
                currency="USD",
                confidence="high",
                evidence={},
            )
        )
    db.commit()

    summary = dashboard_summary(db)
    assert summary["opportunities"]["open"] == 2
    assert {item["provider"] for item in summary["by_provider"]} == {"aws", "oci"}
    assert summary["financial"]["totals"] == [{"currency": "USD", "amount": Decimal("25")}]


def test_unknown_rule_evidence_does_not_claim_aws_source_for_oci():
    evidence = normalize_persisted_evidence(
        provider="oci",
        rule_key="oci_custom_rule",
        service="Compute",
        region="sa-saopaulo-1",
        resource_id="ocid1.instance.example",
        resource_name=None,
        title="OCI finding",
        description="Provider specific fixture",
        evidence={},
        current_monthly_cost=0,
        estimated_monthly_savings=0,
    )
    assert evidence["source"] == "OCI provider data"
