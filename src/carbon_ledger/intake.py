"""Phase 9A structured company-data intake (upload → map → validate).

Pure presentation-independent logic. Streamlit must not be imported here.
Uploaded bytes are processed in memory only; nothing is written to disk.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from pandera.errors import SchemaError, SchemaErrors

from carbon_ledger.domain import (
    ACTIVITY_TYPE_UNIT_COMPATIBILITY,
    ACTIVITY_TYPES,
    SUPPORTED_UNITS,
)
from carbon_ledger.schemas import (
    validate_activity_records,
    validate_source_documents,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_EXTENSIONS = frozenset({".csv", ".xlsx"})
BLANK_TEMPLATE_COLUMNS = (
    "activity_type",
    "activity_value",
    "unit",
    "activity_start_date",
    "activity_end_date",
)
SOURCE_DOCUMENT_NOTES = "User-uploaded structured activity-data file."
UNMAPPED_SENTINEL = ""

ISSUE_MISSING_REQUIRED_MAPPING = "MISSING_REQUIRED_MAPPING"
ISSUE_INVALID_ACTIVITY_VALUE = "INVALID_ACTIVITY_VALUE"
ISSUE_UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"
ISSUE_ACTIVITY_UNIT_MISMATCH = "ACTIVITY_UNIT_MISMATCH"
ISSUE_INVALID_DATE = "INVALID_DATE"
ISSUE_UNMAPPED_ACTIVITY_TYPE = "UNMAPPED_ACTIVITY_TYPE"
ISSUE_UNMAPPED_UNIT = "UNMAPPED_UNIT"
ISSUE_SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
ISSUE_UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
ISSUE_FILE_TOO_LARGE = "FILE_TOO_LARGE"
ISSUE_INVALID_ENCODING = "INVALID_ENCODING"

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "activity_type": (
        "activity_type",
        "activity",
        "type",
        "活動類型",
        "活動",
        "項目",
    ),
    "activity_value": (
        "activity_value",
        "amount",
        "value",
        "quantity",
        "usage",
        "數量",
        "用量",
        "活動量",
    ),
    "unit": ("unit", "單位"),
    "activity_start_date": (
        "activity_start_date",
        "start_date",
        "period_start",
        "開始日期",
        "起始日期",
    ),
    "activity_end_date": (
        "activity_end_date",
        "end_date",
        "period_end",
        "結束日期",
        "結束日",
    ),
}

ACTIVITY_VALUE_ALIASES: dict[str, str] = {
    "electricity": "grid_electricity",
    "grid electricity": "grid_electricity",
    "grid_electricity": "grid_electricity",
    "外購電力": "grid_electricity",
    "電力": "grid_electricity",
    "用電": "grid_electricity",
    "natural gas": "natural_gas",
    "natural_gas": "natural_gas",
    "天然氣": "natural_gas",
    "diesel": "diesel",
    "柴油": "diesel",
    "steel": "purchased_steel",
    "purchased steel": "purchased_steel",
    "purchased_steel": "purchased_steel",
    "鋼材": "purchased_steel",
    "採購鋼材": "purchased_steel",
    "盤元": "purchased_steel",
    "production": "finished_goods_output",
    "output": "finished_goods_output",
    "finished_goods_output": "finished_goods_output",
    "成品": "finished_goods_output",
    "產量": "finished_goods_output",
    "生產數量": "finished_goods_output",
    "third_party_transport": "third_party_transport",
    "scrap_output": "scrap_output",
    "other": "other",
    "unknown": "unknown",
}

UNIT_VALUE_ALIASES: dict[str, str] = {
    "kwh": "kWh",
    "度": "kWh",
    "mwh": "MWh",
    "m3": "m3",
    "m³": "m3",
    "立方公尺": "m3",
    "立方米": "m3",
    "l": "L",
    "公升": "L",
    "liter": "L",
    "litre": "L",
    "kg": "kg",
    "公斤": "kg",
    "t": "t",
    "噸": "t",
    "公噸": "t",
    "tonne": "t",
    "metric ton": "t",
}

RECORD_TYPE_BY_ACTIVITY: dict[str, str] = {
    "grid_electricity": "emission_activity",
    "natural_gas": "emission_activity",
    "diesel": "emission_activity",
    "purchased_steel": "material_input",
    "third_party_transport": "transport_activity",
    "finished_goods_output": "production_output",
    "scrap_output": "scrap_output",
    "other": "other",
    "unknown": "unknown",
}

REJECTION_COLUMNS = (
    "source_row",
    "field",
    "issue_code",
    "issue_message",
    "uploaded_value",
)


@dataclass(frozen=True)
class UploadedTable:
    """In-memory parsed table from an uploaded CSV/XLSX file."""

    file_name: str
    file_extension: str
    sha256: str
    sheet_name: str | None
    sheet_names: tuple[str, ...]
    columns: tuple[str, ...]
    frame: pd.DataFrame
    byte_length: int


@dataclass
class ColumnMapping:
    """User-confirmed column and value mappings for one upload."""

    activity_type_column: str = ""
    activity_value_column: str = ""
    unit_column: str = ""
    use_file_dates: bool = True
    start_date_column: str = ""
    end_date_column: str = ""
    period_start: date | None = None
    period_end: date | None = None
    activity_type_value_map: dict[str, str] = field(default_factory=dict)
    unit_value_map: dict[str, str] = field(default_factory=dict)


@dataclass
class IntakeMetadata:
    """Once-per-upload metadata provided by the beginner."""

    source_name: str
    site_id: str
    document_date: date
    data_quality_tier: str
    intake_run_id: str
    ingested_at: pd.Timestamp


@dataclass
class IntakeValidationResult:
    """Accepted / rejected preview after canonical build + schema checks."""

    source_documents: pd.DataFrame
    accepted_activities: pd.DataFrame
    rejected_rows: pd.DataFrame
    accepted_count: int
    rejected_count: int
    total_count: int
    file_hash: str
    file_name: str


class IntakeError(ValueError):
    """Beginner-facing intake failure with a stable issue code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def sanitize_filename(name: str) -> str:
    """Return basename only, stripping path components and control chars."""
    raw = str(name or "").strip()
    base = Path(raw.replace("\\", "/")).name
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return cleaned or "uploaded_file"


def compute_bytes_sha256(data: bytes) -> str:
    """Return lowercase SHA-256 hex digest of exact bytes."""
    return hashlib.sha256(data).hexdigest()


def validate_upload_bytes(file_name: str, data: bytes) -> str:
    """Validate extension and size; return sanitized lowercase extension."""
    safe_name = sanitize_filename(file_name)
    extension = Path(safe_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise IntakeError(
            ISSUE_UNSUPPORTED_FILE_TYPE,
            f"Unsupported file type: {extension or '(none)'}.",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise IntakeError(
            ISSUE_FILE_TOO_LARGE,
            "File exceeds the 10 MB Phase 9A limit.",
        )
    if not data:
        raise IntakeError(
            ISSUE_INVALID_ENCODING,
            "Uploaded file is empty.",
        )
    return extension


def blank_template_csv_bytes() -> bytes:
    """Return UTF-8 CSV bytes for the blank downloadable template."""
    header = ",".join(BLANK_TEMPLATE_COLUMNS) + "\n"
    return header.encode("utf-8")


def example_csv_bytes() -> bytes:
    """Return UTF-8 CSV bytes for the beginner example download."""
    lines = [
        ",".join(BLANK_TEMPLATE_COLUMNS),
        "外購電力,50000,kWh,2024-01-01,2024-01-31",
        "天然氣,8000,m3,2024-01-01,2024-01-31",
        "柴油,1200,L,2024-01-01,2024-01-31",
        "採購鋼材,150,t,2024-01-01,2024-01-31",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def example_preview_rows() -> pd.DataFrame:
    """On-screen example rows that are never imported."""
    return pd.DataFrame(
        [
            {
                "activity_type": "外購電力",
                "activity_value": 50000,
                "unit": "kWh",
                "activity_start_date": "2024-01-01",
                "activity_end_date": "2024-01-31",
            },
            {
                "activity_type": "天然氣",
                "activity_value": 8000,
                "unit": "m3",
                "activity_start_date": "2024-01-01",
                "activity_end_date": "2024-01-31",
            },
            {
                "activity_type": "柴油",
                "activity_value": 1200,
                "unit": "L",
                "activity_start_date": "2024-01-01",
                "activity_end_date": "2024-01-31",
            },
            {
                "activity_type": "採購鋼材",
                "activity_value": 150,
                "unit": "t",
                "activity_start_date": "2024-01-01",
                "activity_end_date": "2024-01-31",
            },
        ]
    )


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def suggest_column_mapping(columns: list[str] | tuple[str, ...]) -> dict[str, str]:
    """Deterministic column suggestions from aliases; empty when unmatched."""
    normalized = {_normalize_header(col): col for col in columns}
    suggestions: dict[str, str] = {}
    for target, aliases in COLUMN_ALIASES.items():
        matched = ""
        for alias in aliases:
            key = _normalize_header(alias)
            if key in normalized:
                matched = normalized[key]
                break
        suggestions[target] = matched
    return suggestions


def suggest_activity_type(value: Any) -> str:
    """Suggest a canonical activity type; empty string when unmatched."""
    text = str(value if value is not None else "").strip()
    if not text:
        return UNMAPPED_SENTINEL
    direct = ACTIVITY_VALUE_ALIASES.get(text.lower())
    if direct:
        return direct
    return ACTIVITY_VALUE_ALIASES.get(text, UNMAPPED_SENTINEL)


def suggest_unit(value: Any) -> str:
    """Suggest a canonical unit; empty string when unmatched."""
    text = str(value if value is not None else "").strip()
    if not text:
        return UNMAPPED_SENTINEL
    if text in SUPPORTED_UNITS:
        return text
    return UNIT_VALUE_ALIASES.get(text.lower(), UNMAPPED_SENTINEL)


def distinct_values(frame: pd.DataFrame, column: str) -> list[str]:
    """Return sorted distinct non-null string values for a column."""
    if not column or column not in frame.columns:
        return []
    series = frame[column]
    values: list[str] = []
    seen: set[str] = set()
    for item in series.tolist():
        if item is None or (isinstance(item, float) and math.isnan(item)):
            continue
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return sorted(values)


def list_xlsx_sheet_names(data: bytes) -> list[str]:
    """Return workbook sheet names without writing to disk."""
    frame_dict = pd.read_excel(
        BytesIO(data),
        sheet_name=None,
        dtype=object,
        engine="openpyxl",
    )
    return list(frame_dict.keys())


def parse_uploaded_table(
    *,
    file_name: str,
    data: bytes,
    sheet_name: str | None = None,
) -> UploadedTable:
    """Parse CSV/XLSX bytes into an in-memory UploadedTable."""
    extension = validate_upload_bytes(file_name, data)
    safe_name = sanitize_filename(file_name)
    digest = compute_bytes_sha256(data)
    sheet_names: tuple[str, ...] = ()
    selected_sheet: str | None = None

    if extension == ".csv":
        try:
            frame = pd.read_csv(
                BytesIO(data),
                dtype=object,
                encoding="utf-8-sig",
            )
        except UnicodeDecodeError:
            try:
                frame = pd.read_csv(
                    BytesIO(data),
                    dtype=object,
                    encoding="utf-8",
                )
            except UnicodeDecodeError as exc:
                raise IntakeError(
                    ISSUE_INVALID_ENCODING,
                    "CSV must be UTF-8 encoded.",
                ) from exc
    else:
        workbook = pd.read_excel(
            BytesIO(data),
            sheet_name=None,
            dtype=object,
            engine="openpyxl",
        )
        sheet_names = tuple(workbook.keys())
        if not sheet_names:
            raise IntakeError(
                ISSUE_UNSUPPORTED_FILE_TYPE,
                "Workbook contains no sheets.",
            )
        selected_sheet = sheet_name if sheet_name in sheet_names else sheet_names[0]
        frame = workbook[selected_sheet].copy()

    frame = frame.copy()
    frame.columns = [str(col) for col in frame.columns]
    return UploadedTable(
        file_name=safe_name,
        file_extension=extension,
        sha256=digest,
        sheet_name=selected_sheet,
        sheet_names=sheet_names,
        columns=tuple(str(col) for col in frame.columns),
        frame=frame,
        byte_length=len(data),
    )


def source_document_id_from_hash(sha256: str) -> str:
    """Deterministic source_document_id from file hash."""
    return f"upload_{sha256[:12]}"


def activity_record_id(sha256: str, source_row: int) -> str:
    """Deterministic activity record_id from hash + source row number."""
    return f"up_{sha256[:12]}_r{source_row:04d}"


def source_locator(*, sheet_name: str | None, source_row: int) -> str:
    """Deterministic provenance locator back to the uploaded table."""
    if sheet_name:
        return f"sheet:{sheet_name},row:{source_row}"
    return f"row:{source_row}"


def _parse_date(value: Any, *, field_name: str) -> datetime:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError(f"{field_name} is missing")
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is missing")
    parsed = pd.to_datetime(text, errors="raise")
    if isinstance(parsed, pd.Timestamp):
        return parsed.to_pydatetime().replace(tzinfo=None)
    raise ValueError(f"{field_name} is invalid")


def _parse_activity_value(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError("activity value is missing")
    text = str(value).strip().replace(",", "")
    if not text:
        raise ValueError("activity value is missing")
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("activity value must be finite")
    if number <= 0:
        raise ValueError("activity value must be greater than zero")
    return number


def record_type_for_activity(activity_type: str) -> str:
    """Derive record_type from mapped activity_type."""
    return RECORD_TYPE_BY_ACTIVITY.get(activity_type, "unknown")


def _ownership_for_activity(activity_type: str) -> str:
    if activity_type in {
        "grid_electricity",
        "natural_gas",
        "diesel",
        "third_party_transport",
    }:
        return "unknown"
    if activity_type in {
        "purchased_steel",
        "finished_goods_output",
        "scrap_output",
    }:
        return "not_applicable"
    return "unknown"


def _transport_payer_for_record_type(record_type: str) -> str:
    if record_type == "transport_activity":
        return "unknown"
    return "not_applicable"


def _rejection(
    *,
    source_row: int,
    field_name: str,
    issue_code: str,
    issue_message: str,
    uploaded_value: Any,
) -> dict[str, Any]:
    return {
        "source_row": source_row,
        "field": field_name,
        "issue_code": issue_code,
        "issue_message": issue_message,
        "uploaded_value": (
            "" if uploaded_value is None else str(uploaded_value)
        ),
    }


def _as_naive_timestamp(value: Any) -> pd.Timestamp:
    """Normalize an explicit timestamp to timezone-naive pandas form.

    Preserves naive timestamps. Converts timezone-aware values to naive via
    tz_convert(None) without inventing a new instant.
    """
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp


def build_source_document_row(
    uploaded: UploadedTable,
    metadata: IntakeMetadata,
) -> dict[str, Any]:
    """Build one canonical source-document row for the uploaded file."""
    return {
        "source_document_id": source_document_id_from_hash(uploaded.sha256),
        "file_name": uploaded.file_name,
        "document_type": "other",
        "document_date": datetime(
            metadata.document_date.year,
            metadata.document_date.month,
            metadata.document_date.day,
        ),
        "issuer": pd.NA,
        "data_origin": "company_provided",
        "is_synthetic": False,
        "source_path": pd.NA,
        "sha256": uploaded.sha256,
        "ingested_at": _as_naive_timestamp(metadata.ingested_at),
        "ingestion_run_id": metadata.intake_run_id,
        "notes": SOURCE_DOCUMENT_NOTES,
    }


def _units_compatible(activity_type: str, unit: str) -> bool:
    allowed = ACTIVITY_TYPE_UNIT_COMPATIBILITY.get(activity_type)
    if allowed is None:
        return unit in SUPPORTED_UNITS
    return unit in allowed


def build_and_validate_intake(
    uploaded: UploadedTable,
    mapping: ColumnMapping,
    metadata: IntakeMetadata,
) -> IntakeValidationResult:
    """Build canonical rows and validate without mutating the uploaded frame."""
    source_frame = uploaded.frame.copy()
    rejected: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []

    required_columns = {
        "activity_type": mapping.activity_type_column,
        "activity_value": mapping.activity_value_column,
        "unit": mapping.unit_column,
    }
    for field_name, column in required_columns.items():
        if not column or column not in source_frame.columns:
            raise IntakeError(
                ISSUE_MISSING_REQUIRED_MAPPING,
                f"Missing required mapping for {field_name}.",
            )

    if mapping.use_file_dates:
        if (
            not mapping.start_date_column
            or mapping.start_date_column not in source_frame.columns
            or not mapping.end_date_column
            or mapping.end_date_column not in source_frame.columns
        ):
            raise IntakeError(
                ISSUE_MISSING_REQUIRED_MAPPING,
                "Missing required date column mapping.",
            )
    elif mapping.period_start is None or mapping.period_end is None:
        raise IntakeError(
            ISSUE_MISSING_REQUIRED_MAPPING,
            "Reporting period start and end dates are required.",
        )

    source_doc = build_source_document_row(uploaded, metadata)
    try:
        validate_source_documents(pd.DataFrame([source_doc]))
    except (SchemaError, SchemaErrors) as exc:
        raise IntakeError(
            ISSUE_SCHEMA_VALIDATION_FAILED,
            f"Source document failed schema validation: {exc}",
        ) from exc

    for offset, (_, row) in enumerate(source_frame.iterrows()):
        # Header is row 1; first data row is 2.
        source_row = offset + 2

        raw_activity = row.get(mapping.activity_type_column)
        raw_value = row.get(mapping.activity_value_column)
        raw_unit = row.get(mapping.unit_column)

        # Skip completely empty rows.
        if (
            (raw_activity is None or str(raw_activity).strip() == "")
            and (raw_value is None or str(raw_value).strip() == "")
            and (raw_unit is None or str(raw_unit).strip() == "")
        ):
            continue

        activity_key = str(raw_activity).strip() if raw_activity is not None else ""
        mapped_activity = mapping.activity_type_value_map.get(activity_key, "")
        if not mapped_activity or mapped_activity not in ACTIVITY_TYPES:
            rejected.append(
                _rejection(
                    source_row=source_row,
                    field_name="activity_type",
                    issue_code=ISSUE_UNMAPPED_ACTIVITY_TYPE,
                    issue_message=(
                        "Activity type is not mapped to a supported value."
                    ),
                    uploaded_value=raw_activity,
                )
            )
            continue

        unit_key = str(raw_unit).strip() if raw_unit is not None else ""
        mapped_unit = mapping.unit_value_map.get(unit_key, "")
        if not mapped_unit or mapped_unit not in SUPPORTED_UNITS:
            rejected.append(
                _rejection(
                    source_row=source_row,
                    field_name="unit",
                    issue_code=ISSUE_UNMAPPED_UNIT,
                    issue_message="Unit is not mapped to a supported value.",
                    uploaded_value=raw_unit,
                )
            )
            continue

        if not _units_compatible(mapped_activity, mapped_unit):
            rejected.append(
                _rejection(
                    source_row=source_row,
                    field_name="unit",
                    issue_code=ISSUE_ACTIVITY_UNIT_MISMATCH,
                    issue_message=(
                        f"Unit {mapped_unit} is not compatible with "
                        f"activity type {mapped_activity}."
                    ),
                    uploaded_value=raw_unit,
                )
            )
            continue

        try:
            activity_value = _parse_activity_value(raw_value)
        except ValueError as exc:
            rejected.append(
                _rejection(
                    source_row=source_row,
                    field_name="activity_value",
                    issue_code=ISSUE_INVALID_ACTIVITY_VALUE,
                    issue_message=str(exc),
                    uploaded_value=raw_value,
                )
            )
            continue

        try:
            if mapping.use_file_dates:
                start_dt = _parse_date(
                    row.get(mapping.start_date_column),
                    field_name="activity_start_date",
                )
                end_dt = _parse_date(
                    row.get(mapping.end_date_column),
                    field_name="activity_end_date",
                )
            else:
                assert mapping.period_start is not None
                assert mapping.period_end is not None
                start_dt = datetime(
                    mapping.period_start.year,
                    mapping.period_start.month,
                    mapping.period_start.day,
                )
                end_dt = datetime(
                    mapping.period_end.year,
                    mapping.period_end.month,
                    mapping.period_end.day,
                )
            if end_dt < start_dt:
                raise ValueError("end date must be on or after start date")
        except (ValueError, TypeError) as exc:
            rejected.append(
                _rejection(
                    source_row=source_row,
                    field_name="activity_start_date",
                    issue_code=ISSUE_INVALID_DATE,
                    issue_message=str(exc),
                    uploaded_value=(
                        row.get(mapping.start_date_column)
                        if mapping.use_file_dates
                        else mapping.period_start
                    ),
                )
            )
            continue

        record_type = record_type_for_activity(mapped_activity)
        ownership = _ownership_for_activity(mapped_activity)
        transport_payer = _transport_payer_for_record_type(record_type)
        needs_review = True  # conservative unknowns remain

        notes: Any = pd.NA
        if mapped_activity == "other" or record_type == "other":
            notes = "User-mapped activity classified as other."

        activity_row = {
            "record_id": activity_record_id(uploaded.sha256, source_row),
            "source_document_id": source_doc["source_document_id"],
            "source_locator": source_locator(
                sheet_name=uploaded.sheet_name,
                source_row=source_row,
            ),
            "record_type": record_type,
            "activity_start_date": start_dt,
            "activity_end_date": end_dt,
            "site_id": metadata.site_id.strip() or "site_main",
            "production_process_id": pd.NA,
            "product_id": pd.NA,
            "activity_type": mapped_activity,
            "process_use": "unknown",
            "activity_value": float(activity_value),
            "unit": mapped_unit,
            "transport_payer": transport_payer,
            "ownership_control": ownership,
            "organizational_boundary_status": "unknown",
            "cbam_process_boundary_status": "unknown",
            "measurement_method": "unknown",
            "data_quality_tier": metadata.data_quality_tier,
            "human_review_status": (
                "needs_review" if needs_review else "not_required"
            ),
            "notes": notes,
        }

        try:
            validate_activity_records(pd.DataFrame([activity_row]))
        except (SchemaError, SchemaErrors) as exc:
            rejected.append(
                _rejection(
                    source_row=source_row,
                    field_name="record",
                    issue_code=ISSUE_SCHEMA_VALIDATION_FAILED,
                    issue_message=str(exc),
                    uploaded_value=activity_key,
                )
            )
            continue

        accepted.append(activity_row)

    accepted_df = pd.DataFrame(accepted)
    rejected_df = pd.DataFrame(rejected, columns=list(REJECTION_COLUMNS))
    source_docs_df = pd.DataFrame([source_doc])
    total = int(len(accepted) + len(rejected))
    return IntakeValidationResult(
        source_documents=source_docs_df,
        accepted_activities=accepted_df,
        rejected_rows=rejected_df,
        accepted_count=int(len(accepted)),
        rejected_count=int(len(rejected)),
        total_count=total,
        file_hash=uploaded.sha256,
        file_name=uploaded.file_name,
    )


def default_value_maps(
    uploaded: UploadedTable,
    mapping: ColumnMapping,
) -> tuple[dict[str, str], dict[str, str]]:
    """Build suggested activity-type and unit maps for distinct values."""
    activity_map: dict[str, str] = {}
    for value in distinct_values(uploaded.frame, mapping.activity_type_column):
        activity_map[value] = suggest_activity_type(value)
    unit_map: dict[str, str] = {}
    for value in distinct_values(uploaded.frame, mapping.unit_column):
        unit_map[value] = suggest_unit(value)
    return activity_map, unit_map
