# Operational opportunity archiving

Task 24.6 makes operational archiving a complete workflow while preserving the separation introduced by Tasks 24.4 and 24.5.

## Archive is not lifecycle

Archiving means **removing a Finding from the current operational backlog without changing the human decision or technical presence**.

An archive transition changes only the operational archive dimension (`archived_at`, `archived_by`, `archive_reason`) and records `OpportunityArchiveHistory`. It does not implicitly change:

- `status` (`open`, `treated`, `rejected`);
- `presence_status` (`active`, `missing`, `resolved_externally`);
- treatment/rejection timestamps or notes;
- `first_seen_at` / `last_seen_at`;
- technical observations.

Examples:

```text
OPEN     -> archive -> status=open,     archived=true
TREATED  -> archive -> status=treated,  archived=true
REJECTED -> archive -> status=rejected, archived=true
```

## Archive is not a historical snapshot

Operational archive and historical cycle snapshot are independent concepts:

- **archive** mutates the live Finding's visibility in the current backlog;
- **snapshot** appends an immutable representation of a period into `OpportunityHistorySnapshot`.

A period-close workflow may execute both operations together, but an archived Finding is never treated as the historical snapshot itself.

When combined close is used, snapshots are generated first from the pre-archive state. The archive mutation happens afterwards in the same caller transaction. A later archive, collection or lifecycle transition cannot rewrite the snapshot.

## API operations

### Individual

```text
POST /opportunities/{id}/archive
```

Requires operator access. The endpoint uses the existing row-locked, idempotent archive path. Repeating archive on an already archived Finding does not create duplicate archive history.

### Bulk by IDs

```text
POST /opportunities/bulk/archive
```

Example:

```json
{
  "opportunity_ids": ["id-1", "id-2"]
}
```

The request deduplicates IDs, locks Findings in deterministic ID order and commits once. Already archived rows are counted but do not fail the operation or create a second archive history event. An unknown ID makes the request fail without partial mutation.

The explicit-ID API accepts at most 500 distinct IDs. Larger scopes should use server-side filter archiving.

### Preview by filter

```text
POST /opportunities/archive-preview
```

Preview is read-only. It uses the same `OpportunityFilters` semantics as the operational list and reports:

- matching active and already archived counts;
- `to_archive`;
- status/provider/account distribution;
- per-currency current cost and estimated savings;
- deterministic `filter_hash`.

No implicit currency conversion is performed.

### Archive by filter

```text
POST /opportunities/archive-by-filter
```

The server resolves the complete matching set. Pagination is deliberately absent, so an action over 3,842 matching Findings operates on all 3,842, not only the 50 visible in the browser.

The service forcibly targets `archived_at IS NULL` regardless of the client. The filter implementation is shared with the list query; there is no second hand-written filtering language.

An empty filter is rejected unless the client explicitly sends:

```json
{
  "filters": {},
  "archive_all": true
}
```

This prevents an accidentally empty frontend payload from silently archiving the whole backlog.

## Correlation and audit

Every bulk operation receives one `correlation_id`. Every Finding actually changed by that operation records the same correlation in `OpportunityArchiveHistory.context` together with the operation kind (`bulk`, `filter` or `period_close`).

The administrative audit is aggregate:

- `opportunity.archive` for individual archive;
- `opportunity.bulk_archive` for explicit-ID bulk;
- `opportunity.archive_by_filter` for filtered bulk;
- `opportunity.period_close` for combined period close.

Large operations do not emit one `AuditEvent` per Finding. Audit metadata stores bounded samples and counts instead of unbounded ID lists.

## Period close

The explicit **Fechar período** operation is administrative and composes Task 24.5 with operational archiving:

1. preview the cycle and archive scope;
2. report CollectionRun coverage;
3. reject execution if any CollectionRun in the cycle is `RUNNING`;
4. generate immutable snapshots;
5. transition the cycle to `CLOSED`;
6. archive the chosen live Findings;
7. write aggregate audit metadata;
8. commit once.

A `FAILED` CollectionRun is reported in preview but does not block close. The historical snapshot naturally reflects only observations that actually exist.

Snapshot generation, cycle transition and operational archive share the route transaction. If any required step fails, the route rolls the transaction back. A failed combined close must not leave a closed cycle with an incomplete archive, nor an archived backlog without the requested snapshots.

Ordinary individual/bulk/filter archive never closes a historical cycle.

## Rediscovery after archive

Existing product rules remain authoritative:

### OPEN

An archived OPEN Finding can be automatically returned to the operational backlog when the same fingerprint is observed again, according to the existing rediscovery behavior. There is no persistent human suppression decision to preserve.

### TREATED

An archived TREATED Finding follows the existing treatment-review behavior. Rediscovery may auto-unarchive it and set `needs_review=true`.

### REJECTED

Task 24.4 remains authoritative. Rediscovery may update observations and technical presence, but it does not auto-unarchive or reopen a rejected Finding. Returning it to the backlog requires explicit `reopen`.

## Operational visibility and summaries

Default opportunity queries and operational stats target active, non-archived Findings. Archived Findings remain available from the operational History view and through archive history/details. Historical cycle snapshots remain independently queryable.

After mutations the frontend invalidates opportunity and dashboard query state so the backlog, counters, History and operational summaries refresh without a manual browser reload.

## Volume strategy

The current architecture expects period scopes in the low thousands. Filter archiving therefore remains synchronous and transactional, capped at 20,000 active Findings per operation. Explicit-ID bulk is capped at 500 IDs.

For filter operations the server resolves only the matching IDs first, then locks and mutates Findings in deterministic batches of 500. Each batch is flushed but never committed independently. Dashboard summary scopes are deduplicated and refreshed only after all batches have been applied. This bounds ORM object materialization while preserving one all-or-nothing transaction and one aggregate audit event.

This preserves atomicity without introducing a partial-success background job merely for Task 24.6. If production scale later requires tens or hundreds of thousands of rows in one operation, the next design should introduce a durable job entity with explicit status/retry/compensation semantics instead of adding hidden per-batch commits.

## Monthly example

At the end of October 2026:

```text
cycle: 10/2026 (OPEN)
observed opportunities: 1,842
active operational backlog in chosen scope: 1,800
failed CollectionRuns: 3
running CollectionRuns: 0
```

The preview shows 1,842 snapshots and 1,800 operational archives. Confirmation creates the immutable October snapshots, closes the cycle and archives the 1,800 live Findings in the chosen scope.

A November collection can then:

- re-surface a previously archived OPEN Finding under the normal rediscovery rule;
- re-surface a TREATED Finding with review semantics;
- continue observing a REJECTED Finding without returning it to backlog;
- create a new OPEN Finding for a genuinely new fingerprint.

The October snapshots remain unchanged in every case.
