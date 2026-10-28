# Aven Inventory

Task 24.13 establishes `/inventory` as the Aven cloud-resource exploration experience on top of the functional Inventory foundation delivered by Tasks 24.13A, 24.13B and 24.13C.

The page is presentation and query composition only. It does not rediscover cloud resources, derive Inventory from Findings, or move provider business logic into the browser.

## Persisted Query Boundary

The supported runtime path is:

```text
AWS / OCI
    ↓
Inventory Discovery
    ↓
Inventory Persistence
    ↓
Inventory Query API
    ↓
Aven Inventory
```

The frontend consumes only persisted HTTP contracts:

```text
GET /inventory/resources
GET /inventory/options
```

The Inventory page must not call AWS SDK, OCI SDK, collection executors or discovery services directly. Provider refresh remains a collection/discovery responsibility outside this page.

## Page composition

The experience uses the official Aven stack:

```text
PageHeader
↓
FilterBar
↓
Inventory overview MetricCards
↓
Resource explorer Table
↓
Pagination
```

The resource table composes existing Product Components rather than duplicating domain presentation:

```text
ProviderBadge
ResourceIdentifier
StatusIndicator
DataState
```

## Default Active Scope

The page defaults to:

```text
presence_status = active
sort = last_seen_at
direction = desc
page = 1
page_size = 50
```

This keeps the primary view focused on currently observed resources without deleting or hiding historical Inventory semantics.

Users may explicitly choose:

```text
Active resources
Missing resources
All presence states
```

`All presence states` is a UI/query-state concept. The frontend omits `presence_status` from the backend request because the API interprets an omitted presence filter as all states.

## Filters and URL state

The route owns filter/query state through URL search params. Supported controls include:

```text
provider
account_id
region
resource_type
service
lifecycle_status
presence_status
search
sort
direction
page
page_size
```

Provider and account options come from the authorized Inventory options endpoint. Region, resource-type, service and lifecycle options are contextualized by provider/account where the backend supports cascading options.

Changing provider or account clears dependent filters so stale provider-specific selections do not silently constrain the next scope.

All resource filtering, search, sorting and pagination occur server-side.

## Technical Identifiers

Cloud resource IDs are first-class technical data.

`ResourceIdentifier` preserves and exposes the full persisted `resource_id`, including IDs such as:

```text
i-0123456789
vol-0123456789
arn:aws:...
ocid1.instance...
```

Friendly names never replace technical identity. When a friendly name exists, the technical identifier remains visible/copyable. When a friendly name does not exist, the resource ID becomes the primary label.

Account native IDs are also preserved alongside friendly account names when available.

## Lifecycle and presence

Inventory keeps two distinct status dimensions:

```text
lifecycle_status
presence_status
```

Lifecycle represents the normalized provider resource state, such as running, stopped or available.

Presence represents whether the persisted Inventory still observes the resource:

```text
active
missing
```

The UI does not infer missing state. That contract remains backend-owned through coverage-safe reconciliation from Task 24.13B.

## Missing Resources

Missing resources remain queryable for audit and troubleshooting.

The page must not:

- delete missing rows client-side;
- convert missing into terminated/deleted lifecycle state;
- update `last_seen_at` locally;
- fabricate a disappearance timestamp;
- hide missing resources from explicit user queries.

The default Active scope is a presentation choice only.

## Inventory and Opportunities

Inventory is independent from Findings and Opportunities.

```text
Inventory = resources that exist or existed in the cloud environment
Opportunities = analysis produced for some resources
```

The page does not use Findings as an Inventory source and does not infer savings, cost, recommendation priority or reservation state from resource presence.

## Loading, error and empty states

The experience uses official Aven states:

- `Skeleton` for initial loading;
- `StatusIndicator` for background refresh;
- `Alert` for API failures;
- `DataState` for an empty filtered result.

Keeping previous paginated data during page transitions avoids unnecessary layout collapse while preserving query identity across filter changes.

## Sorting and pagination

Sortable resource-table dimensions use the Inventory Query API whitelist:

```text
name
provider
account
resource_type
region
lifecycle_status
presence_status
last_seen_at
```

The page does not construct raw SQL or client-side sort the returned page.

Rows-per-page options are constrained to API-supported values and never bypass the backend maximum page size.

## Responsive behavior

Application Shell remains the owner of page scrolling.

Inventory does not introduce `100vh`, page-level overflow ownership or nested horizontal-scroll wrappers. The canonical `Table` primitive owns table containment while summary cards and pagination stack responsively at narrower widths.

## Theme and Hardcode Gate

Inventory is theme-agnostic and consumes semantic/foundation tokens only.

The Task 24.5 rule remains mandatory:

> No new visual component may use hardcoded colors, border radius, structural spacing or typography.

The Inventory route is included in both:

```bash
npm run lint
npm run lint:design-system
```

Theme changes do not participate in Inventory query keys and do not trigger provider or Inventory API refetches by themselves.

## Functional regression contracts

Task 24.13 preserves these boundaries:

1. Inventory data comes from persisted Inventory Query API contracts.
2. No AWS or OCI SDK request originates from the page.
3. Provider/account authorization remains backend-owned.
4. Search, filters, sorting and pagination remain server-side.
5. Technical IDs remain lossless and copyable.
6. Missing resources remain queryable.
7. Inventory remains independent from Findings and Opportunities.
8. Application Shell retains scroll ownership.
9. Light, Dark and System remain Theme Engine concerns rather than query concerns.
