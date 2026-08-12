"""Motion / reveal helpers for Phase 11B–11C SaaS polish.

Presentation only:
- analysis progress via Streamlit status/progress (real pipeline stages)
- scroll-triggered viewport reveal via IntersectionObserver (client-side)
Respects prefers-reduced-motion. Never mutates calculation results.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from carbon_ledger.pipeline import PipelineRunResult
from carbon_ledger.ui.formatting import format_int, format_tco2e_parts
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_HERO_EMISSIONS_PLAY,
    STATE_LAST_ANIMATED_RESULT,
    STATE_RESULT_REVEAL_PENDING,
    _ss_get,
    run_analysis,
    run_uploaded_analysis,
)

ProgressCallback = Callable[[str, float], None]
_SCROLL_JS_PATH = Path(__file__).with_name("scroll_reveal.js")
_HERO_COUNT_JS_PATH = Path(__file__).with_name("hero_emissions_countup.js")


def analysis_stage_keys() -> list[tuple[str, str]]:
    """Ordered beginner-facing analysis stage message keys."""
    return [
        ("reading", "analysis.stage.reading"),
        ("quality", "analysis.stage.quality"),
        ("factors", "analysis.stage.factors"),
        ("calculate", "analysis.stage.calculate"),
        ("issues", "analysis.stage.issues"),
    ]


def result_reveal_token(result: PipelineRunResult) -> str:
    """Stable token identifying one completed analysis result."""
    count = len(result.activity_records_accepted)
    return f"{result.run_id}|{result.ingested_at.isoformat()}|{count}"


def mark_result_reveal_pending(session_state: Any, result: PipelineRunResult) -> None:
    """Flag that the next results page should play reveal motion once."""
    session_state[STATE_RESULT_REVEAL_PENDING] = result_reveal_token(result)


def should_animate_result_reveal(session_state: Any, result: PipelineRunResult) -> bool:
    """True only when a pending reveal token matches this result."""
    token = result_reveal_token(result)
    pending = _ss_get(session_state, STATE_RESULT_REVEAL_PENDING)
    return pending == token


def consume_result_reveal(session_state: Any, result: PipelineRunResult) -> bool:
    """Return whether to animate, then mark the token as consumed."""
    token = result_reveal_token(result)
    animate = _ss_get(session_state, STATE_RESULT_REVEAL_PENDING) == token
    if animate:
        session_state[STATE_RESULT_REVEAL_PENDING] = None
        session_state[STATE_LAST_ANIMATED_RESULT] = token
        # Persist so Streamlit re-renders of the results page still signal
        # the dedicated hero emissions count-up (JS de-dupes replay).
        session_state[STATE_HERO_EMISSIONS_PLAY] = token
    return animate


def hero_emissions_should_play(
    session_state: Any, result: PipelineRunResult
) -> bool:
    """True while this analysis result should drive the primary KPI count-up."""
    token = result_reveal_token(result)
    return _ss_get(session_state, STATE_HERO_EMISSIONS_PLAY) == token


def inject_hero_emissions_countup() -> None:
    """Inject dedicated 已計算排放量 count-up (no IntersectionObserver)."""
    script = _HERO_COUNT_JS_PATH.read_text(encoding="utf-8")
    stamp = hex(abs(hash(script)) & 0xFFFFFFFF)
    html_body = (
        f"<!-- cel-hero-emissions {stamp} -->\n"
        f"<script>\n{script}\n</script>"
    )
    try:
        st.html(html_body, unsafe_allow_javascript=True)
        return
    except TypeError:
        pass
    except Exception:  # noqa: BLE001
        pass
    components.html(html_body, height=0)


def execute_analysis_with_progress(
    session_state: Any,
    *,
    lang: str,
    uploaded_mode: bool,
    include_ghg: bool,
    include_cbam: bool,
    include_ifrs_s2: bool,
) -> PipelineRunResult:
    """Run demo/uploaded analysis with staged Streamlit status feedback.

    Stages wrap real work. No artificial multi-second sleeps.
    """
    stages = analysis_stage_keys()
    with st.status(t("sidebar.running", lang), expanded=True) as status:
        progress = st.progress(0)

        def _report(index: int) -> None:
            _key, message_key = stages[index]
            status.write(t(message_key, lang))
            progress.progress(min(1.0, (index + 1) / len(stages)))

        _report(0)  # reading activity data / source
        _report(1)  # quality checks (intake already validated; confirm counts)
        _report(2)  # factor matching begins inside pipeline
        _report(3)  # calculate
        if uploaded_mode:
            result = run_uploaded_analysis(
                session_state,
                include_ghg=include_ghg,
                include_cbam=include_cbam,
                include_ifrs_s2=include_ifrs_s2,
            )
        else:
            result = run_analysis(
                session_state,
                include_ghg=include_ghg,
                include_cbam=include_cbam,
                include_ifrs_s2=include_ifrs_s2,
            )
        _report(4)  # organize unresolved issues from QA outputs
        mark_result_reveal_pending(session_state, result)
        status.write(t("analysis.complete_banner", lang))
        status.update(label=t("sidebar.complete", lang), state="complete")
        progress.progress(1.0)
        try:
            st.toast(
                t(
                    "analysis.toast",
                    lang,
                    total=int(len(result.activity_records_accepted)),
                    done=int(
                        (
                            result.calculation_results["calculation_status"]
                            == "calculated"
                        ).sum()
                    )
                    if not result.calculation_results.empty
                    else 0,
                ),
                icon="✅",
            )
        except Exception:  # noqa: BLE001 - toast optional across Streamlit versions
            pass
    return result


def inject_scroll_reveal_runtime() -> None:
    """Inject IntersectionObserver runtime into the Streamlit main document.

    Prefer ``st.html(..., unsafe_allow_javascript=True)`` so the script runs in
    the host page (not a sandboxed iframe). Fall back to ``components.html``
    which attempts ``window.parent.document`` access when needed.
    """
    try:
        st.session_state["_cel_scroll_runtime_injected"] = True
    except Exception:  # noqa: BLE001 - AppTest session proxies vary
        pass
    script = _SCROLL_JS_PATH.read_text(encoding="utf-8")
    # Cache-bust comment so Streamlit re-evaluates after asset changes,
    # while the JS itself still guards against duplicate listener binding.
    stamp = hex(abs(hash(script)) & 0xFFFFFFFF)
    html_body = (
        f"<!-- cel-scroll-reveal {stamp} -->\n"
        f"<script>\n{script}\n</script>"
    )
    # Streamlit >= 1.52: run JS in the main document.
    try:
        st.html(html_body, unsafe_allow_javascript=True)
        return
    except TypeError:
        pass
    except Exception:  # noqa: BLE001 - older / restricted runtimes
        pass
    # Fallback: iframe binder that escapes to parent when same-origin.
    components.html(html_body, height=0)


def mark_chart_reveal(key: str, *, chart: str = "area") -> None:
    """Place a viewport marker that reveals the following Vega chart host."""
    st.markdown(
        (
            f'<div data-cel-reveal="chart" data-cel-key="{key}" '
            f'data-cel-chart="{chart}" data-cel-animation-type="chart" '
            'aria-hidden="true" style="height:0;margin:0;padding:0;"></div>'
        ),
        unsafe_allow_html=True,
    )


def render_skeleton_kpi_row() -> None:
    """Placeholder KPI strip while analysis is preparing results."""
    st.markdown(
        """
        <div class="cel-kpi-grid cel-kpi-grid-hero" aria-hidden="true">
          <div class="cel-skeleton cel-skeleton-kpi cel-skeleton-primary"></div>
          <div class="cel-skeleton cel-skeleton-kpi"></div>
          <div class="cel-skeleton cel-skeleton-kpi"></div>
          <div class="cel-skeleton cel-skeleton-kpi"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_skeleton_charts() -> None:
    """Placeholder chart panels."""
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(
            '<div class="cel-skeleton cel-skeleton-chart" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            '<div class="cel-skeleton cel-skeleton-chart" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )


def render_hero_result_kpis(
    *,
    emissions_value: float | None,
    emissions_label: str,
    emissions_subtitle: str,
    done: int,
    total: int,
    completion_label: str,
    completion_subtitle: str,
    unresolved: int,
    unresolved_label: str,
    unresolved_subtitle: str,
    sources: int,
    sources_label: str,
    sources_subtitle: str,
    animate: bool = False,
    animation_token: str = "",
    play_hero_count: bool = False,
) -> dict[str, Any]:
    """Primary KPI hierarchy; emissions uses dedicated above-fold count-up.

    ``play_hero_count`` drives only the 已計算排放量 number (0 → final) after a
    new analysis. Other cards keep existing scroll-reveal attributes.
    """
    from carbon_ledger.ui.components import render_saas_kpi_row
    from carbon_ledger.ui.formatting import format_percent, format_ratio

    amount, unit = format_tco2e_parts(emissions_value)
    progress_pct = 100.0 * float(done) / float(max(1, total))
    emissions_target = 0.0 if emissions_value is None else float(emissions_value)
    decimals = (
        0
        if abs(emissions_target) >= 100
        else (1 if abs(emissions_target) >= 10 else 2)
    )
    payload = {
        "emissions_display": amount,
        "emissions_unit": unit,
        "emissions_value": emissions_value,
        "completion_display": format_ratio(done, total),
        "completion_percent": format_percent(progress_pct),
        "unresolved_display": format_int(unresolved),
        "sources_display": format_int(sources),
        "progress_pct": progress_pct,
    }
    cards = [
        {
            "label": emissions_label,
            "value": amount,
            "unit": unit,
            "subtitle": emissions_subtitle,
            "primary": True,
            "icon": "◎",
            "accent": "teal",
            "count": {
                "target": emissions_target,
                "decimals": decimals,
                "final": amount,
                "hero_emissions": True,
                "hero_play": bool(play_hero_count),
                "hero_run": str(animation_token or ""),
            },
        },
        {
            "label": completion_label,
            "value": payload["completion_display"],
            "subtitle": f"{completion_subtitle} · {payload['completion_percent']}",
            "progress": progress_pct,
            "accent": "blue",
            "icon": "✓",
            "count": {
                "target": float(done),
                "decimals": 0,
                "final": payload["completion_display"],
                "ratio_total": int(total),
            },
        },
        {
            "label": unresolved_label,
            "value": payload["unresolved_display"],
            "subtitle": unresolved_subtitle,
            "accent": "amber",
            "icon": "!",
            "count": {
                "target": float(unresolved),
                "decimals": 0,
                "final": payload["unresolved_display"],
            },
        },
        {
            "label": sources_label,
            "value": payload["sources_display"],
            "subtitle": sources_subtitle,
            "accent": "slate",
            "icon": "▣",
            "count": {
                "target": float(sources),
                "decimals": 0,
                "final": payload["sources_display"],
            },
        },
    ]
    inject_hero_emissions_countup()
    render_saas_kpi_row(
        cards,
        variant="hero",
        reveal_on_scroll=True,
        scroll_key="dash-kpi",
    )
    _ = animate
    return payload
