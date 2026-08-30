"""Stage 4.2H-A corrected boundary-wizard browser smoke tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from playwright.sync_api import expect

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    ARTIFACTS,
    STUB_ALIGNED_UBN,
    assert_no_app_errors,
    choose_radio,
    choose_selectbox,
    click_button,
    lookup_stub_company,
    open_fresh_app,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e


def _goto_boundary_wizard(page, *, reporting_year: int = 2026) -> None:
    page.set_viewport_size({"width": 1366, "height": 768})
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    year = page.locator('input[aria-label="要評估哪一年度？"]')
    year.fill(str(reporting_year))
    year.press("Tab")
    wait_streamlit_idle(page)
    click_button(page, "繼續")
    click_button(page, "繼續")
    facilities_confirm = page.get_by_role(
        "button", name="是，3 個都正確", exact=True
    )
    if facilities_confirm.count() and facilities_confirm.first.is_visible():
        facilities_confirm.first.click()
        wait_streamlit_idle(page)
    click_button(page, "繼續")
    expect(page.get_by_text("確認報導期間", exact=True)).to_be_visible()


def _wizard(page):
    return page.locator(".st-key-cel_boundary_wizard_root")


def _card(page):
    return _wizard(page).locator(".st-key-cel_boundary_active_card")


def _footer(page):
    return _wizard(page).locator(".st-key-cel_boundary_footer")


def _save_and_continue(page) -> None:
    button = _footer(page).get_by_role("button", name="儲存並繼續", exact=True)
    button.scroll_into_view_if_needed()
    button.click()
    wait_streamlit_idle(page)


def _reach_registration_step(page) -> None:
    _goto_boundary_wizard(page)
    expect(page.get_by_text("選擇本次要使用的已確認報導期間")).to_have_count(0)
    page.get_by_text("我已確認報導年度、開始日與結束日", exact=True).click()
    _save_and_continue(page)
    expect(
        page.get_by_text("為何這些申報目的需要覆核", exact=True)
    ).to_be_visible()
    _save_and_continue(page)
    for _ in range(4):
        if page.get_by_text(
            "把政府紀錄核對到實際公司據點", exact=True
        ).count():
            break
        if page.get_by_text(
            "本期不需確認 IFRS 永續揭露涵蓋範圍。", exact=True
        ).count():
            click_button(page, "繼續")
        elif page.get_by_text(
            "確認 IFRS 永續揭露涵蓋範圍", exact=True
        ).count():
            choose_radio(page, "個別財務報表")
            save_basis = _footer(page).get_by_role(
                "button", name="儲存報導基礎", exact=True
            )
            if save_basis.count():
                save_basis.scroll_into_view_if_needed()
                save_basis.click(force=True)
                wait_streamlit_idle(page)
            else:
                confirm = _footer(page).get_by_role(
                    "button", name="確認此報導範圍", exact=True
                )
                confirm.scroll_into_view_if_needed()
                confirm.click(force=True)
                wait_streamlit_idle(page)
        else:
            _save_and_continue(page)
    expect(
        page.get_by_text("把政府紀錄核對到實際公司據點", exact=True)
    ).to_be_visible()


def test_period_step_hides_historical_selector_and_prefills_assessment_year(
    page,
) -> None:
    _goto_boundary_wizard(page)
    wizard = _wizard(page)
    expect(wizard.get_by_text("選擇本次要使用的已確認報導期間")).to_have_count(
        0
    )
    expect(wizard.get_by_text("報導年度", exact=True)).to_be_visible()
    expect(wizard.get_by_text("期間開始日", exact=True)).to_be_visible()
    expect(wizard.get_by_text("期間結束日", exact=True)).to_be_visible()
    expect(
        wizard.get_by_text("我已確認報導年度、開始日與結束日", exact=True)
    ).to_be_visible()
    year = page.locator('input[aria-label="報導年度"]')
    expect(year).to_have_value("2026")
    start = page.locator('[data-testid="stDateInput"]').filter(
        has_text="期間開始日"
    ).locator("input")
    end = page.locator('[data-testid="stDateInput"]').filter(
        has_text="期間結束日"
    ).locator("input")
    assert "2026" in (start.input_value() + end.input_value())
    assert "01" in start.input_value()
    assert "12" in end.input_value() or "31" in end.input_value()
    page.get_by_text("我已確認報導年度、開始日與結束日", exact=True).click()
    _save_and_continue(page)
    back = _footer(page).get_by_role("button", name="上一步", exact=True)
    back.click()
    wait_streamlit_idle(page)
    expect(wizard.get_by_text("選擇本次要使用的已確認報導期間")).to_have_count(
        0
    )
    expect(year).to_have_value("2026")
    assert_no_app_errors(page)


def test_corrected_journey_reaches_government_record_reconciliation(page) -> None:
    _reach_registration_step(page)
    labels = _wizard(page).locator(".cel-boundary-step strong")
    assert labels.all_text_contents() == [
        "報導期間",
        "申報目的覆核",
        "IFRS 揭露範圍",
        "政府紀錄與據點",
        "營運與主管機關邊界",
        "檢查並確認",
    ]
    expect(page.get_by_text("政府工廠登記資料", exact=True)).to_be_visible()
    expect(page.get_by_text("不能單獨證明", exact=False)).to_be_visible()
    assert "合併" not in _card(page).get_by_role("combobox").inner_text()
    assert_no_app_errors(page)

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    screenshot = ARTIFACTS / "qa_42ha_v2_registration_reconciliation.png"
    page.screenshot(path=str(screenshot), full_page=True)
    assert screenshot.is_file() and screenshot.stat().st_size > 0


def test_wizard_regions_remain_normal_flow_at_supported_viewports(page) -> None:
    _goto_boundary_wizard(page)
    for width, height in ((1366, 768), (1440, 900)):
        page.set_viewport_size({"width": width, "height": height})
        root = _wizard(page)
        expect(root).to_be_visible()
        regions = (
            ".st-key-cel_boundary_stepper_region",
            ".st-key-cel_boundary_context_region",
            ".st-key-cel_boundary_active_card",
            ".st-key-cel_boundary_footer",
        )
        boxes = []
        for selector in regions:
            locator = root.locator(selector)
            expect(locator).to_be_visible()
            box = locator.bounding_box()
            assert box is not None
            boxes.append(box)
        assert all(
            first["y"] + first["height"] <= second["y"] + 1
            for first, second in zip(boxes, boxes[1:], strict=False)
        )
        assert page.evaluate(
            "() => document.documentElement.scrollWidth <= "
            "document.documentElement.clientWidth"
        )
    assert_no_app_errors(page)


def test_registration_reconciliation_five_relations(page) -> None:
    _reach_registration_step(page)
    question = "這筆政府紀錄與本公司實際據點的關係為何？"
    primary = _footer(page).get_by_role("button", name="儲存並繼續", exact=True)
    relation = _card(page).get_by_role("combobox")
    relation.first.click()
    for label in (
        "這筆登記對應本公司的實際據點",
        "這是同一公司據點的另一筆登記",
        "這筆登記不屬於本公司",
        "這筆登記已註銷或不適用於本期",
        "目前無法確認",
    ):
        expect(page.get_by_role("option", name=label)).to_be_visible()
    page.keyboard.press("Escape")
    wait_streamlit_idle(page)

    choose_selectbox(page, question, "這是同一公司據點的另一筆登記")
    expect(
        page.get_by_text(
            "目前沒有可對應的公司據點。請先將第一筆登記核對到本公司據點，"
            "再處理這筆紀錄。",
            exact=True,
        )
    ).to_be_visible()
    expect(page.get_by_role("combobox", name="選擇既有公司據點")).to_have_count(0)
    expect(page.get_by_text("實際公司據點名稱", exact=True)).to_have_count(0)
    expect(primary).to_be_disabled()

    choose_selectbox(page, question, "這筆登記不屬於本公司")
    expect(page.get_by_text("判定依據", exact=True)).to_be_visible()
    expect(page.get_by_text("支持文件或資料參考", exact=True)).to_be_visible()
    expect(page.get_by_text("選擇既有公司據點", exact=True)).to_have_count(0)
    expect(page.get_by_text("實際公司據點名稱", exact=True)).to_have_count(0)
    expect(primary).to_be_enabled()
    _save_and_continue(page)
    expect(
        page.get_by_text("判定不屬於本公司時必須提供依據。", exact=True)
    ).to_be_visible()

    choose_selectbox(page, question, "這筆登記已註銷或不適用於本期")
    expect(page.get_by_text("註銷或失效依據", exact=True)).to_be_visible()
    expect(page.get_by_text("支持文件或資料參考", exact=True)).to_be_visible()
    expect(page.get_by_text("選擇既有公司據點", exact=True)).to_have_count(0)
    _save_and_continue(page)
    expect(
        page.get_by_text(
            "標記政府紀錄已註銷或不適用於本期時必須提供依據。",
            exact=True,
        )
    ).to_be_visible()

    choose_selectbox(page, question, "目前無法確認")
    expect(page.get_by_text("待確認備註（選填）", exact=True)).to_be_visible()
    expect(page.get_by_text("選擇既有公司據點", exact=True)).to_have_count(0)
    expect(page.get_by_text("判定依據", exact=True)).to_have_count(0)
    expect(page.get_by_text("註銷或失效依據", exact=True)).to_have_count(0)

    choose_selectbox(page, question, "這筆登記對應本公司的實際據點")
    site_box = page.get_by_role("combobox", name="選擇既有公司據點")
    expect(site_box).to_be_visible()
    expect(site_box).to_have_value("建立新公司據點")
    expect(
        page.get_by_text("以下資料來自政府紀錄，請確認或修改。", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("textbox", name="實際公司據點名稱")).to_be_visible()
    expect(
        page.get_by_role(
            "checkbox", name="我確認以上名稱與地址是本公司的實際據點。"
        )
    ).to_be_visible()
    name = page.get_by_role("textbox", name="實際公司據點名稱")
    assert name.input_value().strip()
    _save_and_continue(page)
    expect(
        page.get_by_text("請確認名稱與地址是本公司的實際據點。", exact=True)
    ).to_be_visible()
    page.get_by_text(
        "我確認以上名稱與地址是本公司的實際據點。", exact=True
    ).click()
    wait_streamlit_idle(page)
    _save_and_continue(page)
    expect(
        page.get_by_text("把政府紀錄核對到實際公司據點", exact=True)
    ).to_be_visible()
    expect(page.get_by_text("第 2 項，共", exact=False)).to_be_visible()

    choose_selectbox(page, question, "這是同一公司據點的另一筆登記")
    site_box = page.get_by_role("combobox", name="選擇既有公司據點")
    expect(site_box).to_be_visible()
    expect(site_box).not_to_have_value("建立新公司據點")
    expect(primary).to_be_enabled()
    assert_no_app_errors(page)
