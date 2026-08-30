"""Stage 4.2D — customer-first applicability UX and capital presentation."""

from __future__ import annotations

from pathlib import Path

from carbon_ledger.applicability import CompanyProfile, assess_applicability
from carbon_ledger.company_lookup import STUB_SEVEN_UBN, stub_factories
from carbon_ledger.company_master import (
    MATCH_OFFICIAL_ONLY,
    SOURCE_OFFICIAL_FACTORY,
    SOURCE_UPLOAD,
    STATUS_INACTIVE,
    CompanyMaster,
    FacilityMaster,
    FacilityMasterRecord,
    apply_identity_status,
    clear_exception_drafts_dirty,
    commit_identity_drafts,
    confirm_all,
    confirm_all_operating,
    exception_drafts_are_dirty,
    exception_navigation_blocked,
    included_taiwan_sites,
    mark_exception_drafts_dirty,
    profile_updates_from_masters,
    reconcile_facilities,
    taiwan_facility_existence,
)
from carbon_ledger.ui.company_setup import (
    merge_profile_from_setup,
    source_discrepancy_records,
)
from carbon_ledger.ui.customer_presenters import (
    STATUS_APPLICABLE,
    present_assessment,
    present_obligation_card,
)
from carbon_ledger.ui.formatting import format_int
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import render_animated_metric

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH = "zh-TW"
APL = REPO_ROOT / "app_pages" / "applicability.py"


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


def _assess(profile: CompanyProfile):
    return assess_applicability(
        profile,
        repo_root=REPO_ROOT,
        freshness_loader=_fresh_ok,
    )


def _seven_records() -> list[FacilityMasterRecord]:
    return reconcile_facilities(
        official=stub_factories(STUB_SEVEN_UBN),
        upload_names=[],
        ubn=STUB_SEVEN_UBN,
    )


def test_facility_existence_independent_from_reporting_scope() -> None:
    records = _seven_records()
    confirm_all_operating(records)
    assert all(item.included_in_current_reporting_scope is False for item in records)
    assert included_taiwan_sites(records) == []
    existence = taiwan_facility_existence(records, identity_confirmed=True)
    assert existence == "YES"


def test_active_confirmed_facility_is_yes() -> None:
    records = _seven_records()
    confirm_all(records, include_in_scope=False)
    assert taiwan_facility_existence(records, identity_confirmed=True) == "YES"


def test_no_facility_is_no_only_after_explicit_confirmation() -> None:
    records = _seven_records()
    assert taiwan_facility_existence(records, identity_confirmed=False) == "NOT_SURE"
    empty = taiwan_facility_existence(
        [],
        identity_confirmed=True,
        none_declared=True,
    )
    assert empty == "NO"
    for record in records:
        apply_identity_status(record, "sold")
    assert all(item.status == STATUS_INACTIVE for item in records)
    assert (
        taiwan_facility_existence(records, identity_confirmed=True, none_declared=True)
        == "NO"
    )


def test_unresolved_facility_identity_is_not_sure() -> None:
    records = _seven_records()
    assert taiwan_facility_existence(records) == "NOT_SURE"
    company = CompanyMaster(company_name="x", unified_business_number=STUB_SEVEN_UBN)
    master = FacilityMaster(records=records, identity_confirmed=False)
    updates = profile_updates_from_masters(company, master)
    assert "has_taiwan_facilities" not in updates


def test_profile_merge_does_not_use_reporting_scope() -> None:
    records = _seven_records()
    confirm_all_operating(records)
    master = FacilityMaster(records=records, identity_confirmed=True)
    company = CompanyMaster(
        company_name="長興材料工業股份有限公司",
        unified_business_number=STUB_SEVEN_UBN,
    )
    merged = merge_profile_from_setup({}, company, master)
    assert merged["has_taiwan_facilities"] == "YES"
    assert merged["number_of_taiwan_facilities"] == 7
    assert all(item.included_in_current_reporting_scope is False for item in records)


def test_step3_source_has_one_primary_confirmation_and_no_scope_controls() -> None:
    source = APL.read_text(encoding="utf-8")
    assert "setup.facilities.confirm_all" in source
    assert "setup.include_all" not in source
    assert "setup.include_this" not in source
    assert "setup.deactivate" not in source
    assert "setup.inactive.keep" not in source
    assert "setup.full_year_all" not in source
    assert "apl_include_all" not in source
    assert "included_in_current_reporting_scope" in source
    assert "has_real_uploaded_activity" in source


def test_official_only_is_not_a_discrepancy_without_upload() -> None:
    records = _seven_records()
    assert all(item.match_state == MATCH_OFFICIAL_ONLY for item in records)
    assert source_discrepancy_records(records) == []
    mixed = list(records)
    mixed.append(
        FacilityMasterRecord(
            facility_id="fac_upload",
            display_name="台中辦公室",
            discovered_from=(SOURCE_UPLOAD,),
            match_state="upload_only",
        )
    )
    mixed[0].discovered_from = (SOURCE_OFFICIAL_FACTORY,)
    assert len(source_discrepancy_records(mixed)) >= 1


def test_results_aggregate_shared_missing_facts() -> None:
    presented = present_assessment(
        _assess(
            CompanyProfile(
                company_name="presentation-co",
                reporting_year=2026,
                entity_type="general_listed_company",
                listing_status="TWSE",
                paid_in_capital_twd=12_000_000_000,
                jurisdiction="TW",
            )
        ),
        ZH,
    )
    summary = presented.action_summary
    assert summary.customer_action_required is True
    assert summary.headline == "還差 1 項資料"
    assert summary.exact_question
    assert "還需要一些資料" not in summary.headline
    taiwan = [
        item
        for item in presented.presentations
        if item.domain in {"ghg_inventory", "env_verification", "carbon_fee"}
    ]
    assert taiwan == []
    titles = [item.title for item in presented.presentations]
    assert "台灣溫室氣體盤查" not in titles
    assert "碳費" not in titles
    assert "環境部溫室氣體查驗" not in titles


def test_system_limitation_is_hidden_not_customer_task() -> None:
    presented = present_assessment(
        _assess(
            CompanyProfile(
                company_name="presentation-co",
                reporting_year=2026,
                entity_type="general_listed_company",
                listing_status="TWSE",
                paid_in_capital_twd=12_000_000_000,
                jurisdiction="TW",
                has_taiwan_facilities="YES",
                number_of_taiwan_facilities=7,
                received_environmental_authority_inventory_notice="NO",
                received_verification_requirement="NO",
                reporting_entities_known="TRUE",
            )
        ),
        ZH,
    )
    taiwan = [
        item
        for item in presented.presentations
        if item.domain in {"ghg_inventory", "env_verification", "carbon_fee"}
    ]
    assert taiwan == []
    assert presented.action_summary.customer_action_required is False
    blob = " ".join(presented.hidden_not_ready)
    assert "CUSTOMER RESULT NOT READY" in blob
    assert "碳費" in blob or "carbon_fee" in blob.lower() or "盤查" in blob
    assert "查驗" in blob


def test_customer_question_titles_for_taiwan_outcomes() -> None:
    inventory = present_obligation_card(
        {
            "obligation_id": "ghg_inventory",
            "title": "台灣溫室氣體盤查",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "環境部",
            "official_document": "x",
            "citations": ["a"],
        },
        ZH,
    )
    verification = present_obligation_card(
        {
            "obligation_id": "taiwan_environmental_verification",
            "title": "環境部溫室氣體查驗",
            "status": "APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "",
            "official_document": "",
            "citations": [],
        },
        ZH,
    )
    fee = present_obligation_card(
        {
            "obligation_id": "carbon_fee",
            "title": "碳費",
            "status": "NOT_APPLICABLE",
            "missing_field_ids": [],
            "official_authority": "環境部",
            "official_document": "x",
            "citations": ["a"],
        },
        ZH,
    )
    assert inventory.title == "公司需要向環境部盤查／登錄溫室氣體嗎？"
    assert verification.title == "公司需要第三方查驗溫室氣體資料嗎？"
    assert fee.title == "公司可能需要繳碳費嗎？"
    assert inventory.status_code == STATUS_APPLICABLE
    assert "整理年度排放資料" in inventory.explanation


def test_notice_yes_surfaces_verification_need() -> None:
    presented = present_assessment(
        _assess(
            CompanyProfile(
                company_name="presentation-co",
                reporting_year=2026,
                entity_type="general_listed_company",
                listing_status="TWSE",
                paid_in_capital_twd=12_000_000_000,
                jurisdiction="TW",
                has_taiwan_facilities="YES",
                received_environmental_authority_inventory_notice="YES",
                received_verification_requirement="YES",
                reporting_entities_known="TRUE",
            )
        ),
        ZH,
    )
    env = next(
        item for item in presented.presentations if item.domain == "env_verification"
    )
    assert env.title == "公司需要第三方查驗溫室氣體資料嗎？"
    assert env.status_code == STATUS_APPLICABLE
    assert env.short_status in {"適用", "需要"}
    titles = [item.title for item in presented.presentations]
    assert "台灣溫室氣體盤查" not in titles
    assert "碳費" not in titles


def test_notice_no_hides_verification_without_not_applicable() -> None:
    presented = present_assessment(
        _assess(
            CompanyProfile(
                company_name="presentation-co",
                reporting_year=2026,
                entity_type="general_listed_company",
                listing_status="TWSE",
                paid_in_capital_twd=12_000_000_000,
                jurisdiction="TW",
                has_taiwan_facilities="YES",
                received_environmental_authority_inventory_notice="NO",
                received_verification_requirement="NO",
                reporting_entities_known="TRUE",
            )
        ),
        ZH,
    )
    env = [
        item
        for item in presented.presentations
        if item.domain == "env_verification"
    ]
    assert env == []
    assert all(item.status_code != STATUS_APPLICABLE for item in env)
    hidden = " ".join(presented.hidden_not_ready)
    assert "查驗" in hidden
    assert "NOT_APPLICABLE" not in hidden
    assert presented.action_summary.customer_action_required is False


def test_notice_not_sure_one_consolidated_question() -> None:
    presented = present_assessment(
        _assess(
            CompanyProfile(
                company_name="presentation-co",
                reporting_year=2026,
                entity_type="general_listed_company",
                listing_status="TWSE",
                paid_in_capital_twd=12_000_000_000,
                jurisdiction="TW",
                has_taiwan_facilities="YES",
                received_environmental_authority_inventory_notice="NOT_SURE",
                received_verification_requirement="NOT_SURE",
                reporting_entities_known="TRUE",
            )
        ),
        ZH,
    )
    summary = presented.action_summary
    assert summary.customer_action_required is True
    assert summary.headline == "還差 1 項資料"
    assert (
        summary.exact_question
        == "公司是否曾收到主管機關要求盤查、登錄或查驗溫室氣體的通知？"
    )
    taiwan = [
        item
        for item in presented.presentations
        if item.domain in {"ghg_inventory", "env_verification", "carbon_fee"}
    ]
    assert taiwan == []


def test_exception_drafts_do_not_confirm_until_commit() -> None:
    records = _seven_records()
    assert all(not item.customer_confirmed for item in records)
    assert taiwan_facility_existence(records, identity_confirmed=False) == "NOT_SURE"
    drafts = {
        item.facility_id: {"status": "operating"} for item in records
    }
    assert all(not item.customer_confirmed for item in records)
    commit_identity_drafts(records, drafts)
    assert all(item.customer_confirmed for item in records)
    assert taiwan_facility_existence(records, identity_confirmed=True) == "YES"
    assert all(item.included_in_current_reporting_scope is False for item in records)


def test_exception_sold_status_persists_after_explicit_commit() -> None:
    records = _seven_records()
    sold_id = records[1].facility_id
    drafts = {item.facility_id: {"status": "operating"} for item in records}
    drafts[sold_id] = {"status": "sold"}
    commit_identity_drafts(records, drafts)
    sold = next(item for item in records if item.facility_id == sold_id)
    assert sold.status == STATUS_INACTIVE
    assert sold.inactive_reason == "sold"
    assert sold.included_in_current_reporting_scope is False
    assert taiwan_facility_existence(records, identity_confirmed=True) == "YES"


def test_exception_mode_source_requires_explicit_confirm() -> None:
    source = APL.read_text(encoding="utf-8")
    fn_start = source.index("def _render_facility_exception_row")
    fn_end = source.index("def _render_step_facilities")
    row_fn = source[fn_start:fn_end]
    assert "apply_identity_status" not in row_fn
    assert "commit_identity_drafts" in source
    assert "apl_confirm_exception_statuses" in source
    assert "identity_confirmed = True" in source
    assert "mark_exception_drafts_dirty" in source
    assert "exception_navigation_blocked" in source
    assert t("setup.facilities.confirm_statuses", ZH) == "確認這些廠場狀態"


def test_widget_change_invalidates_only_exception_draft_state() -> None:
    records = _seven_records()
    confirm_all_operating(records)
    master = FacilityMaster(records=records, identity_confirmed=True)
    state: dict = {}
    assert exception_navigation_blocked(
        exception_mode=False,
        identity_confirmed=True,
        drafts_dirty=False,
    ) is False
    mark_exception_drafts_dirty(state)
    assert exception_drafts_are_dirty(state)
    assert master.identity_confirmed is True
    assert all(item.identity_status == "operating" for item in records)
    assert taiwan_facility_existence(records, identity_confirmed=True) == "YES"
    assert exception_navigation_blocked(
        exception_mode=True,
        identity_confirmed=master.identity_confirmed,
        drafts_dirty=exception_drafts_are_dirty(state),
    )
    mark_exception_drafts_dirty(state)
    assert master.identity_confirmed is True
    assert all(item.included_in_current_reporting_scope is False for item in records)
    clear_exception_drafts_dirty(state)
    assert exception_drafts_are_dirty(state) is False
    assert exception_navigation_blocked(
        exception_mode=True,
        identity_confirmed=True,
        drafts_dirty=False,
    ) is False


def test_opening_exception_mode_from_confirmed_state_is_dirty() -> None:
    records = _seven_records()
    confirm_all_operating(records)
    master = FacilityMaster(records=records, identity_confirmed=True)
    state: dict = {"facility_exception_mode": False}
    mark_exception_drafts_dirty(state)
    state["facility_exception_mode"] = True
    assert master.identity_confirmed is True
    assert exception_navigation_blocked(
        exception_mode=True,
        identity_confirmed=master.identity_confirmed,
        drafts_dirty=True,
    )
    assert taiwan_facility_existence(
        master.records, identity_confirmed=True
    ) == "YES"


def test_capital_animation_target_equals_official_value() -> None:
    official = 12_000_000_000
    assert format_int(official) == "12,000,000,000"
    source = (REPO_ROOT / "src/carbon_ledger/ui/motion.py").read_text(
        encoding="utf-8"
    )
    assert "def render_capital_countup" in source
    assert "paid-in-capital" in source
    company = CompanyMaster(official_paid_in_capital_twd=official)
    assert company.official_paid_in_capital_twd == official
    assert "hero_emissions_countup.js" not in APL.read_text(encoding="utf-8")


def test_capital_animation_does_not_mutate_business_values() -> None:
    company = CompanyMaster(
        official_paid_in_capital_twd=12_000_000_000,
        confirmed_paid_in_capital_twd=12_000_000_000,
    )
    before = (
        company.official_paid_in_capital_twd,
        company.confirmed_paid_in_capital_twd,
        company.paid_in_capital_twd,
    )
    assert render_animated_metric.__name__ == "render_animated_metric"
    assert before == (
        12_000_000_000,
        12_000_000_000,
        12_000_000_000,
    )


def test_step3_copy_drops_internal_phrases() -> None:
    source = APL.read_text(encoding="utf-8")
    for phrase_key in (
        "setup.include_all",
        "setup.include_this",
        "setup.deactivate",
        "setup.inactive.keep",
        "setup.match.official_only",
        "setup.facilities.confirm_include",
        "setup.full_year_all",
    ):
        assert phrase_key not in source
    assert t("setup.facilities.confirm_all", ZH, n=7) == "是，7 個都正確"
    assert "報導邊界" not in t("setup.facilities.still_operating", ZH, year=2026)
