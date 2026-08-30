"""Normative Stage 4.2H-A boundary-semantics contracts."""

from __future__ import annotations

from dataclasses import replace

import pytest

from carbon_ledger.applicability import (
    STATUS_APPLICABLE,
    STATUS_FUTURE_REQUIREMENT,
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
    CONSOLIDATION_CONSOLIDATED,
    CONSOLIDATION_STANDALONE,
    EVIDENCE_CONFIRMED_COMPANY_DOCUMENT,
    EVIDENCE_CUSTOMER_PENDING,
    EVIDENCE_VERIFIED_OFFICIAL,
    MEMBERSHIP_INCLUDED,
    OPERATING_FULL_PERIOD,
    PURPOSE_IFRS_REPORTING_ENTITY,
    PURPOSE_LISTED_CONSOLIDATED,
    PURPOSE_MOENV_FACILITY,
    PURPOSE_OUTCOME_FUTURE,
    PURPOSE_OUTCOME_UNRESOLVED,
    RECONCILIATION_DUPLICATE,
    RECONCILIATION_MATCHED,
    BoundarySemanticsState,
    CanonicalSite,
    CompetentAuthorityBoundaryEvidence,
    FinancialStatementReportingEntityEvidence,
    PeriodOperatingFact,
    ProfessionalReviewMetadata,
    ReportingPeriod,
    boundaries_from_reviews,
    build_boundary_review_queues,
    initial_boundary_semantics_state,
    purpose_reviews_from_assessment,
)
from carbon_ledger.legal_entity import CONFIRMATION_LOCAL, LegalEntity


def _assessment(
    obligations: dict[str, ObligationResult],
) -> ApplicabilityAssessment:
    return ApplicabilityAssessment(
        assessment_timestamp="2026-08-24T00:00:00Z",
        reporting_year=2026,
        company_profile_snapshot={},
        obligations=obligations,
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


def _company(*, listing_status: str = "") -> CompanyMaster:
    return CompanyMaster(
        company_id="company_one",
        company_name="測試股份有限公司",
        unified_business_number="12345675",
        listing_status=listing_status,
    )


def _entity() -> LegalEntity:
    return LegalEntity(
        entity_id="company_one",
        legal_name="測試股份有限公司",
        jurisdiction="TW",
        taiwan_ubn="12345675",
        confirmation_state=CONFIRMATION_LOCAL,
        locally_confirmed_at="2026-08-24T00:00:00Z",
    )


def _facility(index: int) -> FacilityMasterRecord:
    return FacilityMasterRecord(
        facility_id=f"raw_facility_{index}",
        display_name=f"政府列示工廠 {index}",
        address=f"高雄市測試路 {index} 號",
        official_factory_registration_number=f"REG-{index:03d}",
        company_unified_business_number="12345675",
        discovered_from=(SOURCE_OFFICIAL_FACTORY,),
    )


def _moenv_assessment(status: str = STATUS_NEEDS_INFORMATION):
    return _assessment(
        {
            "ghg_inventory": ObligationResult(
                obligation_id="ghg_inventory",
                obligation_name="GHG Inventory",
                status=status,
            )
        }
    )


def _verified_authority_evidence(
    *,
    evidence_id: str,
    unit: str,
    site_ids: tuple[str, ...],
) -> CompetentAuthorityBoundaryEvidence:
    return CompetentAuthorityBoundaryEvidence(
        evidence_id=evidence_id,
        purpose=PURPOSE_MOENV_FACILITY,
        authority="環境部",
        source_id=f"official-{evidence_id}",
        document_type="operating_boundary",
        document_or_registration_identifier=f"DOC-{evidence_id}",
        described_reporting_or_operating_unit=unit,
        effective_start="2025-01-01",
        effective_end="2027-12-31",
        provenance_reference=f"https://official.example/{evidence_id}",
        verification_state=EVIDENCE_VERIFIED_OFFICIAL,
        linked_canonical_site_ids=site_ids,
    )


def test_purpose_mapping_uses_assessment_only_not_listing_or_factory_rows() -> None:
    assessment = _assessment(
        {
            "ghg_inventory": ObligationResult(
                obligation_id="ghg_inventory",
                obligation_name="GHG Inventory",
                status=STATUS_NEEDS_INFORMATION,
            ),
            "ifrs_s1_s2": ObligationResult(
                obligation_id="ifrs_s1_s2",
                obligation_name="IFRS S1/S2",
                status=STATUS_APPLICABLE,
                applied_rule_ids=[],
            ),
        }
    )
    reviews = purpose_reviews_from_assessment(
        assessment=assessment,
        workspace_id="tw-ubn-12345675",
        reporting_period_id=_period().reporting_period_id,
    )
    assert [item.purpose for item in reviews] == [PURPOSE_MOENV_FACILITY]
    assert reviews[0].outcome == PURPOSE_OUTCOME_UNRESOLVED

    state = initial_boundary_semantics_state(
        assessment=assessment,
        company=_company(listing_status="TWSE"),
        facilities=[_facility(index) for index in range(40)],
        workspace_id="tw-ubn-12345675",
        reporting_period=_period(),
    )
    assert [item.purpose for item in state.purpose_reviews] == [
        PURPOSE_MOENV_FACILITY
    ]
    assert len(state.registration_candidates) == 40
    assert state.boundaries == ()


def test_exact_ifrs_and_consolidated_rules_create_distinct_reviews() -> None:
    assessment = _assessment(
        {
            "ifrs_s1_s2": ObligationResult(
                obligation_id="ifrs_s1_s2",
                obligation_name="IFRS S1/S2",
                status=STATUS_APPLICABLE,
                applied_rule_ids=["tw_order_51756_phase1_ge_10bn"],
            ),
            "verification_assurance": ObligationResult(
                obligation_id="verification_assurance",
                obligation_name="Verification",
                status=STATUS_APPLICABLE,
                applied_rule_ids=[
                    "tw_order_51756_scope12_consolidated_assurance"
                ],
            ),
        }
    )
    reviews = purpose_reviews_from_assessment(
        assessment=assessment,
        workspace_id="tw-ubn-12345675",
        reporting_period_id=_period().reporting_period_id,
    )
    assert {item.purpose for item in reviews} == {
        PURPOSE_IFRS_REPORTING_ENTITY,
        PURPOSE_LISTED_CONSOLIDATED,
    }
    assert all(item.outcome == PURPOSE_OUTCOME_UNRESOLVED for item in reviews)
    assert len({item.purpose_review_id for item in reviews}) == 2


def test_ifrs_future_review_has_no_current_boundary() -> None:
    assessment = _assessment(
        {
            "ifrs_s1_s2": ObligationResult(
                obligation_id="ifrs_s1_s2",
                obligation_name="IFRS S1/S2",
                status=STATUS_FUTURE_REQUIREMENT,
                applied_rule_ids=["tw_order_51756_phase2_5_to_10bn"],
            )
        }
    )
    reviews = purpose_reviews_from_assessment(
        assessment=assessment,
        workspace_id="tw-ubn-12345675",
        reporting_period_id=_period().reporting_period_id,
    )
    assert len(reviews) == 1
    assert reviews[0].outcome == PURPOSE_OUTCOME_FUTURE
    evidence = FinancialStatementReportingEntityEvidence(
        evidence_id="financial_evidence",
        reporting_period_id=_period().reporting_period_id,
        financial_statement_title="合併財務報告",
        financial_statement_type="consolidated",
        issuer_or_source="財會部",
        reporting_entity_identifier="group_one",
        reporting_entity_name="測試集團",
        consolidation_basis=CONSOLIDATION_CONSOLIDATED,
        included_legal_entity_ids=("company_one",),
        provenance_reference="fs-2026",
        verification_state=EVIDENCE_CONFIRMED_COMPANY_DOCUMENT,
    )
    assert (
        boundaries_from_reviews(
            reviews=reviews,
            reporting_period=_period(),
            legal_entities=(_entity(),),
            financial_statement_evidence=(evidence,),
        )
        == ()
    )


def test_registration_candidates_are_not_sites_and_can_reconcile_many_to_one() -> None:
    period = _period()
    state = initial_boundary_semantics_state(
        assessment=_moenv_assessment(),
        company=_company(),
        facilities=[_facility(index) for index in range(40)],
        workspace_id="tw-ubn-12345675",
        reporting_period=period,
    )
    sites = tuple(
        CanonicalSite(
            site_id=f"site_{index}",
            display_name=f"實際據點 {index}",
            address=f"高雄市實際路 {index} 號",
            company_entity_id="company_one",
        )
        for index in range(12)
    )
    reconciliations = []
    for index, value in enumerate(state.registration_reconciliations):
        site_id = sites[index % 12].site_id
        reconciliations.append(
            replace(
                value,
                state=(
                    RECONCILIATION_MATCHED
                    if index < 12
                    else RECONCILIATION_DUPLICATE
                ),
                canonical_site_id=site_id,
                primary_candidate_id=(
                    ""
                    if index < 12
                    else state.registration_candidates[index % 12].candidate_id
                ),
            )
        )
    state = replace(
        state,
        canonical_sites=sites,
        registration_reconciliations=tuple(reconciliations),
    )
    queues = build_boundary_review_queues(state)
    assert len(queues.registration_reconciliations) == 40
    assert len(queues.operating_facts) == 12
    assert queues.facility_memberships == ()


def test_no_verified_authority_evidence_means_zero_moenv_boundaries() -> None:
    period = _period()
    reviews = purpose_reviews_from_assessment(
        assessment=_moenv_assessment(),
        workspace_id="tw-ubn-12345675",
        reporting_period_id=period.reporting_period_id,
    )
    pending = CompetentAuthorityBoundaryEvidence(
        evidence_id="pending_document",
        purpose=PURPOSE_MOENV_FACILITY,
        authority="環境部",
        source_id="customer-upload",
        document_type="registration_boundary",
        document_or_registration_identifier="DOC-PENDING",
        described_reporting_or_operating_unit="待覆核單位",
        effective_start="2026-01-01",
        effective_end="2026-12-31",
        provenance_reference="local-upload",
        verification_state=EVIDENCE_CUSTOMER_PENDING,
        linked_canonical_site_ids=("site_one",),
        professional_review_metadata=ProfessionalReviewMetadata(
            reviewer_name="顧問",
            reviewer_role="查證人員",
            reviewed_at="2026-08-24",
            review_note="看起來合理",
        ),
    )
    assert (
        boundaries_from_reviews(
            reviews=reviews,
            reporting_period=period,
            legal_entities=(_entity(),),
            authority_evidence=(pending,),
        )
        == ()
    )
    assert pending.can_define_moenv_boundary is False


@pytest.mark.parametrize(
    "missing_field",
    [
        "authority",
        "source_id",
        "document_type",
        "document_or_registration_identifier",
        "described_reporting_or_operating_unit",
        "effective_start",
        "effective_end",
        "provenance_reference",
    ],
)
def test_verified_authority_evidence_requires_typed_provenance(
    missing_field: str,
) -> None:
    values = {
        "evidence_id": "evidence_one",
        "purpose": PURPOSE_MOENV_FACILITY,
        "authority": "環境部",
        "source_id": "official-source",
        "document_type": "operating_boundary",
        "document_or_registration_identifier": "DOC-001",
        "described_reporting_or_operating_unit": "第一申報單位",
        "effective_start": "2026-01-01",
        "effective_end": "2026-12-31",
        "provenance_reference": "https://official.example/doc",
        "verification_state": EVIDENCE_VERIFIED_OFFICIAL,
        "linked_canonical_site_ids": ("site_one",),
    }
    values[missing_field] = ""
    with pytest.raises(ValueError, match="complete authority provenance"):
        CompetentAuthorityBoundaryEvidence(**values)


def test_two_verified_authority_units_create_exactly_two_boundaries() -> None:
    period = _period()
    reviews = purpose_reviews_from_assessment(
        assessment=_moenv_assessment(),
        workspace_id="tw-ubn-12345675",
        reporting_period_id=period.reporting_period_id,
    )
    evidence = (
        _verified_authority_evidence(
            evidence_id="unit_a",
            unit="主管機關單位 A",
            site_ids=("site_one", "site_two"),
        ),
        _verified_authority_evidence(
            evidence_id="unit_b",
            unit="主管機關單位 B",
            site_ids=("site_three",),
        ),
    )
    boundaries = boundaries_from_reviews(
        reviews=reviews,
        reporting_period=period,
        legal_entities=(_entity(),),
        authority_evidence=evidence,
    )
    assert len(boundaries) == 2
    assert {item.display_name for item in boundaries} == {
        "主管機關單位 A",
        "主管機關單位 B",
    }
    assert {
        member.canonical_site_id
        for boundary in boundaries
        for member in boundary.facility_memberships
    } == {"site_one", "site_two", "site_three"}


@pytest.mark.parametrize(
    ("basis", "expected"),
    [
        (CONSOLIDATION_STANDALONE, CONSOLIDATION_STANDALONE),
        (CONSOLIDATION_CONSOLIDATED, CONSOLIDATION_CONSOLIDATED),
    ],
)
def test_ifrs_boundary_composition_comes_from_financial_statement_evidence(
    basis: str,
    expected: str,
) -> None:
    period = _period()
    assessment = _assessment(
        {
            "ifrs_s1_s2": ObligationResult(
                obligation_id="ifrs_s1_s2",
                obligation_name="IFRS S1/S2",
                status=STATUS_APPLICABLE,
                applied_rule_ids=["tw_order_51756_phase1_ge_10bn"],
            )
        }
    )
    reviews = purpose_reviews_from_assessment(
        assessment=assessment,
        workspace_id="tw-ubn-12345675",
        reporting_period_id=period.reporting_period_id,
    )
    assert (
        boundaries_from_reviews(
            reviews=reviews,
            reporting_period=period,
            legal_entities=(_entity(),),
        )
        == ()
    )
    evidence = FinancialStatementReportingEntityEvidence(
        evidence_id="financial_evidence",
        reporting_period_id=period.reporting_period_id,
        financial_statement_title="2026 年財務報告",
        financial_statement_type=basis,
        issuer_or_source="財會部",
        reporting_entity_identifier="reporting_entity_one",
        reporting_entity_name="測試報導個體",
        consolidation_basis=basis,
        included_legal_entity_ids=("company_one",),
        provenance_reference="financial-statements-2026",
        verification_state=EVIDENCE_CONFIRMED_COMPANY_DOCUMENT,
    )
    boundaries = boundaries_from_reviews(
        reviews=reviews,
        reporting_period=period,
        legal_entities=(_entity(),),
        financial_statement_evidence=(evidence,),
    )
    assert len(boundaries) == 1
    assert boundaries[0].purpose == PURPOSE_IFRS_REPORTING_ENTITY
    assert boundaries[0].composition_basis == expected


def test_v2_local_confirmation_has_no_source_category_gate() -> None:
    period = _period()
    reviews = purpose_reviews_from_assessment(
        assessment=_moenv_assessment(),
        workspace_id="tw-ubn-12345675",
        reporting_period_id=period.reporting_period_id,
    )
    boundaries = boundaries_from_reviews(
        reviews=reviews,
        reporting_period=period,
        legal_entities=(_entity(),),
        authority_evidence=(
            _verified_authority_evidence(
                evidence_id="unit_a",
                unit="主管機關單位 A",
                site_ids=("site_one",),
            ),
        ),
    )
    boundary = replace(
        boundaries[0],
        entity_memberships=tuple(
            replace(item, state=MEMBERSHIP_INCLUDED)
            for item in boundaries[0].entity_memberships
        ),
        facility_memberships=tuple(
            replace(item, state=MEMBERSHIP_INCLUDED)
            for item in boundaries[0].facility_memberships
        ),
    )
    state = BoundarySemanticsState(
        reporting_period=period,
        purpose_reviews=reviews,
        canonical_sites=(
            CanonicalSite(
                site_id="site_one",
                display_name="實際據點",
                address="高雄市",
                company_entity_id="company_one",
            ),
        ),
        operating_facts=(
            PeriodOperatingFact(
                operating_fact_id="operating_one",
                canonical_site_id="site_one",
                reporting_period_id=period.reporting_period_id,
                status=OPERATING_FULL_PERIOD,
            ),
        ),
        authority_evidence=boundary.authority_evidence,
        boundaries=(boundary,),
        responsible_contact_name="王小明",
        responsible_job_title="永續主管",
    )
    confirmed = state.locally_confirmed(at="2026-08-24T00:00:00Z")
    assert confirmed.confirmation_state == CONFIRMATION_LOCAL
    assert confirmed.boundaries[0].expected_categories == ()
    assert confirmed.authority_evidence[0].verification_state == (
        EVIDENCE_VERIFIED_OFFICIAL
    )
