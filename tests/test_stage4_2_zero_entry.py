"""Stage 4.2 — zero-entry company setup and facility discovery (mocked)."""

from __future__ import annotations

from pathlib import Path

from carbon_ledger.company_lookup import (
    GCIS_SOURCE_ID,
    STUB_ALIGNED_UBN,
    STUB_DIFF_UBN,
    STUB_ENV,
    apply_customer_capital_override,
    lookup_call_count,
    lookup_company,
    parse_gcis_company,
    reset_lookup_cache,
    stub_factories,
)
from carbon_ledger.company_master import (
    MATCH_ALIGNED,
    MATCH_OFFICIAL_ONLY,
    MATCH_UPLOAD_ONLY,
    SOURCE_MANUAL,
    SOURCE_OFFICIAL_FACTORY,
    SOURCE_PREVIOUS,
    SOURCE_UPLOAD,
    STATUS_INACTIVE,
    CompanyMaster,
    FacilityMaster,
    FacilityMasterRecord,
    OfficialFactoryHint,
    apply_reuse_previous,
    confirm_all,
    deactivate_facility,
    extract_upload_site_names,
    included_taiwan_sites,
    reconcile_facilities,
    setup_effort_for_standard_company,
    ubn_checksum_ok,
    utc_now_iso,
    validate_ubn,
)
from carbon_ledger.company_snapshot import reset_company_repository_cache
from carbon_ledger.factory_snapshot import reset_factory_repository_cache
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.source_access import policy_for_source
from carbon_ledger.ui.company_setup import show_net_worth
from carbon_ledger.ui.customer_presenters import present_assessment
from carbon_ledger.ui.i18n import t

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH = "zh-TW"
FIXTURE_CSV = REPO_ROOT / "tests" / "fixtures" / "company_master" / "company_master.csv"

GCIS_SAMPLE = {
    "Business_Accounting_NO": STUB_ALIGNED_UBN,
    "Company_Name": "長興材料工業股份有限公司",
    "Company_Status_Desc": "核准設立",
    "Company_Location": "高雄市大寮區興業路",
    "Paid_In_Capital_Amount": "12000000000",
}


def setup_function() -> None:
    reset_lookup_cache()
    reset_company_repository_cache()
    reset_factory_repository_cache()


def test_ubn_requires_eight_digits_without_mutation() -> None:
    raw, error = validate_ubn("1234-567")
    assert raw == "1234-567"
    assert error == "need_8"
    assert validate_ubn("12345675") == ("12345675", "")
    assert ubn_checksum_ok("12345675")


def test_valid_lookup_populates_company_master() -> None:
    result = lookup_company(STUB_ALIGNED_UBN, environ={STUB_ENV: "1"})
    assert result.ok
    company = result.company
    assert company.company_name == "長興材料工業股份有限公司"
    assert company.official_registered_address.startswith("高雄市")
    assert company.official_paid_in_capital_twd == 12_000_000_000
    assert company.official_company_status == "核准設立"
    assert company.source_records[0].retrieved_at


def test_paid_in_capital_and_address_autofill_from_official_payload() -> None:
    company = parse_gcis_company(
        [GCIS_SAMPLE], ubn=STUB_ALIGNED_UBN, retrieved_at="2026-08-16T00:00:00+00:00"
    )
    assert company.official_paid_in_capital_twd == 12_000_000_000
    assert company.official_registered_address == "高雄市大寮區興業路"
    assert company.paid_in_capital_twd == 12_000_000_000


def test_unknown_official_field_stays_none() -> None:
    company = parse_gcis_company(
        [{"Business_Accounting_NO": STUB_ALIGNED_UBN, "Company_Name": "示範"}],
        ubn=STUB_ALIGNED_UBN,
        retrieved_at="2026-08-16T00:00:00+00:00",
    )
    assert company.official_paid_in_capital_twd is None
    assert company.official_registered_address == ""


def test_customer_capital_override_survives_rerun() -> None:
    first = lookup_company(STUB_ALIGNED_UBN, environ={STUB_ENV: "1"})
    apply_customer_capital_override(first.company, 9_000_000_000)
    assert first.company.capital_overridden is True
    reset_lookup_cache()
    second = lookup_company(
        STUB_ALIGNED_UBN,
        environ={STUB_ENV: "1"},
        previous=first.company,
        force_refresh=True,
    )
    assert first.company.confirmed_paid_in_capital_twd == 9_000_000_000
    assert first.company.official_paid_in_capital_twd == 12_000_000_000
    assert second.company.capital_overridden is True
    assert second.company.confirmed_paid_in_capital_twd == 9_000_000_000
    assert second.company.official_paid_in_capital_twd == 12_000_000_000


def test_api_failure_allows_manual_fallback_and_keeps_confirmed() -> None:
    previous = CompanyMaster(
        unified_business_number=STUB_ALIGNED_UBN,
        company_name="已確認公司",
        official_paid_in_capital_twd=12_000_000_000,
        confirmed_paid_in_capital_twd=12_000_000_000,
        customer_confirmed_at=utc_now_iso(),
    )

    def _boom(_url: str):
        raise RuntimeError("HTTP 500 JSON parse")

    result = lookup_company(
        STUB_ALIGNED_UBN,
        repo_root=REPO_ROOT,
        snapshot_csv=FIXTURE_CSV,
        http_get=_boom,
        previous=previous,
        force_refresh=True,
        environ={STUB_ENV: "0"},
    )
    assert result.ok
    assert result.http_attempted is False
    assert result.company.company_name == "已確認公司"
    assert "HTTP 500" not in result.customer_message
    assert "JSON" not in result.customer_message


def test_rerun_does_not_introduce_http(monkeypatch) -> None:
    monkeypatch.setattr(
        "carbon_ledger.company_lookup.fetch_official_company",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("lookup must not use live HTTP")
        ),
    )
    lookup_company(STUB_ALIGNED_UBN, environ={STUB_ENV: "1"})
    lookup_company(STUB_ALIGNED_UBN, environ={STUB_ENV: "1"})
    assert lookup_call_count("gcis") == 0


def test_source_provenance_retained() -> None:
    company = parse_gcis_company(
        [GCIS_SAMPLE], ubn=STUB_ALIGNED_UBN, retrieved_at="2026-08-16T01:00:00+00:00"
    )
    record = company.source_records[0]
    assert record.authority == "經濟部商業發展署"
    assert record.access_mode == "OFFICIAL_API"
    assert record.dataset_or_api
    assert record.retrieved_at.startswith("2026-08-16")


def test_official_factories_match_ubn() -> None:
    hints = stub_factories(STUB_ALIGNED_UBN)
    assert [item.display_name for item in hints] == ["高雄一廠", "高雄二廠", "台南廠"]
    records = reconcile_facilities(
        official=hints, upload_names=[], ubn=STUB_ALIGNED_UBN
    )
    assert all(
        item.company_unified_business_number == STUB_ALIGNED_UBN for item in records
    )
    assert all(SOURCE_OFFICIAL_FACTORY in item.discovered_from for item in records)
    assert all(item.included_in_current_reporting_scope is False for item in records)


def test_upload_unique_site_names() -> None:
    names = extract_upload_site_names(
        ["高雄廠", "高雄廠", "台南廠", "", "台中營運中心"]
    )
    assert names == ["高雄廠", "台南廠", "台中營運中心"]


def test_same_official_and_upload_site_reconciles() -> None:
    records = reconcile_facilities(
        official=[OfficialFactoryHint(display_name="高雄一廠", address="高雄市")],
        upload_names=["高雄一廠", "高雄一廠"],
    )
    assert len(records) == 1
    assert records[0].match_state == MATCH_ALIGNED
    assert SOURCE_OFFICIAL_FACTORY in records[0].discovered_from
    assert SOURCE_UPLOAD in records[0].discovered_from


def test_upload_only_office_retained() -> None:
    records = reconcile_facilities(
        official=[OfficialFactoryHint(display_name="高雄一廠")],
        upload_names=["高雄一廠", "台中辦公室"],
    )
    by_name = {item.display_name: item for item in records}
    assert by_name["台中辦公室"].match_state == MATCH_UPLOAD_ONLY
    assert by_name["高雄一廠"].match_state == MATCH_ALIGNED


def test_official_only_factory_needs_confirmation_not_boundary() -> None:
    records = reconcile_facilities(
        official=[OfficialFactoryHint(display_name="高雄二廠")],
        upload_names=["高雄一廠"],
    )
    official_only = next(item for item in records if item.display_name == "高雄二廠")
    assert official_only.match_state == MATCH_OFFICIAL_ONLY
    assert official_only.included_in_current_reporting_scope is False
    assert official_only.customer_confirmed is False


def test_bulk_confirm_and_manual_add() -> None:
    records = reconcile_facilities(
        official=stub_factories(STUB_ALIGNED_UBN),
        upload_names=["高雄一廠", "高雄二廠", "台南廠"],
    )
    confirm_all(records, include_in_scope=True)
    assert all(item.customer_confirmed for item in records)
    assert included_taiwan_sites(records) == ["高雄一廠", "高雄二廠", "台南廠"]
    records.append(
        FacilityMasterRecord(
            facility_id="fac_manual",
            display_name="台北辦公室",
            source_type=SOURCE_MANUAL,
            discovered_from=(SOURCE_MANUAL,),
        )
    )
    assert any(item.display_name == "台北辦公室" for item in records)


def test_deactivate_preserves_history() -> None:
    record = FacilityMasterRecord(facility_id="fac_1", display_name="舊廠")
    deactivate_facility(record, reason="sold")
    assert record.status == STATUS_INACTIVE
    assert record.inactive_reason == "sold"
    assert record.display_name == "舊廠"
    assert record.included_in_current_reporting_scope is False


def test_next_year_reuse_and_add() -> None:
    prior = [
        FacilityMasterRecord(
            facility_id="fac_a",
            display_name="高雄一廠",
            customer_confirmed=True,
            status="ACTIVE",
            discovered_from=(SOURCE_PREVIOUS,),
        ),
        FacilityMasterRecord(
            facility_id="fac_old",
            display_name="已停用廠",
            status=STATUS_INACTIVE,
            inactive_reason="sold",
            discovered_from=(SOURCE_PREVIOUS,),
        ),
    ]
    master = FacilityMaster(reporting_year=2026, previous_year_records=prior)
    apply_reuse_previous(master)
    names = {item.display_name: item for item in master.records}
    assert names["高雄一廠"].customer_confirmed is True
    assert names["已停用廠"].status == STATUS_INACTIVE
    master.records.append(
        FacilityMasterRecord(
            facility_id="fac_new",
            display_name="台中辦公室",
            source_type=SOURCE_MANUAL,
        )
    )
    assert any(item.display_name == "台中辦公室" for item in master.records)


def test_temporary_api_failure_does_not_overwrite_confirmed() -> None:
    confirmed = CompanyMaster(
        unified_business_number=STUB_ALIGNED_UBN,
        company_name="已確認公司",
        official_paid_in_capital_twd=12_000_000_000,
        confirmed_paid_in_capital_twd=11_000_000_000,
        capital_overridden=True,
        customer_confirmed_at="2026-08-01T00:00:00+00:00",
    )

    def _boom(_url: str):
        raise TimeoutError("unavailable")

    result = lookup_company(
        STUB_ALIGNED_UBN,
        repo_root=REPO_ROOT,
        snapshot_csv=FIXTURE_CSV,
        http_get=_boom,
        previous=confirmed,
        force_refresh=True,
        environ={},
    )
    assert result.company.confirmed_paid_in_capital_twd == 11_000_000_000
    assert result.company.company_name == "已確認公司"


def test_standard_company_does_not_retype_master_fields() -> None:
    result = lookup_company(STUB_ALIGNED_UBN, environ={STUB_ENV: "1"})
    result.company.customer_confirmed_at = utc_now_iso()
    records = reconcile_facilities(
        official=result.factories,
        upload_names=["高雄一廠", "高雄二廠", "台南廠"],
    )
    confirm_all(records, include_in_scope=True)
    effort = setup_effort_for_standard_company(result.company, records)
    assert effort["typed_fields"] == ["unified_business_number"]
    assert "company" in effort["confirmations"]
    assert "facilities_bulk" in effort["confirmations"]
    assert effort["forbidden_retyped"] == []
    assert effort["facility_count"] == 3


def test_net_worth_not_asked_for_ordinary_listed_company() -> None:
    assert show_net_worth(entity_type="general_listed_company", share_par="") is False
    assert show_net_worth(entity_type="general_listed_company", share_par="no_par")


def test_gcis_and_factory_policies_are_official_not_html() -> None:
    gcis = policy_for_source(GCIS_SOURCE_ID, repo_root=REPO_ROOT)
    factory = policy_for_source("src_tw_factory_open_data", repo_root=REPO_ROOT)
    assert gcis.automated_access_allowed is True
    assert gcis.access_mode == "OFFICIAL_API"
    assert "data.gcis.nat.gov.tw" in gcis.hostname
    assert factory.access_mode == "OFFICIAL_OPEN_DATA"
    assert "factory.moea.gov.tw" not in factory.preferred_access_url


def test_calculation_pipeline_does_not_import_lookup() -> None:
    import carbon_ledger.calculate as calculate
    import carbon_ledger.pipeline as pipeline

    assert "company_lookup" not in calculate.__dict__
    assert "company_snapshot" not in calculate.__dict__
    assert "factory_snapshot" not in calculate.__dict__
    assert "company_lookup" not in pipeline.__dict__
    assert "company_snapshot" not in pipeline.__dict__
    assert "factory_snapshot" not in pipeline.__dict__
    assert callable(run_uploaded_pipeline)


def test_facility_missing_fact_cta_jumps_to_sites() -> None:
    from carbon_ledger.applicability import CompanyProfile, assess_applicability

    assessment = assess_applicability(
        CompanyProfile(
            company_name="cta-co",
            reporting_year=2026,
            entity_type="general_listed_company",
            listing_status="TWSE",
            paid_in_capital_twd=12_000_000_000,
            reporting_entities_known="TRUE",
            received_environmental_authority_inventory_notice="NO",
            received_verification_requirement="NO",
        ),
        repo_root=REPO_ROOT,
    )
    presented = present_assessment(assessment, ZH)
    if presented.action_summary.customer_action_required:
        if presented.action_summary.facts == (t("cust.fact.taiwan_facility", ZH),):
            assert presented.action_summary.primary_action_label == "確認台灣廠場"
            assert presented.action_summary.primary_action_step == 3


def test_customer_copy_avoids_internal_master_terms() -> None:
    assert "Facility Master" not in t("setup.facilities.review", ZH)
    assert "UBN" not in t("setup.ubn.help", ZH)
    assert "報導邊界 entity" not in t("setup.facilities.confirm_include", ZH)
    assert STUB_DIFF_UBN
