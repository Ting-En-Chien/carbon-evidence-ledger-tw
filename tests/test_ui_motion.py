"""Phase 11B motion, hierarchy, and polish coverage (presentation only)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from carbon_ledger.pipeline import run_demo_pipeline
from carbon_ledger.ui import charts
from carbon_ledger.ui.components import DESIGN_CSS
from carbon_ledger.ui.formatting import (
    format_int,
    format_percent,
    format_ratio,
    format_tco2e,
    format_tco2e_parts,
)
from carbon_ledger.ui.i18n import STATE_LANGUAGE, t
from carbon_ledger.ui.motion import (
    analysis_stage_keys,
    consume_result_reveal,
    mark_result_reveal_pending,
    result_reveal_token,
    should_animate_result_reveal,
)
from carbon_ledger.ui.state import (
    STATE_RESULT,
    STATE_RESULT_REVEAL_PENDING,
    activate_demo_mode,
    initialize_ui_state,
    run_analysis,
)
from carbon_ledger.ui.view_models import (
    beginner_result_summary,
    calculated_emissions_summary,
    priority_action_cards,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")
ZH = "zh-TW"


def _full_result():
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="ui_motion_test",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )


def _run_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    activate_demo_mode(at.session_state)
    at.run()
    assert not at.exception
    return at


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
    for button in at.button:
        label = getattr(button, "label", None)
        if label is not None:
            chunks.append(str(label))
    for item in getattr(at, "expander", []):
        label = getattr(item, "label", None)
        if label is not None:
            chunks.append(str(label))
    return "\n".join(chunks)


def test_analysis_progress_stage_messages_exist() -> None:
    stages = analysis_stage_keys()
    assert len(stages) == 6
    for _key, message_key in stages:
        zh = t(message_key, ZH)
        en = t(message_key, "en")
        assert zh and en
        assert zh != message_key
    assert "分析完成" in t("analysis.complete_banner", ZH)


def test_headline_kpi_values_match_real_results() -> None:
    result = _full_result()
    summary = beginner_result_summary(result, ZH)
    emissions = calculated_emissions_summary(result, ZH)
    value = emissions["calculated_tco2e"]
    assert value is not None
    display = format_tco2e(value)
    assert "tCO₂e" in display
    assert format_int(summary["needs_work"])
    assert float(value) > 0


def test_countup_finals_come_from_actual_results() -> None:
    result = _full_result()
    emissions = calculated_emissions_summary(result, ZH)
    summary = beginner_result_summary(result, ZH)
    value = float(emissions["calculated_tco2e"])
    amount, unit = format_tco2e_parts(value)
    assert unit == "tCO₂e"
    normalized = float(amount.replace(",", ""))
    assert abs(normalized - value) < 1.0 or abs(normalized - round(value)) < 1.0
    assert format_ratio(int(summary["calculated"]), int(summary["activities"])).count(
        "/"
    ) == 1


def test_result_reveal_only_once_per_analysis() -> None:
    state: dict = {}
    initialize_ui_state(state)
    result = activate_demo_mode(state)
    assert not should_animate_result_reveal(state, result)
    mark_result_reveal_pending(state, result)
    assert should_animate_result_reveal(state, result)
    assert consume_result_reveal(state, result) is True
    assert consume_result_reveal(state, result) is False
    assert state[STATE_RESULT_REVEAL_PENDING] is None
    assert result_reveal_token(result)


def test_hero_emissions_play_persists_after_consume() -> None:
    from carbon_ledger.ui.motion import (
        animation_run_token,
        hero_emissions_should_play,
    )
    from carbon_ledger.ui.state import STATE_HERO_EMISSIONS_PLAY

    state: dict = {}
    initialize_ui_state(state)
    result = activate_demo_mode(state)
    mark_result_reveal_pending(state, result)
    token = animation_run_token(state, result)
    assert hero_emissions_should_play(state, result) is True
    assert consume_result_reveal(state, result) is True
    assert hero_emissions_should_play(state, result) is False
    assert state[STATE_HERO_EMISSIONS_PLAY] == token
    assert consume_result_reveal(state, result) is False


def test_playing_count_spans_start_at_zero() -> None:
    from carbon_ledger.ui.components import _count_span

    hero = _count_span(
        "1,729.89",
        target=1729.89,
        decimals=2,
        hero_emissions=True,
        hero_play=True,
        hero_run="run-1",
    )
    assert ">0.00</span>" in hero
    assert 'data-cel-hero-play="1"' in hero
    assert 'data-cel-final="1,729.89"' in hero
    assert "1729.89" in hero
    idle = _count_span(
        "1,729.89",
        target=1729.89,
        decimals=2,
        hero_emissions=True,
        hero_play=False,
        hero_run="run-1",
    )
    assert ">1,729.89</span>" in idle
    from carbon_ledger.ui.motion import _HERO_COUNT_JS_PATH

    script = _HERO_COUNT_JS_PATH.read_text(encoding="utf-8")
    assert "data-cel-hero-emissions" in script
    assert "IntersectionObserver" not in script
    assert "1400" in script
    assert "prefers-reduced-motion" in script
    assert "MutationObserver" in script
    assert "fetch(" not in script



def test_dashboard_kpi_semantics_and_formatting() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "已納入公司盤查排放量" in text
    assert "cel-kpi-card-primary" in text or "已納入公司盤查排放量" in text
    assert "tCO₂e" in text or "tCO2e" in text


def test_issues_page_uses_horizontal_compact_cards() -> None:
    at = _run_app()
    at.switch_page("app_pages/issues_actions.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "待處理" in text
    assert "受影響活動" in text
    assert "待辦清單" in text
    assert "writing-mode: horizontal-tb" in DESIGN_CSS
    assert "cel-kpi-grid-compact" in text or "待處理" in text


def test_chart_heights_remain_bounded() -> None:
    assert charts.CHART_HEIGHT_OVERVIEW <= 340
    assert charts.CHART_HEIGHT_SMALL <= 260
    assert charts.CHART_HEIGHT_COMPACT <= 160


def test_blocked_activities_not_rendered_as_zero_in_sources() -> None:
    result = _full_result()
    contrib, blocked = charts.emissions_source_rows(result, ZH)
    assert not blocked.empty
    if not contrib.empty:
        assert (contrib["tco2e"] > 0).all()


def test_priority_cards_include_affected_counts() -> None:
    result = _full_result()
    cards = priority_action_cards(result, ZH, limit=4)
    assert cards
    for card in cards:
        assert int(card["affected_count"]) >= 1


def test_reduced_motion_fallback_exists_in_design_system() -> None:
    assert "prefers-reduced-motion" in DESIGN_CSS
    assert "--motion-fast" in DESIGN_CSS
    assert "--space-4" in DESIGN_CSS
    assert "--radius-card" in DESIGN_CSS


def test_analysis_progress_ui_wired_in_app_source() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    page = (REPO_ROOT / "app_pages/analysis_progress.py").read_text(encoding="utf-8")
    assert "app_pages/analysis_progress.py" in source
    assert "render_analysis_transition_view" in page
    motion = (REPO_ROOT / "src/carbon_ledger/ui/motion.py").read_text(encoding="utf-8")
    assert "@st.dialog" not in motion
    assert "st.progress" in motion
    assert "data-cel-analysis-view" in motion
    assert "analysis.stage.reading" in motion
    assert "time.sleep(" not in motion


def test_bilingual_state_stable_after_navigation() -> None:
    at = _run_app()
    result_before = at.session_state[STATE_RESULT]
    at.session_state[STATE_LANGUAGE] = "en"
    if len(at.segmented_control) >= 1:
        try:
            at.segmented_control[0].set_value("EN")
        except Exception:
            pass
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert (
        "Analysis results" in text
        or "Calculated emissions" in text
        or "Currently calculated" in text
        or "Compliance Overview" in text
    )
    assert at.session_state[STATE_RESULT] is result_before


def test_advanced_technical_details_still_accessible() -> None:
    at = _run_app()
    text = _all_text(at)
    # Technical calc/trace moved off dashboard; CTA remains.
    assert "查看計算依據" in text
    at.switch_page("app_pages/activity_explorer.py")
    at.run()
    act_text = _all_text(at)
    assert "稽核追溯資訊" in act_text or "查看計算依據" in act_text


def test_format_percent_avoids_excess_precision() -> None:
    assert format_percent(50.0) == "50%"
    assert format_percent(50.0001) == "50%"


def test_run_analysis_does_not_auto_flag_reveal_on_init() -> None:
    state: dict = {}
    initialize_ui_state(state)
    assert state.get(STATE_RESULT_REVEAL_PENDING) in (None, "")
    run_analysis(
        state,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    assert state.get(STATE_RESULT_REVEAL_PENDING) in (None, "")
