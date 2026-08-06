# Provenance and Ingestion — Phase 3

This note explains how the Carbon Evidence Ledger reads raw evidence files,
checks them carefully, and keeps both accepted and rejected rows visible.

## What ingestion means

**Ingestion** is the step that brings raw files into a typed, checked form the
rest of the pipeline can trust.

In Phase 3, ingestion means:

1. Read `source_documents.csv` and `activity_records.csv` as text
2. Parse dates, booleans, and numbers **explicitly**
3. Validate rows with the existing Phase 1A Pandera schemas
4. Link each activity to its JSON evidence file
5. Compute a SHA-256 hash for each accepted evidence file
6. Separate rows into **accepted** and **rejected** results

Raw files are never overwritten.

## What provenance means

**Provenance** means knowing where a number came from.

For this project, provenance includes:

- which source document supports an activity record
- which JSON file holds the evidence
- which field inside that JSON was used (`source_locator`)
- the SHA-256 hash of the evidence file at ingestion time
- the ingestion run ID and timestamp

## What SHA-256 means

SHA-256 is a fingerprint of a file’s exact bytes.

- If the file content stays the same, the hash stays the same
- If even one byte changes, the hash changes

SHA-256 helps detect **unexpected file changes**.

It does **not** by itself prove that a document is truthful, complete, or
independently verified. It only proves that the bytes hashed at ingestion time
match the bytes you check later.

## Why raw files are not modified

Raw CSV and JSON files are the evidence archive for the demo pipeline.

Ingestion creates derived results in memory (and later, in later phases, in
processed outputs). Keeping raw files read-only protects:

- auditability
- reproducibility
- clear separation between source facts and derived results

## Why CSV values are parsed explicitly

Phase 1A schemas use `coerce=False`. They reject wrong types instead of quietly
converting them.

So Phase 3 parsing is deliberate:

- `"2024-01-31"` → pandas datetime
- `"true"` / `"false"` → real boolean (values such as `"yes"` or `"1"` are rejected)
- `"50000.0"` → finite float
- blank optional cells → missing values

This fail-closed approach avoids silent repairs.

## Why accepted and rejected records are both preserved

A professional evidence pipeline must not hide problems.

- **Accepted** rows passed parsing, schema checks, uniqueness, evidence-file
  checks, and (for activities) value matching
- **Rejected** rows remain visible with:
  - `row_number`
  - `record_id`
  - `rejection_stage`
  - `rejection_code`
  - `rejection_message`

Nothing is silently dropped.

## How a source document links to an activity record

1. `activity_records.source_document_id` must match an **accepted**
   `source_documents.source_document_id`
2. The source-document row’s `file_name` points to a JSON file under
   `synthetic_documents/`
3. The activity’s `source_locator` names the JSON field that holds the quantity
4. The JSON quantity must match `activity_value`

## How `source_locator` works in this limited MVP

Phase 3 supports only simple top-level locators, for example:

```text
json_path:$.electricity_usage_kwh
```

Supported form:

```text
json_path:$.field_name
```

Not supported yet:

- nested paths such as `json_path:$.a.b`
- filters, wildcards, or full JSONPath libraries

## Why path traversal is blocked

A file name such as `../../private_file.json` must not be allowed to escape the
`synthetic_documents` directory.

`resolve_source_file` rejects absolute paths and `..` segments, and confirms the
resolved path stays inside the documents directory.

## Baseline Phase 2 result

With the existing synthetic data:

- accepted source documents: **5**
- rejected source documents: **0**
- accepted activity records: **5**
- rejected activity records: **0**

Accepted source documents also receive:

- relative `source_path` (for example `synthetic_documents/electricity_bill_2024_01.json`)
- `sha256`
- `ingested_at`
- `ingestion_run_id`

## What Phase 3 does not do

Phase 3 does **not**:

- calculate emissions
- attach emission factors
- assign GHG Protocol scopes
- assign CBAM data roles
- assign IFRS S2 readiness
- convert units
- write DuckDB tables
- run a QA engine

## Current limitations

- Only top-level JSON locators are supported
- Ingestion results are returned in memory (no processed CSV export module yet)
- SHA-256 proves file integrity for the hashed bytes, not document truthfulness
- Duplicate IDs cause **all** affected rows to be rejected (fail closed)
- No command-line `run` subcommand yet beyond the package version entry point
