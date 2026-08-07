"""Tests for Phase 7A framework-neutral core QA exception register."""

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
from carbon_ledger.qa import OUTPUT_COLUMNS, build_core_qa_issues, load_qa_rules

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw"
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
CONFIG_DIR = REPO_ROOT / "config"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T12:00:00")
FIXED_RUN_ID = "test_run_phase7a_001"

ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "info"}

FORBIDDEN_QA_OUTPUT_COLUMNS = {
    "ghg_scope",
    "scope3_category",
    "cbam_relevance",
    "cbam_data_role",
    "data_role",
    "readiness_status",
    "content_area",
    "disclosure_topic",
    "calculated_kgco2e",
    "calculated_tco2e",
    "factor_value",
    "compliance_status",
    "compliance_conclusion",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _copy_raw_tree(tmp_path: Path) -> Path:
    destination = tmp_path / "raw"
    shutil.copytree(RAW_DIR, destination)
    return destination


def _pipeline_outputs(tmp_path: Path) -> dict[str, object]:
    raw = _copy_raw_tree(tmp_path)
    ingestion = ingest_evidence(
        raw_directory=raw,
        ingestion_run_id=FIXED_RUN_ID,
        ingested_at=FIXED_INGESTED_AT,
    )
    accepted = ingestion.activity_records.accepted
    rejections = pd.concat(
        [
            ingestion.source_documents.rejected,
            ingestion.activity_records.rejected,
        ],
        ignore_index=True,
    )
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
    return {
        "accepted": accepted,
        "rejections": rejections,
        "normalized": normalized,
        "readiness": matching.activity_readiness,
        "calculations": calculations,
    }


def _baseline_qa(tmp_path: Path) -> pd.DataFrame:
    pipeline = _pipeline_outputs(tmp_path)
    rules = load_qa_rules(CONFIG_DIR)
    return build_core_qa_issues(
        pipeline["accepted"],
        pipeline["rejections"],
        pipeline["normalized"],
        pipeline["readiness"],
        pipeline["calculations"],
        rules,
    )


def _activity_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "source_document_id": "doc_test_001",
        "activity_type": "grid_electricity",
    }
    row.update(overrides)
    return row


def _norm_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "normalization_status": "already_canonical",
        "normalization_reason": "already canonical",
    }
    row.update(overrides)
    return row


def _ready_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "calculation_readiness": "ready",
        "blocking_dependency": pd.NA,
        "readiness_reason": "ready",
    }
    row.update(overrides)
    return row


def _calc_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "record_id": "rec_test_001",
        "calculation_status": "calculated",
        "calculation_reason": "calculated",
    }
    row.update(overrides)
    return row


def _build_from_rows(
    activities: list[dict[str, object]] | None = None,
    rejections: list[dict[str, object]] | None = None,
    normalized: list[dict[str, object]] | None = None,
    readiness: list[dict[str, object]] | None = None,
    calculations: list[dict[str, object]] | None = None,
) -> pd.DataFrame:
    rules = load_qa_rules(CONFIG_DIR)
    return build_core_qa_issues(
        pd.DataFrame(activities or [_activity_row()]),
        pd.DataFrame(rejections or []),
        pd.DataFrame(normalized or [_norm_row()]),
        pd.DataFrame(readiness or [_ready_row()]),
        pd.DataFrame(calculations or [_calc_row()]),
        rules,
    )


def test_exactly_ten_qa_rule_rows_exist() -> None:
    rules = load_qa_rules(CONFIG_DIR)
    assert len(rules) == 10


def test_qa_rule_ids_are_unique() -> None:
    rules = load_qa_rules(CONFIG_DIR)
    assert rules["rule_id"].is_unique


def test_every_rule_has_version_1_0() -> None:
    rules = load_qa_rules(CONFIG_DIR)
    assert (rules["rule_version"] == "1.0").all()


def test_every_rule_uses_an_allowed_severity() -> None:
    rules = load_qa_rules(CONFIG_DIR)
    assert set(rules["severity"]).issubset(ALLOWED_SEVERITIES)


def test_every_rule_contains_recommended_action() -> None:
    rules = load_qa_rules(CONFIG_DIR)
    assert rules["recommended_action"].astype(str).str.len().gt(0).all()


def test_every_rule_contains_allowed_and_prohibited_use() -> None:
    rules = load_qa_rules(CONFIG_DIR)
    assert rules["allowed_use"].astype(str).str.len().gt(0).all()
    assert rules["prohibited_use"].astype(str).str.len().gt(0).all()


def test_baseline_returns_exactly_three_issues(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert len(result) == 3


def test_natural_gas_creates_one_missing_conversion_issue(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    gas = result.loc[result["record_id"] == "rec_gas_001"]
    assert len(gas) == 1
    assert gas.iloc[0]["issue_code"] == "missing_conversion_dependency"


def test_natural_gas_dependency_is_preserved(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    gas = result.loc[result["record_id"] == "rec_gas_001"].iloc[0]
    assert gas["blocking_dependency"] == (
        "verified_natural_gas_heating_value_m3_to_TJ"
    )


def test_diesel_creates_one_missing_conversion_issue(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    diesel = result.loc[result["record_id"] == "rec_diesel_001"]
    assert len(diesel) == 1
    assert diesel.iloc[0]["issue_code"] == "missing_conversion_dependency"


def test_diesel_dependency_is_preserved(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    diesel = result.loc[result["record_id"] == "rec_diesel_001"].iloc[0]
    assert diesel["blocking_dependency"] == (
        "verified_diesel_heating_value_L_to_TJ"
    )


def test_purchased_steel_creates_one_no_factor_issue(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    steel = result.loc[result["record_id"] == "rec_steel_001"]
    assert len(steel) == 1
    assert steel.iloc[0]["issue_code"] == "no_factor_configured"


def test_electricity_creates_no_core_qa_issue(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert result.loc[result["record_id"] == "rec_electricity_001"].empty


def test_finished_output_creates_no_core_qa_issue(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert result.loc[result["record_id"] == "rec_output_001"].empty


def test_blocked_status_does_not_create_fake_zero_result(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    blocked = result.loc[
        result["issue_code"] == "missing_conversion_dependency"
    ]
    assert len(blocked) == 2
    for _, row in blocked.iterrows():
        assert "zero" in row["prohibited_use"].lower()


def test_one_root_cause_does_not_create_duplicate_issues(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    gas = result.loc[result["record_id"] == "rec_gas_001"]
    assert len(gas) == 1
    assert gas["issue_id"].is_unique


def test_ingestion_rejection_creates_one_issue() -> None:
    rejection = {
        "record_kind": "activity_record",
        "row_number": 3,
        "record_id": "rec_bad_001",
        "rejection_code": "INVALID_VALUE",
        "rejection_message": "bad value",
    }
    result = _build_from_rows(
        activities=[],
        rejections=[rejection],
        normalized=[],
        readiness=[],
        calculations=[],
    )
    assert len(result) == 1
    assert result.iloc[0]["issue_code"] == "ingestion_rejected"


def test_ingestion_rejection_preserves_rejection_code() -> None:
    rejection = {
        "record_kind": "activity_record",
        "row_number": 3,
        "record_id": "rec_bad_001",
        "rejection_code": "INVALID_VALUE",
        "rejection_message": "bad value",
    }
    result = _build_from_rows(
        activities=[],
        rejections=[rejection],
        normalized=[],
        readiness=[],
        calculations=[],
    )
    assert result.iloc[0]["source_status"] == "INVALID_VALUE"


def test_ingestion_rejection_preserves_rejection_message() -> None:
    rejection = {
        "record_kind": "activity_record",
        "row_number": 3,
        "record_id": "rec_bad_001",
        "rejection_code": "INVALID_VALUE",
        "rejection_message": "bad value",
    }
    result = _build_from_rows(
        activities=[],
        rejections=[rejection],
        normalized=[],
        readiness=[],
        calculations=[],
    )
    assert result.iloc[0]["source_reason"] == "bad value"


def test_blank_rejection_record_id_does_not_crash() -> None:
    rejection = {
        "record_kind": "activity_record",
        "row_number": 3,
        "record_id": "",
        "rejection_code": "INVALID_VALUE",
        "rejection_message": "bad value",
    }
    result = _build_from_rows(
        activities=[],
        rejections=[rejection],
        normalized=[],
        readiness=[],
        calculations=[],
    )
    assert len(result) == 1
    assert pd.isna(result.iloc[0]["record_id"])


def test_empty_ingestion_rejection_dataframe_is_supported(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert len(result) == 3


def test_invalid_activity_value_creates_an_issue() -> None:
    result = _build_from_rows(
        normalized=[
            _norm_row(
                normalization_status="invalid_value",
                normalization_reason="value invalid",
            )
        ],
        readiness=[_ready_row(calculation_readiness="ready")],
        calculations=[
            _calc_row(calculation_status="invalid_normalized_input")
        ],
    )
    assert result.iloc[0]["issue_code"] == "invalid_activity_value"


def test_invalid_unit_creates_an_issue() -> None:
    result = _build_from_rows(
        normalized=[
            _norm_row(
                normalization_status="invalid_unit",
                normalization_reason="unit blank",
            )
        ],
        readiness=[
            _ready_row(calculation_readiness="unsupported_activity_type")
        ],
        calculations=[
            _calc_row(calculation_status="unsupported_activity_type")
        ],
    )
    assert any(result["issue_code"] == "invalid_activity_unit")


def test_unsupported_conversion_creates_an_issue() -> None:
    result = _build_from_rows(
        normalized=[
            _norm_row(
                normalization_status="unsupported_conversion",
                normalization_reason="no conversion",
            )
        ],
        readiness=[_ready_row(calculation_readiness="no_factor_configured")],
        calculations=[_calc_row(calculation_status="no_factor_configured")],
    )
    assert result.iloc[0]["issue_code"] == "unsupported_unit_conversion"


def test_unsupported_activity_type_creates_an_issue() -> None:
    result = _build_from_rows(
        normalized=[
            _norm_row(
                normalization_status="unsupported_activity_type",
                normalization_reason="unknown type",
            )
        ],
        readiness=[
            _ready_row(calculation_readiness="unsupported_activity_type")
        ],
        calculations=[
            _calc_row(calculation_status="unsupported_activity_type")
        ],
    )
    assert len(result) == 1
    assert result.iloc[0]["issue_code"] == "unsupported_activity_type"


def test_successful_already_canonical_normalization_creates_no_issue() -> None:
    result = _build_from_rows()
    assert result.empty


def test_successful_normalized_conversion_creates_no_issue() -> None:
    result = _build_from_rows(
        normalized=[
            _norm_row(
                normalization_status="normalized",
                normalization_reason="converted",
            )
        ]
    )
    assert result.empty


def test_missing_normalization_result_creates_critical_consistency_issue() -> None:
    result = _build_from_rows(normalized=[])
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_duplicate_normalization_result_creates_critical_consistency_issue() -> None:
    result = _build_from_rows(normalized=[_norm_row(), _norm_row()])
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_missing_readiness_result_creates_critical_consistency_issue() -> None:
    result = _build_from_rows(readiness=[])
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_duplicate_readiness_result_creates_critical_consistency_issue() -> None:
    result = _build_from_rows(readiness=[_ready_row(), _ready_row()])
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_missing_calculation_result_creates_critical_consistency_issue() -> None:
    result = _build_from_rows(calculations=[])
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_duplicate_calculation_result_creates_critical_consistency_issue() -> None:
    result = _build_from_rows(calculations=[_calc_row(), _calc_row()])
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_empty_normalized_dataframe_does_not_raise_keyerror() -> None:
    result = _build_from_rows(normalized=[])
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_empty_readiness_dataframe_does_not_raise_keyerror() -> None:
    result = _build_from_rows(readiness=[])
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_empty_calculation_dataframe_does_not_raise_keyerror() -> None:
    result = _build_from_rows(calculations=[])
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_missing_record_id_column_produces_a_consistency_issue() -> None:
    rules = load_qa_rules(CONFIG_DIR)
    result = build_core_qa_issues(
        pd.DataFrame([_activity_row()]),
        pd.DataFrame(),
        pd.DataFrame({"normalization_status": ["already_canonical"]}),
        pd.DataFrame([_ready_row()]),
        pd.DataFrame([_calc_row()]),
        rules,
    )
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_orphan_normalization_result_creates_consistency_issue() -> None:
    result = _build_from_rows(
        activities=[],
        normalized=[_norm_row(record_id="rec_orphan_001")],
        readiness=[],
        calculations=[],
    )
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"
    assert "Orphan" in result.iloc[0]["source_reason"]


def test_orphan_readiness_result_creates_consistency_issue() -> None:
    result = _build_from_rows(
        activities=[],
        normalized=[],
        readiness=[_ready_row(record_id="rec_orphan_002")],
        calculations=[],
    )
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_orphan_calculation_result_creates_consistency_issue() -> None:
    result = _build_from_rows(
        activities=[],
        normalized=[],
        readiness=[],
        calculations=[_calc_row(record_id="rec_orphan_003")],
    )
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_ready_plus_calculated_is_consistent() -> None:
    result = _build_from_rows()
    assert result.empty


def test_blocked_plus_calculated_creates_critical_inconsistency_issue() -> None:
    result = _build_from_rows(
        readiness=[
            _ready_row(calculation_readiness="blocked_missing_conversion")
        ],
        calculations=[_calc_row(calculation_status="calculated")],
    )
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_no_factor_plus_calculated_creates_critical_inconsistency_issue() -> None:
    result = _build_from_rows(
        readiness=[_ready_row(calculation_readiness="no_factor_configured")],
        calculations=[_calc_row(calculation_status="calculated")],
    )
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_readiness_calculation_conflict_does_not_also_create_normal_issue() -> None:
    result = _build_from_rows(
        readiness=[
            _ready_row(calculation_readiness="blocked_missing_conversion")
        ],
        calculations=[_calc_row(calculation_status="calculated")],
    )
    assert len(result) == 1
    assert result.iloc[0]["issue_code"] == "pipeline_result_inconsistent"


def test_invalid_normalized_input_creates_a_qa_issue() -> None:
    result = _build_from_rows(
        calculations=[
            _calc_row(
                calculation_status="invalid_normalized_input",
                calculation_reason="bad normalized value",
            )
        ]
    )
    assert result.iloc[0]["issue_code"] == "invalid_normalized_input"
    assert result.iloc[0]["severity"] == "high"


def test_factor_match_inconsistency_creates_a_critical_qa_issue() -> None:
    result = _build_from_rows(
        calculations=[
            _calc_row(
                calculation_status="factor_match_inconsistent",
                calculation_reason="candidate mismatch",
            )
        ]
    )
    assert result.iloc[0]["issue_code"] == "factor_match_inconsistent"
    assert result.iloc[0]["severity"] == "critical"


def test_upstream_normalization_issue_suppresses_downstream_invalid_input() -> None:
    result = _build_from_rows(
        normalized=[
            _norm_row(
                normalization_status="invalid_value",
                normalization_reason="bad value",
            )
        ],
        calculations=[
            _calc_row(calculation_status="invalid_normalized_input")
        ],
    )
    assert len(result) == 1
    assert result.iloc[0]["issue_code"] == "invalid_activity_value"


def test_issue_ids_are_unique(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert result["issue_id"].is_unique


def test_issue_ids_are_deterministic(tmp_path: Path) -> None:
    first = _baseline_qa(tmp_path / "a")
    second = _baseline_qa(tmp_path / "b")
    assert first["issue_id"].tolist() == second["issue_id"].tolist()


def test_repeated_evaluation_produces_identical_output(tmp_path: Path) -> None:
    first = _baseline_qa(tmp_path / "a")
    second = _baseline_qa(tmp_path / "b")
    pd.testing.assert_frame_equal(first, second)


def test_output_ordering_follows_severity_priority() -> None:
    result = _build_from_rows(
        activities=[
            _activity_row(record_id="rec_a"),
            _activity_row(record_id="rec_b"),
        ],
        normalized=[
            _norm_row(record_id="rec_a"),
            _norm_row(record_id="rec_b"),
        ],
        readiness=[
            _ready_row(
                record_id="rec_a",
                calculation_readiness="blocked_missing_conversion",
            ),
            _ready_row(record_id="rec_b", calculation_readiness="ready"),
        ],
        calculations=[
            _calc_row(
                record_id="rec_a",
                calculation_status="blocked_missing_conversion",
            ),
            _calc_row(
                record_id="rec_b",
                calculation_status="factor_match_inconsistent",
            ),
        ],
    )
    assert result.iloc[0]["severity"] == "critical"
    assert result.iloc[1]["severity"] == "high"


def test_output_ordering_is_deterministic(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert result["issue_id"].tolist() == sorted(
        result["issue_id"].tolist(),
        key=lambda issue_id: (
            0 if "missing_conversion" in issue_id or "no_factor" in issue_id else 1,
            issue_id,
        ),
    )
    first = _baseline_qa(tmp_path / "x")
    second = _baseline_qa(tmp_path / "y")
    assert first["issue_id"].tolist() == second["issue_id"].tolist()


def test_inputs_are_not_mutated(tmp_path: Path) -> None:
    pipeline = _pipeline_outputs(tmp_path)
    rules = load_qa_rules(CONFIG_DIR)
    before = {
        "accepted": pipeline["accepted"].copy(deep=True),
        "rejections": pipeline["rejections"].copy(deep=True),
        "normalized": pipeline["normalized"].copy(deep=True),
        "readiness": pipeline["readiness"].copy(deep=True),
        "calculations": pipeline["calculations"].copy(deep=True),
        "rules": rules.copy(deep=True),
    }
    build_core_qa_issues(
        pipeline["accepted"],
        pipeline["rejections"],
        pipeline["normalized"],
        pipeline["readiness"],
        pipeline["calculations"],
        rules,
    )
    pd.testing.assert_frame_equal(pipeline["accepted"], before["accepted"])
    pd.testing.assert_frame_equal(pipeline["rejections"], before["rejections"])
    pd.testing.assert_frame_equal(pipeline["normalized"], before["normalized"])
    pd.testing.assert_frame_equal(pipeline["readiness"], before["readiness"])
    pd.testing.assert_frame_equal(
        pipeline["calculations"], before["calculations"]
    )
    pd.testing.assert_frame_equal(rules, before["rules"])


def test_empty_no_issue_inputs_return_exact_output_columns() -> None:
    result = _build_from_rows(
        activities=[],
        rejections=[],
        normalized=[],
        readiness=[],
        calculations=[],
    )
    assert list(result.columns) == OUTPUT_COLUMNS
    assert result.empty


def test_every_issue_has_issue_status_open(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert (result["issue_status"] == "open").all()


def test_every_baseline_issue_requires_human_review(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert bool(result["requires_human_review"].all()) is True


def test_activity_issues_preserve_source_document_id(tmp_path: Path) -> None:
    pipeline = _pipeline_outputs(tmp_path)
    result = _baseline_qa(tmp_path / "qa")
    for _, issue in result.iterrows():
        expected = pipeline["accepted"].loc[
            pipeline["accepted"]["record_id"] == issue["record_id"],
            "source_document_id",
        ].iloc[0]
        assert issue["source_document_id"] == expected


def test_output_contains_no_ghg_scope(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "ghg_scope" not in result.columns


def test_output_contains_no_scope3_category(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "scope3_category" not in result.columns


def test_output_contains_no_cbam_relevance(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "cbam_relevance" not in result.columns


def test_output_contains_no_ifrs_s2_readiness_field(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "readiness_status" not in result.columns
    assert "content_area" not in result.columns
    assert "disclosure_topic" not in result.columns


def test_output_contains_no_calculated_kgco2e(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "calculated_kgco2e" not in result.columns


def test_output_contains_no_calculated_tco2e(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "calculated_tco2e" not in result.columns


def test_output_contains_no_factor_value(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "factor_value" not in result.columns


def test_output_contains_no_compliance_conclusion(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert "compliance_conclusion" not in result.columns
    assert "compliance_status" not in result.columns


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
    _baseline_qa(tmp_path)
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


def test_core_qa_register_works_without_framework_adapters(tmp_path: Path) -> None:
    result = _baseline_qa(tmp_path)
    assert len(result) == 3
    for column in FORBIDDEN_QA_OUTPUT_COLUMNS:
        assert column not in result.columns
