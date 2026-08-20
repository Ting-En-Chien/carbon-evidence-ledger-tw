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
    button = page.get_by_role(
        "button",
        name=re.compile(
            r"開始使用|稍後再看|Get started|Maybe later|Start using the product"
        ),
    )
    if button.count():
        button.first.click(force=True)
        wait_streamlit_idle(page)
        page.wait_for_timeout(500)


def open_fresh_app(page) -> None:
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
    page.wait_for_timeout(1000)
    dismiss_tutorial_if_present(page)
    page.get_by_role(
        "button", name=re.compile(r"開始公司設定|使用示範資料|Start company|Try demo")
    ).first.wait_for(state="visible", timeout=20_000)


def safe_scroll_into_view(locator) -> None:
    """Scroll if possible; ignore Streamlit node replacement during reruns."""
    try:
        locator.scroll_into_view_if_needed(timeout=3_000)
    except Exception:  # noqa: BLE001
        pass


def click_button(page, label: str) -> None:
    page.get_by_role("button", name=label).first.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_timeout(400)


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
        if "Entity type" in entity_text:
            choose_selectbox(
                page, "Entity type", "General listed company (TWSE)"
            )
        else:
            choose_selectbox(page, "公司類型", "一般上市公司")


def save_step_screenshot(page, name: str, *, required: bool = False) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True, timeout=15_000)
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
    "NG1": "天然氣（環境部年度熱值分類 NG1）",
    "NG2": "天然氣（環境部年度熱值分類 NG2）",
}
DIESEL_CUSTOMER_LABEL = "公司車輛／公司控制的移動燃燒"
ELECTRICITY_CUSTOMER_LABEL = "企業／廠場盤查"


def resolve_intake_exceptions(page, *, ng_choice: str = "NG1") -> None:
    """Apply visible exception-queue answers without opening the mapping editor."""
    apply_re = re.compile(
        r"採用這個選擇|Use this choice|套用這項答案|Apply this answer"
    )
    ng_label = NG_CUSTOMER_LABEL.get(ng_choice, ng_choice)
    for _ in range(16):
        apply_btns = page.get_by_role("button", name=apply_re)
        if apply_btns.count() == 0:
            return
        radios = page.locator('[data-testid="stRadioOption"]')
        if radios.filter(has_text=ng_label).count():
            choose_radio(page, ng_label)
        if radios.filter(has_text=DIESEL_CUSTOMER_LABEL).count():
            choose_radio(page, DIESEL_CUSTOMER_LABEL)
        if radios.filter(has_text=ELECTRICITY_CUSTOMER_LABEL).count():
            choose_radio(page, ELECTRICITY_CUSTOMER_LABEL)
        apply_btns = page.get_by_role("button", name=apply_re)
        if apply_btns.count() == 0:
            return
        apply_btns.first.click(force=True)
        wait_streamlit_idle(page, timeout=40)
        page.wait_for_timeout(250)


def confirm_intake_reading(page, *, ng_choice: str = "NG1") -> None:
    """Resolve remaining exceptions, then continue from the file-read result."""
    page.get_by_text(re.compile(r"資料已讀取|File read successfully")).first.wait_for(
        state="visible", timeout=20_000
    )
    resolve_intake_exceptions(page, ng_choice=ng_choice)
    btn = page.get_by_role(
        "button",
        name=re.compile(
            r"^繼續$|^Continue$|確認並繼續|Confirm and continue"
        ),
    )
    if btn.count():
        btn.first.click(force=True)
        wait_streamlit_idle(page, timeout=40)


def open_intake_mapping_editor(page) -> None:
    btn = page.get_by_role(
        "button", name=re.compile(r"調整欄位對應|Adjust column matching")
    )
    if btn.count():
        btn.first.click(force=True)
        wait_streamlit_idle(page, timeout=40)


def choose_radio(page, option_label: str) -> None:
    """Select a Streamlit radio option by its visible label."""
    option = page.locator('[data-testid="stRadioOption"]').filter(
        has_text=re.compile(rf"^{re.escape(option_label)}$")
    )
    if option.count() == 0:
        option = page.get_by_text(option_label, exact=True)
    option.first.wait_for(state="visible", timeout=15_000)
    option.first.scroll_into_view_if_needed()
    option.first.click(force=True)
    wait_streamlit_idle(page)
    page.wait_for_timeout(250)


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
        "證據紀錄": r"查看文件|View files",
    }
    pattern = patterns[option_label]
    button = page.get_by_role("button", name=re.compile(pattern))
    if button.count() == 0 and option_label == "活動資料":
        button = page.get_by_role(
            "button",
            name=re.compile(r"查看計算依據|View calculation basis"),
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
