"""Row-level organizational-boundary decisions for refrigerant refill.

These records are overrides, not replacements of uploaded source rows.
Effective ownership/boundary values are derived conservatively and then
re-evaluated by the existing GHG Protocol mapper. Emissions values are
never recalculated from a decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

from carbon_ledger.inventory_boundary import utc_now_iso

SCHEMA_VERSION = "activity-boundary-decision-v1"

LEGAL_OWNERS = frozenset({"company", "third_party", "unknown"})
OPERATIONAL_CONTROLLERS = frozenset(
    {"company", "third_party", "shared", "unknown"}
)
BOUNDARY_STATUSES = frozenset({"inside", "outside", "unknown"})
BOUNDARY_BASES = frozenset(
    {
        "taiwan_statutory_facility",
        "operational_control",
        "financial_control",
        "equity_share",
        "unknown",
    }
)

OUTCOME_INCLUDED_SCOPE_1 = "included_scope_1"
OUTCOME_EXCLUDED_OUTSIDE = "excluded_outside"
OUTCOME_NEEDS_REVIEW = "still_needs_review"

ERROR_EVIDENCE_REQUIRED = "evidence_reference_required"
ERROR_INCOMPLETE_FIELDS = "incomplete_fields"
ERROR_PERIOD_MISMATCH = "reporting_period_mismatch"


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def coerce_reporting_year(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        year = int(text)
    except (TypeError, ValueError):
        return None
    if 1990 <= year <= 2100:
        return year
    return None


def reporting_year_from_activity(activity: Mapping[str, Any] | pd.Series) -> int | None:
    """Prefer an explicit year; otherwise require a single calendar year."""
    explicit = coerce_reporting_year(activity.get("reporting_year"))
    if explicit is not None:
        return explicit
    start = pd.to_datetime(activity.get("activity_start_date"), errors="coerce")
    end = pd.to_datetime(activity.get("activity_end_date"), errors="coerce")
    if pd.isna(start) or pd.isna(end):
        return None
    if int(start.year) != int(end.year):
        return None
    return int(start.year)


def period_id_for_decision(*, reporting_period_id: str, reporting_year: int) -> str:
    """Workspace period-directory name. Not the in-memory decision identity."""
    period = _text(reporting_period_id)
    if period:
        return period
    return f"period-{int(reporting_year)}"


def decision_identity(
    record_id: str,
    reporting_year: int,
    reporting_period_id: str = "",
) -> tuple[str, int, str]:
    """Identity for save, replace, withdraw, and existing-form lookup."""
    return (_text(record_id), int(reporting_year), _text(reporting_period_id))


@dataclass(frozen=True)
class ActivityBoundaryDecision:
    """One confirmed boundary judgment for one record in one reporting period."""

    record_id: str
    reporting_year: int
    reporting_period_id: str
    legal_owner: str
    operational_controller: str
    organizational_boundary_status: str
    boundary_basis: str
    evidence_reference: str
    rationale: str
    confirmed_by: str
    confirmed_at: str
    schema_version: str = SCHEMA_VERSION
    withdrawn: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reporting_year"] = int(self.reporting_year)
        payload["withdrawn"] = bool(self.withdrawn)
        return payload

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ActivityBoundaryDecision:
        year = coerce_reporting_year(raw.get("reporting_year"))
        if year is None:
            raise ValueError("reporting_year is required")
        record_id = _text(raw.get("record_id"))
        if not record_id:
            raise ValueError("record_id is required")
        return cls(
            record_id=record_id,
            reporting_year=year,
            reporting_period_id=_text(raw.get("reporting_period_id")),
            legal_owner=_text(raw.get("legal_owner")) or "unknown",
            operational_controller=_text(raw.get("operational_controller"))
            or "unknown",
            organizational_boundary_status=_text(
                raw.get("organizational_boundary_status")
            )
            or "unknown",
            boundary_basis=_text(raw.get("boundary_basis")) or "unknown",
            evidence_reference=_text(raw.get("evidence_reference")),
            rationale=_text(raw.get("rationale")),
            confirmed_by=_text(raw.get("confirmed_by")),
            confirmed_at=_text(raw.get("confirmed_at")) or utc_now_iso(),
            schema_version=_text(raw.get("schema_version")) or SCHEMA_VERSION,
            withdrawn=bool(raw.get("withdrawn")),
        )


def validate_confirmation_input(
    *,
    record_id: str,
    reporting_year: int | None,
    legal_owner: str,
    operational_controller: str,
    organizational_boundary_status: str,
    boundary_basis: str,
    evidence_reference: str,
) -> list[str]:
    """Return machine codes for incomplete confirmation. Evidence is mandatory."""
    errors: list[str] = []
    if not _text(record_id) or reporting_year is None:
        errors.append(ERROR_INCOMPLETE_FIELDS)
    if _text(legal_owner) not in LEGAL_OWNERS:
        errors.append(ERROR_INCOMPLETE_FIELDS)
    if _text(operational_controller) not in OPERATIONAL_CONTROLLERS:
        errors.append(ERROR_INCOMPLETE_FIELDS)
    if _text(organizational_boundary_status) not in BOUNDARY_STATUSES:
        errors.append(ERROR_INCOMPLETE_FIELDS)
    if _text(boundary_basis) not in BOUNDARY_BASES:
        errors.append(ERROR_INCOMPLETE_FIELDS)
    if not _text(evidence_reference):
        errors.append(ERROR_EVIDENCE_REQUIRED)
    return list(dict.fromkeys(errors))


def build_decision(
    *,
    record_id: str,
    reporting_year: int,
    reporting_period_id: str = "",
    legal_owner: str,
    operational_controller: str,
    organizational_boundary_status: str,
    boundary_basis: str,
    evidence_reference: str,
    rationale: str = "",
    confirmed_by: str = "",
    confirmed_at: str = "",
    withdrawn: bool = False,
) -> ActivityBoundaryDecision:
    errors = validate_confirmation_input(
        record_id=record_id,
        reporting_year=reporting_year,
        legal_owner=legal_owner,
        operational_controller=operational_controller,
        organizational_boundary_status=organizational_boundary_status,
        boundary_basis=boundary_basis,
        evidence_reference=evidence_reference,
    )
    if errors and not withdrawn:
        raise ValueError(",".join(errors))
    return ActivityBoundaryDecision(
        record_id=_text(record_id),
        reporting_year=int(reporting_year),
        reporting_period_id=_text(reporting_period_id),
        legal_owner=_text(legal_owner),
        operational_controller=_text(operational_controller),
        organizational_boundary_status=_text(organizational_boundary_status),
        boundary_basis=_text(boundary_basis),
        evidence_reference=_text(evidence_reference),
        rationale=_text(rationale),
        confirmed_by=_text(confirmed_by),
        confirmed_at=_text(confirmed_at) or utc_now_iso(),
        withdrawn=bool(withdrawn),
    )


def derive_effective_ownership_and_boundary(
    decision: ActivityBoundaryDecision,
) -> tuple[str | None, str] | None:
    """Return (ownership_control, organizational_boundary_status) or None.

    None means the existing GHG mapper should keep the raw row (needs_review).
    Ownership None means keep the uploaded ownership_control value.
    Callers never choose Scope directly.
    """
    if decision.withdrawn:
        return None
    if not _text(decision.evidence_reference):
        return None
    boundary = decision.organizational_boundary_status
    if boundary == "outside":
        return (None, "outside")
    if boundary != "inside":
        return None
    if (
        decision.boundary_basis == "operational_control"
        and decision.operational_controller == "company"
    ):
        return ("controlled", "inside")
    if decision.legal_owner == "company":
        return ("owned", "inside")
    return None


def _unanimous_reporting_period_id(activities: pd.DataFrame) -> str:
    if activities.empty or "reporting_period_id" not in activities.columns:
        return ""
    values = {
        _text(value)
        for value in activities["reporting_period_id"].tolist()
        if _text(value)
    }
    if len(values) != 1:
        return ""
    return next(iter(values))


def _activity_reporting_period_id(
    activity: Mapping[str, Any] | pd.Series,
    *,
    analysis_reporting_period_id: str = "",
) -> str:
    activity_period = _text(activity.get("reporting_period_id"))
    if activity_period:
        return activity_period
    return _text(analysis_reporting_period_id)


def decision_matches_activity(
    decision: ActivityBoundaryDecision,
    activity: Mapping[str, Any] | pd.Series,
    *,
    analysis_reporting_period_id: str = "",
) -> bool:
    if decision.withdrawn:
        return False
    if _text(activity.get("record_id")) != decision.record_id:
        return False
    year = reporting_year_from_activity(activity)
    if year != decision.reporting_year:
        return False
    activity_period = _activity_reporting_period_id(
        activity,
        analysis_reporting_period_id=analysis_reporting_period_id,
    )
    decision_period = _text(decision.reporting_period_id)
    if decision_period and activity_period:
        return decision_period == activity_period
    if decision_period or activity_period:
        # Fail closed: a period-qualified decision must not apply to an
        # activity that still has no period after analysis context is filled.
        return False
    # Legacy fallback: both sides omit reporting_period_id, so identity is
    # record_id + reporting_year only. Never use this when either side has a
    # period id, or same-year reporting periods would leak across each other.
    return True


def latest_decisions(
    decisions: Iterable[ActivityBoundaryDecision],
) -> list[ActivityBoundaryDecision]:
    """Keep the newest decision per record_id + reporting_year + period."""
    ranked: dict[tuple[str, int, str], ActivityBoundaryDecision] = {}
    for decision in decisions:
        key = decision_identity(
            decision.record_id,
            decision.reporting_year,
            decision.reporting_period_id,
        )
        previous = ranked.get(key)
        if previous is None or decision.confirmed_at >= previous.confirmed_at:
            ranked[key] = decision
    return list(ranked.values())


def load_decisions(raw: Any) -> list[ActivityBoundaryDecision]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, Mapping):
        nested = raw.get("decisions")
        if isinstance(nested, Mapping):
            items = list(nested.values())
        elif isinstance(nested, list):
            items = nested
        else:
            items = [raw]
    else:
        return []
    loaded: list[ActivityBoundaryDecision] = []
    for item in items:
        if isinstance(item, ActivityBoundaryDecision):
            loaded.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        try:
            loaded.append(ActivityBoundaryDecision.from_dict(item))
        except (TypeError, ValueError):
            continue
    return latest_decisions(loaded)


def decisions_to_payload(
    decisions: Iterable[ActivityBoundaryDecision],
    *,
    reporting_period_id: str = "",
) -> dict[str, Any]:
    current = latest_decisions(decisions)
    return {
        "schema_version": SCHEMA_VERSION,
        "reporting_period_id": _text(reporting_period_id),
        "decisions": {
            f"{item.record_id}:{item.reporting_year}:{item.reporting_period_id}": (
                item.to_dict()
            )
            for item in current
        },
    }


def apply_activity_boundary_decisions(
    activities: pd.DataFrame,
    decisions: Iterable[ActivityBoundaryDecision],
    *,
    analysis_reporting_period_id: str = "",
) -> pd.DataFrame:
    """Return a copy with effective ownership/boundary. Raw rows are not mutated."""
    frame = activities.copy(deep=True)
    if frame.empty:
        return frame
    current = [
        item for item in latest_decisions(decisions) if not item.withdrawn
    ]
    if not current:
        return frame
    period_context = _text(analysis_reporting_period_id) or (
        _unanimous_reporting_period_id(frame)
    )
    ownership_col = "ownership_control"
    boundary_col = "organizational_boundary_status"
    if ownership_col not in frame.columns:
        frame[ownership_col] = "unknown"
    if boundary_col not in frame.columns:
        frame[boundary_col] = "unknown"
    for index, row in frame.iterrows():
        matched = next(
            (
                item
                for item in current
                if decision_matches_activity(
                    item,
                    row,
                    analysis_reporting_period_id=period_context,
                )
            ),
            None,
        )
        if matched is None:
            continue
        effective = derive_effective_ownership_and_boundary(matched)
        if effective is None:
            continue
        ownership, boundary = effective
        if ownership is not None:
            frame.at[index, ownership_col] = ownership
        frame.at[index, boundary_col] = boundary
    return frame
