"""Stage 3B deterministic applicability engine (no LLM, no eval/exec).

CompanyProfile + RegulatoryRuleRegistry + RegulatoryFreshness + ReportingYear
→ ApplicabilityAssessment

Does not invent thresholds. Does not crawl live websites.
Does not modify the carbon calculation pipeline.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from carbon_ledger.regulatory_monitor import get_regulatory_freshness
from carbon_ledger.regulatory_registry import (
    load_regulatory_rules,
    load_regulatory_sources,
    operable_rules,
    outranks,
)

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

OBLIGATION_IFRS = "ifrs_s1_s2"
OBLIGATION_GHG_INVENTORY = "ghg_inventory"
OBLIGATION_VERIFICATION = "verification_assurance"
OBLIGATION_CARBON_FEE = "carbon_fee"

OBLIGATION_IDS = (
    OBLIGATION_IFRS,
    OBLIGATION_GHG_INVENTORY,
    OBLIGATION_VERIFICATION,
    OBLIGATION_CARBON_FEE,
)

STATUS_APPLICABLE = "APPLICABLE"
STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"
STATUS_FUTURE_REQUIREMENT = "FUTURE_REQUIREMENT"
STATUS_NEEDS_INFORMATION = "NEEDS_INFORMATION"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
STATUS_NOT_YET_ASSESSED = "NOT_YET_ASSESSED"
STATUS_MANUAL_VERIFICATION_REQUIRED = "MANUAL_VERIFICATION_REQUIRED"
STATUS_REGULATORY_DATA_STALE = "REGULATORY_DATA_STALE"
STATUS_OUT_OF_V1_SCOPE = "OUT_OF_V1_SCOPE"

APPLICABILITY_STATUSES = frozenset(
    {
        STATUS_APPLICABLE,
        STATUS_NOT_APPLICABLE,
        STATUS_FUTURE_REQUIREMENT,
        STATUS_NEEDS_INFORMATION,
        STATUS_NEEDS_REVIEW,
        STATUS_NOT_YET_ASSESSED,
        STATUS_MANUAL_VERIFICATION_REQUIRED,
        STATUS_REGULATORY_DATA_STALE,
        STATUS_OUT_OF_V1_SCOPE,
    }
)

ENTITY_TYPES_V1 = frozenset(
    {
        "general_listed_company",
        "general_otc_company",
        "financial_holding_company",
        "bank",
        "bills_finance_company",
        "securities_firm",
        "futures_commission_merchant",
        "other",
        "unresolved",
    }
)

LISTING_STATUSES = frozenset(
    {
        "TWSE",
        "TPEX",
        "EMERGING",
        "PRIVATE",
        "NOT_APPLICABLE",
        "UNKNOWN",
    }
)

TRI_STATE = frozenset({"YES", "NO", "NOT_SURE", "TRUE", "FALSE", "UNKNOWN", ""})

# Predicates / identifiers the safe evaluator understands.
KNOWN_IDENTIFIERS = frozenset(
    {
        "entity_type",
        "listing_status",
        "listing",
        "paid_in_capital_twd",
        "net_worth_twd",
        "is_fhc_subsidiary",
        "reporting_year",
        "first_application_year",
        "facility_in_taiwan",
        "official_notice_received",
        "share_par",
        "early_adopt",
        "is_listed_otc_securities_firm",
        "is_listed_parent_integrated_sf_sub",
        "is_listed_otc_fcm",
        "is_listed_parent_dedicated_fcm_sub",
        "tw_ifrs_sustainability_applied",
        "fi_tw_ifrs_applied",
        "sf_tw_ifrs_applied",
        "fcm_tw_ifrs_applied",
        "tw_ar_sustainability_chapter_required",
        "art7_2_condition_met",
        "years_since_first_tw_ifrs_application",
        "assurance_ready_at_ar_filing",
        "assured_ghg",
        "ar_ghg",
        "engages_ghg_assurance",
        "deprecated",
        "use_fi_rule_family",
        "use_dedicated_family",
    }
)

# Adoption / population rules used for the IFRS S1/S2 obligation card.
IFRS_ADOPTION_RULE_IDS = frozenset(
    {
        "tw_order_51756_phase1_ge_10bn",
        "tw_order_51756_phase2_5_to_10bn",
        "tw_order_51756_phase3_lt_5bn",
        "tw_fi_fhc_apply_fy2026",
        "tw_fi_bank_listed_or_fhc_sub_fy2026",
        "tw_fi_bank_nonlisted_non_fhc_sub_fy2027",
        "tw_fi_bills_listed_or_fhc_sub_fy2026",
        "tw_sf_order_56095_phase1_ge_10bn",
        "tw_sf_order_56095_phase2_5_to_10bn",
        "tw_sf_order_56095_phase3_lt_5bn",
        "tw_sf_nonlisted_not_in_56095",
        "tw_fcm_order_56096_phase1_ge_10bn",
        "tw_fcm_order_56096_phase2_5_to_10bn",
        "tw_fcm_order_56096_phase3_lt_5bn",
    }
)

IFRS_ASSURANCE_RULE_IDS = frozenset(
    {
        "tw_order_51756_scope12_consolidated_assurance",
        "tw_fi_scope12_assurance",
        "tw_sf_order_56095_scope12_assurance",
        "tw_fcm_order_56096_scope12_assurance",
    }
)

# Sources that gate Taiwan-recognised IFRS *version* conclusions only.
RECOGNISED_VERSION_SOURCE_IDS = frozenset(
    {
        "src_tw_sfb_ifrs_download_area",
        "src_tw_order_11403851755",
        "src_tw_order_11403856094_recognised",
    }
)

VERIFIED_FOR_CONCLUSION = frozenset(
    {
        "VERIFIED_AUTHORITATIVE",
        "VERIFIED_OFFICIAL_GUIDANCE",
    }
)

_YEAR_RE = re.compile(r"^(\d{4})")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompanyProfile:
    """Application-level company profile (not core carbon domain schema)."""

    company_name: str = ""
    jurisdiction: str = "TW"
    reporting_year: int | None = None
    entity_type: str = "unresolved"
    listing_status: str = "UNKNOWN"
    paid_in_capital_twd: int | None = None
    net_worth_twd: int | None = None
    share_par_value_twd: float | None = None
    has_no_par_value_shares: str = "UNKNOWN"  # TRUE/FALSE/UNKNOWN
    is_fhc_subsidiary: str = "UNKNOWN"  # TRUE/FALSE/UNKNOWN
    parent_entity_type: str = ""
    uses_consolidated_financial_statements: str = "UNKNOWN"
    subsidiary_count: int | None = None
    reporting_entities_known: str = "UNKNOWN"
    industry: str = ""
    sasb_industry: str = ""
    has_taiwan_facilities: str = "NOT_SURE"  # YES/NO/NOT_SURE
    number_of_taiwan_facilities: int | None = None
    received_environmental_authority_inventory_notice: str = "NOT_SURE"
    received_verification_requirement: str = "NOT_SURE"
    known_regulated_facility: str = "NOT_SURE"
    early_adopt: bool = False
    first_application_year: int | None = None

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ObligationResult:
    obligation_id: str
    obligation_name: str
    status: str
    effective_reporting_year: int | None = None
    first_filing_year: int | None = None
    reason: str = ""
    missing_information: list[str] = field(default_factory=list)
    next_action: str = ""
    applied_rule_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    official_authority: str = ""
    official_document: str = ""
    citations: list[str] = field(default_factory=list)
    rule_effective_from: str = ""
    rule_version: str = ""
    last_rule_verified_at: str = ""
    regulatory_freshness_status: str = ""
    assessment_generated_at: str = ""
    product_support_status: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApplicabilityAssessment:
    assessment_timestamp: str
    reporting_year: int | None
    company_profile_snapshot: dict[str, Any]
    obligations: dict[str, ObligationResult]
    rule_ids_used: list[str]
    rule_versions_used: dict[str, str]
    regulatory_freshness_snapshot: dict[str, Any]
    result_statuses: dict[str, str]
    disclaimer: str = (
        "Based on the current company profile and verified regulatory rules. "
        "This assessment supports compliance preparation and should be reviewed "
        "where professional judgement is required."
    )

    def obligation(self, obligation_id: str) -> ObligationResult | None:
        return self.obligations.get(obligation_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_timestamp": self.assessment_timestamp,
            "reporting_year": self.reporting_year,
            "company_profile_snapshot": self.company_profile_snapshot,
            "obligations": {
                key: value.to_dict() for key, value in self.obligations.items()
            },
            "rule_ids_used": list(self.rule_ids_used),
            "rule_versions_used": dict(self.rule_versions_used),
            "regulatory_freshness_snapshot": dict(self.regulatory_freshness_snapshot),
            "result_statuses": dict(self.result_statuses),
            "disclaimer": self.disclaimer,
        }


# ---------------------------------------------------------------------------
# Safe condition evaluator (no eval / exec)
# ---------------------------------------------------------------------------


class ConditionEvaluation:
    __slots__ = ("matched", "missing", "unsupported", "error")

    def __init__(
        self,
        *,
        matched: bool | None = None,
        missing: list[str] | None = None,
        unsupported: str = "",
        error: str = "",
    ) -> None:
        self.matched = matched
        self.missing = list(missing or [])
        self.unsupported = unsupported
        self.error = error


def _normalize_listing(value: str) -> str:
    raw = str(value or "").strip().upper().replace(" ", "")
    if raw in {"TPEX", "TPEXOTC", "OTC"}:
        return "TPEx"
    if raw == "TWSE":
        return "TWSE"
    if raw in {"EMERGING", "PRIVATE", "NOT_APPLICABLE", "UNKNOWN", ""}:
        return raw or "UNKNOWN"
    return raw


def _tri_to_bool(value: str) -> bool | None:
    raw = str(value or "").strip().upper()
    if raw in {"TRUE", "YES"}:
        return True
    if raw in {"FALSE", "NO"}:
        return False
    return None


def build_evaluation_context(
    profile: CompanyProfile,
    *,
    derived: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map CompanyProfile → evaluator facts (unknowns stay None)."""
    listing = _normalize_listing(profile.listing_status)
    is_listed = listing in {"TWSE", "TPEx"}
    entity = str(profile.entity_type or "unresolved")
    fhc_sub = _tri_to_bool(profile.is_fhc_subsidiary)
    ctx: dict[str, Any] = {
        "entity_type": entity,
        "listing_status": listing,
        "listing": listing,
        "paid_in_capital_twd": profile.paid_in_capital_twd,
        "net_worth_twd": profile.net_worth_twd,
        "is_fhc_subsidiary": fhc_sub,
        "reporting_year": profile.reporting_year,
        "first_application_year": profile.first_application_year,
        "facility_in_taiwan": _tri_to_bool(profile.has_taiwan_facilities),
        "official_notice_received": _tri_to_bool(
            profile.received_environmental_authority_inventory_notice
        ),
        "early_adopt": bool(profile.early_adopt),
        "is_listed_otc_securities_firm": (
            entity == "securities_firm" and is_listed
        ),
        "is_listed_parent_integrated_sf_sub": False,
        "is_listed_otc_fcm": (
            entity == "futures_commission_merchant" and is_listed
        ),
        "is_listed_parent_dedicated_fcm_sub": False,
        "deprecated": False,
    }
    if profile.has_no_par_value_shares.upper() == "TRUE":
        ctx["share_par"] = "no_par"
    elif profile.share_par_value_twd is not None:
        if float(profile.share_par_value_twd) != 10.0:
            ctx["share_par"] = "not_10"
        else:
            ctx["share_par"] = "10"
    else:
        ctx["share_par"] = None
    if profile.first_application_year and profile.reporting_year:
        ctx["years_since_first_tw_ifrs_application"] = (
            int(profile.reporting_year) - int(profile.first_application_year)
        )
    else:
        ctx["years_since_first_tw_ifrs_application"] = None
    if derived:
        ctx.update(derived)
    return ctx


def _split_top_level(expression: str, separators: tuple[str, ...]) -> list[str] | None:
    """Split on top-level separators; None if parentheses unbalanced."""
    depth = 0
    current: list[str] = []
    parts: list[str] = []
    i = 0
    text = expression.strip()
    # Normalize separators to bare keywords (AND/OR); spaces handled via boundaries.
    bare_seps = tuple(sep.strip().upper() for sep in separators)
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
            current.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            if depth < 0:
                return None
            current.append(ch)
            i += 1
            continue
        if depth == 0:
            matched_sep = None
            for sep in bare_seps:
                if text[i : i + len(sep)].upper() != sep:
                    continue
                prev = text[i - 1] if i > 0 else " "
                nxt = text[i + len(sep)] if i + len(sep) < len(text) else " "
                # Word boundaries: previous/next must not continue an identifier.
                if (prev.isalnum() or prev == "_") or (nxt.isalnum() or nxt == "_"):
                    continue
                matched_sep = sep
                break
            if matched_sep:
                parts.append("".join(current).strip())
                current = []
                i += len(matched_sep)
                continue
        current.append(ch)
        i += 1
    if depth != 0:
        return None
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def _parse_set_literal(raw: str) -> set[str] | None:
    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    inner = text[1:-1].strip()
    if not inner:
        return set()
    return {item.strip() for item in inner.split(",") if item.strip()}


def _missing_for_identifier(name: str) -> str:
    mapping = {
        "paid_in_capital_twd": "paid_in_capital_twd",
        "net_worth_twd": "net_worth_twd",
        "listing": "listing_status",
        "listing_status": "listing_status",
        "is_fhc_subsidiary": "is_fhc_subsidiary",
        "entity_type": "entity_type",
        "reporting_year": "reporting_year",
        "share_par": "share_par_value_twd",
        "first_application_year": "first_application_year",
        "years_since_first_tw_ifrs_application": "first_application_year",
        "facility_in_taiwan": "has_taiwan_facilities",
        "official_notice_received": (
            "received_environmental_authority_inventory_notice"
        ),
    }
    return mapping.get(name, name)


def evaluate_condition(expression: str, context: dict[str, Any]) -> ConditionEvaluation:
    """Safely evaluate a structured applicability_condition_machine string."""
    text = str(expression or "").strip()
    if not text:
        return ConditionEvaluation(matched=True)
    # Routing implications are not boolean adoption predicates.
    if "=>" in text:
        return ConditionEvaluation(
            unsupported="implication_routing",
            error="Unsupported applicability condition requires review.",
        )
    return _eval_or(text, context)


def _eval_or(expression: str, context: dict[str, Any]) -> ConditionEvaluation:
    parts = _split_top_level(expression, (" OR ",))
    if parts is None:
        return ConditionEvaluation(
            unsupported="unbalanced_parentheses",
            error="Unsupported applicability condition requires review.",
        )
    if len(parts) == 1:
        return _eval_and(parts[0], context)
    missing: list[str] = []
    any_true = False
    saw_definite_false = False
    for part in parts:
        result = _eval_and(part, context)
        if result.unsupported or result.error:
            return result
        missing.extend(result.missing)
        if result.matched is True:
            any_true = True
        elif result.matched is False and not result.missing:
            saw_definite_false = True
    if any_true:
        return ConditionEvaluation(matched=True)
    if missing:
        return ConditionEvaluation(matched=None, missing=sorted(set(missing)))
    if saw_definite_false:
        return ConditionEvaluation(matched=False)
    return ConditionEvaluation(matched=None, missing=sorted(set(missing)))


def _eval_and(expression: str, context: dict[str, Any]) -> ConditionEvaluation:
    parts = _split_top_level(expression, (" AND ",))
    if parts is None:
        return ConditionEvaluation(
            unsupported="unbalanced_parentheses",
            error="Unsupported applicability condition requires review.",
        )
    if len(parts) == 1:
        return _eval_atom(parts[0], context)
    missing: list[str] = []
    for part in parts:
        result = _eval_atom(part, context)
        if result.unsupported or result.error:
            return result
        if result.missing:
            missing.extend(result.missing)
            continue
        if result.matched is False:
            return ConditionEvaluation(matched=False)
    if missing:
        return ConditionEvaluation(matched=None, missing=sorted(set(missing)))
    return ConditionEvaluation(matched=True)


def _eval_atom(expression: str, context: dict[str, Any]) -> ConditionEvaluation:
    text = expression.strip()
    if text.startswith("(") and text.endswith(")"):
        # Ensure outer parentheses wrap the whole expression.
        depth = 0
        wraps = True
        for idx, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(text) - 1:
                    wraps = False
                    break
        if wraps and depth == 0:
            return _eval_or(text[1:-1].strip(), context)

    # not ( ... ) or not identifier / membership
    not_match = re.match(r"^not\s+(.+)$", text, flags=re.IGNORECASE)
    if not_match:
        inner = evaluate_condition(not_match.group(1).strip(), context)
        if inner.unsupported or inner.error:
            return inner
        if inner.missing:
            return ConditionEvaluation(matched=None, missing=inner.missing)
        if inner.matched is None:
            return ConditionEvaluation(matched=None, missing=inner.missing)
        return ConditionEvaluation(matched=not bool(inner.matched))

    # membership: name in {a,b} / name not in {a,b}
    mem = re.match(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s+(not\s+)?in\s+(\{[^}]*\})$",
        text,
        flags=re.IGNORECASE,
    )
    if mem:
        name = mem.group(1)
        negated = bool(mem.group(2))
        values = _parse_set_literal(mem.group(3))
        if values is None or name not in KNOWN_IDENTIFIERS:
            return ConditionEvaluation(
                unsupported=name,
                error="Unsupported applicability condition requires review.",
            )
        actual = context.get(name)
        if actual is None or actual == "" or actual == "unresolved":
            return ConditionEvaluation(
                matched=None, missing=[_missing_for_identifier(name)]
            )
        # Boolean membership uses lowercase true/false tokens.
        actual_norm = str(actual)
        if isinstance(actual, bool):
            actual_norm = "true" if actual else "false"
        hit = actual_norm in values or str(actual) in values
        # listing TWSE/TPEx aliases
        if name in {"listing", "listing_status"}:
            hit = _normalize_listing(str(actual)) in {
                _normalize_listing(v) for v in values
            } or hit
        return ConditionEvaluation(matched=(not hit) if negated else hit)

    # chained compare: 5000000000 <= paid_in_capital_twd < 10000000000
    chained = re.match(
        r"^(-?\d+)\s*(<=|<|>=|>)\s*([A-Za-z_][A-Za-z0-9_]*)\s*"
        r"(<=|<|>=|>)\s*(-?\d+)$",
        text,
    )
    if chained:
        left_n = int(chained.group(1))
        left_op = chained.group(2)
        name = chained.group(3)
        right_op = chained.group(4)
        right_n = int(chained.group(5))
        if name not in KNOWN_IDENTIFIERS:
            return ConditionEvaluation(
                unsupported=name,
                error="Unsupported applicability condition requires review.",
            )
        actual = context.get(name)
        if actual is None:
            return ConditionEvaluation(
                matched=None, missing=[_missing_for_identifier(name)]
            )
        try:
            number = float(actual)
        except (TypeError, ValueError):
            return ConditionEvaluation(
                matched=None, missing=[_missing_for_identifier(name)]
            )
        left_ok = _compare(left_n, left_op, number)
        right_ok = _compare(number, right_op, right_n)
        return ConditionEvaluation(matched=bool(left_ok and right_ok))

    # binary compare / equality
    bin_m = re.match(
        r"^([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|<=|>=|<|>|=)\s*(.+)$",
        text,
    )
    if bin_m:
        name = bin_m.group(1)
        op = bin_m.group(2)
        if op == "=":
            op = "=="
        rhs = bin_m.group(3).strip()
        if name not in KNOWN_IDENTIFIERS:
            return ConditionEvaluation(
                unsupported=name,
                error="Unsupported applicability condition requires review.",
            )
        actual = context.get(name)
        if actual is None or actual == "" or actual == "unresolved":
            # Boolean flags may be explicitly False.
            if name.startswith("is_") or name.endswith("_applied") or name in {
                "early_adopt",
                "deprecated",
            }:
                if actual is False:
                    pass
                else:
                    return ConditionEvaluation(
                        matched=None, missing=[_missing_for_identifier(name)]
                    )
            else:
                return ConditionEvaluation(
                    matched=None, missing=[_missing_for_identifier(name)]
                )
        return ConditionEvaluation(matched=_compare_values(actual, op, rhs, name))

    # bare boolean identifier
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
        if text not in KNOWN_IDENTIFIERS:
            return ConditionEvaluation(
                unsupported=text,
                error="Unsupported applicability condition requires review.",
            )
        actual = context.get(text)
        if actual is None:
            return ConditionEvaluation(
                matched=None, missing=[_missing_for_identifier(text)]
            )
        return ConditionEvaluation(matched=bool(actual))

    return ConditionEvaluation(
        unsupported=text[:80],
        error="Unsupported applicability condition requires review.",
    )


def _compare(left: float, op: str, right: float) -> bool:
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return False


def _compare_values(actual: Any, op: str, rhs: str, name: str) -> bool:
    rhs_stripped = rhs.strip().strip('"').strip("'")
    if rhs_stripped.lower() in {"true", "false"}:
        expected = rhs_stripped.lower() == "true"
        actual_bool = bool(actual) if not isinstance(actual, str) else (
            actual.lower() == "true"
        )
        if op == "==":
            return actual_bool is expected
        if op == "!=":
            return actual_bool is not expected
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", rhs_stripped):
        try:
            return _compare(float(actual), op, float(rhs_stripped))
        except (TypeError, ValueError):
            return False
    left = str(actual)
    right = rhs_stripped
    if name in {"listing", "listing_status"}:
        left = _normalize_listing(left)
        right = _normalize_listing(right)
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return False


def assert_no_dynamic_execution() -> None:
    """Guard used by tests — this module must not call eval/exec."""
    source = Path(__file__).read_text(encoding="utf-8")
    # Ban runtime eval/exec call sites (allow this docstring mention).
    for pattern in (r"(?<![A-Za-z_])eval\s*\(", r"(?<![A-Za-z_])exec\s*\("):
        for match in re.finditer(pattern, source):
            line = source[: match.start()].count("\n") + 1
            # Docstring / comment lines are acceptable; executable calls are not.
            line_text = source.splitlines()[line - 1]
            if line_text.lstrip().startswith("#"):
                continue
            if '"""' in line_text or "'''" in line_text:
                continue
            if "must not call eval/exec" in line_text:
                continue
            raise AssertionError(f"Forbidden dynamic execution at line {line}")


# ---------------------------------------------------------------------------
# Rule selection helpers
# ---------------------------------------------------------------------------


def _parse_year(token: str) -> int | None:
    text = str(token or "").strip()
    if not text:
        return None
    match = _YEAR_RE.match(text)
    if not match:
        return None
    return int(match.group(1))


def _rule_valid_for_reporting_year(row: pd.Series, reporting_year: int) -> bool:
    """True when the rule version is in force for the requested reporting year."""
    start = _parse_year(str(row.get("rule_effective_from") or ""))
    end = _parse_year(str(row.get("rule_effective_to") or ""))
    # FUTURE adoption phases often use effective_from = first mandatory FY.
    # A rule remains a candidate for "future requirement" even when start > year.
    if end is not None and reporting_year > end:
        return False
    if start is not None and end is not None:
        return start <= reporting_year <= end
    return True


def _is_verified_for_conclusion(row: pd.Series) -> bool:
    return str(row.get("verification_status") or "") in VERIFIED_FOR_CONCLUSION


def _filing_year_from_title(title: str, effective_year: int | None) -> int | None:
    match = re.search(r"file\s+(?:from\s+)?(\d{4})", title, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    if effective_year is not None:
        return effective_year + 1
    return None


def _obligation_shell(
    obligation_id: str,
    obligation_name: str,
    *,
    status: str,
    reason: str,
    next_action: str = "",
    missing: list[str] | None = None,
    generated_at: str = "",
    freshness: str = "",
) -> ObligationResult:
    return ObligationResult(
        obligation_id=obligation_id,
        obligation_name=obligation_name,
        status=status,
        reason=reason,
        missing_information=list(missing or []),
        next_action=next_action,
        assessment_generated_at=generated_at,
        regulatory_freshness_status=freshness,
    )


def _populate_rule_metadata(
    result: ObligationResult,
    row: pd.Series,
    *,
    freshness: str = "",
) -> ObligationResult:
    result.applied_rule_ids = [str(row.get("rule_id") or "")]
    result.source_ids = [str(row.get("source_id") or "")]
    result.official_authority = str(row.get("authority") or "")
    result.official_document = str(row.get("official_document") or "")
    citation = str(row.get("citation") or "")
    result.citations = [citation] if citation else []
    result.rule_effective_from = str(row.get("rule_effective_from") or "")
    result.rule_version = str(row.get("version") or row.get("source_version") or "")
    result.last_rule_verified_at = str(row.get("last_verified_at") or "")
    result.product_support_status = str(row.get("product_support_status") or "")
    result.regulatory_freshness_status = freshness
    return result


def check_dependency_freshness(
    repo_root: Path,
    source_ids: list[str],
    *,
    freshness_loader=get_regulatory_freshness,
) -> dict[str, Any]:
    """Dependency-aware freshness for the sources a conclusion relies on."""
    required = [sid for sid in source_ids if sid]
    if not required:
        return {
            "analysis_allowed": True,
            "state": "CURRENT",
            "required_source_ids": [],
            "message": "No authoritative source dependency for this conclusion.",
        }
    return freshness_loader(repo_root, required_source_ids=required)


def freshness_blocks_conclusion(freshness: dict[str, Any]) -> str | None:
    """Return a blocking status code, or None when evaluation may proceed."""
    state = str(freshness.get("state") or "")
    if state in {"FRESHNESS_STATE_UNAVAILABLE", "STATE_PERSISTENCE_FAILED"}:
        return STATUS_REGULATORY_DATA_STALE
    if state == "REGULATORY_DATA_STALE":
        return STATUS_REGULATORY_DATA_STALE
    if state == "MANUAL_VERIFICATION_REQUIRED":
        return STATUS_MANUAL_VERIFICATION_REQUIRED
    if state == "SOURCE_CHECK_FAILED":
        return STATUS_REGULATORY_DATA_STALE
    if state == "UPDATE_REQUIRED":
        # CHECK_DUE — allow evaluation but note freshness.
        return None
    return None


# ---------------------------------------------------------------------------
# Obligation assessors
# ---------------------------------------------------------------------------


def _candidate_adoption_rules(
    rules: pd.DataFrame, profile: CompanyProfile
) -> pd.DataFrame:
    operable = operable_rules(rules)
    tw = operable[operable["jurisdiction"].astype(str).str.upper() == "TW"]
    subset = tw[tw["rule_id"].isin(IFRS_ADOPTION_RULE_IDS)].copy()
    entity = str(profile.entity_type or "unresolved")
    if entity and entity != "unresolved":
        mask = subset["entity_type"].astype(str).apply(
            lambda cell: entity in {part.strip() for part in cell.split("|") if part}
            or cell.strip() == entity
        )
        subset = subset[mask]
    return subset


def assess_ifrs_obligation(
    profile: CompanyProfile,
    rules: pd.DataFrame,
    sources: pd.DataFrame,
    *,
    repo_root: Path,
    generated_at: str,
    freshness_loader=get_regulatory_freshness,
) -> ObligationResult:
    name = "IFRS S1/S2"
    if not profile.reporting_year:
        return _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_NEEDS_INFORMATION,
            reason="Reporting year is required to determine IFRS adoption timing.",
            missing=["reporting_year"],
            next_action="Enter the reporting year for this assessment.",
            generated_at=generated_at,
        )
    entity = str(profile.entity_type or "unresolved")
    if entity in {"", "unresolved"}:
        return _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_NEEDS_INFORMATION,
            reason="Entity type is required to select the correct IFRS rule family.",
            missing=["entity_type"],
            next_action="Select the company's market / licence entity type.",
            generated_at=generated_at,
        )
    if entity == "other":
        return _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_NEEDS_REVIEW,
            reason=(
                "Entity type 'other' is outside the verified V1 IFRS adoption "
                "rule families. Manual review against FSC orders is required."
            ),
            next_action="Confirm whether a dedicated FSC order applies.",
            generated_at=generated_at,
        )

    candidates = _candidate_adoption_rules(rules, profile)
    if entity == "futures_commission_merchant":
        # V1 product support: surface OUT_OF_V1_SCOPE rather than silent omit.
        fcm = candidates
        if fcm.empty:
            fcm = rules[
                (rules["rule_id"].isin(IFRS_ADOPTION_RULE_IDS))
                & (rules["entity_type"].astype(str).str.contains("futures"))
            ]
        row = fcm.iloc[0] if not fcm.empty else None
        result = _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_OUT_OF_V1_SCOPE,
            reason=(
                "Futures commission merchant IFRS adoption rules exist in the "
                "registry but are configured as OUT_OF_V1_SCOPE for this product."
            ),
            next_action="Track FCM obligations outside the current V1 workflow.",
            generated_at=generated_at,
        )
        if row is not None:
            _populate_rule_metadata(result, row)
            result.product_support_status = "OUT_OF_V1_SCOPE"
        return result

    if candidates.empty:
        return _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_NEEDS_REVIEW,
            reason=(
                "No verified Taiwan IFRS adoption rule matched this entity type."
            ),
            next_action="Review the regulatory registry with a compliance specialist.",
            generated_at=generated_at,
        )

    ctx = build_evaluation_context(profile)
    matches: list[tuple[pd.Series, ConditionEvaluation]] = []
    needs_info: list[tuple[pd.Series, list[str]]] = []
    unsupported: list[pd.Series] = []
    for _, row in candidates.iterrows():
        if str(row.get("rule_status") or "") == "SUPERSEDED":
            continue
        verification = str(row.get("verification_status") or "")
        if verification == "UNVERIFIED":
            continue
        # Allow explicit NOT_COVERED conclusions; require verified otherwise.
        if verification not in VERIFIED_FOR_CONCLUSION | {
            "NOT_COVERED_BY_CURRENT_ORDER"
        }:
            continue
        machine = str(row.get("applicability_condition_machine") or "")
        evaluation = evaluate_condition(machine, ctx)
        if evaluation.unsupported or evaluation.error:
            unsupported.append(row)
            continue
        if evaluation.missing:
            needs_info.append((row, evaluation.missing))
            continue
        if evaluation.matched is True:
            matches.append((row, evaluation))

    # Non-listed securities firm: explicit NOT_APPLICABLE under Order 56095.
    for row, _ev in matches:
        if str(row.get("rule_id")) == "tw_sf_nonlisted_not_in_56095":
            freshness = check_dependency_freshness(
                repo_root,
                [str(row.get("source_id") or "")],
                freshness_loader=freshness_loader,
            )
            block = freshness_blocks_conclusion(freshness)
            if block:
                result = _obligation_shell(
                    OBLIGATION_IFRS,
                    name,
                    status=block,
                    reason=(
                        "Required official source freshness could not be confirmed "
                        "for this securities-firm conclusion."
                    ),
                    next_action="Update regulatory monitoring state, then reassess.",
                    generated_at=generated_at,
                    freshness=str(freshness.get("state") or ""),
                )
                return _populate_rule_metadata(
                    result, row, freshness=str(freshness.get("state") or "")
                )
            result = _obligation_shell(
                OBLIGATION_IFRS,
                name,
                status=STATUS_NOT_APPLICABLE,
                reason=(
                    "Based on the current company profile and verified regulatory "
                    "rules, non-listed securities firms are not covered by Order "
                    "11403856095 phased IFRS Sustainability Standards adoption."
                ),
                next_action="Confirm listing / parent-integration status if unclear.",
                generated_at=generated_at,
                freshness=str(freshness.get("state") or ""),
            )
            return _populate_rule_metadata(
                result, row, freshness=str(freshness.get("state") or "")
            )

    phase_matches = [
        row
        for row, _ in matches
        if str(row.get("rule_id")) != "tw_sf_nonlisted_not_in_56095"
    ]

    if not phase_matches and needs_info:
        missing = sorted({item for _, items in needs_info for item in items})
        return _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_NEEDS_INFORMATION,
            reason=(
                "Additional company information is required to determine the "
                "IFRS Sustainability Standards adoption phase."
            ),
            missing=missing,
            next_action="Provide the missing company-profile fields listed above.",
            generated_at=generated_at,
        )

    if not phase_matches and unsupported:
        return _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_NEEDS_REVIEW,
            reason="Unsupported applicability condition requires review.",
            next_action="Ask a specialist to interpret the machine condition.",
            generated_at=generated_at,
        )

    if not phase_matches:
        return _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=STATUS_NOT_APPLICABLE,
            reason=(
                "Based on the current company profile and verified regulatory "
                "rules, the company is outside the matched IFRS adoption population."
            ),
            next_action="Confirm entity type and listing status if this seems wrong.",
            generated_at=generated_at,
        )

    # Conflict detection among matched phase rules for the same year.
    reporting_year = int(profile.reporting_year)
    if len(phase_matches) > 1:
        # Prefer higher-authority source when ranks differ; else NEEDS_REVIEW.
        ids = [str(r.get("source_id") or "") for r in phase_matches]
        unique_sources = sorted(set(ids))
        if len(unique_sources) > 1:
            ranked = sorted(
                phase_matches,
                key=lambda r: int(
                    sources.loc[
                        sources["source_id"] == str(r.get("source_id")),
                        "authority_rank",
                    ].iloc[0]
                )
                if str(r.get("source_id")) in set(sources["source_id"])
                else 999,
            )
            top = ranked[0]
            contested = False
            for other in ranked[1:]:
                if not outranks(
                    sources,
                    str(top.get("source_id")),
                    str(other.get("source_id")),
                ):
                    contested = True
                    break
            if contested:
                result = _obligation_shell(
                    OBLIGATION_IFRS,
                    name,
                    status=STATUS_NEEDS_REVIEW,
                    reason=(
                        "Two or more active authoritative IFRS adoption rules "
                        "conflict for this profile."
                    ),
                    next_action="Review the listed rule IDs with a specialist.",
                    generated_at=generated_at,
                )
                result.applied_rule_ids = [
                    str(r.get("rule_id")) for r in phase_matches
                ]
                result.source_ids = sorted(
                    {str(r.get("source_id")) for r in phase_matches}
                )
                return result
            phase_matches = [top]
        else:
            # Same source, multiple phases matched — should not happen; review.
            result = _obligation_shell(
                OBLIGATION_IFRS,
                name,
                status=STATUS_NEEDS_REVIEW,
                reason=(
                    "Multiple IFRS adoption phases matched the same profile; "
                    "manual review is required."
                ),
                next_action="Verify paid-in capital and listing facts.",
                generated_at=generated_at,
            )
            result.applied_rule_ids = [str(r.get("rule_id")) for r in phase_matches]
            return result

    chosen = phase_matches[0]
    source_id = str(chosen.get("source_id") or "")
    freshness = check_dependency_freshness(
        repo_root,
        [source_id],
        freshness_loader=freshness_loader,
    )
    block = freshness_blocks_conclusion(freshness)
    if block:
        result = _obligation_shell(
            OBLIGATION_IFRS,
            name,
            status=block,
            reason=(
                "Required official-source freshness could not be confirmed for "
                "this IFRS adoption conclusion."
            ),
            next_action="Refresh regulatory monitoring state, then reassess.",
            generated_at=generated_at,
            freshness=str(freshness.get("state") or ""),
        )
        return _populate_rule_metadata(
            result, chosen, freshness=str(freshness.get("state") or "")
        )

    effective_year = _parse_year(str(chosen.get("rule_effective_from") or ""))
    title = str(chosen.get("requirement_title") or "")
    filing_year = _filing_year_from_title(title, effective_year)
    if effective_year is not None and reporting_year < effective_year:
        status = STATUS_FUTURE_REQUIREMENT
        reason = (
            "Based on the company's entity type and verified FSC adoption rules, "
            f"mandatory application begins in FY{effective_year}."
        )
        next_action = "Begin readiness work before the first reporting year."
    else:
        status = STATUS_APPLICABLE
        reason = (
            "Based on the current company profile and verified regulatory rules, "
            "the company is within the mandatory Taiwan IFRS Sustainability "
            "Standards adoption population for this reporting year."
        )
        next_action = (
            "Prepare IFRS S1/S2 disclosures for the applicable reporting year."
        )

    result = _obligation_shell(
        OBLIGATION_IFRS,
        name,
        status=status,
        reason=reason,
        next_action=next_action,
        generated_at=generated_at,
        freshness=str(freshness.get("state") or ""),
    )
    result.effective_reporting_year = effective_year
    result.first_filing_year = filing_year
    _populate_rule_metadata(
        result, chosen, freshness=str(freshness.get("state") or "")
    )
    # Recognised-version uncertainty must not erase adoption-year conclusions.
    version_freshness = check_dependency_freshness(
        repo_root,
        sorted(RECOGNISED_VERSION_SOURCE_IDS),
        freshness_loader=freshness_loader,
    )
    if str(version_freshness.get("state") or "") == "MANUAL_VERIFICATION_REQUIRED":
        result.notes = (
            "Taiwan-recognised IFRS Standard version may still require manual "
            "verification against the SFB recognised-version source. This does "
            "not cancel the independently verified FSC adoption-year conclusion."
        )
    return result


def assess_verification_obligation(
    profile: CompanyProfile,
    rules: pd.DataFrame,
    ifrs_result: ObligationResult,
    *,
    repo_root: Path,
    generated_at: str,
    freshness_loader=get_regulatory_freshness,
) -> ObligationResult:
    name = "Verification / Assurance"
    # Never infer from GHG inventory alone.
    if ifrs_result.status == STATUS_OUT_OF_V1_SCOPE:
        return _obligation_shell(
            OBLIGATION_VERIFICATION,
            name,
            status=STATUS_OUT_OF_V1_SCOPE,
            reason=(
                "IFRS-related assurance for this entity type is outside V1 product "
                "support."
            ),
            generated_at=generated_at,
        )
    if ifrs_result.status in {
        STATUS_NEEDS_INFORMATION,
        STATUS_NEEDS_REVIEW,
        STATUS_NOT_YET_ASSESSED,
        STATUS_REGULATORY_DATA_STALE,
        STATUS_MANUAL_VERIFICATION_REQUIRED,
    }:
        return _obligation_shell(
            OBLIGATION_VERIFICATION,
            name,
            status=ifrs_result.status,
            reason=(
                "IFRS Scope 1/2 assurance depends on the IFRS adoption assessment, "
                "which is not yet conclusive."
            ),
            missing=list(ifrs_result.missing_information),
            next_action=ifrs_result.next_action,
            generated_at=generated_at,
            freshness=ifrs_result.regulatory_freshness_status,
        )
    if ifrs_result.status == STATUS_NOT_APPLICABLE:
        # Environmental verification may still apply — registry lacks MOENV rules.
        env = str(profile.received_verification_requirement or "NOT_SURE").upper()
        if env == "YES":
            return _obligation_shell(
                OBLIGATION_VERIFICATION,
                name,
                status=STATUS_NEEDS_REVIEW,
                reason=(
                    "The company reported receiving a verification requirement, but "
                    "verified Taiwan environmental verification rules are not yet "
                    "available in the V1 registry for automated determination."
                ),
                next_action="Review the official environmental notice manually.",
                generated_at=generated_at,
            )
        return _obligation_shell(
            OBLIGATION_VERIFICATION,
            name,
            status=STATUS_NEEDS_INFORMATION,
            reason=(
                "IFRS-related assurance is not triggered because IFRS adoption is "
                "not applicable. Environmental verification cannot be determined "
                "from verified registry rules alone yet."
            ),
            missing=["received_verification_requirement"],
            next_action=(
                "Confirm whether an environmental authority required verification."
            ),
            generated_at=generated_at,
        )

    # IFRS APPLICABLE or FUTURE → evaluate matching assurance rule.
    entity = str(profile.entity_type or "")
    operable = operable_rules(rules)
    assurance = operable[operable["rule_id"].isin(IFRS_ASSURANCE_RULE_IDS)].copy()
    derived = {
        "tw_ifrs_sustainability_applied": True,
        "fi_tw_ifrs_applied": entity
        in {"financial_holding_company", "bank", "bills_finance_company"},
        "sf_tw_ifrs_applied": entity == "securities_firm",
        "fcm_tw_ifrs_applied": entity == "futures_commission_merchant",
    }
    ctx = build_evaluation_context(profile, derived=derived)
    matched_rows: list[pd.Series] = []
    for _, row in assurance.iterrows():
        tokens = {
            part.strip()
            for part in str(row.get("entity_type") or "").split("|")
            if part.strip()
        }
        if entity not in tokens and str(row.get("entity_type") or "") != entity:
            # General listed assurance rules use listed/otc tokens.
            if entity in {"general_listed_company", "general_otc_company"}:
                if entity not in tokens:
                    continue
            else:
                continue
        if not _is_verified_for_conclusion(row):
            continue
        if str(row.get("product_support_status") or "") == "OUT_OF_V1_SCOPE":
            continue
        evaluation = evaluate_condition(
            str(row.get("applicability_condition_machine") or ""), ctx
        )
        if evaluation.unsupported:
            continue
        if evaluation.missing:
            return _obligation_shell(
                OBLIGATION_VERIFICATION,
                name,
                status=STATUS_NEEDS_INFORMATION,
                reason="Missing information blocks IFRS assurance determination.",
                missing=evaluation.missing,
                next_action="Complete the listed company-profile fields.",
                generated_at=generated_at,
            )
        if evaluation.matched is True:
            matched_rows.append(row)

    if not matched_rows:
        return _obligation_shell(
            OBLIGATION_VERIFICATION,
            name,
            status=STATUS_NEEDS_REVIEW,
            reason=(
                "No verified IFRS Scope 1/2 assurance rule matched after IFRS "
                "adoption was identified. Manual review is required."
            ),
            next_action="Review FSC assurance clauses for this entity family.",
            generated_at=generated_at,
        )

    chosen = matched_rows[0]
    freshness = check_dependency_freshness(
        repo_root,
        [str(chosen.get("source_id") or "")],
        freshness_loader=freshness_loader,
    )
    block = freshness_blocks_conclusion(freshness)
    if block:
        result = _obligation_shell(
            OBLIGATION_VERIFICATION,
            name,
            status=block,
            reason=(
                "Required official-source freshness could not be confirmed for "
                "IFRS assurance."
            ),
            next_action="Refresh regulatory monitoring state, then reassess.",
            generated_at=generated_at,
            freshness=str(freshness.get("state") or ""),
        )
        return _populate_rule_metadata(
            result, chosen, freshness=str(freshness.get("state") or "")
        )

    effective_year = _parse_year(str(chosen.get("rule_effective_from") or ""))
    reporting_year = int(profile.reporting_year or 0)
    if effective_year and reporting_year and reporting_year < effective_year:
        status = STATUS_FUTURE_REQUIREMENT
    else:
        status = (
            STATUS_FUTURE_REQUIREMENT
            if ifrs_result.status == STATUS_FUTURE_REQUIREMENT
            else STATUS_APPLICABLE
        )
    result = _obligation_shell(
        OBLIGATION_VERIFICATION,
        name,
        status=status,
        reason=(
            "Based on verified FSC IFRS Sustainability Standards rules, Scope 1/2 "
            "GHG assurance is linked to IFRS adoption for this entity family. "
            "This is separate from Taiwan environmental inventory verification."
        ),
        next_action="Plan independent third-party Scope 1/2 assurance readiness.",
        generated_at=generated_at,
        freshness=str(freshness.get("state") or ""),
    )
    result.effective_reporting_year = (
        ifrs_result.effective_reporting_year or effective_year
    )
    result.first_filing_year = ifrs_result.first_filing_year
    return _populate_rule_metadata(
        result, chosen, freshness=str(freshness.get("state") or "")
    )


def assess_ghg_inventory_obligation(
    profile: CompanyProfile,
    rules: pd.DataFrame,
    *,
    generated_at: str,
    uploaded_emissions_tco2e: float | None = None,
) -> ObligationResult:
    """Taiwan GHG inventory — only from verified registry rules (none invented)."""
    del uploaded_emissions_tco2e  # Explicitly unused: never infer from totals.
    name = "GHG Inventory"
    # Confirm registry has no MOENV inventory applicability framework yet.
    frameworks = set(rules["framework"].astype(str).str.upper())
    has_inventory_framework = any(
        token in fw
        for fw in frameworks
        for token in ("MOENV", "GHG_INVENTORY", "CARBON_FEE")
    )
    inventory_rules = rules[
        rules["content_area"].astype(str).str.contains(
            "inventory obligation|碳費|盤查義務", case=False, na=False
        )
    ]
    if not has_inventory_framework and inventory_rules.empty:
        missing: list[str] = []
        notice = str(
            profile.received_environmental_authority_inventory_notice or "NOT_SURE"
        ).upper()
        facilities = str(profile.has_taiwan_facilities or "NOT_SURE").upper()
        if facilities == "NOT_SURE":
            missing.append("has_taiwan_facilities")
        if notice == "NOT_SURE":
            missing.append("received_environmental_authority_inventory_notice")
        if missing:
            return _obligation_shell(
                OBLIGATION_GHG_INVENTORY,
                name,
                status=STATUS_NEEDS_INFORMATION,
                reason=(
                    "Verified Taiwan GHG inventory applicability rules are not yet "
                    "present in the V1 regulatory registry. Additional facility / "
                    "notice facts are still needed before a specialist review."
                ),
                missing=missing,
                next_action=(
                    "Answer the Taiwan facility and environmental-notice questions, "
                    "then seek specialist review against MOENV rules."
                ),
                generated_at=generated_at,
            )
        return _obligation_shell(
            OBLIGATION_GHG_INVENTORY,
            name,
            status=STATUS_NEEDS_REVIEW,
            reason=(
                "The verified V1 regulatory registry does not yet contain "
                "sufficient authoritative MOENV inventory-threshold rules for "
                "automated determination. No threshold was invented."
            ),
            next_action="Review official MOENV inventory designation notices manually.",
            generated_at=generated_at,
        )
    return _obligation_shell(
        OBLIGATION_GHG_INVENTORY,
        name,
        status=STATUS_NEEDS_REVIEW,
        reason="Inventory rules require specialist review in the current registry.",
        generated_at=generated_at,
    )


def assess_carbon_fee_obligation(
    profile: CompanyProfile,
    rules: pd.DataFrame,
    *,
    generated_at: str,
    uploaded_emissions_tco2e: float | None = None,
) -> ObligationResult:
    """Taiwan Carbon Fee — never infer from uploaded emissions totals."""
    del uploaded_emissions_tco2e
    name = "Carbon Fee"
    fee_rules = rules[
        rules["framework"].astype(str).str.contains(
            "CARBON_FEE|碳費", case=False, na=False
        )
        | rules["requirement_title"].astype(str).str.contains("碳費", na=False)
    ]
    if fee_rules.empty:
        boundary = str(profile.reporting_entities_known or "UNKNOWN").upper()
        facilities = str(profile.has_taiwan_facilities or "NOT_SURE").upper()
        missing: list[str] = []
        if boundary in {"UNKNOWN", "NO", "FALSE", ""}:
            missing.append("reporting_entities_known")
        if facilities == "NOT_SURE":
            missing.append("has_taiwan_facilities")
        if missing:
            return _obligation_shell(
                OBLIGATION_CARBON_FEE,
                name,
                status=STATUS_NEEDS_INFORMATION,
                reason=(
                    "Carbon Fee applicability cannot be determined from uploaded "
                    "emissions totals. Regulatory-boundary information is incomplete, "
                    "and verified MOENV Carbon Fee rules are not yet in the "
                    "V1 registry."
                ),
                missing=missing,
                next_action=(
                    "Clarify Taiwan facilities / reporting boundary; do not treat "
                    "a low upload total as NOT_APPLICABLE."
                ),
                generated_at=generated_at,
            )
        return _obligation_shell(
            OBLIGATION_CARBON_FEE,
            name,
            status=STATUS_NEEDS_REVIEW,
            reason=(
                "Verified authoritative MOENV Carbon Fee applicability rules are "
                "not yet available in the V1 registry. No unverified threshold was "
                "invented, and uploaded dataset totals were not used."
            ),
            next_action="Review official Carbon Fee designation criteria manually.",
            generated_at=generated_at,
        )
    return _obligation_shell(
        OBLIGATION_CARBON_FEE,
        name,
        status=STATUS_NEEDS_REVIEW,
        reason="Carbon Fee rules require specialist review.",
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Public assessment entrypoint
# ---------------------------------------------------------------------------


def assess_applicability(
    profile: CompanyProfile,
    *,
    repo_root: Path | None = None,
    rules: pd.DataFrame | None = None,
    sources: pd.DataFrame | None = None,
    freshness_loader=get_regulatory_freshness,
    uploaded_emissions_tco2e: float | None = None,
    now: datetime | None = None,
) -> ApplicabilityAssessment:
    """Deterministic applicability assessment for V1 obligations."""
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    rules_df = rules if rules is not None else load_regulatory_rules()
    sources_df = sources if sources is not None else load_regulatory_sources()
    current = now or datetime.now(timezone.utc)
    generated_at = (
        current.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    overall_freshness = freshness_loader(root)
    ifrs = assess_ifrs_obligation(
        profile,
        rules_df,
        sources_df,
        repo_root=root,
        generated_at=generated_at,
        freshness_loader=freshness_loader,
    )
    verification = assess_verification_obligation(
        profile,
        rules_df,
        ifrs,
        repo_root=root,
        generated_at=generated_at,
        freshness_loader=freshness_loader,
    )
    inventory = assess_ghg_inventory_obligation(
        profile,
        rules_df,
        generated_at=generated_at,
        uploaded_emissions_tco2e=uploaded_emissions_tco2e,
    )
    carbon_fee = assess_carbon_fee_obligation(
        profile,
        rules_df,
        generated_at=generated_at,
        uploaded_emissions_tco2e=uploaded_emissions_tco2e,
    )

    obligations = {
        OBLIGATION_IFRS: ifrs,
        OBLIGATION_GHG_INVENTORY: inventory,
        OBLIGATION_VERIFICATION: verification,
        OBLIGATION_CARBON_FEE: carbon_fee,
    }
    rule_ids: list[str] = []
    versions: dict[str, str] = {}
    for result in obligations.values():
        for rule_id in result.applied_rule_ids:
            if rule_id and rule_id not in rule_ids:
                rule_ids.append(rule_id)
            if rule_id and result.rule_version:
                versions[rule_id] = result.rule_version

    return ApplicabilityAssessment(
        assessment_timestamp=generated_at,
        reporting_year=profile.reporting_year,
        company_profile_snapshot=profile.snapshot(),
        obligations=obligations,
        rule_ids_used=rule_ids,
        rule_versions_used=versions,
        regulatory_freshness_snapshot={
            "state": overall_freshness.get("state"),
            "overall_regulatory_freshness": overall_freshness.get(
                "overall_regulatory_freshness"
            ),
            "last_successful_check_at": overall_freshness.get(
                "last_successful_check_at"
            ),
            "last_global_check_at": overall_freshness.get("last_global_check_at"),
            "changes_pending_review": overall_freshness.get("changes_pending_review"),
            "state_source": overall_freshness.get("state_source"),
            "analysis_allowed": overall_freshness.get("analysis_allowed"),
        },
        result_statuses={key: value.status for key, value in obligations.items()},
    )


def company_profile_from_mapping(data: dict[str, Any] | None) -> CompanyProfile:
    """Build a CompanyProfile from session/dict data with safe defaults."""
    raw = dict(data or {})
    year = raw.get("reporting_year")
    reporting_year: int | None
    try:
        reporting_year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        reporting_year = None

    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _float_or_none(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return CompanyProfile(
        company_name=str(raw.get("company_name") or ""),
        jurisdiction=str(raw.get("jurisdiction") or "TW"),
        reporting_year=reporting_year,
        entity_type=str(raw.get("entity_type") or "unresolved"),
        listing_status=str(raw.get("listing_status") or "UNKNOWN"),
        paid_in_capital_twd=_int_or_none(raw.get("paid_in_capital_twd")),
        net_worth_twd=_int_or_none(raw.get("net_worth_twd")),
        share_par_value_twd=_float_or_none(raw.get("share_par_value_twd")),
        has_no_par_value_shares=str(
            raw.get("has_no_par_value_shares") or "UNKNOWN"
        ).upper(),
        is_fhc_subsidiary=str(raw.get("is_fhc_subsidiary") or "UNKNOWN").upper(),
        parent_entity_type=str(raw.get("parent_entity_type") or ""),
        uses_consolidated_financial_statements=str(
            raw.get("uses_consolidated_financial_statements") or "UNKNOWN"
        ).upper(),
        subsidiary_count=_int_or_none(raw.get("subsidiary_count")),
        reporting_entities_known=str(
            raw.get("reporting_entities_known") or "UNKNOWN"
        ).upper(),
        industry=str(raw.get("industry") or ""),
        sasb_industry=str(raw.get("sasb_industry") or ""),
        has_taiwan_facilities=str(
            raw.get("has_taiwan_facilities") or "NOT_SURE"
        ).upper(),
        number_of_taiwan_facilities=_int_or_none(
            raw.get("number_of_taiwan_facilities")
        ),
        received_environmental_authority_inventory_notice=str(
            raw.get("received_environmental_authority_inventory_notice") or "NOT_SURE"
        ).upper(),
        received_verification_requirement=str(
            raw.get("received_verification_requirement") or "NOT_SURE"
        ).upper(),
        known_regulated_facility=str(
            raw.get("known_regulated_facility") or "NOT_SURE"
        ).upper(),
        early_adopt=bool(raw.get("early_adopt") or False),
        first_application_year=_int_or_none(raw.get("first_application_year")),
    )


def with_profile_updates(
    profile: CompanyProfile, **updates: Any
) -> CompanyProfile:
    return replace(profile, **updates)


__all__ = [
    "APPLICABILITY_STATUSES",
    "ApplicabilityAssessment",
    "CompanyProfile",
    "OBLIGATION_CARBON_FEE",
    "OBLIGATION_GHG_INVENTORY",
    "OBLIGATION_IFRS",
    "OBLIGATION_VERIFICATION",
    "ObligationResult",
    "STATUS_APPLICABLE",
    "STATUS_FUTURE_REQUIREMENT",
    "STATUS_MANUAL_VERIFICATION_REQUIRED",
    "STATUS_NEEDS_INFORMATION",
    "STATUS_NEEDS_REVIEW",
    "STATUS_NOT_APPLICABLE",
    "STATUS_NOT_YET_ASSESSED",
    "STATUS_OUT_OF_V1_SCOPE",
    "STATUS_REGULATORY_DATA_STALE",
    "assess_applicability",
    "assert_no_dynamic_execution",
    "build_evaluation_context",
    "company_profile_from_mapping",
    "evaluate_condition",
]
