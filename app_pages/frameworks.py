"""Frameworks — separate GHG Protocol, EU CBAM, and IFRS S2 views."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.charts import (
    render_cbam_role_bars,
    render_ghg_scope_donut,
    render_ifrs_readiness_bars,
)
from carbon_ledger.ui.components import (
    inject_design_system,
    render_disabled_adapter_state,
    render_framework_notice,
    render_kpi_card,
    render_page_header,
    render_page_help,
    render_section_header,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_current_result, get_language
from carbon_ledger.ui.view_models import (
    cbam_framework_table,
    ghg_framework_table,
    ghg_scope_counts,
    ifrs_framework_table,
)

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

render_page_header(t("fw.title", lang), t("fw.subtitle", lang))
render_page_help(t("fw.help", lang))

if result is None:
    st.error(t("error.analysis_failed", lang))
    st.stop()

concept_cols = st.columns(3)
with concept_cols[0]:
    st.markdown(
        f"""
        <div class="cel-card">
          <p class="cel-kpi-label">GHG Protocol</p>
          <p class="cel-issue-title">{t("fw.ghg_card_title", lang)}</p>
          <p class="cel-issue-body">{t("fw.ghg_question", lang)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with concept_cols[1]:
    st.markdown(
        f"""
        <div class="cel-card">
          <p class="cel-kpi-label">EU CBAM</p>
          <p class="cel-issue-title">{t("fw.cbam_card_title", lang)}</p>
          <p class="cel-issue-body">{t("fw.cbam_question", lang)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with concept_cols[2]:
    st.markdown(
        f"""
        <div class="cel-card">
          <p class="cel-kpi-label">IFRS S2</p>
          <p class="cel-issue-title">{t("fw.ifrs_card_title", lang)}</p>
          <p class="cel-issue-body">{t("fw.ifrs_question", lang)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.write("")
ghg_tab, cbam_tab, ifrs_tab = st.tabs(["GHG Protocol", "EU CBAM", "IFRS S2"])

with ghg_tab:
    if not result.include_ghg:
        render_disabled_adapter_state(lang, "GHG Protocol")
    else:
        counts = ghg_scope_counts(result, lang)
        if counts:
            cols = st.columns(min(4, len(counts)))
            for column, (label, value) in zip(cols, counts.items(), strict=False):
                with column:
                    render_kpi_card(value, label)
        render_ghg_scope_donut(result, lang)
        render_section_header("GHG Protocol")
        table = ghg_framework_table(result, lang)
        st.dataframe(
            table.drop(columns=["record_id"], errors="ignore").rename(
                columns={
                    "Activity": t("fw.col.activity", lang),
                    "Scope": t("fw.col.scope", lang),
                    "Category / combustion type": t("fw.col.type", lang),
                    "Status": t("fw.col.status", lang),
                    "Reason": t("fw.col.reason", lang),
                }
            ),
            hide_index=True,
            width="stretch",
        )

with cbam_tab:
    render_framework_notice(t("fw.cbam_warning", lang))
    if not result.include_cbam:
        render_disabled_adapter_state(lang, "EU CBAM")
    else:
        render_cbam_role_bars(result, lang)
        table = cbam_framework_table(result, lang)
        st.dataframe(
            table.drop(columns=["record_id"], errors="ignore").rename(
                columns={
                    "Activity": t("fw.col.activity", lang),
                    "CBAM role": t("fw.col.role", lang),
                    "Relevance": t("fw.col.relevance", lang),
                    "Status": t("fw.col.status", lang),
                    "What is missing": t("fw.col.missing", lang),
                }
            ),
            hide_index=True,
            width="stretch",
        )

with ifrs_tab:
    render_framework_notice(t("fw.ifrs_warning", lang))
    if not result.include_ifrs_s2:
        render_disabled_adapter_state(lang, "IFRS S2")
    else:
        render_ifrs_readiness_bars(result, lang)
        table = ifrs_framework_table(result, lang)
        st.dataframe(
            table.drop(columns=["record_id"], errors="ignore").rename(
                columns={
                    "Activity": t("fw.col.activity", lang),
                    "Evidence role": t("fw.col.evidence_role", lang),
                    "Readiness": t("fw.col.readiness", lang),
                    "Missing data": t("fw.col.missing", lang),
                }
            ),
            hide_index=True,
            width="stretch",
        )
