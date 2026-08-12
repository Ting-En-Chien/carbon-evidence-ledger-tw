"""AppTest coverage for Phase 8 / 8B Streamlit application."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.ui.i18n import STATE_LANGUAGE
from carbon_ledger.ui.tutorial import (
    STATE_TUTORIAL_OPEN_COUNT,
    get_tutorial_copy,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"


def _run_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception
    return at


def _all_text(at: AppTest) -> str:
    chunks: list[str] = []
    for collection_name in (
        "title",
        "header",
        "subheader",
        "markdown",
        "text",
        "caption",
        "info",
        "warning",
        "success",
        "error",
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
    for button in at.button:
        label = getattr(button, "label", None)
        if label is not None:
            chunks.append(str(label))
    for box in at.checkbox:
        label = getattr(box, "label", None)
        if label is not None:
            chunks.append(str(label))
    for item in getattr(at, "download_button", []):
        label = getattr(item, "label", None)
        if label is not None:
            chunks.append(str(label))
    return "\n".join(chunks)


def _switch(at: AppTest, page: str) -> AppTest:
    at.switch_page(page)
    at.run()
    assert not at.exception
    return at


def _switch_language(at: AppTest, option: str) -> AppTest:
    code = "en" if option == "EN" else "zh-TW"
    at.session_state[STATE_LANGUAGE] = code
    if len(at.segmented_control) >= 1:
        try:
            at.segmented_control[0].set_value(option)
        except Exception:
            pass
    at.run()
    assert not at.exception
    return at


def test_application_starts_without_exception() -> None:
    at = _run_app()
    assert not at.exception


def test_traditional_chinese_is_default_language() -> None:
    at = _run_app()
    assert at.session_state[STATE_LANGUAGE] == "zh-TW"
    text = _all_text(at)
    assert "重新分析" in text or "執行示範分析" in text


def test_dashboard_is_default_page() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "分析結果" in text


def test_page_title_contains_carbon_evidence_ledger() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "Carbon Evidence Ledger" in text


def test_sidebar_contains_demo_workspace() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "示範資料" in text
    assert "2024 示範資料" in text or "重新分析" in text


def test_sidebar_contains_run_analysis() -> None:
    at = _run_app()
    labels = [str(button.label) for button in at.button]
    assert "重新分析" in labels
    assert "使用這批資料開始分析" not in labels
    assert labels.count("重新分析") == 1


def test_dashboard_has_single_primary_start_analysis() -> None:
    at = _run_app()
    start_labels = [
        str(button.label)
        for button in at.button
        if str(button.label)
        in {
            "重新分析",
            "Re-run analysis",
            "執行示範分析",
            "Run demo analysis",
            "開始分析",
            "Start analysis",
        }
    ]
    assert len(start_labels) == 1


def test_all_three_adapter_controls_exist() -> None:
    at = _run_app()
    labels = [str(box.label) for box in at.checkbox]
    joined = "\n".join(labels)
    text = _all_text(at)
    assert "公司碳盤查" in joined or "Corporate GHG" in joined or "GHG" in text
    assert "歐盟出口" in joined or "EU export" in joined or "EU CBAM" in text
    assert "氣候揭露" in joined or "Climate disclosure" in joined or "IFRS S2" in text
    # Framework toggles live under analysis settings progressive disclosure.
    expander_labels = [
        str(getattr(item, "label", "") or "")
        for item in getattr(at, "expander", [])
    ]
    assert any("分析設定" in label for label in expander_labels) or "分析設定" in text
    assert "GHG Protocol" in text
    assert "EU CBAM" in text
    assert "IFRS S2" in text


def test_default_state_enables_all_three_adapters() -> None:
    at = _run_app()
    assert at.session_state["include_ghg"] is True
    assert at.session_state["include_cbam"] is True
    assert at.session_state["include_ifrs_s2"] is True
    result = at.session_state["pipeline_result"]
    assert result.include_ghg is True
    assert result.include_cbam is True
    assert result.include_ifrs_s2 is True


def test_language_selector_exists() -> None:
    at = _run_app()
    assert len(at.segmented_control) >= 1
    options = list(at.segmented_control[0].options)
    assert "繁中" in options
    assert "EN" in options


def test_switching_to_english_changes_page_copy() -> None:
    at = _run_app()
    before = at.session_state["pipeline_result"]
    flags = (
        at.session_state["include_ghg"],
        at.session_state["include_cbam"],
        at.session_state["include_ifrs_s2"],
    )
    at = _switch_language(at, "EN")
    text = _all_text(at)
    assert (
        "Start analysis" in text
        or "Run demo analysis" in text
        or "Re-run analysis" in text
    )
    assert at.session_state[STATE_LANGUAGE] == "en"
    assert at.session_state["pipeline_result"] is before
    assert (
        at.session_state["include_ghg"],
        at.session_state["include_cbam"],
        at.session_state["include_ifrs_s2"],
    ) == flags


def test_tutorial_button_exists_and_opens() -> None:
    at = _run_app()
    labels = [str(button.label) for button in at.button]
    assert any("操作教學" in label or "Tutorial" in label for label in labels)
    tutorial_buttons = [
        button
        for button in at.button
        if "操作教學" in str(button.label) or "Tutorial" in str(button.label)
    ]
    before_count = int(at.session_state[STATE_TUTORIAL_OPEN_COUNT])
    tutorial_buttons[0].click()
    at.run()
    assert not at.exception
    after_count = int(at.session_state[STATE_TUTORIAL_OPEN_COUNT])
    assert after_count == before_count + 1

    # Dialog body text is not required from AppTest page-wide collection.
    # Tutorial copy is validated through the pure helper below.
    zh_copy = get_tutorial_copy("zh-TW")
    assert "第一次使用" in zh_copy["title"]
    assert zh_copy["steps"][0]["title"] == "選擇分析內容"
    assert "開始分析" in zh_copy["steps"][1]["title"]
    assert "待處理問題" in zh_copy["steps"][2]["title"]
    assert "查看結果與下載" in zh_copy["steps"][3]["title"]
    assert "猜測" in zh_copy["steps"][2]["body"]
    assert "示範" in zh_copy["footer"]

    en_copy = get_tutorial_copy("en")
    assert "first time" in en_copy["title"].lower()
    assert len(en_copy["steps"]) == 4
    assert "zero" in en_copy["steps"][2]["body"].lower()
    assert "synthetic" in en_copy["footer"].lower()


def test_dashboard_shows_four_kpi_cards() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "已計算排放量" in text
    assert "計算完成" in text
    assert "仍需處理" in text
    assert "資料來源" in text


def test_dashboard_shows_needs_attention() -> None:
    at = _run_app()
    assert "優先處理" in _all_text(at) or "目前無法計算" in _all_text(at)


def test_dashboard_shows_activity_overview() -> None:
    at = _run_app()
    assert "計算明細" in _all_text(at)


def test_dashboard_page_header_and_status_hierarchy() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "分析結果" in text
    assert "已計算排放量" in text
    assert "排放趨勢" in text
    assert "排放來源" in text
    assert "優先處理" in text
    assert "計算明細" in text


def test_dashboard_does_not_render_raw_html_or_svg() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "<svg" not in text
    assert "cel-hero-visual" not in text
    assert "<linearGradient" not in text
    assert '"$schema"' not in text
    assert "可計算、可追溯、可行動" not in text
    # Chart specs must not be dumped as beginner-facing markdown blobs.
    for item in at.markdown:
        body = str(getattr(item, "value", "") or getattr(item, "body", "") or "")
        stripped = body.strip()
        assert not stripped.startswith("<svg")
        assert not stripped.startswith('{"$schema"')
        assert not stripped.startswith("<script")


def test_dashboard_shows_chart_explanations() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "排放趨勢" in text
    assert "排放來源" in text
    assert "資料完整度" in text or "活動計算狀態" in text


def test_beginner_facing_plain_text_widgets_have_no_raw_markup() -> None:
    at = _run_app()
    for collection_name in ("caption", "text", "info", "warning", "success", "error"):
        collection = getattr(at, collection_name, None)
        if collection is None:
            continue
        for item in collection:
            value = str(getattr(item, "value", "") or getattr(item, "body", "") or "")
            stripped = value.lstrip()
            assert not stripped.startswith("<div")
            assert not stripped.startswith("<svg")
            assert not stripped.startswith("<style")
            assert not stripped.startswith("<script")


def test_dashboard_does_not_label_partial_as_total_company_emissions() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "Total company emissions" not in text
    assert "公司的總排放量" in text
    assert "不會被當成 0" in text


def test_dashboard_does_not_show_arbitrary_readiness_percentage() -> None:
    at = _run_app()
    text = _all_text(at).lower()
    assert "readiness score" not in text
    assert "readiness percentage" not in text
    assert "% ready" not in text


def test_dashboard_issue_cards_are_short_and_actionable() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "查看如何處理" in text or "查看資料" in text
    assert "Allowed use" not in text
    assert "prohibited_use" not in text


def test_activity_explorer_page_loads() -> None:
    at = _switch(_run_app(), "app_pages/activity_explorer.py")
    text = _all_text(at)
    assert "活動資料" in text
    assert "請先點選一筆活動" in text


def test_issues_actions_page_loads() -> None:
    at = _switch(_run_app(), "app_pages/issues_actions.py")
    text = _all_text(at)
    assert "待處理問題" in text
    assert "待辦清單" in text


def test_frameworks_page_loads() -> None:
    at = _switch(_run_app(), "app_pages/frameworks.py")
    text = _all_text(at)
    assert "準則分析" in text
    assert "公司碳盤查" in text
    assert "歐盟出口產品碳資料" in text
    assert "氣候資訊揭露準備" in text


def test_audit_export_page_loads() -> None:
    at = _switch(_run_app(), "app_pages/audit_export.py")
    text = _all_text(at)
    assert "稽核與匯出" in text
    assert "官方參考資料" in text
    assert "電力排放係數" in text
    labels = [str(button.label) for button in at.download_button]
    assert any(".zip" in label for label in labels)
    assert "Excel" in text


def test_frameworks_page_contains_separate_framework_views() -> None:
    at = _switch(_run_app(), "app_pages/frameworks.py")
    labels = [str(tab.label) for tab in at.tabs]
    assert "GHG Protocol" in labels
    assert "EU CBAM" in labels
    assert "IFRS S2" in labels


def test_cbam_page_content_contains_demo_assumption_warning() -> None:
    at = _switch(_run_app(), "app_pages/frameworks.py")
    text = _all_text(at)
    assert "CN 7318" in text
    assert "示範假設" in text


def test_ifrs_s2_content_contains_readiness_only_warning() -> None:
    at = _switch(_run_app(), "app_pages/frameworks.py")
    text = _all_text(at)
    assert "資料準備度" in text
    assert "合規" in text


def test_audit_page_contains_audit_bundle_download_control() -> None:
    at = _switch(_run_app(), "app_pages/audit_export.py")
    labels = [str(button.label) for button in at.download_button]
    assert any("zip" in label.lower() for label in labels)


def test_audit_raw_manifest_is_advanced_only() -> None:
    at = _switch(_run_app(), "app_pages/audit_export.py")
    text = _all_text(at)
    assert "進階技術資訊" in text
    assert "下載完整分析資料" in text


def test_application_does_not_display_raw_blocked_missing_conversion() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "blocked_missing_conversion" not in text
    assert (
        "缺少轉換" in text
        or "缺少熱值" in text
        or "目前無法計算" in text
        or "缺少已驗證" in text
    )


def test_no_page_produces_uncaught_streamlit_exception() -> None:
    at = _run_app()
    pages = [
        "app_pages/dashboard.py",
        "app_pages/data_intake.py",
        "app_pages/activity_explorer.py",
        "app_pages/issues_actions.py",
        "app_pages/frameworks.py",
        "app_pages/audit_export.py",
    ]
    for page in pages:
        at = _switch(at, page)
        assert not at.exception


def test_english_navigation_copy() -> None:
    at = _switch_language(_run_app(), "EN")
    text = _all_text(at)
    assert "Analysis results" in text
    assert (
        "Re-run analysis" in text
        or "Run demo analysis" in text
        or "Start analysis" in text
    )
    assert "Emissions trend" in text or "Calculation status" in text
