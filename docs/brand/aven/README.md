# Aven — Official Brand Source

This directory is the canonical source of truth for Aven visual identity and for the product rebrand from DeepOps to Aven.

Before implementing any Task 24.x that changes UI, branding, layout, components, charts, navigation, authentication screens, metadata, favicon, or other visual behavior, read:

1. `docs/brand/aven/README.md`
2. `docs/brand/aven/AVEN_BRAND_GUIDE.txt`
3. `docs/brand/aven/AVEN_DESIGN_TOKENS.md`
4. `docs/brand/aven/AVEN_THEME_ENGINE.md`
5. `docs/brand/aven/AVEN_FOUNDATIONS.md`
6. `docs/brand/aven/AVEN_UI_PRIMITIVES.md`
7. `docs/brand/aven/AVEN_PRODUCT_COMPONENTS.md`
8. `docs/brand/aven/AVEN_APPLICATION_SHELL.md`
9. `docs/brand/aven/AVEN_TECHNICAL_REBRAND.md`
10. `docs/brand/aven/AVEN_LOGIN_EXPERIENCE.md`
11. `docs/brand/aven/AVEN_DASHBOARD.md`
12. `docs/brand/aven/AVEN_BILLING.md`
13. `docs/brand/aven/AVEN_RESERVATIONS.md`
14. `docs/brand/aven/AVEN_INVENTORY.md`
15. `docs/brand/aven/AVEN_RECOMMENDATIONS.md`
16. the applicable assets and visual references under this directory

## Brand direction

- Product name: **Aven**
- Official signature: **Clarity. Flow. Control.**
- Core attributes: **trust** and **control**
- Brand principle: **Complexity underneath. Clarity above.**
- Product direction: premium, technological, secure, controlled, minimal, elegant

The approved visual references in Brand Kit v1 are the golden references for the product redesign, especially the Light and Dark dashboard references.

## Aven Design System foundation

Tasks 24.2–24.14 establish the official token, theme-runtime, visual-foundation, UI primitive, Product Component, persistent Application Shell, technical rebrand, Login Experience, Golden Reference, analytical, operational, inventory and recommendation decision-support architecture:

- `AVEN_DESIGN_TOKENS.md` — token layers, semantic contract, source of truth and migration policy;
- `AVEN_THEME_ENGINE.md` — Light/Dark/System preference, runtime resolution, bootstrap, persistence and `useTheme()` API;
- `AVEN_FOUNDATIONS.md` — typography, spacing, radius, elevation, iconography, density, focus/hit-target and primitive usage contract;
- `AVEN_UI_PRIMITIVES.md` — official generic component APIs, accessibility, hardcode gate, composition and migration rules;
- `AVEN_PRODUCT_COMPONENTS.md` — reusable FinOps/product composition APIs and page-migration contract;
- `AVEN_APPLICATION_SHELL.md` — authenticated shell hierarchy, Sidebar, Topbar, shared navigation, responsive/mobile behavior, scroll model and legacy compatibility;
- `AVEN_TECHNICAL_REBRAND.md` — public identity, runtime assets, metadata, legacy classification/compatibility, brand lint and raster status;
- `AVEN_LOGIN_EXPERIENCE.md` — public Login composition, auth preservation, MFA, responsive/theme behavior and Login-specific gates;
- `AVEN_DASHBOARD.md` — **Aven Page Composition Golden Reference** for authenticated operational pages;
- `AVEN_BILLING.md` — **High-density analytical reference** for financial filters, metrics, stacked charts, tables and query-gated pages;
- `AVEN_RESERVATIONS.md` — **Operational reservations reference** for coverage, utilization, expirations, RDS opportunity semantics and backend-owned matching;
- `AVEN_INVENTORY.md` — **Cloud resource exploration reference** for persisted inventory, technical identifiers, provider context and dense tables;
- `AVEN_RECOMMENDATIONS.md` — **FinOps decision-support reference** for optimization opportunities, potential savings, impact, confidence and action-oriented workflows;
- `aven-semantic-tokens.json` — tooling-oriented token-name index;
- `frontend/app/styles/tokens/` — canonical runtime CSS Custom Properties;
- `frontend/lib/brand.ts` — canonical public product identity/runtime asset map;
- `frontend/lib/iconography.ts` — token-backed React geometry API for `lucide-react`;
- `frontend/components/ui/` — canonical Aven UI primitive implementation;
- `frontend/components/aven/` — canonical Aven Product Component implementation;
- `frontend/components/brand/` — runtime brand/logo abstraction;
- `frontend/components/app-shell/` — canonical persistent authenticated shell implementation;
- `frontend/components/auth/` — reusable Aven authentication-layout composition;
- `frontend/app/dev/ui/` — technical preview using the real Theme Engine.

The product pipeline is:

```text
Aven Brand
↓
Design Tokens
↓
Theme Engine
↓
Visual Foundations
↓
Aven UI Primitives
↓
Aven Product Components
↓
Aven Application Shell
↓
Technical Rebrand
↓
Aven Login Experience
↓
Aven Page Composition Golden Reference
↓
Aven High-density Analytical Reference
↓
Aven Reservations Operational Reference
↓
Aven Inventory Resource Reference
↓
Aven Recommendations Decision-support Reference
↓
Feature Experiences
```

The runtime token contract remains:

```text
Component
↓
Semantic / Foundation / Component Token
↓
Theme Mapping
↓
Primitive Token
```

New Aven UI should use semantic tokens such as `--surface-primary`, `--text-primary` and `--action-primary`, plus foundation roles for typography/spacing/radius/elevation/iconography. Components should not implement independent Light/Dark variants when semantic tokens already express the visual role.

## Aven Technical Rebrand

Task 24.8 makes Aven the public runtime identity without renaming technical contracts purely for aesthetics. `frontend/lib/brand.ts` is the public-name/asset source of truth, `BrandLogo` centralizes runtime logo behavior, root metadata and auth surfaces use Aven, and `npm run lint:brand` rejects unexplained DeepOps/NuvemIQ runtime references.

Legacy storage keys, environment variables, API paths/headers and infrastructure identifiers remain only when compatibility requires them and are documented in `AVEN_TECHNICAL_REBRAND.md` plus the brand-lint allowlist.

Official raster wordmarks/favicons/app icons remain blocked until the Brand Kit raster masters listed in `ASSET_INVENTORY.md` are uploaded through a binary-safe path. They must not be reconstructed from SVG fallbacks or screenshots.

## Aven Application Shell

Task 24.7 makes Aven visible continuously across authenticated routes without redesigning each feature page. Task 24.8 centralizes the shell's brand source while preserving authentication, responsive navigation, Theme Engine and storage compatibility.

The shell is intentionally split into:

```text
authentication/session gate
↓
ApplicationShell
├── Sidebar
├── Topbar
├── shared navigation configuration
├── mobile Drawer
└── main page scroll/content frame
```

## Aven Login Experience

Task 24.9 replaces the legacy Login visual layer with a tokenized Aven authentication experience while preserving the existing `/auth/login`, MFA challenge, enrollment redirect, password-reset link and session behavior.

The Login composition is intentionally layered:

```text
Login Page
↓
AuthLayout
↓
Aven UI Primitives
↓
Tokens / Theme Engine
```

`frontend/components/auth/` owns only institutional/auth layout composition. Authentication logic remains in the page/service/session layers. The Login uses official `Card`, `Input`, `Button`, `IconButton` and `Alert` primitives and is included in both the normal lint scope and the Aven hardcode gate.

## Aven Dashboard — Page Composition Golden Reference

Task 24.10 migrates the authenticated Visão Geral to the Aven Design System and establishes `AVEN_DASHBOARD.md` as the official **Page Composition Golden Reference**.

Future operational pages should reuse its composition rules for:

```text
PageHeader placement
page vertical rhythm
FilterBar layout
metric-grid behavior
Section hierarchy
ChartCard composition
loading / empty / error treatment
responsive stacking
Light / Dark balance
```

The Dashboard reference is intentionally based on real product contracts. It does not fabricate cost evolution, reservation coverage, resource counts or other metrics that are absent from `/dashboard/summary`. Page-specific domain content remains owned by each feature.

## Aven Billing — High-density Analytical Reference

Task 24.11 migrates Billing / Uso e custos and establishes `AVEN_BILLING.md` as the official reference for dense analytical experiences.

Billing extends the Dashboard composition rules with:

```text
explicit account query gating
dense FilterBar composition
DateRangePicker
financial MetricCard hierarchy
stacked cost visualization
actual / estimated / forecast semantics
currency-safe presentation
chart + precision-table composition
responsive table containment
```

The critical Billing contract is `[] accounts != all accounts`: no account selection means no Cost Explorer query. The redesign preserves this data/operational rule while modernizing only presentation and composition.

## Aven Reservations — Operational Reservations Reference

Task 24.12 migrates `/rds/reservations` and establishes `AVEN_RESERVATIONS.md` as the operational reference for pages that combine KPIs, statuses, technical tables, critical dates and recommendations.

Reservations preserves backend ownership of coverage, utilization, the 30-day expiration rule and RDS matching. It does not invent savings, currencies, recommendation priority or provider support. The official Aven page, filter, metric, table, percentage, status and resource-identifier contracts are reused while lazy fetching remains intact.

## Aven Inventory — Cloud Resource Exploration Reference

Task 24.13 migrates `/inventory` and establishes `AVEN_INVENTORY.md` as the reference for dense technical resource exploration over the persisted AWS/OCI inventory foundation.

Inventory keeps provider discovery and persistence out of the page, preserves server-side filters/sorting/pagination, uses `ResourceIdentifier` and `ProviderBadge` for technical context, and keeps resource presence independent from Findings/Opportunities semantics.

## Aven Recommendations — FinOps Decision-support Reference

Task 24.14 migrates `/opportunities`, its operational decision/archive dialogs and its detail drawer. `AVEN_RECOMMENDATIONS.md` is the reference for pages centered on optimization opportunities, financial impact and action-oriented decision support.

Recommendations preserves the backend recommendation engine, lifecycle actions and query contract. Potential savings remains backend-owned, monthly and currency-specific; mixed currencies are never silently aggregated. Backend severity is presented as impact, backend confidence remains distinct, and no frontend priority/confidence/savings algorithm is introduced.

The page uses `RecommendationCard` for small curated result sets and Table primitives for larger result sets/history, preserving analytical density instead of turning the backlog into a wall of oversized cards.

## Mandatory engineering rule — Task 24.5 onward

> A partir da Task 24.5, nenhum novo componente visual deverá utilizar cores, border radius, spacing ou typography hardcoded.

This includes color/background/border-color, structural spacing/padding/margin/gap, border radius, font family, font size, font weight and line height.

### Forbidden

```css
color: #3B82F6;
border-radius: 12px;
padding: 16px;
font-size: 14px;
```

### Expected

```css
color: var(--action-primary);
border-radius: var(--radius-control);
padding: var(--space-4);
font-size: var(--font-size-md);
```

The enforced gates are:

```bash
cd frontend
npm run lint:brand
npm run lint:design-system
```

The design-system gate protects the official primitive library, Product Component library, brand components, Application Shell, Aven authentication experience, migrated Dashboard, Billing, Reservations, Inventory, Recommendations and `/dev/ui` preview instead of failing on historical page debt scheduled for progressive migration.

## Layer dependency rule

The supported dependency direction is:

```text
Page → Application Shell / Auth Layout / Product Component → UI Primitive → Token
```

The shell and Auth Layout are composition layers, not domain layers. `frontend/components/ui/` may not import `frontend/components/aven/` or feature/login layers. Product Components may know reusable product concepts such as account, provider, environment, cost, savings, resource, status and recommendation, but they may not own feature-specific fetching/routing/business rules. Auth Layout may own brand/form composition but not authentication logic.

## Implementation principles

- Treat this directory as the authoritative brand source. Do not recreate the Aven wordmark using text.
- Prefer approved production assets for the wordmark; the fallback SVG remains an approximation where documented.
- Inter is the UI family and Sora is the display family delivered through the framework-native font loader; neither is the Aven wordmark.
- `lucide-react` is the canonical functional icon library. Aven/provider marks remain separate assets.
- Light and Dark are first-class themes; Dark is not a color inversion and uses surface/border contrast before shadow.
- `system` is a durable user preference that resolves dynamically to Light or Dark.
- Purple is a premium accent, not the default color for every component.
- Semantic success/warning/danger/info states remain recognizable and are not replaced by purple.
- Institutional gradients/glow are atmospheric and controlled, not neon or pervasive.
- Data visualization uses dedicated semantic chart tokens rather than raw brand colors.
- Existing DeepOps UI aliases remain temporary compatibility infrastructure; do not use them in new Aven components.
- New generic interaction patterns consume `frontend/components/ui/`; reusable FinOps/product patterns consume `frontend/components/aven/`.
- Persistent authenticated navigation/chrome consumes `frontend/components/app-shell/`.
- Authentication layout composition consumes `frontend/components/auth/` while auth state/API behavior stays in the existing page/service/session layers.
- Feature pages own APIs, query params, routing, permissions, feature state and business rules.
- Authenticated feature pages use `AVEN_DASHBOARD.md` for page-level composition; dense analytical pages additionally use `AVEN_BILLING.md` where its constraints apply.
- Operational reservation pages use `AVEN_RESERVATIONS.md` for coverage/utilization/expiration/opportunity semantics.
- Resource-exploration pages use `AVEN_INVENTORY.md` for persisted inventory, technical identifiers and provider/resource table semantics.
- Decision-support and optimization pages use `AVEN_RECOMMENDATIONS.md` for savings, impact, confidence, resource context, workflow status and action semantics.

## Repository note

Textual specifications, tokens and vector fallbacks are versioned here so every Task/PR can inspect them without external context. Production raster assets supplied in Aven Brand Kit v1 remain the visual master where the guide says raster output is authoritative.

## Version

Brand Kit: **v1**

Tasks 24.2–24.14 provide the design-system, product-composition, persistent-shell, technical-brand, Login, Golden Reference, analytical, Reservations, Inventory and Recommendations foundations required for Task 24.15 — Aven Reports and the remaining progressive feature-page redesign tasks.
