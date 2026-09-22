import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import AwsAccount
from app.models.finding import Finding
from app.models.scan import Scan


def seed_demo_data(db: Session) -> None:
    if db.scalar(select(AwsAccount.id).limit(1)) is not None:
        return

    account = AwsAccount(
        name="Conta demonstração",
        aws_account_id="111122223333",
        role_arn="arn:aws:iam::111122223333:role/NuvemIQReadOnly",
        external_id="nuvemiq-demo-external-id",
        regions=["sa-east-1", "us-east-1"],
        connection_status="connected",
        enabled=True,
    )
    db.add(account)
    db.flush()
    now = datetime.now(UTC)
    scan = Scan(
        account_id=account.id,
        status="completed",
        trigger="manual",
        started_at=now - timedelta(minutes=4),
        completed_at=now,
        findings_count=4,
    )
    db.add(scan)
    db.flush()

    examples = [
        {
            "rule_key": "ebs_unattached",
            "service": "EC2/EBS",
            "region": "sa-east-1",
            "resource_id": "vol-0demo001",
            "resource_name": "backup-antigo",
            "title": "Volume EBS sem anexação",
            "description": "Volume disponível e sem anexação há mais de 30 dias.",
            "cost": "82.40",
            "severity": "medium",
            "confidence": "medium",
        },
        {
            "rule_key": "snapshot_retention",
            "service": "EC2/EBS",
            "region": "us-east-1",
            "resource_id": "snap-0demo002",
            "resource_name": "snapshot-legado",
            "title": "Snapshot fora da retenção",
            "description": "Snapshot com 214 dias, acima da retenção configurada.",
            "cost": "145.00",
            "severity": "high",
            "confidence": "low",
        },
        {
            "rule_key": "load_balancer_no_traffic",
            "service": "Elastic Load Balancing",
            "region": "sa-east-1",
            "resource_id": "app/demo-lb/123456",
            "resource_name": "demo-lb",
            "title": "Load Balancer sem tráfego",
            "description": "Nenhuma requisição observada nos últimos sete dias.",
            "cost": "16.43",
            "severity": "low",
            "confidence": "low",
        },
        {
            "rule_key": "ec2_stopped_with_ebs",
            "service": "EC2",
            "region": "sa-east-1",
            "resource_id": "i-0demo003",
            "resource_name": "hml-web-antiga",
            "title": "EC2 desligada mantendo volumes EBS",
            "description": "Instância desligada há 45 dias com três volumes anexados.",
            "cost": "210.30",
            "severity": "high",
            "confidence": "medium",
        },
    ]

    for item in examples:
        fingerprint = hashlib.sha256(
            f"demo|{item['rule_key']}|{item['resource_id']}".encode()
        ).hexdigest()
        cost = Decimal(item["cost"])
        db.add(
            Finding(
                fingerprint=fingerprint,
                scan_id=scan.id,
                account_id=account.id,
                rule_key=item["rule_key"],
                service=item["service"],
                region=item["region"],
                resource_id=item["resource_id"],
                resource_name=item["resource_name"],
                title=item["title"],
                description=item["description"],
                evidence={"demo": True},
                current_monthly_cost=cost,
                estimated_monthly_savings=cost,
                confidence=item["confidence"],
                severity=item["severity"],
                status="open",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    db.commit()
