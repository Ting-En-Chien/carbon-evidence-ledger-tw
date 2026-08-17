"""Taiwan GHG / Carbon Fee — Stage 3B.2b segmented tracks."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.components import inject_design_system, render_section_header
from carbon_ledger.ui.customer_presenters import present_assessment
from carbon_ledger.ui.enterprise import (
    inject_enterprise_styles,
    render_customer_action_summary,
    render_obligation_result_card,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_applicability_assessment, get_language

inject_design_system()
inject_enterprise_styles()
lang = get_language(st.session_state)

st.markdown(
    f"""
    <p class="cel-page-kicker">Taiwan</p>
    <h1 class="cel-page-title">{t("tw.title", lang)}</h1>
    <p class="cel-page-sub">{t("tw.subtitle", lang)}</p>
    """,
    unsafe_allow_html=True,
)

render_section_header(t("tw.explain_title", lang))
explain_cols = st.columns(2, gap="medium")
explain_items = (
    ("tw.explain.inventory.title", "tw.explain.inventory.body"),
    ("tw.explain.verification.title", "tw.explain.verification.body"),
    ("tw.explain.assurance.title", "tw.explain.assurance.body"),
    ("tw.explain.fee.title", "tw.explain.fee.body"),
)
for index, (title_key, body_key) in enumerate(explain_items):
    with explain_cols[index % 2]:
        st.markdown(f"**{t(title_key, lang)}**")
        st.caption(t(body_key, lang))

assessment = get_applicability_assessment(st.session_state)
render_section_header(t("tw.status_title", lang))
if assessment is None:
    st.info(t("empty.no_assessment_title", lang))
    st.caption(t("empty.no_assessment_body", lang))
    if st.button(t("dash.cta.complete_now", lang), key="tw_go_apl"):
        st.switch_page("app_pages/applicability.py")
    st.stop()

presented = present_assessment(assessment, lang)
render_customer_action_summary(presented.action_summary, lang)
all_cards = {card.obligation_id: card for card in presented.presentations}

TRACKS = [
    (t("tw.track.inventory", lang), ("ghg_inventory",)),
    (
        t("tw.track.env_verification", lang),
        ("taiwan_environmental_verification",),
    ),
    (t("tw.track.carbon_fee", lang), ("carbon_fee",)),
    (
        t("tw.track.ifrs_assurance", lang),
        ("verification_assurance",),
    ),
]

tabs = st.tabs([label for label, _ids in TRACKS])
for tab, (_label, ids) in zip(tabs, TRACKS, strict=True):
    with tab:
        shown = False
        for oid in ids:
            card = all_cards.get(oid)
            if card is None:
                continue
            shown = True
            if oid == "verification_assurance":
                st.caption(t("tw.ifrs_assurance_note", lang))
            render_obligation_result_card(
                card,
                lang,
                show_actions=not presented.action_summary.customer_action_required,
                show_missing=False,
            )
        if not shown:
            st.info(t("tw.track.empty", lang))
