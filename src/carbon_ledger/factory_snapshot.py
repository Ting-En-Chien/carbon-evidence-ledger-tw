"""Local official factory snapshot — build-time download, runtime lookup.

Runtime never requires CEL_FACTORY_OPEN_DATA_URL. Snapshot is a dated
official 登記工廠 open-data version, not live government data.

Registered factories are discovery candidates only. They are never
automatically placed inside the reporting boundary.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from carbon_ledger.company_master import (
    OfficialFactoryHint,
    is_reserved_placeholder_ubn,
    validate_ubn,
)

FACTORY_SOURCE_ID = "src_tw_factory_open_data"
FACTORY_CATALOG_URL = "https://www.ida.gov.tw/opendata/02/SDD6569.csv"
FACTORY_DATASET_PAGE = "https://data.gov.tw/dataset/6569"
FACTORY_AUTHORITY = "經濟部產業發展署"
FACTORY_DATASET = "登記工廠名錄（生產中工廠清冊）"

SNAPSHOT_COLUMNS = (
    "unified_business_number",
    "factory_name",
    "address",
    "registration_number",
    "industry_code",
    "main_products",
    "source_id",
    "source_authority",
    "source_dataset",
    "source_data_date",
)

PERSONAL_FIELD_KEYS = frozenset(
    {
        "工廠負責人姓名",
        "負責人姓名",
        "負責人",
        "董事長",
    }
)


class FactorySnapshotBuildError(RuntimeError):
    """Required factory source missing, empty, or refresh would be unsafe."""


def default_factory_dir(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "data" / "reference" / "factory_master"


def default_factory_csv(repo_root: Path | None = None) -> Path:
    return default_factory_dir(repo_root) / "factory_master.csv"


def default_factory_metadata(repo_root: Path | None = None) -> Path:
    return default_factory_dir(repo_root) / "factory_master_metadata.json"


def factory_file_date(name: str) -> str:
    """Map inner filenames such as 11506.csv to an ISO month date."""
    stem = Path(str(name or "")).stem
    if len(stem) == 5 and stem.isdigit():
        year = 1911 + int(stem[:3])
        return f"{year}-{stem[3:5]}-01"
    return ""


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    lower = {str(k).casefold(): v for k, v in row.items()}
    for key in keys:
        value = lower.get(key.casefold())
        if value not in (None, ""):
            return value
    return None


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\u3000", " ").strip(" －-")


def normalize_factory_row(
    row: Mapping[str, Any],
    *,
    source_data_date: str = "",
) -> dict[str, Any] | None:
    """Keep product-useful factory fields. Never copy personal-name columns."""
    ubn_raw = _first(
        row,
        "統一編號",
        "unified_business_number",
        "Business_Accounting_NO",
        "ban",
        "ubn",
    )
    ubn = str(ubn_raw or "").strip()
    if len(ubn) == 7 and ubn.isdigit():
        ubn = ubn.zfill(8)
    checked, error = validate_ubn(ubn)
    if error:
        return None
    name = _clean_text(
        _first(row, "工廠名稱", "factory_name", "Factory_Name", "name")
    )
    if not name:
        return None
    return {
        "unified_business_number": checked,
        "factory_name": name,
        "address": _clean_text(
            _first(row, "工廠地址", "address", "Factory_Address")
        ),
        "registration_number": _clean_text(
            _first(
                row,
                "工廠登記編號",
                "registration_number",
                "Factory_ID",
            )
        ),
        "industry_code": _clean_text(
            _first(row, "產業類別", "industry_code", "Industry")
        ),
        "main_products": _clean_text(
            _first(row, "主要產品", "main_products", "Product")
        ),
        "source_id": FACTORY_SOURCE_ID,
        "source_authority": FACTORY_AUTHORITY,
        "source_dataset": FACTORY_DATASET,
        "source_data_date": source_data_date,
    }


def merge_factory_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep unique factories. One company may have many sites."""
    seen: set[tuple[str, str, str]] = set()
    merged: list[dict[str, Any]] = []
    for row in rows:
        ubn = str(row.get("unified_business_number") or "")
        if not ubn or is_reserved_placeholder_ubn(ubn):
            continue
        key = (
            ubn,
            str(row.get("registration_number") or ""),
            str(row.get("factory_name") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(row))
    merged.sort(
        key=lambda item: (
            str(item.get("unified_business_number") or ""),
            str(item.get("registration_number") or ""),
            str(item.get("factory_name") or ""),
        )
    )
    return merged


def factory_quality_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {
            "total_records": 0,
            "unique_ubn_count": 0,
            "records_with_name": 0,
            "records_with_address": 0,
            "records_with_registration_number": 0,
        }
    return {
        "total_records": int(len(frame)),
        "unique_ubn_count": int(frame["unified_business_number"].nunique()),
        "records_with_name": int(
            frame["factory_name"].astype(str).str.strip().ne("").sum()
        ),
        "records_with_address": int(
            frame["address"].astype(str).str.strip().ne("").sum()
        ),
        "records_with_registration_number": int(
            frame["registration_number"].astype(str).str.strip().ne("").sum()
        ),
    }


def write_factory_snapshot(
    rows: list[dict[str, Any]],
    *,
    csv_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if PERSONAL_FIELD_KEYS.intersection(SNAPSHOT_COLUMNS):
        raise FactorySnapshotBuildError(
            "personal fields must not be stored in the factory snapshot"
        )
    frame = pd.DataFrame(rows, columns=list(SNAPSHOT_COLUMNS))
    frame.to_csv(csv_path, index=False)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def replace_factory_snapshot_atomically(
    *,
    rows: list[dict[str, Any]],
    csv_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
) -> None:
    tmp_csv = csv_path.with_name(csv_path.name + ".tmp")
    tmp_meta = metadata_path.with_name(metadata_path.name + ".tmp")
    try:
        write_factory_snapshot(
            rows,
            csv_path=tmp_csv,
            metadata_path=tmp_meta,
            metadata=metadata,
        )
        tmp_csv.replace(csv_path)
        tmp_meta.replace(metadata_path)
    finally:
        if tmp_csv.exists():
            tmp_csv.unlink()
        if tmp_meta.exists():
            tmp_meta.unlink()


@dataclass
class LocalOfficialFactoryRepository:
    """In-memory UBN index over a dated official factory snapshot."""

    rows_by_ubn: dict[str, list[dict[str, Any]]]
    metadata: dict[str, Any]
    csv_path: str = ""
    loaded: bool = False

    def hints_for(self, ubn: str) -> list[OfficialFactoryHint]:
        hints: list[OfficialFactoryHint] = []
        for row in self.rows_by_ubn.get(str(ubn), []):
            name = str(row.get("factory_name") or "").strip()
            if not name:
                continue
            hints.append(
                OfficialFactoryHint(
                    display_name=name,
                    address=str(row.get("address") or ""),
                    registration_number=str(row.get("registration_number") or ""),
                    industry_code=str(row.get("industry_code") or ""),
                    main_products=str(row.get("main_products") or ""),
                    unified_business_number=str(ubn),
                )
            )
        return hints


_REPO_CACHE: dict[str, LocalOfficialFactoryRepository] = {}


def load_snapshot_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_factory_repository(
    csv_path: Path,
    *,
    metadata_path: Path | None = None,
) -> LocalOfficialFactoryRepository:
    key = str(csv_path.resolve()) if csv_path.exists() else str(csv_path)
    cached = _REPO_CACHE.get(key)
    if cached is not None:
        return cached
    if not csv_path.is_file():
        repo = LocalOfficialFactoryRepository(
            rows_by_ubn={},
            metadata={},
            csv_path=str(csv_path),
            loaded=False,
        )
        _REPO_CACHE[key] = repo
        return repo
    frame = pd.read_csv(csv_path, dtype=str).fillna("")
    rows_by_ubn: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in frame.to_dict(orient="records"):
        ubn = str(raw.get("unified_business_number") or "").strip()
        if not ubn or is_reserved_placeholder_ubn(ubn):
            continue
        if not str(raw.get("factory_name") or "").strip():
            continue
        rows_by_ubn[ubn].append(raw)
    meta_file = metadata_path or csv_path.with_name("factory_master_metadata.json")
    repo = LocalOfficialFactoryRepository(
        rows_by_ubn=dict(rows_by_ubn),
        metadata=load_snapshot_metadata(meta_file),
        csv_path=str(csv_path),
        loaded=True,
    )
    _REPO_CACHE[key] = repo
    return repo


def reset_factory_repository_cache() -> None:
    _REPO_CACHE.clear()
