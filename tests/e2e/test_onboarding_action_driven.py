"""E2E closure for the action-driven first-run onboarding.

Walks the real product: welcome modal, company setup, upload, confirmation
queue, coverage, analysis, results. The coachmark must follow the live DOM,
never paint a misplaced highlight, and unmount completely at the end.
"""

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
    NAV_EVIDENCE,
    STUB_ALIGNED_UBN,
    _goto_app,
    assert_no_app_errors,
    choose_radio,
    choose_selectbox,
    clear_durable_browser_state,
    click_button,
    confirm_intake_reading,
    lookup_stub_company,
    save_step_screenshot,
    seed_confirmed_boundary_semantics,
    start_uploaded_coverage_analysis,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e

COACH = ".st-key-cel_onboarding_coach"
SPOTLIGHT = "#cel-onboarding-spotlight"
LATER = re.compile(r"^(稍後再說|Not now)$")
START = re.compile(r"^(開始|Start)$")
FINISH = re.compile(r"^(完成|Finish)$")

CLEAN_CSV = (
    "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
    "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
    "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
)

FORBIDDEN_IN_COACH = (
    "不是已確定的法律結論",
    "待覆核",
    "系統無法安全辨識",
    "可以安全辨識的部分",
    "排除、待確認或暫緩",
    "不是 0 排放",
    "這次不納入",
    "適用要求與重要時程",
    "名詞解釋",
    "Glossary",
    "下一步",
    "Next",
    "上一步",
)


def _csv_path() -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / "qa_onboarding_activity.csv"
    path.write_text(CLEAN_CSV, encoding="utf-8")
    return path


def _open_welcome(page) -> None:
    base = page._cel_base_url  # type: ignore[attr-defined]
    for _ in range(3):
        page.context.clear_cookies()
        _goto_app(page, base)
        clear_durable_browser_state(page)
        # Drop the previous Streamlit session so a completed tour cannot hydrate
        # back from cookies after localStorage was cleared.
        page.context.clear_cookies()
        _goto_app(page, base)
        page.wait_for_selector("text=Carbon Evidence Ledger", timeout=30_000)
        dialog = page.get_by_role("dialog")
        try:
            dialog.first.wait_for(state="visible", timeout=8_000)
            return
        except Exception:  # noqa: BLE001 - retry a fully new session
            continue
    page.get_by_role("dialog").first.wait_for(state="visible", timeout=20_000)


def _reload_same_browser(page) -> None:
    """Reload without clearing localStorage, as a customer refresh would."""
    base = page._cel_base_url  # type: ignore[attr-defined]
    _goto_app(page, base)
    page.wait_for_selector("text=Carbon Evidence Ledger", timeout=30_000)


def _current_step(page) -> str:
    return page.evaluate(
        """(sel) => {
          const host = document.querySelector(sel);
          const anchor = host && host.querySelector('[data-cel-coach-config]');
          return anchor ? anchor.getAttribute('data-cel-coach-index') : '';
        }""",
        COACH,
    )


def _assert_no_misplaced_highlight(page) -> None:
    """No target on this page means no box at all — never a stale one."""
    page.wait_for_function(
        f"""() => {{
          const host = document.querySelector('{COACH}');
          if (host && host.getAttribute('data-cel-coach-ready') === '1') {{
            return false;
          }}
          return document.querySelector('{SPOTLIGHT}') === null;
        }}""",
        timeout=20_000,
    )
    assert page.locator(SPOTLIGHT).count() == 0


def _start_tour(page) -> None:
    _open_welcome(page)
    page.get_by_role("button", name=START).first.click(force=True)
    wait_streamlit_idle(page)
    dialog = page.locator('[data-testid="stDialog"]')
    if dialog.count():
        dialog.first.wait_for(state="hidden", timeout=15_000)


def _coach_state(page) -> dict:
    return page.evaluate(
        """(sel) => {
          const hosts = [...document.querySelectorAll(sel)];
          let host = null;
          for (const node of hosts) {
            if (node.getAttribute('data-cel-coach-ready') === '1') host = node;
          }
          if (!host) host = hosts[hosts.length - 1] || hosts[0];
          if (!host) return {present: false};
          const anchor = host.querySelector('[data-cel-coach-config]');
          const rect = host.getBoundingClientRect();
          const spot = document.getElementById('cel-onboarding-spotlight');
          const spotRect = spot ? spot.getBoundingClientRect() : null;
          return {
            present: true,
            hostCount: hosts.length,
            ready: host.getAttribute('data-cel-coach-ready') === '1',
            placement: host.getAttribute('data-cel-coach-placement') || '',
            step: anchor ? anchor.getAttribute('data-cel-coach-index') : '',
            id: anchor ? anchor.getAttribute('data-cel-coach-step') : '',
            text: host.innerText || '',
            buttons: host.querySelectorAll('button').length,
            clipped: host.scrollHeight > host.clientHeight + 2,
            overlap: (() => {
              const card = host.querySelector('.cel-coach-body');
              const btn = host.querySelector('button');
              if (!card || !btn) return false;
              const a = card.getBoundingClientRect();
              const b = btn.getBoundingClientRect();
              return b.top < a.bottom - 1;
            })(),
            rect: {
              left: rect.left,
              top: rect.top,
              right: rect.right,
              bottom: rect.bottom,
            },
            spotlight: spotRect
              ? {
                  left: spotRect.left,
                  top: spotRect.top,
                  width: spotRect.width,
                  height: spotRect.height,
                  pointerEvents: getComputedStyle(spot).pointerEvents,
                  radius: getComputedStyle(spot).borderTopLeftRadius,
                }
              : null,
            viewport: {w: window.innerWidth, h: window.innerHeight},
            geometry: (() => {
              const hostBox = host.getBoundingClientRect();
              const cfg = JSON.parse(
                anchor.getAttribute('data-cel-coach-config') || '{}'
              );
              const selectors = cfg.selectors || [];
              let target = null;
              for (const sel of selectors) {
                try {
                  const node = document.querySelector(sel);
                  if (node) {
                    const named = node.closest("[class*='st-key-cel_onb_']") || node;
                    const r = named.getBoundingClientRect();
                    if (r.width >= 8 && r.height >= 8) { target = named; break; }
                  }
                } catch (e) {}
              }
              const overlap = (a, b) => {
                const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
                const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
                return w > 0 && h > 0 ? w * h : 0;
              };
              const contentBox = (el) => {
                let union = null;
                const add = (r) => {
                  if (!r || r.width < 1 || r.height < 1) return;
                  if (!union) {
                    union = {
                      left: r.left, top: r.top,
                      right: r.right, bottom: r.bottom
                    };
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
                  const r = range.getBoundingClientRect();
                  const parent = node.parentElement;
                  let display = '';
                  let fontSize = 16;
                  try {
                    if (parent) {
                      const style = window.getComputedStyle(parent);
                      display = String(style.display || '');
                      fontSize = parseFloat(style.fontSize) || 16;
                    }
                  } catch (errStyle) {}
                  if (r.width > window.innerWidth * 0.7) {
                    const text = String(node.nodeValue || '').trim();
                    const hasCJK = /[\u4e00-\u9fff]/.test(text);
                    const inkW = Math.min(
                      r.width,
                      Math.max(8, text.length * fontSize * (hasCJK ? 1.05 : 0.7))
                    );
                    add({
                      left: r.left, top: r.top,
                      right: r.left + inkW, bottom: r.bottom
                    });
                    continue;
                  }
                  add(r);
                }
                for (const control of el.querySelectorAll(
                  "button, input, textarea, select, "
                  + "[data-testid='stAlert'], [data-testid='stFileUploader']"
                )) {
                  const cr = control.getBoundingClientRect();
                  if (cr.width > window.innerWidth * 0.7) {
                    const label = String(
                      control.innerText || control.value || ""
                    ).trim();
                    const ctlInk = Math.min(
                      cr.width,
                      Math.max(8, (label.length || 8) * 14 * 0.75)
                    );
                    add({
                      left: cr.left, top: cr.top,
                      right: cr.left + ctlInk, bottom: cr.bottom
                    });
                    continue;
                  }
                  add(cr);
                }
                return union || el.getBoundingClientRect();
              };
              let overlapTarget = 0;
              let tBox = null;
              if (target) {
                tBox = contentBox(target);
                overlapTarget = overlap(hostBox, tBox);
              }
              const controls = [...document.querySelectorAll(
                "input, textarea, select, button, "
                + "[data-testid='stFileUploader'], [data-testid='stAlert']"
              )].filter((el) => {
                if (!el.getBoundingClientRect) return false;
                if (host.contains(el)) return false;
                if (target && target.contains(el)) return false;
                if (el.closest('[data-testid="stHeader"]')) return false;
                if (el.closest('[data-testid="stToolbar"]')) return false;
                if (el.closest('[data-testid="stStatusWidget"]')) return false;
                const r = el.getBoundingClientRect();
                return r.width >= 8 && r.height >= 8;
              });
              let overlapControls = 0;
              for (const el of controls) {
                overlapControls += overlap(hostBox, el.getBoundingClientRect());
              }
              return {
                overlapTarget,
                overlapControls,
                hostBox: {
                  left: hostBox.left, top: hostBox.top,
                  right: hostBox.right, bottom: hostBox.bottom
                },
                targetBox: tBox && {
                  left: tBox.left, top: tBox.top,
                  right: tBox.right, bottom: tBox.bottom
                }
              };
            })(),
          };
        }""",
        COACH,
    )


def _wait_for_step(page, step: int, *, timeout: int = 30_000) -> dict:
    page.wait_for_function(
        """([sel, step]) => {
          const host = document.querySelector(sel);
          if (!host) return false;
          if (host.getAttribute('data-cel-coach-ready') !== '1') return false;
          const anchor = host.querySelector('[data-cel-coach-config]');
          return !!anchor && anchor.getAttribute('data-cel-coach-index') === step;
        }""",
        arg=[COACH, str(step)],
        timeout=timeout,
    )
    return _coach_state(page)


def _switch_language(page, token: str) -> None:
    header = page.locator('[data-testid="stHeader"]')
    option = header.get_by_text(token, exact=True)
    if option.count() == 0:
        option = page.get_by_text(token, exact=True)
    if option.count() == 0:
        option = page.get_by_role("radio", name=token)
    if option.count() == 0:
        option = page.get_by_role("button", name=re.compile(rf"^{token}$"))
    option.first.click(force=True)
    wait_streamlit_idle(page)


def _advance_company_setup_until_upload(page, *, timeout_s: float = 180.0) -> None:
    """Walk the live company-setup wizard until the upload page exists."""
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if page.locator("[data-testid='stFileUploader']").count():
            return
        review_done = page.get_by_role(
            "button", name=re.compile(r"查看目前結果|View current results")
        )
        if review_done.count() and review_done.first.is_visible():
            wait_streamlit_idle(page)
            if page.locator("[data-testid='stFileUploader']").count():
                return
            reopen = page.get_by_role(
                "button", name=re.compile(r"操作教學|Tutorial")
            )
            if reopen.count():
                reopen.first.click(force=True)
                wait_streamlit_idle(page)
            continue
        fac = page.get_by_role("button", name=re.compile(r"是，\d+ 個都正確"))
        cont = page.get_by_role("button", name=re.compile(r"^繼續$"))
        continue_ready = bool(
            cont.count() and cont.first.is_visible() and cont.first.is_enabled()
        )
        if fac.count() and fac.first.is_visible() and not continue_ready:
            fac.first.click(force=True)
            wait_streamlit_idle(page)
            continue
        ack = page.get_by_text("我已確認報導年度、開始日與結束日", exact=True)
        if ack.count() and ack.first.is_visible():
            ack.first.click()
        name = page.get_by_label(re.compile(r"確認人姓名|Confirmer name"))
        if name.count():
            current = name.first.input_value()
            if not str(current or "").strip():
                name.first.fill("王小明")
        title = page.get_by_label(re.compile(r"職稱|Job title"))
        if title.count():
            current = title.first.input_value()
            if not str(current or "").strip():
                title.first.fill("永續管理師")
        relation = page.get_by_text("這筆政府紀錄與本公司實際據點的關係為何？")
        if relation.count():
            primary = page.locator(".st-key-cel_boundary_footer").get_by_role(
                "button", name="儲存並繼續", exact=True
            )
            if primary.count() and not primary.first.is_enabled():
                choose_selectbox(
                    page,
                    "這筆政府紀錄與本公司實際據點的關係為何？",
                    "這筆登記不屬於本公司",
                )
                wait_streamlit_idle(page)
                basis = page.get_by_label(re.compile(r"判定依據"))
                if basis.count():
                    basis.first.fill("與本公司營運無關")
                    wait_streamlit_idle(page)
        if page.get_by_text("確認 IFRS 永續揭露涵蓋範圍", exact=True).count():
            choose_radio(page, "個別財務報表")
        footer = page.locator(".st-key-cel_boundary_footer")
        clicked = False
        for label in (
            "確認此報導範圍",
            "儲存報導基礎",
            "在本機工作區確認此範圍",
            "儲存並繼續",
            "繼續",
        ):
            btn = footer.get_by_role("button", name=label, exact=True)
            if btn.count() and btn.first.is_visible() and btn.first.is_enabled():
                btn.first.scroll_into_view_if_needed()
                btn.first.click(force=True)
                wait_streamlit_idle(page)
                clicked = True
                break
        if clicked:
            continue
        cont = page.get_by_role("button", name=re.compile(r"^繼續$"))
        if cont.count() and cont.first.is_visible() and cont.first.is_enabled():
            cont.first.click(force=True)
            wait_streamlit_idle(page)
            continue
        skip_ifrs = page.get_by_role("button", name=re.compile(r"^繼續$"))
        if (
            page.get_by_text("本期不需確認 IFRS", exact=False).count()
            and skip_ifrs.count()
        ):
            skip_ifrs.first.click(force=True)
            wait_streamlit_idle(page)
            continue
        wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_onboarding_setup_stuck")
    raise AssertionError("company setup never reached the upload page")


def _wait_for_scene(page, scene_id: str, *, timeout: int = 60_000) -> dict:
    page.wait_for_function(
        """([sel, scene]) => {
          const hosts = [...document.querySelectorAll(sel)];
          return hosts.some((host) => {
            if (host.getAttribute('data-cel-coach-ready') !== '1') return false;
            const anchor = host.querySelector('[data-cel-coach-config]');
            return !!anchor && anchor.getAttribute('data-cel-coach-step') === scene;
          });
        }""",
        arg=[COACH, scene_id],
        timeout=timeout,
    )
    return _coach_state(page)


def _assert_within_viewport(state: dict) -> None:
    rect = state["rect"]
    viewport = state["viewport"]
    assert rect["left"] >= -1, rect
    assert rect["top"] >= -1, rect
    assert rect["right"] <= viewport["w"] + 1, rect
    assert rect["bottom"] <= viewport["h"] + 1, rect


def _assert_coachmark_is_small_and_clean(state: dict, *, step: int) -> None:
    assert state["ready"] is True
    assert state["step"] == str(step)
    _assert_within_viewport(state)
    text = state["text"]
    assert f"第 {step}／5 步" in text or f"Step {step} of 5" in text
    for phrase in FORBIDDEN_IN_COACH:
        assert phrase not in text, phrase
    # Progress, title and one line only: 稍後再說 lives on the welcome modal
    # and 完成 only on the last step, so nothing covers the copy.
    assert "稍後再說" not in text and "Not now" not in text
    assert state["buttons"] == (1 if step >= 5 else 0), state["buttons"]
    assert state["clipped"] is False, "coachmark copy is clipped"
    assert state["overlap"] is False, "a button overlaps the coachmark copy"
    spotlight = state["spotlight"]
    assert spotlight is not None, "spotlight missing while coachmark is ready"
    assert spotlight["pointerEvents"] == "none"
    assert spotlight["radius"].startswith("14")
    assert spotlight["width"] > 8 and spotlight["height"] > 8
    geometry = state.get("geometry") or {}
    assert geometry.get("overlapTarget", 0) == 0, (
        state.get("placement"),
        state.get("rect"),
        geometry,
    )
    assert geometry.get("overlapControls", 0) == 0, geometry


def test_welcome_is_short_and_unmounts_on_start(page) -> None:
    _open_welcome(page)
    body = visible_text(page)
    assert "完成第一筆碳排計算" in body
    assert "Excel" in body
    assert "下一步" not in body
    for phrase in FORBIDDEN_IN_COACH:
        assert phrase not in body, phrase
    # No screenshot-based tutorial anywhere in the runtime DOM.
    assert page.locator(".cel-tour-shot, [data-cel-tour-shot]").count() == 0
    assert page.locator('img[src^="data:image/png;base64"]').count() == 0
    save_step_screenshot(page, "qa_onboarding_welcome_zh")

    page.get_by_role("button", name=LATER).first.click(force=True)
    wait_streamlit_idle(page)
    for _ in range(3):
        if page.get_by_text("Start company setup", exact=False).count():
            break
        _switch_language(page, "EN")
    page.get_by_role("button", name=re.compile(r"Tutorial")).first.click(force=True)
    wait_streamlit_idle(page)
    page.get_by_role("dialog").first.wait_for(state="visible", timeout=20_000)
    en_body = visible_text(page)
    assert "Complete your first emissions calculation" in en_body
    save_step_screenshot(page, "qa_onboarding_welcome_en")

    page.get_by_role("button", name=START).first.click(force=True)
    wait_streamlit_idle(page)
    page.locator('[data-testid="stDialog"]').first.wait_for(
        state="hidden", timeout=15_000
    )
    en_state = _wait_for_step(page, 1)
    _assert_coachmark_is_small_and_clean(en_state, step=1)
    assert "Start company setup" in en_state["text"]
    save_step_screenshot(page, "qa_onboarding_1a_start_setup_en")
    _switch_language(page, "繁中")
    state = _wait_for_step(page, 1)
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert "開始公司設定" in state["text"]
    save_step_screenshot(page, "qa_onboarding_1a_start_setup_zh")
    save_step_screenshot(page, "qa_onboarding_step1_company_setup")
    assert_no_app_errors(page)


def test_not_now_removes_every_overlay(page) -> None:
    _open_welcome(page)
    page.get_by_role("button", name=LATER).first.click(force=True)
    wait_streamlit_idle(page)
    page.locator('[data-testid="stDialog"]').first.wait_for(
        state="hidden", timeout=15_000
    )
    assert page.locator(SPOTLIGHT).count() == 0
    coach = page.locator(COACH)
    if coach.count():
        assert not coach.first.is_visible()
    # A dismissed customer is not pushed back into the flow on navigation.
    page.get_by_role("link", name=re.compile(NAV_EVIDENCE)).first.click()
    wait_streamlit_idle(page)
    assert page.locator(SPOTLIGHT).count() == 0
    assert_no_app_errors(page)


def test_steps_advance_only_from_real_product_actions(
    page, e2e_company_workspace_dir
) -> None:
    # Confirming identity is not enough: the customer still has to finish
    # the live company-setup screens, including ReportingPeriod and scope.
    _start_tour(page)
    state = _wait_for_step(page, 1)
    _assert_coachmark_is_small_and_clean(state, step=1)

    click_button(page, "開始公司設定")
    wait_streamlit_idle(page)
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    wait_streamlit_idle(page)
    _advance_company_setup_until_upload(page, timeout_s=240.0)
    save_step_screenshot(page, "qa_onboarding_after_setup")
    try:
        state = _wait_for_step(page, 2, timeout=60_000)
    except Exception as exc:
        raise AssertionError(_coach_state(page)) from exc
    _assert_coachmark_is_small_and_clean(state, step=2)
    assert "上傳活動資料" in state["text"]
    uploader_present = page.locator('[data-testid="stFileUploader"]')
    assert uploader_present.count() >= 1, "step 2 must land on the upload page"
    save_step_screenshot(page, "qa_onboarding_step2_upload")
    save_step_screenshot(page, "qa_onboarding_step2_upload_zh")
    _switch_language(page, "EN")
    en_state = _wait_for_step(page, 2, timeout=60_000)
    _assert_coachmark_is_small_and_clean(en_state, step=2)
    save_step_screenshot(page, "qa_onboarding_step2_upload_en")
    _switch_language(page, "繁中")

    # Merely opening the upload page does not advance past step 2.
    page.get_by_role("link", name=re.compile(NAV_EVIDENCE)).first.click()
    wait_streamlit_idle(page)
    state = _wait_for_step(page, 2, timeout=60_000)
    _assert_coachmark_is_small_and_clean(state, step=2)

    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(_csv_path()))
    wait_streamlit_idle(page, timeout=60)
    page.get_by_text(re.compile(r"資料已讀取|File read successfully")).first.wait_for(
        state="visible", timeout=30_000
    )
    # Step 3 only appears while the confirmation queue still has questions.
    queue_open = page.get_by_role(
        "button", name=re.compile(r"確認並前往下一題|Confirm and continue")
    ).count()
    if queue_open:
        state = _wait_for_step(page, 3, timeout=60_000)
        _assert_coachmark_is_small_and_clean(state, step=3)
        assert "確認資料內容" in state["text"]
        # The spotlight covers the real confirm control, not just the card.
        assert page.evaluate(
            """() => {
              const spot = document.getElementById('cel-onboarding-spotlight');
              const anchor = document.querySelector(
                "[data-cel-tour-target='recognition-apply']"
              );
              if (!spot || !anchor) return false;
              const s = spot.getBoundingClientRect();
              const buttons = Array.from(document.querySelectorAll('button'));
              const target = buttons.find((b) => {
                const r = b.getBoundingClientRect();
                return r.width > 0 && r.height > 0
                  && r.top >= s.top - 24 && r.bottom <= s.bottom + 24;
              });
              return !!target;
            }"""
        ), "step 3 spotlight must include the actionable confirm control"
        save_step_screenshot(page, "qa_onboarding_step3_review")
        save_step_screenshot(page, "qa_onboarding_step3_review_zh")
        _switch_language(page, "EN")
        save_step_screenshot(page, "qa_onboarding_step3_review_en")
        _switch_language(page, "繁中")

    confirm_intake_reading(page)
    _switch_language(page, "繁中")
    state = _wait_for_step(page, 4, timeout=90_000)
    _assert_coachmark_is_small_and_clean(state, step=4)
    assert (
        "開始計算" in state["text"]
        or "檢查計算範圍" in state["text"]
        or "Start calculation" in state["text"]
        or "Review calculation coverage" in state["text"]
    )
    save_step_screenshot(page, "qa_onboarding_step4_coverage_zh")
    save_step_screenshot(page, "qa_onboarding_step4_start_analysis_zh")
    save_step_screenshot(page, "qa_onboarding_step4_start_calculation")
    _switch_language(page, "EN")
    save_step_screenshot(page, "qa_onboarding_step4_coverage_en")
    save_step_screenshot(page, "qa_onboarding_step4_start_analysis_en")
    _switch_language(page, "繁中")

    # The real 開始分析 button owns the transition; no tutorial stand-in.
    start_uploaded_coverage_analysis(page)
    _switch_language(page, "繁中")
    state = _wait_for_step(page, 5, timeout=120_000)
    _assert_coachmark_is_small_and_clean(state, step=5)
    assert "查看計算結果" in state["text"] or "View your results" in state["text"]
    save_step_screenshot(page, "qa_onboarding_step5_results")
    save_step_screenshot(page, "qa_onboarding_step5_results_zh")
    _switch_language(page, "EN")
    en5 = _wait_for_step(page, 5, timeout=60_000)
    _assert_coachmark_is_small_and_clean(en5, step=5)
    save_step_screenshot(page, "qa_onboarding_step5_results_en")
    _switch_language(page, "繁中")

    # 完成 removes spotlight, coachmark and dim, and keeps the results page.
    page.locator(COACH).get_by_role("button", name=FINISH).first.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_function(
        f"() => document.querySelector('{SPOTLIGHT}') === null",
        timeout=15_000,
    )
    coach = page.locator(COACH)
    if coach.count():
        assert not coach.first.is_visible()
    hero = page.locator('[data-cel-hero-emissions="1"]')
    assert hero.count() >= 1, "results page must stay after 完成"
    save_step_screenshot(page, "qa_onboarding_finished")
    assert_no_app_errors(page)


def test_step_survives_route_changes_without_a_misplaced_box(page) -> None:
    _start_tour(page)
    _wait_for_step(page, 1)
    # The upload page has no step 1 target, so the hint hides rather than
    # framing something else. The step itself is kept.
    page.get_by_role("link", name=re.compile(NAV_EVIDENCE)).first.click()
    wait_streamlit_idle(page)
    _assert_no_misplaced_highlight(page)
    assert _current_step(page) == "1"

    # 操作教學 routes back to the page that owns the step.
    page.get_by_role("button", name=re.compile(r"操作教學|Tutorial")).first.click(
        force=True
    )
    wait_streamlit_idle(page)
    state = _wait_for_step(page, 1, timeout=60_000)
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert_no_app_errors(page)


def test_step_survives_language_changes(page) -> None:
    _start_tour(page)
    _wait_for_step(page, 1)
    _switch_language(page, "EN")
    state = _wait_for_step(page, 1, timeout=60_000)
    assert "Complete company setup" not in state["text"]
    assert "Start company setup" in state["text"]
    assert "Step 1 of 5" in state["text"]
    save_step_screenshot(page, "qa_onboarding_1a_start_setup_en")
    assert_no_app_errors(page)


def test_step_one_follows_the_customer_into_company_setup(page) -> None:
    _start_tour(page)
    _wait_for_step(page, 1)
    click_button(page, "開始公司設定")
    wait_streamlit_idle(page)
    state = _wait_for_step(page, 1, timeout=60_000)
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert "查詢公司" in state["text"]
    assert "8 位" in state["text"] or "統一編號" in state["text"]
    save_step_screenshot(page, "qa_onboarding_1b_ubn_lookup_zh")
    _switch_language(page, "EN")
    _wait_for_scene(page, "ubn_lookup", timeout=60_000)
    save_step_screenshot(page, "qa_onboarding_1b_ubn_lookup_en")
    _switch_language(page, "繁中")
    assert_no_app_errors(page)


def test_company_setup_action_scenes_describe_the_current_control(page) -> None:
    """Walk the live company-setup form and assert each action scene."""
    _start_tour(page)
    _wait_for_scene(page, "start_setup")
    click_button(page, "開始公司設定")
    wait_streamlit_idle(page)
    state = _wait_for_scene(page, "ubn_lookup")
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert "查詢公司" in state["text"]

    field = page.get_by_label(re.compile(r"統一編號|Unified business number"))
    field.first.fill(STUB_ALIGNED_UBN)
    click_button(page, "查詢公司")
    wait_streamlit_idle(page)
    state = _wait_for_scene(page, "company_confirmation", timeout=60_000)
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert "核對公司資料" in state["text"]
    assert "這是我的公司" in state["text"]
    assert "確認公司、報導期間與計算範圍。" not in state["text"]
    assert state["placement"] in {
        "right",
        "left",
        "top",
        "bottom",
        "corner-tr",
        "corner-br",
        "corner-tl",
        "corner-bl",
        "dock-right",
    }
    year = page.locator('input[aria-label="要評估哪一年度？"]')
    if year.count() and state["rect"]:
        year_box = year.first.bounding_box()
        if year_box:
            card = state["rect"]
            overlap_w = min(card["right"], year_box["x"] + year_box["width"]) - max(
                card["left"], year_box["x"]
            )
            overlap_h = min(card["bottom"], year_box["y"] + year_box["height"]) - max(
                card["top"], year_box["y"]
            )
            assert overlap_w <= 0 or overlap_h <= 0, (
                "coachmark covers the reporting-year field",
                state["placement"],
                card,
                year_box,
            )
    save_step_screenshot(page, "qa_onboarding_1c_company_confirmation_zh")

    click_button(page, "這是我的公司")
    wait_streamlit_idle(page)
    state = {}
    for _ in range(20):
        state = _coach_state(page)
        if state.get("ready") and state.get("id") == "company_details":
            break
        if state.get("ready") and str(state.get("step")) == "2":
            break
        if page.locator("[data-testid='stFileUploader']").count():
            break
        wait_streamlit_idle(page)
    if str(state.get("step")) == "2" or page.locator(
        "[data-testid='stFileUploader']"
    ).count():
        save_step_screenshot(page, "qa_onboarding_after_1c_upload_ready")
        assert_no_app_errors(page)
        return
    if not (state.get("ready") and state.get("id") == "company_details"):
        save_step_screenshot(page, "qa_onboarding_after_1c_not_details")
        assert_no_app_errors(page)
        return
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert "補充公司資料" in state["text"]
    save_step_screenshot(page, "qa_onboarding_1d_basic_information_zh")

    click_button(page, "繼續")
    wait_streamlit_idle(page)
    state = {}
    for _ in range(20):
        state = _coach_state(page)
        if state.get("ready") and str(state.get("step")) in {"1", "2"}:
            break
        if page.locator("[data-testid='stFileUploader']").count():
            break
        wait_streamlit_idle(page)
    if str(state.get("step")) == "2" or page.locator(
        "[data-testid='stFileUploader']"
    ).count():
        save_step_screenshot(page, "qa_onboarding_after_1d_upload_ready")
        assert_no_app_errors(page)
        return
    if not state.get("ready"):
        save_step_screenshot(page, "qa_onboarding_after_1d_stuck")
        raise AssertionError(state)
    _assert_coachmark_is_small_and_clean(state, step=1)
    scene = state["id"]
    if scene == "additional_information":
        save_step_screenshot(page, "qa_onboarding_1e_additional_information_zh")
        click_button(page, "繼續")
        wait_streamlit_idle(page)
        state = _wait_for_step(page, 1, timeout=60_000)
        scene = state["id"]
    assert scene in {"taiwan_facilities", "facilities_continue"}
    save_step_screenshot(page, f"qa_onboarding_1f_{scene}_zh")
    facilities_confirm = page.get_by_role(
        "button", name=re.compile(r"是，\d+ 個都正確")
    )
    if facilities_confirm.count() and facilities_confirm.first.is_visible():
        facilities_confirm.first.click()
        wait_streamlit_idle(page)
        state = _wait_for_scene(page, "facilities_continue", timeout=60_000)
        _assert_coachmark_is_small_and_clean(state, step=1)
        save_step_screenshot(page, "qa_onboarding_1g_facilities_continue_zh")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    state = _wait_for_scene(page, "reporting_period", timeout=90_000)
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert "報導期間" in state["text"]
    save_step_screenshot(page, "qa_onboarding_1h_reporting_period_zh")
    page.get_by_text("我已確認報導年度、開始日與結束日", exact=True).click()
    footer = page.locator(".st-key-cel_boundary_footer")
    save = footer.get_by_role("button", name="儲存並繼續", exact=True)
    if save.count():
        save.first.scroll_into_view_if_needed()
        save.first.click()
        wait_streamlit_idle(page)
        state = _coach_state(page)
        if state.get("ready") and str(state.get("step")) == "1":
            _assert_coachmark_is_small_and_clean(state, step=1)
            save_step_screenshot(page, f"qa_onboarding_1i_{state['id']}_zh")
            nxt = footer.get_by_role("button", name="儲存並繼續", exact=True)
            if nxt.count() and nxt.first.is_visible():
                nxt.first.scroll_into_view_if_needed()
                nxt.first.click()
                wait_streamlit_idle(page)
                state = _coach_state(page)
                if state.get("ready") and str(state.get("step")) == "1":
                    save_step_screenshot(page, f"qa_onboarding_1j_{state['id']}_zh")
    assert_no_app_errors(page)


def test_company_confirmation_english_screenshots(page) -> None:
    try:
        _start_tour(page)
        click_button(page, "開始公司設定")
        wait_streamlit_idle(page)
        _wait_for_scene(page, "ubn_lookup")
        field = page.get_by_label(re.compile(r"統一編號|Unified business number"))
        field.first.fill(STUB_ALIGNED_UBN)
        click_button(page, "查詢公司")
        wait_streamlit_idle(page)
        _wait_for_scene(page, "company_confirmation", timeout=60_000)
        _switch_language(page, "EN")
        state = _wait_for_scene(page, "company_confirmation", timeout=60_000)
        _assert_coachmark_is_small_and_clean(state, step=1)
        assert "Confirm the company" in state["text"]
        save_step_screenshot(page, "qa_onboarding_1c_company_confirmation_en")
        page.get_by_role(
            "button", name=re.compile(r"This is my company")
        ).first.click(force=True)
        wait_streamlit_idle(page)
        for _ in range(20):
            state = _coach_state(page)
            if state.get("ready") and state.get("id") == "company_details":
                break
            if state.get("ready") and str(state.get("step")) == "2":
                break
            wait_streamlit_idle(page)
        if state.get("ready") and state.get("id") == "company_details":
            save_step_screenshot(page, "qa_onboarding_1d_basic_information_en")
        assert_no_app_errors(page)
    finally:
        try:
            _switch_language(page, "繁中")
        except Exception:  # noqa: BLE001 - cleanup must not mask the test error
            pass


def test_dismissed_state_survives_a_refresh(page) -> None:
    _open_welcome(page)
    page.get_by_role("button", name=LATER).first.click(force=True)
    wait_streamlit_idle(page)
    _reload_same_browser(page)
    assert page.locator(SPOTLIGHT).count() == 0
    dialog = page.locator('[data-testid="stDialog"]')
    if dialog.count():
        assert not dialog.first.is_visible(), "dismissed customer must not replay"
    # The manual entry point still works.
    page.get_by_role("button", name=re.compile(r"操作教學|Tutorial")).first.click(
        force=True
    )
    wait_streamlit_idle(page)
    assert_no_app_errors(page)


def test_welcome_does_not_flash_before_hydration(page) -> None:
    base = page._cel_base_url  # type: ignore[attr-defined]
    _goto_app(page, base)
    clear_durable_browser_state(page)
    _goto_app(page, base)
    page.get_by_role("dialog").first.wait_for(state="visible", timeout=20_000)
    page.get_by_role("button", name=START).first.click(force=True)
    wait_streamlit_idle(page)
    _reload_same_browser(page)
    # Started, not completed: the flow resumes without the welcome modal.
    dialog = page.locator('[data-testid="stDialog"]')
    if dialog.count():
        assert not dialog.first.is_visible()
    assert _current_step(page) in {"1", "2", "3", "4", "5"}
    assert_no_app_errors(page)


def test_missing_target_never_paints_a_misplaced_highlight(page) -> None:
    _start_tour(page)
    _wait_for_step(page, 1)
    # Remove the anchored entry: the highlight must disappear, not relocate.
    page.evaluate(
        """() => {
          const nodes = document.querySelectorAll(
            "[class*='st-key-cel_onb_start'], .st-key-onboard_start_setup"
          );
          nodes.forEach((el) => {
            if (el && el.parentNode) el.parentNode.removeChild(el);
          });
        }"""
    )
    page.wait_for_function(
        f"""() => {{
          const host = document.querySelector('{COACH}');
          if (!host) return true;
          return host.getAttribute('data-cel-coach-ready') !== '1';
        }}""",
        timeout=15_000,
    )
    assert page.locator(SPOTLIGHT).count() == 0
    assert_no_app_errors(page)


@pytest.mark.parametrize(
    "width,height",
    [(1366, 768), (1440, 900), (1440, 1100)],
)
def test_coachmark_fits_supported_viewports(page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    _start_tour(page)
    state = _wait_for_step(page, 1, timeout=60_000)
    _assert_coachmark_is_small_and_clean(state, step=1)
    assert state["placement"] in {
        "bottom",
        "top",
        "left",
        "right",
        "corner-tr",
        "corner-br",
        "corner-tl",
        "corner-bl",
        "dock-right",
    }
    save_step_screenshot(page, f"qa_onboarding_coach_{width}x{height}")
    save_step_screenshot(page, f"qa_onboarding_{width}x{height}")
    assert_no_app_errors(page)


def test_reduced_motion_keeps_positioning_usable(page) -> None:
    page.emulate_media(reduced_motion="reduce")
    try:
        _start_tour(page)
        state = _wait_for_step(page, 1, timeout=60_000)
        _assert_coachmark_is_small_and_clean(state, step=1)
    finally:
        page.emulate_media(reduced_motion="no-preference")
    assert_no_app_errors(page)


def test_applicability_hint_appears_once(page, e2e_company_workspace_dir) -> None:
    seed_confirmed_boundary_semantics(e2e_company_workspace_dir)
    _open_welcome(page)
    page.get_by_role("button", name=LATER).first.click(force=True)
    wait_streamlit_idle(page)
    click_button(page, "開始公司設定")
    wait_streamlit_idle(page)
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    wait_streamlit_idle(page)
    hint = page.locator("[data-cel-page-hint='applicability']")
    seen_first = hint.count()
    # Leave and come back: the hint must not keep occupying the page.
    page.get_by_role("link", name=re.compile(NAV_EVIDENCE)).first.click()
    wait_streamlit_idle(page)
    page.get_by_role(
        "link", name=re.compile(r"適用要求|Requirements")
    ).first.click()
    wait_streamlit_idle(page)
    assert page.locator("[data-cel-page-hint='applicability']").count() == 0, (
        f"hint repeated after the first visit (first render: {seen_first})"
    )
    assert_no_app_errors(page)


def test_customer_chrome_has_no_global_glossary(page) -> None:
    _open_welcome(page)
    page.get_by_role("button", name=LATER).first.click(force=True)
    wait_streamlit_idle(page)
    for label in ("名詞解釋", "Glossary"):
        assert page.get_by_role("button", name=re.compile(rf"^{label}$")).count() == 0
    sidebar = page.locator('section[data-testid="stSidebar"]')
    if sidebar.count():
        sidebar_text = sidebar.inner_text()
        assert "名詞解釋" not in sidebar_text
        assert "Glossary" not in sidebar_text
    tutorial = page.get_by_role("button", name=re.compile(r"操作教學|Tutorial"))
    assert tutorial.count() >= 1
    save_step_screenshot(page, "qa_customer_navigation_without_glossary")
    assert_no_app_errors(page)
