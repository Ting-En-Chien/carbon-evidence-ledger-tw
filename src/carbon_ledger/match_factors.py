"""Deterministic emission-factor matching and calculation readiness.

Phase 5B decides which registered factors are candidates for each activity and
whether calculation is ready or blocked. It does not calculate emissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

CANDIDATE_COLUMNS = [
    "record_id",
    "activity_type",
    "factor_id",
    "gas",
    "activity_unit",
    "factor_denominator_unit",
    "match_status",
    "match_reason",
    "required_conversion",
]

READINESS_COLUMNS = [
    "record_id",
    "activity_type",
    "calculation_readiness",
    "candidate_factor_count",
    "blocking_dependency",
    "readiness_reason",
]

NOT_EMISSIONS_ACTIVITY_TYPES = {
    "finished_goods_output",
    "scrap_output",
}

KNOWN_EMISSIONS_ACTIVITY_TYPES = {
    "grid_electricity",
    "natural_gas",
    "diesel",
}

KNOWN_NO_FACTOR_ACTIVITY_TYPES = {
    "purchased_steel",
    "third_party_transport",
}


@dataclass
class FactorMatchingResult:
    """Candidate factor matches and per-activity calculation readiness."""

    candidate_matches: pd.DataFrame
    activity_readiness: pd.DataFrame


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


def _parse_optional_timestamp(value: Any) -> pd.Timestamp | None:
    if _is_blank(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def _activity_unit(row: pd.Series) -> str:
    """Prefer normalized_unit when present; otherwise use original unit."""
    if "normalized_unit" in row.index and not _is_blank(row.get("normalized_unit")):
        return _text(row.get("normalized_unit"))
    return _text(row.get("unit"))


def _factor_covers_activity_period(
    factor_row: pd.Series,
    activity_start: Any,
    activity_end: Any,
) -> bool:
    """Return False when the activity period is clearly outside factor validity."""
    valid_from = _parse_optional_timestamp(factor_row.get("valid_from"))
    valid_to = _parse_optional_timestamp(factor_row.get("valid_to"))
    start = _parse_optional_timestamp(activity_start)
    end = _parse_optional_timestamp(activity_end)

    if start is None or end is None:
        return True

    if valid_from is not None and end < valid_from:
        return False
    if valid_to is not None and start > valid_to:
        return False
    return True


def _active_factors(
    emission_factors: pd.DataFrame,
    *,
    activity_type: str,
    combustion_context: str | None = None,
) -> pd.DataFrame:
    if emission_factors.empty:
        return emission_factors.copy()

    frame = emission_factors.copy()
    mask = frame["activity_type"].astype(str).str.strip() == activity_type
    mask &= frame["factor_status"].astype(str).str.strip() != "inactive"
    if combustion_context is not None:
        mask &= (
            frame["combustion_context"].astype(str).str.strip()
            == combustion_context
        )
    return frame.loc[mask].copy()


def _candidate_row(
    *,
    record_id: str,
    activity_type: str,
    factor_row: pd.Series,
    activity_unit: str,
    match_status: str,
    match_reason: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "activity_type": activity_type,
        "factor_id": _text(factor_row.get("factor_id")),
        "gas": _text(factor_row.get("gas")),
        "activity_unit": activity_unit,
        "factor_denominator_unit": _text(factor_row.get("denominator_unit")),
        "match_status": match_status,
        "match_reason": match_reason,
        "required_conversion": _text(factor_row.get("required_conversion")),
    }


def _match_grid_electricity(
    *,
    record_id: str,
    activity_type: str,
    activity_unit: str,
    activity_start: Any,
    activity_end: Any,
    emission_factors: pd.DataFrame,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    factors = _active_factors(
        emission_factors, activity_type="grid_electricity"
    )
    for _, factor in factors.iterrows():
        if not _factor_covers_activity_period(
            factor, activity_start, activity_end
        ):
            continue
        status = _text(factor.get("factor_status"))
        denominator = _text(factor.get("denominator_unit"))
        required_conversion = _text(factor.get("required_conversion"))
        if (
            status == "ready"
            and denominator == activity_unit
            and required_conversion == "not_required"
        ):
            candidates.append(
                _candidate_row(
                    record_id=record_id,
                    activity_type=activity_type,
                    factor_row=factor,
                    activity_unit=activity_unit,
                    match_status="matched_ready",
                    match_reason=(
                        "Ready electricity factor with compatible "
                        f"denominator unit {denominator!r}."
                    ),
                )
            )
    return candidates


def _match_natural_gas(
    *,
    record_id: str,
    activity_type: str,
    activity_unit: str,
    activity_start: Any,
    activity_end: Any,
    emission_factors: pd.DataFrame,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    factors = _active_factors(
        emission_factors,
        activity_type="natural_gas",
        combustion_context="stationary_combustion",
    )
    for _, factor in factors.iterrows():
        if not _factor_covers_activity_period(
            factor, activity_start, activity_end
        ):
            continue
        status = _text(factor.get("factor_status"))
        if status != "registered_missing_conversion":
            continue
        required_conversion = _text(factor.get("required_conversion"))
        candidates.append(
            _candidate_row(
                record_id=record_id,
                activity_type=activity_type,
                factor_row=factor,
                activity_unit=activity_unit,
                match_status="matched_blocked_dependency",
                match_reason=(
                    f"Natural-gas activity unit {activity_unit!r} cannot use "
                    f"factor denominator "
                    f"{_text(factor.get('denominator_unit'))!r} until "
                    f"{required_conversion} is verified."
                ),
            )
        )
    return candidates


def _match_diesel(
    *,
    record_id: str,
    activity_type: str,
    activity_unit: str,
    process_use: str,
    activity_start: Any,
    activity_end: Any,
    emission_factors: pd.DataFrame,
) -> list[dict[str, Any]]:
    if process_use != "company_vehicle":
        return []

    candidates: list[dict[str, Any]] = []
    factors = _active_factors(
        emission_factors,
        activity_type="diesel",
        combustion_context="mobile_combustion",
    )
    for _, factor in factors.iterrows():
        if not _factor_covers_activity_period(
            factor, activity_start, activity_end
        ):
            continue
        status = _text(factor.get("factor_status"))
        if status != "registered_missing_conversion":
            continue
        required_conversion = _text(factor.get("required_conversion"))
        candidates.append(
            _candidate_row(
                record_id=record_id,
                activity_type=activity_type,
                factor_row=factor,
                activity_unit=activity_unit,
                match_status="matched_blocked_dependency",
                match_reason=(
                    "Company-vehicle diesel activity unit "
                    f"{activity_unit!r} cannot use factor denominator "
                    f"{_text(factor.get('denominator_unit'))!r} until "
                    f"{required_conversion} is verified."
                ),
            )
        )
    return candidates


def _build_readiness_row(
    *,
    record_id: str,
    activity_type: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    count = len(candidates)

    if activity_type in NOT_EMISSIONS_ACTIVITY_TYPES:
        return {
            "record_id": record_id,
            "activity_type": activity_type,
            "calculation_readiness": "not_emissions_activity",
            "candidate_factor_count": 0,
            "blocking_dependency": pd.NA,
            "readiness_reason": (
                "Production or scrap output is operational evidence, "
                "not an emissions activity."
            ),
        }

    if activity_type in KNOWN_NO_FACTOR_ACTIVITY_TYPES:
        return {
            "record_id": record_id,
            "activity_type": activity_type,
            "calculation_readiness": "no_factor_configured",
            "candidate_factor_count": 0,
            "blocking_dependency": pd.NA,
            "readiness_reason": (
                f"No suitable emission factor is configured yet for "
                f"{activity_type!r} in the current MVP."
            ),
        }

    if activity_type not in KNOWN_EMISSIONS_ACTIVITY_TYPES:
        return {
            "record_id": record_id,
            "activity_type": activity_type,
            "calculation_readiness": "unsupported_activity_type",
            "candidate_factor_count": 0,
            "blocking_dependency": pd.NA,
            "readiness_reason": (
                f"Activity type {activity_type!r} is unsupported for "
                "factor matching in Phase 5B."
            ),
        }

    if count == 0:
        return {
            "record_id": record_id,
            "activity_type": activity_type,
            "calculation_readiness": "no_factor_configured",
            "candidate_factor_count": 0,
            "blocking_dependency": pd.NA,
            "readiness_reason": (
                f"No eligible emission-factor candidates were found for "
                f"{activity_type!r}."
            ),
        }

    statuses = {item["match_status"] for item in candidates}
    if statuses == {"matched_ready"}:
        return {
            "record_id": record_id,
            "activity_type": activity_type,
            "calculation_readiness": "ready",
            "candidate_factor_count": count,
            "blocking_dependency": pd.NA,
            "readiness_reason": (
                "Eligible ready factor candidate(s) found with compatible units."
            ),
        }

    if "matched_blocked_dependency" in statuses:
        blocked = [
            item
            for item in candidates
            if item["match_status"] == "matched_blocked_dependency"
        ]
        dependency = blocked[0]["required_conversion"]
        return {
            "record_id": record_id,
            "activity_type": activity_type,
            "calculation_readiness": "blocked_missing_conversion",
            "candidate_factor_count": count,
            "blocking_dependency": dependency,
            "readiness_reason": (
                "Factor candidates exist but calculation is blocked until "
                f"{dependency} is verified."
            ),
        }

    return {
        "record_id": record_id,
        "activity_type": activity_type,
        "calculation_readiness": "no_factor_configured",
        "candidate_factor_count": count,
        "blocking_dependency": pd.NA,
        "readiness_reason": (
            "Factor candidates were found but none are ready for calculation."
        ),
    }


def match_activity_factors(
    activity_records: pd.DataFrame,
    emission_factors: pd.DataFrame,
    calculation_dependencies: pd.DataFrame,
) -> FactorMatchingResult:
    """Match registered emission factors to activities without calculating.

    ``calculation_dependencies`` is accepted for future dependency checks and
    pipeline consistency. Blocking dependency names currently come from the
    matched factors' ``required_conversion`` values.
    """
    activities = activity_records.copy(deep=True)
    factors = emission_factors.copy(deep=True)
    _ = calculation_dependencies.copy(deep=True)

    all_candidates: list[dict[str, Any]] = []
    readiness_rows: list[dict[str, Any]] = []

    for _, activity in activities.iterrows():
        record_id = _text(activity.get("record_id"))
        activity_type = _text(activity.get("activity_type"))
        activity_unit = _activity_unit(activity)
        process_use = _text(activity.get("process_use"))
        start = activity.get("activity_start_date")
        end = activity.get("activity_end_date")

        candidates: list[dict[str, Any]] = []
        if activity_type == "grid_electricity":
            candidates = _match_grid_electricity(
                record_id=record_id,
                activity_type=activity_type,
                activity_unit=activity_unit,
                activity_start=start,
                activity_end=end,
                emission_factors=factors,
            )
        elif activity_type == "natural_gas":
            candidates = _match_natural_gas(
                record_id=record_id,
                activity_type=activity_type,
                activity_unit=activity_unit,
                activity_start=start,
                activity_end=end,
                emission_factors=factors,
            )
        elif activity_type == "diesel":
            candidates = _match_diesel(
                record_id=record_id,
                activity_type=activity_type,
                activity_unit=activity_unit,
                process_use=process_use,
                activity_start=start,
                activity_end=end,
                emission_factors=factors,
            )

        all_candidates.extend(candidates)
        readiness_rows.append(
            _build_readiness_row(
                record_id=record_id,
                activity_type=activity_type,
                candidates=candidates,
            )
        )

    if all_candidates:
        candidate_matches = pd.DataFrame(
            all_candidates, columns=CANDIDATE_COLUMNS
        )
        candidate_matches = candidate_matches.sort_values(
            ["record_id", "factor_id", "gas"],
            kind="mergesort",
        ).reset_index(drop=True)
    else:
        candidate_matches = pd.DataFrame(columns=CANDIDATE_COLUMNS)

    if readiness_rows:
        activity_readiness = pd.DataFrame(
            readiness_rows, columns=READINESS_COLUMNS
        )
    else:
        activity_readiness = pd.DataFrame(columns=READINESS_COLUMNS)

    return FactorMatchingResult(
        candidate_matches=candidate_matches,
        activity_readiness=activity_readiness,
    )
