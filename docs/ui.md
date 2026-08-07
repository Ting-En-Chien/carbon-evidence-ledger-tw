# Carbon Evidence Ledger UI (Phase 8 + Phase 9A)

## Intended user

Primary users are not programmers and may be new to carbon accounting,
CBAM, IFRS S2, emission factors, and QA terminology.

## Visual design direction

Phase 8 established a clean SaaS application shell with meaningful charts.
Phase 9A adds a Data Intake wizard that matches the same SaaS visual system.

Shared traits:

- top toolbar + left sidebar navigation
- compact page headers
- KPI cards with subtle status accents
- Streamlit-native Vega-Lite charts only (`st.vega_lite_chart`)
- bilingual chart titles, legends, and one-sentence explanations
- no custom SVG / chart HTML / dumped Vega JSON in the UI

## Navigation

1. Dashboard
2. Data Intake (Phase 9A)
3. Activity Data
4. Issues & Actions
5. Frameworks
6. Audit & Export

## Data Intake (Phase 9A)

Wizard steps: upload → map columns/values → confirm → validation result.

Uploaded CSV/XLSX files stay in memory. Validated intake does **not** replace
the demo pipeline result in this phase. See `docs/data_intake.md`.

## Bilingual architecture

`src/carbon_ledger/ui/i18n.py` is the single translation source.

## Limitations

Synthetic demo analysis remains the calculation source until Phase 9B.
No PDF extraction and no uploaded-data carbon calculation in Phase 9A.
