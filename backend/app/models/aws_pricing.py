"""AWS metadata extension; amounts remain authoritative in pricing_catalog_items."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

_AWS_JSON = JSON().with_variant(JSONB, "postgresql")


def _id() -> str:
    return str(uuid.uuid4())


class AwsPricingProduct(TimestampMixin, Base):
    __tablename__ = "aws_pricing_products"
    __table_args__ = (
        UniqueConstraint(
            "service_code",
            "region_code",
            "product_sku",
            name="uq_aws_pricing_product_identity",
        ),
        Index(
            "ix_aws_pricing_product_match",
            "service",
            "region_code",
            "attribute_hash",
        ),
        Index("ix_aws_pricing_product_family", "service", "region_code", "product_family"),
        CheckConstraint("length(region_code) > 0", name="ck_aws_product_region"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    region_code: Mapped[str] = mapped_column(String(40), nullable=False)
    product_sku: Mapped[str] = mapped_column(String(160), nullable=False)
    product_family: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    product_attributes: Mapped[dict[str, Any]] = mapped_column(_AWS_JSON, nullable=False)
    # A validated, canonical, exact set of financial attributes (not arbitrary JSON matching).
    financial_attributes: Mapped[dict[str, str]] = mapped_column(_AWS_JSON, nullable=False)
    attribute_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)


class AwsPricingImportBatch(TimestampMixin, Base):
    __tablename__ = "aws_pricing_import_batches"
    __table_args__ = (
        UniqueConstraint(
            "service_code",
            "region_code",
            "source_version",
            "checksum",
            name="uq_aws_import_batch_source",
        ),
        CheckConstraint(
            "status IN ('running','staged','validated','published','partial','failed')",
            name="ck_aws_import_batch_status",
        ),
        CheckConstraint(
            "products_seen >= 0 AND rates_seen >= 0 AND rates_rejected >= 0",
            name="ck_aws_import_batch_counts",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    region_code: Mapped[str] = mapped_column(String(40), nullable=False)
    source_version: Mapped[str] = mapped_column(String(160), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    products_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rates_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rates_rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    diagnostics: Mapped[dict[str, Any] | None] = mapped_column(_AWS_JSON)
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(_AWS_JSON)


class AwsPricingRateDetail(TimestampMixin, Base):
    __tablename__ = "aws_pricing_rate_details"
    __table_args__ = (
        UniqueConstraint("pricing_item_id", name="uq_aws_rate_pricing_item"),
        Index("ix_aws_rate_product_option", "product_id", "purchase_option", "rate_code"),
        Index("ix_aws_rate_import_batch", "import_batch_id"),
        CheckConstraint(
            "pricing_status IN ('active','unsupported','quarantined','withdrawn')",
            name="ck_aws_rate_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    pricing_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pricing_catalog_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("aws_pricing_products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rate_code: Mapped[str] = mapped_column(String(180), nullable=False)
    term_code: Mapped[str] = mapped_column(String(180), nullable=False)
    purchase_option: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_unit_aws: Mapped[str] = mapped_column(String(64), nullable=False)
    begin_range: Mapped[str] = mapped_column(String(80), nullable=False)
    end_range: Mapped[str] = mapped_column(String(80), nullable=False)
    rate_description: Mapped[str] = mapped_column(String(500), nullable=False)
    pricing_status: Mapped[str] = mapped_column(String(24), nullable=False)
    import_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("aws_pricing_import_batches.id", ondelete="RESTRICT"),
    )
    source_effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class AwsPricingSyncState(TimestampMixin, Base):
    __tablename__ = "aws_pricing_sync_state"
    __table_args__ = (
        UniqueConstraint("service_code", "region_code", name="uq_aws_sync_service_region"),
        CheckConstraint(
            "coverage_status IN ('never_synced','synced','partial','stale','failed')",
            name="ck_aws_sync_coverage_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    region_code: Mapped[str] = mapped_column(String(40), nullable=False)
    last_successful_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("aws_pricing_import_batches.id", ondelete="RESTRICT"),
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="never_synced",
    )
    coverage: Mapped[dict[str, Any] | None] = mapped_column(_AWS_JSON)
    error_summary: Mapped[str | None] = mapped_column(String(500))
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AwsPricingSyncRun(Base):
    """Durable orchestration attempts; price batches remain the financial source of truth."""

    __tablename__ = "aws_pricing_sync_runs"
    __table_args__ = (
        Index("ix_aws_pricing_sync_run_unit", "service_code", "region_code", "started_at"),
        Index("ix_aws_pricing_sync_run_status", "status", "next_retry_at"),
        CheckConstraint(
            "status IN ('running','unchanged','published','partial','failed',"
            "'interrupted','validated')",
            name="ck_aws_pricing_sync_run_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    region_code: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_reference: Mapped[str | None] = mapped_column(String(500))
    source_version: Mapped[str | None] = mapped_column(String(160))
    batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("aws_pricing_import_batches.id", ondelete="RESTRICT")
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    products_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rates_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rates_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rates_published: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(_AWS_JSON)
    coverage: Mapped[dict[str, Any] | None] = mapped_column(_AWS_JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_summary: Mapped[str | None] = mapped_column(String(500))


class AwsPricingSyncRequest(Base):
    """Durable, authorized single-unit manual sync submissions.

    The importer and worker are still the sole publishers of financial data.
    """

    __tablename__ = "aws_pricing_sync_requests"
    __table_args__ = (
        Index("ix_aws_sync_request_status", "status", "requested_at"),
        Index(
            "uq_aws_sync_request_active_unit",
            "service_code",
            "region_code",
            unique=True,
            postgresql_where=sa_text("status IN ('queued','running')"),
            sqlite_where=sa_text("status IN ('queued','running')"),
        ),
        CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_aws_sync_request_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    service_code: Mapped[str] = mapped_column(String(80), nullable=False)
    region_code: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    force: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(_AWS_JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
