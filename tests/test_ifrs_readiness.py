"""IFRS S1/S2 disclosure readiness checklist — data presence only."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from carbon_ledger.applicability import (
    OBLIGATION_IFRS,
    OBLIGATION_VERIFICATION,
    STATUS_APPLICABLE,
    ApplicabilityAssessment,
    CompanyProfile,
    ObligationResult,
)
from carbon_ledger.pipeline import PipelineRunResult
from carbon_ledger.ui.i18n import MESSAGES, t
from carbon_ledger.ui.ifrs_readiness import (
    S1_ITEM_IDS,
    S2_ITEM_IDS,
    STATUS_AVAILABLE,
    STATUS_MISSING,
    STATUS_UNSUPPORTED,
    UNSUPPORTED_ITEM_IDS,
    build_ifrs_readiness_view,
    public_readiness_text,
    try_load_reporting_entity_confirmation,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH = "zh-TW"
EN = "en"
APL = REPO_ROOT / "app_pages" / "applicability.py"
READINESS = REPO_ROOT / "src" / "carbon_ledger" / "ui" / "ifrs_readiness.py"
FORBIDDEN = (
    "合規分數",
    "完成百分比",
    "已完成揭露",
    "已合規",
    "認證完成",
    "準備度百分比",
    "compliance score",
    "completion percentage",
    "disclosure complete",
    "Scope 1／2 已完成 IFRS 揭露",
    "Scope 1/2 已完成 IFRS 揭露",
)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame()


def _pipeline(**frames: pd.DataFrame) -> PipelineRunResult:
    empty = _empty_frame()
    payload = {
        "run_id": "readiness-test",
        "ingested_at": pd.Timestamp("2026-01-01T00:00:00Z"),
        "include_ghg": True,
        "include_cbam": False,
        "include_ifrs_s2": False,
        "source_documents_accepted": empty,
        "source_documents_rejected": empty,
        "activity_records_accepted": empty,
        "activity_records_rejected": empty,
        "normalized_records": empty,
        "candidate_matches": empty,
        "activity_readiness": empty,
        "calculation_results": empty,
        "core_qa_issues": empty,
        "ghg_evaluations": empty,
        "cbam_evaluations": empty,
        "ifrs_s2_evaluations": empty,
    }
    payload.update(frames)
    return PipelineRunResult(**payload)


def _assessment(*, reporting_year: int | None = None) -> ApplicabilityAssessment:
    return ApplicabilityAssessment(
        assessment_timestamp="2026-01-01T00:00:00Z",
        reporting_year=reporting_year,
        company_profile_snapshot={"reporting_year": reporting_year},
        obligations={
            OBLIGATION_IFRS: ObligationResult(
                obligation_id=OBLIGATION_IFRS,
                obligation_name="IFRS S1/S2",
                status=STATUS_APPLICABLE,
            ),
            OBLIGATION_VERIFICATION: ObligationResult(
                obligation_id=OBLIGATION_VERIFICATION,
                obligation_name="verification",
                status=STATUS_APPLICABLE,
            ),
        },
        rule_ids_used=[],
        rule_versions_used={},
        regulatory_freshness_snapshot={},
        result_statuses={},
    )


def test_empty_inputs_do_not_crash() -> None:
    view = build_ifrs_readiness_view()
    assert view.item("reporting_period").status == STATUS_MISSING
    assert view.item("reporting_entity").status == STATUS_MISSING
    assert view.item("scope_1").status == STATUS_MISSING
    assert view.item("scope_2").status == STATUS_MISSING
    text = public_readiness_text(view, ZH)
    assert t("ifrs.readiness.title", ZH) in text


def test_reporting_period_available_when_year_present() -> None:
    view = build_ifrs_readiness_view(company_profile={"reporting_year": 2026})
    assert view.item("reporting_period").status == STATUS_AVAILABLE
    from_assessment = build_ifrs_readiness_view(
        assessment=_assessment(reporting_year=2026)
    )
    assert from_assessment.item("reporting_period").status == STATUS_AVAILABLE


def test_unconfirmed_reporting_entity_is_missing() -> None:
    view = build_ifrs_readiness_view(
        company_profile={"reporting_year": 2026, "entity_type": "unresolved"},
        reporting_entity_confirmed=False,
        reporting_entity_evidence=(SimpleNamespace(confirms_reporting_entity=False),),
    )
    assert view.item("reporting_entity").status == STATUS_MISSING


def test_confirmed_reporting_entity_is_available() -> None:
    view = build_ifrs_readiness_view(
        reporting_entity_evidence=(SimpleNamespace(confirms_reporting_entity=True),)
    )
    assert view.item("reporting_entity").status == STATUS_AVAILABLE


def test_zero_scope_emissions_are_not_treated_as_missing() -> None:
    result = _pipeline(
        activity_records_accepted=pd.DataFrame(
            [
                {"record_id": "s1", "activity_type": "natural_gas"},
                {"record_id": "s2", "activity_type": "grid_electricity"},
            ]
        ),
        calculation_results=pd.DataFrame(
            [
                {
                    "record_id": "s1",
                    "calculation_status": "calculated",
                    "calculated_tco2e": 0.0,
                    "factor_id": "ef_ng",
                },
                {
                    "record_id": "s2",
                    "calculation_status": "calculated",
                    "calculated_tco2e": 0.0,
                    "factor_id": "ef_grid",
                },
            ]
        ),
        ghg_evaluations=pd.DataFrame(
            [
                {
                    "record_id": "s1",
                    "mapping_status": "mapped",
                    "ghg_scope": "scope_1",
                },
                {
                    "record_id": "s2",
                    "mapping_status": "mapped",
                    "ghg_scope": "scope_2",
                },
            ]
        ),
    )
    view = build_ifrs_readiness_view(pipeline_result=result)
    assert view.item("scope_1").status == STATUS_AVAILABLE
    assert view.item("scope_2").status == STATUS_AVAILABLE
    assert view.item("measurement_methods").status == STATUS_AVAILABLE
    text = public_readiness_text(view, ZH)
    assert (
        "系統已有排放計算資料；仍需確認報導邊界、衡量方法、假設及揭露所需佐證。"
        in text
    )
    assert "Scope 1／2 已完成 IFRS 揭露" not in text


def test_missing_scope_calculation_is_not_available() -> None:
    view = build_ifrs_readiness_view(pipeline_result=_pipeline())
    assert view.item("scope_1").status == STATUS_MISSING
    assert view.item("scope_2").status == STATUS_MISSING
    assert view.item("measurement_methods").status == STATUS_MISSING


def test_unsupported_s1_and_s2_items() -> None:
    view = build_ifrs_readiness_view(
        company_profile={"reporting_year": 2026},
        reporting_entity_confirmed=True,
        pipeline_result=_pipeline(),
        assessment=_assessment(reporting_year=2026),
    )
    for item_id in UNSUPPORTED_ITEM_IDS:
        assert view.item(item_id).status == STATUS_UNSUPPORTED
    assert view.item("scope_3").status == STATUS_UNSUPPORTED
    assert view.item("transition_risk").status == STATUS_UNSUPPORTED
    assert view.item("materiality").status == STATUS_UNSUPPORTED


def test_applicable_assurance_is_not_treated_as_evidence() -> None:
    view = build_ifrs_readiness_view(assessment=_assessment(reporting_year=2026))
    assert view.item("assurance_evidence").status == STATUS_UNSUPPORTED
    text = public_readiness_text(view, ZH)
    assert "適用確信要求不代表已有證據" in text


def test_no_compliance_score_or_completion_claims() -> None:
    view = build_ifrs_readiness_view(
        company_profile={"reporting_year": 2026},
        reporting_entity_confirmed=True,
        pipeline_result=_pipeline(
            activity_records_accepted=pd.DataFrame(
                [{"record_id": "s1", "activity_type": "natural_gas"}]
            ),
            calculation_results=pd.DataFrame(
                [
                    {
                        "record_id": "s1",
                        "calculation_status": "calculated",
                        "calculated_tco2e": 0.0,
                        "factor_id": "ef_ng",
                    }
                ]
            ),
        ),
        assessment=_assessment(reporting_year=2026),
    )
    for lang in (ZH, EN):
        blob = public_readiness_text(view, lang)
        lower = blob.lower()
        for token in FORBIDDEN:
            assert token.lower() not in lower, token
        assert (
            "不代表已符合 IFRS S1／S2" in blob
            or "does not mean the company meets IFRS S1/S2" in blob
        )
        assert (
            "也不是公司實際完成率" in blob
            or "is not a company completion rate" in blob
        )
        remainder = blob.replace("不代表已符合 IFRS S1／S2", "")
        assert "已符合 IFRS" not in remainder


def test_readiness_i18n_keys_are_complete() -> None:
    statuses_by_item = {
        "reporting_period": (STATUS_AVAILABLE, STATUS_MISSING),
        "reporting_entity": (STATUS_AVAILABLE, STATUS_MISSING),
        "scope_1": (STATUS_AVAILABLE, STATUS_MISSING),
        "scope_2": (STATUS_AVAILABLE, STATUS_MISSING),
        "measurement_methods": (STATUS_AVAILABLE, STATUS_MISSING),
    }
    required = [
        "ifrs.readiness.title",
        "ifrs.readiness.note",
        "ifrs.readiness.status.available",
        "ifrs.readiness.status.missing",
        "ifrs.readiness.status.unsupported",
        "ifrs.readiness.section.s1",
        "ifrs.readiness.section.s2",
    ]
    for item_id in (*S1_ITEM_IDS, *S2_ITEM_IDS):
        required.append(f"ifrs.readiness.item.{item_id}.name")
        statuses = statuses_by_item.get(item_id, (STATUS_UNSUPPORTED,))
        for status in statuses:
            required.append(f"ifrs.readiness.item.{item_id}.why.{status}")
            required.append(f"ifrs.readiness.item.{item_id}.next.{status}")
    for key in required:
        entry = MESSAGES[key]
        assert entry[ZH].strip()
        assert entry[EN].strip()
        assert t(key, ZH) != key
        assert t(key, EN) != key
    assert t("ifrs.readiness.status.available", ZH) == "系統已有資料"
    assert t("ifrs.readiness.status.missing", ZH) == "尚未提供資料"
    assert t("ifrs.readiness.status.unsupported", ZH) == "目前產品尚未支援"
    assert t("ifrs.readiness.status.available", EN) == "Data available in the system"
    assert t("ifrs.readiness.status.missing", EN) == "Information not yet provided"
    assert t("ifrs.readiness.status.unsupported", EN) == (
        "Not supported by the current product"
    )


def test_applicability_page_renders_readiness_when_ifrs_results_exist() -> None:
    source = APL.read_text(encoding="utf-8")
    assert "render_ifrs_readiness_section" in source
    assert "build_ifrs_readiness_view" in source
    assert "if timeline is not None or ifrs_cards:" in source
    start = source.index("try_load_reporting_entity_confirmation(")
    chunk = source[start : start + 900]
    assert "reporting_year=" in chunk
    assert 'getattr(assessment, "reporting_year"' in chunk
    renderer = READINESS.read_text(encoding="utf-8")
    assert "st.markdown(" in renderer
    assert "合規分數" not in renderer
    assert "DURATION_MS" not in renderer


def test_workspace_lookup_without_company_does_not_crash() -> None:
    assert try_load_reporting_entity_confirmation() is False
    assert (
        try_load_reporting_entity_confirmation(
            taiwan_ubn="", entity_id="", repo_root=REPO_ROOT
        )
        is False
    )
    assert (
        try_load_reporting_entity_confirmation(
            taiwan_ubn="",
            entity_id="",
            repo_root=REPO_ROOT,
            reporting_year=2026,
        )
        is False
    )


def _period_state(
    year: int,
    *,
    confirmed: bool,
    period_id: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        reporting_period=SimpleNamespace(
            reporting_year_confirmed=year,
            reporting_period_id=period_id or f"period-{year}",
        ),
        financial_reporting_entity_evidence=(
            SimpleNamespace(confirms_reporting_entity=confirmed),
        ),
    )


def _try_load_with_states(states: list[SimpleNamespace], **kwargs: object) -> bool:
    workspace = MagicMock()
    workspace.list_semantics_periods.return_value = states
    cls = MagicMock()
    cls.for_company.return_value = workspace
    with (
        patch("carbon_ledger.company_workspace.CompanyWorkspace", cls),
        patch(
            "carbon_ledger.company_workspace.default_workspace_root",
            return_value=Path("/tmp"),
        ),
    ):
        return try_load_reporting_entity_confirmation(
            taiwan_ubn="12345678",
            **kwargs,
        )


def test_prior_year_confirmation_does_not_cover_current_year() -> None:
    confirmed = _try_load_with_states(
        [
            _period_state(2025, confirmed=True),
            _period_state(2026, confirmed=False),
        ],
        reporting_year=2026,
    )
    assert confirmed is False
    view = build_ifrs_readiness_view(
        company_profile={"reporting_year": 2026},
        reporting_entity_confirmed=confirmed,
    )
    assert view.item("reporting_entity").status == STATUS_MISSING


def test_current_year_confirmation_is_available() -> None:
    confirmed = _try_load_with_states(
        [
            _period_state(2025, confirmed=True),
            _period_state(2026, confirmed=True),
        ],
        reporting_year=2026,
    )
    assert confirmed is True
    view = build_ifrs_readiness_view(
        company_profile={"reporting_year": 2026},
        reporting_entity_confirmed=confirmed,
    )
    assert view.item("reporting_entity").status == STATUS_AVAILABLE


def test_other_year_confirmation_alone_is_not_true() -> None:
    assert (
        _try_load_with_states(
            [_period_state(2025, confirmed=True)],
            reporting_year=2026,
        )
        is False
    )
    assert (
        _try_load_with_states(
            [_period_state(2025, confirmed=True, period_id="period-2025")],
            reporting_period_id="period-2026",
        )
        is False
    )


def test_try_load_without_reporting_year_is_false() -> None:
    assert try_load_reporting_entity_confirmation(taiwan_ubn="12345678") is False
    assert (
        _try_load_with_states(
            [_period_state(2026, confirmed=True)],
        )
        is False
    )


def test_ifrs_applicability_does_not_imply_qualitative_data() -> None:
    profile = CompanyProfile(company_name="listed", reporting_year=2026)
    view = build_ifrs_readiness_view(
        company_profile=profile.snapshot(),
        assessment=_assessment(reporting_year=2026),
    )
    assert view.item("governance").status == STATUS_UNSUPPORTED
    assert view.item("strategy").status == STATUS_UNSUPPORTED
    assert view.item("reporting_entity").status == STATUS_MISSING
