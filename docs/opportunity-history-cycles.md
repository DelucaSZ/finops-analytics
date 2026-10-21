# Opportunity history cycles

Task 24.5 separates three concepts that must not be conflated:

1. **Finding operational** — mutable state used by the current backlog.
2. **Archive/unarchive operational** — controls whether the Finding appears in the operational backlog.
3. **Historical cycle snapshot** — immutable representation of what was known and what human lifecycle state existed when a period was closed.

## Cycle model

`OpportunityHistoryCycle` stores an explicit half-open interval `[period_start, period_end)`, a label, timezone and OPEN/CLOSED state. The initial resolver uses calendar months in UTC. The interval model is intentionally generic so a later configuration can choose non-calendar periods without replacing the persistence model.

A CLOSED cycle is immutable. Closing is idempotent and serialized with a row lock. A second close does not recreate snapshots. The unique `(cycle_id, opportunity_id)` constraint provides a second line of protection against duplicates.

The close operation is database-only. It never calls AWS, OCI, Cost Explorer, Monitoring or provider APIs.

## Membership

A Finding belongs to a cycle when it has at least one `OpportunityObservation` satisfying:

```text
period_start <= observed_at < period_end
```

Membership is therefore not inferred from `Finding.created_at` or `Finding.last_seen_at`.

`occurrence_count_in_cycle` counts distinct `collection_run_id` values. The first and last observation timestamps and corresponding CollectionRun ids are also copied into the snapshot.

## Snapshot semantics

`OpportunityHistorySnapshot` is built with an explicit mapper; it is not an ORM clone of `Finding`.

Technical values come from the **latest OpportunityObservation inside the cycle**:

- severity;
- current monthly cost;
- estimated monthly savings;
- currency;
- confidence;
- bounded provider metadata and evidence;
- last CollectionRun in the cycle.

Human/operational state comes from the **Finding at close time**:

- lifecycle status (`open`, `treated`, `rejected`);
- presence status;
- `needs_review`;
- archive state/reason;
- treatment/rejection timestamps and notes;
- externally-resolved timestamp.

Identity and labels are snapshotted too (account name, resource name, title and description), so later renames do not rewrite the historical view.

The snapshot contains all fields required by the historical detail view. `opportunity_id` is only a complementary link to the current Finding. The FK uses `ON DELETE SET NULL`, so deleting a future operational Finding does not delete the historical record.

## Immutability and retention

Snapshots are append-only at the application layer: update/delete through the ORM is rejected. CLOSED cycles cannot be edited or silently reopened.

Once a cycle is closed, later collection, treatment, rejection, reopen, archive/unarchive, label changes or price changes affect only the live Finding/future cycles. Deleting old `OpportunityObservation` rows does not remove the essential historical fields already materialized in the snapshot.

Existing retention jobs continue to act on operational Findings and do not target history cycle/snapshot tables. A future history-retention policy must be explicit.

## Rejected opportunities

Task 24.4 suppression semantics remain authoritative. A rejected Finding that is observed again is not automatically reopened or unarchived by historical cycling. It may legitimately produce a rejected snapshot in multiple periods while the earlier snapshots remain unchanged.

## Multi-currency

Historical amounts are never converted implicitly. Each snapshot stores amount plus currency. Cycle statistics group cost and potential savings by currency; for example USD and BRL totals remain separate.

## Collection coverage and close safety

CollectionRun coverage uses `CollectionRun.started_at` consistently and reports total/SUCCESS/FAILED/RUNNING counts for the cycle interval. A cycle cannot close while a RUNNING CollectionRun belongs to the period; the API returns a conflict instead of creating a potentially partial historical close.

Close executes in the caller transaction. If snapshot generation, cycle update or audit persistence fails, the caller rolls back, leaving the cycle OPEN without a partially committed close.

## Legacy history

Historical archive data created before Task 24.5 is not backfilled with fabricated period snapshots. The existing archived/legacy view remains valid for those records. Immutable cycle snapshots are authoritative only for cycles explicitly closed by the new mechanism.

## Audit

A successful close writes one aggregate `AuditEvent` (`opportunity_cycle.close`) in the same transaction. It records cycle identity, period, snapshot count, per-currency totals and collection coverage. Snapshot creation does not emit one AuditEvent per row.

## Example

October 2026 closes with:

```text
EC2 i-123
status: OPEN
estimated savings: USD 500/month
```

The same logical Finding can later close in November 2026 as:

```text
EC2 i-123
status: TREATED
estimated savings: USD 350/month
```

Both snapshots remain queryable independently. November never rewrites October.
