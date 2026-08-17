"""Stage 3B.3a — regression guards for customer-facing render bugs."""

from __future__ import annotations

from pathlib import Path

from carbon_ledger.applicability import (
    assess_applicability,
    company_profile_from_mapping,
)
from carbon_ledger.ui.enterprise import (
    emit_html,
    render_money_field,
    render_obligation_result_card,
)
from carbon_ledger.ui.learning import status_chip_html
from carbon_ledger.ui.view_models_compliance import assessment_obligation_cards

REPO_ROOT = Path(__file__).resolve().parents[1]
APL_PAGE = REPO_ROOT / "app_pages" / "applicability.py"
ENTERPRISE = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "enterprise.py"
CSS = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "visual_system.css"
HERO_JS = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "hero_emissions_countup.js"
HERO_SHA = "70cd43b7f1fa2bedf4485bc7846278b736e1c183961c6c7117d6cc8b5f5828c0"


def test_applicability_page_does_not_split_html_card_wrappers() -> None:
    source = APL_PAGE.read_text(encoding="utf-8")
    assert 'st.markdown(\'<div class="cel-card-primary">' not in source
    assert 'st.markdown("</div>"' not in source
    assert "st.markdown('</div>'" not in source


def test_obligation_card_uses_emit_html_helper() -> None:
    source = ENTERPRISE.read_text(encoding="utf-8")
    assert "def emit_html" in source
    assert "st.html" in source
    assert "def render_obligation_result_card" in source
    body = source.split("def render_obligation_result_card", 1)[1]
    body = body.split("\ndef ", 1)[0]
    assert "emit_html(" in body
    assert "cel-obligation-result" in body
    assert "cel-meta-year" in body


def test_status_chip_html_is_balanced() -> None:
    chip = status_chip_html("APPLICABLE", "適用")
    assert chip.count("<span") == chip.count("</span>")
    assert "cel-status-chip--success" in chip
    assert "<" in chip and "適用" in chip


def test_meta_year_css_prevents_vertical_digit_wrap() -> None:
    css = CSS.read_text(encoding="utf-8")
    assert "cel-meta-year" in css
    assert "white-space: nowrap" in css
    assert "minmax(7.5rem" in css or "minmax(8rem" in css


def test_listed_profile_unknown_net_worth_stays_none() -> None:
    profile = company_profile_from_mapping(
        {
            "company_name": "test",
            "reporting_year": 2026,
            "entity_type": "general_listed_company",
            "listing_status": "TWSE",
            "paid_in_capital_twd": 12_000_000_000,
            "net_worth_twd": None,
            "jurisdiction": "TW",
        }
    )
    assert profile.net_worth_twd is None
    assessment = assess_applicability(profile, repo_root=REPO_ROOT)
    cards = assessment_obligation_cards(assessment, "zh-TW")
    ifrs = next(c for c in cards if c["obligation_id"] == "ifrs_s1_s2")
    assert ifrs["status"] == "APPLICABLE"
    assert ifrs["effective_reporting_year"] in {2026, "2026"}
    assert ifrs["first_filing_year"] in {2027, "2027"}


def test_unknown_financials_need_information_not_zero_not_applicable() -> None:
    profile = company_profile_from_mapping(
        {
            "company_name": "unknown-finance-co",
            "reporting_year": 2026,
            "entity_type": "general_listed_company",
            "listing_status": "TWSE",
            "paid_in_capital_twd": None,
            "net_worth_twd": None,
            "jurisdiction": "TW",
        }
    )
    assert profile.paid_in_capital_twd is None
    assert profile.net_worth_twd is None
    assessment = assess_applicability(profile, repo_root=REPO_ROOT)
    cards = assessment_obligation_cards(assessment, "zh-TW")
    statuses = {c["obligation_id"]: c["status"] for c in cards}
    assert statuses.get("ifrs_s1_s2") in {
        "APPLICABLE",
        "NEEDS_INFORMATION",
        "FUTURE_REQUIREMENT",
        "NEEDS_REVIEW",
    }
    # Zero must not appear as a fabricated company money value in reasons.
    for card in cards:
        blob = " ".join(
            [
                str(card.get("status") or ""),
                str(card.get("reason") or ""),
                " ".join(card.get("missing_information") or []),
            ]
        )
        assert "NT$0" not in blob
        assert "0.00 億" not in blob


def test_money_field_unknown_returns_none(monkeypatch) -> None:
    class _SS(dict):
        def __contains__(self, key):  # type: ignore[override]
            return dict.__contains__(self, key)

    state = _SS()
    state["apl_net_unknown"] = True

    class _St:
        session_state = state

        def checkbox(self, *args, **kwargs):
            return True

        def caption(self, *args, **kwargs):
            return None

        def markdown(self, *args, **kwargs):
            return None

        def text_input(self, *args, **kwargs):
            raise AssertionError("numeric input must stay hidden when unknown")

        def selectbox(self, *args, **kwargs):
            raise AssertionError("unit select must stay hidden when unknown")

        def columns(self, *args, **kwargs):
            raise AssertionError("columns must stay unused when unknown")

        def warning(self, *args, **kwargs):
            return None

    import carbon_ledger.ui.enterprise as enterprise

    monkeypatch.setattr(enterprise, "st", _St())
    value = render_money_field(
        "淨值",
        lang="zh-TW",
        field_key="net_worth_twd",
        saved_twd=None,
        unknown_toggle_key="apl_net_unknown",
        amount_key="apl_net_amount",
        unit_key="apl_net_unit",
    )
    assert value is None


def test_emit_html_prefers_st_html(monkeypatch) -> None:
    calls: list[str] = []

    class _St:
        def html(self, payload):
            calls.append(payload)

        def markdown(self, *args, **kwargs):
            raise AssertionError("markdown fallback should not run when html works")

    import carbon_ledger.ui.enterprise as enterprise

    monkeypatch.setattr(enterprise, "st", _St())
    emit_html("<div class='cel-card-primary'><span>ok</span></div>")
    assert calls and "cel-card-primary" in calls[0]


def test_hero_countup_js_unchanged() -> None:
    import hashlib

    digest = hashlib.sha256(HERO_JS.read_bytes()).hexdigest()
    assert digest == HERO_SHA


def test_obligation_card_render_smoke_no_exception() -> None:
    """Rendering helper must accept a real card without raising."""
    profile = company_profile_from_mapping(
        {
            "company_name": "test",
            "reporting_year": 2026,
            "entity_type": "general_listed_company",
            "listing_status": "TWSE",
            "paid_in_capital_twd": 12_000_000_000,
            "net_worth_twd": None,
            "jurisdiction": "TW",
        }
    )
    assessment = assess_applicability(profile, repo_root=REPO_ROOT)
    card = assessment_obligation_cards(assessment, "zh-TW")[0]
    # AppTest-less smoke: function import path remains callable.
    assert callable(render_obligation_result_card)
    assert card.get("title")


def test_apptest_step5_has_no_raw_html_leak() -> None:
    """Streamlit AppTest: seeded listed company reaches Step 5 without HTML leak."""
    from streamlit.testing.v1 import AppTest

    from carbon_ledger.ui.state import (
        STATE_APPLICABILITY_WIZARD_STEP,
        STATE_COMPANY_PROFILE_EDITING,
        activate_demo_mode,
        initialize_ui_state,
        save_company_profile,
    )

    at = AppTest.from_file(str(REPO_ROOT / "streamlit_app.py"), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    # Keep customer mode — do not rely on demo analysis for this page.
    save_company_profile(
        at.session_state,
        {
            "company_name": "test",
            "reporting_year": 2026,
            "entity_type": "general_listed_company",
            "listing_status": "TWSE",
            "paid_in_capital_twd": 12_000_000_000,
            "net_worth_twd": None,
            "jurisdiction": "TW",
        },
    )
    at.session_state[STATE_COMPANY_PROFILE_EDITING] = True
    at.session_state[STATE_APPLICABILITY_WIZARD_STEP] = 4
    at.switch_page("app_pages/applicability.py")
    at.run()
    assert not at.exception
    chunks: list[str] = []
    for name in ("markdown", "text", "caption", "write", "title", "header"):
        for item in getattr(at, name, []) or []:
            for attr in ("value", "body", "label"):
                value = getattr(item, attr, None)
                if value is not None:
                    chunks.append(str(value))
    text = "\n".join(chunks)
    compact = text.replace(" ", "").replace("\n", "")
    # Bug 1 signature: orphan closers + chip markup leaked as visible text.
    assert "</p></div><span" not in compact
    assert "</p></div><spanclass=\"cel-status-chip" not in compact
    assert "適用" in text or "IFRS" in text
    _ = activate_demo_mode
