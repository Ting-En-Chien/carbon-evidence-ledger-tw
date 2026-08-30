"""Stage 4.2A — local official company snapshot lookup (offline)."""

from __future__ import annotations

import urllib.request
from pathlib import Path

from carbon_ledger.company_lookup import (
    GCIS_LIVE_ENV,
    NOT_FOUND_MESSAGE,
    apply_customer_capital_override,
    fetch_official_company,
    lookup_call_count,
    lookup_company,
    merge_manual_company,
    reset_lookup_cache,
)
from carbon_ledger.company_master import (
    ORIGIN_CUSTOMER,
    ORIGIN_SNAPSHOT,
    CompanyMaster,
    utc_now_iso,
)
from carbon_ledger.company_snapshot import (
    coverage_statement_zh,
    load_company_repository,
    merge_snapshot_rows,
    normalize_source_row,
    reset_company_repository_cache,
    snapshot_quality_report,
)
from carbon_ledger.factory_snapshot import reset_factory_repository_cache
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.ui.i18n import t

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "company_master"
FIXTURE_CSV = FIXTURE_DIR / "company_master.csv"
RAW_DIR = FIXTURE_DIR / "raw"
ZH = "zh-TW"
FOUND_UBN = "11913502"
CONFIRMED_UBN = "22099131"
LEADING_ZERO_UBN = "00000016"
RESERVED_UBN = "00000000"
MISSING_CAPITAL_UBN = "10000009"
MISSING_ADDRESS_UBN = "10000015"
NOT_IN_SNAPSHOT_UBN = "10000021"
INVALID_UBN = "12345678"


def setup_function() -> None:
    reset_lookup_cache()
    reset_company_repository_cache()
    reset_factory_repository_cache()


def _lookup(ubn: str, **kwargs):
    kwargs.setdefault("snapshot_csv", FIXTURE_CSV)
    kwargs.setdefault("repo_root", REPO_ROOT)
    kwargs.setdefault("environ", {})
    kwargs.setdefault(
        "factory_csv",
        REPO_ROOT / "tests" / "fixtures" / "factory_master" / "factory_master.csv",
    )
    return lookup_company(ubn, **kwargs)


def _block_http(*_args, **_kwargs):
    raise AssertionError("snapshot lookup must not use HTTP")


def test_valid_ubn_found_in_local_snapshot() -> None:
    result = _lookup(FOUND_UBN)
    assert result.ok
    assert result.http_attempted is False
    assert result.origin == ORIGIN_SNAPSHOT
    assert result.company.unified_business_number == FOUND_UBN
    assert result.company.data_origin == ORIGIN_SNAPSHOT


def test_company_name_and_official_address_populated() -> None:
    company = _lookup(FOUND_UBN).company
    assert company.company_name == "台灣水泥股份有限公司"
    assert "台北市" in company.official_registered_address


def test_paid_in_capital_populated_when_present() -> None:
    company = _lookup(FOUND_UBN).company
    assert company.official_paid_in_capital_twd == 77_231_817_420
    assert company.confirmed_paid_in_capital_twd == 77_231_817_420


def test_unavailable_official_fields_remain_none() -> None:
    missing_capital = _lookup(MISSING_CAPITAL_UBN).company
    assert missing_capital.company_name
    assert missing_capital.official_paid_in_capital_twd is None
    missing_address = _lookup(MISSING_ADDRESS_UBN).company
    assert missing_address.company_name
    assert missing_address.official_registered_address == ""
    assert missing_address.official_paid_in_capital_twd == 2_500_000_000


def test_ubn_not_found_allows_manual_fallback() -> None:
    result = _lookup(NOT_IN_SNAPSHOT_UBN)
    assert result.ok is False
    assert result.http_attempted is False
    assert result.customer_message == NOT_FOUND_MESSAGE
    assert "查詢失敗" not in result.customer_message
    assert "API" not in result.customer_message
    manual = merge_manual_company(
        ubn=NOT_IN_SNAPSHOT_UBN,
        name="客戶自行填寫公司",
        previous=result.company,
    )
    assert manual.data_origin == ORIGIN_CUSTOMER
    assert manual.company_name == "客戶自行填寫公司"


def test_malformed_ubn_rejected_locally() -> None:
    need_eight = _lookup("1234-567")
    assert need_eight.ok is False
    assert "8 碼" in need_eight.customer_message
    invalid = _lookup(INVALID_UBN)
    assert invalid.ok is False
    assert "8 碼" in invalid.customer_message


def test_snapshot_lookup_makes_zero_http_requests(monkeypatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _block_http)
    monkeypatch.setattr(
        "carbon_ledger.company_lookup._http_get_json",
        _block_http,
    )
    monkeypatch.setattr(
        "carbon_ledger.company_lookup.fetch_official_company",
        _block_http,
    )
    result = _lookup(FOUND_UBN, http_get=_block_http)
    assert result.ok
    assert lookup_call_count("gcis") == 0


def test_customer_override_preserved() -> None:
    first = _lookup(FOUND_UBN)
    apply_customer_capital_override(first.company, 9_000_000_000)
    assert first.company.capital_overridden is True
    assert first.company.official_paid_in_capital_twd == 77_231_817_420
    assert first.company.confirmed_paid_in_capital_twd == 9_000_000_000
    assert first.company.customer_confirmed_at
    reset_lookup_cache()
    second = _lookup(
        FOUND_UBN,
        previous=first.company,
        force_refresh=True,
        http_get=_block_http,
    )
    assert second.company.official_paid_in_capital_twd == 77_231_817_420
    assert second.company.confirmed_paid_in_capital_twd == 9_000_000_000
    assert second.company.capital_overridden is True


def test_snapshot_missing_does_not_erase_confirmed_company() -> None:
    confirmed = CompanyMaster(
        unified_business_number=NOT_IN_SNAPSHOT_UBN,
        company_name="已確認公司",
        official_paid_in_capital_twd=12_000_000_000,
        confirmed_paid_in_capital_twd=11_000_000_000,
        capital_overridden=True,
        customer_confirmed_at=utc_now_iso(),
        data_origin=ORIGIN_CUSTOMER,
    )
    result = _lookup(
        NOT_IN_SNAPSHOT_UBN,
        previous=confirmed,
        force_refresh=True,
        http_get=_block_http,
    )
    assert result.ok
    assert result.http_attempted is False
    assert result.company.company_name == "已確認公司"
    assert result.company.confirmed_paid_in_capital_twd == 11_000_000_000
    assert result.company.official_paid_in_capital_twd == 12_000_000_000


def test_local_repository_is_cached() -> None:
    first = load_company_repository(FIXTURE_CSV)
    second = load_company_repository(FIXTURE_CSV)
    assert first is second
    assert FOUND_UBN in first.rows_by_ubn


def test_source_metadata_preserved() -> None:
    company = _lookup(FOUND_UBN).company
    assert company.snapshot_data_date == "2026-08-15"
    assert company.source_records
    record = company.source_records[0]
    assert record.authority == "臺灣證券交易所"
    assert record.access_mode == "OFFICIAL_OPEN_DATA"
    assert "t187ap03_L" in record.dataset_or_api
    assert record.source_id == "src_tw_twse_portal"


def test_gcis_live_adapter_not_invoked_in_default_customer_workflow(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "carbon_ledger.company_lookup.fetch_official_company",
        _block_http,
    )
    found = _lookup(FOUND_UBN)
    missing = _lookup(NOT_IN_SNAPSHOT_UBN, force_refresh=True)
    assert found.ok
    assert missing.ok is False
    assert lookup_call_count("gcis") == 0
    assert GCIS_LIVE_ENV not in {"1"}


def test_ten_billion_capital_retained_when_present_in_source_fixture() -> None:
    raw_listed = [
        {
            "出表日期": "1150815",
            "公司代號": "1101",
            "公司名稱": "台灣水泥股份有限公司",
            "住址": "台北市中山區中山北路2段113號",
            "營利事業統一編號": "11913502",
            "實收資本額": "77231817420",
            "董事長": "MUST_NOT_BE_COPIED",
        },
        {
            "出表日期": "1150815",
            "公司代號": "9998",
            "公司名稱": "應被去重的重複列",
            "住址": "舊址",
            "營利事業統一編號": "11913502",
            "實收資本額": "1",
        },
    ]
    rows = []
    for raw, listing in ((raw_listed[0], "TWSE"), (raw_listed[1], "TPEX")):
        item = normalize_source_row(
            raw,
            listing_status=listing,
            source_id="src_tw_twse_portal",
            authority="臺灣證券交易所",
            dataset="test",
        )
        assert item is not None
        assert "董事長" not in item
        rows.append(item)
    merged = merge_snapshot_rows(rows)
    assert len(merged) == 1
    kept = merged[0]
    assert kept["unified_business_number"] == FOUND_UBN
    assert kept["paid_in_capital_twd"] == 77_231_817_420
    assert kept["listing_status"] == "TWSE"
    quality = snapshot_quality_report(merged)
    assert quality["records_paid_in_capital_ge_10b"] == 1
    company = _lookup(FOUND_UBN).company
    assert company.official_paid_in_capital_twd >= 10_000_000_000


def test_build_script_uses_local_fixture_without_http(tmp_path, monkeypatch) -> None:
    import importlib.util

    monkeypatch.setattr(urllib.request, "urlopen", _block_http)
    spec = importlib.util.spec_from_file_location(
        "build_company_snapshot",
        REPO_ROOT / "scripts" / "build_company_snapshot.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.build_snapshot(
        repo_root=tmp_path,
        getter=_block_http,
        from_dir=RAW_DIR,
        downloaded_at="2026-08-16T00:00:00+00:00",
    )
    assert metadata["record_count"] >= 3
    assert metadata["quality"]["records_paid_in_capital_ge_10b"] >= 1
    csv_path = tmp_path / "data" / "reference" / "company_master" / "company_master.csv"
    assert csv_path.is_file()
    text = csv_path.read_text(encoding="utf-8")
    assert "MUST_NOT_BE_COPIED" not in text
    assert "11913502" in text


def test_calculations_do_not_import_company_lookup_networking() -> None:
    import carbon_ledger.calculate as calculate
    import carbon_ledger.pipeline as pipeline

    assert "company_lookup" not in calculate.__dict__
    assert "company_snapshot" not in calculate.__dict__
    assert "factory_snapshot" not in calculate.__dict__
    assert "company_lookup" not in pipeline.__dict__
    assert "company_snapshot" not in pipeline.__dict__
    assert "factory_snapshot" not in pipeline.__dict__
    assert "urllib" not in calculate.__dict__
    assert callable(run_uploaded_pipeline)


def test_customer_copy_does_not_claim_live_api() -> None:
    help_text = t("setup.ubn.help", ZH)
    source = t("setup.source.open_data", ZH)
    assert "即時" not in help_text
    assert "GCIS" not in help_text
    assert "API" not in help_text
    assert source == "政府公開資料"
    assert "目前的官方公司資料庫沒有找到這個統編。" == t("setup.not_found", ZH)
    assert fetch_official_company.__doc__
    assert "OPTIONAL FUTURE" in fetch_official_company.__doc__


def test_customer_confirmed_company_survives_repeated_lookup() -> None:
    previous = CompanyMaster(
        unified_business_number=CONFIRMED_UBN,
        company_name="客戶修正名稱",
        lookup_status="manual",
        customer_confirmed_at=utc_now_iso(),
        data_origin=ORIGIN_CUSTOMER,
        official_paid_in_capital_twd=1,
        confirmed_paid_in_capital_twd=1,
    )
    first = _lookup(CONFIRMED_UBN, previous=previous, force_refresh=True)
    assert first.company.company_name == "客戶修正名稱"
    reset_lookup_cache()
    second = _lookup(CONFIRMED_UBN, previous=first.company, force_refresh=True)
    assert second.company.company_name == "客戶修正名稱"
    assert second.company.official_paid_in_capital_twd == 12_000_000_000


def test_manual_company_name_survives_repeated_lookup() -> None:
    previous = merge_manual_company(
        ubn=CONFIRMED_UBN,
        name="客戶自行填寫名稱",
    )
    result = _lookup(CONFIRMED_UBN, previous=previous, force_refresh=True)
    assert result.ok
    assert result.company.company_name == "客戶自行填寫名稱"
    assert result.company.lookup_status == "manual"


def test_different_ubn_does_not_reuse_previous_company() -> None:
    previous = CompanyMaster(
        unified_business_number=CONFIRMED_UBN,
        company_name="客戶修正名稱",
        lookup_status="manual",
        customer_confirmed_at=utc_now_iso(),
        data_origin=ORIGIN_CUSTOMER,
    )
    result = _lookup(FOUND_UBN, previous=previous, force_refresh=True)
    assert result.company.unified_business_number == FOUND_UBN
    assert result.company.company_name == "台灣水泥股份有限公司"
    assert result.company.company_name != "客戶修正名稱"


def test_unconfirmed_previous_is_enriched_from_snapshot() -> None:
    empty = CompanyMaster(unified_business_number=FOUND_UBN)
    filled = _lookup(FOUND_UBN, previous=empty, force_refresh=True)
    assert filled.company.company_name == "台灣水泥股份有限公司"
    stale = CompanyMaster(
        unified_business_number=FOUND_UBN,
        company_name="過期未確認名稱",
        lookup_status="ok",
    )
    refreshed = _lookup(FOUND_UBN, previous=stale, force_refresh=True)
    assert refreshed.company.company_name == "台灣水泥股份有限公司"


def test_reserved_placeholder_ubn_rejected_at_runtime() -> None:
    from carbon_ledger.company_master import validate_ubn

    checked, error = validate_ubn(RESERVED_UBN)
    assert checked == RESERVED_UBN
    assert error == "reserved"
    result = _lookup(RESERVED_UBN, force_refresh=True)
    assert result.ok is False
    assert "8 碼" in result.customer_message
    leading = _lookup(LEADING_ZERO_UBN, force_refresh=True)
    assert leading.ok
    assert leading.company.company_name == "前導零合法統編示範股份有限公司"


def test_reserved_placeholder_ubn_excluded_from_built_snapshot(
    tmp_path, monkeypatch
) -> None:
    import importlib.util

    monkeypatch.setattr(urllib.request, "urlopen", _block_http)
    spec = importlib.util.spec_from_file_location(
        "build_company_snapshot",
        REPO_ROOT / "scripts" / "build_company_snapshot.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.build_snapshot(
        repo_root=tmp_path,
        getter=_block_http,
        from_dir=RAW_DIR,
        downloaded_at="2026-08-16T00:00:00+00:00",
    )
    csv_path = tmp_path / "data" / "reference" / "company_master" / "company_master.csv"
    import pandas as pd

    frame = pd.read_csv(csv_path, dtype=str).fillna("")
    ubns = set(frame["unified_business_number"].astype(str))
    assert RESERVED_UBN not in ubns
    assert LEADING_ZERO_UBN in ubns
    assert CONFIRMED_UBN in ubns
    assert "公開發行" in metadata["coverage_statement_zh"]
    assert metadata["quality"]["source_distribution"]["PUBLIC"] >= 1


def test_coverage_statement_matches_included_sources_only() -> None:
    listed_otc = coverage_statement_zh(["TWSE", "TPEX"])
    assert "上市" in listed_otc
    assert "上櫃" in listed_otc
    assert "公開發行" not in listed_otc
    full = coverage_statement_zh(["TWSE", "TPEX", "PUBLIC"])
    assert "上市" in full and "上櫃" in full and "公開發行" in full


def test_failed_or_empty_source_does_not_overwrite_snapshot(tmp_path) -> None:
    import importlib.util
    import shutil

    spec = importlib.util.spec_from_file_location(
        "build_company_snapshot",
        REPO_ROOT / "scripts" / "build_company_snapshot.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    csv_path = tmp_path / "data" / "reference" / "company_master" / "company_master.csv"
    meta_dir = tmp_path / "data" / "reference" / "company_master"
    meta_path = meta_dir / "company_master_metadata.json"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("KEEP_LAST_KNOWN_GOOD\n", encoding="utf-8")
    meta_path.write_text('{"keep": true}\n', encoding="utf-8")
    incomplete = tmp_path / "raw"
    incomplete.mkdir()
    shutil.copy(RAW_DIR / "twse.json", incomplete / "twse.json")
    shutil.copy(RAW_DIR / "tpex.json", incomplete / "tpex.json")
    try:
        module.build_snapshot(
            repo_root=tmp_path,
            getter=_block_http,
            from_dir=incomplete,
        )
        raise AssertionError("build must fail when PUBLIC is missing")
    except module.SnapshotBuildError as exc:
        assert "PUBLIC" in str(exc)
    assert csv_path.read_text(encoding="utf-8") == "KEEP_LAST_KNOWN_GOOD\n"
    assert '"keep": true' in meta_path.read_text(encoding="utf-8")

    empty_public = tmp_path / "raw_empty"
    empty_public.mkdir()
    shutil.copy(RAW_DIR / "twse.json", empty_public / "twse.json")
    shutil.copy(RAW_DIR / "tpex.json", empty_public / "tpex.json")
    (empty_public / "public.json").write_text("[]\n", encoding="utf-8")
    try:
        module.build_snapshot(
            repo_root=tmp_path,
            getter=_block_http,
            from_dir=empty_public,
        )
        raise AssertionError("build must fail when PUBLIC is empty")
    except module.SnapshotBuildError as exc:
        assert "zero usable rows" in str(exc)
    assert csv_path.read_text(encoding="utf-8") == "KEEP_LAST_KNOWN_GOOD\n"
