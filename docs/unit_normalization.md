# Unit Normalization — Phase 4

This note explains safe unit normalization in the Carbon Evidence Ledger.

**Normalization is not an emissions calculation.** It only converts supported
activity units into consistent canonical units so later calculation steps can
use one agreed unit per activity type.

## What unit normalization means

Unit normalization answers:

- What was the original value and unit?
- What canonical unit should this activity use?
- Can the conversion be performed safely?
- Was a conversion needed?
- If conversion is impossible, why was it blocked?

## Why consistent units are needed before carbon calculations

Activity data may arrive as `kWh` or `MWh`, `kg` or `t`. Emission factors and
formulas usually expect one agreed unit.

If units are mixed and silently guessed, calculations become hard to audit.
Normalization makes the unit choice explicit and keeps the original values.

## What a canonical unit means

A **canonical unit** is the project's chosen standard unit for an activity type.

| Activity type | Canonical unit |
|---------------|----------------|
| `grid_electricity` | `kWh` |
| `natural_gas` | `m3` |
| `diesel` | `L` |
| `purchased_steel` | `t` |
| `finished_goods_output` | `t` |
| `scrap_output` | `t` |

## Original values are never overwritten

Normalization creates a **derived** result table.

It preserves:

- `record_id`
- `activity_type`
- `original_value`
- `original_unit`

It adds:

- `normalized_value`
- `normalized_unit`
- `normalization_status`
- `normalization_reason`

It does **not** change:

- `activity_value` or `unit` on the input DataFrame
- raw CSV or JSON files
- accepted ingestion DataFrames

## Supported conversions

Only these explicit conversions are allowed:

| From | To | Factor |
|------|----|--------|
| `MWh` | `kWh` | × 1000 |
| `kWh` | `MWh` | × 0.001 |
| `kg` | `t` | × 0.001 |
| `t` | `kg` | × 1000 |

Normalization always converts **toward** the canonical unit when a supported
path exists.

Examples:

- `1 MWh` → `1000 kWh`
- `0.5 MWh` → `500 kWh`
- `1000 kg` → `1 t`
- `2500 kg` → `2.5 t`
- natural gas `8000 m3` → remains `8000 m3` (already canonical)

## Why m3 to GJ is not performed

Natural-gas volume (`m3`) can be converted to energy (`GJ`) only with a
calorific value or similar engineering assumption.

Phase 4 does **not** infer calorific values. Unsupported conversions are blocked
with status `unsupported_conversion`.

## Why L to kg is not performed

Diesel volume (`L`) can be converted to mass (`kg`) only with a fuel density.
Phase 4 does **not** invent densities. That conversion remains blocked.

## Normalization statuses

| Status | Meaning |
|--------|---------|
| `already_canonical` | Source unit already equals the canonical unit |
| `normalized` | A supported conversion was applied |
| `unsupported_conversion` | No safe conversion path to the canonical unit |
| `unsupported_activity_type` | No canonical-unit rule for this activity type |
| `invalid_value` | Value missing, non-numeric, ≤ 0, NaN, or infinite |
| `invalid_unit` | Unit missing or blank |

Every input row produces one output row. Blocked rows keep
`normalized_value` / `normalized_unit` missing and explain why.

## Why calculations are not rounded internally

Normalized values keep full floating-point precision from the explicit factor.
Rounding for display or reporting can happen later. Silent rounding inside
normalization would hide audit detail.

## What Phase 4 does not do

Phase 4 does **not**:

- calculate tCO2e or kgCO2e
- attach emission factors
- assign GHG Protocol scopes
- assign CBAM or IFRS S2 roles
- invent calorific values or fuel densities
- write processed CSV files
- mutate raw evidence files

## Current limitations

- Only a small set of explicit unit pairs is supported
- Activity types without a canonical rule are blocked, not guessed
- String numbers such as `"50000"` are treated as invalid (typed floats required)
- No emission-factor matching yet (later phase)
