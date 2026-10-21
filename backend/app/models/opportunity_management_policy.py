from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class OpportunityCycleMode(StrEnum):
    CALENDAR_MONTH = "CALENDAR_MONTH"
    FIXED_DAYS = "FIXED_DAYS"


class OpportunityManagementPolicy(TimestampMixin, Base):
    """Global administrative policy for opportunity lifecycle automation."""

    __tablename__ = "opportunity_management_policies"
    __table_args__ = (
        UniqueConstraint("scope", name="uq_opportunity_management_policies_scope"),
        CheckConstraint(
            "cycle_mode IN ('CALENDAR_MONTH', 'FIXED_DAYS')",
            name="ck_opportunity_management_policies_cycle_mode",
        ),
        CheckConstraint(
            "cycle_length_days >= 7 AND cycle_length_days <= 365",
            name="ck_opportunity_management_policies_cycle_length",
        ),
        CheckConstraint(
            "treated_archive_days >= 1 AND treated_archive_days <= 3650",
            name="ck_opportunity_management_policies_treated_days",
        ),
        CheckConstraint(
            "rejected_archive_days >= 1 AND rejected_archive_days <= 3650",
            name="ck_opportunity_management_policies_rejected_days",
        ),
        CheckConstraint(
            "resolved_external_archive_days >= 1 AND resolved_external_archive_days <= 3650",
            name="ck_opportunity_management_policies_resolved_days",
        ),
        CheckConstraint(
            "open_archive_days >= 1 AND open_archive_days <= 3650",
            name="ck_opportunity_management_policies_open_days",
        ),
        CheckConstraint(
            "observation_retention_days >= 30 AND observation_retention_days <= 3650",
            name="ck_opportunity_management_policies_observation_days",
        ),
        CheckConstraint("version >= 1", name="ck_opportunity_management_policies_version"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="GLOBAL", server_default="GLOBAL"
    )
    cycle_mode: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=OpportunityCycleMode.CALENDAR_MONTH.value,
        server_default=OpportunityCycleMode.CALENDAR_MONTH.value,
    )
    cycle_length_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    cycle_timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    cycle_anchor_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    automatic_cycle_close_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    treated_archive_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    treated_archive_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    rejected_archive_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    rejected_archive_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    resolved_external_archive_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    resolved_external_archive_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    open_archive_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    open_archive_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    observation_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=400, server_default="400"
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class OpportunityMaintenanceState(Base):
    """Persistent cadence/checkpoint state shared by all workers."""

    __tablename__ = "opportunity_maintenance_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_opportunity_maintenance_state_singleton"),
        Index("ix_opportunity_maintenance_state_retention", "last_retention_run_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_retention_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_cycle_close_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_observation_cleanup_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_retention_result: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    last_cycle_close_result: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    last_observation_cleanup_result: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
