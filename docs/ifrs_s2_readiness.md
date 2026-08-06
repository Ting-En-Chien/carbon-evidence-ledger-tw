# IFRS S2 Climate-Data Readiness (Phase 6C)

## What are IFRS S1 and IFRS S2?

The International Sustainability Standards Board (ISSB) issued two standards on
26 June 2023:

- **IFRS S1** — general requirements for sustainability-related financial
  information in general-purpose financial reports
- **IFRS S2** — climate-related disclosures, including governance, strategy,
  risk management, and metrics and targets

IFRS S2 is effective for annual reporting periods beginning on or after
1 January 2024. Whether an entity must apply these standards depends on
jurisdictional authorities — not on this prototype.

## IFRS S2 is an optional downstream readiness adapter

**The core Carbon Evidence Ledger works without IFRS S2.**

The ledger ingests evidence, normalizes units, matches factors, calculates
emissions where ready, and classifies records under the GHG Protocol. All of
that remains framework-neutral.

The IFRS S2 adapter is applied only when an explicit reporting context is
configured. It performs a **technical data-readiness assessment** — it does
**not** create an IFRS S2 report.

**This is a technical data-readiness assessment, not an IFRS S2 compliance
assessment.**

The adapter does not make an applicability or compliance conclusion.

## Four IFRS S2 core content areas

IFRS S2 addresses climate-related disclosures under:

1. Governance
2. Strategy
3. Risk management
4. Metrics and targets

**The activity ledger currently supports only part of the metrics-and-targets
evidence needed for IFRS S2.**

Phase 6C addresses **metrics-and-targets data readiness only**.

## What activity-level carbon data cannot assess

Activity records in this prototype cannot determine:

| Area | Why not |
| --- | --- |
| Governance | No board or management oversight evidence |
| Strategy | No climate strategy or business-model evidence |
| Risk management | No climate risk identification or management process |
| Financial materiality | No materiality assessment has been performed |
| Reporting completeness | Only a limited synthetic period and five activities |
| Jurisdictional applicability | Not assessed in the baseline context |

**Governance, strategy, risk management, materiality, financial effects, and
reporting completeness require additional evidence and human judgement.**

## Synthetic reporting context

| Field | Baseline value |
| --- | --- |
| context_id | `context_synthetic_ifrs_s2_readiness` |
| assessment_purpose | `data_readiness_only` |
| applicability_status | `not_determined` |
| reporting period | 2024-01-01 to 2024-12-31 |
| jurisdictional_requirement_status | `not_assessed` |
| materiality_assessment_status | `not_performed` |
| amendments_2025_application_status | `not_applied` |

`applicability_status = not_determined` permits technical readiness mapping
but never permits a compliance or materiality conclusion.

## Baseline readiness results

| Record | mapping_status | readiness_status | data_role |
| --- | --- | --- | --- |
| `rec_electricity_001` | mapped | partial_evidence | scope_2_ghg_emissions_evidence_candidate |
| `rec_gas_001` | mapped | data_gap | scope_1_stationary_combustion_evidence_candidate |
| `rec_diesel_001` | mapped | data_gap | scope_1_mobile_combustion_evidence_candidate |
| `rec_steel_001` | mapped | data_gap | scope_3_category1_evidence_candidate |
| `rec_output_001` | supporting_only | supporting_only | industry_metric_or_intensity_denominator_candidate |

Every baseline result requires human review.

## Record-by-record explanation

### Electricity — partial Scope 2 evidence

Grid electricity has a validated calculation and a GHG Protocol Scope 2
classification. This may support **partial** Scope 2 greenhouse gas emissions
information under IFRS S2 paragraph 29(a).

It is **not** fully ready because:

- only limited-period synthetic evidence exists
- full annual reporting-period completeness is not demonstrated
- materiality has not been assessed
- entity-wide reporting coverage is not demonstrated

### Natural gas and diesel — Scope 1 data gaps

Natural gas and diesel are classified as Scope 1 emission sources, but
calculations are blocked because verified heating-value conversions are missing.
The records remain **relevant evidence streams** with identified data gaps.

They must not be reported as zero emissions or as complete Scope 1 disclosures.

### Purchased steel — Scope 3 Category 1 data gap

Purchased steel is classified as Scope 3 Category 1, but no emissions
calculation is configured. The record identifies an upstream evidence stream
and missing supplier or estimation data.

It must not be presented as measured Scope 3 emissions.

### Finished-goods output — supporting metric candidate

Production output is not a greenhouse-gas emission. It may support a future
emissions-intensity denominator or industry-based metric after a metric
definition and allocation method are chosen.

It must not be treated as emissions or as an automatically required IFRS S2
metric.

## GHG Protocol and IFRS S2 are separate decisions

GHG Protocol classification answers: *Which Scope does this activity belong to
in the corporate inventory?*

IFRS S2 readiness answers: *How may this record support climate-related
metrics-and-targets disclosure preparation?*

A record may be Scope 1 in GHG Protocol but still a data gap for IFRS S2 if
calculation is blocked. Electricity may be calculated and Scope 2 but only
partial evidence for IFRS S2.

## IFRS S2 readiness and CBAM are separate decisions

**IFRS S2 readiness and EU CBAM product-data preparation are separate
decisions.**

The IFRS S2 adapter does not use CBAM results. CBAM mapping is not required
before IFRS S2 readiness is evaluated.

## Traceability without duplicating values

For each activity, the readiness output preserves:

- `source_calculation_id` — links to the Phase 5C calculation result
- `source_ghg_evaluation_id` — links to the Phase 6A GHG Protocol evaluation

The output does **not** copy `calculated_kgco2e`, `calculated_tco2e`,
`factor_value`, `ghg_scope`, or `scope3_category`. Source IDs provide
traceability without duplicating framework-specific outputs.

## December 2025 amendments

The ISSB issued Amendments to Greenhouse Gas Emissions Disclosures in December
2025, effective for annual periods beginning on or after 1 January 2027, with
early application permitted.

The synthetic 2024 reporting context does **not** early-apply these amendments
(`amendments_2025_application_status = not_applied`).

## Reporting-context behavior

| Situation | Result |
| --- | --- |
| One valid context | Readiness rules applied; `not_determined` still permits assessment |
| Empty context | `needs_review` / `data_gap` for every activity |
| Multiple contexts | `needs_review` — Phase 6C does not silently pick one |
| Invalid context | `needs_review` with explanatory rationale |
| `applicability_status = not_applicable` | `not_applicable` for every activity |

## Current Phase 6C limitations

This prototype does **not** include:

- full IFRS S2 disclosures or compliance scoring
- legal applicability or financial materiality conclusions
- climate-risk, scenario, or resilience analysis
- climate targets, transition plans, or financial-effects calculations
- company-level GHG totals
- CBAM fields or rules
- new emissions calculations or GHG Protocol rules

Human review is required for every baseline result.

## How to run the IFRS S2 adapter

```python
from pathlib import Path

from carbon_ledger.calculate import calculate_activity_emissions
from carbon_ledger.ifrs_s2 import (
    evaluate_ifrs_s2_readiness,
    load_ifrs_s2_references,
    load_ifrs_s2_reporting_context,
    load_ifrs_s2_rules,
)
from carbon_ledger.match_factors import match_activity_factors
from carbon_ledger.normalize import normalize_activity_records
from carbon_ledger.rules import (
    evaluate_ghg_protocol,
    load_ghg_protocol_references,
    load_ghg_protocol_rules,
)

# After ingestion, use accepted activity records and upstream pipeline outputs.
readiness = evaluate_ifrs_s2_readiness(
    activity_records,
    calculation_results,
    ghg_evaluations,
    load_ifrs_s2_rules(Path("config")),
    load_ifrs_s2_references(Path("data/reference")),
    load_ifrs_s2_reporting_context(Path("config")),
)
```

If the reporting context is empty, the adapter still returns one review row per
activity without breaking the core ledger.
