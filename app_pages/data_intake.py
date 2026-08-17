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
    blank_template_xlsx_bytes,
    build_and_validate_intake,
    context_confirmations_needed,
    default_value_maps,
    detect_header_row,
    example_preview_customer_rows,
    extract_natural_gas_subtype_from_text,
    list_xlsx_sheet_names,
    load_raw_tabular_frame,
    parse_uploaded_table,
    rank_xlsx_worksheets,
    reference_only_columns,
    suggest_column_mapping_with_confidence,
    summarize_pre_analysis_readiness,
    worksheet_detection_labels,
    year_month_transform_preview,
)
from carbon_ledger.potential_duplicates import (
    DECISION_EXCLUDE_DUPLICATES,
    DECISION_KEEP_ALL,
    decide_potential_duplicate_group,
    decision_to_map_payload,
    groups_from_intake,
    unresolved_potential_duplicate_groups,
)
from carbon_ledger.ui.components import (
    inject_design_system,
    render_kpi_row,
    render_section_header,
)
from carbon_ledger.ui.evidence_workspace import (
    TAB_INTAKE,
    render_evidence_workspace_nav,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_INTAKE_BYTES,
    STATE_INTAKE_DUPLICATE_REVIEW,
    STATE_INTAKE_FILE_HASH,
    STATE_INTAKE_FILE_NAME,
    STATE_INTAKE_HEADER_CONFIRMED,
    STATE_INTAKE_HEADER_ROW,
    STATE_INTAKE_MAPPING,
    STATE_INTAKE_METADATA,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_SHEET,
    STATE_INTAKE_SHEET_CONFIRMED,
    STATE_INTAKE_SHOW_DUPLICATE_REVIEW,
    STATE_INTAKE_SHOW_MAPPING_EDITOR,
    STATE_INTAKE_STEP,
    STATE_INTAKE_TABLE,
    STATE_INTAKE_YEAR_MONTH_CONFIRMED,
    STATE_RUN_UPLOADED_REQUEST,
    clear_analysis_result,
    clear_duplicate_review_state,
    clear_intake_state,
    duplicate_review_blocks_analysis,
    duplicate_review_decisions_from_state,
    get_current_result,
    get_language,
)
from carbon_ledger.ui.view_models import (
    beginner_result_summary,
    customer_schema_label,
    customer_site_display,
    should_show_unresolved_cta,
)

inject_design_system()
lang = get_language(st.session_state)

# Evidence & Data workspace: Data Upload is the default landing view.
st.markdown(
    f"""
    <p class="cel-page-kicker">{t("nav.evidence", lang)}</p>
    <h1 class="cel-page-title">{t("ev.title", lang)}</h1>
    <p class="cel-page-sub">{t("ev.subtitle", lang)}</p>
    """,
    unsafe_allow_html=True,
)
render_evidence_workspace_nav(lang, TAB_INTAKE)
st.caption(t("ev.tab.intake_help", lang))

analyzed = get_current_result(st.session_state)
if analyzed is not None:
    ev_summary = beginner_result_summary(analyzed, lang)
    ev_done = int(ev_summary["calculated"])
    ev_unresolved = int(ev_summary["needs_work"])
    render_section_header(t("ev.status_title", lang))
    st.success("✓ " + t("ev.status_done", lang, done=ev_done))
    if should_show_unresolved_cta(ev_unresolved):
        st.warning(
            "⚠ " + t("dash.issues_banner", lang, count=ev_unresolved)
        )
        if st.button(t("dash.cta.view_problems", lang), key="ev_view_issues"):
            st.switch_page("app_pages/issues_actions.py")
    else:
        st.caption("✓ " + t("dash.no_data_issues", lang))
    act_col, file_col = st.columns(2)
    with act_col:
        if st.button(t("ev.cta.view_activities", lang), key="ev_view_activities"):
            st.switch_page("app_pages/activity_explorer.py")
    with file_col:
        if st.button(t("ev.cta.view_files", lang), key="ev_view_files"):
            st.switch_page("app_pages/evidence_data.py")

with st.expander(t("ev.reuse_title", lang), expanded=False):
    st.caption(t("ev.reuse_help", lang))
st.caption(t("ev.reuse_title", lang))

QUALITY_OPTIONS = [
    ("unknown", t("intake.quality.unknown", lang)),
    ("primary", t("intake.quality.primary", lang)),
    ("secondary", t("intake.quality.secondary", lang)),
    ("estimated", t("intake.quality.estimated", lang)),
]
QUALITY_LABEL_TO_CODE = {label: code for code, label in QUALITY_OPTIONS}

ACTIVITY_OPTIONS = [t("intake.choose", lang)] + [
    t(f"activity.{code}", lang) for code in ACTIVITY_TYPES
]
ACTIVITY_LABEL_TO_CODE = {
    t(f"activity.{code}", lang): code for code in ACTIVITY_TYPES
}

UNIT_OPTIONS = [t("intake.choose", lang)] + list(SUPPORTED_UNITS)

_TEMPLATE_XLSX_BYTES: bytes | None = None
_TEMPLATE_XLSX_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _template_download_payload() -> tuple[bytes, str, str]:
    """Stable bytes for st.download_button across Streamlit reruns."""
    global _TEMPLATE_XLSX_BYTES
    if _TEMPLATE_XLSX_BYTES is None:
        try:
            _TEMPLATE_XLSX_BYTES = blank_template_xlsx_bytes()
        except Exception:  # noqa: BLE001
            return (
                blank_template_csv_bytes(),
                "carbon_evidence_template.csv",
                "text/csv",
            )
    return (
        _TEMPLATE_XLSX_BYTES,
        "carbon_evidence_template.xlsx",
        _TEMPLATE_XLSX_MIME,
    )


INTERPRET_FIELD_ORDER = (
    "activity_type",
    "activity_value",
    "unit",
    "site_id",
    "year_month",
    "activity_start_date",
    "activity_end_date",
    "fuel_subtype",
)


def _step_indicator(active: int) -> None:
    labels = [
        t("intake.step1", lang),
        t("intake.step2", lang),
        t("intake.step3", lang),
        t("intake.step4", lang),
        t("intake.step5", lang),
    ]
    cols = st.columns(5)
    for index, (column, label) in enumerate(zip(cols, labels, strict=True), start=1):
        with column:
            if index < active:
                st.markdown(f"✓ {label}")
            elif index == active:
                st.markdown(f"**● {label}**")
            else:
                st.caption(f"○ {label}")


def _render_completed_step_summary(
    *,
    step_no: int,
    title: str,
    detail: str,
    edit_key: str,
    target_step: int,
) -> None:
    st.markdown(
        f"""
        <div class="cel-card-secondary">
          <p class="cel-card-title">✓ {html_escape(title)}</p>
          <p class="cel-card-reason">{html_escape(detail)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(t("intake.nav.edit", lang), key=edit_key):
        st.session_state[STATE_INTAKE_STEP] = target_step
        if target_step <= 3:
            st.session_state[STATE_INTAKE_RESULT] = None
            clear_duplicate_review_state(st.session_state)
        if target_step <= 2:
            st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = False
        if target_step == 1:
            # Keep bytes; user may replace via uploader.
            pass
        _ = step_no
        st.rerun()


def html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _duplicate_context_label(group: Any) -> str:
    fuel = str(getattr(group, "fuel_subtype", "") or "").strip()
    process = str(getattr(group, "process_use", "") or "").strip()
    parts: list[str] = []
    if fuel and fuel not in {"not_applicable", "unknown"}:
        parts.append(fuel)
    if process in {"company_vehicle"}:
        parts.append(t("intake.diesel_company_vehicle", lang))
    elif process in {"general_factory", "forging"}:
        parts.append(t("intake.electricity_enterprise", lang))
    elif process and process not in {"not_applicable", "unknown", "heat_treatment"}:
        parts.append(process)
    return "／".join(parts) if parts else "—"


def _sync_duplicate_review_from_widgets(groups: list[Any]) -> None:
    existing = dict(st.session_state.get(STATE_INTAKE_DUPLICATE_REVIEW) or {})
    review_session = "ui_intake"
    meta = st.session_state.get(STATE_INTAKE_METADATA)
    if meta is not None and getattr(meta, "intake_run_id", None):
        review_session = str(meta.intake_run_id)
    now = pd.Timestamp.now(tz="UTC").isoformat()
    updated: dict[str, Any] = {}
    keep_label = t("intake.dup.keep_all", lang)
    exclude_label = t("intake.dup.exclude", lang)
    for group in groups:
        key = f"intake_dup_decision_{group.group_id}"
        choice = st.session_state.get(key)
        if choice == keep_label:
            decision_code = DECISION_KEEP_ALL
        elif choice == exclude_label:
            decision_code = DECISION_EXCLUDE_DUPLICATES
        else:
            continue
        previous = existing.get(group.group_id) or {}
        reviewed_at = now
        if (
            isinstance(previous, dict)
            and previous.get("decision") == decision_code
            and previous.get("reviewed_at")
        ):
            reviewed_at = str(previous.get("reviewed_at"))
        decided = decide_potential_duplicate_group(
            group,
            decision_code,
            reviewed_at=reviewed_at,
            review_session=review_session,
        )
        updated[group.group_id] = decision_to_map_payload(decided)
    st.session_state[STATE_INTAKE_DUPLICATE_REVIEW] = updated


def _render_potential_duplicate_review(intake_result: Any) -> bool:
    """Show lookalike review. Return True when analysis may continue."""
    groups = list(groups_from_intake(intake_result))
    if not groups:
        return True
    decisions = duplicate_review_decisions_from_state(st.session_state)
    unresolved = unresolved_potential_duplicate_groups(groups, decisions)
    st.warning(t("intake.dup.title", lang))
    st.markdown(t("intake.dup.body", lang, count=len(groups)))
    if st.button(t("intake.dup.review", lang), key="intake_dup_open_review"):
        st.session_state[STATE_INTAKE_SHOW_DUPLICATE_REVIEW] = True
    show = bool(st.session_state.get(STATE_INTAKE_SHOW_DUPLICATE_REVIEW))
    if show:
        st.session_state[STATE_INTAKE_SHOW_DUPLICATE_REVIEW] = True
        keep_label = t("intake.dup.keep_all", lang)
        exclude_label = t("intake.dup.exclude", lang)
        for index, group in enumerate(groups, start=1):
            st.markdown(f"**{t('intake.dup.group', lang, n=index)}**")
            preview = pd.DataFrame(
                {
                    t("intake.dup.file_row", lang): list(group.source_rows),
                    t("intake.field.activity_type", lang): [
                        t(f"activity.{group.activity_type}", lang)
                    ]
                    * len(group.record_ids),
                    t("intake.field.activity_value", lang): [
                        group.activity_value
                    ]
                    * len(group.record_ids),
                    t("intake.field.unit", lang): [group.unit]
                    * len(group.record_ids),
                    t("intake.field.start", lang): [
                        group.activity_start_date
                    ]
                    * len(group.record_ids),
                    t("intake.field.end", lang): [group.activity_end_date]
                    * len(group.record_ids),
                    t("intake.field.site_id", lang): [
                        customer_site_display(group.site_id, lang)
                    ]
                    * len(group.record_ids),
                    t("intake.dup.context", lang): [
                        _duplicate_context_label(group)
                    ]
                    * len(group.record_ids),
                }
            )
            st.dataframe(preview, hide_index=True, width="stretch")
            st.radio(
                t("intake.dup.title", lang),
                options=[keep_label, exclude_label],
                index=None,
                key=f"intake_dup_decision_{group.group_id}",
                label_visibility="collapsed",
            )
        _sync_duplicate_review_from_widgets(groups)
        decisions = duplicate_review_decisions_from_state(st.session_state)
        unresolved = unresolved_potential_duplicate_groups(groups, decisions)
        if not unresolved:
            st.success(t("intake.dup.confirmed", lang))
            exclude_chosen = any(
                item.decision == DECISION_EXCLUDE_DUPLICATES
                for item in decisions
            )
            if exclude_chosen:
                st.caption(t("intake.dup.exclude_note", lang))
            else:
                st.caption(t("intake.dup.keep_note", lang))
        else:
            st.info(t("intake.dup.blocked", lang))
    elif unresolved:
        st.info(t("intake.dup.blocked", lang))
    return not bool(unresolved)


def _reset_for_new_file() -> None:
    clear_intake_state(st.session_state)
    clear_analysis_result(st.session_state)
    st.session_state[STATE_INTAKE_STEP] = 1


def _activity_select_label(code: str) -> str:
    if not code:
        return t("intake.choose", lang)
    return t(f"activity.{code}", lang)


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
                "fuel_subtype": "intake.interpret.fuel_subtype",
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
    # Never invent demo-era period dates; period mode must be set by the user.
    period_start = None
    period_end = None

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
    fuel_suggestion = _suggestion(detailed, "fuel_subtype")
    if _usable_suggestion(fuel_suggestion):
        draft.natural_gas_subtype_column = fuel_suggestion.source_column
    return draft


def _default_metadata(table: Any) -> IntakeMetadata:
    return IntakeMetadata(
        source_name=table.file_name,
        site_id="UNKNOWN",
        document_date=None,
        data_quality_tier="unknown",
        intake_run_id="ui_intake",
        ingested_at=pd.Timestamp.now(tz="UTC"),
    )


render_section_header(t("intake.upload_priority", lang), t("intake.page_lead", lang))
st.markdown(t("intake.upload_limit", lang))

step = int(st.session_state.get(STATE_INTAKE_STEP, 1) or 1)
# Promote mapping editor to step 3 in the five-step wizard.
if bool(st.session_state.get(STATE_INTAKE_SHOW_MAPPING_EDITOR)) and step == 2:
    step = 3
    st.session_state[STATE_INTAKE_STEP] = 3
_step_indicator(step)

existing_table = st.session_state.get(STATE_INTAKE_TABLE)
existing_result = st.session_state.get(STATE_INTAKE_RESULT)

# —— Step summaries for completed upstream steps (only one active workspace) ——
if step > 1 and existing_table is not None:
    _render_completed_step_summary(
        step_no=1,
        title=t("intake.uploaded_summary", lang),
        detail=(
            f"{existing_table.file_name} · "
            f"{len(existing_table.frame)} {t('intake.row_count', lang)}"
        ),
        edit_key="intake_edit_step1",
        target_step=1,
    )
if step > 2 and existing_table is not None:
    _render_completed_step_summary(
        step_no=2,
        title=t("intake.step2", lang),
        detail=t("intake.understood", lang),
        edit_key="intake_edit_step2",
        target_step=2,
    )
if step > 3 and st.session_state.get(STATE_INTAKE_MAPPING) is not None:
    _render_completed_step_summary(
        step_no=3,
        title=t("intake.step3", lang),
        detail=t("intake.journey.confirm", lang),
        edit_key="intake_edit_step3",
        target_step=3,
    )
if step > 4 and existing_result is not None:
    _render_completed_step_summary(
        step_no=4,
        title=t("intake.step4", lang),
        detail=(
            f"{existing_result.accepted_count} ✓ / "
            f"{existing_result.rejected_count} × / "
            f"{existing_result.total_count}"
        ),
        edit_key="intake_edit_step4",
        target_step=4,
    )

uploaded = None
if step == 1:
    st.write("")
    uploaded = st.file_uploader(
        t("intake.upload_label", lang),
        type=["csv", "xlsx"],
        help=t("intake.upload_limit", lang),
        key="intake_file_uploader",
    )

    st.markdown(f"**{t('intake.need_help_prepare', lang)}**")
    template_bytes, template_name, template_mime = _template_download_payload()
    st.download_button(
        label=t("intake.template_button", lang),
        data=template_bytes,
        file_name=template_name,
        mime=template_mime,
        key="intake_template_download",
    )
    with st.expander(t("intake.example_expand", lang), expanded=False):
        st.caption(t("intake.example_disclaimer", lang))
        st.dataframe(
            example_preview_customer_rows(),
            hide_index=True,
            width="stretch",
        )

    st.markdown(f"**{t('intake.needed_fields_title', lang)}**")
    st.markdown(t("intake.needed_fields_list", lang))
    with st.expander(t("intake.advanced_schema", lang), expanded=False):
        st.caption(t("intake.col_help_activity_type", lang))
        st.caption(t("intake.col_help_activity_value", lang))
        st.caption(t("intake.col_help_unit", lang))
        st.caption(t("intake.col_help_start", lang))
        st.caption(t("intake.col_help_end", lang))

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

step = int(st.session_state.get(STATE_INTAKE_STEP, 1) or 1)
if step < 2:
    st.stop()

result = st.session_state.get(STATE_INTAKE_RESULT)
detailed = suggest_column_mapping_with_confidence(list(table.columns))
show_editor = bool(st.session_state.get(STATE_INTAKE_SHOW_MAPPING_EDITOR))

# Active workspace gates: only one expanded step body at a time.
if step >= 4 and result is not None:
    pass  # validation / analysis sections below
elif step in {2, 3} or result is None:
    if step > 3 and result is None:
        st.session_state[STATE_INTAKE_STEP] = 3
        step = 3

# Confirmation / editor only while there is no validated result yet.
if result is None and step <= 3:
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
                needed = context_confirmations_needed(table, mapping)
                if any(needed.values()):
                    st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = True
                    st.session_state[STATE_INTAKE_STEP] = 3
                    st.rerun()
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
    fuel_subtype_column = _select_for(
        "fuel_subtype",
        "intake.map_ng_type_column",
        "intake_map_fuel_subtype",
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
        st.caption(t("intake.period_required", lang))
        period_cols = st.columns(2)
        with period_cols[0]:
            period_start = st.date_input(
                t("intake.period_start", lang),
                value=None,
                key="intake_period_start",
            )
        with period_cols[1]:
            period_end = st.date_input(
                t("intake.period_end", lang),
                value=None,
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

    natural_gas_subtype = "unknown"
    diesel_context = "unknown"
    electricity_context = "unknown"
    mapped_types = set(activity_type_value_map.values())
    unknown_label = t("intake.ng_type_unknown", lang)
    saved_mapping = st.session_state.get(STATE_INTAKE_MAPPING)

    if "natural_gas" in mapped_types:
        source_has_explicit_ng = False
        if activity_type_column:
            for source_value, mapped in activity_type_value_map.items():
                if mapped != "natural_gas":
                    continue
                if extract_natural_gas_subtype_from_text(source_value):
                    source_has_explicit_ng = True
        ng_options = ["NG1", "NG2", unknown_label]
        saved_subtype = "unknown"
        if saved_mapping is not None:
            saved_subtype = str(
                getattr(saved_mapping, "natural_gas_subtype", "unknown") or "unknown"
            )
        default_ng = saved_subtype if saved_subtype in {"NG1", "NG2"} else unknown_label
        st.markdown(f"**{t('intake.ng_type', lang)}**")
        selected_ng = st.radio(
            t("intake.ng_type", lang),
            options=ng_options,
            index=ng_options.index(default_ng),
            key="intake_natural_gas_subtype",
            label_visibility="collapsed",
        )
        st.caption(t("intake.ng_type_help", lang))
        with st.expander(t("intake.ng_learn_title", lang), expanded=False):
            st.write(t("intake.ng_learn_body", lang))
        if source_has_explicit_ng:
            st.caption(t("intake.ng_type_from_file", lang))
        natural_gas_subtype = (
            selected_ng if selected_ng in {"NG1", "NG2"} else "unknown"
        )

    if "diesel" in mapped_types:
        diesel_options = [
            t("intake.diesel_company_vehicle", lang),
            unknown_label,
        ]
        saved_diesel = "unknown"
        if saved_mapping is not None:
            saved_diesel = str(
                getattr(saved_mapping, "diesel_context", "unknown") or "unknown"
            )
        default_diesel = (
            diesel_options[0]
            if saved_diesel == "company_vehicle"
            else unknown_label
        )
        st.markdown(f"**{t('intake.diesel_context', lang)}**")
        selected_diesel = st.radio(
            t("intake.diesel_context", lang),
            options=diesel_options,
            index=diesel_options.index(default_diesel),
            key="intake_diesel_context",
            label_visibility="collapsed",
        )
        st.caption(t("intake.diesel_context_help", lang))
        diesel_context = (
            "company_vehicle"
            if selected_diesel == t("intake.diesel_company_vehicle", lang)
            else "unknown"
        )

    if "grid_electricity" in mapped_types:
        elec_options = [
            t("intake.electricity_enterprise", lang),
            unknown_label,
        ]
        saved_elec = "unknown"
        if saved_mapping is not None:
            saved_elec = str(
                getattr(saved_mapping, "electricity_context", "unknown")
                or "unknown"
            )
        default_elec = (
            elec_options[0] if saved_elec == "enterprise" else unknown_label
        )
        st.markdown(f"**{t('intake.electricity_context', lang)}**")
        selected_elec = st.radio(
            t("intake.electricity_context", lang),
            options=elec_options,
            index=elec_options.index(default_elec),
            key="intake_electricity_context",
            label_visibility="collapsed",
        )
        st.caption(t("intake.electricity_context_help", lang))
        electricity_context = (
            "enterprise"
            if selected_elec == t("intake.electricity_enterprise", lang)
            else "unknown"
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
        site_id = ""
        if not site_column:
            site_id = st.text_input(
                t("intake.site_name", lang),
                value="",
                key="intake_site_id",
                placeholder=t("intake.site_placeholder", lang),
                help=t("intake.site_unknown_help", lang),
            )
    with meta_cols[1]:
        document_date = st.date_input(
            t("intake.document_date", lang),
            value=None,
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
        natural_gas_subtype=natural_gas_subtype,
        natural_gas_subtype_column=fuel_subtype_column,
        diesel_context=diesel_context,
        electricity_context=electricity_context,
    )
    confirmed_document_date = (
        document_date if isinstance(document_date, date) else None
    )
    metadata = IntakeMetadata(
        source_name=source_name.strip() or table.file_name,
        site_id=site_id.strip() or "UNKNOWN",
        document_date=confirmed_document_date,
        data_quality_tier=QUALITY_LABEL_TO_CODE.get(quality_label, "unknown"),
        intake_run_id="ui_intake",
        ingested_at=pd.Timestamp.now(tz="UTC"),
    )
    st.session_state[STATE_INTAKE_MAPPING] = mapping
    st.session_state[STATE_INTAKE_METADATA] = metadata
    if confirmed_document_date is None:
        st.info(t("intake.document_date_required", lang))

    if _action_button(
        t("intake.run_validation", lang),
        t("intake.btn.validate_help", lang),
        key="intake_run_validation",
        primary=True,
    ):
        if confirmed_document_date is None:
            st.error(t("intake.document_date_required", lang))
            st.stop()
        try:
            validated = build_and_validate_intake(table, mapping, metadata)
        except IntakeError as exc:
            st.error(exc.message)
            st.stop()
        st.session_state[STATE_INTAKE_RESULT] = validated
        clear_duplicate_review_state(st.session_state)
        st.session_state[STATE_INTAKE_STEP] = 4
        st.rerun()
    st.stop()

# Validation (step 4) and analysis start (step 5)
if result is None:
    st.stop()

step = int(st.session_state.get(STATE_INTAKE_STEP, 4) or 4)
if step < 4:
    st.session_state[STATE_INTAKE_STEP] = 4
    step = 4

nav_cols = st.columns([1, 1, 2])
with nav_cols[0]:
    if st.button(t("intake.nav.back", lang), key="intake_nav_back_results"):
        st.session_state[STATE_INTAKE_STEP] = 3
        st.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = True
        st.session_state[STATE_INTAKE_RESULT] = None
        clear_duplicate_review_state(st.session_state)
        st.rerun()

if step == 4:
    st.write("")
    render_section_header(t("intake.step4", lang))
    render_kpi_row(
        [
            (result.accepted_count, t("intake.result_accepted", lang), "teal"),
            (result.rejected_count, t("intake.result_rejected", lang), "amber"),
            (result.total_count, t("intake.result_total", lang), "blue"),
        ]
    )
    tab_ok, tab_fix, tab_bad = st.tabs(
        [
            t("intake.result_accepted", lang),
            t("intake.col.review", lang),
            t("intake.result_rejected", lang),
        ]
    )
    accepted = result.accepted_activities
    with tab_ok:
        if accepted is not None and not accepted.empty:
            preview = accepted[
                [
                    "activity_type",
                    "activity_value",
                    "unit",
                    "activity_start_date",
                    "activity_end_date",
                    "site_id",
                ]
            ].copy()
            preview["activity_type"] = preview["activity_type"].map(
                lambda code: t(f"activity.{code}", lang)
            )
            preview["site_id"] = preview["site_id"].map(
                lambda value: customer_site_display(value, lang)
            )
            preview["status"] = t("intake.result_accepted", lang)
            preview["issue"] = "—"
            preview = preview.rename(
                columns={
                    "activity_type": t("intake.field.activity_type", lang),
                    "activity_value": t("intake.field.activity_value", lang),
                    "unit": t("intake.field.unit", lang),
                    "activity_start_date": t("intake.field.start", lang),
                    "activity_end_date": t("intake.field.end", lang),
                    "site_id": t("intake.field.site_id", lang),
                    "status": t("intake.col.status", lang),
                    "issue": t("intake.col.issue", lang),
                }
            )
            st.dataframe(preview, hide_index=True, width="stretch")
        else:
            st.warning(t("intake.partial", lang))
    with tab_fix:
        st.caption(t("intake.partial", lang))
    with tab_bad:
        if result.rejected_count > 0:
            rejected = result.rejected_rows.copy()
            if "field" in rejected.columns:
                rejected["field"] = rejected["field"].map(
                    lambda name: customer_schema_label(str(name), lang)
                )
            rejected = rejected.rename(
                columns={
                    "source_row": t("intake.rej.row", lang),
                    "field": t("intake.rej.field", lang),
                    "issue_message": t("intake.rej.issue", lang),
                    "uploaded_value": t("intake.rej.value", lang),
                }
            )
            st.dataframe(
                rejected[
                    [
                        t("intake.rej.row", lang),
                        t("intake.rej.field", lang),
                        t("intake.rej.issue", lang),
                        t("intake.rej.value", lang),
                    ]
                ],
                hide_index=True,
                width="stretch",
            )
        else:
            st.success(t("intake.success", lang))
    duplicates_ready = _render_potential_duplicate_review(result)
    if result.accepted_count > 0 and duplicates_ready:
        if st.button(
            t("intake.nav.next", lang),
            type="primary",
            key="intake_to_step5",
        ):
            st.session_state[STATE_INTAKE_STEP] = 5
            st.rerun()
    st.stop()

# Step 5 — start analysis
if duplicate_review_blocks_analysis(st.session_state):
    st.session_state[STATE_INTAKE_STEP] = 4
    st.rerun()

st.write("")
render_section_header(t("intake.step5", lang))
st.markdown(t("intake.ready_body", lang, count=result.accepted_count))
st.markdown(t("intake.ready_next", lang))
accepted = result.accepted_activities
st.markdown(
    f"**{t('intake.review.rows', lang)}：** {result.accepted_count}"
)
if accepted is not None and not accepted.empty:
    starts = pd.to_datetime(accepted["activity_start_date"], errors="coerce")
    ends = pd.to_datetime(accepted["activity_end_date"], errors="coerce")
    start_label = (
        starts.min().strftime("%Y-%m") if not starts.isna().all() else "—"
    )
    end_label = ends.max().strftime("%Y-%m") if not ends.isna().all() else "—"
    st.markdown(
        f"**{t('intake.review.period', lang)}：** {start_label} "
        f"{t('intake.review.period_to', lang)} {end_label}"
    )
    site_values = sorted(
        {
            customer_site_display(value, lang)
            for value in accepted["site_id"].tolist()
        }
    )
    st.markdown(
        f"**{t('intake.field.site_id', lang)}：** {'、'.join(site_values) or '—'}"
    )
    type_count = int(accepted["activity_type"].nunique())
    st.markdown(f"**{t('intake.review.activity_types', lang)}：** {type_count}")
    readiness = summarize_pre_analysis_readiness(accepted)
    st.markdown(
        f"**{t('intake.review.ready', lang)}：** "
        f"{readiness.get('ready', 0)}"
    )
    st.markdown(
        f"**{t('intake.review.needs_confirm', lang)}：** "
        f"{readiness.get('needs_confirm', 0)}"
    )
    st.markdown(
        f"**{t('intake.review.unsupported', lang)}：** "
        f"{readiness.get('unsupported', 0)}"
    )
st.markdown(
    f"**{t('intake.review.pending', lang)}：** {result.rejected_count}"
)
st.caption(
    f"{t('intake.file_name', lang)}: "
    f"{st.session_state.get(STATE_INTAKE_FILE_NAME) or '—'}"
)
if result.accepted_count > 0:
    cta_cols = st.columns([2, 1])
    with cta_cols[0]:
        if st.button(
            t("intake.start_analysis", lang),
            type="primary",
            use_container_width=True,
            key="intake_start_uploaded_analysis",
        ):
            st.session_state[STATE_RUN_UPLOADED_REQUEST] = True
            st.rerun()
    with cta_cols[1]:
        if st.button(
            t("intake.nav.back", lang),
            use_container_width=True,
            key="intake_back_edit_data",
        ):
            st.session_state[STATE_INTAKE_STEP] = 4
            st.rerun()
else:
    st.info(t("intake.next_phase", lang))
