from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app import worker
from app.db.base import Base
from app.models.account import CloudAccount, OciAccountConfiguration
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.opportunity_observation import OpportunityObservation
from app.models.scan import Scan
from app.services.collection_executors import OciCollectionExecutor
from app.services.oci_auth import OciConnectionSnapshot
from app.services.oci_cloud_advisor_models import OciCloudAdvisorResult
from app.services.oci_discovery_models import (
    OciDiscoveredResource,
    OciDiscoveryResult,
)
from app.services.oci_monitoring_models import OciMonitoringResult
from app.services.oci_usage_models import OciUsageIssue, OciUsageResult
from app.services.scan_queue import queue_manual_collection

TENANCY = "ocid1.tenancy.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
VOLUME = "ocid1.volume.oc1.sa-saopaulo-1.bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
COMPARTMENT = "ocid1.compartment.oc1..cccccccccccccccccccccccccccccccc"


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'oci-executor.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _account(db: Session) -> CloudAccount:
    account = CloudAccount(
        provider="oci",
        native_account_id=TENANCY,
        name="OCI Executor Test",
        enabled=True,
        connection_status="connected",
    )
    account.oci_configuration = OciAccountConfiguration(
        user_ocid="ocid1.user.oc1..dddddddddddddddddddddddddddddddd",
        fingerprint="aa:bb:cc:dd",
        region="sa-saopaulo-1",
        scope_regions=["sa-saopaulo-1"],
        compartment_ocids=[COMPARTMENT],
        include_root_compartment=True,
        include_subcompartments=True,
        private_key_ciphertext="encrypted-fixture",
        credential_key_version="v1",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _snapshot(account: CloudAccount) -> OciConnectionSnapshot:
    return OciConnectionSnapshot(
        cloud_account_id=account.id,
        configuration_revision=1,
        tenancy_ocid=TENANCY,
        user_ocid="ocid1.user.oc1..dddddddddddddddddddddddddddddddd",
        fingerprint="aa:bb:cc:dd",
        region="sa-saopaulo-1",
        scope_regions=("sa-saopaulo-1",),
        compartment_ocids=(COMPARTMENT,),
        include_root_compartment=True,
        include_subcompartments=True,
        private_key_pem="secret-private-key-fixture",
        private_key_password="secret-passphrase-fixture",
    )


def _datasets(*, usage_error: bool = False):
    now = datetime.now(UTC)
    discovery = OciDiscoveryResult(
        status="success",
        resources=[
            OciDiscoveredResource(
                provider="oci",
                resource_id=VOLUME,
                resource_type="block_volume",
                name="unused-volume",
                region="sa-saopaulo-1",
                compartment_id=COMPARTMENT,
                lifecycle_state="AVAILABLE",
                sources=["block_storage_api"],
                attributes={
                    "attachment_coverage": "complete",
                    "attachment_count": 0,
                    "size_in_gbs": 50,
                },
            )
        ],
        relationships=[],
        regions_scanned=("sa-saopaulo-1",),
        compartments_scanned=(COMPARTMENT,),
        observed_counts_by_type={
            "compute_instance": 0,
            "block_volume": 1,
            "boot_volume": 0,
            "public_ip": 0,
        },
        counts_by_type={
            "compute_instance": 0,
            "block_volume": 1,
            "boot_volume": 0,
            "public_ip": 0,
        },
        warnings=[],
        errors=[],
        started_at=now,
        completed_at=now,
    )
    advisor = OciCloudAdvisorResult(
        status="success",
        recommendations=[],
        resource_actions=[],
        recommendation_count=0,
        resource_action_count=0,
        warnings=[],
        errors=[],
        started_at=now,
        completed_at=now,
        coverage={"recommendations": True, "resource_actions": True},
        pages={"recommendations": 1, "resource_actions": 1},
    )
    usage_issue = OciUsageIssue(
        category="not_authorized_or_not_found",
        source="usage_api",
        operation="resource_cost",
        message="OCI Usage API is not authorized for this principal",
        fatal=False,
    )
    usage = OciUsageResult(
        status="partial" if usage_error else "success",
        period_start=now - timedelta(days=30),
        period_end=now,
        records=[],
        sku_usage_records=[],
        totals_by_currency={},
        warnings=[],
        errors=[usage_issue] if usage_error else [],
        coverage={
            "scope": True,
            "resource_cost": not usage_error,
            "sku_usage": not usage_error,
        },
        pages={"resource_cost": 0, "sku_usage": 0},
        request_count=1,
        started_at=now,
        completed_at=now,
    )
    monitoring = OciMonitoringResult(
        status="success",
        period_start=now - timedelta(days=30),
        period_end=now,
        interval="1h",
        series=[],
        resources=[],
        orphan_series=[],
        warnings=[],
        errors=[],
        coverage={"scope": True, "compute_metrics": True},
        request_count=0,
        started_at=now,
        completed_at=now,
    )
    return discovery, advisor, usage, monitoring


def _patch_pipeline(monkeypatch, account: CloudAccount, *, usage_error: bool = False):
    snapshot = _snapshot(account)
    discovery, advisor, usage, monitoring = _datasets(usage_error=usage_error)
    calls: list[str] = []

    def resolve(_db, cloud_account_id):
        calls.append("credentials")
        assert cloud_account_id == account.id
        return snapshot

    def discover(_service, received_snapshot):
        calls.append("discovery")
        assert received_snapshot is snapshot
        return discovery

    def collect_advisor(_service, received_snapshot, *, discovery):
        calls.append("advisor")
        assert received_snapshot is snapshot
        assert discovery is not None
        return advisor

    def collect_usage(_service, _db, cloud_account_id, *, inventory, **_kwargs):
        calls.append("usage")
        assert cloud_account_id == account.id
        assert inventory is discovery
        return usage

    def collect_monitoring(_service, _db, cloud_account_id, *, inventory, **_kwargs):
        calls.append("monitoring")
        assert cloud_account_id == account.id
        assert inventory is discovery
        return monitoring

    monkeypatch.setattr(
        "app.services.collection_executors.resolve_oci_signing_credentials",
        resolve,
    )
    monkeypatch.setattr(
        "app.services.collection_executors.OciDiscoveryService.discover",
        discover,
    )
    monkeypatch.setattr(
        "app.services.collection_executors.OciCloudAdvisorService.collect",
        collect_advisor,
    )
    monkeypatch.setattr(
        "app.services.collection_executors.OciUsageService.collect_account",
        collect_usage,
    )
    monkeypatch.setattr(
        "app.services.collection_executors.OciMonitoringService.collect_account",
        collect_monitoring,
    )
    return calls


def test_oci_executor_reuses_one_collection_dataset_and_runs_analyzers(db, monkeypatch):
    account = _account(db)
    calls = _patch_pipeline(monkeypatch, account)
    scan = Scan(cloud_account_id=account.id, account_id=None, status="running")
    db.add(scan)
    db.commit()

    result = OciCollectionExecutor().execute(db, account, scan)

    assert calls == ["credentials", "discovery", "advisor", "usage", "monitoring"]
    assert result.resources_analyzed == 1
    assert result.collector_errors == []
    assert {finding.rule_key for finding in result.findings} >= {
        "oci_block_volume_unattached",
        "oci_untagged_resource",
    }
    finding = next(
        item for item in result.findings if item.rule_key == "oci_block_volume_unattached"
    )
    assert finding.resource_id == VOLUME
    assert finding.provider_metadata["provider"] == "oci"
    assert "secret-private-key-fixture" not in str(finding.evidence)
    assert "secret-passphrase-fixture" not in str(finding.evidence)


def test_oci_executor_keeps_service_authorization_failure_partial(db, monkeypatch):
    account = _account(db)
    _patch_pipeline(monkeypatch, account, usage_error=True)
    scan = Scan(cloud_account_id=account.id, account_id=None, status="running")
    db.add(scan)
    db.commit()

    result = OciCollectionExecutor().execute(db, account, scan)

    assert result.findings
    assert result.collector_errors
    executor = OciCollectionExecutor()
    executor.mark_connection_failure(account, "OCI Usage API is not authorized for this principal")
    assert account.connection_status == "connected"


def test_oci_manual_scan_persists_collection_opportunity_and_observation(db, monkeypatch):
    account = _account(db)
    _patch_pipeline(monkeypatch, account)
    monkeypatch.setattr(worker, "rebuild_account_summary", lambda *_args, **_kwargs: None)

    first = queue_manual_collection(db, account)
    db.commit()
    claimed = worker.claim_scan(db)
    assert claimed.id == first.id
    worker.execute_scan(db, claimed)

    first_scan = db.get(Scan, first.id)
    first_run = db.scalar(select(CollectionRun).where(CollectionRun.scan_id == first.id))
    assert first_scan.account_id is None
    assert first_scan.status == "completed"
    assert first_run.provider == "oci"
    assert first_run.account_id == TENANCY
    assert first_run.status == CollectionRunStatus.SUCCESS
    assert first_run.resources_analyzed == 1
    assert first_run.opportunities_found >= 1
    assert "private_key" not in str(first_run.scope).lower()
    assert "passphrase" not in str(first_run.scope).lower()

    opportunities_after_first = db.scalar(select(func.count()).select_from(Finding))
    observations_after_first = db.scalar(select(func.count()).select_from(OpportunityObservation))

    second = queue_manual_collection(db, account)
    db.commit()
    claimed_second = worker.claim_scan(db)
    assert claimed_second.id == second.id
    worker.execute_scan(db, claimed_second)

    assert db.scalar(select(func.count()).select_from(Finding)) == opportunities_after_first
    assert (
        db.scalar(select(func.count()).select_from(OpportunityObservation))
        == observations_after_first + opportunities_after_first
    )
    assert db.scalar(select(func.count()).select_from(CollectionRun)) == 2


def test_oci_treated_opportunity_is_not_reopened_on_next_collection(db, monkeypatch):
    account = _account(db)
    _patch_pipeline(monkeypatch, account)
    monkeypatch.setattr(worker, "rebuild_account_summary", lambda *_args, **_kwargs: None)

    queue_manual_collection(db, account)
    db.commit()
    claimed = worker.claim_scan(db)
    worker.execute_scan(db, claimed)

    finding = db.scalar(select(Finding).where(Finding.rule_key == "oci_block_volume_unattached"))
    finding.status = "treated"
    finding.treated_at = datetime.now(UTC) - timedelta(seconds=1)
    finding.needs_review = False
    db.commit()

    queue_manual_collection(db, account)
    db.commit()
    claimed_second = worker.claim_scan(db)
    worker.execute_scan(db, claimed_second)
    db.refresh(finding)

    assert finding.status == "treated"
    assert finding.needs_review is True
