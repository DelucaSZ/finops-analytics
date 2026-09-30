# Stage 21 integrated validation

Base revision reviewed: `main@18695f3697cd4019517e0eb2a9e71a79dbf0bfbd`.

This document records what was actually validated for the closure of Stages 16–20.
It intentionally separates automated evidence, simulated cloud behavior, real cloud
validation and production deployment.

## Findings and corrections

- Confirmed PR #26 / Stage 20 is merged into `main`; the roadmap was stale and was corrected.
- Found a PostgreSQL sequence hazard in the Stage 17 legacy ID backfill.
  `0016_cloud_account_sequence` now synchronizes the `cloud_accounts.id` sequence.
- Added a migration regression test that upgrades a representative pre-Stage-17
  database and then creates another CloudAccount.
- Fixed the PostgreSQL sequence hazard after the Stage 17 explicit-ID backfill.
- Prevented old API/worker writers from remaining active while a schema migration
  is activated by the manual deploy script.
- Prevented the automatic deploy controller from applying a migration-bearing
  release and then image-rolling back against the changed schema.
- Added an explicit `adopt` action to rebaseline a manually deployed healthy
  migration release.
- Added rollout/recovery guidance covering backup, Fernet key preservation and
  old-image/schema incompatibility.
- Clarified that OCI registration/test does not imply FinOps collection support.

## Validation matrix

| Scenario | Environment/type | Result | Evidence / command | Limitation |
| --- | --- | --- | --- | --- |
| Fresh database to migration head | CI, SQLite + PostgreSQL 17 | Approved | CI #211, `pytest -q`; migration/model parity at `0016_cloud_account_sequence` | No production data |
| Upgrade from representative pre-Stage-17 database | CI, SQLite + PostgreSQL 17 | Approved | CI #211; history fixture + Stage 21 sequence regression | Fixtures, not production clone |
| Re-running normal initialization at head | CI | Approved | CI #211; migration/bootstrap restart regression suite | No production restart |
| AWS account compatibility and immutable identity | CI/API tests | Approved | CI #211; `test_cloud_accounts.py` | AWS remote calls mocked where applicable |
| OCI encrypted persistence and sanitized reads | CI/API tests | Approved | CI #211; `test_cloud_accounts.py` | Test-only generated keys |
| OCI auth/authz/network failure mapping | CI/unit integration | Approved | CI #211; OCI service-error tests | SDK responses simulated |
| OCI manual collection/scheduling/policies blocked | CI | Approved | CI #211; `test_provider_capabilities.py` | No OCI collector exists by design |
| Dashboard collection health excludes unsupported OCI | CI | Approved | CI #211; `test_dashboard.py` | Synthetic fixtures |
| Frontend provider-aware account/policy behavior | CI Node tests/build | Approved | CI #211; 51 Node tests + production build | Browser E2E is recorded separately below |
| Compose definitions, secret placement and static exposure checks | CI static security checks | Approved | CI #211 security job | Does not start Compose stack |
| Auto-deploy refuses migration changes before activation | CI unit tests | Approved | Auto deploy #204; 15 tests | Does not modify a real host |
| Manual deploy stops old writers before migration owner starts | CI shell syntax + code review | Approved | Auto deploy #204; `bash -n scripts/deploy.sh` | Real Compose smoke still separate |
| Browser navigation and critical account/policy interactions | GitHub Actions, Chromium desktop + mobile | Approved | CI #211; 4 Playwright tests | API/cloud responses are mocked; real cloud is separate |
| Local isolated Compose smoke test | Current runtime | Not executed | checkout blocked: runtime cannot resolve github.com | Requires Docker + source checkout |
| Browser navigation desktop/mobile | Current runtime | Not executed | no browser E2E executor available here | Must be executed separately |
| Real OCI connection | Authorized tenancy | Not executed | no test credential supplied through a secure mechanism | Blocks only real-cloud validation |
| Production deploy/post-deploy validation | Production | Not executed | no deployment authorization in this Stage 21 request | Separate operational action |

## Deployment gate

Automated validation is complete on CI #211: backend 299 tests on SQLite/PostgreSQL 17,
frontend 51 tests plus production build, security gates, and 4 Playwright browser
checks. Auto-deploy #204 also passed all 15 deployment-controller tests.

The phase is not declared fully validated operationally: an isolated real Compose
smoke test, authorized real OCI connection, and production rollout/post-deploy checks
remain explicitly unexecuted. A failed real OCI connection must not be interpreted as
collector support; OCI collection remains unsupported in this phase.
