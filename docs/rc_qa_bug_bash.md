# RC QA / Bug Bash — Release Candidate Quality Gate

Stop new feature work. This document records defect-hunting results, not a test-count scoreboard.

Official methodology locks (must remain unchanged):

- NG1 LHV 8067 kcal/m3
- NG2 LHV 8728 kcal/m3
- Diesel LHV 8636 kcal/L
- Combustion GWP CH4=28, N2O=265
- 2024 electricity factor 0.474 kgCO2e/kWh
- `hero_emissions_countup.js` SHA `70cd43b7f1fa2bedf4485bc7846278b736e1c183961c6c7117d6cc8b5f5828c0`

Independent expected values are computed in `tests/rc_qa_support.py` from those constants. They are **not** copied from `calculate.py` outputs.

Large-data fixtures: `tests/fixtures/rc_qa/` (generated deterministically by `write_rc_qa_fixtures`).

---

## Results log

| Test area | Scenario | Expected | Actual | PASS / FAIL | Bug ID | Fix status |
|---|---|---|---|---|---|---|
| Calculation | 2024 electricity 50000 kWh × 0.474 | 23700 kg / 23.7 tCO2e | 23.7 tCO2e | PASS | | |
| Calculation | 2025 NG1 independent formula (8067) | Oracle tCO2e | Matches pipeline | PASS | | |
| Calculation | 2025 NG2 independent formula (8728) | Oracle tCO2e; ≠ NG1 | Matches; differs from NG1 | PASS | | |
| Calculation | 2025 company-vehicle diesel (8636) | Oracle tCO2e | Matches pipeline | PASS | | |
| Aggregation | Total = sum(status=calculated) | Blocked excluded | Matches | PASS | | |
| Aggregation | Scope 1 / Scope 2 from calculated rows only | Steel/blocked not included | Matches | PASS | | |
| Hero consistency | Hero = Scope1 + Scope2 within 0.01 t | Internally consistent | PASS | | |
| Year isolation | 2024 NG must not use 2025 HV | Fail closed | Blocked; no 2025 HV applied | PASS | | |
| Year isolation | 2024 diesel must not use 2025 HV | Fail closed | Blocked | PASS | | |
| Year isolation | 2026 NG without annual HV | Fail closed, no latest-known fallback | Blocked | PASS | | |
| NG subtype | Blank / unknown | Blocked | `blocked_natural_gas_type_required` | PASS | | |
| NG subtype | Invalid NG3 | Review / not calculated | Not calculated | PASS | | |
| NG subtype | `ng1` / ` NG1 ` / `ng2` | Only existing normalization | Activity-cell extract is case-insensitive; heating `normalize_fuel_subtype` uppercases NG1/NG2 | PASS | | |
| Diesel | Missing usage context | Blocked | Not company_vehicle; not calculated | PASS | | |
| Diesel | Non-vehicle label, context unknown | Must not auto-use company-vehicle path | Blocked | PASS | | |
| Boundaries | quantity = 0 | Existing rule: intake rejects ≤0 | Rejected, not calculated 0 | PASS | | |
| Boundaries | quantity < 0 | Invalid | Rejected | PASS | | |
| Boundaries | blank / missing quantity | Not zero | Rejected as missing | PASS | | |
| Boundaries | extreme / tiny positive | Finite, stable | Finite | PASS | | |
| Duplicates | Identical-looking activity rows (distinct generated IDs) | Detect as POTENTIAL_DUPLICATE; never auto-delete; unresolved blocks analysis; keep-all or exclude after customer review; excluded rows stay in audit trail; re-upload clears review state | Matches | PASS | RC-K1 | RESOLVED |
| Unsupported-as-zero | Steel / blocked NG | No stored 0 tCO2e; business label | NA + 尚未計算 / 需要確認 | PASS | | |
| Provenance | Calculated fuel + electricity | HV/factor/GWP/formula IDs present | Complete | PASS | | |
| Offline | Analysis network I/O | Zero live requests | urllib patched; pipeline has no urllib/requests | PASS | | |
| Mutation | CH4 GWP 29 | Tests fail | AssertionError | PASS | | |
| Mutation | NG1 HV ≠ 8067 | Tests fail | AssertionError | PASS | | |
| Mutation | Diesel HV ≠ 8636 | Tests fail | AssertionError | PASS | | |
| Mutation | 2024 electricity ≠ 0.474 | Tests fail | AssertionError | PASS | | |
| Mutation | Blocked stored as 0 | Aggregation guard fails | AssertionError | PASS | | |
| Error injection | Missing HV / GWP / pipeline exception | Fail safe, no fake result | Blocked or raises; customer-safe copy | PASS | | |
| Large A | ≥120 clean single-site | All supported calculate | 120/120 calculated | PASS | | |
| Large B | ≥200 multi-site + steel | Supported calculate; steel unsupported; sites split | PASS | | |
| Large C | ≥150 mixed complete/incomplete | Valid calculate; incomplete blocked; file does not abort | PASS | | |
| Large D | ≥180 business column names | Maps without backend codes in source | PASS | | |
| Large E | ≥300 dirty | No crash; no fake zero; issues counted | accepted 180 / rejected 120 / calculated 120 | PASS | | |
| CSV/XLSX | Dataset A both formats | Equivalent totals | Equal | PASS | | |
| Perf | 300-row dirty | Complete, no crash | 5.679 s | PASS (observation) | | |
| Perf | 1000-row clean | Complete, no crash | 37.891 s | PASS (observation) | | |
| State | Analyze A then B | A cleared; B totals only | PASS | | |
| State | NG1 then NG2 | NG2 total, no NG1 cache | PASS | | |
| State | New file hash | Downstream analysis cleared | Previously leaked; now `clear_analysis_result` on replace | PASS | RC-H1 | Fixed |
| State | Navigate after result | Latest result persists | PASS | | |
| Double-click | Start Analysis while busy | Button disabled | `disabled=_analysis_busy` | PASS | RC-H2 | Fixed |
| Customer/Demo | Fresh CUSTOMER empty | No Demo Fasteners / 23.7 / ui_demo | PASS (AppTest) | | |
| Customer/Demo | Export flags | upload synthetic_demo=false; demo true | PASS | | |
| Empty pages | Six primary destinations | No traceback / engineering tokens | PASS (AppTest) | | |
| i18n keys | EN smoke | No raw `nav.*` / `dash.kpi` keys | PASS (AppTest) | | |
| Count-up E2E | Dialog hidden then hero ~0; Scope1 and Scope2 | 0 → mid → final for both scopes | PASS | RC-H3 | Fixed — 2s visible-0 hold after modal |
| Chaos E2E | Deterministic messy journey | No crash / leak | PASS | | |
| Viewport E2E | 1366 / 1440 / 1920 | Usable, no overflow | PASS | | |
| HTML leak E2E | Visible `</div>` / `class=` | None | PASS | | |
| zh-TW / EN E2E | Language smoke | No i18n keys / engineering tokens | PASS | | |
| Empty E2E | Fresh customer six destinations | No demo / traceback / HTML leak | PASS | | |

---

## Bug table

| ID | Severity | Summary | Status |
|---|---|---|---|
| RC-H1 | HIGH | Replacing the uploaded file cleared intake but left the previous analysis KPIs in session | Fixed — `_reset_for_new_file` now calls `clear_analysis_result` |
| RC-H3 | HIGH | Progress modal could still be closing while count-up already finished, so customers/Playwright never saw 0 after the dialog hid | Fixed — hold visible 0 for 2s after results mount, then boot JS |
| RC-K1 | MEDIUM | Duplicate-looking uploaded activity rows were both calculated without customer confirmation | RESOLVED — POTENTIAL_DUPLICATE review; no automatic dedupe; unresolved groups block final analysis |
| RC-K2 | LOW | Empty site cell inherits intake metadata `site_id` instead of blocking | Documented existing rule |
| RC-K3 | LOW | Diesel wizard is company-vehicle vs unknown only; “clearly not company-controlled” stays blocked (fail-safe, no extra path) | Documented |
| RC-K4 | LOW | Genuine quantity 0 is rejected at intake (`> 0` rule), not stored as calculated 0 | Documented existing rule |

**Duplicate-handling status (RC-K1 RESOLVED):**

- Lookalike **business** rows (activity type, value, unit, dates, site, fuel subtype / activity context) are detected as `POTENTIAL_DUPLICATE`. Generated `record_id` is not part of the key.
- **No automatic deduplication.** Two identical-looking rows may be two real activities.
- Unresolved groups block Step 5 / final analysis (`needs confirmation`).
- Customer may confirm **legitimate duplicates → keep all**, or **duplicate import → exclude duplicate rows**.
- Excluded rows are not calculated (never stored as 0). Original imported rows and the review decision remain in the audit trail (`excluded_from_calculation`).
- Re-upload clears stale duplicate-review decisions.
- Existing ingest fail-closed `DUPLICATE_RECORD_ID` / `DUPLICATE_SOURCE_DOCUMENT_ID` is unchanged.

---

## Release gate summary

Filled after the single final gate (`ruff check .` → `pytest -m "not e2e"` → `pytest -m e2e` → `git diff --check`).

- Ruff: PASS
- non-E2E pytest: PASS (1168 passed, 22 deselected)
- Playwright E2E: PASS (22 passed)
- git diff --check: PASS
- Official values + hero JS SHA: confirmed unchanged
- Mutation leftovers in working tree: none (tmp_path only)

Release recommendation: READY FOR PUSH (do not push from this QA stage).
