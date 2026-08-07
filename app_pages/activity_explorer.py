"""Activity Explorer — beginner-first evidence drill-down."""

from __future__ import annotations

import streamlit as st

from carbon_ledger.ui.charts import status_kind_for_calculation
from carbon_ledger.ui.components import (
    inject_design_system,
    render_empty_state,
    render_page_header,
    render_page_help,
    render_section_header,
    render_status_badge,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import get_current_result, get_focus_record, get_language
from carbon_ledger.ui.view_models import (
    activity_detail_context,
    build_activity_overview,
    calculation_label,
)

inject_design_system()
lang = get_language(st.session_state)
result = get_current_result(st.session_state)

render_page_header(t("act.title", lang), t("act.subtitle", lang))
render_page_help(t("act.help", lang))

if result is None:
    st.error(t("error.analysis_failed", lang))
    st.stop()

overview = build_activity_overview(result, lang)
if overview.empty:
    render_empty_state(t("act.title", lang), t("act.select_hint", lang))
    st.stop()

st.info(t("act.select_hint", lang))

filter_cols = st.columns([2, 1.2, 1.4, 1.2])
with filter_cols[0]:
    search = st.text_input(t("act.filter_search", lang), value="")
with filter_cols[1]:
    type_options = [t("act.filter_all", lang)] + sorted(
        overview["activity_type"].dropna().unique().tolist()
    )
    selected_type = st.selectbox(t("act.filter_type", lang), type_options)
with filter_cols[2]:
    status_options = [t("act.filter_all", lang)] + sorted(
        overview["calculation_label"].dropna().unique().tolist()
    )
    selected_status = st.selectbox(t("act.filter_status", lang), status_options)
with filter_cols[3]:
    attention_filter = st.selectbox(
        t("act.filter_attention", lang),
        [
            t("act.filter_all", lang),
            t("act.filter_yes", lang),
            t("act.filter_no", lang),
        ],
    )

filtered = overview.copy()
all_label = t("act.filter_all", lang)
if search.strip():
    needle = search.strip().lower()
    filtered = filtered[
        filtered["activity_name"].str.lower().str.contains(needle, na=False)
        | filtered["activity_type"].str.lower().str.contains(needle, na=False)
    ]
if selected_type != all_label:
    filtered = filtered[filtered["activity_type"] == selected_type]
if selected_status != all_label:
    filtered = filtered[filtered["calculation_label"] == selected_status]
if attention_filter == t("act.filter_yes", lang):
    filtered = filtered[filtered["attention_required"]]
elif attention_filter == t("act.filter_no", lang):
    filtered = filtered[~filtered["attention_required"]]

if filtered.empty:
    render_empty_state(t("act.title", lang), t("act.select_hint", lang))
    st.stop()

table = filtered[
    [
        "activity_name",
        "activity_amount",
        "activity_unit",
        "calculation_label",
        "ghg_label",
        "cbam_label",
        "ifrs_s2_label",
        "attention_required",
        "record_id",
    ]
].rename(
    columns={
        "activity_name": t("dash.col.activity", lang),
        "activity_amount": t("dash.col.amount", lang),
        "activity_unit": "Unit",
        "calculation_label": t("dash.col.calc", lang),
        "ghg_label": t("dash.col.ghg", lang),
        "cbam_label": t("dash.col.cbam", lang),
        "ifrs_s2_label": t("dash.col.ifrs", lang),
        "attention_required": t("act.filter_attention", lang),
        "record_id": "record_id",
    }
)

event = st.dataframe(
    table,
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    key="activity_explorer_table",
)

focus = get_focus_record(st.session_state)
selected_rows = []
if event is not None and getattr(event, "selection", None) is not None:
    selected_rows = list(event.selection.rows)

if selected_rows:
    selected_record_id = str(table.iloc[selected_rows[0]]["record_id"])
elif focus and focus in set(table["record_id"].astype(str)):
    selected_record_id = focus
else:
    selected_record_id = str(table.iloc[0]["record_id"])

detail = activity_detail_context(result, selected_record_id, lang)
if not detail:
    render_empty_state(t("act.title", lang), t("act.select_hint", lang))
    st.stop()

overview_row = detail["overview"]
calc = detail["calculation"]
activity = detail["activity"]
calc_status = str(overview_row.get("calculation_status", ""))

st.write("")
render_section_header(t("act.status_strip", lang))
strip = st.columns(5)
with strip[0]:
    st.caption(t("dash.col.calc", lang))
    render_status_badge(
        str(overview_row.get("calculation_label", "—")),
        kind=status_kind_for_calculation(calc_status),
    )
with strip[1]:
    st.caption("GHG")
    render_status_badge(str(overview_row.get("ghg_label", "—")), kind="info")
with strip[2]:
    st.caption("CBAM")
    render_status_badge(str(overview_row.get("cbam_label", "—")), kind="muted")
with strip[3]:
    st.caption("IFRS S2")
    render_status_badge(str(overview_row.get("ifrs_s2_label", "—")), kind="muted")
with strip[4]:
    st.caption(t("dash.col.qa", lang))
    qa_label = str(overview_row.get("qa_label", "—"))
    qa_kind = (
        "warning"
        if (
            "高" in qa_label
            or "High" in qa_label
            or "Critical" in qa_label
            or "重大" in qa_label
        )
        else "success"
    )
    render_status_badge(qa_label, kind=qa_kind)

st.write("")
render_section_header(t("act.title", lang))
summary_cols = st.columns(3)
with summary_cols[0]:
    st.markdown(f"**{t('dash.col.activity', lang)}**")
    st.write(overview_row.get("activity_name", "—"))
    st.markdown(f"**{t('dash.col.amount', lang)}**")
    st.write(
        f"{overview_row.get('activity_amount', '—')} "
        f"{overview_row.get('activity_unit', '')}"
    )
with summary_cols[1]:
    st.markdown(f"**{t('dash.col.calc', lang)}**")
    render_status_badge(
        str(overview_row.get("calculation_label", "—")),
        kind=status_kind_for_calculation(calc_status),
    )
    can_calc = (
        t("act.can_calculate", lang)
        if calc_status == "calculated"
        else t("act.cannot_calculate", lang)
    )
    st.write(can_calc)
with summary_cols[2]:
    if calc_status == "calculated" and overview_row.get("calculated_tco2e") is not None:
        st.markdown("**tCO₂e**")
        st.write(f"{float(overview_row['calculated_tco2e']):.6g}")
    else:
        st.markdown(t("act.no_zero", lang))
        st.caption(detail["calculation_next_action"])

tab_summary, tab_calc, tab_evidence, tab_frameworks, tab_tech = st.tabs(
    [
        t("act.tab.summary", lang),
        t("act.tab.calc", lang),
        t("act.tab.evidence", lang),
        t("act.tab.frameworks", lang),
        t("act.tab.tech", lang),
    ]
)

with tab_summary:
    name = overview_row.get("activity_name", "—")
    st.write(
        f"{name} · {overview_row.get('calculation_label', '—')} · "
        f"GHG: {overview_row.get('ghg_label', '—')} · "
        f"CBAM: {overview_row.get('cbam_label', '—')} · "
        f"IFRS S2: {overview_row.get('ifrs_s2_label', '—')}"
    )

with tab_calc:
    st.markdown(f"**{t('dash.col.calc', lang)}:** {detail['calculation_label']}")
    st.markdown(f"**normalized_value:** {calc.get('normalized_value', '—')}")
    st.markdown(f"**normalized_unit:** {calc.get('normalized_unit', '—')}")
    st.markdown(f"**factor_id:** `{calc.get('factor_id', '—') or '—'}`")
    if calc_status == "calculated" and calc.get("calculated_tco2e") is not None:
        st.markdown(f"**tCO₂e:** {float(calc['calculated_tco2e']):.6g}")
    else:
        st.markdown(t("act.no_zero", lang))
        st.warning(t("act.why_blocked", lang))
        st.write(detail["calculation_explanation"])
        st.info(t("act.what_next", lang))
        st.write(detail["calculation_next_action"])

with tab_evidence:
    st.markdown(f"**source_document_id:** `{activity.get('source_document_id', '—')}`")
    st.markdown(f"**source_locator:** `{activity.get('source_locator', '—')}`")
    st.markdown(f"**measurement_method:** {activity.get('measurement_method', '—')}")
    st.markdown(f"**data_quality_tier:** {activity.get('data_quality_tier', '—')}")
    st.markdown(
        f"**period:** {activity.get('activity_start_date', '—')} → "
        f"{activity.get('activity_end_date', '—')}"
    )

with tab_frameworks:
    st.markdown("#### GHG Protocol")
    st.write(overview_row.get("ghg_label", t("common.not_run", lang)))
    st.markdown("#### EU CBAM")
    st.write(overview_row.get("cbam_label", t("common.not_run", lang)))
    st.markdown("#### IFRS S2")
    st.write(overview_row.get("ifrs_s2_label", t("common.not_run", lang)))

with tab_tech:
    with st.expander(t("common.advanced", lang), expanded=False):
        st.write(
            {
                "record_id": overview_row.get("record_id"),
                "calculation_status": overview_row.get("calculation_status"),
                "calculation_label": calculation_label(
                    str(overview_row.get("calculation_status", "")), lang
                ),
                "calculation_id": calc.get("calculation_id"),
                "factor_id": calc.get("factor_id"),
                "evaluation_id_ghg": detail["ghg"].get("evaluation_id"),
                "rule_id_ghg": detail["ghg"].get("rule_id"),
                "reference_id_ghg": detail["ghg"].get("reference_id"),
                "evaluation_id_cbam": detail["cbam"].get("evaluation_id"),
                "rule_id_cbam": detail["cbam"].get("rule_id"),
                "evaluation_id_ifrs": detail["ifrs_s2"].get("evaluation_id"),
                "rule_id_ifrs": detail["ifrs_s2"].get("rule_id"),
            }
        )
