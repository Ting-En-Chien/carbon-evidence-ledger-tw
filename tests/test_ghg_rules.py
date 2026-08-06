"""Tests for Phase 6A deterministic GHG Protocol mapping."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pandas as pd

from carbon_ledger.calculate import calculate_activity_emissions
from carbon_ledger.factors import validate_factor_registry
from carbon_ledger.ingest import ingest_evidence
from carbon_ledger.match_factors import match_activity_factors
from carbon_ledger.normalize import normalize_activity_records
from carbon_ledger.rules import (
    evaluate_ghg_protocol,
    load_ghg_protocol_references,
    load_ghg_protocol_rules,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
CONFIG_DIR = REPO_ROOT / "config"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T12:00:00")
FIXED_RUN_ID = "test_run_phase6a_001"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_raw_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "raw"
    shutil.copytree(RAW_DIR, destination)
    return destination


def _load_rules_and_refs() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        load_ghg_protocol_rules(CONFIG_DIR),
        load_ghg_protocol_references(REFERENCE_DIR),
    )


def _accepted_activities(tmp_path: Path) -> pd.DataFrame:
    raw = _copy_raw_tree(tmp_path)
    ingestion = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    return ingestion.activity_records.accepted


def _baseline_ghg(tmp_path: Path) -> pd.DataFrame:
    activities = _accepted_activities(tmp_path)
    rules, references = _load_rules_and_refs()
    return evaluate_ghg_protocol(activities, rules, references)


def _activity(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "record_type": "emission_activity",
        "activity_type": "grid_electricity",
        "process_use": "general_factory",
        "ownership_control": "not_applicable",
        "organizational_boundary_status": "inside",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _blocked_calculation_statuses(tmp_path: Path) -> dict[str, str]:
    raw = _copy_raw_tree(tmp_path)
    ingestion = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    accepted = ingestion.activity_records.accepted
    normalized = normalize_activity_records(accepted)
    activities = accepted.merge(
        normalized[["record_id", "normalized_unit", "normalization_status"]],
        on="record_id",
        how="left",
    )
    registry = validate_factor_registry(REFERENCE_DIR)
    matching = match_activity_factors(
        activities,
        registry.emission_factors,
        registry.calculation_dependencies,
    )
    calculations = calculate_activity_emissions(
        normalized,
        matching.candidate_matches,
        matching.activity_readiness,
        registry.emission_factors,
    )
    return {
        row["record_id"]: row["calculation_status"]
        for _, row in calculations.iterrows()
    }


def test_two_official_ghg_protocol_reference_rows_exist() -> None:
    references = load_ghg_protocol_references(REFERENCE_DIR)
    assert len(references) == 2
    assert set(references["reference_id"]) == {
        "ref_ghgp_corporate_standard",
        "ref_ghgp_scope3_standard",
    }


def test_five_versioned_ghg_rule_rows_exist() -> None:
    rules = load_ghg_protocol_rules(CONFIG_DIR)
    assert len(rules) == 5


def test_every_rule_references_an_existing_reference() -> None:
    rules, references = _load_rules_and_refs()
    reference_ids = set(references["reference_id"])
    for reference_id in rules["reference_id"]:
        assert reference_id in reference_ids


def test_rule_ids_are_unique() -> None:
    rules = load_ghg_protocol_rules(CONFIG_DIR)
    assert rules["rule_id"].is_unique


def test_electricity_maps_to_scope_2(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["mapping_status"] == "mapped"
    assert row["ghg_scope"] == "scope_2"


def test_electricity_uses_purchased_electricity_rule(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["rule_id"] == "ghg_scope2_purchased_electricity"
    assert row["mapping_code"] == "scope2_purchased_electricity"


def test_natural_gas_maps_to_scope_1_stationary(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["mapping_status"] == "mapped"
    assert row["ghg_scope"] == "scope_1"
    assert row["mapping_code"] == "scope1_stationary_combustion"


def test_natural_gas_remains_scope_1_when_calculation_blocked(
    tmp_path: Path,
) -> None:
    calc_statuses = _blocked_calculation_statuses(tmp_path / "calc")
    assert calc_statuses["rec_gas_001"] == "blocked_missing_conversion"
    result = _baseline_ghg(tmp_path / "ghg")
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["ghg_scope"] == "scope_1"


def test_diesel_maps_to_scope_1_mobile(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["mapping_status"] == "mapped"
    assert row["ghg_scope"] == "scope_1"
    assert row["mapping_code"] == "scope1_mobile_combustion"


def test_diesel_remains_scope_1_when_calculation_blocked(tmp_path: Path) -> None:
    calc_statuses = _blocked_calculation_statuses(tmp_path / "calc")
    assert calc_statuses["rec_diesel_001"] == "blocked_missing_conversion"
    result = _baseline_ghg(tmp_path / "ghg")
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["ghg_scope"] == "scope_1"


def test_purchased_steel_maps_to_scope_3(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert row["mapping_status"] == "mapped"
    assert row["ghg_scope"] == "scope_3"


def test_purchased_steel_maps_to_category_1(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert row["scope3_category"] == "category_1_purchased_goods_and_services"
    assert row["rule_id"] == "ghg_scope3_category1_purchased_steel"


def test_finished_output_is_not_applicable(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert row["mapping_status"] == "not_applicable"
    assert row["ghg_scope"] == "not_applicable"


def test_production_output_is_not_mapped_as_negative_emissions(
    tmp_path: Path,
) -> None:
    result = _baseline_ghg(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert "negative" in row["prohibited_use"].lower()
    assert row["ghg_scope"] == "not_applicable"


def test_unknown_activity_type_requires_review() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(activity_type="unknown"),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert result.iloc[0]["ghg_scope"] == "unknown"
    assert bool(result.iloc[0]["requires_human_review"]) is True


def test_unknown_organizational_boundary_requires_review() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(organizational_boundary_status="unknown"),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "organizational_boundary_status" in result.iloc[0]["rationale"]


def test_unknown_ownership_requires_review() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(
            activity_type="natural_gas",
            process_use="heat_treatment",
            ownership_control="unknown",
            organizational_boundary_status="inside",
        ),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "ownership_control" in result.iloc[0]["rationale"]


def test_natural_gas_controlled_source_maps_successfully() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(
            activity_type="natural_gas",
            process_use="heat_treatment",
            ownership_control="controlled",
            organizational_boundary_status="inside",
        ),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "mapped"
    assert result.iloc[0]["ghg_scope"] == "scope_1"


def test_natural_gas_third_party_source_requires_review() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(
            activity_type="natural_gas",
            process_use="heat_treatment",
            ownership_control="third_party",
            organizational_boundary_status="inside",
        ),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert result.iloc[0]["ghg_scope"] == "unknown"


def test_diesel_without_company_vehicle_requires_review() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(
            activity_type="diesel",
            process_use="general_factory",
            ownership_control="owned",
            organizational_boundary_status="inside",
        ),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"


def test_direct_emission_activity_outside_boundary() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(
            activity_type="grid_electricity",
            organizational_boundary_status="outside",
        ),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "outside_boundary"
    assert result.iloc[0]["ghg_scope"] == "not_applicable"
    assert bool(result.iloc[0]["requires_human_review"]) is False


def test_unsupported_activity_remains_visible() -> None:
    rules, references = _load_rules_and_refs()
    result = evaluate_ghg_protocol(
        _activity(activity_type="mystery_fuel", record_type="emission_activity"),
        rules,
        references,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert result.iloc[0]["record_id"] == "rec_test_001"
    assert "No Phase 6A GHG Protocol rule" in result.iloc[0]["rationale"]


def test_exactly_one_result_row_per_activity(tmp_path: Path) -> None:
    activities = _accepted_activities(tmp_path)
    result = _baseline_ghg(tmp_path / "eval")
    assert len(result) == len(activities)
    assert result["record_id"].is_unique


def test_baseline_output_contains_five_rows(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    assert len(result) == 5


def test_output_ordering_is_deterministic(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    assert result["record_id"].tolist() == sorted(result["record_id"].tolist())


def test_repeated_evaluation_produces_identical_output(tmp_path: Path) -> None:
    first = _baseline_ghg(tmp_path / "a")
    second = _baseline_ghg(tmp_path / "b")
    pd.testing.assert_frame_equal(first, second)


def test_input_dataframes_are_not_mutated() -> None:
    rules, references = _load_rules_and_refs()
    activities = _activity()
    rules_before = rules.copy(deep=True)
    refs_before = references.copy(deep=True)
    activities_before = activities.copy(deep=True)

    evaluate_ghg_protocol(activities, rules, references)

    pd.testing.assert_frame_equal(activities, activities_before)
    pd.testing.assert_frame_equal(rules, rules_before)
    pd.testing.assert_frame_equal(references, refs_before)


def test_mapped_results_preserve_rule_id_and_version(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    mapped = result.loc[result["mapping_status"].isin(["mapped", "not_applicable"])]
    assert mapped["rule_id"].notna().all()
    assert (mapped["rule_version"] == "1.0").all()


def test_mapped_results_preserve_reference_id_and_locator(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    mapped = result.loc[result["mapping_status"].isin(["mapped", "not_applicable"])]
    assert mapped["reference_id"].notna().all()
    assert mapped["reference_locator"].astype(str).str.len().gt(0).all()


def test_every_result_contains_allowed_and_prohibited_use(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    assert result["allowed_use"].astype(str).str.len().gt(0).all()
    assert result["prohibited_use"].astype(str).str.len().gt(0).all()


def test_output_contains_no_calculated_tco2e(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    assert "calculated_tco2e" not in result.columns


def test_output_contains_no_cbam_data_role(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    assert "cbam_data_role" not in result.columns


def test_output_contains_no_ifrs_s2_relevance(tmp_path: Path) -> None:
    result = _baseline_ghg(tmp_path)
    assert "ifrs_s2_relevance" not in result.columns


def test_existing_raw_and_reference_files_remain_unchanged(tmp_path: Path) -> None:
    before_raw = {
        path.relative_to(RAW_DIR).as_posix(): _sha256(path)
        for path in RAW_DIR.rglob("*")
        if path.is_file()
    }
    before_ref = {
        path.relative_to(REFERENCE_DIR).as_posix(): _sha256(path)
        for path in REFERENCE_DIR.rglob("*")
        if path.is_file()
    }
    _baseline_ghg(tmp_path)
    after_raw = {
        path.relative_to(RAW_DIR).as_posix(): _sha256(path)
        for path in RAW_DIR.rglob("*")
        if path.is_file()
    }
    after_ref = {
        path.relative_to(REFERENCE_DIR).as_posix(): _sha256(path)
        for path in REFERENCE_DIR.rglob("*")
        if path.is_file()
    }
    assert after_raw == before_raw
    assert after_ref == before_ref
