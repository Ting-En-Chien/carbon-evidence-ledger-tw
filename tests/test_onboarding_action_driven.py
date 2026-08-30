"""Action-driven first-run onboarding closure.

Covers the acceptance conditions that can be checked without a browser:
copy, step machine, product-state advancement, persistence, and the removal
of the screenshot-based runtime tutorial and the global glossary control.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from carbon_ledger.applicability import ApplicabilityAssessment
from carbon_ledger.company_master import CompanyMaster
from carbon_ledger.company_workspace import (
    CompanyWorkspace,
    workspace_id_for_company,
)
from carbon_ledger.inventory_boundary import (
    ReportingPeriod,
    initial_boundary_semantics_state,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.tutorial import (
    FORBIDDEN_CUSTOMER_TERMS,
    FORBIDDEN_ONBOARDING_PHRASES,
    HYDRATE_DONE,
    HYDRATE_NEW,
    HYDRATE_SKIP,
    ONBOARDING_STEP_COUNT,
    ONBOARDING_STEPS,
    PAGE_INTAKE,
    PAGE_OVERVIEW,
    SCENE_COMPANY_CONFIRMATION,
    SCENE_START_SETUP,
    SCENE_UBN_LOOKUP,
    STAGE_DISMISSED,
    STAGE_DONE,
    STAGE_RUNNING,
    STAGE_WELCOME,
    STATE_APPLICABILITY_HINT_SEEN,
    STATE_ONBOARDING_STAGE,
    STATE_TUTORIAL_COMPLETED,
    STATE_TUTORIAL_KEEP_OPEN,
    STATE_TUTORIAL_SESSION_DISMISSED,
    TOKEN_SKIP_STARTED,
    applicability_hint_pending,
    apply_hydration_token,
    coach_config,
    company_setup_complete,
    complete_onboarding,
    customer_copy_blob,
    dismiss_onboarding,
    get_onboarding_copy,
    mark_applicability_hint_seen,
    note_entered_company_setup,
    note_onboarding_upload_file,
    onboarding_completion,
    onboarding_record,
    onboarding_stage,
    onboarding_step_titles,
    pending_onboarding_page,
    record_onboarding_open_questions,
    record_token,
    request_onboarding,
    resolve_onboarding_scene,
    resolve_onboarding_step,
    result_ready,
    review_queue_complete,
    start_onboarding,
    step_page,
    upload_read_complete,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
UI = REPO_ROOT / "src" / "carbon_ledger" / "ui"
TUTORIAL_PY = UI / "tutorial.py"
COACH_JS = UI / "onboarding_coach.js"
CSS = UI / "visual_system.css"
APP_PY = REPO_ROOT / "streamlit_app.py"
COMPONENTS_PY = UI / "components.py"
ZH = "zh-TW"
EN = "en"

UBN = "12345675"
FILE_A = "hash-file-a"
FILE_B = "hash-file-b"


def _period() -> ReportingPeriod:
    return ReportingPeriod.confirmed(
        reporting_year_suggested=2026,
        reporting_year_confirmed=2026,
        period_start_confirmed="2026-01-01",
        period_end_confirmed="2026-12-31",
    )


def _assessment() -> ApplicabilityAssessment:
    return ApplicabilityAssessment(
        assessment_timestamp="2026-08-29T00:00:00Z",
        reporting_year=2026,
        company_profile_snapshot={},
        obligations={},
        rule_ids_used=[],
        rule_versions_used={},
        regulatory_freshness_snapshot={},
        result_statuses={},
    )


def _company() -> CompanyMaster:
    return CompanyMaster(
        company_id=f"co_{UBN}",
        company_name="測試公司",
        unified_business_number=UBN,
        listing_status="TWSE",
    )


def _confirm_company_identity(state: dict) -> None:
    """Customer-confirmed identity, without any boundary confirmation."""
    state["company_master"] = {
        "company_name": "測試公司",
        "unified_business_number": UBN,
        "company_id": f"co_{UBN}",
        "customer_confirmed_at": "2026-08-29T00:00:00Z",
    }


def _seed_confirmed_boundary(root: Path) -> str:
    """Write the wizard's own locally confirmed period package."""
    workspace_id = workspace_id_for_company(taiwan_ubn=UBN)
    period = _period()
    state = initial_boundary_semantics_state(
        assessment=_assessment(),
        company=_company(),
        facilities=[],
        workspace_id=workspace_id,
        reporting_period=period,
    )
    candidate = replace(
        state,
        responsible_contact_name="王小明",
        responsible_job_title="永續管理師",
    ).locally_confirmed()
    CompanyWorkspace(root, workspace_id).append_semantics_current(candidate)
    return period.reporting_period_id


@pytest.fixture()
def workspace_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "company_workspaces"
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(root))
    return root


def _setup_done(root: Path) -> dict:
    """Session whose company, ReportingPeriod and scope are all confirmed."""
    period_id = _seed_confirmed_boundary(root)
    workspace_id = workspace_id_for_company(taiwan_ubn=UBN)
    state: dict = {}
    _confirm_company_identity(state)
    # The wizard keys its active period on the reporting year in play.
    state["company_profile"] = {"reporting_year": 2026}
    state[f"boundary_active_period_{workspace_id}_2026"] = period_id
    return state


def _uploaded_result(state: dict, *, file_hash: str = FILE_A) -> None:
    """Session that finished a real uploaded analysis for one file."""
    state["uploaded_file_hash"] = file_hash
    state["uploaded_table"] = object()
    state["validated_intake_result"] = object()
    state["pipeline_result"] = object()
    state["analysis_data_source"] = "uploaded"
    state["analysis_source_file_hash"] = file_hash
    state["uploaded_analysis_completed"] = True
    state["analysis_phase"] = "result_reveal"


# --------------------------------------------------------------------------
# Copy
# --------------------------------------------------------------------------


def test_welcome_copy_matches_specification() -> None:
    zh = get_onboarding_copy(ZH)
    assert zh["welcome_title"] == "完成第一筆碳排計算"
    assert zh["welcome_body"] == (
        "準備一份公司現有的 Excel 或 CSV，我們會帶你完成設定、確認與計算。"
    )
    assert zh["start_label"] == "開始"
    assert zh["later_label"] == "稍後再說"
    assert zh["finish_label"] == "完成"

    en = get_onboarding_copy(EN)
    assert en["welcome_title"] == "Complete your first emissions calculation"
    assert en["welcome_body"] == (
        "Have an Excel or CSV ready. We’ll guide you through setup, "
        "review, and calculation."
    )
    assert en["start_label"] == "Start"
    assert en["later_label"] == "Not now"
    assert en["finish_label"] == "Finish"


def test_five_steps_with_one_title_and_one_sentence() -> None:
    assert ONBOARDING_STEP_COUNT == 5
    assert [spec["id"] for spec in ONBOARDING_STEPS] == [
        "company_setup",
        "upload_data",
        "review_data",
        "start_calculation",
        "view_results",
    ]
    assert onboarding_step_titles(ZH) == [
        "完成公司設定",
        "上傳活動資料",
        "確認資料內容",
        "開始計算",
        "查看計算結果",
    ]
    assert onboarding_step_titles(EN) == [
        "Complete company setup",
        "Upload activity data",
        "Review your data",
        "Start calculation",
        "View your results",
    ]
    for lang in (ZH, EN):
        for step in get_onboarding_copy(lang)["steps"]:
            assert step["title"].strip()
            assert step["body"].strip()
            assert "\n" not in step["body"]


def test_progress_label_is_compact() -> None:
    assert t("onb.progress", ZH, current=2, total=5) == "第 2／5 步"
    assert t("onb.progress", EN, current=2, total=5) == "Step 2 of 5"


def test_onboarding_copy_has_no_legal_or_internal_language() -> None:
    blob = customer_copy_blob(ZH) + "\n" + customer_copy_blob(EN)
    for phrase in FORBIDDEN_ONBOARDING_PHRASES:
        assert phrase not in blob, phrase
    for term in FORBIDDEN_CUSTOMER_TERMS:
        assert term not in blob, term
    for phrase in (
        "適用要求與重要時程",
        "名詞解釋",
        "Glossary",
        "下一步",
        "確認公司、報導期間與計算範圍。",
        "Confirm the company, reporting period, and calculation scope.",
        "Next",
        "上一步",
        "Previous",
    ):
        assert phrase not in blob, phrase


def test_applicability_hint_is_one_short_in_page_line() -> None:
    assert t("onb.applicability_hint", ZH) == "查看目前可能適用的要求與重要時程。"
    assert t("onb.applicability_hint", EN) == (
        "Review requirements and key dates that may apply to your company."
    )


# --------------------------------------------------------------------------
# Stage transitions
# --------------------------------------------------------------------------


def test_first_run_starts_at_welcome_and_start_unmounts_it() -> None:
    state: dict = {}
    assert onboarding_stage(state) == STAGE_WELCOME
    start_onboarding(state)
    assert onboarding_stage(state) == STAGE_RUNNING
    assert state[STATE_ONBOARDING_STAGE] == STAGE_RUNNING


def test_dismiss_and_complete_are_sticky_across_version_bumps() -> None:
    dismissed: dict = {}
    dismissed["tutorial_keep_open"] = True
    dismiss_onboarding(dismissed)
    assert onboarding_stage(dismissed) == STAGE_DISMISSED
    dismissed["onboarding_version"] = "some-older-version"
    assert onboarding_stage(dismissed) == STAGE_DISMISSED
    assert dismissed[STATE_TUTORIAL_SESSION_DISMISSED] is True
    assert dismissed[STATE_TUTORIAL_KEEP_OPEN] is False

    completed: dict = {}
    completed["tutorial_keep_open"] = True
    complete_onboarding(completed)
    assert onboarding_stage(completed) == STAGE_DONE
    completed["onboarding_version"] = "some-older-version"
    assert onboarding_stage(completed) == STAGE_DONE
    assert completed[STATE_TUTORIAL_COMPLETED] is True
    assert completed[STATE_TUTORIAL_KEEP_OPEN] is False


def test_replay_resumes_at_earliest_unfinished_step(workspace_root) -> None:
    state = _setup_done(workspace_root)
    start_onboarding(state)
    complete_onboarding(state)
    assert onboarding_stage(state) == STAGE_DONE
    request_onboarding(state)
    assert onboarding_stage(state) == STAGE_RUNNING
    # Company setup is already done, so it is never asked for again.
    assert resolve_onboarding_step(state) == 2


def test_replay_shows_results_step_when_everything_is_done(workspace_root) -> None:
    state = _setup_done(workspace_root)
    _uploaded_result(state)
    start_onboarding(state)
    complete_onboarding(state)
    request_onboarding(state)
    assert resolve_onboarding_step(state) == 5


def test_reopen_routes_to_the_page_that_owns_the_step(workspace_root) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    record_onboarding_open_questions(state, 2, file_hash=FILE_A)
    state["uploaded_file_hash"] = FILE_A
    request_onboarding(state)
    assert resolve_onboarding_step(state) == 3
    assert pending_onboarding_page(state) == PAGE_INTAKE

    fresh: dict = {}
    request_onboarding(fresh)
    assert pending_onboarding_page(fresh) == PAGE_OVERVIEW


def test_step_pages_match_the_real_routes() -> None:
    assert step_page(1) == PAGE_OVERVIEW
    assert step_page(2) == PAGE_INTAKE
    assert step_page(3) == PAGE_INTAKE
    assert step_page(4) == PAGE_INTAKE
    assert step_page(5) == PAGE_OVERVIEW


# --------------------------------------------------------------------------
# Step 1 — authoritative company setup
# --------------------------------------------------------------------------


def test_step_one_needs_confirmed_identity_period_and_scope(workspace_root) -> None:
    assert company_setup_complete({}) is False
    # A saved profile plus an applicability assessment is NOT enough: neither
    # the ReportingPeriod nor the inventory scope is confirmed yet.
    partial: dict = {
        "company_profile": {"company_name": "測試公司"},
        "applicability_assessment": object(),
        "company_profile_editing": False,
    }
    _confirm_company_identity(partial)
    assert company_setup_complete(partial) is False
    assert resolve_onboarding_step(partial) == 1
    # Same session once the wizard confirmed the period package.
    ready = _setup_done(workspace_root)
    assert company_setup_complete(ready) is True


def test_step_one_ignores_applicability_completion(workspace_root) -> None:
    """Applicable requirements must never gate a Scope 1 / Scope 2 run."""
    state = _setup_done(workspace_root)
    assert "applicability_assessment" not in state
    assert company_setup_complete(state) is True
    assert resolve_onboarding_step(state) == 2


def test_step_one_never_targets_the_whole_wizard() -> None:
    config = coach_config(1)
    joined = " ".join(config["selectors"])
    assert ".st-key-cel_boundary_wizard_root" not in joined
    assert "company-boundary" not in joined
    assert "[data-cel-page='applicability']" not in joined


def test_step_one_follows_the_customer_into_company_setup() -> None:
    """Entering company setup must never hide the tour."""
    config = coach_config(1)
    assert config["suppress"] == []
    assert config["routeSuppress"] == []
    assert config["id"] == SCENE_START_SETUP
    assert "start-setup" in " ".join(config["selectors"])


def test_company_setup_scenes_follow_real_product_state() -> None:
    state: dict = {}
    assert resolve_onboarding_scene(state)["id"] == SCENE_START_SETUP
    note_entered_company_setup(state)
    assert resolve_onboarding_scene(state)["id"] == SCENE_UBN_LOOKUP
    state["company_master"] = {"company_name": "Example Co"}
    assert resolve_onboarding_scene(state)["id"] == SCENE_COMPANY_CONFIRMATION
    state["company_master"] = {
        "company_name": "Example Co",
        "customer_confirmed_at": "2026-01-01T00:00:00Z",
    }
    assert resolve_onboarding_scene(state)["id"] == "company_details"
    state["applicability_wizard_step"] = 2
    assert resolve_onboarding_scene(state)["id"] == "additional_information"


def test_scene_copy_describes_the_current_action() -> None:
    zh = get_onboarding_copy(ZH)
    by_id = {scene["id"]: scene for scene in zh["scenes"]}
    assert by_id[SCENE_START_SETUP]["title"] == "開始公司設定"
    assert by_id[SCENE_UBN_LOOKUP]["title"] == "查詢公司"
    assert "8 位" in by_id[SCENE_UBN_LOOKUP]["body"]
    assert by_id[SCENE_COMPANY_CONFIRMATION]["title"] == "核對公司資料"
    assert "這是我的公司" in by_id[SCENE_COMPANY_CONFIRMATION]["body"]
    assert "確認公司、報導期間與計算範圍。" not in by_id[SCENE_START_SETUP]["body"]


def test_finishing_setup_routes_to_the_upload_page(workspace_root) -> None:
    from carbon_ledger.ui.tutorial import _note_step_transition

    state = _setup_done(workspace_root)
    _note_step_transition(state, 1)
    assert pending_onboarding_page(state) == ""
    _note_step_transition(state, 2)
    assert pending_onboarding_page(state) == PAGE_INTAKE


# --------------------------------------------------------------------------
# Steps 2–4 — bound to the current file
# --------------------------------------------------------------------------


def test_step_two_waits_for_a_file_that_was_actually_read(workspace_root) -> None:
    state = _setup_done(workspace_root)
    assert resolve_onboarding_step(state) == 2
    assert upload_read_complete(state) is False
    # Visiting the upload page or opening the picker changes nothing.
    state["intake_wizard_step"] = 1
    assert resolve_onboarding_step(state) == 2
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    assert upload_read_complete(state) is True
    assert resolve_onboarding_step(state) == 3


def test_step_three_holds_until_this_file_queue_is_cleared(workspace_root) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    record_onboarding_open_questions(state, 3, file_hash=FILE_A)
    assert review_queue_complete(state) is False
    assert resolve_onboarding_step(state) == 3
    record_onboarding_open_questions(state, 1, file_hash=FILE_A)
    assert resolve_onboarding_step(state) == 3
    record_onboarding_open_questions(state, 0, file_hash=FILE_A)
    assert review_queue_complete(state) is True
    assert resolve_onboarding_step(state) == 4


def test_step_three_is_skipped_when_this_file_has_no_questions(
    workspace_root,
) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    record_onboarding_open_questions(state, 0, file_hash=FILE_A)
    assert resolve_onboarding_step(state) == 4


def test_a_new_file_never_inherits_the_previous_queue_count(workspace_root) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    record_onboarding_open_questions(state, 0, file_hash=FILE_A)
    assert resolve_onboarding_step(state) == 4

    # A different file is selected: the previous "0 questions" is dropped and
    # step 3 waits for this file's own list_exceptions() run.
    state["uploaded_file_hash"] = FILE_B
    note_onboarding_upload_file(state, FILE_B)
    assert review_queue_complete(state) is False
    assert resolve_onboarding_step(state) == 3
    record_onboarding_open_questions(state, 2, file_hash=FILE_B)
    assert resolve_onboarding_step(state) == 3
    record_onboarding_open_questions(state, 0, file_hash=FILE_B)
    assert resolve_onboarding_step(state) == 4


def test_a_previous_files_nonzero_count_cannot_hold_the_new_file(
    workspace_root,
) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    record_onboarding_open_questions(state, 5, file_hash=FILE_A)
    state["uploaded_file_hash"] = FILE_B
    note_onboarding_upload_file(state, FILE_B)
    record_onboarding_open_questions(state, 0, file_hash=FILE_B)
    assert resolve_onboarding_step(state) == 4


def test_unobserved_queue_never_skips_step_three(workspace_root) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_B
    # Observation recorded for another file only.
    record_onboarding_open_questions(state, 0, file_hash=FILE_A)
    assert review_queue_complete(state) is False
    assert resolve_onboarding_step(state) == 3


def test_validated_intake_alone_does_not_clear_the_review_step(
    workspace_root,
) -> None:
    """Validation happens before the questions are answered."""
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    state["validated_intake_result"] = object()
    assert review_queue_complete(state) is False
    assert resolve_onboarding_step(state) == 3


def test_step_three_spotlight_includes_the_real_confirm_control() -> None:
    selectors = coach_config(3)["selectors"]
    joined = " ".join(selectors)
    assert "recognition-question" in joined
    assert "recognition-apply" in joined or "recognition-question" in joined


# --------------------------------------------------------------------------
# Steps 4–5 — bound to the current uploaded result
# --------------------------------------------------------------------------


def test_step_five_requires_a_ready_result(workspace_root) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    state["validated_intake_result"] = object()
    record_onboarding_open_questions(state, 0, file_hash=FILE_A)
    assert result_ready(state) is False
    assert resolve_onboarding_step(state) == 4
    _uploaded_result(state)
    assert result_ready(state) is True
    assert resolve_onboarding_step(state) == 5


def test_demo_result_never_completes_the_calculation_step(workspace_root) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    record_onboarding_open_questions(state, 0, file_hash=FILE_A)
    state["pipeline_result"] = object()
    state["analysis_data_source"] = "demo"
    state["analysis_source_file_hash"] = ""
    state["uploaded_analysis_completed"] = False
    assert result_ready(state) is False
    assert resolve_onboarding_step(state) == 4


def test_previous_file_result_never_completes_the_new_file(workspace_root) -> None:
    state = _setup_done(workspace_root)
    _uploaded_result(state, file_hash=FILE_A)
    assert result_ready(state) is True
    # A different file is selected: the old result loses its qualification.
    state["uploaded_file_hash"] = FILE_B
    note_onboarding_upload_file(state, FILE_B)
    assert result_ready(state) is False
    record_onboarding_open_questions(state, 0, file_hash=FILE_B)
    assert resolve_onboarding_step(state) == 4


def test_running_analysis_never_shows_the_results_step(workspace_root) -> None:
    state = _setup_done(workspace_root)
    _uploaded_result(state)
    for phase in ("analyzing", "overlay_closing"):
        state["analysis_phase"] = phase
        assert result_ready(state) is False
        assert resolve_onboarding_step(state) == 4
    state["analysis_phase"] = "result_reveal"
    state["analysis_running"] = True
    assert result_ready(state) is False
    state["analysis_running"] = False
    state["navigate_to_results_after_analysis"] = True
    assert result_ready(state) is False
    state["navigate_to_results_after_analysis"] = False
    assert result_ready(state) is True
    assert resolve_onboarding_step(state) == 5


def test_view_results_never_completes_from_product_state(workspace_root) -> None:
    state = _setup_done(workspace_root)
    _uploaded_result(state)
    assert onboarding_completion(state)["view_results"] is False
    # Only the explicit 完成 action ends the flow.
    complete_onboarding(state)
    assert onboarding_stage(state) == STAGE_DONE


def test_step_is_stable_across_reruns_and_language_changes(workspace_root) -> None:
    state = _setup_done(workspace_root)
    state["uploaded_table"] = object()
    state["uploaded_file_hash"] = FILE_A
    record_onboarding_open_questions(state, 2, file_hash=FILE_A)
    first = resolve_onboarding_step(state)
    state["ui_language"] = EN
    state["current_page"] = "app_pages/dashboard.py"
    assert resolve_onboarding_step(state) == first


# --------------------------------------------------------------------------
# Durable state
# --------------------------------------------------------------------------


def test_durable_record_only_carries_onboarding_flags() -> None:
    state: dict = {}
    record = onboarding_record(state)
    assert set(record) == {
        "started",
        "completed",
        "dismissed",
        "version",
        "applicability_hint_seen",
    }
    assert record["started"] is False
    assert record["completed"] is False
    assert record["dismissed"] is False


def test_completed_survives_a_reload() -> None:
    state: dict = {}
    start_onboarding(state)
    complete_onboarding(state)
    token = record_token(onboarding_record(state))
    assert token == HYDRATE_DONE

    reloaded: dict = {}
    apply_hydration_token(reloaded, token)
    assert onboarding_stage(reloaded) == STAGE_DONE
    # A version bump must not replay the flow.
    reloaded["onboarding_version"] = "newer-version"
    assert onboarding_stage(reloaded) == STAGE_DONE


def test_dismissed_survives_a_reload_and_can_be_reopened() -> None:
    state: dict = {}
    dismiss_onboarding(state)
    assert record_token(onboarding_record(state)) == HYDRATE_SKIP

    started: dict = {}
    start_onboarding(started)
    dismiss_onboarding(started)
    token = record_token(onboarding_record(started))
    assert token == TOKEN_SKIP_STARTED

    reloaded: dict = {}
    apply_hydration_token(reloaded, token)
    assert onboarding_stage(reloaded) == STAGE_DISMISSED
    # 操作教學 still reopens it, resuming rather than replaying Welcome.
    request_onboarding(reloaded)
    assert onboarding_stage(reloaded) == STAGE_RUNNING


def test_fresh_browser_hydrates_as_a_first_run() -> None:
    state: dict = {}
    assert record_token(onboarding_record(state)) == HYDRATE_NEW
    apply_hydration_token(state, HYDRATE_NEW)
    assert onboarding_stage(state) == STAGE_WELCOME


def test_applicability_hint_seen_is_durable() -> None:
    state: dict = {}
    state[STATE_APPLICABILITY_HINT_SEEN] = True
    token = record_token(onboarding_record(state))
    assert token.endswith(".h")
    reloaded: dict = {}
    apply_hydration_token(reloaded, token)
    assert reloaded[STATE_APPLICABILITY_HINT_SEEN] is True


def test_applicability_hint_is_shown_once() -> None:
    state: dict = {}
    assert applicability_hint_pending(state) is True
    mark_applicability_hint_seen(state)
    assert applicability_hint_pending(state) is False
    # Never becomes an onboarding step.
    assert all(spec["id"] != "applicability" for spec in ONBOARDING_STEPS)


def test_bridge_stores_nothing_sensitive() -> None:
    from carbon_ledger.ui.tutorial import _bridge_script, _persist_script

    script = _bridge_script() + _persist_script(onboarding_record({}))
    for token in ("company", "ubn", "emission", "tco2e", "file_name", "pipeline"):
        assert token not in script.lower(), token


# --------------------------------------------------------------------------
# DOM anchoring contract
# --------------------------------------------------------------------------


def test_every_step_anchors_to_real_product_selectors() -> None:
    for index in range(1, ONBOARDING_STEP_COUNT + 1):
        config = coach_config(index)
        assert config["step"] == index
        assert config["total"] == ONBOARDING_STEP_COUNT
        assert config["radius"] == 14
        assert config["selectors"]
        for selector in config["selectors"]:
            assert selector.startswith((".st-key-", "[data-", ".cel-"))


def test_results_step_highlights_only_the_hero() -> None:
    config = coach_config(5)
    joined = " ".join(config["selectors"])
    assert "results-hero" in joined
    assert "results-evidence" not in joined
    assert "results-reports" not in joined


def test_runtime_measures_live_dom_and_never_paints_a_stale_box() -> None:
    js = COACH_JS.read_text(encoding="utf-8")
    assert "getBoundingClientRect" in js
    assert "MutationObserver" in js
    assert "requestAnimationFrame" in js
    # Safe pause instead of a misplaced highlight.
    assert "maxMisses" in js
    assert "data-cel-coach-paused" in js
    # No fixed sleeps and no normalized screenshot coordinates.
    assert "setTimeout" not in js
    assert "normalized" not in js


def test_runtime_steps_aside_inside_the_real_setup_flow() -> None:
    js = COACH_JS.read_text(encoding="utf-8")
    assert "function suppressed(" in js
    assert "cfg.suppress" in js
    assert "data-cel-coach-suppressed" in js


def test_runtime_keeps_the_target_clickable_and_unmounts_cleanly() -> None:
    css = CSS.read_text(encoding="utf-8")
    spotlight = css.split(".cel-coach-spotlight {", 1)[1].split("}", 1)[0]
    assert "pointer-events: none;" in spotlight
    assert "border-radius: 14px;" in spotlight
    assert "border-radius: 999px" not in spotlight
    js = COACH_JS.read_text(encoding="utf-8")
    assert "function teardown()" in js
    assert "removeChild" in js


def test_coachmark_is_hidden_until_a_target_is_found() -> None:
    css = CSS.read_text(encoding="utf-8")
    host = css.split(".st-key-cel_onboarding_coach {", 1)[1].split("}", 1)[0]
    # Default state must be invisible, inert and parked off-viewport so a
    # missing target can never leave bare card text in the page flow.
    assert "position: fixed !important;" in host
    assert "visibility: hidden !important;" in host
    assert "opacity: 0 !important;" in host
    assert "pointer-events: none !important;" in host
    assert "left: -10000px !important;" in host
    assert "top: -10000px !important;" in host
    ready = css.split('.st-key-cel_onboarding_coach[data-cel-coach-ready="1"] {', 1)[
        1
    ].split("}", 1)[0]
    assert "visibility: visible !important;" in ready
    assert "opacity: 1 !important;" in ready
    assert "pointer-events: auto !important;" in ready


def test_coachmark_copy_is_not_clipped_by_streamlit_block_margins() -> None:
    css = CSS.read_text(encoding="utf-8")
    marker = (
        '.st-key-cel_onboarding_coach [data-testid="stMarkdownContainer"] {\n'
        "  margin-bottom: 0 !important;\n}"
    )
    assert marker in css
    element = (
        '.st-key-cel_onboarding_coach > [data-testid="stElementContainer"] {\n'
        "  margin: 0 !important;\n}"
    )
    assert element in css


def test_runtime_hides_every_host_before_it_can_be_misplaced() -> None:
    js = COACH_JS.read_text(encoding="utf-8")
    assert "function promoteGroup(" in js
    assert "function contentBox(" in js
    assert "function collectProtected(" in js
    assert "function mainSafeRect(" in js
    assert "function visibleSidebarRect(" in js
    assert "stSidebar" in js
    assert "DIR_PREF" in js
    assert "if (b.space !== a.space)" in js
    assert "function hideAllHosts(" in js
    assert "function pickHost(" in js
    assert "function routeSuppressed(" in js
    # hideHost must make the host invisible, inert and off-viewport.
    hide = js.split("function hideHost(", 1)[1].split("\n  function ", 1)[0]
    assert 'removeAttribute("data-cel-coach-ready")' in hide
    assert 'setProperty("visibility", "hidden", "important")' in hide
    assert 'setProperty("opacity", "0", "important")' in hide
    assert 'setProperty("pointer-events", "none", "important")' in hide
    assert "OFFSCREEN" in hide
    # teardown clears the spotlight and every stale host.
    teardown = js.split("function teardown()", 1)[1].split("\n  function ", 1)[0]
    assert "removeSpotlight()" in teardown
    assert "hideAllHosts()" in teardown
    # A missing target hides on the first sync; maxMisses only stops retries.
    sync = js.split("function sync(force)", 1)[1].split("\n  function ", 1)[0]
    missing = sync.split("var target = findTarget(", 1)[1]
    assert "hideAllHosts();" in missing.split("if (state.misses >=", 1)[0]
    # Suppression is decided before any target lookup.
    assert sync.index("routeSuppressed(cfg.routeSuppress)") < sync.index(
        "var target = findTarget("
    )
    assert "showHost(liveHost)" in sync or "showHost(host)" in sync


def test_no_step_is_suppressed_by_a_route_or_a_wizard() -> None:
    """Entering a product flow repositions the hint; it never hides the tour."""
    for spec in ONBOARDING_STEPS:
        assert not spec.get("route_suppress"), spec["id"]
        assert not spec.get("suppress"), spec["id"]


# --------------------------------------------------------------------------
# Removals
# --------------------------------------------------------------------------


def test_screenshot_based_runtime_tutorial_is_gone() -> None:
    assert not (UI / "tutorial_manifest.py").exists()
    assert not (UI / "tutorial_capture.py").exists()
    assert not (UI / "assets" / "tutorial").exists()
    source = TUTORIAL_PY.read_text(encoding="utf-8")
    for token in (
        "capture_manifest",
        "cel-tour-shot",
        "data:image/png;base64",
        "_image_data_uri",
        "prev_label",
        "next_label",
    ):
        assert token not in source, token


def test_steps_one_to_four_have_no_next_control() -> None:
    source = TUTORIAL_PY.read_text(encoding="utf-8")
    assert "tutorial_next" not in source
    assert "tutorial_prev" not in source
    assert "set_tutorial_step" not in source
    assert "onboarding_later" not in source
    # Welcome 開始 / 稍後再說 plus the single 完成 on the last coachmark.
    assert source.count("st.button(") == 3
    coach = source.split("def _render_coachmark(", 1)[1]
    assert coach.count("st.button(") == 1
    assert "onboarding_finish" in coach


def test_global_glossary_control_removed_from_customer_chrome() -> None:
    components = COMPONENTS_PY.read_text(encoding="utf-8")
    header = components.split("def render_global_header(", 1)[1].split(
        "\ndef ", 1
    )[0]
    assert "render_glossary_popover" not in header
    assert "gloss_col" not in header
    sidebar = components.split("def render_sidebar_help(", 1)[1]
    assert "is_admin_mode" in sidebar
    assert "sidebar_tutorial_link" in sidebar
    # Underlying glossary data and per-term help stay available.
    assert (UI / "glossary.py").is_file()


def test_app_renders_onboarding_before_navigation() -> None:
    app = APP_PY.read_text(encoding="utf-8")
    assert "render_onboarding(" in app
    assert app.index("render_onboarding(") < app.index("navigation.run()")
    assert "analysis_busy=_analysis_busy" in app


def test_queued_route_runs_between_page_registration_and_run() -> None:
    """Never mount the old page next to the new one in the same pass."""
    app = APP_PY.read_text(encoding="utf-8")
    assert "run_pending_onboarding_navigation(st.session_state)" in app
    assert app.index("navigation = st.navigation(") < app.index(
        "run_pending_onboarding_navigation(st.session_state)"
    )
    assert app.index("run_pending_onboarding_navigation(st.session_state)") < app.index(
        "navigation.run()"
    )
