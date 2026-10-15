import logging
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models.cloudwatch_usage import CloudWatchUsageEvent

logger = logging.getLogger("deepops.cloudwatch_usage")


@dataclass(frozen=True)
class CloudWatchUsageContext:
    cloud_account_id: int | None
    aws_account_id: str
    collection_run_id: str | None = None
    region: str | None = None
    collector: str | None = None
    analyzer: str | None = None


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
    response = getattr(error, "response", None)
    return _response_metadata(response)


def _error_type(error: Exception) -> str:
    if isinstance(error, ClientError):
        detail = error.response.get("Error", {})
        if isinstance(detail, dict) and detail.get("Code"):
            return str(detail["Code"])[:80]
    return type(error).__name__[:80]


def _retry_observation(metadata: dict[str, Any], *, success: bool) -> tuple[int, int | None, bool]:
    raw = metadata.get("RetryAttempts")
    if isinstance(raw, int) and raw >= 0:
        return raw + 1, raw, True
    # A successful SDK response necessarily represents at least one service request.
    if success:
        return 1, 0, True
    # Some transport failures do not expose botocore retry metadata. Keep a factual
    # lower bound instead of inventing a precise physical-attempt count.
    return 1, None, False


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
        metric_stats = sum(1 for query in queries if isinstance(query, dict) and query.get("MetricStat"))
        expressions = [
            str(query.get("Expression", ""))
            for query in queries
            if isinstance(query, dict) and query.get("Expression")
        ]
        insights = sum(
            1 for expression in expressions if expression.lstrip().upper().startswith("SELECT ")
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


class CloudWatchUsageTelemetryService:
    """Buffers factual CloudWatch API usage and persists it in one batch per AWS run."""

    def __init__(self, context: CloudWatchUsageContext):
        self.context = context
        self._events: list[dict[str, Any]] = []

    def instrument_session(self, session: Any) -> "InstrumentedAwsSession":
        return InstrumentedAwsSession(session, self, self.context)

    def record(
        self,
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
        request_count, retry_count, exact = _retry_observation(
            response_metadata, success=success
        )
        metadata = {
            key: value
            for key, value in metric["metadata"].items()
            if value is not None
        }
        if not exact:
            metadata["request_count_basis"] = "logical_minimum"
        self._events.append(
            {
                "occurred_at": datetime.now(UTC),
                "provider": "aws",
                "aws_service": "cloudwatch",
                "cloud_account_id": context.cloud_account_id,
                "aws_account_id": context.aws_account_id,
                "region": context.region or "unknown",
                "operation": _operation_name(method_name),
                "collector": context.collector,
                "analyzer": context.analyzer,
                "collection_run_id": context.collection_run_id,
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

    def summary(self) -> dict[str, int]:
        return {
            "events": len(self._events),
            "requests": sum(int(event["request_count"]) for event in self._events),
            "metric_queries": sum(int(event.get("metric_query_count") or 0) for event in self._events),
            "failures": sum(1 for event in self._events if not event["success"]),
        }

    def flush(self, db: Session) -> dict[str, int]:
        summary = self.summary()
        if not self._events:
            return summary
        rows = self._events
        self._events = []
        try:
            db.execute(insert(CloudWatchUsageEvent), rows)
            db.commit()
        except Exception:
            db.rollback()
            raise
        return summary


class InstrumentedCloudWatchClient:
    def __init__(
        self,
        client: Any,
        telemetry: CloudWatchUsageTelemetryService,
        context: CloudWatchUsageContext,
    ):
        self._client = client
        self._telemetry = telemetry
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
                self._telemetry.record(
                    context=self._context,
                    method_name=name,
                    request=kwargs,
                    success=False,
                    duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                    response_metadata=_error_metadata(error),
                    error=error,
                )
                raise
            self._telemetry.record(
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
    """Session proxy that only changes CloudWatch clients; all other AWS clients pass through."""

    def __init__(
        self,
        session: Any,
        telemetry: CloudWatchUsageTelemetryService,
        context: CloudWatchUsageContext,
    ):
        self._session = session
        self._telemetry = telemetry
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
            self._telemetry,
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
            self._telemetry,
            replace(self._context, region=region or "unknown"),
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)


def scope_cloudwatch_usage(
    session: Any,
    *,
    region: str,
    collector: str | None,
    analyzer: str | None,
) -> Any:
    if isinstance(session, InstrumentedAwsSession):
        return session.scoped(region=region, collector=collector, analyzer=analyzer)
    return session
