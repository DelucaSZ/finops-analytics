from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.finops_ledger import FinOpsLedgerEntry
from app.models.opportunity_observation import OpportunityObservation
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.opportunity_saving_recognition import OpportunitySavingRecognitionService
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _entries(db: Session, finding_id: str) -> list[FinOpsLedgerEntry]:
    return list(
        db.scalars(
            select(FinOpsLedgerEntry)
            .where(FinOpsLedgerEntry.opportunity_id == finding_id)
            .order_by(FinOpsLedgerEntry.effective_at, FinOpsLedgerEntry.id)
        )
    )


def _treatment_events(db: Session, finding_id: str) -> list[OpportunityStatusHistory]:
    return list(
        db.scalars(
            select(OpportunityStatusHistory)
            .where(
                OpportunityStatusHistory.opportunity_id == finding_id,
                OpportunityStatusHistory.action == "treat",
            )
            .order_by(OpportunityStatusHistory.changed_at, OpportunityStatusHistory.id)
        )
    )


def _new_finding(
    db: Session,
    *,
    finding_id: str,
    fingerprint: str,
    provider: str = "aws",
    account_id: str = "123456789012",
    saving: str = "100",
    currency: str = "USD",
) -> Finding:
    now = datetime.now(UTC)
    finding = Finding(
        id=finding_id,
        fingerprint=fingerprint,
        provider=provider,
        account_id=account_id,
        rule_key="test_rule",
        service="Compute",
        region="sa-east-1",
        resource_id=f"resource-{finding_id}",
        title=f"Opportunity {finding_id}",
        description="Test opportunity",
        evidence={},
        current_monthly_cost=Decimal(saving),
        estimated_monthly_savings=Decimal(saving),
        currency=currency,
        confidence="high",
        severity="medium",
        status="open",
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(finding)
    db.flush()
    return finding


def _observation(
    db: Session,
    finding: Finding,
    *,
    observed_at: datetime,
    saving: str,
    currency: str,
) -> OpportunityObservation:
    run = CollectionRun(
        provider=finding.provider,
        account_id=finding.account_id,
        scope={},
        started_at=observed_at,
        finished_at=observed_at,
        status=CollectionRunStatus.SUCCESS.value,
    )
    db.add(run)
    db.flush()
    observation = OpportunityObservation(
        opportunity_id=finding.id,
        collection_run_id=run.id,
        observed_at=observed_at,
        severity=finding.severity,
        current_monthly_cost=Decimal(saving),
        estimated_monthly_savings=Decimal(saving),
        currency=currency,
        confidence=finding.confidence,
        provider_metadata={},
        evidence={},
    )
    db.add(observation)
    db.flush()
    return observation


def test_first_treatment_recognizes_monthly_saving_and_is_event_idempotent(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        finding.estimated_monthly_savings = Decimal("500")
        finding.currency = "USD"
        db.commit()

    response = http.post(
        "/api/v1/findings/finding/treat",
        headers=headers(tokens),
        json={"note": "resource removed"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "treated"

    with Session(engine) as db:
        entries = _entries(db, "finding")
        events = _treatment_events(db, "finding")
        assert len(entries) == 1
        assert len(events) == 1
        entry = entries[0]
        event = events[0]
        assert entry.entry_type == "SAVING"
        assert entry.direction == "CREDIT"
        assert entry.amount == Decimal("500")
        assert entry.currency == "USD"
        assert entry.periodicity == "MONTHLY"
        assert entry.source == "OPPORTUNITY"
        assert entry.source_reference == "finding"
        assert entry.source_event_id == event.id
        assert entry.effective_at == event.changed_at
        assert entry.created_by == ids["admin"]
        assert entry.context["snapshot_source"] == "FINDING"
        assert entry.context["opportunity_observation_id"] is None

        actor = db.get(User, ids["admin"])
        finding = db.get(Finding, "finding")
        result = OpportunitySavingRecognitionService(db).recognize(finding, event, actor)
        db.commit()
        assert result.entry.id == entry.id
        assert len(_entries(db, "finding")) == 1

    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        finding.estimated_monthly_savings = Decimal("999")
        db.commit()
        assert _entries(db, "finding")[0].amount == Decimal("500")


@pytest.mark.parametrize(
    ("saving", "currency"),
    [("0", "USD"), ("-10", "USD"), ("100", "")],
)
def test_invalid_monetary_snapshot_does_not_block_treatment_or_create_entry(
    auth_env,
    saving,
    currency,
):
    http, engine, tokens, _ids = auth_env
    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        finding.estimated_monthly_savings = Decimal(saving)
        finding.currency = currency
        db.commit()

    response = http.post(
        "/api/v1/findings/finding/treat",
        headers=headers(tokens),
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "treated"
    with Session(engine) as db:
        assert _entries(db, "finding") == []


def test_observation_snapshot_is_provenance_and_new_cycle_uses_new_value(auth_env):
    http, engine, tokens, _ids = auth_env
    first_observed_at = datetime.now(UTC) - timedelta(days=1)
    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        finding.estimated_monthly_savings = Decimal("700")
        finding.currency = "USD"
        first_observation = _observation(
            db,
            finding,
            observed_at=first_observed_at,
            saving="500",
            currency="USD",
        )
        first_observation_id = first_observation.id
        db.commit()

    response = http.post(
        "/api/v1/findings/finding/treat",
        headers=headers(tokens),
        json={},
    )
    assert response.status_code == 200, response.text

    with Session(engine) as db:
        first_event = _treatment_events(db, "finding")[0]
        first_entry = _entries(db, "finding")[0]
        assert first_entry.amount == Decimal("500")
        assert first_entry.context["snapshot_source"] == "OPPORTUNITY_OBSERVATION"
        assert first_entry.context["opportunity_observation_id"] == first_observation_id
        second_observed_at = first_event.changed_at + timedelta(seconds=1)

    response = http.post(
        "/api/v1/findings/finding/reopen",
        headers=headers(tokens),
        json={"note": "new occurrence"},
    )
    assert response.status_code == 200, response.text

    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        finding.estimated_monthly_savings = Decimal("350")
        second_observation = _observation(
            db,
            finding,
            observed_at=second_observed_at,
            saving="350",
            currency="USD",
        )
        second_observation_id = second_observation.id
        db.commit()

    response = http.post(
        "/api/v1/findings/finding/treat",
        headers=headers(tokens),
        json={},
    )
    assert response.status_code == 200, response.text

    with Session(engine) as db:
        entries = _entries(db, "finding")
        events = _treatment_events(db, "finding")
        assert [entry.amount for entry in entries] == [Decimal("500"), Decimal("350")]
        assert entries[1].source_event_id == events[1].id
        assert entries[1].context["opportunity_observation_id"] == second_observation_id


def test_administrative_reopen_and_retreat_does_not_duplicate_saving(auth_env):
    http, engine, tokens, _ids = auth_env
    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        finding.estimated_monthly_savings = Decimal("500")
        finding.currency = "USD"
        db.commit()

    assert (
        http.post("/api/v1/findings/finding/treat", headers=headers(tokens), json={}).status_code
        == 200
    )
    assert (
        http.post("/api/v1/findings/finding/reopen", headers=headers(tokens), json={}).status_code
        == 200
    )
    assert (
        http.post("/api/v1/findings/finding/treat", headers=headers(tokens), json={}).status_code
        == 200
    )

    with Session(engine) as db:
        assert len(_treatment_events(db, "finding")) == 2
        assert len(_entries(db, "finding")) == 1


def test_oci_treatment_preserves_brl_without_conversion(auth_env):
    http, engine, tokens, _ids = auth_env
    with Session(engine) as db:
        account = CloudAccount(
            provider="oci",
            native_account_id="ocid1.tenancy.oc1..treatment",
            name="OCI treatment",
        )
        db.add(account)
        db.flush()
        _new_finding(
            db,
            finding_id="oci-finding",
            fingerprint="o" * 64,
            provider="oci",
            account_id=account.native_account_id,
            saving="300",
            currency="BRL",
        )
        db.commit()

    response = http.post(
        "/api/v1/findings/oci-finding/treat",
        headers=headers(tokens),
        json={},
    )
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        entry = _entries(db, "oci-finding")[0]
        assert entry.provider == "oci"
        assert entry.amount == Decimal("300")
        assert entry.currency == "BRL"


def test_bulk_treatment_creates_only_eligible_entries_and_remains_atomic(auth_env):
    http, engine, tokens, _ids = auth_env
    with Session(engine) as db:
        existing = db.get(Finding, "finding")
        existing.estimated_monthly_savings = Decimal("100")
        existing.currency = "USD"
        _new_finding(
            db,
            finding_id="bulk-zero",
            fingerprint="z" * 64,
            saving="0",
        )
        _new_finding(
            db,
            finding_id="bulk-positive",
            fingerprint="p" * 64,
            saving="250",
        )
        db.commit()

    response = http.post(
        "/api/v1/findings/bulk/action",
        headers=headers(tokens),
        json={
            "finding_ids": ["finding", "bulk-zero", "bulk-positive"],
            "action": "treat",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 3

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(OpportunityStatusHistory)) == 3
        entries = list(
            db.scalars(select(FinOpsLedgerEntry).where(FinOpsLedgerEntry.source == "OPPORTUNITY"))
        )
        assert sorted(entry.amount for entry in entries) == [Decimal("100"), Decimal("250")]


def test_reject_does_not_create_saving(auth_env):
    http, engine, tokens, _ids = auth_env
    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        finding.estimated_monthly_savings = Decimal("500")
        finding.currency = "USD"
        db.commit()

    response = http.post(
        "/api/v1/findings/finding/reject",
        headers=headers(tokens),
        json={"reason": "RISK_ACCEPTED"},
    )
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        assert _entries(db, "finding") == []
