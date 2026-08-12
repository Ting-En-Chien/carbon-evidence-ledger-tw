"""Applicability — Stage 2 shell (no guessed regulatory conclusions)."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.components import (
    inject_design_system,
    render_page_header,
    render_page_help,
    render_section_header,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_language

inject_design_system()
lang = get_language(st.session_state)

render_page_header(t("apl.title", lang), t("apl.subtitle", lang))
render_page_help(t("apl.help", lang))

render_section_header(t("apl.company_profile", lang))
st.info(t("apl.company_profile_help", lang))
st.caption(t("app.coming_next_stage", lang))

obligation_keys = (
    "apl.obligation_ifrs",
    "apl.obligation_inventory",
    "apl.obligation_verification",
    "apl.obligation_carbon_fee",
)

render_section_header(t("apl.title", lang))
for key in obligation_keys:
    with st.container(border=True):
        st.markdown(f"**{t(key, lang)}**")
        st.markdown(
            f"{t('app.needs_information', lang)} · "
            f"{t('app.rule_not_implemented', lang)}"
        )
        st.caption(t("app.coming_next_stage", lang))
