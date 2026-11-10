# Regulatory change report

Generated at: 2026-11-10T21:47:40Z
Overall freshness: CURRENT
Review required: True

## Reviewable changes

### chg_src_tw_twse_portal_20261110T214734Z
- source_id: `src_tw_twse_portal`
- change_type: `POTENTIAL_REGULATORY_CHANGE`
- previous_hash: `dca8a2bdc9b4cfd9c049dc3f48692cff0bff1b010d6a48383b2ec1821d1f289f`
- new_hash: `5d0d93679b0ec6cd274945f7cab5828a095b5280fe96e2146196cf8de516853b`
- previous_version: `portal_or_doc`
- new_version: `portal_or_doc`
- affected_rule_ids: ``
- activation_status: `NOT_ACTIVATED`
- notes: Detected change recorded; legal rules are NOT auto-activated.

## Reviewer workflow

1. Verify the official source text manually.
2. Confirm whether a legal rule change is required.
3. Add/update rule rows with new `source_version` / `rule_effective_from`.
4. Set the new rule `rule_status=ACTIVE` (or FUTURE).
5. Set the previous rule `rule_status=SUPERSEDED` and link `superseded_by_rule_id`.
6. Never auto-merge monitoring PRs into production compliance logic.
