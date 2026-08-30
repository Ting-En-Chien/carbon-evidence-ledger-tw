"""Stage 4.2D customer facility confirmation, Taiwan results, capital count-up."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    STUB_ALIGNED_UBN,
    STUB_DIFF_UBN,
    STUB_SEVEN_UBN,
    assert_no_app_errors,
    click_button,
    defer_boundary_wizard_if_present,
    lookup_stub_company,
    open_fresh_app,
    parse_metric_number,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e


def _goto_step3(page, ubn: str) -> None:
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    lookup_stub_company(page, ubn)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    click_button(page, "繼續")
    wait_streamlit_idle(page)


def _confirm_all_and_continue(page) -> None:
    click_button(page, "是，7 個都正確")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    defer_boundary_wizard_if_present(page)


def _set_nth_facility_status(page, index: int, option: str) -> None:
    boxes = page.locator('[data-testid="stSelectbox"]').filter(
        has_text=re.compile(r"這個據點目前的狀態")
    )
    control = boxes.nth(index).locator(
        '[data-baseweb="select"], [role="combobox"]'
    ).first
    control.click(force=True)
    page.wait_for_timeout(400)
    page.get_by_role("option", name=option).first.click(force=True)
    wait_streamlit_idle(page)


def _near_zero(value: float, final: float) -> bool:
    return value <= max(0.08 * abs(final), 1.0)


def test_journey_seven_facility_compact_confirm(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    body = visible_text(page)
    assert "根據政府公開資料，我們找到 7 個登記工廠。" in body
    assert "是，7 個都正確" in body
    assert "有廠場已停用、出售或資料不正確" in body
    assert "全部納入本次資料" not in body
    assert "這次如何處理？" not in body
    assert "維持使用" not in body
    assert "納入本次資料" not in body
    assert "僅在政府資料找到" not in body
    assert "報導邊界" not in body
    save_step_screenshot(page, "qa_facility_compact_default", required=True)
    _confirm_all_and_continue(page)
    result = visible_text(page)
    assert "還差 1 項資料" in result
    assert result.count("還需要一些資料") < 2
    assert "台灣溫室氣體盤查" not in result.split("判定結果")[0]
    assert_no_app_errors(page)


def test_journey_facility_exception_edit(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    body = visible_text(page)
    assert "是，7 個都正確" in body
    click_button(page, "有廠場已停用、出售或資料不正確")
    wait_streamlit_idle(page)
    edited = visible_text(page)
    assert "這個據點目前的狀態" in edited
    assert "路竹二廠" in edited
    assert "汐止廠" in edited
    assert "確認這些廠場狀態" in edited
    assert "全部納入本次資料" not in edited
    assert "這次如何處理？" not in edited
    assert "維持使用" not in edited
    boxes = page.locator('[data-testid="stSelectbox"]').filter(
        has_text=re.compile(r"這個據點目前的狀態")
    )
    assert boxes.count() >= 2
    page.set_viewport_size({"width": 1440, "height": 2200})
    confirm_btn = page.get_by_role("button", name="確認這些廠場狀態")
    if confirm_btn.count():
        confirm_btn.first.scroll_into_view_if_needed()
        page.wait_for_timeout(200)
    save_step_screenshot(page, "qa_facility_exception_edit", required=True)
    control = boxes.first.locator('[data-baseweb="select"], [role="combobox"]').first
    control.click(force=True)
    page.wait_for_timeout(400)
    options = page.get_by_role("option")
    labels = " ".join(options.all_inner_texts()) if options.count() else edited
    assert "營運中" in labels
    assert "已出售" in labels
    assert "資料不正確" in labels
    page.keyboard.press("Escape")
    assert_no_app_errors(page)


def test_journey_facility_exception_requires_explicit_confirm(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    click_button(page, "有廠場已停用、出售或資料不正確")
    wait_streamlit_idle(page)
    assert "確認這些廠場狀態" in visible_text(page)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    blocked = visible_text(page)
    assert "確認台灣廠場" in blocked
    assert "請先確認廠場狀態" in blocked
    assert "還差 1 項資料" not in blocked
    assert "你的結果" not in blocked or "步驟 3" in blocked
    _set_nth_facility_status(page, 1, "已出售")
    page.keyboard.press("Escape")
    click_button(page, "確認這些廠場狀態")
    wait_streamlit_idle(page)
    confirmed = visible_text(page)
    assert "汐止廠" in confirmed
    assert "已出售" in confirmed
    assert "確認台灣廠場" in confirmed
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    defer_boundary_wizard_if_present(page)
    result = visible_text(page)
    assert "還差 1 項資料" in result
    assert "公司是否曾收到主管機關要求盤查、登錄或查驗溫室氣體的通知？" in result
    assert_no_app_errors(page)


def test_journey_confirmed_then_exception_edit_blocks_continue(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    click_button(page, "是，7 個都正確")
    wait_streamlit_idle(page)
    click_button(page, "有廠場已停用、出售或資料不正確")
    wait_streamlit_idle(page)
    _set_nth_facility_status(page, 1, "已出售")
    page.keyboard.press("Escape")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    blocked = visible_text(page)
    assert "確認台灣廠場" in blocked
    assert "請先確認廠場狀態" in blocked
    assert "還差 1 項資料" not in blocked
    assert_no_app_errors(page)


def test_journey_exception_dirty_after_confirm_uses_latest_commit(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    click_button(page, "有廠場已停用、出售或資料不正確")
    wait_streamlit_idle(page)
    _set_nth_facility_status(page, 1, "已出售")
    page.keyboard.press("Escape")
    click_button(page, "確認這些廠場狀態")
    wait_streamlit_idle(page)
    _set_nth_facility_status(page, 0, "已停用")
    page.keyboard.press("Escape")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    blocked = visible_text(page)
    assert "請先確認廠場狀態" in blocked
    assert "還差 1 項資料" not in blocked
    click_button(page, "確認這些廠場狀態")
    wait_streamlit_idle(page)
    latest = visible_text(page)
    assert "路竹二廠" in latest
    assert "已停用" in latest
    assert "汐止廠" in latest
    assert "已出售" in latest
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    defer_boundary_wizard_if_present(page)
    result = visible_text(page)
    assert "還差 1 項資料" in result
    assert_no_app_errors(page)


def test_journey_taiwan_missing_fact_one_action(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    _confirm_all_and_continue(page)
    result = visible_text(page)
    assert "還差 1 項資料" in result
    assert "公司是否曾收到主管機關要求盤查、登錄或查驗溫室氣體的通知？" in result
    assert result.count("還需要一些資料") <= 1
    assert "目前還無法確認是否涉及碳費。" not in result
    assert "公司需要第三方查驗溫室氣體資料嗎？" not in result
    titles = page.locator(".cel-outcome-q, .cel-card-title")
    blob = " ".join(titles.all_inner_texts()) if titles.count() else result
    assert blob.count("台灣溫室氣體盤查") == 0 or "嗎？" in result
    save_step_screenshot(page, "qa_taiwan_missing_fact", required=True)
    assert_no_app_errors(page)


def test_journey_taiwan_notice_no_hides_verification(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    _confirm_all_and_continue(page)
    no_btn = page.get_by_role("button", name=re.compile(r"^沒有$"))
    assert no_btn.count()
    no_btn.first.click(force=True)
    wait_streamlit_idle(page)
    result = visible_text(page)
    assert "還差 1 項資料" not in result
    assert "公司需要第三方查驗溫室氣體資料嗎？" not in result
    assert "台灣溫室氣體盤查" not in result
    assert "目前還無法確認是否涉及碳費。" not in result
    assert "需要／適用" not in result
    assert_no_app_errors(page)


def test_journey_taiwan_resolved_results(page) -> None:
    _goto_step3(page, STUB_SEVEN_UBN)
    _confirm_all_and_continue(page)
    yes = page.get_by_role("button", name=re.compile(r"^有$"))
    if yes.count():
        yes.first.click(force=True)
        wait_streamlit_idle(page)
    result = visible_text(page)
    assert "還需要一些資料" not in result or result.count("還需要一些資料") == 0
    assert "公司需要第三方查驗溫室氣體資料嗎？" in result
    assert "需要" in result
    assert "台灣溫室氣體盤查" not in result
    assert "目前還無法確認是否涉及碳費。" not in result
    page.set_viewport_size({"width": 1440, "height": 2400})
    verif = page.locator(".cel-outcome-q").filter(
        has_text="公司需要第三方查驗溫室氣體資料嗎？"
    )
    if verif.count():
        verif.first.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
    save_step_screenshot(page, "qa_taiwan_resolved_results", required=True)
    assert_no_app_errors(page)


def test_journey_company_capital_countup(page) -> None:
    page.emulate_media(reduced_motion="no-preference")
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    field = page.get_by_label(re.compile(r"統一編號|Unified business number"))
    field.first.fill(STUB_ALIGNED_UBN)
    wait_streamlit_idle(page)
    page.get_by_role("button", name=re.compile(r"查詢公司")).first.click(force=True)
    capital = page.locator('[data-cel-kpi-key="paid-in-capital-12345675"]').first
    capital.wait_for(state="attached", timeout=20_000)
    target = float(capital.get_attribute("data-cel-target") or "nan")
    assert target == pytest.approx(12_000_000_000)
    first_run = capital.get_attribute("data-cel-kpi-run") or ""

    start = parse_metric_number(capital.inner_text())
    deadline = time.time() + 8.0
    while time.time() <= deadline and not _near_zero(start, target):
        start = parse_metric_number(capital.inner_text())
        if _near_zero(start, target):
            break
        page.wait_for_timeout(20)
    save_step_screenshot(page, "qa_company_capital_zero", required=True)
    assert _near_zero(start, target), f"capital start={start} target={target}"

    mid = start
    mid_deadline = time.time() + 4.0
    while time.time() <= mid_deadline:
        mid = parse_metric_number(capital.inner_text())
        if 0 < mid < target:
            break
        page.wait_for_timeout(30)
    save_step_screenshot(page, "qa_company_capital_mid", required=True)
    assert 0 < mid < target, f"capital mid={mid} target={target}"

    final_deadline = time.time() + 6.0
    final = mid
    while time.time() <= final_deadline:
        final = parse_metric_number(capital.inner_text())
        if abs(final - target) < 1:
            break
        page.wait_for_timeout(40)
    save_step_screenshot(page, "qa_company_capital_final", required=True)
    assert abs(final - target) < 1

    confirm = page.get_by_role("button", name=re.compile(r"這是我的公司"))
    if confirm.count():
        confirm.first.click(force=True)
        wait_streamlit_idle(page)
    rerun_text = visible_text(page)
    assert "NT$" in rerun_text or "12,000,000,000" in rerun_text
    after = parse_metric_number(
        page.locator('[data-cel-kpi-key="paid-in-capital-12345675"]').first.inner_text()
    )
    assert abs(after - target) < 1

    field = page.get_by_label(re.compile(r"統一編號|Unified business number"))
    field.first.fill(STUB_DIFF_UBN)
    page.evaluate(
        """() => {
          window.__celReplaySamples = [];
          const key = 'paid-in-capital-13579243';
          const read = () => {
            const el = document.querySelector('[data-cel-kpi-key="' + key + '"]');
            if (!el) return;
            window.__celReplaySamples.push(el.textContent || '');
          };
          const obs = new MutationObserver(read);
          obs.observe(document.documentElement, {
            childList: true,
            subtree: true,
            characterData: true,
          });
          window.__celReplayTimer = window.setInterval(read, 16);
          read();
        }"""
    )
    page.get_by_role("button", name=re.compile(r"查詢公司")).first.click(force=True)
    capital = page.locator('[data-cel-kpi-key="paid-in-capital-13579243"]').first
    capital.wait_for(state="attached", timeout=20_000)
    new_target = float(capital.get_attribute("data-cel-target") or "nan")
    assert new_target == pytest.approx(8_000_000_000)
    new_run = capital.get_attribute("data-cel-kpi-run") or ""
    assert new_run != first_run
    assert "13579243" in new_run
    assert capital.get_attribute("data-cel-kpi-play") == "1"

    observed: list[float] = []
    replay_deadline = time.time() + 10.0
    while time.time() <= replay_deadline:
        sampled = page.evaluate("() => window.__celReplaySamples || []")
        observed = [parse_metric_number(str(item)) for item in sampled]
        if capital.count():
            observed.append(
                parse_metric_number(
                    str(capital.evaluate("el => el.textContent || ''"))
                )
            )
        if observed:
            finite = [item for item in observed if item == item]
            if finite:
                lowest = min(finite)
                highest = next(
                    (item for item in reversed(finite)),
                    float("nan"),
                )
                saw_mid = any(0 < item < new_target for item in finite)
                if (
                    _near_zero(lowest, new_target)
                    and saw_mid
                    and abs(highest - new_target) < 1
                ):
                    break
        page.wait_for_timeout(20)
    assert observed, "changed UBN capital element produced no numeric samples"
    finite = [item for item in observed if item == item]
    lowest = min(finite)
    final_seen = next((item for item in reversed(finite)), float("nan"))
    saw_mid = any(0 < item < new_target for item in finite)
    assert abs(final_seen - new_target) < 1, (
        f"changed UBN must finish at {new_target}, last={final_seen}"
    )
    assert _near_zero(lowest, new_target), (
        "changed UBN must replay from zero; "
        f"min={lowest} mid={saw_mid} last={final_seen} target={new_target}"
    )
    assert saw_mid, (
        "changed UBN must show an intermediate value; "
        f"min={lowest} last={final_seen} target={new_target}"
    )
    assert_no_app_errors(page)
