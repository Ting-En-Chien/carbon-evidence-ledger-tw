# Customer product UX rules

Durable presentation rules for Carbon Evidence Ledger.
These constrain **what customers see by default**, not calculation methodology.

Future UI work must follow this document.

## Customer first, system second

The customer is a company, not an engineer operating our pipeline.
Default UI answers business questions. System state is secondary.

## Three information layers

1. **Customer essential (default)** — result, important status, next action, issues that need work.
2. **Business / professional detail (on request)** — source mix, monthly trend, calculation notes, regulatory basis, coverage explanation.
3. **Audit / technical (hidden or Admin)** — IDs, hashes, formula versions, traces, registry health, pipeline states.

Never mix layers on the first screen.

## Progressive disclosure

Do not display everything the system knows.
Ask of every default element:

1. Does the customer need this now?
2. Does it change a decision?
3. Does it require an action?
4. Can it be understood without carbon-accounting expertise?
5. Could it live behind “了解更多”?
6. Is it duplicated elsewhere?

If no: keep the data, hide it from the default view.

## Result-first after analysis

After analysis, the first viewport must answer:

1. How much is currently calculated?
2. Where do emissions mainly come from?
3. Was this dataset fully calculated?
4. Is anything waiting on the customer?
5. What is the next step?

Pre-analysis may stay action-first (onboarding).

## Smart conditional UI

The UI must change with state:

- `unresolved = 0` → no issue KPI, no issue chart, no “查看待處理問題”
- unsupported Scope 3 → “尚未計算”, never `0`
- 100% calculated → no completeness donut/chart
- partial calculation → compact coverage + action, not a philosophy lecture
- applicability incomplete → one prominent CTA
- applicability complete → short status, not a repeated matrix
- healthy regulatory verification → compact chip, not a large card

No static dashboard that always renders every possible component.

## No empty actions

Do not offer a button whose destination has nothing to do.

## No charts for trivial 100% state

Do not draw a 100% donut because a chart component exists.
A success line is enough.

## No raw internal IDs in customer default

Hide `factor_id`, `source_id`, `rule_id`, `record_id`, hashes, and traces
unless the user opens professional/audit detail (or Admin).

## One primary action per section

Each section has at most one obvious next step.
Do not repeat the same CTA in attention, requirements, and footer.

## One primary home per fact

File name, coverage counts, regulatory freshness, reporting year, and
workflow progress each have one primary home.
Do not restack them on the executive dashboard.

## Beginner language by default

Copy must be understandable to a CFO, operations manager, or sustainability beginner.
Avoid default phrases such as completeness, adapter, registry, source activation,
calculation trace, and normalized records.

Technical terms belong behind “了解更多” or on professional pages.

## File metadata is not an executive result

Uploaded file names belong in Evidence & Data (or a data-detail expander).
Home may show reporting period, not `01_完整_單一廠區_120筆.xlsx`.

## Technical detail on demand

Methodology disclaimers such as “missing activities are not treated as zero”
are true — show them inside coverage help, not as first-viewport footnotes.

## Customer presentation architecture

Backend state never renders directly to the customer.
Flow: backend state → product presentation model → customer action / summary
→ optional professional detail → optional audit detail.

Pages must not interpret raw status enums separately.

## System limitation is not a customer to-do

If a result is unresolved because the product, registry, or administrator
review is incomplete, tell the customer they do not need to act.
Do not say “請管理員確認” unless the company’s own people must confirm a fact.

## Merge repeated missing facts

One missing company fact is one customer task, even if several obligations
depend on it. Update all dependent results after the fact is provided.

## No empty value rows or empty actions

Do not render `—` placeholders, “仍需處理 0”, or a CTA with nothing to do.
If there is no verified legal basis, hide “查看法規依據”.
If the customer has no action, render no button.

## No generic obligation template

IFRS, GHG inventory, MOENV verification, and carbon fee each have their own
presentation. Do not reuse IFRS timing fields on unrelated domains.

## Just-in-time micro-learning

Do not put a permanent teaching column on every wizard page.
Help appears next to the field that needs it, in beginner language first
and professional terminology second.

## One primary purpose per screen

Do not simultaneously collect data, teach law, show evidence, and explain
backend internals on the same step.

## One primary CTA per section

Each section has at most one obvious next step.
Result pages lead with the merged customer action, then concise cards.

## No customer admin or defensive engineering copy

Customer UI must not mention 管理員 / admin, “系統不會…”, registry gaps,
or “已驗證規則不足”. Those belong in professional or Admin detail.

## Auto-fill before asking

Do not make the customer type a fact that can be obtained safely from:

1. an authorized Taiwan government API or open-data source
2. previously confirmed company / facility master data
3. the customer's uploaded activity file

Ask only what is still missing for a decision.

## Company lookup uses a local official snapshot first

Company lookup must not require production API registration for the V1
portfolio project. Use local official open-data snapshot first.

Do not tell customers this is live government data. Show the snapshot
date. A missing UBN is normal coverage, not a system failure.

## Confirm, do not retype

Taiwan company setup starts with the unified business number (統一編號).
Official company data is shown for confirmation.
Customers confirm differences; they do not re-enter names, addresses, or capital
that the official source already provided.

## Official data is evidence, not the reporting boundary

A registered address is not a factory.
A registered factory is not automatically inside this year's GHG inventory,
IFRS reporting entity, or carbon-fee scope.
Business items are not actual emission activities.
Paid-in capital is not net worth.

The customer confirms reporting relevance.

## Discover sites from government data and uploads

Facility suggestions come from official factory open data and from the
customer-facing 廠場／營運據點 column after file mapping.
Reconcile both with last year's confirmed master.
A mismatch is not automatically an error.

## Ask differences only

If sources agree, one confirmation is enough.
If they differ, show only the rows that need review.
Support bulk actions such as 全部正確 and 全部納入本次資料.

## Reuse last year's facility master

Next year starts from last year's confirmed sites.
Do not make the customer retype names and addresses.

## One fact, many obligations

A confirmed Taiwan site or notice is entered once.
IFRS, GHG inventory, verification, and carbon-fee results all consume it.
Missing-data actions jump to the setup step that collects that fact.

## No network calls during carbon calculation

Company and factory lookup belong in setup.
「開始分析」 stays deterministic and offline on verified local state.

## Supported surfaces (Stage 4.2G)

Company setup, Excel/CSV ingestion, mapping confirmation, analysis, evidence,
and reporting are a **desktop** workflow.

The six-step guided orientation is approved on desktop only. It covers
confirming the company, reporting period, and inventory boundary; reviewing
applicable requirements and key dates; uploading an existing company file;
confirming items that need judgment; reviewing calculation coverage; and
reviewing traceable results and reports. Mobile guided-tour layout is a
deferred known limitation, not a Stage 4.2G pass. Do not present
`qa_42g_tour_mobile.png` as approval evidence. Do not claim that the current
full workflow supports phones.

Future mobile scope may cover read-only results, alerts, and executive
summaries — not the complete setup-to-report journey.
