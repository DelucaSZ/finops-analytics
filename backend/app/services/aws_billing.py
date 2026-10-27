from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.cloud import CloudProvider
from app.core.config import settings
from app.models.account import AwsAccount, CloudAccount
from app.schemas.billing import (
    AwsBillingRequest,
    BillingBreakdownItem,
    BillingBreakdownResponse,
    BillingDataStatus,
    BillingGranularity,
    BillingGroupBy,
    BillingMetric,
    BillingSeriesGroup,
    BillingSeriesPoint,
    BillingSummaryResponse,
    BillingSummaryTotal,
    BillingTimeSeriesResponse,
)
from app.services.aws_auth import assume_account_session
from app.services.aws_cost_explorer import (
    AWS_METRICS,
    AwsBillingUpstreamError,
    AwsCostExplorerClient,
    build_cost_and_usage_query,
)

logger = logging.getLogger(__name__)

# Version the cache identity so hot processes never reuse rows normalized under an
# older billing contract after a deploy. The cache remains local/in-memory.
_BILLING_CACHE_SCHEMA_VERSION = 2


class BillingServiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True)
class _AccountContext:
    deepops_account_id: int
    aws_account_id: str
    display_name: str
    is_management_account: bool
    configuration: AwsAccount

    @property
    def billing_scope(self) -> str:
        # There is no payer/member relationship persisted today. Each configured
        # role is therefore an independent billing scope for this first version.
        return f"aws-account:{self.aws_account_id}"


@dataclass(frozen=True)
class _BillingRow:
    start_date: date
    end_date: date
    key: str | None
    amount: Decimal
    currency: str
    estimated: bool
    deepops_account_id: int
    aws_account_id: str
    display_name: str


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    rows: tuple[_BillingRow, ...]


class BillingQueryCache:
    def __init__(self) -> None:
        self._items: dict[tuple[Any, ...], _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple[Any, ...]) -> tuple[_BillingRow, ...] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._items.pop(key, None)
                return None
            return entry.rows

    def set(self, key: tuple[Any, ...], rows: tuple[_BillingRow, ...], ttl_seconds: int) -> None:
        with self._lock:
            self._items[key] = _CacheEntry(time.monotonic() + ttl_seconds, rows)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


billing_query_cache = BillingQueryCache()


def _parse_cost(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise BillingServiceError(
            "UPSTREAM_DATA_INVALID",
            "O AWS Cost Explorer retornou um valor monetário inválido.",
        ) from exc


def _status_from_estimation_flags(flags: Iterable[bool]) -> BillingDataStatus:
    """Classify GetCostAndUsage values without deriving forecast from dates."""

    values = frozenset(flags)
    if values == frozenset({True}):
        return BillingDataStatus.ESTIMATED
    if True in values and False in values:
        return BillingDataStatus.PARTIALLY_ESTIMATED
    return BillingDataStatus.ACTUAL


def _bucket_state_counts(rows: Iterable[_BillingRow]) -> tuple[int, int, int]:
    by_bucket: dict[tuple[date, date], set[bool]] = {}
    for row in rows:
        by_bucket.setdefault((row.start_date, row.end_date), set()).add(row.estimated)
    estimated = sum(True in flags for flags in by_bucket.values())
    partial = sum(flags == {False, True} for flags in by_bucket.values())
    return len(by_bucket), estimated, partial


def _normalize_pages(
    pages: tuple[dict[str, Any], ...],
    *,
    metric: BillingMetric,
    group_by: BillingGroupBy,
    account: _AccountContext,
) -> tuple[_BillingRow, ...]:
    metric_name = AWS_METRICS[metric]
    rows: list[_BillingRow] = []
    for page in pages:
        for bucket in page.get("ResultsByTime", []):
            period = bucket.get("TimePeriod") or {}
            try:
                bucket_start = date.fromisoformat(str(period["Start"]))
                bucket_end = date.fromisoformat(str(period["End"]))
            except (KeyError, ValueError) as exc:
                raise BillingServiceError(
                    "UPSTREAM_DATA_INVALID",
                    "O AWS Cost Explorer retornou um período inválido.",
                ) from exc
            # Preserve the authoritative AWS flag at the temporal bucket granularity.
            estimated = bool(bucket.get("Estimated", False))

            if group_by == BillingGroupBy.NONE:
                metric_value = (bucket.get("Total") or {}).get(metric_name)
                if not metric_value:
                    continue
                currency = str(metric_value.get("Unit") or "").strip()
                if not currency:
                    raise BillingServiceError(
                        "UPSTREAM_DATA_INVALID",
                        "O AWS Cost Explorer retornou custo sem unidade/moeda.",
                    )
                rows.append(
                    _BillingRow(
                        start_date=bucket_start,
                        end_date=bucket_end,
                        key=None,
                        amount=_parse_cost(metric_value.get("Amount")),
                        currency=currency,
                        estimated=estimated,
                        deepops_account_id=account.deepops_account_id,
                        aws_account_id=account.aws_account_id,
                        display_name=account.display_name,
                    )
                )
                continue

            for group in bucket.get("Groups", []):
                metric_value = (group.get("Metrics") or {}).get(metric_name)
                keys = group.get("Keys") or []
                if not metric_value or not keys:
                    continue
                currency = str(metric_value.get("Unit") or "").strip()
                if not currency:
                    raise BillingServiceError(
                        "UPSTREAM_DATA_INVALID",
                        "O AWS Cost Explorer retornou custo sem unidade/moeda.",
                    )
                rows.append(
                    _BillingRow(
                        start_date=bucket_start,
                        end_date=bucket_end,
                        key=str(keys[0]),
                        amount=_parse_cost(metric_value.get("Amount")),
                        currency=currency,
                        estimated=estimated,
                        deepops_account_id=account.deepops_account_id,
                        aws_account_id=account.aws_account_id,
                        display_name=account.display_name,
                    )
                )
    return tuple(rows)


def _next_bucket_start(value: date, granularity: BillingGranularity) -> date:
    if granularity == BillingGranularity.DAILY:
        return value + timedelta(days=1)
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


class AwsBillingService:
    def __init__(
        self,
        db: Session,
        *,
        cache: BillingQueryCache = billing_query_cache,
        session_factory: Callable[[AwsAccount], Any] = assume_account_session,
        client_factory: Callable[[Any], AwsCostExplorerClient] = AwsCostExplorerClient,
        today_factory: Callable[[], date] | None = None,
    ) -> None:
        self._db = db
        self._cache = cache
        self._session_factory = session_factory
        self._client_factory = client_factory
        self._today_factory = today_factory or (lambda: datetime.now(UTC).date())

    def _validate_period(self, request: AwsBillingRequest) -> date:
        today = self._today_factory()
        if request.start_date > today:
            raise BillingServiceError(
                "INVALID_PERIOD",
                "Billing histórico não permite um período inteiramente futuro.",
            )
        if request.end_date > today + timedelta(days=1):
            raise BillingServiceError(
                "INVALID_PERIOD",
                "end_date pode avançar no máximo até amanhã para incluir o bucket de hoje.",
            )
        return today

    def _resolve_accounts(self, account_ids: list[int]) -> list[_AccountContext]:
        accounts = list(
            self._db.scalars(
                select(CloudAccount)
                .options(selectinload(CloudAccount.aws_configuration))
                .where(CloudAccount.id.in_(account_ids))
            )
        )
        by_id = {account.id: account for account in accounts}
        contexts: list[_AccountContext] = []
        for account_id in account_ids:
            account = by_id.get(account_id)
            if account is None:
                raise BillingServiceError(
                    "ACCOUNT_NOT_FOUND",
                    f"Conta Aven {account_id} não foi encontrada ou não está autorizada.",
                )
            if account.provider != CloudProvider.AWS.value or account.aws_configuration is None:
                raise BillingServiceError(
                    "ACCOUNT_NOT_AWS",
                    f"Conta Aven {account_id} não possui configuração AWS.",
                )
            contexts.append(
                _AccountContext(
                    deepops_account_id=account.id,
                    aws_account_id=account.native_account_id,
                    display_name=account.name,
                    is_management_account=bool(account.aws_configuration.is_management_account),
                    configuration=account.aws_configuration,
                )
            )
        return contexts

    def _cache_ttl(self, request: AwsBillingRequest, today: date) -> int:
        current_month = date(today.year, today.month, 1)
        if request.end_date <= current_month:
            return settings.aws_billing_cache_ttl_historical_seconds
        return settings.aws_billing_cache_ttl_current_seconds

    @staticmethod
    def _cache_key(
        account: _AccountContext,
        request: AwsBillingRequest,
        group_by: BillingGroupBy,
    ) -> tuple[Any, ...]:
        return (
            _BILLING_CACHE_SCHEMA_VERSION,
            account.billing_scope,
            account.deepops_account_id,
            request.start_date.isoformat(),
            request.end_date.isoformat(),
            request.granularity.value,
            request.metric.value,
            group_by.value,
            tuple(sorted(request.exclude_record_types)),
        )

    def _fetch_account_rows(
        self,
        account: _AccountContext,
        request: AwsBillingRequest,
        *,
        group_by: BillingGroupBy,
        ttl_seconds: int,
        account_count: int,
    ) -> tuple[_BillingRow, ...]:
        cache_key = self._cache_key(account, request, group_by)
        started = time.perf_counter()
        cached = self._cache.get(cache_key)
        if cached is not None:
            bucket_count, estimated_bucket_count, partial_bucket_count = _bucket_state_counts(
                cached
            )
            logger.info(
                "aws_billing_query provider=aws billing_scope=%s account_count=%d "
                "start_date=%s end_date=%s granularity=%s metric=%s group_by=%s "
                "bucket_count=%d estimated_bucket_count=%d partial_bucket_count=%d "
                "forecast_bucket_count=0 cache_hit=true aws_request_count=0 duration_ms=%.2f",
                account.billing_scope,
                account_count,
                request.start_date,
                request.end_date,
                request.granularity.value,
                request.metric.value,
                group_by.value,
                bucket_count,
                estimated_bucket_count,
                partial_bucket_count,
                (time.perf_counter() - started) * 1000,
            )
            return cached

        # A management/payer role can see the whole organization. Restrict it to the
        # registered Aven account so an arbitrary linked account can never leak in.
        linked_account_id = account.aws_account_id if account.is_management_account else None
        query = build_cost_and_usage_query(
            start_date=request.start_date.isoformat(),
            end_date=request.end_date.isoformat(),
            granularity=request.granularity,
            metric=request.metric,
            group_by=group_by,
            exclude_record_types=tuple(sorted(request.exclude_record_types)),
            linked_account_id=linked_account_id,
        )
        try:
            session = self._session_factory(account.configuration)
            result = self._client_factory(session).get_cost_and_usage(query)
        except AwsBillingUpstreamError:
            raise
        except Exception as exc:
            raise BillingServiceError(
                "UPSTREAM_ERROR",
                "Não foi possível inicializar a consulta ao AWS Cost Explorer.",
            ) from exc

        rows = _normalize_pages(
            result.pages,
            metric=request.metric,
            group_by=group_by,
            account=account,
        )
        self._cache.set(cache_key, rows, ttl_seconds)
        bucket_count, estimated_bucket_count, partial_bucket_count = _bucket_state_counts(rows)
        logger.info(
            "aws_billing_query provider=aws billing_scope=%s account_count=%d start_date=%s "
            "end_date=%s granularity=%s metric=%s group_by=%s bucket_count=%d "
            "estimated_bucket_count=%d partial_bucket_count=%d forecast_bucket_count=0 "
            "cache_hit=false aws_request_count=%d duration_ms=%.2f",
            account.billing_scope,
            account_count,
            request.start_date,
            request.end_date,
            request.granularity.value,
            request.metric.value,
            group_by.value,
            bucket_count,
            estimated_bucket_count,
            partial_bucket_count,
            result.aws_request_count,
            (time.perf_counter() - started) * 1000,
        )
        return rows

    def _rows(
        self,
        request: AwsBillingRequest,
        *,
        group_by: BillingGroupBy,
    ) -> tuple[_BillingRow, ...]:
        today = self._validate_period(request)
        accounts = self._resolve_accounts(request.account_ids)
        ttl_seconds = self._cache_ttl(request, today)
        rows: list[_BillingRow] = []
        for account in accounts:
            # Partial multi-account results are deliberately not returned: any failure
            # aborts the operation before an aggregate response is built.
            rows.extend(
                self._fetch_account_rows(
                    account,
                    request,
                    group_by=group_by,
                    ttl_seconds=ttl_seconds,
                    account_count=len(accounts),
                )
            )
        return tuple(rows)

    def summary(self, request: AwsBillingRequest) -> BillingSummaryResponse:
        rows = self._rows(request, group_by=BillingGroupBy.NONE)
        totals: dict[str, tuple[Decimal, frozenset[bool]]] = {}
        for row in rows:
            amount, flags = totals.get(row.currency, (Decimal("0"), frozenset()))
            totals[row.currency] = (amount + row.amount, flags | {row.estimated})
        return BillingSummaryResponse(
            metric=request.metric,
            start_date=request.start_date,
            end_date=request.end_date,
            totals=[
                BillingSummaryTotal(
                    amount=amount,
                    currency=currency,
                    status=_status_from_estimation_flags(flags),
                )
                for currency, (amount, flags) in sorted(totals.items())
            ],
        )

    def timeseries(self, request: AwsBillingRequest) -> BillingTimeSeriesResponse:
        rows = self._rows(request, group_by=request.group_by)
        values: dict[tuple[date, date, str], tuple[Decimal, frozenset[bool]]] = {}
        grouped_values: dict[
            tuple[date, date, str, str], tuple[Decimal, frozenset[bool], _BillingRow]
        ] = {}
        currencies: set[str] = set()
        for row in rows:
            currencies.add(row.currency)
            bucket_key = (row.start_date, row.end_date, row.currency)
            amount, flags = values.get(bucket_key, (Decimal("0"), frozenset()))
            values[bucket_key] = (amount + row.amount, flags | {row.estimated})

            if request.group_by != BillingGroupBy.NONE:
                series_key = row.key or ""
                aggregate_key = (*bucket_key, series_key)
                grouped_amount, grouped_flags, sample = grouped_values.get(
                    aggregate_key,
                    (Decimal("0"), frozenset(), row),
                )
                grouped_values[aggregate_key] = (
                    grouped_amount + row.amount,
                    grouped_flags | {row.estimated},
                    sample,
                )

        # Fill deterministic zero buckets only for units observed elsewhere in the
        # same response. With no AWS data there is no currency to infer safely.
        bucket_start = request.start_date
        while bucket_start < request.end_date:
            natural_end = _next_bucket_start(bucket_start, request.granularity)
            bucket_end = min(natural_end, request.end_date)
            for currency in currencies:
                values.setdefault(
                    (bucket_start, bucket_end, currency),
                    (Decimal("0"), frozenset({False})),
                )
            bucket_start = bucket_end

        points: list[BillingSeriesPoint] = []
        for (start, end, currency), (amount, flags) in sorted(values.items()):
            groups: list[BillingSeriesGroup] = []
            if request.group_by != BillingGroupBy.NONE:
                for (
                    group_start,
                    group_end,
                    group_currency,
                    group_key,
                ), (
                    group_amount,
                    group_flags,
                    sample,
                ) in sorted(grouped_values.items()):
                    if group_start != start or group_end != end or group_currency != currency:
                        continue
                    group_status = _status_from_estimation_flags(group_flags)
                    if request.group_by == BillingGroupBy.ACCOUNT:
                        known = group_key == sample.aws_account_id
                        groups.append(
                            BillingSeriesGroup(
                                key=group_key,
                                label=sample.display_name if known else group_key,
                                amount=group_amount,
                                currency=currency,
                                status=group_status,
                                deepops_account_id=(sample.deepops_account_id if known else None),
                                aws_account_id=group_key,
                                display_name=sample.display_name if known else None,
                            )
                        )
                    else:
                        groups.append(
                            BillingSeriesGroup(
                                key=group_key,
                                label=group_key,
                                amount=group_amount,
                                currency=currency,
                                status=group_status,
                            )
                        )

            points.append(
                BillingSeriesPoint(
                    start_date=start,
                    end_date=end,
                    amount=amount,
                    currency=currency,
                    status=_status_from_estimation_flags(flags),
                    groups=groups,
                )
            )

        return BillingTimeSeriesResponse(
            metric=request.metric,
            granularity=request.granularity,
            group_by=request.group_by,
            start_date=request.start_date,
            end_date=request.end_date,
            points=points,
        )

    def breakdown(self, request: AwsBillingRequest) -> BillingBreakdownResponse:
        if request.group_by == BillingGroupBy.NONE:
            raise BillingServiceError(
                "INVALID_GROUPING",
                "breakdown requer group_by SERVICE ou ACCOUNT.",
            )
        rows = self._rows(request, group_by=request.group_by)
        values: dict[tuple[str, str], tuple[Decimal, frozenset[bool], _BillingRow]] = {}
        for row in rows:
            key = row.key or ""
            aggregate_key = (key, row.currency)
            amount, flags, sample = values.get(
                aggregate_key,
                (Decimal("0"), frozenset(), row),
            )
            values[aggregate_key] = (amount + row.amount, flags | {row.estimated}, sample)

        items: list[BillingBreakdownItem] = []
        for (key, currency), (amount, flags, sample) in sorted(values.items()):
            status = _status_from_estimation_flags(flags)
            if request.group_by == BillingGroupBy.ACCOUNT:
                known = key == sample.aws_account_id
                items.append(
                    BillingBreakdownItem(
                        key=key,
                        label=sample.display_name if known else key,
                        amount=amount,
                        currency=currency,
                        status=status,
                        deepops_account_id=sample.deepops_account_id if known else None,
                        aws_account_id=key,
                        display_name=sample.display_name if known else None,
                    )
                )
            else:
                items.append(
                    BillingBreakdownItem(
                        key=key,
                        label=key,
                        amount=amount,
                        currency=currency,
                        status=status,
                    )
                )
        return BillingBreakdownResponse(
            metric=request.metric,
            group_by=request.group_by,
            start_date=request.start_date,
            end_date=request.end_date,
            items=items,
        )
