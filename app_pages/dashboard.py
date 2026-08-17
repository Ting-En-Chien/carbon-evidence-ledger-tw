"""Compliance Overview — customer-first post-analysis home."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.charts import (
    render_emissions_source_bars,
    render_monthly_emissions_trend,
)
from carbon_ledger.ui.components import (
    inject_design_system,
    render_section_header,
    render_viz_panel_end,
    render_viz_panel_start,
)
from carbon_ledger.ui.enterprise import (
    inject_enterprise_styles,
    render_greeting_block,
    render_regulatory_status_chip,
    render_workflow_journey,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import (
    analysis_phase,
    animation_run_token,
    consume_result_reveal,
    hero_emissions_should_play,
    mark_chart_reveal,
    render_animated_metric,
    render_hero_result_kpis,
    schedule_countup_runtime,
)
from carbon_ledger.ui.state import (
    ANALYSIS_PHASE_ANALYZING,
    ANALYSIS_PHASE_COMPLETE,
    ANALYSIS_PHASE_FAILED,
    REPO_ROOT,
    STATE_ANALYSIS_RUNNING,
    get_analysis_source_summary,
    get_applicability_assessment,
    get_company_profile_mapping,
    get_current_result,
    get_language,
    is_uploaded_analysis,
)
from carbon_ledger.ui.view_models import (
    beginner_result_summary,
    calculated_emissions_summary,
    executive_emissions_insights,
    scope_kpi_states,
    should_show_coverage_chart,
    should_show_unresolved_cta,
)
from carbon_ledger.ui.view_models_compliance import (
    home_requirement_summary,
    regulatory_freshness_banner,
)

inject_design_system()
inject_enterprise_styles()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)
_phase = analysis_phase(st.session_state)
if bool(st.session_state.get(STATE_ANALYSIS_RUNNING)) or _phase in {
    ANALYSIS_PHASE_ANALYZING,
    ANALYSIS_PHASE_COMPLETE,
    ANALYSIS_PHASE_FAILED,
}:
    # Keep result KPIs unmounted while the progress modal is still open so
    # count-up starts at 0 only after the modal closes.
    st.stop()

if result is None:
    from carbon_ledger.ui.state import activate_demo_mode

    st.markdown(
        f"""
        <p class="cel-page-kicker">{t("dash.page_title", lang)}</p>
        <h1 class="cel-page-title">{t("onboard.welcome_title", lang)}</h1>
        <p class="cel-page-sub">{t("onboard.welcome_body", lang)}</p>
        """,
        unsafe_allow_html=True,
    )
    steps = [
        t("onboard.step1", lang),
        t("onboard.step2", lang),
        t("onboard.step3", lang),
        t("onboard.step4", lang),
        t("onboard.step5", lang),
    ]
    render_workflow_journey(
        [
            {
                "label": label,
                "state": "current" if index == 0 else "todo",
            }
            for index, label in enumerate(steps)
        ],
        lang,
    )
    cta1, cta2 = st.columns([1.2, 1])
    with cta1:
        if st.button(
            t("onboard.cta_setup", lang),
            type="primary",
            use_container_width=True,
            key="onboard_start_setup",
        ):
            st.switch_page("app_pages/applicability.py")
    with cta2:
        if st.button(
            t("onboard.cta_demo", lang),
            use_container_width=True,
            key="onboard_try_demo",
        ):
            activate_demo_mode(st.session_state, force=True)
            st.rerun()
    st.caption(t("onboard.demo_note", lang))
    st.stop()

source = get_analysis_source_summary(st.session_state)
uploaded = is_uploaded_analysis(st.session_state)
animate = consume_result_reveal(st.session_state, result)
analysis_token = animation_run_token(st.session_state, result)
play_hero_count = hero_emissions_should_play(st.session_state, result)

profile = get_company_profile_mapping(st.session_state)
assessment = get_applicability_assessment(st.session_state)
company_name = str(profile.get("company_name") or "") or t(
    "dash.greeting_company_fallback", lang
)
reporting_year = profile.get("reporting_year") or source.get("period_end") or "—"

freshness = regulatory_freshness_banner(REPO_ROOT, lang=lang)
summary = beginner_result_summary(result, lang)
emissions = calculated_emissions_summary(result, lang)
value = emissions["calculated_tco2e"]
done = int(summary["calculated"])
unresolved_count = int(summary["needs_work"])
total_count = int(summary["activities"])
source_count = int(summary["source_documents"])
insights = executive_emissions_insights(result, lang)
req_summary = home_requirement_summary(assessment, lang)
show_issues = should_show_unresolved_cta(unresolved_count)
show_coverage_bar = should_show_coverage_chart(done, total_count)

st.markdown(
    f'<p class="cel-page-kicker">{t("dash.page_title", lang)}</p>',
    unsafe_allow_html=True,
)
render_greeting_block(
    company=company_name,
    reporting_year=reporting_year,
    attention_count=0,
    lang=lang,
)
render_regulatory_status_chip(freshness, lang)

# 1. 排放資料摘要
render_section_header(
    t("dash.emissions_section", lang),
    scroll_key="emissions-summary",
)
render_hero_result_kpis(
    emissions_value=value,
    emissions_label=t("dash.kpi.emissions", lang),
    emissions_subtitle="",
    done=done,
    total=total_count,
    completion_label=t("dash.kpi.completion", lang),
    completion_subtitle=t(
        "dash.emissions_ratio",
        lang,
        done=done,
        total=total_count,
    ),
    unresolved=unresolved_count,
    unresolved_label=t("dash.kpi.unresolved", lang),
    unresolved_subtitle=t("dash.kpi.unresolved_hint", lang),
    sources=source_count,
    sources_label=t("dash.kpi.source", lang),
    sources_subtitle=t("dash.kpi.source_hint", lang),
    animate=animate,
    animation_token=analysis_token,
    play_hero_count=play_hero_count,
    include_secondary_cards=False,
)
if show_issues:
    st.warning(
        "⚠ " + t("dash.issues_banner", lang, count=unresolved_count)
    )
    if show_coverage_bar:
        st.progress(float(done) / float(max(1, total_count)))
        st.caption(
            t(
                "dash.coverage_partial",
                lang,
                done=done,
                total=total_count,
            )
        )
    if st.button(t("dash.cta.view_problems", lang), key="dash_view_issues"):
        st.switch_page("app_pages/issues_actions.py")
elif uploaded:
    st.success("✓ " + t("dash.coverage_complete", lang, total=total_count))
    st.caption("✓ " + t("dash.coverage_all_done", lang))
else:
    st.success("✓ " + t("dash.coverage_complete_demo", lang))
    st.caption("✓ " + t("dash.coverage_all_done", lang))

count_cols = st.columns(2 if show_issues else 1)
with count_cols[0]:
    st.caption(t("dash.kpi.completion", lang))
    render_animated_metric(
        done,
        decimals=0,
        key="calculated-count",
        play=play_hero_count,
        run=analysis_token,
    )
if show_issues:
    with count_cols[1]:
        st.caption(t("dash.kpi.unresolved", lang))
        render_animated_metric(
            unresolved_count,
            decimals=0,
            key="unresolved-count",
            play=play_hero_count,
            run=analysis_token,
        )

# 2. Scope 分解
scope_states = scope_kpi_states(result)
render_section_header(
    t("dash.section_scope_main", lang),
    scroll_key="scope-breakdown",
)
scope_cols = st.columns(3)


def _render_scope_kpi(
    scope_key: str, label_key: str, plain_key: str, metric_key: str
) -> None:
    st.markdown(f"**{t(label_key, lang)}**")
    st.caption(t(plain_key, lang))
    state = scope_states.get(scope_key) or {}
    if state.get("state") == "calculated":
        render_animated_metric(
            float(state.get("value") or 0.0),
            decimals=2,
            suffix="tCO₂e",
            key=metric_key,
            play=play_hero_count,
            run=analysis_token,
        )
        return
    if state.get("state") == "unsupported":
        st.write(t("dash.scope3_short", lang))
        return
    st.write(t("dash.scope_pending", lang))


with scope_cols[0]:
    _render_scope_kpi(
        "scope_1", "dash.kpi.scope1", "dash.kpi.scope1_plain", "scope-1"
    )
with scope_cols[1]:
    _render_scope_kpi(
        "scope_2", "dash.kpi.scope2", "dash.kpi.scope2_plain", "scope-2"
    )
with scope_cols[2]:
    _render_scope_kpi(
        "scope_3", "dash.kpi.scope3", "dash.kpi.scope3_plain", "scope-3"
    )
with st.expander(t("dash.scope_help_title", lang), expanded=False):
    st.markdown(t("dash.scope_help_body", lang))
schedule_countup_runtime(st.session_state, play=play_hero_count)

# 3. Insights — one primary, one optional
if insights:
    st.info(insights[0])
    if len(insights) > 1:
        st.caption(insights[1])
    st.markdown(
        '<div data-cel-scroll="insight" id="cel-insight"></div>',
        unsafe_allow_html=True,
    )

# 4. 下一步 — one action, not a repeated matrix
render_section_header(t("dash.section_next", lang), scroll_key="next-step")
if req_summary["cta"] == "complete":
    st.markdown(f"**{t('dash.next.applicability', lang)}**")
    st.caption(t("dash.next.applicability_body", lang))
    if st.button(
        t("dash.cta.complete_now", lang),
        type="primary",
        key="dash_start_apl",
    ):
        st.switch_page("app_pages/applicability.py")
else:
    render_section_header(
        t("dash.section_requirements", lang),
        scroll_key="requirements",
    )
    st.markdown(f"**{t('dash.req.headline', lang)}**")
    for line in req_summary["lines"]:
        st.markdown(f"- {line}")
    if st.button(t("dash.cta.view_requirements", lang), key="dash_view_req"):
        st.switch_page("app_pages/applicability.py")

# 5. 排放明細 — one chart at a time
render_section_header(
    t("dash.section_detail", lang),
    t("dash.section_detail_help", lang),
    scroll_key="detail",
)
source_tab = t("dash.detail.source", lang)
trend_tab = t("dash.detail.trend", lang)
selected_detail = st.segmented_control(
    t("dash.cta.view_detail", lang),
    options=[source_tab, trend_tab],
    default=source_tab,
    key="dash_emission_detail_tab",
)
if selected_detail == trend_tab:
    render_viz_panel_start(
        t("dash.detail.trend_title", lang),
        scroll_key="trend",
        chart_kind="trend",
    )
    mark_chart_reveal("trend", chart="trend")
    render_monthly_emissions_trend(result, lang)
    render_viz_panel_end()
else:
    render_viz_panel_start(
        t("dash.section_sources", lang),
        scroll_key="sources",
        chart_kind="bars",
    )
    mark_chart_reveal("sources", chart="bars")
    render_emissions_source_bars(result, lang)
    render_viz_panel_end()

# 6. Professional detail on request
with st.expander(t("dash.coverage_learn", lang), expanded=False):
    st.markdown(
        '<div data-cel-scroll="professional" id="cel-professional"></div>',
        unsafe_allow_html=True,
    )
    st.write(t("dash.coverage_learn_body", lang))
    st.caption(t("dash.emissions_notice", lang))
    period_start = source.get("period_start")
    period_end = source.get("period_end")
    if period_start and period_end:
        st.caption(
            t(
                "dash.period_line",
                lang,
                start=period_start,
                end=period_end,
            )
        )
    st.caption(t("dash.source_files_line", lang, count=source_count))
    if st.button(
        t("dash.cta.view_calc_basis", lang),
        key="dash_go_activity",
    ):
        st.switch_page("app_pages/activity_explorer.py")
    if st.button(
        t("dash.cta.view_evidence", lang),
        key="dash_go_evidence_records",
    ):
        st.switch_page("app_pages/evidence_data.py")
