from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.api.routes import rds_reservations_pipeline as pipeline_routes
from app.core.security import require_admin
from app.db.base import Base
from app.db.session import get_db
from app.models.rds_coverage import RdsReservationCoverageRun
from app.services import rds_reservations_pipeline as pipeline

NOW = datetime(2026, 10, 30, 18, 0, tzinfo=UTC)
SNAPSHOT = NOW - timedelta(minutes=1)


def _db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


@dataclass
class FakeOpportunityResult:
    coverage_run_id: int
    created: int = 3
    updated: int = 1
    resolved: int = 0

    def to_dict(self):
        return {
            "coverage_run_id": self.coverage_run_id,
            "created": self.created,
            "updated": self.updated,
            "resolved": self.resolved,
        }


def _successful_inventory(_db: Session, **_kwargs):
    return {
        "rds_instances_found": 18,
        "reservations_found": 4,
        "errors": [],
        "duration_ms": 25,
    }


def _successful_coverage(db: Session, *, run: RdsReservationCoverageRun, **_kwargs):
    run.status = "COMPLETED"
    run.pipeline_stage = "coverage"
    run.instances_analyzed = 18
    run.reservations_analyzed = 4
    run.fully_covered = 8
    run.partially_covered = 2
    run.uncovered = 8
    run.billing_validation_status = "NOT_AVAILABLE"
    run.completed_at = NOW
    db.commit()
    return run


def _patch_success(monkeypatch):
    monkeypatch.setattr(pipeline, "collect_rds_inventory", _successful_inventory)
    monkeypatch.setattr(
        pipeline,
        "effective_rds_inventory_snapshot_at",
        lambda db, fallback=None: SNAPSHOT,
    )
    monkeypatch.setattr(pipeline, "run_rds_reservation_coverage", _successful_coverage)
    monkeypatch.setattr(
        pipeline,
        "generate_rds_reservation_opportunities",
        lambda db, *, coverage_run_id, now=None: FakeOpportunityResult(coverage_run_id),
    )


def test_complete_pipeline_runs_inventory_coverage_and_opportunities(monkeypatch) -> None:
    db = _db()
    _patch_success(monkeypatch)

    result = pipeline.refresh_rds_reservations(db, validate_billing=True, now=NOW)

    assert result["status"] == "COMPLETED"
    assert result["inventory"]["status"] == "COMPLETED"
    assert result["inventory"]["instances"] == 18
    assert result["coverage"]["status"] == "COMPLETED"
    assert result["coverage"]["fully_covered"] == 8
    assert result["coverage"]["billing_validation_status"] == "NOT_AVAILABLE"
    assert result["opportunities"]["status"] == "COMPLETED"
    assert result["opportunities"]["created"] == 3
    run = db.get(RdsReservationCoverageRun, result["coverage_run_id"])
    assert run is not None
    assert run.inventory_snapshot_at in {SNAPSHOT.replace(tzinfo=None), SNAPSHOT}


def test_inventory_failure_skips_coverage(monkeypatch) -> None:
    db = _db()
    called = {"coverage": False}
    monkeypatch.setattr(
        pipeline,
        "collect_rds_inventory",
        lambda _db, **_kwargs: {
            "rds_instances_found": 2,
            "reservations_found": 1,
            "errors": ["describe_db_instances failed"],
            "duration_ms": 10,
        },
    )

    def forbidden_coverage(*_args, **_kwargs):
        called["coverage"] = True
        raise AssertionError("coverage must not execute after inventory failure")

    monkeypatch.setattr(pipeline, "run_rds_reservation_coverage", forbidden_coverage)
    result = pipeline.refresh_rds_reservations(db, now=NOW)

    assert result["status"] == "FAILED"
    assert result["inventory"]["status"] == "FAILED"
    assert result["coverage"]["status"] == "NOT_RUN"
    assert not called["coverage"]


def test_opportunity_failure_preserves_completed_coverage(monkeypatch) -> None:
    db = _db()
    _patch_success(monkeypatch)

    def fail_opportunities(*_args, **_kwargs):
        raise RuntimeError("opportunity generation unavailable")

    monkeypatch.setattr(pipeline, "generate_rds_reservation_opportunities", fail_opportunities)
    result = pipeline.refresh_rds_reservations(db, now=NOW)

    assert result["status"] == "COMPLETED_WITH_WARNINGS"
    assert result["coverage"]["status"] == "COMPLETED"
    assert result["opportunities"]["status"] == "FAILED"
    run = db.get(RdsReservationCoverageRun, result["coverage_run_id"])
    assert run is not None
    assert run.status == "COMPLETED"
    assert run.opportunity_status == "FAILED"


def test_repeated_execution_creates_controlled_independent_runs(monkeypatch) -> None:
    db = _db()
    _patch_success(monkeypatch)

    first = pipeline.refresh_rds_reservations(db, now=NOW)
    second = pipeline.refresh_rds_reservations(db, now=NOW + timedelta(minutes=5))

    assert first["coverage_run_id"] != second["coverage_run_id"]
    assert db.query(RdsReservationCoverageRun).count() == 2
    assert all(
        run.status == "COMPLETED"
        for run in db.query(RdsReservationCoverageRun).order_by(RdsReservationCoverageRun.id).all()
    )


def test_operational_status_uses_last_successful_run_when_newest_failed() -> None:
    db = _db()
    successful = RdsReservationCoverageRun(
        started_at=NOW - timedelta(hours=2),
        completed_at=NOW - timedelta(hours=2) + timedelta(minutes=1),
        inventory_snapshot_at=NOW - timedelta(hours=2),
        status="COMPLETED",
        pipeline_stage="completed",
        inventory_status="COMPLETED",
        opportunity_status="COMPLETED",
        billing_validation_status="NOT_AVAILABLE",
        reconciliation_status="NOT_AVAILABLE",
    )
    failed = RdsReservationCoverageRun(
        started_at=NOW - timedelta(minutes=10),
        completed_at=NOW - timedelta(minutes=9),
        inventory_snapshot_at=NOW - timedelta(minutes=10),
        status="FAILED",
        pipeline_stage="inventory",
        inventory_status="FAILED",
        opportunity_status="NOT_RUN",
        billing_validation_status="NOT_AVAILABLE",
        reconciliation_status="NOT_AVAILABLE",
        inventory_error_detail="collection failed",
    )
    db.add_all([successful, failed])
    db.commit()

    status = pipeline.get_rds_reservations_operational_status(db, now=NOW)

    assert status["pipeline_status"] == "FAILED"
    assert status["coverage_status"] == "NOT_RUN"
    assert status["coverage_run_id"] == successful.id
    assert status["last_successful_coverage_run_at"] is not None


def test_operational_status_detects_stale_snapshot(monkeypatch) -> None:
    db = _db()
    monkeypatch.setattr(
        "app.services.rds_reservation_freshness.settings.rds_reservation_inventory_freshness_hours",
        24,
    )
    run = RdsReservationCoverageRun(
        started_at=NOW - timedelta(hours=30),
        completed_at=NOW - timedelta(hours=30) + timedelta(minutes=1),
        inventory_snapshot_at=NOW - timedelta(hours=30),
        status="COMPLETED",
        pipeline_stage="completed",
        inventory_status="COMPLETED",
        opportunity_status="COMPLETED",
        billing_validation_status="AVAILABLE",
        reconciliation_status="MATCH",
    )
    db.add(run)
    db.commit()

    status = pipeline.get_rds_reservations_operational_status(db, now=NOW)

    assert status["data_freshness"] == "STALE"
    assert status["pipeline_status"] == "STALE"


def test_operational_status_without_runs_is_never_executed() -> None:
    db = _db()
    status = pipeline.get_rds_reservations_operational_status(db, now=NOW)
    assert status["pipeline_status"] == "NEVER_EXECUTED"
    assert status["coverage_run_id"] is None
    assert status["data_freshness"] == "UNKNOWN"


def _api_client(db: Session) -> TestClient:
    app = FastAPI()
    app.include_router(pipeline_routes.router, prefix="/api/v1")

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_admin] = lambda: object()
    return TestClient(app)


def test_operational_status_api_returns_never_executed() -> None:
    db = _db()
    response = _api_client(db).get("/api/v1/rds/reservations/operational-status")
    assert response.status_code == 200
    assert response.json()["pipeline_status"] == "NEVER_EXECUTED"


def test_refresh_api_returns_pipeline_summary(monkeypatch) -> None:
    db = _db()
    monkeypatch.setattr(
        pipeline_routes,
        "refresh_rds_reservations",
        lambda db, cloud_account_id=None, validate_billing=True: {
            "status": "COMPLETED",
            "coverage_run_id": 42,
            "inventory": {"status": "COMPLETED"},
            "coverage": {"status": "COMPLETED"},
            "opportunities": {"status": "COMPLETED"},
            "data_freshness": "FRESH",
        },
    )
    response = _api_client(db).post("/api/v1/rds/reservations/refresh?validate_billing=false")
    assert response.status_code == 200
    assert response.json()["coverage_run_id"] == 42


def test_refresh_api_returns_conflict_when_pipeline_is_running(monkeypatch) -> None:
    db = _db()

    def busy(*_args, **_kwargs):
        raise pipeline.RdsReservationsPipelineBusy("already running")

    monkeypatch.setattr(pipeline_routes, "refresh_rds_reservations", busy)
    response = _api_client(db).post("/api/v1/rds/reservations/refresh")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "RDS_RESERVATIONS_REFRESH_RUNNING"
