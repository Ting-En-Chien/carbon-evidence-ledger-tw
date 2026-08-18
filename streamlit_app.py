"""Carbon Evidence Ledger — bilingual professional Streamlit application.

Stage 3B.3: CUSTOMER / DEMO / ADMIN product modes.
Default CUSTOMER starts empty; demo requires explicit activation.
Admin monitoring details require CEL_APP_MODE=admin.
"""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.app_mode import is_admin_mode, is_demo_mode
from carbon_ledger.ui.components import (
    inject_design_system,
    render_analysis_settings,
    render_global_header,
    render_sidebar_help,
    render_sidebar_source,
)
from carbon_ledger.ui.enterprise import render_sidebar_context
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import (
    ANALYSIS_PHASE_ANALYZING,
    ANALYSIS_PHASE_COMPLETE,
    ANALYSIS_PHASE_FAILED,
    analysis_phase,
    consume_analysis_run_requests,
    launch_analysis_progress_dialog,
    should_open_analysis_progress_dialog,
)
from carbon_ledger.ui.state import (
    REPO_ROOT,
    STATE_ANALYSIS_RUNNING,
    STATE_INCLUDE_GHG,
    STATE_INCLUDE_IFRS,
    STATE_NAVIGATE_TO_RESULTS,
    STATE_RUN_ANALYSIS_REQUEST,
    STATE_RUN_UPLOADED_REQUEST,
    STATE_UPLOADED_ANALYSIS_COMPLETED,
    get_analysis_source_summary,
    get_company_profile_mapping,
    get_current_result,
    get_language,
    get_ui_error,
    has_validated_uploaded_data,
    initialize_ui_state,
    is_uploaded_analysis,
)
from carbon_ledger.ui.tutorial import maybe_show_tutorial
from carbon_ledger.ui.view_models_compliance import regulatory_freshness_banner

st.set_page_config(
    page_title="Carbon Evidence Ledger",
    layout="wide",
    initial_sidebar_state="auto",
)

inject_design_system()
initialize_ui_state(st.session_state)
lang = get_language(st.session_state)

if "ui_checkbox_ghg" not in st.session_state:
    st.session_state["ui_checkbox_ghg"] = bool(
        st.session_state.get(STATE_INCLUDE_GHG, True)
    )
if "ui_checkbox_ifrs" not in st.session_state:
    st.session_state["ui_checkbox_ifrs"] = bool(
        st.session_state.get(STATE_INCLUDE_IFRS, True)
    )
# V1: CBAM not exposed; keep key false for any legacy session state.
st.session_state["ui_checkbox_cbam"] = False

render_global_header(lang)
_phase = analysis_phase(st.session_state)
_analysis_busy = (
    bool(st.session_state.get(STATE_ANALYSIS_RUNNING))
    or _phase
    in {
        ANALYSIS_PHASE_ANALYZING,
        ANALYSIS_PHASE_COMPLETE,
        ANALYSIS_PHASE_FAILED,
    }
    or bool(st.session_state.get(STATE_RUN_UPLOADED_REQUEST))
    or bool(st.session_state.get(STATE_RUN_ANALYSIS_REQUEST))
)
if not _analysis_busy:
    maybe_show_tutorial(st.session_state, lang)

if is_demo_mode(st.session_state) or (
    get_analysis_source_summary(st.session_state).get("is_demo")
):
    st.markdown(
        f'<div class="cel-demo-banner"><span class="cel-badge">'
        f'{t("common.demo_badge", lang)}</span></div>',
        unsafe_allow_html=True,
    )

overview_page = st.Page(
    "app_pages/dashboard.py",
    title=t("nav.dashboard", lang),
    icon=":material/dashboard:",
    default=True,
)
applicability_page = st.Page(
    "app_pages/applicability.py",
    title=t("nav.applicability", lang),
    icon=":material/rule:",
)
ifrs_page = st.Page(
    "app_pages/frameworks.py",
    title=t("nav.ifrs", lang),
    icon=":material/account_tree:",
)
taiwan_page = st.Page(
    "app_pages/taiwan_ghg.py",
    title=t("nav.taiwan", lang),
    icon=":material/public:",
)
# Evidence & Data lands on Data Upload (intake) so Excel/CSV is immediately visible.
evidence_page = st.Page(
    "app_pages/data_intake.py",
    title=t("nav.evidence", lang),
    icon=":material/folder_open:",
)
reporting_page = st.Page(
    "app_pages/audit_export.py",
    title=t("nav.audit", lang),
    icon=":material/fact_check:",
)
# Sibling Evidence workspace pages: reachable via in-page tabs / switch_page only.
activity_page = st.Page(
    "app_pages/activity_explorer.py",
    title=t("nav.activity", lang),
    icon=":material/table_view:",
    visibility="hidden",
)
issues_page = st.Page(
    "app_pages/issues_actions.py",
    title=t("nav.issues", lang),
    icon=":material/error_outline:",
    visibility="hidden",
)
evidence_records_page = st.Page(
    "app_pages/evidence_data.py",
    title=t("ev.tab.records", lang),
    icon=":material/folder_open:",
    visibility="hidden",
)

# Flat list: exactly six visible primary destinations (no section headers).
navigation = st.navigation(
    [
        overview_page,
        applicability_page,
        ifrs_page,
        taiwan_page,
        evidence_page,
        reporting_page,
        activity_page,
        issues_page,
        evidence_records_page,
    ],
    position="sidebar",
)

source_summary = get_analysis_source_summary(st.session_state)
prefer_uploaded = has_validated_uploaded_data(st.session_state)
active_uploaded = is_uploaded_analysis(st.session_state)
uploaded_completed = bool(
    st.session_state.get(STATE_UPLOADED_ANALYSIS_COMPLETED)
) or active_uploaded
has_result = get_current_result(st.session_state) is not None

if prefer_uploaded or active_uploaded:
    source_label = str(
        st.session_state.get("uploaded_file_name")
        or source_summary.get("file_name")
        or t("sidebar.source_uploaded", lang)
    )
    period_start = source_summary.get("period_start")
    period_end = source_summary.get("period_end")
    if (active_uploaded or uploaded_completed) and period_start and period_end:
        source_detail = f"{period_start} — {period_end}"
    else:
        source_detail = t("sidebar.source_uploaded", lang)
    run_uploaded_mode = True
    if uploaded_completed and has_result:
        run_label = t("sidebar.rerun", lang)
    else:
        run_label = t("sidebar.run_uploaded", lang)
elif source_summary.get("is_demo") and has_result:
    source_label = t("sidebar.source_demo", lang)
    source_detail = t("sidebar.reporting_context", lang)
    run_uploaded_mode = False
    run_label = t("sidebar.rerun", lang)
else:
    source_label = t("empty.no_upload_title", lang)
    source_detail = t("sidebar.source_empty_detail", lang)
    run_uploaded_mode = False
    run_label = t("sidebar.run", lang)

with st.sidebar:
    profile = get_company_profile_mapping(st.session_state)
    freshness = regulatory_freshness_banner(REPO_ROOT, lang=lang)
    fy_value = profile.get("reporting_year")
    if not fy_value:
        period_end = str(source_summary.get("period_end") or "")
        fy_value = period_end[:4] if len(period_end) >= 4 else period_end
    render_sidebar_context(
        reporting_year=fy_value,
        freshness_label=str(freshness.get("state_label") or ""),
        lang=lang,
    )
    st.divider()
    render_sidebar_source(
        lang,
        source_label=source_label,
        source_detail=source_detail,
        is_demo=bool(source_summary.get("is_demo")),
    )

    # Customer: adapters follow applicability / product defaults — no toggle chaos.
    # Advanced / admin may still adjust analysis modules.
    if is_admin_mode(st.session_state):
        flags = render_analysis_settings(lang)
        include_ghg = flags["include_ghg"]
        include_ifrs = flags["include_ifrs"]
    else:
        include_ghg = bool(st.session_state.get(STATE_INCLUDE_GHG, True))
        include_ifrs = bool(st.session_state.get(STATE_INCLUDE_IFRS, True))
    include_cbam = False

    # Re-run only when an analysis already exists (or uploaded data is ready).
    show_start_uploaded = prefer_uploaded and not uploaded_completed
    show_rerun = has_result and (
        uploaded_completed or bool(source_summary.get("is_demo"))
    )
    if show_start_uploaded or show_rerun:
        run_clicked = st.button(
            run_label,
            type="primary",
            use_container_width=True,
            key="sidebar_run_analysis",
            disabled=_analysis_busy,
        )
    else:
        run_clicked = False

    st.divider()
    render_sidebar_help(lang)

    error = get_ui_error(st.session_state)
    if error and is_admin_mode(st.session_state):
        st.error(error)
    elif error:
        st.error(t("error.analysis_failed_safe", lang))

requested, requested_uploaded = consume_analysis_run_requests(st.session_state)
if requested:
    run_clicked = True
    if requested_uploaded is not None:
        run_uploaded_mode = requested_uploaded

if should_open_analysis_progress_dialog(
    st.session_state, run_clicked=run_clicked
):
    launch_analysis_progress_dialog(
        st.session_state,
        lang=lang,
        uploaded_mode=run_uploaded_mode,
        include_ghg=include_ghg,
        include_cbam=include_cbam,
        include_ifrs_s2=include_ifrs,
    )
    # Do not mount result KPIs under the progress overlay. The dialog script
    # reruns into the results view, where count-up starts from zero.
    st.stop()

if st.session_state.get(STATE_NAVIGATE_TO_RESULTS):
    st.session_state[STATE_NAVIGATE_TO_RESULTS] = False
    st.switch_page("app_pages/dashboard.py")

navigation.run()
