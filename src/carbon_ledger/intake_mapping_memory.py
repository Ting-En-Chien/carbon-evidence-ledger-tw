"""Stage 4.2F-C2 — session-scoped mapping memory and append-only provenance.

No module-global customer cache. Callers pass session_state explicitly.
Memory identity is confirmed UBN + structural fingerprint + schema version.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from carbon_ledger.intake import (
    FieldSuggestion,
    source_document_id_from_hash,
    structural_normalize_header,
)

MAPPING_SCHEMA_VERSION = "intake-mapping-v1"

EVENT_SYSTEM_SUGGESTED = "system_suggested"
EVENT_CUSTOMER_CONFIRMED = "customer_confirmed"
EVENT_CUSTOMER_CORRECTED = "customer_corrected"
EVENT_MEMORY_OFFERED = "remembered_mapping_offered"
EVENT_MEMORY_APPLIED = "remembered_mapping_applied"
EVENT_MARKED_UNKNOWN = "marked_unknown_and_held"
EVENT_VALIDATION_REJECTED = "validation_rejected"

CUSTOMER_EVENT_LABELS = {
    EVENT_SYSTEM_SUGGESTED: "系統建議",
    EVENT_CUSTOMER_CONFIRMED: "你已確認",
    EVENT_CUSTOMER_CORRECTED: "你已調整",
    EVENT_MEMORY_OFFERED: "發現上次設定",
    EVENT_MEMORY_APPLIED: "已沿用上次設定",
    EVENT_MARKED_UNKNOWN: "暫緩處理",
    EVENT_VALIDATION_REJECTED: "驗證未通過",
}
CUSTOMER_EVENT_LABELS_EN = {
    EVENT_SYSTEM_SUGGESTED: "System suggested",
    EVENT_CUSTOMER_CONFIRMED: "You confirmed",
    EVENT_CUSTOMER_CORRECTED: "You adjusted",
    EVENT_MEMORY_OFFERED: "Previous settings found",
    EVENT_MEMORY_APPLIED: "Previous settings reused",
    EVENT_MARKED_UNKNOWN: "Deferred",
    EVENT_VALIDATION_REJECTED: "Validation did not pass",
}

_UNKNOWN_SENTINELS = frozenset({"", "unknown"})
_SAFE_COLUMN_FIELDS = frozenset(
    {
        "activity_type",
        "activity_value",
        "unit",
        "site_id",
        "fuel_subtype",
        "refrigerant_code",
        "refill_confirmed",
        "ownership_control",
        "organizational_boundary_status",
        "activity_start_date",
        "activity_end_date",
        "year_month",
    }
)
_SAFE_DATE_MODES = frozenset({"file", "year_month", "period"})


def structural_fingerprint(
    *,
    columns: list[str] | tuple[str, ...],
    sheet_name: str = "",
    header_row_index: int = 0,
    schema_version: str = MAPPING_SCHEMA_VERSION,
) -> str:
    """Hash table structure without changing worksheet titles or cell values."""
    _ = sheet_name
    payload = {
        "header_index": int(header_row_index or 0),
        "names": [structural_normalize_header(col) for col in columns],
        "schema": schema_version,
    }
    blob = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def memory_identity_key(
    ubn: str,
    fingerprint: str,
    *,
    schema_version: str = MAPPING_SCHEMA_VERSION,
) -> str:
    return f"{str(ubn).strip()}|{schema_version}|{fingerprint}"


def snapshot_rememberable_committed(committed: dict[str, Any]) -> dict[str, Any]:
    """Keep only reusable structure and explicitly confirmed source labels."""
    columns = {
        str(field): str(column)
        for field, column in dict(committed.get("columns") or {}).items()
        if field in _SAFE_COLUMN_FIELDS and str(column).strip()
    }
    applied_ids = {
        str(item) for item in list(committed.get("applied_ids") or [])
    }
    activity_map = {
        str(source): str(mapped)
        for source, mapped in dict(
            committed.get("activity_type_value_map") or {}
        ).items()
        if str(mapped).strip()
        and str(mapped).strip() not in _UNKNOWN_SENTINELS
        and f"activity_value:{source}" in applied_ids
    }
    unit_map = {
        str(source): str(mapped)
        for source, mapped in dict(committed.get("unit_value_map") or {}).items()
        if str(mapped).strip()
        and str(mapped).strip() not in _UNKNOWN_SENTINELS
        and f"unit_value:{source}" in applied_ids
    }
    date_mode = str(committed.get("date_mode") or "").strip()
    if date_mode not in _SAFE_DATE_MODES:
        date_mode = ""
    snapshot: dict[str, Any] = {
        "activity_type_value_map": activity_map,
        "columns": columns,
        "date_mode": date_mode,
        "schema_version": MAPPING_SCHEMA_VERSION,
        "unit_value_map": unit_map,
        "year_month_confirmed": (
            date_mode == "year_month"
            and bool(committed.get("year_month_confirmed"))
        ),
    }
    return snapshot


def _frame_values(frame: pd.DataFrame | None, column: str) -> set[str]:
    if frame is None or not column or column not in frame.columns:
        return set()
    return {
        str(value).strip()
        for value in frame[column].tolist()
        if str(value).strip()
    }


def overlay_remembered_committed(
    current: dict[str, Any],
    remembered: dict[str, Any],
    *,
    frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Apply safe remembered structure without copying prior-file facts."""
    merged = {
        **current,
        "activity_type_value_map": dict(
            current.get("activity_type_value_map") or {}
        ),
        "columns": dict(current.get("columns") or {}),
        "unit_value_map": dict(current.get("unit_value_map") or {}),
    }
    available_columns = set(frame.columns) if frame is not None else None
    for field_name, column in dict(remembered.get("columns") or {}).items():
        if (
            field_name in _SAFE_COLUMN_FIELDS
            and str(column).strip()
            and (available_columns is None or column in available_columns)
        ):
            merged["columns"][str(field_name)] = str(column)

    activity_values = _frame_values(
        frame, str(merged["columns"].get("activity_type") or "")
    )
    for source, mapped in dict(
        remembered.get("activity_type_value_map") or {}
    ).items():
        if source in activity_values and str(mapped).strip():
            merged["activity_type_value_map"][str(source)] = str(mapped)

    unit_values = _frame_values(
        frame, str(merged["columns"].get("unit") or "")
    )
    for source, mapped in dict(remembered.get("unit_value_map") or {}).items():
        if source in unit_values and str(mapped).strip():
            merged["unit_value_map"][str(source)] = str(mapped)

    date_mode = str(remembered.get("date_mode") or "")
    if date_mode in _SAFE_DATE_MODES:
        merged["date_mode"] = date_mode
    merged["year_month_confirmed"] = bool(
        date_mode == "year_month"
        and remembered.get("year_month_confirmed")
        and merged["columns"].get("year_month")
    )
    if date_mode == "period":
        merged["period_start"] = None
        merged["period_end"] = None
        merged["document_date"] = None
    return merged


def _entries_from_session(session_state: Any) -> dict[str, Any]:
    raw = None
    try:
        raw = session_state["intake_mapping_memory"]
    except Exception:  # noqa: BLE001 - AppTest session_state has no .get()
        raw = None
    if not isinstance(raw, dict):
        return {}
    entries = raw.get("entries")
    return dict(entries) if isinstance(entries, dict) else {}


def lookup_remembered_mapping(
    session_state: Any,
    *,
    ubn: str,
    fingerprint: str,
    schema_version: str = MAPPING_SCHEMA_VERSION,
) -> dict[str, Any] | None:
    company = str(ubn or "").strip()
    if not company or not fingerprint:
        return None
    entries = _entries_from_session(session_state)
    identity = memory_identity_key(
        company, fingerprint, schema_version=schema_version
    )
    stored = entries.get(identity)
    if not isinstance(stored, dict):
        return None
    snapshot = stored.get("committed")
    if not isinstance(snapshot, dict) or not snapshot.get("columns"):
        return None
    return dict(snapshot)


def remember_committed_mapping(
    session_state: Any,
    *,
    ubn: str,
    fingerprint: str,
    committed: dict[str, Any],
    source_document_id: str = "",
    schema_version: str = MAPPING_SCHEMA_VERSION,
) -> None:
    company = str(ubn or "").strip()
    snapshot = snapshot_rememberable_committed(committed)
    if not company or not fingerprint or not snapshot.get("columns"):
        return
    entries = _entries_from_session(session_state)
    identity = memory_identity_key(
        company, fingerprint, schema_version=schema_version
    )
    entries[identity] = {
        "committed": snapshot,
        "fingerprint": fingerprint,
        "schema_version": schema_version,
        "source_document_id": str(source_document_id or ""),
        "ubn": company,
        "updated_at": _now_iso(),
    }
    session_state["intake_mapping_memory"] = {"entries": entries}


def append_provenance_event(
    session_state: Any,
    *,
    event: str,
    company_ubn: str = "",
    fingerprint: str = "",
    field: str = "",
    proposed: str = "",
    committed: str = "",
    source: str = "",
    reason: str = "",
    source_document_id: str = "",
    schema_version: str = MAPPING_SCHEMA_VERSION,
) -> None:
    history = _history_from_session(session_state)
    history.append(
        {
            "committed": str(committed or ""),
            "company_ubn": str(company_ubn or ""),
            "event": event,
            "field": str(field or ""),
            "fingerprint": str(fingerprint or ""),
            "proposed": str(proposed or ""),
            "reason": str(reason or ""),
            "schema_version": schema_version,
            "source": str(source or ""),
            "source_document_id": str(source_document_id or ""),
            "timestamp": _now_iso(),
        }
    )
    session_state["intake_mapping_provenance"] = history


def record_system_suggestions(
    session_state: Any,
    detailed: dict[str, FieldSuggestion],
    *,
    company_ubn: str,
    fingerprint: str,
    source_document_id: str,
) -> None:
    marker_key = "intake_suggestions_recorded_for"
    identity = "|".join(
        (str(company_ubn or "").strip(), fingerprint, source_document_id)
    )
    try:
        already = session_state[marker_key]
    except Exception:  # noqa: BLE001
        already = None
    if already == identity:
        return
    for field_name, suggestion in detailed.items():
        if not suggestion.source_column:
            continue
        append_provenance_event(
            session_state,
            event=EVENT_SYSTEM_SUGGESTED,
            company_ubn=company_ubn,
            fingerprint=fingerprint,
            field=field_name,
            proposed=suggestion.source_column,
            source="inference",
            reason=suggestion.confidence,
            source_document_id=source_document_id,
        )
    session_state[marker_key] = identity


def customer_history_rows(
    session_state: Any,
    *,
    company_ubn: str,
    lang: str = "zh-TW",
    field_labels: dict[str, str] | None = None,
    value_labels: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Customer-visible history. No fingerprints, hashes, or internal event names."""
    labels = (
        CUSTOMER_EVENT_LABELS_EN if lang == "en" else CUSTOMER_EVENT_LABELS
    )
    rows: list[dict[str, str]] = []
    names = field_labels or {}
    values = value_labels or {}
    active_company = str(company_ubn or "").strip()
    if not active_company:
        return []
    for item in _history_from_session(session_state):
        if str(item.get("company_ubn") or "").strip() != active_company:
            continue
        event = str(item.get("event") or "")
        label = labels.get(event)
        if not label:
            continue
        field_name = str(item.get("field") or "")
        field_label = names.get(field_name, "")
        if field_label in {field_name, "activity_type", "activity_value", "site_id"}:
            field_label = ""
        raw_detail = str(item.get("committed") or item.get("proposed") or "")
        rows.append(
            {
                "action": label,
                "detail": values.get(raw_detail, raw_detail),
                "field": field_label,
                "when": str(item.get("timestamp") or "")[:19].replace("T", " "),
            }
        )
    return rows


def snapshot_contains_raw_samples(payload: Any) -> bool:
    """True when a memory payload appears to include workbook bytes or samples."""
    if isinstance(payload, (bytes, bytearray)):
        return True
    if isinstance(payload, dict):
        forbidden = {
            "bytes",
            "file_bytes",
            "frame",
            "raw",
            "samples",
            "workbook",
        }
        if forbidden.intersection(payload.keys()):
            return True
        return any(snapshot_contains_raw_samples(value) for value in payload.values())
    if isinstance(payload, (list, tuple)):
        return any(snapshot_contains_raw_samples(value) for value in payload)
    return False


def document_id_for_hash(file_hash: str) -> str:
    return source_document_id_from_hash(file_hash)


def _history_from_session(session_state: Any) -> list[dict[str, Any]]:
    try:
        raw = session_state["intake_mapping_provenance"]
    except Exception:  # noqa: BLE001
        raw = None
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
