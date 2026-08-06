# GHG Protocol Mapping — Phase 6A

This note explains deterministic GHG Protocol classification.

**GHG Protocol classification and emissions calculation are separate
decisions.**

A record may receive a Scope classification even when its emissions calculation
is currently blocked.

## What Scope 1, Scope 2, and Scope 3 mean

| Scope | Meaning |
|-------|---------|
| **Scope 1** | Direct emissions from owned or controlled sources |
| **Scope 2** | Indirect emissions from purchased electricity, heat, or steam |
| **Scope 3** | Other indirect value-chain emissions |

Phase 6A also supports:

- `not_applicable` for non-emissions operational evidence
- `unknown` when human review is required

## Why GHG classification is separate from emissions calculation

Classification answers: *What kind of inventory source is this?*

Calculation answers: *How many kgCO2e or tCO2e can we compute right now?*

Those questions use different inputs. Classification can be known before a
verified heating value exists.

## Why blocked natural-gas and diesel calculations can still be Scope 1

Natural gas in a controlled heat-treatment furnace is still a direct Scope 1
source even if the heating value needed for calculation is missing.

Company-vehicle diesel is still a direct Scope 1 mobile source even if the
diesel-to-TJ conversion is missing.

In those cases:

- GHG mapping: `mapped` → `scope_1`
- Calculation status (from Phase 5C): `blocked_missing_conversion`

## Why purchased electricity is Scope 2

Purchased grid electricity used inside the organizational boundary is an
indirect Scope 2 source under the GHG Protocol Corporate Standard.

## Why purchased steel is Scope 3 Category 1

Purchased steel is a purchased material input. Under the Scope 3 Standard it
belongs to Category 1: Purchased Goods and Services.

This remains true even when `organizational_boundary_status = outside`, because
Scope 3 activities occur outside owned or controlled operations.

## Why finished output is not an emissions activity

Finished-goods output is operational or denominator evidence. It is not itself
a greenhouse-gas emission source and must not be treated as negative emissions.

## Why organizational boundary matters

For Scope 1 and Scope 2, the activity must normally be inside the corporate
inventory boundary.

If a direct-emission activity is explicitly `outside`:

- mapping status = `outside_boundary`
- Scope 1 / Scope 2 is not assigned

## Why unknown or inconsistent data goes to human review

Examples:

- unknown activity type
- unknown organizational boundary
- unknown ownership
- natural gas owned by a third party
- diesel without `company_vehicle` process use

Phase 6A does not guess. It returns:

- `mapping_status = needs_review`
- `ghg_scope = unknown`
- `requires_human_review = true`

## What allowed_use and prohibited_use mean

Every evaluation preserves:

- **allowed_use** — what the classification may support
- **prohibited_use** — what it must not be stretched to mean

Example: Scope 2 electricity classification does **not** by itself determine an
EU CBAM embedded-emissions role or IFRS S2 compliance.

## Why GHG classification does not determine CBAM or IFRS S2 conclusions

GHG Protocol, EU CBAM, and IFRS S2 answer different questions.

- GHG Protocol: corporate inventory Scope
- CBAM: product / production-process data roles (later phase)
- IFRS S2: climate-data readiness signals (later phase)

Do not collapse them.

## Official references used

1. GHG Protocol Corporate Accounting and Reporting Standard  
   `ref_ghgp_corporate_standard`

2. Corporate Value Chain (Scope 3) Accounting and Reporting Standard (2011)  
   `ref_ghgp_scope3_standard`

## Baseline mappings for the five synthetic activities

| Record | Status | Scope | Mapping code |
|--------|--------|-------|--------------|
| Electricity | mapped | scope_2 | scope2_purchased_electricity |
| Natural gas | mapped | scope_1 | scope1_stationary_combustion |
| Diesel | mapped | scope_1 | scope1_mobile_combustion |
| Purchased steel | mapped | scope_3 | scope3_category1_purchased_goods_services |
| Finished output | not_applicable | not_applicable | not_emissions_activity |

## Current Phase 6A limitations

- No transport-category Scope 3 rules yet
- No emissions values are produced here
- No company-level Scope totals
- No CBAM or IFRS S2 mappings
- Natural-gas Scope 1 currently requires `process_use = heat_treatment`
- Diesel Scope 1 currently requires `process_use = company_vehicle`
