# DeepOps

Formerly NuvemIQ. Existing `NUVEMIQ_*` environment variables, database names,
login credentials, browser sessions and IAM role names remain compatible.
The rebrand does not require an infrastructure or data migration.

DeepOps is a self-hosted, multi-account AWS FinOps platform focused on finding
waste, explaining evidence and prioritizing savings opportunities.

## Current milestone

This repository contains the first functional foundation of the MVP:

- Next.js dashboard;
- FastAPI API;
- PostgreSQL persistence;
- durable scan worker;
- EC2 instance-profile + cross-account `AssumeRole` authentication;
- global policies with account-level overrides;
- account onboarding and connection validation;
- nine configurable efficiency and waste detectors;
- optional AI explanations through Amazon Bedrock;
- Docker Compose deployment for Linux.

The application is read-only. It does not stop, resize or delete AWS resources.

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
   `.env`.

For a UI-only evaluation without connecting AWS, set `NUVEMIQ_DEMO_MODE=true`
before the first start. Demo data is never loaded when the option is false.

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
