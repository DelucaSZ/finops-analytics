import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app import worker
from app.db.base import Base
from app.models.account import AwsAccount, CloudAccount
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
    require_provider_operation,
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


def test_provider_capability_matrix_distinguishes_aws_and_oci():
    aws = get_provider_capabilities("aws")
    oci = get_provider_capabilities("oci")

    assert aws.registration is True
    assert aws.connection_test is True
    assert aws.manual_collection is True
    assert aws.scheduling is True
    assert aws.finops_policies is True

    assert oci.registration is True
    assert oci.editing is True
    assert oci.connection_test is True
    assert oci.manual_collection is False
    assert oci.scheduling is False
    assert oci.finops_policies is False

    with pytest.raises(UnsupportedProviderOperation, match="does not support manual_collection"):
        require_provider_operation("oci", ProviderOperation.MANUAL_COLLECTION)
    with pytest.raises(UnsupportedProviderOperation, match="Unknown cloud provider"):
        get_provider_capabilities("unknown-cloud")


def test_unsupported_oci_collection_does_not_create_scan_or_collection_run(db):
    account = CloudAccount(
        provider="oci",
        native_account_id="ocid1.tenancy.oc1..aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        name="OCI connected fixture",
        enabled=True,
        connection_status="connected",
    )
    db.add(account)
    db.commit()

    with pytest.raises(UnsupportedProviderOperation):
        queue_manual_collection(db, account)

    assert db.scalar(select(func.count()).select_from(Scan)) == 0
    assert db.scalar(select(func.count()).select_from(CollectionRun)) == 0


def test_manual_aws_collection_populates_both_account_identifiers(db):
    account = _aws_account(db)

    scan = queue_manual_collection(db, account.cloud_account)

    assert scan.account_id == account.id
    assert scan.cloud_account_id == account.cloud_account_id
    assert scan.cloud_account_id == account.cloud_account.id


def test_disabled_aws_collection_is_rejected_without_creating_a_scan(db):
    account = _aws_account(db)
    account.cloud_account.enabled = False
    db.commit()

    with pytest.raises(CollectionPreconditionError, match="disabled"):
        queue_manual_collection(db, account.cloud_account)

    assert db.scalar(select(func.count()).select_from(Scan)) == 0


def test_worker_does_not_create_collection_run_for_ineligible_queued_work(db):
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

    failed = db.get(Scan, claimed.id)
    assert failed.status == "failed"
    assert account.cloud_account.connection_status == "untested"
    assert (
        db.scalar(
            select(func.count())
            .select_from(CollectionRun)
            .where(CollectionRun.scan_id == claimed.id)
        )
        == 0
    )


def test_collection_executor_registry_has_only_operational_aws():
    executor = get_collection_executor("aws")

    assert executor.provider == "aws"
    assert has_collection_executor("aws") is True
    assert has_collection_executor("oci") is False

    with pytest.raises(CollectionExecutorUnavailable, match="no operational collection executor"):
        get_collection_executor("oci")
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

    assert db.scalar(select(func.count()).select_from(Scan)) == 1


def test_claim_resolves_provider_from_cloud_account_not_legacy_aws_link(db):
    aws_account = _aws_account(db)
    oci_account = CloudAccount(
        provider="oci",
        native_account_id="ocid1.tenancy.oc1..bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        name="OCI queued corruption fixture",
        enabled=True,
        connection_status="connected",
    )
    db.add(oci_account)
    db.commit()

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
    assert aws_account.cloud_account.connection_status == "untested"
