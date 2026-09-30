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


## Multi-cloud schema rollout and recovery

The Stage 17+ account model introduces a provider-neutral `cloud_accounts` row and
a required one-to-one link from every legacy `aws_accounts` row. Stage 18 adds
encrypted OCI configuration, and Stage 21 synchronizes the PostgreSQL sequence
after the legacy-account backfill.

For an existing installation:

1. Create and verify a database backup before updating the application.
2. Back up `NUVEMIQ_OCI_CREDENTIALS_KEY` and
   `NUVEMIQ_OCI_CREDENTIALS_KEY_VERSION` separately from the database. A database
   backup alone cannot recover OCI private keys.
3. Stop old API and worker writers before applying these migrations.
4. Pull/build the new revision and start the API so it can run the migrations.
5. Confirm the API healthcheck, then start/confirm worker, web and proxy.
6. Verify Configurações → Contas, an existing AWS connection, the provider
   capability matrix and an AWS scan before treating the rollout as complete.

Do not run an older API image against a database already migrated to Stage 17+:
older account creation code does not populate the required `cloud_account_id`
link and is not write-compatible with the new schema.

If rollout fails after the schema changed, rolling back only the container image is
not sufficient. Stop writers and restore a database backup that is consistent with
the older application revision. Data created after that backup will be lost unless
it is explicitly reconciled before restoration. OCI credentials additionally
require the matching backed-up Fernet key/version.
