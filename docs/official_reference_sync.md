# Official reference sync (Phase 10A)

Phase 10A adds an **auditable official-reference synchronization layer**.

**Synchronization is not calculation.** Downloading an official file never
authorizes emissions math by itself.

## Why this exists

Company users should not type annual government electricity factors by hand.
At the same time, the ledger must never scrape a webpage number and silently
use it for carbon calculations.

## Critical principle — versioned references

Older factor versions are never overwritten merely because a newer year exists.

- 2024 electricity factor and 2025 electricity factor are separate rows
- Historical activity periods keep matching the factor that covers their dates
- Re-running a 2024 analysis later must not silently pick the newest factor

The current registry already encodes this for Taiwan electricity:

- value `0.474 kgCO2e/kWh`
- `valid_from = 2024-01-01`
- `valid_to = 2024-12-31`

A 2025 activity does **not** match that row. If no applicable factor exists,
calculation stays blocked.

## Architecture

| Concern | Location |
|---|---|
| Source allowlist / parser type | `config/official_reference_sources.csv` |
| Explicit fallback rules | `config/official_reference_rules.csv` |
| Sync engine (HTTP + parse + candidates) | `src/carbon_ledger/reference_sync.py` |
| Snapshot index | `data/reference/reference_snapshots.csv` |
| Candidate updates | `data/reference/reference_candidates.csv` |
| Activation audit | `data/reference/reference_activations.csv` (append-only; this is the activation audit ledger) |
| Artifact bytes | `data/reference_snapshots/` |
| Active calculation registry | `data/reference/emission_factors.csv` (and related) |

Calculation modules (`calculate.py`, `pipeline.py`, UI analysis path) do **not**
perform network I/O. After sync, offline analysis uses the local versioned
registry only.

## Allowlist behavior

Runtime fetch accepts only configured official domains such as:

- `moea.gov.tw` (upstream/canonical MOEA host `www.moea.gov.tw`)
- `ghgregistry.moenv.gov.tw`

Do **not** use the incorrect host `ghg.moenv.gov.tw`.

Rejected by design:

- blogs, news articles, Wikipedia
- consultancy summaries
- commercial factor databases
- arbitrary user-supplied URLs
- invented `/official-reference/...` endpoints
- company-uploaded Excel emission-factor columns as official truth
- unofficial third-party mirrors

Redirects are followed only while the target remains allowlisted.

## Enterprise-inventory electricity factor strategy

Both MOEA public hosts currently return HTTP 403 to automated clients. This is
treated as a **source-resilience** design issue, not a reason for browser
impersonation, cookies, proxies, or anti-bot bypass.

### Provenance model

| Concept | Value |
|---|---|
| Operational source authority | Taiwan Ministry of Environment / Climate Change Administration |
| Upstream factor authority | Taiwan Ministry of Economic Affairs / Energy Administration |
| Operational source URL | `https://ghgregistry.moenv.gov.tw/epa_ghg/News/NewsList.aspx?Type_ID=1` |
| Upstream canonical URL | `https://www.moea.gov.tw/mns/Populace/news/News.aspx?kind=1&menu_id=40&news_id=122891` |

Do **not** pretend MOENV originated the MOEA factor. Snapshots retain upstream
MOEA canonical URL and authority even though runtime sync does not require the
MOEA page to be reachable.

### Source roles and retrieval strategies

Each official source declares an explicit `retrieval_strategy` (do not infer
from parser names or URL shapes):

| Source | `retrieval_strategy` | Behavior |
|---|---|---|
| `src_tw_moea_electricity_factor` | `provenance_only` | Upstream/canonical provenance; no network fetch |
| `src_tw_moenv_electricity_factor_enterprise` | `parse_landing` | Fetch and parse the MOENV NewsList HTML itself |
| `src_tw_moenv_general_emission_factors` | `discover_attachment` | Landing → allowlisted attachment → snapshot/parse |
| `src_tw_moenv_fuel_heating_values` | `discover_attachment` | same |
| `src_tw_moenv_gwp_reference` | `discover_attachment` | same |

For enterprise electricity (`parse_landing`):

- the NewsList HTML page is the supported machine-readable evidence
- the deterministic parser locates the 2026-06-17 announcement and extracts
  categorized factors from that HTML
- PDF/ODS links on the page must **not** automatically replace `retrieved_url`
- one HTML fetch creates at most one snapshot for that byte content

Normal `references check` / `fetch` does **not** repeatedly call the known-403
MOEA page. Check status reports MOEA as `recorded / access restricted` and
MOENV as the available operational source.

### Category / intended use

The MOENV 2026-06-17 announcement parser preserves distinct categories:

- `public_sales_average` — public electricity-sales average
- `industrial_enterprise_inventory` — industrial / enterprise inventory
- `residential` — residential

Parsing is bounded: locate the announcement by date `2026/06/17` and the
stable title phrase `114年度電力排碳係數`, then extract labelled factors only
from that block. The parser does not depend solely on fixture CSS class names
and must tolerate the live ASP.NET NewsList markup (`news-list-date`,
`txtlimit`, etc.).

Year semantics are kept separate:

- `publication_date` = 2026-06-17
- `factor_year` = 2025 (from ROC 114年度), with annual validity 2025-01-01 …
  2025-12-31 derived from that ROC year, not from publication date

For company GHG inventory in this project, the industrial factor is the
relevant candidate when applicability requirements are met. The candidate
stores intended-use and applicability notes (business tariff categories). The
system must not silently treat every 2025 electricity activity as using the
industrial factor when tariff/use context is missing.

Values are extracted from the fetched official page and staged as candidates.
They are never hard-coded into the active registry from configuration.

## TLS verification and Python 3.13 compatibility

Official fetches always use a verified HTTPS context from
`ssl.create_default_context()`:

- CA certificate validation remains enabled (`CERT_REQUIRED`)
- hostname checking remains enabled
- `verify=False` and unverified HTTPS contexts are never used

Source configuration includes an explicit `tls_compatibility_mode`:

| Mode | Meaning |
|---|---|
| `default` | Keep Python/OpenSSL `VERIFY_X509_STRICT` (normal behavior) |
| `python313_relaxed_x509_strict` | Clear only `VERIFY_X509_STRICT` for known official chains that fail Python 3.13 strict RFC 5280 checks (e.g. Missing Subject Key Identifier) |

Compatibility mode is **source-specific**. MOEA electricity remains `default`.
Allowlisted MOENV GHG Registry sources (`ghgregistry.moenv.gov.tw`) use
`python313_relaxed_x509_strict`.

This is still verified TLS. Snapshot metadata records:

- `tls_verification=verified`
- `tls_compatibility_mode=<configured mode>`

Do **not** describe compatibility mode as insecure TLS. Other SSL failures
(expired certificate, hostname mismatch, unknown issuer, non-allowlisted
redirect) are **not** automatically retried with relaxed strictness.

## Official request identity

Official GET requests send a transparent application User-Agent, for example:

`CarbonEvidenceLedger/0.1 (+https://github.com/Ting-En-Chien/carbon-evidence-ledger-tw)`

plus conservative `Accept` / `Accept-Language` headers. They do **not**
impersonate Chrome, and they do not add cookies, authentication, referer
spoofing, or browser `Sec-*` client-hint headers.

If an allowlisted source still returns HTTP 403 after this transparent
identity, sync reports `SOURCE_ACCESS_RESTRICTED` and does not retry with
browser impersonation.

## Unicode / IRI official attachment URLs

Official landing pages may discover attachment hrefs whose path or query
contains Traditional Chinese characters (IRI form).

Runtime fetch flow:

1. resolve href against the official landing page
2. parse hostname and validate the official allowlist
3. convert the Unicode IRI to an ASCII URI (`normalize_request_url`)
4. perform the HTTPS GET

Path and query are percent-encoded separately so scheme separators and
already-valid percent escapes are not double-encoded. Snapshot provenance may
retain both:

- `discovered_url` — original official Unicode/resolved href
- `retrieved_url` — percent-encoded transport URI actually used

## Retrieval strategies

Official sources declare an explicit `retrieval_strategy` in
`config/official_reference_sources.csv`:

### `parse_landing`

Used by MOENV enterprise electricity.

1. fetch allowlisted landing HTML
2. parse the HTML with the configured deterministic parser
3. register one HTML snapshot (dedupe by SHA-256)
4. stage parsed candidates (or `needs_parser_review` if structure changed)

Do **not** auto-discover or substitute PDF/ODS attachments for this strategy.

### `discover_attachment`

Used by general emission factors, fuel heating values, and GWP.

1. fetch allowlisted landing page
2. discover attachment hrefs
3. keep only allowlisted absolute URLs
4. prefer ODS/CSV/XLSX/PDF according to source policy
5. validate the discovered artifact URL separately
6. download artifact → hash snapshot → parse

Unicode IRI attachment URLs are normalized to ASCII URIs after allowlist checks.

### `provenance_only`

Used by the MOEA upstream/canonical electricity source. No network fetch.

Direct stable CSV endpoints are not assumed for any strategy.

## Snapshot architecture

Every fetched artifact records:

- `source_id`, authority
- `canonical_url` / `upstream_canonical_url` (when configured)
- `upstream_factor_authority` (when configured)
- `discovered_url` (original official href when Unicode encoding was needed)
- `retrieved_url`, `retrieved_host`, `retrieved_at`
- publication date (if known)
- file name, media type, byte size
- SHA-256
- parser version
- local path
- `tls_verification` (always `verified` for successful official HTTPS fetches)
- `tls_compatibility_mode` (`default` or `python313_relaxed_x509_strict`)

`publication_date` is **not** treated as `valid_from` / `valid_to`.

MOENV enterprise electricity announcement parsing preserves category
distinctions such as public electricity-sales average
(`public_sales_average`), industrial / enterprise inventory
(`industrial_enterprise_inventory`), and residential (`residential`). Values
are extracted from the fetched page and staged as candidates only — never
hard-coded from config into the active registry. Categories are not treated as
interchangeable for company GHG inventory use.

Identical SHA-256 values reuse the existing snapshot. Different bytes create a
new snapshot and never overwrite an existing artifact file with different
content.

## Candidate lifecycle

`discovered → downloaded → parsed → validated → candidate/active/rejected/superseded`

or `needs_parser_review` when no deterministic parser exists yet.

A newly fetched number remains inactive until validation **and** an explicit
activation step.

## Parsers

Supported in Phase 10A:

- `tw_moenv_electricity_news_landing_v1` — MOENV GHG Registry news announcement
  parser for the 2026-06-17 enterprise electricity-factor update (operational)
- `tw_moea_electricity_landing_v1` — retained for upstream MOEA provenance tooling
- `tw_moenv_file_downloads_landing_v1` — GHG Registry FileDownloads discovery
  (prefer ODS)
- `tw_moenv_news_heating_values_landing_v1` — registry/news heating-value discovery
- `tw_electricity_factor_csv_v1` — structured electricity-factor CSV artifact
- `tw_fuel_heating_values_csv_v1` — structured heating-value CSV artifact
- `needs_parser_review` — PDF/ODS/unstructured artifacts: snapshot + version only

The MOENV electricity news parser locates only the expected announcement by
stable date/title evidence. If the structure cannot be found, it returns
`needs_parser_review` / source-format-changed and does not guess.

Parsers preserve category distinctions such as industry / residential /
utility average / public electricity-sales average when the official file
provides them. Values are never invented from this documentation alone.

## Validation and activation

Validation checks include finite positive values, supported units, explicit
applicability dates where required, source locator, snapshot ID, and parser
version.

Activation:

- requires selecting exactly one `--candidate-id` (never all validated rows)
- requires an explicit `--activated-at` timestamp (no hidden `datetime.now()`)
- requires `--confirm` after reviewing the printed pre-activation summary
- refuses `needs_parser_review` / failed / pending / rejected candidates
- activates only the selected category (e.g. industrial enterprise inventory
  does not activate public-sales-average or residential)
- appends a new registry row and preserves historical years (2024 + 2025 coexist)
- writes activation audit metadata including candidate ID, snapshot ID,
  category, value, units, SHA-256, and provenance

There is no one-step internet-to-production activation.

## Official fallback rules

There is **no** implicit “use previous year” behavior.

If an authority documents a temporary previous-year fallback, represent it in
`official_reference_rules.csv` with provenance. The audit trail must
distinguish:

- exact-year factor used
- previous-year factor used under an explicit rule

## Fuel heating values and GWP

Fuel heating values are versioned separately and do **not** automatically clear
`calculation_dependencies`. Missing verified conversions still block
calculation.

GWP references remain separate from fuel/emission factors. Newer assessments
do not silently replace an existing calculation basis.

## CLI

```bash
python -m carbon_ledger references check
python -m carbon_ledger references fetch --retrieved-at 2026-08-10T00:00:00Z
python -m carbon_ledger references validate
python -m carbon_ledger references propose-update
python -m carbon_ledger references status
python -m carbon_ledger references activate \
  --candidate-id cand_xxx \
  --activated-at 2026-08-11T14:30:00+08:00
# review summary, then:
python -m carbon_ledger references activate \
  --candidate-id cand_xxx \
  --activated-at 2026-08-11T14:30:00+08:00 \
  --confirm
```

Normal `run-demo` / Streamlit analysis does not crawl official websites.

## UI

Audit & Export shows a compact **官方參考資料** maintenance status:

- electricity years: available / candidate / unavailable
- fuel heating-value latest registered years
- last checked timestamp

## Offline behavior

If official sites are unavailable:

- sync reports `unavailable`
- already-validated local registry versions remain usable
- calculation does not crash merely because the network is down

## Official factor update v1

The system **automatically checks** allowlisted official sources on a weekly
GitHub Actions schedule (`official-factor-update.yml`) and via
`python -m carbon_ledger references propose-update`.

It does **not** auto-merge pull requests and does **not** silently swap
coefficients in the live registry. A bot branch/PR only proposes append-only
versioned rows plus an activation-audit trail. **Merging that PR is the human
approval that enables the new coefficients.**

### Reviewer checklist

- Official source id, URL, retrieved timestamp, MIME type, and snapshot SHA-256
- Old value vs new value, units, activity type, geography, and gas/context
- Applicable year / `valid_from`–`valid_to` (not the publication date)
- Percent change and which calculation types could be affected
- Validation result; items that cannot be activated and why
- GWP assessment basis (AR5 vs AR6) is explicit and not mixed
- Purchased-steel average-data factors are **not** present as invented numbers

### Publication date vs effective period

| Field | Meaning |
|---|---|
| `publication_date` | When the authority published the document |
| `valid_from` / `valid_to` | The activity dates the coefficient may cover |
| `factor_year` / `reporting_year` | Version label; not “today’s calendar year” |

A coefficient published in 2026 may still apply to 2025 if `valid_from` /
`valid_to` say so. A 2025 coefficient is never applied to 2024 merely because
it is newer.

### Recalculating an older year

Matching uses the **activity / reporting period**, then identity
(activity, context, gas, geography, unit), then:

1. `valid_from` empty or `valid_from <= activity date`
2. `valid_to` empty or `activity date <= valid_to`
3. If several rows still match, an explicit version rule (same GWP assessment
   with the latest covering `valid_from`) is used; otherwise matching fails closed
4. Completed 2024 results keep their `factor_id` / version in calculation and
   activation audit traces. A later publication does not rewrite them.

There is no “use last year because this year is missing” fallback unless
`official_reference_rules.csv` records an auditable rule.

### When an official source cannot be fetched

401, 403, CAPTCHA, login walls, robots restrictions, and similar blocks become
`manual_review_required`. The job must not activate data after a failed
download, and it must not delete previously stored snapshots or registry rows.
Reviewers get an artifact and/or a GitHub issue. Manual retrieval still has to
go through snapshot → parse → candidate → validate → PR merge.

### Steel and other secondary factors

Purchased-steel average-data factors have an extension point only. v1 has **no
approved steel coefficient**, so the updater must not invent a number and must
not make a 10 t steel activity start calculating.

## Limitations

- Live government HTML/PDF layouts are not blindly scraped into active factors
- PDF support is primarily evidence download + hash/version tracking unless a
  deterministic parser already exists
- Activation is intentional and separate from fetch/validate
- Company intake Excel factor columns never become official registry truth
