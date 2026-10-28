# Aven Flow & Secondary Pages

## Scope

Task 24.16 migrates only existing, functional product surfaces that remained outside the Aven page migration after Tasks 24.9–24.15.

```text
Existing product behavior
↓
Preserve
↓
Aven visual migration
```

No route, API, persistence model, workflow state, business rule, permission rule or production mock was created to complete navigation.

The primary migration is `/flow`. The secondary existing surfaces included after router and data-source audit are `/collections`, `/collections/[collectionId]`, `/collections/[collectionId]/compare`, and `/scans`.

## Functional Foundation Gate

| Route | Route exists | Current UI exists | Real data source exists | Actions exist | Auth/permission contract known | Migratable without invented logic | Task 24.16 action |
|---|---:|---:|---:|---:|---:|---:|---|
| `/flow` | YES | YES | YES | YES | YES | YES | MIGRATE |
| `/collections` | YES | YES | YES | YES | YES | YES | MIGRATE |
| `/collections/[collectionId]` | YES | YES | YES | YES | YES | YES | MIGRATE |
| `/collections/[collectionId]/compare` | YES | YES | YES | YES | YES | YES | MIGRATE |
| `/scans` | YES | YES | YES | read/navigation | YES | YES | MIGRATE |
| `/finops/ledger` | YES | redirect only | N/A | N/A | inherited | YES | KEEP redirect |
| `/security` | YES | redirect only | N/A | N/A | inherited | YES | KEEP redirect |

The Flow foundation is backed by the existing `/finops/flow/*` query endpoints and `/finops/ledger/*` mutation endpoints. Collections are backed by existing collection list/detail/options/comparison contracts and the existing manual collection mutation. Scans use the existing scan/account/collection APIs.

No missing dependency was filled with a mock or new backend work.

## Route Inventory

| Route / family | Functional status | Aven status entering 24.16 | 24.16 decision |
|---|---|---|---|
| `/` | functional | migrated in 24.10 | KEEP |
| auth routes | functional | migrated previously | KEEP |
| `/billing` | functional | migrated in 24.11 | KEEP |
| `/rds/reservations` | functional | migrated in 24.12 | KEEP |
| `/inventory` | functional | migrated in 24.13 | KEEP |
| `/opportunities` and existing opportunity routes | functional | migrated in 24.14 | KEEP |
| `/settings/*` | functional existing settings | migrated in 24.15 | KEEP |
| `/flow` | functional | legacy visual composition | MIGRATE |
| `/collections` | functional | legacy/transitional composition | MIGRATE |
| `/collections/[collectionId]` | functional | legacy/transitional composition | MIGRATE |
| `/collections/[collectionId]/compare` | functional | legacy/transitional composition | MIGRATE |
| `/scans` | functional | legacy composition | MIGRATE |
| `/finops/ledger` | redirect to `/flow` | no independent UI | KEEP |
| `/security` | redirect to `/settings/security` | no independent UI | KEEP |
| `/dev/ui` | technical design-system preview | Aven technical surface | KEEP |

No menu label or planned product concept was treated as proof that a route or feature exists.

## Migrated Routes

MIGRATED:
- `/flow`
- `/collections`
- `/collections/[collectionId]`
- `/collections/[collectionId]/compare`
- `/scans`

KEPT AS-IS:
- `/finops/ledger` → `/flow`
- `/security` → `/settings/security`
- routes already migrated by Tasks 24.9–24.15
- `/dev/ui`

OUT OF SCOPE — FUNCTIONALITY DOES NOT EXIST:
- no additional route was added from navigation concepts or future product planning
- no missing backend capability was implemented to justify a new page

DEPRECATED / REVIEW LATER:
- `/finops/ledger` remains a legacy compatibility alias and should only be removed after consumer verification
- `/security` remains a legacy compatibility alias and should only be removed after consumer verification

## Out-of-Scope / Nonexistent Routes

Task 24.16 does not create pages for features that are absent from the router or lack real data/action contracts. A placeholder or desired navigation destination is not sufficient foundation. Any future capability must receive its own domain/backend task before a visual page task.

## FinOps Flow Architecture

The existing Flow remains a financial ledger experience, not a workflow redesign:

```text
/flow page
├── context filters
├── /finops/flow/options
├── /finops/flow/summary
├── /finops/flow/timeseries
├── /finops/flow/breakdowns
├── /finops/flow/entries
├── POST /finops/ledger/manual
└── POST /finops/ledger/{id}/reverse
```

The Aven migration changes page hierarchy, controls, surfaces, table composition, financial display, status presentation and dialogs. Query/mutation paths and payload semantics remain feature-owned.

The page uses the official `PageHeader`, `Section`, `FilterBar`, `MetricCard`, `ChartCard`, `DataState`, `CurrencyDisplay`, `ProviderBadge`, `StatusIndicator`, Aven UI table primitives and Aven dialogs.

## Existing Flow States

Flow is not modeled as a Kanban/state-machine workflow in the current product, so Task 24.16 does not invent approval or progress stages.

Existing persisted flags are presented without changing their meaning:

- normal ledger entry → `Registrada`;
- `is_reversed` → `Revertida`;
- `is_reversal` → `Reversal`.

These are presentation mappings over existing ledger state, not a new backend status contract.

## Existing Flow Actions

Preserved actions:

- register a manual ledger movement through `POST /finops/ledger/manual`;
- reverse an eligible movement through `POST /finops/ledger/{id}/reverse`;
- inspect persisted movement details;
- navigate to an associated real opportunity when `opportunity_id` exists;
- paginate/filter existing entries.

Manual movement validation remains local to the existing form contract, including positive decimal normalization, non-future effective date, account requirement, description requirement and idempotency request ID.

Dead CTAs introduced: **0**.

## Filters

The existing Flow filters remain:

- period preset/custom date range;
- provider;
- account;
- currency;
- financial basis/periodicity;
- source;
- entry type for movements;
- text search for movements;
- page.

Mixed currencies remain separated. `Todas (sem consolidar)` explicitly prevents a fabricated cross-currency total.

Collections keeps its existing provider/account/status/date/analyzer-version filters and URL-state model. No new filter semantics were introduced.

## Tables / Cards

Flow summary values use `MetricCard` only for metrics already returned by the backend: recognized savings, reallocated amount, net adjustments and balance.

The Flow movements table uses official table primitives while retaining the same entry fields and actions. Collections preserves its existing dense operational workspace and comparison structures under a scoped Aven compatibility layer so query orchestration and retention behavior are not rewritten. Scans uses official Aven table/status/state components directly.

## Resource / Financial Context

Flow provider context uses `ProviderBadge`. Monetary values use `CurrencyDisplay` with the currency supplied by the backend/entry. No implicit currency conversion or consolidation is performed.

The existing custom Flow time-series remains data-equivalent and consumes established Aven chart semantic tokens. Task 24.16 does not introduce a new charting abstraction or new analytical metric; system-level standardization belongs to Task 24.17.

## Loading

- Flow analytics and movement-table loading are represented independently with `DataState`.
- Collections route-level Suspense fallbacks use Aven `DataState`.
- Collections preserves its existing keep-previous-data and conditional 15-second polling behavior while a run is active.
- Scans preserves its existing 10-second refresh interval and clears the interval on unmount.

## Empty

Empty states distinguish real no-data conditions from loading/error conditions. Flow never fabricates sample ledger entries. Collections retains the distinction between no history, no filtered results and an empty later page. Scans reports that no analysis has run only after its initial load completes.

## Error

Flow analytics errors do not replace the movement-table error state; the two functional regions can fail independently. Mutation errors remain in their corresponding dialogs and no optimistic false-success state is retained after a failed request.

Collections keeps existing list/detail/options error behavior. Scans surfaces refresh errors through the official `Alert` while retaining previously loaded operational data when present.

## Light Theme

All new/refactored Task 24.16 visual CSS consumes semantic/foundation/component tokens. No route-specific Light palette is defined.

## Dark Theme

The same tokenized composition resolves through the Dark semantic mapping. No separate Dark component implementation or raw color override is introduced.

## Responsive Behavior

The Flow summary grid, breakdowns, dialogs, filters and detail grid use tokenized responsive composition. The primary table owns horizontal overflow rather than the page/Application Shell. Collections similarly confines wide operational tables to their table wrapper. Scans uses the shared table primitive wrapper.

The Application Shell remains the single page-scroll owner; no Task 24.16 page adds `height: 100vh` or page-level `overflow: hidden`.

## Accessibility

The migration preserves semantic headings, labels, table header scopes, dialog labeling, native form controls, button/link roles, status labels and keyboard-operable controls. Aven primitives provide focus-visible behavior and dialog semantics. Existing collection table regions remain keyboard focusable where horizontal scrolling is required.

## Performance

No query or mutation was added for styling. Theme changes are absent from Flow/Collections/Scans query signatures and cannot trigger domain refetches.

Preserved refresh behavior:

- Collections: 15-second polling only when a collection is running and only while the document is visible;
- Scans: existing 10-second polling;
- Flow: request changes are driven by existing functional filters/reload after successful mutation.

## Test Baseline

Baseline source: `main` commit `1e3cd9941d0fab11adf1311b3b134e4ee197b0a9`, immediately after PR #125.

GitHub Actions CI run `40706027295` completed successfully before Task 24.16 implementation. The frontend job passed `npm ci`, `npm run lint:brand`, `npm run lint:design-system`, `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build`.

Before implementation:
- Suites: 0 (`node:test` aggregate)
- Tests: **334 passed**
- Failures: **0**
- Skipped: **0**

After Task 24.16, CI run `40710507919`, frontend job `122894183530`:
- Suites: 0 (`node:test` aggregate)
- Tests: **343 passed**
- Failures: **0**
- Skipped: **0**
- Cancelled: **0**
- Todo: **0**

The same frontend job also passed:

```text
npm run lint:brand
npm run lint:design-system
npm run lint
npm run typecheck
npm test
npm run build
```

The first Task 24.16 CI run exposed five obsolete visual assertions tied to the legacy Flow CSS/empty-state wording. The production query/mutation contracts were not changed to satisfy those tests. The tests were updated to validate the new Aven visual contract while retaining strong assertions for API paths, scroll ownership, responsive behavior, chart geometry, table containment and ledger semantics.

Failures introduced: **0**.

Tests skipped to make task pass: **0**.

## Test Isolation Rules

Task 24.16 does not change Jest/Vitest/Node test setup, package test scripts, global mocks, environment defaults, auth defaults, theme defaults or CI environment.

The production timers touched by migrated secondary surfaces are explicitly cleaned up on unmount. No Task 24.16 test mutates `process.env`, `localStorage`, `sessionStorage`, system time, fake timers, `matchMedia`, location or global fetch state.

Test configuration changes: None.

Environment variable changes: None.

## Legacy Migration

`frontend/components/page-header.tsx` is retained as a compatibility bridge but now composes the official Aven `PageHeader`, allowing existing secondary consumers to migrate without duplicating page-header visuals.

Collections intentionally uses a route-scoped Aven compatibility layer around the existing functional workspace rather than rewriting its query orchestration in a visual task. The legacy `/finops/ledger` and `/security` routes remain redirects. No aggressive global legacy deletion is performed; broad cleanup remains Task 24.19 territory.

## Existing Feature Gate

Were any new features created to complete the Aven navigation? NO

Were any fake routes created? NO

Were any APIs created solely to support visual ideas? NO

Were any mock datasets shipped as production behavior? NO

Were any dead CTAs introduced? NO

Were any missing backend features silently implemented? NO

## Test Integrity Gate

Was test configuration changed merely to make tests pass? NO

Were environment defaults changed merely for tests? NO

Were tests skipped? NO

Were assertions weakened without a contract change? NO

Were global mocks changed speculatively? NO

Are environment/global changes restored after tests? YES — Task 24.16 introduces no mutable global test state.

Does the complete frontend test suite pass? YES — **343/343**.

## Functional Regression Gate

### Flow

- Existing data still loads? YES
- Existing filters still work? YES
- Existing actions still work? YES
- Existing state/ledger semantics preserved? YES
- Permissions preserved? YES — no permission/auth contract changed
- History preserved? YES
- Financial/resource context preserved? YES
- Theme switch causes domain refetch? NO

### Collections

- Existing data still loads? YES
- Existing filters still work? YES
- Existing manual collection action still works? YES
- Existing comparison behavior preserved? YES
- Permissions preserved? YES
- Polling/retention semantics preserved? YES
- Theme switch causes domain refetch? NO

### Scans

- Existing data still loads? YES
- Existing polling preserved? YES
- Existing collection/compare navigation preserved? YES
- Existing status/error context preserved? YES
- Theme switch causes domain refetch? NO

## Hardcoding / Brand Gates

Task 24.16 expands `lint:design-system` coverage to Flow, Collections, Scans, the PageHeader compatibility bridge and ManualCollectionLauncher.

Final CI result:

```text
Aven hardcode gate: PASS
Hardcoded colors: 0
Hardcoded structural spacing: 0
Hardcoded border radius: 0
Hardcoded typography: 0
```

`npm run lint:brand` also passes. No new visible DeepOps or NuvemIQ branding is introduced.

## Task 24.17 Readiness

Is Task 24.17 ready to start? YES

All existing primary pages migrated to Aven: YES

Flow migrated: YES

Existing secondary pages migrated: YES

No nonexistent feature was created: YES

Frontend full test suite green: YES

Test environment stable: YES

Light/Dark/System stable: YES

Data visualization consumers identified: YES

Existing charts can be standardized without creating new analytics: YES

The identified visualization consumers include the existing Flow time series, Billing visualizations and other already-functional metrics/charts from prior migrations. Task 24.17 may standardize presentation only; it must not invent analytical data to fill charts.
