# Aven Reports

## Goals

Task 24.15 establishes the Aven reference for asynchronous operational history, status-oriented processing and report-like execution results without inventing a file-generation subsystem that does not exist in the product.

The user-facing Reports experience is exposed through the existing `/collections` route. The route remains unchanged for compatibility; the Application Shell label and page title are **Relatórios**.

```text
Aven Application Shell
↓
PageHeader
↓
Supported operational action
↓
FilterBar
↓
Report History
↓
Status / Result
↓
Supported action
```

## Existing Report Architecture

The audit found **no independent Reports domain, `/reports` frontend route, `/reports` backend route, report-file generation queue, signed-download endpoint or generated-file storage contract**.

The real asynchronous history architecture is:

```text
Manual collection action
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

`CollectionRun` is therefore the current history/result record surfaced by Reports. Task 24.15 modernizes that real architecture rather than creating a parallel report engine.

The lower-level `/scans` endpoint is preserved. Reports uses the richer CollectionRun contract because it already provides provider/account context, server-side filters, pagination, sorting, retained-detail semantics and efficient conditional polling.

## Page Composition

The page follows the Aven Golden Reference:

1. `PageHeader`;
2. supported primary action and refresh;
3. `FilterBar`;
4. optional account context;
5. `Section` containing Report History;
6. official `Table`;
7. official `Pagination`;
8. detail `Section` for a selected `CollectionRun`.

The page owns orchestration and URL state. Visual contracts come from `frontend/components/aven/` and `frontend/components/ui/`.

## Report Generation

Report-file generation is **N/A** in the current product architecture.

The existing manual action is **Iniciar coleta**, not “Gerar relatório”. It preserves the real mutation:

```text
POST /cloud-accounts/{id}/scans
```

Task 24.15 preserves its permissions, provider capability checks, duplicate-submit protection and query invalidation while migrating presentation to the official `Dialog`, `Select`, `Button`, `Alert` and `Toast` primitives.

The asynchronous success feedback is:

> Coleta enviada para processamento

The UI never claims that a report file was generated.

## Report Parameters

There is no report-file generation form and therefore no file-format parameter contract.

The existing manual collection action preserves only parameters actually accepted by its flow:

- provider/cloud;
- connected cloud account.

The account's configured scope remains authoritative.

The history query preserves the real filters:

- provider;
- native account ID;
- CollectionRun status;
- `date_from`;
- `date_to`;
- analyzer version.

No report type, PDF/CSV/XLSX/JSON format, environment, file-retention option or unsupported submit parameter is invented.

## Report History

Report History is backed by `GET /collections` and preserves:

- server-side filtering;
- server-side sorting;
- server-side pagination;
- page sizes 25 / 50 / 100;
- default `started_at desc` ordering;
- `opportunities_found` as the existing alternate sort field;
- URL-owned filter/sort/page state;
- previous-data behavior while fetching;
- detail prefetch on row interaction.

The table prioritizes Report/execution time, scope, status, duration, resources and opportunities so 1366×768 remains useful without adding unsupported columns.

## Status Model

The real CollectionRun status contract is exactly:

| Backend status | Aven presentation | Terminal |
|---|---|---|
| `RUNNING` | Pending / Em andamento | No |
| `SUCCESS` | Success / Concluída | Yes |
| `FAILED` | Danger / Falhou | Yes |

A `SUCCESS` run with persisted warnings is presented with warning semantics without inventing another backend status.

A failed CollectionRun remains a valid history row. It is process state, not a page-load failure. Status never depends only on color because `StatusIndicator` provides text and icon semantics.

## Polling / Refresh

The existing polling lifecycle is preserved:

```text
interval: 15 seconds
only while at least one CollectionRun is RUNNING
only while document.visibilityState === "visible"
stop when no RUNNING item remains
clear interval on dependency change/unmount
```

Detail polling follows the same rule. Manual refresh remains available.

Theme preference is not part of the query key or timer lifecycle, so Light/Dark/System changes do not create report refetches, new timers, filter resets or pagination resets.

## Download

Download behavior: **N/A**.

The audit found no generated report file, download endpoint, signed URL, file path or file-availability field. Task 24.15 therefore renders no fake or disabled Download action and generates no files in the frontend.

A future download action must be backed by a real backend file-availability contract before it can appear.

## Actions

Supported actions:

- start a manual collection when role/provider/account capabilities allow it;
- refresh history/detail;
- open CollectionRun detail;
- inspect comparison data while detailed observations are retained;
- open opportunities associated with a retained CollectionRun.

Unsupported and intentionally absent:

- file download;
- retry failed report job;
- regenerate report file;
- cancel;
- delete.

### Status/action matrix

| Status | View detail | Retained opportunities/comparison | Download | Retry | Cancel | Delete |
|---|---|---|---|---|---|---|
| `RUNNING` | Yes | Retention dependent | N/A | No | No | No |
| `SUCCESS` | Yes | Retention dependent | N/A | No | No | No |
| `FAILED` | Yes | Retention dependent | N/A | No | No | No |

## Filters

`FilterBar` preserves the existing submit semantics.

Provider uses `ProviderSelector`. Account uses `AccountSelector` for available account options. The reusable selector now supports an optional `onSearchChange` hook for server-backed option-search integrations without creating a Reports-only selector.

The backend period contract is datetime-based and applies `[date_from, date_to)` to `started_at`. The current official `DateRangePicker` is date-only, so Reports deliberately keeps official `Input type="datetime-local"` controls rather than silently dropping time-of-day/timezone boundaries.

## Sorting

Sorting remains server-side and limited to the existing allowlist:

- `started_at`;
- `opportunities_found`.

Direction remains `asc` / `desc`. No client-side re-sort over a paginated sample is introduced.

## Pagination

Pagination remains server-side through the official `Pagination` primitive. Filtering/sorting resets to page 1 through the existing `patchCollectionQuery()` contract. History is never loaded unbounded.

## Loading

Initial list/detail loads use structural `Skeleton` states. Polling refresh keeps existing rows visible and updates status/data in place instead of replacing the table with skeletons.

## Empty

The page distinguishes:

- no report-like executions processed yet;
- no results for current filters;
- an empty later page.

Filtered empty state offers clear-filters behavior.

## Error

Load failures use `Alert` and retry where appropriate. CollectionRun `FAILED` is not confused with an API-load failure.

The page only surfaces persisted/safe error detail already provided by the backend; it does not add raw stack traces, credentials, tokens or storage internals.

## File Formats

Generated file formats: N/A.

No PDF, CSV, XLSX or JSON generation contract exists in the audited architecture, and Task 24.15 does not emulate one.

## Report Branding

The migrated experience uses Aven public branding through Application Shell and the Aven Design System.

Generated PDF branding: N/A.

CSV/XLSX branding: N/A.

No visible DeepOps or NuvemIQ branding is introduced in the migrated Reports experience.

## Light Theme

Light uses the Golden Reference semantic surface, text, action and status tokens. No Reports-specific palette is introduced.

## Dark Theme

Dark uses Theme Engine semantic remapping. Table, filters, statuses and dialog remain legible without local dark branches, neon or glow.

## Responsive Behavior

The page remains inside Application Shell scroll ownership and targets 1280 / 1366 / 1440 / 1600 / 1920 / 2560 plus narrower layouts.

At smaller widths filters reduce from three columns to two and then one, metadata grids stack, header/section actions stack, and the official Table wrapper owns horizontal containment. No global page overflow or second viewport-height scroll owner is introduced.

## Accessibility

The migrated experience uses semantic heading composition, real form labels, semantic tables, text + icon status semantics, official Dialog focus behavior, Button loading state, Alerts, accessible Pagination and primitive focus-visible behavior.

Status never relies only on color.

## Performance

Task 24.15 adds no report endpoint and no new polling family.

Preserved behavior:

- list query remains server-side;
- options query remains metadata-scoped;
- existing option lookup stays bounded/debounced where used;
- polling occurs only while `RUNNING` exists;
- hidden tabs do not poll;
- terminal histories keep no timer alive;
- manual mutation invalidates existing dashboard/collection query families;
- theme is absent from report query keys.

## Legacy Migration

Removed/replaced on the migrated Reports surfaces:

- legacy PageHeader consumption;
- legacy collection status presentation;
- legacy panel/table/button composition in CollectionWorkspace;
- custom native-dialog styling in the manual launcher;
- hardcoded launcher spacing/radius/colors/typography;
- absolute-positioned primary action outside PageHeader.

Preserved:

- `/collections` route;
- CollectionRun model and API contracts;
- manual scan mutation;
- permissions/capability checks;
- query/filter/sort/pagination behavior;
- comparison behavior;
- conditional polling lifecycle.

Legacy styles still used by unrelated comparison surfaces are not deleted only for cleanup.

## Golden Reference Alignment

Task 24.15 reuses:

- Task 24.10: PageHeader, Section hierarchy, loading/empty/error composition;
- Task 24.11: FilterBar and dense-table behavior;
- Task 24.13: provider/account context, Table and Pagination;
- Task 24.14: status/action prioritization and clear feedback.

Reports becomes the Aven reference for asynchronous status, background processing history, terminal/non-terminal state, conditional polling, and future generated-file/download workflows only after a real backend contract exists.

## Functional Regression Gate

```text
Report generation preserved?
N/A — no report-file generation contract exists; existing manual collection submission remains preserved.

Report parameters preserved?
N/A for report-file generation; YES for existing manual collection parameters and history filters.

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

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

`lint:brand` remains authoritative for visible legacy branding.

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
