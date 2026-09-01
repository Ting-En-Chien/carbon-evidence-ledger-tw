"""Intake + pipeline vertical for actual refrigerant refill."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.intake import (
    ColumnMapping,
    IntakeMetadata,
    blank_template_csv_bytes,
    blank_template_xlsx_bytes,
    build_and_validate_intake,
    default_value_maps,
    normalize_refrigerant_org_boundary,
    normalize_refrigerant_ownership,
    parse_uploaded_table,
    suggest_activity_type,
    suggest_column_mapping,
    suggest_unit,
)
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.ui.view_models import calculated_emissions_by_product_scope

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2026-02-01T00:00:00Z")

_HEADER = (
    "activity_type,activity_value,unit,activity_start_date,activity_end_date,"
    "refrigerant_code,refill_confirmed,ownership_control,"
    "organizational_boundary_status"
)
_HEADER_WITHOUT_BOUNDARY = (
    "activity_type,activity_value,unit,activity_start_date,activity_end_date,"
    "refrigerant_code,refill_confirmed"
)
_ELECTRICITY_ROW = "外購電力,50000,kWh,2025-01-01,2025-01-31,,,,"
_R134A_CONFIRMED = (
    "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-134a,是,公司所有,納入"
)
_R134A_CONTROLLED = (
    "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-134a,是,營運控制,納入"
)
_R134A_OUTSIDE = (
    "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-134a,是,公司所有,不納入"
)
_R134A_THIRD_PARTY = (
    "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-134a,是,第三方,納入"
)
_R134A_UNRECOGNIZED = (
    "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-134a,是,租賃,大概在邊界"
)
_R410A_CONFIRMED = (
    "冷媒實際補充,2,kg,2026-01-01,2026-12-31,R-410A,是,公司所有,納入"
)
_R134A_UNCONFIRMED = (
    "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-134a,否,公司所有,納入"
)
_UNKNOWN_REFRIGERANT = (
    "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-999,是,公司所有,納入"
)
_CROSS_YEAR = (
    "冷媒實際補充,15,kg,2025-01-01,2026-12-31,R-134a,是,公司所有,納入"
)
_R134A_NO_BOUNDARY_COLUMNS = "冷媒實際補充,15,kg,2026-01-01,2026-12-31,R-134a,是"


def _metadata(name: str = "refrigerant.csv") -> IntakeMetadata:
    return IntakeMetadata(
        source_name=name,
        site_id="高雄廠",
        document_date=date(2026, 12, 31),
        data_quality_tier="unknown",
        intake_run_id="refrigerant_intake",
        ingested_at=FIXED_INGESTED_AT,
    )


def _mapping_for(table, **overrides: object) -> ColumnMapping:
    suggestions = suggest_column_mapping(list(table.columns))
    activity_map, unit_map = default_value_maps(
        table,
        ColumnMapping(
            activity_type_column=suggestions["activity_type"],
            activity_value_column=suggestions["activity_value"],
            unit_column=suggestions["unit"],
        ),
    )
    activity_map = {
        key: value or suggest_activity_type(key) for key, value in activity_map.items()
    }
    unit_map = {key: value or suggest_unit(key) for key, value in unit_map.items()}
    mapping = ColumnMapping(
        activity_type_column=suggestions["activity_type"],
        activity_value_column=suggestions["activity_value"],
        unit_column=suggestions["unit"],
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
        electricity_context="enterprise",
    )
    for key, value in overrides.items():
        setattr(mapping, key, value)
    return mapping


def _intake(csv_text: str, **mapping_overrides: object):
    table = parse_uploaded_table(
        file_name="refrigerant.csv",
        data=csv_text.encode("utf-8"),
    )
    mapping = _mapping_for(table, **mapping_overrides)
    return build_and_validate_intake(table, mapping, _metadata())


def _run(csv_text: str, **mapping_overrides: object):
    intake = _intake(csv_text, **mapping_overrides)
    result = run_uploaded_pipeline(
        REPO_ROOT,
        run_id="refrigerant_upload",
        ingested_at=FIXED_INGESTED_AT,
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
    )
    return result, intake


def _csv(*rows: str, header: str = _HEADER) -> str:
    return "\n".join((header, *rows, ""))


def _scope1_total(result) -> float:
    return float(calculated_emissions_by_product_scope(result).get("scope_1") or 0.0)


def _refrigerant_activity(intake):
    accepted = intake.accepted_activities
    return accepted[accepted["activity_type"] == "refrigerant_refill"].iloc[0]


def _ghg_for(result, record_id):
    ghg = result.ghg_evaluations
    return ghg[ghg["record_id"] == record_id].iloc[0]


def _calc_for_activity(result, activity_type: str) -> pd.DataFrame:
    activities = result.activity_records_accepted
    calcs = result.calculation_results
    matched = activities[activities["activity_type"].astype(str) == activity_type]
    return calcs[calcs["record_id"].isin(matched["record_id"])]


def test_download_template_includes_refrigerant_columns() -> None:
    csv_header = blank_template_csv_bytes().decode("utf-8").splitlines()[0]
    assert "refrigerant_code" in csv_header.split(",")
    assert "refill_confirmed" in csv_header.split(",")
    assert "ownership_control" in csv_header.split(",")
    assert "organizational_boundary_status" in csv_header.split(",")

    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(blank_template_xlsx_bytes()))
    fill_headers = [cell.value for cell in workbook["資料填寫"][1]]
    assert "冷媒種類" in fill_headers
    assert "補充量已確認" in fill_headers
    assert "設備控制方式" in fill_headers
    assert "組織盤查邊界" in fill_headers
    guide_system_names = [
        cell.value for cell in workbook["欄位說明"]["D"] if cell.value
    ]
    assert "refrigerant_code" in guide_system_names
    assert "refill_confirmed" in guide_system_names
    assert "ownership_control" in guide_system_names
    assert "organizational_boundary_status" in guide_system_names


def test_confirmed_r134a_calculates_scope_1() -> None:
    result, intake = _run(_csv(_ELECTRICITY_ROW, _R134A_CONFIRMED))
    accepted = intake.accepted_activities
    row = accepted[accepted["activity_type"] == "refrigerant_refill"].iloc[0]
    calcs = result.calculation_results
    calc = calcs[calcs["record_id"] == row["record_id"]].iloc[0]
    ghg = result.ghg_evaluations
    mapped = ghg[ghg["record_id"] == row["record_id"]].iloc[0]

    assert str(row["ownership_control"]) == "owned"
    assert str(row["organizational_boundary_status"]) == "inside"
    assert str(calc["calculation_status"]) == "calculated"
    assert float(calc["gwp_value"]) == 1300
    assert float(calc["calculated_kgco2e"]) == 19500
    assert float(calc["calculated_tco2e"]) == 19.5
    assert str(mapped["ghg_scope"]) == "scope_1"
    assert str(mapped["mapping_code"]) == "scope1_fugitive_refrigerant"
    totals = calculated_emissions_by_product_scope(result)
    assert totals["scope_1"] == pytest.approx(19.5)


def test_confirmed_r410a_uses_weighted_gwp() -> None:
    result, intake = _run(_csv(_R410A_CONFIRMED))
    row = intake.accepted_activities.iloc[0]
    calc = result.calculation_results[
        result.calculation_results["record_id"] == row["record_id"]
    ].iloc[0]
    assert float(calc["gwp_value"]) == 1923.5
    assert float(calc["calculated_tco2e"]) == pytest.approx(3.847)
    assert str(calc["gwp_id"]) == "gwp_ar5_r410a_weighted"
    assert str(calc["factor_id"]) == "gwp_ar5_r410a_weighted"


def test_unconfirmed_refill_is_not_calculated() -> None:
    result, intake = _run(_csv(_R134A_UNCONFIRMED))
    calc = result.calculation_results.iloc[0]
    assert str(calc["calculation_status"]) != "calculated"
    assert str(calc["calculation_status"]) == "blocked_missing_refill_quantity"
    assert pd.isna(calc["calculated_tco2e"]) or calc["calculated_tco2e"] in {
        None,
        "",
    }


def test_unknown_refrigerant_is_not_calculated() -> None:
    result, intake = _run(_csv(_UNKNOWN_REFRIGERANT))
    accepted = intake.accepted_activities.iloc[0]
    assert str(accepted["refrigerant_code"]) == "R-999"
    calc = result.calculation_results.iloc[0]
    assert str(calc["calculation_status"]) == "blocked_unknown_refrigerant"
    assert pd.isna(calc["calculated_tco2e"]) or calc["calculated_tco2e"] in {
        None,
        "",
    }


def test_cross_year_dates_do_not_select_a_reporting_year() -> None:
    result, intake = _run(_csv(_CROSS_YEAR))
    calc = result.calculation_results.iloc[0]
    assert str(calc["calculation_status"]) == "blocked_invalid_reporting_period"
    reporting_year = calc.get("reporting_year")
    assert reporting_year in {None, ""} or pd.isna(reporting_year)


def test_one_calculation_row_per_refrigerant_record() -> None:
    result, intake = _run(
        _csv(
            _ELECTRICITY_ROW,
            _R134A_CONFIRMED,
            _R410A_CONFIRMED,
            _R134A_UNCONFIRMED,
            _UNKNOWN_REFRIGERANT,
        )
    )
    refrigerant_ids = intake.accepted_activities.loc[
        intake.accepted_activities["activity_type"] == "refrigerant_refill",
        "record_id",
    ]
    calcs = result.calculation_results
    for record_id in refrigerant_ids:
        matches = calcs[calcs["record_id"].astype(str) == str(record_id)]
        assert len(matches) == 1
    counts = calcs.groupby(calcs["record_id"].astype(str)).size()
    assert counts.max() == 1


def test_existing_electricity_upload_is_unchanged() -> None:
    electricity_only = _csv(_ELECTRICITY_ROW)
    mixed = _csv(_ELECTRICITY_ROW, _R134A_CONFIRMED)
    only_result, _ = _run(electricity_only)
    mixed_result, _ = _run(mixed)
    only_calc = _calc_for_activity(only_result, "grid_electricity").iloc[0]
    mixed_calc = _calc_for_activity(mixed_result, "grid_electricity").iloc[0]
    assert str(only_calc["calculation_status"]) == "calculated"
    assert str(mixed_calc["calculation_status"]) == str(only_calc["calculation_status"])
    assert float(mixed_calc["calculated_tco2e"]) == pytest.approx(
        float(only_calc["calculated_tco2e"])
    )
    assert str(mixed_calc["factor_id"]) == str(only_calc["factor_id"])
    assert str(mixed_calc["formula_id"]) == str(only_calc["formula_id"])


def test_refrigerant_value_aliases_are_deterministic() -> None:
    assert normalize_refrigerant_ownership("公司所有") == "owned"
    assert normalize_refrigerant_ownership("自有") == "owned"
    assert normalize_refrigerant_ownership("OWNED") == "owned"
    assert normalize_refrigerant_ownership("營運控制") == "controlled"
    assert normalize_refrigerant_ownership("控制") == "controlled"
    assert normalize_refrigerant_ownership("controlled") == "controlled"
    assert normalize_refrigerant_ownership("第三方") == "third_party"
    assert normalize_refrigerant_ownership("third_party") == "third_party"
    assert normalize_refrigerant_ownership("") == "unknown"
    assert normalize_refrigerant_ownership("不確定") == "unknown"
    assert normalize_refrigerant_ownership("租賃") == "unknown"
    assert normalize_refrigerant_org_boundary("納入") == "inside"
    assert normalize_refrigerant_org_boundary("邊界內") == "inside"
    assert normalize_refrigerant_org_boundary("inside") == "inside"
    assert normalize_refrigerant_org_boundary("不納入") == "outside"
    assert normalize_refrigerant_org_boundary("邊界外") == "outside"
    assert normalize_refrigerant_org_boundary("outside") == "outside"
    assert normalize_refrigerant_org_boundary("") == "unknown"
    assert normalize_refrigerant_org_boundary("不確定") == "unknown"
    assert normalize_refrigerant_org_boundary("大概在邊界") == "unknown"


def test_controlled_inside_maps_to_scope_1() -> None:
    result, intake = _run(_csv(_R134A_CONTROLLED))
    row = _refrigerant_activity(intake)
    mapped = _ghg_for(result, row["record_id"])
    assert str(row["ownership_control"]) == "controlled"
    assert str(row["organizational_boundary_status"]) == "inside"
    assert str(mapped["mapping_status"]) == "mapped"
    assert str(mapped["ghg_scope"]) == "scope_1"
    assert _scope1_total(result) == pytest.approx(19.5)


def test_owned_outside_is_excluded_from_scope_1() -> None:
    result, intake = _run(_csv(_R134A_OUTSIDE))
    row = _refrigerant_activity(intake)
    mapped = _ghg_for(result, row["record_id"])
    calc = result.calculation_results.iloc[0]
    assert str(row["organizational_boundary_status"]) == "outside"
    assert str(mapped["mapping_status"]) == "outside_boundary"
    assert str(mapped["ghg_scope"]) == "not_applicable"
    assert str(calc["calculation_status"]) == "calculated"
    assert _scope1_total(result) == pytest.approx(0.0)


def test_third_party_inside_needs_review_and_is_not_scope_1() -> None:
    result, intake = _run(_csv(_R134A_THIRD_PARTY))
    row = _refrigerant_activity(intake)
    mapped = _ghg_for(result, row["record_id"])
    calc = result.calculation_results.iloc[0]
    assert str(row["ownership_control"]) == "third_party"
    assert str(mapped["mapping_status"]) == "needs_review"
    assert str(mapped["ghg_scope"]) == "unknown"
    assert str(calc["calculation_status"]) == "calculated"
    assert _scope1_total(result) == pytest.approx(0.0)


def test_missing_boundary_columns_are_unknown_needs_review() -> None:
    result, intake = _run(
        _csv(_R134A_NO_BOUNDARY_COLUMNS, header=_HEADER_WITHOUT_BOUNDARY)
    )
    row = _refrigerant_activity(intake)
    mapped = _ghg_for(result, row["record_id"])
    assert str(row["ownership_control"]) == "unknown"
    assert str(row["organizational_boundary_status"]) == "unknown"
    assert str(mapped["mapping_status"]) == "needs_review"
    assert str(mapped["ghg_scope"]) == "unknown"
    assert _scope1_total(result) == pytest.approx(0.0)


def test_unrecognized_boundary_values_are_unknown_needs_review() -> None:
    result, intake = _run(_csv(_R134A_UNRECOGNIZED))
    row = _refrigerant_activity(intake)
    mapped = _ghg_for(result, row["record_id"])
    assert str(row["ownership_control"]) == "unknown"
    assert str(row["organizational_boundary_status"]) == "unknown"
    assert str(mapped["mapping_status"]) == "needs_review"
    assert _scope1_total(result) == pytest.approx(0.0)


def test_scope_1_total_excludes_outside_third_party_and_unknown() -> None:
    result, _ = _run(
        _csv(
            _R134A_CONFIRMED,
            _R134A_OUTSIDE,
            _R134A_THIRD_PARTY,
            _R134A_UNRECOGNIZED,
        )
    )
    assert _scope1_total(result) == pytest.approx(19.5)
