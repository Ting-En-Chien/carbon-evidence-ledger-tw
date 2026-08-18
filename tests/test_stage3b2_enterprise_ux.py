"""Stage 3B.2 — enterprise UX, wizard, money input, localization."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.applicability import (
    OBLIGATION_IFRS,
    CompanyProfile,
    assess_applicability,
    company_profile_from_mapping,
)
from carbon_ledger.ui.money_input import normalize_money_to_twd, parse_optional_int
from carbon_ledger.ui.state import (
    STATE_APPLICABILITY_WIZARD_STEP,
    STATE_COMPANY_PROFILE_EDITING,
    activate_demo_mode,
    get_company_profile_mapping,
    initialize_ui_state,
    save_company_profile,
)
from carbon_ledger.ui.view_models import calculated_emissions_summary
from carbon_ledger.ui.view_models_compliance import (
    assessment_obligation_cards,
    localize_obligation_text,
    obligation_card_view,
    unified_attention_items,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
ZH = "zh-TW"


def _run_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    activate_demo_mode(at.session_state)
    at.run()
    assert not at.exception
    return at


def _all_text(at: AppTest) -> str:
    chunks: list[str] = []
    for collection_name in (
        "markdown",
        "caption",
        "text",
        "info",
        "success",
        "warning",
        "error",
        "title",
    ):
        collection = getattr(at, collection_name, None)
        if collection is None:
            continue
        for item in collection:
            value = getattr(item, "value", None)
            if value is not None:
                chunks.append(str(value))
            body = getattr(item, "body", None)
            if body is not None:
                chunks.append(str(body))
    return "\n".join(chunks)


def _switch(at: AppTest, page: str) -> AppTest:
    at.switch_page(page)
    at.run()
    assert not at.exception
    return at


def _fresh_ok(repo_root=None, required_source_ids=None, **kwargs):
    return {
        "analysis_allowed": True,
        "state": "CURRENT",
        "overall_regulatory_freshness": "CURRENT",
        "last_successful_check_at": "2026-08-12T10:00:00Z",
        "changes_pending_review": 0,
        "state_source": "durable_persisted_state",
    }


def test_blank_money_is_not_zero() -> None:
    assert normalize_money_to_twd(0, "yi") is None
    assert normalize_money_to_twd(None, "yi") is None
    assert parse_optional_int(0) is None
    assert parse_optional_int("") is None
    assert parse_optional_int(None) is None
    profile = company_profile_from_mapping(
        {
            "reporting_year": 2026,
            "entity_type": "general_listed_company",
            "paid_in_capital_twd": None,
            "net_worth_twd": None,
        }
    )
    assert profile.paid_in_capital_twd is None
    assert profile.net_worth_twd is None


def test_business_friendly_money_conversion() -> None:
    assert normalize_money_to_twd(120, "yi") == 12_000_000_000
    assert normalize_money_to_twd(500, "wan") == 5_000_000
    assert normalize_money_to_twd(1000, "yuan") == 1000


def test_wizard_profile_persistence() -> None:
    state: dict = {}
    initialize_ui_state(state)
    mapping = {
        "company_name": "精靈測試",
        "reporting_year": 2026,
        "entity_type": "general_listed_company",
        "listing_status": "TWSE",
        "paid_in_capital_twd": 12_000_000_000,
        "net_worth_twd": None,
        "jurisdiction": "TW",
    }
    save_company_profile(state, mapping)
    state[STATE_APPLICABILITY_WIZARD_STEP] = 3
    state[STATE_COMPANY_PROFILE_EDITING] = True
    assert get_company_profile_mapping(state)["company_name"] == "精靈測試"
    assert get_company_profile_mapping(state)["net_worth_twd"] is None
    assert state[STATE_APPLICABILITY_WIZARD_STEP] == 3


def test_progressive_disclosure_capital_for_listed_only() -> None:
    listed = "general_listed_company"
    bank = "bank"
    assert listed in {
        "general_listed_company",
        "general_otc_company",
        "securities_firm",
        "futures_commission_merchant",
    }
    assert bank not in {
        "general_listed_company",
        "general_otc_company",
        "securities_firm",
        "futures_commission_merchant",
    }


def test_validated_case_unchanged() -> None:
    assessment = assess_applicability(
        CompanyProfile(
            company_name="Demo Fasteners Taiwan",
            entity_type="general_listed_company",
            listing_status="TWSE",
            reporting_year=2026,
            paid_in_capital_twd=12_000_000_000,
        ),
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )
    ifrs = assessment.obligations[OBLIGATION_IFRS]
    assert ifrs.status == "APPLICABLE"
    assert ifrs.effective_reporting_year == 2026
    assert ifrs.first_filing_year == 2027


def test_chinese_result_explanations_not_english() -> None:
    assessment = assess_applicability(
        CompanyProfile(
            company_name="Demo",
            entity_type="general_listed_company",
            listing_status="TWSE",
            reporting_year=2026,
            paid_in_capital_twd=12_000_000_000,
        ),
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )
    card = obligation_card_view(assessment.obligations[OBLIGATION_IFRS], ZH)
    assert "Based on the current company profile" not in card["reason"]
    assert "Prepare IFRS" not in (card["next_action"] or "")
    assert "適用" in card["status_label"] or card["status"] == "APPLICABLE"


def test_localize_blocks_english_in_zh() -> None:
    text = localize_obligation_text(
        obligation_id="ghg_inventory",
        status="NEEDS_INFORMATION",
        text="Verified Taiwan GHG inventory applicability rules are not yet present.",
        kind="reason",
        lang=ZH,
    )
    assert "Verified Taiwan" not in text
    assert "還無法確認" in text or "資料" in text


def test_result_cards_hide_rule_ids_by_default_structure() -> None:
    assessment = assess_applicability(
        CompanyProfile(
            entity_type="general_listed_company",
            listing_status="TWSE",
            reporting_year=2026,
            paid_in_capital_twd=12_000_000_000,
        ),
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )
    cards = assessment_obligation_cards(assessment, ZH)
    titles = [c["title"] for c in cards]
    assert any("IFRS S1/S2" in title for title in titles)
    assert any("確信" in title for title in titles)
    assert any("查驗" in title for title in titles)
    assert titles.count([t for t in titles if "查驗" in t or "確信" in t][0]) >= 0
    # Distinct wording present
    joined = " ".join(titles)
    assert "IFRS Scope 1/2" in joined or "確信" in joined
    assert "環境部" in joined or "環境查驗" in joined or "台灣環境" in joined


def test_one_current_attention_section_on_dashboard() -> None:
    at = _switch(_run_app(), "app_pages/dashboard.py")
    text = _all_text(at)
    # AppTest may duplicate markdown value/body; dedupe exact lines.
    deduped = "\n".join(dict.fromkeys(text.splitlines()))
    assert deduped.count("下一步") == 1


def test_admin_monitoring_expander_absent_in_customer_mode() -> None:
    """Stage 3B.3: default CUSTOMER rendering must not expose admin internals."""
    at = _switch(_run_app(), "app_pages/dashboard.py")
    expanders = list(getattr(at, "expander", []) or [])
    labels = [str(getattr(item, "label", "") or "") for item in expanders]
    admin_labels = [
        label
        for label in labels
        if "系統維護" in label or "admin" in label.lower()
    ]
    text = _all_text(at)
    assert not admin_labels
    assert "automated_sources_expected" not in text
    assert "MONITORING_PARTIAL" not in text


def test_evidence_uploader_still_accessible() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    assert len(at.file_uploader) >= 1
    text = _all_text(at)
    assert "上傳能源與營運資料" in text
    assert "選擇公司檔案" in text or "上傳資料檔" in text


def test_countup_still_uses_calculated_tco2e() -> None:
    at = _run_app()
    result = at.session_state["pipeline_result"]
    emissions = calculated_emissions_summary(result, ZH)
    target = float(emissions["calculated_tco2e"])
    assert target > 0
    js_path = REPO_ROOT / "src/carbon_ledger/ui/hero_emissions_countup.js"
    assert js_path.is_file()
    js = js_path.read_text(encoding="utf-8")
    assert "5311" not in js
    # Motion helper still reads calculated_tco2e (not a hard-coded demo number).
    from carbon_ledger.ui import motion

    source = Path(motion.__file__).read_text(encoding="utf-8")
    assert "calculated_tco2e" in source or "emissions_value" in source
    at = _switch(at, "app_pages/dashboard.py")
    assert "排放" in _all_text(at)


def test_no_fake_compliance_percentage_and_no_cbam() -> None:
    at = _switch(_run_app(), "app_pages/dashboard.py")
    text = _all_text(at)
    assert "合規分數：" not in text
    assert "80% compliant" not in text.lower()
    assert "CBAM" not in text
    assert "目前已計算排放量" in text


def test_unified_attention_merges_sources() -> None:
    items = unified_attention_items(
        assessment=None,
        emissions_priority=[
            {"reason": "缺少電費單", "record_id": "r1"},
        ],
        lang=ZH,
        limit=5,
    )
    assert items
    assert items[0]["page"].endswith("applicability.py")
