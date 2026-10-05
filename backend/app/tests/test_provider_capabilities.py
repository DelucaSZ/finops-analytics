from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app import worker
from app.db.base import Base
from app.models.account import AwsAccount, CloudAccount, OciAccountConfiguration
from app.models.collection_run import CollectionRun
from app.models.scan import Scan
from app.services.collection_executors import (
    CollectionExecutorUnavailable,
    get_collection_executor,
    has_collection_executor,
)
from app.services.provider_capabilities import (
    ProviderOperation,
    UnsupportedProviderOperation,
    get_provider_capabilities,
    providers_supporting,
)
from app.services.scan_queue import CollectionPreconditionError, queue_manual_collection


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'provider-capabilities.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _aws_account(db: Session) -> AwsAccount:
    account = AwsAccount(
        name="AWS Test",
        aws_account_id="123456789012",
        role_arn="arn:aws:iam::123456789012:role/DeepOps",
        external_id="test-external-id-1234",
        regions=["sa-east-1"],
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _oci_account(db: Session, *, enabled: bool = True) -> CloudAccount:
    account = CloudAccount(
        provider="oci",
        native_account_id="ocid1.tenancy.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        name="OCI Test",
        enabled=enabled,
        connection_status="connected",
    )
    account.oci_configuration = OciAccountConfiguration(
        user_ocid="ocid1.user.oc1..bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        fingerprint="aa:bb:cc:dd",
        region="sa-saopaulo-1",
        scope_regions=["sa-saopaulo-1"],
        compartment_ocids=["ocid1.compartment.oc1..cccccccccccccccccccccccccccccccc"],
        include_root_compartment=True,
        include_subcompartments=True,
        private_key_ciphertext="encrypted-fixture",
        credential_key_version="v1",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def test_provider_capability_matrix_enables_manual_and_scheduled_oci():
    aws = get_provider_capabilities("aws")
    oci = get_provider_capabilities("oci")
    azure = get_provider_capabilities("azure")
    gcp = get_provider_capabilities("gcp")

    assert aws.manual_collection is True
    assert aws.scheduling is True
    assert aws.finops_policies is True

    assert oci.registration is True
    assert oci.editing is True
    assert oci.connection_test is True
    assert oci.manual_collection is True
    assert oci.scheduling is True
    assert oci.finops_policies is False

    assert azure.manual_collection is False
    assert azure.scheduling is False
    assert gcp.manual_collection is False
    assert gcp.scheduling is False
    assert providers_supporting(ProviderOperation.SCHEDULING) == ("aws", "oci")

    with pytest.raises(UnsupportedProviderOperation, match="Unknown cloud provider"):
        get_provider_capabilities("unknown-cloud")


def test_manual_aws_collection_populates_both_account_identifiers(db):
    account = _aws_account(db)

    scan = queue_manual_collection(db, account.cloud_account)

    assert scan.account_id == account.id
    assert scan.cloud_account_id == account.cloud_account_id


def test_manual_oci_collection_uses_only_cloud_account_identity(db):
    account = _oci_account(db)

    scan = queue_manual_collection(db, account)

    assert scan.cloud_account_id == account.id
    assert scan.account_id is None
    assert scan.trigger == "manual"
    assert db.scalar(select(func.count()).select_from(AwsAccount)) == 0


def test_disabled_oci_collection_is_rejected_without_creating_scan(db):
    account = _oci_account(db, enabled=False)

    with pytest.raises(CollectionPreconditionError, match="disabled"):
        queue_manual_collection(db, account)

    assert db.scalar(select(func.count()).select_from(Scan)) == 0


def test_manual_oci_duplicate_pending_and_running_use_cloud_account_identity(db):
    account = _oci_account(db)
    first = queue_manual_collection(db, account)
    db.commit()

    with pytest.raises(CollectionPreconditionError, match="already pending or running"):
        queue_manual_collection(db, account)

    first.status = "running"
    db.commit()
    with pytest.raises(CollectionPreconditionError, match="already pending or running"):
        queue_manual_collection(db, account)


def test_scheduler_reads_cloud_account_and_queues_due_aws(db):
    account = _aws_account(db)
    due_at = datetime.now(UTC) - timedelta(hours=1)
    account.cloud_account.schedule_enabled = True
    account.cloud_account.scan_interval_hours = 24
    account.cloud_account.next_scan_at = due_at
    db.commit()

    worker.enqueue_due_scans(db)

    scan = db.scalar(select(Scan))
    assert scan is not None
    assert scan.trigger == "scheduled"
    assert scan.cloud_account_id == account.cloud_account_id
    assert scan.account_id == account.id
    persisted_next = account.cloud_account.next_scan_at
    assert persisted_next is not None
    if persisted_next.tzinfo is None:
        persisted_next = persisted_next.replace(tzinfo=UTC)
    assert persisted_next > due_at
    assert account.next_scan_at == account.cloud_account.next_scan_at


def test_scheduler_queues_due_oci_without_legacy_aws_identity(db):
    account = _oci_account(db)
    due_at = datetime.now(UTC) - timedelta(hours=1)
    account.schedule_enabled = True
    account.scan_interval_hours = 24
    account.next_scan_at = due_at
    db.commit()

    worker.enqueue_due_scans(db)

    scan = db.scalar(select(Scan))
    assert scan is not None
    assert scan.trigger == "scheduled"
    assert scan.cloud_account_id == account.id
    assert scan.account_id is None
    assert db.scalar(select(func.count()).select_from(AwsAccount)) == 0
    persisted_next = account.next_scan_at
    assert persisted_next is not None
    if persisted_next.tzinfo is None:
        persisted_next = persisted_next.replace(tzinfo=UTC)
    assert persisted_next > due_at


def test_scheduler_ignores_disabled_future_or_schedule_disabled_oci(db):
    account = _oci_account(db)
    account.schedule_enabled = False
    account.scan_interval_hours = 24
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()

    worker.enqueue_due_scans(db)
    assert db.scalar(select(func.count()).select_from(Scan)) == 0

    account.schedule_enabled = True
    account.next_scan_at = datetime.now(UTC) + timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)
    assert db.scalar(select(func.count()).select_from(Scan)) == 0

    account.enabled = False
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)
    assert db.scalar(select(func.count()).select_from(Scan)) == 0


def test_scheduler_ignores_disabled_or_future_aws(db):
    account = _aws_account(db)
    account.cloud_account.schedule_enabled = True
    account.cloud_account.scan_interval_hours = 24
    account.cloud_account.next_scan_at = datetime.now(UTC) + timedelta(hours=1)
    db.commit()

    worker.enqueue_due_scans(db)
    assert db.scalar(select(func.count()).select_from(Scan)) == 0

    account.cloud_account.enabled = False
    account.cloud_account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)
    assert db.scalar(select(func.count()).select_from(Scan)) == 0


def test_scheduler_duplicate_pending_and_running_do_not_create_second_scan(db):
    account = _oci_account(db)
    account.schedule_enabled = True
    account.scan_interval_hours = 24
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()

    worker.enqueue_due_scans(db)
    first = db.scalar(select(Scan))
    assert first is not None
    first.status = "pending"
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)
    assert db.scalar(select(func.count()).select_from(Scan)) == 1

    first.status = "running"
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)
    assert db.scalar(select(func.count()).select_from(Scan)) == 1


def test_manual_oci_active_blocks_scheduled_duplicate(db):
    account = _oci_account(db)
    manual = queue_manual_collection(db, account)
    account.schedule_enabled = True
    account.scan_interval_hours = 24
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()

    worker.enqueue_due_scans(db)

    assert db.scalar(select(func.count()).select_from(Scan)) == 1
    assert db.get(Scan, manual.id).trigger == "manual"


def test_scheduled_oci_active_blocks_manual_duplicate(db):
    account = _oci_account(db)
    account.schedule_enabled = True
    account.scan_interval_hours = 24
    account.next_scan_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()
    worker.enqueue_due_scans(db)

    scheduled = db.scalar(select(Scan))
    assert scheduled is not None
    assert scheduled.trigger == "scheduled"

    with pytest.raises(CollectionPreconditionError, match="already pending or running"):
        queue_manual_collection(db, account)

    assert db.scalar(select(func.count()).select_from(Scan)) == 1


def test_worker_does_not_create_collection_run_for_disabled_queued_work(db):
    account = _aws_account(db)
    scan = Scan(
        account_id=account.id,
        cloud_account_id=account.cloud_account_id,
        trigger="manual",
    )
    db.add(scan)
    db.commit()

    account.cloud_account.enabled = False
    db.commit()

    claimed = worker.claim_scan(db)
    assert claimed is not None
    assert claimed.status == "failed"
    assert (
        db.scalar(
            select(func.count())
            .select_from(CollectionRun)
            .where(CollectionRun.scan_id == claimed.id)
        )
        == 0
    )


def test_collection_executor_registry_resolves_aws_and_oci():
    assert get_collection_executor("aws").provider == "aws"
    assert get_collection_executor("oci").provider == "oci"
    assert has_collection_executor("aws") is True
    assert has_collection_executor("oci") is True

    with pytest.raises(CollectionExecutorUnavailable, match="Unknown cloud provider"):
        get_collection_executor("unknown-cloud")


def test_manual_queue_duplicate_check_uses_cloud_account_identity(db):
    account = _aws_account(db)
    other = AwsAccount(
        name="Other AWS",
        aws_account_id="210987654321",
        role_arn="arn:aws:iam::210987654321:role/DeepOps",
        external_id="other-external-id",
        regions=["us-east-1"],
    )
    db.add(other)
    db.commit()

    db.add(
        Scan(
            account_id=other.id,
            cloud_account_id=account.cloud_account_id,
            trigger="manual",
        )
    )
    db.commit()

    with pytest.raises(CollectionPreconditionError, match="already pending or running"):
        queue_manual_collection(db, account.cloud_account)


def test_claim_rejects_oci_scan_with_legacy_aws_link(db):
    aws_account = _aws_account(db)
    oci_account = _oci_account(db)
    scan = Scan(
        account_id=aws_account.id,
        cloud_account_id=oci_account.id,
        trigger="manual",
    )
    db.add(scan)
    db.commit()

    claimed = worker.claim_scan(db)

    assert claimed is not None
    assert claimed.status == "failed"
    assert (
        db.scalar(
            select(func.count()).select_from(CollectionRun).where(CollectionRun.scan_id == scan.id)
        )
        == 0
    )
    assert oci_account.connection_status == "connected"
