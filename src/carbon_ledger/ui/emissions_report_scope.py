"""Read-only company / reporting-period / boundary snapshot for the PDF.

Presentation only. Does not confirm drafts, alter memberships, or change
inventory-boundary semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from carbon_ledger.company_workspace import (
    CompanyWorkspace,
    default_workspace_root,
)
from carbon_ledger.inventory_boundary import (
    MEMBERSHIP_EXCLUDED,
    MEMBERSHIP_INCLUDED,
    MEMBERSHIP_NOT_PERIOD,
    MEMBERSHIP_PENDING,
    MEMBERSHIP_UNCERTAIN,
    InventoryBoundary,
    ReportingPeriod,
)
from carbon_ledger.legal_entity import CONFIRMATION_LOCAL
from carbon_ledger.ui.i18n import DEFAULT_LANG, t
from carbon_ledger.ui.state import (
    REPO_ROOT,
    _ss_get,
    get_applicability_assessment,
    get_company_master_mapping,
    get_company_profile_mapping,
    get_facility_master_mapping,
)


@dataclass(frozen=True)
class ConfirmedReportScope:
    company_name: str
    reporting_period: ReportingPeriod
    entity_name: str
    entities_included: tuple[str, ...]
    entities_pending: tuple[str, ...]
    sites_included: tuple[str, ...]
    sites_pending: tuple[str, ...]
    exclusions: tuple[tuple[str, str], ...]
    boundary_summary: str
    from_current: bool


_PLACEHOLDER_NAMES = frozenset(
    {
        "尚未提供",
        "Not yet provided",
        "Not-yet-provided",
        "company",
        "Company",
    }
)


def _confirmed_company_master(session_state: Any) -> dict[str, Any]:
    """Return CompanyMaster only when the customer has confirmed it."""
    master = get_company_master_mapping(session_state)
    if not str(master.get("customer_confirmed_at") or "").strip():
        return {}
    name = str(master.get("legal_name") or master.get("company_name") or "").strip()
    if not name or name in _PLACEHOLDER_NAMES:
        return {}
    ubn = str(master.get("unified_business_number") or "").strip()
    entity_id = str(master.get("company_id") or "").strip()
    if not ubn and not entity_id:
        return {}
    return master


def confirmed_company_display_name(session_state: Any) -> str:
    """Return the customer-confirmed company name, or empty if identity is missing."""
    master = _confirmed_company_master(session_state)
    if not master:
        return ""
    return str(master.get("legal_name") or master.get("company_name") or "").strip()


def _workspace_for_session(session_state: Any) -> CompanyWorkspace | None:
    master = _confirmed_company_master(session_state)
    if not master:
        return None
    ubn = str(master.get("unified_business_number") or "").strip()
    entity_id = str(master.get("company_id") or "").strip()
    root = default_workspace_root(Path(REPO_ROOT))
    try:
        if ubn:
            return CompanyWorkspace.for_company(root=root, taiwan_ubn=ubn)
        if entity_id:
            return CompanyWorkspace.for_company(root=root, entity_id=entity_id)
    except ValueError:
        return None
    return None


def _period_ids(workspace: CompanyWorkspace) -> list[str]:
    periods_dir = workspace.path / "periods"
    if not periods_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in periods_dir.iterdir()
        if path.is_dir() and path.name
    )


def _period_is_confirmed_current(period: ReportingPeriod | None) -> bool:
    return bool(
        period is not None
        and period.confirmation_state == CONFIRMATION_LOCAL
        and period.is_explicitly_confirmed
    )


def _confirmed_periods_from_workspace(
    workspace: CompanyWorkspace,
) -> dict[str, ReportingPeriod]:
    found: dict[str, ReportingPeriod] = {}
    for period_id in _period_ids(workspace):
        period: ReportingPeriod | None = None
        try:
            state = workspace.load_semantics_current(reporting_period_id=period_id)
        except (OSError, ValueError, FileNotFoundError):
            state = None
        if (
            state is not None
            and state.confirmation_state == CONFIRMATION_LOCAL
            and _period_is_confirmed_current(state.reporting_period)
        ):
            period = state.reporting_period
        else:
            try:
                currents = workspace.list_current(reporting_period_id=period_id)
            except (OSError, ValueError, FileNotFoundError):
                currents = []
            for boundary in currents:
                if (
                    boundary.confirmation_state == CONFIRMATION_LOCAL
                    and _period_is_confirmed_current(boundary.reporting_period)
                ):
                    period = boundary.reporting_period
                    break
        if period is not None:
            found[period.reporting_period_id] = period
    return found


def _session_keys(session_state: Any) -> list[str]:
    try:
        return [str(key) for key in session_state.keys()]
    except Exception:  # noqa: BLE001 - AppTest proxies vary
        return []


def _hinted_reporting_years(session_state: Any) -> list[int]:
    years: list[int] = []
    seen: set[int] = set()

    def _add(raw: Any) -> None:
        try:
            year = int(raw or 0)
        except (TypeError, ValueError):
            return
        if year and year not in seen:
            seen.add(year)
            years.append(year)

    _add(_ss_get(session_state, "boundary_wizard_period_year"))
    assessment = get_applicability_assessment(session_state)
    _add(getattr(assessment, "reporting_year", 0))
    profile = get_company_profile_mapping(session_state)
    _add(profile.get("reporting_year"))
    return years


def _session_active_period_ids(
    session_state: Any, workspace: CompanyWorkspace
) -> list[str]:
    prefix = f"boundary_active_period_{workspace.workspace_id}_"
    found: list[str] = []
    seen: set[str] = set()
    for key in _session_keys(session_state):
        if not key.startswith(prefix):
            continue
        value = str(_ss_get(session_state, key, "") or "").strip()
        if value and value not in seen:
            seen.add(value)
            found.append(value)
    probe_years = list(_hinted_reporting_years(session_state))
    probe_years.extend(range(2000, 2036))
    for year in probe_years:
        value = str(_ss_get(session_state, f"{prefix}{year}", "") or "").strip()
        if value and value not in seen:
            seen.add(value)
            found.append(value)
    return found


def _preferred_active_period_id(
    session_state: Any, workspace: CompanyWorkspace
) -> str | None:
    prefix = f"boundary_active_period_{workspace.workspace_id}_"
    for year in _hinted_reporting_years(session_state):
        value = str(_ss_get(session_state, f"{prefix}{year}", "") or "").strip()
        if value:
            return value
    ids = _session_active_period_ids(session_state, workspace)
    if len(ids) == 1:
        return ids[0]
    return None


def confirmed_reporting_period(session_state: Any) -> ReportingPeriod | None:
    """Return the active current/confirmed ReportingPeriod, if it can be known."""
    workspace = _workspace_for_session(session_state)
    if workspace is None:
        return None
    confirmed = _confirmed_periods_from_workspace(workspace)
    if not confirmed:
        return None
    active_ids = _session_active_period_ids(session_state, workspace)
    preferred = _preferred_active_period_id(session_state, workspace)
    if preferred:
        period = confirmed.get(preferred)
        if _period_is_confirmed_current(period):
            return period
        return None
    if active_ids:
        return None
    if len(confirmed) == 1:
        return next(iter(confirmed.values()))
    return None


def has_confirmed_company_and_reporting_period(session_state: Any) -> bool:
    return bool(
        confirmed_company_display_name(session_state)
        and confirmed_reporting_period(session_state) is not None
    )


def _site_label(
    facility_id: str,
    *,
    facilities: Mapping[str, Any] | None,
    canonical_names: Mapping[str, str],
) -> str:
    if facility_id in canonical_names:
        return canonical_names[facility_id]
    records = []
    if isinstance(facilities, Mapping):
        records = list(facilities.get("records") or [])
    for item in records:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("facility_id") or "") == facility_id:
            name = str(item.get("display_name") or "").strip()
            if name:
                return name
    return facility_id


def _entity_label(entity_id: str, boundary: InventoryBoundary) -> str:
    for entity in boundary.legal_entities:
        if entity.entity_id == entity_id:
            return entity.legal_name
    return entity_id


def _exclusion_reason(membership, lang: str) -> str:
    reason = str(getattr(membership, "reason", "") or "").strip()
    if reason:
        return reason
    return t("report.still_pending", lang)


def _collect_from_boundaries(
    boundaries: list[InventoryBoundary],
    *,
    lang: str,
    facilities: Mapping[str, Any] | None,
    canonical_names: Mapping[str, str],
    treat_as_current: bool,
) -> tuple[
    list[str],
    list[str],
    list[str],
    list[str],
    list[tuple[str, str]],
    str,
]:
    entities_included: list[str] = []
    entities_pending: list[str] = []
    sites_included: list[str] = []
    sites_pending: list[str] = []
    exclusions: list[tuple[str, str]] = []
    summaries: list[str] = []
    pending_states = {MEMBERSHIP_PENDING, MEMBERSHIP_UNCERTAIN}
    for boundary in boundaries:
        current = (
            treat_as_current
            and boundary.confirmation_state == CONFIRMATION_LOCAL
            and boundary.reporting_period.is_explicitly_confirmed
        )
        purpose_key = f"boundary.purpose.{boundary.purpose}"
        purpose_label = t(purpose_key, lang)
        if purpose_label == purpose_key:
            purpose_label = boundary.display_name or boundary.purpose
        if current:
            summaries.append(
                t("report.boundary.confirmed_purpose", lang, purpose=purpose_label)
            )
        else:
            summaries.append(
                t("report.boundary.draft_purpose", lang, purpose=purpose_label)
            )
        names = {
            **canonical_names,
        }
        for membership in boundary.entity_memberships:
            label = _entity_label(membership.entity_id, boundary)
            if current and membership.state == MEMBERSHIP_INCLUDED:
                entities_included.append(label)
            elif membership.state in pending_states or not current:
                entities_pending.append(label)
            elif current and membership.state in {
                MEMBERSHIP_EXCLUDED,
                MEMBERSHIP_NOT_PERIOD,
            }:
                exclusions.append((label, _exclusion_reason(membership, lang)))
        for membership in boundary.facility_memberships:
            label = _site_label(
                membership.facility_id,
                facilities=facilities,
                canonical_names=names,
            )
            if current and membership.state == MEMBERSHIP_INCLUDED:
                sites_included.append(label)
            elif membership.state in pending_states or not current:
                sites_pending.append(label)
            elif current and membership.state in {
                MEMBERSHIP_EXCLUDED,
                MEMBERSHIP_NOT_PERIOD,
            }:
                exclusions.append((label, _exclusion_reason(membership, lang)))
        approach = str(boundary.organizational_approach or "").strip()
        if current and approach:
            summaries.append(approach)
    return (
        entities_included,
        entities_pending,
        sites_included,
        sites_pending,
        exclusions,
        "；".join(dict.fromkeys(summaries)),
    )


def _exclusive_status_sets(
    included: list[str] | tuple[str, ...],
    pending: list[str] | tuple[str, ...],
    exclusions: list[tuple[str, str]] | tuple[tuple[str, str], ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[str, str], ...]]:
    """Current confirmed status wins; a name may appear in only one bucket."""
    included_u = tuple(dict.fromkeys(included))
    included_set = set(included_u)
    exclusions_u = tuple(
        (name, reason)
        for name, reason in dict.fromkeys(exclusions)
        if name not in included_set
    )
    excluded_set = {name for name, _reason in exclusions_u}
    pending_u = tuple(
        name
        for name in dict.fromkeys(pending)
        if name not in included_set and name not in excluded_set
    )
    return included_u, pending_u, exclusions_u


def _list_drafts(
    workspace: CompanyWorkspace, reporting_period_id: str
) -> list[InventoryBoundary]:
    drafts_dir = (
        workspace.path / "periods" / reporting_period_id / "boundaries" / "drafts"
    )
    if not drafts_dir.is_dir():
        return []
    drafts: list[InventoryBoundary] = []
    for path in sorted(drafts_dir.glob("*.json")):
        try:
            loaded = workspace.load_draft(
                reporting_period_id=reporting_period_id,
                boundary_id=path.stem,
            )
        except (OSError, ValueError, FileNotFoundError):
            continue
        if loaded is not None:
            drafts.append(loaded)
    return drafts


def load_confirmed_report_scope(
    session_state: Any,
    *,
    lang: str = DEFAULT_LANG,
) -> ConfirmedReportScope | None:
    """Assemble PDF scope from current/confirmed workspace records only."""
    company_name = confirmed_company_display_name(session_state)
    workspace = _workspace_for_session(session_state)
    period = confirmed_reporting_period(session_state)
    if not company_name or period is None or workspace is None:
        return None
    period_id = period.reporting_period_id
    canonical_names: dict[str, str] = {}
    current_boundaries: list[InventoryBoundary] = []
    try:
        state = workspace.load_semantics_current(reporting_period_id=period_id)
    except (OSError, ValueError, FileNotFoundError):
        state = None
    if (
        state is not None
        and state.confirmation_state == CONFIRMATION_LOCAL
        and state.reporting_period.is_explicitly_confirmed
    ):
        current_boundaries.extend(
            [
                boundary
                for boundary in state.boundaries
                if boundary.confirmation_state == CONFIRMATION_LOCAL
            ]
        )
        for site in state.canonical_sites:
            canonical_names[site.site_id] = site.display_name
    try:
        current_boundaries.extend(
            [
                boundary
                for boundary in workspace.list_current(reporting_period_id=period_id)
                if boundary.confirmation_state == CONFIRMATION_LOCAL
            ]
        )
    except (OSError, ValueError, FileNotFoundError):
        pass
    unique: dict[str, InventoryBoundary] = {}
    for boundary in current_boundaries:
        unique[boundary.boundary_id] = boundary
    current_boundaries = list(unique.values())
    current_ids = {boundary.boundary_id for boundary in current_boundaries}
    facilities = get_facility_master_mapping(session_state)
    included_e, pending_e, included_s, pending_s, exclusions, summary = (
        _collect_from_boundaries(
            current_boundaries,
            lang=lang,
            facilities=facilities,
            canonical_names=canonical_names,
            treat_as_current=True,
        )
    )
    drafts = [
        draft
        for draft in _list_drafts(workspace, period_id)
        if draft.boundary_id not in current_ids
    ]
    _ie, draft_e, _is, draft_s, _ex, _sum = _collect_from_boundaries(
        drafts,
        lang=lang,
        facilities=facilities,
        canonical_names=canonical_names,
        treat_as_current=False,
    )
    pending_e = list(dict.fromkeys([*pending_e, *draft_e]))
    pending_s = list(dict.fromkeys([*pending_s, *draft_s]))
    included_e, pending_e, exclusions = _exclusive_status_sets(
        included_e, pending_e, exclusions
    )
    included_s, pending_s, exclusions = _exclusive_status_sets(
        included_s, pending_s, exclusions
    )
    if _sum:
        summary = "；".join(
            part for part in dict.fromkeys([summary, _sum]) if part
        )
    if not summary:
        summary = t("report.boundary.confirmed_company", lang, company=company_name)
    return ConfirmedReportScope(
        company_name=company_name,
        reporting_period=period,
        entity_name=company_name,
        entities_included=included_e,
        entities_pending=pending_e,
        sites_included=included_s,
        sites_pending=pending_s,
        exclusions=exclusions,
        boundary_summary=summary,
        from_current=True,
    )
