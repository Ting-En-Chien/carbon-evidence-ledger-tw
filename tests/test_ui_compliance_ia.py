"""Stage 3B UI compliance / applicability integration tests."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.applicability import (
    OBLIGATION_IFRS,
    CompanyProfile,
    assess_applicability,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_APPLICABILITY_ASSESSMENT,
    STATE_COMPANY_PROFILE,
    STATE_COMPANY_PROFILE_EDITING,
    activate_demo_mode,
    get_applicability_assessment,
    initialize_ui_state,
    save_applicability_assessment,
    save_company_profile,
)
from carbon_ledger.ui.view_models import calculated_emissions_summary

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
        "last_global_check_at": "2026-08-12T10:00:00Z",
        "changes_pending_review": 0,
        "state_source": "durable_persisted_state",
    }


def test_company_profile_survives_page_navigation() -> None:
    at = _run_app()
    mapping = {
        "company_name": "導航測試公司",
        "reporting_year": 2026,
        "entity_type": "financial_holding_company",
        "jurisdiction": "TW",
    }
    save_company_profile(at.session_state, mapping)
    assessment = assess_applicability(
        CompanyProfile(
            company_name="導航測試公司",
            reporting_year=2026,
            entity_type="financial_holding_company",
        ),
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )
    save_applicability_assessment(at.session_state, assessment)
    at = _switch(at, "app_pages/dashboard.py")
    at = _switch(at, "app_pages/frameworks.py")
    at = _switch(at, "app_pages/applicability.py")
    stored = at.session_state[STATE_COMPANY_PROFILE]
    assert stored["company_name"] == "導航測試公司"
    assert stored["entity_type"] == "financial_holding_company"
    assert get_applicability_assessment(at.session_state) is not None


def test_four_obligation_result_cards_render() -> None:
    from carbon_ledger.ui.customer_presenters import present_assessment

    at = _run_app()
    assessment = assess_applicability(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
        ),
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )
    save_company_profile(
        at.session_state,
        {
            "company_name": "卡片測試",
            "reporting_year": 2026,
            "entity_type": "financial_holding_company",
        },
    )
    at.session_state[STATE_COMPANY_PROFILE_EDITING] = False
    save_applicability_assessment(at.session_state, assessment)
    presented = present_assessment(assessment, ZH)
    titles = [item.title for item in presented.presentations]
    domains = [item.domain for item in presented.presentations]
    assert "IFRS永續揭露準則適用時程（S1＋S2）" in titles
    assert "台灣溫室氣體盤查" not in titles
    assert "環境部溫室氣體查驗" not in titles
    assert "碳費" not in titles
    assert "ifrs_assurance" in domains or "ifrs" in domains
    at = _switch(at, "app_pages/applicability.py")
    text = _all_text(at)
    assert "管理員" not in text
    assert "適用報導年度：—" not in text
    assert "為什麼？" not in text


def test_no_raw_i18n_keys_on_applicability_and_dashboard() -> None:
    at = _switch(_run_app(), "app_pages/applicability.py")
    text = _all_text(at)
    assert "apl." not in text
    assert "dash.section_" not in text
    at = _switch(at, "app_pages/dashboard.py")
    text = _all_text(at)
    assert "reg.status_title" not in text
    assert "apl.status." not in text


def test_no_fake_compliance_percentage() -> None:
    at = _switch(_run_app(), "app_pages/dashboard.py")
    text = _all_text(at).lower()
    assert "compliance score" not in text
    assert "ifrs compliance" not in text
    assert "68%" not in text
    assert "84%" not in text
    # Negating "not a compliance score" is fine; ban scored readiness claims.
    assert "合規分數：" not in _all_text(at)
    assert "readiness 84" not in text


def test_cbam_absent_from_v1_compliance_surfaces() -> None:
    at = _switch(_run_app(), "app_pages/dashboard.py")
    text = _all_text(at)
    assert "CBAM" not in text
    at = _switch(at, "app_pages/applicability.py")
    assert "CBAM" not in _all_text(at)


def test_excel_csv_upload_remains_accessible() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    assert len(at.file_uploader) >= 1


def test_dashboard_consumes_same_assessment_object() -> None:
    at = _run_app()
    assessment = assess_applicability(
        CompanyProfile(
            reporting_year=2026,
            entity_type="financial_holding_company",
        ),
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )
    save_applicability_assessment(at.session_state, assessment)
    at = _switch(at, "app_pages/dashboard.py")
    assert at.session_state[STATE_APPLICABILITY_ASSESSMENT] is assessment
    text = _all_text(at)
    status = assessment.obligations[OBLIGATION_IFRS].status
    assert t(f"apl.status.{status}", ZH) in text
    assert (
        t("dash.section_requirements", ZH) in text
        or t("dash.section_next", ZH) in text
        or t("dash.req.headline", ZH) in text
    )


def test_hero_emissions_still_uses_calculated_tco2e() -> None:
    at = _run_app()
    result = at.session_state["pipeline_result"]
    emissions = calculated_emissions_summary(result, ZH)
    assert "calculated_tco2e" in emissions
    at = _switch(at, "app_pages/dashboard.py")
    text = _all_text(at)
    assert t("dash.section_emissions_summary", ZH) in text


def test_regulatory_freshness_display_uses_actual_state() -> None:
    at = _switch(_run_app(), "app_pages/dashboard.py")
    text = _all_text(at)
    assert t("reg.status_title", ZH) in text
    # Must render a business-friendly status from durable state.
    assert any(
        label in text
        for label in (
            t("reg.status_verified", ZH),
            t("reg.status_pending_verification", ZH),
            t("reg.freshness.CURRENT", ZH),
            t("reg.freshness.CHECK_DUE", ZH),
            t("reg.freshness.UPDATE_REQUIRED", ZH),
            t("reg.freshness.STALE", ZH),
            t("reg.freshness.PARTIAL", ZH),
            t("reg.freshness.FRESHNESS_STATE_UNAVAILABLE", ZH),
            t("reg.freshness.MANUAL_VERIFICATION_REQUIRED", ZH),
        )
    )
    assert "hard-coded Current" not in text
    assert t("reg.last_verified", ZH) in text or t("reg.auto_sources_label", ZH) in text
    deduped = "\n".join(dict.fromkeys(text.splitlines()))
    assert deduped.count("下一步") == 1


def test_initialize_does_not_wipe_company_profile() -> None:
    state: dict = {}
    initialize_ui_state(state)
    save_company_profile(
        state,
        {"company_name": "保留", "entity_type": "bank", "reporting_year": 2027},
    )
    initialize_ui_state(state, force=False)
    assert state[STATE_COMPANY_PROFILE]["company_name"] == "保留"
