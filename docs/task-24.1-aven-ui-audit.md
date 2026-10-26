# Task 24.1 — Aven UI Audit

## 1. Executive Summary

This audit establishes the current frontend baseline before the DeepOps → Aven visual migration. No visual behavior is changed by this task.

The frontend is a Next.js 15.2 / React 19 / TypeScript application using the App Router. Styling is built from global CSS plus CSS Modules, with no Tailwind, CSS-in-JS framework, component library, or chart library. `lucide-react` is the only explicit UI/icon dependency.

The main architectural finding is that the current UI has three overlapping styling layers:

1. `app/globals.css` — original/legacy global design language and page/component selectors;
2. `app/ui-system.css` — newer light/dark variables, component-level global rules, and legacy aliases;
3. `app/legacy-theme-compat.css` — compatibility overrides that make legacy selectors survive the newer theme model.

Additional page-specific global styles and 10 CSS Modules sit on top of those layers. The repository currently contains 17 CSS files under `frontend/`, approximately 174 KB in total.

The current theme engine is functional and already supports `light`, `dark`, and `system`, including a pre-hydration bootstrap to reduce incorrect-theme flash. However, theme resolution/application is duplicated across `app/layout.tsx`, `components/app-shell.tsx`, and `components/theme-selector.tsx`.

The largest blockers for a token-only Aven component architecture are:

- visual literals remain widespread in global CSS and page CSS Modules;
- the semantic meaning of existing CSS variables is incomplete and mixed with legacy aliases;
- typography is not centrally tokenized and `Inter` is referenced in CSS but not explicitly loaded by the application;
- page-level CSS frequently owns controls, cards, badges, tables, chart surfaces, spacing and responsive behavior that should be primitives/product components;
- `AppShell` combines visual shell, navigation, authentication gating, preference persistence and responsive state;
- chart implementations are custom and have visual rules embedded in TSX/CSS;
- responsive breakpoints and spacing/radius scales are inconsistent;
- legacy DeepOps/NuvemIQ identifiers exist in both user-visible branding and compatibility/infrastructure code and cannot be blindly renamed.

### Decision

**Task 24.2 is ready to start: YES.**

The audit found no blocker requiring a redesign first. Task 24.2 should create the semantic token contract and a temporary compatibility alias layer before any page migration.

---

## 2. Current Frontend Stack

| Area | Current implementation | Audit conclusion |
|---|---|---|
| Framework | Next.js `^15.2.0` | App Router |
| React | React / React DOM `^19.0.0` | Client-heavy screens |
| Language | TypeScript `^5.7.0` | Keep |
| Routing | `frontend/app/**/page.tsx` | 31 page routes catalogued |
| CSS | Global CSS + CSS Modules | No Tailwind/CSS-in-JS |
| UI library | None | Aven primitives will be first internal component system |
| Icons | `lucide-react ^0.468.0` | Keep behind future iconography rules |
| Charts | No external chart library | Custom SVG/DOM/CSS implementations |
| Forms | Native React/forms | No form framework |
| Fonts | CSS font stacks | `Inter` referenced but not explicitly bundled/imported |
| UI state | Local React state + URL state | Keep where appropriate |
| Server state | Custom `useApiQuery` / query-key layer | Outside visual migration |
| Theme persistence | `localStorage` | Key: `deepops.theme` |
| Sidebar persistence | `localStorage` | Key: `deepops.sidebar.collapsed` |
| Theme modes | `system`, `light`, `dark` | Functional today |
| System theme | `matchMedia('(prefers-color-scheme: dark)')` | Functional today |
| Tests | Node test runner | `npm test` → `node --test tests/*.test.mjs` |
| Build | Next production build | `npm run build` |

No evidence was found of Tailwind, styled-components, Emotion, MUI, Chakra, Radix, shadcn, Bootstrap, Recharts, Chart.js, D3, or a form library in `package.json`.

---

## 3. Current Styling Architecture

### 3.1 Global load order

`app/layout.tsx` loads CSS in this order:

1. `globals.css`
2. `opportunities-stage5.css`
3. `ui-system.css`
4. `legacy-theme-compat.css`
5. `dashboard-executive.css`
6. `dashboard-operational-insights.css`
7. `task-23-25-layout.css`

This order is material. The current UI depends on later files overriding earlier global selectors. Migration must therefore remove legacy layers incrementally, not by deleting `globals.css` at the start.

### 3.2 CSS inventory

| File | Approx. size | Function | Disposition | Risk |
|---|---:|---|---|---|
| `app/globals.css` | 50.9 KB | Legacy global foundation + many page/component selectors | MIGRATE then REMOVE legacy portions | P0 |
| `app/opportunities-stage5.css` | 22.5 KB | Opportunities-specific global styling | MIGRATE to product components/module | P1 |
| `app/ui-system.css` | 16.7 KB | Current light/dark variables and shared global components | REPLACE/EVOLVE into Aven semantic layer | P0 |
| `app/legacy-theme-compat.css` | 2.2 KB | Theme compatibility overrides | TEMPORARY; REMOVE at end | P0 |
| `app/dashboard-executive.css` | 0.4 KB | Dashboard visual patch | CONSOLIDATE | P2 |
| `app/dashboard-operational-insights.css` | 2.7 KB | Dashboard insight styling | MIGRATE | P1 |
| `app/task-23-25-layout.css` | 2.5 KB | Layout fixes from prior work | ABSORB into components/tokens | P1 |
| `app/billing/billing.module.css` | 12.6 KB | Billing layout, filters, KPIs, chart, table | MIGRATE | P1 |
| `app/collections/collection.module.css` | 3.8 KB | Collection workspace/page visuals | MIGRATE | P2 |
| `app/flow/flow-layout.module.css` | 13.2 KB | Flow route-specific corrective layout | REBUILD around product components | P1 |
| `app/opportunities/history-cycles/page.module.css` | 3.6 KB | History page visuals | MIGRATE | P2 |
| `app/rds/reservations/rds-reservations.module.css` | 18.9 KB | RDS dashboard/tables/filters | MIGRATE | P1 |
| `app/settings/settings-layout.module.css` | 7.1 KB | Settings shell/navigation | MIGRATE | P1 |
| `app/settings/opportunities/page.module.css` | 3.5 KB | Settings page visuals | MIGRATE | P2 |
| `app/settings/pricing/oci/pricing.module.css` | 4.3 KB | OCI pricing visuals | MIGRATE | P2 |
| `app/settings/usage-costs/usage-costs.module.css` | 7.9 KB | Usage/cost configuration visuals | MIGRATE | P2 |
| `components/manual-collection-launcher.module.css` | 1.1 KB | Shared launcher visuals | REFACTOR | P2 |

### 3.3 Architecture conclusion

The codebase is not missing a design layer; it has a transitional design layer that still depends on legacy globals. Task 24.2 must not simply rename current variables. It must introduce a clean primitive → semantic → component token hierarchy while providing compatibility aliases until migrated screens stop consuming legacy names.

---

## 4. Current Theme Architecture

### Current flow

```text
User preference
    ↓
localStorage: deepops.theme
    ↓
normalizeThemePreference / resolveThemePreference
    ↓
pre-hydration bootstrap + AppShell/ThemeSelector runtime application
    ↓
<html data-theme-preference="..." data-theme="light|dark" style="color-scheme: ...">
    ↓
ui-system.css variables
    ↓
legacy-theme-compat.css overrides
    ↓
page/global/module CSS
    ↓
component
```

### What works

- `light`, `dark`, `system` preferences exist.
- System mode uses `prefers-color-scheme` through `matchMedia`.
- The preference is persisted in `localStorage`.
- The root layout applies the theme before React hydration, reducing FOUC.
- `suppressHydrationWarning` is already used on `<html>`.
- Runtime system changes and storage changes are observed in the application shell.

### Debt / risk

- Theme application logic exists in three places: `layout.tsx`, `app-shell.tsx`, and `theme-selector.tsx`.
- Storage key and custom event names contain legacy `deepops` branding.
- The server does not know the preference; the system is browser/localStorage centric.
- Legacy selectors need compatibility overrides to respect light mode.
- Some page styles still use literal dark surfaces/rgba values rather than semantic theme values.
- `ui-system.css` combines tokens, legacy aliases, shell styling and component styling in one file.

### Recommendation for 24.3

Create one theme controller API responsible for reading, resolving, applying, observing and persisting theme. Keep a tiny pre-hydration bootstrap generated from the same constants/contract. Do not rename storage keys in 24.3 unless compatibility/migration behavior is explicit; technical branding rename belongs to 24.8.

---

## 5. Global CSS Inventory

Current global responsibilities are too broad. They include:

- root variables;
- body/html resets;
- shell/sidebar/topbar rules;
- page headers;
- buttons and controls;
- panels/cards;
- tables;
- badges/statuses;
- alerts;
- dialogs/drawers;
- login/auth visuals;
- opportunity visuals;
- dashboard visuals;
- responsive overrides;
- compatibility rules.

The migration target is:

```text
Aven primitive tokens
    ↓
Aven semantic tokens (light/dark)
    ↓
UI primitives
    ↓
Product components
    ↓
Page composition only
```

Page CSS should eventually own composition/layout exceptions, not reimplement the visual contract of buttons, inputs, cards, badges, tables, dialogs or typography.

---

## 6. Shared Components Inventory

| Component | Current role | Classification | Aven destination |
|---|---|---|---|
| `PageHeader` | Shared page title/description/actions markup | REFACTOR | Product `PageHeader` using typography/button primitives |
| `StatusBadge` | Maps domain statuses to global CSS classes | REFACTOR | Primitive `Badge` + product `StatusIndicator` mapping |
| `ThemeSelector` | Theme choice UI + theme mutation logic | REFACTOR | Product settings control over centralized theme API |
| `AppShell` | Auth gate, navigation, brand, sidebar, mobile header, theme sync | REBUILD | Aven Shell; extract/preserve non-visual behavior |
| `ExecutiveDashboard` | Dashboard composition + KPIs/distributions/states | REFACTOR | Golden reference built from Aven product components |
| `DashboardOperationalInsights` | Dashboard operational insight block | REFACTOR | Product visualization/insight component |
| `ManualCollectionLauncher` | Reusable collection action UI | REFACTOR | Product action component on primitives |
| `CollectionWorkspace` | Large domain workspace | REFACTOR | Split into smaller product components |
| `CollectionComparisonActions` | Collection comparison actions | REFACTOR | Product component |
| `CollectionOpportunityInvestigation` | Domain investigation UI | REFACTOR | Product component |
| `CollectionScheduleFields` | Scheduling fields | REFACTOR | Product fields over form primitives |
| `OpportunityDetail` | Large opportunity domain UI | REFACTOR | Split into product sections |
| `OpportunityDecisionDialog` | Domain decision modal | REFACTOR | Product dialog over `Dialog` primitive |
| `OpportunityArchiveDialog` | Domain archive modal | REFACTOR | Product dialog over `Dialog` primitive |
| `OpportunityArchiveHistory` | Archive history | REFACTOR | Product history/table component |
| `OpportunityPresenceHistory` | Presence history | REFACTOR | Product history component |
| `FindingEvidence` | Evidence presentation | REFACTOR | Product evidence component |
| `IdentityProof` | Identity/security presentation | REFACTOR | Product security component |
| `AccessForm` | Auth/access form reuse | REFACTOR | Auth product form over form primitives |
| `MfaSettings` | MFA settings workflow | REFACTOR | Security product component |

No shared component inspected should be removed solely because of the rebrand. Most contain reusable behavior. The visual shell is the exception where rebuilding composition is safer than layering more global overrides.

---

## 7. Route/Page Inventory

The App Router exposes 31 page routes.

| Route | Area | Styling/dependency profile | Visual complexity | Migration priority | Risk |
|---|---|---|---|---|---|
| `/` | Dashboard | Global dashboard CSS + shared components | High | 24.10 | High |
| `/accept-invitation` | Auth | Legacy auth/global CSS | Medium | 24.9/24.17 | Medium |
| `/billing` | Billing | `billing.module.css`, custom SVG chart | Very high | 24.11 | High |
| `/collections` | Collections | Global + collection/product components | High | 24.15/24.17 | High |
| `/collections/[collectionId]` | Collections workspace | `collection.module.css`, large workspace | Very high | 24.15/24.17 | High |
| `/collections/[collectionId]/compare` | Collections comparison | Collection/product components | High | 24.15/24.17 | High |
| `/finops/ledger` | Ledger | FinOps/domain visuals | High | 24.17 | High |
| `/flow` | FinOps Flow | `flow-layout.module.css` + global selectors | Very high | 24.17 | High |
| `/forgot-password` | Auth | Legacy auth/global CSS | Medium | 24.9 | Medium |
| `/login` | Auth | Legacy login global CSS + DeepOps branding | High | 24.9 | High |
| `/mfa-setup` | Auth/Security | Auth/global CSS | Medium | 24.9/24.16 | Medium |
| `/opportunities` | Opportunities | `opportunities-stage5.css`, large page | Very high | 24.14 | High |
| `/opportunities/collection/[collectionId]` | Opportunities | Opportunity product components | High | 24.14 | High |
| `/opportunities/history-cycles` | Opportunities history | CSS Module + global components | High | 24.14/24.17 | Medium |
| `/rds/reservations` | RDS reservations | Large CSS Module, dashboard/table/filter patterns | Very high | 24.12 | High |
| `/reset-password` | Auth | Legacy auth/global CSS | Medium | 24.9 | Medium |
| `/scans` | Collections/scans | Global/shared collection visuals | High | 24.15/24.17 | Medium |
| `/security` | Security | Shared/security composition | Medium | 24.16 | Medium |
| `/settings` | Settings landing | Settings shell/global shared | Medium | 24.16 | Medium |
| `/settings/accounts` | Accounts | Large settings page | Very high | 24.16 | High |
| `/settings/appearance` | Appearance | `PageHeader` + `ThemeSelector` | Low | 24.16 | Medium |
| `/settings/audit` | Audit | Large settings page/table | High | 24.16 | High |
| `/settings/billing/profiles` | Billing profiles | Settings/form/table patterns | High | 24.16 | High |
| `/settings/https` | HTTPS | Settings/forms/status | High | 24.16 | Medium |
| `/settings/opportunities` | Opportunity settings | CSS Module | High | 24.16 | Medium |
| `/settings/policies` | Policies | Settings/forms | High | 24.16 | Medium |
| `/settings/pricing/oci` | OCI Pricing | `pricing.module.css` | High | 24.16 | Medium |
| `/settings/security` | Security settings | Settings/security components | High | 24.16 | Medium |
| `/settings/sessions` | Sessions | Settings/table/actions | Medium | 24.16 | Medium |
| `/settings/usage-costs` | Usage/cost settings | `usage-costs.module.css` | High | 24.16 | Medium |
| `/settings/users` | Users | Large settings/table/dialog page | Very high | 24.16 | High |

### Route-wide risks

- large TSX pages own both orchestration and visual composition;
- page CSS frequently redefines patterns that should become primitives/product components;
- many tables require horizontal scrolling and fixed minimum widths;
- several newer route modules use `color-mix()` while older selectors depend on rgba/legacy variables;
- layout fixes are often selector-structure dependent (`nth-of-type`, `:global`, `!important`).

---

## 8. Hardcoded Visual Values

Hardcodes are widespread and are a **P0 blocker** for the Task 24.5 rule if new primitives were built on top of the current styling architecture.

### Categories found

- colors: hex, rgb/rgba, transparent overlays, `color-mix()` percentages;
- radius: literal `2px`, `5px`, `7px`, `8px`, `9px`, `10px`, `11px`, `12px`, `14px`, pill `50%/99px` plus CSS variables;
- spacing: frequent `2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 22, 24px` and larger layout values;
- typography: rem and px sizes, multiple nonstandard weights such as `650`, `750`, `800`, `850`, `900`;
- shadows: literal rgba shadows plus `--shadow`;
- z-index: local literals including chart tooltip and shell layers;
- transitions: repeated literal timings (for example 120ms/180ms);
- chart geometry: SVG dimensions, margins, bar widths, rotation angles and opacity values in TSX;
- responsive geometry: fixed/min widths such as 560/960/1050/1180px and route-specific grid breakpoints.

### Rule for 24.5+

From Task 24.5 onward, new visual components must consume semantic/design tokens for color, radius, spacing and typography. Exceptions such as SVG geometry or data-derived dimensions should be explicit and documented; they must not become an escape hatch for visual styling literals.

---

## 9. Color Inventory

### Legacy/current root colors

The original global root includes values such as:

- background `#070b10`;
- surfaces `#0c131b`, `#111b26`, `#172331`;
- text `#e7eef6`;
- muted text `#93a4b6`, `#6f8296`;
- border `#1e3042`;
- accent `#ff3d7f`, secondary accent `#ff6b9d`;
- blue `#4ea1ff`;
- violet `#8b7bff`.

### Transitional `ui-system.css` semantic-ish colors

Light mode defines `--background`, `--foreground`, `--surface`, `--surface-muted`, borders, primary, success, warning, danger, info, focus and five chart variables. Dark mode overrides the same conceptual set. It also aliases old names (`--bg`, `--text`, `--surface-2`, `--accent`, etc.) for compatibility.

### Future semantic groups

Task 24.2 should define at minimum:

- `background.canvas`;
- `background.subtle`;
- `surface.default`, `surface.raised`, `surface.sunken`, `surface.overlay`;
- `text.primary`, `text.secondary`, `text.tertiary`, `text.inverse`, `text.brand`;
- `border.default`, `border.strong`, `border.focus`;
- `action.primary.*`, `action.secondary.*`, `action.destructive.*`;
- `status.success.*`, `status.warning.*`, `status.danger.*`, `status.info.*`, `status.neutral.*`;
- `focus.ring`;
- `chart.series.1..N`;
- `chart.forecast`, `chart.estimated`, `chart.grid`, `chart.axis`, `chart.tooltip.*`.

The Aven palette under `docs/brand/aven/` is canonical. Current colors are migration inputs only, not design authority.

---

## 10. Typography Inventory

### Current state

- `globals.css` references `Inter, ui-sans-serif, system-ui, ...` for the body.
- There is no explicit `next/font` import or font asset in the inspected application root.
- Sizes are implemented through a mixture of px/rem/clamp.
- Weight values include standard and nonstandard values (`650`, `750`, `850`, etc.).
- KPI/numeric values often use `font-variant-numeric: tabular-nums`.
- Resource identifiers use a monospace stack (`SFMono-Regular`, Consolas, monospace) in at least RDS/table UI.

### Aven direction

- Brand/display: geometric / Sora-like.
- UI: Inter.
- Supported weights: 400 / 500 / 600 / 700.

### 24.4 requirements

Create named text styles for display, page title, section title, body, label, caption, button, table header/body, KPI, code/resource identifier. Replace arbitrary weights and page-local type scales with these styles.

---

## 11. Spacing Inventory

A consistent implicit scale exists, but the UI also uses many off-scale values.

### Common values observed

`4, 8, 12, 16, 20, 24, 32px` occur conceptually across layout/component rules and align with the planned Aven scale.

### Frequent divergences

`2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 18, 22px` are also common, especially inside controls, badges, tables and corrective page layout CSS.

### Aven target scale

`4, 8, 12, 16, 20, 24, 32, 40, 48, 64`.

Task 24.2/24.4 should define semantic spacing roles in addition to primitive scale values; otherwise pages will merely replace literals with arbitrary primitive-token choices.

---

## 12. Radius Inventory

Observed radius usage includes:

- tiny chart/detail geometry: `1–2px`;
- controls and small surfaces: `5–10px`;
- cards/panels: `9–14px` and `var(--radius)`;
- special surfaces/details: `11–12px`;
- pills/progress/segmented bars: `50%`, `99px`;
- current variables: `--radius-sm: 6px`, `--radius-md: 9px`, `--radius-lg: 12px`, plus legacy `--radius: 14px`.

Aven direction is approximately controls `10px`, cards `16px`, modals `18px`. Task 24.4 should formalize semantic radius names (`control`, `card`, `dialog`, `pill`, `round`) rather than exposing page code to raw numeric tokens.

---

## 13. Data Visualization Inventory

There is no chart dependency in `package.json`; visualization is hand-built.

| Page/area | Component / implementation | Type | Current visual contract | Main risk |
|---|---|---|---|---|
| Billing | `BillingCostChart` | Stacked/custom SVG bar chart | 8-series CSS-variable palette, forecast opacity/dashes, tooltip, axes, legend | Visual rules and geometry embedded in TSX/CSS |
| Dashboard | `ExecutiveDashboard` | KPI/distribution/breakdown visualizations | Global dashboard classes | Golden-reference migration touches shared metrics/distributions |
| Dashboard | `DashboardOperationalInsights` | Operational insight visualization | Dedicated global CSS | Separate styling layer |
| RDS reservations | route implementation + module CSS | Coverage/progress/stacked summaries | Accent/warning/danger segments | Reimplements chart/status semantics |
| Flow | route SVG + corrective module CSS | Temporal/custom SVG visuals | Selector-based geometry overrides | Extremely coupled to DOM structure |

### Billing chart specifics

The chart currently contains hardcoded visual geometry and behavior such as:

- 8-series palette references;
- max series count derived from palette length;
- tooltip edge threshold;
- opacity per ACTUAL/ESTIMATED/FORECAST state;
- SVG margins, preferred slot size, min/max chart width, fixed height;
- bar width/radius;
- axis tick count;
- label rotation;
- dashed forecast stroke;
- tooltip positioning and sizing.

These are valid visualization concepts but should be divided into data/geometry configuration versus visual tokens.

### Sequence implication

Task 24.18 cannot remain entirely after Dashboard (24.10) and Billing (24.11). At minimum the **chart token contract and forecast/estimated visual semantics must be defined before 24.10/24.11**. Recommended execution order moves the full 24.18 foundation before the first chart-heavy page migration, or splits 24.18 into foundation-before-pages + final consistency pass later.

---

## 14. Responsive Architecture

The current responsive model is distributed across global and module CSS rather than centralized.

Findings:

- route modules define their own breakpoints;
- `Flow` includes explicit `1100px` and `900px` transitions and minimum chart/table widths;
- legacy compatibility rules also use `900px` behavior;
- Billing uses horizontally scrollable chart canvas with a minimum chart width of 960px;
- Flow tables use minimum widths around 1050px;
- RDS tables use minimum widths around 1180px;
- large grids depend on `auto-fit`, fixed column counts and page-local thresholds;
- shell mobile behavior is controlled in `AppShell` plus global CSS.

### Required test widths for migration

Each migrated page must be visually verified at 1280, 1366, 1440, 1600, 1920 and 2560, plus narrower notebook/tablet widths. Aven should define a small canonical breakpoint set in 24.4/24.19 rather than preserving every current page-specific breakpoint.

---

## 15. Accessibility Findings

This is an initial visual/accessibility audit, not a full WCAG conformance review.

Positive findings:

- skip link exists in `AppShell`;
- navigation uses ARIA labels;
- Billing chart provides `role="img"` and an accessible label;
- errors frequently use `role="alert"`;
- loading/empty states are represented explicitly;
- form inputs generally use native controls.

Risks to address during component standardization:

- icon-only controls must consistently receive labels/tooltips;
- focus treatment is not centralized across all legacy controls;
- status meaning is frequently encoded with color plus class conventions and should retain textual/icon cues;
- small labels/badges use 0.6875rem/11px in several places;
- horizontal tables and charts need keyboard/scroll usability review;
- disabled/hover/focus-visible behavior is not generated from a single state model;
- selector-based compatibility CSS can accidentally suppress visible focus states.

A full accessibility QA should be performed after primitives and again during 24.20.

---

## 16. Legacy Branding Inventory

Legacy branding appears in multiple categories and must be migrated selectively.

| Occurrence/category | Example | User-visible? | Rename strategy | Risk |
|---|---|---:|---|---|
| Metadata | `DeepOps | FinOps Multi-Cloud` in root layout | Yes | 24.8 | Low |
| App shell brand | `DeepOps`, navigation ARIA label | Yes | 24.7/24.8 | Medium |
| Login brand/copy | `DeepOps`, CloudCog mark | Yes | 24.9 | Low |
| Appearance copy | “tema visual do DeepOps” | Yes | 24.8/24.16 | Low |
| Theme storage | `deepops.theme` | No | compatibility migration in 24.8 | Medium |
| Sidebar storage | `deepops.sidebar.collapsed` | No | compatibility migration in 24.8 | Medium |
| Custom events | `deepops:theme-change`, session event | No | rename only with dual compatibility | Medium |
| Local storage cleanup | `nuvemiq_token` | No | retain until auth compatibility verified | High |
| Infrastructure filenames/templates | DeepOps/NuvemIQ names | No | out of visual task; rename only with infra plan | High |
| API/config identifiers | possible DeepOps/NuvemIQ technical identifiers | No | do not blindly rename | High |
| Tests/docs | legacy terminology | Mixed | update with owning implementation | Medium |

Rule: visible branding can migrate on the planned rebrand tasks. Storage keys, environment variables, APIs, infrastructure identifiers, database fields and compatibility names require an explicit migration strategy and may intentionally remain legacy internally.

---

## 17. Visual Technical Debt

### P0 — blocks the design system

1. Legacy global values and selectors coexist with the newer theme system.
2. No canonical Aven semantic token contract is consumed by components.
3. Hardcoded color/radius/spacing/typography remains widespread.
4. `ui-system.css` mixes token definitions with component/shell styling and legacy aliases.
5. Theme application logic is duplicated across three code paths.
6. Page CSS reimplements primitives such as controls, cards, badges, tables and states.
7. Data visualization has no shared visual contract.

### P1 — high impact

1. `AppShell` is coupled to auth, navigation, responsive layout, theme and branding.
2. Large page/workspace components increase migration blast radius.
3. `Flow` relies on DOM-order selectors, `:global`, `nth-of-type`, and `!important` corrective styling.
4. Billing/RDS/Opportunities have substantial route-local visual systems.
5. Responsive behavior and minimum widths vary by route.
6. Typography uses arbitrary weights/sizes and lacks explicit font delivery.
7. Legacy compatibility CSS can hide theme regressions until it is removed.

### P2 — medium impact

1. Multiple local implementations of empty/loading/error states.
2. Multiple badge/pill/progress implementations.
3. Repeated table/filter/header structures.
4. Repeated transition/shadow/z-index literals.
5. Settings pages duplicate common form/table composition.
6. Dashboard-specific global CSS is split into patches.

### P3 — cosmetic / low impact

1. Small off-scale spacing values.
2. Inconsistent micro-radius values.
3. Minor label/letter-spacing differences.
4. Local visual patches left by historical tasks.

---

## 18. Aven UI Primitive Candidates

| Primitive | Exists today? | Current implementations | Consolidation | Priority |
|---|---:|---|---|---|
| Button | Yes | Global `.button` + local variants | Yes | P0 |
| IconButton | Partial | Local buttons in shell/tables/dialogs | Yes | P0 |
| Input | Yes | Global + page/module variants | Yes | P0 |
| Textarea | Yes | Global/page variants | Yes | P0 |
| Select | Yes | Global + many page/module variants | Yes | P0 |
| Checkbox | Yes | Native + page styles | Yes | P0 |
| Radio | Yes | Theme selector/native | Yes | P1 |
| Switch | Partial/route-specific | Not canonical | Yes | P1 |
| Badge | Yes | `StatusBadge` + local badges | Yes | P0 |
| Tooltip | Partial | Native title/custom Billing tooltip | Yes | P1 |
| Dropdown/Menu | Partial | Shell/local controls | Yes | P1 |
| Tabs | Yes | RDS and route-local variants | Yes | P1 |
| Dialog | Yes | Opportunity dialogs/global rules | Yes | P0 |
| Drawer | Yes | Global/shell patterns | Yes | P1 |
| Card | Yes | `.panel`, metric cards, route cards | Yes | P0 |
| Table | Yes | Global + multiple route variants | Yes | P0 |
| Pagination | Yes | Global/module variants | Yes | P1 |
| Skeleton | Yes | Dashboard/global classes | Yes | P1 |
| Alert | Yes | Global `.alert` + local alerts | Yes | P0 |
| EmptyState | Yes, inconsistent | Multiple route implementations | Yes | P1 |
| Toast | Limited/not canonical | No single audited primitive | Yes | P2 |
| Divider | Implicit | Borders/local elements | Yes | P2 |
| Popover | Partial | Tooltips/menus/date-related UI | Yes | P1 |
| Avatar | Limited | User/account UI dependent | Yes if required | P2 |

Task 24.5 should implement primitives only after 24.2–24.4 freeze semantic APIs for color, type, spacing, radius, shadow, motion/focus and iconography.

---

## 19. Aven Product Component Candidates

Recommended product-layer components:

- `PageHeader`;
- `MetricCard` / `KpiCard`;
- `FilterBar`;
- `AccountSelector`;
- `EnvironmentSelector` / provider scope selector;
- `DateRangePicker`;
- `ChartCard`;
- `Section` / `PanelSection`;
- `StatusIndicator`;
- `RecommendationCard` / `OpportunityCard`;
- `CostSummary`;
- `SavingsSummary`;
- `ProviderBadge`;
- `ResourceIdentifier`;
- `CurrencyDisplay`;
- `DataState` (loading/error/empty/no-data composition);
- `DataTable` with responsive/scroll contract;
- `SettingsSection`;
- `SettingsNavigation`;
- `CollectionLauncher`;
- `CollectionWorkspaceHeader`;
- `OpportunityDecisionPanel`;
- `CoverageSummary` for reservation/coverage domains;
- `ForecastStatus` / `EstimatedDataIndicator`;
- `ScopeSelector` for Dashboard/Billing/Flow views.

Product components must consume primitives; pages should compose product components rather than add new visual foundations.

---

## 20. Migration Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Removing legacy globals too early | Broad visual regression | Compatibility aliases + route-by-route removal |
| Changing semantic meaning of existing variables | Theme regressions | New Aven namespace/contract first, aliases second |
| Theme FOUC/hydration regression | Visible startup defect | Preserve pre-hydration theme application with centralized resolver |
| Blind DeepOps/NuvemIQ renames | Auth/config/infra breakage | Separate visible rebrand from technical identifier migration |
| AppShell rewrite affects auth/navigation | Functional regression | Extract/preserve auth/nav/persistence behavior; shell tests |
| Chart redesign before chart contract | Duplicate/inconsistent work | Execute chart foundation before Dashboard/Billing migration |
| Large monolithic pages | High review/QA blast radius | Extract product components before/while visually migrating route |
| Page-specific breakpoints | Responsive regressions | Canonical breakpoints + required viewport QA matrix |
| `!important`/DOM-order selectors | Hidden cascade failures | Remove only after owning component migrated |
| Font swap changes metrics | Layout shifts/truncation | Load fonts centrally and verify tables/cards at target widths |

---

## 21. Recommended Migration Order

The planned order is broadly correct through 24.9, but data visualization has an earlier dependency than originally scheduled.

Recommended execution:

```text
24.1 — UI audit (this task)
24.2 — Aven design tokens + semantic token architecture
24.3 — Theme engine Light / Dark / System
24.4 — Typography, spacing, radius, shadows, motion/focus and iconography
24.5 — Aven UI primitives
24.6 — Product components
24.7 — Application Shell + Sidebar + Topbar
24.8 — Technical rebrand DeepOps → Aven
24.9 — Login Aven
24.18A — Data Visualization foundation (chart semantic tokens, axes/grid/tooltip/legend/status contracts)
24.10 — Dashboard Aven (golden reference)
24.11 — Billing Aven
24.12 — Reservations Aven
24.13 — Inventory Aven
24.14 — Recommendations/Opportunities Aven
24.15 — Reports/Collections Aven
24.16 — Settings Aven
24.17 — Flow/Ledger/secondary pages
24.18B — Data Visualization consistency completion, if any residual work remains
24.19 — Responsive/UI consistency pass
24.20 — Visual QA + legacy design removal
```

If task numbering must remain unchanged, execute the foundation slice of 24.18 as a dependency of 24.10/24.11 and retain 24.18 for final consolidation. This avoids designing Billing/Dashboard charts twice.

---

## 22. Dependencies for Task 24.2

Task 24.2 must consume:

### Existing primitive colors

- legacy root palette from `globals.css`;
- transitional light/dark values from `ui-system.css`;
- canonical Aven palette from `docs/brand/aven/palette/aven_design_tokens.json` and `aven-brand.css`.

### Required semantic token categories

- canvas/background/surface/overlay;
- text hierarchy/inverse/brand;
- borders/focus;
- actions and interactive states;
- success/warning/danger/info/neutral statuses;
- charts/data states;
- typography;
- spacing;
- radius;
- shadows/elevation;
- opacity;
- motion/transitions;
- z-index/layers;
- control dimensions.

### Existing theme hooks

- `data-theme-preference`;
- `data-theme`;
- `style.colorScheme`;
- `prefers-color-scheme` listener;
- localStorage preference;
- storage/custom-event synchronization.

### Existing CSS variables / compatibility requirements

Legacy aliases currently consumed by pages include concepts such as:

- `--bg`, `--text`, `--surface`, `--surface-2`, `--surface-3`;
- `--muted`, `--muted-2`;
- `--border`, `--border-strong`;
- `--accent`, `--accent-2`, `--blue`, `--violet`;
- `--warning`, `--danger`;
- `--radius`, `--radius-sm/md/lg`;
- `--shadow`;
- chart variables;
- sidebar width variables.

These should be mapped to temporary aliases, not become the public Aven token API.

### High-risk components

- `AppShell`;
- `ExecutiveDashboard`;
- Billing chart/filter/table stack;
- RDS reservation page;
- `CollectionWorkspace`;
- Opportunities workspace/detail/dialog stack;
- Flow visualization/table layout;
- Settings accounts/users/audit pages.

### High-risk pages

- `/`;
- `/billing`;
- `/rds/reservations`;
- `/opportunities`;
- `/collections/[collectionId]`;
- `/flow`;
- `/finops/ledger`;
- `/settings/accounts`;
- `/settings/users`;
- `/settings/audit`.

---

## 23. Definition of Ready for Task 24.2

**Is Task 24.2 ready to start? YES.**

Required inputs are available:

- canonical Aven brand assets/tokens are versioned in `docs/brand/aven/`;
- current primitive and transitional colors are identified;
- current CSS variable compatibility surface is identified;
- current light/dark/system theme hooks are understood;
- high-risk components/pages are known;
- token categories required by current UI patterns are known;
- the migration must retain compatibility until route migrations remove legacy consumption;
- chart semantics must be included early enough to support Dashboard/Billing.

### Definition of Ready checklist

- [x] Aven brand source is canonical and versioned.
- [x] Current styling layers are mapped.
- [x] Theme persistence and application flow are mapped.
- [x] Current shared components are classified.
- [x] 31 routes are catalogued.
- [x] Hardcode categories are identified.
- [x] Current color/type/spacing/radius patterns are inventoried.
- [x] Data visualization architecture is inventoried.
- [x] Responsive and accessibility risks are recorded.
- [x] Legacy branding categories are separated by rename risk.
- [x] Visual technical debt is prioritized P0–P3.
- [x] Migration order/dependencies are explicit.

---

## Appendix A — Dashboard as Golden Reference

The Dashboard is suitable as the future visual golden reference because it already exercises a broad cross-section of the product system:

- `PageHeader` and actions;
- scope/provider/account controls;
- freshness/data-status messaging;
- KPI cards;
- savings/currency formatting;
- severity/status representations;
- provider/account/service/rule distributions;
- links and navigation affordances;
- loading skeletons;
- empty state;
- error state/retry;
- responsive grids;
- operational insights.

Before 24.10, primitives and product components should already be stable enough that the Dashboard composes them rather than inventing page-only patterns. Once approved, its typography density, surfaces, card hierarchy, controls, states and visualization treatment become the reference for subsequent routes.

---

## Appendix B — Application Shell Audit

`components/app-shell.tsx` currently owns:

- public/private route detection;
- `/auth/me` session validation;
- session invalidation handling;
- navigation items/icons;
- active-route detection;
- desktop sidebar and collapse persistence;
- mobile overlay/topbar state;
- current DeepOps logo/brand markup;
- theme synchronization listener;
- user email display;
- logout action;
- skip link/main-content structure.

Recommended 24.7 boundary:

- preserve/extract session/auth logic;
- preserve route definitions and active-route semantics unless product requirements change;
- preserve accessible main/skip-link behavior;
- preserve sidebar preference behavior through a compatibility-aware preference API;
- rebuild visual sidebar/topbar/shell on Aven primitives/tokens;
- remove theme mutation responsibility from the shell once 24.3 centralizes it.

---

## Appendix C — Validation Contract

No runtime/visual code is intentionally changed by Task 24.1. The repository CI already executes the required frontend validation on pull requests:

```bash
cd frontend
npm ci
npm test
npm run build
```

The final PR must be considered complete only when the frontend CI job passes. Backend/security CI are expected to remain unaffected because the task adds audit documentation only.
