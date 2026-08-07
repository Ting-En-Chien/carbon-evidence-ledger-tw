"""Command-line entry point for the carbon_ledger package.

Examples:

    python -m carbon_ledger --version

    python -m carbon_ledger run-demo --run-id portfolio_demo --all-adapters
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from carbon_ledger import __version__
from carbon_ledger.export import export_run_bundle
from carbon_ledger.pipeline import run_demo_pipeline, validate_run_id

DEFAULT_INGESTED_AT = "2024-02-01T00:00:00Z"


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="carbon_ledger",
        description=(
            "Carbon Evidence Ledger for Taiwanese Exporters — "
            "reproducible evidence pipeline and export runner."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="Print the package version and exit.",
    )

    subparsers = parser.add_subparsers(dest="command")
    run_demo = subparsers.add_parser(
        "run-demo",
        help="Run the reproducible synthetic demo pipeline and export a bundle.",
    )
    run_demo.add_argument(
        "--run-id",
        required=True,
        help="Safe run identifier used for ingestion and the output folder.",
    )
    run_demo.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Default: outputs/<run-id>",
    )
    run_demo.add_argument(
        "--ingested-at",
        default=DEFAULT_INGESTED_AT,
        help=(
            "Explicit ingestion timestamp for reproducibility. "
            f"Default: {DEFAULT_INGESTED_AT}"
        ),
    )
    run_demo.add_argument(
        "--include-ghg",
        action="store_true",
        help="Enable the optional GHG Protocol adapter.",
    )
    run_demo.add_argument(
        "--include-cbam",
        action="store_true",
        help="Enable the optional EU CBAM adapter.",
    )
    run_demo.add_argument(
        "--include-ifrs-s2",
        action="store_true",
        help="Enable the optional IFRS S2 readiness adapter.",
    )
    run_demo.add_argument(
        "--all-adapters",
        action="store_true",
        help="Enable GHG Protocol, EU CBAM, and IFRS S2 adapters.",
    )
    return parser


def _parse_ingested_at(raw_value: str) -> pd.Timestamp:
    text = str(raw_value).strip()
    if not text:
        raise ValueError("ingested-at must be a non-empty timestamp.")
    parsed = pd.to_datetime(text, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Invalid ingested-at value: {raw_value!r}")
    # Store as timezone-naive UTC wall time for stable CSV/JSON text.
    return pd.Timestamp(parsed.tz_convert(None))


def _print_success(
    *,
    run_id: str,
    accepted_activities: int,
    calculated_activities: int,
    core_qa_issues: int,
    ghg_rows: int,
    cbam_rows: int,
    ifrs_rows: int,
    bundle_dir: Path,
    manifest_path: Path,
) -> None:
    print("Carbon Evidence Ledger demo completed.")
    print()
    print(f"Run ID: {run_id}")
    print(f"Accepted activities: {accepted_activities}")
    print(f"Calculated activities: {calculated_activities}")
    print(f"Core QA issues: {core_qa_issues}")
    print(f"GHG rows: {ghg_rows}")
    print(f"CBAM rows: {cbam_rows}")
    print(f"IFRS S2 rows: {ifrs_rows}")
    print(f"Bundle: {bundle_dir}")
    print(f"Manifest: {manifest_path}")


def _run_demo_command(args: argparse.Namespace) -> int:
    try:
        run_id = validate_run_id(args.run_id)
        ingested_at = _parse_ingested_at(args.ingested_at)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    include_ghg = bool(args.include_ghg or args.all_adapters)
    include_cbam = bool(args.include_cbam or args.all_adapters)
    include_ifrs_s2 = bool(args.include_ifrs_s2 or args.all_adapters)

    repo_root = Path.cwd()
    output_dir = (
        Path(args.output_dir)
        if args.output_dir is not None
        else repo_root / "outputs" / run_id
    )

    try:
        result = run_demo_pipeline(
            repo_root,
            run_id=run_id,
            ingested_at=ingested_at,
            include_ghg=include_ghg,
            include_cbam=include_cbam,
            include_ifrs_s2=include_ifrs_s2,
        )
        manifest_path = export_run_bundle(result, output_dir)
    except FileExistsError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    calculated = 0
    if (
        not result.calculation_results.empty
        and "calculation_status" in result.calculation_results.columns
    ):
        calculated = int(
            (result.calculation_results["calculation_status"] == "calculated").sum()
        )

    _print_success(
        run_id=result.run_id,
        accepted_activities=len(result.activity_records_accepted),
        calculated_activities=calculated,
        core_qa_issues=len(result.core_qa_issues),
        ghg_rows=len(result.ghg_evaluations),
        cbam_rows=len(result.cbam_evaluations),
        ifrs_rows=len(result.ifrs_s2_evaluations),
        bundle_dir=output_dir,
        manifest_path=manifest_path,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested command."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run-demo":
        return _run_demo_command(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
