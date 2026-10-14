from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.finops_ledger import FinOpsLedgerEntry
from app.models.opportunity_status_history import OpportunityStatusHistory
from app.models.user import User
from app.services.finops_ledger import (
    FinOpsLedgerConflictError,
    FinOpsLedgerError,
    FinOpsLedgerFilters,
    FinOpsLedgerService,
)
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _accounts(db: Session) -> tuple[CloudAccount, CloudAccount]:
    aws = db.scalar(select(CloudAccount).where(CloudAccount.provider == "aws"))
    assert aws is not None
    oci = db.scalar(select(CloudAccount).where(CloudAccount.provider == "oci"))
    if oci is None:
        oci = CloudAccount(
            provider="oci",
            native_account_id="ocid1.tenancy.oc1..ledgerfixture",
            name="OCI ledger fixture",
        )
        db.add(oci)
        db.flush()
    return aws, oci


def _actor(db: Session, ids: dict) -> User:
    actor = db.get(User, ids["admin"])
    assert actor is not None
    return actor


def test_credit_debit_adjustments_and_multi_currency_summary(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        aws, oci = _accounts(db)
        actor = _actor(db, ids)
        service = FinOpsLedgerService(db)
        now = utcnow()
        service.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount=Decimal("100"),
            currency="USD",
            effective_at=now,
            source="MANUAL",
            actor=actor,
        )
        service.create_entry(
            entry_type="REALLOCATION",
            direction="DEBIT",
            cloud_account_id=aws.id,
            amount=Decimal("20"),
            currency="USD",
            effective_at=now,
            source="MANUAL",
            actor=actor,
        )
        service.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=oci.id,
            amount=Decimal("50"),
            currency="BRL",
            effective_at=now,
            source="MANUAL",
            actor=actor,
        )
        service.create_entry(
            entry_type="ADJUSTMENT",
            direction="DEBIT",
            cloud_account_id=oci.id,
            amount=Decimal("10"),
            currency="BRL",
            effective_at=now,
            source="MANUAL",
            actor=actor,
        )
        service.create_entry(
            entry_type="ADJUSTMENT",
            direction="CREDIT",
            cloud_account_id=oci.id,
            amount=Decimal("5"),
            currency="BRL",
            effective_at=now,
            source="MANUAL",
            actor=actor,
        )
        db.commit()

    response = http.get("/api/v1/finops/ledger/summary", headers=headers(tokens))
    assert response.status_code == 200, response.text
    data = response.json()
    assert set(data) == {"BRL", "USD"}
    assert Decimal(data["USD"]["credits"]) == Decimal("100")
    assert Decimal(data["USD"]["debits"]) == Decimal("20")
    assert Decimal(data["USD"]["balance"]) == Decimal("80")
    assert Decimal(data["BRL"]["credits"]) == Decimal("55")
    assert Decimal(data["BRL"]["debits"]) == Decimal("10")
    assert Decimal(data["BRL"]["balance"]) == Decimal("45")
    assert "balance" not in data


def test_amount_direction_and_manual_actor_validation(auth_env):
    _, engine, _, ids = auth_env
    with Session(engine) as db:
        aws, _ = _accounts(db)
        actor = _actor(db, ids)
        service = FinOpsLedgerService(db)
        common = {
            "cloud_account_id": aws.id,
            "currency": "USD",
            "effective_at": utcnow(),
            "source": "MANUAL",
            "actor": actor,
        }
        for invalid in (Decimal("0"), Decimal("-1")):
            with pytest.raises(FinOpsLedgerError, match="greater than zero"):
                service.create_entry(
                    entry_type="SAVING",
                    direction="CREDIT",
                    amount=invalid,
                    **common,
                )
        with pytest.raises(FinOpsLedgerError, match="SAVING"):
            service.create_entry(
                entry_type="SAVING",
                direction="DEBIT",
                amount=Decimal("1"),
                **common,
            )
        with pytest.raises(FinOpsLedgerError, match="REALLOCATION"):
            service.create_entry(
                entry_type="REALLOCATION",
                direction="CREDIT",
                amount=Decimal("1"),
                **common,
            )
        with pytest.raises(FinOpsLedgerError, match="authenticated actor"):
            service.create_entry(
                entry_type="ADJUSTMENT",
                direction="CREDIT",
                cloud_account_id=aws.id,
                amount=Decimal("1"),
                currency="USD",
                effective_at=utcnow(),
                source="MANUAL",
            )


def test_aws_usd_and_oci_brl_are_preserved_without_cross_currency_rule(auth_env):
    _, engine, _, ids = auth_env
    with Session(engine) as db:
        aws, oci = _accounts(db)
        actor = _actor(db, ids)
        service = FinOpsLedgerService(db)
        aws_entry = service.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="12.34",
            currency="USD",
            effective_at=utcnow(),
            source="MANUAL",
            actor=actor,
        )
        oci_entry = service.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=oci.id,
            amount="56.78",
            currency="BRL",
            effective_at=utcnow(),
            source="MANUAL",
            actor=actor,
        )
        db.commit()
        assert aws_entry.provider == "aws" and aws_entry.currency == "USD"
        assert oci_entry.provider == "oci" and oci_entry.currency == "BRL"


def test_list_filters_period_pagination_and_get(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        aws, oci = _accounts(db)
        actor = _actor(db, ids)
        service = FinOpsLedgerService(db)
        now = utcnow()
        first = service.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="10",
            currency="USD",
            effective_at=now - timedelta(days=2),
            source="MANUAL",
            actor=actor,
        )
        service.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="20",
            currency="USD",
            effective_at=now - timedelta(days=1),
            source="MANUAL",
            actor=actor,
        )
        service.create_entry(
            entry_type="ADJUSTMENT",
            direction="DEBIT",
            cloud_account_id=oci.id,
            amount="3",
            currency="BRL",
            effective_at=now,
            source="MANUAL",
            actor=actor,
        )
        db.commit()
        first_id = first.id
        aws_account_id = aws.native_account_id
        period = (now - timedelta(days=3)).isoformat()

    response = http.get(
        "/api/v1/finops/ledger",
        headers=headers(tokens),
        params={
            "provider": "AWS",
            "account_id": aws_account_id,
            "currency": "usd",
            "entry_type": "saving",
            "direction": "credit",
            "source": "manual",
            "effective_from": period,
            "page": 1,
            "page_size": 1,
        },
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 2
    assert page["total_pages"] == 2
    assert len(page["items"]) == 1
    assert page["items"][0]["provider"] == "aws"
    assert page["items"][0]["currency"] == "USD"

    detail = http.get(f"/api/v1/finops/ledger/{first_id}", headers=headers(tokens))
    assert detail.status_code == 200
    assert detail.json()["id"] == first_id


def test_idempotency_key_returns_single_entry(auth_env):
    _, engine, _, _ = auth_env
    with Session(engine) as db:
        aws, _ = _accounts(db)
        service = FinOpsLedgerService(db)
        kwargs = {
            "entry_type": "ADJUSTMENT",
            "direction": "CREDIT",
            "cloud_account_id": aws.id,
            "amount": "7.25",
            "currency": "USD",
            "effective_at": utcnow(),
            "source": "SYSTEM",
            "idempotency_key": "automatic-event-1",
        }
        first = service.create_entry(**kwargs)
        second = service.create_entry(**kwargs)
        db.commit()
        assert first.id == second.id
        assert (
            db.scalar(
                select(func.count())
                .select_from(FinOpsLedgerEntry)
                .where(FinOpsLedgerEntry.idempotency_key == "automatic-event-1")
            )
            == 1
        )


def test_opportunity_source_requires_treatment_event_and_is_event_idempotent(auth_env):
    _, engine, _, ids = auth_env
    with Session(engine) as db:
        aws, _ = _accounts(db)
        actor = _actor(db, ids)
        service = FinOpsLedgerService(db)
        with pytest.raises(FinOpsLedgerError, match="require opportunity_id"):
            service.create_entry(
                entry_type="SAVING",
                direction="CREDIT",
                cloud_account_id=aws.id,
                amount="100",
                currency="USD",
                effective_at=utcnow(),
                source="OPPORTUNITY",
            )

        event = OpportunityStatusHistory(
            opportunity_id="finding",
            from_status="open",
            to_status="treated",
            action="treat",
            changed_by=actor.id,
            changed_at=utcnow(),
        )
        db.add(event)
        db.flush()
        kwargs = {
            "entry_type": "SAVING",
            "direction": "CREDIT",
            "cloud_account_id": aws.id,
            "amount": "100",
            "currency": "USD",
            "effective_at": utcnow(),
            "source": "OPPORTUNITY",
            "opportunity_id": "finding",
            "source_event_id": event.id,
            "idempotency_key": f"opportunity-treated:{event.id}:saving",
        }
        first = service.create_entry(**kwargs)
        second = service.create_entry(**kwargs)
        db.commit()
        assert first.id == second.id
        assert first.source_reference == "finding"
        assert first.source_event_id == event.id


def test_reversal_preserves_original_and_zeroes_balance(auth_env):
    _, engine, _, ids = auth_env
    with Session(engine) as db:
        aws, _ = _accounts(db)
        actor = _actor(db, ids)
        service = FinOpsLedgerService(db)
        original = service.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="100",
            currency="USD",
            effective_at=utcnow(),
            source="MANUAL",
            actor=actor,
        )
        reversal = service.reverse_entry(original.id, actor=actor)
        db.commit()
        assert reversal.direction == "DEBIT"
        assert reversal.amount == original.amount
        assert reversal.currency == original.currency
        assert reversal.reversal_of_id == original.id
        assert db.get(FinOpsLedgerEntry, original.id) is not None
        balances = service.calculate_balances(FinOpsLedgerFilters(currency="USD"))
        assert balances["USD"]["balance"] == Decimal("0")
        with pytest.raises(FinOpsLedgerConflictError, match="already reversed"):
            service.reverse_entry(original.id, actor=actor)


def test_ledger_entries_cannot_be_updated_or_deleted(auth_env):
    _, engine, _, ids = auth_env
    with Session(engine) as db:
        aws, _ = _accounts(db)
        actor = _actor(db, ids)
        entry = FinOpsLedgerService(db).create_entry(
            entry_type="ADJUSTMENT",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="15",
            currency="USD",
            effective_at=utcnow(),
            source="MANUAL",
            actor=actor,
        )
        db.commit()
        entry_id = entry.id

    with Session(engine) as db:
        entry = db.get(FinOpsLedgerEntry, entry_id)
        entry.amount = Decimal("16")
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()

    with Session(engine) as db:
        entry = db.get(FinOpsLedgerEntry, entry_id)
        db.delete(entry)
        with pytest.raises(ValueError, match="append-only"):
            db.commit()
        db.rollback()
        assert db.get(FinOpsLedgerEntry, entry_id) is not None
