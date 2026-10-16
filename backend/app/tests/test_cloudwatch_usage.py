from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db.base import Base
from app.models.account import CloudAccount
from app.models.cloudwatch_usage import CloudWatchUsageEvent
from app.models.collection_run import CollectionRun
from app.models.scan import Scan
from app.services.cloudwatch_usage import (
    _buffered_events,
    clear_cloudwatch_usage_buffer,
    instrument_aws_session,
)
from app.services.cloudwatch_usage_query import (
    CloudWatchUsageFilters,
    list_usage_events,
    usage_summary,
)


@pytest.fixture(autouse=True)
def isolated_usage_buffer():
    clear_cloudwatch_usage_buffer()
    yield
    clear_cloudwatch_usage_buffer()


class FakeCloudWatch:
    def __init__(self):
        self.meta = SimpleNamespace(region_name="sa-east-1")
        self.response = {
            "Datapoints": [{"Average": 7.5}],
            "ResponseMetadata": {"RequestId": "request-1", "RetryAttempts": 2},
        }

    def get_metric_statistics(self, **_request):
        return self.response

    def get_metric_data(self, **_request):
        return {
            "MetricDataResults": [],
            "ResponseMetadata": {"RequestId": "gmd-1", "RetryAttempts": 0},
        }

    def list_metrics(self, **_request):
        return {
            "Metrics": [],
            "ResponseMetadata": {"RequestId": "list-1", "RetryAttempts": 0},
        }

    def fail(self, **_request):
        raise ClientError(
            {
                "Error": {"Code": "Throttling", "Message": "safe test detail"},
                "ResponseMetadata": {"RequestId": "failed-1", "RetryAttempts": 1},
            },
            "GetMetricStatistics",
        )


class FakeSession:
    def __init__(self):
        self.cloudwatch = FakeCloudWatch()
        self.other_client = object()

    def client(self, service_name, *_args, **_kwargs):
        if service_name == "cloudwatch":
            return self.cloudwatch
        return self.other_client


def wrapped_session(*, cloud_account_id=7, aws_account_id="123456789012"):
    source = FakeSession()
    return (
        source,
        instrument_aws_session(
            source,
            cloud_account_id=cloud_account_id,
            aws_account_id=aws_account_id,
        ),
    )


def test_get_metric_statistics_records_factual_usage_and_preserves_response():
    source, session = wrapped_session()
    response = session.client("cloudwatch", region_name="sa-east-1").get_metric_statistics(
        Namespace="AWS/RDS",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "DBInstanceIdentifier", "Value": "must-not-be-persisted"}],
        StartTime=datetime.now(UTC) - timedelta(days=7),
        EndTime=datetime.now(UTC),
        Period=86400,
        Statistics=["Average"],
    )

    assert response is source.cloudwatch.response
    [event] = _buffered_events()
    assert event["operation"] == "GetMetricStatistics"
    assert event["request_count"] == 3
    assert event["retry_count"] == 2
    assert event["request_count_is_exact"] is True
    assert event["metrics_requested"] == 1
    assert event["collector"] == "rds_nonprod_idle"
    assert event["analyzer"] == "rds_nonprod_idle"
    assert event["region"] == "sa-east-1"
    assert event["aws_request_id"] == "request-1"
    assert "must-not-be-persisted" not in repr(event)


def test_load_balancer_namespace_is_attributed_once():
    _, session = wrapped_session()
    client = session.client("cloudwatch", region_name="us-east-1")
    client.get_metric_statistics(
        Namespace="AWS/ApplicationELB",
        MetricName="RequestCount",
        StartTime=datetime.now(UTC) - timedelta(days=1),
        EndTime=datetime.now(UTC),
        Period=86400,
        Statistics=["Sum"],
    )

    assert len(_buffered_events()) == 1
    event = _buffered_events()[0]
    assert event["collector"] == "load_balancer_no_traffic"
    assert event["analyzer"] == "load_balancer_no_traffic"


def test_client_error_is_recorded_and_reraised_with_retry_observation():
    _, session = wrapped_session()
    client = session.client("cloudwatch", region_name="sa-east-1")

    with pytest.raises(ClientError):
        client.fail(Namespace="AWS/RDS")

    [event] = _buffered_events()
    assert event["success"] is False
    assert event["error_type"] == "Throttling"
    assert event["request_count"] == 2
    assert event["retry_count"] == 1
    assert event["aws_request_id"] == "failed-1"


def test_get_metric_data_classifies_queries_and_each_page_is_a_separate_event():
    _, session = wrapped_session()
    client = session.client("cloudwatch", region_name="sa-east-1")
    queries = [
        {"Id": "m1", "MetricStat": {"Metric": {"Namespace": "AWS/EC2"}}},
        {"Id": "e1", "Expression": "m1 * 2"},
        {"Id": "q1", "Expression": 'SELECT AVG(CPUUtilization) FROM SCHEMA("AWS/EC2")'},
    ]
    client.get_metric_data(MetricDataQueries=queries)
    client.get_metric_data(MetricDataQueries=queries, NextToken="page-2")

    assert len(_buffered_events()) == 2
    first, second = _buffered_events()
    assert first["metric_query_count"] == 3
    assert first["metric_stat_query_count"] == 1
    assert first["expression_query_count"] == 2
    assert first["metrics_insights_query_count"] == 1
    assert first["metrics_requested"] == 1
    assert first["metadata"]["paginated_request"] is False
    assert second["metadata"]["paginated_request"] is True


def test_non_cloudwatch_clients_pass_through_without_telemetry():
    source, session = wrapped_session()
    assert session.client("ec2", region_name="sa-east-1") is source.other_client
    assert _buffered_events() == []


def test_commit_batches_events_and_correlates_collection_run():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    started = datetime.now(UTC) - timedelta(minutes=2)

    with Session(engine) as db:
        db.add(
            CloudAccount(
                id=7,
                provider="aws",
                native_account_id="123456789012",
                name="AWS test",
            )
        )
        scan = Scan(
            id="scan-1",
            account_id=None,
            cloud_account_id=7,
            status="running",
            trigger="manual",
            started_at=started,
        )
        db.add(scan)
        db.add(
            CollectionRun(
                id="run-1",
                scan_id="scan-1",
                provider="aws",
                account_id="123456789012",
                scope={"regions": ["sa-east-1"]},
                started_at=started,
                status="RUNNING",
            )
        )
        db.commit()

        _, session = wrapped_session()
        client = session.client("cloudwatch", region_name="sa-east-1")
        for metric in ("CPUUtilization", "DatabaseConnections"):
            client.get_metric_statistics(
                Namespace="AWS/RDS",
                MetricName=metric,
                StartTime=started,
                EndTime=datetime.now(UTC),
                Period=86400,
                Statistics=["Average"],
            )

        db.commit()
        events = list(db.scalars(select(CloudWatchUsageEvent).order_by(CloudWatchUsageEvent.id)))

    assert len(events) == 2
    assert {event.collection_run_id for event in events} == {"run-1"}
    assert {event.cloud_account_id for event in events} == {7}
    assert {event.aws_account_id for event in events} == {"123456789012"}
    engine.dispose()


def test_query_filters_pagination_and_database_summary():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add_all(
            [
                CloudWatchUsageEvent(
                    occurred_at=now - timedelta(minutes=2),
                    provider="aws",
                    aws_service="cloudwatch",
                    aws_account_id="111111111111",
                    region="sa-east-1",
                    operation="GetMetricStatistics",
                    collector="rds_nonprod_idle",
                    analyzer="rds_nonprod_idle",
                    request_count=1,
                    retry_count=0,
                    request_count_is_exact=True,
                    metrics_requested=1,
                    success=True,
                    event_metadata={},
                ),
                CloudWatchUsageEvent(
                    occurred_at=now - timedelta(minutes=1),
                    provider="aws",
                    aws_service="cloudwatch",
                    aws_account_id="222222222222",
                    region="us-east-1",
                    operation="GetMetricStatistics",
                    collector="load_balancer_no_traffic",
                    analyzer="load_balancer_no_traffic",
                    request_count=2,
                    retry_count=1,
                    request_count_is_exact=True,
                    metrics_requested=1,
                    success=False,
                    error_type="Throttling",
                    event_metadata={},
                ),
            ]
        )
        db.commit()

        page = list_usage_events(
            db,
            CloudWatchUsageFilters(aws_account_id="222222222222", success=False),
            page=1,
            page_size=1,
        )
        summary = usage_summary(db, CloudWatchUsageFilters(), group_by="account")

    assert page["total"] == 1
    assert page["items"][0]["error_type"] == "Throttling"
    assert {item["group"] for item in summary["items"]} == {
        "111111111111",
        "222222222222",
    }
    assert sum(item["requests"] for item in summary["items"]) == 3
    assert sum(item["failed_events"] for item in summary["items"]) == 1
    engine.dispose()
