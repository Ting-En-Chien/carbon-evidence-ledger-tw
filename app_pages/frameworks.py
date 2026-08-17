"""IFRS S1/S2 — learning-first customer page."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.applicability import OBLIGATION_IFRS
from carbon_ledger.ui.charts import render_ifrs_readiness_bars
from carbon_ledger.ui.components import (
    inject_design_system,
    render_disabled_adapter_state,
    render_framework_notice,
    render_section_header,
)
from carbon_ledger.ui.customer_presenters import present_assessment
from carbon_ledger.ui.enterprise import (
    inject_enterprise_styles,
    render_obligation_result_card,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    get_applicability_assessment,
    get_company_profile_mapping,
    get_current_result,
    get_language,
    save_company_profile,
)
from carbon_ledger.ui.view_models import ifrs_framework_table

inject_design_system()
inject_enterprise_styles()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

st.markdown(
    f"""
    <p class="cel-page-kicker">IFRS</p>
    <h1 class="cel-page-title">{t("fw.title", lang)}</h1>
    <p class="cel-page-sub">{t("fw.subtitle", lang)}</p>
    """,
    unsafe_allow_html=True,
)

render_section_header(t("fw.prepare_what", lang))
st.write(t("fw.prepare_body", lang))
st.caption(t("fw.not_compliance", lang))
with st.expander(t("fw.ifrs_what_title", lang), expanded=False):
    st.markdown(t("learn.req.ifrs.what", lang))

PILLARS = [
    ("fw.pillar.governance", "fw.pillar.governance_q"),
    ("fw.pillar.strategy", "fw.pillar.strategy_q"),
    ("fw.pillar.risk", "fw.pillar.risk_q"),
    ("fw.pillar.metrics", "fw.pillar.metrics_q"),
]

render_section_header(t("fw.pillars_title", lang), t("fw.pillars_help", lang))
cols = st.columns(2, gap="medium")
for index, (title_key, question_key) in enumerate(PILLARS):
    with cols[index % 2]:
        st.markdown(
            f"""
            <div class="cel-card-secondary">
              <p class="cel-card-title">{t(title_key, lang)}</p>
              <p class="cel-card-reason">{t(question_key, lang)}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

assessment = get_applicability_assessment(st.session_state)
render_section_header(t("fw.applicability_summary", lang))
if assessment is None or assessment.obligation(OBLIGATION_IFRS) is None:
    st.info(t("empty.no_assessment_title", lang))
    st.caption(t("empty.no_assessment_body", lang))
    if st.button(t("dash.cta.complete_now", lang), key="fw_go_apl"):
        st.switch_page("app_pages/applicability.py")
else:
    presented = present_assessment(assessment, lang)
    ifrs_card = next(
        (item for item in presented.presentations if item.domain == "ifrs"),
        None,
    )
    if ifrs_card is not None:
        render_obligation_result_card(
            ifrs_card,
            lang,
            show_actions=ifrs_card.customer_action_required,
        )

profile = get_company_profile_mapping(st.session_state)
sasb_current = str(profile.get("sasb_industry") or "").strip()
with st.expander(t("fw.sasb_title", lang), expanded=False):
    st.caption(t("fw.sasb_help", lang))
    if sasb_current:
        st.write(f"{t('fw.sasb_current', lang)}：{sasb_current}")
    else:
        st.info(t("fw.sasb_unset", lang))
    sasb_edit = st.text_input(
        t("apl.field.sasb_industry", lang),
        value=sasb_current,
        key="fw_sasb_industry",
    )
    if st.button(t("fw.sasb_save", lang), key="fw_sasb_save"):
        merged = {**profile, "sasb_industry": sasb_edit.strip()}
        save_company_profile(st.session_state, merged)
        st.success(t("apl.saved_ok", lang))
        st.rerun()

with st.expander(t("fw.metrics_readiness_title", lang), expanded=False):
    st.caption(t("fw.pillar.shell_status", lang))
    st.caption(t("fw.data_readiness_section", lang))
    render_section_header(
        t("fw.metrics_readiness_title", lang),
        t("fw.metrics_readiness_disclaimer", lang),
    )
    if result is None:
        from carbon_ledger.ui.components import render_empty_state

        render_empty_state(
            t("empty.no_assessment_title", lang),
            t("empty.no_assessment_body", lang),
        )
    elif not result.include_ifrs_s2:
        render_disabled_adapter_state(lang, "IFRS S2")
    else:
        render_framework_notice(t("fw.ifrs_warning", lang))
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
