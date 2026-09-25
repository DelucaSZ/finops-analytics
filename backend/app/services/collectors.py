import re
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.services.aws_auth import BOTO_CONFIG
from app.services.collector_types import CollectedFinding
from app.services.opportunity_evidence import build_collected_finding_evidence


def _tags_to_dict(tags: list[dict] | None) -> dict[str, str]:
    return {tag["Key"]: tag.get("Value", "") for tag in tags or [] if "Key" in tag}


def _resource_name(tags: dict[str, str]) -> str | None:
    return tags.get("Name") or tags.get("name")


def _is_excluded(tags: dict[str, str], config: dict[str, Any]) -> bool:
    excluded_keys = {key.lower() for key in config.get("excluded_tag_keys", [])}
    return any(key.lower() in excluded_keys for key in tags)


def _money(value: Decimal | float | int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _severity(savings: Decimal) -> str:
    if savings >= 100:
        return "high"
    if savings >= 20:
        return "medium"
    return "low"


def _volume_monthly_cost(volume: dict, config: dict[str, Any]) -> Decimal:
    rates = config.get("monthly_price_per_gb", {})
    rate = Decimal(str(rates.get(volume.get("VolumeType", "gp3"), rates.get("gp3", 0))))
    base = Decimal(str(volume.get("Size", 0))) * rate
    return _money(base)


def collect_ebs_unattached(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    ec2 = session.client("ec2", region_name=region, config=BOTO_CONFIG)
    now = datetime.now(UTC)
    minimum_age = int(config.get("minimum_age_days", 7))
    minimum_savings = Decimal(str(config.get("minimum_monthly_savings_usd", 0)))
    findings: list[CollectedFinding] = []

    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}]):
        for volume in page.get("Volumes", []):
            tags = _tags_to_dict(volume.get("Tags"))
            if _is_excluded(tags, config):
                continue
            age_days = max(0, (now - volume["CreateTime"]).days)
            if age_days < minimum_age:
                continue
            savings = _volume_monthly_cost(volume, config)
            if savings < minimum_savings:
                continue
            findings.append(
                CollectedFinding(
                    rule_key="ebs_unattached",
                    service="EC2/EBS",
                    region=region,
                    resource_id=volume["VolumeId"],
                    resource_name=_resource_name(tags),
                    title="Volume EBS sem anexação",
                    description=(
                        "O volume está disponível e sem anexação. "
                        f"Ele foi criado há {age_days} dias "
                        "e continua gerando cobrança de armazenamento."
                    ),
                    evidence={
                        "state": volume.get("State"),
                        "size_gib": volume.get("Size"),
                        "volume_type": volume.get("VolumeType"),
                        "created_at": volume["CreateTime"].isoformat(),
                        "age_days": age_days,
                        "tags": tags,
                        "observation": "Age is based on volume creation time, not detachment time.",
                    },
                    current_monthly_cost=savings,
                    estimated_monthly_savings=savings,
                    confidence="medium",
                    severity=_severity(savings),
                )
            )
    return findings


def collect_eip_unassociated(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    ec2 = session.client("ec2", region_name=region, config=BOTO_CONFIG)
    monthly_cost = _money(config.get("monthly_cost_usd", 3.65))
    minimum_savings = Decimal(str(config.get("minimum_monthly_savings_usd", 0)))
    if monthly_cost < minimum_savings:
        return []

    findings: list[CollectedFinding] = []
    for address in ec2.describe_addresses().get("Addresses", []):
        if (
            address.get("AssociationId")
            or address.get("InstanceId")
            or address.get("NetworkInterfaceId")
        ):
            continue
        tags = _tags_to_dict(address.get("Tags"))
        if _is_excluded(tags, config):
            continue
        resource_id = address.get("AllocationId") or address["PublicIp"]
        findings.append(
            CollectedFinding(
                rule_key="eip_unassociated",
                service="EC2/VPC",
                region=region,
                resource_id=resource_id,
                resource_name=_resource_name(tags),
                title="Elastic IP sem associação",
                description=(
                    "O endereço IPv4 público está alocado, mas não está associado a um recurso."
                ),
                evidence={
                    "public_ip": address.get("PublicIp"),
                    "allocation_id": address.get("AllocationId"),
                    "domain": address.get("Domain"),
                    "tags": tags,
                },
                current_monthly_cost=monthly_cost,
                estimated_monthly_savings=monthly_cost,
                confidence="high",
                severity=_severity(monthly_cost),
            )
        )
    return findings


def _ami_snapshot_ids(ec2: Any) -> set[str]:
    snapshot_ids: set[str] = set()
    paginator = ec2.get_paginator("describe_images")
    for page in paginator.paginate(Owners=["self"]):
        for image in page.get("Images", []):
            for mapping in image.get("BlockDeviceMappings", []):
                snapshot_id = mapping.get("Ebs", {}).get("SnapshotId")
                if snapshot_id:
                    snapshot_ids.add(snapshot_id)
    return snapshot_ids


def collect_old_snapshots(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    ec2 = session.client("ec2", region_name=region, config=BOTO_CONFIG)
    now = datetime.now(UTC)
    retention_days = int(config.get("retention_days", 90))
    preserve_last = int(config.get("preserve_last_per_volume", 3))
    preserve_ami = bool(config.get("preserve_ami_snapshots", True))
    rate = Decimal(str(config.get("monthly_price_per_gb", 0.05)))
    minimum_savings = Decimal(str(config.get("minimum_monthly_savings_usd", 0)))
    protected_by_ami = _ami_snapshot_ids(ec2) if preserve_ami else set()

    snapshots: list[dict] = []
    paginator = ec2.get_paginator("describe_snapshots")
    for page in paginator.paginate(OwnerIds=["self"]):
        snapshots.extend(page.get("Snapshots", []))

    by_volume: dict[str, list[dict]] = defaultdict(list)
    for snapshot in snapshots:
        by_volume[snapshot.get("VolumeId") or "unknown"].append(snapshot)

    preserved: set[str] = set()
    for volume_snapshots in by_volume.values():
        ordered = sorted(volume_snapshots, key=lambda item: item["StartTime"], reverse=True)
        preserved.update(item["SnapshotId"] for item in ordered[:preserve_last])

    findings: list[CollectedFinding] = []
    for snapshot in snapshots:
        snapshot_id = snapshot["SnapshotId"]
        tags = _tags_to_dict(snapshot.get("Tags"))
        if (
            _is_excluded(tags, config)
            or snapshot_id in protected_by_ami
            or snapshot_id in preserved
        ):
            continue
        age_days = max(0, (now - snapshot["StartTime"]).days)
        if age_days <= retention_days:
            continue
        estimated_upper_bound = _money(Decimal(str(snapshot.get("VolumeSize", 0))) * rate)
        if estimated_upper_bound < minimum_savings:
            continue
        findings.append(
            CollectedFinding(
                rule_key="snapshot_retention",
                service="EC2/EBS",
                region=region,
                resource_id=snapshot_id,
                resource_name=_resource_name(tags),
                title="Snapshot fora da retenção",
                description=(
                    f"O snapshot tem {age_days} dias, acima da retenção configurada de "
                    f"{retention_days} dias."
                ),
                evidence={
                    "volume_id": snapshot.get("VolumeId"),
                    "volume_size_gib": snapshot.get("VolumeSize"),
                    "started_at": snapshot["StartTime"].isoformat(),
                    "age_days": age_days,
                    "retention_days": retention_days,
                    "tags": tags,
                    "cost_note": "Upper-bound estimate; EBS snapshots are incremental.",
                },
                current_monthly_cost=estimated_upper_bound,
                estimated_monthly_savings=estimated_upper_bound,
                confidence="low",
                severity=_severity(estimated_upper_bound),
            )
        )
    return findings


STOP_TIME_PATTERN = re.compile(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) GMT\)")


def _stopped_at(instance: dict) -> datetime | None:
    match = STOP_TIME_PATTERN.search(instance.get("StateTransitionReason", ""))
    if not match:
        return None
    return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _describe_volumes(ec2: Any, volume_ids: list[str]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for start in range(0, len(volume_ids), 500):
        batch = volume_ids[start : start + 500]
        if not batch:
            continue
        response = ec2.describe_volumes(VolumeIds=batch)
        result.update({volume["VolumeId"]: volume for volume in response.get("Volumes", [])})
    return result


def collect_stopped_ec2_with_ebs(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    ec2 = session.client("ec2", region_name=region, config=BOTO_CONFIG)
    now = datetime.now(UTC)
    minimum_days = int(config.get("minimum_stopped_days", 7))
    include_unknown = bool(config.get("include_unknown_stop_time", True))
    minimum_savings = Decimal(str(config.get("minimum_monthly_savings_usd", 0)))
    instances: list[dict] = []

    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    ):
        for reservation in page.get("Reservations", []):
            instances.extend(reservation.get("Instances", []))

    all_volume_ids = [
        mapping["Ebs"]["VolumeId"]
        for instance in instances
        for mapping in instance.get("BlockDeviceMappings", [])
        if mapping.get("Ebs", {}).get("VolumeId")
    ]
    volumes = _describe_volumes(ec2, all_volume_ids)
    findings: list[CollectedFinding] = []

    for instance in instances:
        tags = _tags_to_dict(instance.get("Tags"))
        if _is_excluded(tags, config):
            continue
        stopped_at = _stopped_at(instance)
        stopped_days = (now - stopped_at).days if stopped_at else None
        if stopped_days is None and not include_unknown:
            continue
        if stopped_days is not None and stopped_days < minimum_days:
            continue

        attached_volumes = [
            volumes[mapping["Ebs"]["VolumeId"]]
            for mapping in instance.get("BlockDeviceMappings", [])
            if mapping.get("Ebs", {}).get("VolumeId") in volumes
        ]
        savings = sum(
            (_volume_monthly_cost(volume, config) for volume in attached_volumes), Decimal("0")
        )
        savings = _money(savings)
        if savings < minimum_savings:
            continue
        duration = (
            f"há {stopped_days} dias" if stopped_days is not None else "por tempo não determinado"
        )
        findings.append(
            CollectedFinding(
                rule_key="ec2_stopped_with_ebs",
                service="EC2",
                region=region,
                resource_id=instance["InstanceId"],
                resource_name=_resource_name(tags),
                title="EC2 desligada mantendo volumes EBS",
                description=(
                    f"A instância está desligada {duration}, mas mantém "
                    f"{len(attached_volumes)} volume(s) EBS cobrados."
                ),
                evidence={
                    "state": instance.get("State", {}).get("Name"),
                    "instance_type": instance.get("InstanceType"),
                    "state_transition_reason": instance.get("StateTransitionReason"),
                    "stopped_at": stopped_at.isoformat() if stopped_at else None,
                    "stopped_days": stopped_days,
                    "volumes": [
                        {
                            "volume_id": volume["VolumeId"],
                            "size_gib": volume.get("Size"),
                            "type": volume.get("VolumeType"),
                        }
                        for volume in attached_volumes
                    ],
                    "tags": tags,
                },
                current_monthly_cost=savings,
                estimated_monthly_savings=savings,
                confidence="medium" if stopped_at else "low",
                severity=_severity(savings),
            )
        )
    return findings


def _is_nonproduction(tags: dict[str, str], config: dict[str, Any]) -> bool:
    normalized = {key.lower(): value.lower().strip() for key, value in tags.items()}
    keys = [key.lower() for key in config.get("environment_tag_keys", [])]
    values = {value.lower() for value in config.get("nonproduction_values", [])}
    return any(normalized.get(key) in values for key in keys)


def _outside_business_hours(config: dict[str, Any], now: datetime | None = None) -> bool:
    timezone = ZoneInfo(str(config.get("timezone", "UTC")))
    local_now = now.astimezone(timezone) if now else datetime.now(timezone)
    business_days = {int(day) for day in config.get("business_days", [1, 2, 3, 4, 5])}
    if local_now.isoweekday() not in business_days:
        return True
    start_hour, start_minute = map(int, str(config.get("business_hours_start", "08:00")).split(":"))
    end_hour, end_minute = map(int, str(config.get("business_hours_end", "19:00")).split(":"))
    current_minutes = local_now.hour * 60 + local_now.minute
    return not (start_hour * 60 + start_minute <= current_minutes < end_hour * 60 + end_minute)


def collect_nonprod_ec2_outside_hours(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    if not _outside_business_hours(config):
        return []
    observed_at = datetime.now(UTC)
    timezone = ZoneInfo(str(config.get("timezone", "UTC")))
    ec2 = session.client("ec2", region_name=region, config=BOTO_CONFIG)
    hourly_prices = config.get("estimated_hourly_cost_by_instance_type", {})
    findings: list[CollectedFinding] = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    ):
        for reservation in page.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                tags = _tags_to_dict(instance.get("Tags"))
                if _is_excluded(tags, config) or not _is_nonproduction(tags, config):
                    continue
                instance_type = instance.get("InstanceType", "unknown")
                hourly_cost = Decimal(str(hourly_prices.get(instance_type, 0)))
                findings.append(
                    CollectedFinding(
                        rule_key="ec2_nonprod_outside_hours",
                        service="EC2",
                        region=region,
                        resource_id=instance["InstanceId"],
                        resource_name=_resource_name(tags),
                        title="EC2 não produtiva ligada fora do expediente",
                        description=(
                            "A instância está em execução fora da janela de expediente "
                            "configurada para recursos não produtivos."
                        ),
                        evidence={
                            "state": instance.get("State", {}).get("Name"),
                            "instance_type": instance_type,
                            "launched_at": instance.get("LaunchTime").isoformat()
                            if instance.get("LaunchTime")
                            else None,
                            "observed_at": observed_at.isoformat(),
                            "observed_local_time": observed_at.astimezone(timezone).isoformat(),
                            "timezone": config.get("timezone"),
                            "business_hours_start": config.get("business_hours_start"),
                            "business_hours_end": config.get("business_hours_end"),
                            "tags": tags,
                        },
                        current_monthly_cost=_money(hourly_cost * Decimal("730")),
                        estimated_monthly_savings=_money(hourly_cost * Decimal("365")),
                        confidence="medium" if hourly_cost else "low",
                        severity="medium",
                    )
                )
    return findings


def _metric_statistics(
    cloudwatch: Any,
    *,
    namespace: str,
    metric_name: str,
    dimensions: list[dict[str, str]],
    lookback_days: int,
    statistic: str,
) -> list[float]:
    end = datetime.now(UTC)
    response = cloudwatch.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=end - timedelta(days=lookback_days),
        EndTime=end,
        Period=86400,
        Statistics=[statistic],
    )
    return [float(point[statistic]) for point in response.get("Datapoints", [])]


def collect_load_balancers_no_traffic(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    elbv2 = session.client("elbv2", region_name=region, config=BOTO_CONFIG)
    classic = session.client("elb", region_name=region, config=BOTO_CONFIG)
    cloudwatch = session.client("cloudwatch", region_name=region, config=BOTO_CONFIG)
    now = datetime.now(UTC)
    lookback_days = int(config.get("lookback_days", 7))
    minimum_age_days = int(config.get("minimum_age_days", 7))
    maximum_requests = float(config.get("maximum_requests", 0))
    maximum_bytes = float(config.get("maximum_processed_bytes", 0))
    estimated_cost = _money(config.get("estimated_base_monthly_cost_usd", 0))
    findings: list[CollectedFinding] = []

    paginator = elbv2.get_paginator("describe_load_balancers")
    for page in paginator.paginate():
        for load_balancer in page.get("LoadBalancers", []):
            age_days = (now - load_balancer["CreatedTime"]).days
            if age_days < minimum_age_days:
                continue
            arn = load_balancer["LoadBalancerArn"]
            tag_response = elbv2.describe_tags(ResourceArns=[arn])
            tags = _tags_to_dict(tag_response.get("TagDescriptions", [{}])[0].get("Tags"))
            if _is_excluded(tags, config):
                continue
            lb_type = load_balancer.get("Type", "application")
            is_application = lb_type == "application"
            namespace = "AWS/ApplicationELB" if is_application else "AWS/NetworkELB"
            metric_name = "RequestCount" if is_application else "ProcessedBytes"
            threshold = maximum_requests if is_application else maximum_bytes
            dimension_value = arn.split("loadbalancer/", 1)[-1]
            values = _metric_statistics(
                cloudwatch,
                namespace=namespace,
                metric_name=metric_name,
                dimensions=[{"Name": "LoadBalancer", "Value": dimension_value}],
                lookback_days=lookback_days,
                statistic="Sum",
            )
            total = sum(values)
            if total > threshold:
                continue
            if not values:
                title = "Load Balancer sem métricas suficientes"
                description = (
                    f"O CloudWatch não retornou amostras de {metric_name} nos últimos "
                    f"{lookback_days} dias; o tráfego precisa ser validado."
                )
            elif total == 0:
                title = "Load Balancer sem tráfego observado"
                description = (
                    f"O CloudWatch registrou zero para {metric_name} nos últimos "
                    f"{lookback_days} dias."
                )
            else:
                title = "Load Balancer com tráfego abaixo do limite"
                description = (
                    f"O CloudWatch registrou {total:.2f} para {metric_name}, dentro do "
                    f"limite configurado de {threshold:.2f} nos últimos {lookback_days} dias."
                )
            findings.append(
                CollectedFinding(
                    rule_key="load_balancer_no_traffic",
                    service="Elastic Load Balancing",
                    region=region,
                    resource_id=arn,
                    resource_name=load_balancer.get("LoadBalancerName"),
                    title=title,
                    description=description,
                    evidence={
                        "type": lb_type,
                        "metric": metric_name,
                        "metric_total": total,
                        "datapoint_count": len(values),
                        "lookback_days": lookback_days,
                        "created_at": load_balancer["CreatedTime"].isoformat(),
                        "tags": tags,
                    },
                    current_monthly_cost=estimated_cost,
                    estimated_monthly_savings=estimated_cost,
                    confidence="low",
                    severity=_severity(estimated_cost),
                )
            )

    classic_paginator = classic.get_paginator("describe_load_balancers")
    for page in classic_paginator.paginate():
        for load_balancer in page.get("LoadBalancerDescriptions", []):
            age_days = (now - load_balancer["CreatedTime"]).days
            if age_days < minimum_age_days:
                continue
            name = load_balancer["LoadBalancerName"]
            tag_response = classic.describe_tags(LoadBalancerNames=[name])
            tags = _tags_to_dict(tag_response.get("TagDescriptions", [{}])[0].get("Tags"))
            if _is_excluded(tags, config):
                continue
            values = _metric_statistics(
                cloudwatch,
                namespace="AWS/ELB",
                metric_name="RequestCount",
                dimensions=[{"Name": "LoadBalancerName", "Value": name}],
                lookback_days=lookback_days,
                statistic="Sum",
            )
            total = sum(values)
            if total > maximum_requests:
                continue
            if not values:
                title = "Classic Load Balancer sem métricas suficientes"
                description = (
                    f"O CloudWatch não retornou amostras de RequestCount nos últimos "
                    f"{lookback_days} dias; o tráfego precisa ser validado."
                )
            elif total == 0:
                title = "Classic Load Balancer sem tráfego observado"
                description = (
                    f"O CloudWatch registrou zero requisições nos últimos {lookback_days} dias."
                )
            else:
                title = "Classic Load Balancer com tráfego abaixo do limite"
                description = (
                    f"O CloudWatch registrou {total:.2f} requisições, dentro do limite "
                    f"configurado de {maximum_requests:.2f} nos últimos {lookback_days} dias."
                )
            findings.append(
                CollectedFinding(
                    rule_key="load_balancer_no_traffic",
                    service="Elastic Load Balancing",
                    region=region,
                    resource_id=name,
                    resource_name=name,
                    title=title,
                    description=description,
                    evidence={
                        "type": "classic",
                        "metric": "RequestCount",
                        "metric_total": total,
                        "datapoint_count": len(values),
                        "lookback_days": lookback_days,
                        "created_at": load_balancer["CreatedTime"].isoformat(),
                        "tags": tags,
                    },
                    current_monthly_cost=estimated_cost,
                    estimated_monthly_savings=estimated_cost,
                    confidence="low",
                    severity=_severity(estimated_cost),
                )
            )
    return findings


def collect_idle_nonprod_rds(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    rds = session.client("rds", region_name=region, config=BOTO_CONFIG)
    cloudwatch = session.client("cloudwatch", region_name=region, config=BOTO_CONFIG)
    lookback_days = int(config.get("lookback_days", 7))
    max_cpu = float(config.get("maximum_average_cpu_percent", 5))
    max_connections = float(config.get("maximum_connections", 1))
    price_map = config.get("estimated_monthly_cost_by_instance_class", {})
    findings: list[CollectedFinding] = []

    paginator = rds.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for instance in page.get("DBInstances", []):
            arn = instance["DBInstanceArn"]
            tags = _tags_to_dict(rds.list_tags_for_resource(ResourceName=arn).get("TagList"))
            if _is_excluded(tags, config) or not _is_nonproduction(tags, config):
                continue
            identifier = instance["DBInstanceIdentifier"]
            dimensions = [{"Name": "DBInstanceIdentifier", "Value": identifier}]
            cpu_values = _metric_statistics(
                cloudwatch,
                namespace="AWS/RDS",
                metric_name="CPUUtilization",
                dimensions=dimensions,
                lookback_days=lookback_days,
                statistic="Average",
            )
            connection_values = _metric_statistics(
                cloudwatch,
                namespace="AWS/RDS",
                metric_name="DatabaseConnections",
                dimensions=dimensions,
                lookback_days=lookback_days,
                statistic="Maximum",
            )
            if not cpu_values or not connection_values:
                continue
            average_cpu = sum(cpu_values) / len(cpu_values)
            maximum_connections = max(connection_values)
            if average_cpu > max_cpu or maximum_connections > max_connections:
                continue
            instance_class = instance.get("DBInstanceClass", "unknown")
            estimated_cost = _money(price_map.get(instance_class, 0))
            findings.append(
                CollectedFinding(
                    rule_key="rds_nonprod_idle",
                    service="RDS",
                    region=region,
                    resource_id=identifier,
                    resource_name=identifier,
                    title="RDS não produtivo ocioso",
                    description=(
                        "As amostras de CPU e conexões retornadas pelo CloudWatch ficaram "
                        f"abaixo dos limites na janela de {lookback_days} dias."
                    ),
                    evidence={
                        "engine": instance.get("Engine"),
                        "instance_class": instance_class,
                        "average_cpu_percent": round(average_cpu, 2),
                        "maximum_connections": round(maximum_connections, 2),
                        "cpu_datapoint_count": len(cpu_values),
                        "connection_datapoint_count": len(connection_values),
                        "lookback_days": lookback_days,
                        "tags": tags,
                    },
                    current_monthly_cost=estimated_cost,
                    estimated_monthly_savings=estimated_cost,
                    confidence="medium" if estimated_cost else "low",
                    severity="medium",
                )
            )
    return findings


def _missing_tags(tags: dict[str, str], required: list[str]) -> list[str]:
    existing = {key.lower() for key in tags}
    return [key for key in required if key.lower() not in existing]


def _tag_finding(
    *,
    region: str,
    service: str,
    resource_id: str,
    resource_name: str | None,
    tags: dict[str, str],
    missing: list[str],
) -> CollectedFinding:
    return CollectedFinding(
        rule_key="missing_required_tags",
        service=service,
        region=region,
        resource_id=resource_id,
        resource_name=resource_name,
        title="Recurso sem tags obrigatórias",
        description=f"O recurso não possui as tags obrigatórias: {', '.join(missing)}.",
        evidence={"missing_tags": missing, "current_tags": tags},
        confidence="high",
        severity="low",
    )


def collect_missing_tags(
    session: boto3.Session, region: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    required = [str(item) for item in config.get("required_tags", [])]
    resource_types = set(config.get("resource_types", []))
    findings: list[CollectedFinding] = []
    ec2 = session.client("ec2", region_name=region, config=BOTO_CONFIG)

    if "ec2" in resource_types:
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    tags = _tags_to_dict(instance.get("Tags"))
                    missing = _missing_tags(tags, required)
                    if missing and not _is_excluded(tags, config):
                        findings.append(
                            _tag_finding(
                                region=region,
                                service="EC2",
                                resource_id=instance["InstanceId"],
                                resource_name=_resource_name(tags),
                                tags=tags,
                                missing=missing,
                            )
                        )

    if "ebs" in resource_types:
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for volume in page.get("Volumes", []):
                tags = _tags_to_dict(volume.get("Tags"))
                missing = _missing_tags(tags, required)
                if missing and not _is_excluded(tags, config):
                    findings.append(
                        _tag_finding(
                            region=region,
                            service="EC2/EBS",
                            resource_id=volume["VolumeId"],
                            resource_name=_resource_name(tags),
                            tags=tags,
                            missing=missing,
                        )
                    )

    if "rds" in resource_types:
        rds = session.client("rds", region_name=region, config=BOTO_CONFIG)
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for instance in page.get("DBInstances", []):
                tags = _tags_to_dict(
                    rds.list_tags_for_resource(ResourceName=instance["DBInstanceArn"]).get(
                        "TagList"
                    )
                )
                missing = _missing_tags(tags, required)
                if missing and not _is_excluded(tags, config):
                    identifier = instance["DBInstanceIdentifier"]
                    findings.append(
                        _tag_finding(
                            region=region,
                            service="RDS",
                            resource_id=identifier,
                            resource_name=identifier,
                            tags=tags,
                            missing=missing,
                        )
                    )

    if "load-balancer" in resource_types:
        elbv2 = session.client("elbv2", region_name=region, config=BOTO_CONFIG)
        paginator = elbv2.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for load_balancer in page.get("LoadBalancers", []):
                arn = load_balancer["LoadBalancerArn"]
                response = elbv2.describe_tags(ResourceArns=[arn])
                tags = _tags_to_dict(response.get("TagDescriptions", [{}])[0].get("Tags"))
                missing = _missing_tags(tags, required)
                if missing and not _is_excluded(tags, config):
                    findings.append(
                        _tag_finding(
                            region=region,
                            service="Elastic Load Balancing",
                            resource_id=arn,
                            resource_name=load_balancer.get("LoadBalancerName"),
                            tags=tags,
                            missing=missing,
                        )
                    )
    return findings


def _cost_results(client: Any, **request: Any) -> list[dict]:
    """Read every Cost Explorer page, preserving the request across tokens."""
    results: list[dict] = []
    while True:
        response = client.get_cost_and_usage(**request)
        results.extend(response.get("ResultsByTime", []))
        token = response.get("NextPageToken")
        if not token:
            return results
        request["NextPageToken"] = token


def _cost_contributors(
    client: Any,
    service: str,
    aws_region: str,
    baseline_start: date,
    recent_start: date,
    end: date,
    baseline_days: int,
    comparison_days: int,
) -> dict:
    """Explain cost increases by billing usage type, without inferring resource causes."""
    try:
        results = _cost_results(
            client,
            TimePeriod={"Start": baseline_start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            Filter={
                "And": [
                    {"Dimensions": {"Key": "SERVICE", "Values": [service]}},
                    {"Dimensions": {"Key": "REGION", "Values": [aws_region]}},
                ]
            },
            GroupBy=[{"Type": "DIMENSION", "Key": "USAGE_TYPE"}],
        )
    except (BotoCoreError, ClientError):
        # The primary comparison is still valid if this optional query fails.
        return {"breakdown_status": "unavailable", "cost_contributors": []}

    baseline: dict[str, Decimal] = defaultdict(Decimal)
    recent: dict[str, Decimal] = defaultdict(Decimal)
    for result in results:
        destination = (
            recent if result["TimePeriod"]["Start"] >= recent_start.isoformat() else baseline
        )
        for group in result.get("Groups", []):
            destination[group["Keys"][0]] += Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
    changes = []
    for usage_type in baseline.keys() | recent.keys():
        expected = baseline[usage_type] / Decimal(baseline_days) * Decimal(comparison_days)
        changes.append((recent[usage_type] - expected, usage_type, expected, recent[usage_type]))
    positive = sorted((item for item in changes if item[0] > 0), reverse=True)
    return {
        "breakdown_status": "available",
        "breakdown_estimated": any(result.get("Estimated", False) for result in results),
        "positive_contributor_count": len(positive),
        "cost_contributors": [
            {
                "usage_type": usage_type,
                "baseline_equivalent_usd": float(_money(expected)),
                "current_spend_usd": float(_money(current)),
                "delta_usd": float(_money(delta)),
            }
            for delta, usage_type, expected, current in positive[:5]
        ],
    }


def collect_cost_growth_anomalies(
    session: boto3.Session, _: str, config: dict[str, Any]
) -> list[CollectedFinding]:
    client = session.client("ce", region_name="us-east-1", config=BOTO_CONFIG)
    baseline_days = int(config.get("baseline_days", 28))
    comparison_days = int(config.get("comparison_days", 7))
    minimum_growth = float(config.get("minimum_growth_percent", 30))
    minimum_delta = Decimal(str(config.get("minimum_delta_usd", 50)))
    minimum_spend = Decimal(str(config.get("minimum_current_spend_usd", 20)))
    end = datetime.now(UTC).date()
    recent_start = end - timedelta(days=comparison_days)
    baseline_start = recent_start - timedelta(days=baseline_days)
    results = _cost_results(
        client,
        TimePeriod={"Start": baseline_start.isoformat(), "End": end.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "REGION"},
        ],
    )

    baseline: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    recent: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for result in results:
        result_date = datetime.fromisoformat(result["TimePeriod"]["Start"]).date()
        destination = recent if result_date >= recent_start else baseline
        for group in result.get("Groups", []):
            service, aws_region = group.get("Keys", ["Unknown", "global"])
            amount = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
            destination[(service, aws_region)] += amount

    findings: list[CollectedFinding] = []
    for key, current_spend in recent.items():
        if current_spend < minimum_spend:
            continue
        baseline_equivalent = (
            baseline[key] / Decimal(str(baseline_days)) * Decimal(str(comparison_days))
        )
        delta = current_spend - baseline_equivalent
        if delta < minimum_delta:
            continue
        growth_percent = (
            float(delta / baseline_equivalent * 100) if baseline_equivalent > 0 else None
        )
        if growth_percent is not None and growth_percent < minimum_growth:
            continue
        service, raw_region = key
        aws_region = raw_region or "global"
        comparison = (
            f"Alta de {growth_percent:.1f}% sobre a média diária histórica."
            if growth_percent is not None
            else "Base histórica zero ou negativa; variação percentual não aplicável."
        )
        breakdown = _cost_contributors(
            client,
            service,
            raw_region,
            baseline_start,
            recent_start,
            end,
            baseline_days,
            comparison_days,
        )
        findings.append(
            CollectedFinding(
                rule_key="cost_growth_anomaly",
                service=service,
                region=aws_region,
                resource_id=f"{service}|{aws_region}",
                resource_name=service,
                title="Crescimento anormal de custo",
                description=(
                    f"{service} em {aws_region}: US$ {current_spend:.2f} nos últimos "
                    f"{comparison_days} dias, contra US$ {baseline_equivalent:.2f} esperados "
                    f"para o mesmo intervalo (aumento de US$ {delta:.2f}). {comparison}"
                ),
                evidence={
                    "baseline_period_days": baseline_days,
                    "comparison_period_days": comparison_days,
                    "baseline_equivalent_usd": float(_money(baseline_equivalent)),
                    "current_spend_usd": float(_money(current_spend)),
                    "delta_usd": float(_money(delta)),
                    "growth_percent": round(growth_percent, 2)
                    if growth_percent is not None
                    else None,
                    "baseline_start": baseline_start.isoformat(),
                    "baseline_end_exclusive": recent_start.isoformat(),
                    "comparison_start": recent_start.isoformat(),
                    "comparison_end_exclusive": end.isoformat(),
                    "baseline_total_usd": float(_money(baseline[key])),
                    "minimum_growth_percent": minimum_growth,
                    "minimum_delta_usd": float(minimum_delta),
                    "minimum_current_spend_usd": float(minimum_spend),
                    "source": "AWS Cost Explorer",
                    "metric": "UnblendedCost",
                    "estimated": any(result.get("Estimated", False) for result in results),
                    **breakdown,
                },
                current_monthly_cost=_money(
                    current_spend / Decimal(str(comparison_days)) * Decimal("30")
                ),
                estimated_monthly_savings=Decimal("0"),
                confidence="high",
                severity="high" if delta >= 500 else "medium",
            )
        )
    return findings


COLLECTORS = {
    "ebs_unattached": collect_ebs_unattached,
    "eip_unassociated": collect_eip_unassociated,
    "snapshot_retention": collect_old_snapshots,
    "ec2_stopped_with_ebs": collect_stopped_ec2_with_ebs,
    "ec2_nonprod_outside_hours": collect_nonprod_ec2_outside_hours,
    "load_balancer_no_traffic": collect_load_balancers_no_traffic,
    "rds_nonprod_idle": collect_idle_nonprod_rds,
    "missing_required_tags": collect_missing_tags,
    "cost_growth_anomaly": collect_cost_growth_anomalies,
}

GLOBAL_COLLECTORS = {"cost_growth_anomaly"}


def run_collectors(
    session: boto3.Session, regions: list[str], policies: list[dict]
) -> tuple[list[CollectedFinding], list[str], set[str]]:
    findings: list[CollectedFinding] = []
    errors: list[str] = []
    failed_rule_keys: set[str] = set()
    for policy in policies:
        collector = COLLECTORS.get(policy["rule_key"])
        if not collector or not policy["enabled"] or not policy["implemented"]:
            continue
        collector_regions = ["global"] if policy["rule_key"] in GLOBAL_COLLECTORS else regions
        for region in collector_regions:
            try:
                collected = collector(session, region, policy["config"])
                evaluated_at = datetime.now(UTC)
                for finding in collected:
                    finding.evidence = build_collected_finding_evidence(
                        finding,
                        policy,
                        evaluated_at=evaluated_at,
                    )
                findings.extend(collected)
            except (BotoCoreError, ClientError) as exc:
                errors.append(f"{policy['rule_key']}@{region}: {exc}")
                failed_rule_keys.add(policy["rule_key"])
    return findings, errors, failed_rule_keys
