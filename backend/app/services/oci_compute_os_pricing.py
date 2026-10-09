from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.oci_os import OciOperatingSystemFamily, OciOperatingSystemResolution
from app.services.oci_pricing import (
    OCI_WINDOWS_OCPU_HOUR,
    OciComputePricingResult,
    OciPricingService,
    quantize_money,
    resolve_compute_price_family,
)


@dataclass(frozen=True)
class OciComputeOsPricingResult:
    compute: OciComputePricingResult
    operating_system: OciOperatingSystemResolution
    compute_base_monthly_cost: Decimal | None
    windows_monthly_cost: Decimal
    total_monthly_cost: Decimal | None
    os_pricing_status: str

    @property
    def windows_license_included(self) -> bool:
        return self.compute.windows_license_included

    @property
    def financial_value_populated(self) -> bool:
        return self.compute.financial_value_populated


class OciComputeOsPricingService:
    """Apply Windows licensing only after an explicit OCI OS resolution."""

    def __init__(self, pricing: OciPricingService | None = None) -> None:
        self._pricing = pricing or OciPricingService()

    def price(
        self,
        *,
        shape: str | None,
        ocpus: Decimal | int | float | str | None,
        memory_gb: Decimal | int | float | str | None,
        operating_system: OciOperatingSystemResolution,
    ) -> OciComputeOsPricingResult:
        include_windows = operating_system.family is OciOperatingSystemFamily.WINDOWS

        # Keep the resource-level domain statuses from Task 5 for unsupported/missing inputs.
        base = self._pricing.price_compute_resource(
            shape=shape,
            ocpus=ocpus,
            memory_gb=memory_gb,
        )
        if not base.financial_value_populated:
            return OciComputeOsPricingResult(
                compute=base,
                operating_system=operating_system,
                compute_base_monthly_cost=None,
                windows_monthly_cost=Decimal("0.00"),
                total_monthly_cost=None,
                os_pricing_status=(
                    "unknown_os"
                    if operating_system.family is OciOperatingSystemFamily.UNKNOWN
                    else "resolved_os"
                ),
            )

        assert base.base_monthly_cost is not None
        compute_result = base
        windows_monthly_cost = Decimal("0.00")
        total = base.base_monthly_cost
        if include_windows:
            family = resolve_compute_price_family(shape)
            compute_result = self._pricing.compute_monthly_pricing(
                family=family,
                ocpus=ocpus,
                memory_gb=memory_gb,
                include_windows_license=True,
                shape=shape,
            )
            assert compute_result.base_monthly_cost is not None
            parsed_ocpus = compute_result.ocpus
            assert parsed_ocpus is not None
            windows_monthly_cost = quantize_money(
                parsed_ocpus * OCI_WINDOWS_OCPU_HOUR * compute_result.monthly_hours
            )
            total = compute_result.base_monthly_cost

        return OciComputeOsPricingResult(
            compute=compute_result,
            operating_system=operating_system,
            compute_base_monthly_cost=base.base_monthly_cost,
            windows_monthly_cost=windows_monthly_cost,
            total_monthly_cost=total,
            os_pricing_status=(
                "unknown_os"
                if operating_system.family is OciOperatingSystemFamily.UNKNOWN
                else "resolved_os"
            ),
        )
