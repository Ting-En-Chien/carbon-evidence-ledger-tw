"""Applicability — confirm company and sites, then show results."""

from __future__ import annotations

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
from carbon_ledger.ui.company_setup import (
    GROUP_SELF_ONLY,
    GROUP_UNKNOWN,
    GROUP_WITH_SUBS,
    apply_group_choice,
    entity_needs_customer,
    factory_source_as_of,
    has_real_uploaded_activity,
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
    render_money_field,
    render_stepper,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.learning import render_micro_help
from carbon_ledger.ui.money_input import format_twd_display
from carbon_ledger.ui.motion import (
    inject_animated_kpi_runtime,
    render_capital_countup,
    schedule_capital_countup,
)
from carbon_ledger.ui.state import (
    REPO_ROOT,
    STATE_APPLICABILITY_WIZARD_STEP,
    STATE_CAPITAL_LOOKUP_GEN,
    STATE_CAPITAL_PLAY_UBN,
    STATE_CAPITAL_RUNTIME_READY,
    STATE_COMPANY_LOOKUP_MANUAL,
    STATE_COMPANY_LOOKUP_NOT_FOUND,
    STATE_COMPANY_PROFILE_EDITING,
    STATE_FACILITY_EXCEPTION_MODE,
    STATE_WIZARD_MAX_STEP,
    get_applicability_assessment,
    get_company_master_mapping,
    get_company_profile_mapping,
    get_facility_master_mapping,
    get_language,
    save_applicability_assessment,
    save_company_master_mapping,
    save_company_profile,
    save_facility_master_mapping,
)

inject_design_system()
inject_enterprise_styles()
lang = get_language(st.session_state)
repo_root = Path(REPO_ROOT)

st.markdown(
    f"""
    <p class="cel-page-kicker">{t("nav.applicability", lang)}</p>
    <h1 class="cel-page-title">{t("apl.title", lang)}</h1>
    <p class="cel-page-sub">{t("apl.subtitle", lang)}</p>
    """,
    unsafe_allow_html=True,
)

saved = get_company_profile_mapping(st.session_state)
editing = bool(st.session_state.get(STATE_COMPANY_PROFILE_EDITING, True)) or not saved
step = int(st.session_state.get(STATE_APPLICABILITY_WIZARD_STEP) or 1)
step = max(1, min(STATE_WIZARD_MAX_STEP, step))

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


def _persist_partial(mapping: dict) -> None:
    company = _load_company()
    facilities = _load_facilities()
    merged = merge_profile_from_setup(saved, company, facilities, mapping)
    save_company_profile(st.session_state, merged)
    st.session_state[STATE_COMPANY_PROFILE_EDITING] = True


def _render_results(assessment) -> None:
    presented = present_assessment(assessment, lang)
    st.markdown(f"### {t('cust.results.heading', lang)}")
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
    if presented.presentations:
        st.markdown(f"**{t('cust.results.outcomes', lang)}**")
    for card in presented.presentations:
        render_compact_outcome_row(
            card,
            lang,
            show_actions=not presented.action_summary.customer_action_required,
        )


def _wizard_nav(draft: dict, *, finish_label: str | None = None) -> None:
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
            if st.button(t("setup.confirm_company", lang), key="apl_confirm_co"):
                company.customer_confirmed_at = utc_now_iso()
                inferred = infer_entity_from_listing(company.listing_status)
                if inferred:
                    draft["entity_type"] = inferred
                    draft["listing_status"] = company.listing_status
                _store_company(company)
                st.success(t("setup.confirm_company_ok", lang))
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
            index=ENTITY_OPTIONS.index(str(saved.get("entity_type") or "unresolved")),
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
            st.warning(t("setup.facilities.exception_need_confirm", lang))
        for record in facilities.records:
            with st.container():
                _render_facility_exception_row(record)
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

    if facilities.identity_confirmed and has_real_uploaded_activity(
        st.session_state
    ):
        coverage = st.radio(
            t("setup.coverage.question", lang),
            options=["all", "some", "unsure"],
            format_func=lambda code: t(f"setup.coverage.{code}", lang),
            key="apl_coverage_choice",
            index={"all": 0, "some": 1, "unsure": 2}.get(
                facilities.coverage_choice, 2
            ),
        )
        facilities.coverage_choice = str(coverage)
        active = [
            item
            for item in facilities.records
            if item.customer_confirmed and item.status != STATUS_INACTIVE
        ]
        if coverage == "all":
            for item in active:
                item.included_in_current_reporting_scope = True
        elif coverage == "some":
            for item in active:
                item.included_in_current_reporting_scope = st.checkbox(
                    item.display_name,
                    value=item.included_in_current_reporting_scope,
                    key=f"fac_cov_{item.facility_id}",
                )
        else:
            for item in active:
                item.included_in_current_reporting_scope = False

    draft["has_taiwan_facilities"] = taiwan_facility_existence(
        facilities.records,
        identity_confirmed=facilities.identity_confirmed,
        none_declared=facilities.none_declared,
    )
    _store_facilities(facilities)
    return facilities


if not editing and saved and get_applicability_assessment(st.session_state) is not None:
    pad_l, results_col, pad_r = st.columns([0.4, 7.2, 0.4])
    with results_col:
        if st.button(t("apl.edit_profile", lang), key="apl_edit_profile"):
            st.session_state[STATE_COMPANY_PROFILE_EDITING] = True
            st.session_state[STATE_APPLICABILITY_WIZARD_STEP] = 1
            st.rerun()
        _render_results(get_applicability_assessment(st.session_state))
else:
    pad_l, shell, pad_r = st.columns([0.35, 7.3, 0.35])
    with shell:
        render_stepper(step, STATE_WIZARD_MAX_STEP, STEP_LABELS, lang)
        draft = dict(saved)
        finish_label: str | None = None
        company = _load_company()
        facilities = _load_facilities()

        if step == 1:
            company = _render_step_company(draft, company)
        elif step == 2:
            _render_step_missing(draft, company)
        elif step == 3:
            facilities = _render_step_facilities(draft, company, facilities)
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
            _render_results(assessment)

        _wizard_nav(draft, finish_label=finish_label)
