from __future__ import annotations

import json

import app.models  # noqa: F401
from app.db.session import SessionLocal
from app.services.opportunity_policy import OpportunityManagementPolicyService
from app.services.opportunity_retention import OpportunityRetentionService


def main() -> None:
    with SessionLocal() as db:
        policy = OpportunityManagementPolicyService.get_or_create(db)
        if not policy.enabled:
            print(json.dumps({"enabled": False, "policy_version": policy.version}))
            return
        result = OpportunityRetentionService.from_management_policy(policy).run(db)
        print(json.dumps(result.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
