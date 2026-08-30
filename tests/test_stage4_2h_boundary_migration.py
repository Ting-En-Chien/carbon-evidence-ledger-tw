"""Explicit and rollback-compatible boundary-semantics-v2 migration."""

from __future__ import annotations

from pathlib import Path

import pytest

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
from carbon_ledger.company_workspace import CompanyWorkspace
from carbon_ledger.inventory_boundary import (
    CATEGORY_EXPECTED,
    PURPOSE_IFRS_REPORTING_ENTITY,
    REQUIREMENT_NEEDS_FACT,
    SOURCE_CATEGORIES,
    ExpectedSourceCategory,
    InventoryBoundary,
    RegistrationLink,
    ReportingPeriod,
    initial_boundary_semantics_state,
)


def _period() -> ReportingPeriod:
    return ReportingPeriod.confirmed(
        reporting_year_suggested=2026,
        reporting_year_confirmed=2026,
        period_start_confirmed="2026-01-01",
        period_end_confirmed="2026-12-31",
    )


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


def _company() -> CompanyMaster:
    return CompanyMaster(
        company_id="company_one",
        company_name="測試股份有限公司",
        unified_business_number="12345675",
    )


def _facilities() -> list[FacilityMasterRecord]:
    return [
        FacilityMasterRecord(
            facility_id="raw_one",
            display_name="政府工廠一",
            address="高雄市一號",
            official_factory_registration_number="REG-001",
            company_unified_business_number="12345675",
            discovered_from=(SOURCE_OFFICIAL_FACTORY,),
        ),
        FacilityMasterRecord(
            facility_id="raw_two",
            display_name="政府工廠二",
            address="高雄市二號",
            official_factory_registration_number="REG-002",
            company_unified_business_number="12345675",
            discovered_from=(SOURCE_OFFICIAL_FACTORY,),
        ),
    ]


def _legacy_boundary() -> InventoryBoundary:
    period = _period()
    return InventoryBoundary(
        boundary_id="legacy_boundary",
        purpose=PURPOSE_IFRS_REPORTING_ENTITY,
        requirement_status=REQUIREMENT_NEEDS_FACT,
        display_name="舊版範圍提示",
        reporting_period=period,
        registration_links=(
            RegistrationLink(
                registration_link_id="registration_link_one",
                registration_identity="REG-001",
                facility_id="raw_one",
                official_source=SOURCE_OFFICIAL_FACTORY,
                location="高雄市一號",
                combined_with=("registration_link_two",),
                combination_basis="公司主張是同一單位",
                combination_evidence="顧問覆核筆記",
            ),
            RegistrationLink(
                registration_link_id="registration_link_two",
                registration_identity="REG-002",
                facility_id="raw_two",
                official_source=SOURCE_OFFICIAL_FACTORY,
                location="高雄市二號",
            ),
        ),
        expected_categories=tuple(
            ExpectedSourceCategory(category=item, state=CATEGORY_EXPECTED)
            for item in SOURCE_CATEGORIES
        ),
        schema_version="inventory-boundary-v1",
    )


def _state():
    return initial_boundary_semantics_state(
        assessment=_assessment(),
        company=_company(),
        facilities=_facilities(),
        workspace_id="tw-ubn-12345675",
        reporting_period=_period(),
    )


def test_migration_dry_run_is_read_only_and_does_not_promote_legacy_facts(
    tmp_path: Path,
) -> None:
    workspace = CompanyWorkspace.for_company(
        root=tmp_path, taiwan_ubn="12345675"
    )
    legacy_path = workspace.write_draft(_legacy_boundary())
    before = legacy_path.read_bytes()

    preview = workspace.dry_run_boundary_semantics_migration(
        reporting_period_id=_period().reporting_period_id
    )

    assert preview["legacy_boundary_records"] == 1
    assert preview["official_registration_candidates"] == 2
    assert preview["canonical_sites_auto_confirmed"] == 0
    assert preview["legacy_facility_memberships_auto_migrated"] == 0
    assert preview["legacy_source_category_rows_preserved"] == 6
    assert preview["verified_official_authority_evidence"] == 0
    assert preview["moenv_boundaries_creatable"] == 0
    assert legacy_path.read_bytes() == before
    assert workspace.load_semantics_current(
        reporting_period_id=_period().reporting_period_id
    ) is None


def test_explicit_migration_is_idempotent_append_only_and_preserves_v1(
    tmp_path: Path,
) -> None:
    workspace = CompanyWorkspace.for_company(
        root=tmp_path, taiwan_ubn="12345675"
    )
    legacy_path = workspace.write_draft(_legacy_boundary())
    legacy_before = legacy_path.read_bytes()
    prepared = workspace.prepare_boundary_semantics_v2_migration(_state())

    assert prepared.boundaries == ()
    assert prepared.canonical_sites == ()
    assert prepared.operating_facts == ()
    assert len(prepared.legacy_source_category_snapshot) == 6
    assert len(prepared.customer_asserted_related_pending_review) == 1
    assertion = prepared.customer_asserted_related_pending_review[0]
    assert assertion["state"] == "customer_asserted_related_pending_review"
    assert assertion["verification_state"] == "customer_supplied_pending_review"

    migrated = workspace.migrate_boundary_semantics_v2(
        state=prepared,
        dry_run_reviewed=True,
    )
    rerun = workspace.migrate_boundary_semantics_v2(
        state=prepared,
        dry_run_reviewed=True,
    )

    assert rerun == migrated
    assert legacy_path.read_bytes() == legacy_before
    versions = list(
        (
            workspace.path
            / "periods"
            / _period().reporting_period_id
            / "boundary_semantics_v2"
            / "versions"
        ).glob("v*.json")
    )
    assert len(versions) == 1
    events = (
        workspace.path
        / "periods"
        / _period().reporting_period_id
        / "boundaries"
        / "events.jsonl"
    ).read_text(encoding="utf-8")
    assert "boundary_semantics_v2_migrated" in events


def test_migration_requires_explicit_dry_run_acknowledgement(
    tmp_path: Path,
) -> None:
    workspace = CompanyWorkspace.for_company(
        root=tmp_path, taiwan_ubn="12345675"
    )
    with pytest.raises(ValueError, match="explicitly reviewed dry-run"):
        workspace.migrate_boundary_semantics_v2(
            state=_state(),
            dry_run_reviewed=False,
        )


def test_atomic_pointer_failure_leaves_v1_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = CompanyWorkspace.for_company(
        root=tmp_path, taiwan_ubn="12345675"
    )
    legacy_path = workspace.write_draft(_legacy_boundary())
    original = workspace._atomic_json

    def fail_current_pointer(destination, payload, *, replace_existing=True):
        if destination.name == "migration_state.json":
            raise OSError("simulated pointer failure")
        return original(
            destination,
            payload,
            replace_existing=replace_existing,
        )

    monkeypatch.setattr(workspace, "_atomic_json", fail_current_pointer)
    with pytest.raises(OSError, match="pointer failure"):
        workspace.migrate_boundary_semantics_v2(
            state=workspace.prepare_boundary_semantics_v2_migration(_state()),
            dry_run_reviewed=True,
        )

    assert legacy_path.is_file()
    assert workspace.load_draft(
        reporting_period_id=_period().reporting_period_id,
        boundary_id="legacy_boundary",
    ) is not None
    assert workspace.load_semantics_current(
        reporting_period_id=_period().reporting_period_id
    ) is None


def test_rollback_selects_v1_without_deleting_v2_history(tmp_path: Path) -> None:
    workspace = CompanyWorkspace.for_company(
        root=tmp_path, taiwan_ubn="12345675"
    )
    workspace.write_draft(_legacy_boundary())
    migrated = workspace.migrate_boundary_semantics_v2(
        state=workspace.prepare_boundary_semantics_v2_migration(_state()),
        dry_run_reviewed=True,
    )
    version_path = (
        workspace.path
        / "periods"
        / _period().reporting_period_id
        / "boundary_semantics_v2"
        / "versions"
        / f"v{migrated.version:04d}.json"
    )
    assert version_path.is_file()

    workspace.rollback_boundary_semantics_to_v1(
        reporting_period_id=_period().reporting_period_id,
        reason="migration review required",
    )

    assert workspace.load_semantics_current(
        reporting_period_id=_period().reporting_period_id
    ) is None
    assert workspace.boundary_semantics_migration_status(
        reporting_period_id=_period().reporting_period_id
    ) == "v1_detected"
    assert version_path.is_file()
    assert workspace.load_draft(
        reporting_period_id=_period().reporting_period_id,
        boundary_id="legacy_boundary",
    ) is not None
