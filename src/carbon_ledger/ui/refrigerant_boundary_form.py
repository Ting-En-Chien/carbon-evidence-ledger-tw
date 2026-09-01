"""Streamlit form for refrigerant organizational-boundary confirmation."""

from __future__ import annotations

from typing import Any

import streamlit as st

from carbon_ledger.activity_boundary_decisions import (
    ERROR_EVIDENCE_REQUIRED,
    OUTCOME_EXCLUDED_OUTSIDE,
    OUTCOME_INCLUDED_SCOPE_1,
    OUTCOME_NEEDS_REVIEW,
    build_decision,
    decision_identity,
    validate_confirmation_input,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_BOUNDARY_CONFIRM_FLASH,
    activity_boundary_decisions_from_state,
    has_validated_uploaded_data,
    request_run_uploaded_analysis,
    save_activity_boundary_decision_in_session,
    withdraw_activity_boundary_decision_in_session,
)
from carbon_ledger.ui.view_models import pending_refrigerant_boundary_rows

_OWNER_CODES = ("company", "third_party", "unknown")
_CONTROLLER_CODES = ("company", "third_party", "shared", "unknown")
_BOUNDARY_CODES = ("inside", "outside", "unknown")
_BASIS_CODES = (
    "operational_control",
    "financial_control",
    "equity_share",
    "taiwan_statutory_facility",
    "unknown",
)


def _option_pairs(
    prefix: str, codes: tuple[str, ...], lang: str
) -> list[tuple[str, str]]:
    return [(code, t(f"{prefix}.{code}", lang)) for code in codes]


def _select(
    label: str,
    codes: tuple[str, ...],
    prefix: str,
    *,
    key: str,
    lang: str,
    default: str,
) -> str:
    pairs = _option_pairs(prefix, codes, lang)
    labels = [item_label for _, item_label in pairs]
    lookup = {item_label: code for code, item_label in pairs}
    default_code = default if default in codes else codes[-1]
    default_label = t(f"{prefix}.{default_code}", lang)
    index = labels.index(default_label) if default_label in labels else 0
    chosen = st.selectbox(label, labels, index=index, key=key)
    return lookup.get(str(chosen), "unknown")


def _default_owner(ownership: str) -> str:
    if ownership == "owned":
        return "company"
    if ownership == "third_party":
        return "third_party"
    return "unknown"


def _default_controller(ownership: str) -> str:
    if ownership == "controlled":
        return "company"
    if ownership == "third_party":
        return "third_party"
    return "unknown"


def confirmation_outcome_for_record(result: Any, record_id: str) -> str:
    ghg = getattr(result, "ghg_evaluations", None)
    if ghg is None or getattr(ghg, "empty", True):
        return OUTCOME_NEEDS_REVIEW
    matched = ghg[ghg["record_id"].astype(str) == str(record_id)]
    if matched.empty:
        return OUTCOME_NEEDS_REVIEW
    row = matched.iloc[0]
    mapping = str(row.get("mapping_status") or "").strip()
    scope = str(row.get("ghg_scope") or "").strip()
    if mapping == "outside_boundary":
        return OUTCOME_EXCLUDED_OUTSIDE
    if mapping == "mapped" and scope == "scope_1":
        return OUTCOME_INCLUDED_SCOPE_1
    return OUTCOME_NEEDS_REVIEW


def render_confirmation_flash(result: Any, lang: str) -> None:
    flash = st.session_state.get(STATE_BOUNDARY_CONFIRM_FLASH) or {}
    record_id = str(flash.get("record_id") or "").strip()
    if not record_id or result is None:
        return
    outcome = confirmation_outcome_for_record(result, record_id)
    message = t(f"boundary.outcome.{outcome}", lang)
    if outcome == OUTCOME_INCLUDED_SCOPE_1:
        st.success(message)
    elif outcome == OUTCOME_EXCLUDED_OUTSIDE:
        st.info(message)
    else:
        st.warning(message)
    st.session_state[STATE_BOUNDARY_CONFIRM_FLASH] = None


def render_refrigerant_boundary_confirmation(
    result: Any,
    lang: str,
    *,
    record_filter: str | None = None,
) -> None:
    if result is None:
        return
    pending = pending_refrigerant_boundary_rows(result, lang)
    if record_filter:
        pending = [row for row in pending if row["record_id"] == record_filter]
    if not pending:
        return
    st.markdown(f"**{t('boundary.confirm.title', lang)}**")
    st.caption(t("boundary.confirm.help", lang))
    decisions = activity_boundary_decisions_from_state(st.session_state)
    by_key = {
        decision_identity(
            item.record_id, item.reporting_year, item.reporting_period_id
        ): item
        for item in decisions
        if not item.withdrawn
    }
    for row in pending:
        record_id = str(row["record_id"])
        year = row.get("reporting_year")
        period_id = str(row.get("reporting_period_id") or "")
        existing = (
            by_key.get(decision_identity(record_id, int(year), period_id))
            if year is not None
            else None
        )
        title = f"{record_id} · {row.get('refrigerant_code') or '—'}"
        with st.expander(title, expanded=True):
            st.markdown(f"**{t('boundary.confirm.record_id', lang)}**")
            st.code(record_id)
            cols = st.columns(3)
            with cols[0]:
                st.markdown(f"**{t('boundary.confirm.refrigerant', lang)}**")
                st.write(row.get("refrigerant_code") or "—")
            with cols[1]:
                st.markdown(f"**{t('boundary.confirm.quantity', lang)}**")
                quantity = row.get("activity_value")
                unit = row.get("unit") or "kg"
                st.write(f"{quantity} {unit}" if quantity is not None else "—")
            with cols[2]:
                st.markdown(f"**{t('boundary.confirm.tco2e', lang)}**")
                tco2e = row.get("calculated_tco2e")
                st.write(f"{tco2e:.6g}" if tco2e is not None else "—")
            st.markdown(f"**{t('boundary.confirm.current_mapping', lang)}**")
            reason = row.get("rationale") or row.get("ghg_label") or "—"
            st.write(f"{row.get('ghg_label') or '—'} — {reason}")
            owner_default = (
                existing.legal_owner
                if existing is not None
                else _default_owner(str(row.get("ownership_control") or ""))
            )
            controller_default = (
                existing.operational_controller
                if existing is not None
                else _default_controller(str(row.get("ownership_control") or ""))
            )
            boundary_default = (
                existing.organizational_boundary_status
                if existing is not None
                else (str(row.get("organizational_boundary_status") or "unknown"))
            )
            if boundary_default not in _BOUNDARY_CODES:
                boundary_default = "unknown"
            basis_default = (
                existing.boundary_basis if existing is not None else "unknown"
            )
            legal_owner = _select(
                t("boundary.confirm.legal_owner", lang),
                _OWNER_CODES,
                "boundary.owner",
                key=f"rf_owner_{record_id}",
                lang=lang,
                default=owner_default,
            )
            controller = _select(
                t("boundary.confirm.controller", lang),
                _CONTROLLER_CODES,
                "boundary.controller",
                key=f"rf_ctrl_{record_id}",
                lang=lang,
                default=controller_default,
            )
            boundary = _select(
                t("boundary.confirm.boundary_status", lang),
                _BOUNDARY_CODES,
                "boundary.status",
                key=f"rf_bound_{record_id}",
                lang=lang,
                default=boundary_default,
            )
            basis = _select(
                t("boundary.confirm.boundary_basis", lang),
                _BASIS_CODES,
                "boundary.basis",
                key=f"rf_basis_{record_id}",
                lang=lang,
                default=basis_default,
            )
            evidence = st.text_input(
                t("boundary.confirm.evidence", lang),
                value=existing.evidence_reference if existing is not None else "",
                key=f"rf_evidence_{record_id}",
            )
            rationale = st.text_area(
                t("boundary.confirm.rationale", lang),
                value=existing.rationale if existing is not None else "",
                key=f"rf_rationale_{record_id}",
            )
            error_box = st.empty()
            save_col, withdraw_col = st.columns(2)
            with save_col:
                save_clicked = st.button(
                    t("boundary.confirm.save", lang),
                    type="primary",
                    key=f"rf_save_{record_id}",
                )
            withdraw_clicked = False
            if existing is not None:
                with withdraw_col:
                    withdraw_clicked = st.button(
                        t("boundary.confirm.withdraw", lang),
                        key=f"rf_withdraw_{record_id}",
                    )
            if save_clicked:
                _handle_save(
                    lang=lang,
                    record_id=record_id,
                    reporting_year=year,
                    reporting_period_id=str(row.get("reporting_period_id") or ""),
                    legal_owner=legal_owner,
                    controller=controller,
                    boundary=boundary,
                    basis=basis,
                    evidence=evidence,
                    rationale=rationale,
                    error_box=error_box,
                )
            if withdraw_clicked and year is not None:
                withdraw_activity_boundary_decision_in_session(
                    st.session_state,
                    record_id=record_id,
                    reporting_year=int(year),
                    reporting_period_id=period_id,
                )
                st.session_state[STATE_BOUNDARY_CONFIRM_FLASH] = {
                    "record_id": record_id
                }
                request_run_uploaded_analysis(st.session_state)
                st.rerun()


def _handle_save(
    *,
    lang: str,
    record_id: str,
    reporting_year: Any,
    reporting_period_id: str,
    legal_owner: str,
    controller: str,
    boundary: str,
    basis: str,
    evidence: str,
    rationale: str,
    error_box: Any,
) -> None:
    if not has_validated_uploaded_data(st.session_state):
        error_box.error(t("boundary.confirm.no_upload", lang))
        return
    errors = validate_confirmation_input(
        record_id=record_id,
        reporting_year=reporting_year,
        legal_owner=legal_owner,
        operational_controller=controller,
        organizational_boundary_status=boundary,
        boundary_basis=basis,
        evidence_reference=evidence,
    )
    if ERROR_EVIDENCE_REQUIRED in errors:
        error_box.error(t("boundary.confirm.evidence_required", lang))
        return
    if errors:
        error_box.error(t("boundary.confirm.incomplete", lang))
        return
    decision = build_decision(
        record_id=record_id,
        reporting_year=int(reporting_year),
        reporting_period_id=reporting_period_id,
        legal_owner=legal_owner,
        operational_controller=controller,
        organizational_boundary_status=boundary,
        boundary_basis=basis,
        evidence_reference=evidence,
        rationale=rationale,
    )
    save_activity_boundary_decision_in_session(st.session_state, decision)
    st.session_state[STATE_BOUNDARY_CONFIRM_FLASH] = {"record_id": record_id}
    request_run_uploaded_analysis(st.session_state)
    st.rerun()
