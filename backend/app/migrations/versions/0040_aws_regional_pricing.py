"""Regional AWS pricing metadata, shared catalog identity and audit provenance.

Revision ID: 0040_aws_regional_pricing
Revises: 0039_oci_db_calculator_bindings

No AWS prices are imported. All existing OCI pricing rows remain untouched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0040_aws_regional_pricing"
down_revision = "0039_oci_db_calculator_bindings"
branch_labels = None
depends_on = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    # SQLite needs the Alembic batch-copy strategy to remove its old UNIQUE.
    # PostgreSQL performs ordinary ALTERs, retaining every OCI row/id.
    with op.batch_alter_table("pricing_catalog_items") as batch:
        batch.add_column(sa.Column("region_code", sa.String(40), nullable=True))
        batch.drop_constraint("uq_pricing_catalog_items_identity_effective_from", type_="unique")
        batch.create_check_constraint(
            "ck_pricing_catalog_items_aws_region",
            "provider <> 'aws' OR (region_code IS NOT NULL AND length(trim(region_code)) > 0)",
        )
        batch.create_check_constraint(
            "ck_pricing_catalog_items_aws_currency",
            "provider <> 'aws' OR currency = 'USD'",
        )

    op.create_index(
        "uq_pricing_catalog_items_oci_effective",
        "pricing_catalog_items",
        ["provider", "service", "sku", "unit", "effective_from"],
        unique=True,
        postgresql_where=sa.text("provider <> 'aws'"),
        sqlite_where=sa.text("provider <> 'aws'"),
    )
    op.create_index(
        "uq_pricing_catalog_items_aws_effective",
        "pricing_catalog_items",
        ["provider", "service", "region_code", "sku", "unit", "effective_from"],
        unique=True,
        postgresql_where=sa.text("provider = 'aws'"),
        sqlite_where=sa.text("provider = 'aws'"),
    )
    op.create_index(
        "ix_pricing_catalog_items_aws_lookup",
        "pricing_catalog_items",
        ["provider", "service", "region_code", "sku", "unit", "enabled", "effective_from"],
    )

    # PostgreSQL enforces overlap across concurrent writers, including cases
    # where neither writer sees the other's uncommitted row.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute(
            "ALTER TABLE pricing_catalog_items "
            "ADD CONSTRAINT ex_aws_pricing_effective_no_overlap "
            "EXCLUDE USING gist ("
            "service WITH =, region_code WITH =, sku WITH =, unit WITH =, "
            "tstzrange(effective_from, effective_until, '[)') WITH &&"
            ") WHERE (provider = 'aws' AND enabled)"
        )

    op.create_table(
        "aws_pricing_import_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_code", sa.String(80), nullable=False),
        sa.Column("region_code", sa.String(40), nullable=False),
        sa.Column("source_version", sa.String(160), nullable=False),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("source_uri", sa.String(1000)),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("products_seen", sa.Integer(), nullable=False),
        sa.Column("rates_seen", sa.Integer(), nullable=False),
        sa.Column("rates_rejected", sa.Integer(), nullable=False),
        sa.Column("diagnostics", _JSON),
        sa.Column("checkpoint", _JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','staged','validated','published','partial','failed')",
            name="ck_aws_import_batch_status",
        ),
        sa.CheckConstraint(
            "products_seen >= 0 AND rates_seen >= 0 AND rates_rejected >= 0",
            name="ck_aws_import_batch_counts",
        ),
        sa.UniqueConstraint(
            "service_code",
            "region_code",
            "source_version",
            "checksum",
            name="uq_aws_import_batch_source",
        ),
    )
    op.create_table(
        "aws_pricing_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_code", sa.String(80), nullable=False),
        sa.Column("service", sa.String(64), nullable=False),
        sa.Column("region_code", sa.String(40), nullable=False),
        sa.Column("product_sku", sa.String(160), nullable=False),
        sa.Column("product_family", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("product_attributes", _JSON, nullable=False),
        sa.Column("financial_attributes", _JSON, nullable=False),
        sa.Column("attribute_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(region_code) > 0", name="ck_aws_product_region"),
        sa.UniqueConstraint(
            "service_code",
            "region_code",
            "product_sku",
            name="uq_aws_pricing_product_identity",
        ),
    )
    op.create_index(
        "ix_aws_pricing_product_match",
        "aws_pricing_products",
        ["service", "region_code", "attribute_hash"],
    )
    op.create_index(
        "ix_aws_pricing_product_family",
        "aws_pricing_products",
        ["service", "region_code", "product_family"],
    )
    op.create_table(
        "aws_pricing_rate_details",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pricing_item_id", sa.String(36), nullable=False),
        sa.Column("product_id", sa.String(36), nullable=False),
        sa.Column("rate_code", sa.String(180), nullable=False),
        sa.Column("term_code", sa.String(180), nullable=False),
        sa.Column("purchase_option", sa.String(32), nullable=False),
        sa.Column("billing_unit_aws", sa.String(64), nullable=False),
        sa.Column("begin_range", sa.String(80), nullable=False),
        sa.Column("end_range", sa.String(80), nullable=False),
        sa.Column("rate_description", sa.String(500), nullable=False),
        sa.Column("pricing_status", sa.String(24), nullable=False),
        sa.Column("import_batch_id", sa.String(36)),
        sa.Column("source_effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "pricing_status IN ('active','unsupported','quarantined','withdrawn')",
            name="ck_aws_rate_status",
        ),
        sa.ForeignKeyConstraint(
            ["pricing_item_id"], ["pricing_catalog_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["aws_pricing_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["aws_pricing_import_batches.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("pricing_item_id", name="uq_aws_rate_pricing_item"),
    )
    op.create_index(
        "ix_aws_rate_product_option",
        "aws_pricing_rate_details",
        ["product_id", "purchase_option", "rate_code"],
    )
    op.create_index(
        "ix_aws_rate_import_batch",
        "aws_pricing_rate_details",
        ["import_batch_id"],
    )
    op.create_table(
        "aws_pricing_sync_state",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("service_code", sa.String(80), nullable=False),
        sa.Column("region_code", sa.String(40), nullable=False),
        sa.Column("last_successful_batch_id", sa.String(36)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("coverage_status", sa.String(24), nullable=False),
        sa.Column("coverage", _JSON),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["last_successful_batch_id"],
            ["aws_pricing_import_batches.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "coverage_status IN ('never_synced','synced','partial','stale','failed')",
            name="ck_aws_sync_coverage_status",
        ),
        sa.UniqueConstraint("service_code", "region_code", name="uq_aws_sync_service_region"),
    )
    with op.batch_alter_table("pricing_audit_events") as batch:
        batch.add_column(sa.Column("region_code", sa.String(40), nullable=True))
        batch.add_column(sa.Column("import_batch_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_pricing_audit_import_batch",
            "aws_pricing_import_batches",
            ["import_batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.create_index(
        "ix_pricing_audit_aws_key_occurred",
        "pricing_audit_events",
        ["provider", "service", "region_code", "sku", "unit", "occurred_at"],
    )


def downgrade() -> None:
    # A downgrade is safe only before real AWS catalog data has been staged.
    bind = op.get_bind()
    for table in (
        "aws_pricing_rate_details",
        "aws_pricing_products",
        "aws_pricing_import_batches",
        "aws_pricing_sync_state",
    ):
        count = bind.scalar(sa.text(f"SELECT count(*) FROM {table}"))
        if count:
            raise RuntimeError(f"Cannot downgrade AWS pricing with existing data in {table}")
    if bind.scalar(sa.text("SELECT count(*) FROM pricing_catalog_items WHERE provider = 'aws'")):
        raise RuntimeError("Cannot downgrade AWS pricing with published AWS prices")

    op.drop_index("ix_pricing_audit_aws_key_occurred", table_name="pricing_audit_events")
    with op.batch_alter_table("pricing_audit_events") as batch:
        batch.drop_constraint("fk_pricing_audit_import_batch", type_="foreignkey")
        batch.drop_column("import_batch_id")
        batch.drop_column("region_code")

    op.drop_table("aws_pricing_sync_state")
    op.drop_index("ix_aws_rate_import_batch", table_name="aws_pricing_rate_details")
    op.drop_index("ix_aws_rate_product_option", table_name="aws_pricing_rate_details")
    op.drop_table("aws_pricing_rate_details")
    op.drop_index("ix_aws_pricing_product_family", table_name="aws_pricing_products")
    op.drop_index("ix_aws_pricing_product_match", table_name="aws_pricing_products")
    op.drop_table("aws_pricing_products")
    op.drop_table("aws_pricing_import_batches")

    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE pricing_catalog_items DROP CONSTRAINT ex_aws_pricing_effective_no_overlap"
        )
    op.drop_index("ix_pricing_catalog_items_aws_lookup", table_name="pricing_catalog_items")
    op.drop_index("uq_pricing_catalog_items_aws_effective", table_name="pricing_catalog_items")
    op.drop_index("uq_pricing_catalog_items_oci_effective", table_name="pricing_catalog_items")
    with op.batch_alter_table("pricing_catalog_items") as batch:
        batch.drop_constraint("ck_pricing_catalog_items_aws_currency", type_="check")
        batch.drop_constraint("ck_pricing_catalog_items_aws_region", type_="check")
        batch.drop_column("region_code")
        batch.create_unique_constraint(
            "uq_pricing_catalog_items_identity_effective_from",
            ["provider", "service", "sku", "unit", "effective_from"],
        )
