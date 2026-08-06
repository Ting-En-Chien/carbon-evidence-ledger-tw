# Data Dictionary — Phase 1A

This document describes the first two raw-data tables in the Carbon Evidence
Ledger project. Phase 1A defines **what fields exist** and **how they are
validated**. It does **not** calculate emissions or perform regulatory
assessments.

---

## Overview

| Table | Purpose |
|-------|---------|
| `source_documents` | Register of evidence files (bills, invoices, receipts, logs) |
| `activity_records` | Individual operational facts extracted from those documents |

Every activity record must link to a source document through
`source_document_id`. Synthetic data is labelled on the **document**, not by
guessing later in the pipeline.

---

## `source_documents`

### What it means

This table answers: *Which document supports a number?* It stores metadata about
electricity bills, gas invoices, fuel receipts, purchase invoices, and
production logs. It does **not** store emissions totals or framework
classifications.

### Fields

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `source_document_id` | Yes | No | Unique identifier for the document |
| `file_name` | Yes | No | Human-readable file name |
| `document_type` | Yes | No | Kind of document (controlled vocabulary) |
| `document_date` | Yes | No | Document datetime as a pandas datetime value (`datetime64[ns]`, e.g. `pd.Timestamp`); not a free-text string |
| `issuer` | No | Yes | Who issued the document (utility, supplier, etc.) |
| `data_origin` | Yes | No | How the data was obtained (controlled vocabulary) |
| `is_synthetic` | Yes | No | `true` when the document is synthetic demo data |
| `source_path` | No (may be absent) | Yes | File path; added later by ingestion |
| `sha256` | No (may be absent) | Yes | File hash; added later by ingestion |
| `ingested_at` | No (may be absent) | Yes | Ingestion timestamp; added later by ingestion |
| `ingestion_run_id` | No (may be absent) | Yes | Pipeline run ID; added later by ingestion |
| `notes` | No | Yes | Free-text notes; **required** when `document_type = other` |

### Controlled vocabulary — `document_type`

| Value | Meaning |
|-------|---------|
| `electricity_bill` | Utility electricity bill |
| `natural_gas_invoice` | Natural gas supplier invoice |
| `fuel_receipt` | Fuel purchase receipt |
| `material_purchase_invoice` | Purchased materials invoice |
| `transport_invoice` | Transport service invoice |
| `production_log` | Production or output log |
| `other` | Other document type (notes required) |
| `unknown` | Type not yet determined (kept visible) |

### Controlled vocabulary — `data_origin`

| Value | Meaning |
|-------|---------|
| `synthetic_generated` | Created for this project's demo pipeline |
| `public_reference` | From a public reference source |
| `company_provided` | Provided by a company (not synthetic) |
| `unknown` | Origin not yet determined |

### Synthetic consistency

- `is_synthetic = true` requires `data_origin = synthetic_generated`
- `data_origin = synthetic_generated` requires `is_synthetic = true`

### Optional ingestion fields (Phase 1A)

These four fields are **added later by the ingestion / provenance process**:

- `source_path`
- `sha256`
- `ingested_at`
- `ingestion_run_id`

In Phase 1A they may be **entirely absent** from a `source_documents`
DataFrame. Pre-ingestion test data should omit them rather than fill them
with Python `None` values.

If `ingested_at` **is** present:

- it must be a real pandas datetime column (`datetime64[ns]`)
- a real `pd.Timestamp` is valid
- a missing value must be `pd.NaT` inside a datetime64 column
- a string such as `"2024-01-31"` is rejected (`coerce=False`; no silent conversion)

---

## `activity_records`

### What it means

This table answers: *What operational fact was recorded?* Examples include
electricity consumption, natural-gas use, diesel use, steel purchases, and
finished-goods production output.

Raw records store **source facts only**. They do **not** store:

- `calculated_tco2e` / `calculated_kgco2e`
- `emission_factor`
- `ghg_scope` / `scope3_category`
- `cbam_data_role` / `cbam_relevance`
- `ifrs_s2_relevance`

Those belong in derived tables (for example `calculations` and
`rule_evaluations`) in later phases.

### Fields

| Field | Required | Nullable | Description |
|-------|----------|----------|-------------|
| `record_id` | Yes | No | Unique identifier for the activity record |
| `source_document_id` | Yes | No | Link to supporting document |
| `source_locator` | Yes | No | Where in the document (page, row, sheet) |
| `record_type` | Yes | No | Semantic role of the record |
| `activity_start_date` | Yes | No | Start of activity period (pandas datetime / `datetime64[ns]`) |
| `activity_end_date` | Yes | No | End of activity period (pandas datetime; must be ≥ start) |
| `site_id` | Yes | No | Site or facility identifier |
| `production_process_id` | No | Yes | Production process, when relevant |
| `product_id` | No | Yes | Product identifier, when relevant |
| `activity_type` | Yes | No | Specific activity (electricity, gas, etc.) |
| `process_use` | No | Yes | How the activity was used (e.g. heat treatment) |
| `activity_value` | Yes | No | Numeric quantity (must be > 0) |
| `unit` | Yes | No | Unit of measure |
| `transport_payer` | No | Yes | Who paid for transport (transport records) |
| `ownership_control` | Yes | No | Asset or operational control relationship |
| `organizational_boundary_status` | Yes | No | Position relative to **corporate GHG boundary** |
| `cbam_process_boundary_status` | Yes | No | Position relative to **CBAM production-process boundary** |
| `measurement_method` | Yes | No | How the value was measured or obtained |
| `data_quality_tier` | Yes | No | Data quality classification |
| `human_review_status` | Yes | No | Whether a person must review this record |
| `notes` | No | Yes | Free-text notes; **required** when certain fields = `other` |

### Controlled vocabulary — `record_type`

| Value | Meaning |
|-------|---------|
| `emission_activity` | Energy or fuel consumption that may lead to emissions |
| `material_input` | Purchased material (e.g. steel wire rod) |
| `transport_activity` | Transport service activity |
| `production_output` | Production quantity (not an emissions activity) |
| `scrap_output` | Scrap or waste output |
| `other` | Other record type (notes required) |
| `unknown` | Type not yet determined |

### Controlled vocabulary — `activity_type`

| Value | Meaning |
|-------|---------|
| `grid_electricity` | Purchased grid electricity |
| `natural_gas` | Natural gas consumption |
| `diesel` | Diesel fuel consumption |
| `purchased_steel` | Purchased steel or wire rod |
| `third_party_transport` | Third-party transport service |
| `finished_goods_output` | Finished product output quantity |
| `scrap_output` | Scrap material output |
| `other` | Other activity (notes required) |
| `unknown` | Activity not yet classified |

### Controlled vocabulary — `process_use`

| Value | Meaning |
|-------|---------|
| `heat_treatment` | Used in heat-treatment process |
| `forging` | Used in forging process |
| `company_vehicle` | Used in a company-owned vehicle |
| `office_heating` | Office space heating |
| `general_factory` | General factory use |
| `other` | Other use (notes required) |
| `unknown` | Use not yet determined |
| `not_applicable` | Field does not apply to this record |

### Controlled vocabulary — `transport_payer`

| Value | Meaning |
|-------|---------|
| `exporter` | Exporting company paid |
| `supplier` | Supplier paid |
| `customer` | Customer paid |
| `third_party` | Another party paid |
| `unknown` | Payer not yet determined |
| `not_applicable` | Not a transport record |

### Controlled vocabulary — `ownership_control`

| Value | Meaning |
|-------|---------|
| `owned` | Company owns the asset |
| `controlled` | Company has operational control |
| `third_party` | Third party owns or controls |
| `unknown` | Not yet determined |
| `not_applicable` | Not relevant for this record |

### Controlled vocabulary — `organizational_boundary_status`

Describes position relative to the **corporate GHG inventory boundary**.

| Value | Meaning |
|-------|---------|
| `inside` | Inside the organizational boundary |
| `outside` | Outside the organizational boundary |
| `unknown` | Boundary position not yet determined |
| `not_applicable` | Not relevant (e.g. some output records) |

### Controlled vocabulary — `cbam_process_boundary_status`

Describes **boundary position only** relative to the CBAM
production-process boundary.

This field answers: *Is this activity physically inside or outside the CBAM
production-process boundary?*

It does **not** store CBAM data roles such as:

- precursor candidate
- product-quantity / denominator data
- supporting energy evidence
- direct-emissions input candidate

Those roles will be derived later by the rule engine and stored in
`rule_evaluations`, not in raw `activity_records`.

| Value | Meaning |
|-------|---------|
| `inside` | Inside the CBAM production-process boundary |
| `outside` | Outside the CBAM production-process boundary |
| `unknown` | Boundary position not yet determined |
| `not_applicable` | CBAM process-boundary position does not apply to this record |

### Controlled vocabulary — `measurement_method`

| Value | Meaning |
|-------|---------|
| `invoice` | Value taken from an invoice |
| `meter` | Meter reading |
| `purchase_record` | Purchase system record |
| `production_log` | Production log |
| `supplier_data` | Data from supplier |
| `estimate` | Estimated value |
| `other` | Other method (notes required) |
| `unknown` | Method not yet determined |

### Controlled vocabulary — `data_quality_tier`

| Value | Meaning |
|-------|---------|
| `primary` | Primary / direct measurement |
| `secondary` | Secondary data |
| `estimated` | Estimated data |
| `synthetic_test` | Synthetic demo data (use for public MVP) |
| `unknown` | Tier not yet assigned |

### Controlled vocabulary — `human_review_status`

| Value | Meaning |
|-------|---------|
| `not_required` | No human review needed now |
| `needs_review` | A person should review this record |
| `approved` | Reviewed and approved |
| `rejected` | Reviewed and rejected |

### Supported units

`kWh`, `MWh`, `m3`, `L`, `kg`, `t`

### Unit compatibility (activity_type → allowed unit)

| `activity_type` | Allowed `unit` |
|-----------------|----------------|
| `grid_electricity` | `kWh`, `MWh` |
| `natural_gas` | `m3` |
| `diesel` | `L` |
| `purchased_steel` | `kg`, `t` |
| `finished_goods_output` | `kg`, `t` |
| `scrap_output` | `kg`, `t` |

Other activity types must still use a supported unit, but are not restricted
further in Phase 1A.

---

## `unknown` vs `not_applicable`

| Term | Meaning |
|------|---------|
| `unknown` | The correct value is **not yet known**. The record should usually trigger `human_review_status = needs_review`. The system must not guess. |
| `not_applicable` | The field **does not apply** to this record type. This is intentional, not missing data. |

Example: company-vehicle diesel may have `organizational_boundary_status = inside`
but `cbam_process_boundary_status = outside` because the vehicle is outside the
product production-process boundary.

---

## Organizational boundary vs CBAM process boundary

These answer **different questions** and must stay in separate fields.

| Field | Question |
|-------|----------|
| `organizational_boundary_status` | Is this activity inside the company's GHG inventory boundary? |
| `cbam_process_boundary_status` | Is this activity inside the CBAM **production-process** boundary for the product being assessed? |

Example — factory electricity:

- Organizational boundary: often `inside` (counts toward corporate Scope 2)
- CBAM process boundary: may be `inside` for the factory process, but CBAM
  **data roles** (such as supporting energy vs direct input) are decided later
  by the rule engine — not stored here.

Example — company-vehicle diesel:

- Organizational boundary: `inside`
- CBAM process boundary: `outside`

Example — purchased steel wire rod:

- Organizational boundary: `outside` (upstream material input)
- CBAM process boundary: `not_applicable` (precursor role is derived later)

Example — finished fastener production output:

- Organizational boundary: `not_applicable` (not an emissions activity)
- CBAM process boundary: `not_applicable` (product-quantity role is derived later)

---

## Validation does not silently convert raw values

Phase 1A schemas use `coerce=False`. That means:

- Date/datetime fields (`document_date`, `activity_start_date`,
  `activity_end_date`) must already be pandas datetime values
  (`datetime64[ns]`, typically built with `pd.Timestamp`)
- If `ingested_at` is present, it must also be a pandas datetime column —
  not an all-`None` object column and not a string
- Raw date **strings** such as `"2024-01-01"` are **rejected** in Phase 1A
- `is_synthetic` must already be a boolean
- `activity_value` must already be numeric

If a CSV row contains a date string like `"2024-01-31"` or a number string like
`"50000"`, validation **rejects** the row instead of silently converting it.
Parsing CSV strings into pandas datetime values will happen later during the
ingestion phase, before schema validation of typed DataFrames.

---

## Derived roles are not stored on raw records

Raw `activity_records` do not store:

- GHG scope or Scope 3 category
- CBAM data roles (precursor candidate, product quantity, supporting energy, etc.)
- IFRS S2 relevance
- Calculated emissions

For example:

- Purchased steel may later receive a **precursor candidate** role in
  `rule_evaluations`, but the raw record only states that steel was purchased.
- Finished-goods output may later receive a **product-quantity** role in
  `rule_evaluations`, but the raw record only states how much was produced.

---

## Five first valid record examples

All supporting source documents use `is_synthetic = true` and
`data_origin = synthetic_generated`.

| # | Record | `record_type` | `activity_type` | `unit` | Key boundary notes |
|---|--------|---------------|-----------------|--------|-------------------|
| 1 | Factory purchased electricity | `emission_activity` | `grid_electricity` | `kWh` | Org `inside`, CBAM `inside` |
| 2 | Natural gas in heat treatment | `emission_activity` | `natural_gas` | `m3` | `process_use = heat_treatment`, org `inside`, CBAM `inside` |
| 3 | Diesel in company vehicle | `emission_activity` | `diesel` | `L` | `process_use = company_vehicle`, org `inside`, CBAM `outside` |
| 4 | Purchased steel wire rod | `material_input` | `purchased_steel` | `t` | Org `outside`, CBAM `not_applicable` |
| 5 | Finished fastener output | `production_output` | `finished_goods_output` | `t` | Org `not_applicable`, CBAM `not_applicable` |

All five examples use `data_quality_tier = synthetic_test`.

---

## Phase 1A limitations

Phase 1A provides:

- Controlled vocabularies in `domain.py`
- Pandera schemas in `schemas.py` with `coerce=False` (no silent type conversion)
- Tests in `tests/test_schemas.py`

Phase 1A does **not** yet provide:

- Synthetic CSV data files
- Foreign-key validation between tables (deferred to ingestion phase)
- SHA-256 provenance hashing
- Emission-factor matching or carbon calculations
- GHG Protocol, CBAM, or IFRS S2 mapping rules
- QA engine, DuckDB storage, or SQL views

This project does **not** yet calculate emissions or issue regulatory
assessments.
