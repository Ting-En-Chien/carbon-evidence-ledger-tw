"""Motion / reveal helpers for analysis progress and result reveal.

Presentation only:
- blocking analysis progress dialog driven by real pipeline milestones
- scroll-triggered viewport reveal via IntersectionObserver (client-side)
Respects prefers-reduced-motion. Never mutates calculation results.

Progress events come from optional pipeline callbacks — no time.sleep
fake percentages.
"""

from __future__ import annotations

import html
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from carbon_ledger.pipeline import PipelineRunResult
from carbon_ledger.ui.formatting import format_int, format_result_tco2e_amount
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    ANALYSIS_PHASE_ANALYZING,
    ANALYSIS_PHASE_CLOSING,
    ANALYSIS_PHASE_FAILED,
    ANALYSIS_PHASE_IDLE,
    ANALYSIS_PHASE_REVEAL,
    STATE_ANALYSIS_FAILURE,
    STATE_ANALYSIS_PHASE,
    STATE_ANALYSIS_RUNNING,
    STATE_ANIMATION_RUN,
    STATE_CAPITAL_RUNTIME_READY,
    STATE_COUNTUP_RUNTIME_READY,
    STATE_HERO_EMISSIONS_PLAY,
    STATE_IFRS_TIMELINE_LAST_RUN,
    STATE_IFRS_TIMELINE_RUNTIME_READY,
    STATE_LAST_ANIMATED_RESULT,
    STATE_RESULT,
    STATE_RESULT_REVEAL_PENDING,
    STATE_RUN_ANALYSIS_REQUEST,
    STATE_RUN_UPLOADED_REQUEST,
    _ss_get,
    get_intake_result,
    run_analysis,
    run_uploaded_analysis,
)

ProgressCallback = Callable[[str, float], None]
_SCROLL_JS_PATH = Path(__file__).with_name("scroll_reveal.js")
_HERO_COUNT_JS_PATH = Path(__file__).with_name("hero_emissions_countup.js")
_KPI_COUNT_JS_PATH = Path(__file__).with_name("animated_kpi.js")
_IFRS_TIMELINE_JS_PATH = Path(__file__).with_name("ifrs_timeline.js")


def analysis_stage_keys() -> list[tuple[str, str]]:
    """Ordered beginner-facing analysis stage message keys."""
    return [
        ("reading", "analysis.stage.reading"),
        ("normalize", "analysis.stage.normalize"),
        ("factors", "analysis.stage.factors"),
        ("calculate", "analysis.stage.calculate"),
        ("quality", "analysis.stage.quality"),
        ("issues", "analysis.stage.issues"),
    ]


def result_reveal_token(result: PipelineRunResult) -> str:
    """Stable token identifying one completed analysis result."""
    count = len(result.activity_records_accepted)
    return f"{result.run_id}|{result.ingested_at.isoformat()}|{count}"


def animation_run_token(session_state: Any, result: PipelineRunResult) -> str:
    """Per-execution token so re-analysis always counts up from zero."""
    run = _ss_get(session_state, STATE_ANIMATION_RUN)
    if run:
        return str(run)
    return result_reveal_token(result)


def mark_result_reveal_pending(session_state: Any, result: PipelineRunResult) -> None:
    """Flag that the next results page should play reveal motion once."""
    token = animation_run_token(session_state, result)
    session_state[STATE_RESULT_REVEAL_PENDING] = token
    session_state[STATE_HERO_EMISSIONS_PLAY] = token


def should_animate_result_reveal(session_state: Any, result: PipelineRunResult) -> bool:
    """True only when a pending reveal token matches this result."""
    token = animation_run_token(session_state, result)
    pending = _ss_get(session_state, STATE_RESULT_REVEAL_PENDING)
    return pending == token


def consume_result_reveal(session_state: Any, result: PipelineRunResult) -> bool:
    """Return whether to animate, then mark the token as consumed.

    Does not clear ``STATE_HERO_EMISSIONS_PLAY``: the first clean Dashboard
    paint already computed play from the pending token.
    """
    token = animation_run_token(session_state, result)
    animate = _ss_get(session_state, STATE_RESULT_REVEAL_PENDING) == token
    if animate:
        session_state[STATE_RESULT_REVEAL_PENDING] = None
        session_state[STATE_LAST_ANIMATED_RESULT] = token
        session_state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_REVEAL
    return animate


def hero_emissions_should_play(
    session_state: Any, result: PipelineRunResult
) -> bool:
    """True on the first clean Dashboard paint of a new analysis run token."""
    token = animation_run_token(session_state, result)
    if str(_ss_get(session_state, STATE_LAST_ANIMATED_RESULT) or "") == token:
        return False
    pending = _ss_get(session_state, STATE_RESULT_REVEAL_PENDING)
    hero = _ss_get(session_state, STATE_HERO_EMISSIONS_PLAY)
    return pending == token or hero == token


def _should_defer_countup_runtime() -> bool:
    """Hero JS boots on the first clean results paint. Do not hold it back."""
    return False


def inject_hero_emissions_countup() -> None:
    """Inject dedicated 已計算排放量 count-up (no IntersectionObserver)."""
    if _should_defer_countup_runtime():
        return
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


def inject_animated_kpi_runtime() -> None:
    """Inject reusable analysis-result KPI count-up (not the hero script)."""
    if _should_defer_countup_runtime():
        return
    script = _KPI_COUNT_JS_PATH.read_text(encoding="utf-8")
    stamp = hex(abs(hash(script)) & 0xFFFFFFFF)
    html_body = (
        f"<!-- cel-kpi-metric {stamp} -->\n"
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


def inject_ifrs_timeline_runtime() -> None:
    """Inject IFRS timeline track animation. Presentation only."""
    script = _IFRS_TIMELINE_JS_PATH.read_text(encoding="utf-8")
    stamp = hex(abs(hash(script)) & 0xFFFFFFFF)
    html_body = (
        f"<!-- cel-ifrs-timeline {stamp} -->\n"
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


def schedule_ifrs_timeline_runtime(session_state: Any, *, play: bool) -> None:
    """Hold the track at 0 so first reveal can be observed from the left edge."""
    if not play or bool(_ss_get(session_state, STATE_IFRS_TIMELINE_RUNTIME_READY)):
        return
    if not float(_ss_get(session_state, "_cel_timeline_visible_at") or 0):
        session_state["_cel_timeline_visible_at"] = time.monotonic()

    @st.fragment(run_every=0.4)
    def _arm_timeline_runtime() -> None:
        started = float(_ss_get(session_state, "_cel_timeline_visible_at") or 0)
        if started <= 0 or (time.monotonic() - started) < 0.55:
            return
        session_state[STATE_IFRS_TIMELINE_RUNTIME_READY] = True
        st.rerun()

    _arm_timeline_runtime()


def mark_ifrs_timeline_consumed(session_state: Any, run_id: str) -> None:
    session_state[STATE_IFRS_TIMELINE_LAST_RUN] = str(run_id or "")
    session_state[STATE_IFRS_TIMELINE_RUNTIME_READY] = True


def ifrs_timeline_should_play(session_state: Any, run_id: str) -> bool:
    last = str(_ss_get(session_state, STATE_IFRS_TIMELINE_LAST_RUN) or "")
    return bool(run_id) and last != str(run_id)


def schedule_countup_runtime(session_state: Any, *, play: bool) -> None:
    """Paint KPI zeroes first, then boot client count-up on the next pass.

    Hold the visible 0 after the progress dialog unmounts so the customer
    (and Playwright) can observe 0 before the count-up script starts.
    """
    if not play or bool(_ss_get(session_state, STATE_COUNTUP_RUNTIME_READY)):
        return
    if not float(_ss_get(session_state, "_cel_countup_visible_at") or 0):
        session_state["_cel_countup_visible_at"] = time.monotonic()

    @st.fragment(run_every=2.0)
    def _arm_countup_runtime() -> None:
        started = float(_ss_get(session_state, "_cel_countup_visible_at") or 0)
        if started <= 0 or (time.monotonic() - started) < 2.0:
            return
        session_state[STATE_COUNTUP_RUNTIME_READY] = True
        st.rerun()

    _arm_countup_runtime()


def schedule_capital_countup(session_state: Any, *, play: bool) -> None:
    """Hold visible 0 briefly so the capital count-up can be observed from zero."""
    if not play or bool(_ss_get(session_state, STATE_CAPITAL_RUNTIME_READY)):
        return
    if not float(_ss_get(session_state, "_cel_capital_visible_at") or 0):
        session_state["_cel_capital_visible_at"] = time.monotonic()

    @st.fragment(run_every=0.4)
    def _arm_capital_runtime() -> None:
        started = float(_ss_get(session_state, "_cel_capital_visible_at") or 0)
        if started <= 0 or (time.monotonic() - started) < 0.6:
            return
        session_state[STATE_CAPITAL_RUNTIME_READY] = True
        st.rerun()

    _arm_capital_runtime()


def render_animated_metric(
    value: float | int | None,
    decimals: int = 0,
    suffix: str = "",
    key: str = "metric",
    *,
    play: bool = False,
    run: str = "",
    start_visible_at_zero: bool = False,
    inject_runtime: bool = True,
) -> str:
    """Render a client-side 0 → result KPI. Final value stays in the DOM."""
    if inject_runtime:
        inject_animated_kpi_runtime()
    target = 0.0 if value is None else float(value)
    if decimals > 0:
        final = f"{target:,.{int(decimals)}f}"
    else:
        final = format_int(target)
    play_flag = "1" if play else "0"
    safe_key = html.escape(str(key or "metric"), quote=True)
    safe_run = html.escape(str(run or ""), quote=True)
    safe_final = html.escape(final)
    safe_suffix = html.escape(str(suffix or ""))
    if play and start_visible_at_zero:
        visible = f"{0:.{int(decimals)}f}" if decimals > 0 else "0"
    elif play and not _should_defer_countup_runtime():
        visible = safe_final
    elif play:
        visible = f"{0:.{int(decimals)}f}" if decimals > 0 else "0"
    else:
        visible = safe_final
    html_body = (
        f'<span class="cel-kpi-value" id="cel-kpi-{safe_key}-{safe_run or "idle"}" '
        f'data-cel-kpi-metric="1" '
        f'data-cel-kpi-key="{safe_key}" data-cel-kpi-play="{play_flag}" '
        f'data-cel-kpi-run="{safe_run}" data-cel-target="{target}" '
        f'data-cel-decimals="{int(decimals)}" data-cel-final="{safe_final}">'
        f"{visible}</span>"
    )
    if safe_suffix:
        html_body += f'<span class="cel-kpi-unit-inline"> {safe_suffix}</span>'
    st.markdown(html_body, unsafe_allow_html=True)
    return final


def render_capital_countup(
    value: int,
    *,
    play: bool,
    run: str,
    prefix: str = "NT$",
    metric_key: str = "paid-in-capital",
) -> str:
    """Paid-in capital 0 → official amount. Presentation only.

    Caller should inject the KPI runtime once at page top. This helper
    only paints the numeric span so layout columns stay stable.
    """
    token = str(run or "").replace(":", "-")
    target = int(value)
    final = format_int(target)
    play_flag = "1" if play else "0"
    safe_run = html.escape(token or "", quote=True)
    safe_final = html.escape(final)
    visible = "0" if play else safe_final
    safe_key = html.escape(str(metric_key or "paid-in-capital"), quote=True)
    html_body = (
        "<p class='cel-capital-line'>"
        f"<span class='cel-capital-prefix'>{html.escape(prefix)}</span>"
        f'<span class="cel-kpi-value" id="cel-kpi-{safe_key}-'
        f'{safe_run or "idle"}" data-cel-kpi-metric="1" '
        f'data-cel-kpi-key="{safe_key}" data-cel-kpi-play="{play_flag}" '
        f'data-cel-kpi-run="{safe_run}" data-cel-target="{float(target)}" '
        f'data-cel-decimals="0" data-cel-final="{safe_final}">{visible}</span>'
        "</p>"
    )
    try:
        st.html(html_body)
    except Exception:  # noqa: BLE001 - AppTest / older Streamlit
        st.markdown(html_body, unsafe_allow_html=True)
    return final


def analysis_phase(session_state: Any) -> str:
    """Current analysis presentation phase."""
    return str(_ss_get(session_state, STATE_ANALYSIS_PHASE) or ANALYSIS_PHASE_IDLE)


def should_render_analysis_transition_view(
    session_state: Any, *, run_clicked: bool
) -> bool:
    """Mount the blocking analysis view. Never mount Dashboard underneath.

    RESULT_READY / CLOSING must not remount this view so the next script run
    can navigate to results with the analysis view already gone.
    """
    if run_clicked:
        return True
    return analysis_phase(session_state) in {
        ANALYSIS_PHASE_ANALYZING,
        ANALYSIS_PHASE_FAILED,
    }


def should_open_analysis_progress_dialog(
    session_state: Any, *, run_clicked: bool
) -> bool:
    """Compatibility alias — analysis no longer uses ``st.dialog``."""
    return should_render_analysis_transition_view(
        session_state, run_clicked=run_clicked
    )


def consume_analysis_run_requests(session_state: Any) -> tuple[bool, bool | None]:
    """Consume one-shot start-analysis flags. Returns (clicked, uploaded_mode)."""
    if bool(_ss_get(session_state, STATE_RUN_UPLOADED_REQUEST)):
        session_state[STATE_RUN_UPLOADED_REQUEST] = False
        session_state[STATE_RUN_ANALYSIS_REQUEST] = False
        return True, True
    if bool(_ss_get(session_state, STATE_RUN_ANALYSIS_REQUEST)):
        session_state[STATE_RUN_ANALYSIS_REQUEST] = False
        session_state[STATE_RUN_UPLOADED_REQUEST] = False
        return True, False
    return False, None


def progress_percent_for_stages(completed: int, total: int) -> int:
    """Map completed real stages to a percentage. Never invent sub-progress."""
    if total <= 0:
        return 0
    return int(round(100.0 * min(max(completed, 0), total) / float(total)))


def pending_activity_count(session_state: Any) -> int:
    """Activity rows the current analysis is about to process."""
    from carbon_ledger.ui.state import (
        duplicate_review_blocks_analysis,
        included_activities_for_uploaded_analysis,
    )

    intake = get_intake_result(session_state)
    accepted = getattr(intake, "accepted_activities", None) if intake else None
    if accepted is not None and hasattr(accepted, "__len__"):
        try:
            if intake is not None and not duplicate_review_blocks_analysis(
                session_state
            ):
                included = included_activities_for_uploaded_analysis(session_state)
                return int(len(included))
            return int(len(accepted))
        except (TypeError, ValueError):
            pass
    from carbon_ledger.ui.state import STATE_ANALYSIS_ACTIVITY_COUNT

    return int(_ss_get(session_state, STATE_ANALYSIS_ACTIVITY_COUNT) or 0)


def begin_analysis_presentation_reset(session_state: Any) -> None:
    """Hide stale KPIs before a new analysis starts."""
    session_state[STATE_RESULT] = None
    session_state[STATE_HERO_EMISSIONS_PLAY] = None
    session_state[STATE_RESULT_REVEAL_PENDING] = None
    session_state[STATE_LAST_ANIMATED_RESULT] = None
    session_state[STATE_ANIMATION_RUN] = str(uuid.uuid4())
    session_state[STATE_COUNTUP_RUNTIME_READY] = False
    session_state["_cel_countup_arm_tick"] = 0
    session_state["_cel_countup_visible_at"] = 0.0
    session_state[STATE_ANALYSIS_RUNNING] = True
    session_state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_ANALYZING
    session_state[STATE_ANALYSIS_FAILURE] = None


def _progress_checklist_markdown(
    *,
    lang: str,
    done: set[str],
    current: str,
    percent: float,
) -> str:
    _ = percent
    lines = [""]
    for ui_key, message_key in analysis_stage_keys():
        label = t(message_key, lang)
        if ui_key == current:
            lines.append(f"→ {label}")
        elif ui_key in done:
            lines.append(f"✓ {label}")
        else:
            lines.append(f"○ {label}")
    return "\n".join(lines)


def customer_safe_analysis_error(exc: BaseException, lang: str) -> str:
    """Map pipeline exceptions to plain-language customer messages."""
    from carbon_ledger.potential_duplicates import (
        PotentialDuplicateReviewRequired,
    )

    if isinstance(exc, PotentialDuplicateReviewRequired):
        return t("intake.dup.blocked", lang)
    text = str(exc or "").lower()
    if "potential duplicate" in text:
        return t("intake.dup.blocked", lang)
    if "accepted_activities" in text or "no validated" in text:
        return t("error.analysis_missing_fields", lang)
    if "unit" in text or "encoding" in text:
        return t("error.analysis_unit", lang)
    if "file" in text or "format" in text or "unsupported" in text:
        return t("error.analysis_file_format", lang)
    return t("error.analysis_failed_safe", lang)


def execute_analysis_with_progress(
    session_state: Any,
    *,
    lang: str,
    uploaded_mode: bool,
    include_ghg: bool,
    include_cbam: bool,
    include_ifrs_s2: bool,
) -> PipelineRunResult:
    """Run demo/uploaded analysis with real pipeline milestone feedback.

    Progress is driven by optional pipeline callbacks. No artificial sleeps.
    """
    stages = analysis_stage_keys()
    pipeline_to_ui = {
        "ingest": "reading",
        "normalize": "normalize",
        "factors": "factors",
        "calculate": "calculate",
        "qa": "quality",
        "rules": "issues",
    }
    begin_analysis_presentation_reset(session_state)
    activity_count = pending_activity_count(session_state)

    progress = st.progress(0, text=t("analysis.percent_label", lang, percent=0))
    checklist = st.empty()
    checklist.markdown(
        _progress_checklist_markdown(
            lang=lang,
            done=set(),
            current="reading",
            percent=0.0,
        )
    )
    if activity_count:
        st.caption(t("analysis.processing_count", lang, count=activity_count))

    def _on_progress(stage: str, completed: int, total: int, message: str) -> None:
        _ = message
        ui_key = pipeline_to_ui.get(stage, stage)
        ordered = [key for key, _ in stages]
        current_index = ordered.index(ui_key) if ui_key in ordered else 0
        done_keys = set(ordered[:current_index])
        percent = progress_percent_for_stages(int(completed), int(total))
        progress.progress(
            min(1.0, percent / 100.0),
            text=t("analysis.percent_label", lang, percent=percent),
        )
        checklist.markdown(
            _progress_checklist_markdown(
                lang=lang,
                done=done_keys,
                current=ui_key,
                percent=float(percent),
            )
        )

    try:
        if uploaded_mode:
            result = run_uploaded_analysis(
                session_state,
                include_ghg=include_ghg,
                include_cbam=include_cbam,
                include_ifrs_s2=include_ifrs_s2,
                progress_callback=_on_progress,
            )
        else:
            result = run_analysis(
                session_state,
                include_ghg=include_ghg,
                include_cbam=include_cbam,
                include_ifrs_s2=include_ifrs_s2,
                progress_callback=_on_progress,
            )
    except Exception as exc:
        session_state[STATE_ANALYSIS_RUNNING] = False
        session_state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_FAILED
        session_state[STATE_ANALYSIS_FAILURE] = customer_safe_analysis_error(
            exc, lang
        )
        raise RuntimeError(session_state[STATE_ANALYSIS_FAILURE]) from exc

    mark_result_reveal_pending(session_state, result)
    progress.progress(1.0, text=t("analysis.percent_label", lang, percent=100))
    checklist.markdown(
        _progress_checklist_markdown(
            lang=lang,
            done={key for key, _ in analysis_stage_keys()},
            current="",
            percent=100.0,
        )
    )
    session_state[STATE_ANALYSIS_RUNNING] = False
    session_state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_CLOSING
    return result


def _render_analysis_failure(session_state: Any, lang: str) -> None:
    st.error(t("error.analysis_incomplete", lang))
    st.markdown(f"**{t('analysis.failed_reason', lang)}**")
    st.write(
        str(_ss_get(session_state, STATE_ANALYSIS_FAILURE) or "")
        or t("error.analysis_failed_safe", lang)
    )
    st.markdown(f"**{t('analysis.failed_next', lang)}**")
    st.write(t("analysis.failed_next_body", lang))
    if st.button(
        t("analysis.return_to_data", lang),
        type="primary",
        key="analysis_modal_return_data",
    ):
        session_state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_IDLE
        session_state[STATE_ANALYSIS_FAILURE] = None
        session_state[STATE_ANALYSIS_RUNNING] = False
        st.switch_page("app_pages/data_intake.py")


def render_analysis_transition_view(
    session_state: Any,
    *,
    lang: str,
    uploaded_mode: bool,
    include_ghg: bool,
    include_cbam: bool,
    include_ifrs_s2: bool,
) -> None:
    """Blocking analysis page content. Not a dialog. Dashboard is not mounted."""
    phase = analysis_phase(session_state)
    failed = phase == ANALYSIS_PHASE_FAILED
    if failed:
        title = t("error.analysis_incomplete", lang)
    else:
        title = t("analysis.running_title", lang)
    st.markdown(
        f'<div class="cel-analysis-view" data-cel-analysis-view="1" '
        f'data-cel-analysis-modal="1" role="status" aria-live="polite">'
        f'<p class="cel-page-kicker">{html.escape(t("nav.dashboard", lang))}</p>'
        f'<h1 class="cel-page-title">{html.escape(title)}</h1>'
        f"</div>",
        unsafe_allow_html=True,
    )
    if failed:
        _render_analysis_failure(session_state, lang)
        return
    try:
        execute_analysis_with_progress(
            session_state,
            lang=lang,
            uploaded_mode=uploaded_mode,
            include_ghg=include_ghg,
            include_cbam=include_cbam,
            include_ifrs_s2=include_ifrs_s2,
        )
    except Exception as exc:
        session_state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_FAILED
        session_state[STATE_RUN_UPLOADED_REQUEST] = False
        session_state[STATE_RUN_ANALYSIS_REQUEST] = False
        if not _ss_get(session_state, STATE_ANALYSIS_FAILURE):
            session_state[STATE_ANALYSIS_FAILURE] = customer_safe_analysis_error(
                exc, lang
            )
        _render_analysis_failure(session_state, lang)
        return
    # Unmount this page on the next run; parent then switches to Dashboard.
    st.rerun()


def launch_analysis_progress_dialog(
    session_state: Any,
    *,
    lang: str,
    uploaded_mode: bool,
    include_ghg: bool,
    include_cbam: bool,
    include_ifrs_s2: bool,
) -> None:
    """Compatibility alias for the dedicated analysis transition view."""
    render_analysis_transition_view(
        session_state,
        lang=lang,
        uploaded_mode=uploaded_mode,
        include_ghg=include_ghg,
        include_cbam=include_cbam,
        include_ifrs_s2=include_ifrs_s2,
    )


def post_analysis_dashboard_sections() -> tuple[str, ...]:
    """Canonical post-analysis Compliance Overview section order."""
    return (
        "emissions-summary",
        "scope-breakdown",
        "insight",
        "next-step",
        "detail",
        "professional",
    )


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
    include_secondary_cards: bool = True,
    status_label: str = "",
    disposition_caption: str = "",
    scope_caption: str = "",
    excluded_caption: str = "",
    meta_caption: str = "",
) -> dict[str, Any]:
    """Primary KPI hierarchy; emissions uses dedicated above-fold count-up.

    ``play_hero_count`` drives only the 已計算排放量 number (0 → final) after a
    new analysis. Other cards keep existing scroll-reveal attributes.
    ``include_secondary_cards`` is for non-home surfaces; the post-analysis
    home shows the emissions hero only.
    """
    from carbon_ledger.ui.components import render_saas_kpi_row
    from carbon_ledger.ui.formatting import format_percent, format_ratio

    if status_label:
        st.markdown(f"**{status_label}**")
    if disposition_caption:
        st.caption(disposition_caption)
    if excluded_caption:
        st.caption(excluded_caption)
    if scope_caption:
        st.caption(scope_caption)
    if meta_caption:
        st.caption(meta_caption)

    amount = format_result_tco2e_amount(emissions_value)
    unit = "tCO₂e"
    progress_pct = 100.0 * float(done) / float(max(1, total))
    emissions_target = 0.0 if emissions_value is None else float(emissions_value)
    decimals = 2
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
    cards: list[dict[str, Any]] = [
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
    ]
    if include_secondary_cards:
        cards.append(
            {
                "label": completion_label,
                "value": payload["completion_display"],
                "subtitle": (
                    f"{completion_subtitle} · {payload['completion_percent']}"
                ),
                "progress": progress_pct,
                "accent": "blue",
                "icon": "✓",
                "count": {
                    "target": float(done),
                    "decimals": 0,
                    "final": payload["completion_display"],
                    "ratio_total": int(total),
                    "kpi_metric": True,
                    "kpi_play": bool(play_hero_count),
                    "kpi_run": str(animation_token or ""),
                    "kpi_key": "calculated-count",
                },
            }
        )
        if int(unresolved) > 0:
            cards.append(
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
                        "kpi_metric": True,
                        "kpi_play": bool(play_hero_count),
                        "kpi_run": str(animation_token or ""),
                        "kpi_key": "unresolved-count",
                    },
                }
            )
    _ = (sources, sources_label, sources_subtitle)
    inject_hero_emissions_countup()
    inject_animated_kpi_runtime()
    render_saas_kpi_row(
        cards,
        variant="hero",
        reveal_on_scroll=True,
        scroll_key="dash-kpi",
        tour_target="results-hero",
    )
    _ = animate
    return payload
