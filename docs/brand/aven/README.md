# Aven — Official Brand Source

This directory is the canonical source of truth for Aven visual identity and for the product rebrand from DeepOps to Aven.

Before implementing any Task 24.x that changes UI, branding, layout, components, charts, navigation, authentication screens, metadata, favicon, or other visual behavior, read:

1. `docs/brand/aven/README.md`
2. `docs/brand/aven/AVEN_BRAND_GUIDE.txt`
3. `docs/brand/aven/AVEN_DESIGN_TOKENS.md`
4. the applicable assets and visual references under this directory

## Brand direction

- Product name: **Aven**
- Official signature: **Clarity. Flow. Control.**
- Core attributes: **trust** and **control**
- Brand principle: **Complexity underneath. Clarity above.**
- Product direction: premium, technological, secure, controlled, minimal, elegant

The approved visual references in the Brand Kit v1 are the golden references for the product redesign, especially the light and dark dashboard references.

## Aven Design System foundation

Task 24.2 establishes the official design-token architecture documented in:

- `docs/brand/aven/AVEN_DESIGN_TOKENS.md` — architecture, usage rules, theme mapping and migration policy;
- `docs/brand/aven/aven-semantic-tokens.json` — tooling-oriented token-name index;
- `frontend/app/styles/tokens/` — canonical product-token source and runtime CSS Custom Properties.

The runtime contract follows:

```text
Component
↓
Semantic / Component Token
↓
Theme Mapping
↓
Primitive Token
```

New Aven UI should use semantic tokens such as `--surface-primary`, `--text-primary` and `--action-primary`, not raw brand colors.

## Mandatory engineering rule — Task 24.5 onward

Starting with **Task 24.5**, no new visual component may hardcode:

- colors;
- border radius;
- spacing;
- font family;
- font size;
- font weight;
- line height.

All such values must originate from the Aven design system and its semantic tokens.

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
font-size: var(--font-size-sm);
```

This rule applies to all new visual components and to components migrated into the Aven design system from Task 24.5 onward.

## Implementation principles

- Treat this directory as the authoritative brand source. Do not recreate the Aven wordmark using text.
- Prefer the approved production PNGs for the wordmark. SVG wordmark assets are fallback approximations, as specified in the guide.
- Light and dark modes must be designed as first-class themes; dark mode must not be a simple color inversion.
- Purple is a premium accent, not the default color for every component.
- Semantic states such as success, warning, error and information must remain recognizable.
- Institutional gradients should be atmospheric and controlled, not neon or pervasive.
- Data visualization must use dedicated semantic chart tokens rather than raw brand colors.
- Existing DeepOps UI aliases remain temporary compatibility infrastructure; do not use them in new Aven components.

## Repository note

The textual specifications, tokens and vector fallbacks are stored directly under this directory so every Task/PR can inspect them without external context. The production raster pack supplied in Aven Brand Kit v1 remains the visual master for PNG wordmarks, favicons and 4K references.

## Version

Brand Kit: **v1**

The identity and product-token foundation are now versioned. Tasks 24.3 and 24.4 can evolve theme resolution and refine typography/spacing/radius/shadows without rebuilding the token architecture.
