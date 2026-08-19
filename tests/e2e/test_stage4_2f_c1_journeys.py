"""Stage 4.2F-C1 — confidence exceptions and exception-only confirmation."""

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
    choose_selectbox,
    open_fresh_app,
    open_intake_mapping_editor,
    resolve_intake_exceptions,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e

HIGH_STEEL = (
    "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
    "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
)
MEDIUM_STEEL = (
    "活動類型,用量,單位,開始日期,結束日期,廠場\n"
    "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
)
UNMATCHED = (
    "說明欄,使用量,單位,開始日期,結束日期,廠場\n"
    "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
)
MIXED = (
    "活動類型,用量,單位,開始日期,結束日期,廠場\n"
    "外購電力,1000,kWh,2025-01-01,2025-01-31,高雄廠\n"
    "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    "柴油,1200,L,2025-01-01,2025-01-31,高雄廠\n"
    "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    "雜項能源,5,t,2025-01-01,2025-01-31,高雄廠\n"
)
INTERNAL_TERMS = (
    "High",
    "Medium",
    "Low",
    "canonical",
    "confidence score",
    "activity_type",
    "activity_value",
    "site_id",
)


def _goto_intake(page) -> None:
    open_fresh_app(page)
    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    page.get_by_text("上傳能源與營運資料").first.wait_for(
        state="visible", timeout=20_000
    )


def _upload_csv(page, name: str, content: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path = ARTIFACTS / name
    csv_path.write_text(content, encoding="utf-8")
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(csv_path))
    wait_streamlit_idle(page, timeout=40)
    page.get_by_text(
        re.compile(r"資料已讀取|File read successfully"),
        exact=False,
    ).first.wait_for(state="visible", timeout=20_000)


def _select_unknown_activity(page, source_label: str) -> None:
    unknown = "還不確定（相關列暫不計算）"
    boxes = page.locator('[data-testid="stSelectbox"]')
    target = None
    for index in range(boxes.count()):
        box = boxes.nth(index)
        body = box.inner_text()
        if source_label in body and "其他資料功能" not in body:
            target = box
            break
    assert target is not None, f"activity question not found for {source_label!r}"
    control = target.locator(
        '[data-baseweb="select"], [role="combobox"], input'
    ).first
    control.click(force=True)
    listbox = page.get_by_role("listbox")
    listbox.first.wait_for(state="visible", timeout=10_000)
    option = listbox.first.get_by_role("option", name=unknown)
    if option.count() == 0:
        option = listbox.first.get_by_text(unknown, exact=True)
    option.first.click(force=True)
    try:
        listbox.first.wait_for(state="hidden", timeout=5_000)
    except Exception:  # noqa: BLE001
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    wait_streamlit_idle(page)
    page.wait_for_timeout(300)


def _confirm_count(text: str) -> int:
    match = re.search(r"(\d+) 個項目需要確認", text)
    assert match, f"confirmation count missing in: {text[:500]}"
    return int(match.group(1))


def _apply_button(page):
    return page.get_by_role("button", name=re.compile(r"採用這個選擇|Use this choice"))


def test_journey_42fc1_a_zero_exception_desktop(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake(page)
    _upload_csv(page, "qa_42fc1_high.csv", HIGH_STEEL)
    text = visible_text(page)
    assert "資料已可繼續" in text
    assert "可繼續 1 筆；0 筆暫緩處理" in text
    assert "等待回覆" not in text
    assert "沒有需要確認的項目" not in text
    assert _apply_button(page).count() == 0
    assert page.get_by_role("button", name="確認並繼續").count() == 0
    assert page.get_by_role("button", name="繼續").count() >= 1
    for token in INTERNAL_TERMS:
        assert token not in text
    save_step_screenshot(page, "qa_42fc1_zero_exception_desktop", required=True)
    page.get_by_role("button", name="繼續").first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    results = visible_text(page)
    assert "可接受" in results
    assert "必須確認" not in results


def test_journey_42fc1_b_medium_exception(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake(page)
    _upload_csv(page, "qa_42fc1_medium.csv", MEDIUM_STEEL)
    text = visible_text(page)
    assert _confirm_count(text) >= 1
    assert "需要你確認的項目" in text
    assert "請確認「用量」欄位" in text
    assert "要使用哪一欄？" in text
    assert "看起來是用量" not in text
    assert page.get_by_role("button", name="繼續").count() == 0
    assert _apply_button(page).count() >= 1
    save_step_screenshot(page, "qa_42fc1_medium_exception", required=True)
    _apply_button(page).first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    after = visible_text(page)
    assert "資料已可繼續" in after
    assert "可繼續 1 筆；0 筆暫緩處理" in after
    page.get_by_role("button", name="繼續").first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    assert "可接受" in visible_text(page)


def test_journey_42fc1_c_unmatched_required(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake(page)
    _upload_csv(page, "qa_42fc1_unmatched.csv", UNMATCHED)
    text = visible_text(page)
    assert "請確認「說明欄」欄位" in text
    assert page.get_by_role("button", name="繼續").count() == 0
    save_step_screenshot(page, "qa_42fc1_unmatched_required", required=True)
    choose_selectbox(page, "要使用哪一欄？", "說明欄")
    _apply_button(page).first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    after = visible_text(page)
    assert "資料已可繼續" in after
    page.get_by_role("button", name="繼續").first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    assert "可接受" in visible_text(page)


def test_journey_42fc1_d_mixed_queue_to_zero(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 2000})
    _goto_intake(page)
    _upload_csv(page, "qa_42fc1_mixed.csv", MIXED)
    before = visible_text(page)
    start = _confirm_count(before)
    assert start >= 2
    assert "請確認「用量」欄位" in before
    assert "第 1 項，共 5 項" in before
    assert "請確認天然氣的環境部年度熱值分類。" not in before
    assert _apply_button(page).count() == 1
    assert "必須確認" not in before
    save_step_screenshot(page, "qa_42fc1_mixed_queue", required=True)
    _apply_button(page).first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    mid = visible_text(page)
    assert _confirm_count(mid) == start - 1
    assert "第 2 項，共 5 項" in mid
    assert "雜項能源" in mid
    assert _apply_button(page).count() == 1
    _select_unknown_activity(page, "雜項能源")
    apply_btn = _apply_button(page)
    apply_btn.first.wait_for(state="visible", timeout=15_000)
    apply_btn.first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    resolve_intake_exceptions(page)
    zero = visible_text(page)
    assert re.search(r"[1-9]\d* 個項目需要確認", zero) is None
    assert "已完成目前確認；另有 1 筆暫緩處理，不納入本次計算" in zero
    assert "等待回覆" not in zero
    save_step_screenshot(page, "qa_42fc1_mixed_zero", required=True)


def test_journey_42fc1_e_unresolved_rows_held_out(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 2000})
    _goto_intake(page)
    _upload_csv(page, "qa_42fc1_held.csv", MIXED)
    _apply_button(page).first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    _select_unknown_activity(page, "雜項能源")
    apply_btn = _apply_button(page)
    apply_btn.first.wait_for(state="visible", timeout=15_000)
    apply_btn.first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    resolve_intake_exceptions(page)
    assert _apply_button(page).count() == 0, visible_text(page)
    cont = page.get_by_role("button", name="繼續")
    cont.first.wait_for(state="visible", timeout=20_000)
    cont.first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    body = visible_text(page)
    assert "可接受" in body
    assert "需要修正" in body
    assert "總筆數" in body
    tab = page.get_by_role("tab", name="需要修正")
    tab.first.click()
    wait_streamlit_idle(page)
    page.get_by_text("暫不計算", exact=False).first.wait_for(
        state="attached", timeout=15_000
    )
    html = page.content()
    assert "暫不計算" in html
    assert "還無法判斷" in html
    save_step_screenshot(page, "qa_42fc1_unresolved_rows", required=True)


def test_journey_42fc1_unknown_context_held_summary(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake(page)
    csv_text = (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    )
    _upload_csv(page, "qa_42fc1_ng_unknown.csv", csv_text)
    unknown = page.get_by_text("還不確定（相關列暫不計算）", exact=True)
    unknown.first.wait_for(state="visible", timeout=15_000)
    unknown.first.click(force=True)
    wait_streamlit_idle(page)
    _apply_button(page).first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    text = visible_text(page)
    assert "已完成目前確認；另有 1 筆暫緩處理，不納入本次計算" in text
    assert "資料已可繼續" not in text
    assert "等待回覆" not in text
    assert "可繼續 1 筆；1 筆暫緩處理" in text
    save_step_screenshot(page, "qa_42fc1_unknown_context_held", required=True)
    page.get_by_role("button", name="繼續").first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    result = visible_text(page)
    assert "可接受" in result
    assert "需要修正" in result


def test_journey_42fc1_f_draft_continue_stays_on_confirmation(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 2000})
    _goto_intake(page)
    _upload_csv(page, "qa_42fc1_draft.csv", MEDIUM_STEEL)
    open_intake_mapping_editor(page)
    editor = visible_text(page)
    assert "必須確認" in editor
    assert "你有尚未套用的選擇" in editor
    page.get_by_role("button", name="繼續").first.click(force=True)
    wait_streamlit_idle(page)
    stayed = visible_text(page)
    assert "必須確認" in stayed
    assert "你有尚未套用的選擇" in stayed
    assert "可接受" not in stayed
    choose_selectbox(page, "用量欄位", "請選擇")
    wait_streamlit_idle(page)
    rerun = visible_text(page)
    assert "必須確認" in rerun
    assert "可接受" not in rerun


def _assert_in_viewport(box: dict, viewport: dict) -> None:
    assert box is not None
    assert box["width"] > 8
    assert box["height"] > 8
    assert box["x"] >= -1
    assert box["y"] >= -1
    assert box["x"] + box["width"] <= viewport["width"] + 8
    assert box["y"] < viewport["height"]


def test_journey_42fc1_mobile_fresh_sidebar(page) -> None:
    browser = page.context.browser
    assert browser is not None
    context = browser.new_context(
        viewport={"width": 390, "height": 1800},
        locale="zh-TW",
        is_mobile=True,
        has_touch=True,
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
            "Mobile/15E148 Safari/604.1"
        ),
    )
    mobile = context.new_page()
    mobile._cel_base_url = page._cel_base_url  # type: ignore[attr-defined]
    try:
        open_fresh_app(mobile)
        expand = mobile.get_by_text("keyboard_double_arrow_right", exact=False)
        assert expand.count() >= 1
        mobile.goto(
            f"{mobile._cel_base_url}/data_intake",  # type: ignore[attr-defined]
            wait_until="domcontentloaded",
        )
        wait_streamlit_idle(mobile)
        mobile.get_by_text("上傳能源與營運資料").first.wait_for(
            state="visible", timeout=20_000
        )
        _upload_csv(mobile, "qa_42fc1_mobile_fresh.csv", MEDIUM_STEEL)
        question = mobile.get_by_text("請確認「用量」欄位", exact=False)
        question.first.wait_for(state="visible", timeout=20_000)
        viewport = mobile.viewport_size or {"width": 390, "height": 1800}
        _assert_in_viewport(question.first.bounding_box(), viewport)
        control = mobile.locator('[data-testid="stSelectbox"]').first
        apply_btn = _apply_button(mobile).first
        apply_btn.wait_for(state="visible", timeout=15_000)
        _assert_in_viewport(control.bounding_box(), viewport)
        _assert_in_viewport(apply_btn.bounding_box(), viewport)
        reopen = mobile.get_by_text("keyboard_double_arrow_right", exact=False)
        close = mobile.get_by_text("keyboard_double_arrow_left", exact=False)
        assert reopen.count() >= 1 or close.count() >= 1
        sidebar = mobile.locator('[data-testid="stSidebar"]')
        qbox = question.first.bounding_box()
        if sidebar.count() and sidebar.first.is_visible():
            sbox = sidebar.first.bounding_box()
            if sbox and qbox:
                overlap_w = (
                    min(sbox["x"] + sbox["width"], qbox["x"] + qbox["width"])
                    - max(sbox["x"], qbox["x"])
                )
                overlap_h = (
                    min(sbox["y"] + sbox["height"], qbox["y"] + qbox["height"])
                    - max(sbox["y"], qbox["y"])
                )
                covering = overlap_w > 24 and overlap_h > 24
                assert not covering or sbox["width"] < 80
        overflow = mobile.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        assert overflow <= 8
        save_step_screenshot(mobile, "qa_42fc1_exception_mobile", required=True)
    finally:
        context.close()


def test_journey_42fc1_english(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1800})
    _goto_intake(page)
    en = page.get_by_text("EN", exact=True)
    assert en.count() >= 1
    en.first.click(force=True)
    wait_streamlit_idle(page)
    _upload_csv(page, "qa_42fc1_en.csv", HIGH_STEEL)
    text = visible_text(page)
    assert "File read successfully" in text
    assert "This file is ready to continue" in text
    assert "Nothing needs confirmation" not in text
    assert "waiting for answers" not in text
    assert "intake.read_title" not in text
    assert "intake.ex.none" not in text
    for token in INTERNAL_TERMS:
        assert token not in text
    save_step_screenshot(page, "qa_42fc1_english", required=True)
