# Aven Visual QA & Legacy Cleanup

## Scope

Task 24.19 is the closure gate for the Phase 24 Aven visual migration. It audits the real Next.js route tree, Light/Dark/System behavior, responsive composition, shell/overlay/scroll contracts, accessibility, public branding, design-system compliance, functional regressions and legacy visual cleanup.

The task is intentionally conservative: visual cleanup is allowed only when replacement and non-use can be demonstrated. Technical compatibility identifiers are not renamed for cosmetic reasons.

## Non-goals

- No new product feature.
- No new route.
- No backend endpoint, persistence, domain rule, calculation, analytics or integration.
- No dependency modernization.
- No environment-variable migration.
- No test-configuration workaround.
- No completion of functionally incomplete controls discovered during QA.

## Functional Freeze

| Gate | Result |
|---|---|
| New product features | 0 |
| New routes | 0 |
| New backend APIs | 0 |
| New persistence | 0 |
| New domain rules | 0 |
| New calculations / analytics | 0 |
| New integrations | 0 |
| Existing functional defaults intentionally changed | 0 |

## Route Inventory

The inventory is derived from every `frontend/app/**/page.tsx`, not from Sidebar configuration. Redirect aliases and the technical `/dev/ui` preview are listed explicitly so that they are not mistaken for missing product pages.

| Route | Functional | Aven | Light | Dark | Responsive | Legacy UI | Action |
|---|---:|---:|---:|---:|---:|---:|---|
| `/` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/accept-invitation` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/billing` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/collections` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/collections/[collectionId]` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/collections/[collectionId]/compare` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/dev/ui` | DEV PREVIEW | YES | PASS | PASS | PASS | NO | KEEP |
| `/finops/ledger` | REDIRECT | N/A | N/A | N/A | N/A | COMPAT | KEEP redirect to `/flow` |
| `/flow` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/forgot-password` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/inventory` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/login` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/mfa-setup` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/opportunities` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/opportunities/collection/[collectionId]` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/opportunities/history-cycles` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/rds/reservations` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/reset-password` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/scans` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/security` | REDIRECT | N/A | N/A | N/A | N/A | COMPAT | KEEP redirect to `/settings/security` |
| `/settings` | REDIRECT | N/A | N/A | N/A | N/A | COMPAT | KEEP redirect to `/settings/security` |
| `/settings/accounts` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/appearance` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/audit` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/billing/profiles` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/https` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/opportunities` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/policies` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/pricing/oci` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/security` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/sessions` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/usage-costs` | YES | YES | PASS | PASS | PASS | NO | KEEP |
| `/settings/users` | YES | YES | PASS | PASS | PASS | NO | KEEP |

Route inventory is protected by `frontend/tests/aven-visual-qa-legacy-cleanup.test.mjs`; adding or removing a page route now requires an explicit update to the closure inventory.

## Light QA

Light remains the primary golden-reference theme. The final pass covers shell canvas/surfaces, navigation, cards, borders, controls, tables, charts, badges/statuses, overlays, loading/empty/error states and page-specific composition. No Light-only fallback or hardcoded dark surface was introduced by Task 24.19.

## Dark QA

Dark uses the same semantic component contract as Light. The final pass checks surface separation, border intensity, readable chart roles, input boundaries, semantic status colors and the absence of hardcoded light backgrounds/black text. No separate Dark-only feature path exists.

## System QA

The existing Theme Engine remains the sole owner of `light | dark | system`. System continues to resolve through `prefers-color-scheme` and runtime media-query changes without introducing a new theme state or page remount contract.

Theme switching is presentation state only: it must not reset feature filters/forms/pagination, mutate domain data or trigger feature-domain refetches. Existing Theme Engine tests remain authoritative for persistence and runtime resolution; browser validation exercises theme switching on the real application shell.

## Responsive QA

The final baseline preserves the Task 24.18 viewport matrix:

- 1280×720
- 1366×768
- 1440×900
- 1600×900
- 1920×1080
- 2560×1440
- representative narrow widths including 1024, 768, 480 and 375 CSS pixels

The design-system scanner and responsive tests continue to reject page-specific historical breakpoint families on migrated Aven pages. Tables may own internal horizontal scroll; page-level horizontal overflow is not acceptable.

## Application Shell QA

Verified contracts:

- one authenticated Application Shell;
- persistent Sidebar and Topbar;
- main content owns page scroll;
- navigation owns its internal scroll;
- collapsed/expanded navigation remains available;
- active/nested navigation continues to derive from shared route configuration;
- theme selector and user menu stay shared shell controls;
- overlay placement remains viewport-aware;
- focus restoration remains part of Dropdown/Tooltip contracts.

The active `legacy-theme-compat.css` file is not an alternate shell. It is a token-backed compatibility layer for still-consumed historical global selectors and therefore remains intentionally imported.

## Page-by-Page QA

### Dashboard

Preserves real dashboard loading, filters/context, KPI semantics, chart semantics, supporting sections and shared Aven page rhythm. Metrics are not recalculated in Task 24.19.

### Billing

Preserved regression contracts:

- no account selected by default;
- Select All initially unchecked;
- zero Cost Explorer query with zero selected accounts;
- filters remain below account selector;
- custom date picker uses the existing anchored overlay behavior;
- page scroll remains owned by the shell main content;
- stacked service chart remains intact;
- actual / estimated / forecast semantics remain unchanged;
- service table and currency behavior remain unchanged.

### Reservations

Coverage, utilization, savings presentation, active/expired/expiring reservations, 30-day expiration semantics and RDS opportunity matching remain backend/domain owned. Task 24.19 does not alter the engine.

### Inventory

AWS/OCI provider context, search, filters, sorting, pagination, technical ARN/OCID identifiers and horizontal table containment remain unchanged.

### Recommendations

Opportunity hierarchy, potential savings, impact, confidence, resource/provider context, filters and decision/archive actions remain unchanged. The final hardcode scanner now covers the complete `app/opportunities` route family rather than only its root page.

### Settings

Only existing settings are represented. Real values, persistence, permissions, secret handling and the existing appearance preference remain unchanged. The final hardcode scanner now covers the complete `app/settings` route family rather than selected subroutes.

### Flow / Collections / Scans

Flow remains the existing FinOps ledger; Collections preserves URL/server-state, polling, retention/detail/compare contracts; Scans preserves operational refresh/navigation. Compatibility redirect `/finops/ledger` continues to redirect to `/flow` instead of carrying duplicate UI.

### Authentication secondary routes

`/login`, `/forgot-password`, `/reset-password`, `/accept-invitation` and `/mfa-setup` continue to use the existing Aven authentication/access composition and authentication contracts. No auth behavior is changed.

## Accessibility QA

The existing Aven primitive and responsive suites continue to cover focus-visible behavior, overlay Escape handling/focus return, semantic form controls, table wrappers and accessible icon/button labels. The final browser pass uses reduced motion and validates overlay geometry/focus return. No animation framework or accessibility bypass is introduced.

## Brand QA

`npm run lint:brand` remains the executable public-brand gate. It scans application/runtime code for DeepOps/NuvemIQ variants and requires every technical occurrence to be explicitly allowlisted with a classification and compatibility reason.

Expected user-visible result:

- visible DeepOps product branding: 0;
- visible NuvemIQ product branding: 0;
- Aven metadata/logo/login/sidebar identity: active.

## Hardcode Audit

The Task 24.19 hardcode audit expands the enforced scanner from selected Recommendations/Settings files to the complete migrated route families:

- `frontend/app/opportunities/**`
- `frontend/app/settings/**`

The gate continues to require:

- new hardcoded colors: 0;
- new hardcoded structural spacing: 0;
- new hardcoded radius: 0;
- new hardcoded typography: 0;
- new ad-hoc responsive breakpoints introduced by this task: 0.

## Legacy CSS Inventory

| Candidate | Classification | Decision | Reason |
|---|---|---|---|
| `frontend/app/legacy-theme-compat.css` | BACKWARD_COMPATIBILITY / VISUAL_STYLE | PRESERVE | Imported by root layout and still owns token-backed compatibility selectors. |
| `frontend/app/styles/tokens/legacy.css` | BACKWARD_COMPATIBILITY | PRESERVE | Imported by the canonical token index and retains compatibility aliases with active consumers. |
| `frontend/app/ui-system.css` | BACKWARD_COMPATIBILITY / VISUAL_STYLE | PRESERVE | Still part of root runtime styling; removal is not proven safe. |
| `frontend/app/task-23-25-layout.css` | BACKWARD_COMPATIBILITY / VISUAL_STYLE | PRESERVE | Still imported by root layout; removal is not proven safe. |
| page-specific CSS modules | ACTIVE_VISUAL_STYLE | KEEP | Current route consumers remain. |

No global CSS file was removed merely because its name appears historical.

## Legacy Component Inventory

No component was deleted without complete consumer proof. Aven UI Primitives, Product Components and Application Shell already own the canonical new layers; historical route/component names that still have imports remain active compatibility or feature implementation, not dead code.

## Legacy Asset Inventory

Official Aven assets remain the runtime source. No asset was removed in Task 24.19 without a complete reference proof. Historical/deployed infrastructure filenames are not treated as visual assets.

## Removed Legacy

| Path | What it was | Replacement | Proof no longer used |
|---|---|---|---|
| `/AVEN_DATA_VISUALIZATION_SYSTEM.md` | Historical duplicate at repository root | `docs/brand/aven/AVEN_DATA_VISUALIZATION_SYSTEM.md` | Both paths had the identical blob SHA; canonical README already referenced only the `docs/brand/aven` copy; Task 24.18 explicitly identified the root copy as historical cleanup debt; closure test requires the root copy to be absent and canonical copy present. |

No runtime component, stylesheet, asset or dependency was removed in this task because no additional candidate satisfied the complete proof-before-delete gate.

## Preserved Compatibility Contracts

Representative intentional historical identifiers remain classified and allowlisted by `frontend/scripts/brand-legacy-allowlist.mjs`:

| Identifier / location | Classification | Reason preserved |
|---|---|---|
| `deepops.theme`, `deepops.sidebar.collapsed` | BACKWARD_COMPATIBILITY | Persisted browser keys must not reset user preferences. |
| `X-DeepOps-Request`, `deepops:session-invalidated` | API_CONTRACT / BACKWARD_COMPATIBILITY | Existing request/session contracts. |
| `nuvemiq_token` cleanup path | BACKWARD_COMPATIBILITY | Existing-session cleanup compatibility. |
| `deepops_account_id` | API_CONTRACT | Serialized billing contract. |
| `NUVEMIQ_*` | ENVIRONMENT_CONTRACT | Deployed environment configuration names. |
| `deepops_session` | BACKWARD_COMPATIBILITY | Existing authentication cookie contract. |
| `/api/v1/deepops-costs` | API_CONTRACT | Existing deployed endpoint contract. |
| `deepops_schema_version`, `deepops_mfa_schema_version` | DATABASE_CONTRACT | Deployed migration/version-table contract. |
| `deepops:totp:v1` | BACKWARD_COMPATIBILITY | Cryptographic context for existing MFA material. |
| `nuvemiq:ignore` | API_CONTRACT | Existing cloud-resource exclusion tag convention. |
| legacy CloudFormation/IAM filenames and IDs | ENVIRONMENT_CONTRACT | Deployment/infrastructure compatibility. |
| `deepops-web` npm package name | INTERNAL_IDENTIFIER | Private package/lockfile identifier, not user-visible branding. |
| historical logger namespaces | INTERNAL_IDENTIFIER | Observability/filter compatibility. |

The objective is zero active legacy visual experience, not zero historical strings at the cost of deployment/API/database compatibility.

## Test Baseline

Before Task 24.19 implementation, the latest Task 24.18/main validation recorded:

- Tests: 354 passed
- Failures: 0
- Skipped: 0
- `npm run lint`: PASS (pre-existing warnings documented by Task 24.18)
- `npm run typecheck`: PASS
- `npm run build`: PASS, 34/34 static pages
- `npm run lint:design-system`: PASS
- `npm run lint:brand`: PASS
- browser visual matrix: 153/153 PASS

No environment variable or test-configuration change was made to create the Task 24.19 implementation branch.

## Final Validation

Final CI and Task 24.19 browser-evidence run identifiers are recorded in the PR once generated. The required final commands are unchanged:

```bash
cd frontend
npm run lint:brand
npm run lint:design-system
npm run lint
npm run typecheck
npm test
npm run build
```

Test configuration changes: **None**.

Environment variable changes: **None**.

Tests skipped to complete Task 24.19: **0**.

Assertions weakened: **0**.

Timeout workarounds: **0**.

Mass snapshot updates: **0**.

## Remaining Functional Debt

No functional debt discovered by this visual closure task is implemented here. Any future functional gap must be handled by a separately scoped task.

## Remaining Visual Debt

None accepted as an active production visual path. Compatibility CSS/tokens listed above are retained because they still have runtime consumers; they are technical migration infrastructure, not a parallel user-facing brand.

Populated production-domain data is not fabricated for visual QA. Browser evidence uses the real isolated application contracts and empty states; data-dense semantics remain covered by the existing feature regression suites and source-level composition contracts.

## Phase 24 Closure

Closure is valid only when the implementation PR CI and final browser evidence are green.

### Visual Regression Gate

```text
All active routes visually audited? YES
Light theme complete? YES
Dark theme complete? YES
System theme complete? YES
1366×768 complete? YES
Unexpected global horizontal overflow? NO
Clipped overlays? NO
Broken page scroll? NO
Visible legacy DeepOps branding? NO
Visible legacy NuvemIQ product branding? NO
```

### Functional Freeze Gate

```text
New feature introduced? NO
New route introduced? NO
New backend endpoint introduced? NO
New database/persistence introduced? NO
New business rule introduced? NO
New analytics introduced? NO
Existing functional defaults changed? NO
```

### Legacy Cleanup Safety Gate

```text
Every removed component had no active consumers? N/A — no component removed
Every removed CSS rule/file was proven unused or replaced? N/A — no CSS removed
Every removed asset was proven unused? N/A — no asset removed
Every removed dependency was proven unused? N/A — no dependency removed
Every removed documentation duplicate had a canonical replacement and no runtime consumer? YES
Compatibility identifiers were preserved when still required? YES
No deployment/API/database contract was renamed solely for branding? YES
```

### Test Integrity Gate

```text
Test configuration changed merely to complete this task? NO
Environment variables changed? NO
Tests skipped? NO
Assertions weakened? NO
Timeouts increased as workaround? NO
Snapshots mass-updated without review? NO
Global mocks modified speculatively? NO
Full frontend npm test passes? PENDING FINAL CI
```

### Design System Gate

```text
New hardcoded colors? NO
New hardcoded structural spacing? NO
New hardcoded radius? NO
New hardcoded typography? NO
New ad-hoc responsive breakpoints? NO
Shared visual problems fixed centrally where applicable? YES
```

### Phase 24 Closure Gate

```text
Is Phase 24 — Aven Visual Transformation complete? PENDING FINAL CI / BROWSER EVIDENCE

Aven branding complete: YES
Aven Design System active: YES
Light theme production-ready: YES
Dark theme production-ready: YES
System theme production-ready: YES
Application Shell production-ready: YES
Dashboard production-ready: YES
Billing production-ready: YES
Reservations production-ready: YES
Inventory production-ready: YES
Recommendations production-ready: YES
Settings production-ready: YES
Flow / existing secondary pages production-ready: YES
Data Visualization System production-ready: YES
Responsive consistency complete: YES
Legacy visual layer removed where safe: YES
Frontend full test suite green: PENDING FINAL CI
Production build green: PENDING FINAL CI
```

Do not change the three pending closure fields to `YES` until the final implementation CI and visual-evidence run are green.
