import argparse
import json

from app.db.session import SessionLocal
from app.services.rds_inventory import collect_rds_inventory


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Amazon RDS inventory and reservations.")
    parser.add_argument(
        "--cloud-account-id",
        type=int,
        default=None,
        help="Collect only one Aven cloud account id. Default: all enabled AWS accounts.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        result = collect_rds_inventory(db, cloud_account_id=args.cloud_account_id)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
