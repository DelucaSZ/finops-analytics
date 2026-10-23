from sqlalchemy.orm import Session

from app.models.collection_run import CollectionRun
from app.tests.test_dashboard import dashboard  # noqa: F401
from app.tests.test_opportunities_api import client  # noqa: F401


def _comparison_details(http) -> dict:
    response = http.get("/dashboard/summary?provider=aws&account_id=111111111111")
    assert response.status_code == 200
    details = response.json()["opportunities"]["new_since_previous_details"]
    assert details is not None
    assert details["comparison_context"]
    return details


def test_dashboard_new_since_previous_matches_frozen_deep_link_and_stats(
    dashboard,  # noqa: F811
):
    http, _ = dashboard
    details = _comparison_details(http)
    params = {
        "provider": "aws",
        "account_id": "111111111111",
        "discovery_type": "new_vs_previous",
        "comparison_context": details["comparison_context"],
        "page_size": 100,
    }

    listing = http.get("/opportunities", params=params)
    assert listing.status_code == 200
    assert listing.json()["total"] == details["count"]

    stats = http.get(
        "/opportunities/stats",
        params={key: value for key, value in params.items() if key != "page_size"},
    )
    assert stats.status_code == 200
    assert sum(stats.json().values()) == details["count"]


def test_comparison_context_rejects_tampering(
    dashboard,  # noqa: F811
):
    http, _ = dashboard
    details = _comparison_details(http)
    token = details["comparison_context"]
    replacement = "A" if token[-1] != "A" else "B"
    tampered = token[:-1] + replacement

    response = http.get(
        "/opportunities",
        params={
            "discovery_type": "new_vs_previous",
            "comparison_context": tampered,
        },
    )
    assert response.status_code == 422
    assert "INVALID_CONTEXT" in response.json()["detail"]


def test_frozen_comparison_returns_gone_after_observation_retention_expires(
    dashboard,  # noqa: F811
):
    http, engine = dashboard
    details = _comparison_details(http)

    with Session(engine) as db:
        baseline = db.get(CollectionRun, "run-a1")
        assert baseline is not None
        baseline.detailed_observations_available = False
        db.commit()

    response = http.get(
        "/opportunities",
        params={
            "provider": "aws",
            "account_id": "111111111111",
            "discovery_type": "new_vs_previous",
            "comparison_context": details["comparison_context"],
        },
    )
    assert response.status_code == 410
    assert "CONTEXT_EXPIRED" in response.json()["detail"]
