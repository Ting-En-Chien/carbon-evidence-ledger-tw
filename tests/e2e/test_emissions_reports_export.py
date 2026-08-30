"""E2E coverage for commercial emissions reports and hidden IFRS/Taiwan nav."""

from __future__ import annotations

import io
import re
import shutil
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

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

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR) not in sys.path:
    sys.path.insert(0, str(E2E_DIR))

from helpers import (  # noqa: E402
    ARTIFACTS,
    NAV_EVIDENCE,
    STUB_ALIGNED_UBN,
    click_button,
    confirm_intake_reading,
    lookup_stub_company,
    open_fresh_app,
    save_step_screenshot,
    start_uploaded_coverage_analysis,
    visible_text,
    wait_for_hero_settled,
    wait_streamlit_idle,
)

pytestmark = pytest.mark.e2e

COMPLETE_CLEAN = (
    "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
    "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
    "外購電力,1000,kWh,2025-02-01,2025-02-28,高雄廠\n"
)
PRELIMINARY_MIX = (
    "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
    "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
    "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
)
NAV_REPORTS = r"碳排報表與匯出|Emissions Reports|報表與匯出"
INTERNAL = (
    "NEEDS_INFORMATION",
    "factor_id",
    "formula_id",
    "calculation_trace",
    "schema_version",
    "ghg_inventory",
    "ifrs_s1_s2",
)


COMPANY_NAME = "長興材料工業股份有限公司"


def _seed_confirmed_workspace(root: Path, *, year: int = 2025) -> None:
    period = ReportingPeriod.confirmed(
        reporting_year_suggested=year,
        reporting_year_confirmed=year,
        period_start_confirmed=f"{year}-01-01",
        period_end_confirmed=f"{year}-12-31",
    )
    entity = LegalEntity(
        entity_id="entity_report",
        legal_name=COMPANY_NAME,
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
    if workspace.path.exists():
        shutil.rmtree(workspace.path)
    workspace = CompanyWorkspace.for_company(
        root=root, taiwan_ubn=STUB_ALIGNED_UBN
    )
    workspace.append_locally_confirmed(confirmed)


def _open_with_confirmed_company(page, workspace_dir: Path) -> None:
    _seed_confirmed_workspace(workspace_dir)
    open_fresh_app(page)
    click_button(page, "開始公司設定")
    lookup_stub_company(page, STUB_ALIGNED_UBN)
    wait_streamlit_idle(page)
    confirm = page.get_by_role(
        "button",
        name=re.compile(r"這是我的公司|This is my company"),
    )
    if confirm.count():
        confirm.first.click(force=True)
        wait_streamlit_idle(page)
    page.get_by_role("link", name=re.compile(NAV_EVIDENCE)).first.click()
    wait_streamlit_idle(page)


def _save_pdf_qa_pages(pdf_bytes: bytes) -> None:
    import pypdfium2 as pdfium

    pages = [
        (page_obj.extract_text() or "").replace("\x00", "₂")
        for page_obj in PdfReader(io.BytesIO(pdf_bytes)).pages
    ]
    cover_idx = 0
    results_idx = next(
        (i for i, text in enumerate(pages) if "排放結果" in text),
        min(2, len(pages) - 1),
    )
    quality_idx = next(
        (i for i, text in enumerate(pages) if "資料品質" in text),
        min(3, len(pages) - 1),
    )
    document = pdfium.PdfDocument(pdf_bytes)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for index, name in (
        (cover_idx, "qa_commercial_emissions_report_cover"),
        (results_idx, "qa_commercial_emissions_report_results"),
        (quality_idx, "qa_commercial_emissions_report_quality"),
    ):
        page = document[index]
        image = page.render(scale=1.8).to_pil()
        image.save(ARTIFACTS / f"{name}.png")
    document.close()


def _extract_pdf(pdf_bytes: bytes) -> str:
    return "\n".join(
        (page_obj.extract_text() or "")
        for page_obj in PdfReader(io.BytesIO(pdf_bytes)).pages
    ).replace("\x00", "₂")


def _assert_commercial_pdf(text: str, filename: str) -> None:
    assert COMPANY_NAME in text
    assert "尚未提供" not in filename
    assert "Not-yet-provided" not in filename
    assert "ghg-emissions-summary-company-" not in filename.lower()
    assert "2025-01-01" in text
    assert "2025-12-31" in text
    assert "2025-01" in text
    assert "2025-02" in text
    assert "tCO₂e" in text or "tCO2e" in text
    assert "tCO²e" not in text
    assert "Asia/Taipei" in text
    assert "T06:" not in text
    for token in INTERNAL:
        assert token not in text


def _upload_csv(page, name: str, content: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    csv_path = ARTIFACTS / name
    csv_path.write_text(content, encoding="utf-8")
    uploader = page.locator('[data-testid="stFileUploader"] input[type="file"]')
    uploader.first.wait_for(state="attached", timeout=30_000)
    uploader.first.set_input_files(str(csv_path))
    wait_streamlit_idle(page, timeout=40)
    page.get_by_text(
        re.compile(r"資料已讀取|File read successfully"),
        exact=False,
    ).first.wait_for(state="visible", timeout=20_000)


def _open_reports(page) -> None:
    page.get_by_role("link", name=re.compile(NAV_REPORTS)).first.click()
    wait_streamlit_idle(page, timeout=40)


def _switch_to_english(page) -> None:
    """Switch the header language control to EN and wait for English nav."""
    control = page.locator(".st-key-cel_language_control")
    option = control.get_by_text("EN", exact=True)
    if option.count() == 0:
        option = page.locator('[data-testid="stButtonGroup"]').get_by_text(
            "EN", exact=True
        )
    if option.count() == 0:
        option = page.get_by_role("radio", name="EN")
    if option.count() == 0:
        option = page.get_by_text("EN", exact=True)
    assert option.count(), "header language control has no EN option"
    option.first.click(force=True)
    wait_streamlit_idle(page, timeout=40)
    page.get_by_text("Emissions Reports & Exports", exact=False).first.wait_for(
        timeout=20_000
    )


def _sidebar_text(page) -> str:
    nav = page.locator('[data-testid="stSidebarNav"]')
    if nav.count():
        return nav.inner_text()
    return page.locator('[data-testid="stSidebar"]').inner_text()


def test_customer_sidebar_hides_ifrs_and_taiwan(page) -> None:
    open_fresh_app(page)
    sidebar = _sidebar_text(page)
    assert "IFRS S1/S2" not in sidebar
    assert "台灣溫室氣體與碳費" not in sidebar
    assert "合規總覽" in sidebar
    assert "排放資料與計算" in sidebar
    assert "碳排報表與匯出" in sidebar


def test_empty_reports_page_cta_and_company_without_result(page) -> None:
    open_fresh_app(page)
    _open_reports(page)
    text = visible_text(page)
    assert "完成公司與報導期間設定" in text
    page.get_by_role(
        "link", name=re.compile(r"我的適用要求|Your requirements")
    ).first.click()
    wait_streamlit_idle(page)
    page.get_by_role("link", name=re.compile(NAV_REPORTS)).first.click()
    wait_streamlit_idle(page)
    # Still no confirmed company/year from just opening applicability.
    body = visible_text(page)
    assert "完成公司與報導期間設定" in body or "尚無可匯出的碳排結果" in body


def test_complete_result_pdf_matches_dashboard_and_screenshot(
    page, e2e_company_workspace_dir: Path
) -> None:
    _open_with_confirmed_company(page, e2e_company_workspace_dir)
    _upload_csv(page, "report_complete.csv", COMPLETE_CLEAN)
    confirm_intake_reading(page)
    start_uploaded_coverage_analysis(page)
    page.get_by_text("碳排計算完成", exact=False).first.wait_for(
        state="visible", timeout=40_000
    )
    hero = wait_for_hero_settled(page)
    dash_text = visible_text(page)
    _open_reports(page)
    page.get_by_role(
        "button",
        name=re.compile(r"下載碳排摘要報告|Download Emissions Summary"),
    ).first.wait_for(state="visible", timeout=40_000)
    page.set_viewport_size({"width": 1440, "height": 900})
    wait_streamlit_idle(page)
    save_step_screenshot(
        page, "qa_emissions_reports_export_page", required=True, full_page=False
    )
    report_text = visible_text(page)
    assert "碳排計算完成" in report_text
    assert COMPANY_NAME in report_text
    assert hero["text"] in report_text or hero["final"] in report_text
    assert "專業覆核附件" in report_text
    expander = page.locator("[data-testid='stExpander']").filter(
        has_text=re.compile(r"專業覆核附件|Technical review")
    )
    if expander.count():
        expander.first.click()
        wait_streamlit_idle(page)
    zip_hits = page.get_by_text(
        re.compile(r"稽核包|audit package|\.zip"), exact=False
    )
    assert zip_hits.count()
    with page.expect_download(timeout=30_000) as download_info:
        page.get_by_role(
            "button",
            name=re.compile(r"下載碳排摘要報告|Download Emissions Summary"),
        ).first.click()
    download = download_info.value
    filename = download.suggested_filename or "ghg-emissions-summary.pdf"
    dest = ARTIFACTS / filename
    download.save_as(str(dest))
    data = dest.read_bytes()
    assert data[:4] == b"%PDF"
    text = _extract_pdf(data)
    assert "溫室氣體排放計算與適用性摘要報告" in text
    assert hero["text"].replace(",", "")[:4] in text.replace(",", "")
    assert "碳排計算完成" in text
    _assert_commercial_pdf(text, filename)
    _save_pdf_qa_pages(data)
    for stale in ARTIFACTS.glob("ghg-emissions-summary-尚未提供-*.pdf"):
        stale.unlink()
    for stale in ARTIFACTS.glob("ghg-emissions-summary-Not-yet-provided-*.pdf"):
        stale.unlink()
    for stale in ARTIFACTS.glob("ghg-emissions-summary-company-*.pdf"):
        stale.unlink()
    assert dash_text  # dashboard was reached before export


def test_preliminary_result_pdf_status(
    page, e2e_company_workspace_dir: Path
) -> None:
    _open_with_confirmed_company(page, e2e_company_workspace_dir)
    _upload_csv(page, "report_prelim.csv", PRELIMINARY_MIX)
    confirm_intake_reading(page, ng_choice="我現在無法確認，暫不納入計算")
    start_uploaded_coverage_analysis(page)
    page.get_by_text("初步碳排結果", exact=False).first.wait_for(
        state="visible", timeout=40_000
    )
    _open_reports(page)
    page.get_by_text("初步碳排結果", exact=False).first.wait_for(
        state="visible", timeout=40_000
    )
    with page.expect_download(timeout=30_000) as download_info:
        page.get_by_role(
            "button",
            name=re.compile(r"下載碳排摘要報告|Download Emissions Summary"),
        ).first.click()
    download = download_info.value
    dest = ARTIFACTS / (download.suggested_filename or "ghg-prelim.pdf")
    download.save_as(str(dest))
    data = dest.read_bytes()
    assert data[:4] == b"%PDF"
    text = _extract_pdf(data)
    assert COMPANY_NAME in text
    assert "初步碳排結果" in text or "初步結果" in text
    assert "請勿以正式" in text or "初步結果" in text
    assert "tCO²e" not in text
    for token in INTERNAL:
        assert token not in text


def test_english_pdf_download_has_no_garbled_title(
    page, e2e_company_workspace_dir: Path
) -> None:
    _open_with_confirmed_company(page, e2e_company_workspace_dir)
    _upload_csv(page, "report_en.csv", COMPLETE_CLEAN)
    confirm_intake_reading(page)
    start_uploaded_coverage_analysis(page)
    page.get_by_text("碳排計算完成", exact=False).first.wait_for(
        state="visible", timeout=40_000
    )
    _switch_to_english(page)
    _open_reports(page)
    page.get_by_role(
        "button",
        name=re.compile(r"Download Emissions Summary Report"),
    ).first.wait_for(state="visible", timeout=40_000)
    with page.expect_download(timeout=30_000) as download_info:
        page.get_by_role(
            "button",
            name=re.compile(r"Download Emissions Summary Report"),
        ).first.click()
    download = download_info.value
    dest = ARTIFACTS / (download.suggested_filename or "ghg-en.pdf")
    download.save_as(str(dest))
    text = _extract_pdf(dest.read_bytes())
    assert "GHG Emissions Calculation and Applicability Summary" in text
    assert COMPANY_NAME in text
    assert "tCO₂e" in text or "tCO2e" in text
    assert "tCO²e" not in text
    assert "(Asia/Taipei)" in text
    assert "\ufffd" not in text
    for token in INTERNAL:
        assert token not in text
