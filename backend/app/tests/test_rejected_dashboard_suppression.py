from sqlalchemy.orm import Session

from app.models.finding import Finding
from app.services.dashboard import _recent_changes
from app.services.dashboard_aggregation import refresh_summaries_for_findings
from app.tests.test_dashboard import client, dashboard  # noqa: F401


def test_rejected_target_only_observation_is_not_operationally_new(dashboard):  # noqa: F811
    http, engine = dashboard

    before = http.get("/dashboard/summary?provider=aws&account_id=111111111111").json()
    assert before["opportunities"]["new_since_previous"] == 1

    with Session(engine) as db:
        finding = db.get(Finding, "opp-010")
        assert finding is not None
        finding.status = "rejected"
        finding.needs_review = False
        refresh_summaries_for_findings(db, [finding])
        db.commit()

    after = http.get("/dashboard/summary?provider=aws&account_id=111111111111").json()
    assert after["opportunities"]["new_since_previous"] == 0
    assert after["recent_changes"]["new"] == 0

    with Session(engine) as db:
        direct = _recent_changes(db, provider="aws", account_id="111111111111")
        assert direct["new"] == 0
