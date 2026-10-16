from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.cloudwatch_usage import CloudWatchUsageEvent
from app.services.cloudwatch_usage_query import (
    SHARED_ANALYZER_FILTER,
    CloudWatchUsageFilters,
    usage_summary,
)


def _event(
    *,
    run_id: str | None,
    requests: int,
    failed: bool = False,
    analyzer: str | None = "rds_nonprod_idle",
) -> CloudWatchUsageEvent:
    return CloudWatchUsageEvent(
        occurred_at=datetime.now(UTC),
        provider="aws",
        aws_service="cloudwatch",
        aws_account_id="123456789012",
        region="sa-east-1",
        operation="GetMetricStatistics",
        collector="rds_nonprod_idle",
        analyzer=analyzer,
        collection_run_id=run_id,
        request_count=requests,
        retry_count=0,
        request_count_is_exact=True,
        metrics_requested=1,
        success=not failed,
        error_type="Throttling" if failed else None,
        event_metadata={},
    )


def test_usage_summary_groups_collection_runs_without_dropping_unattributed_usage():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    with Session(engine) as db:
        db.add_all(
            [
                _event(run_id="run-success", requests=2),
                _event(run_id="run-success", requests=1),
                _event(run_id="run-failed", requests=3, failed=True),
                _event(run_id=None, requests=4),
            ]
        )
        db.commit()

        summary = usage_summary(
            db,
            CloudWatchUsageFilters(
                date_from=now - timedelta(minutes=5),
                date_to=now + timedelta(minutes=5),
            ),
            group_by="collection_run",
        )

    by_run = {item["group"]: item for item in summary["items"]}
    assert by_run["run-success"]["requests"] == 3
    assert by_run["run-success"]["failed_events"] == 0
    assert by_run["run-failed"]["requests"] == 3
    assert by_run["run-failed"]["failed_events"] == 1
    assert by_run[None]["requests"] == 4
    engine.dispose()


def test_usage_summary_can_filter_shared_analyzer_without_inventing_an_identifier():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add_all(
            [
                _event(run_id="run-shared", requests=2, analyzer=None),
                _event(run_id="run-assigned", requests=5, analyzer="rds_nonprod_idle"),
            ]
        )
        db.commit()

        summary = usage_summary(
            db,
            CloudWatchUsageFilters(analyzer=SHARED_ANALYZER_FILTER),
            group_by="analyzer",
        )

    assert summary["items"] == [
        {
            "group": None,
            "events": 1,
            "requests": 2,
            "metric_queries": 0,
            "metrics_requested": 1,
            "failed_events": 0,
        }
    ]
    engine.dispose()
