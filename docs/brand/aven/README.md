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
16. `docs/brand/aven/AVEN_SETTINGS.md`
17. `docs/brand/aven/AVEN_FLOW_AND_SECONDARY_PAGES.md`
18. `docs/brand/aven/AVEN_DATA_VISUALIZATION_SYSTEM.md`
19. `docs/brand/aven/AVEN_RESPONSIVE_AND_UI_CONSISTENCY.md`
20. `docs/brand/aven/AVEN_VISUAL_QA_AND_LEGACY_CLEANUP.md`
21. the applicable assets and visual references under this directory

## Brand direction

- Product name: **Aven**
- Official signature: **Clarity. Flow. Control.**
- Core attributes: **trust** and **control**
- Brand principle: **Complexity underneath. Clarity above.**
- Product direction: premium, technological, secure, controlled, minimal, elegant

The approved visual references in Brand Kit v1 are the golden references for the product redesign, especially the Light and Dark dashboard references.

## Aven Design System foundation

Tasks 24.2–24.19 establish and close the official token, theme-runtime, visual-foundation, UI primitive, Product Component, persistent Application Shell, technical rebrand, Login Experience, Golden Reference, analytical, operational, inventory, recommendation, Settings, Flow/secondary-page, visualization, responsive-consistency and final QA architecture:

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
- `AVEN_SETTINGS.md` — **Settings migration reference** for the Functional Foundation Gate, route-based configuration navigation, forms, persistence, permissions, secrets and no-invented-feature rule;
- `AVEN_FLOW_AND_SECONDARY_PAGES.md` — **Flow and existing-secondary-page reference** for functional-foundation auditing, preserved ledger/collection contracts, route classification, test baseline/integrity and scoped legacy migration;
- `AVEN_DATA_VISUALIZATION_SYSTEM.md` — **Visualization-system reference** for chart semantic roles, categorical series, accessible chart behavior and Light/Dark chart tokens;
- `AVEN_RESPONSIVE_AND_UI_CONSISTENCY.md` — **Cross-page responsive/consistency reference** for shell/page rhythm, shared breakpoints, tables, overlays, scroll ownership, accessibility and viewport audit rules;
- `AVEN_VISUAL_QA_AND_LEGACY_CLEANUP.md` — **Phase 24 closure reference** for route coverage, Light/Dark/System QA, regression gates, brand/hardcode audit, proof-before-delete legacy cleanup and preserved compatibility contracts;
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
Aven Settings Functional Foundation Reference
↓
Aven Flow & Existing Secondary Pages Reference
↓
Aven Data Visualization System
↓
Aven Responsive & UI Consistency
↓
Aven Visual QA & Legacy Cleanup
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

Billing extends the Dashboard composition rules with explicit account query gating, dense filters, temporal controls, financial metrics, stacked cost visualization, exact actual/estimated/forecast semantics and responsive precision tables.

The critical Billing contract is `[] accounts != all accounts`: no account selection means no Cost Explorer query. The redesign preserves this data/operational rule while modernizing only presentation and composition.

## Aven Reservations — Operational Reservations Reference

Task 24.12 migrates `/rds/reservations` and establishes `AVEN_RESERVATIONS.md` as the operational reference for pages that combine KPIs, statuses, technical tables, critical dates and recommendations.

Reservations preserves backend ownership of coverage, utilization, the 30-day expiration rule and RDS matching. It does not invent savings, currencies, recommendation priority or provider support.

## Aven Inventory — Cloud Resource Exploration Reference

Task 24.13 migrates `/inventory` and establishes `AVEN_INVENTORY.md` as the reference for dense technical resource exploration over the persisted AWS/OCI inventory foundation.

Inventory keeps provider discovery and persistence out of the page, preserves server-side filters/sorting/pagination, uses `ResourceIdentifier` and `ProviderBadge` for technical context, and keeps resource presence independent from Findings/Opportunities semantics.

## Aven Recommendations — FinOps Decision-support Reference

Task 24.14 migrates `/opportunities`, its operational decision/archive dialogs and its detail drawer. `AVEN_RECOMMENDATIONS.md` is the reference for pages centered on optimization opportunities, financial impact and action-oriented decision support.

Recommendations preserves the backend recommendation engine, lifecycle actions and query contract. Potential savings remains backend-owned, monthly and currency-specific; mixed currencies are never silently aggregated. Backend severity is presented as impact, backend confidence remains distinct, and no frontend priority/confidence/savings algorithm is introduced.

## Aven Settings — Functional Foundation Reference

Task 24.15 migrates the existing `/settings/*` route family while enforcing a mandatory Functional Foundation Gate. `AVEN_SETTINGS.md` records the audited existing Settings inventory, permissions, persistence, sensitive-data handling, loading/error/success behavior and the explicit list of features not created because no functional foundation exists.

Settings retains its route-based information architecture and real deep links. The common navigation uses official Aven Tabs, while migrated security/session/billing-profile surfaces use the shared Aven form/table/feedback primitives. The existing Theme Engine remains the only Light/Dark/System preference controller.

The governing rule for Settings and subsequent secondary-page migration is:

```text
Existing functionality
↓
Aven visual migration
```

No visual concept is allowed to justify a new backend API, database model, mock, credential, integration or dead CTA.

## Aven Flow & Existing Secondary Pages

Task 24.16 migrates the existing `/flow` experience and the audited existing secondary surfaces `/collections`, `/collections/[collectionId]`, `/collections/[collectionId]/compare`, and `/scans`. `AVEN_FLOW_AND_SECONDARY_PAGES.md` records the route inventory, Functional Foundation Gate, preserved Flow/Collections/Scans contracts, loading/error/empty behavior, test baseline, test-isolation rules and Task 24.17 readiness.

Flow continues to represent the existing FinOps ledger and does not become a new workflow engine. Existing summary/timeseries/breakdown/entry queries, manual ledger movement and reversal mutations remain feature-owned. Collections preserves its URL-state, server-state, polling, retention and comparison contracts. Scans preserves its existing operational refresh and collection navigation.

Legacy aliases `/finops/ledger` and `/security` remain redirects instead of receiving duplicate UI. No nonexistent route or backend capability is created to complete navigation.

## Aven Data Visualization System

Task 24.17 standardizes existing analytical visualizations without introducing new analytics. `AVEN_DATA_VISUALIZATION_SYSTEM.md` defines semantic chart series/structure roles, theme mapping, accessible interaction and the canonical `ChartCard` state-container contract.

## Aven Responsive & UI Consistency

Task 24.18 applies a cross-page responsive and consistency pass without changing product capability. `AVEN_RESPONSIVE_AND_UI_CONSISTENCY.md` defines the shared composition thresholds, 1366×768 baseline, page rhythm, overflow strategy, overlay collision handling, scroll ownership, responsive accessibility expectations, test strategy and cross-page audit matrix.

## Aven Visual QA & Legacy Cleanup

Task 24.19 closes Phase 24 with a router-derived route inventory, final Light/Dark/System and responsive QA, functional-regression gates, public-brand and hardcode scans, accessibility/overlay/scroll checks and proof-before-delete legacy cleanup. `AVEN_VISUAL_QA_AND_LEGACY_CLEANUP.md` is the authoritative closure record and explicitly documents compatibility identifiers and visual migration infrastructure that must remain until a separately planned migration can retire them safely.

The closure rule is deliberately stricter than a textual rename:

```text
zero active legacy visual experience
+
zero visible old branding
+
zero unsafe cleanup
```

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

The design-system gate protects the official primitive library, Product Component library, brand components, Application Shell, Aven authentication experience, migrated Dashboard, Billing, Reservations, Inventory, complete Recommendations and Settings route families, Flow, existing secondary pages and `/dev/ui` preview instead of failing on unrelated historical debt.

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
- Settings and future secondary-page migrations use `AVEN_SETTINGS.md` to enforce the Functional Foundation Gate and prohibit invented capabilities during visual redesign.
- Flow and remaining existing-secondary-page migrations use `AVEN_FLOW_AND_SECONDARY_PAGES.md` to preserve real contracts, route classification, test integrity and scoped legacy cleanup.
- Existing charts use `AVEN_DATA_VISUALIZATION_SYSTEM.md`; responsive/cross-page changes use `AVEN_RESPONSIVE_AND_UI_CONSISTENCY.md`.
- Final route/theme/brand/legacy closure work uses `AVEN_VISUAL_QA_AND_LEGACY_CLEANUP.md` and must preserve technical compatibility contracts unless their removal is independently proven safe.

## Repository note

Textual specifications, tokens and vector fallbacks are versioned here so every Task/PR can inspect them without external context. Production raster assets supplied in Aven Brand Kit v1 remain the visual master where the guide says raster output is authoritative.

## Version

Brand Kit: **v1**

Tasks 24.2–24.19 provide the complete design-system, product-composition, persistent-shell, technical-brand, Login, page, visualization, responsive-consistency and final visual-QA foundations for the Aven Phase 24 transformation. The final closure status is recorded in `AVEN_VISUAL_QA_AND_LEGACY_CLEANUP.md` and is valid only when its CI and browser-evidence gates are green.
