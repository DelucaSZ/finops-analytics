from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import case, extract, func, literal, or_, select
from sqlalchemy.orm import Session, aliased

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
from app.models.user import User


@dataclass(frozen=True)
class FinOpsFlowFilters:
    provider: str | None = None
    account_id: str | None = None
    currency: str | None = None
    source: str | None = None
    entry_type: str | None = None
    periodicity: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    search: str | None = None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _currency(value: str) -> str:
    normalized = str(value).strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("currency must be a three-letter ISO-style code")
    return normalized


def _enum_value(value: str, enum_type, field: str) -> str:
    try:
        return enum_type(str(value).strip().upper()).value
    except ValueError as exc:
        raise ValueError(f"Unsupported {field}: {value}") from exc


class FinOpsFlowAnalyticsService:
    """Read model for the FinOps Flow dashboard.

    Ledger entries remain the only financial source of truth. Reversal rows are
    classified by the type/source of their original entry for analytical metrics,
    while their signed financial effect stays exactly as recorded in the ledger.
    Aggregations are always segmented by currency and periodicity.
    """

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _aliases():
        entry = aliased(FinOpsLedgerEntry, name="flow_entry")
        original = aliased(FinOpsLedgerEntry, name="flow_original")
        finding = aliased(Finding, name="flow_finding")
        account = aliased(CloudAccount, name="flow_account")
        actor = aliased(User, name="flow_actor")
        return entry, original, finding, account, actor

    @staticmethod
    def _logical(entry, original):
        logical_type = func.coalesce(original.entry_type, entry.entry_type)
        logical_source = func.coalesce(original.source, entry.source)
        logical_opportunity_id = func.coalesce(original.opportunity_id, entry.opportunity_id)
        return logical_type, logical_source, logical_opportunity_id

    def _conditions(
        self,
        filters: FinOpsFlowFilters,
        entry,
        original,
        finding,
        *,
        include_dates: bool = True,
    ) -> list[Any]:
        logical_type, logical_source, logical_opportunity_id = self._logical(entry, original)
        conditions: list[Any] = []
        if filters.provider:
            conditions.append(entry.provider == normalize_provider(filters.provider))
        if filters.account_id:
            conditions.append(entry.account_id == str(filters.account_id).strip())
        if filters.currency:
            conditions.append(entry.currency == _currency(filters.currency))
        if filters.source:
            conditions.append(
                logical_source
                == _enum_value(filters.source, FinOpsLedgerSource, "source")
            )
        if filters.entry_type:
            conditions.append(
                logical_type
                == _enum_value(filters.entry_type, FinOpsLedgerEntryType, "entry_type")
            )
        if filters.periodicity:
            conditions.append(
                entry.periodicity
                == _enum_value(
                    filters.periodicity,
                    FinOpsLedgerPeriodicity,
                    "periodicity",
                )
            )
        if include_dates and filters.effective_from:
            conditions.append(entry.effective_at >= _aware(filters.effective_from))
        if include_dates and filters.effective_to:
            conditions.append(entry.effective_at < _aware(filters.effective_to))
        if filters.search:
            pattern = f"%{filters.search.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(func.coalesce(entry.description, "")).like(pattern),
                    func.lower(entry.account_id).like(pattern),
                    func.lower(func.coalesce(finding.title, "")).like(pattern),
                    func.lower(func.coalesce(finding.resource_id, "")).like(pattern),
                    func.lower(func.coalesce(logical_opportunity_id, "")).like(pattern),
                )
            )
        return conditions

    @staticmethod
    def _metric_expressions(entry, original):
        logical_type, _, _ = FinOpsFlowAnalyticsService._logical(entry, original)
        zero = literal(Decimal("0"))
        signed_balance = case(
            (entry.direction == FinOpsLedgerDirection.CREDIT.value, entry.amount),
            else_=-entry.amount,
        )
        recognized_savings = case(
            (logical_type == FinOpsLedgerEntryType.SAVING.value, signed_balance),
            else_=zero,
        )
        reallocated = case(
            (logical_type == FinOpsLedgerEntryType.REALLOCATION.value, -signed_balance),
            else_=zero,
        )
        adjustment_net = case(
            (logical_type == FinOpsLedgerEntryType.ADJUSTMENT.value, signed_balance),
            else_=zero,
        )
        return recognized_savings, reallocated, adjustment_net, signed_balance

    def summary(self, filters: FinOpsFlowFilters) -> list[dict[str, Any]]:
        entry, original, finding, _, _ = self._aliases()
        recognized, reallocated, adjustment, balance = self._metric_expressions(
            entry,
            original,
        )
        conditions = self._conditions(filters, entry, original, finding)
        rows = self.db.execute(
            select(
                entry.currency,
                entry.periodicity,
                func.coalesce(func.sum(recognized), 0),
                func.coalesce(func.sum(reallocated), 0),
                func.coalesce(func.sum(adjustment), 0),
                func.coalesce(func.sum(balance), 0),
            )
            .select_from(entry)
            .outerjoin(original, entry.reversal_of_id == original.id)
            .outerjoin(
                finding,
                finding.id == func.coalesce(original.opportunity_id, entry.opportunity_id),
            )
            .where(*conditions)
            .group_by(entry.currency, entry.periodicity)
            .order_by(entry.currency, entry.periodicity)
        ).all()
        return [
            {
                "currency": currency,
                "basis": periodicity,
                "recognized_savings": Decimal(recognized_value),
                "reallocated": Decimal(reallocated_value),
                "adjustment_net": Decimal(adjustment_value),
                "balance": Decimal(balance_value),
            }
            for (
                currency,
                periodicity,
                recognized_value,
                reallocated_value,
                adjustment_value,
                balance_value,
            ) in rows
        ]

    @staticmethod
    def _granularity(filters: FinOpsFlowFilters) -> str:
        if filters.effective_from and filters.effective_to:
            span = _aware(filters.effective_to) - _aware(filters.effective_from)
            if span.days <= 45:
                return "day"
        return "month"

    def _opening_balances(
        self,
        filters: FinOpsFlowFilters,
    ) -> dict[tuple[str, str], Decimal]:
        if not filters.effective_from:
            return {}
        entry, original, finding, _, _ = self._aliases()
        _, _, _, balance = self._metric_expressions(entry, original)
        conditions = self._conditions(
            filters,
            entry,
            original,
            finding,
            include_dates=False,
        )
        conditions.append(entry.effective_at < _aware(filters.effective_from))
        rows = self.db.execute(
            select(
                entry.currency,
                entry.periodicity,
                func.coalesce(func.sum(balance), 0),
            )
            .select_from(entry)
            .outerjoin(original, entry.reversal_of_id == original.id)
            .outerjoin(
                finding,
                finding.id == func.coalesce(original.opportunity_id, entry.opportunity_id),
            )
            .where(*conditions)
            .group_by(entry.currency, entry.periodicity)
        ).all()
        return {
            (currency, periodicity): Decimal(value)
            for currency, periodicity, value in rows
        }

    def timeseries(
        self,
        filters: FinOpsFlowFilters,
    ) -> tuple[str, list[dict[str, Any]]]:
        entry, original, finding, _, _ = self._aliases()
        recognized, reallocated, adjustment, balance = self._metric_expressions(
            entry,
            original,
        )
        conditions = self._conditions(filters, entry, original, finding)
        granularity = self._granularity(filters)
        year = extract("year", entry.effective_at)
        month = extract("month", entry.effective_at)
        dimensions: list[Any] = [year, month]
        day = extract("day", entry.effective_at)
        if granularity == "day":
            dimensions.append(day)

        rows = self.db.execute(
            select(
                entry.currency,
                entry.periodicity,
                *dimensions,
                func.coalesce(func.sum(recognized), 0),
                func.coalesce(func.sum(reallocated), 0),
                func.coalesce(func.sum(adjustment), 0),
                func.coalesce(func.sum(balance), 0),
            )
            .select_from(entry)
            .outerjoin(original, entry.reversal_of_id == original.id)
            .outerjoin(
                finding,
                finding.id == func.coalesce(original.opportunity_id, entry.opportunity_id),
            )
            .where(*conditions)
            .group_by(entry.currency, entry.periodicity, *dimensions)
            .order_by(entry.currency, entry.periodicity, *dimensions)
        ).all()

        running = defaultdict(lambda: Decimal("0"))
        running.update(self._opening_balances(filters))
        points: list[dict[str, Any]] = []
        for row in rows:
            currency = row[0]
            basis = row[1]
            year_value = int(row[2])
            month_value = int(row[3])
            offset = 4
            if granularity == "day":
                day_value = int(row[4])
                bucket = date(year_value, month_value, day_value).isoformat()
                offset = 5
            else:
                bucket = f"{year_value:04d}-{month_value:02d}"
            recognized_value = Decimal(row[offset])
            reallocated_value = Decimal(row[offset + 1])
            adjustment_value = Decimal(row[offset + 2])
            balance_delta = Decimal(row[offset + 3])
            key = (currency, basis)
            running[key] += balance_delta
            points.append(
                {
                    "currency": currency,
                    "basis": basis,
                    "bucket": bucket,
                    "recognized_savings": recognized_value,
                    "reallocated": reallocated_value,
                    "adjustment_net": adjustment_value,
                    "balance_delta": balance_delta,
                    "cumulative_balance": running[key],
                }
            )
        return granularity, points

    def breakdowns(
        self,
        filters: FinOpsFlowFilters,
        *,
        top_n: int = 10,
    ) -> dict[str, list[dict[str, Any]]]:
        entry, original, finding, account, _ = self._aliases()
        recognized, _, _, _ = self._metric_expressions(entry, original)
        conditions = self._conditions(filters, entry, original, finding)
        account_rows = self.db.execute(
            select(
                entry.currency,
                entry.periodicity,
                entry.account_id,
                account.name,
                func.coalesce(func.sum(recognized), 0),
            )
            .select_from(entry)
            .outerjoin(original, entry.reversal_of_id == original.id)
            .outerjoin(
                finding,
                finding.id == func.coalesce(original.opportunity_id, entry.opportunity_id),
            )
            .join(account, account.id == entry.cloud_account_id)
            .where(*conditions)
            .group_by(entry.currency, entry.periodicity, entry.account_id, account.name)
        ).all()

        grouped_accounts: dict[
            tuple[str, str],
            list[tuple[str, str | None, Decimal]],
        ] = defaultdict(list)
        for currency, basis, account_id, account_name, value in account_rows:
            grouped_accounts[(currency, basis)].append(
                (account_id, account_name, Decimal(value))
            )

        by_account: list[dict[str, Any]] = []
        for (currency, basis), items in sorted(grouped_accounts.items()):
            ordered = sorted(items, key=lambda item: item[2], reverse=True)
            for account_id, account_name, value in ordered[:top_n]:
                by_account.append(
                    {
                        "currency": currency,
                        "basis": basis,
                        "account_id": account_id,
                        "account_name": account_name,
                        "recognized_savings": value,
                    }
                )
            remainder = ordered[top_n:]
            if remainder:
                by_account.append(
                    {
                        "currency": currency,
                        "basis": basis,
                        "account_id": "__other__",
                        "account_name": "Outros",
                        "recognized_savings": sum(
                            (item[2] for item in remainder), Decimal("0")
                        ),
                    }
                )

        _, logical_source, _ = self._logical(entry, original)
        source_rows = self.db.execute(
            select(
                entry.currency,
                entry.periodicity,
                logical_source,
                func.coalesce(func.sum(recognized), 0),
            )
            .select_from(entry)
            .outerjoin(original, entry.reversal_of_id == original.id)
            .outerjoin(
                finding,
                finding.id == func.coalesce(original.opportunity_id, entry.opportunity_id),
            )
            .where(*conditions)
            .group_by(entry.currency, entry.periodicity, logical_source)
            .order_by(entry.currency, entry.periodicity, logical_source)
        ).all()
        by_source = [
            {
                "currency": currency,
                "basis": basis,
                "source": source,
                "recognized_savings": Decimal(value),
            }
            for currency, basis, source, value in source_rows
        ]
        return {"by_account": by_account, "by_source": by_source}

    def list_entries(
        self,
        filters: FinOpsFlowFilters,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        entry, original, finding, account, actor = self._aliases()
        logical_type, logical_source, logical_opportunity_id = self._logical(
            entry,
            original,
        )
        conditions = self._conditions(filters, entry, original, finding)

        def joins(stmt):
            return stmt.outerjoin(
                original,
                entry.reversal_of_id == original.id,
            ).outerjoin(
                finding,
                finding.id == logical_opportunity_id,
            )

        total_stmt = joins(select(func.count()).select_from(entry)).where(*conditions)
        total = self.db.scalar(total_stmt) or 0

        rows = self.db.execute(
            joins(
                select(
                    entry,
                    account.name,
                    actor.name,
                    finding.title,
                    finding.service,
                    finding.resource_id,
                    logical_type.label("logical_entry_type"),
                    logical_source.label("logical_source"),
                ).select_from(entry)
            )
            .join(account, account.id == entry.cloud_account_id)
            .outerjoin(actor, actor.id == entry.created_by)
            .where(*conditions)
            .order_by(entry.effective_at.desc(), entry.created_at.desc(), entry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        entries = [row[0] for row in rows]
        entry_ids = [item.id for item in entries]
        reversal_rows = (
            self.db.execute(
                select(FinOpsLedgerEntry.reversal_of_id, FinOpsLedgerEntry.id).where(
                    FinOpsLedgerEntry.reversal_of_id.in_(entry_ids)
                )
            ).all()
            if entry_ids
            else []
        )
        reversed_by = {
            original_id: reversal_id
            for original_id, reversal_id in reversal_rows
            if original_id is not None
        }

        items = []
        for row in rows:
            item = row[0]
            items.append(
                {
                    "entry": item,
                    "account_name": row[1],
                    "created_by_name": row[2],
                    "opportunity_title": row[3],
                    "opportunity_service": row[4],
                    "opportunity_resource_id": row[5],
                    "logical_entry_type": row[6],
                    "logical_source": row[7],
                    "is_reversal": item.reversal_of_id is not None,
                    "is_reversed": item.id in reversed_by,
                    "reversed_by_id": reversed_by.get(item.id),
                }
            )
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if total else 0,
        }

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        entry, original, finding, account, actor = self._aliases()
        logical_type, logical_source, logical_opportunity_id = self._logical(
            entry,
            original,
        )
        row = self.db.execute(
            select(
                entry,
                account.name,
                actor.name,
                finding.title,
                finding.service,
                finding.resource_id,
                logical_type,
                logical_source,
            )
            .select_from(entry)
            .outerjoin(original, entry.reversal_of_id == original.id)
            .outerjoin(finding, finding.id == logical_opportunity_id)
            .join(account, account.id == entry.cloud_account_id)
            .outerjoin(actor, actor.id == entry.created_by)
            .where(entry.id == entry_id)
        ).first()
        if row is None:
            return None
        item = row[0]
        reversed_by_id = self.db.scalar(
            select(FinOpsLedgerEntry.id).where(
                FinOpsLedgerEntry.reversal_of_id == item.id
            )
        )
        return {
            "entry": item,
            "account_name": row[1],
            "created_by_name": row[2],
            "opportunity_title": row[3],
            "opportunity_service": row[4],
            "opportunity_resource_id": row[5],
            "logical_entry_type": row[6],
            "logical_source": row[7],
            "is_reversal": item.reversal_of_id is not None,
            "is_reversed": reversed_by_id is not None,
            "reversed_by_id": reversed_by_id,
        }

    def options(self, filters: FinOpsFlowFilters) -> dict[str, list[str]]:
        entry, original, finding, _, _ = self._aliases()
        _, logical_source, _ = self._logical(entry, original)
        conditions = self._conditions(filters, entry, original, finding)
        base = (
            select(entry.currency, entry.periodicity, entry.provider, logical_source)
            .select_from(entry)
            .outerjoin(original, entry.reversal_of_id == original.id)
            .outerjoin(
                finding,
                finding.id == func.coalesce(original.opportunity_id, entry.opportunity_id),
            )
            .where(*conditions)
            .distinct()
        )
        rows = self.db.execute(base).all()
        return {
            "currencies": sorted({row[0] for row in rows}),
            "periodicities": sorted({row[1] for row in rows}),
            "providers": sorted({row[2] for row in rows}),
            "sources": sorted({row[3] for row in rows}),
        }

    @staticmethod
    def generated_at() -> datetime:
        return utcnow()
