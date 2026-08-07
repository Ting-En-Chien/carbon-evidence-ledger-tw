"""Audit & Export — download-first audit presentation."""

from __future__ import annotations

import json

import streamlit as st

from carbon_ledger.export import SCHEMA_VERSION
from carbon_ledger.ui.components import (
    inject_design_system,
    render_empty_state,
    render_kpi_card,
    render_page_header,
    render_page_help,
    render_section_header,
)
from carbon_ledger.ui.downloads import (
    audit_bundle_filename,
    build_audit_bundle_zip,
    build_qa_issues_csv_bytes,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_current_result, get_language
from carbon_ledger.ui.view_models import audit_summary, evidence_documents_table

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

render_page_header(t("aud.title", lang), t("aud.subtitle", lang))
render_page_help(t("aud.help", lang))

if result is None:
    st.error(t("error.analysis_failed", lang))
    st.stop()

summary = audit_summary(result)

dl_left, dl_right = st.columns(2)
with dl_left:
    st.markdown(
        f"""
        <div class="cel-card">
          <p class="cel-download-title">{t("aud.zip_title", lang)}</p>
          <p class="cel-download-tag">ZIP</p>
          <p class="cel-issue-body">{t("aud.zip_desc", lang)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    try:
        zip_bytes = build_audit_bundle_zip(result)
        st.download_button(
            label=t("aud.zip_button", lang),
            data=zip_bytes,
            file_name=audit_bundle_filename(result.run_id),
            mime="application/zip",
            type="primary",
        )
    except Exception:
        st.error(t("error.export_failed", lang))

with dl_right:
    st.markdown(
        f"""
        <div class="cel-card">
          <p class="cel-download-title">{t("aud.csv_title", lang)}</p>
          <p class="cel-download-tag">CSV</p>
          <p class="cel-issue-body">{t("aud.csv_desc", lang)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if summary["qa_issues"] > 0:
        st.download_button(
            label=t("aud.csv_button", lang),
            data=build_qa_issues_csv_bytes(result),
            file_name=f"core_qa_issues_{result.run_id}.csv",
            mime="text/csv",
        )
    else:
        st.caption(t("iss.empty", lang))

st.write("")
render_section_header(t("aud.info_title", lang))
info_cols = st.columns(5)
adapters = []
if summary["include_ghg"]:
    adapters.append("GHG")
if summary["include_cbam"]:
    adapters.append("CBAM")
if summary["include_ifrs_s2"]:
    adapters.append("IFRS S2")
with info_cols[0]:
    render_kpi_card(summary["run_id"], t("aud.run_id", lang))
with info_cols[1]:
    render_kpi_card(summary["accepted_activities"], t("aud.activities", lang))
with info_cols[2]:
    render_kpi_card(summary["calculation_rows"], t("aud.calculations", lang))
with info_cols[3]:
    render_kpi_card(summary["qa_issues"], t("aud.issues", lang))
with info_cols[4]:
    render_kpi_card(", ".join(adapters) or "—", t("aud.enabled", lang))

st.write("")
render_section_header(t("aud.evidence_title", lang))
docs = evidence_documents_table(result)
if docs.empty:
    render_empty_state(t("aud.evidence_title", lang), t("iss.empty", lang))
else:
    st.dataframe(docs, hide_index=True, width="stretch")

st.write("")
with st.expander(t("aud.advanced", lang), expanded=False):
    manifest_preview = {
        "run_id": result.run_id,
        "schema_version": SCHEMA_VERSION,
        "synthetic_demo": True,
        "ingested_at": summary["ingested_at"],
        "adapters": {
            "ghg_protocol": result.include_ghg,
            "eu_cbam": result.include_cbam,
            "ifrs_s2": result.include_ifrs_s2,
        },
        "summary": {
            "accepted_source_documents": summary["accepted_source_documents"],
            "accepted_activities": summary["accepted_activities"],
            "calculation_rows": summary["calculation_rows"],
            "qa_issues": summary["qa_issues"],
        },
    }
    st.json(manifest_preview)
    st.code(json.dumps(manifest_preview, indent=2, sort_keys=True), language="json")
