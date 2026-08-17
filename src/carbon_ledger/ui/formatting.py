"""Presentation-only number formatting for SaaS UI.

Does not alter underlying calculation values.
"""

from __future__ import annotations

from typing import Any


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def format_int(value: Any) -> str:
    """Format an integer with thousands separators."""
    number = _as_float(value)
    if number is None:
        return "—"
    return f"{int(round(number)):,}"


def format_ratio(done: int, total: int) -> str:
    """Format completion as ``36 / 72``."""
    return f"{format_int(done)} / {format_int(total)}"


def format_percent(value: float, *, digits: int = 0) -> str:
    """Format a percentage without unnecessary precision."""
    if digits <= 0:
        return f"{int(round(value))}%"
    return f"{value:.{digits}f}%"


def format_tco2e_parts(value: Any) -> tuple[str, str]:
    """Return (amount, unit) for emissions display.

    Large values use thousands separators without excess decimals.
    """
    number = _as_float(value)
    if number is None:
        return "—", "tCO₂e"
    abs_number = abs(number)
    if abs_number >= 100:
        amount = f"{number:,.0f}"
    elif abs_number >= 10:
        amount = f"{number:,.1f}"
    else:
        amount = f"{number:,.2f}"
    return amount, "tCO₂e"


RESULT_TCO2E_DECIMALS = 2


def format_result_tco2e_amount(value: Any) -> str:
    """Always two decimal places for analysis-result tCO2e KPIs."""
    number = _as_float(value)
    if number is None:
        return "—"
    return f"{number:,.{RESULT_TCO2E_DECIMALS}f}"


def format_tco2e(value: Any) -> str:
    """Single-line emissions label such as ``5,311 tCO₂e``."""
    amount, unit = format_tco2e_parts(value)
    if amount == "—":
        return "—"
    return f"{amount} {unit}"


def format_activity_amount(value: Any) -> str:
    """Format activity quantities with thousands separators."""
    number = _as_float(value)
    if number is None:
        return "—"
    if abs(number) >= 100:
        return f"{number:,.0f}"
    if float(number).is_integer():
        return f"{int(number):,}"
    return f"{number:,.4g}"
