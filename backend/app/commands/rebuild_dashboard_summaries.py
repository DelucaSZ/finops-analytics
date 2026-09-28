from __future__ import annotations

import argparse

import app.models  # noqa: F401
from app.db.session import SessionLocal
from app.models.collection_run import CollectionRun
from app.services.dashboard_aggregation import (
    backfill_dashboard_summaries,
    rebuild_account_summary,
    summary_matches_source,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild derived dashboard summaries from operational data."
    )
    parser.add_argument("--provider")
    parser.add_argument("--account-id")
    parser.add_argument("--collection-run-id")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.account_id and not args.provider:
        parser.error("--account-id requires --provider")

    with SessionLocal() as db:
        if args.collection_run_id:
            target = db.get(CollectionRun, args.collection_run_id)
            if target is None:
                parser.error("CollectionRun not found")
            if args.provider and target.provider != args.provider.lower():
                parser.error("CollectionRun provider does not match --provider")
            if args.account_id and target.account_id != args.account_id:
                parser.error("CollectionRun account does not match --account-id")
            summary = rebuild_account_summary(
                db,
                provider=target.provider,
                account_id=target.account_id,
                collection_run_id=target.id,
            )
            rebuilt = 1 if summary is not None else 0
            scopes = [(target.provider, target.account_id)]
        else:
            rebuilt = backfill_dashboard_summaries(
                db,
                provider=args.provider,
                account_id=args.account_id,
                commit_every=50,
            )
            scopes = (
                [(args.provider.lower(), args.account_id)]
                if args.provider and args.account_id
                else []
            )
        db.commit()

        verified = None
        if args.verify and scopes:
            verified = all(
                summary_matches_source(db, provider=provider, account_id=account_id)
                for provider, account_id in scopes
            )

    message = f"rebuilt={rebuilt}"
    if verified is not None:
        message += f" verified={str(verified).lower()}"
    print(message)


if __name__ == "__main__":
    main()
