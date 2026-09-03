"""Actual-refill refrigerant fugitive calculation — data presence, not leak rates."""

from __future__ import annotations

import math
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd
import pytest

from carbon_ledger.factors import (
    GWP_CONTEXT_FUEL_COMBUSTION,
    GWP_CONTEXT_REFRIGERANT_FUGITIVE,
    select_gwp_row,
    validate_factor_registry,
)
from carbon_ledger.refrigerants import (
    FORMULA_ID,
    FORMULA_VERSION,
    STATUS_BLOCKED_INCOMPLETE_COMPOSITION,
    STATUS_BLOCKED_INVALID_PERIOD,
    STATUS_BLOCKED_INVALID_QUANTITY,
    STATUS_BLOCKED_MISSING_EVIDENCE,
    STATUS_BLOCKED_MISSING_GWP,
    STATUS_BLOCKED_MISSING_QUANTITY,
    STATUS_BLOCKED_MISSING_RECORD_ID,
    STATUS_BLOCKED_UNCONFIRMED_ZERO,
    STATUS_BLOCKED_UNKNOWN_REFRIGERANT,
    STATUS_CALCULATED,
    STATUS_CONFIRMED_NO_REFILL,
    RefrigerantRegistryError,
    calculate_actual_refill,
    canonicalize_refrigerant_code,
    derived_blend_gwp_id,
    load_refrigerant_calculation_inputs,
    lookup_refrigerant_ar5_gwp,
    validate_refrigerant_compositions,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = REPO_ROOT / "data" / "reference"
ODS_PATH = (
    REPO_ROOT
    / "data"
    / "reference_snapshots"
    / "src_tw_moenv_general_emission_factors__unknown-pub__085fe962e158.ods"
)
TABLE_NS = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def _inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_refrigerant_calculation_inputs(REFERENCE_DIR)


def _base_record(**fields: object) -> dict[str, object]:
    record: dict[str, object] = {
        "record_id": "rec_refill_001",
        "reporting_year": 2026,
        "reporting_period_id": "period-2026",
        "refrigerant_code": "R-134a",
        "actual_refill_kg": 15,
        "refill_confirmed": True,
        "source_document_id": "doc_refill_001",
    }
    record.update(fields)
    return record


def _calculate(**fields: object):
    compositions, gwp_values = _inputs()
    return calculate_actual_refill(
        _base_record(**fields),
        compositions=compositions,
        gwp_values=gwp_values,
    )


def test_r134a_15kg_actual_refill() -> None:
    result = _calculate()
    assert result.calculation_status == STATUS_CALCULATED
    assert result.calculated_kgco2e == 19500.0
    assert result.calculated_tco2e == 19.5
    assert result.activity_type == "refrigerant_refill"
    assert result.ghg_scope == "scope_1"
    assert result.emission_form == "fugitive_emission"
    assert result.method_id == "actual_refill_mass_balance"
    assert result.formula_id == FORMULA_ID
    assert result.formula_version == FORMULA_VERSION
    assert result.gwp_value == 1300.0
    assert result.gwp_source_reference_id == "ref_tw_moenv_2024_emission_factors"
    assert result.reporting_year == 2026
    assert result.reporting_period_id == "period-2026"
    assert "gwp_ar5_hfc134a_refrigerant_fugitive" in result.calculation_trace
    assert FORMULA_ID in result.calculation_trace
    assert "IPCC AR5 100-year GWP" in result.calculation_trace
    row = result.to_calculation_row()
    assert row["formula_id"] == FORMULA_ID
    assert row["gwp_source_reference_id"] == "ref_tw_moenv_2024_emission_factors"
    assert row["calculation_status"] == STATUS_CALCULATED


def test_r410a_ar5_gwp_is_weighted_from_components() -> None:
    compositions, gwp_values = _inputs()
    looked_up = lookup_refrigerant_ar5_gwp(
        "R-410A", compositions=compositions, gwp_values=gwp_values
    )
    assert looked_up is not None
    expected = Decimal("0.5") * Decimal("677") + Decimal("0.5") * Decimal("3170")
    assert expected == Decimal("1923.5")
    assert looked_up.gwp_value == expected
    gases = {item["gas"] for item in looked_up.components}
    assert gases == {"HFC-32", "HFC-125"}
    fractions = {
        item["gas"]: Decimal(item["mass_fraction"]) for item in looked_up.components
    }
    assert fractions["HFC-32"] == Decimal("0.5")
    assert fractions["HFC-125"] == Decimal("0.5")
    assert "2088" not in str(looked_up.gwp_value)
    assert looked_up.gwp_id == "gwp_ar5_r410a_weighted"
    assert derived_blend_gwp_id("R-410A") == "gwp_ar5_r410a_weighted"
    result = _calculate(refrigerant_code="R410A", actual_refill_kg=2)
    assert result.calculation_status == STATUS_CALCULATED
    assert result.gwp_id == "gwp_ar5_r410a_weighted"
    assert result.factor_id == "gwp_ar5_r410a_weighted"
    assert result.gwp_id.strip()
    assert result.factor_id.strip()
    assert result.gwp_value == 1923.5
    assert result.calculated_kgco2e == 3847.0
    assert result.calculated_tco2e == 3.847
    assert "1923.5" in result.calculation_trace
    assert "0.5 × 677 + 0.5 × 3170" in result.calculation_trace
    assert "gwp_ar5_hfc32_refrigerant_fugitive" in result.calculation_trace
    assert "gwp_ar5_hfc125_refrigerant_fugitive" in result.calculation_trace
    assert "ref_ipcc_2006_vol3_ch7" in result.calculation_trace


def test_confirmed_no_refill_is_zero_not_missing() -> None:
    result = _calculate(actual_refill_kg=0, refill_confirmed=True)
    assert result.calculation_status == STATUS_CONFIRMED_NO_REFILL
    assert result.calculated_kgco2e == 0.0
    assert result.calculated_tco2e == 0.0
    assert result.calculation_status != STATUS_BLOCKED_MISSING_QUANTITY
    assert "missing" not in result.calculation_status


def test_missing_quantity_without_confirmation_is_blocked_not_zero() -> None:
    result = _calculate(actual_refill_kg=None, refill_confirmed=False)
    assert result.calculation_status == STATUS_BLOCKED_MISSING_QUANTITY
    assert result.calculated_kgco2e is None
    assert result.calculated_tco2e is None
    row = result.to_calculation_row()
    assert pd.isna(row["calculated_kgco2e"])
    assert pd.isna(row["calculated_tco2e"])
    zeroed = _calculate(actual_refill_kg=0, refill_confirmed=False)
    assert zeroed.calculation_status == STATUS_BLOCKED_UNCONFIRMED_ZERO
    assert zeroed.calculated_kgco2e is None
    assert zeroed.calculated_tco2e is None


def test_unknown_refrigerant_is_blocked() -> None:
    result = _calculate(refrigerant_code="R-407C")
    assert result.calculation_status == STATUS_BLOCKED_UNKNOWN_REFRIGERANT
    assert result.calculated_kgco2e is None
    assert canonicalize_refrigerant_code("R407C") is None
    assert canonicalize_refrigerant_code("R134a") == "R-134A"
    assert canonicalize_refrigerant_code("R-134A") == "R-134A"
    assert canonicalize_refrigerant_code("r-134a") == "R-134A"
    assert canonicalize_refrigerant_code("HFC-134a") == "R-134A"


def test_negative_nan_infinity_are_blocked() -> None:
    for value in (-1, float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"):
        result = _calculate(actual_refill_kg=value)
        assert result.calculation_status == STATUS_BLOCKED_INVALID_QUANTITY, value
        assert result.calculated_kgco2e is None
        assert result.calculated_tco2e is None
        if isinstance(value, float):
            assert math.isnan(value) or math.isinf(value)


def test_composition_fractions_must_sum_to_one() -> None:
    broken = pd.DataFrame(
        [
            {
                "refrigerant_code": "R-410A",
                "component_gas": "HFC-32",
                "mass_fraction": "0.4",
                "composition_status": "ready",
                "source_reference_id": "ref_ipcc_2006_vol3_ch7",
                "source_locator": "test",
                "valid_from": "2006-01-01",
                "notes": "broken",
            },
            {
                "refrigerant_code": "R-410A",
                "component_gas": "HFC-125",
                "mass_fraction": "0.4",
                "composition_status": "ready",
                "source_reference_id": "ref_ipcc_2006_vol3_ch7",
                "source_locator": "test",
                "valid_from": "2006-01-01",
                "notes": "broken",
            },
        ]
    )
    with pytest.raises(RefrigerantRegistryError, match="sum to"):
        validate_refrigerant_compositions(broken)
    compositions, gwp_values = _inputs()
    compositions = compositions.loc[compositions["refrigerant_code"] != "R-410A"]
    compositions = pd.concat([compositions, broken], ignore_index=True)
    result = calculate_actual_refill(
        _base_record(refrigerant_code="R-410A"),
        compositions=compositions,
        gwp_values=gwp_values,
    )
    assert result.calculation_status == STATUS_BLOCKED_INCOMPLETE_COMPOSITION
    assert result.calculated_kgco2e is None


def test_result_retains_method_gwp_and_period_provenance() -> None:
    result = _calculate(refrigerant_code="HFC-134a")
    assert result.formula_id == FORMULA_ID
    assert result.formula_version == "1.0"
    assert result.gwp_source_reference_id
    assert result.calculation_trace
    assert result.reporting_year == 2026
    assert result.reporting_period_id == "period-2026"
    missing_period = _calculate(reporting_year=None, reporting_period_id="")
    assert missing_period.calculation_status == STATUS_BLOCKED_INVALID_PERIOD
    assert missing_period.calculated_kgco2e is None
    period_id_only = _calculate(reporting_year=None, reporting_period_id="period-2026")
    assert period_id_only.calculation_status == STATUS_BLOCKED_INVALID_PERIOD
    assert period_id_only.calculated_kgco2e is None


def test_moenv_ods_gwp_matches_refrigerant_registry() -> None:
    assert ODS_PATH.is_file()
    expected = {
        "HFC-32": Decimal("677"),
        "HFC-125": Decimal("3170"),
        "HFC-134a": Decimal("1300"),
        "HFC-143a": Decimal("4800"),
    }
    ods_values = _ods_hfc_gwp(ODS_PATH)
    for gas, value in expected.items():
        assert ods_values[gas] == value
    registry = validate_factor_registry(REFERENCE_DIR)
    assert registry.issues.empty
    fugitive = registry.gwp_values.loc[
        registry.gwp_values["emission_context"] == GWP_CONTEXT_REFRIGERANT_FUGITIVE
    ]
    found = {
        str(row["gas"]): Decimal(str(row["gwp_value"]))
        for _, row in fugitive.iterrows()
    }
    assert found == expected
    combustion = registry.gwp_values.loc[
        registry.gwp_values["emission_context"] == GWP_CONTEXT_FUEL_COMBUSTION
    ]
    combustion_values = {
        str(row["gas"]): Decimal(str(row["gwp_value"]))
        for _, row in combustion.iterrows()
    }
    assert combustion_values == {
        "CO2": Decimal("1"),
        "CH4": Decimal("28"),
        "N2O": Decimal("265"),
    }


def test_caller_cannot_override_gwp() -> None:
    result = _calculate(gwp_value=1, refrigerant_gwp=1)
    assert result.gwp_value == 1300.0
    assert result.calculated_kgco2e == 19500.0


def test_missing_evidence_is_blocked() -> None:
    result = _calculate(source_document_id="", evidence_reference="")
    assert result.calculation_status == STATUS_BLOCKED_MISSING_EVIDENCE
    assert result.calculated_kgco2e is None
    assert result.calculated_tco2e is None
    by_evidence = _calculate(
        source_document_id="", evidence_reference="maint-log-2026"
    )
    assert by_evidence.calculation_status == STATUS_CALCULATED
    assert by_evidence.calculated_kgco2e == 19500.0


def test_blank_record_id_is_blocked() -> None:
    result = _calculate(record_id="")
    assert result.calculation_status == STATUS_BLOCKED_MISSING_RECORD_ID
    assert result.calculation_id != "calc_unknown"
    assert result.calculation_status != STATUS_CALCULATED
    assert result.calculated_kgco2e is None
    assert result.calculated_tco2e is None


def test_gwp_not_applicable_before_valid_from_year() -> None:
    too_early = _calculate(reporting_year=2023)
    assert too_early.calculation_status == STATUS_BLOCKED_MISSING_GWP
    assert too_early.calculated_kgco2e is None
    assert too_early.calculated_tco2e is None
    current = _calculate(reporting_year=2026)
    assert current.calculation_status == STATUS_CALCULATED
    assert current.calculated_kgco2e == 19500.0
    assert current.calculated_tco2e == 19.5


def _hfc134a_versions(gwp_values: pd.DataFrame) -> pd.DataFrame:
    """Same AR5 GWP 1300 with dated versions; formula values are unchanged."""
    base = gwp_values.loc[
        (gwp_values["gas"] == "HFC-134a")
        & (gwp_values["emission_context"] == GWP_CONTEXT_REFRIGERANT_FUGITIVE)
    ].iloc[0]
    others = gwp_values.loc[gwp_values["gwp_id"] != base["gwp_id"]].copy()
    versions = []
    for gwp_id, valid_from, valid_to in (
        ("gwp_ar5_hfc134a_2023", "2023-01-01", "2023-12-31"),
        ("gwp_ar5_hfc134a_2024h1", "2024-01-01", "2024-06-30"),
        ("gwp_ar5_hfc134a_2024h2", "2024-07-01", "2024-12-31"),
    ):
        row = base.to_dict()
        row["gwp_id"] = gwp_id
        row["gwp_value"] = "1300"
        row["valid_from"] = valid_from
        row["valid_to"] = valid_to
        versions.append(row)
    return pd.concat([others, pd.DataFrame(versions)], ignore_index=True)


def test_refrigerant_gwp_uses_actual_activity_date_within_same_year() -> None:
    compositions, gwp_values = _inputs()
    dated = _hfc134a_versions(gwp_values)
    early = select_gwp_row(
        dated,
        gas="HFC-134a",
        emission_context=GWP_CONTEXT_REFRIGERANT_FUGITIVE,
        activity_date="2024-03-15",
    )
    late = select_gwp_row(
        dated,
        gas="HFC-134a",
        emission_context=GWP_CONTEXT_REFRIGERANT_FUGITIVE,
        activity_date="2024-09-01",
    )
    assert early is not None
    assert late is not None
    assert early["gwp_id"] == "gwp_ar5_hfc134a_2024h1"
    assert late["gwp_id"] == "gwp_ar5_hfc134a_2024h2"
    assert str(early["gwp_value"]) == "1300"
    assert str(late["gwp_value"]) == "1300"

    march = calculate_actual_refill(
        _base_record(
            reporting_year=2024,
            activity_end_date="2024-03-15",
        ),
        compositions=compositions,
        gwp_values=dated,
    )
    september = calculate_actual_refill(
        _base_record(
            reporting_year=2024,
            actual_refill_date="2024-09-01",
        ),
        compositions=compositions,
        gwp_values=dated,
    )
    assert march.calculation_status == STATUS_CALCULATED
    assert september.calculation_status == STATUS_CALCULATED
    assert march.gwp_id == "gwp_ar5_hfc134a_2024h1"
    assert september.gwp_id == "gwp_ar5_hfc134a_2024h2"
    assert march.gwp_value == 1300.0
    assert september.gwp_value == 1300.0
    assert march.calculated_kgco2e == 19500.0
    assert "activity_date" in march.calculation_trace
    assert "2024-12-31" not in march.calculation_trace


def test_year_only_gwp_fallback_fails_closed_when_two_versions_share_year() -> None:
    compositions, gwp_values = _inputs()
    dated = _hfc134a_versions(gwp_values)
    year_only = select_gwp_row(
        dated,
        gas="HFC-134a",
        emission_context=GWP_CONTEXT_REFRIGERANT_FUGITIVE,
        reporting_year=2024,
    )
    assert year_only is None
    result = calculate_actual_refill(
        _base_record(reporting_year=2024),
        compositions=compositions,
        gwp_values=dated,
    )
    assert result.calculation_status == STATUS_BLOCKED_MISSING_GWP
    assert result.calculated_kgco2e is None
    looked_up = lookup_refrigerant_ar5_gwp(
        "R-134a",
        compositions=compositions,
        gwp_values=dated,
        reporting_year=2024,
    )
    assert looked_up is None


def test_old_year_recalc_uses_then_valid_gwp_version() -> None:
    compositions, gwp_values = _inputs()
    dated = _hfc134a_versions(gwp_values)
    selected = select_gwp_row(
        dated,
        gas="HFC-134a",
        emission_context=GWP_CONTEXT_REFRIGERANT_FUGITIVE,
        activity_date="2023-06-01",
    )
    assert selected is not None
    assert selected["gwp_id"] == "gwp_ar5_hfc134a_2023"
    result = calculate_actual_refill(
        _base_record(
            reporting_year=2023,
            activity_end_date="2023-06-01",
        ),
        compositions=compositions,
        gwp_values=dated,
    )
    assert result.calculation_status == STATUS_CALCULATED
    assert result.gwp_id == "gwp_ar5_hfc134a_2023"
    assert result.gwp_value == 1300.0
    assert result.calculated_kgco2e == 19500.0
    later_activity = calculate_actual_refill(
        _base_record(
            reporting_year=2024,
            activity_end_date="2024-03-15",
        ),
        compositions=compositions,
        gwp_values=dated,
    )
    assert later_activity.gwp_id == "gwp_ar5_hfc134a_2024h1"
    assert later_activity.gwp_id != result.gwp_id


def _hfc134a_windows(
    gwp_values: pd.DataFrame,
    windows: tuple[tuple[str, str, str], ...],
) -> pd.DataFrame:
    base = gwp_values.loc[
        (gwp_values["gas"] == "HFC-134a")
        & (gwp_values["emission_context"] == GWP_CONTEXT_REFRIGERANT_FUGITIVE)
    ].iloc[0]
    others = gwp_values.loc[gwp_values["gwp_id"] != base["gwp_id"]].copy()
    rows = []
    for gwp_id, valid_from, valid_to in windows:
        row = base.to_dict()
        row["gwp_id"] = gwp_id
        row["gwp_value"] = "1300"
        row["valid_from"] = valid_from
        row["valid_to"] = valid_to
        rows.append(row)
    return pd.concat([others, pd.DataFrame(rows)], ignore_index=True)


def _single_hfc134a(
    gwp_values: pd.DataFrame,
    *,
    gwp_id: str,
    valid_from: str,
    valid_to: str,
) -> pd.DataFrame:
    return _hfc134a_windows(gwp_values, ((gwp_id, valid_from, valid_to),))


def _select_hfc134a(
    gwp_values: pd.DataFrame,
    *,
    reporting_year: int | None = None,
    activity_date: str | None = None,
):
    return select_gwp_row(
        gwp_values,
        gas="HFC-134a",
        emission_context=GWP_CONTEXT_REFRIGERANT_FUGITIVE,
        reporting_year=reporting_year,
        activity_date=activity_date,
    )


def test_year_fallback_rejects_unique_future_gwp() -> None:
    _, gwp_values = _inputs()
    dated = _single_hfc134a(
        gwp_values,
        gwp_id="gwp_ar5_hfc134a_future",
        valid_from="2026-01-01",
        valid_to="2030-12-31",
    )
    assert _select_hfc134a(dated, reporting_year=2025) is None
    assert _select_hfc134a(dated) is not None


def test_year_fallback_rejects_unique_expired_gwp() -> None:
    _, gwp_values = _inputs()
    dated = _single_hfc134a(
        gwp_values,
        gwp_id="gwp_ar5_hfc134a_expired",
        valid_from="2020-01-01",
        valid_to="2024-12-31",
    )
    assert _select_hfc134a(dated, reporting_year=2025) is None


def test_year_fallback_rejects_unique_midyear_gwp() -> None:
    _, gwp_values = _inputs()
    dated = _single_hfc134a(
        gwp_values,
        gwp_id="gwp_ar5_hfc134a_midyear",
        valid_from="2025-07-01",
        valid_to="2025-12-31",
    )
    assert _select_hfc134a(dated, reporting_year=2025) is None
    selected = _select_hfc134a(dated, activity_date="2025-08-01")
    assert selected is not None
    assert selected["gwp_id"] == "gwp_ar5_hfc134a_midyear"


def test_year_fallback_selects_unique_full_year_gwp() -> None:
    _, gwp_values = _inputs()
    dated = _single_hfc134a(
        gwp_values,
        gwp_id="gwp_ar5_hfc134a_2025",
        valid_from="2025-01-01",
        valid_to="2025-12-31",
    )
    selected = _select_hfc134a(dated, reporting_year=2025)
    assert selected is not None
    assert selected["gwp_id"] == "gwp_ar5_hfc134a_2025"
    assert str(selected["gwp_value"]) == "1300"


def test_year_fallback_rejects_two_full_year_versions() -> None:
    _, gwp_values = _inputs()
    dated = _hfc134a_windows(
        gwp_values,
        (
            ("gwp_ar5_hfc134a_open", "2024-01-01", ""),
            ("gwp_ar5_hfc134a_also_2025", "2020-01-01", "2030-12-31"),
        ),
    )
    assert _select_hfc134a(dated, reporting_year=2025) is None


def test_activity_date_still_selects_covering_version() -> None:
    _, gwp_values = _inputs()
    dated = _hfc134a_windows(
        gwp_values,
        (
            ("gwp_ar5_hfc134a_2025h1", "2025-01-01", "2025-06-30"),
            ("gwp_ar5_hfc134a_2025h2", "2025-07-01", "2025-12-31"),
        ),
    )
    early = _select_hfc134a(dated, activity_date="2025-03-15")
    late = _select_hfc134a(dated, activity_date="2025-09-01")
    assert early is not None
    assert late is not None
    assert early["gwp_id"] == "gwp_ar5_hfc134a_2025h1"
    assert late["gwp_id"] == "gwp_ar5_hfc134a_2025h2"
    assert _select_hfc134a(dated, reporting_year=2025) is None


def test_ipcc_composition_source_uses_official_url() -> None:
    refs = pd.read_csv(
        REFERENCE_DIR / "regulatory_references.csv", dtype=str, keep_default_na=False
    )
    row = refs.loc[refs["reference_id"] == "ref_ipcc_2006_vol3_ch7"].iloc[0]
    assert row["source_location"].startswith("https://www.ipcc-nggip.iges.or.jp/")
    assert row["source_location"].endswith("V3_7_Ch7_ODS_Substitutes.pdf")


def _ods_hfc_gwp(path: Path) -> dict[str, Decimal]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    sheet = None
    for table in root.findall(f".//{{{TABLE_NS}}}table"):
        if table.get(f"{{{TABLE_NS}}}name") == "附表四":
            sheet = table
            break
    assert sheet is not None
    found: dict[str, Decimal] = {}
    for index, row in enumerate(sheet.findall(f"{{{TABLE_NS}}}table-row"), start=1):
        cells: list[str] = []
        for cell in row.findall(f"{{{TABLE_NS}}}table-cell"):
            repeat = int(cell.get(f"{{{TABLE_NS}}}number-columns-repeated", "1"))
            parts = [
                "".join(paragraph.itertext())
                for paragraph in cell.findall(f".//{{{TEXT_NS}}}p")
            ]
            text = " ".join(parts).strip()
            cells.extend([text] * min(repeat, 8))
        if len(cells) < 3:
            continue
        label, raw_gwp = cells[0], cells[2]
        for gas in ("HFC-32", "HFC-125", "HFC-134a", "HFC-143a"):
            if f"（{gas}）" in label or f"({gas})" in label:
                found[gas] = Decimal(raw_gwp.replace(",", ""))
                assert index in {9, 11, 13, 15}
    return found
