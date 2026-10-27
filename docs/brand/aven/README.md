# Aven — Official Brand Source

This directory is the canonical source of truth for Aven visual identity and for the product rebrand from DeepOps to Aven.

Before implementing any Task 24.x that changes UI, branding, layout, components, charts, navigation, authentication screens, metadata, favicon, or other visual behavior, read:

1. `docs/brand/aven/README.md`
2. `docs/brand/aven/AVEN_BRAND_GUIDE.txt`
3. `docs/brand/aven/AVEN_DESIGN_TOKENS.md`
4. `docs/brand/aven/AVEN_THEME_ENGINE.md`
5. `docs/brand/aven/AVEN_FOUNDATIONS.md`
6. the applicable assets and visual references under this directory

## Brand direction

- Product name: **Aven**
- Official signature: **Clarity. Flow. Control.**
- Core attributes: **trust** and **control**
- Brand principle: **Complexity underneath. Clarity above.**
- Product direction: premium, technological, secure, controlled, minimal, elegant

The approved visual references in Brand Kit v1 are the golden references for the product redesign, especially the Light and Dark dashboard references.

## Aven Design System foundation

Tasks 24.2–24.4 establish the official token, theme-runtime and visual-foundation architecture:

- `AVEN_DESIGN_TOKENS.md` — token layers, semantic contract, source of truth and migration policy;
- `AVEN_THEME_ENGINE.md` — Light/Dark/System preference, runtime resolution, bootstrap, persistence and `useTheme()` API;
- `AVEN_FOUNDATIONS.md` — typography, spacing, radius, elevation, iconography, density, focus/hit-target and Task 24.5 usage contract;
- `aven-semantic-tokens.json` — tooling-oriented token-name index;
- `frontend/app/styles/tokens/` — canonical runtime CSS Custom Properties;
- `frontend/lib/iconography.ts` — token-backed React geometry API for `lucide-react`.

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
UI Primitives
↓
Product Components
↓
Pages
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

## Repository note

Textual specifications, tokens and vector fallbacks are versioned here so every Task/PR can inspect them without external context. Production raster assets supplied in Aven Brand Kit v1 remain the visual master where the guide says raster output is authoritative.

## Version

Brand Kit: **v1**

Tasks 24.2–24.4 now provide the complete foundation required for Task 24.5 — Aven UI Primitives.
