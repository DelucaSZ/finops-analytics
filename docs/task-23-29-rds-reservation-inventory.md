# Task 23.29 — RDS Reservation Inventory

## Scope

This task establishes the persistent Amazon RDS inventory required by the future
reservation coverage engine. It intentionally does **not** implement matching,
coverage, normalized units, size flexibility, savings, purchase recommendations
or expiration alerts.

## Inventory

The collector inventories every enabled AWS account registered in DeepOps and
every region configured for that account.

### DB Instances

Source API: `rds:DescribeDBInstances`.

Persisted data includes account/region, identifiers and ARN, DB instance class
and its parsed family/size, original and normalized engine, version, status,
Multi-AZ, availability zones, license model, storage attributes, public access,
cluster/VPC identifiers, tags, processor features, option/parameter group
metadata, AWS creation time, collection time and last-seen time.

`coverage_eligible` is only a workload-status classification. It does not mean a
reservation covers the instance.

### Reserved DB Instances

Source API: `rds:DescribeReservedDBInstances`.

Persisted data includes reservation/offering IDs, DB instance class and parsed
family/size, ProductDescription and normalized engine, instance count, Multi-AZ,
offering type/class, currency, fixed/usage prices, recurring charges, state,
lease ID, start time, duration in seconds, expiration, collection time and
last-seen time.

`expiration_at` is calculated as `StartTime + Duration`, where the AWS API
returns `Duration` in seconds. `days_until_expiration` is derived when the API
response is generated so it cannot become stale in storage.

## Reconciliation and failure isolation

Natural keys are:

- DB Instance: `cloud_account_id + region + DBInstanceArn`;
- reservation: `cloud_account_id + region + ReservedDBInstanceId`.

Collection is idempotent. Existing rows are updated and newly observed rows are
inserted. A previously known row is marked `is_active=false` only after the
complete paginated collection for that resource type and region succeeds. This
prevents a failed or partial AWS call from incorrectly deactivating inventory.

Account, region and resource-type failures are isolated. AWS SDK adaptive retry
configuration is reused from the existing assume-role path. Tag collection is
best-effort and never discards the parent DB Instance.

## API

All endpoints use the existing DeepOps administrator authorization dependency.

- `POST /api/v1/rds/collect`
- `GET /api/v1/rds/instances`
- `GET /api/v1/rds/reservations`

The GET endpoints support account, region, engine and instance-class filters.
Instances additionally support status; reservations support state and expiration
range filters. Both default to active inventory and provide pagination.

The collector can also be run from the backend environment:

```bash
python -m app.commands.rds_inventory
python -m app.commands.rds_inventory --cloud-account-id 123
```

## IAM

The target role needs only these RDS read actions for this feature:

```json
{
  "Effect": "Allow",
  "Action": [
    "rds:DescribeDBInstances",
    "rds:DescribeReservedDBInstances",
    "rds:ListTagsForResource"
  ],
  "Resource": "*"
}
```

No RDS write permission is introduced.

## Explicitly deferred to Task 23.30+

The inventory does not perform reservation-to-workload matching, cross-account
sharing, consolidated-billing rules, normalized units, size flexibility,
coverage calculations, partial coverage, Cost Explorer reservation coverage,
savings estimates, purchase recommendations or alert generation.
