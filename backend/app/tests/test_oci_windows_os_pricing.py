from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.oci_compute_os_pricing import OciComputeOsPricingService
from app.services.oci_inventory import _compute_resource, _instance_image_id
from app.services.oci_os import (
    OciImageOperatingSystemResolver,
    OciOperatingSystemFamily,
    OciOperatingSystemResolution,
    resolve_operating_system,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Windows", OciOperatingSystemFamily.WINDOWS),
        ("Microsoft Windows", OciOperatingSystemFamily.WINDOWS),
        ("Windows Server 2022", OciOperatingSystemFamily.WINDOWS),
        ("Oracle Linux", OciOperatingSystemFamily.NON_WINDOWS),
        ("Ubuntu", OciOperatingSystemFamily.NON_WINDOWS),
    ],
)
def test_structured_image_os_metadata_resolves_explicit_families(raw, expected):
    resolution = resolve_operating_system(raw)
    assert resolution.family is expected
    assert resolution.raw_value == raw
    assert resolution.source == "oci_image_metadata"


def test_missing_or_unrecognized_image_metadata_remains_unknown():
    missing = resolve_operating_system(None)
    custom = resolve_operating_system("Custom Appliance OS")

    assert missing.family is OciOperatingSystemFamily.UNKNOWN
    assert missing.source == "missing_image_metadata"
    assert custom.family is OciOperatingSystemFamily.UNKNOWN
    assert custom.source == "unrecognized_image_metadata"


def test_instance_name_tags_and_shape_do_not_control_os_resolution():
    item = SimpleNamespace(
        id="instance-1",
        display_name="windows-server-prod",
        shape="VM.Standard.E4.Flex",
        shape_config=SimpleNamespace(ocpus=4, memory_in_gbs=64),
        fault_domain=None,
        time_created=None,
        compartment_id="compartment-1",
        lifecycle_state="RUNNING",
        availability_domain="AD-1",
        freeform_tags={"OS": "Windows"},
        defined_tags={},
    )
    resource = _compute_resource(item, "sa-saopaulo-1")
    assert resource is not None

    linux = resolve_operating_system("Oracle Linux")
    assert linux.family is OciOperatingSystemFamily.NON_WINDOWS
    assert resource.name == "windows-server-prod"
    assert resource.attributes["shape"] == "VM.Standard.E4.Flex"


def test_instance_image_id_prefers_structured_image_source():
    item = SimpleNamespace(
        image_id="legacy-image",
        source_details=SimpleNamespace(source_type="image", image_id="source-image"),
    )
    assert _instance_image_id(item) == "source-image"


def test_instance_without_reliable_image_id_remains_without_image_reference():
    item = SimpleNamespace(
        image_id=None,
        source_details=SimpleNamespace(source_type="bootVolume", boot_volume_id="boot-1"),
    )
    assert _instance_image_id(item) is None


class _ImageClient:
    def __init__(self, operating_system="Windows", version="2022", failure=None):
        self.operating_system = operating_system
        self.version = version
        self.failure = failure
        self.calls = 0

    def get_image(self, image_id):
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(
            data=SimpleNamespace(
                id=image_id,
                display_name="custom-name-does-not-matter",
                operating_system=self.operating_system,
                operating_system_version=self.version,
            )
        )


def test_image_metadata_lookup_is_cached_per_region_and_image_id():
    client = _ImageClient()
    resolver = OciImageOperatingSystemResolver()

    first = resolver.resolve(
        compute_client=client,
        region="sa-saopaulo-1",
        image_id="image-1",
        instance_id="instance-1",
    )
    second = resolver.resolve(
        compute_client=client,
        region="sa-saopaulo-1",
        image_id="image-1",
        instance_id="instance-2",
    )

    assert first == second
    assert first.family is OciOperatingSystemFamily.WINDOWS
    assert first.version == "2022"
    assert client.calls == 1


def test_image_lookup_failure_is_unknown_and_does_not_raise():
    client = _ImageClient(failure=RuntimeError("OCI unavailable"))
    resolver = OciImageOperatingSystemResolver()

    resolution = resolver.resolve(
        compute_client=client,
        region="sa-saopaulo-1",
        image_id="image-1",
        instance_id="instance-1",
    )

    assert resolution.family is OciOperatingSystemFamily.UNKNOWN
    assert resolution.source == "image_lookup_failed"
    assert client.calls == 1


def _os(family):
    return OciOperatingSystemResolution(
        family=family,
        source="oci_image_metadata",
        raw_value=("Windows" if family is OciOperatingSystemFamily.WINDOWS else "Oracle Linux"),
    )


def test_e4_windows_compute_adds_exact_catalog_license_component():
    service = OciComputeOsPricingService()
    windows = service.price(
        shape="VM.Standard.E4.Flex",
        ocpus=Decimal("4"),
        memory_gb=Decimal("64"),
        operating_system=_os(OciOperatingSystemFamily.WINDOWS),
    )
    non_windows = service.price(
        shape="VM.Standard.E4.Flex",
        ocpus=Decimal("4"),
        memory_gb=Decimal("64"),
        operating_system=_os(OciOperatingSystemFamily.NON_WINDOWS),
    )

    assert windows.compute_base_monthly_cost == Decimal("400.27")
    assert windows.windows_monthly_cost == Decimal("1371.70")
    assert windows.total_monthly_cost == Decimal("1771.97")
    assert windows.windows_license_included is True
    assert non_windows.total_monthly_cost == Decimal("400.27")
    assert non_windows.windows_monthly_cost == Decimal("0.00")
    assert non_windows.windows_license_included is False
    assert windows.total_monthly_cost > non_windows.total_monthly_cost
    assert windows.total_monthly_cost - non_windows.total_monthly_cost == Decimal("1371.70")


def test_unknown_os_keeps_base_compute_and_excludes_windows():
    service = OciComputeOsPricingService()
    unknown = service.price(
        shape="VM.Standard.E4.Flex",
        ocpus=4,
        memory_gb=64,
        operating_system=OciOperatingSystemResolution(
            family=OciOperatingSystemFamily.UNKNOWN,
            source="missing_image_metadata",
        ),
    )

    assert unknown.compute_base_monthly_cost == Decimal("400.27")
    assert unknown.total_monthly_cost == Decimal("400.27")
    assert unknown.windows_monthly_cost == Decimal("0.00")
    assert unknown.windows_license_included is False
    assert unknown.os_pricing_status == "unknown_os"
