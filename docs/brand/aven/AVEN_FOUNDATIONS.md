# Aven Foundations

Task 24.4 closes the structural foundation of the Aven Design System. It refines the token architecture created in Task 24.2 and consumes the Light/Dark/System runtime created in Task 24.3; it does not create a parallel styling system and it does not redesign product pages.

## Philosophy

Aven should communicate trust, control, clarity, sophistication and technology while remaining operationally dense enough for FinOps work.

> Complexity underneath. Clarity above.

The visual hierarchy must be premium and restrained, not gamer-like, neon, overly rounded, decorative or marketing-dashboard heavy.

The product contract is:

```text
Aven Brand
↓
Primitive Tokens
↓
Visual Foundations
↓
Semantic Theme Mapping
↓
UI Primitives
↓
Product Components
↓
Pages
```

Runtime source of truth remains `frontend/app/styles/tokens/`. `AVEN_DESIGN_TOKENS.md` describes architecture; this document describes how the visual foundations are applied.

---

## Typography

### Font Families

Aven uses three explicit family roles:

| Token | Family | Usage |
|---|---|---|
| `--font-family-ui` | Inter + system fallback | body, labels, buttons, inputs, tables, navigation, badges, forms and metadata |
| `--font-family-display` | Sora + Inter/system fallback | page/section headings, editorial display and selected KPI emphasis |
| `--font-family-mono` | system monospace stack | ARN, OCID, resource IDs, account IDs when technical, code and logs |

Inter and Sora are delivered by the framework-native `next/font/google` loader with the Latin subset, `display: swap`, and only weights 400/500/600/700. This avoids a new font package and lets Next.js handle preloading/font optimization.

The Aven wordmark is an official graphic asset. **Never rebuild the wordmark by typing “Aven” with Sora, Inter, or another approximate font.**

### Font Weights

| Token | Value | Meaning |
|---|---:|---|
| `--font-weight-regular` | 400 | body/content |
| `--font-weight-medium` | 500 | labels/metadata emphasis |
| `--font-weight-semibold` | 600 | controls/subheadings |
| `--font-weight-bold` | 700 | display/KPI emphasis |

New Aven UI must not introduce arbitrary 550/650/750/800/850/900 weights. Legacy values remain migration debt and are not the model for new primitives.

### Font Sizes

The scale intentionally includes 13px and 14px because the Task 24.1 audit showed a dense operational UI with tables, filters and metadata. Large text remains controlled rather than marketing-sized.

| Token | Value | Typical use |
|---|---:|---|
| `--font-size-xs` | 12px | captions, compact metadata |
| `--font-size-sm` | 13px | dense labels/table headers |
| `--font-size-md` | 14px | default operational body/control text |
| `--font-size-lg` | 16px | comfortable body/small heading |
| `--font-size-xl` | 18px | heading |
| `--font-size-2xl` | 20px | section heading |
| `--font-size-3xl` | 24px | page heading/KPI |
| `--font-size-4xl` | 30px | prominent KPI/display |
| `--font-size-5xl` | 36px | restrained display maximum |

### Line Heights

| Token | Value | Use |
|---|---:|---|
| `--line-height-none` | 1 | compact control text / isolated metric |
| `--line-height-tight` | 1.2 | display and KPI |
| `--line-height-snug` | 1.35 | headings/labels |
| `--line-height-normal` | 1.5 | body/table content |
| `--line-height-relaxed` | 1.65 | longer reading copy when required |

### Letter Spacing

Aven uses letter spacing sparingly:

| Token | Value | Use |
|---|---:|---|
| `--letter-spacing-tight` | `-0.02em` | display/large KPI |
| `--letter-spacing-normal` | `0` | default UI |
| `--letter-spacing-wide` | `0.04em` | exceptional tiny labels/metadata only |

Do not turn tracking into a decorative default and do not use aggressive uppercase tracking throughout the product.

### Semantic Roles

Semantic text roles live in `frontend/app/styles/tokens/foundations.css`. Each role exposes family, size, weight and line-height; display/KPI roles also expose letter spacing when required.

| Role | Family | Size | Weight | Line height | Usage |
|---|---|---:|---:|---:|---|
| Display LG | Display | 36px | 700 | 1.2 | rare institutional/display moment |
| Display MD | Display | 30px | 700 | 1.2 | prominent page/editorial moment |
| Heading XL | Display | 24px | 700 | 1.2 | page title |
| Heading LG | Display | 20px | 600 | 1.35 | main section |
| Heading MD | UI | 18px | 600 | 1.35 | subsection/card heading |
| Heading SM | UI | 16px | 600 | compact section heading |
| Body LG | UI | 16px | 400 | comfortable content |
| Body MD | UI | 14px | 400 | default operational content |
| Body SM | UI | 13px | 400 | dense content/metadata |
| Label MD | UI | 14px | 500 | form/control label |
| Label SM | UI | 13px | 500 | dense label |
| Caption | UI | 12px | 400 | metadata/supporting copy |
| Button | UI | 14px | 600 | button/control text |
| KPI LG | Display | 30px | 700 | primary metric |
| KPI MD | Display | 24px | 700 | secondary metric |
| Table header | UI | 13px | 600 | table headings |
| Table body | UI | 14px | 400 | table values |
| Code/resource | Mono | 13px | 400 | technical identifiers/code |

Task 24.5 may wrap these roles in primitive components/variants. It must not create a second type scale.

### KPI Typography

KPI emphasis is constrained to `KPI LG` and `KPI MD` for normal product surfaces. Currency, percentages, counts, savings, coverage and utilization should be prominent through hierarchy, contrast and spacing—not oversized marketing typography, gradients on every number or excessive uppercase.

Use `font-variant-numeric: var(--font-variant-numeric-tabular)` for metrics where stable digit alignment matters.

### Numeric Typography

Use tabular numerals for:

- currency and cost;
- percentages and utilization;
- counts in aligned metric groups;
- dates/times in tables where digit alignment improves scanning;
- usage and coverage values.

Do not force tabular numerals on prose.

### Monospace

Use `--font-family-mono` for truly technical identifiers such as ARN, OCID, resource/account IDs when presented as identifiers, logs and code. Normal financial values, dates and counts remain in the UI/display families.

---

## Spacing

### Scale

Aven uses one shared spacing scale:

| Token | Value |
|---|---:|
| `--space-0` | 0 |
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-5` | 20px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-10` | 40px |
| `--space-12` | 48px |
| `--space-16` | 64px |

The scale covers the repeated values identified by the 24.1 audit without preserving historical off-scale corrective values as new design decisions.

### Usage

Recommended composition:

| Context | Guidance |
|---|---|
| control internal gap | `--space-2` |
| compact control inline padding | `--space-3` |
| default control inline padding | `--space-4` |
| comfortable control inline padding | `--space-5` |
| card padding | `--space-6` |
| section gap | `--space-6` to `--space-8` |
| toolbar/filter gap | `--space-2` to `--space-3` |
| form field gap | `--space-2` |
| table cell padding | block `--space-3`, inline `--space-4` |
| dialog padding | `--space-6` |
| page-level padding | compose from the shared scale; responsive page composition may vary |

Do not create page tokens such as `--billing-padding`, `--dashboard-gap`, `--reservation-margin` or `--login-spacing`.

### Density

Aven is a FinOps operations product. The density model is conceptual rather than page-specific:

- **compact** — dense tables and filter-heavy operational areas;
- **default** — normal application UI;
- **comfortable** — forms and prominent/low-density areas.

Control heights are standardized as 36px / 40px / 44px. A 36px desktop minimum hit target is available as `--hit-target-min`; touch-oriented interactions should target at least `--hit-target-touch` (44px).

---

## Radius

### Scale

| Token | Value | Purpose |
|---|---:|---|
| `--radius-none` | 0 | intentionally square geometry |
| `--radius-xs` | 4px | micro surface/detail |
| `--radius-sm` | 6px | small nested surface |
| `--radius-md` | 9px | compatibility-scale intermediate; avoid as the primary component decision |
| `--radius-control` | 10px | inputs/selects/buttons/icon controls |
| `--radius-card` | 16px | cards/panels/popovers |
| `--radius-dialog` | 18px | dialogs/drawers |
| `--radius-pill` | 999px | badges/chips/true pills |
| `--radius-full` | 9999px | circular/fully rounded geometry such as avatars |

`--radius-md` remains at 9px to avoid a migration conflict with the existing transitional UI. New primitives should prefer the semantic roles (`control`, `card`, `dialog`, `pill`, `full`) rather than choosing an arbitrary intermediate radius.

### Usage

- Input / Select / Button → `--radius-control`
- Cards → `--radius-card`
- Dialogs / Drawers → `--radius-dialog`
- Badge / Chip → `--radius-pill`
- Avatar → `--radius-full`

Nested geometry should remain visually ordered: a control inside a 16px card normally uses the 10px control radius. Inner elements should not become visually rounder than their container without a specific interaction reason.

Aven is not a “bubble UI”; do not use `--radius-pill` as the default control/card geometry.

---

## Elevation

Elevation is a combination of **surface + border + shadow**, never shadow alone.

The stable shadow API is:

```css
--shadow-none
--shadow-xs
--shadow-sm
--shadow-md
--shadow-lg
--shadow-xl
```

The numeric shape of those shadows is intentionally theme-mapped in `semantic-light.css` and `semantic-dark.css` because Dark elevation requires a different strategy.

### Light Theme

Light uses restrained black-alpha shadows. Cards normally use a very small shadow plus a subtle border; popovers/dialogs can step up progressively. Avoid large opaque shadows, excessive blur and Material-style floating stacks.

### Dark Theme

Dark prioritizes surface and border contrast:

- Level 1 deliberately uses no shadow;
- Level 2 begins with only `--shadow-xs`;
- higher floating surfaces increase shadow gradually;
- no bright shadow/glow is used for normal hierarchy.

Glow is not a standard card elevation. It is reserved for rare institutional/premium moments such as a login brand background or explicitly selected premium element.

### Levels

| Level | Intent | Light | Dark |
|---|---|---|---|
| 0 | application background | background + no shadow | background + no shadow |
| 1 | cards/base surfaces | subtle border + `shadow-xs` | surface/border + no shadow |
| 2 | dropdown/popover | elevated surface + `shadow-sm` | elevated surface/border + `shadow-xs` |
| 3 | dialog/drawer | overlay surface + `shadow-md` | overlay surface/border + `shadow-sm` |
| 4 | critical floating UI | strongest normal border + `shadow-lg` | stronger border + `shadow-md` |

Use the `--elevation-N-surface`, `--elevation-N-border` and `--elevation-N-shadow` contracts rather than recreating elevation literals.

---

## Iconography

### Library

`lucide-react` is the canonical functional icon library. The audit found no need for a second icon package. Existing custom/provider/brand assets remain separate domains.

`frontend/lib/iconography.ts` is the React-facing geometry API; its sizes point back to CSS variables so the CSS token layer remains the visual source of truth.

### Sizes

| Token | Value | API key |
|---|---:|---|
| `--icon-size-xs` | 12px | `xs` |
| `--icon-size-sm` | 14px | `sm` |
| `--icon-size-md` | 16px | `md` |
| `--icon-size-lg` | 18px | `lg` |
| `--icon-size-xl` | 20px | `xl` |
| `--icon-size-2xl` | 24px | `2xl` |
| `--icon-size-3xl` | 32px | `3xl` |

Default functional icon: `iconSizes.md` (16px). Default prominent control icon: `iconSizes.lg` (18px). Sidebar guidance for Task 24.7 is 18px default, centered in the row/hit area.

### Stroke

- default functional stroke → `--icon-stroke-default` = 1.75;
- stronger/emphasis stroke → `--icon-stroke-strong` = 2;
- individual components must not invent arbitrary stroke widths.

### Functional Icons

Functional icons should inherit `currentColor`; the consuming component selects semantic color such as `--text-secondary`, `--action-primary` or status tokens.

Correct:

```tsx
<SearchIcon size={iconSizes.md} strokeWidth={iconStrokeWidths.default} />
```

Avoid:

```tsx
<SearchIcon size={17} color="#3B82F6" />
```

### Status Icons

Status communication should combine color + icon + label whenever practical:

- success → semantic success color + affirmative icon + text;
- warning → warning color + warning icon + text;
- danger → danger color + error/alert icon + text;
- info → info color + informational icon + text;
- pending → neutral/info treatment + pending icon + text;
- loading → standardized loader behavior + accessible status text/label.

Do not encode state only by color.

### Disclosure

Use one consistent disclosure vocabulary:

- `ChevronDown` for a closed dropdown/accordion that opens downward;
- `ChevronUp` only when the same affordance explicitly collapses upward;
- `ChevronRight` for collapsed hierarchical navigation/detail rows;
- `ChevronDown` for expanded hierarchical navigation/detail rows.

Do not mix unrelated arrows/carets for the same action.

### Loading

Future Spinner primitives should use the Lucide-compatible 16–20px range in normal controls and consume the shared spinner motion values. Under `prefers-reduced-motion: reduce`, the foundation reduces the rotation contract to a single iteration; the component must retain a textual/ARIA loading state so motion is not the sole signal.

### Brand Icons

The Aven symbol/wordmark are official brand assets. Do not reconstruct them with Lucide.

AWS/OCI marks are provider assets, not generic design-system icons. Do not recolor/rebuild official provider marks as if they were Lucide glyphs.

### Accessibility

Icon-only controls must provide:

- an accessible name (`aria-label` or equivalent);
- visible focus treatment using the semantic focus system;
- an adequate hit target (36px minimum desktop, 44px where touch is expected);
- a tooltip when the action is not self-evident or benefits from explanation.

The glyph may be 16–20px while the hit target is larger.

---

## Focus System

Focus color remains semantic (`--focus-ring`, `--focus-ring-offset`). Geometry is now standardized with `--focus-outline-width` and `--focus-outline-offset`.

Future primitives must align focus shape with the element radius. An IconButton using `--radius-control` must not render a focus affordance whose geometry visually conflicts with that control.

Do not remove focus outlines without supplying a visible `:focus-visible` replacement.

---

## Tables

Task 24.5/24.6 should build table primitives/product components from this contract:

- header → `type-table-header` role;
- cell → `type-table-body` role;
- numeric cells → tabular numerals and deliberate alignment;
- cell padding → `--space-3` block / `--space-4` inline as the default composition;
- status indicators → semantic status + icon/text where needed;
- action icons → canonical icon sizes and adequate hit areas;
- compact density is appropriate for high-volume FinOps tables.

This task does not redesign existing tables.

---

## Forms

Default future form direction:

- label → `type-label-md`;
- helper/error → body-sm/caption scale with semantic text/status colors;
- control text → body-md / button role as appropriate;
- control radius → `--radius-control`;
- control height → 40px default, 36px compact, 44px comfortable;
- inline control gap → `--space-2`;
- icon → 16–18px inside a control;
- field-to-helper gap → `--space-2`.

Task 24.5 owns final primitive implementation.

---

## Responsive Guidance

Typography remains mostly fixed so dense operational UI is predictable. Do not make table/body/control text fluid.

A page or institutional display may use a controlled `clamp()` later when a concrete layout needs it, bounded by the existing type scale. Do not introduce free-form responsive type values outside the scale.

The spacing scale is stable across viewports. Page-level composition may choose a smaller/larger token at defined breakpoints, but should not create dozens of viewport-specific spacing literals.

---

## Usage Rules

### Typography

Correct:

```css
.title {
  font-family: var(--font-family-display);
  font-size: var(--font-size-3xl);
  font-weight: var(--font-weight-bold);
  line-height: var(--line-height-tight);
}
```

Incorrect:

```css
.title {
  font-family: Inter;
  font-size: 24px;
  font-weight: 700;
  line-height: 30px;
}
```

### Spacing

Correct:

```css
.card {
  padding: var(--space-6);
  gap: var(--space-4);
}
```

Incorrect:

```css
.card {
  padding: 24px;
  gap: 16px;
}
```

### Radius

Correct:

```css
.card {
  border-radius: var(--radius-card);
}
```

Incorrect:

```css
.card {
  border-radius: 16px;
}
```

### Elevation

Correct:

```css
.popover {
  background: var(--elevation-2-surface);
  border-color: var(--elevation-2-border);
  box-shadow: var(--elevation-2-shadow);
}
```

Avoid reusable local shadow literals.

### Component Composition

Correct:

```css
.component {
  font-family: var(--font-family-ui);
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  line-height: var(--line-height-normal);

  padding: var(--space-4);
  gap: var(--space-2);

  border-radius: var(--radius-control);
  box-shadow: var(--shadow-sm);
}
```

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

---

## Legacy Migration

Task 24.4 does not mass-replace existing hardcodes. Legacy typography, spacing, radii, shadows and local icon choices identified by Task 24.1 remain migration debt owned by later route/component tasks.

Compatibility rules:

- existing DeepOps variables stay in `ui-system.css` / `legacy-theme-compat.css` until their owners migrate;
- Brand Kit aliases stay in `tokens/legacy.css`;
- new Aven primitives must consume the Aven token/foundation API, not the transitional DeepOps variables;
- `--radius-md` remains 9px because that primitive name currently overlaps the transitional scale; new components should use semantic radius roles so the overlap does not become a new dependency;
- no page-specific aliases are introduced to disguise legacy hardcodes.

Priority is a complete contract for new UI, not a cosmetic rewrite of old pages.

---

## Forbidden Patterns

Do not introduce in new/migrated Aven visual components:

- literal hex/rgb/hsl colors where semantic tokens exist;
- arbitrary spacing/padding/margin/gap values;
- arbitrary border radii;
- local font-family/font-size/font-weight/line-height scales;
- one-off reusable shadows;
- arbitrary Lucide sizes/strokes;
- emojis as functional icons;
- filled/outline icon mixing without a deliberate semantic reason;
- provider logos treated as generic UI glyphs;
- page-specific design tokens such as `--billing-filter-gap`;
- glow as standard card elevation.

Token abuse is also forbidden: an extremely local 2–3px geometry detail that is not a shared design decision does not need a global token. The strict rule applies to structural color, spacing, radius and typography decisions in new components.

---

## Task 24.5 Contract

**Mandatory rule:**

> A partir da Task 24.5, nenhum novo componente visual deverá utilizar cores, border radius, spacing ou typography hardcoded.

This includes:

- `color`, `background`, `border-color`;
- structural spacing, `padding`, `margin`, `gap`;
- `border-radius`;
- `font-family`, `font-size`, `font-weight`, `line-height`.

New components consume Aven Design System tokens/APIs. Shadows and icon geometry should also use the foundation contracts whenever they represent reusable visual decisions.

### Hardcode enforcement readiness

Can new components use tokens for all of the following?

- Colors: **YES**
- Spacing: **YES**
- Radius: **YES**
- Font family: **YES**
- Font size: **YES**
- Font weight: **YES**
- Line height: **YES**
- Shadows: **YES**
- Icons: **YES**
- Theme awareness: **YES**

### Definition of Ready

Is Task 24.5 ready to start? **YES**

Task 24.5 can now build Aven UI Primitives without embedding structural visual literals. The Theme Engine remains the owner of Light/Dark/System resolution; normal primitives should react to theme through semantic CSS tokens rather than branching on `resolvedTheme`.
