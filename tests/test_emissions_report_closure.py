"""Regression for commercial PDF data-semantics closure."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pandas as pd
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from carbon_ledger.company_workspace import CompanyWorkspace, default_workspace_root
from carbon_ledger.intake import (
    IntakeMetadata,
    build_and_validate_intake,
    parse_uploaded_table,
    suggest_column_mapping_with_confidence,
)
from carbon_ledger.intake_exceptions import initialize_committed, mapping_from_committed
from carbon_ledger.inventory_boundary import (
    MEMBERSHIP_EXCLUDED,
    MEMBERSHIP_INCLUDED,
    MEMBERSHIP_PENDING,
    PURPOSE_MOENV_FACILITY,
    REQUIREMENT_VOLUNTARY,
    FacilityMembership,
    InventoryBoundary,
    LegalEntityMembership,
    ReportingPeriod,
)
from carbon_ledger.legal_entity import (
    CONFIRMATION_LOCAL,
    CONFIRMATION_PENDING,
    LegalEntity,
)
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.ui.customer_presenters import present_obligation_card
from carbon_ledger.ui.emissions_report import (
    build_emissions_report_from_session,
    build_emissions_report_model,
    emissions_report_filename,
    format_report_generated_at,
    has_company_and_reporting_period,
)
from carbon_ledger.ui.emissions_report_pdf import render_emissions_summary_pdf
from carbon_ledger.ui.emissions_report_scope import (
    confirmed_company_display_name,
    confirmed_reporting_period,
    has_confirmed_company_and_reporting_period,
    load_confirmed_report_scope,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    ANALYSIS_SOURCE_UPLOADED,
    STATE_ANALYSIS_PERIOD_END,
    STATE_ANALYSIS_PERIOD_START,
    STATE_ANALYSIS_SOURCE,
    STATE_INTAKE_FILE_NAME,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_TABLE,
    STATE_RESULT,
    STATE_UPLOADED_ANALYSIS_COMPLETED,
    initialize_ui_state,
    save_company_master_mapping,
    save_company_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
ZH = "zh-TW"
EN = "en"
COMPANY = "長興材料工業股份有限公司"
UBN = "12345675"
FIXED_AT = "2026-08-28T06:42:00Z"


def _all_text(at: AppTest) -> str:
    chunks: list[str] = []
    for collection_name in (
        "markdown",
        "caption",
        "text",
        "info",
        "success",
        "warning",
        "error",
        "title",
        "header",
        "subheader",
    ):
        collection = getattr(at, collection_name, None)
        if collection is None:
            continue
        for item in collection:
            value = getattr(item, "value", None)
            if value is not None:
                chunks.append(str(value))
            body = getattr(item, "body", None)
            if body is not None:
                chunks.append(str(body))
    for button in list(at.button) + list(getattr(at, "download_button", [])):
        label = getattr(button, "label", None)
        if label is not None:
            chunks.append(str(label))
    return "\n".join(chunks)


def _fresh() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    assert not at.exception
    return at


def seed_confirmed_report_workspace(
    root: Path,
    *,
    ubn: str = UBN,
    company: str = COMPANY,
    year: int = 2025,
    included_sites: tuple[str, ...] = ("高雄廠",),
    pending_sites: tuple[str, ...] = (),
    excluded_sites: tuple[tuple[str, str], ...] = (),
    boundary_id: str = "report_confirmed_boundary",
) -> ReportingPeriod:
    """Write one current/confirmed v1 boundary and optional draft pending sites."""
    period = ReportingPeriod.confirmed(
        reporting_year_suggested=year,
        reporting_year_confirmed=year,
        period_start_confirmed=f"{year}-01-01",
        period_end_confirmed=f"{year}-12-31",
    )
    entity = LegalEntity(
        entity_id="entity_report",
        legal_name=company,
        jurisdiction="TW",
        taiwan_ubn=ubn,
        confirmation_state=CONFIRMATION_LOCAL,
        locally_confirmed_at="2026-08-01T00:00:00Z",
        responsible_contact_name="測試聯絡人",
        responsible_job_title="永續主管",
    )
    facilities = [
        FacilityMembership(facility_id=site, state=MEMBERSHIP_INCLUDED)
        for site in included_sites
    ]
    facilities.extend(
        FacilityMembership(
            facility_id=site,
            state=MEMBERSHIP_EXCLUDED,
            reason=reason,
            evidence_source="customer_confirmed",
        )
        for site, reason in excluded_sites
    )
    confirmed = InventoryBoundary(
        boundary_id=boundary_id,
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
        facility_memberships=tuple(facilities),
        organizational_approach="營運控制權法",
        responsible_contact_name="測試聯絡人",
        responsible_job_title="永續主管",
        schema_version="inventory-boundary-v1",
    ).locally_confirmed(at="2026-08-01T00:00:00Z")
    workspace = CompanyWorkspace.for_company(root=root, taiwan_ubn=ubn)
    workspace.append_locally_confirmed(confirmed)
    if pending_sites:
        draft = InventoryBoundary(
            boundary_id="report_draft_boundary",
            purpose=PURPOSE_MOENV_FACILITY,
            requirement_status=REQUIREMENT_VOLUNTARY,
            display_name="仍待確認盤查範圍",
            reporting_period=period,
            legal_entities=(entity,),
            entity_memberships=(
                LegalEntityMembership(
                    entity_id=entity.entity_id,
                    state=MEMBERSHIP_PENDING,
                ),
            ),
            facility_memberships=tuple(
                FacilityMembership(facility_id=site, state=MEMBERSHIP_PENDING)
                for site in pending_sites
            ),
            schema_version="inventory-boundary-v1",
        )
        workspace.write_draft(draft)
    return period


def bind_confirmed_company(session_state, *, company: str = COMPANY, ubn: str = UBN):
    save_company_profile(
        session_state,
        {
            "company_name": company,
            "reporting_year": 2025,
            "unified_business_number": ubn,
        },
    )
    save_company_master_mapping(
        session_state,
        {
            "company_id": "entity_report",
            "legal_name": company,
            "company_name": company,
            "unified_business_number": ubn,
            "customer_confirmed_at": "2026-08-01T00:00:00Z",
        },
    )


def bind_unconfirmed_company(
    session_state, *, company: str = COMPANY, ubn: str = UBN
) -> None:
    save_company_profile(
        session_state,
        {
            "company_name": company,
            "reporting_year": 2025,
            "unified_business_number": ubn,
        },
    )
    save_company_master_mapping(
        session_state,
        {
            "company_id": "entity_report",
            "legal_name": company,
            "company_name": company,
            "unified_business_number": ubn,
        },
    )


def bind_active_reporting_period(
    session_state,
    period: ReportingPeriod,
    *,
    ubn: str = UBN,
    year: int | None = None,
) -> None:
    workspace = CompanyWorkspace.for_company(
        root=default_workspace_root(REPO_ROOT),
        taiwan_ubn=ubn,
    )
    year_key = int(year or period.reporting_year_confirmed or 0)
    session_state[f"boundary_active_period_{workspace.workspace_id}_{year_key}"] = (
        period.reporting_period_id
    )


def prepare_session_for_pdf_export(
    session_state,
    monkeypatch,
    tmp_path,
    *,
    company: str = COMPANY,
    ubn: str = UBN,
    year: int = 2025,
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(
        tmp_path, ubn=ubn, company=company, year=year
    )
    bind_confirmed_company(session_state, company=company, ubn=ubn)


def _run_csv(csv: str, *, natural_gas_subtype: str | None = None):
    table = parse_uploaded_table(file_name="ops.csv", data=csv.encode("utf-8"))
    detailed = suggest_column_mapping_with_confidence(
        list(table.columns), frame=table.frame
    )
    committed = initialize_committed(table, detailed)
    mapping = mapping_from_committed(table, committed)
    mapping.electricity_context = "enterprise"
    if natural_gas_subtype:
        mapping.natural_gas_subtype = natural_gas_subtype
    if "天然氣種類" in table.columns:
        mapping.natural_gas_subtype_column = "天然氣種類"
    intake = build_and_validate_intake(
        table,
        mapping,
        IntakeMetadata(
            source_name="ops.csv",
            site_id="高雄廠",
            document_date=date(2025, 1, 31),
            data_quality_tier="unknown",
            intake_run_id="report_closure",
            ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
        ),
    )
    result = run_uploaded_pipeline(
        REPO_ROOT,
        run_id="report_closure",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
        include_ifrs_s2=True,
    )
    return result, intake, table


def _complete_result():
    csv = (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
        "外購電力,1000,kWh,2025-02-01,2025-02-28,高雄廠\n"
    )
    return _run_csv(csv)


def _put_result(at: AppTest, result, intake, table) -> None:
    at.session_state[STATE_RESULT] = result
    at.session_state[STATE_INTAKE_RESULT] = intake
    at.session_state[STATE_INTAKE_TABLE] = table
    at.session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_UPLOADED
    at.session_state[STATE_INTAKE_FILE_NAME] = "ops.csv"
    at.session_state[STATE_UPLOADED_ANALYSIS_COMPLETED] = True
    at.session_state[STATE_ANALYSIS_PERIOD_START] = "2025-01"
    at.session_state[STATE_ANALYSIS_PERIOD_END] = "2025-02"


def _pdf_text(pdf_bytes: bytes) -> str:
    return "\n".join(
        (page.extract_text() or "") for page in PdfReader(io.BytesIO(pdf_bytes)).pages
    ).replace("\x00", "₂")


def _pdf_download_labels(at: AppTest) -> list[str]:
    return [str(item.label) for item in at.download_button]
    return [str(item.label) for item in at.download_button]


def test_filename_rejects_placeholder_company() -> None:
    for name in ("尚未提供", "Not yet provided", "Not-yet-provided", "company"):
        try:
            emissions_report_filename(company=name, period="2025")
        except ValueError:
            continue
        raise AssertionError(f"placeholder company {name!r} was accepted")


def test_reporting_period_and_data_coverage_stay_separate() -> None:
    result, _intake, _table = _complete_result()
    model = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        uploaded=True,
        generated_at=FIXED_AT,
    )
    assert model.reporting_period == "2025-01-01 – 2025-12-31"
    assert model.data_coverage_period == "2025-01 – 2025-02"
    assert model.coverage_partial is True
    text = _pdf_text(render_emissions_summary_pdf(model))
    assert "2025-01-01 – 2025-12-31" in text
    assert "2025-01 – 2025-02" in text
    assert text.count("2025-01-01 – 2025-12-31") >= 1
    assert "資料涵蓋期間" in text
    assert "報導期間" in text


def test_method_rows_keep_distinct_factor_years_and_usage_count() -> None:
    result, _intake, _table = _complete_result()
    calcs = result.calculation_results.copy()
    calculated = calcs[calcs["calculation_status"].astype(str) == "calculated"]
    assert len(calculated) >= 2
    second = calculated.index[1]
    calcs.loc[second, "factor_id"] = "ef_tw_grid_electricity_2024"
    result.calculation_results = calcs
    model = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        uploaded=True,
        generated_at=FIXED_AT,
    )
    years = {row.factor_year for row in model.methods}
    assert "2024" in years
    assert "2025" in years
    assert len(model.methods) >= 2
    duplicate = build_emissions_report_model(
        result=_complete_result()[0],
        lang=ZH,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        uploaded=True,
        generated_at=FIXED_AT,
    )
    assert len(duplicate.methods) == 1
    assert duplicate.methods[0].usage_count == 2


def test_ng1_and_ng2_are_listed_separately() -> None:
    csv = (
        "活動類型,使用量,單位,開始日期,結束日期,廠場,天然氣種類\n"
        "天然氣,1000,m3,2025-01-01,2025-01-31,高雄廠,NG1\n"
        "天然氣,2000,m3,2025-01-01,2025-01-31,高雄廠,NG2\n"
    )
    result, _intake, _table = _run_csv(csv)
    model = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        uploaded=True,
        generated_at=FIXED_AT,
    )
    names = [row.activity_name for row in model.methods]
    assert any("NG1" in name for name in names)
    assert any("NG2" in name for name in names)
    text = _pdf_text(render_emissions_summary_pdf(model))
    assert "NG1" in text
    assert "NG2" in text


def test_confirmed_boundary_semantics_not_draft(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(
        tmp_path,
        included_sites=("高雄廠",),
        pending_sites=("台南廠",),
        excluded_sites=(("已停用廠", "客戶確認該廠已停用"),),
    )
    session = {
        "company_profile": {
            "company_name": COMPANY,
            "reporting_year": 2025,
            "unified_business_number": UBN,
        },
        "company_master": {
            "legal_name": COMPANY,
            "unified_business_number": UBN,
            "customer_confirmed_at": "2026-08-01T00:00:00Z",
        },
    }
    scope = load_confirmed_report_scope(session, lang=ZH)
    assert scope is not None
    assert "高雄廠" in scope.sites_included
    assert "台南廠" in scope.sites_pending
    assert "台南廠" not in scope.sites_included
    assert any(name == "已停用廠" for name, _reason in scope.exclusions)
    assert any("已停用" in reason for _name, reason in scope.exclusions)
    assert "已確認盤查目的" in scope.boundary_summary
    assert "仍待確認的盤查目的" in scope.boundary_summary
    model = build_emissions_report_model(
        result=_complete_result()[0],
        lang=ZH,
        company_name=scope.company_name,
        reporting_year=scope.reporting_period.reporting_year_confirmed,
        reporting_period_start=scope.reporting_period.period_start_confirmed,
        reporting_period_end=scope.reporting_period.period_end_confirmed,
        uploaded=True,
        generated_at=FIXED_AT,
        entity_name=scope.entity_name,
        entities_included=scope.entities_included,
        entities_pending=scope.entities_pending,
        sites_included=scope.sites_included,
        sites_pending=scope.sites_pending,
        exclusions=scope.exclusions,
        boundary_summary=scope.boundary_summary,
    )
    text = _pdf_text(render_emissions_summary_pdf(model))
    assert "高雄廠" in text
    assert "台南廠" in text
    assert "已停用廠" in text
    assert "客戶確認該廠已停用" in text
    assert "仍待確認" in text
    assert "locally_confirmed" not in text


def test_customer_cta_does_not_point_at_hidden_routes() -> None:
    ifrs = present_obligation_card(
        {
            "obligation_id": "ifrs_s1_s2",
            "title": "IFRS S1/S2",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "FSC",
            "official_document": "order",
            "citations": ["a"],
        },
        ZH,
    )
    assert ifrs.primary_action_target == ""
    assert "frameworks.py" not in ifrs.primary_action_target
    assert ifrs.primary_action_label == ""
    ghg = present_obligation_card(
        {
            "obligation_id": "ghg_inventory",
            "title": "台灣溫室氣體盤查",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "環境部",
            "official_document": "x",
            "citations": ["a"],
        },
        ZH,
    )
    assert ghg.primary_action_target == "app_pages/data_intake.py"
    assert "taiwan_ghg.py" not in ghg.primary_action_target
    fee = present_obligation_card(
        {
            "obligation_id": "carbon_fee",
            "title": "碳費",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "環境部",
            "official_document": "x",
            "citations": ["a"],
        },
        ZH,
    )
    assert fee.primary_action_target == "app_pages/data_intake.py"
    verification = present_obligation_card(
        {
            "obligation_id": "taiwan_environmental_verification",
            "title": "環境部溫室氣體查驗",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "環境部",
            "official_document": "x",
            "citations": ["a"],
        },
        ZH,
    )
    assert verification.primary_action_target == "app_pages/data_intake.py"


def test_admin_cta_can_open_hidden_ifrs(monkeypatch) -> None:
    monkeypatch.setenv("CEL_APP_MODE", "admin")
    ifrs = present_obligation_card(
        {
            "obligation_id": "ifrs_s1_s2",
            "title": "IFRS S1/S2",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "FSC",
            "official_document": "order",
            "citations": ["a"],
        },
        ZH,
    )
    assert ifrs.primary_action_target == "app_pages/frameworks.py"
    assert ifrs.primary_action_label == t("apl.cta.start_prepare_ifrs", ZH)


def test_generated_at_is_not_ingestion_time() -> None:
    result, _intake, _table = _complete_result()
    model = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        uploaded=True,
        generated_at=FIXED_AT,
    )
    assert model.generated_at == "2026-08-28 14:42（Asia/Taipei）"
    assert str(result.ingested_at) not in model.generated_at
    assert "2025-02-01" not in model.generated_at
    text = _pdf_text(render_emissions_summary_pdf(model))
    assert "2026-08-28 14:42（Asia/Taipei）" in text
    assert "T06:42:00" not in text
    assert ".000" not in model.generated_at or "14:42" in model.generated_at
    assert "Z" not in model.generated_at
    english = format_report_generated_at(FIXED_AT, EN)
    assert english == "2026-08-28 14:42 (Asia/Taipei)"
    first = model.fingerprint
    second = build_emissions_report_model(
        result=result,
        lang=ZH,
        company_name=COMPANY,
        reporting_year=2025,
        reporting_period_start="2025-01-01",
        reporting_period_end="2025-12-31",
        uploaded=True,
        generated_at="2026-08-29T00:00:00Z",
    )
    assert first == second.fingerprint


def test_result_without_company_cannot_download_pdf(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    result, intake, table = _complete_result()
    at = _fresh()
    _put_result(at, result, intake, table)
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "尚未完成公司與報導期間設定" in text
    assert any("完成公司與報導期間設定" in str(button.label) for button in at.button)
    assert not any(
        "PDF" in label or "碳排摘要" in label for label in _pdf_download_labels(at)
    )
    assert at.session_state[STATE_RESULT] is result
    assert build_emissions_report_from_session(at.session_state) is None
    assert has_company_and_reporting_period(at.session_state) is False


def test_result_with_company_but_no_confirmed_period_cannot_download(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    result, intake, table = _complete_result()
    at = _fresh()
    bind_confirmed_company(at.session_state)
    _put_result(at, result, intake, table)
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "請確認本次報導期間" in text
    assert any("確認本次報導期間" in str(button.label) for button in at.button)
    assert not any(
        "PDF" in label or "碳排摘要" in label for label in _pdf_download_labels(at)
    )
    assert at.session_state[STATE_RESULT] is result


def test_confirmed_company_period_and_result_can_download(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path)
    result, intake, table = _complete_result()
    at = _fresh()
    bind_confirmed_company(at.session_state)
    _put_result(at, result, intake, table)
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "碳排計算完成" in text
    labels = _pdf_download_labels(at)
    assert any("PDF" in label or "碳排摘要" in label for label in labels)
    cache = (
        at.session_state["cel_emissions_pdf_cache"]
        if "cel_emissions_pdf_cache" in at.session_state
        else {}
    )
    data = cache.get("bytes")
    name = str(cache.get("name") or "")
    assert isinstance(data, (bytes, bytearray))
    assert bytes(data[:4]) == b"%PDF"
    assert "尚未提供" not in name
    assert "Not-yet-provided" not in name
    assert "-company-" not in name.lower()
    assert "長興" in name
    first_stamp = cache.get("generated_at")
    at.run()
    second = (
        at.session_state["cel_emissions_pdf_cache"]
        if "cel_emissions_pdf_cache" in at.session_state
        else {}
    )
    second_stamp = second.get("generated_at")
    assert first_stamp
    assert first_stamp == second_stamp
    assert "T" not in first_stamp or "Asia/Taipei" in first_stamp
    assert "." not in first_stamp.split(" ")[-1]


def _assert_no_pdf_download(at: AppTest) -> None:
    assert not any(
        "PDF" in label or "碳排摘要" in label for label in _pdf_download_labels(at)
    )
    cache = (
        at.session_state["cel_emissions_pdf_cache"]
        if "cel_emissions_pdf_cache" in at.session_state
        else {}
    )
    assert not cache.get("bytes")


def test_unconfirmed_company_cannot_use_existing_workspace_pdf(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path)
    result, intake, table = _complete_result()
    at = _fresh()
    bind_unconfirmed_company(at.session_state)
    _put_result(at, result, intake, table)
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    _assert_no_pdf_download(at)
    assert at.session_state[STATE_RESULT] is result
    assert build_emissions_report_from_session(at.session_state) is None
    assert has_confirmed_company_and_reporting_period(at.session_state) is False


def test_placeholder_profile_only_and_unconfirmed_master_cannot_pass(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path)
    placeholder = {
        "company_id": "entity_report",
        "legal_name": "尚未提供",
        "company_name": "尚未提供",
        "unified_business_number": UBN,
        "customer_confirmed_at": "2026-08-01T00:00:00Z",
    }
    assert confirmed_company_display_name({"company_master": placeholder}) == ""
    assert load_confirmed_report_scope({"company_master": placeholder}) is None
    profile_only = {
        "company_profile": {
            "company_name": COMPANY,
            "reporting_year": 2025,
            "unified_business_number": UBN,
        }
    }
    assert confirmed_company_display_name(profile_only) == ""
    assert load_confirmed_report_scope(profile_only) is None
    unconfirmed_master = {
        "company_master": {
            "company_id": "entity_report",
            "legal_name": COMPANY,
            "company_name": COMPANY,
            "unified_business_number": UBN,
        }
    }
    assert confirmed_company_display_name(unconfirmed_master) == ""
    assert load_confirmed_report_scope(unconfirmed_master) is None
    assert has_confirmed_company_and_reporting_period(unconfirmed_master) is False


def test_active_reporting_period_2025_not_2026(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    period_2025 = seed_confirmed_report_workspace(
        tmp_path, year=2025, boundary_id="b_2025"
    )
    seed_confirmed_report_workspace(tmp_path, year=2026, boundary_id="b_2026")
    session: dict = {}
    bind_confirmed_company(session)
    bind_active_reporting_period(session, period_2025, year=2025)
    scope = load_confirmed_report_scope(session, lang=ZH)
    assert scope is not None
    assert scope.reporting_period.reporting_year_confirmed == 2025
    assert scope.reporting_period.period_start_confirmed == "2025-01-01"
    assert scope.reporting_period.reporting_period_id == period_2025.reporting_period_id
    result, intake, table = _complete_result()
    session[STATE_RESULT] = result
    session[STATE_INTAKE_RESULT] = intake
    session[STATE_INTAKE_TABLE] = table
    model = build_emissions_report_from_session(session, lang=ZH, generated_at=FIXED_AT)
    assert model is not None
    assert "2025-01-01" in model.reporting_period
    assert "2026-01-01" not in model.reporting_period
    assert "2025" in emissions_report_filename(
        company=model.company_name, period=model.reporting_period
    )


def test_active_reporting_period_2026_not_2025(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path, year=2025, boundary_id="b_2025")
    period_2026 = seed_confirmed_report_workspace(
        tmp_path, year=2026, boundary_id="b_2026"
    )
    session: dict = {}
    bind_confirmed_company(session)
    bind_active_reporting_period(session, period_2026, year=2026)
    scope = load_confirmed_report_scope(session, lang=ZH)
    assert scope is not None
    assert scope.reporting_period.reporting_year_confirmed == 2026
    assert scope.reporting_period.period_start_confirmed == "2026-01-01"
    result, _intake, _table = _complete_result()
    session[STATE_RESULT] = result
    model = build_emissions_report_from_session(session, lang=ZH, generated_at=FIXED_AT)
    assert model is not None
    assert "2026-01-01" in model.reporting_period
    assert "2025-01-01" not in model.reporting_period


def test_multiple_periods_without_active_id_cannot_guess(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path, year=2025, boundary_id="b_2025")
    seed_confirmed_report_workspace(tmp_path, year=2026, boundary_id="b_2026")
    result, intake, table = _complete_result()
    at = _fresh()
    bind_confirmed_company(at.session_state)
    _put_result(at, result, intake, table)
    assert confirmed_reporting_period(at.session_state) is None
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "請確認本次報導期間" in text
    _assert_no_pdf_download(at)
    assert at.session_state[STATE_RESULT] is result
    assert build_emissions_report_from_session(at.session_state) is None


def test_active_draft_period_cannot_download_pdf(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path, year=2025, boundary_id="b_2025")
    workspace = CompanyWorkspace.for_company(root=tmp_path, taiwan_ubn=UBN)
    draft_period = ReportingPeriod(
        reporting_period_id="draft-period-2026",
        reporting_year_suggested=2026,
        confirmation_state=CONFIRMATION_PENDING,
    )
    entity = LegalEntity(
        entity_id="entity_report",
        legal_name=COMPANY,
        jurisdiction="TW",
        taiwan_ubn=UBN,
        confirmation_state=CONFIRMATION_LOCAL,
        locally_confirmed_at="2026-08-01T00:00:00Z",
        responsible_contact_name="測試聯絡人",
        responsible_job_title="永續主管",
    )
    workspace.write_draft(
        InventoryBoundary(
            boundary_id="draft_2026_boundary",
            purpose=PURPOSE_MOENV_FACILITY,
            requirement_status=REQUIREMENT_VOLUNTARY,
            display_name="未確認報導期間",
            reporting_period=draft_period,
            legal_entities=(entity,),
            entity_memberships=(
                LegalEntityMembership(
                    entity_id=entity.entity_id,
                    state=MEMBERSHIP_INCLUDED,
                ),
            ),
            schema_version="inventory-boundary-v1",
        )
    )
    result, intake, table = _complete_result()
    at = _fresh()
    bind_confirmed_company(at.session_state)
    bind_active_reporting_period(at.session_state, draft_period, year=2026)
    _put_result(at, result, intake, table)
    assert confirmed_reporting_period(at.session_state) is None
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    _assert_no_pdf_download(at)
    assert at.session_state[STATE_RESULT] is result


def test_same_boundary_id_draft_is_not_pending_when_current_exists(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(
        tmp_path,
        included_sites=("高雄廠",),
        excluded_sites=(("已停用廠", "客戶確認該廠已停用"),),
    )
    workspace = CompanyWorkspace.for_company(root=tmp_path, taiwan_ubn=UBN)
    period = ReportingPeriod.confirmed(
        reporting_year_suggested=2025,
        reporting_year_confirmed=2025,
        period_start_confirmed="2025-01-01",
        period_end_confirmed="2025-12-31",
    )
    entity = LegalEntity(
        entity_id="entity_report",
        legal_name=COMPANY,
        jurisdiction="TW",
        taiwan_ubn=UBN,
        confirmation_state=CONFIRMATION_LOCAL,
        locally_confirmed_at="2026-08-01T00:00:00Z",
        responsible_contact_name="測試聯絡人",
        responsible_job_title="永續主管",
    )
    workspace.write_draft(
        InventoryBoundary(
            boundary_id="report_confirmed_boundary",
            purpose=PURPOSE_MOENV_FACILITY,
            requirement_status=REQUIREMENT_VOLUNTARY,
            display_name="舊稿",
            reporting_period=period,
            legal_entities=(entity,),
            entity_memberships=(
                LegalEntityMembership(
                    entity_id=entity.entity_id,
                    state=MEMBERSHIP_PENDING,
                ),
            ),
            facility_memberships=(
                FacilityMembership(facility_id="高雄廠", state=MEMBERSHIP_PENDING),
                FacilityMembership(facility_id="台南廠", state=MEMBERSHIP_PENDING),
            ),
            schema_version="inventory-boundary-v1",
        )
    )
    workspace.write_draft(
        InventoryBoundary(
            boundary_id="report_other_draft",
            purpose=PURPOSE_MOENV_FACILITY,
            requirement_status=REQUIREMENT_VOLUNTARY,
            display_name="另一份未解草稿",
            reporting_period=period,
            legal_entities=(entity,),
            entity_memberships=(
                LegalEntityMembership(
                    entity_id="other_entity",
                    state=MEMBERSHIP_PENDING,
                ),
            ),
            facility_memberships=(
                FacilityMembership(facility_id="新竹廠", state=MEMBERSHIP_PENDING),
            ),
            schema_version="inventory-boundary-v1",
        )
    )
    session: dict = {}
    bind_confirmed_company(session)
    scope = load_confirmed_report_scope(session, lang=ZH)
    assert scope is not None
    assert "高雄廠" in scope.sites_included
    assert "高雄廠" not in scope.sites_pending
    assert "台南廠" not in scope.sites_pending
    assert "新竹廠" in scope.sites_pending
    assert COMPANY in scope.entities_included
    assert COMPANY not in scope.entities_pending
    included = set(scope.entities_included) | set(scope.sites_included)
    pending = set(scope.entities_pending) | set(scope.sites_pending)
    excluded = {name for name, _reason in scope.exclusions}
    assert not included.intersection(pending)
    assert not included.intersection(excluded)
    assert not pending.intersection(excluded)
    assert "已停用廠" in excluded
    assert "已停用廠" not in pending
    assert "已停用廠" not in included
