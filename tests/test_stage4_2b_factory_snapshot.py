"""Stage 4.2B — local official factory snapshot lookup (offline)."""

from __future__ import annotations

import os
from pathlib import Path

from carbon_ledger.company_lookup import (
    fetch_official_factories,
    lookup_company,
    reset_lookup_cache,
)
from carbon_ledger.company_master import (
    MATCH_ALIGNED,
    MATCH_OFFICIAL_ONLY,
    MATCH_PREVIOUS_ONLY,
    MATCH_UPLOAD_ONLY,
    SOURCE_OFFICIAL_FACTORY,
    SOURCE_PREVIOUS,
    SOURCE_UPLOAD,
    FacilityMasterRecord,
    reconcile_facilities,
)
from carbon_ledger.factory_snapshot import (
    load_factory_repository,
    normalize_factory_row,
    reset_factory_repository_cache,
)
from carbon_ledger.pipeline import run_uploaded_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = REPO_ROOT / "tests" / "fixtures" / "factory_master" / "raw" / "factories.csv"
FIXTURE_CSV = (
    REPO_ROOT / "tests" / "fixtures" / "factory_master" / "factory_master.csv"
)
COMPANY_CSV = REPO_ROOT / "tests" / "fixtures" / "company_master" / "company_master.csv"
FOUND_UBN = "11913502"
LEADING_ZERO_UBN = "00000016"
RESERVED_UBN = "00000000"


def setup_function() -> None:
    reset_lookup_cache()
    reset_factory_repository_cache()


def _block_http(*_args, **_kwargs):
    raise AssertionError("factory snapshot lookup must not use HTTP")


def test_normalize_drops_reserved_ubn_and_personal_name() -> None:
    kept = normalize_factory_row(
        {
            "工廠名稱": "高雄一廠",
            "工廠登記編號": "F-KH-001",
            "工廠地址": "高雄市大寮區",
            "工廠負責人姓名": "MUST_NOT_BE_COPIED",
            "統一編號": FOUND_UBN,
            "產業類別": "25金屬製品",
            "主要產品": "鋼構",
        }
    )
    assert kept is not None
    assert kept["factory_name"] == "高雄一廠"
    assert "MUST_NOT_BE_COPIED" not in kept.values()
    assert "工廠負責人姓名" not in kept
    dropped = normalize_factory_row(
        {
            "工廠名稱": "佔位廠",
            "統一編號": RESERVED_UBN,
            "工廠負責人姓名": "MUST_NOT_BE_COPIED",
        }
    )
    assert dropped is None
    leading = normalize_factory_row(
        {
            "工廠名稱": "合法前導零廠",
            "統一編號": LEADING_ZERO_UBN,
        }
    )
    assert leading is not None
    assert leading["unified_business_number"] == LEADING_ZERO_UBN


def test_factory_lookup_by_ubn_from_local_snapshot() -> None:
    hints = fetch_official_factories(
        FOUND_UBN,
        repo_root=REPO_ROOT,
        snapshot_csv=FIXTURE_CSV,
        http_get=_block_http,
        environ={},
    )
    names = [item.display_name for item in hints]
    assert names == ["高雄一廠", "高雄二廠"]
    assert all(item.unified_business_number == FOUND_UBN for item in hints)
    empty = fetch_official_factories(
        "10000009",
        repo_root=REPO_ROOT,
        snapshot_csv=FIXTURE_CSV,
        http_get=_block_http,
        environ={},
    )
    assert empty == []


def test_factory_lookup_requires_no_env_configuration(monkeypatch) -> None:
    monkeypatch.delenv("CEL_FACTORY_OPEN_DATA_URL", raising=False)
    assert "CEL_FACTORY_OPEN_DATA_URL" not in os.environ
    result = lookup_company(
        FOUND_UBN,
        repo_root=REPO_ROOT,
        snapshot_csv=COMPANY_CSV,
        factory_csv=FIXTURE_CSV,
        environ={},
        http_get=_block_http,
        force_refresh=True,
    )
    assert result.ok
    assert [item.display_name for item in result.factories] == [
        "高雄一廠",
        "高雄二廠",
    ]


def test_registered_factory_is_candidate_not_boundary() -> None:
    hints = fetch_official_factories(
        FOUND_UBN,
        snapshot_csv=FIXTURE_CSV,
        environ={},
        http_get=_block_http,
    )
    records = reconcile_facilities(
        official=hints,
        upload_names=["高雄一廠", "台中辦公室"],
        previous=[
            FacilityMasterRecord(
                facility_id="fac_prev",
                display_name="去年已確認廠",
                customer_confirmed=True,
                source_type=SOURCE_PREVIOUS,
            )
        ],
        ubn=FOUND_UBN,
    )
    by_name = {item.display_name: item for item in records}
    assert by_name["高雄一廠"].match_state == MATCH_ALIGNED
    assert SOURCE_OFFICIAL_FACTORY in by_name["高雄一廠"].discovered_from
    assert SOURCE_UPLOAD in by_name["高雄一廠"].discovered_from
    assert by_name["高雄二廠"].match_state == MATCH_OFFICIAL_ONLY
    assert by_name["高雄二廠"].included_in_current_reporting_scope is False
    assert by_name["高雄二廠"].customer_confirmed is False
    assert by_name["台中辦公室"].match_state == MATCH_UPLOAD_ONLY
    assert SOURCE_UPLOAD in by_name["台中辦公室"].discovered_from
    assert by_name["去年已確認廠"].match_state == MATCH_PREVIOUS_ONLY


def test_build_script_excludes_reserved_ubn_and_personal_fields(
    tmp_path, monkeypatch
) -> None:
    import importlib.util
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _block_http)
    spec = importlib.util.spec_from_file_location(
        "build_factory_snapshot",
        REPO_ROOT / "scripts" / "build_factory_snapshot.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.build_factory_snapshot(
        repo_root=tmp_path,
        from_csv=RAW_CSV,
        downloaded_at="2026-08-16T00:00:00+00:00",
    )
    import pandas as pd

    csv_path = tmp_path / "data" / "reference" / "factory_master" / "factory_master.csv"
    text = csv_path.read_text(encoding="utf-8")
    frame = pd.read_csv(csv_path, dtype=str).fillna("")
    ubns = set(frame["unified_business_number"].astype(str))
    assert RESERVED_UBN not in ubns
    assert LEADING_ZERO_UBN in ubns
    assert FOUND_UBN in ubns
    assert "MUST_NOT_BE_COPIED" not in text
    assert "工廠負責人姓名" not in text
    assert metadata["record_count"] == 4
    assert metadata["quality"]["unique_ubn_count"] == 3


def test_failed_factory_refresh_does_not_overwrite_snapshot(tmp_path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_factory_snapshot",
        REPO_ROOT / "scripts" / "build_factory_snapshot.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    csv_path = tmp_path / "data" / "reference" / "factory_master" / "factory_master.csv"
    meta_path = (
        tmp_path
        / "data"
        / "reference"
        / "factory_master"
        / "factory_master_metadata.json"
    )
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("KEEP_FACTORY\n", encoding="utf-8")
    meta_path.write_text('{"keep": true}\n', encoding="utf-8")
    empty = tmp_path / "empty.csv"
    empty.write_text("工廠名稱,統一編號\n", encoding="utf-8")
    try:
        module.build_factory_snapshot(repo_root=tmp_path, from_csv=empty)
        raise AssertionError("build must fail when factory source is empty")
    except module.FactorySnapshotBuildError:
        pass
    assert csv_path.read_text(encoding="utf-8") == "KEEP_FACTORY\n"
    assert '"keep": true' in meta_path.read_text(encoding="utf-8")


def test_factory_repository_is_cached() -> None:
    first = load_factory_repository(FIXTURE_CSV)
    second = load_factory_repository(FIXTURE_CSV)
    assert first is second
    assert FOUND_UBN in first.rows_by_ubn
    assert first.loaded is True


def test_calculations_do_not_import_factory_snapshot() -> None:
    import carbon_ledger.calculate as calculate
    import carbon_ledger.pipeline as pipeline

    assert "factory_snapshot" not in calculate.__dict__
    assert "factory_snapshot" not in pipeline.__dict__
    assert callable(run_uploaded_pipeline)
