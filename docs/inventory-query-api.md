# Inventory Query API

Task 24.13C exposes the provider-neutral Inventory persisted by Tasks 24.13A/24.13B. HTTP requests never invoke AWS, OCI, discovery adapters, or collection executors. The request path is strictly:

```text
Aven frontend -> Inventory Query API -> InventoryQueryService -> PostgreSQL/InventoryResource
```

The API is mounted under `/api/v1/inventory` and requires the existing authenticated user session. The current product authorization model grants authenticated users read access to the configured `CloudAccount` set; Inventory centralizes that account scope in `InventoryQueryService` so future account-level ACLs can replace the scope without changing endpoint contracts.

## `GET /api/v1/inventory/resources`

Returns a server-side paginated collection:

```json
{
  "items": [],
  "page": 1,
  "page_size": 50,
  "total": 0,
  "total_pages": 0
}
```

`page` defaults to `1`. `page_size` defaults to `50` and is capped at `100`. `total` is calculated after all authorization/search/filter predicates and before `OFFSET/LIMIT`; `total_pages` is `ceil(total / page_size)` and is `0` when `total == 0`.

Supported filters are `provider`, `account_id`, `region`, `resource_type`, `lifecycle_status`, `presence_status`, and `service`. Filters compose with `AND`. This first version intentionally uses one value per filter rather than introducing custom multi-value parsing. `presence_status` is not defaulted by the API: callers that want the normal Inventory view should explicitly send `presence_status=active`, while `missing` resources remain queryable.

`provider` uses the product provider canonicalizer; syntactically unsupported provider names return HTTP 422. Regions and resource types are persisted-domain strings and are never validated against a hardcoded AWS/OCI list.

### Search

`search` is trimmed, limited to 256 characters, and executed in the database as a case-insensitive substring match over:

- `name`;
- `resource_id`;
- `native_account_id`;
- `resource_type`;
- `service`;
- `region`.

`%`, `_`, and the SQL `LIKE` escape character are escaped before the parameterized predicate is built. Search never casts/scans `tags` or `attributes` JSON.

### Sorting

`sort` is an enum/whitelist and supports:

- `name`;
- `provider`;
- `account`;
- `resource_type`;
- `service`;
- `region`;
- `lifecycle_status`;
- `presence_status`;
- `first_seen_at`;
- `last_seen_at`.

`direction` accepts only `asc` or `desc`. The default is `last_seen_at DESC`. Every sort adds `id` in the same direction as a deterministic tie-breaker, so equal primary sort values do not produce unstable page ordering. User input is never interpolated into raw SQL or passed to `order_by(text(...))`.

Example:

```http
GET /api/v1/inventory/resources?presence_status=active&page=1&page_size=50&sort=last_seen_at&direction=desc
```

Combined example:

```http
GET /api/v1/inventory/resources?provider=aws&account_id=17&region=us-east-1&resource_type=compute_instance&lifecycle_status=running&presence_status=active&search=api
```

The resource contract is explicit and includes product/native account identity, account name, provider-neutral/native resource type, service/location, normalized/native status, sanitized tags/attributes, presence state, and first/last seen timestamps. List serialization does not expose SQLAlchemy models directly. `account_name` is resolved in the same joined query as resources, avoiding N+1 queries.

## `GET /api/v1/inventory/options`

Returns filter options derived from Inventory rows visible in the same authorization scope:

```json
{
  "providers": ["aws", "oci"],
  "accounts": [
    {
      "id": 17,
      "name": "Production",
      "native_account_id": "123456789012",
      "provider": "aws"
    }
  ],
  "regions": ["sa-saopaulo-1", "us-east-1"],
  "resource_types": ["compute_instance"],
  "services": ["Compute", "EC2"],
  "lifecycle_statuses": ["running"],
  "presence_statuses": ["active", "missing"]
}
```

No option is hardcoded. `provider` and `account_id` may be supplied to cascade the option set to the current provider/account context. Values are selected with database `DISTINCT`; facet counts are intentionally not included in the first version.

## `GET /api/v1/inventory/resources/{id}`

Returns one current-state Inventory resource using the same authorization scope. Missing and inaccessible resources deliberately share the same HTTP 404 response, avoiding existence disclosure. Detail adds `first_seen_collection_run_id`; the list/detail contracts expose collection-run IDs only as scalar references and never load a `CollectionRun` object or observation history.

## Security

All endpoints use the existing session-based `require_user` dependency. Inventory does not create a parallel provider/account authentication mechanism. Query construction uses SQLAlchemy expressions and bound parameters. Sort fields and direction are enums, and search is escaped/parameterized.

`tags` and `attributes` are revalidated with the Inventory metadata guardrails before HTTP serialization. Credential-bearing keys, excessive nesting/non-JSON content, and oversized Inventory metadata therefore cannot be returned through the public contract even if a row bypassed the normal persistence service.

Responses are marked `Cache-Control: no-store` by the existing sensitive-response middleware.

## Performance model and index review

Filtering, search, sorting, counting, `OFFSET/LIMIT`, and distinct filter-option queries execute in the database. The API never calls `.all()` and filters in Python. Resource list queries join `cloud_accounts` once to resolve `account_name`; the count query stays on `inventory_resources` and does not load JSON/relationships.

The 24.13A indexes were reviewed against these access patterns. They already cover provider, CloudAccount, native account identity, resource type, `last_seen_at`, `cloud_account_id + presence_status + resource_type`, `provider + cloud_account_id + region`, and `cloud_account_id + lifecycle_status`. For the initial 10k-100k target, no additional PostgreSQL extension or speculative combinatorial index was added. The dominant page order can use the existing `last_seen_at` index, and scoped filters use the existing composites. `region`-only or `service`-only workloads should be observed in production before adding more indexes.

No `pg_trgm`, Redis cache, Inventory-specific rate limiter, or provider-specific attribute index is introduced in this task.

## Known limitations

- Search does not inspect `tags` or `attributes`.
- Provider-specific attribute filters such as instance type, OCI shape, engine, or volume type do not exist yet.
- Inventory contains only resource types currently emitted by AWS/OCI discovery.
- Inventory does not infer or expose per-resource cost, savings, recommendations, Findings, or Opportunities.
- Historical `InventoryResourceObservation` querying is not part of the public API yet.
- This version accepts one value per filter query parameter; multi-value OR semantics can be added later without changing the core query service.
- The product currently has global authenticated read access to configured CloudAccounts rather than a per-user CloudAccount membership table. Inventory preserves that existing authorization model and centralizes the scope for a future ACL implementation.

## Task 24.13 readiness

The Aven Inventory page can now obtain current resources, filter options, account names, search/sort/pagination metadata, and resource details exclusively through HTTP. It does not need AWS/OCI clients, collection executors, discovery internals, Findings, or client-side full-inventory filtering/sorting/pagination.
