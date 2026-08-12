"""Session-state helpers for the Streamlit demonstration workspace.

Keeps one PipelineRunResult in memory and avoids re-running the pipeline on
ordinary page navigation or language changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from carbon_ledger.pipeline import (
    PipelineRunResult,
    run_demo_pipeline,
    run_uploaded_pipeline,
)
from carbon_ledger.ui.i18n import DEFAULT_LANG, STATE_LANGUAGE, normalize_lang
from carbon_ledger.ui.tutorial import (
    STATE_TUTORIAL_OPEN_COUNT,
    ensure_tutorial_state,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUN_ID = "ui_demo"
UPLOADED_RUN_ID = "ui_uploaded"
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")

ANALYSIS_SOURCE_DEMO = "demo"
ANALYSIS_SOURCE_UPLOADED = "uploaded"

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
STATE_RUN_UPLOADED_REQUEST = "run_uploaded_analysis_request"
STATE_NAVIGATE_TO_RESULTS = "navigate_to_results_after_analysis"
STATE_RESULT_REVEAL_PENDING = "result_reveal_pending_token"
STATE_LAST_ANIMATED_RESULT = "last_animated_result_token"
STATE_HERO_EMISSIONS_PLAY = "hero_emissions_play_token"

STATE_ANALYSIS_SOURCE = "analysis_data_source"
STATE_ANALYSIS_FILE_NAME = "analysis_source_file_name"
STATE_ANALYSIS_PERIOD_START = "analysis_period_start"
STATE_ANALYSIS_PERIOD_END = "analysis_period_end"
STATE_ANALYSIS_ACTIVITY_COUNT = "analysis_activity_count"
STATE_UPLOADED_ANALYSIS_COMPLETED = "uploaded_analysis_completed"

# Phase 9A structured intake (session-only; never written to disk)
STATE_INTAKE_FILE_HASH = "uploaded_file_hash"
STATE_INTAKE_FILE_NAME = "uploaded_file_name"
STATE_INTAKE_TABLE = "uploaded_table"
STATE_INTAKE_BYTES = "uploaded_file_bytes"
STATE_INTAKE_SHEET = "intake_selected_sheet"
STATE_INTAKE_SHEET_CONFIRMED = "intake_sheet_confirmed"
STATE_INTAKE_HEADER_ROW = "intake_header_row"
STATE_INTAKE_HEADER_CONFIRMED = "intake_header_confirmed"
STATE_INTAKE_YEAR_MONTH_CONFIRMED = "intake_year_month_confirmed"
STATE_INTAKE_SHOW_MAPPING_EDITOR = "intake_show_mapping_editor"
STATE_INTAKE_MAPPING = "intake_mapping"
STATE_INTAKE_METADATA = "intake_metadata"
STATE_INTAKE_RESULT = "validated_intake_result"
STATE_INTAKE_STEP = "intake_wizard_step"


def _ss_get(session_state: Any, key: str, default: Any = None) -> Any:
    """Read session state without relying on SessionState.get (AppTest-safe)."""
    try:
        if key in session_state:
            return session_state[key]
    except Exception:  # noqa: BLE001 - AppTest proxies vary
        pass
    try:
        return session_state[key]
    except Exception:  # noqa: BLE001
        return default


def _default_adapter_flags() -> dict[str, bool]:
    return {
        STATE_INCLUDE_GHG: True,
        # V1 product hides CBAM; backend capability remains for future V2.
        STATE_INCLUDE_CBAM: False,
        STATE_INCLUDE_IFRS: True,
    }


def get_language(session_state: Any) -> str:
    """Return the active UI language code."""
    return normalize_lang(_ss_get(session_state, STATE_LANGUAGE, DEFAULT_LANG))


def set_language(session_state: Any, lang: str) -> None:
    """Store UI language without touching pipeline results."""
    session_state[STATE_LANGUAGE] = normalize_lang(lang)


def activity_period_bounds(
    activities: pd.DataFrame,
) -> tuple[str | None, str | None]:
    """Return YYYY-MM start/end labels from activity date columns."""
    if activities is None or activities.empty:
        return None, None
    starts = activities.get("activity_start_date")
    ends = activities.get("activity_end_date")
    if starts is None or ends is None:
        return None, None
    start_ts = pd.to_datetime(starts, errors="coerce").dropna()
    end_ts = pd.to_datetime(ends, errors="coerce").dropna()
    if start_ts.empty or end_ts.empty:
        return None, None
    start_label = pd.Timestamp(start_ts.min()).strftime("%Y-%m")
    end_label = pd.Timestamp(end_ts.max()).strftime("%Y-%m")
    return start_label, end_label


def _store_analysis_source_demo(session_state: Any, result: PipelineRunResult) -> None:
    session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_DEMO
    session_state[STATE_ANALYSIS_FILE_NAME] = None
    start, end = activity_period_bounds(result.activity_records_accepted)
    session_state[STATE_ANALYSIS_PERIOD_START] = start
    session_state[STATE_ANALYSIS_PERIOD_END] = end
    session_state[STATE_ANALYSIS_ACTIVITY_COUNT] = int(
        len(result.activity_records_accepted)
    )
    session_state[STATE_UPLOADED_ANALYSIS_COMPLETED] = False


def _store_analysis_source_uploaded(
    session_state: Any,
    result: PipelineRunResult,
    *,
    file_name: str,
) -> None:
    session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_UPLOADED
    session_state[STATE_ANALYSIS_FILE_NAME] = file_name
    start, end = activity_period_bounds(result.activity_records_accepted)
    session_state[STATE_ANALYSIS_PERIOD_START] = start
    session_state[STATE_ANALYSIS_PERIOD_END] = end
    session_state[STATE_ANALYSIS_ACTIVITY_COUNT] = int(
        len(result.activity_records_accepted)
    )
    session_state[STATE_UPLOADED_ANALYSIS_COMPLETED] = True


def get_analysis_source(session_state: Any) -> str:
    """Return demo or uploaded for the active analysis result."""
    value = _ss_get(session_state, STATE_ANALYSIS_SOURCE, ANALYSIS_SOURCE_DEMO)
    if value == ANALYSIS_SOURCE_UPLOADED:
        return ANALYSIS_SOURCE_UPLOADED
    return ANALYSIS_SOURCE_DEMO


def is_uploaded_analysis(session_state: Any) -> bool:
    """True when the active pipeline result came from uploaded company data."""
    return get_analysis_source(session_state) == ANALYSIS_SOURCE_UPLOADED


def has_validated_uploaded_data(session_state: Any) -> bool:
    """True when intake validation produced at least one accepted activity."""
    intake = get_intake_result(session_state)
    if intake is None:
        return False
    accepted = getattr(intake, "accepted_activities", None)
    count = int(getattr(intake, "accepted_count", 0) or 0)
    if accepted is None or getattr(accepted, "empty", True):
        return False
    return count > 0


def get_analysis_source_summary(session_state: Any) -> dict[str, Any]:
    """Return beginner-facing labels for the active analysis dataset."""
    source = get_analysis_source(session_state)
    if source == ANALYSIS_SOURCE_UPLOADED:
        file_name = _ss_get(
            session_state, STATE_ANALYSIS_FILE_NAME
        ) or _ss_get(session_state, STATE_INTAKE_FILE_NAME)
        return {
            "source": source,
            "file_name": str(file_name or "").strip() or "uploaded_file",
            "period_start": _ss_get(session_state, STATE_ANALYSIS_PERIOD_START),
            "period_end": _ss_get(session_state, STATE_ANALYSIS_PERIOD_END),
            "activity_count": int(
                _ss_get(session_state, STATE_ANALYSIS_ACTIVITY_COUNT) or 0
            ),
            "is_demo": False,
        }
    return {
        "source": ANALYSIS_SOURCE_DEMO,
        "file_name": None,
        "period_start": _ss_get(session_state, STATE_ANALYSIS_PERIOD_START),
        "period_end": _ss_get(session_state, STATE_ANALYSIS_PERIOD_END),
        "activity_count": int(
            _ss_get(session_state, STATE_ANALYSIS_ACTIVITY_COUNT) or 0
        ),
        "is_demo": True,
    }


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
    if STATE_RUN_UPLOADED_REQUEST not in session_state:
        session_state[STATE_RUN_UPLOADED_REQUEST] = False
    if STATE_NAVIGATE_TO_RESULTS not in session_state:
        session_state[STATE_NAVIGATE_TO_RESULTS] = False
    if STATE_RESULT_REVEAL_PENDING not in session_state:
        session_state[STATE_RESULT_REVEAL_PENDING] = None
    if STATE_LAST_ANIMATED_RESULT not in session_state:
        session_state[STATE_LAST_ANIMATED_RESULT] = None
    if STATE_HERO_EMISSIONS_PLAY not in session_state:
        session_state[STATE_HERO_EMISSIONS_PLAY] = None
    if STATE_ANALYSIS_SOURCE not in session_state:
        session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_DEMO
    if STATE_UPLOADED_ANALYSIS_COMPLETED not in session_state:
        session_state[STATE_UPLOADED_ANALYSIS_COMPLETED] = False
    if STATE_INTAKE_STEP not in session_state:
        session_state[STATE_INTAKE_STEP] = 1
    if STATE_TUTORIAL_OPEN_COUNT not in session_state:
        session_state[STATE_TUTORIAL_OPEN_COUNT] = 0
    ensure_tutorial_state(session_state)

    already = bool(_ss_get(session_state, STATE_INITIALIZED)) and (
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
        "analysis_data_source": ANALYSIS_SOURCE_DEMO,
    }
    _store_analysis_source_demo(session_state, result)
    session_state[STATE_INITIALIZED] = True
    session_state[STATE_RUN_ANALYSIS_REQUEST] = False
    session_state[STATE_RUN_UPLOADED_REQUEST] = False
    return result


def run_uploaded_analysis(
    session_state: Any,
    *,
    include_ghg: bool | None = None,
    include_cbam: bool | None = None,
    include_ifrs_s2: bool | None = None,
    run_id: str = UPLOADED_RUN_ID,
    repo_root: Path | None = None,
) -> PipelineRunResult:
    """Analyze the currently validated uploaded dataset (never demo raw)."""
    intake = get_intake_result(session_state)
    if intake is None:
        raise ValueError("No validated uploaded intake result is available.")
    accepted = getattr(intake, "accepted_activities", None)
    documents = getattr(intake, "source_documents", None)
    if accepted is None or getattr(accepted, "empty", True):
        raise ValueError("Validated intake has no accepted activities.")
    if documents is None or getattr(documents, "empty", True):
        raise ValueError("Validated intake has no source documents.")

    flags = get_adapter_flags(session_state)
    ghg = flags["include_ghg"] if include_ghg is None else bool(include_ghg)
    cbam = flags["include_cbam"] if include_cbam is None else bool(include_cbam)
    ifrs = (
        flags["include_ifrs_s2"]
        if include_ifrs_s2 is None
        else bool(include_ifrs_s2)
    )

    file_name = str(
        getattr(intake, "file_name", None)
        or _ss_get(session_state, STATE_INTAKE_FILE_NAME)
        or "uploaded_file"
    ).strip()
    ingested_at = pd.Timestamp.now(tz="UTC")
    meta = _ss_get(session_state, STATE_INTAKE_METADATA)
    if meta is not None and getattr(meta, "ingested_at", None) is not None:
        ingested_at = pd.Timestamp(meta.ingested_at)

    session_state[STATE_ERROR] = None
    try:
        result = run_uploaded_pipeline(
            Path(repo_root) if repo_root is not None else REPO_ROOT,
            run_id=run_id,
            ingested_at=ingested_at,
            source_documents=documents,
            accepted_activities=accepted,
            include_ghg=ghg,
            include_cbam=cbam,
            include_ifrs_s2=ifrs,
        )
    except Exception as exc:  # noqa: BLE001 - surface as UI error text
        session_state[STATE_ERROR] = str(exc)
        raise

    session_state[STATE_RESULT] = result
    session_state[STATE_INCLUDE_GHG] = ghg
    session_state[STATE_INCLUDE_CBAM] = cbam
    session_state[STATE_INCLUDE_IFRS] = ifrs
    session_state[STATE_RUN_ID] = result.run_id
    session_state[STATE_LAST_CONFIG] = {
        "run_id": result.run_id,
        "ingested_at": str(ingested_at),
        "include_ghg": ghg,
        "include_cbam": cbam,
        "include_ifrs_s2": ifrs,
        "analysis_data_source": ANALYSIS_SOURCE_UPLOADED,
        "file_name": file_name,
    }
    _store_analysis_source_uploaded(session_state, result, file_name=file_name)
    session_state[STATE_INITIALIZED] = True
    session_state[STATE_RUN_ANALYSIS_REQUEST] = False
    session_state[STATE_RUN_UPLOADED_REQUEST] = False
    return result


def get_current_result(session_state: Any) -> PipelineRunResult | None:
    """Return the stored pipeline result, if any."""
    result = _ss_get(session_state, STATE_RESULT)
    if result is None:
        return None
    if not isinstance(result, PipelineRunResult):
        return None
    return result


def get_adapter_flags(session_state: Any) -> dict[str, bool]:
    """Return the currently selected analysis-module flags."""
    return {
        "include_ghg": bool(_ss_get(session_state, STATE_INCLUDE_GHG, True)),
        "include_cbam": bool(_ss_get(session_state, STATE_INCLUDE_CBAM, False)),
        "include_ifrs_s2": bool(_ss_get(session_state, STATE_INCLUDE_IFRS, True)),
    }


def get_ui_error(session_state: Any) -> str | None:
    """Return the last user-facing analysis error, if any."""
    value = _ss_get(session_state, STATE_ERROR)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def set_focus_record(session_state: Any, record_id: str | None) -> None:
    """Store a record ID for Activity Explorer deep-links."""
    session_state[STATE_FOCUS_RECORD] = record_id


def get_focus_record(session_state: Any) -> str | None:
    """Return the focused record ID, if any."""
    value = _ss_get(session_state, STATE_FOCUS_RECORD)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def request_run_analysis(session_state: Any) -> None:
    """Ask the shell to run demo analysis on the next sidebar pass."""
    session_state[STATE_RUN_ANALYSIS_REQUEST] = True
    session_state[STATE_RUN_UPLOADED_REQUEST] = False


def request_run_uploaded_analysis(session_state: Any) -> None:
    """Ask the shell to analyze the validated uploaded dataset."""
    session_state[STATE_RUN_UPLOADED_REQUEST] = True
    session_state[STATE_RUN_ANALYSIS_REQUEST] = False


def clear_intake_state(session_state: Any) -> None:
    """Clear Phase 9A intake session values without touching analysis results."""
    for key in (
        STATE_INTAKE_FILE_HASH,
        STATE_INTAKE_FILE_NAME,
        STATE_INTAKE_TABLE,
        STATE_INTAKE_BYTES,
        STATE_INTAKE_SHEET,
        STATE_INTAKE_SHEET_CONFIRMED,
        STATE_INTAKE_HEADER_ROW,
        STATE_INTAKE_HEADER_CONFIRMED,
        STATE_INTAKE_YEAR_MONTH_CONFIRMED,
        STATE_INTAKE_SHOW_MAPPING_EDITOR,
        STATE_INTAKE_MAPPING,
        STATE_INTAKE_METADATA,
        STATE_INTAKE_RESULT,
        STATE_INTAKE_STEP,
    ):
        if key in session_state:
            del session_state[key]


def get_intake_result(session_state: Any) -> Any | None:
    """Return the validated intake result stored in session, if any."""
    return _ss_get(session_state, STATE_INTAKE_RESULT)
