# Opportunity discovery semantics

Task 24.8 separates historical discovery from collection-to-collection change detection. These concepts must not be collapsed into a generic `new` flag.

## Persistent Finding fields

- `first_seen_at`: timestamp of the first known technical observation of the logical opportunity.
- `last_seen_at`: timestamp of the most recent known technical observation.
- `first_seen_collection_run_id`: CollectionRun in which the logical opportunity was first observed. It is stable after it is established. If the source run is later removed by retention, the FK may become `NULL` while `first_seen_at` remains valid.
- `last_seen_collection_run_id`: CollectionRun that owns the chronologically latest observation. Out-of-order ingestion must not move this pointer backwards. It may also become `NULL` if the source run is removed.

`Finding.scan_id` is not a discovery-origin field. It can change as a Finding is observed again and must not be used to answer which CollectionRun created the logical opportunity.

## Collection-relative concepts

### observed_in_run

The Finding has an `OpportunityObservation` whose `collection_run_id` is the target run. This is the meaning of the normal `collection_run_id` filter.

### first_seen_in_run

The Finding was observed in the target and `first_seen_collection_run_id == target.id`. This is the historical first appearance.

### new_vs_previous

The Finding is observed in the target but not in its comparable baseline. The baseline is the previous successful CollectionRun for the same provider/account and compatible collection scope. A first collection without a baseline is **not** treated as `new_vs_previous`.

For operational Dashboard metrics, rejected or archived Findings are excluded from the attention-oriented new count. The technical classification remains available independently.

### reappeared

The Finding is observed in the target, absent from the baseline, and its historical first CollectionRun is not the target. It existed before, disappeared from the immediately comparable baseline, and returned.

### continued

The Finding is observed in both target and baseline.

### no_longer_detected

The Finding is observed in the baseline and not in the target, but only when the target has authoritative successful scope coverage for the Finding's provider/account/rule/region. A failed or uncovered target scope is not interpreted as absence.

## Three-run example

Assume the same AWS account and compatible scope:

| Run | Observations |
| --- | --- |
| Run A | X, Y |
| Run B | Y, Z |
| Run C | X, Y, W |

For Run C compared with Run B:

- `observed_in_run`: X, Y, W
- `first_seen_in_run`: W
- `continued`: Y
- `new_vs_previous`: X, W
- `reappeared`: X
- `no_longer_detected`: Z, if Run C had authoritative coverage for Z's scope

X is therefore new relative to the previous run but is **not** a historically new opportunity.

## Baseline and compatibility

Comparison is account-local. AWS is never compared with OCI and one account is never compared with another. The existing collection-comparison compatibility rules are reused when selecting the previous successful run.

If there is no baseline, comparison metadata reports `comparable=false` and `reason=NO_BASELINE`. If retained detailed observations are unavailable, the comparison is also not treated as complete.

`analyzer_version` divergence is exposed through `rules_version_changed`/warnings rather than hidden. A missing version on either side is reported as unknown.

## Temporal filters

The normal opportunities API supports:

- `first_seen_from`, `first_seen_to`
- `last_seen_from`, `last_seen_to`
- `first_seen_collection_run_id`
- `collection_run_id`
- collection-relative `discovery_type`

Timestamp ranges are semi-open: `>= from` and `< to`. UI date-only custom ranges convert the final day to the start of the following local day. `last_24h`, `last_7d`, and `last_30d` are moving windows. `today` uses the browser/application-local day boundary.

The UI defaults temporal discovery to `first_seen`. `last_seen` is a separate explicit mode and is never labelled as creation.

List and stats queries share the same `OpportunityFilters` semantics and are evaluated server-side before pagination.

## APIs

Normal Finding/Observation filters remain on:

- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/stats`

Collection-relative classification is also exposed explicitly through:

- `GET /api/v1/collections/{run_id}/opportunity-changes`
- `GET /api/v1/collections/{run_id}/opportunities?discovery_type=...`

Supported discovery types are `observed`, `first_seen`, `new_vs_previous`, `reappeared`, `continued`, and on the collection endpoint `no_longer_detected`.

## Retention

The new run FKs use `ON DELETE SET NULL`. Retention of CollectionRuns therefore cannot delete a Finding or invalidate `first_seen_at`/`last_seen_at`. Historical cycle snapshots remain cycle-relative and are not replaced by the global Finding fields introduced here.
