from datetime import timedelta

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import worker
from app.api.routes.collections import router
from app.models.collection_run import CollectionRun
from app.models.scan import Scan
from app.services import collection_executors
from app.services.collection_errors import GENERIC_ERROR, sanitize_collection_error
from app.services.collection_query import CollectionFilters, list_collections
from app.tests.test_opportunities_api import START, client  # noqa: F401


@pytest.fixture
def collections(client):  # noqa: F811
    http, engine = client
    http.app.include_router(router)
    with Session(engine) as db:
        db.add_all(
            [
                CollectionRun(
                    id="oci-failed",
                    provider="oci",
                    account_id="ocid1.tenancy.example",
                    started_at=START + timedelta(days=2),
                    finished_at=START + timedelta(days=2, seconds=12),
                    status="FAILED",
                    error_detail="AccessDenied token=PRIVATE postgres://user:pass@host/db",
                ),
                CollectionRun(
                    id="aws-running",
                    provider="aws",
                    account_id="111111111111",
                    started_at=START + timedelta(days=3),
                    status="RUNNING",
                ),
            ]
        )
        db.get(CollectionRun, "run-a1").analyzer_version = "v1"
        db.get(CollectionRun, "run-a1").opportunities_found = 5
        db.commit()
    return http, engine


def test_collection_pagination_sort_and_legacy(collections):
    http, _ = collections
    page = http.get("/collections?page=1&page_size=2").json()
    assert page["total"] == 5 and page["total_pages"] == 3
    assert [i["id"] for i in page["items"]] == ["aws-running", "oci-failed"]
    second = http.get("/collections?page=2&page_size=2").json()
    assert len(second["items"]) == 2
    assert not {i["id"] for i in page["items"]} & {i["id"] for i in second["items"]}
    assert http.get("/collections?page=9").json()["items"] == []
    legacy = http.get("/collections?limit=2&offset=2").json()
    assert isinstance(legacy, list) and [i["id"] for i in legacy] == [
        i["id"] for i in second["items"]
    ]
    ordered = http.get("/collections?page=1&sort=opportunities_found&order=desc").json()
    assert ordered["items"][0]["id"] == "run-a1"
    assert (
        http.get("/collections?page=1&sort=started_at&order=asc").json()["items"][0]["id"]
        == "run-a1"
    )


@pytest.mark.parametrize(
    "query,ids",
    [
        ("provider=oci", {"oci-failed"}),
        ("provider=AWS", {"run-a1", "run-a2", "run-b1", "aws-running"}),
        ("account_id=222222222222", {"run-b1"}),
        ("status=FAILED", {"oci-failed"}),
        ("status=failed", {"oci-failed"}),
        ("provider=aws&account_id=111111111111&status=SUCCESS&analyzer_version=v1", {"run-a1"}),
        ("provider=gcp", set()),
    ],
)
def test_collection_filters(collections, query, ids):
    http, _ = collections
    response = http.get(f"/collections?page=1&{query}")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["items"]} == ids


def test_date_bounds_are_start_inclusive_end_exclusive_and_timezone_aware(collections):
    http, _ = collections
    response = http.get(
        "/collections",
        params={
            "page": 1,
            "date_from": "2026-09-21T09:00:00-03:00",
            "date_to": "2026-09-22T12:00:00Z",
        },
    )
    assert [i["id"] for i in response.json()["items"]] == ["run-a2"]
    response = http.get("/collections", params={"page": 1, "date_from": "2026-09-22T12:00:00Z"})
    assert {i["id"] for i in response.json()["items"]} == {"oci-failed", "aws-running"}


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page_size=201",
        "sort=error_detail",
        "order=oops",
        "status=STUCK",
        "date_from=invalid",
        "date_from=2026-10-01&date_to=2026-09-01",
    ],
)
def test_invalid_filters(collections, query):
    assert collections[0].get(f"/collections?{query}").status_code == 422


def test_detail_counts_observations_and_sanitizes_historical_errors(collections):
    http, _ = collections
    detail = http.get("/collections/run-a1").json()
    assert detail["opportunities_observed"] == 5  # not 100 findings or the latest scan
    assert detail["account_name"] == "Production"
    assert detail["duration_seconds"] == 120
    assert detail["analyzer_version"] == "v1"
    assert detail["resources_analyzed_available"] is False
    assert detail["started_at"].endswith("Z")
    assert "evidence" not in detail and "observations" not in detail
    assert http.get("/collections/missing").status_code == 404
    failed = http.get("/collections/oci-failed").json()
    assert "AccessDenied" in failed["error_detail"] and "PRIVATE" not in str(failed)
    assert "user:pass" not in str(failed)
    assert failed["duration_seconds"] == 12
    linked = http.get("/opportunities?collection_run_id=run-a1").json()
    assert linked["total"] == detail["opportunities_observed"]
    assert "opp-002" in {item["id"] for item in linked["items"]}
    assert http.get("/collections/aws-running").json()["duration_seconds"] is None


def test_account_context_ignores_date_status_and_options_are_bounded(collections):
    http, _ = collections
    page = http.get("/collections?page=1&provider=aws&account_id=111111111111&status=FAILED").json()
    assert page["items"] == []
    assert page["account_summary"]["latest_run"]["id"] == "aws-running"
    assert page["account_summary"]["latest_success"]["id"] == "run-a2"
    options = http.get("/collections/options?limit=1").json()
    assert options["providers"] == ["aws", "oci"]
    assert len(options["accounts"]) == 1 and options["has_more_accounts"]
    options = http.get("/collections/options?search=Production&provider=aws").json()
    assert options["accounts"] == [
        {"provider": "aws", "account_id": "111111111111", "account_name": "Production"}
    ]
    assert (
        http.get("/collections/options?provider=oci").json()["accounts"][0]["account_id"]
        == "ocid1.tenancy.example"
    )


def test_collection_list_has_constant_query_count(collections):
    _, engine = collections
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    with Session(engine) as db:
        event.listen(engine, "before_cursor_execute", record)
        try:
            for size in (1, 50):
                statements.clear()
                list_collections(
                    db, CollectionFilters(), page=1, page_size=size, sort="started_at", order="desc"
                )
                assert len(statements) == 2
                assert "LIMIT" in statements[1] and "opportunity_observations" not in statements[1]
        finally:
            event.remove(engine, "before_cursor_execute", record)


def test_worker_failure_and_warning_flow_are_sanitized(collections, monkeypatch):
    http, engine = collections
    with Session(engine) as db:
        # Run through the same worker boundary as process_once.
        worker.fail_scan(db, "scan-a1", RuntimeError("AccessDenied token=PRIVATE"))
        assert db.get(Scan, "scan-a1").error == sanitize_collection_error("AccessDenied")
    assert http.get("/collections/run-a1").json()["status"] == "FAILED"
    with Session(engine) as db:
        scan = db.get(Scan, "scan-a2")
        monkeypatch.setattr(collection_executors, "assume_account_session", lambda _: object())
        monkeypatch.setattr(
            collection_executors,
            "get_caller_identity",
            lambda _: type("Identity", (), {"account_id": "111111111111"})(),
        )
        monkeypatch.setattr(collection_executors, "list_effective_policies", lambda *_: [])
        monkeypatch.setattr(
            collection_executors,
            "run_collectors",
            lambda *_: ([], ["AccessDenied secret=PRIVATE"], set()),
        )
        worker.execute_scan(db, scan)
    detail = http.get("/collections/run-a2").json()
    assert detail["status"] == "SUCCESS" and detail["has_warnings"]
    assert "AccessDenied" in detail["warning_detail"] and "PRIVATE" not in detail["warning_detail"]


@pytest.mark.parametrize(
    "raw",
    [
        "postgres://admin:PRIVATE@host/db",
        "Authorization: Bearer PRIVATE",
        "aws_access_key_id=PRIVATE",
        "Traceback (most recent call last):\npassword=PRIVATE",
        "x-api-key: PRIVATE",
        '{"token": "PRIVATE"}',
    ],
)
def test_sanitizer_drops_unstructured_payload(raw):
    assert sanitize_collection_error(raw) == GENERIC_ERROR
    assert sanitize_collection_error(sanitize_collection_error(raw)) == GENERIC_ERROR


def test_collection_reads_require_auth(collections):
    http, _ = collections
    http.headers.pop("Cookie")
    http.cookies.clear()
    for path in ("/collections?page=1", "/collections/options", "/collections/run-a1"):
        assert http.get(path).status_code == 401


def test_legacy_scan_errors_are_also_safe_on_read(collections):
    from app.api.routes.scans import router as scans_router

    http, engine = collections
    http.app.include_router(scans_router)
    with Session(engine) as db:
        db.get(Scan, "scan-a1").error = "AccessDenied secret=PRIVATE"
        db.commit()
    result = http.get("/scans/scan-a1")
    assert result.status_code == 200
    assert "AccessDenied" in result.json()["error"]
    assert "PRIVATE" not in result.text
