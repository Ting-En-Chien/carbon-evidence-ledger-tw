# EU CBAM Data-Role Mapping (Phase 6B)

## What is CBAM?

The EU Carbon Border Adjustment Mechanism (CBAM) is a European Union policy that
requires importers to report embedded greenhouse-gas emissions for certain
goods. Over time, it may also require payment for those emissions through CBAM
certificates.

This project does **not** calculate CBAM certificate liability, produce CBAM
declarations, or perform formal customs classification.

## CBAM is an optional downstream adapter

**CBAM is an optional adapter. The core Carbon Evidence Ledger can be used
without CBAM.**

The Carbon Evidence Ledger ingests activity evidence, normalizes units, matches
emission factors, calculates emissions where ready, and classifies records under
the GHG Protocol. All of that work remains framework-neutral.

The CBAM adapter is applied only when a CBAM product scenario is explicitly
configured. If your company:

- does not export relevant goods to the European Union,
- has products outside CBAM Annex I,
- only needs corporate GHG accounting, or
- uses another policy framework,

you should **not** activate the CBAM adapter.

## When might a company activate the CBAM adapter?

A company might choose to activate the optional CBAM adapter when it needs to
prepare product-level data for a CBAM-covered export scenario — for example,
when an exporter wants to understand which activity records could support
embedded-emissions data preparation for a specific CN code.

Even then, this prototype only performs a **technical data-readiness mapping**.
It does not replace legal, customs, or assurance review.

## Synthetic CN 7318 demonstration scenario

For this portfolio project, one synthetic scenario is configured:

- **Scenario ID:** `scenario_synthetic_cn7318_fasteners`
- **Assumed CN code:** 7318 (iron or steel fasteners)
- **Classification status:** `assumed_for_demo`

**The synthetic CN 7318 classification is a demonstration assumption, not a
formal customs determination.**

CN 7318 covers screws, bolts, nuts, and similar articles of iron or steel.
Regulation (EU) 2023/956 lists CN 7318 in both Annex I (covered goods) and
Annex II (direct-emissions-only goods).

## Annex I versus Annex II

| Concept | Meaning in this prototype |
| --- | --- |
| **Annex I in scope** | The assumed product is a CBAM-covered good category. |
| **Annex II direct only** | For this product, only **direct** embedded emissions are taken into account under current CBAM rules. |

For the synthetic CN 7318 scenario, both flags are `true`.

## Why only direct emissions matter for CN 7318

Regulation (EU) 2023/956 Article 7(1) and Annex II state that for goods listed
in Annex II — including CN 7318 — only direct emissions are taken into account
in the current CBAM embedded-emissions approach.

That means:

- fuel combusted inside the production-process boundary may be a direct-emissions
  candidate
- purchased electricity is **not** added to CBAM direct embedded emissions in
  this scenario, even though it may remain useful supporting evidence

**Corporate GHG accounting and CBAM product-data preparation are separate
decisions.**

## Baseline mapping results

These results come from the five synthetic activity records when the CN 7318
scenario is active:

| Record | Activity | mapping_status | cbam_relevance | data_role | Human review |
| --- | --- | --- | --- | --- | --- |
| `rec_electricity_001` | Grid electricity | excluded | supporting_only | supporting_energy_evidence | No |
| `rec_gas_001` | Heat-treatment natural gas | mapped | core_candidate | direct_emissions_activity_candidate | Yes |
| `rec_diesel_001` | Company-vehicle diesel | excluded | excluded | outside_process_boundary | No |
| `rec_steel_001` | Purchased steel wire rod | needs_review | data_gap | possible_precursor_candidate | Yes |
| `rec_output_001` | Finished-goods output | mapped | supporting_only | product_quantity_denominator_candidate | Yes |

## Record-by-record explanation

### Electricity — supporting evidence, excluded from embedded indirect emissions

Grid electricity is retained as **supporting energy evidence** because it can
help document factory operations. However, because CN 7318 is an Annex II
direct-only product, corporate Scope 2 electricity must **not** be copied into
CBAM direct embedded emissions.

### Natural gas — direct-emissions activity candidate

Natural gas used in heat treatment inside the CBAM production-process boundary
may support **direct embedded-emissions preparation**. This mapping is
independent of whether the carbon calculation is currently blocked (for example,
because a verified heating value is still missing).

### Company-vehicle diesel — outside the product-process boundary

Fuel used by a company vehicle is outside the synthetic fastener
production-process boundary. It may remain in the corporate GHG inventory, but
it must not be included as CBAM product-process direct emissions.

### Purchased steel — possible precursor data gap

A **precursor** is an input material whose embedded emissions may need to be
reported when it is obtained from another installation. Purchased steel may be
relevant, but the raw record does not prove:

- the exact precursor CN code
- the producing installation
- specific embedded emissions
- the production route

So the record is only a **possible precursor candidate** requiring human review.
A generic corporate Scope 3 estimate must not be substituted for verified CBAM
precursor data.

### Finished-goods output — product-quantity denominator evidence

Production output is not an emissions activity. It may support the **product
quantity denominator** needed to express embedded emissions per tonne of product.
It must not be treated as negative emissions or as a formal CN 7318 customs
determination.

## Why GHG Protocol Scope classifications cannot be copied into CBAM

Corporate GHG Protocol mapping answers: *Which Scope does this activity belong
to in the company inventory?*

CBAM mapping answers: *How may this record support product-level embedded-
emissions data preparation for a specific export scenario?*

These are different questions. For example:

- electricity is Scope 2 in GHG Protocol, but excluded from CBAM direct embedded
  emissions for Annex II CN 7318
- purchased steel is Scope 3 Category 1 in GHG Protocol, but only a possible
  precursor data gap in CBAM
- production output is not a GHG emissions activity, but may be denominator
  evidence in CBAM

The CBAM adapter never copies `ghg_scope`, calculated emissions, or factor
values into its output.

## Allowed use and prohibited use

Each CBAM rule includes:

- **allowed_use** — what the record may support after the stated conditions are met
- **prohibited_use** — what the record must not be used for

These fields make the mapping auditable and help prevent misuse, such as copying
corporate Scope 2 electricity into CBAM direct emissions or treating a purchase
quantity as verified precursor embedded emissions.

## Missing, multiple, or inconsistent product scenarios

The adapter fails closed to human review when:

| Situation | Result |
| --- | --- |
| No product scenario supplied | `needs_review` / `data_gap` for every activity |
| More than one scenario supplied | `needs_review` — Phase 6B does not silently pick one |
| Invalid or inconsistent scenario | `needs_review` with an explanatory rationale |
| Product outside Annex I | `not_applicable` for every activity |

The core pipeline continues to work in all of these cases. CBAM is never
required.

## Official references used in Phase 6B

1. **Regulation (EU) 2023/956** — establishes CBAM scope; CN 7318 in Annex I and II
2. **Commission Implementing Regulation (EU) 2025/2547** — methods for embedded
   emissions, system boundaries, precursors, and attribution
3. **European Commission screws-and-nuts communication-template example** — useful
   non-binding implementation example only

## Limitations and disclaimer

This prototype is **not legal, customs, assurance, or compliance advice**.

Phase 6B does **not** include:

- CBAM certificate prices or liability
- full embedded-emissions calculations
- CBAM declarations
- formal CN classification
- IFRS S2 mappings
- CBAM-specific fields in core raw, normalized, or calculation tables

Human review is required for the synthetic scenario itself and for several
baseline mappings.

## How to run the CBAM adapter

```python
from pathlib import Path

from carbon_ledger.cbam import (
    evaluate_cbam,
    load_cbam_product_scenario,
    load_cbam_references,
    load_cbam_rules,
)

config_dir = Path("config")
reference_dir = Path("data/reference")

rules = load_cbam_rules(config_dir)
references = load_cbam_references(reference_dir)
scenario = load_cbam_product_scenario(config_dir)

# activity_records should be accepted records from ingestion
cbam_results = evaluate_cbam(activity_records, rules, references, scenario)
```

If `scenario` is empty, the adapter still returns one review row per activity
without breaking the core ledger.
