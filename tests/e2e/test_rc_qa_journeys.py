"""RC QA Playwright journeys: state leak, count-up order, chaos, viewports."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
TESTS_DIR = E2E_DIR.parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from helpers import (  # noqa: E402
    APPLICABILITY_NAV,
    ARTIFACTS,
    NG_CUSTOMER_LABEL,
    assert_no_app_errors,
    assert_no_engineering_leak,
    assert_no_raw_html_leak,
    choose_radio,
    click_button,
    confirm_intake_reading,
    fill_streamlit_date,
    open_fresh_app,
    open_intake_mapping_editor,
    parse_metric_number,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)
from test_customer_journeys import (  # noqa: E402
    _backend_total_for_csv,
    _stage41_csv,
    _walk_stage41_intake,
)

pytestmark = pytest.mark.e2e


def _write_csv(name: str, text: str) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(text, encoding="utf-8")
    return path


def _open_intake_uploader(page) -> None:
    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    if uploader.count():
        return
    edit = page.get_by_role("button", name=re.compile(r"^修改$|^Edit$"))
    if edit.count():
        edit.first.click(force=True)
        wait_streamlit_idle(page)


def _hero_target(page) -> float:
    hero = page.locator("[data-cel-hero-emissions='1']").first
    hero.wait_for(state="visible", timeout=30_000)
    return float(hero.get_attribute("data-cel-target") or "nan")


def _no_overflow(page) -> None:
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth > "
        "document.documentElement.clientWidth + 2"
    )
    assert overflow is False, "horizontal overflow"


def test_rc_empty_customer_no_demo_or_leaks(page) -> None:
    open_fresh_app(page)
    for name in (
        r"合規總覽|Compliance",
        APPLICABILITY_NAV,
        r"IFRS",
        r"台灣|Taiwan",
        r"證據與資料|Evidence",
        r"報表|Reporting|匯出",
    ):
        page.get_by_role("link", name=re.compile(name)).first.click()
        wait_streamlit_idle(page)
        body = visible_text(page)
        assert "Demo Fasteners" not in body
        assert "23.7" not in body
        assert "Traceback" not in body
        assert_no_raw_html_leak(body)
        assert_no_engineering_leak(body)
        assert_no_app_errors(page)


def test_rc_progress_modal_then_countup_both_scopes(page) -> None:
    page.emulate_media(reduced_motion="no-preference")
    csv_path = _write_csv("rc_countup.csv", _stage41_csv(ng_cell="天然氣"))
    open_fresh_app(page)
    _walk_stage41_intake(page, csv_path, ng_choice="NG1")
    expected = _backend_total_for_csv(csv_path, ng_subtype="NG1")
    rerun = page.get_by_role("button", name=re.compile(r"重新分析|Re-run"))
    rerun.first.click(force=True)
    dialog = page.get_by_role("dialog")
    dialog.first.wait_for(state="visible", timeout=15_000)
    body = visible_text(page)
    assert any(
        token in body for token in ("讀取", "標準化", "配對", "計算", "正在分析")
    )

    def _near_zero(value: float, final: float) -> bool:
        return value <= max(0.08 * abs(final), 1.0)

    def _dialog_hidden() -> bool:
        return dialog.count() == 0 or not dialog.first.is_visible()

    hero_loc = page.locator("[data-cel-hero-emissions='1']")
    found_zero = False
    target = float("nan")
    deadline = time.time() + 30.0
    while time.time() <= deadline:
        if not _dialog_hidden() or hero_loc.count() == 0:
            page.wait_for_timeout(20)
            continue
        snaps = hero_loc.evaluate_all(
            """els => els.map(el => ({
              play: el.getAttribute('data-cel-hero-play'),
              text: el.textContent || '',
              target: el.getAttribute('data-cel-target'),
            }))"""
        )
        for snap in snaps:
            target = float(snap.get("target") or "nan")
            start_val = parse_metric_number(str(snap.get("text") or ""))
            if snap.get("play") == "1" and _near_zero(start_val, target):
                found_zero = True
                break
        if found_zero:
            break
        page.wait_for_timeout(20)
    assert found_zero, "hero was not near 0 after dialog hidden"
    assert target == pytest.approx(expected)
    scope1 = page.locator('[data-cel-kpi-key="scope-1"]').first
    scope2 = page.locator('[data-cel-kpi-key="scope-2"]').first
    scope1.wait_for(state="visible", timeout=5_000)
    scope2.wait_for(state="visible", timeout=5_000)
    assert float(scope1.get_attribute("data-cel-target") or 0) > 0
    assert float(scope2.get_attribute("data-cel-target") or 0) > 0
    page.wait_for_timeout(1800)
    body = visible_text(page)
    assert_no_raw_html_leak(body)
    assert_no_engineering_leak(body)
    assert_no_app_errors(page)


def test_rc_reupload_replaces_previous_result(page) -> None:
    csv_a = _write_csv("rc_file_a.csv", _stage41_csv(ng_cell="天然氣"))
    csv_b = _write_csv(
        "rc_file_b.csv",
        (
            "活動類型,用量,單位,開始日期,結束日期,廠場\n"
            "外購電力,1000,kWh,2025-01-01,2025-01-31,高雄廠\n"
            "天然氣 NG2,100,m3,2025-01-01,2025-01-31,高雄廠\n"
            "柴油,10,L,2025-01-01,2025-01-31,高雄廠\n"
        ),
    )
    open_fresh_app(page)
    _walk_stage41_intake(page, csv_a, ng_choice="NG1")
    total_a = _hero_target(page)
    _open_intake_uploader(page)
    _walk_stage41_intake(page, csv_b, ng_choice="NG2")
    total_b = _hero_target(page)
    assert total_a != total_b
    expected_b = _backend_total_for_csv(csv_b, ng_subtype="NG2")
    assert total_b == pytest.approx(expected_b)
    assert_no_app_errors(page)


def test_rc_language_english_smoke(page) -> None:
    open_fresh_app(page)
    en = page.get_by_text("EN", exact=True)
    if en.count():
        en.first.click(force=True)
        wait_streamlit_idle(page)
    body = visible_text(page)
    assert "nav.dashboard" not in body
    assert "dash.kpi" not in body
    assert_no_engineering_leak(body)
    start = page.get_by_role(
        "button", name=re.compile(r"Start company|Get started|開始")
    )
    assert start.count() >= 1
    assert_no_app_errors(page)


@pytest.mark.parametrize("width,height", [(1366, 768), (1440, 900), (1920, 1080)])
def test_rc_viewport_smoke(page, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    csv_path = _write_csv("rc_viewport.csv", _stage41_csv(ng_cell="天然氣"))
    open_fresh_app(page)
    _walk_stage41_intake(page, csv_path, ng_choice="NG1")
    page.locator("[data-cel-hero-emissions='1']").first.wait_for(
        state="visible", timeout=30_000
    )
    sidebar = page.locator('[data-testid="stSidebar"]')
    assert sidebar.count() >= 1
    rerun = page.get_by_role("button", name=re.compile(r"重新分析|Re-run|開始分析"))
    assert rerun.count() >= 1
    _no_overflow(page)
    body = visible_text(page)
    assert_no_raw_html_leak(body)
    assert_no_app_errors(page)


def test_rc_chaos_journey(page) -> None:
    from rc_qa_support import dataset_c_csv

    csv_path = _write_csv("rc_chaos_c.csv", dataset_c_csv(rows=150))
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    page.wait_for_timeout(400)
    name = page.get_by_label(re.compile(r"公司名稱|Company name"))
    if name.count():
        name.first.fill("RC Chaos Co")
        wait_streamlit_idle(page)
    page.get_by_role("link", name=re.compile(r"證據與資料|Evidence")).first.click()
    wait_streamlit_idle(page)
    _open_intake_uploader(page)
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(csv_path))
    wait_streamlit_idle(page, timeout=40)
    confirm_intake_reading(page)
    back = page.get_by_role("button", name=re.compile(r"上一步|Back"))
    if back.count():
        back.first.click(force=True)
        wait_streamlit_idle(page)
    nxt = page.get_by_role(
        "button", name=re.compile(r"確認並繼續|Continue|下一步")
    )
    if nxt.count():
        nxt.first.click(force=True)
        wait_streamlit_idle(page, timeout=40)
    ng_help = page.get_by_text("NG1 與 NG2 的官方年度熱值", exact=False)
    if ng_help.count() == 0:
        open_intake_mapping_editor(page)
        ng_help = page.get_by_text("NG1 與 NG2 的官方年度熱值", exact=False)
    if ng_help.count():
        choose_radio(page, NG_CUSTOMER_LABEL["NG2"])
        if page.get_by_text("公司車輛／公司控制的移動燃燒", exact=False).count():
            choose_radio(page, "公司車輛／公司控制的移動燃燒")
        if page.get_by_text("企業／廠場盤查", exact=False).count():
            choose_radio(page, "企業／廠場盤查")
        validate = page.get_by_role(
            "button", name=re.compile(r"資料格式檢查|Check data format")
        )
        if validate.count():
            validate.first.click(force=True)
            wait_streamlit_idle(page, timeout=40)
        nxt = page.get_by_role("button", name=re.compile(r"下一步|Next"))
        if nxt.count():
            nxt.first.click(force=True)
            wait_streamlit_idle(page)
    start = page.get_by_role("button", name=re.compile(r"開始分析|Start analysis"))
    if start.count():
        start.first.click(force=True)
        dialog = page.get_by_role("dialog")
        if dialog.count():
            try:
                dialog.first.wait_for(state="hidden", timeout=120_000)
            except Exception:  # noqa: BLE001
                pass
        wait_streamlit_idle(page, timeout=120)
    for name in (
        r"合規總覽|Compliance",
        r"證據與資料|Evidence",
        r"報表|Reporting|匯出",
    ):
        page.get_by_role("link", name=re.compile(name)).first.click()
        wait_streamlit_idle(page)
        body = visible_text(page)
        assert_no_raw_html_leak(body)
        assert "Traceback" not in body
    replacement = _write_csv("rc_chaos_replace.csv", _stage41_csv(ng_cell="天然氣 NG1"))
    _open_intake_uploader(page)
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(replacement))
    assert_no_app_errors(page)
    save_step_screenshot(page, "rc_chaos_end")


def _walk_ng_file_to_validation(page, csv_path: Path) -> None:
    _open_intake_uploader(page)
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(csv_path))
    wait_streamlit_idle(page, timeout=40)
    page.wait_for_timeout(700)
    confirm_intake_reading(page)
    ng_help = page.get_by_text("NG1 與 NG2 的官方年度熱值", exact=False)
    if ng_help.count() == 0:
        open_intake_mapping_editor(page)
    ng_help.first.wait_for(state="visible", timeout=20_000)
    choose_radio(page, NG_CUSTOMER_LABEL["NG1"])
    if page.get_by_text("公司車輛／公司控制的移動燃燒", exact=False).count():
        choose_radio(page, "公司車輛／公司控制的移動燃燒")
    if page.get_by_text("企業／廠場盤查", exact=False).count():
        choose_radio(page, "企業／廠場盤查")
    fill_streamlit_date(page, "文件日期", "2025-01-31")
    page.get_by_text("請確認文件日期", exact=False).first.wait_for(
        state="hidden", timeout=15_000
    )
    validate = page.get_by_role(
        "button", name=re.compile(r"資料格式檢查|Check data format")
    )
    assert validate.count() >= 1
    validate.first.click(force=True)
    wait_streamlit_idle(page, timeout=40)


def _start_uploaded_analysis(page) -> None:
    nxt = page.get_by_role("button", name=re.compile(r"下一步|Next"))
    nxt.first.wait_for(state="visible", timeout=20_000)
    nxt.first.click(force=True)
    wait_streamlit_idle(page)
    start = page.get_by_role(
        "button", name=re.compile(r"開始分析|Start analysis")
    )
    start.first.wait_for(state="visible", timeout=20_000)
    start.first.click(force=True)
    dialog = page.get_by_role("dialog")
    try:
        dialog.first.wait_for(state="visible", timeout=15_000)
    except Exception:  # noqa: BLE001
        pass
    wait_streamlit_idle(page, timeout=120)
    page.get_by_text("排放資料摘要", exact=False).first.wait_for(
        state="visible", timeout=60_000
    )
    if dialog.count():
        dialog.first.wait_for(state="hidden", timeout=30_000)
    page.wait_for_timeout(800)


def test_rc_potential_duplicate_review_then_reupload(page) -> None:
    open_fresh_app(page)
    dup_csv = (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    )
    clean_csv = (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    )
    dup_path = _write_csv("rc_dup_lookalike.csv", dup_csv)
    clean_path = _write_csv("rc_dup_clean.csv", clean_csv)
    expected = _backend_total_for_csv(clean_path, ng_subtype="NG1")

    _walk_ng_file_to_validation(page, dup_path)
    body = visible_text(page)
    assert "發現可能重複的資料" in body
    assert "重複資料可能造成排放量重複計算" in body
    nxt = page.get_by_role("button", name=re.compile(r"下一步|Next"))
    assert nxt.count() == 0
    page.get_by_role("button", name=re.compile(r"查看並確認")).first.click(force=True)
    wait_streamlit_idle(page)
    choose_radio(page, "這是重複匯入 → 排除重複列")
    assert_no_engineering_leak(visible_text(page))
    _start_uploaded_analysis(page)
    actual = _hero_target(page)
    assert actual == pytest.approx(expected, rel=1e-6, abs=1e-9)
    save_step_screenshot(page, "rc_dup_excluded_total")

    _walk_ng_file_to_validation(page, clean_path)
    clean_body = visible_text(page)
    assert "發現可能重複的資料" not in clean_body
    _start_uploaded_analysis(page)
    clean_actual = _hero_target(page)
    assert clean_actual == pytest.approx(expected, rel=1e-6, abs=1e-9)
    assert_no_app_errors(page)
