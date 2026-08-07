# Core Data-Quality Exception Register (Phase 7A)

## What is a data-quality exception register?

A data-quality exception register is a single, auditable list of technical
problems found while moving activity evidence through the core Carbon Evidence
Ledger pipeline.

Instead of leaving status codes scattered across ingestion, normalization,
factor matching, and calculation outputs, the register consolidates blocking
problems into one place so a human can see:

- which record is affected
- which pipeline stage failed
- why it failed
- what to do next
- what the record may still be used for
- what it must not be used for

**The exception register identifies technical data problems; it does not make
GHG Protocol, CBAM, IFRS S2, legal, customs, materiality, or compliance
conclusions.**

## Why consolidate pipeline statuses?

Each pipeline stage reports its own status. That is useful for debugging one
step, but it is hard to review as a whole. The exception register turns those
statuses into explicit open issues with recommended actions.

## Framework-neutral core feature

Phase 7A is part of the **framework-neutral** Carbon Evidence Ledger.

It uses only:

- ingestion rejections
- accepted activity records
- normalization results
- activity calculation-readiness results
- calculation results

It does **not** require GHG Protocol, EU CBAM, or IFRS S2 adapters.

Those optional adapters may receive separate human-review queues in a later
phase. They are excluded from Phase 7A so the core ledger remains usable on its
own.

## Ingestion rejection versus accepted-record issue

| Kind | Meaning |
| --- | --- |
| **Ingestion rejection** | A source-document or activity row never entered the accepted table. |
| **Accepted-record issue** | The record was accepted, but a later core stage blocked progress. |

Rejected rows must not be used in normalization, factor matching, calculation,
or reporting. They may remain as an audit trail.

## Normalization issues

These normalization statuses create issues:

- `invalid_value`
- `invalid_unit`
- `unsupported_activity_type`
- `unsupported_conversion`

These statuses are successful and create **no** issue:

- `already_canonical`
- `normalized`

When an upstream normalization issue exists, the register does not also create a
duplicate downstream calculation issue for the same invalid input.

## Missing-conversion issues

Natural gas and diesel may match emission factors but still be blocked when a
verified heating-value conversion is missing.

**A missing result is not zero.**

The register creates one `missing_conversion_dependency` issue and preserves the
`blocking_dependency` identifier so the required evidence can be collected.

## No-factor issues

Purchased steel currently has no configured emissions factor. The register
creates one `no_factor_configured` issue. The activity quantity may remain
visible as a data gap, but must not be replaced with zero or an undocumented
fallback.

## Factor-match inconsistencies

If the calculation layer reports `factor_match_inconsistent`, the register
creates a **critical** issue. Do not silently select a factor or report a
calculated value.

## Pipeline-result inconsistencies

The register requires exactly one normalization, readiness, and calculation
result for every accepted activity.

It also detects:

- missing results
- duplicated results
- orphan results whose `record_id` is not in accepted activities
- readiness/calculation status conflicts
- empty or schemaless source DataFrames

These become **critical** `pipeline_result_inconsistent` issues. Duplicate rows
are never silently selected.

## Why `not_emissions_activity` is not an error

Finished-goods output is operational quantity evidence, not an emissions
activity. A `not_emissions_activity` calculation status is successful for that
record type and does not create a QA issue.

## Source-document traceability

For accepted-activity issues, `source_document_id` is copied from the activity
record. The register does not invent document IDs, re-read JSON files, or
recompute hashes.

## Deterministic issue IDs

Activity issues use:

`qa_<record_id>_<issue_code>`

Ingestion rejection issues use:

`qa_ingestion_<record_kind>_row_<row_number>_<rejection_code>`

Components are lowercased and non-alphanumeric sequences become underscores.
No random values, hashes, or timestamps are used.

## Deduplication

**The same root cause must not be counted twice merely because it appears in
both readiness and calculation outputs.**

Example: natural-gas blocked conversion creates one missing-conversion issue,
not separate readiness and calculation issues.

## Severity ordering

Issues are sorted by:

1. severity (`critical`, `high`, `medium`, `low`, `info`)
2. `record_id` (blank IDs last)
3. `pipeline_stage`
4. `issue_code`
5. `issue_id`

## Baseline three-issue result

| record_id | issue_code | severity | source_status | blocking_dependency |
| --- | --- | --- | --- | --- |
| `rec_gas_001` | missing_conversion_dependency | high | blocked_missing_conversion | verified_natural_gas_heating_value_m3_to_TJ |
| `rec_diesel_001` | missing_conversion_dependency | high | blocked_missing_conversion | verified_diesel_heating_value_L_to_TJ |
| `rec_steel_001` | no_factor_configured | high | no_factor_configured | (blank) |

No baseline issue for:

- `rec_electricity_001` (calculated successfully)
- `rec_output_001` (not an emissions activity)

Every baseline issue requires human review.

## Current limitations

Phase 7A does **not** include:

- issue-resolution workflow, owners, or due dates
- timestamps or alerts
- company-level totals or compliance scores
- GHG-, CBAM-, or IFRS S2-specific review queues
- dashboards or visualization tools

## How to run the QA register

```python
from pathlib import Path

from carbon_ledger.qa import build_core_qa_issues, load_qa_rules

rules = load_qa_rules(Path("config"))
issues = build_core_qa_issues(
    activity_records,
    ingestion_rejections,
    normalized_records,
    activity_readiness,
    calculation_results,
    rules,
)
```
