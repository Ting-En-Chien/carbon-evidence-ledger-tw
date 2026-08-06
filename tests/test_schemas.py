"""Tests for source_documents and activity_records Pandera schemas."""

from __future__ import annotations

import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors

from carbon_ledger.schemas import validate_activity_records, validate_source_documents


def _valid_source_document(**overrides: object) -> dict[str, object]:
    """Build one valid pre-ingestion source_documents row.

    Omits ingestion-generated columns by default:
    source_path, sha256, ingested_at, ingestion_run_id.
    """
    row: dict[str, object] = {
        "source_document_id": "doc_electricity_001",
        "file_name": "2024-01_taipower_bill_synthetic.pdf",
        "document_type": "electricity_bill",
        "document_date": pd.Timestamp("2024-01-31"),
        "issuer": "Taiwan Power Company (synthetic)",
        "data_origin": "synthetic_generated",
        "is_synthetic": True,
        "notes": None,
    }
    row.update(overrides)
    return row


def _valid_activity_record(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "record_id": "rec_electricity_001",
        "source_document_id": "doc_electricity_001",
        "source_locator": "page 1, usage table row 3",
        "record_type": "emission_activity",
        "activity_start_date": pd.Timestamp("2024-01-01"),
        "activity_end_date": pd.Timestamp("2024-01-31"),
        "site_id": "site_twn_factory_01",
        "production_process_id": None,
        "product_id": None,
        "activity_type": "grid_electricity",
        "process_use": None,
        "activity_value": 50000.0,
        "unit": "kWh",
        "transport_payer": None,
        "ownership_control": "not_applicable",
        "organizational_boundary_status": "inside",
        "cbam_process_boundary_status": "inside",
        "measurement_method": "invoice",
        "data_quality_tier": "synthetic_test",
        "human_review_status": "not_required",
        "notes": None,
    }
    row.update(overrides)
    return row


def _source_documents_df(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _activity_records_df(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# ---------------------------------------------------------------------------
# Valid source_documents
# ---------------------------------------------------------------------------


def test_valid_source_documents_for_five_examples() -> None:
    """Five synthetic source documents support the first vertical-slice records."""
    df = _source_documents_df(
        _valid_source_document(
            source_document_id="doc_electricity_001",
            document_type="electricity_bill",
            file_name="2024-01_taipower_bill_synthetic.pdf",
        ),
        _valid_source_document(
            source_document_id="doc_gas_001",
            document_type="natural_gas_invoice",
            file_name="2024-01_gas_invoice_synthetic.pdf",
        ),
        _valid_source_document(
            source_document_id="doc_diesel_001",
            document_type="fuel_receipt",
            file_name="2024-01_diesel_receipt_synthetic.pdf",
        ),
        _valid_source_document(
            source_document_id="doc_steel_001",
            document_type="material_purchase_invoice",
            file_name="2024-01_steel_invoice_synthetic.pdf",
        ),
        _valid_source_document(
            source_document_id="doc_production_001",
            document_type="production_log",
            file_name="2024-01_production_log_synthetic.pdf",
        ),
    )
    result = validate_source_documents(df)
    assert len(result) == 5
    assert result["is_synthetic"].dtype == bool
    assert result["is_synthetic"].all()
    assert (result["data_origin"] == "synthetic_generated").all()
    assert pd.api.types.is_datetime64_any_dtype(result["document_date"])
    # Pre-ingestion frames omit ingestion-generated columns.
    for column in ("source_path", "sha256", "ingested_at", "ingestion_run_id"):
        assert column not in result.columns


def test_valid_source_documents_without_optional_ingestion_columns() -> None:
    """Rule: source_path, sha256, ingested_at, ingestion_run_id may be absent."""
    df = _source_documents_df(_valid_source_document())
    result = validate_source_documents(df)
    assert "ingested_at" not in result.columns
    assert "source_path" not in result.columns
    assert "sha256" not in result.columns
    assert "ingestion_run_id" not in result.columns


def test_valid_source_document_with_ingested_at_timestamp() -> None:
    """Rule: when present, ingested_at accepts a real pandas Timestamp."""
    df = _source_documents_df(
        _valid_source_document(
            source_path="data/raw/synthetic/bill.pdf",
            sha256="a" * 64,
            ingested_at=pd.Timestamp("2024-02-01T10:00:00"),
            ingestion_run_id="run_001",
        )
    )
    result = validate_source_documents(df)
    assert pd.api.types.is_datetime64_any_dtype(result["ingested_at"])
    assert result.iloc[0]["ingested_at"] == pd.Timestamp("2024-02-01T10:00:00")


def test_valid_source_document_with_ingested_at_nat() -> None:
    """Rule: nullable ingested_at may be pd.NaT in a datetime64[ns] column."""
    df = _source_documents_df(_valid_source_document())
    df["ingested_at"] = pd.Series([pd.NaT], dtype="datetime64[ns]")
    result = validate_source_documents(df)
    assert pd.api.types.is_datetime64_any_dtype(result["ingested_at"])
    assert pd.isna(result.iloc[0]["ingested_at"])


# ---------------------------------------------------------------------------
# Valid activity_records — five vertical-slice examples
# ---------------------------------------------------------------------------


def test_valid_factory_purchased_electricity() -> None:
    df = _activity_records_df(
        _valid_activity_record(
            record_id="rec_electricity_001",
            source_document_id="doc_electricity_001",
            activity_type="grid_electricity",
            unit="kWh",
            activity_value=50000.0,
            ownership_control="not_applicable",
            organizational_boundary_status="inside",
            cbam_process_boundary_status="inside",
            data_quality_tier="synthetic_test",
        )
    )
    result = validate_activity_records(df)
    assert result.iloc[0]["activity_type"] == "grid_electricity"
    assert pd.api.types.is_datetime64_any_dtype(result["activity_start_date"])
    assert pd.api.types.is_datetime64_any_dtype(result["activity_end_date"])


def test_valid_natural_gas_heat_treatment() -> None:
    df = _activity_records_df(
        _valid_activity_record(
            record_id="rec_gas_001",
            source_document_id="doc_gas_001",
            activity_type="natural_gas",
            process_use="heat_treatment",
            unit="m3",
            activity_value=8000.0,
            ownership_control="controlled",
            organizational_boundary_status="inside",
            cbam_process_boundary_status="inside",
            data_quality_tier="synthetic_test",
        )
    )
    result = validate_activity_records(df)
    assert result.iloc[0]["process_use"] == "heat_treatment"


def test_valid_diesel_company_vehicle() -> None:
    df = _activity_records_df(
        _valid_activity_record(
            record_id="rec_diesel_001",
            source_document_id="doc_diesel_001",
            activity_type="diesel",
            process_use="company_vehicle",
            unit="L",
            activity_value=1200.0,
            ownership_control="owned",
            organizational_boundary_status="inside",
            cbam_process_boundary_status="outside",
            data_quality_tier="synthetic_test",
        )
    )
    result = validate_activity_records(df)
    assert result.iloc[0]["cbam_process_boundary_status"] == "outside"


def test_valid_purchased_steel_wire_rod() -> None:
    df = _activity_records_df(
        _valid_activity_record(
            record_id="rec_steel_001",
            source_document_id="doc_steel_001",
            record_type="material_input",
            activity_type="purchased_steel",
            unit="t",
            activity_value=150.0,
            ownership_control="not_applicable",
            organizational_boundary_status="outside",
            cbam_process_boundary_status="not_applicable",
            measurement_method="purchase_record",
            data_quality_tier="synthetic_test",
        )
    )
    result = validate_activity_records(df)
    assert result.iloc[0]["record_type"] == "material_input"
    assert result.iloc[0]["organizational_boundary_status"] == "outside"
    assert result.iloc[0]["cbam_process_boundary_status"] == "not_applicable"


def test_valid_finished_fastener_production_output() -> None:
    df = _activity_records_df(
        _valid_activity_record(
            record_id="rec_output_001",
            source_document_id="doc_production_001",
            record_type="production_output",
            activity_type="finished_goods_output",
            unit="t",
            activity_value=95.0,
            product_id="prod_fastener_m10",
            production_process_id="proc_assembly_01",
            ownership_control="not_applicable",
            organizational_boundary_status="not_applicable",
            cbam_process_boundary_status="not_applicable",
            measurement_method="production_log",
            data_quality_tier="synthetic_test",
        )
    )
    result = validate_activity_records(df)
    assert result.iloc[0]["activity_type"] == "finished_goods_output"
    assert result.iloc[0]["cbam_process_boundary_status"] == "not_applicable"


# ---------------------------------------------------------------------------
# Invalid source_documents
# ---------------------------------------------------------------------------


def test_invalid_duplicate_source_document_id() -> None:
    """Rule: source_document_id must be unique."""
    df = _source_documents_df(
        _valid_source_document(source_document_id="doc_dup"),
        _valid_source_document(
            source_document_id="doc_dup",
            file_name="second_copy_synthetic.pdf",
        ),
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_empty_source_document_id() -> None:
    """Rule: source_document_id must be a non-empty string."""
    df = _source_documents_df(_valid_source_document(source_document_id=""))
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_synthetic_true_with_non_synthetic_origin() -> None:
    """Rule: is_synthetic=true requires data_origin=synthetic_generated."""
    df = _source_documents_df(
        _valid_source_document(is_synthetic=True, data_origin="company_provided")
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_synthetic_origin_with_synthetic_false() -> None:
    """Rule: data_origin=synthetic_generated requires is_synthetic=true."""
    df = _source_documents_df(
        _valid_source_document(is_synthetic=False, data_origin="synthetic_generated")
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_document_type_other_without_notes() -> None:
    """Rule: document_type=other requires a non-empty notes explanation."""
    df = _source_documents_df(
        _valid_source_document(document_type="other", notes=None)
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_source_document_string_date_not_coerced() -> None:
    """Rule: document_date must be datetime64[ns]; raw strings are rejected."""
    df = _source_documents_df(
        _valid_source_document(document_date="2024-01-31")
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_source_document_string_boolean_not_coerced() -> None:
    """Rule: is_synthetic must already be boolean; strings are rejected."""
    df = _source_documents_df(_valid_source_document(is_synthetic="true"))
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_source_document_ingested_at_string_not_coerced() -> None:
    """Rule: ingested_at string values are rejected when the column is present."""
    df = _source_documents_df(
        _valid_source_document(ingested_at="2024-01-31")
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


def test_invalid_source_document_unexpected_column() -> None:
    """Rule: strict schema rejects unexpected columns on source_documents."""
    row = _valid_source_document()
    row["ghg_scope"] = "scope_2"
    df = _source_documents_df(row)
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_source_documents(df)


# ---------------------------------------------------------------------------
# Invalid activity_records
# ---------------------------------------------------------------------------


def test_invalid_duplicate_record_id() -> None:
    """Rule: record_id must be unique."""
    df = _activity_records_df(
        _valid_activity_record(record_id="rec_dup"),
        _valid_activity_record(
            record_id="rec_dup",
            source_document_id="doc_gas_001",
            activity_type="natural_gas",
            process_use="heat_treatment",
            unit="m3",
            activity_value=100.0,
        ),
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_activity_value_zero() -> None:
    """Rule: activity_value must be greater than zero."""
    df = _activity_records_df(_valid_activity_record(activity_value=0.0))
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_negative_activity_value() -> None:
    """Rule: activity_value must be greater than zero."""
    df = _activity_records_df(_valid_activity_record(activity_value=-10.0))
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_activity_end_before_start() -> None:
    """Rule: activity_end_date must not be earlier than activity_start_date."""
    df = _activity_records_df(
        _valid_activity_record(
            activity_start_date=pd.Timestamp("2024-02-01"),
            activity_end_date=pd.Timestamp("2024-01-01"),
        )
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_controlled_vocabulary_value() -> None:
    """Rule: unknown controlled-vocabulary values must be rejected."""
    df = _activity_records_df(
        _valid_activity_record(record_type="emission_scope_99")
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_unsupported_unit_not_in_vocabulary() -> None:
    """Rule: unit must be in the supported-unit vocabulary."""
    df = _activity_records_df(_valid_activity_record(unit="gallon"))
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_electricity_recorded_in_litres() -> None:
    """Rule: grid_electricity must use kWh or MWh."""
    df = _activity_records_df(
        _valid_activity_record(activity_type="grid_electricity", unit="L")
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_diesel_recorded_in_kwh() -> None:
    """Rule: diesel must use L."""
    df = _activity_records_df(
        _valid_activity_record(
            activity_type="diesel",
            process_use="company_vehicle",
            unit="kWh",
            activity_value=500.0,
        )
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_unknown_boundary_without_needs_review() -> None:
    """Rule: unknown boundary fields require human_review_status=needs_review."""
    df = _activity_records_df(
        _valid_activity_record(
            cbam_process_boundary_status="unknown",
            human_review_status="not_required",
        )
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_record_type_other_without_notes() -> None:
    """Rule: record_type=other requires a non-empty notes explanation."""
    df = _activity_records_df(
        _valid_activity_record(record_type="other", notes=None)
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_unexpected_derived_column_ghg_scope() -> None:
    """Rule: strict schema rejects derived field ghg_scope."""
    row = _valid_activity_record()
    row["ghg_scope"] = "scope_2"
    df = _activity_records_df(row)
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_unexpected_derived_column_calculated_tco2e() -> None:
    """Rule: strict schema rejects derived field calculated_tco2e."""
    row = _valid_activity_record()
    row["calculated_tco2e"] = 12.5
    df = _activity_records_df(row)
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_activity_record_string_date_not_coerced() -> None:
    """Rule: activity dates must be datetime64[ns]; raw strings are rejected."""
    df = _activity_records_df(
        _valid_activity_record(
            activity_start_date="2024-01-01",
            activity_end_date="2024-01-31",
        )
    )
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)


def test_invalid_activity_record_string_numeric_not_coerced() -> None:
    """Rule: activity_value must already be numeric; strings are rejected."""
    df = _activity_records_df(_valid_activity_record(activity_value="50000"))
    with pytest.raises((SchemaError, SchemaErrors)):
        validate_activity_records(df)
