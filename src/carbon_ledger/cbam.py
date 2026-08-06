"""Optional deterministic EU CBAM data-role mapping.

Phase 6B maps activity records to CBAM data-preparation roles when an explicit
product scenario is supplied. The core Carbon Evidence Ledger remains usable
without CBAM. This module does not calculate emissions or reuse GHG Protocol
classifications.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

OUTPUT_COLUMNS = [
    "evaluation_id",
    "record_id",
    "framework",
    "scenario_id",
    "assumed_cn_code",
    "cn_classification_status",
    "annex_i_in_scope",
    "annex_ii_direct_only",
    "mapping_status",
    "cbam_relevance",
    "data_role",
    "rule_id",
    "rule_version",
    "reference_id",
    "reference_locator",
    "rationale",
    "allowed_use",
    "prohibited_use",
    "required_data",
    "requires_human_review",
]

FRAMEWORK = "eu_cbam"

DIRECT_EMISSION_CANDIDATE_TYPES = frozenset({"natural_gas", "diesel"})

SCENARIO_REQUIRED_FIELDS = (
    "scenario_id",
    "assumed_cn_code",
    "cn_classification_status",
    "annex_i_in_scope",
    "annex_ii_direct_only",
    "reference_id",
)


def load_cbam_references(reference_directory: Path) -> pd.DataFrame:
    """Load EU CBAM reference metadata from a reference directory."""
    path = Path(reference_directory) / "cbam_references.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_cbam_rules(config_directory: Path) -> pd.DataFrame:
    """Load versioned EU CBAM mapping rules from a config directory."""
    path = Path(config_directory) / "cbam_rules.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_cbam_product_scenario(config_directory: Path) -> pd.DataFrame:
    """Load configured CBAM product scenarios from a config directory."""
    path = Path(config_directory) / "cbam_product_scenario.csv"
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


def _parse_bool(value: Any) -> bool | None:
    text = _text(value).lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def _blank_to_na(value: str) -> Any:
    return value if value else pd.NA


def _rule_lookup(rules: pd.DataFrame) -> dict[str, pd.Series]:
    lookup: dict[str, pd.Series] = {}
    for _, row in rules.iterrows():
        rule_id = _text(row.get("rule_id"))
        if rule_id:
            lookup[rule_id] = row
    return lookup


def _scenario_context(scenario_row: pd.Series | None) -> dict[str, Any]:
    if scenario_row is None:
        return {
            "scenario_id": pd.NA,
            "assumed_cn_code": pd.NA,
            "cn_classification_status": pd.NA,
            "annex_i_in_scope": pd.NA,
            "annex_ii_direct_only": pd.NA,
        }
    annex_i = _parse_bool(scenario_row.get("annex_i_in_scope"))
    annex_ii = _parse_bool(scenario_row.get("annex_ii_direct_only"))
    return {
        "scenario_id": _text(scenario_row.get("scenario_id")),
        "assumed_cn_code": _text(scenario_row.get("assumed_cn_code")),
        "cn_classification_status": _text(
            scenario_row.get("cn_classification_status")
        ),
        "annex_i_in_scope": annex_i if annex_i is not None else pd.NA,
        "annex_ii_direct_only": annex_ii if annex_ii is not None else pd.NA,
    }


def _assess_scenario(
    product_scenario: pd.DataFrame,
    references: pd.DataFrame,
) -> tuple[str, pd.Series | None, str]:
    """Return scenario state, optional scenario row, and optional rationale."""
    if product_scenario.empty:
        return (
            "missing",
            None,
            (
                "The optional CBAM adapter cannot determine a data role "
                "without an explicit product and CN-code scenario."
            ),
        )

    if len(product_scenario) > 1:
        return (
            "multiple",
            None,
            (
                "Phase 6B supports one explicit CBAM product scenario per "
                "evaluation; multiple scenarios were supplied."
            ),
        )

    scenario_row = product_scenario.iloc[0]
    missing_fields = [
        field_name
        for field_name in SCENARIO_REQUIRED_FIELDS
        if _is_blank(scenario_row.get(field_name))
    ]
    if missing_fields:
        joined = ", ".join(missing_fields)
        return (
            "invalid",
            scenario_row,
            (
                f"CBAM product scenario is missing or blank required fields: "
                f"{joined}."
            ),
        )

    annex_i = _parse_bool(scenario_row.get("annex_i_in_scope"))
    annex_ii = _parse_bool(scenario_row.get("annex_ii_direct_only"))
    if annex_i is None or annex_ii is None:
        return (
            "invalid",
            scenario_row,
            (
                "CBAM product scenario annex_i_in_scope and "
                "annex_ii_direct_only must be true or false."
            ),
        )

    if annex_ii and not annex_i:
        return (
            "invalid",
            scenario_row,
            (
                "CBAM product scenario is inconsistent: annex_ii_direct_only "
                "cannot be true when annex_i_in_scope is false."
            ),
        )

    reference_ids = set(references["reference_id"].astype(str))
    reference_id = _text(scenario_row.get("reference_id"))
    if reference_id not in reference_ids:
        return (
            "invalid",
            scenario_row,
            (
                f"CBAM product scenario references unknown reference_id "
                f"{reference_id!r}."
            ),
        )

    if not annex_i:
        return (
            "outside_annex_i",
            scenario_row,
            (
                "The configured CBAM product scenario is outside Annex I, so "
                "the optional CBAM adapter is not applicable."
            ),
        )

    return "valid", scenario_row, ""


def _mapped_from_rule(
    *,
    record_id: str,
    rule: pd.Series,
    scenario_row: pd.Series,
    mapping_status_override: str | None = None,
    rationale_override: str | None = None,
    requires_human_review_override: bool | None = None,
) -> dict[str, Any]:
    context = _scenario_context(scenario_row)
    requires_review = (
        requires_human_review_override
        if requires_human_review_override is not None
        else _parse_bool(rule.get("requires_human_review"))
    )
    return {
        "evaluation_id": f"eval_cbam_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        **context,
        "mapping_status": mapping_status_override
        or _text(rule.get("mapping_status")),
        "cbam_relevance": _text(rule.get("cbam_relevance")),
        "data_role": _text(rule.get("data_role")),
        "rule_id": _text(rule.get("rule_id")),
        "rule_version": _text(rule.get("rule_version")),
        "reference_id": _text(rule.get("reference_id")),
        "reference_locator": _text(rule.get("reference_locator")),
        "rationale": rationale_override or _text(rule.get("rationale")),
        "allowed_use": _text(rule.get("allowed_use")),
        "prohibited_use": _text(rule.get("prohibited_use")),
        "required_data": _text(rule.get("required_data")),
        "requires_human_review": requires_review,
    }


def _needs_review(
    *,
    record_id: str,
    rationale: str,
    scenario_row: pd.Series | None = None,
    mapping_code: str = "needs_review",
) -> dict[str, Any]:
    context = _scenario_context(scenario_row)
    return {
        "evaluation_id": f"eval_cbam_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        **context,
        "mapping_status": "needs_review",
        "cbam_relevance": "data_gap",
        "data_role": _blank_to_na(mapping_code),
        "rule_id": pd.NA,
        "rule_version": pd.NA,
        "reference_id": pd.NA,
        "reference_locator": pd.NA,
        "rationale": rationale,
        "allowed_use": (
            "May be used only after human review clarifies the missing or "
            "inconsistent CBAM data-role inputs."
        ),
        "prohibited_use": (
            "Must not be treated as a final CBAM embedded-emissions or "
            "precursor-data determination."
        ),
        "required_data": "not_applicable",
        "requires_human_review": True,
    }


def _not_applicable(
    *,
    record_id: str,
    scenario_row: pd.Series,
    rationale: str,
) -> dict[str, Any]:
    context = _scenario_context(scenario_row)
    return {
        "evaluation_id": f"eval_cbam_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        **context,
        "mapping_status": "not_applicable",
        "cbam_relevance": "not_applicable",
        "data_role": pd.NA,
        "rule_id": pd.NA,
        "rule_version": pd.NA,
        "reference_id": pd.NA,
        "reference_locator": pd.NA,
        "rationale": rationale,
        "allowed_use": (
            "May support documentation that CBAM data preparation is not "
            "required for this product scenario."
        ),
        "prohibited_use": (
            "Must not be used to claim CBAM embedded-emissions results for a "
            "product outside Annex I."
        ),
        "required_data": "not_applicable",
        "requires_human_review": False,
    }


def _direct_emissions_inputs_need_review(
    activity_type: str,
    process_use: str,
    cbam_boundary: str,
) -> str | None:
    if activity_type not in DIRECT_EMISSION_CANDIDATE_TYPES:
        return None
    if cbam_boundary == "unknown" or cbam_boundary == "":
        return (
            "cbam_process_boundary_status is unknown or missing for a "
            "potential direct-emissions activity; CBAM data role is not "
            "guessed."
        )
    if process_use == "unknown" or process_use == "":
        return (
            "process_use is unknown or missing for a potential "
            "direct-emissions activity; CBAM data role is not guessed."
        )
    return None


def _evaluate_one_activity(
    activity: pd.Series,
    rules_by_id: dict[str, pd.Series],
    scenario_state: str,
    scenario_row: pd.Series | None,
    scenario_rationale: str,
) -> dict[str, Any]:
    record_id = _text(activity.get("record_id")) or "<missing>"
    activity_type = _text(activity.get("activity_type"))
    record_type = _text(activity.get("record_type"))
    process_use = _text(activity.get("process_use"))
    cbam_boundary = _text(activity.get("cbam_process_boundary_status"))

    if scenario_state == "missing":
        return _needs_review(
            record_id=record_id,
            rationale=scenario_rationale,
        )

    if scenario_state == "multiple":
        return _needs_review(
            record_id=record_id,
            rationale=scenario_rationale,
        )

    if scenario_state == "invalid":
        return _needs_review(
            record_id=record_id,
            rationale=scenario_rationale,
            scenario_row=scenario_row,
        )

    assert scenario_row is not None

    if scenario_state == "outside_annex_i":
        return _not_applicable(
            record_id=record_id,
            scenario_row=scenario_row,
            rationale=scenario_rationale,
        )

    annex_ii_direct_only = _parse_bool(scenario_row.get("annex_ii_direct_only"))

    # Grid electricity / Annex II supporting-only exclusion.
    if activity_type == "grid_electricity" and annex_ii_direct_only:
        rule = rules_by_id["cbam_annex2_electricity_supporting_only"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            scenario_row=scenario_row,
        )

    # Purchased steel / possible precursor data gap.
    if record_type == "material_input" and activity_type == "purchased_steel":
        rule = rules_by_id["cbam_purchased_steel_possible_precursor"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            scenario_row=scenario_row,
        )

    # Finished-goods output / product-quantity evidence.
    if (
        record_type == "production_output"
        and activity_type == "finished_goods_output"
    ):
        rule = rules_by_id["cbam_finished_output_quantity_evidence"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            scenario_row=scenario_row,
        )

    boundary_review = _direct_emissions_inputs_need_review(
        activity_type,
        process_use,
        cbam_boundary,
    )
    if boundary_review is not None:
        return _needs_review(
            record_id=record_id,
            rationale=boundary_review,
            scenario_row=scenario_row,
            mapping_code="direct_emissions_boundary_unknown",
        )

    # Heat-treatment natural gas / direct-emissions candidate.
    if (
        activity_type == "natural_gas"
        and process_use == "heat_treatment"
        and cbam_boundary == "inside"
    ):
        rule = rules_by_id["cbam_direct_heat_treatment_fuel_candidate"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            scenario_row=scenario_row,
        )

    # Company-vehicle diesel / outside process boundary.
    if (
        activity_type == "diesel"
        and process_use == "company_vehicle"
        and cbam_boundary == "outside"
    ):
        rule = rules_by_id["cbam_company_vehicle_outside_process_boundary"]
        return _mapped_from_rule(
            record_id=record_id,
            rule=rule,
            scenario_row=scenario_row,
        )

    return _needs_review(
        record_id=record_id,
        rationale=(
            f"No Phase 6B CBAM rule is configured for activity_type "
            f"{activity_type!r} / record_type {record_type!r}."
        ),
        scenario_row=scenario_row,
        mapping_code="unsupported_activity_type",
    )


def evaluate_cbam(
    activity_records: pd.DataFrame,
    rules: pd.DataFrame,
    references: pd.DataFrame,
    product_scenario: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate optional EU CBAM data roles for activity records.

    Returns one evaluation row per input activity. Does not mutate inputs and
    does not calculate emissions.
    """
    activities = activity_records.copy(deep=True)
    rules_frame = rules.copy(deep=True)
    refs_frame = references.copy(deep=True)
    scenario_frame = product_scenario.copy(deep=True)

    rules_by_id = _rule_lookup(rules_frame)
    scenario_state, scenario_row, scenario_rationale = _assess_scenario(
        scenario_frame,
        refs_frame,
    )

    results: list[dict[str, Any]] = []
    for _, activity in activities.iterrows():
        results.append(
            _evaluate_one_activity(
                activity,
                rules_by_id,
                scenario_state,
                scenario_row,
                scenario_rationale,
            )
        )

    if not results:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    output = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    output = output.sort_values("record_id", kind="mergesort").reset_index(
        drop=True
    )
    return output
