# DeepOps

Formerly NuvemIQ. Existing `NUVEMIQ_*` environment variables, database names,
and IAM role names remain compatible. The users migration imports the existing
admin credentials once; old browser tokens require a new login.

DeepOps is a self-hosted, multi-account AWS FinOps platform focused on finding
waste, explaining evidence and prioritizing savings opportunities.

## Current milestone

This repository contains the first functional foundation of the MVP:

- Next.js dashboard;
- FastAPI API;
- PostgreSQL persistence with versioned Alembic migrations;
- individual users with Argon2id passwords and admin/operator/viewer permissions;
- revocable cookie sessions, invitations, password recovery and personal security screens;
- durable scan worker;
- EC2 instance-profile + cross-account `AssumeRole` authentication;
- global policies with account-level overrides;
- account onboarding and connection validation;
- nine configurable efficiency and waste detectors;
- evidence summaries on every opportunity, with expandable observations and policy criteria;
- cost growth comparisons with dates, normalized baseline, and top billing usage-type increases;
- optional AI explanations through Amazon Bedrock;
- Docker Compose deployment for Linux.

The application is read-only. It does not stop, resize or delete AWS resources.

Opportunity evidence is explained without requiring Bedrock. Existing findings use
their stored evidence; run a new scan after updating to capture policy snapshots,
exact cost periods, and usage-type breakdowns. Cost breakdowns add a paginated
Cost Explorer query per detected service/region anomaly (normal AWS API charges
apply), using the existing `ce:GetCostAndUsage` permission. If this optional query
fails, the primary comparison is retained and the UI reports missing detail.
Billing growth is not proof of higher consumption or a specific resource change.

## Architecture

```text
Browser -> Caddy -> Next.js / FastAPI -> PostgreSQL
                                  |
                                  +-> Worker -> STS AssumeRole -> AWS accounts
```

The EC2 instance receives temporary base credentials from its IAM instance
profile. For each registered AWS account, DeepOps calls STS `AssumeRole` with a
unique External ID. No AWS access key is stored by the application.

## Quick start

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Replace every password and secret in `.env`.

3. Start the stack:

   ```bash
   docker compose up --build -d
   ```

4. Open `http://SERVER_IP` and sign in with the admin credentials configured in
   `.env` (imported once into the database on the first startup).

For a UI-only evaluation without connecting AWS, set `NUVEMIQ_DEMO_MODE=true`
before the first start. Demo data is never loaded when the option is false.

See [Users and permissions](docs/users-and-permissions.md) for the migration,
API administration and rollback limits. [Authentication lifecycle](docs/authentication-lifecycle.md)
covers the current cookie API, invitations, recovery and personal security screens.
Administrative settings screens, MFA and HTTPS management remain upcoming stages;
keep access restricted to the controlled network.

## AWS setup

1. Attach an IAM role to the EC2 instance hosting DeepOps.
2. Allow that central role to call `sts:AssumeRole` on the account roles.
3. Deploy
   `infrastructure/cloudformation/nuvemiq-readonly-role.yaml` in every target
   account.
4. Register the resulting Role ARN and the matching External ID in DeepOps.
5. Use **Test connection** before running the first scan.

The central instance role can be created with
`infrastructure/cloudformation/nuvemiq-central-role.yaml`. The target-account
role is created with `nuvemiq-readonly-role.yaml`.

## AI explanations

The calculations and detection rules are deterministic. AI is only used to
explain evidence and recommend validation steps. To enable Amazon Bedrock:

1. deploy the central-role stack with `EnableBedrock=true`;
2. enable model access in the configured Bedrock region;
3. set `NUVEMIQ_AI_PROVIDER=bedrock`;
4. set `NUVEMIQ_BEDROCK_MODEL_ID` to an enabled model or inference profile.

Cost Explorer must be enabled in the relevant account. Consolidated organization
cost analysis should be performed through the management/payer account.

Detailed instructions are available in [AWS onboarding](docs/aws-onboarding.md)
and [Linux deployment](docs/deployment.md).

For automatic EC2 updates from `main`, health validation and image-based rollback,
see [Automatic deployment](docs/auto-deploy.md). Install once with
`sudo bash scripts/install-auto-deploy.sh` after pulling the repository.

## Development

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Security notes

- Never commit `.env`, AWS credentials, certificates or SSH keys.
- Restrict the EC2 security group and place the application behind HTTPS before
  production use.
- Replace the broad AWS managed read-only policies with a least-privilege policy
  after validating the APIs used by the collectors.
- Store production secrets in AWS Secrets Manager or SSM Parameter Store.
- Prefer Session Manager over exposing TCP/22 to the internet.

### MFA TOTP

Em **Minha segurança**, configure o autenticador pelo QR code ou chave manual e
salve os dez códigos de recuperação. O login passa a exigir senha + segundo fator.
Para exigir o cadastro de todos, configure `NUVEMIQ_MFA_REQUIRED=true` no servidor.
Consulte [MFA e recuperação](docs/mfa-totp.md) para chaves, operação e migração.
