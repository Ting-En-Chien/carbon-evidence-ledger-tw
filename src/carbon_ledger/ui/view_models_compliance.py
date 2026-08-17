"""Stage 3B compliance / applicability view helpers for Streamlit pages."""

from __future__ import annotations

from typing import Any

from carbon_ledger.applicability import (
    OBLIGATION_CARBON_FEE,
    OBLIGATION_GHG_INVENTORY,
    OBLIGATION_IFRS,
    OBLIGATION_VERIFICATION,
    ApplicabilityAssessment,
    ObligationResult,
)
from carbon_ledger.regulatory_monitor import get_regulatory_freshness
from carbon_ledger.ui.i18n import status_label, t

OBLIGATION_I18N = {
    OBLIGATION_IFRS: "apl.obligation_ifrs",
    OBLIGATION_GHG_INVENTORY: "apl.obligation_inventory",
    OBLIGATION_VERIFICATION: "apl.obligation_verification",
    OBLIGATION_CARBON_FEE: "apl.obligation_carbon_fee",
}


def applicability_status_label(status: str, lang: str) -> str:
    key = f"apl.status.{status}"
    labeled = t(key, lang)
    if labeled != key:
        return labeled
    return status_label(status, lang)


def freshness_display_label(state: str, lang: str) -> str:
    key = f"reg.freshness.{state}"
    labeled = t(key, lang)
    if labeled != key:
        return labeled
    return status_label(state, lang)


def missing_field_label(field_name: str, lang: str) -> str:
    key = f"apl.field.{field_name}"
    labeled = t(key, lang)
    if labeled != key:
        return labeled
    return field_name.replace("_", " ")


def _looks_english(text: str) -> bool:
    if not text:
        return False
    letters = sum(1 for ch in text if "A" <= ch <= "Z" or "a" <= ch <= "z")
    return letters >= max(12, int(len(text) * 0.35))


def localize_obligation_text(
    *,
    obligation_id: str,
    status: str,
    text: str,
    kind: str,
    lang: str,
    effective_year: int | None = None,
    first_filing_year: int | None = None,
) -> str:
    """Map engine English prose to i18n for business UI without changing conclusions."""
    if not text:
        return ""
    params = {
        "year": effective_year or "",
        "filing": first_filing_year or "",
    }
    specific_key = f"apl.{kind}.{obligation_id}.{status}"
    specific = t(specific_key, lang)
    if specific != specific_key:
        return specific.format(**params)
    generic_key = f"apl.{kind}_generic.{status}"
    generic = t(generic_key, lang)
    if str(lang).startswith("zh") and _looks_english(text):
        if generic != generic_key:
            return generic.format(**params)
        return t("apl.text_needs_review_fallback", lang)
    if generic != generic_key and str(lang).startswith("zh"):
        return generic.format(**params)
    return text


def regulatory_freshness_banner(
    repo_root,
    *,
    lang: str,
    freshness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build company-facing regulatory status (no crawler-policy details)."""
    if freshness is not None:
        payload = freshness
    else:
        payload = get_regulatory_freshness(repo_root)
    state = str(
        payload.get("overall_regulatory_freshness")
        or payload.get("state")
        or "FRESHNESS_STATE_UNAVAILABLE"
    )
    pending_signals = int(
        payload.get("change_signals_pending_review")
        or (payload.get("summary") or {}).get("change_signals_pending_review")
        or 0
    )
    pending_reviews = int(payload.get("changes_pending_review") or 0)
    pending = max(pending_signals, pending_reviews)
    last_verified = str(
        payload.get("last_verified_regulatory_update_at")
        or (payload.get("summary") or {}).get("last_verified_regulatory_update_at")
        or payload.get("last_successful_check_at")
        or ""
    )
    if pending > 0:
        state_label = t("reg.status_pending_verification", lang)
    elif state in {
        "CURRENT",
        "AUTOMATED_CURRENT",
        "MANUALLY_VERIFIED",
        "PARTIAL",
        "UPDATE_REQUIRED",
        "CHECK_DUE",
    }:
        state_label = t("reg.status_verified", lang)
    else:
        state_label = freshness_display_label(state, lang)

    summary = payload.get("summary") or {}
    auto_expected = int(
        payload.get("automated_sources_expected")
        or summary.get("automated_sources_expected")
        or 0
    )
    auto_failed = int(
        payload.get("automated_sources_failed")
        or summary.get("automated_sources_failed")
        or 0
    )
    auto_config = int(
        payload.get("automated_sources_configuration_required")
        or summary.get("automated_sources_configuration_required")
        or 0
    )
    critical_failed = int(summary.get("critical_sources_failed") or 0)
    if critical_failed == 0 and (auto_expected == 0 or auto_failed == 0):
        auto_label = t("reg.auto_sources_ok", lang)
    else:
        auto_label = t("reg.auto_sources_attention", lang)

    admin_details = {
        "automated_sources_expected": str(auto_expected),
        "automated_sources_successful": str(
            payload.get("automated_sources_successful")
            or summary.get("automated_sources_successful")
            or 0
        ),
        "automated_sources_failed": str(auto_failed),
        "automated_sources_configuration_required": str(auto_config),
        "sources_manual_access": str(summary.get("sources_manual_access") or 0),
        "manual_reference_sources": str(summary.get("manual_reference_sources") or 0),
        "restricted_automation_sources": str(
            summary.get("restricted_automation_sources") or 0
        ),
        "change_signals_pending_review": str(pending_signals),
        "last_verified_regulatory_update_at": last_verified,
        "monitoring_health": str(summary.get("monitoring_health") or ""),
    }
    if auto_config > 0:
        admin_details["supporting_sources_note"] = t(
            "reg.supporting_config_required",
            lang,
            n=auto_config,
        )
    return {
        "state": state,
        "state_label": state_label,
        "last_successful_check_at": last_verified,
        "pending_reviews": str(pending),
        "title": t("reg.status_title", lang),
        "last_check_label": t("reg.last_verified", lang),
        "pending_label": t("reg.pending_major_updates", lang),
        "auto_label": t("reg.auto_sources_label", lang),
        "auto_status": auto_label,
        "pending_signal_note": (
            t("reg.pending_signal_note", lang) if pending > 0 else ""
        ),
        "admin_details": admin_details,
    }


def obligation_card_view(
    result: ObligationResult,
    lang: str,
    *,
    display_title_key: str | None = None,
    display_kind: str | None = None,
) -> dict[str, Any]:
    title_key = display_title_key or OBLIGATION_I18N.get(result.obligation_id, "")
    title = t(title_key, lang) if title_key else result.obligation_name
    missing = [
        missing_field_label(item, lang) for item in result.missing_information
    ]
    reason = localize_obligation_text(
        obligation_id=result.obligation_id,
        status=result.status,
        text=result.reason,
        kind="reason",
        lang=lang,
        effective_year=result.effective_reporting_year,
        first_filing_year=result.first_filing_year,
    )
    next_action = localize_obligation_text(
        obligation_id=result.obligation_id,
        status=result.status,
        text=result.next_action,
        kind="next",
        lang=lang,
        effective_year=result.effective_reporting_year,
        first_filing_year=result.first_filing_year,
    )
    notes = result.notes
    if notes and str(lang).startswith("zh") and _looks_english(notes):
        notes = t("apl.notes_secondary", lang)
    return {
        "obligation_id": result.obligation_id,
        "title": title,
        "display_kind": display_kind or "",
        "status": result.status,
        "status_label": applicability_status_label(result.status, lang),
        "reason": reason,
        "effective_reporting_year": result.effective_reporting_year,
        "first_filing_year": result.first_filing_year,
        "missing_information": missing,
        "next_action": next_action,
        "official_authority": result.official_authority,
        "official_document": result.official_document,
        "citations": list(result.citations),
        "applied_rule_ids": list(result.applied_rule_ids),
        "source_ids": list(result.source_ids),
        "rule_effective_from": result.rule_effective_from,
        "rule_version": result.rule_version,
        "last_rule_verified_at": result.last_rule_verified_at,
        "regulatory_freshness_status": result.regulatory_freshness_status,
        "notes": notes,
    }


def assessment_obligation_cards(
    assessment: ApplicabilityAssessment | None,
    lang: str,
) -> list[dict[str, Any]]:
    """Five business rows; verification split for clear IFRS vs MOENV wording."""
    if assessment is None:
        return []
    cards: list[dict[str, Any]] = []
    ifrs = assessment.obligation(OBLIGATION_IFRS)
    if ifrs is not None:
        cards.append(obligation_card_view(ifrs, lang))

    verification = assessment.obligation(OBLIGATION_VERIFICATION)
    if verification is not None:
        cards.append(
            obligation_card_view(
                verification,
                lang,
                display_title_key="apl.obligation_ifrs_assurance",
                display_kind=t("apl.kind.ifrs_assurance", lang),
            )
        )

    inventory = assessment.obligation(OBLIGATION_GHG_INVENTORY)
    if inventory is not None:
        cards.append(obligation_card_view(inventory, lang))

    # Presentation-only companion row — does not change backend conclusions.
    snapshot = assessment.company_profile_snapshot or {}
    env_flag = str(
        snapshot.get("received_verification_requirement") or "NOT_SURE"
    ).upper()
    if env_flag == "YES":
        env_status = "APPLICABLE"
        env_missing: list[str] = []
    elif env_flag == "NO":
        # Customer said no notice. V1 has no verified "not required" threshold,
        # so this stays a non-actionable review state — never APPLICABLE.
        env_status = "NEEDS_REVIEW"
        env_missing = []
    else:
        env_status = "NEEDS_INFORMATION"
        env_missing = ["received_verification_requirement"]
    cards.append(
        {
            "obligation_id": "taiwan_environmental_verification",
            "title": t("apl.obligation_env_verification", lang),
            "display_kind": t("apl.kind.env_verification", lang),
            "status": env_status,
            "status_label": applicability_status_label(env_status, lang),
            "reason": t(f"apl.reason.env_verification.{env_status}", lang)
            if t(f"apl.reason.env_verification.{env_status}", lang)
            != f"apl.reason.env_verification.{env_status}"
            else "",
            "effective_reporting_year": None,
            "first_filing_year": None,
            "missing_information": [
                missing_field_label("received_verification_requirement", lang)
            ]
            if env_missing
            else [],
            "next_action": t(f"apl.next.env_verification.{env_status}", lang)
            if t(f"apl.next.env_verification.{env_status}", lang)
            != f"apl.next.env_verification.{env_status}"
            else "",
            "official_authority": "",
            "official_document": "",
            "citations": [],
            "applied_rule_ids": [],
            "source_ids": [],
            "rule_effective_from": "",
            "rule_version": "",
            "last_rule_verified_at": "",
            "regulatory_freshness_status": "",
            "notes": "",
        }
    )

    carbon = assessment.obligation(OBLIGATION_CARBON_FEE)
    if carbon is not None:
        cards.append(obligation_card_view(carbon, lang))
    return cards


def company_profile_missing_items(
    assessment: ApplicabilityAssessment | None,
    lang: str,
) -> list[str]:
    if assessment is None:
        return []
    seen: set[str] = set()
    items: list[str] = []
    for result in assessment.obligations.values():
        for field_name in result.missing_information:
            if field_name in seen:
                continue
            seen.add(field_name)
            items.append(missing_field_label(field_name, lang))
    return items


def unified_attention_items(
    *,
    assessment: ApplicabilityAssessment | None,
    emissions_priority: list[dict[str, Any]] | None,
    lang: str,
    limit: int = 5,
) -> list[dict[str, str]]:
    """Single prioritized Current Attention list for Compliance Overview."""
    items: list[dict[str, str]] = []

    if assessment is None:
        items.append(
            {
                "title": t("dash.attention.need_profile", lang),
                "reason": t("dash.attention.need_profile_action", lang),
                "priority": t("dash.priority.high", lang),
                "cta": t("dash.cta.complete_now", lang),
                "page": "app_pages/applicability.py",
            }
        )
    else:
        freshness_state = str(
            (assessment.regulatory_freshness_snapshot or {}).get("state") or ""
        )
        if freshness_state in {
            "REGULATORY_DATA_STALE",
            "MANUAL_VERIFICATION_REQUIRED",
            "SOURCE_CHECK_FAILED",
            "FRESHNESS_STATE_UNAVAILABLE",
        }:
            items.append(
                {
                    "title": t("dash.attention.freshness", lang),
                    "reason": t("dash.attention.freshness_action", lang),
                    "priority": t("dash.priority.high", lang),
                    "cta": t("dash.cta.review_reg", lang),
                    "page": "app_pages/applicability.py",
                }
            )
        for result in assessment.obligations.values():
            title = obligation_card_view(result, lang)["title"]
            if result.status in {
                "REGULATORY_DATA_STALE",
                "MANUAL_VERIFICATION_REQUIRED",
            }:
                items.append(
                    {
                        "title": title,
                        "reason": localize_obligation_text(
                            obligation_id=result.obligation_id,
                            status=result.status,
                            text=result.next_action,
                            kind="next",
                            lang=lang,
                        )
                        or t("dash.attention.review_action", lang),
                        "priority": t("dash.priority.high", lang),
                        "cta": t("dash.cta.complete_now", lang),
                        "page": "app_pages/applicability.py",
                    }
                )
            elif result.status == "NEEDS_INFORMATION" and result.missing_information:
                items.append(
                    {
                        "title": t(
                            "dash.attention.missing_profile",
                            lang,
                            obligation=title,
                        ),
                        "reason": t(
                            "dash.attention.missing_profile_action",
                            lang,
                        ),
                        "priority": t("dash.priority.medium", lang),
                        "cta": t("dash.cta.complete_now", lang),
                        "page": "app_pages/applicability.py",
                    }
                )

    for card in emissions_priority or []:
        if len(items) >= limit:
            break
        items.append(
            {
                "title": t("dash.uncalculable_title", lang),
                "reason": str(card.get("reason") or ""),
                "priority": t("dash.priority.medium", lang),
                "cta": t("dash.cta.how_to_fix", lang),
                "page": "app_pages/activity_explorer.py",
                "record_id": str(card.get("record_id") or ""),
            }
        )
    return items[:limit]


def attention_items_from_assessment(
    assessment: ApplicabilityAssessment | None,
    lang: str,
) -> list[dict[str, str]]:
    """Backward-compatible wrapper used by older tests."""
    items = unified_attention_items(
        assessment=assessment,
        emissions_priority=None,
        lang=lang,
    )
    return [
        {"title": item["title"], "action": item.get("reason") or item.get("action", "")}
        for item in items
    ]


def workflow_journey_steps(
    *,
    has_profile: bool,
    has_assessment: bool,
    has_emissions_data: bool,
    lang: str,
) -> list[dict[str, str]]:
    steps = [
        {
            "label": t("dash.journey.company", lang),
            "state": "done" if has_profile else "current",
        },
        {
            "label": t("dash.journey.applicability", lang),
            "state": (
                "done"
                if has_assessment
                else ("current" if has_profile else "todo")
            ),
        },
        {
            "label": t("dash.journey.data", lang),
            "state": (
                "done"
                if has_emissions_data and has_assessment
                else ("current" if has_assessment else "todo")
            ),
        },
        {
            "label": t("dash.journey.prepare", lang),
            "state": "current" if has_emissions_data and has_assessment else "todo",
        },
        {
            "label": t("dash.journey.reporting", lang),
            "state": "todo",
        },
    ]
    # Ensure only one current marker.
    seen_current = False
    for step in steps:
        if step["state"] == "current":
            if seen_current:
                step["state"] = "todo"
            seen_current = True
    return steps


_NEEDS_STATUSES = {"NEEDS_INFORMATION", "NEEDS_REVIEW"}


def home_requirement_summary(
    assessment: ApplicabilityAssessment | None,
    lang: str,
) -> dict[str, Any]:
    """Compact home status: one CTA or 2–3 lines, never the full matrix."""
    cards = assessment_obligation_cards(assessment, lang)
    if not cards:
        return {
            "state": "missing",
            "lines": [],
            "cta": "complete",
        }
    applicable = [card for card in cards if card.get("status") == "APPLICABLE"]
    needs = [card for card in cards if card.get("status") in _NEEDS_STATUSES]
    lines: list[str] = []
    for card in applicable[:3]:
        year = card.get("effective_reporting_year")
        extra = (
            t("dash.req.year_applies", lang, year=year)
            if year
            else t("dash.req.applies", lang)
        )
        lines.append(f"{card['title']} · {extra}")
    if needs and not lines:
        lines = [t("dash.next.need_more", lang)]
    return {
        "state": "partial" if needs else "ready",
        "lines": lines[:3],
        "cta": "complete" if needs else "view_all",
    }


__all__ = [
    "applicability_status_label",
    "assessment_obligation_cards",
    "attention_items_from_assessment",
    "company_profile_missing_items",
    "freshness_display_label",
    "home_requirement_summary",
    "localize_obligation_text",
    "obligation_card_view",
    "regulatory_freshness_banner",
    "unified_attention_items",
    "workflow_journey_steps",
]
