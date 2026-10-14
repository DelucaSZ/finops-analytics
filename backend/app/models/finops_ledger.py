import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, utcnow


class FinOpsLedgerEntryType(StrEnum):
    SAVING = "SAVING"
    REALLOCATION = "REALLOCATION"
    ADJUSTMENT = "ADJUSTMENT"


class FinOpsLedgerDirection(StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class FinOpsLedgerSource(StrEnum):
    OPPORTUNITY = "OPPORTUNITY"
    MANUAL = "MANUAL"
    SYSTEM = "SYSTEM"


class FinOpsLedgerPeriodicity(StrEnum):
    ONE_TIME = "ONE_TIME"
    MONTHLY = "MONTHLY"


class FinOpsLedgerEntry(Base):
    """Append-only recognized FinOps financial movement.

    Estimated opportunity savings stay on Finding/OpportunityObservation. This table
    records only movements explicitly recognized by the FinOps flow.
    """

    __tablename__ = "finops_ledger_entries"
    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('SAVING', 'REALLOCATION', 'ADJUSTMENT')",
            name="ck_finops_ledger_entry_type",
        ),
        CheckConstraint(
            "direction IN ('CREDIT', 'DEBIT')",
            name="ck_finops_ledger_direction",
        ),
        CheckConstraint("amount > 0", name="ck_finops_ledger_amount_positive"),
        CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)",
            name="ck_finops_ledger_currency_iso_code",
        ),
        CheckConstraint(
            "source IN ('OPPORTUNITY', 'MANUAL', 'SYSTEM')",
            name="ck_finops_ledger_source",
        ),
        CheckConstraint(
            "periodicity IN ('ONE_TIME', 'MONTHLY')",
            name="ck_finops_ledger_periodicity",
        ),
        CheckConstraint(
            "reference_period_end IS NULL OR reference_period_start IS NOT NULL",
            name="ck_finops_ledger_reference_period_start_required",
        ),
        CheckConstraint(
            "reference_period_end IS NULL OR reference_period_end >= reference_period_start",
            name="ck_finops_ledger_reference_period_order",
        ),
        CheckConstraint(
            "source != 'OPPORTUNITY' OR "
            "(opportunity_id IS NOT NULL AND source_event_id IS NOT NULL "
            "AND idempotency_key IS NOT NULL)",
            name="ck_finops_ledger_opportunity_source_reference",
        ),
        CheckConstraint(
            "source != 'MANUAL' OR created_by IS NOT NULL",
            name="ck_finops_ledger_manual_actor",
        ),
        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id != id",
            name="ck_finops_ledger_not_self_reversal",
        ),
        UniqueConstraint("idempotency_key", name="uq_finops_ledger_idempotency_key"),
        UniqueConstraint("reversal_of_id", name="uq_finops_ledger_reversal_of"),
        Index(
            "ix_finops_ledger_currency_effective_at",
            "currency",
            "effective_at",
        ),
        Index(
            "ix_finops_ledger_account_effective_at",
            "cloud_account_id",
            "effective_at",
        ),
        Index(
            "ix_finops_ledger_provider_account_effective_at",
            "provider",
            "account_id",
            "effective_at",
        ),
        Index("ix_finops_ledger_type_effective_at", "entry_type", "effective_at"),
        Index("ix_finops_ledger_source_reference", "source", "source_reference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entry_type: Mapped[str] = mapped_column(String(24), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)

    provider: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    cloud_account_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("findings.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    source_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunity_status_history.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", nullable=False)

    periodicity: Mapped[str] = mapped_column(
        String(16),
        default=FinOpsLedgerPeriodicity.ONE_TIME.value,
        server_default=FinOpsLedgerPeriodicity.ONE_TIME.value,
        nullable=False,
    )
    reference_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
        index=True,
    )
    reversal_of_id: Mapped[str | None] = mapped_column(
        ForeignKey("finops_ledger_entries.id", ondelete="RESTRICT"),
        nullable=True,
    )


@event.listens_for(Session, "before_flush")
def _enforce_finops_ledger_append_only(session, _flush_context, _instances) -> None:
    for item in tuple(session.dirty):
        if isinstance(item, FinOpsLedgerEntry) and session.is_modified(
            item, include_collections=False
        ):
            raise ValueError(
                "FinOps ledger entries are append-only; create a reversal or adjustment"
            )
    for item in tuple(session.deleted):
        if isinstance(item, FinOpsLedgerEntry):
            raise ValueError("FinOps ledger entries are append-only and cannot be deleted")
