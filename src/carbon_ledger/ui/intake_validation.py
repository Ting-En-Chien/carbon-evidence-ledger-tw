"""Session lock + exception-safe intake validation commit.

Presentation/session orchestration only. Does not change calculation arithmetic.
"""

from __future__ import annotations

from typing import Any

from carbon_ledger.intake import IntakeError, build_and_validate_intake
from carbon_ledger.intake_exceptions import hold_unknown_context_rows
from carbon_ledger.intake_mapping_memory import (
    EVENT_VALIDATION_REJECTED,
    append_provenance_event,
    remember_committed_mapping,
)
from carbon_ledger.ui.state import (
    STATE_INTAKE_RESULT,
    STATE_INTAKE_STEP,
    STATE_INTAKE_VALIDATION_ERROR,
    STATE_INTAKE_VALIDATION_REQUESTED,
    STATE_INTAKE_VALIDATION_RUNNING,
    _ss_get,
)

OUTCOME_OK = "ok"
OUTCOME_INTAKE_ERROR = "intake_error"
OUTCOME_UNEXPECTED = "unexpected"


def clear_intake_validation_lock(
    session_state: Any, *, error: Any = None
) -> None:
    """Drop REQUESTED/RUNNING so the customer can retry after a stop or error."""
    session_state[STATE_INTAKE_VALIDATION_REQUESTED] = False
    session_state[STATE_INTAKE_VALIDATION_RUNNING] = False
    session_state[STATE_INTAKE_VALIDATION_ERROR] = error


def recover_stale_intake_validation(session_state: Any) -> bool:
    """Clear a leftover RUNNING flag from an interrupted previous script run.

    Streamlit runs are serial per session: RUNNING at the start of a new run
    cannot mean work is still in flight.
    """
    if not bool(_ss_get(session_state, STATE_INTAKE_VALIDATION_RUNNING)):
        return False
    session_state[STATE_INTAKE_VALIDATION_RUNNING] = False
    return True


def execute_intake_validation(
    session_state: Any,
    *,
    table: Any,
    mapping: Any,
    metadata: Any,
    committed: Any,
    ubn: str,
    fingerprint: str,
    doc_id: str,
    progress: Any = None,
    unexpected_error: str,
) -> str:
    """Validate, hold, remember, and commit. Always leaves RUNNING=False."""
    recover_stale_intake_validation(session_state)
    session_state[STATE_INTAKE_VALIDATION_RUNNING] = True
    try:
        try:
            validated = build_and_validate_intake(
                table, mapping, metadata, progress=progress
            )
            validated = hold_unknown_context_rows(validated, mapping)
            if ubn:
                remember_committed_mapping(
                    session_state,
                    ubn=ubn,
                    fingerprint=fingerprint,
                    committed=committed,
                    source_document_id=doc_id,
                )
            session_state[STATE_INTAKE_RESULT] = validated
            session_state[STATE_INTAKE_STEP] = 3
            clear_intake_validation_lock(session_state, error=None)
            return OUTCOME_OK
        except IntakeError as exc:
            try:
                append_provenance_event(
                    session_state,
                    event=EVENT_VALIDATION_REJECTED,
                    company_ubn=ubn,
                    fingerprint=fingerprint,
                    source="validation",
                    reason=str(exc.code or ""),
                    source_document_id=doc_id,
                )
            except Exception:
                clear_intake_validation_lock(
                    session_state, error=unexpected_error
                )
                return OUTCOME_UNEXPECTED
            clear_intake_validation_lock(
                session_state, error=str(exc.message)
            )
            return OUTCOME_INTAKE_ERROR
        except Exception:
            clear_intake_validation_lock(
                session_state, error=unexpected_error
            )
            return OUTCOME_UNEXPECTED
    finally:
        session_state[STATE_INTAKE_VALIDATION_RUNNING] = False
