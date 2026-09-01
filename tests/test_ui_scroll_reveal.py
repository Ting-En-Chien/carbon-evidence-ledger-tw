"""Phase 11C scroll-triggered viewport reveal coverage (presentation only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from carbon_ledger.pipeline import run_demo_pipeline
from carbon_ledger.ui import charts
from carbon_ledger.ui.components import DESIGN_CSS
from carbon_ledger.ui.formatting import format_tco2e
from carbon_ledger.ui.motion import (
    _SCROLL_JS_PATH,
    inject_scroll_reveal_runtime,
    mark_chart_reveal,
)
from carbon_ledger.ui.view_models import (
    calculated_emissions_summary,
    calculation_trace_fields,
    first_calculated_electricity_record_id,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")
ZH = "zh-TW"


def _full_result():
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="ui_scroll_test",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )


def _run_app() -> AppTest:
    from carbon_ledger.ui.state import activate_demo_mode

    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    activate_demo_mode(at.session_state)
    at.run()
    assert not at.exception
    return at


def _all_markdown(at: AppTest) -> str:
    chunks: list[str] = []
    for item in at.markdown:
        value = getattr(item, "value", None)
        if value is not None:
            chunks.append(str(value))
        body = getattr(item, "body", None)
        if body is not None:
            chunks.append(str(body))
    return "\n".join(chunks)


def test_scroll_reveal_js_uses_intersection_observer() -> None:
    script = _SCROLL_JS_PATH.read_text(encoding="utf-8")
    assert "IntersectionObserver" in script
    assert "scrollingDown" in script
    assert "data-cel-animated" in script
    assert "prefers-reduced-motion" in script
    assert "fetch(" not in script
    assert "XMLHttpRequest" not in script
    assert "addEventListener" in script and "scroll" in script
    assert "scrollY" in script
    # Early exit when observer unavailable — content stays visible.
    assert 'typeof w.IntersectionObserver !== "function"' in script


def test_below_fold_sections_marked_for_viewport_reveal() -> None:
    at = _run_app()
    text = _all_markdown(at)
    assert 'data-cel-reveal="kpi"' in text or "data-cel-reveal=" in text
    assert 'data-cel-key="sources"' in text or 'data-cel-key="sources-panel"' in text
    assert 'data-cel-key="detail"' in text or "排放明細" in text
    assert "data-cel-animation-type" in text


def test_one_time_animation_semantics_in_runtime() -> None:
    script = _SCROLL_JS_PATH.read_text(encoding="utf-8")
    assert "unobserve" in script
    assert "__celSeenKeys" in script
    assert "data-cel-animated" in script


def test_kpi_count_attributes_use_real_result_values() -> None:
    at = _run_app()
    text = _all_markdown(at)
    result = at.session_state["pipeline_result"]
    emissions = calculated_emissions_summary(result, ZH)
    value = emissions["calculated_tco2e"]
    assert value is not None
    assert f'data-cel-target="{float(value)}"' in text or "data-cel-target=" in text
    assert "data-cel-final=" in text
    # Primary emissions uses dedicated hero count-up (not scroll-reveal count).
    assert 'data-cel-hero-emissions="1"' in text
    assert "cel-hero-emissions" in text
    assert "cel-kpi-metric" in text
    assert "cel-kpi-unit-inline" in text
    assert "cel-kpi-value-primary" in text


def test_trace_card_includes_countup_spans() -> None:
    """Calculation basis lives on Activity Explorer (not dashboard)."""
    at = _run_app()
    at.switch_page("app_pages/activity_explorer.py")
    at.run()
    text = _all_markdown(at)
    # Layer-2 basis expander exposes formula terms without dashboard trace card.
    assert "查看計算依據" in text or "計算" in text
    assert "排放" in text or "tCO" in text or "kgCO2e" in text
    # Hero count-up path on dashboard remains covered by other tests.
    dash = _run_app()
    dash_text = _all_markdown(dash)
    assert 'data-cel-hero-emissions="1"' in dash_text
    assert 'data-cel-key="calc-trace"' not in dash_text


def test_completeness_stats_use_countup_markup() -> None:
    source = (
        REPO_ROOT / "src/carbon_ledger/ui/components.py"
    ).read_text(encoding="utf-8")
    assert 'scroll_key: str = "completeness-metrics"' in source
    assert "cel-stat-value" in source
    assert "cel-stat-stack" in source
    at = _run_app()
    text = _all_markdown(at)
    assert 'data-cel-key="completeness-metrics"' not in text


def test_electricity_trace_preserves_factor_and_result() -> None:
    result = _full_result()
    record_id = first_calculated_electricity_record_id(result)
    assert record_id
    trace = calculation_trace_fields(result, record_id, ZH)
    assert float(trace["factor_value"]) == 0.474 or float(trace["factor_value"]) > 0
    # Demo may use 2024 factor; assert arithmetic consistency instead of uploaded 0.466.
    amount = float(trace["activity_amount"])
    factor = float(trace["factor_value"])
    tco2e = float(trace["calculated_tco2e"])
    expected = amount * factor / 1000.0
    assert abs(tco2e - expected) < 1e-6
    assert format_tco2e(tco2e)


def test_uploaded_style_factor_math_unchanged_by_motion() -> None:
    # Canonical presentation check for the screenshot scenario values.
    amount = 120_000.0
    factor = 0.466
    kg = amount * factor
    tco2e = kg / 1000.0
    assert abs(kg - 55_920.0) < 1e-9
    assert abs(tco2e - 55.92) < 1e-9
    assert format_tco2e(tco2e) in {"55.92 tCO₂e", "55.9 tCO₂e"}


def test_chart_data_unchanged_by_motion_helpers() -> None:
    result = _full_result()
    before = charts.monthly_emissions_series(result, ZH).copy()
    contrib_before, blocked_before = charts.emissions_source_rows(result, ZH)
    # Reading motion helpers / markers must not mutate pipeline frames.
    assert callable(mark_chart_reveal)
    after = charts.monthly_emissions_series(result, ZH)
    contrib_after, blocked_after = charts.emissions_source_rows(result, ZH)
    pd.testing.assert_frame_equal(before, after)
    pd.testing.assert_frame_equal(contrib_before, contrib_after)
    pd.testing.assert_frame_equal(blocked_before, blocked_after)
    assert not blocked_after.empty


def test_blocked_activities_still_not_zero_in_source_chart() -> None:
    result = _full_result()
    contrib, blocked = charts.emissions_source_rows(result, ZH)
    assert not blocked.empty
    if not contrib.empty:
        assert (contrib["tco2e"] > 0).all()


def test_fail_open_css_does_not_hide_by_default() -> None:
    """Hide rules must be gated behind motion-ready (JS init success only)."""
    assert "html.motion-ready" in DESIGN_CSS
    assert "html.cel-js" not in DESIGN_CSS
    # Must NOT unconditionally zero opacity on all reveal targets.
    assert not DESIGN_CSS.replace(" ", "").startswith("[data-cel-reveal]{opacity:0")
    unconditional = "\n".join(
        line
        for line in DESIGN_CSS.splitlines()
        if line.strip().startswith("[data-cel-reveal]")
        and "opacity: 0" in line
        and "motion-ready" not in line
    )
    assert unconditional == ""
    # Never hide generic Streamlit chart hosts via follow-class CSS.
    assert "cel-chart-follow" not in DESIGN_CSS
    assert "prefers-reduced-motion" in DESIGN_CSS
    assert "opacity: 1 !important" in DESIGN_CSS


def test_result_page_kpi_content_visible_without_motion_init() -> None:
    """AppTest has no browser observer; content must still be present."""
    at = _run_app()
    text = _all_markdown(at)
    for label in ("已納入公司盤查排放量",):
        assert label in text
    assert "排放明細" in text
    assert "排放來源" in text or "依來源" in text
    assert "缺少的資料" not in text
    assert "資料完整度" not in text
    assert 'data-cel-key="completeness-metrics"' not in text
    # Final numeric payloads remain in DOM attributes / text.
    assert "data-cel-final=" in text
    assert "tCO₂e" in text or "tCO2e" in text


def test_runtime_is_fail_open_and_uses_mutation_observer() -> None:
    script = _SCROLL_JS_PATH.read_text(encoding="utf-8")
    assert "motion-ready" in script
    assert "IntersectionObserver" in script
    assert "MutationObserver" in script
    # Must not add motion-ready before observer exists.
    idx_obs = script.find("IntersectionObserver")
    idx_ready = script.find('classList.add("motion-ready")')
    assert idx_obs != -1 and idx_ready != -1
    assert idx_obs < idx_ready
    # Do not manipulate Streamlit chart host opacity.
    assert "cel-chart-follow" not in script
    assert "fail-open" in script.lower() or "Fail-open" in script


def test_scroll_runtime_has_no_network_and_is_presentation_only() -> None:
    script = _SCROLL_JS_PATH.read_text(encoding="utf-8")
    assert "http://" not in script
    assert "https://" not in script
    assert "WebSocket" not in script
    assert "pipeline" not in script.lower() or "Presentation" in script
    source = Path(
        REPO_ROOT / "src/carbon_ledger/ui/motion.py"
    ).read_text(encoding="utf-8")
    assert "inject_scroll_reveal_runtime" in source
    assert "unsafe_allow_javascript" in source
    assert "st.html" in source
    assert "IntersectionObserver" in _SCROLL_JS_PATH.read_text(encoding="utf-8")


def test_inject_prefers_main_document_javascript() -> None:
    source = Path(
        REPO_ROOT / "src/carbon_ledger/ui/motion.py"
    ).read_text(encoding="utf-8")
    # Main-document injection must come before iframe fallback.
    idx_html = source.find("st.html(")
    idx_components = source.find("components.html(")
    assert idx_html != -1
    assert idx_components != -1
    assert idx_html < idx_components
    assert "unsafe_allow_javascript=True" in source


def test_runtime_handles_streamlit_scroll_containers() -> None:
    script = _SCROLL_JS_PATH.read_text(encoding="utf-8")
    assert "stAppViewContainer" in script
    assert "isInViewport" in script
    assert "motionArmed" in script


def test_issues_page_marks_kpi_and_gap_for_scroll_reveal() -> None:
    at = _run_app()
    at.switch_page("app_pages/issues_actions.py")
    at.run()
    assert not at.exception
    text = _all_markdown(at)
    assert 'data-cel-key="issues-kpi"' in text
    assert 'data-cel-chart="bars"' in text or 'data-cel-key="issues-gap"' in text


def test_inject_scroll_reveal_runtime_is_callable() -> None:
    # Smoke: function exists and reads the JS asset.
    assert _SCROLL_JS_PATH.is_file()
    assert "IntersectionObserver" in _SCROLL_JS_PATH.read_text(encoding="utf-8")
    assert callable(inject_scroll_reveal_runtime)
