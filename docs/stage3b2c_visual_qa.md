# Stage 3B.2c — Visual Polish Fix 1 QA

## Root cause of visible `\A`
`visual_system.css` used `content: "...\\A ..."`. The doubled backslash wrote a **literal** `\A` into CSS instead of the CSS newline escape. Fixed by splitting brand into `::before` + `::after` with no newline escape.

## Status badge contrast
Sidebar `* { color: rgba(...) !important }` overrode chip text to near-white. Added explicit sidebar chip rules: bg `#E7F6EE`, text `#17643F`, dot `#21865A`. Measured: `rgb(231,246,238)` / `rgb(23,100,63)`.

## Top-bar alignment
Replaced stacked appbar + floating control row with one `st.columns` baseline: context | status | 說明 | 名詞解釋 | 語言.

## Spacing
Tightened main padding, exec header, appbar, card padding (~15–25%). Attention cards use `min-height` + flex reason area; CTAs `use_container_width`.

## Screenshots
`docs/stage3b2c_screenshots/`
- `01_sidebar_brand_top.png`
- `02_sidebar_fy_status.png`
- `03_compliance_overview_top.png`

## Verification
- No literal `\A` (computed `::before` / `::after` clean)
- Dark sidebar retained
- `hero_emissions_countup.js` unchanged (`70cd43b7…`)
- Ruff: All checks passed
- Pytest: 945 passed

No push.
