"""Reporting & Export — business outputs first; admin/advanced technical last."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from carbon_ledger.export import SCHEMA_VERSION
from carbon_ledger.ui.app_mode import is_admin_mode
from carbon_ledger.ui.components import (
    inject_design_system,
    render_empty_state,
    render_kpi_card,
    render_section_header,
)
from carbon_ledger.ui.downloads import (
    audit_bundle_filename,
    build_audit_bundle_zip,
    build_qa_issues_csv_bytes,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    get_current_result,
    get_language,
    is_synthetic_analysis,
)
from carbon_ledger.ui.view_models import (
    audit_summary,
    evidence_documents_customer_view,
    official_reference_status_view,
)

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)
admin = is_admin_mode(st.session_state)

st.markdown(
    f"""
    <p class="cel-page-kicker">{t("nav.audit", lang)}</p>
    <h1 class="cel-page-title">{t("aud.title", lang)}</h1>
    <p class="cel-page-sub">{t("aud.subtitle", lang)}</p>
    """,
    unsafe_allow_html=True,
)
st.caption(t("aud.workpaper_note", lang))

if result is None:
    render_empty_state(
        t("empty.no_analysis_title", lang),
        t("empty.no_analysis_body", lang),
    )
    if st.button(t("onboard.cta_setup", lang), key="aud_empty_setup"):
        st.switch_page("app_pages/applicability.py")
    st.stop()

synthetic = is_synthetic_analysis(st.session_state)
if synthetic:
    st.caption(t("common.demo_badge", lang))

summary = audit_summary(result)
has_issues = summary["qa_issues"] > 0

# A — For leadership
render_section_header(
    t("aud.ask.management", lang),
    t("aud.group.management", lang),
)
st.caption(t("aud.group.management_help", lang))
mgmt_cols = st.columns(3)
with mgmt_cols[0]:
    render_kpi_card(summary["accepted_activities"], t("aud.activities", lang))
with mgmt_cols[1]:
    render_kpi_card(summary["accepted_source_documents"], t("aud.evidence_title", lang))
with mgmt_cols[2]:
    render_kpi_card(summary["qa_issues"], t("aud.issues", lang))
st.info(t("aud.group.management_unavailable", lang))

# B — Prepare IFRS
render_section_header(t("aud.ask.ifrs", lang), t("aud.group.ifrs", lang))
st.caption(t("aud.group.ifrs_body", lang))
if st.button(t("dash.cta.view_ifrs", lang), key="aud_go_ifrs"):
    st.switch_page("app_pages/frameworks.py")

# C — Inventory / verification
render_section_header(t("aud.ask.ghg", lang), t("aud.group.evidence", lang))
docs = evidence_documents_customer_view(result, lang)
if docs.empty:
    render_empty_state(t("aud.evidence_title", lang), t("iss.empty", lang))
else:
    st.dataframe(docs, hide_index=True, width="stretch")

# D — Analyze yourself
render_section_header(t("aud.ask.data", lang), t("aud.group.data", lang))
if has_issues:
    st.download_button(
        label=t("aud.csv_button", lang),
        data=build_qa_issues_csv_bytes(result),
        file_name="core_qa_issues.csv",
        mime="text/csv",
        key="aud_csv_dl",
    )
else:
    st.caption(t("iss.empty", lang))

# E — For auditors
render_section_header(
    t("aud.ask.audit", lang),
    t("aud.group.audit_pkg", lang),
)
st.caption(t("aud.group.audit_pkg_body", lang))
try:
    zip_bytes = build_audit_bundle_zip(result, synthetic_demo=synthetic)
    st.download_button(
        label=t("aud.zip_button", lang),
        data=zip_bytes,
        file_name=audit_bundle_filename(result.run_id),
        mime="application/zip",
        type="primary",
        key="aud_zip_dl",
    )
except Exception:
    st.error(t("error.export_failed", lang))

# Audit trace → technical identifiers (collapsed). Registry stays ADMIN-only.
with st.expander(t("aud.audit_trace", lang), expanded=False):
    st.caption(t("aud.advanced_customer_note", lang))
    with st.expander(t("aud.tech_ids", lang), expanded=False):
        info_cols = st.columns(3)
        with info_cols[0]:
            render_kpi_card(summary["run_id"], t("aud.run_id", lang))
        with info_cols[1]:
            render_kpi_card(
                summary["accepted_activities"], t("aud.activities", lang)
            )
        with info_cols[2]:
            ingested = summary["ingested_at"]
            render_kpi_card(
                ingested if ingested != "unavailable" else "—",
                t("aud.ingested_at", lang),
            )
        if admin:
            render_section_header(t("aud.ref_title", lang), t("aud.ref_help", lang))
            ref_status = official_reference_status_view(Path.cwd(), lang)
            st.markdown(
                f"**{t('aud.ref_last_checked', lang)}:** "
                f"{ref_status['last_checked_at']}"
            )
            ref_cols = st.columns(2)
            with ref_cols[0]:
                st.markdown(f"**{t('aud.ref_electricity', lang)}**")
                for row in ref_status["electricity_rows"]:
                    st.write(f"{row['year']} — {row['label']}")
            with ref_cols[1]:
                st.markdown(f"**{t('aud.ref_heating', lang)}**")
                for row in ref_status["heating_rows"]:
                    st.write(f"{row['fuel']} — {row['latest_year']}")
            adapters = []
            if summary["include_ghg"]:
                adapters.append("GHG")
            if summary["include_ifrs_s2"]:
                adapters.append("IFRS S2")
            st.json(
                {
                    "run_id": result.run_id,
                    "schema_version": SCHEMA_VERSION,
                    "synthetic_demo": synthetic,
                    "ingested_at": summary["ingested_at"],
                    "adapters": {
                        "ghg_protocol": result.include_ghg,
                        "eu_cbam": result.include_cbam,
                        "ifrs_s2": result.include_ifrs_s2,
                    },
                    "summary": {
                        "accepted_source_documents": summary[
                            "accepted_source_documents"
                        ],
                        "accepted_activities": summary["accepted_activities"],
                        "calculation_rows": summary["calculation_rows"],
                        "qa_issues": summary["qa_issues"],
                        "enabled": adapters,
                    },
                }
            )
        else:
            st.caption(t("aud.advanced_admin_only", lang))
