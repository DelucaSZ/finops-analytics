# Aven Responsive & UI Consistency

## Goals

Task 24.18 is a cross-page responsive and consistency pass over the Aven experiences that already exist. It does not create product capability. The target contract is one Application Shell, one page-composition language, one spacing system, one responsive strategy, one table/overflow strategy, one overlay strategy and one Light/Dark/System visual foundation.

The implementation prioritizes shared causes over page-local patches. Shell, UI primitives and Product Components own behavior that is common across consumers; feature CSS owns only layout that is genuinely feature-specific.

## Scope

Audited existing Aven surfaces:

- Dashboard / `/`;
- Billing / `/billing`;
- Reservations / `/rds/reservations`;
- Inventory / `/inventory`;
- Recommendations / `/opportunities` and its existing detail/action surfaces;
- Settings / `/settings/*`;
- Flow / `/flow`;
- Collections / `/collections`, `/collections/[collectionId]`, `/collections/[collectionId]/compare`;
- Scans / `/scans`;
- shared Application Shell, Sidebar and Topbar;
- shared UI primitives/Product Components used by those routes;
- chart consumers established by Task 24.17.

Every listed route already existed, had real data/action contracts where applicable, and was already inside the Aven migration scope before Task 24.18. No missing product foundation was completed here.

## Non-goals

Task 24.18 does not add routes, APIs, persistence, KPIs, analytics, financial calculations, reservation matching, inventory discovery, recommendation logic, Flow semantics, authentication behavior, production mocks, environment variables or feature flags.

Functional behavior is preserved. Visual problems that require a new product/backend/domain capability are documented rather than implemented.

## Supported Viewports

Required review targets:

- 1280×720;
- 1366×768;
- 1440×900;
- 1600×900;
- 1920×1080;
- 2560×1440;
- representative narrow widths: 1024, 768, 480 and 375;
- constrained-height reference: 1366×650.

The page-composition scale used by migrated analytical/operational content is `78rem`, `62rem` and `48rem`. These are shared composition thresholds rather than screenshot-specific fixes. The Application Shell keeps its established `850px` and `620px` navigation thresholds because they are an existing shell contract from Task 24.7, not new page-specific breakpoints.

Pixel-accurate interactive browser validation is separate from source/CI contract validation. The connected implementation environment for this task exposes GitHub and CI but not an interactive browser viewport. Therefore the source matrix below records structural readiness; a viewport is not marked visually PASS unless it has actually been rendered and inspected.

## 1366×768 Baseline

1366×768 is the primary corporate-notebook baseline.

The Task 24.18 composition reduces avoidable vertical whitespace while retaining Aven density and hit-target rules:

- the shared content frame uses `--space-6` top spacing and `--space-10` bottom spacing;
- primary page rhythm uses `--space-6`;
- PageHeader actions wrap instead of forcing width;
- FilterBar keeps controls on one row while space exists and stacks at the shared narrow threshold;
- metric grids reduce columns at shared composition thresholds;
- tables keep horizontal overflow inside their own wrappers;
- long technical identifiers truncate/wrap through existing resource/table contracts rather than widening the page.

No special `1366px` media query is introduced.

## Application Shell

The persistent shell remains the owner of global composition:

```text
ApplicationShell
├── Sidebar
├── Topbar
└── mainContent
    └── contentFrame
        └── page
```

The shell grid and workspace use `minmax(0, 1fr)` / `min-inline-size: 0` so flex/grid descendants can shrink without creating global horizontal overflow. Direct children of `contentFrame` are also constrained with `min-inline-size: 0`.

Sidebar navigation retains its own vertical scroll only when the navigation area is height-constrained. The footer remains outside that scrolling region so essential controls are not pushed away by long navigation.

## Page Gutters

Authenticated pages consume the Application Shell gutter tokens. Feature pages do not introduce independent outer horizontal containers merely to change spacing.

Desktop uses `--shell-page-gutter`; compact shell mode uses `--shell-page-gutter-compact`. Feature modules may control internal analytical widths where the domain requires them, but they do not replace the shell gutter contract.

## PageHeader

The official Product Component is the page-header contract. It now explicitly supports shrinkable copy/actions, bounded action width and narrow stacking.

Operational PageHeaders must expose the page title and context without consuming a disproportionate share of 1366×768. Page title, description, metadata and actions remain distinct roles; the Topbar is not used as a substitute for PageHeader.

## Section Rhythm

The default outer page rhythm is `--space-6` across Dashboard, Billing, Reservations, Inventory, Recommendations, Settings, Flow and Scans. Collections keeps its scoped compatibility composition but participates in the same shell/gutter/overflow strategy.

Internal component spacing continues to use the Aven scale. Larger gaps may remain inside intentionally separated analytical regions; arbitrary per-page values are not introduced.

## Card Density

Card geometry remains owned by Aven primitives/Product Components. Task 24.18 does not create nested visual cards to compensate for layout problems.

`MetricCard` now fills its grid row consistently so equal grid rows do not produce accidental height drift. Existing card padding, radius, border and elevation remain token-backed.

## Metrics

Metric grids use shared composition thresholds instead of historical page-specific pixel cuts. Wide layouts retain useful parallel comparison; medium layouts reduce columns; narrow layouts become single-column where needed.

Numeric semantics are unchanged. Currency, percentage and trend presentation continue to use existing product display components.

## Filters

`FilterBar` is responsible for shared wrapping/stacking behavior. Controls may grow while space exists, are bounded by the available inline size and become full-width only at the shared narrow threshold.

Account, environment, provider and date-range controls retain their existing functional contracts. Task 24.18 does not reinterpret empty selections or query defaults.

## Forms

Settings retains route-owned persistence and validation. Shared/scoped form grids use two columns only while the composition can support them and collapse to one column at the shared `62rem` threshold.

Long technical values remain shrinkable/wrappable. Task 24.18 does not make all fields arbitrarily full-width on ultrawide displays; existing feature-level controlled surfaces remain authoritative.

## Tables

The Aven table primitive keeps horizontal overflow inside the table wrapper. Feature tables that retain scoped compatibility wrappers, including Collections and Settings, use the same containment model.

The page/Application Shell must not gain horizontal scroll because a technical table is wider than the viewport. Numeric columns continue to use tabular numerals and end alignment through the Table primitive. Technical identifiers continue to use existing truncation/wrapping/copy affordances.

No new sticky-header behavior is introduced.

## Charts

Task 24.18 preserves the Task 24.17 visualization contract and does not create charts or calculations.

Audited consumers remain:

- Billing stacked cost visualization;
- Dashboard ranked opportunity bars;
- Flow savings/reallocation/balance visualization;
- Settings Usage & Costs time series.

Chart containers remain shrinkable. Legends retain wrapping/contained scrolling where needed. Flow keeps its explicit internal horizontal chart viewport rather than widening the page. Billing retains its responsive SVG/container geometry and tooltip alignment contract.

The Task 24.17 specification is now also available at the canonical path `docs/brand/aven/AVEN_DATA_VISUALIZATION_SYSTEM.md`.

## Overlays

Dropdown and Tooltip positioning is centralized in `frontend/components/ui/viewport-position.ts`.

Shared behavior:

- measure trigger and overlay geometry after render;
- use the Aven `--space-2` viewport inset;
- clamp inline position to the viewport;
- Dropdown chooses top/bottom based on available space;
- Dropdown bounds its block size and scrolls internally when necessary;
- Tooltip chooses above/below and clamps to viewport edges;
- recalculate on window resize and scroll, including nested scroll containers;
- use the established overlay z-index tokens rather than page-local z-index escalation.

Topbar menus no longer apply a local transform that conflicts with shared viewport collision handling.

## Scroll Ownership

| Level | Scroll contract |
|---|---|
| Browser/body | Locked by the persistent Application Shell composition |
| Application Shell root | No independent scrolling |
| Sidebar navigation | Vertical only when nav height is constrained |
| `mainContent` | Primary vertical page scroll owner |
| Table wrappers | Horizontal overflow only as required by wide data |
| Flow chart viewport | Horizontal overflow only for the existing minimum chart geometry |
| Dialog/Drawer body | Internal vertical scrolling only when content exceeds available top-layer height |
| Dropdown menu | Internal vertical scrolling only when viewport collision limits menu height |

Nested page + main + card vertical scrolling is not introduced.

Billing explicitly remains inside `mainContent`; no Billing page-level `height: 100vh` or `overflow: hidden` is introduced.

## Responsive Rules

1. Prefer CSS layout and media rules; no resize listener is added for ordinary page layout.
2. Use the shared page-composition thresholds `78rem`, `62rem`, `48rem`.
3. Retain established shell navigation thresholds `850px`, `620px` as a documented shell exception.
4. Do not add screenshot-specific breakpoints.
5. Apply `min-inline-size: 0` at analyzed grid/flex boundaries, not globally.
6. Wide tables/charts own their horizontal overflow.
7. PageHeader/FilterBar/actions wrap or stack through shared contracts rather than duplicate mobile page components.
8. Preserve domain behavior and query signatures during responsive changes.

## Light Theme

No Light-specific page override is introduced. Surfaces, borders, muted text, controls, tables, status presentation and charts remain semantic-token consumers.

## Dark Theme

No Dark-specific page implementation is introduced. App canvas, surfaces, elevated overlays/dialogs and charts continue to resolve through semantic/theme tokens.

## Accessibility

The pass preserves existing landmarks (`nav`, `header`, `main`), semantic table roles, labels, dialog semantics and heading structure.

Shared overlays retain keyboard focus behavior; Dropdown returns focus to its trigger on Escape/selection, Tooltip is exposed through `aria-describedby`, and existing focus-visible token styling remains intact. Hit-target geometry remains token-controlled and is not compressed for responsive layouts.

## Performance

No query, mutation, polling interval or domain calculation is added. Theme preference is not added to domain query keys. Ordinary responsive behavior remains CSS-driven.

The only runtime geometry listeners added by Task 24.18 belong to open portaled overlays and are attached only while the relevant overlay is open; they are removed on cleanup. This avoids global resize listeners and chart/page remount loops.

## Test Strategy

### Baseline

The branch was created from `main` commit `0fd7c92358d9e04dd622b9333473712277e430f9`.

The successful PR #127 CI used synthetic merge commit `d7e8a2a665403014608dcd63499cc57dee98644d`. Both commits point to the identical tree SHA `d1487ec7f96b8f2dcaa6cee4780b4552cdffaece`, so that CI is an exact pre-Task-24.18 source baseline.

Before implementation:

- Suites: 0 (`node:test` aggregate)
- Tests: 347 passed
- Failures: 0
- Skipped: 0
- Brand lint: PASS
- Design-system lint: PASS
- Hardcoded colors: 0
- Hardcoded structural spacing: 0
- Hardcoded border radius: 0
- Hardcoded typography: 0
- Lint: PASS with pre-existing warnings recorded by CI
- Typecheck: PASS
- Build: PASS

Task 24.18 adds `frontend/tests/aven-responsive-consistency.test.mjs` to guard shell scroll ownership, viewport-aware overlay positioning, Product Component narrow behavior, shared page-composition thresholds, outer page rhythm and table overflow containment.

Test configuration changes: **None**.

Environment variable changes: **None**.

Tests skipped: **None**.

Assertions weakened: **None**.

After-implementation CI values are recorded in the PR after the branch CI completes; they must not be inferred from source inspection.

## Cross-page Audit

Legend:

- `STATIC PASS` = route/source contract was audited and the responsive/overflow rule is present;
- `VISUAL PENDING` = exact interactive viewport rendering was not available in the connected GitHub-only implementation environment;
- `N/A` = no independent visual page exists (redirect/alias only).

| Page | 1280 | 1366 | 1440 | 1600 | 1920 | 2560 | Narrow | Overflow | Static status |
|---|---|---|---|---|---|---|---|---|---|
| Dashboard | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | contained | STATIC PASS |
| Billing | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | table/chart contained | STATIC PASS |
| Reservations | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | table contained | STATIC PASS |
| Inventory | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | table contained | STATIC PASS |
| Recommendations | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | cards/table contained | STATIC PASS |
| Settings | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | tabs/tables contained | STATIC PASS |
| Flow | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | chart/table contained | STATIC PASS |
| Collections list/detail/compare | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | scoped table contained | STATIC PASS |
| Scans | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | VISUAL PENDING | STATIC PASS | table contained | STATIC PASS |

### Functional Change Gate

- New API behavior introduced? **NO**
- New domain behavior introduced? **NO**
- New calculations introduced? **NO**
- New product feature introduced? **NO**
- New route introduced? **NO**
- New persistence introduced? **NO**
- Existing functional defaults changed? **NO**

### Test Integrity Gate

- Test config changed merely for this task? **NO**
- Environment variables changed? **NO**
- Tests skipped? **NO**
- Assertions weakened? **NO**
- Global mocks modified speculatively? **NO**
- New mutable test globals introduced? **NO**
- Full `npm test` after implementation: **CI PENDING**

## Remaining Visual Debt

1. **Interactive viewport evidence:** exact rendered checks for 1280×720, 1366×768, 1440×900, 1600×900, 1920×1080, 2560×1440, 1024, 768, 480, 375 and 1366×650 require an interactive browser. The connected implementation environment for this task does not expose one, so these checks are intentionally not fabricated. They must be completed before the Responsive Gate can be declared fully PASS.
2. **Task 24.17 root documentation duplicate:** `AVEN_DATA_VISUALIZATION_SYSTEM.md` still exists at repository root. Task 24.18 adds the canonical copy under `docs/brand/aven/`; deletion of the proven-dead root duplicate belongs to Task 24.19 legacy cleanup.
3. **Existing lint warnings outside this task's visual changes:** warnings already present in the exact pre-task CI baseline are not hidden by configuration changes. Any broader cleanup remains separately scoped unless a Task 24.18 change causes a new warning.

Until item 1 is completed with real rendered evidence, Task 24.19 readiness must not be reported as fully YES solely from static source/CI validation.
