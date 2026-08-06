"""Tests for Phase 6C optional IFRS S2 climate-data readiness mapping."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pandas as pd

from carbon_ledger.calculate import calculate_activity_emissions
from carbon_ledger.factors import validate_factor_registry
from carbon_ledger.ifrs_s2 import (
    evaluate_ifrs_s2_readiness,
    load_ifrs_s2_references,
    load_ifrs_s2_reporting_context,
    load_ifrs_s2_rules,
)
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
FIXED_RUN_ID = "test_run_phase6c_001"

IFRS_ONLY_OUTPUT_COLUMNS = {
    "context_id",
    "assessment_purpose",
    "reporting_period_start",
    "reporting_period_end",
    "readiness_status",
    "content_area",
    "disclosure_topic",
    "source_calculation_id",
    "source_ghg_evaluation_id",
    "available_evidence",
    "missing_data",
}

FORBIDDEN_CONCLUSION_COLUMNS = {
    "compliance_status",
    "compliance_conclusion",
    "materiality_status",
    "materiality_conclusion",
    "is_compliant",
    "is_material",
}

FORBIDDEN_CONCLUSION_STATUS_VALUES = {
    "compliant",
    "non_compliant",
    "material",
    "not_material",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_raw_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "raw"
    shutil.copytree(RAW_DIR, destination)
    return destination


def _load_ifrs_assets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return (
        load_ifrs_s2_rules(CONFIG_DIR),
        load_ifrs_s2_references(REFERENCE_DIR),
        load_ifrs_s2_reporting_context(CONFIG_DIR),
    )


def _pipeline_outputs(tmp_path: Path) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
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
    return accepted, normalized, matching, calculations, ghg, registry.emission_factors


def _baseline_ifrs_s2(tmp_path: Path) -> pd.DataFrame:
    accepted, _, _, calculations, ghg, _ = _pipeline_outputs(tmp_path)
    rules, references, context = _load_ifrs_assets()
    return evaluate_ifrs_s2_readiness(
        accepted,
        calculations,
        ghg,
        rules,
        references,
        context,
    )


def _activity(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "record_type": "emission_activity",
        "activity_type": "grid_electricity",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _calc_row(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "calculation_id": "calc_rec_test_001",
        "record_id": "rec_test_001",
        "calculation_status": "calculated",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _ghg_row(**overrides: object) -> pd.DataFrame:
    row: dict[str, object] = {
        "evaluation_id": "eval_ghg_rec_test_001",
        "record_id": "rec_test_001",
        "ghg_scope": "scope_2",
        "mapping_code": "scope2_purchased_electricity",
        "mapping_status": "mapped",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _evaluate_single(
    activity: pd.DataFrame,
    calculations: pd.DataFrame,
    ghg: pd.DataFrame,
    context: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rules, references, default_context = _load_ifrs_assets()
    if context is None:
        context = default_context
    return evaluate_ifrs_s2_readiness(
        activity,
        calculations,
        ghg,
        rules,
        references,
        context,
    )


def test_three_ifrs_references_exist() -> None:
    references = load_ifrs_s2_references(REFERENCE_DIR)
    assert len(references) == 3


def test_ifrs_s2_reference_has_effective_date_2024_01_01() -> None:
    references = load_ifrs_s2_references(REFERENCE_DIR)
    row = references.loc[
        references["reference_id"] == "ref_issb_ifrs_s2_2023"
    ].iloc[0]
    assert row["effective_from"] == "2024-01-01"


def test_ifrs_s1_reference_exists() -> None:
    references = load_ifrs_s2_references(REFERENCE_DIR)
    assert "ref_issb_ifrs_s1_2023" in set(references["reference_id"])


def test_december_2025_amendment_reference_exists() -> None:
    references = load_ifrs_s2_references(REFERENCE_DIR)
    assert "ref_issb_ifrs_s2_2025_ghg_amendments" in set(
        references["reference_id"]
    )


def test_december_2025_amendments_have_effective_date_2027_01_01() -> None:
    references = load_ifrs_s2_references(REFERENCE_DIR)
    row = references.loc[
        references["reference_id"] == "ref_issb_ifrs_s2_2025_ghg_amendments"
    ].iloc[0]
    assert row["effective_from"] == "2027-01-01"


def test_baseline_context_does_not_apply_2025_amendments() -> None:
    context = load_ifrs_s2_reporting_context(CONFIG_DIR)
    assert context.iloc[0]["amendments_2025_application_status"] == "not_applied"


def test_exactly_one_baseline_reporting_context_exists() -> None:
    context = load_ifrs_s2_reporting_context(CONFIG_DIR)
    assert len(context) == 1


def test_context_purpose_is_data_readiness_only() -> None:
    context = load_ifrs_s2_reporting_context(CONFIG_DIR)
    assert context.iloc[0]["assessment_purpose"] == "data_readiness_only"


def test_context_applicability_is_not_determined() -> None:
    context = load_ifrs_s2_reporting_context(CONFIG_DIR)
    assert context.iloc[0]["applicability_status"] == "not_determined"


def test_context_jurisdictional_requirement_is_not_assessed() -> None:
    context = load_ifrs_s2_reporting_context(CONFIG_DIR)
    assert context.iloc[0]["jurisdictional_requirement_status"] == "not_assessed"


def test_context_materiality_assessment_is_not_performed() -> None:
    context = load_ifrs_s2_reporting_context(CONFIG_DIR)
    assert context.iloc[0]["materiality_assessment_status"] == "not_performed"


def test_exactly_five_ifrs_s2_readiness_rules_exist() -> None:
    rules = load_ifrs_s2_rules(CONFIG_DIR)
    assert len(rules) == 5


def test_rule_ids_are_unique() -> None:
    rules = load_ifrs_s2_rules(CONFIG_DIR)
    assert rules["rule_id"].is_unique


def test_every_rule_references_an_existing_reference() -> None:
    rules, references, _ = _load_ifrs_assets()
    reference_ids = set(references["reference_id"])
    for reference_id in rules["reference_id"]:
        assert reference_id in reference_ids


def test_electricity_maps_to_partial_evidence(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["readiness_status"] == "partial_evidence"


def test_electricity_maps_to_metrics_and_targets(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["content_area"] == "metrics_and_targets"


def test_electricity_receives_scope_2_evidence_candidate_role(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["data_role"] == "scope_2_ghg_emissions_evidence_candidate"


def test_electricity_preserves_source_calculation_id(tmp_path: Path) -> None:
    _, _, _, calculations, _, _ = _pipeline_outputs(tmp_path / "src")
    result = _baseline_ifrs_s2(tmp_path / "eval")
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    calc_id = calculations.loc[
        calculations["record_id"] == "rec_electricity_001", "calculation_id"
    ].iloc[0]
    assert row["source_calculation_id"] == calc_id


def test_electricity_preserves_source_ghg_evaluation_id(tmp_path: Path) -> None:
    _, _, _, _, ghg, _ = _pipeline_outputs(tmp_path / "src")
    result = _baseline_ifrs_s2(tmp_path / "eval")
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    ghg_id = ghg.loc[
        ghg["record_id"] == "rec_electricity_001", "evaluation_id"
    ].iloc[0]
    assert row["source_ghg_evaluation_id"] == ghg_id


def test_electricity_is_not_described_as_fully_ready(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert row["readiness_status"] == "partial_evidence"
    assert row["rule_id"] == "ifrs_s2_scope2_electricity_partial_evidence"


def test_electricity_requires_human_review(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    assert bool(row["requires_human_review"]) is True


def test_electricity_missing_data_mentions_reporting_period_completeness(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_electricity_001"].iloc[0]
    missing = row["missing_data"].lower()
    assert "reporting-period" in missing or "reporting period" in missing


def test_natural_gas_maps_to_data_gap(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["readiness_status"] == "data_gap"


def test_natural_gas_receives_stationary_scope_1_evidence_role(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["data_role"] == "scope_1_stationary_combustion_evidence_candidate"


def test_natural_gas_remains_relevant_while_calculation_blocked(
    tmp_path: Path,
) -> None:
    _, _, _, calculations, _, _ = _pipeline_outputs(tmp_path / "calc")
    assert calculations.loc[
        calculations["record_id"] == "rec_gas_001", "calculation_status"
    ].iloc[0] == "blocked_missing_conversion"
    result = _baseline_ifrs_s2(tmp_path / "ifrs")
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert row["mapping_status"] == "mapped"


def test_natural_gas_missing_data_names_heating_value_dependency(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert "heating value" in row["missing_data"].lower()


def test_diesel_maps_to_data_gap(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["readiness_status"] == "data_gap"


def test_diesel_receives_mobile_scope_1_evidence_role(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["data_role"] == "scope_1_mobile_combustion_evidence_candidate"


def test_diesel_remains_relevant_while_calculation_blocked(
    tmp_path: Path,
) -> None:
    _, _, _, calculations, _, _ = _pipeline_outputs(tmp_path / "calc")
    assert calculations.loc[
        calculations["record_id"] == "rec_diesel_001", "calculation_status"
    ].iloc[0] == "blocked_missing_conversion"
    result = _baseline_ifrs_s2(tmp_path / "ifrs")
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert row["mapping_status"] == "mapped"


def test_diesel_missing_data_names_heating_value_dependency(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert "heating value" in row["missing_data"].lower()


def test_purchased_steel_maps_to_scope_3_category_1_evidence_candidate(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert row["data_role"] == "scope_3_category1_evidence_candidate"


def test_purchased_steel_remains_a_data_gap(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert row["readiness_status"] == "data_gap"


def test_purchased_steel_missing_data_mentions_emissions_measurement(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    missing = row["missing_data"].lower()
    assert "emissions" in missing or "estimation" in missing


def test_purchased_steel_is_not_described_as_measured_scope_3_emissions(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_steel_001"].iloc[0]
    assert "measured Scope 3" in row["prohibited_use"]


def test_finished_output_is_supporting_only(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert row["mapping_status"] == "supporting_only"
    assert row["readiness_status"] == "supporting_only"


def test_finished_output_receives_intensity_denominator_candidate_role(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert row["data_role"] == "industry_metric_or_intensity_denominator_candidate"


def test_finished_output_is_not_treated_as_emissions(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert "greenhouse gas emissions" in row["prohibited_use"].lower()


def test_finished_output_is_not_automatically_selected_as_required_metric(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    row = result.loc[result["record_id"] == "rec_output_001"].iloc[0]
    assert "automatically required" in row["prohibited_use"].lower()


def test_empty_reporting_context_requires_review(tmp_path: Path) -> None:
    accepted, _, _, calculations, ghg, _ = _pipeline_outputs(tmp_path)
    rules, references, _ = _load_ifrs_assets()
    columns = load_ifrs_s2_reporting_context(CONFIG_DIR).columns
    empty_context = pd.DataFrame(columns=columns)
    result = evaluate_ifrs_s2_readiness(
        accepted,
        calculations,
        ghg,
        rules,
        references,
        empty_context,
    )
    assert (result["mapping_status"] == "needs_review").all()
    assert (result["readiness_status"] == "data_gap").all()
    assert bool(result.iloc[0]["requires_human_review"]) is True


def test_multiple_reporting_contexts_require_review() -> None:
    rules, references, context = _load_ifrs_assets()
    duplicate = pd.concat([context, context], ignore_index=True)
    result = _evaluate_single(
        _activity(),
        _calc_row(),
        _ghg_row(),
        duplicate,
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "multiple contexts" in result.iloc[0]["rationale"].lower()


def test_invalid_reporting_context_requires_review() -> None:
    rules, references, context = _load_ifrs_assets()
    invalid = context.copy()
    invalid.loc[0, "context_id"] = ""
    result = _evaluate_single(_activity(), _calc_row(), _ghg_row(), invalid)
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "context_id" in result.iloc[0]["rationale"]


def test_explicitly_not_applicable_context_returns_not_applicable() -> None:
    rules, references, context = _load_ifrs_assets()
    not_applicable = context.copy()
    not_applicable.loc[0, "applicability_status"] = "not_applicable"
    result = _evaluate_single(
        _activity(),
        _calc_row(),
        _ghg_row(),
        not_applicable,
    )
    assert result.iloc[0]["mapping_status"] == "not_applicable"
    assert result.iloc[0]["readiness_status"] == "not_applicable"


def test_missing_calculation_result_requires_review() -> None:
    result = _evaluate_single(_activity(), pd.DataFrame(), _ghg_row())
    assert len(result) == 1
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert result.iloc[0]["readiness_status"] == "data_gap"
    assert bool(result.iloc[0]["requires_human_review"]) is True
    assert pd.isna(result.iloc[0]["source_calculation_id"])
    assert "calculation result" in result.iloc[0]["rationale"].lower()


def test_duplicate_calculation_result_requires_review() -> None:
    calculations = pd.concat([_calc_row(), _calc_row()], ignore_index=True)
    result = _evaluate_single(_activity(), calculations, _ghg_row())
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "Multiple calculation result" in result.iloc[0]["rationale"]


def test_missing_ghg_evaluation_requires_review() -> None:
    result = _evaluate_single(_activity(), _calc_row(), pd.DataFrame())
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "GHG Protocol evaluation" in result.iloc[0]["rationale"]


def test_duplicate_ghg_evaluation_requires_review() -> None:
    ghg = pd.concat([_ghg_row(), _ghg_row()], ignore_index=True)
    result = _evaluate_single(_activity(), _calc_row(), ghg)
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "Multiple GHG Protocol evaluation" in result.iloc[0]["rationale"]


def test_inconsistent_electricity_ghg_evidence_requires_review() -> None:
    result = _evaluate_single(
        _activity(activity_type="grid_electricity"),
        _calc_row(calculation_status="calculated"),
        _ghg_row(ghg_scope="scope_1", mapping_code="scope1_stationary_combustion"),
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert "inconsistent" in result.iloc[0]["rationale"].lower()


def test_unsupported_activity_remains_visible() -> None:
    result = _evaluate_single(
        _activity(activity_type="mystery_fuel", record_type="emission_activity"),
        _calc_row(record_id="rec_test_001", calculation_status="unsupported"),
        _ghg_row(record_id="rec_test_001", ghg_scope="unknown"),
    )
    assert result.iloc[0]["mapping_status"] == "needs_review"
    assert result.iloc[0]["record_id"] == "rec_test_001"
    assert "No Phase 6C IFRS S2 readiness rule" in result.iloc[0]["rationale"]


def test_exactly_one_output_row_exists_per_activity_record(tmp_path: Path) -> None:
    accepted, _, _, calculations, ghg, _ = _pipeline_outputs(tmp_path)
    rules, references, context = _load_ifrs_assets()
    result = evaluate_ifrs_s2_readiness(
        accepted,
        calculations,
        ghg,
        rules,
        references,
        context,
    )
    assert len(result) == len(accepted)
    assert result["record_id"].is_unique


def test_baseline_output_contains_five_rows(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert len(result) == 5


def test_output_ordering_is_deterministic(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert result["record_id"].tolist() == sorted(result["record_id"].tolist())


def test_repeated_evaluation_produces_identical_output(tmp_path: Path) -> None:
    first = _baseline_ifrs_s2(tmp_path / "a")
    second = _baseline_ifrs_s2(tmp_path / "b")
    pd.testing.assert_frame_equal(first, second)


def test_input_dataframes_are_not_mutated(tmp_path: Path) -> None:
    accepted, _, _, calculations, ghg, _ = _pipeline_outputs(tmp_path)
    rules, references, context = _load_ifrs_assets()
    accepted_before = accepted.copy(deep=True)
    calc_before = calculations.copy(deep=True)
    ghg_before = ghg.copy(deep=True)
    rules_before = rules.copy(deep=True)
    refs_before = references.copy(deep=True)
    context_before = context.copy(deep=True)

    evaluate_ifrs_s2_readiness(
        accepted,
        calculations,
        ghg,
        rules,
        references,
        context,
    )

    pd.testing.assert_frame_equal(accepted, accepted_before)
    pd.testing.assert_frame_equal(calculations, calc_before)
    pd.testing.assert_frame_equal(ghg, ghg_before)
    pd.testing.assert_frame_equal(rules, rules_before)
    pd.testing.assert_frame_equal(references, refs_before)
    pd.testing.assert_frame_equal(context, context_before)


def test_every_rule_based_result_preserves_rule_version(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    rule_based = result.loc[result["rule_id"].notna()]
    assert (rule_based["rule_version"] == "1.0").all()


def test_every_rule_based_result_preserves_reference_id_and_locator(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    rule_based = result.loc[result["rule_id"].notna()]
    assert rule_based["reference_id"].notna().all()
    assert rule_based["reference_locator"].astype(str).str.len().gt(0).all()


def test_every_rule_based_result_contains_allowed_and_prohibited_use(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    rule_based = result.loc[result["rule_id"].notna()]
    assert rule_based["allowed_use"].astype(str).str.len().gt(0).all()
    assert rule_based["prohibited_use"].astype(str).str.len().gt(0).all()


def test_every_baseline_result_requires_human_review(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert bool(result["requires_human_review"].all()) is True


def test_output_contains_no_calculated_kgco2e(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert "calculated_kgco2e" not in result.columns


def test_output_contains_no_calculated_tco2e(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert "calculated_tco2e" not in result.columns


def test_output_contains_no_factor_value(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert "factor_value" not in result.columns


def test_output_contains_no_ghg_scope(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert "ghg_scope" not in result.columns


def test_output_contains_no_scope3_category(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert "scope3_category" not in result.columns


def test_output_contains_no_cbam_relevance(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert "cbam_relevance" not in result.columns


def test_output_contains_no_cbam_data_role(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert "cbam_data_role" not in result.columns


def test_output_contains_no_compliance_conclusion(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    for column in FORBIDDEN_CONCLUSION_COLUMNS:
        assert column not in result.columns
    assert not set(result["mapping_status"]).intersection(
        FORBIDDEN_CONCLUSION_STATUS_VALUES
    )
    assert not set(result["readiness_status"]).intersection(
        FORBIDDEN_CONCLUSION_STATUS_VALUES
    )


def test_output_contains_no_materiality_conclusion(tmp_path: Path) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    materiality_columns = {
        "materiality_status",
        "materiality_conclusion",
        "is_material",
    }
    for column in materiality_columns:
        assert column not in result.columns
    assert not set(result["mapping_status"]).intersection(
        FORBIDDEN_CONCLUSION_STATUS_VALUES
    )
    assert not set(result["readiness_status"]).intersection(
        FORBIDDEN_CONCLUSION_STATUS_VALUES
    )


def test_core_pipeline_continues_without_calling_ifrs_s2_adapter(
    tmp_path: Path,
) -> None:
    accepted, normalized, matching, calculations, ghg, _ = _pipeline_outputs(
        tmp_path
    )

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
        for column in IFRS_ONLY_OUTPUT_COLUMNS:
            assert column not in frame.columns


def test_ifrs_s2_readiness_works_without_calling_cbam_adapter(
    tmp_path: Path,
) -> None:
    result = _baseline_ifrs_s2(tmp_path)
    assert len(result) == 5
    assert "cbam_relevance" not in result.columns
    assert "scenario_id" not in result.columns


def test_existing_raw_and_reference_files_outside_phase_6c_remain_unchanged(
    tmp_path: Path,
) -> None:
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
    _baseline_ifrs_s2(tmp_path)
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
