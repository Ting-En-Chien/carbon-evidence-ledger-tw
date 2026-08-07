"""Carbon Evidence Ledger — bilingual professional Streamlit application.

Phase 9A adds structured CSV/XLSX company-data intake.
Demo pipeline accounting logic stays unchanged until Phase 9B.
"""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.components import (
    inject_design_system,
    render_global_header,
    render_sidebar_controls,
    render_sidebar_help,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_INCLUDE_CBAM,
    STATE_INCLUDE_GHG,
    STATE_INCLUDE_IFRS,
    STATE_RUN_ANALYSIS_REQUEST,
    get_language,
    get_ui_error,
    initialize_ui_state,
    run_analysis,
)
from carbon_ledger.ui.tutorial import maybe_show_tutorial

st.set_page_config(
    page_title="Carbon Evidence Ledger",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_design_system()
initialize_ui_state(st.session_state)
lang = get_language(st.session_state)

if "ui_checkbox_ghg" not in st.session_state:
    st.session_state["ui_checkbox_ghg"] = bool(
        st.session_state.get(STATE_INCLUDE_GHG, True)
    )
if "ui_checkbox_cbam" not in st.session_state:
    st.session_state["ui_checkbox_cbam"] = bool(
        st.session_state.get(STATE_INCLUDE_CBAM, True)
    )
if "ui_checkbox_ifrs" not in st.session_state:
    st.session_state["ui_checkbox_ifrs"] = bool(
        st.session_state.get(STATE_INCLUDE_IFRS, True)
    )

render_global_header(lang)
maybe_show_tutorial(st.session_state, lang)

dashboard_page = st.Page(
    "app_pages/dashboard.py",
    title=t("nav.dashboard", lang),
    icon=":material/dashboard:",
    default=True,
)
intake_page = st.Page(
    "app_pages/data_intake.py",
    title=t("nav.intake", lang),
    icon=":material/upload_file:",
)
activity_page = st.Page(
    "app_pages/activity_explorer.py",
    title=t("nav.activity", lang),
    icon=":material/table_view:",
)
issues_page = st.Page(
    "app_pages/issues_actions.py",
    title=t("nav.issues", lang),
    icon=":material/error_outline:",
)
frameworks_page = st.Page(
    "app_pages/frameworks.py",
    title=t("nav.frameworks", lang),
    icon=":material/account_tree:",
)
audit_page = st.Page(
    "app_pages/audit_export.py",
    title=t("nav.audit", lang),
    icon=":material/fact_check:",
)

navigation = st.navigation(
    [
        dashboard_page,
        intake_page,
        activity_page,
        issues_page,
        frameworks_page,
        audit_page,
    ],
    position="sidebar",
)

with st.sidebar:
    st.divider()
    flags = render_sidebar_controls(lang)
    include_ghg = flags["include_ghg"]
    include_cbam = flags["include_cbam"]
    include_ifrs = flags["include_ifrs"]

    run_clicked = st.button(
        t("sidebar.run", lang),
        type="primary",
        use_container_width=True,
        key="sidebar_run_analysis",
    )
    if st.session_state.get(STATE_RUN_ANALYSIS_REQUEST):
        run_clicked = True

    if run_clicked:
        with st.status(t("sidebar.running", lang), expanded=True) as status:
            st.write(t("sidebar.loading", lang))
            try:
                run_analysis(
                    st.session_state,
                    include_ghg=include_ghg,
                    include_cbam=include_cbam,
                    include_ifrs_s2=include_ifrs,
                )
                st.write(t("sidebar.pipeline_done", lang))
                status.update(label=t("sidebar.complete", lang), state="complete")
            except Exception:
                status.update(label=t("error.analysis_failed", lang), state="error")
                st.error(t("error.analysis_failed", lang))

    st.divider()
    render_sidebar_help(lang)

    error = get_ui_error(st.session_state)
    if error:
        st.error(t("error.analysis_failed", lang))

navigation.run()
