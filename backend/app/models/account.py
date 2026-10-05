import uuid
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
    inspect,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.cloud import CloudProvider
from app.db.base import Base, TimestampMixin, utcnow


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
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scan_interval_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    next_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    aws_configuration: Mapped["AwsAccount | None"] = relationship(
        back_populates="cloud_account",
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
        uselist=False,
    )
    oci_configuration: Mapped["OciAccountConfiguration | None"] = relationship(
        back_populates="cloud_account",
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
        uselist=False,
    )


class AwsAccount(TimestampMixin, Base):
    """AWS-specific configuration plus compatibility mirrors.

    CloudAccount is the source of truth for provider/native identity, name,
    administrative enablement, connection state and scheduling. The legacy common
    and scheduling columns remain readable mirrors for compatibility with the
    existing AWS contract, scans and old images.
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


class OciAccountConfiguration(TimestampMixin, Base):
    __tablename__ = "oci_account_configurations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cloud_account_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_ocid: Mapped[str] = mapped_column(String(255), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_regions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    compartment_ocids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    include_root_compartment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    include_subcompartments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    private_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_key_password_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_key_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credential_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    configuration_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    cloud_account: Mapped[CloudAccount] = relationship(back_populates="oci_configuration")

    @property
    def credentials_configured(self) -> bool:
        return bool(self.private_key_ciphertext)


class CloudAccountAuditEvent(Base):
    __tablename__ = "cloud_account_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    native_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


def _adopt_legacy_schedule_write(account: AwsAccount, *, creating: bool) -> None:
    """Map legacy AWS schedule writes into the authoritative CloudAccount fields."""

    cloud_account = account.cloud_account
    if cloud_account is None:
        return
    state = inspect(account)
    schedule_changed = creating or any(
        state.attrs[field].history.has_changes()
        for field in ("schedule_enabled", "scan_interval_hours", "next_scan_at")
    )
    if not schedule_changed:
        return
    cloud_account.schedule_enabled = bool(account.schedule_enabled)
    cloud_account.scan_interval_hours = account.scan_interval_hours or 24
    cloud_account.next_scan_at = account.next_scan_at


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
    account.schedule_enabled = cloud_account.schedule_enabled
    account.scan_interval_hours = cloud_account.scan_interval_hours
    account.next_scan_at = cloud_account.next_scan_at


@event.listens_for(Session, "before_flush")
def _synchronize_aws_compatibility_mirrors(session, _flush_context, _instances) -> None:
    """Bridge legacy fixtures/writes, then keep AWS compatibility columns as mirrors."""

    candidates: list[tuple[AwsAccount, bool]] = []
    for item in tuple(session.new) + tuple(session.dirty):
        if isinstance(item, AwsAccount):
            creating = item in session.new
            if item.cloud_account is None and creating:
                item.cloud_account = CloudAccount(
                    provider=CloudProvider.AWS.value,
                    native_account_id=item.aws_account_id,
                    name=item.name,
                    enabled=True if item.enabled is None else item.enabled,
                    connection_status=item.connection_status or "untested",
                    last_connection_test_at=item.last_connection_test_at,
                    last_error=item.last_error,
                    schedule_enabled=(
                        False if item.schedule_enabled is None else item.schedule_enabled
                    ),
                    scan_interval_hours=item.scan_interval_hours or 24,
                    next_scan_at=item.next_scan_at,
                )
            candidates.append((item, creating))
        elif isinstance(item, CloudAccount) and item.aws_configuration is not None:
            candidates.append((item.aws_configuration, False))

    seen: set[int] = set()
    for account, creating in candidates:
        marker = id(account)
        if marker in seen:
            continue
        seen.add(marker)
        _adopt_legacy_schedule_write(account, creating=creating)
        _sync_aws_mirror(account)
