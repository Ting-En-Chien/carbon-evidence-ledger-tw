"""On-demand company / factory lookup (setup only).

V1 customer lookup uses local official open-data snapshots.
It never requires GCIS registration, API keys, a live GCIS call,
or CEL_FACTORY_OPEN_DATA_URL.

The GCIS live adapter below is OPTIONAL FUTURE PRODUCTION INTEGRATION.
It must not run in default CUSTOMER mode.

Never imported by the GHG calculation pipeline.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from carbon_ledger.company_master import (
    ORIGIN_CUSTOMER,
    ORIGIN_OFFICIAL,
    ORIGIN_SNAPSHOT,
    CompanyMaster,
    OfficialFactoryHint,
    SourceRecord,
    utc_now_iso,
    validate_ubn,
)
from carbon_ledger.company_snapshot import (
    default_snapshot_csv,
    load_company_repository,
)
from carbon_ledger.factory_snapshot import (
    default_factory_csv,
    load_factory_repository,
)
from carbon_ledger.source_access import (
    policy_for_source,
)

GCIS_SOURCE_ID = "src_tw_gcis_company_open_api"
FACTORY_SOURCE_ID = "src_tw_factory_open_data"
TWSE_SOURCE_ID = "src_tw_twse_portal"
TPEX_SOURCE_ID = "src_tw_tpex_portal"

GCIS_COMPANY_API_ID = "5F64D864-61CB-4D0D-8AD9-492047CC1EA6"
GCIS_COMPANY_API = (
    f"https://data.gcis.nat.gov.tw/od/data/api/{GCIS_COMPANY_API_ID}"
)
TWSE_LISTING_API = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TPEX_LISTING_API = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_basic"

STUB_ENV = "CEL_ZERO_ENTRY_STUB"
GCIS_LIVE_ENV = "CEL_ENABLE_GCIS_LIVE"
# Aligned happy-path company used by mocked tests / E2E.
STUB_ALIGNED_UBN = "12345675"
# Official factories differ from a typical upload set.
STUB_DIFF_UBN = "13579243"
# Official company exists; capital and listing are unknown.
STUB_SPARSE_UBN = "24681358"
# Deterministic 7-factory identity-confirmation journey.
STUB_SEVEN_UBN = "15700001"

NOT_FOUND_MESSAGE = "目前的官方公司資料庫沒有找到這個統編。"
STUB_COMPANY_UBNS = frozenset(
    {STUB_ALIGNED_UBN, STUB_DIFF_UBN, STUB_SPARSE_UBN, STUB_SEVEN_UBN}
)

_CALL_COUNTS: dict[str, int] = {}


@dataclass
class LookupResult:
    company: CompanyMaster
    factories: list[OfficialFactoryHint] = field(default_factory=list)
    listing_status: str = "UNKNOWN"
    origin: str = ORIGIN_OFFICIAL
    ok: bool = False
    customer_message: str = ""
    http_attempted: bool = False


def reset_lookup_cache() -> None:
    """Reset lookup counters. Official repositories have their own caches."""
    _CALL_COUNTS.clear()


def lookup_call_count(kind: str = "company") -> int:
    return int(_CALL_COUNTS.get(kind, 0))


def _count(kind: str) -> None:
    _CALL_COUNTS[kind] = _CALL_COUNTS.get(kind, 0) + 1


def _copy_company(company: CompanyMaster) -> CompanyMaster:
    """Return a new CompanyMaster so callers cannot leak session mutations."""
    return CompanyMaster.from_dict(company.to_dict())


def _lookup_result(
    *,
    company: CompanyMaster,
    factories: list[OfficialFactoryHint],
    origin: str = ORIGIN_OFFICIAL,
    ok: bool = False,
    customer_message: str = "",
    http_attempted: bool = False,
) -> LookupResult:
    return LookupResult(
        company=_copy_company(company),
        factories=list(factories),
        listing_status=company.listing_status,
        origin=origin,
        ok=ok,
        customer_message=customer_message,
        http_attempted=http_attempted,
    )


def _http_get_json(url: str, *, timeout: float = 12.0) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CarbonEvidenceLedger/company-setup",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        raw = response.read().decode("utf-8")
    if not raw.strip():
        return None
    return json.loads(raw)


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    lower = {str(k).casefold(): v for k, v in row.items()}
    for key in keys:
        value = lower.get(key.casefold())
        if value not in (None, ""):
            return value
    return None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).replace(",", "").replace(" ", "")
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def gcis_company_url(ubn: str) -> str:
    """OPTIONAL FUTURE PRODUCTION INTEGRATION — not used by default CUSTOMER lookup."""
    query = urllib.parse.urlencode(
        {
            "$format": "json",
            "$filter": f"Business_Accounting_NO eq {ubn}",
            "$skip": "0",
            "$top": "1",
        }
    )
    return f"{GCIS_COMPANY_API}?{query}"


def parse_gcis_company(payload: Any, *, ubn: str, retrieved_at: str) -> CompanyMaster:
    """OPTIONAL FUTURE PRODUCTION INTEGRATION — parse a GCIS company payload."""
    rows = payload if isinstance(payload, list) else [payload]
    row = next((item for item in rows if isinstance(item, dict)), {})
    capital = _as_int(
        _first(row, "Paid_In_Capital_Amount", "paid_in_capital_amount")
    )
    name = str(_first(row, "Company_Name", "company_name") or "")
    status = str(_first(row, "Company_Status_Desc", "Company_Status") or "")
    address = str(_first(row, "Company_Location", "company_location") or "")
    items = str(_first(row, "Business_Item_Desc", "business_items") or "")
    company_type = str(
        _first(row, "Company_Type", "Register_Organization_Desc") or ""
    )
    return CompanyMaster(
        company_id=f"co_{ubn}",
        unified_business_number=ubn,
        company_name=name,
        official_company_status=status,
        official_registered_address=address,
        official_paid_in_capital_twd=capital,
        confirmed_paid_in_capital_twd=capital,
        business_items=items,
        company_registration_type=company_type,
        lookup_status="ok" if name else "empty",
        last_official_lookup_at=retrieved_at,
        source_records=[
            SourceRecord(
                source_id=GCIS_SOURCE_ID,
                authority="經濟部商業發展署",
                access_mode="OFFICIAL_API",
                retrieved_at=retrieved_at,
                dataset_or_api="公司登記基本資料-應用一",
                raw_source_identifier=GCIS_COMPANY_API_ID,
                verified_access_mode="OFFICIAL_API",
            )
        ],
    )


def parse_official_factories(
    payload: Any, *, ubn: str
) -> list[OfficialFactoryHint]:
    rows = payload if isinstance(payload, list) else [payload]
    hints: list[OfficialFactoryHint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_ubn = str(
            _first(
                row,
                "統一編號",
                "Business_Accounting_NO",
                "ban",
                "ubn",
            )
            or ubn
        )
        if row_ubn and row_ubn != ubn:
            continue
        name = str(
            _first(row, "工廠名稱", "factory_name", "Factory_Name", "name") or ""
        ).strip()
        if not name:
            continue
        hints.append(
            OfficialFactoryHint(
                display_name=name,
                address=str(
                    _first(row, "工廠地址", "address", "Factory_Address") or ""
                ),
                registration_number=str(
                    _first(
                        row,
                        "工廠登記編號",
                        "registration_number",
                        "Factory_ID",
                    )
                    or ""
                ),
                industry_code=str(
                    _first(row, "產業類別", "industry_code", "Industry") or ""
                ),
                main_products=str(
                    _first(row, "主要產品", "main_products", "Product") or ""
                ),
                unified_business_number=ubn,
            )
        )
    return hints


def _listing_from_rows(rows: Any, ubn: str, status: str) -> str:
    if not isinstance(rows, list):
        return "UNKNOWN"
    for row in rows:
        if not isinstance(row, dict):
            continue
        found = str(
            _first(
                row,
                "營利事業統一編號",
                "統一編號",
                "Business_Accounting_NO",
                "ubn",
            )
            or ""
        )
        if found == ubn:
            return status
    return "UNKNOWN"


def _policy_allows(source_id: str, repo_root: Path | None) -> bool:
    policy = policy_for_source(source_id, repo_root=repo_root)
    return bool(policy.automated_access_allowed and policy.expects_scheduled_http)


def _stub_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return str(env.get(STUB_ENV) or "").strip() in {"1", "true", "yes"}


def stub_company(ubn: str) -> CompanyMaster:
    retrieved = utc_now_iso()
    if ubn == STUB_ALIGNED_UBN:
        return CompanyMaster(
            company_id=f"co_{ubn}",
            unified_business_number=ubn,
            company_name="長興材料工業股份有限公司",
            official_company_status="核准設立",
            official_registered_address="高雄市大寮區興業路",
            official_paid_in_capital_twd=12_000_000_000,
            confirmed_paid_in_capital_twd=12_000_000_000,
            listing_status="TWSE",
            listing_source=TWSE_SOURCE_ID,
            business_items="合成樹脂及塑膠製造業",
            lookup_status="ok",
            last_official_lookup_at=retrieved,
            source_records=[
                SourceRecord(
                    source_id=GCIS_SOURCE_ID,
                    authority="經濟部商業發展署",
                    access_mode="OFFICIAL_API",
                    retrieved_at=retrieved,
                    dataset_or_api="公司登記基本資料-應用一",
                    raw_source_identifier=GCIS_COMPANY_API_ID,
                    verified_access_mode="OFFICIAL_API",
                )
            ],
        )
    if ubn == STUB_DIFF_UBN:
        return CompanyMaster(
            company_id=f"co_{ubn}",
            unified_business_number=ubn,
            company_name="高雄示範工業股份有限公司",
            official_company_status="核准設立",
            official_registered_address="高雄市前鎮區",
            official_paid_in_capital_twd=8_000_000_000,
            confirmed_paid_in_capital_twd=8_000_000_000,
            listing_status="TWSE",
            listing_source=TWSE_SOURCE_ID,
            lookup_status="ok",
            last_official_lookup_at=retrieved,
            source_records=[
                SourceRecord(
                    source_id=GCIS_SOURCE_ID,
                    authority="經濟部商業發展署",
                    access_mode="OFFICIAL_API",
                    retrieved_at=retrieved,
                    dataset_or_api="公司登記基本資料-應用一",
                    raw_source_identifier=GCIS_COMPANY_API_ID,
                    verified_access_mode="OFFICIAL_API",
                )
            ],
        )
    if ubn == STUB_SPARSE_UBN:
        return CompanyMaster(
            company_id=f"co_{ubn}",
            unified_business_number=ubn,
            company_name="未公開財務示範股份有限公司",
            official_company_status="核准設立",
            official_registered_address="台北市信義區",
            official_paid_in_capital_twd=None,
            listing_status="UNKNOWN",
            lookup_status="ok",
            last_official_lookup_at=retrieved,
            source_records=[
                SourceRecord(
                    source_id=GCIS_SOURCE_ID,
                    authority="經濟部商業發展署",
                    access_mode="OFFICIAL_API",
                    retrieved_at=retrieved,
                    dataset_or_api="公司登記基本資料-應用一",
                    raw_source_identifier=GCIS_COMPANY_API_ID,
                    verified_access_mode="OFFICIAL_API",
                )
            ],
        )
    if ubn == STUB_SEVEN_UBN:
        return CompanyMaster(
            company_id=f"co_{ubn}",
            unified_business_number=ubn,
            company_name="長興材料工業股份有限公司",
            official_company_status="核准設立",
            official_registered_address="高雄市大寮區興業路",
            official_paid_in_capital_twd=12_000_000_000,
            confirmed_paid_in_capital_twd=12_000_000_000,
            listing_status="TWSE",
            listing_source=TWSE_SOURCE_ID,
            business_items="合成樹脂及塑膠製造業",
            lookup_status="ok",
            last_official_lookup_at=retrieved,
            source_records=[
                SourceRecord(
                    source_id=GCIS_SOURCE_ID,
                    authority="經濟部商業發展署",
                    access_mode="OFFICIAL_API",
                    retrieved_at=retrieved,
                    dataset_or_api="公司登記基本資料-應用一",
                    raw_source_identifier=GCIS_COMPANY_API_ID,
                    verified_access_mode="OFFICIAL_API",
                )
            ],
        )
    return CompanyMaster(
        unified_business_number=ubn,
        lookup_status="empty",
        last_official_lookup_at=retrieved,
    )


def stub_factories(ubn: str) -> list[OfficialFactoryHint]:
    if ubn == STUB_ALIGNED_UBN:
        return [
            OfficialFactoryHint(
                display_name="高雄一廠",
                address="高雄市大寮區",
                registration_number="F-KH-001",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="高雄二廠",
                address="高雄市林園區",
                registration_number="F-KH-002",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="台南廠",
                address="台南市安南區",
                registration_number="F-TN-001",
                unified_business_number=ubn,
            ),
        ]
    if ubn == STUB_DIFF_UBN:
        return [
            OfficialFactoryHint(
                display_name="高雄一廠",
                address="高雄市前鎮區",
                registration_number="F-KH-101",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="高雄二廠",
                address="高雄市小港區",
                registration_number="F-KH-102",
                unified_business_number=ubn,
            ),
        ]
    if ubn == STUB_SEVEN_UBN:
        return [
            OfficialFactoryHint(
                display_name="路竹二廠",
                address="高雄市路竹區",
                registration_number="F-KH-201",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="汐止廠",
                address="新北市汐止區",
                registration_number="F-NT-201",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="路竹一廠",
                address="高雄市路竹區",
                registration_number="F-KH-202",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="大寮廠",
                address="高雄市大寮區",
                registration_number="F-KH-203",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="大園廠",
                address="桃園市大園區",
                registration_number="F-TY-201",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="新竹廠",
                address="新竹市香山區",
                registration_number="F-HC-201",
                unified_business_number=ubn,
            ),
            OfficialFactoryHint(
                display_name="高雄廠",
                address="高雄市前鎮區",
                registration_number="F-KH-204",
                unified_business_number=ubn,
            ),
        ]
    return []


def _gcis_live_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return str(env.get(GCIS_LIVE_ENV) or "").strip() in {"1", "true", "yes"}


def _preserve_customer_overrides(
    company: CompanyMaster, previous: CompanyMaster | None
) -> CompanyMaster:
    if previous is None:
        return company
    if previous.capital_overridden:
        company.capital_overridden = True
        company.confirmed_paid_in_capital_twd = previous.confirmed_paid_in_capital_twd
    if previous.address_overridden:
        company.address_overridden = True
        company.confirmed_registered_address = previous.confirmed_registered_address
    if previous.customer_confirmed_at:
        company.customer_confirmed_at = previous.customer_confirmed_at
    return company


def _authoritative_previous(
    previous: CompanyMaster | None, ubn: str
) -> CompanyMaster | None:
    """Customer-confirmed or customer-entered data for this UBN wins."""
    if previous is None:
        return None
    if previous.unified_business_number != ubn:
        return None
    if previous.customer_confirmed_at:
        return previous
    if previous.lookup_status == "manual":
        return previous
    if previous.data_origin == ORIGIN_CUSTOMER:
        return previous
    return None


def _refresh_official_fields(
    company: CompanyMaster, snapshot: CompanyMaster | None
) -> CompanyMaster:
    """Keep customer-facing corrections; refresh official provenance if present."""
    if snapshot is None:
        return company
    if snapshot.official_paid_in_capital_twd is not None:
        company.official_paid_in_capital_twd = snapshot.official_paid_in_capital_twd
        if not company.capital_overridden:
            company.confirmed_paid_in_capital_twd = (
                company.confirmed_paid_in_capital_twd
                if company.confirmed_paid_in_capital_twd is not None
                else snapshot.official_paid_in_capital_twd
            )
    if snapshot.official_registered_address:
        company.official_registered_address = snapshot.official_registered_address
    if snapshot.listing_status and company.listing_status in {"", "UNKNOWN"}:
        company.listing_status = snapshot.listing_status
        company.listing_source = snapshot.listing_source or company.listing_source
    if snapshot.snapshot_data_date:
        company.snapshot_data_date = snapshot.snapshot_data_date
    if snapshot.source_records:
        existing_ids = {item.source_id for item in company.source_records}
        for record in snapshot.source_records:
            if record.source_id not in existing_ids:
                company.source_records.append(record)
    return company


def _keep_previous_company(
    previous: CompanyMaster | None, ubn: str
) -> CompanyMaster | None:
    if previous is None:
        return None
    if previous.unified_business_number != ubn:
        return None
    if not previous.company_name:
        return None
    return previous


def fetch_official_company(
    ubn: str,
    *,
    repo_root: Path | None = None,
    http_get: Callable[[str], Any] | None = None,
) -> CompanyMaster:
    """OPTIONAL FUTURE PRODUCTION INTEGRATION.

    Live GCIS Open API. Not the V1 default. Requires explicit
    CEL_ENABLE_GCIS_LIVE=1. May need MOEA IP registration in production.
    """
    _count("gcis")
    if not _policy_allows(GCIS_SOURCE_ID, repo_root):
        raise LookupError("policy_denied")
    getter = http_get or _http_get_json
    payload = getter(gcis_company_url(ubn))
    return parse_gcis_company(payload, ubn=ubn, retrieved_at=utc_now_iso())


def fetch_official_factories(
    ubn: str,
    *,
    repo_root: Path | None = None,
    http_get: Callable[[str], Any] | None = None,
    snapshot_rows: list[dict[str, Any]] | None = None,
    snapshot_csv: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[OfficialFactoryHint]:
    """V1 reads the local official factory snapshot. No env is required.

    CEL_FACTORY_OPEN_DATA_URL is optional future/development live HTTP only.
    """
    _count("factory")
    if snapshot_rows is not None:
        return parse_official_factories(snapshot_rows, ubn=ubn)
    csv_path = snapshot_csv or default_factory_csv(repo_root)
    repo = load_factory_repository(csv_path)
    if repo.loaded:
        return repo.hints_for(ubn)
    env = environ if environ is not None else os.environ
    url = str(env.get("CEL_FACTORY_OPEN_DATA_URL") or "").strip()
    if not url:
        return []
    if not _policy_allows(FACTORY_SOURCE_ID, repo_root):
        return []
    getter = http_get or _http_get_json
    return parse_official_factories(getter(url), ubn=ubn)


def fetch_listing_status(
    ubn: str,
    *,
    repo_root: Path | None = None,
    http_get: Callable[[str], Any] | None = None,
) -> str:
    _count("listing")
    getter = http_get or _http_get_json
    if _policy_allows(TWSE_SOURCE_ID, repo_root):
        try:
            if _listing_from_rows(getter(TWSE_LISTING_API), ubn, "TWSE") == "TWSE":
                return "TWSE"
        except Exception:  # noqa: BLE001 - listing is optional
            pass
    if _policy_allows(TPEX_SOURCE_ID, repo_root):
        try:
            if _listing_from_rows(getter(TPEX_LISTING_API), ubn, "TPEX") == "TPEX":
                return "TPEX"
        except Exception:  # noqa: BLE001
            pass
    return "UNKNOWN"


def lookup_company(
    raw_ubn: str,
    *,
    repo_root: Path | None = None,
    force_refresh: bool = False,
    http_get: Callable[[str], Any] | None = None,
    factory_rows: list[dict[str, Any]] | None = None,
    factory_csv: Path | None = None,
    environ: Mapping[str, str] | None = None,
    previous: CompanyMaster | None = None,
    snapshot_csv: Path | None = None,
) -> LookupResult:
    """Validate locally, then look up the local official company snapshot.

    Provider order for V1:
    1. previously customer-confirmed or customer-entered CompanyMaster
    2. LocalOfficialCompanyRepository
    3. optional test stub overlay
    4. customer manual input

    Official snapshot may refresh provenance. It must not overwrite
    customer-confirmed or customer-entered fields for the same UBN.

    Customer CompanyMaster / LookupResult objects are never stored in a
    process-global cache. Official company/factory repositories may be.

    Live GCIS is not in this list unless CEL_ENABLE_GCIS_LIVE is set.
    """
    ubn, error = validate_ubn(raw_ubn)
    if error in {"need_8", "invalid", "reserved"}:
        company = (
            _copy_company(previous)
            if previous is not None
            else CompanyMaster(unified_business_number=str(raw_ubn or ""))
        )
        return LookupResult(
            company=company,
            customer_message="請輸入 8 碼統一編號。",
        )
    _ = force_refresh
    _count("company")

    factories: list[OfficialFactoryHint] = []
    if _stub_enabled(environ) and ubn in STUB_COMPANY_UBNS:
        factories = stub_factories(ubn)
    else:
        factories = fetch_official_factories(
            ubn,
            repo_root=repo_root,
            http_get=http_get,
            snapshot_rows=factory_rows,
            snapshot_csv=factory_csv,
            environ=environ,
        )

    csv_path = snapshot_csv or default_snapshot_csv(repo_root)
    repository = load_company_repository(csv_path)
    snapshot_company = repository.to_company_master(ubn)

    authoritative = _authoritative_previous(previous, ubn)
    if authoritative is not None:
        company = _refresh_official_fields(
            _copy_company(authoritative), snapshot_company
        )
        company = _preserve_customer_overrides(company, previous)
        return _lookup_result(
            company=company,
            factories=factories,
            origin=company.data_origin or ORIGIN_CUSTOMER,
            ok=True,
        )

    if snapshot_company is not None:
        company = _preserve_customer_overrides(
            _copy_company(snapshot_company), previous
        )
        return _lookup_result(
            company=company,
            factories=factories,
            origin=ORIGIN_SNAPSHOT,
            ok=True,
        )

    kept = _keep_previous_company(previous, ubn)
    if kept is not None:
        return _lookup_result(
            company=kept,
            factories=factories,
            origin=kept.data_origin or ORIGIN_CUSTOMER,
            ok=True,
        )

    if _stub_enabled(environ):
        company = stub_company(ubn)
        if company.company_name:
            company = _preserve_customer_overrides(company, previous)
            return _lookup_result(
                company=company,
                factories=factories,
                origin=ORIGIN_OFFICIAL,
                ok=True,
            )

    if _gcis_live_enabled(environ):
        try:
            company = fetch_official_company(
                ubn, repo_root=repo_root, http_get=http_get
            )
            listing = fetch_listing_status(
                ubn, repo_root=repo_root, http_get=http_get
            )
            if listing != "UNKNOWN":
                company.listing_status = listing
                company.listing_source = (
                    TWSE_SOURCE_ID if listing == "TWSE" else TPEX_SOURCE_ID
                )
            company = _preserve_customer_overrides(company, previous)
            company.data_origin = "GCIS_LIVE"
            return _lookup_result(
                company=company,
                factories=factories,
                origin=ORIGIN_OFFICIAL,
                ok=bool(company.company_name),
                customer_message="" if company.company_name else NOT_FOUND_MESSAGE,
                http_attempted=True,
            )
        except Exception:  # noqa: BLE001 - optional live path must not leak
            return _lookup_result(
                company=CompanyMaster(
                    unified_business_number=ubn,
                    lookup_status="empty",
                ),
                factories=factories,
                customer_message=NOT_FOUND_MESSAGE,
                http_attempted=True,
            )

    return _lookup_result(
        company=CompanyMaster(
            unified_business_number=ubn,
            lookup_status="empty",
        ),
        factories=factories,
        customer_message=NOT_FOUND_MESSAGE,
    )


def apply_customer_capital_override(
    company: CompanyMaster, value: int | None
) -> CompanyMaster:
    official = company.official_paid_in_capital_twd
    company.confirmed_paid_in_capital_twd = value
    company.capital_overridden = official is not None and value != official
    if company.capital_overridden and not company.customer_confirmed_at:
        company.customer_confirmed_at = utc_now_iso()
    return company


def apply_customer_address_override(
    company: CompanyMaster, value: str
) -> CompanyMaster:
    """Keep official registered address; store a customer correction separately."""
    text = str(value or "").strip()
    official = str(company.official_registered_address or "").strip()
    if not text or text == official:
        company.address_overridden = False
        company.confirmed_registered_address = ""
        return company
    company.confirmed_registered_address = text
    company.address_overridden = True
    return company


def merge_manual_company(
    *,
    ubn: str,
    name: str,
    previous: CompanyMaster | None = None,
    address: str | None = None,
) -> CompanyMaster:
    base = previous or CompanyMaster()
    base.unified_business_number = ubn
    base.company_name = name
    base.lookup_status = "manual"
    base.data_origin = ORIGIN_CUSTOMER
    if address is not None:
        apply_customer_address_override(base, address)
    if not base.source_records or all(
        item.access_mode != "CUSTOMER_ENTERED" for item in base.source_records
    ):
        base.source_records = [
            *base.source_records,
            SourceRecord(
                source_id="customer",
                authority="",
                access_mode="CUSTOMER_ENTERED",
                retrieved_at=utc_now_iso(),
                verified_access_mode="CUSTOMER_ENTERED",
            ),
        ]
    return base
