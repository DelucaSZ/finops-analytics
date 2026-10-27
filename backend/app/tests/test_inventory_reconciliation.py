from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.inventory import (
    DiscoveredInventoryResource,
    InventoryCoverage,
    InventoryCoverageStatus,
    InventoryDiscoveryResult,
)
from app.db.base import Base
from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.inventory import InventoryResource, InventoryResourceObservation
from app.models.scan import Scan
from app.services.collection_executors import _persist_inventory_discovery
from app.services.inventory_persistence import InventoryPersistenceService

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'inventory-reconcile.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _account(db: Session, provider="aws", native_id="123456789012", name="A"):
    account = CloudAccount(provider=provider, native_account_id=native_id, name=name)
    db.add(account)
    db.flush()
    return account


def _run(db: Session, account: CloudAccount, suffix: int, at: datetime):
    run = CollectionRun(
        id=f"10000000-0000-0000-0000-{suffix:012d}",
        provider=account.provider,
        account_id=account.native_account_id,
        scope={"regions": ["us-east-1", "us-west-2"]},
        started_at=at,
        finished_at=at + timedelta(minutes=1),
        status=CollectionRunStatus.SUCCESS,
        resources_analyzed=0,
        opportunities_found=0,
    )
    db.add(run)
    db.flush()
    return run


def _resource(resource_id, *, provider="aws", resource_type="compute_instance", region="us-east-1"):
    return DiscoveredInventoryResource(
        provider=provider,
        resource_id=resource_id,
        resource_type=resource_type,
        service="EC2" if provider == "aws" else "Compute",
        region=region,
        lifecycle_status="running",
        native_status="running" if provider == "aws" else "RUNNING",
        tags={},
        attributes={},
    )


def _coverage(account, resource_type, region, status):
    return InventoryCoverage(
        provider=account.provider,
        cloud_account_id=account.id,
        resource_type=resource_type,
        region=region,
        status=status,
    )


def _current(db, account, resource_id, resource_type="compute_instance"):
    return db.scalar(
        select(InventoryResource).where(
            InventoryResource.cloud_account_id == account.id,
            InventoryResource.resource_type == resource_type,
            InventoryResource.resource_id == resource_id,
        )
    )


def test_complete_scope_marks_missing_without_false_observation_or_last_seen_change(db):
    account = _account(db)
    run1 = _run(db, account, 1, NOW)
    service = InventoryPersistenceService()
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run1,
        resources=[_resource("i-a")],
        observed_at=NOW,
    )
    db.flush()
    row = _current(db, account, "i-a")
    last_seen = row.last_seen_at
    last_seen_run = row.last_seen_collection_run_id

    run2 = _run(db, account, 2, NOW + timedelta(hours=1))
    reconciled = service.reconcile_complete_scopes(
        db,
        cloud_account=account,
        collection_run=run2,
        resources=[],
        coverage=[_coverage(account, "compute_instance", "us-east-1", "complete")],
        observed_at=run2.started_at,
    )
    db.flush()

    assert reconciled == 1
    assert row.presence_status == "missing"
    assert row.last_seen_at == last_seen
    assert row.last_seen_collection_run_id == last_seen_run
    assert db.scalar(select(func.count()).select_from(InventoryResourceObservation)) == 1


def test_failed_and_partial_scopes_never_reconcile_absence(db):
    account = _account(db)
    run1 = _run(db, account, 1, NOW)
    service = InventoryPersistenceService()
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run1,
        resources=[
            _resource("i-failed", resource_type="relational_database"),
            _resource("i-partial", resource_type="block_volume"),
        ],
        observed_at=NOW,
    )
    run2 = _run(db, account, 2, NOW + timedelta(hours=1))

    reconciled = service.reconcile_complete_scopes(
        db,
        cloud_account=account,
        collection_run=run2,
        resources=[],
        coverage=[
            _coverage(account, "relational_database", "us-east-1", "failed"),
            _coverage(account, "block_volume", "us-east-1", "partial"),
        ],
        observed_at=run2.started_at,
    )
    db.flush()

    assert reconciled == 0
    assert _current(db, account, "i-failed", "relational_database").presence_status == "active"
    assert _current(db, account, "i-partial", "block_volume").presence_status == "active"


def test_regional_and_resource_type_isolation_matches_required_partial_run_examples(db):
    account = _account(db)
    run1 = _run(db, account, 1, NOW)
    service = InventoryPersistenceService()
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run1,
        resources=[
            _resource("i-east", region="us-east-1"),
            _resource("i-west", region="us-west-2"),
            _resource("db-east", resource_type="relational_database", region="us-east-1"),
        ],
        observed_at=NOW,
    )
    run2 = _run(db, account, 2, NOW + timedelta(hours=1))

    reconciled = service.reconcile_complete_scopes(
        db,
        cloud_account=account,
        collection_run=run2,
        resources=[],
        coverage=[
            _coverage(account, "compute_instance", "us-east-1", "complete"),
            _coverage(account, "compute_instance", "us-west-2", "failed"),
            _coverage(account, "relational_database", "us-east-1", "failed"),
        ],
        observed_at=run2.started_at,
    )
    db.flush()

    assert reconciled == 1
    assert _current(db, account, "i-east").presence_status == "missing"
    assert _current(db, account, "i-west").presence_status == "active"
    assert _current(db, account, "db-east", "relational_database").presence_status == "active"


def test_empty_successful_discovery_is_complete_and_reconciles(db):
    account = _account(db)
    service = InventoryPersistenceService()
    run1 = _run(db, account, 1, NOW)
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run1,
        resources=[_resource("i-empty")],
        observed_at=NOW,
    )
    run2 = _run(db, account, 2, NOW + timedelta(hours=1))

    assert service.reconcile_complete_scopes(
        db,
        cloud_account=account,
        collection_run=run2,
        resources=[],
        coverage=[_coverage(account, "compute_instance", "us-east-1", "complete")],
        observed_at=run2.started_at,
    ) == 1
    assert _current(db, account, "i-empty").presence_status == "missing"


def test_reappearance_preserves_first_seen_and_updates_last_seen(db):
    account = _account(db)
    service = InventoryPersistenceService()
    run1 = _run(db, account, 1, NOW)
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run1,
        resources=[_resource("i-return")],
        observed_at=NOW,
    )
    db.flush()
    row = _current(db, account, "i-return")
    first_seen = row.first_seen_at
    first_run = row.first_seen_collection_run_id

    run2 = _run(db, account, 2, NOW + timedelta(hours=1))
    service.reconcile_complete_scopes(
        db,
        cloud_account=account,
        collection_run=run2,
        resources=[],
        coverage=[_coverage(account, "compute_instance", "us-east-1", "complete")],
        observed_at=run2.started_at,
    )
    assert row.presence_status == "missing"

    run3 = _run(db, account, 3, NOW + timedelta(hours=2))
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run3,
        resources=[_resource("i-return")],
        observed_at=run3.started_at,
    )
    db.flush()

    assert row.presence_status == "active"
    assert row.first_seen_at == first_seen
    assert row.first_seen_collection_run_id == first_run
    assert row.last_seen_at == run3.started_at
    assert row.last_seen_collection_run_id == run3.id
    assert db.scalar(select(func.count()).select_from(InventoryResourceObservation)) == 2


def test_account_and_provider_coverage_are_strictly_isolated(db):
    aws_a = _account(db, native_id="111111111111", name="A")
    aws_b = _account(db, native_id="222222222222", name="B")
    oci = _account(db, provider="oci", native_id="ocid1.tenancy.example", name="OCI")
    service = InventoryPersistenceService()

    run_a = _run(db, aws_a, 1, NOW)
    run_b = _run(db, aws_b, 2, NOW)
    run_oci = _run(db, oci, 3, NOW)
    service.persist_observations(
        db,
        cloud_account=aws_a,
        collection_run=run_a,
        resources=[_resource("same-id")],
        observed_at=NOW,
    )
    service.persist_observations(
        db,
        cloud_account=aws_b,
        collection_run=run_b,
        resources=[_resource("same-id")],
        observed_at=NOW,
    )
    service.persist_observations(
        db,
        cloud_account=oci,
        collection_run=run_oci,
        resources=[_resource("same-id", provider="oci")],
        observed_at=NOW,
    )

    run_a2 = _run(db, aws_a, 4, NOW + timedelta(hours=1))
    service.reconcile_complete_scopes(
        db,
        cloud_account=aws_a,
        collection_run=run_a2,
        resources=[],
        coverage=[_coverage(aws_a, "compute_instance", "us-east-1", "complete")],
        observed_at=run_a2.started_at,
    )
    db.flush()

    assert _current(db, aws_a, "same-id").presence_status == "missing"
    assert _current(db, aws_b, "same-id").presence_status == "active"
    assert _current(db, oci, "same-id").presence_status == "active"


def test_conflicting_or_provider_specific_coverage_is_not_broadened_to_complete(db):
    account = _account(db)
    service = InventoryPersistenceService()
    run1 = _run(db, account, 1, NOW)
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run1,
        resources=[_resource("i-safe")],
        observed_at=NOW,
    )
    run2 = _run(db, account, 2, NOW + timedelta(hours=1))

    conflicting = [
        _coverage(account, "compute_instance", "us-east-1", InventoryCoverageStatus.COMPLETE),
        _coverage(account, "compute_instance", "us-east-1", InventoryCoverageStatus.FAILED),
        InventoryCoverage(
            provider="aws",
            cloud_account_id=account.id,
            resource_type="compute_instance",
            region="us-east-1",
            scope=(("subscope", "one"),),
            status="complete",
        ),
    ]
    assert service.reconcile_complete_scopes(
        db,
        cloud_account=account,
        collection_run=run2,
        resources=[],
        coverage=conflicting,
        observed_at=run2.started_at,
    ) == 0
    assert _current(db, account, "i-safe").presence_status == "active"


def test_delayed_older_run_cannot_mark_newer_observation_missing(db):
    account = _account(db)
    service = InventoryPersistenceService()
    newer = _run(db, account, 2, NOW + timedelta(hours=2))
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=newer,
        resources=[_resource("i-newer")],
        observed_at=newer.started_at,
    )
    older = _run(db, account, 1, NOW + timedelta(hours=1))

    assert service.reconcile_complete_scopes(
        db,
        cloud_account=account,
        collection_run=older,
        resources=[],
        coverage=[_coverage(account, "compute_instance", "us-east-1", "complete")],
        observed_at=older.started_at,
    ) == 0
    assert _current(db, account, "i-newer").presence_status == "active"


def test_collection_run_integration_persists_inventory_and_returns_distinct_observed_count(db):
    account = _account(db)
    scan = Scan(cloud_account_id=account.id, account_id=None, status="running")
    db.add(scan)
    db.flush()
    run = CollectionRun(
        id="10000000-0000-0000-0000-000000000099",
        scan_id=scan.id,
        provider="aws",
        account_id=account.native_account_id,
        scope={"regions": ["us-east-1"]},
        started_at=NOW,
        status=CollectionRunStatus.RUNNING,
        resources_analyzed=0,
        opportunities_found=0,
    )
    db.add(run)
    db.flush()

    result = InventoryDiscoveryResult(
        resources=(_resource("i-flow"),),
        coverage=(_coverage(account, "compute_instance", "us-east-1", "complete"),),
    )
    assert _persist_inventory_discovery(db, account, scan, result) == 1
    db.flush()

    current = _current(db, account, "i-flow")
    assert current is not None
    assert current.last_seen_collection_run_id == run.id
    assert db.scalar(select(func.count()).select_from(InventoryResourceObservation)) == 1


def test_inventory_persistence_remains_transactional_and_caller_rollback_removes_both_states(db):
    account = _account(db)
    run = _run(db, account, 1, NOW)
    service = InventoryPersistenceService()
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run,
        resources=[_resource("i-rollback")],
        observed_at=NOW,
    )
    db.flush()
    assert db.scalar(select(func.count()).select_from(InventoryResource)) == 1
    assert db.scalar(select(func.count()).select_from(InventoryResourceObservation)) == 1

    db.rollback()
    assert db.scalar(select(func.count()).select_from(InventoryResource)) == 0
    assert db.scalar(select(func.count()).select_from(InventoryResourceObservation)) == 0
