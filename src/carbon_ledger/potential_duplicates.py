"""Potential-duplicate detection for uploaded company activity rows.

Looks at business-significant fields after mapping/normalization. Does not
delete rows. Distinct generated record IDs are expected and ignored.
True duplicate-ID ingest failures remain in ingest.py.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

ISSUE_POTENTIAL_DUPLICATE = "POTENTIAL_DUPLICATE"
DECISION_KEEP_ALL = "keep_all"
DECISION_EXCLUDE_DUPLICATES = "exclude_duplicates"
DECISION_UNRESOLVED = "unresolved"

DUPLICATE_KEY_FIELDS = (
    "activity_type",
    "activity_value",
    "unit",
    "activity_start_date",
    "activity_end_date",
    "site_id",
    "fuel_subtype",
    "process_use",
)

REVIEW_LOG_COLUMNS = (
    "record_id",
    "group_id",
    "source_row",
    "decision",
    "excluded_from_calculation",
    "reviewed_at",
    "review_session",
)

_ROW_LOCATOR_RE = re.compile(r"row:(\d+)", re.IGNORECASE)


class PotentialDuplicateReviewRequired(ValueError):
    """Final analysis is blocked until lookalike rows are reviewed."""


@dataclass(frozen=True)
class PotentialDuplicateGroup:
    """One set of uploaded rows that look like the same business activity."""

    group_id: str
    fingerprint: str
    record_ids: tuple[str, ...]
    source_rows: tuple[int, ...]
    activity_type: str
    activity_value: float
    unit: str
    activity_start_date: str
    activity_end_date: str
    site_id: str
    fuel_subtype: str
    process_use: str


@dataclass(frozen=True)
class DuplicateReviewDecision:
    """Customer review of one potential-duplicate group."""

    group_id: str
    decision: str
    included_record_ids: tuple[str, ...]
    excluded_record_ids: tuple[str, ...]
    reviewed_at: str
    review_session: str = ""


def source_row_from_locator(locator: Any) -> int:
    """Parse the Excel-style source row from a provenance locator."""
    match = _ROW_LOCATOR_RE.search(str(locator or ""))
    if match is None:
        return 0
    return int(match.group(1))


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "<na>", "none", "nat"}


def _normalize_key_value(field: str, value: Any) -> str:
    if field == "activity_value":
        if _blank(value):
            return ""
        return f"{round(float(value), 10):.10f}"
    if field in {"activity_start_date", "activity_end_date"}:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return ""
        return pd.Timestamp(parsed).strftime("%Y-%m-%d")
    if _blank(value):
        return ""
    return str(value).strip()


def activity_duplicate_fingerprint(row: Mapping[str, Any] | pd.Series) -> str:
    """Stable business-content key. Never includes record_id."""
    parts = [
        f"{field}={_normalize_key_value(field, row.get(field))}"
        for field in DUPLICATE_KEY_FIELDS
    ]
    return "|".join(parts)


def _group_id_for(fingerprint: str, file_hash: str) -> str:
    payload = f"{str(file_hash or '').strip()}|{fingerprint}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def find_potential_duplicate_groups(
    accepted: pd.DataFrame | None,
    *,
    file_hash: str = "",
) -> list[PotentialDuplicateGroup]:
    """Group lookalike accepted rows. Never drops a row."""
    if accepted is None or getattr(accepted, "empty", True):
        return []
    if "record_id" not in accepted.columns:
        return []
    missing = [name for name in DUPLICATE_KEY_FIELDS if name not in accepted.columns]
    if missing:
        return []

    buckets: dict[str, list[int]] = {}
    fingerprints: dict[str, str] = {}
    for index, row in accepted.iterrows():
        fingerprint = activity_duplicate_fingerprint(row)
        group_id = _group_id_for(fingerprint, file_hash)
        buckets.setdefault(group_id, []).append(int(index))
        fingerprints[group_id] = fingerprint

    groups: list[PotentialDuplicateGroup] = []
    for group_id, positions in buckets.items():
        if len(positions) < 2:
            continue
        subset = accepted.loc[positions].copy()
        locators = (
            subset["source_locator"]
            if "source_locator" in subset.columns
            else pd.Series([""] * len(subset), index=subset.index)
        )
        source_rows = [
            source_row_from_locator(value) for value in locators.tolist()
        ]
        order = sorted(
            range(len(positions)),
            key=lambda i: (source_rows[i], str(subset.iloc[i]["record_id"])),
        )
        first = subset.iloc[order[0]]
        groups.append(
            PotentialDuplicateGroup(
                group_id=group_id,
                fingerprint=fingerprints[group_id],
                record_ids=tuple(str(subset.iloc[i]["record_id"]) for i in order),
                source_rows=tuple(source_rows[i] for i in order),
                activity_type=_normalize_key_value(
                    "activity_type", first.get("activity_type")
                ),
                activity_value=float(first.get("activity_value") or 0.0),
                unit=_normalize_key_value("unit", first.get("unit")),
                activity_start_date=_normalize_key_value(
                    "activity_start_date", first.get("activity_start_date")
                ),
                activity_end_date=_normalize_key_value(
                    "activity_end_date", first.get("activity_end_date")
                ),
                site_id=_normalize_key_value("site_id", first.get("site_id")),
                fuel_subtype=_normalize_key_value(
                    "fuel_subtype", first.get("fuel_subtype")
                ),
                process_use=_normalize_key_value(
                    "process_use", first.get("process_use")
                ),
            )
        )
    groups.sort(key=lambda item: (item.source_rows[0], item.group_id))
    return groups


def groups_from_intake(intake: Any) -> tuple[PotentialDuplicateGroup, ...]:
    """Return stored groups, or detect them from accepted activities."""
    stored = getattr(intake, "potential_duplicate_groups", None)
    if stored:
        return tuple(stored)
    accepted = getattr(intake, "accepted_activities", None)
    file_hash = str(getattr(intake, "file_hash", "") or "")
    return tuple(find_potential_duplicate_groups(accepted, file_hash=file_hash))


def decide_potential_duplicate_group(
    group: PotentialDuplicateGroup,
    decision: str,
    *,
    reviewed_at: str,
    review_session: str = "",
) -> DuplicateReviewDecision:
    """Apply a keep-all or exclude-duplicates decision. Never auto-drops."""
    if decision not in {DECISION_KEEP_ALL, DECISION_EXCLUDE_DUPLICATES}:
        raise ValueError(f"Unsupported duplicate review decision: {decision}")
    ids = list(group.record_ids)
    if decision == DECISION_KEEP_ALL:
        included: tuple[str, ...] = tuple(ids)
        excluded: tuple[str, ...] = ()
    else:
        included = (ids[0],)
        excluded = tuple(ids[1:])
    return DuplicateReviewDecision(
        group_id=group.group_id,
        decision=decision,
        included_record_ids=included,
        excluded_record_ids=excluded,
        reviewed_at=str(reviewed_at or ""),
        review_session=str(review_session or ""),
    )


def decision_to_map_payload(decision: DuplicateReviewDecision) -> dict[str, Any]:
    return {
        "group_id": decision.group_id,
        "decision": decision.decision,
        "included_record_ids": list(decision.included_record_ids),
        "excluded_record_ids": list(decision.excluded_record_ids),
        "reviewed_at": decision.reviewed_at,
        "review_session": decision.review_session,
    }


def load_review_decisions(raw: Any) -> list[DuplicateReviewDecision]:
    """Deserialize session-stored review decisions."""
    if not raw:
        return []
    if isinstance(raw, Mapping):
        items = raw.values()
    else:
        items = raw
    decisions: list[DuplicateReviewDecision] = []
    for item in items:
        if isinstance(item, DuplicateReviewDecision):
            decisions.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        decision = str(item.get("decision") or "").strip()
        if decision not in {DECISION_KEEP_ALL, DECISION_EXCLUDE_DUPLICATES}:
            continue
        included = tuple(
            str(value) for value in (item.get("included_record_ids") or ())
        )
        excluded = tuple(
            str(value) for value in (item.get("excluded_record_ids") or ())
        )
        decisions.append(
            DuplicateReviewDecision(
                group_id=str(item.get("group_id") or ""),
                decision=decision,
                included_record_ids=included,
                excluded_record_ids=excluded,
                reviewed_at=str(item.get("reviewed_at") or ""),
                review_session=str(item.get("review_session") or ""),
            )
        )
    return decisions


def effective_review_decisions(
    groups: Iterable[PotentialDuplicateGroup],
    stored: Iterable[DuplicateReviewDecision],
) -> list[DuplicateReviewDecision]:
    """Keep decisions only when they still match current group membership."""
    by_id = {group.group_id: group for group in groups}
    effective: list[DuplicateReviewDecision] = []
    for decision in stored:
        group = by_id.get(decision.group_id)
        if group is None:
            continue
        expected = set(group.record_ids)
        got = set(decision.included_record_ids) | set(
            decision.excluded_record_ids
        )
        if got != expected:
            continue
        if decision.decision == DECISION_EXCLUDE_DUPLICATES:
            if not decision.included_record_ids:
                continue
            if set(decision.excluded_record_ids) & set(
                decision.included_record_ids
            ):
                continue
        effective.append(decision)
    return effective


def unresolved_potential_duplicate_groups(
    groups: Iterable[PotentialDuplicateGroup],
    decisions: Iterable[DuplicateReviewDecision],
) -> list[PotentialDuplicateGroup]:
    resolved = {
        item.group_id
        for item in effective_review_decisions(groups, decisions)
        if item.decision in {DECISION_KEEP_ALL, DECISION_EXCLUDE_DUPLICATES}
    }
    return [group for group in groups if group.group_id not in resolved]


def analysis_blocked_for_potential_duplicates(
    groups: Iterable[PotentialDuplicateGroup],
    decisions: Iterable[DuplicateReviewDecision],
) -> bool:
    """Unresolved lookalikes must not enter a finalized customer result."""
    return bool(unresolved_potential_duplicate_groups(groups, decisions))


def excluded_record_ids(
    groups: Iterable[PotentialDuplicateGroup],
    decisions: Iterable[DuplicateReviewDecision],
) -> set[str]:
    blocked = analysis_blocked_for_potential_duplicates(groups, decisions)
    if blocked:
        return set()
    excluded: set[str] = set()
    for decision in effective_review_decisions(groups, decisions):
        excluded.update(decision.excluded_record_ids)
    return excluded


def activities_included_for_calculation(
    accepted: pd.DataFrame,
    groups: Iterable[PotentialDuplicateGroup],
    decisions: Iterable[DuplicateReviewDecision],
) -> pd.DataFrame:
    """Return confirmed included rows. Raises if review is still required."""
    group_list = list(groups)
    if analysis_blocked_for_potential_duplicates(group_list, decisions):
        raise PotentialDuplicateReviewRequired(
            "Potential duplicate activities need confirmation before analysis."
        )
    if accepted is None or getattr(accepted, "empty", True):
        return accepted
    excluded = excluded_record_ids(group_list, decisions)
    if not excluded:
        return accepted.copy()
    mask = ~accepted["record_id"].astype(str).isin(excluded)
    return accepted.loc[mask].copy()


def build_duplicate_review_log(
    accepted: pd.DataFrame | None,
    groups: Iterable[PotentialDuplicateGroup],
    decisions: Iterable[DuplicateReviewDecision],
) -> pd.DataFrame:
    """Audit rows for lookalike groups. Original imported rows stay intact."""
    rows: list[dict[str, Any]] = []
    decision_by_group = {
        item.group_id: item
        for item in effective_review_decisions(groups, decisions)
    }
    accepted_by_id: dict[str, pd.Series] = {}
    if accepted is not None and not getattr(accepted, "empty", True):
        for _, row in accepted.iterrows():
            accepted_by_id[str(row.get("record_id") or "")] = row
    for group in groups:
        decision = decision_by_group.get(group.group_id)
        excluded = set(decision.excluded_record_ids) if decision else set()
        decision_code = decision.decision if decision else DECISION_UNRESOLVED
        reviewed_at = decision.reviewed_at if decision else ""
        review_session = decision.review_session if decision else ""
        for record_id, source_row in zip(
            group.record_ids, group.source_rows, strict=True
        ):
            original = accepted_by_id.get(record_id)
            rows.append(
                {
                    "record_id": record_id,
                    "group_id": group.group_id,
                    "source_row": int(source_row),
                    "decision": decision_code,
                    "excluded_from_calculation": bool(record_id in excluded),
                    "reviewed_at": reviewed_at,
                    "review_session": review_session,
                    "original_present": original is not None,
                }
            )
    if not rows:
        return pd.DataFrame(columns=list(REVIEW_LOG_COLUMNS) + ["original_present"])
    return pd.DataFrame(rows)
