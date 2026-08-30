"""Focused geometry checks: coachmark vs sidebar, reporting-period wrap."""

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
    assert_no_app_errors,
    click_button,
    confirm_intake_reading,
    lookup_stub_company,
    save_step_screenshot,
    start_uploaded_coverage_analysis,
    wait_streamlit_idle,
)
from test_emissions_reports_export import (  # noqa: E402
    COMPLETE_CLEAN,
    _open_reports,
    _open_with_confirmed_company,
    _switch_to_english,
    _upload_csv,
)
from test_onboarding_action_driven import (  # noqa: E402
    COACH,
    SPOTLIGHT,
    _coach_state,
    _start_tour,
    _wait_for_scene,
)

pytestmark = pytest.mark.e2e

GEOMETRY_JS = """() => {
  const host = [...document.querySelectorAll('.st-key-cel_onboarding_coach')]
    .find((node) => node.getAttribute('data-cel-coach-ready') === '1');
  if (!host) return { ready: false };
  const hostBox = host.getBoundingClientRect();
  const sidebar = document.querySelector('[data-testid="stSidebar"]');
  const sideBox = sidebar ? sidebar.getBoundingClientRect() : null;
  const sideVisible = !!(sideBox && sideBox.width >= 80 && sideBox.right > 12);
  const overlap = (a, b) => {
    if (!a || !b) return 0;
    const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 0 && h > 0 ? w * h : 0;
  };
  const cfg = JSON.parse(
    (host.querySelector('[data-cel-coach-config]') || {})
      .getAttribute?.('data-cel-coach-config') || '{}'
  );
  let target = null;
  for (const sel of cfg.selectors || []) {
    try {
      const node = document.querySelector(sel);
      if (!node) continue;
      const named = node.closest("[class*='st-key-cel_onb_']") || node;
      const r = named.getBoundingClientRect();
      if (r.width >= 8 && r.height >= 8) { target = named; break; }
    } catch (e) {}
  }
  const contentBox = (el) => {
    let union = null;
    const add = (r) => {
      if (!r || r.width < 1 || r.height < 1) return;
      if (!union) {
        union = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
      } else {
        union.left = Math.min(union.left, r.left);
        union.top = Math.min(union.top, r.top);
        union.right = Math.max(union.right, r.right);
        union.bottom = Math.max(union.bottom, r.bottom);
      }
    };
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!String(node.nodeValue || '').trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      add(range.getBoundingClientRect());
    }
    for (const control of el.querySelectorAll(
      "button, input, textarea, select, [data-testid='stAlert']"
    )) {
      add(control.getBoundingClientRect());
    }
    if (!union) {
      const r = el.getBoundingClientRect();
      union = { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
    }
    union.width = union.right - union.left;
    union.height = union.bottom - union.top;
    return union;
  };
  const tBox = target ? contentBox(target) : null;
  const spot = document.querySelector('#cel-onboarding-spotlight');
  const sBox = spot ? spot.getBoundingClientRect() : null;
  return {
    ready: true,
    host: {
      left: hostBox.left, top: hostBox.top,
      right: hostBox.right, bottom: hostBox.bottom,
      width: hostBox.width, height: hostBox.height,
      scrollWidth: host.scrollWidth, clientWidth: host.clientWidth,
    },
    sidebar: sideVisible ? {
      left: sideBox.left, right: sideBox.right, width: sideBox.width
    } : null,
    overlapSidebar: sideVisible ? overlap(hostBox, sideBox) : 0,
    overlapTarget: tBox ? overlap(hostBox, tBox) : 0,
    target: tBox && {
      left: tBox.left, top: tBox.top, right: tBox.right, bottom: tBox.bottom,
      width: tBox.width, height: tBox.height
    },
    spotlight: sBox && {
      left: sBox.left, top: sBox.top, width: sBox.width, height: sBox.height
    },
    viewport: { w: window.innerWidth, h: window.innerHeight },
    scene: cfg.id || '',
    text: (host.innerText || '').trim(),
  };
}"""


def _geometry(page) -> dict:
    page.wait_for_function(
        """(sel) => {
          const host = document.querySelector(sel);
          return !!host && host.getAttribute('data-cel-coach-ready') === '1';
        }""",
        arg=COACH,
        timeout=30_000,
    )
    return page.evaluate(GEOMETRY_JS)


def _assert_coach_geometry(page) -> dict:
    geo = _geometry(page)
    assert geo.get("ready") is True, geo
    host = geo["host"]
    viewport = geo["viewport"]
    assert host["left"] >= -1, host
    assert host["top"] >= -1, host
    assert host["right"] <= viewport["w"] + 1, host
    assert host["bottom"] <= viewport["h"] + 1, host
    assert host["scrollWidth"] <= host["clientWidth"] + 1, host
    sidebar = geo.get("sidebar")
    if sidebar:
        assert host["left"] >= sidebar["right"] + 12 - 0.5, (host, sidebar)
        assert geo.get("overlapSidebar", 1) == 0, geo
    assert geo.get("overlapTarget", 1) == 0, geo
    spotlight = geo.get("spotlight")
    assert spotlight is not None, geo
    target = geo.get("target")
    assert target is not None, geo
    assert spotlight["width"] > 8 and spotlight["height"] > 8
    state = _coach_state(page)
    assert state.get("clipped") is False, state
    assert page.locator(SPOTLIGHT).count() >= 1
    assert_no_app_errors(page)
    return geo


def _current_scene(page) -> str:
    return str(
        page.evaluate(
            """() => {
              const host = document.querySelector('.st-key-cel_onboarding_coach');
              const anchor = host && host.querySelector('[data-cel-coach-config]');
              if (!anchor) return '';
                try {
                  const raw = anchor.getAttribute('data-cel-coach-config') || '{}';
                  return JSON.parse(raw).id || '';
              } catch (e) { return ''; }
            }"""
        )
        or ""
    )


def _on_reporting_period_page(page) -> bool:
    title = page.get_by_text("確認報導期間", exact=True)
    return bool(title.count() and title.first.is_visible())


def _walk_to_scene(page, scene_id: str, *, timeout_s: float = 120.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _current_scene(page) == scene_id:
            return _wait_for_scene(page, scene_id, timeout=20_000)
        if scene_id == "reporting_period" and _on_reporting_period_page(page):
            return _wait_for_scene(page, scene_id, timeout=20_000)
        fac = page.get_by_role("button", name=re.compile(r"是，\d+ 個都正確"))
        cont = page.get_by_role("button", name=re.compile(r"^繼續$"))
        continue_ready = bool(
            cont.count() and cont.first.is_visible() and cont.first.is_enabled()
        )
        if fac.count() and fac.first.is_visible() and not continue_ready:
            fac.first.click(force=True)
            wait_streamlit_idle(page)
            continue
        footer = page.locator(".st-key-cel_boundary_footer")
        skip_period_save = _on_reporting_period_page(page)
        clicked = False
        for label in ("繼續", "儲存並繼續"):
            if skip_period_save and label == "儲存並繼續":
                continue
            btn = footer.get_by_role("button", name=label, exact=True)
            if btn.count() == 0:
                btn = page.get_by_role("button", name=label, exact=True)
            if btn.count() and btn.first.is_visible() and btn.first.is_enabled():
                btn.first.scroll_into_view_if_needed()
                btn.first.click(force=True)
                wait_streamlit_idle(page)
                clicked = True
                break
        if clicked:
            continue
        wait_streamlit_idle(page)
    raise AssertionError(f"never reached scene {scene_id}: {_current_scene(page)}")


def _start_setup(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    _start_tour(page)
    click_button(page, "開始公司設定")
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    wait_streamlit_idle(page)


def test_coachmark_stays_in_main_safe_area_zh(page) -> None:
    _start_setup(page)
    _walk_to_scene(page, "company_details")
    _assert_coach_geometry(page)
    save_step_screenshot(
        page, "qa_onboarding_company_details_zh", required=True, full_page=False
    )

    _walk_to_scene(page, "taiwan_facilities")
    _assert_coach_geometry(page)
    save_step_screenshot(
        page, "qa_onboarding_taiwan_facilities_zh", required=True, full_page=False
    )

    _walk_to_scene(page, "reporting_period")
    geo = _assert_coach_geometry(page)
    target = geo.get("target") or {}
    viewport = geo["viewport"]
    sidebar = geo.get("sidebar") or {}
    safe_left = float(sidebar.get("right") or 0) + 12
    safe_w = max(1.0, float(viewport["w"]) - safe_left)
    assert target.get("width", safe_w) <= safe_w * 0.7 + 1, (target, safe_w)
    save_step_screenshot(
        page, "qa_onboarding_reporting_period_zh", required=True, full_page=False
    )

    page.set_viewport_size({"width": 1366, "height": 768})
    wait_streamlit_idle(page)
    _assert_coach_geometry(page)
    save_step_screenshot(
        page, "qa_onboarding_sidebar_safe_1366_zh", required=True, full_page=False
    )


def _assert_period_range_fits(page) -> None:
    page.locator("[data-cel-period-range]").first.wait_for(
        state="visible", timeout=40_000
    )
    metrics = page.evaluate(
        """() => {
          const range = document.querySelector('[data-cel-period-range]');
          const card = range && range.closest('.cel-kpi-card');
          const start = range && range.querySelector('.cel-period-start');
          const end = range && range.querySelector('.cel-period-end');
          if (!range || !card || !start || !end) return null;
          return {
            rangeScroll: range.scrollWidth,
            rangeClient: range.clientWidth,
            cardScroll: card.scrollWidth,
            cardClient: card.clientWidth,
            start: (start.textContent || '').trim(),
            end: (end.textContent || '').trim(),
            startVisible: start.getClientRects().length > 0,
            endVisible: end.getClientRects().length > 0,
          };
        }"""
    )
    assert metrics, "reporting-period range card not in the DOM"
    assert metrics["rangeScroll"] <= metrics["rangeClient"] + 1, metrics
    assert metrics["cardScroll"] <= metrics["cardClient"] + 1, metrics
    assert metrics["startVisible"] is True, metrics
    assert metrics["endVisible"] is True, metrics
    assert metrics["start"], metrics
    assert metrics["end"], metrics


PERIOD_OVERLAP_JS = """() => {
  const overlap = (a, b) => {
    if (!a || !b) return 0;
    const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
    const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    return w > 0 && h > 0 ? w * h : 0;
  };
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      left: r.left, top: r.top, right: r.right, bottom: r.bottom,
      width: r.width, height: r.height,
    };
  };
  const host = [...document.querySelectorAll('.st-key-cel_onboarding_coach')]
    .find((node) => node.getAttribute('data-cel-coach-ready') === '1');
  const group = document.querySelector(
    "[class*='st-key-cel_onb_reporting_period_confirmation']"
  );
  const marker = document.querySelector(
    "[data-cel-onboarding-target='reporting-period-confirmation']"
  );
  const year = document.querySelector('input[aria-label="報導年度"]')
    || document.querySelector('#boundary_wizard_period_year');
  const start = document.querySelector(
    'input[aria-label="期間開始日"], input[aria-label="開始日"]'
  );
  const end = document.querySelector(
    'input[aria-label="期間結束日"], input[aria-label="結束日"]'
  );
  const dates = [...document.querySelectorAll('[data-testid="stDateInput"]')];
  const checkbox = document.querySelector('[data-testid="stCheckbox"]');
  const checkboxLabel = [...document.querySelectorAll('label, p, span')]
    .find((n) => (n.textContent || '').trim() === '我已確認報導年度、開始日與結束日');
  const later = [...document.querySelectorAll('button')]
    .find((b) => (b.innerText || '').trim() === '稍後處理');
  const save = [...document.querySelectorAll('button')]
    .find((b) => (b.innerText || '').trim() === '儲存並繼續');
  const hostBox = host ? host.getBoundingClientRect() : null;
  const hit = (el) => hostBox && el ? overlap(hostBox, el.getBoundingClientRect()) : 0;
  const className = group ? String(group.className || '') : '';
  return {
    ready: !!(host && hostBox && hostBox.width >= 8),
    hidden: !host || !hostBox || hostBox.width < 8,
    placement: host ? host.getAttribute('data-cel-coach-placement') : null,
    coach: box(host),
    group: box(group),
    groupClass: className,
    boundToGroup: className.indexOf('cel_onb_reporting_period_confirmation') !== -1,
    boundToSave: !!(save && host && save.closest && hostBox
      && overlap(hostBox, save.getBoundingClientRect()) > 0
      && save.className
      && String(save.className).indexOf('boundary_period_primary') !== -1),
    markerPresent: !!marker,
    year: box(year),
    start: box(start) || (dates[0] ? box(dates[0]) : null),
    end: box(end) || (dates[1] ? box(dates[1]) : null),
    checkbox: box(checkbox),
    checkboxLabel: box(checkboxLabel),
    later: box(later),
    save: box(save),
    overlap: {
      year: hit(year),
      start: hit(start) || (dates[0] ? hit(dates[0]) : 0),
      end: hit(end) || (dates[1] ? hit(dates[1]) : 0),
      checkbox: hit(checkbox),
      checkboxLabel: hit(checkboxLabel),
      later: hit(later),
      save: hit(save),
    },
    viewport: { w: window.innerWidth, h: window.innerHeight },
  };
}"""


def _assert_period_coach_clear(page, *, width: int, height: int) -> dict:
    page.set_viewport_size({"width": width, "height": height})
    wait_streamlit_idle(page)
    geo = None
    for _ in range(12):
        geo = page.evaluate(PERIOD_OVERLAP_JS)
        if geo and (geo.get("ready") or geo.get("hidden")):
            if geo.get("ready") and geo.get("boundToGroup"):
                break
        wait_streamlit_idle(page)
    assert geo is not None
    overlap = geo.get("overlap") or {}
    covered = {k: v for k, v in overlap.items() if float(v or 0) > 1}
    print(
        f"reporting_period {width}x{height} placement={geo.get('placement')} "
        f"boundToGroup={geo.get('boundToGroup')} hidden={geo.get('hidden')} "
        f"coach={geo.get('coach')} group={geo.get('group')} "
        f"year={geo.get('year')} start={geo.get('start')} end={geo.get('end')} "
        f"checkbox={geo.get('checkbox')} checkboxLabel={geo.get('checkboxLabel')} "
        f"later={geo.get('later')} save={geo.get('save')} overlap={overlap}"
    )
    if geo.get("hidden") and not geo.get("ready"):
        return geo
    assert geo.get("boundToGroup") is True, geo
    assert not covered, (width, height, covered, geo)
    return geo


def test_reporting_period_coachmark_binds_the_period_group(page) -> None:
    _start_setup(page)
    _walk_to_scene(page, "reporting_period")
    geo1440 = _assert_period_coach_clear(page, width=1440, height=900)
    save_step_screenshot(
        page,
        "qa_onboarding_reporting_period_group_1440_zh",
        required=True,
        full_page=False,
    )
    geo1366 = _assert_period_coach_clear(page, width=1366, height=768)
    save_step_screenshot(
        page,
        "qa_onboarding_reporting_period_group_1366_zh",
        required=True,
        full_page=False,
    )
    assert geo1440.get("markerPresent") is True
    assert geo1366.get("markerPresent") is True
    page.get_by_text("我已確認報導年度、開始日與結束日", exact=True).click()
    footer = page.locator(".st-key-cel_boundary_footer")
    save = footer.get_by_role("button", name="儲存並繼續", exact=True)
    save.first.click()
    wait_streamlit_idle(page)
    nxt = _current_scene(page)
    assert nxt not in {"", "reporting_period"}, nxt


def test_reporting_period_card_wraps_zh_and_en(
    page, e2e_company_workspace_dir: Path
) -> None:
    _open_with_confirmed_company(page, e2e_company_workspace_dir)
    _upload_csv(page, "period_wrap.csv", COMPLETE_CLEAN)
    confirm_intake_reading(page)
    start_uploaded_coverage_analysis(page)
    page.get_by_text("碳排計算完成", exact=False).first.wait_for(
        state="visible", timeout=40_000
    )
    _open_reports(page)
    wait_streamlit_idle(page, timeout=40)
    page.set_viewport_size({"width": 1440, "height": 900})
    wait_streamlit_idle(page)
    _assert_period_range_fits(page)
    save_step_screenshot(
        page, "qa_period_range_wrap_zh", required=True, full_page=False
    )
    _switch_to_english(page)
    _assert_period_range_fits(page)
    save_step_screenshot(
        page, "qa_period_range_wrap_en", required=True, full_page=False
    )
    assert_no_app_errors(page)
