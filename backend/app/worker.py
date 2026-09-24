import hashlib
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import settings
from app.db.migrations import wait_for_database
from app.db.session import SessionLocal, engine
from app.models.account import AwsAccount
from app.models.collection_run import CollectionRun, CollectionRunStatus
from app.models.finding import Finding
from app.models.scan import Scan
from app.services.aws_auth import assume_account_session, get_caller_identity
from app.services.collectors import run_collectors
from app.services.policies import list_effective_policies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("nuvemiq.worker")


def _fingerprint(
    account_id: int, rule_key: str, service: str, region: str, resource_id: str
) -> str:
    raw = f"{account_id}|{rule_key}|{service}|{region}|{resource_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def enqueue_due_scans(db: Session) -> None:
    now = datetime.now(UTC)
    due_accounts = list(
        db.scalars(
            select(AwsAccount).where(
                AwsAccount.enabled.is_(True),
                AwsAccount.schedule_enabled.is_(True),
                AwsAccount.next_scan_at.is_not(None),
                AwsAccount.next_scan_at <= now,
            )
        )
    )
    for account in due_accounts:
        active = db.scalar(
            select(Scan).where(
                Scan.account_id == account.id, Scan.status.in_(["pending", "running"])
            )
        )
        if active is None:
            db.add(Scan(account_id=account.id, trigger="scheduled"))
        account.next_scan_at = now + timedelta(hours=account.scan_interval_hours)
    db.commit()


def claim_scan(db: Session) -> Scan | None:
    statement = (
        select(Scan)
        .where(Scan.status == "pending")
        .order_by(Scan.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    with db.begin():
        scan = db.scalar(statement)
        if scan:
            started_at = datetime.now(UTC)
            scan.status = "running"
            scan.started_at = started_at
            account = db.get(AwsAccount, scan.account_id)
            account_id = account.aws_account_id if account else f"legacy:{scan.account_id}"
            db.add(
                CollectionRun(
                    scan_id=scan.id,
                    provider="aws",
                    account_id=account_id,
                    started_at=started_at,
                    status=CollectionRunStatus.RUNNING,
                )
            )
    return scan


def collection_run_for_scan(db: Session, scan_id: str) -> CollectionRun | None:
    return db.scalar(select(CollectionRun).where(CollectionRun.scan_id == scan_id))


def persist_findings(db: Session, scan: Scan, collected: list, active_rule_keys: list[str]) -> int:
    now = datetime.now(UTC)
    seen: set[str] = set()
    for item in collected:
        fingerprint = _fingerprint(
            scan.account_id, item.rule_key, item.service, item.region, item.resource_id
        )
        seen.add(fingerprint)
        finding = db.scalar(select(Finding).where(Finding.fingerprint == fingerprint))
        if finding is None:
            finding = Finding(
                fingerprint=fingerprint,
                scan_id=scan.id,
                account_id=scan.account_id,
                rule_key=item.rule_key,
                service=item.service,
                region=item.region,
                resource_id=item.resource_id,
                resource_name=item.resource_name,
                title=item.title,
                description=item.description,
                evidence=item.evidence,
                current_monthly_cost=item.current_monthly_cost,
                estimated_monthly_savings=item.estimated_monthly_savings,
                confidence=item.confidence,
                severity=item.severity,
                status="open",
                first_seen_at=now,
                last_seen_at=now,
            )
            db.add(finding)
        else:
            finding.scan_id = scan.id
            finding.resource_name = item.resource_name
            finding.title = item.title
            finding.description = item.description
            finding.evidence = item.evidence
            finding.current_monthly_cost = item.current_monthly_cost
            finding.estimated_monthly_savings = item.estimated_monthly_savings
            finding.confidence = item.confidence
            finding.severity = item.severity
            finding.last_seen_at = now
            if finding.status == "resolved":
                finding.status = "open"

    if active_rule_keys:
        open_findings = list(
            db.scalars(
                select(Finding).where(
                    Finding.account_id == scan.account_id,
                    Finding.rule_key.in_(active_rule_keys),
                    Finding.status == "open",
                )
            )
        )
        for finding in open_findings:
            if finding.fingerprint not in seen:
                finding.status = "resolved"
    db.flush()
    return len(collected)


def execute_scan(db: Session, scan: Scan) -> None:
    account = db.get(AwsAccount, scan.account_id)
    if account is None or not account.enabled:
        raise RuntimeError("AWS account was removed or disabled")

    run = collection_run_for_scan(db, scan.id)
    if run is None:
        raise RuntimeError("CollectionRun missing for claimed scan")

    aws_session = assume_account_session(account)
    identity = get_caller_identity(aws_session)
    if identity.account_id != account.aws_account_id:
        raise RuntimeError(
            f"Assumed role returned account {identity.account_id}; "
            f"expected {account.aws_account_id}"
        )

    policies = list_effective_policies(db, account.id)
    active_rule_keys = [
        policy["rule_key"] for policy in policies if policy["enabled"] and policy["implemented"]
    ]
    collected, collector_errors, failed_rule_keys = run_collectors(
        aws_session, account.regions, policies
    )
    active_rule_keys = [key for key in active_rule_keys if key not in failed_rule_keys]
    scan.findings_count = persist_findings(db, scan, collected, active_rule_keys)
    scan.status = "completed_with_warnings" if collector_errors else "completed"
    scan.completed_at = datetime.now(UTC)
    scan.error = "\n".join(collector_errors)[:4000] if collector_errors else None

    run.status = CollectionRunStatus.SUCCESS
    run.finished_at = scan.completed_at
    run.opportunities_found = len(collected)
    # The current collector contract does not expose total evaluated resources.
    # Keep this explicit rather than equating resources analyzed with findings.
    run.resources_analyzed = 0
    run.error_detail = None

    account.connection_status = "connected"
    account.last_error = None
    db.commit()


def fail_scan(db: Session, scan_id: str, exc: Exception) -> None:
    db.rollback()
    failed_scan = db.get(Scan, scan_id)
    if failed_scan is None:
        return

    finished_at = datetime.now(UTC)
    error = str(exc)
    failed_scan.status = "failed"
    failed_scan.completed_at = finished_at
    failed_scan.error = error[:4000]

    run = collection_run_for_scan(db, scan_id)
    if run:
        run.status = CollectionRunStatus.FAILED
        run.finished_at = finished_at
        run.error_detail = error[:4000]

    account = db.get(AwsAccount, failed_scan.account_id)
    if account:
        account.connection_status = "error"
        account.last_error = error[:2000]
    db.commit()


def process_once() -> bool:
    with SessionLocal() as db:
        enqueue_due_scans(db)
        scan = claim_scan(db)
        if scan is None:
            return False
        try:
            logger.info("Starting scan %s for account %s", scan.id, scan.account_id)
            execute_scan(db, scan)
            logger.info("Completed scan %s with %s findings", scan.id, scan.findings_count)
        except Exception as exc:  # worker boundary: persist errors and continue
            logger.exception("Scan %s failed", scan.id)
            fail_scan(db, scan.id, exc)
        return True


def main() -> None:
    wait_for_database(engine)
    logger.info("NuvemIQ worker started")
    while True:
        worked = process_once()
        if not worked:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
