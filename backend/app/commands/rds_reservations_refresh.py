from __future__ import annotations

import argparse
import json

from app.db.session import SessionLocal
from app.services.rds_reservations_pipeline import (
    RdsReservationsPipelineBusy,
    refresh_rds_reservations,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect RDS inventory and refresh reservation coverage/opportunities"
    )
    parser.add_argument("--cloud-account-id", type=int, default=None)
    parser.add_argument(
        "--validate-billing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable AWS Cost Explorer reservation coverage reconciliation",
    )
    args = parser.parse_args()

    try:
        with SessionLocal() as db:
            result = refresh_rds_reservations(
                db,
                cloud_account_id=args.cloud_account_id,
                validate_billing=args.validate_billing,
            )
    except RdsReservationsPipelineBusy as exc:
        print(json.dumps({"status": "BUSY", "message": str(exc)}, indent=2))
        raise SystemExit(2) from exc

    print(json.dumps(result, indent=2, default=str))
    if result["status"] == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
