# Aven visual regression guardrails

Task 24.38 turns the visual decisions from Phase 24 into executable contracts. The goal is to stop accidental regressions without freezing intentional Design System evolution.

## Strategy

The current frontend has no browser E2E or screenshot-regression harness. It uses Node's built-in `node:test`, ESLint, TypeScript, Next.js build validation, and static source-contract tests. Task 24.38 therefore strengthens the existing stack instead of introducing a second, high-maintenance browser stack without an authentication/test-data harness.

Coverage is split by failure mode:

| Category | Guardrail |
| --- | --- |
| Branding | Official asset existence, surface-aware `AvenLogo`, Login/AuthLayout and Sidebar contracts |
| Tokens | Static hardcode gate for color, spacing, radius and typography |
| Surface | Existing Surface semantic-contract tests in the Phase 24 suite |
| Layout | PageContainer/FilterBar contracts, shrink-safe shell/page/table source contracts |
| Filters / Forms | Shared FilterBar contract plus Inventory uniqueness/composition regression tests |
| Tables | Semantic critical-cell kinds, controlled table overflow, Opportunities Impact/Confidence contract |
| Responsive | Existing container-query/shell shrink-safety tests from Task 24.37 plus overflow ownership contracts |
| Theme | Existing Light/Dark/System engine, persistence/bootstrap and surface-aware branding tests |
| Runtime | Typecheck, unit/contract tests, Next.js build; true browser console/hydration checks remain a future E2E concern |

## Static design-system gate

`npm run lint:design-system` continues to scan the Phase 24 migrated scopes in full.

`npm run lint:design-system:changed -- <base-ref>` adds the no-regression-budget rule. It scans only lines added under `frontend/app` and `frontend/components` relative to the supplied base ref. This means historical debt is not silently accepted as new debt, while a PR cannot increase it.

The scanner rejects direct visual values such as:

- hex, `rgb()`, `rgba()`, `hsl()` and `hsla()` colors;
- arbitrary padding, margin and gap values;
- large arbitrary Tailwind width/height values that are likely to be layout decisions rather than icon sizing;
- arbitrary border radius;
- arbitrary font size, family, weight, line-height and letter-spacing.

Failure output includes file, line, category, matched value and the expected Aven-token remediation.

### Allowlist

The allowlist is `frontend/scripts/visual-guardrail-allowlist.mjs`.

Rules:

1. entries are exact paths; wildcards are not allowed;
2. every entry requires a written reason;
3. prefer semantic tokens or shared components before adding an exception;
4. third-party/technical exceptions must be as narrow as possible;
5. an allowlist change must be reviewed as an architectural change, not as a way to make CI green.

The initial allowlist contains only `app/globals.css`, because it is the token/theme definition source where raw values are expected to originate.

## Regression contracts

The focused suite is:

```bash
cd frontend
npm run check:visual-regression
```

It protects, among other contracts:

- official Aven assets and `on-dark` / `on-light` selection;
- Login branding through `AuthLayout` + `AvenLogo`, not a textual `AVEN` facsimile;
- Sidebar wordmark/mark and persisted expanded/collapsed state;
- Inventory: one Search, Provider, Account, Region, Resource type, Service, Lifecycle and Presence filter, plus one Clear filters action, all inside the shared FilterBar;
- shared PageContainer and FilterBar semantic regions;
- Opportunities `Impacto / confiança` rendered inside the non-clipping `statusStack`;
- table-owned horizontal overflow and semantic critical cell kinds (`status`, `badge`, `currency`, `actions`);
- shell/page/table shrink-safe structural contracts;
- negative fixtures proving the static scanner actually fails controlled regressions.

Existing Phase 24 tests remain part of `npm test`, including filter/form layout, table density, theme engine, responsive/theme parity, branding assets, UI primitives and page-specific polish contracts.

## Responsive and theme coverage

The source-contract suite protects responsive behavior through container queries and shrink-safe layout primitives rather than exact pixel coordinates. Task 24.37 already verifies the shell, page composition, Inventory, table overflow, overlays, and Light/Dark/System theme engine.

Priority browser widths for any future browser harness are:

- 1920;
- 1440;
- 1366;
- 1280;
- 1024;
- 768 for a reduced page subset.

The current repository does **not** claim runtime viewport execution at those widths. In particular, `document.documentElement.scrollWidth <= document.documentElement.clientWidth` requires a real browser and is not simulated by source tests.

## Screenshot regression status

Screenshot baselines were intentionally **not** added in Task 24.38. There was no Playwright/Cypress installation, browser provisioning, deterministic authenticated fixture layer, or screenshot ownership convention to build on. Adding Playwright only to manufacture screenshots would also require solving auth, API interception/fixtures, browser binaries and CI artifacts in the same task, which would create a fragile parallel test platform.

When a browser harness is introduced, the first visual baselines should be Login, Dashboard, Opportunities, Inventory, Billing and Settings, with at least one collapsed Sidebar capture and representative Light/Dark coverage. The initial golden width should be 1366, adding 1920 only where wide-layout behavior materially differs.

### Baseline update procedure

A screenshot baseline must never be updated automatically just to make CI green. For an intentional visual change:

1. inspect the diff and confirm the product change is expected;
2. review the rendered actual/diff output;
3. update only the affected baseline;
4. commit the baseline with the intentional UI change in the same PR;
5. document why the visual contract changed.

Mask only genuinely dynamic elements; never mask large regions that should be protected.

## Adding a new page or component

For a new shared visual component, add a semantic contract test and keep it free of raw visual values. For a page with filters/tables, consume the shared Aven architecture and add a focused regression assertion for the page-specific risk.

Once a browser E2E harness exists, add a structural smoke test for the route before adding a screenshot. Browser tests should use deterministic fixtures, no real AWS/OCI accounts, state-based waits rather than sleeps, disabled animations for screenshots, and triaged console/runtime errors.

## Local commands

```bash
cd frontend
npm ci
npm run lint:brand
npm run lint:design-system
npm run check:visual-regression
npm run lint
npm run typecheck
npm test
npm run build
```

To emulate the PR-only new-lines gate:

```bash
cd frontend
npm run lint:design-system:changed -- <base-ref-or-sha>
```

There is intentionally no `test:e2e` or `test:visual` script yet because the repository has no functional browser test stack. Do not add placeholder commands that imply coverage which is not actually executed.
