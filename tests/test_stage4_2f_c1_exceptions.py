"""Stage 4.2F-C1 — confidence exceptions, true zero, draft vs committed."""

from __future__ import annotations

from datetime import date

import pandas as pd

from carbon_ledger.intake import (
    CONFIDENCE_HIGH,
    IntakeMetadata,
    build_and_validate_intake,
    parse_uploaded_table,
    suggest_column_mapping_with_confidence,
)
from carbon_ledger.intake_exceptions import (
    apply_exception,
    can_validate,
    high_match_count,
    hold_unknown_context_rows,
    initialize_committed,
    list_exceptions,
    mapping_from_committed,
    medium_is_uncommitted,
    required_unresolved_blocks,
    row_readiness_counts,
    summary_counts,
    unresolved_count,
)


def _table(csv: str, name: str = "ops.csv"):
    return parse_uploaded_table(file_name=name, data=csv.encode("utf-8"))


def _high_steel() -> str:
    return (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    )


def _medium_quantity() -> str:
    return (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    )


def _unmatched_required() -> str:
    return (
        "說明欄,數字欄,度量欄,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    )


def _mixed_energy() -> str:
    return (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,1000,kWh,2025-01-01,2025-01-31,高雄廠\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
        "柴油,1200,L,2025-01-01,2025-01-31,高雄廠\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
        "雜項能源,5,t,2025-01-01,2025-01-31,高雄廠\n"
    )


def test_true_zero_count_when_all_required_are_high() -> None:
    table = _table(_high_steel())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    counts = summary_counts(table, detailed, committed)
    assert counts["confirm"] == 0
    assert unresolved_count(table, detailed, committed) == 0
    assert list_exceptions(table, detailed, committed) == []
    assert can_validate(table, detailed, committed)


def test_high_auto_recognition_does_not_need_confirmation() -> None:
    table = _table(_high_steel())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    assert detailed["activity_type"].confidence == CONFIDENCE_HIGH
    assert detailed["activity_value"].confidence == CONFIDENCE_HIGH
    assert committed["columns"]["activity_value"] == "使用量"
    assert high_match_count(detailed) >= 5
    mapping = mapping_from_committed(table, committed)
    assert mapping.activity_value_column == "使用量"
    assert mapping.activity_type_value_map.get("採購鋼材") == "purchased_steel"


def test_medium_is_not_committed_before_confirmation() -> None:
    table = _table(_medium_quantity())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    assert detailed["activity_value"].confidence == "medium"
    assert "activity_value" not in committed["columns"]
    assert medium_is_uncommitted(detailed, committed, "activity_value")
    mapping = mapping_from_committed(table, committed)
    assert mapping.activity_value_column == ""
    items = list_exceptions(table, detailed, committed)
    assert any(item.item_id == "column:activity_value" for item in items)
    assert not can_validate(table, detailed, committed)


def test_low_required_field_remains_unresolved() -> None:
    table = _table(_unmatched_required())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    assert detailed["activity_type"].source_column == ""
    assert "activity_type" not in committed["columns"]
    items = list_exceptions(table, detailed, committed)
    unmatched = [item for item in items if item.item_id == "column:activity_type"]
    assert len(unmatched) == 1
    assert unmatched[0].proposed == ""
    assert required_unresolved_blocks(table, detailed, committed)


def test_exception_queue_omits_high_matches() -> None:
    table = _table(_mixed_energy())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    ids = {item.item_id for item in list_exceptions(table, detailed, committed)}
    assert "column:activity_type" not in ids
    assert "column:unit" not in ids
    assert "column:activity_value" in ids
    assert "context:natural_gas" in ids
    assert "context:diesel" in ids
    assert "context:electricity" in ids
    assert "activity_value:雜項能源" in ids


def test_count_updates_and_reaches_zero() -> None:
    table = _table(_medium_quantity())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    before = unresolved_count(table, detailed, committed)
    assert before >= 1
    item = next(
        row
        for row in list_exceptions(table, detailed, committed)
        if row.item_id == "column:activity_value"
    )
    committed = apply_exception(
        committed,
        item,
        {"column": "用量", "table": table},
    )
    after = unresolved_count(table, detailed, committed)
    assert after == before - 1
    assert after == 0
    assert can_validate(table, detailed, committed)


def test_draft_payload_without_apply_does_not_become_fact() -> None:
    table = _table(_medium_quantity())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    original = dict(committed["columns"])
    draft = {"column": "用量"}
    mapping = mapping_from_committed(table, committed)
    assert mapping.activity_value_column == ""
    assert committed["columns"] == original
    assert draft["column"] == "用量"


def test_required_unresolved_blocks_validation() -> None:
    table = _table(_unmatched_required())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    assert required_unresolved_blocks(table, detailed, committed)
    assert not can_validate(table, detailed, committed)


def test_unresolved_rows_are_held_out_not_dropped() -> None:
    table = _table(_mixed_energy())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    item = next(
        row
        for row in list_exceptions(table, detailed, committed)
        if row.item_id == "column:activity_value"
    )
    committed = apply_exception(
        committed, item, {"column": "用量", "table": table}
    )
    exceptions = list_exceptions(table, detailed, committed)
    ready, waiting = row_readiness_counts(table, committed, exceptions)
    assert ready + waiting == 5
    assert waiting >= 1
    mapping = mapping_from_committed(table, committed)
    assert mapping.activity_type_value_map.get("雜項能源", "") == ""
    assert mapping.activity_type_value_map.get("採購鋼材") == "purchased_steel"


def test_unknown_activity_hold_resolves_question_without_guessing() -> None:
    table = _table(_mixed_energy())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    for item_id, payload in (
        ("column:activity_value", {"column": "用量", "table": table}),
        ("activity_value:雜項能源", {"value": "unknown"}),
        ("context:natural_gas", {"value": "NG1"}),
        ("context:diesel", {"value": "company_vehicle"}),
        ("context:electricity", {"value": "enterprise"}),
    ):
        item = next(
            row
            for row in list_exceptions(table, detailed, committed)
            if row.item_id == item_id
        )
        committed = apply_exception(committed, item, payload)
    assert unresolved_count(table, detailed, committed) == 0
    mapping = mapping_from_committed(table, committed)
    assert mapping.activity_type_value_map.get("雜項能源") == ""
    assert mapping.activity_type_value_map.get("採購鋼材") == "purchased_steel"
    ready, waiting = row_readiness_counts(table, committed, [])
    assert waiting == 1
    assert ready == 4


def test_unknown_context_holds_matching_rows_not_ready() -> None:
    table = _table(_mixed_energy())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    for item_id, payload in (
        ("column:activity_value", {"column": "用量", "table": table}),
        ("activity_value:雜項能源", {"value": "unknown"}),
        ("context:natural_gas", {"value": "unknown"}),
        ("context:diesel", {"value": "unknown"}),
        ("context:electricity", {"value": "unknown"}),
    ):
        item = next(
            row
            for row in list_exceptions(table, detailed, committed)
            if row.item_id == item_id
        )
        committed = apply_exception(committed, item, payload)
    assert unresolved_count(table, detailed, committed) == 0
    ready, held = row_readiness_counts(table, committed, [])
    assert ready + held == 5
    assert ready == 1
    assert held == 4
    mapping = mapping_from_committed(table, committed)
    assert mapping.natural_gas_subtype == "unknown"
    assert mapping.diesel_context == "unknown"
    assert mapping.electricity_context == "unknown"
    validated = build_and_validate_intake(
        table,
        mapping,
        IntakeMetadata(
            source_name="ops.csv",
            site_id="UNKNOWN",
            document_date=date(2025, 1, 31),
            data_quality_tier="unknown",
            intake_run_id="test",
            ingested_at=pd.Timestamp("2025-01-31T00:00:00Z"),
        ),
    )
    validated = hold_unknown_context_rows(validated, mapping)
    assert validated.accepted_count == ready
    assert validated.rejected_count == held
    assert validated.accepted_count + validated.rejected_count == 5


def _apply_named(table, detailed, committed, item_id: str, payload: dict) -> dict:
    item = next(
        row
        for row in list_exceptions(table, detailed, committed)
        if row.item_id == item_id
    )
    return apply_exception(committed, item, payload)


def _validated_counts(table, committed):
    mapping = mapping_from_committed(table, committed)
    validated = build_and_validate_intake(
        table,
        mapping,
        IntakeMetadata(
            source_name="ops.csv",
            site_id="UNKNOWN",
            document_date=date(2025, 1, 31),
            data_quality_tier="unknown",
            intake_run_id="test",
            ingested_at=pd.Timestamp("2025-01-31T00:00:00Z"),
        ),
    )
    return hold_unknown_context_rows(validated, mapping)


def test_unknown_natural_gas_context_holds_gas_row() -> None:
    table = _table(
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    )
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    committed = _apply_named(
        table, detailed, committed, "context:natural_gas", {"value": "unknown"}
    )
    assert unresolved_count(table, detailed, committed) == 0
    ready, held = row_readiness_counts(table, committed, [])
    assert ready == 1
    assert held == 1
    assert ready + held == 2
    validated = _validated_counts(table, committed)
    assert validated.accepted_count == ready
    assert validated.rejected_count == held
    assert any(
        str(row.get("issue_code")) == "HELD_NG_CONTEXT"
        for _, row in validated.rejected_rows.iterrows()
    )


def test_unknown_diesel_context_holds_diesel_row() -> None:
    table = _table(
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
        "柴油,1200,L,2025-01-01,2025-01-31,高雄廠\n"
    )
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    committed = _apply_named(
        table, detailed, committed, "context:diesel", {"value": "unknown"}
    )
    assert unresolved_count(table, detailed, committed) == 0
    ready, held = row_readiness_counts(table, committed, [])
    assert ready == 1
    assert held == 1
    validated = _validated_counts(table, committed)
    assert validated.accepted_count == ready
    assert validated.rejected_count == held
    assert any(
        str(row.get("issue_code")) == "HELD_DIESEL_CONTEXT"
        for _, row in validated.rejected_rows.iterrows()
    )


def test_unknown_electricity_context_holds_electricity_row() -> None:
    table = _table(
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
        "外購電力,1000,kWh,2025-01-01,2025-01-31,高雄廠\n"
    )
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    committed = _apply_named(
        table, detailed, committed, "context:electricity", {"value": "unknown"}
    )
    assert unresolved_count(table, detailed, committed) == 0
    ready, held = row_readiness_counts(table, committed, [])
    assert ready == 1
    assert held == 1
    validated = _validated_counts(table, committed)
    assert validated.accepted_count == ready
    assert validated.rejected_count == held
    assert any(
        str(row.get("issue_code")) == "HELD_ELEC_CONTEXT"
        for _, row in validated.rejected_rows.iterrows()
    )
