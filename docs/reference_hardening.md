# Reference Hardening — Phase 7B

## Official source files obtained by the user

The user obtained these official Taiwan Ministry of Environment documents:

1. `113年2月5日公告溫室氣體排放係數.pdf`
2. `113年2月5日公告溫室氣體排放係數.ods`
3. `溫室氣體排放量盤查作業指引113年版.pdf`

Binary PDF and ODS files are **not** committed to this Git repository. Their
provenance is recorded as reference metadata instead.

## What was already represented

Before Phase 7B, the repository already registered:

- `ref_tw_moenv_2024_emission_factors` for announcement
  環部授氣字第1139101231號
- stationary natural-gas and mobile diesel emission factors
- GWP values from the same announcement
- fuel factors marked `registered_missing_conversion`

Those emission-factor values were not changed in Phase 7B.

## PDF and ODS companion formats

The official PDF and ODS files are companion representations of the **same**
announced emission-factor tables.

This prototype therefore:

- keeps one regulatory reference for the announcement
- does **not** create separate emission-factor values merely because both
  formats exist
- notes that both formats are available from the Taiwan MOENV GHG Registry

## New inventory-guidance reference

Phase 7B adds:

`ref_tw_moenv_2024_inventory_guidance`

Title: 溫室氣體排放量盤查作業指引113年版

Authority level: `official_government_guidance`

This reference supports:

- the fuel-combustion calculation sequence
- lower heating-value evidence requirements
- the physical conversion 1 kcal = 4.1868e-9 TJ

Publication and effective dates are left blank because an exact independently
recorded date was not available in the repository metadata.

## New kcal → TJ engineering conversion

Phase 7B creates `data/reference/engineering_conversions.csv` with one ready
row:

| Field | Value |
| --- | --- |
| conversion_id | `conv_kcal_to_tj_moenv_2024` |
| source_unit | kcal |
| target_unit | TJ |
| multiplier | 4.1868e-9 |
| status | ready |
| source_reference_id | `ref_tw_moenv_2024_inventory_guidance` |

Allowed use: convert a known energy quantity expressed in kcal to TJ.

Prohibited use: do not use this conversion alone to convert litres or cubic
metres of fuel to TJ.

## Why natural gas and diesel remain blocked

**A verified physical unit conversion is not a substitute for a verified
fuel-specific heating value.**

Knowing kcal → TJ does **not** mean:

- m3 → TJ is known for natural gas
- L → TJ is known for diesel

Therefore:

- natural-gas factors remain `registered_missing_conversion`
- diesel factors remain `registered_missing_conversion`
- calculation readiness remains `blocked_missing_conversion`
- Phase 7A QA still reports missing conversion dependencies for gas and diesel

## Why worked-example heating values are not registered

The official guidance includes worked-example values such as:

- diesel 8,500 kcal/L
- natural gas 8,845 kcal/m3

**Worked-example values are not generic emission parameters.**

They belong only to the example facility and are described as supplier-provided
annual weighted-average heating values for that example. They are not copied
into emission factors, engineering conversions, calculation dependencies as
resolved values, or calculation logic.

## Why provenance quality matters more than making every demo record calculable

It would be easy to invent a heating value so that every synthetic activity
becomes calculable. That would hide a real evidence gap.

This project keeps missing fuel-specific heating values visible because:

- official guidance requires appropriate heating-value evidence
- silent fallbacks are prohibited
- auditors need to see what is verified and what is still missing

## Current Phase 7B limitations

- Engineering conversions are registered and validated only
- They are not automatically applied during emissions calculation
- Fuel-specific heating values remain unresolved for the synthetic company
- Binary official source files remain outside the Git repository
