"""Dashboard — compact SaaS carbon data overview with meaningful charts."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.charts import (
    render_activity_status_bars,
    render_calculation_status_donut,
    render_emissions_contribution_bars,
)
from carbon_ledger.ui.components import (
    inject_design_system,
    render_emissions_panel,
    render_empty_state,
    render_issue_card,
    render_kpi_row,
    render_page_header,
    render_section_header,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    get_current_result,
    get_language,
    set_focus_record,
)
from carbon_ledger.ui.tutorial import request_tutorial
from carbon_ledger.ui.view_models import (
    attention_issue_cards,
    build_activity_overview,
    calculated_emissions_summary,
    dashboard_kpi_counts,
)

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

if result is None:
    st.error(t("error.analysis_failed", lang))
    st.stop()

render_page_header(
    t("dash.page_title", lang),
    t("dash.page_subtitle", lang),
    badge=t("common.demo_badge", lang),
)

if st.button(
    t("dash.tutorial_hint", lang),
    key="dashboard_open_tutorial",
    type="tertiary",
):
    request_tutorial(st.session_state)
    st.rerun()

kpis = dashboard_kpi_counts(result, lang)
render_kpi_row(
    [
        (kpis["activities"], t("dash.kpi_activities", lang), "slate"),
        (kpis["calculated"], t("dash.kpi_calculated", lang), "teal"),
        (kpis["open_qa_issues"], t("dash.kpi_issues", lang), "amber"),
        (kpis["source_documents"], t("dash.kpi_docs", lang), "blue"),
    ]
)

viz_left, viz_right = st.columns(2, gap="large")
with viz_left:
    render_calculation_status_donut(result, lang)
with viz_right:
    render_activity_status_bars(result, lang)

emissions = calculated_emissions_summary(result, lang)
value = emissions["calculated_tco2e"]
display = f"{value:.6g} tCO₂e" if value is not None else "—"
ratio = t(
    "dash.emissions_ratio",
    lang,
    done=emissions["calculated_row_count"],
    total=kpis["activities"],
)
render_emissions_panel(
    title=t("dash.emissions_title", lang),
    value_display=display,
    ratio=ratio,
    status_label=emissions["label"],
    notice=t("dash.emissions_notice", lang),
)
render_emissions_contribution_bars(result, lang)

render_section_header(
    t("dash.attention_title", lang),
    t("dash.attention_sub", lang),
)
cards = attention_issue_cards(result, lang)
if not cards:
    render_empty_state(
        t("dash.attention_empty", lang),
        t("dash.attention_empty", lang),
    )
else:
    card_cols = st.columns(min(3, len(cards)), gap="medium")
    for index, card in enumerate(cards):
        with card_cols[index % len(card_cols)]:
            render_issue_card(
                activity_name=card["activity_name"],
                title=card["title"],
                severity=card["severity"],
                action_hint=card["action_hint"],
            )
            if st.button(
                t("common.view_missing", lang),
                key=f"dash_issue_{card['record_id']}",
                type="tertiary",
            ):
                set_focus_record(st.session_state, card["record_id"])
                st.switch_page("app_pages/activity_explorer.py")

st.write("")
render_section_header(
    t("dash.activities_title", lang),
    t("dash.activities_sub", lang),
)
overview = build_activity_overview(result, lang)
display_table = overview[
    [
        "activity_name",
        "activity_amount",
        "calculation_label",
        "ghg_label",
        "cbam_label",
        "ifrs_s2_label",
        "qa_label",
    ]
].rename(
    columns={
        "activity_name": t("dash.col.activity", lang),
        "activity_amount": t("dash.col.amount", lang),
        "calculation_label": t("dash.col.calc", lang),
        "ghg_label": t("dash.col.ghg", lang),
        "cbam_label": t("dash.col.cbam", lang),
        "ifrs_s2_label": t("dash.col.ifrs", lang),
        "qa_label": t("dash.col.qa", lang),
    }
)
st.dataframe(display_table, hide_index=True, width="stretch")
