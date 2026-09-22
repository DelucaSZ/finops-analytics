from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AccountBase(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    aws_account_id: str = Field(pattern=r"^[0-9]{12}$")
    role_arn: str = Field(pattern=r"^arn:(aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/.+$")
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
    role_arn: str | None = None
    external_id: str | None = Field(default=None, min_length=16, max_length=255)
    regions: list[str] | None = None
    enabled: bool | None = None
    is_management_account: bool | None = None
    schedule_enabled: bool | None = None
    scan_interval_hours: int | None = Field(default=None, ge=1, le=720)


class AccountRead(AccountBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connection_status: str
    last_connection_test_at: datetime | None
    last_error: str | None
    next_scan_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ConnectionTestResult(BaseModel):
    ok: bool
    expected_account_id: str
    caller_account_id: str | None = None
    caller_arn: str | None = None
    error: str | None = None
