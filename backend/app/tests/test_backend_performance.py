"""Contract and bounded-loading regression tests (SQLite and CI PostgreSQL)."""

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.collection_run import CollectionRun
from app.services.collection_comparison import compare_collection_runs
from app.services.collection_query import get_collection
from app.services.dashboard import dashboard_summary
from app.services.opportunity_query import OpportunityFilters, list_opportunities
from app.tests.test_migrations import migration_engine  # noqa: F401
from benchmarks.backend_reads import seed


def test_read_contracts_and_bounded_loading(migration_engine):  # noqa: F811
    Base.metadata.create_all(migration_engine)
    seed(migration_engine, accounts=2, per_account=60)
    statements, loaded = [], []

    def query(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement.lower())

    event.listen(migration_engine, "before_cursor_execute", query)
    try:
        with Session(migration_engine) as db:
            event.listen(db, "loaded_as_persistent", lambda _db, obj: loaded.append(type(obj)))
            for size in (1, 50):
                statements.clear()
                result = list_opportunities(
                    db,
                    OpportunityFilters(),
                    page=1,
                    page_size=size,
                    sort="last_seen_at",
                    order="desc",
                )
                assert result["total"] == 120
                assert len(result["items"]) == size
                assert len(statements) <= 2
                assert "join" not in statements[0]
                assert all("findings.evidence" not in sql for sql in statements)
                assert all("aws_accounts.external_id" not in sql for sql in statements)

            current = list_opportunities(
                db,
                OpportunityFilters(provider="aws", current=True, status="open"),
                page=1,
                page_size=50,
                sort="last_seen_at",
                order="desc",
            )
            assert current["total"] == 18
            summary = dashboard_summary(db, provider="aws")
            assert summary["opportunities"]["open"] == 18
            assert summary["opportunities"]["treated"] == 18
            assert summary["opportunities"]["rejected"] == 18
            assert summary["financial"]["totals"][0]["amount"] == 184
            assert summary["recent_changes"]["new"] == 6
            assert summary["recent_changes"]["no_longer_detected"] == 6

            baseline = db.get(CollectionRun, "run-0-98")
            target = db.get(CollectionRun, "run-0-99")
            for category, expected in (
                ("NEW", 6),
                ("NO_LONGER_DETECTED", 6),
                ("CHANGED", 12),
                ("PERSISTENT", 36),
            ):
                statements.clear()
                loaded.clear()
                pages = []
                for page in range(1, expected // 3 + 2):
                    result = compare_collection_runs(
                        db, target, baseline=baseline, category=category, page=page, page_size=3
                    )
                    assert result["total"] == expected
                    assert result["summary"]["baseline_total"] == 54
                    assert result["financial_summary"]["delta"] == 12
                    pages.extend(item["opportunity_id"] for item in result["items"])
                assert len(pages) == len(set(pages)) == expected
                assert pages == sorted(pages)
                assert loaded == []  # Snapshots are projections, not unbounded ORM graphs.
                assert all("findings.evidence" not in sql for sql in statements)
                assert len(statements) <= 3 * (expected // 3 + 1)
                if category in {"NEW", "NO_LONGER_DETECTED"}:
                    assert "limit" in statements[-1]
            statements.clear()
            assert get_collection(db, "run-0-99")["opportunities_observed"] == 54
            assert len(statements) <= 2
    finally:
        event.remove(migration_engine, "before_cursor_execute", query)
