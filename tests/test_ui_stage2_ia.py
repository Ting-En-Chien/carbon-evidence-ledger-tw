"""Stage 2 information-architecture coverage (V1 navigation + CBAM hidden)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from carbon_ledger.pipeline import run_demo_pipeline
from carbon_ledger.ui.glossary import glossary_contains, glossary_pairs
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import _HERO_COUNT_JS_PATH
from carbon_ledger.ui.state import STATE_INCLUDE_CBAM, initialize_ui_state
from carbon_ledger.ui.tutorial import get_tutorial_copy
from carbon_ledger.ui.view_models import calculated_emissions_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")
ZH = "zh-TW"


def _run_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
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


def test_v1_navigation_has_six_approved_areas() -> None:
    titles_zh = [
        t("nav.dashboard", ZH),
        t("nav.applicability", ZH),
        t("nav.ifrs", ZH),
        t("nav.taiwan", ZH),
        t("nav.evidence", ZH),
        t("nav.audit", ZH),
    ]
    assert titles_zh == [
        "合規總覽",
        "適用性判定",
        "IFRS S1/S2",
        "台灣溫室氣體與碳費",
        "證據與資料",
        "報表與匯出",
    ]
    titles_en = [
        t("nav.dashboard", "en"),
        t("nav.applicability", "en"),
        t("nav.ifrs", "en"),
        t("nav.taiwan", "en"),
        t("nav.evidence", "en"),
        t("nav.audit", "en"),
    ]
    assert titles_en == [
        "Compliance Overview",
        "Applicability",
        "IFRS S1/S2",
        "Taiwan GHG / Carbon Fee",
        "Evidence & Data",
        "Reporting & Export",
    ]
    at = _run_app()
    text = _all_text(at)
    assert "合規總覽" in text
    assert "分析結果" not in text
    assert "目前需要注意" in text
    assert "缺少的資料" in text
    assert "排放資料摘要" in text


def test_rendered_ui_has_no_raw_i18n_keys() -> None:
    """Visible labels must never expose internal translation keys."""
    import re

    pages = [
        "app_pages/dashboard.py",
        "app_pages/applicability.py",
        "app_pages/frameworks.py",
        "app_pages/taiwan_ghg.py",
        "app_pages/evidence_data.py",
        "app_pages/audit_export.py",
        "app_pages/data_intake.py",
        "app_pages/activity_explorer.py",
        "app_pages/issues_actions.py",
    ]
    # Patterns that match developer key leakage in visible copy.
    key_pattern = re.compile(
        r"\b(?:nav|dash|apl|fw|tw|ev|aud|app|tut|sidebar|chart)"
        r"\.[a-zA-Z0-9_.]+\b"
    )
    at = _run_app()
    for page in pages:
        at = _switch(at, page)
        text = _all_text(at)
        # Also scan button labels.
        for button in list(at.button) + list(getattr(at, "download_button", [])):
            label = getattr(button, "label", None)
            if label is not None:
                text += f"\n{label}"
        for box in at.checkbox:
            label = getattr(box, "label", None)
            if label is not None:
                text += f"\n{label}"
        hits = sorted(set(key_pattern.findall(text)))
        assert hits == [], f"{page} leaked i18n keys: {hits}"
        # Old IA labels must not reappear as the primary homepage title.
        if page == "app_pages/dashboard.py":
            assert "合規總覽" in text
            assert "分析結果" not in text
        if page == "app_pages/audit_export.py":
            assert "報表與匯出" in text
            assert "稽核與匯出" not in text


def test_cbam_absent_from_v1_sidebar_and_messaging() -> None:
    at = _run_app()
    labels = [str(box.label) for box in at.checkbox]
    joined = "\n".join(labels)
    text = _all_text(at)
    assert "歐盟出口" not in joined
    assert "EU export" not in joined
    assert "EU CBAM" not in text
    assert "CBAM" not in joined
    tutorial = get_tutorial_copy(ZH)
    assert "CBAM" not in tutorial["steps"][0]["body"]
    assert "CBAM" not in tutorial["steps"][3]["body"]
    assert not glossary_contains("CBAM")
    for title, _body in glossary_pairs(ZH):
        assert "CBAM" not in title


def test_cbam_backend_still_present_and_usable() -> None:
    assert (REPO_ROOT / "src/carbon_ledger/cbam.py").is_file()
    assert (REPO_ROOT / "config/cbam_rules.csv").is_file()
    assert (REPO_ROOT / "config/cbam_product_scenario.csv").is_file()
    assert (REPO_ROOT / "data/reference/cbam_references.csv").is_file()
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="stage2_cbam_backend",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=False,
        include_cbam=True,
        include_ifrs_s2=False,
    )
    assert result.include_cbam is True
    assert len(result.cbam_evaluations) == 5


def test_v1_default_disables_cbam_adapter() -> None:
    state: dict = {}
    initialize_ui_state(state)
    assert state[STATE_INCLUDE_CBAM] is False
    at = _run_app()
    assert at.session_state["include_cbam"] is False
    assert at.session_state["pipeline_result"].include_cbam is False


def test_ifrs_page_exposes_four_pillars() -> None:
    at = _switch(_run_app(), "app_pages/frameworks.py")
    labels = [str(tab.label) for tab in at.tabs]
    assert t("fw.pillar.governance", ZH) in labels
    assert t("fw.pillar.strategy", ZH) in labels
    assert t("fw.pillar.risk", ZH) in labels
    assert t("fw.pillar.metrics", ZH) in labels
    assert "EU CBAM" not in labels
    text = _all_text(at)
    assert "規則集尚未實作" in text or "Rule set not yet implemented" in text


def test_taiwan_page_exposes_three_tracks() -> None:
    at = _switch(_run_app(), "app_pages/taiwan_ghg.py")
    text = _all_text(at)
    assert "溫室氣體盤查" in text or "GHG Inventory" in text
    assert "查驗" in text or "Verification" in text
    assert "碳費" in text or "Carbon Fee" in text
    assert "需要更多資訊" in text
    assert "規則集尚未實作" in text
    assert "合規分數" not in text
    assert "compliance score" not in text.lower()


def test_applicability_does_not_guess() -> None:
    at = _switch(_run_app(), "app_pages/applicability.py")
    text = _all_text(at)
    assert "需要更多資訊" in text
    assert "Applicable" not in text or "需要更多資訊" in text
    # Must not invent a positive applicability conclusion for Taiwan fee.
    assert "已適用碳費" not in text


def test_evidence_workspace_defaults_to_data_upload() -> None:
    """Sidebar Evidence & Data lands on intake with uploader immediately visible."""
    at = _switch(_run_app(), "app_pages/data_intake.py")
    text = _all_text(at)
    assert "證據與資料" in text
    assert "匯入公司資料" in text or "資料匯入" in text
    assert len(at.file_uploader) >= 1
    nav_labels: list[str] = []
    selected_nav: list[str] = []
    for control in getattr(at, "segmented_control", []):
        options = [
            str(option) for option in (getattr(control, "options", None) or [])
        ]
        if "資料匯入" in options and "證據紀錄" in options:
            nav_labels = options
            value = getattr(control, "value", None)
            if value is not None:
                selected_nav.append(str(value))
    assert nav_labels == [
        "資料匯入",
        "活動資料",
        "待處理問題",
        "證據紀錄",
    ]
    assert "資料匯入" in selected_nav


def test_evidence_records_tab_still_reachable() -> None:
    at = _switch(_run_app(), "app_pages/evidence_data.py")
    text = _all_text(at)
    assert "證據紀錄" in text
    assert "證據與資料" in text


def test_hero_counter_uses_calculated_final_not_hardcoded() -> None:
    at = _run_app()
    text = _all_text(at)
    result = at.session_state["pipeline_result"]
    emissions = calculated_emissions_summary(result, ZH)
    value = emissions["calculated_tco2e"]
    assert value is not None
    assert 'data-cel-hero-emissions="1"' in text
    assert f'data-cel-target="{float(value)}"' in text
    assert "5311" not in Path(
        REPO_ROOT / "src/carbon_ledger/ui/hero_emissions_countup.js"
    ).read_text(encoding="utf-8")
    script = _HERO_COUNT_JS_PATH.read_text(encoding="utf-8")
    assert "data-cel-hero-emissions" in script
    assert "1400" in script


def test_calculation_pipeline_unchanged_for_core_demo() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="stage2_core",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=False,
        include_ifrs_s2=True,
    )
    assert not result.calculation_results.empty
    assert result.include_cbam is False
    emissions = calculated_emissions_summary(result, ZH)
    assert emissions["calculated_tco2e"] is not None
