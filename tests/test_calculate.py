"""Tests for Phase 5C limited and auditable emissions calculation."""

from __future__ import annotations

import hashlib
import math
import shutil
from pathlib import Path

import pandas as pd

from carbon_ledger.calculate import OUTPUT_COLUMNS, calculate_activity_emissions
from carbon_ledger.factors import validate_factor_registry
from carbon_ledger.ingest import ingest_evidence
from carbon_ledger.match_factors import match_activity_factors
from carbon_ledger.normalize import normalize_activity_records

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T12:00:00")
FIXED_RUN_ID = "test_run_phase5c_001"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_raw_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "raw"
    shutil.copytree(RAW_DIR, destination)
    return destination


def _baseline_pipeline(tmp_path: Path) -> pd.DataFrame:
    raw = _copy_raw_tree(tmp_path)
    ingestion = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    accepted = ingestion.activity_records.accepted
    normalized = normalize_activity_records(accepted)
    activities = accepted.merge(
        normalized[["record_id", "normalized_unit", "normalization_status"]],
        on="record_id",
        how="left",
    )
    registry = validate_factor_registry(REFERENCE_DIR)
    matching = match_activity_factors(
        activity_records=activities,
        emission_factors=registry.emission_factors,
        calculation_dependencies=registry.calculation_dependencies,
    )
    return calculate_activity_emissions(
        normalized_records=normalized,
        candidate_matches=matching.candidate_matches,
        activity_readiness=matching.activity_readiness,
        emission_factors=registry.emission_factors,
    )


def _normalized_row(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "record_id": "rec_electricity_001",
        "activity_type": "grid_electricity",
        "original_value": 50000.0,
        "original_unit": "kWh",
        "normalized_value": 50000.0,
        "normalized_unit": "kWh",
        "normalization_status": "already_canonical",
        "normalization_reason": "test",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _readiness_row(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "record_id": "rec_electricity_001",
        "activity_type": "grid_electricity",
        "calculation_readiness": "ready",
        "candidate_factor_count": 1,
        "blocking_dependency": pd.NA,
        "readiness_reason": "ready for test",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _ready_candidate(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "record_id": "rec_electricity_001",
        "activity_type": "grid_electricity",
        "factor_id": "ef_tw_grid_electricity_2024",
        "gas": "CO2e",
        "activity_unit": "kWh",
        "factor_denominator_unit": "kWh",
        "match_status": "matched_ready",
        "match_reason": "ready",
        "required_conversion": "not_required",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _registry_factors() -> pd.DataFrame:
    return validate_factor_registry(REFERENCE_DIR).emission_factors


def test_baseline_returns_exactly_five_rows(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    assert len(result) == 5


def test_electricity_calculation_status_is_calculated(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["calculation_status"] == "calculated"


def test_electricity_result_is_23700_kgco2e(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["calculated_kgco2e"] == 23700.0


def test_electricity_result_is_23_7_tco2e(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["calculated_tco2e"] == 23.7


def test_electricity_factor_id_is_preserved(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["factor_id"] == "ef_tw_grid_electricity_2024"


def test_electricity_source_reference_id_is_preserved(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["source_reference_id"] == "ref_tw_moea_2024_electricity_factor"


def test_electricity_formula_id_and_version_are_preserved(
    tmp_path: Path,
) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["formula_id"] == "activity_value_times_direct_co2e_factor"
    assert row["formula_version"] == "1.0"


def test_natural_gas_remains_blocked_missing_conversion(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["calculation_status"] == "blocked_missing_conversion"


def test_natural_gas_calculated_values_are_missing(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert pd.isna(row["calculated_kgco2e"])
    assert pd.isna(row["calculated_tco2e"])
    assert pd.isna(row["factor_id"])


def test_natural_gas_reason_names_required_conversion(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert "verified_natural_gas_heating_value_m3_to_TJ" in row[
        "calculation_reason"
    ]


def test_diesel_remains_blocked_missing_conversion(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["calculation_status"] == "blocked_missing_conversion"


def test_diesel_calculated_values_are_missing(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert pd.isna(row["calculated_kgco2e"])
    assert pd.isna(row["calculated_tco2e"])


def test_diesel_reason_names_required_conversion(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert "verified_diesel_heating_value_L_to_TJ" in row["calculation_reason"]


def test_purchased_steel_remains_no_factor_configured(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert row["calculation_status"] == "no_factor_configured"
    assert pd.isna(row["calculated_kgco2e"])


def test_finished_output_remains_not_emissions_activity(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert row["calculation_status"] == "not_emissions_activity"
    assert pd.isna(row["calculated_tco2e"])


def test_blocked_rows_do_not_contain_fake_zero_emissions(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    blocked = result.loc[result["calculation_status"] != "calculated"]
    assert len(blocked) == 4
    assert blocked["calculated_kgco2e"].isna().all()
    assert blocked["calculated_tco2e"].isna().all()
    assert not (blocked["calculated_kgco2e"] == 0).any()


def test_ready_activity_with_no_candidate_is_inconsistent() -> None:
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(),
        candidate_matches=pd.DataFrame(
            columns=[
                "record_id",
                "activity_type",
                "factor_id",
                "gas",
                "activity_unit",
                "factor_denominator_unit",
                "match_status",
                "match_reason",
                "required_conversion",
            ]
        ),
        activity_readiness=_readiness_row(),
        emission_factors=_registry_factors(),
    )
    assert result.iloc[0]["calculation_status"] == "factor_match_inconsistent"


def test_ready_activity_with_two_ready_candidates_is_inconsistent() -> None:
    candidates = pd.concat(
        [
            _ready_candidate(),
            _ready_candidate(factor_id="ef_tw_grid_electricity_2024_dup"),
        ],
        ignore_index=True,
    )
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(),
        candidate_matches=candidates,
        activity_readiness=_readiness_row(candidate_factor_count=2),
        emission_factors=_registry_factors(),
    )
    assert result.iloc[0]["calculation_status"] == "factor_match_inconsistent"


def test_candidate_factor_missing_from_registry_is_inconsistent() -> None:
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(),
        candidate_matches=_ready_candidate(factor_id="ef_does_not_exist"),
        activity_readiness=_readiness_row(),
        emission_factors=_registry_factors(),
    )
    assert result.iloc[0]["calculation_status"] == "factor_match_inconsistent"


def test_incompatible_denominator_is_inconsistent() -> None:
    factors = _registry_factors().copy()
    mask = factors["factor_id"] == "ef_tw_grid_electricity_2024"
    factors.loc[mask, "denominator_unit"] = "MWh"
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(),
        candidate_matches=_ready_candidate(),
        activity_readiness=_readiness_row(),
        emission_factors=factors,
    )
    assert result.iloc[0]["calculation_status"] == "factor_match_inconsistent"


def test_non_co2e_direct_factor_is_inconsistent() -> None:
    factors = _registry_factors().copy()
    mask = factors["factor_id"] == "ef_tw_grid_electricity_2024"
    factors.loc[mask, "gas"] = "CO2"
    factors.loc[mask, "numerator_unit"] = "kgCO2"
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(),
        candidate_matches=_ready_candidate(),
        activity_readiness=_readiness_row(),
        emission_factors=factors,
    )
    assert result.iloc[0]["calculation_status"] == "factor_match_inconsistent"


def test_missing_normalized_value_is_invalid_input() -> None:
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(normalized_value=pd.NA),
        candidate_matches=_ready_candidate(),
        activity_readiness=_readiness_row(),
        emission_factors=_registry_factors(),
    )
    assert result.iloc[0]["calculation_status"] == "invalid_normalized_input"


def test_zero_normalized_value_is_invalid_input() -> None:
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(normalized_value=0.0),
        candidate_matches=_ready_candidate(),
        activity_readiness=_readiness_row(),
        emission_factors=_registry_factors(),
    )
    assert result.iloc[0]["calculation_status"] == "invalid_normalized_input"


def test_negative_normalized_value_is_invalid_input() -> None:
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(normalized_value=-10.0),
        candidate_matches=_ready_candidate(),
        activity_readiness=_readiness_row(),
        emission_factors=_registry_factors(),
    )
    assert result.iloc[0]["calculation_status"] == "invalid_normalized_input"


def test_infinite_normalized_value_is_invalid_input() -> None:
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(normalized_value=math.inf),
        candidate_matches=_ready_candidate(),
        activity_readiness=_readiness_row(),
        emission_factors=_registry_factors(),
    )
    assert result.iloc[0]["calculation_status"] == "invalid_normalized_input"


def test_invalid_factor_value_is_inconsistent() -> None:
    factors = _registry_factors().copy()
    mask = factors["factor_id"] == "ef_tw_grid_electricity_2024"
    factors.loc[mask, "factor_value"] = "-1"
    result = calculate_activity_emissions(
        normalized_records=_normalized_row(),
        candidate_matches=_ready_candidate(),
        activity_readiness=_readiness_row(),
        emission_factors=factors,
    )
    assert result.iloc[0]["calculation_status"] == "factor_match_inconsistent"


def test_output_preserves_one_row_per_readiness_record(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    assert len(result) == 5
    assert result["record_id"].is_unique
    assert result["calculation_id"].tolist() == [
        f"calc_{record_id}" for record_id in result["record_id"]
    ]


def test_output_ordering_is_deterministic(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    assert result["record_id"].tolist() == sorted(result["record_id"].tolist())


def test_input_dataframes_are_not_mutated() -> None:
    normalized = _normalized_row()
    candidates = _ready_candidate()
    readiness = _readiness_row()
    factors = _registry_factors()

    normalized_before = normalized.copy(deep=True)
    candidates_before = candidates.copy(deep=True)
    readiness_before = readiness.copy(deep=True)
    factors_before = factors.copy(deep=True)

    calculate_activity_emissions(
        normalized, candidates, readiness, factors
    )

    pd.testing.assert_frame_equal(normalized, normalized_before)
    pd.testing.assert_frame_equal(candidates, candidates_before)
    pd.testing.assert_frame_equal(readiness, readiness_before)
    pd.testing.assert_frame_equal(factors, factors_before)


def test_repeated_calculation_produces_identical_output(tmp_path: Path) -> None:
    first = _baseline_pipeline(tmp_path / "a")
    second = _baseline_pipeline(tmp_path / "b")
    pd.testing.assert_frame_equal(first, second)


def test_output_contains_no_ghg_scope(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    assert "ghg_scope" not in OUTPUT_COLUMNS
    electricity = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    if "ghg_scope" in result.columns:
        assert pd.isna(electricity["ghg_scope"])
    steel = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert steel["ghg_scope"] == "scope_3"


def test_output_contains_no_scope3_category(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    assert "scope3_category" not in OUTPUT_COLUMNS
    electricity = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    if "scope3_category" in result.columns:
        assert pd.isna(electricity["scope3_category"])
    steel = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert steel["scope_3_category"] == "category_1"


def test_output_contains_no_cbam_data_role(tmp_path: Path) -> None:
    result = _baseline_pipeline(tmp_path)
    assert "cbam_data_role" not in result.columns


def test_existing_raw_and_reference_files_remain_unchanged(tmp_path: Path) -> None:
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
    _baseline_pipeline(tmp_path)
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
