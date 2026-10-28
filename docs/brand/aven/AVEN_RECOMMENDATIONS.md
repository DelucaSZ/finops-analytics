# Aven Recommendations

Task 24.14 migrates `/opportunities` to the Aven Design System while preserving the existing recommendation engine, lifecycle mutations, server-side query contract, archive/history workflow and technical evidence model.

## Goals

Recommendations is the Aven reference for FinOps decision support. The interface must make opportunity, resource, financial impact, confidence, status and available action scannable without turning each finding into a marketing card or recreating recommendation logic in the browser.

The page follows **Clarity. Flow. Control.** and the shared Aven rule: complexity stays in the domain/query layers while the page composes the official primitives and Product Components.

## Information Architecture

```text
Aven Application Shell
↓
PageHeader
↓
Recommendation Summary
↓
Workflow tabs
↓
FilterBar + advanced context
↓
Opportunities
├── RecommendationCard for a small curated result set
└── Table for larger result sets / history
↓
Pagination / detail / existing lifecycle actions
```

The page does not take vertical-scroll ownership from the Application Shell.

## Recommendation Model

The UI consumes the persisted `Finding` / opportunity contract. It does not calculate or infer recommendation-domain outputs.

- **Opportunity** — the backend-provided recommendation title, description and rule identity.
- **Potential Savings** — `estimated_monthly_savings` with the backend-provided `currency`; it is estimated monthly savings, not realized savings.
- **Impact** — represented by the backend-provided `severity` dimension. The UI maps its existing values to semantic status presentation but does not generate severity.
- **Confidence** — the backend-provided `confidence` string. Task 24.14 preserves it as supplied and does not coerce it into a percentage because the current contract is categorical/string-based rather than an explicit percentage contract.
- **Priority** — no independent priority field exists in the current `Finding` contract, so the UI does not invent one.
- **Status** — existing human workflow status (`open`, `treated`, `rejected`) remains separate from technical presence (`active`, `missing`, `resolved_externally`).
- **Resource** — backend resource name/ID plus provider/account/region/service/type context.
- **Action** — only existing detail, treat, reject, reopen, archive and restore flows are exposed.

## Page Composition

`PageHeader`, `Section`, `MetricCard`, `FilterBar`, `Tabs`, `Table`, `Pagination`, `Alert`, `Skeleton` and `DataState` compose the page. Visual values in the migrated route use Aven tokens exclusively.

The Dashboard Golden Reference supplies page rhythm and state composition. Billing supplies analytical density and financial formatting. Reservations supplies operational status/recommendation patterns. Inventory supplies dense technical resource/provider presentation.

## Recommendation Summary

The compact summary shows data that exists without adding backend work:

- result count for the current server-side scope;
- potential monthly savings for the currently loaded page, grouped by currency;
- latest persisted detection (or latest archive timestamp in history) among loaded rows.

`/opportunities/stats` currently exposes lifecycle counts only. Therefore Task 24.14 deliberately does **not** label page-level savings as a global total.

## Filters

Primary filters reuse `FilterBar`, `ProviderSelector`, `AccountSelector`, `Input` and `Select` for search, provider, account, service, resource type, severity and rule.

Advanced filters preserve existing URL/query capabilities for region, first/last-seen time windows, collection-run context, discovery type, `current=true`, and history-specific status/presence/archive filters.

Search remains debounced and server-side. No client-side filtering is performed over a partial page.

## Opportunity Presentation

A small operational result set can use `RecommendationCard`. Larger result sets and history use the official Table primitive. This avoids rendering dozens of oversized cards while still exercising the richer recommendation hierarchy where it adds value.

Both presentations expose the same backend finding rather than querying or transforming a second dataset.

## Recommendation Card

`RecommendationCard` receives composed values only:

- backend title/description;
- `CurrencyDisplay`-based monthly savings;
- backend severity as impact;
- backend confidence;
- `ResourceIdentifier`;
- provider and status;
- account/region/service/type metadata;
- existing lifecycle actions.

The card does not execute optimization or own routing/query logic.

## Table Presentation

The dense table prioritizes recommendation, resource/provider, account/region, impact/confidence, potential savings, status and actions. The Table primitive owns narrow-layout horizontal containment. Numeric financial cells use its numeric alignment contract.

Bulk selection remains current-page selection only and uses the official Checkbox primitive. No implicit select-all across the dataset is introduced.

## Resource Context

`ResourceIdentifier` keeps long names/ARNs/OCIDs/instance identifiers usable and copyable. `ProviderBadge` communicates provider without hardcoded provider colors. Account and region remain visible in the main comparison surface.

## Potential Savings

Savings is displayed from `estimated_monthly_savings` and the exact backend `currency` metadata through `CurrencyDisplay`.

- period: `/mês`;
- zero remains zero;
- invalid/missing presentation values render unavailable rather than becoming zero;
- `cost_growth_anomaly` preserves the existing "Não estimada" semantic;
- currencies are never converted automatically;
- different currencies are never silently summed together.

The page summary groups loaded-page savings by currency and explicitly labels the scope as the current page.

## Impact

Current backend `severity` is the available impact dimension. Task 24.14 displays that value semantically and textually. No new `High/Medium/Low` value is generated in the browser; the labels map only the existing backend enum.

## Confidence

Confidence remains distinct from impact and savings. The current field is a backend string, so `PercentageDisplay` is intentionally not used. If the backend later introduces an explicit percentage score contract, it can be composed with `PercentageDisplay` without changing page architecture.

## Status

Human workflow status and technical presence are separate:

```text
human: open / treated / rejected
technical: active / missing / resolved_externally
```

`StatusIndicator` supplies icon + text + semantic treatment so status does not depend on color alone. Accepted/implemented states are not invented by this migration.

## Actions

Task 24.14 preserves existing real actions:

- view details;
- treat;
- reject;
- reopen;
- archive;
- unarchive / restore history;
- existing bulk lifecycle/archive actions.

No "Apply optimization" or automatic cloud mutation CTA is introduced. Existing dialogs/mutations remain the source of lifecycle behavior and continue to invalidate the same opportunity/dashboard query keys.

## Loading

Initial loading uses `MetricCard` loading state plus `Skeleton`. Background refetch keeps previous data and shows an updating status instead of replacing the entire page with a spinner.

## Empty

Overall empty and filtered-empty states are differentiated. The page says the engine returned no recommendations in the current state/scope; it does not claim the environment is fully optimized.

## Error

List/filter errors use `Alert` and `DataState` patterns without stack traces. Existing mutation dialogs retain their action error handling and never report success when a mutation fails.

## Light Theme

Light consumes semantic tokens through Aven components and the page CSS module. No route-level Light palette exists.

## Dark Theme

Dark uses the same component tree and semantic token roles. Financial values, resource identifiers and statuses retain contrast without neon or provider-specific hardcoded colors.

## Responsive Behavior

The page is desktop-first and follows the Golden Reference breakpoints/composition behavior:

- metric summary collapses progressively;
- RecommendationCard layout collapses to one column;
- FilterBar wraps through the shared component;
- advanced filters collapse from four to two to one column;
- Table keeps internal horizontal overflow through the primitive wrapper;
- bulk actions wrap;
- Pagination stacks on narrow layouts;
- no page-level `100vh`/vertical overflow container is introduced.

The required smoke matrix remains 1280, 1366, 1440, 1600, 1920, 2560 and narrower layouts, with 1366×768 treated as the critical density viewport.

## Accessibility

The migration uses semantic headings, native controls, accessible Tabs, labeled Select/Input/Checkbox primitives, semantic Table markup, explicit Button actions, focus-visible behavior inherited from primitives and textual StatusIndicator output. Cards are not clickable `div` containers.

## Performance

Existing query behavior is preserved:

- server-side filters/search/sort/pagination;
- 350 ms search debounce;
- `keepPreviousData` for list transitions;
- next-page and detail prefetch;
- no new provider/API calls caused by the redesign;
- no theme-driven query dependency;
- mutations invalidate the same query families as before.

Theme state is absent from opportunity query keys, so Light/Dark/System changes do not refetch recommendations or reset filters/pagination/selection.

## Legacy Migration

The `/opportunities` page stops using the legacy PageHeader, StatusBadge, page-local panel/table/button classes and legacy summary/filter composition. The legacy opportunity stylesheet remains imported at root while detail/history/dialog components that have not yet been independently removed still depend on it; shared legacy CSS is not deleted prematurely.

Task 24.14 adds `/app/opportunities` to both normal lint scope and the Aven hardcode scanner.

Expected hardcode gate:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

## Golden Reference Alignment

Recommendations reuses the established chain:

```text
Task 24.10 Dashboard
  → page composition / states / responsive rhythm
Task 24.11 Billing
  → analytical density / financial presentation
Task 24.12 Reservations
  → operational recommendation/status patterns
Task 24.13 Inventory
  → resource/provider/table patterns
Task 24.14 Recommendations
  → FinOps decision support / savings / confidence / actions
```

This leaves Reports able to migrate using the same PageHeader, filters, metrics, tables, financial formatting, status, technical context and loading/empty/error architecture rather than creating a new visual system.
