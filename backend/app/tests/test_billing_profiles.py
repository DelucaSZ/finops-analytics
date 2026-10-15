from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.billing_profile import BillingProfile
from app.models.user import User  # noqa: F401 - registers FK target in metadata
from app.schemas.billing import (
    AwsBillingApiRequest,
    BillingGranularity,
    BillingGroupBy,
    BillingMetric,
    BillingProfileCreate,
    BillingProfileUpdate,
)
from app.services.billing_profiles import (
    FINOPS_SYSTEM_PROFILE_ID,
    BillingProfileError,
    BillingProfileService,
    ensure_finops_profile,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _api_request(**overrides):
    values = {
        "account_ids": [1],
        "start_date": date(2026, 10, 1),
        "end_date": date(2026, 10, 15),
    }
    values.update(overrides)
    return AwsBillingApiRequest(**values)


def test_finops_seed_is_idempotent_and_has_operational_defaults(db):
    first = ensure_finops_profile(db)
    second = ensure_finops_profile(db)

    assert first.id == second.id == FINOPS_SYSTEM_PROFILE_ID
    assert db.scalar(select(func.count()).select_from(BillingProfile)) == 1
    assert first.name == "FinOps"
    assert first.granularity == BillingGranularity.DAILY.value
    assert first.metric == BillingMetric.AMORTIZED_COST.value
    assert first.exclude_record_types == ["Credit"]
    assert first.is_default is True
    assert first.is_system is True


def test_bootstrap_does_not_overwrite_existing_finops_customization(db):
    profile = ensure_finops_profile(db)
    profile.metric = BillingMetric.UNBLENDED_COST.value
    profile.description = "Customizado operacionalmente"
    db.commit()

    bootstrapped = ensure_finops_profile(db)

    assert bootstrapped.metric == BillingMetric.UNBLENDED_COST.value
    assert bootstrapped.description == "Customizado operacionalmente"


def test_create_edit_and_case_insensitive_duplicate_name_rejected(db):
    ensure_finops_profile(db)
    service = BillingProfileService(db)
    created = service.create(
        BillingProfileCreate(
            name="Mensal amortizado",
            granularity=BillingGranularity.MONTHLY,
            metric=BillingMetric.AMORTIZED_COST,
            group_by=BillingGroupBy.SERVICE,
            exclude_record_types=["Credit", "Refund"],
        ),
        actor_user_id="actor-1",
    )

    updated = service.update(
        created.id,
        BillingProfileUpdate(description="Visão mensal", metric=BillingMetric.UNBLENDED_COST),
    )
    assert updated.description == "Visão mensal"
    assert updated.metric == BillingMetric.UNBLENDED_COST.value
    assert updated.created_by == "actor-1"

    with pytest.raises(BillingProfileError) as error:
        service.create(
            BillingProfileCreate(name="mensal amortizado"),
            actor_user_id="actor-2",
        )
    assert error.value.code == "PROFILE_NAME_CONFLICT"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"metric": "INVALID"}, "metric"),
        ({"granularity": "HOURLY"}, "granularity"),
        ({"group_by": "REGION"}, "group_by"),
        ({"exclude_record_types": ["MadeUpType"]}, "exclude_record_types"),
    ],
)
def test_profile_domain_values_are_validated(payload, field):
    with pytest.raises(ValidationError) as error:
        BillingProfileCreate(name="Inválido", **payload)
    assert field in str(error.value)


def test_switching_default_is_atomic_from_service_perspective(db):
    finops = ensure_finops_profile(db)
    service = BillingProfileService(db)
    custom = service.create(
        BillingProfileCreate(name="Mensal", granularity=BillingGranularity.MONTHLY),
        actor_user_id="actor-1",
    )

    selected = service.set_default(custom.id)
    db.refresh(finops)

    assert selected.is_default is True
    assert finops.is_default is False
    defaults = list(db.scalars(select(BillingProfile).where(BillingProfile.is_default.is_(True))))
    assert [item.id for item in defaults] == [custom.id]


def test_database_rejects_two_defaults(db):
    ensure_finops_profile(db)
    db.add(
        BillingProfile(
            name="Outro",
            granularity="DAILY",
            metric="AMORTIZED_COST",
            group_by="NONE",
            exclude_record_types=["Credit"],
            is_default=True,
            enabled=True,
            is_system=False,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_default_cannot_be_deactivated_and_system_fallback_is_protected(db):
    finops = ensure_finops_profile(db)
    service = BillingProfileService(db)

    with pytest.raises(BillingProfileError) as error:
        service.deactivate(finops.id)
    assert error.value.code == "DEFAULT_PROFILE_REQUIRED"

    custom = service.create(
        BillingProfileCreate(name="Custom", is_default=True),
        actor_user_id="actor-1",
    )
    db.refresh(finops)
    assert custom.is_default is True
    with pytest.raises(BillingProfileError) as error:
        service.deactivate(finops.id)
    assert error.value.code == "SYSTEM_PROFILE_PROTECTED"


def test_profile_resolves_to_canonical_billing_request(db):
    finops = ensure_finops_profile(db)
    resolved = BillingProfileService(db).resolve(_api_request(profile_id=finops.id))

    assert resolved.profile_id == finops.id
    assert resolved.request.granularity == BillingGranularity.DAILY
    assert resolved.request.metric == BillingMetric.AMORTIZED_COST
    assert resolved.request.group_by == BillingGroupBy.NONE
    assert resolved.request.exclude_record_types == ["Credit"]


def test_default_profile_applies_without_explicit_profile_id(db):
    ensure_finops_profile(db)
    service = BillingProfileService(db)
    custom = service.create(
        BillingProfileCreate(
            name="Mensal",
            granularity=BillingGranularity.MONTHLY,
            metric=BillingMetric.UNBLENDED_COST,
            group_by=BillingGroupBy.SERVICE,
            exclude_record_types=["Refund"],
            is_default=True,
        ),
        actor_user_id="actor-1",
    )

    resolved = service.resolve(_api_request())

    assert resolved.profile_id == custom.id
    assert resolved.request.granularity == BillingGranularity.MONTHLY
    assert resolved.request.metric == BillingMetric.UNBLENDED_COST
    assert resolved.request.exclude_record_types == ["Refund"]


def test_explicit_overrides_win_without_mutating_profile(db):
    finops = ensure_finops_profile(db)
    service = BillingProfileService(db)

    resolved = service.resolve(
        _api_request(
            profile_id=finops.id,
            granularity=BillingGranularity.MONTHLY,
            group_by=BillingGroupBy.ACCOUNT,
            exclude_record_types=[],
        )
    )

    assert resolved.request.granularity == BillingGranularity.MONTHLY
    assert resolved.request.metric == BillingMetric.AMORTIZED_COST
    assert resolved.request.group_by == BillingGroupBy.ACCOUNT
    assert resolved.request.exclude_record_types == []
    db.refresh(finops)
    assert finops.granularity == BillingGranularity.DAILY.value
    assert finops.exclude_record_types == ["Credit"]


def test_dates_and_accounts_are_query_scope_not_profile_state(db):
    finops = ensure_finops_profile(db)
    service = BillingProfileService(db)

    october = service.resolve(
        _api_request(profile_id=finops.id, account_ids=[1], end_date=date(2026, 10, 15))
    )
    november = service.resolve(
        _api_request(
            profile_id=finops.id,
            account_ids=[2, 3],
            start_date=date(2026, 11, 1),
            end_date=date(2026, 12, 1),
        )
    )

    assert october.profile_id == november.profile_id == finops.id
    assert october.request.account_ids == [1]
    assert november.request.account_ids == [2, 3]
    assert october.request.start_date != november.request.start_date
    db.refresh(finops)
    assert not hasattr(finops, "account_ids")
    assert not hasattr(finops, "start_date")


def test_inactive_profile_cannot_be_selected_for_query(db):
    ensure_finops_profile(db)
    service = BillingProfileService(db)
    custom = service.create(BillingProfileCreate(name="Temporário"), actor_user_id="actor-1")
    service.deactivate(custom.id)

    with pytest.raises(BillingProfileError) as error:
        service.resolve(_api_request(profile_id=custom.id))
    assert error.value.code == "PROFILE_INACTIVE"


def test_finops_is_fallback_when_no_profile_is_marked_default(db):
    finops = ensure_finops_profile(db)
    finops.is_default = False
    db.commit()

    resolved = BillingProfileService(db).resolve(_api_request())

    assert resolved.profile_id == finops.id
    assert resolved.request.metric == BillingMetric.AMORTIZED_COST
