"""Persistent current-state and historical Inventory models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.inventory import InventoryPresenceStatus
from app.db.base import Base, TimestampMixin, utcnow


class InventoryResource(TimestampMixin, Base):
    __tablename__ = "inventory_resources"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "cloud_account_id",
            "resource_type",
            "resource_id",
            name="uq_inventory_resources_identity",
        ),
        Index(
            "ix_inventory_resources_account_presence_type",
            "cloud_account_id",
            "presence_status",
            "resource_type",
        ),
        Index(
            "ix_inventory_resources_provider_account_region",
            "provider",
            "cloud_account_id",
            "region",
        ),
        Index(
            "ix_inventory_resources_account_lifecycle",
            "cloud_account_id",
            "lifecycle_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    cloud_account_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    native_account_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    resource_id: Mapped[str] = mapped_column(String(2048), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    native_resource_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service: Mapped[str | None] = mapped_column(String(120), nullable=True)

    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    availability_zone: Mapped[str | None] = mapped_column(String(160), nullable=True)

    lifecycle_status: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    native_status: Mapped[str | None] = mapped_column(String(120), nullable=True)

    tags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    presence_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=InventoryPresenceStatus.ACTIVE.value
    )

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    first_seen_collection_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_collection_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL"), nullable=True
    )


class InventoryResourceObservation(Base):
    __tablename__ = "inventory_resource_observations"
    __table_args__ = (
        UniqueConstraint(
            "inventory_resource_id",
            "collection_run_id",
            name="uq_inventory_resource_observation_run",
        ),
        Index(
            "ix_inventory_observations_resource_observed",
            "inventory_resource_id",
            "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inventory_resource_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    collection_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    native_resource_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service: Mapped[str | None] = mapped_column(String(120), nullable=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    availability_zone: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(64), nullable=False)
    native_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
