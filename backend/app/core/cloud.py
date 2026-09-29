import re
from enum import StrEnum


class CloudProvider(StrEnum):
    AWS = "aws"
    OCI = "oci"
    AZURE = "azure"
    GCP = "gcp"


PROVIDER_LABELS: dict[CloudProvider, str] = {
    CloudProvider.AWS: "AWS",
    CloudProvider.OCI: "OCI",
    CloudProvider.AZURE: "Azure",
    CloudProvider.GCP: "GCP",
}


def normalize_provider(value: str | CloudProvider) -> str:
    """Return the canonical provider key and reject unknown provider names."""
    return CloudProvider(str(value).strip().lower()).value


def validate_oci_ocid(value: str, resource_type: str) -> str:
    """Validate OCI OCID structure without assuming realm, region or identifier length."""
    if value != value.strip() or not value:
        raise ValueError(f"OCI {resource_type} OCID must not contain surrounding whitespace")
    if len(value) > 255:
        raise ValueError(f"OCI {resource_type} OCID is too long")
    parts = value.split(".")
    if len(parts) < 5 or parts[0] != "ocid1" or parts[1] != resource_type:
        raise ValueError(f"Expected an OCI {resource_type} OCID")
    if not parts[2] or not parts[-1]:
        raise ValueError(f"OCI {resource_type} OCID is structurally invalid")
    allowed = re.compile(r"^[A-Za-z0-9_-]*$")
    if any(not allowed.fullmatch(part) for part in parts[2:]):
        raise ValueError(f"OCI {resource_type} OCID contains invalid characters")
    return value


def validate_native_account_id(provider: str | CloudProvider, value: str) -> str:
    """Validate a provider-native account identifier without changing its case."""
    provider_key = normalize_provider(provider)
    if value != value.strip():
        raise ValueError("Native account identifier must not contain surrounding whitespace")
    if not value or len(value) > 255:
        raise ValueError("Native account identifier must contain between 1 and 255 characters")
    if provider_key == CloudProvider.AWS.value and not re.fullmatch(r"[0-9]{12}", value):
        raise ValueError("AWS account identifier must contain exactly 12 digits")
    if provider_key == CloudProvider.OCI.value:
        validate_oci_ocid(value, "tenancy")
    return value


def provider_label(value: str | CloudProvider) -> str:
    provider = CloudProvider(normalize_provider(value))
    return PROVIDER_LABELS[provider]
