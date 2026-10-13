from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text

from app.db.migrations import migration_config

EXPECTED_OCI_PRICES = {
    ("compute", "VM.Standard.E3.Flex.OCPU", "OCPU_HOUR"): Decimal("0.05210000"),
    ("compute", "VM.Standard.E3.Flex.Memory", "GB_RAM_HOUR"): Decimal("0.00310000"),
    ("compute", "VM.Standard.E4.Flex.OCPU", "OCPU_HOUR"): Decimal("0.06890000"),
    ("compute", "VM.Standard.E4.Flex.Memory", "GB_RAM_HOUR"): Decimal("0.00410000"),
    ("compute", "VM.Standard.E5.Flex.OCPU", "OCPU_HOUR"): Decimal("0.08266000"),
    ("compute", "VM.Standard.E5.Flex.Memory", "GB_RAM_HOUR"): Decimal("0.00551100"),
    ("compute", "WINDOWS_LICENSE_OCPU", "OCPU_HOUR"): Decimal("0.46092000"),
    ("block_volume", "BLOCK_VOLUME_GB_MONTH", "GB_MONTH"): Decimal("0.05310000"),
    (
        "block_volume",
        "BLOCK_VOLUME_VPU_GB_MONTH",
        "VPU_GB_MONTH",
    ): Decimal("0.00360000"),
}


@pytest.fixture(params=["sqlite", "postgresql"])
def pricing_migration_engine(request, tmp_path):
    if request.param == "sqlite":
        engine = create_engine(f"sqlite:///{tmp_path / 'pricing-migration.db'}")
        yield engine
        engine.dispose()
        return

    url = os.environ.get("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set TEST_POSTGRES_URL to exercise real PostgreSQL migrations")
    schema = "test_pricing_" + uuid.uuid4().hex
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def test_stage23_7_migration_creates_and_seeds_oci_brl_catalog(pricing_migration_engine):
    with pricing_migration_engine.begin() as connection:
        cfg = migration_config()
        cfg.attributes["connection"] = connection
        cfg.attributes["version_table"] = "deepops_mfa_schema_version"
        command.upgrade(cfg, "0023_opportunity_retention")
        assert "pricing_catalog_items" not in inspect(connection).get_table_names()

        command.upgrade(cfg, "0024_pricing_catalog")

        inspector = inspect(connection)
        assert "pricing_catalog_items" in inspector.get_table_names()
        columns = {column["name"]: column for column in inspector.get_columns("pricing_catalog_items")}
        assert columns["provider"]["nullable"] is False
        assert columns["service"]["nullable"] is False
        assert columns["sku"]["nullable"] is False
        assert columns["unit"]["nullable"] is False
        assert columns["currency"]["nullable"] is False
        assert columns["effective_from"]["nullable"] is False
        assert columns["price"]["nullable"] is False
        assert columns["price"]["type"].precision == 20
        assert columns["price"]["type"].scale == 8
        assert "ix_pricing_catalog_items_lookup" in {
            index["name"] for index in inspector.get_indexes("pricing_catalog_items")
        }
        constraint_names = {
            constraint["name"] for constraint in inspector.get_check_constraints("pricing_catalog_items")
        }
        assert "ck_pricing_catalog_items_price_non_negative" in constraint_names
        assert "ck_pricing_catalog_items_currency_iso_code" in constraint_names
        assert "ck_pricing_catalog_items_effective_interval" in constraint_names

        table = Table("pricing_catalog_items", MetaData(), autoload_with=connection)
        rows = connection.execute(select(table)).mappings().all()
        assert len(rows) == len(EXPECTED_OCI_PRICES) == 9
        assert {row["provider"] for row in rows} == {"oci"}
        assert {row["currency"] for row in rows} == {"BRL"}
        assert {row["source"] for row in rows} == {"IMPORTED_OCI_CALCULATOR"}
        assert all(row["enabled"] for row in rows)
        assert all(row["effective_until"] is None for row in rows)
        assert {
            (row["service"], row["sku"], row["unit"]): Decimal(row["price"])
            for row in rows
        } == EXPECTED_OCI_PRICES
