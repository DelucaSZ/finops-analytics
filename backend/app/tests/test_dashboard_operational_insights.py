from datetime import timedelta

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun
from app.services.dashboard_operational_insights import collection_failure_insights
from app.tests.test_dashboard import dashboard  # noqa: F401
from app.tests.test_opportunities_api import START


def _run(
    *,
    run_id: str,
    provider: str,
    account_id: str,
    minutes: int,
    status: str,
    error_detail: str | None = None,
):
    started_at = START + timedelta(days=4, minutes=minutes)
    return CollectionRun(
        id=run_id,
        provider=provider,
        account_id=account_id,
        started_at=started_at,
        finished_at=None if status == "RUNNING" else started_at + timedelta(minutes=1),
        status=status,
        error_detail=error_detail,
    )


def _active_account(db: Session, provider: str, account_id: str) -> CloudAccount:
    return db.scalar(
        select(CloudAccount).where(
            CloudAccount.provider == provider,
            CloudAccount.native_account_id == account_id,
        )
    )


def test_latest_failed_terminal_run_is_exposed_with_safe_account_identity(
    dashboard,  # noqa: F811
):
    http, _ = dashboard

    response = http.get("/dashboard/operational-insights")

    assert response.status_code == 200
    body = response.json()["collection_failures"]
    assert body["count"] == 1
    assert body["truncated"] is False
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["provider"] == "aws"
    assert item["account_id"] == "111111111111"
    assert item["collection_run_id"] == "run-a3-failed"
    assert item["status"] == "FAILED"
    assert "AccessDenied" in item["error_summary"]
    assert item["newer_run"] is None


def test_success_posterior_resolves_failure_and_historical_failed_does_not_return(
    dashboard,  # noqa: F811
):
    http, engine = dashboard
    with Session(engine) as db:
        db.add(
            _run(
                run_id="run-a4-success",
                provider="aws",
                account_id="111111111111",
                minutes=10,
                status="SUCCESS",
            )
        )
        db.commit()

    body = http.get("/dashboard/operational-insights").json()["collection_failures"]
    assert body == {"count": 0, "items": [], "truncated": False}

    with Session(engine) as db:
        db.add(
            _run(
                run_id="run-a5-failed",
                provider="aws",
                account_id="111111111111",
                minutes=20,
                status="FAILED",
                error_detail="AccessDenied",
            )
        )
        db.commit()

    current = http.get("/dashboard/operational-insights").json()["collection_failures"]
    assert current["count"] == 1
    assert current["items"][0]["collection_run_id"] == "run-a5-failed"


def test_newer_running_run_keeps_last_failed_terminal_visible(
    dashboard,  # noqa: F811
):
    http, engine = dashboard
    with Session(engine) as db:
        db.add(
            _run(
                run_id="run-a4-running",
                provider="aws",
                account_id="111111111111",
                minutes=10,
                status="RUNNING",
            )
        )
        db.commit()

    response = http.get("/dashboard/operational-insights").json()
    item = response["collection_failures"]["items"][0]
    assert item["collection_run_id"] == "run-a3-failed"
    assert item["newer_run"]["id"] == "run-a4-running"
    assert item["newer_run"]["status"] == "RUNNING"

    with Session(engine) as db:
        running = db.get(CollectionRun, "run-a4-running")
        running.status = "SUCCESS"
        running.finished_at = running.started_at + timedelta(minutes=2)
        db.commit()

    resolved = http.get("/dashboard/operational-insights").json()["collection_failures"]
    assert resolved == {"count": 0, "items": [], "truncated": False}


def test_provider_and_account_scope_do_not_mix_clouds(
    dashboard,  # noqa: F811
):
    http, engine = dashboard
    with Session(engine) as db:
        db.add(
            _run(
                run_id="run-oci-failed",
                provider="oci",
                account_id="ocid1.tenancy.dashboard",
                minutes=30,
                status="FAILED",
                error_detail="OCI authentication failure private-key=DO-NOT-LEAK",
            )
        )
        db.commit()

    global_response = http.get("/dashboard/operational-insights").json()
    global_items = global_response["collection_failures"]["items"]
    assert {(item["provider"], item["account_id"]) for item in global_items} == {
        ("aws", "111111111111"),
        ("oci", "ocid1.tenancy.dashboard"),
    }

    aws_response = http.get("/dashboard/operational-insights?provider=aws").json()
    aws = aws_response["collection_failures"]
    assert aws["count"] == 1
    assert {item["provider"] for item in aws["items"]} == {"aws"}

    oci_response = http.get(
        "/dashboard/operational-insights?provider=oci&account_id=ocid1.tenancy.dashboard"
    ).json()
    oci = oci_response["collection_failures"]
    assert oci["count"] == 1
    assert oci["items"][0]["provider"] == "oci"
    assert oci["items"][0]["account_id"] == "ocid1.tenancy.dashboard"


def test_error_summary_is_allowlisted_and_does_not_echo_credentials(
    dashboard,  # noqa: F811
):
    http, engine = dashboard
    secret = "AKIA_NOT_A_REAL_KEY_BUT_MUST_NOT_LEAK"
    with Session(engine) as db:
        failed = db.get(CollectionRun, "run-a3-failed")
        failed.error_detail = (
            f"Authorization: Bearer token-super-secret password=hunter2 secret={secret}"
        )
        db.commit()

    response = http.get("/dashboard/operational-insights").json()
    summary = response["collection_failures"]["items"][0]["error_summary"]
    assert summary == "Falha durante a coleta. Verifique a conexão e as permissões da conta."
    assert "Bearer" not in summary
    assert "hunter2" not in summary
    assert secret not in summary


def test_disabled_account_does_not_keep_home_alert_alive(
    dashboard,  # noqa: F811
):
    http, engine = dashboard
    with Session(engine) as db:
        account = _active_account(db, "aws", "111111111111")
        assert account is not None
        account.enabled = False
        db.commit()

    body = http.get("/dashboard/operational-insights").json()["collection_failures"]
    assert body == {"count": 0, "items": [], "truncated": False}


def test_failures_are_ordered_newest_first_and_response_is_bounded(
    dashboard,  # noqa: F811
):
    http, engine = dashboard
    with Session(engine) as db:
        db.add(
            _run(
                run_id="run-b2-failed",
                provider="aws",
                account_id="222222222222",
                minutes=40,
                status="FAILED",
                error_detail="UnauthorizedOperation",
            )
        )
        db.commit()

    response = http.get("/dashboard/operational-insights?max_items=1").json()
    body = response["collection_failures"]
    assert body["count"] == 2
    assert body["truncated"] is True
    assert len(body["items"]) == 1
    assert body["items"][0]["collection_run_id"] == "run-b2-failed"


def test_service_uses_one_bounded_query_without_per_account_reads(
    dashboard,  # noqa: F811
):
    _, engine = dashboard
    statements: list[str] = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    with Session(engine) as db:
        event.listen(engine, "before_cursor_execute", record)
        try:
            result = collection_failure_insights(db, max_items=10)
        finally:
            event.remove(engine, "before_cursor_execute", record)

    assert result["collection_failures"]["count"] == 1
    assert len(statements) == 1
    assert "row_number" in statements[0].lower()
