from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class OciOperatingSystemFamily(StrEnum):
    WINDOWS = "windows"
    NON_WINDOWS = "non_windows"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OciOperatingSystemResolution:
    family: OciOperatingSystemFamily
    source: str
    raw_value: str | None = None
    version: str | None = None


_WINDOWS_VALUES = ("windows", "microsoft windows")
_NON_WINDOWS_PREFIXES = (
    "oracle linux",
    "ubuntu",
    "centos",
    "rocky linux",
    "almalinux",
    "red hat enterprise linux",
    "red hat",
    "rhel",
    "debian",
    "suse",
    "fedora",
)


def resolve_operating_system(
    operating_system: Any,
    *,
    version: Any = None,
    source: str = "oci_image_metadata",
) -> OciOperatingSystemResolution:
    """Resolve structured OCI image OS metadata without resource-name heuristics."""

    raw_value = str(operating_system).strip() if operating_system is not None else ""
    raw_version = str(version).strip() if version is not None else ""
    if not raw_value:
        return OciOperatingSystemResolution(
            family=OciOperatingSystemFamily.UNKNOWN,
            source="missing_image_metadata",
            version=raw_version or None,
        )

    normalized = " ".join(raw_value.casefold().split())
    if any(normalized == value or normalized.startswith(f"{value} ") for value in _WINDOWS_VALUES):
        family = OciOperatingSystemFamily.WINDOWS
    elif any(
        normalized == value or normalized.startswith(f"{value} ") for value in _NON_WINDOWS_PREFIXES
    ):
        family = OciOperatingSystemFamily.NON_WINDOWS
    else:
        family = OciOperatingSystemFamily.UNKNOWN

    resolved_source = (
        source if family is not OciOperatingSystemFamily.UNKNOWN else "unrecognized_image_metadata"
    )
    return OciOperatingSystemResolution(
        family=family,
        source=resolved_source,
        raw_value=raw_value,
        version=raw_version or None,
    )


class OciImageOperatingSystemResolver:
    """Resolve OCI image metadata with a collection-local cache keyed by region/image OCID."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], OciOperatingSystemResolution] = {}

    def resolve(
        self,
        *,
        compute_client: Any,
        region: str,
        image_id: str | None,
        cloud_account_id: str | None = None,
        compartment_id: str | None = None,
        instance_id: str | None = None,
    ) -> OciOperatingSystemResolution:
        if not image_id:
            return OciOperatingSystemResolution(
                family=OciOperatingSystemFamily.UNKNOWN,
                source="missing_image_id",
            )

        key = (region, image_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        try:
            response = compute_client.get_image(image_id)
            image = getattr(response, "data", None)
            if image is None:
                resolution = OciOperatingSystemResolution(
                    family=OciOperatingSystemFamily.UNKNOWN,
                    source="missing_image_metadata",
                )
            else:
                resolution = resolve_operating_system(
                    getattr(image, "operating_system", None),
                    version=getattr(image, "operating_system_version", None),
                )
        except Exception as exc:  # OCI SDK exceptions vary by transport/service failure.
            logger.warning(
                "OCI image OS lookup failed cloud_account_id=%s region=%s compartment_id=%s "
                "instance_id=%s image_id=%s error_type=%s",
                cloud_account_id,
                region,
                compartment_id,
                instance_id,
                image_id,
                type(exc).__name__,
            )
            resolution = OciOperatingSystemResolution(
                family=OciOperatingSystemFamily.UNKNOWN,
                source="image_lookup_failed",
            )

        self._cache[key] = resolution
        return resolution
