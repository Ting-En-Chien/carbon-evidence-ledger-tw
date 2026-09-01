"""IFRS S1/S2 disclosure readiness checklist (data presence, not compliance)."""

from __future__ import annotations

import html
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from carbon_ledger.pipeline import PipelineRunResult
from carbon_ledger.ui.enterprise import emit_html
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.view_models import scope_kpi_states

STATUS_AVAILABLE = "available"
STATUS_MISSING = "missing"
STATUS_UNSUPPORTED = "unsupported"

S1_ITEM_IDS = (
    "reporting_period",
    "reporting_entity",
    "materiality",
    "governance",
    "strategy",
    "risk_management",
    "metrics_targets",
    "financial_connectivity",
)
S2_ITEM_IDS = (
    "physical_risk",
    "transition_risk",
    "climate_opportunity",
    "scope_1",
    "scope_2",
    "scope_3",
    "measurement_methods",
    "climate_metrics_targets",
    "scenario_analysis",
    "transition_plan",
    "assurance_evidence",
)
UNSUPPORTED_ITEM_IDS = frozenset(
    {
        "materiality",
        "governance",
        "strategy",
        "risk_management",
        "metrics_targets",
        "financial_connectivity",
        "physical_risk",
        "transition_risk",
        "climate_opportunity",
        "scope_3",
        "climate_metrics_targets",
        "scenario_analysis",
        "transition_plan",
        "assurance_evidence",
    }
)


@dataclass(frozen=True)
class ReadinessItem:
    item_id: str
    status: str


@dataclass(frozen=True)
class ReadinessSection:
    section_id: str
    items: tuple[ReadinessItem, ...]


@dataclass(frozen=True)
class IfrsReadinessView:
    sections: tuple[ReadinessSection, ...]

    def item(self, item_id: str) -> ReadinessItem | None:
        for section in self.sections:
            for item in section.items:
                if item.item_id == item_id:
                    return item
        return None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_reporting_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    if 1900 <= year <= 2100:
        return year
    return None


def _valid_reporting_year(
    company_profile: Mapping[str, Any] | None,
    assessment: Any,
) -> bool:
    candidates = []
    if isinstance(company_profile, Mapping):
        candidates.append(company_profile.get("reporting_year"))
    if assessment is not None:
        candidates.append(getattr(assessment, "reporting_year", None))
        snapshot = getattr(assessment, "company_profile_snapshot", None)
        if isinstance(snapshot, Mapping):
            candidates.append(snapshot.get("reporting_year"))
    return any(_coerce_reporting_year(raw) is not None for raw in candidates)


def _semantics_state_matches_current_period(
    state: Any,
    *,
    reporting_year: int | None = None,
    reporting_period_id: str = "",
) -> bool:
    """True only when the semantics state is the current assessment period."""
    wanted_id = _text(reporting_period_id)
    wanted_year = _coerce_reporting_year(reporting_year)
    if not wanted_id and wanted_year is None:
        return False
    try:
        period = getattr(state, "reporting_period", None)
        if period is None:
            return False
        period_id = _text(getattr(period, "reporting_period_id", ""))
        year = _coerce_reporting_year(
            getattr(period, "reporting_year_confirmed", None)
        )
        if wanted_id and period_id != wanted_id:
            return False
        if wanted_year is not None and year != wanted_year:
            return False
    except Exception:
        return False
    return True


def reporting_entity_is_confirmed(
    *,
    reporting_entity_confirmed: bool | None = None,
    reporting_entity_evidence: Iterable[Any] | None = None,
) -> bool:
    """True only when existing data explicitly confirms the reporting entity."""
    if reporting_entity_confirmed is True:
        return True
    if reporting_entity_confirmed is False:
        return False
    for item in reporting_entity_evidence or ():
        try:
            if bool(getattr(item, "confirms_reporting_entity", False)):
                return True
        except Exception:
            continue
    return False


def try_load_reporting_entity_confirmation(
    *,
    taiwan_ubn: str = "",
    entity_id: str = "",
    repo_root: Path | None = None,
    reporting_year: int | None = None,
    reporting_period_id: str = "",
) -> bool:
    """Best-effort lookup for the current period only. Other years do not count."""
    if (
        not _text(reporting_period_id)
        and _coerce_reporting_year(reporting_year) is None
    ):
        return False
    try:
        from carbon_ledger.company_workspace import (
            CompanyWorkspace,
            default_workspace_root,
        )

        workspace = CompanyWorkspace.for_company(
            root=default_workspace_root(repo_root),
            taiwan_ubn=taiwan_ubn,
            entity_id=entity_id,
        )
        states = workspace.list_semantics_periods()
    except Exception:
        return False
    for state in states:
        try:
            if not _semantics_state_matches_current_period(
                state,
                reporting_year=reporting_year,
                reporting_period_id=reporting_period_id,
            ):
                continue
            evidence = getattr(state, "financial_reporting_entity_evidence", ()) or ()
            if reporting_entity_is_confirmed(reporting_entity_evidence=evidence):
                return True
        except Exception:
            continue
    return False


def _scope_calculated(result: PipelineRunResult | None) -> dict[str, bool]:
    empty = {"scope_1": False, "scope_2": False}
    if result is None:
        return empty
    try:
        states = scope_kpi_states(result)
    except Exception:
        return empty
    found: dict[str, bool] = {}
    for key in ("scope_1", "scope_2"):
        found[key] = str((states.get(key) or {}).get("state") or "") == "calculated"
    return found


def _has_method_records(result: PipelineRunResult | None) -> bool:
    if result is None:
        return False
    try:
        calcs = result.calculation_results
        if calcs is None or getattr(calcs, "empty", True):
            return False
        if "calculation_status" not in calcs.columns:
            return False
        calculated = calcs[calcs["calculation_status"].astype(str) == "calculated"]
        if calculated.empty:
            return False
        for column in ("factor_id", "source_reference_id", "formula_id"):
            if column not in calculated.columns:
                continue
            for value in calculated[column].tolist():
                if _text(value) and _text(value).lower() not in {"nan", "<na>", "none"}:
                    return True
        if "factor_value" in calculated.columns:
            numeric = pd.to_numeric(calculated["factor_value"], errors="coerce")
            if bool(numeric.notna().any()):
                return True
    except Exception:
        return False
    return False


def _status_for(item_id: str, *, available: bool) -> str:
    if item_id in UNSUPPORTED_ITEM_IDS:
        return STATUS_UNSUPPORTED
    return STATUS_AVAILABLE if available else STATUS_MISSING


def build_ifrs_readiness_view(
    *,
    company_profile: Mapping[str, Any] | None = None,
    assessment: Any = None,
    pipeline_result: PipelineRunResult | None = None,
    reporting_entity_confirmed: bool | None = None,
    reporting_entity_evidence: Iterable[Any] | None = None,
) -> IfrsReadinessView:
    """Map existing company and calculation data into a presence checklist."""
    period_available = _valid_reporting_year(company_profile, assessment)
    entity_available = reporting_entity_is_confirmed(
        reporting_entity_confirmed=reporting_entity_confirmed,
        reporting_entity_evidence=reporting_entity_evidence,
    )
    scopes = _scope_calculated(pipeline_result)
    methods_available = _has_method_records(pipeline_result)
    availability = {
        "reporting_period": period_available,
        "reporting_entity": entity_available,
        "scope_1": scopes["scope_1"],
        "scope_2": scopes["scope_2"],
        "measurement_methods": methods_available,
    }
    s1 = tuple(
        ReadinessItem(
            item_id=item_id,
            status=_status_for(
                item_id, available=availability.get(item_id, False)
            ),
        )
        for item_id in S1_ITEM_IDS
    )
    s2 = tuple(
        ReadinessItem(
            item_id=item_id,
            status=_status_for(
                item_id, available=availability.get(item_id, False)
            ),
        )
        for item_id in S2_ITEM_IDS
    )
    return IfrsReadinessView(
        sections=(
            ReadinessSection(section_id="s1", items=s1),
            ReadinessSection(section_id="s2", items=s2),
        )
    )


def _item_copy(item: ReadinessItem, lang: str) -> tuple[str, str, str, str]:
    name = t(f"ifrs.readiness.item.{item.item_id}.name", lang)
    status = t(f"ifrs.readiness.status.{item.status}", lang)
    why = t(f"ifrs.readiness.item.{item.item_id}.why.{item.status}", lang)
    nxt = t(f"ifrs.readiness.item.{item.item_id}.next.{item.status}", lang)
    return name, status, why, nxt


def public_readiness_text(view: IfrsReadinessView, lang: str) -> str:
    """Flatten customer-visible copy for tests (no Streamlit)."""
    chunks = [
        t("ifrs.readiness.title", lang),
        t("ifrs.readiness.note", lang),
    ]
    for section in view.sections:
        chunks.append(t(f"ifrs.readiness.section.{section.section_id}", lang))
        for item in section.items:
            chunks.extend(_item_copy(item, lang))
    return "\n".join(chunks)


def render_ifrs_readiness_section(view: IfrsReadinessView, lang: str) -> None:
    """Simple list. Reuses existing outcome-row styles. No progress or animation."""
    st.markdown(f"**{t('ifrs.readiness.title', lang)}**")
    st.caption(t("ifrs.readiness.note", lang))
    for section in view.sections:
        st.markdown(t(f"ifrs.readiness.section.{section.section_id}", lang))
        for item in section.items:
            name, status, why, nxt = _item_copy(item, lang)
            emit_html(
                "<div class='cel-outcome-row' data-cel-ifrs-readiness='1'>"
                f"<p class='cel-outcome-q'>{html.escape(name)}｜"
                f"{html.escape(status)}</p>"
                f"<p class='cel-outcome-why'>{html.escape(why)}</p>"
                f"<p class='cel-outcome-why'>{html.escape(nxt)}</p>"
                "</div>"
            )
