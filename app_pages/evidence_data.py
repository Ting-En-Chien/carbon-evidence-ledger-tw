"""Evidence Records — source-document evidence register inside Evidence & Data."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.components import (
    inject_design_system,
    render_empty_state,
    render_page_header,
    render_page_help,
    render_section_header,
)
from carbon_ledger.ui.evidence_workspace import (
    TAB_RECORDS,
    render_evidence_workspace_nav,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_current_result, get_language
from carbon_ledger.ui.view_models import evidence_documents_table

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

render_page_header(t("ev.title", lang), t("ev.subtitle", lang))
render_evidence_workspace_nav(lang, TAB_RECORDS)
render_section_header(t("ev.tab.records", lang), t("ev.tab.records_help", lang))
render_page_help(t("ev.records_help", lang))

if result is None:
    st.error(t("error.analysis_failed", lang))
    st.stop()

docs = evidence_documents_table(result)
if docs.empty:
    render_empty_state(t("ev.tab.records", lang), t("iss.empty", lang))
else:
    st.dataframe(docs, hide_index=True, width="stretch")
