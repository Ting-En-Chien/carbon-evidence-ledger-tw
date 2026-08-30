"""Potential-duplicate detection, customer review, and fail-closed analysis."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.ingest import ingest_evidence
from carbon_ledger.intake import (
    ColumnMapping,
    IntakeMetadata,
    build_and_validate_intake,
    default_value_maps,
    parse_uploaded_table,
    suggest_activity_type,
    suggest_column_mapping,
    suggest_unit,
)
from carbon_ledger.potential_duplicates import (
    DECISION_EXCLUDE_DUPLICATES,
    DECISION_KEEP_ALL,
    ISSUE_POTENTIAL_DUPLICATE,
    PotentialDuplicateReviewRequired,
    activities_included_for_calculation,
    analysis_blocked_for_potential_duplicates,
    build_duplicate_review_log,
    decide_potential_duplicate_group,
    decision_to_map_payload,
    find_potential_duplicate_groups,
)
from carbon_ledger.ui.state import (
    STATE_INTAKE_DUPLICATE_REVIEW,
    STATE_INTAKE_RESULT,
    clear_intake_state,
    duplicate_review_blocks_analysis,
    initialize_ui_state,
    run_uploaded_analysis,
)
from carbon_ledger.ui.view_models import calculated_emissions_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
FIXED_INGESTED_AT = pd.Timestamp("2025-02-01T00:00:00Z")
REVIEWED_AT = "2026-08-15T00:00:00Z"

_HEADER = "活動類型,用量,單位,開始日期,結束日期,廠場"


def _csv(*rows: str) -> str:
    return _HEADER + "\n" + "\n".join(rows) + "\n"


def _row(
    activity: str,
    value: str = "8000",
    unit: str = "m3",
    start: str = "2025-01-01",
    end: str = "2025-01-31",
    site: str = "高雄廠",
) -> str:
    return f"{activity},{value},{unit},{start},{end},{site}"


def _metadata(file_name: str = "dup.csv") -> IntakeMetadata:
    return IntakeMetadata(
        source_name=file_name,
        site_id="高雄廠",
        document_date=date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="dup_review_test",
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
        key: value or suggest_activity_type(key)
        for key, value in activity_map.items()
    }
    unit_map = {key: value or suggest_unit(key) for key, value in unit_map.items()}
    mapping = ColumnMapping(
        activity_type_column=suggestions["activity_type"],
        activity_value_column=suggestions["activity_value"],
        unit_column=suggestions["unit"],
        site_column=suggestions.get("site_id") or "",
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
        natural_gas_subtype="NG1",
        diesel_context="company_vehicle",
        electricity_context="enterprise",
    )
    for key, value in overrides.items():
        setattr(mapping, key, value)
    return mapping


def _intake(csv_text: str, file_name: str = "dup.csv", **mapping_overrides: object):
    table = parse_uploaded_table(
        file_name=file_name,
        data=csv_text.encode("utf-8"),
    )
    mapping = _mapping_for(table, **mapping_overrides)
    return build_and_validate_intake(table, mapping, _metadata(file_name))


def _decision_map(intake, decision: str) -> dict[str, dict]:
    groups = list(intake.potential_duplicate_groups)
    assert groups, "expected potential-duplicate groups"
    payload = {}
    for group in groups:
        decided = decide_potential_duplicate_group(
            group,
            decision,
            reviewed_at=REVIEWED_AT,
            review_session="dup_review_test",
        )
        payload[group.group_id] = decision_to_map_payload(decided)
    return payload


def _state_for(intake, decisions: dict | None = None) -> dict:
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_INTAKE_RESULT] = intake
    state[STATE_INTAKE_DUPLICATE_REVIEW] = decisions or {}
    return state


def test_identical_looking_rows_are_detected_as_potential_duplicates() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"))
    intake = _intake(csv)
    assert intake.accepted_count == 2
    groups = find_potential_duplicate_groups(
        intake.accepted_activities, file_hash=intake.file_hash
    )
    assert len(groups) == 1
    assert groups[0].record_ids[0] != groups[0].record_ids[1]
    assert len(intake.potential_duplicate_groups) == 1
    assert ISSUE_POTENTIAL_DUPLICATE == "POTENTIAL_DUPLICATE"


def test_different_site_is_not_the_same_duplicate_group() -> None:
    csv = _csv(
        _row("天然氣 NG1", site="高雄廠"),
        _row("天然氣 NG1", site="台中廠"),
    )
    intake = _intake(csv)
    assert intake.accepted_count == 2
    assert list(intake.potential_duplicate_groups) == []


def test_different_date_is_not_the_same_duplicate_group() -> None:
    csv = _csv(
        _row("天然氣 NG1", start="2025-01-01", end="2025-01-31"),
        _row("天然氣 NG1", start="2025-02-01", end="2025-02-28"),
    )
    intake = _intake(csv)
    assert intake.accepted_count == 2
    assert list(intake.potential_duplicate_groups) == []


def test_different_ng_subtype_is_not_the_same_duplicate_group() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG2"))
    intake = _intake(csv)
    subtypes = sorted(
        str(value) for value in intake.accepted_activities["fuel_subtype"].tolist()
    )
    assert subtypes == ["NG1", "NG2"]
    assert list(intake.potential_duplicate_groups) == []


def test_customer_confirmed_legitimate_duplicates_both_calculate() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"))
    intake = _intake(csv)
    state = _state_for(intake, _decision_map(intake, DECISION_KEEP_ALL))
    result = run_uploaded_analysis(state, run_id="dup_keep_all")
    summary = calculated_emissions_summary(result)
    assert summary["calculated_row_count"] == 2
    calculated = result.calculation_results
    calculated = calculated[
        calculated["calculation_status"].astype(str) == "calculated"
    ]
    values = pd.to_numeric(calculated["calculated_tco2e"], errors="coerce")
    assert float(values.min()) > 0
    assert summary["calculated_tco2e"] == pytest.approx(float(values.sum()))
    single = _intake(_csv(_row("天然氣 NG1")), file_name="single.csv")
    single_state = _state_for(single, {})
    single_result = run_uploaded_analysis(single_state, run_id="dup_single")
    single_total = calculated_emissions_summary(single_result)["calculated_tco2e"]
    assert summary["calculated_tco2e"] == pytest.approx(2 * float(single_total))


def test_confirmed_duplicate_import_excludes_duplicate_from_total() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"))
    intake = _intake(csv)
    decisions = _decision_map(intake, DECISION_EXCLUDE_DUPLICATES)
    state = _state_for(intake, decisions)
    result = run_uploaded_analysis(state, run_id="dup_exclude")
    summary = calculated_emissions_summary(result)
    assert summary["calculated_row_count"] == 1
    excluded = set()
    for payload in decisions.values():
        excluded.update(payload["excluded_record_ids"])
    calc_ids = set(result.calculation_results["record_id"].astype(str))
    assert excluded.isdisjoint(calc_ids)
    single = _intake(_csv(_row("天然氣 NG1")), file_name="single.csv")
    single_total = calculated_emissions_summary(
        run_uploaded_analysis(_state_for(single), run_id="dup_exclude_single")
    )["calculated_tco2e"]
    assert summary["calculated_tco2e"] == pytest.approx(float(single_total))


def test_unresolved_duplicate_blocks_final_analysis() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"))
    intake = _intake(csv)
    groups = list(intake.potential_duplicate_groups)
    assert analysis_blocked_for_potential_duplicates(groups, [])
    state = _state_for(intake, {})
    assert duplicate_review_blocks_analysis(state) is True
    with pytest.raises(PotentialDuplicateReviewRequired):
        run_uploaded_analysis(state, run_id="dup_blocked")
    with pytest.raises(PotentialDuplicateReviewRequired):
        activities_included_for_calculation(
            intake.accepted_activities, groups, []
        )


def test_excluded_duplicate_is_never_treated_as_zero() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"))
    intake = _intake(csv)
    decisions = _decision_map(intake, DECISION_EXCLUDE_DUPLICATES)
    result = run_uploaded_analysis(
        _state_for(intake, decisions), run_id="dup_not_zero"
    )
    excluded: list[str] = []
    for payload in decisions.values():
        excluded.extend(payload["excluded_record_ids"])
    assert excluded
    calc = result.calculation_results
    if not calc.empty:
        overlap = calc[calc["record_id"].astype(str).isin(excluded)]
        assert overlap.empty
        calculated = calc[calc["calculation_status"].astype(str) == "calculated"]
        values = pd.to_numeric(calculated["calculated_tco2e"], errors="coerce")
        assert not (values.fillna(0) == 0).any()


def test_audit_trail_preserves_original_imported_row() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"))
    intake = _intake(csv)
    original_ids = list(intake.accepted_activities["record_id"].astype(str))
    assert len(original_ids) == 2
    decisions = _decision_map(intake, DECISION_EXCLUDE_DUPLICATES)
    run_uploaded_analysis(_state_for(intake, decisions), run_id="dup_audit")
    still = list(intake.accepted_activities["record_id"].astype(str))
    assert still == original_ids
    log = build_duplicate_review_log(
        intake.accepted_activities,
        intake.potential_duplicate_groups,
        [
            decide_potential_duplicate_group(
                intake.potential_duplicate_groups[0],
                DECISION_EXCLUDE_DUPLICATES,
                reviewed_at=REVIEWED_AT,
                review_session="dup_review_test",
            )
        ],
    )
    assert len(log) == 2
    assert bool(log["original_present"].all())
    assert int(log["excluded_from_calculation"].sum()) == 1
    assert set(log["decision"]) == {DECISION_EXCLUDE_DUPLICATES}
    assert REVIEWED_AT in set(log["reviewed_at"])


def test_existing_duplicate_id_fail_closed_behavior_unchanged(tmp_path: Path) -> None:
    import shutil

    raw = tmp_path / "raw"
    shutil.copytree(RAW_DIR, raw)
    csv_path = raw / "activity_records.csv"
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    duplicate_id = frame.loc[0, "record_id"]
    frame.loc[1, "record_id"] = duplicate_id
    frame.to_csv(csv_path, index=False)
    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id="dup_id_gate",
        ingested_at=pd.Timestamp("2024-02-01T12:00:00"),
    )
    dupes = result.activity_records.rejected
    dupes = dupes[dupes["rejection_code"] == "DUPLICATE_RECORD_ID"]
    assert len(dupes) == 2

    docs_path = raw / "source_documents.csv"
    shutil.rmtree(raw)
    shutil.copytree(RAW_DIR, raw)
    docs_path = raw / "source_documents.csv"
    docs = pd.read_csv(docs_path, dtype=str, keep_default_na=False)
    duplicate_doc = docs.loc[0, "source_document_id"]
    docs.loc[1, "source_document_id"] = duplicate_doc
    docs.to_csv(docs_path, index=False)
    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id="dup_doc_gate",
        ingested_at=pd.Timestamp("2024-02-01T12:00:00"),
    )
    doc_dupes = result.source_documents.rejected
    doc_dupes = doc_dupes[
        doc_dupes["rejection_code"] == "DUPLICATE_SOURCE_DOCUMENT_ID"
    ]
    assert len(doc_dupes) == 2


def test_totals_equal_confirmed_included_calculated_rows_only() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"), _row("外購電力", "50000", "kWh"))
    intake = _intake(csv)
    decisions = _decision_map(intake, DECISION_EXCLUDE_DUPLICATES)
    result = run_uploaded_analysis(
        _state_for(intake, decisions), run_id="dup_totals"
    )
    included = activities_included_for_calculation(
        intake.accepted_activities,
        intake.potential_duplicate_groups,
        [
            decide_potential_duplicate_group(
                group,
                DECISION_EXCLUDE_DUPLICATES,
                reviewed_at=REVIEWED_AT,
                review_session="dup_review_test",
            )
            for group in intake.potential_duplicate_groups
        ],
    )
    summary = calculated_emissions_summary(result)
    calc = result.calculation_results
    calc = calc[calc["calculation_status"].astype(str) == "calculated"]
    assert set(calc["record_id"].astype(str)) <= set(
        included["record_id"].astype(str)
    )
    assert summary["calculated_tco2e"] == pytest.approx(
        float(pd.to_numeric(calc["calculated_tco2e"], errors="coerce").sum())
    )
    assert len(included) == intake.accepted_count - 1


def test_reupload_clears_old_duplicate_review_decisions() -> None:
    first = _intake(
        _csv(_row("天然氣 NG1"), _row("天然氣 NG1")), file_name="first.csv"
    )
    decisions = _decision_map(first, DECISION_EXCLUDE_DUPLICATES)
    state = _state_for(first, decisions)
    state["intake_dup_decision_stale"] = DECISION_EXCLUDE_DUPLICATES
    assert duplicate_review_blocks_analysis(state) is False
    clear_intake_state(state)
    assert state.get(STATE_INTAKE_DUPLICATE_REVIEW) == {}
    assert state.get("intake_dup_decision_stale") is None

    second = _intake(
        _csv(
            _row("天然氣 NG1", value="8100"),
            _row("天然氣 NG1", value="8100"),
        ),
        file_name="second.csv",
    )
    assert first.file_hash != second.file_hash
    state[STATE_INTAKE_RESULT] = second
    state[STATE_INTAKE_DUPLICATE_REVIEW] = decisions
    assert duplicate_review_blocks_analysis(state) is True
    with pytest.raises(PotentialDuplicateReviewRequired):
        run_uploaded_analysis(state, run_id="dup_stale")

    clean = _intake(_csv(_row("天然氣 NG1")), file_name="clean.csv")
    state[STATE_INTAKE_RESULT] = clean
    state[STATE_INTAKE_DUPLICATE_REVIEW] = decisions
    assert duplicate_review_blocks_analysis(state) is False
    clean_result = run_uploaded_analysis(state, run_id="dup_clean_reupload")
    assert calculated_emissions_summary(clean_result)["calculated_row_count"] == 1


def test_parser_does_not_automatically_drop_lookalike_rows() -> None:
    csv = _csv(_row("天然氣 NG1"), _row("天然氣 NG1"))
    intake = _intake(csv)
    assert intake.accepted_count == 2
    assert intake.rejected_count == 0
    ids = list(intake.accepted_activities["record_id"].astype(str))
    assert ids[0] != ids[1]
    assert hashlib.sha256(csv.encode("utf-8")).hexdigest() == intake.file_hash
