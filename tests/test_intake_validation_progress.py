"""Intake validation progress, batch schema parity, and popover contrast."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.intake import (
    ColumnMapping,
    IntakeError,
    IntakeMetadata,
    build_and_validate_intake,
    default_value_maps,
    intake_validation_percent,
    parse_uploaded_table,
    suggest_activity_type,
    suggest_column_mapping,
    suggest_unit,
)
from carbon_ledger.potential_duplicates import source_row_from_locator
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.intake_validation import (
    OUTCOME_OK,
    OUTCOME_UNEXPECTED,
    execute_intake_validation,
    recover_stale_intake_validation,
)
from carbon_ledger.ui.motion import (
    ANALYSIS_PHASE_ANALYZING,
    ANALYSIS_PHASE_CLOSING,
    ANALYSIS_PHASE_FAILED,
    ANALYSIS_PHASE_REVEAL,
    should_open_analysis_progress_dialog,
)
from carbon_ledger.ui.state import (
    STATE_ANALYSIS_PHASE,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_STEP,
    STATE_INTAKE_VALIDATION_ERROR,
    STATE_INTAKE_VALIDATION_REQUESTED,
    STATE_INTAKE_VALIDATION_RUNNING,
    initialize_ui_state,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2025-02-01T00:00:00Z")
ZH = "zh-TW"
EN = "en"


def _metadata() -> IntakeMetadata:
    return IntakeMetadata(
        source_name="ops.csv",
        site_id="高雄廠",
        document_date=date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="progress_test",
        ingested_at=FIXED_INGESTED_AT,
    )


def _mapping_for(table) -> ColumnMapping:
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
    return ColumnMapping(
        activity_type_column=suggestions["activity_type"],
        activity_value_column=suggestions["activity_value"],
        unit_column=suggestions["unit"],
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
    )


def _mixed_csv() -> str:
    return (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "grid_electricity,1000,kWh,2025-01-01,2025-01-31\n"
        "grid_electricity,1000,kWh,2025-01-01,2025-01-31\n"
        "natural_gas,8000,m3,2025-01-01,2025-01-31\n"
        "diesel,abc,L,2025-01-01,2025-01-31\n"
        "mystery_fuel,10,t,2025-01-01,2025-01-31\n"
        "diesel,10,L,not-a-date,2025-01-31\n"
    )


def _snapshot(result) -> dict[str, object]:
    rejected = result.rejected_rows.sort_values("source_row").reset_index(drop=True)
    accepted = result.accepted_activities.reset_index(drop=True)
    accepted_rows = [
        source_row_from_locator(locator)
        for locator in accepted.get("source_locator", pd.Series(dtype=str)).tolist()
    ]
    groups = [
        (tuple(group.record_ids), tuple(group.source_rows))
        for group in result.potential_duplicate_groups
    ]
    dispositions: list[tuple[int, str, str, str]] = []
    for source_row in accepted_rows:
        dispositions.append((int(source_row), "accepted", "", ""))
    if len(rejected):
        for item in rejected.itertuples(index=False):
            dispositions.append(
                (
                    int(item.source_row),
                    "rejected",
                    str(item.issue_code),
                    str(item.field),
                )
            )
    dispositions.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return {
        "accepted_count": int(result.accepted_count),
        "rejected_count": int(result.rejected_count),
        "total_count": int(result.total_count),
        "accepted_ids": list(accepted.get("record_id", pd.Series(dtype=str))),
        "accepted_source": list(accepted.get("source_locator", pd.Series(dtype=str))),
        "accepted_source_rows": accepted_rows,
        "accepted_review": list(
            accepted.get("human_review_status", pd.Series(dtype=str))
        ),
        "rejected_rows": rejected["source_row"].tolist() if len(rejected) else [],
        "rejected_codes": rejected["issue_code"].tolist() if len(rejected) else [],
        "rejected_messages": (
            rejected["issue_message"].tolist() if len(rejected) else []
        ),
        "rejected_fields": rejected["field"].tolist() if len(rejected) else [],
        "dispositions": dispositions,
        "duplicate_groups": groups,
    }


def test_intake_progress_is_monotonic_zero_to_hundred() -> None:
    table = parse_uploaded_table(
        file_name="ops.csv", data=_mixed_csv().encode("utf-8")
    )
    seen: list[int] = []

    def _progress(stage: str, completed: int, total: int, message: str) -> None:
        del message
        percent = intake_validation_percent(stage, completed, total)
        if seen:
            assert percent >= seen[-1]
        seen.append(percent)

    result = build_and_validate_intake(
        table, _mapping_for(table), _metadata(), progress=_progress
    )
    assert seen[0] == 0 or seen[0] == 8
    assert seen[-1] == 100
    assert result.total_count >= 1
    row_percents = [
        intake_validation_percent("rows", done, 1000)
        for done in range(0, 1001, 25)
    ]
    assert row_percents == sorted(row_percents)
    assert intake_validation_percent("rows", 0, 1000) == 8
    assert intake_validation_percent("complete", 1, 1) == 100


def test_batch_schema_matches_row_strategy_exactly() -> None:
    table = parse_uploaded_table(
        file_name="ops.csv", data=_mixed_csv().encode("utf-8")
    )
    mapping = _mapping_for(table)
    metadata = _metadata()
    batched = build_and_validate_intake(
        table, mapping, metadata, schema_strategy="batch"
    )
    rowwise = build_and_validate_intake(
        table, mapping, metadata, schema_strategy="row"
    )
    assert _snapshot(batched) == _snapshot(rowwise)


def test_closing_does_not_remount_dialog() -> None:
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_ANALYZING
    assert should_open_analysis_progress_dialog(state, run_clicked=False)
    state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_CLOSING
    assert should_open_analysis_progress_dialog(state, run_clicked=False) is False
    state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_REVEAL
    assert should_open_analysis_progress_dialog(state, run_clicked=False) is False
    state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_FAILED
    assert should_open_analysis_progress_dialog(state, run_clicked=True)


def test_click_run_only_sets_validation_requested() -> None:
    source = (REPO_ROOT / "app_pages/data_intake.py").read_text(encoding="utf-8")
    click_at = source.find("STATE_INTAKE_VALIDATION_REQUESTED] = True")
    assert click_at != -1
    window = source[click_at : click_at + 500]
    assert "st.rerun()" in window
    assert "build_and_validate_intake" not in window
    round_two = source.split("def _run_intake_validation_round_two")[1].split(
        "def _field_label"
    )[0]
    paint_at = round_two.find("st.progress")
    work_at = round_two.find("execute_intake_validation")
    assert 0 <= paint_at < work_at
    assert "disabled=True" in round_two[:work_at]
    recover_at = source.find("recover_stale_intake_validation(st.session_state)")
    busy_at = source.find("_validation_busy")
    assert 0 <= recover_at < busy_at
    summary = source.split("def _render_completed_step_summary")[1].split(
        "HELD_ISSUE_CODES"
    )[0]
    assert summary.count("st.button(") == 2
    assert summary.count("disabled=disabled") == 2
    assert "disabled=_validation_busy" in source
    assert "time.sleep" not in source


def test_navigate_flag_only_set_on_clean_run_source() -> None:
    app = (REPO_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    dash = (REPO_ROOT / "app_pages/dashboard.py").read_text(encoding="utf-8")
    motion = (REPO_ROOT / "src/carbon_ledger/ui/motion.py").read_text(encoding="utf-8")
    page = (REPO_ROOT / "app_pages/analysis_progress.py").read_text(encoding="utf-8")
    assert "ANALYSIS_PHASE_CLOSING" in app
    assert "STATE_NAVIGATE_TO_RESULTS" in app
    closing_at = app.find(
        "if analysis_phase(st.session_state) == ANALYSIS_PHASE_CLOSING:"
    )
    navigate_at = app.find("STATE_NAVIGATE_TO_RESULTS] = True")
    analysis_switch_at = app.find(
        'st.switch_page("app_pages/analysis_progress.py")'
    )
    dash_switch_at = app.find('st.switch_page("app_pages/dashboard.py")')
    nav_run_at = app.find("navigation.run()")
    assert closing_at != -1 and navigate_at != -1
    assert (
        0
        <= analysis_switch_at
        < closing_at
        < navigate_at
        < dash_switch_at
        < nav_run_at
    )
    assert "ANALYSIS_PHASE_ANALYZING" in dash
    assert "st.stop()" in dash
    assert "render_analysis_transition_view" in page
    assert "@st.dialog" not in motion
    assert "@st.dialog" not in page
    assert "ANALYSIS_PHASE_COMPLETE" not in (
        motion.split("def should_render_analysis_transition_view")[1].split("def ")[0]
    )


def test_popover_css_is_scoped_and_bilingual() -> None:
    css = (REPO_ROOT / "src/carbon_ledger/ui/visual_system.css").read_text(
        encoding="utf-8"
    )
    design = (REPO_ROOT / "src/carbon_ledger/ui/components.py").read_text(
        encoding="utf-8"
    )
    blob = css + design
    assert 'div[data-testid="stPopover"] > button' in blob
    assert 'div[data-testid="stPopover"] > div > button' in blob
    assert "focus-visible" in blob
    assert ":disabled" in blob
    assert "section[data-testid=\"stSidebar\"] div[data-testid=\"stPopover\"]" in blob
    assert t("header.glossary", ZH) == "名詞解釋"
    assert t("header.glossary", EN) == "Glossary"
    assert "button {" not in blob.split("stPopover")[0][-80:]
    assert 'div[data-testid="stPopover"] button[kind]' not in blob
    assert 'div[data-testid="stPopover"] button p' not in blob
    assert 'div[data-testid="stPopover"] button span' not in blob
    scoped = blob.replace('div[data-testid="stPopover"] > div > button', "")
    scoped = scoped.replace('div[data-testid="stPopover"] > button', "")
    assert "stPopover\"] button" not in scoped


def test_progress_status_copy_meets_contrast_on_white() -> None:
    css = (REPO_ROOT / "src/carbon_ledger/ui/visual_system.css").read_text(
        encoding="utf-8"
    )
    design = (REPO_ROOT / "src/carbon_ledger/ui/components.py").read_text(
        encoding="utf-8"
    )
    source = (REPO_ROOT / "app_pages/data_intake.py").read_text(encoding="utf-8")
    blob = css + design
    assert ".cel-intake-progress-copy" in blob
    rule = blob.split(".cel-intake-progress-copy")[1].split("}")[0]
    assert "#334155" in rule
    assert _contrast_ratio("#334155", "#FFFFFF") >= 4.5
    assert "cel-intake-progress-copy" in source
    round_two = source.split("def _run_intake_validation_round_two")[1].split(
        "def _field_label"
    )[0]
    assert "st.caption" not in round_two
    assert t("intake.validate.stage.rows", ZH) == "驗證資料列"
    assert t("intake.validate.processing_count", ZH, count="1,000") == (
        "正在處理 1,000 筆活動資料"
    )
    assert "cursor: not-allowed" in blob
    assert 'button[kind="primary"]:disabled' in blob
    assert 'button[kind="secondary"]:disabled' in blob
    assert _contrast_ratio("#115E59", "#B6E3DF") >= 4.5
    assert _contrast_ratio("#1E293B", "#E2E8F0") >= 4.5


def _srgb_channel(value: int) -> float:
    channel = value / 255.0
    if channel <= 0.03928:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _hex_luminance(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    red = int(raw[0:2], 16)
    green = int(raw[2:4], 16)
    blue = int(raw[4:6], 16)
    return (
        0.2126 * _srgb_channel(red)
        + 0.7152 * _srgb_channel(green)
        + 0.0722 * _srgb_channel(blue)
    )


def _contrast_ratio(foreground: str, background: str) -> float:
    lighter = max(_hex_luminance(foreground), _hex_luminance(background))
    darker = min(_hex_luminance(foreground), _hex_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _lock_state() -> dict:
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_INTAKE_STEP] = 2
    state[STATE_INTAKE_RESULT] = None
    state[STATE_INTAKE_VALIDATION_REQUESTED] = True
    state[STATE_INTAKE_VALIDATION_RUNNING] = False
    state[STATE_INTAKE_VALIDATION_ERROR] = None
    return state


def _execute(state: dict, **kwargs):
    return execute_intake_validation(
        state,
        table=object(),
        mapping=object(),
        metadata=object(),
        committed={},
        ubn="",
        fingerprint="",
        doc_id="doc",
        unexpected_error=t("intake.validate.unexpected_error", ZH),
        **kwargs,
    )


def test_non_intake_error_clears_lock_and_stays_on_page(monkeypatch) -> None:
    state = _lock_state()

    def _boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        "carbon_ledger.ui.intake_validation.build_and_validate_intake",
        _boom,
    )
    outcome = _execute(state)
    assert outcome == OUTCOME_UNEXPECTED
    assert state[STATE_INTAKE_VALIDATION_RUNNING] is False
    assert state[STATE_INTAKE_VALIDATION_REQUESTED] is False
    assert state[STATE_INTAKE_STEP] == 2
    assert state[STATE_INTAKE_RESULT] is None
    assert state[STATE_INTAKE_VALIDATION_ERROR] == t(
        "intake.validate.unexpected_error", ZH
    )


def test_provenance_append_failure_does_not_escape_recovery(monkeypatch) -> None:
    state = _lock_state()

    def _intake_boom(*args, **kwargs):
        del args, kwargs
        raise IntakeError("validation_failed", "column mapping invalid")

    def _provenance_boom(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("provenance store unavailable")

    monkeypatch.setattr(
        "carbon_ledger.ui.intake_validation.build_and_validate_intake",
        _intake_boom,
    )
    monkeypatch.setattr(
        "carbon_ledger.ui.intake_validation.append_provenance_event",
        _provenance_boom,
    )
    outcome = _execute(state)
    assert outcome == OUTCOME_UNEXPECTED
    assert state[STATE_INTAKE_VALIDATION_RUNNING] is False
    assert state[STATE_INTAKE_VALIDATION_REQUESTED] is False
    assert state[STATE_INTAKE_STEP] == 2
    assert state[STATE_INTAKE_RESULT] is None
    assert state[STATE_INTAKE_VALIDATION_ERROR] == t(
        "intake.validate.unexpected_error", ZH
    )


def test_stale_running_state_is_recoverable(monkeypatch) -> None:
    state = _lock_state()
    state[STATE_INTAKE_VALIDATION_RUNNING] = True
    state[STATE_INTAKE_VALIDATION_REQUESTED] = False
    assert recover_stale_intake_validation(state) is True
    assert state[STATE_INTAKE_VALIDATION_RUNNING] is False
    state[STATE_INTAKE_VALIDATION_REQUESTED] = True
    sentinel = object()
    monkeypatch.setattr(
        "carbon_ledger.ui.intake_validation.build_and_validate_intake",
        lambda *args, **kwargs: sentinel,
    )
    monkeypatch.setattr(
        "carbon_ledger.ui.intake_validation.hold_unknown_context_rows",
        lambda validated, mapping: validated,
    )
    outcome = _execute(state)
    assert outcome == OUTCOME_OK
    assert state[STATE_INTAKE_VALIDATION_RUNNING] is False
    assert state[STATE_INTAKE_VALIDATION_REQUESTED] is False
    assert state[STATE_INTAKE_VALIDATION_ERROR] is None
    assert state[STATE_INTAKE_STEP] == 3
    assert state[STATE_INTAKE_RESULT] is sentinel


def test_rerun_interrupt_still_clears_running_flag(monkeypatch) -> None:
    state = _lock_state()

    class _RerunInterrupt(BaseException):
        pass

    def _boom(*args, **kwargs):
        del args, kwargs
        raise _RerunInterrupt()

    monkeypatch.setattr(
        "carbon_ledger.ui.intake_validation.build_and_validate_intake",
        _boom,
    )
    with pytest.raises(_RerunInterrupt):
        _execute(state)
    assert state[STATE_INTAKE_VALIDATION_RUNNING] is False
