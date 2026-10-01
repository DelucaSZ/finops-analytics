from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import CloudAccount
from app.models.scan import Scan
from app.services.cloud_accounts import require_aws_configuration
from app.services.provider_capabilities import ProviderOperation, require_provider_operation


class CollectionPreconditionError(ValueError):
    """Raised when collection is implemented but the account cannot run it now."""


def queue_manual_collection(
    db: Session,
    account: CloudAccount,
    *,
    trigger: str = "manual",
) -> Scan:
    require_provider_operation(account.provider, ProviderOperation.MANUAL_COLLECTION)
    if not account.enabled:
        raise CollectionPreconditionError("Cloud account is disabled")

    aws_account = require_aws_configuration(account)
    pending = db.scalar(
        select(Scan).where(
            Scan.account_id == aws_account.id,
            Scan.status.in_(["pending", "running"]),
        )
    )
    if pending is not None:
        raise CollectionPreconditionError("A scan is already pending or running")

    scan = Scan(
        account_id=aws_account.id,
        cloud_account_id=account.id,
        trigger=trigger,
    )
    db.add(scan)
    db.flush()
    return scan
