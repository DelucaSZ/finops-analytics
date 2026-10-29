# Deploying DeepOps on Linux

The recommended first deployment is one Ubuntu 24.04 LTS EC2 instance running
Docker Compose. PostgreSQL is containerized for the MVP; moving it to RDS is a
straightforward later step.

## EC2 prerequisites

- attach the `NuvemIQCentralRole` instance profile;
- enable IMDSv2 and require tokens;
- install and configure the SSM Agent;
- allow outbound HTTPS to AWS service endpoints;
- expose the application only through the corporate network, VPN or an
  authenticated reverse proxy;
- prefer Session Manager instead of opening SSH to the internet;
- allocate persistent encrypted EBS storage for Docker data.

## Application deployment

```bash
sudo mkdir -p /opt/nuvemiq
sudo chown "$USER":"$USER" /opt/nuvemiq
git clone YOUR_REPOSITORY_URL /opt/nuvemiq
cd /opt/nuvemiq
cp .env.example .env
```

Generate strong values for `POSTGRES_PASSWORD`, `NUVEMIQ_SECRET_KEY` and
`NUVEMIQ_ADMIN_PASSWORD`. Do not reuse AWS credentials or commit `.env`.

Start the services:

```bash
NEXT_PUBLIC_BUILD_SHA="$(git rev-parse --short=12 HEAD)" docker compose build --pull --no-cache && \
  docker compose up -d --force-recreate --remove-orphans
docker compose ps
docker compose logs -f --tail=200
```

The `&&` is intentional: a failed image build must stop the deployment before
`docker compose up` can reuse an older local image. For routine updates, use the
versioned deployment script below instead of running build and up independently.

The default Caddy configuration serves HTTP on port 80 for initial private-network
validation. Before external exposure, apply HTTPS from **Configurações > HTTPS**,
switch the application environment to production and follow
[External access](external-access.md). Do not publish API, web, PostgreSQL or the
Caddy admin port directly.

## Users and database initialization

The API runs versioned Alembic migrations and imports the configured administrator
once before accepting requests. The worker waits for initialization. Existing
FinOps tables and data are preserved. See [Users and permissions](users-and-permissions.md)
for backup and first-login details, and [Authentication lifecycle](authentication-lifecycle.md)
for cookie, SMTP and current migration/rollback behavior.

## Updating

```bash
./scripts/deploy.sh /opt/nuvemiq
```

The deployment script refuses tracked local modifications, runs `git pull --ff-only`,
derives `NEXT_PUBLIC_BUILD_SHA` from the checked-out commit, builds every buildable
image with `--pull --no-cache`, and only then recreates containers with
`--force-recreate --remove-orphans`. Because the script uses `set -euo pipefail`,
any failed pull or build aborts before container recreation.

After startup, the script verifies that the running `web` container reports the
same SHA that was built. The frontend also exposes immutable build metadata at:

```text
/version
```

A successful response has the form:

```json
{"buildSha":"c28e6c7c0696"}
```

The value is injected while the frontend image is built and is also recorded in
the image label `org.opencontainers.image.revision`, so troubleshooting can tie a
running frontend back to the source commit incorporated into the image.

## Backup

The MVP stores application data in the `postgres_data` Docker volume. Configure
both periodic `pg_dump` backups to encrypted object storage and EBS snapshots.
Test restoration before relying on either mechanism.

## Production hardening backlog

External exposure baseline (MFA, HTTPS, 80/443-only ingress and validation) is
covered by [External access](external-access.md). Remaining larger architecture
items include:

- move PostgreSQL to encrypted RDS Multi-AZ;
- integrate company SSO/OIDC instead of the bootstrap admin login;
- place an ALB and WAF in front of the service when internet access is required;
- use Secrets Manager or Parameter Store for runtime secrets;
- send application and access logs to CloudWatch Logs;
- restrict the target-account policy after measuring real API usage.
