"""Evidence Records — customer-friendly register with progressive drill-down."""

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
from carbon_ledger.ui.view_models import (
    evidence_documents_customer_view,
    evidence_documents_table,
)

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

render_page_header(t("ev.title", lang), t("ev.subtitle", lang))
render_evidence_workspace_nav(lang, TAB_RECORDS)
render_section_header(t("ev.tab.records", lang), t("ev.tab.records_help", lang))
render_page_help(t("ev.records_help", lang))

if result is None:
    render_empty_state(
        t("empty.no_upload_title", lang),
        t("empty.no_upload_body", lang),
    )
    if st.button(t("nav.evidence", lang), key="ev_empty_upload"):
        st.switch_page("app_pages/data_intake.py")
    st.stop()

full = evidence_documents_table(result, lang)
customer = evidence_documents_customer_view(result, lang)
if customer.empty:
    render_empty_state(t("ev.tab.records", lang), t("iss.empty", lang))
    st.stop()

st.caption(t("ev.reuse_help", lang))
event = st.dataframe(
    customer,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    key="evidence_records_table",
)

selected_rows = []
if event is not None and getattr(event, "selection", None) is not None:
    selected_rows = list(event.selection.rows)
index = selected_rows[0] if selected_rows else 0
row = full.iloc[index]

st.write("")
render_section_header(t("ev.drill.title", lang))
st.markdown(f"**{t('ev.col.name', lang)}**")
st.write(row.get("file_name") or "—")
st.markdown(f"**{t('ev.reuse_title', lang)}**")
st.write(row.get("used_for") or t("ev.reuse.none", lang))

with st.expander(t("ev.drill.usage", lang), expanded=True):
    st.write(row.get("used_for") or t("ev.reuse.none", lang))
    st.caption(t("ev.col.status", lang) + f"：{row.get('status') or '—'}")

with st.expander(t("ev.drill.source", lang), expanded=False):
    st.markdown(f"**{t('ev.col.source', lang)}**")
    st.write(row.get("source_name") or "—")
    st.markdown(f"**{t('ev.col.type', lang)}**")
    st.write(row.get("document_type_label") or "—")
    st.markdown(f"**{t('ev.col.period', lang)}**")
    st.write(row.get("period") or "—")
    st.markdown(f"**{t('ev.col.data_origin', lang)}**")
    origin = str(row.get("data_origin") or "")
    if origin in {"synthetic", "synthetic_demo", "demo"} or row.get("is_synthetic"):
        st.write(t("ev.status.demo", lang))
    else:
        st.write(t("ev.origin.company", lang))

with st.expander(t("ev.drill.audit", lang), expanded=False):
    st.write(
        {
            "source_document_id": row.get("source_document_id"),
            "sha256": row.get("sha256"),
            "source_locator": row.get("source_locator"),
            "ingested_at": row.get("ingested_at"),
            "data_origin": row.get("data_origin"),
            "document_date": row.get("document_date"),
        }
    )
