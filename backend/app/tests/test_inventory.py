from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.models  # noqa: F401 - register the complete model metadata
from app.core.inventory import DiscoveredInventoryResource, InventoryPresenceStatus
from app.db.base import Base
from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.inventory import InventoryResource, InventoryResourceObservation
from app.services.inventory_persistence import InventoryPersistenceService


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'inventory.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_context(db: Session, *, provider="aws", native_account_id="123456789012", suffix="1"):
    account = CloudAccount(
        provider=provider,
        native_account_id=native_account_id,
        name=f"Inventory {suffix}",
    )
    db.add(account)
    db.flush()
    run = CollectionRun(
        id=f"00000000-0000-0000-0000-{int(suffix):012d}",
        provider=provider,
        account_id=native_account_id,
        scope={},
        started_at=datetime(2026, 10, 27, 12, int(suffix), tzinfo=UTC),
        finished_at=datetime(2026, 10, 27, 12, int(suffix), 30, tzinfo=UTC),
        status=CollectionRunStatus.SUCCESS,
        resources_analyzed=0,
        opportunities_found=0,
    )
    db.add(run)
    db.flush()
    return account, run


def resource(**changes):
    values = {
        "provider": "aws",
        "resource_id": "i-0123456789",
        "resource_type": "compute_instance",
        "native_resource_type": "AWS::EC2::Instance",
        "service": "EC2",
        "name": None,
        "region": None,
        "availability_zone": "sa-east-1a",
        "lifecycle_status": "running",
        "native_status": "running",
        "tags": {"Environment": "prod"},
        "attributes": {"instance_type": "m6i.large"},
    }
    values.update(changes)
    return DiscoveredInventoryResource(**values)


def test_model_supports_nullable_name_region_json_and_collection_references(db):
    account, run = add_context(db)
    seen = datetime(2026, 10, 27, 13, tzinfo=UTC)
    row = InventoryResource(
        provider="aws",
        cloud_account_id=account.id,
        native_account_id=account.native_account_id,
        resource_id="vol-1",
        resource_type="block_volume",
        name=None,
        region=None,
        lifecycle_status="available",
        tags={"Owner": "platform"},
        attributes={"size_gb": 100},
        presence_status=InventoryPresenceStatus.ACTIVE.value,
        first_seen_at=seen,
        last_seen_at=seen,
        first_seen_collection_run_id=run.id,
        last_seen_collection_run_id=run.id,
    )
    db.add(row)
    db.flush()

    assert row.name is None and row.region is None
    assert row.tags == {"Owner": "platform"}
    assert row.attributes == {"size_gb": 100}
    assert row.presence_status == "active"
    assert row.first_seen_collection_run_id == run.id
    assert row.last_seen_collection_run_id == run.id


def test_natural_identity_allows_same_resource_id_across_account_provider_and_type(db):
    aws_a, run_a = add_context(db, suffix="1")
    aws_b, run_b = add_context(db, native_account_id="999999999999", suffix="2")
    oci, run_oci = add_context(
        db,
        provider="oci",
        native_account_id="ocid1.tenancy.oc1..inventory",
        suffix="3",
    )
    service = InventoryPersistenceService()
    observed_at = datetime(2026, 10, 27, 14, tzinfo=UTC)

    service.persist_observation(
        db,
        cloud_account=aws_a,
        collection_run=run_a,
        resource=resource(),
        observed_at=observed_at,
    )
    service.persist_observation(
        db,
        cloud_account=aws_b,
        collection_run=run_b,
        resource=resource(),
        observed_at=observed_at,
    )
    service.persist_observation(
        db,
        cloud_account=oci,
        collection_run=run_oci,
        resource=resource(provider="oci", native_resource_type="Instance", service="Compute"),
        observed_at=observed_at,
    )
    other_type_run = CollectionRun(
        id="00000000-0000-0000-0000-000000000004",
        provider="aws",
        account_id=aws_a.native_account_id,
        scope={},
        started_at=observed_at,
        finished_at=observed_at,
        status=CollectionRunStatus.SUCCESS,
        resources_analyzed=0,
        opportunities_found=0,
    )
    db.add(other_type_run)
    db.flush()
    service.persist_observation(
        db,
        cloud_account=aws_a,
        collection_run=other_type_run,
        resource=resource(resource_type="public_ip"),
        observed_at=observed_at + timedelta(minutes=1),
    )
    db.flush()

    assert db.scalar(select(func.count()).select_from(InventoryResource)) == 4

    duplicate = InventoryResource(
        provider="aws",
        cloud_account_id=aws_a.id,
        native_account_id=aws_a.native_account_id,
        resource_id="i-0123456789",
        resource_type="compute_instance",
        lifecycle_status="running",
        tags={},
        attributes={},
        presence_status="active",
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_first_and_second_observation_update_current_but_preserve_history(db):
    account, run1 = add_context(db, suffix="1")
    service = InventoryPersistenceService()
    first_observed_at = datetime(2026, 10, 27, 13, tzinfo=UTC)
    current = service.persist_observation(
        db,
        cloud_account=account,
        collection_run=run1,
        resource=resource(name="old", attributes={"instance_type": "m5.large"}),
        observed_at=first_observed_at,
    )
    db.flush()
    first_id = current.id
    first_seen = current.first_seen_at
    first_run = current.first_seen_collection_run_id

    run2 = CollectionRun(
        id="00000000-0000-0000-0000-000000000002",
        provider="aws",
        account_id=account.native_account_id,
        scope={},
        started_at=first_observed_at + timedelta(hours=1),
        finished_at=first_observed_at + timedelta(hours=1, minutes=1),
        status=CollectionRunStatus.SUCCESS,
        resources_analyzed=0,
        opportunities_found=0,
    )
    db.add(run2)
    db.flush()
    current2 = service.persist_observation(
        db,
        cloud_account=account,
        collection_run=run2,
        resource=resource(name="new", attributes={"instance_type": "m6i.large"}),
        observed_at=first_observed_at + timedelta(hours=1),
    )
    db.flush()

    assert current2.id == first_id
    assert current2.name == "new"
    assert current2.attributes == {"instance_type": "m6i.large"}
    assert current2.first_seen_at == first_seen
    assert current2.first_seen_collection_run_id == first_run
    assert current2.last_seen_collection_run_id == run2.id

    observations = db.scalars(
        select(InventoryResourceObservation)
        .where(InventoryResourceObservation.inventory_resource_id == first_id)
        .order_by(InventoryResourceObservation.observed_at)
    ).all()
    assert len(observations) == 2
    assert observations[0].attributes == {"instance_type": "m5.large"}
    assert observations[1].attributes == {"instance_type": "m6i.large"}


def test_same_run_is_idempotent_and_does_not_mutate_snapshot(db):
    account, run = add_context(db)
    service = InventoryPersistenceService()
    observed_at = datetime(2026, 10, 27, 13, tzinfo=UTC)
    service.persist_observation(
        db,
        cloud_account=account,
        collection_run=run,
        resource=resource(name="first"),
        observed_at=observed_at,
    )
    db.flush()
    service.persist_observation(
        db,
        cloud_account=account,
        collection_run=run,
        resource=resource(name="reprocessed"),
        observed_at=observed_at + timedelta(minutes=5),
    )
    db.flush()

    current = db.scalar(select(InventoryResource))
    observations = db.scalars(select(InventoryResourceObservation)).all()
    assert len(observations) == 1
    assert observations[0].name == "first"
    assert current.name == "first"
    assert current.last_seen_at == observed_at


def test_reappearance_reactivates_without_changing_first_seen(db):
    account, run1 = add_context(db, suffix="1")
    service = InventoryPersistenceService()
    first_observed_at = datetime(2026, 10, 27, 13, tzinfo=UTC)
    current = service.persist_observation(
        db,
        cloud_account=account,
        collection_run=run1,
        resource=resource(),
        observed_at=first_observed_at,
    )
    db.flush()
    current.presence_status = InventoryPresenceStatus.MISSING.value
    db.flush()
    first_seen = current.first_seen_at

    run2 = CollectionRun(
        id="00000000-0000-0000-0000-000000000002",
        provider="aws",
        account_id=account.native_account_id,
        scope={},
        started_at=first_observed_at + timedelta(days=1),
        finished_at=first_observed_at + timedelta(days=1, minutes=1),
        status=CollectionRunStatus.SUCCESS,
        resources_analyzed=0,
        opportunities_found=0,
    )
    db.add(run2)
    db.flush()
    service.persist_observation(
        db,
        cloud_account=account,
        collection_run=run2,
        resource=resource(name="back"),
        observed_at=first_observed_at + timedelta(days=1),
    )
    db.flush()

    assert current.presence_status == "active"
    assert current.first_seen_at == first_seen
    assert current.name == "back"


def test_absence_from_new_run_never_marks_resource_missing(db):
    account, run1 = add_context(db, suffix="1")
    service = InventoryPersistenceService()
    service.persist_observation(
        db,
        cloud_account=account,
        collection_run=run1,
        resource=resource(),
        observed_at=datetime(2026, 10, 27, 13, tzinfo=UTC),
    )
    db.flush()
    run2 = CollectionRun(
        id="00000000-0000-0000-0000-000000000002",
        provider="aws",
        account_id=account.native_account_id,
        scope={},
        started_at=datetime(2026, 10, 28, 13, tzinfo=UTC),
        finished_at=datetime(2026, 10, 28, 13, 1, tzinfo=UTC),
        status=CollectionRunStatus.SUCCESS,
        resources_analyzed=0,
        opportunities_found=0,
    )
    db.add(run2)
    db.flush()

    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run2,
        resources=[],
    )
    db.flush()

    current = db.scalar(select(InventoryResource))
    assert current.presence_status == "active"
    assert current.last_seen_collection_run_id == run1.id


def test_batch_path_avoids_select_per_resource(db):
    account, run = add_context(db)
    service = InventoryPersistenceService()
    statements = []

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = statement.lower()
        if normalized.lstrip().startswith("select") and "inventory_" in normalized:
            statements.append(statement)

    resources = [
        resource(resource_id=f"i-{index:010d}", name=f"instance-{index}")
        for index in range(100)
    ]
    service.persist_observations(
        db,
        cloud_account=account,
        collection_run=run,
        resources=resources,
        observed_at=datetime(2026, 10, 27, 13, tzinfo=UTC),
    )
    db.flush()

    assert len(statements) <= 2
    assert db.scalar(select(func.count()).select_from(InventoryResource)) == 100


def test_metadata_guardrails_reject_credentials_and_oversized_payloads():
    with pytest.raises(ValueError, match="Sensitive metadata key"):
        resource(attributes={"session_token": "do-not-store"})
    with pytest.raises(ValueError, match="too large|exceeds"):
        resource(attributes={"blob": "x" * (256 * 1024 + 1)})


def test_context_must_match_provider_and_native_account(db):
    account, run = add_context(db)
    service = InventoryPersistenceService()
    run.account_id = "000000000000"
    with pytest.raises(ValueError, match="native identity"):
        service.persist_observation(
            db,
            cloud_account=account,
            collection_run=run,
            resource=resource(),
        )
