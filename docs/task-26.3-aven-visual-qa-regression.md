# Task 26.3 — Aven Visual QA & Regression Validation

## Scope and integration baseline

- Task 26.1 — PR [#177](https://github.com/DelucaSZ/finops-analytics/pull/177), merged to `main`.
- Task 26.2 — PR [#178](https://github.com/DelucaSZ/finops-analytics/pull/178), merged to `main`.
- Integration commit: `f51bb77aa951197de78a2e736c1135d857a9a315`.
- The baseline CI workflow completed successfully: [run 43031964658](https://github.com/DelucaSZ/finops-analytics/actions/runs/43031964658).
- QA branch: `task/26.3-aven-visual-qa-regression-validation`.
- No backend, authentication, business-rule or FinOps calculation changes belong to this task.

## Browser validation matrix

The automated suite is a **real Chromium browser** running against the production Next.js build with a **synthetic, intercepted API backend**. It is not a production end-to-end test.

| Dimension | Coverage | Validation |
| --- | --- | --- |
| Protected routes | All 24 inventoried authenticated routes | Navigate, render, locale, browser errors, original/native-select regressions, interactive dropdowns, avatar |
| Locale | `pt-BR`, `en-US` | Both languages for all protected routes |
| Theme | `light`, `dark`, `system` | Real computed HTML theme and preference; system tested with dark OS preference and light OS preference in a separate baseline |
| Width | 1440, 768, 390 px | Actual Chromium viewports; document overflow, menu geometry, user avatar |
| Sidebar | Expanded, collapsed | Expanded on the default route audit and Flow/Billing; collapsed on desktop matrix. Desktop sidebar must be hidden at <=850 px |
| Select | Single selection | Combobox/listbox ARIA, ArrowDown, Escape, surface styling, repositioning, viewport clipping |
| Multi / searchable | Billing AWS accounts | Search input, checkbox options, dropdown open/close |
| Billing custom | 2026-10-01 through 2026-10-31 | Date fields, underlying period value, billing summary request, AWS account IDs |
| Avatar | Normal and long identity | ~36 px, 1:1 geometry, radius, flex shrink, clipping, ellipsis, menu and Escape |
| Evidence | JSON and screenshots | CI uploads `aven-phase26-visual-qa` artifact even when validation fails |

All pages are *visited in the browser*, rather than inferred from code-search matches. The suite does not exercise disabled controls, every individual option or every possible state combination; those are documented coverage limitations.

## Commands and infrastructure

```bash
cd frontend
npm ci
npm run lint:brand
npm run lint:design-system
npm run lint:i18n
npm run lint:i18n:references
npm run audit:i18n:baseline
npm run lint
npm run typecheck
npm test
npm run build
npm install --no-save --package-lock=false playwright-core@1.57.0
npm run smoke:i18n:authenticated
npm run test:aven:phase26
```

The CI also runs Python backend checks, pytest, security checks and the production web image build as configured in `.github/workflows/ci.yml`. The new browser command is wired into that existing workflow.

## Findings and corrections during Task 26.3

- Initial Chromium run [43034149770](https://github.com/DelucaSZ/finops-analytics/actions/runs/43034149770): **68 passed, 2 failed, 0 blocked**, from 70 browser cases. Both failures occurred on `/collections` (one in each locale) while Playwright attempted to scroll a combobox inside a **hidden tab** into view. This is an **automation selector defect**, not a confirmed application regression.
- Correction: scope actionable dropdown tests to `:visible` controls; preserve the separate structural assertion against native `<select>` tags in all mounted page content.
- Add regression guard against hidden-tab interaction and ensure blocked synthetic API fixtures fail the Phase 26 CI gate instead of silently passing.
- Rerun the dedicated Chromium matrix after the correction; do not count the first run as PASS.

## Integrated QA signoff — 11 Nov 2026

The following test outcome is based on saved JSON artifacts, not a static-code assertion:

- [Authenticated full i18n E2E artifact](https://github.com/DelucaSZ/finops-analytics/actions/runs/43034149729): **65 passed, 0 failed, 0 blocked** (previous integrated build).
- Phase 26 extended Chromium artifact from commit `ceca5a6d987ca5fd774ef8e62a32a7bae30a50af`: **76 passed, 0 failed, 0 blocked, 0 not run**.
- Coverage totals: 48 authenticated route visits, 18 integrated Billing/avatar theme-viewport-locale scenarios, 4 large-list multi/single-select interactions, 2 disabled-select cases, 2 Flow cases and 2 default Billing cases.
- Inspected screenshot contact sheets from the 26 generated captures, including dark/light, PT-BR/EN-US, desktop, tablet, mobile and expanded multi-select. No obvious clipping, oval avatar or bleeding overlay was observed in those samples.
- Regressions caught during QA: selecting a dropdown in a hidden tab (test selector defect), and complex overlay-opacity issues (fixed through shared semantic popover surface tokens). Synthetic account fixtures and extended assertions were corrected and rerun.
- Shared Aven select now uses an opaque semantic popover background in both Light and Dark themes; avatar remains a initials-only 36×36 circle.
- The last branch commit and associated workflows must remain green before merge. A prior successful report is **not** evidence that later changes passed.

### Scope boundaries, not blockers to this UI-only task

Real Chromium drives the production Next.js build with deterministic simulated API responses. This validates real rendering, keyboard/mouse behavior, layout geometry, selection state, locale, theme, and intercepted request payloads. It **does not assert** production-backend correctness, physical-device/browser-engine interoperability, real AWS/OCI costs, or tenant authorization behavior. Those require independent staging/production acceptance and do not belong to the visual-only Task 26.3.

### Release gate

- **PASS:** all Phase 26 UI acceptance checks and the PR's latest required CI workflows pass, with artifacts retained.
- **PASS WITH WARNINGS:** a required UI check remains unverified even though no defect is known.
- **FAIL:** any critical functional/visual regression or CI failure remains.

The evidence supports **PASS for Phase 26 UI scope** provided the latest PR commit has successful CI, authenticated E2E, Compose smoke and auto-deploy workflows. Nothing in this report establishes a successful real-production deployment. Manual device lab coverage is a separate compatibility initiative, not a prerequisite introduced retroactively for this scoped UI refinement.
