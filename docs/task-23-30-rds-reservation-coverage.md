# Task 23.30 — RDS Reservation Coverage Engine

## Scope

This task adds the current-state Amazon RDS Reserved DB Instance coverage engine. It calculates a logical billing allocation between active RDS workloads and active Reserved DB Instances; it does not create a permanent AWS-side reservation-to-instance binding.

Out of scope: opportunities, savings estimates, Reserved DB Instance offerings/pricing, expiration alerts/notifications, frontend work, purchase or renewal automation.

## Architecture

The implementation is split into four responsibilities:

1. `RdsReservationMatcher` decides technical compatibility and returns an explicit match type/reason.
2. `RdsReservationCoverageEngine` converts eligible workloads and reservations into capacity, allocates it deterministically, and enforces mathematical invariants.
3. coverage persistence stores immutable run snapshots, per-instance coverage, reservation utilization, and auditable allocations.
4. `RdsCostExplorerClient` obtains AWS-observed historical coverage for reconciliation without becoming the source of truth for current inventory coverage.

The allocator groups candidates first by Region, normalized engine/product, and instance family. Within a pool it uses stable account/Region/engine/class/identifier ordering. Allocation has two phases: exact class first, then size flexibility. Reservation capacity is decremented after every allocation and can never be reused.

## Compatibility rules

Matching always requires the same Region, engine/product, and instance class family. License model is normalized and matched when present. SQL Server editions and Oracle editions remain distinct because their normalized engine/product identifiers are distinct (`sqlserver-se`, `sqlserver-ee`, `oracle-ee`, `oracle-se2`, and so on). Engine version is retained in inventory but is not a compatibility key.

Size flexibility is enabled only for MySQL, MariaDB, PostgreSQL, Db2, Oracle BYOL, Aurora MySQL, and Aurora PostgreSQL. SQL Server and Oracle License Included use exact class/deployment matching.

Cross-account allocation is accepted only when a `BillingScopeContext` can prove a common billing scope and RI sharing enabled for both accounts. Unknown sharing is not promoted to confirmed coverage. The current account model does not yet persist AWS Organizations/payer/sharing metadata, so production runs default to reliable same-account allocation. The abstraction is ready to receive verified metadata later without changing the matching algorithm.

## Normalized units

| Size | Units |
|---|---:|
| micro | 0.5 |
| small | 1 |
| medium | 2 |
| large | 4 |
| xlarge | 8 |
| 2xlarge | 16 |
| 4xlarge | 32 |
| 6xlarge | 48 |
| 8xlarge | 64 |
| 10xlarge | 80 |
| 12xlarge | 96 |
| 16xlarge | 128 |
| 24xlarge | 192 |
| 32xlarge | 256 |

The table is explicit and uses `Decimal`; values are never derived from vCPU. Unknown sizes produce `UNKNOWN` coverage instead of a guessed value.

`DBInstanceCount` multiplies the reservation capacity. For size-flexible traditional RDS, a Multi-AZ Reserved DB Instance contributes 2× the class base units.

## Single-AZ, Multi-AZ, and Multi-AZ DB Cluster

For traditional RDS demand:

- Single-AZ DB instance: 1× base units.
- Multi-AZ DB instance (primary + standby): 2× base units.
- logical Multi-AZ DB cluster: 3× base units.

`DescribeDBInstances` exposes the three members of a Multi-AZ DB cluster individually. The enrichment step uses `DescribeDBClusters` and tags those rows as `multi_az_cluster_member`, so each inventory row consumes one base unit and the three-member cluster totals 3×. This avoids applying the 3× multiplier three times.

If cluster topology cannot be refreshed, a non-Aurora instance with `DBClusterIdentifier` is treated as unknown rather than guessed as a traditional Multi-AZ DB instance.

## Aurora

Aurora MySQL and Aurora PostgreSQL use size flexibility. Cluster storage configuration is refreshed with `DescribeDBClusters`:

- Aurora Standard: base normalized units.
- Aurora I/O-Optimized: base × `1.3`.

Unknown Aurora storage configuration produces `UNKNOWN`; the engine never silently assumes Aurora Standard.

## Active resources

A reservation contributes capacity only when the inventory row is active, its AWS state is `active`, `start_time <= calculation_time < expiration_at`, and its configuration is supported.

Transient DB instance states already recognized by the RDS inventory (for example `modifying`, `backing-up`, and `rebooting`) remain demand. Clearly non-running states `stopped`, `stopping`, `deleting`, and `failed` do not create current coverage demand.

## Coverage results

Per instance:

- `required_units`
- `covered_units`
- `uncovered_units`
- `coverage_percentage`
- `FULL`, `PARTIAL`, `UNCOVERED`, or `UNKNOWN`
- allocation list with reservation, units, match type, scope, and reason

Per reservation:

- `total_units`
- `allocated_units`
- `unused_units`
- `utilization_percentage`

Run snapshots also retain summary totals and reconciliation status.

## Cost Explorer reconciliation

The optional observed-billing adapter calls `ce:GetReservationCoverage` for the last complete UTC day with an explicit `SERVICE = Amazon Relational Database Service` filter, `LINKED_ACCOUNT` when an account is known, `Metrics = Unit`, daily granularity, and pagination.

Current technical coverage always comes from inventory + the local coverage engine. Cost Explorer is separate historical evidence. Reconciliation statuses are `MATCH`, `MINOR_VARIANCE`, `MISMATCH`, or `NOT_AVAILABLE`. If any analyzed account cannot provide Cost Explorer coverage (including `AccessDenied`), the technical run still completes and billing reconciliation remains `NOT_AVAILABLE` rather than comparing a partial scope.

## API

- `POST /api/v1/rds/reservation-coverage/run?validate_billing=true`
- `GET /api/v1/rds/reservation-coverage`
- `GET /api/v1/rds/reservation-utilization`

Coverage supports filters for account, Region, engine, family, coverage status, and coverage scope. Utilization supports account, Region, and engine.

## IAM

The existing account role already includes:

- `ce:GetReservationCoverage`
- `ce:GetDimensionValues`

Task 23.30 adds `rds:DescribeDBClusters` to the RDS inventory policy because topology and Aurora storage configuration must be verified instead of inferred.

## Invariants

The engine validates:

- `covered_units <= required_units`
- `allocated_units <= total_units`
- non-negative uncovered/unused units
- coverage/utilization percentages in `[0, 100]`
- sum of allocations for each reservation does not exceed its capacity

All arithmetic is performed with `Decimal`. Rounding is left to presentation.

## Known limitation

The current DeepOps AWS account schema stores whether an account is a management account, but it does not persist a verified Organization/payer billing-scope identifier plus RI discount-sharing preference. For that reason, cross-account matching is implemented and unit-tested through `BillingScopeContext`, but default production runs do not infer cross-account eligibility from tenant membership or `is_management_account` alone. This intentionally prevents false-positive coverage until verified billing-scope metadata is available.
