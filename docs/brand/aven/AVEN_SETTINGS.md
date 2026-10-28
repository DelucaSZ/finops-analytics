# Aven Settings

Task 24.15 migrates the existing Settings experience to the Aven visual architecture without creating new product capabilities.

The governing rule is:

```text
Existing functionality
↓
Aven visual migration
```

Never:

```text
Visual idea
↓
Invent missing functionality
```

## Scope

The route family remains `/settings/*`. Existing deep links, authorization boundaries, API contracts, persistence mechanisms, validation rules and mutation semantics are preserved.

The Settings information architecture continues to be route-based because the product already exposes multiple independent settings areas. The shared layout now presents those routes with the official Aven Tabs primitive while the URL remains the source of truth.

Task 24.15 does not add backend endpoints, tables, providers, integrations, credentials, notifications, webhooks, preferences or administrative capabilities.

## Functional Foundation Gate

Every visible Settings destination was audited before redesign.

The required questions were:

```text
Route exists?
Current UI exists?
Real data source exists?
API/query exists?
Persistence exists?
Required mutations exist?
Permission/auth contract exists?
Loading/error semantics are known?
Can this setting be migrated without mocks or invented business logic?
```

Read-only areas treat write API/persistence as `N/A` rather than manufacturing a mutation. Appearance uses the existing Theme Engine and its browser persistence contract instead of a backend API.

All destinations kept in navigation have an existing functional foundation. No destination was added merely to complete a Settings taxonomy.

## Existing Settings Inventory

| Setting / section | UI exists | Read source | Write API / action | Persistence | Permission contract | Action |
| --- | --- | --- | --- | --- | --- | --- |
| Appearance | YES | Theme Engine state | `setTheme()` | existing Theme Engine browser persistence | authenticated user | MIGRATE |
| Cloud accounts | YES | `/cloud-accounts`, capabilities, account detail | existing create/update/test/scan actions | backend | role + provider capabilities | MIGRATE |
| Policies | YES | global/account policy APIs | existing PUT/DELETE policy actions | backend | admin edit / permitted read | MIGRATE |
| My security | YES | `/auth/mfa/status` | `/auth/change-password`, `/auth/reauthenticate`, existing MFA workflow | backend/security services | current authenticated user | MIGRATE |
| Sessions | YES | `/auth/sessions` | DELETE session, `/auth/logout-all` | backend sessions | current authenticated user | MIGRATE |
| Users | YES | `/users`, `/auth/me`, user-session endpoints | existing invite/create/update/deactivate/reactivate/reset/MFA-admin actions | backend | admin | MIGRATE |
| Audit | YES | `/audit`, `/audit/users` | N/A — read-only | persisted audit data | admin | MIGRATE |
| HTTPS | YES | `/tls` | `/tls/validate`, `/tls/apply` | existing TLS service/files | admin + reauthentication where required | MIGRATE |
| OCI Pricing | YES | `/pricing/oci`, `/pricing/oci/meta`, audit/history | existing create/update/deactivate | backend pricing persistence | admin | MIGRATE |
| Billing Profiles | YES | existing Billing Profile list API | create/update/default/deactivate | backend | admin | MIGRATE |
| Usage and costs | YES | existing CloudWatch usage/cost/account/collection queries | N/A — analytical read-only workflow | existing usage/cost persistence and provider data | admin | MIGRATE |
| Opportunity retention/history | YES | `/settings/opportunity-policy` | preview + PUT existing policy | backend with optimistic version contract | admin | MIGRATE |

The `/settings` route remains a redirect to an existing Settings destination and does not become a second landing-page feature.

## Not Implemented Because Functionality Does Not Exist

The following were deliberately not introduced:

- future Integrations catalog;
- Notifications preferences;
- Webhooks;
- API-token management;
- language preference;
- timezone preference;
- currency preference;
- density preference;
- new AWS/OCI credential fields;
- new provider types;
- new cloud-account onboarding flow;
- new invitation/user-management semantics beyond the existing Users area;
- new MFA actions beyond the existing security contracts;
- new billing configuration outside existing Billing Profiles;
- new feature flags;
- `.env` editing;
- new authentication/session policy controls.

No empty tab, dead CTA or mocked setting was added for these concepts.

## Information Architecture

The shared Settings layout is:

```text
Aven Application Shell
↓
Existing Settings route navigation
↓
Current route content
↓
Existing read / mutation / persistence contracts
↓
Aven feedback
```

The route remains authoritative. Selecting a Settings tab pushes the existing route; reloading or deep-linking reconstructs the selected area from the pathname.

The admin-only route contract is preserved. Hiding navigation is not considered authorization; backend permissions remain authoritative.

## Navigation / Tabs

The existing role-aware navigation contract in `frontend/lib/settings-navigation.mjs` is retained.

Common destinations:

- Appearance;
- Accounts;
- Policies;
- My security;
- Sessions.

Admin destinations:

- Users;
- Audit;
- HTTPS;
- OCI Pricing;
- Billing Profiles;
- Usage and costs;
- Opportunity retention/history.

The shared Settings layout now uses the official Aven `Tabs`, `TabsList`, `TabsTrigger` and `TabsContent` primitives. The tab value is derived from the current pathname and navigation continues through Next.js routing.

The `/auth/me` role bootstrap is no longer coupled to pathname changes. Navigating between Settings subroutes therefore does not refetch the current user solely because the active tab changed.

## Sections

Aven `PageHeader` and `Section` are the preferred composition boundary for migrated Settings pages.

Task 24.15 directly migrates common/high-risk patterns in Appearance, My security, Sessions and Billing Profiles. Large pre-existing administrative workflows retain their business components and domain-specific layout while the shared Settings scope supplies the Aven semantic surface/control contract. This avoids rewriting provider, account, pricing, retention, audit or TLS business logic merely to change visual composition.

## Forms

New/refactored form composition uses official primitives such as:

- `Input`;
- `Select`;
- `Checkbox`;
- `Button`;
- `Alert`;
- `Table`;
- `Tabs`.

No `SettingsInput`, `SettingsButton`, `SettingsSwitch` or parallel local primitive family was introduced.

Existing large workflows that are not behaviorally rewritten remain under a scoped tokenized compatibility bridge so their native controls adopt Aven semantic surface, border, focus, typography and density contracts without changing payloads or handlers.

## Validation

Existing backend/domain validation remains authoritative.

Task 24.15 does not introduce client-side validation that conflicts with API contracts. Existing required fields, password limits, Billing Profile constraints, OCI pricing validation, policy ranges, HTTPS PEM rules and cloud-account capability validation are preserved.

## Persistence

Save semantics remain feature-owned:

- explicit-submit workflows still require explicit submit;
- Theme Engine retains its existing persistence behavior;
- no autosave is introduced;
- no optimistic success is displayed before a real mutation succeeds;
- existing reload/persistence semantics remain backed by the current APIs/storage.

A successful mutation may update local state/refetch through the mechanism the feature already used. A failed mutation does not leave a success message claiming persistence.

## Permissions

Settings preserves both route-level presentation and server-side authorization.

The shared layout still distinguishes common and admin-only destinations. Feature-level role/capability checks in Accounts, Policies, Users and other administrative workflows remain in place.

Task 24.15 does not convert a real 403 contract into a fake disabled form and does not treat hidden buttons as authorization.

## Secrets

Existing sensitive-data behavior is preserved.

Security password fields continue to use `type="password"`.

HTTPS custom certificate configuration continues to keep private-key input client-side only for the existing submission flow; the key is not returned by the API and is cleared after successful apply. Task 24.15 does not invent masked secret values or resubmit placeholder text as a real secret.

Cloud-account credential handling remains owned by the existing account workflow. No new localStorage persistence for credentials is introduced.

## Cloud Account Configuration

The existing Accounts workflow remains the sole Settings owner of current cloud-account configuration.

Existing AWS/OCI capability checks, provider-specific fields, external-ID behavior, update semantics, connection test and scan actions are preserved. Task 24.15 does not add unsupported provider fields or move cloud credentials into a new persistence mechanism.

## Status

Operational status uses existing Aven semantic components where a route is refactored, including `StatusIndicator` for Billing Profile enablement.

Status remains textually explicit and is not encoded by color alone.

## Loading

The shared Settings bootstrap uses Aven `Skeleton` instead of fake default values.

Migrated tables use explicit loading rows/states. Existing larger workflows retain their established request lifecycle and are visually normalized through the Settings Aven scope.

## Error

The shared Settings role bootstrap and migrated feature errors use `Alert`.

Raw exceptions are not intentionally exposed by new Task 24.15 code. Existing feature-safe API error messages remain preserved.

## Success

Success is displayed only after a real mutation resolves. Billing Profile success, security confirmation and equivalent existing workflows keep their current persistence boundary.

Critical state remains visible in the section/table after refetch rather than relying only on transient notification copy.

## Light Theme

Settings consumes Aven semantic surface, text, border, focus and status tokens. No Settings-specific Light palette exists.

The intended result is clean, structured and moderately dense.

## Dark Theme

Dark uses the same component tree and semantic roles. Input boundaries, technical metadata and statuses remain readable without neon/glow styling.

## Theme Engine

Appearance reuses the official Theme Engine and `ThemeSelector`.

Supported preferences remain exactly:

```text
Light
Dark
System
```

Task 24.15 does not create a second theme store, localStorage key, media-query resolver or DOM theme mutation path.

Changing theme remains presentation-only and must not reset a Settings form, selected route or server state.

## Responsive Behavior

Settings is desktop-first but usable at narrow widths.

The shared navigation has horizontal containment instead of forcing page-level overflow. Form grids and action rows progressively stack. Tables keep their own containment through the official Table primitive or existing domain table wrapper.

The Application Shell remains the page scroll owner; Task 24.15 does not introduce a Settings `100vh`/`overflow: hidden` scroll container.

Validation targets remain:

```text
1280
1366
1440
1600
1920
2560
```

plus narrower notebook/tablet/mobile widths.

## Accessibility

The migration preserves/adds:

- official Tabs keyboard semantics for route navigation;
- one page-level heading through migrated `PageHeader` composition;
- real labels from `Input`/`Select`/`Checkbox` primitives;
- `aria-invalid`/described-by behavior provided by form primitives;
- semantic Table markup;
- alert/status live-region semantics;
- focus-visible semantic tokens;
- native button semantics;
- no placeholder-only labels in refactored forms.

Existing complex dialogs/security components continue to own their established focus and proof behavior.

## Performance

The shared role bootstrap no longer runs on every Settings pathname change.

Task 24.15 does not add Settings data APIs or background polling. Existing feature request/cache behavior remains unchanged.

A single Save click continues to call the existing mutation once through the feature handler. Theme changes are not included in feature query signatures.

## Legacy Migration

`settings-layout.module.css` was rebuilt around Aven semantic/foundation/component tokens. A small `settings-page.module.css` owns page composition only.

The migration deliberately does not delete unrelated global legacy CSS that is still used by pages outside Settings.

The hardcode scanner covers the new/refactored Settings shell, composition modules and directly migrated pages. Required result for that migration surface:

```text
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

## Functional Regression Gate

```text
Existing settings still load? YES
Existing editable settings still save? YES
Persistence preserved? YES
Permissions preserved? YES
Secrets handling preserved? YES
Existing provider/account configuration preserved? YES
Theme setting still uses official Theme Engine? YES
Theme switch causes configuration reset? NO
New functional settings invented? NO
```

These statements describe the retained contracts in the implementation; runtime CI/browser smoke remains the verification mechanism for deployed behavior.

## Invented Feature Gate

```text
Were any new settings created only for this redesign?
NO

Were any new backend APIs created to support visual ideas?
NO

Were any new database/persistence models created to support this task?
NO

Were any fake controls or dead CTAs introduced?
NO

Were any missing settings moved into this task through mocks?
NO
```

Final scope counters:

```text
Mocked settings: 0
Fake controls: 0
Dead CTAs: 0
Invented APIs: 0
Invented persistence: 0
Invented features: 0
```

## Task 24.16 Readiness

Task 24.16 is **Aven Flow + existing secondary pages** and inherits the same Functional Foundation Gate.

```text
Is Task 24.16 ready to start? YES
Golden page composition ready: YES
Application Shell ready: YES
Form patterns ready: YES
Table patterns ready: YES
Status/action patterns ready: YES
Loading/Empty/Error ready: YES
Responsive patterns ready: YES
Functional Foundation Gate documented: YES
24.16 can proceed without inventing missing features: YES
```

Task 24.16 may migrate only routes, features, flows, actions and data that already exist functionally.
