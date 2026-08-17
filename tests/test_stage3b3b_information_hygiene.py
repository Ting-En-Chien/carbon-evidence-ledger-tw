"""Stage 3B.3b — commercial information hygiene regression tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from carbon_ledger.applicability import CompanyProfile, company_profile_from_mapping
from carbon_ledger.intake import IntakeError, IntakeMetadata, build_source_document_row
from carbon_ledger.pipeline import run_demo_pipeline
from carbon_ledger.ui.app_mode import is_admin_mode
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    activate_demo_mode,
    initialize_ui_state,
)
from carbon_ledger.ui.view_models import (
    audit_summary,
    evidence_documents_customer_view,
    evidence_documents_table,
    issues_table,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
HERO_JS = REPO_ROOT / "src/carbon_ledger/ui/hero_emissions_countup.js"
HERO_JS_SHA256 = (
    "70cd43b7f1fa2bedf4485bc7846278b736e1c183961c6c7117d6cc8b5f5828c0"
)
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")
ZH = "zh-TW"


def _demo_result():
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="stage3b3b_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=False,
        include_ifrs_s2=True,
    )


def _uploaded_like_result():
    """Demo pipeline frames with synthetic flags cleared (company upload shape)."""
    result = _demo_result()
    docs = result.source_documents_accepted.copy()
    if "is_synthetic" in docs.columns:
        docs["is_synthetic"] = False
    if "data_origin" in docs.columns:
        docs["data_origin"] = "company_provided"
    result.source_documents_accepted = docs
    # Use a non-demo ingested_at for audit_summary checks.
    object.__setattr__(result, "ingested_at", pd.Timestamp("2026-08-13T10:00:00Z"))
    object.__setattr__(result, "run_id", "upload_run_2026")
    return result


def _all_text(at: AppTest) -> str:
    chunks: list[str] = []
    for name in (
        "title",
        "header",
        "subheader",
        "markdown",
        "text",
        "caption",
        "info",
        "warning",
        "success",
        "error",
        "expander",
    ):
        collection = getattr(at, name, None)
        if collection is None:
            continue
        for item in collection:
            value = (
                getattr(item, "value", None)
                or getattr(item, "body", None)
                or getattr(item, "label", None)
            )
            if value:
                chunks.append(str(value))
    return "\n".join(chunks)


def test_real_uploaded_evidence_never_says_synthetic_demonstration() -> None:
    result = _uploaded_like_result()
    table = evidence_documents_table(result, ZH)
    blob = table.to_string()
    assert "Synthetic demonstration" not in blob
    assert "示範資料" not in table["status"].astype(str).tolist()
    assert any(
        status in {"已匯入", "待確認", "需要處理", "已驗證"}
        for status in table["status"].astype(str).tolist()
    )


def test_demo_evidence_can_still_be_marked_demo() -> None:
    result = _demo_result()
    table = evidence_documents_table(result, ZH)
    assert "示範資料" in table["status"].astype(str).tolist()


def test_real_audit_summary_has_no_hardcoded_2024_ingestion() -> None:
    result = _uploaded_like_result()
    summary = audit_summary(result)
    assert "2024-02-01T00:00:00+00:00" not in str(summary["ingested_at"])
    assert "2026-08-13" in str(summary["ingested_at"])


def test_demo_audit_summary_keeps_fixture_timestamp() -> None:
    result = _demo_result()
    summary = audit_summary(result)
    assert "2024-02-01" in str(summary["ingested_at"])


def test_unknown_document_date_is_not_date_today() -> None:
    intake_page = (REPO_ROOT / "app_pages/data_intake.py").read_text(encoding="utf-8")
    assert "date.today()" not in intake_page
    meta = IntakeMetadata(
        source_name="x.csv",
        site_id="UNKNOWN",
        document_date=None,
        data_quality_tier="unknown",
        intake_run_id="ui_intake",
        ingested_at=pd.Timestamp.now(tz="UTC"),
    )
    assert meta.document_date is None


def test_unknown_document_date_requires_confirmation() -> None:
    class _Uploaded:
        file_name = "x.csv"
        sha256 = "a" * 64

    meta = IntakeMetadata(
        source_name="x.csv",
        site_id="UNKNOWN",
        document_date=None,
        data_quality_tier="unknown",
        intake_run_id="ui_intake",
        ingested_at=pd.Timestamp.now(tz="UTC"),
    )
    with pytest.raises(IntakeError) as exc:
        build_source_document_row(_Uploaded(), meta)  # type: ignore[arg-type]
    assert exc.value.code == "DOCUMENT_DATE_REQUIRED"


def test_customer_reporting_hides_run_id_and_registry_by_default() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    activate_demo_mode(at.session_state)
    at.switch_page("app_pages/audit_export.py")
    at.run()
    text = _all_text(at)
    assert "一般分析不會" not in text
    assert "automated_sources_expected" not in text
    # Run ID KPI is only inside advanced expander — default groups are business.
    assert "管理摘要" in text or "Management" in text
    assert t("aud.advanced_audit", ZH) in text or "稽核追溯" in text


def test_activity_default_hides_factor_id_audit_exposes() -> None:
    page = (REPO_ROOT / "app_pages/activity_explorer.py").read_text(encoding="utf-8")
    # Default table block must not include factor_id column labeling outside audit.
    assert 't("act.layer.audit"' in page or "act.layer.audit" in page
    assert "factor_id" in page
    # factor_id only appears inside the audit expander payload.
    assert page.index("act.layer.audit") < page.rindex("factor_id")


def test_issues_default_hides_record_id_uses_labels() -> None:
    result = _demo_result()
    table = issues_table(result, ZH)
    if table.empty:
        pytest.skip("demo has no QA issues")
    assert "document_label" in table.columns
    assert "period_label" in table.columns
    page = (REPO_ROOT / "app_pages/issues_actions.py").read_text(encoding="utf-8")
    assert "record_id:`" not in page.replace(" ", "")
    assert "iss.related.activity" in page
    assert "iss.audit_trace" in page


def test_evidence_table_does_not_lead_with_hash() -> None:
    result = _demo_result()
    customer = evidence_documents_customer_view(result, ZH)
    cols = list(customer.columns)
    assert cols[0] == t("ev.col.name", ZH)
    joined = " ".join(cols)
    assert "SHA" not in joined
    assert "sha256" not in joined.lower()
    assert "Evidence hash" not in joined
    full = evidence_documents_table(result, ZH)
    assert "sha256" in full.columns


def test_outdated_demo_notice_removed() -> None:
    notice = t("intake.page_lead", ZH)
    assert "仍顯示示範" not in notice
    assert "demo analysis results remain" not in t("intake.page_lead", "en").lower()
    page = (REPO_ROOT / "app_pages/data_intake.py").read_text(encoding="utf-8")
    assert "intake.page_lead" in page
    assert "intake.demo_notice" not in page


def test_initial_applicability_wizard_hides_sasb() -> None:
    page = (REPO_ROOT / "app_pages/applicability.py").read_text(encoding="utf-8")
    assert "apl_sasb_industry" not in page
    assert "apl.field.sasb_industry" not in page
    # Backend field still persisted from saved profile.
    assert "sasb_industry" in page
    profile = company_profile_from_mapping({"sasb_industry": "Extractives"})
    assert profile.sasb_industry == "Extractives"
    assert "sasb_industry" in CompanyProfile.__dataclass_fields__


def test_dashboard_no_developer_copy_or_calc_trace() -> None:
    page = (REPO_ROOT / "app_pages/dashboard.py").read_text(encoding="utf-8")
    assert "dash.no_fake_score_note" not in page
    assert "calculation_table_rows" not in page
    assert "calculation_trace_fields" not in page
    assert "render_trace_card" not in page


def test_no_raw_monitoring_enum_in_customer_freshness_labels() -> None:
    for code in (
        "MONITORING_PARTIAL",
        "BASELINE_CAPTURED",
        "SOURCE_UNAVAILABLE",
        "NOT_ACTIVATED",
        "OUT_OF_V1_SCOPE",
    ):
        label = t(f"reg.freshness.{code}", ZH)
        assert code not in label
        assert "_" not in label or "／" in label


def test_fresh_customer_six_pages_no_demo_contamination() -> None:
    pages = [
        "app_pages/dashboard.py",
        "app_pages/applicability.py",
        "app_pages/frameworks.py",
        "app_pages/taiwan_ghg.py",
        "app_pages/data_intake.py",
        "app_pages/audit_export.py",
    ]
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    for page in pages:
        at.switch_page(page)
        at.run()
        text = _all_text(at)
        assert "示範公司" not in text
        assert "Synthetic demonstration" not in text
        assert "MONITORING_PARTIAL" not in text
        assert "automated_sources_expected" not in text
        assert "2024-02-01T00:00:00+00:00" not in text


def test_no_site_main_or_2024_defaults_in_customer_intake_path() -> None:
    intake_page = (REPO_ROOT / "app_pages/data_intake.py").read_text(encoding="utf-8")
    assert "site_main" not in intake_page
    assert "date.today()" not in intake_page
    assert 'document_date=None' in intake_page or "document_date=None" in intake_page


def test_hero_countup_unchanged() -> None:
    digest = __import__("hashlib").sha256(HERO_JS.read_bytes()).hexdigest()
    assert digest == HERO_JS_SHA256


def test_admin_mode_retains_technical_reporting(monkeypatch) -> None:
    monkeypatch.setenv("CEL_APP_MODE", "admin")
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert is_admin_mode(at.session_state)
    activate_demo_mode(at.session_state)
    at.switch_page("app_pages/audit_export.py")
    at.run()
    text = _all_text(at)
    assert "稽核追溯" in text or t("aud.audit_trace", ZH) in text
    assert t("aud.ref_title", ZH) in text or "參考" in text
