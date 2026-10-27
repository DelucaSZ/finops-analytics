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
9. the applicable assets and visual references under this directory

## Brand direction

- Product name: **Aven**
- Official signature: **Clarity. Flow. Control.**
- Core attributes: **trust** and **control**
- Brand principle: **Complexity underneath. Clarity above.**
- Product direction: premium, technological, secure, controlled, minimal, elegant

The approved visual references in Brand Kit v1 are the golden references for the product redesign, especially the Light and Dark dashboard references.

## Aven Design System foundation

Tasks 24.2–24.7 establish the official token, theme-runtime, visual-foundation, UI primitive, Product Component and persistent Application Shell architecture:

- `AVEN_DESIGN_TOKENS.md` — token layers, semantic contract, source of truth and migration policy;
- `AVEN_THEME_ENGINE.md` — Light/Dark/System preference, runtime resolution, bootstrap, persistence and `useTheme()` API;
- `AVEN_FOUNDATIONS.md` — typography, spacing, radius, elevation, iconography, density, focus/hit-target and primitive usage contract;
- `AVEN_UI_PRIMITIVES.md` — official generic component APIs, accessibility, hardcode gate, composition and migration rules;
- `AVEN_PRODUCT_COMPONENTS.md` — reusable FinOps/product composition APIs and page-migration contract;
- `AVEN_APPLICATION_SHELL.md` — authenticated shell hierarchy, Sidebar, Topbar, shared navigation, responsive/mobile behavior, scroll model and legacy compatibility;
- `aven-semantic-tokens.json` — tooling-oriented token-name index;
- `frontend/app/styles/tokens/` — canonical runtime CSS Custom Properties;
- `frontend/lib/iconography.ts` — token-backed React geometry API for `lucide-react`;
- `frontend/components/ui/` — canonical Aven UI primitive implementation;
- `frontend/components/aven/` — canonical Aven Product Component implementation;
- `frontend/components/app-shell/` — canonical persistent authenticated shell implementation;
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
Feature Pages
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

## Aven Application Shell

Task 24.7 makes Aven visible continuously across authenticated routes without redesigning each feature page.

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

The Sidebar collapse preference remains independent from theme. The Topbar delegates Light/Dark/System to the existing Theme Engine, mobile navigation consumes the same navigation configuration as desktop, and the fallback wordmark has centralized theme-aware treatment until Task 24.8 replaces final runtime assets.

Task 24.8 may replace global product naming, metadata, favicon, manifest and final runtime brand assets without rebuilding the shell.

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

Shadows and icon geometry should likewise use the shared foundation contracts whenever they represent reusable design decisions.

Task 24.7 enforces this with:

```bash
cd frontend
npm run lint:design-system
```

The gate protects the official primitive library, Product Component library, Application Shell and `/dev/ui` technical preview instead of failing on historical page debt that is scheduled for progressive migration.

## Layer dependency rule

The supported dependency direction is:

```text
Page → Application Shell / Product Component → UI Primitive → Token
```

The shell is persistent composition, not a domain layer. `frontend/components/ui/` may not import `frontend/components/aven/`. Product Components may know reusable product concepts such as account, provider, environment, cost, savings, resource, status and recommendation, but they may not own feature-specific fetching/routing/business rules.

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
- Feature pages own APIs, query params, routing, permissions, feature state and business rules.

## Repository note

Textual specifications, tokens and vector fallbacks are versioned here so every Task/PR can inspect them without external context. Production raster assets supplied in Aven Brand Kit v1 remain the visual master where the guide says raster output is authoritative.

## Version

Brand Kit: **v1**

Tasks 24.2–24.7 provide the complete design-system, product-composition and persistent-shell foundation required for Task 24.8 — Technical Rebrand DeepOps → Aven and the progressive feature-page redesign tasks.
