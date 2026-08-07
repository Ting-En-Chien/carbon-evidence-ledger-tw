# Structured company-data intake (Phase 9A)

Phase 9A adds a beginner-friendly **upload → map → validate** wizard for
real company CSV/XLSX files.

## Why intake is separate from calculation

Incorrect column or value mapping must never silently become a carbon
calculation. Phase 9A therefore stops after canonical schema validation and
accepted/rejected preview. Connecting accepted rows into normalization,
calculation, GHG Protocol, CBAM, IFRS S2, and QA is reserved for Phase 9B.

## Supported file types

- CSV (UTF-8 / UTF-8 BOM)
- XLSX (openpyxl; sheet selector when multiple sheets exist)

Not supported yet: PDF, images, scanned invoices, XLS, XLSM, Google Sheets URLs,
or OCR.

Maximum upload size: **10 MB**.

## Template format

The blank downloadable template columns are:

`activity_type,activity_value,unit,activity_start_date,activity_end_date`

No sample rows are included in the download. An on-screen example preview is
shown separately and is never imported.

## Column mapping

Users confirm which uploaded columns mean:

- activity type
- activity amount
- unit
- start/end dates **or** one shared reporting period

Deterministic alias suggestions are provided for common English/Chinese headers.
Suggestions are user-confirmable; nothing is auto-forced.

## Value mapping

Distinct uploaded activity-type and unit values are listed. Users map each
value to a canonical activity type / unit. Conservative aliases (for example
`電力` → `grid_electricity`, `度` → `kWh`) are suggestions only.

## Deterministic provenance IDs

- `source_document_id`: `upload_<first 12 sha256 chars>`
- activity `record_id`: `up_<sha12>_r0002`
- `source_locator`: `row:2` or `sheet:Sheet1,row:2`
- `sha256`: SHA-256 of exact uploaded bytes

Identical bytes + mapping + metadata produce identical IDs.

## Conservative default fields

Fields the beginner did not supply (ownership, process use, CBAM boundary,
measurement method, and similar) default to `unknown` / `not_applicable` as
appropriate. Unknown controlled fields keep `human_review_status = needs_review`.

## Validation and accepted / rejected rows

Canonical source-document and activity rows are validated with the existing
Pandera schemas. Valid rows remain previewable when other rows fail. Rejected
rows show source row, field, issue code, human-readable message, and uploaded
value.

## No persistent storage

Uploaded company files are processed in memory (`bytes` / `BytesIO`) only.
They are not written under `data/raw`, not committed to Git, and not sent to
external APIs or AI services.

## Current limitations / Phase 9B

Phase 9A does **not**:

- replace the demo `PipelineRunResult`
- run normalization, factor matching, calculation, GHG, CBAM, IFRS S2, or QA
- extract PDF invoices

Phase 9B will connect accepted intake rows into the auditable calculation path.
