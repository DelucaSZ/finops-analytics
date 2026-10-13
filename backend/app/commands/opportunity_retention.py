from __future__ import annotations

import argparse
import json

import app.models  # noqa: F401
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.opportunity_retention import OpportunityRetentionService


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archive opportunities eligible under the configured retention policy."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required safety flag; without it no archive operation is executed.",
    )
    args = parser.parse_args()

    if not args.execute:
        parser.error("Use --execute to apply opportunity retention")
    if not settings.opportunity_retention_enabled:
        parser.error("Opportunity retention is disabled by OPPORTUNITY_RETENTION_ENABLED")

    with SessionLocal() as db:
        result = OpportunityRetentionService.from_settings().run(db)
    print(json.dumps(result.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
