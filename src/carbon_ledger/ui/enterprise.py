"""Enterprise SaaS presentation components (Stage 3B.2b visual system)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

from carbon_ledger.ifrs_timeline import (
    MILESTONE_CURRENT,
    MILESTONE_PAST,
    IfrsTimelineView,
)
from carbon_ledger.ui.app_mode import is_admin_mode
from carbon_ledger.ui.customer_presenters import (
    CustomerActionSummary,
    CustomerObligationPresentation,
    present_obligation_card,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.learning import status_chip_html
from carbon_ledger.ui.money_input import (
    format_twd_display,
    money_unit_options,
    normalize_money_to_twd,
    twd_to_display_parts,
)
from carbon_ledger.ui.state import (
    STATE_APPLICABILITY_WIZARD_STEP,
    STATE_COMPANY_PROFILE_EDITING,
)

_VISUAL_CSS_PATH = Path(__file__).with_name("visual_system.css")


def inject_enterprise_styles() -> None:
    css = _VISUAL_CSS_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)


def emit_html(markup: str) -> None:
    """Render a complete HTML fragment without Streamlit markdown splitting.

    Prefer ``st.html`` so nested chips/cards are not broken into literal
    ``</p></div><span…`` text. Fall back to a single markdown call.
    """
    payload = str(markup or "").strip()
    if not payload:
        return
    try:
        st.html(payload)
        return
    except Exception:  # noqa: BLE001 - older Streamlit / AppTest stubs
        pass
    st.markdown(payload, unsafe_allow_html=True)


def render_app_bar(
    *,
    page_title: str,
    company: str,
    reporting_year: str | int | None,
    freshness_label: str,
    freshness_detail: str,
    lang: str,
) -> None:
    st.markdown(
        f"""
        <div class="cel-appbar">
          <p class="cel-appbar-title">{html.escape(page_title)}</p>
          <div class="cel-appbar-meta">
            <span>{html.escape(company)}</span>
            <span>{html.escape(
                t(
                    "dash.legal_year_label",
                    lang,
                    year=str(reporting_year or "—"),
                )
            )}</span>
            <span class="cel-freshness-chip">
              <span class="cel-freshness-dot" aria-hidden="true"></span>
              {html.escape(freshness_label)}
            </span>
            <span>{html.escape(freshness_detail)}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_greeting_block(
    *,
    company: str,
    reporting_year: str | int | None,
    attention_count: int,
    lang: str,
    data_period: str = "",
) -> None:
    company_safe = html.escape(company or t("dash.greeting_company_fallback", lang))
    greeting = t("dash.greeting", lang, company=company_safe)
    legal = html.escape(
        t("dash.legal_year_label", lang, year=str(reporting_year or "—"))
    )
    period = html.escape(str(data_period or "").strip())
    if period:
        period_line = html.escape(t("dash.period_label", lang)) + period
        sub = f"{period_line} · {legal}"
    else:
        sub = legal
    if attention_count > 0:
        extra = html.escape(
            t("dash.greeting_attention_count", lang, n=attention_count)
        )
        sub = f"{sub} · {extra}"
    st.markdown(
        f"""
        <div class="cel-exec-header">
          <h1>{greeting}</h1>
          <p>{sub}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_context_bar(
    *,
    company: str,
    reporting_year: str | int | None,
    freshness_label: str,
    freshness_detail: str,
    lang: str,
) -> None:
    render_app_bar(
        page_title=t("dash.page_title", lang),
        company=company or t("dash.greeting_company_fallback", lang),
        reporting_year=reporting_year,
        freshness_label=freshness_label,
        freshness_detail=freshness_detail,
        lang=lang,
    )


def render_action_card(
    *,
    title: str,
    reason: str,
    priority: str,
    cta_label: str,
    key: str,
    on_click_page: str | None = None,
) -> bool:
    priority_cls = "cel-priority-pill"
    if "高" in priority or priority.lower() in {"high", "高優先"}:
        priority_cls += " cel-priority-pill--high"
    st.markdown(
        f"""
        <div class="cel-card-primary cel-attention-card">
          <span class="{priority_cls}">{html.escape(priority)}</span>
          <p class="cel-card-title">{html.escape(title)}</p>
          <p class="cel-card-reason">{html.escape(reason)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    clicked = st.button(cta_label, key=key, type="primary", use_container_width=True)
    if clicked and on_click_page:
        st.switch_page(on_click_page)
    return clicked


def render_requirement_tile(card: dict[str, Any], lang: str) -> None:
    chip = status_chip_html(
        str(card.get("status") or ""),
        str(card.get("status_label") or ""),
    )
    year = card.get("effective_reporting_year") or "—"
    emit_html(
        "<div class='cel-req-tile'>"
        f"<h4>{html.escape(str(card.get('title') or ''))}</h4>"
        f"{chip}"
        "<p class='cel-card-reason' style='margin-top:8px;'>"
        f"{html.escape(t('apl.effective_year', lang))}: "
        f"{html.escape(str(year))}</p>"
        "</div>"
    )


def render_obligation_result_card(
    card: dict[str, Any] | CustomerObligationPresentation,
    lang: str,
    *,
    show_actions: bool = True,
    show_missing: bool = False,
) -> None:
    """Render a customer presentation card — never a generic backend template."""
    pres = (
        card
        if isinstance(card, CustomerObligationPresentation)
        else present_obligation_card(card, lang)
    )
    chip = status_chip_html(pres.status_code, pres.short_status)
    title_html = html.escape(pres.title)
    timing_html = ""
    if pres.timing_items:
        cells: list[str] = []
        for label, value in pres.timing_items:
            line = html.escape(label or str(value))
            if not line:
                continue
            cells.append(
                "<div class='cel-meta-item'>"
                f"<p class='value cel-meta-year'>{line}</p>"
                "</div>"
            )
        if cells:
            timing_html = (
                "<div class='cel-meta-grid'>" + "".join(cells) + "</div>"
            )
    emit_html(
        "<div class='cel-card-primary cel-obligation-result'>"
        "<div class='cel-decision-head'>"
        "<div class='cel-decision-copy'>"
        f"<p class='cel-card-title'>{title_html}</p>"
        f"<p class='cel-card-reason'>{html.escape(pres.explanation)}</p>"
        "</div>"
        f"<div class='cel-decision-chip'>{chip}</div>"
        "</div>"
        f"{timing_html}"
        "</div>"
    )
    if show_missing and pres.missing_items:
        items = "".join(
            f"<li>{html.escape(str(item))}</li>" for item in pres.missing_items
        )
        emit_html(f"<ul class='cel-missing-bullets'>{items}</ul>")
    if (
        show_actions
        and pres.customer_action_required
        and pres.primary_action_label
    ):
        if st.button(
            pres.primary_action_label,
            key=f"obl_cta_{pres.obligation_id}_{pres.status_code}",
            type="primary",
        ):
            if pres.primary_action_step:
                st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = (
                    pres.primary_action_step
                )
                st.session_state[STATE_COMPANY_PROFILE_EDITING] = True
            if pres.primary_action_target:
                st.switch_page(pres.primary_action_target)
    elif (
        show_actions
        and pres.status_code == "applicable"
        and pres.primary_action_label
    ):
        if st.button(
            pres.primary_action_label,
            key=f"obl_cta_{pres.obligation_id}_{pres.status_code}",
        ):
            if pres.primary_action_target:
                st.switch_page(pres.primary_action_target)
    _render_official_basis(pres, lang)


def compact_outcome_answer(
    pres: CustomerObligationPresentation, lang: str
) -> str:
    if pres.domain in {"ghg_inventory", "env_verification", "carbon_fee"}:
        if pres.status_code == "applicable":
            return f"✓ {t('cust.answer.need', lang)}"
        if pres.status_code == "not_applicable":
            return f"○ {t('cust.answer.not_need', lang)}"
        if pres.status_code == "future_applicable":
            return f"◐ {t('cust.answer.future', lang)}"
    if pres.status_code == "applicable":
        return f"✓ {pres.short_status}"
    if pres.status_code == "not_applicable":
        return f"○ {pres.short_status}"
    return pres.short_status


def render_compact_outcome_row(
    pres: CustomerObligationPresentation,
    lang: str,
    *,
    show_actions: bool = True,
    omit_timing: bool = False,
    show_basis: bool = True,
) -> None:
    """Compact question + answer. No giant empty card. No duplicated status chip."""
    answer = compact_outcome_answer(pres, lang)
    reason = pres.explanation.strip()
    timing_html = ""
    if not omit_timing:
        timing_html = "".join(
            f"<p class='cel-outcome-why cel-meta-year'>{html.escape(label)}</p>"
            for label, _value in pres.timing_items
            if label
        )
    emit_html(
        "<div class='cel-outcome-row'>"
        f"<p class='cel-outcome-q'>{html.escape(pres.title)}</p>"
        f"<p class='cel-outcome-a'>{html.escape(answer)}</p>"
        + (
            f"<p class='cel-outcome-why'>{html.escape(reason)}</p>"
            if reason
            else ""
        )
        + timing_html
        + "</div>"
    )
    if show_actions and pres.primary_action_label:
        if pres.customer_action_required or pres.status_code == "applicable":
            if st.button(
                pres.primary_action_label,
                key=f"obl_cta_{pres.obligation_id}_{pres.status_code}",
            ):
                if pres.primary_action_step:
                    st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = (
                        pres.primary_action_step
                    )
                    st.session_state[STATE_COMPANY_PROFILE_EDITING] = True
                if pres.primary_action_target:
                    st.switch_page(pres.primary_action_target)
    if show_basis:
        _render_official_basis(pres, lang)


def render_customer_notice(*, title: str, body: str) -> None:
    emit_html(
        "<div class='cel-notice-warn' data-cel-facility-notice='1'>"
        f"<p class='cel-notice-warn-title'>{html.escape(title)}</p>"
        f"<p class='cel-notice-warn-body'>{html.escape(body)}</p>"
        "</div>"
    )


def ifrs_timeline_markup(
    view: IfrsTimelineView,
    lang: str,
    *,
    play: bool,
    initial_pct: float,
) -> str:
    """Build the consolidated IFRS timeline HTML. No Streamlit side effects."""
    count = len(view.milestones)
    chips = "".join(
        f"<span class='cel-ifrs-chip'>{html.escape(item)}</span>"
        for item in view.summary_items
    )
    markers: list[str] = []
    captions: list[str] = []
    mobile_items: list[str] = []
    for index, item in enumerate(view.milestones):
        state_cls = {
            MILESTONE_PAST: "is-past",
            MILESTONE_CURRENT: "is-current",
        }.get(item.state, "is-upcoming")
        live_cls = " is-live" if play and item.state == MILESTONE_CURRENT else ""
        revealed = (not play) and index <= view.reveal_through
        visible = "1" if revealed else "0"
        rail_reached = "1" if (not play) and item.state == MILESTONE_PAST else "0"
        past_label = (
            t("ifrs.timeline.past", lang) if item.state == MILESTONE_PAST else ""
        )
        badge = ""
        if item.conditional:
            badge = (
                "<span class='cel-timeline-badge'>"
                f"{html.escape(t('ifrs.timeline.conditional', lang))}</span>"
            )
        elif item.derived:
            badge = (
                "<span class='cel-timeline-badge'>"
                f"{html.escape(t('ifrs.timeline.derived', lang))}</span>"
            )
        aria = html.escape(
            f"{item.period_label} {item.short_action} {item.detail} "
            f"{past_label}".strip()
        )
        markers.append(
            "<div class='cel-timeline-marker "
            f"{state_cls}{live_cls}' "
            f"data-cel-timeline-marker='{index}' "
            f"data-cel-timeline-state='{html.escape(item.state)}' "
            f"title='{html.escape(item.detail, quote=True)}' "
            f"aria-label='{aria}'>"
            "<div class='cel-timeline-dot' data-cel-timeline-dot='desktop' "
            f"data-cel-timeline-visible='{visible}'></div>"
            "</div>"
        )
        captions.append(
            "<div class='cel-timeline-caption "
            f"{state_cls}' data-cel-timeline-caption='{index}' "
            f"title='{html.escape(item.detail, quote=True)}'>"
            "<p class='cel-timeline-period'>"
            f"{html.escape(item.period_label)}</p>"
            "<p class='cel-timeline-action'>"
            f"{html.escape(item.short_action)}{badge}</p>"
            "<p class='cel-timeline-caption-detail'>"
            f"{html.escape(item.detail)}</p>"
            "</div>"
        )
        mobile_items.append(
            "<div class='cel-timeline-mobile-item "
            f"{state_cls}{live_cls}' "
            f"data-cel-timeline-mobile-item='{index}' "
            f"data-cel-timeline-state='{html.escape(item.state)}' "
            f"data-cel-rail-reached='{rail_reached}'>"
            "<div class='cel-timeline-mobile-rail'>"
            "<div class='cel-timeline-dot' data-cel-timeline-dot='mobile' "
            f"data-cel-timeline-visible='{visible}'></div>"
            "</div>"
            "<div class='cel-timeline-mobile-copy'>"
            f"<p class='period'>{html.escape(item.period_label)}{badge}</p>"
            f"<p class='action'>{html.escape(item.short_action)}</p>"
            f"<p class='detail'>{html.escape(item.detail)}</p>"
            + (
                f"<p class='detail'>{html.escape(past_label)}</p>"
                if past_label
                else ""
            )
            + "</div></div>"
        )
    play_flag = "1" if play else "0"
    heading = html.escape(t("ifrs.timeline.heading", lang))
    return (
        "<div class='cel-ifrs-timeline' data-cel-timeline='1' "
        f"data-cel-timeline-run='{html.escape(view.run_identity, quote=True)}' "
        f"data-cel-timeline-play='{play_flag}' "
        f"data-cel-timeline-progress='{view.progress_pct}' "
        f"data-cel-timeline-current='{view.current_index}' "
        f"data-cel-timeline-reveal='{view.reveal_through}' "
        f"data-cel-timeline-count='{count}'>"
        f"<p class='cel-ifrs-timeline-title'>{heading}</p>"
        f"<div class='cel-ifrs-summary'>{chips}</div>"
        "<div class='cel-timeline-desktop' data-cel-timeline-scope='desktop'>"
        "<div class='cel-timeline-lane'>"
        "<div class='cel-timeline-track'>"
        "<span class='cel-timeline-progress' data-cel-timeline-bar='1' "
        f"style='width:{initial_pct:.4f}%;' "
        f"data-cel-timeline-width='{initial_pct}'></span>"
        "</div>"
        f"<div class='cel-timeline-markers'>{''.join(markers)}</div>"
        "</div>"
        f"<div class='cel-timeline-captions'>{''.join(captions)}</div>"
        "</div>"
        "<div class='cel-timeline-mobile' data-cel-timeline-scope='mobile'>"
        f"{''.join(mobile_items)}</div>"
        "<p class='cel-timeline-current-copy'>"
        f"{html.escape(view.current_action)}</p>"
        f"<p class='cel-timeline-note'>{html.escape(view.schedule_note)}</p>"
        "</div>"
    )


def render_ifrs_product_scope(lang: str) -> None:
    """Product capability note beside IFRS applicability results."""
    note = html.escape(t("ifrs.result.product_scope", lang)).replace("\n", "<br>")
    emit_html(f"<p class='cel-outcome-why'>{note}</p>")


def render_ifrs_timeline_section(
    view: IfrsTimelineView,
    lang: str,
    *,
    play: bool,
    initial_pct: float,
) -> None:
    emit_html(
        ifrs_timeline_markup(view, lang, play=play, initial_pct=initial_pct)
    )


def render_ifrs_timeline_evidence(view: IfrsTimelineView, lang: str) -> None:
    with st.expander(t("ifrs.timeline.evidence", lang), expanded=False):
        st.markdown(
            f"**{t('ifrs.timeline.source.phase_rule', lang)}**  \n"
            f"{view.phase_rule_explanation}"
        )
        st.markdown(
            f"**{t('ifrs.timeline.source.october', lang)}**  \n"
            f"{view.october_explanation}"
        )
        st.markdown(
            f"**{t('ifrs.timeline.source.scope3', lang)}**  \n"
            f"{view.scope3_explanation}"
        )
        for source in view.sources:
            st.markdown(
                f"**{t('ifrs.timeline.source.authority', lang)}**  \n"
                f"{source.authority}"
            )
            st.markdown(
                f"**{t('ifrs.timeline.source.document', lang)}**  \n"
                f"{t('ifrs.timeline.source.official_title', lang)}：{source.title}"
            )
            st.markdown(
                f"**{t('ifrs.timeline.source.url', lang)}**  \n{source.url}"
            )
            if source.published_or_effective:
                st.markdown(
                    f"**{t('ifrs.timeline.source.published', lang)}**  \n"
                    f"{source.published_or_effective}"
                )
            st.markdown(
                f"**{t('ifrs.timeline.source.retrieved', lang)}**  \n"
                f"{source.retrieved}"
            )


def render_customer_action_summary(
    summary: CustomerActionSummary, lang: str
) -> None:
    """One merged missing-data action. Hidden when the customer has nothing to do."""
    _ = lang
    if not summary.customer_action_required or not summary.headline:
        return
    facts_html = "".join(
        f"<li>{html.escape(item)}</li>" for item in summary.facts if item
    )
    emit_html(
        "<div class='cel-card-primary cel-action-summary'>"
        f"<p class='cel-card-title'>{html.escape(summary.headline)}</p>"
        + (
            f"<p class='cel-card-reason'>{html.escape(summary.exact_question)}</p>"
            if summary.exact_question
            else ""
        )
        + (
            f"<ol class='cel-missing-bullets'>{facts_html}</ol>"
            if facts_html and not summary.exact_question
            else ""
        )
        + (
            f"<p class='cel-card-reason'>{html.escape(summary.follow_up)}</p>"
            if summary.follow_up
            else ""
        )
        + "</div>"
    )
    if summary.primary_action_label and not summary.answer_controls:
        if st.button(
            summary.primary_action_label,
            key="cust_action_summary_cta",
            type="primary",
        ):
            if summary.primary_action_step:
                st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = (
                    summary.primary_action_step
                )
                st.session_state[STATE_COMPANY_PROFILE_EDITING] = True
            if summary.primary_action_target:
                st.switch_page(summary.primary_action_target)


def _render_official_basis(
    pres: CustomerObligationPresentation, lang: str
) -> None:
    if not pres.show_official_basis:
        return
    with st.expander(t("apl.cta.view_basis", lang), expanded=False):
        if pres.official_authority:
            st.markdown(
                f"**{t('apl.basis.authority', lang)}**  \n"
                f"{pres.official_authority}"
            )
        if pres.official_document:
            st.markdown(
                f"**{t('apl.basis.document', lang)}**  \n"
                f"{pres.official_document}"
            )
        if pres.citations:
            st.markdown(
                f"**{t('apl.basis.citation', lang)}**  \n"
                f"{'；'.join(pres.citations)}"
            )


def render_workflow_journey(steps: list[dict[str, str]], lang: str) -> None:
    parts: list[str] = []
    for step in steps:
        state = step.get("state") or "todo"
        icon = {"done": "✓", "current": "→", "todo": "○"}.get(state, "○")
        parts.append(
            "<div class='cel-journey-step cel-journey-"
            f"{html.escape(state)}'>"
            f"<span class='cel-journey-icon'>{icon}</span>"
            f"<span>{html.escape(step.get('label') or '')}</span>"
            "</div>"
        )
    st.markdown(
        f"""
        <div class="cel-journey">
          <p class="cel-section-title">{t("dash.journey_title", lang)}</p>
          <div class="cel-journey-row">{"".join(parts)}</div>
          <p class="cel-section-help">{t("dash.journey_help", lang)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_stepper(current: int, total: int, labels: list[str], lang: str) -> None:
    nodes: list[str] = []
    for index, label in enumerate(labels, start=1):
        cls = "done" if index < current else ("current" if index == current else "todo")
        nodes.append(
            f"<div class='cel-step cel-step-{cls}'>"
            f"<span class='cel-step-num'>{index}</span>"
            f"<span class='cel-step-label'>{html.escape(label)}</span>"
            "</div>"
        )
    st.markdown(
        f"""
        <div class="cel-stepper">
          <p class="cel-stepper-meta">
            {t("apl.wizard.step_of", lang, current=current, total=total)}
          </p>
          <div class="cel-stepper-row">{"".join(nodes)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_learning_panel(lang: str, *, step: int) -> None:
    title = t(f"learn.wizard.step{step}.title", lang)
    body = t(f"learn.wizard.step{step}.body", lang)
    where = t(f"learn.wizard.step{step}.where", lang)
    why = t(f"learn.wizard.step{step}.why", lang)
    if title.startswith("learn.wizard"):
        title = t("learn.panel_title", lang)
        body = t("apl.company_profile_help", lang)
        where = ""
        why = ""
    parts = [
        f"<h4>{html.escape(title)}</h4>",
        f"<p>{html.escape(body)}</p>",
    ]
    if where and not where.startswith("learn."):
        parts.append(
            "<p><strong>"
            + html.escape(t("learn.where_label", lang))
            + "</strong><br/>"
            + html.escape(where)
            + "</p>"
        )
    if why and not why.startswith("learn."):
        parts.append(
            "<p><strong>"
            + html.escape(t("learn.why_label", lang))
            + "</strong><br/>"
            + html.escape(why)
            + "</p>"
        )
    emit_html(f'<div class="cel-learn-card">{"".join(parts)}</div>')


def render_money_field(
    label: str,
    *,
    lang: str,
    field_key: str,
    saved_twd: int | None,
    unknown_toggle_key: str,
    amount_key: str,
    unit_key: str,
    hint_key: str = "",
) -> int | None:
    """Nullable money input. Unknown must never surface as 0.00."""
    _ = field_key
    st.markdown(f"**{label}**")
    hint_source = hint_key or field_key
    hint = t(f"learn.hint.{hint_source}", lang)
    if hint != f"learn.hint.{hint_source}":
        st.caption(hint)
    why = t(f"learn.why.{hint_source}", lang)
    help_text = why if why != f"learn.why.{hint_source}" else None
    if unknown_toggle_key not in st.session_state:
        st.session_state[unknown_toggle_key] = saved_twd is None
    unknown = st.checkbox(
        t("apl.money.unknown", lang),
        key=unknown_toggle_key,
    )
    if unknown:
        st.caption(t("apl.money.unknown_help", lang))
        # Clear any prior numeric widget residue so 0 is never persisted.
        if amount_key in st.session_state:
            st.session_state[amount_key] = ""
        return None
    amount_default, unit_default = twd_to_display_parts(saved_twd)
    c1, c2 = st.columns([2.2, 1])
    with c1:
        # text_input stays blank; number_input cannot represent nullable empty.
        default_text = (
            ""
            if amount_default is None
            else (
                str(int(amount_default))
                if float(amount_default).is_integer()
                else str(amount_default)
            )
        )
        if amount_key not in st.session_state:
            st.session_state[amount_key] = default_text
        raw = st.text_input(
            label,
            key=amount_key,
            placeholder=t("apl.money.amount_placeholder", lang),
            help=help_text,
            label_visibility="collapsed",
        )
    with c2:
        unit_labels = {
            "yi": t("apl.money.unit.yi", lang),
            "wan": t("apl.money.unit.wan", lang),
            "yuan": t("apl.money.unit.yuan", lang),
        }
        unit = st.selectbox(
            t("apl.money.unit_label", lang),
            options=money_unit_options(),
            index=money_unit_options().index(unit_default),
            format_func=lambda u: unit_labels.get(u, u),
            key=unit_key,
        )
    text = str(raw or "").strip().replace(",", "")
    if not text:
        return None
    try:
        amount = float(text)
    except ValueError:
        st.warning(t("apl.money.invalid_number", lang))
        return None
    twd = normalize_money_to_twd(amount, unit)
    st.caption(format_twd_display(twd, lang=lang))
    return twd


def render_regulatory_status_chip(
    freshness: dict[str, Any],
    lang: str,
) -> None:
    """Compact header chip; expand only when the customer asks for detail."""
    pending = int(freshness.get("pending_reviews") or 0)
    title = html.escape(str(freshness.get("title") or ""))
    state = html.escape(str(freshness.get("state_label") or ""))
    last_label = html.escape(str(freshness.get("last_check_label") or ""))
    last_at = html.escape(str(freshness.get("last_successful_check_at") or "—"))
    st.markdown(
        f"""
        <div class="cel-reg-chip-row">
          <span class="cel-freshness-chip">
            <span class="cel-freshness-dot" aria-hidden="true"></span>
            {title} {state}
          </span>
          <span class="cel-reg-chip-meta">{last_label} {last_at}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if pending > 0:
        render_freshness_summary(freshness, lang)
        return
    with st.expander(t("dash.reg_details", lang), expanded=False):
        render_freshness_summary(freshness, lang)


def render_freshness_summary(freshness: dict[str, Any], lang: str) -> None:
    """Customer-facing regulatory status. Admin metrics only in ADMIN mode."""
    # Prefer concise business wording; never dump raw monitoring enums.
    customer_auto = str(freshness.get("customer_auto_status") or "").strip()
    auto_status = customer_auto or str(freshness.get("auto_status") or "—")
    st.markdown(
        f"""
        <div class="cel-reg-rail">
          <h3>{html.escape(freshness["title"])}</h3>
          <span class="cel-freshness-chip">
            <span class="cel-freshness-dot" aria-hidden="true"></span>
            {html.escape(freshness["state_label"])}
          </span>
          <div class="cel-reg-row">
            <p class="label">{html.escape(freshness["last_check_label"])}</p>
            <p class="value">
              {html.escape(str(freshness.get("last_successful_check_at") or "—"))}
            </p>
            <p class="label">{html.escape(freshness["auto_label"])}</p>
            <p class="value">{html.escape(auto_status)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not is_admin_mode(st.session_state):
        return
    with st.expander(t("reg.admin_expander", lang), expanded=False):
        details = freshness.get("admin_details") or {}
        friendly = {
            "automated_sources_expected": t("reg.admin.expected", lang),
            "automated_sources_successful": t("reg.admin.successful", lang),
            "automated_sources_failed": t("reg.admin.failed", lang),
            "automated_sources_configuration_required": t(
                "reg.admin.config_required", lang
            ),
            "sources_manual_access": t("reg.admin.manual_access", lang),
            "manual_reference_sources": t("reg.admin.manual_reference", lang),
            "restricted_automation_sources": t("reg.admin.restricted", lang),
            "change_signals_pending_review": t("reg.admin.pending_signals", lang),
            "last_verified_regulatory_update_at": t("reg.admin.last_verified", lang),
            "monitoring_health": t("reg.admin.monitoring_health", lang),
            "supporting_sources_note": t("reg.admin.supporting_note", lang),
        }
        for key, value in details.items():
            label = friendly.get(key, key)
            st.caption(f"{label}: {value}")


def render_sidebar_context(
    *,
    reporting_year: str | int | None,
    freshness_label: str,
    lang: str,
) -> None:
    legal = html.escape(
        t("dash.legal_year_label", lang, year=str(reporting_year or "—"))
    )
    raw = (freshness_label or "").strip()
    if raw and "法規" not in raw and lang.startswith("zh"):
        display = f"法規{raw}"
    else:
        display = raw or t("reg.status_verified", lang)
    label = html.escape(display)
    st.markdown(
        f"""
        <div class="cel-sidebar-meta-group">
          <p class="cel-sidebar-fy">{legal}</p>
          <span class="cel-freshness-chip">
            <span class="cel-freshness-dot" aria-hidden="true"></span>
            {label}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
