from datetime import UTC, datetime

from app.core.inventory import InventoryCoverageStatus
from app.services.aws_inventory_discovery import AwsInventoryDiscoveryService
from app.services.oci_discovery_models import (
    OciDiscoveredResource,
    OciDiscoveryIssue,
    OciDiscoveryResult,
)
from app.services.oci_inventory_adapter import adapt_oci_inventory


class AwsApiError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.response = {"Error": {"Code": code, "Message": "do not persist raw sdk detail"}}


class FakePaginator:
    def __init__(self, pages, *, fail_after=None, code="RequestTimeout"):
        self.pages = list(pages)
        self.fail_after = fail_after
        self.code = code

    def paginate(self):
        for index, page in enumerate(self.pages):
            if self.fail_after is not None and index >= self.fail_after:
                raise AwsApiError(self.code)
            yield page
        if self.fail_after is not None and self.fail_after >= len(self.pages):
            raise AwsApiError(self.code)


class FakeEc2Client:
    def __init__(self, *, instance_pages=None, volume_pages=None, addresses=None, failures=None):
        self.instance_pages = instance_pages or [{"Reservations": []}]
        self.volume_pages = volume_pages or [{"Volumes": []}]
        self.addresses = addresses if addresses is not None else []
        self.failures = failures or {}

    def get_paginator(self, operation):
        failure = self.failures.get(operation)
        if operation == "describe_instances":
            return FakePaginator(self.instance_pages, **(failure or {}))
        if operation == "describe_volumes":
            return FakePaginator(self.volume_pages, **(failure or {}))
        raise AssertionError(operation)

    def describe_addresses(self):
        failure = self.failures.get("describe_addresses")
        if failure:
            raise AwsApiError(failure["code"])
        return {"Addresses": self.addresses}


class FakeRdsClient:
    def __init__(self, *, pages=None, failure=None):
        self.pages = pages or [{"DBInstances": []}]
        self.failure = failure

    def get_paginator(self, operation):
        assert operation == "describe_db_instances"
        return FakePaginator(self.pages, **(self.failure or {}))


class FakeSession:
    def __init__(self, clients):
        self.clients = clients

    def client(self, service, *, region_name):
        return self.clients[(service, region_name)]


def _coverage(result, resource_type, region):
    return next(
        item
        for item in result.coverage
        if item.resource_type == resource_type and item.region == region
    )


def test_aws_wave1_maps_fields_uses_stable_ids_and_paginates():
    launched = datetime(2026, 10, 1, 10, tzinfo=UTC)
    ec2 = FakeEc2Client(
        instance_pages=[
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-1",
                                "State": {"Name": "running"},
                                "InstanceType": "m7i.large",
                                "Architecture": "x86_64",
                                "PlatformDetails": "Linux/UNIX",
                                "LaunchTime": launched,
                                "Placement": {"AvailabilityZone": "us-east-1a"},
                                "VpcId": "vpc-1",
                                "SubnetId": "subnet-1",
                                "PrivateIpAddress": "10.0.0.1",
                                "Tags": [{"Key": "Environment", "Value": "prod"}],
                            }
                        ]
                    }
                ]
            },
            {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-2",
                                "State": {"Name": "stopped"},
                                "Tags": [{"Key": "Name", "Value": "batch"}],
                            }
                        ]
                    }
                ]
            },
        ],
        volume_pages=[
            {
                "Volumes": [
                    {
                        "VolumeId": "vol-1",
                        "State": "in-use",
                        "AvailabilityZone": "us-east-1a",
                        "VolumeType": "gp3",
                        "Size": 100,
                        "Iops": 3000,
                        "Throughput": 125,
                        "Encrypted": True,
                        "MultiAttachEnabled": False,
                        "Attachments": [
                            {
                                "InstanceId": "i-1",
                                "Device": "/dev/xvda",
                                "State": "attached",
                                "AttachTime": launched,
                                "DeleteOnTermination": True,
                            }
                        ],
                        "Tags": [{"Key": "Name", "Value": "data"}],
                    }
                ]
            },
            {"Volumes": [{"VolumeId": "vol-2", "State": "available"}]},
        ],
        addresses=[
            {
                "AllocationId": "eipalloc-1",
                "PublicIp": "203.0.113.10",
                "AssociationId": "eipassoc-1",
                "NetworkInterfaceId": "eni-1",
                "InstanceId": "i-1",
                "Domain": "vpc",
            },
            {"AllocationId": "eipalloc-2", "PublicIp": "203.0.113.11", "Domain": "vpc"},
        ],
    )
    rds = FakeRdsClient(
        pages=[
            {
                "DBInstances": [
                    {
                        "DBInstanceIdentifier": "orders",
                        "DBInstanceArn": "arn:aws:rds:us-east-1:123456789012:db:orders",
                        "DBInstanceStatus": "available",
                        "Engine": "postgres",
                        "EngineVersion": "16.3",
                        "DBInstanceClass": "db.r6g.large",
                        "MultiAZ": True,
                        "StorageType": "gp3",
                        "AllocatedStorage": 200,
                        "AvailabilityZone": "us-east-1b",
                        "Endpoint": {"Address": "orders.example", "Port": 5432},
                        "LicenseModel": "postgresql-license",
                    }
                ]
            },
            {"DBInstances": []},
        ]
    )
    result = AwsInventoryDiscoveryService().discover(
        FakeSession({("ec2", "us-east-1"): ec2, ("rds", "us-east-1"): rds}),
        cloud_account_id=7,
        regions=["us-east-1"],
    )

    assert result.resources_analyzed == 7
    assert all(item.status == InventoryCoverageStatus.COMPLETE for item in result.coverage)
    by_id = {item.resource_id: item for item in result.resources}
    assert by_id["i-1"].name is None
    assert by_id["i-1"].attributes["launch_time"] == launched.isoformat()
    assert by_id["i-2"].name == "batch"
    assert by_id["vol-1"].availability_zone == "us-east-1a"
    assert by_id["vol-1"].attributes["attachments"][0]["instance_id"] == "i-1"
    assert by_id["eipalloc-1"].attributes["public_ip"] == "203.0.113.10"
    assert "203.0.113.10" not in {item.resource_id for item in result.resources}
    database = by_id["arn:aws:rds:us-east-1:123456789012:db:orders"]
    assert database.name == "orders"
    assert database.lifecycle_status == "running"
    assert database.native_status == "available"


def test_aws_failure_is_isolated_by_region_and_resource_type_and_empty_success_is_complete():
    east_ec2 = FakeEc2Client()
    west_ec2 = FakeEc2Client()
    east_rds = FakeRdsClient()
    west_rds = FakeRdsClient(failure={"fail_after": 0, "code": "AccessDenied"})
    result = AwsInventoryDiscoveryService().discover(
        FakeSession(
            {
                ("ec2", "us-east-1"): east_ec2,
                ("rds", "us-east-1"): east_rds,
                ("ec2", "us-west-2"): west_ec2,
                ("rds", "us-west-2"): west_rds,
            }
        ),
        cloud_account_id=9,
        regions=["us-east-1", "us-west-2"],
    )

    assert result.resources_analyzed == 0
    assert _coverage(result, "compute_instance", "us-east-1").status == "complete"
    assert _coverage(result, "compute_instance", "us-west-2").status == "complete"
    assert _coverage(result, "relational_database", "us-east-1").status == "complete"
    failed = _coverage(result, "relational_database", "us-west-2")
    assert failed.status == "failed"
    assert failed.error_code == "AccessDenied"
    assert len(result.errors) == 1


def test_aws_paginator_failure_after_page_is_partial_and_preserves_observed_resources():
    ec2 = FakeEc2Client(
        instance_pages=[
            {
                "Reservations": [
                    {"Instances": [{"InstanceId": "i-observed", "State": {"Name": "running"}}]}
                ]
            }
        ],
        failures={"describe_instances": {"fail_after": 1, "code": "RequestTimeout"}},
    )
    result = AwsInventoryDiscoveryService().discover(
        FakeSession(
            {
                ("ec2", "us-east-1"): ec2,
                ("rds", "us-east-1"): FakeRdsClient(),
            }
        ),
        cloud_account_id=11,
        regions=["us-east-1"],
    )

    coverage = _coverage(result, "compute_instance", "us-east-1")
    assert coverage.status == "partial"
    assert coverage.error_code == "RequestTimeout"
    assert {item.resource_id for item in result.resources} == {"i-observed"}
    assert result.resources_analyzed == 1


def _oci_resource(resource_type: str, suffix: str, lifecycle: str):
    return OciDiscoveredResource(
        provider="oci",
        resource_id=f"ocid1.{suffix}.example",
        resource_type=resource_type,
        name=f"{resource_type}-{suffix}",
        region="sa-saopaulo-1",
        compartment_id="ocid1.compartment.example",
        lifecycle_state=lifecycle,
        availability_domain="kIdk:SA-SAOPAULO-1-AD-1",
        freeform_tags={"Team": "platform"},
        defined_tags={"Operations": {"CostCenter": "42"}},
        sources=["wave1_api"],
        attributes={"shape": "VM.Standard.E5.Flex"},
    )


def test_oci_adapter_maps_existing_wave1_without_second_discovery_and_preserves_native_data():
    now = datetime.now(UTC)
    resources = [
        _oci_resource("compute_instance", "instance", "RUNNING"),
        _oci_resource("block_volume", "volume", "AVAILABLE"),
        _oci_resource("boot_volume", "bootvolume", "AVAILABLE"),
        _oci_resource("public_ip", "publicip", "ASSIGNED"),
    ]
    result = adapt_oci_inventory(
        OciDiscoveryResult(
            status="success",
            resources=resources,
            relationships=[],
            regions_scanned=("sa-saopaulo-1",),
            compartments_scanned=("ocid1.compartment.example",),
            observed_counts_by_type={item.resource_type: 1 for item in resources},
            counts_by_type={item.resource_type: 1 for item in resources},
            warnings=[],
            errors=[],
            started_at=now,
            completed_at=now,
        ),
        cloud_account_id=17,
    )

    assert result.resources_analyzed == 4
    assert all(item.status == "complete" for item in result.coverage)
    compute = next(item for item in result.resources if item.resource_type == "compute_instance")
    assert compute.native_status == "RUNNING"
    assert compute.lifecycle_status == "running"
    assert compute.availability_zone == "kIdk:SA-SAOPAULO-1-AD-1"
    assert compute.tags["freeform"] == {"Team": "platform"}
    assert compute.tags["defined"]["Operations"]["CostCenter"] == "42"
    assert compute.attributes["compartment_id"] == "ocid1.compartment.example"
    assert compute.attributes["sources"] == ["wave1_api"]


def test_oci_incomplete_resource_type_never_becomes_complete_coverage():
    now = datetime.now(UTC)
    issue = OciDiscoveryIssue(
        category="authorization",
        source="compute_api",
        operation="list_instances",
        message="not authorized",
        region="sa-saopaulo-1",
        compartment_id="ocid1.compartment.example",
        resource_type="compute_instance",
        fatal=False,
    )
    discovery = OciDiscoveryResult(
        status="partial",
        resources=[],
        relationships=[],
        regions_scanned=("sa-saopaulo-1",),
        compartments_scanned=("ocid1.compartment.example",),
        observed_counts_by_type={
            "compute_instance": 0,
            "block_volume": 0,
            "boot_volume": 0,
            "public_ip": 0,
        },
        counts_by_type={
            "compute_instance": None,
            "block_volume": 0,
            "boot_volume": 0,
            "public_ip": 0,
        },
        warnings=[],
        errors=[issue],
        started_at=now,
        completed_at=now,
    )
    result = adapt_oci_inventory(discovery, cloud_account_id=19)

    assert _coverage(result, "compute_instance", "sa-saopaulo-1").status == "failed"
    assert _coverage(result, "block_volume", "sa-saopaulo-1").status == "complete"
    assert len(result.errors) == 1
    assert "not authorized" not in result.errors[0].message
