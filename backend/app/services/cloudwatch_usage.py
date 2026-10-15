import logging
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import event, insert, or_, select
from sqlalchemy.orm import Session

from app.models.cloudwatch_usage import CloudWatchUsageEvent
from app.models.collection_run import CollectionRun
from app.models.scan import Scan

logger = logging.getLogger("deepops.cloudwatch_usage")
_buffer = threading.local()


@dataclass(frozen=True)
class CloudWatchUsageContext:
    cloud_account_id: int | None
    aws_account_id: str
    region: str | None = None
    collector: str | None = None
    analyzer: str | None = None


def _buffered_events() -> list[dict[str, Any]]:
    events = getattr(_buffer, "events", None)
    if events is None:
        events = []
        _buffer.events = events
    return events


def _operation_name(method_name: str) -> str:
    return "".join(part.capitalize() for part in method_name.split("_"))


def _response_metadata(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    metadata = value.get("ResponseMetadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _error_metadata(error: Exception) -> dict[str, Any]:
    if isinstance(error, ClientError):
        return _response_metadata(error.response)
    return _response_metadata(getattr(error, "response", None))


def _error_type(error: Exception) -> str:
    if isinstance(error, ClientError):
        detail = error.response.get("Error", {})
        if isinstance(detail, dict) and detail.get("Code"):
            return str(detail["Code"])[:80]
    return type(error).__name__[:80]


def _retry_observation(
    metadata: dict[str, Any], *, success: bool
) -> tuple[int, int | None, bool]:
    raw = metadata.get("RetryAttempts")
    if isinstance(raw, int) and raw >= 0:
        return raw + 1, raw, True
    if success:
        return 1, 0, True
    # Transport failures can lack botocore retry metadata. Preserve only the factual
    # minimum instead of claiming a physical attempt count that the SDK did not expose.
    return 1, None, False


def _current_attribution(
    method_name: str, request: dict[str, Any]
) -> tuple[str | None, str | None]:
    if method_name != "get_metric_statistics":
        return None, None
    namespace = request.get("Namespace")
    if namespace == "AWS/RDS":
        return "rds_nonprod_idle", "rds_nonprod_idle"
    if namespace in {"AWS/ApplicationELB", "AWS/NetworkELB", "AWS/ELB"}:
        return "load_balancer_no_traffic", "load_balancer_no_traffic"
    return None, None


def _metric_dimensions(method_name: str, request: dict[str, Any]) -> dict[str, Any]:
    if method_name == "get_metric_statistics":
        statistics = request.get("Statistics") or request.get("ExtendedStatistics") or []
        return {
            "metrics_requested": 1,
            "metric_query_count": None,
            "metric_stat_query_count": None,
            "expression_query_count": None,
            "metrics_insights_query_count": None,
            "metadata": {
                "statistics_requested": len(statistics),
                "period_seconds": request.get("Period"),
            },
        }
    if method_name == "get_metric_data":
        queries = request.get("MetricDataQueries") or []
        metric_stats = sum(
            1
            for query in queries
            if isinstance(query, dict) and query.get("MetricStat")
        )
        expressions = [
            str(query.get("Expression", ""))
            for query in queries
            if isinstance(query, dict) and query.get("Expression")
        ]
        insights = sum(
            1
            for expression in expressions
            if expression.lstrip().upper().startswith("SELECT ")
        )
        return {
            "metrics_requested": metric_stats,
            "metric_query_count": len(queries),
            "metric_stat_query_count": metric_stats,
            "expression_query_count": len(expressions),
            "metrics_insights_query_count": insights,
            "metadata": {
                "max_datapoints": request.get("MaxDatapoints"),
                "paginated_request": bool(request.get("NextToken")),
                "scan_by": request.get("ScanBy"),
            },
        }
    if method_name == "list_metrics":
        return {
            "metrics_requested": None,
            "metric_query_count": None,
            "metric_stat_query_count": None,
            "expression_query_count": None,
            "metrics_insights_query_count": None,
            "metadata": {"paginated_request": bool(request.get("NextToken"))},
        }
    return {
        "metrics_requested": None,
        "metric_query_count": None,
        "metric_stat_query_count": None,
        "expression_query_count": None,
        "metrics_insights_query_count": None,
        "metadata": {},
    }


def _record_event(
    *,
    context: CloudWatchUsageContext,
    method_name: str,
    request: dict[str, Any],
    success: bool,
    duration_ms: int,
    response_metadata: dict[str, Any],
    error: Exception | None = None,
) -> None:
    metric = _metric_dimensions(method_name, request)
    request_count, retry_count, exact = _retry_observation(response_metadata, success=success)
    inferred_collector, inferred_analyzer = _current_attribution(method_name, request)
    metadata = {
        key: value for key, value in metric["metadata"].items() if value is not None
    }
    if not exact:
        metadata["request_count_basis"] = "logical_minimum"
    _buffered_events().append(
        {
            "occurred_at": datetime.now(UTC),
            "provider": "aws",
            "aws_service": "cloudwatch",
            "cloud_account_id": context.cloud_account_id,
            "aws_account_id": context.aws_account_id,
            "region": context.region or "unknown",
            "operation": _operation_name(method_name),
            "collector": context.collector or inferred_collector,
            "analyzer": context.analyzer or inferred_analyzer,
            "collection_run_id": None,
            "request_count": request_count,
            "retry_count": retry_count,
            "request_count_is_exact": exact,
            "metrics_requested": metric["metrics_requested"],
            "metric_query_count": metric["metric_query_count"],
            "metric_stat_query_count": metric["metric_stat_query_count"],
            "expression_query_count": metric["expression_query_count"],
            "metrics_insights_query_count": metric["metrics_insights_query_count"],
            "success": success,
            "error_type": _error_type(error) if error is not None else None,
            "request_duration_ms": duration_ms,
            "aws_request_id": (
                str(response_metadata.get("RequestId"))[:128]
                if response_metadata.get("RequestId")
                else None
            ),
            "metadata": metadata,
        }
    )


class InstrumentedCloudWatchClient:
    def __init__(self, client: Any, context: CloudWatchUsageContext):
        self._client = client
        self._context = context

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._client, name)
        if not callable(target) or name.startswith("_"):
            return target

        def instrumented(*args: Any, **kwargs: Any) -> Any:
            started = time.monotonic()
            try:
                response = target(*args, **kwargs)
            except Exception as error:
                _record_event(
                    context=self._context,
                    method_name=name,
                    request=kwargs,
                    success=False,
                    duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                    response_metadata=_error_metadata(error),
                    error=error,
                )
                raise
            _record_event(
                context=self._context,
                method_name=name,
                request=kwargs,
                success=True,
                duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                response_metadata=_response_metadata(response),
            )
            return response

        return instrumented


class InstrumentedAwsSession:
    """Proxy that instruments only CloudWatch while preserving boto3 session semantics."""

    def __init__(self, session: Any, context: CloudWatchUsageContext):
        self._session = session
        self._context = context

    def scoped(
        self,
        *,
        region: str,
        collector: str | None,
        analyzer: str | None,
    ) -> "InstrumentedAwsSession":
        return InstrumentedAwsSession(
            self._session,
            replace(
                self._context,
                region=region,
                collector=collector,
                analyzer=analyzer,
            ),
        )

    def client(self, service_name: str, *args: Any, **kwargs: Any) -> Any:
        client = self._session.client(service_name, *args, **kwargs)
        if service_name != "cloudwatch":
            return client
        region = kwargs.get("region_name") or self._context.region
        if not region:
            region = getattr(getattr(client, "meta", None), "region_name", None)
        return InstrumentedCloudWatchClient(
            client,
            replace(self._context, region=region or "unknown"),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


def instrument_aws_session(
    session: Any,
    *,
    cloud_account_id: int | None,
    aws_account_id: str,
) -> InstrumentedAwsSession:
    return InstrumentedAwsSession(
        session,
        CloudWatchUsageContext(
            cloud_account_id=cloud_account_id,
            aws_account_id=aws_account_id,
        ),
    )


def _resolve_collection_run_id(
    db: Session,
    *,
    cloud_account_id: int | None,
    first_event_at: datetime,
    last_event_at: datetime,
) -> str | None:
    if cloud_account_id is None:
        return None
    statement = (
        select(CollectionRun.id)
        .join(Scan, CollectionRun.scan_id == Scan.id)
        .where(
            Scan.cloud_account_id == cloud_account_id,
            CollectionRun.provider == "aws",
            CollectionRun.started_at <= first_event_at,
            or_(
                CollectionRun.finished_at.is_(None),
                CollectionRun.finished_at >= last_event_at,
            ),
        )
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
    )
    with db.no_autoflush:
        return db.scalar(statement)


def _flush_buffered_usage(db: Session) -> None:
    events = list(_buffered_events())
    if not events:
        return
    _buffer.events = []

    grouped: dict[tuple[int | None, str], list[dict[str, Any]]] = {}
    for row in events:
        key = (row["cloud_account_id"], row["aws_account_id"])
        grouped.setdefault(key, []).append(row)

    for (cloud_account_id, _aws_account_id), rows in grouped.items():
        timestamps = [row["occurred_at"] for row in rows]
        run_id = _resolve_collection_run_id(
            db,
            cloud_account_id=cloud_account_id,
            first_event_at=min(timestamps),
            last_event_at=max(timestamps),
        )
        for row in rows:
            row["collection_run_id"] = run_id

    connection = db.connection()
    savepoint = connection.begin_nested()
    try:
        connection.execute(insert(CloudWatchUsageEvent.__table__), events)
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.warning(
            "event=cloudwatch_usage_persist_failed events=%s",
            len(events),
        )
        return

    run_ids = {row["collection_run_id"] for row in events if row["collection_run_id"]}
    logger.info(
        "event=cloudwatch_usage_summary collection_run_id=%s events=%s requests=%s "
        "metric_queries=%s failed_requests=%s",
        next(iter(run_ids)) if len(run_ids) == 1 else "mixed_or_missing",
        len(events),
        sum(int(row["request_count"]) for row in events),
        sum(int(row.get("metric_query_count") or 0) for row in events),
        sum(int(row["request_count"]) for row in events if not row["success"]),
    )


@event.listens_for(Session, "before_commit")
def _persist_cloudwatch_usage_before_commit(session: Session) -> None:
    _flush_buffered_usage(session)


def clear_cloudwatch_usage_buffer() -> None:
    """Test/error-boundary helper to prevent stale process-local telemetry reuse."""

    _buffer.events = []
