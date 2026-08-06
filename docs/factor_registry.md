# Factor Registry — Phase 5A

This note explains the versioned emission-factor and official-reference
registry.

**The registry stores reference data. Registration does not automatically
authorize a calculation.**

Phase 5A does **not** calculate emissions and does **not** match factors to
activity records.

## What an emission factor is

An emission factor is a published number that relates an activity quantity to
emissions of a greenhouse gas.

Example:

- Taiwan 2024 purchased electricity factor: **0.474 kgCO2e / kWh**

That means each kilowatt-hour of purchased electricity is associated with
0.474 kilograms of carbon-dioxide-equivalent emissions for the location-based
corporate inventory scenario used in this project.

## What a GWP value is

**GWP** means Global Warming Potential. It compares the climate impact of a
gas to carbon dioxide over a chosen time horizon.

Phase 5A registers IPCC AR5 100-year GWP values from the Taiwan Ministry of
Environment emission-factor announcement:

| Gas | GWP |
|-----|-----|
| CO2 | 1 |
| CH4 | 28 |
| N2O | 265 |

These GWP values are stored for later use. Phase 5A does **not** combine
gas-specific fuel factors into a single CO2e result yet.

## What numerator and denominator mean

Every factor has two units:

- **numerator unit** — the emissions unit (for example `kgCO2e` or `kgCH4`)
- **denominator unit** — the activity unit the factor expects (for example
  `kWh` or `TJ`)

A factor can be used only when the activity quantity can be expressed in the
denominator unit, or when a verified conversion to that unit exists.

## Why factor version and source page matter

Auditable carbon work needs more than a number. It needs:

- which official publication the number came from
- which page or location holds the value
- which year or validity period applies

That is why each factor stores `source_reference_id`, `source_locator`,
`factor_year`, and validity dates.

## Official references registered

1. **Taiwan Ministry of Environment** emission-factor announcement  
   `ref_tw_moenv_2024_emission_factors`  
   Identifier: 環部授氣字第1139101231號  
   Effective from 2024-02-05

2. **Taiwan Ministry of Economic Affairs** 2024 electricity carbon factor  
   `ref_tw_moea_2024_electricity_factor`  
   Official publication reporting **0.474 kgCO2e/kWh**  
   No invented document number is used.

## Registered emission factors

### Ready factor

| Factor | Value | Units | Status |
|--------|-------|-------|--------|
| `ef_tw_grid_electricity_2024` | 0.474 | kgCO2e / kWh | `ready` |

Electricity can be ready because the activity data is already in `kWh`, which
matches the factor denominator.

### Registered but blocked fuel factors

Natural-gas stationary combustion (PDF page 2, Natural Gas row):

| Gas | Value | Units |
|-----|-------|-------|
| CO2 | 56100 | kgCO2 / TJ |
| CH4 | 1 | kgCH4 / TJ |
| N2O | 0.1 | kgN2O / TJ |

Diesel mobile combustion (PDF page 3, Gas/Diesel Oil row):

| Gas | Value | Units |
|-----|-------|-------|
| CO2 | 74100 | kgCO2 / TJ |
| CH4 | 3.9 | kgCH4 / TJ |
| N2O | 3.9 | kgN2O / TJ |

All six fuel rows have:

- `factor_status = registered_missing_conversion`
- a named conversion requirement

## Why electricity can be ready while fuel factors remain blocked

- Electricity activity is measured in `kWh`
- The electricity factor denominator is also `kWh`

Natural gas and diesel activity data in this project are measured in `m3` and
`L`, but the official combustion factors are published per `TJ`. Without a
verified heating-value conversion, multiplying would invent energy content.

## Why kg/TJ cannot be multiplied directly by m3 or L

The units do not match.

- `kgCO2 / TJ` needs activity energy in `TJ`
- activity records currently store `m3` or `L`

`m3 × (kg/TJ)` or `L × (kg/TJ)` is not a valid calculation unless a verified
conversion from volume to `TJ` is available.

## What a calculation dependency means

A calculation dependency records a missing input that must be filled before a
calculation is allowed.

Phase 5A dependencies:

1. Natural gas: verified heating value converting `m3` → `TJ`
2. Diesel: verified heating value converting `L` → `TJ`

Acceptable evidence may include supplier invoices, contracts, test reports, or
verified official heat-value publications. Uncited generic internet values are
prohibited.

## Why missing data is kept visible

Professional carbon data work fails closed.

- Missing conversions stay visible as `registered_missing_conversion`
- Dependency rows explain what evidence is still required
- No silent fallback is used

## Why no combined diesel or natural-gas CO2e result is calculated yet

Creating a combined kgCO2e per litre or per cubic metre would require:

1. verified energy conversion to TJ
2. multiplication by each gas factor
3. multiplication by GWP values
4. summing to CO2e

Phase 5A stops at registration. Combining those steps belongs to a later
calculation phase.

## Why an official source does not make every factor suitable for every use

An official publication can be authentic and still incomplete for a specific
record. Suitability also depends on:

- matching activity type
- matching units
- geography and year
- organizational or process boundary
- whether required conversions are available

## Current limitations

- No factor-to-activity matching yet
- No emissions calculation yet
- No combined CO2e fuel factors
- No guessed heating values
- Fuel factors remain blocked until verified conversion evidence exists
