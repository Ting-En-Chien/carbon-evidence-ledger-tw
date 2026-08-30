#!/usr/bin/env python3
"""Build the local official factory snapshot from Taiwan open data.

V1 refresh is manual:

    python scripts/build_factory_snapshot.py

Runtime customer lookup never downloads. This script is the only network step.
CEL_FACTORY_OPEN_DATA_URL is not required.
"""

from __future__ import annotations

import argparse
import csv
import io
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from carbon_ledger.factory_snapshot import (  # noqa: E402
    FACTORY_AUTHORITY,
    FACTORY_CATALOG_URL,
    FACTORY_DATASET,
    FACTORY_DATASET_PAGE,
    FACTORY_SOURCE_ID,
    PERSONAL_FIELD_KEYS,
    FactorySnapshotBuildError,
    default_factory_csv,
    default_factory_metadata,
    factory_file_date,
    factory_quality_report,
    merge_factory_rows,
    normalize_factory_row,
    replace_factory_snapshot_atomically,
)

SNAPSHOT_VERSION = "2026-08-16.v1"


def _curl_get(url: str, *, timeout: float) -> bytes:
    curl = shutil.which("curl")
    if not curl:
        raise FactorySnapshotBuildError("curl is required to refresh the snapshot")
    completed = subprocess.run(
        [
            curl,
            "-fsSL",
            "--max-time",
            str(int(timeout)),
            "-A",
            "CarbonEvidenceLedger/factory-snapshot-build",
            url,
        ],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def _http_get_text(url: str, *, timeout: float = 60.0) -> str:
    raw = _curl_get(url, timeout=timeout)
    if not raw.strip():
        raise FactorySnapshotBuildError("catalog download was empty")
    return raw.decode("utf-8-sig")


def _http_get_bytes(url: str, *, timeout: float = 120.0) -> bytes:
    raw = _curl_get(url, timeout=timeout)
    if not raw:
        raise FactorySnapshotBuildError("factory ZIP download was empty")
    return raw


def catalog_zip_url(catalog_text: str) -> str:
    reader = csv.DictReader(io.StringIO(catalog_text))
    for row in reader:
        fmt = str(row.get("檔案格式") or "").strip().upper()
        url = str(row.get("下載連結") or "").strip()
        if fmt == "ZIP" and url.startswith("http"):
            return url
    raise FactorySnapshotBuildError("catalog has no ZIP download link")


def rows_from_csv_text(
    text: str,
    *,
    source_data_date: str,
) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    normalized: list[dict[str, Any]] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        item = normalize_factory_row(row, source_data_date=source_data_date)
        if item is not None:
            normalized.append(item)
    return normalized


def rows_from_zip_bytes(raw: bytes) -> tuple[list[dict[str, Any]], str, str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise FactorySnapshotBuildError("factory download is not a ZIP") from exc
    csv_names = [
        name
        for name in archive.namelist()
        if name.lower().endswith(".csv") and not name.endswith("/")
    ]
    if not csv_names:
        raise FactorySnapshotBuildError("factory ZIP has no CSV")
    inner_name = csv_names[0]
    payload = archive.read(inner_name)
    for encoding in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            text = ""
    else:
        raise FactorySnapshotBuildError("factory CSV encoding is unsupported")
    source_date = factory_file_date(inner_name)
    rows = rows_from_csv_text(text, source_data_date=source_date)
    return rows, inner_name, source_date


def collect_factory_rows(
    *,
    from_csv: Path | None = None,
    from_zip: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if from_csv is not None:
        if not from_csv.is_file():
            raise FactorySnapshotBuildError(f"required CSV missing: {from_csv}")
        text = from_csv.read_text(encoding="utf-8-sig")
        source_date = factory_file_date(from_csv.name)
        rows = rows_from_csv_text(text, source_data_date=source_date)
        used = {
            "source_name": FACTORY_DATASET,
            "source_authority": FACTORY_AUTHORITY,
            "source_url": str(from_csv),
            "dataset_page": FACTORY_DATASET_PAGE,
            "inner_file": from_csv.name,
            "record_count": len(rows),
            "source_data_date": source_date,
        }
        return rows, used
    if from_zip is not None:
        if not from_zip.is_file():
            raise FactorySnapshotBuildError(f"required ZIP missing: {from_zip}")
        rows, inner_name, source_date = rows_from_zip_bytes(from_zip.read_bytes())
        used = {
            "source_name": FACTORY_DATASET,
            "source_authority": FACTORY_AUTHORITY,
            "source_url": str(from_zip),
            "dataset_page": FACTORY_DATASET_PAGE,
            "inner_file": inner_name,
            "record_count": len(rows),
            "source_data_date": source_date,
        }
        return rows, used
    try:
        catalog_text = _http_get_text(FACTORY_CATALOG_URL)
        zip_url = catalog_zip_url(catalog_text)
        zip_bytes = _http_get_bytes(zip_url)
    except FactorySnapshotBuildError:
        raise
    except Exception as exc:
        raise FactorySnapshotBuildError(
            f"required factory source failed: {exc}"
        ) from exc
    rows, inner_name, source_date = rows_from_zip_bytes(zip_bytes)
    used = {
        "source_name": FACTORY_DATASET,
        "source_authority": FACTORY_AUTHORITY,
        "source_url": zip_url,
        "catalog_url": FACTORY_CATALOG_URL,
        "dataset_page": FACTORY_DATASET_PAGE,
        "inner_file": inner_name,
        "record_count": len(rows),
        "source_data_date": source_date,
    }
    return rows, used


def build_factory_snapshot(
    *,
    repo_root: Path,
    from_csv: Path | None = None,
    from_zip: Path | None = None,
    downloaded_at: str | None = None,
) -> dict[str, Any]:
    collected, used = collect_factory_rows(from_csv=from_csv, from_zip=from_zip)
    if not collected:
        raise FactorySnapshotBuildError(
            "required factory source returned zero usable rows"
        )
    merged = merge_factory_rows(collected)
    if not merged:
        raise FactorySnapshotBuildError(
            "required factory source returned zero usable rows"
        )
    quality = factory_quality_report(merged)
    metadata = {
        "source_name": FACTORY_DATASET,
        "source_authority": FACTORY_AUTHORITY,
        "source_id": FACTORY_SOURCE_ID,
        "source_url": used.get("source_url") or FACTORY_CATALOG_URL,
        "dataset_page": FACTORY_DATASET_PAGE,
        "sources": [used],
        "downloaded_at": downloaded_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_data_date": used.get("source_data_date") or "",
        "record_count": len(merged),
        "fields_included": list(
            [
                "unified_business_number",
                "factory_name",
                "address",
                "registration_number",
                "industry_code",
                "main_products",
            ]
        ),
        "fields_not_kept": sorted(PERSONAL_FIELD_KEYS),
        "snapshot_version": SNAPSHOT_VERSION,
        "coverage_statement_zh": (
            "目前本地工廠資料庫涵蓋政府公開資料中的生產中登記工廠。"
        ),
        "quality": quality,
        "note_zh": "登記工廠僅為發現候選，不會自動納入盤查邊界。",
    }
    replace_factory_snapshot_atomically(
        rows=merged,
        csv_path=default_factory_csv(repo_root),
        metadata_path=default_factory_metadata(repo_root),
        metadata=metadata,
    )
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-csv", type=Path, default=None)
    parser.add_argument("--from-zip", type=Path, default=None)
    args = parser.parse_args()
    try:
        metadata = build_factory_snapshot(
            repo_root=ROOT,
            from_csv=args.from_csv,
            from_zip=args.from_zip,
        )
    except Exception as exc:
        print(f"FACTORY SNAPSHOT BUILD FAILED: {exc}")
        print("Last known-good snapshot was not overwritten.")
        return 1
    quality = metadata.get("quality") or {}
    print(f"records={metadata['record_count']}")
    print(f"source_data_date={metadata['source_data_date']}")
    print(f"unique_ubn_count={quality.get('unique_ubn_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
