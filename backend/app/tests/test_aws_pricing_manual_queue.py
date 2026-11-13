"""Task 28.5 queue worker tests without any AWS network calls."""

from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.db.base import Base
from app.models.aws_pricing import AwsPricingSyncRequest
from app.services.aws_pricing_manual_queue import AwsPricingManualQueue


def test_manual_queue_runs_async_worker_contract_and_preserves_request(monkeypatch):
    monkeypatch.setenv("AVEN_AWS_PRICING_IMPORT_ENABLED", "1")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    calls = []

    class StubSynchronizer:
        def run_unit(self, service, region, *, trigger, dry_run, force):
            calls.append((service, region, trigger, dry_run, force))
            return {"status": "validated" if dry_run else "published"}

    with sessions.begin() as db:
        request = AwsPricingSyncRequest(
            service_code="AmazonEC2", region_code="sa-east-1",
            requested_by="admin-test", status="queued", dry_run=True,
            force=False, requested_at=datetime.now(UTC),
        )
        db.add(request)
        db.flush()
        request_id = request.id
    queue = AwsPricingManualQueue(session_factory=sessions, synchronizer=StubSynchronizer())
    assert queue.run_next()["status"] == "validated"
    assert queue.run_next() is None
    assert calls == [("AmazonEC2", "sa-east-1", "manual", True, False)]
    with sessions() as db:
        stored = db.get(AwsPricingSyncRequest, request_id)
        assert stored.status == "completed"
        assert stored.finished_at is not None
        assert stored.result == {"status": "validated"}
    engine.dispose()


def test_manual_queue_stays_disabled_without_optin(monkeypatch):
    monkeypatch.delenv("AVEN_AWS_PRICING_IMPORT_ENABLED", raising=False)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as db:
        db.add(
            AwsPricingSyncRequest(
                service_code="AmazonVPC", region_code="sa-east-1",
                requested_by="admin-test", status="queued", dry_run=False,
                force=False, requested_at=datetime.now(UTC),
            )
        )
    queue = AwsPricingManualQueue(session_factory=sessions)
    assert queue.run_next() is None
    with sessions() as db:
        assert db.scalar(select(AwsPricingSyncRequest.status)) == "queued"
    engine.dispose()
