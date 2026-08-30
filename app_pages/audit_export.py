"""Emissions reports & exports — management PDF first, technical files last."""

from __future__ import annotations

import html
from dataclasses import replace
from pathlib import Path

import streamlit as st

from carbon_ledger.export import SCHEMA_VERSION
from carbon_ledger.ui.app_mode import is_admin_mode
from carbon_ledger.ui.components import (
    inject_design_system,
    period_range_inner_html,
    render_empty_state,
    render_kpi_card,
    render_section_header,
)
from carbon_ledger.ui.downloads import (
    audit_bundle_filename,
    build_audit_bundle_zip,
    build_qa_issues_csv_bytes,
)
from carbon_ledger.ui.emissions_report import (
    build_emissions_report_from_session,
    emissions_report_filename,
    format_report_generated_at,
    format_tco2e,
    now_report_generated_at,
)
from carbon_ledger.ui.emissions_report_pdf import render_emissions_summary_pdf
from carbon_ledger.ui.emissions_report_scope import (
    confirmed_company_display_name,
    confirmed_reporting_period,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    get_current_result,
    get_language,
    is_synthetic_analysis,
)
from carbon_ledger.ui.view_models import (
    audit_summary,
    official_reference_status_view,
)

STATE_PDF_CACHE = "cel_emissions_pdf_cache"

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

company_ok = bool(confirmed_company_display_name(st.session_state))
period_ok = confirmed_reporting_period(st.session_state) is not None

if result is None and not company_ok:
    render_empty_state(
        t("report.empty.no_company_title", lang),
        t("report.empty.no_company_body", lang),
    )
    if st.button(
        t("report.empty.cta_company", lang),
        type="primary",
        key="aud_empty_setup",
    ):
        st.switch_page("app_pages/applicability.py")
    st.stop()

if result is None:
    render_empty_state(
        t("report.empty.no_result_title", lang),
        t("report.empty.no_result_body", lang),
    )
    if st.button(
        t("report.empty.cta_intake", lang),
        type="primary",
        key="aud_empty_intake",
    ):
        st.switch_page("app_pages/data_intake.py")
    st.stop()

if not company_ok:
    render_empty_state(
        t("report.empty.no_company_title", lang),
        t("report.empty.no_company_body", lang),
    )
    if st.button(
        t("report.empty.cta_company", lang),
        type="primary",
        key="aud_result_needs_company",
    ):
        st.switch_page("app_pages/applicability.py")
    st.stop()

if not period_ok:
    render_empty_state(
        t("report.empty.no_period_title", lang),
        t("report.empty.no_period_body", lang),
    )
    if st.button(
        t("report.empty.cta_period", lang),
        type="primary",
        key="aud_result_needs_period",
    ):
        st.switch_page("app_pages/applicability.py")
    st.stop()

synthetic = is_synthetic_analysis(st.session_state)
if synthetic:
    st.caption(t("common.demo_badge", lang))

model = build_emissions_report_from_session(st.session_state, lang=lang)
if model is None:
    render_empty_state(
        t("report.empty.no_period_title", lang)
        if company_ok
        else t("report.empty.no_company_title", lang),
        t("report.empty.no_period_body", lang)
        if company_ok
        else t("report.empty.no_company_body", lang),
    )
    if st.button(
        t("report.empty.cta_period", lang)
        if company_ok
        else t("report.empty.cta_company", lang),
        type="primary",
        key="aud_model_needs_scope",
    ):
        st.switch_page("app_pages/applicability.py")
    st.stop()

def _kpi_html(label: str, value: str) -> str:
    return (
        '<div class="cel-kpi-card">'
        f'<p class="cel-kpi-label">{html.escape(label)}</p>'
        '<p class="cel-kpi-metric">'
        f'<span class="cel-kpi-value">{period_range_inner_html(value)}</span></p></div>'
    )


status_kind = "success" if model.complete else "warning"
included_value = t(
    "report.kpi.included_value",
    lang,
    included=model.included_rows,
    total=model.population_rows,
)
st.markdown(
    f"""
    <div class="cel-report-hero">
      <span class="cel-status cel-status-{status_kind}">
        {html.escape(model.status_label)}
      </span>
    </div>
    <div class="cel-report-kpis">
      {_kpi_html(t("report.kpi.total", lang), format_tco2e(model.total_tco2e, lang))}
      {_kpi_html(t("dash.kpi.scope1", lang), format_tco2e(model.scope_1_tco2e, lang))}
      {_kpi_html(model.scope_2_method, format_tco2e(model.scope_2_tco2e, lang))}
      {_kpi_html(t("report.cover.period", lang), model.reporting_period)}
      {_kpi_html(t("report.cover.coverage", lang), model.data_coverage_period or "—")}
      {_kpi_html(t("report.kpi.included", lang), included_value)}
      {_kpi_html(t("report.kpi.pending", lang), str(model.pending_rows))}
      {_kpi_html(t("report.kpi.documents", lang), str(model.source_documents))}
    </div>
    """,
    unsafe_allow_html=True,
)

render_section_header(t("report.card_title", lang), t("report.card_help", lang))

cache = st.session_state.get(STATE_PDF_CACHE) or {}
cache_key = f"{model.fingerprint}:{lang}"
if cache.get("key") != cache_key:
    with st.status(t("report.generating", lang), expanded=True) as status:
        stamped = replace(
            model,
            generated_at=format_report_generated_at(
                now_report_generated_at(), lang
            ),
        )
        pdf_bytes = render_emissions_summary_pdf(stamped)
        filename = emissions_report_filename(
            company=stamped.company_name,
            period=stamped.reporting_period,
        )
        st.session_state[STATE_PDF_CACHE] = {
            "key": cache_key,
            "bytes": pdf_bytes,
            "name": filename,
            "generated_at": stamped.generated_at,
        }
        status.update(label=t("report.ready", lang), state="complete")
else:
    pdf_bytes = cache["bytes"]
    filename = cache["name"]

st.download_button(
    label=t("report.pdf_button", lang),
    data=pdf_bytes,
    file_name=filename,
    mime="application/pdf",
    type="primary",
    key=f"aud_pdf_dl_{lang}",
)

summary = audit_summary(result)
has_issues = summary["qa_issues"] > 0

with st.expander(t("report.technical_files", lang), expanded=False):
    st.caption(t("report.technical_help", lang))
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
    try:
        zip_bytes = build_audit_bundle_zip(result, synthetic_demo=synthetic)
        st.download_button(
            label=t("aud.zip_button", lang),
            data=zip_bytes,
            file_name=audit_bundle_filename(result.run_id),
            mime="application/zip",
            key="aud_zip_dl",
        )
    except Exception:
        st.error(t("error.export_failed", lang))
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
