"""Pure tests for Phase 9A structured company-data intake."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger import intake as intake_mod
from carbon_ledger.intake import (
    MAX_UPLOAD_BYTES,
    ColumnMapping,
    IntakeError,
    IntakeMetadata,
    blank_template_csv_bytes,
    build_and_validate_intake,
    compute_bytes_sha256,
    default_value_maps,
    list_xlsx_sheet_names,
    parse_uploaded_table,
    sanitize_filename,
    source_document_id_from_hash,
    suggest_activity_type,
    suggest_column_mapping,
    suggest_unit,
    validate_upload_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")


def _metadata(**overrides: object) -> IntakeMetadata:
    base = IntakeMetadata(
        source_name="demo.csv",
        site_id="site_main",
        document_date=date(2024, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="test_intake",
        ingested_at=FIXED_INGESTED_AT,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _valid_csv() -> bytes:
    return _csv_bytes(
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "grid_electricity,50000,kWh,2024-01-01,2024-01-31\n"
        "natural_gas,8000,m3,2024-01-01,2024-01-31\n"
        "diesel,1200,L,2024-01-01,2024-01-31\n"
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
    # Force complete mappings for known aliases.
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
    )
    for key, value in overrides.items():
        setattr(mapping, key, value)
    return mapping


def _xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def test_csv_bytes_parse_successfully() -> None:
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    assert len(table.frame) == 3
    assert "activity_type" in table.columns


def test_utf8_bom_csv_parses() -> None:
    bom = b"\xef\xbb\xbf" + _valid_csv()
    table = parse_uploaded_table(file_name="bom.csv", data=bom)
    assert len(table.frame) == 3


def test_invalid_csv_encoding_rejected() -> None:
    bad = "活動,數量\n電力,1".encode("big5")
    with pytest.raises(IntakeError) as exc:
        parse_uploaded_table(file_name="bad.csv", data=bad)
    assert exc.value.code == "INVALID_ENCODING"


def test_xlsx_parses_successfully() -> None:
    data = _xlsx_bytes(
        {
            "Sheet1": pd.DataFrame(
                {
                    "activity_type": ["diesel"],
                    "activity_value": [10],
                    "unit": ["L"],
                    "activity_start_date": ["2024-01-01"],
                    "activity_end_date": ["2024-01-31"],
                }
            )
        }
    )
    table = parse_uploaded_table(file_name="demo.xlsx", data=data)
    assert len(table.frame) == 1
    assert table.sheet_name == "Sheet1"


def test_multiple_xlsx_sheets_discoverable() -> None:
    data = _xlsx_bytes(
        {
            "Alpha": pd.DataFrame({"a": [1]}),
            "Beta": pd.DataFrame({"b": [2]}),
        }
    )
    assert list_xlsx_sheet_names(data) == ["Alpha", "Beta"]


def test_selected_xlsx_sheet_is_parsed() -> None:
    data = _xlsx_bytes(
        {
            "Alpha": pd.DataFrame({"activity_type": ["diesel"], "x": [1]}),
            "Beta": pd.DataFrame({"activity_type": ["natural_gas"], "x": [2]}),
        }
    )
    table = parse_uploaded_table(
        file_name="multi.xlsx",
        data=data,
        sheet_name="Beta",
    )
    assert table.sheet_name == "Beta"
    assert table.frame.iloc[0]["activity_type"] == "natural_gas"


def test_unsupported_extension_rejected() -> None:
    with pytest.raises(IntakeError) as exc:
        validate_upload_bytes("scan.pdf", b"%PDF")
    assert exc.value.code == "UNSUPPORTED_FILE_TYPE"


def test_file_larger_than_10mb_rejected() -> None:
    with pytest.raises(IntakeError) as exc:
        validate_upload_bytes("big.csv", b"a" * (MAX_UPLOAD_BYTES + 1))
    assert exc.value.code == "FILE_TOO_LARGE"


def test_sanitized_filename_removes_path_components() -> None:
    assert sanitize_filename(r"C:\temp\..\secret\demo.csv") == "demo.csv"
    assert sanitize_filename("/var/tmp/upload.xlsx") == "upload.xlsx"


def test_sha256_is_deterministic() -> None:
    data = _valid_csv()
    assert compute_bytes_sha256(data) == compute_bytes_sha256(data)


def test_identical_bytes_produce_identical_source_document_id() -> None:
    data = _valid_csv()
    digest = compute_bytes_sha256(data)
    assert source_document_id_from_hash(digest) == source_document_id_from_hash(
        digest
    )


def test_identical_input_produces_identical_activity_record_ids() -> None:
    data = _valid_csv()
    table = parse_uploaded_table(file_name="demo.csv", data=data)
    mapping = _mapping_for(table)
    first = build_and_validate_intake(table, mapping, _metadata())
    second = build_and_validate_intake(table, mapping, _metadata())
    assert list(first.accepted_activities["record_id"]) == list(
        second.accepted_activities["record_id"]
    )


def test_column_alias_suggests_activity_type() -> None:
    assert suggest_column_mapping(["activity_type", "x"])["activity_type"] == (
        "activity_type"
    )


def test_chinese_alias_suggests_activity_type() -> None:
    assert suggest_column_mapping(["活動類型", "數量"])["activity_type"] == "活動類型"


def test_amount_alias_suggestion_works() -> None:
    assert suggest_column_mapping(["用量", "單位"])["activity_value"] == "用量"


def test_unit_alias_suggestion_works() -> None:
    assert suggest_column_mapping(["單位"])["unit"] == "單位"


def test_date_alias_suggestion_works() -> None:
    mapping = suggest_column_mapping(["開始日期", "結束日期"])
    assert mapping["activity_start_date"] == "開始日期"
    assert mapping["activity_end_date"] == "結束日期"


def test_unmatched_column_remains_unselected() -> None:
    assert suggest_column_mapping(["foo", "bar"])["activity_type"] == ""


def test_electricity_alias_maps_to_grid_electricity() -> None:
    assert suggest_activity_type("電力") == "grid_electricity"
    assert suggest_activity_type("electricity") == "grid_electricity"


def test_natural_gas_alias_suggestion_works() -> None:
    assert suggest_activity_type("天然氣") == "natural_gas"


def test_diesel_alias_suggestion_works() -> None:
    assert suggest_activity_type("柴油") == "diesel"


def test_steel_alias_suggestion_works() -> None:
    assert suggest_activity_type("採購鋼材") == "purchased_steel"
    assert suggest_activity_type("盤元") == "purchased_steel"


def test_production_alias_suggestion_works() -> None:
    assert suggest_activity_type("生產數量") == "finished_goods_output"


def test_unit_degree_suggests_kwh() -> None:
    assert suggest_unit("度") == "kWh"


def test_m3_symbol_suggests_m3() -> None:
    assert suggest_unit("m³") == "m3"


def test_liter_chinese_suggests_l() -> None:
    assert suggest_unit("公升") == "L"


def test_tonne_chinese_suggests_t() -> None:
    assert suggest_unit("噸") == "t"


def test_unmatched_activity_value_requires_mapping() -> None:
    assert suggest_activity_type("神秘燃料") == ""


def test_unmatched_unit_requires_mapping() -> None:
    assert suggest_unit("gallon") == ""


def _result_with_value(value: object) -> intake_mod.IntakeValidationResult:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        f"diesel,{value},L,2024-01-01,2024-01-31\n"
    )
    table = parse_uploaded_table(file_name="demo.csv", data=_csv_bytes(csv))
    return build_and_validate_intake(table, _mapping_for(table), _metadata())


def test_invalid_activity_amount_rejected() -> None:
    result = _result_with_value("abc")
    assert result.rejected_count == 1
    assert result.rejected_rows.iloc[0]["issue_code"] == "INVALID_ACTIVITY_VALUE"


def test_zero_activity_amount_rejected() -> None:
    result = _result_with_value(0)
    assert result.rejected_count == 1


def test_negative_activity_amount_rejected() -> None:
    result = _result_with_value(-5)
    assert result.rejected_count == 1


def test_invalid_date_rejected() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "diesel,10,L,not-a-date,2024-01-31\n"
    )
    table = parse_uploaded_table(file_name="demo.csv", data=_csv_bytes(csv))
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.rejected_count == 1
    assert result.rejected_rows.iloc[0]["issue_code"] == "INVALID_DATE"


def test_end_date_before_start_date_rejected() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "diesel,10,L,2024-02-01,2024-01-01\n"
    )
    table = parse_uploaded_table(file_name="demo.csv", data=_csv_bytes(csv))
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.rejected_count == 1
    assert result.rejected_rows.iloc[0]["issue_code"] == "INVALID_DATE"


def test_electricity_with_l_rejected_as_unit_mismatch() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "grid_electricity,10,L,2024-01-01,2024-01-31\n"
    )
    table = parse_uploaded_table(file_name="demo.csv", data=_csv_bytes(csv))
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.rejected_count == 1
    assert result.rejected_rows.iloc[0]["issue_code"] == "ACTIVITY_UNIT_MISMATCH"


def test_gas_with_kwh_rejected_as_unit_mismatch() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "natural_gas,10,kWh,2024-01-01,2024-01-31\n"
    )
    table = parse_uploaded_table(file_name="demo.csv", data=_csv_bytes(csv))
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.rejected_count == 1
    assert result.rejected_rows.iloc[0]["issue_code"] == "ACTIVITY_UNIT_MISMATCH"


def test_diesel_with_l_accepted_structurally() -> None:
    result = _result_with_value(12)
    assert result.accepted_count == 1
    assert result.rejected_count == 0


def test_purchased_steel_with_t_accepted_structurally() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "purchased_steel,15,t,2024-01-01,2024-01-31\n"
    )
    table = parse_uploaded_table(file_name="demo.csv", data=_csv_bytes(csv))
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.accepted_count == 1


def test_source_document_uses_company_provided() -> None:
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.source_documents.iloc[0]["data_origin"] == "company_provided"


def test_source_document_is_synthetic_false() -> None:
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert bool(result.source_documents.iloc[0]["is_synthetic"]) is False


def test_source_document_hash_matches_uploaded_bytes() -> None:
    data = _valid_csv()
    table = parse_uploaded_table(file_name="demo.csv", data=data)
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.source_documents.iloc[0]["sha256"] == compute_bytes_sha256(data)


def test_document_type_other_includes_required_notes() -> None:
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    row = result.source_documents.iloc[0]
    assert row["document_type"] == "other"
    assert str(row["notes"]).strip()


def test_row_locator_is_deterministic() -> None:
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.accepted_activities.iloc[0]["source_locator"] == "row:2"


def test_unknown_conservative_fields_trigger_needs_review() -> None:
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert (
        result.accepted_activities["human_review_status"] == "needs_review"
    ).all()


def test_valid_rows_remain_accepted_when_another_row_fails() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "diesel,10,L,2024-01-01,2024-01-31\n"
        "diesel,-1,L,2024-01-01,2024-01-31\n"
    )
    table = parse_uploaded_table(file_name="demo.csv", data=_csv_bytes(csv))
    result = build_and_validate_intake(table, _mapping_for(table), _metadata())
    assert result.accepted_count == 1
    assert result.rejected_count == 1


def test_rejected_rows_contain_source_row_issue_and_reason() -> None:
    result = _result_with_value("abc")
    row = result.rejected_rows.iloc[0]
    assert "source_row" in row
    assert row["issue_code"]
    assert row["issue_message"]


def test_intake_does_not_mutate_uploaded_dataframe() -> None:
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    before = table.frame.copy()
    build_and_validate_intake(table, _mapping_for(table), _metadata())
    pd.testing.assert_frame_equal(before, table.frame)


def test_intake_does_not_write_files_to_repository(tmp_path: Path) -> None:
    before = {path for path in REPO_ROOT.rglob("*") if path.is_file()}
    table = parse_uploaded_table(file_name="demo.csv", data=_valid_csv())
    build_and_validate_intake(table, _mapping_for(table), _metadata())
    after = {path for path in REPO_ROOT.rglob("*") if path.is_file()}
    assert before == after
    assert blank_template_csv_bytes().startswith(b"activity_type,")
