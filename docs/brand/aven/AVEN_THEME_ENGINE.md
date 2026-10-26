# Aven Theme Engine

## Overview

Task 24.3 centralizes Aven theme behavior into one runtime controller while preserving the semantic-token architecture introduced by Task 24.2.

Runtime flow:

```text
Stored Preference
        │
        ├── light ─────────────→ Light
        │
        ├── dark ──────────────→ Dark
        │
        └── system
              │
              └── prefers-color-scheme
                       │
                       ├── light → Light
                       └── dark  → Dark
```

Product flow:

```text
User preference
      ↓
Theme resolver
      ↓
Resolved theme
      ↓
<html data-theme="light|dark">
      ↓
Aven semantic tokens
      ↓
UI
```

The engine is intentionally small: localStorage persists preference, an early bootstrap resolves the first paint, `ThemeProvider` owns runtime state/listeners, and `useTheme()` is the consumer API.

## Theme Preference

The only supported preference values are:

```ts
type ThemePreference = "light" | "dark" | "system";
```

The default for a user without a persisted preference is `system`.

`system` is a durable user preference. It is never overwritten with the currently resolved Light or Dark value simply because the operating system currently uses that mode.

## Resolved Theme

The resolved theme is always:

```ts
type ResolvedTheme = "light" | "dark";
```

Resolution matrix:

| Preference | OS | Resolved |
|---|---|---|
| Light | Light | Light |
| Light | Dark | Light |
| Dark | Light | Dark |
| Dark | Dark | Dark |
| System | Light | Light |
| System | Dark | Dark |

Explicit Light/Dark always wins over the operating-system preference.

## DOM Contract

The resolved theme is exposed to CSS through one authoritative selector:

```html
<html data-theme="light">
```

or:

```html
<html data-theme="dark">
```

`data-theme` is the only resolved-theme selector used by the Aven token mappings.

For diagnostics and preference-aware controls, the root also exposes the non-resolved preference:

```html
<html data-theme-preference="system" data-theme="dark">
```

These attributes represent different concepts and must not conflict. `style.colorScheme` mirrors the resolved theme so native controls and browser-provided UI use the appropriate Light/Dark scheme.

## Token Integration

Task 24.3 consumes, rather than recreates, the Task 24.2 token architecture:

```text
frontend/app/styles/tokens/semantic-light.css
frontend/app/styles/tokens/semantic-dark.css
```

The Light mapping is selected by `:root` / `html[data-theme="light"]`; the Dark mapping is selected by `html[data-theme="dark"]`.

Components should continue to express visual intent through semantic tokens:

```css
.component {
  background: var(--surface-primary);
  color: var(--text-primary);
  border-color: var(--border-subtle);
}
```

Common components should not branch on `resolvedTheme` when CSS custom properties can solve the requirement. `resolvedTheme` is intended for cases such as JavaScript-driven charts, external libraries, or assets that require an explicit Light/Dark variant.

Legacy application aliases remain in the existing compatibility layers so Task 24.3 does not trigger an unplanned redesign.

## Persistence

Preference is persisted in browser `localStorage` using the existing production key:

```text
deepops.theme
```

The legacy technical name is deliberately retained in Task 24.3 because the Task 24.1 audit identifies it as an existing production compatibility key and assigns technical branding migration to a later rebrand task. Introducing `aven.theme` now would create two sources of truth or silently discard existing preferences.

Persisted values are only:

```text
light
dark
system
```

Legacy boolean values are normalized once:

```text
true  → dark
false → light
```

Invalid persisted values fall back to `system` and are corrected when storage is writable.

If localStorage throws (privacy restrictions, browser policy, test environment), the engine continues in memory and resolves from `system` rather than breaking the application.

## Initial Bootstrap

`getThemeBootstrapScript()` in `frontend/lib/ui-preferences.mjs` generates the minimal pre-hydration script used by the root layout.

Order:

```text
1. read deepops.theme
2. normalize/migrate the stored preference
3. resolve system with prefers-color-scheme
4. set data-theme-preference
5. set data-theme
6. set color-scheme
7. React hydrates
```

This executes in `<head>` before the application body is rendered. The critical first-frame case is therefore:

```text
stored dark + OS light → first resolved DOM theme is dark
```

There is no `useEffect`-only first-paint dependency.

The sidebar bootstrap remains separate because sidebar collapse is an independent preference domain.

## System Theme

`system` resolves through:

```js
window.matchMedia("(prefers-color-scheme: dark)")
```

When the operating-system theme changes while the application is open and the preference remains `system`, `ThemeProvider` updates `resolvedTheme`, the root DOM contract, `color-scheme`, and therefore the semantic-token mapping without a reload.

Explicit `light` and `dark` preferences do not subscribe to operating-system changes.

## Runtime Updates

Calling `setTheme()` performs the complete transition:

```text
setTheme(preference)
      ↓
update provider preference state
      ↓
persist preference (best effort)
      ↓
resolve current Light/Dark theme
      ↓
update data-theme-preference
      ↓
update data-theme + color-scheme
      ↓
semantic tokens switch immediately
```

No page reload is required.

System-theme listeners are created only while `theme === "system"`, cleaned up on preference changes/unmount, and include the legacy `MediaQueryList.addListener/removeListener` fallback for older WebKit implementations.

## Theme Provider

The official provider is:

```text
frontend/components/theme-provider.tsx
```

It owns:

- preference state;
- resolved theme state;
- storage read/write behavior;
- DOM application;
- operating-system media-query subscription;
- multi-tab storage synchronization.

Theme behavior was removed from `AppShell` and `ThemeSelector`, eliminating the previous three-way duplicated controller.

The provider is mounted at the root layout around `AppShell`, so public/authenticated routes share the same engine and theme does not depend on authentication state.

## useTheme API

Consumer API:

```tsx
const { theme, resolvedTheme, setTheme } = useTheme();
```

Examples:

```tsx
setTheme("light");
setTheme("dark");
setTheme("system");
```

Consumers do not read/write storage, resolve media queries, or mutate the root theme attribute directly.

`ThemeSelector` now uses only this API.

## Legacy Migration

Compatibility decisions:

- keep `deepops.theme` as the single persisted key for Task 24.3;
- migrate string/boolean legacy values `true`/`false` to `dark`/`light`;
- normalize invalid values to `system`;
- remove the old `deepops:theme-change` custom-event dependency because provider state is now the same-tab source of truth;
- remove theme mutation/listener logic from `AppShell` and `ThemeSelector`;
- retain existing legacy CSS/DeepOps variables because broad visual migration is explicitly outside Task 24.3.

The storage-key branding migration can occur later with an explicit one-time compatibility strategy.

## SSR / Hydration

The application uses Next.js App Router. The server cannot know a localStorage preference, so Task 24.3 does not add cookies or backend persistence.

SSR strategy:

```text
Server
  └── deterministic provider snapshot: theme=system, resolvedTheme=light

Browser before body paint
  └── bootstrap reads localStorage + matchMedia and applies real DOM theme

After hydration
  └── ThemeProvider reads the same preference and synchronizes React state
```

`<html suppressHydrationWarning>` remains in place because the pre-hydration bootstrap intentionally mutates root data attributes before React hydrates.

Theme-dependent component markup should prefer semantic CSS. JavaScript consumers that need `resolvedTheme` receive the synchronized provider value after mount; current application components do not render theme-specific markup during SSR.

No cookie is introduced because it would add a second persistence mechanism without a current SSR requirement.

## Multi-tab Synchronization

`ThemeProvider` listens for the browser `storage` event for `deepops.theme`.

```text
Tab A: setTheme("dark")
        ↓
localStorage changes
        ↓
Tab B receives storage event
        ↓
preference=dark / resolvedTheme=dark
```

Same-tab updates do not depend on the storage event; `setTheme()` updates provider and DOM synchronously.

## Accessibility

The existing Theme Selector remains a native radio-group structure (`fieldset`, `legend`, radio inputs and text labels). This preserves:

- accessible group labeling;
- keyboard navigation provided by native radio controls;
- a textual current option, not color-only state;
- existing focus-visible behavior from the current UI layer.

Task 24.3 does not redesign the selector.

Native controls receive the resolved `color-scheme` at the root, improving browser-native rendering for date/datetime/select/checkbox/radio controls in both themes.

## Testing Matrix

Automated coverage includes:

- explicit Light/Dark resolver behavior;
- `system` + OS Light/Dark;
- missing preference → `system`;
- invalid preference → `system`;
- legacy boolean migration;
- storage read/write failure fallback;
- first-paint bootstrap precedence;
- bootstrap behavior with invalid/blocked storage;
- provider ownership of system/storage listeners and cleanup;
- semantic Light/Dark token selectors;
- ThemeSelector delegation to `useTheme()`;
- removal of theme-controller logic from `AppShell`.

Required manual browser smoke matrix:

```text
1. no stored preference -> System
2. System + OS Dark -> Dark
3. System + OS Light -> Light
4. explicit Dark ignores OS changes
5. explicit Light ignores OS changes
6. switch back to System -> follows OS again
7. reload -> preference preserved
8. navigate between routes -> no reset/flash
9. login -> authenticated application -> logout/login -> same browser preference
10. second tab follows a preference change through storage event
```

## Known Constraints

- The server does not know localStorage preference. The early bootstrap is therefore the FOUC-prevention mechanism; cookies are intentionally not added.
- A no-JavaScript session falls back to the existing CSS default rather than reading persisted browser preference. A CSS-only system fallback was not duplicated into the semantic token files because doing so would duplicate the complete Dark mapping and could diverge from the canonical token contract.
- `meta[name="theme-color"]` is not currently part of the application/PWA runtime contract and is not introduced in this functional task. It can be wired when Aven metadata/PWA rebranding is applied.
- Existing legacy pages still consume `ui-system.css` / compatibility aliases. Task 24.3 changes theme orchestration, not their visual design.
- Final raster/logo switching remains deferred to the Application Shell/Login rebrand tasks.

## Usage Examples

Normal component — no theme branch:

```css
.card {
  background: var(--surface-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}
```

JavaScript-driven visualization/asset — explicit resolved theme when required:

```tsx
const { resolvedTheme } = useTheme();

const chartTheme = resolvedTheme === "dark" ? darkChartConfig : lightChartConfig;
```

Do not use `resolvedTheme` merely to choose normal card/text/background colors; semantic CSS tokens own those decisions.

## Task 24.4 Readiness

```text
Is Task 24.4 ready to start?
YES
```

Current foundation:

```text
Current UI font loading:
- Inter is referenced in CSS stacks but is not explicitly bundled/imported.
- system-ui fallback is active when Inter is unavailable.

Display font strategy:
- Task 24.4 should define a geometric/Sora-like display strategy for headings/identity.
- The Aven wordmark remains an approved image asset and must not be recreated as text.

Available spacing tokens:
--space-0, --space-1, --space-2, --space-3, --space-4, --space-5,
--space-6, --space-8, --space-10, --space-12, --space-16

Available radius tokens:
--radius-none, --radius-sm, --radius-md, --radius-control, --radius-card,
--radius-dialog, --radius-pill, --radius-full

Available shadow tokens:
--shadow-xs, --shadow-sm, --shadow-md, --shadow-lg, --shadow-xl

Current icon library:
lucide-react

Theme-dependent icon constraints:
- normal interface icons should inherit currentColor / semantic foreground tokens;
- no separate Light/Dark icon system is required today;
- theme-specific brand/image assets may consume resolvedTheme when later rebrand tasks introduce them;
- iconography must not encode provider identity or theme state through hardcoded colors.
```

## Task 24.5 Readiness

```text
Can Aven UI primitives consume theme-aware semantic tokens without visual hardcoding?
YES
```

The primitive → semantic Light/Dark mappings already exist from Task 24.2, and Task 24.3 now provides a stable runtime selector and consumer API. New primitives can use semantic color tokens plus the existing spacing/radius/typography/shadow hooks without embedding visual literals.
