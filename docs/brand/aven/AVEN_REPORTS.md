# Aven Reports

## Goals

Task 24.15 establishes the Aven reference for asynchronous operational history, status-oriented processing and report-like execution results without inventing a file-generation subsystem that does not exist in the product.

The user-facing Reports experience is exposed through the existing `/collections` route. The route is preserved for compatibility; the Application Shell label and page title are now **Relatórios**.

The design goal is:

```text
Aven Application Shell
↓
PageHeader
↓
Generate / process action
↓
FilterBar
↓
Report history
↓
Status / result
↓
Supported action
```

The central product rule remains: **Complexity underneath. Clarity above.**

## Existing Report Architecture

The pre-24.15 audit found **no independent Reports domain, `/reports` frontend route, `/reports` backend route, file-generation queue, signed-download endpoint or generated-file storage contract**.

The real asynchronous reporting/history architecture already present in the product is:

```text
Manual action
↓
POST /cloud-accounts/{cloud_account_id}/scans
↓
Scan / provider collection execution
↓
CollectionRun
↓
GET /collections
GET /collections/{collection_id}
↓
Persisted status, scope, timings and opportunity totals
```

`CollectionRun` is therefore the current report/history record. Task 24.15 modernizes that real architecture rather than fabricating a parallel report engine.

The related `/scans` endpoint remains a lower-level execution record. The Reports experience uses the richer `CollectionRun` query/detail contract because it already provides provider/account context, server-side filters, server-side pagination, sorting, retained-detail semantics and conditional polling.

## Page Composition

The Reports page follows the authenticated Aven Golden Reference:

1. `PageHeader`
2. primary action and refresh
3. `FilterBar`
4. optional account context
5. `Section` containing Report History
6. official `Table`
7. official `Pagination`
8. detail `Section` for a selected `CollectionRun`

The page owns orchestration and URL state. Visual contracts come from `frontend/components/aven/` and `frontend/components/ui/`.

No Reports-specific button, badge, table system or theme branch is introduced.

## Report Generation

There is no generated-file report engine today.

The only existing manual generation-like action is the existing cloud analysis mutation:

```text
POST /cloud-accounts/{id}/scans
```

Task 24.15 preserves that action, permissions, provider capability checks, duplicate-submit protection and query invalidation. It is presented through the official Aven `Dialog`, `Select`, `Button`, `Alert` and `Toast` primitives.

The success copy is intentionally asynchronous:

> Relatório enviado para processamento

The UI does not claim that a file has already been generated.

## Report Parameters

The manual action preserves the parameters actually supported by the backend:

- provider/cloud;
- connected cloud account.

The account's existing configured scope remains authoritative.

No report type, PDF/CSV/XLSX/JSON format, environment, arbitrary date range or file-retention parameter is added to the submit mutation because those parameters do not exist in the current backend contract.

The history query preserves the existing real filters:

- provider;
- native account ID;
- CollectionRun status;
- `date_from`;
- `date_to`;
- analyzer version.

## Report History

Report History is backed by:

```text
GET /collections
```

The page preserves:

- server-side filtering;
- server-side sorting;
- server-side pagination;
- `page_size` values of 25, 50 and 100;
- default ordering by `started_at desc`;
- `opportunities_found` as the existing alternate sort field;
- URL-owned filter/sort/page state;
- previous-data behavior while a new page/filter request is fetching;
- detail prefetch on row interaction.

The table prioritizes:

- Report / execution time + technical ID;
- scope (provider + account);
- status;
- duration;
- resources analyzed;
- opportunities found.

This keeps the 1366×768 information horizon useful without adding columns for data the backend does not expose.

## Status Model

The real CollectionRun status contract is exactly:

| Backend status | Aven presentation | Terminal |
|---|---|---|
| `RUNNING` | Pending / Em andamento | No |
| `SUCCESS` | Success / Concluída | Yes |
| `FAILED` | Danger / Falhou | Yes |

A successful run with persisted warnings is presented as a warning-oriented completed state rather than inventing a fourth backend status.

Status is never color-only: `StatusIndicator` supplies label and icon semantics.

A failed CollectionRun remains a valid history row. It is business/process state, not a page-load failure.

## Polling / Refresh

The existing efficient polling lifecycle is preserved:

```text
poll interval: 15 seconds
only while at least one visible CollectionRun is RUNNING
only while document.visibilityState === "visible"
stop automatically when no RUNNING item remains
clear interval on dependency change/unmount
```

Detail polling follows the same rule for a selected `CollectionRun`.

Manual refresh remains available.

Theme preference is not part of the query key or polling lifecycle. Switching Light/Dark/System therefore does not start a new timer, reset filters, reset pagination or cause a report refetch by design.

## Download

Download behavior: **N/A**.

The audit found no generated report file, download endpoint, signed URL, file path or file-availability field in the current report/history architecture.

Task 24.15 therefore does **not** render a disabled or fake Download action and does not generate files in the frontend.

When a future backend adds a real generated-file contract, the action must be enabled only from backend-confirmed file availability and should use the official Button/IconButton patterns.

## Actions

Current supported actions are:

- generate/start a new manual execution, when the current user role and provider/account capabilities allow it;
- refresh history/detail;
- open a CollectionRun detail;
- inspect comparison data while detailed observations are retained;
- open opportunities associated with a retained CollectionRun.

Current unsupported actions are intentionally absent:

- file download;
- retry failed job;
- regenerate same parameters as a distinct backend report action;
- cancel;
- delete.

### Status/action matrix

| Status | View detail | View retained opportunities/comparison | Download | Retry | Cancel | Delete |
|---|---|---|---|---|---|---|
| `RUNNING` | Yes | Backend retention dependent | N/A | No | No | No |
| `SUCCESS` | Yes | Backend retention dependent | N/A | No | No | No |
| `FAILED` | Yes | Backend retention dependent | N/A | No | No | No |

No unsupported action is synthesized in the frontend.

## Filters

`FilterBar` preserves the existing filters and submit semantics.

Provider uses the official `ProviderSelector`.

Account uses the official `AccountSelector` for available account options. Task 24.15 extends the reusable selector with an optional `onSearchChange` hook so report pages can drive server-backed option search without inventing a Reports-only control.

The backend period contract is datetime-based and applies `[date_from, date_to)` to `started_at`. The current official `DateRangePicker` is date-only, so Task 24.15 deliberately keeps official `Input type="datetime-local"` controls rather than silently losing time-of-day/timezone boundary semantics.

This is an applicability decision, not a new date picker implementation.

## Sorting

Sorting remains server-side and limited to the existing allowlist:

- `started_at`;
- `opportunities_found`.

Direction remains `asc` / `desc`.

No client-side re-sort is introduced over a paginated sample.

## Pagination

Pagination remains server-side. The page uses the official Aven `Pagination` primitive and preserves page-size options 25 / 50 / 100.

Filtering or sorting resets the page through the existing `patchCollectionQuery()` contract.

The page never loads an unbounded report history.

## Loading

Initial list/detail loads use structural Aven `Skeleton` states.

A polling refresh does not replace already rendered rows with skeletons. Existing content remains visible while status/data refreshes, with a small `StatusIndicator` for the updating state.

## Empty

The page distinguishes:

- no reports processed yet;
- no reports matching current filters;
- an empty later page.

Filtered empty state offers a clear-filters action.

## Error

Page/query failures use official `Alert` presentation and offer retry where useful.

CollectionRun `FAILED` is not treated as a history API failure.

Failure details only use the sanitized/persisted backend `error_detail`; the page does not expose credentials, tokens, internal bucket paths or raw stack traces by adding new frontend diagnostics.

Option-loading failures remain isolated from the report-history query.

## File Formats

Generated file formats: N/A.

No PDF, CSV, XLSX or JSON generation contract exists in the audited runtime architecture.

Task 24.15 does not promise or emulate those formats.

## Report Branding

The migrated experience uses Aven public branding through the existing Application Shell and Aven Design System.

Generated PDF branding: N/A because there is no generated PDF engine in the current contract.

CSV/XLSX branding: N/A because those generated formats do not exist in the current contract.

No visible DeepOps or NuvemIQ branding is introduced in the migrated Reports experience.

## Light Theme

Light theme uses the same semantic surface/text/action/status tokens as the Aven Golden Reference. There is no Reports-specific palette.

## Dark Theme

Dark theme uses semantic token remapping from the Theme Engine. Status, table, filter and dialog readability do not depend on a page-local dark override, glow or hardcoded color.

## Responsive Behavior

Reports remains inside Application Shell scroll ownership.

The composition is designed for:

- 1280;
- 1366;
- 1440;
- 1600;
- 1920;
- 2560;
- narrower layouts.

At lower widths:

- filters reduce from three columns to two and then one;
- metadata grids stack;
- header/section actions stack when needed;
- the official Table wrapper owns horizontal containment;
- the page does not introduce global `overflow-x` or a second viewport-height scroll owner.

## Accessibility

The migrated experience uses:

- semantic `PageHeader`/section heading hierarchy;
- real form labels through `Input`, `Select`, `ProviderSelector` and `AccountSelector`;
- semantic table primitives;
- text + icon status semantics;
- native Aven `Dialog` focus/cancel behavior;
- official Button loading state for duplicate-submit protection;
- `Alert` for load/process failures;
- accessible Pagination controls;
- focus-visible behavior from the Aven primitives.

Status never relies only on color.

## Performance

Task 24.15 does not add a report endpoint or extra polling family.

Preserved request behavior:

- list query remains server-side;
- options query remains metadata-scoped;
- account option search stays debounced/server-backed where used;
- polling occurs only while `RUNNING` exists;
- hidden tabs do not poll;
- terminal histories do not keep a timer alive;
- manual mutation invalidates existing dashboard/collection query families;
- no theme-dependent query key is introduced.

## Legacy Migration

Removed/replaced from the migrated Reports surfaces:

- legacy `PageHeader` consumption;
- legacy `StatusBadge`/collection status CSS presentation;
- legacy panel/table/button composition in CollectionWorkspace;
- custom native-dialog visual implementation in the manual launcher;
- hardcoded launcher spacing/radius/colors/typography;
- absolute-positioned primary action outside the official PageHeader.

The underlying `/collections` route, CollectionRun backend model, scan mutation, query contracts and comparison behavior remain intact.

Legacy styles used by unrelated collection-comparison screens are not deleted solely for visual cleanup.

## Golden Reference Alignment

Task 24.15 reuses:

- Task 24.10: PageHeader, Section hierarchy, page rhythm, loading/empty/error composition;
- Task 24.11: FilterBar and high-density table behavior;
- Task 24.13: provider/account technical context, Table and Pagination patterns;
- Task 24.14: status/action prioritization and decision-oriented feedback.

Reports becomes the Aven reference for:

- asynchronous status;
- background processing history;
- terminal vs non-terminal state;
- conditional polling;
- generation-like submit feedback;
- future generated-file/download workflows once a real backend contract exists.

## Functional Regression Gate

```text
Report generation preserved?
YES — existing manual scan/collection submission preserved; generated-file engine N/A.

Report parameters preserved?
YES — real provider/account submission and history filters preserved.

Report history preserved?
YES

Job statuses preserved?
YES — RUNNING / SUCCESS / FAILED only.

Polling/status refresh preserved?
YES

Download behavior preserved?
N/A — no current download contract.

Retry/regenerate behavior preserved?
N/A — no current backend action.

Permissions preserved?
YES

Generated file formats preserved?
N/A — no generated file formats exist.

Theme change triggers unnecessary report refetch/polling?
NO

Frontend now generates report files itself?
NO
```

## Hardcode / Brand Gate

Migrated Reports files are included in `lint:design-system`.

Expected result:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

`lint:brand` remains authoritative for visible DeepOps/NuvemIQ references.

## Task 24.16 Readiness

```text
Is Task 24.16 ready to start?
YES

Golden page composition ready: YES
PageHeader ready: YES
Form primitives ready: YES
Section patterns ready: YES
Tabs ready: YES
Dialog/Drawer patterns ready: YES
Status patterns ready: YES
Loading/Empty/Error ready: YES
Responsive forms ready: YES
Settings can migrate without creating a new visual architecture: YES
```
