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
| Fresh database to migration head | CI, SQLite + PostgreSQL 17 | Pending CI | `pytest -q` / `test_fresh_database_matches_models_and_worker_is_ready` | No production data |
| Upgrade from representative pre-Stage-17 database | CI, SQLite + PostgreSQL 17 | Pending CI | Stage 17 history fixture + Stage 21 sequence regression | Fixtures, not production clone |
| Re-running normal initialization at head | CI | Pending CI | migration/bootstrap regression suite | No production restart |
| AWS account compatibility and immutable identity | CI/API tests | Pending CI | `test_cloud_accounts.py` | AWS remote calls mocked where applicable |
| OCI encrypted persistence and sanitized reads | CI/API tests | Pending CI | `test_cloud_accounts.py` | Test-only generated keys |
| OCI auth/authz/network failure mapping | CI/unit integration | Pending CI | OCI service-error tests | SDK responses simulated |
| OCI manual collection/scheduling/policies blocked | CI | Pending CI | `test_provider_capabilities.py` | No OCI collector exists by design |
| Dashboard collection health excludes unsupported OCI | CI | Pending CI | `test_dashboard.py` | Synthetic fixtures |
| Frontend provider-aware account/policy behavior | CI Node tests/build | Pending CI | `npm test`, `npm run build` | Not browser E2E |
| Compose definitions, secret placement and static exposure checks | CI static security checks | Pending CI | security job | Does not start Compose stack |
| Auto-deploy refuses migration changes before activation | CI unit tests | Pending CI | `python -m unittest discover -s scripts/tests -v` | Does not modify a real host |
| Manual deploy stops old writers before migration owner starts | CI shell syntax + code review | Pending CI | `bash -n scripts/deploy.sh` | Real Compose smoke still separate |
| Local isolated Compose smoke test | Current runtime | Not executed | checkout blocked: runtime cannot resolve github.com | Requires Docker + source checkout |
| Browser navigation desktop/mobile | Current runtime | Not executed | no browser E2E executor available here | Must be executed separately |
| Real OCI connection | Authorized tenancy | Not executed | no test credential supplied through a secure mechanism | Blocks only real-cloud validation |
| Production deploy/post-deploy validation | Production | Not executed | no deployment authorization in this Stage 21 request | Separate operational action |

## Deployment gate

Do not call the phase fully validated until the branch CI passes and any required
browser/real-cloud checks are executed for the target rollout. A failed real OCI
connection must not be interpreted as collector support; OCI collection remains
unsupported in this phase.
