from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.collection_run import CollectionRun
from app.models.dashboard_summary import DashboardAccountSummary
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.services.dashboard_aggregation import (
    backfill_dashboard_summaries,
    rebuild_account_summary,
    summary_matches_source,
)

START = datetime(2026, 9, 1, tzinfo=UTC)


def _finding(provider: str, account_id: str, suffix: str) -> Finding:
    return Finding(
        id=f"opp-{provider}-{suffix}",
        fingerprint=hashlib.sha256(f"{provider}:{account_id}:{suffix}".encode()).hexdigest(),
        provider=provider,
        account_id=account_id,
        rule_key="ebs_unattached",
        service="EBS",
        region="sa-east-1" if provider == "aws" else None,
        resource_id=f"resource-{suffix}",
        title=f"Opportunity {suffix}",
        description="Test",
        evidence={},
        current_monthly_cost=Decimal("20"),
        estimated_monthly_savings=Decimal("10"),
        currency="USD",
        confidence="high",
        severity="high",
        status="open",
        first_seen_at=START,
        last_seen_at=START,
    )


def _observation(opportunity_id: str, run_id: str) -> OpportunityObservation:
    return OpportunityObservation(
        opportunity_id=opportunity_id,
        collection_run_id=run_id,
        observed_at=START,
        severity="high",
        current_monthly_cost=Decimal("20"),
        estimated_monthly_savings=Decimal("10"),
        currency="USD",
        confidence="high",
        evidence={},
    )


def test_summary_is_idempotent_and_provider_account_identity_isolated(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'summary.db'}")
    Base.metadata.create_all(engine)
    shared_account_id = "shared-native-id"

    with Session(engine) as db:
        aws_run = CollectionRun(
            id="run-aws",
            provider="aws",
            account_id=shared_account_id,
            started_at=START,
            finished_at=START + timedelta(minutes=1),
            status="SUCCESS",
            scope={"regions": ["sa-east-1"]},
        )
        oci_run = CollectionRun(
            id="run-oci",
            provider="oci",
            account_id=shared_account_id,
            started_at=START,
            finished_at=START + timedelta(minutes=1),
            status="SUCCESS",
            scope={"regions": ["sa-saopaulo-1"]},
        )
        aws_finding = _finding("aws", shared_account_id, "aws")
        oci_finding = _finding("oci", shared_account_id, "oci")
        db.add_all(
            [
                aws_run,
                oci_run,
                aws_finding,
                oci_finding,
                _observation(aws_finding.id, aws_run.id),
                _observation(oci_finding.id, oci_run.id),
            ]
        )
        db.commit()

        assert backfill_dashboard_summaries(db) == 2
        db.commit()
        assert (
            db.scalar(select(func.count()).select_from(DashboardAccountSummary))
            == 2
        )

        rebuild_account_summary(
            db,
            provider="aws",
            account_id=shared_account_id,
            collection_run_id=aws_run.id,
        )
        rebuild_account_summary(
            db,
            provider="aws",
            account_id=shared_account_id,
            collection_run_id=aws_run.id,
        )
        db.commit()

        assert (
            db.scalar(select(func.count()).select_from(DashboardAccountSummary))
            == 2
        )
        assert db.get(
            DashboardAccountSummary,
            ("aws", shared_account_id),
        ).collection_run_id == "run-aws"
        assert db.get(
            DashboardAccountSummary,
            ("oci", shared_account_id),
        ).collection_run_id == "run-oci"
        assert summary_matches_source(
            db,
            provider="aws",
            account_id=shared_account_id,
        )
        assert summary_matches_source(
            db,
            provider="oci",
            account_id=shared_account_id,
        )
    engine.dispose()


def test_failed_collection_does_not_advance_current_summary(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'failed-summary.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        good = CollectionRun(
            id="run-good",
            provider="aws",
            account_id="123456789012",
            started_at=START,
            finished_at=START + timedelta(minutes=1),
            status="SUCCESS",
        )
        failed = CollectionRun(
            id="run-failed",
            provider="aws",
            account_id="123456789012",
            started_at=START + timedelta(days=1),
            finished_at=START + timedelta(days=1, minutes=1),
            status="FAILED",
        )
        finding = _finding("aws", "123456789012", "one")
        db.add_all([good, failed, finding, _observation(finding.id, good.id)])
        db.commit()

        rebuild_account_summary(
            db,
            provider="aws",
            account_id="123456789012",
        )
        db.commit()

        summary = db.get(
            DashboardAccountSummary,
            ("aws", "123456789012"),
        )
        assert summary.collection_run_id == "run-good"
        assert summary.has_baseline is False
        assert summary.new_count == 0
    engine.dispose()
