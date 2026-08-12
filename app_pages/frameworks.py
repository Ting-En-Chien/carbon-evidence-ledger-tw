"""IFRS S1/S2 work area — four official pillars (Stage 2 IA)."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.charts import render_ifrs_readiness_bars
from carbon_ledger.ui.components import (
    inject_design_system,
    render_disabled_adapter_state,
    render_framework_notice,
    render_page_header,
    render_page_help,
    render_section_header,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_current_result, get_language
from carbon_ledger.ui.view_models import ifrs_framework_table

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

render_page_header(t("fw.title", lang), t("fw.subtitle", lang))
render_page_help(t("fw.help", lang))

gov_tab, strategy_tab, risk_tab, metrics_tab = st.tabs(
    [
        t("fw.pillar.governance", lang),
        t("fw.pillar.strategy", lang),
        t("fw.pillar.risk", lang),
        t("fw.pillar.metrics", lang),
    ]
)


def _pillar_shell(title_key: str) -> None:
    render_section_header(t(title_key, lang))
    with st.container(border=True):
        st.markdown(f"**{t('fw.pillar.shell_status', lang)}**")
        st.write(t("fw.pillar.shell_help", lang))
        st.caption(t("fw.needs_information", lang))
        st.caption(t("app.coming_next_stage", lang))


with gov_tab:
    _pillar_shell("fw.pillar.governance")

with strategy_tab:
    _pillar_shell("fw.pillar.strategy")

with risk_tab:
    _pillar_shell("fw.pillar.risk")

with metrics_tab:
    render_section_header(t("fw.pillar.metrics", lang))
    st.caption(t("fw.metrics_help", lang))
    if result is None:
        st.warning(t("error.analysis_failed", lang))
    else:
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
