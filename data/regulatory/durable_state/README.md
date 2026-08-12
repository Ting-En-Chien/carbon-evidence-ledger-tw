# Durable regulatory monitoring STATE

This directory holds a local export of operational monitoring state
(`source_freshness_state.csv`, `monitoring_summary.json`, etc.).

## Source of truth

| Environment | Source of truth |
|-------------|-----------------|
| Production / scheduled monitor | Git branch `regulatory-monitor-state` (or `CARBON_LEDGER_REGULATORY_STATE_DIR`) |
| Fallback | Repository-bundled `data/regulatory/*` (may lag a deployment) |

This directory is **MONITORING STATE**, not legal CONTENT.  
Automatic monitoring must never activate or rewrite `config/regulatory_rules.csv` here.

GitHub Actions artifacts are supplementary evidence only.
