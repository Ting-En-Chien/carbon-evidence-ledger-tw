# Stage 4.2 — authorized company and factory lookup

On-demand setup lookup only. This is not scheduled regulatory monitoring
and is never called from the GHG calculation pipeline.

No HTML scraping. A public webpage is not an approved access route.

## Company master — local official snapshot (V1 default)

| Item | Value |
|---|---|
| Sources | TWSE listed / public + TPEx OTC official OpenAPI JSON |
| Access | Government open data (OGDL). No application, API key, or IP whitelist |
| Build | `python scripts/build_company_snapshot.py` |
| Runtime | Local CSV snapshot indexed by 8-digit UBN |
| Customer copy | 資料來源：政府公開資料；資料更新至：YYYY-MM-DD |
| Not found | Normal. Offer 手動填寫公司資料. Do not show API / 查詢失敗 |
| Detail | [stage4_2_company_snapshot.md](./stage4_2_company_snapshot.md) |

V1 is runnable with no GCIS registration.

## Future optional integration — GCIS Open API

Not required for the current portfolio / CUSTOMER demo.

| Item | Value |
|---|---|
| Status | OPTIONAL FUTURE PRODUCTION INTEGRATION |
| Service | 公司登記基本資料-應用一 |
| Authority | 經濟部商業發展署 / 商工行政資料開放平臺 |
| source_id | `src_tw_gcis_company_open_api` |
| Access mode | Official Open API (`OFFICIAL_API`) |
| Permission / licence | 政府資料開放授權條款第 1 版 (OGDL) |
| Policy URL | https://data.gcis.nat.gov.tw/od/rule |
| Endpoint | `https://data.gcis.nat.gov.tw/od/data/api/5F64D864-61CB-4D0D-8AD9-492047CC1EA6` |
| Enable | Only if `CEL_ENABLE_GCIS_LIVE=1` is set later |
| Production note | Live GCIS calls may require MOEA IP registration / a fixed outbound IP. That is **not** a V1 prerequisite. |
| Fields consumed | company name, status, registered address, paid-in capital, optional business items |
| Fields not used | responsible person and other unused personal / unused registration fields |

Do not scrape ordinary GCIS HTML company pages.

## Factory directory — local official snapshot (V1 default)

```
Official 登記工廠 open data
  → snapshot build (manual)
  → normalized local factory master
  → filter by company UBN
  → facility candidates
  → reconcile with upload sites + previously confirmed sites
```

| Item | Value |
|---|---|
| Service | 登記工廠名錄（生產中工廠清冊） |
| Authority | 經濟部產業發展署 |
| source_id | `src_tw_factory_open_data` |
| Access mode | Official open data (`OFFICIAL_OPEN_DATA`) |
| Permission / licence | 政府資料開放授權條款第 1 版 (OGDL) |
| Dataset | https://data.gov.tw/dataset/6569 |
| Catalog | https://www.ida.gov.tw/opendata/02/SDD6569.csv |
| Build | `python scripts/build_factory_snapshot.py` |
| Runtime | Local CSV snapshot indexed by 8-digit UBN. No live HTTP. |
| Fields kept | factory name, address, registration number, industry, main products, unified business number |
| Fields not kept | 工廠負責人姓名 and other personal-name columns |
| Live HTTP | Optional future/development only if `CEL_FACTORY_OPEN_DATA_URL` is set. Not required for V1. |
| Tests / E2E | Fixture snapshot or `CEL_ZERO_ENTRY_STUB=1`; no live government dependency |
| Scheduled monitor | No |
| Not used | `factory.moea.gov.tw` HTML search, Fidbweb HTML |

A registered factory is a discovery candidate. It is not automatically inside
the current reporting boundary.

## Listing status — TWSE / TPEx open data in the company snapshot

| Item | Value |
|---|---|
| TWSE | `src_tw_twse_portal` / https://openapi.twse.com.tw |
| TPEx | `src_tw_tpex_portal` / https://www.tpex.org.tw/openapi/ |
| Use | Snapshot `listing_status` (上市 / 上櫃 / 公開發行). Not a live per-lookup HTTP call. |

## Upload discovery

After Evidence & Data mapping, unique non-empty values in 廠場／營運據點
(`site_id`) become facility candidates. No third-party or LLM service is used.

## Calculation lock

`開始分析` does not call these adapters. Calculation stays offline on local state.
