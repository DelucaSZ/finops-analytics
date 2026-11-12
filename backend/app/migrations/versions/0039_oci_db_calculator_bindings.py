"""Verified catalog identity bindings for OCI Base Database Service estimates.

Revision ID: 0039_oci_db_calculator_bindings
Revises: 0038_rds_reservations_pipeline
No pricing values or unverified Oracle SKUs are seeded.
"""

import sqlalchemy as sa
from alembic import op

revision = "0039_oci_db_calculator_bindings"
down_revision = "0038_rds_reservations_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oci_db_calculator_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("region", sa.String(length=80), nullable=False),
        sa.Column("deployment_model", sa.String(length=32), nullable=False),
        sa.Column("shape", sa.String(length=80), nullable=False),
        sa.Column("edition", sa.String(length=32), nullable=False),
        sa.Column("license_model", sa.String(length=24), nullable=False),
        sa.Column("cpu_unit", sa.String(length=8), nullable=False),
        sa.Column("component", sa.String(length=24), nullable=False),
        sa.Column("sku", sa.String(length=160), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("includes_license", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint(
            "component IN ('capacity', 'license', 'storage')",
            name="ck_oci_db_binding_component",
        ),
        sa.CheckConstraint("cpu_unit = 'ECPU'", name="ck_oci_db_binding_ecpu"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "region",
            "deployment_model",
            "shape",
            "edition",
            "license_model",
            "cpu_unit",
            "component",
            name="uq_oci_db_calculator_binding",
        ),
    )
    op.create_index(
        "ix_oci_db_calculator_bindings_region",
        "oci_db_calculator_bindings",
        ["region", "enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oci_db_calculator_bindings_region",
        table_name="oci_db_calculator_bindings",
    )
    op.drop_table("oci_db_calculator_bindings")
