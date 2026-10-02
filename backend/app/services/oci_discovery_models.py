from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.cloud import CloudProvider

WAVE1_RESOURCE_TYPES = (
    "compute_instance",
    "block_volume",
    "boot_volume",
    "public_ip",
)


@dataclass(frozen=True)
class OciDiscoveryScope:
    regions: tuple[str, ...]
    compartment_ids: tuple[str, ...]
    include_root_compartment: bool
    include_subcompartments: bool
    complete: bool = True


@dataclass
class OciDiscoveredResource:
    provider: str
    resource_id: str
    resource_type: str
    name: str | None = None
    region: str | None = None
    compartment_id: str | None = None
    lifecycle_state: str | None = None
    availability_domain: str | None = None
    freeform_tags: dict[str, str] = field(default_factory=dict)
    defined_tags: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider != CloudProvider.OCI.value:
            raise ValueError("OCI discovery resources must use provider=oci")


@dataclass(frozen=True)
class OciResourceRelationship:
    relation_type: str
    source_id: str
    target_id: str
    source_type: str
    target_type: str


@dataclass(frozen=True)
class OciDiscoveryIssue:
    category: str
    source: str
    operation: str
    message: str
    region: str | None = None
    compartment_id: str | None = None
    resource_type: str | None = None
    fatal: bool = False


@dataclass
class OciDiscoveryResult:
    status: str
    resources: list[OciDiscoveredResource]
    relationships: list[OciResourceRelationship]
    regions_scanned: tuple[str, ...]
    compartments_scanned: tuple[str, ...]
    observed_counts_by_type: dict[str, int]
    counts_by_type: dict[str, int | None]
    warnings: list[OciDiscoveryIssue]
    errors: list[OciDiscoveryIssue]
    started_at: datetime
    completed_at: datetime

    @property
    def is_partial(self) -> bool:
        return self.status == "partial"

    @property
    def is_failed(self) -> bool:
        return self.status == "failed"
