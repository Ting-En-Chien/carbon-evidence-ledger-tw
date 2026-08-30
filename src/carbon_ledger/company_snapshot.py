"""Local official company snapshot — build-time download, runtime lookup.

Runtime never calls GCIS. Snapshot is a dated official open-data version,
not live government data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from carbon_ledger.company_master import (
    ORIGIN_SNAPSHOT,
    CompanyMaster,
    SourceRecord,
    is_reserved_placeholder_ubn,
    utc_now_iso,
    validate_ubn,
)

TWSE_SOURCE_ID = "src_tw_twse_portal"
TPEX_SOURCE_ID = "src_tw_tpex_portal"

SNAPSHOT_COLUMNS = (
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
)

REQUIRED_LISTING_STATUSES = ("TWSE", "TPEX", "PUBLIC")
COVERAGE_LABELS = (("TWSE", "上市"), ("TPEX", "上櫃"), ("PUBLIC", "公開發行"))
LISTING_PRIORITY = {"TWSE": 0, "TPEX": 1, "PUBLIC": 2}

TWSE_LISTED_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TWSE_PUBLIC_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_P"
TPEX_OTC_URL = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"

SNAPSHOT_SOURCES = (
    {
        "source_id": TWSE_SOURCE_ID,
        "authority": "臺灣證券交易所",
        "dataset": "上市公司基本資料 t187ap03_L",
        "url": TWSE_LISTED_URL,
        "listing_status": "TWSE",
        "dataset_page": "https://data.gov.tw/dataset/18419",
    },
    {
        "source_id": TPEX_SOURCE_ID,
        "authority": "證券櫃檯買賣中心",
        "dataset": "上櫃公司基本資料 mopsfin_t187ap03_O",
        "url": TPEX_OTC_URL,
        "listing_status": "TPEX",
        "dataset_page": "https://data.gov.tw/dataset/25036",
    },
    {
        "source_id": TWSE_SOURCE_ID,
        "authority": "臺灣證券交易所",
        "dataset": "公開發行公司基本資料 t187ap03_P",
        "url": TWSE_PUBLIC_URL,
        "listing_status": "PUBLIC",
        "dataset_page": "https://data.gov.tw/dataset/28567",
    },
)


class SnapshotBuildError(RuntimeError):
    """Required official source missing, empty, or refresh would be unsafe."""


def coverage_statement_zh(listing_statuses: Iterable[str]) -> str:
    present = {str(item) for item in listing_statuses}
    parts = [label for code, label in COVERAGE_LABELS if code in present]
    if not parts:
        return "目前本地公司資料庫尚未涵蓋可用的官方公開公司資料。"
    return (
        "目前本地公司資料庫涵蓋政府公開資料中的"
        f"{'／'.join(parts)}公司。"
    )


def require_snapshot_sources(used: list[dict[str, Any]]) -> None:
    present = {
        str(item.get("listing_status") or "")
        for item in used
        if int(item.get("record_count") or 0) > 0
    }
    missing = [code for code in REQUIRED_LISTING_STATUSES if code not in present]
    if missing:
        raise SnapshotBuildError(
            "required sources missing or empty: " + ", ".join(missing)
        )


def default_snapshot_dir(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "data" / "reference" / "company_master"


def default_snapshot_csv(repo_root: Path | None = None) -> Path:
    return default_snapshot_dir(repo_root) / "company_master.csv"


def default_snapshot_metadata(repo_root: Path | None = None) -> Path:
    return default_snapshot_dir(repo_root) / "company_master_metadata.json"


def roc_date_to_iso(value: Any) -> str:
    text = str(value or "").strip().replace("/", "")
    if len(text) == 7 and text.isdigit():
        year = 1911 + int(text[:3])
        return f"{year}-{text[3:5]}-{text[5:7]}"
    if len(text) == 8 and text.isdigit() and text.startswith("20"):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
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


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).replace(",", "").replace(" ", "")
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\u3000", " ").strip(" －-")


def normalize_source_row(
    row: Mapping[str, Any],
    *,
    listing_status: str,
    source_id: str,
    authority: str,
    dataset: str,
) -> dict[str, Any] | None:
    """Keep only product-useful fields. Never copy personal-name columns."""
    ubn_raw = _first(
        row,
        "營利事業統一編號",
        "統一編號",
        "BusinessAccountingNO",
        "Business_Accounting_NO",
        "UnifiedBusinessNo",
        "UnifiedBusinessNo.",
        "ubn",
    )
    ubn = str(ubn_raw or "").strip()
    if len(ubn) == 7 and ubn.isdigit():
        ubn = ubn.zfill(8)
    checked, error = validate_ubn(ubn)
    if error:
        return None
    name = _clean_text(
        _first(row, "公司名稱", "CompanyName", "company_name")
    )
    if not name:
        return None
    address = _clean_text(
        _first(row, "住址", "CompanyAddress", "Address", "address")
    )
    capital = _as_int(
        _first(
            row,
            "實收資本額",
            "PaidInCapital",
            "paid_in_capital",
            "Capital",
            "Paidin.Capital.NTDollars",
        )
    )
    source_date = roc_date_to_iso(
        _first(row, "出表日期", "DateOfData", "Date", "source_data_date")
    )
    return {
        "unified_business_number": checked,
        "company_name": name,
        "registered_address": address,
        "paid_in_capital_twd": capital,
        "listing_status": listing_status,
        "industry_code": _clean_text(_first(row, "產業別", "SecuritiesIndustryCode")),
        "stock_code": _clean_text(
            _first(row, "公司代號", "SecuritiesCompanyCode", "CompanyCode")
        ),
        "source_id": source_id,
        "source_authority": authority,
        "source_dataset": dataset,
        "source_data_date": source_date,
    }


def merge_snapshot_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per UBN. Prefer listed over OTC over emerging over public."""
    by_ubn: dict[str, dict[str, Any]] = {}
    for row in rows:
        ubn = str(row.get("unified_business_number") or "")
        if not ubn:
            continue
        current = by_ubn.get(ubn)
        if current is None:
            by_ubn[ubn] = dict(row)
            continue
        incoming_rank = LISTING_PRIORITY.get(str(row.get("listing_status")), 9)
        current_rank = LISTING_PRIORITY.get(str(current.get("listing_status")), 9)
        if incoming_rank < current_rank:
            by_ubn[ubn] = dict(row)
            continue
        if incoming_rank == current_rank:
            if not current.get("paid_in_capital_twd") and row.get(
                "paid_in_capital_twd"
            ):
                by_ubn[ubn] = dict(row)
            elif not current.get("registered_address") and row.get(
                "registered_address"
            ):
                by_ubn[ubn] = dict(row)
    ordered = sorted(
        by_ubn.values(),
        key=lambda item: (
            LISTING_PRIORITY.get(str(item.get("listing_status")), 9),
            str(item.get("stock_code") or ""),
            str(item.get("unified_business_number") or ""),
        ),
    )
    return ordered


def snapshot_quality_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {
            "total_records": 0,
            "records_with_ubn": 0,
            "records_with_company_name": 0,
            "records_with_address": 0,
            "records_with_paid_in_capital": 0,
            "records_paid_in_capital_ge_10b": 0,
            "source_distribution": {},
        }
    capital = pd.to_numeric(frame.get("paid_in_capital_twd"), errors="coerce")
    return {
        "total_records": int(len(frame)),
        "records_with_ubn": int(
            frame["unified_business_number"].astype(str).str.len().eq(8).sum()
        ),
        "records_with_company_name": int(
            frame["company_name"].astype(str).str.strip().ne("").sum()
        ),
        "records_with_address": int(
            frame["registered_address"].astype(str).str.strip().ne("").sum()
        ),
        "records_with_paid_in_capital": int(capital.notna().sum()),
        "records_paid_in_capital_ge_10b": int((capital >= 10_000_000_000).sum()),
        "source_distribution": {
            str(key): int(value)
            for key, value in frame["listing_status"].value_counts().to_dict().items()
        },
    }


def write_snapshot(
    rows: list[dict[str, Any]],
    *,
    csv_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        capital = item.get("paid_in_capital_twd")
        item["paid_in_capital_twd"] = (
            "" if capital in (None, "") else int(capital)
        )
        prepared.append(item)
    frame = pd.DataFrame(prepared, columns=list(SNAPSHOT_COLUMNS))
    frame.to_csv(csv_path, index=False)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def replace_snapshot_atomically(
    *,
    rows: list[dict[str, Any]],
    csv_path: Path,
    metadata_path: Path,
    metadata: dict[str, Any],
) -> None:
    """Write a complete snapshot, then replace the last known-good files."""
    tmp_csv = csv_path.with_name(csv_path.name + ".tmp")
    tmp_meta = metadata_path.with_name(metadata_path.name + ".tmp")
    try:
        write_snapshot(
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
class LocalOfficialCompanyRepository:
    """In-memory UBN index over a dated official snapshot."""

    rows_by_ubn: dict[str, dict[str, Any]]
    metadata: dict[str, Any]
    csv_path: str = ""

    def get(self, ubn: str) -> dict[str, Any] | None:
        return self.rows_by_ubn.get(str(ubn))

    def to_company_master(self, ubn: str) -> CompanyMaster | None:
        row = self.get(ubn)
        if not row:
            return None
        capital = row.get("paid_in_capital_twd")
        capital_int = int(capital) if capital not in (None, "") else None
        retrieved = utc_now_iso()
        source_date = str(
            row.get("source_data_date")
            or self.metadata.get("source_data_date")
            or ""
        )
        return CompanyMaster(
            company_id=f"co_{ubn}",
            unified_business_number=ubn,
            company_name=str(row.get("company_name") or ""),
            official_registered_address=str(row.get("registered_address") or ""),
            official_paid_in_capital_twd=capital_int,
            confirmed_paid_in_capital_twd=capital_int,
            listing_status=str(row.get("listing_status") or "UNKNOWN"),
            listing_source=str(row.get("source_id") or ""),
            company_registration_type=str(row.get("listing_status") or ""),
            lookup_status="ok",
            last_official_lookup_at=retrieved,
            snapshot_data_date=source_date,
            data_origin=ORIGIN_SNAPSHOT,
            source_records=[
                SourceRecord(
                    source_id=str(row.get("source_id") or ""),
                    authority=str(row.get("source_authority") or ""),
                    access_mode="OFFICIAL_OPEN_DATA",
                    retrieved_at=retrieved,
                    dataset_or_api=str(row.get("source_dataset") or ""),
                    raw_source_identifier="",
                    verified_access_mode="OFFICIAL_OPEN_DATA",
                )
            ],
        )


_REPO_CACHE: dict[str, LocalOfficialCompanyRepository] = {}


def load_snapshot_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_company_repository(
    csv_path: Path,
    *,
    metadata_path: Path | None = None,
) -> LocalOfficialCompanyRepository:
    key = str(csv_path.resolve()) if csv_path.exists() else str(csv_path)
    cached = _REPO_CACHE.get(key)
    if cached is not None:
        return cached
    if not csv_path.is_file():
        repo = LocalOfficialCompanyRepository(
            rows_by_ubn={},
            metadata={},
            csv_path=str(csv_path),
        )
        _REPO_CACHE[key] = repo
        return repo
    frame = pd.read_csv(csv_path, dtype=str).fillna("")
    rows_by_ubn: dict[str, dict[str, Any]] = {}
    for raw in frame.to_dict(orient="records"):
        ubn = str(raw.get("unified_business_number") or "").strip()
        if not ubn or is_reserved_placeholder_ubn(ubn):
            continue
        capital_raw = raw.get("paid_in_capital_twd")
        capital = _as_int(capital_raw) if capital_raw not in ("", None) else None
        rows_by_ubn[ubn] = {
            **raw,
            "paid_in_capital_twd": capital,
        }
    meta_file = metadata_path or csv_path.with_name("company_master_metadata.json")
    repo = LocalOfficialCompanyRepository(
        rows_by_ubn=rows_by_ubn,
        metadata=load_snapshot_metadata(meta_file),
        csv_path=str(csv_path),
    )
    _REPO_CACHE[key] = repo
    return repo


def reset_company_repository_cache() -> None:
    _REPO_CACHE.clear()


def repository_load_count() -> int:
    return len(_REPO_CACHE)
