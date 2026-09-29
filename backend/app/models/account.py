from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.cloud import CloudProvider
from app.db.base import Base, TimestampMixin


class CloudAccount(TimestampMixin, Base):
    __tablename__ = "cloud_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "native_account_id",
            name="uq_cloud_accounts_provider_native_account",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    native_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    connection_status: Mapped[str] = mapped_column(String(24), default="untested", nullable=False)
    last_connection_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    aws_configuration: Mapped["AwsAccount | None"] = relationship(
        back_populates="cloud_account",
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
        uselist=False,
    )


class AwsAccount(TimestampMixin, Base):
    """AWS-specific configuration plus compatibility mirrors.

    CloudAccount is the source of truth for provider/native identity, name,
    administrative enablement and connection state. The legacy common columns remain
    readable for compatibility with the existing AWS contract, scans and old images.
    """

    __tablename__ = "aws_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cloud_account_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Compatibility mirrors: synchronized from CloudAccount before every flush.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    aws_account_id: Mapped[str] = mapped_column(String(12), unique=True, index=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_status: Mapped[str] = mapped_column(String(24), default="untested")
    last_connection_test_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    role_arn: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    regions: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["sa-east-1"])
    is_management_account: Mapped[bool] = mapped_column(Boolean, default=False)
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    scan_interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cloud_account: Mapped[CloudAccount] = relationship(back_populates="aws_configuration")


def _sync_aws_mirror(account: AwsAccount) -> None:
    cloud_account = account.cloud_account
    if cloud_account is None:
        return
    if cloud_account.provider != CloudProvider.AWS.value:
        raise ValueError("AWS configuration must reference an AWS CloudAccount")

    account.aws_account_id = cloud_account.native_account_id
    account.name = cloud_account.name
    account.enabled = cloud_account.enabled
    account.connection_status = cloud_account.connection_status
    account.last_connection_test_at = cloud_account.last_connection_test_at
    account.last_error = cloud_account.last_error


@event.listens_for(Session, "before_flush")
def _synchronize_aws_compatibility_mirrors(session, _flush_context, _instances) -> None:
    """Bridge legacy fixtures once, then keep common AWS fields read-only mirrors."""

    candidates: list[AwsAccount] = []
    for item in tuple(session.new) + tuple(session.dirty):
        if isinstance(item, AwsAccount):
            if item.cloud_account is None and item in session.new:
                item.cloud_account = CloudAccount(
                    provider=CloudProvider.AWS.value,
                    native_account_id=item.aws_account_id,
                    name=item.name,
                    enabled=True if item.enabled is None else item.enabled,
                    connection_status=item.connection_status or "untested",
                    last_connection_test_at=item.last_connection_test_at,
                    last_error=item.last_error,
                )
            candidates.append(item)
        elif isinstance(item, CloudAccount) and item.aws_configuration is not None:
            candidates.append(item.aws_configuration)

    seen: set[int] = set()
    for account in candidates:
        marker = id(account)
        if marker in seen:
            continue
        seen.add(marker)
        _sync_aws_mirror(account)
