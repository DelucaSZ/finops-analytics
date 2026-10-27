# Aven UI Primitives

Task 24.5 establishes the official reusable UI primitive layer for Aven. Primitives express generic interface intent; they do not know AWS, OCI, billing, savings, reservations, recommendations, accounts, resources, or other product-domain concepts.

## Philosophy

Aven UI follows the product principle **“Complexity underneath. Clarity above.”** The primitive layer should be predictable, restrained, accessible, theme-aware, and sufficiently dense for an operational FinOps product.

The architecture is:

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
Product Components
↓
Application Pages
```

Primitives own reusable visual behavior. Pages own content, layout composition, and business logic.

## Architecture

Canonical implementation:

```text
frontend/components/ui/
```

The primitive layer uses:

- React 19 and TypeScript;
- native HTML semantics whenever practical;
- CSS Modules for visual implementation;
- Aven semantic/foundation/component CSS custom properties as the visual source of truth;
- `lucide-react` through `frontend/lib/iconography.ts` for functional icon geometry;
- the existing Aven Theme Engine for Light/Dark/System.

No new UI/headless dependency was introduced in Task 24.5. Native controls are used for behavior that browsers already implement correctly. More complex primitives use small React state/focus layers without importing a second visual system.

## Hardcoding Rule

Starting with Task 24.5:

> No new visual component may use hardcoded colors, structural spacing, border radius, or typography.

Forbidden in `frontend/components/ui/`:

```css
color: #3b82f6;
padding: 16px;
gap: 8px;
border-radius: 10px;
font-size: 14px;
font-weight: 600;
```

Expected:

```css
color: var(--text-primary);
padding: var(--space-4);
gap: var(--space-2);
border-radius: var(--radius-control);
font-size: var(--type-body-md-size);
font-weight: var(--type-body-md-weight);
```

The token-definition layer may contain raw values because it is the source of truth. Components and the `/dev/ui` preview may not.

Run:

```bash
cd frontend
npm run lint:design-system
```

The deterministic scanner covers `components/ui` and `app/dev/ui` and reports four explicit counters: colors, structural spacing, radius, and typography.

## Theme Awareness

Primitives consume semantic tokens and therefore react automatically to:

- `light`;
- `dark`;
- `system` resolved by the Theme Engine.

Normal primitives do not read `resolvedTheme` and do not branch on theme in JavaScript. Portaled UI (Tooltip, Dropdown, and Toast) is rendered under `document.body`, where the root `html[data-theme]` semantic-token contract remains available. Dialog and Drawer use the browser top layer through native `<dialog>`.

## Accessibility

Accessibility is part of the primitive contract:

- native interactive elements are preferred;
- focus-visible uses the Aven focus tokens;
- disabled state blocks interaction and has a distinct semantic surface/text treatment;
- form errors expose `aria-invalid` and `aria-describedby`;
- loading buttons expose `aria-busy` and disable repeat activation;
- IconButton requires an accessible `aria-label` at the type level;
- Tabs expose `tablist`/`tab`/`tabpanel`, selection state, roving focus, and arrow/Home/End navigation;
- Dropdown supports Escape, ArrowUp/ArrowDown, Home/End, outside dismissal, and focus return;
- Dialog/Drawer use native modal `<dialog>` behavior, including top-layer focus trapping and Escape/cancel semantics;
- Tooltip supports pointer, focus, and Escape;
- Toast uses live-region/status semantics and a keyboard-reachable dismiss control;
- reduced-motion handling is included for animated primitives.

Status components combine semantic color with icon/text whenever the status needs to carry meaning. Color is not the sole signal.

## Component API

APIs express intent rather than appearance. Prefer:

```tsx
<Button variant="primary" size="md">Salvar</Button>
<Badge variant="success">Ativo</Badge>
```

Do not expose color/radius/padding props such as `blue`, `rounded10`, or `mediumPadding`.

`className` remains available for composition/layout integration, but is not the supported mechanism for replacing the Aven visual contract.

## Button

`<Button />` supports:

- variants: `primary`, `secondary`, `outline`, `ghost`, `danger`;
- sizes: `sm`, `md`, `lg`;
- states: default, hover, active, focus-visible, disabled, loading;
- leading/trailing content for icons;
- native button attributes and forwarded refs.

Loading preserves the label, adds the standardized Spinner, exposes `aria-busy`, and disables repeated activation.

## IconButton

`<IconButton />` supports standardized sizes, loading, disabled state, optional Tooltip, and requires `aria-label`. The hit target uses control geometry rather than the glyph size.

## Input

`<Input />` supports label, helper text, error, disabled, readOnly, leading icon, trailing action, control size, native input attributes, and forwarded refs.

## Textarea

`<Textarea />` shares the Input field language and supports label, helper text, error, disabled/readOnly, and `none | vertical | both` resize behavior.

## Select

`<Select />` intentionally uses native `<select>` behavior. It supports label, placeholder, options, disabled options, error/helper text, sizes, keyboard navigation, native theme/color-scheme behavior, and refs. Search is not introduced because no existing search-select infrastructure exists.

## Checkbox

`<Checkbox />` supports checked, unchecked, indeterminate, disabled, label, and description. The visual indicator includes a check/minus glyph so selection is not color-only.

## Radio

`<Radio />` and `<RadioGroup />` use native radio semantics. `RadioGroup` provides a fieldset/legend composition primitive; browser radio-group keyboard behavior is preserved.

## Switch

`<Switch />` represents a boolean only. It supports controlled/uncontrolled state, label, description, disabled state, keyboard activation, and `role="switch"`. Three-state selectors such as Light/Dark/System must not use Switch.

## Badge

`<Badge />` variants are semantic: `neutral`, `info`, `success`, `warning`, `danger`. Appearances are `solid`, `outline`, and `subtle`. APIs do not expose named colors.

## Tooltip

`<Tooltip />` opens by pointer or focus and closes on pointer leave, blur, or Escape. It renders through a portal to avoid clipping, uses the motion token as a short reveal delay, and augments the trigger's `aria-describedby`; it does not replace required form/control labels.

## Dropdown

Compound API:

```tsx
<DropdownMenu>
  <DropdownMenuTrigger>...</DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuItem>...</DropdownMenuItem>
    <DropdownMenuSeparator />
  </DropdownMenuContent>
</DropdownMenu>
```

Items support icons, disabled state, semantic danger actions, keyboard navigation, focus management, and outside dismissal.

## Tabs

Compound API: `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`. Controlled and uncontrolled active values are supported. Keyboard navigation follows horizontal tabs conventions.

## Dialog

Compound API: `Dialog`, `DialogTrigger`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription`, `DialogFooter`, `DialogClose`.

Native `<dialog>.showModal()` supplies modal top-layer/focus trapping behavior. Aven owns surface, border, radius, elevation, focus, sizing, backdrop, and responsive visual treatment.

## Drawer

Compound API mirrors Dialog and supports `left` and `right`. Bottom drawer is intentionally not implemented because no current product requirement justifies the additional variant.

## Card

Compound API: `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`.

Cards use Aven surface/border/radius/elevation tokens. Do not turn every section into an elevated Card: prefer normal sections/dividers where a distinct surface is not meaningful.

## Table

Primitives: `Table`, `TableHeader`, `TableBody`, `TableFooter`, `TableCaption`, `TableRow`, `TableHead`, `TableCell`, `TableState`.

The wrapper handles narrow-layout overflow. Numeric cells use consistent end alignment and tabular numerals. Empty/loading state content can be composed with `TableState`. Sorting/filtering/virtualization remain product/data-table responsibilities.

## Pagination

`<Pagination />` supports previous/next, page count, current page, disabled boundaries, accessible labels, and controlled page changes.

## Skeleton

`<Skeleton />` supports `text`, `rectangular`, and `circle`. Animation is disabled under `prefers-reduced-motion`.

## Alert

`<Alert />` supports `info`, `success`, `warning`, and `danger`, with default semantic icon, title, description, actions, and custom content.

## EmptyState

`<EmptyState />` supports optional icon, title, description, primary action, and secondary action. It intentionally has no product-domain knowledge.

## Toast

`<ToastProvider />` + `useToast()` provide `success`, `info`, `warning`, and `danger` notifications. Toasts are dismissible, have configurable timeout, pause on pointer hover or keyboard focus, use live-region/status semantics, and inherit the active theme through root CSS custom properties.

The provider is mounted once at the application root.

## Divider

`<Divider />` supports `horizontal` and `vertical`, using border tokens only.

## Avatar

`<Avatar />` supports image, fallback initials, and `sm | md | lg`. No arbitrary user gradient is generated.

## Spinner

`<Spinner />` supports `sm | md | lg`, uses the official Lucide geometry/stroke contract, exposes an optional screen-reader label, and respects the shared reduced-motion foundation.

## Usage Rules

- Build product components from these primitives plus Aven tokens.
- Reuse semantic variants rather than creating page-specific colors.
- Keep layout decisions in product/page composition where possible.
- Preserve native semantics before adding ARIA.
- Use semantic status tokens for status meaning.
- Use `danger` for destructive actions.
- Align equivalent `sm | md | lg` controls through the shared control-height contract.
- Do not branch on Light/Dark in ordinary primitive code.

## Composition

Prefer small compound primitives over monolithic prop surfaces:

```tsx
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardContent>...</CardContent>
</Card>
```

`Field`, `FieldLabel`, `FieldDescription`, and `FieldError` are shared internal/public composition helpers used by form primitives to prevent duplicated label/error contracts.

## Forbidden Patterns

Do not:

- add raw color values to primitives;
- add literal padding/margin/gap/radius/type values;
- use legacy application aliases such as `--bg`, `--accent`, or `--surface-2`;
- add arbitrary Tailwind-style values if Tailwind is introduced later;
- use `transition: all`;
- use `outline: none` without the Aven focus replacement;
- create `purpleBadge`, `greenButton`, or other appearance-driven APIs;
- introduce a second icon library for common UI actions;
- implement product/domain concepts in this directory;
- replace native semantics with `div role=...` without a concrete requirement.

## Legacy Migration

Legacy UI remains available during progressive migration. Task 24.5 does not mass-replace pages.

| Legacy component/pattern | Aven destination | Migration |
|---|---|---|
| global `.button` / page-local buttons | `Button`, `IconButton` | page migrations 24.7+ |
| legacy form selectors | `Input`, `Textarea`, `Select`, choice primitives | auth/settings/page migrations |
| `StatusBadge` | `Badge` + future product `StatusIndicator` | 24.6+ |
| legacy card/panel selectors | `Card` or semantic section/divider composition | page migrations |
| `OpportunityDecisionDialog` | `Dialog` + product content | 24.6 / 24.14 |
| `OpportunityArchiveDialog` | `Dialog` + product content | 24.6 / 24.14 |
| page-local table styling | Table primitives + future product DataTable | 24.6+ / page migrations |
| legacy loading/status blocks | `Spinner`, `Skeleton`, `Alert`, `EmptyState`, Toast | page migrations |
| AppShell navigation controls | Aven primitives + future shell product composition | 24.7 |

Removal of legacy CSS is deliberately deferred until dependent pages are migrated.

## Testing

Automated Task 24.5 checks cover:

- required primitive/barrel presence;
- hardcode gate = zero;
- scanner rejection of representative forbidden values;
- Button semantic/loading contract;
- native form and error/accessibility contracts;
- Tabs/Dropdown keyboard contracts;
- Dialog/Drawer native modal/cancel contract;
- reduced-motion and `transition: all` prohibition.

Technical preview:

```text
/dev/ui
```

The preview uses the real Theme Engine and exposes Light/Dark/System controls plus relevant default, disabled, loading, error, selected, overlay, data, and feedback states.
