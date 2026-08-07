"""Session-state helpers for the Streamlit demonstration workspace.

Keeps one PipelineRunResult in memory and avoids re-running the pipeline on
ordinary page navigation or language changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from carbon_ledger.pipeline import PipelineRunResult, run_demo_pipeline
from carbon_ledger.ui.i18n import DEFAULT_LANG, STATE_LANGUAGE, normalize_lang
from carbon_ledger.ui.tutorial import (
    STATE_TUTORIAL_OPEN_COUNT,
    ensure_tutorial_state,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_ID = "ui_demo"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")

STATE_RESULT = "pipeline_result"
STATE_INCLUDE_GHG = "include_ghg"
STATE_INCLUDE_CBAM = "include_cbam"
STATE_INCLUDE_IFRS = "include_ifrs_s2"
STATE_RUN_ID = "run_id"
STATE_LAST_CONFIG = "last_run_config"
STATE_INITIALIZED = "ui_initialized"
STATE_ERROR = "ui_error"
STATE_FOCUS_RECORD = "focus_record_id"
STATE_RUN_ANALYSIS_REQUEST = "run_analysis_request"

# Phase 9A structured intake (session-only; never written to disk)
STATE_INTAKE_FILE_HASH = "uploaded_file_hash"
STATE_INTAKE_FILE_NAME = "uploaded_file_name"
STATE_INTAKE_TABLE = "uploaded_table"
STATE_INTAKE_BYTES = "uploaded_file_bytes"
STATE_INTAKE_SHEET = "intake_selected_sheet"
STATE_INTAKE_MAPPING = "intake_mapping"
STATE_INTAKE_METADATA = "intake_metadata"
STATE_INTAKE_RESULT = "validated_intake_result"
STATE_INTAKE_STEP = "intake_wizard_step"


def _default_adapter_flags() -> dict[str, bool]:
    return {
        STATE_INCLUDE_GHG: True,
        STATE_INCLUDE_CBAM: True,
        STATE_INCLUDE_IFRS: True,
    }


def get_language(session_state: Any) -> str:
    """Return the active UI language code."""
    return normalize_lang(session_state.get(STATE_LANGUAGE, DEFAULT_LANG))


def set_language(session_state: Any, lang: str) -> None:
    """Store UI language without touching pipeline results."""
    session_state[STATE_LANGUAGE] = normalize_lang(lang)


def initialize_ui_state(session_state: Any, *, force: bool = False) -> None:
    """Ensure session defaults exist and run the demo pipeline once."""
    defaults = _default_adapter_flags()
    if STATE_LANGUAGE not in session_state:
        session_state[STATE_LANGUAGE] = DEFAULT_LANG
    else:
        session_state[STATE_LANGUAGE] = normalize_lang(
            session_state[STATE_LANGUAGE]
        )
    if STATE_INCLUDE_GHG not in session_state:
        session_state[STATE_INCLUDE_GHG] = defaults[STATE_INCLUDE_GHG]
    if STATE_INCLUDE_CBAM not in session_state:
        session_state[STATE_INCLUDE_CBAM] = defaults[STATE_INCLUDE_CBAM]
    if STATE_INCLUDE_IFRS not in session_state:
        session_state[STATE_INCLUDE_IFRS] = defaults[STATE_INCLUDE_IFRS]
    if STATE_RUN_ID not in session_state:
        session_state[STATE_RUN_ID] = DEFAULT_RUN_ID
    if STATE_ERROR not in session_state:
        session_state[STATE_ERROR] = None
    if STATE_FOCUS_RECORD not in session_state:
        session_state[STATE_FOCUS_RECORD] = None
    if STATE_RUN_ANALYSIS_REQUEST not in session_state:
        session_state[STATE_RUN_ANALYSIS_REQUEST] = False
    if STATE_INTAKE_STEP not in session_state:
        session_state[STATE_INTAKE_STEP] = 1
    if STATE_TUTORIAL_OPEN_COUNT not in session_state:
        session_state[STATE_TUTORIAL_OPEN_COUNT] = 0
    ensure_tutorial_state(session_state)

    already = bool(session_state.get(STATE_INITIALIZED)) and (
        get_current_result(session_state) is not None
    )
    if already and not force:
        return

    run_analysis(
        session_state,
        include_ghg=bool(session_state[STATE_INCLUDE_GHG]),
        include_cbam=bool(session_state[STATE_INCLUDE_CBAM]),
        include_ifrs_s2=bool(session_state[STATE_INCLUDE_IFRS]),
        run_id=str(session_state[STATE_RUN_ID]),
    )
    session_state[STATE_INITIALIZED] = True


def run_analysis(
    session_state: Any,
    *,
    include_ghg: bool,
    include_cbam: bool,
    include_ifrs_s2: bool,
    run_id: str = DEFAULT_RUN_ID,
    repo_root: Path | None = None,
) -> PipelineRunResult:
    """Execute the reproducible demo pipeline and store the result."""
    session_state[STATE_ERROR] = None
    try:
        result = run_demo_pipeline(
            Path(repo_root) if repo_root is not None else REPO_ROOT,
            run_id=run_id,
            ingested_at=FIXED_INGESTED_AT,
            include_ghg=include_ghg,
            include_cbam=include_cbam,
            include_ifrs_s2=include_ifrs_s2,
        )
    except Exception as exc:  # noqa: BLE001 - surface as UI error text
        session_state[STATE_ERROR] = str(exc)
        raise

    session_state[STATE_RESULT] = result
    session_state[STATE_INCLUDE_GHG] = include_ghg
    session_state[STATE_INCLUDE_CBAM] = include_cbam
    session_state[STATE_INCLUDE_IFRS] = include_ifrs_s2
    session_state[STATE_RUN_ID] = result.run_id
    session_state[STATE_LAST_CONFIG] = {
        "run_id": result.run_id,
        "ingested_at": "2024-02-01T00:00:00+00:00",
        "include_ghg": include_ghg,
        "include_cbam": include_cbam,
        "include_ifrs_s2": include_ifrs_s2,
    }
    session_state[STATE_INITIALIZED] = True
    session_state[STATE_RUN_ANALYSIS_REQUEST] = False
    return result


def get_current_result(session_state: Any) -> PipelineRunResult | None:
    """Return the stored pipeline result, if any."""
    result = session_state.get(STATE_RESULT)
    if result is None:
        return None
    if not isinstance(result, PipelineRunResult):
        return None
    return result


def get_adapter_flags(session_state: Any) -> dict[str, bool]:
    """Return the currently selected analysis-module flags."""
    return {
        "include_ghg": bool(session_state.get(STATE_INCLUDE_GHG, True)),
        "include_cbam": bool(session_state.get(STATE_INCLUDE_CBAM, True)),
        "include_ifrs_s2": bool(session_state.get(STATE_INCLUDE_IFRS, True)),
    }


def get_ui_error(session_state: Any) -> str | None:
    """Return the last user-facing analysis error, if any."""
    value = session_state.get(STATE_ERROR)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def set_focus_record(session_state: Any, record_id: str | None) -> None:
    """Store a record ID for Activity Explorer deep-links."""
    session_state[STATE_FOCUS_RECORD] = record_id


def get_focus_record(session_state: Any) -> str | None:
    """Return the focused record ID, if any."""
    value = session_state.get(STATE_FOCUS_RECORD)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def request_run_analysis(session_state: Any) -> None:
    """Ask the shell to run analysis on the next sidebar pass."""
    session_state[STATE_RUN_ANALYSIS_REQUEST] = True


def clear_intake_state(session_state: Any) -> None:
    """Clear Phase 9A intake session values without touching demo results."""
    for key in (
        STATE_INTAKE_FILE_HASH,
        STATE_INTAKE_FILE_NAME,
        STATE_INTAKE_TABLE,
        STATE_INTAKE_BYTES,
        STATE_INTAKE_SHEET,
        STATE_INTAKE_MAPPING,
        STATE_INTAKE_METADATA,
        STATE_INTAKE_RESULT,
        STATE_INTAKE_STEP,
    ):
        if key in session_state:
            del session_state[key]


def get_intake_result(session_state: Any) -> Any | None:
    """Return the validated intake result stored in session, if any."""
    return session_state.get(STATE_INTAKE_RESULT)
