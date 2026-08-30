"""Stage 4.2F-B — customer-first intake landing, upload, and confirmation."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    ARTIFACTS,
    NG_CUSTOMER_LABEL,
    assert_no_app_errors,
    assert_no_raw_html_leak,
    choose_radio,
    open_emissions_data_nav,
    open_fresh_app,
    open_intake_mapping_editor,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e

CSV_TEXT = (
    "活動類型,用量,單位,開始日期,結束日期,廠場\n"
    "外購電力,1000,kWh,2025-01-01,2025-01-31,高雄廠\n"
    "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
)


def _goto_intake(page) -> None:
    open_fresh_app(page)
    open_emissions_data_nav(page)
    page.get_by_text("上傳能源與營運資料").first.wait_for(
        state="visible", timeout=20_000
    )


def _upload_company_csv(page) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path = ARTIFACTS / "qa_42fb_ops.csv"
    csv_path.write_text(CSV_TEXT, encoding="utf-8")
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(csv_path))
    wait_streamlit_idle(page, timeout=40)
    page.get_by_text("資料已讀取", exact=False).first.wait_for(
        state="visible", timeout=20_000
    )


def test_journey_42fb_landing_and_upload_screens(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake(page)
    text = visible_text(page)
    assert "上傳能源與營運資料" in text
    assert "上傳公司現有資料" in text
    assert "選擇公司檔案" in text
    assert "還沒有資料檔？下載範例" in text
    assert "需要準備的資料" not in text
    assert "不知道怎麼準備資料" not in text
    assert "我們看懂這份 Excel" not in text
    assert "activity_type" not in text
    assert "activity_value" not in text
    assert_no_raw_html_leak(text)
    save_step_screenshot(page, "qa_42fb_landing_desktop", required=True)
    save_step_screenshot(page, "qa_42fb_upload_desktop", required=True)

    page.set_viewport_size({"width": 390, "height": 1800})
    wait_streamlit_idle(page)
    mobile = visible_text(page)
    assert "上傳能源與營運資料" in mobile
    assert "選擇公司檔案" in mobile
    save_step_screenshot(page, "qa_42fb_landing_mobile", required=True)
    save_step_screenshot(page, "qa_42fb_upload_mobile", required=True)
    assert_no_app_errors(page)


def test_journey_42fb_read_result_editor_and_ng(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 2200})
    _goto_intake(page)
    _upload_company_csv(page)
    text = visible_text(page)
    assert "資料已讀取" in text
    assert "找到 2 筆資料" in text
    assert "系統已自動辨識" in text
    assert "需要確認" in text
    assert "我們看懂這份 Excel" not in text
    assert "可計算" not in text
    assert "activity_type" not in text
    assert "必須確認" not in text
    assert page.get_by_role("button", name="確認並繼續").count() == 0
    assert page.get_by_role("button", name="確認並前往下一題").count() >= 1
    assert page.get_by_role("button", name="修改系統辨識結果").count() >= 1
    save_step_screenshot(page, "qa_42fb_read_compact", required=True)

    open_intake_mapping_editor(page)
    editor = visible_text(page)
    assert "必須確認" in editor
    assert "可選調整" in editor
    assert "activity_type" not in editor
    assert "activity_value" not in editor
    save_step_screenshot(page, "qa_42fb_mapping_editor", required=True)

    ng_help = page.get_by_text("NG1 與 NG2 的官方年度熱值", exact=False)
    ng_help.first.wait_for(state="visible", timeout=20_000)
    ng_help.first.scroll_into_view_if_needed()
    ng_text = visible_text(page)
    assert NG_CUSTOMER_LABEL["NG1"] in ng_text
    assert NG_CUSTOMER_LABEL["NG2"] in ng_text
    assert "還不確定（此列暫不計算）" in ng_text
    radios = page.locator('[data-testid="stRadioOption"]')
    bare = radios.filter(has_text=re.compile(r"^NG1$|^NG2$"))
    assert bare.count() == 0
    choose_radio(page, NG_CUSTOMER_LABEL["NG1"])
    save_step_screenshot(page, "qa_42fb_ng_confirm", required=True)
    assert_no_app_errors(page)


def test_journey_42fb_english_has_no_raw_keys(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake(page)
    en = page.get_by_text("EN", exact=True)
    assert en.count() >= 1
    en.first.click(force=True)
    wait_streamlit_idle(page)
    text = visible_text(page)
    assert "Upload energy and operating data" in text
    assert "Upload your company’s existing data" in text
    assert "Don’t have a data file yet? Download an example." in text
    assert "intake.read_title" not in text
    assert "ev.landing.title" not in text
    assert "activity_type" not in text
    assert_no_app_errors(page)
