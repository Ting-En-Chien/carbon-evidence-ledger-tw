"""Tests for Phase 7C reproducible pipeline orchestration."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.pipeline import run_demo_pipeline, validate_run_id

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _core_run() -> object:
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="core_demo",
        ingested_at=FIXED_INGESTED_AT,
    )


def test_valid_run_id_accepted() -> None:
    assert validate_run_id("portfolio_demo") == "portfolio_demo"
    assert validate_run_id("demo-2024") == "demo-2024"
    assert validate_run_id("run.001") == "run.001"


def test_blank_run_id_rejected() -> None:
    with pytest.raises(ValueError):
        validate_run_id("")
    with pytest.raises(ValueError):
        validate_run_id("   ")


def test_traversal_run_id_rejected() -> None:
    with pytest.raises(ValueError):
        validate_run_id("../secret")


def test_slash_rejected() -> None:
    with pytest.raises(ValueError):
        validate_run_id("demo/run")


def test_backslash_rejected() -> None:
    with pytest.raises(ValueError):
        validate_run_id("demo\\run")


def test_overly_long_run_id_rejected() -> None:
    with pytest.raises(ValueError):
        validate_run_id("a" * 65)


def test_core_only_run_completes() -> None:
    result = _core_run()
    assert result.run_id == "core_demo"
    assert result.include_ghg is False
    assert result.include_cbam is False
    assert result.include_ifrs_s2 is False


def test_accepted_source_count_is_5() -> None:
    assert len(_core_run().source_documents_accepted) == 5


def test_accepted_activity_count_is_5() -> None:
    assert len(_core_run().activity_records_accepted) == 5


def test_normalized_count_is_5() -> None:
    assert len(_core_run().normalized_records) == 5


def test_candidate_matches_is_7() -> None:
    assert len(_core_run().candidate_matches) == 7


def test_readiness_is_5() -> None:
    assert len(_core_run().activity_readiness) == 5


def test_calculations_is_5() -> None:
    assert len(_core_run().calculation_results) == 5


def test_qa_issues_is_3() -> None:
    assert len(_core_run().core_qa_issues) == 3


def test_electricity_remains_calculated() -> None:
    result = _core_run()
    row = result.calculation_results.loc[
        result.calculation_results["record_id"] == "rec_electricity_001"
    ].iloc[0]
    assert row["calculation_status"] == "calculated"


def test_natural_gas_remains_blocked() -> None:
    result = _core_run()
    row = result.calculation_results.loc[
        result.calculation_results["record_id"] == "rec_gas_001"
    ].iloc[0]
    assert row["calculation_status"] == "blocked_missing_conversion"


def test_diesel_remains_blocked() -> None:
    result = _core_run()
    row = result.calculation_results.loc[
        result.calculation_results["record_id"] == "rec_diesel_001"
    ].iloc[0]
    assert row["calculation_status"] == "blocked_missing_conversion"


def test_steel_remains_no_factor_configured() -> None:
    result = _core_run()
    row = result.calculation_results.loc[
        result.calculation_results["record_id"] == "rec_steel_001"
    ].iloc[0]
    assert row["calculation_status"] == "no_factor_configured"


def test_output_remains_not_emissions_activity() -> None:
    result = _core_run()
    row = result.calculation_results.loc[
        result.calculation_results["record_id"] == "rec_output_001"
    ].iloc[0]
    assert row["calculation_status"] == "not_emissions_activity"


def test_core_only_ghg_is_empty() -> None:
    assert _core_run().ghg_evaluations.empty


def test_core_only_cbam_is_empty() -> None:
    assert _core_run().cbam_evaluations.empty


def test_core_only_ifrs_s2_is_empty() -> None:
    assert _core_run().ifrs_s2_evaluations.empty


def test_include_ghg_produces_5_rows() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="ghg_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
    )
    assert len(result.ghg_evaluations) == 5
    assert result.include_ghg is True


def test_include_cbam_produces_5_rows() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="cbam_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_cbam=True,
    )
    assert len(result.cbam_evaluations) == 5
    assert result.include_cbam is True


def test_include_ifrs_s2_produces_5_rows() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="ifrs_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ifrs_s2=True,
    )
    assert len(result.ifrs_s2_evaluations) == 5


def test_include_ifrs_s2_also_produces_5_ghg_rows() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="ifrs_ghg_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ifrs_s2=True,
    )
    assert len(result.ghg_evaluations) == 5
    assert result.include_ghg is True


def test_include_ifrs_s2_does_not_produce_cbam() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="ifrs_only_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ifrs_s2=True,
    )
    assert result.cbam_evaluations.empty
    assert result.include_cbam is False


def test_all_adapters_produce_5_rows_each() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="all_adapters_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    assert len(result.ghg_evaluations) == 5
    assert len(result.cbam_evaluations) == 5
    assert len(result.ifrs_s2_evaluations) == 5


def test_adapters_do_not_change_calculations() -> None:
    core = _core_run()
    full = run_demo_pipeline(
        REPO_ROOT,
        run_id="full_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    pd.testing.assert_frame_equal(
        core.calculation_results,
        full.calculation_results,
    )


def test_adapters_do_not_change_core_qa() -> None:
    core = _core_run()
    full = run_demo_pipeline(
        REPO_ROOT,
        run_id="full_qa_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    pd.testing.assert_frame_equal(core.core_qa_issues, full.core_qa_issues)


def test_repeated_runs_are_deterministic() -> None:
    first = run_demo_pipeline(
        REPO_ROOT,
        run_id="repeat_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    second = run_demo_pipeline(
        REPO_ROOT,
        run_id="repeat_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    pd.testing.assert_frame_equal(
        first.calculation_results,
        second.calculation_results,
    )
    pd.testing.assert_frame_equal(first.core_qa_issues, second.core_qa_issues)
    pd.testing.assert_frame_equal(first.ghg_evaluations, second.ghg_evaluations)
    pd.testing.assert_frame_equal(
        first.cbam_evaluations,
        second.cbam_evaluations,
    )
    pd.testing.assert_frame_equal(
        first.ifrs_s2_evaluations,
        second.ifrs_s2_evaluations,
    )


def test_source_and_reference_repository_files_remain_unchanged() -> None:
    before_raw = {
        path.relative_to(RAW_DIR).as_posix(): _sha256(path)
        for path in RAW_DIR.rglob("*")
        if path.is_file()
    }
    before_ref = {
        path.relative_to(REFERENCE_DIR).as_posix(): _sha256(path)
        for path in REFERENCE_DIR.rglob("*")
        if path.is_file()
    }
    run_demo_pipeline(
        REPO_ROOT,
        run_id="unchanged_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    after_raw = {
        path.relative_to(RAW_DIR).as_posix(): _sha256(path)
        for path in RAW_DIR.rglob("*")
        if path.is_file()
    }
    after_ref = {
        path.relative_to(REFERENCE_DIR).as_posix(): _sha256(path)
        for path in REFERENCE_DIR.rglob("*")
        if path.is_file()
    }
    assert after_raw == before_raw
    assert after_ref == before_ref
