"""Stage 4.2F-C2 — deterministic flexible column inference."""

from __future__ import annotations

import pandas as pd

from carbon_ledger.intake import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    is_reference_only_column,
    suggest_column_mapping_with_confidence,
)


def test_exact_unambiguous_alias_remains_high() -> None:
    detailed = suggest_column_mapping_with_confidence(
        ["活動類型", "使用量", "單位", "開始日期", "結束日期", "廠場"]
    )
    assert detailed["activity_type"].confidence == CONFIDENCE_HIGH
    assert detailed["activity_value"].source_column == "使用量"
    assert detailed["activity_value"].confidence == CONFIDENCE_HIGH
    assert detailed["unit"].confidence == CONFIDENCE_HIGH


def test_parenthetical_unit_header_is_still_high() -> None:
    detailed = suggest_column_mapping_with_confidence(["使用量（kWh）", "單位"])
    assert detailed["activity_value"].source_column == "使用量（kWh）"
    assert detailed["activity_value"].confidence == CONFIDENCE_HIGH


def test_medium_alias_is_not_auto_high() -> None:
    detailed = suggest_column_mapping_with_confidence(["活動類型", "用量", "單位"])
    assert detailed["activity_value"].source_column == "用量"
    assert detailed["activity_value"].confidence == CONFIDENCE_MEDIUM


def test_competing_high_aliases_drop_to_medium() -> None:
    detailed = suggest_column_mapping_with_confidence(["使用量", "耗用量", "單位"])
    assert detailed["activity_value"].confidence == CONFIDENCE_MEDIUM
    assert detailed["activity_value"].source_column in {"使用量", "耗用量"}


def test_wrapped_high_alias_stays_medium() -> None:
    detailed = suggest_column_mapping_with_confidence(["使用量欄位", "單位"])
    assert detailed["activity_value"].source_column == "使用量欄位"
    assert detailed["activity_value"].confidence == CONFIDENCE_MEDIUM


def test_value_assisted_unique_numeric_column_is_medium() -> None:
    frame = pd.DataFrame(
        {
            "說明": ["外購電力", "天然氣"],
            "數字": [1200, 8000],
            "度量": ["kWh", "m3"],
        }
    )
    detailed = suggest_column_mapping_with_confidence(
        list(frame.columns), frame=frame
    )
    assert detailed["activity_value"].source_column == "數字"
    assert detailed["activity_value"].confidence == CONFIDENCE_MEDIUM
    assert detailed["unit"].source_column == "度量"
    assert detailed["unit"].confidence == CONFIDENCE_MEDIUM
    assert detailed["activity_type"].source_column == "說明"
    assert detailed["activity_type"].confidence == CONFIDENCE_MEDIUM


def test_competing_numeric_columns_stay_low() -> None:
    frame = pd.DataFrame({"甲": [10, 20], "乙": [30, 40], "單位": ["kWh", "kWh"]})
    detailed = suggest_column_mapping_with_confidence(
        list(frame.columns), frame=frame
    )
    assert detailed["activity_value"].confidence == CONFIDENCE_LOW
    assert detailed["activity_value"].source_column == ""
    assert detailed["unit"].source_column == "單位"


def test_emissions_total_never_becomes_activity_value() -> None:
    assert is_reference_only_column("排放量 (kgCO2e)")
    frame = pd.DataFrame(
        {
            "能源別": ["外購電力"],
            "使用量": [100],
            "單位": ["kWh"],
            "排放量 (kgCO2e)": [49.4],
        }
    )
    detailed = suggest_column_mapping_with_confidence(
        list(frame.columns), frame=frame
    )
    assert detailed["activity_value"].source_column == "使用量"
    assert detailed["activity_value"].source_column != "排放量 (kgCO2e)"


def test_facility_names_are_suggestion_context_only() -> None:
    frame = pd.DataFrame(
        {
            "活動類型": ["外購電力"],
            "使用量": [10],
            "單位": ["kWh"],
            "營運點": ["高雄廠"],
        }
    )
    detailed = suggest_column_mapping_with_confidence(
        list(frame.columns),
        frame=frame,
        facility_names=("高雄廠",),
    )
    assert detailed["site_id"].source_column == "營運點"
    assert detailed["site_id"].confidence == CONFIDENCE_MEDIUM
