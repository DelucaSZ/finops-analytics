from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.collection_run import CollectionRun
from app.models.collection_scope_execution import (
    CollectionScopeExecution,
    CollectionScopeExecutionStatus,
)
from app.models.finding import Finding, OpportunityPresenceStatus
from app.services.opportunity_reconciliation import (
    ALL_REGIONS_SCOPE,
    reconcile_opportunity_presence,
)

START = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def test_all_regions_success_scope_reconciles_concrete_region_finding():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            run = CollectionRun(
                id="run-global",
                provider="aws",
                account_id="123456789012",
                scope={"regions": ["sa-east-1"]},
                started_at=START + timedelta(hours=1),
                status="RUNNING",
            )
            finding = Finding(
                id="finding-global",
                fingerprint="a" * 64,
                provider="aws",
                account_id="123456789012",
                rule_key="cost_growth_anomaly",
                service="Amazon EC2",
                region="us-east-1",
                resource_id="Amazon EC2|us-east-1",
                title="Cost growth",
                description="test",
                evidence={},
                first_seen_at=START,
                last_seen_at=START,
            )
            scope = CollectionScopeExecution(
                collection_run_id=run.id,
                provider=run.provider,
                account_id=run.account_id,
                region=ALL_REGIONS_SCOPE,
                rule_key="cost_growth_anomaly",
                status=CollectionScopeExecutionStatus.SUCCESS.value,
                started_at=run.started_at,
                finished_at=run.started_at + timedelta(minutes=1),
            )
            db.add_all([run, finding, scope])
            db.flush()

            reconcile_opportunity_presence(db, run, [scope], missing_threshold=3)

            assert finding.presence_status == OpportunityPresenceStatus.MISSING.value
            assert finding.missing_count == 1
    finally:
        engine.dispose()
