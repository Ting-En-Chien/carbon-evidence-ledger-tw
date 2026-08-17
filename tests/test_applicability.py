"""Stage 3B applicability engine tests (deterministic, no live crawl, no eval)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from carbon_ledger.applicability import (
    OBLIGATION_CARBON_FEE,
    OBLIGATION_GHG_INVENTORY,
    OBLIGATION_IFRS,
    OBLIGATION_VERIFICATION,
    CompanyProfile,
    assert_no_dynamic_execution,
    assess_applicability,
    build_evaluation_context,
    evaluate_condition,
)
from carbon_ledger.regulatory_registry import load_regulatory_rules

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fresh_ok(repo_root=None, required_source_ids=None, **kwargs):
    return {
        "analysis_allowed": True,
        "state": "CURRENT",
        "overall_regulatory_freshness": "CURRENT",
        "last_successful_check_at": "2026-08-12T00:00:00Z",
        "last_global_check_at": "2026-08-12T00:00:00Z",
        "changes_pending_review": 0,
        "state_source": "durable_persisted_state",
        "required_source_ids": list(required_source_ids or []),
    }


def _fresh_for_sources(states: dict[str, str]):
    def loader(repo_root=None, required_source_ids=None, **kwargs):
        required = list(required_source_ids or [])
        if not required:
            return _fresh_ok(required_source_ids=required)
        worst = "CURRENT"
        for sid in required:
            state = states.get(sid, "CURRENT")
            if state == "MANUAL_ACCESS_REQUIRED":
                return {
                    **_fresh_ok(required_source_ids=required),
                    "state": "MANUAL_VERIFICATION_REQUIRED",
                    "analysis_allowed": False,
                }
            if state == "STALE":
                worst = "REGULATORY_DATA_STALE"
            if state == "UNAVAILABLE":
                return {
                    **_fresh_ok(required_source_ids=required),
                    "state": "FRESHNESS_STATE_UNAVAILABLE",
                    "analysis_allowed": False,
                }
        if worst == "REGULATORY_DATA_STALE":
            return {
                **_fresh_ok(required_source_ids=required),
                "state": "REGULATORY_DATA_STALE",
                "analysis_allowed": False,
            }
        return _fresh_ok(required_source_ids=required)

    return loader


def _assess(profile: CompanyProfile, freshness_loader=_fresh_ok):
    return assess_applicability(
        profile,
        repo_root=REPO_ROOT,
        freshness_loader=freshness_loader,
    )


def test_incomplete_profile_needs_information() -> None:
    assessment = _assess(CompanyProfile(reporting_year=2026, entity_type="unresolved"))
    assert assessment.obligations[OBLIGATION_IFRS].status == "NEEDS_INFORMATION"
    assert "entity_type" in assessment.obligations[OBLIGATION_IFRS].missing_information


def test_missing_capital_never_not_applicable() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
        )
    )
    result = assessment.obligations[OBLIGATION_IFRS]
    assert result.status == "NEEDS_INFORMATION"
    assert result.status != "NOT_APPLICABLE"
    assert "paid_in_capital_twd" in result.missing_information


def test_listed_company_selects_phase_rule_family() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        )
    )
    result = assessment.obligations[OBLIGATION_IFRS]
    assert result.status == "APPLICABLE"
    assert result.applied_rule_ids == ["tw_order_51756_phase1_ge_10bn"]


def test_securities_firm_does_not_use_general_company_rules() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="securities_firm",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        )
    )
    result = assessment.obligations[OBLIGATION_IFRS]
    assert "tw_order_51756" not in "".join(result.applied_rule_ids)
    assert any("56095" in rid for rid in result.applied_rule_ids)


def test_bank_and_fhc_remain_separate() -> None:
    bank = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="bank",
            listing_status="TWSE",
            is_fhc_subsidiary="FALSE",
        )
    )
    fhc = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
        )
    )
    assert bank.obligations[OBLIGATION_IFRS].applied_rule_ids == [
        "tw_fi_bank_listed_or_fhc_sub_fy2026"
    ]
    assert fhc.obligations[OBLIGATION_IFRS].applied_rule_ids == [
        "tw_fi_fhc_apply_fy2026"
    ]


def test_bills_finance_separate_rule() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="bills_finance_company",
            listing_status="TWSE",
            is_fhc_subsidiary="FALSE",
        )
    )
    assert assessment.obligations[OBLIGATION_IFRS].applied_rule_ids == [
        "tw_fi_bills_listed_or_fhc_sub_fy2026"
    ]


def test_futures_commission_merchant_out_of_v1_scope() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="futures_commission_merchant",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        )
    )
    assert assessment.obligations[OBLIGATION_IFRS].status == "OUT_OF_V1_SCOPE"


def test_future_rule_returns_future_requirement() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=3_000_000_000,
        )
    )
    result = assessment.obligations[OBLIGATION_IFRS]
    assert result.status == "FUTURE_REQUIREMENT"
    assert result.effective_reporting_year == 2028


def test_superseded_rule_not_used() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        )
    )
    used = set(assessment.rule_ids_used)
    assert "tw_ifrs_phase1_capital_10bn_news_legacy" not in used
    rules = load_regulatory_rules()
    legacy = rules.loc[
        rules["rule_id"] == "tw_ifrs_phase1_capital_10bn_news_legacy"
    ].iloc[0]
    assert legacy["rule_status"] == "SUPERSEDED"


def test_effective_dates_by_reporting_year() -> None:
    early = _assess(
        CompanyProfile(
            reporting_year=2027,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=6_000_000_000,
        )
    )
    assert early.obligations[OBLIGATION_IFRS].status == "APPLICABLE"
    assert early.obligations[OBLIGATION_IFRS].applied_rule_ids == [
        "tw_order_51756_phase2_5_to_10bn"
    ]


def test_unsupported_machine_condition_needs_review() -> None:
    result = evaluate_condition(
        "unknown_predicate_xyz == 1",
        build_evaluation_context(CompanyProfile()),
    )
    assert result.unsupported
    assert "Unsupported applicability condition requires review." in result.error


def test_conflicting_authoritative_rules_needs_review(monkeypatch) -> None:
    # Force two phase matches by patching evaluator path via duplicate capital windows.
    # Safer: inject a tiny rules frame with two conflicting ACTIVE verified rules.
    rules = pd.DataFrame(
        [
            {
                "rule_id": "rule_a",
                "jurisdiction": "TW",
                "framework": "TW_IFRS_S1_S2",
                "authority": "A",
                "source_id": "src_a",
                "official_document": "doc a",
                "citation": "c1",
                "content_area": "Applicability",
                "requirement_title": "Conflict A FY2026",
                "requirement_summary": "a",
                "entity_type": "general_listed_company",
                "applicability_condition_machine": (
                    "entity_type==general_listed_company"
                ),
                "concept_layer": "TAIWAN_ADOPTION",
                "publication_date": "2025-01-01",
                "source_version": "1",
                "rule_effective_from": "2026-01-01",
                "rule_effective_to": "",
                "rule_status": "FUTURE",
                "supersedes_rule_id": "",
                "superseded_by_rule_id": "",
                "last_verified_at": "2026-01-01",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "international_standard_version": "",
                "taiwan_recognised_version": "",
                "taiwan_status": "",
                "version": "1",
                "product_support_status": "IN_V1_SCOPE",
            },
            {
                "rule_id": "rule_b",
                "jurisdiction": "TW",
                "framework": "TW_IFRS_S1_S2",
                "authority": "B",
                "source_id": "src_b",
                "official_document": "doc b",
                "citation": "c2",
                "content_area": "Applicability",
                "requirement_title": "Conflict B FY2026",
                "requirement_summary": "b",
                "entity_type": "general_listed_company",
                "applicability_condition_machine": (
                    "entity_type==general_listed_company"
                ),
                "concept_layer": "TAIWAN_ADOPTION",
                "publication_date": "2025-01-01",
                "source_version": "1",
                "rule_effective_from": "2026-01-01",
                "rule_effective_to": "",
                "rule_status": "FUTURE",
                "supersedes_rule_id": "",
                "superseded_by_rule_id": "",
                "last_verified_at": "2026-01-01",
                "verification_status": "VERIFIED_AUTHORITATIVE",
                "international_standard_version": "",
                "taiwan_recognised_version": "",
                "taiwan_status": "",
                "version": "1",
                "product_support_status": "IN_V1_SCOPE",
            },
        ]
    )
    sources = pd.DataFrame(
        [
            {
                "source_id": "src_a",
                "jurisdiction": "TW",
                "authority": "A",
                "source_class": "FSC_ORDER",
                "source_type": "order",
                "document_title": "a",
                "official_url": "https://example.invalid/a",
                "retrieved_date": "2026-01-01",
                "authority_level": "AUTHORITATIVE",
                "authority_rank": "10",
                "status": "ACTIVE",
                "monitor_enabled": "true",
                "monitor_frequency": "weekly",
                "freshness_status": "CURRENT",
            },
            {
                "source_id": "src_b",
                "jurisdiction": "TW",
                "authority": "B",
                "source_class": "FSC_ORDER",
                "source_type": "order",
                "document_title": "b",
                "official_url": "https://example.invalid/b",
                "retrieved_date": "2026-01-01",
                "authority_level": "AUTHORITATIVE",
                "authority_rank": "10",
                "status": "ACTIVE",
                "monitor_enabled": "true",
                "monitor_frequency": "weekly",
                "freshness_status": "CURRENT",
            },
        ]
    )
    monkeypatch.setattr(
        "carbon_ledger.applicability.IFRS_ADOPTION_RULE_IDS",
        frozenset({"rule_a", "rule_b"}),
    )
    assessment = assess_applicability(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
        ),
        repo_root=REPO_ROOT,
        rules=rules,
        sources=sources,
        freshness_loader=_fresh_ok,
    )
    assert assessment.obligations[OBLIGATION_IFRS].status == "NEEDS_REVIEW"
    assert set(assessment.obligations[OBLIGATION_IFRS].applied_rule_ids) == {
        "rule_a",
        "rule_b",
    }


def test_no_eval_exec_condition_execution() -> None:
    assert_no_dynamic_execution()
    source = Path(
        __import__("carbon_ledger.applicability", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")
    # No runtime call sites besides the guard's own documentation.
    assert "eval(" not in source.replace("must not call eval/exec", "")
    assert "exec(" not in source.replace("must not call eval/exec", "")


def test_identical_inputs_identical_results() -> None:
    profile = CompanyProfile(
        reporting_year=2026,
        entity_type="financial_holding_company",
        company_name="Demo Co",
    )
    first = _assess(profile)
    second = _assess(profile)
    assert first.result_statuses == second.result_statuses
    assert first.rule_ids_used == second.rule_ids_used
    assert first.to_dict()["result_statuses"] == second.to_dict()["result_statuses"]


def test_stale_required_source_blocks_unconditional_conclusion() -> None:
    loader = _fresh_for_sources({"src_tw_order_11403851756": "STALE"})
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        ),
        freshness_loader=loader,
    )
    assert assessment.obligations[OBLIGATION_IFRS].status == "REGULATORY_DATA_STALE"


def test_unrelated_supplementary_stale_does_not_block_ifrs() -> None:
    loader = _fresh_for_sources({"src_tw_moenv_oaout": "STALE"})
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        ),
        freshness_loader=loader,
    )
    assert assessment.obligations[OBLIGATION_IFRS].status == "APPLICABLE"


def test_manual_access_only_blocks_dependent_conclusions() -> None:
    # Adoption uses FSC order source; SFB manual access alone should not block.
    loader = _fresh_for_sources(
        {
            "src_tw_sfb_ifrs_download_area": "MANUAL_ACCESS_REQUIRED",
            "src_tw_order_11403851756": "CURRENT",
        }
    )
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        ),
        freshness_loader=loader,
    )
    result = assessment.obligations[OBLIGATION_IFRS]
    assert result.status == "APPLICABLE"
    assert "recognised" in result.notes.lower() or "manual" in result.notes.lower()


def test_recognised_version_uncertainty_does_not_erase_adoption_year() -> None:
    loader = _fresh_for_sources(
        {
            "src_tw_order_11403851755": "MANUAL_ACCESS_REQUIRED",
            "src_tw_sfb_ifrs_download_area": "MANUAL_ACCESS_REQUIRED",
            "src_tw_order_11403856094_recognised": "MANUAL_ACCESS_REQUIRED",
            "src_tw_order_11402739247_fi": "CURRENT",
        }
    )
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
        ),
        freshness_loader=loader,
    )
    assert assessment.obligations[OBLIGATION_IFRS].status in {
        "APPLICABLE",
        "FUTURE_REQUIREMENT",
    }


def test_freshness_state_unavailable_fails_safe() -> None:
    def loader(repo_root=None, required_source_ids=None, **kwargs):
        return {
            "analysis_allowed": False,
            "state": "FRESHNESS_STATE_UNAVAILABLE",
            "overall_regulatory_freshness": "FRESHNESS_STATE_UNAVAILABLE",
            "last_successful_check_at": "",
            "required_source_ids": list(required_source_ids or []),
        }

    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
        ),
        freshness_loader=loader,
    )
    assert assessment.obligations[OBLIGATION_IFRS].status == "REGULATORY_DATA_STALE"


def test_applicability_does_not_trigger_live_web_requests(monkeypatch) -> None:
    calls: list[str] = []

    def blocked(*args, **kwargs):
        calls.append("fetch")
        raise AssertionError("live fetch must not run during applicability")

    monkeypatch.setattr(
        "carbon_ledger.regulatory_monitor.default_fetch",
        blocked,
    )
    monkeypatch.setattr(
        "carbon_ledger.regulatory_monitor.fetch_with_retries",
        blocked,
    )
    _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
        )
    )
    assert calls == []


def test_inventory_separate_from_verification() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
            has_taiwan_facilities="YES",
            received_environmental_authority_inventory_notice="YES",
            reporting_entities_known="TRUE",
        )
    )
    assert (
        assessment.obligations[OBLIGATION_GHG_INVENTORY].status
        != assessment.obligations[OBLIGATION_VERIFICATION].status
        or assessment.obligations[OBLIGATION_GHG_INVENTORY].reason
        != assessment.obligations[OBLIGATION_VERIFICATION].reason
    )


def test_verification_separate_from_carbon_fee() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
            reporting_entities_known="TRUE",
            has_taiwan_facilities="YES",
        )
    )
    assert (
        assessment.obligations[OBLIGATION_VERIFICATION].obligation_id
        != assessment.obligations[OBLIGATION_CARBON_FEE].obligation_id
    )
    assert assessment.obligations[OBLIGATION_CARBON_FEE].status in {
        "NEEDS_REVIEW",
        "NEEDS_INFORMATION",
    }


def test_low_uploaded_emissions_do_not_imply_not_applicable() -> None:
    assessment = assess_applicability(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
            reporting_entities_known="TRUE",
            has_taiwan_facilities="YES",
            received_environmental_authority_inventory_notice="YES",
        ),
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
        uploaded_emissions_tco2e=0.01,
    )
    assert assessment.obligations[OBLIGATION_CARBON_FEE].status != "NOT_APPLICABLE"
    assert assessment.obligations[OBLIGATION_GHG_INVENTORY].status != "NOT_APPLICABLE"


def test_incomplete_regulatory_boundary_needs_information() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
            reporting_entities_known="UNKNOWN",
            has_taiwan_facilities="NOT_SURE",
        )
    )
    fee = assessment.obligations[OBLIGATION_CARBON_FEE]
    assert fee.status == "NEEDS_INFORMATION"
    assert "reporting_entities_known" in fee.missing_information


def test_no_unverified_carbon_fee_threshold_invented() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
            reporting_entities_known="TRUE",
            has_taiwan_facilities="YES",
        )
    )
    reason = assessment.obligations[OBLIGATION_CARBON_FEE].reason.lower()
    assert "invent" in reason or "not yet" in reason or "registry" in reason
    assert assessment.obligations[OBLIGATION_CARBON_FEE].status == "NEEDS_REVIEW"


def test_only_verified_rules_create_definitive_conclusions() -> None:
    assessment = _assess(
        CompanyProfile(
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
        )
    )
    rules = load_regulatory_rules().set_index("rule_id")
    for rule_id in assessment.obligations[OBLIGATION_IFRS].applied_rule_ids:
        assert rules.loc[rule_id, "verification_status"] in {
            "VERIFIED_AUTHORITATIVE",
            "VERIFIED_OFFICIAL_GUIDANCE",
            "NOT_COVERED_BY_CURRENT_ORDER",
        }
