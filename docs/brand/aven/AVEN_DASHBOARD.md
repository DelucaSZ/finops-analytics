# Aven Dashboard

## Role as Golden Reference

Task 24.10 establishes the authenticated Dashboard / Visão Geral as the **Aven Page Composition Golden Reference**.

Future operational pages must reuse its composition decisions for page header placement, page rhythm, filter surfaces, metric grids, analytical card hierarchy, loading/empty/error treatment, responsive stacking and Light/Dark balance. The reference is architectural and visual; page-specific Dashboard content must not be copied into unrelated features.

The dependency direction remains:

```text
Page composition
↓
Aven Product Components
↓
Aven UI Primitives
↓
Semantic Tokens / Visual Foundations
↓
Theme Engine
```

No new Dashboard visual code may introduce hardcoded colors, structural spacing, border radius or typography.

## Information Hierarchy

The Dashboard follows this operational hierarchy:

```text
PageHeader
↓
Scope / filters
↓
Primary KPIs
↓
Primary analytical visualization
↓
Supporting operational information
```

The current data contract allows the page to answer, without manufacturing metrics:

- how many current opportunities are open;
- how much estimated monthly savings is available, preserving currency boundaries;
- how many opportunities are new compared with the previous comparable collection;
- how many valid scopes contribute to the current summary;
- where the current opportunity backlog is concentrated;
- whether collection failures require attention.

The Dashboard intentionally does not claim to show total cloud spend or reservation coverage because those metrics are not part of the current `/dashboard/summary` contract.

## Page Composition

`frontend/app/page.tsx` remains the `/` route and keeps the existing `Suspense` boundary. `frontend/components/executive-dashboard.tsx` owns orchestration and page composition while visual contracts are delegated to official Aven components.

Composition:

```text
PageHeader
FilterBar
Operational attention, when real failures exist
DataState
  Section: primary metrics
  Comparison context
  Section: backlog analysis
    ChartCard: service concentration
    Section card: lifecycle state
  Section: provider distribution
  Section: top opportunities
```

The page does not introduce a decorative hero, a second application shell or page-specific copies of primitives.

## Page Header

The Dashboard uses the official `PageHeader` product component with:

- title and concise operational description;
- real scope metadata;
- real data freshness timestamp when provided by the backend;
- a refresh action that already existed functionally and refetches the existing summary/options queries.

The header does not duplicate global Application Shell branding or global theme controls.

## Filters

The Dashboard preserves the existing provider/account scope contract and URL query state.

The official `FilterBar`, `ProviderSelector` and `AccountSelector` replace legacy native-select presentation. The selectors continue to use `/collections/options`, maintain the existing account/provider coupling and preserve deep-link behavior through `dashboard-query.mjs`.

The page does not add a `DateRangePicker`: the current Dashboard summary endpoint accepts provider and account scope only. Introducing a date selector without a corresponding backend contract would create a misleading visual-only filter. `DateRangePicker` remains an established Aven Product Component and is ready for pages whose data contracts are temporal, including Billing.

## Metric Grid

Primary metrics use the official `MetricCard`:

1. Oportunidades em aberto;
2. Economia potencial mensal;
3. Novas vs coleta anterior;
4. Escopos válidos.

These metrics are backed by the current Dashboard response. They deliberately replace the previous five-card lifecycle-heavy row with a clearer four-card executive hierarchy while preserving treated/rejected values in the supporting lifecycle section.

`CurrencyDisplay` renders financial totals using each backend-provided currency. Multiple currencies are rendered as separate values; the Dashboard never reduces USD and BRL into one number without an explicit exchange-rate business rule.

The grid is page-owned composition: four columns when space permits, two columns at intermediate widths and one column at narrow widths. `MetricCard` itself remains width-agnostic.

## Cost Evolution

The current `/dashboard/summary` API does **not** expose a historical cost time series, daily/weekly/monthly cost points or an actual/forecast series. Task 24.10 therefore does not fabricate, interpolate or add an extra API call to produce “Evolução de custos”.

Instead, the primary `ChartCard` visualizes a real analytical dimension already present in the response: open opportunities by service (`by_service`). The visualization also exposes the service name, open count and currency-separated savings in visible content, so critical information is not available only through hover or color.

A true cost-evolution visualization requires a real cost-history contract. Billing remains the appropriate detailed cost analysis surface, and Task 24.18 remains responsible for the complete Aven Data Visualization System.

## Supporting Sections

Supporting information is intentionally concise:

- lifecycle state: open, treated and rejected opportunities with semantic deep links;
- provider distribution: backlog and currency-separated savings by real provider identity;
- top opportunities: up to four high-impact opportunities using `RecommendationCard`;
- collection failures: rendered only when the existing operational-insights endpoint reports actual failures.

The page does not reproduce the full Opportunities, Billing, Reservations or Inventory experiences.

## Loading

Initial and partial loading use existing Aven component states:

- `MetricCard` loading states preserve KPI geometry;
- `ChartCard` delegates to `DataState` and official Skeleton treatment;
- lifecycle/supporting content uses `DataState` or loading-capable product components;
- `DashboardBoot` mirrors header → filters → metrics → chart geometry rather than showing a full-page spinner.

This keeps the page stable while independent queries resolve.

## Empty

`DataState` handles the no-current-data state when the backend reports `scope.has_current_data = false`.

Sections with valid summary data but no local rows use explicit empty/healthy states instead of broken charts or invented zeros. A zero count remains a valid value; absence of data remains an empty state or `—` as appropriate.

## Error

Summary failure uses a standard danger `Alert` with an in-place retry action. Filter-option failure is isolated as a warning so already available summary data can remain visible.

Operational-insight endpoint failures remain intentionally isolated and do not turn into a false warning card or take down the executive Dashboard. This preserves the previous partial-failure behavior.

## Light Theme

The Dashboard has no theme-specific page logic. Official components and page CSS consume semantic tokens such as text, surface, border, focus and chart roles.

Light mode therefore inherits the Aven clean, airy, low-contrast surface hierarchy from the Theme Engine and semantic token layer.

## Dark Theme

Dark mode uses the same DOM and data state. Semantic tokens and visualization roles resolve to the dark palette without changing API queries or remounting data ownership.

The page adds no neon borders, bright purple card surfaces or glow effects.

## Responsive Rules

The Dashboard is the reusable page-composition reference for wide analytical screens.

Rules:

- page content uses the Application Shell width contract rather than a narrow marketing container;
- KPI grid: 4 → 2 → 1 columns;
- analytical grid: primary chart + supporting card → stacked layout;
- provider and opportunity grids reduce progressively;
- filters use the official wrapping behavior from `FilterBar`;
- no core section uses absolute positioning;
- charts size from their container and do not introduce page-level horizontal scrolling.

The CSS thresholds are composition breakpoints, not visual spacing literals. The intended smoke-test matrix is 1280, 1366, 1440, 1600, 1920 and 2560 px plus narrower/mobile widths, with 1366×768 treated as a first-class corporate-notebook viewport.

## Accessibility

The migration preserves or adds:

- one page-level `h1` through `PageHeader`;
- section headings through `Section`/`ChartCard`;
- native selector/button/link semantics;
- tokenized `focus-visible` treatment for page-local links;
- semantic status labels through `StatusIndicator`;
- provider identity through `ProviderBadge`;
- visible chart labels/counts in addition to the bar geometry;
- explicit chart accessible label;
- no information that exists only on hover;
- status/error presentation that does not depend on color alone.

## Performance

Task 24.10 keeps the existing server-state architecture and query keys.

It preserves:

- `/dashboard/summary` as the executive summary request;
- `/collections/options` as the selector metadata request;
- `/dashboard/operational-insights` as the isolated operational request;
- existing cache policies and query-key ownership;
- the 45-second operational-insight refresh interval;
- URL state and deep-link behavior.

No duplicate data query or new chart library is introduced. Theme switching is presentation-only and does not alter query keys.

## Legacy Migration

| Legacy area | Disposition | Aven result |
| --- | --- | --- |
| Dashboard route and Suspense boundary | REUSED | Existing `/` route preserved |
| Dashboard API/query orchestration | REUSED | Existing endpoints, query keys, cache policies and URL scope preserved |
| Legacy shared `PageHeader` usage | REPLACED | Official Aven `PageHeader` |
| Native Dashboard scope selects | REPLACED | `FilterBar`, `ProviderSelector`, `AccountSelector` |
| Legacy KPI cards | REPLACED | `MetricCard` |
| Legacy panel/chart containers | REPLACED | `Section` and `ChartCard` |
| Manual money formatting in primary composition | REFACTORED | `CurrencyDisplay` with backend currency metadata |
| Severity/provider/account/service widget stack | REFACTORED | Executive service chart, provider metrics and top opportunities |
| Collection-failure visual layer | REFACTORED | Aven `Section`, `Alert`, `ProviderBadge`, `StatusIndicator` |
| `dashboard-executive.css` | REMOVED | Tokenized CSS Module composition |
| `dashboard-operational-insights.css` | REMOVED | Tokenized CSS Module composition |
| Legacy global Dashboard visual selectors | DEPRECATED | New Dashboard does not depend on them for migrated elements |

Global cleanup outside the migrated Dashboard surface is intentionally deferred; unrelated legacy selectors are not removed by this task.

## Reuse Rules for Future Pages

Future Aven pages should copy these **composition rules**, not Dashboard domain content:

- use official `PageHeader` before local page context;
- place page filters in `FilterBar` and keep selector state coupled to real query behavior;
- use `Section` to create vertical rhythm instead of wrapping every section in a card;
- let the page own responsive metric-grid columns while `MetricCard` remains reusable;
- use `ChartCard` as the standard analytical visualization container and state boundary;
- preserve content geometry with component-level loading rather than a full-page spinner;
- use `DataState`/`Alert`/`EmptyState` contracts for empty and error treatment;
- keep currency/provider semantics separate from Aven brand accent semantics;
- keep Light/Dark behavior token-driven and data-fetching independent;
- prefer natural grid/flex flow and progressive stacking over absolute positioning;
- maintain the same page-level breathing room and restrained surface hierarchy.

## Validation

Task 24.10 adds `frontend/tests/aven-dashboard.test.mjs` and expands the Design System hardcode scanner to cover all new/refactored Dashboard files.

Required hardcode result:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

Repository CI remains the source of truth for:

```bash
cd frontend
npm run lint:brand
npm run lint:design-system
npm run lint
npm run typecheck
npm test
npm run build
```

## Golden Reference Gate

```text
Can this Dashboard be used as the visual composition reference for the remaining Aven pages? YES
```

## Task 24.11 Readiness

```text
Is Task 24.11 ready to start? YES

Aven page composition reference ready: YES
PageHeader ready: YES
FilterBar ready: YES
AccountSelector ready: YES
DateRangePicker ready: YES
MetricCard ready: YES
ChartCard ready: YES
CurrencyDisplay ready: YES
Loading/Empty/Error patterns ready: YES
Light/Dark patterns ready: YES
Responsive page rules ready: YES
Billing can migrate without new visual architecture: YES
```

`DateRangePicker` is ready as an existing Product Component even though the Dashboard intentionally does not render it because its current backend contract has no date-range dimension.
