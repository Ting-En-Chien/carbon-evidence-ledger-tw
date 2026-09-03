"""Actual-refill refrigerant fugitive calculation (Scope 1).

V1 accepts verified refill mass only. Equipment leak-rate estimation is not
implemented and must not be mixed with this method.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from carbon_ledger.calculate import OUTPUT_COLUMNS
from carbon_ledger.factors import (
    GWP_CONTEXT_REFRIGERANT_FUGITIVE,
    READY_GWP_STATUS,
    load_gwp_values,
    select_gwp_row,
)

FORMULA_ID = "refrigerant_actual_refill_times_ar5_gwp"
FORMULA_VERSION = "1.0"
ACTIVITY_TYPE = "refrigerant_refill"
METHOD_ID = "actual_refill_mass_balance"
EMISSION_FORM = "fugitive_emission"
GHG_SCOPE = "scope_1"
ASSESSMENT_BASIS = "IPCC AR5 100-year GWP"
NORMALIZED_UNIT = "kg"

STATUS_CALCULATED = "calculated"
STATUS_CONFIRMED_NO_REFILL = "confirmed_no_refill"
STATUS_BLOCKED_MISSING_QUANTITY = "blocked_missing_refill_quantity"
STATUS_BLOCKED_UNCONFIRMED_ZERO = "blocked_unconfirmed_zero_refill"
STATUS_BLOCKED_UNKNOWN_REFRIGERANT = "blocked_unknown_refrigerant"
STATUS_BLOCKED_MISSING_GWP = "blocked_missing_gwp"
STATUS_BLOCKED_INCOMPLETE_COMPOSITION = "blocked_incomplete_composition"
STATUS_BLOCKED_INVALID_QUANTITY = "blocked_invalid_quantity"
STATUS_BLOCKED_INVALID_PERIOD = "blocked_invalid_reporting_period"
STATUS_BLOCKED_MISSING_EVIDENCE = "blocked_missing_evidence"
STATUS_BLOCKED_MISSING_RECORD_ID = "blocked_missing_record_id"
STATUS_BLOCKED_GWP_NOT_APPLICABLE = "blocked_gwp_not_applicable_to_period"

COMPOSITION_COLUMNS = [
    "refrigerant_code",
    "component_gas",
    "mass_fraction",
    "composition_status",
    "source_reference_id",
    "source_locator",
    "valid_from",
    "notes",
]

_REFRIGERANT_ALIASES = {
    "R-134A": "R-134A",
    "R134A": "R-134A",
    "HFC-134A": "R-134A",
    "HFC134A": "R-134A",
    "R-32": "R-32",
    "R32": "R-32",
    "HFC-32": "R-32",
    "HFC32": "R-32",
    "R-410A": "R-410A",
    "R410A": "R-410A",
}


class RefrigerantRegistryError(ValueError):
    """Raised when the refrigerant composition registry cannot be used."""


@dataclass(frozen=True)
class RefrigerantComponent:
    refrigerant_code: str
    component_gas: str
    mass_fraction: Decimal
    composition_status: str
    source_reference_id: str
    source_locator: str


@dataclass(frozen=True)
class RefrigerantGwp:
    refrigerant_code: str
    gwp_value: Decimal
    gwp_id: str
    gwp_source_reference_id: str
    composition_source_reference_id: str
    valid_from_year: int | None
    weighted_formula: str
    components: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class RefrigerantCalculationResult:
    """Typed result aligned with calculation OUTPUT_COLUMNS plus refrigerant fields."""

    calculation_id: str
    record_id: str
    activity_type: str
    normalized_value: float | None
    normalized_unit: str
    calculated_kgco2e: float | None
    calculated_tco2e: float | None
    calculation_status: str
    calculation_reason: str
    formula_id: str
    formula_version: str
    gwp_id: str
    gwp_value: float | None
    gwp_source_reference_id: str
    refrigerant_code: str
    reporting_year: int | None
    reporting_period_id: str
    ghg_scope: str
    emission_form: str
    method_id: str
    source_document_id: str
    evidence_reference: str
    calculation_trace: str
    factor_id: str
    source_reference_id: str

    def to_calculation_row(self) -> dict[str, Any]:
        row = {column: pd.NA for column in OUTPUT_COLUMNS}
        row.update(
            {
                "calculation_id": self.calculation_id,
                "record_id": self.record_id,
                "activity_type": self.activity_type,
                "normalized_value": _optional_number(self.normalized_value),
                "normalized_unit": self.normalized_unit or pd.NA,
                "factor_id": self.factor_id or pd.NA,
                "factor_value": _optional_number(self.gwp_value),
                "source_reference_id": self.source_reference_id or pd.NA,
                "formula_id": self.formula_id or pd.NA,
                "formula_version": self.formula_version or pd.NA,
                "gwp_source_reference_id": self.gwp_source_reference_id or pd.NA,
                "calculation_trace": self.calculation_trace or pd.NA,
                "calculated_kgco2e": _optional_number(self.calculated_kgco2e),
                "calculated_tco2e": _optional_number(self.calculated_tco2e),
                "calculation_status": self.calculation_status,
                "calculation_reason": self.calculation_reason,
                "gwp_id": self.gwp_id,
                "gwp_value": _optional_number(self.gwp_value),
                "refrigerant_code": self.refrigerant_code,
                "reporting_year": self.reporting_year
                if self.reporting_year is not None
                else pd.NA,
                "reporting_period_id": self.reporting_period_id,
                "ghg_scope": self.ghg_scope,
                "emission_form": self.emission_form,
                "method_id": self.method_id,
                "source_document_id": self.source_document_id,
                "evidence_reference": self.evidence_reference,
            }
        )
        return row


def _optional_number(value: float | None) -> Any:
    if value is None:
        return pd.NA
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _is_confirmed(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    return _text(value).lower() in {"true", "1", "yes", "是"}


def canonicalize_refrigerant_code(raw: Any) -> str | None:
    """Map known name variants. Unknown codes are not guessed."""
    token = _text(raw).upper().replace(" ", "").replace("_", "-")
    while "--" in token:
        token = token.replace("--", "-")
    if not token:
        return None
    return _REFRIGERANT_ALIASES.get(token)


def _coerce_reporting_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, bool) or pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        year = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 1900 <= year <= 2100:
        return year
    return None


def _reporting_year_is_valid(reporting_year: Any) -> bool:
    return _coerce_reporting_year(reporting_year) is not None


def _valid_from_year(value: Any) -> int | None:
    text = _text(value)
    if len(text) < 4:
        return None
    try:
        year = int(text[:4])
    except ValueError:
        return None
    if 1900 <= year <= 2100:
        return year
    return None


def derived_blend_gwp_id(refrigerant_code: str) -> str:
    """Stable derived identifier for a weighted blend GWP."""
    canonical = canonicalize_refrigerant_code(refrigerant_code)
    slug = (canonical or refrigerant_code).lower().replace("-", "")
    return f"gwp_ar5_{slug}_weighted"


def _parse_mass_fraction(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    text = _text(value)
    if not text:
        return None
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number <= 0 or number > 1:
        return None
    return number


def _parse_quantity(value: Any) -> Decimal | None | str:
    """Return Decimal, None if blank, or 'invalid' for NaN/Inf/negative/unparseable."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "invalid"
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return "invalid"
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = _text(value)
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"nan", "inf", "+inf", "-inf", "infinity", "-infinity"}:
        return "invalid"
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        return "invalid"
    if not number.is_finite() or number < 0:
        return "invalid"
    return number


def load_refrigerant_compositions(reference_directory: Path) -> pd.DataFrame:
    path = Path(reference_directory) / "refrigerant_compositions.csv"
    if not path.is_file():
        raise RefrigerantRegistryError(
            "refrigerant_compositions.csv is missing from the reference directory."
        )
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [column for column in COMPOSITION_COLUMNS if column not in frame.columns]
    if missing:
        raise RefrigerantRegistryError(
            "refrigerant_compositions.csv missing columns: " + ", ".join(missing)
        )
    return frame


def validate_refrigerant_compositions(frame: pd.DataFrame) -> None:
    """Fractions must be unique, positive, and sum to exactly 1 per refrigerant."""
    if frame.empty:
        raise RefrigerantRegistryError("refrigerant_compositions.csv has no rows.")
    grouped: dict[str, list[tuple[str, Decimal]]] = {}
    for offset, row in enumerate(frame.to_dict(orient="records")):
        code = canonicalize_refrigerant_code(row.get("refrigerant_code"))
        gas = _text(row.get("component_gas"))
        status = _text(row.get("composition_status"))
        fraction = _parse_mass_fraction(row.get("mass_fraction"))
        if code is None or not gas or status != READY_GWP_STATUS or fraction is None:
            raise RefrigerantRegistryError(
                f"Invalid refrigerant composition row {offset + 1}."
            )
        grouped.setdefault(code, [])
        gases = [item[0] for item in grouped[code]]
        if gas in gases:
            raise RefrigerantRegistryError(
                f"Duplicate component {gas!r} for refrigerant {code}."
            )
        grouped[code].append((gas, fraction))
    for code, parts in grouped.items():
        total = sum((item[1] for item in parts), Decimal("0"))
        if total != Decimal("1"):
            raise RefrigerantRegistryError(
                f"Mass fractions for {code} sum to {total}, not 1."
            )


def _components_for_code(
    compositions: pd.DataFrame, refrigerant_code: str
) -> tuple[RefrigerantComponent, ...]:
    rows = []
    for row in compositions.to_dict(orient="records"):
        code = canonicalize_refrigerant_code(row.get("refrigerant_code"))
        if code != refrigerant_code:
            continue
        fraction = _parse_mass_fraction(row.get("mass_fraction"))
        if fraction is None:
            return ()
        rows.append(
            RefrigerantComponent(
                refrigerant_code=code,
                component_gas=_text(row.get("component_gas")),
                mass_fraction=fraction,
                composition_status=_text(row.get("composition_status")),
                source_reference_id=_text(row.get("source_reference_id")),
                source_locator=_text(row.get("source_locator")),
            )
        )
    if not rows:
        return ()
    total = sum((item.mass_fraction for item in rows), Decimal("0"))
    gases = [item.component_gas for item in rows]
    if (
        total != Decimal("1")
        or len(set(gases)) != len(gases)
        or any(item.mass_fraction <= 0 for item in rows)
        or any(item.composition_status != READY_GWP_STATUS for item in rows)
    ):
        return ()
    return tuple(rows)


def _iso_date(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return text
    return pd.Timestamp(parsed).strftime("%Y-%m-%d")


def _activity_date_from_record(record: Mapping[str, Any]) -> str:
    """Return an actual refill/activity date, never a year-end invented date."""
    for key in ("actual_refill_date", "refill_date", "activity_end_date"):
        text = _iso_date(record.get(key))
        if text:
            return text
    return ""


def lookup_refrigerant_ar5_gwp(
    refrigerant_code: str,
    *,
    compositions: pd.DataFrame,
    gwp_values: pd.DataFrame,
    reporting_year: int | None = None,
    activity_date: str | None = None,
) -> RefrigerantGwp | None:
    """Pure GWP or Σ(mass_fraction × component GWP). No caller GWP override.

    ``activity_date`` is the actual refill or activity_end date when known.
    ``reporting_year`` is a year-granularity fallback only; it is not turned
    into 31 December and is not treated as an activity date.
    """
    canonical = canonicalize_refrigerant_code(refrigerant_code)
    if canonical is None:
        return None
    components = _components_for_code(compositions, canonical)
    if not components:
        return None
    weighted = Decimal("0")
    trace_parts: list[dict[str, str]] = []
    source_ids: list[str] = []
    gwp_ids: list[str] = []
    valid_from_years: list[int] = []
    composition_sources: list[str] = []
    assessment_bases: set[str] = set()
    selected_activity_date = _text(activity_date) or None
    for component in components:
        gwp_row = select_gwp_row(
            gwp_values,
            gas=component.component_gas,
            emission_context=GWP_CONTEXT_REFRIGERANT_FUGITIVE,
            activity_date=selected_activity_date,
            reporting_year=None if selected_activity_date else reporting_year,
        )
        if gwp_row is None:
            return None
        assessment = _text(gwp_row.get("assessment_basis"))
        if assessment:
            assessment_bases.add(assessment)
        if len(assessment_bases) > 1:
            return None
        applicable_from = _valid_from_year(gwp_row.get("valid_from"))
        if applicable_from is None:
            return None
        try:
            gwp_value = Decimal(str(gwp_row.get("gwp_value")).strip())
        except (InvalidOperation, ValueError, TypeError):
            return None
        if not gwp_value.is_finite() or gwp_value <= 0:
            return None
        weighted += component.mass_fraction * gwp_value
        gwp_id = _text(gwp_row.get("gwp_id"))
        source_id = _text(gwp_row.get("source_reference_id"))
        gwp_ids.append(gwp_id)
        source_ids.append(source_id)
        valid_from_years.append(applicable_from)
        composition_sources.append(component.source_reference_id)
        trace_parts.append(
            {
                "gas": component.component_gas,
                "mass_fraction": str(component.mass_fraction),
                "gwp_id": gwp_id,
                "gwp_value": str(gwp_value),
                "valid_from": _text(gwp_row.get("valid_from")),
                "source_reference_id": source_id,
                "composition_source_reference_id": component.source_reference_id,
            }
        )
    if not weighted.is_finite() or weighted <= 0:
        return None
    blend = len(components) > 1
    gwp_id = (
        derived_blend_gwp_id(canonical) if blend else (gwp_ids[0] if gwp_ids else "")
    )
    source_id = source_ids[0] if len(set(source_ids)) == 1 else ""
    composition_source = (
        composition_sources[0] if len(set(composition_sources)) == 1 else ""
    )
    formula = " + ".join(
        f"{item['mass_fraction']} × {item['gwp_value']}" for item in trace_parts
    )
    return RefrigerantGwp(
        refrigerant_code=canonical,
        gwp_value=weighted,
        gwp_id=gwp_id,
        gwp_source_reference_id=source_id,
        composition_source_reference_id=composition_source,
        valid_from_year=max(valid_from_years) if valid_from_years else None,
        weighted_formula=formula,
        components=tuple(trace_parts),
    )


def _dump_trace(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _decimal_to_float(value: Decimal) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise RefrigerantRegistryError("non-finite calculation output")
    return number


def _result(
    *,
    record_id: str,
    status: str,
    reason: str,
    refrigerant_code: str = "",
    reporting_year: int | None = None,
    reporting_period_id: str = "",
    source_document_id: str = "",
    evidence_reference: str = "",
    normalized_value: float | None = None,
    calculated_kgco2e: float | None = None,
    calculated_tco2e: float | None = None,
    gwp: RefrigerantGwp | None = None,
    trace: Mapping[str, Any] | None = None,
) -> RefrigerantCalculationResult:
    gwp_id = gwp.gwp_id if gwp is not None else ""
    gwp_value = _decimal_to_float(gwp.gwp_value) if gwp is not None else None
    gwp_source = gwp.gwp_source_reference_id if gwp is not None else ""
    payload = dict(trace or {})
    payload.setdefault("formula_id", FORMULA_ID)
    payload.setdefault("formula_version", FORMULA_VERSION)
    payload.setdefault("method_id", METHOD_ID)
    payload.setdefault("assessment_basis", ASSESSMENT_BASIS)
    payload.setdefault("emission_context", GWP_CONTEXT_REFRIGERANT_FUGITIVE)
    payload.setdefault("ghg_scope", GHG_SCOPE)
    payload.setdefault("emission_form", EMISSION_FORM)
    payload.setdefault("leak_rate_method_applied", False)
    if gwp is not None:
        payload.setdefault("derived_gwp_id", gwp.gwp_id)
        payload.setdefault(
            "component_gwp_ids",
            [item["gwp_id"] for item in gwp.components],
        )
        payload.setdefault(
            "mass_fractions",
            {item["gas"]: item["mass_fraction"] for item in gwp.components},
        )
        payload.setdefault(
            "composition_source_reference_id",
            gwp.composition_source_reference_id,
        )
        payload.setdefault(
            "component_gwp_source_references",
            [item["source_reference_id"] for item in gwp.components],
        )
        payload.setdefault("weighted_formula", gwp.weighted_formula)
        payload.setdefault("weighted_gwp", str(gwp.gwp_value))
        payload.setdefault("components", list(gwp.components))
    return RefrigerantCalculationResult(
        calculation_id=f"calc_{record_id}" if record_id else "",
        record_id=record_id,
        activity_type=ACTIVITY_TYPE,
        normalized_value=normalized_value,
        normalized_unit=NORMALIZED_UNIT,
        calculated_kgco2e=calculated_kgco2e,
        calculated_tco2e=calculated_tco2e,
        calculation_status=status,
        calculation_reason=reason,
        formula_id=FORMULA_ID,
        formula_version=FORMULA_VERSION,
        gwp_id=gwp_id,
        gwp_value=gwp_value,
        gwp_source_reference_id=gwp_source,
        refrigerant_code=refrigerant_code,
        reporting_year=reporting_year,
        reporting_period_id=reporting_period_id,
        ghg_scope=GHG_SCOPE,
        emission_form=EMISSION_FORM,
        method_id=METHOD_ID,
        source_document_id=source_document_id,
        evidence_reference=evidence_reference,
        calculation_trace=_dump_trace(payload),
        factor_id=gwp_id,
        source_reference_id=gwp_source,
    )


def calculate_actual_refill(
    record: Mapping[str, Any],
    *,
    compositions: pd.DataFrame,
    gwp_values: pd.DataFrame,
) -> RefrigerantCalculationResult:
    """Calculate Scope 1 fugitive emissions from confirmed refill mass only."""
    record_id = _text(record.get("record_id"))
    reporting_year = _coerce_reporting_year(record.get("reporting_year"))
    reporting_period_id = _text(record.get("reporting_period_id"))
    source_document_id = _text(record.get("source_document_id"))
    evidence_reference = _text(
        record.get("evidence_reference") or record.get("source_reference")
    )
    activity_date = _activity_date_from_record(record)
    common = {
        "record_id": record_id,
        "reporting_year": reporting_year,
        "reporting_period_id": reporting_period_id,
        "source_document_id": source_document_id,
        "evidence_reference": evidence_reference,
    }
    if not record_id:
        return _result(
            status=STATUS_BLOCKED_MISSING_RECORD_ID,
            reason="record_id is required before an actual-refill calculation.",
            **common,
        )
    if not _reporting_year_is_valid(record.get("reporting_year")):
        return _result(
            status=STATUS_BLOCKED_INVALID_PERIOD,
            reason=(
                "A valid reporting_year is required; reporting_period_id "
                "is not enough."
            ),
            **common,
        )
    if not source_document_id and not evidence_reference:
        return _result(
            status=STATUS_BLOCKED_MISSING_EVIDENCE,
            reason=(
                "actual-refill calculation requires source_document_id or "
                "evidence_reference."
            ),
            **common,
        )
    quantity = _parse_quantity(record.get("actual_refill_kg"))
    confirmed = _is_confirmed(record.get("refill_confirmed"))
    if quantity == "invalid":
        return _result(
            status=STATUS_BLOCKED_INVALID_QUANTITY,
            reason="actual_refill_kg is negative, non-finite, or not a number.",
            **common,
        )
    if quantity is None and not confirmed:
        return _result(
            status=STATUS_BLOCKED_MISSING_QUANTITY,
            reason=(
                "No refill quantity was provided and the period was not "
                "confirmed as having no refill."
            ),
            **common,
        )
    if quantity is None and confirmed:
        return _result(
            status=STATUS_BLOCKED_MISSING_QUANTITY,
            reason=(
                "refill_confirmed is true but actual_refill_kg is blank; "
                "confirmed no-refill requires an explicit 0 kg quantity."
            ),
            **common,
        )
    assert isinstance(quantity, Decimal)
    if quantity == 0 and not confirmed:
        return _result(
            status=STATUS_BLOCKED_UNCONFIRMED_ZERO,
            reason=(
                "A 0 kg refill is not treated as zero emissions unless "
                "refill_confirmed is true."
            ),
            normalized_value=0.0,
            **common,
        )
    if quantity == 0 and confirmed:
        canonical = canonicalize_refrigerant_code(record.get("refrigerant_code"))
        gwp = None
        if canonical is not None:
            gwp = lookup_refrigerant_ar5_gwp(
                canonical,
                compositions=compositions,
                gwp_values=gwp_values,
                reporting_year=reporting_year,
                activity_date=activity_date or None,
            )
        return _result(
            status=STATUS_CONFIRMED_NO_REFILL,
            reason="Confirmed that no refrigerant was refilled in this period.",
            refrigerant_code=canonical or "",
            normalized_value=0.0,
            calculated_kgco2e=0.0,
            calculated_tco2e=0.0,
            gwp=gwp,
            trace={
                "actual_refill_kg": "0",
                "refill_confirmed": True,
                "reporting_year": reporting_year,
                "reporting_period_id": reporting_period_id,
            },
            **common,
        )
    if not confirmed:
        return _result(
            status=STATUS_BLOCKED_MISSING_QUANTITY,
            reason=(
                "A refill quantity is present but refill_confirmed is not true, "
                "so the actual-refill method does not calculate."
            ),
            normalized_value=_decimal_to_float(quantity),
            **common,
        )
    canonical = canonicalize_refrigerant_code(record.get("refrigerant_code"))
    if canonical is None:
        return _result(
            status=STATUS_BLOCKED_UNKNOWN_REFRIGERANT,
            reason="Refrigerant code is missing or not in the supported registry.",
            normalized_value=_decimal_to_float(quantity),
            **common,
        )
    components = _components_for_code(compositions, canonical)
    if not components:
        return _result(
            status=STATUS_BLOCKED_INCOMPLETE_COMPOSITION,
            reason=(
                "Refrigerant composition is missing, duplicated, or mass "
                "fractions do not sum to 1."
            ),
            refrigerant_code=canonical,
            normalized_value=_decimal_to_float(quantity),
            **common,
        )
    gwp = lookup_refrigerant_ar5_gwp(
        canonical,
        compositions=compositions,
        gwp_values=gwp_values,
        reporting_year=reporting_year,
        activity_date=activity_date or None,
    )
    if gwp is None:
        return _result(
            status=STATUS_BLOCKED_MISSING_GWP,
            reason=(
                "A ready AR5 GWP in the refrigerant_fugitive context was not "
                "found for every blend component."
            ),
            refrigerant_code=canonical,
            normalized_value=_decimal_to_float(quantity),
            **common,
        )
    if (
        gwp.valid_from_year is None
        or reporting_year is None
        or reporting_year < gwp.valid_from_year
    ):
        return _result(
            status=STATUS_BLOCKED_GWP_NOT_APPLICABLE,
            reason=(
                "The selected AR5 GWP is not applicable to this reporting year."
            ),
            refrigerant_code=canonical,
            normalized_value=_decimal_to_float(quantity),
            gwp=gwp,
            **common,
        )
    kgco2e = quantity * gwp.gwp_value
    tco2e = kgco2e / Decimal("1000")
    return _result(
        status=STATUS_CALCULATED,
        reason=(
            "Calculated as confirmed refill mass × AR5 GWP. This is not an "
            "IFRS S2 completeness conclusion."
        ),
        refrigerant_code=canonical,
        normalized_value=_decimal_to_float(quantity),
        calculated_kgco2e=_decimal_to_float(kgco2e),
        calculated_tco2e=_decimal_to_float(tco2e),
        gwp=gwp,
        trace={
            "actual_refill_kg": str(quantity),
            "refill_confirmed": True,
            "refrigerant_code": canonical,
            "blend_gwp": str(gwp.gwp_value),
            "components": list(gwp.components),
            "calculated_kgco2e": str(kgco2e),
            "calculated_tco2e": str(tco2e),
            "reporting_year": reporting_year,
            "reporting_period_id": reporting_period_id,
            "gwp_date_selection": (
                "activity_date" if activity_date else "reporting_year_granularity"
            ),
            "activity_date": activity_date,
        },
        **common,
    )


def load_refrigerant_calculation_inputs(
    reference_directory: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    compositions = load_refrigerant_compositions(reference_directory)
    validate_refrigerant_compositions(compositions)
    gwp_values = load_gwp_values(reference_directory)
    return compositions, gwp_values
