"""Stage 4.2G — immersive guided-tour copy, assets, and state semantics."""

from __future__ import annotations

import struct
from pathlib import Path

from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.tutorial import (
    FORBIDDEN_CUSTOMER_TERMS,
    STATE_TUTORIAL_COMPLETED,
    STATE_TUTORIAL_SESSION_DISMISSED,
    STATE_TUTORIAL_STEP,
    STATE_TUTORIAL_VISIBLE,
    begin_tutorial_view,
    complete_tutorial,
    current_tutorial_step,
    customer_copy_blob,
    dismiss_tutorial_for_session,
    ensure_tutorial_state,
    get_tutorial_copy,
    request_tutorial,
    set_tutorial_step,
    tour_should_open,
    tutorial_step_texts,
)
from carbon_ledger.ui.tutorial_manifest import (
    STEP_IDS,
    TOUR_STEP_COUNT,
    TOUR_STEPS,
    TOUR_VERSION,
    iter_tour_steps,
    missing_or_empty_assets,
    production_asset_paths,
    step_by_index,
    tour_step_visual,
)

ZH = "zh-TW"
EN = "en"
REPO = Path(__file__).resolve().parents[1]
EXPECTED_ZH = [
    "確認公司與目前營運據點",
    "使用公司既有的資料檔",
    "檢視分析結果與可下載資料",
]
EXPECTED_EN = [
    "Confirm the company and current operating locations",
    "Use the file the company already keeps",
    "Review the analysis and downloadable files",
]
FACT_KEYS = (
    "company_ubn",
    "company_name",
    "pipeline_result",
    "uploaded_table",
    "uploaded_file_name",
    "uploaded_file_hash",
    "include_ghg",
    "include_ifrs_s2",
)
NAV_PAGES = (
    "app_pages/data_intake.py",
    "app_pages/activity_explorer.py",
    "app_pages/issues_actions.py",
    "app_pages/evidence_data.py",
)
MIN_TOUR_ASSET_WIDTH = 640
MIN_TOUR_ASSET_HEIGHT = 240
MIN_STEP1_HEIGHT = 220
MAX_STEP1_HEIGHT = 480
MIN_STEP3_WIDTH = 700


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def test_tour_has_exactly_three_stable_steps() -> None:
    steps = iter_tour_steps()
    assert TOUR_STEP_COUNT == 3
    assert len(steps) == 3
    assert len(STEP_IDS) == 3
    assert tuple(step["id"] for step in steps) == STEP_IDS
    assert [step["index"] for step in steps] == [1, 2, 3]
    for index in range(1, 4):
        assert step_by_index(index)["id"] == STEP_IDS[index - 1]


def test_chinese_and_english_copy_are_complete() -> None:
    zh = get_tutorial_copy(ZH)
    en = get_tutorial_copy(EN)
    assert tutorial_step_texts(ZH) == EXPECTED_ZH
    assert tutorial_step_texts(EN) == EXPECTED_EN
    assert zh["subtitle"] == (
        "用 3 個步驟了解如何確認公司、上傳既有資料，並查看可追溯的結果與報告。"
    )
    assert en["subtitle"] == (
        "See how to confirm your company, upload existing data, "
        "and review traceable results and reports in three steps."
    )
    assert zh["helps"] == "需要說明時，點「？」查看與目前畫面相關的指引。"
    assert en["helps"] == 'Select “?” for guidance related to the current screen.'
    assert "不需要先懂碳盤查" not in zh["subtitle"]
    assert zh["start_label"] == "開始使用"
    assert en["start_label"] == "Start using the product"
    assert zh["later_label"] == "稍後再看"
    assert en["later_label"] == "Maybe later"
    assert t("tut.progress", ZH, current=2, total=3) == "第 2 步，共 3 步"
    assert t("tut.progress", EN, current=2, total=3) == "Step 2 of 3"
    expected = {
        ZH: {
            "why": [
                "法規要求、申報時程與資料範圍，都取決於正確的公司及實際營運據點。",
                "系統會讀取公司日常使用的 Excel 或 CSV，不必先改成指定格式。",
                "分析完成後，這裡是內部管理與申報準備的起點，不是另一個設定畫面。",
            ],
            "action": [
                "核對官方登記的公司資料，並確認政府找到的據點目前是否仍由公司營運。",
                "選擇公司目前保存的 Excel 或 CSV，交給系統處理。",
                "查看已計算的排放摘要，並依需要開啟證據或下載報告。",
            ],
            "next": [
                "系統會依已確認的公司與據點，整理適用要求、重要時程與仍待補充的資料。",
                (
                    "系統會先整理可安全辨識的欄位。你只需確認不確定項目，"
                    "並在分析前查看哪些資料會納入、暫緩或仍待補充。"
                ),
                "教學到此結束。進入產品後，可從結果頁繼續處理待確認項目或匯出資料。",
            ],
            "callout": [
                "核對公司與目前營運據點",
                "交給系統處理的是公司既有檔案",
                "分析後可立即查看的排放摘要",
            ],
        },
        EN: {
            "why": [
                (
                    "Regulatory requirements, reporting timelines, and data "
                    "scope depend on the correct company and the locations "
                    "it actually operates."
                ),
                (
                    "The product reads the Excel or CSV the company already "
                    "uses. It does not require a special template first."
                ),
                (
                    "After analysis, this is the starting point for internal "
                    "review and filing preparation, not another setup screen."
                ),
            ],
            "action": [
                (
                    "Verify the official company record and confirm whether "
                    "the locations found in government records are still "
                    "operated by the company."
                ),
                (
                    "Select the Excel or CSV the company currently keeps, "
                    "and provide it to the system."
                ),
                (
                    "Review the calculated emissions summary, then open "
                    "evidence or download a report as needed."
                ),
            ],
            "next": [
                (
                    "The system uses the confirmed company and locations to "
                    "organize applicable requirements, key dates, and "
                    "information still needed."
                ),
                (
                    "The system first organizes fields it can identify safely. "
                    "You only confirm uncertain items and review which data "
                    "will be included, held, or still needed before analysis."
                ),
                (
                    "This tour ends here. After you enter the product, "
                    "continue from the results page to resolve open items "
                    "or export files."
                ),
            ],
            "callout": [
                "Verify the company and current operating locations",
                "Provide the company's existing file",
                "The emissions summary available after analysis",
            ],
        },
    }
    for lang, copy in ((ZH, zh), (EN, en)):
        assert "tut." not in copy["title"]
        assert copy["glossary_hint"] == ""
        assert len(copy["steps"]) == 3
        for index, step in enumerate(copy["steps"]):
            assert step["title"].strip()
            assert step["why"] == expected[lang]["why"][index]
            assert step["action"] == expected[lang]["action"][index]
            assert step["next"] == expected[lang]["next"][index]
            assert step["alt"].strip()
            assert step["callouts"] == [expected[lang]["callout"][index]]
            assert "tut." not in step["title"]
            assert "tut." not in step["why"]
            assert "tut." not in step["alt"]


def test_production_assets_exist_and_are_non_empty() -> None:
    missing = missing_or_empty_assets()
    assert missing == (), f"missing or empty tutorial assets: {missing}"
    paths = production_asset_paths()
    assert len(paths) == 6
    for spec in TOUR_STEPS:
        assert spec["image"] == spec["images"]["zh-TW"]
        assert spec["images"]["en"].endswith(".en.png")
        assert spec["images"]["zh-TW"] != spec["images"]["en"]
        for filename in spec["images"].values():
            path = next(item for item in paths if item.name == filename)
            assert path.is_file()
            assert path.stat().st_size > 0
            assert "artifacts/e2e" not in str(path)
            assert "qa_" not in path.name
        assert spec["capture_version"] == TOUR_VERSION
        assert spec["language"] == ZH
        assert "capture_band" not in spec
        for highlight in spec["highlights"].values():
            assert 0 <= float(highlight["left"]) < 1
            assert 0 <= float(highlight["top"]) < 1
            assert 0 < float(highlight["width"]) <= 1
            assert 0 < float(highlight["height"]) <= 1
        assert len(spec["callouts"]) == 1


def test_tour_selects_language_matched_assets() -> None:
    for spec in TOUR_STEPS:
        zh = tour_step_visual(spec, ZH)
        en = tour_step_visual(spec, EN)
        assert zh["lang"] == "zh-TW"
        assert en["lang"] == "en"
        assert zh["image"] == spec["images"]["zh-TW"]
        assert en["image"] == spec["images"]["en"]
        assert zh["image"] != en["image"]
        assert zh["path"].name == zh["image"]
        assert en["path"].name == en["image"]
        assert zh["highlight"] == spec["highlights"]["zh-TW"]
        assert en["highlight"] == spec["highlights"]["en"]
        assert zh["path"].read_bytes() != en["path"].read_bytes()
    tutorial = (REPO / "src" / "carbon_ledger" / "ui" / "tutorial.py").read_text(
        encoding="utf-8"
    )
    assert "tour_step_visual" in tutorial
    assert "data-cel-tour-lang" in tutorial
    assert "data-cel-tour-image" in tutorial


def test_production_assets_have_uncropped_dimensions() -> None:
    sizes = {path.name: _png_size(path) for path in production_asset_paths()}
    for spec in TOUR_STEPS:
        callout = spec["callouts"][0]
        for lang, filename in spec["images"].items():
            width, height = sizes[filename]
            assert width >= MIN_TOUR_ASSET_WIDTH, (filename, width, height)
            min_height = (
                MIN_STEP1_HEIGHT
                if filename.startswith("step1_")
                else MIN_TOUR_ASSET_HEIGHT
            )
            assert height >= min_height, (filename, width, height)
            highlight = spec["highlights"][lang]
            assert 0 <= float(highlight["left"]) < 1
            assert 0 <= float(highlight["top"]) < 1
            assert float(highlight["left"]) + float(highlight["width"]) <= 1.001
            assert float(highlight["top"]) + float(highlight["height"]) <= 1.001
            assert 0 <= float(callout["left"]) <= 1
            assert 0 <= float(callout["top"]) <= 1
    width1, height1 = sizes["step1_company.png"]
    assert MIN_STEP1_HEIGHT <= height1 <= MAX_STEP1_HEIGHT, (width1, height1)
    en1 = sizes["step1_company.en.png"]
    assert MIN_STEP1_HEIGHT <= en1[1] <= MAX_STEP1_HEIGHT, en1
    width3, height3 = sizes["step3_results.png"]
    assert width3 >= MIN_STEP3_WIDTH, (width3, height3)
    assert width3 >= height3 * 0.9, (width3, height3)
    en3w, en3h = sizes["step3_results.en.png"]
    assert en3w >= MIN_STEP3_WIDTH, (en3w, en3h)
    assert en3w >= en3h * 0.9, (en3w, en3h)


def test_step_alt_text_matches_visible_crop() -> None:
    zh = get_tutorial_copy(ZH)
    en = get_tutorial_copy(EN)
    assert "已確認的公司名稱" in zh["steps"][0]["alt"]
    assert "台灣廠場確認題" in zh["steps"][0]["alt"]
    assert "兩個選擇" in zh["steps"][0]["alt"]
    assert "confirmed company name" in en["steps"][0]["alt"]
    assert "排放資料摘要" in zh["steps"][2]["alt"]
    assert "tCO₂e" in zh["steps"][2]["alt"]
    assert "證據與報表" in zh["steps"][2]["alt"]
    assert "tCO₂e" in en["steps"][2]["alt"]
    assert "evidence" in en["steps"][2]["alt"]


def test_customer_copy_avoids_engineering_terms() -> None:
    for lang in (ZH, EN):
        blob = customer_copy_blob(lang)
        assert "tut." not in blob
        for term in FORBIDDEN_CUSTOMER_TERMS:
            assert term not in blob, f"{term!r} leaked into {lang} tour copy"
        assert "canonical" not in blob.lower()
        assert "fingerprint" not in blob.lower()
        assert "obligation_id" not in blob
        assert "CASE C" not in blob
        assert "qa_" not in blob


def test_dead_workspace_nav_is_removed() -> None:
    module = REPO / "src" / "carbon_ledger" / "ui" / "evidence_workspace.py"
    assert not module.exists()
    for rel in NAV_PAGES:
        source = (REPO / rel).read_text(encoding="utf-8")
        assert "render_evidence_workspace_nav" not in source
        assert "evidence_workspace" not in source
        assert "TAB_INTAKE" not in source
        assert "TAB_ACTIVITY" not in source
        assert "TAB_ISSUES" not in source
        assert "TAB_RECORDS" not in source
    intake = (REPO / "app_pages" / "data_intake.py").read_text(encoding="utf-8")
    assert "ev.cta.view_activities" in intake
    assert "ev.cta.view_files" in intake
    dashboard = (REPO / "app_pages" / "dashboard.py").read_text(encoding="utf-8")
    assert "dash.cta.view_calc_basis" in dashboard
    assert "dash.cta.view_evidence" in dashboard
    assert "app_pages/activity_explorer.py" in dashboard
    assert "app_pages/evidence_data.py" in dashboard
    assert "app_pages/issues_actions.py" in dashboard
    assert (REPO / "app_pages" / "activity_explorer.py").is_file()
    assert (REPO / "app_pages" / "issues_actions.py").is_file()
    assert (REPO / "app_pages" / "evidence_data.py").is_file()
    assert (REPO / "app_pages" / "audit_export.py").is_file()


def test_opening_does_not_mark_completion() -> None:
    state: dict = {}
    ensure_tutorial_state(state)
    assert tour_should_open(state) is True
    begin_tutorial_view(state)
    assert state[STATE_TUTORIAL_VISIBLE] is True
    assert state[STATE_TUTORIAL_COMPLETED] is False
    assert state[STATE_TUTORIAL_SESSION_DISMISSED] is False
    assert tour_should_open(state) is True


def test_later_versus_completed_semantics() -> None:
    later: dict = {}
    begin_tutorial_view(later)
    dismiss_tutorial_for_session(later)
    assert later[STATE_TUTORIAL_COMPLETED] is False
    assert later[STATE_TUTORIAL_SESSION_DISMISSED] is True
    assert later[STATE_TUTORIAL_VISIBLE] is False
    assert tour_should_open(later) is False

    done: dict = {}
    begin_tutorial_view(done)
    set_tutorial_step(done, 3)
    complete_tutorial(done)
    assert done[STATE_TUTORIAL_COMPLETED] is True
    assert done[STATE_TUTORIAL_VISIBLE] is False
    assert tour_should_open(done) is False


def test_replay_starts_from_step_one() -> None:
    state: dict = {}
    begin_tutorial_view(state)
    set_tutorial_step(state, 3)
    complete_tutorial(state)
    request_tutorial(state)
    assert state[STATE_TUTORIAL_STEP] == 1
    assert tour_should_open(state) is True
    begin_tutorial_view(state, replay=True)
    assert current_tutorial_step(state) == 1
    assert state[STATE_TUTORIAL_COMPLETED] is True
    assert state[STATE_TUTORIAL_VISIBLE] is True


def test_rerun_preserves_current_step() -> None:
    state: dict = {}
    begin_tutorial_view(state)
    set_tutorial_step(state, 2)
    begin_tutorial_view(state, replay=False)
    assert current_tutorial_step(state) == 2
    assert state[STATE_TUTORIAL_VISIBLE] is True


def test_tutorial_navigation_does_not_mutate_facts() -> None:
    state: dict = {key: f"keep-{key}" for key in FACT_KEYS}
    state["intake_mapping_memory"] = {"kept": True}
    begin_tutorial_view(state)
    snapshot = {key: state[key] for key in FACT_KEYS}
    snapshot["intake_mapping_memory"] = dict(state["intake_mapping_memory"])
    set_tutorial_step(state, 3)
    set_tutorial_step(state, 2)
    request_tutorial(state)
    begin_tutorial_view(state, replay=True)
    dismiss_tutorial_for_session(state)
    for key in FACT_KEYS:
        assert state[key] == snapshot[key]
    assert state["intake_mapping_memory"] == snapshot["intake_mapping_memory"]


def test_tour_dialog_css_overlay_and_section_card() -> None:
    css = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "carbon_ledger"
        / "ui"
        / "visual_system.css"
    ).read_text(encoding="utf-8")
    tutorial = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "carbon_ledger"
        / "ui"
        / "tutorial.py"
    ).read_text(encoding="utf-8")
    tour_css = css.split("Stage 4.2G tour dialog only.", 1)[1].split(
        ".cel-notice-warn", 1
    )[0]
    overlay_rule = tour_css.split(
        'section[role="dialog"]:has(.cel-tour-root) {', 1
    )[0]
    assert "data-cel-tour-body" in tutorial
    assert "data-cel-tour-footer" in tutorial
    assert "section[role=\"dialog\"]:has(.cel-tour-root)" in tour_css
    assert "inset: 0 !important" in overlay_rule
    assert "width: 100vw !important" in overlay_rule
    assert "height: 100dvh !important" in overlay_rule
    assert "z-index: 1000000 !important" in overlay_rule
    assert "rgba(8, 26, 43, 0.62)" in overlay_rule
    assert "background: #fff !important" in tour_css
    assert "background: transparent" not in tour_css
    assert "data-cel-tour-body" in tour_css
    assert "data-cel-tour-footer" in tour_css
    assert "env(safe-area-inset-bottom" in tour_css
    assert overlay_rule.count("background: #fff") == 0


def test_tour_shot_uses_shrink_wrap_frame() -> None:
    css = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "carbon_ledger"
        / "ui"
        / "visual_system.css"
    ).read_text(encoding="utf-8")
    tutorial = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "carbon_ledger"
        / "ui"
        / "tutorial.py"
    ).read_text(encoding="utf-8")
    tour_css = css.split("Stage 4.2G tour dialog only.", 1)[1].split(
        "@media (max-width: 720px)", 1
    )[0]
    img_rule = tour_css.split(".cel-tour-shot img {", 1)[1].split("}", 1)[0]
    assert "cel-tour-shot-frame" in tutorial
    assert "<div class='cel-tour-shot-frame'>" in tutorial
    assert ".cel-tour-shot-frame" in tour_css
    assert "container-type: inline-size" in tour_css
    img_lines = [line.strip() for line in img_rule.splitlines() if line.strip()]
    assert "width: auto;" in img_lines
    assert "height: auto;" in img_lines
    assert "width: 100%;" not in img_lines
    assert "object-fit: contain;" not in img_lines
    assert "object-fit: contain" not in tour_css
    assert "max-height: min(48vh, calc(90vh - 22rem));" in img_lines
    mobile_css = css.split("@media (max-width: 720px)", 1)[1]
    mobile_img = mobile_css.split(".cel-tour-shot img {", 1)[1].split("}", 1)[0]
    assert "max-height: min(18vh, 148px)" in mobile_img


def test_tour_e2e_clicks_tutorial_controls_without_force() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "e2e"
        / "test_stage4_2g_tour.py"
    ).read_text(encoding="utf-8")
    click_fn = source.split("def _click_in_tour", 1)[1].split("\ndef ", 1)[0]
    assert "force=True" not in click_fn
    assert "button.first.click()" in click_fn
    assert "expect(button.first).to_be_enabled" in click_fn
    wait_fn = source.split("def _wait_hero_countup_stable", 1)[1].split(
        "def ", 1
    )[0]
    assert "data-cel-hero-done" not in wait_fn
    assert "textContent ===" not in wait_fn
    assert "data-cel-target" in wait_fn
    assert "data-cel-decimals" in wait_fn
    assert "section[role='dialog']" in source
    assert 'section[role="dialog"]:has(.cel-tour-root)' in source
    assert "overlayDark" in source
    assert "shotVisiblePx" in source


def test_stage4_2g_desktop_first_defers_mobile_tour() -> None:
    e2e = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "e2e"
        / "test_stage4_2g_tour.py"
    ).read_text(encoding="utf-8")
    review = e2e.split("REVIEW_SHOTS = (", 1)[1].split(")", 1)[0]
    assert "qa_42g_tour_cover_desktop" in review
    assert "qa_42g_tour_english" in review
    assert "qa_42g_tour_en_step1_company" in review
    assert "qa_42g_tour_step1_1366x768" in review
    assert "qa_42g_tour_replay" in review
    assert "qa_42g_intake_upload_desktop" in review
    assert "qa_42g_tour_mobile" not in review
    mobile_head = e2e.split("def test_fresh_mobile_tour_layout", 1)[0][-500:]
    assert "@pytest.mark.skip" in mobile_head
    assert "desktop-first" in mobile_head
    ux = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "customer_product_ux_rules.md"
    ).read_text(encoding="utf-8")
    tutorial = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "carbon_ledger"
        / "ui"
        / "tutorial.py"
    ).read_text(encoding="utf-8")
    assert "deferred known limitation" in ux
    assert "Do not claim that the current" in ux
    assert "three-step" in tutorial
    assert "desktop-first" in tutorial
