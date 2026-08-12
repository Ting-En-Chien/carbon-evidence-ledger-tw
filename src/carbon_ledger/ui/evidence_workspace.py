"""Evidence & Data workspace chrome (tabs across intake / activity / issues / records)."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.i18n import t

TAB_INTAKE = "intake"
TAB_ACTIVITY = "activity"
TAB_ISSUES = "issues"
TAB_RECORDS = "records"

PAGE_BY_TAB = {
    TAB_INTAKE: "app_pages/data_intake.py",
    TAB_ACTIVITY: "app_pages/activity_explorer.py",
    TAB_ISSUES: "app_pages/issues_actions.py",
    TAB_RECORDS: "app_pages/evidence_data.py",
}


def render_evidence_workspace_nav(lang: str, active: str) -> None:
    """Render segmented workspace navigation; switch page when the user changes tab."""
    options = [
        (TAB_INTAKE, t("ev.tab.intake", lang)),
        (TAB_ACTIVITY, t("ev.tab.activity", lang)),
        (TAB_ISSUES, t("ev.tab.issues", lang)),
        (TAB_RECORDS, t("ev.tab.records", lang)),
    ]
    labels = [label for _tab, label in options]
    label_to_tab = {label: tab for tab, label in options}
    active_label = dict(options)[active]

    selected = st.segmented_control(
        t("ev.workspace_nav", lang),
        options=labels,
        default=active_label,
        # Per-page key so the control always reflects the active page on entry.
        key=f"evidence_workspace_nav_{active}",
        label_visibility="collapsed",
    )
    if selected and selected != active_label:
        st.switch_page(PAGE_BY_TAB[label_to_tab[selected]])
