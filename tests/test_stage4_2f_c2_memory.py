"""Stage 4.2F-C2 — session-scoped mapping memory and provenance."""

from __future__ import annotations

from datetime import date

import pandas as pd

import carbon_ledger.intake_mapping_memory as memory_mod
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
    initialize_committed,
    list_exceptions,
    mapping_from_committed,
    summary_counts,
)
from carbon_ledger.intake_mapping_memory import (
    EVENT_CUSTOMER_CONFIRMED,
    EVENT_CUSTOMER_CORRECTED,
    EVENT_MARKED_UNKNOWN,
    MAPPING_SCHEMA_VERSION,
    append_provenance_event,
    customer_history_rows,
    lookup_remembered_mapping,
    memory_identity_key,
    overlay_remembered_committed,
    record_system_suggestions,
    remember_committed_mapping,
    snapshot_contains_raw_samples,
    snapshot_rememberable_committed,
    structural_fingerprint,
)
from carbon_ledger.ui.state import clear_intake_state, confirmed_company_ubn


def _table(csv: str):
    return parse_uploaded_table(file_name="ops.csv", data=csv.encode("utf-8"))


def _high_csv() -> str:
    return (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    )


def _medium_csv() -> str:
    return (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    )


def test_fingerprint_is_structural_not_file_bytes() -> None:
    first = _table(_high_csv())
    second = _table(
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,99,t,2025-02-01,2025-02-28,高雄廠\n"
    )
    fp1 = structural_fingerprint(
        columns=list(first.columns), header_row_index=first.header_row_index
    )
    fp2 = structural_fingerprint(
        columns=list(second.columns), header_row_index=second.header_row_index
    )
    assert fp1 == fp2
    assert first.sha256 != second.sha256
    assert len(fp1) == 64


def test_monthly_worksheet_titles_share_structural_fingerprint() -> None:
    columns = ["活動類型", "用量", "單位", "開始日期", "結束日期"]
    fingerprints = {
        structural_fingerprint(columns=columns, sheet_name=sheet)
        for sheet in ("2026年1月", "2026年2月", "Jan", "Feb")
    }
    assert len(fingerprints) == 1


def test_changed_required_headers_have_different_fingerprints() -> None:
    first = structural_fingerprint(columns=["活動類型", "用量", "單位"])
    changed = structural_fingerprint(columns=["活動類型", "實際用量", "單位"])
    assert first != changed


def test_same_ubn_same_structure_finds_memory() -> None:
    table = _table(_medium_csv())
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
    session: dict = {}
    fingerprint = structural_fingerprint(columns=list(table.columns))
    remember_committed_mapping(
        session, ubn="12345675", fingerprint=fingerprint, committed=committed
    )
    found = lookup_remembered_mapping(
        session, ubn="12345675", fingerprint=fingerprint
    )
    assert found is not None
    assert found["columns"]["activity_value"] == "用量"


def test_different_ubn_never_receives_mapping() -> None:
    session: dict = {}
    fingerprint = structural_fingerprint(columns=["活動類型", "用量", "單位"])
    remember_committed_mapping(
        session,
        ubn="12345675",
        fingerprint=fingerprint,
        committed={"columns": {"activity_value": "用量"}},
    )
    assert (
        lookup_remembered_mapping(
            session, ubn="24681358", fingerprint=fingerprint
        )
        is None
    )


def test_incompatible_structure_does_not_force_reuse() -> None:
    session: dict = {}
    remember_committed_mapping(
        session,
        ubn="12345675",
        fingerprint=structural_fingerprint(columns=["活動類型", "用量", "單位"]),
        committed={"columns": {"activity_value": "用量"}},
    )
    other = structural_fingerprint(columns=["說明欄", "數字", "度量"])
    assert lookup_remembered_mapping(session, ubn="12345675", fingerprint=other) is None


def test_draft_medium_suggestion_is_not_remembered() -> None:
    table = _table(_medium_csv())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    draft = initialize_committed(table, detailed)
    assert "activity_value" not in (draft.get("columns") or {})
    snapshot = snapshot_rememberable_committed(draft)
    assert "activity_value" not in snapshot["columns"]


def test_unknown_answer_is_not_remembered_as_confirmed() -> None:
    snapshot = snapshot_rememberable_committed(
        {
            "activity_type_value_map": {"雜項能源": ""},
            "columns": {"activity_type": "活動類型"},
            "diesel_context": "unknown",
            "electricity_context": "unknown",
            "natural_gas_subtype": "unknown",
        }
    )
    assert snapshot["activity_type_value_map"] == {}
    assert "natural_gas_subtype" not in snapshot
    assert "diesel_context" not in snapshot
    assert "electricity_context" not in snapshot


def test_snapshot_retains_only_safe_structural_contract() -> None:
    snapshot = snapshot_rememberable_committed(
        {
            "columns": {
                "activity_type": "活動類型",
                "activity_value": "用量",
                "unit": "單位",
                "site_id": "廠場",
            },
            "date_mode": "period",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "document_date": "2026-01-31",
            "natural_gas_subtype": "NG1",
            "diesel_context": "company_vehicle",
            "electricity_context": "enterprise",
            "fallback_site_id": "高雄一廠",
            "source_name": "January energy file",
            "data_quality_tier": "primary",
            "activity_type_value_map": {
                "客製燃料": "natural_gas",
                "未確認燃料": "diesel",
            },
            "unit_value_map": {"立方公尺": "m3", "未確認單位": "L"},
            "applied_ids": [
                "column:activity_value",
                "activity_value:客製燃料",
                "unit_value:立方公尺",
            ],
        }
    )
    assert snapshot == {
        "activity_type_value_map": {"客製燃料": "natural_gas"},
        "columns": {
            "activity_type": "活動類型",
            "activity_value": "用量",
            "unit": "單位",
            "site_id": "廠場",
        },
        "date_mode": "period",
        "schema_version": MAPPING_SCHEMA_VERSION,
        "unit_value_map": {"立方公尺": "m3"},
        "year_month_confirmed": False,
    }


def test_global_period_and_context_are_not_reused_in_new_file() -> None:
    remembered = snapshot_rememberable_committed(
        {
            "columns": {
                "activity_type": "活動類型",
                "activity_value": "用量",
                "unit": "單位",
            },
            "date_mode": "period",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "document_date": "2026-01-31",
            "natural_gas_subtype": "NG1",
            "diesel_context": "company_vehicle",
            "electricity_context": "enterprise",
        }
    )
    table = _table(
        "活動類型,用量,單位\n"
        "天然氣,2,m3\n"
        "柴油,3,L\n"
        "外購電力,4,kWh\n"
    )
    current = initialize_committed(
        table,
        suggest_column_mapping_with_confidence(list(table.columns)),
    )
    reused = overlay_remembered_committed(current, remembered, frame=table.frame)
    assert reused["date_mode"] == "period"
    assert reused["period_start"] is None
    assert reused["period_end"] is None
    assert reused["document_date"] is None
    assert reused["natural_gas_subtype"] == ""
    assert reused["diesel_context"] == ""
    assert reused["electricity_context"] == ""
    exceptions = list_exceptions(
        table,
        suggest_column_mapping_with_confidence(list(table.columns)),
        reused,
    )
    assert any(item.item_id == "dates_period" for item in exceptions)
    assert not can_validate(
        table,
        suggest_column_mapping_with_confidence(list(table.columns)),
        reused,
    )


def test_february_validation_uses_only_february_period_and_quantity() -> None:
    january = _table(
        "活動類型,用量,單位,廠場\n"
        "天然氣,8000,m3,高雄一廠\n"
    )
    january_detailed = suggest_column_mapping_with_confidence(
        list(january.columns)
    )
    january_committed = initialize_committed(january, january_detailed)
    quantity_item = next(
        item
        for item in list_exceptions(
            january, january_detailed, january_committed
        )
        if item.item_id == "column:activity_value"
    )
    january_committed = apply_exception(
        january_committed,
        quantity_item,
        {"column": "用量", "table": january},
    )
    dates_item = next(
        item
        for item in list_exceptions(
            january, january_detailed, january_committed
        )
        if item.item_id == "dates_period"
    )
    january_committed = apply_exception(
        january_committed,
        dates_item,
        {
            "date_mode": "period",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
        },
    )
    context_item = next(
        item
        for item in list_exceptions(
            january, january_detailed, january_committed
        )
        if item.item_id == "context:natural_gas"
    )
    january_committed = apply_exception(
        january_committed, context_item, {"value": "NG1"}
    )
    remembered = snapshot_rememberable_committed(january_committed)

    february = _table(
        "活動類型,用量,單位,廠場\n"
        "天然氣,9000,m3,高雄一廠\n"
    )
    february_detailed = suggest_column_mapping_with_confidence(
        list(february.columns)
    )
    february_committed = overlay_remembered_committed(
        initialize_committed(february, february_detailed),
        remembered,
        frame=february.frame,
    )
    assert february_committed["period_start"] is None
    assert february_committed["period_end"] is None
    assert february_committed["natural_gas_subtype"] == ""
    feb_dates = next(
        item
        for item in list_exceptions(
            february, february_detailed, february_committed
        )
        if item.item_id == "dates_period"
    )
    february_committed = apply_exception(
        february_committed,
        feb_dates,
        {
            "date_mode": "period",
            "period_start": "2026-02-01",
            "period_end": "2026-02-28",
        },
    )
    feb_context = next(
        item
        for item in list_exceptions(
            february, february_detailed, february_committed
        )
        if item.item_id == "context:natural_gas"
    )
    february_committed = apply_exception(
        february_committed, feb_context, {"value": "NG1"}
    )
    result = build_and_validate_intake(
        february,
        mapping_from_committed(february, february_committed),
        IntakeMetadata(
            source_name="February current file",
            site_id="UNKNOWN",
            document_date=date(2026, 2, 28),
            data_quality_tier="unknown",
            intake_run_id="test-february",
            ingested_at=pd.Timestamp("2026-03-01T00:00:00Z"),
        ),
    )
    assert result.accepted_count == 1
    accepted = result.accepted_activities.iloc[0]
    assert accepted["activity_value"] == 9000
    assert str(accepted["activity_start_date"])[:10] == "2026-02-01"
    assert str(accepted["activity_end_date"])[:10] == "2026-02-28"
    assert "8000" not in result.accepted_activities.to_string()
    assert "2026-01" not in result.accepted_activities.to_string()


def test_exact_source_labels_only_are_reused() -> None:
    remembered = {
        "columns": {"activity_type": "活動類型", "unit": "單位"},
        "activity_type_value_map": {"客製燃料": "natural_gas"},
        "unit_value_map": {"立方公尺": "m3"},
    }
    same = _table(
        "活動類型,使用量,單位,開始日期,結束日期\n"
        "客製燃料,1,立方公尺,2026-02-01,2026-02-28\n"
    )
    same_reused = overlay_remembered_committed(
        initialize_committed(
            same,
            suggest_column_mapping_with_confidence(list(same.columns)),
        ),
        remembered,
        frame=same.frame,
    )
    assert same_reused["activity_type_value_map"]["客製燃料"] == "natural_gas"
    assert same_reused["unit_value_map"]["立方公尺"] == "m3"

    changed = _table(
        "活動類型,使用量,單位,開始日期,結束日期\n"
        "新燃料,1,新單位,2026-02-01,2026-02-28\n"
    )
    detailed = suggest_column_mapping_with_confidence(list(changed.columns))
    changed_reused = overlay_remembered_committed(
        initialize_committed(changed, detailed),
        remembered,
        frame=changed.frame,
    )
    assert "客製燃料" not in changed_reused["activity_type_value_map"]
    assert "立方公尺" not in changed_reused["unit_value_map"]
    ids = {
        item.item_id
        for item in list_exceptions(changed, detailed, changed_reused)
    }
    assert "activity_value:新燃料" in ids
    assert "unit_value:新單位" in ids


def test_only_explicitly_confirmed_value_maps_are_remembered() -> None:
    snapshot = snapshot_rememberable_committed(
        {
            "columns": {"activity_type": "活動類型", "unit": "單位"},
            "activity_type_value_map": {
                "天然氣": "natural_gas",
                "客製燃料": "diesel",
            },
            "unit_value_map": {"kWh": "kWh", "箱": "item"},
            "applied_ids": ["activity_value:客製燃料", "unit_value:箱"],
        }
    )
    assert snapshot["activity_type_value_map"] == {"客製燃料": "diesel"}
    assert snapshot["unit_value_map"] == {"箱": "item"}


def test_later_correction_becomes_latest_reusable_mapping() -> None:
    session: dict = {}
    fingerprint = structural_fingerprint(columns=["活動類型", "用量", "單位"])
    remember_committed_mapping(
        session,
        ubn="12345675",
        fingerprint=fingerprint,
        committed={"columns": {"activity_value": "用量"}},
    )
    remember_committed_mapping(
        session,
        ubn="12345675",
        fingerprint=fingerprint,
        committed={"columns": {"activity_value": "實際用量"}},
    )
    found = lookup_remembered_mapping(
        session, ubn="12345675", fingerprint=fingerprint
    )
    assert found is not None
    assert found["columns"]["activity_value"] == "實際用量"


def test_provenance_keeps_earlier_confirmation_and_later_correction() -> None:
    session: dict = {}
    append_provenance_event(
        session,
        event=EVENT_CUSTOMER_CONFIRMED,
        company_ubn="12345675",
        field="activity_value",
        committed="用量",
    )
    append_provenance_event(
        session,
        event=EVENT_CUSTOMER_CORRECTED,
        company_ubn="12345675",
        field="activity_value",
        committed="實際用量",
    )
    rows = customer_history_rows(
        session,
        company_ubn="12345675",
        lang="zh-TW",
        field_labels={"activity_value": "用量"},
    )
    assert [row["action"] for row in rows] == ["你已確認", "你已調整"]
    assert rows[0]["detail"] == "用量"
    assert rows[1]["detail"] == "實際用量"
    for row in rows:
        assert "customer_confirmed" not in row["action"]
        assert "fingerprint" not in row["detail"]
        assert "activity_value" not in row["field"] or row["field"] == "用量"


def test_company_history_is_scoped_to_confirmed_ubn() -> None:
    session: dict = {}
    for ubn, detail in (
        ("12345675", "甲公司欄位"),
        ("24681358", "乙公司欄位"),
        ("", "確認公司前欄位"),
    ):
        append_provenance_event(
            session,
            event=EVENT_CUSTOMER_CONFIRMED,
            company_ubn=ubn,
            field="activity_value",
            committed=detail,
        )
    rows = customer_history_rows(
        session, company_ubn="24681358", lang="zh-TW"
    )
    assert [row["detail"] for row in rows] == ["乙公司欄位"]
    assert "甲公司欄位" not in str(rows)
    assert "確認公司前欄位" not in str(rows)


def test_history_localizes_internal_values_in_both_languages() -> None:
    session: dict = {}
    for value in (
        "natural_gas",
        "company_vehicle",
        "enterprise",
        "emission_activity",
    ):
        append_provenance_event(
            session,
            event=EVENT_CUSTOMER_CONFIRMED,
            company_ubn="12345675",
            field="activity_type",
            committed=value,
        )
    labels_zh = {
        "natural_gas": "天然氣",
        "company_vehicle": "公司車輛／公司控制的移動燃燒",
        "enterprise": "企業／廠場盤查",
        "emission_activity": "排放活動",
    }
    labels_en = {
        "natural_gas": "Natural gas",
        "company_vehicle": "Company vehicle",
        "enterprise": "Enterprise / site inventory",
        "emission_activity": "Emissions activity",
    }
    zh_rows = customer_history_rows(
        session,
        company_ubn="12345675",
        lang="zh-TW",
        value_labels=labels_zh,
    )
    en_rows = customer_history_rows(
        session,
        company_ubn="12345675",
        lang="en",
        value_labels=labels_en,
    )
    for raw in labels_zh:
        assert raw not in str(zh_rows)
        assert raw not in str(en_rows)
    assert "天然氣" in str(zh_rows)
    assert "Natural gas" in str(en_rows)


def test_suggestion_reruns_do_not_duplicate_history() -> None:
    table = _table(_medium_csv())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    session: dict = {}
    fingerprint = structural_fingerprint(columns=list(table.columns))
    record_system_suggestions(
        session,
        detailed,
        company_ubn="12345675",
        fingerprint=fingerprint,
        source_document_id="upload_abc",
    )
    first_count = len(session["intake_mapping_provenance"])
    record_system_suggestions(
        session,
        detailed,
        company_ubn="12345675",
        fingerprint=fingerprint,
        source_document_id="upload_abc",
    )
    assert len(session["intake_mapping_provenance"]) == first_count
    record_system_suggestions(
        session,
        detailed,
        company_ubn="24681358",
        fingerprint=fingerprint,
        source_document_id="upload_abc",
    )
    assert len(session["intake_mapping_provenance"]) == first_count * 2


def test_memory_contains_no_workbook_bytes_or_samples() -> None:
    session: dict = {}
    remember_committed_mapping(
        session,
        ubn="12345675",
        fingerprint="abc",
        committed={
            "columns": {"activity_value": "用量"},
            "bytes": b"secret",
            "samples": ["8000"],
        },
    )
    stored = session["intake_mapping_memory"]
    assert not snapshot_contains_raw_samples(stored["entries"])
    blob = str(stored)
    assert "secret" not in blob
    assert "8000" not in blob


def test_no_module_global_customer_mapping_leakage() -> None:
    for name, value in vars(memory_mod).items():
        if name.startswith("__"):
            continue
        if isinstance(value, dict) and any(
            key in str(value) for key in ("12345675", "activity_value")
        ):
            raise AssertionError(f"module-global mapping cache: {name}")
    assert not hasattr(memory_mod, "MAPPING_CACHE")
    key = memory_identity_key("12345675", "fp")
    assert MAPPING_SCHEMA_VERSION in key


def test_reset_for_new_file_does_not_erase_mapping_memory() -> None:
    session = {
        "intake_mapping_memory": {
            "entries": {
                "12345675|intake-mapping-v1|fp": {
                    "committed": {"columns": {"activity_value": "用量"}}
                }
            }
        },
        "intake_mapping_provenance": [{"event": EVENT_CUSTOMER_CONFIRMED}],
        "intake_committed_decisions": {"columns": {"unit": "單位"}},
        "uploaded_table": object(),
        "intake_memory_choice": "apply",
    }
    clear_intake_state(session)
    assert "intake_mapping_memory" in session
    assert "intake_mapping_provenance" in session
    assert "intake_committed_decisions" not in session
    assert "uploaded_table" not in session
    assert "intake_memory_choice" not in session


def test_c1_counts_remain_correct_after_reuse() -> None:
    table = _table(_medium_csv())
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    first = initialize_committed(table, detailed)
    item = next(
        row
        for row in list_exceptions(table, detailed, first)
        if row.item_id == "column:activity_value"
    )
    first = apply_exception(first, item, {"column": "用量", "table": table})
    reused = overlay_remembered_committed(
        initialize_committed(table, detailed),
        snapshot_rememberable_committed(first),
    )
    counts = summary_counts(table, detailed, reused)
    assert counts["confirm"] == 0
    assert counts["ready_rows"] == 1
    assert counts["waiting_rows"] == 0
    assert detailed["activity_value"].confidence != CONFIDENCE_HIGH


def test_unknown_event_is_not_treated_as_confirmed_mapping() -> None:
    snapshot = snapshot_rememberable_committed(
        {
            "activity_type_value_map": {"雜項能源": ""},
            "columns": {"activity_type": "活動類型"},
        }
    )
    append_payload = {"event": EVENT_MARKED_UNKNOWN, "committed": ""}
    assert snapshot["activity_type_value_map"] == {}
    assert append_payload["committed"] == ""


def test_unconfirmed_company_has_no_ubn() -> None:
    assert confirmed_company_ubn({}) == ""
    assert (
        confirmed_company_ubn(
            {
                "company_master": {
                    "unified_business_number": "12345675",
                    "customer_confirmed_at": "",
                }
            }
        )
        == ""
    )
    assert (
        confirmed_company_ubn(
            {
                "company_master": {
                    "unified_business_number": "12345675",
                    "customer_confirmed_at": "2026-08-01T00:00:00Z",
                }
            }
        )
        == "12345675"
    )
