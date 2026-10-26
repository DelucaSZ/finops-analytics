from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, utcnow


class AwsRdsInstance(TimestampMixin, Base):
    __tablename__ = "aws_rds_instances"
    __table_args__ = (
        UniqueConstraint(
            "cloud_account_id",
            "region",
            "db_instance_arn",
            name="uq_aws_rds_instances_account_region_arn",
        ),
        Index(
            "ix_aws_rds_instances_account_region_active",
            "cloud_account_id",
            "region",
            "is_active",
        ),
        Index(
            "ix_aws_rds_instances_engine_class",
            "engine_normalized",
            "db_instance_class",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cloud_account_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    db_instance_identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    db_instance_arn: Mapped[str] = mapped_column(String(512), nullable=False)
    db_instance_class: Mapped[str] = mapped_column(String(64), nullable=False)
    class_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    instance_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    instance_size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_normalized: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    engine_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    license_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    coverage_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    multi_az: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deployment_topology: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cluster_storage_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    availability_zone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    secondary_availability_zone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    storage_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allocated_storage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    iops: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_throughput: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publicly_accessible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cluster_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vpc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    processor_features: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    option_group_memberships: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    parameter_groups: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    aws_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class AwsRdsReservedInstance(TimestampMixin, Base):
    __tablename__ = "aws_rds_reserved_instances"
    __table_args__ = (
        UniqueConstraint(
            "cloud_account_id",
            "region",
            "reserved_db_instance_id",
            name="uq_aws_rds_reserved_account_region_id",
        ),
        Index(
            "ix_aws_rds_reserved_account_region_active",
            "cloud_account_id",
            "region",
            "is_active",
        ),
        Index(
            "ix_aws_rds_reserved_engine_class",
            "engine_normalized",
            "db_instance_class",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cloud_account_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reserved_db_instance_id: Mapped[str] = mapped_column(String(255), nullable=False)
    offering_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    db_instance_class: Mapped[str] = mapped_column(String(64), nullable=False)
    class_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True)
    instance_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    instance_size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product_description: Mapped[str] = mapped_column(String(255), nullable=False)
    engine_normalized: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instance_count: Mapped[int] = mapped_column(Integer, nullable=False)
    multi_az: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    offering_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    offering_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    fixed_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recurring_charges: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lease_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    expiration_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
