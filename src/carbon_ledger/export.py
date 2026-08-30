"""Deterministic export bundle writer for pipeline results.

Phase 7C writes analysis artifacts only. It does not mutate pipeline results
or repository source data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from carbon_ledger.pipeline import PipelineRunResult

SCHEMA_VERSION = "1.0"

CORE_EXPORTS = (
    ("source_documents_accepted", "source_documents_accepted.csv"),
    ("source_documents_rejected", "source_documents_rejected.csv"),
    ("activity_records_accepted", "activity_records_accepted.csv"),
    ("activity_records_rejected", "activity_records_rejected.csv"),
    ("normalized_records", "normalized_records.csv"),
    ("candidate_matches", "candidate_matches.csv"),
    ("activity_readiness", "activity_readiness.csv"),
    ("calculation_results", "calculation_results.csv"),
    ("core_qa_issues", "core_qa_issues.csv"),
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_csv(frame: pd.DataFrame, path: Path) -> tuple[int, str]:
    """Write a deterministic CSV and return (row_count, sha256)."""
    frame.to_csv(
        path,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
        na_rep="",
    )
    digest = _sha256_bytes(path.read_bytes())
    return len(frame), digest


def _status_count(frame: pd.DataFrame, status: str) -> int:
    if frame.empty or "calculation_status" not in frame.columns:
        return 0
    return int((frame["calculation_status"] == status).sum())


def _build_summary(result: PipelineRunResult) -> dict[str, int]:
    return {
        "accepted_source_document_count": len(result.source_documents_accepted),
        "rejected_source_document_count": len(result.source_documents_rejected),
        "accepted_activity_count": len(result.activity_records_accepted),
        "rejected_activity_count": len(result.activity_records_rejected),
        "normalized_record_count": len(result.normalized_records),
        "candidate_match_count": len(result.candidate_matches),
        "activity_readiness_count": len(result.activity_readiness),
        "calculation_row_count": len(result.calculation_results),
        "calculated_activity_count": _status_count(
            result.calculation_results, "calculated"
        ),
        "blocked_missing_conversion_count": _status_count(
            result.calculation_results, "blocked_missing_conversion"
        ),
        "no_factor_configured_count": _status_count(
            result.calculation_results, "no_factor_configured"
        ),
        "not_emissions_activity_count": _status_count(
            result.calculation_results, "not_emissions_activity"
        ),
        "core_qa_issue_count": len(result.core_qa_issues),
        "ghg_evaluation_count": len(result.ghg_evaluations),
        "cbam_evaluation_count": len(result.cbam_evaluations),
        "ifrs_s2_evaluation_count": len(result.ifrs_s2_evaluations),
    }


def _frame_by_logical_name(
    result: PipelineRunResult,
    logical_name: str,
) -> pd.DataFrame:
    return getattr(result, logical_name)


def export_run_bundle(
    result: PipelineRunResult,
    output_directory: Path,
    *,
    synthetic_demo: bool = True,
) -> Path:
    """Export a deterministic run bundle and return the manifest path.

    ``synthetic_demo`` must reflect the analysis source/mode:
    demo fixtures → True; uploaded company analysis → False.
    Do not infer this from run_id naming.
    """
    output_dir = Path(output_directory)

    if output_dir.exists():
        if any(output_dir.iterdir()):
            raise FileExistsError(
                f"Output directory is not empty: {output_dir}"
            )
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    output_files: list[dict[str, Any]] = []

    for logical_name, filename in CORE_EXPORTS:
        frame = _frame_by_logical_name(result, logical_name)
        row_count, digest = _write_csv(frame, output_dir / filename)
        output_files.append(
            {
                "filename": filename,
                "logical_name": logical_name,
                "row_count": row_count,
                "sha256": digest,
            }
        )

    if result.include_ghg:
        row_count, digest = _write_csv(
            result.ghg_evaluations,
            output_dir / "ghg_evaluations.csv",
        )
        output_files.append(
            {
                "filename": "ghg_evaluations.csv",
                "logical_name": "ghg_evaluations",
                "row_count": row_count,
                "sha256": digest,
            }
        )

    if result.include_cbam:
        row_count, digest = _write_csv(
            result.cbam_evaluations,
            output_dir / "cbam_evaluations.csv",
        )
        output_files.append(
            {
                "filename": "cbam_evaluations.csv",
                "logical_name": "cbam_evaluations",
                "row_count": row_count,
                "sha256": digest,
            }
        )

    if result.include_ifrs_s2:
        row_count, digest = _write_csv(
            result.ifrs_s2_evaluations,
            output_dir / "ifrs_s2_evaluations.csv",
        )
        output_files.append(
            {
                "filename": "ifrs_s2_evaluations.csv",
                "logical_name": "ifrs_s2_evaluations",
                "row_count": row_count,
                "sha256": digest,
            }
        )

    output_files = sorted(output_files, key=lambda item: item["filename"])

    ingested_at = result.ingested_at
    if getattr(ingested_at, "tzinfo", None) is not None:
        ingested_at_text = ingested_at.isoformat()
    else:
        ingested_at_text = ingested_at.isoformat()

    manifest: dict[str, Any] = {
        "adapters": {
            "eu_cbam": result.include_cbam,
            "ghg_protocol": result.include_ghg,
            "ifrs_s2": result.include_ifrs_s2,
        },
        "ingested_at": ingested_at_text,
        "output_files": output_files,
        "run_id": result.run_id,
        "schema_version": SCHEMA_VERSION,
        "summary": _build_summary(result),
        "synthetic_demo": bool(synthetic_demo),
    }

    manifest_path = output_dir / "manifest.json"
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    manifest_path.write_text(payload, encoding="utf-8")
    return manifest_path
