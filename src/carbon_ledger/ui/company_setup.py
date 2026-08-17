"""Setup-layer helpers for zero-entry company / facility confirmation."""

from __future__ import annotations

from typing import Any, Iterable

from carbon_ledger.company_lookup import LookupResult
from carbon_ledger.company_master import (
    MATCH_ALIGNED,
    MATCH_OFFICIAL_ONLY,
    MATCH_PREVIOUS_ONLY,
    MATCH_UPLOAD_ONLY,
    SOURCE_OFFICIAL_FACTORY,
    SOURCE_PREVIOUS,
    SOURCE_UPLOAD,
    STATUS_INACTIVE,
    CompanyMaster,
    FacilityMaster,
    FacilityMasterRecord,
    OfficialFactoryHint,
    all_sources_aligned,
    profile_updates_from_masters,
    reconcile_facilities,
)
from carbon_ledger.ui.state import upload_site_names_from_session

LISTING_NEEDS_QUESTION = frozenset({"", "UNKNOWN"})
ENTITY_NEEDS_QUESTION = frozenset({"", "unresolved"})

GROUP_SELF_ONLY = "SELF_ONLY"
GROUP_WITH_SUBS = "WITH_SUBSIDIARIES"
GROUP_UNKNOWN = "UNKNOWN"


def listing_customer_label_key(listing: str) -> str:
    return {
        "TWSE": "setup.listing.TWSE",
        "TPEX": "setup.listing.TPEX",
        "PUBLIC": "setup.listing.PUBLIC",
    }.get(str(listing or ""), "")


def listing_needs_customer(company: CompanyMaster) -> bool:
    return str(company.listing_status or "UNKNOWN") in LISTING_NEEDS_QUESTION


def entity_needs_customer(mapping: dict[str, Any]) -> bool:
    return str(mapping.get("entity_type") or "unresolved") in ENTITY_NEEDS_QUESTION


def infer_entity_from_listing(listing: str) -> str:
    if listing == "TWSE":
        return "general_listed_company"
    if listing == "TPEX":
        return "general_otc_company"
    return ""


def show_capital_for_entity(entity_type: str) -> bool:
    return entity_type in {
        "general_listed_company",
        "general_otc_company",
        "securities_firm",
        "futures_commission_merchant",
    }


def show_fhc_for_entity(entity_type: str) -> bool:
    return entity_type in {
        "bank",
        "bills_finance_company",
        "securities_firm",
    }


def show_net_worth(*, entity_type: str, share_par: str) -> bool:
    """Ask net worth only when a verified rule actually substitutes it."""
    if not show_capital_for_entity(entity_type):
        return False
    return str(share_par or "") in {"no_par", "not_10"}


def apply_group_choice(choice: str) -> str:
    if choice == GROUP_SELF_ONLY:
        return "TRUE"
    if choice == GROUP_WITH_SUBS:
        return "TRUE"
    return "UNKNOWN"


def match_state_label_key(state: str) -> str:
    return {
        MATCH_ALIGNED: "setup.match.aligned",
        MATCH_OFFICIAL_ONLY: "setup.match.official_only",
        MATCH_UPLOAD_ONLY: "setup.match.upload_only",
        MATCH_PREVIOUS_ONLY: "setup.match.previous_only",
    }.get(state, "setup.match.needs_review")


def source_flags(record: FacilityMasterRecord) -> dict[str, bool]:
    found = set(record.discovered_from)
    return {
        "official": SOURCE_OFFICIAL_FACTORY in found,
        "upload": SOURCE_UPLOAD in found,
        "previous": SOURCE_PREVIOUS in found,
    }


def session_update_from_lookup(result: LookupResult) -> dict[str, Any]:
    """Split company identity from factory discovery.

    A valid UBN may miss the company snapshot and still have official
    factory candidates. Factory names are never copied onto CompanyMaster.
    """
    found = bool(result.ok and result.company.company_name)
    return {
        "company_found": found,
        "not_found": not found,
        "manual": not found,
        "company": result.company,
        "factories": list(result.factories),
    }


def rebuild_facility_master(
    *,
    session_state: Any,
    company: CompanyMaster,
    official: Iterable[OfficialFactoryHint],
    existing: FacilityMaster,
    reporting_year: int | None,
) -> FacilityMaster:
    upload_names = upload_site_names_from_session(session_state)
    records = reconcile_facilities(
        official=official,
        upload_names=upload_names,
        previous=existing.previous_year_records,
        ubn=company.unified_business_number,
        existing=existing.records,
    )
    existing.records = records
    existing.reporting_year = reporting_year
    return existing


def merge_profile_from_setup(
    saved: dict[str, Any],
    company: CompanyMaster,
    facilities: FacilityMaster,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = {**saved, **profile_updates_from_masters(company, facilities)}
    listing = company.listing_status or merged.get("listing_status") or "UNKNOWN"
    inferred = infer_entity_from_listing(listing)
    current_entity = str(merged.get("entity_type") or "unresolved")
    if inferred and current_entity in ENTITY_NEEDS_QUESTION:
        merged["entity_type"] = inferred
    merged["listing_status"] = listing
    if extra:
        merged.update(extra)
    return merged


def facilities_need_difference_review(
    records: Iterable[FacilityMasterRecord],
) -> bool:
    items = list(records)
    if not items:
        return False
    if all_sources_aligned(items) and all(item.customer_confirmed for item in items):
        return False
    return not all_sources_aligned(items)


def official_factory_records(
    records: Iterable[FacilityMasterRecord],
) -> list[FacilityMasterRecord]:
    return [
        item
        for item in records
        if SOURCE_OFFICIAL_FACTORY in item.discovered_from
        and item.status != STATUS_INACTIVE
    ]


def source_discrepancy_records(
    records: Iterable[FacilityMasterRecord],
) -> list[FacilityMasterRecord]:
    """Meaningful source disagreements only — not aligned matches.

    Official-only rows are normal when no activity file exists.
    """
    items = list(records)
    has_official = any(
        SOURCE_OFFICIAL_FACTORY in item.discovered_from for item in items
    )
    has_upload = any(SOURCE_UPLOAD in item.discovered_from for item in items)
    if not (has_official and has_upload):
        return []
    return [
        item
        for item in items
        if item.match_state in {MATCH_OFFICIAL_ONLY, MATCH_UPLOAD_ONLY}
    ]


def has_real_uploaded_activity(session_state: Any) -> bool:
    """True only when a real intake file produced site names.

    Stub overlay names are not treated as an uploaded dataset.
    """
    from carbon_ledger.ui.state import get_intake_result

    intake = get_intake_result(session_state)
    accepted = getattr(intake, "accepted_activities", None) if intake else None
    if accepted is None:
        return False
    try:
        if getattr(accepted, "empty", True) or "site_id" not in accepted.columns:
            return False
        return bool(
            [
                name
                for name in accepted["site_id"].tolist()
                if str(name or "").strip()
            ]
        )
    except Exception:  # noqa: BLE001
        return False


def factory_source_as_of(repo_root: Any | None = None) -> str:
    from pathlib import Path

    from carbon_ledger.factory_snapshot import (
        default_factory_metadata,
        load_snapshot_metadata,
    )

    root = Path(repo_root) if repo_root else None
    meta = load_snapshot_metadata(default_factory_metadata(root))
    return str(meta.get("source_data_date") or "")[:10]
