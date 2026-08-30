"""Shared helpers for Playwright customer E2E tests."""

from __future__ import annotations

import re
import time
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts" / "e2e"
APPLICABILITY_NAV = (
    r"我的適用要求|適用性判定|Applicability|Your requirements"
)
STUB_ALIGNED_UBN = "12345675"
STUB_SPARSE_UBN = "24681358"
STUB_DIFF_UBN = "13579243"
STUB_SEVEN_UBN = "15700001"


def assert_no_raw_html_leak(text: str) -> None:
    for token in ("</p>", "</div>", "<span", "cel-status-chip", "class=", "<style"):
        assert token not in text, f"raw HTML token visible to customer: {token!r}"


ENGINEERING_LEAK_TOKENS = (
    "grid_electricity",
    "stationary_combustion",
    "mobile_combustion",
    "factor_id",
    "source_id",
    "rule_id",
    "record_id",
    "evaluation_id",
    "MONITORING_PARTIAL",
    "BASELINE_CAPTURED",
    "NOT_ACTIVATED",
    "calculation_trace",
    "schema_version",
)


def assert_no_engineering_leak(text: str) -> None:
    for token in ENGINEERING_LEAK_TOKENS:
        assert token not in text, f"engineering token visible to customer: {token!r}"


def assert_no_app_errors(page) -> None:
    console_errors = getattr(page, "_cel_console_errors", [])
    page_errors = getattr(page, "_cel_page_errors", [])
    assert not page_errors, f"page errors: {page_errors}"
    assert not console_errors, f"console errors: {console_errors}"


def wait_streamlit_idle(page, *, timeout: float = 20.0) -> None:
    page.wait_for_timeout(150)
    deadline = time.time() + timeout
    app = page.locator('[data-testid="stApp"]')
    while time.time() < deadline:
        state = ""
        if app.count():
            state = str(app.first.get_attribute("data-test-script-state") or "")
        running = page.locator('[data-testid="stStatusWidget"]')
        status_busy = False
        if running.count():
            label = running.first.inner_text().lower()
            status_busy = "running" in label or "執行" in label
        if state in {"notRunning", "initial"} and not status_busy:
            page.wait_for_timeout(250)
            return
        if not state and running.count() == 0:
            page.wait_for_timeout(250)
            return
        page.wait_for_timeout(200)


def dismiss_tutorial_if_present(page) -> None:
    """Close the first-run welcome modal and any live coachmark."""
    button = page.get_by_role(
        "button",
        name=re.compile(r"^(稍後再說|Not now)$"),
    )
    if button.count():
        button.first.click(force=True)
        wait_streamlit_idle(page)
        page.wait_for_timeout(500)
    dialog = page.locator('[data-testid="stDialog"]')
    if dialog.count() and dialog.first.is_visible():
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        wait_streamlit_idle(page)
    coach = page.locator(".st-key-cel_onboarding_coach")
    if coach.count():
        later = coach.get_by_role("button", name=re.compile(r"^(稍後再說|Not now)$"))
        if later.count():
            later.first.click(force=True)
            wait_streamlit_idle(page)
            page.wait_for_timeout(300)


def wait_for_hero_settled(page, *, timeout: float = 30.0) -> dict[str, str]:
    """Wait until the primary emissions KPI shows its final formatted value."""
    hero = page.locator('[data-cel-hero-emissions="1"]').first
    hero.wait_for(state="visible", timeout=int(timeout * 1000))
    read_js = """() => {
      const els = [...document.querySelectorAll('[data-cel-hero-emissions="1"]')];
      const el = els.find((node) => node.offsetParent !== null) || els[0];
      if (!el) return null;
      return {
        text: (el.textContent || '').trim(),
        final: (el.getAttribute('data-cel-final') || '').trim(),
        target: el.getAttribute('data-cel-target') || '',
      };
    }"""

    def _settled(snap: dict | None) -> bool:
        if not snap or not snap.get("final"):
            return False
        try:
            target = float(snap.get("target") or "nan")
        except ValueError:
            return False
        text = str(snap.get("text") or "")
        if text != snap["final"]:
            return False
        if target > 0 and text in {"0.00", "0"}:
            return False
        return True

    deadline = time.time() + timeout
    last: dict | None = None
    while time.time() < deadline:
        wait_streamlit_idle(page, timeout=8.0)
        snap = page.evaluate(read_js)
        last = snap if isinstance(snap, dict) else last
        if _settled(snap if isinstance(snap, dict) else None):
            page.wait_for_timeout(350)
            wait_streamlit_idle(page, timeout=5.0)
            confirm = page.evaluate(read_js)
            if _settled(confirm if isinstance(confirm, dict) else None):
                return {
                    "text": str(confirm["text"]),
                    "final": str(confirm["final"]),
                    "target": str(confirm["target"]),
                }
        page.wait_for_timeout(150)
    raise AssertionError(
        f"hero KPI did not settle before timeout; last={last!r}"
    )


def assert_above_fold(locator, page, *, label: str) -> None:
    """Require a visible control to sit inside the current viewport."""
    assert locator.count() >= 1, f"missing {label}"
    target = locator.first
    assert target.is_visible(), f"{label} is not visible"
    box = target.bounding_box()
    assert box is not None, f"{label} has no bounding box"
    viewport = page.viewport_size or {"width": 1440, "height": 900}
    bottom = box["y"] + box["height"]
    right = box["x"] + box["width"]
    assert box["y"] >= -1, f"{label} starts above the viewport: y={box['y']}"
    assert bottom <= viewport["height"] + 2, (
        f"{label} is below the fold: bottom={bottom:.1f} "
        f"viewport={viewport['height']}"
    )
    assert right <= viewport["width"] + 2, (
        f"{label} overflows horizontally: right={right:.1f} "
        f"viewport={viewport['width']}"
    )


def assert_no_modal_overlay(page) -> None:
    dialog = page.locator('[data-testid="stDialog"]')
    if dialog.count():
        assert not dialog.first.is_visible(), "modal dialog still covers the page"
    coach = page.locator(".st-key-cel_onboarding_coach")
    if coach.count():
        assert not coach.first.is_visible(), "coachmark still covers the page"
    spotlight = page.locator("#cel-onboarding-spotlight")
    assert spotlight.count() == 0, "onboarding spotlight backdrop still mounted"
    progress = page.locator('[data-cel-progress-modal="1"]')
    if progress.count():
        assert not progress.first.is_visible(), "progress modal still covers the page"


def assert_analysis_overlay_unmounted(page) -> None:
    """Require the analysis view, dialog, and backdrop to be gone from the DOM."""
    assert page.locator('[data-cel-analysis-view="1"]').count() == 0
    assert page.locator('[data-cel-analysis-modal="1"]').count() == 0
    analysis_dialogs = page.locator('[data-testid="stDialog"]').filter(
        has_text=re.compile(r"正在分析你的資料|Analyzing your data")
    )
    assert analysis_dialogs.count() == 0
    backdrops = page.locator(
        '[data-baseweb="modal"], [class*="stModal"], [class*="ModalOverlay"]'
    )
    visible_backdrops = [
        index
        for index in range(backdrops.count())
        if backdrops.nth(index).is_visible()
    ]
    assert visible_backdrops == [], "analysis backdrop still visible"


_OVERLAP_INSTALL_JS = """() => {
  if (window.__celOverlapInstalled) return true;
  window.__celOverlapEvents = [];
  window.__celHeroFirst = null;
  window.__celHeroSamples = [];
  function isAnalysisProgress() {
    if (document.querySelector('[data-cel-analysis-view="1"]')) return true;
    if (document.querySelector('[data-cel-analysis-modal="1"]')) return true;
    const dialogs = [...document.querySelectorAll('[data-testid="stDialog"]')];
    if (dialogs.some((el) => {
      if (el.querySelector('.cel-onb-welcome')) return false;
      const text = el.innerText || '';
      return /正在分析你的資料|Analyzing your data/.test(text);
    })) return true;
    const body = document.body ? document.body.innerText : '';
    if (/正在分析你的資料|Analyzing your data/.test(body)) return true;
    return false;
  }
  function isResultSurface() {
    if (document.querySelector('[data-cel-hero-emissions="1"]')) return true;
    const text = document.body ? document.body.innerText : '';
    if (/碳排計算完成|目前已計算排放量|Currently calculated emissions/.test(text)) {
      return true;
    }
    if (document.querySelector('.cel-kpi-card-primary')) return true;
    return false;
  }
  function heroSnap() {
    const el = document.querySelector('[data-cel-hero-emissions="1"]');
    if (!el) return null;
    return {
      text: (el.textContent || '').trim(),
      play: el.getAttribute('data-cel-hero-play') || '',
      target: el.getAttribute('data-cel-target') || '',
      final: el.getAttribute('data-cel-final') || '',
    };
  }
  function check() {
    const progress = isAnalysisProgress();
    const result = isResultSurface();
    if (progress && result) {
      window.__celOverlapEvents.push({
        t: Date.now(),
        progress: true,
        result: true,
      });
    }
    const snap = heroSnap();
    if (snap) {
      if (!window.__celHeroFirst) {
        window.__celHeroFirst = Object.assign({}, snap, {
          progressPresent: progress,
        });
      }
      if (window.__celHeroSamples.length < 240) {
        window.__celHeroSamples.push(snap.text);
      }
    }
  }
  const mo = new MutationObserver(check);
  mo.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
  });
  function loop() {
    check();
    if (!window.__celOverlapStop) requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);
  window.__celOverlapInstalled = true;
  return true;
}"""


def install_analysis_result_overlap_watch(page) -> None:
    """Watch every frame for analysis progress overlapping result hero/KPI."""
    page.evaluate(_OVERLAP_INSTALL_JS)


def analysis_result_overlap_events(page) -> list:
    return page.evaluate("() => window.__celOverlapEvents || []") or []


def analysis_hero_first_snapshot(page) -> dict:
    snap = page.evaluate("() => window.__celHeroFirst || null")
    return snap if isinstance(snap, dict) else {}


def analysis_hero_samples(page) -> list[str]:
    samples = page.evaluate("() => window.__celHeroSamples || []") or []
    return [str(item) for item in samples]


def wait_for_analysis_progress(page, *, timeout: float = 20.0) -> None:
    """Wait for the analysis page in the main view, not a hidden sidebar title."""
    page.wait_for_function(
        """() => {
          if (document.querySelector('[data-cel-analysis-view="1"]')) return true;
          if (document.querySelector('.cel-analysis-view')) return true;
          const main = document.querySelector('[data-testid="stMain"]')
            || document.querySelector('[data-testid="stAppViewContainer"]');
          const text = main ? (main.innerText || '') : '';
          return /正在分析你的資料|Analyzing your data/.test(text);
        }""",
        timeout=int(timeout * 1000),
    )


def wait_for_analysis_view_unmounted(page, *, timeout: float = 180.0) -> None:
    page.wait_for_function(
        """() => {
          if (document.querySelector('[data-cel-analysis-view="1"]')) return false;
          if (document.querySelector('.cel-analysis-view')) return false;
          const main = document.querySelector('[data-testid="stMain"]')
            || document.querySelector('[data-testid="stAppViewContainer"]');
          const text = main ? (main.innerText || '') : '';
          return !/正在分析你的資料|Analyzing your data/.test(text);
        }""",
        timeout=int(timeout * 1000),
    )


def wait_for_hero_first_attach(page, *, timeout: float = 30.0) -> dict:
    page.wait_for_function(
        "() => window.__celHeroFirst !== null",
        timeout=int(timeout * 1000),
    )
    return analysis_hero_first_snapshot(page)


def wait_for_hero_countup_mid(page, *, timeout: float = 10.0) -> str:
    page.wait_for_function(
        """() => {
          const el = document.querySelector('[data-cel-hero-emissions="1"]');
          if (!el) return false;
          const text = (el.textContent || '').trim();
          const target = parseFloat(el.getAttribute('data-cel-target') || 'NaN');
          const value = parseFloat(text.replace(/,/g, ''));
          return Number.isFinite(value) && Number.isFinite(target)
            && value > 0 && value < target;
        }""",
        timeout=int(timeout * 1000),
    )
    hero = page.locator('[data-cel-hero-emissions="1"]').first
    return (hero.inner_text() or "").strip()


def assert_english_nav_readable(page) -> None:
    full = "Emissions Data & Calculations"
    link = page.locator('[data-testid="stSidebarNavLink"]').filter(
        has_text=re.compile(r"Emissions Data")
    )
    assert link.count() >= 1, "English emissions nav link missing"
    text = (link.first.inner_text() or "").replace("\n", " ")
    collapsed = re.sub(r"\s+", " ", text).strip()
    assert full in collapsed, f"full English nav name not readable: {collapsed!r}"
    assert "Cal..." not in collapsed
    assert "…" not in collapsed
    box = link.first.bounding_box()
    sidebar = page.locator('[data-testid="stSidebar"]').first.bounding_box()
    assert box is not None and sidebar is not None
    assert box["x"] + box["width"] <= sidebar["x"] + sidebar["width"] + 2
    reports = page.locator('[data-testid="stSidebarNavLink"]').filter(
        has_text=re.compile(r"Reporting")
    )
    if reports.count():
        other = reports.first.bounding_box()
        if other is not None:
            assert box["y"] + box["height"] <= other["y"] + 4, (
                "English nav label overlaps the next item"
            )


def clear_durable_browser_state(page) -> None:
    """Forget the durable onboarding record for this browser profile.

    The hydration bridge reloads once per fresh load, which can destroy the
    execution context mid-evaluate, so the clear is retried.
    """
    for _ in range(4):
        try:
            page.evaluate(
                "() => { try { localStorage.clear(); sessionStorage.clear(); }"
                " catch (e) {} }"
            )
            return
        except Exception:  # noqa: BLE001 - navigation raced the evaluate
            page.wait_for_timeout(500)


def _goto_app(page, base: str) -> None:
    """Navigate to the app, tolerating the onboarding hydrate location.replace."""
    try:
        page.goto(base, wait_until="domcontentloaded")
    except Exception as exc:  # noqa: BLE001 - hydrate replace aborts the first load
        msg = str(exc).lower()
        if not any(
            token in msg
            for token in (
                "err_aborted",
                "interrupted",
                "ns_binding_aborted",
                "frame was detached",
            )
        ):
            raise
    page.wait_for_selector('[data-testid="stApp"]', timeout=30_000)
    wait_streamlit_idle(page)


def open_fresh_app(page) -> None:
    base = page._cel_base_url  # type: ignore[attr-defined]
    last_error: Exception | None = None
    for _ in range(3):
        try:
            page.context.clear_cookies()
            try:
                page.goto("about:blank")
            except Exception:  # noqa: BLE001
                pass
            _goto_app(page, base)
            clear_durable_browser_state(page)
            page.context.clear_cookies()
            try:
                page.goto("about:blank")
            except Exception:  # noqa: BLE001
                pass
            _goto_app(page, base)
            page.wait_for_selector("text=Carbon Evidence Ledger", timeout=30_000)
            page.wait_for_timeout(1000)
            dismiss_tutorial_if_present(page)
            page.get_by_role(
                "button",
                name=re.compile(
                    r"開始公司設定|使用示範資料|Start company|Try demo"
                ),
            ).first.wait_for(state="visible", timeout=20_000)
            return
        except Exception as exc:  # noqa: BLE001 - retry a fully new session
            last_error = exc
    if last_error is not None:
        raise last_error


def safe_scroll_into_view(locator) -> None:
    """Scroll if possible; ignore Streamlit node replacement during reruns."""
    try:
        locator.scroll_into_view_if_needed(timeout=3_000)
    except Exception:  # noqa: BLE001
        pass


def defer_boundary_wizard_if_present(page) -> None:
    """Leave the 4.2H wizard via 稍後處理 so older result journeys can continue."""
    calendar = page.locator('[data-baseweb="calendar"]')
    if calendar.count() and calendar.first.is_visible():
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)
    later = page.get_by_role(
        "button", name=re.compile(r"^稍後處理$|^Do this later$")
    )
    if later.count() == 0:
        return
    later.first.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_timeout(300)


def click_button(page, label: str) -> None:
    page.get_by_role("button", name=label).first.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_timeout(400)


def seed_confirmed_pdf_workspace(root: Path, *, year: int = 2025) -> None:
    """Write a confirmed ReportingPeriod so commercial PDF export can open."""
    from carbon_ledger.company_workspace import CompanyWorkspace
    from carbon_ledger.inventory_boundary import (
        MEMBERSHIP_INCLUDED,
        PURPOSE_MOENV_FACILITY,
        REQUIREMENT_VOLUNTARY,
        FacilityMembership,
        InventoryBoundary,
        LegalEntityMembership,
        ReportingPeriod,
    )
    from carbon_ledger.legal_entity import CONFIRMATION_LOCAL, LegalEntity

    period = ReportingPeriod.confirmed(
        reporting_year_suggested=year,
        reporting_year_confirmed=year,
        period_start_confirmed=f"{year}-01-01",
        period_end_confirmed=f"{year}-12-31",
    )
    entity = LegalEntity(
        entity_id="entity_report",
        legal_name="長興材料工業股份有限公司",
        jurisdiction="TW",
        taiwan_ubn=STUB_ALIGNED_UBN,
        confirmation_state=CONFIRMATION_LOCAL,
        locally_confirmed_at="2026-08-01T00:00:00Z",
        responsible_contact_name="測試聯絡人",
        responsible_job_title="永續主管",
    )
    confirmed = InventoryBoundary(
        boundary_id="report_e2e_boundary",
        purpose=PURPOSE_MOENV_FACILITY,
        requirement_status=REQUIREMENT_VOLUNTARY,
        display_name="已確認盤查範圍",
        reporting_period=period,
        legal_entities=(entity,),
        entity_memberships=(
            LegalEntityMembership(
                entity_id=entity.entity_id,
                state=MEMBERSHIP_INCLUDED,
            ),
        ),
        facility_memberships=(
            FacilityMembership(facility_id="高雄廠", state=MEMBERSHIP_INCLUDED),
        ),
        organizational_approach="營運控制權法",
        responsible_contact_name="測試聯絡人",
        responsible_job_title="永續主管",
        schema_version="inventory-boundary-v1",
    ).locally_confirmed(at="2026-08-01T00:00:00Z")
    workspace = CompanyWorkspace.for_company(
        root=root, taiwan_ubn=STUB_ALIGNED_UBN
    )
    try:
        workspace.append_locally_confirmed(confirmed)
    except FileExistsError:
        pass


def seed_confirmed_boundary_semantics(root: Path, *, year: int = 2026) -> None:
    """Write the wizard's own locally confirmed period package.

    Same artifact ``append_semantics_current`` produces after the customer
    confirms the reporting period and inventory scope, so onboarding step 1
    reads a real confirmation instead of a faked flag.
    """
    from dataclasses import replace

    from carbon_ledger.applicability import ApplicabilityAssessment
    from carbon_ledger.company_master import CompanyMaster
    from carbon_ledger.company_workspace import (
        CompanyWorkspace,
        workspace_id_for_company,
    )
    from carbon_ledger.inventory_boundary import (
        ReportingPeriod,
        initial_boundary_semantics_state,
    )

    period = ReportingPeriod.confirmed(
        reporting_year_suggested=year,
        reporting_year_confirmed=year,
        period_start_confirmed=f"{year}-01-01",
        period_end_confirmed=f"{year}-12-31",
    )
    workspace_id = workspace_id_for_company(taiwan_ubn=STUB_ALIGNED_UBN)
    assessment = ApplicabilityAssessment(
        assessment_timestamp=f"{year}-01-01T00:00:00Z",
        reporting_year=year,
        company_profile_snapshot={},
        obligations={},
        rule_ids_used=[],
        rule_versions_used={},
        regulatory_freshness_snapshot={},
        result_statuses={},
    )
    state = initial_boundary_semantics_state(
        assessment=assessment,
        company=CompanyMaster(
            company_id=f"co_{STUB_ALIGNED_UBN}",
            company_name="長興材料工業股份有限公司",
            unified_business_number=STUB_ALIGNED_UBN,
            listing_status="TWSE",
        ),
        facilities=[],
        workspace_id=workspace_id,
        reporting_period=period,
    )
    confirmed = replace(
        state,
        responsible_contact_name="測試聯絡人",
        responsible_job_title="永續主管",
    ).locally_confirmed(at=f"{year}-02-01T00:00:00Z")
    try:
        CompanyWorkspace(root, workspace_id).append_semantics_current(confirmed)
    except FileExistsError:
        pass


def confirm_stub_company_for_pdf(page) -> None:
    start = page.get_by_role("button", name=re.compile(r"開始公司設定|Start setup"))
    if start.count():
        start.first.click(force=True)
        wait_streamlit_idle(page)
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    wait_streamlit_idle(page)


def lookup_stub_company(page, ubn: str) -> None:
    """Enter a stub UBN, look up official data, and confirm the company."""
    field = page.get_by_label(re.compile(r"統一編號|Unified business number"))
    if field.count():
        field.first.fill(ubn)
    else:
        page.locator('input[type="text"]').first.fill(ubn)
    wait_streamlit_idle(page)
    lookup = page.get_by_role(
        "button", name=re.compile(r"查詢公司|Look up company")
    )
    lookup.first.wait_for(state="visible", timeout=15_000)
    lookup.first.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_timeout(400)
    confirm = page.get_by_role(
        "button", name=re.compile(r"這是我的公司|This is my company")
    )
    if confirm.count():
        confirm.first.click(force=True)
        wait_streamlit_idle(page)
        page.wait_for_timeout(300)
    entity_boxes = page.locator('[data-testid="stSelectbox"]').filter(
        has_text=re.compile(r"公司類型|Entity type")
    )
    if entity_boxes.count():
        entity_text = entity_boxes.first.inner_text()
        option_label = (
            "General listed company (TWSE)"
            if "Entity type" in entity_text
            else "一般上市公司"
        )
        control = entity_boxes.first.locator(
            '[data-baseweb="select"], [role="combobox"], input'
        ).first
        if control.count():
            control.click(force=True)
            page.wait_for_timeout(400)
        option = page.get_by_role("option", name=option_label)
        if option.count() == 0:
            page.keyboard.press("Escape")
        else:
            option.first.click(force=True)
            wait_streamlit_idle(page)
            page.wait_for_timeout(300)


def save_step_screenshot(
    page, name: str, *, required: bool = False, full_page: bool = True
) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=full_page, timeout=15_000)
    except Exception:  # noqa: BLE001 - retry a simpler capture
        if required:
            page.screenshot(path=str(path), full_page=False, timeout=15_000)
        else:
            try:
                page.screenshot(path=str(path), full_page=False, timeout=8_000)
            except Exception:  # noqa: BLE001 - optional screenshots must not fail
                pass
    if required:
        assert path.is_file() and path.stat().st_size > 0, (
            f"required screenshot missing or empty: {path}"
        )
    return path


def visible_text(page) -> str:
    return page.locator("body").inner_text()


def parse_metric_number(text: str) -> float:
    """Parse the first numeric value from a KPI's visible text."""
    cleaned = (text or "").replace(",", "").replace(" ", "")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return float("nan")
    return float(match.group(0))


def fill_streamlit_date(page, label: str, value: str) -> None:
    """Commit a Streamlit date widget; do not cancel the calendar with Escape."""
    root = page.locator('[data-testid="stDateInput"]').filter(
        has_text=re.compile(re.escape(label))
    )
    if root.count() == 0:
        root = page.locator('[data-testid="stDateInput"]')
    if root.count() == 0:
        return
    field = root.locator("input").first
    field.click(force=True)
    page.wait_for_timeout(200)
    slash = value.replace("-", "/")
    field.fill(slash)
    field.press("Enter")
    page.wait_for_timeout(250)
    day = str(int(value.split("-")[2]))
    calendar = page.locator('[data-baseweb="calendar"]')
    if calendar.count() and calendar.first.is_visible():
        cell = calendar.get_by_text(day, exact=True)
        if cell.count():
            cell.last.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_timeout(300)


NG_CUSTOMER_LABEL = {
    "NG1": "NG1——帳單或契約標示為 NG1",
    "NG2": "NG2——帳單或契約標示為 NG2",
}
NG_CUSTOMER_LABEL_EN = {
    "NG1": "NG1 — the bill or contract is labelled NG1",
    "NG2": "NG2 — the bill or contract is labelled NG2",
}
DIESEL_CUSTOMER_LABEL = "公司車輛／公司控制的移動燃燒"
DIESEL_CUSTOMER_LABEL_EN = (
    "Company vehicle / company-controlled mobile combustion"
)
ELECTRICITY_CUSTOMER_LABEL = "企業／廠場盤查"
ELECTRICITY_CUSTOMER_LABEL_EN = "Enterprise / site inventory"
NAV_EVIDENCE = r"排放資料與計算|Emissions Data"
INTAKE_APPLY = r"確認並前往下一題|Confirm and go to the next question"
INTAKE_EDITOR = r"修改系統辨識結果|Edit recognition"
INTAKE_CONTINUE = (
    r"完成確認並檢查資料|Finish confirmation|"
    r"^繼續$|^Continue$|確認並繼續|Confirm and continue"
)
INTAKE_START = (
    r"使用這批資料開始分析|Analyze this uploaded|"
    r"開始分析|Start analysis"
)


def open_emissions_data_nav(page) -> None:
    page.get_by_role("link", name=re.compile(NAV_EVIDENCE)).first.click()
    wait_streamlit_idle(page)


def _hold_unknown_activity_if_present(page) -> None:
    """Commit the customer hold option when an unknown-activity question is open."""
    body = visible_text(page)
    if (
        "哪一種活動" not in body
        and "which activity" not in body.lower()
        and "what activity" not in body.lower()
    ):
        return
    unknown = re.compile(r"還不確定（相關列暫不計算）|Not sure yet")
    boxes = page.locator('[data-testid="stSelectbox"]')
    for index in range(boxes.count()):
        box = boxes.nth(index)
        label = box.inner_text()
        if "其他資料功能" in label:
            continue
        control = box.locator(
            '[data-baseweb="select"], [role="combobox"], input'
        ).first
        if control.count() == 0:
            continue
        control.scroll_into_view_if_needed()
        control.click()
        listbox = page.get_by_role("listbox")
        listbox.first.wait_for(state="visible", timeout=10_000)
        option = listbox.first.get_by_role("option").filter(has_text=unknown)
        if option.count() == 0:
            option = page.get_by_role("option").filter(has_text=unknown)
        if option.count() == 0:
            page.keyboard.press("Escape")
            continue
        option.first.click()
        try:
            listbox.first.wait_for(state="hidden", timeout=8_000)
        except Exception:  # noqa: BLE001
            page.keyboard.press("Escape")
            listbox.first.wait_for(state="hidden", timeout=5_000)
        wait_streamlit_idle(page)
        return
    page.keyboard.press("Escape")


def resolve_intake_exceptions(page, *, ng_choice: str = "NG1") -> None:
    """Apply visible exception-queue answers without opening the mapping editor."""
    apply_re = re.compile(INTAKE_APPLY)
    ng_labels = [
        NG_CUSTOMER_LABEL.get(ng_choice, ng_choice),
        NG_CUSTOMER_LABEL_EN.get(ng_choice, ng_choice),
        ng_choice,
    ]
    diesel_labels = (DIESEL_CUSTOMER_LABEL, DIESEL_CUSTOMER_LABEL_EN)
    elec_labels = (ELECTRICITY_CUSTOMER_LABEL, ELECTRICITY_CUSTOMER_LABEL_EN)
    for _ in range(16):
        apply_btns = page.get_by_role("button", name=apply_re)
        if apply_btns.count() == 0:
            return
        radios = page.locator('[data-testid="stRadioOption"]')
        for label in ng_labels:
            if label and radios.filter(has_text=label).count():
                choose_radio(page, label)
                break
        for label in diesel_labels:
            if radios.filter(has_text=label).count():
                choose_radio(page, label)
                break
        for label in elec_labels:
            if radios.filter(has_text=label).count():
                choose_radio(page, label)
                break
        _hold_unknown_activity_if_present(page)
        apply_btns = page.get_by_role("button", name=apply_re)
        if apply_btns.count() == 0:
            return
        apply_btns.first.evaluate(
            "el => { el.scrollIntoView({block:'center'}); el.click(); }"
        )
        wait_streamlit_idle(page, timeout=40)


def wait_for_intake_coverage(page, *, timeout: float = 120.0) -> None:
    """Wait until coverage review is visible after intake validation."""
    page.get_by_text(
        re.compile(
            r"可納入計算|Included in calculation|Ready to calculate"
        )
    ).first.wait_for(state="visible", timeout=int(timeout * 1000))
    wait_streamlit_idle(page, timeout=40)


def click_finish_intake_confirmation(page) -> None:
    """Two-round intake validation: click, then wait for coverage review."""
    page.get_by_role(
        "button",
        name=re.compile(r"完成確認並檢查資料|Finish confirmation"),
    ).first.click(force=True)
    page.wait_for_function(
        """() => {
          const text = document.body ? document.body.innerText : '';
          const processing = /正在檢查你的資料|Checking your data/.test(text);
          const coverage = /可納入計算|Included in calculation/.test(text);
          return processing || coverage;
        }""",
        timeout=20_000,
    )
    wait_for_intake_coverage(page)


def confirm_intake_reading(page, *, ng_choice: str = "NG1") -> None:
    """Resolve remaining exceptions, then continue from the file-read result."""
    page.get_by_text(re.compile(r"資料已讀取|File read successfully")).first.wait_for(
        state="visible", timeout=20_000
    )
    resolve_intake_exceptions(page, ng_choice=ng_choice)
    btn = page.get_by_role(
        "button",
        name=re.compile(r"完成確認並檢查資料|Finish confirmation"),
    )
    if btn.count():
        click_finish_intake_confirmation(page)
        return
    wait_for_intake_coverage(page)


def start_uploaded_coverage_analysis(page) -> None:
    """Start calculation from coverage review without a customer step 5."""
    start = page.get_by_role(
        "button",
        name=re.compile(r"使用這批資料開始分析|Analyze this uploaded"),
    )
    if start.count() == 0:
        start = page.get_by_role("button", name=re.compile(INTAKE_START))
    start.first.wait_for(state="visible", timeout=20_000)
    start.first.evaluate(
        "el => { el.scrollIntoView({block: 'center', inline: 'nearest'}); el.click(); }"
    )
    wait_streamlit_idle(page, timeout=90)


def open_intake_mapping_editor(page) -> None:
    btn = page.get_by_role(
        "button", name=re.compile(INTAKE_EDITOR)
    )
    if btn.count():
        btn.first.click(force=True)
        wait_streamlit_idle(page, timeout=40)


def choose_radio(page, option_label: str) -> None:
    """Select a Streamlit radio option by its visible label."""
    last_error: Exception | None = None
    for _ in range(4):
        option = page.locator('[data-testid="stRadioOption"]').filter(
            has_text=re.compile(rf"^{re.escape(option_label)}$")
        )
        if option.count() == 0:
            option = page.get_by_text(option_label, exact=True)
        try:
            option.first.wait_for(state="visible", timeout=15_000)
            option.first.evaluate(
                "el => { el.scrollIntoView({block:'center'}); el.click(); }"
            )
            wait_streamlit_idle(page)
            page.wait_for_timeout(250)
            return
        except Exception as exc:  # noqa: BLE001 - Streamlit reruns detach radios
            last_error = exc
            wait_streamlit_idle(page)
            page.wait_for_timeout(300)
    if last_error:
        raise last_error


def choose_selectbox(page, field_label: str, option_label: str) -> None:
    """Select an option from a Streamlit stSelectbox by field label."""
    root = page.locator('[data-testid="stSelectbox"]').filter(
        has_text=re.compile(re.escape(field_label))
    )
    assert root.count() >= 1, f"selectbox not found for {field_label!r}"
    control = root.first.locator(
        '[data-baseweb="select"], [role="combobox"], input'
    ).first
    if control.count():
        control.click(force=True)
    else:
        root.first.click(force=True)
    page.wait_for_timeout(500)
    option = page.get_by_role("option", name=option_label)
    if option.count() == 0:
        option = page.get_by_text(option_label, exact=True)
    assert option.count() >= 1, f"option not found: {option_label!r}"
    option.first.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_timeout(450)


def open_evidence_workspace_tool(page, option_label: str) -> None:
    """Open a populated post-analysis page via its customer-facing CTA."""
    wait_streamlit_idle(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    patterns = {
        "活動資料": r"查看活動資料|View activities",
        "待處理問題": r"^查看問題$|^View issues$",
        "證據紀錄": r"查看佐證文件|View supporting documents|查看文件|View files",
    }
    pattern = patterns[option_label]
    button = page.get_by_role("button", name=re.compile(pattern))
    if button.count() == 0 and option_label == "活動資料":
        button = page.get_by_role(
            "button",
            name=re.compile(
                r"查看計算依據|View calculation basis|"
                r"係數與版本|Factors and version"
            ),
        )
    if button.count() == 0 and option_label == "待處理問題":
        button = page.get_by_role(
            "button",
            name=re.compile(r"查看待處理問題"),
        )
    if button.count() == 0 and option_label == "證據紀錄":
        button = page.get_by_role(
            "button",
            name=re.compile(r"^查看證據$|^View evidence"),
        )
    button.first.wait_for(state="visible", timeout=15_000)
    button.first.click()
    wait_streamlit_idle(page)
    page.wait_for_timeout(300)


def set_money_unknown(page, *, index: int, unknown: bool) -> None:
    """Toggle the Nth「不知道 / 暫不填」checkbox via its label (Streamlit RAC)."""
    labels = page.locator("label").filter(has_text=re.compile(r"不知道|leave blank"))
    assert labels.count() > index
    label = labels.nth(index)
    selected = (label.get_attribute("data-selected") or "").lower() == "true"
    if selected != unknown:
        label.click(force=True)
        wait_streamlit_idle(page)
        page.wait_for_timeout(300)


def fill_money_amount(page, *, index: int, amount: str) -> None:
    """Fill the Nth visible money text input after unknown is unchecked."""
    inputs = page.locator('[data-testid="stTextInput"] input')
    assert inputs.count() > index
    inputs.nth(index).fill(amount)
    wait_streamlit_idle(page)
    page.wait_for_timeout(250)
