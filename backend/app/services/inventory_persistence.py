"""Inventory persistence with batch-oriented current-state upsert semantics."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.core.cloud import normalize_provider
from app.core.inventory import (
    DiscoveredInventoryResource,
    InventoryPresenceStatus,
    prepare_inventory_metadata,
)
from app.db.base import utcnow
from app.models.inventory import InventoryResource, InventoryResourceObservation

if TYPE_CHECKING:
    from app.models.account import CloudAccount
    from app.models.collection_run import CollectionRun

_RESOURCE_LOOKUP_CHUNK = 250
_OBSERVATION_LOOKUP_CHUNK = 500


def _chunks(values: Sequence, size: int) -> Iterable[Sequence]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _utc_comparable(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class InventoryPersistenceService:
    """Persist normalized resource observations without owning transaction commit."""

    @staticmethod
    def _validate_context(cloud_account: CloudAccount, collection_run: CollectionRun) -> str:
        account_provider = normalize_provider(cloud_account.provider).value
        run_provider = normalize_provider(collection_run.provider).value
        if account_provider != run_provider:
            raise ValueError("CollectionRun provider does not match CloudAccount provider")
        if collection_run.account_id != cloud_account.native_account_id:
            raise ValueError("CollectionRun account_id does not match CloudAccount native identity")
        if cloud_account.id is None:
            raise ValueError("CloudAccount must be persisted before Inventory observations")
        if not collection_run.id:
            raise ValueError("CollectionRun must be persisted before Inventory observations")
        return account_provider

    @staticmethod
    def _apply_current_state(
        current: InventoryResource,
        resource: DiscoveredInventoryResource,
        *,
        native_account_id: str,
        collection_run_id: str,
        observed_at: datetime,
    ) -> None:
        current.native_account_id = native_account_id
        current.native_resource_type = resource.native_resource_type
        current.service = resource.service
        current.name = resource.name
        current.region = resource.region
        current.availability_zone = resource.availability_zone
        current.lifecycle_status = resource.lifecycle_status
        current.native_status = resource.native_status
        current.tags = prepare_inventory_metadata(resource.tags, field_name="tags")
        current.attributes = prepare_inventory_metadata(
            resource.attributes, field_name="attributes"
        )
        current.presence_status = InventoryPresenceStatus.ACTIVE.value
        current.last_seen_at = observed_at
        current.last_seen_collection_run_id = collection_run_id

    def persist_observation(
        self,
        db: Session,
        *,
        cloud_account: CloudAccount,
        collection_run: CollectionRun,
        resource: DiscoveredInventoryResource,
        observed_at: datetime | None = None,
    ) -> InventoryResource:
        return self.persist_observations(
            db,
            cloud_account=cloud_account,
            collection_run=collection_run,
            resources=[resource],
            observed_at=observed_at,
        )[0]

    def persist_observations(
        self,
        db: Session,
        *,
        cloud_account: CloudAccount,
        collection_run: CollectionRun,
        resources: Sequence[DiscoveredInventoryResource],
        observed_at: datetime | None = None,
    ) -> list[InventoryResource]:
        """Persist a collection batch using O(chunks) reads, never one SELECT per resource."""

        provider = self._validate_context(cloud_account, collection_run)
        if not resources:
            return []
        observed_at = observed_at or utcnow()

        input_by_identity: dict[tuple[str, str], DiscoveredInventoryResource] = {}
        ordered_identities: list[tuple[str, str]] = []
        for resource in resources:
            if normalize_provider(resource.provider).value != provider:
                raise ValueError(
                    "Discovered resource provider does not match CloudAccount provider"
                )
            identity = (resource.resource_type, resource.resource_id)
            if identity in input_by_identity:
                raise ValueError(f"Duplicate Inventory resource in one batch: {identity!r}")
            input_by_identity[identity] = resource
            ordered_identities.append(identity)

        current_by_identity: dict[tuple[str, str], InventoryResource] = {}
        for identity_chunk in _chunks(ordered_identities, _RESOURCE_LOOKUP_CHUNK):
            rows = db.scalars(
                select(InventoryResource).where(
                    InventoryResource.provider == provider,
                    InventoryResource.cloud_account_id == cloud_account.id,
                    tuple_(InventoryResource.resource_type, InventoryResource.resource_id).in_(
                        identity_chunk
                    ),
                )
            ).all()
            current_by_identity.update(
                {(row.resource_type, row.resource_id): row for row in rows}
            )

        new_identities: set[tuple[str, str]] = set()
        for identity in ordered_identities:
            if identity in current_by_identity:
                continue
            resource = input_by_identity[identity]
            row = InventoryResource(
                provider=provider,
                cloud_account_id=cloud_account.id,
                native_account_id=cloud_account.native_account_id,
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                native_resource_type=resource.native_resource_type,
                service=resource.service,
                name=resource.name,
                region=resource.region,
                availability_zone=resource.availability_zone,
                lifecycle_status=resource.lifecycle_status,
                native_status=resource.native_status,
                tags=prepare_inventory_metadata(resource.tags, field_name="tags"),
                attributes=prepare_inventory_metadata(
                    resource.attributes, field_name="attributes"
                ),
                presence_status=InventoryPresenceStatus.ACTIVE.value,
                first_seen_at=observed_at,
                last_seen_at=observed_at,
                first_seen_collection_run_id=collection_run.id,
                last_seen_collection_run_id=collection_run.id,
            )
            db.add(row)
            new_identities.add(identity)
            current_by_identity[identity] = row

        # A single flush is required only when new current-state rows need primary keys
        # for their observations. The caller still owns commit/rollback.
        if new_identities:
            db.flush()

        resource_ids = [current_by_identity[identity].id for identity in ordered_identities]
        already_observed: set[int] = set()
        for id_chunk in _chunks(resource_ids, _OBSERVATION_LOOKUP_CHUNK):
            already_observed.update(
                db.scalars(
                    select(InventoryResourceObservation.inventory_resource_id).where(
                        InventoryResourceObservation.collection_run_id == collection_run.id,
                        InventoryResourceObservation.inventory_resource_id.in_(id_chunk),
                    )
                ).all()
            )

        new_observations: list[InventoryResourceObservation] = []
        result: list[InventoryResource] = []
        for identity in ordered_identities:
            resource = input_by_identity[identity]
            current = current_by_identity[identity]
            result.append(current)
            if current.id in already_observed:
                continue

            # Historical observations are always appended for a new run. Current state
            # only moves forward in observation time, preventing delayed runs from
            # rolling back the latest known metadata or presence.
            should_update_current = identity in new_identities or _utc_comparable(
                observed_at
            ) >= _utc_comparable(current.last_seen_at)
            if should_update_current:
                self._apply_current_state(
                    current,
                    resource,
                    native_account_id=cloud_account.native_account_id,
                    collection_run_id=collection_run.id,
                    observed_at=observed_at,
                )

            new_observations.append(
                InventoryResourceObservation(
                    inventory_resource_id=current.id,
                    collection_run_id=collection_run.id,
                    observed_at=observed_at,
                    native_resource_type=resource.native_resource_type,
                    service=resource.service,
                    name=resource.name,
                    region=resource.region,
                    availability_zone=resource.availability_zone,
                    lifecycle_status=resource.lifecycle_status,
                    native_status=resource.native_status,
                    tags=prepare_inventory_metadata(resource.tags, field_name="tags"),
                    attributes=prepare_inventory_metadata(
                        resource.attributes, field_name="attributes"
                    ),
                )
            )

        if new_observations:
            db.add_all(new_observations)
        return result
