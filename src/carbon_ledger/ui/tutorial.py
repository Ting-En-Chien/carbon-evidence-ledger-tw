"""Immersive first-run product tour for Carbon Evidence Ledger.

Stage 4.2G is desktop-first. The three-step orientation covers company and
operating-location confirmation, existing-file upload, and review of
traceable results on desktop. Mobile guided-tour layout is a deferred
known limitation.
"""

from __future__ import annotations

import base64
import html
from typing import Any

import streamlit as st

from carbon_ledger.ui.i18n import (
    LANG_CODE_TO_OPTION,
    LANG_OPTION_TO_CODE,
    LANG_OPTIONS,
    STATE_LANGUAGE,
    t,
)
from carbon_ledger.ui.tutorial_manifest import (
    TOUR_STEP_COUNT,
    TOUR_VERSION,
    iter_tour_steps,
    step_by_index,
    tour_step_visual,
)

STATE_TUTORIAL_SEEN = "tutorial_seen"
STATE_OPEN_TUTORIAL = "open_tutorial"
STATE_TUTORIAL_OPEN_COUNT = "tutorial_open_count"
STATE_TUTORIAL_COMPLETED = "tutorial_completed"
STATE_TUTORIAL_SESSION_DISMISSED = "tutorial_session_dismissed"
STATE_TUTORIAL_VISIBLE = "tutorial_visible"
STATE_TUTORIAL_STEP = "tutorial_step"
STATE_TUTORIAL_VERSION = "tutorial_version"
STATE_TUTORIAL_NAVIGATING = "tutorial_navigating"
STATE_TUTORIAL_KEEP_OPEN = "tutorial_keep_open"
STATE_TUTORIAL_RENDERED_LANG = "tutorial_rendered_lang"

FORBIDDEN_CUSTOMER_TERMS = (
    "High",
    "Medium",
    "Low",
    "confidence score",
    "activity_type",
    "activity_value",
    "site_id",
    "fingerprint",
    "schema",
    "canonical",
    "parser",
    "obligation_id",
    "rule_id",
    "CASE C",
    "qa_",
)


def get_tutorial_copy(lang: str) -> dict[str, Any]:
    """Return customer-facing tour copy (pure, testable)."""
    steps = []
    for spec in iter_tour_steps():
        steps.append(
            {
                "id": spec["id"],
                "title": t(spec["title_key"], lang),
                "why": t(spec["why_key"], lang),
                "body": t(spec["why_key"], lang),
                "outcome": t(spec["why_key"], lang),
                "action": t(spec["action_key"], lang),
                "next": t(spec["next_key"], lang),
                "alt": t(spec["alt_key"], lang),
                "callouts": [t(item["key"], lang) for item in spec["callouts"]],
            }
        )
    return {
        "title": t("tut.title", lang),
        "subtitle": t("tut.subtitle", lang),
        "steps": steps,
        "helps": t("tut.helps", lang),
        "glossary_hint": "",
        "start_label": t("tut.start", lang),
        "later_label": t("tut.later", lang),
        "prev_label": t("tut.prev", lang),
        "next_label": t("tut.next", lang),
        "progress": t(
            "tut.progress", lang, current=1, total=TOUR_STEP_COUNT
        ),
        "version": TOUR_VERSION,
    }


def tutorial_step_texts(lang: str) -> list[str]:
    """Return beginner step titles (for tests)."""
    return [step["title"] for step in get_tutorial_copy(lang)["steps"]]


def customer_copy_blob(lang: str) -> str:
    copy = get_tutorial_copy(lang)
    parts = [
        copy["title"],
        copy["subtitle"],
        copy["helps"],
        copy["start_label"],
        copy["later_label"],
        copy["prev_label"],
        copy["next_label"],
    ]
    for step in copy["steps"]:
        parts.extend(
            [
                step["title"],
                step["why"],
                step["action"],
                step["next"],
                step["alt"],
                *step["callouts"],
            ]
        )
    return "\n".join(parts)


def ensure_tutorial_state(session_state: Any) -> None:
    """Initialize tutorial flags without forcing a dialog every page change."""
    if STATE_TUTORIAL_SEEN not in session_state:
        session_state[STATE_TUTORIAL_SEEN] = False
    if STATE_OPEN_TUTORIAL not in session_state:
        session_state[STATE_OPEN_TUTORIAL] = False
    if STATE_TUTORIAL_OPEN_COUNT not in session_state:
        session_state[STATE_TUTORIAL_OPEN_COUNT] = 0
    if STATE_TUTORIAL_COMPLETED not in session_state:
        session_state[STATE_TUTORIAL_COMPLETED] = False
    if STATE_TUTORIAL_SESSION_DISMISSED not in session_state:
        session_state[STATE_TUTORIAL_SESSION_DISMISSED] = False
    if STATE_TUTORIAL_VISIBLE not in session_state:
        session_state[STATE_TUTORIAL_VISIBLE] = False
    if STATE_TUTORIAL_STEP not in session_state:
        session_state[STATE_TUTORIAL_STEP] = 1
    if STATE_TUTORIAL_VERSION not in session_state:
        session_state[STATE_TUTORIAL_VERSION] = TOUR_VERSION
    if STATE_TUTORIAL_NAVIGATING not in session_state:
        session_state[STATE_TUTORIAL_NAVIGATING] = False
    if STATE_TUTORIAL_KEEP_OPEN not in session_state:
        session_state[STATE_TUTORIAL_KEEP_OPEN] = False
    if STATE_TUTORIAL_RENDERED_LANG not in session_state:
        session_state[STATE_TUTORIAL_RENDERED_LANG] = ""


def _ss_flag(session_state: Any, key: str, default: Any = False) -> Any:
    """Read session flags without SessionState.get (AppTest-safe)."""
    try:
        if key in session_state:
            return session_state[key]
    except Exception:  # noqa: BLE001
        pass
    try:
        return session_state[key]
    except Exception:  # noqa: BLE001
        return default


def current_tutorial_step(session_state: Any) -> int:
    ensure_tutorial_state(session_state)
    try:
        step = int(session_state[STATE_TUTORIAL_STEP] or 1)
    except Exception:  # noqa: BLE001
        step = 1
    return max(1, min(TOUR_STEP_COUNT, step))


def set_tutorial_step(session_state: Any, step: int) -> None:
    """Move the tour step without touching company or intake facts."""
    ensure_tutorial_state(session_state)
    session_state[STATE_TUTORIAL_STEP] = max(1, min(TOUR_STEP_COUNT, int(step)))
    session_state[STATE_TUTORIAL_NAVIGATING] = True
    session_state[STATE_TUTORIAL_KEEP_OPEN] = True


def tour_should_open(session_state: Any) -> bool:
    ensure_tutorial_state(session_state)
    if bool(_ss_flag(session_state, STATE_OPEN_TUTORIAL)) or bool(
        _ss_flag(session_state, STATE_TUTORIAL_VISIBLE)
    ):
        return True
    if bool(_ss_flag(session_state, STATE_TUTORIAL_COMPLETED)):
        return False
    if bool(_ss_flag(session_state, STATE_TUTORIAL_SESSION_DISMISSED)):
        return False
    return True


def begin_tutorial_view(session_state: Any, *, replay: bool = False) -> None:
    """Record that the dialog is showing. Does not mark the tour completed."""
    ensure_tutorial_state(session_state)
    if replay:
        session_state[STATE_TUTORIAL_STEP] = 1
        session_state["tutorial_stepper"] = "1"
    if not bool(_ss_flag(session_state, STATE_TUTORIAL_VISIBLE)):
        session_state[STATE_TUTORIAL_OPEN_COUNT] = (
            int(_ss_flag(session_state, STATE_TUTORIAL_OPEN_COUNT, 0) or 0) + 1
        )
    session_state[STATE_TUTORIAL_VISIBLE] = True
    session_state[STATE_OPEN_TUTORIAL] = False
    session_state[STATE_TUTORIAL_VERSION] = TOUR_VERSION


def dismiss_tutorial_for_session(session_state: Any) -> None:
    """Close for this session without marking the tour completed."""
    ensure_tutorial_state(session_state)
    session_state[STATE_TUTORIAL_VISIBLE] = False
    session_state[STATE_OPEN_TUTORIAL] = False
    session_state[STATE_TUTORIAL_SESSION_DISMISSED] = True
    session_state[STATE_TUTORIAL_SEEN] = True


def complete_tutorial(session_state: Any) -> None:
    """Mark the tour completed after the final customer action."""
    ensure_tutorial_state(session_state)
    session_state[STATE_TUTORIAL_VISIBLE] = False
    session_state[STATE_OPEN_TUTORIAL] = False
    session_state[STATE_TUTORIAL_COMPLETED] = True
    session_state[STATE_TUTORIAL_SESSION_DISMISSED] = True
    session_state[STATE_TUTORIAL_SEEN] = True


def request_tutorial(session_state: Any) -> None:
    """Open the tutorial from a utility control and restart at step 1."""
    ensure_tutorial_state(session_state)
    session_state[STATE_OPEN_TUTORIAL] = True
    session_state[STATE_TUTORIAL_VISIBLE] = False
    session_state[STATE_TUTORIAL_STEP] = 1
    session_state["tutorial_stepper"] = "1"
    session_state[STATE_TUTORIAL_SESSION_DISMISSED] = False


def mark_tutorial_keep_open(session_state: Any) -> None:
    """Keep the tour open across language changes and in-dialog reruns."""
    ensure_tutorial_state(session_state)
    if bool(_ss_flag(session_state, STATE_TUTORIAL_VISIBLE)):
        session_state[STATE_TUTORIAL_KEEP_OPEN] = True


def _on_dialog_dismiss() -> None:
    state = st.session_state
    if bool(_ss_flag(state, STATE_TUTORIAL_NAVIGATING)) or bool(
        _ss_flag(state, STATE_TUTORIAL_KEEP_OPEN)
    ):
        state[STATE_TUTORIAL_NAVIGATING] = False
        state[STATE_TUTORIAL_KEEP_OPEN] = False
        return
    dismiss_tutorial_for_session(state)


def _pct(value: float) -> str:
    return f"{max(0.0, min(1.0, float(value))) * 100:.3f}%"


def _callout_style(item: dict[str, Any]) -> str:
    top = _pct(item["top"])
    left = float(item["left"])
    if left >= 0.55:
        return f"right:{_pct(1.0 - left)};top:{top};"
    return f"left:{_pct(left)};top:{top};"


def _image_data_uri(path: Any) -> str:
    payload = path.read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _render_step_visual(spec: dict[str, Any], lang: str) -> None:
    visual = tour_step_visual(spec, lang)
    image = visual["path"]
    alt = html.escape(t(spec["alt_key"], lang))
    highlight = visual["highlight"]
    callout_html = []
    for item in spec["callouts"][:1]:
        label = html.escape(t(item["key"], lang))
        callout_html.append(
            "<span class='cel-tour-callout' role='note' style='"
            f"{_callout_style(item)}'>{label}</span>"
        )
    if image.is_file() and image.stat().st_size > 0:
        src = _image_data_uri(image)
        figure = (
            f"<figure class='cel-tour-shot' data-cel-tour-shot='{spec['id']}' "
            f"data-cel-tour-capture='{spec['capture_version']}' "
            f"data-cel-tour-lang='{visual['lang']}' "
            f"data-cel-tour-image='{visual['image']}'>"
            "<div class='cel-tour-shot-frame'>"
            f"<img src='{src}' alt='{alt}' />"
            "<span class='cel-tour-spotlight' aria-hidden='true' style='"
            f"left:{_pct(highlight['left'])};top:{_pct(highlight['top'])};"
            f"width:{_pct(highlight['width'])};height:{_pct(highlight['height'])};"
            "'></span>"
            + "".join(callout_html)
            + "</div></figure>"
        )
    else:
        figure = (
            "<div class='cel-tour-shot cel-tour-shot--missing'>"
            f"<p>{alt}</p></div>"
        )
    st.markdown(figure, unsafe_allow_html=True)


def _render_tutorial_body(lang: str) -> None:
    navigating = bool(_ss_flag(st.session_state, STATE_TUTORIAL_NAVIGATING))
    keep_open = bool(_ss_flag(st.session_state, STATE_TUTORIAL_KEEP_OPEN))
    copy = get_tutorial_copy(lang)
    step_no = current_tutorial_step(st.session_state)
    previous_lang = str(
        _ss_flag(st.session_state, STATE_TUTORIAL_RENDERED_LANG, "") or ""
    )
    if navigating:
        st.session_state["tutorial_stepper"] = str(step_no)
    if keep_open or previous_lang != lang:
        st.session_state["tutorial_language_control"] = LANG_CODE_TO_OPTION.get(
            lang, "繁中"
        )
    st.session_state[STATE_TUTORIAL_NAVIGATING] = False
    st.session_state[STATE_TUTORIAL_KEEP_OPEN] = False
    st.session_state[STATE_TUTORIAL_RENDERED_LANG] = lang
    spec = step_by_index(step_no)
    with st.container():
        st.markdown(
            "<div class='cel-tour-body' data-cel-tour-body='1'></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='cel-tutorial-dialog cel-tour-root' "
            f"data-cel-tutorial-dialog='1' data-cel-tour-step='{spec['id']}' "
            f"data-cel-tour-index='{step_no}'></div>",
            unsafe_allow_html=True,
        )
        progress_col, lang_col = st.columns([3, 1])
        with progress_col:
            st.caption(
                t("tut.progress", lang, current=step_no, total=TOUR_STEP_COUNT)
            )
        with lang_col:
            current_option = LANG_CODE_TO_OPTION.get(lang, "繁中")
            selected = st.segmented_control(
                t("header.language_aria", lang),
                options=list(LANG_OPTIONS),
                default=current_option,
                key="tutorial_language_control",
                label_visibility="collapsed",
            )
            if selected and selected != current_option:
                st.session_state[STATE_LANGUAGE] = LANG_OPTION_TO_CODE[selected]
                mark_tutorial_keep_open(st.session_state)
                st.rerun()
        if step_no == 1:
            st.write(copy["subtitle"])
            st.caption(copy["helps"])
        step_choice = st.segmented_control(
            t("tut.progress", lang, current=step_no, total=TOUR_STEP_COUNT),
            options=[str(index) for index in range(1, TOUR_STEP_COUNT + 1)],
            default=str(step_no),
            key="tutorial_stepper",
            label_visibility="collapsed",
            help=copy["steps"][step_no - 1]["title"],
        )
        if step_choice and int(step_choice) != step_no:
            set_tutorial_step(st.session_state, int(step_choice))
            st.rerun()
        st.markdown(f"**{t(spec['title_key'], lang)}**")
        _render_step_visual(spec, lang)

    with st.container():
        st.markdown(
            "<div class='cel-tour-footer' data-cel-tour-footer='1'></div>",
            unsafe_allow_html=True,
        )
        st.write(t(spec["why_key"], lang))
        st.caption(t(spec["action_key"], lang))
        st.write(t(spec["next_key"], lang))
        prev_col, next_col, skip_col = st.columns(3)
        with prev_col:
            if st.button(
                copy["prev_label"],
                key="tutorial_prev",
                use_container_width=True,
                disabled=step_no <= 1,
            ):
                set_tutorial_step(st.session_state, step_no - 1)
                st.rerun()
        with next_col:
            if step_no >= TOUR_STEP_COUNT:
                if st.button(
                    copy["start_label"],
                    type="primary",
                    use_container_width=True,
                    key="tutorial_start",
                ):
                    complete_tutorial(st.session_state)
                    st.rerun()
            elif st.button(
                copy["next_label"],
                type="primary",
                use_container_width=True,
                key="tutorial_next",
            ):
                set_tutorial_step(st.session_state, step_no + 1)
                st.rerun()
        with skip_col:
            if st.button(
                copy["later_label"],
                use_container_width=True,
                key="tutorial_later",
            ):
                dismiss_tutorial_for_session(st.session_state)
                st.rerun()


def maybe_show_tutorial(session_state: Any, lang: str) -> None:
    """Show the tour once for a new session, or when explicitly requested."""
    ensure_tutorial_state(session_state)
    replay = bool(_ss_flag(session_state, STATE_OPEN_TUTORIAL))
    if not tour_should_open(session_state):
        return
    begin_tutorial_view(session_state, replay=replay)

    @st.dialog(
        t("tut.title", lang),
        width="large",
        on_dismiss=_on_dialog_dismiss,
    )
    def _dialog() -> None:
        _render_tutorial_body(lang)

    _dialog()
