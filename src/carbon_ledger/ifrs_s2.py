"""Optional deterministic IFRS S2 climate-data readiness mapping.

Phase 6C maps activity records to IFRS S2 metrics-and-targets readiness when an
explicit reporting context is supplied. The core Carbon Evidence Ledger remains
usable without IFRS S2. This module does not create disclosures, assess
materiality, or determine compliance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

OUTPUT_COLUMNS = [
    "evaluation_id",
    "record_id",
    "framework",
    "context_id",
    "assessment_purpose",
    "reporting_period_start",
    "reporting_period_end",
    "content_area",
    "mapping_status",
    "readiness_status",
    "data_role",
    "disclosure_topic",
    "source_calculation_id",
    "source_ghg_evaluation_id",
    "rule_id",
    "rule_version",
    "reference_id",
    "reference_locator",
    "rationale",
    "available_evidence",
    "missing_data",
    "allowed_use",
    "prohibited_use",
    "requires_human_review",
]

FRAMEWORK = "ifrs_s2"

CONTEXT_REQUIRED_FIELDS = (
    "context_id",
    "reporting_entity",
    "assessment_purpose",
    "applicability_status",
    "reporting_period_start",
    "reporting_period_end",
    "jurisdictional_requirement_status",
    "materiality_assessment_status",
    "standard_reference_id",
    "amendments_2025_application_status",
    "requires_human_review",
)


def load_ifrs_s2_references(reference_directory: Path) -> pd.DataFrame:
    """Load IFRS S2 reference metadata from a reference directory."""
    path = Path(reference_directory) / "ifrs_s2_references.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_ifrs_s2_rules(config_directory: Path) -> pd.DataFrame:
    """Load versioned IFRS S2 readiness rules from a config directory."""
    path = Path(config_directory) / "ifrs_s2_rules.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_ifrs_s2_reporting_context(config_directory: Path) -> pd.DataFrame:
    """Load configured IFRS S2 reporting contexts from a config directory."""
    path = Path(config_directory) / "ifrs_s2_reporting_context.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _text(value: Any) -> str:
    if _is_blank(value):
        return ""
    return str(value).strip()


def _parse_bool(value: Any) -> bool:
    return _text(value).lower() == "true"


def _rule_lookup(rules: pd.DataFrame) -> dict[str, pd.Series]:
    lookup: dict[str, pd.Series] = {}
    for _, row in rules.iterrows():
        rule_id = _text(row.get("rule_id"))
        if rule_id:
            lookup[rule_id] = row
    return lookup


def _context_fields(context_row: pd.Series | None) -> dict[str, Any]:
    if context_row is None:
        return {
            "context_id": pd.NA,
            "assessment_purpose": pd.NA,
            "reporting_period_start": pd.NA,
            "reporting_period_end": pd.NA,
        }
    return {
        "context_id": _text(context_row.get("context_id")),
        "assessment_purpose": _text(context_row.get("assessment_purpose")),
        "reporting_period_start": _text(context_row.get("reporting_period_start")),
        "reporting_period_end": _text(context_row.get("reporting_period_end")),
    }


def _assess_context(
    reporting_context: pd.DataFrame,
    references: pd.DataFrame,
) -> tuple[str, pd.Series | None, str]:
    if reporting_context.empty:
        return (
            "missing",
            None,
            (
                "The optional IFRS S2 adapter cannot determine readiness "
                "without an explicit reporting context."
            ),
        )

    if len(reporting_context) > 1:
        return (
            "multiple",
            None,
            (
                "Phase 6C supports one explicit IFRS S2 reporting context per "
                "evaluation; multiple contexts were supplied."
            ),
        )

    context_row = reporting_context.iloc[0]
    missing_fields = [
        field_name
        for field_name in CONTEXT_REQUIRED_FIELDS
        if _is_blank(context_row.get(field_name))
    ]
    if missing_fields:
        joined = ", ".join(missing_fields)
        return (
            "invalid",
            context_row,
            (
                f"IFRS S2 reporting context is missing or blank required "
                f"fields: {joined}."
            ),
        )

    reference_ids = set(references["reference_id"].astype(str))
    standard_ref = _text(context_row.get("standard_reference_id"))
    if standard_ref not in reference_ids:
        return (
            "invalid",
            context_row,
            (
                f"IFRS S2 reporting context references unknown "
                f"standard_reference_id {standard_ref!r}."
            ),
        )

    if _text(context_row.get("applicability_status")) == "not_applicable":
        return (
            "not_applicable",
            context_row,
            (
                "The configured IFRS S2 reporting context is explicitly not "
                "applicable, so the optional adapter does not apply readiness "
                "rules."
            ),
        )

    return "valid", context_row, ""


def _source_frame_available(frame: pd.DataFrame) -> bool:
    return not frame.empty and "record_id" in frame.columns


def _missing_source_frame_rationale(source_kind: str) -> str:
    if source_kind == "calculation":
        return (
            "Calculation result evidence is missing because calculation_results "
            "is empty or does not include a record_id column."
        )
    return (
        "GHG Protocol evaluation evidence is missing because ghg_evaluations "
        "is empty or does not include a record_id column."
    )


def _lookup_by_record_id(
    frame: pd.DataFrame,
    record_id: str,
    label: str,
) -> tuple[str, pd.Series | None, str]:
    matches = frame.loc[frame["record_id"] == record_id]
    if matches.empty:
        return (
            "missing",
            None,
            f"No {label} exists for record_id {record_id!r}.",
        )
    if len(matches) > 1:
        return (
            "duplicate",
            None,
            f"Multiple {label} rows exist for record_id {record_id!r}.",
        )
    return "ok", matches.iloc[0], ""


def _mapped_from_rule(
    *,
    record_id: str,
    rule: pd.Series,
    context_row: pd.Series,
    source_calculation_id: Any,
    source_ghg_evaluation_id: Any,
    mapping_status_override: str | None = None,
    rationale_override: str | None = None,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"eval_ifrs_s2_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        **_context_fields(context_row),
        "content_area": _text(rule.get("content_area")),
        "mapping_status": mapping_status_override
        or _text(rule.get("mapping_status")),
        "readiness_status": _text(rule.get("readiness_status")),
        "data_role": _text(rule.get("data_role")),
        "disclosure_topic": _text(rule.get("disclosure_topic")),
        "source_calculation_id": source_calculation_id,
        "source_ghg_evaluation_id": source_ghg_evaluation_id,
        "rule_id": _text(rule.get("rule_id")),
        "rule_version": _text(rule.get("rule_version")),
        "reference_id": _text(rule.get("reference_id")),
        "reference_locator": _text(rule.get("reference_locator")),
        "rationale": rationale_override or _text(rule.get("rationale")),
        "available_evidence": _text(rule.get("available_evidence")),
        "missing_data": _text(rule.get("missing_data")),
        "allowed_use": _text(rule.get("allowed_use")),
        "prohibited_use": _text(rule.get("prohibited_use")),
        "requires_human_review": _parse_bool(rule.get("requires_human_review")),
    }


def _needs_review(
    *,
    record_id: str,
    rationale: str,
    context_row: pd.Series | None = None,
    source_calculation_id: Any = pd.NA,
    source_ghg_evaluation_id: Any = pd.NA,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"eval_ifrs_s2_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        **_context_fields(context_row),
        "content_area": pd.NA,
        "mapping_status": "needs_review",
        "readiness_status": "data_gap",
        "data_role": pd.NA,
        "disclosure_topic": pd.NA,
        "source_calculation_id": source_calculation_id,
        "source_ghg_evaluation_id": source_ghg_evaluation_id,
        "rule_id": pd.NA,
        "rule_version": pd.NA,
        "reference_id": pd.NA,
        "reference_locator": pd.NA,
        "rationale": rationale,
        "available_evidence": pd.NA,
        "missing_data": (
            "Materiality assessment; jurisdictional applicability; reporting "
            "completeness; and any missing source-evidence linkage must be "
            "resolved before readiness can be determined."
        ),
        "allowed_use": (
            "May be used only after human review clarifies the missing or "
            "inconsistent readiness inputs."
        ),
        "prohibited_use": (
            "Must not be treated as a final IFRS S2 readiness conclusion, "
            "compliance statement, or materiality determination."
        ),
        "requires_human_review": True,
    }


def _not_applicable(
    *,
    record_id: str,
    context_row: pd.Series,
    rationale: str,
    source_calculation_id: Any = pd.NA,
    source_ghg_evaluation_id: Any = pd.NA,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"eval_ifrs_s2_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        **_context_fields(context_row),
        "content_area": pd.NA,
        "mapping_status": "not_applicable",
        "readiness_status": "not_applicable",
        "data_role": pd.NA,
        "disclosure_topic": pd.NA,
        "source_calculation_id": source_calculation_id,
        "source_ghg_evaluation_id": source_ghg_evaluation_id,
        "rule_id": pd.NA,
        "rule_version": pd.NA,
        "reference_id": pd.NA,
        "reference_locator": pd.NA,
        "rationale": rationale,
        "available_evidence": pd.NA,
        "missing_data": "not_applicable",
        "allowed_use": (
            "May support documentation that IFRS S2 readiness assessment is "
            "not required for this reporting context."
        ),
        "prohibited_use": (
            "Must not be used to claim IFRS S2 metrics-and-targets readiness "
            "for a context marked not applicable."
        ),
        "requires_human_review": False,
    }


def _ghg_scope_1_stationary(ghg_row: pd.Series) -> bool:
    return (
        _text(ghg_row.get("ghg_scope")) == "scope_1"
        and _text(ghg_row.get("mapping_code")) == "scope1_stationary_combustion"
    )


def _ghg_scope_1_mobile(ghg_row: pd.Series) -> bool:
    return (
        _text(ghg_row.get("ghg_scope")) == "scope_1"
        and _text(ghg_row.get("mapping_code")) == "scope1_mobile_combustion"
    )


def _ghg_scope_3_category_1(ghg_row: pd.Series) -> bool:
    return (
        _text(ghg_row.get("ghg_scope")) == "scope_3"
        and _text(ghg_row.get("mapping_code"))
        == "scope3_category1_purchased_goods_services"
    )


def _ghg_not_applicable(ghg_row: pd.Series) -> bool:
    return _text(ghg_row.get("mapping_status")) == "not_applicable"


def _evaluate_one_activity(
    activity: pd.Series,
    rules_by_id: dict[str, pd.Series],
    context_state: str,
    context_row: pd.Series | None,
    context_rationale: str,
    calc_row: pd.Series | None,
    ghg_row: pd.Series | None,
    source_issue: str | None,
) -> dict[str, Any]:
    record_id = _text(activity.get("record_id")) or "<missing>"
    activity_type = _text(activity.get("activity_type"))
    record_type = _text(activity.get("record_type"))

    calc_id = (
        _text(calc_row.get("calculation_id")) if calc_row is not None else pd.NA
    )
    ghg_id = (
        _text(ghg_row.get("evaluation_id")) if ghg_row is not None else pd.NA
    )

    if context_state == "missing":
        return _needs_review(record_id=record_id, rationale=context_rationale)

    if context_state == "multiple":
        return _needs_review(record_id=record_id, rationale=context_rationale)

    if context_state == "invalid":
        return _needs_review(
            record_id=record_id,
            rationale=context_rationale,
            context_row=context_row,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    assert context_row is not None

    if context_state == "not_applicable":
        return _not_applicable(
            record_id=record_id,
            context_row=context_row,
            rationale=context_rationale,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    if source_issue is not None:
        return _needs_review(
            record_id=record_id,
            rationale=source_issue,
            context_row=context_row,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    assert calc_row is not None
    assert ghg_row is not None
    calc_status = _text(calc_row.get("calculation_status"))

    # Grid electricity / partial Scope 2 evidence.
    if activity_type == "grid_electricity":
        if calc_status != "calculated" or _text(ghg_row.get("ghg_scope")) != "scope_2":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Grid-electricity IFRS S2 readiness requires calculation_status "
                    "= calculated and a Scope 2 GHG Protocol evaluation; source "
                    "evidence is inconsistent."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        rule = rules_by_id["ifrs_s2_scope2_electricity_partial_evidence"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            context_row=context_row,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    # Natural gas / Scope 1 stationary combustion data gap.
    if activity_type == "natural_gas":
        if not _ghg_scope_1_stationary(ghg_row):
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Natural-gas IFRS S2 readiness requires a Scope 1 stationary-"
                    "combustion GHG Protocol evaluation; source evidence is "
                    "inconsistent."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        if calc_status != "blocked_missing_conversion":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Natural-gas IFRS S2 readiness expects calculation_status "
                    "= blocked_missing_conversion for the current prototype; "
                    f"got {calc_status!r}."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        rule = rules_by_id["ifrs_s2_scope1_stationary_combustion_data_gap"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            context_row=context_row,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    # Diesel / Scope 1 mobile combustion data gap.
    if activity_type == "diesel":
        if not _ghg_scope_1_mobile(ghg_row):
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Diesel IFRS S2 readiness requires a Scope 1 mobile-combustion "
                    "GHG Protocol evaluation; source evidence is inconsistent."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        if calc_status != "blocked_missing_conversion":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Diesel IFRS S2 readiness expects calculation_status "
                    "= blocked_missing_conversion for the current prototype; "
                    f"got {calc_status!r}."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        rule = rules_by_id["ifrs_s2_scope1_mobile_combustion_data_gap"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            context_row=context_row,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    # Purchased steel / Scope 3 Category 1 data gap.
    if record_type == "material_input" and activity_type == "purchased_steel":
        if not _ghg_scope_3_category_1(ghg_row):
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Purchased-steel IFRS S2 readiness requires a Scope 3 "
                    "Category 1 GHG Protocol evaluation; source evidence is "
                    "inconsistent."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        if calc_status != "no_factor_configured":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Purchased-steel IFRS S2 readiness expects calculation_status "
                    "= no_factor_configured for the current prototype; "
                    f"got {calc_status!r}."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        rule = rules_by_id["ifrs_s2_scope3_category1_data_gap"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            context_row=context_row,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    # Finished-goods output / supporting metric candidate.
    if (
        record_type == "production_output"
        and activity_type == "finished_goods_output"
    ):
        if calc_status != "not_emissions_activity" or not _ghg_not_applicable(
            ghg_row
        ):
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Finished-goods output IFRS S2 readiness requires "
                    "calculation_status = not_emissions_activity and a GHG "
                    "Protocol not_applicable evaluation; source evidence is "
                    "inconsistent."
                ),
                context_row=context_row,
                source_calculation_id=calc_id,
                source_ghg_evaluation_id=ghg_id,
            )
        rule = rules_by_id["ifrs_s2_finished_output_supporting_metric_candidate"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            context_row=context_row,
            source_calculation_id=calc_id,
            source_ghg_evaluation_id=ghg_id,
        )

    return _needs_review(
        record_id=record_id,
        rationale=(
            f"No Phase 6C IFRS S2 readiness rule is configured for activity_type "
            f"{activity_type!r} / record_type {record_type!r}."
        ),
        context_row=context_row,
        source_calculation_id=calc_id,
        source_ghg_evaluation_id=ghg_id,
    )


def evaluate_ifrs_s2_readiness(
    activity_records: pd.DataFrame,
    calculation_results: pd.DataFrame,
    ghg_evaluations: pd.DataFrame,
    rules: pd.DataFrame,
    references: pd.DataFrame,
    reporting_context: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate optional IFRS S2 climate-data readiness for activity records.

    Returns one readiness row per input activity. Does not mutate inputs and
    does not create IFRS S2 disclosures.
    """
    activities = activity_records.copy(deep=True)
    calculations = calculation_results.copy(deep=True)
    ghg_frame = ghg_evaluations.copy(deep=True)
    rules_frame = rules.copy(deep=True)
    refs_frame = references.copy(deep=True)
    context_frame = reporting_context.copy(deep=True)

    rules_by_id = _rule_lookup(rules_frame)
    context_state, context_row, context_rationale = _assess_context(
        context_frame,
        refs_frame,
    )
    calc_frame_ok = _source_frame_available(calculations)
    ghg_frame_ok = _source_frame_available(ghg_frame)

    results: list[dict[str, Any]] = []
    for _, activity in activities.iterrows():
        record_id = _text(activity.get("record_id")) or "<missing>"
        calc_row: pd.Series | None = None
        ghg_row: pd.Series | None = None
        source_issue: str | None = None

        if calc_frame_ok:
            calc_state, calc_row, calc_issue = _lookup_by_record_id(
                calculations,
                record_id,
                "calculation result",
            )
        else:
            calc_state = "unavailable"

        if ghg_frame_ok:
            ghg_state, ghg_row, ghg_issue = _lookup_by_record_id(
                ghg_frame,
                record_id,
                "GHG Protocol evaluation",
            )
        else:
            ghg_state = "unavailable"

        if context_state == "valid":
            if not calc_frame_ok:
                source_issue = _missing_source_frame_rationale("calculation")
            elif not ghg_frame_ok:
                source_issue = _missing_source_frame_rationale("ghg")
            elif calc_state != "ok":
                source_issue = calc_issue
            elif ghg_state != "ok":
                source_issue = ghg_issue

        results.append(
            _evaluate_one_activity(
                activity,
                rules_by_id,
                context_state,
                context_row,
                context_rationale,
                calc_row,
                ghg_row,
                source_issue,
            )
        )

    if not results:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    output = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    output = output.sort_values("record_id", kind="mergesort").reset_index(
        drop=True
    )
    return output
