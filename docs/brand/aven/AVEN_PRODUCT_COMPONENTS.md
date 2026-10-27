# Aven Product Components

Task 24.6 establishes the official reusable product-component layer between generic Aven UI Primitives and feature pages.

## Philosophy

Aven Product Components know reusable FinOps concepts such as cost, savings, account, provider, environment, resource, recommendation, status, date range and metric. They do **not** own page-specific business rules, data fetching, routing, query parameters, permissions or API orchestration.

The goal remains **Complexity underneath. Clarity above.** A feature page should primarily compose data, state and business rules instead of redrawing interface patterns.

## Primitive vs Product Component

A primitive expresses generic UI intent:

```tsx
<Button>Export</Button>
<Badge variant="success">Active</Badge>
<Card>...</Card>
```

A Product Component expresses reusable product intent:

```tsx
<MetricCard label="Potential savings" value={...} />
<AccountSelector options={...} />
<StatusIndicator status="success" label="Active" />
```

A Product Component must remain useful across more than one feature. Do not create `DashboardPotentialSavingsCard`, `BillingAccountSelector` or provider-specific recommendation cards when composition can express the same structure.

## Architecture

```text
Aven Brand
↓
Design Tokens
↓
Theme Engine
↓
Visual Foundations
↓
UI Primitives
↓
Product Components
↓
Feature Pages
```

Canonical implementation:

```text
frontend/components/aven/
```

Dependency direction is one-way:

```text
Page → Product Component → UI Primitive → Token
```

`frontend/components/ui/` must never import `frontend/components/aven/`.

## Composition Rules

- Product Components compose `Button`, `Card`, `Badge`, `Input`, `Select`, `Tooltip`, `IconButton`, `Skeleton`, `Alert`, `EmptyState` and other primitives.
- Pages provide data and callbacks.
- Product Components may format presentation values but do not convert currency or infer business meaning.
- Prefer slots/React nodes where domain-specific presentation can be composed without multiplying variants.
- Product APIs express intention (`provider`, `status`, `sentiment`, `currency`) rather than appearance (`orange`, `rounded`, `compactBlue`).

## Hardcoding Rule

Starting with Task 24.5 and continuing here:

> No new visual component may use hardcoded colors, structural spacing, border radius or typography.

Task 24.6 expands `npm run lint:design-system` to:

```text
frontend/components/ui/
frontend/components/aven/
frontend/app/dev/ui/
```

Expected gate:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

Layout composition may use CSS structure such as flex/grid/minmax, but visual decisions use Aven semantic/foundation/component tokens.

## PageHeader

`PageHeader` standardizes page title hierarchy, supporting description, optional breadcrumbs, actions and metadata. Actions wrap rather than overlap at narrow widths. Filters remain outside the header.

```tsx
<PageHeader
  title="Billing"
  description="Usage and cloud costs."
  actions={<Button>Export</Button>}
/>
```

## Section

`Section` standardizes section heading, supporting text and actions. `appearance="plain"` is the default; `appearance="card"` explicitly composes the Card primitive when a distinct surface is meaningful. A section is therefore not automatically a card.

## MetricCard

`MetricCard` supports label, value, optional icon, supporting text, status, trend, loading and an explicit empty fallback.

Nullish values render the configured `emptyValue`; numeric/string zero remains data and is not converted into “no data”. Loading reuses the primitive `Skeleton`.

Trend semantics remain explicit:

```tsx
<MetricCard
  label="Total cost"
  value={<CurrencyDisplay value={124810} currency="USD" />}
  trend={{ value: 6.3, direction: "up", sentiment: "negative" }}
/>
```

Direction never implies sentiment.

## FilterBar

`FilterBar` is a visual/compositional toolbar for primary filters plus actions/clear controls. It wraps variable-width children and owns no global filter store, query params or fetch behavior.

## AccountSelector

`AccountSelector` accepts caller-provided options and controlled selection. It supports single and multi selection, search, disabled/loading/empty states, clear, and explicit Select All for multi-select.

An empty multi value `[]` is always empty. The component never interprets it as “all accounts”. Billing remains responsible for the rule that empty selection triggers no Cost Explorer query.

Account presentation can include account ID, provider and environment metadata without creating an API dependency.

## EnvironmentSelector

`EnvironmentSelector` uses the same controlled generic selector contract for environment scope. It supports single/multi selection, search when requested, loading, disabled, empty and clear.

## ProviderSelector

`ProviderSelector` is implemented because provider scope is already reused by Dashboard/Billing/Inventory/Recommendations readiness. Provider values are strings supplied by the caller; the component does not hard-code a closed AWS/OCI universe.

## DateRangePicker

`DateRangePicker` supports controlled start/end values, caller-configured presets, clear and disabled behavior.

The implementation deliberately composes native `input[type="date"]` through the Aven `Input` primitive. The browser owns calendar overlay positioning/top-layer behavior, preventing the historical failure mode where a page-local absolutely positioned calendar jumped to the page top. No page-specific positioning fix is introduced.

Presets remain configurable:

```tsx
<DateRangePicker
  value={range}
  onChange={setRange}
  presets={[
    { value: "current-month", label: "Current month", range: ... },
    { value: "custom", label: "Custom" },
  ]}
/>
```

Dates use the native ISO `YYYY-MM-DD` control value contract; feature-level display formatting remains separate when rendered as prose/table text.

## ChartCard

`ChartCard` owns title, description, actions, optional legend area and standardized loading/error/empty states through `DataState`. It never defines chart series, geometry or a chart library.

```tsx
<ChartCard title="Cost evolution">
  <CostChart />
</ChartCard>
```

The Aven Data Visualization System remains Task 24.18.

## StatusIndicator

`StatusIndicator` represents operational state with a semantic `Badge` plus icon and text. Supported states are neutral, info, success, warning, danger and pending. Color is never the sole signal.

Feature-specific status mappings can choose/override semantic meaning instead of imposing one universal business mapping.

## ProviderBadge

`ProviderBadge` presents provider identity consistently while remaining extensible. `provider` is a string rather than a duplicate closed frontend domain union because no canonical reusable provider type currently exists in the frontend.

Known labels normalize AWS/OCI capitalization. Unknown providers fall back to their supplied value. No logic treats “not AWS” as OCI, and no raw provider brand color is introduced. Official provider logos can be passed later as assets through `icon` without rebuilding/recoloring them as Aven glyphs.

## ResourceIdentifier

`ResourceIdentifier` presents a primary resource name plus optional technical ID. Technical identifiers use the Aven code/resource typography role, truncate visually, retain a tooltip with the full value, and optionally provide a labeled copy action through `IconButton`/Tooltip.

## CurrencyDisplay

`CurrencyDisplay` formats currency with `Intl.NumberFormat` and requires `currency` explicitly.

Supported today includes any Intl-supported currency, including the required USD and BRL scenarios. It supports full/compact notation, fraction controls, negative values, zero and null.

It never infers currency from provider and never converts values. Therefore AWS USD and OCI BRL pricing remain correct when their domain metadata is passed correctly.

## PercentageDisplay

`PercentageDisplay` has an explicit input contract:

- `valueMode="percent"` (default): `42` renders as `42%`;
- `valueMode="fraction"`: `0.42` renders as `42%`.

It supports zero, 100, negative values, decimals, null and Intl fraction/sign formatting.

## TrendIndicator

`TrendIndicator` accepts independent:

- `direction`: `up | down | flat`;
- `sentiment`: `positive | negative | neutral`.

The arrow communicates direction, semantic badge treatment communicates sentiment, and the accessible name includes both. `up + negative`, `down + positive` and every other valid combination are supported.

## RecommendationCard

`RecommendationCard` establishes one reusable opportunity hierarchy: title/opportunity, potential savings, impact, confidence, resource/provider, status/metadata and explicit actions.

It accepts already composed values such as `CurrencyDisplay`, `PercentageDisplay` and `ResourceIdentifier`. It performs no recommendation execution, API request or routing and does not create EC2/RDS/OCI variants.

## DataState

`DataState` is a light presentation abstraction for loading, error and empty content. It composes `Skeleton`, `Alert` and `EmptyState` and accepts fallbacks/empty content.

It does not fetch, retry, infer whether a dataset is empty or own request lifecycle state.

## CostSummary / SavingsSummary / PeriodSelector

These are intentionally **not** introduced in Task 24.6. Current requirements are already expressed by `MetricCard + CurrencyDisplay + TrendIndicator` and `DateRangePicker`. Adding wrappers now would create pass-through components without a stable reusable UX semantic. They can be added later only if page migrations expose a repeated composition with real behavior/hierarchy value.

## Theme Support

Product Components consume semantic/foundation tokens and Aven primitives. Normal component code never branches on Light/Dark. Therefore Light, Dark and System follow the existing Theme Engine automatically.

Provider marks or future chart libraries may consume resolved theme only when the external asset/library actually requires it; ordinary product surfaces do not.

## Accessibility

- Native controls and primitive semantics are preserved.
- Selectors retain native select keyboard semantics and labels.
- Search fields have accessible names.
- Date range inputs are labeled native date inputs.
- Status/trend include icon/text and do not depend on color alone.
- Copy actions have labels and tooltip feedback.
- Long technical IDs are keyboard-focusable for full-value tooltip access.
- Product cards are not clickable `<div>` containers; actions remain explicit controls.
- Primitive focus-visible treatment is preserved rather than suppressed.

## Responsive Behavior

Product components do not set page widths. Cards are grid-ready and shrink within their parent. PageHeader/Section/Chart headers wrap actions. FilterBar wraps children. Selectors keep usable minimums while allowing the parent to control placement. Recommendation metrics collapse to one column at narrow widths; essential opportunity data remains ordered before metadata/actions.

Required page migrations should still smoke-test 1280, 1366, 1440, 1600, 1920 and 2560 plus narrower notebook/tablet layouts. Task 24.6 establishes responsive component behavior but does not choose page grid breakpoints for future features.

## Legacy Migration

| Legacy pattern | Aven Product Component | Migration task |
|---|---|---|
| Shared legacy `PageHeader` | `PageHeader` | 24.7+ / owning page |
| Dashboard KPI card | `MetricCard` | 24.10 |
| Dashboard filter/scope rows | `FilterBar` + selectors | 24.10 |
| Billing account selector | `AccountSelector` | 24.11 |
| Billing period/date controls | `DateRangePicker` | 24.11 |
| Billing KPI/cost surfaces | `MetricCard` + `CurrencyDisplay` | 24.11 |
| Billing chart panel | `ChartCard` | 24.11 |
| Reservations status pill | `StatusIndicator` | 24.12 |
| Reservations coverage metrics | `MetricCard` + `PercentageDisplay` | 24.12 |
| Inventory provider/status/resource cells | `ProviderBadge` + `StatusIndicator` + `ResourceIdentifier` | 24.13 |
| Opportunity/recommendation cards | `RecommendationCard` | 24.14 |
| Repeated loading/error/empty blocks | `DataState` | owning page migration |

Legacy CSS/components remain until their route owners migrate. Task 24.6 does not mass-remove them.

## Usage Examples

```tsx
<PageHeader
  title="Billing"
  description="Usage and cloud costs."
/>

<FilterBar>
  <AccountSelector
    label="Accounts"
    options={accounts}
    multiple
    value={selectedAccountIds}
    onChange={setSelectedAccountIds}
    selectAll
  />
  <DateRangePicker value={range} onChange={setRange} />
</FilterBar>

<div className={styles.metricsGrid}>
  <MetricCard
    label="Total cost"
    value={<CurrencyDisplay value={124810} currency="USD" />}
  />
  <MetricCard
    label="Potential savings"
    value={<CurrencyDisplay value={21400} currency="USD" />}
    trend={{ value: 8.2, direction: "up", sentiment: "positive" }}
  />
</div>

<ChartCard title="Cost evolution">
  <CostChart />
</ChartCard>
```

The page still owns `accounts`, selected IDs, range, Cost Explorer query behavior, chart data, business rules and grid composition.

## Forbidden Patterns

Do not:

- add raw colors/spacing/radius/type literals to `components/aven`;
- import Product Components from `components/ui`;
- fetch APIs inside selectors/presentation components without a separately defined container pattern;
- infer empty account selection as “all”;
- infer currency from cloud provider;
- infer trend sentiment from direction;
- encode provider identity using ad-hoc raw colors;
- add page-specific components/variants where composition works;
- make a whole card clickable with a non-semantic `div`;
- put chart-series styling inside `ChartCard`;
- add page-specific design tokens to disguise hardcodes.

## Technical Preview

`/dev/ui` now includes a Product Components section using the real Theme Engine and preview-only mock data. It covers normal, long-content, disabled, loading, empty, error, positive/negative/neutral trend, multi-account empty selection, provider fallback, currency/percentage contracts and ChartCard states.

## Task 24.7 Readiness

**Is Task 24.7 ready to start? YES.**

| Capability | Ready? |
|---|---|
| Page structure | YES |
| Navigation controls | YES |
| Buttons | YES |
| Menus | YES |
| Tooltips | YES |
| Selectors | YES |
| Status | YES |
| Theme integration | YES |
| Responsive foundations | YES |
| Accessibility foundations | YES |

The shell can be built with Aven primitives + Product Components; shell-specific navigation/sidebar/topbar composition remains Task 24.7.

## Future Page Readiness

| Task | Readiness | Existing Product Component support |
|---|---|---|
| 24.10 Dashboard | YES | PageHeader, Section, MetricCard, FilterBar, selectors, ChartCard, DataState |
| 24.11 Billing | YES | AccountSelector, ProviderSelector, DateRangePicker, MetricCard, CurrencyDisplay, ChartCard, DataState |
| 24.12 Reservations | YES | MetricCard, PercentageDisplay, StatusIndicator, ProviderBadge, ResourceIdentifier, FilterBar |
| 24.13 Inventory | YES | FilterBar, selectors, ProviderBadge, StatusIndicator, ResourceIdentifier, DataState |
| 24.14 Recommendations | YES | RecommendationCard, CurrencyDisplay, PercentageDisplay, ProviderBadge, ResourceIdentifier, StatusIndicator |

These readiness statements cover product-component composition only. They do not implement or visually migrate the pages themselves.
