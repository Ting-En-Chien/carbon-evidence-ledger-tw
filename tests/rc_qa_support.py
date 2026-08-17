"""RC QA independent expected calculations and deterministic fixtures.

Official constants are copied from published methodology / registry tables.
They are not read back from calculate.py outputs.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from carbon_ledger.intake import (
    ColumnMapping,
    IntakeMetadata,
    build_and_validate_intake,
    default_value_maps,
    parse_uploaded_table,
    suggest_activity_type,
    suggest_column_mapping,
    suggest_unit,
)
from carbon_ledger.pipeline import run_uploaded_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2025-02-01T00:00:00Z")

# Independent official constants (methodology v1 / MOENV tables).
KCAL_TO_TJ = Decimal("4.1868E-9")
ELEC_2024_KG_PER_KWH = Decimal("0.474")
ELEC_2025_KG_PER_KWH = Decimal("0.466")
HV_NG1_LOW = Decimal("8067")
HV_NG2_LOW = Decimal("8728")
HV_DIESEL = Decimal("8636")
CO2_NG = Decimal("56100")
CH4_NG = Decimal("1")
N2O_NG = Decimal("0.1")
CO2_DIESEL = Decimal("74100")
CH4_DIESEL = Decimal("3.9")
N2O_DIESEL = Decimal("3.9")
GWP_CO2 = Decimal("1")
GWP_CH4 = Decimal("28")
GWP_N2O = Decimal("265")
HERO_JS_SHA = "70cd43b7f1fa2bedf4485bc7846278b736e1c183961c6c7117d6cc8b5f5828c0"


def electricity_tco2e(kwh: Decimal, factor: Decimal = ELEC_2024_KG_PER_KWH) -> Decimal:
    return (kwh * factor) / Decimal("1000")


def combustion_tco2e(
    activity: Decimal,
    heating_value: Decimal,
    co2: Decimal,
    ch4: Decimal,
    n2o: Decimal,
    *,
    ch4_gwp: Decimal = GWP_CH4,
    n2o_gwp: Decimal = GWP_N2O,
) -> Decimal:
    energy_tj = activity * heating_value * KCAL_TO_TJ
    kg = (
        energy_tj * co2 * GWP_CO2
        + energy_tj * ch4 * ch4_gwp
        + energy_tj * n2o * n2o_gwp
    )
    return kg / Decimal("1000")


def ng1_tco2e(m3: Decimal) -> Decimal:
    return combustion_tco2e(m3, HV_NG1_LOW, CO2_NG, CH4_NG, N2O_NG)


def ng2_tco2e(m3: Decimal) -> Decimal:
    return combustion_tco2e(m3, HV_NG2_LOW, CO2_NG, CH4_NG, N2O_NG)


def diesel_tco2e(litres: Decimal) -> Decimal:
    return combustion_tco2e(
        litres, HV_DIESEL, CO2_DIESEL, CH4_DIESEL, N2O_DIESEL
    )


def metadata(*, name: str = "rc_qa.csv", site: str = "高雄廠") -> IntakeMetadata:
    return IntakeMetadata(
        source_name=name,
        site_id=site,
        document_date=date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="rc_qa",
        ingested_at=FIXED_INGESTED_AT,
    )


def mapping_for(table: pd.DataFrame, **overrides: object) -> ColumnMapping:
    suggestions = suggest_column_mapping(list(table.columns))
    activity_map, unit_map = default_value_maps(
        table,
        ColumnMapping(
            activity_type_column=suggestions["activity_type"],
            activity_value_column=suggestions["activity_value"],
            unit_column=suggestions["unit"],
        ),
    )
    activity_map = {
        key: value or suggest_activity_type(key) for key, value in activity_map.items()
    }
    unit_map = {key: value or suggest_unit(key) for key, value in unit_map.items()}
    mapping = ColumnMapping(
        activity_type_column=suggestions["activity_type"],
        activity_value_column=suggestions["activity_value"],
        unit_column=suggestions["unit"],
        site_column=suggestions.get("site_id") or "",
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
        natural_gas_subtype="NG1",
        diesel_context="company_vehicle",
        electricity_context="enterprise",
    )
    for key, value in overrides.items():
        setattr(mapping, key, value)
    return mapping


def intake_and_run(
    csv_text: str,
    *,
    file_name: str = "rc_qa.csv",
    run_id: str = "rc_qa",
    data: bytes | None = None,
    repo_root: Path | None = None,
    **mapping_overrides: object,
):
    payload = data if data is not None else csv_text.encode("utf-8")
    table = parse_uploaded_table(file_name=file_name, data=payload)
    mapping = mapping_for(table, **mapping_overrides)
    intake = build_and_validate_intake(table, mapping, metadata(name=file_name))
    result = run_uploaded_pipeline(
        repo_root or REPO_ROOT,
        run_id=run_id,
        ingested_at=FIXED_INGESTED_AT,
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
        include_ifrs_s2=True,
    )
    return result, intake


def _row(activity: str, qty: str, unit: str, start: str, end: str, site: str) -> str:
    return f"{activity},{qty},{unit},{start},{end},{site}"


def dataset_a_csv(*, rows: int = 120) -> str:
    """Clean single-site mix of electricity / NG1 / NG2 / diesel."""
    header = "活動類型,用量,單位,開始日期,結束日期,廠場"
    lines = [header]
    kinds = [
        ("外購電力", "100", "kWh"),
        ("天然氣 NG1", "10", "m3"),
        ("天然氣 NG2", "10", "m3"),
        ("柴油", "5", "L"),
    ]
    while len(lines) - 1 < rows:
        activity, qty, unit = kinds[(len(lines) - 1) % 4]
        lines.append(_row(activity, qty, unit, "2025-01-01", "2025-01-31", "高雄廠"))
    return "\n".join(lines) + "\n"


def dataset_b_csv(*, rows: int = 200) -> str:
    """Clean multi-site plus unsupported steel."""
    header = "活動類型,用量,單位,開始日期,結束日期,廠場"
    lines = [header]
    kinds = [
        ("外購電力", "80", "kWh", "高雄廠"),
        ("天然氣 NG1", "8", "m3", "台中廠"),
        ("天然氣 NG2", "8", "m3", "高雄廠"),
        ("柴油", "4", "L", "台北倉"),
        ("採購鋼材", "1", "t", "高雄廠"),
    ]
    while len(lines) - 1 < rows:
        activity, qty, unit, site = kinds[(len(lines) - 1) % 5]
        lines.append(_row(activity, qty, unit, "2025-01-01", "2025-01-31", site))
    return "\n".join(lines) + "\n"


def dataset_c_csv(*, rows: int = 150) -> str:
    """Mixed valid and incomplete rows."""
    header = "活動類型,用量,單位,開始日期,結束日期,廠場"
    lines = [header]
    templates = [
        ("外購電力", "50", "kWh", "高雄廠"),
        ("天然氣", "10", "m3", "高雄廠"),  # missing subtype in cell
        ("柴油", "3", "L", "高雄廠"),  # ambiguous diesel context
        ("天然氣 NG1", "10", "m3", "台中廠"),
        ("公司車輛柴油", "4", "L", "台中廠"),
        ("外購電力", "40", "kWh", ""),  # missing site (inherits metadata)
    ]
    while len(lines) - 1 < rows:
        activity, qty, unit, site = templates[(len(lines) - 1) % 6]
        lines.append(_row(activity, qty, unit, "2025-01-01", "2025-01-31", site))
    return "\n".join(lines) + "\n"


def dataset_d_csv(*, rows: int = 180) -> str:
    """Business column labels different from internal schema."""
    header = "能源項目,數量,計量單位,期間開始,期間結束,廠場"
    lines = [header]
    kinds = [
        ("外購電力", "60", "度"),
        ("天然氣 NG1", "12", "立方公尺"),
        ("柴油", "6", "公升"),
        ("採購鋼材", "2", "噸"),
    ]
    while len(lines) - 1 < rows:
        activity, qty, unit = kinds[(len(lines) - 1) % 4]
        lines.append(_row(activity, qty, unit, "2025-01-01", "2025-01-31", "高雄廠"))
    return "\n".join(lines) + "\n"


def dataset_e_csv(*, rows: int = 300) -> str:
    """Dirty / stress rows mixed with valid ones."""
    header = "活動類型,用量,單位,開始日期,結束日期,廠場"
    lines = [header]
    dirty = [
        ("外購電力", "20", "kWh", "2025-01-01", "2025-01-31", "高雄廠"),
        ("外購電力", "", "kWh", "2025-01-01", "2025-01-31", "高雄廠"),
        ("天然氣 NG1", "5", "", "2025-01-01", "2025-01-31", "台中廠"),
        ("柴油", "-3", "L", "2025-01-01", "2025-01-31", "高雄廠"),
        ("天然氣", "8", "m3", "2025-01-01", "2025-01-31", "高雄廠"),
        ("神秘燃料", "1", "kg", "2025-01-01", "2025-01-31", "高雄廠"),
        ("採購鋼材", "1", "t", "2025-01-01", "2025-01-31", "高雄廠"),
        ("外購電力", "0", "kWh", "2025-01-01", "2025-01-31", "高雄廠"),
        ("  外購電力  ", "15", "kWh", "2025-01-01", "2025-01-31", "台北倉"),
        ("diesel", "2", "l", "2025-01-01", "2025-01-31", "高雄廠"),
        ("外購電力", "999999", "kWh", "2025-01-01", "2025-01-31", "高雄廠"),
        ("天然氣 NG1", "0.001", "m3", "2025-01-01", "2025-01-31", "高雄廠"),
        ("外購電力", "10", "kWh", "", "2025-01-31", "高雄廠"),
        ("外購電力", "10", "kWh", "2025-01-01", "2025-01-31", ""),
        ("外購電力", "10", "kWh", "2025-01-01", "2025-01-31", "高雄廠"),
    ]
    while len(lines) - 1 < rows:
        item = dirty[(len(lines) - 1) % len(dirty)]
        lines.append(",".join(item))
    return "\n".join(lines) + "\n"


def dataset_clean_1000_csv() -> str:
    return dataset_a_csv(rows=1000)


def csv_to_xlsx_bytes(csv_text: str) -> bytes:
    table = pd.read_csv(io.StringIO(csv_text))
    buffer = io.BytesIO()
    table.to_excel(buffer, index=False)
    return buffer.getvalue()


def calculated_rows(result) -> pd.DataFrame:
    frame = result.calculation_results
    return frame[frame["calculation_status"].astype(str) == "calculated"].copy()


def blocked_or_unsupported(result) -> pd.DataFrame:
    frame = result.calculation_results
    status = frame["calculation_status"].astype(str)
    return frame[status != "calculated"].copy()


def calculated_tco2e_sum(result) -> Decimal:
    rows = calculated_rows(result)
    if rows.empty:
        return Decimal("0")
    total = Decimal("0")
    for value in rows["calculated_tco2e"].tolist():
        if value is None or pd.isna(value):
            continue
        total += Decimal(str(value))
    return total


def assert_blocked_not_zero(result) -> None:
    blocked = blocked_or_unsupported(result)
    if blocked.empty:
        return
    numeric = pd.to_numeric(blocked["calculated_tco2e"], errors="coerce")
    zero_mask = numeric.notna() & (numeric == 0)
    sample = blocked.loc[zero_mask, ["record_id", "calculation_status"]]
    assert not bool(zero_mask.any()), (
        "blocked/unsupported rows must not store 0 tCO2e: "
        f"{sample.to_dict('records')}"
    )


def write_rc_qa_fixtures(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    mapping = {
        "dataset_a_clean_single_site.csv": dataset_a_csv(rows=120),
        "dataset_b_clean_multi_site.csv": dataset_b_csv(rows=200),
        "dataset_c_partial.csv": dataset_c_csv(rows=150),
        "dataset_d_business_columns.csv": dataset_d_csv(rows=180),
        "dataset_e_dirty_stress.csv": dataset_e_csv(rows=300),
    }
    paths: dict[str, Path] = {}
    for name, text in mapping.items():
        path = directory / name
        path.write_text(text, encoding="utf-8")
        paths[name] = path
    return paths
