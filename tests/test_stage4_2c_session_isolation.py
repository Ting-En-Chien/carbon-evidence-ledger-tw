"""Stage 4.2C — session isolation, factory fallback, address correction."""

from __future__ import annotations

from pathlib import Path

from carbon_ledger.company_lookup import (
    apply_customer_address_override,
    apply_customer_capital_override,
    lookup_company,
    merge_manual_company,
    reset_lookup_cache,
)
from carbon_ledger.company_master import (
    ORIGIN_CUSTOMER,
    CompanyMaster,
    FacilityMaster,
    reconcile_facilities,
    utc_now_iso,
)
from carbon_ledger.company_snapshot import (
    load_company_repository,
    reset_company_repository_cache,
)
from carbon_ledger.factory_snapshot import (
    load_factory_repository,
    reset_factory_repository_cache,
)
from carbon_ledger.ui.company_setup import (
    rebuild_facility_master,
    session_update_from_lookup,
)
from carbon_ledger.ui.i18n import t

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPANY_CSV = REPO_ROOT / "tests" / "fixtures" / "company_master" / "company_master.csv"
FACTORY_CSV = REPO_ROOT / "tests" / "fixtures" / "factory_master" / "factory_master.csv"
FOUND_UBN = "22099131"
FACTORY_ONLY_UBN = "00004131"
ZH = "zh-TW"


def setup_function() -> None:
    reset_lookup_cache()
    reset_company_repository_cache()
    reset_factory_repository_cache()


def _lookup(ubn: str, **kwargs):
    kwargs.setdefault("snapshot_csv", COMPANY_CSV)
    kwargs.setdefault("factory_csv", FACTORY_CSV)
    kwargs.setdefault("repo_root", REPO_ROOT)
    kwargs.setdefault("environ", {})
    return lookup_company(ubn, **kwargs)


def _block_http(*_args, **_kwargs):
    raise AssertionError("lookup must not use HTTP")


def test_customer_a_manual_correction_cannot_appear_in_customer_b() -> None:
    first = _lookup(FOUND_UBN, http_get=_block_http)
    first.company.company_name = "CUSTOMER_A_PRIVATE_CORRECTION"
    first.company.customer_confirmed_at = "USER_A_CONFIRM"
    second = _lookup(FOUND_UBN, previous=None, http_get=_block_http)
    assert second.company.company_name != "CUSTOMER_A_PRIVATE_CORRECTION"
    assert second.company.company_name == "快照官方名稱"
    assert second.company.customer_confirmed_at != "USER_A_CONFIRM"
    assert second.company.customer_confirmed_at == ""
    assert first.company is not second.company


def test_customer_confirmation_timestamp_is_session_local() -> None:
    first = _lookup(FOUND_UBN, http_get=_block_http)
    apply_customer_capital_override(first.company, 1)
    first.company.customer_confirmed_at = "USER_A_CONFIRM"
    second = _lookup(FOUND_UBN, previous=None, http_get=_block_http)
    assert second.company.customer_confirmed_at == ""
    assert second.company.capital_overridden is False
    assert first.company is not second.company


def test_independent_lookups_return_distinct_company_objects() -> None:
    first = _lookup(FOUND_UBN, http_get=_block_http)
    second = _lookup(FOUND_UBN, http_get=_block_http)
    assert first.company is not second.company
    first.company.company_name = "MUTATED"
    assert second.company.company_name != "MUTATED"


def test_official_repository_caching_still_works() -> None:
    first = load_company_repository(COMPANY_CSV)
    second = load_company_repository(COMPANY_CSV)
    assert first is second
    factories_a = load_factory_repository(FACTORY_CSV)
    factories_b = load_factory_repository(FACTORY_CSV)
    assert factories_a is factories_b


def test_lookup_introduces_no_http(monkeypatch) -> None:
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _block_http)
    result = _lookup(FOUND_UBN, http_get=_block_http)
    assert result.ok
    assert result.http_attempted is False


def test_company_not_found_retains_factory_candidate() -> None:
    result = _lookup(FACTORY_ONLY_UBN, http_get=_block_http)
    assert result.ok is False
    assert result.company.company_name == ""
    assert result.customer_message
    assert [item.display_name for item in result.factories] == [
        "川盛信記企業股份有限公司"
    ]
    update = session_update_from_lookup(result)
    assert update["company_found"] is False
    assert update["not_found"] is True
    assert update["manual"] is True
    assert update["company"].company_name == ""
    assert [item.display_name for item in update["factories"]] == [
        "川盛信記企業股份有限公司"
    ]


def test_manual_fallback_does_not_infer_company_name_from_factory() -> None:
    result = _lookup(FACTORY_ONLY_UBN, http_get=_block_http)
    update = session_update_from_lookup(result)
    manual = merge_manual_company(
        ubn=FACTORY_ONLY_UBN,
        name="客戶手動公司",
        previous=update["company"],
    )
    assert manual.company_name == "客戶手動公司"
    assert manual.company_name != "川盛信記企業股份有限公司"
    records = reconcile_facilities(
        official=update["factories"],
        upload_names=[],
        ubn=FACTORY_ONLY_UBN,
    )
    assert [item.display_name for item in records] == ["川盛信記企業股份有限公司"]
    assert all(item.included_in_current_reporting_scope is False for item in records)


def test_no_duplicate_facility_after_manual_company_entry() -> None:
    result = _lookup(FACTORY_ONLY_UBN, http_get=_block_http)
    update = session_update_from_lookup(result)
    existing = FacilityMaster()
    first = rebuild_facility_master(
        session_state={},
        company=update["company"],
        official=update["factories"],
        existing=existing,
        reporting_year=2026,
    )
    manual = merge_manual_company(
        ubn=FACTORY_ONLY_UBN,
        name="客戶手動公司",
        previous=update["company"],
    )
    second = rebuild_facility_master(
        session_state={},
        company=manual,
        official=update["factories"],
        existing=first,
        reporting_year=2026,
    )
    names = [item.display_name for item in second.records]
    assert names == ["川盛信記企業股份有限公司"]
    assert len(second.records) == 1


def test_address_override_preserves_official_value() -> None:
    first = _lookup("11913502", http_get=_block_http)
    official = first.company.official_registered_address
    assert official
    apply_customer_address_override(first.company, "客戶提供地址")
    assert first.company.address_overridden is True
    assert first.company.official_registered_address == official
    assert first.company.registered_address == "客戶提供地址"
    second = _lookup(
        "11913502",
        previous=first.company,
        http_get=_block_http,
    )
    assert second.company.official_registered_address == official
    assert second.company.registered_address == "客戶提供地址"
    assert second.company.address_overridden is True


def test_data_wrong_copy_allows_address_correction() -> None:
    assert t("setup.data_wrong", ZH) == "資料不正確"
    assert "地址" in t("setup.data_wrong.help", ZH)
    assert "官方" in t("setup.data_wrong.help", ZH)
    manual = merge_manual_company(
        ubn="11913502",
        name="客戶修正名稱",
        previous=CompanyMaster(
            unified_business_number="11913502",
            official_registered_address="台北市中山區中山北路2段113號",
            data_origin=ORIGIN_CUSTOMER,
            customer_confirmed_at=utc_now_iso(),
        ),
        address="客戶提供地址",
    )
    assert manual.official_registered_address == "台北市中山區中山北路2段113號"
    assert manual.registered_address == "客戶提供地址"
    assert manual.address_overridden is True
