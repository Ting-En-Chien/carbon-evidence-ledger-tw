"""Data Intake — Phase 9A structured company-file wizard."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from carbon_ledger.domain import ACTIVITY_TYPES, SUPPORTED_UNITS
from carbon_ledger.intake import (
    ColumnMapping,
    IntakeError,
    IntakeMetadata,
    blank_template_csv_bytes,
    build_and_validate_intake,
    default_value_maps,
    example_csv_bytes,
    example_preview_rows,
    list_xlsx_sheet_names,
    parse_uploaded_table,
    suggest_column_mapping,
)
from carbon_ledger.ui.components import (
    inject_design_system,
    render_kpi_row,
    render_page_header,
    render_section_header,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_INTAKE_BYTES,
    STATE_INTAKE_FILE_HASH,
    STATE_INTAKE_FILE_NAME,
    STATE_INTAKE_MAPPING,
    STATE_INTAKE_METADATA,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_SHEET,
    STATE_INTAKE_STEP,
    STATE_INTAKE_TABLE,
    clear_intake_state,
    get_language,
)

inject_design_system()
lang = get_language(st.session_state)

QUALITY_OPTIONS = [
    ("unknown", t("intake.quality.unknown", lang)),
    ("primary", t("intake.quality.primary", lang)),
    ("secondary", t("intake.quality.secondary", lang)),
    ("estimated", t("intake.quality.estimated", lang)),
]
QUALITY_LABEL_TO_CODE = {label: code for code, label in QUALITY_OPTIONS}

ACTIVITY_OPTIONS = [t("intake.choose", lang)] + [
    f"{t(f'activity.{code}', lang)} / {code}" for code in ACTIVITY_TYPES
]
ACTIVITY_LABEL_TO_CODE = {
    f"{t(f'activity.{code}', lang)} / {code}": code for code in ACTIVITY_TYPES
}

UNIT_OPTIONS = [t("intake.choose", lang)] + list(SUPPORTED_UNITS)


def _step_indicator(active: int) -> None:
    labels = [
        t("intake.step1", lang),
        t("intake.step2", lang),
        t("intake.step3", lang),
        t("intake.step4", lang),
    ]
    cols = st.columns(4)
    for index, (column, label) in enumerate(zip(cols, labels, strict=True), start=1):
        with column:
            if index == active:
                st.markdown(f"**{label}**")
            else:
                st.caption(label)


def _reset_for_new_file() -> None:
    clear_intake_state(st.session_state)
    st.session_state[STATE_INTAKE_STEP] = 1


def _activity_select_label(code: str) -> str:
    if not code:
        return t("intake.choose", lang)
    return f"{t(f'activity.{code}', lang)} / {code}"


render_page_header(t("intake.title", lang), t("intake.subtitle", lang))
st.info(t("intake.demo_notice", lang))
st.markdown(t("intake.intro", lang).replace("\n", "  \n"))

step = int(st.session_state.get(STATE_INTAKE_STEP, 1) or 1)
_step_indicator(step)

st.write("")
render_section_header(t("intake.step1", lang))
uploaded = st.file_uploader(
    t("intake.upload_label", lang),
    type=["csv", "xlsx"],
    help=t("intake.upload_help", lang),
    key="intake_file_uploader",
)

dl_cols = st.columns(2)
with dl_cols[0]:
    st.download_button(
        label=t("intake.template_button", lang),
        data=blank_template_csv_bytes(),
        file_name="carbon_evidence_intake_template.csv",
        mime="text/csv",
        key="intake_template_download",
    )
with dl_cols[1]:
    st.download_button(
        label=t("intake.example_button", lang),
        data=example_csv_bytes(),
        file_name="carbon_evidence_intake_example.csv",
        mime="text/csv",
        key="intake_example_download",
    )

st.caption(t("intake.example_label", lang))
st.caption(t("intake.col_help_activity_type", lang))
st.caption(t("intake.col_help_activity_value", lang))
st.caption(t("intake.col_help_unit", lang))
st.caption(t("intake.col_help_start", lang))
st.caption(t("intake.col_help_end", lang))
st.dataframe(example_preview_rows(), hide_index=True, width="stretch")

if uploaded is not None:
    file_bytes = uploaded.getvalue()
    file_name = uploaded.name
    previous_hash = st.session_state.get(STATE_INTAKE_FILE_HASH)
    try:
        from carbon_ledger.intake import compute_bytes_sha256, validate_upload_bytes

        validate_upload_bytes(file_name, file_bytes)
        file_hash = compute_bytes_sha256(file_bytes)
    except IntakeError as exc:
        if exc.code == "FILE_TOO_LARGE":
            st.error(t("intake.err_too_large", lang))
        elif exc.code == "INVALID_ENCODING":
            st.error(t("intake.err_encoding", lang))
        else:
            st.error(t("intake.err_unsupported", lang))
        st.stop()

    if previous_hash and previous_hash != file_hash:
        _reset_for_new_file()

    st.session_state[STATE_INTAKE_BYTES] = file_bytes
    st.session_state[STATE_INTAKE_FILE_HASH] = file_hash
    st.session_state[STATE_INTAKE_FILE_NAME] = file_name

    sheet_name = st.session_state.get(STATE_INTAKE_SHEET)
    extension = file_name.lower().rsplit(".", 1)[-1]
    if extension == "xlsx":
        try:
            sheets = list_xlsx_sheet_names(file_bytes)
        except Exception:
            st.error(t("intake.err_unsupported", lang))
            st.stop()
        if not sheets:
            st.error(t("intake.err_unsupported", lang))
            st.stop()
        default_index = sheets.index(sheet_name) if sheet_name in sheets else 0
        sheet_name = st.selectbox(
            t("intake.sheet_label", lang),
            options=sheets,
            index=default_index,
            key="intake_sheet_selector",
        )
        st.session_state[STATE_INTAKE_SHEET] = sheet_name

    try:
        table = parse_uploaded_table(
            file_name=file_name,
            data=file_bytes,
            sheet_name=sheet_name,
        )
    except IntakeError as exc:
        if exc.code == "INVALID_ENCODING":
            st.error(t("intake.err_encoding", lang))
        elif exc.code == "FILE_TOO_LARGE":
            st.error(t("intake.err_too_large", lang))
        else:
            st.error(t("intake.err_unsupported", lang))
        st.stop()

    st.session_state[STATE_INTAKE_TABLE] = table
    render_section_header(t("intake.preview_title", lang))
    meta_cols = st.columns(4)
    with meta_cols[0]:
        st.markdown(f"**{t('intake.file_name', lang)}**")
        st.write(table.file_name)
    with meta_cols[1]:
        st.markdown(f"**{t('intake.file_type', lang)}**")
        st.write(table.file_extension)
    with meta_cols[2]:
        st.markdown(f"**{t('intake.row_count', lang)}**")
        st.write(len(table.frame))
    with meta_cols[3]:
        st.markdown(f"**{t('intake.col_count', lang)}**")
        st.write(len(table.columns))
    if table.sheet_name:
        st.caption(f"{t('intake.sheet_name', lang)}: {table.sheet_name}")
    st.dataframe(table.frame.head(20), hide_index=True, width="stretch")

    if st.button(t("intake.continue_mapping", lang), type="primary"):
        st.session_state[STATE_INTAKE_STEP] = 2
        st.rerun()

table = st.session_state.get(STATE_INTAKE_TABLE)
if table is None:
    st.stop()

if int(st.session_state.get(STATE_INTAKE_STEP, 1)) < 2:
    st.stop()

st.write("")
render_section_header(t("intake.step2", lang))
suggestions = suggest_column_mapping(list(table.columns))
column_options = [t("intake.choose", lang)] + list(table.columns)


def _column_index(preferred: str) -> int:
    if preferred and preferred in table.columns:
        return column_options.index(preferred)
    return 0


map_cols = st.columns(3)
with map_cols[0]:
    activity_type_col = st.selectbox(
        t("intake.map_activity_type", lang),
        options=column_options,
        index=_column_index(suggestions.get("activity_type", "")),
        key="intake_map_activity_type",
    )
with map_cols[1]:
    activity_value_col = st.selectbox(
        t("intake.map_activity_value", lang),
        options=column_options,
        index=_column_index(suggestions.get("activity_value", "")),
        key="intake_map_activity_value",
    )
with map_cols[2]:
    unit_col = st.selectbox(
        t("intake.map_unit", lang),
        options=column_options,
        index=_column_index(suggestions.get("unit", "")),
        key="intake_map_unit",
    )

date_mode = st.radio(
    label=t("intake.dates_in_file", lang) + " / " + t("intake.dates_period", lang),
    options=["file", "period"],
    format_func=lambda key: (
        t("intake.dates_in_file", lang)
        if key == "file"
        else t("intake.dates_period", lang)
    ),
    horizontal=True,
    key="intake_date_mode",
)
use_file_dates = date_mode == "file"

start_col = ""
end_col = ""
period_start: date | None = None
period_end: date | None = None
if use_file_dates:
    date_cols = st.columns(2)
    with date_cols[0]:
        start_col = st.selectbox(
            t("intake.map_start", lang),
            options=column_options,
            index=_column_index(suggestions.get("activity_start_date", "")),
            key="intake_map_start",
        )
    with date_cols[1]:
        end_col = st.selectbox(
            t("intake.map_end", lang),
            options=column_options,
            index=_column_index(suggestions.get("activity_end_date", "")),
            key="intake_map_end",
        )
else:
    period_cols = st.columns(2)
    with period_cols[0]:
        period_start = st.date_input(
            t("intake.period_start", lang),
            value=date(2024, 1, 1),
            key="intake_period_start",
        )
    with period_cols[1]:
        period_end = st.date_input(
            t("intake.period_end", lang),
            value=date(2024, 1, 31),
            key="intake_period_end",
        )

choose_label = t("intake.choose", lang)
activity_type_column = "" if activity_type_col == choose_label else activity_type_col
activity_value_column = (
    "" if activity_value_col == choose_label else activity_value_col
)
unit_column = "" if unit_col == choose_label else unit_col
start_date_column = "" if start_col == choose_label else start_col
end_date_column = "" if end_col == choose_label else end_col

draft_mapping = ColumnMapping(
    activity_type_column=activity_type_column,
    activity_value_column=activity_value_column,
    unit_column=unit_column,
    use_file_dates=use_file_dates,
    start_date_column=start_date_column,
    end_date_column=end_date_column,
    period_start=period_start,
    period_end=period_end,
)
suggested_activity_map, suggested_unit_map = default_value_maps(table, draft_mapping)

st.markdown(f"**{t('intake.value_map_activity', lang)}**")
activity_type_value_map: dict[str, str] = {}
if activity_type_column:
    for source_value, suggestion in suggested_activity_map.items():
        default_label = _activity_select_label(suggestion)
        index = (
            ACTIVITY_OPTIONS.index(default_label)
            if default_label in ACTIVITY_OPTIONS
            else 0
        )
        selected = st.selectbox(
            source_value,
            options=ACTIVITY_OPTIONS,
            index=index,
            key=f"intake_act_map_{source_value}",
        )
        activity_type_value_map[source_value] = ACTIVITY_LABEL_TO_CODE.get(
            selected, ""
        )

st.markdown(f"**{t('intake.value_map_unit', lang)}**")
unit_value_map: dict[str, str] = {}
if unit_column:
    for source_value, suggestion in suggested_unit_map.items():
        default_unit = suggestion if suggestion in UNIT_OPTIONS else choose_label
        index = UNIT_OPTIONS.index(default_unit)
        selected_unit = st.selectbox(
            source_value,
            options=UNIT_OPTIONS,
            index=index,
            key=f"intake_unit_map_{source_value}",
        )
        unit_value_map[source_value] = (
            "" if selected_unit == choose_label else selected_unit
        )

meta_cols = st.columns(2)
with meta_cols[0]:
    source_name = st.text_input(
        t("intake.source_name", lang),
        value=table.file_name,
        key="intake_source_name",
    )
    site_id = st.text_input(
        t("intake.site_id", lang),
        value="site_main",
        key="intake_site_id",
    )
with meta_cols[1]:
    document_date = st.date_input(
        t("intake.document_date", lang),
        value=date(2024, 1, 31),
        key="intake_document_date",
    )
    quality_label = st.selectbox(
        t("intake.data_quality", lang),
        options=[label for _, label in QUALITY_OPTIONS],
        index=0,
        key="intake_data_quality",
    )

mapping = ColumnMapping(
    activity_type_column=activity_type_column,
    activity_value_column=activity_value_column,
    unit_column=unit_column,
    use_file_dates=use_file_dates,
    start_date_column=start_date_column,
    end_date_column=end_date_column,
    period_start=period_start if isinstance(period_start, date) else None,
    period_end=period_end if isinstance(period_end, date) else None,
    activity_type_value_map=activity_type_value_map,
    unit_value_map=unit_value_map,
)
metadata = IntakeMetadata(
    source_name=source_name.strip() or table.file_name,
    site_id=site_id.strip() or "site_main",
    document_date=document_date
    if isinstance(document_date, date)
    else date(2024, 1, 31),
    data_quality_tier=QUALITY_LABEL_TO_CODE.get(quality_label, "unknown"),
    intake_run_id="ui_intake",
    ingested_at=pd.Timestamp.now(tz="UTC"),
)
st.session_state[STATE_INTAKE_MAPPING] = mapping
st.session_state[STATE_INTAKE_METADATA] = metadata

if st.button(t("intake.run_validation", lang), type="primary"):
    try:
        result = build_and_validate_intake(table, mapping, metadata)
    except IntakeError as exc:
        st.error(exc.message)
        st.stop()
    st.session_state[STATE_INTAKE_RESULT] = result
    st.session_state[STATE_INTAKE_STEP] = 4
    st.rerun()

result = st.session_state.get(STATE_INTAKE_RESULT)
if result is None:
    st.stop()

st.write("")
render_section_header(t("intake.step3", lang))
accepted = result.accepted_activities
if accepted is not None and not accepted.empty:
    preview = accepted[
        [
            "activity_type",
            "activity_value",
            "unit",
            "activity_start_date",
            "activity_end_date",
            "data_quality_tier",
            "human_review_status",
        ]
    ].copy()
    preview["activity_type"] = preview["activity_type"].map(
        lambda code: t(f"activity.{code}", lang)
    )
    preview["human_review_status"] = preview["human_review_status"].map(
        lambda status: "Yes" if status == "needs_review" else "No"
    )
    preview = preview.rename(
        columns={
            "activity_type": t("intake.col.activity", lang),
            "activity_value": t("intake.col.amount", lang),
            "unit": t("intake.col.unit", lang),
            "activity_start_date": t("intake.col.start", lang),
            "activity_end_date": t("intake.col.end", lang),
            "data_quality_tier": t("intake.col.quality", lang),
            "human_review_status": t("intake.col.review", lang),
        }
    )
    st.dataframe(preview, hide_index=True, width="stretch")
    with st.expander(t("intake.advanced", lang)):
        st.dataframe(
            accepted[
                [
                    "record_id",
                    "source_document_id",
                    "source_locator",
                    "record_type",
                    "process_use",
                    "ownership_control",
                    "organizational_boundary_status",
                    "cbam_process_boundary_status",
                ]
            ],
            hide_index=True,
            width="stretch",
        )
else:
    st.warning(t("intake.partial", lang))

st.write("")
render_section_header(t("intake.step4", lang))
render_kpi_row(
    [
        (result.accepted_count, t("intake.result_accepted", lang), "teal"),
        (result.rejected_count, t("intake.result_rejected", lang), "amber"),
        (result.total_count, t("intake.result_total", lang), "blue"),
    ]
)
if result.rejected_count == 0 and result.accepted_count > 0:
    st.success(t("intake.success", lang))
elif result.rejected_count > 0:
    st.warning(t("intake.partial", lang))
    rejected = result.rejected_rows.rename(
        columns={
            "source_row": t("intake.rej.row", lang),
            "field": t("intake.rej.field", lang),
            "issue_message": t("intake.rej.issue", lang),
            "uploaded_value": t("intake.rej.value", lang),
        }
    )
    display_cols = [
        t("intake.rej.row", lang),
        t("intake.rej.field", lang),
        t("intake.rej.issue", lang),
        t("intake.rej.value", lang),
    ]
    st.markdown(f"**{t('intake.rejected_title', lang)}**")
    st.dataframe(rejected[display_cols], hide_index=True, width="stretch")

st.info(t("intake.next_phase", lang))
