"""Focused checks for reporting-period date-range wrapping."""

from __future__ import annotations

from pathlib import Path

from carbon_ledger.ui.components import period_range_inner_html
from carbon_ledger.ui.i18n import t

ROOT = Path(__file__).resolve().parents[1]
ZH = "zh-TW"
EN = "en"


def test_period_range_html_keeps_each_date_intact() -> None:
    html = period_range_inner_html("2026-01-01 – 2026-12-31")
    assert 'data-cel-period-range="1"' in html
    assert 'class="cel-period-start">2026-01-01</span>' in html
    assert 'class="cel-period-end">2026-12-31</span>' in html
    assert 'class="cel-period-sep"' in html


def test_period_range_html_leaves_plain_values_alone() -> None:
    assert period_range_inner_html("12.34") == "12.34"
    assert "&lt;" in period_range_inner_html("<script>")


def test_period_range_css_wraps_before_the_end_date() -> None:
    css = (ROOT / "src/carbon_ledger/ui/visual_system.css").read_text(
        encoding="utf-8"
    )
    block = css.split(".cel-period-range", 1)[1].split(".cel-report-hero", 1)[0]
    assert "flex-wrap: wrap" in block
    assert "white-space: nowrap" in css.split(".cel-period-start", 1)[1][:400]
    assert "white-space: nowrap" in css.split(".cel-period-end", 1)[1][:200]


def test_reports_kpi_renders_wrapping_range(monkeypatch, tmp_path) -> None:
    from streamlit.testing.v1 import AppTest
    from test_emissions_report_closure import (
        bind_confirmed_company,
        seed_confirmed_report_workspace,
    )
    from test_emissions_reports_export_ui import _complete_result

    from carbon_ledger.ui.state import (
        ANALYSIS_SOURCE_UPLOADED,
        STATE_ANALYSIS_SOURCE,
        STATE_INTAKE_FILE_NAME,
        STATE_INTAKE_RESULT,
        STATE_INTAKE_TABLE,
        STATE_RESULT,
        STATE_UPLOADED_ANALYSIS_COMPLETED,
        initialize_ui_state,
    )

    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path, company="報表測試公司")
    result, intake, table = _complete_result()
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    bind_confirmed_company(at.session_state, company="報表測試公司")
    at.session_state[STATE_RESULT] = result
    at.session_state[STATE_INTAKE_RESULT] = intake
    at.session_state[STATE_INTAKE_TABLE] = table
    at.session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_UPLOADED
    at.session_state[STATE_INTAKE_FILE_NAME] = "ops.csv"
    at.session_state[STATE_UPLOADED_ANALYSIS_COMPLETED] = True
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    html = "\n".join(str(getattr(item, "body", "") or "") for item in at.markdown)
    assert 'data-cel-period-range="1"' in html
    assert "cel-period-start" in html
    assert "cel-period-end" in html
    assert t("report.cover.period", ZH) in html or "報導期間" in html
    english = period_range_inner_html("2026-01-01 – 2026-12-31")
    assert "cel-period-start" in english
    assert "Reporting period" == t("report.cover.period", EN)
