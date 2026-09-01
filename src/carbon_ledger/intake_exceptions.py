"""Stage 4.2F-C1 — exception-only intake decisions.

Presentation-independent. High-confidence matches may be adopted
automatically. Medium/Low and required context stay unresolved until an
explicit apply. True zero is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from carbon_ledger.domain import ACTIVITY_TYPES, SUPPORTED_UNITS
from carbon_ledger.intake import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    REJECTION_COLUMNS,
    ColumnMapping,
    FieldSuggestion,
    IntakeValidationResult,
    context_confirmations_needed,
    default_value_maps,
    distinct_values,
    extract_diesel_vehicle_context_from_text,
    extract_natural_gas_subtype_from_text,
    fuel_subtype_source_column,
    ng_group_key_for_site,
    suggest_activity_type,
    suggest_unit,
)

REQUIRED_FIELDS = ("activity_type", "activity_value", "unit")
OPTIONAL_FIELDS = (
    "site_id",
    "fuel_subtype",
    "refrigerant_code",
    "refill_confirmed",
    "ownership_control",
    "organizational_boundary_status",
)
DATE_FIELDS = ("activity_start_date", "activity_end_date", "year_month")
COLUMN_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS + DATE_FIELDS

KIND_COLUMN = "column"
KIND_DATES = "dates"
KIND_YEAR_MONTH = "year_month"
KIND_CONTEXT = "context"
KIND_ACTIVITY_VALUE = "activity_value"
KIND_UNIT_VALUE = "unit_value"

ISSUE_HELD_NG_CONTEXT = "HELD_NG_CONTEXT"
ISSUE_HELD_DIESEL_CONTEXT = "HELD_DIESEL_CONTEXT"
ISSUE_HELD_ELEC_CONTEXT = "HELD_ELEC_CONTEXT"
ISSUE_HELD_PENDING_ACTUAL_HV = "HELD_PENDING_ACTUAL_HV"

CONTEXT_NG = "natural_gas"
CONTEXT_DIESEL = "diesel"
CONTEXT_ELECTRICITY = "electricity"
NG_VALUE_PENDING_HV = "pending_actual_hv"
NG_GROUP_SINGLE = "__single_source__"
NG_ANSWERED_VALUES = frozenset({"NG1", "NG2", "unknown", NG_VALUE_PENDING_HV})


@dataclass(frozen=True)
class IntakeException:
    """One customer-facing question that still needs an explicit apply."""

    item_id: str
    kind: str
    field: str
    required: bool
    proposed: str
    source_label: str
    allow_unknown: bool
    group_id: str = ""
    affected_source_rows: tuple[int, ...] = ()


def empty_committed() -> dict[str, Any]:
    return {
        "columns": {},
        "date_mode": "",
        "year_month_confirmed": False,
        "period_start": None,
        "period_end": None,
        "activity_type_value_map": {},
        "unit_value_map": {},
        "natural_gas_subtype": "",
        "natural_gas_groups": {},
        "pending_heating_value_reviews": {},
        "question_log": [],
        "question_snapshots": [],
        "diesel_context": "",
        "electricity_context": "",
        "document_date": None,
        "applied_ids": [],
    }


def _suggestion(
    detailed: dict[str, FieldSuggestion],
    field_name: str,
) -> FieldSuggestion:
    return detailed.get(
        field_name,
        FieldSuggestion(field_name, "", CONFIDENCE_LOW),
    )


def initialize_committed(
    table: Any,
    detailed: dict[str, FieldSuggestion],
) -> dict[str, Any]:
    """Adopt High-confidence matches only. Never adopt Medium or Low."""
    committed = empty_committed()
    columns: dict[str, str] = {}
    for field_name in COLUMN_FIELDS:
        suggestion = _suggestion(detailed, field_name)
        if suggestion.confidence == CONFIDENCE_HIGH and suggestion.source_column:
            columns[field_name] = suggestion.source_column
    committed["columns"] = columns
    if columns.get("activity_start_date") and columns.get("activity_end_date"):
        committed["date_mode"] = "file"
    elif columns.get("year_month"):
        committed["date_mode"] = "year_month"
    _autofill_value_maps(table, committed)
    _autofill_context_from_file(table, committed)
    _autofill_document_date(table, committed)
    return committed


def high_match_count(detailed: dict[str, FieldSuggestion]) -> int:
    """Count High-confidence column matches only."""
    return sum(
        1
        for field_name in COLUMN_FIELDS
        if _suggestion(detailed, field_name).confidence == CONFIDENCE_HIGH
        and _suggestion(detailed, field_name).source_column
    )


def _draft_mapping(table: Any, committed: dict[str, Any]) -> ColumnMapping:
    columns = dict(committed.get("columns") or {})
    date_mode = str(committed.get("date_mode") or "")
    return ColumnMapping(
        activity_type_column=columns.get("activity_type", ""),
        activity_value_column=columns.get("activity_value", ""),
        unit_column=columns.get("unit", ""),
        site_column=columns.get("site_id", ""),
        use_file_dates=date_mode == "file",
        use_year_month=date_mode == "year_month",
        year_month_column=columns.get("year_month", ""),
        year_month_confirmed=bool(committed.get("year_month_confirmed")),
        start_date_column=columns.get("activity_start_date", ""),
        end_date_column=columns.get("activity_end_date", ""),
        period_start=_as_date(committed.get("period_start")),
        period_end=_as_date(committed.get("period_end")),
        natural_gas_subtype=str(
            committed.get("natural_gas_subtype") or "unknown"
        ),
        natural_gas_subtype_column=columns.get("fuel_subtype", ""),
        natural_gas_groups={
            str(key): str(value)
            for key, value in dict(committed.get("natural_gas_groups") or {}).items()
            if str(value).strip()
        },
        diesel_context=str(committed.get("diesel_context") or "unknown"),
        electricity_context=str(
            committed.get("electricity_context") or "unknown"
        ),
        refrigerant_code_column=columns.get("refrigerant_code", ""),
        refill_confirmed_column=columns.get("refill_confirmed", ""),
        ownership_control_column=columns.get("ownership_control", ""),
        organizational_boundary_column=columns.get(
            "organizational_boundary_status", ""
        ),
        activity_type_value_map=dict(
            committed.get("activity_type_value_map") or {}
        ),
        unit_value_map=dict(committed.get("unit_value_map") or {}),
    )


def mapping_from_committed(table: Any, committed: dict[str, Any]) -> ColumnMapping:
    """Committed mapping only. Draft widget values must not be passed in."""
    return _draft_mapping(table, committed)


def _source_row_for_offset(table: Any, offset: int) -> int:
    header = int(getattr(table, "header_row_index", 0) or 0)
    return offset + header + 2


def _row_site_id(row: Any, mapping: ColumnMapping) -> str:
    site_col = str(mapping.site_column or "").strip()
    if site_col and site_col in getattr(row, "index", []):
        raw = row.get(site_col)
        return str(raw).strip() if raw is not None else ""
    return ""


def unresolved_natural_gas_groups(
    table: Any,
    mapping: ColumnMapping,
    committed: dict[str, Any],
) -> list[dict[str, Any]]:
    """Group unresolved NG rows by confirmed site / single-source file."""
    frame = table.frame
    activity_col = mapping.activity_type_column
    if not activity_col or activity_col not in frame.columns:
        return []
    value_map = mapping.activity_type_value_map or {}
    subtype_col = fuel_subtype_source_column(frame.columns, mapping)
    has_site = bool(str(mapping.site_column or "").strip())
    answers = dict(committed.get("natural_gas_groups") or {})
    buckets: dict[str, list[int]] = {}
    ungroupable: list[int] = []
    for offset, (_, row) in enumerate(frame.iterrows()):
        source = row.get(activity_col)
        source_text = str(source).strip() if source is not None else ""
        mapped = value_map.get(source_text) or suggest_activity_type(source_text)
        if mapped != "natural_gas":
            continue
        if extract_natural_gas_subtype_from_text(source_text):
            continue
        if subtype_col and subtype_col in frame.columns:
            if extract_natural_gas_subtype_from_text(row.get(subtype_col)):
                continue
        source_row = _source_row_for_offset(table, offset)
        group_key = ng_group_key_for_site(
            _row_site_id(row, mapping), has_site_column=has_site
        )
        if group_key is None:
            ungroupable.append(source_row)
            continue
        if str(answers.get(group_key) or "").strip() in NG_ANSWERED_VALUES:
            continue
        buckets.setdefault(group_key, []).append(source_row)
    file_answer = str(committed.get("natural_gas_subtype") or "").strip()
    # Legacy / programmatic file-level answer applies only when there is a
    # single site-or-source group. Mixed-site files still get per-group questions.
    if (
        file_answer in NG_ANSWERED_VALUES
        and len(buckets) == 1
        and not any(
            str(value).strip() in NG_ANSWERED_VALUES for value in answers.values()
        )
    ):
        buckets.clear()
    groups: list[dict[str, Any]] = []
    for group_id, rows in buckets.items():
        groups.append(
            {
                "group_id": group_id,
                "source_rows": tuple(rows),
                "ungroupable": False,
            }
        )
    if ungroupable:
        groups.append(
            {
                "group_id": "",
                "source_rows": tuple(ungroupable),
                "ungroupable": True,
            }
        )
    return groups


def required_columns_ready(committed: dict[str, Any]) -> bool:
    columns = committed.get("columns") or {}
    return all(columns.get(name) for name in REQUIRED_FIELDS)


def dates_ready(committed: dict[str, Any]) -> bool:
    columns = committed.get("columns") or {}
    mode = str(committed.get("date_mode") or "")
    if mode == "file":
        return bool(
            columns.get("activity_start_date") and columns.get("activity_end_date")
        )
    if mode == "year_month":
        return bool(
            columns.get("year_month") and committed.get("year_month_confirmed")
        )
    if mode == "period":
        return (
            _as_date(committed.get("period_start")) is not None
            and _as_date(committed.get("period_end")) is not None
        )
    return False


def _autofill_value_maps(table: Any, committed: dict[str, Any]) -> None:
    columns = committed.get("columns") or {}
    activity_col = columns.get("activity_type", "")
    unit_col = columns.get("unit", "")
    activity_map = dict(committed.get("activity_type_value_map") or {})
    unit_map = dict(committed.get("unit_value_map") or {})
    if activity_col:
        draft = ColumnMapping(activity_type_column=activity_col)
        suggested, _ = default_value_maps(table, draft)
        for source, mapped in suggested.items():
            if source not in activity_map and mapped:
                activity_map[source] = mapped
    if unit_col:
        draft = ColumnMapping(unit_column=unit_col)
        _, suggested_units = default_value_maps(table, draft)
        for source, mapped in suggested_units.items():
            if source not in unit_map and mapped:
                unit_map[source] = mapped
    committed["activity_type_value_map"] = activity_map
    committed["unit_value_map"] = unit_map


def _autofill_context_from_file(table: Any, committed: dict[str, Any]) -> None:
    columns = committed.get("columns") or {}
    activity_col = columns.get("activity_type", "")
    if not activity_col or activity_col not in table.frame.columns:
        return
    mapping = _draft_mapping(table, committed)
    needed = context_confirmations_needed(table, mapping)
    if not needed.get(CONTEXT_NG):
        activity_col = columns.get("activity_type", "")
        subtype_col = fuel_subtype_source_column(table.frame.columns, mapping)
        value_map = mapping.activity_type_value_map or {}
        found: set[str] = set()
        for _, row in table.frame.iterrows():
            source = str(row.get(activity_col) or "").strip()
            mapped = value_map.get(source) or suggest_activity_type(source)
            if mapped != "natural_gas":
                continue
            subtype = extract_natural_gas_subtype_from_text(source)
            if not subtype and subtype_col and subtype_col in table.frame.columns:
                subtype = extract_natural_gas_subtype_from_text(
                    row.get(subtype_col)
                )
            if subtype in {"NG1", "NG2"}:
                found.add(subtype)
        if len(found) == 1:
            committed["natural_gas_subtype"] = next(iter(found))
        else:
            for source, mapped in mapping.activity_type_value_map.items():
                if mapped != "natural_gas":
                    continue
                subtype = extract_natural_gas_subtype_from_text(source)
                if subtype:
                    committed["natural_gas_subtype"] = subtype
                    break
    if not needed.get(CONTEXT_DIESEL):
        for source, mapped in mapping.activity_type_value_map.items():
            if mapped == "diesel" and extract_diesel_vehicle_context_from_text(
                source
            ):
                committed["diesel_context"] = "company_vehicle"
                break
    if not needed.get(CONTEXT_ELECTRICITY) and any(
        mapped == "grid_electricity"
        for mapped in mapping.activity_type_value_map.values()
    ):
        # Electricity still needs an explicit enterprise confirmation unless
        # the mapping already recorded it. Leave unanswered.
        pass


def _autofill_document_date(table: Any, committed: dict[str, Any]) -> None:
    columns = committed.get("columns") or {}
    end_col = columns.get("activity_end_date", "")
    if not end_col or end_col not in table.frame.columns:
        return
    latest: date | None = None
    for item in table.frame[end_col].tolist():
        parsed = _as_date(item)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    if latest is not None:
        committed["document_date"] = latest.isoformat()


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return date(value.year, value.month, value.day)
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def list_exceptions(
    table: Any,
    detailed: dict[str, FieldSuggestion],
    committed: dict[str, Any],
) -> list[IntakeException]:
    """Unanswered Medium/Low/context items. High matches are omitted."""
    items: list[IntakeException] = []
    columns = dict(committed.get("columns") or {})

    for field_name in REQUIRED_FIELDS:
        suggestion = _suggestion(detailed, field_name)
        if columns.get(field_name):
            continue
        if suggestion.confidence == CONFIDENCE_MEDIUM and suggestion.source_column:
            items.append(
                IntakeException(
                    item_id=f"column:{field_name}",
                    kind=KIND_COLUMN,
                    field=field_name,
                    required=True,
                    proposed=suggestion.source_column,
                    source_label=suggestion.source_column,
                    allow_unknown=False,
                )
            )
        else:
            items.append(
                IntakeException(
                    item_id=f"column:{field_name}",
                    kind=KIND_COLUMN,
                    field=field_name,
                    required=True,
                    proposed="",
                    source_label="",
                    allow_unknown=False,
                )
            )

    for field_name in OPTIONAL_FIELDS:
        suggestion = _suggestion(detailed, field_name)
        if columns.get(field_name):
            continue
        if suggestion.confidence == CONFIDENCE_MEDIUM and suggestion.source_column:
            items.append(
                IntakeException(
                    item_id=f"column:{field_name}",
                    kind=KIND_COLUMN,
                    field=field_name,
                    required=False,
                    proposed=suggestion.source_column,
                    source_label=suggestion.source_column,
                    allow_unknown=True,
                )
            )

    if not dates_ready(committed):
        ym = _suggestion(detailed, "year_month")
        if (
            str(committed.get("date_mode") or "") == "year_month"
            or (
                ym.confidence == CONFIDENCE_HIGH
                and ym.source_column
                and not committed.get("year_month_confirmed")
            )
        ):
            items.append(
                IntakeException(
                    item_id="year_month_confirm",
                    kind=KIND_YEAR_MONTH,
                    field="year_month",
                    required=True,
                    proposed=columns.get("year_month") or ym.source_column,
                    source_label=columns.get("year_month") or ym.source_column,
                    allow_unknown=False,
                )
            )
        else:
            items.append(
                IntakeException(
                    item_id="dates_period",
                    kind=KIND_DATES,
                    field="period",
                    required=True,
                    proposed="",
                    source_label="",
                    allow_unknown=False,
                )
            )

    if columns.get("activity_type"):
        mapping = _draft_mapping(table, committed)
        activity_map = mapping.activity_type_value_map
        for source in distinct_values(table.frame, columns["activity_type"]):
            if source in activity_map:
                continue
            mapped = suggest_activity_type(source)
            if mapped:
                continue
            items.append(
                IntakeException(
                    item_id=f"activity_value:{source}",
                    kind=KIND_ACTIVITY_VALUE,
                    field="activity_type",
                    required=True,
                    proposed="",
                    source_label=source,
                    allow_unknown=True,
                )
            )
        if columns.get("unit"):
            unit_map = mapping.unit_value_map
            for source in distinct_values(table.frame, columns["unit"]):
                if source in unit_map:
                    continue
                mapped = suggest_unit(source)
                if mapped:
                    continue
                items.append(
                    IntakeException(
                        item_id=f"unit_value:{source}",
                        kind=KIND_UNIT_VALUE,
                        field="unit",
                        required=True,
                        proposed="",
                        source_label=source,
                        allow_unknown=True,
                    )
                )
        needed = context_confirmations_needed(table, mapping)
        ng_groups = unresolved_natural_gas_groups(table, mapping, committed)
        askable = [group for group in ng_groups if not group["ungroupable"]]
        for group in askable:
            group_id = str(group["group_id"])
            item_id = (
                "context:natural_gas"
                if len(askable) == 1
                else f"context:natural_gas:site:{group_id}"
            )
            items.append(
                IntakeException(
                    item_id=item_id,
                    kind=KIND_CONTEXT,
                    field=CONTEXT_NG,
                    required=True,
                    proposed="",
                    source_label=group_id,
                    allow_unknown=True,
                    group_id=group_id,
                    affected_source_rows=tuple(group["source_rows"]),
                )
            )
        if needed.get(CONTEXT_DIESEL) and not str(
            committed.get("diesel_context") or ""
        ):
            items.append(
                IntakeException(
                    item_id="context:diesel",
                    kind=KIND_CONTEXT,
                    field=CONTEXT_DIESEL,
                    required=True,
                    proposed="",
                    source_label="",
                    allow_unknown=True,
                )
            )
        if needed.get(CONTEXT_ELECTRICITY) and not str(
            committed.get("electricity_context") or ""
        ):
            items.append(
                IntakeException(
                    item_id="context:electricity",
                    kind=KIND_CONTEXT,
                    field=CONTEXT_ELECTRICITY,
                    required=True,
                    proposed="",
                    source_label="",
                    allow_unknown=True,
                )
            )
    return items


def exception_snapshot(item: IntakeException) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "kind": item.kind,
        "field": item.field,
        "required": item.required,
        "proposed": item.proposed,
        "source_label": item.source_label,
        "allow_unknown": item.allow_unknown,
        "group_id": item.group_id,
        "affected_source_rows": list(item.affected_source_rows),
    }


def exception_from_snapshot(data: dict[str, Any]) -> IntakeException:
    rows = data.get("affected_source_rows") or ()
    return IntakeException(
        item_id=str(data.get("item_id") or ""),
        kind=str(data.get("kind") or ""),
        field=str(data.get("field") or ""),
        required=bool(data.get("required")),
        proposed=str(data.get("proposed") or ""),
        source_label=str(data.get("source_label") or ""),
        allow_unknown=bool(data.get("allow_unknown")),
        group_id=str(data.get("group_id") or ""),
        affected_source_rows=tuple(int(value) for value in rows),
    )


def confirmation_timeline(
    table: Any,
    detailed: dict[str, FieldSuggestion],
    committed: dict[str, Any],
) -> list[IntakeException]:
    """Answered snapshots first, then remaining questions. One slot, no stack."""
    remaining = list_exceptions(table, detailed, committed)
    remaining_ids = {item.item_id for item in remaining}
    items: list[IntakeException] = []
    seen: set[str] = set()
    for snap in committed.get("question_snapshots") or []:
        if not isinstance(snap, dict):
            continue
        item = exception_from_snapshot(snap)
        if not item.item_id or item.item_id in remaining_ids or item.item_id in seen:
            continue
        items.append(item)
        seen.add(item.item_id)
    items.extend(remaining)
    return items


def _record_answered_question(
    next_state: dict[str, Any], item: IntakeException
) -> None:
    log = list(next_state.get("question_log") or [])
    snaps = [
        dict(entry)
        for entry in (next_state.get("question_snapshots") or [])
        if isinstance(entry, dict)
    ]
    snapshot = exception_snapshot(item)
    if item.item_id in log:
        replaced = False
        for index, entry in enumerate(snaps):
            if str(entry.get("item_id") or "") == item.item_id:
                snaps[index] = snapshot
                replaced = True
                break
        if not replaced:
            snaps.append(snapshot)
    else:
        log.append(item.item_id)
        snaps.append(snapshot)
    next_state["question_log"] = log
    next_state["question_snapshots"] = snaps


def unresolved_count(
    table: Any,
    detailed: dict[str, FieldSuggestion],
    committed: dict[str, Any],
) -> int:
    """True unresolved count. Zero remains zero."""
    return len(list_exceptions(table, detailed, committed))


def summary_counts(
    table: Any,
    detailed: dict[str, FieldSuggestion],
    committed: dict[str, Any],
) -> dict[str, int]:
    exceptions = list_exceptions(table, detailed, committed)
    ready, waiting = row_readiness_counts(table, committed, exceptions)
    return {
        "recognized": high_match_count(detailed),
        "confirm": len(exceptions),
        "ready_rows": ready,
        "waiting_rows": waiting,
    }


def apply_exception(
    committed: dict[str, Any],
    item: IntakeException,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Commit one explicit answer. Does not mutate the input dict."""
    next_state = {
        **committed,
        "columns": dict(committed.get("columns") or {}),
        "activity_type_value_map": dict(
            committed.get("activity_type_value_map") or {}
        ),
        "unit_value_map": dict(committed.get("unit_value_map") or {}),
        "applied_ids": list(committed.get("applied_ids") or []),
    }
    item_id = item.item_id
    if item.kind == KIND_COLUMN:
        column = str(payload.get("column") or "").strip()
        if column:
            next_state["columns"][item.field] = column
        elif item.required:
            return committed
        next_state["applied_ids"] = _with_id(next_state["applied_ids"], item_id)
        table = payload.get("table")
        if table is not None:
            _autofill_value_maps(table, next_state)
            _autofill_context_from_file(table, next_state)
            _autofill_document_date(table, next_state)
        _record_answered_question(next_state, item)
        return next_state
    if item.kind == KIND_YEAR_MONTH:
        if payload.get("confirmed"):
            column = str(payload.get("column") or item.proposed or "").strip()
            if column:
                next_state["columns"]["year_month"] = column
            next_state["date_mode"] = "year_month"
            next_state["year_month_confirmed"] = True
            next_state["applied_ids"] = _with_id(
                next_state["applied_ids"], item_id
            )
            _record_answered_question(next_state, item)
        return next_state
    if item.kind == KIND_DATES:
        mode = str(payload.get("date_mode") or "")
        if mode == "file":
            start = str(payload.get("start_column") or "").strip()
            end = str(payload.get("end_column") or "").strip()
            if not start or not end:
                return committed
            next_state["columns"]["activity_start_date"] = start
            next_state["columns"]["activity_end_date"] = end
            next_state["date_mode"] = "file"
        elif mode == "year_month":
            column = str(payload.get("year_month_column") or "").strip()
            if not column or not payload.get("confirmed"):
                return committed
            next_state["columns"]["year_month"] = column
            next_state["date_mode"] = "year_month"
            next_state["year_month_confirmed"] = True
        elif mode == "period":
            start = _as_date(payload.get("period_start"))
            end = _as_date(payload.get("period_end"))
            if start is None or end is None:
                return committed
            next_state["period_start"] = start.isoformat()
            next_state["period_end"] = end.isoformat()
            next_state["document_date"] = end.isoformat()
            next_state["date_mode"] = "period"
        else:
            return committed
        next_state["applied_ids"] = _with_id(next_state["applied_ids"], item_id)
        _record_answered_question(next_state, item)
        return next_state
    if item.kind == KIND_CONTEXT:
        value = str(payload.get("value") or "").strip()
        if not value:
            return committed
        if item.field == CONTEXT_NG:
            groups = dict(next_state.get("natural_gas_groups") or {})
            group_id = str(item.group_id or "").strip() or NG_GROUP_SINGLE
            if value == NG_VALUE_PENDING_HV:
                heating_value = str(payload.get("heating_value") or "").strip()
                heating_unit = str(payload.get("heating_unit") or "").strip()
                period_start = str(payload.get("period_start") or "").strip()
                period_end = str(payload.get("period_end") or "").strip()
                source_ref = str(payload.get("source_reference") or "").strip()
                if not all(
                    [heating_value, heating_unit, period_start, period_end, source_ref]
                ):
                    return committed
                reviews = dict(next_state.get("pending_heating_value_reviews") or {})
                reviews[group_id] = {
                    "value": heating_value,
                    "unit": heating_unit,
                    "period_start": period_start,
                    "period_end": period_end,
                    "source": source_ref,
                    "source_rows": list(item.affected_source_rows),
                    "status": "pending_review",
                }
                next_state["pending_heating_value_reviews"] = reviews
            groups[group_id] = value
            next_state["natural_gas_groups"] = groups
            if group_id == NG_GROUP_SINGLE:
                next_state["natural_gas_subtype"] = (
                    value if value in {"NG1", "NG2", "unknown"} else "unknown"
                )
        elif item.field == CONTEXT_DIESEL:
            next_state["diesel_context"] = value
        elif item.field == CONTEXT_ELECTRICITY:
            next_state["electricity_context"] = value
        next_state["applied_ids"] = _with_id(next_state["applied_ids"], item_id)
        _record_answered_question(next_state, item)
        return next_state
    if item.kind == KIND_ACTIVITY_VALUE:
        mapped = str(payload.get("value") or "").strip()
        if mapped == "unknown":
            next_state["activity_type_value_map"][item.source_label] = ""
            next_state["applied_ids"] = _with_id(
                next_state["applied_ids"], item_id
            )
            _record_answered_question(next_state, item)
            return next_state
        if not mapped or mapped not in ACTIVITY_TYPES:
            return committed
        next_state["activity_type_value_map"][item.source_label] = mapped
        next_state["applied_ids"] = _with_id(next_state["applied_ids"], item_id)
        _record_answered_question(next_state, item)
        return next_state
    if item.kind == KIND_UNIT_VALUE:
        mapped = str(payload.get("value") or "").strip()
        if mapped == "unknown":
            next_state["unit_value_map"][item.source_label] = ""
            next_state["applied_ids"] = _with_id(
                next_state["applied_ids"], item_id
            )
            _record_answered_question(next_state, item)
            return next_state
        if not mapped or mapped not in SUPPORTED_UNITS:
            return committed
        next_state["unit_value_map"][item.source_label] = mapped
        next_state["applied_ids"] = _with_id(next_state["applied_ids"], item_id)
        _record_answered_question(next_state, item)
        return next_state
    return committed


def _with_id(applied: list[str], item_id: str) -> list[str]:
    if item_id in applied:
        return applied
    return [*applied, item_id]


def medium_is_uncommitted(
    detailed: dict[str, FieldSuggestion],
    committed: dict[str, Any],
    field_name: str,
) -> bool:
    suggestion = _suggestion(detailed, field_name)
    if suggestion.confidence != CONFIDENCE_MEDIUM or not suggestion.source_column:
        return False
    return (committed.get("columns") or {}).get(field_name) != suggestion.source_column


def required_unresolved_blocks(
    table: Any,
    detailed: dict[str, FieldSuggestion],
    committed: dict[str, Any],
) -> bool:
    exceptions = list_exceptions(table, detailed, committed)
    return any(item.required for item in exceptions)


def _source_row_from_locator(locator: Any) -> int:
    text = str(locator or "")
    if "row:" not in text:
        return 0
    try:
        return int(text.rsplit("row:", 1)[-1])
    except ValueError:
        return 0


def _ng_row_is_held(row: Any, mapping: ColumnMapping) -> bool:
    activity_source = row.get(mapping.activity_type_column)
    if extract_natural_gas_subtype_from_text(activity_source):
        return False
    subtype_col = fuel_subtype_source_column(getattr(row, "index", []), mapping)
    if subtype_col:
        extracted = extract_natural_gas_subtype_from_text(row.get(subtype_col))
        if extracted:
            return False
    site_id = str(row.get("site_id") or "").strip() or _row_site_id(row, mapping)
    group_key = ng_group_key_for_site(
        site_id, has_site_column=bool(str(mapping.site_column or "").strip())
    )
    grouped = ""
    if group_key:
        grouped = str((mapping.natural_gas_groups or {}).get(group_key) or "").strip()
    if grouped in {"NG1", "NG2"}:
        return False
    if grouped in {"unknown", NG_VALUE_PENDING_HV}:
        return True
    if group_key is None:
        return True
    if not mapping.natural_gas_groups:
        return str(mapping.natural_gas_subtype or "").strip() not in {"NG1", "NG2"}
    return True


def _diesel_row_is_held(row: Any, mapping: ColumnMapping) -> bool:
    activity_source = row.get(mapping.activity_type_column)
    if extract_diesel_vehicle_context_from_text(activity_source):
        return False
    return str(mapping.diesel_context or "").strip() != "company_vehicle"


def _electricity_row_is_held(mapping: ColumnMapping) -> bool:
    return str(mapping.electricity_context or "").strip() != "enterprise"


def row_readiness_counts(
    table: Any,
    committed: dict[str, Any],
    exceptions: list[IntakeException] | None = None,
) -> tuple[int, int]:
    """Rows that can continue vs rows held out. Never silent-drop."""
    frame = table.frame
    total = int(len(frame))
    if not required_columns_ready(committed) or not dates_ready(committed):
        return 0, total
    mapping = _draft_mapping(table, committed)
    waiting = 0
    ready = 0
    activity_col = mapping.activity_type_column
    unit_col = mapping.unit_column
    value_col = mapping.activity_value_column
    for _, row in frame.iterrows():
        raw_activity = row.get(activity_col)
        raw_value = row.get(value_col)
        raw_unit = row.get(unit_col)
        if (
            (raw_activity is None or str(raw_activity).strip() == "")
            and (raw_value is None or str(raw_value).strip() == "")
            and (raw_unit is None or str(raw_unit).strip() == "")
        ):
            continue
        activity_key = str(raw_activity).strip() if raw_activity is not None else ""
        mapped = mapping.activity_type_value_map.get(activity_key, "")
        unit_key = str(raw_unit).strip() if raw_unit is not None else ""
        mapped_unit = mapping.unit_value_map.get(unit_key, "")
        blocked = False
        if not mapped or mapped not in ACTIVITY_TYPES:
            blocked = True
        elif not mapped_unit or mapped_unit not in SUPPORTED_UNITS:
            blocked = True
        elif mapped == "natural_gas" and _ng_row_is_held(row, mapping):
            blocked = True
        elif mapped == "diesel" and _diesel_row_is_held(row, mapping):
            blocked = True
        elif mapped == "grid_electricity" and _electricity_row_is_held(mapping):
            blocked = True
        if blocked:
            waiting += 1
        else:
            ready += 1
    return ready, waiting


def hold_unknown_context_rows(
    result: IntakeValidationResult,
    mapping: ColumnMapping,
) -> IntakeValidationResult:
    """Move unknown-context rows out of accepted so validation matches summary."""
    accepted = result.accepted_activities
    if accepted is None or accepted.empty:
        return result
    keep_rows: list[int] = []
    extra: list[dict[str, Any]] = []
    for idx, row in accepted.iterrows():
        activity = str(row.get("activity_type") or "")
        held_code = ""
        held_field = ""
        if activity == "natural_gas":
            fuel = str(row.get("fuel_subtype") or "").strip()
            if fuel not in {"NG1", "NG2"}:
                site_id = str(row.get("site_id") or "").strip()
                group_key = ng_group_key_for_site(
                    site_id,
                    has_site_column=bool(str(mapping.site_column or "").strip()),
                )
                grouped = ""
                if group_key:
                    grouped = str(
                        (mapping.natural_gas_groups or {}).get(group_key) or ""
                    ).strip()
                if grouped == NG_VALUE_PENDING_HV:
                    held_code = ISSUE_HELD_PENDING_ACTUAL_HV
                else:
                    held_code = ISSUE_HELD_NG_CONTEXT
                held_field = "fuel_subtype"
        elif activity == "diesel":
            process_use = str(row.get("process_use") or "").strip()
            if process_use != "company_vehicle":
                held_code = ISSUE_HELD_DIESEL_CONTEXT
                held_field = "process_use"
        elif activity == "grid_electricity":
            if _electricity_row_is_held(mapping):
                held_code = ISSUE_HELD_ELEC_CONTEXT
                held_field = "process_use"
        if not held_code:
            keep_rows.append(idx)
            continue
        extra.append(
            {
                "source_row": _source_row_from_locator(row.get("source_locator")),
                "field": held_field,
                "issue_code": held_code,
                "issue_message": held_code,
                "uploaded_value": activity,
            }
        )
    if not extra:
        return result
    kept = accepted.loc[keep_rows].reset_index(drop=True)
    extra_df = pd.DataFrame(extra, columns=list(REJECTION_COLUMNS))
    rejected = result.rejected_rows
    if rejected is None or rejected.empty:
        rejected = extra_df
    else:
        rejected = pd.concat([rejected, extra_df], ignore_index=True)
    return IntakeValidationResult(
        source_documents=result.source_documents,
        accepted_activities=kept,
        rejected_rows=rejected,
        accepted_count=int(len(kept)),
        rejected_count=int(len(rejected)),
        total_count=int(len(kept) + len(rejected)),
        file_hash=result.file_hash,
        file_name=result.file_name,
        potential_duplicate_groups=result.potential_duplicate_groups,
    )


def can_validate(
    table: Any,
    detailed: dict[str, FieldSuggestion],
    committed: dict[str, Any],
) -> bool:
    if required_unresolved_blocks(table, detailed, committed):
        return False
    if not required_columns_ready(committed) or not dates_ready(committed):
        return False
    return True
