# Regulatory monitoring (Stage 3A.4)

Official regulatory research is a **continuous process**. The monitor runs on a schedule, persists durable monitoring STATE, and never auto-activates legal rules.

## CONTENT vs STATE

| Kind | Examples | Automatic monitor may rewrite? |
|------|----------|--------------------------------|
| **REGULATORY CONTENT** | `config/regulatory_rules.csv`, `data/reference/regulatory_sources.csv`, ACTIVE/FUTURE/SUPERSEDED legal rows | **No** (human review only) |
| **MONITORING STATE** | `source_freshness_state.csv`, `monitoring_summary.json`, change/conflict logs, `persistence_status.json` | **Yes** (operational) |

## Automatic schedule

GitHub Actions workflow:

```text
.github/workflows/regulatory-monitor.yml
```

| Trigger | Cadence |
|---------|---------|
| `schedule` | **Daily** — `cron: "17 16 * * *"` (~16:17 UTC, non-zero minute) |
| `workflow_dispatch` | Manual run anytime |

GitHub scheduled execution is **periodic, not guaranteed** at an exact legal clock minute. Delays are possible under Actions congestion.

**Default-branch requirement:** scheduled workflows run only if this workflow file exists on the repository **default branch**. Keep `.github/workflows/regulatory-monitor.yml` on the default branch.

Do not schedule more frequently than daily unless policy changes in `config/regulatory_monitoring.yaml`.

## Manual trigger

```bash
python -m carbon_ledger.regulatory_monitor --check-all
python -m carbon_ledger.regulatory_monitor --authority FSC
python -m carbon_ledger.regulatory_monitor --source src_tw_sfb_ifrs_download_area
python -m carbon_ledger.regulatory_monitor --status
```

Or run the workflow manually from the GitHub Actions UI (`workflow_dispatch`).

## Durable freshness persistence (source of truth)

GitHub Actions logs/artifacts alone are **not** authoritative for application freshness.

| Layer | Role |
|-------|------|
| Branch `regulatory-monitor-state` | MVP durable store updated on **every** successful scheduled run, including `NO_CHANGE` |
| `CARBON_LEDGER_REGULATORY_STATE_DIR` | Production mount/checkout of latest durable state for readers |
| `data/regulatory/durable_state/` | Local export written by `persist_monitoring_state()` |
| `data/regulatory/*` (bundled) | Fallback shipped with a deployment (may be stale) |
| Actions artifacts | Supplementary debugging / forensic evidence only |

On every successful official-source check (including `NO_CHANGE`):

1. Update `last_checked_at`, `last_successful_fetch_at`, `fetch_status`, `freshness_status`, `next_check_at`
2. Persist monitoring STATE to the durable store / state branch
3. Do **not** open a regulatory review PR for `NO_CHANGE`

If sources were fetched successfully but STATE cannot be persisted → `STATE_PERSISTENCE_FAILED`. The run is **not** fully successful. This is distinct from `FETCH_FAILED`.

## Freshness gate API

```python
from carbon_ledger.regulatory_monitor import get_regulatory_freshness

freshness = get_regulatory_freshness(repo_root)
# freshness["state_source"]  # durable_persisted_state | bundled_fallback | unavailable
# freshness["analysis_allowed"]
# freshness["state"]
# freshness["overall_regulatory_freshness"]
# freshness["last_global_check_at"] / last_successful_check_at
# freshness["sources_current" / "sources_stale" / "sources_failed"]
# freshness["changes_pending_review"] / regulatory_conflicts
# freshness["consecutive_fetch_failures"] / consecutive_persistence_failures
```

Preference order for `get_regulatory_freshness()`:

1. **Durable** — `CARBON_LEDGER_REGULATORY_STATE_DIR` or `data/regulatory/durable_state`
2. **Bundled fallback** — `data/regulatory` (explicitly labeled; may lag)
3. **Unavailable** — `FRESHNESS_STATE_UNAVAILABLE` / `UPDATE_REQUIRED` (never pretend CURRENT)

Future Stage 3B applicability logic must call this **before** issuing regulatory conclusions.

## Monitored authorities / domains

Taiwan (authoritative / official):

- `law.fsc.gov.tw`
- `www.fsc.gov.tw`
- `www.sfb.gov.tw`
- `ifrs.sfb.gov.tw` (**high-priority** Taiwan-recognised IFRS version locus)
- `isds.tpex.org.tw`
- `www.twse.com.tw`
- `www.tpex.org.tw`
- `ghgregistry.moenv.gov.tw`
- `oaout.moenv.gov.tw`

International (public pages only):

- `www.ifrs.org` (S1/S2, amendments, ISSB implementation, SASB)

International IFRS.org changes **never** automatically become Taiwan-active.

## Freshness windows

Configured in `config/regulatory_monitoring.yaml`:

| Profile | Window | Typical use |
|---------|--------|-------------|
| `high_change_source` | 1 day | FSC law portal, Taiwan recognised IFRS download area, key orders/regs |
| `normal_regulatory_source` | 7 days | Other official regulatory pages |
| `stable_standard_reference` | 30 days | IFRS Foundation public pages |

**CURRENT** requires `last_successful_fetch_at` within the configured window.  
A workflow run alone does **not** make a source CURRENT.

## Network / persistence failure behavior

| Failure | Meaning |
|---------|---------|
| `FETCH_FAILED` | Official source could not be fetched; `last_successful_fetch_at` unchanged |
| `STATE_PERSISTENCE_FAILED` | Fetch may have succeeded, but durable STATE was not stored |
| `FRESHNESS_STATE_UNAVAILABLE` | Reader cannot obtain durable or bundled freshness STATE |

Repeated failures escalate via `consecutive_fetch_failures` / `consecutive_persistence_failures` toward `STALE`, `UPDATE_REQUIRED`, `SOURCE_CHECK_FAILED`, or `FRESHNESS_STATE_UNAVAILABLE` per policy.

## Meaningful-change criteria

| Classification | Opens PR/Issue? | Persists freshness STATE? |
|----------------|-----------------|---------------------------|
| `NO_CHANGE` | No | **Yes** |
| `COSMETIC_CHANGE` | No | Yes |
| `METADATA_CHANGE` (etag/last-modified only) | No | Yes |
| `METADATA_CHANGE` with version identifier change | Yes | Yes |
| `POTENTIAL_REGULATORY_CHANGE` | Yes | Yes |
| `CONFIRMED_REGULATORY_CHANGE` | Yes | Yes |
| `REGULATORY_CONFLICT` | Yes | Yes |
| `SOURCE_UNAVAILABLE` | No PR spam | Yes (failure recorded) |

## What happens when a source changes (reviewable)

```text
scheduled official-source check
→ detect source change
→ persist monitoring STATE (including state branch)
→ mark potentially affected rules PENDING_REVIEW
→ open review PR on branch regulatory-update/<run-id>
  (fallback: GitHub Issue + uploaded artifacts)
→ human verification
→ only then allow new rule version ACTIVE / FUTURE
→ previous rule SUPERSEDED when appropriate
```

**Never auto-merge. Never auto-approve. Never auto-activate legal rules.**

## GitHub Actions permissions (least privilege)

Explicit workflow permissions:

| Permission | Why |
|------------|-----|
| `contents: write` | Push `regulatory-monitor-state` and review branches; read repository content via checkout |
| `pull-requests: write` | Create regulatory review PRs |
| `issues: write` | Create fallback review Issues |

No automatic PR approval, no automatic merging, no broader token scopes.

## Persistence files

| File | Role |
|------|------|
| `data/regulatory/source_freshness_state.csv` | Last check / success / hash / freshness |
| `data/regulatory/regulatory_change_log.csv` | Permanent change audit trail |
| `data/regulatory/regulatory_conflict_log.csv` | Unresolved conflicts |
| `data/regulatory/monitoring_summary.json` | Stage 3B / UI-ready summary |
| `data/regulatory/persistence_status.json` | Durable persist OK / STATE_PERSISTENCE_FAILED |
| `data/regulatory/regulatory_change_report.md` | Human review report (when reviewable) |
| `data/regulatory/durable_state/` | Local durable export |
| `config/regulatory_monitoring.yaml` | Cadence, windows, high-priority sources |

## Taiwan recognised IFRS version monitoring

High-priority sources include `src_tw_sfb_ifrs_download_area` and related recognised-version orders.  
Never infer Taiwan recognition from IFRS.org alone.

## How a reviewer approves a regulatory change

1. Open the monitoring PR (or Issue) and `regulatory_change_report.md`
2. Manually verify the official law/order/page
3. Confirm legal impact
4. Add a **new** rule version row (`ACTIVE` or `FUTURE`)
5. Set the previous rule to `SUPERSEDED`
6. Merge only after human confirmation

## How to recover if monitoring failed for several days

1. Run `--check-all` or `workflow_dispatch`
2. Confirm durable STATE updated on `regulatory-monitor-state` (not only artifacts)
3. Inspect `source_freshness_state.csv` and `monitoring_summary.json`
4. Do **not** issue unconditional applicability conclusions until `get_regulatory_freshness()` allows analysis
