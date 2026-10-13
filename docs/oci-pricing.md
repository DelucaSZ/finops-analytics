# OCI pricing contract

This document records the deterministic OCI pricing contract after Task 23.7, when the approved commercial rates moved from application constants to the persistent provider-neutral Pricing Catalog.

## Persistent source of truth

The single runtime source of approved OCI commercial unit prices is the `pricing_catalog_items` table. `backend/app/services/oci_pricing.py` contains only stable pricing keys, formulas, shape allowlists and monetary conventions; it does not contain the production rate amounts.

The initial OCI rows are inserted deterministically by Alembic migration `0024_pricing_catalog` so a deployment does not require manual pricing setup.

- provider: `oci`
- source: `IMPORTED_OCI_CALCULATOR`
- catalog generation/version used by current evidence: `2026-10`
- currency: `BRL`
- monthly Compute convention: `744` hours/month
- persisted price type: `Numeric(20, 8)` / Python `Decimal`
- public monetary precision: BRL cents (`0.01`, `ROUND_HALF_UP`)
- taxes: not included
- regional/tenant/contract price variation: not implemented in Task 23.7
- Oracle Price List API / automatic public-price import / FX conversion: not implemented

The values OCI previously supplied to the project are denominated in **BRL (Brazilian reais)**. The AWS pricing currently used by DeepOps is denominated in **USD**. DeepOps does not assume one global currency and must not sum BRL and USD without an explicit conversion layer; FX is outside Task 23.7.

## Seeded OCI pricing items

The migration preserves the exact commercial rates that were already used by the application:

| Service | SKU | Unit | Rate | Currency |
| --- | --- | --- | ---: | --- |
| Compute | `VM.Standard.E3.Flex.OCPU` | `OCPU_HOUR` | 0.0521 | BRL |
| Compute | `VM.Standard.E3.Flex.Memory` | `GB_RAM_HOUR` | 0.0031 | BRL |
| Compute | `VM.Standard.E4.Flex.OCPU` | `OCPU_HOUR` | 0.0689 | BRL |
| Compute | `VM.Standard.E4.Flex.Memory` | `GB_RAM_HOUR` | 0.0041 | BRL |
| Compute | `VM.Standard.E5.Flex.OCPU` | `OCPU_HOUR` | 0.08266 | BRL |
| Compute | `VM.Standard.E5.Flex.Memory` | `GB_RAM_HOUR` | 0.005511 | BRL |
| Compute | `WINDOWS_LICENSE_OCPU` | `OCPU_HOUR` | 0.46092 | BRL |
| Block Volume | `BLOCK_VOLUME_GB_MONTH` | `GB_MONTH` | 0.0531 | BRL |
| Block Volume | `BLOCK_VOLUME_VPU_GB_MONTH` | `VPU_GB_MONTH` | 0.0036 | BRL |

Each row also persists description, `effective_from`, optional `effective_until`, `enabled`, source and timestamps. The schema is provider-neutral and can represent OCI, AWS, Azure, GCP or another provider without a structural change. Task 23.7 does not migrate AWS rates into this table.

## Effective-dated resolver

`PricingResolver` is the only generic database lookup layer. A current price must satisfy:

```text
enabled = true
effective_from <= reference_date
effective_until is null OR reference_date < effective_until
```

The caller supplies provider, service, SKU, unit and optionally a reference date. The returned `ResolvedPrice` carries the amount together with provider, service, SKU, unit, currency, source and validity data.

Failure is explicit:

- no valid row: `PricingNotFoundError`;
- more than one simultaneously valid row for the same pricing identity: `PricingAmbiguityError`;
- unexpected currency: `PricingCurrencyMismatchError`.

A missing catalog row is never silently interpreted as `price = 0` and there is no runtime fallback to the former static prices.

The resolver supports a provider snapshot that loads effective rows in one query. `OciPricingService` can operate over that immutable snapshot, so loops do not issue one SQL query per resource. Its default path also keeps a read snapshot and exposes `clear_cache()` for the administrative lifecycle that will be added in Task 23.8.

## Supported Compute shapes

Shape pricing uses an exact allowlist. It must not infer pricing families from substrings, prefixes or case normalization.

| OCI shape | Pricing family |
| --- | --- |
| `VM.Standard.E3.Flex` | E3 |
| `VM.Standard.E4.Flex` | E4 |
| `VM.Standard.E5.Flex` | E5 |

Examples that remain unsupported include `VM.Standard.A1.Flex`, `VM.Standard.E6.Flex`, `BM.Standard.E4.128` and `VM.DenseIO.E4.Flex`.

Unsupported or incomplete Compute resource input is not a valid zero-price result. Resource pricing returns an explicit non-priced status such as `unsupported_shape`, `missing_pricing_input` or `invalid_pricing_input`. Catalog configuration errors remain exceptions rather than resource-data statuses.

## Compute and Windows

Base Compute pricing preserves the existing formula:

```text
OCPU * resolved OCPU-hour rate * 744
+
RAM GB * resolved RAM GB-hour rate * 744
```

Windows is added only after OCI image metadata resolves the operating-system family as `WINDOWS`:

```text
OCPU * resolved WINDOWS_LICENSE_OCPU rate * 744
```

Operating-system states are `WINDOWS`, `NON_WINDOWS` and `UNKNOWN`.

- `WINDOWS`: base Compute plus resolved Windows license.
- `NON_WINDOWS`: base Compute only.
- `UNKNOWN`: base Compute may still be calculated when shape/OCPU/RAM are valid, but Windows is not added and OS uncertainty remains explicit.

Instance name, hostname, tags, display name and shape are not authoritative Windows indicators.

## Storage pricing

Block/boot volume monthly price preserves the existing formula but resolves both unit prices from the catalog:

```text
size_gb * resolved BLOCK_VOLUME_GB_MONTH
+
size_gb * vpus_per_gb * resolved BLOCK_VOLUME_VPU_GB_MONTH
```

`vpus_per_gb = 0` is valid. `vpus_per_gb = None` is incomplete resource input and must not be converted to zero.

A 500 GB volume at 10 VPU/GB remains 44.55 BRL/month. The approved stopped-Compute example with a 100 GB boot volume plus a 500 GB block volume, both at 10 VPU/GB, remains 53.46 BRL/month.

`oci_block_volume_unattached` continues to use the full priced volume cost as its monthly saving. `oci_stopped_compute_with_storage` continues to price only persistent related storage and deliberately excludes OCPU, RAM and Windows licensing.

## Currency and persisted opportunities

Pricing fields continue to use the provider-neutral opportunity contract:

- `current_monthly_cost`;
- `estimated_monthly_savings`;
- `currency`;
- `provider_metadata.financial_value_populated`;
- evidence payload.

OCI priced findings persist `BRL`. AWS findings continue to persist/use `USD` according to the existing AWS path. Currency accompanies the monetary value, so a historical OCI saving is not reinterpreted as USD later.

OCI Usage API evidence remains separate observed billing/spend evidence. Its observed currency does not overwrite the catalog-pricing currency, and Task 23.7 does not reconcile catalog estimates with actual billing.

## Validation coverage

Task 23.7 adds coverage for:

- deterministic nine-row OCI seed after migration;
- all imported OCI rows explicitly `BRL`;
- numeric precision, constraints and lookup index;
- enabled/current, future, expired and disabled validity cases;
- ambiguous effective rows;
- missing prices;
- currency mismatch and simultaneous OCI/BRL plus AWS/USD contexts;
- database-backed Compute and Block Volume equivalence;
- catalog-value changes affecting calculations, proving there is no static production fallback;
- provider snapshot behavior that avoids per-resource SELECTs;
- existing OCI E3/E4/E5, Windows, Block Volume and savings regressions;
- full AWS regression through the existing backend suite.

## Deliberate follow-up scope

Task 23.7 creates the persistent source of truth. Administrative price editing belongs to Task 23.8. Complete price-change versioning/audit lifecycle belongs to Task 23.9. Neither FX conversion nor a global base currency is introduced here.
