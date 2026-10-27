# Inventory domain, discovery and persistence

## Purpose

Inventory is the provider-neutral record of cloud resources that exist or have existed in a configured cloud account. It is intentionally independent from Findings/Opportunities: an Inventory resource exists even when no FinOps recommendation is produced for it. Findings are therefore never used as an Inventory source of truth or backfill source.

Task 24.13A introduced the persistence foundation. Task 24.13B connects that foundation to real AWS and OCI discovery. It still does not add public Inventory endpoints or frontend behavior; those remain responsibilities of 24.13C and the later Aven Inventory experience.

## Domain boundary

Discovery adapters emit `DiscoveredInventoryResource`. The DTO is not coupled to SQLAlchemy and carries canonical provider, stable resource identity, normalized resource type/status, optional provider-native type/status, service, location, tags, and provider-specific attributes. `CloudProvider`/`normalize_provider()` remain the canonical provider domain.

The natural resource identity is:

`(provider, cloud_account_id, resource_type, resource_id)`

`cloud_account_id` points at the product `CloudAccount`. `native_account_id` is copied from `CloudAccount.native_account_id` for search and troubleshooting; it is not a second source of truth.

Inventory discovery produces an `InventoryDiscoveryResult` containing:

- `resources`: resources positively observed in the current CollectionRun;
- `coverage`: explicit evidence describing which provider/account/resource-type/location scopes were enumerated;
- `warnings` and `errors`: sanitized operational issues that contain no provider credentials or raw SDK exception payloads.

Inventory Discovery and Opportunity Discovery remain separate responsibilities. AWS opportunity collectors are not rewritten as Inventory collectors, and OCI analyzers continue consuming the existing `OciDiscoveryResult` dataset.

## Current state

`inventory_resources` stores the latest known state. A first observation creates the row as `active` and sets both first/last seen timestamps and CollectionRun references. Later observations update mutable metadata, `last_seen_at`, `last_seen_collection_run_id`, and return a previously `missing` resource to `active`. `first_seen_at` and `first_seen_collection_run_id` are never rewritten on re-observation.

`active -> missing` is now supported through coverage-safe reconciliation. Marking a resource `missing` does **not** update `last_seen_at` or `last_seen_collection_run_id`, because the resource was not positively observed in that run.

## Observation history

`inventory_resource_observations` is append-only by service contract. Each snapshot records the metadata observed in one CollectionRun. A unique constraint on `(inventory_resource_id, collection_run_id)` makes same-run reprocessing idempotent. Later current-state changes do not mutate prior snapshots.

Only resources actually observed by provider discovery receive an `InventoryResourceObservation`. A resource marked `missing` through reconciliation does not receive a synthetic absence observation.

CollectionRun references use `ON DELETE SET NULL` so retention of run rows cannot erase Inventory history; timestamps remain available. Inventory resources are owned by `CloudAccount` and use `ON DELETE CASCADE`, matching the existing account-owned data lifecycle. Observation rows cascade only when their parent Inventory resource is intentionally deleted.

The current `CollectionRun` model stores provider plus native `account_id`, not `cloud_account_id`. The persistence service therefore validates `CollectionRun.provider/account_id` against `CloudAccount.provider/native_account_id` before writing Inventory rows, while preserving the existing CollectionRun contract.

## Coverage semantics

Coverage is explicit and tri-state:

- `complete`: sufficient evidence exists that the scope was fully enumerated;
- `partial`: part of the scope was enumerated, but completeness is not proven;
- `failed`: the scope could not be enumerated.

Only `complete` coverage authorizes absence reconciliation.

For 24.13B, persisted reconciliation scopes are deterministic `account + region + resource_type` scopes. The coverage contract can carry additional provider-specific scope dimensions, but persistence deliberately refuses to broaden such a scope to region level. This prevents a successful compartment or sub-scope from hiding resources in another failed sub-scope.

Conflicting evidence for the same scope is conservative: the scope is reconcilable only when all coverage entries for that scope are `complete`.

An empty result is not a failure. If an API successfully enumerates a scope and returns zero resources, coverage is `complete` and previously active resources in that scope may become `missing`. Conversely, AccessDenied, authorization errors, timeouts, throttling exhaustion, partial pagination, or other incomplete enumeration never become `0 resources + complete`.

## Safe reconciliation

For each complete scope, reconciliation:

1. queries active resources for the same provider and CloudAccount in batch;
2. restricts candidates to the completed resource type and region;
3. compares them with identities positively observed in the current discovery result;
4. marks absent candidates `missing` without modifying their last-seen metadata;
5. skips any resource whose current state is newer than the CollectionRun being reconciled.

Partial and failed scopes do not reconcile absence. Coverage for one provider or account cannot mutate another provider/account, even if resource IDs and normalized types happen to match.

A later positive observation of a missing resource reactivates the same `InventoryResource`, updates last-seen state, and preserves first-seen state.

## AWS Inventory discovery

`AwsInventoryDiscoveryService` is independent from opportunity collectors. It reuses the existing assumed-role session and the exact region list already configured for the AWS account/CollectionRun. No AWS region list is hardcoded.

Wave 1 enumerates:

| AWS API resource | Canonical type | Native type |
| --- | --- | --- |
| EC2 Instance | `compute_instance` | `AWS::EC2::Instance` |
| EBS Volume | `block_volume` | `AWS::EC2::Volume` |
| Elastic IP | `public_ip` | `AWS::EC2::EIP` |
| RDS DB Instance | `relational_database` | `AWS::RDS::DBInstance` |

EC2 Instances, EBS Volumes and RDS DB Instances use the official SDK paginator. Elastic IP discovery uses `DescribeAddresses`, which is not a paginated operation in the current AWS API. Each resource type is isolated per region, so an RDS failure in one region does not discard successful EC2/EBS/EIP discovery elsewhere.

Stable native identifiers are preferred. Elastic IP uses `AllocationId` when available rather than the address itself. EC2 `Name` is sourced only from the AWS `Name` tag; an instance ID is not fabricated as a display name. RDS uses the DB ARN as stable resource identity when supplied and retains the DB instance identifier as its name.

AWS attributes are normalized to the fields needed by Inventory and future query/UI work. Raw AWS API payloads are not persisted.

## OCI integration

OCI discovery is not reimplemented. `OciCollectionExecutor` still invokes `OciDiscoveryService.discover()` exactly once per CollectionRun. The returned `OciDiscoveryResult` continues to feed Cloud Advisor, Usage, Monitoring, correlation and analyzers unchanged.

A pure OCI Inventory adapter converts the same in-memory resources to `DiscoveredInventoryResource` and preserves the existing Wave 1 resource types:

- `compute_instance`;
- `block_volume`;
- `boot_volume`;
- `public_ip`.

OCID, name, region, compartment ID, availability domain, native lifecycle state, defined/freeform tags, sources and provider attributes are preserved. `availability_domain` maps to the normalized availability-zone field where applicable. Unknown lifecycle values normalize to `unknown` while the original native state remains available for troubleshooting.

OCI `counts_by_type` is used as the authoritative completeness signal already produced by the current discovery implementation. A type with aggregate incomplete coverage is never promoted to `complete`; errors are scoped conservatively by region/resource type when possible.

## CollectionRun integration

The operational flow is now:

```text
CollectionRun starts
  -> provider authentication/session
  -> Inventory discovery
  -> existing opportunity/analyzer collection
  -> Inventory persistence + safe reconciliation
  -> opportunity persistence/reconciliation
  -> CollectionRun completion
```

Inventory rows and observations use the same CollectionRun created by the worker. Provider network calls still run outside the database transaction pattern already established by the executors. Inventory persistence does not commit; the worker remains the transaction owner, so a failure can roll back current-state and observation changes together.

`CollectionRun.resources_analyzed` now means the number of distinct resources positively observed by Inventory discovery in that run. Partial runs count resources that were actually observed and do not count scopes that could not be enumerated.

For OCI, this count comes from the adapted in-memory discovery dataset. For AWS, it comes from the new Wave 1 Inventory discovery rather than the previous placeholder zero.

## Transactions and performance

`InventoryPersistenceService` never commits. The caller owns commit/rollback. A flush is issued only when newly inserted current-state rows need primary keys for observation rows.

The batch observation path performs set-based lookups in chunks: one current-state lookup per identity chunk and one existing-observation lookup per ID chunk. Reconciliation performs an account/provider/type candidate query and compares observed identities in memory; it does not issue a `SELECT` per resource.

This portable SQLAlchemy strategy is used instead of PostgreSQL-only `ON CONFLICT` because the project supports SQLite in tests/migrations.

Indexes are targeted at expected server-side filters: provider, product/native account identity, normalized resource type, last-seen time, account+presence+type, provider+account+region, and account+lifecycle status. The natural identity has a unique constraint.

## Security and observability

Provider tags and attributes are untrusted input. The domain contract rejects known credential-bearing keys (access/secret/session credentials, passwords, private keys, Authorization/credential payloads), non-JSON values, excessive nesting, strings larger than 64 KiB, and each JSON document larger than 256 KiB. Data is copied before persistence so later adapter mutation cannot change an existing snapshot in memory.

Discovery issues are normalized to provider/resource-type/region/category/code and deterministic safe messages. Raw SDK exceptions and credential-bearing payloads are not persisted. Structured collection logs include provider, CloudAccount, CollectionRun, stage, resource count, issue count, duration, and reconciled-missing count without dumping resource ID lists.

No new metrics stack is introduced. Existing collection logging is reused for discovery/persistence observability.

## Known limitations of Wave 1

AWS Inventory currently covers only EC2 Instances, EBS Volumes, Elastic IPs and RDS DB Instances. Absence of S3, Lambda, ECS, EKS, Load Balancers, NAT Gateways, snapshots, DynamoDB, ElastiCache, CloudFront, Route53, IAM or another AWS service from Inventory does **not** mean that service/resource is absent from the account.

OCI Inventory covers the resource types already produced by the existing OCI Wave 1 discovery: compute instances, block volumes, boot volumes and public IPs.

24.13B does not query pricing, calculate savings, create new opportunity rules, expose a public Inventory API, or add frontend routes/components.

## 24.13C readiness

24.13B leaves current Inventory state and historical observations populated from real provider discovery. Task 24.13C can therefore implement server-side query, filtering, search, sorting and pagination over persisted data without invoking AWS or OCI during HTTP requests.
