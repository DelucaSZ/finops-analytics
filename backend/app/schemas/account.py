import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.cloud import (
    CloudProvider,
    normalize_provider,
    validate_native_account_id,
    validate_oci_ocid,
)

AWS_ROLE_PATTERN = r"^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/.+$"
OCI_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{32}$")
OCI_REGION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")


def _normalize_oci_fingerprint(value: str) -> str:
    compact = value.strip().lower().replace(":", "")
    if not OCI_FINGERPRINT_PATTERN.fullmatch(compact):
        raise ValueError("OCI fingerprint must contain 16 hexadecimal bytes")
    return ":".join(compact[index : index + 2] for index in range(0, 32, 2))


def _normalize_oci_region(value: str) -> str:
    region = value.strip().lower()
    if not OCI_REGION_PATTERN.fullmatch(region):
        raise ValueError("OCI region is invalid")
    return region


def _unique_oci_regions(regions: list[str]) -> list[str]:
    return list(dict.fromkeys(_normalize_oci_region(region) for region in regions))


def _unique_compartments(compartments: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            validate_oci_ocid(compartment.strip(), "compartment")
            for compartment in compartments
        )
    )


class AccountBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    aws_account_id: str = Field(pattern=r"^[0-9]{12}$")
    role_arn: str = Field(pattern=AWS_ROLE_PATTERN)
    external_id: str = Field(min_length=16, max_length=255)
    regions: list[str] = Field(default_factory=lambda: ["sa-east-1"], min_length=1)
    enabled: bool = True
    is_management_account: bool = False
    schedule_enabled: bool = False
    scan_interval_hours: int = Field(default=24, ge=1, le=720)

    @field_validator("regions")
    @classmethod
    def unique_regions(cls, regions: list[str]) -> list[str]:
        return list(dict.fromkeys(region.strip() for region in regions if region.strip()))


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role_arn: str | None = Field(default=None, pattern=AWS_ROLE_PATTERN)
    external_id: str | None = Field(default=None, min_length=16, max_length=255)
    regions: list[str] | None = None
    enabled: bool | None = None
    is_management_account: bool | None = None
    schedule_enabled: bool | None = None
    scan_interval_hours: int | None = Field(default=None, ge=1, le=720)

    @field_validator("regions")
    @classmethod
    def unique_regions(cls, regions: list[str] | None) -> list[str] | None:
        if regions is None:
            return None
        return list(dict.fromkeys(region.strip() for region in regions if region.strip()))


class AccountRead(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_status: str
    last_connection_test_at: datetime | None
    last_error: str | None
    next_scan_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AwsAccountConfigurationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_arn: str = Field(pattern=AWS_ROLE_PATTERN)
    external_id: str = Field(min_length=16, max_length=255)
    regions: list[str] = Field(default_factory=lambda: ["sa-east-1"], min_length=1)
    is_management_account: bool = False
    schedule_enabled: bool = False
    scan_interval_hours: int = Field(default=24, ge=1, le=720)

    @field_validator("regions")
    @classmethod
    def unique_regions(cls, regions: list[str]) -> list[str]:
        return list(dict.fromkeys(region.strip() for region in regions if region.strip()))


class AwsAccountConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_arn: str | None = Field(default=None, pattern=AWS_ROLE_PATTERN)
    external_id: str | None = Field(default=None, min_length=16, max_length=255)
    regions: list[str] | None = None
    is_management_account: bool | None = None
    schedule_enabled: bool | None = None
    scan_interval_hours: int | None = Field(default=None, ge=1, le=720)

    @field_validator("regions")
    @classmethod
    def unique_regions(cls, regions: list[str] | None) -> list[str] | None:
        if regions is None:
            return None
        return list(dict.fromkeys(region.strip() for region in regions if region.strip()))


class AwsAccountConfigurationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_arn: str
    external_id: str
    regions: list[str]
    is_management_account: bool
    schedule_enabled: bool
    scan_interval_hours: int
    next_scan_at: datetime | None
    created_at: datetime
    updated_at: datetime


class OciAccountConfigurationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ocid: str = Field(min_length=1, max_length=255)
    fingerprint: str = Field(min_length=1, max_length=64)
    region: str = Field(min_length=3, max_length=64)
    scope_regions: list[str] = Field(default_factory=list)
    compartment_ocids: list[str] = Field(default_factory=list)
    include_root_compartment: bool = False
    include_subcompartments: bool = False
    private_key_pem: str = Field(min_length=64, max_length=65536)
    private_key_password: str | None = Field(default=None, max_length=1024)

    @field_validator("user_ocid")
    @classmethod
    def valid_user_ocid(cls, value: str) -> str:
        return validate_oci_ocid(value, "user")

    @field_validator("fingerprint")
    @classmethod
    def valid_fingerprint(cls, value: str) -> str:
        return _normalize_oci_fingerprint(value)

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str) -> str:
        return _normalize_oci_region(value)

    @field_validator("scope_regions")
    @classmethod
    def valid_scope_regions(cls, value: list[str]) -> list[str]:
        return _unique_oci_regions(value)

    @field_validator("compartment_ocids")
    @classmethod
    def valid_compartments(cls, value: list[str]) -> list[str]:
        return _unique_compartments(value)

    @field_validator("private_key_password")
    @classmethod
    def non_empty_password(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("OCI private key password cannot be empty")
        return value

    @model_validator(mode="after")
    def valid_scope(self):
        if self.include_subcompartments and not (
            self.include_root_compartment or self.compartment_ocids
        ):
            raise ValueError(
                "include_subcompartments requires the tenancy root or at least one compartment"
            )
        return self


class OciAccountConfigurationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_ocid: str | None = Field(default=None, min_length=1, max_length=255)
    fingerprint: str | None = Field(default=None, min_length=1, max_length=64)
    region: str | None = Field(default=None, min_length=3, max_length=64)
    scope_regions: list[str] | None = None
    compartment_ocids: list[str] | None = None
    include_root_compartment: bool | None = None
    include_subcompartments: bool | None = None
    private_key_pem: str | None = Field(default=None, max_length=65536)
    private_key_password: str | None = Field(default=None, max_length=1024)
    remove_credentials: bool = False

    @field_validator("user_ocid")
    @classmethod
    def valid_user_ocid(cls, value: str | None) -> str | None:
        return validate_oci_ocid(value, "user") if value is not None else None

    @field_validator("fingerprint")
    @classmethod
    def valid_fingerprint(cls, value: str | None) -> str | None:
        return _normalize_oci_fingerprint(value) if value is not None else None

    @field_validator("region")
    @classmethod
    def valid_region(cls, value: str | None) -> str | None:
        return _normalize_oci_region(value) if value is not None else None

    @field_validator("scope_regions")
    @classmethod
    def valid_scope_regions(cls, value: list[str] | None) -> list[str] | None:
        return _unique_oci_regions(value) if value is not None else None

    @field_validator("compartment_ocids")
    @classmethod
    def valid_compartments(cls, value: list[str] | None) -> list[str] | None:
        return _unique_compartments(value) if value is not None else None

    @field_validator("private_key_pem")
    @classmethod
    def non_empty_key(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("OCI private key PEM cannot be empty")
        return value

    @field_validator("private_key_password")
    @classmethod
    def non_empty_password(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("OCI private key password cannot be empty")
        return value

    @model_validator(mode="after")
    def explicit_credential_semantics(self):
        fields = self.model_fields_set
        replacing = "private_key_pem" in fields
        changing_password = "private_key_password" in fields
        changing_fingerprint = "fingerprint" in fields
        if self.remove_credentials and (replacing or changing_password or changing_fingerprint):
            raise ValueError(
                "remove_credentials cannot be combined with OCI credential replacement fields"
            )
        if changing_password and not replacing:
            raise ValueError("OCI key passphrase can only change together with a new private key")
        if changing_fingerprint and not replacing:
            raise ValueError("OCI fingerprint can only change together with a new private key")
        return self


class OciAccountConfigurationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_ocid: str
    fingerprint: str
    region: str
    scope_regions: list[str]
    compartment_ocids: list[str]
    include_root_compartment: bool
    include_subcompartments: bool
    credentials_configured: bool
    credential_key_version: str | None
    credential_revision: int
    configuration_revision: int
    created_at: datetime
    updated_at: datetime


class CloudAccountBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=2, max_length=16)
    native_account_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=2, max_length=120)
    enabled: bool = True

    @field_validator("provider")
    @classmethod
    def canonical_provider(cls, provider: str) -> str:
        return normalize_provider(provider)

    @model_validator(mode="after")
    def provider_specific_identity(self):
        validate_native_account_id(self.provider, self.native_account_id)
        return self


class CloudAccountCreate(CloudAccountBase):
    configuration: AwsAccountConfigurationCreate | OciAccountConfigurationCreate | None = None

    @model_validator(mode="after")
    def provider_configuration(self):
        if self.provider == CloudProvider.AWS.value:
            if not isinstance(self.configuration, AwsAccountConfigurationCreate):
                raise ValueError("AWS configuration is required")
            role_account_id = self.configuration.role_arn.split(":")[4]
            if role_account_id != self.native_account_id:
                raise ValueError("Role ARN account does not match native account identifier")
        elif self.provider == CloudProvider.OCI.value:
            if not isinstance(self.configuration, OciAccountConfigurationCreate):
                raise ValueError("OCI configuration is required")
        elif self.configuration is not None:
            raise ValueError("Provider-specific configuration is not valid for this provider")
        return self


class CloudAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    enabled: bool | None = None
    configuration: AwsAccountConfigurationUpdate | OciAccountConfigurationUpdate | None = None


class CloudAccountRead(CloudAccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_status: str
    last_connection_test_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    aws_configuration: AwsAccountConfigurationRead | None = None
    oci_configuration: OciAccountConfigurationRead | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    expected_account_id: str
    provider: str = CloudProvider.AWS.value
    caller_account_id: str | None = None
    caller_arn: str | None = None
    error_code: str | None = None
    error: str | None = None
    verified_checks: list[str] = Field(default_factory=list)


class CloudAccountAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: int | None
    provider: str
    native_account_id: str
    actor_id: str | None
    action: str
    result: str
    detail: str
    created_at: datetime
