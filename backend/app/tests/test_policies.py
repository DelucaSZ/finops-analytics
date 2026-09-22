from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.account import AwsAccount
from app.services.policies import deep_merge, get_effective_policy, upsert_policy


def test_deep_merge_preserves_unmodified_nested_values() -> None:
    base = {"days": 7, "prices": {"gp2": 0.1, "gp3": 0.08}}
    override = {"prices": {"gp3": 0.07}}

    assert deep_merge(base, override) == {
        "days": 7,
        "prices": {"gp2": 0.1, "gp3": 0.07},
    }
    assert base["prices"]["gp3"] == 0.08


def test_account_policy_overrides_only_selected_fields() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        account = AwsAccount(
            name="Production",
            aws_account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/NuvemIQReadOnly",
            external_id="nuvemiq-1234567890",
            regions=["sa-east-1"],
        )
        db.add(account)
        db.commit()
        db.refresh(account)

        upsert_policy(
            db,
            rule_key="ebs_unattached",
            scope="global",
            account_id=None,
            enabled=True,
            config={"minimum_age_days": 10, "minimum_monthly_savings_usd": 5},
        )
        upsert_policy(
            db,
            rule_key="ebs_unattached",
            scope="account",
            account_id=account.id,
            enabled=None,
            config={"minimum_age_days": 30},
        )

        policy = get_effective_policy(db, "ebs_unattached", account.id)
        assert policy["enabled"] is True
        assert policy["config"]["minimum_age_days"] == 30
        assert policy["config"]["minimum_monthly_savings_usd"] == 5
        assert policy["override_fields"] == ["minimum_age_days"]
