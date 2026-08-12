# Regulatory source coverage report (Stage 3A.4)

Date: 2026-08-12  
Stage: **3A.4 — durable freshness persistence** (not Stage 3B)

## Status legend (strict)

| Status | Meaning |
|--------|---------|
| **VERIFIED_AUTHORITATIVE** | Grounded in FSC LAW/REGULATION, FSC ORDER, or TWSE/TPEx official rule/announcement |
| **VERIFIED_OFFICIAL_GUIDANCE** | Official guidance / Q&A / reference materials |
| **PARTIAL** | Official URL/public summary captured; completeness incomplete |
| **REQUIRES_MANUAL_IFRS_ACCESS** | Topic registered; full IFRS paragraph text not retrieved |
| **SOURCE_NOT_YET_VERIFIED** | Research incomplete / source not yet checked |
| **NOT_COVERED_BY_CURRENT_ORDER** | Authoritative order fully reviewed; entity/topic outside its scope (legal silence ≠ research failure) |
| **PENDING_REVIEW** | Change detected or human review required; not operable as ACTIVE |
| **SUPERSEDED** | Retained historically; not active |

## Stage 3B readiness gate

| Required area | Coverage |
|---------------|----------|
| Taiwan general listed/OTC applicability | VERIFIED_AUTHORITATIVE |
| General annual-report IFRS requirements | VERIFIED_AUTHORITATIVE |
| Scope 1/2 assurance | VERIFIED_AUTHORITATIVE |
| Scope 3 timing | VERIFIED_AUTHORITATIVE |
| Taiwan-recognised IFRS version mechanism | VERIFIED_AUTHORITATIVE |
| Financial institution rule families | Separated (FHC / bank / bills) |
| Securities firm rule family | Separated (`TW_IFRS_S1_S2_SF`) |
| Futures commission merchant rule family | Registered + `OUT_OF_V1_SCOPE` |
| IFRS S1 four core areas | Official-source coverage with `REQUIRES_MANUAL_IFRS_ACCESS` + paragraph anchors |
| IFRS S2 four core areas | Official-source coverage with `REQUIRES_MANUAL_IFRS_ACCESS` + paragraph anchors |
| IFRS S2 Dec 2025 GHG amendments | International PARTIAL; Taiwan `NOT_YET_VERIFIED` |
| Official-source monitor | Implemented + **daily schedule enabled** (`17 16 * * *`) |
| Freshness / change detection / stale fail-safe | Implemented |
| Durable monitoring STATE | Branch `regulatory-monitor-state` (artifacts supplementary only) |
| Review persistence | PR branch `regulatory-update/<run-id>` (Issue fallback); CONTENT still human-approved |
| Freshness gate API | `get_regulatory_freshness()` with `state_source` provenance |
| Auto-activation blocked | Confirmed (`auto_activate_rules: false`) |

## Gap transitions (PREVIOUS → NEW)

| Gap | PREVIOUS STATUS | NEW STATUS | SOURCE THAT RESOLVED IT | DATE VERIFIED |
|-----|-----------------|------------|-------------------------|---------------|
| Securities firms under general AR rules | VERIFIED_AUTHORITATIVE (wrong family) | SUPERSEDED → dedicated SF family VERIFIED_AUTHORITATIVE | FL007040 Art.32-1 + 11403856095/56094 | 2026-08-12 |
| Futures commission merchants | Missing | VERIFIED_AUTHORITATIVE + OUT_OF_V1_SCOPE | FL021990 Art.34-1 + 11403856096/56094 | 2026-08-12 |
| Non-listed SF under 56095 | Ambiguous | NOT_COVERED_BY_CURRENT_ORDER | 11403856095 | 2026-08-12 |
| Static regulatory import assumption | Architecture gap | Continuous monitor + freshness gates | Stage 3A.2 monitor | 2026-08-12 |

## Entity-type families supported

- `general_listed_company`
- `general_otc_company`
- `financial_holding_company`
- `bank`
- `bills_finance_company`
- `securities_firm`
- `futures_commission_merchant`
- `other`
- `unresolved`

Future applicability engines must identify entity type **before** selecting a rule family.

## Taiwan — securities firms

| Area | Coverage | Notes |
|------|----------|-------|
| Rule family | VERIFIED_AUTHORITATIVE | FL007040 Art.32-1 |
| Applicability schedule | VERIFIED_AUTHORITATIVE | 11403856095 points 2(1)–(3) |
| Reporting / filing timing | VERIFIED_AUTHORITATIVE | Apply FY / file following year with financial reports |
| Scope 1 / 2 + assurance | VERIFIED_AUTHORITATIVE | Order point 4 |
| Scope 3 timing | VERIFIED_AUTHORITATIVE | Fourth FY after first application |
| Recognised IFRS version | VERIFIED_AUTHORITATIVE | 11403856094 |
| Capital measurement basis | VERIFIED_AUTHORITATIVE | Admin Rules Art.21 latest FS |
| Non-listed SF outside order | NOT_COVERED_BY_CURRENT_ORDER | Explicit legal silence |

## Taiwan — futures commission merchants

| Area | Coverage | Notes |
|------|----------|-------|
| Rule family | VERIFIED_AUTHORITATIVE | FL021990 Art.34-1 |
| Applicability / assurance / Scope3 | VERIFIED_AUTHORITATIVE | 11403856096 |
| Recognised IFRS version | VERIFIED_AUTHORITATIVE | 11403856094 |
| Product support | OUT_OF_V1_SCOPE | Family registered, not silently omitted |
| Later non-sustainability amendments | PARTIAL / FUTURE | Example of provision-level effective dates (FY2028 package) |

## IFRS S1 / S2

Four core content areas have official public paragraph anchors from IFRS Foundation education/mapping materials, retained as `REQUIRES_MANUAL_IFRS_ACCESS` (not upgraded to VERIFIED_AUTHORITATIVE merely because a mapping tool shows a paragraph number).

December 2025 IFRS S2 GHG amendments:

- International: PARTIAL (official project page)
- Taiwan recognition: `NOT_YET_VERIFIED` (must not auto-activate)

## Freshness architecture

| Capability | Status |
|------------|--------|
| Official-source monitor (`regulatory_monitor.py`) | Present |
| Source freshness metadata | Present on sources + `source_freshness_state.csv` |
| Change detection (hash / ETag / Last-Modified / version) | Present |
| Change log | `data/regulatory/regulatory_change_log.csv` |
| Stale fail-safe states | `REGULATORY_DATA_STALE` / `UPDATE_REQUIRED` / `SOURCE_CHECK_FAILED` |
| Manual / on-demand refresh CLI | `python -m carbon_ledger.regulatory_monitor` |
| Scheduler readiness | Documented + optional GitHub workflow (dispatch; schedule commented) |
| Auto-activate legal rules | Disabled |

## Completeness statement

Stage 3A.2 closes the securities/FCM structural gaps and installs continuous monitoring foundations.

Stage **3B must not begin** until human review accepts remaining IFRS manual-access items and monitoring operationalization choices.
