# Aven Design Tokens

Task 24.2 defines the official product-token foundation for Aven. It converts Brand Kit v1 and the Task 24.1 UI audit into a runtime token contract that later UI work can consume without knowing raw color, radius, spacing or typography values.

## Philosophy

Aven follows the brand principle **“Complexity underneath. Clarity above.”** The design-token architecture therefore separates raw visual values from product meaning:

```text
Component
  ↓
Semantic / Component Token
  ↓
Theme Mapping
  ↓
Primitive Token
```

Product code should express intent (`--action-primary`, `--text-secondary`, `--surface-primary`) instead of implementation (`#2563eb`, `16px`, `600`).

The brand direction remains premium, technological, secure, controlled, minimal and elegant. Purple is a selective premium accent; it is not a replacement for every semantic state. Success, warning, danger and information retain recognizable semantics.

## Architecture

Runtime tokens live under:

```text
frontend/app/styles/tokens/
  primitives.css
  semantic-light.css
  semantic-dark.css
  status.css
  visualization.css
  components.css
  legacy.css
  index.css
```

Layers:

1. **Primitive tokens** — raw brand anchors and reusable scales.
2. **Semantic tokens** — visual function resolved per Light/Dark theme.
3. **Status tokens** — success/warning/danger/info/neutral families.
4. **Data visualization tokens** — categorical chart series and chart structure/state semantics.
5. **Component tokens** — a deliberately small set of reusable structural aliases derived from semantic tokens.
6. **Legacy compatibility** — temporary names needed while the existing UI migrates incrementally.

`frontend/app/styles/tokens/index.css` is the single runtime entrypoint.

## Source of Truth

The product token source of truth is:

```text
frontend/app/styles/tokens/*.css
```

CSS Custom Properties are both the canonical product definitions and the runtime interface. This avoids maintaining divergent raw values in CSS, JSON and TypeScript.

`docs/brand/aven/palette/aven_design_tokens.json` remains the **Brand Kit input**, not a second product-token store.

`docs/brand/aven/aven-semantic-tokens.json` is an index for future tooling. It lists token names and ownership but intentionally does **not** duplicate raw values.

## Primitive Tokens

### Brand color anchors

Official Brand Kit anchors are preserved:

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

Intermediate blue/indigo/violet/neutral values are systematic ramps around those anchors. Green, amber, red and cyan ramps are supporting primitives required for semantic states and data visualization; they are not additional brand-primary colors.

### Gradients

```css
--gradient-brand
--gradient-background-light
--gradient-background-dark
```

These preserve the Brand Kit v1 gradients. They are intended for institutional/background/hero moments, not as default card/control backgrounds.

## Semantic Tokens

### Background

```css
--background-primary
--background-secondary
--background-tertiary
--background-inverse
```

### Surfaces

```css
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

### Text

```css
--text-primary
--text-secondary
--text-muted
--text-disabled
--text-inverse
--text-link
--text-link-hover
--text-brand
```

### Borders

```css
--border-subtle
--border-default
--border-strong
--border-interactive
--border-focus
--border-disabled
```

### Actions

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
```

Primary actions use the blue/indigo family. The semantic action color is intentionally not tied to `--aven-color-blue-500`; the current mapping uses a darker blue step where necessary to maintain readable white text.

### Focus

```css
--focus-ring
--focus-ring-offset
```

Focus is a dedicated semantic state and must not depend only on a background change.

### Interactive states

```css
--state-hover-overlay
--state-active-overlay
--state-selected-bg
--state-selected-border
```

These prevent each component from inventing independent hover/active/selected opacities.

### Overlay/backdrop

```css
--overlay-backdrop
--overlay-backdrop-strong
```

Intended for dialogs, drawers, command palettes and other modal surfaces.

## Theme Mapping

### Light

Selector:

```css
:root,
html[data-theme="light"] { ... }
```

Direction:

- white/off-white backgrounds;
- subtle blue tertiary surfaces;
- white primary/elevated cards;
- near-black and dark-slate text hierarchy;
- blue/indigo actions;
- violet only as selective premium/brand accent;
- soft borders and restrained shadow.

### Dark

Selector:

```css
html[data-theme="dark"] { ... }
```

Direction:

- near-black/deep-navy application background;
- dark-neutral surfaces with limited deep-indigo use;
- cool white/gray text;
- blue/indigo/violet accents;
- surface + border differentiation before shadow;
- no pervasive purple, neon glow or gaming aesthetic.

System preference continues to resolve to one of these two selectors through the existing theme engine. Task 24.2 does not rebuild theme persistence/resolution.

## Status Tokens

Every status has base, background, border and text roles:

```css
--status-success
--status-success-bg
--status-success-border
--status-success-text

--status-warning
--status-warning-bg
--status-warning-border
--status-warning-text

--status-danger
--status-danger-bg
--status-danger-border
--status-danger-text

--status-info
--status-info-bg
--status-info-border
--status-info-text

--status-neutral
--status-neutral-bg
--status-neutral-border
--status-neutral-text
```

Status semantics are explicitly independent from brand accent. A successful operation remains green even when Aven brand accents are blue/indigo/violet.

## Interactive States

New components should derive hover, active, selected, disabled and focus behavior from semantic state/action tokens rather than inventing local alpha values or literal colors.

Disabled state must preserve state comprehension and accessible text contrast. Task 24.4/24.5 may refine opacity and control-specific rules while preserving this contract.

## Surfaces

Surface roles are reusable across application background, Sidebar, Header, Cards, Tables, Forms, Dropdowns, Dialogs and Tooltips. Page-specific names such as `--billing-card-blue` or `--dashboard-widget-purple` are prohibited.

## Text

Text hierarchy is semantic, not page-specific:

- `--text-primary`: primary reading content and headings;
- `--text-secondary`: supporting content;
- `--text-muted`: metadata/low-emphasis content;
- `--text-disabled`: unavailable control content;
- `--text-inverse`: content on inverse surfaces;
- link/brand roles are explicit.

## Borders

Cards/surfaces must not rely on shadow alone. Dark theme in particular should prefer surface differentiation plus subtle borders.

## Actions

Correct:

```css
.buttonPrimary {
  color: var(--action-primary-text);
  background: var(--action-primary);
}
```

Avoid:

```css
.buttonPrimary {
  background: var(--aven-color-blue-500);
}
```

The semantic mapping can change without editing every component.

## Focus

Recommended primitive pattern:

```css
.control:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
}
```

Task 24.4 will refine focus geometry if needed; components should already consume the semantic focus roles.

## Shadows

Available scale:

```css
--shadow-xs
--shadow-sm
--shadow-md
--shadow-lg
--shadow-xl
```

Light theme may use restrained elevation. Dark theme should not simulate elevation with bright/heavy shadows; use surfaces and borders first.

## Radius

```css
--radius-none
--radius-sm
--radius-md
--radius-control
--radius-card
--radius-dialog
--radius-pill
--radius-full
```

Initial Aven structural direction:

- controls: `--radius-control` = 10px;
- cards: `--radius-card` = 16px;
- dialogs: `--radius-dialog` = 18px.

`--radius-pill` is reserved for true pill/chip/status geometries, not every control.

## Spacing

Official scale:

```css
--space-0   /* 0 */
--space-1   /* 4px */
--space-2   /* 8px */
--space-3   /* 12px */
--space-4   /* 16px */
--space-5   /* 20px */
--space-6   /* 24px */
--space-8   /* 32px */
--space-10  /* 40px */
--space-12  /* 48px */
--space-16  /* 64px */
```

Do not create page implementation aliases such as `--billing-filter-gap` unless a genuine reusable product semantic emerges.

## Typography

Task 24.2 establishes hooks; Task 24.4 owns final tuning/font delivery.

Families:

```css
--font-family-ui
--font-family-display
--font-family-mono
```

Weights:

```css
--font-weight-regular
--font-weight-medium
--font-weight-semibold
--font-weight-bold
```

Initial size hooks:

```css
--font-size-xs
--font-size-sm
--font-size-md
--font-size-lg
--font-size-xl
--font-size-2xl
--font-size-3xl
```

Line height:

```css
--line-height-tight
--line-height-normal
--line-height-relaxed
```

The Aven wordmark remains an official image asset and must not be recreated with `--font-family-display`.

## Data Visualization

Categorical series:

```css
--chart-series-1
--chart-series-2
--chart-series-3
--chart-series-4
--chart-series-5
--chart-series-6
```

Structure:

```css
--chart-grid
--chart-axis
--chart-label
--chart-tooltip-bg
--chart-tooltip-text
--chart-reference-line
```

Financial/data states:

```css
--chart-forecast
--chart-estimated
--chart-comparison
--chart-baseline
```

The sequence follows Blue → Indigo → Violet → Light Blue → Lavender-compatible → Cool Cyan-compatible.

### FinOps rule

Chart series are **categorical tokens**, not provider identities. Do not infer:

```text
AWS = Aven blue
OCI = Aven violet
```

unless a later explicit product semantic establishes that mapping. Cost, forecast, savings, reservation coverage, service, account and environment dimensions must use visualization semantics appropriate to the data.

Task 24.18 may refine palette/geometry/legend/tooltip behavior without changing the semantic contract established here.

## Component Tokens

The component layer is intentionally small and reusable:

```css
--sidebar-background
--sidebar-border
--header-background
--header-border
--card-background
--card-border
--control-background
--control-border
--dialog-background
--dialog-border
--tooltip-background
--tooltip-text
```

Every component token derives from semantic tokens. Page-specific component tokens are forbidden.

## Contrast

Representative WCAG contrast checks for the current mappings:

| Pair | Ratio |
|---|---:|
| Light `text-primary` on `surface-primary` | 19.75:1 |
| Light `text-secondary` on `surface-primary` | 10.31:1 |
| Light `text-muted` on `surface-primary` | 4.83:1 |
| `action-primary-text` on `action-primary` | 5.17:1 |
| Dark `text-primary` on primary background | 19.75:1 |
| Dark `text-secondary` on primary surface | 12.04:1 |
| Dark `text-muted` on primary surface | 6.99:1 |

Representative status text/background pairs are above 6.8:1 in Light and above 8.1:1 in Dark.

These checks validate core text/action/status mappings, not every future component composition. Component-level contrast still requires validation when primitives and product components are built.

## Legacy Compatibility

Task 24.1 identified two compatibility domains.

### 1. Brand Kit v1 aliases

`frontend/app/styles/tokens/legacy.css` keeps the original brand-token names such as:

```css
--aven-blue
--aven-purple
--aven-indigo
--aven-bg-light
--aven-bg-dark
--aven-brand-gradient
--aven-radius-card
--aven-radius-control
--aven-font-ui
```

These now resolve to the formal token system.

### 2. Existing DeepOps application variables

The current application consumes transitional/legacy variables such as:

```css
--background
--foreground
--surface
--surface-muted
--primary
--bg
--text
--accent
--accent-2
--radius
--shadow
--chart-1 ... --chart-5
```

They intentionally remain owned by `frontend/app/ui-system.css` during Task 24.2. Repointing them to the Aven semantic palette now would cause a broad unplanned redesign.

Migration contract:

```text
Existing UI
  ↓
ui-system.css / legacy-theme-compat.css (temporary)

New or migrated Aven UI
  ↓
Aven semantic tokens
```

As routes/components migrate, old variables are removed progressively. The compatibility layers must not become permanent.

## Usage Rules

New/migrated visual components should consume semantic tokens first. Primitive color tokens are appropriate only inside token-definition layers or when the value truly represents raw brand identity rather than UI meaning.

### Correct

```css
.card {
  background: var(--surface-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-card);
  padding: var(--space-6);
}
```

### Incorrect

```css
.card {
  background: #ffffff;
  color: #1f2937;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 24px;
}
```

## Forbidden Patterns

Starting with **Task 24.5**, new visual components must not introduce hardcoded:

- color;
- border radius;
- spacing;
- font family;
- font size;
- font weight;
- line height.

Forbidden in new/migrated component styling:

```css
color: #6b7280;
background: #3b82f6;
padding: 16px;
gap: 12px;
border-radius: 10px;
font-size: 14px;
font-weight: 600;
```

Expected:

```css
color: var(--text-secondary);
background: var(--action-primary);
padding: var(--space-4);
gap: var(--space-3);
border-radius: var(--radius-control);
font-size: var(--font-size-sm);
font-weight: var(--font-weight-semibold);
```

### Token abuse is also forbidden

Do not mechanically replace every literal with a page-specific variable:

```css
--dashboard-card-padding
--billing-filter-gap
--reservation-table-radius
```

Prefer reusable design decisions:

```css
--space-4
--space-6
--radius-card
```

## Coverage

The token set can represent the planned visual requirements for:

- application background;
- Sidebar / Header;
- Cards;
- Tables;
- Forms/controls;
- Buttons/links;
- Badges/statuses;
- Dialogs/drawers;
- Tooltips/dropdowns;
- Charts;
- loading/empty/error/warning/success states;
- disabled/focus/selected/hover states.

This is infrastructure coverage; Task 24.2 does not migrate all of those components.

## Migration Notes

Task 24.1 found repeated literal colors in multiple syntaxes, inconsistent spacing/radii and duplicated page-local visual systems. The new architecture consolidates the future design decisions without mass-editing legacy CSS.

The load strategy is intentionally additive:

```text
globals.css
opportunities-stage5.css
Aven tokens/index.css
ui-system.css
legacy-theme-compat.css
remaining page/global CSS
```

The Aven semantic names do not collide with the existing transitional names, so importing the token layer should not alter current page rendering by itself.

### No page redesign in 24.2

This task does not redesign Dashboard, Billing, Reservations, Inventory, Recommendations, Reports, Settings, Login, Sidebar or Topbar. It only establishes the shared runtime contract required for those later tasks.

## Task 24.3 Readiness

**Is Task 24.3 ready to start? YES.**

Task 24.3: **Aven Theme Engine — Light / Dark / System**.

Inputs now available:

```text
Light theme token selector:
:root, html[data-theme="light"]

Dark theme token selector:
html[data-theme="dark"]

Current theme persistence mechanism:
localStorage key "deepops.theme"

Current resolved DOM attribute:
html[data-theme="light|dark"]

Current preference DOM attribute:
html[data-theme-preference="system|light|dark"]

Current resolver:
pre-hydration bootstrap in frontend/app/layout.tsx plus duplicated runtime logic in AppShell and ThemeSelector

Compatibility aliases:
Brand Kit aliases in frontend/app/styles/tokens/legacy.css;
existing application aliases remain in ui-system.css / legacy-theme-compat.css until migrated
```

Theme-sensitive areas requiring careful migration include AppShell, ThemeSelector, Billing charts, Dashboard, RDS Reservations, Opportunities, Flow and Settings surfaces/controls.

Task 24.3 should centralize resolution/application/persistence while preserving the current `deepops.theme` compatibility behavior until the technical rebrand owns key migration.

## Task 24.4 Readiness

**Is Task 24.4 foundation ready? YES.**

Task 24.4 may refine values without rebuilding architecture for:

- Typography;
- Spacing;
- Radius;
- Shadows;
- Focus/motion;
- Iconography.

The required token hooks are already present. Typography still needs final font delivery and named text-style decisions; spacing/radius/shadow values may be tuned while keeping their semantic API stable.
