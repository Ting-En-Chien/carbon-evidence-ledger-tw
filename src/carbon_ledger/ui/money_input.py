"""Business-friendly Taiwan dollar input helpers (UI only)."""

from __future__ import annotations

from typing import Any

# Display units → multiplier to TWD (元).
MONEY_UNIT_MULTIPLIERS: dict[str, int] = {
    "yuan": 1,
    "wan": 10_000,
    "yi": 100_000_000,
}


def money_unit_options() -> list[str]:
    return ["yi", "wan", "yuan"]


def normalize_money_to_twd(
    amount: float | int | None,
    unit: str,
) -> int | None:
    """Convert a unit-aware amount to integer TWD, or None if unknown/blank."""
    if amount is None:
        return None
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    mult = MONEY_UNIT_MULTIPLIERS.get(str(unit), 1)
    # Treat exact zero as unknown — never invent a fabricated zero threshold.
    if value == 0:
        return None
    return int(round(value * mult))


def twd_to_display_parts(twd: int | None) -> tuple[float | None, str]:
    """Pick a convenient unit for editing an existing TWD value."""
    if twd is None:
        return None, "yi"
    if twd >= 100_000_000 and twd % 100_000_000 == 0:
        return float(twd // 100_000_000), "yi"
    if twd >= 10_000 and twd % 10_000 == 0:
        return float(twd // 10_000), "wan"
    return float(twd), "yuan"


def format_twd_display(twd: int | None, *, lang: str = "zh-TW") -> str:
    if twd is None:
        return "—" if lang.startswith("zh") else "—"
    formatted = f"{twd:,}"
    if lang.startswith("zh"):
        return f"NT${formatted}"
    return f"NT${formatted}"


def parse_optional_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    return value
