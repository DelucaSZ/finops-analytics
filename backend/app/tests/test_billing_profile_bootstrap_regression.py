from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.billing_profile import BillingProfile
from app.models.user import User  # noqa: F401 - registers FK target in metadata
from app.schemas.billing import BillingMetric
from app.services.billing_profiles import FINOPS_SYSTEM_PROFILE_ID, ensure_finops_profile


def test_bootstrap_uses_stable_system_id_after_profile_rename():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            profile = ensure_finops_profile(db)
            profile.name = "FinOps personalizado"
            profile.metric = BillingMetric.UNBLENDED_COST.value
            db.commit()

            bootstrapped = ensure_finops_profile(db)

            assert bootstrapped.id == FINOPS_SYSTEM_PROFILE_ID
            assert bootstrapped.name == "FinOps personalizado"
            assert bootstrapped.metric == BillingMetric.UNBLENDED_COST.value
            assert db.scalar(select(func.count()).select_from(BillingProfile)) == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
