"""Adopt the pre-users schema without changing existing application data."""

import sqlalchemy as sa
from alembic import op

revision = "0001_legacy"
down_revision = None
branch_labels = None
depends_on = None


def _create_table(name, *elements, **kwargs):
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table(name):
        expected = {item.name for item in elements if isinstance(item, sa.Column)}
        actual = {item["name"] for item in inspector.get_columns(name)}
        if not expected.issubset(actual):
            raise RuntimeError(f"Legacy table {name} differs from the expected schema")
        return
    op.create_table(name, *elements, **kwargs)


def _create_index(name, table, columns, **kwargs):
    if name not in {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table)}:
        op.create_index(name, table, columns, **kwargs)


def upgrade():
    _create_table(
        "aws_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("aws_account_id", sa.String(length=12), nullable=False),
        sa.Column("role_arn", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_management_account", sa.Boolean(), nullable=False),
        sa.Column("schedule_enabled", sa.Boolean(), nullable=False),
        sa.Column("scan_interval_hours", sa.Integer(), nullable=False),
        sa.Column("next_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connection_status", sa.String(length=24), nullable=False),
        sa.Column("last_connection_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(
        op.f("ix_aws_accounts_aws_account_id"), "aws_accounts", ["aws_account_id"], unique=True
    )
    _create_table(
        "policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("rule_key", sa.String(length=80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["aws_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope", "account_id", "rule_key", name="uq_policy_scope_rule"),
    )
    _create_index(op.f("ix_policies_account_id"), "policies", ["account_id"], unique=False)
    _create_index(op.f("ix_policies_rule_key"), "policies", ["rule_key"], unique=False)
    _create_index(op.f("ix_policies_scope"), "policies", ["scope"], unique=False)
    _create_table(
        "scans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("trigger", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("findings_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["aws_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(op.f("ix_scans_account_id"), "scans", ["account_id"], unique=False)
    _create_index(op.f("ix_scans_status"), "scans", ["status"], unique=False)
    _create_table(
        "findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("rule_key", sa.String(length=80), nullable=False),
        sa.Column("service", sa.String(length=40), nullable=False),
        sa.Column("region", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("resource_name", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("current_monthly_cost", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("estimated_monthly_savings", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["aws_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["scan_id"],
            ["scans.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    _create_index(op.f("ix_findings_account_id"), "findings", ["account_id"], unique=False)
    _create_index(op.f("ix_findings_fingerprint"), "findings", ["fingerprint"], unique=True)
    _create_index(op.f("ix_findings_rule_key"), "findings", ["rule_key"], unique=False)
    _create_index(op.f("ix_findings_scan_id"), "findings", ["scan_id"], unique=False)
    _create_index(op.f("ix_findings_status"), "findings", ["status"], unique=False)


def downgrade():
    raise RuntimeError("Data-preserving migrations: restore a verified backup to downgrade")
