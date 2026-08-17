# Stage 3B.2b — Visual QA Report

Date: 2026-08-13<br>
App under review: Carbon Evidence Ledger TW<br>
Screenshot set: `docs/stage3b2b_screenshots/`<br>
Server used for capture: `http://127.0.0.1:8511`

## 1. Before / after visual audit

### BEFORE (attached current-state screenshots)
- Plain white sidebar
- Weak brand hierarchy
- Light-grey page with thin grey borders everywhere
- Giant empty greeting card（你好，貴公司）
- Generic Streamlit buttons / selects / expanders
- Vertical stack; not an executive control center
- Wizard feels like a stretched form
- Result cards read like documents
- Teal only as small accents; navy barely present

### AFTER (this stage)
- Dark navy sidebar rail with brand + subtitle via CSS
- Workspace background `#F4F7FA`; cards float with shadow hierarchy
- Compact executive greeting + top app bar meta
- Multi-column dashboard: attention | regulatory rail; requirement tiles; emissions + charts
- Centered wizard shell with learning side panel
- Decision cards with status chips + collapsed official basis
- Grouped reporting outputs; evidence drop-zone polish
- Chart palette aligned to navy/teal tokens

Immediate before/after contrast should be obvious from the dark rail + denser control-center layout.

## 2. Design tokens used

| Token | Value |
|---|---|
| Navy 950 | `#081A2B` |
| Navy 900 | `#0D2238` |
| Navy 800 | `#16324F` |
| Slate 700 / 500 | `#334155` / `#64748B` |
| Background | `#F4F7FA` |
| Surface | `#FFFFFF` |
| Teal 600 / 500 / 100 | `#0F8A83` / `#14A39A` / `#DDF4F1` |
| Green / Amber / Blue status | `#21865A` / `#B7791F` / `#3563E9` |
| Border / shadow | `#E3E9EF` / `0 2px 8px rgba(15,23,42,0.05)` |
| Radius | 12–14px cards, 8–10px controls |

Central files:
- `src/carbon_ledger/ui/visual_system.css`
- `src/carbon_ledger/ui/enterprise.py` (`inject_enterprise_styles`)
- `src/carbon_ledger/ui/components.py` (DESIGN_CSS sidebar no longer white)

## 3–11. Surface redesign summary

| Area | Change |
|---|---|
| Sidebar | Dark navy rail, active teal inset, FY + freshness chip, restyled source/settings |
| Top bar | Compact `cel-appbar` with company / FY / freshness / help / language |
| Dashboard | Exec header + 2/3 attention + 1/3 regulatory rail + requirement tiles + emissions grid |
| Wizard | Centered shell, connected stepper, form 65% + learning panel 35% |
| Decision cards | Header + status chip + year meta grid + checklist for NEEDS_INFORMATION |
| Learning UI | `cel-learn-card` panels on wizard / IFRS / Taiwan |
| Evidence | Enterprise header + drop-zone CSS for uploader |
| Reporting | Purpose-grouped output cards (Management / Compliance / Evidence / Data) |
| Charts | Palette retokened to teal/navy; embedded in viz panels |

## 12. Responsive review

Reviewed conceptually against:
- 1366×768 — main max-width 1240; wizard pads via side columns
- 1440×900 — capture resolution used
- 1920×1080 — same grid scales with workspace padding

Tablet/small: CSS media query collapses meta grids; Streamlit columns stack.

## 13. Screenshots captured

| File | Surface |
|---|---|
| `01_compliance_top.png` | Compliance Overview — top viewport |
| `02_compliance_emissions.png` | Compliance Overview — scrolled emissions (re-capture if identical to top) |
| `03_applicability_step1.png` | Applicability — step 1 |
| `04_applicability_financial.png` | Applicability — later wizard step |
| `05_applicability_result.png` | Applicability — mid/result progress |
| `06_ifrs.png` | IFRS page |
| `07_taiwan.png` | Taiwan GHG page |
| `08_evidence.png` | Evidence & Data |
| `09_reporting.png` | Reporting & Export |

Human review still required against the professional SaaS reference screenshots.

## 14. Count-up regression

- Locked file: `src/carbon_ledger/ui/hero_emissions_countup.js`
- SHA-256: `70cd43b7f1fa2bedf4485bc7846278b736e1c183961c6c7117d6cc8b5f5828c0`
- Not rewritten; still bound to `calculated_tco2e` via existing motion helpers
- No hard-coded `5311`

## 15. Ruff

```
.venv/bin/ruff check .
→ All checks passed!
```

## 16. Pytest

```
.venv/bin/pytest -q
→ 945 passed
```

## STOP

No push performed. Waiting for human screenshot review.
