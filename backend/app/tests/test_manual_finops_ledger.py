import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.finding import Finding
from app.models.finops_ledger import FinOpsLedgerEntry
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.finops_ledger import FinOpsLedgerService
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _aws_account(db: Session) -> CloudAccount:
    account = db.scalar(select(CloudAccount).where(CloudAccount.provider == "aws"))
    assert account is not None
    return account


def _oci_account(db: Session) -> CloudAccount:
    account = db.scalar(select(CloudAccount).where(CloudAccount.provider == "oci"))
    if account is None:
        account = CloudAccount(
            provider="oci",
            native_account_id="ocid1.tenancy.oc1..manualledgerfixture",
            name="OCI manual ledger fixture",
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


def _payload(
    cloud_account_id: int,
    **overrides,
) -> dict:
    payload = {
        "entry_type": "SAVING",
        "provider": "aws",
        "cloud_account_id": cloud_account_id,
        "amount": "1000.00",
        "currency": "USD",
        "effective_date": utcnow().date().isoformat(),
        "periodicity": "MONTHLY",
        "description": "Saving manual validado",
        "manual_entry_request_id": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("entry_type", "direction", "expected_direction"),
    [
        ("SAVING", None, "CREDIT"),
        ("REALLOCATION", None, "DEBIT"),
        ("ADJUSTMENT", "CREDIT", "CREDIT"),
        ("ADJUSTMENT", "DEBIT", "DEBIT"),
    ],
)
def test_manual_entry_types_use_server_side_source_and_direction(
    auth_env,
    entry_type,
    direction,
    expected_direction,
):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        account = _aws_account(db)
        account_id = account.id

    payload = _payload(account_id, entry_type=entry_type, periodicity="ONE_TIME")
    if direction is not None:
        payload["direction"] = direction

    response = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens, "operator"),
        json=payload,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["entry_type"] == entry_type
    assert data["direction"] == expected_direction
    assert data["source"] == "MANUAL"
    assert data["created_by"] == ids["operator"]
    assert data["provider"] == "aws"
    assert Decimal(data["amount"]) == Decimal("1000.00")


@pytest.mark.parametrize(
    "overrides",
    [
        {"entry_type": "SAVING", "direction": "DEBIT"},
        {"entry_type": "REALLOCATION", "direction": "CREDIT"},
        {"entry_type": "ADJUSTMENT"},
        {"amount": "0"},
        {"amount": "-1"},
        {"currency": "EUR"},
    ],
)
def test_manual_entry_rejects_invalid_financial_payloads(auth_env, overrides):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db:
        account_id = _aws_account(db).id
    response = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens),
        json=_payload(account_id, **overrides),
    )
    assert response.status_code == 422, response.text


def test_manual_entry_rejects_source_and_actor_spoofing(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        account_id = _aws_account(db).id

    for spoofed in (
        {"source": "OPPORTUNITY"},
        {"created_by": ids["viewer"]},
        {"reversal_of": "forged"},
    ):
        response = http.post(
            "/api/v1/finops/ledger/manual",
            headers=headers(tokens),
            json=_payload(account_id, **spoofed),
        )
        assert response.status_code == 422, response.text


def test_manual_entry_validates_provider_account_without_structural_currency_coupling(auth_env):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db:
        aws = _aws_account(db)
        oci = _oci_account(db)
        aws_id = aws.id
        oci_id = oci.id

    mismatch = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens),
        json=_payload(oci_id, provider="aws", currency="BRL"),
    )
    assert mismatch.status_code == 422, mismatch.text
    assert "provider does not match" in mismatch.json()["detail"]

    cross_currency = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens),
        json=_payload(
            aws_id,
            currency="BRL",
            amount="25.50",
            description="Ajuste legítimo em BRL para conta AWS",
        ),
    )
    assert cross_currency.status_code == 201, cross_currency.text
    assert cross_currency.json()["currency"] == "BRL"


def test_manual_effective_date_periodicity_and_idempotency_are_preserved(auth_env):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db:
        account_id = _aws_account(db).id

    effective_date = utcnow().date() - timedelta(days=5)
    request_id = str(uuid.uuid4())
    payload = _payload(
        account_id,
        effective_date=effective_date.isoformat(),
        periodicity="MONTHLY",
        description="Renegociação mensal retroativa",
        manual_entry_request_id=request_id,
    )
    first = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens),
        json=payload,
    )
    second = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens),
        json=payload,
    )
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["effective_at"].startswith(effective_date.isoformat())
    assert first.json()["periodicity"] == "MONTHLY"
    assert first.json()["created_at"][:10] >= effective_date.isoformat()

    with Session(engine) as db:
        count = db.scalar(
            select(func.count())
            .select_from(FinOpsLedgerEntry)
            .where(FinOpsLedgerEntry.idempotency_key == f"manual:{request_id}")
        )
        assert count == 1


def test_manual_entry_rejects_future_effective_date(auth_env):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db:
        account_id = _aws_account(db).id
    response = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens),
        json=_payload(
            account_id,
            effective_date=(utcnow().date() + timedelta(days=1)).isoformat(),
        ),
    )
    assert response.status_code == 422, response.text
    assert "future" in response.json()["detail"]


def test_reversal_requires_reason_is_complete_and_cannot_repeat(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        account_id = _aws_account(db).id

    created = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens),
        json=_payload(account_id, amount="1000", currency="USD"),
    )
    assert created.status_code == 201, created.text
    original = created.json()

    missing_reason = http.post(
        f"/api/v1/finops/ledger/{original['id']}/reverse",
        headers=headers(tokens, "operator"),
        json={"reason": ""},
    )
    assert missing_reason.status_code == 422

    reversed_response = http.post(
        f"/api/v1/finops/ledger/{original['id']}/reverse",
        headers=headers(tokens, "operator"),
        json={"reason": "Movimentação cadastrada na conta incorreta."},
    )
    assert reversed_response.status_code == 200, reversed_response.text
    reversal = reversed_response.json()
    assert reversal["direction"] == "DEBIT"
    assert Decimal(reversal["amount"]) == Decimal(original["amount"])
    assert reversal["currency"] == original["currency"]
    assert reversal["reversal_of_id"] == original["id"]
    assert reversal["source"] == "SYSTEM"
    assert reversal["created_by"] == ids["operator"]

    detail = http.get(
        f"/api/v1/finops/ledger/{original['id']}",
        headers=headers(tokens),
    )
    assert detail.status_code == 200
    assert detail.json()["is_reversed"] is True
    assert detail.json()["reversed_by_id"] == reversal["id"]

    repeated = http.post(
        f"/api/v1/finops/ledger/{original['id']}/reverse",
        headers=headers(tokens),
        json={"reason": "Tentativa duplicada"},
    )
    assert repeated.status_code == 409


def test_opportunity_entry_reversal_does_not_change_finding_lifecycle(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        account = _aws_account(db)
        actor = db.get(User, ids["admin"])
        finding = db.get(Finding, "finding")
        assert actor is not None and finding is not None
        finding.status = "treated"
        event = OpportunityStatusHistory(
            opportunity_id=finding.id,
            from_status="open",
            to_status="treated",
            action="treat",
            changed_by=actor.id,
            changed_at=utcnow(),
        )
        db.add(event)
        db.flush()
        entry = FinOpsLedgerService(db).create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=account.id,
            amount="500",
            currency="USD",
            effective_at=event.changed_at,
            source="OPPORTUNITY",
            actor=actor,
            opportunity_id=finding.id,
            source_event_id=event.id,
            idempotency_key=f"opportunity-treated:{event.id}:saving",
        )
        db.commit()
        entry_id = entry.id

    response = http.post(
        f"/api/v1/finops/ledger/{entry_id}/reverse",
        headers=headers(tokens),
        json={"reason": "Saving reconhecido incorretamente"},
    )
    assert response.status_code == 200, response.text
    with Session(engine) as db:
        finding = db.get(Finding, "finding")
        assert finding is not None
        assert finding.status == "treated"


def test_manual_mutations_require_operator_permission(auth_env):
    http, engine, tokens, _ = auth_env
    with Session(engine) as db:
        account_id = _aws_account(db).id

    create_response = http.post(
        "/api/v1/finops/ledger/manual",
        headers=headers(tokens, "viewer"),
        json=_payload(account_id),
    )
    assert create_response.status_code == 403
