from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.account import CloudAccount
from app.models.user import User
from app.services.finops_ledger import FinOpsLedgerService
from app.tests.test_security import auth_env as auth_env
from app.tests.test_security import headers


def _accounts(db: Session) -> tuple[CloudAccount, CloudAccount]:
    aws = db.scalar(select(CloudAccount).where(CloudAccount.provider == "aws"))
    assert aws is not None
    oci = db.scalar(select(CloudAccount).where(CloudAccount.provider == "oci"))
    if oci is None:
        oci = CloudAccount(
            provider="oci",
            native_account_id="ocid1.tenancy.oc1..flowfixture",
            name="OCI Flow fixture",
        )
        db.add(oci)
        db.flush()
    return aws, oci


def _actor(db: Session, ids: dict) -> User:
    actor = db.get(User, ids["admin"])
    assert actor is not None
    return actor


def test_flow_summary_separates_currency_and_periodicity(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        aws, oci = _accounts(db)
        actor = _actor(db, ids)
        ledger = FinOpsLedgerService(db)
        now = utcnow() - timedelta(days=1)
        common = {"effective_at": now, "source": "MANUAL", "actor": actor}
        ledger.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="1000",
            currency="USD",
            periodicity="MONTHLY",
            **common,
        )
        ledger.create_entry(
            entry_type="REALLOCATION",
            direction="DEBIT",
            cloud_account_id=aws.id,
            amount="300",
            currency="USD",
            periodicity="MONTHLY",
            **common,
        )
        ledger.create_entry(
            entry_type="ADJUSTMENT",
            direction="DEBIT",
            cloud_account_id=aws.id,
            amount="100",
            currency="USD",
            periodicity="MONTHLY",
            **common,
        )
        ledger.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="500",
            currency="USD",
            periodicity="ONE_TIME",
            **common,
        )
        ledger.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=oci.id,
            amount="2000",
            currency="BRL",
            periodicity="MONTHLY",
            **common,
        )
        db.commit()

    response = http.get("/api/v1/finops/flow/summary", headers=headers(tokens))
    assert response.status_code == 200, response.text
    data = {(item["currency"], item["basis"]): item for item in response.json()}
    assert set(data) == {
        ("USD", "MONTHLY"),
        ("USD", "ONE_TIME"),
        ("BRL", "MONTHLY"),
    }
    monthly_usd = data[("USD", "MONTHLY")]
    assert Decimal(monthly_usd["recognized_savings"]) == Decimal("1000")
    assert Decimal(monthly_usd["reallocated"]) == Decimal("300")
    assert Decimal(monthly_usd["adjustment_net"]) == Decimal("-100")
    assert Decimal(monthly_usd["balance"]) == Decimal("600")
    assert Decimal(data[("USD", "ONE_TIME")]["balance"]) == Decimal("500")
    assert Decimal(data[("BRL", "MONTHLY")]["balance"]) == Decimal("2000")


def test_reversal_nets_original_metric_and_inherits_source_for_analytics(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        aws, _ = _accounts(db)
        actor = _actor(db, ids)
        ledger = FinOpsLedgerService(db)
        original = ledger.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="1000",
            currency="USD",
            effective_at=utcnow() - timedelta(days=2),
            source="MANUAL",
            actor=actor,
            periodicity="MONTHLY",
            description="Saving to reverse",
        )
        ledger.reverse_entry(
            original.id,
            actor=actor,
            effective_at=utcnow() - timedelta(days=1),
            description="Correction",
        )
        db.commit()

    response = http.get(
        "/api/v1/finops/flow/summary?currency=USD&periodicity=MONTHLY&source=MANUAL",
        headers=headers(tokens),
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    item = response.json()[0]
    assert Decimal(item["recognized_savings"]) == Decimal("0")
    assert Decimal(item["adjustment_net"]) == Decimal("0")
    assert Decimal(item["balance"]) == Decimal("0")

    entries = http.get(
        "/api/v1/finops/flow/entries?currency=USD&periodicity=MONTHLY&source=MANUAL",
        headers=headers(tokens),
    )
    assert entries.status_code == 200, entries.text
    payload = entries.json()
    assert payload["total"] == 2
    assert any(item["is_reversal"] for item in payload["items"])
    assert all(item["logical_source"] == "MANUAL" for item in payload["items"])
    reversal = next(item for item in payload["items"] if item["is_reversal"])
    assert reversal["logical_entry_type"] == "SAVING"
    assert reversal["source"] == "SYSTEM"


def test_flow_filters_breakdowns_and_timeseries_use_effective_date(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        aws, oci = _accounts(db)
        actor = _actor(db, ids)
        ledger = FinOpsLedgerService(db)
        now = utcnow()
        ledger.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="120",
            currency="USD",
            effective_at=now - timedelta(days=10),
            source="MANUAL",
            actor=actor,
            periodicity="ONE_TIME",
        )
        ledger.create_entry(
            entry_type="REALLOCATION",
            direction="DEBIT",
            cloud_account_id=aws.id,
            amount="20",
            currency="USD",
            effective_at=now - timedelta(days=5),
            source="MANUAL",
            actor=actor,
            periodicity="ONE_TIME",
        )
        ledger.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=oci.id,
            amount="900",
            currency="BRL",
            effective_at=now - timedelta(days=5),
            source="MANUAL",
            actor=actor,
            periodicity="ONE_TIME",
        )
        db.commit()
        aws_native = aws.native_account_id

    params = {
        "currency": "USD",
        "periodicity": "ONE_TIME",
        "effective_from": (now - timedelta(days=15)).isoformat(),
        "effective_to": (now + timedelta(days=1)).isoformat(),
    }
    series = http.get(
        "/api/v1/finops/flow/timeseries",
        params=params,
        headers=headers(tokens),
    )
    assert series.status_code == 200, series.text
    data = series.json()
    assert data["granularity"] == "day"
    assert len(data["items"]) == 2
    assert Decimal(data["items"][-1]["cumulative_balance"]) == Decimal("100")
    assert all(item["currency"] == "USD" for item in data["items"])

    breakdowns = http.get(
        "/api/v1/finops/flow/breakdowns",
        params=params,
        headers=headers(tokens),
    )
    assert breakdowns.status_code == 200, breakdowns.text
    by_account = breakdowns.json()["by_account"]
    assert len(by_account) == 1
    assert by_account[0]["account_id"] == aws_native
    assert Decimal(by_account[0]["recognized_savings"]) == Decimal("120")
    by_source = breakdowns.json()["by_source"]
    assert len(by_source) == 1
    assert by_source[0]["source"] == "MANUAL"


def test_flow_entries_are_paginated_and_periodicity_filter_is_server_side(auth_env):
    http, engine, tokens, ids = auth_env
    with Session(engine) as db:
        aws, _ = _accounts(db)
        actor = _actor(db, ids)
        ledger = FinOpsLedgerService(db)
        now = utcnow() - timedelta(days=1)
        for index in range(3):
            ledger.create_entry(
                entry_type="SAVING",
                direction="CREDIT",
                cloud_account_id=aws.id,
                amount=str(10 + index),
                currency="USD",
                effective_at=now + timedelta(minutes=index),
                source="MANUAL",
                actor=actor,
                periodicity="MONTHLY",
                description=f"monthly flow {index}",
            )
        ledger.create_entry(
            entry_type="SAVING",
            direction="CREDIT",
            cloud_account_id=aws.id,
            amount="99",
            currency="USD",
            effective_at=now,
            source="MANUAL",
            actor=actor,
            periodicity="ONE_TIME",
            description="one time flow",
        )
        db.commit()

    first = http.get(
        "/api/v1/finops/flow/entries?periodicity=MONTHLY&page=1&page_size=2&search=monthly",
        headers=headers(tokens),
    )
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload["total"] == 3
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 2
    assert all(item["periodicity"] == "MONTHLY" for item in payload["items"])
