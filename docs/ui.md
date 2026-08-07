# Carbon Evidence Ledger UI (Phase 8 / 8B / 8C / 8D / 8E)

## Intended user

Primary users are not programmers and may be new to carbon accounting,
CBAM, IFRS S2, emission factors, and QA terminology.

## Visual design direction

Phase 8D established a clean SaaS application shell.
Phase 8E adds meaningful data visualization and richer semantic color without
returning to marketing-hero or custom SVG experiments.

Shared traits:

- top toolbar + left sidebar navigation
- compact page headers
- KPI cards with subtle status accents
- Streamlit-native Vega-Lite charts only (`st.vega_lite_chart`)
- bilingual chart titles, legends, and one-sentence explanations
- no custom SVG / chart HTML / dumped Vega JSON in the UI

## Dashboard visualizations

1. **活動計算狀態** — donut of calculation-status counts
2. **各活動目前狀態** — horizontal status bars per activity
3. **目前已能計算的排放量** — total plus contribution bars for calculated
   activities only (blocked rows never appear as zero)

## Framework / Issues visualizations

- GHG: activity classification counts (explicitly not emissions share)
- CBAM / IFRS: compact role / readiness count bars
- Issues: missing-data type bars

## Bilingual architecture

`src/carbon_ledger/ui/i18n.py` is the single translation source.
Chart category labels use the same friendly status helpers as tables.

## Limitations

Synthetic demo only. No historical trends, fake readiness scores, estimated
missing emissions, or company-wide totals beyond currently calculated rows.
