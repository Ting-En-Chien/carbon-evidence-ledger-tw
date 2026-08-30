"""UX contracts for the corrected Stage 4.2H-A six-step wizard."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from carbon_ledger.applicability import (
    STATUS_NEEDS_INFORMATION,
    ApplicabilityAssessment,
    ObligationResult,
)
from carbon_ledger.company_master import (
    SOURCE_OFFICIAL_FACTORY,
    CompanyMaster,
    FacilityMasterRecord,
)
from carbon_ledger.inventory_boundary import (
    OPERATING_FULL_PERIOD,
    RECONCILIATION_DUPLICATE,
    RECONCILIATION_MATCHED,
    RECONCILIATION_NO_LONGER_VALID,
    RECONCILIATION_OTHER_COMPANY,
    RECONCILIATION_UNRESOLVED,
    CanonicalSite,
    PeriodOperatingFact,
    ReportingPeriod,
    initial_boundary_semantics_state,
)
from carbon_ledger.ui.boundary_wizard import (
    WIZARD_STEPS,
    apply_reconciliation_answer,
    period_form_defaults,
    reconciliation_form_spec,
)
from carbon_ledger.ui.i18n import t

ROOT = Path(__file__).resolve().parents[1]


def test_boundary_wizard_has_the_normative_six_steps() -> None:
    assert WIZARD_STEPS == (
        "period",
        "purposes",
        "reporting_entities",
        "registrations",
        "operations",
        "review",
    )
    assert [t(f"boundary.wizard.step.{item}", "zh-TW") for item in WIZARD_STEPS] == [
        "報導期間",
        "申報目的覆核",
        "IFRS 揭露範圍",
        "政府紀錄與據點",
        "營運與主管機關邊界",
        "檢查並確認",
    ]
    assert all(
        not t(f"boundary.wizard.step.{item}", "en").startswith("boundary.")
        for item in WIZARD_STEPS
    )


def test_customer_copy_distinguishes_registration_site_and_boundary() -> None:
    assert (
        t("boundary.wizard.registrations.official_record", "zh-TW")
        == "政府工廠登記資料"
    )
    limit = t("boundary.wizard.registrations.limit", "zh-TW")
    assert "不能單獨證明" in limit
    assert "實際營運據點" in limit
    assert "環境部盤查邊界" in limit
    assert "獨立申報單位" in limit
    assert "目前無法確認" in t(
        "boundary.wizard.registrations.uncertain", "zh-TW"
    )
    assert t(
        "boundary.wizard.reconciliation.matched_to_confirmed_site", "zh-TW"
    ) == "這筆登記對應本公司的實際據點"
    assert t(
        "boundary.wizard.reconciliation.duplicate_or_additional_record_for_same_site",
        "zh-TW",
    ) == "這是同一公司據點的另一筆登記"
    assert t(
        "boundary.wizard.reconciliation.belongs_to_another_company", "zh-TW"
    ) == "這筆登記不屬於本公司"
    assert t(
        "boundary.wizard.reconciliation.no_longer_valid", "zh-TW"
    ) == "這筆登記已註銷或不適用於本期"
    assert t("boundary.wizard.reconciliation.unresolved", "zh-TW") == "目前無法確認"


def test_ifrs_copy_does_not_infer_standalone_or_consolidated() -> None:
    copy = t("boundary.wizard.reporting_entities.ifrs_notice", "zh-TW")
    assert "應與相關財務報表的報導個體一致" in copy
    assert "系統不會自行決定採用個別或合併報表" in copy
    assert t("boundary.wizard.consolidation.unresolved", "zh-TW") == "尚未確認"
    assert t("boundary.wizard.consolidation.standalone", "zh-TW") == "個別財務報表"
    assert t("boundary.wizard.consolidation.consolidated", "zh-TW") == "合併財務報表"


def test_authority_copy_is_official_source_only() -> None:
    official = t("boundary.wizard.authority.official_only", "zh-TW")
    review = t("boundary.wizard.authority.professional_review", "zh-TW")
    assert "官方來源驗證" in official
    assert "才會建立環境部邊界" in official
    assert "不能取代主管機關文件" in review
    assert "專業人員" in review


def test_local_confirmation_copy_is_not_a_legal_conclusion() -> None:
    copy = t("boundary.wizard.review.not_legal_conclusion", "zh-TW")
    assert "本機確認" in copy
    assert "不代表法律結論" in copy
    assert "官方來源驗證" in copy


def test_stage_4_2h_a_source_has_no_category_or_free_merge_journey() -> None:
    source = (
        ROOT / "src/carbon_ledger/ui/boundary_wizard.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "SOURCE_CATEGORIES",
        "ExpectedSourceCategory",
        "_render_category_step",
        "combination_basis",
        "combined_with",
        "合併 registrations",
    ):
        assert forbidden not in source
    assert "RegistrationReconciliation" in source
    assert "CanonicalSite" in source
    assert "CompetentAuthorityBoundaryEvidence" in source


def test_boundary_wizard_css_remains_scoped_normal_flow() -> None:
    css = (ROOT / "src/carbon_ledger/ui/visual_system.css").read_text(
        encoding="utf-8"
    )
    source = (
        ROOT / "src/carbon_ledger/ui/boundary_wizard.py"
    ).read_text(encoding="utf-8")
    marker = (
        "/* Stage 4.2H-A — all boundary-wizard layout rules stay under this "
        "keyed root. */"
    )
    block = css.split(marker, maxsplit=1)[1]
    assert ".st-key-cel_boundary_wizard_root" in block
    assert ".st-key-cel_boundary_stepper_region" in block
    assert ".st-key-cel_boundary_context_region" in block
    assert ".st-key-cel_boundary_active_card" in block
    assert ".st-key-cel_boundary_footer" in block
    assert "position: fixed" not in block
    assert "overflow-y: auto" not in block
    assert "data-cel-boundary-primary-card='1'" in source
    assert "data-cel-boundary-completion-card='1'" in source
    assert 'with st.container(key="cel_boundary_validation_area")' in source


def test_no_obsolete_standalone_purpose_in_production_python() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src").rglob("*.py")
    )
    assert "PURPOSE_LISTED_STANDALONE" not in source
    assert '"listed_standalone"' not in source
    assert "PURPOSE_IFRS_REPORTING_ENTITY" in source


def test_period_step_has_no_historical_selector() -> None:
    source = (
        ROOT / "src/carbon_ledger/ui/boundary_wizard.py"
    ).read_text(encoding="utf-8")
    wrapper = source.split("def _period_step", maxsplit=1)[1].split(
        "def _period_step_body", maxsplit=1
    )[0]
    step = source.split("def _period_step_body", maxsplit=1)[1].split(
        "\ndef ", maxsplit=1
    )[0]
    assert "boundary.period.choose_active" not in wrapper
    assert "boundary.period.choose_active" not in step
    assert "list_semantics_periods" not in wrapper
    assert "list_semantics_periods" not in step
    assert "boundary_wizard_saved_period" not in wrapper
    assert "boundary_wizard_saved_period" not in step
    assert "period_form_defaults" in step
    assert "boundary.period.year" in step
    assert "boundary.period.start" in step
    assert "boundary.period.end" in step
    assert "boundary.period.confirm" in step


def test_period_form_defaults_use_active_period_or_assessment_year() -> None:
    year, start, end = period_form_defaults(
        assessment_year=2026,
        active_period=None,
    )
    assert (year, start, end) == (2026, date(2026, 1, 1), date(2026, 12, 31))
    period = ReportingPeriod.confirmed(
        reporting_year_suggested=2025,
        reporting_year_confirmed=2025,
        period_start_confirmed="2025-04-01",
        period_end_confirmed="2026-03-31",
    )
    year, start, end = period_form_defaults(
        assessment_year=2026,
        active_period=period,
    )
    assert (year, start, end) == (2025, date(2025, 4, 1), date(2026, 3, 31))


def _assessment() -> ApplicabilityAssessment:
    return ApplicabilityAssessment(
        assessment_timestamp="2026-08-24T00:00:00Z",
        reporting_year=2026,
        company_profile_snapshot={},
        obligations={
            "ghg_inventory": ObligationResult(
                obligation_id="ghg_inventory",
                obligation_name="GHG Inventory",
                status=STATUS_NEEDS_INFORMATION,
            )
        },
        rule_ids_used=[],
        rule_versions_used={},
        regulatory_freshness_snapshot={},
        result_statuses={},
    )


def _period() -> ReportingPeriod:
    return ReportingPeriod.confirmed(
        reporting_year_suggested=2026,
        reporting_year_confirmed=2026,
        period_start_confirmed="2026-01-01",
        period_end_confirmed="2026-12-31",
    )


def _company() -> CompanyMaster:
    return CompanyMaster(
        company_id="company_one",
        company_name="測試股份有限公司",
        unified_business_number="12345675",
    )


def _facility(index: int) -> FacilityMasterRecord:
    return FacilityMasterRecord(
        facility_id=f"raw_facility_{index}",
        display_name=f"政府列示工廠 {index}",
        address=f"高雄市測試路 {index} 號",
        official_factory_registration_number=f"REG-{index:03d}",
        source_type=SOURCE_OFFICIAL_FACTORY,
        discovered_from=(SOURCE_OFFICIAL_FACTORY,),
    )


def _state(*, facilities: int = 2):
    return initial_boundary_semantics_state(
        assessment=_assessment(),
        company=_company(),
        facilities=[_facility(index) for index in range(1, facilities + 1)],
        workspace_id="tw-ubn-12345675",
        reporting_period=_period(),
    )


STALE_FIELDS = {
    "selected_site_id": "stale_site",
    "new_site_name": "政府列示工廠 9",
    "new_site_address": "高雄市失效路 9 號",
    "new_site_confirmed": True,
    "basis": "stale-basis",
    "evidence_reference": "stale-evidence",
    "notes": "stale-notes",
}


def _stale(**overrides):
    return {**STALE_FIELDS, **overrides}


def _commit(state, result):
    assert result.error_key == ""
    assert result.reconciliation is not None
    sites = list(state.canonical_sites)
    if result.new_site is not None:
        sites.append(result.new_site)
    recs = [
        result.reconciliation
        if item.reconciliation_id == result.reconciliation.reconciliation_id
        else item
        for item in state.registration_reconciliations
    ]
    return replace_state(
        state,
        canonical_sites=tuple(sites),
        registration_reconciliations=tuple(recs),
    )


def replace_state(state, **changes):
    return replace(state, **changes)


def test_only_matched_can_create_a_new_canonical_site() -> None:
    state = _state()
    first = state.registration_reconciliations[0]
    matched = apply_reconciliation_answer(
        existing=first,
        state_choice=RECONCILIATION_MATCHED,
        new_site_name="高雄一廠",
        new_site_address="高雄市前鎮區",
        new_site_confirmed=True,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
        **{
            key: value
            for key, value in STALE_FIELDS.items()
            if key
            not in {
                "selected_site_id",
                "new_site_name",
                "new_site_address",
                "new_site_confirmed",
            }
        },
    )
    assert matched.error_key == ""
    assert matched.new_site is not None
    assert isinstance(matched.new_site, CanonicalSite)
    assert matched.reconciliation is not None
    assert matched.reconciliation.state == RECONCILIATION_MATCHED
    assert matched.reconciliation.canonical_site_id == matched.new_site.site_id
    assert matched.reconciliation.basis == ""
    assert matched.reconciliation.evidence_reference == ""
    updated = _commit(state, matched)
    second = updated.registration_reconciliations[1]
    duplicate = apply_reconciliation_answer(
        existing=second,
        state_choice=RECONCILIATION_DUPLICATE,
        selected_site_id=matched.new_site.site_id,
        new_site_name="不應建立",
        new_site_address="不應使用",
        new_site_confirmed=True,
        existing_sites=updated.canonical_sites,
        existing_reconciliations=updated.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
    )
    assert duplicate.error_key == ""
    assert duplicate.new_site is None
    assert duplicate.reconciliation is not None
    assert duplicate.reconciliation.state == RECONCILIATION_DUPLICATE
    assert duplicate.reconciliation.canonical_site_id == matched.new_site.site_id


def test_duplicate_requires_existing_site_and_blocks_empty_inventory() -> None:
    state = _state()
    spec = reconciliation_form_spec(
        RECONCILIATION_DUPLICATE,
        existing_site_count=0,
    )
    assert spec.show_no_sites_for_duplicate is True
    assert spec.allow_create_site is False
    assert spec.show_new_site_fields is False
    assert spec.primary_disabled is True
    empty = apply_reconciliation_answer(
        existing=state.registration_reconciliations[0],
        state_choice=RECONCILIATION_DUPLICATE,
        new_site_name="政府列示工廠 1",
        new_site_address="高雄市測試路 1 號",
        new_site_confirmed=True,
        existing_sites=(),
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
    )
    assert empty.error_key == "boundary.error.duplicate_site"
    assert empty.new_site is None


def test_other_company_and_no_longer_valid_require_basis_without_sites() -> None:
    state = _state()
    existing = state.registration_reconciliations[0]
    other_spec = reconciliation_form_spec(
        RECONCILIATION_OTHER_COMPANY,
        existing_site_count=2,
        selected_site_id="stale_site",
    )
    invalid_spec = reconciliation_form_spec(
        RECONCILIATION_NO_LONGER_VALID,
        existing_site_count=2,
        selected_site_id="stale_site",
    )
    assert other_spec.show_site_select is False
    assert other_spec.show_new_site_fields is False
    assert other_spec.show_other_basis is True
    assert invalid_spec.show_site_select is False
    assert invalid_spec.show_invalid_basis is True
    missing_other = apply_reconciliation_answer(
        existing=existing,
        state_choice=RECONCILIATION_OTHER_COMPANY,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        **_stale(basis=""),
    )
    assert missing_other.error_key == "boundary.error.other_company_basis"
    other = apply_reconciliation_answer(
        existing=existing,
        state_choice=RECONCILIATION_OTHER_COMPANY,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
        **_stale(basis="公開資料顯示屬於他公司"),
    )
    assert other.error_key == ""
    assert other.new_site is None
    assert other.reconciliation is not None
    assert other.reconciliation.state == RECONCILIATION_OTHER_COMPANY
    assert other.reconciliation.canonical_site_id == ""
    assert other.reconciliation.primary_candidate_id == ""
    assert other.reconciliation.basis == "公開資料顯示屬於他公司"
    missing_invalid = apply_reconciliation_answer(
        existing=existing,
        state_choice=RECONCILIATION_NO_LONGER_VALID,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        **_stale(basis=""),
    )
    assert missing_invalid.error_key == "boundary.error.registration_basis"
    invalid = apply_reconciliation_answer(
        existing=existing,
        state_choice=RECONCILIATION_NO_LONGER_VALID,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
        **_stale(basis="工廠登記已註銷"),
    )
    assert invalid.error_key == ""
    assert invalid.new_site is None
    assert invalid.reconciliation is not None
    assert invalid.reconciliation.state == RECONCILIATION_NO_LONGER_VALID
    assert invalid.reconciliation.canonical_site_id == ""


def test_unresolved_keeps_notes_without_mapping_or_exclusion() -> None:
    state = _state()
    spec = reconciliation_form_spec(
        RECONCILIATION_UNRESOLVED,
        existing_site_count=1,
        selected_site_id="stale_site",
    )
    assert spec.show_site_select is False
    assert spec.show_new_site_fields is False
    assert spec.show_notes is True
    result = apply_reconciliation_answer(
        existing=state.registration_reconciliations[0],
        state_choice=RECONCILIATION_UNRESOLVED,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
        **_stale(notes="需向廠務確認"),
    )
    assert result.error_key == ""
    assert result.new_site is None
    assert result.reconciliation is not None
    assert result.reconciliation.state == RECONCILIATION_UNRESOLVED
    assert result.reconciliation.canonical_site_id == ""
    assert result.reconciliation.primary_candidate_id == ""
    assert result.reconciliation.evidence_reference == ""
    assert result.reconciliation.locally_confirmed_at == ""
    assert result.reconciliation.basis == "需向廠務確認"


def test_government_prefill_is_not_company_confirmation() -> None:
    state = _state()
    spec = reconciliation_form_spec(
        RECONCILIATION_MATCHED,
        existing_site_count=0,
        selected_site_id="",
    )
    assert spec.show_government_prefill_notice is True
    assert spec.require_site_confirm is True
    assert spec.allow_create_site is True
    blocked = apply_reconciliation_answer(
        existing=state.registration_reconciliations[0],
        state_choice=RECONCILIATION_MATCHED,
        selected_site_id="",
        new_site_name="政府列示工廠 1",
        new_site_address="高雄市測試路 1 號",
        new_site_confirmed=False,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
    )
    assert blocked.error_key == "boundary.error.site_confirm"
    assert blocked.new_site is None
    assert t("boundary.wizard.registrations.gov_prefill", "zh-TW") == (
        "以下資料來自政府紀錄，請確認或修改。"
    )


def test_switching_choices_drops_stale_hidden_values() -> None:
    state = _state()
    existing = state.registration_reconciliations[0]
    unresolved = apply_reconciliation_answer(
        existing=existing,
        state_choice=RECONCILIATION_UNRESOLVED,
        **STALE_FIELDS,
    )
    assert unresolved.reconciliation is not None
    assert unresolved.reconciliation.canonical_site_id == ""
    assert unresolved.reconciliation.basis == "stale-notes"
    assert unresolved.reconciliation.evidence_reference == ""
    other = apply_reconciliation_answer(
        existing=existing,
        state_choice=RECONCILIATION_OTHER_COMPANY,
        **_stale(basis="不屬於本公司"),
    )
    assert other.reconciliation is not None
    assert other.reconciliation.canonical_site_id == ""
    assert other.new_site is None
    assert other.reconciliation.basis == "不屬於本公司"
    matched = apply_reconciliation_answer(
        existing=existing,
        state_choice=RECONCILIATION_MATCHED,
        selected_site_id="",
        new_site_name="本公司高雄廠",
        new_site_address="高雄市前鎮區",
        new_site_confirmed=True,
        basis="stale-basis",
        evidence_reference="stale-evidence",
        notes="stale-notes",
        existing_sites=(),
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
    )
    assert matched.reconciliation is not None
    assert matched.reconciliation.basis == ""
    assert matched.reconciliation.evidence_reference == ""
    assert matched.new_site is not None


def test_reconciliation_does_not_change_operating_status_or_boundary() -> None:
    state = _state()
    first = apply_reconciliation_answer(
        existing=state.registration_reconciliations[0],
        state_choice=RECONCILIATION_MATCHED,
        selected_site_id="",
        new_site_name="高雄一廠",
        new_site_address="高雄市前鎮區",
        new_site_confirmed=True,
        existing_sites=state.canonical_sites,
        existing_reconciliations=state.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
    )
    updated = _commit(state, first)
    fact = PeriodOperatingFact(
        operating_fact_id="op_existing",
        canonical_site_id=first.new_site.site_id,
        reporting_period_id=updated.reporting_period.reporting_period_id,
        status=OPERATING_FULL_PERIOD,
    )
    with_ops = replace_state(
        updated,
        operating_facts=(fact,),
    )
    second = apply_reconciliation_answer(
        existing=with_ops.registration_reconciliations[1],
        state_choice=RECONCILIATION_OTHER_COMPANY,
        basis="另一家公司",
        evidence_reference="經濟部商工登記",
        existing_sites=with_ops.canonical_sites,
        existing_reconciliations=with_ops.registration_reconciliations,
        workspace_id="tw-ubn-12345675",
        company_entity_id="company_one",
        confirmed_at="2026-08-28T00:00:00Z",
        selected_site_id=first.new_site.site_id,
        new_site_name="不應建立",
        new_site_confirmed=True,
    )
    after = _commit(with_ops, second)
    assert after.operating_facts == with_ops.operating_facts
    assert after.operating_facts[0].status == OPERATING_FULL_PERIOD
    assert after.boundaries == with_ops.boundaries
    assert after.authority_evidence == with_ops.authority_evidence
    assert after.registration_candidates == with_ops.registration_candidates
    assert {item.candidate_id for item in after.registration_candidates} == {
        item.candidate_id for item in state.registration_candidates
    }
    source = (
        ROOT / "src/carbon_ledger/ui/boundary_wizard.py"
    ).read_text(encoding="utf-8")
    step = source.split("def _registration_step", maxsplit=1)[1].split(
        "\ndef ", maxsplit=1
    )[0]
    assert "operating_facts" not in step
    assert "authority_evidence" not in step
    assert "PeriodOperatingFact" not in step


def test_registration_step_keeps_original_government_records() -> None:
    source = (
        ROOT / "src/carbon_ledger/ui/boundary_wizard.py"
    ).read_text(encoding="utf-8")
    step = source.split("def _registration_step", maxsplit=1)[1].split(
        "\ndef ", maxsplit=1
    )[0]
    assert "registration_candidates" not in step.split("def save", maxsplit=1)[1]
    assert t("boundary.wizard.registrations.new_site", "zh-TW") == "建立新公司據點"
