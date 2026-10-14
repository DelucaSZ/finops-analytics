from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.cloud import normalize_provider
from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.finding import Finding
from app.models.finops_ledger import (
    FinOpsLedgerDirection,
    FinOpsLedgerEntry,
    FinOpsLedgerEntryType,
    FinOpsLedgerPeriodicity,
    FinOpsLedgerSource,
)
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User

logger = logging.getLogger(__name__)

MANUAL_CURRENCIES = frozenset({"BRL", "USD"})


class FinOpsLedgerError(ValueError):
    pass


class FinOpsLedgerNotFoundError(FinOpsLedgerError):
    pass


class FinOpsLedgerConflictError(FinOpsLedgerError):
    pass


@dataclass(frozen=True)
class FinOpsLedgerFilters:
    provider: str | None = None
    account_id: str | None = None
    currency: str | None = None
    entry_type: str | None = None
    direction: str | None = None
    source: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _enum_value(value: str, enum_type, field: str) -> str:
    try:
        return enum_type(str(value).strip().upper()).value
    except ValueError as exc:
        raise FinOpsLedgerError(f"Unsupported {field}: {value}") from exc


def _amount(value: Decimal | str | int) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FinOpsLedgerError("amount must be a valid Decimal value") from exc
    if not amount.is_finite() or amount <= 0:
        raise FinOpsLedgerError("amount must be greater than zero")
    return amount


def _currency(value: str) -> str:
    normalized = str(value).strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise FinOpsLedgerError("currency must be a three-letter ISO-style code")
    return normalized


class FinOpsLedgerService:
    def __init__(self, db: Session):
        self.db = db

    def _account(self, cloud_account_id: int, provider: str) -> CloudAccount:
        account = self.db.get(CloudAccount, cloud_account_id)
        if account is None:
            raise FinOpsLedgerError("Cloud account not found")
        if account.provider != provider:
            raise FinOpsLedgerError("provider does not match the selected cloud account")
        return account

    def _validate_opportunity_source(
        self,
        *,
        provider: str,
        account_id: str,
        opportunity_id: str | None,
        source_event_id: str | None,
        idempotency_key: str | None,
    ) -> tuple[str, str]:
        if not opportunity_id or not source_event_id or not idempotency_key:
            raise FinOpsLedgerError(
                "OPPORTUNITY entries require opportunity_id, source_event_id and idempotency_key"
            )
        finding = self.db.get(Finding, opportunity_id)
        event = self.db.get(OpportunityStatusHistory, source_event_id)
        if finding is None or event is None or event.opportunity_id != opportunity_id:
            raise FinOpsLedgerError("Invalid opportunity source reference")
        if event.to_status != "treated":
            raise FinOpsLedgerError("Opportunity source event must be a treatment transition")
        if finding.provider != provider or finding.account_id != account_id:
            raise FinOpsLedgerError("Opportunity provider/account does not match ledger account")
        return opportunity_id, source_event_id

    def create_entry(
        self,
        *,
        entry_type: str,
        direction: str,
        cloud_account_id: int,
        amount: Decimal | str | int,
        currency: str,
        effective_at: datetime,
        source: str,
        actor: User | None = None,
        description: str | None = None,
        source_reference: str | None = None,
        opportunity_id: str | None = None,
        source_event_id: str | None = None,
        idempotency_key: str | None = None,
        periodicity: str = FinOpsLedgerPeriodicity.ONE_TIME.value,
        reference_period_start: date | None = None,
        reference_period_end: date | None = None,
        context: dict[str, Any] | None = None,
    ) -> FinOpsLedgerEntry:
        type_value = _enum_value(entry_type, FinOpsLedgerEntryType, "entry_type")
        direction_value = _enum_value(direction, FinOpsLedgerDirection, "direction")
        source_value = _enum_value(source, FinOpsLedgerSource, "source")
        periodicity_value = _enum_value(periodicity, FinOpsLedgerPeriodicity, "periodicity")
        amount_value = _amount(amount)
        currency_value = _currency(currency)

        if type_value == FinOpsLedgerEntryType.SAVING.value and direction_value != "CREDIT":
            raise FinOpsLedgerError("SAVING entries must use CREDIT direction")
        if type_value == FinOpsLedgerEntryType.REALLOCATION.value and direction_value != "DEBIT":
            raise FinOpsLedgerError("REALLOCATION entries must use DEBIT direction")
        if reference_period_end is not None and reference_period_start is None:
            raise FinOpsLedgerError("reference_period_end requires reference_period_start")
        if (
            reference_period_start is not None
            and reference_period_end is not None
            and reference_period_end < reference_period_start
        ):
            raise FinOpsLedgerError("reference_period_end cannot precede reference_period_start")
        if source_value == FinOpsLedgerSource.MANUAL.value and actor is None:
            raise FinOpsLedgerError("MANUAL entries require an authenticated actor")

        account = self.db.get(CloudAccount, cloud_account_id)
        if account is None:
            raise FinOpsLedgerError("Cloud account not found")
        provider_value = normalize_provider(account.provider)
        account = self._account(cloud_account_id, provider_value)

        if source_value == FinOpsLedgerSource.OPPORTUNITY.value:
            opportunity_id, source_event_id = self._validate_opportunity_source(
                provider=provider_value,
                account_id=account.native_account_id,
                opportunity_id=opportunity_id,
                source_event_id=source_event_id,
                idempotency_key=idempotency_key,
            )
            source_reference = source_reference or opportunity_id

        key = idempotency_key.strip() if idempotency_key else None
        if key == "":
            key = None
        if key is not None and len(key) > 255:
            raise FinOpsLedgerError("idempotency_key must have at most 255 characters")

        entry = FinOpsLedgerEntry(
            entry_type=type_value,
            direction=direction_value,
            provider=provider_value,
            cloud_account_id=account.id,
            account_id=account.native_account_id,
            amount=amount_value,
            currency=currency_value,
            effective_at=_aware(effective_at),
            source=source_value,
            source_reference=source_reference,
            opportunity_id=opportunity_id,
            source_event_id=source_event_id,
            idempotency_key=key,
            description=(description or "").strip() or None,
            context=context or {},
            periodicity=periodicity_value,
            reference_period_start=reference_period_start,
            reference_period_end=reference_period_end,
            created_by=actor.id if actor is not None else None,
        )

        try:
            with self.db.begin_nested():
                self.db.add(entry)
                self.db.flush()
        except IntegrityError:
            if key is not None:
                existing = self.db.scalar(
                    select(FinOpsLedgerEntry).where(FinOpsLedgerEntry.idempotency_key == key)
                )
                if existing is not None:
                    return existing
            raise

        logger.info(
            "finops_ledger_entry_created entry_id=%s type=%s direction=%s currency=%s "
            "provider=%s source=%s",
            entry.id,
            entry.entry_type,
            entry.direction,
            entry.currency,
            entry.provider,
            entry.source,
        )
        return entry

    def create_manual_entry(
        self,
        *,
        entry_type: str,
        direction: str | None,
        provider: str,
        cloud_account_id: int,
        amount: Decimal | str | int,
        currency: str,
        effective_at: datetime,
        actor: User,
        description: str,
        manual_entry_request_id: str,
        periodicity: str = FinOpsLedgerPeriodicity.ONE_TIME.value,
        reference_period_start: date | None = None,
        reference_period_end: date | None = None,
    ) -> FinOpsLedgerEntry:
        """Create an authenticated manual movement without exposing provenance fields."""
        try:
            provider_value = normalize_provider(provider)
        except ValueError as exc:
            raise FinOpsLedgerError(f"Unsupported provider: {provider}") from exc
        account = self._account(cloud_account_id, provider_value)

        type_value = _enum_value(entry_type, FinOpsLedgerEntryType, "entry_type")
        if type_value == FinOpsLedgerEntryType.SAVING.value:
            if direction is not None and _enum_value(
                direction, FinOpsLedgerDirection, "direction"
            ) != FinOpsLedgerDirection.CREDIT.value:
                raise FinOpsLedgerError("SAVING entries must use CREDIT direction")
            direction_value = FinOpsLedgerDirection.CREDIT.value
        elif type_value == FinOpsLedgerEntryType.REALLOCATION.value:
            if direction is not None and _enum_value(
                direction, FinOpsLedgerDirection, "direction"
            ) != FinOpsLedgerDirection.DEBIT.value:
                raise FinOpsLedgerError("REALLOCATION entries must use DEBIT direction")
            direction_value = FinOpsLedgerDirection.DEBIT.value
        else:
            if direction is None:
                raise FinOpsLedgerError("ADJUSTMENT entries require direction")
            direction_value = _enum_value(direction, FinOpsLedgerDirection, "direction")

        currency_value = _currency(currency)
        if currency_value not in MANUAL_CURRENCIES:
            raise FinOpsLedgerError("Manual entries currently support BRL and USD currencies")

        normalized_description = description.strip()
        if len(normalized_description) < 3:
            raise FinOpsLedgerError("description must contain at least 3 characters")

        effective_value = _aware(effective_at)
        if effective_value.astimezone(UTC).date() > utcnow().astimezone(UTC).date():
            raise FinOpsLedgerError("effective_date cannot be in the future")

        request_id = str(manual_entry_request_id).strip()
        if not request_id:
            raise FinOpsLedgerError("manual_entry_request_id is required")
        key = f"manual:{request_id}"

        entry = self.create_entry(
            entry_type=type_value,
            direction=direction_value,
            cloud_account_id=account.id,
            amount=amount,
            currency=currency_value,
            effective_at=effective_value,
            source=FinOpsLedgerSource.MANUAL.value,
            actor=actor,
            description=normalized_description,
            idempotency_key=key,
            periodicity=periodicity,
            reference_period_start=reference_period_start,
            reference_period_end=reference_period_end,
            context={"manual_entry_request_id": request_id},
        )
        logger.info(
            "manual_finops_entry_created entry_id=%s entry_type=%s direction=%s currency=%s "
            "provider=%s account=%s actor=%s",
            entry.id,
            entry.entry_type,
            entry.direction,
            entry.currency,
            entry.provider,
            entry.account_id,
            actor.id,
        )
        return entry

    def get_entry(self, entry_id: str) -> FinOpsLedgerEntry:
        entry = self.db.get(FinOpsLedgerEntry, entry_id)
        if entry is None:
            raise FinOpsLedgerNotFoundError("FinOps ledger entry not found")
        return entry

    def reversal_map(self, entry_ids: list[str]) -> dict[str, str]:
        if not entry_ids:
            return {}
        rows = self.db.execute(
            select(FinOpsLedgerEntry.reversal_of_id, FinOpsLedgerEntry.id).where(
                FinOpsLedgerEntry.reversal_of_id.in_(entry_ids)
            )
        ).all()
        return {
            original_id: reversal_id
            for original_id, reversal_id in rows
            if original_id is not None
        }

    def reverse_entry(
        self,
        entry_id: str,
        *,
        actor: User | None,
        effective_at: datetime | None = None,
        description: str | None = None,
    ) -> FinOpsLedgerEntry:
        original = self.db.scalar(
            select(FinOpsLedgerEntry).where(FinOpsLedgerEntry.id == entry_id).with_for_update()
        )
        if original is None:
            raise FinOpsLedgerNotFoundError("FinOps ledger entry not found")
        if original.reversal_of_id is not None:
            raise FinOpsLedgerConflictError("A reversal entry cannot be reversed by this operation")
        existing = self.db.scalar(
            select(FinOpsLedgerEntry).where(FinOpsLedgerEntry.reversal_of_id == original.id)
        )
        if existing is not None:
            raise FinOpsLedgerConflictError("FinOps ledger entry is already reversed")

        reverse_direction = (
            FinOpsLedgerDirection.DEBIT.value
            if original.direction == FinOpsLedgerDirection.CREDIT.value
            else FinOpsLedgerDirection.CREDIT.value
        )
        normalized_description = (description or f"Reversal of ledger entry {original.id}").strip()
        reversal = FinOpsLedgerEntry(
            entry_type=FinOpsLedgerEntryType.ADJUSTMENT.value,
            direction=reverse_direction,
            provider=original.provider,
            cloud_account_id=original.cloud_account_id,
            account_id=original.account_id,
            amount=original.amount,
            currency=original.currency,
            effective_at=_aware(effective_at or utcnow()),
            source=FinOpsLedgerSource.SYSTEM.value,
            source_reference=original.id,
            idempotency_key=f"finops-reversal:{original.id}",
            description=normalized_description,
            context={"reversal_of": original.id, "reason": normalized_description},
            periodicity=original.periodicity,
            reference_period_start=original.reference_period_start,
            reference_period_end=original.reference_period_end,
            created_by=actor.id if actor is not None else None,
            reversal_of_id=original.id,
        )
        try:
            with self.db.begin_nested():
                self.db.add(reversal)
                self.db.flush()
        except IntegrityError as exc:
            raise FinOpsLedgerConflictError("FinOps ledger entry is already reversed") from exc

        logger.info(
            "finops_entry_reversed entry_id=%s reversal_id=%s entry_type=%s direction=%s "
            "currency=%s provider=%s account=%s actor=%s",
            original.id,
            reversal.id,
            reversal.entry_type,
            reversal.direction,
            reversal.currency,
            reversal.provider,
            reversal.account_id,
            actor.id if actor is not None else "system",
        )
        return reversal

    @staticmethod
    def _conditions(filters: FinOpsLedgerFilters) -> list:
        conditions = []
        if filters.provider:
            conditions.append(FinOpsLedgerEntry.provider == normalize_provider(filters.provider))
        if filters.account_id:
            conditions.append(FinOpsLedgerEntry.account_id == filters.account_id)
        if filters.currency:
            conditions.append(FinOpsLedgerEntry.currency == _currency(filters.currency))
        if filters.entry_type:
            conditions.append(
                FinOpsLedgerEntry.entry_type
                == _enum_value(filters.entry_type, FinOpsLedgerEntryType, "entry_type")
            )
        if filters.direction:
            conditions.append(
                FinOpsLedgerEntry.direction
                == _enum_value(filters.direction, FinOpsLedgerDirection, "direction")
            )
        if filters.source:
            conditions.append(
                FinOpsLedgerEntry.source
                == _enum_value(filters.source, FinOpsLedgerSource, "source")
            )
        if filters.effective_from:
            conditions.append(FinOpsLedgerEntry.effective_at >= _aware(filters.effective_from))
        if filters.effective_to:
            conditions.append(FinOpsLedgerEntry.effective_at < _aware(filters.effective_to))
        return conditions

    def list_entries(
        self,
        filters: FinOpsLedgerFilters,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        conditions = self._conditions(filters)
        total = (
            self.db.scalar(select(func.count()).select_from(FinOpsLedgerEntry).where(*conditions))
            or 0
        )
        items = list(
            self.db.scalars(
                select(FinOpsLedgerEntry)
                .where(*conditions)
                .order_by(
                    FinOpsLedgerEntry.effective_at.desc(),
                    FinOpsLedgerEntry.created_at.desc(),
                    FinOpsLedgerEntry.id.desc(),
                )
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        )
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
        }

    def calculate_balances(self, filters: FinOpsLedgerFilters) -> dict[str, dict[str, Decimal]]:
        conditions = self._conditions(filters)
        rows = self.db.execute(
            select(
                FinOpsLedgerEntry.currency,
                FinOpsLedgerEntry.direction,
                func.sum(FinOpsLedgerEntry.amount),
            )
            .where(*conditions)
            .group_by(FinOpsLedgerEntry.currency, FinOpsLedgerEntry.direction)
            .order_by(FinOpsLedgerEntry.currency)
        ).all()
        result: dict[str, dict[str, Decimal]] = {}
        for currency, direction, amount in rows:
            bucket = result.setdefault(
                currency,
                {"credits": Decimal("0"), "debits": Decimal("0"), "balance": Decimal("0")},
            )
            key = "credits" if direction == FinOpsLedgerDirection.CREDIT.value else "debits"
            bucket[key] += Decimal(amount)
        for bucket in result.values():
            bucket["balance"] = bucket["credits"] - bucket["debits"]
        return result
