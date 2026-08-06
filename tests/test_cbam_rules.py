"""Tests for Phase 6B optional deterministic EU CBAM data-role mapping."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pandas as pd

from carbon_ledger.calculate import calculate_activity_emissions
from carbon_ledger.cbam import (
    evaluate_cbam,
    load_cbam_product_scenario,
    load_cbam_references,
    load_cbam_rules,
)
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
FIXED_RUN_ID = "test_run_phase6b_001"

CBAM_ONLY_OUTPUT_COLUMNS = {
    "scenario_id",
    "assumed_cn_code",
    "cn_classification_status",
    "annex_i_in_scope",
    "annex_ii_direct_only",
    "cbam_relevance",
    "data_role",
    "required_data",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_raw_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "raw"
    shutil.copytree(RAW_DIR, destination)
    return destination


def _load_cbam_assets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        load_cbam_rules(CONFIG_DIR),
        load_cbam_references(REFERENCE_DIR),
        load_cbam_product_scenario(CONFIG_DIR),
    )


def _accepted_activities(tmp_path: Path) -> pd.DataFrame:
    raw = _copy_raw_tree(tmp_path)
    ingestion = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    return ingestion.activity_records.accepted


def _baseline_cbam(tmp_path: Path) -> pd.DataFrame:
    activities = _accepted_activities(tmp_path)
    rules, references, scenario = _load_cbam_assets()
    return evaluate_cbam(activities, rules, references, scenario)


def _activity(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "record_type": "emission_activity",
        "activity_type": "grid_electricity",
        "process_use": "general_factory",
        "cbam_process_boundary_status": "inside",
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


def test_three_cbam_reference_records_exist() -> None:
    references = load_cbam_references(REFERENCE_DIR)
    assert len(references) == 3
    assert set(references["reference_id"]) == {
        "ref_eu_cbam_regulation_2023_956",
        "ref_eu_cbam_implementing_2025_2547",
        "ref_eu_cbam_screws_nuts_example",
    }


def test_one_product_scenario_exists() -> None:
    scenario = load_cbam_product_scenario(CONFIG_DIR)
    assert len(scenario) == 1


def test_five_cbam_rules_exist() -> None:
    rules = load_cbam_rules(CONFIG_DIR)
    assert len(rules) == 5


def test_rule_ids_are_unique() -> None:
    rules = load_cbam_rules(CONFIG_DIR)
    assert rules["rule_id"].is_unique


def test_every_rule_references_an_existing_reference() -> None:
    rules, references, _ = _load_cbam_assets()
    reference_ids = set(references["reference_id"])
    for reference_id in rules["reference_id"]:
        assert reference_id in reference_ids


def test_scenario_references_an_existing_reference() -> None:
    _, references, scenario = _load_cbam_assets()
    reference_ids = set(references["reference_id"])
    assert scenario.iloc[0]["reference_id"] in reference_ids


def test_scenario_uses_assumed_cn_code_7318() -> None:
    scenario = load_cbam_product_scenario(CONFIG_DIR)
    assert scenario.iloc[0]["assumed_cn_code"] == "7318"


def test_scenario_is_marked_assumed_for_demo() -> None:
    scenario = load_cbam_product_scenario(CONFIG_DIR)
    assert scenario.iloc[0]["cn_classification_status"] == "assumed_for_demo"


def test_scenario_requires_human_review() -> None:
    scenario = load_cbam_product_scenario(CONFIG_DIR)
    assert scenario.iloc[0]["requires_human_review"].lower() == "true"


def test_electricity_is_excluded_from_embedded_indirect_emissions(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["mapping_status"] == "excluded"
    assert row["rule_id"] == "cbam_annex2_electricity_supporting_only"


def test_electricity_remains_supporting_energy_evidence(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["cbam_relevance"] == "supporting_only"
    assert row["data_role"] == "supporting_energy_evidence"


def test_electricity_prohibited_use_mentions_corporate_scope_2(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert "Scope 2" in row["prohibited_use"]


def test_natural_gas_is_direct_emissions_activity_candidate(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["mapping_status"] == "mapped"
    assert row["cbam_relevance"] == "core_candidate"
    assert row["data_role"] == "direct_emissions_activity_candidate"


def test_natural_gas_requires_human_review(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert bool(row["requires_human_review"]) is True


def test_natural_gas_required_data_mentions_heating_value(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert "heating value" in row["required_data"].lower()


def test_natural_gas_mapping_remains_valid_when_calculation_blocked(
    tmp_path: Path,
) -> None:
    calc_statuses = _blocked_calculation_statuses(tmp_path / "calc")
    assert calc_statuses["rec_gas_001"] == "blocked_missing_conversion"
    result = _baseline_cbam(tmp_path / "cbam")
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["mapping_status"] == "mapped"
    assert row["data_role"] == "direct_emissions_activity_candidate"


def test_company_diesel_is_outside_process_boundary(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["data_role"] == "outside_process_boundary"


def test_company_diesel_is_excluded_from_cbam_embedded_emissions(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["mapping_status"] == "excluded"
    assert row["cbam_relevance"] == "excluded"
    prohibited = row["prohibited_use"]
    assert "CBAM" in prohibited or "product-process" in prohibited


def test_purchased_steel_is_only_possible_precursor_candidate(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert row["data_role"] == "possible_precursor_candidate"


def test_purchased_steel_mapping_status_is_needs_review(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert row["mapping_status"] == "needs_review"
    assert row["cbam_relevance"] == "data_gap"


def test_purchased_steel_required_data_includes_producing_installation(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert "producing installation" in row["required_data"]


def test_purchased_steel_prohibited_use_rejects_generic_scope_3_substitution(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert "Scope 3" in row["prohibited_use"]


def test_finished_output_is_product_quantity_evidence(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert row["data_role"] == "product_quantity_denominator_candidate"
    assert row["cbam_relevance"] == "supporting_only"


def test_finished_output_is_not_negative_emissions(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert "negative" in row["prohibited_use"].lower()


def test_finished_output_does_not_formally_confirm_cn_classification(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert "customs" in row["prohibited_use"].lower()


def test_unknown_cbam_process_boundary_requires_review() -> None:
    rules, references, scenario = _load_cbam_assets()
    result = evaluate_cbam(
        _activity(
            activity_type="natural_gas",
            process_use="heat_treatment",
            cbam_process_boundary_status="unknown",
        ),
        rules,
        references,
        scenario,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert result.iloc[0]["cbam_relevance"] == "data_gap"
    assert "cbam_process_boundary_status" in result.iloc[0]["rationale"]


def test_missing_process_use_requires_review() -> None:
    rules, references, scenario = _load_cbam_assets()
    result = evaluate_cbam(
        _activity(
            activity_type="natural_gas",
            process_use="",
            cbam_process_boundary_status="inside",
        ),
        rules,
        references,
        scenario,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "process_use" in result.iloc[0]["rationale"]


def test_missing_product_scenario_requires_review_without_breaking_core_pipeline(
    tmp_path: Path,
) -> None:
    activities = _accepted_activities(tmp_path)
    rules, references, _ = _load_cbam_assets()
    scenario_columns = load_cbam_product_scenario(CONFIG_DIR).columns
    empty_scenario = pd.DataFrame(columns=scenario_columns)
    result = evaluate_cbam(activities, rules, references, empty_scenario)
    assert len(result) == len(activities)
    assert (result["mapping_status"] == "needs_review").all()
    assert (result["cbam_relevance"] == "data_gap").all()
    assert bool(result.iloc[0]["requires_human_review"]) is True
    assert "explicit product" in result.iloc[0]["rationale"]


def test_multiple_product_scenarios_require_review() -> None:
    rules, references, scenario = _load_cbam_assets()
    duplicate = pd.concat([scenario, scenario], ignore_index=True)
    result = evaluate_cbam(_activity(), rules, references, duplicate)
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "multiple scenarios" in result.iloc[0]["rationale"].lower()


def test_invalid_product_scenario_requires_review() -> None:
    rules, references, scenario = _load_cbam_assets()
    invalid = scenario.copy()
    invalid.loc[0, "assumed_cn_code"] = ""
    result = evaluate_cbam(_activity(), rules, references, invalid)
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "assumed_cn_code" in result.iloc[0]["rationale"]


def test_scenario_outside_annex_i_returns_not_applicable() -> None:
    rules, references, scenario = _load_cbam_assets()
    outside = scenario.copy()
    outside.loc[0, "annex_i_in_scope"] = "false"
    outside.loc[0, "annex_ii_direct_only"] = "false"
    result = evaluate_cbam(_activity(), rules, references, outside)
    assert result.iloc[0]["mapping_status"] == "not_applicable"
    assert result.iloc[0]["cbam_relevance"] == "not_applicable"
    assert bool(result.iloc[0]["requires_human_review"]) is False


def test_unsupported_activity_remains_visible() -> None:
    rules, references, scenario = _load_cbam_assets()
    result = evaluate_cbam(
        _activity(
            activity_type="mystery_fuel",
            record_type="emission_activity",
        ),
        rules,
        references,
        scenario,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert result.iloc[0]["record_id"] == "rec_test_001"
    assert "No Phase 6B CBAM rule" in result.iloc[0]["rationale"]


def test_exactly_one_evaluation_row_per_activity(tmp_path: Path) -> None:
    activities = _accepted_activities(tmp_path)
    result = _baseline_cbam(tmp_path / "eval")
    assert len(result) == len(activities)
    assert result["record_id"].is_unique


def test_baseline_contains_five_rows(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    assert len(result) == 5


def test_output_ordering_is_deterministic(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    assert result["record_id"].tolist() == sorted(result["record_id"].tolist())


def test_repeated_evaluation_produces_identical_output(tmp_path: Path) -> None:
    first = _baseline_cbam(tmp_path / "a")
    second = _baseline_cbam(tmp_path / "b")
    pd.testing.assert_frame_equal(first, second)


def test_input_dataframes_are_not_mutated() -> None:
    rules, references, scenario = _load_cbam_assets()
    activities = _activity()
    rules_before = rules.copy(deep=True)
    refs_before = references.copy(deep=True)
    scenario_before = scenario.copy(deep=True)
    activities_before = activities.copy(deep=True)

    evaluate_cbam(activities, rules, references, scenario)

    pd.testing.assert_frame_equal(activities, activities_before)
    pd.testing.assert_frame_equal(rules, rules_before)
    pd.testing.assert_frame_equal(references, refs_before)
    pd.testing.assert_frame_equal(scenario, scenario_before)


def test_every_mapped_rule_preserves_rule_version(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    mapped = result.loc[
        result["mapping_status"].isin(["mapped", "excluded", "needs_review"])
        & result["rule_id"].notna()
    ]
    assert (mapped["rule_version"] == "1.0").all()


def test_every_result_preserves_reference_id_and_locator_where_rule_applied(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    rule_based = result.loc[result["rule_id"].notna()]
    assert rule_based["reference_id"].notna().all()
    assert rule_based["reference_locator"].astype(str).str.len().gt(0).all()


def test_every_rule_based_result_contains_allowed_and_prohibited_use(
    tmp_path: Path,
) -> None:
    result = _baseline_cbam(tmp_path)
    rule_based = result.loc[result["rule_id"].notna()]
    assert rule_based["allowed_use"].astype(str).str.len().gt(0).all()
    assert rule_based["prohibited_use"].astype(str).str.len().gt(0).all()


def test_output_contains_no_calculated_tco2e(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    assert "calculated_tco2e" not in result.columns


def test_output_contains_no_calculated_kgco2e(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    assert "calculated_kgco2e" not in result.columns


def test_output_contains_no_factor_value(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    assert "factor_value" not in result.columns


def test_output_contains_no_ghg_scope(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    assert "ghg_scope" not in result.columns


def test_output_contains_no_scope3_category(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
    assert "scope3_category" not in result.columns


def test_output_contains_no_ifrs_s2_relevance(tmp_path: Path) -> None:
    result = _baseline_cbam(tmp_path)
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
    _baseline_cbam(tmp_path)
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


def test_core_pipeline_continues_without_calling_cbam_adapter(
    tmp_path: Path,
) -> None:
    raw = _copy_raw_tree(tmp_path)
    ingestion = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    accepted = ingestion.activity_records.accepted
    normalized = normalize_activity_records(accepted)
    registry = validate_factor_registry(REFERENCE_DIR)
    activities = accepted.merge(
        normalized[["record_id", "normalized_unit", "normalization_status"]],
        on="record_id",
        how="left",
    )
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
    ghg_rules = load_ghg_protocol_rules(CONFIG_DIR)
    ghg_refs = load_ghg_protocol_references(REFERENCE_DIR)
    ghg = evaluate_ghg_protocol(accepted, ghg_rules, ghg_refs)

    assert len(accepted) == 5
    assert len(normalized) == 5
    assert len(matching.activity_readiness) == 5
    assert len(calculations) == 5
    assert len(ghg) == 5
    assert calculations.loc[
        calculations["record_id"] == "rec_electricity_001",
        "calculation_status",
    ].iloc[0] == "calculated"
    assert ghg.loc[
        ghg["record_id"] == "rec_electricity_001", "ghg_scope"
    ].iloc[0] == "scope_2"

    core_frames = (
        accepted,
        normalized,
        matching.candidate_matches,
        matching.activity_readiness,
        calculations,
        ghg,
    )
    for frame in core_frames:
        for column in CBAM_ONLY_OUTPUT_COLUMNS:
            assert column not in frame.columns
