# Inventory domain and persistence

## Purpose

Inventory is the provider-neutral record of cloud resources that exist or have existed in a configured cloud account. It is intentionally independent from Findings/Opportunities: an Inventory resource exists even when no FinOps recommendation is produced for it. Findings are therefore never used as an Inventory source of truth or backfill source.

Task 24.13A adds only the persistence foundation. It does not add AWS discovery, new OCI API calls, public Inventory endpoints, or frontend behavior.

## Domain boundary

Discovery adapters emit `DiscoveredInventoryResource`. The DTO is not coupled to SQLAlchemy and carries canonical provider, stable resource identity, normalized resource type/status, optional provider-native type/status, service, location, tags, and provider-specific attributes. `CloudProvider`/`normalize_provider()` remain the canonical provider domain.

The natural resource identity is:

`(provider, cloud_account_id, resource_type, resource_id)`

`cloud_account_id` points at the product `CloudAccount`. `native_account_id` is copied from `CloudAccount.native_account_id` for search and troubleshooting; it is not a second source of truth.

## Current state

`inventory_resources` stores the latest known state. A first observation creates the row as `active` and sets both first/last seen timestamps and CollectionRun references. Later observations update mutable metadata, `last_seen_at`, `last_seen_collection_run_id`, and return a previously `missing` resource to `active`. `first_seen_at` and `first_seen_collection_run_id` are never rewritten on re-observation.

The domain supports `active` and `missing`, but 24.13A never infers `missing` from absence. A resource omitted from a persistence call remains unchanged. Coverage-aware reconciliation belongs to Task 24.13B so partial/failed provider discovery cannot create false disappearances.

## Observation history

`inventory_resource_observations` is append-only by service contract. Each snapshot records the metadata observed in one CollectionRun. A unique constraint on `(inventory_resource_id, collection_run_id)` makes same-run reprocessing idempotent. Later current-state changes do not mutate prior snapshots.

CollectionRun references use `ON DELETE SET NULL` so retention of run rows cannot erase Inventory history; timestamps remain available. Inventory resources are owned by `CloudAccount` and use `ON DELETE CASCADE`, matching the existing account-owned data lifecycle. Observation rows cascade only when their parent Inventory resource is intentionally deleted.

The current `CollectionRun` model stores provider plus native `account_id`, not `cloud_account_id`. The persistence service therefore validates `CollectionRun.provider/account_id` against `CloudAccount.provider/native_account_id` before writing Inventory rows, while preserving the existing CollectionRun contract.

## Transactions and performance

`InventoryPersistenceService` never commits. The caller owns commit/rollback. A flush is issued only when newly inserted current-state rows need primary keys for observation rows.

The batch path performs set-based lookups in chunks: one current-state lookup per identity chunk and one existing-observation lookup per ID chunk. It does not issue a `SELECT` per resource. This portable SQLAlchemy strategy is used instead of PostgreSQL-only `ON CONFLICT` because the project supports SQLite in tests/migrations.

Indexes are targeted at expected server-side filters: provider, product/native account identity, normalized resource type, last-seen time, account+presence+type, provider+account+region, and account+lifecycle status. The natural identity has a unique constraint.

## Provider metadata safety

Provider tags and attributes are untrusted input. The domain contract rejects known credential-bearing keys (access/secret/session credentials, passwords, private keys, Authorization/credential payloads), non-JSON values, excessive nesting, strings larger than 64 KiB, and each JSON document larger than 256 KiB. Data is copied before persistence so later adapter mutation cannot change an existing snapshot in memory.

OCI defined/freeform tags must be mapped losslessly by the future adapter. When a lossless normalized tag map is not possible, the original structure belongs in `attributes`; 24.13A does not alter `OciDiscoveryService`.

## Backfill and rollout

There is deliberately no historical backfill. Findings, Opportunities, Billing, Reservations, and `CollectionRun.resources_analyzed` cannot reconstruct a complete resource inventory. Inventory starts empty and will be populated by future successful discovery integration.

Task 24.13B will adapt AWS/OCI discovery to `DiscoveredInventoryResource`, define coverage per resource type/scope, persist observations, and perform coverage-safe missing reconciliation. Task 24.13C will add the query API. The visual Inventory experience remains blocked until those foundations exist.
