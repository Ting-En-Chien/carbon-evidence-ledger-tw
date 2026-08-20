"""Stage 4.2G immersive guided-tour journeys."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook
from playwright.sync_api import expect

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    ARTIFACTS,
    STUB_ALIGNED_UBN,
    assert_no_app_errors,
    click_button,
    dismiss_tutorial_if_present,
    lookup_stub_company,
    open_evidence_workspace_tool,
    open_fresh_app,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)

from carbon_ledger.ui.tutorial_manifest import (  # noqa: E402
    ASSET_DIR,
    STEP_IDS,
    TOUR_STEP_COUNT,
    missing_or_empty_assets,
    production_asset_paths,
    step_by_index,
    tour_step_visual,
)

pytestmark = pytest.mark.e2e

REVIEW_SHOTS = (
    "qa_42g_tour_cover_desktop",
    "qa_42g_tour_step1_company",
    "qa_42g_tour_step2_upload",
    "qa_42g_tour_step3_results",
    "qa_42g_tour_step1_1366x768",
    "qa_42g_tour_step1_1440x900",
    "qa_42g_tour_step1_1440x1100",
    "qa_42g_tour_english",
    "qa_42g_tour_en_step1_company",
    "qa_42g_tour_en_step2_upload",
    "qa_42g_tour_en_step3_results",
    "qa_42g_tour_replay",
    "qa_42g_intake_upload_desktop",
)
SAMPLE_XLSX_NAME = "2026年2月能源使用.xlsx"
HIDE_CHROME = """
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stSidebarCollapsedControl"] {
  display: none !important;
}
section[data-testid="stSidebar"] { display: none !important; }
"""
STEP1_TEACHING_CHROME = (
    HIDE_CHROME
    + """
.cel-page-kicker,
.cel-page-title,
.cel-page-sub,
.cel-stepper,
.cel-learn-card {
  display: none !important;
}
[data-testid="stMarkdownContainer"]:has(.cel-page-kicker),
[data-testid="stMarkdownContainer"]:has(.cel-page-title),
[data-testid="stMarkdownContainer"]:has(.cel-page-sub),
[data-testid="stMarkdownContainer"]:has(.cel-stepper),
[data-testid="stMarkdownContainer"]:has(.cel-learn-card) {
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
}
"""
)
HIDE_CHROME_KEEP_SIDEBAR = """
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"] {
  display: none !important;
}
"""
FORBIDDEN_UI = (
    "qa_",
    "tut.",
    "activity_type",
    "canonical",
    "fingerprint",
    "schema",
    "parser",
    "尚未設定公司",
    "Company not set",
)


def _tour_overlay(page):
    return page.locator('[data-testid="stDialog"]').filter(
        has=page.locator(".cel-tour-root")
    )


def _tour_dialog(page):
    return _tour_overlay(page)


def _tour_card(page):
    return page.locator("section[role='dialog']").filter(
        has=page.locator(".cel-tour-root")
    )


_TOUR_DOM_DUMPED = False


def _dump_tour_dom(page) -> dict:
    """Print the live ancestor chain from .cel-tour-root once."""
    dump = page.evaluate(
        """() => {
          const root = document.querySelector('.cel-tour-root');
          const chain = [];
          let node = root;
          while (node && node !== document.documentElement) {
            const cs = window.getComputedStyle(node);
            const r = node.getBoundingClientRect();
            chain.push({
              tag: node.tagName,
              id: node.id || "",
              testid: node.getAttribute('data-testid') || "",
              role: node.getAttribute('role') || "",
              className: String(node.className || "").slice(0, 180),
              position: cs.position,
              inset: cs.inset,
              top: cs.top,
              right: cs.right,
              bottom: cs.bottom,
              left: cs.left,
              width: cs.width,
              height: cs.height,
              background: cs.backgroundColor,
              overflow: cs.overflow + '/' + cs.overflowY,
              box: {
                x: Math.round(r.left),
                y: Math.round(r.top),
                w: Math.round(r.width),
                h: Math.round(r.height),
              },
            });
            node = node.parentElement;
          }
          return {
            vw: window.innerWidth,
            vh: window.innerHeight,
            hasOverlayClass: !!document.querySelector(
              '.react-aria-ModalOverlay'
            ),
            chain,
          };
        }"""
    )
    print("TOUR_DOM_DUMP " + repr(dump))
    return dump


def _assert_opaque_tour_card(page) -> dict:
    global _TOUR_DOM_DUMPED
    _tour_overlay(page).first.wait_for(state="visible", timeout=15_000)
    _tour_card(page).first.wait_for(state="visible", timeout=15_000)
    if not _TOUR_DOM_DUMPED:
        _dump_tour_dom(page)
        _TOUR_DOM_DUMPED = True
    metrics = page.evaluate(
        """() => {
          const overlay = document.querySelector(
            '[data-testid="stDialog"]:has(.cel-tour-root)'
          );
          const card = document.querySelector(
            'section[role="dialog"]:has(.cel-tour-root)'
          );
          if (!overlay || !card) {
            return {ok: false, reason: 'missing-overlay-or-card'};
          }
          const ocs = window.getComputedStyle(overlay);
          const ccs = window.getComputedStyle(card);
          const parseRgba = (value) => {
            const m = String(value).match(/rgba?\\(([^)]+)\\)/);
            if (!m) return null;
            const p = m[1].split(',').map((s) => parseFloat(s.trim()));
            return {
              r: p[0],
              g: p[1],
              b: p[2],
              a: p.length > 3 ? p[3] : 1,
            };
          };
          const overlayColor = parseRgba(ocs.backgroundColor);
          const cardColor = parseRgba(ccs.backgroundColor);
          const or_ = overlay.getBoundingClientRect();
          const cr = card.getBoundingClientRect();
          const inset0 =
            (ocs.top === '0px' &&
              ocs.right === '0px' &&
              ocs.bottom === '0px' &&
              ocs.left === '0px') ||
            ocs.inset === '0px';
          const inside = (box, host) =>
            box.left >= host.left - 1 &&
            box.top >= host.top - 1 &&
            box.right <= host.right + 1 &&
            box.bottom <= host.bottom + 1;
          const body = document.querySelector(
            '[data-testid="stVerticalBlock"]:has([data-cel-tour-body="1"]):not(:has([data-cel-tour-footer="1"]))'
          );
          const footer = document.querySelector(
            '[data-testid="stVerticalBlock"]:has([data-cel-tour-footer="1"]):not(:has([data-cel-tour-body="1"]))'
          );
          const shot = document.querySelector('.cel-tour-shot');
          const title = card.querySelector('h1, h2, h3, [slot="title"]');
          const sampleFooter = footer
            ? footer.getBoundingClientRect()
            : null;
          const sampleShot = shot ? shot.getBoundingClientRect() : null;
          const sampleBody = body ? body.getBoundingClientRect() : null;
          const outsideX = 8;
          const outsideY = 8;
          const outsideInsideCard =
            outsideX >= cr.left &&
            outsideX <= cr.right &&
            outsideY >= cr.top &&
            outsideY <= cr.bottom;
          const hitX = outsideInsideCard ? window.innerWidth - 8 : outsideX;
          const hitY = outsideInsideCard ? 8 : outsideY;
          const hit = document.elementFromPoint(hitX, hitY);
          const hitOnOverlay = !!(
            hit && hit.closest('[data-testid="stDialog"]')
          );
          const hitOnCard = !!(
            hit && hit.closest('section[role="dialog"]')
          );
          const hitOnMainOnly = !!(
            hit &&
            hit.closest('section[data-testid="stMain"]') &&
            !hit.closest('[data-testid="stDialog"]')
          );
          let shotVisiblePx = 0;
          if (sampleShot && sampleBody) {
            const top = Math.max(sampleShot.top, sampleBody.top, 0);
            const bottom = Math.min(
              sampleShot.bottom,
              sampleBody.bottom,
              window.innerHeight
            );
            shotVisiblePx = Math.max(0, bottom - top);
          }
          const titleBox = title ? title.getBoundingClientRect() : null;
          return {
            ok: true,
            vw: window.innerWidth,
            vh: window.innerHeight,
            overlayPosition: ocs.position,
            overlayInset0: inset0,
            overlayWidth: or_.width,
            overlayHeight: or_.height,
            overlayBg: ocs.backgroundColor,
            overlayDark: !!(
              overlayColor &&
              overlayColor.a >= 0.35 &&
              overlayColor.a < 0.95 &&
              overlayColor.r <= 40 &&
              overlayColor.g <= 50 &&
              overlayColor.b <= 70
            ),
            cardWidth: cr.width,
            cardHeight: cr.height,
            cardBg: ccs.backgroundColor,
            cardOpaqueWhite: !!(
              cardColor &&
              cardColor.a >= 0.99 &&
              cardColor.r >= 250 &&
              cardColor.g >= 250 &&
              cardColor.b >= 250
            ),
            cardInsideOverlay: inside(cr, or_),
            overlayNearViewport:
              or_.width >= window.innerWidth * 0.95 &&
              or_.height >= window.innerHeight * 0.9,
            bodyContainsFooter: !!(body && footer && body.contains(footer)),
            footerContainsBody: !!(body && footer && footer.contains(body)),
            bodyInCard: !!(body && card.contains(body)),
            footerInCard: !!(footer && card.contains(footer)),
            footerBottom: sampleFooter ? sampleFooter.bottom : null,
            cardBottom: cr.bottom,
            hitOnOverlay,
            hitOnCard,
            hitOnMainOnly,
            hitTag: hit ? hit.tagName : null,
            shotVisiblePx,
            titleVisible: !!(
              titleBox &&
              titleBox.bottom > 0 &&
              titleBox.top < window.innerHeight &&
              titleBox.height > 8
            ),
            boxes: {
              overlay: {
                left: or_.left,
                top: or_.top,
                right: or_.right,
                bottom: or_.bottom,
                width: or_.width,
                height: or_.height,
              },
              card: {
                left: cr.left,
                top: cr.top,
                right: cr.right,
                bottom: cr.bottom,
                width: cr.width,
                height: cr.height,
              },
              shot: sampleShot,
              footer: sampleFooter,
              body: sampleBody,
              title: titleBox,
            },
          };
        }"""
    )
    assert metrics["ok"] is True, metrics
    assert metrics["overlayPosition"] == "fixed", metrics
    assert metrics["overlayInset0"] is True, metrics
    assert metrics["overlayNearViewport"] is True, metrics
    assert metrics["overlayDark"] is True, metrics
    assert metrics["cardOpaqueWhite"] is True, metrics
    assert metrics["cardWidth"] < metrics["overlayWidth"] - 8, metrics
    assert metrics["cardHeight"] < metrics["overlayHeight"] - 8, metrics
    assert metrics["cardInsideOverlay"] is True, metrics
    assert metrics["bodyContainsFooter"] is False, metrics
    assert metrics["footerContainsBody"] is False, metrics
    assert metrics["bodyInCard"] is True, metrics
    assert metrics["footerInCard"] is True, metrics
    if metrics["footerBottom"] is not None:
        assert metrics["footerBottom"] <= metrics["cardBottom"] + 2, metrics
    assert metrics["hitOnOverlay"] is True, metrics
    assert metrics["hitOnCard"] is False, metrics
    assert metrics["hitOnMainOnly"] is False, metrics
    host = metrics["boxes"]["card"]
    for name in ("shot", "footer"):
        box = metrics["boxes"].get(name)
        if not box:
            continue
        assert box["left"] >= host["left"] - 2, (name, box, host)
        assert box["top"] >= host["top"] - 2, (name, box, host)
        assert box["right"] <= host["right"] + 2, (name, box, host)
        assert box["bottom"] <= host["bottom"] + 2, (name, box, host)
    if metrics["vw"] <= 420:
        assert metrics["titleVisible"] is True, metrics
        assert metrics["shotVisiblePx"] >= 60, metrics
    return metrics


def _wait_hero_countup_stable(page, timeout: int = 20_000) -> None:
    page.wait_for_function(
        """() => {
          const el = document.querySelector("[data-cel-hero-emissions='1']");
          if (!el) return false;
          const target = parseFloat(el.getAttribute("data-cel-target") || "");
          const decimals = parseInt(
            el.getAttribute("data-cel-decimals") || "0",
            10
          );
          const raw = String(el.textContent || "")
            .replace(/\\u00a0/g, "")
            .replace(/\\s/g, "")
            .replace(/,/g, "");
          const shown = parseFloat(raw);
          if (!Number.isFinite(shown) || !Number.isFinite(target)) return false;
          if (shown <= 0) return false;
          const tol = 0.5 * Math.pow(10, -decimals);
          if (Math.abs(shown - target) > tol) {
            window.__celHeroWait = { value: null, since: 0 };
            return false;
          }
          const now = Date.now();
          const prev = window.__celHeroWait || { value: null, since: 0 };
          if (prev.value !== shown) {
            window.__celHeroWait = { value: shown, since: now };
            return false;
          }
          return now - prev.since >= 300;
        }""",
        timeout=timeout,
    )


def _assert_fully_in_viewport(locator, *, hit_test: bool = True) -> dict:
    locator.wait_for(state="visible", timeout=15_000)
    metrics = locator.evaluate(
        """el => {
          const r = el.getBoundingClientRect();
          const vw = window.innerWidth;
          const vh = window.innerHeight;
          const cx = r.left + r.width / 2;
          const cy = r.top + r.height / 2;
          const hit = document.elementFromPoint(cx, cy);
          const host = el.closest('button') || el;
          const hitHost = hit && (hit.closest('button') || hit);
          const sameControl = !!(
            hit && (host === hit || host.contains(hit) || hitHost === host)
          );
          return {
            left: r.left,
            top: r.top,
            right: r.right,
            bottom: r.bottom,
            width: r.width,
            height: r.height,
            vw,
            vh,
            fullyIn:
              r.left >= -0.5 &&
              r.top >= -0.5 &&
              r.right <= vw + 0.5 &&
              r.bottom <= vh + 0.5,
            occluded: !sameControl,
            hitTag: hit ? hit.tagName : null,
          };
        }"""
    )
    assert metrics["width"] > 8 and metrics["height"] > 8, metrics
    assert metrics["fullyIn"] is True, metrics
    if hit_test:
        assert metrics["occluded"] is False, metrics
    return metrics


def _assert_tour_footer_visible(page) -> dict:
    dialog = _tour_dialog(page)
    card = _tour_card(page)
    prev = dialog.get_by_role("button", name=re.compile(r"^上一步$|^Previous$"))
    nxt = dialog.get_by_role(
        "button",
        name=re.compile(
            r"^下一步$|^Next$|^開始使用$|^Start using the product$"
        ),
    )
    later = dialog.get_by_role(
        "button", name=re.compile(r"稍後再看|Maybe later")
    )
    prev.first.wait_for(state="visible", timeout=10_000)
    nxt.first.wait_for(state="visible", timeout=10_000)
    later.first.wait_for(state="visible", timeout=10_000)
    _assert_opaque_tour_card(page)
    prev_disabled = bool(prev.first.is_disabled())
    measurements = {
        "prev": _assert_fully_in_viewport(prev.first, hit_test=not prev_disabled),
        "next": _assert_fully_in_viewport(nxt.first),
        "later": _assert_fully_in_viewport(later.first),
    }
    assert dialog.locator("[data-cel-tour-footer='1']").count() >= 1
    overflow = card.evaluate(
        """el => ({
          x: el.scrollWidth > el.clientWidth + 2,
          page: document.documentElement.scrollWidth > window.innerWidth + 2,
        })"""
    )
    assert overflow["x"] is False
    assert overflow["page"] is False
    print(
        "TOUR_FOOTER_METRICS "
        f"vw={measurements['next']['vw']} vh={measurements['next']['vh']} "
        f"next=({measurements['next']['left']:.1f},{measurements['next']['top']:.1f},"
        f"{measurements['next']['right']:.1f},{measurements['next']['bottom']:.1f}) "
        f"later=({measurements['later']['left']:.1f},{measurements['later']['top']:.1f},"
        f"{measurements['later']['right']:.1f},{measurements['later']['bottom']:.1f})"
    )
    return measurements


def _assert_tour_card_clear_of_sidebar(page) -> dict:
    """Fail if the sidebar covers the white tour card (1366px regression)."""
    dialog = _tour_dialog(page)
    card = _tour_card(page)
    dialog.first.wait_for(state="visible", timeout=15_000)
    card.first.wait_for(state="visible", timeout=15_000)
    heading = dialog.get_by_text(
        re.compile(
            r"歡迎使用 Carbon Evidence Ledger|"
            r"Welcome to Carbon Evidence Ledger"
        )
    )
    intro = dialog.get_by_text(
        re.compile(r"用 3 個步驟了解|See how to confirm your company")
    )
    step_title = dialog.get_by_text(
        re.compile(
            r"確認公司與目前營運據點|"
            r"Confirm the company and current operating locations"
        )
    )
    heading.first.wait_for(state="visible", timeout=10_000)
    intro.first.wait_for(state="visible", timeout=10_000)
    step_title.first.wait_for(state="visible", timeout=10_000)
    metrics = page.evaluate(
        """() => {
          const overlay = document.querySelector(
            '[data-testid="stDialog"]:has(.cel-tour-root)'
          );
          const card = document.querySelector(
            'section[role="dialog"]:has(.cel-tour-root)'
          );
          const sidebar = document.querySelector(
            'section[data-testid="stSidebar"]'
          );
          if (!overlay || !card) {
            return {ok: false, reason: 'missing'};
          }
          const chainOf = (el) => {
            const rows = [];
            let node = el;
            while (node && node !== document.documentElement) {
              const cs = window.getComputedStyle(node);
              rows.push({
                tag: node.tagName,
                testid: node.getAttribute('data-testid') || '',
                position: cs.position,
                zIndex: cs.zIndex,
                transform: cs.transform === 'none' ? 'none' : cs.transform,
                isolation: cs.isolation,
                filter: cs.filter === 'none' ? 'none' : 'set',
                contain: cs.contain,
              });
              node = node.parentElement;
            }
            return rows;
          };
          const or_ = overlay.getBoundingClientRect();
          const cr = card.getBoundingClientRect();
          const sr = sidebar ? sidebar.getBoundingClientRect() : null;
          const ocs = getComputedStyle(overlay);
          const ccs = getComputedStyle(card);
          const scs = sidebar ? getComputedStyle(sidebar) : null;
          const overlaps = (a, b) =>
            !!(
              b &&
              a.left < b.right &&
              a.right > b.left &&
              a.top < b.bottom &&
              a.bottom > b.top
            );
          const sample = (x, y) => {
            const hit = document.elementFromPoint(x, y);
            return {
              x: Math.round(x),
              y: Math.round(y),
              tag: hit ? hit.tagName : null,
              testid: hit ? hit.getAttribute('data-testid') : null,
              className: hit ? String(hit.className || '').slice(0, 90) : null,
              inSidebar: !!(
                hit && hit.closest('section[data-testid="stSidebar"]')
              ),
              inCard: !!(
                hit && hit.closest('section[role="dialog"]')
              ),
              inOverlay: !!(
                hit && hit.closest('[data-testid="stDialog"]')
              ),
            };
          };
          const inset = 14;
          const margin = 8;
          const vw = window.innerWidth;
          const vh = window.innerHeight;
          return {
            ok: true,
            vw,
            vh,
            overlay: {
              left: or_.left,
              top: or_.top,
              right: or_.right,
              bottom: or_.bottom,
              w: or_.width,
              h: or_.height,
              position: ocs.position,
              zIndex: ocs.zIndex,
              transform: ocs.transform,
            },
            card: {
              left: cr.left,
              top: cr.top,
              right: cr.right,
              bottom: cr.bottom,
              w: cr.width,
              h: cr.height,
              position: ccs.position,
              zIndex: ccs.zIndex,
              transform: ccs.transform,
            },
            sidebar: sr && {
              left: sr.left,
              top: sr.top,
              right: sr.right,
              bottom: sr.bottom,
              w: sr.width,
              h: sr.height,
              position: scs.position,
              zIndex: scs.zIndex,
              transform: scs.transform,
            },
            cardOverlapsSidebar: overlaps(cr, sr),
            cardInViewport:
              cr.left >= margin - 0.5 &&
              cr.top >= margin - 0.5 &&
              cr.right <= vw - margin + 0.5 &&
              cr.bottom <= vh - margin + 0.5,
            overlayMatchesViewport:
              Math.abs(or_.left) <= 2 &&
              Math.abs(or_.top) <= 2 &&
              Math.abs(or_.width - vw) <= 4 &&
              Math.abs(or_.height - vh) <= 4,
            pageOverflow: document.documentElement.scrollWidth > vw + 2,
            cardOverflowX: card.scrollWidth > card.clientWidth + 2,
            overlayChain: chainOf(overlay),
            sidebarChain: sidebar ? chainOf(sidebar) : [],
            hits: {
              topLeft: sample(cr.left + inset, cr.top + inset),
              midLeft: sample(cr.left + inset, cr.top + cr.height / 2),
              botLeft: sample(cr.left + inset, cr.bottom - inset),
              topRight: sample(cr.right - inset, cr.top + inset),
              botRight: sample(cr.right - inset, cr.bottom - inset),
            },
          };
        }"""
    )
    print("TOUR_STACKING " + repr(metrics))
    assert metrics["ok"] is True, metrics
    assert metrics["overlayMatchesViewport"] is True, metrics
    assert metrics["cardInViewport"] is True, metrics
    assert metrics["pageOverflow"] is False, metrics
    assert metrics["cardOverflowX"] is False, metrics
    overlay_z = int(str(metrics["overlay"]["zIndex"]).replace("auto", "0"))
    sidebar_z = 0
    if metrics.get("sidebar"):
        sidebar_z = int(str(metrics["sidebar"]["zIndex"]).replace("auto", "0"))
    assert overlay_z > sidebar_z, (overlay_z, sidebar_z, metrics)
    for name, hit in metrics["hits"].items():
        assert hit["inSidebar"] is False, (name, hit, metrics)
        assert hit["inCard"] is True or hit["inOverlay"] is True, (name, hit)
    for locator in (heading.first, intro.first, step_title.first):
        box = locator.bounding_box()
        assert box is not None and box["x"] >= 8, box
        assert box["x"] + box["width"] <= metrics["vw"] - 8, box
        hit = locator.evaluate(
            """el => {
              const r = el.getBoundingClientRect();
              const hit = document.elementFromPoint(
                r.left + Math.min(12, r.width / 2),
                r.top + r.height / 2
              );
              return {
                inSidebar: !!(
                  hit && hit.closest('section[data-testid="stSidebar"]')
                ),
                inCard: !!(
                  hit && hit.closest('section[role="dialog"]')
                ),
              };
            }"""
        )
        assert hit["inSidebar"] is False, hit
        assert hit["inCard"] is True, hit
    close = page.locator(
        '[data-testid="stDialog"]:has(.cel-tour-root) button[aria-label="Close"]'
    )
    if close.count() == 0:
        close = page.locator(
            '[data-testid="stDialog"]:has(.cel-tour-root) button[kind="header"]'
        )
    if close.count():
        close_metrics = close.first.evaluate(
            """el => {
              const r = el.getBoundingClientRect();
              const hit = document.elementFromPoint(
                r.left + r.width / 2,
                r.top + r.height / 2
              );
              return {
                left: r.left,
                top: r.top,
                width: r.width,
                height: r.height,
                inSidebar: !!(
                  hit && hit.closest('section[data-testid="stSidebar"]')
                ),
                inOverlay: !!(
                  hit && hit.closest('[data-testid="stDialog"]')
                ),
              };
            }"""
        )
        assert close_metrics["width"] >= 12, close_metrics
        assert close_metrics["height"] >= 12, close_metrics
        assert close_metrics["left"] >= 8, close_metrics
        assert close_metrics["inSidebar"] is False, close_metrics
        assert close_metrics["inOverlay"] is True, close_metrics
    _assert_tour_footer_visible(page)
    return metrics


def _open_tour(page) -> None:
    base = page._cel_base_url  # type: ignore[attr-defined]
    page.context.clear_cookies()
    page.goto(base, wait_until="domcontentloaded")
    wait_streamlit_idle(page)
    page.evaluate(
        "() => { try { localStorage.clear(); sessionStorage.clear(); } catch (e) {} }"
    )
    page.goto(base, wait_until="domcontentloaded")
    wait_streamlit_idle(page)
    page.wait_for_selector("text=Carbon Evidence Ledger", timeout=30_000)
    _tour_dialog(page).first.wait_for(state="visible", timeout=20_000)


def _click_in_tour(page, pattern: str) -> None:
    button = _tour_dialog(page).get_by_role("button", name=re.compile(pattern))
    button.first.wait_for(state="visible", timeout=15_000)
    expect(button.first).to_be_enabled(timeout=15_000)
    _assert_fully_in_viewport(button.first)
    button.first.click()
    wait_streamlit_idle(page)
    page.wait_for_timeout(250)


def _assert_step(page, index: int, title: str) -> None:
    dialog = _tour_dialog(page)
    dialog.first.wait_for(state="visible", timeout=15_000)
    body = dialog.first.inner_text()
    assert f"第 {index} 步，共 3 步" in body or f"Step {index} of 3" in body
    assert title in body
    shot = dialog.locator(".cel-tour-shot img")
    shot.first.wait_for(state="visible", timeout=10_000)
    assert dialog.locator(".cel-tour-shot--missing").count() == 0
    assert dialog.locator(".cel-tour-spotlight").count() == 1
    assert dialog.locator(".cel-tour-callout").count() == 1
    _assert_tour_footer_visible(page)
    for token in FORBIDDEN_UI:
        assert token not in body, f"forbidden token {token!r} in tour copy"
    if index == 1:
        assert "營運據點" in body or "operating locations" in body
    if index == 3:
        assert "開始使用" in body or "Start using the product" in body
        img_metrics = shot.first.evaluate(
            """el => {
              const box = el.getBoundingClientRect();
              return {
                naturalWidth: el.naturalWidth,
                naturalHeight: el.naturalHeight,
                displayWidth: box.width,
                displayHeight: box.height,
                objectFit: getComputedStyle(el).objectFit,
              };
            }"""
        )
        assert img_metrics["naturalWidth"] >= 700, img_metrics
        assert img_metrics["displayWidth"] > 360, img_metrics
        assert img_metrics["objectFit"] != "contain"
        assert "tCO" in (shot.first.get_attribute("alt") or "")


def _assert_aligned_and_no_overflow(page) -> None:
    _assert_shot_geometry(page)


def _bitmap_and_overlay_metrics(page) -> dict:
    dialog = _tour_card(page).first
    dialog.wait_for(state="visible", timeout=15_000)
    page.locator(".cel-tour-shot img").first.wait_for(state="visible", timeout=10_000)
    page.locator(".cel-tour-shot-frame").first.wait_for(
        state="visible", timeout=10_000
    )
    page.wait_for_function(
        """() => {
          const img = document.querySelector('.cel-tour-shot img');
          if (!img || img.naturalWidth <= 100) return false;
          return img.getBoundingClientRect().width > 40;
        }""",
        timeout=10_000,
    )
    return dialog.evaluate(
        """el => {
          const figure = el.querySelector('.cel-tour-shot');
          const frame = figure && figure.querySelector('.cel-tour-shot-frame');
          const img = figure && figure.querySelector('img');
          const spot = figure && figure.querySelector('.cel-tour-spotlight');
          const callout = figure && figure.querySelector('.cel-tour-callout');
          const card = document.querySelector(
            'section[role="dialog"]:has(.cel-tour-root)'
          );
          if (!figure || !frame || !img || !spot || !callout || !card) {
            return {ok: false, reason: 'missing'};
          }
          const contentRect = (image) => {
            const r = image.getBoundingClientRect();
            const nw = image.naturalWidth;
            const nh = image.naturalHeight;
            if (!nw || !nh || r.height < 1) {
              return {
                left: r.left,
                top: r.top,
                right: r.right,
                bottom: r.bottom,
                width: r.width,
                height: r.height,
              };
            }
            const ir = nw / nh;
            const cratio = r.width / r.height;
            const fit = getComputedStyle(image).objectFit;
            if (fit !== 'contain' || Math.abs(ir - cratio) < 0.03) {
              return {
                left: r.left,
                top: r.top,
                right: r.right,
                bottom: r.bottom,
                width: r.width,
                height: r.height,
              };
            }
            if (ir > cratio) {
              const h = r.width / ir;
              const top = r.top + (r.height - h) / 2;
              return {
                left: r.left,
                top,
                right: r.left + r.width,
                bottom: top + h,
                width: r.width,
                height: h,
              };
            }
            const w = r.height * ir;
            const left = r.left + (r.width - w) / 2;
            return {
              left,
              top: r.top,
              right: left + w,
              bottom: r.top + r.height,
              width: w,
              height: r.height,
            };
          };
          const fr = frame.getBoundingClientRect();
          const ir = img.getBoundingClientRect();
          const br = contentRect(img);
          const pr = spot.getBoundingClientRect();
          const cr = callout.getBoundingClientRect();
          const cs = getComputedStyle(frame);
          const borderX =
            (parseFloat(cs.borderLeftWidth) || 0) +
            (parseFloat(cs.borderRightWidth) || 0);
          const borderY =
            (parseFloat(cs.borderTopWidth) || 0) +
            (parseFloat(cs.borderBottomWidth) || 0);
          const pad = 4;
          const inside = (box, host) =>
            box.left >= host.left - pad &&
            box.right <= host.right + pad &&
            box.top >= host.top - pad &&
            box.bottom <= host.bottom + pad;
          return {
            ok: true,
            figureW: figure.getBoundingClientRect().width,
            frameW: fr.width,
            frameH: fr.height,
            imgW: ir.width,
            imgH: ir.height,
            bitmapW: br.width,
            bitmapH: br.height,
            letterboxW: Math.abs(ir.width - br.width),
            letterboxH: Math.abs(ir.height - br.height),
            frameVsBitmapW: Math.abs(fr.width - borderX - br.width),
            frameVsBitmapH: Math.abs(fr.height - borderY - br.height),
            spotInsideImage: inside(pr, br),
            calloutInsideImage: inside(cr, br),
            overflow: ir.width > fr.width + 2,
            pageOverflow:
              document.documentElement.scrollWidth > window.innerWidth + 2,
            objectFit: getComputedStyle(img).objectFit,
            imgWDisplay: ir.width,
            spotW: pr.width,
          };
        }"""
    )


def _assert_shot_geometry(page) -> dict:
    metrics = _bitmap_and_overlay_metrics(page)
    assert metrics["ok"] is True, metrics
    assert metrics["imgWDisplay"] > 200, metrics
    assert metrics["spotW"] > 24, metrics
    assert metrics["letterboxW"] <= 4, metrics
    assert metrics["letterboxH"] <= 4, metrics
    assert metrics["frameVsBitmapW"] <= 4, metrics
    assert metrics["frameVsBitmapH"] <= 4, metrics
    assert metrics["spotInsideImage"] is True, metrics
    assert metrics["calloutInsideImage"] is True, metrics
    assert metrics["overflow"] is False, metrics
    assert metrics["pageOverflow"] is False, metrics
    assert metrics["objectFit"] != "contain", metrics
    return metrics


def _assert_teaching_target_in_body_clip(page, *, title: str) -> dict:
    """Fail if the spotlight/callout sit below the visible tour-body clip."""
    dialog = _tour_dialog(page)
    dialog.first.wait_for(state="visible", timeout=15_000)
    title_loc = dialog.get_by_text(title, exact=False)
    title_loc.first.wait_for(state="visible", timeout=10_000)
    page.evaluate(
        """() => {
          const body = document.querySelector(
            '[data-testid="stVerticalBlock"]:has([data-cel-tour-body="1"]):not(:has([data-cel-tour-footer="1"]))'
          );
          if (body) body.scrollTop = 0;
        }"""
    )
    page.wait_for_timeout(120)
    metrics = page.evaluate(
        """titleText => {
          const body = document.querySelector(
            '[data-testid="stVerticalBlock"]:has([data-cel-tour-body="1"]):not(:has([data-cel-tour-footer="1"]))'
          );
          const card = document.querySelector(
            'section[role="dialog"]:has(.cel-tour-root)'
          );
          const spot = document.querySelector('.cel-tour-spotlight');
          const callout = document.querySelector('.cel-tour-callout');
          if (!body || !card || !spot || !callout) {
            return {ok: false, reason: 'missing'};
          }
          const br = body.getBoundingClientRect();
          const crd = card.getBoundingClientRect();
          const clip = {
            left: Math.max(br.left, crd.left, 0),
            top: Math.max(br.top, crd.top, 0),
            right: Math.min(br.right, crd.right, window.innerWidth),
            bottom: Math.min(br.bottom, crd.bottom, window.innerHeight),
          };
          const pad = 6;
          const inside = (box) =>
            box.left >= clip.left - pad &&
            box.right <= clip.right + pad &&
            box.top >= clip.top - pad &&
            box.bottom <= clip.bottom + pad;
          const titles = Array.from(
            document.querySelectorAll(
              'section[role="dialog"] p, section[role="dialog"] strong'
            )
          );
          const titleEl = titles.find((el) =>
            (el.textContent || '').includes(titleText)
          );
          const titleBox = titleEl ? titleEl.getBoundingClientRect() : null;
          const img = document.querySelector('.cel-tour-shot img');
          const frame = document.querySelector('.cel-tour-shot-frame');
          const spotBox = spot.getBoundingClientRect();
          const imgBox = img ? img.getBoundingClientRect() : null;
          const frameBox = frame ? frame.getBoundingClientRect() : null;
          return {
            ok: true,
            scrollTop: body.scrollTop,
            bodyH: br.height,
            spotInsideClip: inside(spotBox),
            calloutInsideClip: inside(callout.getBoundingClientRect()),
            titleInsideClip: titleBox ? inside(titleBox) : false,
            imgInsideClip: imgBox ? inside(imgBox) : false,
            pageOverflow:
              document.documentElement.scrollWidth > window.innerWidth + 2,
            clip,
            spot: {
              top: spotBox.top,
              bottom: spotBox.bottom,
              left: spotBox.left,
              right: spotBox.right,
            },
            img: imgBox && {
              top: imgBox.top,
              bottom: imgBox.bottom,
              width: imgBox.width,
              height: imgBox.height,
            },
            frame: frameBox && {
              top: frameBox.top,
              bottom: frameBox.bottom,
              width: frameBox.width,
              height: frameBox.height,
            },
            overflowSpot: {
              bottom: spotBox.bottom - clip.bottom,
              top: clip.top - spotBox.top,
            },
          };
        }""",
        title,
    )
    print("TOUR_BODY_CLIP", metrics)
    assert metrics["ok"] is True, metrics
    assert metrics["scrollTop"] == 0, metrics
    assert metrics["spotInsideClip"] is True, metrics
    assert metrics["calloutInsideClip"] is True, metrics
    assert metrics["titleInsideClip"] is True, metrics
    assert metrics["pageOverflow"] is False, metrics
    _assert_tour_footer_visible(page)
    return metrics


def _shot_dialog(page, name: str) -> Path:
    dialog = _tour_dialog(page).first
    dialog.wait_for(state="visible", timeout=15_000)
    _assert_tour_footer_visible(page)
    try:
        dialog.evaluate(
            """el => {
              const scroller = el.querySelector(
                '[data-testid="stVerticalBlock"]:has([data-cel-tour-body="1"]):not(:has([data-cel-tour-footer="1"]))'
              );
              if (scroller) scroller.scrollTop = 0;
            }"""
        )
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(150)
    _assert_tour_footer_visible(page)
    return save_step_screenshot(page, name, required=True)


def _goto_evidence(page) -> None:
    expand = page.get_by_text("keyboard_double_arrow_right", exact=False)
    if expand.count():
        expand.first.click(force=True)
        wait_streamlit_idle(page)
    link = page.get_by_role("link", name=re.compile(r"證據與資料|Evidence"))
    link.first.wait_for(state="visible", timeout=20_000)
    link.first.click(force=True)
    wait_streamlit_idle(page)
    close = page.get_by_text("keyboard_double_arrow_left", exact=False)
    if close.count() and close.first.is_visible():
        close.first.click(force=True)
        wait_streamlit_idle(page)


def _collapse_sidebar(page) -> None:
    close = page.get_by_text("keyboard_double_arrow_left", exact=False)
    if close.count() == 0:
        return
    try:
        if close.first.is_visible():
            close.first.click(force=True, timeout=2_000)
            wait_streamlit_idle(page)
    except Exception:  # noqa: BLE001
        page.keyboard.press("Escape")


def _expand_sidebar(page) -> None:
    expand = page.get_by_text("keyboard_double_arrow_right", exact=False)
    if expand.count() == 0:
        return
    try:
        if expand.first.is_visible():
            expand.first.click(force=True, timeout=2_000)
            wait_streamlit_idle(page)
    except Exception:  # noqa: BLE001
        pass


def _collapse_hidden_chrome_wrappers(page) -> None:
    """Remove leftover Streamlit flex-gap from display:none teaching chrome."""
    page.evaluate(
        """() => {
          const sels = [
            '.cel-page-kicker',
            '.cel-page-title',
            '.cel-page-sub',
            '.cel-stepper',
            '.cel-learn-card',
          ];
          for (const sel of sels) {
            for (const el of document.querySelectorAll(sel)) {
              const block = el.closest('[data-testid="stVerticalBlock"]');
              if (!block) continue;
              let child = el;
              while (child.parentElement && child.parentElement !== block) {
                child = child.parentElement;
              }
              if (child.parentElement !== block) continue;
              if (child.querySelector('[data-testid="stButton"]')) continue;
              child.style.setProperty('display', 'none', 'important');
              child.style.setProperty('height', '0', 'important');
              child.style.setProperty('margin', '0', 'important');
              child.style.setProperty('padding', '0', 'important');
              child.style.setProperty('min-height', '0', 'important');
            }
          }
        }"""
    )
    page.wait_for_timeout(80)


def _inject_capture_css(page, css: str) -> None:
    page.evaluate(
        """css => {
          const existing = document.getElementById('cel-tour-capture-css');
          if (existing) existing.remove();
          const style = document.createElement('style');
          style.id = 'cel-tour-capture-css';
          style.textContent = css;
          document.head.appendChild(style);
        }""",
        css,
    )
    page.wait_for_timeout(80)


def _clear_capture_css(page) -> None:
    page.evaluate(
        """() => {
          const css = document.getElementById('cel-tour-capture-css');
          if (css) css.remove();
        }"""
    )


def _assert_boxes_in_clip(boxes: list[dict], clip: dict[str, float]) -> None:
    clip_right = clip["x"] + clip["width"]
    clip_bottom = clip["y"] + clip["height"]
    for box in boxes:
        assert box["x"] >= clip["x"] - 1, box
        assert box["y"] >= clip["y"] - 1, box
        assert box["x"] + box["width"] <= clip_right + 1, (box, clip)
        assert box["y"] + box["height"] <= clip_bottom + 1, (box, clip)


def _visible_box(locator, name: str) -> dict:
    locator.first.wait_for(state="visible", timeout=15_000)
    box = locator.first.bounding_box()
    assert box is not None and box["width"] > 4 and box["height"] > 4, (name, box)
    return {
        "name": name,
        "x": float(box["x"]),
        "y": float(box["y"]),
        "width": float(box["width"]),
        "height": float(box["height"]),
    }


def _relative_highlight(clip: dict[str, float], boxes: list[dict]) -> dict[str, float]:
    left = min(item["x"] for item in boxes)
    top = min(item["y"] for item in boxes)
    right = max(item["x"] + item["width"] for item in boxes)
    bottom = max(item["y"] + item["height"] for item in boxes)
    pad_x = 10.0
    pad_y = 10.0
    width = max(clip["width"], 1.0)
    height = max(clip["height"], 1.0)
    highlight = {
        "left": max(0.0, (left - pad_x - clip["x"]) / width),
        "top": max(0.0, (top - pad_y - clip["y"]) / height),
        "width": min(1.0, (right - left + pad_x * 2) / width),
        "height": min(1.0, (bottom - top + pad_y * 2) / height),
    }
    assert highlight["left"] + highlight["width"] <= 1.02, (highlight, clip)
    assert highlight["top"] + highlight["height"] <= 1.02, (highlight, clip)
    return highlight


def _png_size(path: Path) -> tuple[int, int]:
    import struct

    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _tighten_png_vertical_whitespace(
    path: Path, *, max_gap: int = 10
) -> None:
    """Drop long interior empty bands from a live screenshot (no fake UI)."""
    from PIL import Image

    image = Image.open(path).convert("RGB")
    width, height = image.size
    pixels = image.load()
    assert pixels is not None

    def row_is_empty(y: int) -> bool:
        samples = []
        for x in range(0, width, 12):
            red, green, blue = pixels[x, y]
            samples.append(red + green + blue)
        mean = sum(samples) / max(len(samples), 1)
        return mean >= 720 and max(samples) - min(samples) <= 48

    empty = [row_is_empty(y) for y in range(height)]
    keep: list[int] = []
    index = 0
    while index < height:
        if not empty[index]:
            keep.append(index)
            index += 1
            continue
        start = index
        while index < height and empty[index]:
            index += 1
        run = index - start
        if not keep or index >= height:
            keep.extend(range(start, index))
            continue
        keep.extend(range(start, start + min(run, max_gap)))
    if len(keep) >= height - 8 or len(keep) < 180:
        return
    out = Image.new("RGB", (width, len(keep)))
    for new_y, old_y in enumerate(keep):
        out.paste(image.crop((0, old_y, width, old_y + 1)), (0, new_y))
    out.save(path)


def _clip_from_boxes(
    boxes: list[dict],
    viewport: dict,
    *,
    pad: float,
    min_width: float,
    min_height: float,
) -> dict[str, float]:
    left = min(item["x"] for item in boxes)
    top = min(item["y"] for item in boxes)
    right = max(item["x"] + item["width"] for item in boxes)
    bottom = max(item["y"] + item["height"] for item in boxes)
    needed_w = (right - left) + pad * 2
    needed_h = (bottom - top) + pad * 2
    width = max(needed_w, min_width)
    height = max(needed_h, min_height)
    vw = float(viewport["width"])
    vh = float(viewport["height"])
    extra_w = max(0.0, width - needed_w)
    extra_h = max(0.0, height - needed_h)
    x = max(0.0, left - pad - extra_w)
    y = max(0.0, top - pad - extra_h / 2)
    if x + width > vw:
        x = max(0.0, vw - width)
        width = min(width, vw - x)
    if y + height > vh:
        y = max(0.0, vh - height)
        height = min(height, vh - y)
    clip = {
        "x": float(int(x)),
        "y": float(int(y)),
        "width": float(int(width + 0.999)),
        "height": float(int(height + 0.999)),
    }
    if clip["x"] + clip["width"] > vw:
        clip["width"] = vw - clip["x"]
    if clip["y"] + clip["height"] > vh:
        clip["height"] = vh - clip["y"]
    return clip


def _ensure_required_boxes_in_viewport(page, locators) -> None:
    viewport = page.viewport_size or {"width": 1440, "height": 1200}
    vh = float(viewport["height"])
    measured: list[tuple] = []
    for locator, name in locators:
        locator.first.wait_for(state="visible", timeout=15_000)
        box = locator.first.bounding_box()
        assert box is not None, name
        measured.append((locator, name, box))
    topmost = min(measured, key=lambda item: item[2]["y"])
    lowest = max(measured, key=lambda item: item[2]["y"] + item[2]["height"])
    all_visible = all(
        item[2]["y"] >= 0 and item[2]["y"] + item[2]["height"] <= vh
        for item in measured
    )
    span = (lowest[2]["y"] + lowest[2]["height"]) - topmost[2]["y"]
    assert span + 48 <= vh, (
        f"required elements span {span:.0f}px which exceeds viewport {vh:.0f}px"
    )
    if all_visible:
        return
    try:
        topmost[0].first.evaluate(
            "el => el.scrollIntoView({block: 'start', inline: 'nearest'})"
        )
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(200)


def _product_shot_elements(
    page,
    dest: Path,
    locators,
    *,
    css: str = HIDE_CHROME,
    pad: float = 36.0,
    min_width: float = 640.0,
    min_height: float = 240.0,
    highlight_locators=None,
    write: bool = True,
    collapse_chrome: bool = False,
) -> dict:
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    _inject_capture_css(page, css)
    if collapse_chrome:
        _collapse_hidden_chrome_wrappers(page)
    dest.parent.mkdir(parents=True, exist_ok=True)
    named = []
    for item in locators:
        if isinstance(item, tuple):
            named.append(item)
        else:
            named.append((item, "element"))
    _ensure_required_boxes_in_viewport(page, named)
    boxes = [_visible_box(locator, name) for locator, name in named]
    viewport = page.viewport_size or {"width": 1440, "height": 1200}
    clip = _clip_from_boxes(
        boxes,
        viewport,
        pad=pad,
        min_width=min_width,
        min_height=min_height,
    )
    _assert_boxes_in_clip(boxes, clip)
    highlight_boxes = boxes
    if highlight_locators:
        highlight_boxes = [
            _visible_box(locator, name) for locator, name in highlight_locators
        ]
        _assert_boxes_in_clip(highlight_boxes, clip)
    highlight = _relative_highlight(clip, highlight_boxes)
    if write:
        page.screenshot(path=str(dest), clip=clip, timeout=15_000)
        _clear_capture_css(page)
        assert dest.is_file() and dest.stat().st_size > 0, dest
        width, height = _png_size(dest)
        assert width >= min_width - 1, (dest.name, width, height, clip)
        assert height >= min_height - 1, (dest.name, width, height, clip)
        assert width >= clip["width"] - 1, (dest.name, width, clip)
        assert height >= clip["height"] - 1, (dest.name, height, clip)
    else:
        _clear_capture_css(page)
    print(
        "CAPTURE_PROOF "
        f"file={dest.name} clip={clip} boxes={boxes} highlight={highlight}"
    )
    return {"clip": clip, "boxes": boxes, "highlight": highlight}


def _product_shot_around(
    page,
    dest: Path,
    text: str,
    *,
    pad_top: float = 340.0,
    pad_bottom: float = 220.0,
) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    _collapse_sidebar(page)
    target = page.get_by_text(text, exact=False)
    target.first.wait_for(state="visible", timeout=15_000)
    try:
        target.last.scroll_into_view_if_needed(timeout=5_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(250)
    page.evaluate(
        """() => {
          const existing = document.getElementById('cel-tour-capture-css');
          if (existing) existing.remove();
          const style = document.createElement('style');
          style.id = 'cel-tour-capture-css';
          style.textContent = `%s`;
          document.head.appendChild(style);
        }"""
        % HIDE_CHROME
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    main = page.locator('section[data-testid="stMain"]')
    main.first.wait_for(state="visible", timeout=15_000)
    main_box = main.first.bounding_box()
    focus_box = target.last.bounding_box()
    assert main_box is not None and focus_box is not None
    clip_y = max(float(main_box["y"]), float(focus_box["y"]) - pad_top)
    clip_bottom = min(
        float(main_box["y"]) + float(main_box["height"]),
        float(focus_box["y"]) + float(focus_box["height"]) + pad_bottom,
    )
    clip_h = max(420.0, min(640.0, clip_bottom - clip_y))
    page.screenshot(
        path=str(dest),
        clip={
            "x": main_box["x"],
            "y": clip_y,
            "width": main_box["width"],
            "height": clip_h,
        },
        timeout=15_000,
    )
    page.evaluate(
        """() => {
          const css = document.getElementById('cel-tour-capture-css');
          if (css) css.remove();
        }"""
    )
    assert dest.is_file() and dest.stat().st_size > 0, dest


def _product_shot(
    page,
    dest: Path,
    *,
    scroll_text: str | None = None,
    band: dict[str, float] | None = None,
) -> None:
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    _collapse_sidebar(page)
    if scroll_text:
        target = page.get_by_text(scroll_text, exact=False)
        if target.count():
            try:
                target.last.scroll_into_view_if_needed(timeout=5_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(250)
    page.evaluate(
        """() => {
          const existing = document.getElementById('cel-tour-capture-css');
          if (existing) existing.remove();
          const style = document.createElement('style');
          style.id = 'cel-tour-capture-css';
          style.textContent = `%s`;
          document.head.appendChild(style);
        }"""
        % HIDE_CHROME
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    main = page.locator('section[data-testid="stMain"]')
    main.first.wait_for(state="visible", timeout=15_000)
    box = main.first.bounding_box()
    assert box is not None
    frame_h = min(float(box["height"]), 1100.0)
    top_frac = float((band or {}).get("top", 0.0))
    height_frac = float((band or {}).get("height", 1.0))
    clip_y = float(box["y"]) + frame_h * top_frac
    clip_h = max(360.0, min(frame_h * height_frac, frame_h - frame_h * top_frac))
    page.screenshot(
        path=str(dest),
        clip={
            "x": box["x"],
            "y": clip_y,
            "width": box["width"],
            "height": clip_h,
        },
        timeout=15_000,
    )
    page.evaluate(
        """() => {
          const css = document.getElementById('cel-tour-capture-css');
          if (css) css.remove();
        }"""
    )
    assert dest.is_file() and dest.stat().st_size > 0, dest


def _write_sample_xlsx() -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / SAMPLE_XLSX_NAME
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "2月能源"
    sheet.append(["活動類型", "用量", "單位", "開始日期", "結束日期", "廠場"])
    sheet.append(["外購電力", 50000, "kWh", "2025-01-01", "2025-01-31", "高雄一廠"])
    sheet.append(["天然氣", 8000, "m3", "2025-01-01", "2025-01-31", "高雄一廠"])
    sheet.append(["柴油", 1200, "L", "2025-01-01", "2025-01-31", "高雄一廠"])
    sheet.append(["採購鋼材", 10, "t", "2025-01-01", "2025-01-31", "高雄一廠"])
    sheet.append(["雜項能源", 5, "t", "2025-01-01", "2025-01-31", "高雄一廠"])
    workbook.save(path)
    return path


def _upload_sample(page) -> None:
    path = _write_sample_xlsx()
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(path))
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
    if target is None:
        return
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
    wait_streamlit_idle(page)


def _stamp_hero_meta(path: Path, hero_val: float) -> None:
    from PIL import Image, PngImagePlugin

    image = Image.open(path)
    meta = PngImagePlugin.PngInfo()
    meta.add_text("cel_hero_tco2e", f"{hero_val:.6f}")
    image.save(path, pnginfo=meta)


def _read_hero_meta(path: Path) -> float:
    from PIL import Image

    image = Image.open(path)
    raw = (image.info or {}).get("cel_hero_tco2e")
    assert raw, f"missing hero metadata in {path}"
    value = float(raw)
    assert value > 0, value
    return value


def _switch_product_language(page, lang: str) -> None:
    token = "EN" if lang == "en" else "繁中"
    dismiss_tutorial_if_present(page)
    main = page.locator('section[data-testid="stMain"]')
    option = main.get_by_text(token, exact=True)
    if option.count() == 0:
        option = page.get_by_text(token, exact=True)
    option.first.wait_for(state="visible", timeout=15_000)
    option.first.click()
    wait_streamlit_idle(page)
    page.wait_for_timeout(400)
    dismiss_tutorial_if_present(page)


def _capture_step1(page, *, lang: str) -> dict:
    visual = tour_step_visual(step_by_index(1), lang)
    dest = visual["path"]
    english = lang == "en"
    start = "Start company setup" if english else "開始公司設定"
    heading_pat = "Confirm Taiwan sites" if english else "確認台灣廠場"
    found_pat = (
        "Official public records show" if english else "根據政府公開資料"
    )
    still_pat = (
        "Are these factories still operated" if english else "這些工廠在"
    )
    primary_pat = r"^Yes, all" if english else r"^是，"
    exception_pat = (
        r"Some sites are closed" if english else r"有廠場已停用"
    )
    open_fresh_app(page)
    if english:
        _switch_product_language(page, "en")
        page.get_by_role(
            "button", name=re.compile(r"Start company setup")
        ).first.wait_for(state="visible", timeout=20_000)
    click_button(page, start)
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    page.keyboard.press("Escape")
    wait_streamlit_idle(page)
    body = visible_text(page)
    assert "長興材料" in body
    for _ in range(6):
        if page.get_by_text(still_pat, exact=False).count():
            break
        if page.get_by_role("button", name=re.compile(primary_pat)).count():
            break
        cont = page.get_by_role("button", name=re.compile(r"^繼續$|^Continue$"))
        if cont.count() == 0:
            break
        cont.first.click(force=True)
        wait_streamlit_idle(page)
        page.wait_for_timeout(250)
    company = (
        page.locator('section[data-testid="stMain"]')
        .locator(".cel-appbar-title")
        .filter(has_text="長興材料")
    )
    heading = page.get_by_text(heading_pat, exact=True)
    found = page.get_by_text(found_pat, exact=False)
    still = page.get_by_text(still_pat, exact=False)
    primary = page.get_by_role("button", name=re.compile(primary_pat))
    exception = page.get_by_role("button", name=re.compile(exception_pat))
    company.first.wait_for(state="visible", timeout=20_000)
    heading.last.wait_for(state="visible", timeout=20_000)
    still.first.wait_for(state="visible", timeout=20_000)
    primary.first.wait_for(state="visible", timeout=15_000)
    exception.first.wait_for(state="visible", timeout=15_000)
    locators = [
        (company, "confirmed-company"),
        (heading.last, "facility-heading"),
        (still, "facility-question"),
        (primary, "facility-primary"),
        (exception, "facility-exception"),
    ]
    if found.count():
        locators.insert(2, (found, "facility-found"))
    result = _product_shot_elements(
        page,
        dest,
        locators,
        css=STEP1_TEACHING_CHROME,
        pad=16.0,
        min_width=880.0,
        min_height=220.0,
        highlight_locators=[
            (heading.last, "facility-heading"),
            (still, "facility-question"),
            (primary, "facility-primary"),
            (exception, "facility-exception"),
        ],
        collapse_chrome=True,
    )
    _tighten_png_vertical_whitespace(dest)
    width, height = _png_size(dest)
    print(f"STEP1_TIGHTENED_{lang} {width}x{height}")
    assert height <= 480, (dest.name, width, height)
    assert height >= 220, (dest.name, width, height)
    print(f"STEP1_HIGHLIGHT_{lang}", result["highlight"])
    return result


def capture_production_assets(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1200})
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    _capture_step1(page, lang="zh-TW")
    _capture_step1(page, lang="en")

    _goto_evidence(page)
    _switch_product_language(page, "zh-TW")
    page.get_by_text(
        re.compile(r"上傳能源與營運資料|Upload energy and operating data")
    ).first.wait_for(state="visible", timeout=20_000)
    _collapse_sidebar(page)
    landing = visible_text(page)
    assert "尚未設定公司" not in landing
    assert "Company not set" not in landing
    assert "其他資料功能" not in landing
    assert "More data tools" not in landing
    assert "完成分析後即可查看結果" not in landing
    assert "待確認資料" not in landing
    assert "查看欄位處理紀錄" not in landing
    _inject_capture_css(page, HIDE_CHROME)
    intake_shot = ARTIFACTS / "qa_42g_intake_upload_desktop.png"
    intake_shot.parent.mkdir(parents=True, exist_ok=True)
    main = page.locator('section[data-testid="stMain"]')
    main.first.wait_for(state="visible", timeout=15_000)
    box = main.first.bounding_box()
    assert box is not None
    page.screenshot(
        path=str(intake_shot),
        clip={
            "x": float(box["x"]),
            "y": float(box["y"]),
            "width": min(float(box["width"]), 1100.0),
            "height": min(float(box["height"]), 900.0),
        },
        timeout=15_000,
    )
    _clear_capture_css(page)
    assert intake_shot.is_file() and intake_shot.stat().st_size > 0

    for lang in ("zh-TW", "en"):
        if lang == "en":
            _switch_product_language(page, "en")
        heading_upload = page.get_by_text(
            re.compile(r"上傳公司現有資料|Upload your company"),
            exact=False,
        )
        uploader = page.locator('[data-testid="stFileUploader"]')
        heading_upload.first.wait_for(state="visible", timeout=15_000)
        uploader.first.wait_for(state="visible", timeout=15_000)
        dest = tour_step_visual(step_by_index(2), lang)["path"]
        if lang == "zh-TW" and dest.is_file():
            measured = _product_shot_elements(
                page,
                dest,
                [
                    (heading_upload, "intake-heading"),
                    (uploader, "intake-uploader"),
                ],
                pad=28.0,
                min_width=640.0,
                min_height=240.0,
                write=False,
            )
            step2_w, step2_h = _png_size(dest)
            union_w = max(
                item["x"] + item["width"] for item in measured["boxes"]
            ) - min(item["x"] for item in measured["boxes"])
            union_h = max(
                item["y"] + item["height"] for item in measured["boxes"]
            ) - min(item["y"] for item in measured["boxes"])
            clipped = (
                step2_w < 640
                or step2_h < 240
                or union_w > step2_w + 2
                or union_h > step2_h + 2
            )
            if not clipped:
                print(
                    "PRESERVE_STEP2 "
                    f"existing={step2_w}x{step2_h} "
                    f"measured_clip={measured['clip']}"
                )
                continue
        result = _product_shot_elements(
            page,
            dest,
            [
                (heading_upload, "intake-heading"),
                (uploader, "intake-uploader"),
            ],
            pad=28.0,
            min_width=640.0,
            min_height=240.0,
        )
        print(f"STEP2_HIGHLIGHT_{lang}", result["highlight"])

    for lang in ("zh-TW", "en"):
        open_fresh_app(page)
        if lang == "en":
            _switch_product_language(page, "en")
        demo = "Try demo data" if lang == "en" else "使用示範資料"
        click_button(page, demo)
        wait_streamlit_idle(page, timeout=120)
        summary_text = "Emissions summary" if lang == "en" else "排放資料摘要"
        page.get_by_text(summary_text, exact=False).first.wait_for(
            state="visible", timeout=60_000
        )
        _expand_sidebar(page)
        hero = page.locator("[data-cel-hero-emissions='1']")
        hero.first.wait_for(state="visible", timeout=30_000)
        hero_val = float(hero.first.get_attribute("data-cel-target") or "0")
        assert hero_val > 0, f"step 3 capture has zero result: {hero_val}"
        _wait_hero_countup_stable(page)
        summary = page.locator("h2.cel-section-title").filter(
            has_text=summary_text
        )
        card = page.locator(".cel-kpi-card").first
        unit = page.locator(".cel-kpi-unit-inline").first
        evidence_nav = page.locator('[data-testid="stSidebarNavLink"]').filter(
            has_text=re.compile(r"證據與資料|Evidence")
        )
        reports_nav = page.locator('[data-testid="stSidebarNavLink"]').filter(
            has_text=re.compile(r"報表與匯出|Reporting")
        )
        summary.first.wait_for(state="visible", timeout=15_000)
        card.wait_for(state="visible", timeout=15_000)
        unit.wait_for(state="visible", timeout=15_000)
        evidence_nav.first.wait_for(state="visible", timeout=15_000)
        reports_nav.first.wait_for(state="visible", timeout=15_000)
        dest = tour_step_visual(step_by_index(3), lang)["path"]
        result = _product_shot_elements(
            page,
            dest,
            [
                (evidence_nav, "nav-evidence"),
                (reports_nav, "nav-reports"),
                (summary, "emissions-heading"),
                (card, "kpi-card"),
                (hero, "kpi-value"),
                (unit, "kpi-unit"),
            ],
            css=HIDE_CHROME_KEEP_SIDEBAR,
            pad=36.0,
            min_width=880.0,
            min_height=280.0,
            highlight_locators=[(card, "kpi-card")],
        )
        print(f"STEP3_HIGHLIGHT_{lang}", result["highlight"])
        _stamp_hero_meta(dest, hero_val)
        assert result["clip"]["width"] >= 700

    missing = missing_or_empty_assets()
    assert missing == (), missing
    for lang in ("zh-TW", "en"):
        path1 = tour_step_visual(step_by_index(1), lang)["path"]
        path3 = tour_step_visual(step_by_index(3), lang)["path"]
        width1, height1 = _png_size(path1)
        width3, height3 = _png_size(path3)
        assert width1 >= 640 and 220 <= height1 <= 480, (
            path1.name,
            width1,
            height1,
        )
        assert width3 >= 700, (path3.name, width3, height3)
        assert width3 >= height3 * 0.9, (path3.name, width3, height3)


def test_capture_production_tutorial_assets(page) -> None:
    capture_production_assets(page)
    assert missing_or_empty_assets() == ()
    for path in production_asset_paths():
        assert path.is_file() and path.stat().st_size > 0
    for lang in ("zh-TW", "en"):
        width1, height1 = _png_size(
            tour_step_visual(step_by_index(1), lang)["path"]
        )
        width2, height2 = _png_size(
            tour_step_visual(step_by_index(2), lang)["path"]
        )
        width3, height3 = _png_size(
            tour_step_visual(step_by_index(3), lang)["path"]
        )
        assert width1 >= 640 and 220 <= height1 <= 480, (
            lang,
            width1,
            height1,
        )
        assert width2 >= 640 and height2 >= 240, (lang, width2, height2)
        assert width3 >= 700 and height3 >= 240, (lang, width3, height3)
        assert width3 >= height3 * 0.9, (lang, width3, height3)


def test_desktop_tour_steps_one_through_three(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1100})
    _open_tour(page)
    titles = [
        "確認公司與目前營運據點",
        "使用公司既有的資料檔",
        "檢視分析結果與可下載資料",
    ]
    save_step_screenshot(page, "qa_42g_tour_cover_desktop", required=True)
    _assert_tour_footer_visible(page)
    for index, title in enumerate(titles, start=1):
        _assert_step(page, index, title)
        _assert_aligned_and_no_overflow(page)
        _shot_dialog(page, f"qa_42g_tour_step{index}_{STEP_IDS[index - 1]}")
        if index == 1:
            _assert_teaching_target_in_body_clip(page, title=title)
            _assert_tour_card_clear_of_sidebar(page)
            visual = tour_step_visual(step_by_index(1), "zh-TW")
            figure = _tour_dialog(page).locator(".cel-tour-shot").first
            assert figure.get_attribute("data-cel-tour-image") == visual["image"]
            assert not str(visual["image"]).endswith(".en.png")
        if index < TOUR_STEP_COUNT:
            _click_in_tour(page, r"^下一步$|^Next$")
    _read_hero_meta(ASSET_DIR / "step3_results.png")
    _click_in_tour(page, r"開始使用|Start using the product")
    _tour_dialog(page).first.wait_for(state="hidden", timeout=15_000)
    assert_no_app_errors(page)


GEOMETRY_VIEWPORTS = (
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1440, "height": 1100},
)


@pytest.mark.parametrize(
    "viewport",
    GEOMETRY_VIEWPORTS,
    ids=("1366x768", "1440x900", "1440x1100"),
)
def test_tour_image_geometry_matches_visible_image(page, viewport) -> None:
    page.set_viewport_size(viewport)
    _open_tour(page)
    titles = [
        "確認公司與目前營運據點",
        "使用公司既有的資料檔",
        "檢視分析結果與可下載資料",
    ]
    for index, title in enumerate(titles, start=1):
        _assert_step(page, index, title)
        metrics = _assert_shot_geometry(page)
        _assert_tour_footer_visible(page)
        if index == 1:
            _assert_teaching_target_in_body_clip(page, title=title)
            _assert_tour_card_clear_of_sidebar(page)
            _shot_dialog(
                page,
                f"qa_42g_tour_step1_{viewport['width']}x{viewport['height']}",
            )
        print(
            "TOUR_GEOMETRY "
            f"viewport={viewport['width']}x{viewport['height']} "
            f"step={index} frame={metrics['frameW']:.0f}x{metrics['frameH']:.0f} "
            f"bitmap={metrics['bitmapW']:.0f}x{metrics['bitmapH']:.0f} "
            f"letterbox={metrics['letterboxW']:.1f}x{metrics['letterboxH']:.1f}"
        )
        if index < TOUR_STEP_COUNT:
            _click_in_tour(page, r"^下一步$|^Next$")
    assert_no_app_errors(page)


@pytest.mark.skip(
    reason=(
        "Stage 4.2G is desktop-first. The three-step guided tour is not an "
        "approved mobile workflow; phone layout is a deferred known "
        "limitation, not a pass."
    )
)
def test_fresh_mobile_tour_layout(page) -> None:
    browser = page.context.browser
    assert browser is not None
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="zh-TW",
        is_mobile=True,
        has_touch=True,
    )
    mobile = context.new_page()
    mobile._cel_base_url = page._cel_base_url  # type: ignore[attr-defined]
    try:
        _open_tour(mobile)
        _assert_step(mobile, 1, "確認公司與目前營運據點")
        _assert_aligned_and_no_overflow(mobile)
        footer = _assert_tour_footer_visible(mobile)
        assert footer["next"]["fullyIn"] is True
        assert footer["later"]["fullyIn"] is True
        overflow = mobile.evaluate(
            "() => document.documentElement.scrollWidth - window.innerWidth"
        )
        assert overflow <= 8
    finally:
        context.close()


def test_english_tour_copy_and_controls(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1100})
    _open_tour(page)
    control = _tour_dialog(page).locator('[data-testid="stSegmentedControl"]')
    option = control.get_by_text("EN", exact=True)
    if option.count() == 0:
        option = _tour_dialog(page).get_by_text("EN", exact=True)
    option.first.wait_for(state="visible", timeout=15_000)
    _assert_fully_in_viewport(option.first)
    option.first.click()
    wait_streamlit_idle(page)
    page.wait_for_timeout(400)
    dialog = _tour_dialog(page)
    body = dialog.first.inner_text()
    if "Step 1 of 3" not in body:
        option.first.click()
        wait_streamlit_idle(page)
        body = dialog.first.inner_text()
    assert "Step 1 of 3" in body
    assert "Confirm the company and current operating locations" in body
    assert "Next" in body
    assert "Maybe later" in body
    assert "開始使用" not in body
    assert "tut." not in body
    _assert_aligned_and_no_overflow(page)
    _assert_tour_footer_visible(page)
    save_step_screenshot(page, "qa_42g_tour_english", required=True)
    titles_en = [
        "Confirm the company and current operating locations",
        "Use the file the company already keeps",
        "Review the analysis and downloadable files",
    ]
    for index, title in enumerate(titles_en, start=1):
        _assert_step(page, index, title)
        visual = tour_step_visual(step_by_index(index), "en")
        figure = _tour_dialog(page).locator(".cel-tour-shot").first
        assert figure.get_attribute("data-cel-tour-lang") == "en"
        assert figure.get_attribute("data-cel-tour-image") == visual["image"]
        assert str(visual["image"]).endswith(".en.png")
        _shot_dialog(page, f"qa_42g_tour_en_step{index}_{STEP_IDS[index - 1]}")
        if index < TOUR_STEP_COUNT:
            _click_in_tour(page, r"^Next$")
    _shot_dialog(page, "qa_42g_tour_english")


def test_replay_starts_at_step_one(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1100})
    _open_tour(page)
    for _ in range(TOUR_STEP_COUNT - 1):
        _click_in_tour(page, r"^下一步$|^Next$")
    _assert_step(page, 3, "檢視分析結果與可下載資料")
    _click_in_tour(page, r"開始使用|Start using the product")
    _tour_dialog(page).first.wait_for(state="hidden", timeout=15_000)
    replay = page.get_by_role("button", name=re.compile(r"操作教學|Tutorial"))
    replay.first.wait_for(state="visible", timeout=15_000)
    expect(replay.first).to_be_enabled(timeout=10_000)
    _assert_fully_in_viewport(replay.first)
    replay.first.click()
    wait_streamlit_idle(page)
    _assert_step(page, 1, "確認公司與目前營運據點")
    save_step_screenshot(page, "qa_42g_tour_replay", required=True)
    _shot_dialog(page, "qa_42g_tour_replay")


def test_reduced_motion_shows_final_highlight(page) -> None:
    page.emulate_media(reduced_motion="reduce")
    page.set_viewport_size({"width": 1440, "height": 1100})
    _open_tour(page)
    _assert_step(page, 1, "確認公司與目前營運據點")
    animation = page.locator(".cel-tour-spotlight").first.evaluate(
        "el => getComputedStyle(el).animationName"
    )
    opacity = page.locator(".cel-tour-spotlight").first.evaluate(
        "el => getComputedStyle(el).opacity"
    )
    assert animation in {"none", ""}
    assert float(opacity) >= 0.99
    _assert_aligned_and_no_overflow(page)


def test_cleaned_intake_and_populated_post_analysis_ctas(page) -> None:
    page.set_viewport_size({"width": 1440, "height": 1100})
    open_fresh_app(page)
    click_button(page, "使用示範資料")
    wait_streamlit_idle(page, timeout=120)
    page.get_by_text("排放資料摘要", exact=False).first.wait_for(
        state="visible", timeout=60_000
    )
    _goto_evidence(page)
    landing = visible_text(page)
    assert "其他資料功能" not in landing
    assert "More data tools" not in landing
    assert "完成分析後即可查看結果" not in landing
    open_evidence_workspace_tool(page, "活動資料")
    act = visible_text(page)
    assert "完成分析後即可查看結果" not in act
    assert "活動" in act
    _goto_evidence(page)
    open_evidence_workspace_tool(page, "證據紀錄")
    rec = visible_text(page)
    assert "尚未上傳公司資料" not in rec
    assert "證據" in rec
    _goto_evidence(page)
    issues_btn = page.get_by_role(
        "button", name=re.compile(r"^查看問題$|^View issues$")
    )
    if issues_btn.count():
        open_evidence_workspace_tool(page, "待處理問題")
        iss = visible_text(page)
        assert "完成分析後即可查看結果" not in iss
        assert "待處理" in iss or "問題" in iss
    assert_no_app_errors(page)


def test_required_review_screenshots_exist() -> None:
    missing: list[str] = []
    for name in REVIEW_SHOTS:
        path = ARTIFACTS / f"{name}.png"
        if not path.is_file() or path.stat().st_size <= 0:
            missing.append(name)
    assert not missing, f"required review screenshots missing or empty: {missing}"
