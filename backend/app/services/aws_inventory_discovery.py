"""AWS Wave 1 Inventory discovery, independent from FinOps opportunity collectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from app.core.inventory import (
    DiscoveredInventoryResource,
    InventoryCoverage,
    InventoryCoverageStatus,
    InventoryDiscoveryIssue,
    InventoryDiscoveryResult,
)

AWS_WAVE1_RESOURCE_TYPES = (
    "compute_instance",
    "block_volume",
    "public_ip",
    "relational_database",
)


@dataclass(slots=True)
class _ScopeFailure(Exception):
    cause: Exception
    resources: list[DiscoveredInventoryResource]
    pages_seen: int = 0


class AwsInventoryDiscoveryService:
    """Enumerate AWS resources by region/resource type without writing to the database."""

    def discover(
        self,
        session,
        *,
        cloud_account_id: int,
        regions: list[str] | tuple[str, ...],
    ) -> InventoryDiscoveryResult:
        resources_by_identity: dict[tuple[str, str], DiscoveredInventoryResource] = {}
        coverage: list[InventoryCoverage] = []
        warnings: list[InventoryDiscoveryIssue] = []
        errors: list[InventoryDiscoveryIssue] = []

        adapters: tuple[
            tuple[str, Callable[[Any, str], list[DiscoveredInventoryResource]]], ...
        ] = (
            ("compute_instance", self._discover_instances),
            ("block_volume", self._discover_volumes),
            ("public_ip", self._discover_addresses),
            ("relational_database", self._discover_databases),
        )

        for region in dict.fromkeys(str(item).strip() for item in regions if str(item).strip()):
            for resource_type, adapter in adapters:
                try:
                    observed = adapter(session, region)
                except _ScopeFailure as failure:
                    for resource in failure.resources:
                        resources_by_identity[(
                            resource.resource_type, resource.resource_id
                        )] = resource
                    status = (
                        InventoryCoverageStatus.PARTIAL
                        if failure.pages_seen > 0
                        else InventoryCoverageStatus.FAILED
                    )
                    code = self._error_code(failure.cause)
                    issue = InventoryDiscoveryIssue(
                        provider="aws",
                        resource_type=resource_type,
                        region=region,
                        category=self._error_category(code),
                        code=code,
                        message=f"AWS {resource_type} discovery failed in {region} ({code})",
                    )
                    errors.append(issue)
                    coverage.append(
                        InventoryCoverage(
                            provider="aws",
                            cloud_account_id=cloud_account_id,
                            resource_type=resource_type,
                            region=region,
                            status=status,
                            error_code=code,
                            error_message=issue.message,
                        )
                    )
                    continue
                except Exception as exc:  # defensive isolation around client creation
                    code = self._error_code(exc)
                    issue = InventoryDiscoveryIssue(
                        provider="aws",
                        resource_type=resource_type,
                        region=region,
                        category=self._error_category(code),
                        code=code,
                        message=f"AWS {resource_type} discovery failed in {region} ({code})",
                    )
                    errors.append(issue)
                    coverage.append(
                        InventoryCoverage(
                            provider="aws",
                            cloud_account_id=cloud_account_id,
                            resource_type=resource_type,
                            region=region,
                            status=InventoryCoverageStatus.FAILED,
                            error_code=code,
                            error_message=issue.message,
                        )
                    )
                    continue

                for resource in observed:
                    resources_by_identity[(resource.resource_type, resource.resource_id)] = resource
                coverage.append(
                    InventoryCoverage(
                        provider="aws",
                        cloud_account_id=cloud_account_id,
                        resource_type=resource_type,
                        region=region,
                        status=InventoryCoverageStatus.COMPLETE,
                    )
                )

        return InventoryDiscoveryResult(
            resources=tuple(resources_by_identity.values()),
            coverage=tuple(coverage),
            warnings=tuple(warnings),
            errors=tuple(errors),
        )

    @staticmethod
    def _tags(value: Any) -> dict[str, Any]:
        if not isinstance(value, list):
            return {}
        tags: dict[str, Any] = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = item.get("Key")
            if key is None:
                continue
            tags[str(key)] = item.get("Value")
        return tags

    @staticmethod
    def _name(tags: dict[str, Any]) -> str | None:
        value = tags.get("Name")
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): AwsInventoryDiscoveryService._json_value(child)
                for key, child in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [AwsInventoryDiscoveryService._json_value(child) for child in value]
        return value

    @staticmethod
    def _error_code(exc: Exception) -> str:
        response = getattr(exc, "response", None)
        if isinstance(response, dict):
            error = response.get("Error")
            if isinstance(error, dict) and error.get("Code"):
                return str(error["Code"])[:120]
        return type(exc).__name__[:120] or "ProviderError"

    @staticmethod
    def _error_category(code: str) -> str:
        lowered = code.lower()
        if lowered in {
            "accessdenied",
            "accessdeniedexception",
            "unauthorizedoperation",
            "authfailure",
            "invalidclienttokenid",
        }:
            return "authorization"
        if any(token in lowered for token in ("throttl", "requestlimit", "toomanyrequests")):
            return "throttling"
        if any(token in lowered for token in ("timeout", "connection", "endpoint")):
            return "network"
        return "provider_error"

    @staticmethod
    def _ec2_status(native: str | None) -> str:
        mapping = {
            "pending": "starting",
            "running": "running",
            "stopping": "stopping",
            "stopped": "stopped",
            "shutting-down": "terminating",
            "terminated": "terminated",
        }
        return mapping.get(str(native or "").lower(), "unknown")

    @staticmethod
    def _ebs_status(native: str | None) -> str:
        mapping = {
            "creating": "creating",
            "available": "available",
            "in-use": "in_use",
            "deleting": "deleting",
            "deleted": "deleted",
            "error": "error",
        }
        return mapping.get(str(native or "").lower(), "unknown")

    @staticmethod
    def _rds_status(native: str | None) -> str:
        value = str(native or "").lower()
        mapping = {
            "available": "running",
            "backing-up": "running",
            "configuring-enhanced-monitoring": "running",
            "configuring-iam-database-auth": "running",
            "maintenance": "running",
            "modifying": "running",
            "rebooting": "running",
            "renaming": "running",
            "resetting-master-credentials": "running",
            "starting": "starting",
            "stopping": "stopping",
            "stopped": "stopped",
            "creating": "creating",
            "deleting": "deleting",
            "failed": "error",
            "inaccessible-encryption-credentials": "error",
            "incompatible-network": "error",
            "incompatible-option-group": "error",
            "incompatible-parameters": "error",
            "incompatible-restore": "error",
            "storage-full": "error",
        }
        return mapping.get(value, "unknown")

    def _discover_instances(self, session, region: str) -> list[DiscoveredInventoryResource]:
        client = session.client("ec2", region_name=region)
        paginator = client.get_paginator("describe_instances")
        resources: list[DiscoveredInventoryResource] = []
        pages_seen = 0
        try:
            for page in paginator.paginate():
                pages_seen += 1
                for reservation in page.get("Reservations", []):
                    for item in reservation.get("Instances", []):
                        resource_id = item.get("InstanceId")
                        if not resource_id:
                            continue
                        tags = self._tags(item.get("Tags"))
                        native_status = (item.get("State") or {}).get("Name")
                        resources.append(
                            DiscoveredInventoryResource(
                                provider="aws",
                                resource_id=str(resource_id),
                                resource_type="compute_instance",
                                native_resource_type="AWS::EC2::Instance",
                                service="EC2",
                                name=self._name(tags),
                                region=region,
                                availability_zone=(item.get("Placement") or {}).get(
                                    "AvailabilityZone"
                                ),
                                lifecycle_status=self._ec2_status(native_status),
                                native_status=native_status,
                                tags=tags,
                                attributes=self._json_value(
                                    {
                                        "instance_type": item.get("InstanceType"),
                                        "architecture": item.get("Architecture"),
                                        "platform": item.get("Platform"),
                                        "platform_details": item.get("PlatformDetails"),
                                        "launch_time": item.get("LaunchTime"),
                                        "vpc_id": item.get("VpcId"),
                                        "subnet_id": item.get("SubnetId"),
                                        "private_ip": item.get("PrivateIpAddress"),
                                        "public_ip": item.get("PublicIpAddress"),
                                    }
                                ),
                            )
                        )
        except Exception as exc:
            raise _ScopeFailure(exc, resources, pages_seen) from exc
        return resources

    def _discover_volumes(self, session, region: str) -> list[DiscoveredInventoryResource]:
        client = session.client("ec2", region_name=region)
        paginator = client.get_paginator("describe_volumes")
        resources: list[DiscoveredInventoryResource] = []
        pages_seen = 0
        try:
            for page in paginator.paginate():
                pages_seen += 1
                for item in page.get("Volumes", []):
                    resource_id = item.get("VolumeId")
                    if not resource_id:
                        continue
                    tags = self._tags(item.get("Tags"))
                    native_status = item.get("State")
                    attachments = [
                        self._json_value(
                            {
                                "instance_id": attachment.get("InstanceId"),
                                "device": attachment.get("Device"),
                                "state": attachment.get("State"),
                                "attach_time": attachment.get("AttachTime"),
                                "delete_on_termination": attachment.get("DeleteOnTermination"),
                            }
                        )
                        for attachment in item.get("Attachments", [])
                    ]
                    resources.append(
                        DiscoveredInventoryResource(
                            provider="aws",
                            resource_id=str(resource_id),
                            resource_type="block_volume",
                            native_resource_type="AWS::EC2::Volume",
                            service="EC2",
                            name=self._name(tags),
                            region=region,
                            availability_zone=item.get("AvailabilityZone"),
                            lifecycle_status=self._ebs_status(native_status),
                            native_status=native_status,
                            tags=tags,
                            attributes=self._json_value(
                                {
                                    "volume_type": item.get("VolumeType"),
                                    "size_gb": item.get("Size"),
                                    "iops": item.get("Iops"),
                                    "throughput": item.get("Throughput"),
                                    "encrypted": item.get("Encrypted"),
                                    "multi_attach_enabled": item.get("MultiAttachEnabled"),
                                    "attachments": attachments,
                                }
                            ),
                        )
                    )
        except Exception as exc:
            raise _ScopeFailure(exc, resources, pages_seen) from exc
        return resources

    def _discover_addresses(self, session, region: str) -> list[DiscoveredInventoryResource]:
        client = session.client("ec2", region_name=region)
        resources: list[DiscoveredInventoryResource] = []
        try:
            response = client.describe_addresses()
            for item in response.get("Addresses", []):
                allocation_id = item.get("AllocationId")
                public_ip = item.get("PublicIp")
                resource_id = allocation_id or public_ip
                if not resource_id:
                    continue
                tags = self._tags(item.get("Tags"))
                associated = bool(item.get("AssociationId"))
                resources.append(
                    DiscoveredInventoryResource(
                        provider="aws",
                        resource_id=str(resource_id),
                        resource_type="public_ip",
                        native_resource_type="AWS::EC2::EIP",
                        service="EC2",
                        name=self._name(tags),
                        region=region,
                        lifecycle_status="associated" if associated else "available",
                        native_status=None,
                        tags=tags,
                        attributes={
                            "public_ip": public_ip,
                            "allocation_id": allocation_id,
                            "association_id": item.get("AssociationId"),
                            "network_interface_id": item.get("NetworkInterfaceId"),
                            "instance_id": item.get("InstanceId"),
                            "domain": item.get("Domain"),
                        },
                    )
                )
        except Exception as exc:
            raise _ScopeFailure(exc, resources, 0) from exc
        return resources

    def _discover_databases(self, session, region: str) -> list[DiscoveredInventoryResource]:
        client = session.client("rds", region_name=region)
        paginator = client.get_paginator("describe_db_instances")
        resources: list[DiscoveredInventoryResource] = []
        pages_seen = 0
        try:
            for page in paginator.paginate():
                pages_seen += 1
                for item in page.get("DBInstances", []):
                    identifier = item.get("DBInstanceIdentifier")
                    resource_id = item.get("DBInstanceArn") or identifier
                    if not resource_id:
                        continue
                    native_status = item.get("DBInstanceStatus")
                    endpoint = item.get("Endpoint") or {}
                    resources.append(
                        DiscoveredInventoryResource(
                            provider="aws",
                            resource_id=str(resource_id),
                            resource_type="relational_database",
                            native_resource_type="AWS::RDS::DBInstance",
                            service="RDS",
                            name=str(identifier) if identifier else None,
                            region=region,
                            availability_zone=item.get("AvailabilityZone"),
                            lifecycle_status=self._rds_status(native_status),
                            native_status=native_status,
                            tags={},
                            attributes=self._json_value(
                                {
                                    "engine": item.get("Engine"),
                                    "engine_version": item.get("EngineVersion"),
                                    "db_instance_class": item.get("DBInstanceClass"),
                                    "multi_az": item.get("MultiAZ"),
                                    "storage_type": item.get("StorageType"),
                                    "allocated_storage": item.get("AllocatedStorage"),
                                    "endpoint": {
                                        "address": endpoint.get("Address"),
                                        "port": endpoint.get("Port"),
                                    }
                                    if endpoint
                                    else None,
                                    "license_model": item.get("LicenseModel"),
                                }
                            ),
                        )
                    )
        except Exception as exc:
            raise _ScopeFailure(exc, resources, pages_seen) from exc
        return resources
