# Aven Design Tokens

Task 24.2 established the official Aven product-token architecture. Task 24.4 refines the visual foundation values while preserving that architecture. Detailed visual application rules now live in [`AVEN_FOUNDATIONS.md`](./AVEN_FOUNDATIONS.md); this document remains the architectural contract.

## Philosophy

Aven follows **“Complexity underneath. Clarity above.”** Product code expresses visual intent instead of raw implementation values.

```text
Component
  ↓
Semantic / Foundation / Component Token
  ↓
Theme Mapping
  ↓
Primitive Token
```

Raw brand colors and scales belong in the token-definition layer. New product components should not know whether a semantic action currently resolves to a particular hex value, shadow alpha or font file.

## Architecture

Runtime tokens live under:

```text
frontend/app/styles/tokens/
  primitives.css
  foundations.css
  semantic-light.css
  semantic-dark.css
  status.css
  visualization.css
  components.css
  legacy.css
  index.css
```

Layers:

1. **Primitive tokens** — raw brand anchors and reusable scales for spacing, radius, typography, icon geometry, focus/hit-target geometry and shared motion.
2. **Foundation roles** — semantic typography roles, operational density and cross-cutting visual guidance derived from primitives.
3. **Theme semantic tokens** — Light/Dark background, surfaces, text, borders, actions, focus, overlays, shadows and elevation mapping.
4. **Status tokens** — success/warning/danger/info/neutral families.
5. **Visualization tokens** — categorical chart series and chart structure/state semantics.
6. **Component tokens** — a deliberately small reusable composition layer derived from semantic/foundation roles.
7. **Legacy compatibility** — temporary aliases needed while the existing product migrates incrementally.

`frontend/app/styles/tokens/index.css` is the single runtime entrypoint.

## Source of Truth

Canonical runtime values are CSS Custom Properties in:

```text
frontend/app/styles/tokens/*.css
```

`docs/brand/aven/palette/aven_design_tokens.json` remains Brand Kit input, not a competing runtime store.

`docs/brand/aven/aven-semantic-tokens.json` indexes token names for tooling without duplicating raw values.

`frontend/lib/iconography.ts` is a token-backed React adapter for Lucide geometry; it references CSS variables rather than creating a second numeric icon scale.

## Primitive Brand Anchors

Brand Kit anchors remain unchanged:

| Brand value | Primitive |
|---|---|
| Primary Blue `#3B82F6` | `--aven-color-blue-500` |
| Primary Purple `#8B5CF6` | `--aven-color-violet-500` |
| Accent Indigo `#6366F1` | `--aven-color-indigo-500` |
| Light Blue `#60A5FA` | `--aven-color-blue-400` |
| Soft Blue `#EAF4FF` | `--aven-color-soft-blue` |
| Lavender `#F3EEFF` | `--aven-color-lavender` |
| Soft Violet `#EDE9FE` | `--aven-color-soft-violet` |
| Soft Cyan `#ECFDF5` | `--aven-color-soft-cyan` |
| Near Black `#0A0A0F` | `--aven-color-neutral-950` |
| Dark Slate `#1F2937` | `--aven-color-neutral-800` |
| Slate `#6B7280` | `--aven-color-neutral-500` |
| Light Gray `#E5E7EB` | `--aven-color-neutral-200` |
| White `#FFFFFF` | `--aven-color-neutral-0` |

Intermediate ramps and semantic status ramps are supporting primitives; they do not replace the official brand-primary colors.

## Semantic Interface

### Background and surfaces

```css
--background-primary
--background-secondary
--background-tertiary
--background-inverse

--surface-primary
--surface-secondary
--surface-tertiary
--surface-elevated
--surface-overlay
--surface-hover
--surface-selected
--surface-disabled
--surface-inverse
```

### Text and borders

```css
--text-primary
--text-secondary
--text-muted
--text-disabled
--text-inverse
--text-link
--text-link-hover
--text-brand

--border-subtle
--border-default
--border-strong
--border-interactive
--border-focus
--border-disabled
```

### Actions and interaction

```css
--action-primary
--action-primary-hover
--action-primary-active
--action-primary-text
--action-secondary
--action-secondary-hover
--action-secondary-active
--action-secondary-text
--action-ghost-hover
--action-ghost-active
--action-disabled
--action-disabled-text

--focus-ring
--focus-ring-offset
--state-hover-overlay
--state-active-overlay
--state-selected-bg
--state-selected-border
--overlay-backdrop
--overlay-backdrop-strong
```

Primary actions use the blue/indigo family. Purple remains a selective premium/brand accent.

## Theme Mapping

Light is selected by:

```css
:root,
html[data-theme="light"]
```

Dark is selected by:

```css
html[data-theme="dark"]
```

The Task 24.3 Theme Engine owns preference resolution and root attributes. Components should not branch on `resolvedTheme` for normal CSS colors when semantic tokens can express the role.

The Light and Dark shadow/elevation APIs have the same names but intentionally different values. Dark prioritizes surface + border contrast and starts base cards at zero shadow.

## Visual Foundations

The complete scale, usage matrix and constraints for typography, spacing, radius, elevation and iconography are documented in [`AVEN_FOUNDATIONS.md`](./AVEN_FOUNDATIONS.md).

Key public hooks include:

### Typography

```css
--font-family-ui
--font-family-display
--font-family-mono
--font-weight-regular
--font-weight-medium
--font-weight-semibold
--font-weight-bold
--font-size-xs ... --font-size-5xl
--line-height-none
--line-height-tight
--line-height-snug
--line-height-normal
--line-height-relaxed
--letter-spacing-tight
--letter-spacing-normal
--letter-spacing-wide
```

Semantic text roles use the `--type-*` family in `foundations.css`, including display, heading, body, label, caption, button, KPI, table and code/resource roles.

Inter is the UI family; Sora is the display family. Both are loaded through `next/font/google` with weights 400/500/600/700. The Aven wordmark remains an official graphic asset and must not be recreated using the display font.

### Spacing

```css
--space-0
--space-1
--space-2
--space-3
--space-4
--space-5
--space-6
--space-8
--space-10
--space-12
--space-16
```

No page-specific spacing namespaces are permitted unless a genuine reusable product semantic emerges.

### Radius

```css
--radius-none
--radius-xs
--radius-sm
--radius-md
--radius-control
--radius-card
--radius-dialog
--radius-pill
--radius-full
```

New components should prefer semantic geometry roles (`control`, `card`, `dialog`, `pill`, `full`) instead of choosing arbitrary intermediates.

### Shadows and elevation

```css
--shadow-none
--shadow-xs
--shadow-sm
--shadow-md
--shadow-lg
--shadow-xl

--elevation-0-surface / border / shadow
...
--elevation-4-surface / border / shadow
```

Elevation is always a surface/border/shadow composition. Glow is not standard card elevation.

### Iconography

```css
--icon-size-xs
--icon-size-sm
--icon-size-md
--icon-size-lg
--icon-size-xl
--icon-size-2xl
--icon-size-3xl
--icon-stroke-default
--icon-stroke-strong
```

`lucide-react` is the canonical functional icon library. Brand/provider assets remain separate.

## Status Tokens

Every status exposes base/background/border/text roles:

```css
--status-success*
--status-warning*
--status-danger*
--status-info*
--status-neutral*
```

Semantic status must not be replaced by brand purple. Status UI should not rely on color alone; icon and/or label should accompany state where appropriate.

## Data Visualization

Categorical series:

```css
--chart-series-1 ... --chart-series-6
```

Structure/state:

```css
--chart-grid
--chart-axis
--chart-label
--chart-tooltip-bg
--chart-tooltip-text
--chart-reference-line
--chart-forecast
--chart-estimated
--chart-comparison
--chart-baseline
```

Chart series are categorical—not provider identities. Do not infer AWS = blue or OCI = violet without an explicit product semantic.

## Component Tokens

The reusable component-composition layer includes structural roles such as:

```css
--card-background
--card-border
--card-radius
--card-padding
--card-shadow
--control-background
--control-border
--control-radius
--control-padding-inline-*
--dialog-background
--dialog-border
--dialog-radius
--dialog-padding
--dialog-shadow
--popover-*
--icon-button-*
--form-field-gap
--table-cell-padding-*
```

These derive from the shared token/foundation system. Page-specific component tokens remain prohibited.

## Legacy Compatibility

Two compatibility domains remain deliberately separate:

1. `frontend/app/styles/tokens/legacy.css` keeps Brand Kit v1 alias names such as `--aven-blue`, `--aven-radius-card` and `--aven-font-ui`.
2. `frontend/app/ui-system.css` and `legacy-theme-compat.css` continue to own existing DeepOps application variables during incremental migration.

Do not use transitional names such as `--bg`, `--accent`, `--surface-2`, `--radius` or the legacy application palette in new Aven primitives.

Task 24.4 does not mass-replace existing hardcodes. Later component/page tasks remove legacy consumption route by route.

## Usage Rules

Correct:

```css
.card {
  background: var(--card-background);
  color: var(--text-primary);
  border: 1px solid var(--card-border);
  border-radius: var(--card-radius);
  padding: var(--card-padding);
  box-shadow: var(--card-shadow);
}
```

Incorrect:

```css
.card {
  background: #ffffff;
  color: #1f2937;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 24px;
  box-shadow: 0 8px 24px rgba(0,0,0,.1);
}
```

## Forbidden Patterns

Starting with Task 24.5, new/migrated visual components must not introduce hardcoded structural:

- colors;
- spacing/padding/margin/gap;
- border radius;
- font family;
- font size;
- font weight;
- line height.

Shadows and functional icon geometry should use the shared API whenever they represent reusable visual decisions.

Token abuse is also forbidden. Do not create variables such as `--billing-label-top-2px` simply to hide a local literal.

## Task 24.5 Readiness

The token architecture, Theme Engine and Visual Foundations together now provide a complete input contract for Aven UI Primitives.

**Is Task 24.5 ready to start? YES.**
