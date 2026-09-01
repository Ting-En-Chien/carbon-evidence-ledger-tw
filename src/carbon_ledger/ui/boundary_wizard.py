"""Stage 4.2H-A period-level boundary semantics wizard."""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from carbon_ledger.company_master import CompanyMaster, FacilityMaster
from carbon_ledger.company_workspace import CompanyWorkspace, default_workspace_root
from carbon_ledger.inventory_boundary import (
    CONSOLIDATION_CONSOLIDATED,
    CONSOLIDATION_STANDALONE,
    CONSOLIDATION_UNRESOLVED,
    EVIDENCE_CONFIRMED_COMPANY_DOCUMENT,
    EVIDENCE_CUSTOMER_PENDING,
    MEMBERSHIP_EXCLUDED,
    MEMBERSHIP_INCLUDED,
    MEMBERSHIP_NOT_PERIOD,
    MEMBERSHIP_UNCERTAIN,
    OPERATING_FULL_PERIOD,
    OPERATING_NO_OPERATION_FULL_PERIOD,
    OPERATING_STARTED_DURING_PERIOD,
    OPERATING_STOPPED_DURING_PERIOD,
    OPERATING_TRANSFERRED_DURING_PERIOD,
    OPERATING_UNCERTAIN,
    PURPOSE_IFRS_REPORTING_ENTITY,
    PURPOSE_LISTED_CONSOLIDATED,
    PURPOSE_MOENV_FACILITY,
    PURPOSE_OUTCOME_FUTURE,
    PURPOSE_OUTCOME_UNRESOLVED,
    RECONCILIATION_DUPLICATE,
    RECONCILIATION_MATCHED,
    RECONCILIATION_NO_LONGER_VALID,
    RECONCILIATION_OTHER_COMPANY,
    RECONCILIATION_UNRESOLVED,
    BoundarySemanticsState,
    CanonicalSite,
    CompetentAuthorityBoundaryEvidence,
    FinancialStatementReportingEntityEvidence,
    PeriodOperatingFact,
    RegistrationReconciliation,
    ReportingPeriod,
    boundaries_from_reviews,
    build_boundary_review_queues,
    canonical_site_id,
    initial_boundary_semantics_state,
    normalize_confirmer_details,
    utc_now_iso,
)
from carbon_ledger.legal_entity import (
    CONFIRMATION_DRAFT,
    CONFIRMATION_LOCAL,
    LegalEntity,
)
from carbon_ledger.ui.app_mode import is_admin_mode
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_BOUNDARY_COMPANY_INDEX,
    STATE_BOUNDARY_EVIDENCE_INDEX,
    STATE_BOUNDARY_MEMBERSHIP_INDEX,
    STATE_BOUNDARY_OPERATING_INDEX,
    STATE_BOUNDARY_RECONCILIATION_INDEX,
    STATE_BOUNDARY_WIZARD_DEFERRED,
    STATE_BOUNDARY_WIZARD_RESULTS,
    STATE_BOUNDARY_WIZARD_STEP,
    confirmed_company_ubn,
    get_applicability_assessment,
    get_company_master_mapping,
    get_company_profile_mapping,
)
from carbon_ledger.ui.tutorial import onboarding_target

WIZARD_STEPS = (
    "period",
    "purposes",
    "reporting_entities",
    "registrations",
    "operations",
    "review",
)

OPERATING_CHOICES = (
    OPERATING_FULL_PERIOD,
    OPERATING_STARTED_DURING_PERIOD,
    OPERATING_STOPPED_DURING_PERIOD,
    OPERATING_TRANSFERRED_DURING_PERIOD,
    OPERATING_NO_OPERATION_FULL_PERIOD,
    OPERATING_UNCERTAIN,
)
MEMBERSHIP_CHOICES = (
    MEMBERSHIP_INCLUDED,
    MEMBERSHIP_EXCLUDED,
    MEMBERSHIP_NOT_PERIOD,
    MEMBERSHIP_UNCERTAIN,
)
RECONCILIATION_CHOICES = (
    RECONCILIATION_MATCHED,
    RECONCILIATION_DUPLICATE,
    RECONCILIATION_OTHER_COMPANY,
    RECONCILIATION_NO_LONGER_VALID,
    RECONCILIATION_UNRESOLVED,
)
NEW_SITE_OPTION = ""

_ACTIVE_PERIOD_PREFIX = "boundary_active_period_"


def active_reporting_year(session_state: Any) -> int:
    """The reporting year this session is working on (0 when unknown).

    Reuses the wizard's own sources in priority order: the assessment year the
    wizard keys its active period on, then the confirmed company profile year.
    """
    assessment = get_applicability_assessment(session_state)
    raw = getattr(assessment, "reporting_year", None)
    try:
        year = int(raw or 0)
    except (TypeError, ValueError):
        year = 0
    if year > 0:
        return year
    profile = get_company_profile_mapping(session_state)
    try:
        year = int(profile.get("reporting_year") or 0)
    except (TypeError, ValueError):
        return 0
    return year if year > 0 else 0


def active_period_id(session_state: Any, workspace_id: str, year: int) -> str:
    """Exact active period this session selected for one company and year."""
    if not workspace_id or year <= 0:
        return ""
    key = f"{_ACTIVE_PERIOD_PREFIX}{workspace_id}_{year}"
    try:
        return str(session_state[key] or "").strip()
    except Exception:  # noqa: BLE001 - AppTest proxies vary
        return ""


def confirmed_boundary_semantics(
    session_state: Any,
    *,
    repo_root: Path | None = None,
) -> BoundarySemanticsState | None:
    """Return the confirmed package of the period this session is working on.

    This is the wizard's own authority: a period package only becomes current
    after ``append_semantics_current``, which requires an explicitly confirmed
    ReportingPeriod. Only the exact active period is read — an earlier year
    that was confirmed never stands in for the current one.
    """
    ubn = confirmed_company_ubn(session_state)
    if not ubn:
        return None
    master = get_company_master_mapping(session_state)
    try:
        workspace = CompanyWorkspace.for_company(
            root=default_workspace_root(repo_root),
            taiwan_ubn=ubn,
            entity_id=str(master.get("company_id") or ""),
        )
    except ValueError:
        return None
    period_id = active_period_id(
        session_state,
        workspace.workspace_id,
        active_reporting_year(session_state),
    )
    if not period_id:
        return None
    try:
        state = workspace.load_semantics_current(reporting_period_id=period_id)
    except (OSError, ValueError, FileNotFoundError):
        return None
    if state is None or state.confirmation_state != CONFIRMATION_LOCAL:
        return None
    try:
        state.reporting_period.require_explicit_confirmation()
    except Exception:  # noqa: BLE001 - unconfirmed period is not authority
        return None
    return state


def company_setup_ready(
    session_state: Any,
    *,
    repo_root: Path | None = None,
) -> bool:
    """True when identity, ReportingPeriod and boundary scope are confirmed."""
    return confirmed_boundary_semantics(session_state, repo_root=repo_root) is not None


def ifrs_reporting_entity_step_required(
    session_state: Any,
    *,
    repo_root: Path | None = None,
) -> bool:
    """Read-only: whether the IFRS reporting-entity wizard step will render.

    Does not change boundary confirmation or purpose outcomes. Returns True
    when the draft cannot be read, so onboarding never skips a live step.
    """
    ubn = confirmed_company_ubn(session_state)
    if not ubn:
        return False
    master = get_company_master_mapping(session_state)
    try:
        workspace = CompanyWorkspace.for_company(
            root=default_workspace_root(repo_root),
            taiwan_ubn=ubn,
            entity_id=str(master.get("company_id") or ""),
        )
    except ValueError:
        return True
    period_id = active_period_id(
        session_state,
        workspace.workspace_id,
        active_reporting_year(session_state),
    )
    if not period_id:
        return True
    try:
        state = workspace.load_semantics_draft(reporting_period_id=period_id)
        if state is None:
            state = workspace.load_semantics_current(reporting_period_id=period_id)
    except (OSError, ValueError, FileNotFoundError):
        return True
    if state is None:
        return True
    return _ifrs_step_required(state)


@dataclass(frozen=True)
class ReconciliationFormSpec:
    show_site_select: bool
    allow_create_site: bool
    show_new_site_fields: bool
    show_government_prefill_notice: bool
    require_site_confirm: bool
    show_other_basis: bool
    show_invalid_basis: bool
    show_evidence: bool
    show_notes: bool
    show_no_sites_for_duplicate: bool
    primary_disabled: bool


@dataclass(frozen=True)
class ReconciliationAnswerResult:
    error_key: str = ""
    reconciliation: RegistrationReconciliation | None = None
    new_site: CanonicalSite | None = None


def period_form_defaults(
    *,
    assessment_year: int,
    active_period: ReportingPeriod | None,
) -> tuple[int, date, date]:
    """Prefill the active period, otherwise the assessment calendar year."""
    if active_period is None:
        year = int(assessment_year)
        return year, date(year, 1, 1), date(year, 12, 31)
    year = int(active_period.reporting_year_confirmed or assessment_year)
    start_raw = str(active_period.period_start_confirmed or "").strip()
    end_raw = str(active_period.period_end_confirmed or "").strip()
    start = date.fromisoformat(start_raw) if start_raw else date(year, 1, 1)
    end = date.fromisoformat(end_raw) if end_raw else date(year, 12, 31)
    return year, start, end


def reconciliation_form_spec(
    state_choice: str,
    *,
    existing_site_count: int,
    selected_site_id: str = "",
) -> ReconciliationFormSpec:
    """Decide which reconciliation fields the customer should see."""
    matched = state_choice == RECONCILIATION_MATCHED
    duplicate = state_choice == RECONCILIATION_DUPLICATE
    other = state_choice == RECONCILIATION_OTHER_COMPANY
    invalid = state_choice == RECONCILIATION_NO_LONGER_VALID
    unresolved = state_choice == RECONCILIATION_UNRESOLVED
    no_sites = existing_site_count == 0
    creating_new = matched and not str(selected_site_id or "").strip()
    return ReconciliationFormSpec(
        show_site_select=matched or (duplicate and not no_sites),
        allow_create_site=matched,
        show_new_site_fields=creating_new,
        show_government_prefill_notice=creating_new,
        require_site_confirm=creating_new,
        show_other_basis=other,
        show_invalid_basis=invalid,
        show_evidence=other or invalid,
        show_notes=unresolved,
        show_no_sites_for_duplicate=duplicate and no_sites,
        primary_disabled=duplicate and no_sites,
    )


def apply_reconciliation_answer(
    *,
    existing: RegistrationReconciliation,
    state_choice: str,
    selected_site_id: str = "",
    new_site_name: str = "",
    new_site_address: str = "",
    new_site_confirmed: bool = False,
    basis: str = "",
    evidence_reference: str = "",
    notes: str = "",
    existing_sites: tuple[CanonicalSite, ...] = (),
    existing_reconciliations: tuple[RegistrationReconciliation, ...] = (),
    workspace_id: str = "",
    company_entity_id: str = "",
    confirmed_at: str = "",
) -> ReconciliationAnswerResult:
    """Validate one answer and drop fields that do not belong to that choice."""
    sites = {item.site_id: item for item in existing_sites}
    spec = reconciliation_form_spec(
        state_choice,
        existing_site_count=len(sites),
        selected_site_id=selected_site_id,
    )
    if spec.primary_disabled:
        return ReconciliationAnswerResult(error_key="boundary.error.duplicate_site")
    canonical_id = ""
    primary_candidate_id = ""
    saved_basis = ""
    saved_evidence = ""
    stamp = str(confirmed_at or "").strip()
    new_site: CanonicalSite | None = None
    if state_choice == RECONCILIATION_MATCHED:
        chosen = str(selected_site_id or "").strip()
        if chosen:
            if chosen not in sites:
                return ReconciliationAnswerResult(
                    error_key="boundary.error.canonical_site"
                )
            canonical_id = chosen
        else:
            if not new_site_confirmed:
                return ReconciliationAnswerResult(
                    error_key="boundary.error.site_confirm"
                )
            if not str(new_site_name or "").strip():
                return ReconciliationAnswerResult(
                    error_key="boundary.error.canonical_site"
                )
            canonical_id = canonical_site_id(
                workspace_id=workspace_id,
                display_name=new_site_name,
                address=new_site_address,
            )
            if canonical_id not in sites:
                new_site = CanonicalSite(
                    site_id=canonical_id,
                    display_name=str(new_site_name).strip(),
                    address=str(new_site_address).strip(),
                    company_entity_id=company_entity_id,
                    locally_confirmed_at=stamp,
                )
    elif state_choice == RECONCILIATION_DUPLICATE:
        chosen = str(selected_site_id or "").strip()
        if not chosen or chosen not in sites:
            return ReconciliationAnswerResult(error_key="boundary.error.duplicate_site")
        canonical_id = chosen
        primary_candidate_id = next(
            (
                item.candidate_id
                for item in existing_reconciliations
                if item.candidate_id != existing.candidate_id
                and item.canonical_site_id == canonical_id
                and item.state
                in {RECONCILIATION_MATCHED, RECONCILIATION_DUPLICATE}
            ),
            "",
        )
        if not primary_candidate_id:
            return ReconciliationAnswerResult(
                error_key="boundary.error.duplicate_primary"
            )
    elif state_choice == RECONCILIATION_OTHER_COMPANY:
        if not str(basis or "").strip():
            return ReconciliationAnswerResult(
                error_key="boundary.error.other_company_basis"
            )
        saved_basis = str(basis).strip()
        saved_evidence = str(evidence_reference or "").strip()
    elif state_choice == RECONCILIATION_NO_LONGER_VALID:
        if not str(basis or "").strip():
            return ReconciliationAnswerResult(
                error_key="boundary.error.registration_basis"
            )
        saved_basis = str(basis).strip()
        saved_evidence = str(evidence_reference or "").strip()
    elif state_choice == RECONCILIATION_UNRESOLVED:
        saved_basis = str(notes or "").strip()
        stamp = ""
    else:
        return ReconciliationAnswerResult(error_key="boundary.wizard.answer_required")
    return ReconciliationAnswerResult(
        reconciliation=RegistrationReconciliation(
            reconciliation_id=existing.reconciliation_id,
            candidate_id=existing.candidate_id,
            reporting_period_id=existing.reporting_period_id,
            state=state_choice,
            canonical_site_id=canonical_id,
            primary_candidate_id=primary_candidate_id,
            basis=saved_basis,
            evidence_reference=saved_evidence,
            locally_confirmed_at=stamp,
        ),
        new_site=new_site,
    )


@dataclass(frozen=True)
class BoundaryWizardContext:
    assessment: Any
    company: CompanyMaster
    facilities: FacilityMaster
    workspace: CompanyWorkspace
    assessment_year: int
    active_period_key: str


def _id(prefix: str, *parts: str) -> str:
    value = "\x1f".join(str(part or "").strip() for part in parts)
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _render_stepper(step: int, lang: str) -> None:
    nodes: list[str] = []
    for index, code in enumerate(WIZARD_STEPS, start=1):
        state = "done" if index < step else ("current" if index == step else "todo")
        nodes.append(
            "<div class='cel-boundary-step "
            f"is-{state}'><span>{index}</span><strong>"
            f"{_escape(t(f'boundary.wizard.step.{code}', lang))}"
            "</strong></div>"
        )
    with st.container(key="cel_boundary_stepper_region"):
        st.markdown(
            "<div data-cel-boundary-stepper='1' class='cel-boundary-stepper'>"
            "<div class='cel-boundary-stepper-meta'>"
            f"{_escape(t('boundary.wizard.step_of', lang, current=step))}</div>"
            f"<div class='cel-boundary-stepper-row'>{''.join(nodes)}</div></div>",
            unsafe_allow_html=True,
        )


def _render_context(title: str, lang: str, step: int) -> None:
    with st.container(key="cel_boundary_context_region"):
        st.markdown(
            "<div data-cel-boundary-context='1' class='cel-boundary-context'>"
            f"{_escape(t('boundary.wizard.step_of', lang, current=step))} · "
            f"{_escape(title)}</div>",
            unsafe_allow_html=True,
        )


def _card(title: str, *, completion: bool = False) -> Any:
    container = st.container(key="cel_boundary_active_card", border=True)
    with container:
        marker = (
            "data-cel-boundary-completion-card='1'"
            if completion
            else "data-cel-boundary-primary-card='1'"
        )
        st.markdown(f"<span {marker}></span>", unsafe_allow_html=True)
        st.markdown(
            f"<h2 class='cel-boundary-step-title'>{_escape(title)}</h2>",
            unsafe_allow_html=True,
        )
    return container


def _support(*, why: str, role: str, evidence: str, uncertain: str, lang: str) -> None:
    blocks = "".join(
        "<div><strong>"
        f"{_escape(t(f'boundary.wizard.support.{code}', lang))}</strong>"
        f"<p>{_escape(text)}</p></div>"
        for code, text in (
            ("why", why),
            ("role", role),
            ("evidence", evidence),
            ("uncertain", uncertain),
        )
    )
    st.markdown(
        f"<div class='cel-boundary-support'>{blocks}</div>",
        unsafe_allow_html=True,
    )


def _status(text: str, tone: str = "warning") -> None:
    st.markdown(
        f"<div class='cel-boundary-status is-{tone}' role='status'>"
        f"{_escape(text)}</div>",
        unsafe_allow_html=True,
    )


def _go(step: int) -> None:
    st.session_state[STATE_BOUNDARY_WIZARD_STEP] = max(1, min(6, step))
    st.session_state[STATE_BOUNDARY_WIZARD_DEFERRED] = False
    st.session_state[STATE_BOUNDARY_WIZARD_RESULTS] = False
    st.rerun()


def _defer() -> None:
    st.session_state[STATE_BOUNDARY_WIZARD_DEFERRED] = True
    st.session_state[STATE_BOUNDARY_WIZARD_RESULTS] = False
    st.rerun()


def _footer(
    *,
    key: str,
    lang: str,
    primary_label: str,
    on_primary: Callable[[], None],
    on_back: Callable[[], None] | None,
    disabled: bool = False,
) -> None:
    clicked = False
    with st.container(key="cel_boundary_footer"):
        st.markdown(
            "<span data-cel-boundary-footer='1'></span>",
            unsafe_allow_html=True,
        )
        back_col, later_col, primary_col = st.columns([1, 1, 1.6])
        with back_col:
            if on_back and st.button(
                t("boundary.wizard.back", lang),
                key=f"{key}_back",
                use_container_width=True,
            ):
                on_back()
        with later_col:
            if st.button(
                t("boundary.wizard.later", lang),
                key=f"{key}_later",
                use_container_width=True,
            ):
                _defer()
        with primary_col:
            clicked = st.button(
                primary_label,
                key=f"{key}_primary",
                type="primary",
                disabled=disabled,
                use_container_width=True,
            )
    if clicked:
        on_primary()


def _collect_context(
    *,
    assessment: Any,
    company: CompanyMaster,
    facilities: FacilityMaster,
    repo_root: Path,
) -> BoundaryWizardContext | None:
    try:
        workspace = CompanyWorkspace.for_company(
            root=default_workspace_root(repo_root),
            taiwan_ubn=company.unified_business_number,
            entity_id=company.company_id,
        )
    except ValueError:
        return None
    year = int(getattr(assessment, "reporting_year", 0) or 0)
    return BoundaryWizardContext(
        assessment=assessment,
        company=company,
        facilities=facilities,
        workspace=workspace,
        assessment_year=year,
        active_period_key=f"boundary_active_period_{workspace.workspace_id}_{year}",
    )


def _active_period_id(context: BoundaryWizardContext) -> str:
    return str(st.session_state.get(context.active_period_key) or "")


def _load_state(context: BoundaryWizardContext) -> BoundarySemanticsState | None:
    period_id = _active_period_id(context)
    if not period_id:
        return None
    draft = context.workspace.load_semantics_draft(reporting_period_id=period_id)
    if draft is not None:
        return draft
    return context.workspace.load_semantics_current(reporting_period_id=period_id)


def _save_state(context: BoundaryWizardContext, state: BoundarySemanticsState) -> None:
    context.workspace.write_semantics_draft(
        replace(
            state,
            confirmation_state=CONFIRMATION_DRAFT,
            locally_confirmed_at="",
            version=0,
        )
    )


def _company_entity(context: BoundaryWizardContext) -> LegalEntity:
    name = context.company.company_name.strip()
    return LegalEntity(
        entity_id=context.company.company_id
        or _id(
            "entity",
            context.company.unified_business_number,
            context.company.company_name,
        ),
        legal_name=name,
        jurisdiction="TW",
        registration_id=context.company.unified_business_number,
        taiwan_ubn=context.company.unified_business_number,
        source="company_master",
    )


def _purpose_label(purpose: str, lang: str) -> str:
    return t(f"boundary.purpose.{purpose}", lang)


def _reporting_entity_display_name(purpose: str, lang: str) -> str:
    return t(f"boundary.wizard.reporting_entities.name.{purpose}", lang)


def _reporting_entity_reviews(
    state: BoundarySemanticsState,
) -> list[Any]:
    return [
        item
        for item in state.purpose_reviews
        if item.purpose
        in {PURPOSE_IFRS_REPORTING_ENTITY, PURPOSE_LISTED_CONSOLIDATED}
        and item.outcome != PURPOSE_OUTCOME_FUTURE
    ]


def _ifrs_step_required(state: BoundarySemanticsState) -> bool:
    return bool(_reporting_entity_reviews(state))


def _step_after_purposes(state: BoundarySemanticsState) -> int:
    return 3 if _ifrs_step_required(state) else 4


def _step_before_registrations(state: BoundarySemanticsState) -> int:
    return 3 if _ifrs_step_required(state) else 2


def _known_legal_entities(
    context: BoundaryWizardContext, state: BoundarySemanticsState
) -> tuple[LegalEntity, ...]:
    company = _company_entity(context)
    by_id = {company.entity_id: company}
    for boundary in state.boundaries:
        for entity in boundary.legal_entities:
            entity_id = str(entity.entity_id or "").strip()
            if entity_id and entity_id not in by_id:
                by_id[entity_id] = entity
    return tuple(by_id.values())


def included_legal_entity_ids_for_basis(
    *,
    basis: str,
    company_entity_id: str,
    candidate_ids: tuple[str, ...] = (),
    known_legal_entity_ids: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Choose included legal-entity IDs from real legal entities only."""
    company = str(company_entity_id or "").strip()
    known = {
        str(item).strip()
        for item in (
            known_legal_entity_ids
            if known_legal_entity_ids is not None
            else candidate_ids
        )
        if str(item).strip()
    }
    if company:
        known.add(company)
    filtered: list[str] = []
    seen: set[str] = set()
    for raw in candidate_ids:
        entity_id = str(raw).strip()
        if not entity_id or entity_id in seen or entity_id not in known:
            continue
        seen.add(entity_id)
        filtered.append(entity_id)
    if basis == CONSOLIDATION_STANDALONE:
        return (company,) if company else ()
    if basis == CONSOLIDATION_CONSOLIDATED:
        others = tuple(item for item in filtered if item != company)
        if not company or not others:
            return ()
        return (company, *others)
    return ()


def draft_reporting_entity_evidence(
    *,
    existing: FinancialStatementReportingEntityEvidence | None,
    reporting_period_id: str,
    entity: LegalEntity,
    basis: str,
    reporting_entity_name: str,
    financial_statement_title: str = "",
    financial_statement_type: str = "",
    issuer_or_source: str = "",
    provenance_reference: str = "",
    included_legal_entity_ids: tuple[str, ...] = (),
    known_legal_entity_ids: tuple[str, ...] | None = None,
) -> FinancialStatementReportingEntityEvidence:
    """Build one period-level evidence row without changing domain rules."""
    name = str(reporting_entity_name or "").strip()
    provenance = str(provenance_reference or "").strip()
    included = included_legal_entity_ids_for_basis(
        basis=basis,
        company_entity_id=entity.entity_id,
        candidate_ids=included_legal_entity_ids,
        known_legal_entity_ids=known_legal_entity_ids,
    )
    candidate = FinancialStatementReportingEntityEvidence(
        evidence_id=(
            existing.evidence_id
            if existing
            else _id(
                "financial_reporting_entity_evidence",
                reporting_period_id,
                entity.entity_id,
            )
        ),
        reporting_period_id=reporting_period_id,
        financial_statement_title=str(financial_statement_title or ""),
        financial_statement_type=str(financial_statement_type or ""),
        issuer_or_source=str(issuer_or_source or ""),
        reporting_entity_identifier=entity.entity_id,
        reporting_entity_name=name,
        consolidation_basis=basis,
        included_legal_entity_ids=included,
        provenance_reference=provenance,
        verification_state=EVIDENCE_CONFIRMED_COMPANY_DOCUMENT,
    )
    if candidate.confirms_reporting_entity:
        return candidate
    return replace(
        candidate,
        verification_state=EVIDENCE_CUSTOMER_PENDING,
        included_legal_entity_ids=(),
    )


def _rebuild_boundaries(
    context: BoundaryWizardContext, state: BoundarySemanticsState
) -> BoundarySemanticsState:
    old_by_id = {item.boundary_id: item for item in state.boundaries}
    built = boundaries_from_reviews(
        reviews=state.purpose_reviews,
        reporting_period=state.reporting_period,
        legal_entities=_known_legal_entities(context, state),
        authority_evidence=state.authority_evidence,
        financial_statement_evidence=state.financial_reporting_entity_evidence,
    )
    merged = []
    for boundary in built:
        previous = old_by_id.get(boundary.boundary_id)
        if previous is None:
            merged.append(boundary)
            continue
        previous_entities = {
            item.entity_id: item for item in previous.entity_memberships
        }
        previous_sites = {
            item.canonical_site_id: item for item in previous.facility_memberships
        }
        merged.append(
            replace(
                boundary,
                entity_memberships=tuple(
                    previous_entities.get(item.entity_id, item)
                    for item in boundary.entity_memberships
                ),
                facility_memberships=tuple(
                    previous_sites.get(item.canonical_site_id, item)
                    for item in boundary.facility_memberships
                ),
            )
        )
    return replace(state, boundaries=tuple(merged))


def _period_step(context: BoundaryWizardContext, lang: str) -> None:
    _period_step_body(context, lang)


def _period_step_body(context: BoundaryWizardContext, lang: str) -> None:
    title = t("boundary.wizard.period.title", lang)
    _render_context(title, lang, 1)
    current = _load_state(context)
    with _card(title):
        _support(
            why=t("boundary.wizard.period.why", lang),
            role=t("boundary.wizard.period.role", lang),
            evidence=t("boundary.wizard.period.evidence", lang),
            uncertain=t("boundary.wizard.period.uncertain", lang),
            lang=lang,
        )
        selected = current.reporting_period if current else None
        year_default, start_default, end_default = period_form_defaults(
            assessment_year=context.assessment_year,
            active_period=selected,
        )
        active_id = _active_period_id(context)
        prefill_key = "boundary_wizard_period_prefilled_for"
        if active_id and st.session_state.get(prefill_key) != active_id:
            st.session_state["boundary_wizard_period_year"] = year_default
            st.session_state["boundary_wizard_period_start"] = start_default
            st.session_state["boundary_wizard_period_end"] = end_default
            st.session_state["boundary_wizard_period_explicit"] = True
            st.session_state[prefill_key] = active_id
        compact, _ = st.columns((7, 5))
        with compact:
            with onboarding_target("reporting-period-confirmation"):
                year = st.number_input(
                    t("boundary.period.year", lang),
                    min_value=2020,
                    max_value=2100,
                    value=year_default,
                    step=1,
                    key="boundary_wizard_period_year",
                )
                cols = st.columns(2)
                with cols[0]:
                    start = st.date_input(
                        t("boundary.period.start", lang),
                        value=start_default,
                        key="boundary_wizard_period_start",
                    )
                with cols[1]:
                    end = st.date_input(
                        t("boundary.period.end", lang),
                        value=end_default,
                        key="boundary_wizard_period_end",
                    )
                explicit = st.checkbox(
                    t("boundary.period.confirm", lang),
                    value=selected is not None,
                    key="boundary_wizard_period_explicit",
                )

    def save() -> None:
        if not explicit:
            st.error(t("boundary.error.period", lang))
            return
        try:
            period = ReportingPeriod.confirmed(
                reporting_year_suggested=context.assessment_year,
                reporting_year_confirmed=int(year),
                period_start_confirmed=start.isoformat(),
                period_end_confirmed=end.isoformat(),
            )
        except ValueError:
            st.error(t("boundary.error.period", lang))
            return
        state = context.workspace.load_semantics_draft(
            reporting_period_id=period.reporting_period_id
        ) or context.workspace.load_semantics_current(
            reporting_period_id=period.reporting_period_id
        )
        if state is None:
            state = initial_boundary_semantics_state(
                assessment=context.assessment,
                company=context.company,
                facilities=context.facilities.records,
                workspace_id=context.workspace.workspace_id,
                reporting_period=period,
            )
        st.session_state[context.active_period_key] = period.reporting_period_id
        st.session_state[STATE_BOUNDARY_COMPANY_INDEX] = 0
        st.session_state[STATE_BOUNDARY_RECONCILIATION_INDEX] = 0
        st.session_state[STATE_BOUNDARY_EVIDENCE_INDEX] = "evidence"
        st.session_state[STATE_BOUNDARY_OPERATING_INDEX] = 0
        st.session_state[STATE_BOUNDARY_MEMBERSHIP_INDEX] = 0
        _save_state(context, replace(state, reporting_period=period))
        _go(2)

    _footer(
        key="boundary_period",
        lang=lang,
        primary_label=t("boundary.wizard.save_continue", lang),
        on_primary=save,
        on_back=None,
    )


def _customer_purpose_status_key(review: Any) -> str:
    status = str(getattr(review, "assessment_status", "") or "")
    outcome = str(getattr(review, "outcome", "") or "")
    if outcome == PURPOSE_OUTCOME_FUTURE:
        return "boundary.wizard.purposes.status.future"
    if status == "APPLICABLE" and outcome != PURPOSE_OUTCOME_UNRESOLVED:
        return "boundary.wizard.purposes.status.applicable_confirm"
    return "boundary.wizard.purposes.status.needs_confirm"


def _purpose_step(
    context: BoundaryWizardContext, state: BoundarySemanticsState, lang: str
) -> None:
    title = t("boundary.wizard.purposes.title", lang)
    _render_context(title, lang, 2)
    with _card(title):
        st.markdown(
            "<span data-cel-purpose-review-customer='1'></span>",
            unsafe_allow_html=True,
        )
        st.markdown(t("boundary.wizard.purposes.intro", lang))
        _status(t("boundary.wizard.purposes.non_approval", lang), "neutral")
        if not state.purpose_reviews:
            st.info(t("boundary.wizard.purposes.none", lang))
        for review in state.purpose_reviews:
            st.markdown(f"**{_purpose_label(review.purpose, lang)}**")
            st.caption(
                f"{t('boundary.wizard.purposes.status_label', lang)}："
                f"{t(_customer_purpose_status_key(review), lang)}"
            )
            st.caption(
                f"{t('boundary.wizard.purposes.why_label', lang)}："
                f"{t(f'boundary.wizard.purposes.why.{review.purpose}', lang)}"
            )
            st.caption(
                f"{t('boundary.wizard.purposes.impact_label', lang)}："
                f"{t(f'boundary.wizard.purposes.impact.{review.purpose}', lang)}"
            )
            if review.effective_year:
                st.caption(
                    t(
                        "boundary.wizard.purposes.effective_year",
                        lang,
                        year=review.effective_year,
                    )
                )
            if is_admin_mode(st.session_state):
                st.caption(
                    t(
                        "boundary.wizard.purposes.admin_provenance",
                        lang,
                        obligation=review.obligation_id,
                        status=review.assessment_status,
                        rules=", ".join(review.applied_rule_ids) or "—",
                    )
                )
        st.caption(t("boundary.wizard.later_not_confirmed", lang))
    _footer(
        key="boundary_purposes",
        lang=lang,
        primary_label=t("boundary.wizard.save_continue", lang),
        on_primary=lambda: _go(_step_after_purposes(state)),
        on_back=lambda: _go(1),
    )


def _reporting_entity_step(
    context: BoundaryWizardContext, state: BoundarySemanticsState, lang: str
) -> None:
    title = t("boundary.wizard.reporting_entities.title", lang)
    _render_context(title, lang, 3)
    reviews = _reporting_entity_reviews(state)
    if not reviews:
        _go(4)
        return
    existing = next(
        (
            item
            for item in state.financial_reporting_entity_evidence
            if item.reporting_period_id == state.reporting_period.reporting_period_id
        ),
        None,
    )
    company_name = context.company.company_name.strip()
    legal_entities = _known_legal_entities(context, state)
    period_id = state.reporting_period.reporting_period_id
    with _card(title):
        st.markdown(
            "<span data-cel-ifrs-guided-flow='1'></span>",
            unsafe_allow_html=True,
        )
        st.caption(
            t(
                "boundary.wizard.reporting_entities.affects",
                lang,
                names="、".join(
                    _reporting_entity_display_name(item.purpose, lang)
                    for item in reviews
                ),
            )
        )
        st.info(t("boundary.wizard.reporting_entities.ifrs_notice", lang))
        st.caption(t("boundary.wizard.reporting_entities.limit", lang))
        basis_options = (
            CONSOLIDATION_STANDALONE,
            CONSOLIDATION_CONSOLIDATED,
            CONSOLIDATION_UNRESOLVED,
        )
        current_basis = (
            existing.consolidation_basis if existing else CONSOLIDATION_UNRESOLVED
        )
        basis = st.radio(
            t("boundary.wizard.reporting_entities.question", lang),
            options=basis_options,
            index=(
                basis_options.index(current_basis)
                if current_basis in basis_options
                else 2
            ),
            format_func=lambda value: t(
                f"boundary.wizard.consolidation.{value}", lang
            ),
            key=f"boundary_reporting_basis_{period_id}",
        )
        default_entity = (
            existing.reporting_entity_name
            if existing and existing.reporting_entity_name
            else company_name
        )
        entity_name = default_entity
        if basis == CONSOLIDATION_STANDALONE:
            st.markdown(
                t(
                    "boundary.wizard.reporting_entities.standalone_confirm",
                    lang,
                    company=company_name or "—",
                )
            )
            entity_name = st.text_input(
                t("boundary.wizard.reporting_entities.entity_name", lang),
                value=default_entity,
                key=f"boundary_reporting_name_{period_id}",
            )
            if any(
                item.purpose == PURPOSE_LISTED_CONSOLIDATED for item in reviews
            ):
                pending_key = (
                    "boundary.wizard.reporting_entities."
                    "standalone_keeps_listed_pending"
                )
                st.caption(t(pending_key, lang))
        elif basis == CONSOLIDATION_CONSOLIDATED:
            st.markdown(
                t("boundary.wizard.reporting_entities.consolidated_confirm", lang)
            )
            entity_name = st.text_input(
                t("boundary.wizard.reporting_entities.group_name", lang),
                value=default_entity,
                key=f"boundary_reporting_name_{period_id}",
            )
            if len(legal_entities) <= 1:
                st.info(
                    t(
                        "boundary.wizard.reporting_entities.no_subsidiaries",
                        lang,
                    )
                )
                st.caption(
                    t(
                        "boundary.wizard.reporting_entities.need_subsidiaries",
                        lang,
                    )
                )
            else:
                st.caption(
                    t("boundary.wizard.reporting_entities.covered_companies", lang)
                )
                for entity in legal_entities:
                    st.write(f"- {entity.legal_name}")
        else:
            st.info(t("boundary.wizard.reporting_entities.unresolved_help", lang))
            st.caption(t("boundary.wizard.later_not_confirmed", lang))
        with st.expander(
            t("boundary.wizard.reporting_entities.evidence_expander", lang),
            expanded=False,
        ):
            statement_title = st.text_input(
                t("boundary.wizard.reporting_entities.statement", lang),
                value=existing.financial_statement_title if existing else "",
                key=f"boundary_reporting_statement_{period_id}",
            )
            statement_type = st.text_input(
                t("boundary.wizard.reporting_entities.statement_type", lang),
                value=existing.financial_statement_type if existing else "",
                key=f"boundary_reporting_type_{period_id}",
            )
            issuer = st.text_input(
                t("boundary.wizard.reporting_entities.issuer", lang),
                value=existing.issuer_or_source if existing else "",
                key=f"boundary_reporting_issuer_{period_id}",
            )
            provenance = st.text_input(
                t("boundary.wizard.reporting_entities.provenance", lang),
                value=existing.provenance_reference if existing else "",
                key=f"boundary_reporting_provenance_{period_id}",
            )
            extra_entity = st.text_input(
                t("boundary.wizard.reporting_entities.entity_name", lang),
                value=entity_name,
                key=f"boundary_reporting_evidence_name_{period_id}",
            )
            if extra_entity.strip():
                entity_name = extra_entity

    entity = _company_entity(context)
    known_ids = tuple(item.entity_id for item in legal_entities)
    missing_subsidiaries = (
        basis == CONSOLIDATION_CONSOLIDATED and len(legal_entities) <= 1
    )
    draft = draft_reporting_entity_evidence(
        existing=existing,
        reporting_period_id=period_id,
        entity=entity,
        basis=basis,
        reporting_entity_name=str(entity_name or "").strip() or company_name,
        financial_statement_title=statement_title,
        financial_statement_type=statement_type,
        issuer_or_source=issuer,
        provenance_reference=provenance,
        included_legal_entity_ids=known_ids,
        known_legal_entity_ids=known_ids,
    )
    can_confirm = draft.confirms_reporting_entity
    if (
        basis in {CONSOLIDATION_STANDALONE, CONSOLIDATION_CONSOLIDATED}
        and not can_confirm
        and not missing_subsidiaries
    ):
        st.caption(t("boundary.wizard.reporting_entities.need_document", lang))

    def save() -> None:
        values = tuple(
            item
            for item in state.financial_reporting_entity_evidence
            if item.evidence_id != draft.evidence_id
        ) + (draft,)
        updated = _rebuild_boundaries(
            context,
            replace(state, financial_reporting_entity_evidence=values),
        )
        _save_state(context, updated)
        _go(4)

    _footer(
        key=f"boundary_reporting_{period_id}",
        lang=lang,
        primary_label=t(
            (
                "boundary.wizard.reporting_entities.confirm"
                if can_confirm
                else "boundary.wizard.reporting_entities.save_basis"
            ),
            lang,
        ),
        on_primary=save,
        on_back=lambda: _go(2),
        disabled=basis == CONSOLIDATION_UNRESOLVED,
    )


def _registration_step(
    context: BoundaryWizardContext, state: BoundarySemanticsState, lang: str
) -> None:
    title = t("boundary.wizard.registrations.title", lang)
    _render_context(title, lang, 4)
    reconciliations = list(state.registration_reconciliations)
    candidates = {item.candidate_id: item for item in state.registration_candidates}
    if not reconciliations:
        with _card(title):
            st.info(t("boundary.wizard.registrations.none", lang))
        _footer(
            key="boundary_registrations_none",
            lang=lang,
            primary_label=t("boundary.wizard.continue", lang),
            on_primary=lambda: _go(5),
            on_back=lambda: _go(_step_before_registrations(state)),
        )
        return
    index = max(
        0,
        min(
            len(reconciliations) - 1,
            int(st.session_state.get(STATE_BOUNDARY_RECONCILIATION_INDEX) or 0),
        ),
    )
    reconciliation = reconciliations[index]
    candidate = candidates[reconciliation.candidate_id]
    sites = {item.site_id: item for item in state.canonical_sites}
    with _card(title):
        st.caption(
            t(
                "boundary.wizard.counter",
                lang,
                current=index + 1,
                total=len(reconciliations),
            )
        )
        st.markdown(
            f"### {t('boundary.wizard.registrations.official_record', lang)}"
        )
        st.write(candidate.display_name)
        st.caption(
            f"{candidate.address} · {candidate.registration_identity} · "
            f"{candidate.official_source}"
        )
        st.warning(t("boundary.wizard.registrations.limit", lang))
        _support(
            why=t("boundary.wizard.registrations.why", lang),
            role=t("boundary.wizard.registrations.role", lang),
            evidence=t("boundary.wizard.registrations.evidence", lang),
            uncertain=t("boundary.wizard.registrations.uncertain", lang),
            lang=lang,
        )
        rid = reconciliation.reconciliation_id
        state_choice = st.selectbox(
            t("boundary.wizard.registrations.question", lang),
            options=RECONCILIATION_CHOICES,
            index=RECONCILIATION_CHOICES.index(reconciliation.state),
            format_func=lambda value: t(
                f"boundary.wizard.reconciliation.{value}", lang
            ),
            key=f"boundary_reconciliation_{rid}",
        )
        selected_site = NEW_SITE_OPTION
        site_name = candidate.display_name
        site_address = candidate.address
        site_confirmed = False
        basis = ""
        evidence_reference = ""
        notes = ""
        if state_choice == RECONCILIATION_MATCHED:
            matched_options = (NEW_SITE_OPTION, *sites)
            selected_site = st.selectbox(
                t("boundary.wizard.registrations.site", lang),
                options=matched_options,
                index=(
                    matched_options.index(reconciliation.canonical_site_id)
                    if reconciliation.canonical_site_id in matched_options
                    else 0
                ),
                format_func=lambda value: (
                    t("boundary.wizard.registrations.new_site", lang)
                    if not value
                    else sites[value].display_name
                ),
                key=f"boundary_reconciliation_matched_site_{rid}",
            )
        elif state_choice == RECONCILIATION_DUPLICATE and sites:
            duplicate_options = (NEW_SITE_OPTION, *sites)
            selected_site = st.selectbox(
                t("boundary.wizard.registrations.site", lang),
                options=duplicate_options,
                index=(
                    duplicate_options.index(reconciliation.canonical_site_id)
                    if reconciliation.canonical_site_id in duplicate_options
                    else 0
                ),
                format_func=lambda value: (
                    t("boundary.wizard.choose", lang)
                    if not value
                    else sites[value].display_name
                ),
                key=f"boundary_reconciliation_duplicate_site_{rid}",
            )
        spec = reconciliation_form_spec(
            state_choice,
            existing_site_count=len(sites),
            selected_site_id=selected_site,
        )
        if spec.show_no_sites_for_duplicate:
            st.warning(t("boundary.wizard.registrations.no_sites_for_duplicate", lang))
        if spec.show_new_site_fields:
            st.info(t("boundary.wizard.registrations.gov_prefill", lang))
            site_name = st.text_input(
                t("boundary.wizard.registrations.site_name", lang),
                value=candidate.display_name,
                key=f"boundary_reconciliation_name_{rid}",
            )
            site_address = st.text_input(
                t("boundary.wizard.registrations.site_address", lang),
                value=candidate.address,
                key=f"boundary_reconciliation_address_{rid}",
            )
            site_confirmed = st.checkbox(
                t("boundary.wizard.registrations.confirm_site", lang),
                value=False,
                key=f"boundary_reconciliation_confirm_{rid}",
            )
        if spec.show_other_basis:
            basis = st.text_input(
                t("boundary.wizard.registrations.other_basis", lang),
                value="",
                key=f"boundary_reconciliation_other_basis_{rid}",
            )
        if spec.show_invalid_basis:
            basis = st.text_input(
                t("boundary.wizard.registrations.invalid_basis", lang),
                value="",
                key=f"boundary_reconciliation_invalid_basis_{rid}",
            )
        if spec.show_evidence:
            evidence_reference = st.text_input(
                t("boundary.wizard.registrations.evidence_reference", lang),
                value="",
                key=f"boundary_reconciliation_evidence_{rid}_{state_choice}",
            )
        if spec.show_notes:
            notes = st.text_area(
                t("boundary.wizard.registrations.notes", lang),
                value="",
                key=f"boundary_reconciliation_notes_{rid}",
            )

    def save() -> None:
        result = apply_reconciliation_answer(
            existing=reconciliation,
            state_choice=state_choice,
            selected_site_id=selected_site,
            new_site_name=site_name,
            new_site_address=site_address,
            new_site_confirmed=site_confirmed,
            basis=basis,
            evidence_reference=evidence_reference,
            notes=notes,
            existing_sites=tuple(state.canonical_sites),
            existing_reconciliations=tuple(state.registration_reconciliations),
            workspace_id=context.workspace.workspace_id,
            company_entity_id=_company_entity(context).entity_id,
            confirmed_at=utc_now_iso(),
        )
        if result.error_key or result.reconciliation is None:
            st.error(t(result.error_key or "boundary.wizard.answer_required", lang))
            return
        canonical_sites = list(state.canonical_sites)
        if result.new_site is not None:
            canonical_sites.append(result.new_site)
        reconciliations[index] = result.reconciliation
        updated = replace(
            state,
            canonical_sites=tuple(canonical_sites),
            registration_reconciliations=tuple(reconciliations),
        )
        _save_state(context, updated)
        if index + 1 < len(reconciliations):
            st.session_state[STATE_BOUNDARY_RECONCILIATION_INDEX] = index + 1
            st.rerun()
        st.session_state[STATE_BOUNDARY_RECONCILIATION_INDEX] = 0
        _go(5)

    _footer(
        key=f"boundary_registration_{reconciliation.reconciliation_id}",
        lang=lang,
        primary_label=t("boundary.wizard.save_continue", lang),
        on_primary=save,
        on_back=lambda: _go(_step_before_registrations(state)),
        disabled=spec.primary_disabled,
    )


def _authority_evidence_card(
    context: BoundaryWizardContext,
    state: BoundarySemanticsState,
    lang: str,
    on_done: Callable[[BoundarySemanticsState], None],
) -> None:
    title = t("boundary.wizard.operations.title", lang)
    with _card(title):
        st.markdown(f"### {t('boundary.wizard.authority.title', lang)}")
        st.warning(t("boundary.wizard.authority.official_only", lang))
        st.info(t("boundary.wizard.authority.professional_review", lang))
        action = st.selectbox(
            t("boundary.wizard.authority.action", lang),
            options=("no_evidence", "add_pending"),
            format_func=lambda value: t(
                f"boundary.wizard.authority.action.{value}", lang
            ),
            key="boundary_authority_action",
        )
        authority = source_id = document_type = identifier = unit = ""
        effective_start = effective_end = provenance = note = ""
        if action == "add_pending":
            authority = st.text_input(
                t("boundary.wizard.authority.authority", lang),
                key="boundary_authority_name",
            )
            source_id = st.text_input(
                t("boundary.wizard.authority.source_id", lang),
                key="boundary_authority_source",
            )
            document_type = st.text_input(
                t("boundary.wizard.authority.document_type", lang),
                key="boundary_authority_document_type",
            )
            identifier = st.text_input(
                t("boundary.wizard.authority.identifier", lang),
                key="boundary_authority_identifier",
            )
            unit = st.text_input(
                t("boundary.wizard.authority.unit", lang),
                key="boundary_authority_unit",
            )
            effective_start = st.text_input(
                t("boundary.wizard.authority.effective_start", lang),
                key="boundary_authority_start",
            )
            effective_end = st.text_input(
                t("boundary.wizard.authority.effective_end", lang),
                key="boundary_authority_end",
            )
            provenance = st.text_input(
                t("boundary.wizard.authority.provenance", lang),
                key="boundary_authority_provenance",
            )
            note = st.text_area(
                t("boundary.wizard.authority.note", lang),
                key="boundary_authority_note",
            )

    def save() -> None:
        updated = state
        if action == "add_pending":
            if not identifier.strip():
                st.error(t("boundary.error.authority_identifier", lang))
                return
            evidence = CompetentAuthorityBoundaryEvidence(
                evidence_id=_id(
                    "authority_evidence",
                    identifier,
                    state.reporting_period.reporting_period_id,
                ),
                purpose=PURPOSE_MOENV_FACILITY,
                authority=authority,
                source_id=source_id,
                document_type=document_type,
                document_or_registration_identifier=identifier,
                described_reporting_or_operating_unit=unit,
                effective_start=effective_start,
                effective_end=effective_end,
                provenance_reference=provenance,
                verification_state=EVIDENCE_CUSTOMER_PENDING,
                supporting_note=note,
            )
            values = tuple(
                item
                for item in state.authority_evidence
                if item.evidence_id != evidence.evidence_id
            ) + (evidence,)
            updated = replace(state, authority_evidence=values)
        on_done(_rebuild_boundaries(context, updated))

    _footer(
        key="boundary_authority_evidence",
        lang=lang,
        primary_label=t("boundary.wizard.save_continue", lang),
        on_primary=save,
        on_back=lambda: _go(4),
    )


def _operations_step(
    context: BoundaryWizardContext, state: BoundarySemanticsState, lang: str
) -> None:
    title = t("boundary.wizard.operations.title", lang)
    _render_context(title, lang, 5)
    phase = str(st.session_state.get(STATE_BOUNDARY_EVIDENCE_INDEX) or "evidence")

    def after_evidence(updated: BoundarySemanticsState) -> None:
        _save_state(context, updated)
        st.session_state[STATE_BOUNDARY_EVIDENCE_INDEX] = "operating"
        st.rerun()

    has_moenv = any(
        item.purpose == PURPOSE_MOENV_FACILITY for item in state.purpose_reviews
    )
    if phase == "evidence" and has_moenv:
        _authority_evidence_card(context, state, lang, after_evidence)
        return
    state = _rebuild_boundaries(context, state)
    queues = build_boundary_review_queues(state)
    site_by_id = {item.site_id: item for item in state.canonical_sites}
    operating_index = max(
        0, int(st.session_state.get(STATE_BOUNDARY_OPERATING_INDEX) or 0)
    )
    if operating_index < len(queues.operating_facts):
        site_id, period_id = queues.operating_facts[operating_index]
        existing = next(
            (
                item
                for item in state.operating_facts
                if item.canonical_site_id == site_id
                and item.reporting_period_id == period_id
            ),
            None,
        )
        with _card(title):
            st.caption(
                t(
                    "boundary.wizard.operating_counter",
                    lang,
                    current=operating_index + 1,
                    total=len(queues.operating_facts),
                )
            )
            st.markdown(f"### {site_by_id[site_id].display_name}")
            st.info(t("boundary.wizard.operations.separate_facts", lang))
            operating_status = st.selectbox(
                t("boundary.wizard.operations.operating_question", lang),
                options=OPERATING_CHOICES,
                index=(
                    OPERATING_CHOICES.index(existing.status) if existing else 5
                ),
                format_func=lambda value: t(
                    f"boundary.wizard.operating.{value}", lang
                ),
                key=f"boundary_operating_{site_id}",
            )
            effective_date = st.text_input(
                t("boundary.wizard.operations.effective_date", lang),
                value=existing.effective_date if existing else "",
                key=f"boundary_operating_date_{site_id}",
            )
            basis = st.text_input(
                t("boundary.wizard.operations.basis", lang),
                value=existing.supporting_basis if existing else "",
                key=f"boundary_operating_basis_{site_id}",
            )

        def save_operating() -> None:
            try:
                fact = PeriodOperatingFact(
                    operating_fact_id=(
                        existing.operating_fact_id
                        if existing
                        else _id("operating_fact", site_id, period_id)
                    ),
                    canonical_site_id=site_id,
                    reporting_period_id=period_id,
                    status=operating_status,
                    effective_date=effective_date,
                    supporting_basis=basis,
                    locally_confirmed_at=utc_now_iso(),
                )
            except ValueError:
                st.error(t("boundary.error.operating_fact", lang))
                return
            facts = tuple(
                item
                for item in state.operating_facts
                if item.operating_fact_id != fact.operating_fact_id
            ) + (fact,)
            _save_state(context, replace(state, operating_facts=facts))
            st.session_state[STATE_BOUNDARY_OPERATING_INDEX] = operating_index + 1
            st.rerun()

        _footer(
            key=f"boundary_operating_{site_id}",
            lang=lang,
            primary_label=t("boundary.wizard.save_continue", lang),
            on_primary=save_operating,
            on_back=lambda: _go(4),
        )
        return
    membership_index = max(
        0, int(st.session_state.get(STATE_BOUNDARY_MEMBERSHIP_INDEX) or 0)
    )
    if membership_index < len(queues.facility_memberships):
        site_id, boundary_id = queues.facility_memberships[membership_index]
        boundary = next(
            item for item in state.boundaries if item.boundary_id == boundary_id
        )
        membership = next(
            item
            for item in boundary.facility_memberships
            if item.canonical_site_id == site_id
        )
        with _card(title):
            st.caption(
                t(
                    "boundary.wizard.membership_counter",
                    lang,
                    current=membership_index + 1,
                    total=len(queues.facility_memberships),
                )
            )
            st.markdown(
                f"### {site_by_id[site_id].display_name} · {boundary.display_name}"
            )
            st.info(t("boundary.wizard.operations.authority_membership", lang))
            choice = st.selectbox(
                t("boundary.wizard.operations.membership_question", lang),
                options=MEMBERSHIP_CHOICES,
                index=(
                    MEMBERSHIP_CHOICES.index(membership.state)
                    if membership.state in MEMBERSHIP_CHOICES
                    else 3
                ),
                format_func=lambda value: t(
                    f"boundary.wizard.membership.{value}", lang
                ),
                key=f"boundary_membership_{boundary_id}_{site_id}",
            )
            reason = st.text_input(
                t("boundary.wizard.operations.membership_reason", lang),
                value=membership.reason,
                key=f"boundary_membership_reason_{boundary_id}_{site_id}",
            )

        def save_membership() -> None:
            if (
                choice in {MEMBERSHIP_EXCLUDED, MEMBERSHIP_NOT_PERIOD}
                and not reason.strip()
            ):
                st.error(t("boundary.error.membership_reason", lang))
                return
            changed = replace(
                membership,
                state=choice,
                reason=reason,
                evidence_source=", ".join(
                    item.evidence_id for item in boundary.authority_evidence
                ),
            )
            boundaries = tuple(
                replace(
                    item,
                    facility_memberships=tuple(
                        changed
                        if member.canonical_site_id == site_id
                        else member
                        for member in item.facility_memberships
                    ),
                )
                if item.boundary_id == boundary_id
                else item
                for item in state.boundaries
            )
            _save_state(context, replace(state, boundaries=boundaries))
            st.session_state[STATE_BOUNDARY_MEMBERSHIP_INDEX] = membership_index + 1
            st.rerun()

        _footer(
            key=f"boundary_membership_{boundary_id}_{site_id}",
            lang=lang,
            primary_label=t("boundary.wizard.save_continue", lang),
            on_primary=save_membership,
            on_back=lambda: _go(4),
        )
        return
    with _card(title):
        st.success(t("boundary.wizard.operations.complete", lang))
        st.caption(
            t(
                "boundary.wizard.operations.counts",
                lang,
                sites=len(queues.operating_facts),
                memberships=len(queues.facility_memberships),
            )
        )
    _footer(
        key="boundary_operations_complete",
        lang=lang,
        primary_label=t("boundary.wizard.continue", lang),
        on_primary=lambda: _go(6),
        on_back=lambda: _go(4),
    )


def _review_step(
    context: BoundaryWizardContext,
    state: BoundarySemanticsState,
    lang: str,
    on_view_results: Callable[[], None],
) -> None:
    title = t("boundary.wizard.review.title", lang)
    _render_context(title, lang, 6)
    current = context.workspace.load_semantics_current(
        reporting_period_id=state.reporting_period.reporting_period_id
    )
    if current is not None and current.confirmation_state == CONFIRMATION_LOCAL:
        with _card(title, completion=True):
            _status(t("boundary.confirmation.locally_confirmed", lang), "success")
            st.warning(t("boundary.wizard.review.not_legal_conclusion", lang))
            st.write(
                t(
                    "boundary.wizard.review.unresolved_counts",
                    lang,
                    legal=current.legal_or_official_review_unresolved,
                    company=current.company_actionable_facts_unresolved,
                )
            )
        _footer(
            key="boundary_review_complete",
            lang=lang,
            primary_label=t("boundary.wizard.review.view_results", lang),
            on_primary=on_view_results,
            on_back=lambda: _go(5),
        )
        return
    with _card(title):
        st.write(
            t(
                "boundary.wizard.review.summary",
                lang,
                purposes=len(state.purpose_reviews),
                boundaries=len(state.boundaries),
                candidates=len(state.registration_candidates),
                sites=len(state.canonical_sites),
            )
        )
        _status(
            t(
                "boundary.wizard.review.unresolved_counts",
                lang,
                legal=state.legal_or_official_review_unresolved,
                company=state.company_actionable_facts_unresolved,
            )
        )
        st.warning(t("boundary.wizard.review.not_legal_conclusion", lang))
        for boundary in state.boundaries:
            st.markdown(
                f"- **{boundary.display_name}**"
                f"（{_purpose_label(boundary.purpose, lang)}）"
            )
        with st.container(key="cel_boundary_validation_area"):
            st.markdown(
                "<span data-cel-boundary-validation-area='1'></span>",
                unsafe_allow_html=True,
            )
            cols = st.columns(2)
            with cols[0]:
                name = st.text_input(
                    t("boundary.contact.name", lang),
                    value=state.responsible_contact_name,
                    key="boundary_review_contact_name",
                )
            with cols[1]:
                title_value = st.text_input(
                    t("boundary.contact.title", lang),
                    value=state.responsible_job_title,
                    key="boundary_review_contact_title",
                )
            st.caption(t("boundary.contact.unverified", lang))

    def confirm() -> None:
        try:
            normalized_name, normalized_title = normalize_confirmer_details(
                name, title_value
            )
            candidate = _rebuild_boundaries(
                context,
                replace(
                    state,
                    responsible_contact_name=normalized_name,
                    responsible_job_title=normalized_title,
                ),
            ).locally_confirmed()
            context.workspace.append_semantics_current(candidate)
            _save_state(context, candidate)
        except ValueError as error:
            st.error(str(error))
            return
        st.rerun()

    _footer(
        key="boundary_review",
        lang=lang,
        primary_label=t("boundary.confirm", lang),
        on_primary=confirm,
        on_back=lambda: _go(5),
    )


def _render_migration_action(
    context: BoundaryWizardContext,
    state: BoundarySemanticsState,
    lang: str,
) -> None:
    period_id = state.reporting_period.reporting_period_id
    done_key = f"boundary_migration_done_{period_id}"
    summary_key = f"boundary_migration_show_summary_{period_id}"
    if st.session_state.get(done_key):
        st.success(t("boundary.wizard.migration.done", lang))
        st.session_state[done_key] = False
        return
    if (
        context.workspace.boundary_semantics_migration_status(
            reporting_period_id=period_id
        )
        != "v1_detected"
    ):
        return
    with st.container(key="cel_boundary_migration_notice"):
        st.markdown(
            "<span data-cel-boundary-migration-notice='1'></span>",
            unsafe_allow_html=True,
        )
        st.warning(t("boundary.wizard.migration.title", lang))
        st.write(t("boundary.wizard.migration.explicit", lang))
        secondary, primary = st.columns([1, 1.2])
        with secondary:
            if st.button(
                t("boundary.wizard.migration.view_summary", lang),
                key=f"boundary_migration_summary_{period_id}",
            ):
                st.session_state[summary_key] = True
        with primary:
            run_clicked = st.button(
                t("boundary.wizard.migration.run", lang),
                key=f"boundary_migration_run_{period_id}",
                type="primary",
            )
        if st.session_state.get(summary_key):
            st.info(t("boundary.wizard.migration.summary_title", lang))
            st.write(t("boundary.wizard.migration.summary", lang))
        if is_admin_mode(st.session_state):
            preview = context.workspace.dry_run_boundary_semantics_migration(
                reporting_period_id=period_id
            )
            st.caption(
                t(
                    "boundary.wizard.migration.admin_summary",
                    lang,
                    boundaries=preview["legacy_boundary_records"],
                    registrations=preview["official_registration_candidates"],
                    categories=preview["legacy_source_category_rows_preserved"],
                )
            )
        if run_clicked:
            prepared = context.workspace.prepare_boundary_semantics_v2_migration(
                state
            )
            context.workspace.migrate_boundary_semantics_v2(
                state=prepared,
                dry_run_reviewed=True,
            )
            _save_state(context, prepared)
            st.session_state[done_key] = True
            st.session_state[summary_key] = False
            st.rerun()


def render_boundary_wizard(
    *,
    assessment: Any,
    company: CompanyMaster,
    facilities: FacilityMaster,
    repo_root: Path,
    lang: str,
    on_view_results: Callable[[], None] | None = None,
) -> bool:
    """Render v2 queues and return exact-period local completion state."""
    context = _collect_context(
        assessment=assessment,
        company=company,
        facilities=facilities,
        repo_root=repo_root,
    )
    if context is None:
        return True
    active_period_id = _active_period_id(context)
    current = (
        context.workspace.load_semantics_current(
            reporting_period_id=active_period_id
        )
        if active_period_id
        else None
    )
    complete = (
        current is not None and current.confirmation_state == CONFIRMATION_LOCAL
    )
    with st.container(key="cel_boundary_wizard_root"):
        st.markdown(
            "<span data-cel-boundary-wizard-root='1' "
            "data-cel-tour-target='company-boundary'></span>",
            unsafe_allow_html=True,
        )
        if st.session_state.get(STATE_BOUNDARY_WIZARD_DEFERRED):
            st.info(t("boundary.wizard.deferred", lang))
            if st.button(
                t("boundary.wizard.resume", lang),
                key="boundary_wizard_resume",
                type="primary",
            ):
                st.session_state[STATE_BOUNDARY_WIZARD_DEFERRED] = False
                st.rerun()
            return complete
        step = int(
            st.session_state.get(STATE_BOUNDARY_WIZARD_STEP)
            or (2 if active_period_id else 1)
        )
        if step > 1 and not active_period_id:
            step = 1
        state = None
        if step > 1:
            state = _load_state(context)
            if state is None:
                st.session_state[STATE_BOUNDARY_WIZARD_STEP] = 1
                st.rerun()
            assert state is not None
            if step == 3 and not _ifrs_step_required(state):
                step = 4
                st.session_state[STATE_BOUNDARY_WIZARD_STEP] = 4
                st.rerun()
        _render_stepper(step, lang)
        if step == 1:
            _period_step(context, lang)
            return complete
        assert state is not None
        _render_migration_action(context, state, lang)
        if step == 2:
            with onboarding_target("purpose-review"):
                _purpose_step(context, state, lang)
        elif step == 3:
            with onboarding_target("reporting-entity"):
                _reporting_entity_step(context, state, lang)
        elif step == 4:
            with onboarding_target("government-sites"):
                _registration_step(context, state, lang)
        elif step == 5:
            with onboarding_target("operations-boundary"):
                _operations_step(context, state, lang)
        else:
            with onboarding_target("confirm-boundary"):
                _review_step(context, state, lang, on_view_results or _defer)
    return complete
