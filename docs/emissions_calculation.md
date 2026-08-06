# Emissions Calculation — Phase 5C

This note explains the limited and auditable emissions calculation step.

**A calculated value is only produced when the activity, unit, factor, and
readiness checks all agree.**

Phase 5C does **not** invent missing heating values, Scope 3 factors, GHG
scopes, CBAM roles, or IFRS S2 roles.

## What emissions calculation means

Emissions calculation turns a validated activity quantity and a compatible
emission factor into a greenhouse-gas result.

In this phase, only a **direct CO2e factor** with matching units may be used.

## Why calculation occurs only after validation and factor matching

Earlier phases already checked:

1. evidence and schema validity
2. safe unit normalization
3. registered factor versions and sources
4. whether the activity is ready or blocked

Calculation is therefore a final arithmetic step, not a place to guess missing
inputs.

## The electricity formula

Formula:

- `formula_id = activity_value_times_direct_co2e_factor`
- `formula_version = 1.0`

```text
calculated_kgco2e = normalized_value × factor_value
calculated_tco2e = calculated_kgco2e / 1000
```

Electricity example:

```text
50000 kWh × 0.474 kgCO2e/kWh
= 23700 kgCO2e
= 23.7 tCO2e
```

## Why kgCO2e is converted to tCO2e by dividing by 1000

One tonne equals 1000 kilograms.

So:

```text
tCO2e = kgCO2e / 1000
```

Phase 5C does not round internally. Simple decimal inputs are handled with
`Decimal` so avoidable binary floating-point artefacts are reduced.

## Why natural gas and diesel remain blocked

Their registered factors are published per `TJ`, while activity data is in
`m3` or `L`. Without a verified heating-value conversion, calculation would
invent energy content.

Those rows keep:

- `calculation_status = blocked_missing_conversion`
- missing calculated values
- a reason that names the required conversion

## Why missing results are not written as zero

Zero would look like a real calculated result.

Blocked or incomplete records keep `calculated_kgco2e` and `calculated_tco2e`
missing (`NA`). That keeps the gap visible.

## Why purchased steel is not calculated yet

No suitable purchased-steel emission factor is configured in the current MVP.
Status:

- `no_factor_configured`

## Why production output is not an emissions activity

Finished-goods output is product-quantity / operational evidence. It is not
itself fuel or electricity consumption. Status:

- `not_emissions_activity`

## Calculation statuses

| Status | Meaning |
|--------|---------|
| `calculated` | Direct CO2e calculation completed |
| `blocked_missing_conversion` | Factor candidates exist but conversion evidence is missing |
| `no_factor_configured` | No suitable factor is configured |
| `not_emissions_activity` | Record is not an emissions activity |
| `unsupported_activity_type` | No calculation method exists |
| `invalid_normalized_input` | Normalized value/unit is missing or invalid |
| `factor_match_inconsistent` | Readiness says ready, but candidates/factor checks disagree |

## How factor and formula traceability is preserved

For a calculated electricity row, the output keeps:

- `factor_id`
- `factor_value`
- factor numerator and denominator units
- `source_reference_id`
- `formula_id`
- `formula_version`

That makes the arithmetic auditable.

## Why no company total is produced yet

Phase 5C calculates **per activity record** only.

A company total would mix:

- calculated electricity
- blocked fuel records
- non-emissions records

Totals belong to a later reporting phase after blocked items are resolved or
explicitly excluded with documented rules.

## Baseline result for the five synthetic activities

| Record | Status | Result |
|--------|--------|--------|
| Electricity | `calculated` | 23700 kgCO2e = 23.7 tCO2e |
| Natural gas | `blocked_missing_conversion` | missing |
| Diesel | `blocked_missing_conversion` | missing |
| Purchased steel | `no_factor_configured` | missing |
| Finished-goods output | `not_emissions_activity` | missing |

## Current limitations

- Only direct CO2e factors with matching units are calculated
- Natural gas and diesel remain blocked
- No Scope 3 purchased-steel calculation
- No company-level total
- No GHG Protocol / CBAM / IFRS S2 mapping in this phase
