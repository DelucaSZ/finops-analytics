from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_user
from app.db.session import get_db
from app.models.account import AwsAccount
from app.models.finding import Finding
from app.models.scan import Scan

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_user)])


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    accounts = db.scalar(select(func.count()).select_from(AwsAccount)) or 0
    connected_accounts = (
        db.scalar(
            select(func.count())
            .select_from(AwsAccount)
            .where(AwsAccount.connection_status == "connected")
        )
        or 0
    )
    open_findings = (
        db.scalar(select(func.count()).select_from(Finding).where(Finding.status == "open")) or 0
    )
    monthly_savings = db.scalar(
        select(func.coalesce(func.sum(Finding.estimated_monthly_savings), 0)).where(
            Finding.status == "open"
        )
    ) or Decimal("0")
    severity_rows = db.execute(
        select(Finding.severity, func.count())
        .where(Finding.status == "open")
        .group_by(Finding.severity)
    ).all()
    latest_scans = list(db.scalars(select(Scan).order_by(Scan.created_at.desc()).limit(5)))
    top_findings = list(
        db.scalars(
            select(Finding)
            .where(Finding.status == "open")
            .order_by(Finding.estimated_monthly_savings.desc())
            .limit(5)
        )
    )
    return {
        "accounts": accounts,
        "connected_accounts": connected_accounts,
        "open_findings": open_findings,
        "estimated_monthly_savings_usd": float(monthly_savings),
        "estimated_annual_savings_usd": float(monthly_savings * 12),
        "by_severity": {severity: count for severity, count in severity_rows},
        "latest_scans": [
            {
                "id": scan.id,
                "account_id": scan.account_id,
                "status": scan.status,
                "created_at": scan.created_at,
                "findings_count": scan.findings_count,
            }
            for scan in latest_scans
        ],
        "top_findings": [
            {
                "id": finding.id,
                "account_id": finding.account_id,
                "title": finding.title,
                "resource_id": finding.resource_id,
                "region": finding.region,
                "severity": finding.severity,
                "estimated_monthly_savings_usd": float(finding.estimated_monthly_savings),
            }
            for finding in top_findings
        ],
    }
