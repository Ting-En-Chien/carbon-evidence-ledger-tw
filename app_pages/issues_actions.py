"""Issues & Actions — beginner-first operational task list."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.charts import render_issue_gap_bars
from carbon_ledger.ui.components import (
    inject_design_system,
    render_empty_state,
    render_kpi_card,
    render_page_header,
    render_page_help,
    render_section_header,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_current_result, get_language
from carbon_ledger.ui.view_models import issues_table

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

render_page_header(t("iss.title", lang), t("iss.subtitle", lang))
render_page_help(t("iss.help", lang))

if result is None:
    st.error(t("error.analysis_failed", lang))
    st.stop()

table = issues_table(result, lang)
open_issues = int(len(table))
critical = int((table["severity_code"] == "critical").sum()) if open_issues else 0
high = int((table["severity_code"] == "high").sum()) if open_issues else 0
affected = int(table["record_id"].nunique()) if open_issues else 0

metric_cols = st.columns(4)
with metric_cols[0]:
    render_kpi_card(open_issues, t("iss.metric_open", lang))
with metric_cols[1]:
    render_kpi_card(critical, t("iss.metric_critical", lang))
with metric_cols[2]:
    render_kpi_card(high, t("iss.metric_high", lang))
with metric_cols[3]:
    render_kpi_card(affected, t("iss.metric_affected", lang))

if open_issues == 0:
    render_empty_state(t("iss.empty", lang), t("iss.empty", lang))
    st.stop()

render_issue_gap_bars(result, lang)

st.write("")
filter_cols = st.columns(3)
severities = [t("act.filter_all", lang)] + sorted(
    table["Priority"].dropna().unique().tolist()
)
issue_types = [t("act.filter_all", lang)] + sorted(
    table["issue_code"].dropna().unique().tolist()
)
activities = [t("act.filter_all", lang)] + sorted(
    table["Activity"].dropna().unique().tolist()
)
with filter_cols[0]:
    severity_filter = st.selectbox(t("iss.filter_severity", lang), severities)
with filter_cols[1]:
    issue_filter = st.selectbox(t("iss.filter_type", lang), issue_types)
with filter_cols[2]:
    activity_filter = st.selectbox(t("iss.filter_activity", lang), activities)

filtered = table.copy()
all_label = t("act.filter_all", lang)
if severity_filter != all_label:
    filtered = filtered[filtered["Priority"] == severity_filter]
if issue_filter != all_label:
    filtered = filtered[filtered["issue_code"] == issue_filter]
if activity_filter != all_label:
    filtered = filtered[filtered["Activity"] == activity_filter]

if filtered.empty:
    render_empty_state(t("iss.empty", lang), t("iss.help", lang))
    st.stop()

render_section_header(t("iss.title", lang), t("iss.help", lang))
display = filtered[
    [
        "Priority",
        "Activity",
        "Issue",
        "Why it matters",
        "Recommended action",
        "issue_id",
    ]
].rename(
    columns={
        "Priority": t("iss.col.priority", lang),
        "Activity": t("iss.col.activity", lang),
        "Issue": t("iss.col.issue", lang),
        "Why it matters": t("iss.col.why", lang),
        "Recommended action": t("iss.col.next", lang),
    }
)
event = st.dataframe(
    display.drop(columns=["issue_id"]),
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    key="issues_table",
)

selected_rows = []
if event is not None and getattr(event, "selection", None) is not None:
    selected_rows = list(event.selection.rows)
selected_index = selected_rows[0] if selected_rows else 0
selected = filtered.iloc[selected_index]

st.write("")
render_section_header(t("iss.detail.problem", lang))
detail_cols = st.columns(2)
with detail_cols[0]:
    st.markdown(f"**{t('iss.detail.problem', lang)}**")
    st.write(selected["Issue"])
    st.markdown(f"**{t('iss.detail.why', lang)}**")
    st.write(selected["Why it matters"])
    st.markdown(f"**{t('iss.detail.next', lang)}**")
    st.write(selected["Recommended action"])
with detail_cols[1]:
    st.markdown(f"**{t('iss.detail.allowed', lang)}**")
    st.write(selected.get("allowed_use") or "—")
    st.markdown(f"**{t('iss.detail.prohibited', lang)}**")
    st.write(selected.get("prohibited_use") or "—")
    st.markdown(f"**{t('iss.detail.related', lang)}**")
    st.write(
        f"{selected['Activity']}  \n"
        f"record_id: `{selected['record_id']}`  \n"
        f"source_document_id: `{selected.get('source_document_id') or '—'}`"
    )
