# Aven Technical Rebrand

## Scope

Task 24.8 moves the public/runtime identity from DeepOps to Aven without turning branding into a breaking infrastructure refactor. Public naming, metadata, authentication copy, email copy, developer-facing API title, browser icon and shell brand consumption are migrated. Technical identifiers remain legacy where changing them would alter API, storage, deployment, database or infrastructure contracts.

**Technical rebrand: COMPLETE**  
**Raster-dependent runtime branding: PARTIAL**

The partial raster state is intentional: the approved raster masters listed in `ASSET_INVENTORY.md` are not present in the repository and were not regenerated or approximated.

## Public Product Identity

- Product name: **Aven**
- Tagline: **Clarity. Flow. Control.**
- Principle: **Complexidade por baixo. Clareza por cima.**
- Runtime description: FinOps visibility, optimization, governance and cloud cost control.

`frontend/lib/brand.ts` is the frontend source of truth for product name, tagline, description and runtime asset references.

## Branding Source of Truth

```text
docs/brand/aven/                canonical kit/specification
        ↓
frontend/public/brand/aven/     runtime vector copies required by the application
        ↓
frontend/lib/brand.ts           public naming + runtime asset paths
        ↓
BrandLogo / metadata / auth / shell
```

The application must not import runtime assets directly from `docs/brand/aven/`.

## Runtime Assets

Versioned runtime assets currently available:

- `frontend/public/brand/aven/aven-logo-horizontal-fallback.svg`
- `frontend/public/brand/aven/aven-icon-gradient.svg`
- `frontend/app/icon.svg` — exact copy of the official gradient symbol for Next.js metadata routing.

The horizontal SVG remains the documented technical fallback. The approved raster wordmarks remain the visual master.

## Logo Strategy

`frontend/components/brand/BrandLogo` centralizes runtime logo selection.

- Light: horizontal repository fallback wordmark is used where a wordmark is appropriate.
- Dark: the official gradient symbol is used while the approved dark-runtime raster wordmark is unavailable.
- Compact/collapsed: official gradient symbol.
- No text is used to recreate the AVEN wordmark.
- No CSS brightness/invert/hue recoloring is required; the legacy shell filter token resolves to `none`.

This is an explicit temporary runtime strategy until the approved raster masters are uploaded.

## Favicon

The old DeepOps `frontend/app/favicon.ico` was removed so Next.js cannot continue auto-publishing a legacy favicon. `frontend/app/icon.svg` now contains the official Aven gradient symbol and root metadata points to the versioned official SVG runtime symbol.

The final approved `favicon.ico` and raster sizes are still blocked by missing masters; no raster was generated from SVG or screenshots.

## Metadata

Root metadata now uses Aven for:

- `applicationName`;
- default browser title;
- title template `%s — Aven`;
- product description;
- icon metadata.

No artificial SEO/Open Graph/Twitter metadata was added because the authenticated application did not already use those surfaces.

A static `theme-color` was not introduced: the application already resolves Light/Dark/System client-side and a hardcoded color would diverge from the semantic Theme Engine. This can be added later only through a framework-supported theme-aware strategy.

## Manifest / PWA

The repository contains a brand-kit reference manifest under `docs/brand/aven/web/manifest.webmanifest`, but the runtime application does not currently implement a complete PWA/manifest flow. Task 24.8 therefore does not create a partial PWA. When PWA support is introduced, `name` and `short_name` must both be `Aven` and icons must use the approved raster masters.

## Application Shell

The Task 24.7 shell already exposed Aven publicly. Task 24.8 makes it consume the central brand configuration and shared `BrandLogo` abstraction, preserving navigation, auth gating, responsive behavior, sidebar persistence and Theme Engine behavior.

## Authentication Surfaces

Updated public branding:

- Login base branding uses Aven runtime logo.
- Login account copy uses `PRODUCT_NAME`.
- Forgot/reset/invitation form uses Aven runtime logo.
- MFA enrollment references Aven.
- Authentication flow, routes, cookies and session behavior are unchanged.

The complete visual Login redesign remains Task 24.9.

## Reports / Exports

No public report/export branding contract requiring a safe rename was identified in the current Task 24.1 inventory. Existing API/export contracts are intentionally left unchanged. Feature-level report redesign remains outside this task.

## Email Templates

Password-reset and invitation email subjects/body now identify the product as Aven. SMTP host, credentials, sender address/domain, TLS and DKIM/SPF concerns were not changed.

## Legacy Branding Inventory

| Legacy reference | Location | Classification | Action | Final state | Compatibility reason |
| --- | --- | --- | --- | --- | --- |
| `DeepOps | FinOps Multi-Cloud` | `frontend/app/layout.tsx` | METADATA | REPLACE | Aven metadata | Public browser identity |
| DeepOps login wordmark/copy | `frontend/app/login/page.tsx` | USER_VISIBLE_BRAND | REPLACE | Aven logo/name | Public auth surface |
| DeepOps access-form brand | `frontend/components/access-form.tsx` | USER_VISIBLE_BRAND | REPLACE | Aven logo | Public auth surface |
| `Proteja sua conta DeepOps` | `frontend/app/mfa-setup/page.tsx` | USER_VISIBLE_BRAND | REPLACE | Aven | Public auth surface |
| `tema visual do DeepOps` | Appearance settings | USER_VISIBLE_BRAND | REPLACE | Aven | Public settings copy |
| DeepOps mail subject/body | `backend/app/services/mailer.py` | USER_VISIBLE_BRAND | REPLACE | Aven | User-facing email |
| `DeepOps API` | `backend/app/main.py` | METADATA | REPLACE | `Aven API` | Developer-facing brand metadata only |
| legacy green `app/icon.svg` | `frontend/app/icon.svg` | ASSET | REPLACE | official Aven gradient SVG | Public browser icon |
| old `app/favicon.ico` | `frontend/app/favicon.ico` | ASSET | REMOVE | absent until approved Aven ICO arrives | Prevent stale DeepOps runtime icon |
| `deepops.theme` | `frontend/lib/ui-preferences.mjs` | BACKWARD_COMPATIBILITY | KEEP | preserved | Avoid resetting theme preference |
| `deepops.sidebar.collapsed` | `frontend/lib/ui-preferences.mjs` | BACKWARD_COMPATIBILITY | KEEP | preserved | Avoid resetting sidebar preference |
| `deepops:session-invalidated` | frontend API/AppShell | BACKWARD_COMPATIBILITY | KEEP | preserved | Existing cross-module session event |
| `nuvemiq_token` cleanup | `frontend/components/app-shell.tsx` | BACKWARD_COMPATIBILITY | KEEP | preserved | Clears obsolete auth state safely |
| `X-DeepOps-Request` | `frontend/lib/api.ts` | API_CONTRACT | KEEP | preserved | Backend CSRF/request marker contract |
| `/api/v1/deepops-costs` | backend/cloudwatch cost API | API_CONTRACT | KEEP | preserved | Existing client/API contract |
| `NUVEMIQ_*` | `backend/app/core/config.py` | ENVIRONMENT_VARIABLE | KEEP | preserved | Production/deployment compatibility |
| `nuvemiq-api` health service | `backend/app/main.py` | INFRASTRUCTURE | KEEP | preserved | Health/observability compatibility |
| `deepops-usage-costs.*` | frontend lib/imports | INTERNAL_IDENTIFIER | KEEP | preserved | Private module naming, no public value |
| `deepops-web` | `frontend/package.json` | INTERNAL_IDENTIFIER | KEEP | preserved | Private package/lockfile coupling |
| DeepOps/NuvemIQ CFN filenames/identifiers | `infrastructure/cloudformation/` | INFRASTRUCTURE | KEEP | preserved | Deployed infrastructure contracts |
| historical Task/docs terminology | historical docs/changelogs | DOCUMENTATION | KEEP | preserved | Correct historical context |

## Technical Identifiers Preserved

Technical legacy is allowed only where it is classified and justified. Public identity and internal contract names are deliberately separated. Remaining technical identifiers do not authorize new DeepOps/NuvemIQ user-facing copy.

## Environment Variables

`NUVEMIQ_*` remains the active environment-variable family. Strategy: **KEEP / MIGRATE LATER**.

If an `AVEN_*` family is introduced in the future, it must use compatible fallback/alias behavior before existing deployment variables are deprecated. Task 24.8 does not rename production `.env`, Docker, EC2, CI/CD, reverse-proxy or CORS configuration.

## Storage / Cookie Compatibility

- Keep `deepops.theme`.
- Keep `deepops.sidebar.collapsed`.
- Keep existing auth/session cookies and their security attributes.
- Keep `nuvemiq_token` cleanup until obsolete-token compatibility is explicitly retired.

No user preference or authenticated session is reset by this rebrand.

## Brand Lint

`npm run lint:brand` scans runtime frontend/backend/infrastructure source for DeepOps/NuvemIQ variants. Known technical references are allowed only through `frontend/scripts/brand-legacy-allowlist.mjs`, where each entry records file, classification, reason and future migration strategy. Legacy filenames are separately allowlisted by exact path.

The CI frontend job executes brand lint before the design-system gate, lint, typecheck, tests and build.

## Raster Asset Status

Blocked/pending approved files from `ASSET_INVENTORY.md`:

### Production wordmarks
- `01_Logos/PNG/aven_logo_horizontal_dark_ui_4096.png`
- `01_Logos/PNG/aven_logo_horizontal_light_ui_4096.png`
- `01_Logos/PNG/aven_logo_vertical_dark_ui_4096.png`
- `01_Logos/PNG/aven_logo_vertical_light_ui_4096.png`
- `01_Logos/PNG/aven_logo_vertical_no_tagline_dark_text_4096.png`
- `01_Logos/PNG/aven_logo_vertical_no_tagline_white_text_4096.png`

### Favicon/app icons
- `02_Icons/Favicon/favicon.ico`
- `02_Icons/Favicon/apple-touch-icon.png`
- `02_Icons/Favicon/android-chrome-192x192.png`
- `02_Icons/Favicon/android-chrome-512x512.png`
- `02_Icons/Favicon/aven_icon_16x16.png`
- `02_Icons/Favicon/aven_icon_32x32.png`
- `02_Icons/Favicon/aven_icon_48x48.png`
- `02_Icons/Favicon/aven_icon_64x64.png`
- `02_Icons/Favicon/aven_icon_128x128.png`
- `02_Icons/Favicon/aven_icon_180x180.png`
- `02_Icons/Favicon/aven_icon_192x192.png`
- `02_Icons/Favicon/aven_icon_256x256.png`
- `02_Icons/Favicon/aven_icon_512x512.png`
- `02_Icons/Favicon/aven_icon_1024x1024.png`

No blocked raster criterion is reported as complete.

## Validation

Required automated gates:

```bash
cd frontend
npm run lint:brand
npm run lint:design-system
npm run lint
npm run typecheck
npm test
npm run build
```

Backend CI continues to run Ruff formatting/lint and pytest. Runtime smoke validation covers Login, authenticated shell, Dashboard, Billing, Reservations, Collections/Inventory-equivalent surfaces, Recommendations/Opportunities, Reports where present, and Settings without altering feature business logic.

Expected hardcode gate for the new branding component:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

## Scope Report

### Changed
- Public product naming and root metadata.
- Browser SVG icon.
- Shell brand consumption/asset strategy.
- Login/access/MFA/appearance visible branding.
- User-facing auth emails.
- FastAPI public/developer title.
- Brand lint and CI gate.

### Preserved intentionally
- API paths/headers.
- `NUVEMIQ_*` environment variables.
- storage keys, auth cleanup and session event.
- database/service/infrastructure identifiers.
- repository/domain/DNS/TLS/CORS.

### Deprecated
- DeepOps public product identity.
- old DeepOps App Router favicon asset.
- CloudCog/text recreation of the login brand.

### Blocked by missing raster assets
- approved `favicon.ico`;
- Apple touch icon;
- Android/PWA icons;
- production light/dark PNG wordmarks.

### Deferred
- domain/repository/infrastructure renaming;
- environment-variable aliases/migration;
- full PWA implementation;
- Login redesign (24.9);
- Dashboard redesign (24.10);
- feature-page redesigns.

## Deferred Infrastructure Changes

No repository rename, domain/DNS/TLS change, CORS change, API namespace change, database migration, Docker network/container/volume rename, OAuth/OIDC identifier change or telemetry rename is part of Task 24.8.

## Task 24.9 Readiness

**Is Task 24.9 ready to start? YES**

- Aven product name globally available: **YES**
- Aven logo runtime available: **YES** (official SVG symbol + documented horizontal fallback)
- Light logo strategy: **YES**
- Dark logo strategy: **YES** (official symbol fallback; final raster wordmark pending)
- Tagline available: **YES**
- Theme Engine ready: **YES**
- UI Primitives ready: **YES**
- Authentication flow preserved: **YES**
- Login legacy branding removed: **YES**

Task 24.9 can redesign the Login without solving identity, runtime asset routing, theme or primitive foundations again.

## Task 24.10 Readiness

Dashboard redesign can start after Task 24.9 without reopening global branding, shell, theme, logo routing or metadata architecture. The approved raster asset upload remains an independent completion item for final production artwork quality.
