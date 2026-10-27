# Aven Application Shell

Task 24.7 establishes the persistent authenticated application frame for Aven. The shell consumes the Design Tokens, Theme Engine, Visual Foundations, UI Primitives and Product Components created by Tasks 24.2–24.6; feature pages remain independently migratable.

## Architecture

```text
Root AppShell
├── public-route passthrough
├── authentication/session gate
└── ApplicationShell
    ├── Sidebar
    ├── Topbar
    ├── Mobile Drawer
    └── Main Content Frame
        └── Feature Page
```

`frontend/components/app-shell.tsx` retains the pre-existing authentication/session orchestration. Visual shell code lives in `frontend/components/app-shell/`.

This separation is deliberate: authentication, logout, routing and API behavior are not visual responsibilities, while collapse/mobile navigation and persistent shell composition are.

## Shell Hierarchy

Authenticated routes render inside one viewport-height grid. The desktop sidebar and topbar remain outside the main scroll owner. `main` is the primary page scroll container.

Public authentication routes continue to bypass the authenticated shell.

No feature-specific fetch, query parameter, permission decision or FinOps business rule is implemented in `ApplicationShell`.

## Sidebar

The desktop Sidebar uses the Aven semantic surface and border contracts. It preserves the existing collapse preference and the production compatibility key `deepops.sidebar.collapsed`.

Expanded mode shows the approved Aven horizontal fallback asset. Collapsed mode uses the official Aven gradient symbol. The fallback source includes the institutional tagline in its full artwork; the shell constrains the rendered viewport to the wordmark area so the persistent navigation does not display the tagline.

The sidebar does not use a permanent institutional gradient, glass effect or theme-specific JSX.

## Topbar

The Topbar is persistent application chrome, not a replacement for `PageHeader`.

It owns only global utilities currently supported by the product:

- mobile navigation trigger;
- Theme Engine control;
- current user identity when available from the existing session endpoint;
- existing logout action.

No account/environment selector is moved into the shell because the audited application does not currently provide a canonical global account/environment context. Page-specific selectors remain owned by their feature pages.

## Navigation Configuration

The navigation tree is defined once in:

```text
frontend/components/app-shell/navigation.ts
```

Both the desktop Sidebar and mobile Drawer render from this configuration.

Task 24.7 deliberately preserves the existing primary destinations and label language instead of performing an information-architecture redesign:

- Dashboard
- Oportunidades
- Histórico
- Fluxo
- Billing
- Reservas RDS
- Coletas
- Configurações

Other existing routes remain routable and are not deleted or blocked by the shell.

## Active Route

`isNavigationItemActive()` derives state from the real pathname.

Rules:

1. exact route match is active;
2. explicitly owned nested prefixes can remain active;
3. non-exact destinations match only `href + "/"`, avoiding accidental string-prefix collisions.

`/opportunities/collection/*` keeps Oportunidades active, while `/opportunities/history-cycles` remains represented by Histórico.

No duplicate local "selected navigation item" state exists.

## Branding

Task 24.7 is the controlled transitional shell-branding step.

Runtime shell assets are copied from the versioned Brand Kit fallbacks:

```text
/public/brand/aven/aven-logo-horizontal-fallback.svg
/public/brand/aven/aven-icon-gradient.svg
```

The shell never recreates the Aven wordmark with Inter/Sora text. A centralized `--shell-brand-wordmark-filter` token provides a dark-theme fallback until final runtime assets are supplied. Final raster/runtime asset selection and global technical rebrand remain Task 24.8.

## Theme Integration

The shell uses the Task 24.3 `useTheme()` API only.

Supported preferences:

```text
Light
Dark
System
```

The Topbar does not read/write theme storage, call `matchMedia`, resolve the system theme or mutate `data-theme`. Semantic CSS tokens change Sidebar, Topbar, main background, menus, Drawer and primitive overlays automatically.

Sidebar collapse remains a separate preference domain.

## Responsive Behavior

The audited application breakpoint for shell collapse/mobile behavior is retained at 850px.

Desktop:
- persistent Sidebar;
- optional persisted collapse;
- persistent Topbar;
- main content owns page scrolling.

Narrow layout:
- desktop Sidebar is removed from layout;
- Topbar exposes the mobile trigger;
- the same navigation configuration renders inside the Aven `Drawer`;
- content gutters use the compact shell token.

No second mobile navigation tree exists.

## Mobile Navigation

Mobile navigation reuses the Task 24.5 native-dialog-backed `Drawer`, including modal top-layer behavior, Escape handling, backdrop dismissal and browser focus management.

Route navigation closes the Drawer.

## Scroll Model

Ownership is explicit:

```text
html/body
└── ApplicationShell: viewport frame, overflow hidden
    ├── Sidebar: fixed frame
    │   └── Navigation: internal overflow only when required
    └── Workspace
        ├── Topbar: persistent grid row
        └── main: page scroll owner
```

This prevents body/main double scrolling and keeps the Topbar visible without adding sticky overlay stacking contexts.

Legacy feature pages may retain their own horizontal table/chart overflow where required.

## Z-Index / Overlays

The shell uses the shared z-index scale from `components.css`.

Dropdown and Tooltip primitives remain portaled to `document.body`. Drawer uses native `<dialog>` top-layer behavior. The main scroll container therefore does not clip those overlays.

No arbitrary high z-index is introduced.

## Accessibility

The shell provides:

- skip link to `#main-content`;
- semantic `<aside>`, `<nav>`, `<header>` and `<main>` landmarks;
- labeled navigation regions;
- `aria-current="page"` for active navigation;
- accessible labels for icon-only collapse/mobile controls;
- tooltips for collapsed icon-only navigation;
- primitive focus-visible behavior;
- shared Dropdown keyboard behavior;
- Drawer Escape/focus behavior;
- session identity derived from real session data rather than fictitious placeholders.

Expanded navigation does not add redundant tooltips.

## Legacy Page Compatibility

Task 24.7 changes persistent chrome only. Feature-page markup and business behavior are not redesigned.

The old global `.app-shell`, `.sidebar`, `.main-content` and related visual selectors remain temporarily in legacy CSS because later page tasks still own broader cleanup. The new shell uses CSS Modules, so the legacy selectors no longer style the authenticated frame.

Page gutters are supplied once by `contentFrame`; the removed legacy `.main-content` class prevents double shell padding.

Wide pages can consume the full available inline size. The shell imposes no universal page `max-width`.

## Hardcoding Rules

All visual source under:

```text
frontend/components/app-shell.tsx
frontend/components/app-shell/
```

is protected by `npm run lint:design-system`.

Expected result:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

Shared shell geometry is expressed through semantic/component tokens in `frontend/app/styles/tokens/components.css`.

Brand SVG source values are official versioned assets, not component styling, and therefore remain outside the component hardcode gate.

## Testing

`frontend/tests/aven-application-shell.test.mjs` covers:

- required architecture;
- shared navigation configuration;
- exact/nested active-route behavior;
- collapse persistence separation from theme;
- Light/Dark/System Theme Engine delegation;
- shared mobile Drawer navigation;
- logout/session compatibility;
- public routes/auth gate;
- landmarks and `aria-current`;
- scroll ownership;
- shell hardcode gate;
- shared shell tokens;
- documentation integration.

Normal release validation remains:

```bash
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
npm run lint:design-system
```

Browser smoke testing should cover Light/Dark/System, desktop expanded/collapsed navigation, mobile Drawer, user menu, theme menu, nested routes, short/long/table/chart pages, existing overlays and logout.

## Migration Notes

| Legacy element | Task 24.7 disposition |
|---|---|
| `components/app-shell.tsx` mixed visual/auth component | REFACTORED into auth gate + ApplicationShell |
| global `.app-shell` frame | DEPRECATED for authenticated shell |
| global `.sidebar` visual implementation | DEPRECATED for authenticated shell |
| manual mobile overlay/nav | REPLACED by Aven Drawer |
| inline local nav array | REPLACED by shared `navigation.ts` |
| route-active rendering | REFACTORED into `isNavigationItemActive()` |
| manual sidebar tooltip spans | REPLACED by Tooltip primitive |
| legacy DeepOps shell mark | REPLACED in shell by versioned Aven fallback asset |
| Theme Engine | REUSED |
| Button/IconButton/Dropdown/Avatar/Divider/Drawer/Tooltip | REUSED |
| logout/session API behavior | REUSED without protocol change |

The legacy CSS may be physically removed only after dependent page migrations prove it is no longer needed.

## Task 24.8 Readiness

Task 24.8 can change the global product name, runtime brand asset mapping, metadata, favicon and manifest without rebuilding shell layout or navigation architecture.

The shell's brand surface is isolated to `AvenBrand`, and normal theme visuals are semantic-token-driven.

## Page Migration Readiness

The shell contract is ready to receive Tasks 24.9–24.17 progressively. Login remains outside the authenticated shell; Dashboard, Billing, Reservations, Inventory/collection-related surfaces, Recommendations, Reports/secondary areas and Settings can migrate their internal page composition without another persistent-shell reconstruction.
