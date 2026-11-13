"""Administrative AWS Pricing synchronization, status and coverage inspection.

Examples:
  python -m app.commands.aws_pricing_sync --status
  python -m app.commands.aws_pricing_sync --coverage --service AmazonRDS --region sa-east-1
  python -m app.commands.aws_pricing_sync --service AmazonEC2 --region sa-east-1 --dry-run
  AVEN_AWS_PRICING_IMPORT_ENABLED=1 python -m app.commands.aws_pricing_sync \\
      --service AmazonEC2 --region sa-east-1 --apply
  AVEN_AWS_PRICING_IMPORT_ENABLED=1 python -m app.commands.aws_pricing_sync --all --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from app.db.session import SessionLocal
from app.services.aws_pricing_sync import AwsPricingSynchronizer, coverage_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="Read-only operational status")
    mode.add_argument("--coverage", action="store_true", help="Read-only live catalog coverage")
    mode.add_argument("--dry-run", action="store_true", help="Inspect without writing prices")
    mode.add_argument("--apply", action="store_true", help="Publish checked official sources")
    parser.add_argument("--service", help="Official AWS ServiceCode")
    parser.add_argument("--region", help="Commercial AWS region")
    parser.add_argument(
        "--all", action="store_true", help="Process eligible regions (bounded cycle)"
    )
    parser.add_argument("--retry-failed", action="store_true", help="Only retry last failed units")
    parser.add_argument("--force", action="store_true", help="Revalidate even if ARN is unchanged")
    parser.add_argument("--fixture", type=Path, help="Read-only official-format test fixture")
    parser.add_argument("--limit", type=int, default=100, help="Status pagination limit (max 500)")
    args = parser.parse_args(argv)
    if args.fixture and not args.dry_run:
        parser.error("fixture is supported for dry-run only")
    if args.fixture and (not args.service or not args.region):
        parser.error("fixture requires --service and --region")
    if args.coverage and (not args.service or not args.region):
        parser.error("coverage requires --service and --region")
    if args.force and not args.apply:
        parser.error("--force requires --apply")
    if args.force and args.all:
        parser.error("--force applies only to a single service/region")
    if args.retry_failed and not args.apply:
        parser.error("--retry-failed requires --apply")
    if (args.apply or args.dry_run) and not args.all and (not args.service or not args.region):
        parser.error("a single run requires --service and --region; use --all for a bounded cycle")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sync = AwsPricingSynchronizer()
    try:
        if args.status:
            output = sync.status(service=args.service, region=args.region, limit=args.limit)
        elif args.coverage:
            with SessionLocal() as db:
                output = coverage_report(db, args.service, args.region)
        elif args.all:
            output = sync.run_cycle(
                service=args.service,
                region=args.region,
                due_only=False,
                dry_run=args.dry_run,
                retry_failed=args.retry_failed,
            )
        else:
            output = sync.run_unit(
                args.service,
                args.region,
                dry_run=args.dry_run,
                fixture_path=args.fixture,
                force=args.force,
            )
        print(json.dumps(output, default=str, sort_keys=True, indent=2))
        if isinstance(output, list):
            failed = any(item.get("status") in {"failed", "partial", "busy"} for item in output)
        else:
            failed = isinstance(output, dict) and output.get("status") in {
                "failed",
                "partial",
                "busy",
            }
        return 2 if failed else 0
    except (ValueError, PermissionError, RuntimeError) as exc:
        logging.getLogger(__name__).error(
            "aws_pricing_sync_command_failed error_code=%s", type(exc).__name__
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
