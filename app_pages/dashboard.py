"""Compliance Overview — Stage 2 IA shell over existing result components."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.charts import (
    render_calculation_status_donut,
    render_emissions_source_bars,
    render_monthly_emissions_trend,
)
from carbon_ledger.ui.components import (
    inject_design_system,
    render_completeness_stats,
    render_empty_state,
    render_issue_card,
    render_page_header,
    render_result_meta_strip,
    render_section_header,
    render_success_banner,
    render_trace_card,
    render_viz_panel_end,
    render_viz_panel_start,
)
from carbon_ledger.ui.formatting import (
    format_activity_amount,
    format_tco2e,
    format_tco2e_parts,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import (
    consume_result_reveal,
    hero_emissions_should_play,
    mark_chart_reveal,
    render_hero_result_kpis,
    result_reveal_token,
)
from carbon_ledger.ui.state import (
    get_analysis_source_summary,
    get_current_result,
    get_language,
    is_uploaded_analysis,
    set_focus_record,
)
from carbon_ledger.ui.view_models import (
    beginner_result_summary,
    build_activity_overview,
    calculated_emissions_summary,
    calculation_table_rows,
    calculation_trace_fields,
    first_calculated_electricity_record_id,
    priority_action_cards,
)

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

if result is None:
    st.error(t("error.analysis_failed", lang))
    st.stop()

source = get_analysis_source_summary(st.session_state)
uploaded = is_uploaded_analysis(st.session_state)
badge = (
    t("common.uploaded_badge", lang)
    if uploaded
    else t("common.demo_badge", lang)
)
animate = consume_result_reveal(st.session_state, result)
analysis_token = result_reveal_token(result)
play_hero_count = hero_emissions_should_play(st.session_state, result)

render_page_header(
    t("dash.page_title", lang),
    t("dash.page_subtitle", lang),
)
st.caption(t("dash.no_fake_score_note", lang))

period_start = source.get("period_start")
period_end = source.get("period_end")
if period_start and period_end:
    period_text = f"{period_start} — {period_end}"
else:
    period_text = t("dash.period_unknown", lang)

if uploaded:
    file_display = str(source.get("file_name") or "uploaded_file")
else:
    file_display = t("sidebar.workspace_name", lang)

st.markdown(
    (
        '<div data-cel-reveal="section" data-cel-key="result-meta" '
        'data-cel-animation-type="section">'
    ),
    unsafe_allow_html=True,
)
render_result_meta_strip(
    file_name=file_display,
    period_text=period_text,
    badge=badge,
)
st.markdown("</div>", unsafe_allow_html=True)

summary = beginner_result_summary(result, lang)
emissions = calculated_emissions_summary(result, lang)
value = emissions["calculated_tco2e"]
done = int(summary["calculated"])
partial_label = (
    t("common.partial_result", lang)
    if done < int(summary["activities"])
    else t("status.calculated", lang)
)

if animate:
    render_success_banner(
        title=t("dash.complete_title", lang),
        body=t(
            "analysis.complete_detail",
            lang,
            total=int(summary["activities"]),
            done=done,
        ),
        reveal=True,
    )

# Level 1 — what requires attention
render_section_header(
    t("dash.section_attention", lang),
    t("dash.section_attention_help", lang),
    scroll_key="priority",
)
priority = priority_action_cards(result, lang, limit=4)
if not priority:
    render_empty_state(
        t("dash.attention_empty", lang),
        t("dash.attention_empty", lang),
    )
else:
    cols = st.columns(min(4, len(priority)), gap="medium")
    for index, card in enumerate(priority):
        with cols[index % len(cols)]:
            impact = int(card.get("affected_count") or 0)
            impact_text = t("dash.priority.affected", lang, count=impact)
            render_issue_card(
                activity_name=card["activity_name"],
                title=t("dash.uncalculable_title", lang),
                severity=t("common.partial_result", lang),
                action_hint=f"{card['reason']}\n{impact_text}",
                scroll_key=f"priority-{index}",
            )
            if st.button(
                t("dash.cta.how_to_fix", lang),
                key=f"dash_priority_{card['record_id']}",
                type="tertiary",
            ):
                set_focus_record(st.session_state, card["record_id"])
                st.switch_page("app_pages/activity_explorer.py")

# Level 2/3 — missing / review
render_section_header(
    t("dash.section_missing", lang),
    t("dash.section_completeness_help", lang),
    scroll_key="completeness",
)
comp_left, comp_right = st.columns([1.1, 1], gap="large")
with comp_left:
    render_viz_panel_start(
        t("chart.calc_status.title", lang),
        scroll_key="completeness-donut",
        chart_kind="donut",
    )
    mark_chart_reveal("completeness-donut", chart="donut")
    render_calculation_status_donut(result, lang)
    render_viz_panel_end()
with comp_right:
    render_completeness_stats(
        note=t("dash.completeness_note", lang),
        calculated_label=t("dash.calculated_kpi", lang),
        calculated_value=int(done),
        needs_work_label=t("dash.needs_work_kpi", lang),
        needs_work_value=int(summary["needs_work"]),
        scroll_key="completeness-metrics",
    )

cta_cols = st.columns([1, 1, 1, 1])
with cta_cols[0]:
    if st.button(
        t("dash.cta.view_issues", lang),
        key="dash_view_issues",
        type="secondary",
        use_container_width=True,
    ):
        st.switch_page("app_pages/issues_actions.py")
with cta_cols[1]:
    if st.button(
        t("dash.cta.view_evidence", lang),
        key="dash_view_evidence",
        type="secondary",
        use_container_width=True,
    ):
        st.switch_page("app_pages/data_intake.py")
with cta_cols[2]:
    if st.button(
        t("dash.cta.view_ifrs", lang),
        key="dash_open_ifrs",
        type="tertiary",
        use_container_width=True,
    ):
        st.switch_page("app_pages/frameworks.py")
with cta_cols[3]:
    if st.button(
        t("dash.cta.view_taiwan", lang),
        key="dash_open_taiwan",
        type="tertiary",
        use_container_width=True,
    ):
        st.switch_page("app_pages/taiwan_ghg.py")

# Level 4 secondary — emissions evidence summary (preserve hero count-up)
render_section_header(
    t("dash.section_emissions_summary", lang),
    t("dash.section_emissions_summary_help", lang),
    scroll_key="emissions-summary",
)
render_hero_result_kpis(
    emissions_value=value,
    emissions_label=t("dash.kpi.emissions", lang),
    emissions_subtitle=partial_label,
    done=done,
    total=int(summary["activities"]),
    completion_label=t("dash.kpi.completion", lang),
    completion_subtitle=t(
        "dash.emissions_ratio",
        lang,
        done=done,
        total=summary["activities"],
    ),
    unresolved=int(summary["needs_work"]),
    unresolved_label=t("dash.kpi.unresolved", lang),
    unresolved_subtitle=t("dash.kpi.unresolved_hint", lang),
    sources=int(summary["source_documents"]),
    sources_label=t("dash.kpi.source", lang),
    sources_subtitle=t("dash.kpi.source_hint", lang),
    animate=animate,
    animation_token=analysis_token,
    play_hero_count=play_hero_count,
)
st.caption(t("dash.emissions_notice", lang))

left, right = st.columns(2, gap="large")
with left:
    render_viz_panel_start(
        t("dash.section_trend", lang),
        t("dash.section_trend_help", lang),
        scroll_key="trend-panel",
        chart_kind="area",
    )
    mark_chart_reveal("trend", chart="area")
    render_monthly_emissions_trend(result, lang)
    render_viz_panel_end()
with right:
    render_viz_panel_start(
        t("dash.section_sources", lang),
        t("dash.section_sources_help", lang),
        scroll_key="sources-panel",
        chart_kind="bars",
    )
    mark_chart_reveal("sources", chart="bars")
    render_emissions_source_bars(result, lang)
    render_viz_panel_end()

render_section_header(
    t("dash.section_calc_table", lang),
    t("dash.section_calc_table_help", lang),
    scroll_key="calc-table",
)
table = calculation_table_rows(result, lang)
selected_rows: list[int] = []
if table.empty:
    render_empty_state(t("dash.section_calc_table", lang), "—")
else:
    display = table.drop(columns=["record_id"], errors="ignore")
    event = st.dataframe(
        display,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key="dash_calc_table",
    )
    if event is not None and getattr(event, "selection", None) is not None:
        selected_rows = list(event.selection.rows)

render_section_header(t("dash.section_trace", lang), scroll_key="trace-header")
trace_id = None
if selected_rows and not table.empty:
    trace_id = str(table.iloc[selected_rows[0]]["record_id"])
if not trace_id:
    trace_id = first_calculated_electricity_record_id(result)
if not trace_id and not table.empty:
    trace_id = str(table.iloc[0]["record_id"])

if trace_id:
    trace = calculation_trace_fields(
        result,
        trace_id,
        lang,
        official_source=uploaded,
    )
    amount = trace.get("activity_amount")
    factor_value = trace.get("factor_value")
    kg = trace.get("calculated_kgco2e")
    tco2e = trace.get("calculated_tco2e")
    unit = trace.get("activity_unit") or ""
    if (
        trace.get("is_calculated")
        and amount is not None
        and factor_value is not None
        and tco2e is not None
    ):
        amount_display = format_activity_amount(amount)
        factor_display = f"{float(factor_value):.6g}"
        kg_display = format_activity_amount(kg) if kg is not None else None
        tco2e_amount, _tco2e_unit = format_tco2e_parts(tco2e)
        formula = (
            f"{amount_display} × {factor_display}"
            f" = {kg_display} kgCO2e"
            if kg_display is not None
            else f"{amount_display} × {factor_display}"
        )
        render_trace_card(
            title=str(trace.get("activity_name") or t("dash.section_trace", lang)),
            activity_label=t("act.trace_activity", lang),
            activity_value=f"{amount_display} {unit}",
            factor_label=t("act.trace_factor", lang),
            factor_value=f"{factor_display} kgCO2e/{unit or 'unit'}",
            year_label=t("act.trace_factor_year", lang),
            year_value=str(trace.get("factor_year") or "—"),
            emissions_label=t("dash.col.emissions", lang),
            emissions_value=format_tco2e(tco2e),
            formula=formula,
            source_label=t("act.trace_source", lang),
            source_value=str(trace.get("source_label") or "—"),
            activity_amount=float(amount),
            activity_amount_display=amount_display,
            activity_unit=str(unit or ""),
            factor_num=float(factor_value),
            factor_display=factor_display,
            kg_num=float(kg) if kg is not None else None,
            kg_display=kg_display,
            tco2e_num=float(tco2e),
            tco2e_display=tco2e_amount,
        )
        with st.expander(t("dash.trace_evidence", lang), expanded=False):
            st.caption(t("dash.section_advanced", lang))
            st.write(
                {
                    "record_id": trace_id,
                    "factor_id": trace.get("factor_id"),
                    "calculated_kgco2e": kg,
                    "calculated_tco2e": tco2e,
                }
            )
    else:
        st.markdown(f"**{trace.get('activity_name', '—')}**")
        st.warning(t("dash.uncalculable_title", lang))
        st.write(trace.get("missing") or "—")
        st.caption(f"{t('dash.uncalculable_next', lang)} {trace.get('next_step')}")
else:
    st.info(t("dash.emissions_notice", lang))

with st.expander(t("dash.section_advanced", lang), expanded=False):
    overview = build_activity_overview(result, lang)
    tech_cols = [
        "record_id",
        "activity_name",
        "calculation_label",
        "ghg_label",
        "ifrs_s2_label",
        "qa_label",
    ]
    tech = overview[tech_cols].rename(
        columns={
            "activity_name": t("dash.col.activity", lang),
            "calculation_label": t("dash.col.calc", lang),
            "ghg_label": t("dash.col.ghg", lang),
            "ifrs_s2_label": t("dash.col.ifrs", lang),
            "qa_label": t("dash.col.qa", lang),
        }
    )
    st.dataframe(tech, hide_index=True, width="stretch")
    if st.button(
        t("nav.audit", lang) + " →",
        key="dash_open_audit",
        type="tertiary",
    ):
        st.switch_page("app_pages/audit_export.py")
