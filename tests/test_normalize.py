"""Tests for Phase 4 safe unit normalization."""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.ingest import ingest_evidence
from carbon_ledger.normalize import convert_unit, normalize_activity_records

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T12:00:00")
FIXED_RUN_ID = "test_run_phase4_001"


def _activity_frame(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "activity_type": "grid_electricity",
        "activity_value": 1.0,
        "unit": "MWh",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _copy_raw_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "raw"
    shutil.copytree(RAW_DIR, destination)
    return destination


def test_one_mwh_converts_to_1000_kwh() -> None:
    assert convert_unit(1.0, "MWh", "kWh") == 1000.0
    result = normalize_activity_records(
        _activity_frame(activity_value=1.0, unit="MWh")
    )
    assert result.iloc[0]["normalization_status"] == "normalized"
    assert result.iloc[0]["normalized_value"] == 1000.0
    assert result.iloc[0]["normalized_unit"] == "kWh"


def test_half_mwh_converts_to_500_kwh() -> None:
    assert convert_unit(0.5, "MWh", "kWh") == 500.0
    result = normalize_activity_records(
        _activity_frame(activity_value=0.5, unit="MWh")
    )
    assert result.iloc[0]["normalized_value"] == 500.0


def test_kwh_remains_unchanged() -> None:
    result = normalize_activity_records(
        _activity_frame(activity_value=50000.0, unit="kWh")
    )
    assert result.iloc[0]["normalization_status"] == "already_canonical"
    assert result.iloc[0]["normalized_value"] == 50000.0
    assert result.iloc[0]["normalized_unit"] == "kWh"


def test_1000_kg_converts_to_1_t() -> None:
    assert convert_unit(1000.0, "kg", "t") == 1.0
    result = normalize_activity_records(
        _activity_frame(
            activity_type="purchased_steel",
            activity_value=1000.0,
            unit="kg",
        )
    )
    assert result.iloc[0]["normalization_status"] == "normalized"
    assert result.iloc[0]["normalized_value"] == 1.0
    assert result.iloc[0]["normalized_unit"] == "t"


def test_2500_kg_converts_to_2_5_t() -> None:
    assert convert_unit(2500.0, "kg", "t") == 2.5
    result = normalize_activity_records(
        _activity_frame(
            activity_type="finished_goods_output",
            activity_value=2500.0,
            unit="kg",
        )
    )
    assert result.iloc[0]["normalized_value"] == 2.5


def test_t_remains_unchanged() -> None:
    result = normalize_activity_records(
        _activity_frame(
            activity_type="purchased_steel",
            activity_value=150.0,
            unit="t",
        )
    )
    assert result.iloc[0]["normalization_status"] == "already_canonical"
    assert result.iloc[0]["normalized_value"] == 150.0


def test_natural_gas_m3_remains_unchanged() -> None:
    result = normalize_activity_records(
        _activity_frame(
            activity_type="natural_gas",
            activity_value=8000.0,
            unit="m3",
        )
    )
    assert result.iloc[0]["normalization_status"] == "already_canonical"
    assert result.iloc[0]["normalized_unit"] == "m3"
    assert result.iloc[0]["normalized_value"] == 8000.0


def test_diesel_l_remains_unchanged() -> None:
    result = normalize_activity_records(
        _activity_frame(
            activity_type="diesel",
            activity_value=1200.0,
            unit="L",
        )
    )
    assert result.iloc[0]["normalization_status"] == "already_canonical"
    assert result.iloc[0]["normalized_unit"] == "L"


def test_unsupported_electricity_unit_kg_is_blocked() -> None:
    result = normalize_activity_records(
        _activity_frame(activity_value=10.0, unit="kg")
    )
    assert result.iloc[0]["normalization_status"] == "unsupported_conversion"
    assert pd.isna(result.iloc[0]["normalized_value"])
    assert pd.isna(result.iloc[0]["normalized_unit"])


def test_unsupported_natural_gas_conversion_is_blocked() -> None:
    result = normalize_activity_records(
        _activity_frame(
            activity_type="natural_gas",
            activity_value=8000.0,
            unit="GJ",
        )
    )
    assert result.iloc[0]["normalization_status"] == "unsupported_conversion"
    with pytest.raises(ValueError, match="Unsupported conversion"):
        convert_unit(8000.0, "m3", "GJ")


def test_unknown_activity_type_is_unsupported() -> None:
    result = normalize_activity_records(
        _activity_frame(
            activity_type="mystery_fuel",
            activity_value=10.0,
            unit="kWh",
        )
    )
    assert result.iloc[0]["normalization_status"] == "unsupported_activity_type"
    assert result.iloc[0]["activity_type"] == "mystery_fuel"
    assert pd.isna(result.iloc[0]["normalized_value"])


def test_missing_unit_produces_invalid_unit() -> None:
    result = normalize_activity_records(
        _activity_frame(unit=None)
    )
    assert result.iloc[0]["normalization_status"] == "invalid_unit"


def test_blank_unit_produces_invalid_unit() -> None:
    result = normalize_activity_records(_activity_frame(unit="  "))
    assert result.iloc[0]["normalization_status"] == "invalid_unit"


def test_zero_value_produces_invalid_value() -> None:
    result = normalize_activity_records(_activity_frame(activity_value=0.0))
    assert result.iloc[0]["normalization_status"] == "invalid_value"


def test_negative_value_produces_invalid_value() -> None:
    result = normalize_activity_records(_activity_frame(activity_value=-5.0))
    assert result.iloc[0]["normalization_status"] == "invalid_value"


def test_nan_produces_invalid_value() -> None:
    result = normalize_activity_records(
        _activity_frame(activity_value=float("nan"))
    )
    assert result.iloc[0]["normalization_status"] == "invalid_value"


def test_infinity_produces_invalid_value() -> None:
    result = normalize_activity_records(
        _activity_frame(activity_value=float("inf"))
    )
    assert result.iloc[0]["normalization_status"] == "invalid_value"
    assert not math.isfinite(float("inf"))


def test_string_numeric_value_produces_invalid_value() -> None:
    result = normalize_activity_records(
        _activity_frame(activity_value="50000")
    )
    assert result.iloc[0]["normalization_status"] == "invalid_value"


def test_input_dataframe_is_not_mutated() -> None:
    frame = _activity_frame(activity_value=1.0, unit="MWh")
    original = frame.copy(deep=True)
    normalize_activity_records(frame)
    pd.testing.assert_frame_equal(frame, original)


def test_output_has_one_row_per_input_row() -> None:
    frame = pd.DataFrame(
        [
            {
                "record_id": "rec_a",
                "activity_type": "grid_electricity",
                "activity_value": 1.0,
                "unit": "MWh",
            },
            {
                "record_id": "rec_b",
                "activity_type": "diesel",
                "activity_value": -1.0,
                "unit": "L",
            },
            {
                "record_id": "rec_c",
                "activity_type": "natural_gas",
                "activity_value": 10.0,
                "unit": "GJ",
            },
        ]
    )
    result = normalize_activity_records(frame)
    assert len(result) == 3


def test_output_preserves_input_order() -> None:
    frame = pd.DataFrame(
        [
            {
                "record_id": "rec_z",
                "activity_type": "diesel",
                "activity_value": 1.0,
                "unit": "L",
            },
            {
                "record_id": "rec_a",
                "activity_type": "grid_electricity",
                "activity_value": 1.0,
                "unit": "kWh",
            },
        ]
    )
    result = normalize_activity_records(frame)
    assert result["record_id"].tolist() == ["rec_z", "rec_a"]


def test_repeated_execution_produces_identical_output() -> None:
    frame = _activity_frame(activity_value=0.5, unit="MWh")
    first = normalize_activity_records(frame)
    second = normalize_activity_records(frame)
    pd.testing.assert_frame_equal(first, second)


def test_phase3_baseline_accepted_records_are_already_canonical(
    tmp_path: Path,
) -> None:
    raw = _copy_raw_tree(tmp_path)
    ingestion = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    accepted = ingestion.activity_records.accepted
    result = normalize_activity_records(accepted)

    assert len(result) == 5
    assert (result["normalization_status"] == "already_canonical").all()
    assert result.loc[
        result["record_id"] == "rec_electricity_001", "normalized_value"
    ].iloc[0] == 50000.0
    assert result.loc[
        result["record_id"] == "rec_gas_001", "normalized_value"
    ].iloc[0] == 8000.0
    assert result.loc[
        result["record_id"] == "rec_diesel_001", "normalized_value"
    ].iloc[0] == 1200.0
    assert result.loc[
        result["record_id"] == "rec_steel_001", "normalized_value"
    ].iloc[0] == 150.0
    assert result.loc[
        result["record_id"] == "rec_output_001", "normalized_value"
    ].iloc[0] == 95.0


def test_normalized_output_does_not_contain_ghg_scope() -> None:
    result = normalize_activity_records(_activity_frame())
    assert "ghg_scope" not in result.columns


def test_normalized_output_does_not_contain_calculated_tco2e() -> None:
    result = normalize_activity_records(_activity_frame())
    assert "calculated_tco2e" not in result.columns
