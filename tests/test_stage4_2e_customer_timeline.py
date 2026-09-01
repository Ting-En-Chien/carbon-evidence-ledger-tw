"""Stage 4.2E — customer-language cleanup and IFRS disclosure timeline."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from carbon_ledger.applicability import (
    OBLIGATION_IFRS,
    CompanyProfile,
    assess_applicability,
)
from carbon_ledger.company_lookup import STUB_SEVEN_UBN, stub_factories
from carbon_ledger.company_master import (
    FacilityMaster,
    confirm_all_operating,
    exception_navigation_blocked,
    mark_exception_drafts_dirty,
    reconcile_facilities,
)
from carbon_ledger.ifrs_timeline import (
    CGC_4386_OFFICIAL_TITLE,
    FIRST_STAGE_ADOPTION_RULE_ID,
    FIRST_STAGE_MIN_CAPITAL_TWD,
    FSC_OFFICIAL_TITLE,
    MILESTONE_CURRENT,
    MILESTONE_PAST,
    MILESTONE_UPCOMING,
    MODE_BETWEEN_WINDOWS,
    PHASE_FIRST,
    SOURCE_RETRIEVED_CGC_4386,
    SOURCE_RETRIEVED_FSC,
    SOURCE_RETRIEVED_TWSE_EXAMPLE,
    TIMELINE_VERSION,
    TWSE_ARTICLE_OFFICIAL_TITLE,
    build_first_stage_timeline,
    first_stage_timeline_from_assessment,
    timeline_animation_plan,
    timeline_run_identity,
)
from carbon_ledger.ui.customer_presenters import (
    customer_copy_violations,
    present_assessment,
)
from carbon_ledger.ui.enterprise import ifrs_timeline_markup
from carbon_ledger.ui.i18n import MESSAGES, t
from carbon_ledger.ui.motion import ifrs_timeline_should_play

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH = "zh-TW"
EN = "en"
JS = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "ifrs_timeline.js"
APL = REPO_ROOT / "app_pages" / "applicability.py"
TIMELINE_PY = REPO_ROOT / "src" / "carbon_ledger" / "ifrs_timeline.py"
REVIEW_DATE = date(2026, 8, 17)
CJK = re.compile(r"[\u4e00-\u9fff]")
SHORT_ACTIONS_ZH = (
    "成立專案小組、完成初步盤點",
    "盤點資料並調整流程",
    "試編永續資訊專章",
    "完成首次申報",
    "視情況補交確信報告",
    "納入 Scope 3 揭露",
)


def _fresh_ok(repo_root=None, required_source_ids=None, **kwargs):
    return {
        "analysis_allowed": True,
        "state": "CURRENT",
        "overall_regulatory_freshness": "CURRENT",
        "last_successful_check_at": "2026-08-12T00:00:00Z",
        "last_global_check_at": "2026-08-12T00:00:00Z",
        "changes_pending_review": 0,
        "state_source": "durable_persisted_state",
        "required_source_ids": list(required_source_ids or []),
    }


def _listed_12b() -> CompanyProfile:
    return CompanyProfile(
        company_name="timeline-co",
        reporting_year=2026,
        entity_type="general_listed_company",
        listing_status="TWSE",
        paid_in_capital_twd=12_000_000_000,
        jurisdiction="TW",
        has_taiwan_facilities="YES",
        received_verification_requirement="NO",
        received_environmental_authority_inventory_notice="NO",
    )


def _assess(profile: CompanyProfile):
    return assess_applicability(
        profile,
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )


def _timeline(*, as_of=REVIEW_DATE, lang=ZH):
    return build_first_stage_timeline(
        ubn="12345675",
        as_of=as_of,
        lang=lang,
    )


def test_nt12_billion_maps_to_first_phase() -> None:
    assert 12_000_000_000 >= FIRST_STAGE_MIN_CAPITAL_TWD
    assessment = _assess(_listed_12b())
    ifrs = assessment.obligation(OBLIGATION_IFRS)
    assert ifrs is not None
    assert FIRST_STAGE_ADOPTION_RULE_ID in ifrs.applied_rule_ids
    assert ifrs.effective_reporting_year == 2026
    assert ifrs.first_filing_year == 2027
    view = first_stage_timeline_from_assessment(
        assessment, ubn="12345675", as_of=REVIEW_DATE, lang=ZH
    )
    assert view is not None


def test_special_share_case_suppresses_confident_timeline() -> None:
    """Do not invent 令第 7 點 net-worth substitution in the presentation layer."""
    profile = CompanyProfile(
        company_name="timeline-co",
        reporting_year=2026,
        entity_type="general_listed_company",
        listing_status="TWSE",
        paid_in_capital_twd=12_000_000_000,
        has_no_par_value_shares="TRUE",
        net_worth_twd=None,
        jurisdiction="TW",
        has_taiwan_facilities="YES",
        received_verification_requirement="NO",
        received_environmental_authority_inventory_notice="NO",
    )
    assessment = _assess(profile)
    view = first_stage_timeline_from_assessment(
        assessment, ubn="12345675", as_of=REVIEW_DATE, lang=ZH
    )
    assert view is None


def test_phase_two_capital_does_not_receive_first_stage_timeline() -> None:
    profile = CompanyProfile(
        company_name="timeline-co",
        reporting_year=2026,
        entity_type="general_listed_company",
        listing_status="TWSE",
        paid_in_capital_twd=6_000_000_000,
        jurisdiction="TW",
        has_taiwan_facilities="YES",
        received_verification_requirement="NO",
        received_environmental_authority_inventory_notice="NO",
    )
    assessment = _assess(profile)
    ifrs = assessment.obligation(OBLIGATION_IFRS)
    assert ifrs is not None
    assert FIRST_STAGE_ADOPTION_RULE_ID not in ifrs.applied_rule_ids
    assert (
        first_stage_timeline_from_assessment(
            assessment, ubn="12345675", as_of=REVIEW_DATE, lang=ZH
        )
        is None
    )


def test_first_phase_timeline_has_six_milestones() -> None:
    view = _timeline()
    assert view is not None
    assert len(view.milestones) == 6
    markup = ifrs_timeline_markup(view, ZH, play=False, initial_pct=view.progress_pct)
    assert markup.count("data-cel-timeline-marker=") == 6
    assert "data-cel-timeline-count='6'" in markup
    assert markup.count("data-cel-timeline-dot='desktop'") == 6
    assert markup.count("data-cel-timeline-dot='mobile'") == 6


def test_review_date_maps_to_milestone_three() -> None:
    view = _timeline(as_of=date(2026, 8, 17))
    assert view is not None
    assert view.current_index == 2
    assert view.in_active_window is True
    current = view.milestones[2]
    assert current.milestone_id == "trial_prepare"
    assert current.state == MILESTONE_CURRENT
    assert current.period_label == "2026 Q3–Q4"
    assert current.short_action == "試編永續資訊專章"
    assert view.current_action == "依官方時程，目前建議階段：試編永續資訊專章"


def test_prior_milestones_are_not_described_as_completed() -> None:
    view = _timeline()
    assert view is not None
    markup = ifrs_timeline_markup(view, ZH, play=False, initial_pct=view.progress_pct)
    assert "checkmark" not in markup.lower()
    assert "✓" not in markup
    assert 'data-cel-timeline-state="completed"' not in markup
    assert "data-cel-timeline-state='completed'" not in markup
    for item in view.milestones[:2]:
        assert item.state == MILESTONE_PAST
    assert "官方時程已經過" in markup
    assert view.schedule_note == (
        "此時程依主管機關導入時程與今天日期顯示目前位置，不代表公司已完成"
        "前述工作，也不是公司實際完成率。"
    )
    assert t("ifrs.timeline.heading", ZH) == "IFRS永續揭露法規時程（非公司完成度）"
    assert t("ifrs.timeline.past", ZH) == "官方時程已經過"
    assert "已完成" not in t("ifrs.timeline.past", ZH)
    assert "非公司完成度" in markup


def test_october_assurance_is_labelled_conditional() -> None:
    view = _timeline()
    assert view is not None
    october = view.milestones[4]
    assert october.conditional is True
    assert "條件期限" in october.badge
    assert "若年報申報時尚未取得確信" in october.detail
    assert "條件式最晚期限" in view.october_explanation
    assert "不是自動產生的第二次申報義務" in view.october_explanation


def test_scope3_2029_is_derived_future_requirement() -> None:
    view = _timeline()
    assert view is not None
    scope3 = view.milestones[5]
    assert scope3.derived is True
    assert scope3.period_label == "2029 年度"
    assert "第四個會計年度" in scope3.detail
    assert "2029" in view.scope3_explanation
    assert "推導" in view.scope3_explanation
    markup = ifrs_timeline_markup(view, ZH, play=False, initial_pct=view.progress_pct)
    assert "推導時程" in markup


def test_timeline_does_not_modify_capital_or_obligations() -> None:
    profile = _listed_12b()
    before = _assess(profile)
    capital_before = profile.paid_in_capital_twd
    ifrs_before = before.obligation(OBLIGATION_IFRS)
    assert ifrs_before is not None
    obligation_before = (
        ifrs_before.status,
        ifrs_before.effective_reporting_year,
        ifrs_before.first_filing_year,
        tuple(ifrs_before.applied_rule_ids),
    )
    view = build_first_stage_timeline(
        ubn="12345675",
        as_of=REVIEW_DATE,
    )
    after = _assess(profile)
    ifrs_after = after.obligation(OBLIGATION_IFRS)
    assert ifrs_after is not None
    assert profile.paid_in_capital_twd == capital_before == 12_000_000_000
    assert (
        ifrs_after.status,
        ifrs_after.effective_reporting_year,
        ifrs_after.first_filing_year,
        tuple(ifrs_after.applied_rule_ids),
    ) == obligation_before
    assert view is not None
    assert "emissions" not in view.run_identity


def test_facility_dirty_draft_blocking_unchanged() -> None:
    records = reconcile_facilities(
        official=stub_factories(STUB_SEVEN_UBN),
        upload_names=[],
        ubn=STUB_SEVEN_UBN,
    )
    confirm_all_operating(records)
    master = FacilityMaster(records=records, identity_confirmed=True)
    state: dict = {}
    mark_exception_drafts_dirty(state)
    assert exception_navigation_blocked(
        exception_mode=True,
        identity_confirmed=master.identity_confirmed,
        drafts_dirty=True,
    )
    source = APL.read_text(encoding="utf-8")
    assert "exception_navigation_blocked" in source
    assert "mark_exception_drafts_dirty" in source
    assert "render_customer_notice" in source


def test_case_c_results_remain_hidden() -> None:
    presented = present_assessment(_assess(_listed_12b()), ZH)
    ids = {item.obligation_id for item in presented.presentations}
    assert "taiwan_environmental_verification" not in ids
    assert "ghg_inventory" not in ids
    assert "carbon_fee" not in ids


def test_missing_fact_consolidation_unchanged() -> None:
    profile = CompanyProfile(
        company_name="timeline-co",
        reporting_year=2026,
        entity_type="general_listed_company",
        listing_status="TWSE",
        paid_in_capital_twd=12_000_000_000,
        jurisdiction="TW",
        has_taiwan_facilities="YES",
        received_verification_requirement="NOT_SURE",
        received_environmental_authority_inventory_notice="NOT_SURE",
    )
    presented = present_assessment(_assess(profile), ZH)
    summary = presented.action_summary
    assert summary.customer_action_required is True
    assert len(summary.facts) == 1
    assert "主管機關" in summary.exact_question


def test_customer_visible_copy_omits_internal_terms() -> None:
    assert customer_copy_violations(MESSAGES) == []
    title = t("setup.facilities.exception_need_confirm_title", ZH)
    body = t("setup.facilities.exception_need_confirm_body", ZH)
    assert title == "請先確認廠場狀態"
    assert body == "請確認每個廠場的最新狀態，再按『確認這些廠場狀態』。"
    blob = " ".join(
        [
            title,
            body,
            t("ifrs.timeline.heading", ZH),
            t("ifrs.timeline.evidence", ZH),
        ]
    )
    for token in (
        "dirty",
        "identity confirmation",
        "CASE C",
        "NEEDS_REVIEW",
        "obligation_id",
        "開啟編輯不會自動",
        "報導邊界",
    ):
        assert token not in blob
    source = APL.read_text(encoding="utf-8")
    assert "setup.facilities.exception_need_confirm_title" in source
    assert "開啟編輯不會自動" not in source


def test_facility_warning_title_without_dropdown_edit() -> None:
    title = t("setup.facilities.exception_need_confirm_title", ZH)
    body = t("setup.facilities.exception_need_confirm_body", ZH)
    assert title == "請先確認廠場狀態"
    assert "尚未確認的廠場變更" not in title
    assert "確認這些廠場狀態" in body
    source = APL.read_text(encoding="utf-8")
    assert "mark_exception_drafts_dirty" in source
    assert "exception_navigation_blocked" in source


def test_reduced_motion_uses_final_state_immediately() -> None:
    view = _timeline()
    assert view is not None
    initial, animate = timeline_animation_plan(
        play=True,
        reduced_motion=True,
        already_seen=False,
        target_pct=view.progress_pct,
    )
    assert animate is False
    assert initial == view.progress_pct
    script = JS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in script
    assert "DURATION_MS = 1400" in script
    assert "START_HOLD_MS = 450" in script
    css = (REPO_ROOT / "src" / "carbon_ledger" / "ui" / "visual_system.css").read_text(
        encoding="utf-8"
    )
    assert "prefers-reduced-motion: reduce" in css
    assert "cel-timeline-mobile-item.is-current.is-live" in css


def test_ordinary_reruns_do_not_replay_animation() -> None:
    run = timeline_run_identity(
        ubn="12345675", phase_id=PHASE_FIRST, timeline_version=TIMELINE_VERSION
    )
    state: dict = {"ifrs_timeline_last_run": ""}
    assert ifrs_timeline_should_play(state, run) is True
    state["ifrs_timeline_last_run"] = run
    assert ifrs_timeline_should_play(state, run) is False
    other = timeline_run_identity(ubn="13579243", phase_id=PHASE_FIRST)
    assert ifrs_timeline_should_play(state, other) is True
    initial, animate = timeline_animation_plan(
        play=False,
        reduced_motion=False,
        already_seen=True,
        target_pct=40.0,
    )
    assert animate is False
    assert initial == 40.0
    script = JS.read_text(encoding="utf-8")
    assert "__celTimelineSeen" in script


def test_consolidated_timeline_omits_duplicate_year_cards() -> None:
    source = APL.read_text(encoding="utf-8")
    assert "omit_timing=True" in source
    assert "show_basis=False" in source
    assert "render_ifrs_timeline_evidence" in source
    view = _timeline()
    assert view is not None
    markup = ifrs_timeline_markup(view, ZH, play=False, initial_pct=40)
    assert "2026 年度開始適用" in "".join(view.summary_items)
    assert view.summary_items == (
        "實收資本額達 100 億元以上",
        "第一階段適用",
        "2026 年度開始適用",
        "2027 年首次申報",
    )
    assert markup.count("2026 年度開始適用") == 1


def test_production_path_does_not_pass_frozen_review_date() -> None:
    page = APL.read_text(encoding="utf-8")
    module = TIMELINE_PY.read_text(encoding="utf-8")
    assert "REVIEW_AS_OF" not in page
    assert "REVIEW_AS_OF" not in module
    assert "first_stage_timeline_from_assessment" in page
    assert "select_disclosure_phase" not in page
    assert "paid_in_capital_twd=capital" not in page
    assert "select_disclosure_phase" not in module
    assert "datetime.now(TAIPEI)" in module


def test_injected_dates_select_schedule_state() -> None:
    mid_2025 = _timeline(as_of=date(2025, 5, 15))
    filing = _timeline(as_of=date(2027, 2, 1))
    assert mid_2025 is not None and filing is not None
    assert mid_2025.current_index == 1
    assert mid_2025.milestones[1].milestone_id == "design_execute"
    assert mid_2025.milestones[1].state == MILESTONE_CURRENT
    assert filing.current_index == 3
    assert filing.milestones[3].milestone_id == "first_filing"
    assert filing.in_active_window is True


def test_gap_between_windows_does_not_keep_expired_milestone_current() -> None:
    view = _timeline(as_of=date(2027, 5, 1))
    assert view is not None
    assert view.in_active_window is False
    assert view.schedule_mode == MODE_BETWEEN_WINDOWS
    assert view.current_index == -1
    assert view.milestones[3].milestone_id == "first_filing"
    assert view.milestones[3].state == MILESTONE_PAST
    assert view.milestones[4].state == MILESTONE_UPCOMING
    assert all(item.state != MILESTONE_CURRENT for item in view.milestones)
    assert view.current_action.startswith("下一官方時程：")
    assert "視情況補交確信報告" in view.current_action
    assert "目前應進行" not in view.current_action


def test_source_retrieval_date_does_not_follow_display_date() -> None:
    first = _timeline(as_of=date(2026, 8, 17))
    later = _timeline(as_of=date(2027, 1, 5))
    assert first is not None and later is not None
    assert [item.retrieved for item in first.sources] == [
        item.retrieved for item in later.sources
    ]
    retrieved = {item.source_id: item.retrieved for item in first.sources}
    assert retrieved["fsc"] == SOURCE_RETRIEVED_FSC == "2026-08-17"
    assert retrieved["twse"] == SOURCE_RETRIEVED_TWSE_EXAMPLE == "2026-08-12"
    assert retrieved["cgc"] == SOURCE_RETRIEVED_CGC_4386 == "2026-08-17"
    assert later.sources[1].retrieved != "2027-01-05"


def test_official_source_titles_are_exact_page_titles() -> None:
    view = _timeline()
    assert view is not None
    titles = {item.source_id: item.title for item in view.sources}
    assert titles["fsc"] == FSC_OFFICIAL_TITLE
    assert "（金管證審字第11403851756號）" not in titles["fsc"]
    assert titles["twse"] == TWSE_ARTICLE_OFFICIAL_TITLE
    assert "參考範例" not in titles["twse"]
    urls = {item.source_id: item.url for item in view.sources}
    assert urls["twse"].endswith("8a8216d69236c2e30192db1f6c6902fb")
    assert titles["cgc"] == CGC_4386_OFFICIAL_TITLE
    assert "建議作業時程" not in titles["cgc"]
    published = {item.source_id: item.published_or_effective for item in view.sources}
    assert published["fsc"] == "2025-11-12"
    assert published["twse"] == "2024-11-04"
    assert published["cgc"] == "2024-08-30"


def test_desktop_renders_actionable_detail_for_all_six_milestones() -> None:
    view = _timeline()
    assert view is not None
    assert tuple(item.short_action for item in view.milestones) == SHORT_ACTIONS_ZH
    markup = ifrs_timeline_markup(view, ZH, play=False, initial_pct=view.progress_pct)
    assert markup.count("cel-timeline-caption ") == 6
    for phrase in SHORT_ACTIONS_ZH:
        assert phrase in markup
    css = (REPO_ROOT / "src" / "carbon_ledger" / "ui" / "visual_system.css").read_text(
        encoding="utf-8"
    )
    assert "font-size: 0.68rem" not in css.split(".cel-timeline-action")[1][:180]
    assert ".cel-timeline-action" in css
    assert "0.82rem" in css


def test_mobile_current_state_and_rail_reach_milestone_three() -> None:
    view = _timeline()
    assert view is not None
    markup = ifrs_timeline_markup(view, ZH, play=False, initial_pct=view.progress_pct)
    assert "data-cel-timeline-mobile-item='2'" in markup
    assert markup.count("data-cel-rail-reached='1'") == 2
    assert re.search(
        r"cel-timeline-mobile-item is-current[^>]*data-cel-timeline-mobile-item='2'",
        markup,
    )
    mobile_third = markup.split("data-cel-timeline-mobile-item='2'")[1].split(
        "data-cel-timeline-mobile-item='3'"
    )[0]
    assert "data-cel-timeline-state='current_schedule'" in mobile_third
    assert "data-cel-rail-reached='0'" in mobile_third


def test_animation_counts_six_logical_markers_not_combined_nodelist() -> None:
    script = JS.read_text(encoding="utf-8")
    assert 'querySelectorAll("[data-cel-timeline-dot]")' not in script
    assert "data-cel-timeline-scope" in script
    assert "logicalCount" in script
    assert "revealDots(root, 100)" not in script
    view = _timeline()
    assert view is not None
    markup = ifrs_timeline_markup(view, ZH, play=True, initial_pct=0)
    assert markup.count("data-cel-timeline-dot=") == 12
    assert "data-cel-timeline-scope='desktop'" in markup
    assert "data-cel-timeline-scope='mobile'" in markup
    settled = ifrs_timeline_markup(
        view, ZH, play=False, initial_pct=view.progress_pct
    )
    desktop = settled.split("data-cel-timeline-scope='desktop'")[1].split(
        "data-cel-timeline-scope='mobile'"
    )[0]
    assert desktop.count("data-cel-timeline-visible='1'") == 3
    assert desktop.count("data-cel-timeline-visible='0'") == 3


def test_english_timeline_section_is_not_mixed_language() -> None:
    view = _timeline(lang=EN)
    assert view is not None
    markup = ifrs_timeline_markup(view, EN, play=False, initial_pct=view.progress_pct)
    assert CJK.search(markup) is None
    assert "not company completion" in t("ifrs.timeline.heading", EN)
    assert t("ifrs.timeline.heading", EN) in markup
    assert "Based on the official timeline, the current recommended stage is:" in (
        view.current_action
    )
    assert "today's date" in view.schedule_note
    assert "Draft the sustainability information chapter" in view.current_action
    assert CJK.search(view.current_action) is None
    assert CJK.search(view.phase_rule_explanation) is None
    assert CJK.search(view.october_explanation) is None
    assert CJK.search(view.scope3_explanation) is None
    for item in view.milestones:
        assert CJK.search(item.short_action) is None
        assert CJK.search(item.detail) is None
        assert CJK.search(item.period_label) is None
    for source in view.sources:
        assert CJK.search(source.authority) is None
        assert CJK.search(source.title) is not None
