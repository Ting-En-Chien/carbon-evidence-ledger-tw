"""Official IFRS sustainability-disclosure timeline (presentation only).

Does not change applicability conclusions, capital values, or obligation IDs.
Does not use uploaded emissions to choose a phase or progress.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

from carbon_ledger.applicability import (
    OBLIGATION_IFRS,
    STATUS_APPLICABLE,
    STATUS_FUTURE_REQUIREMENT,
    ApplicabilityAssessment,
)
from carbon_ledger.ui.i18n import t

TAIPEI = ZoneInfo("Asia/Taipei")
TIMELINE_VERSION = "fsc-51756-first-stage-v1"
PHASE_FIRST = "first"
FIRST_STAGE_ADOPTION_RULE_ID = "tw_order_51756_phase1_ge_10bn"
FIRST_STAGE_MIN_CAPITAL_TWD = 10_000_000_000

# Evidence facts: when these official pages were actually retrieved.
# Independent of the customer display date.
SOURCE_RETRIEVED_FSC = "2026-08-17"
SOURCE_RETRIEVED_TWSE_EXAMPLE = "2026-08-12"
SOURCE_RETRIEVED_CGC_4386 = "2026-08-17"

FSC_OFFICIAL_TITLE = (
    "有關「公開發行公司年報應行記載事項準則」第7條第2項及"
    "第10條之1第7款、第8款規定之令"
)
TWSE_ARTICLE_OFFICIAL_TITLE = "IFRS永續揭露準則導入計畫之介紹"
CGC_4386_OFFICIAL_TITLE = (
    "證交所推動導入IFRS永續揭露準則，第一階段企業宣導會響應熱烈"
)

MILESTONE_PAST = "past_schedule"
MILESTONE_CURRENT = "current_schedule"
MILESTONE_UPCOMING = "upcoming"

MODE_IN_WINDOW = "in_window"
MODE_BEFORE_START = "before_start"
MODE_BETWEEN_WINDOWS = "between_windows"
MODE_AFTER_END = "after_end"

@dataclass(frozen=True)
class _MilestoneSpec:
    milestone_id: str
    start: date
    end: date
    conditional: bool = False
    derived: bool = False


_MILESTONE_SPECS = (
    _MilestoneSpec("analysis_planning", date(2024, 10, 1), date(2025, 3, 31)),
    _MilestoneSpec("design_execute", date(2025, 4, 1), date(2026, 6, 30)),
    _MilestoneSpec("trial_prepare", date(2026, 7, 1), date(2026, 12, 31)),
    _MilestoneSpec("first_filing", date(2027, 1, 1), date(2027, 3, 16)),
    _MilestoneSpec(
        "scope12_assurance",
        date(2027, 10, 1),
        date(2027, 10, 31),
        conditional=True,
    ),
    _MilestoneSpec(
        "scope3_start",
        date(2029, 1, 1),
        date(2029, 12, 31),
        derived=True,
    ),
)


@dataclass(frozen=True)
class TimelineMilestone:
    milestone_id: str
    period_label: str
    action_label: str
    short_action: str
    detail: str
    start: date
    end: date
    state: str = MILESTONE_UPCOMING
    conditional: bool = False
    derived: bool = False
    derived_note: str = ""
    badge: str = ""


@dataclass(frozen=True)
class TimelineSource:
    source_id: str
    authority: str
    title: str
    url: str
    published_or_effective: str
    retrieved: str


@dataclass(frozen=True)
class SchedulePosition:
    mode: str
    current_index: int
    progress_index: int
    next_index: int
    reveal_through: int
    in_active_window: bool


@dataclass(frozen=True)
class IfrsTimelineView:
    phase_id: str
    phase_label: str
    capital_summary: str
    applicability_start_year: int
    first_filing_year: int
    current_action: str
    schedule_note: str
    phase_rule_explanation: str
    october_explanation: str
    scope3_explanation: str
    timeline_version: str
    run_identity: str
    current_index: int
    progress_index: int
    reveal_through: int
    progress_pct: float
    in_active_window: bool
    schedule_mode: str
    milestones: tuple[TimelineMilestone, ...]
    sources: tuple[TimelineSource, ...]
    summary_items: tuple[str, ...]


def taipei_today(now: datetime | date | None = None) -> date:
    if isinstance(now, date) and not isinstance(now, datetime):
        return now
    if isinstance(now, datetime):
        return now.astimezone(TAIPEI).date()
    return datetime.now(TAIPEI).date()


def special_share_blocks_confident_first_stage(
    snapshot: dict | None,
) -> bool:
    """True when 令第 7 點 may apply and capital-only phase is not safe.

    The backend phase rules still evaluate paid-in capital only. This
    presentation layer must not invent a net-worth substitute mapping.
    """
    data = snapshot or {}
    no_par = str(data.get("has_no_par_value_shares") or "").upper()
    if no_par == "TRUE":
        return True
    raw = data.get("share_par_value_twd")
    if raw in (None, "", "UNKNOWN"):
        return False
    try:
        return float(raw) != 10.0
    except (TypeError, ValueError):
        return True


def first_stage_from_resolved_assessment(
    assessment: ApplicabilityAssessment | None,
) -> bool:
    """Show the first-stage timeline only from a safely resolved IFRS result."""
    if assessment is None:
        return False
    ifrs = assessment.obligation(OBLIGATION_IFRS)
    if ifrs is None:
        return False
    if ifrs.status not in {STATUS_APPLICABLE, STATUS_FUTURE_REQUIREMENT}:
        return False
    if FIRST_STAGE_ADOPTION_RULE_ID not in list(ifrs.applied_rule_ids or []):
        return False
    if ifrs.effective_reporting_year != 2026:
        return False
    if special_share_blocks_confident_first_stage(
        assessment.company_profile_snapshot
    ):
        return False
    return True


def timeline_run_identity(
    *,
    ubn: str,
    phase_id: str,
    timeline_version: str = TIMELINE_VERSION,
) -> str:
    return f"{str(ubn or '').strip()}|{phase_id}|{timeline_version}"


def timeline_animation_plan(
    *,
    play: bool,
    reduced_motion: bool,
    already_seen: bool,
    target_pct: float,
) -> tuple[float, bool]:
    """Return (initial width %, should_animate). Presentation only."""
    if (not play) or already_seen or reduced_motion:
        return float(target_pct), False
    return 0.0, True


def _progress_pct(progress_index: int, count: int) -> float:
    if count <= 1:
        return 0.0
    return round(100.0 * progress_index / (count - 1), 4)


def schedule_position(
    milestones: tuple[TimelineMilestone, ...], as_of: date
) -> SchedulePosition:
    """Locate as_of against official windows without treating a gap as current."""
    last = len(milestones) - 1
    for index, item in enumerate(milestones):
        if item.start <= as_of <= item.end:
            return SchedulePosition(
                mode=MODE_IN_WINDOW,
                current_index=index,
                progress_index=index,
                next_index=index,
                reveal_through=index,
                in_active_window=True,
            )
    if as_of < milestones[0].start:
        return SchedulePosition(
            mode=MODE_BEFORE_START,
            current_index=-1,
            progress_index=0,
            next_index=0,
            reveal_through=-1,
            in_active_window=False,
        )
    for index, item in enumerate(milestones):
        if as_of < item.start:
            past = max(0, index - 1)
            return SchedulePosition(
                mode=MODE_BETWEEN_WINDOWS,
                current_index=-1,
                progress_index=past,
                next_index=index,
                reveal_through=past,
                in_active_window=False,
            )
    return SchedulePosition(
        mode=MODE_AFTER_END,
        current_index=-1,
        progress_index=last,
        next_index=last,
        reveal_through=last,
        in_active_window=False,
    )


def current_milestone_index(
    milestones: tuple[TimelineMilestone, ...], as_of: date
) -> int | None:
    """Index of the official window that contains as_of, else None."""
    position = schedule_position(milestones, as_of)
    if position.in_active_window:
        return position.current_index
    return None


def _milestone_copy(milestone_id: str, lang: str) -> dict[str, str]:
    prefix = f"ifrs.timeline.m.{milestone_id}"
    badge = ""
    derived_note = ""
    if milestone_id == "scope12_assurance":
        badge = t("ifrs.timeline.conditional", lang)
    elif milestone_id == "scope3_start":
        badge = t("ifrs.timeline.derived", lang)
        derived_note = t(f"{prefix}.derived_note", lang)
    return {
        "period_label": t(f"{prefix}.period", lang),
        "action_label": t(f"{prefix}.label", lang),
        "short_action": t(f"{prefix}.short", lang),
        "detail": t(f"{prefix}.detail", lang),
        "badge": badge,
        "derived_note": derived_note,
    }


def _first_stage_milestones(lang: str) -> tuple[TimelineMilestone, ...]:
    items: list[TimelineMilestone] = []
    for spec in _MILESTONE_SPECS:
        copy = _milestone_copy(spec.milestone_id, lang)
        items.append(
            TimelineMilestone(
                milestone_id=spec.milestone_id,
                period_label=copy["period_label"],
                action_label=copy["action_label"],
                short_action=copy["short_action"],
                detail=copy["detail"],
                start=spec.start,
                end=spec.end,
                conditional=spec.conditional,
                derived=spec.derived,
                derived_note=copy["derived_note"],
                badge=copy["badge"],
            )
        )
    return tuple(items)


def _with_schedule_states(
    milestones: tuple[TimelineMilestone, ...],
    position: SchedulePosition,
) -> tuple[TimelineMilestone, ...]:
    updated: list[TimelineMilestone] = []
    for index, item in enumerate(milestones):
        if position.mode == MODE_IN_WINDOW:
            if index < position.current_index:
                state = MILESTONE_PAST
            elif index == position.current_index:
                state = MILESTONE_CURRENT
            else:
                state = MILESTONE_UPCOMING
        elif position.mode == MODE_BEFORE_START:
            state = MILESTONE_UPCOMING
        elif position.mode == MODE_AFTER_END:
            state = MILESTONE_PAST
        elif index <= position.progress_index:
            state = MILESTONE_PAST
        else:
            state = MILESTONE_UPCOMING
        updated.append(replace(item, state=state))
    return tuple(updated)


def official_timeline_sources(*, lang: str) -> tuple[TimelineSource, ...]:
    return (
        TimelineSource(
            source_id="fsc",
            authority=t("ifrs.timeline.source.fsc.authority", lang),
            title=FSC_OFFICIAL_TITLE,
            url="https://law.fsc.gov.tw/LawContent.aspx?id=GL004194",
            published_or_effective="2025-11-12",
            retrieved=SOURCE_RETRIEVED_FSC,
        ),
        TimelineSource(
            source_id="twse",
            authority=t("ifrs.timeline.source.twse.authority", lang),
            title=TWSE_ARTICLE_OFFICIAL_TITLE,
            url=(
                "https://www.twse.com.tw/market_insights/zh/detail/"
                "8a8216d69236c2e30192db1f6c6902fb"
            ),
            published_or_effective="2024-11-04",
            retrieved=SOURCE_RETRIEVED_TWSE_EXAMPLE,
        ),
        TimelineSource(
            source_id="cgc",
            authority=t("ifrs.timeline.source.cgc.authority", lang),
            title=CGC_4386_OFFICIAL_TITLE,
            url="https://cgc.twse.com.tw/pressReleases/promoteNewsArticleCh/4386",
            published_or_effective="2024-08-30",
            retrieved=SOURCE_RETRIEVED_CGC_4386,
        ),
    )


def _current_action(
    *,
    lang: str,
    position: SchedulePosition,
    milestones: tuple[TimelineMilestone, ...],
) -> str:
    if position.mode == MODE_IN_WINDOW:
        current = milestones[position.current_index]
        return t("ifrs.timeline.now", lang, task=current.short_action)
    if position.mode == MODE_AFTER_END:
        last = milestones[-1]
        return t("ifrs.timeline.after", lang, task=last.short_action)
    nxt = milestones[position.next_index]
    return t(
        "ifrs.timeline.next",
        lang,
        period=nxt.period_label,
        task=nxt.short_action,
    )


def build_first_stage_timeline(
    *,
    ubn: str,
    as_of: date | None = None,
    lang: str | None = None,
) -> IfrsTimelineView:
    """Build first-stage schedule copy. Caller must gate with the assessment."""
    today = taipei_today(as_of)
    raw = _first_stage_milestones(lang or "zh-TW")
    position = schedule_position(raw, today)
    milestones = _with_schedule_states(raw, position)
    progress_pct = (
        0.0
        if position.mode == MODE_BEFORE_START
        else _progress_pct(position.progress_index, len(milestones))
    )
    if position.mode == MODE_AFTER_END:
        progress_pct = 100.0
    return IfrsTimelineView(
        phase_id=PHASE_FIRST,
        phase_label=t("ifrs.timeline.phase_first", lang),
        capital_summary=t("ifrs.timeline.capital_100", lang),
        applicability_start_year=2026,
        first_filing_year=2027,
        current_action=_current_action(
            lang=lang or "zh-TW",
            position=position,
            milestones=milestones,
        ),
        schedule_note=t("ifrs.timeline.note", lang),
        phase_rule_explanation=t("ifrs.timeline.phase_rule", lang),
        october_explanation=t("ifrs.timeline.october", lang),
        scope3_explanation=t("ifrs.timeline.scope3", lang),
        timeline_version=TIMELINE_VERSION,
        run_identity=timeline_run_identity(ubn=ubn, phase_id=PHASE_FIRST),
        current_index=position.current_index,
        progress_index=position.progress_index,
        reveal_through=position.reveal_through,
        progress_pct=progress_pct,
        in_active_window=position.in_active_window,
        schedule_mode=position.mode,
        milestones=milestones,
        sources=official_timeline_sources(lang=lang or "zh-TW"),
        summary_items=(
            t("ifrs.timeline.capital_100", lang),
            t("ifrs.timeline.phase_first", lang),
            t("ifrs.timeline.start_2026", lang),
            t("ifrs.timeline.file_2027", lang),
        ),
    )


def first_stage_timeline_from_assessment(
    assessment: ApplicabilityAssessment | None,
    *,
    ubn: str,
    as_of: date | None = None,
    lang: str | None = None,
) -> IfrsTimelineView | None:
    if not first_stage_from_resolved_assessment(assessment):
        return None
    return build_first_stage_timeline(ubn=ubn, as_of=as_of, lang=lang)


__all__ = [
    "CGC_4386_OFFICIAL_TITLE",
    "FIRST_STAGE_ADOPTION_RULE_ID",
    "FIRST_STAGE_MIN_CAPITAL_TWD",
    "FSC_OFFICIAL_TITLE",
    "IfrsTimelineView",
    "MILESTONE_CURRENT",
    "MILESTONE_PAST",
    "MILESTONE_UPCOMING",
    "MODE_AFTER_END",
    "MODE_BEFORE_START",
    "MODE_BETWEEN_WINDOWS",
    "MODE_IN_WINDOW",
    "PHASE_FIRST",
    "SOURCE_RETRIEVED_CGC_4386",
    "SOURCE_RETRIEVED_FSC",
    "SOURCE_RETRIEVED_TWSE_EXAMPLE",
    "TIMELINE_VERSION",
    "TWSE_ARTICLE_OFFICIAL_TITLE",
    "TimelineMilestone",
    "TimelineSource",
    "build_first_stage_timeline",
    "current_milestone_index",
    "first_stage_from_resolved_assessment",
    "first_stage_timeline_from_assessment",
    "official_timeline_sources",
    "schedule_position",
    "special_share_blocks_confident_first_stage",
    "taipei_today",
    "timeline_animation_plan",
    "timeline_run_identity",
]
