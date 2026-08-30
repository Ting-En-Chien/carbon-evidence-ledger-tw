"""Application-level company and facility master (setup layer only).

Not part of the GHG calculation domain. Official facts are suggestions;
the customer confirms reporting relevance.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

UBN_RE = re.compile(r"^\d{8}$")
_UBN_WEIGHTS = (1, 2, 1, 2, 1, 2, 4, 1)
# Source placeholder that happens to pass the checksum. Not a usable company id.
RESERVED_PLACEHOLDER_UBNS = frozenset({"00000000"})

ORIGIN_OFFICIAL = "OFFICIAL"
ORIGIN_SNAPSHOT = "SNAPSHOT"
ORIGIN_CUSTOMER = "CUSTOMER_ENTERED"
ORIGIN_CONFIRMED = "CUSTOMER_CONFIRMED"
ORIGIN_OVERRIDE = "CUSTOMER_OVERRIDE"

SOURCE_OFFICIAL_FACTORY = "OFFICIAL_FACTORY_OPEN_DATA"
SOURCE_UPLOAD = "UPLOADED_ACTIVITY_DATA"
SOURCE_PREVIOUS = "PREVIOUS_CONFIRMED"
SOURCE_MANUAL = "CUSTOMER_MANUAL_ENTRY"

MATCH_ALIGNED = "aligned"
MATCH_OFFICIAL_ONLY = "official_only"
MATCH_UPLOAD_ONLY = "upload_only"
MATCH_PREVIOUS_ONLY = "previous_only"
MATCH_NEEDS_REVIEW = "needs_review"

STATUS_ACTIVE = "ACTIVE"
STATUS_INACTIVE = "INACTIVE"
STATUS_NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"

IDENTITY_OPERATING = "operating"
IDENTITY_INACTIVE = "inactive"
IDENTITY_SOLD = "sold"
IDENTITY_NOT_OURS = "not_ours"
IDENTITY_INCORRECT = "incorrect"
IDENTITY_STATUSES = (
    IDENTITY_OPERATING,
    IDENTITY_INACTIVE,
    IDENTITY_SOLD,
    IDENTITY_NOT_OURS,
    IDENTITY_INCORRECT,
)

SITE_TYPES = ("factory", "office", "warehouse", "other")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_reserved_placeholder_ubn(ubn: str) -> bool:
    """True for explicit source placeholders such as 00000000."""
    return str(ubn or "") in RESERVED_PLACEHOLDER_UBNS


def validate_ubn(raw: str) -> tuple[str, str]:
    """Return (digits_or_raw, error_code). Never mutates non-8-digit input."""
    text = str(raw or "")
    if not UBN_RE.fullmatch(text):
        return text, "need_8"
    if not ubn_checksum_ok(text):
        return text, "invalid"
    if is_reserved_placeholder_ubn(text):
        return text, "reserved"
    return text, ""


def ubn_checksum_ok(digits: str) -> bool:
    if not UBN_RE.fullmatch(str(digits or "")):
        return False
    total = 0
    for index, weight in enumerate(_UBN_WEIGHTS):
        product = int(digits[index]) * weight
        total += product // 10 + product % 10
    if total % 10 == 0:
        return True
    return digits[6] == "7" and (total + 1) % 10 == 0


def normalize_site_name(name: str) -> str:
    return "".join(str(name or "").strip().casefold().split())


@dataclass
class SourceRecord:
    source_id: str
    authority: str
    access_mode: str
    retrieved_at: str
    dataset_or_api: str = ""
    raw_source_identifier: str = ""
    verified_access_mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SourceRecord:
        data = dict(raw or {})
        return cls(
            source_id=str(data.get("source_id") or ""),
            authority=str(data.get("authority") or ""),
            access_mode=str(data.get("access_mode") or ""),
            retrieved_at=str(data.get("retrieved_at") or ""),
            dataset_or_api=str(data.get("dataset_or_api") or ""),
            raw_source_identifier=str(data.get("raw_source_identifier") or ""),
            verified_access_mode=str(data.get("verified_access_mode") or ""),
        )


@dataclass
class CompanyMaster:
    company_id: str = ""
    unified_business_number: str = ""
    company_name: str = ""
    official_company_status: str = ""
    official_registered_address: str = ""
    confirmed_registered_address: str = ""
    address_overridden: bool = False
    official_paid_in_capital_twd: int | None = None
    confirmed_paid_in_capital_twd: int | None = None
    capital_overridden: bool = False
    listing_status: str = "UNKNOWN"
    listing_source: str = ""
    business_items: str = ""
    company_registration_type: str = ""
    lookup_status: str = ""
    lookup_error: str = ""
    last_official_lookup_at: str = ""
    customer_confirmed_at: str = ""
    official_stale: bool = False
    snapshot_data_date: str = ""
    data_origin: str = ""
    source_records: list[SourceRecord] = field(default_factory=list)

    @property
    def registered_address(self) -> str:
        if self.address_overridden and self.confirmed_registered_address:
            return self.confirmed_registered_address
        if self.confirmed_registered_address:
            return self.confirmed_registered_address
        return self.official_registered_address

    @property
    def paid_in_capital_twd(self) -> int | None:
        if self.capital_overridden:
            return self.confirmed_paid_in_capital_twd
        if self.confirmed_paid_in_capital_twd is not None:
            return self.confirmed_paid_in_capital_twd
        return self.official_paid_in_capital_twd

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_records"] = [item.to_dict() for item in self.source_records]
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> CompanyMaster:
        data = dict(raw or {})
        records = [
            SourceRecord.from_dict(item)
            for item in (data.get("source_records") or [])
            if isinstance(item, dict)
        ]
        capital_official = data.get("official_paid_in_capital_twd")
        capital_confirmed = data.get("confirmed_paid_in_capital_twd")
        return cls(
            company_id=str(data.get("company_id") or ""),
            unified_business_number=str(data.get("unified_business_number") or ""),
            company_name=str(data.get("company_name") or ""),
            official_company_status=str(data.get("official_company_status") or ""),
            official_registered_address=str(
                data.get("official_registered_address") or ""
            ),
            confirmed_registered_address=str(
                data.get("confirmed_registered_address") or ""
            ),
            address_overridden=bool(data.get("address_overridden")),
            official_paid_in_capital_twd=(
                int(capital_official) if capital_official not in (None, "") else None
            ),
            confirmed_paid_in_capital_twd=(
                int(capital_confirmed) if capital_confirmed not in (None, "") else None
            ),
            capital_overridden=bool(data.get("capital_overridden")),
            listing_status=str(data.get("listing_status") or "UNKNOWN"),
            listing_source=str(data.get("listing_source") or ""),
            business_items=str(data.get("business_items") or ""),
            company_registration_type=str(data.get("company_registration_type") or ""),
            lookup_status=str(data.get("lookup_status") or ""),
            lookup_error=str(data.get("lookup_error") or ""),
            last_official_lookup_at=str(data.get("last_official_lookup_at") or ""),
            customer_confirmed_at=str(data.get("customer_confirmed_at") or ""),
            official_stale=bool(data.get("official_stale")),
            snapshot_data_date=str(data.get("snapshot_data_date") or ""),
            data_origin=str(data.get("data_origin") or ""),
            source_records=records,
        )


@dataclass
class FacilityMasterRecord:
    facility_id: str
    display_name: str
    address: str = ""
    source_type: str = SOURCE_MANUAL
    official_factory_registration_number: str = ""
    industry_code: str = ""
    main_products: str = ""
    company_unified_business_number: str = ""
    status: str = STATUS_NEEDS_CONFIRMATION
    included_in_current_reporting_scope: bool = False
    discovered_from: tuple[str, ...] = ()
    match_state: str = MATCH_NEEDS_REVIEW
    customer_confirmed: bool = False
    last_confirmed_at: str = ""
    site_kind: str = "factory"
    inactive_reason: str = ""
    official_display_name: str = ""
    official_address: str = ""
    identity_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["discovered_from"] = list(self.discovered_from)
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> FacilityMasterRecord:
        data = dict(raw or {})
        discovered = tuple(
            str(item) for item in (data.get("discovered_from") or []) if item
        )
        return cls(
            facility_id=str(data.get("facility_id") or ""),
            display_name=str(data.get("display_name") or ""),
            address=str(data.get("address") or ""),
            source_type=str(data.get("source_type") or SOURCE_MANUAL),
            official_factory_registration_number=str(
                data.get("official_factory_registration_number") or ""
            ),
            industry_code=str(data.get("industry_code") or ""),
            main_products=str(data.get("main_products") or ""),
            company_unified_business_number=str(
                data.get("company_unified_business_number") or ""
            ),
            status=str(data.get("status") or STATUS_NEEDS_CONFIRMATION),
            included_in_current_reporting_scope=bool(
                data.get("included_in_current_reporting_scope")
            ),
            discovered_from=discovered,
            match_state=str(data.get("match_state") or MATCH_NEEDS_REVIEW),
            customer_confirmed=bool(data.get("customer_confirmed")),
            last_confirmed_at=str(data.get("last_confirmed_at") or ""),
            site_kind=str(data.get("site_kind") or "factory"),
            inactive_reason=str(data.get("inactive_reason") or ""),
            official_display_name=str(data.get("official_display_name") or ""),
            official_address=str(data.get("official_address") or ""),
            identity_status=str(data.get("identity_status") or ""),
        )


@dataclass
class OfficialFactoryHint:
    display_name: str
    address: str = ""
    registration_number: str = ""
    industry_code: str = ""
    main_products: str = ""
    unified_business_number: str = ""


@dataclass
class FacilityMaster:
    reporting_year: int | None = None
    records: list[FacilityMasterRecord] = field(default_factory=list)
    previous_year_records: list[FacilityMasterRecord] = field(default_factory=list)
    reuse_choice: str = ""
    last_reconciled_at: str = ""
    identity_confirmed: bool = False
    none_declared: bool = False
    coverage_choice: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reporting_year": self.reporting_year,
            "records": [item.to_dict() for item in self.records],
            "previous_year_records": [
                item.to_dict() for item in self.previous_year_records
            ],
            "reuse_choice": self.reuse_choice,
            "last_reconciled_at": self.last_reconciled_at,
            "identity_confirmed": self.identity_confirmed,
            "none_declared": self.none_declared,
            "coverage_choice": self.coverage_choice,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> FacilityMaster:
        data = dict(raw or {})
        year = data.get("reporting_year")
        return cls(
            reporting_year=int(year) if year not in (None, "") else None,
            records=[
                FacilityMasterRecord.from_dict(item)
                for item in (data.get("records") or [])
                if isinstance(item, dict)
            ],
            previous_year_records=[
                FacilityMasterRecord.from_dict(item)
                for item in (data.get("previous_year_records") or [])
                if isinstance(item, dict)
            ],
            reuse_choice=str(data.get("reuse_choice") or ""),
            last_reconciled_at=str(data.get("last_reconciled_at") or ""),
            identity_confirmed=bool(data.get("identity_confirmed")),
            none_declared=bool(data.get("none_declared")),
            coverage_choice=str(data.get("coverage_choice") or ""),
        )


def extract_upload_site_names(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for raw in values:
        name = str(raw or "").strip()
        if not name or name.upper() in {"UNKNOWN", "N/A", "NA", "—", "-"}:
            continue
        key = normalize_site_name(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def reconcile_facilities(
    *,
    official: Iterable[OfficialFactoryHint],
    upload_names: Iterable[str],
    previous: Iterable[FacilityMasterRecord] = (),
    ubn: str = "",
    existing: Iterable[FacilityMasterRecord] = (),
) -> list[FacilityMasterRecord]:
    """Merge official, upload, and previously confirmed sites. No legal conclusion."""
    by_key: dict[str, FacilityMasterRecord] = {}

    def _ensure(
        name: str,
        source: str,
        *,
        identity_key: str = "",
    ) -> FacilityMasterRecord:
        key = identity_key or normalize_site_name(name)
        record = by_key.get(key)
        if record is None:
            record = FacilityMasterRecord(
                facility_id=f"fac_{key or 'manual'}_{len(by_key)+1}",
                display_name=name,
                company_unified_business_number=ubn,
                source_type=source,
                discovered_from=(source,),
                status=STATUS_NEEDS_CONFIRMATION,
                included_in_current_reporting_scope=False,
            )
            by_key[key] = record
            return record
        if source not in record.discovered_from:
            record.discovered_from = (*record.discovered_from, source)
        return record

    for hint in official:
        registration = str(hint.registration_number or "").strip()
        official_key = (
            f"official:{registration}"
            if registration
            else "official:"
            + normalize_site_name(hint.display_name)
            + ":"
            + normalize_site_name(hint.address)
        )
        record = _ensure(
            hint.display_name,
            SOURCE_OFFICIAL_FACTORY,
            identity_key=official_key,
        )
        if hint.address and not record.address:
            record.address = hint.address
        if hint.registration_number:
            record.official_factory_registration_number = hint.registration_number
        if hint.industry_code:
            record.industry_code = hint.industry_code
        if hint.main_products:
            record.main_products = hint.main_products
    for name in extract_upload_site_names(upload_names):
        matches = [
            item
            for item in by_key.values()
            if normalize_site_name(item.display_name) == normalize_site_name(name)
        ]
        if len(matches) == 1:
            record = matches[0]
            if SOURCE_UPLOAD not in record.discovered_from:
                record.discovered_from = (*record.discovered_from, SOURCE_UPLOAD)
        else:
            _ensure(
                name,
                SOURCE_UPLOAD,
                identity_key=f"upload:{normalize_site_name(name)}",
            )
    for prior in previous:
        if prior.status == STATUS_INACTIVE:
            key = normalize_site_name(prior.display_name)
            if key not in by_key:
                kept = FacilityMasterRecord.from_dict(prior.to_dict())
                kept.discovered_from = tuple(
                    dict.fromkeys((*kept.discovered_from, SOURCE_PREVIOUS))
                )
                by_key[key] = kept
            continue
        record = _ensure(prior.display_name, SOURCE_PREVIOUS)
        if prior.address and not record.address:
            record.address = prior.address
        if prior.customer_confirmed:
            record.customer_confirmed = True
            record.last_confirmed_at = prior.last_confirmed_at
    for current in existing:
        registration = str(
            current.official_factory_registration_number or ""
        ).strip()
        key = (
            f"official:{registration}"
            if registration
            else normalize_site_name(current.display_name)
        )
        if key not in by_key:
            name_matches = [
                candidate_key
                for candidate_key, candidate in by_key.items()
                if normalize_site_name(candidate.display_name)
                == normalize_site_name(current.display_name)
            ]
            if len(name_matches) == 1:
                key = name_matches[0]
        if key in by_key:
            live = by_key[key]
            live.included_in_current_reporting_scope = (
                current.included_in_current_reporting_scope
            )
            live.customer_confirmed = current.customer_confirmed
            live.status = current.status
            live.inactive_reason = current.inactive_reason
            live.identity_status = current.identity_status or live.identity_status
            live.site_kind = current.site_kind or live.site_kind
            if current.address and not live.address:
                live.address = current.address
        elif current.source_type == SOURCE_MANUAL or current.customer_confirmed:
            by_key[key] = FacilityMasterRecord.from_dict(current.to_dict())

    records = list(by_key.values())
    for record in records:
        sources = set(record.discovered_from)
        has_official = SOURCE_OFFICIAL_FACTORY in sources
        has_upload = SOURCE_UPLOAD in sources
        if has_official and has_upload:
            record.match_state = MATCH_ALIGNED
        elif has_official:
            record.match_state = MATCH_OFFICIAL_ONLY
        elif has_upload:
            record.match_state = MATCH_UPLOAD_ONLY
        elif SOURCE_PREVIOUS in sources:
            record.match_state = MATCH_PREVIOUS_ONLY
        else:
            record.match_state = MATCH_NEEDS_REVIEW
    return records


def differences_only(
    records: Iterable[FacilityMasterRecord],
) -> list[FacilityMasterRecord]:
    return [
        item
        for item in records
        if item.match_state != MATCH_ALIGNED or not item.customer_confirmed
    ]


def all_sources_aligned(records: Iterable[FacilityMasterRecord]) -> bool:
    items = list(records)
    return bool(items) and all(item.match_state == MATCH_ALIGNED for item in items)


def confirm_all(
    records: list[FacilityMasterRecord],
    *,
    include_in_scope: bool,
    at: str | None = None,
) -> list[FacilityMasterRecord]:
    stamp = at or utc_now_iso()
    for record in records:
        if record.status == STATUS_INACTIVE:
            continue
        record.customer_confirmed = True
        record.last_confirmed_at = stamp
        record.status = STATUS_ACTIVE
        record.identity_status = IDENTITY_OPERATING
        if include_in_scope:
            record.included_in_current_reporting_scope = True
    return records


def confirm_all_operating(
    records: list[FacilityMasterRecord],
    *,
    at: str | None = None,
) -> list[FacilityMasterRecord]:
    """Confirm identity only. Never sets reporting-scope inclusion."""
    return confirm_all(records, include_in_scope=False, at=at)


def apply_identity_status(
    record: FacilityMasterRecord,
    status: str,
    *,
    display_name: str | None = None,
    address: str | None = None,
    at: str | None = None,
) -> FacilityMasterRecord:
    """Apply one customer identity fact. Does not set reporting-scope inclusion."""
    stamp = at or utc_now_iso()
    code = str(status or IDENTITY_OPERATING)
    record.customer_confirmed = True
    record.last_confirmed_at = stamp
    record.identity_status = code
    if code == IDENTITY_OPERATING:
        record.status = STATUS_ACTIVE
        record.inactive_reason = ""
        return record
    if code == IDENTITY_INCORRECT:
        if not record.official_display_name:
            record.official_display_name = record.display_name
        if not record.official_address:
            record.official_address = record.address
        if display_name is not None:
            record.display_name = str(display_name).strip() or record.display_name
        if address is not None:
            record.address = str(address).strip()
        record.status = STATUS_ACTIVE
        record.inactive_reason = ""
        return record
    reason = {
        IDENTITY_INACTIVE: "inactive",
        IDENTITY_SOLD: "sold",
        IDENTITY_NOT_OURS: "not_ours",
    }.get(code, "inactive")
    return deactivate_facility(record, reason=reason, at=stamp)


def commit_identity_drafts(
    records: list[FacilityMasterRecord],
    drafts: dict[str, dict[str, str]],
    *,
    at: str | None = None,
) -> list[FacilityMasterRecord]:
    """Apply explicit exception-mode choices. Widget defaults are not facts."""
    for record in records:
        payload = drafts.get(record.facility_id) or {}
        status = str(payload.get("status") or IDENTITY_OPERATING)
        name = payload.get("display_name")
        address = payload.get("address")
        apply_identity_status(
            record,
            status,
            display_name=name if status == IDENTITY_INCORRECT else None,
            address=address if status == IDENTITY_INCORRECT else None,
            at=at,
        )
    return records


def mark_exception_drafts_dirty(state: Any) -> None:
    """Widget drafts changed. Does not mutate committed facility facts."""
    state["facility_exception_draft_dirty"] = True


def clear_exception_drafts_dirty(state: Any) -> None:
    """Current exception drafts were explicitly committed."""
    state["facility_exception_draft_dirty"] = False


def exception_drafts_are_dirty(state: Any) -> bool:
    getter = getattr(state, "get", None)
    if callable(getter):
        return bool(getter("facility_exception_draft_dirty"))
    try:
        return bool(state["facility_exception_draft_dirty"])
    except Exception:  # noqa: BLE001 - missing key / AppTest proxy
        return False


def exception_navigation_blocked(
    *,
    exception_mode: bool,
    identity_confirmed: bool,
    drafts_dirty: bool,
) -> bool:
    """Continue is blocked while exception-mode drafts are uncommitted."""
    if not exception_mode:
        return False
    return bool(drafts_dirty) or not bool(identity_confirmed)


def confirmed_active_taiwan_sites(
    records: Iterable[FacilityMasterRecord],
) -> list[FacilityMasterRecord]:
    return [
        item
        for item in records
        if item.customer_confirmed and item.status != STATUS_INACTIVE
    ]


def taiwan_facility_existence(
    records: Iterable[FacilityMasterRecord],
    *,
    identity_confirmed: bool = False,
    none_declared: bool = False,
) -> str:
    """Company has Taiwan facilities? Independent of reporting-scope inclusion."""
    if confirmed_active_taiwan_sites(records) and identity_confirmed:
        return "YES"
    if identity_confirmed or none_declared:
        return "NO"
    return "NOT_SURE"


def deactivate_facility(
    record: FacilityMasterRecord,
    *,
    reason: str,
    at: str | None = None,
) -> FacilityMasterRecord:
    record.status = STATUS_INACTIVE
    record.inactive_reason = reason
    record.included_in_current_reporting_scope = False
    record.customer_confirmed = True
    record.last_confirmed_at = at or utc_now_iso()
    return record


def apply_reuse_previous(master: FacilityMaster) -> FacilityMaster:
    reused: list[FacilityMasterRecord] = []
    for prior in master.previous_year_records:
        item = FacilityMasterRecord.from_dict(prior.to_dict())
        if item.status != STATUS_INACTIVE:
            item.customer_confirmed = True
            item.status = STATUS_ACTIVE
        reused.append(item)
    master.records = reused
    master.reuse_choice = "reuse"
    master.last_reconciled_at = utc_now_iso()
    return master


def included_taiwan_sites(records: Iterable[FacilityMasterRecord]) -> list[str]:
    return [
        item.display_name
        for item in records
        if item.status != STATUS_INACTIVE and item.included_in_current_reporting_scope
    ]


STANDARD_AUTOFILL_FIELDS = (
    "company_name",
    "registered_address",
    "paid_in_capital_twd",
    "facility_names",
    "facility_addresses",
)


def setup_effort_for_standard_company(
    company: CompanyMaster,
    records: Iterable[FacilityMasterRecord],
) -> dict[str, Any]:
    """Measurable setup effort: customer should confirm, not retype master data."""
    typed: list[str] = ["unified_business_number"]
    confirmed = [
        "company" if company.customer_confirmed_at else "",
        "facilities_bulk"
        if records and all(item.customer_confirmed for item in records)
        else "",
    ]
    retyped = []
    if not company.company_name:
        retyped.append("company_name")
    if not company.official_registered_address:
        retyped.append("registered_address")
    if company.official_paid_in_capital_twd is None:
        retyped.append("paid_in_capital_twd")
    unnamed = [item for item in records if not item.display_name]
    if unnamed:
        retyped.append("facility_names")
    return {
        "typed_fields": typed,
        "confirmations": [item for item in confirmed if item],
        "forbidden_retyped": retyped,
        "facility_count": len(list(records)),
    }


def profile_updates_from_masters(
    company: CompanyMaster,
    facilities: FacilityMaster,
) -> dict[str, Any]:
    """Map confirmed master facts onto the existing CompanyProfile mapping."""
    existence = taiwan_facility_existence(
        facilities.records,
        identity_confirmed=facilities.identity_confirmed,
        none_declared=facilities.none_declared,
    )
    updates: dict[str, Any] = {
        "company_name": company.company_name,
        "unified_business_number": company.unified_business_number,
        "paid_in_capital_twd": company.paid_in_capital_twd,
        "listing_status": company.listing_status or "UNKNOWN",
        "industry": company.business_items,
    }
    if company.company_name:
        updates.setdefault("jurisdiction", "TW")
    if existence != "NOT_SURE":
        updates["has_taiwan_facilities"] = existence
        updates["number_of_taiwan_facilities"] = len(
            confirmed_active_taiwan_sites(facilities.records)
        )
    return updates
