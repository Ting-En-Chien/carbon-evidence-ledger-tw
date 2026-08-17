"""Convert pipeline DataFrames into user-facing display tables.

Source PipelineRunResult frames are never mutated. Display labels hide
internal status codes from primary UI surfaces and honor UI language.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from carbon_ledger.pipeline import PipelineRunResult
from carbon_ledger.ui.i18n import DEFAULT_LANG, status_label, t

REPO_ROOT = Path(__file__).resolve().parents[3]

ACTIVITY_KEYS = {
    "grid_electricity": "activity.grid_electricity",
    "natural_gas": "activity.natural_gas",
    "diesel": "activity.diesel",
    "purchased_steel": "activity.purchased_steel",
    "finished_goods_output": "activity.finished_goods_output",
    "third_party_transport": "activity.third_party_transport",
    "scrap_output": "activity.scrap_output",
    "other": "activity.other",
    "unknown": "activity.unknown",
}

CUSTOMER_SCHEMA_LABEL_KEYS = {
    "activity_type": "intake.field.activity_type",
    "activity_value": "intake.field.activity_value",
    "unit": "intake.field.unit",
    "activity_start_date": "intake.field.start",
    "activity_end_date": "intake.field.end",
    "site_id": "intake.field.site_id",
}

_UNCONFIRMED_SITE_TOKENS = frozenset(
    {"", "unknown", "site_main", "n/a", "na", "none"}
)

CBAM_ROLE_KEYS = {
    "supporting_energy_evidence": "cbam.role.supporting_energy",
    "direct_emissions_activity_candidate": "cbam.role.direct_candidate",
    "outside_process_boundary": "cbam.role.outside",
    "possible_precursor_candidate": "cbam.role.precursor",
    "product_quantity_denominator_candidate": "cbam.role.product_qty",
}

ATTENTION_TITLE_KEYS = {
    "blocked_missing_conversion": "status.attention_blocked",
    "blocked_natural_gas_type_required": "status.attention_blocked",
    "no_factor_configured": "status.attention_factor",
}

ATTENTION_ACTION_KEYS = {
    "natural_gas": "dash.attention_gas_action",
    "diesel": "dash.attention_diesel_action",
    "purchased_steel": "dash.attention_steel_action",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def not_run_label(lang: str = DEFAULT_LANG) -> str:
    """Return the disabled-adapter label."""
    return t("common.not_run", lang)


def customer_schema_label(field: str, lang: str = DEFAULT_LANG) -> str:
    """Presentation-only label for a backend schema field name."""
    key = CUSTOMER_SCHEMA_LABEL_KEYS.get(str(field or "").strip())
    return t(key, lang) if key else str(field or "")


def customer_site_display(value: Any, lang: str = DEFAULT_LANG) -> str:
    """Human location name; unknown/internal tokens need confirmation."""
    text = _text(value)
    if text.casefold() in _UNCONFIRMED_SITE_TOKENS:
        return t("intake.site_unconfirmed", lang)
    return text


def activity_display_name(
    activity_type: str,
    lang: str = DEFAULT_LANG,
) -> str:
    """Return a human-readable activity name."""
    key = _text(activity_type)
    msg_key = ACTIVITY_KEYS.get(key)
    if msg_key:
        return t(msg_key, lang)
    return key.replace("_", " ").title() or "Activity"


def calculation_label(status: str, lang: str = DEFAULT_LANG) -> str:
    """Return the primary user-facing calculation label."""
    return status_label(status, lang)


def calculation_explanation(status: str, lang: str = DEFAULT_LANG) -> str:
    """Return a short explanation for a calculation status."""
    key = _text(status)
    msg = f"explain.{key}"
    if msg in {
        "explain.calculated",
        "explain.blocked_missing_conversion",
        "explain.blocked_natural_gas_type_required",
        "explain.no_factor_configured",
        "explain.not_emissions_activity",
    }:
        return t(msg, lang)
    return t("explain.no_factor_configured", lang)


def calculation_next_action(status: str, lang: str = DEFAULT_LANG) -> str:
    """Return the recommended next action for a calculation status."""
    key = _text(status)
    msg = f"next.{key}"
    known = {
        "next.calculated",
        "next.blocked_missing_conversion",
        "next.blocked_natural_gas_type_required",
        "next.no_factor_configured",
        "next.not_emissions_activity",
    }
    if msg in known:
        return t(msg, lang)
    return t("next.no_factor_configured", lang)


def status_presentation(code: str, lang: str = DEFAULT_LANG) -> dict[str, str]:
    """Return label, explanation, and next action for a technical status code."""
    key = _text(code)
    return {
        "code": key,
        "label": calculation_label(key, lang),
        "explanation": calculation_explanation(key, lang),
        "next_action": calculation_next_action(key, lang),
    }


def ghg_display_label(
    ghg_row: pd.Series | None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Build a GHG Protocol label from an evaluation row."""
    if ghg_row is None:
        return not_run_label(lang)
    scope = _text(ghg_row.get("ghg_scope"))
    category = _text(ghg_row.get("scope3_category"))
    if scope == "scope_3" and "category_1" in category:
        return t("ghg.scope_3_cat1", lang)
    if scope == "scope_1":
        return t("ghg.scope_1", lang)
    if scope == "scope_2":
        return t("ghg.scope_2", lang)
    if scope == "scope_3":
        return t("ghg.scope_3", lang)
    if scope == "not_applicable" or _text(ghg_row.get("mapping_status")) == (
        "not_applicable"
    ):
        return t("status.not_applicable", lang)
    return scope.replace("_", " ").title() or not_run_label(lang)


def cbam_display_label(
    cbam_row: pd.Series | None,
    *,
    enabled: bool,
    lang: str = DEFAULT_LANG,
) -> str:
    """Build a CBAM role label from an evaluation row."""
    if not enabled or cbam_row is None:
        return not_run_label(lang)
    role = _text(cbam_row.get("data_role"))
    role_key = CBAM_ROLE_KEYS.get(role)
    if role_key:
        return t(role_key, lang)
    status = _text(cbam_row.get("mapping_status"))
    return status_label(status, lang)


def ifrs_display_label(
    ifrs_row: pd.Series | None,
    *,
    enabled: bool,
    lang: str = DEFAULT_LANG,
) -> str:
    """Build an IFRS S2 readiness label from an evaluation row."""
    if not enabled or ifrs_row is None:
        return not_run_label(lang)
    readiness = _text(ifrs_row.get("readiness_status"))
    return status_label(readiness, lang)


def qa_display_label(
    issues: pd.DataFrame,
    record_id: str,
    lang: str = DEFAULT_LANG,
) -> str:
    """Summarize open QA attention for one activity."""
    if issues.empty:
        return t("status.no_open_issue", lang)
    matched = issues[issues["record_id"].astype(str) == record_id]
    if matched.empty:
        return t("status.no_open_issue", lang)
    severity = _text(matched.iloc[0].get("severity"))
    return t(f"severity.{severity}", lang) if severity else t(
        "status.no_open_issue", lang
    )


def _row_by_record(frame: pd.DataFrame, record_id: str) -> pd.Series | None:
    if frame is None or frame.empty or "record_id" not in frame.columns:
        return None
    matched = frame[frame["record_id"].astype(str) == record_id]
    if matched.empty:
        return None
    return matched.iloc[0]


def build_activity_overview(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> pd.DataFrame:
    """Build a unified activity overview without mutating source frames."""
    activities = result.activity_records_accepted.copy()
    calculations = result.calculation_results.copy()
    ghg = result.ghg_evaluations.copy()
    cbam = result.cbam_evaluations.copy()
    ifrs = result.ifrs_s2_evaluations.copy()
    issues = result.core_qa_issues.copy()
    idle = not_run_label(lang)

    rows: list[dict[str, Any]] = []
    for _, activity in activities.iterrows():
        record_id = _text(activity.get("record_id"))
        activity_type = _text(activity.get("activity_type"))
        calc_row = _row_by_record(calculations, record_id)
        calc_status = (
            _text(calc_row.get("calculation_status")) if calc_row is not None else ""
        )
        calculated_tco2e = None
        if calc_row is not None and calc_status == "calculated":
            value = calc_row.get("calculated_tco2e")
            try:
                if value is not None and not pd.isna(value):
                    calculated_tco2e = float(value)
            except (TypeError, ValueError):
                calculated_tco2e = None

        attention = False
        if not issues.empty and "record_id" in issues.columns:
            attention = bool((issues["record_id"].astype(str) == record_id).any())

        amount = activity.get("activity_value")
        try:
            amount_value = (
                float(amount) if amount is not None and not pd.isna(amount) else None
            )
        except (TypeError, ValueError):
            amount_value = None

        rows.append(
            {
                "record_id": record_id,
                "activity_name": activity_display_name(activity_type, lang),
                "activity_type": activity_type,
                "activity_amount": amount_value,
                "activity_unit": _text(activity.get("unit")),
                "calculation_status": calc_status,
                "calculation_label": calculation_label(calc_status, lang),
                "calculated_tco2e": calculated_tco2e,
                "ghg_label": (
                    ghg_display_label(_row_by_record(ghg, record_id), lang)
                    if result.include_ghg
                    else idle
                ),
                "cbam_label": cbam_display_label(
                    _row_by_record(cbam, record_id),
                    enabled=result.include_cbam,
                    lang=lang,
                ),
                "ifrs_s2_label": ifrs_display_label(
                    _row_by_record(ifrs, record_id),
                    enabled=result.include_ifrs_s2,
                    lang=lang,
                ),
                "qa_label": qa_display_label(issues, record_id, lang),
                "attention_required": attention,
                "source_document_id": _text(activity.get("source_document_id")),
            }
        )
    return pd.DataFrame(rows)


def dashboard_kpi_counts(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> dict[str, int]:
    """Compute dashboard KPI values from the current result."""
    overview = build_activity_overview(result, lang)
    calculated = 0
    if not overview.empty:
        calculated = int(
            (overview["calculation_status"].astype(str) == "calculated").sum()
        )
    return {
        "activities": int(len(result.activity_records_accepted)),
        "calculated": calculated,
        "open_qa_issues": int(len(result.core_qa_issues)),
        "source_documents": int(len(result.source_documents_accepted)),
    }


def calculated_emissions_summary(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> dict[str, Any]:
    """Summarize currently calculated emissions only."""
    calculations = result.calculation_results.copy()
    empty = {
        "calculated_tco2e": None,
        "calculated_row_count": 0,
        "partial": True,
        "label": t("common.partial_result", lang),
    }
    if calculations.empty or "calculation_status" not in calculations.columns:
        return empty
    calculated = calculations[
        calculations["calculation_status"].astype(str) == "calculated"
    ].copy()
    if calculated.empty:
        return empty
    numeric = pd.to_numeric(calculated["calculated_tco2e"], errors="coerce")
    return {
        "calculated_tco2e": float(numeric.fillna(0).sum()),
        "calculated_row_count": int(len(calculated)),
        "partial": True,
        "label": t("common.partial_result", lang),
    }


def calculated_emissions_by_ghg_scope(
    result: PipelineRunResult,
) -> dict[str, float]:
    """Sum calculated tCO2e by GHG scope. Blocked rows are excluded."""
    calculations = result.calculation_results.copy()
    ghg = result.ghg_evaluations.copy()
    totals: dict[str, float] = {}
    if calculations.empty or ghg.empty:
        return totals
    calculated = calculations[
        calculations["calculation_status"].astype(str) == "calculated"
    ].copy()
    if calculated.empty:
        return totals
    merged = calculated.merge(
        ghg[["record_id", "ghg_scope"]],
        on="record_id",
        how="left",
    )
    merged["calculated_tco2e"] = pd.to_numeric(
        merged["calculated_tco2e"], errors="coerce"
    )
    merged = merged.dropna(subset=["calculated_tco2e"])
    for scope, group in merged.groupby(merged["ghg_scope"].astype(str)):
        totals[str(scope)] = float(group["calculated_tco2e"].sum())
    return totals


_ACTIVITY_PRODUCT_SCOPE = {
    "grid_electricity": "scope_2",
    "natural_gas": "scope_1",
    "diesel": "scope_1",
}


def calculated_emissions_by_product_scope(
    result: PipelineRunResult,
) -> dict[str, float | None]:
    """Customer Scope totals from calculated rows only.

    Prefers mapped GHG scopes. Falls back to V1 activity-type paths so
    Scope 1/2 still display when GHG needs review. Scope 3 is omitted
    unless a calculated row actually maps to it.
    """
    calculations = result.calculation_results.copy()
    activities = result.activity_records_accepted.copy()
    totals: dict[str, float | None] = {"scope_1": 0.0, "scope_2": 0.0}
    if calculations.empty or activities.empty:
        return totals
    calculated = calculations[
        calculations["calculation_status"].astype(str) == "calculated"
    ].copy()
    if calculated.empty:
        return totals
    keep = ["record_id", "activity_type"]
    merged = calculated.merge(
        activities[keep],
        on="record_id",
        how="left",
    )
    ghg = result.ghg_evaluations.copy()
    if not ghg.empty:
        ghg_cols = ["record_id"]
        if "ghg_scope" in ghg.columns:
            ghg_cols.append("ghg_scope")
        if "mapping_status" in ghg.columns:
            ghg_cols.append("mapping_status")
        merged = merged.merge(ghg[ghg_cols], on="record_id", how="left")
    merged["calculated_tco2e"] = pd.to_numeric(
        merged["calculated_tco2e"], errors="coerce"
    )
    merged = merged.dropna(subset=["calculated_tco2e"])
    scope_3 = 0.0
    has_scope_3 = False
    for _, row in merged.iterrows():
        value = float(row["calculated_tco2e"])
        mapping_status = _text(row.get("mapping_status"))
        ghg_scope = _text(row.get("ghg_scope"))
        if mapping_status == "mapped" and ghg_scope in {
            "scope_1",
            "scope_2",
            "scope_3",
        }:
            scope = ghg_scope
        else:
            scope = _ACTIVITY_PRODUCT_SCOPE.get(
                _text(row.get("activity_type")), ""
            )
        if scope == "scope_3":
            has_scope_3 = True
            scope_3 += value
        elif scope in {"scope_1", "scope_2"}:
            totals[scope] = float(totals.get(scope) or 0.0) + value
    if has_scope_3:
        totals["scope_3"] = scope_3
    return totals


def should_show_coverage_chart(calculated: int, total: int) -> bool:
    """Show compact coverage only when calculation is partial, never at 100%."""
    return 0 < int(calculated) < int(total)


def should_show_unresolved_cta(unresolved: int) -> bool:
    """Issue CTAs exist only when the customer has something to fix."""
    return int(unresolved) > 0


def executive_emissions_insights(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> list[str]:
    """At most two deterministic sentences. Source share first. No LLM."""
    summary = calculated_emissions_summary(result, lang)
    total = float(summary.get("calculated_tco2e") or 0.0)
    if total <= 0:
        return []
    scopes = calculated_emissions_by_product_scope(result)
    scope_1 = float(scopes.get("scope_1") or 0.0)
    scope_2 = float(scopes.get("scope_2") or 0.0)
    leading_scope = "Scope 1" if scope_1 >= scope_2 else "Scope 2"
    leading_value = max(scope_1, scope_2)
    leading_share = leading_value / total
    overview = build_activity_overview(result, lang)
    top_name = ""
    top_value = 0.0
    if not overview.empty:
        calculated = overview[
            overview["calculation_status"].astype(str) == "calculated"
        ].copy()
        if not calculated.empty:
            calculated["tco2e"] = pd.to_numeric(
                calculated["calculated_tco2e"], errors="coerce"
            )
            grouped = (
                calculated.dropna(subset=["tco2e"])
                .groupby("activity_name", dropna=False)["tco2e"]
                .sum()
                .sort_values(ascending=False)
            )
            if not grouped.empty:
                top_name = str(grouped.index[0] or "")
                top_value = float(grouped.iloc[0] or 0.0)
    items: list[str] = []
    if top_name and top_value > 0:
        percent = int(round(100.0 * top_value / total))
        items.append(
            t(
                "dash.insight.top_source_share",
                lang,
                name=top_name,
                percent=percent,
            )
        )
    elif top_name:
        items.append(t("dash.insight.top_source", lang, name=top_name))
    if 0.5 <= leading_share < 0.95:
        percent = int(round(100.0 * leading_share))
        items.append(
            t(
                "dash.insight.top_scope",
                lang,
                scope=leading_scope,
                percent=percent,
            )
        )
    elif not items and leading_value > 0:
        percent = int(round(100.0 * leading_share))
        items.append(
            t(
                "dash.insight.top_scope",
                lang,
                scope=leading_scope,
                percent=percent,
            )
        )
    return items[:2]


def executive_emissions_insight(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> str:
    """Primary deterministic insight. No LLM."""
    items = executive_emissions_insights(result, lang)
    return items[0] if items else ""


def scope_kpi_states(result: PipelineRunResult) -> dict[str, dict[str, Any]]:
    """Distinguish calculated Scope totals from unresolved / unsupported."""
    totals = calculated_emissions_by_product_scope(result)
    activities = result.activity_records_accepted.copy()
    calculations = result.calculation_results.copy()
    status_by_id: dict[str, str] = {}
    if not calculations.empty:
        for _, row in calculations.iterrows():
            status_by_id[_text(row.get("record_id"))] = _text(
                row.get("calculation_status")
            )
    ghg_by_id: dict[str, Any] = {}
    ghg = result.ghg_evaluations.copy()
    if not ghg.empty:
        for _, row in ghg.iterrows():
            ghg_by_id[_text(row.get("record_id"))] = row
    calculated_present = {"scope_1": False, "scope_2": False}
    if not activities.empty:
        for _, row in activities.iterrows():
            record_id = _text(row.get("record_id"))
            ghg_row = ghg_by_id.get(record_id)
            mapping_status = ""
            ghg_scope = ""
            if ghg_row is not None:
                mapping_status = _text(ghg_row.get("mapping_status"))
                ghg_scope = _text(ghg_row.get("ghg_scope"))
            if mapping_status == "mapped" and ghg_scope in {
                "scope_1",
                "scope_2",
                "scope_3",
            }:
                scope = ghg_scope
            else:
                scope = _ACTIVITY_PRODUCT_SCOPE.get(
                    _text(row.get("activity_type")), ""
                )
            if scope not in {"scope_1", "scope_2"}:
                continue
            if status_by_id.get(record_id) == "calculated":
                calculated_present[scope] = True
    states: dict[str, dict[str, Any]] = {}
    for key in ("scope_1", "scope_2"):
        if calculated_present[key]:
            states[key] = {
                "state": "calculated",
                "value": float(totals.get(key) or 0.0),
            }
        else:
            states[key] = {"state": "pending", "value": None}
    if totals.get("scope_3") is not None:
        states["scope_3"] = {
            "state": "calculated",
            "value": float(totals["scope_3"]),
        }
    else:
        states["scope_3"] = {"state": "unsupported", "value": None}
    return states


def attention_issue_cards(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> list[dict[str, str]]:
    """Build short dashboard attention cards from core QA issues."""
    issues = result.core_qa_issues.copy()
    activities = result.activity_records_accepted.copy()
    if issues.empty:
        return []

    type_by_record = {
        _text(row.get("record_id")): _text(row.get("activity_type"))
        for _, row in activities.iterrows()
    }
    cards: list[dict[str, str]] = []
    for _, issue in issues.iterrows():
        record_id = _text(issue.get("record_id"))
        activity_type = type_by_record.get(record_id, "")
        source_status = _text(issue.get("source_status"))
        title_key = ATTENTION_TITLE_KEYS.get(source_status)
        title = (
            t(title_key, lang)
            if title_key
            else calculation_label(source_status, lang)
        )
        action_key = ATTENTION_ACTION_KEYS.get(activity_type)
        action_hint = (
            t(action_key, lang)
            if action_key
            else calculation_next_action(source_status, lang)
        )
        severity_code = _text(issue.get("severity"))
        cards.append(
            {
                "record_id": record_id,
                "activity_name": activity_display_name(activity_type, lang),
                "activity_type": activity_type,
                "severity": t(f"severity.{severity_code}", lang),
                "title": title,
                "action_hint": action_hint,
                "reason": _text(issue.get("issue_summary")),
                "recommended_action": _text(issue.get("recommended_action")),
                "issue_id": _text(issue.get("issue_id")),
            }
        )
    return cards


def framework_coverage_cards(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> list[dict[str, Any]]:
    """Build compact framework coverage summaries."""
    return [
        {
            "name": "GHG Protocol",
            "enabled": bool(result.include_ghg),
            "row_count": (
                int(len(result.ghg_evaluations)) if result.include_ghg else 0
            ),
            "purpose": t("fw.purpose_ghg", lang),
        },
        {
            "name": "EU CBAM",
            "enabled": bool(result.include_cbam),
            "row_count": (
                int(len(result.cbam_evaluations)) if result.include_cbam else 0
            ),
            "purpose": t("fw.purpose_cbam", lang),
        },
        {
            "name": "IFRS S2",
            "enabled": bool(result.include_ifrs_s2),
            "row_count": (
                int(len(result.ifrs_s2_evaluations))
                if result.include_ifrs_s2
                else 0
            ),
            "purpose": t("fw.purpose_ifrs", lang),
        },
    ]


def issues_table(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> pd.DataFrame:
    """Build the Issues & Actions display table."""
    issues = result.core_qa_issues.copy()
    activities = result.activity_records_accepted.copy()
    documents = result.source_documents_accepted.copy()
    columns = [
        "Priority",
        "Activity",
        "Issue",
        "Why it matters",
        "Recommended action",
        "record_id",
        "issue_id",
        "severity_code",
        "issue_code",
        "allowed_use",
        "prohibited_use",
        "source_document_id",
        "document_label",
        "period_label",
    ]
    if issues.empty:
        return pd.DataFrame(columns=columns)

    name_by_record = {
        _text(row.get("record_id")): activity_display_name(
            _text(row.get("activity_type")), lang
        )
        for _, row in activities.iterrows()
    }
    period_by_record = {
        _text(row.get("record_id")): (
            f"{_text(row.get('activity_start_date'))[:7]}"
            if _text(row.get("activity_start_date"))
            else "—"
        )
        for _, row in activities.iterrows()
    }
    doc_name_by_id = {
        _text(row.get("source_document_id")): (
            _text(row.get("file_name")) or _text(row.get("issuer")) or "—"
        )
        for _, row in documents.iterrows()
    }
    rows: list[dict[str, Any]] = []
    for _, issue in issues.iterrows():
        record_id = _text(issue.get("record_id"))
        severity_code = _text(issue.get("severity"))
        doc_id = _text(issue.get("source_document_id"))
        if not doc_id and not activities.empty:
            act = activities[activities["record_id"].astype(str) == record_id]
            if not act.empty:
                doc_id = _text(act.iloc[0].get("source_document_id"))
        rows.append(
            {
                "Priority": t(f"severity.{severity_code}", lang),
                "Activity": name_by_record.get(record_id, record_id or "—"),
                "Issue": _text(issue.get("issue_summary")),
                "Why it matters": _text(issue.get("source_reason"))
                or _text(issue.get("issue_summary")),
                "Recommended action": _text(issue.get("recommended_action")),
                "record_id": record_id,
                "issue_id": _text(issue.get("issue_id")),
                "severity_code": severity_code,
                "issue_code": _text(issue.get("issue_code")),
                "allowed_use": _text(issue.get("allowed_use")),
                "prohibited_use": _text(issue.get("prohibited_use")),
                "source_document_id": doc_id,
                "document_label": doc_name_by_id.get(doc_id, "—"),
                "period_label": period_by_record.get(record_id, "—"),
                "blocking_dependency": _text(issue.get("blocking_dependency")),
                "rule_id": _text(issue.get("rule_id")),
            }
        )
    return pd.DataFrame(rows)


def ghg_framework_table(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> pd.DataFrame:
    """Build the GHG Protocol frameworks table."""
    if not result.include_ghg:
        return pd.DataFrame()
    overview = build_activity_overview(result, lang)
    ghg = result.ghg_evaluations.copy()
    rows: list[dict[str, Any]] = []
    for _, activity in overview.iterrows():
        record_id = _text(activity.get("record_id"))
        ghg_row = _row_by_record(ghg, record_id)
        combustion = ""
        if ghg_row is not None:
            code = _text(ghg_row.get("mapping_code"))
            if "stationary" in code:
                combustion = "Stationary combustion"
            elif "mobile" in code:
                combustion = "Mobile combustion"
            elif "category1" in code or "purchased" in code:
                combustion = "Purchased goods and services"
            elif "electricity" in code:
                combustion = "Purchased electricity"
            elif "not_emissions" in code:
                combustion = "Not an emissions activity"
            status = status_label(_text(ghg_row.get("mapping_status")), lang)
            reason = _text(ghg_row.get("rationale"))
        else:
            status = not_run_label(lang)
            reason = ""
        rows.append(
            {
                "Activity": _text(activity.get("activity_name")),
                "Scope": _text(activity.get("ghg_label")),
                "Category / combustion type": combustion,
                "Status": status,
                "Reason": reason,
                "record_id": record_id,
            }
        )
    return pd.DataFrame(rows)


def cbam_framework_table(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> pd.DataFrame:
    """Build the EU CBAM frameworks table."""
    if not result.include_cbam:
        return pd.DataFrame()
    overview = build_activity_overview(result, lang)
    cbam = result.cbam_evaluations.copy()
    rows: list[dict[str, Any]] = []
    for _, activity in overview.iterrows():
        record_id = _text(activity.get("record_id"))
        cbam_row = _row_by_record(cbam, record_id)
        missing = ""
        relevance = ""
        status = ""
        if cbam_row is not None:
            missing = _text(cbam_row.get("required_data"))
            if missing.lower() == "not_applicable":
                missing = "—"
            relevance = status_label(_text(cbam_row.get("cbam_relevance")), lang)
            status = status_label(_text(cbam_row.get("mapping_status")), lang)
        rows.append(
            {
                "Activity": _text(activity.get("activity_name")),
                "CBAM role": _text(activity.get("cbam_label")),
                "Relevance": relevance,
                "Status": status,
                "What is missing": missing,
                "record_id": record_id,
            }
        )
    return pd.DataFrame(rows)


def ifrs_framework_table(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> pd.DataFrame:
    """Build the IFRS S2 frameworks table."""
    if not result.include_ifrs_s2:
        return pd.DataFrame()
    overview = build_activity_overview(result, lang)
    ifrs = result.ifrs_s2_evaluations.copy()
    rows: list[dict[str, Any]] = []
    for _, activity in overview.iterrows():
        record_id = _text(activity.get("record_id"))
        ifrs_row = _row_by_record(ifrs, record_id)
        role = ""
        missing = ""
        if ifrs_row is not None:
            role = _text(ifrs_row.get("data_role")).replace("_", " ")
            missing = _text(ifrs_row.get("missing_data"))
        rows.append(
            {
                "Activity": _text(activity.get("activity_name")),
                "Evidence role": role.title() if role else "—",
                "Readiness": _text(activity.get("ifrs_s2_label")),
                "Missing data": missing,
                "record_id": record_id,
            }
        )
    return pd.DataFrame(rows)


def _document_type_label(document_type: str, lang: str) -> str:
    key = f"ev.doc_type.{document_type}"
    labeled = t(key, lang)
    if labeled != key:
        return labeled
    return document_type.replace("_", " ") or "—"


def _document_review_status(
    doc: pd.Series,
    *,
    activity_statuses: list[str],
    lang: str,
) -> str:
    """Derive customer-facing review status — never hard-code synthetic."""
    is_synthetic = bool(doc.get("is_synthetic"))
    origin = _text(doc.get("data_origin")).lower()
    if is_synthetic or origin in {"synthetic", "synthetic_demo", "demo"}:
        return t("ev.status.demo", lang)
    if any(status == "needs_review" for status in activity_statuses):
        return t("ev.status.needs_action", lang)
    if activity_statuses and all(
        status in {"approved", "not_required"} for status in activity_statuses
    ):
        return t("ev.status.verified", lang)
    if activity_statuses:
        return t("ev.status.pending", lang)
    return t("ev.status.imported", lang)


def _document_reuse_labels(
    result: PipelineRunResult,
    source_document_id: str,
    lang: str,
) -> list[str]:
    """Return verified reuse labels for one evidence document (no fabrication)."""
    activities = result.activity_records_accepted
    if activities.empty or "source_document_id" not in activities.columns:
        return []
    linked = activities[
        activities["source_document_id"].astype(str) == source_document_id
    ]
    if linked.empty:
        return []
    labels: list[str] = []
    record_ids = {_text(row.get("record_id")) for _, row in linked.iterrows()}
    calcs = result.calculation_results
    calculated = False
    if not calcs.empty and "record_id" in calcs.columns:
        matched = calcs[calcs["record_id"].astype(str).isin(record_ids)]
        if not matched.empty:
            if "calculation_status" in matched.columns:
                calculated = (
                    matched["calculation_status"].astype(str).eq("calculated").any()
                )
            else:
                calculated = True
    if result.include_ghg and not result.ghg_evaluations.empty:
        ghg = result.ghg_evaluations
        ghg_linked = ghg[ghg["record_id"].astype(str).isin(record_ids)]
        if not ghg_linked.empty:
            labels.append(t("ev.reuse.ghg", lang))
            scopes = {
                _text(row.get("ghg_scope")).lower()
                for _, row in ghg_linked.iterrows()
            }
            if calculated and "scope_2" in scopes:
                labels.append(t("ev.reuse.scope2", lang))
            elif calculated and "scope_1" in scopes:
                labels.append(t("ev.reuse.scope1", lang))
            elif calculated:
                labels.append(t("ev.reuse.calculation", lang))
    elif calculated:
        labels.append(t("ev.reuse.calculation", lang))
    if result.include_ifrs_s2 and not result.ifrs_s2_evaluations.empty:
        ifrs = result.ifrs_s2_evaluations
        if "record_id" in ifrs.columns and ifrs["record_id"].astype(str).isin(
            record_ids
        ).any():
            labels.append(t("ev.reuse.ifrs", lang))
    # Preserve order, drop duplicates
    seen: set[str] = set()
    ordered: list[str] = []
    for label in labels:
        if label not in seen:
            seen.add(label)
            ordered.append(label)
    return ordered


def evidence_documents_table(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> pd.DataFrame:
    """Customer-facing evidence register (no hash / raw IDs as lead columns)."""
    docs = result.source_documents_accepted.copy()
    columns = [
        "file_name",
        "document_type_label",
        "period",
        "source_name",
        "used_for",
        "status",
        "source_document_id",
        "sha256",
        "data_origin",
        "ingested_at",
        "is_synthetic",
        "document_date",
        "issuer",
        "source_locator",
    ]
    if docs.empty:
        return pd.DataFrame(columns=columns)

    activities = result.activity_records_accepted
    review_by_doc: dict[str, list[str]] = {}
    if not activities.empty and "source_document_id" in activities.columns:
        for _, act in activities.iterrows():
            doc_id = _text(act.get("source_document_id"))
            review_by_doc.setdefault(doc_id, []).append(
                _text(act.get("human_review_status"))
            )

    rows: list[dict[str, Any]] = []
    for _, doc in docs.iterrows():
        doc_id = _text(doc.get("source_document_id"))
        period = _text(doc.get("document_date"))
        if period and len(period) >= 7:
            period = period[:7]
        reuse = _document_reuse_labels(result, doc_id, lang)
        rows.append(
            {
                "file_name": _text(doc.get("file_name")) or "—",
                "document_type_label": _document_type_label(
                    _text(doc.get("document_type")), lang
                ),
                "period": period or "—",
                "source_name": _text(doc.get("issuer"))
                or _text(doc.get("file_name"))
                or "—",
                "used_for": " · ".join(reuse) if reuse else t("ev.reuse.none", lang),
                "status": _document_review_status(
                    doc,
                    activity_statuses=review_by_doc.get(doc_id, []),
                    lang=lang,
                ),
                "source_document_id": doc_id,
                "sha256": _text(doc.get("sha256")),
                "data_origin": _text(doc.get("data_origin")),
                "ingested_at": _text(doc.get("ingested_at")),
                "is_synthetic": bool(doc.get("is_synthetic")),
                "document_date": _text(doc.get("document_date")),
                "issuer": _text(doc.get("issuer")),
                "source_locator": _text(doc.get("source_path"))
                or _text(doc.get("source_locator")),
            }
        )
    return pd.DataFrame(rows)


def evidence_documents_customer_view(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> pd.DataFrame:
    """Default customer columns only (no hash / IDs)."""
    full = evidence_documents_table(result, lang)
    if full.empty:
        return pd.DataFrame(
            columns=[
                t("ev.col.name", lang),
                t("ev.col.type", lang),
                t("ev.col.period", lang),
                t("ev.col.source", lang),
                t("ev.col.used_for", lang),
                t("ev.col.status", lang),
            ]
        )
    return full[
        [
            "file_name",
            "document_type_label",
            "period",
            "source_name",
            "used_for",
            "status",
        ]
    ].rename(
        columns={
            "file_name": t("ev.col.name", lang),
            "document_type_label": t("ev.col.type", lang),
            "period": t("ev.col.period", lang),
            "source_name": t("ev.col.source", lang),
            "used_for": t("ev.col.used_for", lang),
            "status": t("ev.col.status", lang),
        }
    )


def audit_summary(result: PipelineRunResult) -> dict[str, Any]:
    """Build compact audit metrics and run metadata."""
    ingested = result.ingested_at
    if ingested is None or (isinstance(ingested, float) and pd.isna(ingested)):
        ingested_at = "unavailable"
    else:
        ingested_at = str(ingested)
    return {
        "accepted_source_documents": int(len(result.source_documents_accepted)),
        "accepted_activities": int(len(result.activity_records_accepted)),
        "calculation_rows": int(len(result.calculation_results)),
        "qa_issues": int(len(result.core_qa_issues)),
        "run_id": result.run_id,
        "ingested_at": ingested_at,
        "include_ghg": bool(result.include_ghg),
        "include_cbam": bool(result.include_cbam),
        "include_ifrs_s2": bool(result.include_ifrs_s2),
    }


def official_reference_status_view(
    repo_root: Any,
    lang: str = DEFAULT_LANG,
) -> dict[str, Any]:
    """Build beginner/admin official-reference status for Audit & Export."""
    from pathlib import Path

    from carbon_ledger.reference_sync import reference_sync_status

    status = reference_sync_status(Path(repo_root))
    state_labels = {
        "available": t("aud.ref_year_available", lang),
        "candidate": t("aud.ref_year_candidate", lang),
        "unavailable": t("aud.ref_year_unavailable", lang),
        "needs_parser_review": t("aud.ref_year_candidate", lang),
    }
    electricity_rows = [
        {
            "year": year,
            "state": state,
            "label": state_labels.get(state, state),
        }
        for year, state in status.electricity_years.items()
    ]
    heating_rows = [
        {
            "fuel": fuel,
            "latest_year": (
                t("aud.ref_unregistered", lang)
                if year == "unregistered"
                else year
            ),
        }
        for fuel, year in status.heating_value_latest.items()
    ]
    return {
        "last_checked_at": status.last_checked_at,
        "electricity_rows": electricity_rows,
        "heating_rows": heating_rows,
        "snapshot_count": status.snapshot_count,
        "candidate_count": status.candidate_count,
        "source_count": status.source_count,
        "upstream_factor_authority": status.upstream_factor_authority,
        "operational_source_authority": status.operational_source_authority,
        "upstream_source_status": status.upstream_source_status,
        "operational_source_status": status.operational_source_status,
        "upstream_canonical_url": status.upstream_canonical_url,
        "operational_source_url": status.operational_source_url,
    }


def _load_emission_factor_lookup(repo_root: str) -> dict[str, dict[str, Any]]:
    path = Path(repo_root) / "data" / "reference" / "emission_factors.csv"
    if not path.is_file():
        return {}
    frame = pd.read_csv(path)
    if frame.empty or "factor_id" not in frame.columns:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in frame.iterrows():
        factor_id = _text(row.get("factor_id"))
        if not factor_id:
            continue
        lookup[factor_id] = {
            "factor_year": _text(row.get("factor_year")),
            "factor_value": row.get("factor_value"),
            "numerator_unit": _text(row.get("numerator_unit")),
            "denominator_unit": _text(row.get("denominator_unit")),
            "source_reference_id": _text(row.get("source_reference_id")),
        }
    return lookup


@lru_cache(maxsize=4)
def _cached_emission_factor_lookup(repo_root: str) -> dict[str, dict[str, Any]]:
    return _load_emission_factor_lookup(repo_root)


def factor_registry_row(
    factor_id: str,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any] | None:
    """Look up factor metadata for UI traces without mutating calculations."""
    cleaned = _text(factor_id)
    if not cleaned:
        return None
    root = Path(repo_root) if repo_root is not None else REPO_ROOT
    return _cached_emission_factor_lookup(str(root)).get(cleaned)


def calculation_trace_fields(
    result: PipelineRunResult,
    record_id: str,
    lang: str = DEFAULT_LANG,
    *,
    repo_root: Path | None = None,
    official_source: bool = False,
) -> dict[str, Any]:
    """Build beginner-facing calculation trace values from real outputs."""
    detail = activity_detail_context(result, record_id, lang)
    if not detail:
        return {}
    calc = detail.get("calculation") or {}
    overview = detail.get("overview") or {}
    status = _text(overview.get("calculation_status"))
    factor_id = _text(calc.get("factor_id"))
    registry = factor_registry_row(factor_id, repo_root=repo_root) or {}
    factor_value = calc.get("factor_value")
    try:
        if factor_value is not None and pd.isna(factor_value):
            factor_value = registry.get("factor_value")
    except (TypeError, ValueError):
        pass
    if factor_value is None:
        factor_value = registry.get("factor_value")
    factor_year = _text(registry.get("factor_year"))
    source_label = (
        t("act.trace_source_official", lang)
        if official_source
        else t("act.trace_source_demo", lang)
    )
    return {
        "status": status,
        "activity_name": overview.get("activity_name"),
        "activity_amount": overview.get("activity_amount"),
        "activity_unit": _text(overview.get("activity_unit")),
        "factor_id": factor_id,
        "factor_value": factor_value,
        "factor_year": factor_year,
        "calculated_kgco2e": calc.get("calculated_kgco2e"),
        "calculated_tco2e": calc.get("calculated_tco2e"),
        "source_label": source_label,
        "missing": detail.get("calculation_explanation", ""),
        "next_step": detail.get("calculation_next_action", ""),
        "is_calculated": status == "calculated",
    }


def uncalculable_activity_cards(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Return beginner cards for activities that are not currently calculable."""
    overview = build_activity_overview(result, lang)
    if overview.empty:
        return []
    cards: list[dict[str, Any]] = []
    for _, row in overview.iterrows():
        status = _text(row.get("calculation_status"))
        if status in {"calculated", "not_emissions_activity"}:
            continue
        cards.append(
            {
                "record_id": _text(row.get("record_id")),
                "activity_name": _text(row.get("activity_name")),
                "title": t("dash.uncalculable_title", lang),
                "missing": calculation_explanation(status, lang),
                "next_step": calculation_next_action(status, lang),
                "status": status,
            }
        )
        if len(cards) >= limit:
            break
    return cards


def priority_action_cards(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
    *,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Concise beginner priority cards (no internal QA codes)."""
    overview = build_activity_overview(result, lang)
    if overview.empty:
        return []
    # Prefer one card per activity type that is blocked.
    seen_types: set[str] = set()
    cards: list[dict[str, Any]] = []
    for _, row in overview.iterrows():
        status = _text(row.get("calculation_status"))
        if status in {"calculated", "not_emissions_activity"}:
            continue
        activity_type = _text(row.get("activity_type"))
        if activity_type in seen_types:
            continue
        seen_types.add(activity_type)
        if status == "blocked_missing_conversion":
            reason = t("dash.priority.missing_conversion", lang)
        elif status == "blocked_natural_gas_type_required":
            reason = t("explain.blocked_natural_gas_type_required", lang)
        elif status == "no_factor_configured":
            reason = t("dash.priority.missing_factor", lang)
        else:
            reason = calculation_explanation(status, lang)
        same_type = overview[
            overview["activity_type"].astype(str) == (activity_type or "")
        ]
        affected_count = int(
            (
                ~same_type["calculation_status"].isin(
                    {"calculated", "not_emissions_activity"}
                )
            ).sum()
        )
        cards.append(
            {
                "record_id": _text(row.get("record_id")),
                "activity_name": _text(row.get("activity_name")),
                "reason": reason,
                "status": status,
                "affected_count": max(1, affected_count),
            }
        )
        if len(cards) >= limit:
            break
    return cards


def calculation_table_rows(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
    *,
    repo_root: Path | None = None,
) -> pd.DataFrame:
    """Structured calculation table with factor year for beginner results."""
    overview = build_activity_overview(result, lang)
    if overview.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    calcs = result.calculation_results
    for _, row in overview.iterrows():
        record_id = _text(row.get("record_id"))
        status = _text(row.get("calculation_status"))
        calc = _row_by_record(calcs, record_id)
        factor_value = None
        factor_year = ""
        if calc is not None:
            raw_factor = calc.get("factor_value")
            try:
                if raw_factor is not None and not pd.isna(raw_factor):
                    factor_value = float(raw_factor)
            except (TypeError, ValueError):
                factor_value = None
            factor_id = _text(calc.get("factor_id"))
            registry = factor_registry_row(factor_id, repo_root=repo_root) or {}
            factor_year = _text(registry.get("factor_year"))
        if status == "calculated" and row.get("calculated_tco2e") is not None:
            emissions_cell: Any = float(row["calculated_tco2e"])
        elif status == "not_emissions_activity":
            emissions_cell = "—"
        else:
            emissions_cell = t("chart.source.not_calculated", lang)
        rows.append(
            {
                "record_id": record_id,
                t("dash.col.activity", lang): row.get("activity_name"),
                t("dash.col.amount", lang): row.get("activity_amount"),
                t("intake.col.unit", lang): row.get("activity_unit"),
                t("dash.col.factor", lang): (
                    f"{factor_value:.6g}" if factor_value is not None else "—"
                ),
                t("dash.col.factor_year", lang): factor_year or "—",
                t("dash.col.emissions", lang): (
                    f"{emissions_cell:.6g}"
                    if isinstance(emissions_cell, float)
                    else emissions_cell
                ),
                t("dash.col.calc", lang): row.get("calculation_label"),
            }
        )
    return pd.DataFrame(rows)


def beginner_result_summary(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> dict[str, Any]:
    """Summarize five beginner questions for the results page."""
    kpis = dashboard_kpi_counts(result, lang)
    emissions = calculated_emissions_summary(result, lang)
    needs_work = max(0, int(kpis["activities"]) - int(kpis["calculated"]))
    return {
        "activities": kpis["activities"],
        "calculated": kpis["calculated"],
        "needs_work": needs_work,
        "open_qa_issues": kpis["open_qa_issues"],
        "source_documents": kpis["source_documents"],
        "calculated_tco2e": emissions["calculated_tco2e"],
        "emissions_label": emissions["label"],
        "calculated_row_count": emissions["calculated_row_count"],
    }


def first_calculated_electricity_record_id(
    result: PipelineRunResult,
) -> str | None:
    """Return a calculated grid_electricity record_id for trace examples."""
    activities = result.activity_records_accepted
    calcs = result.calculation_results
    if activities.empty or calcs.empty:
        return None
    electricity = activities[
        activities["activity_type"].astype(str) == "grid_electricity"
    ]
    if electricity.empty:
        return None
    for record_id in electricity["record_id"].astype(str).tolist():
        calc_row = calcs[calcs["record_id"].astype(str) == record_id]
        if calc_row.empty:
            continue
        if _text(calc_row.iloc[0].get("calculation_status")) == "calculated":
            return record_id
    return None


def activity_detail_context(
    result: PipelineRunResult,
    record_id: str,
    lang: str = DEFAULT_LANG,
) -> dict[str, Any]:
    """Assemble detail-panel data for one activity without mutating sources."""
    overview = build_activity_overview(result, lang)
    matched = overview[overview["record_id"] == record_id]
    if matched.empty:
        return {}
    row = matched.iloc[0]
    activity = _row_by_record(result.activity_records_accepted.copy(), record_id)
    calc = _row_by_record(result.calculation_results.copy(), record_id)
    normalized = _row_by_record(result.normalized_records.copy(), record_id)
    ghg = _row_by_record(result.ghg_evaluations.copy(), record_id)
    cbam = _row_by_record(result.cbam_evaluations.copy(), record_id)
    ifrs = _row_by_record(result.ifrs_s2_evaluations.copy(), record_id)
    issues = result.core_qa_issues.copy()
    record_issues = (
        issues[issues["record_id"].astype(str) == record_id]
        if not issues.empty and "record_id" in issues.columns
        else pd.DataFrame()
    )
    calc_status = _text(row.get("calculation_status"))
    return {
        "overview": row.to_dict(),
        "activity": activity.to_dict() if activity is not None else {},
        "calculation": calc.to_dict() if calc is not None else {},
        "normalized": normalized.to_dict() if normalized is not None else {},
        "ghg": ghg.to_dict() if ghg is not None else {},
        "cbam": cbam.to_dict() if cbam is not None else {},
        "ifrs_s2": ifrs.to_dict() if ifrs is not None else {},
        "issues": record_issues,
        "calculation_label": calculation_label(calc_status, lang),
        "calculation_explanation": calculation_explanation(calc_status, lang),
        "calculation_next_action": calculation_next_action(calc_status, lang),
    }


def ghg_scope_counts(
    result: PipelineRunResult,
    lang: str = DEFAULT_LANG,
) -> dict[str, int]:
    """Count GHG evaluation rows by display scope label."""
    if not result.include_ghg:
        return {}
    table = ghg_framework_table(result, lang)
    if table.empty:
        return {}
    counts = table["Scope"].value_counts().to_dict()
    return {str(key): int(value) for key, value in counts.items()}
