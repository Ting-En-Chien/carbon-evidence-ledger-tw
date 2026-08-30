"""Stage 4.2E — facility warning copy, IFRS timeline animation, evidence."""

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
    ARTIFACTS,
    STUB_SEVEN_UBN,
    assert_no_app_errors,
    click_button,
    defer_boundary_wizard_if_present,
    lookup_stub_company,
    open_fresh_app,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e

SHORT_ACTIONS = (
    "成立專案小組、完成初步盤點",
    "盤點資料並調整流程",
    "試編永續資訊專章",
    "完成首次申報",
    "視情況補交確信報告",
    "納入 Scope 3 揭露",
)


def _goto_step3(page) -> None:
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    lookup_stub_company(page, STUB_SEVEN_UBN)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    click_button(page, "繼續")
    wait_streamlit_idle(page)


def _goto_results(page) -> None:
    _goto_step3(page)
    click_button(page, "是，7 個都正確")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    defer_boundary_wizard_if_present(page)


def _track_width(page) -> float:
    return float(
        page.evaluate(
            """() => {
              const bar = document.querySelector('[data-cel-timeline-bar]');
              if (!bar) return NaN;
              const attr = parseFloat(
                bar.getAttribute('data-cel-timeline-width') || ''
              );
              if (isFinite(attr)) return attr;
              const parent = bar.parentElement;
              if (!parent) return NaN;
              const pw = parent.getBoundingClientRect().width;
              if (!pw) return NaN;
              return (bar.getBoundingClientRect().width / pw) * 100;
            }"""
        )
    )


def _timeline_root(page):
    return page.locator("[data-cel-timeline='1']").first


def _desktop_markers(page) -> dict:
    return page.evaluate(
        """() => {
          const desktop = document.querySelector(
            '[data-cel-timeline-scope="desktop"]'
          );
          if (!desktop) return {nMarkers: 0, nDots: 0, states: [], vis: []};
          const markers = [...desktop.querySelectorAll(
            '[data-cel-timeline-marker]'
          )];
          const dots = [...desktop.querySelectorAll('[data-cel-timeline-dot]')];
          const captions = [...desktop.querySelectorAll(
            '[data-cel-timeline-caption]'
          )];
          return {
            nMarkers: markers.length,
            nDots: dots.length,
            nCaptions: captions.length,
            states: markers.map((el) => el.getAttribute('data-cel-timeline-state')),
            vis: dots.map((el) => el.getAttribute('data-cel-timeline-visible')),
            actions: captions.map(
              (el) => (el.querySelector('.cel-timeline-action') || {}).innerText || ''
            ),
          };
        }"""
    )


def _mobile_markers(page) -> dict:
    return page.evaluate(
        """() => {
          const mobile = document.querySelector(
            '[data-cel-timeline-scope="mobile"]'
          );
          if (!mobile) return {n: 0, states: [], vis: [], rail: [], current: -1};
          const items = [...mobile.querySelectorAll(
            '[data-cel-timeline-mobile-item]'
          )];
          return {
            n: items.length,
            states: items.map((el) => el.getAttribute('data-cel-timeline-state')),
            vis: items.map((el) => {
              const dot = el.querySelector('[data-cel-timeline-dot]');
              return dot ? dot.getAttribute('data-cel-timeline-visible') : '';
            }),
            rail: items.map((el) => el.getAttribute('data-cel-rail-reached')),
            classes: items.map((el) => el.className),
            current: items.findIndex((el) => el.classList.contains('is-current')),
          };
        }"""
    )


def _install_width_sampler(page) -> None:
    page.evaluate(
        """() => {
          window.__celTimelineSamples = [];
          const read = () => {
            const bar = document.querySelector('[data-cel-timeline-bar]');
            if (!bar) return;
            window.__celTimelineSamples.push(
              bar.getAttribute('data-cel-timeline-width')
              || bar.style.width
              || ''
            );
          };
          const obs = new MutationObserver(read);
          obs.observe(document.documentElement, {
            childList: true,
            subtree: true,
            attributes: true,
            characterData: true,
          });
          window.__celTimelineTimer = window.setInterval(read, 16);
          read();
        }"""
    )


def _sampled_widths(page) -> list[float]:
    sampled = page.evaluate("() => window.__celTimelineSamples || []")
    observed: list[float] = []
    for item in sampled:
        text = str(item).replace("%", "").strip()
        try:
            observed.append(float(text))
        except ValueError:
            continue
    live = _track_width(page)
    if live == live:
        observed.append(live)
    return [item for item in observed if item == item]


def test_journey_facility_dirty_warning_copy(page) -> None:
    _goto_step3(page)
    click_button(page, "有廠場已停用、出售或資料不正確")
    wait_streamlit_idle(page)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    body = visible_text(page)
    assert "請先確認廠場狀態" in body
    assert "你還有尚未確認的廠場變更" not in body
    assert "請確認每個廠場的最新狀態" in body
    assert "確認這些廠場狀態" in body
    assert "開啟編輯不會自動" not in body
    assert "dirty" not in body
    assert "CASE C" not in body
    notice = page.locator("[data-cel-facility-notice='1']")
    if notice.count():
        notice.first.scroll_into_view_if_needed()
        page.wait_for_timeout(200)
    page.keyboard.press("Escape")
    save_step_screenshot(page, "qa_42e_facility_dirty_warning", required=True)
    assert_no_app_errors(page)


def test_journey_ifrs_timeline_animates_to_milestone_three(page) -> None:
    page.emulate_media(reduced_motion="no-preference")
    page.set_viewport_size({"width": 1440, "height": 2400})
    _goto_step3(page)
    click_button(page, "是，7 個都正確")
    _install_width_sampler(page)
    page.get_by_role("button", name="繼續").first.click(force=True)
    wait_streamlit_idle(page)
    defer_boundary_wizard_if_present(page)
    root = _timeline_root(page)
    root.wait_for(state="attached", timeout=20_000)
    target = float(root.get_attribute("data-cel-timeline-progress") or "nan")
    assert root.get_attribute("data-cel-timeline-count") == "6"
    assert target == pytest.approx(40.0)
    assert int(root.get_attribute("data-cel-timeline-current") or "-1") == 2
    assert int(root.get_attribute("data-cel-timeline-reveal") or "-1") == 2

    observed: list[float] = []
    start_shot = False
    mid_shot = False
    hold_deadline = time.time() + 1.6
    while time.time() <= hold_deadline:
        live = _track_width(page)
        if live == live and live <= 8.0:
            save_step_screenshot(page, "qa_42e_timeline_start", required=True)
            start_shot = True
            break
        page.wait_for_timeout(16)
    if not start_shot:
        save_step_screenshot(page, "qa_42e_timeline_start", required=True)
        start_shot = True
    deadline = time.time() + 10.0
    while time.time() <= deadline:
        observed = _sampled_widths(page)
        live = _track_width(page)
        if not mid_shot and live == live and 6.0 < live < target - 2.0:
            save_step_screenshot(page, "qa_42e_timeline_mid", required=True)
            mid_shot = True
        if observed:
            if start_shot and mid_shot and abs(observed[-1] - target) < 1.5:
                break
        page.wait_for_timeout(20)

    observed = _sampled_widths(page)
    assert observed, "timeline produced no width samples"
    lowest = min(observed)
    highest = observed[-1]
    saw_mid = any(4.0 < item < target - 1.0 for item in observed)
    if not start_shot:
        save_step_screenshot(page, "qa_42e_timeline_start", required=True)
    if not mid_shot:
        save_step_screenshot(page, "qa_42e_timeline_mid", required=True)
    page.locator(".cel-ifrs-timeline").first.scroll_into_view_if_needed()
    page.wait_for_timeout(250)
    save_step_screenshot(page, "qa_42e_timeline_settled", required=True)
    assert lowest <= 8.0, f"timeline should start near zero, min={lowest}"
    assert saw_mid, (
        f"need intermediate width, samples={observed[:12]}... last={highest}"
    )
    assert abs(highest - target) < 1.5, f"final={highest} target={target}"

    markers = _desktop_markers(page)
    assert markers["nMarkers"] == 6
    assert markers["nDots"] == 6
    assert markers["nCaptions"] == 6
    assert markers["states"] == [
        "past_schedule",
        "past_schedule",
        "current_schedule",
        "upcoming",
        "upcoming",
        "upcoming",
    ]
    assert markers["vis"] == ["1", "1", "1", "0", "0", "0"]
    for phrase in SHORT_ACTIONS:
        assert any(phrase in action for action in markers["actions"]), phrase
    body = visible_text(page)
    assert "你的 IFRS 永續揭露時程" in body
    assert "目前應進行：試編永續資訊專章" in body
    assert "不代表公司已完成前述工作" in body
    for phrase in SHORT_ACTIONS:
        assert phrase in body
    assert_no_app_errors(page)

    no_btn = page.get_by_role("button", name=re.compile(r"^沒有$"))
    if no_btn.count():
        no_btn.first.click(force=True)
        wait_streamlit_idle(page)
    stable = _track_width(page)
    assert abs(stable - target) < 1.5
    rerun = _desktop_markers(page)
    assert rerun["vis"] == ["1", "1", "1", "0", "0", "0"]


def test_journey_ifrs_timeline_mobile_current_state(page) -> None:
    page.emulate_media(reduced_motion="no-preference")
    page.set_viewport_size({"width": 1440, "height": 2400})
    _goto_step3(page)
    click_button(page, "是，7 個都正確")
    wait_streamlit_idle(page)
    page.set_viewport_size({"width": 390, "height": 2400})
    wait_streamlit_idle(page)
    _install_width_sampler(page)
    page.get_by_role("button", name="繼續").first.click(force=True)
    wait_streamlit_idle(page)
    defer_boundary_wizard_if_present(page)
    root = _timeline_root(page)
    root.wait_for(state="attached", timeout=20_000)
    target = float(root.get_attribute("data-cel-timeline-progress") or "nan")
    assert int(root.get_attribute("data-cel-timeline-current") or "-1") == 2

    start_shot = False
    mid_shot = False
    hold_deadline = time.time() + 1.6
    while time.time() <= hold_deadline:
        live = _track_width(page)
        revealed = _mobile_markers(page)["vis"].count("1")
        if (live == live and live <= 8.0) or revealed <= 1:
            save_step_screenshot(page, "qa_42e_timeline_mobile_start", required=True)
            start_shot = True
            break
        page.wait_for_timeout(16)
    if not start_shot:
        save_step_screenshot(page, "qa_42e_timeline_mobile_start", required=True)
        start_shot = True
    deadline = time.time() + 10.0
    while time.time() <= deadline:
        live = _track_width(page)
        mobile = _mobile_markers(page)
        revealed = mobile["vis"].count("1") if mobile["n"] else 0
        if not mid_shot and (
            (live == live and 6.0 < live < target - 2.0) or revealed == 2
        ):
            save_step_screenshot(page, "qa_42e_timeline_mobile_mid", required=True)
            mid_shot = True
        if start_shot and mid_shot and mobile.get("current") == 2:
            if mobile["vis"][:3] == ["1", "1", "1"]:
                break
        page.wait_for_timeout(20)

    if not start_shot:
        save_step_screenshot(page, "qa_42e_timeline_mobile_start", required=True)
    if not mid_shot:
        save_step_screenshot(page, "qa_42e_timeline_mobile_mid", required=True)
    mobile_root = page.locator(".cel-ifrs-timeline").first
    mobile_root.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    save_step_screenshot(page, "qa_42e_timeline_mobile_settled", required=True)
    settled = _mobile_markers(page)
    assert settled["n"] == 6
    assert settled["current"] == 2
    assert "is-current" in settled["classes"][2]
    assert settled["states"][2] == "current_schedule"
    assert settled["states"][:2] == ["past_schedule", "past_schedule"]
    assert settled["states"][3:] == ["upcoming", "upcoming", "upcoming"]
    assert settled["vis"] == ["1", "1", "1", "0", "0", "0"]
    assert settled["rail"][:2] == ["1", "1"]
    assert settled["rail"][2:] == ["0", "0", "0", "0"]
    body = visible_text(page)
    assert "依官方時程與今天日期推估" in body
    assert "不代表公司已完成前述工作" in body
    path = ARTIFACTS / "qa_42e_timeline_mobile.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mobile_root.screenshot(path=str(path), timeout=8_000)
    except Exception:  # noqa: BLE001
        page.screenshot(
            path=str(path),
            full_page=False,
            timeout=8_000,
            animations="disabled",
        )
    assert path.is_file() and path.stat().st_size > 0
    assert_no_app_errors(page)


def test_journey_ifrs_timeline_evidence_and_layouts(page) -> None:
    page.emulate_media(reduced_motion="no-preference")
    page.set_viewport_size({"width": 1440, "height": 2600})
    _goto_results(page)
    yes = page.get_by_role("button", name=re.compile(r"^有$"))
    if yes.count():
        yes.first.click(force=True)
        wait_streamlit_idle(page)
    body = visible_text(page)
    assert "你的 IFRS 永續揭露時程" in body
    assert "實收資本額達 100 億元以上" in body
    assert "第一階段適用" in body
    expander = page.get_by_text("查看官方時程依據")
    assert expander.count()
    expander.first.scroll_into_view_if_needed()
    expander.first.click()
    wait_streamlit_idle(page)
    page.keyboard.press("Escape")
    evidence = visible_text(page)
    assert "law.fsc.gov.tw" in evidence
    fsc_title = (
        "有關「公開發行公司年報應行記載事項準則」第7條第2項及"
        "第10條之1第7款、第8款規定之令"
    )
    assert fsc_title in evidence
    assert "（金管證審字第11403851756號）" not in evidence
    assert "IFRS永續揭露準則導入計畫之介紹" in evidence
    assert "IFRS 永續揭露準則導入計畫參考範例" not in evidence
    assert "證交所推動導入IFRS永續揭露準則，第一階段企業宣導會響應熱烈" in evidence
    assert "建議作業時程" not in evidence
    assert "2026-08-12" in evidence
    assert "條件式最晚期限" in evidence or "10 月底" in evidence
    assert "第四個會計年度" in evidence
    save_step_screenshot(page, "qa_42e_timeline_evidence", required=True)

    page.locator(".cel-ifrs-timeline").first.scroll_into_view_if_needed()
    page.wait_for_timeout(250)
    save_step_screenshot(page, "qa_42e_taiwan_ifrs_full", required=True)
    assert_no_app_errors(page)


def test_journey_ifrs_timeline_english_not_mixed(page) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size({"width": 1440, "height": 2400})
    _goto_results(page)
    en = page.get_by_text("EN", exact=True)
    assert en.count() >= 1
    en.first.click(force=True)
    wait_streamlit_idle(page)
    root = _timeline_root(page)
    root.wait_for(state="attached", timeout=20_000)
    text = root.inner_text()
    assert "Your IFRS sustainability disclosure timeline" in text
    assert "Currently scheduled:" in text
    assert "today's date" in text
    assert "Draft the sustainability information chapter" in text
    for token in (
        "目前應進行",
        "試編永續資訊專章",
        "依今天日期推估",
        "第一階段適用",
        "成立專案小組",
        "盤點資料並調整流程",
    ):
        assert token not in text, token
    page.locator(".cel-ifrs-timeline").first.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    save_step_screenshot(page, "qa_42e_timeline_en", required=True)
    assert_no_app_errors(page)


def test_journey_reduced_motion_skips_to_final(page) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size({"width": 1440, "height": 2400})
    _goto_results(page)
    root = _timeline_root(page)
    root.wait_for(state="attached", timeout=20_000)
    root.scroll_into_view_if_needed()
    target = float(root.get_attribute("data-cel-timeline-progress") or "nan")
    page.wait_for_function(
        """(target) => {
          const root = document.querySelector("[data-cel-timeline='1']");
          const bar = document.querySelector('[data-cel-timeline-bar]');
          if (!root || !bar) return false;
          const attr = parseFloat(bar.getAttribute('data-cel-timeline-width') || '');
          const done = root.getAttribute('data-cel-timeline-done') === '1';
          return done && isFinite(attr) && Math.abs(attr - target) < 1.5;
        }""",
        arg=target,
        timeout=10_000,
    )
    width = _track_width(page)
    assert abs(width - target) < 1.5 or width == pytest.approx(target, abs=2.0)
    markers = _desktop_markers(page)
    assert markers["vis"][:3] == ["1", "1", "1"]
    assert markers["vis"][3:] == ["0", "0", "0"]
    assert markers["states"][2] == "current_schedule"
    assert_no_app_errors(page)
