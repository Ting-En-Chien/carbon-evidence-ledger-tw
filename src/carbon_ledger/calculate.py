"""Limited and auditable emissions calculation for ready activities only.

Phase 5C calculates emissions only when readiness, factor matching, units, and
values all agree. It does not invent fallbacks or framework mappings.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

FORMULA_ID = "activity_value_times_direct_co2e_factor"
FORMULA_VERSION = "1.0"

OUTPUT_COLUMNS = [
    "calculation_id",
    "record_id",
    "activity_type",
    "normalized_value",
    "normalized_unit",
    "factor_id",
    "factor_value",
    "factor_numerator_unit",
    "factor_denominator_unit",
    "source_reference_id",
    "formula_id",
    "formula_version",
    "calculated_kgco2e",
    "calculated_tco2e",
    "calculation_status",
    "calculation_reason",
]

PASSTHROUGH_STATUSES = {
    "blocked_missing_conversion",
    "no_factor_configured",
    "not_emissions_activity",
    "unsupported_activity_type",
}


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


def _to_decimal(value: Any) -> Decimal | None:
    """Parse a positive finite number via Decimal from its string form."""
    if isinstance(value, bool):
        return None
    if _is_blank(value):
        return None
    try:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not number.is_finite():
        return None
    if number <= 0:
        return None
    return number


def _empty_result_fields() -> dict[str, Any]:
    return {
        "factor_id": pd.NA,
        "factor_value": pd.NA,
        "factor_numerator_unit": pd.NA,
        "factor_denominator_unit": pd.NA,
        "source_reference_id": pd.NA,
        "formula_id": pd.NA,
        "formula_version": pd.NA,
        "calculated_kgco2e": pd.NA,
        "calculated_tco2e": pd.NA,
    }


def _result_row(
    *,
    record_id: str,
    activity_type: str,
    normalized_value: Any,
    normalized_unit: Any,
    calculation_status: str,
    calculation_reason: str,
    factor_id: Any = pd.NA,
    factor_value: Any = pd.NA,
    factor_numerator_unit: Any = pd.NA,
    factor_denominator_unit: Any = pd.NA,
    source_reference_id: Any = pd.NA,
    formula_id: Any = pd.NA,
    formula_version: Any = pd.NA,
    calculated_kgco2e: Any = pd.NA,
    calculated_tco2e: Any = pd.NA,
) -> dict[str, Any]:
    return {
        "calculation_id": f"calc_{record_id}",
        "record_id": record_id,
        "activity_type": activity_type,
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "factor_id": factor_id,
        "factor_value": factor_value,
        "factor_numerator_unit": factor_numerator_unit,
        "factor_denominator_unit": factor_denominator_unit,
        "source_reference_id": source_reference_id,
        "formula_id": formula_id,
        "formula_version": formula_version,
        "calculated_kgco2e": calculated_kgco2e,
        "calculated_tco2e": calculated_tco2e,
        "calculation_status": calculation_status,
        "calculation_reason": calculation_reason,
    }


def _lookup_normalized(
    normalized_records: pd.DataFrame, record_id: str
) -> pd.Series | None:
    if normalized_records.empty or "record_id" not in normalized_records.columns:
        return None
    matches = normalized_records.loc[
        normalized_records["record_id"].astype(str) == record_id
    ]
    if matches.empty:
        return None
    return matches.iloc[0]


def _lookup_factor(
    emission_factors: pd.DataFrame, factor_id: str
) -> pd.Series | None:
    if emission_factors.empty or "factor_id" not in emission_factors.columns:
        return None
    matches = emission_factors.loc[
        emission_factors["factor_id"].astype(str) == factor_id
    ]
    if matches.empty:
        return None
    return matches.iloc[0]


def _ready_candidates(
    candidate_matches: pd.DataFrame, record_id: str
) -> pd.DataFrame:
    if candidate_matches.empty:
        return pd.DataFrame(columns=candidate_matches.columns)
    mask = candidate_matches["record_id"].astype(str) == record_id
    mask &= candidate_matches["match_status"].astype(str) == "matched_ready"
    return candidate_matches.loc[mask].copy()


def _passthrough_reason(readiness_row: pd.Series) -> str:
    status = _text(readiness_row.get("calculation_readiness"))
    dependency = readiness_row.get("blocking_dependency")
    readiness_reason = _text(readiness_row.get("readiness_reason"))

    if status == "blocked_missing_conversion":
        dependency_text = _text(dependency)
        if dependency_text:
            return (
                "Calculation blocked until verified conversion "
                f"{dependency_text} is available."
            )
        return "Calculation blocked by a missing verified conversion."

    if status == "no_factor_configured":
        return (
            readiness_reason
            or "No suitable emission factor is configured for calculation."
        )

    if status == "not_emissions_activity":
        return (
            readiness_reason
            or (
                "Operational or production evidence is not itself an "
                "emissions activity."
            )
        )

    if status == "unsupported_activity_type":
        return (
            readiness_reason
            or "No calculation method exists for this activity type."
        )

    return readiness_reason or f"Calculation not performed ({status})."


def _calculate_ready_row(
    *,
    record_id: str,
    activity_type: str,
    normalized_row: pd.Series | None,
    ready_candidates: pd.DataFrame,
    emission_factors: pd.DataFrame,
) -> dict[str, Any]:
    if normalized_row is None:
        return _result_row(
            record_id=record_id,
            activity_type=activity_type,
            normalized_value=pd.NA,
            normalized_unit=pd.NA,
            calculation_status="invalid_normalized_input",
            calculation_reason=(
                "Normalized activity record is missing for this record_id."
            ),
            **_empty_result_fields(),
        )

    normalized_value_raw = normalized_row.get("normalized_value")
    normalized_unit = _text(normalized_row.get("normalized_unit"))
    normalized_decimal = _to_decimal(normalized_value_raw)

    if normalized_decimal is None or not normalized_unit:
        return _result_row(
            record_id=record_id,
            activity_type=activity_type,
            normalized_value=normalized_value_raw,
            normalized_unit=normalized_unit or pd.NA,
            calculation_status="invalid_normalized_input",
            calculation_reason=(
                "Normalized value/unit must be present, finite, and greater "
                "than zero."
            ),
            **_empty_result_fields(),
        )

    if len(ready_candidates) != 1:
        return _result_row(
            record_id=record_id,
            activity_type=activity_type,
            normalized_value=float(normalized_decimal),
            normalized_unit=normalized_unit,
            calculation_status="factor_match_inconsistent",
            calculation_reason=(
                "Readiness is ready but the number of matched_ready candidates "
                f"is {len(ready_candidates)}, expected exactly 1."
            ),
            **_empty_result_fields(),
        )

    candidate = ready_candidates.iloc[0]
    factor_id = _text(candidate.get("factor_id"))
    factor_row = _lookup_factor(emission_factors, factor_id)
    if factor_row is None:
        return _result_row(
            record_id=record_id,
            activity_type=activity_type,
            normalized_value=float(normalized_decimal),
            normalized_unit=normalized_unit,
            calculation_status="factor_match_inconsistent",
            calculation_reason=(
                f"Candidate factor_id {factor_id!r} was not found in the "
                "emission-factor registry."
            ),
            **_empty_result_fields(),
        )

    gas = _text(factor_row.get("gas"))
    numerator_unit = _text(factor_row.get("numerator_unit"))
    denominator_unit = _text(factor_row.get("denominator_unit"))
    factor_decimal = _to_decimal(factor_row.get("factor_value"))
    source_reference_id = _text(factor_row.get("source_reference_id"))

    if gas != "CO2e" or numerator_unit != "kgCO2e":
        return _result_row(
            record_id=record_id,
            activity_type=activity_type,
            normalized_value=float(normalized_decimal),
            normalized_unit=normalized_unit,
            calculation_status="factor_match_inconsistent",
            calculation_reason=(
                "Ready calculation requires a direct CO2e factor with "
                "numerator unit kgCO2e."
            ),
            **_empty_result_fields(),
        )

    if denominator_unit != normalized_unit:
        return _result_row(
            record_id=record_id,
            activity_type=activity_type,
            normalized_value=float(normalized_decimal),
            normalized_unit=normalized_unit,
            calculation_status="factor_match_inconsistent",
            calculation_reason=(
                f"Factor denominator {denominator_unit!r} does not match "
                f"normalized unit {normalized_unit!r}."
            ),
            **_empty_result_fields(),
        )

    if factor_decimal is None:
        return _result_row(
            record_id=record_id,
            activity_type=activity_type,
            normalized_value=float(normalized_decimal),
            normalized_unit=normalized_unit,
            calculation_status="factor_match_inconsistent",
            calculation_reason=(
                "Factor value must be a finite number greater than zero."
            ),
            **_empty_result_fields(),
        )

    kgco2e = normalized_decimal * factor_decimal
    tco2e = kgco2e / Decimal("1000")

    return _result_row(
        record_id=record_id,
        activity_type=activity_type,
        normalized_value=float(normalized_decimal),
        normalized_unit=normalized_unit,
        factor_id=factor_id,
        factor_value=float(factor_decimal),
        factor_numerator_unit=numerator_unit,
        factor_denominator_unit=denominator_unit,
        source_reference_id=source_reference_id or pd.NA,
        formula_id=FORMULA_ID,
        formula_version=FORMULA_VERSION,
        calculated_kgco2e=float(kgco2e),
        calculated_tco2e=float(tco2e),
        calculation_status="calculated",
        calculation_reason=(
            "Calculated using normalized activity value times a direct "
            "CO2e emission factor."
        ),
    )


def calculate_activity_emissions(
    normalized_records: pd.DataFrame,
    candidate_matches: pd.DataFrame,
    activity_readiness: pd.DataFrame,
    emission_factors: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate emissions only for fully ready and consistent activities.

    Returns one output row for every activity-readiness row. Does not mutate
    inputs and does not invent fallback factors or zeros for blocked records.
    """
    normalized = normalized_records.copy(deep=True)
    candidates = candidate_matches.copy(deep=True)
    readiness = activity_readiness.copy(deep=True)
    factors = emission_factors.copy(deep=True)

    results: list[dict[str, Any]] = []

    for _, readiness_row in readiness.iterrows():
        record_id = _text(readiness_row.get("record_id"))
        activity_type = _text(readiness_row.get("activity_type"))
        readiness_status = _text(readiness_row.get("calculation_readiness"))
        normalized_row = _lookup_normalized(normalized, record_id)

        normalized_value = (
            normalized_row.get("normalized_value")
            if normalized_row is not None
            else pd.NA
        )
        normalized_unit = (
            _text(normalized_row.get("normalized_unit"))
            if normalized_row is not None
            else ""
        )

        if readiness_status in PASSTHROUGH_STATUSES:
            results.append(
                _result_row(
                    record_id=record_id,
                    activity_type=activity_type,
                    normalized_value=normalized_value,
                    normalized_unit=normalized_unit or pd.NA,
                    calculation_status=readiness_status,
                    calculation_reason=_passthrough_reason(readiness_row),
                    **_empty_result_fields(),
                )
            )
            continue

        if readiness_status == "ready":
            ready_candidates = _ready_candidates(candidates, record_id)
            results.append(
                _calculate_ready_row(
                    record_id=record_id,
                    activity_type=activity_type,
                    normalized_row=normalized_row,
                    ready_candidates=ready_candidates,
                    emission_factors=factors,
                )
            )
            continue

        results.append(
            _result_row(
                record_id=record_id,
                activity_type=activity_type,
                normalized_value=normalized_value,
                normalized_unit=normalized_unit or pd.NA,
                calculation_status="factor_match_inconsistent",
                calculation_reason=(
                    f"Unrecognized or inconsistent readiness status "
                    f"{readiness_status!r}."
                ),
                **_empty_result_fields(),
            )
        )

    if not results:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    output = pd.DataFrame(results, columns=OUTPUT_COLUMNS)
    output = output.sort_values("record_id", kind="mergesort").reset_index(
        drop=True
    )
    return output
