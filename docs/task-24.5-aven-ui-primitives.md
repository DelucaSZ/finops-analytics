# Task 24.5 — Aven UI Primitives

## Scope

Task 24.5 creates the first official Aven component layer on top of Tasks 24.2–24.4. It does not migrate entire product pages, create product-domain components, rebuild the Application Shell, or perform the DeepOps → Aven technical rebrand.

## Components created

The new canonical library is `frontend/components/ui/` and exports:

- Button
- IconButton
- Input
- Textarea
- Select
- Checkbox
- Radio / RadioGroup
- Switch
- Badge
- Tooltip
- DropdownMenu compound primitives
- Tabs compound primitives
- Dialog compound primitives
- Drawer compound primitives
- Card compound primitives
- Table compound primitives
- Pagination
- Skeleton
- Alert
- EmptyState
- ToastProvider / useToast
- Divider
- Avatar
- Spinner
- Field / FieldLabel / FieldDescription / FieldError

A barrel export is available at `frontend/components/ui/index.ts`.

## Components reused / foundations consumed

Task 24.5 deliberately reuses instead of rebuilding:

- the semantic Light/Dark mappings from Task 24.2;
- the Task 24.3 Theme Engine and root `data-theme` contract;
- typography, spacing, radius, elevation, hit-target, focus, icon, and motion foundations from Task 24.4;
- `frontend/lib/iconography.ts` and `lucide-react`;
- native browser behaviors for input/select/radio/checkbox/table/dialog where they are mature.

No Radix, CVA, shadcn, or second UI library was added because the audited stack contains no existing headless dependency and the required behaviors can be implemented without importing a competing system.

## API decisions

- APIs are semantic (`variant="success"`, `variant="danger"`) rather than color-driven.
- Equivalent controls use `sm | md | lg` and shared control-height tokens.
- `className` is retained for layout/composition integration, not as the primary visual customization API.
- Native HTML attributes are extended where appropriate.
- Forwarded refs are supported for Button, IconButton, Input, Textarea, Select, Checkbox, Radio, Spinner, and other relevant leaf controls.
- Compound primitives are used for Card, Tabs, Dialog, Drawer, Dropdown, and Table instead of monolithic prop surfaces.

## Variants and states

### Button

Variants: primary, secondary, outline, ghost, danger.

Sizes: sm, md, lg.

States: default, hover, active, focus-visible, disabled, loading.

### Forms

Input/Textarea/Select: default, hover, focus, disabled, readOnly where applicable, error, helper text.

Checkbox: unchecked, checked, indeterminate, disabled.

Radio: checked/unchecked/disabled with native group keyboard behavior.

Switch: on/off/disabled with controlled and uncontrolled state.

### Status and feedback

Badge: neutral/info/success/warning/danger with solid/outline/subtle appearances.

Alert and Toast: info/success/warning/danger.

Skeleton/Spinner: shared loading language and reduced-motion behavior.

## Accessibility

Implementation includes:

- native elements before ARIA emulation;
- Aven focus-visible token treatment;
- explicit accessible label requirement for IconButton;
- `aria-busy` for loading Button;
- `aria-invalid` + `aria-describedby` for field errors;
- indeterminate checkbox semantics;
- `role="switch"` and `aria-checked` for Switch;
- Tabs ARIA relationships and ArrowLeft/ArrowRight/Home/End behavior;
- Dropdown Escape/ArrowUp/ArrowDown/Home/End/outside-dismiss/focus management and portal rendering;
- native modal `<dialog>` behavior for Dialog/Drawer;
- Tooltip focus/pointer/Escape behavior, short tokenized reveal delay, and portal rendering;
- Toast live region, status/alert semantics, dismiss button, and timeout pause while hovered or keyboard-focused;
- reduced-motion handling.

## Hardcode validation

Added:

```text
frontend/scripts/check-design-system.mjs
```

Run:

```bash
cd frontend
npm run lint:design-system
```

Scopes:

```text
components/ui
app/dev/ui
```

Expected gate:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

The scanner intentionally excludes the token-definition files because raw values belong in the design-token source of truth, not in components.

## Token additions

The existing component/status token layers were extended only where primitives required a reusable semantic contract:

- danger action tokens;
- dialog/drawer/popover/tooltip sizing roles;
- switch/avatar/skeleton/empty-state/toast geometry roles;
- overlay z-index scale.

These are shared primitive decisions, not page-specific aliases.

## Preview / smoke test

A technical preview exists at:

```text
/dev/ui
```

It uses the real `useTheme()` engine to switch Light/Dark/System and demonstrates:

- Button variants/sizes/loading/disabled;
- IconButton/Tooltip;
- Input normal/error/disabled;
- Select/Textarea;
- Checkbox checked/indeterminate/disabled;
- Radio and Switch;
- Badge variants;
- Alerts and Toast;
- Dropdown, Tabs, Dialog, Drawer;
- Card, EmptyState, Table, Pagination;
- Spinner, Avatar, Divider, Skeleton.

The route is a development/technical preview and is not a product-page migration.

## Toast root integration

`ToastProvider` is mounted once inside the existing ThemeProvider at the root layout so product components can consume `useToast()` without creating multiple notification roots.

## Legacy migration map

| Legacy component/pattern | Aven primitive | Migration task |
|---|---|---|
| legacy/global buttons | Button / IconButton | 24.7+ page migrations |
| legacy form controls | Input / Textarea / Select / Checkbox / Radio / Switch | 24.9+ / 24.16+ |
| `StatusBadge` | Badge + future StatusIndicator | 24.6+ |
| legacy cards/panels | Card or section/divider composition | page migrations |
| `OpportunityDecisionDialog` | Dialog + product content | 24.6 / 24.14 |
| `OpportunityArchiveDialog` | Dialog + product content | 24.6 / 24.14 |
| page-local tables | Table primitives + future DataTable | 24.6+ / page migrations |
| page-local loading/empty/error UI | Spinner / Skeleton / Alert / EmptyState / Toast | page migrations |
| legacy shell interaction controls | Button / IconButton / Tooltip / Dropdown / Divider | 24.7 |

No legacy UI is removed in this task.

## Tests

Task-specific Node tests are in:

```text
frontend/tests/aven-ui-primitives.test.mjs
```

The CI/frontend job also runs the hardcode gate and TypeScript typecheck before the production build.

## Pending / explicitly deferred

Not part of Task 24.5:

- MetricCard, RecommendationCard, AccountSelector, FilterBar, DateRangePicker, ChartCard, provider/status domain mapping, and other Product Components — Task 24.6;
- new Sidebar, Topbar, Navigation, Application Shell — Task 24.7;
- global DeepOps/NuvemIQ rebrand — Task 24.8;
- full page migrations and legacy CSS removal — later Task 24.x migrations;
- advanced DataTable behaviors such as sorting, filtering, virtualization, column visibility — product layer;
- searchable combobox — defer until a concrete product requirement or existing infrastructure exists.

## Definition of Ready — Task 24.6

```text
Is Task 24.6 ready to start?
YES

Can product components be built using only Aven primitives + Aven tokens?

Button: YES
Forms: YES
Cards: YES
Status: YES
Overlays: YES
Tables: YES
Feedback states: YES
Loading states: YES
Theme awareness: YES
Accessibility foundation: YES
```

## Definition of Ready — Task 24.7

```text
Does the foundation support Application Shell / Sidebar / Topbar / Navigation
without introducing a second component system?
YES
```

Task 24.7 can compose shell navigation from Button, IconButton, Tooltip, Dropdown, Avatar, Divider, loading/feedback primitives, Aven tokens, and future Task 24.6 product-level composition where needed.
