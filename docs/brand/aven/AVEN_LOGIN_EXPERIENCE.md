# Aven Login Experience

## Goals

Task 24.9 makes the public Login the first complete Aven feature experience. The surface must communicate **Aven** and **Clarity. Flow. Control.** with a premium, restrained and operational presentation while preserving the existing authentication contracts.

The implementation follows the mandatory Task 24.5+ rule: new and refactored visual code must consume Aven tokens and official primitives instead of hardcoded colors, structural spacing, radius or typography.

## Current Authentication Flow

The functional flow remains owned by `frontend/app/login/page.tsx` and `frontend/lib/api`:

```text
email + password
↓
POST /auth/login
├── authenticated → /
├── enrollment_required → /mfa-setup
└── mfa_required + challenge
    ↓
    authenticator code or recovery code
    ↓
    POST /auth/mfa/verify
    ↓
    /
```

The authenticated application session gate remains in `frontend/components/app-shell.tsx`. Public auth routes continue to bypass the authenticated Application Shell, and protected routes continue to use `/auth/me` and redirect unauthenticated users to `/login`.

## New Auth Layout

`frontend/components/auth/auth-layout.tsx` is a visual composition layer only. It owns:

- institutional brand area;
- authentication content frame;
- Light/Dark institutional background selection through semantic/theme tokens;
- responsive collapse from two-column desktop composition to authentication-first mobile composition.

It does not fetch, authenticate, redirect, persist credentials or own session state.

Dependency direction:

```text
Login Page
↓
AuthLayout
↓
Aven UI Primitives
↓
Aven tokens / Theme Engine
```

## Brand Area

The desktop institutional area uses the official `BrandLogo` abstraction, the canonical `PRODUCT_TAGLINE`, the product principle and the official background gradient tokens.

The wordmark fallback contains dark text, so it is rendered on a controlled light logo surface rather than recolored or reconstructed. No new logo or illustration is introduced.

## Login Form

The Login form uses the canonical Aven primitives:

- `Card` for the form surface;
- `Input` for email, password and MFA/recovery codes;
- `IconButton` for accessible password visibility;
- `Button` for primary and secondary actions;
- `Alert` for authentication errors.

The form remains a native `<form>` and supports Enter submit. Email and password keep the browser/password-manager semantics `autocomplete="username"` and `autocomplete="current-password"`.

## Theme Support

The Login does not implement a separate theme runtime. It consumes the existing Task 24.3 Theme Engine and semantic tokens.

- Light institutional surface: `--gradient-background-light`;
- Dark institutional surface: `--gradient-background-dark`;
- System mode: resolved by the global Theme Engine before the application renders;
- form controls/surfaces: semantic tokens used by official primitives.

This preserves the existing no-flash bootstrap behavior from the root layout and Theme Engine.

## Responsive Behavior

Desktop uses institutional and authentication areas side by side. Medium widths stack the institutional area above the form. Narrow/mobile widths prioritize authentication and replace the large institutional panel with compact Aven branding above the form.

The auth surface uses natural vertical scrolling and `100dvh`, so low-height notebooks, mobile viewports and zoomed layouts do not rely on rigid fixed positioning.

## Authentication Preservation

Task 24.9 does not change:

- login endpoint or payload;
- MFA verification endpoint or payload;
- cookies/session behavior;
- `/auth/me` session gate;
- logout behavior;
- authorization rules;
- CORS/security headers;
- backend authentication;
- enrollment redirect;
- password-reset route.

Passwords and MFA codes remain component state only and are not persisted to storage.

## MFA

The existing challenge flow remains embedded in Login. A successful initial login that returns `mfa_required` stores only the challenge in component state and renders the same form surface for either:

- six-digit authenticator code; or
- recovery code.

The MFA input preserves `autocomplete="one-time-code"`, numeric input mode and six-digit pattern when the authenticator path is active. The recovery-code toggle and return-to-login action use official Aven buttons.

## Error Handling

Backend/client authentication errors retain the current message semantics and are presented through `Alert variant="danger"`. Task 24.9 does not introduce more specific credential errors that could increase user-enumeration risk.

The Alert primitive provides the accessible alert role for danger messages.

## Accessibility

The experience preserves or adds:

- native form/input/button semantics;
- explicit labels for all fields;
- browser autofill/password-manager attributes;
- keyboard submit;
- tokenized `focus-visible` treatment inherited from primitives;
- accessible `Mostrar senha` / `Ocultar senha` IconButton labels and tooltips;
- non-focusable decorative lock icon;
- error announcement through the Alert primitive;
- authentication-first mobile reading order.

## Performance

The Login adds no animation library, background video, stock photography or large raster asset. The layout is CSS-based and the existing client boundary remains limited to authentication/form state.

## Asset Strategy

`BrandLogo` remains the single runtime logo abstraction. Task 24.9 uses the repository-safe official/fallback assets already centralized by Task 24.8 and does not regenerate raster masters.

Approved raster masters remain subject to the asset inventory and can replace fallbacks later without changing Login composition.

## Hardcoding Rules

The enforced Login scopes are:

```text
frontend/components/auth
frontend/app/login
```

`frontend/scripts/check-design-system.mjs` scans these paths in addition to the established Aven Design System scopes.

Expected result:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

Responsive breakpoint literals are CSS media-query thresholds rather than visual spacing tokens; CSS custom properties cannot be used directly in media-query conditions.

## Tests

`frontend/tests/aven-login-experience.test.mjs` verifies:

- reusable `AuthLayout` architecture;
- official Aven primitive composition;
- login/MFA endpoint and redirect preservation;
- password-manager/autofill semantics;
- password visibility accessibility;
- recovery-code availability;
- Light/Dark gradient contract;
- responsive composition contract;
- zero hardcodes in new/refactored Login sources;
- documentation integration.

Repository gates remain:

```bash
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
npm run lint:design-system
npm run lint:brand
```

## Known Constraints

- The approved raster wordmark masters are still governed by `ASSET_INVENTORY.md`; Login intentionally uses the centralized runtime-safe brand abstraction from Task 24.8.
- Browser-specific autofill and third-party password-manager overlays require interactive browser smoke testing in addition to static/test/build gates.
- Task 24.9 does not redesign unrelated account-management pages or alter authentication policy.
