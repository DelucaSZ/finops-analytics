import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.scan import Scan
from app.services.cloud_accounts import add_account_audit
from app.services.collection_executors import (
    CollectionPreconditionError,
    get_collection_executor,
)
from app.services.provider_capabilities import ProviderOperation, require_provider_operation

logger = logging.getLogger("deepops.collection_queue")


def queue_manual_collection(
    db: Session,
    account: CloudAccount,
    *,
    trigger: str = "manual",
    actor_id: str | None = None,
) -> Scan:
    require_provider_operation(account.provider, ProviderOperation.MANUAL_COLLECTION)
    if not account.enabled:
        raise CollectionPreconditionError("Cloud account is disabled")

    executor = get_collection_executor(account.provider)
    preparation = executor.prepare(db, account)
    pending = db.scalar(
        select(Scan).where(
            Scan.cloud_account_id == account.id,
            Scan.status.in_(["pending", "running"]),
        )
    )
    if pending is not None:
        logger.info(
            "event=collection_enqueue_skipped provider=%s cloud_account_id=%s "
            "native_account_id=%s scan_id=%s trigger=%s reason=active_scan",
            account.provider,
            account.id,
            account.native_account_id,
            pending.id,
            trigger,
        )
        raise CollectionPreconditionError("A scan is already pending or running")

    scan = Scan(
        account_id=preparation.legacy_scan_account_id,
        cloud_account_id=account.id,
        trigger=trigger,
    )
    db.add(scan)
    db.flush()

    logger.info(
        "event=collection_enqueued provider=%s cloud_account_id=%s native_account_id=%s "
        "scan_id=%s trigger=%s",
        account.provider,
        account.id,
        account.native_account_id,
        scan.id,
        trigger,
    )
    if trigger == "manual":
        add_account_audit(
            db,
            account=account,
            actor_id=actor_id,
            action="collection.manual.requested",
            result="success",
            detail=f"scan_id={scan.id}",
        )
    return scan
