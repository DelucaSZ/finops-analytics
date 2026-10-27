# Aven Reservations

Task 24.12 migrates `/rds/reservations` to the Aven Design System without changing the existing reservation engine, AWS/RDS contracts, coverage allocation, expiration rules or opportunity generation.

## Goals

Provide one operational view for active Reserved DB Instances, reservation coverage, reserved-capacity utilization, expirations and reservation opportunities. The page follows the Dashboard Golden Reference and Billing analytical-density rules without introducing a third visual language.

## Functional Architecture

The page remains a client-side composition over the existing `/rds/reservations-dashboard/*` APIs. `useApiQuery`, query keys, cache policies, URL state and backend contracts remain feature-owned. The page never recalculates reservation matching or opportunity eligibility.

Current provider scope is AWS RDS. `ProviderBadge` makes this explicit; no OCI reservation support is implied. An empty account URL parameter retains the existing Reservations contract: all authorized accounts are in scope. This is a page/domain rule, not behavior embedded in `AccountSelector`.

## Page Composition

```text
Aven Application Shell
→ PageHeader
→ FilterBar / scope
→ Reservation KPIs
→ Coverage / Utilization
→ Reservation explorer tabs
   → Coverage
   → Active Reservations
   → Expiring Reservations
   → Reservation Opportunities
```

Tabs are intentionally retained. Only the active operational dataset is fetched, preserving the existing request profile instead of loading every table simultaneously.

## Filters

`FilterBar` composes the official `AccountSelector` and tokenized `Select` primitives for region, engine, family, class and view-specific status filters. Common scope filters affect the summary and selected dataset when supported by the API. View-specific filters affect only their existing endpoint; the UI does not fabricate unsupported summary filtering.

## Reservation KPIs

The overview uses official `MetricCard` components for active reservations, reservation coverage, utilization, reservations expiring within 30 days and uncovered RDS workloads. Reservation count is distinct from reserved units/capacity.

Savings are intentionally absent from the KPI row because the current Reservations contracts do not provide a reliable realized/potential savings value for this page.

## Coverage

Coverage is the backend-calculated portion of eligible RDS workload capacity protected by compatible reserved capacity. The page consumes `coverage_percentage`, required units, covered units, uncovered units and `coverage_status` exactly as returned. It uses `PercentageDisplay` and semantic `StatusIndicator` labels; no page threshold reclassifies coverage.

## Utilization

Utilization is the backend-calculated portion of reserved capacity currently allocated. It is distinct from coverage. `PercentageDisplay` receives the backend value without a page-level clamp or arbitrary `< 60%` warning rule. Any backend anomaly remains observable instead of being silently rewritten.

## Savings

Potential or realized savings are not inferred from reservation price fields. The existing opportunity engine records savings as not calculated for uncovered RDS opportunities, so Task 24.12 does not fabricate currency, monthly savings or annual savings. `CurrencyDisplay` should be introduced only when a trustworthy backend savings contract exists.

## Active Reservations

The Active Reservations tab uses official Table primitives and shows only data present in the API: reservation identifier, engine, class, account, region, quantity/capacity, utilization, expiration and state. `ResourceIdentifier` handles long technical identifiers. Numeric values use the primitive alignment contract.

## Expiring Reservations

The Expiring Reservations tab reuses the reservations endpoint with the existing expiration query contract. It shows the absolute expiration date and backend-provided days remaining together. Expired reservations are rendered as a distinct state from expiring reservations.

## 30-Day Expiration Rule

The existing frontend query helper sends `expiration_range=LE_30` by default for the Expiring tab and orders expiration ascending. The backend remains authoritative for the boundary. Existing backend tests establish 30 days as included and 31 days as excluded; Task 24.12 does not recalculate this threshold in React.

## RDS Reservation Opportunities

The Opportunities tab consumes the existing backend opportunity result. It can display uncovered RDS, partial coverage, unused capacity and expiring-reservation findings without performing matching in the UI. The interface does not expose a Buy Reservation action and does not imply that a reservation was purchased.

## Opportunity Matching

Compatibility remains owned by the existing reservation engine and rules. Engine/technology, family/class, licensing/topology rules, current instances, existing reservations and normalized capacity are evaluated before the UI receives coverage/opportunity data. Existing tests cover engine mismatch, family mismatch, partial coverage, existing reservation allocation and uncovered opportunity generation.

The UI does not duplicate or expand aggregated findings into false opportunities.

## Loading

Summary KPIs use `MetricCard` loading states. Tables use official `Skeleton` rows. Independent summary/options/table queries remain independently visible so a partial failure does not erase valid data.

## Empty

Empty states are specific: no coverage rows, no active reservations, no reservations in the 30-day window, and no opportunities are separate `DataState` outcomes. The page does not collapse them into a generic “no data” message.

## Error

`Alert` and `DataState` convert provider/API failures into user-safe operational messages. Permission denied, coverage not calculated, rate limiting and provider unavailability are not presented as empty data. Raw backend error bodies are not surfaced.

## Light Theme

Light mode inherits the Aven semantic surfaces, borders, text, status and visualization tokens. No Reservations-specific light palette exists.

## Dark Theme

Dark mode uses the same semantic contracts with Theme Engine mappings. Warnings and danger states retain semantic contrast without neon treatment.

## Responsive Behavior

At 1280px and above the five KPI cards stay on one row to preserve the 1366×768 information horizon. Below 1280px the grid reduces columns, and narrow layouts stack. Official `Table` owns internal horizontal scrolling; the page does not create global horizontal overflow or take scroll ownership from the Application Shell.

## Accessibility

The page uses semantic table markup, keyboard-capable official Tabs, labeled controls, textual status labels plus icons, and `ResourceIdentifier` copy/tooltip behavior. Status is never conveyed by color alone.

## Performance

Theme changes do not participate in query keys and therefore do not trigger refetches or reset filters. Tabs preserve lazy operational fetching. The redesign introduces no additional reservation API family and does not execute all table queries at once.

## Legacy Migration

Task 24.12 removes page-local visual implementations of Badge, MetricCard, Skeleton, progress, table state and legacy filter/table styling. The page CSS becomes composition-only and token-driven. The previous arbitrary utilization color threshold is removed because it was not a documented product rule.

## Golden Reference Alignment

Reservations reuses Dashboard page rhythm, PageHeader, Section hierarchy, metric grid and data states, plus Billing FilterBar/table density and analytical presentation. It remains less financially dense than Billing and does not introduce a new chart system before Task 24.18.

## Concepts

- **Coverage** — eligible workload capacity protected by compatible reserved capacity.
- **Utilization** — reserved capacity allocated to eligible workloads.
- **Active Reservation** — reservation reported active by the current backend contract.
- **Expiring Reservation** — active reservation inside the backend expiration window; the default view is within 30 days.
- **Expired Reservation** — reservation whose expiration state/date is already past; not the same as expiring.
- **Reservation Opportunity** — backend-generated finding representing a coverage gap, partial coverage, unused capacity or approaching expiration.
- **Potential Savings** — a future financial estimate only when supplied by a trustworthy backend calculation; not currently fabricated by this page.
