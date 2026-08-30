"""Stage 4.2 — mocked zero-entry company and facility journeys."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    STUB_ALIGNED_UBN,
    STUB_DIFF_UBN,
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


def test_zero_entry_aligned_company_and_sites(page) -> None:
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    body = visible_text(page)
    assert "長興材料工業股份有限公司" in body
    assert "政府公開資料" in body
    assert "即時" not in body
    assert "GCIS" not in body
    assert "HTTP" not in body
    save_step_screenshot(page, "qa_zero_entry_company_lookup")
    save_step_screenshot(page, "qa_zero_entry_company_confirm")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    sites = visible_text(page)
    assert "高雄一廠" in sites or "登記工廠" in sites
    assert "全部納入本次資料" not in sites
    assert "這次如何處理？" not in sites
    assert "維持使用" not in sites
    save_step_screenshot(page, "qa_zero_entry_facilities")
    save_step_screenshot(page, "qa_zero_entry_facility_match")
    click_button(page, "是，3 個都正確")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    defer_boundary_wizard_if_present(page)
    result = visible_text(page)
    assert "適用" in result
    assert "HTTP 500" not in result
    save_step_screenshot(page, "qa_zero_entry_result")
    assert_no_app_errors(page)


def test_zero_entry_facility_differences(page) -> None:
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    lookup_stub_company(page, STUB_DIFF_UBN)
    click_button(page, "繼續")
    click_button(page, "繼續")
    wait_streamlit_idle(page)
    body = visible_text(page)
    assert "高雄一廠" in body or "2 個據點需要確認" in body
    assert "高雄二廠" in body
    assert "台中辦公室" in body
    assert "僅在政府資料找到" not in body
    assert "僅在上傳資料找到" not in body
    assert "全部納入本次資料" not in body
    assert "錯誤" not in body or "資料一致" in body
    assert_no_app_errors(page)
