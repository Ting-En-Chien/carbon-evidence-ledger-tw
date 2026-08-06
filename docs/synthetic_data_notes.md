# Synthetic Data Notes — Phase 2

This note explains the first transparent synthetic dataset used by the Carbon
Evidence Ledger project.

## Why synthetic data is used

The project needs realistic activity records so the data pipeline can be tested
end to end. Real company operational data is private and must not be committed
to a public repository without explicit permission.

Synthetic records let learners and reviewers inspect every value, every source
document link, and every boundary field without exposing confidential business
information.

Company-level and regulatory references are based on public sources.
Activity-level records are synthetic and used only to test the data pipeline.
They are not presented as actual company operational data.

## Fictional company

All Phase 2 documents use:

**Demo Fasteners Taiwan Ltd. (Synthetic)**

None of the records represent a real company, real utility account, real
supplier, or real production site. Issuers such as "Demo Taiwan Power Utility
(Synthetic)" are also fictional labels created for testing.

## The five synthetic records

| # | Activity | Source document | What it represents |
|---|----------|-----------------|--------------------|
| 1 | Factory purchased electricity | `electricity_bill_2024_01.json` | 50,000 kWh of grid electricity for January 2024 |
| 2 | Heat-treatment natural gas | `natural_gas_invoice_2024_01.json` | 8,000 m3 of natural gas used in heat treatment |
| 3 | Company-vehicle diesel | `diesel_receipt_2024_01.json` | 1,200 L of diesel for a company-owned vehicle |
| 4 | Purchased steel wire rod | `steel_purchase_invoice_2024_01.json` | 150 t of purchased steel wire rod |
| 5 | Finished fastener output | `production_log_2024_01.json` | 95 t of finished synthetic M10 steel fasteners |

These quantities are **plausible test placeholders**. They are sized to be easy
to read in examples and interviews. They are **not** verified operational data
and must not be treated as real emissions evidence.

## How each activity record links to a source document

Every activity row in `data/raw/activity_records.csv` contains a
`source_document_id` that matches one row in `data/raw/source_documents.csv`.

Each source-document row points to a JSON file under
`data/raw/synthetic_documents/` through `file_name`.

The `source_locator` field tells a reader which JSON value was extracted. For
example:

- electricity → `json_path:$.electricity_usage_kwh`
- natural gas → `json_path:$.natural_gas_usage_m3`
- diesel → `json_path:$.diesel_quantity_litres`
- purchased steel → `json_path:$.purchased_quantity_tonnes`
- production output → `json_path:$.finished_goods_output_tonnes`

## Boundary fields used in the five records

| Record | Organizational boundary | CBAM process boundary |
|--------|-------------------------|------------------------|
| Electricity | `inside` | `inside` |
| Natural gas | `inside` | `inside` |
| Diesel (company vehicle) | `inside` | `outside` |
| Purchased steel | `outside` | `not_applicable` |
| Finished-goods output | `not_applicable` | `not_applicable` |

CBAM precursor or product-quantity **roles** are not stored on these raw
records. Those roles will be derived later by the rule engine.

## Why no carbon calculation is performed yet

Phase 2 only creates transparent evidence and activity facts. It does **not**:

- match emission factors
- calculate tCO2e
- assign GHG Protocol scopes
- assign CBAM data roles
- assign IFRS S2 readiness signals

Those steps belong to later phases. Keeping raw facts separate from derived
results is an intentional design rule.

## Files created in Phase 2

- `data/raw/synthetic_documents/*.json` — five fictional source documents
- `data/raw/source_documents.csv` — document register (five rows)
- `data/raw/activity_records.csv` — activity facts (five rows)
- `tests/test_synthetic_data.py` — checks that CSV and JSON stay consistent
- `docs/synthetic_data_notes.md` — this note

## Limitations remaining after Phase 2

- No SHA-256 provenance hashing yet
- No production ingestion module yet (tests parse CSV types locally)
- No emission factors or calculations
- No framework mapping rules
- Only five records (a later MVP may expand toward about 20–25 records)
- No products / production-process reference tables yet

## Important privacy reminder

Real private company data must never be committed to this repository without
permission. If a future private pilot is performed, real source files must stay
out of Git and only approved synthetic or anonymized examples may remain public.
