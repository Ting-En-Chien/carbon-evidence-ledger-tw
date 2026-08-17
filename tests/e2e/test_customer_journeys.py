"""Stage 3B.3a — browser E2E customer journeys (Playwright)."""

from __future__ import annotations

import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.intake import (
    ColumnMapping,
    IntakeMetadata,
    build_and_validate_intake,
    default_value_maps,
    parse_uploaded_table,
    suggest_activity_type,
    suggest_column_mapping,
    suggest_unit,
)
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.ui.view_models import calculated_emissions_summary

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    APPLICABILITY_NAV,
    ARTIFACTS,
    STUB_ALIGNED_UBN,
    STUB_SPARSE_UBN,
    assert_no_app_errors,
    assert_no_raw_html_leak,
    choose_radio,
    choose_selectbox,
    click_button,
    fill_streamlit_date,
    lookup_stub_company,
    open_fresh_app,
    parse_metric_number,
    safe_scroll_into_view,
    save_step_screenshot,
    set_money_unknown,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e


def test_simple_first_run_tutorial(page) -> None:
    base = page._cel_base_url  # type: ignore[attr-defined]
    page.goto(base, wait_until="domcontentloaded")
    wait_streamlit_idle(page)
    page.wait_for_selector("text=Carbon Evidence Ledger", timeout=30_000)
    dialog = page.get_by_role("dialog")
    dialog.first.wait_for(state="visible", timeout=20_000)
    body = visible_text(page)
    assert "歡迎使用 Carbon Evidence Ledger" in body
    assert "填公司資料" in body
    assert "上傳電力、燃料等營運資料" in body
    assert "查看分析結果" in body
    assert "治理、策略" not in body
    assert "GHG Protocol" not in body
    save_step_screenshot(page, "qa_simple_tutorial")
    page.get_by_role("button", name=re.compile(r"開始使用|Get started")).first.click(
        force=True
    )
    wait_streamlit_idle(page)
    if dialog.count():
        dialog.first.wait_for(state="hidden", timeout=15_000)
    assert_no_app_errors(page)


def _goto_applicability_step1(page) -> None:
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    page.wait_for_timeout(600)
    body = visible_text(page)
    assert "統一編號" in body or "確認公司" in body


def _fill_listed_company(page, company_name: str, *, capital_yi: str | None) -> None:
    del company_name
    if capital_yi is None:
        lookup_stub_company(page, STUB_SPARSE_UBN)
        click_button(page, "繼續")
        choose_selectbox(page, "公司是否上市／上櫃？", "上市（TWSE）")
        set_money_unknown(page, index=0, unknown=True)
        body = visible_text(page)
        assert "0.00" not in body
        assert "NT$0" not in body
    else:
        lookup_stub_company(page, STUB_ALIGNED_UBN)
        click_button(page, "繼續")
        body = visible_text(page)
        assert "NT$12,000,000,000" in body or "實收資本額" in body
        assert not re.search(r"淨值[^\n]{0,24}0\.00", body)
    save_step_screenshot(page, "qa_applicability_step2")
    click_button(page, "繼續")


def test_journey1_new_customer_applicability_results(page) -> None:
    open_fresh_app(page)
    text = visible_text(page)
    assert "示範公司" not in text
    assert "automated_sources_expected" not in text
    assert "MONITORING_PARTIAL" not in text
    assert "開始公司設定" in text
    save_step_screenshot(page, "qa_new_customer_home")

    click_button(page, "開始公司設定")
    _fill_listed_company(page, "test", capital_yi="120")

    save_step_screenshot(page, "qa_applicability_step3")
    text3 = visible_text(page)
    assert_no_raw_html_leak(text3)
    assert "高雄一廠" in text3 or "據點" in text3 or "廠場" in text3
    empty_cards = page.locator(".cel-card-primary")
    for index in range(empty_cards.count()):
        card = empty_cards.nth(index)
        if not card.is_visible():
            continue
        content = (card.inner_text() or "").strip()
        box = card.bounding_box()
        if box and box["height"] > 48:
            assert content, "empty white card surface rendered without content"
    gap = page.evaluate(
        """() => {
          const stepper = document.querySelector('.cel-stepper');
          const field = document.querySelector(
            '[data-testid="stButton"], [data-testid="stCheckbox"], p'
          );
          if (!stepper || !field) return null;
          return field.getBoundingClientRect().top
            - stepper.getBoundingClientRect().bottom;
        }"""
    )
    assert gap is not None, "stepper/fields missing on step 3"
    assert gap < 80, (
        f"unexplained empty surface between stepper and fields: gap={gap}px"
    )

    click_button(page, "繼續")
    page.wait_for_timeout(1000)
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_applicability_step5")
    text5 = visible_text(page)
    assert_no_raw_html_leak(text5)
    assert "適用" in text5
    assert "2026" in text5
    assert "2027" in text5

    timeline = page.locator(".cel-ifrs-timeline").first
    timeline.wait_for(state="visible", timeout=15_000)
    assert timeline.is_visible()
    markers = page.locator(
        '[data-cel-timeline-scope="desktop"] [data-cel-timeline-marker]'
    )
    assert markers.count() == 6
    visible_markers = 0
    for index in range(markers.count()):
        node = markers.nth(index)
        if not node.is_visible():
            continue
        visible_markers += 1
        box = node.bounding_box()
        assert box is not None
        assert box["width"] > 0 and box["height"] > 0
    assert visible_markers == 6
    timeline_text = timeline.inner_text()
    assert "2026 年度開始適用" in timeline_text
    assert "2027 年首次申報" in timeline_text
    periods = page.locator(
        '[data-cel-timeline-scope="desktop"] .cel-timeline-period'
    )
    actions = page.locator(
        '[data-cel-timeline-scope="desktop"] .cel-timeline-action'
    )
    assert periods.count() == 6
    assert actions.count() == 6
    for index in range(6):
        for loc in (periods.nth(index), actions.nth(index)):
            assert loc.is_visible()
            box = loc.bounding_box()
            assert box is not None, f"timeline label missing box index={index}"
            assert box["width"] >= 24, (
                f"timeline label width too narrow (vertical stack): {box}"
            )
            assert box["height"] <= 96, (
                f"timeline label appears vertically corrupted: {box}"
            )

    overflow = page.evaluate(
        """() => {
          const main = document.querySelector('section.main') || document.body;
          const timeline = document.querySelector('.cel-ifrs-timeline');
          const mainOk = main.scrollWidth <= main.clientWidth + 2;
          const timelineOk = !timeline || (
            timeline.scrollWidth <= timeline.clientWidth + 2
          );
          return mainOk && timelineOk;
        }"""
    )
    assert overflow
    assert_no_app_errors(page)


def test_journey2_unknown_financial_data(page) -> None:
    _goto_applicability_step1(page)
    _fill_listed_company(page, "unknown-finance-co", capital_yi=None)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    text = visible_text(page)
    assert_no_raw_html_leak(text)
    assert "NT$0" not in text
    assert "0.00 億" not in text
    # Unknown money → needs information, never fabricated zero NOT_APPLICABLE.
    assert "還需要一些資料" in text or "需要" in text
    assert_no_app_errors(page)


def test_journey3_explicit_demo(page) -> None:
    open_fresh_app(page)
    click_button(page, "使用示範資料")
    wait_streamlit_idle(page)
    page.wait_for_timeout(800)
    text = visible_text(page)
    assert "示範資料" in text or "Demo data" in text
    assert "automated_sources_expected" not in text
    assert_no_raw_html_leak(text)
    assert "tCO" in text or "排放" in text
    hero = page.locator(".cel-kpi-grid-hero, .cel-kpi-grid")
    assert hero.count() >= 1
    assert_no_app_errors(page)


def test_journey4_evidence_wizard_one_active_step(page) -> None:
    open_fresh_app(page)
    nav = page.get_by_role("link", name=re.compile(r"證據|Evidence"))
    if nav.count() == 0:
        nav = page.get_by_text(re.compile(r"證據與資料|Evidence"))
    nav.first.click()
    wait_streamlit_idle(page)
    text = visible_text(page)
    assert "上傳" in text or "Upload" in text
    assert (
        page.locator('input[type="file"]').count() >= 1
        or page.get_by_text(re.compile(r"Drag and drop|Browse|上傳")).count() >= 1
    )
    page.get_by_text("需要準備的資料").first.wait_for(state="visible", timeout=15_000)
    page.set_viewport_size({"width": 1440, "height": 1800})
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_data_upload")
    text = visible_text(page)
    assert text.count("開始分析") <= 2
    assert_no_raw_html_leak(text)
    # Stage 3B.3c — Data Upload customer hygiene
    assert "activity_type" not in text
    assert "activity_value" not in text
    assert "系統內部欄位名稱" not in text
    assert "200MB" not in text and "200 MB" not in text
    assert "10 MB" in text or "10MB" in text
    assert "需要準備的資料" in text
    assert "50000" not in text
    assert "2024-01-01" not in text
    downloads = page.get_by_role(
        "button", name=re.compile(r"下載資料範本|Download data template")
    )
    assert downloads.count() >= 1
    example_dl = page.get_by_role(
        "button", name=re.compile(r"下載範例檔|example file")
    )
    assert example_dl.count() == 0
    assert_no_app_errors(page)


def test_journey6_information_hygiene(page) -> None:
    """Customer information hygiene smoke (extends existing E2E gate)."""
    open_fresh_app(page)
    home = visible_text(page)
    assert "Synthetic demonstration" not in home
    assert "MONITORING_PARTIAL" not in home
    assert "仍顯示示範分析結果" not in home
    save_step_screenshot(page, "qa_hygiene_customer_home")

    # Six empty customer pages stay clean.
    for label, shot in (
        (APPLICABILITY_NAV, "qa_hygiene_applicability"),
        (r"IFRS", "qa_hygiene_ifrs"),
        (r"台灣|Taiwan", "qa_hygiene_taiwan"),
        (r"證據與資料|Evidence", "qa_hygiene_evidence"),
        (r"報表|Reporting|Export|匯出", "qa_hygiene_reporting"),
    ):
        link = page.get_by_role("link", name=re.compile(label))
        if link.count() == 0:
            link = page.get_by_text(re.compile(label))
        link.first.click()
        wait_streamlit_idle(page)
        text = visible_text(page)
        assert "Synthetic demonstration" not in text
        assert "MONITORING_PARTIAL" not in text
        assert "automated_sources_expected" not in text
        assert "示範公司" not in text
        assert_no_raw_html_leak(text)
        save_step_screenshot(page, shot)

    # Applicability initial setup: no SASB field.
    page.get_by_role("link", name=re.compile(APPLICABILITY_NAV)).first.click()
    wait_streamlit_idle(page)
    setup = page.get_by_role("button", name=re.compile(r"開始公司設定"))
    if setup.count():
        setup.first.click(force=True)
        wait_streamlit_idle(page)
    if "統一編號" in visible_text(page) or "確認公司" in visible_text(page):
        lookup_stub_company(page, STUB_SPARSE_UBN)
        click_button(page, "繼續")
        if "公司是否上市／上櫃" in visible_text(page):
            choose_selectbox(page, "公司是否上市／上櫃？", "上市（TWSE）")
            set_money_unknown(page, index=0, unknown=True)
        click_button(page, "繼續")
        wait_streamlit_idle(page)
        step3 = visible_text(page)
        assert "SASB" not in step3
        save_step_screenshot(page, "qa_hygiene_applicability_step3")

    # Demo path: activity / issues / evidence / reporting hygiene.
    open_fresh_app(page)
    click_button(page, "使用示範資料")
    wait_streamlit_idle(page)
    page.wait_for_timeout(800)
    save_step_screenshot(page, "qa_hygiene_demo_dashboard")

    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    # Prefer activity explorer sub-nav if present.
    act = page.get_by_text(re.compile(r"活動|Activity"))
    if act.count():
        act.first.click()
        wait_streamlit_idle(page)
    act_text = visible_text(page)
    assert "factor_id" not in act_text
    save_step_screenshot(page, "qa_hygiene_activity_default")
    audit = page.locator("summary, [data-testid='stExpander']").filter(
        has_text=re.compile(r"稽核追溯資訊|Audit trace")
    )
    if audit.count() == 0:
        audit = page.get_by_text(re.compile(r"稽核追溯資訊|Audit trace"))
    if audit.count():
        audit.first.click(force=True)
        wait_streamlit_idle(page)
        page.wait_for_timeout(400)
    save_step_screenshot(page, "qa_hygiene_activity_audit")

    issues = page.get_by_text(re.compile(r"問題|Issues|Actions"))
    if issues.count():
        issues.first.click()
        wait_streamlit_idle(page)
        iss_text = visible_text(page)
        assert "record_id:" not in iss_text
        save_step_screenshot(page, "qa_hygiene_issues")

    records = page.get_by_text(re.compile(r"證據紀錄|Evidence records|紀錄"))
    if records.count():
        records.first.click()
        wait_streamlit_idle(page)
        rec_text = visible_text(page)
        assert "SHA-256" not in rec_text
        assert "Evidence hash" not in rec_text
        save_step_screenshot(page, "qa_hygiene_evidence_records")

    page.get_by_role("link", name=re.compile(r"報表|Reporting|匯出")).first.click()
    wait_streamlit_idle(page)
    reporting = visible_text(page)
    assert "一般分析不會" not in reporting
    # Run ID not in default business groups (only advanced expander).
    assert "stage3b3" not in reporting
    save_step_screenshot(page, "qa_hygiene_reporting_customer")
    adv = page.locator("summary, [data-testid='stExpander']").filter(
        has_text=re.compile(r"稽核追溯資訊|Audit trace|技術識別")
    )
    if adv.count() == 0:
        adv = page.get_by_text(re.compile(r"稽核追溯資訊|Audit trace|技術識別"))
    if adv.count():
        adv.first.click(force=True)
        wait_streamlit_idle(page)
        page.wait_for_timeout(300)
    save_step_screenshot(page, "qa_hygiene_reporting_advanced")
    assert_no_app_errors(page)


def test_journey5_analysis_loading_and_reveal(page) -> None:
    open_fresh_app(page)
    click_button(page, "使用示範資料")
    wait_streamlit_idle(page)
    page.wait_for_timeout(800)
    rerun = page.get_by_role("button", name=re.compile(r"重新分析|Re-run"))
    if rerun.count():
        rerun.first.click(force=True)
        page.wait_for_timeout(150)
        mid = visible_text(page)
        assert "正在分析" in mid or "分析" in mid or "讀取" in mid or "排放" in mid
        wait_streamlit_idle(page)
        page.wait_for_timeout(600)
    text = visible_text(page)
    assert "排放" in text or "tCO" in text
    assert_no_raw_html_leak(text)
    assert_no_app_errors(page)
    save_step_screenshot(page, "qa_demo_analysis_result")
    assert ARTIFACTS.exists()


def test_journey7_terminology_and_reporting_screens(page) -> None:
    """Stage 3B.3d screenshots and customer-language smoke."""
    open_fresh_app(page)
    click_button(page, "使用示範資料")
    wait_streamlit_idle(page)
    page.wait_for_timeout(800)

    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    act = page.get_by_text(re.compile(r"^活動資料$|Activity data"))
    if act.count() == 0:
        act = page.get_by_text(re.compile(r"活動資料|Activity"))
    if act.count():
        act.first.click()
        wait_streamlit_idle(page)
    act_text = visible_text(page)
    assert "grid_electricity" not in act_text
    assert "stationary_combustion" not in act_text
    page.set_viewport_size({"width": 1440, "height": 1800})
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_3d_activity")

    page.get_by_role("link", name=re.compile(r"IFRS")).first.click()
    wait_streamlit_idle(page)
    ifrs_text = visible_text(page)
    assert "氣候指標資料準備度" in ifrs_text or "Climate Metrics" in ifrs_text
    assert "不代表" in ifrs_text or "does not represent" in ifrs_text.lower()
    page.set_viewport_size({"width": 1440, "height": 2400})
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_3d_ifrs")

    page.get_by_role("link", name=re.compile(r"報表|Reporting|匯出")).first.click()
    wait_streamlit_idle(page)
    page.get_by_text(re.compile(r"稽核包|Audit package")).first.wait_for(
        state="visible", timeout=15_000
    )
    reporting = visible_text(page)
    assert "管理摘要" in reporting or "Management summary" in reporting
    assert "稽核包" in reporting or "Audit package" in reporting
    assert "尚未建立" in reporting or "not available yet" in reporting.lower()
    zip_btn = page.get_by_text(re.compile(r"下載稽核包|Download audit package|\.zip"))
    assert zip_btn.count() >= 1
    page.set_viewport_size({"width": 1440, "height": 2400})
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_3d_reporting")

    # Mapping / validation / review via a small company CSV.
    csv_path = ARTIFACTS / "qa_3d_upload.csv"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,100,kWh,2025-01-01,2025-01-31,高雄廠\n",
        encoding="utf-8",
    )
    open_fresh_app(page)
    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    file_input = page.locator('input[type="file"]')
    if file_input.count():
        file_input.first.set_input_files(str(csv_path))
        wait_streamlit_idle(page)
        page.wait_for_timeout(600)
        cont = page.get_by_role("button", name=re.compile(r"^繼續$|^Continue$"))
        if cont.count():
            cont.first.click(force=True)
            wait_streamlit_idle(page)
        fix = page.get_by_role(
            "button", name=re.compile(r"有地方不對|Something is wrong")
        )
        if fix.count():
            fix.first.click(force=True)
            wait_streamlit_idle(page)
        map_text = visible_text(page)
        assert "grid_electricity" not in map_text
        assert "場址 ID" not in map_text
        page.set_viewport_size({"width": 1440, "height": 2000})
        wait_streamlit_idle(page)
        save_step_screenshot(page, "qa_3d_mapping")
        date_input = page.locator('[data-testid="stDateInput"] input')
        if date_input.count():
            date_input.first.fill("2025-01-31")
            wait_streamlit_idle(page)
        validate = page.get_by_role(
            "button", name=re.compile(r"資料格式檢查|Check data format")
        )
        if validate.count():
            validate.first.click(force=True)
            wait_streamlit_idle(page)
            page.wait_for_timeout(500)
            val_text = visible_text(page)
            assert "activity_type" not in val_text
            assert "site_id" not in val_text
            save_step_screenshot(page, "qa_3d_validation")
            nxt = page.get_by_role("button", name=re.compile(r"下一步|Next"))
            if nxt.count():
                nxt.first.click(force=True)
                wait_streamlit_idle(page)
                review = visible_text(page)
                assert "site_id" not in review
                assert "site_main" not in review
                save_step_screenshot(page, "qa_3d_review")
    assert_no_app_errors(page)


def test_journey8_stage4_2025_fixture_no_fake_zero(page) -> None:
    """Upload a 2025 fixture; blocked fuels must not display as zero."""
    csv_path = ARTIFACTS / "qa_stage4_2025.csv"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,1000,kWh,2025-03-01,2025-03-31,高雄廠\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
        "柴油,1200,L,2025-06-01,2025-06-30,高雄廠\n",
        encoding="utf-8",
    )
    open_fresh_app(page)
    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    file_input = page.locator('input[type="file"]')
    if file_input.count() == 0:
        save_step_screenshot(page, "qa_stage4_2025_upload")
        return
    file_input.first.set_input_files(str(csv_path))
    wait_streamlit_idle(page)
    page.wait_for_timeout(600)
    for label in (
        r"^繼續$|^Continue$",
        r"資料格式檢查|Check data format",
        r"下一步|Next",
        r"開始分析|Start analysis",
    ):
        btn = page.get_by_role("button", name=re.compile(label))
        if btn.count():
            btn.first.click(force=True)
            wait_streamlit_idle(page)
            page.wait_for_timeout(400)
    text = visible_text(page)
    assert_no_raw_html_leak(text)
    assert "0.0 tCO₂e" not in text
    save_step_screenshot(page, "qa_stage4_2025_upload")
    assert_no_app_errors(page)


def _stage41_csv(*, ng_cell: str) -> str:
    return (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
        f"{ng_cell},8000,m3,2025-01-01,2025-01-31,高雄廠\n"
        "柴油,1200,L,2025-01-01,2025-01-31,高雄廠\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    )


def _walk_stage41_intake(page, csv_path: Path, *, ng_choice: str) -> None:
    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    page.wait_for_timeout(800)
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(csv_path))
    wait_streamlit_idle(page, timeout=40)
    page.wait_for_timeout(700)
    cont = page.get_by_role("button", name=re.compile(r"^繼續$|^Continue$"))
    assert cont.count() >= 1
    cont.first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    accept = page.get_by_role("button", name=re.compile(r"正確，繼續|Looks right"))
    if accept.count():
        accept.first.click(force=True)
        wait_streamlit_idle(page, timeout=40)
    ng_help = page.get_by_text("NG1 與 NG2 的官方年度熱值", exact=False)
    if ng_help.count() == 0:
        fix = page.get_by_role(
            "button", name=re.compile(r"有地方不對|Something is wrong")
        )
        if fix.count():
            fix.first.click(force=True)
            wait_streamlit_idle(page, timeout=40)
    ng_help.first.wait_for(state="visible", timeout=20_000)
    ng_help.first.scroll_into_view_if_needed()
    choose_radio(page, ng_choice)
    choose_radio(page, "公司車輛／公司控制的移動燃燒")
    choose_radio(page, "企業／廠場盤查")
    fill_streamlit_date(page, "文件日期", "2025-01-31")
    page.get_by_text("請確認文件日期", exact=False).first.wait_for(
        state="hidden", timeout=15_000
    )
    save_step_screenshot(page, "qa_stage41_mapping_ng")
    validate = page.get_by_role(
        "button", name=re.compile(r"資料格式檢查|Check data format")
    )
    assert validate.count() >= 1
    validate.first.scroll_into_view_if_needed()
    validate.first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    nxt = page.get_by_role("button", name=re.compile(r"下一步|Next"))
    nxt.first.wait_for(state="visible", timeout=20_000)
    nxt.first.click(force=True)
    wait_streamlit_idle(page)
    page.get_by_text("可開始分析", exact=False).first.wait_for(
        state="visible", timeout=20_000
    )
    review = visible_text(page)
    assert "可開始分析" in review
    assert "仍需確認" in review
    assert "已知不支援" in review
    assert "grid_electricity" not in review
    save_step_screenshot(page, "qa_stage41_review")
    start = page.get_by_role(
        "button", name=re.compile(r"開始分析|Start analysis")
    )
    assert start.count() >= 1
    start.first.click(force=True)
    dialog = page.get_by_role("dialog")
    try:
        dialog.first.wait_for(state="visible", timeout=15_000)
        page.get_by_text(
            re.compile(r"正在分析你的資料|讀取資料|分析完成"),
            exact=False,
        ).first.wait_for(state="visible", timeout=10_000)
        save_step_screenshot(page, "qa_stage41a_progress_modal")
        save_step_screenshot(page, "qa_stage41_progress")
    except Exception:  # noqa: BLE001 - dialog may close before the wait if pipeline is fast
        save_step_screenshot(page, "qa_stage41_progress")
    wait_streamlit_idle(page, timeout=120)
    page.get_by_text("排放資料摘要", exact=False).first.wait_for(
        state="visible", timeout=60_000
    )
    if dialog.count():
        dialog.first.wait_for(state="hidden", timeout=30_000)
    page.wait_for_timeout(800)


def _backend_total_for_csv(csv_path: Path, *, ng_subtype: str) -> float:
    table = parse_uploaded_table(
        file_name=csv_path.name,
        data=csv_path.read_bytes(),
    )
    suggestions = suggest_column_mapping(list(table.columns))
    activity_map, unit_map = default_value_maps(
        table,
        ColumnMapping(
            activity_type_column=suggestions["activity_type"],
            activity_value_column=suggestions["activity_value"],
            unit_column=suggestions["unit"],
        ),
    )
    activity_map = {
        key: value or suggest_activity_type(key)
        for key, value in activity_map.items()
    }
    unit_map = {key: value or suggest_unit(key) for key, value in unit_map.items()}
    mapping = ColumnMapping(
        activity_type_column=suggestions["activity_type"],
        activity_value_column=suggestions["activity_value"],
        unit_column=suggestions["unit"],
        site_column=suggestions.get("site_id") or "",
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
        natural_gas_subtype=ng_subtype,
        diesel_context="company_vehicle",
        electricity_context="enterprise",
    )
    intake = build_and_validate_intake(
        table,
        mapping,
        IntakeMetadata(
            source_name=csv_path.name,
            site_id="高雄廠",
            document_date=date(2025, 1, 31),
            data_quality_tier="unknown",
            intake_run_id="e2e_stage41",
            ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
        ),
    )
    result = run_uploaded_pipeline(
        Path(__file__).resolve().parents[2],
        run_id=f"e2e_stage41_{ng_subtype.lower()}",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
        include_ifrs_s2=True,
    )
    return float(calculated_emissions_summary(result)["calculated_tco2e"] or 0)


def test_journey9_stage41_customer_calculation(page) -> None:
    csv_path = ARTIFACTS / "qa_stage41_ng1.csv"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(_stage41_csv(ng_cell="天然氣"), encoding="utf-8")
    open_fresh_app(page)
    _walk_stage41_intake(page, csv_path, ng_choice="NG1")
    body = visible_text(page)
    assert "分析完成" in body or "目前已計算排放量" in body
    hero = page.locator("[data-cel-hero-emissions='1']")
    assert hero.count() >= 1
    hero.first.wait_for(state="visible", timeout=30_000)
    safe_scroll_into_view(hero.first)
    page.wait_for_timeout(300)
    save_step_screenshot(page, "qa_stage41_complete")
    displayed = float(
        page.locator("[data-cel-hero-emissions='1']").first.get_attribute(
            "data-cel-target"
        )
        or "nan"
    )
    expected = _backend_total_for_csv(csv_path, ng_subtype="NG1")
    assert displayed == pytest.approx(expected)
    emissions_box = page.get_by_text("排放資料摘要", exact=False).first.bounding_box()
    next_box = page.get_by_text("下一步", exact=False).first.bounding_box()
    assert emissions_box is not None
    assert next_box is not None
    assert emissions_box["y"] < next_box["y"]
    save_step_screenshot(page, "qa_stage41a_result_top")
    save_step_screenshot(page, "qa_simple_result_top")
    assert "Scope 1" in body
    assert "Scope 2" in body
    assert "尚未計算" in body or "尚未支援" in body
    assert "直接排放" in body
    assert "下一步" in body or "仍需處理" in body
    detail = page.get_by_text("排放明細", exact=False).first
    safe_scroll_into_view(detail)
    page.wait_for_timeout(200)
    save_step_screenshot(page, "qa_simple_result_detail")
    save_step_screenshot(page, "qa_stage41_dashboard_kpi")
    scope = page.get_by_text("Scope 1", exact=False).first
    if scope.count():
        safe_scroll_into_view(scope)
        page.wait_for_timeout(200)
    save_step_screenshot(page, "qa_stage41_scope")
    save_step_screenshot(page, "qa_stage41a_result_scope")
    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    activity_tab = page.get_by_text("活動資料", exact=True)
    activity_tab.first.wait_for(state="visible", timeout=15_000)
    activity_tab.first.click(force=True)
    wait_streamlit_idle(page)
    expander = page.get_by_text("查看計算依據")
    expander.first.wait_for(state="visible", timeout=15_000)
    expander.first.click()
    wait_streamlit_idle(page)
    basis = visible_text(page)
    assert "原始用量" in basis or "年度低位熱值" in basis or "計算" in basis
    save_step_screenshot(page, "qa_stage41_calc_basis")
    assert_no_app_errors(page)


def test_journey9b_stage41_ng2_result_differs(page) -> None:
    csv_path = ARTIFACTS / "qa_stage41_ng2.csv"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(_stage41_csv(ng_cell="天然氣"), encoding="utf-8")
    open_fresh_app(page)
    _walk_stage41_intake(page, csv_path, ng_choice="NG2")
    hero = page.locator("[data-cel-hero-emissions='1']")
    assert hero.count() >= 1
    ng2_value = float(hero.first.get_attribute("data-cel-target") or "nan")
    ng1_backend = _backend_total_for_csv(csv_path, ng_subtype="NG1")
    ng2_backend = _backend_total_for_csv(csv_path, ng_subtype="NG2")
    assert ng1_backend != ng2_backend
    assert ng2_value == pytest.approx(ng2_backend)
    assert_no_app_errors(page)


def test_journey10_product_ux_screenshots(page) -> None:
    """Stage 4.1c customer-product screenshots after analysis."""
    open_fresh_app(page)
    click_button(page, "使用示範資料")
    wait_streamlit_idle(page)
    page.wait_for_timeout(800)
    page.get_by_text("排放資料摘要", exact=False).first.wait_for(
        state="visible", timeout=30_000
    )
    page.set_viewport_size({"width": 1440, "height": 1800})
    home = visible_text(page)
    assert "目前已計算排放量" in home
    assert "Scope 1" in home
    assert "直接排放" in home
    assert "下一步" in home
    save_step_screenshot(page, "qa_product_home_post_analysis")
    detail = page.get_by_text("排放明細", exact=False).first
    safe_scroll_into_view(detail)
    page.wait_for_timeout(200)
    save_step_screenshot(page, "qa_product_result_detail")

    page.get_by_role("link", name=re.compile(APPLICABILITY_NAV)).first.click()
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_product_applicability")

    page.get_by_role("link", name=re.compile(r"IFRS")).first.click()
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_product_ifrs")

    page.get_by_role("link", name=re.compile(r"台灣|Taiwan")).first.click()
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_product_taiwan")

    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_product_evidence")

    page.get_by_role("link", name=re.compile(r"報表|Reporting|匯出")).first.click()
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_product_reporting")
    assert_no_app_errors(page)


def test_journey11_visible_countup_from_zero(page) -> None:
    """Hero / Scope / counts must visibly run 0 → intermediate → backend final."""
    page.emulate_media(reduced_motion="no-preference")
    csv_path = ARTIFACTS / "qa_stage41_ng1.csv"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(_stage41_csv(ng_cell="天然氣"), encoding="utf-8")
    open_fresh_app(page)
    _walk_stage41_intake(page, csv_path, ng_choice="NG1")
    expected = _backend_total_for_csv(csv_path, ng_subtype="NG1")
    hero = page.locator("[data-cel-hero-emissions='1']").first
    hero.wait_for(state="visible", timeout=30_000)
    assert float(hero.get_attribute("data-cel-target") or "nan") == pytest.approx(
        expected
    )

    rerun = page.get_by_role("button", name=re.compile(r"重新分析|Re-run"))
    assert rerun.count() >= 1
    rerun.first.click(force=True)
    dialog = page.get_by_role("dialog")
    dialog.first.wait_for(state="visible", timeout=15_000)

    def _near_zero(value: float, final: float) -> bool:
        return value <= max(0.08 * abs(final), 1.0)

    def _metric_text(loc) -> str:
        return str(loc.evaluate("el => el.textContent || ''"))

    def _dialog_hidden() -> bool:
        return dialog.count() == 0 or not dialog.first.is_visible()

    hero_loc = page.locator("[data-cel-hero-emissions='1']")
    target = float("nan")
    hero = None
    hero_start = float("nan")
    last_snaps: list = []
    deadline = time.time() + 30.0
    while time.time() <= deadline:
        if not _dialog_hidden():
            page.wait_for_timeout(20)
            continue
        if hero_loc.count() == 0:
            page.wait_for_timeout(20)
            continue
        snapshots = hero_loc.evaluate_all(
            """els => els.map(el => ({
              play: el.getAttribute('data-cel-hero-play'),
              text: el.textContent || '',
              target: el.getAttribute('data-cel-target'),
              done: el.getAttribute('data-cel-hero-done'),
            }))"""
        )
        last_snaps = snapshots
        for index, snap in enumerate(snapshots):
            node_target = float(snap.get("target") or "nan")
            node_start = parse_metric_number(str(snap.get("text") or ""))
            if snap.get("play") == "1" and _near_zero(node_start, node_target):
                hero = hero_loc.nth(index)
                target = node_target
                hero_start = node_start
                break
        if hero is not None:
            break
        page.wait_for_timeout(20)
    assert hero is not None, f"hero never at 0 after dialog hidden: {last_snaps!r}"
    assert target == pytest.approx(expected)
    save_step_screenshot(page, "qa_countup_start")
    assert _near_zero(hero_start, target), (
        f"hero start={hero_start} target={target} text={_metric_text(hero)!r}"
    )

    scope1 = page.locator('[data-cel-kpi-key="scope-1"]').first
    scope2 = page.locator('[data-cel-kpi-key="scope-2"]').first
    calc = page.locator('[data-cel-kpi-key="calculated-count"]').first
    scope1.wait_for(state="visible", timeout=5_000)
    scope2.wait_for(state="visible", timeout=5_000)
    calc.wait_for(state="attached", timeout=5_000)
    scope1_target = float(scope1.get_attribute("data-cel-target") or "nan")
    scope2_target = float(scope2.get_attribute("data-cel-target") or "nan")
    calc_target = float(calc.get_attribute("data-cel-target") or "nan")
    scope1_start = parse_metric_number(_metric_text(scope1))
    scope2_start = parse_metric_number(_metric_text(scope2))
    calc_start = parse_metric_number(_metric_text(calc))
    assert scope1.get_attribute("data-cel-kpi-play") == "1"
    assert scope2.get_attribute("data-cel-kpi-play") == "1"
    assert calc.get_attribute("data-cel-kpi-play") == "1"
    assert scope1_target > 0
    assert scope2_target > 0
    assert calc_target >= 1
    assert _near_zero(scope1_start, scope1_target), (
        f"scope1 start={scope1_start} target={scope1_target}"
    )
    assert _near_zero(scope2_start, scope2_target), (
        f"scope2 start={scope2_start} target={scope2_target}"
    )
    assert _near_zero(calc_start, calc_target), (
        f"count start={calc_start} target={calc_target}"
    )

    mid_deadline = time.time() + 6.0
    hero_mid = scope1_mid = scope2_mid = calc_mid = float("nan")
    saved_mid = False
    while time.time() <= mid_deadline:
        hero_now = parse_metric_number(_metric_text(hero))
        scope1_now = parse_metric_number(_metric_text(scope1))
        scope2_now = parse_metric_number(_metric_text(scope2))
        calc_now = parse_metric_number(_metric_text(calc))
        if not (0 < hero_mid < target) and 0 < hero_now < target:
            hero_mid = hero_now
            save_step_screenshot(page, "qa_countup_mid")
            saved_mid = True
        if not (0 < scope1_mid < scope1_target) and 0 < scope1_now < scope1_target:
            scope1_mid = scope1_now
        if not (0 < scope2_mid < scope2_target) and 0 < scope2_now < scope2_target:
            scope2_mid = scope2_now
        if not (0 < calc_mid < calc_target) and 0 < calc_now < calc_target:
            calc_mid = calc_now
        if (
            0 < hero_mid < target
            and 0 < scope1_mid < scope1_target
            and 0 < scope2_mid < scope2_target
            and (calc_target <= 1 or 0 < calc_mid < calc_target)
        ):
            break
        page.wait_for_timeout(40)
    if not saved_mid:
        save_step_screenshot(page, "qa_countup_mid")
    assert 0 < hero_mid < target, f"hero mid={hero_mid} target={target}"
    assert 0 < scope1_mid < scope1_target, (
        f"scope1 mid={scope1_mid} target={scope1_target}"
    )
    assert 0 < scope2_mid < scope2_target, (
        f"scope2 mid={scope2_mid} target={scope2_target}"
    )
    if calc_target > 1:
        assert 0 < calc_mid < calc_target, (
            f"count mid={calc_mid} target={calc_target}"
        )
    else:
        assert calc_mid >= 0

    settle_deadline = time.time() + 5.0
    hero_final = scope1_final = scope2_final = calc_final = float("nan")
    while time.time() <= settle_deadline:
        hero_final = parse_metric_number(_metric_text(hero))
        scope1_final = parse_metric_number(_metric_text(scope1))
        scope2_final = parse_metric_number(_metric_text(scope2))
        calc_final = parse_metric_number(_metric_text(calc))
        if (
            abs(hero_final - target) <= 0.015
            and abs(scope1_final - scope1_target) <= 0.015
            and abs(scope2_final - scope2_target) <= 0.015
            and abs(calc_final - calc_target) <= 0.1
        ):
            break
        page.wait_for_timeout(80)
    save_step_screenshot(page, "qa_countup_final")
    assert hero_final == pytest.approx(target, abs=0.015)
    assert scope1_final == pytest.approx(scope1_target, abs=0.015)
    assert scope2_final == pytest.approx(scope2_target, abs=0.015)
    assert calc_final == pytest.approx(calc_target, abs=0.1)

    body = visible_text(page)
    assert "尚未計算" in body or "尚未支援" in body
    assert_no_raw_html_leak(body)
    assert_no_app_errors(page)


def test_customer_comprehension_qa(page) -> None:
    """Playwright: a non-expert can see what to do without a methodology manual."""
    base = page._cel_base_url  # type: ignore[attr-defined]
    page.goto(base, wait_until="domcontentloaded")
    wait_streamlit_idle(page)
    page.wait_for_selector("text=Carbon Evidence Ledger", timeout=30_000)
    page.get_by_role("dialog").first.wait_for(state="visible", timeout=20_000)
    welcome = visible_text(page)
    assert "歡迎使用 Carbon Evidence Ledger" in welcome
    assert "第一次使用" not in welcome
    assert "tut.glossary_hint" not in welcome
    assert "排放量" not in welcome or "不需要先懂碳盤查" in welcome
    assert "哪些資料有問題" not in welcome
    save_step_screenshot(page, "qa_customer_welcome")
    page.get_by_role("button", name=re.compile(r"開始使用|Get started")).first.click(
        force=True
    )
    wait_streamlit_idle(page)

    click_button(page, "開始公司設定")
    wait_streamlit_idle(page)
    step1 = visible_text(page)
    assert "你的公司適用哪些要求" in step1 or "確認公司" in step1
    assert "為什麼我要回答這些問題" not in step1
    assert "這一步需要什麼" not in step1
    save_step_screenshot(page, "qa_customer_step1")

    lookup_stub_company(page, STUB_SPARSE_UBN)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    step2 = visible_text(page)
    assert "公司是否上市／上櫃" in step2
    assert "市場身分" not in step2
    assert "系統不會把空白當成 0" not in step2
    assert "不知道／暫不填" not in step2
    assert "我不知道" in step2
    save_step_screenshot(page, "qa_customer_step2")

    choose_selectbox(page, "公司是否上市／上櫃？", "上市（TWSE）")
    set_money_unknown(page, index=0, unknown=True)
    click_button(page, "繼續")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    results = visible_text(page)
    finish = page.get_by_role("button", name=re.compile(r"完成判定"))
    assert finish.count() == 0
    assert "查看目前結果" in results or "儲存並查看結果" in results
    assert "還差" in results or "還需要一些資料" in results
    assert "適用報導年度：—" not in results
    assert "首次申報／揭露年度：—" not in results
    assert "管理員" not in results
    save_step_screenshot(page, "qa_customer_result_actions")

    page.get_by_role(
        "link",
        name=re.compile(r"台灣|Taiwan"),
    ).first.click()
    wait_streamlit_idle(page)
    taiwan = visible_text(page)
    assert "溫室氣體盤查" in taiwan
    assert "環境部溫室氣體查驗" in taiwan or "查驗" in taiwan
    assert "碳費" in taiwan
    assert "IFRS Scope 1/2 確信" in taiwan or "確信" in taiwan
    save_step_screenshot(page, "qa_customer_ghg")

    env_tab = page.get_by_role("tab", name=re.compile(r"查驗"))
    if env_tab.count():
        env_tab.first.click()
        wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_customer_verification")
    verification = visible_text(page)
    assert "管理員" not in verification
    assert "適用報導年度：—" not in verification

    fee_tab = page.get_by_role("tab", name=re.compile(r"碳費"))
    if fee_tab.count():
        fee_tab.first.click()
        wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_customer_carbon_fee")
    fee = visible_text(page)
    assert "首次申報／揭露年度：—" not in fee
    assert "適用報導年度：—" not in fee
    assert_no_app_errors(page)
