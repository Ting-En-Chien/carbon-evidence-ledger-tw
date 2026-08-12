"""Data Intake — Phase 9A structured company-file wizard."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from carbon_ledger.domain import ACTIVITY_TYPES, SUPPORTED_UNITS
from carbon_ledger.intake import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    ColumnMapping,
    FieldSuggestion,
    IntakeError,
    IntakeMetadata,
    blank_template_csv_bytes,
    build_and_validate_intake,
    default_value_maps,
    detect_header_row,
    example_csv_bytes,
    example_preview_rows,
    list_xlsx_sheet_names,
    load_raw_tabular_frame,
    parse_uploaded_table,
    rank_xlsx_worksheets,
    reference_only_columns,
    suggest_column_mapping_with_confidence,
    worksheet_detection_labels,
    year_month_transform_preview,
)
from carbon_ledger.ui.components import (
    inject_design_system,
    render_kpi_row,
    render_page_header,
    render_section_header,
    render_upload_journey,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import execute_analysis_with_progress
from carbon_ledger.ui.state import (
    STATE_INTAKE_BYTES,
    STATE_INTAKE_FILE_HASH,
    STATE_INTAKE_FILE_NAME,
    STATE_INTAKE_HEADER_CONFIRMED,
    STATE_INTAKE_HEADER_ROW,
    STATE_INTAKE_MAPPING,
    STATE_INTAKE_METADATA,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_SHEET,
    STATE_INTAKE_SHEET_CONFIRMED,
    STATE_INTAKE_SHOW_MAPPING_EDITOR,
    STATE_INTAKE_STEP,
    STATE_INTAKE_TABLE,
    STATE_INTAKE_YEAR_MONTH_CONFIRMED,
    clear_intake_state,
    get_adapter_flags,
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

INTERPRET_FIELD_ORDER = (
    "activity_type",
    "activity_value",
    "unit",
    "site_id",
    "year_month",
    "activity_start_date",
    "activity_end_date",
)


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


def _confidence_caption(confidence: str) -> str:
    if confidence == CONFIDENCE_HIGH:
        return t("intake.confidence_high", lang)
    if confidence == CONFIDENCE_MEDIUM:
        return t("intake.confidence_medium", lang)
    return t("intake.confidence_low", lang)


def _column_index(options: list[str], preferred: str, *, allow_preselect: bool) -> int:
    if allow_preselect and preferred and preferred in options:
        return options.index(preferred)
    return 0


def _action_button(
    label: str,
    help_text: str,
    *,
    key: str,
    primary: bool = False,
) -> bool:
    st.caption(help_text)
    return st.button(
        label,
        type="primary" if primary else "secondary",
        key=key,
    )


def _suggestion(
    detailed: dict[str, FieldSuggestion],
    field_name: str,
) -> FieldSuggestion:
    return detailed.get(
        field_name,
        FieldSuggestion(field_name, "", CONFIDENCE_LOW),
    )


def _usable_suggestion(suggestion: FieldSuggestion) -> bool:
    return bool(suggestion.source_column) and suggestion.confidence in {
        CONFIDENCE_HIGH,
        CONFIDENCE_MEDIUM,
    }


def _required_suggestions_ready(detailed: dict[str, FieldSuggestion]) -> bool:
    return all(
        _usable_suggestion(_suggestion(detailed, field_name))
        for field_name in ("activity_type", "activity_value", "unit")
    )


def _sample_year_month_value(table: Any, column: str) -> Any | None:
    if not column or column not in table.frame.columns:
        return None
    for item in table.frame[column].tolist():
        if item is not None and str(item).strip():
            return item
    return None


def _default_date_mode(detailed: dict[str, FieldSuggestion]) -> str:
    ym = _suggestion(detailed, "year_month")
    start = _suggestion(detailed, "activity_start_date")
    end = _suggestion(detailed, "activity_end_date")
    if (
        _usable_suggestion(ym)
        and not (
            _usable_suggestion(start)
            and _usable_suggestion(end)
        )
    ):
        return "year_month"
    if _usable_suggestion(start) and _usable_suggestion(end):
        return "file"
    return "period"


def _render_natural_interpretation(
    table: Any,
    detailed: dict[str, FieldSuggestion],
) -> None:
    st.markdown(f"### {t('intake.interpret.title', lang)}")
    st.markdown(t("intake.interpret.intro", lang))
    for field_name in INTERPRET_FIELD_ORDER:
        suggestion = _suggestion(detailed, field_name)
        if not _usable_suggestion(suggestion):
            continue
        column = suggestion.source_column
        st.markdown(f"• 「{column}」")
        if field_name == "year_month":
            sample = _sample_year_month_value(table, column)
            example = str(sample).strip() if sample is not None else "2025-01"
            start_text = "2025-01-01"
            end_text = "2025-01-31"
            if sample is not None:
                try:
                    preview = year_month_transform_preview(sample)
                    example = preview["source"]
                    start_text = preview["activity_start_date"]
                    end_text = preview["activity_end_date"]
                except ValueError:
                    pass
            body = t(
                "intake.interpret.year_month",
                lang,
                example=example,
                start=start_text,
                end=end_text,
            )
            st.markdown(body.replace("\n", "  \n"))
        else:
            key = {
                "activity_type": "intake.interpret.activity_type",
                "activity_value": "intake.interpret.activity_value",
                "unit": "intake.interpret.unit",
                "site_id": "intake.interpret.site_id",
                "activity_start_date": "intake.interpret.start",
                "activity_end_date": "intake.interpret.end",
            }.get(field_name)
            if key:
                st.markdown(t(key, lang))


def _mapping_from_suggestions(
    table: Any,
    detailed: dict[str, FieldSuggestion],
) -> ColumnMapping:
    date_mode = _default_date_mode(detailed)
    activity_type_column = _suggestion(detailed, "activity_type").source_column
    activity_value_column = _suggestion(detailed, "activity_value").source_column
    unit_column = _suggestion(detailed, "unit").source_column
    site_column = _suggestion(detailed, "site_id").source_column
    year_month_column = _suggestion(detailed, "year_month").source_column
    start_date_column = _suggestion(detailed, "activity_start_date").source_column
    end_date_column = _suggestion(detailed, "activity_end_date").source_column

    use_year_month = date_mode == "year_month"
    use_file_dates = date_mode == "file"
    period_start = date(2024, 1, 1) if date_mode == "period" else None
    period_end = date(2024, 1, 31) if date_mode == "period" else None

    draft = ColumnMapping(
        activity_type_column=activity_type_column,
        activity_value_column=activity_value_column,
        unit_column=unit_column,
        site_column=site_column if _usable_suggestion(
            _suggestion(detailed, "site_id")
        ) else "",
        use_file_dates=use_file_dates,
        use_year_month=use_year_month,
        year_month_column=year_month_column if use_year_month else "",
        year_month_confirmed=use_year_month,
        start_date_column=start_date_column if use_file_dates else "",
        end_date_column=end_date_column if use_file_dates else "",
        period_start=period_start,
        period_end=period_end,
    )
    activity_map, unit_map = default_value_maps(table, draft)
    draft.activity_type_value_map = activity_map
    draft.unit_value_map = unit_map
    return draft


def _default_metadata(table: Any) -> IntakeMetadata:
    return IntakeMetadata(
        source_name=table.file_name,
        site_id="site_main",
        document_date=date(2024, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="ui_intake",
        ingested_at=pd.Timestamp.now(tz="UTC"),
    )


render_page_header(t("intake.title", lang), t("intake.subtitle", lang))
st.markdown(t("intake.intro", lang).replace("\n", "  \n"))
render_upload_journey(
    [
        ("1", t("intake.journey.upload", lang)),
        ("2", t("intake.journey.confirm", lang)),
        ("3", t("intake.journey.results", lang)),
    ]
)
st.caption(t("intake.demo_notice", lang))

step = int(st.session_state.get(STATE_INTAKE_STEP, 1) or 1)
_step_indicator(step)

st.write("")
render_section_header(t("intake.upload_priority", lang), t("intake.upload_help", lang))
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
with st.expander(t("intake.advanced_canonical", lang)):
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
    sheet_confirmed = bool(st.session_state.get(STATE_INTAKE_SHEET_CONFIRMED))
    extension = file_name.lower().rsplit(".", 1)[-1]
    if extension == "xlsx":
        try:
            sheets = list_xlsx_sheet_names(file_bytes)
            ranked = rank_xlsx_worksheets(file_bytes)
        except Exception:
            st.error(t("intake.err_unsupported", lang))
            st.stop()
        if not sheets or not ranked:
            st.error(t("intake.err_unsupported", lang))
            st.stop()

        suggested = ranked[0]
        if len(sheets) > 1 and not sheet_confirmed:
            st.markdown(f"**{t('intake.suggest_sheet_title', lang)}**")
            st.markdown(f"### {suggested.sheet_name}")
            st.markdown(t("intake.detect_result", lang))
            for label in worksheet_detection_labels(suggested):
                st.markdown(f"- {label}")
            btn_cols = st.columns(2)
            with btn_cols[0]:
                if _action_button(
                    t("intake.use_suggested_sheet", lang),
                    t("intake.btn.use_sheet_help", lang),
                    key="intake_use_suggested_sheet",
                    primary=True,
                ):
                    st.session_state[STATE_INTAKE_SHEET] = suggested.sheet_name
                    st.session_state[STATE_INTAKE_SHEET_CONFIRMED] = True
                    st.rerun()
            with btn_cols[1]:
                if _action_button(
                    t("intake.choose_other_sheet", lang),
                    t("intake.btn.other_sheet_help", lang),
                    key="intake_choose_other_sheet",
                ):
                    st.session_state["intake_sheet_picker_open"] = True
            if st.session_state.get("intake_sheet_picker_open"):
                default_index = (
                    sheets.index(sheet_name) if sheet_name in sheets else 0
                )
                picked = st.selectbox(
                    t("intake.sheet_label", lang),
                    options=sheets,
                    index=default_index,
                    key="intake_sheet_selector",
                )
                if _action_button(
                    t("intake.header_confirm", lang),
                    t("intake.btn.header_help", lang),
                    key="intake_confirm_sheet",
                    primary=True,
                ):
                    st.session_state[STATE_INTAKE_SHEET] = picked
                    st.session_state[STATE_INTAKE_SHEET_CONFIRMED] = True
                    st.session_state["intake_sheet_picker_open"] = False
                    st.rerun()
            st.stop()

        if not sheet_confirmed:
            st.session_state[STATE_INTAKE_SHEET] = suggested.sheet_name
            st.session_state[STATE_INTAKE_SHEET_CONFIRMED] = True
            sheet_name = suggested.sheet_name
        else:
            sheet_name = (
                st.session_state.get(STATE_INTAKE_SHEET) or suggested.sheet_name
            )

    header_row = st.session_state.get(STATE_INTAKE_HEADER_ROW)
    header_confirmed = bool(st.session_state.get(STATE_INTAKE_HEADER_CONFIRMED))

    if not header_confirmed:
        try:
            raw = load_raw_tabular_frame(
                data=file_bytes,
                file_extension=extension,
                sheet_name=sheet_name,
            )
            detection = detect_header_row(raw)
        except Exception:
            st.error(t("intake.err_unsupported", lang))
            st.stop()

        if detection.needs_confirmation:
            st.markdown(f"**{t('intake.header_ask', lang)}**")
            options = list(detection.candidate_rows) or [
                detection.header_row_index
            ]
            labels = {
                idx: t("intake.header_row_label", lang, row=idx + 1)
                for idx in options
            }
            selected_idx = st.radio(
                t("intake.header_ask", lang),
                options=options,
                index=options.index(detection.header_row_index)
                if detection.header_row_index in options
                else 0,
                format_func=lambda idx: labels.get(idx, str(idx + 1)),
                key="intake_header_radio",
            )
            preview_rows = []
            for idx in options[:5]:
                if idx < len(raw):
                    preview_rows.append(
                        {
                            t("intake.header_row_label", lang, row=idx + 1): " | ".join(
                                str(v) if v is not None else ""
                                for v in raw.iloc[idx].tolist()[:8]
                            )
                        }
                    )
            if preview_rows:
                st.dataframe(
                    pd.DataFrame(preview_rows),
                    hide_index=True,
                    width="stretch",
                )
            if _action_button(
                t("intake.header_confirm", lang),
                t("intake.btn.header_help", lang),
                key="intake_confirm_header",
                primary=True,
            ):
                st.session_state[STATE_INTAKE_HEADER_ROW] = int(selected_idx)
                st.session_state[STATE_INTAKE_HEADER_CONFIRMED] = True
                st.rerun()
            st.stop()

        st.session_state[STATE_INTAKE_HEADER_ROW] = detection.header_row_index
        st.session_state[STATE_INTAKE_HEADER_CONFIRMED] = True
        header_row = detection.header_row_index

    try:
        table = parse_uploaded_table(
            file_name=file_name,
            data=file_bytes,
            sheet_name=sheet_name,
            header_row=int(header_row) if header_row is not None else None,
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
    st.caption(
        t("intake.header_row_label", lang, row=table.header_row_index + 1)
    )
    st.dataframe(table.frame.head(20), hide_index=True, width="stretch")

    if _action_button(
        t("intake.continue_mapping", lang),
        t("intake.btn.continue_help", lang),
        key="intake_continue_to_interpret",
        primary=True,
    ):
        st.session_state[STATE_INTAKE_STEP] = 2
        st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = False
        st.rerun()

table = st.session_state.get(STATE_INTAKE_TABLE)
if table is None:
    st.stop()

if int(st.session_state.get(STATE_INTAKE_STEP, 1)) < 2:
    st.stop()

result = st.session_state.get(STATE_INTAKE_RESULT)
detailed = suggest_column_mapping_with_confidence(list(table.columns))
show_editor = bool(st.session_state.get(STATE_INTAKE_SHOW_MAPPING_EDITOR))

# Confirmation / editor only while there is no validated result yet.
if result is None:
    st.write("")
    render_section_header(t("intake.step2", lang))
    st.info(t("intake.no_rename", lang))
    ready = _required_suggestions_ready(detailed)
    if ready and not show_editor:
        st.markdown(
            f'<div class="cel-understood cel-reveal cel-reveal-1">'
            f'<span class="cel-check" aria-hidden="true">✓</span>'
            f"{t('intake.understood', lang)}"
            f"</div>",
            unsafe_allow_html=True,
        )
    _render_natural_interpretation(table, detailed)

    ref_cols = reference_only_columns(list(table.columns))
    if ref_cols:
        st.caption(t("intake.reference_only_note", lang))

    if not show_editor:
        st.markdown(f"**{t('intake.interpret.ask', lang)}**")
        if not ready:
            st.warning(t("intake.interpret.need_help", lang))
            if _action_button(
                t("intake.btn.fix", lang),
                t("intake.btn.fix_help", lang),
                key="intake_fix_required",
                primary=True,
            ):
                st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = True
                st.rerun()
            st.stop()

        btn_cols = st.columns(2)
        with btn_cols[0]:
            if _action_button(
                t("intake.btn.accept", lang),
                t("intake.btn.accept_help", lang),
                key="intake_accept_interpretation",
                primary=True,
            ):
                mapping = _mapping_from_suggestions(table, detailed)
                metadata = _default_metadata(table)
                st.session_state[STATE_INTAKE_MAPPING] = mapping
                st.session_state[STATE_INTAKE_METADATA] = metadata
                st.session_state[STATE_INTAKE_YEAR_MONTH_CONFIRMED] = (
                    mapping.year_month_confirmed
                )
                try:
                    validated = build_and_validate_intake(table, mapping, metadata)
                except IntakeError as exc:
                    st.error(exc.message)
                    st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = True
                    st.stop()
                st.session_state[STATE_INTAKE_RESULT] = validated
                st.session_state[STATE_INTAKE_STEP] = 4
                st.rerun()
        with btn_cols[1]:
            if _action_button(
                t("intake.btn.fix", lang),
                t("intake.btn.fix_help", lang),
                key="intake_fix_interpretation",
            ):
                st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = True
                st.rerun()
        st.stop()

    # Technical mapping controls — only after the beginner asks to fix.
    column_options = [t("intake.choose", lang)] + list(table.columns)

    def _select_for(
        field_name: str,
        label_key: str,
        widget_key: str,
        *,
        required: bool = False,
    ) -> str:
        suggestion = _suggestion(detailed, field_name)
        preferred = suggestion.source_column
        confidence = suggestion.confidence
        allow_preselect = confidence in {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM}
        if required and confidence == CONFIDENCE_LOW:
            st.caption(t("intake.mapping_unknown", lang))
        selected = st.selectbox(
            t(label_key, lang),
            options=column_options,
            index=_column_index(
                column_options,
                preferred,
                allow_preselect=allow_preselect,
            ),
            key=widget_key,
            help=_confidence_caption(confidence),
        )
        choose_label = t("intake.choose", lang)
        return "" if selected == choose_label else selected

    map_cols = st.columns(3)
    with map_cols[0]:
        activity_type_column = _select_for(
            "activity_type",
            "intake.map_activity_type",
            "intake_map_activity_type",
            required=True,
        )
    with map_cols[1]:
        activity_value_column = _select_for(
            "activity_value",
            "intake.map_activity_value",
            "intake_map_activity_value",
            required=True,
        )
    with map_cols[2]:
        unit_column = _select_for(
            "unit",
            "intake.map_unit",
            "intake_map_unit",
            required=True,
        )

    site_column = _select_for(
        "site_id",
        "intake.map_site",
        "intake_map_site",
    )

    default_date_mode = _default_date_mode(detailed)
    if "intake_date_mode" not in st.session_state:
        st.session_state["intake_date_mode"] = default_date_mode

    date_mode = st.radio(
        label=(
            t("intake.dates_in_file", lang)
            + " / "
            + t("intake.dates_year_month", lang)
            + " / "
            + t("intake.dates_period", lang)
        ),
        options=["file", "year_month", "period"],
        format_func=lambda key: {
            "file": t("intake.dates_in_file", lang),
            "year_month": t("intake.dates_year_month", lang),
            "period": t("intake.dates_period", lang),
        }[key],
        horizontal=True,
        key="intake_date_mode",
    )

    use_file_dates = date_mode == "file"
    use_year_month = date_mode == "year_month"
    start_date_column = ""
    end_date_column = ""
    year_month_column = ""
    period_start: date | None = None
    period_end: date | None = None
    year_month_confirmed = bool(
        st.session_state.get(STATE_INTAKE_YEAR_MONTH_CONFIRMED, False)
    )

    if use_file_dates:
        date_cols = st.columns(2)
        with date_cols[0]:
            start_date_column = _select_for(
                "activity_start_date",
                "intake.map_start",
                "intake_map_start",
            )
        with date_cols[1]:
            end_date_column = _select_for(
                "activity_end_date",
                "intake.map_end",
                "intake_map_end",
            )
    elif use_year_month:
        year_month_column = _select_for(
            "year_month",
            "intake.map_year_month",
            "intake_map_year_month",
        )
        if year_month_column and year_month_column in table.frame.columns:
            sample_value = _sample_year_month_value(table, year_month_column)
            if sample_value is not None:
                try:
                    preview = year_month_transform_preview(sample_value)
                    st.markdown(f"**{year_month_column}**")
                    st.write(preview["source"])
                    st.markdown(
                        f"**{t('intake.year_month_preview_title', lang)}**"
                    )
                    st.write(
                        f"{t('intake.field.start', lang)}: "
                        f"{preview['activity_start_date']}"
                    )
                    st.write(
                        f"{t('intake.field.end', lang)}: "
                        f"{preview['activity_end_date']}"
                    )
                except ValueError:
                    st.warning(t("intake.mapping_unknown", lang))
            year_month_confirmed = st.checkbox(
                t("intake.year_month_confirm", lang),
                value=year_month_confirmed,
                key="intake_year_month_confirm_box",
            )
            st.session_state[STATE_INTAKE_YEAR_MONTH_CONFIRMED] = (
                year_month_confirmed
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

    draft_mapping = ColumnMapping(
        activity_type_column=activity_type_column,
        activity_value_column=activity_value_column,
        unit_column=unit_column,
        site_column=site_column,
        use_file_dates=use_file_dates,
        use_year_month=use_year_month,
        year_month_column=year_month_column,
        year_month_confirmed=year_month_confirmed,
        start_date_column=start_date_column,
        end_date_column=end_date_column,
        period_start=period_start,
        period_end=period_end,
    )
    suggested_activity_map, suggested_unit_map = default_value_maps(
        table, draft_mapping
    )

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
    choose_label = t("intake.choose", lang)
    if unit_column:
        for source_value, suggestion in suggested_unit_map.items():
            default_unit = (
                suggestion if suggestion in UNIT_OPTIONS else choose_label
            )
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
            help=t("intake.map_site", lang),
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

    with st.expander(t("intake.advanced_canonical", lang)):
        st.caption(
            "activity_type / activity_value / unit / "
            "activity_start_date / activity_end_date / site_id"
        )

    mapping = ColumnMapping(
        activity_type_column=activity_type_column,
        activity_value_column=activity_value_column,
        unit_column=unit_column,
        site_column=site_column,
        use_file_dates=use_file_dates,
        use_year_month=use_year_month,
        year_month_column=year_month_column,
        year_month_confirmed=year_month_confirmed,
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

    if _action_button(
        t("intake.run_validation", lang),
        t("intake.btn.validate_help", lang),
        key="intake_run_validation",
        primary=True,
    ):
        try:
            validated = build_and_validate_intake(table, mapping, metadata)
        except IntakeError as exc:
            st.error(exc.message)
            st.stop()
        st.session_state[STATE_INTAKE_RESULT] = validated
        st.session_state[STATE_INTAKE_STEP] = 4
        st.rerun()
    st.stop()

# Results
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
            "site_id",
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
            "site_id": t("intake.field.site_id", lang),
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

if result.accepted_count > 0:
    st.write("")
    st.markdown(f"### {t('intake.ready_title', lang)}")
    st.markdown(t("intake.ready_body", lang, count=result.accepted_count))
    st.markdown(t("intake.ready_next", lang))
    cta_cols = st.columns([2, 1])
    with cta_cols[0]:
        if st.button(
            t("intake.start_analysis", lang),
            type="primary",
            use_container_width=True,
            key="intake_start_uploaded_analysis",
        ):
            flags = get_adapter_flags(st.session_state)
            try:
                execute_analysis_with_progress(
                    st.session_state,
                    lang=lang,
                    uploaded_mode=True,
                    include_ghg=flags["include_ghg"],
                    include_cbam=flags["include_cbam"],
                    include_ifrs_s2=flags["include_ifrs_s2"],
                )
            except Exception:
                st.error(t("error.analysis_failed", lang))
                st.stop()
            st.switch_page("app_pages/dashboard.py")
    with cta_cols[1]:
        if st.button(
            t("intake.back_edit", lang),
            use_container_width=True,
            key="intake_back_edit_data",
        ):
            st.session_state[STATE_INTAKE_STEP] = 3
            st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = True
            st.rerun()
else:
    st.info(t("intake.next_phase", lang))
