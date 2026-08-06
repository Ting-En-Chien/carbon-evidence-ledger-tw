"""Tests for Phase 5A versioned emission-factor registry."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pandas as pd

from carbon_ledger.factors import validate_factor_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
RAW_DIR = REPO_ROOT / "data" / "raw"


def _copy_reference_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "reference"
    shutil.copytree(REFERENCE_DIR, destination)
    return destination


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_registry_loads_expected_four_tables() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    assert not result.emission_factors.empty
    assert not result.gwp_values.empty
    assert not result.regulatory_references.empty
    assert not result.calculation_dependencies.empty
    assert result.issues.empty


def test_seven_emission_factor_rows_exist() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    assert len(result.emission_factors) == 7


def test_three_gwp_rows_exist() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    assert len(result.gwp_values) == 3


def test_two_dependency_rows_exist() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    assert len(result.calculation_dependencies) == 2


def test_electricity_factor_is_ready_0_474() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"] == "ef_tw_grid_electricity_2024"
    ].iloc[0]
    assert float(row["factor_value"]) == 0.474
    assert row["numerator_unit"] == "kgCO2e"
    assert row["denominator_unit"] == "kWh"
    assert row["factor_status"] == "ready"
    assert row["valid_from"] == "2024-01-01"
    assert row["valid_to"] == "2024-12-31"


def test_natural_gas_co2_factor_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"]
        == "ef_tw_natural_gas_stationary_co2_2024"
    ].iloc[0]
    assert float(row["factor_value"]) == 56100.0
    assert row["numerator_unit"] == "kgCO2"
    assert row["denominator_unit"] == "TJ"


def test_natural_gas_ch4_factor_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"]
        == "ef_tw_natural_gas_stationary_ch4_2024"
    ].iloc[0]
    assert float(row["factor_value"]) == 1.0
    assert row["numerator_unit"] == "kgCH4"


def test_natural_gas_n2o_factor_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"]
        == "ef_tw_natural_gas_stationary_n2o_2024"
    ].iloc[0]
    assert float(row["factor_value"]) == 0.1
    assert row["numerator_unit"] == "kgN2O"


def test_diesel_co2_factor_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"] == "ef_tw_diesel_mobile_co2_2024"
    ].iloc[0]
    assert float(row["factor_value"]) == 74100.0
    assert row["numerator_unit"] == "kgCO2"
    assert row["denominator_unit"] == "TJ"


def test_diesel_ch4_factor_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"] == "ef_tw_diesel_mobile_ch4_2024"
    ].iloc[0]
    assert float(row["factor_value"]) == 3.9
    assert row["numerator_unit"] == "kgCH4"


def test_diesel_n2o_factor_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"] == "ef_tw_diesel_mobile_n2o_2024"
    ].iloc[0]
    assert float(row["factor_value"]) == 3.9
    assert row["numerator_unit"] == "kgN2O"


def test_gwp_values_are_expected() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    values = {
        row["gas"]: float(row["gwp_value"])
        for _, row in result.gwp_values.iterrows()
    }
    assert values == {"CO2": 1.0, "CH4": 28.0, "N2O": 265.0}


def test_every_factor_references_existing_official_source() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    reference_ids = set(result.regulatory_references["reference_id"])
    for source_id in result.emission_factors["source_reference_id"]:
        assert source_id in reference_ids
    for source_id in result.gwp_values["source_reference_id"]:
        assert source_id in reference_ids


def test_electricity_factor_requires_no_conversion() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    row = result.emission_factors.loc[
        result.emission_factors["factor_id"] == "ef_tw_grid_electricity_2024"
    ].iloc[0]
    assert row["required_conversion"] == "not_required"
    assert row["factor_status"] == "ready"


def test_natural_gas_factors_blocked_by_missing_heating_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    gas_rows = result.emission_factors.loc[
        result.emission_factors["activity_type"] == "natural_gas"
    ]
    assert len(gas_rows) == 3
    assert (
        gas_rows["factor_status"] == "registered_missing_conversion"
    ).all()
    assert (
        gas_rows["required_conversion"]
        == "verified_natural_gas_heating_value_m3_to_TJ"
    ).all()
    assert (gas_rows["valid_from"].astype(str).str.strip() == "").all()
    assert (gas_rows["valid_to"].astype(str).str.strip() == "").all()
    assert "natural_gas" in set(
        result.calculation_dependencies["activity_type"]
    )


def test_diesel_factors_blocked_by_missing_heating_value() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    diesel_rows = result.emission_factors.loc[
        result.emission_factors["activity_type"] == "diesel"
    ]
    assert len(diesel_rows) == 3
    assert (
        diesel_rows["factor_status"] == "registered_missing_conversion"
    ).all()
    assert (
        diesel_rows["required_conversion"]
        == "verified_diesel_heating_value_L_to_TJ"
    ).all()
    assert (diesel_rows["valid_from"].astype(str).str.strip() == "").all()
    assert (diesel_rows["valid_to"].astype(str).str.strip() == "").all()
    assert "diesel" in set(result.calculation_dependencies["activity_type"])


def test_duplicate_factor_id_is_reported(tmp_path: Path) -> None:
    reference = _copy_reference_tree(tmp_path)
    path = reference / "emission_factors.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[1, "factor_id"] = frame.loc[0, "factor_id"]
    frame.to_csv(path, index=False)

    result = validate_factor_registry(reference)
    codes = set(result.issues["issue_code"])
    assert "DUPLICATE_ID" in codes


def test_missing_reference_id_is_reported(tmp_path: Path) -> None:
    reference = _copy_reference_tree(tmp_path)
    path = reference / "emission_factors.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, "source_reference_id"] = "ref_does_not_exist"
    frame.to_csv(path, index=False)

    result = validate_factor_registry(reference)
    assert "MISSING_REFERENCE" in set(result.issues["issue_code"])


def test_negative_factor_value_is_reported(tmp_path: Path) -> None:
    reference = _copy_reference_tree(tmp_path)
    path = reference / "emission_factors.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, "factor_value"] = "-1"
    frame.to_csv(path, index=False)

    result = validate_factor_registry(reference)
    assert "NON_POSITIVE_VALUE" in set(result.issues["issue_code"])


def test_invalid_validity_dates_are_reported(tmp_path: Path) -> None:
    reference = _copy_reference_tree(tmp_path)
    path = reference / "emission_factors.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[0, "valid_from"] = "2024-12-31"
    frame.loc[0, "valid_to"] = "2024-01-01"
    frame.to_csv(path, index=False)

    result = validate_factor_registry(reference)
    assert "INVALID_VALIDITY_DATES" in set(result.issues["issue_code"])


def test_ready_factor_with_conversion_dependency_is_reported(
    tmp_path: Path,
) -> None:
    reference = _copy_reference_tree(tmp_path)
    path = reference / "emission_factors.csv"
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    electricity = frame["factor_id"] == "ef_tw_grid_electricity_2024"
    frame.loc[electricity, "required_conversion"] = (
        "verified_natural_gas_heating_value_m3_to_TJ"
    )
    frame.to_csv(path, index=False)

    result = validate_factor_registry(reference)
    assert "READY_REQUIRES_NOT_REQUIRED_CONVERSION" in set(
        result.issues["issue_code"]
    )


def test_missing_conversion_factor_without_dependency_is_reported(
    tmp_path: Path,
) -> None:
    reference = _copy_reference_tree(tmp_path)
    deps_path = reference / "calculation_dependencies.csv"
    frame = pd.read_csv(deps_path, dtype=str, keep_default_na=False)
    frame = frame.loc[frame["activity_type"] != "natural_gas"].copy()
    frame.to_csv(deps_path, index=False)

    result = validate_factor_registry(reference)
    assert "MISSING_CONVERSION_DEPENDENCY" in set(result.issues["issue_code"])


def test_registry_validation_does_not_calculate_emissions() -> None:
    result = validate_factor_registry(REFERENCE_DIR)
    forbidden = {
        "calculated_tco2e",
        "calculated_kgco2e",
        "ghg_scope",
        "emissions",
    }
    for table in (
        result.emission_factors,
        result.gwp_values,
        result.regulatory_references,
        result.calculation_dependencies,
        result.issues,
    ):
        assert forbidden.isdisjoint(set(table.columns))


def test_existing_raw_activity_files_remain_unchanged() -> None:
    before = {
        path.relative_to(RAW_DIR).as_posix(): _sha256(path)
        for path in RAW_DIR.rglob("*")
        if path.is_file()
    }
    validate_factor_registry(REFERENCE_DIR)
    after = {
        path.relative_to(RAW_DIR).as_posix(): _sha256(path)
        for path in RAW_DIR.rglob("*")
        if path.is_file()
    }
    assert after == before
