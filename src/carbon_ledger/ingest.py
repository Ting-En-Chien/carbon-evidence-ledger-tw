"""Provenance-aware evidence ingestion for raw source documents and activities.

Phase 3 reads raw CSV/JSON evidence, parses values explicitly, validates with
existing Pandera schemas, links activities to documents, and computes SHA-256
hashes. It does not calculate emissions or apply framework mappings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pandera.errors import SchemaError, SchemaErrors

from carbon_ledger.provenance import (
    compute_sha256,
    extract_top_level_json_value,
    load_json_document,
    resolve_source_file,
)
from carbon_ledger.schemas import (
    validate_activity_records,
    validate_source_documents,
)

REJECTION_COLUMNS = [
    "record_kind",
    "row_number",
    "record_id",
    "rejection_stage",
    "rejection_code",
    "rejection_message",
]

TRUE_VALUES = {"true"}
FALSE_VALUES = {"false"}

SOURCE_OPTIONAL_TEXT_COLUMNS = ("issuer", "notes")
ACTIVITY_OPTIONAL_TEXT_COLUMNS = (
    "production_process_id",
    "product_id",
    "process_use",
    "transport_payer",
    "notes",
)

NUMERIC_COMPARE_TOLERANCE = 1e-9


@dataclass
class TableIngestionResult:
    """Accepted and rejected rows for one table."""

    accepted: pd.DataFrame
    rejected: pd.DataFrame


@dataclass
class EvidenceIngestionResult:
    """Full evidence-ingestion outcome for documents and activities."""

    source_documents: TableIngestionResult
    activity_records: TableIngestionResult


def _empty_rejection_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=REJECTION_COLUMNS)


def _sort_rejections(rejected: pd.DataFrame) -> pd.DataFrame:
    if rejected.empty:
        return _empty_rejection_frame()
    return (
        rejected.sort_values(["row_number", "rejection_code"], kind="mergesort")
        .reset_index(drop=True)
    )


def _rejection_row(
    *,
    record_kind: str,
    row_number: int,
    record_id: str,
    rejection_stage: str,
    rejection_code: str,
    rejection_message: str,
) -> dict[str, Any]:
    return {
        "record_kind": record_kind,
        "row_number": row_number,
        "record_id": record_id,
        "rejection_stage": rejection_stage,
        "rejection_code": rejection_code,
        "rejection_message": rejection_message,
    }


def _blank_to_missing(value: Any) -> Any:
    if value is None:
        return pd.NA
    text = str(value).strip()
    if text == "":
        return pd.NA
    return text


def _parse_strict_bool(raw_value: Any) -> bool:
    if raw_value is None:
        raise ValueError("Boolean value is missing.")
    text = str(raw_value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    raise ValueError(
        f"Invalid boolean {raw_value!r}. Only 'true' or 'false' are accepted."
    )


def _parse_datetime(raw_value: Any, field_name: str) -> pd.Timestamp:
    if raw_value is None or str(raw_value).strip() == "":
        raise ValueError(f"{field_name} is missing.")
    text = str(raw_value).strip()
    parsed = pd.to_datetime(text, errors="coerce", utc=False)
    if pd.isna(parsed):
        raise ValueError(f"Invalid date for {field_name}: {raw_value!r}")
    return pd.Timestamp(parsed)


def _parse_finite_float(raw_value: Any) -> float:
    if raw_value is None or str(raw_value).strip() == "":
        raise ValueError("activity_value is missing.")
    try:
        number = float(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid number for activity_value: {raw_value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(
            f"activity_value must be a finite number, got: {raw_value!r}"
        )
    return number


def _values_match(json_value: Any, activity_value: float) -> bool:
    try:
        json_number = float(json_value)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(json_number):
        return False
    return math.isclose(
        json_number,
        float(activity_value),
        rel_tol=NUMERIC_COMPARE_TOLERANCE,
        abs_tol=NUMERIC_COMPARE_TOLERANCE,
    )


def _validate_single_source_row(row: dict[str, Any]) -> None:
    frame = pd.DataFrame([row])
    validate_source_documents(frame)


def _validate_single_activity_row(row: dict[str, Any]) -> None:
    frame = pd.DataFrame([row])
    validate_activity_records(frame)


def _parse_source_document_row(raw_row: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "source_document_id": str(raw_row.get("source_document_id", "")).strip(),
        "file_name": str(raw_row.get("file_name", "")).strip(),
        "document_type": str(raw_row.get("document_type", "")).strip(),
        "document_date": _parse_datetime(
            raw_row.get("document_date"), "document_date"
        ),
        "data_origin": str(raw_row.get("data_origin", "")).strip(),
        "is_synthetic": _parse_strict_bool(raw_row.get("is_synthetic")),
    }
    for column in SOURCE_OPTIONAL_TEXT_COLUMNS:
        if column in raw_row:
            parsed[column] = _blank_to_missing(raw_row.get(column))
    return parsed


def _parse_activity_record_row(raw_row: dict[str, Any]) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "record_id": str(raw_row.get("record_id", "")).strip(),
        "source_document_id": str(raw_row.get("source_document_id", "")).strip(),
        "source_locator": str(raw_row.get("source_locator", "")).strip(),
        "record_type": str(raw_row.get("record_type", "")).strip(),
        "activity_start_date": _parse_datetime(
            raw_row.get("activity_start_date"), "activity_start_date"
        ),
        "activity_end_date": _parse_datetime(
            raw_row.get("activity_end_date"), "activity_end_date"
        ),
        "site_id": str(raw_row.get("site_id", "")).strip(),
        "activity_type": str(raw_row.get("activity_type", "")).strip(),
        "activity_value": _parse_finite_float(raw_row.get("activity_value")),
        "unit": str(raw_row.get("unit", "")).strip(),
        "ownership_control": str(raw_row.get("ownership_control", "")).strip(),
        "organizational_boundary_status": str(
            raw_row.get("organizational_boundary_status", "")
        ).strip(),
        "cbam_process_boundary_status": str(
            raw_row.get("cbam_process_boundary_status", "")
        ).strip(),
        "measurement_method": str(raw_row.get("measurement_method", "")).strip(),
        "data_quality_tier": str(raw_row.get("data_quality_tier", "")).strip(),
        "human_review_status": str(raw_row.get("human_review_status", "")).strip(),
    }
    for column in ACTIVITY_OPTIONAL_TEXT_COLUMNS:
        if column in raw_row:
            parsed[column] = _blank_to_missing(raw_row.get(column))
    return parsed


def _ingest_source_documents(
    raw_directory: Path,
    ingestion_run_id: str,
    ingested_at: pd.Timestamp,
) -> TableIngestionResult:
    csv_path = raw_directory / "source_documents.csv"
    documents_directory = raw_directory / "synthetic_documents"
    raw_df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    rejected_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for offset, raw_row in enumerate(raw_df.to_dict(orient="records")):
        row_number = offset + 1
        record_id = str(raw_row.get("source_document_id", "")).strip() or "<missing>"

        try:
            parsed = _parse_source_document_row(raw_row)
        except ValueError as exc:
            code = "INVALID_DATE"
            message = str(exc)
            lower = message.lower()
            if "boolean" in lower:
                code = "INVALID_BOOLEAN"
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="csv_parsing",
                    rejection_code=code,
                    rejection_message=message,
                )
            )
            continue

        record_id = parsed["source_document_id"] or record_id

        try:
            _validate_single_source_row(parsed)
        except (SchemaError, SchemaErrors) as exc:
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="schema_validation",
                    rejection_code="SCHEMA_VALIDATION_FAILED",
                    rejection_message=str(exc),
                )
            )
            continue

        candidates.append(
            {
                "row_number": row_number,
                "parsed": parsed,
            }
        )

    # Fail-closed uniqueness: reject every row sharing a duplicated ID.
    id_counts: dict[str, int] = {}
    for item in candidates:
        doc_id = item["parsed"]["source_document_id"]
        id_counts[doc_id] = id_counts.get(doc_id, 0) + 1

    unique_candidates: list[dict[str, Any]] = []
    for item in candidates:
        doc_id = item["parsed"]["source_document_id"]
        if id_counts[doc_id] > 1:
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=item["row_number"],
                    record_id=doc_id,
                    rejection_stage="uniqueness",
                    rejection_code="DUPLICATE_SOURCE_DOCUMENT_ID",
                    rejection_message=(
                        f"Duplicate source_document_id {doc_id!r}; "
                        "all duplicates are rejected."
                    ),
                )
            )
        else:
            unique_candidates.append(item)

    accepted_rows: list[dict[str, Any]] = []
    for item in unique_candidates:
        parsed = dict(item["parsed"])
        row_number = item["row_number"]
        doc_id = parsed["source_document_id"]
        file_name = parsed["file_name"]

        try:
            resolved = resolve_source_file(documents_directory, file_name)
        except ValueError as exc:
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=doc_id,
                    rejection_stage="evidence_file",
                    rejection_code="UNSAFE_SOURCE_PATH",
                    rejection_message=str(exc),
                )
            )
            continue

        if not resolved.is_file():
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=doc_id,
                    rejection_stage="evidence_file",
                    rejection_code="SOURCE_FILE_NOT_FOUND",
                    rejection_message=f"Source file not found: {file_name}",
                )
            )
            continue

        try:
            document = load_json_document(resolved)
        except ValueError as exc:
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=doc_id,
                    rejection_stage="json_validation",
                    rejection_code="INVALID_JSON",
                    rejection_message=str(exc),
                )
            )
            continue
        except FileNotFoundError as exc:
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=doc_id,
                    rejection_stage="evidence_file",
                    rejection_code="SOURCE_FILE_NOT_FOUND",
                    rejection_message=str(exc),
                )
            )
            continue

        json_doc_id = document.get("source_document_id")
        if json_doc_id != doc_id:
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=doc_id,
                    rejection_stage="json_validation",
                    rejection_code="JSON_DOCUMENT_ID_MISMATCH",
                    rejection_message=(
                        f"JSON source_document_id {json_doc_id!r} "
                        f"does not match CSV value {doc_id!r}."
                    ),
                )
            )
            continue

        try:
            digest = compute_sha256(resolved)
        except FileNotFoundError as exc:
            rejected_rows.append(
                _rejection_row(
                    record_kind="source_document",
                    row_number=row_number,
                    record_id=doc_id,
                    rejection_stage="evidence_file",
                    rejection_code="SOURCE_FILE_NOT_FOUND",
                    rejection_message=str(exc),
                )
            )
            continue

        parsed["source_path"] = f"synthetic_documents/{file_name}"
        parsed["sha256"] = digest
        parsed["ingested_at"] = ingested_at
        parsed["ingestion_run_id"] = ingestion_run_id
        accepted_rows.append(parsed)

    if accepted_rows:
        accepted = pd.DataFrame(accepted_rows)
        accepted = accepted.sort_values(
            "source_document_id", kind="mergesort"
        ).reset_index(drop=True)
    else:
        accepted = pd.DataFrame()

    rejected = _sort_rejections(pd.DataFrame(rejected_rows))
    return TableIngestionResult(accepted=accepted, rejected=rejected)


def _ingest_activity_records(
    raw_directory: Path,
    accepted_source_documents: pd.DataFrame,
) -> TableIngestionResult:
    csv_path = raw_directory / "activity_records.csv"
    documents_directory = raw_directory / "synthetic_documents"
    raw_df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

    accepted_doc_ids = set()
    file_name_by_id: dict[str, str] = {}
    if not accepted_source_documents.empty:
        accepted_doc_ids = set(accepted_source_documents["source_document_id"])
        file_name_by_id = dict(
            zip(
                accepted_source_documents["source_document_id"],
                accepted_source_documents["file_name"],
                strict=True,
            )
        )

    rejected_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for offset, raw_row in enumerate(raw_df.to_dict(orient="records")):
        row_number = offset + 1
        record_id = str(raw_row.get("record_id", "")).strip() or "<missing>"

        try:
            parsed = _parse_activity_record_row(raw_row)
        except ValueError as exc:
            message = str(exc)
            lower = message.lower()
            if "date" in lower:
                code = "INVALID_DATE"
            elif "number" in lower or "finite" in lower or "activity_value" in lower:
                code = "INVALID_NUMBER"
            else:
                code = "INVALID_NUMBER"
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="csv_parsing",
                    rejection_code=code,
                    rejection_message=message,
                )
            )
            continue

        record_id = parsed["record_id"] or record_id

        try:
            _validate_single_activity_row(parsed)
        except (SchemaError, SchemaErrors) as exc:
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="schema_validation",
                    rejection_code="SCHEMA_VALIDATION_FAILED",
                    rejection_message=str(exc),
                )
            )
            continue

        candidates.append({"row_number": row_number, "parsed": parsed})

    id_counts: dict[str, int] = {}
    for item in candidates:
        rec_id = item["parsed"]["record_id"]
        id_counts[rec_id] = id_counts.get(rec_id, 0) + 1

    unique_candidates: list[dict[str, Any]] = []
    for item in candidates:
        rec_id = item["parsed"]["record_id"]
        if id_counts[rec_id] > 1:
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=item["row_number"],
                    record_id=rec_id,
                    rejection_stage="uniqueness",
                    rejection_code="DUPLICATE_RECORD_ID",
                    rejection_message=(
                        f"Duplicate record_id {rec_id!r}; "
                        "all duplicates are rejected."
                    ),
                )
            )
        else:
            unique_candidates.append(item)

    accepted_rows: list[dict[str, Any]] = []
    for item in unique_candidates:
        parsed = dict(item["parsed"])
        row_number = item["row_number"]
        record_id = parsed["record_id"]
        source_document_id = parsed["source_document_id"]

        if source_document_id not in accepted_doc_ids:
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="foreign_key",
                    rejection_code="MISSING_SOURCE_DOCUMENT_REFERENCE",
                    rejection_message=(
                        f"source_document_id {source_document_id!r} is missing "
                        "from accepted source documents."
                    ),
                )
            )
            continue

        file_name = file_name_by_id[source_document_id]
        try:
            resolved = resolve_source_file(documents_directory, file_name)
            document = load_json_document(resolved)
        except ValueError as exc:
            message = str(exc).lower()
            if "unsafe" in message or "traversal" in message:
                code = "UNSAFE_SOURCE_PATH"
                stage = "evidence_file"
            elif "invalid json" in message:
                code = "INVALID_JSON"
                stage = "json_validation"
            else:
                code = "SOURCE_FILE_NOT_FOUND"
                stage = "evidence_file"
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage=stage,
                    rejection_code=code,
                    rejection_message=str(exc),
                )
            )
            continue
        except FileNotFoundError as exc:
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="evidence_file",
                    rejection_code="SOURCE_FILE_NOT_FOUND",
                    rejection_message=str(exc),
                )
            )
            continue

        try:
            json_value = extract_top_level_json_value(
                document, parsed["source_locator"]
            )
        except ValueError as exc:
            message = str(exc)
            lower = message.lower()
            if "not found" in lower:
                code = "SOURCE_FIELD_NOT_FOUND"
            else:
                code = "UNSUPPORTED_SOURCE_LOCATOR"
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="source_locator",
                    rejection_code=code,
                    rejection_message=message,
                )
            )
            continue

        if not _values_match(json_value, parsed["activity_value"]):
            rejected_rows.append(
                _rejection_row(
                    record_kind="activity_record",
                    row_number=row_number,
                    record_id=record_id,
                    rejection_stage="value_comparison",
                    rejection_code="SOURCE_VALUE_MISMATCH",
                    rejection_message=(
                        f"JSON value {json_value!r} does not match "
                        f"activity_value {parsed['activity_value']!r}."
                    ),
                )
            )
            continue

        accepted_rows.append(parsed)

    if accepted_rows:
        accepted = pd.DataFrame(accepted_rows)
        accepted = accepted.sort_values("record_id", kind="mergesort").reset_index(
            drop=True
        )
    else:
        accepted = pd.DataFrame()

    rejected = _sort_rejections(pd.DataFrame(rejected_rows))
    return TableIngestionResult(accepted=accepted, rejected=rejected)


def ingest_evidence(
    raw_directory: Path,
    ingestion_run_id: str,
    ingested_at: pd.Timestamp | None = None,
) -> EvidenceIngestionResult:
    """Ingest source documents and activity records with provenance checks.

    Raw files under ``raw_directory`` are read only and never modified.
    """
    raw_path = Path(raw_directory)
    if ingested_at is None:
        ingested_at = pd.Timestamp.now(tz="UTC").tz_convert(None)

    source_result = _ingest_source_documents(
        raw_directory=raw_path,
        ingestion_run_id=ingestion_run_id,
        ingested_at=pd.Timestamp(ingested_at),
    )
    activity_result = _ingest_activity_records(
        raw_directory=raw_path,
        accepted_source_documents=source_result.accepted,
    )
    return EvidenceIngestionResult(
        source_documents=source_result,
        activity_records=activity_result,
    )
