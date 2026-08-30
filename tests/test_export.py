"""Tests for Phase 7C deterministic export bundle and CLI."""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger import __main__ as cli_main
from carbon_ledger.export import export_run_bundle
from carbon_ledger.pipeline import PipelineRunResult, run_demo_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00")

CORE_CSV_NAMES = {
    "source_documents_accepted.csv",
    "source_documents_rejected.csv",
    "activity_records_accepted.csv",
    "activity_records_rejected.csv",
    "normalized_records.csv",
    "candidate_matches.csv",
    "activity_readiness.csv",
    "calculation_results.csv",
    "core_qa_issues.csv",
}


def _core_result() -> PipelineRunResult:
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="export_core",
        ingested_at=FIXED_INGESTED_AT,
    )


def _all_adapters_result() -> PipelineRunResult:
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="export_all",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_creates_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_a"
    manifest = export_run_bundle(_core_result(), output_dir)
    assert output_dir.is_dir()
    assert manifest == output_dir / "manifest.json"


def test_core_run_creates_9_core_csvs(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_core"
    export_run_bundle(_core_result(), output_dir)
    csv_names = {path.name for path in output_dir.glob("*.csv")}
    assert csv_names == CORE_CSV_NAMES


def test_manifest_exists(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_manifest"
    manifest = export_run_bundle(_core_result(), output_dir)
    assert manifest.is_file()


def test_empty_rejection_csv_has_headers(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_reject"
    export_run_bundle(_core_result(), output_dir)
    frame = pd.read_csv(output_dir / "activity_records_rejected.csv")
    assert frame.empty
    assert list(frame.columns)


def test_disabled_adapters_produce_no_optional_csv(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_disabled"
    export_run_bundle(_core_result(), output_dir)
    names = {path.name for path in output_dir.iterdir()}
    assert "ghg_evaluations.csv" not in names
    assert "cbam_evaluations.csv" not in names
    assert "ifrs_s2_evaluations.csv" not in names


def test_enabled_ghg_exports_ghg_csv(tmp_path: Path) -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="export_ghg",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
    )
    output_dir = tmp_path / "bundle_ghg"
    export_run_bundle(result, output_dir)
    assert (output_dir / "ghg_evaluations.csv").is_file()


def test_enabled_cbam_exports_cbam_csv(tmp_path: Path) -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="export_cbam",
        ingested_at=FIXED_INGESTED_AT,
        include_cbam=True,
    )
    output_dir = tmp_path / "bundle_cbam"
    export_run_bundle(result, output_dir)
    assert (output_dir / "cbam_evaluations.csv").is_file()


def test_enabled_ifrs_exports_ifrs_csv(tmp_path: Path) -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="export_ifrs",
        ingested_at=FIXED_INGESTED_AT,
        include_ifrs_s2=True,
    )
    output_dir = tmp_path / "bundle_ifrs"
    export_run_bundle(result, output_dir)
    assert (output_dir / "ifrs_s2_evaluations.csv").is_file()


def test_ifrs_dependency_also_exports_ghg_csv(tmp_path: Path) -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="export_ifrs_ghg",
        ingested_at=FIXED_INGESTED_AT,
        include_ifrs_s2=True,
    )
    output_dir = tmp_path / "bundle_ifrs_ghg"
    export_run_bundle(result, output_dir)
    assert (output_dir / "ghg_evaluations.csv").is_file()
    assert (output_dir / "cbam_evaluations.csv").exists() is False


def test_schema_version_is_1_0(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_schema"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"


def test_run_id_preserved(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_run_id"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "export_core"


def test_synthetic_demo_true(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_synthetic"
    manifest_path = export_run_bundle(
        _core_result(), output_dir, synthetic_demo=True
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["synthetic_demo"] is True


def test_synthetic_demo_false_for_company(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_company"
    manifest_path = export_run_bundle(
        _core_result(), output_dir, synthetic_demo=False
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["synthetic_demo"] is False


def test_ingested_at_preserved(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_ingested"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "2024-02-01" in manifest["ingested_at"]


def test_adapter_states_correct(tmp_path: Path) -> None:
    result = _all_adapters_result()
    output_dir = tmp_path / "bundle_adapters"
    manifest_path = export_run_bundle(result, output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["adapters"] == {
        "eu_cbam": True,
        "ghg_protocol": True,
        "ifrs_s2": True,
    }


def test_summary_counts_match_dataframes(tmp_path: Path) -> None:
    result = _all_adapters_result()
    output_dir = tmp_path / "bundle_summary"
    manifest_path = export_run_bundle(result, output_dir)
    summary = json.loads(manifest_path.read_text(encoding="utf-8"))["summary"]
    assert summary["accepted_activity_count"] == len(
        result.activity_records_accepted
    )
    assert summary["candidate_match_count"] == len(result.candidate_matches)
    assert summary["core_qa_issue_count"] == len(result.core_qa_issues)
    assert summary["ghg_evaluation_count"] == len(result.ghg_evaluations)
    assert summary["cbam_evaluation_count"] == len(result.cbam_evaluations)
    assert summary["ifrs_s2_evaluation_count"] == len(
        result.ifrs_s2_evaluations
    )


def test_baseline_calculated_count_is_1(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_calc_count"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    summary = json.loads(manifest_path.read_text(encoding="utf-8"))["summary"]
    assert summary["calculated_activity_count"] == 1


def test_baseline_qa_count_is_3(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_qa_count"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    summary = json.loads(manifest_path.read_text(encoding="utf-8"))["summary"]
    assert summary["core_qa_issue_count"] == 3


def test_csv_row_counts_match_manifest(tmp_path: Path) -> None:
    result = _all_adapters_result()
    output_dir = tmp_path / "bundle_rows"
    manifest_path = export_run_bundle(result, output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["output_files"]:
        frame = pd.read_csv(output_dir / entry["filename"])
        assert entry["row_count"] == len(frame)


def test_sha256_matches_exact_file_bytes(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_hash"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["output_files"]:
        assert entry["sha256"] == _sha256(output_dir / entry["filename"])


def test_filenames_are_relative(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_relative"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["output_files"]:
        assert "/" not in entry["filename"]
        assert "\\" not in entry["filename"]


def test_no_absolute_repository_path_in_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_abs"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    text = manifest_path.read_text(encoding="utf-8")
    assert str(REPO_ROOT) not in text


def test_no_username_home_path_in_manifest(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_home"
    manifest_path = export_run_bundle(_core_result(), output_dir)
    text = manifest_path.read_text(encoding="utf-8")
    assert str(Path.home()) not in text


def test_output_metadata_sorted(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_sorted"
    manifest_path = export_run_bundle(_all_adapters_result(), output_dir)
    filenames = [
        entry["filename"]
        for entry in json.loads(manifest_path.read_text(encoding="utf-8"))[
            "output_files"
        ]
    ]
    assert filenames == sorted(filenames)


def test_csv_output_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "bundle_det_a"
    second_dir = tmp_path / "bundle_det_b"
    result = _core_result()
    export_run_bundle(result, first_dir)
    export_run_bundle(result, second_dir)
    for name in CORE_CSV_NAMES:
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()


def test_repeated_exports_to_different_directories_have_byte_identical_csvs(
    tmp_path: Path,
) -> None:
    first = run_demo_pipeline(
        REPO_ROOT,
        run_id="repeat_export",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    second = run_demo_pipeline(
        REPO_ROOT,
        run_id="repeat_export",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    first_dir = tmp_path / "repeat_a"
    second_dir = tmp_path / "repeat_b"
    export_run_bundle(first, first_dir)
    export_run_bundle(second, second_dir)
    first_csvs = sorted(path.name for path in first_dir.glob("*.csv"))
    second_csvs = sorted(path.name for path in second_dir.glob("*.csv"))
    assert first_csvs == second_csvs
    for name in first_csvs:
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()


def test_manifests_are_equivalent(tmp_path: Path) -> None:
    first = _all_adapters_result()
    second = _all_adapters_result()
    first_dir = tmp_path / "manifest_a"
    second_dir = tmp_path / "manifest_b"
    first_manifest = export_run_bundle(first, first_dir)
    second_manifest = export_run_bundle(second, second_dir)
    assert json.loads(first_manifest.read_text(encoding="utf-8")) == json.loads(
        second_manifest.read_text(encoding="utf-8")
    )


def test_non_empty_directory_raises_file_exists_error(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_nonempty"
    output_dir.mkdir()
    (output_dir / "existing.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_run_bundle(_core_result(), output_dir)


def test_exporter_does_not_delete_existing_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_keep"
    output_dir.mkdir()
    existing = output_dir / "existing.txt"
    existing.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_run_bundle(_core_result(), output_dir)
    assert existing.read_text(encoding="utf-8") == "keep"


def test_exporter_does_not_mutate_dataframes(tmp_path: Path) -> None:
    result = _core_run_snapshot()
    before = result.calculation_results.copy(deep=True)
    export_run_bundle(result, tmp_path / "bundle_immutable")
    pd.testing.assert_frame_equal(result.calculation_results, before)


def _core_run_snapshot() -> PipelineRunResult:
    return _core_result()


def test_manifest_ends_with_newline(tmp_path: Path) -> None:
    manifest_path = export_run_bundle(_core_result(), tmp_path / "bundle_nl")
    assert manifest_path.read_bytes().endswith(b"\n")


def test_version_still_works() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--version"])
    assert exc_info.value.code == 0


def test_run_demo_requires_run_id() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["run-demo"])
    assert exc_info.value.code != 0


def test_core_only_cli_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output_dir = tmp_path / "cli_core"
    code = cli_main.main(
        [
            "run-demo",
            "--run-id",
            "cli_core",
            "--output-dir",
            str(output_dir),
        ]
    )
    assert code == 0
    assert (output_dir / "manifest.json").is_file()


def test_all_adapters_cli_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output_dir = tmp_path / "cli_all"
    code = cli_main.main(
        [
            "run-demo",
            "--run-id",
            "cli_all",
            "--output-dir",
            str(output_dir),
            "--all-adapters",
        ]
    )
    assert code == 0
    assert (output_dir / "ghg_evaluations.csv").is_file()
    assert (output_dir / "cbam_evaluations.csv").is_file()
    assert (output_dir / "ifrs_s2_evaluations.csv").is_file()


def test_ifrs_flag_generates_ghg_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output_dir = tmp_path / "cli_ifrs"
    code = cli_main.main(
        [
            "run-demo",
            "--run-id",
            "cli_ifrs",
            "--output-dir",
            str(output_dir),
            "--include-ifrs-s2",
        ]
    )
    assert code == 0
    assert (output_dir / "ifrs_s2_evaluations.csv").is_file()
    assert (output_dir / "ghg_evaluations.csv").is_file()


def test_invalid_run_id_returns_non_zero(tmp_path: Path) -> None:
    code = cli_main.main(
        [
            "run-demo",
            "--run-id",
            "../bad",
            "--output-dir",
            str(tmp_path / "cli_bad"),
        ]
    )
    assert code != 0


def test_non_empty_output_dir_returns_non_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output_dir = tmp_path / "cli_nonempty"
    output_dir.mkdir()
    (output_dir / "keep.txt").write_text("x", encoding="utf-8")
    code = cli_main.main(
        [
            "run-demo",
            "--run-id",
            "cli_nonempty",
            "--output-dir",
            str(output_dir),
        ]
    )
    assert code != 0


def test_cli_prints_bundle_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output_dir = tmp_path / "cli_print"
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_main.main(
            [
                "run-demo",
                "--run-id",
                "cli_print",
                "--output-dir",
                str(output_dir),
            ]
        )
    assert code == 0
    text = buffer.getvalue()
    assert "Bundle:" in text
    assert str(output_dir) in text
    assert "Manifest:" in text


def test_cli_does_not_print_full_dataframes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    output_dir = tmp_path / "cli_no_df"
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli_main.main(
            [
                "run-demo",
                "--run-id",
                "cli_no_df",
                "--output-dir",
                str(output_dir),
                "--all-adapters",
            ]
        )
    assert code == 0
    text = buffer.getvalue()
    assert "calculation_status" not in text
    assert "DataFrame" not in text
