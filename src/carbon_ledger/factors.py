"""Versioned emission-factor and official-reference registry loaders.

Phase 5A registers verified reference data with units, versions, and missing
conversion requirements. It does not calculate emissions or match factors to
activity records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

EMISSION_FACTOR_COLUMNS = [
    "factor_id",
    "activity_type",
    "combustion_context",
    "gas",
    "factor_value",
    "numerator_unit",
    "denominator_unit",
    "geography",
    "factor_year",
    "valid_from",
    "valid_to",
    "source_reference_id",
    "source_locator",
    "factor_status",
    "required_conversion",
    "notes",
]

GWP_COLUMNS = [
    "gwp_id",
    "gas",
    "gwp_value",
    "assessment_basis",
    "source_reference_id",
    "source_locator",
    "valid_from",
    "notes",
]

REGULATORY_REFERENCE_COLUMNS = [
    "reference_id",
    "framework",
    "title",
    "publisher",
    "identifier",
    "publication_date",
    "effective_from",
    "authority_level",
    "binding_status",
    "source_location",
    "notes",
]

DEPENDENCY_COLUMNS = [
    "dependency_id",
    "activity_type",
    "source_unit",
    "required_target_unit",
    "dependency_type",
    "status",
    "acceptable_evidence",
    "prohibited_fallback",
    "notes",
]

ENGINEERING_CONVERSION_COLUMNS = [
    "conversion_id",
    "source_unit",
    "target_unit",
    "multiplier",
    "conversion_type",
    "source_reference_id",
    "source_locator",
    "status",
    "allowed_use",
    "prohibited_use",
    "notes",
]

ALLOWED_FACTOR_STATUSES = {
    "ready",
    "registered_missing_conversion",
    "inactive",
}

ISSUE_COLUMNS = [
    "table_name",
    "row_number",
    "issue_code",
    "issue_message",
]


@dataclass
class FactorRegistryResult:
    """Loaded registry tables plus validation issues."""

    emission_factors: pd.DataFrame
    gwp_values: pd.DataFrame
    regulatory_references: pd.DataFrame
    calculation_dependencies: pd.DataFrame
    engineering_conversions: pd.DataFrame
    issues: pd.DataFrame


def _empty_issues() -> pd.DataFrame:
    return pd.DataFrame(columns=ISSUE_COLUMNS)


def _issue(
    *,
    table_name: str,
    row_number: int,
    issue_code: str,
    issue_message: str,
) -> dict[str, Any]:
    return {
        "table_name": table_name,
        "row_number": row_number,
        "issue_code": issue_code,
        "issue_message": issue_message,
    }


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip() == ""


def _parse_finite_positive(value: Any) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number <= 0:
        return None
    return number


def _parse_optional_date(value: Any) -> pd.Timestamp | None:
    if _is_blank(value):
        return None
    parsed = pd.to_datetime(str(value).strip(), errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def load_emission_factors(reference_directory: Path) -> pd.DataFrame:
    """Load emission_factors.csv from a reference directory."""
    path = Path(reference_directory) / "emission_factors.csv"
    return _read_csv(path)


def load_gwp_values(reference_directory: Path) -> pd.DataFrame:
    """Load gwp_values.csv from a reference directory."""
    path = Path(reference_directory) / "gwp_values.csv"
    return _read_csv(path)


def load_regulatory_references(reference_directory: Path) -> pd.DataFrame:
    """Load regulatory_references.csv from a reference directory."""
    path = Path(reference_directory) / "regulatory_references.csv"
    return _read_csv(path)


def load_calculation_dependencies(reference_directory: Path) -> pd.DataFrame:
    """Load calculation_dependencies.csv from a reference directory."""
    path = Path(reference_directory) / "calculation_dependencies.csv"
    return _read_csv(path)


def load_engineering_conversions(reference_directory: Path) -> pd.DataFrame:
    """Load engineering_conversions.csv from a reference directory."""
    path = Path(reference_directory) / "engineering_conversions.csv"
    return _read_csv(path)


def _check_required_columns(
    table: pd.DataFrame,
    required: list[str],
    table_name: str,
    issues: list[dict[str, Any]],
) -> bool:
    missing = [column for column in required if column not in table.columns]
    if missing:
        issues.append(
            _issue(
                table_name=table_name,
                row_number=0,
                issue_code="MISSING_REQUIRED_COLUMN",
                issue_message=(
                    f"Missing required columns: {', '.join(missing)}"
                ),
            )
        )
        return False
    return True


def _check_unique_ids(
    table: pd.DataFrame,
    id_column: str,
    table_name: str,
    issues: list[dict[str, Any]],
) -> None:
    seen: dict[str, int] = {}
    for offset, raw_id in enumerate(table[id_column].tolist()):
        row_number = offset + 1
        if _is_blank(raw_id):
            issues.append(
                _issue(
                    table_name=table_name,
                    row_number=row_number,
                    issue_code="EMPTY_ID",
                    issue_message=f"{id_column} is empty.",
                )
            )
            continue
        key = str(raw_id).strip()
        if key in seen:
            issues.append(
                _issue(
                    table_name=table_name,
                    row_number=row_number,
                    issue_code="DUPLICATE_ID",
                    issue_message=(
                        f"Duplicate {id_column} {key!r} "
                        f"(also seen on row {seen[key]})."
                    ),
                )
            )
        else:
            seen[key] = row_number


def validate_factor_registry(reference_directory: Path) -> FactorRegistryResult:
    """Load and validate the factor registry without calculating."""
    reference_path = Path(reference_directory)
    issues: list[dict[str, Any]] = []

    emission_factors = load_emission_factors(reference_path)
    gwp_values = load_gwp_values(reference_path)
    regulatory_references = load_regulatory_references(reference_path)
    calculation_dependencies = load_calculation_dependencies(reference_path)
    engineering_conversions = load_engineering_conversions(reference_path)

    factors_ok = _check_required_columns(
        emission_factors, EMISSION_FACTOR_COLUMNS, "emission_factors", issues
    )
    gwp_ok = _check_required_columns(
        gwp_values, GWP_COLUMNS, "gwp_values", issues
    )
    refs_ok = _check_required_columns(
        regulatory_references,
        REGULATORY_REFERENCE_COLUMNS,
        "regulatory_references",
        issues,
    )
    deps_ok = _check_required_columns(
        calculation_dependencies,
        DEPENDENCY_COLUMNS,
        "calculation_dependencies",
        issues,
    )
    conversions_ok = _check_required_columns(
        engineering_conversions,
        ENGINEERING_CONVERSION_COLUMNS,
        "engineering_conversions",
        issues,
    )

    if refs_ok:
        _check_unique_ids(
            regulatory_references,
            "reference_id",
            "regulatory_references",
            issues,
        )
        reference_ids = {
            str(value).strip()
            for value in regulatory_references["reference_id"]
            if not _is_blank(value)
        }
    else:
        reference_ids = set()

    if gwp_ok:
        _check_unique_ids(gwp_values, "gwp_id", "gwp_values", issues)
        for offset, row in enumerate(gwp_values.to_dict(orient="records")):
            row_number = offset + 1
            gwp_value = _parse_finite_positive(row.get("gwp_value"))
            if gwp_value is None:
                raw = row.get("gwp_value")
                try:
                    number = float(str(raw).strip())
                    code = (
                        "NON_FINITE_VALUE"
                        if not math.isfinite(number)
                        else "NON_POSITIVE_VALUE"
                    )
                except (TypeError, ValueError):
                    code = "NON_POSITIVE_VALUE"
                issues.append(
                    _issue(
                        table_name="gwp_values",
                        row_number=row_number,
                        issue_code=code,
                        issue_message=(
                            f"gwp_value must be a finite number greater "
                            f"than zero, got {raw!r}."
                        ),
                    )
                )
            source_ref = str(row.get("source_reference_id", "")).strip()
            if source_ref and source_ref not in reference_ids:
                issues.append(
                    _issue(
                        table_name="gwp_values",
                        row_number=row_number,
                        issue_code="MISSING_REFERENCE",
                        issue_message=(
                            f"source_reference_id {source_ref!r} "
                            "does not exist in regulatory_references."
                        ),
                    )
                )

    if deps_ok:
        _check_unique_ids(
            calculation_dependencies,
            "dependency_id",
            "calculation_dependencies",
            issues,
        )
        dependency_activity_types = {
            str(value).strip()
            for value in calculation_dependencies["activity_type"]
            if not _is_blank(value)
        }
    else:
        dependency_activity_types = set()

    if conversions_ok:
        _check_unique_ids(
            engineering_conversions,
            "conversion_id",
            "engineering_conversions",
            issues,
        )
        for offset, row in enumerate(
            engineering_conversions.to_dict(orient="records")
        ):
            row_number = offset + 1
            multiplier = _parse_finite_positive(row.get("multiplier"))
            if multiplier is None:
                raw = row.get("multiplier")
                try:
                    number = float(str(raw).strip())
                    code = (
                        "NON_FINITE_VALUE"
                        if not math.isfinite(number)
                        else "NON_POSITIVE_VALUE"
                    )
                except (TypeError, ValueError):
                    code = "NON_POSITIVE_VALUE"
                issues.append(
                    _issue(
                        table_name="engineering_conversions",
                        row_number=row_number,
                        issue_code=code,
                        issue_message=(
                            f"multiplier must be a finite number greater "
                            f"than zero, got {raw!r}."
                        ),
                    )
                )

            source_ref = str(row.get("source_reference_id", "")).strip()
            if source_ref and source_ref not in reference_ids:
                issues.append(
                    _issue(
                        table_name="engineering_conversions",
                        row_number=row_number,
                        issue_code="MISSING_REFERENCE",
                        issue_message=(
                            f"source_reference_id {source_ref!r} "
                            "does not exist in regulatory_references."
                        ),
                    )
                )

            status = str(row.get("status", "")).strip()
            if status != "ready":
                issues.append(
                    _issue(
                        table_name="engineering_conversions",
                        row_number=row_number,
                        issue_code="INVALID_CONVERSION_STATUS",
                        issue_message=(
                            f"status must equal ready for Phase 7B, "
                            f"got {status!r}."
                        ),
                    )
                )

            if _is_blank(row.get("source_unit")):
                issues.append(
                    _issue(
                        table_name="engineering_conversions",
                        row_number=row_number,
                        issue_code="BLANK_SOURCE_UNIT",
                        issue_message="source_unit must be non-blank.",
                    )
                )
            if _is_blank(row.get("target_unit")):
                issues.append(
                    _issue(
                        table_name="engineering_conversions",
                        row_number=row_number,
                        issue_code="BLANK_TARGET_UNIT",
                        issue_message="target_unit must be non-blank.",
                    )
                )
            if _is_blank(row.get("allowed_use")):
                issues.append(
                    _issue(
                        table_name="engineering_conversions",
                        row_number=row_number,
                        issue_code="BLANK_ALLOWED_USE",
                        issue_message="allowed_use must be non-blank.",
                    )
                )
            if _is_blank(row.get("prohibited_use")):
                issues.append(
                    _issue(
                        table_name="engineering_conversions",
                        row_number=row_number,
                        issue_code="BLANK_PROHIBITED_USE",
                        issue_message="prohibited_use must be non-blank.",
                    )
                )

    if factors_ok:
        _check_unique_ids(
            emission_factors, "factor_id", "emission_factors", issues
        )
        for offset, row in enumerate(emission_factors.to_dict(orient="records")):
            row_number = offset + 1
            factor_value = _parse_finite_positive(row.get("factor_value"))
            if factor_value is None:
                raw = row.get("factor_value")
                try:
                    number = float(str(raw).strip())
                    code = (
                        "NON_FINITE_VALUE"
                        if not math.isfinite(number)
                        else "NON_POSITIVE_VALUE"
                    )
                except (TypeError, ValueError):
                    code = "NON_POSITIVE_VALUE"
                issues.append(
                    _issue(
                        table_name="emission_factors",
                        row_number=row_number,
                        issue_code=code,
                        issue_message=(
                            f"factor_value must be a finite number greater "
                            f"than zero, got {raw!r}."
                        ),
                    )
                )

            source_ref = str(row.get("source_reference_id", "")).strip()
            if source_ref and source_ref not in reference_ids:
                issues.append(
                    _issue(
                        table_name="emission_factors",
                        row_number=row_number,
                        issue_code="MISSING_REFERENCE",
                        issue_message=(
                            f"source_reference_id {source_ref!r} "
                            "does not exist in regulatory_references."
                        ),
                    )
                )

            valid_from = _parse_optional_date(row.get("valid_from"))
            valid_to = _parse_optional_date(row.get("valid_to"))
            if (
                valid_from is not None
                and valid_to is not None
                and valid_to < valid_from
            ):
                issues.append(
                    _issue(
                        table_name="emission_factors",
                        row_number=row_number,
                        issue_code="INVALID_VALIDITY_DATES",
                        issue_message=(
                            "valid_to is earlier than valid_from."
                        ),
                    )
                )

            status = str(row.get("factor_status", "")).strip()
            required_conversion = str(
                row.get("required_conversion", "")
            ).strip()
            activity_type = str(row.get("activity_type", "")).strip()

            if status not in ALLOWED_FACTOR_STATUSES:
                issues.append(
                    _issue(
                        table_name="emission_factors",
                        row_number=row_number,
                        issue_code="INVALID_FACTOR_STATUS",
                        issue_message=(
                            f"factor_status {status!r} is not allowed."
                        ),
                    )
                )

            if status == "ready" and required_conversion != "not_required":
                issues.append(
                    _issue(
                        table_name="emission_factors",
                        row_number=row_number,
                        issue_code="READY_REQUIRES_NOT_REQUIRED_CONVERSION",
                        issue_message=(
                            "A ready factor must have "
                            "required_conversion = not_required."
                        ),
                    )
                )

            if status == "registered_missing_conversion":
                if (
                    _is_blank(required_conversion)
                    or required_conversion == "not_required"
                ):
                    issues.append(
                        _issue(
                            table_name="emission_factors",
                            row_number=row_number,
                            issue_code="MISSING_CONVERSION_REQUIREMENT_NAME",
                            issue_message=(
                                "registered_missing_conversion factors must "
                                "name a conversion requirement."
                            ),
                        )
                    )
                elif activity_type not in dependency_activity_types:
                    issues.append(
                        _issue(
                            table_name="emission_factors",
                            row_number=row_number,
                            issue_code="MISSING_CONVERSION_DEPENDENCY",
                            issue_message=(
                                f"No calculation_dependencies row found for "
                                f"activity_type {activity_type!r}."
                            ),
                        )
                    )

    issue_frame = (
        pd.DataFrame(issues, columns=ISSUE_COLUMNS)
        if issues
        else _empty_issues()
    )
    if not issue_frame.empty:
        issue_frame = issue_frame.sort_values(
            ["table_name", "row_number", "issue_code"],
            kind="mergesort",
        ).reset_index(drop=True)

    return FactorRegistryResult(
        emission_factors=emission_factors,
        gwp_values=gwp_values,
        regulatory_references=regulatory_references,
        calculation_dependencies=calculation_dependencies,
        engineering_conversions=engineering_conversions,
        issues=issue_frame,
    )
