"""First-time tutorial dialog for Carbon Evidence Ledger."""

from __future__ import annotations

from typing import Any

import streamlit as st

from carbon_ledger.ui.i18n import t

STATE_TUTORIAL_SEEN = "tutorial_seen"
STATE_OPEN_TUTORIAL = "open_tutorial"
STATE_TUTORIAL_OPEN_COUNT = "tutorial_open_count"


def get_tutorial_copy(lang: str) -> dict[str, Any]:
    """Return simplified first-run tutorial copy (pure, testable)."""
    return {
        "title": t("tut.title", lang),
        "subtitle": t("tut.subtitle", lang),
        "steps": [
            {
                "title": t("tut.step1_title", lang),
                "body": t("tut.step1_body", lang),
            },
            {
                "title": t("tut.step2_title", lang),
                "body": t("tut.step2_body", lang),
            },
            {
                "title": t("tut.step3_title", lang),
                "body": t("tut.step3_body", lang),
            },
        ],
        "helps": t("tut.helps", lang),
        "glossary_hint": "",
        "start_label": t("tut.start", lang),
        "later_label": t("tut.later", lang),
    }


def _close_tutorial() -> None:
    st.session_state[STATE_TUTORIAL_SEEN] = True
    st.session_state[STATE_OPEN_TUTORIAL] = False
    st.rerun()


def _render_tutorial_body(lang: str) -> None:
    """Shared tutorial content — three steps, no framework lecture."""
    copy = get_tutorial_copy(lang)
    st.markdown(
        '<div class="cel-tutorial-dialog" data-cel-tutorial-dialog="1"></div>',
        unsafe_allow_html=True,
    )
    st.write(copy["subtitle"])
    for index, step in enumerate(copy["steps"], start=1):
        st.markdown(f"**{index}. {step['title']}**")
    st.write(copy["helps"])
    if copy["glossary_hint"]:
        st.caption(copy["glossary_hint"])
    primary, secondary = st.columns(2)
    with primary:
        if st.button(
            copy["start_label"],
            type="primary",
            use_container_width=True,
            key="tutorial_start",
        ):
            _close_tutorial()
    with secondary:
        if st.button(
            copy["later_label"],
            use_container_width=True,
            key="tutorial_later",
        ):
            _close_tutorial()


def ensure_tutorial_state(session_state: Any) -> None:
    """Initialize tutorial flags without forcing a dialog every page change."""
    if STATE_TUTORIAL_SEEN not in session_state:
        session_state[STATE_TUTORIAL_SEEN] = False
    if STATE_OPEN_TUTORIAL not in session_state:
        session_state[STATE_OPEN_TUTORIAL] = False
    if STATE_TUTORIAL_OPEN_COUNT not in session_state:
        session_state[STATE_TUTORIAL_OPEN_COUNT] = 0


def request_tutorial(session_state: Any) -> None:
    """Open the tutorial from a utility control."""
    ensure_tutorial_state(session_state)
    session_state[STATE_OPEN_TUTORIAL] = True


def maybe_show_tutorial(session_state: Any, lang: str) -> None:
    """Show tutorial once per first session, or when explicitly requested."""
    ensure_tutorial_state(session_state)
    should_open = (not bool(session_state[STATE_TUTORIAL_SEEN])) or bool(
        session_state.get(STATE_OPEN_TUTORIAL)
    )
    if not should_open:
        return
    if not session_state[STATE_TUTORIAL_SEEN]:
        session_state[STATE_TUTORIAL_SEEN] = True
    session_state[STATE_OPEN_TUTORIAL] = False
    session_state[STATE_TUTORIAL_OPEN_COUNT] = (
        int(session_state.get(STATE_TUTORIAL_OPEN_COUNT, 0)) + 1
    )

    @st.dialog(t("tut.title", lang), width="medium")
    def _dialog() -> None:
        _render_tutorial_body(lang)

    _dialog()


def tutorial_step_texts(lang: str) -> list[str]:
    """Return beginner step titles (for tests)."""
    return [step["title"] for step in get_tutorial_copy(lang)["steps"]]
