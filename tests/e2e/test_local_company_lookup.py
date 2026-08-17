"""Stage 4.2A — local official company snapshot customer journeys."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pytest

from carbon_ledger.company_master import ubn_checksum_ok

E2E_DIR = Path(__file__).resolve().parent
REPO_ROOT = E2E_DIR.parents[1]
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    assert_no_app_errors,
    click_button,
    open_fresh_app,
    save_step_screenshot,
    visible_text,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e
SNAPSHOT_CSV = (
    REPO_ROOT / "data" / "reference" / "company_master" / "company_master.csv"
)


def _snapshot_sample() -> tuple[str, str]:
    with SNAPSHOT_CSV.open(encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    ubn = str(row["unified_business_number"]).strip()
    name = str(row["company_name"]).strip()
    assert ubn and name
    return ubn, name


def _unused_valid_ubn() -> str:
    existing = set()
    with SNAPSHOT_CSV.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            existing.add(str(row["unified_business_number"]).strip())
    for stub in ("12345675", "13579243", "24681358"):
        existing.add(stub)
    for number in range(10_000_000, 10_050_000):
        candidate = f"{number:08d}"
        if ubn_checksum_ok(candidate) and candidate not in existing:
            return candidate
    raise AssertionError("could not find a valid UBN outside the snapshot")


def _continue_through_setup(page) -> None:
    for _ in range(4):
        body = visible_text(page)
        if "適用" in body and "你的結果" in body:
            return
        continue_btn = page.get_by_role("button", name="繼續")
        if continue_btn.count():
            click_button(page, "繼續")
            wait_streamlit_idle(page)
            continue
        break


def test_local_company_lookup_found(page) -> None:
    ubn, name = _snapshot_sample()
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    field = page.get_by_label("統一編號")
    field.first.fill(ubn)
    wait_streamlit_idle(page)
    click_button(page, "查詢公司")
    body = visible_text(page)
    assert name in body
    assert "政府公開資料" in body
    assert "資料更新至" in body
    assert "即時" not in body
    assert "GCIS" not in body
    assert "查詢失敗" not in body
    save_step_screenshot(page, "qa_local_company_lookup_found")
    click_button(page, "這是我的公司")
    save_step_screenshot(page, "qa_local_company_confirm")
    _continue_through_setup(page)
    result = visible_text(page)
    assert "適用" in result
    assert "HTTP 500" not in result
    assert_no_app_errors(page)


def test_company_not_found_keeps_factory_candidate(page) -> None:
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    page.get_by_label("統一編號").first.fill("00004131")
    wait_streamlit_idle(page)
    click_button(page, "查詢公司")
    body = visible_text(page)
    assert "目前的官方公司資料庫沒有找到這個統編。" in body
    assert "查詢失敗" not in body
    name_field = page.get_by_label("公司名稱")
    assert name_field.count()
    assert name_field.first.input_value() != "川盛信記企業股份有限公司"
    name_field.first.fill("客戶手動公司")
    wait_streamlit_idle(page)
    save_step_screenshot(page, "qa_factory_fallback_manual_company")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    sites = visible_text(page)
    expander = page.get_by_text(re.compile(r"查看找到的 1 個廠場"))
    if expander.count():
        expander.first.click(force=True)
        wait_streamlit_idle(page)
        sites = visible_text(page)
    assert "川盛信記企業股份有限公司" in sites
    assert sites.count("川盛信記企業股份有限公司") == 1
    assert "客戶手動公司" not in sites or "確認台灣廠場" in sites
    save_step_screenshot(page, "qa_factory_fallback_step3")
    assert_no_app_errors(page)


def test_local_company_lookup_not_found_manual_fallback(page) -> None:
    ubn = _unused_valid_ubn()
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    page.get_by_label("統一編號").first.fill(ubn)
    wait_streamlit_idle(page)
    click_button(page, "查詢公司")
    body = visible_text(page)
    assert "目前的官方公司資料庫沒有找到這個統編。" in body
    assert "查詢失敗" not in body
    assert "API error" not in body
    assert "HTTP" not in body
    save_step_screenshot(page, "qa_local_company_lookup_not_found")
    name_field = page.get_by_label("公司名稱")
    assert name_field.count()
    name_field.first.fill("手動輸入示範公司")
    wait_streamlit_idle(page)
    _continue_through_setup(page)
    result = visible_text(page)
    assert "適用" in result or "需要更多" in result
    assert_no_app_errors(page)
