"""Typed, side-effect-free API contracts for the future Cloud Cost Calculator.

Task 27.1 defines contracts only; price selection and duration metering belong to 27.2+.
All monetary amounts are Decimals. Missing prices must remain nullable, never zero-filled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CalculatorPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["monthly", "hours", "days", "weeks", "custom"] = "monthly"
    amount: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def validate_period(self) -> CalculatorPeriod:
        if self.mode in {"hours", "days", "weeks"}:
            if self.amount is None or self.start_at is not None or self.end_at is not None:
                raise ValueError("duration periods require amount and no date range")
            seconds = (
                self.amount
                * {
                    "hours": Decimal(3600),
                    "days": Decimal(86400),
                    "weeks": Decimal(604800),
                }[self.mode]
            )
            if seconds > Decimal(5 * 366 * 86400):
                raise ValueError("duration exceeds five-year simulation limit")
        elif self.mode == "custom":
            if self.amount is not None or self.start_at is None or self.end_at is None:
                raise ValueError("custom period requires start_at and end_at only")
            if self.start_at.utcoffset() is None or self.end_at.utcoffset() is None:
                raise ValueError("custom period datetimes must be timezone-aware")
            elapsed = self.end_at.astimezone(UTC) - self.start_at.astimezone(UTC)
            if elapsed.total_seconds() <= 0:
                raise ValueError("end_at must be after start_at")
            if elapsed.days > 5 * 366 or (
                elapsed.days == 5 * 366 and (elapsed.seconds or elapsed.microseconds)
            ):
                raise ValueError("date range exceeds five-year simulation limit")
        elif self.amount is not None or self.start_at is not None or self.end_at is not None:
            raise ValueError("monthly period cannot specify a duration or date range")
        return self


class AwsEc2Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["ec2"] = "ec2"
    instance_type: str | None = None
    operating_system: str | None = None
    tenancy: str | None = None
    purchase_option: str | None = None
    root_volume_gb: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    ebs_volume_type: Literal["gp2", "gp3"] = "gp3"
    ebs_volume_count: int = Field(default=1, ge=1, le=100)
    ebs_iops: int | None = Field(default=None, ge=3000, le=80000)
    ebs_throughput_mbps: int | None = Field(default=None, ge=125, le=2000)


class AwsRdsConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["rds"] = "rds"
    instance_class: str | None = None
    engine: str | None = None
    deployment: str | None = None
    storage_type: str | None = None
    allocated_storage_gb: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    provisioned_iops: int | None = Field(default=None, ge=0)
    provisioned_throughput_mbps: int | None = Field(default=None, ge=0)
    database_edition: str | None = None
    license_model: str | None = None


class OciVolumeConfiguration(BaseModel):
    """An explicitly provisioned OCI block/boot volume; no implicit performance tier."""

    model_config = ConfigDict(extra="forbid")

    size_gb: Decimal = Field(gt=0, allow_inf_nan=False)
    vpus_per_gb: Decimal | None = Field(default=None, ge=0, le=120, allow_inf_nan=False)
    count: int = Field(default=1, ge=1, le=100)


class OciComputeConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["compute"] = "compute"
    shape: str | None = None
    ocpus: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    memory_gb: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    operating_system: Literal["linux", "windows", "unknown"] = "unknown"
    boot_volume: OciVolumeConfiguration | None = None
    block_volumes: list[OciVolumeConfiguration] = Field(default_factory=list, max_length=20)
    # Backward-compatible 27.1 fields. Never charge them twice with boot_volume.
    boot_volume_gb: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    vpus_per_gb: Decimal | None = Field(default=None, ge=0, le=120, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_storage_style(self) -> OciComputeConfiguration:
        if self.boot_volume is not None and (
            self.boot_volume_gb is not None or self.vpus_per_gb is not None
        ):
            raise ValueError("choose boot_volume or legacy boot_volume_gb/vpus_per_gb")
        if self.vpus_per_gb is not None and self.boot_volume_gb is None:
            raise ValueError("legacy vpus_per_gb requires boot_volume_gb")
        return self


class OciDbSystemConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: Literal["db_system"] = "db_system"
    deployment_model: Literal["base_database"] = "base_database"
    shape: str | None = None
    edition: Literal["standard", "enterprise", "enterprise_high_performance"] | None = None
    license_model: Literal["license_included", "byol"] | None = None
    cpu_unit: Literal["ECPU", "OCPU"] | None = None
    cpu_count: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    storage_gb: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)


ResourceConfiguration = Annotated[
    AwsEc2Configuration | AwsRdsConfiguration | OciComputeConfiguration | OciDbSystemConfiguration,
    Field(discriminator="service"),
]


class AwsFinancialTerms(BaseModel):
    """User-supplied contractual terms; never mutate the underlying USD catalog."""

    model_config = ConfigDict(extra="forbid")

    discount_percent: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, decimal_places=6, allow_inf_nan=False
    )
    conversion_enabled: bool = False
    usd_brl_rate: Decimal | None = Field(
        default=None, gt=0, le=Decimal("1000000"), decimal_places=8, allow_inf_nan=False
    )
    tax_percent: Decimal = Field(
        default=Decimal("13"), ge=0, le=1000, decimal_places=6, allow_inf_nan=False
    )

    @model_validator(mode="after")
    def validate_conversion(self) -> AwsFinancialTerms:
        if self.conversion_enabled and self.usd_brl_rate is None:
            raise ValueError("usd_brl_rate is required when conversion is enabled")
        if not self.conversion_enabled and self.usd_brl_rate is not None:
            raise ValueError("usd_brl_rate is only allowed when conversion is enabled")
        return self


class CalculatorEstimateRequest(BaseModel):
    """A simulation is not tied to any configured cloud account."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["aws", "oci"]
    region: str = Field(min_length=1, max_length=80)
    resource_configuration: ResourceConfiguration
    quantity: int = Field(default=1, ge=1, le=100000)
    period: CalculatorPeriod = Field(default_factory=CalculatorPeriod)
    pricing_reference_date: datetime | None = None
    aws_financial: AwsFinancialTerms | None = None

    @field_validator("region")
    @classmethod
    def strip_region(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("region cannot be blank")
        return value.strip()

    @field_validator("pricing_reference_date")
    @classmethod
    def validate_reference_date(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("pricing_reference_date must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_provider_service(self) -> CalculatorEstimateRequest:
        service = self.resource_configuration.service
        allowed = {"aws": {"ec2", "rds"}, "oci": {"compute", "db_system"}}
        if service not in allowed[self.provider]:
            raise ValueError("service is not available for the selected provider")
        if self.provider == "oci" and self.aws_financial is not None:
            raise ValueError("AWS discount, exchange rate and tax are not available for OCI")
        return self


CalculatorPricingStatus = Literal[
    "priced",
    "partially_priced",
    "sku_missing",
    "unsupported_configuration",
    "price_not_effective",
    "missing_configuration",
    "invalid_combination",
    "pricing_configuration_error",
    "sync_required",
]


class CalculatorPricingComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    sku: str
    unit: str
    description: str | None = None
    pricing_status: CalculatorPricingStatus | None = None
    reference_month_hours: Decimal | None = None
    billing_increment_seconds: int | None = None
    minimum_billable_seconds: int = 0
    pricing_item_id: str | None = None
    region_code: str | None = None
    product_sku: str | None = None
    rate_code: str | None = None
    import_batch_id: str | None = None
    synced_at: datetime | None = None
    unit_price: Decimal | None = None
    monthly_units: Decimal | None = None
    period_units: Decimal | None = None
    monthly_original_cost: Decimal | None = None
    period_original_cost: Decimal | None = None
    discount_eligible: bool = False
    currency: Literal["USD", "BRL"]
    source: str | None = None
    effective_from: datetime | None = None
    effective_until: datetime | None = None


class CalculatorEstimateResponse(BaseModel):
    """Conceptual response for Tasks 27.2-27.7; all costs are nullable on failure."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["aws", "oci"]
    service: Literal["ec2", "rds", "compute", "db_system"]
    region: str
    resource_configuration: ResourceConfiguration
    quantity: int = Field(ge=1)
    period: CalculatorPeriod
    period_duration_hours: Decimal | None = None
    monthly_known_subtotal: Decimal | None = None
    period_known_subtotal: Decimal | None = None
    pricing_components: list[CalculatorPricingComponent] = Field(default_factory=list)
    pricing_source: str | None = None
    pricing_reference_date: datetime | None = None
    pricing_currency: Literal["USD", "BRL"]
    monthly_original_cost: Decimal | None = None
    period_original_cost: Decimal | None = None
    discount_percent: Decimal | None = None
    discount_amount: Decimal | None = None
    monthly_discount_amount: Decimal | None = None
    period_discount_amount: Decimal | None = None
    monthly_net_cost: Decimal | None = None
    period_net_cost: Decimal | None = None
    conversion_enabled: bool = False
    usd_brl_rate: Decimal | None = None
    tax_percent: Decimal | None = None
    tax_amount: Decimal | None = None
    monthly_converted_cost: Decimal | None = None
    period_converted_cost: Decimal | None = None
    monthly_tax_amount: Decimal | None = None
    period_tax_amount: Decimal | None = None
    monthly_final_cost: Decimal | None = None
    period_final_cost: Decimal | None = None
    final_currency: Literal["USD", "BRL"]
    pricing_status: CalculatorPricingStatus
    missing_pricing_components: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_financial_consistency(self) -> CalculatorEstimateResponse:
        if self.service != self.resource_configuration.service:
            raise ValueError("service does not match resource configuration")
        allowed = {"aws": {"ec2", "rds"}, "oci": {"compute", "db_system"}}
        if self.service not in allowed[self.provider]:
            raise ValueError("service is not available for the selected provider")
        if self.pricing_currency != ("USD" if self.provider == "aws" else "BRL"):
            raise ValueError("provider pricing currency mismatch")
        if self.provider == "oci" and (
            self.conversion_enabled
            or self.discount_amount is not None
            or self.discount_percent is not None
            or self.tax_amount is not None
            or self.monthly_discount_amount is not None
            or self.period_discount_amount is not None
            or self.monthly_converted_cost is not None
            or self.period_converted_cost is not None
            or self.monthly_tax_amount is not None
            or self.period_tax_amount is not None
            or self.tax_percent is not None
            or self.usd_brl_rate is not None
            or self.final_currency != "BRL"
        ):
            raise ValueError("OCI catalog prices are final BRL values; no financial adjustments")
        if self.provider == "oci":
            for original, net, final in (
                (self.monthly_original_cost, self.monthly_net_cost, self.monthly_final_cost),
                (self.period_original_cost, self.period_net_cost, self.period_final_cost),
            ):
                populated = [value for value in (original, net, final) if value is not None]
                if len(set(populated)) > 1:
                    raise ValueError("OCI commercial BRL totals cannot include extra adjustments")
        if self.provider == "aws":
            expected = "BRL" if self.conversion_enabled else "USD"
            if self.final_currency != expected:
                raise ValueError("AWS final currency does not match conversion_enabled")
        if any(
            component.currency != self.pricing_currency for component in self.pricing_components
        ):
            raise ValueError("mixed currencies in pricing components")
        if self.pricing_status == "priced" and (
            self.monthly_final_cost is None
            or self.period_final_cost is None
            or self.missing_pricing_components
        ):
            raise ValueError("priced estimate requires both final totals and no missing components")
        if self.pricing_status != "priced" and any(
            value is not None
            for value in (
                self.monthly_original_cost,
                self.period_original_cost,
                self.monthly_net_cost,
                self.period_net_cost,
                self.monthly_final_cost,
                self.period_final_cost,
            )
        ):
            raise ValueError("non-priced estimates must not advertise definitive cost totals")
        return self
