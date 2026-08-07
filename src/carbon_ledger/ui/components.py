"""Reusable Streamlit presentation helpers for Carbon Evidence Ledger."""

from __future__ import annotations

from typing import Any

import streamlit as st

from carbon_ledger.ui.glossary import render_glossary_popover
from carbon_ledger.ui.i18n import (
    LANG_CODE_TO_OPTION,
    LANG_OPTION_TO_CODE,
    LANG_OPTIONS,
    t,
)
from carbon_ledger.ui.state import set_language
from carbon_ledger.ui.tutorial import request_tutorial

DESIGN_CSS = """
<style>
html, body, [class*="css"],
.stApp, .stMarkdown, button, input, textarea, select {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
    "SF Pro Text", "PingFang TC", "Noto Sans TC", "Microsoft JhengHei",
    "Segoe UI", sans-serif !important;
}
:root {
  --cel-primary: #0F766E;
  --cel-primary-hover: #0D5F59;
  --cel-navy: #172A46;
  --cel-text: #0F172A;
  --cel-slate: #64748B;
  --cel-page: #F7F9FC;
  --cel-surface: #FFFFFF;
  --cel-soft: #F3F6F9;
  --cel-border: #E5EAF0;
  --cel-warning: #D97706;
  --cel-critical: #B42318;
  --cel-success: #047857;
  --cel-info: #2563EB;
  --cel-radius: 12px;
  --cel-radius-sm: 10px;
}

.stApp {
  background: var(--cel-page);
}

/* Do not force a tiny padding-top; let Streamlit clear its chrome. */
section[data-testid="stMain"] .block-container,
div[data-testid="stMainBlockContainer"] {
  padding-bottom: 2.5rem;
  max-width: 1120px;
}

/* Quiet Streamlit chrome; app toolbar owns brand utilities. */
header[data-testid="stHeader"] {
  background: transparent;
  border-bottom: none;
}
header[data-testid="stHeader"] [data-testid="stToolbar"] {
  display: none;
}

/* Sidebar shell */
section[data-testid="stSidebar"] {
  background: var(--cel-surface);
  border-right: 1px solid var(--cel-border);
  min-width: 260px !important;
  width: 260px !important;
}
section[data-testid="stSidebar"] > div {
  width: 260px !important;
}
[data-testid="stSidebar"] .block-container {
  padding-top: 0.85rem;
  padding-left: 0.85rem;
  padding-right: 0.85rem;
}
[data-testid="stSidebarNav"] {
  padding-top: 0.25rem;
}
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] span {
  font-size: 0.92rem !important;
  font-weight: 550 !important;
  color: var(--cel-slate) !important;
  border-radius: 10px !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"],
[data-testid="stSidebarNav"] [aria-selected="true"],
[data-testid="stSidebarNavLinkActive"] {
  background: #E8F5F3 !important;
  color: var(--cel-navy) !important;
  font-weight: 650 !important;
  border-left: 3px solid var(--cel-primary);
}
[data-testid="stSidebar"] label {
  font-size: 0.92rem !important;
  font-weight: 600 !important;
  color: var(--cel-text) !important;
}
[data-testid="stSidebar"] [data-testid="stCaption"] {
  color: var(--cel-slate) !important;
  font-size: 0.75rem !important;
  line-height: 1.4 !important;
}

/* Buttons */
div[data-testid="stButton"] > button[kind="primary"] {
  background: var(--cel-primary) !important;
  border: 1px solid var(--cel-primary) !important;
  color: #FFFFFF !important;
  border-radius: var(--cel-radius-sm) !important;
  font-weight: 600 !important;
  min-height: 44px;
  box-shadow: none !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
  background: var(--cel-primary-hover) !important;
  border-color: var(--cel-primary-hover) !important;
}
div[data-testid="stButton"] > button[kind="secondary"] {
  background: #FFFFFF !important;
  border: 1px solid var(--cel-border) !important;
  color: var(--cel-navy) !important;
  border-radius: var(--cel-radius-sm) !important;
  font-weight: 600 !important;
}
div[data-testid="stButton"] > button[kind="tertiary"] {
  background: transparent !important;
  border: none !important;
  color: var(--cel-navy) !important;
  font-weight: 600 !important;
  box-shadow: none !important;
  min-height: 2rem;
  padding-left: 0.1rem !important;
  padding-right: 0.1rem !important;
}
div[data-testid="stButton"] > button {
  white-space: nowrap;
  border-radius: var(--cel-radius-sm);
}

/* Language control */
div[data-testid="stSegmentedControl"] {
  background: #FFFFFF;
  border: 1px solid var(--cel-border);
  border-radius: 999px;
  padding: 2px;
}
div[data-testid="stSegmentedControl"] label,
div[data-testid="stSegmentedControl"] button {
  border-radius: 999px !important;
  font-size: 0.8rem !important;
  font-weight: 650 !important;
  min-height: 28px !important;
}
div[data-testid="stSegmentedControl"] [aria-checked="true"],
div[data-testid="stSegmentedControl"] [aria-selected="true"] {
  background: #CCFBF1 !important;
  color: var(--cel-primary) !important;
}

/* Top toolbar */
.cel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 64px;
  margin: 0 0 8px 0;
  padding: 8px 0 12px 0;
  border-bottom: 1px solid var(--cel-border);
  background: var(--cel-surface);
}
.cel-brand-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.cel-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: linear-gradient(145deg, #0F766E 0%, #172A46 100%);
  position: relative;
  flex: 0 0 auto;
}
.cel-mark::before {
  content: "";
  position: absolute;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgba(255,255,255,0.95);
  top: 7px;
  left: 7px;
}
.cel-mark::after {
  content: "";
  position: absolute;
  width: 11px;
  height: 11px;
  border: 1.5px solid rgba(255,255,255,0.9);
  border-radius: 3px;
  right: 6px;
  bottom: 6px;
}
.cel-brand-name {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--cel-navy);
  white-space: nowrap;
}

/* Page header */
.cel-page-header {
  margin: 8px 0 28px 0;
}
.cel-page-title {
  margin: 0 0 8px 0;
  font-size: 1.9rem;
  font-weight: 700;
  color: var(--cel-navy);
  letter-spacing: -0.02em;
  line-height: 1.2;
}
.cel-page-sub {
  margin: 0 0 10px 0;
  color: var(--cel-slate);
  font-size: 0.95rem;
  line-height: 1.6;
  max-width: 42rem;
}
.cel-page-hint {
  margin: 8px 0 0 0;
  color: var(--cel-slate);
  font-size: 0.86rem;
}
.cel-badge {
  display: inline-block;
  padding: 0.18rem 0.6rem;
  border: 1px solid var(--cel-border);
  border-radius: 999px;
  background: var(--cel-soft);
  color: var(--cel-slate);
  font-size: 0.75rem;
  font-weight: 650;
}

/* Section */
.cel-section {
  margin: 0 0 8px 0;
}
.cel-section-title {
  margin: 0 0 6px 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--cel-navy);
  letter-spacing: -0.015em;
  line-height: 1.25;
}
.cel-section-help {
  margin: 0 0 16px 0;
  color: var(--cel-slate);
  font-size: 0.9rem;
  line-height: 1.55;
  max-width: 40rem;
}
.cel-page-help {
  color: var(--cel-slate);
  font-size: 0.88rem;
  line-height: 1.55;
  margin: 0 0 20px 0;
  white-space: pre-line;
  max-width: 40rem;
}

/* KPI cards */
.cel-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 0 0 32px 0;
}
.cel-kpi-card {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 20px 20px 18px 20px;
  border-top: 3px solid #94A3B8;
}
.cel-kpi-card.cel-accent-teal { border-top-color: #14B8A6; }
.cel-kpi-card.cel-accent-amber { border-top-color: #F59E0B; }
.cel-kpi-card.cel-accent-blue { border-top-color: #3B82F6; }
.cel-kpi-card.cel-accent-slate { border-top-color: #94A3B8; }
.cel-kpi-card.cel-accent-coral { border-top-color: #F97316; }
.cel-viz-panel {
  background: #F3F7F8;
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 16px 16px 8px 16px;
  margin: 0 0 24px 0;
}
.cel-viz-panel-soft {
  background: #F5F4FF;
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 16px 16px 8px 16px;
  margin: 0 0 24px 0;
}
.cel-kpi-label {
  margin: 0;
  color: var(--cel-slate);
  font-size: 0.84rem;
  font-weight: 550;
}
.cel-kpi-value {
  margin: 10px 0 0 0;
  color: var(--cel-navy);
  font-size: 2rem;
  font-weight: 700;
  line-height: 1.05;
  letter-spacing: -0.02em;
}

/* Panels / cards */
.cel-panel {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 22px 24px;
  margin: 0 0 32px 0;
}
.cel-panel-title {
  margin: 0 0 14px 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-emissions-value {
  margin: 0;
  font-size: 2.1rem;
  font-weight: 700;
  color: var(--cel-navy);
  letter-spacing: -0.02em;
  line-height: 1.15;
}
.cel-emissions-meta {
  margin: 8px 0 0 0;
  color: var(--cel-slate);
  font-size: 0.88rem;
}
.cel-emissions-note {
  margin: 14px 0 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--cel-border);
  color: var(--cel-slate);
  font-size: 0.88rem;
  line-height: 1.6;
}

.cel-status {
  display: inline-flex;
  align-items: center;
  padding: 0.16rem 0.55rem;
  border-radius: 999px;
  border: 1px solid var(--cel-border);
  font-size: 0.74rem;
  font-weight: 650;
  background: #FFFFFF;
  color: var(--cel-text);
}
.cel-status-success {
  color: var(--cel-success);
  border-color: #A7F3D0;
  background: #ECFDF5;
}
.cel-status-warning {
  color: var(--cel-warning);
  border-color: #FDE68A;
  background: #FFFBEB;
}
.cel-status-critical {
  color: var(--cel-critical);
  border-color: #FECACA;
  background: #FEF2F2;
}
.cel-status-info {
  color: var(--cel-info);
  border-color: #BFDBFE;
  background: #EFF6FF;
}
.cel-status-attention {
  color: #C2410C;
  border-color: #FDBA74;
  background: #FFF7ED;
}
.cel-status-muted { color: var(--cel-slate); }

.cel-issue-card {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 16px 16px 12px 16px;
  height: 100%;
  min-height: 0;
  border-left: 3px solid var(--cel-warning);
}
.cel-issue-card.cel-issue-critical {
  border-left-color: var(--cel-critical);
}
.cel-issue-title {
  margin: 8px 0 4px 0;
  font-size: 0.98rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-issue-meta {
  margin: 0;
  color: var(--cel-slate);
  font-size: 0.84rem;
  line-height: 1.45;
}
.cel-issue-body {
  margin: 8px 0 0 0;
  color: var(--cel-text);
  font-size: 0.86rem;
  line-height: 1.5;
}

.cel-framework-notice {
  background: #EFF6FF;
  border: 1px solid #BFDBFE;
  border-radius: var(--cel-radius);
  padding: 12px 14px;
  color: var(--cel-text);
  font-size: 0.88rem;
  margin-bottom: 16px;
  line-height: 1.55;
}
.cel-empty {
  background: var(--cel-soft);
  border: 1px dashed var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 18px;
}
.cel-empty-title {
  margin: 0;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-empty-body {
  margin: 6px 0 0 0;
  color: var(--cel-slate);
  font-size: 0.88rem;
  line-height: 1.55;
}

.cel-sidebar-title {
  margin: 4px 0 8px 0;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--cel-slate);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.cel-sidebar-meta {
  margin: 0 0 2px 0;
  color: var(--cel-navy);
  font-size: 0.9rem;
  font-weight: 700;
}
.cel-sidebar-muted {
  margin: 0 0 16px 0;
  color: var(--cel-slate);
  font-size: 0.78rem;
}
.cel-module-sub {
  margin: -6px 0 10px 1.55rem;
  color: var(--cel-slate);
  font-size: 0.74rem;
  font-weight: 500;
}
.cel-card {
  background: var(--cel-surface);
  border: 1px solid var(--cel-border);
  border-radius: var(--cel-radius);
  padding: 16px 18px;
  height: 100%;
}
.cel-download-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--cel-navy);
}
.cel-download-tag {
  margin: 4px 0 6px 0;
  color: var(--cel-primary);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.03em;
}

@media (max-width: 1100px) {
  .cel-kpi-grid { grid-template-columns: 1fr 1fr; }
  .cel-page-title { font-size: 1.65rem; }
}
</style>
"""


def inject_design_system() -> None:
    """Inject application-owned CSS once per page render."""
    st.markdown(DESIGN_CSS, unsafe_allow_html=True)


def render_global_header(lang: str) -> None:
    """Render top toolbar: brand left, tutorial + language right."""
    brand, utilities = st.columns(
        [2.8, 1.2],
        gap="medium",
        vertical_alignment="center",
    )
    with brand:
        toolbar_style = (
            "border:none;margin:0;padding:0;min-height:48px;"
        )
        st.markdown(
            (
                f'<div class="cel-toolbar" style="{toolbar_style}">'
                '<div class="cel-brand-row">'
                '<div class="cel-mark" aria-hidden="true"></div>'
                f'<p class="cel-brand-name">{t("brand.name", lang)}</p>'
                "</div>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    with utilities:
        tut_col, lang_col = st.columns(
            [1.1, 0.95],
            gap="small",
            vertical_alignment="center",
        )
        with tut_col:
            if st.button(
                t("header.tutorial", lang),
                key="header_tutorial_btn",
                type="tertiary",
            ):
                request_tutorial(st.session_state)
                st.rerun()
        with lang_col:
            current = LANG_CODE_TO_OPTION.get(lang, "繁中")
            selected = st.segmented_control(
                t("header.language_aria", lang),
                options=list(LANG_OPTIONS),
                default=current,
                key="ui_language_control",
                label_visibility="collapsed",
            )
            if selected and selected != current:
                set_language(st.session_state, LANG_OPTION_TO_CODE[selected])
                st.rerun()
    st.markdown(
        '<div style="border-bottom:1px solid #E5EAF0;margin:4px 0 12px 0;"></div>',
        unsafe_allow_html=True,
    )


def render_page_header(
    title: str,
    subtitle: str,
    *,
    badge: str | None = None,
    hint: str | None = None,
) -> None:
    """Render a compact SaaS page header."""
    badge_html = f'<span class="cel-badge">{badge}</span>' if badge else ""
    hint_html = f'<p class="cel-page-hint">{hint}</p>' if hint else ""
    st.markdown(
        f"""
        <div class="cel-page-header">
          <h1 class="cel-page-title">{title}</h1>
          <p class="cel-page-sub">{subtitle}</p>
          {badge_html}
          {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, help_text: str | None = None) -> None:
    """Render a restrained section title."""
    help_html = (
        f'<p class="cel-section-help">{help_text}</p>' if help_text else ""
    )
    st.markdown(
        f'<div class="cel-section"><h2 class="cel-section-title">{title}</h2>'
        f"{help_html}</div>",
        unsafe_allow_html=True,
    )


def render_page_help(text: str) -> None:
    """Render compact page-level how-to guidance."""
    st.markdown(
        f'<p class="cel-page-help">{text}</p>',
        unsafe_allow_html=True,
    )


def render_kpi_row(items: list[tuple[Any, str] | tuple[Any, str, str]]) -> None:
    """Render four equal SaaS KPI cards with optional accent class."""
    cards = []
    for item in items:
        value = item[0]
        label = item[1]
        accent = item[2] if len(item) >= 3 else "slate"
        cards.append(
            f"<div class='cel-kpi-card cel-accent-{accent}'>"
            f"<p class='cel-kpi-label'>{label}</p>"
            f"<p class='cel-kpi-value'>{value}</p>"
            "</div>"
        )
    st.markdown(
        f"<div class='cel-kpi-grid'>{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def render_kpi_card(
    value: Any,
    label: str,
    *,
    help_text: str | None = None,
) -> None:
    """Render one KPI card (compatibility helper)."""
    help_html = (
        f'<p class="cel-kpi-label">{help_text}</p>' if help_text else ""
    )
    st.markdown(
        f"""
        <div class="cel-kpi-card">
          <p class="cel-kpi-label">{label}</p>
          <p class="cel-kpi-value">{value}</p>
          {help_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _status_class(kind: str) -> str:
    mapping = {
        "success": "cel-status-success",
        "warning": "cel-status-warning",
        "critical": "cel-status-critical",
        "attention": "cel-status-attention",
        "info": "cel-status-info",
        "muted": "cel-status-muted",
    }
    return mapping.get(kind, "cel-status-muted")


def render_status_badge(label: str, *, kind: str = "muted") -> None:
    """Render a text status badge that does not rely on color alone."""
    st.markdown(
        f'<span class="cel-status {_status_class(kind)}">{label}</span>',
        unsafe_allow_html=True,
    )


def render_issue_card(
    *,
    activity_name: str,
    title: str,
    severity: str,
    action_hint: str,
) -> None:
    """Render a compact dashboard attention card."""
    is_critical = "重大" in severity or "Critical" in severity
    severity_kind = "critical" if is_critical else "warning"
    tone = "cel-issue-critical" if is_critical else ""
    st.markdown(
        f"""
        <div class="cel-issue-card {tone}">
          <span class="cel-status {_status_class(severity_kind)}">{severity}</span>
          <p class="cel-issue-title">{activity_name}</p>
          <p class="cel-issue-meta">{title}</p>
          <p class="cel-issue-body">{action_hint}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, body: str) -> None:
    """Render a professional empty or success state."""
    st.markdown(
        f"""
        <div class="cel-empty">
          <p class="cel-empty-title">{title}</p>
          <p class="cel-empty-body">{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_framework_notice(text: str) -> None:
    """Render a restrained framework information notice."""
    st.markdown(
        f'<div class="cel-framework-notice">{text}</div>',
        unsafe_allow_html=True,
    )


def render_disabled_adapter_state(lang: str, framework_name: str) -> None:
    """Explain that an optional adapter was not run."""
    render_empty_state(
        t("fw.disabled_title", lang),
        f"{framework_name}\n\n{t('fw.disabled', lang)}",
    )


def render_emissions_panel(
    *,
    title: str,
    value_display: str,
    ratio: str,
    status_label: str,
    notice: str,
) -> None:
    """Render one cohesive calculated-emissions summary panel."""
    st.markdown(
        f"""
        <div class="cel-panel">
          <p class="cel-panel-title">{title}</p>
          <p class="cel-emissions-value">{value_display}</p>
          <p class="cel-emissions-meta">{ratio}</p>
          <div style="margin-top:10px;">
            <span class="cel-status cel-status-info">{status_label}</span>
          </div>
          <p class="cel-emissions-note">{notice}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_controls(lang: str) -> dict[str, bool]:
    """Render compact analysis-module controls below navigation."""
    st.markdown(
        f"""
        <p class="cel-sidebar-title">{t("sidebar.current_analysis", lang)}</p>
        <p class="cel-sidebar-meta">{t("sidebar.workspace_name", lang)}</p>
        <p class="cel-sidebar-muted">{t("sidebar.reporting_context", lang)}</p>
        <p class="cel-sidebar-title">{t("sidebar.analysis_contents", lang)}</p>
        """,
        unsafe_allow_html=True,
    )

    include_ghg = st.checkbox(
        t("sidebar.ghg_title", lang),
        key="ui_checkbox_ghg",
        help=t("sidebar.ghg_help", lang),
    )
    st.markdown(
        '<p class="cel-module-sub">GHG Protocol</p>',
        unsafe_allow_html=True,
    )

    include_cbam = st.checkbox(
        t("sidebar.cbam_title", lang),
        key="ui_checkbox_cbam",
        help=t("sidebar.cbam_help", lang),
    )
    st.markdown(
        '<p class="cel-module-sub">EU CBAM</p>',
        unsafe_allow_html=True,
    )

    include_ifrs = st.checkbox(
        t("sidebar.ifrs_title", lang),
        key="ui_checkbox_ifrs",
        help=t("sidebar.ifrs_help", lang),
    )
    st.markdown(
        '<p class="cel-module-sub">IFRS S2</p>',
        unsafe_allow_html=True,
    )
    return {
        "include_ghg": bool(include_ghg),
        "include_cbam": bool(include_cbam),
        "include_ifrs": bool(include_ifrs),
    }


def render_sidebar_help(lang: str) -> None:
    """Render compact sidebar help with glossary access."""
    st.markdown(
        f'<p class="cel-sidebar-title">{t("sidebar.need_help", lang)}</p>',
        unsafe_allow_html=True,
    )
    if st.button(
        t("sidebar.tutorial_link", lang),
        key="sidebar_tutorial_link",
        type="tertiary",
    ):
        request_tutorial(st.session_state)
        st.rerun()
    render_glossary_popover(lang)
