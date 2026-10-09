# OCI pricing contract

This document closes the DeepOps OCI pricing track (Tasks 1/7–7/7) and records the deterministic pricing contract implemented in code.

## Source and monetary policy

The single source of approved OCI commercial prices is `backend/app/services/oci_pricing.py`.

- source: `deepops_oci_price_table`
- version: `2026-10`
- currency: `BRL`
- monthly Compute convention: `744` hours/month
- money arithmetic: `Decimal`
- public monetary precision: BRL cents (`0.01`, `ROUND_HALF_UP`)
- taxes: not included
- regional/tenant/contract price variation: not implemented in this track
- Oracle Price List API / automatic catalog import / FX conversion: not implemented in this track

Approved rates:

| Component | Rate |
| --- | ---: |
| E3 OCPU | 0.0521 BRL/OCPU-hour |
| E3 RAM | 0.0031 BRL/GB-hour |
| E4 OCPU | 0.0689 BRL/OCPU-hour |
| E4 RAM | 0.0041 BRL/GB-hour |
| E5 OCPU | 0.08266 BRL/OCPU-hour |
| E5 RAM | 0.005511 BRL/GB-hour |
| Windows | 0.46092 BRL/OCPU-hour |
| Block Storage capacity | 0.0531 BRL/GB-month |
| Block Storage performance | 0.0036 BRL/VPU/GB-month |

## Supported Compute shapes

Shape pricing uses an exact allowlist. It must not infer pricing families from substrings, prefixes or case normalization.

| OCI shape | Pricing family |
| --- | --- |
| `VM.Standard.E3.Flex` | E3 |
| `VM.Standard.E4.Flex` | E4 |
| `VM.Standard.E5.Flex` | E5 |

Examples that remain unsupported in this track include `VM.Standard.A1.Flex`, `VM.Standard.E6.Flex`, `BM.Standard.E4.128` and `VM.DenseIO.E4.Flex`.

Unsupported or incomplete Compute input is not a valid zero-price result. Pricing returns an explicit non-priced status such as `unsupported_shape`, `missing_pricing_input` or `invalid_pricing_input`.

## Compute and Windows

Base Compute pricing is:

```text
OCPU * OCPU-hour rate * 744
+
RAM GB * RAM GB-hour rate * 744
```

Windows is added only after OCI image metadata resolves the operating-system family as `WINDOWS`:

```text
OCPU * 0.46092 * 744
```

Operating-system states are `WINDOWS`, `NON_WINDOWS` and `UNKNOWN`.

- `WINDOWS`: base Compute plus Windows license.
- `NON_WINDOWS`: base Compute only.
- `UNKNOWN`: base Compute may still be calculated when shape/OCPU/RAM are valid, but Windows is not added and OS uncertainty remains explicit.

Instance name, hostname, tags, display name and shape are not authoritative Windows indicators.

## Storage pricing

Block/boot volume monthly price is:

```text
size_gb * 0.0531
+
size_gb * vpus_per_gb * 0.0036
```

`vpus_per_gb = 0` is valid. `vpus_per_gb = None` is incomplete input and must not be converted to zero.

### `oci_block_volume_unattached`

When both storage inputs are valid:

```text
current_monthly_cost = estimated_monthly_savings = full monthly volume cost
currency = BRL
financial_value_populated = true
```

A 500 GB volume at 10 VPU/GB is 44.55 BRL/month.

### `oci_stopped_compute_with_storage`

This rule prices only persistent storage related to the stopped instance:

```text
Boot Volumes + Block Volumes
```

It deliberately excludes OCPU, RAM and Windows licensing even when the instance is Windows. Relationship IDs are deduplicated before pricing, so the same OCID is not counted twice.

The approved example (100 GB boot + 500 GB block, both at 10 VPU/GB) is 53.46 BRL/month.

If any related volume cannot be priced, the rule is financially incomplete: the main opportunity saving is not promoted from the partial subtotal and `financial_value_populated` remains false.

## Rules without pricing in this track

| Rule/resource | Pricing | Currency | Saving |
| --- | --- | --- | --- |
| OCI Block Volume unattached | Yes | BRL | 100% of priced volume cost |
| OCI stopped compute with storage | Yes | BRL | 100% of priced persistent storage |
| OCI Compute E3/E4/E5 | Available to compatible consumers | BRL | Depends on analyzer/consumer |
| OCI Windows | Additional only when confirmed | BRL | Depends on analyzer/consumer |
| OCI Public IP unassigned | No | — | — |
| OCI Untagged Resource | No | — | — |
| Unsupported shape | No | — | — |

Public IP and untagged-resource opportunities remain operational findings with `financial_value_populated = false`; this track does not invent savings for them.

## Evidence and Usage API

Priced OCI findings record pricing metadata in the existing evidence structure, including:

- pricing status;
- source;
- catalog version;
- BRL currency;
- calculation inputs;
- calculated result;
- whether the financial value is populated.

Storage evidence records size/VPU and monthly cost. Stopped-compute evidence records the boot/block volume sets, per-volume pricing, subtotal and final persistent-storage total.

OCI Usage API evidence remains separate as observed billing/spend evidence. Its observed currency does not overwrite the BRL catalog-pricing currency, and this track does not reconcile catalog estimates with actual billing.

## Persistence and opportunity identity

Pricing fields use the existing provider-neutral opportunity contract:

- `current_monthly_cost`
- `estimated_monthly_savings`
- `currency`
- `provider_metadata.financial_value_populated`
- evidence payload

Persistence refreshes those fields on subsequent observations. Pricing amount, currency and pricing version are not part of the opportunity fingerprint. Therefore the same logical opportunity can receive a new price in a later collection without creating a duplicate or changing lifecycle status semantics.

The Opportunities API serializes the same financial fields used by AWS; no OCI-specific frontend contract is required.

## Validation coverage

The OCI pricing test suite covers, among other cases:

- E3/E4/E5 catalog rates and exact shape resolver behavior;
- unsupported shapes;
- 500 GB / 10 VPU block volume = 44.55 BRL;
- VPU zero = capacity-only price;
- missing storage input remains unpriced;
- boot + block storage for stopped Compute = 53.46 BRL;
- multiple volumes and duplicate relationship protection;
- stopped Compute excluding OCPU/RAM/Windows;
- Windows confirmed, non-Windows and unknown OS;
- persistence of OCI financial values and evidence;
- API serialization of persisted OCI pricing;
- same fingerprint with a refreshed financial amount across collection runs.
