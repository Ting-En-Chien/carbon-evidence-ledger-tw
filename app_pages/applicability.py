"""Applicability — confirm company and sites, then show results."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import streamlit as st

from carbon_ledger.applicability import (
    assess_applicability,
    company_profile_from_mapping,
)
from carbon_ledger.company_lookup import (
    apply_customer_capital_override,
    lookup_company,
    merge_manual_company,
)
from carbon_ledger.company_master import (
    IDENTITY_INCORRECT,
    IDENTITY_STATUSES,
    MATCH_OFFICIAL_ONLY,
    MATCH_UPLOAD_ONLY,
    SOURCE_MANUAL,
    STATUS_INACTIVE,
    CompanyMaster,
    FacilityMaster,
    FacilityMasterRecord,
    OfficialFactoryHint,
    apply_reuse_previous,
    clear_exception_drafts_dirty,
    commit_identity_drafts,
    confirm_all_operating,
    exception_drafts_are_dirty,
    exception_navigation_blocked,
    mark_exception_drafts_dirty,
    normalize_site_name,
    taiwan_facility_existence,
    utc_now_iso,
)
from carbon_ledger.company_workspace import CompanyWorkspace, default_workspace_root
from carbon_ledger.ifrs_timeline import first_stage_timeline_from_assessment
from carbon_ledger.inventory_boundary import (
    CATEGORY_NOT_EXPECTED,
    CATEGORY_PENDING,
    EXISTING_SCOPE_DRAFT_ZH,
    MEMBERSHIP_EXCLUDED,
    MEMBERSHIP_INCLUDED,
    MEMBERSHIP_NOT_PERIOD,
    MEMBERSHIP_PENDING,
    PURPOSE_LISTED_CONSOLIDATED,
    PURPOSE_MOENV_FACILITY,
    REQUIREMENT_NEEDS_FACT,
    ConfirmerDetailsError,
    ExpectedSourceCategory,
    FacilityMembership,
    InventoryBoundary,
    LegalEntityMembership,
    RegistrationLink,
    ReportingPeriod,
    confirmer_details_are_complete,
    draft_boundaries_from_assessment,
    migrate_legacy_scope_draft,
    normalize_confirmer_details,
    validate_registration_combinations,
)
from carbon_ledger.legal_entity import CONFIRMATION_LOCAL, LegalEntity
from carbon_ledger.ui.boundary_wizard import render_boundary_wizard
from carbon_ledger.ui.company_setup import (
    GROUP_SELF_ONLY,
    GROUP_UNKNOWN,
    GROUP_WITH_SUBS,
    apply_group_choice,
    entity_needs_customer,
    factory_source_as_of,
    infer_entity_from_listing,
    listing_customer_label_key,
    listing_needs_customer,
    merge_profile_from_setup,
    official_factory_records,
    rebuild_facility_master,
    session_update_from_lookup,
    show_capital_for_entity,
    show_fhc_for_entity,
    show_net_worth,
    source_discrepancy_records,
)
from carbon_ledger.ui.components import inject_design_system
from carbon_ledger.ui.customer_presenters import present_assessment
from carbon_ledger.ui.enterprise import (
    inject_enterprise_styles,
    render_compact_outcome_row,
    render_customer_action_summary,
    render_customer_notice,
    render_ifrs_product_scope,
    render_ifrs_timeline_evidence,
    render_ifrs_timeline_section,
    render_money_field,
    render_stepper,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.ifrs_readiness import (
    build_ifrs_readiness_view,
    render_ifrs_readiness_section,
    try_load_reporting_entity_confirmation,
)
from carbon_ledger.ui.learning import render_micro_help
from carbon_ledger.ui.money_input import format_twd_display
from carbon_ledger.ui.motion import (
    ifrs_timeline_should_play,
    inject_animated_kpi_runtime,
    inject_ifrs_timeline_runtime,
    mark_ifrs_timeline_consumed,
    render_capital_countup,
    schedule_capital_countup,
    schedule_ifrs_timeline_runtime,
)
from carbon_ledger.ui.state import (
    REPO_ROOT,
    STATE_APPLICABILITY_WIZARD_STEP,
    STATE_BOUNDARY_WIZARD_DEFERRED,
    STATE_BOUNDARY_WIZARD_RESULTS,
    STATE_CAPITAL_LOOKUP_GEN,
    STATE_CAPITAL_PLAY_UBN,
    STATE_CAPITAL_RUNTIME_READY,
    STATE_COMPANY_LOOKUP_MANUAL,
    STATE_COMPANY_LOOKUP_NOT_FOUND,
    STATE_COMPANY_PROFILE_EDITING,
    STATE_FACILITY_EXCEPTION_MODE,
    STATE_IFRS_TIMELINE_RUNTIME_READY,
    STATE_WIZARD_MAX_STEP,
    get_applicability_assessment,
    get_company_master_mapping,
    get_company_profile_mapping,
    get_current_result,
    get_facility_master_mapping,
    get_language,
    save_applicability_assessment,
    save_company_master_mapping,
    save_company_profile,
    save_facility_master_mapping,
)
from carbon_ledger.ui.tutorial import (
    note_entered_company_setup,
    onboarding_running,
    onboarding_target,
    render_applicability_page_hint,
)

inject_design_system()
inject_enterprise_styles()
note_entered_company_setup(st.session_state)
lang = get_language(st.session_state)
repo_root = Path(REPO_ROOT)

saved = get_company_profile_mapping(st.session_state)
editing = bool(st.session_state.get(STATE_COMPANY_PROFILE_EDITING, True)) or not saved
step = int(st.session_state.get(STATE_APPLICABILITY_WIZARD_STEP) or 1)
step = max(1, min(STATE_WIZARD_MAX_STEP, step))
boundary_host_visible = bool(
    (editing and step == STATE_WIZARD_MAX_STEP)
    or (
        not editing
        and saved
        and get_applicability_assessment(st.session_state) is not None
    )
)
if not boundary_host_visible:
    st.markdown(
        f"""
        <p class="cel-page-kicker">{t("nav.applicability", lang)}</p>
        <h1 class="cel-page-title">{t("apl.title", lang)}</h1>
        <p class="cel-page-sub">{t("apl.subtitle", lang)}</p>
        """,
        unsafe_allow_html=True,
    )

ENTITY_OPTIONS = [
    "unresolved",
    "general_listed_company",
    "general_otc_company",
    "financial_holding_company",
    "bank",
    "bills_finance_company",
    "securities_firm",
    "futures_commission_merchant",
    "other",
]
LISTING_OPTIONS = [
    "UNKNOWN",
    "TWSE",
    "TPEX",
    "EMERGING",
    "PRIVATE",
    "NOT_APPLICABLE",
]
TRI = ["NOT_SURE", "YES", "NO"]
BOOL_TRI = ["UNKNOWN", "TRUE", "FALSE"]
SITE_KINDS = ("factory", "office", "warehouse", "other")
STEP_LABELS = [
    t("apl.wizard.step1", lang),
    t("apl.wizard.step2", lang),
    t("apl.wizard.step3", lang),
    t("apl.wizard.step4", lang),
]


def _label_entity(code: str) -> str:
    return t(f"apl.entity.{code}", lang)


def _label_listing(code: str) -> str:
    return t(f"apl.listing.{code}", lang)


def _label_choice(code: str) -> str:
    return t(f"apl.choice.{code}", lang)


def _load_company() -> CompanyMaster:
    return CompanyMaster.from_dict(get_company_master_mapping(st.session_state))


def _load_facilities() -> FacilityMaster:
    return FacilityMaster.from_dict(get_facility_master_mapping(st.session_state))


def _store_company(company: CompanyMaster) -> None:
    save_company_master_mapping(st.session_state, company.to_dict())


def _store_facilities(master: FacilityMaster) -> None:
    save_facility_master_mapping(st.session_state, master.to_dict())


def _view_current_results() -> None:
    st.session_state[STATE_BOUNDARY_WIZARD_DEFERRED] = False
    st.session_state[STATE_BOUNDARY_WIZARD_RESULTS] = True
    st.session_state[STATE_COMPANY_PROFILE_EDITING] = False
    st.rerun()


def _persist_partial(mapping: dict) -> None:
    company = _load_company()
    facilities = _load_facilities()
    merged = merge_profile_from_setup(saved, company, facilities, mapping)
    save_company_profile(st.session_state, merged)
    st.session_state[STATE_COMPANY_PROFILE_EDITING] = True


def _render_results(assessment) -> None:
    presented = present_assessment(assessment, lang)
    st.markdown(
        "<span data-cel-tour-target='applicability-results'></span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"### {t('cust.results.heading', lang)}")
    render_applicability_page_hint(lang)
    render_customer_action_summary(presented.action_summary, lang)
    summary = presented.action_summary
    if summary.customer_action_required and summary.answer_controls:
        cols = st.columns(3)
        answers = (
            ("YES", t("cust.cta.notice_yes", lang)),
            ("NO", t("cust.cta.notice_no", lang)),
            ("NOT_SURE", t("cust.cta.notice_unsure", lang)),
        )
        for column, (code, label) in zip(cols, answers, strict=True):
            with column:
                if st.button(
                    label,
                    key=f"cust_notice_{code}",
                    use_container_width=True,
                ):
                    mapping = dict(get_company_profile_mapping(st.session_state))
                    mapping["received_environmental_authority_inventory_notice"] = code
                    mapping["received_verification_requirement"] = code
                    profile = company_profile_from_mapping(mapping)
                    updated = assess_applicability(profile, repo_root=repo_root)
                    save_company_profile(st.session_state, mapping)
                    save_applicability_assessment(st.session_state, updated)
                    st.rerun()
    elif (
        summary.customer_action_required
        and summary.primary_action_label
        and not summary.answer_controls
    ):
        pass
    snapshot = assessment.company_profile_snapshot or {}
    company = _load_company()
    timeline = first_stage_timeline_from_assessment(
        assessment,
        ubn=str(
            company.unified_business_number
            or snapshot.get("unified_business_number")
            or ""
        ),
        lang=lang,
    )
    ifrs_cards = [
        card
        for card in presented.presentations
        if card.domain in {"ifrs", "ifrs_assurance"}
    ]
    other_cards = [
        card
        for card in presented.presentations
        if card.domain not in {"ifrs", "ifrs_assurance"}
    ]
    if timeline is not None:
        play_identity = ifrs_timeline_should_play(
            st.session_state, timeline.run_identity
        )
        if play_identity:
            schedule_ifrs_timeline_runtime(st.session_state, play=True)
        runtime_ready = bool(
            st.session_state.get(STATE_IFRS_TIMELINE_RUNTIME_READY)
        )
        animate = play_identity and runtime_ready
        if play_identity:
            initial_pct = 0.0
        else:
            initial_pct = timeline.progress_pct
        if animate:
            inject_ifrs_timeline_runtime()
        render_ifrs_timeline_section(
            timeline,
            lang,
            play=animate,
            initial_pct=initial_pct,
        )
        if animate:
            mark_ifrs_timeline_consumed(st.session_state, timeline.run_identity)
        if ifrs_cards:
            st.markdown(f"**{t('ifrs.timeline.rows_heading', lang)}**")
            render_ifrs_product_scope(lang)
        for card in ifrs_cards:
            render_compact_outcome_row(
                card,
                lang,
                show_actions=not presented.action_summary.customer_action_required,
                omit_timing=True,
                show_basis=False,
            )
        render_ifrs_timeline_evidence(timeline, lang)
    elif ifrs_cards:
        st.markdown(f"**{t('cust.results.outcomes', lang)}**")
        render_ifrs_product_scope(lang)
        for card in ifrs_cards:
            render_compact_outcome_row(
                card,
                lang,
                show_actions=not presented.action_summary.customer_action_required,
            )
    if timeline is not None or ifrs_cards:
        company_master = get_company_master_mapping(st.session_state)
        profile = get_company_profile_mapping(st.session_state)
        readiness = build_ifrs_readiness_view(
            company_profile=profile,
            assessment=assessment,
            pipeline_result=get_current_result(st.session_state),
            reporting_entity_confirmed=try_load_reporting_entity_confirmation(
                taiwan_ubn=str(
                    company_master.get("unified_business_number")
                    or snapshot.get("unified_business_number")
                    or ""
                ),
                entity_id=str(company_master.get("company_id") or ""),
                repo_root=repo_root,
                reporting_year=(
                    getattr(assessment, "reporting_year", None)
                    or (profile or {}).get("reporting_year")
                    or snapshot.get("reporting_year")
                ),
            ),
        )
        render_ifrs_readiness_section(readiness, lang)
    if other_cards:
        st.markdown(f"**{t('cust.results.outcomes', lang)}**")
        for card in other_cards:
            render_compact_outcome_row(
                card,
                lang,
                show_actions=not presented.action_summary.customer_action_required,
            )


def _date_or_default(value: str, default: date) -> date:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return default


def _boundary_choice_label(boundary: InventoryBoundary) -> str:
    if boundary.display_name == EXISTING_SCOPE_DRAFT_ZH:
        return t("boundary.legacy.title", lang)
    purpose = t(f"boundary.purpose.{boundary.purpose}", lang)
    if boundary.registration_links:
        registration = boundary.registration_links[0].registration_identity
        return f"{purpose} · {registration}"
    return purpose


def _boundary_confirmation_status(*, locally_confirmed: bool) -> str:
    key = (
        "boundary.confirmation.locally_confirmed"
        if locally_confirmed
        else "boundary.confirmation.pending"
    )
    return t(key, lang)


def _boundary_legal_status(boundary: InventoryBoundary) -> str:
    return t(
        "boundary.legal_status",
        lang,
        status=t(f"boundary.requirement.{boundary.requirement_status}", lang),
    )


def _reporting_period_label(boundary: InventoryBoundary) -> str:
    period = boundary.reporting_period
    return t(
        "boundary.period.option",
        lang,
        year=period.reporting_year_confirmed,
        start=period.period_start_confirmed,
        end=period.period_end_confirmed,
    )


def _boundary_missing_fact_text(boundary: InventoryBoundary) -> str:
    facts = [
        t(f"boundary.missing.{fact}", lang)
        for fact in boundary.missing_company_facts
    ]
    facts = [fact for fact in facts if fact]
    if facts:
        return t("boundary.missing_fact", lang, fact="；".join(facts))
    return ""


def _boundary_resolution_text(boundary: InventoryBoundary) -> str:
    if boundary.missing_company_facts:
        fact = boundary.missing_company_facts[0]
        translated = t(f"boundary.resolve.{fact}", lang)
        if translated and not translated.startswith("boundary.resolve."):
            return translated
    return boundary.missing_fact_resolution


def _boundary_error_message(error: ValueError) -> str:
    message = str(error)
    mappings = (
        ("at least one legal entity", "boundary.error.included_entity"),
        ("included registered facility", "boundary.error.included_registration"),
        ("requires its registered facility", "boundary.error.included_registration"),
        ("reason and evidence", "boundary.error.exclusion_support"),
        ("not_expected", "boundary.error.not_expected_reason"),
        ("annual or fiscal-period", "boundary.error.period"),
        ("canonical identity", "boundary.error.period"),
        ("memberships require confirmation", "boundary.error.pending"),
        ("source categories require confirmation", "boundary.error.pending"),
        ("registration combination", "boundary.error.combination"),
        ("circular registration", "boundary.error.combination"),
    )
    for token, key in mappings:
        if token in message:
            return t(key, lang)
    return t("boundary.confirm_error", lang)


def _render_boundary_confirmation(
    assessment,
    company: CompanyMaster,
    facilities: FacilityMaster,
) -> bool:
    """Render 4.2H-A local confirmation without changing applicability results."""
    # included_in_current_reporting_scope is read only by the legacy draft
    # migration below; it never becomes a locally confirmed boundary fact.
    # has_real_uploaded_activity is deliberately not consulted here: uploaded
    # coverage reconciliation belongs to Stage 4.2H-B.
    drafts = list(
        draft_boundaries_from_assessment(
            assessment=assessment,
            company=company,
            facilities=facilities.records,
        )
    )
    legacy = migrate_legacy_scope_draft(
        company=company,
        facilities=facilities.records,
        reporting_year_suggested=getattr(assessment, "reporting_year", None),
    )
    if legacy is not None:
        drafts.append(legacy)

    st.markdown(f"## {t('boundary.heading', lang)}")
    st.write(t("boundary.intro", lang))
    with st.expander(t("boundary.local.heading", lang), expanded=False):
        st.write(t("boundary.local.summary", lang))
        st.write(t("boundary.local.details", lang))
        st.caption(t("boundary.contact.unverified", lang))

    if not drafts:
        return True

    workspace = CompanyWorkspace.for_company(
        root=default_workspace_root(repo_root),
        taiwan_ubn=company.unified_business_number,
        entity_id=drafts[0].legal_entities[0].entity_id,
    )
    if legacy is not None:
        workspace.write_draft(legacy)

    assessment_year = int(getattr(assessment, "reporting_year", 0) or 0)
    records_by_id = {
        boundary.boundary_id: workspace.list_current_for_boundary(
            boundary_id=boundary.boundary_id
        )
        for boundary in drafts
    }
    period_candidates: dict[str, InventoryBoundary] = {}
    prior_records: list[tuple[InventoryBoundary, InventoryBoundary]] = []
    for boundary in drafts:
        for stored in records_by_id[boundary.boundary_id]:
            period = stored.reporting_period
            if period.reporting_year_confirmed == assessment_year:
                period_candidates.setdefault(period.reporting_period_id, stored)
            else:
                prior_records.append((boundary, stored))

    active_period_key = (
        f"boundary_active_period_{workspace.workspace_id}_{assessment_year}"
    )
    active_period_id = str(st.session_state.get(active_period_key) or "")
    candidate_ids = sorted(period_candidates)
    if active_period_id not in period_candidates:
        st.session_state.pop(active_period_key, None)
        active_period_id = ""
    if len(candidate_ids) == 1 and not active_period_id:
        active_period_id = candidate_ids[0]
        st.session_state[active_period_key] = active_period_id
    elif len(candidate_ids) > 1:
        selector_key = f"{active_period_key}_selector"
        selector_options = ["", *candidate_ids]
        if st.session_state.get(selector_key) not in selector_options:
            st.session_state[selector_key] = active_period_id
        chosen_period_id = st.selectbox(
            t("boundary.period.choose_active", lang),
            options=selector_options,
            format_func=lambda period_id: (
                t("boundary.period.choose_placeholder", lang)
                if not period_id
                else _reporting_period_label(period_candidates[period_id])
            ),
            key=selector_key,
        )
        if chosen_period_id:
            active_period_id = chosen_period_id
            st.session_state[active_period_key] = chosen_period_id
        else:
            active_period_id = ""
            st.session_state.pop(active_period_key, None)

    if active_period_id:
        st.caption(
            t(
                "boundary.period.active",
                lang,
                period=_reporting_period_label(
                    period_candidates[active_period_id]
                ),
            )
        )

    if prior_records:
        with st.expander(t("boundary.prior.heading", lang), expanded=True):
            for draft, stored in prior_records:
                st.markdown(f"**{_boundary_choice_label(draft)}**")
                period = stored.reporting_period
                st.caption(
                    t(
                        "boundary.prior.item",
                        lang,
                        year=period.reporting_year_confirmed,
                        start=period.period_start_confirmed,
                        end=period.period_end_confirmed,
                        current_year=assessment_year,
                    )
                )

    active_records_by_id: dict[str, InventoryBoundary] = {}
    if active_period_id:
        for boundary in drafts:
            stored = workspace.load_current(
                reporting_period_id=active_period_id,
                boundary_id=boundary.boundary_id,
            )
            if stored is not None:
                active_records_by_id[boundary.boundary_id] = stored
    current_by_id = {
        boundary_id: stored
        for boundary_id, stored in active_records_by_id.items()
        if confirmer_details_are_complete(stored)
    }

    confirmed_count = len(current_by_id)
    st.markdown(
        "### "
        + t(
            "boundary.progress",
            lang,
            confirmed=confirmed_count,
            total=len(drafts),
        )
    )
    unconfirmed = [
        item for item in drafts if item.boundary_id not in current_by_id
    ]
    next_boundary = unconfirmed[0] if unconfirmed else None
    if next_boundary is not None:
        st.info(
            t(
                "boundary.next_task",
                lang,
                boundary=_boundary_choice_label(next_boundary),
            )
        )
    else:
        unresolved_boundaries = sum(
            boundary.requirement_status == REQUIREMENT_NEEDS_FACT
            for boundary in drafts
        )
        summary_key = (
            "boundary.completed_summary.unresolved"
            if unresolved_boundaries
            else "boundary.completed_summary.resolved"
        )
        st.success(
            t(
                summary_key,
                lang,
                total=len(drafts),
                unresolved=unresolved_boundaries,
            )
        )
        for boundary in drafts:
            st.caption(
                t(
                    "boundary.completed_item",
                    lang,
                    boundary=_boundary_choice_label(boundary),
                )
            )

    registration_count = sum(len(item.registration_links) for item in drafts)
    if registration_count:
        st.info(t("boundary.registration_separate", lang))

    with st.expander(t("boundary.overview", lang), expanded=False):
        for boundary in drafts:
            st.markdown(f"**{_boundary_choice_label(boundary)}**")
            st.caption(
                _boundary_confirmation_status(
                    locally_confirmed=boundary.boundary_id in current_by_id
                )
            )
            st.caption(_boundary_legal_status(boundary))
            missing_fact = _boundary_missing_fact_text(boundary)
            resolution = _boundary_resolution_text(boundary)
            if missing_fact:
                st.caption(missing_fact)
            if resolution:
                st.caption(
                    t("boundary.provide_fact", lang, resolution=resolution)
                )
            if boundary.requirement_effective_year is not None:
                st.caption(
                    t(
                        "boundary.evidence.effective_year",
                        lang,
                        year=boundary.requirement_effective_year,
                    )
                )
            if boundary.legal_document:
                st.caption(
                    t(
                        "boundary.evidence.document",
                        lang,
                        document=boundary.legal_document,
                    )
                )
            for link in boundary.registration_links:
                st.caption(
                    t(
                        "boundary.registration",
                        lang,
                        registration=link.registration_identity,
                    )
                )
                if link.location:
                    st.caption(link.location)

    default_boundary_id = (
        next_boundary.boundary_id
        if next_boundary is not None
        else drafts[0].boundary_id
    )
    pending_selected_id = st.session_state.pop(
        "boundary_next_selected_id", None
    )
    valid_boundary_ids = [item.boundary_id for item in drafts]
    if pending_selected_id in valid_boundary_ids:
        st.session_state["boundary_selected_id"] = pending_selected_id
    elif st.session_state.get("boundary_selected_id") not in valid_boundary_ids:
        st.session_state["boundary_selected_id"] = default_boundary_id
    selected_id = st.radio(
        t("boundary.select", lang),
        options=valid_boundary_ids,
        format_func=lambda boundary_id: _boundary_choice_label(
            next(item for item in drafts if item.boundary_id == boundary_id)
        ),
        index=[item.boundary_id for item in drafts].index(default_boundary_id),
        key="boundary_selected_id",
    )
    selected = next(item for item in drafts if item.boundary_id == selected_id)
    stored_current = active_records_by_id.get(selected.boundary_id)
    current = current_by_id.get(selected.boundary_id)
    form_value = stored_current or selected
    period_context = active_period_id or f"assessment_{assessment_year}"
    key_prefix = f"boundary_{selected.boundary_id}_{period_context}"

    if current is not None:
        st.success(t("boundary.confirmed", lang))
        st.caption(t("boundary.contact.unverified", lang))
    elif stored_current is not None:
        st.warning(t("boundary.contact.reconfirm_legacy", lang))

    st.caption(
        _boundary_confirmation_status(locally_confirmed=current is not None)
    )
    st.caption(_boundary_legal_status(selected))
    missing_fact = _boundary_missing_fact_text(selected)
    resolution = _boundary_resolution_text(selected)
    if missing_fact:
        st.warning(missing_fact)
    if resolution:
        st.caption(t("boundary.provide_fact", lang, resolution=resolution))
    evidence_bits: list[str] = []
    if selected.requirement_effective_year is not None:
        evidence_bits.append(
            t(
                "boundary.evidence.effective_year",
                lang,
                year=selected.requirement_effective_year,
            )
        )
    if selected.legal_authority:
        evidence_bits.append(
            t(
                "boundary.evidence.authority",
                lang,
                authority=selected.legal_authority,
            )
        )
    if selected.legal_document:
        evidence_bits.append(
            t(
                "boundary.evidence.document",
                lang,
                document=selected.legal_document,
            )
        )
    if evidence_bits:
        st.caption(" · ".join(evidence_bits))

    combination_enabled = False
    combination_targets: list[str] = []
    combination_basis = ""
    combination_evidence = ""
    registration_candidates: dict[str, RegistrationLink] = {}
    for draft in drafts:
        stored = active_records_by_id.get(draft.boundary_id) or draft
        for registration_link in stored.registration_links:
            registration_candidates[registration_link.registration_link_id] = (
                registration_link
            )
    if (
        selected.purpose == PURPOSE_MOENV_FACILITY
        and form_value.registration_links
    ):
        primary_link = form_value.registration_links[0]
        target_ids = [
            registration_link_id
            for registration_link_id in registration_candidates
            if registration_link_id != primary_link.registration_link_id
        ]
        with st.expander(t("boundary.combination.heading", lang), expanded=False):
            st.write(t("boundary.combination.help", lang))
            st.caption(t("boundary.combination.unverified", lang))
            combination_enabled = st.checkbox(
                t("boundary.combination.enable", lang),
                value=bool(primary_link.combined_with),
                key=f"{key_prefix}_combination_enabled",
            )
            if combination_enabled:
                st.caption(t("boundary.combination.targets", lang))
                combination_targets = [
                    target
                    for target in target_ids
                    if st.checkbox(
                        registration_candidates[target].registration_identity,
                        value=target in primary_link.combined_with,
                        key=f"{key_prefix}_combination_target_{target}",
                    )
                ]
                combination_basis = st.text_area(
                    t("boundary.combination.basis", lang),
                    value=primary_link.combination_basis,
                    key=f"{key_prefix}_combination_basis",
                )
                combination_evidence = st.text_input(
                    t("boundary.combination.evidence", lang),
                    value=primary_link.combination_evidence,
                    key=f"{key_prefix}_combination_evidence",
                )

    st.markdown(f"### {t('boundary.period.heading', lang)}")
    suggested_year = (
        form_value.reporting_period.reporting_year_confirmed
        or form_value.reporting_period.reporting_year_suggested
    )
    if suggested_year is not None:
        st.caption(
            t("boundary.period.suggestion", lang, year=int(suggested_year))
        )
    else:
        st.caption(t("boundary.period.no_suggestion", lang))
    reporting_year = int(
        st.number_input(
            t("boundary.period.year", lang),
            min_value=2020,
            max_value=2100,
            value=int(suggested_year or date.today().year),
            step=1,
            key=f"{key_prefix}_year",
        )
    )
    start_default = date(reporting_year, 1, 1)
    end_default = date(reporting_year, 12, 31)
    period_cols = st.columns(2)
    with period_cols[0]:
        period_start = st.date_input(
            t("boundary.period.start", lang),
            value=_date_or_default(
                form_value.reporting_period.period_start_confirmed,
                start_default,
            ),
            key=f"{key_prefix}_start",
        )
    with period_cols[1]:
        period_end = st.date_input(
            t("boundary.period.end", lang),
            value=_date_or_default(
                form_value.reporting_period.period_end_confirmed,
                end_default,
            ),
            key=f"{key_prefix}_end",
        )
    period_explicit = st.checkbox(
        t("boundary.period.confirm", lang),
        value=bool(current and current.reporting_period.is_explicitly_confirmed),
        key=f"{key_prefix}_period_explicit",
    )

    membership_options = [
        MEMBERSHIP_PENDING,
        MEMBERSHIP_INCLUDED,
        MEMBERSHIP_EXCLUDED,
        MEMBERSHIP_NOT_PERIOD,
    ]
    entity_membership_by_id = {
        item.entity_id: item for item in form_value.entity_memberships
    }
    facility_membership_by_id = {
        item.facility_id: item for item in form_value.facility_memberships
    }

    st.markdown(f"### {t('boundary.entities.heading', lang)}")
    st.caption(t("boundary.entities.help", lang))
    entity_values: list[LegalEntity] = list(form_value.legal_entities)
    entity_inputs: list[tuple[LegalEntity, str, str, str]] = []
    for entity in entity_values:
        existing_membership = entity_membership_by_id.get(entity.entity_id)
        state = st.selectbox(
            entity.legal_name,
            options=membership_options,
            index=membership_options.index(
                existing_membership.state
                if existing_membership
                else MEMBERSHIP_PENDING
            ),
            format_func=lambda code: t(f"boundary.membership.{code}", lang),
            key=f"{key_prefix}_entity_{entity.entity_id}",
        )
        detail_cols = st.columns(2)
        with detail_cols[0]:
            reason = st.text_input(
                t("boundary.membership.reason", lang),
                value=existing_membership.reason if existing_membership else "",
                key=f"{key_prefix}_entity_reason_{entity.entity_id}",
            )
        with detail_cols[1]:
            evidence = st.text_input(
                t("boundary.membership.evidence", lang),
                value=(
                    existing_membership.evidence_source
                    if existing_membership
                    else ""
                ),
                key=f"{key_prefix}_entity_evidence_{entity.entity_id}",
            )
        entity_inputs.append((entity, str(state), reason, evidence))

    subsidiary_inputs: list[tuple[LegalEntity, str, str, str]] = []
    subsidiary_identities_complete = True
    if selected.purpose == PURPOSE_LISTED_CONSOLIDATED:
        subsidiary_count = int(
            st.number_input(
                t("boundary.entity.add_count", lang),
                min_value=0,
                max_value=20,
                value=max(0, len(form_value.legal_entities) - 1),
                step=1,
                key=f"{key_prefix}_subsidiary_count",
            )
        )
        parent_id = form_value.legal_entities[0].entity_id
        existing_subsidiaries = list(form_value.legal_entities[1:])
        for index in range(subsidiary_count):
            existing = (
                existing_subsidiaries[index]
                if index < len(existing_subsidiaries)
                else None
            )
            suffix = index + 1
            name = st.text_input(
                t("boundary.entity.name", lang),
                value=existing.legal_name if existing else "",
                key=f"{key_prefix}_sub_name_{suffix}",
            )
            identity_cols = st.columns(3)
            with identity_cols[0]:
                jurisdiction = st.text_input(
                    t("boundary.entity.jurisdiction", lang),
                    value=existing.jurisdiction if existing else "",
                    key=f"{key_prefix}_sub_jurisdiction_{suffix}",
                )
            with identity_cols[1]:
                registration_id = st.text_input(
                    t("boundary.entity.registration", lang),
                    value=existing.registration_id if existing else "",
                    key=f"{key_prefix}_sub_registration_{suffix}",
                )
            with identity_cols[2]:
                taiwan_ubn = st.text_input(
                    t("boundary.entity.ubn", lang),
                    value=existing.taiwan_ubn if existing else "",
                    key=f"{key_prefix}_sub_ubn_{suffix}",
                )
            entity_id = (
                existing.entity_id
                if existing
                else f"{parent_id}_subsidiary_{suffix}"
            )
            if not name.strip() or not jurisdiction.strip():
                subsidiary_identities_complete = False
            subsidiary = LegalEntity(
                entity_id=entity_id,
                legal_name=name or f"Subsidiary {suffix}",
                jurisdiction=jurisdiction or "UNCONFIRMED",
                registration_id=registration_id,
                taiwan_ubn=taiwan_ubn,
                parent_entity_id=parent_id,
                source="customer_entered",
            )
            state = st.selectbox(
                name or t("boundary.entity.name", lang),
                options=membership_options,
                index=membership_options.index(
                    entity_membership_by_id.get(
                        entity_id,
                        LegalEntityMembership(entity_id=entity_id),
                    ).state
                ),
                format_func=lambda code: t(f"boundary.membership.{code}", lang),
                key=f"{key_prefix}_sub_state_{suffix}",
            )
            reason = st.text_input(
                t("boundary.membership.reason", lang),
                key=f"{key_prefix}_sub_reason_{suffix}",
            )
            evidence = st.text_input(
                t("boundary.membership.evidence", lang),
                key=f"{key_prefix}_sub_evidence_{suffix}",
            )
            subsidiary_inputs.append(
                (subsidiary, str(state), reason, evidence)
            )

    st.markdown(f"### {t('boundary.facilities.heading', lang)}")
    st.caption(t("boundary.facilities.help", lang))
    facility_by_id = {item.facility_id: item for item in facilities.records}
    facility_inputs: list[tuple[str, str, str, str]] = []
    for membership in form_value.facility_memberships:
        facility = facility_by_id.get(membership.facility_id)
        existing_membership = facility_membership_by_id.get(
            membership.facility_id
        )
        label = facility.display_name if facility else membership.facility_id
        state = st.selectbox(
            label,
            options=membership_options,
            index=membership_options.index(
                existing_membership.state
                if existing_membership
                else MEMBERSHIP_PENDING
            ),
            format_func=lambda code: t(f"boundary.membership.{code}", lang),
            key=f"{key_prefix}_facility_{membership.facility_id}",
        )
        detail_cols = st.columns(2)
        with detail_cols[0]:
            reason = st.text_input(
                t("boundary.membership.reason", lang),
                value=existing_membership.reason if existing_membership else "",
                key=f"{key_prefix}_facility_reason_{membership.facility_id}",
            )
        with detail_cols[1]:
            evidence = st.text_input(
                t("boundary.membership.evidence", lang),
                value=(
                    existing_membership.evidence_source
                    if existing_membership
                    else ""
                ),
                key=f"{key_prefix}_facility_evidence_{membership.facility_id}",
            )
        facility_inputs.append(
            (membership.facility_id, str(state), reason, evidence)
        )

    st.markdown(f"### {t('boundary.categories.heading', lang)}")
    st.caption(t("boundary.categories.help", lang))
    categories_by_id = {
        item.category: item for item in form_value.expected_categories
    }
    category_inputs: list[ExpectedSourceCategory] = []
    category_columns = st.columns(2)
    for index, category in enumerate(form_value.expected_categories):
        with category_columns[index % 2]:
            state = st.selectbox(
                t(f"boundary.category.{category.category}", lang),
                options=[CATEGORY_PENDING, "expected", "not_expected"],
                index=[CATEGORY_PENDING, "expected", "not_expected"].index(
                    categories_by_id.get(
                        category.category,
                        ExpectedSourceCategory(category=category.category),
                    ).state
                ),
                format_func=lambda code: t(f"boundary.category.{code}", lang),
                key=f"{key_prefix}_category_{category.category}",
            )
            reason = ""
            if state == CATEGORY_NOT_EXPECTED:
                reason = st.text_input(
                    t("boundary.category.not_expected_reason", lang),
                    value=categories_by_id.get(
                        category.category,
                        ExpectedSourceCategory(category=category.category),
                    ).reason,
                    key=f"{key_prefix}_category_reason_{category.category}",
                )
            category_inputs.append(
                ExpectedSourceCategory(
                    category=category.category,
                    state=str(state),
                    reason=str(reason or ""),
                )
            )

    st.markdown(f"### {t('boundary.contact.heading', lang)}")
    contact_cols = st.columns(2)
    with contact_cols[0]:
        contact_name = st.text_input(
            t("boundary.contact.name", lang),
            value=form_value.responsible_contact_name,
            key=f"{key_prefix}_contact_name",
        )
    with contact_cols[1]:
        contact_title = st.text_input(
            t("boundary.contact.title", lang),
            value=form_value.responsible_job_title,
            key=f"{key_prefix}_contact_title",
        )
    st.caption(t("boundary.contact.unverified", lang))

    if st.button(
        t("boundary.confirm", lang),
        type="primary",
        key=f"{key_prefix}_confirm",
    ):
        stamp = utc_now_iso()
        try:
            if not period_explicit or not subsidiary_identities_complete:
                raise ValueError("reporting period not explicitly confirmed")
            normalized_name, normalized_title = normalize_confirmer_details(
                contact_name,
                contact_title,
            )
            period = ReportingPeriod.confirmed(
                reporting_year_suggested=(
                    selected.reporting_period.reporting_year_suggested
                ),
                reporting_year_confirmed=reporting_year,
                period_start_confirmed=period_start.isoformat(),
                period_end_confirmed=period_end.isoformat(),
            )
            registration_links = form_value.registration_links
            if (
                selected.purpose == PURPOSE_MOENV_FACILITY
                and registration_links
            ):
                primary_link = registration_links[0]
                if combination_enabled and not combination_targets:
                    raise ValueError(
                        "registration combination requires at least one target"
                    )
                combination_changed = (
                    tuple(combination_targets) != primary_link.combined_with
                    or str(combination_basis or "").strip()
                    != primary_link.combination_basis
                    or str(combination_evidence or "").strip()
                    != primary_link.combination_evidence
                )
                history = primary_link.confirmation_history
                if combination_changed:
                    history = (
                        *history,
                        {
                            "at": stamp,
                            "targets": ",".join(combination_targets),
                            "basis": str(combination_basis or "").strip(),
                            "evidence": str(combination_evidence or "").strip(),
                            "confirmation_method": "local_workspace_unverified",
                        },
                    )
                updated_link = replace(
                    primary_link,
                    combined_with=tuple(combination_targets),
                    combination_basis=(
                        str(combination_basis or "").strip()
                        if combination_enabled
                        else ""
                    ),
                    combination_evidence=(
                        str(combination_evidence or "").strip()
                        if combination_enabled
                        else ""
                    ),
                    confirmation_history=history,
                )
                all_registration_links = {
                    **registration_candidates,
                    updated_link.registration_link_id: updated_link,
                }
                validate_registration_combinations(
                    all_registration_links.values()
                )
                registration_links = (updated_link,)
            all_entity_inputs = [*entity_inputs, *subsidiary_inputs]
            confirmed_entities = tuple(
                replace(
                    entity,
                    confirmation_state=CONFIRMATION_LOCAL,
                    locally_confirmed_at=stamp,
                    responsible_contact_name=normalized_name,
                    responsible_job_title=normalized_title,
                )
                for entity, _, _, _ in all_entity_inputs
            )
            entity_memberships = tuple(
                LegalEntityMembership(
                    entity_id=entity.entity_id,
                    state=state,
                    effective_start=period_start.isoformat(),
                    effective_end=period_end.isoformat(),
                    reason=str(reason or ""),
                    evidence_source=str(evidence or ""),
                    locally_confirmed_at=stamp,
                    responsible_contact_name=normalized_name,
                    responsible_job_title=normalized_title,
                    reporting_purpose=selected.purpose,
                )
                for entity, state, reason, evidence in all_entity_inputs
            )
            facility_memberships = tuple(
                FacilityMembership(
                    facility_id=facility_id,
                    state=state,
                    effective_start=period_start.isoformat(),
                    effective_end=period_end.isoformat(),
                    reason=str(reason or ""),
                    evidence_source=str(evidence or ""),
                    locally_confirmed_at=stamp,
                    responsible_contact_name=normalized_name,
                    responsible_job_title=normalized_title,
                    reporting_purpose=selected.purpose,
                )
                for facility_id, state, reason, evidence in facility_inputs
            )
            candidate = replace(
                selected,
                display_name=_boundary_choice_label(selected),
                reporting_period=period,
                legal_entities=confirmed_entities,
                entity_memberships=entity_memberships,
                facility_memberships=facility_memberships,
                registration_links=registration_links,
                expected_categories=tuple(category_inputs),
                organizational_approach=form_value.organizational_approach,
                responsible_contact_name=normalized_name,
                responsible_job_title=normalized_title,
            ).locally_confirmed(at=stamp)
            workspace.append_locally_confirmed(candidate)
        except ConfirmerDetailsError as error:
            for field in error.missing_fields:
                st.error(t(f"boundary.error.{field}", lang))
            st.caption(t("boundary.confirmation.not_saved", lang))
        except ValueError as error:
            st.error(_boundary_error_message(error))
        else:
            if period.reporting_year_confirmed == assessment_year:
                st.session_state[active_period_key] = (
                    period.reporting_period_id
                )
            st.success(t("boundary.confirmed", lang))
            remaining_ids = [
                item.boundary_id
                for item in drafts
                if item.boundary_id != selected.boundary_id
                and item.boundary_id not in current_by_id
            ]
            if remaining_ids:
                st.session_state["boundary_next_selected_id"] = remaining_ids[0]
            st.rerun()

    return all(item.boundary_id in current_by_id for item in drafts)


def _wizard_nav(
    draft: dict,
    *,
    finish_label: str | None = None,
    finish_disabled: bool = False,
) -> None:
    if step < STATE_WIZARD_MAX_STEP:
        nav1, nav2, nav3 = st.columns([1, 1, 1.2])
        with nav1:
            if step > 1 and st.button(
                t("apl.wizard.back", lang), key="apl_back", use_container_width=True
            ):
                _persist_partial(draft)
                st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = step - 1
                st.rerun()
        with nav2:
            if st.button(
                t("apl.wizard.save", lang), key="apl_save", use_container_width=True
            ):
                _persist_partial(draft)
                st.success(t("apl.saved_ok", lang))
        with nav3:
            if st.button(
                t("apl.wizard.continue", lang),
                key="apl_continue",
                type="primary",
                use_container_width=True,
            ):
                exception_open = bool(
                    st.session_state.get(STATE_FACILITY_EXCEPTION_MODE)
                )
                pending_exception = (
                    step == 3
                    and exception_navigation_blocked(
                        exception_mode=exception_open,
                        identity_confirmed=_load_facilities().identity_confirmed,
                        drafts_dirty=exception_drafts_are_dirty(
                            st.session_state
                        ),
                    )
                )
                if pending_exception:
                    st.session_state["_cel_facility_exception_need_confirm"] = True
                    st.rerun()
                _persist_partial(draft)
                st.session_state["_cel_facility_exception_need_confirm"] = False
                st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = step + 1
                st.rerun()
        return
    b1, b2 = st.columns(2)
    with b1:
        if st.button(
            t("apl.wizard.back", lang),
            key="apl_back_results",
            use_container_width=True,
        ):
            st.session_state[STATE_COMPANY_PROFILE_EDITING] = True
            st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = 3
            st.rerun()
    with b2:
        label = finish_label or t("apl.wizard.view_current", lang)
        if st.button(
            label,
            key="apl_finish",
            type="primary",
            use_container_width=True,
            disabled=finish_disabled,
        ):
            st.session_state[STATE_COMPANY_PROFILE_EDITING] = False
            st.rerun()


def _render_company_card(company: CompanyMaster) -> None:
    st.markdown(f"**{t('setup.found', lang)}**")
    st.markdown(f"### {company.company_name}")
    listing_key = listing_customer_label_key(company.listing_status)
    as_of = (company.snapshot_data_date or "")[:10]
    address = company.registered_address
    if address:
        st.markdown(f"**{t('setup.address', lang)}**  \n{address}")
    capital = company.official_paid_in_capital_twd
    if capital is not None:
        st.markdown(f"**{t('setup.capital', lang)}**")
        ubn = company.unified_business_number
        gen = int(st.session_state.get(STATE_CAPITAL_LOOKUP_GEN) or 0)
        play_ubn = str(st.session_state.get(STATE_CAPITAL_PLAY_UBN) or "")
        play = bool(
            play_ubn == ubn
            and gen > 0
            and company.lookup_status != "manual"
            and not company.capital_overridden
        )
        if play:
            schedule_capital_countup(st.session_state, play=True)
        runtime_ready = bool(st.session_state.get(STATE_CAPITAL_RUNTIME_READY))
        if play and runtime_ready:
            inject_animated_kpi_runtime()
        render_capital_countup(
            int(capital),
            play=play,
            run=f"{ubn}-{gen}",
            metric_key=f"paid-in-capital-{ubn}",
        )
    if listing_key:
        st.markdown(f"**{t('setup.listing', lang)}**  \n{t(listing_key, lang)}")
    st.markdown(
        f"**{t('setup.source', lang)}**  \n{t('setup.source.open_data', lang)}"
    )
    if as_of:
        st.markdown(f"**{t('setup.data_as_of', lang)}**  \n{as_of}")


def _render_step_company(draft: dict, company: CompanyMaster) -> CompanyMaster:
    with onboarding_target("company-ubn-lookup"):
        st.caption(t("setup.ubn.help", lang))
        ubn_value = st.text_input(
            t("setup.ubn.label", lang),
            value=str(
                company.unified_business_number
                or saved.get("unified_business_number")
                or ""
            ),
            key="apl_ubn",
        )
        draft["unified_business_number"] = ubn_value
        actions = st.columns(2)
        with actions[0]:
            lookup_clicked = st.button(
                t("setup.lookup", lang), key="apl_lookup", type="primary"
            )
        with actions[1]:
            if st.button(t("setup.manual", lang), key="apl_manual"):
                st.session_state[STATE_COMPANY_LOOKUP_MANUAL] = True
    if lookup_clicked:
        result = lookup_company(
            ubn_value, repo_root=repo_root, previous=company
        )
        update = session_update_from_lookup(result)
        company = update["company"]
        _store_company(company)
        official = update["factories"]
        st.session_state["_cel_official_factories"] = [
            hint.__dict__ for hint in official
        ]
        facilities = rebuild_facility_master(
            session_state=st.session_state,
            company=company,
            official=official,
            existing=_load_facilities(),
            reporting_year=int(draft.get("reporting_year") or 2026),
        )
        _store_facilities(facilities)
        st.session_state[STATE_COMPANY_LOOKUP_NOT_FOUND] = bool(
            update["not_found"]
        )
        st.session_state[STATE_COMPANY_LOOKUP_MANUAL] = bool(update["manual"])
        if (
            update["company_found"]
            and company.official_paid_in_capital_twd is not None
            and company.lookup_status != "manual"
        ):
            st.session_state[STATE_CAPITAL_LOOKUP_GEN] = (
                int(st.session_state.get(STATE_CAPITAL_LOOKUP_GEN) or 0) + 1
            )
            st.session_state[STATE_CAPITAL_PLAY_UBN] = company.unified_business_number
            st.session_state[STATE_CAPITAL_RUNTIME_READY] = False
            st.session_state["_cel_capital_visible_at"] = 0.0
        st.session_state["_cel_factory_as_of"] = factory_source_as_of(repo_root)
        st.session_state[STATE_FACILITY_EXCEPTION_MODE] = False
        clear_exception_drafts_dirty(st.session_state)
        st.rerun()

    not_found = bool(st.session_state.get(STATE_COMPANY_LOOKUP_NOT_FOUND))
    if not_found and not company.company_name:
        st.warning(t("setup.not_found", lang))
        st.caption(t("setup.not_found.hint", lang))

    if company.company_name and company.lookup_status != "manual":
        _render_company_card(company)
        c1, c2 = st.columns(2)
        with c1:
            with onboarding_target("company-confirmation"):
                if st.button(
                    t("setup.confirm_company", lang), key="apl_confirm_co"
                ):
                    company.customer_confirmed_at = utc_now_iso()
                    inferred = infer_entity_from_listing(company.listing_status)
                    if inferred:
                        draft["entity_type"] = inferred
                        draft["listing_status"] = company.listing_status
                    _store_company(company)
                    st.success(t("setup.confirm_company_ok", lang))
                    if onboarding_running(st.session_state):
                        st.rerun()
        with c2:
            if st.button(t("setup.data_wrong", lang), key="apl_wrong_co"):
                st.session_state[STATE_COMPANY_LOOKUP_MANUAL] = True
                st.rerun()

    manual = bool(st.session_state.get(STATE_COMPANY_LOOKUP_MANUAL)) or not_found
    if manual or company.lookup_status == "manual":
        st.caption(t("setup.data_wrong.help", lang))
        draft["company_name"] = st.text_input(
            t("apl.field.company_name", lang),
            value=str(company.company_name or saved.get("company_name") or ""),
            key="apl_company_name",
        )
        address_value = st.text_input(
            t("setup.address", lang),
            value=str(
                company.confirmed_registered_address
                or company.official_registered_address
                or ""
            ),
            key="apl_company_address",
        )
        if draft["company_name"] and (
            manual or company.lookup_status in {"", "failed", "manual", "empty"}
        ):
            company = merge_manual_company(
                ubn=str(ubn_value or ""),
                name=str(draft["company_name"]),
                previous=company,
                address=str(address_value or ""),
            )
            _store_company(company)
    elif company.company_name:
        draft["company_name"] = company.company_name

    with onboarding_target("company-basic-information"):
        draft["reporting_year"] = int(
            st.number_input(
                t("apl.field.reporting_year", lang),
                min_value=2024,
                max_value=2035,
                value=int(saved.get("reporting_year") or 2026),
                step=1,
                key="apl_reporting_year",
                help=t("apl.field.reporting_year_help", lang),
            )
        )
        st.caption(t("apl.field.reporting_year_professional", lang))
        if entity_needs_customer({**saved, **draft}) and not infer_entity_from_listing(
            company.listing_status
        ):
            draft["entity_type"] = st.selectbox(
                t("apl.field.entity_type", lang),
                options=ENTITY_OPTIONS,
                index=ENTITY_OPTIONS.index(
                    str(saved.get("entity_type") or "unresolved")
                ),
                format_func=_label_entity,
                key="apl_entity_type",
                help=t("learn.why.entity_type", lang),
            )
            render_micro_help(lang, field_key="entity_type")
        else:
            draft["entity_type"] = (
                infer_entity_from_listing(company.listing_status)
                or saved.get("entity_type")
                or "unresolved"
            )
        draft["jurisdiction"] = "TW"
        draft["sasb_industry"] = saved.get("sasb_industry") or ""
        draft["listing_status"] = company.listing_status or saved.get(
            "listing_status"
        ) or "UNKNOWN"
        if company.paid_in_capital_twd is not None:
            draft["paid_in_capital_twd"] = company.paid_in_capital_twd
        _wizard_nav(draft)
    return company


def _render_step_missing(draft: dict, company: CompanyMaster) -> None:
    if listing_needs_customer(company):
        listing_status = str(saved.get("listing_status") or "UNKNOWN")
        draft["listing_status"] = st.selectbox(
            t("apl.field.listing_status", lang),
            options=LISTING_OPTIONS,
            index=LISTING_OPTIONS.index(listing_status)
            if listing_status in LISTING_OPTIONS
            else 0,
            format_func=_label_listing,
            key="apl_listing_status",
        )
        company.listing_status = str(draft["listing_status"])
        inferred = infer_entity_from_listing(company.listing_status)
        if inferred and entity_needs_customer({**saved, **draft}):
            draft["entity_type"] = inferred
    else:
        draft["listing_status"] = company.listing_status
        st.markdown(
            f"**{t('apl.field.listing_status', lang)}**  \n"
            f"{_label_listing(company.listing_status)}"
        )
        st.caption(t("setup.listing_source", lang))

    entity_type = str(
        draft.get("entity_type")
        or saved.get("entity_type")
        or infer_entity_from_listing(company.listing_status)
        or "unresolved"
    )

    if show_capital_for_entity(entity_type):
        official = company.official_paid_in_capital_twd
        if official is not None and not company.capital_overridden:
            st.markdown(f"**{t('setup.capital', lang)}**")
            st.markdown(format_twd_display(official, lang=lang))
            st.caption(t("setup.capital_source", lang))
            if st.checkbox(t("setup.capital_edit", lang), key="apl_capital_edit"):
                edited = render_money_field(
                    t("apl.field.paid_in_capital_twd", lang),
                    lang=lang,
                    field_key="paid_in_capital_twd",
                    saved_twd=official,
                    unknown_toggle_key="apl_capital_unknown",
                    amount_key="apl_capital_amount",
                    unit_key="apl_capital_unit",
                    hint_key="paid_in_capital_twd",
                )
                apply_customer_capital_override(company, edited)
                draft["paid_in_capital_twd"] = company.paid_in_capital_twd
            else:
                draft["paid_in_capital_twd"] = official
        else:
            draft["paid_in_capital_twd"] = render_money_field(
                t("apl.field.paid_in_capital_twd", lang),
                lang=lang,
                field_key="paid_in_capital_twd",
                saved_twd=(
                    int(saved["paid_in_capital_twd"])
                    if saved.get("paid_in_capital_twd") not in (None, "", 0, "0")
                    else company.paid_in_capital_twd
                ),
                unknown_toggle_key="apl_capital_unknown",
                amount_key="apl_capital_amount",
                unit_key="apl_capital_unit",
                hint_key="paid_in_capital_twd",
            )
        if show_net_worth(
            entity_type=entity_type,
            share_par=str(saved.get("share_par") or ""),
        ):
            st.caption(t("setup.net_worth_help", lang))
            draft["net_worth_twd"] = render_money_field(
                t("apl.field.net_worth_twd", lang),
                lang=lang,
                field_key="net_worth_twd",
                saved_twd=(
                    int(saved["net_worth_twd"])
                    if saved.get("net_worth_twd") not in (None, "", 0, "0")
                    else None
                ),
                unknown_toggle_key="apl_net_unknown",
                amount_key="apl_net_amount",
                unit_key="apl_net_unit",
                hint_key="net_worth_twd",
            )
        else:
            draft["net_worth_twd"] = saved.get("net_worth_twd")
    else:
        draft["paid_in_capital_twd"] = saved.get("paid_in_capital_twd")
        draft["net_worth_twd"] = saved.get("net_worth_twd")

    if show_fhc_for_entity(entity_type):
        is_fhc = str(saved.get("is_fhc_subsidiary") or "UNKNOWN")
        draft["is_fhc_subsidiary"] = st.selectbox(
            t("apl.field.is_fhc_subsidiary", lang),
            options=BOOL_TRI,
            index=BOOL_TRI.index(is_fhc) if is_fhc in BOOL_TRI else 0,
            format_func=_label_choice,
            key="apl_is_fhc_subsidiary",
        )
    else:
        draft["is_fhc_subsidiary"] = saved.get("is_fhc_subsidiary") or "UNKNOWN"

    group = str(saved.get("company_group_choice") or GROUP_UNKNOWN)
    group_options = [GROUP_SELF_ONLY, GROUP_WITH_SUBS, GROUP_UNKNOWN]
    draft["company_group_choice"] = st.selectbox(
        t("setup.group.label", lang),
        options=group_options,
        index=group_options.index(group) if group in group_options else 2,
        format_func=lambda code: t(f"setup.group.{code}", lang),
        key="apl_company_group",
        help=t("setup.group.help", lang),
    )
    draft["reporting_entities_known"] = apply_group_choice(
        str(draft["company_group_choice"])
    )
    draft["uses_consolidated_financial_statements"] = (
        "TRUE" if draft["company_group_choice"] == GROUP_WITH_SUBS else "UNKNOWN"
    )

    notice = str(
        saved.get("received_environmental_authority_inventory_notice")
        or saved.get("received_verification_requirement")
        or "NOT_SURE"
    )
    if notice not in TRI:
        notice = "NOT_SURE"
    chosen = st.selectbox(
        t("apl.field.received_authority_notice", lang),
        options=TRI,
        index=TRI.index(notice),
        format_func=_label_choice,
        key="apl_authority_notice",
    )
    draft["received_environmental_authority_inventory_notice"] = chosen
    draft["received_verification_requirement"] = chosen
    _store_company(company)


def _official_hints() -> list[OfficialFactoryHint]:
    raw = st.session_state.get("_cel_official_factories") or []
    hints: list[OfficialFactoryHint] = []
    for item in raw:
        if isinstance(item, dict) and item.get("display_name"):
            hints.append(
                OfficialFactoryHint(
                    display_name=str(item.get("display_name") or ""),
                    address=str(item.get("address") or ""),
                    registration_number=str(item.get("registration_number") or ""),
                    industry_code=str(item.get("industry_code") or ""),
                    main_products=str(item.get("main_products") or ""),
                    unified_business_number=str(
                        item.get("unified_business_number") or ""
                    ),
                )
            )
    return hints


def _on_exception_draft_change() -> None:
    mark_exception_drafts_dirty(st.session_state)


def _exception_drafts_from_session(
    records: list[FacilityMasterRecord],
) -> dict[str, dict[str, str]]:
    drafts: dict[str, dict[str, str]] = {}
    for record in records:
        status = str(
            st.session_state.get(f"fac_id_{record.facility_id}")
            or record.identity_status
            or "operating"
        )
        payload = {"status": status}
        if status == IDENTITY_INCORRECT:
            payload["display_name"] = str(
                st.session_state.get(f"fac_fix_name_{record.facility_id}")
                or record.display_name
            )
            payload["address"] = str(
                st.session_state.get(f"fac_fix_addr_{record.facility_id}")
                or record.address
            )
        drafts[record.facility_id] = payload
    return drafts


def _render_facility_exception_row(record: FacilityMasterRecord) -> None:
    st.markdown(f"**{record.display_name}**")
    if record.address:
        st.caption(record.address)
    current = record.identity_status or (
        "sold"
        if record.inactive_reason == "sold"
        else (
            "not_ours"
            if record.inactive_reason == "not_ours"
            else (
                "inactive"
                if record.status == STATUS_INACTIVE
                else "operating"
            )
        )
    )
    if current not in IDENTITY_STATUSES:
        current = "operating"
    status = st.selectbox(
        t("setup.identity.status", lang),
        options=list(IDENTITY_STATUSES),
        index=list(IDENTITY_STATUSES).index(current),
        format_func=lambda code: t(f"setup.identity.{code}", lang),
        key=f"fac_id_{record.facility_id}",
        on_change=_on_exception_draft_change,
    )
    if status == IDENTITY_INCORRECT:
        st.text_input(
            t("setup.site_name", lang),
            value=record.display_name,
            key=f"fac_fix_name_{record.facility_id}",
            on_change=_on_exception_draft_change,
        )
        st.text_input(
            t("setup.site_address", lang),
            value=record.address,
            key=f"fac_fix_addr_{record.facility_id}",
            on_change=_on_exception_draft_change,
        )


def _render_step_facilities(
    draft: dict, company: CompanyMaster, facilities: FacilityMaster
) -> FacilityMaster:
    year = int(draft.get("reporting_year") or saved.get("reporting_year") or 2026)
    if facilities.previous_year_records and facilities.reuse_choice == "":
        st.markdown(t("setup.year_reuse", lang))
        reuse = st.radio(
            t("setup.year_reuse", lang),
            options=["reuse", "changed"],
            format_func=lambda code: t(f"setup.year_reuse.{code}", lang),
            key="apl_year_reuse",
            label_visibility="collapsed",
        )
        if reuse == "reuse":
            facilities = apply_reuse_previous(facilities)
            facilities.identity_confirmed = True
            _store_facilities(facilities)
        else:
            facilities.reuse_choice = "changed"

    facilities = rebuild_facility_master(
        session_state=st.session_state,
        company=company,
        official=_official_hints(),
        existing=facilities,
        reporting_year=year,
    )
    live = [item for item in facilities.records if item.status != STATUS_INACTIVE]
    official = official_factory_records(facilities.records)
    count = len(official) or len(live)
    exception_mode = bool(st.session_state.get(STATE_FACILITY_EXCEPTION_MODE))
    as_of = str(st.session_state.get("_cel_factory_as_of") or "")[:10]
    discrepancies = source_discrepancy_records(facilities.records)

    st.markdown(f"**{t('setup.facilities.title', lang)}**")
    if count:
        st.markdown(t("setup.facilities.found_official", lang, n=count))
        st.caption(t("setup.facilities.source_once", lang))
        if as_of:
            st.caption(t("setup.facilities.as_of", lang, date=as_of))
        st.markdown(t("setup.facilities.still_operating", lang, year=year))
    else:
        st.info(t("setup.facilities.none_found", lang))

    if discrepancies:
        st.markdown(
            t("setup.facilities.discrepancy_n", lang, n=len(discrepancies))
        )
        for item in discrepancies:
            st.markdown(f"**{item.display_name}**")
            if item.match_state == MATCH_OFFICIAL_ONLY:
                st.caption(t("setup.facilities.diff.official_only", lang))
            elif item.match_state == MATCH_UPLOAD_ONLY:
                st.caption(t("setup.facilities.diff.upload_only", lang))

    if count and not exception_mode:
        with onboarding_target("taiwan-facilities"):
            primary, secondary = st.columns(2)
            with primary:
                if st.button(
                    t("setup.facilities.confirm_all", lang, n=count),
                    key="apl_confirm_operating",
                    type="primary",
                ):
                    targets = official or live
                    confirm_all_operating(targets)
                    facilities.identity_confirmed = True
                    facilities.none_declared = False
                    st.session_state[STATE_FACILITY_EXCEPTION_MODE] = False
                    clear_exception_drafts_dirty(st.session_state)
                    _store_facilities(facilities)
                    st.rerun()
            with secondary:
                if st.button(
                    t("setup.facilities.exceptions", lang),
                    key="apl_facility_exceptions",
                ):
                    st.session_state[STATE_FACILITY_EXCEPTION_MODE] = True
                    mark_exception_drafts_dirty(st.session_state)
                    st.rerun()
        with st.expander(
            t("setup.facilities.view_list", lang, n=count), expanded=False
        ):
            for record in official or live:
                st.markdown(f"**{record.display_name}**")
                if record.address:
                    st.caption(record.address)
    elif not count:
        with onboarding_target("taiwan-facilities"):
            if st.button(
                t("setup.facilities.confirm_none", lang),
                key="apl_confirm_no_sites",
            ):
                facilities.identity_confirmed = True
                facilities.none_declared = True
                _store_facilities(facilities)
                st.rerun()

    if exception_mode:
        if st.session_state.get("_cel_facility_exception_need_confirm"):
            render_customer_notice(
                title=t("setup.facilities.exception_need_confirm_title", lang),
                body=t("setup.facilities.exception_need_confirm_body", lang),
            )
        for record in facilities.records:
            with st.container():
                _render_facility_exception_row(record)
        with onboarding_target("taiwan-facilities"):
            if st.button(
                t("setup.facilities.confirm_statuses", lang),
                key="apl_confirm_exception_statuses",
                type="primary",
            ):
                commit_identity_drafts(
                    facilities.records,
                    _exception_drafts_from_session(facilities.records),
                )
                facilities.identity_confirmed = True
                facilities.none_declared = not any(
                    item.customer_confirmed and item.status != STATUS_INACTIVE
                    for item in facilities.records
                )
                st.session_state["_cel_facility_exception_need_confirm"] = False
                clear_exception_drafts_dirty(st.session_state)
                _store_facilities(facilities)
                st.rerun()
        with st.expander(t("setup.add_site", lang), expanded=False):
            new_name = st.text_input(
                t("setup.site_name", lang),
                key="apl_new_site_name",
                on_change=_on_exception_draft_change,
            )
            new_addr = st.text_input(
                t("setup.site_address", lang),
                key="apl_new_site_addr",
                on_change=_on_exception_draft_change,
            )
            new_kind = st.selectbox(
                t("setup.site_kind", lang),
                options=SITE_KINDS,
                format_func=lambda code: t(f"setup.kind.{code}", lang),
                key="apl_new_site_kind",
                on_change=_on_exception_draft_change,
            )
            if st.button(t("setup.add_site_confirm", lang), key="apl_add_site"):
                name = str(new_name or "").strip()
                if name:
                    facilities.records.append(
                        FacilityMasterRecord(
                            facility_id=f"fac_{normalize_site_name(name)}_m",
                            display_name=name,
                            address=str(new_addr or ""),
                            source_type=SOURCE_MANUAL,
                            discovered_from=(SOURCE_MANUAL,),
                            site_kind=str(new_kind),
                            company_unified_business_number=(
                                company.unified_business_number
                            ),
                        )
                    )
                    mark_exception_drafts_dirty(st.session_state)
                    _store_facilities(facilities)
                    st.rerun()

    draft["has_taiwan_facilities"] = taiwan_facility_existence(
        facilities.records,
        identity_confirmed=facilities.identity_confirmed,
        none_declared=facilities.none_declared,
    )
    _store_facilities(facilities)
    return facilities


if not editing and saved and get_applicability_assessment(st.session_state) is not None:
    saved_assessment = get_applicability_assessment(st.session_state)
    showing_results = bool(
        st.session_state.get(STATE_BOUNDARY_WIZARD_RESULTS)
    )
    wizard_deferred = bool(
        st.session_state.get(STATE_BOUNDARY_WIZARD_DEFERRED)
    )
    if not showing_results and not wizard_deferred:
        render_boundary_wizard(
            assessment=saved_assessment,
            company=_load_company(),
            facilities=_load_facilities(),
            repo_root=repo_root,
            lang=lang,
            on_view_results=_view_current_results,
        )
    else:
        pad_l, results_col, pad_r = st.columns([0.4, 7.2, 0.4])
        with results_col:
            _render_results(saved_assessment)
            if st.button(t("apl.edit_profile", lang), key="apl_edit_profile"):
                st.session_state[STATE_COMPANY_PROFILE_EDITING] = True
                st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = 1
                st.rerun()
else:
    boundary_active = (
        step == STATE_WIZARD_MAX_STEP
        and not st.session_state.get(STATE_BOUNDARY_WIZARD_DEFERRED)
    )
    if boundary_active:
        shell = st.container()
    else:
        pad_l, shell, pad_r = st.columns([0.35, 7.3, 0.35])
    with shell:
        if step != STATE_WIZARD_MAX_STEP:
            render_stepper(step, STATE_WIZARD_MAX_STEP, STEP_LABELS, lang)
        draft = dict(saved)
        finish_label: str | None = None
        finish_disabled = False
        company = _load_company()
        facilities = _load_facilities()

        if step == 1:
            company = _render_step_company(draft, company)
        elif step == 2:
            with onboarding_target("company-additional-information"):
                _render_step_missing(draft, company)
                _wizard_nav(draft)
        elif step == 3:
            facilities = _render_step_facilities(draft, company, facilities)
            if facilities.identity_confirmed:
                with onboarding_target("facilities-continue"):
                    _wizard_nav(draft)
            else:
                _wizard_nav(draft)
        elif step == 4:
            mapping = merge_profile_from_setup(
                {**get_company_profile_mapping(st.session_state), **draft},
                company,
                facilities,
            )
            mapping["jurisdiction"] = "TW"
            if mapping.get("paid_in_capital_twd") in (0, "0"):
                mapping["paid_in_capital_twd"] = None
            if mapping.get("net_worth_twd") in (0, "0"):
                mapping["net_worth_twd"] = None
            profile = company_profile_from_mapping(mapping)
            assessment = assess_applicability(profile, repo_root=repo_root)
            save_company_profile(st.session_state, mapping)
            save_applicability_assessment(st.session_state, assessment)
            presented = present_assessment(assessment, lang)
            finish_label = t(presented.finish_label_key, lang)
            boundary_complete = render_boundary_wizard(
                assessment=assessment,
                company=company,
                facilities=facilities,
                repo_root=repo_root,
                lang=lang,
                on_view_results=_view_current_results,
            )
            finish_disabled = not boundary_complete
            if st.session_state.get(STATE_BOUNDARY_WIZARD_DEFERRED):
                _render_results(assessment)

        boundary_active = (
            step == STATE_WIZARD_MAX_STEP
            and not st.session_state.get(STATE_BOUNDARY_WIZARD_DEFERRED)
        )
        if not boundary_active and step == 4:
            _wizard_nav(
                draft,
                finish_label=finish_label,
                finish_disabled=finish_disabled,
            )
