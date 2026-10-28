# Aven Data Visualization System

## Scope

This document defines the visualization contract introduced and consolidated by Task 24.17. It applies to analytical visualizations already supported by product data. It does not authorize creating charts where the product has no chart-backed use case.

Current chart consumers audited for this task:

- Billing / Uso e Custos: stacked cost bars by period and grouping.
- Dashboard / Visão Geral: ranked opportunity bars.
- Flow: savings, reallocation and cumulative-balance SVG visualization.
- Settings / Usage & Costs: estimated-cost time series.

Reservations currently exposes coverage and percentage information through product metrics/progress patterns. It is intentionally not converted into a chart. Inventory and other pages must likewise not receive speculative visualizations.

## Architecture

The Aven visualization layer is intentionally library-agnostic. The frontend currently renders charts with React, CSS and SVG and has no dedicated charting dependency. Task 24.17 preserves that implementation instead of replacing it for aesthetic reasons.

The contract is split into three layers:

1. `frontend/app/styles/tokens/visualization.css` owns chart-specific visual roles.
2. Existing chart renderers own data-to-geometry mapping and domain-specific interaction.
3. `ChartCard`, from `frontend/components/aven/layout.tsx`, is the canonical product container whenever a chart needs standardized loading, error or empty-state handling.

Domain calculations remain outside the visual token layer. Visualization tokens must never encode AWS, OCI, account, service or business-status identity.

## Token contract

### Categorical series

Use the ordered palette below for unrelated categorical series:

- `--chart-series-1`
- `--chart-series-2`
- `--chart-series-3`
- `--chart-series-4`
- `--chart-series-5`
- `--chart-series-6`

The palette is provider-neutral. A series color identifies a position/category within a visualization; it must not mean AWS, OCI, success, warning or failure.

When a chart has more categories than the supported palette, prefer an explicit aggregation strategy such as `Outros` instead of inventing a hardcoded seventh color. Billing follows this rule by compacting long service lists.

### Structural chart roles

Use:

- `--chart-grid` for grid lines.
- `--chart-axis` for axes.
- `--chart-label` for chart labels.
- `--chart-tooltip-bg` and `--chart-tooltip-text` for tooltip surfaces.
- `--chart-reference-line` for neutral reference lines.
- `--chart-baseline` for neutral baselines.

### Data-state roles

Use:

- `--chart-forecast` for forecast-specific visual treatment.
- `--chart-estimated` for estimated-data treatment.
- `--chart-comparison` for comparison series.

These roles describe data semantics inside a visualization. Product status colors such as success, warning or danger must not be reused merely to differentiate categorical series.

## Light and dark themes

Every chart token in `visualization.css` has an explicit Light and Dark mapping. Consumers reference the semantic chart token only; they must not branch on theme or import primitive colors directly.

This guarantees that axes, labels, tooltip contrast and series colors remain controlled by the theme engine established earlier in Phase 24.

## Container and states

`ChartCard` owns standardized chart-surface states through `DataState`:

- loading;
- error;
- empty;
- empty title and description.

A page may retain an existing domain-specific container when migrating it would broaden the task beyond visualization or change behavior. New chart surfaces should default to `ChartCard` unless there is a documented product reason not to.

The visualization renderer itself should focus on plotting valid data. It should not duplicate page-level request state or API orchestration.

## Accessibility

All SVG charts must expose an accessible `role="img"` and a meaningful `aria-label`. Interactive chart regions must remain keyboard reachable when they expose details that are otherwise available only on pointer hover.

Text labels, legends and tooltips must use semantic typography and color tokens. Color must not be the only carrier of critical status information; labels, markers or text should accompany forecast/estimated states where applicable.

Zero-valued data must remain semantically zero. A renderer must not manufacture a positive visual value solely to make a zero bar visible.

## Existing consumers after Task 24.17

### Billing

`frontend/app/billing/billing-cost-chart.tsx`

- Uses the six Aven categorical series tokens.
- Uses `--chart-forecast` for forecast outlines.
- Aggregates excessive service categories into `Outros` rather than extending the palette ad hoc.
- Preserves existing keyboard and tooltip behavior.

### Dashboard

`frontend/components/executive-dashboard.module.css`

- Uses `--chart-series-1` for ranked opportunity bars.
- Does not use product error/status colors as categorical identity.

### Flow

`frontend/app/flow/flow-layout.module.css`

- Axis uses `--chart-axis`.
- Savings, reallocation and cumulative balance use series 1, 2 and 3 respectively.
- The existing SVG remains the renderer; Task 24.17 does not replace it with a new chart library.
- The page keeps `ChartCard` as the analytical container.

### Settings / Usage & Costs

`frontend/app/settings/usage-costs/usage-costs.module.css`

- Migrated from the legacy `--chart-1` alias to `--chart-series-1`.
- Axis and labels now use `--chart-axis` and `--chart-label`.
- Chart metadata and axis typography use Aven typography tokens.
- Chart-specific structural spacing uses Aven spacing tokens.

## Rules for future charts

1. Do not add a chart unless real product data and an existing or approved analytical use case support it.
2. Do not introduce a charting library solely to restyle an existing SVG/CSS visualization.
3. Use Aven chart tokens; never hardcode chart colors.
4. Do not reuse status colors as categorical series colors.
5. Use the existing six-series palette and aggregate overflow categories intentionally.
6. Keep provider identity out of categorical colors.
7. Support Light and Dark through semantic tokens, not component branches.
8. Prefer `ChartCard` for new chart surfaces and let it own request states.
9. Preserve accessible labels, keyboard behavior and non-color status cues.
10. Keep domain calculations and persistence/API concerns outside the visualization layer.

## Regression guard

`frontend/tests/aven-data-visualization.test.mjs` verifies the Light/Dark token contract, provider neutrality, the use of Aven tokens by the audited consumers, removal of the legacy Usage & Costs chart alias, and the stateful `ChartCard` contract.
