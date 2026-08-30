# Commercial Information Hygiene

Stage 3B.3b product rule for customer-facing information architecture.

Customer UI answers: **What is happening? What applies? What is missing? What next?**

Progressive disclosure:

1. **Customer default** — business meaning
2. **Professional detail** — methodology / official sources
3. **Audit / Admin** — raw IDs, hashes, registry maintenance

| Information | Customer default | Professional detail | Audit / Admin | Decision |
|---|---|---|---|---|
| Regulatory freshness | 法規資料：已驗證 / 法規更新確認中 | Last verification date | Monitoring health, crawler counts, source enums | Friendly labels only in customer |
| Run ID | Hidden | — | Advanced audit / Admin | Not a KPI |
| rule_id | Hidden | — | Audit trace | Expand only |
| source_id / source_document_id | Document file name | Source issuer / type | Raw IDs | Human labels first |
| factor_id | Hidden | Factor description, year, authority | Raw factor_id | Basis expander |
| record_id | Hidden | — | Audit trace | Never lead |
| Evidence hash (SHA-256) | Hidden | — | Evidence drill-down audit | Never primary column |
| schema_version | Hidden | — | Admin manifest | Admin only |
| Ingestion timestamp | — | Optional in advanced | Actual timestamp / unavailable | Never fabricate 2024 |
| Emission factor source | — | Official authority + year | factor_id + registry row | Professional detail |
| Official regulatory basis | Status chips + why | 「查看官方依據」 | Rule/eval IDs | Keep accessible |
| Calculation trace | Off dashboard | Activity「查看計算依據」 | Activity「稽核追溯資訊」 | Not on Overview |
| Crawler / source monitoring | Hidden | — | Admin reporting | AppMode.ADMIN |
| SASB classification | Not in initial setup | IFRS preparation | Stored on CompanyProfile | Defer from onboarding |
| Demo status | Explicit「示範資料」badge | — | synthetic_demo flag in export | Never label real uploads synthetic |

## Hard rules

- UNKNOWN ≠ 0 and UNKNOWN ≠ today
- Real uploads never show “Synthetic demonstration”
- Customer pages must not expose raw monitoring enums
- Review archives (`carbon-ledger-*-review*`) are not product source

## Quality gate

Customer-facing stages still require Ruff + pytest + Playwright E2E + screenshots + one manual journey (`docs/customer_browser_qa.md`).
