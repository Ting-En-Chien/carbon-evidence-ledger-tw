"""Taiwan GHG / Carbon Fee — Stage 2 structural shell (three separate tracks)."""

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

render_page_header(t("tw.title", lang), t("tw.subtitle", lang))
render_page_help(t("tw.help", lang))

for title_key in ("tw.inventory", "tw.verification", "tw.carbon_fee"):
    render_section_header(t(title_key, lang))
    with st.container(border=True):
        st.markdown(f"**{t('app.needs_information', lang)}**")
        st.caption(t("app.rule_not_implemented", lang))
        st.write(t("tw.section_help", lang))
        st.caption(t("app.coming_next_stage", lang))
