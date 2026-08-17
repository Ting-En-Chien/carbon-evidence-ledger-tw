# Stage 4.2A — local official company snapshot

V1 company lookup does **not** call a live government API.

```
Official Taiwan open data
  → snapshot build (manual)
  → normalized local company master
  → UBN lookup in process memory
  → customer confirmation
  → manual fallback if not in the snapshot
```

This is a dated official public-data version, not live government data.

## Sources

Verified official machine-readable downloads. No application, API key,
IP whitelist, or HTML scraping.

| Population | Authority | Dataset | Access |
|---|---|---|---|
| 上市 | 臺灣證券交易所 | 上市公司基本資料 `t187ap03_L` | https://openapi.twse.com.tw/v1/opendata/t187ap03_L |
| 上櫃 | 證券櫃檯買賣中心 | 上櫃公司基本資料 `mopsfin_t187ap03_O` | https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O |
| 公開發行 | 臺灣證券交易所 | 公開發行公司基本資料 `t187ap03_P` | https://openapi.twse.com.tw/v1/opendata/t187ap03_P |

Corresponding government open-data pages (OGDL):

- https://data.gov.tw/dataset/18419
- https://data.gov.tw/dataset/25036
- https://data.gov.tw/dataset/28567

Fields kept: unified business number, company name, registered address,
paid-in capital (TWD integer), listing / public-company status, official
source, source data date.

Fields not kept: chairman, general manager, spokesman, and other personal
or unused registration fields.

## Coverage

The snapshot is **not** every Taiwan company.

Coverage metadata is generated from the sources actually included in the
build. For the current V1 profile, TWSE listed, TPEx OTC, and TWSE public
are all required. If a required source fails or returns zero usable rows,
the build fails and the last known-good snapshot is left unchanged.

Do not say 「全台百億公司全部涵蓋」. If a source row has paid-in capital
≥ NT$10,000,000,000, the build must keep it. That is a filter check, not
a completeness claim.

Exact counts live in `data/reference/company_master/company_master_metadata.json`
(`quality` plus `source_data_date`).

## Runtime lookup

Provider order:

1. Previously customer-confirmed or customer-entered `CompanyMaster` for the same UBN. Official snapshot may refresh provenance; it must not overwrite customer-confirmed corrections.
2. Local official snapshot (`LocalOfficialCompanyRepository`)
3. Customer manual input (`data_origin = CUSTOMER_ENTERED`)

`00000000` is a reserved source placeholder, not a usable company identifier. The snapshot build excludes it. Runtime validation rejects it. Legitimate leading-zero UBNs remain valid.

Lookup is an exact 8-digit UBN match against an in-memory index loaded once
from `data/reference/company_master/company_master.csv`.

No GCIS network request. No API key. No fixed public IP.

## Customer copy

- 「輸入統一編號，我們會從目前的官方公司資料中尋找。」
- 「資料來源：政府公開資料」
- 「資料更新至：YYYY-MM-DD」

Not found is normal:

- 「目前的官方公司資料庫沒有找到這個統編。」
- 「目前資料庫以公開發行／上市櫃等官方公開公司資料為主。」
- then 「手動填寫公司資料」

Do not say 即時官方資料, 官方即時資料, GCIS API, 查詢失敗, or API error.

## Manual refresh

```bash
python scripts/build_company_snapshot.py
```

That command downloads the approved OpenAPI JSON and rewrites the snapshot
only after every required source succeeds. V1 does not schedule daily crawls.

## Future optional live GCIS integration

`fetch_official_company` / `parse_gcis_company` remain in the repository as
**OPTIONAL FUTURE PRODUCTION INTEGRATION**.

They are not the default provider. CUSTOMER mode does not call them.
Enabling them later would require `CEL_ENABLE_GCIS_LIVE=1` and whatever
registration the GCIS production API then requires (possibly IP whitelist).
That is not a V1 setup requirement.

## Calculation lock

The GHG analysis pipeline does not import company lookup or snapshot code.
`開始分析` stays offline on local state.
