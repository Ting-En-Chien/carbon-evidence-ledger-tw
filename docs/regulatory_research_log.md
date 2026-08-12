# Regulatory research log (Stage 3A / 3A.1 / 3A.2 / 3A.3 / 3A.4)

Purpose: make Taiwan / IFRS sustainability regulatory research reproducible and continuous.
This log records source checks only. It does **not** determine company compliance.

## Session 2026-08-12 — Stage 3A.4 persist regulatory freshness reliably

### Objective

Close the operational gap where successful `NO_CHANGE` checks left freshness only in Actions logs/artifacts. Persist durable MONITORING STATE (branch `regulatory-monitor-state`) separately from REGULATORY CONTENT. No additional regulatory research. No UI. No applicability. No carbon pipeline changes.

| Item | PREVIOUS STATUS | NEW STATUS | SOURCE THAT RESOLVED IT | DATE VERIFIED |
|------|-----------------|------------|-------------------------|---------------|
| Durable freshness SoT | Artifacts / review PR only | Branch `regulatory-monitor-state` + local `durable_state` + env override | workflow + `persist_monitoring_state()` | 2026-08-12 |
| NO_CHANGE persistence | No repo update | Always update freshness STATE; no review PR | workflow + monitor | 2026-08-12 |
| Freshness reader | Bundled CSV only | Prefer durable; fallback bundled; else `FRESHNESS_STATE_UNAVAILABLE` | `get_regulatory_freshness()` | 2026-08-12 |
| Cron congestion | `0 16 * * *` | `17 16 * * *` (non-zero minute) | workflow + yaml | 2026-08-12 |
| Persistence vs fetch failure | Not distinguished | `FETCH_FAILED` vs `STATE_PERSISTENCE_FAILED` | monitor + summary | 2026-08-12 |

---

## Session 2026-08-12 — Stage 3A.3 activate continuous monitoring

### Objective

Activate the Stage 3A.2 monitoring architecture so it runs automatically (daily GitHub Actions schedule), persists reviewable results, and exposes a freshness gate for future Stage 3B.

No additional broad regulatory research. No UI. No applicability engine. No carbon pipeline changes.

| Item | PREVIOUS STATUS | NEW STATUS | SOURCE THAT RESOLVED IT | DATE VERIFIED |
|------|-----------------|------------|-------------------------|---------------|
| Scheduled monitor | workflow_dispatch only; cron commented | Daily cron `0 16 * * *` + workflow_dispatch | `.github/workflows/regulatory-monitor.yml` | 2026-08-12 |
| Change persistence | Ephemeral runner risk | Review PR branch `regulatory-update/<run-id>` (+ Issue fallback) | workflow + change log/summary | 2026-08-12 |
| Freshness gate API | Partial helpers | `get_regulatory_freshness()` + `monitoring_summary.json` | `regulatory_monitor.py` | 2026-08-12 |
| Taiwan recognised IFRS monitoring | Present but not high-priority wired | High-priority daily sources include SFB download area + recognition orders | config + sources CSV | 2026-08-12 |

### Monitoring session metadata

| Field | Value |
|-------|-------|
| last successful source check | pending first scheduled/live run (`CHECK_DUE`) |
| detected changes | none at activation bootstrap |
| pending reviews | none |
| failed checks | none |
| unresolved conflicts | none |

---

## Session 2026-08-12 — Stage 3A.2 securities/FCM correction + continuous monitoring

### Objective

Close remaining structural gaps (securities firms, futures commission merchants, rule-level versioning, verification nuance) and introduce a scheduler-ready official-source monitoring architecture.

No Stage 3B Applicability. No carbon calculation pipeline changes. No extensive UI work.

### Gap corrections (audit trail)

| Topic | PREVIOUS STATUS | NEW STATUS | SOURCE THAT RESOLVED IT | DATE VERIFIED |
|-------|-----------------|------------|-------------------------|---------------|
| Securities firms under FL007032 via Art.2 non-exclusion | VERIFIED_AUTHORITATIVE (incorrect family) | SUPERSEDED; replaced by dedicated SF family | 證券商財務報告編製準則 Art.32-1 + 金管證券字第11403856095/56094號 | 2026-08-12 |
| Securities firm applicability / assurance / Scope3 / recognised version | Missing dedicated family | VERIFIED_AUTHORITATIVE (`TW_IFRS_S1_S2_SF`) | FL007040 + 11403856095 + 11403856094 | 2026-08-12 |
| Futures commission merchants | Omitted / unresolved | VERIFIED_AUTHORITATIVE family + `OUT_OF_V1_SCOPE` product support | FL021990 Art.34-1 + 11403856096 + 11403856094 | 2026-08-12 |
| Non-listed SF outside Order 56095 | Ambiguous / unresolved | NOT_COVERED_BY_CURRENT_ORDER | 11403856095 point 2 population | 2026-08-12 |
| General order 51756 covering SF/FCM | Implicit inheritance risk | NOT_COVERED_BY_CURRENT_ORDER boundary rule | 11403851756 vs 56095/56096 | 2026-08-12 |
| IFRS S1/S2 core paragraph anchors | PARTIAL About-page only | REQUIRES_MANUAL_IFRS_ACCESS with official education-mapping anchors | IFRS Foundation education mapping PDF | 2026-08-12 |
| Continuous monitoring architecture | Absent (static import assumption) | Implemented monitor + freshness + change log | Stage 3A.2 monitor layer | 2026-08-12 |

### Newly registered Taiwan laws / orders

- 證券商財務報告編製準則（FL007040）Art.32-1
- 金管證券字第11403856095號
- 金管證券字第11403856094號（SF/FCM recognised version）
- 期貨商財務報告編製準則（FL021990）Art.34-1
- 金管證券字第11403856096號

### Monitoring session metadata (initial)

| Field | Value |
|-------|-------|
| last successful source check | not yet run in production (freshness `CHECK_DUE`) |
| detected changes | none at registry bootstrap |
| pending reviews | none at bootstrap |
| failed checks | none at bootstrap |
| unresolved conflicts | none at bootstrap |

### Explicit non-actions

- No Stage 3B Applicability engine
- No auto-activation of legal rules from webpage diffs
- No UI overhaul
- No carbon calculation pipeline changes

---

## Session 2026-08-12 — Stage 3A.1 verified-source gap closure

### Objective

Close verified-source gaps before any applicability engine (Stage 3B).

### Gap corrections (selected)

| Topic | PREVIOUS STATUS | NEW STATUS | SOURCE THAT RESOLVED IT | DATE VERIFIED |
|-------|-----------------|------------|-------------------------|---------------|
| Taiwan general listed/OTC applicability phases | VERIFIED via SFB news only | VERIFIED_AUTHORITATIVE via FSC Order | 金管證審字第11403851756號 | 2026-08-12 |
| Annual-report IFRS requirements | VERIFIED via press | VERIFIED_AUTHORITATIVE | FL007032 | 2026-08-12 |
| Scope 1/2 assurance | VERIFIED via press | VERIFIED_AUTHORITATIVE | 11403851756 point 4 | 2026-08-12 |
| Scope 3 timing | VERIFIED “first three years” via press | VERIFIED_AUTHORITATIVE “from 4th FY” | 11403851756 point 6 | 2026-08-12 |
| Taiwan-recognised IFRS version | Implied | VERIFIED_AUTHORITATIVE | 11403851755 | 2026-08-12 |
| Non-listed banks / FHC applicability | “Under discussion” | VERIFIED_AUTHORITATIVE | 金管銀法字第11402739247號 | 2026-08-12 |

### Explicit non-actions

- No Applicability engine
- No carbon calculation pipeline changes

---

## Session 2026-08-12 — Stage 3A initial registry build

Initial source/rule registry architecture created. Several Taiwan items later upgraded in 3A.1/3A.2 after formal law/order retrieval.
