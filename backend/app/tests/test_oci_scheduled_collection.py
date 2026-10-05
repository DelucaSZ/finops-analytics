from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app import worker
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.services.scan_queue import queue_manual_collection
from app.tests.test_oci_collection_executor import _account, _patch_pipeline


def _run_due_scheduled_oci(db, monkeypatch):
    account = _account(db)
    _patch_pipeline(monkeypatch, account)
    monkeypatch.setattr(worker, "rebuild_account_summary", lambda *_args, **_kwargs: None)
    account.schedule_enabled = True
    account.scan_interval_hours = 24
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()

    worker.enqueue_due_scans(db)
    scan = db.scalar(select(Scan))
    assert scan is not None
    assert scan.trigger == "scheduled"
    assert scan.cloud_account_id == account.id
    assert scan.account_id is None

    claimed = worker.claim_scan(db)
    assert claimed is not None
    assert claimed.id == scan.id
    worker.execute_scan(db, claimed)
    return account, db.get(Scan, scan.id)


def test_scheduled_oci_runs_through_common_worker_and_persists_pipeline(db, monkeypatch):
    account, scan = _run_due_scheduled_oci(db, monkeypatch)

    run = db.scalar(select(CollectionRun).where(CollectionRun.scan_id == scan.id))
    assert scan.status == "completed"
    assert run is not None
    assert run.provider == "oci"
    assert run.account_id == account.native_account_id
    assert run.status == CollectionRunStatus.SUCCESS
    assert run.resources_analyzed == 1
    assert run.opportunities_found >= 1
    assert db.scalar(select(func.count()).select_from(Finding)) >= 1
    assert db.scalar(select(func.count()).select_from(OpportunityObservation)) >= 1
    assert "private_key" not in str(run.scope).lower()
    assert "passphrase" not in str(run.scope).lower()


def test_manual_then_scheduled_oci_reuses_opportunities_and_adds_observations(db, monkeypatch):
    account = _account(db)
    _patch_pipeline(monkeypatch, account)
    monkeypatch.setattr(worker, "rebuild_account_summary", lambda *_args, **_kwargs: None)

    manual = queue_manual_collection(db, account)
    db.commit()
    claimed_manual = worker.claim_scan(db)
    assert claimed_manual.id == manual.id
    worker.execute_scan(db, claimed_manual)

    opportunity_count = db.scalar(select(func.count()).select_from(Finding))
    observation_count = db.scalar(select(func.count()).select_from(OpportunityObservation))
    assert opportunity_count >= 1

    account.schedule_enabled = True
    account.scan_interval_hours = 24
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)

    scheduled = db.scalar(
        select(Scan).where(Scan.trigger == "scheduled", Scan.cloud_account_id == account.id)
    )
    assert scheduled is not None
    claimed_scheduled = worker.claim_scan(db)
    assert claimed_scheduled.id == scheduled.id
    worker.execute_scan(db, claimed_scheduled)

    assert db.scalar(select(func.count()).select_from(Finding)) == opportunity_count
    assert (
        db.scalar(select(func.count()).select_from(OpportunityObservation))
        == observation_count + opportunity_count
    )
    assert db.scalar(select(func.count()).select_from(CollectionRun)) == 2


def test_scheduled_oci_preserves_treated_and_rejected_lifecycle(db, monkeypatch):
    account = _account(db)
    _patch_pipeline(monkeypatch, account)
    monkeypatch.setattr(worker, "rebuild_account_summary", lambda *_args, **_kwargs: None)

    queue_manual_collection(db, account)
    db.commit()
    worker.execute_scan(db, worker.claim_scan(db))

    findings = list(db.scalars(select(Finding).order_by(Finding.rule_key)))
    assert findings
    findings[0].status = "treated"
    findings[0].treated_at = datetime.now(UTC) - timedelta(seconds=1)
    findings[0].needs_review = False
    if len(findings) > 1:
        findings[1].status = "rejected"
        findings[1].rejected_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    account.schedule_enabled = True
    account.scan_interval_hours = 24
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)
    worker.execute_scan(db, worker.claim_scan(db))

    db.refresh(findings[0])
    assert findings[0].status == "treated"
    assert findings[0].needs_review is True
    if len(findings) > 1:
        db.refresh(findings[1])
        assert findings[1].status == "rejected"
