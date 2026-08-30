"""Commercial GHG emissions summary PDF — model, filename, and render tests."""

from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from carbon_ledger.intake import (
    IntakeMetadata,
    build_and_validate_intake,
    parse_uploaded_table,
    suggest_column_mapping_with_confidence,
)
from carbon_ledger.intake_exceptions import (
    hold_unknown_context_rows,
    initialize_committed,
    mapping_from_committed,
)
from carbon_ledger.pipeline import run_demo_pipeline, run_uploaded_pipeline
from carbon_ledger.ui.emissions_report import (
    build_emissions_report_model,
    emissions_report_filename,
    format_report_generated_at,
    format_tco2e,
    model_contains_internal_token,
    sanitize_filename_part,
    text_contains_internal_token,
)
from carbon_ledger.ui.emissions_report_pdf import render_emissions_summary_pdf
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.view_models import (
    DISPOSITION_EXCLUDED_DUPLICATE,
    calculated_emissions_summary,
    reconcile_row_dispositions,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "artifacts" / "e2e"
FIXED_AT = "2026-08-28T06:42:00Z"
ZH = "zh-TW"
EN = "en"
SCOPE3_ZERO = re.compile(r"Scope\s*3.{0,48}0(?:\.0+)?\s*tCO", re.I | re.S)
COMPANY = "示例鋼鐵股份有限公司"


def _table(csv: str, name: str = "ops.csv"):
    return parse_uploaded_table(file_name=name, data=csv.encode("utf-8"))


def _metadata(name: str = "ops.csv") -> IntakeMetadata:
    return IntakeMetadata(
        source_name=name,
        site_id="高雄廠",
        document_date=date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="emissions_report",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
    )


def _run_uploaded(csv: str, *, hold_ng: bool = False):
    table = _table(csv)
    detailed = suggest_column_mapping_with_confidence(
        list(table.columns), frame=table.frame
    )
    committed = initialize_committed(table, detailed)
    mapping = mapping_from_committed(table, committed)
    mapping.electricity_context = "enterprise"
    if hold_ng:
        mapping.natural_gas_subtype = "unknown"
    intake = build_and_validate_intake(table, mapping, _metadata())
    if hold_ng:
        intake = hold_unknown_context_rows(intake, mapping)
    result = run_uploaded_pipeline(
        REPO_ROOT,
        run_id="emissions_report",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
        include_ifrs_s2=True,
    )
    return result, intake, table


def _complete_csv() -> str:
    return (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
        "外購電力,1000,kWh,2025-02-01,2025-02-28,高雄廠\n"
    )


def _preliminary_csv() -> str:
    return (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    )


def _complete_model(**kwargs):
    result, intake, table = _run_uploaded(_complete_csv())
    recon = reconcile_row_dispositions(
        uploaded_table=table,
        intake_result=intake,
        pipeline_result=result,
        is_uploaded_analysis=True,
        duplicate_excluded_ids=kwargs.get("duplicate_excluded_ids"),
    )
    model = build_emissions_report_model(
        result=result,
        lang=kwargs.get("lang", ZH),
        company_name=kwargs.get("company_name", COMPANY),
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        assessment=kwargs.get("assessment"),
        dispositions=recon,
        uploaded=True,
        generated_at=kwargs.get("generated_at", FIXED_AT),
        entity_name=kwargs.get("entity_name", COMPANY),
        entities_included=kwargs.get("entities_included", (COMPANY,)),
        entities_pending=kwargs.get("entities_pending", ()),
        sites_included=kwargs.get("sites_included", ("高雄廠",)),
        sites_pending=kwargs.get("sites_pending", ()),
        exclusions=kwargs.get("exclusions", ()),
        boundary_summary=kwargs.get("boundary_summary", ""),
    )
    return model, result, recon


def _preliminary_model(*, lang: str = ZH):
    result, intake, table = _run_uploaded(_preliminary_csv(), hold_ng=True)
    recon = reconcile_row_dispositions(
        uploaded_table=table,
        intake_result=intake,
        pipeline_result=result,
        is_uploaded_analysis=True,
    )
    model = build_emissions_report_model(
        result=result,
        lang=lang,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        uploaded=True,
        dispositions=recon,
        generated_at=FIXED_AT,
        sites_included=("高雄廠",),
    )
    return model, result, recon


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _assert_clean_co2e_units(text: str) -> None:
    assert "\x00" not in text
    assert "�" not in text
    assert "□" not in text
    assert "tCO²e" not in text
    assert "kgCO²e" not in text
    assert "tCO2e" in text or "tCO₂e" in text


def _page_texts(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [(page.extract_text() or "") for page in reader.pages]


def _render_page_png(pdf_bytes: bytes, index: int, dest: Path, *, scale: float = 1.8):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_bytes)
    page = document[index]
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil()
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest)
    document.close()
    return image


def test_filename_is_sanitized_and_stable() -> None:
    name = emissions_report_filename(
        company="示例/鋼鐵*公司?.pdf",
        period="2025 01–12",
    )
    assert name.startswith("ghg-emissions-summary-")
    assert name.endswith(".pdf")
    assert "/" not in name
    assert "*" not in name
    assert "?" not in name
    assert " " not in name
    assert "示例" in name
    assert "鋼鐵" in name
    assert sanitize_filename_part("../etc/passwd") == "etc-passwd"
    assert (
        emissions_report_filename(
            company="示例/鋼鐵*公司?.pdf",
            period="2025 01–12",
        )
        == name
    )


def test_complete_pdf_generates_with_required_content() -> None:
    model, result, recon = _complete_model()
    assert model.complete is True
    assert recon["complete"] is True
    assert model.status_label == t("dash.coverage_complete", ZH)
    pdf = render_emissions_summary_pdf(model)
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) > 1
    text = _pdf_text(pdf)
    total = calculated_emissions_summary(result, ZH)["calculated_tco2e"]
    assert t("report.title", ZH) in text
    assert "示例鋼鐵股份有限公司" in text
    assert "2025-01-01 – 2025-12-31" in text
    assert "2025-01 – 2025-02" in text
    assert f"{float(total):.2f}" in text
    _assert_clean_co2e_units(text)
    assert "碳排結果狀態" in text
    assert "2026-08-28 14:42（Asia/Taipei）" in text
    assert "T06:42" not in text
    assert ".294710" not in text
    assert "尚未納入 Scope 3" in text
    assert SCOPE3_ZERO.search(text) is None
    assert "環境部正式盤查報告書" not in text
    assert not text_contains_internal_token(text)
    assert not model_contains_internal_token(model)


def test_preliminary_pdf_contains_warning_and_status() -> None:
    model, _result, recon = _preliminary_model()
    assert model.complete is False
    assert recon["preliminary"] is True
    assert model.pending_rows >= 1
    pdf = render_emissions_summary_pdf(model)
    text = _pdf_text(pdf)
    assert t("dash.result_preliminary", ZH) in text
    assert t("report.limit.preliminary_banner", ZH) in text
    assert SCOPE3_ZERO.search(text) is None


def test_duplicate_exclusion_does_not_make_complete_preliminary() -> None:
    result, intake, table = _run_uploaded(_complete_csv())
    record_ids = [
        str(value) for value in result.activity_records_accepted["record_id"].tolist()
    ]
    recon = reconcile_row_dispositions(
        uploaded_table=table,
        intake_result=intake,
        pipeline_result=result,
        duplicate_excluded_ids={record_ids[0]},
        is_uploaded_analysis=True,
    )
    assert recon["counts"][DISPOSITION_EXCLUDED_DUPLICATE] == 1
    assert recon["complete"] is True
    model = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        dispositions=recon,
        uploaded=True,
        generated_at=FIXED_AT,
    )
    assert model.complete is True
    text = _pdf_text(render_emissions_summary_pdf(model))
    assert t("dash.coverage_complete", ZH) in text
    assert t("dash.result_preliminary", ZH) not in text
    assert t("report.disp.excluded_duplicate", ZH) in text


def test_missing_optional_inputs_do_not_crash() -> None:
    result, _intake, _table = _run_uploaded(_complete_csv())
    model = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name="",
        reporting_year=None,
        assessment=None,
        uploaded=True,
        generated_at=FIXED_AT,
    )
    pdf = render_emissions_summary_pdf(model)
    assert pdf.startswith(b"%PDF")
    text = _pdf_text(pdf)
    assert model.company_name == ""
    assert "尚未提供" not in model.company_name
    assert t("report.applicability_disclaimer", ZH) in text
    assert not text_contains_internal_token(text)


def test_english_pdf_has_title_and_no_internal_codes() -> None:
    model, _result, _recon = _complete_model(lang=EN)
    pdf = render_emissions_summary_pdf(model)
    text = _pdf_text(pdf)
    assert t("report.title", EN) in text
    assert "Emissions calculation complete" in text
    assert "Emissions result status" in text
    _assert_clean_co2e_units(text)
    assert "2026-08-28 14:42 (Asia/Taipei)" in text
    assert SCOPE3_ZERO.search(text) is None
    assert not text_contains_internal_token(text)


def test_same_input_is_content_stable() -> None:
    model, result, _recon = _complete_model()
    before = result.calculation_results.copy(deep=True)
    first = _pdf_text(render_emissions_summary_pdf(model))
    second = _pdf_text(render_emissions_summary_pdf(model))
    assert first == second
    after = result.calculation_results
    assert after.equals(before)
    total = calculated_emissions_summary(result, ZH)["calculated_tco2e"]
    assert f"{float(total):.2f}" in first


def test_demo_result_does_not_recalculate() -> None:
    result = run_demo_pipeline(
        REPO_ROOT,
        run_id="emissions_report_demo",
        ingested_at=pd.Timestamp("2024-02-01T00:00:00Z"),
        include_ghg=True,
        include_ifrs_s2=True,
    )
    before = result.calculation_results.copy(deep=True)
    total_before = calculated_emissions_summary(result, ZH)["calculated_tco2e"]
    model = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name="示範公司",
        reporting_year=2024,
        reporting_period_start="2024-01-01",
        reporting_period_end="2024-12-31",
        uploaded=False,
        generated_at=FIXED_AT,
    )
    pdf = render_emissions_summary_pdf(model)
    assert pdf.startswith(b"%PDF")
    assert result.calculation_results.equals(before)
    assert calculated_emissions_summary(result, ZH)["calculated_tco2e"] == total_before
    text = _pdf_text(pdf)
    if total_before is not None:
        assert f"{float(total_before):.2f}" in text


def test_pdf_visual_pages_render_to_required_artifacts() -> None:
    model, _result, _recon = _complete_model()
    pdf = render_emissions_summary_pdf(model)
    pages = _page_texts(pdf)
    cover_idx = 0
    results_idx = next(
        (i for i, text in enumerate(pages) if t("report.section.results", ZH) in text),
        min(2, len(pages) - 1),
    )
    quality_idx = next(
        (i for i, text in enumerate(pages) if t("report.section.quality", ZH) in text),
        min(3, len(pages) - 1),
    )
    cover = _render_page_png(
        pdf, cover_idx, ARTIFACTS / "qa_commercial_emissions_report_cover.png"
    )
    results = _render_page_png(
        pdf, results_idx, ARTIFACTS / "qa_commercial_emissions_report_results.png"
    )
    quality = _render_page_png(
        pdf, quality_idx, ARTIFACTS / "qa_commercial_emissions_report_quality.png"
    )
    for image in (cover, results, quality):
        assert image.size[0] > 400
        assert image.size[1] > 500
        extrema = image.convert("L").getextrema()
        assert extrema[0] < 250
        assert extrema[1] > 10
    prelim, _r, _x = _preliminary_model()
    prelim_text = _pdf_text(render_emissions_summary_pdf(prelim))
    complete_text = _pdf_text(pdf)
    assert t("dash.result_preliminary", ZH) in prelim_text
    assert t("dash.coverage_complete", ZH) in complete_text
    assert t("dash.result_preliminary", ZH) not in complete_text


def test_format_tco2e_uses_professional_subscript() -> None:
    assert format_tco2e(1.23, ZH) == "1.23 tCO₂e"
    assert "₂" in format_tco2e(1.23, ZH)
    assert "²" not in format_tco2e(1.23, ZH)
    assert format_report_generated_at(FIXED_AT, ZH) == "2026-08-28 14:42（Asia/Taipei）"
    assert format_report_generated_at(FIXED_AT, EN) == "2026-08-28 14:42 (Asia/Taipei)"


def _assert_visual_subscript_two(pdf_bytes: bytes, page_index: int) -> None:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(pdf_bytes)
    page = document[page_index]
    textpage = page.get_textpage()
    raw = textpage.get_text_bounded()
    marker = "CO2e"
    idx = raw.find(marker)
    if idx < 0:
        idx = raw.find("CO₂e")
    assert idx >= 0, f"page {page_index + 1} has no CO2e unit: {raw!r}"
    two_index = idx + 2
    o_box = textpage.get_charbox(idx + 1)
    two_box = textpage.get_charbox(two_index)
    o_mid = (o_box[1] + o_box[3]) / 2
    two_mid = (two_box[1] + two_box[3]) / 2
    two_height = two_box[3] - two_box[1]
    o_height = o_box[3] - o_box[1]
    assert two_mid < o_mid, (
        f"page {page_index + 1} unit 2 is not subscript "
        f"(O mid={o_mid:.2f}, 2 mid={two_mid:.2f})"
    )
    assert two_height < o_height * 0.95, (
        f"page {page_index + 1} unit 2 is not smaller than surrounding letters"
    )
    document.close()


def test_pdf_unit_glyphs_render_without_boxes() -> None:
    model, _result, _recon = _complete_model()
    pdf = render_emissions_summary_pdf(model)
    assert b"NotoSansUnits" not in pdf
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 6
    pages = _page_texts(pdf)
    for index in (1, 3, 5):
        raw = pages[index]
        assert "\x00" not in raw
        assert "�" not in raw
        assert "□" not in raw
        assert "tCO²e" not in raw
        assert "tCO2e" in raw or "tCO₂e" in raw or "CO2e" in raw or "CO₂e" in raw
        _assert_visual_subscript_two(pdf, index)
    _render_page_png(pdf, 1, ARTIFACTS / "qa_pdf_unit_render_page2.png")
    _render_page_png(pdf, 3, ARTIFACTS / "qa_pdf_unit_render_page4.png")
    _render_page_png(pdf, 5, ARTIFACTS / "qa_pdf_unit_render_page6.png")
    for page_index in range(len(reader.pages)):
        image = _render_page_png(
            pdf,
            page_index,
            ARTIFACTS / f"qa_pdf_v3_page{page_index + 1}.png",
        )
        extrema = image.convert("L").getextrema()
        assert extrema[0] < 250
        assert extrema[1] > 10


def test_empty_pending_and_applicability_wording_zh_en() -> None:
    zh_model, _result, _recon = _complete_model(
        lang=ZH,
        assessment=None,
        entities_pending=(),
        sites_pending=(),
    )
    en_model, _result_en, _recon_en = _complete_model(
        lang=EN,
        assessment=None,
        entities_pending=(),
        sites_pending=(),
    )
    zh_text = _pdf_text(render_emissions_summary_pdf(zh_model))
    en_text = _pdf_text(render_emissions_summary_pdf(en_model))
    assert t("report.none", ZH) in zh_text
    assert t("report.none", EN) in en_text
    assert t("report.applicability.not_completed", ZH) in zh_text
    assert t("report.applicability.not_completed", EN) in en_text
    assert "適用性評估尚未完成" in zh_text
    assert "Applicability assessment not yet completed" in en_text
    assert zh_text.count("尚未提供") == 0
    assert "Not yet provided" not in en_text
