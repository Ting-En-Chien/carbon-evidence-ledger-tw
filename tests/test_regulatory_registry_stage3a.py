"""Stage 3A / 3A.1 / 3A.2 regulatory registry integrity tests."""

from __future__ import annotations

from pathlib import Path

from carbon_ledger.regulatory_registry import (
    CONCEPT_LAYERS,
    VERIFICATION_STATUSES,
    active_rules,
    load_regulatory_rules,
    load_regulatory_sources,
    operable_rules,
    outranks,
    rules_for_entity_type,
    validate_registry_integrity,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = REPO_ROOT / "data/reference/regulatory_sources.csv"
RULES_PATH = REPO_ROOT / "config/regulatory_rules.csv"


def test_regulatory_sources_registry_loads() -> None:
    sources = load_regulatory_sources(SOURCES_PATH)
    assert len(sources) >= 20
    ids = set(sources["source_id"])
    assert "src_tw_fsc_law_portal" in ids
    assert "src_tw_securities_fin_report_fl007040" in ids
    assert "src_tw_order_11403856095_securities" in ids
    assert "src_tw_order_11403856094_recognised" in ids
    assert "src_tw_fcm_fin_report_fl021990" in ids
    assert "src_tw_order_11403856096_fcm" in ids
    assert sources["official_url"].str.startswith("http").all()


def test_regulatory_rules_registry_loads_and_links_sources() -> None:
    sources = load_regulatory_sources(SOURCES_PATH)
    rules = load_regulatory_rules(RULES_PATH)
    assert len(rules) >= 90
    issues = validate_registry_integrity(sources, rules)
    assert issues == []
    assert set(rules["verification_status"]) <= VERIFICATION_STATUSES


def test_concept_layers_are_separated() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    layers = set(rules["concept_layer"])
    assert layers <= CONCEPT_LAYERS


def test_authoritative_fsc_sources_outrank_news_releases() -> None:
    sources = load_regulatory_sources(SOURCES_PATH)
    assert outranks(
        sources,
        "src_tw_annual_report_rules_fl007032",
        "src_tw_sfb_press_20251028",
    )
    assert outranks(
        sources,
        "src_tw_order_11403856095_securities",
        "src_tw_sfb_press_20251028",
    )
    assert not outranks(
        sources,
        "src_tw_sfb_press_20251028",
        "src_tw_order_11403851756",
    )


def test_securities_firms_use_own_regulatory_family() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    sf = rules_for_entity_type(rules, "securities_firm")
    assert not sf.empty
    assert (sf["framework"] == "TW_IFRS_S1_S2_SF").any()
    assert "tw_sf_art32_1_family" in set(sf["rule_id"])
    assert "src_tw_securities_fin_report_fl007040" in set(sf["source_id"])
    # Incorrect FL007032 mapping must be superseded / not operable.
    legacy = rules.loc[
        rules["rule_id"] == "tw_securities_firm_uses_general_ar_if_public_company"
    ].iloc[0]
    assert legacy["rule_status"] == "SUPERSEDED"
    operable_sf_ids = set(sf["rule_id"])
    assert "tw_securities_firm_uses_general_ar_if_public_company" not in operable_sf_ids


def test_futures_commission_merchants_have_own_family() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    fcm = rules_for_entity_type(rules, "futures_commission_merchant")
    assert not fcm.empty
    assert (fcm["framework"] == "TW_IFRS_S1_S2_FCM").any()
    family = rules.loc[rules["rule_id"] == "tw_fcm_art34_1_family"].iloc[0]
    assert family["verification_status"] == "VERIFIED_AUTHORITATIVE"
    assert family["product_support_status"] == "OUT_OF_V1_SCOPE"


def test_taiwan_recognised_ifrs_version_distinct_from_international_latest() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    row = rules.loc[
        rules["rule_id"] == "tw_order_51755_recognised_ifrs_version_locus"
    ].iloc[0]
    assert row["verification_status"] == "VERIFIED_AUTHORITATIVE"
    assert row["taiwan_recognised_version"] != row["international_standard_version"]


def test_international_ifrs_amendments_do_not_auto_become_taiwan_active() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    row = rules.loc[
        rules["rule_id"] == "ifrs_s2_ghg_amendments_2025_international"
    ].iloc[0]
    assert row["taiwan_status"] == "NOT_YET_VERIFIED"
    assert row["jurisdiction"] == "INTL"


def test_rule_level_effective_dates_support_active_and_future() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    assert "ACTIVE" in set(rules["rule_status"])
    assert "FUTURE" in set(rules["rule_status"])
    future = rules[rules["rule_status"] == "FUTURE"]
    assert (future["rule_effective_from"] != "").all()
    # Same FCM regulation can have a later provision effective date.
    note = rules.loc[
        rules["rule_id"] == "tw_fcm_other_articles_fy2028_package_note"
    ].iloc[0]
    assert note["rule_effective_from"] == "2028-01-01"
    assert note["rule_status"] == "FUTURE"


def test_superseded_rules_remain_historically_available() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    superseded = rules[rules["rule_status"] == "SUPERSEDED"]
    assert not superseded.empty
    live = operable_rules(rules)
    assert "SUPERSEDED" not in set(live["rule_status"])
    assert "PENDING_REVIEW" not in set(active_rules(rules)["rule_status"])


def test_manual_ifrs_access_remains_explicit() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    manual = rules[rules["verification_status"] == "REQUIRES_MANUAL_IFRS_ACCESS"]
    assert len(manual) >= 10


def test_not_covered_by_current_order_distinct_from_research_failure() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    assert "NOT_COVERED_BY_CURRENT_ORDER" in set(rules["verification_status"])
    covered = rules[rules["verification_status"] == "NOT_COVERED_BY_CURRENT_ORDER"]
    assert not covered.empty


def test_entity_types_supported() -> None:
    rules = load_regulatory_rules(RULES_PATH)
    tokens: set[str] = set()
    for value in rules["entity_type"]:
        tokens.update(part.strip() for part in str(value).split("|") if part.strip())
    for required in {
        "general_listed_company",
        "general_otc_company",
        "financial_holding_company",
        "bank",
        "bills_finance_company",
        "securities_firm",
        "futures_commission_merchant",
        "other",
    }:
        assert required in tokens


def test_research_and_coverage_docs_exist() -> None:
    assert (REPO_ROOT / "docs/regulatory_research_log.md").is_file()
    assert (REPO_ROOT / "docs/regulatory_source_coverage.md").is_file()
    assert (REPO_ROOT / "docs/regulatory_monitoring.md").is_file()
    coverage = (REPO_ROOT / "docs/regulatory_source_coverage.md").read_text(
        encoding="utf-8"
    )
    assert "VERIFIED_AUTHORITATIVE" in coverage
    assert "PREVIOUS STATUS" in coverage
    assert "securities_firm" in coverage
    assert "futures_commission_merchant" in coverage


def test_calculation_pipeline_modules_untouched_by_stage3a_loader() -> None:
    import carbon_ledger.regulatory_monitor as mon
    import carbon_ledger.regulatory_registry as reg

    assert not hasattr(reg, "calculate")
    assert not hasattr(mon, "calculate")
    assert "calculate" not in reg.__dict__
    assert "calculate" not in mon.__dict__
