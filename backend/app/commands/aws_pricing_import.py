"""Operator-only AWS Pricing Bulk importer (no HTTP route or schedule).

Examples:
  python -m app.commands.aws_pricing_import --service AmazonEC2 --region sa-east-1 --dry-run
  AVEN_AWS_PRICING_IMPORT_ENABLED=1 python -m app.commands.aws_pricing_import \
      --service AmazonRDS --region us-east-1 --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from app.db.session import SessionLocal
from app.services.aws_pricing_import import import_aws_prices


def _date(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timezone required")
        return dt.astimezone(UTC)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be timezone-aware ISO-8601") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, help="Official AWS ServiceCode")
    parser.add_argument("--region", required=True, help="Commercial product region, e.g. sa-east-1")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--effective-at", type=_date, help="Official reference date, ISO-8601")
    parser.add_argument("--pricing-endpoint", default="us-east-1")
    parser.add_argument("--max-bytes", type=int, default=2_000_000_000)
    parser.add_argument("--max-products", type=int, default=1_000_000)
    parser.add_argument("--max-rates", type=int, default=1_000_000)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--fixture", type=Path, help="Offline official-format test fixture")
    parser.add_argument("--allow-fixture-apply", action="store_true")
    parser.add_argument(
        "--offline-dry-run", action="store_true",
        help="Skip DB conflict lookup (dry-run only, report this limitation)",
    )
    args = parser.parse_args(argv)
    if args.apply and os.environ.get("AVEN_AWS_PRICING_IMPORT_ENABLED") != "1":
        parser.error(
            "apply requires AVEN_AWS_PRICING_IMPORT_ENABLED=1 in administrative environment"
        )
    if args.apply and args.fixture and (
        not args.allow_fixture_apply
        or os.environ.get("AVEN_ALLOW_OFFLINE_PRICE_FIXTURES") != "1"
    ):
        parser.error(
            "test fixture publication requires explicit fixture flags and environment opt-in"
        )
    if args.offline_dry_run and not args.dry_run:
        parser.error("--offline-dry-run requires --dry-run")
    if args.allow_partial and not args.apply:
        parser.error("--allow-partial requires --apply")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    session = None if args.offline_dry_run else SessionLocal()
    try:
        result = import_aws_prices(
            service_code=args.service,
            region_code=args.region,
            db=session,
            dry_run=args.dry_run,
            allow_partial=args.allow_partial,
            effective_at=args.effective_at,
            fixture_path=args.fixture,
            max_bytes=args.max_bytes,
            max_products=args.max_products,
            max_rates=args.max_rates,
            endpoint_region=args.pricing_endpoint,
        )
        print(json.dumps(asdict(result), default=str, sort_keys=True, indent=2))
        return 0 if result.status in {"validated", "published", "already_published"} else 2
    except Exception as exc:
        logging.getLogger(__name__).error(
            "aws_pricing_import_failed service=%s region=%s type=%s error=%s",
            args.service, args.region, type(exc).__name__, str(exc)[:300],
        )
        return 3
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    sys.exit(main())
