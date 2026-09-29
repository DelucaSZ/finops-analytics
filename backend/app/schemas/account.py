from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.cloud import CloudProvider, normalize_provider, validate_native_account_id

AWS_ROLE_PATTERN = r"^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/.+$"


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
    configuration: AwsAccountConfigurationCreate | None = None

    @model_validator(mode="after")
    def provider_configuration(self):
        if self.provider == CloudProvider.AWS.value:
            if self.configuration is None:
                raise ValueError("AWS configuration is required")
            role_account_id = self.configuration.role_arn.split(":")[4]
            if role_account_id != self.native_account_id:
                raise ValueError("Role ARN account does not match native account identifier")
        elif self.configuration is not None:
            raise ValueError("AWS configuration is not valid for this provider")
        return self


class CloudAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=120)
    enabled: bool | None = None
    configuration: AwsAccountConfigurationUpdate | None = None


class CloudAccountRead(CloudAccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_status: str
    last_connection_test_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    aws_configuration: AwsAccountConfigurationRead | None = None


class ConnectionTestResult(BaseModel):
    ok: bool
    expected_account_id: str
    caller_account_id: str | None = None
    caller_arn: str | None = None
    error: str | None = None
