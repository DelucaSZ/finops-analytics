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

## Execution status and evidence protocol

- **Baseline integrated CI:** PASS on the `main` baseline commit above.
- **Task 26.3 dedicated browser QA:** requires running the Task 26.3 PR CI and examining `frontend/artifacts/phase26/report.json`. Never assume green status from the test source code.
- **Browser/screenshots:** screenshots are machine-generated evidence. They do not constitute an independent human visual review.
- **Physical mobile/tablet hardware, alternate browser engines, live multi-account production data and real backend:** not covered by this fixture-based CI suite.
- **Unknown API fixtures:** reported as `blocked` in JSON, not silently counted as passes.
- **Failed or skipped checks:** inspect CI jobs, the uploaded JSON report, and screenshot artifacts before assigning a final task status.

## Release gate

- **PASS:** all mandatory checks verified, with no unresolved limitation.
- **PASS WITH WARNINGS:** no known critical regression, but physical device/live backend/manual visual verification or other explicitly listed items remain pending.
- **FAIL:** a mandatory browser assertion, CI test, or critical behavior fails.

**Phase 26 must not be declared completed until status PASS is supported by actual evidence.** Do not merge the Task 26.3 PR automatically.
