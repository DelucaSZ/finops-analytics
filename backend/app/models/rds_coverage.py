from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class RdsReservationCoverageRun(TimestampMixin, Base):
    __tablename__ = "rds_reservation_coverage_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inventory_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    accounts_analyzed: Mapped[int] = mapped_column(default=0, nullable=False)
    instances_analyzed: Mapped[int] = mapped_column(default=0, nullable=False)
    reservations_analyzed: Mapped[int] = mapped_column(default=0, nullable=False)
    fully_covered: Mapped[int] = mapped_column(default=0, nullable=False)
    partially_covered: Mapped[int] = mapped_column(default=0, nullable=False)
    uncovered: Mapped[int] = mapped_column(default=0, nullable=False)
    unknown: Mapped[int] = mapped_column(default=0, nullable=False)
    required_units: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), default=Decimal("0"), nullable=False
    )
    covered_units: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), default=Decimal("0"), nullable=False
    )
    uncovered_units: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), default=Decimal("0"), nullable=False
    )
    reserved_units: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), default=Decimal("0"), nullable=False
    )
    allocated_reserved_units: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), default=Decimal("0"), nullable=False
    )
    unused_reserved_units: Mapped[Decimal] = mapped_column(
        Numeric(24, 6), default=Decimal("0"), nullable=False
    )
    calculated_coverage_percentage: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    aws_observed_coverage_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    reconciliation_status: Mapped[str] = mapped_column(
        String(24), default="NOT_AVAILABLE", nullable=False
    )
    reconciliation_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_validation_status: Mapped[str] = mapped_column(
        String(24), default="NOT_AVAILABLE", nullable=False
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class RdsInstanceReservationCoverage(TimestampMixin, Base):
    __tablename__ = "rds_instance_reservation_coverage"
    __table_args__ = (
        UniqueConstraint(
            "coverage_run_id", "rds_instance_id", name="uq_rds_instance_coverage_run_instance"
        ),
        Index("ix_rds_instance_coverage_run_status", "coverage_run_id", "coverage_status"),
        Index("ix_rds_instance_coverage_account_region", "account_id", "region"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    coverage_run_id: Mapped[int] = mapped_column(
        ForeignKey("rds_reservation_coverage_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rds_instance_id: Mapped[int] = mapped_column(
        ForeignKey("aws_rds_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    required_units: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    covered_units: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    uncovered_units: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    coverage_percentage: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    coverage_status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    coverage_scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    calculation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RdsReservationAllocation(TimestampMixin, Base):
    __tablename__ = "rds_reservation_allocations"
    __table_args__ = (
        UniqueConstraint(
            "coverage_run_id",
            "reservation_id",
            "rds_instance_id",
            "match_type",
            name="uq_rds_reservation_allocation",
        ),
        Index("ix_rds_reservation_alloc_run_reservation", "coverage_run_id", "reservation_id"),
        Index("ix_rds_reservation_alloc_run_instance", "coverage_run_id", "rds_instance_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    coverage_run_id: Mapped[int] = mapped_column(
        ForeignKey("rds_reservation_coverage_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("aws_rds_reserved_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rds_instance_id: Mapped[int] = mapped_column(
        ForeignKey("aws_rds_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allocated_units: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    allocation_percentage: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    match_type: Mapped[str] = mapped_column(String(24), nullable=False)
    allocation_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RdsReservationUtilization(TimestampMixin, Base):
    __tablename__ = "rds_reservation_utilization"
    __table_args__ = (
        UniqueConstraint(
            "coverage_run_id", "reservation_id", name="uq_rds_reservation_utilization_run"
        ),
        Index("ix_rds_reservation_util_run_reservation", "coverage_run_id", "reservation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    coverage_run_id: Mapped[int] = mapped_column(
        ForeignKey("rds_reservation_coverage_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("aws_rds_reserved_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_units: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    allocated_units: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    unused_units: Mapped[Decimal] = mapped_column(Numeric(24, 6), nullable=False)
    utilization_percentage: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
