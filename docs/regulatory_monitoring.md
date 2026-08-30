# Regulatory monitoring (Stage 3A.6)

Official regulatory research is a **continuous process**. The monitor runs on a schedule, persists durable monitoring STATE, and never auto-activates legal rules.

## CONTENT vs STATE

| Kind | Examples | Automatic monitor may rewrite? |
|------|----------|--------------------------------|
| **REGULATORY CONTENT** | `config/regulatory_rules.csv`, `data/reference/regulatory_sources.csv`, ACTIVE/FUTURE/SUPERSEDED legal rows | **No** (human review only) |
| **MONITORING STATE** | `source_freshness_state.csv`, `monitoring_summary.json`, change/conflict logs, `persistence_status.json` | **Yes** (operational) |

## Runtime state path (source of truth)

```text
runtime monitor
→ data/regulatory/durable_state/
→ git branch regulatory-monitor-state
```

Do **not** persist a stale bundled `data/regulatory/` template. After push, the workflow verifies persisted summary == runtime summary (`STATE_PERSISTENCE_MISMATCH` on diff).

Workflow order: live monitor (continue-on-error) → persist STATE → verify → artifacts → final health gate → unit tests. Persistence must not be skipped when a critical source fails.

## TLS compatibility (Python 3.13)

1. Attempt normal strict `ssl.create_default_context()`
2. If and only if the error is an X509-strict compatibility issue (e.g. Missing Subject Key Identifier)
3. And the hostname is in `tls_x509_strict_fallback_hosts` (Taiwan official domains only)
4. Retry with CA trust + hostname verification still required, clearing only `VERIFY_X509_STRICT`

Never use `verify=False`, unverified contexts, or `curl -k`.  
`www.ifrs.org` remains on full strict TLS.

## Primary authoritative vs alternate monitoring (SFB IFRS)

- `PRIMARY_AUTHORITATIVE_SOURCE` (e.g. `src_tw_sfb_ifrs_download_area`) remains the legal recognition locus.
- HTTP 401/403/407 on a primary source → `MANUAL_ACCESS_REQUIRED` (not endless `SOURCE_UNAVAILABLE`, not `CURRENT`).
- Optional `ALTERNATE_OFFICIAL_MONITORING_SOURCE` may emit `ALTERNATE_OFFICIAL_SIGNAL` / `PENDING_REVIEW` early-warning only.
- Alternate signals **never** auto-activate Taiwan-recognised IFRS versions.
- Applicability gates treat `MANUAL_ACCESS_REQUIRED` as `MANUAL_VERIFICATION_REQUIRED` (no unconditional conclusions).

## Baseline vs amendment

First successful fetch with no prior content hash → `BASELINE_CAPTURED` (`review_required=false`). Subsequent meaningful hash diffs → potential `PENDING_REVIEW`.

## Failed latest check

A failed latest fetch never reports `freshness_status=CURRENT`. Preserve `last_successful_fetch_at` from the prior success.

## Critical sources

`critical_source_ids` in `config/regulatory_monitoring.yaml` are Taiwan applicability / recognition sources.  
Hard `FETCH_FAILED` on CRITICAL sources → `critical_sources_failed > 0` → health `CRITICAL_SOURCE_FAILURE`.
Managed `MANUAL_ACCESS_REQUIRED` does **not** increment `critical_sources_failed`.

## Health precedence

1. `STATE_PERSISTENCE_FAILED`
2. `STATE_PERSISTENCE_MISMATCH`
3. `CRITICAL_SOURCE_FAILURE`
4. `MONITORING_PARTIAL` (incl. manual verification / supplementary)
5. `MONITORING_CURRENT`

## Automatic schedule

GitHub Actions workflow:

```text
.github/workflows/regulatory-monitor.yml
```

| Trigger | Cadence |
|---------|---------|
| `schedule` | **Daily** — `cron: "17 16 * * *"` (~16:17 UTC, non-zero minute) |
| `workflow_dispatch` | Manual run anytime |

GitHub scheduled execution is **periodic, not guaranteed** at an exact legal clock minute.

**Default-branch requirement:** scheduled workflows run only if this workflow file exists on the repository **default branch**.

## Health gate

| Status | Meaning |
|--------|---------|
| `MONITORING_CURRENT` | Critical sources OK; overall CURRENT |
| `MONITORING_PARTIAL` | Non-critical gaps; not false NO_CHANGE |
| `CRITICAL_SOURCE_FAILURE` | One or more CRITICAL sources unavailable — workflow fails |
| `STATE_PERSISTENCE_FAILED` | Could not store durable state — workflow fails |
| `STATE_PERSISTENCE_MISMATCH` | Branch summary ≠ runtime — workflow fails |

`NO_CHANGE` requires a successful fetch + compare. `SOURCE_UNAVAILABLE` is never NO_CHANGE.

## Manual trigger

```bash
python -m carbon_ledger.regulatory_monitor --check-all
python -m carbon_ledger.regulatory_monitor --status
python -m carbon_ledger.regulatory_monitor --health-gate
```

## Freshness gate API

```python
from carbon_ledger.regulatory_monitor import get_regulatory_freshness

freshness = get_regulatory_freshness(repo_root)
# freshness["state_source"]
# freshness["summary"]["critical_sources_failed"]
# freshness["summary"]["monitoring_health"]
```

Preference: durable env/dir → bundled fallback → unavailable.

## Permissions

| Permission | Why |
|------------|-----|
| `contents: write` | Push `regulatory-monitor-state` and review branches |
| `pull-requests: write` | Create regulatory review PRs |
| `issues: write` | Create fallback review Issues |

No automatic PR approval or merging.
