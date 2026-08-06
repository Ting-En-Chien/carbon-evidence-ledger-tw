# Factor Matching — Phase 5B

This note explains deterministic emission-factor matching and calculation
readiness.

**Matching is not calculation.** Phase 5B decides which registered factors are
candidates and whether a later calculation is allowed. It does **not** multiply
activity values by factors and does **not** produce kgCO2e or tCO2e.

## What factor matching means

Factor matching answers:

- Does this activity have a registered factor?
- Which factor or factors are candidates?
- Are the activity unit and factor denominator already compatible?
- Is a verified conversion dependency still missing?
- Is this record intentionally not calculated in the current MVP?

## Why matching is separate from calculation

Keeping matching separate from calculation makes the pipeline easier to audit:

1. Normalize units
2. Match factors and decide readiness
3. Calculate only when readiness is `ready` (later phase)

A matched factor means only that a candidate exists. It does **not** mean that
emissions were calculated.

## Why electricity is ready

Purchased electricity activity is measured in `kWh`.

The registered Taiwan 2024 electricity factor is:

- `ef_tw_grid_electricity_2024`
- `0.474 kgCO2e / kWh`
- `factor_status = ready`
- `required_conversion = not_required`

Because the units already match, electricity readiness is `ready`.

## Why natural gas and diesel are blocked

Natural-gas activity is measured in `m3`, but the official combustion factors
are published per `TJ`.

Diesel company-vehicle activity is measured in `L`, but the official mobile
combustion factors are also published per `TJ`.

Phase 5B therefore returns candidates with:

- `match_status = matched_blocked_dependency`

and readiness:

- `calculation_readiness = blocked_missing_conversion`

No heating value is guessed.

## Why three gas-specific factors may match one fuel activity

Official MOENV tables publish separate factors for:

- CO2
- CH4
- N2O

One fuel activity may therefore have three candidates. Combining them with GWP
values into CO2e is a later calculation step, not part of Phase 5B.

## Why purchased steel has no configured factor yet

Purchased steel is a material-input / Scope 3 style record. The first MVP has
not registered a suitable purchased-steel emission factor, so readiness is:

- `no_factor_configured`

This is intentional and visible.

## Why production output does not need an emissions factor

Finished-goods output is product-quantity / operational evidence. It is not an
emissions activity, so readiness is:

- `not_emissions_activity`

## Matching and readiness statuses

### Candidate `match_status`

| Status | Meaning |
|--------|---------|
| `matched_ready` | Compatible ready factor candidate |
| `matched_blocked_dependency` | Factor candidate exists but a conversion is still missing |

### Activity `calculation_readiness`

| Status | Meaning |
|--------|---------|
| `ready` | Calculation may proceed in a later phase |
| `blocked_missing_conversion` | Candidates exist but a verified conversion is missing |
| `no_factor_configured` | No suitable factor is configured yet |
| `not_emissions_activity` | Record is not an emissions activity |
| `unsupported_activity_type` | Activity type is outside current matching rules |

## Why no fallback factor is guessed

If units do not match, explicit validity dates do not cover the activity
period, or a factor is inactive, Phase 5B does not invent a substitute factor.
Fail closed and keep the reason visible.

Blank `valid_from` / `valid_to` values mean this prototype does **not** assert
an applicability period for that factor. Matching still applies factor status
and conversion dependencies. Explicit dates (such as the electricity factor
window) continue to be checked.

## Why no emissions are calculated in Phase 5B

Calculation would require multiplying normalized activity values by factor
values (and for fuels, applying verified heating values and GWP). That belongs
to a later phase after readiness is `ready`.

## Baseline table for the five synthetic activities

| Activity | Candidates | Readiness | Blocking dependency |
|----------|------------|-----------|---------------------|
| Electricity | 1 | `ready` | none |
| Natural gas | 3 | `blocked_missing_conversion` | `verified_natural_gas_heating_value_m3_to_TJ` |
| Diesel (company vehicle) | 3 | `blocked_missing_conversion` | `verified_diesel_heating_value_L_to_TJ` |
| Purchased steel | 0 | `no_factor_configured` | none |
| Finished-goods output | 0 | `not_emissions_activity` | none |

Totals:

- candidate rows: **7**
- readiness rows: **5**

## Current limitations

- No emissions multiplication yet
- No heating-value conversions yet
- No Scope 3 purchased-steel factor yet
- Diesel matching currently limited to `process_use = company_vehicle`
- Stationary diesel / other combustion contexts are not configured
- Natural-gas and diesel factor rows leave validity dates blank in this
  prototype; only explicit dates are enforced
- No GHG Protocol, CBAM, or IFRS S2 mappings in this phase
