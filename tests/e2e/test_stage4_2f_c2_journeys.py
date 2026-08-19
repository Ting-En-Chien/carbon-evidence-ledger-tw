"""Stage 4.2F final monthly mapping-memory customer journeys."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    ARTIFACTS,
    NG_CUSTOMER_LABEL,
    STUB_ALIGNED_UBN,
    STUB_SPARSE_UBN,
    choose_radio,
    click_button,
    dismiss_tutorial_if_present,
    fill_streamlit_date,
    lookup_stub_company,
    open_fresh_app,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e

COMPANY_A_NAME = "長興材料工業股份有限公司"
COMPANY_B_NAME = "未公開財務示範股份有限公司"
MONTHLY_HEADERS = ["活動類型", "用量", "單位", "廠場"]
INTERNAL_TERMS = (
    "High",
    "Medium",
    "Low",
    "canonical",
    "parser",
    "fingerprint",
    "activity_type",
    "activity_value",
    "site_id",
    "system_suggested",
    "customer_confirmed",
    "remembered_mapping_applied",
    "company_vehicle",
    "enterprise",
    "emission_activity",
)
TWO_QUESTIONS = (
    "說明欄,數字甲,數字乙,單位,開始日期,結束日期,廠場\n"
    "採購鋼材,10,20,t,2026-01-01,2026-01-31,高雄一廠\n"
)
MEDIUM_JAN = (
    "活動類型,用量,單位,開始日期,結束日期,廠場\n"
    "採購鋼材,10,t,2026-01-01,2026-01-31,高雄一廠\n"
)
MEDIUM_FEB = (
    "活動類型,用量,單位,開始日期,結束日期,廠場\n"
    "採購鋼材,99,t,2026-02-01,2026-02-28,高雄一廠\n"
)


def _assert_no_internal(text: str) -> None:
    for token in INTERNAL_TERMS:
        assert token not in text


def _assert_company(page, name: str, ubn: str) -> None:
    text = visible_text(page)
    assert name in text
    assert ubn in text
    assert "尚未設定公司" not in text
    assert "Company not set" not in text


def _goto_intake_with_company(page, ubn: str = STUB_ALIGNED_UBN) -> None:
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    dismiss_tutorial_if_present(page)
    lookup_stub_company(page, ubn)
    page.keyboard.press("Escape")
    confirm = page.get_by_role(
        "button", name=re.compile(r"這是我的公司|This is my company")
    )
    if confirm.count():
        confirm.first.click(force=True)
        wait_streamlit_idle(page)
    _navigate_sidebar(page, r"證據與資料|Evidence")
    dismiss_tutorial_if_present(page)
    page.get_by_text("上傳能源與營運資料").first.wait_for(
        state="visible", timeout=20_000
    )


def _write_monthly_xlsx(name: str, sheet_name: str, quantity: int) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(MONTHLY_HEADERS)
    sheet.append(["天然氣", quantity, "m3", "高雄一廠"])
    workbook.save(path)
    return path


def _upload_path(page, path: Path) -> None:
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(path))
    wait_streamlit_idle(page, timeout=40)
    page.get_by_text(
        re.compile(
            r"資料已讀取|File read successfully|"
            r"找到上次確認的欄位設定|Previous confirmed"
        ),
        exact=False,
    ).first.wait_for(state="visible", timeout=20_000)


def _upload_csv(page, name: str, content: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(content, encoding="utf-8")
    _upload_path(page, path)


def _apply_choice(page) -> None:
    page.get_by_role(
        "button", name=re.compile(r"採用這個選擇|Use this choice")
    ).first.click(force=True)
    wait_streamlit_idle(page, timeout=40)


def _edit_uploaded_file(page) -> None:
    page.get_by_role("button", name=re.compile(r"^修改$|^Edit$")).first.click(
        force=True
    )
    wait_streamlit_idle(page, timeout=40)
    page.locator('[data-testid="stFileUploader"] input[type="file"]').first.wait_for(
        state="attached", timeout=20_000
    )


def _choose_global_period(page, start: str, end: str) -> None:
    choose_radio(page, "使用同一資料期間")
    fill_streamlit_date(page, "開始日期", start)
    fill_streamlit_date(page, "結束日期", end)
    _apply_choice(page)


def _confirm_ng1(page) -> None:
    choose_radio(page, NG_CUSTOMER_LABEL["NG1"])
    _apply_choice(page)


def _continue(page) -> None:
    page.get_by_role("button", name=re.compile(r"^繼續$|^Continue$")).first.click(
        force=True
    )
    wait_streamlit_idle(page, timeout=40)


def _show_review_summary(page) -> str:
    page.get_by_role("button", name=re.compile(r"下一步|Next")).first.click(
        force=True
    )
    wait_streamlit_idle(page, timeout=40)
    return visible_text(page)


def _switch_company(page, ubn: str) -> None:
    _navigate_sidebar(page, r"我的適用要求|Your requirements")
    dismiss_tutorial_if_present(page)
    lookup_stub_company(page, ubn)
    _navigate_sidebar(page, r"證據與資料|Evidence")
    dismiss_tutorial_if_present(page)


def _navigate_sidebar(page, name: str) -> None:
    expand = page.get_by_text("keyboard_double_arrow_right", exact=False)
    if expand.count():
        expand.first.click(force=True)
        wait_streamlit_idle(page)
    link = page.get_by_role("link", name=re.compile(name))
    link.first.wait_for(state="visible", timeout=20_000)
    link.first.click(force=True)
    wait_streamlit_idle(page)
    close = page.get_by_text("keyboard_double_arrow_left", exact=False)
    if close.count() and close.first.is_visible():
        close.first.click(force=True)
        wait_streamlit_idle(page)


def test_monthly_january_to_february_then_company_switch(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1900})
    _goto_intake_with_company(page)
    _assert_company(page, COMPANY_A_NAME, STUB_ALIGNED_UBN)

    january = _write_monthly_xlsx(
        "qa_42fc2_monthly_january.xlsx", "2026年1月", 8000
    )
    _upload_path(page, january)
    january_question = visible_text(page)
    assert "請確認「用量」欄位" in january_question
    assert "第 1 項，共 3 項" in january_question
    _assert_company(page, COMPANY_A_NAME, STUB_ALIGNED_UBN)
    _assert_no_internal(january_question)
    _apply_choice(page)
    assert "請告訴系統這份資料的日期或期間。" in visible_text(page)
    _choose_global_period(page, "2026-01-01", "2026-01-31")
    assert "請確認天然氣的環境部年度熱值分類。" in visible_text(page)
    _confirm_ng1(page)
    save_step_screenshot(page, "qa_42fc2_monthly_january", required=True)
    _continue(page)
    january_result = visible_text(page)
    assert "可接受" in january_result
    january_review = _show_review_summary(page)
    assert "2026-01" in january_review
    assert "2026-02" not in january_review

    _edit_uploaded_file(page)
    february = _write_monthly_xlsx(
        "qa_42fc2_monthly_february.xlsx", "2026年2月", 9000
    )
    _upload_path(page, february)
    offered = visible_text(page)
    assert "找到上次確認的欄位設定" in offered
    assert "使用上次設定" in offered
    assert "重新檢查" in offered
    assert "請確認「用量」欄位" not in offered
    assert "2026-01-01" not in offered
    assert "NG1" not in offered
    _assert_company(page, COMPANY_A_NAME, STUB_ALIGNED_UBN)
    _assert_no_internal(offered)
    save_step_screenshot(
        page, "qa_42fc2_monthly_memory_offered", required=True
    )

    page.get_by_role("button", name="使用上次設定").first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    february_period = visible_text(page)
    assert "請告訴系統這份資料的日期或期間。" in february_period
    assert "2026-01-01" not in february_period
    assert "2026-01-31" not in february_period
    assert page.get_by_role("button", name="繼續").count() == 0
    _assert_no_internal(february_period)
    save_step_screenshot(
        page, "qa_42fc2_february_period_required", required=True
    )
    save_step_screenshot(page, "qa_42fc2_memory_applied", required=True)

    _choose_global_period(page, "2026-02-01", "2026-02-28")
    february_context = visible_text(page)
    assert "請確認天然氣的環境部年度熱值分類。" in february_context
    assert "第 2 項，共 2 項" in february_context
    assert "2026-01-01" not in february_context
    _confirm_ng1(page)
    _continue(page)
    february_result = visible_text(page)
    assert "可接受" in february_result
    february_review = _show_review_summary(page)
    assert "2026-02" in february_review
    assert "2026-01" not in february_review

    _switch_company(page, STUB_SPARSE_UBN)
    _assert_company(page, COMPANY_B_NAME, STUB_SPARSE_UBN)
    _edit_uploaded_file(page)
    company_b = _write_monthly_xlsx(
        "qa_42fc2_company_b.xlsx", "2026年2月", 7000
    )
    _upload_path(page, company_b)
    company_b_text = visible_text(page)
    assert "找到上次確認的欄位設定" not in company_b_text
    assert "請確認「用量」欄位" in company_b_text
    assert "你已確認" not in company_b_text
    _assert_company(page, COMPANY_B_NAME, STUB_SPARSE_UBN)
    _assert_no_internal(company_b_text)
    history = page.locator('[data-testid="stExpander"]').filter(
        has_text="查看欄位處理紀錄"
    )
    history.first.click(force=True)
    wait_streamlit_idle(page)
    scoped_history = visible_text(page)
    assert "你已確認" not in scoped_history
    assert COMPANY_A_NAME not in scoped_history
    save_step_screenshot(
        page, "qa_42fc2_company_scoped_history", required=True
    )


def test_two_questions_are_shown_sequentially(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake_with_company(page)
    _upload_csv(page, "qa_42fc2_two_questions.csv", TWO_QUESTIONS)
    first = visible_text(page)
    assert "第 1 項，共 2 項" in first
    assert "請確認「說明欄」欄位" in first
    assert "哪一欄是實際用量？" not in first
    assert page.get_by_role("button", name="採用這個選擇").count() == 1
    save_step_screenshot(page, "qa_42fc2_question_1_of_2", required=True)
    _apply_choice(page)
    second = visible_text(page)
    assert "第 2 項，共 2 項" in second
    assert "請確認「說明欄」欄位" not in second
    assert "哪一欄是實際用量？" in second
    assert page.get_by_role("button", name="採用這個選擇").count() == 1
    _assert_no_internal(second)
    save_step_screenshot(page, "qa_42fc2_question_2_of_2", required=True)


def test_mobile_repeated_upload_fits_390px(page) -> None:
    browser = page.context.browser
    assert browser is not None
    context = browser.new_context(
        viewport={"width": 390, "height": 1800},
        locale="zh-TW",
        is_mobile=True,
        has_touch=True,
    )
    mobile = context.new_page()
    mobile._cel_base_url = page._cel_base_url  # type: ignore[attr-defined]
    try:
        _goto_intake_with_company(mobile)
        _upload_csv(mobile, "qa_42fc2_mobile_jan.csv", MEDIUM_JAN)
        _apply_choice(mobile)
        assert "資料已可繼續" in visible_text(mobile)
        _continue(mobile)
        _edit_uploaded_file(mobile)
        _upload_csv(mobile, "qa_42fc2_mobile_feb.csv", MEDIUM_FEB)
        text = visible_text(mobile)
        assert "找到上次確認的欄位設定" in text
        _assert_company(mobile, COMPANY_A_NAME, STUB_ALIGNED_UBN)
        use_button = mobile.get_by_role("button", name="使用上次設定").first
        use_button.wait_for(state="visible", timeout=15_000)
        box = use_button.bounding_box()
        assert box is not None
        assert box["x"] >= -1
        assert box["x"] + box["width"] <= 398
        overflow = mobile.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        assert overflow <= 8
        _assert_no_internal(text)
        save_step_screenshot(mobile, "qa_42fc2_mobile", required=True)
    finally:
        context.close()


def test_english_memory_offer_has_company_and_no_internal_values(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake_with_company(page)
    page.get_by_text("EN", exact=True).first.click(force=True)
    wait_streamlit_idle(page)
    _upload_csv(page, "qa_42fc2_english_jan.csv", MEDIUM_JAN)
    _apply_choice(page)
    _continue(page)
    _edit_uploaded_file(page)
    _upload_csv(page, "qa_42fc2_english_feb.csv", MEDIUM_FEB)
    text = visible_text(page)
    assert "Previous confirmed column settings were found" in text
    assert "Use previous settings" in text
    assert "Check again" in text
    assert COMPANY_A_NAME in text
    assert STUB_ALIGNED_UBN in text
    assert "Company not set" not in text
    _assert_no_internal(text)
    save_step_screenshot(page, "qa_42fc2_english", required=True)
