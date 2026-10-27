# Aven Billing

## Goals

Task 24.11 migrates `/billing` to the Aven Design System and establishes Billing as the **High-density analytical reference** for financial and operational pages.

The page follows:

```text
PageHeader
↓
Account Context
↓
FilterBar / Period
↓
Financial Summary
↓
Cost Evolution
↓
Service / Account Breakdown
```

The implementation reuses the existing Billing data pipeline. The redesign changes presentation, composition and accessibility without rewriting AWS Cost Explorer integration, request contracts, aggregation rules, cache behavior or financial semantics.

## Functional Contracts

The feature keeps the existing `/billing/aws/*` contracts and Billing Profile behavior.

Critical invariants:

```text
[] accounts != all accounts
```

```text
No accounts selected
→
No Cost Explorer query
```

```text
Estimated styling
→
only for actual estimated/forecast points
```

The route still accepts explicit account IDs from the URL. A missing or empty `accounts` parameter restores `[]`; an explicit valid account list restores only those accounts.

Theme preference is not part of the Billing query signature. Light/Dark/System changes presentation only and do not trigger cost requests.

## Account Selection

Billing uses the official `AccountSelector`.

The selector:

- is controlled by the page;
- starts empty unless the URL explicitly contains valid account IDs;
- supports search;
- exposes an explicit `Selecionar todas` action;
- exposes `Limpar seleção`;
- shows account name, AWS account ID and provider metadata;
- never converts an empty selection into all accounts.

`Selecionar todas` selects all eligible AWS accounts currently available to the authenticated user. Clearing returns the value to `[]`.

## No-Selection Behavior

The no-selection state is intentional and is not loading.

When `selectedAccountIds` is empty:

- Summary state is cleared.
- Previous-period summary state is cleared.
- Time-series state is cleared.
- Service breakdown state is cleared.
- Account breakdown state is cleared.
- The request effect returns before calling any Cost Explorer endpoint.
- Billing renders an orientative `DataState` instead of zero-value metrics or empty charts.

This is a performance and cost-control contract, not a visual preference.

## Filter Architecture

Account selection appears before Billing filters.

The official `FilterBar` contains the real existing controls:

- Billing Profile;
- period;
- metric;
- granularity;
- grouping.

Temporary profile overrides remain visible and can be reset to the selected profile.

Record-type exclusions remain under the advanced-filter disclosure and use Aven `Checkbox` primitives.

No new export, scheduling, sharing or saved-view actions were introduced.

## Period Selection

Billing uses the official `DateRangePicker`.

Preset behavior remains based on `BILLING_PERIOD_PRESETS` and the existing `resolveBillingPeriod()` helper. Custom ranges continue to use local date boundaries and the existing end-exclusive API contract.

The Product Component uses native `input[type="date"]`, so the browser owns the calendar overlay. This avoids page-local absolute positioning, viewport offsets and z-index fixes.

Billing supplies the current local date as `maxDate`; future custom dates are therefore blocked at the control layer and still validated by the existing period resolver.

## Financial Summary

Financial Summary uses `MetricCard`, `CurrencyDisplay`, `TrendIndicator` through the MetricCard trend contract, and `StatusIndicator`.

Only metrics supported by the existing response are shown. Task 24.11 does not fabricate average daily cost, savings scores or optimization metrics.

Each backend currency remains a separate metric. Previous-period comparison uses the matching currency only.

Zero is preserved as data. Missing data remains an empty value/state.

## Cost Evolution

The primary visualization remains the existing custom Billing chart, now hosted by the official `ChartCard`.

No chart dependency was added.

The chart is responsive to its container and no longer forces a fixed minimum rendered width or a normal-desktop horizontal scroller.

When grouping is `SERVICE`, each period remains a stacked bar composed by service. The chart still supports the existing `NONE` and `ACCOUNT` grouping contracts.

The same series key is mapped deterministically to the same Aven visualization token where possible.

The chart consumes:

```text
--chart-series-1 … --chart-series-6
--chart-grid
--chart-label
--chart-baseline
--chart-forecast
--chart-tooltip-bg
--chart-tooltip-text
```

Legacy application palette aliases are not used by the migrated chart.

## Service Breakdown

The precise breakdown remains available below the chart and uses official semantic `Table` primitives.

Service breakdown is grouped by returned currency and sorted by the existing `topBillingItems()` behavior.

When more than one account is selected, the existing account breakdown remains visible as a second analytical section.

Table wrappers own narrow-width overflow; the page itself does not acquire horizontal scrolling.

## Forecast / Estimated Semantics

Billing consumes explicit backend status values:

```text
ACTUAL
ESTIMATED
PARTIALLY_ESTIMATED
FORECAST
INCLUDES_FORECAST
```

The frontend does not infer forecast from date position or from “last point” heuristics.

Per-period and per-series status is preserved by `mapBillingTimeSeriesToChartData()`.

Visual behavior:

- `ACTUAL` remains fully rendered.
- `ESTIMATED` is marked only on the affected bucket/series.
- `PARTIALLY_ESTIMATED` remains explicitly partial.
- `FORECAST` uses the forecast visualization token and a trace pattern.
- `INCLUDES_FORECAST` states that forecast is included; it does not claim the entire range is forecast.

A fully actual dataset has no estimated/forecast note.

## Currency Semantics

Financial values use `CurrencyDisplay` with the currency returned by Billing.

No FX conversion is introduced.

The current `/billing` data endpoints remain AWS Cost Explorer endpoints. Task 24.11 does not fabricate an OCI Cost Explorer path or combine AWS USD with OCI BRL. Existing OCI pricing and other provider contracts remain untouched.

Aven Product Components remain provider/currency-neutral and can render BRL/USD when the owning feature supplies the correct metadata.

## Loading

No-account state is never loading.

After explicit selection:

- summary metrics use MetricCard skeleton geometry;
- ChartCard uses DataState loading;
- breakdown sections use DataState loading;
- independent requests can resolve independently.

The page does not add a full-screen spinner.

## Empty

Billing distinguishes:

1. no account selected;
2. selected account(s) with no cost in the period;
3. a local breakdown with no rows.

These states use Aven `DataState` or `EmptyState` and are not represented as artificial zero financial values.

## Error

Bootstrap and request errors use Aven `Alert`/`DataState`.

Existing Cost Explorer error classification remains preserved, including permission, unavailable service, invalid scope, throttling, invalid period and upstream-data errors.

No raw backend stack trace is shown.

## Light Theme

Billing consumes Aven semantic surfaces, text, borders and visualization tokens.

The Light experience remains clean and financially dense, with controlled chart color and restrained surface hierarchy.

There is no Light-specific data-fetching branch.

## Dark Theme

Dark uses the same DOM and data state.

Semantic tokens change canvas, surfaces, borders, text, chart structure and series colors. The chart avoids legacy neon/brand aliases.

There is no Dark-specific query path.

## Responsive Behavior

Billing is a wide analytical page inside the Application Shell.

Composition rules:

- metrics: three-column analytical grid, reducing to two and then one;
- record-type filters: progressive wrapping;
- chart context: four columns plus status, reducing to two and then one;
- service/account breakdown: two columns when useful, then stacked;
- tables keep their own narrow-width overflow;
- the chart fills its container without a forced desktop horizontal scroller.

The reference viewport remains 1366×768, with validation also expected at 1280, 1440, 1600, 1920 and 2560 plus narrow layouts.

## Accessibility

The migration preserves/adds:

- one page-level `h1` through `PageHeader`;
- native labels for Select, AccountSelector and date controls;
- keyboard-native multi-select behavior;
- focus-visible Aven treatment;
- semantic Table markup;
- status text/icons in addition to color;
- keyboard-focusable chart period targets;
- tooltip access from focus as well as pointer;
- chart `aria-label` describing currency, granularity and grouping;
- explicit empty/error states.

Critical financial meaning is not encoded only by color.

## Performance

The existing request effect, `AbortController`, sequence guard and `billingQuerySignature()` remain the orchestration model.

Task 24.11 does not add Billing endpoints or duplicate current requests.

The request count contract is:

```text
Cost query count with zero selected accounts: 0
```

Theme changes do not enter query keys/signatures and therefore do not refetch Cost Explorer data.

## Legacy Migration

Migrated:

- legacy shared PageHeader → Aven `PageHeader`;
- raw Billing account checkbox grid → `AccountSelector`;
- page-local date controls → `DateRangePicker`;
- raw select styling → Aven `Select`;
- custom KPI cards → `MetricCard`;
- manual money presentation in migrated surfaces → `CurrencyDisplay`;
- panel-based chart shell → `ChartCard`;
- raw breakdown table markup → Aven Table primitives;
- local loading/error/empty blocks → `DataState`, `Alert`, `EmptyState`;
- legacy chart palette aliases → Aven visualization tokens.

`billing.module.css` now owns page/chart composition only and is included in the design-system hardcode gate.

## Golden Reference Alignment

Billing follows `AVEN_DASHBOARD.md` for:

- PageHeader placement;
- vertical rhythm;
- Section hierarchy;
- FilterBar composition;
- metric-grid behavior;
- ChartCard state handling;
- loading/empty/error treatment;
- responsive stacking;
- semantic Light/Dark behavior.

Billing deliberately differs where its domain requires higher density, account-first query gating, temporal controls, stacked cost analysis and precision tables.

## Validation Gates

Required commands:

```bash
cd frontend
npm run lint:brand
npm run lint:design-system
npm run lint
npm run typecheck
npm test
npm run build
```

Expected Billing hardcode result:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

Functional Regression Gate:

```text
No account selected triggers cost query?
NO

Empty account list interpreted as all?
NO

Select All explicit?
YES

Custom date picker anchored correctly?
YES

Billing page scroll works?
YES

Stacked cost-by-service chart preserved?
YES

Actual vs forecast correctly differentiated?
YES
```

## High-density analytical reference

Task 24.11 establishes Billing as the **High-density analytical reference** for later Aven pages that combine:

- wide analytical layouts;
- dense FilterBar composition;
- financial metrics;
- chart + table analysis;
- responsive tables;
- explicit query gating;
- partial loading and precise empty/error semantics.

Reservations, Inventory and Reports can reuse these composition decisions without creating a parallel visual system.
