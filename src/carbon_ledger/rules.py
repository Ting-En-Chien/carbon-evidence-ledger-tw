"""Deterministic GHG Protocol classification rules.

Phase 6A maps activity records to Scope 1 / 2 / 3 classifications. Mapping is
independent of emissions calculation readiness and of CBAM / IFRS S2 results.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

OUTPUT_COLUMNS = [
    "evaluation_id",
    "record_id",
    "framework",
    "mapping_status",
    "mapping_code",
    "ghg_scope",
    "scope3_category",
    "rule_id",
    "rule_version",
    "reference_id",
    "reference_locator",
    "rationale",
    "allowed_use",
    "prohibited_use",
    "requires_human_review",
]

FRAMEWORK = "ghg_protocol"

OWNED_OR_CONTROLLED = {"owned", "controlled"}


def load_ghg_protocol_references(reference_directory: Path) -> pd.DataFrame:
    """Load GHG Protocol reference metadata from a reference directory."""
    path = Path(reference_directory) / "ghg_protocol_references.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_ghg_protocol_rules(config_directory: Path) -> pd.DataFrame:
    """Load versioned GHG Protocol mapping rules from a config directory."""
    path = Path(config_directory) / "ghg_protocol_rules.csv"
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


def _blank_to_na(value: str) -> Any:
    return value if value else pd.NA


def _mapped_from_rule(
    *,
    record_id: str,
    mapping_status: str,
    rule: pd.Series,
    rationale_override: str | None = None,
    requires_human_review_override: bool | None = None,
) -> dict[str, Any]:
    requires_review = (
        requires_human_review_override
        if requires_human_review_override is not None
        else _parse_bool(rule.get("requires_human_review"))
    )
    return {
        "evaluation_id": f"eval_ghg_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        "mapping_status": mapping_status,
        "mapping_code": _text(rule.get("mapping_code")),
        "ghg_scope": _text(rule.get("ghg_scope")),
        "scope3_category": _blank_to_na(_text(rule.get("scope3_category"))),
        "rule_id": _text(rule.get("rule_id")),
        "rule_version": _text(rule.get("rule_version")),
        "reference_id": _text(rule.get("reference_id")),
        "reference_locator": _text(rule.get("reference_locator")),
        "rationale": rationale_override or _text(rule.get("rationale")),
        "allowed_use": _text(rule.get("allowed_use")),
        "prohibited_use": _text(rule.get("prohibited_use")),
        "requires_human_review": requires_review,
    }


def _needs_review(
    *,
    record_id: str,
    rationale: str,
    mapping_code: str = "needs_review",
) -> dict[str, Any]:
    return {
        "evaluation_id": f"eval_ghg_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        "mapping_status": "needs_review",
        "mapping_code": mapping_code,
        "ghg_scope": "unknown",
        "scope3_category": pd.NA,
        "rule_id": pd.NA,
        "rule_version": pd.NA,
        "reference_id": pd.NA,
        "reference_locator": pd.NA,
        "rationale": rationale,
        "allowed_use": (
            "May be used only after human review clarifies the missing or "
            "inconsistent classification inputs."
        ),
        "prohibited_use": (
            "Must not be treated as a final GHG Protocol Scope assignment."
        ),
        "requires_human_review": True,
    }


def _outside_boundary(
    *,
    record_id: str,
    activity_type: str,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"eval_ghg_{record_id}",
        "record_id": record_id,
        "framework": FRAMEWORK,
        "mapping_status": "outside_boundary",
        "mapping_code": "outside_corporate_inventory_boundary",
        "ghg_scope": "not_applicable",
        "scope3_category": pd.NA,
        "rule_id": pd.NA,
        "rule_version": pd.NA,
        "reference_id": pd.NA,
        "reference_locator": pd.NA,
        "rationale": (
            f"Activity type {activity_type!r} is marked outside the current "
            "corporate inventory boundary, so Scope 1 or Scope 2 is not assigned."
        ),
        "allowed_use": (
            "May support inventory-boundary documentation and exclusion notes."
        ),
        "prohibited_use": (
            "Must not be counted as corporate Scope 1 or Scope 2 for this "
            "inventory boundary."
        ),
        "requires_human_review": False,
    }


def _evaluate_one_activity(
    activity: pd.Series,
    rules_by_id: dict[str, pd.Series],
) -> dict[str, Any]:
    record_id = _text(activity.get("record_id")) or "<missing>"
    activity_type = _text(activity.get("activity_type"))
    record_type = _text(activity.get("record_type"))
    process_use = _text(activity.get("process_use"))
    ownership_control = _text(activity.get("ownership_control"))
    org_boundary = _text(activity.get("organizational_boundary_status"))

    # Unknown core fields fail closed to human review.
    for field_name, field_value in (
        ("activity_type", activity_type),
        ("record_type", record_type),
        ("organizational_boundary_status", org_boundary),
        ("ownership_control", ownership_control),
    ):
        if field_value == "unknown" or field_value == "":
            label = "missing" if field_value == "" else "unknown"
            return _needs_review(
                record_id=record_id,
                rationale=(
                    f"Field {field_name} is {label}; GHG Protocol Scope is "
                    "not guessed."
                ),
            )

    # Finished-goods / production output.
    if (
        record_type == "production_output"
        and activity_type == "finished_goods_output"
    ):
        rule = rules_by_id["ghg_not_emissions_activity_production_output"]
        return _mapped_from_rule(
            record_id=record_id,
            mapping_status="not_applicable",
            rule=rule,
        )

    # Purchased steel / Scope 3 Category 1.
    if record_type == "material_input" and activity_type == "purchased_steel":
        rule = rules_by_id["ghg_scope3_category1_purchased_steel"]
        return _mapped_from_rule(
            record_id=record_id,
            mapping_status="mapped",
            rule=rule,
        )

    # Grid electricity / Scope 2.
    if activity_type == "grid_electricity":
        if org_boundary == "outside":
            return _outside_boundary(
                record_id=record_id, activity_type=activity_type
            )
        if org_boundary != "inside":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "organizational_boundary_status must be inside for "
                    "Scope 2 purchased-electricity mapping, or outside for "
                    "an explicit boundary exclusion."
                ),
            )
        rule = rules_by_id["ghg_scope2_purchased_electricity"]
        return _mapped_from_rule(
            record_id=record_id,
            mapping_status="mapped",
            rule=rule,
        )

    # Natural gas / Scope 1 stationary combustion.
    if activity_type == "natural_gas":
        if process_use == "unknown" or process_use == "":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "process_use is unknown or missing for natural-gas "
                    "stationary-combustion classification."
                ),
            )
        if org_boundary == "outside":
            return _outside_boundary(
                record_id=record_id, activity_type=activity_type
            )
        if org_boundary != "inside":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "organizational_boundary_status must be inside for "
                    "Scope 1 natural-gas mapping."
                ),
            )
        if process_use != "heat_treatment":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Natural-gas Scope 1 stationary mapping in Phase 6A "
                    "requires process_use = heat_treatment."
                ),
            )
        if ownership_control not in OWNED_OR_CONTROLLED:
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Natural-gas Scope 1 mapping requires ownership_control "
                    "owned or controlled; "
                    f"got {ownership_control!r}."
                ),
            )
        rule = rules_by_id["ghg_scope1_stationary_combustion"]
        return _mapped_from_rule(
            record_id=record_id,
            mapping_status="mapped",
            rule=rule,
        )

    # Diesel / Scope 1 mobile combustion.
    if activity_type == "diesel":
        if process_use == "unknown" or process_use == "":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "process_use is unknown or missing for diesel "
                    "mobile-combustion classification."
                ),
            )
        if org_boundary == "outside":
            return _outside_boundary(
                record_id=record_id, activity_type=activity_type
            )
        if org_boundary != "inside":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "organizational_boundary_status must be inside for "
                    "Scope 1 diesel mapping."
                ),
            )
        if process_use != "company_vehicle":
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Diesel Scope 1 mobile mapping in Phase 6A requires "
                    "process_use = company_vehicle."
                ),
            )
        if ownership_control not in OWNED_OR_CONTROLLED:
            return _needs_review(
                record_id=record_id,
                rationale=(
                    "Diesel Scope 1 mapping requires ownership_control owned "
                    f"or controlled; got {ownership_control!r}."
                ),
            )
        rule = rules_by_id["ghg_scope1_mobile_combustion"]
        return _mapped_from_rule(
            record_id=record_id,
            mapping_status="mapped",
            rule=rule,
        )

    return _needs_review(
        record_id=record_id,
        rationale=(
            f"No Phase 6A GHG Protocol rule is configured for activity_type "
            f"{activity_type!r} / record_type {record_type!r}."
        ),
        mapping_code="unsupported_activity_type",
    )


def evaluate_ghg_protocol(
    activity_records: pd.DataFrame,
    rules: pd.DataFrame,
    references: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate GHG Protocol classifications for activity records.

    Returns one evaluation row per input activity. Does not mutate inputs and
    does not calculate emissions.
    """
    activities = activity_records.copy(deep=True)
    rules_frame = rules.copy(deep=True)
    _ = references.copy(deep=True)

    rules_by_id = _rule_lookup(rules_frame)
    results: list[dict[str, Any]] = []

    for _, activity in activities.iterrows():
        results.append(_evaluate_one_activity(activity, rules_by_id))

    if not results:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    output = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    output = output.sort_values("record_id", kind="mergesort").reset_index(
        drop=True
    )
    return output
