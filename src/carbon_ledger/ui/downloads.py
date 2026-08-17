"""In-memory download helpers for audit bundles.

Uses the existing export_run_bundle writer inside a temporary directory and
returns ZIP bytes. Persistent export folders are not retained by the UI.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from carbon_ledger.export import export_run_bundle
from carbon_ledger.pipeline import PipelineRunResult


def build_audit_bundle_zip(
    result: PipelineRunResult,
    *,
    synthetic_demo: bool = False,
) -> bytes:
    """Create a ZIP of the deterministic export bundle in memory."""
    buffer = io.BytesIO()
    with TemporaryDirectory(prefix="cel_ui_export_") as tmp:
        output_dir = Path(tmp) / "bundle"
        export_run_bundle(result, output_dir, synthetic_demo=synthetic_demo)
        archive_file = zipfile.ZipFile(
            buffer,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        )
        with archive_file as archive:
            for path in sorted(output_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.name)
    return buffer.getvalue()


def build_qa_issues_csv_bytes(result: PipelineRunResult) -> bytes:
    """Serialize core QA issues to CSV bytes for download."""
    frame = result.core_qa_issues
    if frame is None:
        frame = pd.DataFrame()
    return frame.to_csv(index=False, encoding="utf-8", lineterminator="\n").encode(
        "utf-8"
    )


def audit_bundle_filename(run_id: str) -> str:
    """Return the download filename for an audit ZIP."""
    safe = "".join(
        ch if ch.isalnum() or ch in "._-" else "_"
        for ch in run_id.strip()
    )
    return f"carbon_evidence_ledger_{safe or 'run'}.zip"
