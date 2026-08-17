"""Contextual learning-layer helpers (progressive disclosure)."""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from carbon_ledger.ui.glossary import glossary_entry, glossary_pairs
from carbon_ledger.ui.i18n import t


def render_learn_more(
    title: str,
    layer1: str,
    *,
    layer2: str | None = None,
    layer3: str | None = None,
    key: str,
) -> None:
    """Three-layer progressive disclosure for a concept."""
    st.caption(layer1)
    if layer2 or layer3:
        with st.expander(title, expanded=False):
            if layer2:
                st.markdown(layer2)
            if layer3:
                st.caption(layer3)


def render_why_we_ask(
    lang: str,
    *,
    field_key: str,
    key: str,
) -> None:
    """Why-we-ask expander for an important form field."""
    why = t(f"learn.why.{field_key}", lang)
    if why == f"learn.why.{field_key}":
        return
    with st.expander(t("learn.why_label", lang), expanded=False):
        st.markdown(why)
        detail = t(f"learn.why_detail.{field_key}", lang)
        if detail != f"learn.why_detail.{field_key}":
            st.caption(detail)


def render_example(lang: str, *, field_key: str) -> None:
    example = t(f"learn.example.{field_key}", lang)
    if example == f"learn.example.{field_key}":
        return
    st.caption(example)


def render_micro_help(lang: str, *, field_key: str) -> None:
    """One-line just-in-time hint. No permanent lesson panel."""
    hint = t(f"learn.hint.{field_key}", lang)
    if hint == f"learn.hint.{field_key}":
        return
    st.caption(hint)


def render_glossary_term(term_key: str, lang: str) -> None:
    entry = glossary_entry(term_key, lang)
    if not entry:
        return
    title, body = entry
    with st.expander(title, expanded=False):
        st.markdown(body)


def render_requirement_learn_panel(
    lang: str,
    *,
    obligation_key: str,
) -> None:
    """Compact 'Learn this requirement' panel on obligation pages."""
    parts: list[str] = [
        f"<h4>{html.escape(t('learn.panel_title', lang))}</h4>"
    ]
    for suffix in ("what", "why", "need", "first"):
        text = t(f"learn.req.{obligation_key}.{suffix}", lang)
        if text == f"learn.req.{obligation_key}.{suffix}":
            continue
        label = t(f"learn.req.label.{suffix}", lang)
        parts.append(
            f"<p><strong>{html.escape(label)}</strong><br/>"
            f"{html.escape(text)}</p>"
        )
    st.markdown(
        f'<div class="cel-learn-card">{"".join(parts)}</div>',
        unsafe_allow_html=True,
    )


def render_page_intro(
    title: str,
    subtitle: str,
    *,
    status_html: str | None = None,
) -> None:
    status = status_html or ""
    st.markdown(
        f"""
        <div class="cel-page-header">
          <h1 class="cel-page-title">{html.escape(title)}</h1>
          <p class="cel-page-sub">{html.escape(subtitle)}</p>
          {status}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_chip(
    label: str,
    *,
    kind: str = "neutral",
    icon: str = "",
) -> str:
    safe = html.escape(label)
    icon_html = f'<span class="cel-chip-icon">{html.escape(icon)}</span>' if icon else ""  # noqa: E501
    return (
        f'<span class="cel-status-chip cel-status-chip--{html.escape(kind)}">'
        f"{icon_html}{safe}</span>"
    )


STATUS_CHIP_KIND: dict[str, tuple[str, str]] = {
    "APPLICABLE": ("success", "✓"),
    "FUTURE_REQUIREMENT": ("info", "○"),
    "NEEDS_INFORMATION": ("warning", "!"),
    "NEEDS_REVIEW": ("info", "○"),
    "MANUAL_VERIFICATION_REQUIRED": ("info", "○"),
    "NOT_APPLICABLE": ("neutral", "—"),
    "OUT_OF_V1_SCOPE": ("neutral", "—"),
    "NOT_YET_ASSESSED": ("neutral", "○"),
    "REGULATORY_DATA_STALE": ("danger", "!"),
    "applicable": ("success", "✓"),
    "not_applicable": ("neutral", "—"),
    "future_applicable": ("info", "○"),
    "needs_company_data": ("warning", "!"),
    "system_review": ("info", "○"),
    "no_automatic_result": ("neutral", "○"),
    "not_started": ("neutral", "○"),
    "unsupported": ("neutral", "—"),
}


def status_chip_html(status: str, label: str) -> str:
    kind, icon = STATUS_CHIP_KIND.get(status, ("neutral", "•"))
    return render_status_chip(label, kind=kind, icon=icon)


def glossary_lookup_html(lang: str) -> list[dict[str, Any]]:
    return [{"term": a, "body": b} for a, b in glossary_pairs(lang)]
