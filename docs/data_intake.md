# Structured company-data intake (Phase 9A)

Phase 9A adds a beginner-friendly **upload → interpret → confirm → validate**
wizard for real company CSV/XLSX files.

Users should **not** need to rename spreadsheet columns to the application's
canonical field names. The system inspects workbook structure, suggests the
likely data worksheet and header row, proposes semantic column mappings, and
asks for confirmation before building canonical records.

## Why intake is separate from calculation

Incorrect column or value mapping must never silently become a carbon
calculation. Phase 9A therefore stops after canonical schema validation and
accepted/rejected preview. Connecting accepted rows into normalization,
calculation, GHG Protocol, CBAM, IFRS S2, and QA is reserved for Phase 9B.

## Supported file types

- CSV (UTF-8 / UTF-8 BOM)
- XLSX (openpyxl; worksheet ranking + confirmation when multiple sheets exist)

Not supported yet: PDF, images, scanned invoices, XLS, XLSM, Google Sheets URLs,
or OCR.

Maximum upload size: **10 MB**.

## Worksheet ranking

For multi-sheet workbooks, every worksheet is scored with deterministic
structural signals (tabular rows, numeric/date/unit/activity-like columns,
header-like rows). Sheet **names** are only a weak hint. Instruction/prose
sheets are ranked below real tabular activity data even when the data sheet is
named `Sheet2` or `abc123`.

## Header row detection

Excel row 1 is not assumed to be the header. The first scan window is inspected
for the most plausible header row. When uncertain, the UI asks which row
contains column names and shows a preview.

## Template format

The blank downloadable template columns are:

`activity_type,activity_value,unit,activity_start_date,activity_end_date`

No sample rows are included in the download. An on-screen example preview is
shown separately and is never imported. Canonical template uploads continue to
work unchanged.

## Column mapping

Users confirm which uploaded columns mean:

- activity type（活動類型）
- activity amount（活動數量）
- unit（單位）
- site / plant（廠區／場址） — optional
- start/end dates, **or** one year-month column, **or** one shared reporting period

Deterministic alias suggestions cover common English/Chinese business labels
such as `能源別`, `使用量`, `廠區`, and `年月`. Each suggestion carries an
internal confidence of high / medium / low. Low-confidence mappings are never
auto-selected. Users may override every suggestion.

Beginner UI shows business labels (for example `能源別 → 活動類型`). Canonical
names remain available under advanced details.

## Year-month periods

A single year-month column such as `2025-01`, `2025/01`, or `2025年1月` can be
confirmed as a monthly reporting period. After confirmation it becomes:

- start date = first calendar day of the month
- end date = last calendar day of the month

Leap years are handled correctly. Ambiguous date columns are never transformed
silently.

## Uploaded calculation columns

Columns such as `排放係數`, `排放量`, `CO2e`, or `計算結果` are treated as
source/reference only. They are not used as the application's factor registry
or calculated emissions truth. The controlled calculation path remains
unchanged and independent.

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
- modify calculation business-rule modules

Phase 9B will connect accepted intake rows into the auditable calculation path.
