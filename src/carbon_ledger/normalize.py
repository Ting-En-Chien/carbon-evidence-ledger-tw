"""Safe unit normalization for accepted activity records.

Phase 4 converts supported activity units into consistent canonical units.
It does not calculate emissions or apply framework mappings.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

# Canonical units by activity type.
CANONICAL_UNITS: dict[str, str] = {
    "grid_electricity": "kWh",
    "natural_gas": "m3",
    "diesel": "L",
    "refrigerant_refill": "kg",
    "purchased_steel": "t",
    "finished_goods_output": "t",
    "scrap_output": "t",
}

# Explicit conversion factors: (source_unit, target_unit) -> multiplier.
CONVERSION_FACTORS: dict[tuple[str, str], float] = {
    ("MWh", "kWh"): 1000.0,
    ("kWh", "MWh"): 0.001,
    ("kg", "t"): 0.001,
    ("t", "kg"): 1000.0,
}

OUTPUT_COLUMNS = [
    "record_id",
    "activity_type",
    "original_value",
    "original_unit",
    "normalized_value",
    "normalized_unit",
    "normalization_status",
    "normalization_reason",
]


def convert_unit(value: float, source_unit: str, target_unit: str) -> float:
    """Convert a numeric value between explicitly supported units.

    Returns the original value when source and target units match.
    Raises ValueError for unsupported conversions.
    Does not round the result.
    """
    if source_unit == target_unit:
        return float(value)

    key = (source_unit, target_unit)
    if key not in CONVERSION_FACTORS:
        raise ValueError(
            f"Unsupported conversion from {source_unit!r} to {target_unit!r}."
        )
    return float(value) * CONVERSION_FACTORS[key]


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _parse_numeric_value(value: Any) -> float | None:
    """Return a finite float, or None when the value is invalid."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        if number <= 0:
            return None
        return number
    if isinstance(value, str):
        return None
    return None


def _result_row(
    *,
    record_id: Any,
    activity_type: Any,
    original_value: Any,
    original_unit: Any,
    normalized_value: Any,
    normalized_unit: Any,
    normalization_status: str,
    normalization_reason: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "activity_type": activity_type,
        "original_value": original_value,
        "original_unit": original_unit,
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "normalization_status": normalization_status,
        "normalization_reason": normalization_reason,
    }


def normalize_activity_records(activity_records: pd.DataFrame) -> pd.DataFrame:
    """Normalize activity units into canonical units without mutating input.

    Returns one derived result row for every input row, preserving order.
    Problematic rows remain visible with a status and reason.
    """
    working = activity_records.copy(deep=True)
    results: list[dict[str, Any]] = []

    for _, row in working.iterrows():
        record_id = row.get("record_id")
        activity_type = row.get("activity_type")
        original_value = row.get("activity_value")
        original_unit = row.get("unit")

        if _is_blank(original_unit):
            results.append(
                _result_row(
                    record_id=record_id,
                    activity_type=activity_type,
                    original_value=original_value,
                    original_unit=original_unit,
                    normalized_value=pd.NA,
                    normalized_unit=pd.NA,
                    normalization_status="invalid_unit",
                    normalization_reason="Unit is missing or blank.",
                )
            )
            continue

        unit_text = str(original_unit).strip()
        numeric_value = _parse_numeric_value(original_value)
        if numeric_value is None:
            results.append(
                _result_row(
                    record_id=record_id,
                    activity_type=activity_type,
                    original_value=original_value,
                    original_unit=unit_text,
                    normalized_value=pd.NA,
                    normalized_unit=pd.NA,
                    normalization_status="invalid_value",
                    normalization_reason=(
                        "activity_value must be a finite number greater than zero."
                    ),
                )
            )
            continue

        activity_type_text = (
            None if _is_blank(activity_type) else str(activity_type).strip()
        )
        if activity_type_text not in CANONICAL_UNITS:
            results.append(
                _result_row(
                    record_id=record_id,
                    activity_type=activity_type,
                    original_value=numeric_value,
                    original_unit=unit_text,
                    normalized_value=pd.NA,
                    normalized_unit=pd.NA,
                    normalization_status="unsupported_activity_type",
                    normalization_reason=(
                        f"No canonical-unit rule for activity_type "
                        f"{activity_type_text!r}."
                    ),
                )
            )
            continue

        canonical_unit = CANONICAL_UNITS[activity_type_text]

        if unit_text == canonical_unit:
            results.append(
                _result_row(
                    record_id=record_id,
                    activity_type=activity_type_text,
                    original_value=numeric_value,
                    original_unit=unit_text,
                    normalized_value=numeric_value,
                    normalized_unit=canonical_unit,
                    normalization_status="already_canonical",
                    normalization_reason=(
                        f"Unit {unit_text!r} is already canonical for "
                        f"{activity_type_text!r}."
                    ),
                )
            )
            continue

        try:
            converted = convert_unit(numeric_value, unit_text, canonical_unit)
        except ValueError:
            results.append(
                _result_row(
                    record_id=record_id,
                    activity_type=activity_type_text,
                    original_value=numeric_value,
                    original_unit=unit_text,
                    normalized_value=pd.NA,
                    normalized_unit=pd.NA,
                    normalization_status="unsupported_conversion",
                    normalization_reason=(
                        f"Cannot safely convert {unit_text!r} to canonical "
                        f"unit {canonical_unit!r} for {activity_type_text!r}."
                    ),
                )
            )
            continue

        results.append(
            _result_row(
                record_id=record_id,
                activity_type=activity_type_text,
                original_value=numeric_value,
                original_unit=unit_text,
                normalized_value=converted,
                normalized_unit=canonical_unit,
                normalization_status="normalized",
                normalization_reason=(
                    f"Converted {unit_text!r} to canonical unit "
                    f"{canonical_unit!r}."
                ),
            )
        )

    if not results:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    output = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    return output
