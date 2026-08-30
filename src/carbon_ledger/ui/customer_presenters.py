"""Customer presentation model for applicability and obligation results.

Backend status objects never render directly. Pages consume these product
objects: customer action / summary first, professional and audit detail only
on request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from carbon_ledger.applicability import (
    OBLIGATION_CARBON_FEE,
    OBLIGATION_GHG_INVENTORY,
    OBLIGATION_IFRS,
    OBLIGATION_VERIFICATION,
    ApplicabilityAssessment,
    ObligationResult,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.view_models_compliance import (
    assessment_obligation_cards,
    missing_field_label,
)

# Customer-facing status taxonomy (not backend enums).
STATUS_APPLICABLE = "applicable"
STATUS_NOT_APPLICABLE = "not_applicable"
STATUS_FUTURE = "future_applicable"
STATUS_NEEDS_DATA = "needs_company_data"
STATUS_SYSTEM_REVIEW = "system_review"
STATUS_NO_AUTO = "no_automatic_result"
STATUS_NOT_STARTED = "not_started"
STATUS_UNSUPPORTED = "unsupported"

TAIWAN_OBLIGATION_IDS = frozenset(
    {
        OBLIGATION_GHG_INVENTORY,
        OBLIGATION_CARBON_FEE,
        "taiwan_environmental_verification",
    }
)

FACT_TAIWAN_FACILITY = "taiwan_facility"
FACT_AUTHORITY_NOTICE = "authority_notice"
FACT_REPORTING_SCOPE = "reporting_scope"
FACT_CAPITAL = "paid_in_capital"
FACT_NET_WORTH = "net_worth"
FACT_LISTING = "listing"
FACT_ENTITY = "entity_type"

_FIELD_TO_FACT: dict[str, str] = {
    "has_taiwan_facilities": FACT_TAIWAN_FACILITY,
    "known_regulated_facility": FACT_TAIWAN_FACILITY,
    "received_environmental_authority_inventory_notice": FACT_AUTHORITY_NOTICE,
    "received_verification_requirement": FACT_AUTHORITY_NOTICE,
    "reporting_entities_known": FACT_REPORTING_SCOPE,
    "uses_consolidated_financial_statements": FACT_REPORTING_SCOPE,
    "paid_in_capital_twd": FACT_CAPITAL,
    "net_worth_twd": FACT_NET_WORTH,
    "listing_status": FACT_LISTING,
    "entity_type": FACT_ENTITY,
}

_KNOWN_FACTS = frozenset(_FIELD_TO_FACT.values())
_SYSTEM_BACKEND_STATUSES = frozenset(
    {
        "MANUAL_VERIFICATION_REQUIRED",
        "REGULATORY_DATA_STALE",
    }
)


@dataclass(frozen=True)
class CustomerObligationPresentation:
    """One domain-specific customer card. Layout contracts around filled fields."""

    obligation_id: str
    domain: str
    title: str
    short_status: str
    status_code: str
    status_tone: str
    headline: str
    explanation: str
    missing_items: tuple[str, ...] = ()
    primary_action_label: str = ""
    primary_action_target: str = ""
    primary_action_step: int = 0
    show_official_basis: bool = False
    timing_items: tuple[tuple[str, str], ...] = ()
    customer_action_required: bool = False
    system_action_pending: bool = False
    professional_detail: str = ""
    official_authority: str = ""
    official_document: str = ""
    citations: tuple[str, ...] = ()


@dataclass(frozen=True)
class CustomerActionSummary:
    """Merged missing-data action for the result page."""

    headline: str
    facts: tuple[str, ...] = ()
    affected_count: int = 0
    primary_action_label: str = ""
    primary_action_target: str = "app_pages/applicability.py"
    primary_action_step: int = 0
    customer_action_required: bool = False
    exact_question: str = ""
    fact_id: str = ""
    follow_up: str = ""
    answer_controls: bool = False


@dataclass(frozen=True)
class CustomerAssessmentPresentation:
    presentations: tuple[CustomerObligationPresentation, ...]
    action_summary: CustomerActionSummary
    finish_label_key: str
    hidden_not_ready: tuple[str, ...] = ()


def customer_status_label(status_code: str, lang: str) -> str:
    return t(f"cust.status.{status_code}", lang)


def has_verified_legal_basis(card: dict[str, Any] | ObligationResult) -> bool:
    """True only when there is customer-visible legal/source content."""
    if isinstance(card, ObligationResult):
        return bool(
            str(card.official_authority or "").strip()
            or str(card.official_document or "").strip()
            or [item for item in (card.citations or []) if item]
        )
    return bool(
        str(card.get("official_authority") or "").strip()
        or str(card.get("official_document") or "").strip()
        or [item for item in (card.get("citations") or []) if item]
    )


def _fact_label(fact_id: str, lang: str) -> str:
    return t(f"cust.fact.{fact_id}", lang)


def customer_facts_from_fields(field_names: Iterable[str], lang: str) -> list[str]:
    """Collapse backend missing-field names into unique customer facts."""
    seen: set[str] = set()
    labels: list[str] = []
    for raw in field_names:
        fact_id = _FIELD_TO_FACT.get(str(raw) or "", "")
        if fact_id:
            if fact_id in seen:
                continue
            seen.add(fact_id)
            labels.append(_fact_label(fact_id, lang))
            continue
        label = missing_field_label(str(raw), lang)
        if label and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


def map_backend_status(
    *,
    backend_status: str,
    missing_fields: Iterable[str],
    has_basis: bool,
) -> tuple[str, str, bool, bool]:
    """Return (status_code, tone, customer_action, system_pending)."""
    status = str(backend_status or "").strip()
    missing = [item for item in missing_fields if item]
    if status == "APPLICABLE":
        return STATUS_APPLICABLE, "success", False, False
    if status == "NOT_APPLICABLE":
        return STATUS_NOT_APPLICABLE, "neutral", False, False
    if status == "FUTURE_REQUIREMENT":
        return STATUS_FUTURE, "info", False, False
    if status == "OUT_OF_V1_SCOPE":
        return STATUS_UNSUPPORTED, "neutral", False, False
    if status in _SYSTEM_BACKEND_STATUSES:
        return STATUS_SYSTEM_REVIEW, "info", False, True
    if status == "NOT_YET_ASSESSED":
        if has_basis:
            return STATUS_NOT_STARTED, "neutral", False, False
        return STATUS_NO_AUTO, "neutral", False, False
    if status == "NEEDS_INFORMATION" or (status == "NEEDS_REVIEW" and missing):
        return STATUS_NEEDS_DATA, "warning", True, False
    if status == "NEEDS_REVIEW":
        if has_basis:
            return STATUS_SYSTEM_REVIEW, "info", False, True
        return STATUS_NO_AUTO, "neutral", False, False
    return STATUS_NO_AUTO, "neutral", False, False


def _domain_for(obligation_id: str) -> str:
    if obligation_id == OBLIGATION_IFRS:
        return "ifrs"
    if obligation_id == OBLIGATION_VERIFICATION:
        return "ifrs_assurance"
    if obligation_id == "taiwan_environmental_verification":
        return "env_verification"
    if obligation_id == OBLIGATION_GHG_INVENTORY:
        return "ghg_inventory"
    if obligation_id == OBLIGATION_CARBON_FEE:
        return "carbon_fee"
    return obligation_id or "generic"


def _cta_for(status_code: str, domain: str, lang: str) -> tuple[str, str, int]:
    from carbon_ledger.ui.app_mode import AppMode, resolve_boot_mode

    admin = resolve_boot_mode() is AppMode.ADMIN
    if status_code == STATUS_NEEDS_DATA and domain == "env_verification":
        return t("cust.cta.confirm_notice", lang), "app_pages/applicability.py", 2
    if status_code == STATUS_NEEDS_DATA and domain in {"carbon_fee", "ghg_inventory"}:
        return t("cust.cta.confirm_facilities", lang), "app_pages/applicability.py", 3
    if status_code == STATUS_NEEDS_DATA:
        return (
            t("cust.cta.provide_company_facts", lang),
            "app_pages/applicability.py",
            2,
        )
    if status_code == STATUS_APPLICABLE and domain == "ifrs":
        if admin:
            return t("apl.cta.start_prepare_ifrs", lang), "app_pages/frameworks.py", 0
        return "", "", 0
    if status_code == STATUS_APPLICABLE and domain in {
        "ghg_inventory",
        "env_verification",
        "carbon_fee",
    }:
        return t("cust.cta.prepare_emissions", lang), "app_pages/data_intake.py", 0
    return "", "", 0


def _timing_for(
    domain: str, card: dict[str, Any], lang: str
) -> tuple[tuple[str, str], ...]:
    if domain not in {"ifrs", "ifrs_assurance"}:
        return ()
    items: list[tuple[str, str]] = []
    start = card.get("effective_reporting_year")
    filing = card.get("first_filing_year")
    if start not in (None, "", "—"):
        items.append(
            (t("cust.timing.start_year", lang, year=start), str(start))
        )
    if filing not in (None, "", "—"):
        items.append(
            (t("cust.timing.first_filing", lang, year=filing), str(filing))
        )
    return tuple(items)


def _explanation_for(
    domain: str,
    status_code: str,
    card: dict[str, Any],
    lang: str,
) -> str:
    specific = t(f"cust.explain.{domain}.{status_code}", lang)
    key = f"cust.explain.{domain}.{status_code}"
    if specific != key:
        return specific
    generic = t(f"cust.explain.{status_code}", lang)
    if generic != f"cust.explain.{status_code}":
        return generic
    return str(card.get("reason") or "").strip()


def present_obligation_card(
    card: dict[str, Any], lang: str
) -> CustomerObligationPresentation:
    """Map one legacy/backend card dict into a customer presentation object."""
    obligation_id = str(card.get("obligation_id") or "")
    domain = _domain_for(obligation_id)
    backend_status = str(card.get("status") or "")
    field_ids = [str(item) for item in (card.get("missing_field_ids") or [])]
    has_basis = has_verified_legal_basis(card)
    status_code, tone, customer_action, system_pending = map_backend_status(
        backend_status=backend_status,
        missing_fields=field_ids,
        has_basis=has_basis,
    )
    facts = customer_facts_from_fields(field_ids, lang)
    if not facts:
        facts = [
            str(item) for item in (card.get("missing_information") or []) if item
        ]
    if domain == "env_verification" and backend_status == "NEEDS_REVIEW":
        if field_ids:
            status_code = STATUS_NEEDS_DATA
            tone = "warning"
            customer_action = True
            if not facts:
                facts = [_fact_label(FACT_AUTHORITY_NOTICE, lang)]
        else:
            # NO notice is not a verified "not required" rule. Hide (CASE C).
            # Do not invent APPLICABLE or NOT_APPLICABLE.
            status_code = STATUS_NO_AUTO
            tone = "neutral"
            customer_action = False
            facts = []
    action_label, action_target, action_step = _cta_for(status_code, domain, lang)
    if status_code != STATUS_NEEDS_DATA:
        facts = []
        if status_code != STATUS_APPLICABLE:
            action_label, action_target, action_step = "", "", 0
            customer_action = False
    if status_code in {STATUS_SYSTEM_REVIEW, STATUS_NO_AUTO, STATUS_UNSUPPORTED}:
        action_label, action_target, action_step = "", "", 0
        customer_action = False
        facts = []
    if status_code in {STATUS_APPLICABLE, STATUS_NOT_APPLICABLE, STATUS_FUTURE}:
        meaning = t(f"cust.meaning.{domain}", lang)
        if meaning != f"cust.meaning.{domain}":
            explanation = meaning
        else:
            explanation = _explanation_for(domain, status_code, card, lang)
    else:
        explanation = _explanation_for(domain, status_code, card, lang)
    title = str(card.get("title") or "")
    question = t(f"cust.q.{domain}", lang)
    if question != f"cust.q.{domain}":
        title = question
    elif domain == "env_verification":
        title = t("apl.obligation_env_verification", lang)
    if domain == "ifrs_assurance":
        title = t("apl.obligation_ifrs_assurance", lang)
    return CustomerObligationPresentation(
        obligation_id=obligation_id,
        domain=domain,
        title=title,
        short_status=customer_status_label(status_code, lang),
        status_code=status_code,
        status_tone=tone,
        headline=customer_status_label(status_code, lang),
        explanation=explanation,
        missing_items=tuple(facts) if customer_action else (),
        primary_action_label=(
            action_label
            if customer_action or status_code == STATUS_APPLICABLE
            else ""
        ),
        primary_action_target=action_target if action_label else "",
        primary_action_step=action_step if action_label else 0,
        show_official_basis=has_basis,
        timing_items=_timing_for(domain, card, lang),
        customer_action_required=customer_action,
        system_action_pending=system_pending,
        professional_detail=str(card.get("notes") or ""),
        official_authority=str(card.get("official_authority") or ""),
        official_document=str(card.get("official_document") or ""),
        citations=tuple(
            str(item) for item in (card.get("citations") or []) if item
        ),
    )


def _attach_field_ids(
    card: dict[str, Any], result: ObligationResult | None
) -> dict[str, Any]:
    payload = dict(card)
    if result is not None:
        payload["missing_field_ids"] = list(result.missing_information)
    elif card.get("obligation_id") == "taiwan_environmental_verification":
        if str(card.get("status") or "") == "NEEDS_INFORMATION":
            payload["missing_field_ids"] = ["received_verification_requirement"]
        else:
            payload["missing_field_ids"] = []
    return payload


_CUSTOMER_TAIWAN_FACTS = frozenset({FACT_TAIWAN_FACILITY, FACT_AUTHORITY_NOTICE})
_DETERMINISTIC_STATUSES = frozenset(
    {STATUS_APPLICABLE, STATUS_NOT_APPLICABLE, STATUS_FUTURE}
)
_NOT_READY_STATUSES = frozenset(
    {STATUS_NO_AUTO, STATUS_SYSTEM_REVIEW, STATUS_UNSUPPORTED, STATUS_NOT_STARTED}
)
_NOT_READY_REASONS = {
    OBLIGATION_GHG_INVENTORY: (
        "CUSTOMER RESULT NOT READY — 台灣溫室氣體盤查："
        "V1 監理登錄尚無足夠環境部盤查門檻規則，完成顧客事實後仍非自動法律結論"
    ),
    OBLIGATION_CARBON_FEE: (
        "CUSTOMER RESULT NOT READY — 碳費："
        "V1 尚無足夠碳費適用規則，且不得用上傳排放量推導"
    ),
    "taiwan_environmental_verification": (
        "CUSTOMER RESULT NOT READY — 環境部查驗："
        "尚無足夠查驗門檻規則；僅在顧客表示已收到通知時呈現「需要」"
    ),
}


def _is_taiwan_presentation(pres: CustomerObligationPresentation) -> bool:
    return pres.obligation_id in TAIWAN_OBLIGATION_IDS or pres.domain in {
        "ghg_inventory",
        "env_verification",
        "carbon_fee",
    }


def present_assessment(
    assessment: ApplicabilityAssessment | None,
    lang: str,
) -> CustomerAssessmentPresentation:
    """Build the full customer result model, including merged actions."""
    if assessment is None:
        empty = CustomerActionSummary(
            headline=t("cust.action.need_profile", lang),
            facts=(),
            affected_count=0,
            primary_action_label=t("dash.cta.complete_now", lang),
            customer_action_required=True,
        )
        return CustomerAssessmentPresentation(
            presentations=(),
            action_summary=empty,
            finish_label_key="apl.wizard.view_current",
        )
    raw_cards = assessment_obligation_cards(assessment, lang)
    by_id = {
        result.obligation_id: result for result in assessment.obligations.values()
    }
    enriched = [
        _attach_field_ids(card, by_id.get(str(card.get("obligation_id") or "")))
        for card in raw_cards
    ]
    presentations = [present_obligation_card(card, lang) for card in enriched]
    fact_ids: list[str] = []
    seen: set[str] = set()
    affected = 0
    visible: list[CustomerObligationPresentation] = []
    hidden: list[str] = []
    for card, pres in zip(enriched, presentations, strict=True):
        raw_fields = [str(item) for item in (card.get("missing_field_ids") or [])]
        customer_fields = [
            _FIELD_TO_FACT.get(name, name)
            for name in raw_fields
            if _FIELD_TO_FACT.get(name, name) != FACT_REPORTING_SCOPE
        ]
        if _is_taiwan_presentation(pres):
            if pres.status_code == STATUS_NEEDS_DATA:
                taiwan_facts = [
                    item
                    for item in customer_fields
                    if item in _CUSTOMER_TAIWAN_FACTS
                ]
                if not taiwan_facts:
                    hidden.append(
                        _NOT_READY_REASONS.get(
                            pres.obligation_id,
                            f"CUSTOMER RESULT NOT READY — {pres.obligation_id}",
                        )
                    )
                    continue
                affected += 1
                for fact_id in taiwan_facts:
                    if fact_id in seen:
                        continue
                    seen.add(fact_id)
                    fact_ids.append(fact_id)
                continue
            if pres.status_code in _DETERMINISTIC_STATUSES:
                visible.append(pres)
                continue
            hidden.append(
                _NOT_READY_REASONS.get(
                    pres.obligation_id,
                    f"CUSTOMER RESULT NOT READY — {pres.obligation_id}",
                )
            )
            continue
        if (
            pres.status_code in _NOT_READY_STATUSES
            and not pres.customer_action_required
        ):
            hidden.append(
                f"CUSTOMER RESULT NOT READY — {pres.obligation_id}"
            )
            continue
        if pres.customer_action_required:
            affected += 1
            for name in raw_fields:
                fact_id = _FIELD_TO_FACT.get(str(name), str(name))
                if fact_id == FACT_REPORTING_SCOPE:
                    continue
                if fact_id in seen:
                    continue
                seen.add(fact_id)
                fact_ids.append(fact_id)
        visible.append(pres)
    fact_labels = [
        _fact_label(item, lang)
        if item in _KNOWN_FACTS
        else missing_field_label(item, lang)
        for item in fact_ids
    ]
    primary_fact = fact_ids[0] if fact_ids else ""
    if fact_ids:
        headline = t("cust.action.missing_count", lang, n=1)
    else:
        headline = ""
    needs_customer = bool(fact_ids)
    exact_question = ""
    follow_up = ""
    answer_controls = False
    action_label = ""
    action_step = 0
    if primary_fact == FACT_TAIWAN_FACILITY:
        exact_question = t("cust.q.missing_facilities", lang)
        action_label = t("cust.cta.confirm_facilities", lang)
        action_step = 3
        follow_up = t("cust.action.after_answer", lang)
    elif primary_fact == FACT_AUTHORITY_NOTICE:
        exact_question = t("cust.q.missing_notice", lang)
        action_label = t("cust.cta.confirm_notice", lang)
        action_step = 2
        follow_up = t("cust.action.after_answer", lang)
        answer_controls = True
    elif needs_customer:
        exact_question = fact_labels[0] if fact_labels else ""
        action_label = t("cust.cta.provide_company_facts", lang)
        action_step = 2
        follow_up = t("cust.action.after_answer", lang)
    summary = CustomerActionSummary(
        headline=headline,
        facts=tuple(fact_labels[:1]) if fact_labels else (),
        affected_count=affected,
        primary_action_label=action_label,
        primary_action_step=action_step,
        customer_action_required=needs_customer,
        exact_question=exact_question,
        fact_id=primary_fact,
        follow_up=follow_up,
        answer_controls=answer_controls,
    )
    finish_key = (
        "apl.wizard.view_current" if needs_customer else "apl.wizard.save_view"
    )
    return CustomerAssessmentPresentation(
        presentations=tuple(visible),
        action_summary=summary,
        finish_label_key=finish_key,
        hidden_not_ready=tuple(dict.fromkeys(hidden)),
    )


def customer_copy_violations(
    messages: dict[str, dict[str, str]],
) -> list[str]:
    """Flag customer-facing zh-TW strings that still leak engineering language."""
    skip_prefixes = (
        "reg.admin",
        "apl.basis.rule_id",
        "apl.basis.source",
        "apl.basis.version",
        "apl.basis.technical",
        "error.",
        "status.",
    )
    forbidden = (
        "管理員",
        "系統管理員",
        "系統不會把空白當成 0",
        "已驗證規則不足",
        "不是合規百分比",
        "需要人工 review",
        "CASE C",
        "NEEDS_REVIEW",
        "dirty state",
        "identity confirmation",
        "開啟編輯不會自動",
    )
    hits: list[str] = []
    for key, entry in messages.items():
        if any(key.startswith(prefix) for prefix in skip_prefixes):
            continue
        text = str((entry or {}).get("zh-TW") or "")
        for token in forbidden:
            if token in text:
                hits.append(f"{key}: {token}")
    return hits
