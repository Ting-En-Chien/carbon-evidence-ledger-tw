# Factor Registry

This note explains the versioned emission-factor and official-reference
registry, including Phase 7B physical unit-conversion hardening.

**The registry stores reference data. Registration does not automatically
authorize a calculation.**

## Four related but different concepts

| Concept | What it is | Example in this project |
| --- | --- | --- |
| **Emission factor** | Relates an activity quantity to greenhouse-gas emissions | 0.474 kgCO2e / kWh; 56100 kgCO2 / TJ |
| **GWP value** | Compares a gas to CO2 over a chosen time horizon | CH4 = 28; N2O = 265 |
| **Physical unit conversion** | Converts one energy unit to another | 1 kcal = 4.1868e-9 TJ |
| **Fuel-specific lower heating value** | Energy content of a fuel per volume | kcal/m3 for natural gas; kcal/L for diesel |

These must not be mixed up.

## What an emission factor is

An emission factor is a published number that relates an activity quantity to
emissions of a greenhouse gas.

Example:

- Taiwan 2024 purchased electricity factor: **0.474 kgCO2e / kWh**

## What a GWP value is

**GWP** means Global Warming Potential. Phase 5A registers IPCC AR5 100-year
GWP values from the Taiwan Ministry of Environment emission-factor
announcement:

| Gas | GWP |
|-----|-----|
| CO2 | 1 |
| CH4 | 28 |
| N2O | 265 |

## What a physical unit conversion is

A physical unit conversion changes how energy is expressed, without saying how
much energy one litre or one cubic metre of fuel contains.

The Taiwan MOENV 113-year inventory guidance states:

**1 kcal = 4.1868 × 10^-9 TJ**

This prototype registers that conversion as:

`conv_kcal_to_tj_moenv_2024`

**A verified physical unit conversion is not a substitute for a verified
fuel-specific heating value.**

## What a fuel-specific lower heating value is

A lower heating value (LHV) tells how much energy is released by a specific
fuel quantity, for example:

- natural gas: kcal per m3
- diesel: kcal per L

The official guidance requires that fuel heating values be supported by
appropriate testing or supplier evidence under the applicable requirements.

## Why kcal → TJ alone cannot convert 8000 m3 or 1200 L

The calculation sequence for fuel combustion with the emission-factor method
is:

activity data
× lower heating value
× unit conversion factor
× emission factor
× GWP

If only kcal → TJ is known:

- `8000 m3 × 4.1868e-9 TJ/kcal` is invalid because m3 is not kcal
- `1200 L × 4.1868e-9 TJ/kcal` is invalid because L is not kcal

The missing step is still:

- natural-gas lower heating value in kcal/m3 or equivalent
- diesel lower heating value in kcal/L or equivalent

## Why worked-example values are not reused

The official guidance contains worked-example heating values such as:

- diesel 8,500 kcal/L
- natural gas 8,845 kcal/m3

**Worked-example values are not generic emission parameters.**

They are described as supplier-provided annual weighted-average heating values
for the example facility only. This prototype does not register them as
general factors or conversions.

## Official references registered

1. **Taiwan Ministry of Environment** emission-factor announcement  
   `ref_tw_moenv_2024_emission_factors`  
   Identifier: 環部授氣字第1139101231號  
   Effective from 2024-02-05  
   Official tables are available as PDF and ODS companion formats.

2. **Taiwan Ministry of Economic Affairs** 2024 electricity carbon factor  
   `ref_tw_moea_2024_electricity_factor`  
   Official publication reporting **0.474 kgCO2e/kWh**

3. **Taiwan Ministry of Environment** inventory guidance  
   `ref_tw_moenv_2024_inventory_guidance`  
   溫室氣體排放量盤查作業指引113年版  
   Used for methodology sequence, LHV evidence requirements, and kcal → TJ

## Registered emission factors

### Ready factor

| Factor | Value | Units | Status |
|--------|-------|-------|--------|
| `ef_tw_grid_electricity_2024` | 0.474 | kgCO2e / kWh | `ready` |

### Registered but blocked fuel factors

Natural-gas and diesel combustion factors remain:

- `factor_status = registered_missing_conversion`
- natural gas requires `verified_natural_gas_heating_value_m3_to_TJ`
- diesel requires `verified_diesel_heating_value_L_to_TJ`

## Why electricity can be ready while fuel factors remain blocked

- Electricity activity is measured in `kWh`
- The electricity factor denominator is also `kWh`

Natural gas and diesel activity data are measured in `m3` and `L`, but the
official combustion factors are published per `TJ`. Knowing kcal → TJ does not
provide the fuel-specific heating value needed to reach TJ from volume.

## What a calculation dependency means

Phase 7B keeps exactly two fuel dependencies:

1. Natural gas: verified heating value converting `m3` → `TJ`
2. Diesel: verified heating value converting `L` → `TJ`

Both remain `missing_verified_value`.

Acceptable evidence may include an applicable supplier-provided value or
appropriately supported test evidence under the official 113-year guidance.
Uncited generic internet values and worked-example heating values are
prohibited.

## Why missing data is kept visible

Professional carbon data work fails closed.

- Missing conversions stay visible as `registered_missing_conversion`
- Dependency rows explain what evidence is still required
- No silent fallback is used

## Current limitations

- No automatic application of engineering conversions during calculation
- No combined CO2e fuel factors
- No guessed heating values
- Fuel factors remain blocked until verified fuel-specific conversion evidence
  exists
