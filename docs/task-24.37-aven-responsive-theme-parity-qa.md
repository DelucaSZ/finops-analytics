# Task 24.37 — Aven Responsive & Theme Parity QA

## Scope

This task is a regression QA/correction pass over the visual architecture delivered by Tasks 24.31–24.36. It does not redesign the product and does not modify API contracts, authentication, authorization, queries, calculations, filtering semantics or backend behavior.

The validation method available in the repository is:

- source-level audit of shared Aven layout, shell, theme, table and overlay contracts;
- structural `node:test` regression coverage;
- the existing frontend CI gates (`lint:brand`, `lint:design-system`, lint, typecheck, tests and production build);
- existing page-specific structural coverage for Dashboard, Opportunities/History, Inventory, Flow, Billing, Reservations and Settings.

The repository does not currently include Playwright, Cypress or an equivalent browser screenshot runner. This task therefore does **not** claim screenshot/pixel validation for every width/theme combination and does not add a large E2E stack solely for this pass.

## Responsive QA matrix

The width matrix below records the responsive contract exercised by the shared shell/page composition. `Structural` means that the behavior is covered by CSS/source invariants and automated tests; it is not a claim of pixel-perfect browser screenshots.

| Viewport | Status | Contract validated |
| --- | --- | --- |
| 1920px | Structural | wide page max-width, shared gutters, fluid grids/tables |
| 1680px | Structural | wide page composition without exact-width hacks |
| 1440px | Structural | natural shared breakpoint progression |
| 1366px | Structural / priority | page reacts to available inline size after Sidebar width |
| 1280px | Structural / priority | container-aware filters and grid density |
| 1024px | Structural / priority | wrapping, split-grid collapse, table-local overflow |
| 768px | Structural | compact shell/drawer behavior and stacked filters remain accessible |

Limited-height scenarios are protected structurally by viewport-relative overlay/dialog constraints (`100dvh`), internal overlay scrolling and shell-owned page scrolling. The intended scenarios are 1366x768, 1440x900 and 1920x1080; no browser screenshots are claimed for those dimensions in this task.

## Theme QA matrix

| Theme | Status | Contract validated |
| --- | --- | --- |
| Light | Structural | resolved `data-theme`, semantic tokens, `color-scheme` |
| Dark | Structural | resolved `data-theme`, semantic tokens, `color-scheme` |
| System → OS Light | Structural | live `matchMedia` resolution and DOM update |
| System → OS Dark | Structural | live `matchMedia` resolution and DOM update |
| Persistence | Structural | explicit preference storage remains distinct from resolved theme |
| Initial load / FOUC guard | Structural | pre-hydration theme bootstrap runs before body hydration |

No Theme Engine rewrite was required. The existing engine already updates System mode live and keeps persistence semantics intact; Task 24.37 adds regression coverage for those contracts.

## Pages audited

The shared responsive/theme contracts and existing page-specific tests cover:

- Dashboard;
- Opportunities;
- History;
- Inventory;
- Flow;
- Billing;
- Reservations;
- Settings and existing secondary Settings routes;
- Login/branding surfaces where theme-aware official Aven assets are used.

## Regressions found and corrected

### Layout / Responsive — page width did not fully reflect Sidebar state

**Finding:** page-level responsive composition primarily depended on browser viewport media queries. At notebook widths, an expanded Sidebar can materially reduce content width without crossing a viewport breakpoint, so FilterBar/grid composition could remain too dense.

**Correction:** `PageContainer` is now an inline-size query container. Shared filter composition responds to the actual page width after the Application Shell has resolved expanded/collapsed Sidebar geometry. Existing media queries remain as compatibility fallbacks.

This is semantic responsive behavior; there are no exact-resolution rules such as `@media (width: 1366px)`.

### Responsive — Inventory metric grid had an abrupt density jump

**Finding:** Inventory changed from four metric columns directly to two at the existing medium breakpoint.

**Correction:** Inventory now follows 4 → 3 → 2 → 1 columns according to available page width, with equivalent viewport fallbacks. This preserves readable metrics while avoiding oversized empty gaps.

### Wrapping — shared Badge forced `nowrap`

**Finding:** the shared Badge primitive forced all badge content onto one line. Long provider/status combinations could therefore contribute to clipping pressure in narrow analytical columns.

**Correction:** badges expose a semantic `data-aven-badge` hook and use controlled wrapping (`overflow-wrap`) with a maximum inline size. Critical status content remains recoverable instead of being silently clipped.

## Contracts audited without new implementation

### Sidebar

The existing Application Shell already uses shrink-safe `minmax(0, 1fr)` columns for expanded and collapsed states, `min-inline-size: 0` for the workspace/content chain, a compact Drawer mode, persisted desktop collapse state and `prefers-reduced-motion` handling. Task 24.37 adds guardrails around these invariants and makes inner page composition react to the resulting available width.

### Tables

The shared Table wrapper already owns horizontal overflow (`overflow-x: auto`) with a 100% maximum inline size, so analytical tables can scroll internally without intentionally creating body/page horizontal scroll. Task 24.37 adds a regression assertion for this contract and for badge wrapping inside dense columns.

### Dropdowns, popovers and tooltips

Shared overlay positioning already:

- portals floating content outside clipping parents;
- clamps inline position to viewport bounds;
- flips above/below according to available space;
- reacts to window resize, ancestor scroll and `visualViewport` resize/scroll;
- constrains dropdown/tooltips to viewport-relative maximum sizes.

No replacement positioning system was introduced.

### Billing date range

The current shared `DateRangePicker` uses browser-native `input[type=date]` controls rather than a detached custom datepicker popover. The historical detached-anchor failure mode is therefore not reintroduced by this implementation.

### Modals and drawers

Existing overlays already use viewport-relative maximum block sizes and internal scrolling. No new z-index scale or global `overflow: hidden` policy was added.

### Charts

Existing Dashboard/Billing/Flow tests and styles already enforce responsive chart containment and semantic visualization tokens. This task does not redesign chart palettes; theme parity remains token-driven.

## Automated regression coverage added

`frontend/tests/aven-responsive-theme-parity.test.mjs` protects:

1. Sidebar expanded/collapsed/compact shrink safety and reduced motion;
2. container-aware page/filter responsiveness and absence of exact-resolution hacks;
3. Inventory 4 → 3 → 2 → 1 density progression;
4. table-local horizontal overflow and recoverable Badge wrapping;
5. Light/Dark/System live theme resolution, persistence and pre-hydration bootstrap;
6. dropdown/tooltip visual-viewport collision handling and modal viewport bounds.

The existing repository tests continue to cover page-specific composition, FilterBar contracts, Opportunities clipping regressions, Billing responsiveness/date controls, branding, chart tokens, surface hierarchy and Theme Engine behavior.

## Files changed by Task 24.37

- `frontend/app/layout-system.css`
- `frontend/app/inventory/inventory.module.css`
- `frontend/components/ui/badge.tsx`
- `frontend/tests/aven-responsive-theme-parity.test.mjs`
- `docs/task-24.37-aven-responsive-theme-parity-qa.md`

## Validation commands

The PR CI is the authoritative executable gate and runs the required frontend sequence:

```bash
cd frontend
npm ci
npm run lint:brand
npm run lint:design-system
npm run lint
npm run typecheck
npm test
npm run build
```

It also builds the production frontend image after a successful Next.js production build.

## Deliberate non-changes

- no backend/API/business-logic changes;
- no authentication/authorization changes;
- no query/filter calculation changes;
- no redesign of Tasks 24.31–24.36;
- no new FilterBar, Table, Theme Engine or overlay system;
- no exact-resolution media-query hacks;
- no forbidden hardcoded colors, radius, spacing or typography;
- no broad browser-compatibility initiative;
- no heavy Playwright/Cypress installation solely to produce screenshots for this task.
