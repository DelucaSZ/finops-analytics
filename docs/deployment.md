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
docker compose up --build -d
docker compose ps
docker compose logs -f --tail=200
```

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
cd /opt/nuvemiq
git pull --ff-only
./scripts/deploy.sh /opt/nuvemiq
```

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
