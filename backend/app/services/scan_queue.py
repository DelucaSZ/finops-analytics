from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.scan import Scan
from app.services.collection_executors import (
    CollectionPreconditionError,
    get_collection_executor,
)
from app.services.provider_capabilities import ProviderOperation, require_provider_operation


def queue_manual_collection(
    db: Session,
    account: CloudAccount,
    *,
    trigger: str = "manual",
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
        raise CollectionPreconditionError("A scan is already pending or running")

    scan = Scan(
        account_id=preparation.legacy_scan_account_id,
        cloud_account_id=account.id,
        trigger=trigger,
    )
    db.add(scan)
    db.flush()
    return scan
