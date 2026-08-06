"""Tests for provenance-aware evidence ingestion."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pandas as pd

from carbon_ledger.ingest import ingest_evidence

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T12:00:00")
FIXED_RUN_ID = "test_run_phase3_001"


def _copy_raw_tree(tmp_path: Path) -> Path:
    """Copy Phase 2 raw data into a temporary directory for safe mutation."""
    destination = tmp_path / "raw"
    shutil.copytree(RAW_DIR, destination)
    return destination


def _rewrite_csv(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_baseline_phase2_data_accepts_all_five(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    assert len(result.source_documents.accepted) == 5
    assert len(result.activity_records.accepted) == 5


def test_baseline_produces_no_rejected_rows(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    assert result.source_documents.rejected.empty
    assert result.activity_records.rejected.empty


def test_accepted_source_documents_contain_hash_and_metadata(
    tmp_path: Path,
) -> None:
    raw = _copy_raw_tree(tmp_path)
    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    accepted = result.source_documents.accepted
    for _, row in accepted.iterrows():
        assert str(row["source_path"]).startswith("synthetic_documents/")
        assert len(row["sha256"]) == 64
        assert row["sha256"] == row["sha256"].lower()
        assert row["ingestion_run_id"] == FIXED_RUN_ID
        assert pd.Timestamp(row["ingested_at"]) == FIXED_INGESTED_AT


def test_accepted_results_are_deterministically_sorted(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    docs = result.source_documents.accepted["source_document_id"].tolist()
    acts = result.activity_records.accepted["record_id"].tolist()
    assert docs == sorted(docs)
    assert acts == sorted(acts)


def test_raw_repository_files_remain_unchanged(tmp_path: Path) -> None:
    before_docs = {
        path.name: _sha256_of(path)
        for path in (RAW_DIR / "synthetic_documents").glob("*.json")
    }
    before_source_csv = _sha256_of(RAW_DIR / "source_documents.csv")
    before_activity_csv = _sha256_of(RAW_DIR / "activity_records.csv")

    raw = _copy_raw_tree(tmp_path)
    ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )

    after_docs = {
        path.name: _sha256_of(path)
        for path in (RAW_DIR / "synthetic_documents").glob("*.json")
    }
    assert after_docs == before_docs
    assert _sha256_of(RAW_DIR / "source_documents.csv") == before_source_csv
    assert _sha256_of(RAW_DIR / "activity_records.csv") == before_activity_csv


def test_invalid_source_document_date_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "source_documents.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(
        "2024-01-31,Demo Taiwan Power",
        "not-a-date,Demo Taiwan Power",
        1,
    )
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.source_documents.rejected
    assert (rejected["rejection_code"] == "INVALID_DATE").any()


def test_invalid_synthetic_boolean_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "source_documents.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(",true,", ",yes,", 1)
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.source_documents.rejected
    assert (rejected["rejection_code"] == "INVALID_BOOLEAN").any()


def test_invalid_activity_date_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "activity_records.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(
        "emission_activity,2024-01-01,2024-01-31",
        "emission_activity,bad-date,2024-01-31",
        1,
    )
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.activity_records.rejected
    assert (rejected["rejection_code"] == "INVALID_DATE").any()


def test_invalid_activity_number_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "activity_records.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(",50000.0,kWh,", ",not-a-number,kWh,", 1)
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.activity_records.rejected
    assert (rejected["rejection_code"] == "INVALID_NUMBER").any()


def test_duplicate_source_document_ids_are_all_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "source_documents.csv"
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    duplicate_id = frame.loc[0, "source_document_id"]
    frame.loc[1, "source_document_id"] = duplicate_id
    frame.to_csv(csv_path, index=False)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.source_documents.rejected
    dupes = rejected[rejected["rejection_code"] == "DUPLICATE_SOURCE_DOCUMENT_ID"]
    assert len(dupes) == 2
    assert duplicate_id not in set(
        result.source_documents.accepted["source_document_id"]
    )


def test_duplicate_activity_ids_are_all_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "activity_records.csv"
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    duplicate_id = frame.loc[0, "record_id"]
    frame.loc[1, "record_id"] = duplicate_id
    frame.to_csv(csv_path, index=False)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.activity_records.rejected
    dupes = rejected[rejected["rejection_code"] == "DUPLICATE_RECORD_ID"]
    assert len(dupes) == 2


def test_missing_json_source_file_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "source_documents.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(
        "electricity_bill_2024_01.json",
        "missing_electricity_bill.json",
        1,
    )
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.source_documents.rejected
    assert (rejected["rejection_code"] == "SOURCE_FILE_NOT_FOUND").any()


def test_json_source_document_id_mismatch_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    json_path = raw / "synthetic_documents" / "electricity_bill_2024_01.json"
    payload = json_path.read_text(encoding="utf-8")
    payload = payload.replace(
        '"source_document_id": "doc_electricity_001"',
        '"source_document_id": "doc_wrong_id"',
        1,
    )
    json_path.write_text(payload, encoding="utf-8")

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.source_documents.rejected
    assert (rejected["rejection_code"] == "JSON_DOCUMENT_ID_MISMATCH").any()


def test_activity_pointing_to_missing_or_rejected_document_is_rejected(
    tmp_path: Path,
) -> None:
    raw = _copy_raw_tree(tmp_path)
    # Remove the electricity document so its source row is rejected.
    (raw / "synthetic_documents" / "electricity_bill_2024_01.json").unlink()

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.activity_records.rejected
    assert (
        rejected["rejection_code"] == "MISSING_SOURCE_DOCUMENT_REFERENCE"
    ).any()
    assert "rec_electricity_001" in set(rejected["record_id"])


def test_missing_json_locator_field_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "activity_records.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(
        "json_path:$.electricity_usage_kwh",
        "json_path:$.does_not_exist",
        1,
    )
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.activity_records.rejected
    assert (rejected["rejection_code"] == "SOURCE_FIELD_NOT_FOUND").any()


def test_json_activity_value_mismatch_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "activity_records.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(",50000.0,kWh,", ",49999.0,kWh,", 1)
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.activity_records.rejected
    assert (rejected["rejection_code"] == "SOURCE_VALUE_MISMATCH").any()


def test_unexpected_schema_value_is_rejected(tmp_path: Path) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "activity_records.csv"
    text = csv_path.read_text(encoding="utf-8")
    text = text.replace(",emission_activity,", ",not_a_valid_record_type,", 1)
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.activity_records.rejected
    assert (rejected["rejection_code"] == "SCHEMA_VALIDATION_FAILED").any()


def test_rejection_dataframes_preserve_row_number_code_and_message(
    tmp_path: Path,
) -> None:
    raw = _copy_raw_tree(tmp_path)
    csv_path = raw / "source_documents.csv"
    text = csv_path.read_text(encoding="utf-8").replace(",true,", ",maybe,", 1)
    _rewrite_csv(csv_path, text)

    result = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    rejected = result.source_documents.rejected
    assert set(rejected.columns) == {
        "record_kind",
        "row_number",
        "record_id",
        "rejection_stage",
        "rejection_code",
        "rejection_message",
    }
    assert rejected.iloc[0]["row_number"] >= 1
    assert rejected.iloc[0]["rejection_code"]
    assert rejected.iloc[0]["rejection_message"]


def test_same_inputs_same_timestamp_produce_same_order_and_hashes(
    tmp_path: Path,
) -> None:
    raw = _copy_raw_tree(tmp_path)
    first = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    second = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    assert (
        first.source_documents.accepted["source_document_id"].tolist()
        == second.source_documents.accepted["source_document_id"].tolist()
    )
    assert (
        first.source_documents.accepted["sha256"].tolist()
        == second.source_documents.accepted["sha256"].tolist()
    )
    assert (
        first.activity_records.accepted["record_id"].tolist()
        == second.activity_records.accepted["record_id"].tolist()
    )
