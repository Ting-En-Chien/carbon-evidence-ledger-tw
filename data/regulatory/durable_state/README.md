# Durable regulatory monitoring STATE (Stage 3A.5)

This directory is the **runtime source of truth** for monitoring STATE.

## Flow

```text
runtime monitor
→ data/regulatory/durable_state/
→ git branch regulatory-monitor-state
```

Bundled `data/regulatory/*` is a mirrored fallback only.  
GitHub Actions must copy **from this directory**, never from a stale bundled template.

## Source of truth

| Environment | Source of truth |
|-------------|-----------------|
| Production / scheduled monitor | Git branch `regulatory-monitor-state` (populated from this dir) |
| Local / CI runtime | This directory after `--check-all` |
| Fallback | Repository-bundled `data/regulatory/*` (may lag) |

This directory is **MONITORING STATE**, not legal CONTENT.  
Automatic monitoring must never activate or rewrite `config/regulatory_rules.csv` here.

GitHub Actions artifacts are supplementary evidence only.
