from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

import app.models  # noqa: F401
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.retention import (
    cleanup_observations,
    retention_cutoff,
    retention_preview,
)


def _parse_before(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use an ISO-8601 datetime for --before") from exc
    parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    if parsed > datetime.now(UTC):
        raise argparse.ArgumentTypeError("--before cannot be in the future")
    return parsed


def _json(value) -> str:
    return json.dumps(value, default=lambda item: item.isoformat(), sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview or delete eligible historical opportunity observations."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default).")
    mode.add_argument("--execute", action="store_true", help="Apply deletion in committed batches.")
    parser.add_argument(
        "--before",
        type=_parse_before,
        help="Override the configured cutoff with an explicit UTC/offset ISO-8601 datetime.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=settings.retention_batch_size,
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=settings.retention_max_rows_per_run,
        help="Safety cap for this execution; 0 means unlimited.",
    )
    parser.add_argument("--provider")
    parser.add_argument("--account-id")
    args = parser.parse_args()

    if args.account_id and not args.provider:
        parser.error("--account-id requires --provider")
    if args.batch_size <= 0:
        parser.error("--batch-size must be greater than zero")
    if args.max_rows < 0:
        parser.error("--max-rows must be zero or greater")
    if args.execute and not settings.retention_enabled:
        parser.error("Retention cleanup is disabled by NUVEMIQ_RETENTION_ENABLED")

    cutoff = args.before or retention_cutoff(
        days=settings.opportunity_observation_retention_days
    )
    with SessionLocal() as db:
        preview = retention_preview(
            db,
            cutoff=cutoff,
            provider=args.provider,
            account_id=args.account_id,
        )
        print(_json({"mode": "dry-run", **preview.as_dict()}))
        if not args.execute:
            return

        result = cleanup_observations(
            db,
            cutoff=cutoff,
            batch_size=args.batch_size,
            max_rows=args.max_rows,
            provider=args.provider,
            account_id=args.account_id,
        )
        print(_json({"mode": "execute", **result.as_dict()}))


if __name__ == "__main__":
    main()
