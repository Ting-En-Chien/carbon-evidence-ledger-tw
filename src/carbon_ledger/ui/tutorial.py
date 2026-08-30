"""Action-driven first-run onboarding for Carbon Evidence Ledger.

The first run shows one short welcome modal. After the customer selects
"開始" the modal unmounts completely and every later hint is a small
coachmark attached to the real product UI.

Steps advance from real product state only — company setup, a file that was
actually read, an empty confirmation queue, a finished analysis, and a ready
result. There is no "next" control for steps 1–4 and no product screenshot
in the runtime DOM.

Session keys of other modules are referenced by their literal names on
purpose: ``carbon_ledger.ui.state`` imports this module, so importing it
back here would create a cycle.
"""

from __future__ import annotations

import html
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import streamlit as st
import streamlit.components.v1 as components

from carbon_ledger.ui.i18n import t

_COACH_JS_PATH = Path(__file__).with_name("onboarding_coach.js")

ONBOARDING_VERSION = "stage4-2j-visible-replay-20260830"
ONBOARDING_STEP_COUNT = 5

STAGE_WELCOME = "welcome"
STAGE_RUNNING = "running"
STAGE_DONE = "done"
STAGE_DISMISSED = "dismissed"

STATE_ONBOARDING_STAGE = "onboarding_stage"
STATE_ONBOARDING_STARTED = "onboarding_started"
STATE_ONBOARDING_STEP = "onboarding_step"
STATE_ONBOARDING_VERSION = "onboarding_version"
# {"file_hash": str, "observed": bool, "open_questions": int}
STATE_ONBOARDING_QUEUE = "onboarding_queue_observation"
STATE_ONBOARDING_PENDING_PAGE = "onboarding_pending_page"
STATE_ONBOARDING_LAST_STEP = "onboarding_last_resolved_step"
STATE_ONBOARDING_SCENE = "onboarding_scene"
STATE_ONBOARDING_ENTERED_SETUP = "onboarding_entered_company_setup"
STATE_ONBOARDING_COVERAGE_SEEN = "onboarding_coverage_seen"
STATE_ONBOARDING_HYDRATED = "onboarding_hydrated"
STATE_ONBOARDING_PERSISTED = "onboarding_persisted_record"
STATE_APPLICABILITY_HINT_SEEN = "onboarding_applicability_hint_seen"

# Durable transport for the browser bridge.
# v2 intentionally gives every browser one clean first run after the original
# Cloud deployment could persist a dismissed state before showing any UI.
LOCAL_STORAGE_KEY = "cel.onboarding.v2"
QUERY_PARAM = "onb"
HYDRATE_NEW = "new"
HYDRATE_RUN = "run"
HYDRATE_DONE = "done"
HYDRATE_SKIP = "skip"

# Legacy names kept so existing sessions and callers keep working.
STATE_TUTORIAL_SEEN = "tutorial_seen"
STATE_OPEN_TUTORIAL = "open_tutorial"
STATE_TUTORIAL_OPEN_COUNT = "tutorial_open_count"
STATE_TUTORIAL_COMPLETED = "tutorial_completed"
STATE_TUTORIAL_SESSION_DISMISSED = "tutorial_session_dismissed"
STATE_TUTORIAL_VISIBLE = "tutorial_visible"
STATE_TUTORIAL_STEP = "tutorial_step"
STATE_TUTORIAL_VERSION = "tutorial_version"
STATE_TUTORIAL_KEEP_OPEN = "tutorial_keep_open"

# Product state read by the step machine. Literal keys avoid an import cycle
# with carbon_ledger.ui.state, which imports this module.
_KEY_INTAKE_TABLE = "uploaded_table"
_KEY_INTAKE_RESULT = "validated_intake_result"
_KEY_INTAKE_FILE_HASH = "uploaded_file_hash"
_KEY_PIPELINE_RESULT = "pipeline_result"
_KEY_ANALYSIS_SOURCE = "analysis_data_source"
_KEY_ANALYSIS_FILE_HASH = "analysis_source_file_hash"
_KEY_UPLOADED_ANALYSIS_DONE = "uploaded_analysis_completed"
_KEY_ANALYSIS_PHASE = "analysis_phase"
_KEY_ANALYSIS_RUNNING = "analysis_running"
_KEY_NAVIGATE_TO_RESULTS = "navigate_to_results_after_analysis"
_ANALYSIS_SOURCE_UPLOADED = "uploaded"
_ANALYSIS_PHASE_ANALYZING = "analyzing"
_ANALYSIS_PHASE_CLOSING = "overlay_closing"

PAGE_OVERVIEW = "app_pages/dashboard.py"
PAGE_APPLICABILITY = "app_pages/applicability.py"
PAGE_INTAKE = "app_pages/data_intake.py"

_KEY_COMPANY_MASTER = "company_master"
_KEY_FACILITY_MASTER = "facility_master"
_KEY_WIZARD_STEP = "applicability_wizard_step"
_KEY_BOUNDARY_STEP = "boundary_wizard_step"
_KEY_INTAKE_STEP = "intake_wizard_step"

STEP_COMPANY_SETUP = "company_setup"
STEP_UPLOAD_DATA = "upload_data"
STEP_REVIEW_DATA = "review_data"
STEP_START_CALCULATION = "start_calculation"
STEP_VIEW_RESULTS = "view_results"

SCENE_START_SETUP = "start_setup"
SCENE_UBN_LOOKUP = "ubn_lookup"
SCENE_COMPANY_CONFIRMATION = "company_confirmation"
SCENE_COMPANY_DETAILS = "company_details"
SCENE_ADDITIONAL_INFORMATION = "additional_information"
SCENE_TAIWAN_FACILITIES = "taiwan_facilities"
SCENE_FACILITIES_CONTINUE = "facilities_continue"
SCENE_REPORTING_PERIOD = "reporting_period"
SCENE_PURPOSE_REVIEW = "purpose_review"
SCENE_REPORTING_ENTITY = "reporting_entity"
SCENE_GOVERNMENT_SITES = "government_sites"
SCENE_OPERATIONS_BOUNDARY = "operations_boundary"
SCENE_CONFIRM_BOUNDARY = "confirm_boundary"
SCENE_UPLOAD_ACTIVITY = "upload_activity_data"
SCENE_REVIEW_DATA = "review_data"
SCENE_REVIEW_COVERAGE = "review_coverage"
SCENE_START_ANALYSIS = "start_analysis"
SCENE_VIEW_RESULTS = "view_results"

TARGET = "[data-cel-onboarding-target='{name}']"


def _target(name: str) -> str:
    return TARGET.format(name=name)


ONBOARDING_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": STEP_COMPANY_SETUP,
        "index": 1,
        "title_key": "onb.s1.title",
        "body_key": "onb.s1.body",
        "page": PAGE_OVERVIEW,
    },
    {
        "id": STEP_UPLOAD_DATA,
        "index": 2,
        "title_key": "onb.s2.title",
        "body_key": "onb.s2.body",
        "page": PAGE_INTAKE,
    },
    {
        "id": STEP_REVIEW_DATA,
        "index": 3,
        "title_key": "onb.s3.title",
        "body_key": "onb.s3.body",
        "page": PAGE_INTAKE,
    },
    {
        "id": STEP_START_CALCULATION,
        "index": 4,
        "title_key": "onb.s4.title",
        "body_key": "onb.s4.body",
        "page": PAGE_INTAKE,
    },
    {
        "id": STEP_VIEW_RESULTS,
        "index": 5,
        "title_key": "onb.s5.title",
        "body_key": "onb.s5.body",
        "page": PAGE_OVERVIEW,
    },
)

ONBOARDING_SCENES: tuple[dict[str, Any], ...] = (
    {
        "id": SCENE_START_SETUP,
        "step": 1,
        "title_key": "onb.s1a.title",
        "body_key": "onb.s1a.body",
        "page": PAGE_OVERVIEW,
        "selectors": (
            _target("start-setup"),
            ".st-key-onboard_start_setup",
        ),
    },
    {
        "id": SCENE_UBN_LOOKUP,
        "step": 1,
        "title_key": "onb.s1b.title",
        "body_key": "onb.s1b.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("company-ubn-lookup"),
            ".st-key-apl_lookup",
        ),
    },
    {
        "id": SCENE_COMPANY_CONFIRMATION,
        "step": 1,
        "title_key": "onb.s1c.title",
        "body_key": "onb.s1c.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("company-confirmation"),
            ".st-key-apl_confirm_co",
        ),
    },
    {
        "id": SCENE_COMPANY_DETAILS,
        "step": 1,
        "title_key": "onb.s1d.title",
        "body_key": "onb.s1d.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("company-basic-information"),
            ".st-key-apl_continue",
        ),
    },
    {
        "id": SCENE_ADDITIONAL_INFORMATION,
        "step": 1,
        "title_key": "onb.s1e.title",
        "body_key": "onb.s1e.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("company-additional-information"),
            ".st-key-apl_continue",
        ),
    },
    {
        "id": SCENE_TAIWAN_FACILITIES,
        "step": 1,
        "title_key": "onb.s1f.title",
        "body_key": "onb.s1f.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("taiwan-facilities"),
            ".st-key-apl_confirm_operating",
            ".st-key-apl_confirm_no_sites",
            ".st-key-apl_confirm_exception_statuses",
        ),
    },
    {
        "id": SCENE_FACILITIES_CONTINUE,
        "step": 1,
        "title_key": "onb.s1g.title",
        "body_key": "onb.s1g.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("facilities-continue"),
            ".st-key-apl_continue",
        ),
    },
    {
        "id": SCENE_REPORTING_PERIOD,
        "step": 1,
        "title_key": "onb.s1h.title",
        "body_key": "onb.s1h.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("reporting-period-confirmation"),
            _target("reporting-period"),
            ".st-key-boundary_period_primary",
        ),
    },
    {
        "id": SCENE_PURPOSE_REVIEW,
        "step": 1,
        "title_key": "onb.s1i.title",
        "body_key": "onb.s1i.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("purpose-review"),
            ".st-key-boundary_purposes_primary",
        ),
    },
    {
        "id": SCENE_REPORTING_ENTITY,
        "step": 1,
        "title_key": "onb.s1j.title",
        "body_key": "onb.s1j.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("reporting-entity"),
            "[class*='st-key-boundary_'][class*='_primary']",
        ),
    },
    {
        "id": SCENE_GOVERNMENT_SITES,
        "step": 1,
        "title_key": "onb.s1k.title",
        "body_key": "onb.s1k.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("government-sites"),
            "[class*='st-key-boundary_'][class*='_primary']",
        ),
    },
    {
        "id": SCENE_OPERATIONS_BOUNDARY,
        "step": 1,
        "title_key": "onb.s1l.title",
        "body_key": "onb.s1l.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("operations-boundary"),
            "[class*='st-key-boundary_'][class*='_primary']",
        ),
    },
    {
        "id": SCENE_CONFIRM_BOUNDARY,
        "step": 1,
        "title_key": "onb.s1m.title",
        "body_key": "onb.s1m.body",
        "page": PAGE_APPLICABILITY,
        "selectors": (
            _target("confirm-boundary"),
            "[class*='st-key-boundary_review'][class*='_primary']",
        ),
    },
    {
        "id": SCENE_UPLOAD_ACTIVITY,
        "step": 2,
        "title_key": "onb.s2.title",
        "body_key": "onb.s2.body",
        "page": PAGE_INTAKE,
        "selectors": (
            _target("upload-activity-data"),
            ".st-key-intake_file_uploader",
            "[data-testid='stFileUploader']",
            "[data-cel-tour-target='upload-dropzone']",
        ),
    },
    {
        "id": SCENE_REVIEW_DATA,
        "step": 3,
        "title_key": "onb.s3.title",
        "body_key": "onb.s3.body",
        "page": PAGE_INTAKE,
        "selectors": (
            _target("recognition-question"),
            "[data-cel-tour-target='recognition-question']",
            "[data-cel-tour-target='recognition-apply']",
            ".cel-exception-card",
        ),
    },
    {
        "id": SCENE_REVIEW_COVERAGE,
        "step": 4,
        "title_key": "onb.s4a.title",
        "body_key": "onb.s4a.body",
        "page": PAGE_INTAKE,
        "selectors": (
            _target("calculation-coverage"),
            "[data-cel-tour-target='coverage-summary']",
            ".st-key-intake_accept_interpretation",
        ),
    },
    {
        "id": SCENE_START_ANALYSIS,
        "step": 4,
        "title_key": "onb.s4b.title",
        "body_key": "onb.s4b.body",
        "page": PAGE_INTAKE,
        "selectors": (
            _target("start-analysis"),
            ".st-key-intake_start_uploaded_analysis",
            "[data-cel-tour-target='coverage-cta']",
        ),
    },
    {
        "id": SCENE_VIEW_RESULTS,
        "step": 5,
        "title_key": "onb.s5.title",
        "body_key": "onb.s5.body",
        "page": PAGE_OVERVIEW,
        "selectors": (
            _target("results-hero"),
            "[data-cel-tour-target='results-hero']",
            "[data-cel-hero-emissions='1']",
        ),
    },
)

FORBIDDEN_CUSTOMER_TERMS = (
    "High",
    "Medium",
    "Low",
    "confidence score",
    "activity_type",
    "activity_value",
    "site_id",
    "fingerprint",
    "schema",
    "canonical",
    "parser",
    "obligation_id",
    "rule_id",
    "CASE C",
    "qa_",
)

# Legal, internal-status and technical phrasing that must never reach the
# first-run onboarding. Those belong to contextual notices on data pages.
FORBIDDEN_ONBOARDING_PHRASES = (
    "不是已確定的法律結論",
    "待覆核",
    "系統無法安全辨識",
    "可以安全辨識的部分",
    "排除、待確認或暫緩",
    "不是 0 排放",
    "這次不納入",
    "settled legal conclusion",
    "pending review",
    "not zero emissions",
    "not included this time",
    "disposition",
)


def _ss_flag(session_state: Any, key: str, default: Any = False) -> Any:
    """Read session flags without SessionState.get (AppTest-safe)."""
    try:
        if key in session_state:
            return session_state[key]
    except Exception:  # noqa: BLE001
        pass
    try:
        return session_state[key]
    except Exception:  # noqa: BLE001
        return default


def _unknown_queue() -> dict[str, Any]:
    """Queue observation before any file was inspected in this session."""
    return {"file_hash": "", "observed": False, "open_questions": -1}


def ensure_onboarding_state(session_state: Any) -> None:
    """Initialize onboarding flags without forcing anything on later pages."""
    if STATE_ONBOARDING_STAGE not in session_state:
        session_state[STATE_ONBOARDING_STAGE] = STAGE_WELCOME
    if STATE_ONBOARDING_STARTED not in session_state:
        session_state[STATE_ONBOARDING_STARTED] = False
    if STATE_ONBOARDING_STEP not in session_state:
        session_state[STATE_ONBOARDING_STEP] = 1
    if STATE_ONBOARDING_VERSION not in session_state:
        session_state[STATE_ONBOARDING_VERSION] = ONBOARDING_VERSION
    if STATE_ONBOARDING_QUEUE not in session_state:
        session_state[STATE_ONBOARDING_QUEUE] = _unknown_queue()
    if STATE_ONBOARDING_PENDING_PAGE not in session_state:
        session_state[STATE_ONBOARDING_PENDING_PAGE] = ""
    if STATE_ONBOARDING_LAST_STEP not in session_state:
        session_state[STATE_ONBOARDING_LAST_STEP] = 0
    if STATE_ONBOARDING_SCENE not in session_state:
        session_state[STATE_ONBOARDING_SCENE] = SCENE_START_SETUP
    if STATE_ONBOARDING_ENTERED_SETUP not in session_state:
        session_state[STATE_ONBOARDING_ENTERED_SETUP] = False
    if STATE_ONBOARDING_COVERAGE_SEEN not in session_state:
        session_state[STATE_ONBOARDING_COVERAGE_SEEN] = False
    if STATE_ONBOARDING_HYDRATED not in session_state:
        session_state[STATE_ONBOARDING_HYDRATED] = False
    if STATE_APPLICABILITY_HINT_SEEN not in session_state:
        session_state[STATE_APPLICABILITY_HINT_SEEN] = False
    if STATE_TUTORIAL_SEEN not in session_state:
        session_state[STATE_TUTORIAL_SEEN] = False
    if STATE_OPEN_TUTORIAL not in session_state:
        session_state[STATE_OPEN_TUTORIAL] = False
    if STATE_TUTORIAL_OPEN_COUNT not in session_state:
        session_state[STATE_TUTORIAL_OPEN_COUNT] = 0
    if STATE_TUTORIAL_COMPLETED not in session_state:
        session_state[STATE_TUTORIAL_COMPLETED] = False
    if STATE_TUTORIAL_SESSION_DISMISSED not in session_state:
        session_state[STATE_TUTORIAL_SESSION_DISMISSED] = False
    if STATE_TUTORIAL_VISIBLE not in session_state:
        session_state[STATE_TUTORIAL_VISIBLE] = False
    if STATE_TUTORIAL_STEP not in session_state:
        session_state[STATE_TUTORIAL_STEP] = 1
    if STATE_TUTORIAL_VERSION not in session_state:
        session_state[STATE_TUTORIAL_VERSION] = ONBOARDING_VERSION
    if STATE_TUTORIAL_KEEP_OPEN not in session_state:
        session_state[STATE_TUTORIAL_KEEP_OPEN] = False


# Backwards-compatible alias: carbon_ledger.ui.state imports this name.
ensure_tutorial_state = ensure_onboarding_state


def onboarding_stage(session_state: Any) -> str:
    """Return the persisted onboarding stage.

    Completed and dismissed are sticky: an ONBOARDING_VERSION bump never
    reopens the flow for a customer who already finished or skipped it.
    """
    ensure_onboarding_state(session_state)
    if bool(_ss_flag(session_state, STATE_TUTORIAL_COMPLETED)):
        return STAGE_DONE
    if bool(_ss_flag(session_state, STATE_TUTORIAL_SESSION_DISMISSED)):
        return STAGE_DISMISSED
    stage = str(_ss_flag(session_state, STATE_ONBOARDING_STAGE, STAGE_WELCOME) or "")
    if stage not in {STAGE_WELCOME, STAGE_RUNNING, STAGE_DONE, STAGE_DISMISSED}:
        stage = STAGE_WELCOME
    return stage


def onboarding_running(session_state: Any) -> bool:
    """True only while the customer is actually inside the tour."""
    return onboarding_stage(session_state) == STAGE_RUNNING


# --------------------------------------------------------------------------
# Real product state → step completion
# --------------------------------------------------------------------------


def company_setup_complete(session_state: Any) -> bool:
    """True when the existing required company setup is already finished.

    Authority is the boundary wizard's own confirmed period package: the
    customer confirmed the company identity, an explicitly confirmed
    ReportingPeriod is current, and the scope review reached local
    confirmation. Applicable requirements are deliberately not part of this
    gate — they must never block a first Scope 1 / Scope 2 calculation.
    """
    try:
        from carbon_ledger.ui.boundary_wizard import company_setup_ready
        from carbon_ledger.ui.state import REPO_ROOT

        # Re-read every time: a newly selected reporting period is unconfirmed
        # again, so this must never latch to True.
        return bool(company_setup_ready(session_state, repo_root=REPO_ROOT))
    except Exception:  # noqa: BLE001 - never break a render on a workspace read
        return False


def upload_read_complete(session_state: Any) -> bool:
    """True only after a file was actually read into an intake table."""
    if _ss_flag(session_state, _KEY_INTAKE_TABLE, None) is not None:
        return True
    return _ss_flag(session_state, _KEY_INTAKE_RESULT, None) is not None


def current_file_hash(session_state: Any) -> str:
    return str(_ss_flag(session_state, _KEY_INTAKE_FILE_HASH, "") or "")


def queue_observation(session_state: Any) -> dict[str, Any]:
    """Queue observation bound to the file it was actually taken from."""
    raw = _ss_flag(session_state, STATE_ONBOARDING_QUEUE, None)
    if not isinstance(raw, dict):
        return _unknown_queue()
    try:
        count = int(raw.get("open_questions", -1))
    except (TypeError, ValueError):
        count = -1
    return {
        "file_hash": str(raw.get("file_hash") or ""),
        "observed": bool(raw.get("observed")),
        "open_questions": count,
    }


def open_question_count(session_state: Any) -> int:
    """Observed queue length for the current file (-1 when not observed)."""
    observation = queue_observation(session_state)
    current = current_file_hash(session_state)
    if not observation["observed"]:
        return -1
    if not current or observation["file_hash"] != current:
        return -1
    return observation["open_questions"]


def record_onboarding_open_questions(
    session_state: Any,
    count: int,
    *,
    file_hash: str = "",
) -> bool:
    """Mirror the real confirmation-queue length of one specific file.

    Observation only — the queue itself, its answers and every disposition
    stay owned by the intake page. An observation is never reused for a
    different file.

    Returns True when this observation is the first to see an empty queue for
    this file, so the caller can hand the next render a settled step.
    """
    hash_value = str(file_hash or "") or current_file_hash(session_state)
    if not hash_value:
        return False
    try:
        remaining = max(0, int(count))
    except (TypeError, ValueError):
        return False
    previous = queue_observation(session_state)
    already_clear = (
        previous["observed"]
        and previous["file_hash"] == hash_value
        and previous["open_questions"] == 0
    )
    try:
        session_state[STATE_ONBOARDING_QUEUE] = {
            "file_hash": hash_value,
            "observed": True,
            "open_questions": remaining,
        }
    except Exception:  # noqa: BLE001
        return False
    return remaining == 0 and not already_clear


def reset_onboarding_queue_observation(session_state: Any) -> None:
    """Forget the previous file's queue length."""
    try:
        session_state[STATE_ONBOARDING_QUEUE] = _unknown_queue()
    except Exception:  # noqa: BLE001
        pass


def note_onboarding_upload_file(session_state: Any, file_hash: str) -> None:
    """Bind onboarding observations to the file currently being read.

    Called on every intake render: when the selected file changes, the queue
    observation of the previous file is dropped so step 3 is decided again by
    the real ``list_exceptions()`` run of the new file.
    """
    hash_value = str(file_hash or "")
    if not hash_value:
        return
    if queue_observation(session_state)["file_hash"] != hash_value:
        reset_onboarding_queue_observation(session_state)


def review_queue_complete(session_state: Any) -> bool:
    """True only when the current file's own queue was observed empty."""
    if not upload_read_complete(session_state):
        return False
    if result_ready(session_state):
        return True
    return open_question_count(session_state) == 0


def result_ready(session_state: Any) -> bool:
    """True when the current uploaded file has a finished, readable result.

    A demo run, a result from a previously uploaded file, or an analysis that
    is still running never qualifies.
    """
    if _ss_flag(session_state, _KEY_PIPELINE_RESULT, None) is None:
        return False
    source = str(_ss_flag(session_state, _KEY_ANALYSIS_SOURCE, "") or "")
    if source != _ANALYSIS_SOURCE_UPLOADED:
        return False
    if not bool(_ss_flag(session_state, _KEY_UPLOADED_ANALYSIS_DONE)):
        return False
    current = current_file_hash(session_state)
    analysed = str(_ss_flag(session_state, _KEY_ANALYSIS_FILE_HASH, "") or "")
    if not current or not analysed or current != analysed:
        return False
    phase = str(_ss_flag(session_state, _KEY_ANALYSIS_PHASE, "") or "")
    if phase in {_ANALYSIS_PHASE_ANALYZING, _ANALYSIS_PHASE_CLOSING}:
        return False
    if bool(_ss_flag(session_state, _KEY_ANALYSIS_RUNNING)):
        return False
    # Still mid-navigation: the results page is not mounted yet.
    return not bool(_ss_flag(session_state, _KEY_NAVIGATE_TO_RESULTS))


def onboarding_completion(session_state: Any) -> dict[str, bool]:
    """Per-step completion derived from real product state only."""
    return {
        STEP_COMPANY_SETUP: company_setup_complete(session_state),
        STEP_UPLOAD_DATA: upload_read_complete(session_state),
        STEP_REVIEW_DATA: review_queue_complete(session_state),
        STEP_START_CALCULATION: result_ready(session_state),
        # Only the explicit "完成" action ends the flow.
        STEP_VIEW_RESULTS: False,
    }


def _mapping(session_state: Any, key: str) -> dict[str, Any]:
    raw = _ss_flag(session_state, key, None)
    return dict(raw) if isinstance(raw, dict) else {}


def _int_flag(session_state: Any, key: str, default: int = 0) -> int:
    try:
        return int(_ss_flag(session_state, key, default) or default)
    except (TypeError, ValueError):
        return default


def company_found(session_state: Any) -> bool:
    """True when lookup or manual entry produced a company name."""
    master = _mapping(session_state, _KEY_COMPANY_MASTER)
    return bool(str(master.get("company_name") or "").strip())


def company_identity_confirmed(session_state: Any) -> bool:
    master = _mapping(session_state, _KEY_COMPANY_MASTER)
    return bool(str(master.get("customer_confirmed_at") or "").strip())


def facilities_identity_confirmed(session_state: Any) -> bool:
    facilities = _mapping(session_state, _KEY_FACILITY_MASTER)
    return bool(facilities.get("identity_confirmed"))


def entered_company_setup(session_state: Any) -> bool:
    return bool(_ss_flag(session_state, STATE_ONBOARDING_ENTERED_SETUP))


def note_entered_company_setup(session_state: Any) -> None:
    """Observe that the customer is inside the real company-setup flow."""
    ensure_onboarding_state(session_state)
    try:
        session_state[STATE_ONBOARDING_ENTERED_SETUP] = True
    except Exception:  # noqa: BLE001
        pass


def _coverage_kpis_available(session_state: Any) -> bool:
    result = _ss_flag(session_state, _KEY_INTAKE_RESULT, None)
    if result is None:
        return False
    try:
        return int(getattr(result, "accepted_count", 0) or 0) >= 0 and _int_flag(
            session_state, _KEY_INTAKE_STEP, 1
        ) >= 3
    except (TypeError, ValueError):
        return False


def _start_analysis_available(session_state: Any) -> bool:
    result = _ss_flag(session_state, _KEY_INTAKE_RESULT, None)
    if result is None:
        return False
    try:
        return int(getattr(result, "accepted_count", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def scene_by_id(scene_id: str) -> dict[str, Any]:
    for spec in ONBOARDING_SCENES:
        if spec["id"] == scene_id:
            return spec
    return ONBOARDING_SCENES[0]


def scene_for_step(index: int) -> dict[str, Any]:
    for spec in ONBOARDING_SCENES:
        if int(spec["step"]) == int(index):
            return spec
    return ONBOARDING_SCENES[0]


def resolve_onboarding_scene(session_state: Any) -> dict[str, Any]:
    """Derive the live action scene from real product state."""
    ensure_onboarding_state(session_state)
    if result_ready(session_state):
        return scene_by_id(SCENE_VIEW_RESULTS)
    if not company_setup_complete(session_state):
        return _resolve_company_setup_scene(session_state)
    if not upload_read_complete(session_state):
        return scene_by_id(SCENE_UPLOAD_ACTIVITY)
    phase = str(_ss_flag(session_state, _KEY_ANALYSIS_PHASE, "") or "")
    running = bool(_ss_flag(session_state, _KEY_ANALYSIS_RUNNING))
    navigating = bool(_ss_flag(session_state, _KEY_NAVIGATE_TO_RESULTS))
    if running or phase in {_ANALYSIS_PHASE_ANALYZING, _ANALYSIS_PHASE_CLOSING}:
        return scene_by_id(SCENE_START_ANALYSIS)
    if not review_queue_complete(session_state):
        return scene_by_id(SCENE_REVIEW_DATA)
    if navigating:
        return scene_by_id(SCENE_START_ANALYSIS)
    if _start_analysis_available(session_state) and bool(
        _ss_flag(session_state, STATE_ONBOARDING_COVERAGE_SEEN)
    ):
        return scene_by_id(SCENE_START_ANALYSIS)
    return scene_by_id(SCENE_REVIEW_COVERAGE)


def _resolve_company_setup_scene(session_state: Any) -> dict[str, Any]:
    wizard = _int_flag(session_state, _KEY_WIZARD_STEP, 1)
    found = company_found(session_state)
    confirmed = company_identity_confirmed(session_state)
    entered = entered_company_setup(session_state) or found or wizard > 1
    if not entered:
        return scene_by_id(SCENE_START_SETUP)
    if wizard <= 1:
        if not found:
            return scene_by_id(SCENE_UBN_LOOKUP)
        if not confirmed:
            return scene_by_id(SCENE_COMPANY_CONFIRMATION)
        return scene_by_id(SCENE_COMPANY_DETAILS)
    if wizard == 2:
        return scene_by_id(SCENE_ADDITIONAL_INFORMATION)
    if wizard == 3:
        if not facilities_identity_confirmed(session_state):
            return scene_by_id(SCENE_TAIWAN_FACILITIES)
        return scene_by_id(SCENE_FACILITIES_CONTINUE)
    boundary = _int_flag(session_state, _KEY_BOUNDARY_STEP, 1) or 1
    mapping = {
        1: SCENE_REPORTING_PERIOD,
        2: SCENE_PURPOSE_REVIEW,
        3: SCENE_REPORTING_ENTITY,
        4: SCENE_GOVERNMENT_SITES,
        5: SCENE_OPERATIONS_BOUNDARY,
    }
    if boundary == 3 and not _ifrs_reporting_entity_needed(session_state):
        boundary = 4
    return scene_by_id(mapping.get(boundary, SCENE_CONFIRM_BOUNDARY))


def _ifrs_reporting_entity_needed(session_state: Any) -> bool:
    try:
        from carbon_ledger.ui.boundary_wizard import (
            ifrs_reporting_entity_step_required,
        )
        from carbon_ledger.ui.state import REPO_ROOT

        return bool(
            ifrs_reporting_entity_step_required(
                session_state, repo_root=REPO_ROOT
            )
        )
    except Exception:  # noqa: BLE001
        return True


def resolve_onboarding_step(session_state: Any) -> int:
    """Return the earliest step the customer has not completed yet."""
    return int(resolve_onboarding_scene(session_state)["step"])


def step_by_index(index: int) -> dict[str, Any]:
    if index < 1 or index > ONBOARDING_STEP_COUNT:
        raise ValueError(f"onboarding step out of range: {index}")
    return ONBOARDING_STEPS[index - 1]


def iter_onboarding_steps() -> tuple[dict[str, Any], ...]:
    return ONBOARDING_STEPS


def step_page(index: int) -> str:
    return str(step_by_index(index).get("page") or PAGE_OVERVIEW)


def scene_page(scene: dict[str, Any]) -> str:
    return str(scene.get("page") or PAGE_OVERVIEW)


# --------------------------------------------------------------------------
# Cross-page navigation
# --------------------------------------------------------------------------


def request_onboarding_page(session_state: Any, page: str) -> None:
    """Queue one safe route change for the next Streamlit run."""
    target = str(page or "").strip()
    if not target:
        return
    try:
        session_state[STATE_ONBOARDING_PENDING_PAGE] = target
    except Exception:  # noqa: BLE001
        pass


def pending_onboarding_page(session_state: Any) -> str:
    return str(_ss_flag(session_state, STATE_ONBOARDING_PENDING_PAGE, "") or "")


def consume_onboarding_page(session_state: Any) -> str:
    """Read and clear the queued route so it can never loop."""
    target = pending_onboarding_page(session_state)
    if target:
        try:
            session_state[STATE_ONBOARDING_PENDING_PAGE] = ""
        except Exception:  # noqa: BLE001
            pass
    return target


def run_pending_onboarding_navigation(session_state: Any) -> str:
    """Execute a queued route change after the router registered its pages.

    Called from the shell between ``st.navigation(...)`` and ``.run()`` so the
    old page is never mounted next to the new one.
    """
    ensure_onboarding_state(session_state)
    if onboarding_stage(session_state) not in {STAGE_WELCOME, STAGE_RUNNING}:
        consume_onboarding_page(session_state)
        return ""
    target = consume_onboarding_page(session_state)
    if not target:
        return ""
    try:
        st.switch_page(target)
    except Exception:  # noqa: BLE001 - unknown page must not break the shell
        return ""
    return target


def _note_step_transition(session_state: Any, step_no: int) -> None:
    """Route to the upload page once the real company setup is finished."""
    try:
        previous = int(_ss_flag(session_state, STATE_ONBOARDING_LAST_STEP, 0) or 0)
    except (TypeError, ValueError):
        previous = 0
    if previous == step_no:
        return
    try:
        session_state[STATE_ONBOARDING_LAST_STEP] = step_no
    except Exception:  # noqa: BLE001
        return
    if previous == 1 and step_no == 2:
        request_onboarding_page(session_state, PAGE_INTAKE)


# --------------------------------------------------------------------------
# Stage transitions
# --------------------------------------------------------------------------


def start_onboarding(session_state: Any) -> None:
    """Accept the welcome modal. The modal unmounts on the next render."""
    ensure_onboarding_state(session_state)
    session_state[STATE_ONBOARDING_STAGE] = STAGE_RUNNING
    session_state[STATE_ONBOARDING_STARTED] = True
    session_state[STATE_TUTORIAL_VISIBLE] = False
    session_state[STATE_OPEN_TUTORIAL] = False
    session_state[STATE_TUTORIAL_SEEN] = True
    session_state[STATE_ONBOARDING_VERSION] = ONBOARDING_VERSION
    scene = resolve_onboarding_scene(session_state)
    step_no = int(scene["step"])
    session_state[STATE_ONBOARDING_LAST_STEP] = step_no
    session_state[STATE_ONBOARDING_SCENE] = scene["id"]
    dest = scene_page(scene)
    # Welcome is already on the default dashboard. Switching to it aborts the
    # in-flight load that Playwright's page.goto is waiting on.
    if dest != PAGE_OVERVIEW:
        request_onboarding_page(session_state, dest)


def dismiss_onboarding(session_state: Any) -> None:
    """Close for this session without marking onboarding completed."""
    ensure_onboarding_state(session_state)
    session_state[STATE_ONBOARDING_STAGE] = STAGE_DISMISSED
    session_state[STATE_TUTORIAL_SESSION_DISMISSED] = True
    session_state[STATE_TUTORIAL_VISIBLE] = False
    session_state[STATE_OPEN_TUTORIAL] = False
    session_state[STATE_TUTORIAL_SEEN] = True
    session_state[STATE_TUTORIAL_KEEP_OPEN] = False


def complete_onboarding(session_state: Any) -> None:
    """Mark onboarding completed after the customer selects 完成."""
    ensure_onboarding_state(session_state)
    session_state[STATE_ONBOARDING_STAGE] = STAGE_DONE
    session_state[STATE_TUTORIAL_COMPLETED] = True
    session_state[STATE_TUTORIAL_SESSION_DISMISSED] = True
    session_state[STATE_TUTORIAL_VISIBLE] = False
    session_state[STATE_OPEN_TUTORIAL] = False
    session_state[STATE_TUTORIAL_SEEN] = True
    session_state[STATE_TUTORIAL_KEEP_OPEN] = False


def request_onboarding(session_state: Any) -> None:
    """Reopen from 操作教學 with an unmistakable visible starting surface."""
    ensure_onboarding_state(session_state)
    session_state[STATE_TUTORIAL_COMPLETED] = False
    session_state[STATE_TUTORIAL_SESSION_DISMISSED] = False
    # Always show the welcome dialog first. Previously a returning browser
    # jumped straight to a small coachmark; if routing was still settling the
    # click appeared to do nothing. Selecting 開始 still resumes at the earliest
    # unfinished real-product step through ``start_onboarding`` below.
    session_state[STATE_ONBOARDING_STAGE] = STAGE_WELCOME
    session_state[STATE_OPEN_TUTORIAL] = True
    session_state[STATE_TUTORIAL_OPEN_COUNT] = (
        int(_ss_flag(session_state, STATE_TUTORIAL_OPEN_COUNT, 0) or 0) + 1
    )
    # Reopening from another route must land on the page that owns the scene.
    scene = resolve_onboarding_scene(session_state)
    step_no = int(scene["step"])
    session_state[STATE_ONBOARDING_LAST_STEP] = step_no
    session_state[STATE_ONBOARDING_SCENE] = scene["id"]
    request_onboarding_page(session_state, scene_page(scene))


# Header and sidebar controls import this name.
request_tutorial = request_onboarding


def current_onboarding_step(session_state: Any) -> int:
    ensure_onboarding_state(session_state)
    try:
        step = int(_ss_flag(session_state, STATE_ONBOARDING_STEP, 1) or 1)
    except Exception:  # noqa: BLE001
        step = 1
    return max(1, min(ONBOARDING_STEP_COUNT, step))


def mark_tutorial_keep_open(session_state: Any) -> None:
    """Keep the language control stable across in-flow reruns."""
    ensure_onboarding_state(session_state)
    if onboarding_stage(session_state) in {STAGE_WELCOME, STAGE_RUNNING}:
        session_state[STATE_TUTORIAL_KEEP_OPEN] = True


# --------------------------------------------------------------------------
# Durable state
#
# The prototype has no server-side customer preference store: the company
# workspace is keyed by a confirmed UBN and therefore does not exist on a
# first run. So the durable record lives in browser localStorage and is
# handed to Python once per session through a single query-parameter hop.
# Only onboarding flags are stored — never company or emissions data.
# --------------------------------------------------------------------------


def onboarding_record(session_state: Any) -> dict[str, Any]:
    """The durable part of onboarding state (no product data)."""
    ensure_onboarding_state(session_state)
    return {
        "started": bool(_ss_flag(session_state, STATE_ONBOARDING_STARTED)),
        "completed": bool(_ss_flag(session_state, STATE_TUTORIAL_COMPLETED)),
        "dismissed": bool(_ss_flag(session_state, STATE_TUTORIAL_SESSION_DISMISSED)),
        "version": ONBOARDING_VERSION,
        "applicability_hint_seen": bool(
            _ss_flag(session_state, STATE_APPLICABILITY_HINT_SEEN)
        ),
    }


TOKEN_SKIP_STARTED = f"{HYDRATE_SKIP}-{HYDRATE_RUN}"


def record_token(record: dict[str, Any]) -> str:
    """Encode a durable record as one short query-parameter token."""
    if record.get("completed"):
        token = HYDRATE_DONE
    elif record.get("dismissed"):
        token = TOKEN_SKIP_STARTED if record.get("started") else HYDRATE_SKIP
    elif record.get("started"):
        token = HYDRATE_RUN
    else:
        token = HYDRATE_NEW
    if record.get("applicability_hint_seen"):
        token = f"{token}.h"
    return token


def apply_hydration_token(session_state: Any, token: str) -> None:
    """Restore started / completed / dismissed from a durable token.

    Completed and dismissed stay sticky here as well: a new
    ONBOARDING_VERSION never replays the flow for those customers.
    """
    ensure_onboarding_state(session_state)
    raw = str(token or "").strip()
    base, _, suffix = raw.partition(".")
    if suffix == "h":
        session_state[STATE_APPLICABILITY_HINT_SEEN] = True
    started = base in {HYDRATE_RUN, HYDRATE_DONE, TOKEN_SKIP_STARTED}
    session_state[STATE_ONBOARDING_STARTED] = started
    if base == HYDRATE_DONE:
        session_state[STATE_TUTORIAL_COMPLETED] = True
        session_state[STATE_ONBOARDING_STAGE] = STAGE_DONE
        session_state[STATE_TUTORIAL_SEEN] = True
    elif base in {HYDRATE_SKIP, TOKEN_SKIP_STARTED}:
        session_state[STATE_TUTORIAL_SESSION_DISMISSED] = True
        session_state[STATE_ONBOARDING_STAGE] = STAGE_DISMISSED
        session_state[STATE_TUTORIAL_SEEN] = True
    elif started:
        session_state[STATE_ONBOARDING_STAGE] = STAGE_RUNNING
        session_state[STATE_TUTORIAL_SEEN] = True
    session_state[STATE_ONBOARDING_HYDRATED] = True


def _browser_bridge_available() -> bool:
    """False under AppTest, where no browser can answer the bridge."""
    try:
        from streamlit import runtime

        return bool(runtime.exists())
    except Exception:  # noqa: BLE001
        return False


def _read_query_token() -> str:
    try:
        return str(st.query_params.get(QUERY_PARAM) or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _clear_query_token() -> None:
    """Drop the transport param so a reload re-reads the durable record."""
    try:
        del st.query_params[QUERY_PARAM]
    except Exception:  # noqa: BLE001
        pass


def _bridge_script() -> str:
    return (
        "(function(){"
        "var w=window;try{var d=w.document;"
        "var marker='.st-key-cel_onboarding_hydrate';"
        "if(!d.querySelector(marker)&&w.parent&&w.parent!==w){"
        "var pd=w.parent.document;"
        "if(pd.querySelector(marker)){w=w.parent;}}}"
        "catch(e){w=window;}"
        "var token='new';"
        "try{var raw=w.localStorage.getItem(" + json.dumps(LOCAL_STORAGE_KEY) + ");"
        "if(raw){var r=JSON.parse(raw)||{};"
        "if(r.completed){token='done';}"
        "else if(r.dismissed){token=r.started?'skip-run':'skip';}"
        "else if(r.started){token='run';}"
        "if(r.applicability_hint_seen){token=token+'.h';}}}catch(e){token='new';}"
        "try{var url=new w.URL(w.location.href);"
        "if(url.searchParams.get(" + json.dumps(QUERY_PARAM) + ")){return;}"
        "url.searchParams.set(" + json.dumps(QUERY_PARAM) + ",token);"
        "var done=false;"
        "var go=function(){if(done)return;done=true;"
        "try{w.location.replace(url.toString());}catch(e2){}};"
        "var later=function(){if(w.setTimeout){w.setTimeout(go,50);}else{go();}};"
        "var d=w.document;"
        "if(!d||d.readyState==='complete'){later();}"
        "else{w.addEventListener('load',later);}}catch(e){}"
        "})();"
    )


def _persist_script(record: dict[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
    return (
        "(function(){"
        "var w=window;try{var d=w.document;"
        "var marker='.st-key-cel_onboarding_persist';"
        "if(!d.querySelector(marker)&&w.parent&&w.parent!==w){"
        "var pd=w.parent.document;"
        "if(pd.querySelector(marker)){w=w.parent;}}}"
        "catch(e){w=window;}"
        "try{w.localStorage.setItem(" + json.dumps(LOCAL_STORAGE_KEY) + ","
        + json.dumps(payload)
        + ");}catch(e){}"
        "})();"
    )


def _run_script(script: str, *, key: str) -> None:
    body = f"<script>\n{script}\n</script>"
    with st.container(key=key):
        try:
            st.html(body, unsafe_allow_javascript=True)
            return
        except TypeError:
            pass
        except Exception:  # noqa: BLE001
            pass
        components.html(body, height=0)


def hydrate_onboarding(session_state: Any) -> bool:
    """True once the durable record is known for this session.

    Returns False on the single run that asks the browser for it, so the
    welcome modal never flashes before the answer arrives.
    """
    ensure_onboarding_state(session_state)
    if bool(_ss_flag(session_state, STATE_ONBOARDING_HYDRATED)):
        return True
    if not _browser_bridge_available():
        session_state[STATE_ONBOARDING_HYDRATED] = True
        return True
    token = _read_query_token()
    if token:
        apply_hydration_token(session_state, token)
        _clear_query_token()
        return True
    _run_script(_bridge_script(), key="cel_onboarding_hydrate")
    return False


def persist_onboarding_record(session_state: Any) -> None:
    """Write the durable record whenever it changed in this session."""
    record = onboarding_record(session_state)
    if _ss_flag(session_state, STATE_ONBOARDING_PERSISTED, None) == record:
        return
    try:
        session_state[STATE_ONBOARDING_PERSISTED] = dict(record)
    except Exception:  # noqa: BLE001
        pass
    if not _browser_bridge_available():
        return
    _run_script(_persist_script(record), key="cel_onboarding_persist")


# --------------------------------------------------------------------------
# Copy
# --------------------------------------------------------------------------


def get_onboarding_copy(lang: str) -> dict[str, Any]:
    """Return customer-facing onboarding copy (pure, testable)."""
    steps = []
    for spec in ONBOARDING_STEPS:
        steps.append(
            {
                "id": spec["id"],
                "index": spec["index"],
                "title": t(spec["title_key"], lang),
                "body": t(spec["body_key"], lang),
                "progress": t(
                    "onb.progress",
                    lang,
                    current=spec["index"],
                    total=ONBOARDING_STEP_COUNT,
                ),
            }
        )
    scenes = []
    for spec in ONBOARDING_SCENES:
        scenes.append(
            {
                "id": spec["id"],
                "step": int(spec["step"]),
                "title": t(spec["title_key"], lang),
                "body": t(spec["body_key"], lang),
            }
        )
    return {
        "welcome_title": t("onb.welcome.title", lang),
        "welcome_body": t("onb.welcome.body", lang),
        "start_label": t("onb.welcome.start", lang),
        "later_label": t("onb.welcome.later", lang),
        "finish_label": t("onb.finish", lang),
        "steps": steps,
        "scenes": scenes,
        "version": ONBOARDING_VERSION,
    }


def onboarding_step_titles(lang: str) -> list[str]:
    return [step["title"] for step in get_onboarding_copy(lang)["steps"]]


def customer_copy_blob(lang: str) -> str:
    copy = get_onboarding_copy(lang)
    parts = [
        copy["welcome_title"],
        copy["welcome_body"],
        copy["start_label"],
        copy["later_label"],
        copy["finish_label"],
    ]
    for step in copy["steps"]:
        parts.extend([step["title"], step["body"], step["progress"]])
    for scene in copy["scenes"]:
        parts.extend([scene["title"], scene["body"]])
    return "\n".join(parts)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _inject_coach_runtime() -> None:
    """Inject the DOM-anchoring runtime into the Streamlit main document."""
    try:
        script = _COACH_JS_PATH.read_text(encoding="utf-8")
    except OSError:
        return
    stamp = hex(abs(hash(script)) & 0xFFFFFFFF)
    html_body = f"<!-- cel-onboarding-coach {stamp} -->\n<script>\n{script}\n</script>"
    with st.container(key="cel_onboarding_runtime"):
        try:
            st.html(html_body, unsafe_allow_javascript=True)
            return
        except TypeError:
            # Older Streamlit: fall back to an iframe that drives the parent.
            pass
        except Exception:  # noqa: BLE001 - restricted runtimes
            pass
        components.html(html_body, height=0)


def _on_welcome_dismiss() -> None:
    dismiss_onboarding(st.session_state)


def _render_welcome(lang: str) -> None:
    copy = get_onboarding_copy(lang)

    @st.dialog(copy["welcome_title"], on_dismiss=_on_welcome_dismiss)
    def _dialog() -> None:
        st.markdown(
            "<div class='cel-onb-welcome' data-cel-onboarding-welcome='1'></div>",
            unsafe_allow_html=True,
        )
        st.write(copy["welcome_body"])
        start_col, later_col = st.columns(2)
        with start_col:
            if st.button(
                copy["start_label"],
                type="primary",
                use_container_width=True,
                key="onboarding_welcome_start",
            ):
                start_onboarding(st.session_state)
                st.rerun()
        with later_col:
            if st.button(
                copy["later_label"],
                use_container_width=True,
                key="onboarding_welcome_later",
            ):
                dismiss_onboarding(st.session_state)
                st.rerun()

    _dialog()


def coach_config(scene: dict[str, Any] | int) -> dict[str, Any]:
    """Config handed to the DOM runtime for the current action scene."""
    spec = scene_for_step(scene) if isinstance(scene, int) else scene
    return {
        "step": int(spec["step"]),
        "id": str(spec["id"]),
        "major": str(step_by_index(int(spec["step"]))["id"]),
        "total": ONBOARDING_STEP_COUNT,
        "selectors": list(spec["selectors"]),
        "suppress": [],
        "routeSuppress": [],
        "pad": 8,
        "radius": 14,
        "maxMisses": 40,
        "version": ONBOARDING_VERSION,
    }


@contextmanager
def onboarding_target(name: str) -> Iterator[None]:
    """Wrap a live product region so the coachmark can measure the whole group."""
    safe = "".join(
        ch if ch.isalnum() or ch == "_" else "_" for ch in str(name).replace("-", "_")
    )
    with st.container(key=f"cel_onb_{safe}"):
        st.markdown(
            "<span data-cel-onboarding-target='"
            f"{html.escape(str(name), quote=True)}' aria-hidden='true'></span>",
            unsafe_allow_html=True,
        )
        yield


def _render_coachmark(scene: dict[str, Any], lang: str) -> None:
    step_no = int(scene["step"])
    copy = get_onboarding_copy(lang)
    progress = t(
        "onb.progress", lang, current=step_no, total=ONBOARDING_STEP_COUNT
    )
    config = html.escape(
        json.dumps(coach_config(scene), ensure_ascii=False), quote=True
    )
    title = t(scene["title_key"], lang)
    body = t(scene["body_key"], lang)
    with st.container(key="cel_onboarding_coach"):
        st.markdown(
            "<div class='cel-coach-anchor' data-cel-coach-config=\""
            f"{config}\" data-cel-coach-step='{html.escape(str(scene['id']))}' "
            f"data-cel-coach-index='{step_no}' aria-hidden='true'></div>"
            "<div class='cel-coach-card' role='note' aria-live='polite' "
            f"aria-label='{html.escape(title)}'>"
            f"<p class='cel-coach-progress'>{html.escape(progress)}</p>"
            f"<p class='cel-coach-title'>{html.escape(title)}</p>"
            f"<p class='cel-coach-body'>{html.escape(body)}</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        # Steps 1–4 carry progress, title and one line only. 稍後再說 lives on
        # the welcome modal; the last step is the single place with a button.
        if step_no >= ONBOARDING_STEP_COUNT:
            if st.button(
                copy["finish_label"],
                type="primary",
                use_container_width=True,
                key="onboarding_finish",
            ):
                complete_onboarding(st.session_state)
                st.rerun()


def render_onboarding(
    session_state: Any,
    lang: str,
    *,
    analysis_busy: bool = False,
) -> None:
    """Render the current onboarding surface for this run.

    Welcome is a modal. Every later step is a coachmark whose position is
    measured from the live DOM. Nothing is rendered once onboarding is
    completed or dismissed, so the runtime removes the spotlight itself.
    """
    ensure_onboarding_state(session_state)
    if not hydrate_onboarding(session_state):
        # Durable record still in flight: render nothing at all.
        return
    stage = onboarding_stage(session_state)
    persist_onboarding_record(session_state)
    if stage in {STAGE_DONE, STAGE_DISMISSED}:
        # Nothing is rendered, so the bound runtime removes the spotlight,
        # the coachmark and the dim on its next DOM observation.
        return
    if stage == STAGE_WELCOME:
        session_state[STATE_TUTORIAL_VISIBLE] = True
        _render_welcome(lang)
        return
    session_state[STATE_TUTORIAL_VISIBLE] = True
    session_state[STATE_OPEN_TUTORIAL] = False
    scene = resolve_onboarding_scene(session_state)
    step_no = int(scene["step"])
    session_state[STATE_ONBOARDING_STEP] = step_no
    session_state[STATE_TUTORIAL_STEP] = step_no
    session_state[STATE_ONBOARDING_SCENE] = scene["id"]
    if scene["id"] == SCENE_REVIEW_COVERAGE and _coverage_kpis_available(
        session_state
    ):
        session_state[STATE_ONBOARDING_COVERAGE_SEEN] = True
    _note_step_transition(session_state, step_no)
    if pending_onboarding_page(session_state):
        # A safe route change runs later in this same script pass; mounting a
        # coachmark that is about to be discarded would only flicker.
        return
    # Analysis owns the screen: keep the step, drop the coachmark.
    if not analysis_busy:
        _render_coachmark(scene, lang)
    _inject_coach_runtime()


def applicability_hint_pending(session_state: Any) -> bool:
    """True only on the customer's first visit to the requirements page."""
    ensure_onboarding_state(session_state)
    return not bool(_ss_flag(session_state, STATE_APPLICABILITY_HINT_SEEN))


def mark_applicability_hint_seen(session_state: Any) -> None:
    ensure_onboarding_state(session_state)
    try:
        session_state[STATE_APPLICABILITY_HINT_SEEN] = True
    except Exception:  # noqa: BLE001
        pass


def render_applicability_page_hint(lang: str) -> bool:
    """One short in-page hint, shown on the first visit only.

    Applicable requirements are not an onboarding step and never block a
    Scope 1 / Scope 2 calculation.
    """
    session_state = st.session_state
    if not applicability_hint_pending(session_state):
        return False
    st.markdown(
        "<p class='cel-page-hint' data-cel-page-hint='applicability'>"
        f"{html.escape(t('onb.applicability_hint', lang))}</p>",
        unsafe_allow_html=True,
    )
    mark_applicability_hint_seen(session_state)
    return True
