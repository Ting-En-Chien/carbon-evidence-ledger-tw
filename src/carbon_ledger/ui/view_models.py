"""Convert pipeline DataFrames into user-facing display tables.

Source PipelineRunResult frames are never mutated. Display labels hide
internal status codes from primary UI surfaces and honor UI language.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from carbon_ledger.pipeline import PipelineRunResult
from carbon_ledger.ui.i18n import DEFAULT_LANG, status_label, t

ACTIVITY_KEYS = {
    "grid_electricity": "activity.grid_electricity",
    "natural_gas": "activity.natural_gas",
    "diesel": "activity.diesel",
    "purchased_steel": "activity.purchased_steel",
    "finished_goods_output": "activity.finished_goods_output",
}

CBAM_ROLE_KEYS = {
    "supporting_energy_evidence": "cbam.role.supporting_energy",
    "direct_emissions_activity_candidate": "cbam.role.direct_candidate",
    "outside_process_boundary": "cbam.role.outside",
    "possible_precursor_candidate": "cbam.role.precursor",
    "product_quantity_denominator_candidate": "cbam.role.product_qty",
}

ATTENTION_TITLE_KEYS = {
    "blocked_missing_conversion": "status.attention_blocked",
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
    ]
    if issues.empty:
        return pd.DataFrame(columns=columns)

    name_by_record = {
        _text(row.get("record_id")): activity_display_name(
            _text(row.get("activity_type")), lang
        )
        for _, row in activities.iterrows()
    }
    rows: list[dict[str, Any]] = []
    for _, issue in issues.iterrows():
        record_id = _text(issue.get("record_id"))
        severity_code = _text(issue.get("severity"))
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
                "source_document_id": _text(issue.get("source_document_id")),
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


def evidence_documents_table(result: PipelineRunResult) -> pd.DataFrame:
    """Build the accepted source-document evidence table."""
    docs = result.source_documents_accepted.copy()
    if docs.empty:
        return pd.DataFrame(
            columns=[
                "Document ID",
                "Document type",
                "Source name",
                "Evidence hash",
                "Data origin",
                "Review status",
            ]
        )
    rows: list[dict[str, Any]] = []
    for _, doc in docs.iterrows():
        rows.append(
            {
                "Document ID": _text(doc.get("source_document_id")),
                "Document type": _text(doc.get("document_type")).replace("_", " "),
                "Source name": _text(doc.get("issuer"))
                or _text(doc.get("file_name")),
                "Evidence hash": _text(doc.get("sha256")),
                "Data origin": _text(doc.get("data_origin")).replace("_", " "),
                "Review status": "Synthetic demonstration",
            }
        )
    return pd.DataFrame(rows)


def audit_summary(result: PipelineRunResult) -> dict[str, Any]:
    """Build compact audit metrics and run metadata."""
    return {
        "accepted_source_documents": int(len(result.source_documents_accepted)),
        "accepted_activities": int(len(result.activity_records_accepted)),
        "calculation_rows": int(len(result.calculation_results)),
        "qa_issues": int(len(result.core_qa_issues)),
        "run_id": result.run_id,
        "ingested_at": "2024-02-01T00:00:00+00:00",
        "include_ghg": bool(result.include_ghg),
        "include_cbam": bool(result.include_cbam),
        "include_ifrs_s2": bool(result.include_ifrs_s2),
    }


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
