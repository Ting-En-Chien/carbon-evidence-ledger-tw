"""Tests for Phase 2 transparent synthetic data files."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from carbon_ledger.schemas import validate_activity_records, validate_source_documents

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
DOCS_DIR = RAW_DIR / "synthetic_documents"
SOURCE_DOCUMENTS_CSV = RAW_DIR / "source_documents.csv"
ACTIVITY_RECORDS_CSV = RAW_DIR / "activity_records.csv"

COMPANY_NAME = "Demo Fasteners Taiwan Ltd. (Synthetic)"

EXPECTED_ACTIVITY_TYPES = {
    "grid_electricity",
    "natural_gas",
    "diesel",
    "purchased_steel",
    "finished_goods_output",
}

FORBIDDEN_DERIVED_COLUMNS = {
    "calculated_tco2e",
    "calculated_kgco2e",
    "emission_factor",
    "ghg_scope",
    "scope3_category",
    "cbam_data_role",
    "cbam_relevance",
    "ifrs_s2_relevance",
}

# JSON value field pointed to by each activity source_locator
JSON_VALUE_FIELDS = {
    "rec_electricity_001": "electricity_usage_kwh",
    "rec_gas_001": "natural_gas_usage_m3",
    "rec_diesel_001": "diesel_quantity_litres",
    "rec_steel_001": "purchased_quantity_tonnes",
    "rec_output_001": "finished_goods_output_tonnes",
}


def _parse_bool_series(series: pd.Series) -> pd.Series:
    """Parse CSV boolean text into real Python/pandas booleans."""
    mapping = {"true": True, "false": False, "1": True, "0": False}
    return series.astype(str).str.strip().str.lower().map(mapping).astype(bool)


def _empty_to_na(series: pd.Series) -> pd.Series:
    """Treat blank CSV cells as missing values."""
    cleaned = series.replace("", pd.NA)
    return cleaned.where(cleaned.notna(), other=pd.NA)


def load_source_documents() -> pd.DataFrame:
    """Load and type-parse source_documents.csv for schema validation."""
    df = pd.read_csv(SOURCE_DOCUMENTS_CSV, dtype=str)
    df["document_date"] = pd.to_datetime(df["document_date"])
    df["is_synthetic"] = _parse_bool_series(df["is_synthetic"])
    if "issuer" in df.columns:
        df["issuer"] = _empty_to_na(df["issuer"])
    if "notes" in df.columns:
        df["notes"] = _empty_to_na(df["notes"])
    return df


def load_activity_records() -> pd.DataFrame:
    """Load and type-parse activity_records.csv for schema validation."""
    df = pd.read_csv(ACTIVITY_RECORDS_CSV, dtype=str)
    df["activity_start_date"] = pd.to_datetime(df["activity_start_date"])
    df["activity_end_date"] = pd.to_datetime(df["activity_end_date"])
    df["activity_value"] = df["activity_value"].astype(float)
    for column in (
        "production_process_id",
        "product_id",
        "process_use",
        "transport_payer",
        "notes",
    ):
        if column in df.columns:
            df[column] = _empty_to_na(df[column])
    return df


def _load_json_document(file_name: str) -> dict:
    path = DOCS_DIR / file_name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Row counts and schema validation
# ---------------------------------------------------------------------------


def test_source_documents_csv_has_exactly_five_rows() -> None:
    df = load_source_documents()
    assert len(df) == 5


def test_activity_records_csv_has_exactly_five_rows() -> None:
    df = load_activity_records()
    assert len(df) == 5


def test_source_documents_pass_schema() -> None:
    df = load_source_documents()
    result = validate_source_documents(df)
    assert len(result) == 5


def test_activity_records_pass_schema() -> None:
    df = load_activity_records()
    result = validate_activity_records(df)
    assert len(result) == 5


def test_every_activity_source_document_id_exists() -> None:
    sources = load_source_documents()
    activities = load_activity_records()
    known_ids = set(sources["source_document_id"])
    activity_ids = set(activities["source_document_id"])
    assert activity_ids.issubset(known_ids)


def test_every_referenced_json_document_exists() -> None:
    sources = load_source_documents()
    for file_name in sources["file_name"]:
        path = DOCS_DIR / file_name
        assert path.is_file(), f"Missing synthetic document: {path}"


def test_every_json_document_is_synthetic_and_fictional_company() -> None:
    sources = load_source_documents()
    for file_name in sources["file_name"]:
        payload = _load_json_document(file_name)
        assert payload["is_synthetic"] is True
        assert payload["company_name"] == COMPANY_NAME
        assert "fictional" in payload["disclaimer"].lower() or "synthetic" in payload[
            "disclaimer"
        ].lower()


def test_json_source_document_ids_match_csv() -> None:
    sources = load_source_documents()
    for _, row in sources.iterrows():
        payload = _load_json_document(row["file_name"])
        assert payload["source_document_id"] == row["source_document_id"]
        assert payload["document_type"] == row["document_type"]


def test_activity_values_in_json_match_csv() -> None:
    activities = load_activity_records()
    sources = load_source_documents().set_index("source_document_id")
    for _, activity in activities.iterrows():
        record_id = activity["record_id"]
        field_name = JSON_VALUE_FIELDS[record_id]
        file_name = sources.loc[activity["source_document_id"], "file_name"]
        payload = _load_json_document(file_name)
        assert float(payload[field_name]) == float(activity["activity_value"])
        assert field_name in activity["source_locator"]


def test_five_expected_activity_types_are_present() -> None:
    activities = load_activity_records()
    assert set(activities["activity_type"]) == EXPECTED_ACTIVITY_TYPES


def test_no_derived_columns_in_raw_csv_files() -> None:
    source_columns = set(pd.read_csv(SOURCE_DOCUMENTS_CSV, nrows=0).columns)
    activity_columns = set(pd.read_csv(ACTIVITY_RECORDS_CSV, nrows=0).columns)
    assert source_columns.isdisjoint(FORBIDDEN_DERIVED_COLUMNS)
    assert activity_columns.isdisjoint(FORBIDDEN_DERIVED_COLUMNS)
