#!/usr/bin/env python3
"""Build the local official company snapshot from Taiwan open data.

V1 refresh is manual:

    python scripts/build_company_snapshot.py

Runtime customer lookup never downloads. This script is the only network step.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from carbon_ledger.company_snapshot import (  # noqa: E402
    SNAPSHOT_SOURCES,
    SnapshotBuildError,
    coverage_statement_zh,
    default_snapshot_csv,
    default_snapshot_metadata,
    merge_snapshot_rows,
    normalize_source_row,
    replace_snapshot_atomically,
    require_snapshot_sources,
    snapshot_quality_report,
)

SNAPSHOT_VERSION = "2026-08-16.v1"


def _http_get_json(url: str, *, timeout: float = 60.0) -> Any:
    """Download official JSON. Prefer curl so macOS SSL stores work."""
    curl = shutil.which("curl")
    if curl:
        completed = subprocess.run(
            [
                curl,
                "-fsSL",
                "--max-time",
                str(int(timeout)),
                "-A",
                "CarbonEvidenceLedger/company-snapshot-build",
                "-H",
                "Accept: application/json",
                url,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        raw = completed.stdout
    else:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CarbonEvidenceLedger/company-snapshot-build",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
    if not raw.strip():
        return []
    return json.loads(raw)


def _load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows_from_payload(
    payload: Any,
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    if payload is None:
        return []
    rows = payload if isinstance(payload, list) else [payload]
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = normalize_source_row(
            row,
            listing_status=str(source["listing_status"]),
            source_id=str(source["source_id"]),
            authority=str(source["authority"]),
            dataset=str(source["dataset"]),
        )
        if item is not None:
            normalized.append(item)
    return normalized


def collect_source_rows(
    *,
    getter: Callable[[str], Any],
    from_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    collected: list[dict[str, Any]] = []
    used: list[dict[str, Any]] = []
    for source in SNAPSHOT_SOURCES:
        payload: Any = None
        if from_dir is not None:
            local = from_dir / f"{source['listing_status'].lower()}.json"
            if local.is_file():
                payload = _load_json_file(local)
            else:
                raise SnapshotBuildError(
                    "required source missing: " + str(source["listing_status"])
                )
        else:
            try:
                payload = getter(str(source["url"]))
            except SnapshotBuildError:
                raise
            except Exception as exc:
                raise SnapshotBuildError(
                    "required source failed: "
                    + str(source["listing_status"])
                    + f": {exc}"
                ) from exc
        rows = _rows_from_payload(payload, source)
        if not rows:
            raise SnapshotBuildError(
                "required source returned zero usable rows: "
                + str(source["listing_status"])
            )
        collected.extend(rows)
        dates = sorted(
            {str(item.get("source_data_date") or "") for item in rows} - {""}
        )
        used.append(
            {
                "source_name": source["dataset"],
                "source_authority": source["authority"],
                "source_url": source["url"],
                "dataset_page": source.get("dataset_page", ""),
                "listing_status": source["listing_status"],
                "record_count": len(rows),
                "source_data_date": dates[-1] if dates else "",
            }
        )
    return collected, used


def build_snapshot(
    *,
    repo_root: Path,
    getter: Callable[[str], Any] | None = None,
    from_dir: Path | None = None,
    downloaded_at: str | None = None,
) -> dict[str, Any]:
    collected, used = collect_source_rows(
        getter=getter or _http_get_json,
        from_dir=from_dir,
    )
    require_snapshot_sources(used)
    merged = merge_snapshot_rows(collected)
    quality = snapshot_quality_report(merged)
    dates = sorted(
        {str(item.get("source_data_date") or "") for item in merged} - {""}
    )
    included_statuses = [
        str(item.get("listing_status") or "")
        for item in used
        if int(item.get("record_count") or 0) > 0
    ]
    metadata = {
        "source_name": "TWSE / TPEx official company open data",
        "source_authority": "臺灣證券交易所、證券櫃檯買賣中心",
        "source_url": "https://openapi.twse.com.tw/v1/swagger.json",
        "sources": used,
        "downloaded_at": downloaded_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_data_date": dates[-1] if dates else "",
        "record_count": len(merged),
        "fields_included": [
            "unified_business_number",
            "company_name",
            "registered_address",
            "paid_in_capital_twd",
            "listing_status",
            "industry_code",
            "stock_code",
            "source_id",
            "source_authority",
            "source_dataset",
            "source_data_date",
        ],
        "snapshot_version": SNAPSHOT_VERSION,
        "coverage_statement_zh": coverage_statement_zh(included_statuses),
        "quality": quality,
    }
    replace_snapshot_atomically(
        rows=merged,
        csv_path=default_snapshot_csv(repo_root),
        metadata_path=default_snapshot_metadata(repo_root),
        metadata=metadata,
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-dir",
        type=Path,
        default=None,
        help="Read local JSON fixtures instead of downloading.",
    )
    args = parser.parse_args()
    try:
        metadata = build_snapshot(repo_root=ROOT, from_dir=args.from_dir)
    except Exception as exc:
        print(f"SNAPSHOT BUILD FAILED: {exc}")
        print("Last known-good snapshot was not overwritten.")
        return 1
    quality = metadata.get("quality") or {}
    print(f"records={metadata['record_count']}")
    print(f"source_data_date={metadata['source_data_date']}")
    print(f"paid_in_capital_ge_10b={quality.get('records_paid_in_capital_ge_10b')}")
    print(f"sources={metadata.get('sources')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
