"""Stage 4.2H-A inventory-boundary models and safe local-confirmation rules."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

from carbon_ledger.company_master import (
    SOURCE_OFFICIAL_FACTORY,
    CompanyMaster,
    FacilityMasterRecord,
)
from carbon_ledger.legal_entity import (
    CONFIRMATION_DRAFT,
    CONFIRMATION_LOCAL,
    CONFIRMATION_PENDING,
    CONFIRMATION_STATES,
    LOCAL_CONFIRMATION_METHOD,
    LegalEntity,
)

PURPOSE_MOENV_FACILITY = "moenv_facility"
PURPOSE_IFRS_REPORTING_ENTITY = "ifrs_reporting_entity"
PURPOSE_LISTED_CONSOLIDATED = "listed_consolidated"
BOUNDARY_PURPOSES = frozenset(
    {
        PURPOSE_MOENV_FACILITY,
        PURPOSE_IFRS_REPORTING_ENTITY,
        PURPOSE_LISTED_CONSOLIDATED,
    }
)

PURPOSE_OUTCOME_CURRENT = "current"
PURPOSE_OUTCOME_FUTURE = "future_preparation_only"
PURPOSE_OUTCOME_UNRESOLVED = "unresolved"
PURPOSE_OUTCOMES = frozenset(
    {
        PURPOSE_OUTCOME_CURRENT,
        PURPOSE_OUTCOME_FUTURE,
        PURPOSE_OUTCOME_UNRESOLVED,
    }
)

IFRS_ADOPTION_RULE_IDS = frozenset(
    {
        "tw_order_51756_phase1_ge_10bn",
        "tw_order_51756_phase2_5_to_10bn",
        "tw_order_51756_phase3_lt_5bn",
        "tw_fi_fhc_apply_fy2026",
        "tw_fi_bank_listed_or_fhc_sub_fy2026",
        "tw_fi_bank_nonlisted_non_fhc_sub_fy2027",
        "tw_fi_bills_listed_or_fhc_sub_fy2026",
        "tw_sf_order_56095_phase1_ge_10bn",
        "tw_sf_order_56095_phase2_5_to_10bn",
        "tw_sf_order_56095_phase3_lt_5bn",
        "tw_sf_nonlisted_not_in_56095",
        "tw_fcm_order_56096_phase1_ge_10bn",
        "tw_fcm_order_56096_phase2_5_to_10bn",
        "tw_fcm_order_56096_phase3_lt_5bn",
    }
)
CONSOLIDATED_ASSURANCE_RULE_IDS = frozenset(
    {
        "tw_order_51756_scope12_consolidated_assurance",
        "tw_sf_order_56095_scope12_assurance",
    }
)

RECONCILIATION_MATCHED = "matched_to_confirmed_site"
RECONCILIATION_DUPLICATE = "duplicate_or_additional_record_for_same_site"
RECONCILIATION_OTHER_COMPANY = "belongs_to_another_company"
RECONCILIATION_NO_LONGER_VALID = "no_longer_valid"
RECONCILIATION_UNRESOLVED = "unresolved"
RECONCILIATION_STATES = frozenset(
    {
        RECONCILIATION_MATCHED,
        RECONCILIATION_DUPLICATE,
        RECONCILIATION_OTHER_COMPANY,
        RECONCILIATION_NO_LONGER_VALID,
        RECONCILIATION_UNRESOLVED,
    }
)

EVIDENCE_CUSTOMER_PENDING = "customer_supplied_pending_review"
EVIDENCE_VERIFIED_OFFICIAL = "verified_official_source"
EVIDENCE_CONFIRMED_COMPANY_DOCUMENT = "confirmed_company_document"
EVIDENCE_REJECTED = "rejected"
EVIDENCE_SUPERSEDED = "superseded"
AUTHORITY_EVIDENCE_STATES = frozenset(
    {
        EVIDENCE_CUSTOMER_PENDING,
        EVIDENCE_VERIFIED_OFFICIAL,
        EVIDENCE_REJECTED,
        EVIDENCE_SUPERSEDED,
    }
)

CONSOLIDATION_STANDALONE = "standalone"
CONSOLIDATION_CONSOLIDATED = "consolidated"
CONSOLIDATION_UNRESOLVED = "unresolved"
CONSOLIDATION_BASES = frozenset(
    {
        CONSOLIDATION_STANDALONE,
        CONSOLIDATION_CONSOLIDATED,
        CONSOLIDATION_UNRESOLVED,
    }
)

REQUIREMENT_ENGINE = "engine_applicable"
REQUIREMENT_FUTURE = "engine_future_requirement"
REQUIREMENT_NEEDS_FACT = "needs_customer_fact"
REQUIREMENT_VOLUNTARY = "customer_requested_voluntary"
REQUIREMENT_STATUSES = frozenset(
    {
        REQUIREMENT_ENGINE,
        REQUIREMENT_FUTURE,
        REQUIREMENT_NEEDS_FACT,
        REQUIREMENT_VOLUNTARY,
    }
)

MEMBERSHIP_PENDING = "pending_confirmation"
MEMBERSHIP_INCLUDED = "included"
MEMBERSHIP_EXCLUDED = "excluded"
MEMBERSHIP_NOT_PERIOD = "not_applicable_to_period"
MEMBERSHIP_UNCERTAIN = "uncertain"
MEMBERSHIP_STATES = frozenset(
    {
        MEMBERSHIP_PENDING,
        MEMBERSHIP_INCLUDED,
        MEMBERSHIP_EXCLUDED,
        MEMBERSHIP_NOT_PERIOD,
        MEMBERSHIP_UNCERTAIN,
    }
)

CATEGORY_PENDING = "pending"
CATEGORY_EXPECTED = "expected"
CATEGORY_NOT_EXPECTED = "not_expected"
CATEGORY_UNCERTAIN = "uncertain"
CATEGORY_STATES = frozenset(
    {
        CATEGORY_PENDING,
        CATEGORY_EXPECTED,
        CATEGORY_NOT_EXPECTED,
        CATEGORY_UNCERTAIN,
    }
)

OPERATING_FULL_PERIOD = "full_period"
OPERATING_STARTED_DURING_PERIOD = "started_during_period"
OPERATING_STOPPED_DURING_PERIOD = "stopped_during_period"
OPERATING_TRANSFERRED_DURING_PERIOD = "transferred_during_period"
OPERATING_NO_OPERATION_FULL_PERIOD = "no_operation_full_period"
OPERATING_NOT_COMPANY = "not_company"
OPERATING_UNCERTAIN = "uncertain"
OPERATING_STATUSES = frozenset(
    {
        "",
        OPERATING_FULL_PERIOD,
        OPERATING_STARTED_DURING_PERIOD,
        OPERATING_STOPPED_DURING_PERIOD,
        OPERATING_TRANSFERRED_DURING_PERIOD,
        OPERATING_NO_OPERATION_FULL_PERIOD,
        OPERATING_NOT_COMPANY,
        OPERATING_UNCERTAIN,
    }
)
PARTIAL_PERIOD_OPERATING_STATUSES = frozenset(
    {
        OPERATING_STARTED_DURING_PERIOD,
        OPERATING_STOPPED_DURING_PERIOD,
        OPERATING_TRANSFERRED_DURING_PERIOD,
    }
)

SOURCE_CATEGORIES = (
    "stationary_combustion",
    "mobile_combustion",
    "process_emissions",
    "fugitive_emissions",
    "purchased_electricity",
    "purchased_steam",
)

ACTION_EFFECTS = frozenset(
    {
        "applicability",
        "boundary_local_confirmation",
        "calculation_completeness",
        "final_reporting",
        "verification_readiness",
    }
)

EXISTING_SCOPE_DRAFT_ZH = "待確認的既有範圍"
EXISTING_SCOPE_DRAFT_EN = "Existing scope to review"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_id(prefix: str, *parts: str) -> str:
    blob = "\x1f".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def confirmed_reporting_period_id(
    reporting_year: int,
    period_start: str,
    period_end: str,
) -> str:
    """Return the canonical identity of one explicitly confirmed period."""
    return _stable_id(
        "period_confirmed",
        str(reporting_year),
        period_start,
        period_end,
    )


def _annual_period_is_valid(start: date, end: date) -> bool:
    """Accept a 52- or 53-week annual/fiscal reporting period."""
    inclusive_days = (end - start).days + 1
    return 364 <= inclusive_days <= 371


class ConfirmerDetailsError(ValueError):
    """Identify every missing required confirmer field."""

    def __init__(self, missing_fields: Iterable[str]) -> None:
        self.missing_fields = tuple(missing_fields)
        super().__init__(
            "responsible contact name and job title are required: "
            + ", ".join(self.missing_fields)
        )


def normalize_confirmer_details(name: str, job_title: str) -> tuple[str, str]:
    """Return immutable-record values after one shared required-field check."""
    normalized_name = str(name or "").strip()
    normalized_title = str(job_title or "").strip()
    missing_fields = tuple(
        field
        for field, value in (
            ("responsible_contact_name", normalized_name),
            ("responsible_job_title", normalized_title),
        )
        if not value
    )
    if missing_fields:
        raise ConfirmerDetailsError(missing_fields)
    return normalized_name, normalized_title


@dataclass(frozen=True)
class ReportingPeriod:
    """A suggested year is not confirmed until all explicit fields are supplied."""

    reporting_period_id: str
    reporting_year_suggested: int | None = None
    reporting_year_confirmed: int | None = None
    period_start_confirmed: str = ""
    period_end_confirmed: str = ""
    confirmation_state: str = CONFIRMATION_PENDING

    def __post_init__(self) -> None:
        if self.confirmation_state not in CONFIRMATION_STATES:
            raise ValueError("invalid reporting-period confirmation_state")
        if self.confirmation_state == CONFIRMATION_LOCAL:
            self.require_explicit_confirmation()
            canonical = confirmed_reporting_period_id(
                int(self.reporting_year_confirmed or 0),
                self.period_start_confirmed,
                self.period_end_confirmed,
            )
            if self.reporting_period_id != canonical:
                raise ValueError(
                    "confirmed reporting period must use its canonical identity"
                )

    @property
    def is_explicitly_confirmed(self) -> bool:
        if self.confirmation_state != CONFIRMATION_LOCAL:
            return False
        if self.reporting_year_confirmed is None:
            return False
        try:
            start = date.fromisoformat(self.period_start_confirmed)
            end = date.fromisoformat(self.period_end_confirmed)
        except ValueError:
            return False
        return (
            start <= end
            and start.year <= self.reporting_year_confirmed <= end.year
            and _annual_period_is_valid(start, end)
        )

    def require_explicit_confirmation(self) -> None:
        if not self.is_explicitly_confirmed:
            raise ValueError(
                "reporting year, start date, and end date require a valid annual "
                "or fiscal-period confirmation"
            )

    @classmethod
    def confirmed(
        cls,
        *,
        reporting_year_suggested: int | None,
        reporting_year_confirmed: int,
        period_start_confirmed: str,
        period_end_confirmed: str,
    ) -> ReportingPeriod:
        period_id = confirmed_reporting_period_id(
            reporting_year_confirmed,
            period_start_confirmed,
            period_end_confirmed,
        )
        return cls(
            reporting_period_id=period_id,
            reporting_year_suggested=reporting_year_suggested,
            reporting_year_confirmed=reporting_year_confirmed,
            period_start_confirmed=period_start_confirmed,
            period_end_confirmed=period_end_confirmed,
            confirmation_state=CONFIRMATION_LOCAL,
        )


@dataclass(frozen=True)
class PurposeReview:
    """One assessment-derived reporting-purpose review for one exact period."""

    purpose_review_id: str
    purpose: str
    reporting_period_id: str
    obligation_id: str
    assessment_status: str
    outcome: str
    assessment_timestamp: str = ""
    effective_year: int | None = None
    applied_rule_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    official_authority: str = ""
    official_document: str = ""
    schema_version: str = "purpose-review-v1"

    def __post_init__(self) -> None:
        if self.purpose not in BOUNDARY_PURPOSES:
            raise ValueError("unsupported purpose review")
        if self.outcome not in PURPOSE_OUTCOMES:
            raise ValueError("invalid purpose-review outcome")
        if not self.purpose_review_id.strip() or not self.reporting_period_id.strip():
            raise ValueError("purpose review requires stable identities")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PurposeReview:
        data = dict(raw or {})
        return cls(
            purpose_review_id=str(data.get("purpose_review_id") or ""),
            purpose=str(data.get("purpose") or ""),
            reporting_period_id=str(data.get("reporting_period_id") or ""),
            obligation_id=str(data.get("obligation_id") or ""),
            assessment_status=str(data.get("assessment_status") or ""),
            outcome=str(data.get("outcome") or PURPOSE_OUTCOME_UNRESOLVED),
            assessment_timestamp=str(data.get("assessment_timestamp") or ""),
            effective_year=(
                int(data["effective_year"])
                if data.get("effective_year") not in (None, "")
                else None
            ),
            applied_rule_ids=tuple(data.get("applied_rule_ids") or ()),
            source_ids=tuple(data.get("source_ids") or ()),
            missing_information=tuple(data.get("missing_information") or ()),
            official_authority=str(data.get("official_authority") or ""),
            official_document=str(data.get("official_document") or ""),
            schema_version=str(data.get("schema_version") or "purpose-review-v1"),
        )


@dataclass(frozen=True)
class OfficialRegistrationCandidate:
    """An official row retained as evidence, never as a confirmed company site."""

    candidate_id: str
    registration_identity: str
    official_source: str
    source_record_id: str
    display_name: str
    address: str
    company_ubn: str = ""
    provenance_reference: str = ""
    schema_version: str = "official-registration-candidate-v1"

    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.registration_identity.strip():
            raise ValueError("official registration candidate requires an identity")
        if not self.official_source.strip():
            raise ValueError("official registration candidate requires a source")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> OfficialRegistrationCandidate:
        return cls(**dict(raw or {}))


@dataclass(frozen=True)
class CanonicalSite:
    """A company-confirmed physical factory or operating location."""

    site_id: str
    display_name: str
    address: str
    company_entity_id: str
    locally_confirmed_at: str = ""
    responsible_contact_name: str = ""
    responsible_job_title: str = ""
    schema_version: str = "canonical-site-v1"

    def __post_init__(self) -> None:
        if not self.site_id.strip() or not self.display_name.strip():
            raise ValueError("canonical site requires an identity and name")
        if not self.company_entity_id.strip():
            raise ValueError("canonical site requires a company entity")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> CanonicalSite:
        return cls(**dict(raw or {}))


@dataclass(frozen=True)
class RegistrationReconciliation:
    """A period-local answer linking an official row to a canonical site."""

    reconciliation_id: str
    candidate_id: str
    reporting_period_id: str
    state: str = RECONCILIATION_UNRESOLVED
    canonical_site_id: str = ""
    primary_candidate_id: str = ""
    basis: str = ""
    evidence_reference: str = ""
    locally_confirmed_at: str = ""
    schema_version: str = "registration-reconciliation-v1"

    def __post_init__(self) -> None:
        if self.state not in RECONCILIATION_STATES:
            raise ValueError("invalid registration reconciliation state")
        if not self.reconciliation_id.strip() or not self.candidate_id.strip():
            raise ValueError("registration reconciliation requires identities")
        if self.state in {RECONCILIATION_MATCHED, RECONCILIATION_DUPLICATE}:
            if not self.canonical_site_id.strip():
                raise ValueError("matched registration requires a canonical site")
        elif self.canonical_site_id.strip():
            raise ValueError("unmatched registration cannot identify a canonical site")
        if self.state == RECONCILIATION_DUPLICATE:
            if not self.primary_candidate_id.strip():
                raise ValueError("duplicate registration requires a primary record")
            if self.primary_candidate_id == self.candidate_id:
                raise ValueError("a registration cannot duplicate itself")
        if self.state == RECONCILIATION_NO_LONGER_VALID and not self.basis.strip():
            raise ValueError("invalid registration requires a supporting basis")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> RegistrationReconciliation:
        return cls(**dict(raw or {}))


@dataclass(frozen=True)
class PeriodOperatingFact:
    """Operating timing for one canonical site in one reporting period."""

    operating_fact_id: str
    canonical_site_id: str
    reporting_period_id: str
    status: str = OPERATING_UNCERTAIN
    effective_date: str = ""
    supporting_basis: str = ""
    locally_confirmed_at: str = ""
    schema_version: str = "period-operating-fact-v1"

    def __post_init__(self) -> None:
        allowed = OPERATING_STATUSES - {"", OPERATING_NOT_COMPANY}
        if self.status not in allowed:
            raise ValueError("invalid canonical-site operating status")
        if not self.operating_fact_id.strip() or not self.canonical_site_id.strip():
            raise ValueError("operating fact requires stable identities")
        if self.status in PARTIAL_PERIOD_OPERATING_STATUSES:
            if not self.effective_date.strip() or not self.supporting_basis.strip():
                raise ValueError(
                    "partial-period operating fact requires date and evidence"
                )
            date.fromisoformat(self.effective_date)
        if (
            self.status == OPERATING_NO_OPERATION_FULL_PERIOD
            and not self.supporting_basis.strip()
        ):
            raise ValueError("non-operating fact requires a supporting basis")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PeriodOperatingFact:
        return cls(**dict(raw or {}))


@dataclass(frozen=True)
class ProfessionalReviewMetadata:
    reviewer_name: str = ""
    reviewer_role: str = ""
    reviewed_at: str = ""
    review_note: str = ""


@dataclass(frozen=True)
class CompetentAuthorityBoundaryEvidence:
    """Typed official evidence; professional interpretation is metadata only."""

    evidence_id: str
    purpose: str
    authority: str
    source_id: str
    document_type: str
    document_or_registration_identifier: str
    described_reporting_or_operating_unit: str
    effective_start: str
    effective_end: str
    provenance_reference: str
    verification_state: str = EVIDENCE_CUSTOMER_PENDING
    linked_registration_candidate_ids: tuple[str, ...] = ()
    linked_canonical_site_ids: tuple[str, ...] = ()
    supporting_note: str = ""
    professional_review_metadata: ProfessionalReviewMetadata | None = None
    schema_version: str = "competent-authority-boundary-evidence-v1"

    def __post_init__(self) -> None:
        if self.purpose != PURPOSE_MOENV_FACILITY:
            raise ValueError("competent-authority evidence is MOENV-specific")
        if self.verification_state not in AUTHORITY_EVIDENCE_STATES:
            raise ValueError("invalid authority-evidence verification state")
        if not self.evidence_id.strip():
            raise ValueError("authority evidence requires an identity")
        if self.verification_state == EVIDENCE_VERIFIED_OFFICIAL:
            required = (
                self.authority,
                self.source_id,
                self.document_type,
                self.document_or_registration_identifier,
                self.described_reporting_or_operating_unit,
                self.effective_start,
                self.effective_end,
                self.provenance_reference,
            )
            if not all(str(item or "").strip() for item in required):
                raise ValueError(
                    "verified official evidence requires complete authority provenance"
                )
            start = date.fromisoformat(self.effective_start)
            end = date.fromisoformat(self.effective_end)
            if start > end:
                raise ValueError("authority evidence effective period is invalid")
            if not self.linked_canonical_site_ids:
                raise ValueError(
                    "verified official evidence requires linked canonical sites"
                )

    @property
    def can_define_moenv_boundary(self) -> bool:
        return self.verification_state == EVIDENCE_VERIFIED_OFFICIAL

    def covers(self, period: ReportingPeriod) -> bool:
        if not self.can_define_moenv_boundary or not period.is_explicitly_confirmed:
            return False
        return (
            date.fromisoformat(self.effective_start)
            <= date.fromisoformat(period.period_end_confirmed)
            and date.fromisoformat(self.effective_end)
            >= date.fromisoformat(period.period_start_confirmed)
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, Any]
    ) -> CompetentAuthorityBoundaryEvidence:
        data = dict(raw or {})
        review = data.get("professional_review_metadata")
        return cls(
            **{
                **data,
                "linked_registration_candidate_ids": tuple(
                    data.get("linked_registration_candidate_ids") or ()
                ),
                "linked_canonical_site_ids": tuple(
                    data.get("linked_canonical_site_ids") or ()
                ),
                "professional_review_metadata": (
                    ProfessionalReviewMetadata(**review)
                    if isinstance(review, dict)
                    else None
                ),
            }
        )


@dataclass(frozen=True)
class FinancialStatementReportingEntityEvidence:
    evidence_id: str
    reporting_period_id: str
    financial_statement_title: str
    financial_statement_type: str
    issuer_or_source: str
    reporting_entity_identifier: str
    reporting_entity_name: str
    consolidation_basis: str = CONSOLIDATION_UNRESOLVED
    included_legal_entity_ids: tuple[str, ...] = ()
    provenance_reference: str = ""
    verification_state: str = EVIDENCE_CUSTOMER_PENDING
    schema_version: str = "financial-statement-reporting-entity-evidence-v1"

    def __post_init__(self) -> None:
        if self.consolidation_basis not in CONSOLIDATION_BASES:
            raise ValueError("invalid financial-statement consolidation basis")
        if self.verification_state not in {
            *AUTHORITY_EVIDENCE_STATES,
            EVIDENCE_CONFIRMED_COMPANY_DOCUMENT,
        }:
            raise ValueError("invalid reporting-entity evidence state")
        if not self.evidence_id.strip() or not self.reporting_period_id.strip():
            raise ValueError("reporting-entity evidence requires stable identities")

    @property
    def confirms_reporting_entity(self) -> bool:
        return (
            self.verification_state
            in {
                EVIDENCE_VERIFIED_OFFICIAL,
                EVIDENCE_CONFIRMED_COMPANY_DOCUMENT,
            }
            and self.consolidation_basis
            in {CONSOLIDATION_STANDALONE, CONSOLIDATION_CONSOLIDATED}
            and bool(self.reporting_entity_identifier.strip())
            and bool(self.reporting_entity_name.strip())
            and bool(self.provenance_reference.strip())
            and bool(self.included_legal_entity_ids)
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls, raw: Mapping[str, Any]
    ) -> FinancialStatementReportingEntityEvidence:
        data = dict(raw or {})
        return cls(
            **{
                **data,
                "included_legal_entity_ids": tuple(
                    data.get("included_legal_entity_ids") or ()
                ),
            }
        )


@dataclass(frozen=True)
class LegalEntityMembership:
    entity_id: str
    state: str = MEMBERSHIP_PENDING
    effective_start: str = ""
    effective_end: str = ""
    reason: str = ""
    evidence_source: str = ""
    locally_confirmed_at: str = ""
    responsible_contact_name: str = ""
    responsible_job_title: str = ""
    confirmation_method: str = LOCAL_CONFIRMATION_METHOD
    reporting_purpose: str = ""

    def __post_init__(self) -> None:
        _validate_membership(self.state, self.confirmation_method)


@dataclass(frozen=True)
class FacilityMembership:
    facility_id: str
    state: str = MEMBERSHIP_PENDING
    effective_start: str = ""
    effective_end: str = ""
    reason: str = ""
    evidence_source: str = ""
    locally_confirmed_at: str = ""
    responsible_contact_name: str = ""
    responsible_job_title: str = ""
    confirmation_method: str = LOCAL_CONFIRMATION_METHOD
    reporting_purpose: str = ""
    period_operating_status: str = ""
    operating_status_effective_date: str = ""
    operating_status_basis: str = ""

    def __post_init__(self) -> None:
        _validate_membership(self.state, self.confirmation_method)
        if self.period_operating_status not in OPERATING_STATUSES:
            raise ValueError("invalid period_operating_status")
        if self.period_operating_status in PARTIAL_PERIOD_OPERATING_STATUSES:
            if not self.operating_status_effective_date.strip():
                raise ValueError("partial-period operating status requires a date")
            try:
                date.fromisoformat(self.operating_status_effective_date)
            except ValueError as error:
                raise ValueError(
                    "partial-period operating status requires an ISO date"
                ) from error
            if not self.operating_status_basis.strip():
                raise ValueError(
                    "partial-period operating status requires a supporting basis"
                )
        if self.period_operating_status in {
            OPERATING_NO_OPERATION_FULL_PERIOD,
            OPERATING_NOT_COMPANY,
        } and not self.operating_status_basis.strip():
            raise ValueError("non-operating status requires a supporting basis")

    @property
    def canonical_site_id(self) -> str:
        """V2 semantic name; facility_id remains the legacy wire key."""
        return self.facility_id


def _validate_membership(state: str, method: str) -> None:
    if state not in MEMBERSHIP_STATES:
        raise ValueError("invalid membership state")
    if method != LOCAL_CONFIRMATION_METHOD:
        raise ValueError("unsupported confirmation_method")


def _membership_has_exclusion_support(
    membership: LegalEntityMembership | FacilityMembership,
) -> bool:
    if membership.state not in {MEMBERSHIP_EXCLUDED, MEMBERSHIP_NOT_PERIOD}:
        return True
    return bool(membership.reason.strip() and membership.evidence_source.strip())


@dataclass(frozen=True)
class RegistrationLink:
    """Preserve one government registration as a distinct candidate."""

    registration_link_id: str
    registration_identity: str
    facility_id: str
    official_source: str
    location: str
    company_ubn: str = ""
    combined_with: tuple[str, ...] = ()
    combination_basis: str = ""
    combination_evidence: str = ""
    confirmation_history: tuple[dict[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.registration_identity.strip():
            raise ValueError("registration_identity is required")
        targets = tuple(str(item).strip() for item in self.combined_with)
        if len(targets) != len(set(targets)):
            raise ValueError("registration combination targets must be unique")
        if (
            self.registration_link_id in targets
            or self.registration_identity in targets
        ):
            raise ValueError("a registration cannot be combined with itself")
        if self.combined_with and not (
            self.combination_basis.strip() and self.combination_evidence.strip()
        ):
            raise ValueError(
                "combining registrations requires a recorded basis and evidence"
            )


def validate_registration_combinations(
    links: Iterable[RegistrationLink],
) -> None:
    """Validate targets and cycles across the complete registration candidate set."""
    candidates = tuple(links)
    by_id = {item.registration_link_id: item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("registration_link_id values must be unique")
    graph: dict[str, tuple[str, ...]] = {}
    for item in candidates:
        targets = tuple(item.combined_with)
        missing = [target for target in targets if target not in by_id]
        if missing:
            raise ValueError("registration combination target does not exist")
        graph[item.registration_link_id] = targets

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("circular registration combinations are not permitted")
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, ()):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for registration_link_id in graph:
        visit(registration_link_id)


@dataclass(frozen=True)
class ExpectedSourceCategory:
    category: str
    state: str = CATEGORY_PENDING
    reason: str = ""

    def __post_init__(self) -> None:
        if self.category not in SOURCE_CATEGORIES:
            raise ValueError("invalid expected-source category")
        if self.state not in CATEGORY_STATES:
            raise ValueError("invalid expected-source state")
        if self.state == CATEGORY_NOT_EXPECTED and not self.reason.strip():
            raise ValueError("not_expected source categories require a company reason")


@dataclass(frozen=True)
class ActionItem:
    """Structured action data only; Stage 4.2H-B renders customer cards."""

    action_id: str
    missing_or_uncertain: str
    affected_entity_ids: tuple[str, ...]
    affected_facility_ids: tuple[str, ...]
    reporting_period_id: str
    why_needed: str
    affected_outcome: str
    suggested_company_role: str
    where_to_find: str
    required_action: str
    current_status: str
    effects: frozenset[str]
    responsible_contact_name: str = ""
    responsible_job_title: str = ""
    due_date: str = ""
    source_or_evidence_link: str = ""

    def __post_init__(self) -> None:
        required = (
            self.action_id,
            self.missing_or_uncertain,
            self.reporting_period_id,
            self.why_needed,
            self.affected_outcome,
            self.suggested_company_role,
            self.where_to_find,
            self.required_action,
            self.current_status,
        )
        if not all(str(value).strip() for value in required):
            raise ValueError("action items require precise, actionable details")
        if not self.effects or not self.effects.issubset(ACTION_EFFECTS):
            raise ValueError("invalid action-item effects")


@dataclass(frozen=True)
class InventoryBoundary:
    boundary_id: str
    purpose: str
    requirement_status: str
    display_name: str
    reporting_period: ReportingPeriod
    legal_entities: tuple[LegalEntity, ...] = ()
    entity_memberships: tuple[LegalEntityMembership, ...] = ()
    facility_memberships: tuple[FacilityMembership, ...] = ()
    registration_links: tuple[RegistrationLink, ...] = ()
    expected_categories: tuple[ExpectedSourceCategory, ...] = ()
    purpose_review_id: str = ""
    authority_evidence: tuple[CompetentAuthorityBoundaryEvidence, ...] = ()
    financial_reporting_entity_evidence: (
        tuple[FinancialStatementReportingEntityEvidence, ...]
    ) = ()
    composition_basis: str = CONSOLIDATION_UNRESOLVED
    organizational_approach: str = ""
    confirmation_state: str = CONFIRMATION_DRAFT
    confirmation_method: str = LOCAL_CONFIRMATION_METHOD
    locally_confirmed_at: str = ""
    responsible_contact_name: str = ""
    responsible_job_title: str = ""
    requirement_engine_status: str = ""
    requirement_effective_year: int | None = None
    applied_rule_ids: tuple[str, ...] = ()
    legal_source_ids: tuple[str, ...] = ()
    legal_authority: str = ""
    legal_document: str = ""
    missing_company_facts: tuple[str, ...] = ()
    missing_fact_resolution: str = ""
    version: int = 0
    supersedes_boundary_id: str = ""
    schema_version: str = "inventory-boundary-v2"

    def __post_init__(self) -> None:
        if self.purpose not in BOUNDARY_PURPOSES:
            raise ValueError("unsupported boundary purpose")
        if self.requirement_status not in REQUIREMENT_STATUSES:
            raise ValueError("invalid requirement_status")
        if self.confirmation_state not in CONFIRMATION_STATES:
            raise ValueError("invalid confirmation_state")
        if self.confirmation_method != LOCAL_CONFIRMATION_METHOD:
            raise ValueError("unsupported confirmation_method")
        if not self.boundary_id.strip() or not self.display_name.strip():
            raise ValueError("boundary_id and display_name are required")
        if self.composition_basis not in CONSOLIDATION_BASES:
            raise ValueError("invalid boundary composition basis")
        if len({item.entity_id for item in self.entity_memberships}) != len(
            self.entity_memberships
        ):
            raise ValueError("legal-entity memberships must be unique")
        if len({item.canonical_site_id for item in self.facility_memberships}) != len(
            self.facility_memberships
        ):
            raise ValueError("facility memberships must be unique")
        if self.schema_version == "inventory-boundary-v2" and not (
            self.purpose_review_id.strip()
        ):
            raise ValueError("v2 boundary requires a purpose review identity")
        if self.schema_version == "inventory-boundary-v2" and (
            self.registration_links or self.expected_categories
        ):
            raise ValueError(
                "v2 boundaries cannot contain raw registrations or source categories"
            )
        if self.purpose == PURPOSE_MOENV_FACILITY and self.schema_version.endswith(
            "-v2"
        ):
            if not self.authority_evidence or any(
                not item.can_define_moenv_boundary for item in self.authority_evidence
            ):
                raise ValueError(
                    "MOENV v2 boundary requires verified official-source evidence"
                )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> InventoryBoundary:
        data = dict(raw or {})
        period = ReportingPeriod(**dict(data.get("reporting_period") or {}))
        purpose = str(data.get("purpose") or "")
        if purpose == "listed_" + "standalone":
            purpose = PURPOSE_IFRS_REPORTING_ENTITY
        return cls(
            boundary_id=str(data.get("boundary_id") or ""),
            purpose=purpose,
            requirement_status=str(data.get("requirement_status") or ""),
            display_name=str(data.get("display_name") or ""),
            reporting_period=period,
            legal_entities=tuple(
                LegalEntity.from_dict(item)
                for item in data.get("legal_entities") or []
            ),
            entity_memberships=tuple(
                LegalEntityMembership(**item)
                for item in data.get("entity_memberships") or []
            ),
            facility_memberships=tuple(
                FacilityMembership(**item)
                for item in data.get("facility_memberships") or []
            ),
            registration_links=tuple(
                RegistrationLink(
                    **{
                        **item,
                        "combined_with": tuple(item.get("combined_with") or ()),
                        "confirmation_history": tuple(
                            item.get("confirmation_history") or ()
                        ),
                    }
                )
                for item in data.get("registration_links") or []
            ),
            expected_categories=tuple(
                ExpectedSourceCategory(**item)
                for item in data.get("expected_categories") or []
            ),
            purpose_review_id=str(data.get("purpose_review_id") or ""),
            authority_evidence=tuple(
                CompetentAuthorityBoundaryEvidence.from_dict(item)
                for item in data.get("authority_evidence") or []
            ),
            financial_reporting_entity_evidence=tuple(
                FinancialStatementReportingEntityEvidence.from_dict(item)
                for item in data.get("financial_reporting_entity_evidence") or []
            ),
            composition_basis=str(
                data.get("composition_basis") or CONSOLIDATION_UNRESOLVED
            ),
            organizational_approach=str(
                data.get("organizational_approach") or ""
            ),
            confirmation_state=str(
                data.get("confirmation_state") or CONFIRMATION_DRAFT
            ),
            confirmation_method=str(
                data.get("confirmation_method") or LOCAL_CONFIRMATION_METHOD
            ),
            locally_confirmed_at=str(data.get("locally_confirmed_at") or ""),
            responsible_contact_name=str(
                data.get("responsible_contact_name") or ""
            ),
            responsible_job_title=str(data.get("responsible_job_title") or ""),
            requirement_engine_status=str(
                data.get("requirement_engine_status") or ""
            ),
            requirement_effective_year=(
                int(data["requirement_effective_year"])
                if data.get("requirement_effective_year") not in (None, "")
                else None
            ),
            applied_rule_ids=tuple(data.get("applied_rule_ids") or ()),
            legal_source_ids=tuple(data.get("legal_source_ids") or ()),
            legal_authority=str(data.get("legal_authority") or ""),
            legal_document=str(data.get("legal_document") or ""),
            missing_company_facts=tuple(
                data.get("missing_company_facts") or ()
            ),
            missing_fact_resolution=str(
                data.get("missing_fact_resolution") or ""
            ),
            version=int(data.get("version") or 0),
            supersedes_boundary_id=str(data.get("supersedes_boundary_id") or ""),
            schema_version=str(
                data.get("schema_version") or "inventory-boundary-v1"
            ),
        )

    def locally_confirmed(self, *, at: str | None = None) -> InventoryBoundary:
        self.reporting_period.require_explicit_confirmation()
        memberships: tuple[LegalEntityMembership | FacilityMembership, ...] = (
            *self.entity_memberships,
            *self.facility_memberships,
        )
        if any(
            item.state in {MEMBERSHIP_PENDING, MEMBERSHIP_UNCERTAIN}
            for item in memberships
        ):
            raise ValueError("all entity and facility memberships require confirmation")
        if any(not _membership_has_exclusion_support(item) for item in memberships):
            raise ValueError(
                "excluded and not-applicable memberships require a reason and evidence"
            )
        if not any(
            item.state == MEMBERSHIP_INCLUDED for item in self.entity_memberships
        ):
            raise ValueError("at least one legal entity must be included")
        if self.purpose == PURPOSE_MOENV_FACILITY:
            included_facilities = {
                item.facility_id
                for item in self.facility_memberships
                if item.state == MEMBERSHIP_INCLUDED
            }
            if not included_facilities:
                raise ValueError(
                    "an MOENV boundary requires an included canonical site"
                )
            evidence_sites = {
                site_id
                for evidence in self.authority_evidence
                for site_id in evidence.linked_canonical_site_ids
            }
            if self.schema_version.endswith("-v2") and (
                not self.authority_evidence
                or any(
                    not evidence.can_define_moenv_boundary
                    or not evidence.covers(self.reporting_period)
                    for evidence in self.authority_evidence
                )
            ):
                raise ValueError(
                    "MOENV boundary evidence must be official and effective"
                )
            if evidence_sites and not included_facilities.issubset(evidence_sites):
                raise ValueError(
                    "MOENV membership must be linked by official boundary evidence"
                )
        if self.purpose == PURPOSE_IFRS_REPORTING_ENTITY:
            if self.composition_basis not in {
                CONSOLIDATION_STANDALONE,
                CONSOLIDATION_CONSOLIDATED,
            } or not any(
                item.confirms_reporting_entity
                for item in self.financial_reporting_entity_evidence
            ):
                raise ValueError(
                    "IFRS boundary requires confirmed reporting-entity evidence"
                )
        # Source-category coverage and row completeness belong to Stage 4.2H-B.
        # Legacy v1 records retain their category payload, but v2 confirmation
        # deliberately does not require or reinterpret it.
        normalized = self.with_normalized_confirmer_details()
        stamp = at or utc_now_iso()
        return replace(
            normalized,
            confirmation_state=CONFIRMATION_LOCAL,
            confirmation_method=LOCAL_CONFIRMATION_METHOD,
            locally_confirmed_at=stamp,
        )

    def with_normalized_confirmer_details(self) -> InventoryBoundary:
        """Return a normalized copy without mutating frozen confirmation records."""
        name, job_title = normalize_confirmer_details(
            self.responsible_contact_name,
            self.responsible_job_title,
        )
        return replace(
            self,
            responsible_contact_name=name,
            responsible_job_title=job_title,
            legal_entities=tuple(
                replace(
                    entity,
                    responsible_contact_name=name,
                    responsible_job_title=job_title,
                )
                for entity in self.legal_entities
            ),
            entity_memberships=tuple(
                replace(
                    membership,
                    responsible_contact_name=name,
                    responsible_job_title=job_title,
                )
                for membership in self.entity_memberships
            ),
            facility_memberships=tuple(
                replace(
                    membership,
                    responsible_contact_name=name,
                    responsible_job_title=job_title,
                )
                for membership in self.facility_memberships
            ),
        )


def confirmer_details_are_complete(boundary: InventoryBoundary) -> bool:
    """Return whether a current record can satisfy the local completion gate."""
    try:
        expected = normalize_confirmer_details(
            boundary.responsible_contact_name,
            boundary.responsible_job_title,
        )
        recorded = (
            *boundary.legal_entities,
            *boundary.entity_memberships,
            *boundary.facility_memberships,
        )
        return all(
            normalize_confirmer_details(
                item.responsible_contact_name,
                item.responsible_job_title,
            )
            == expected
            for item in recorded
        )
    except ConfirmerDetailsError:
        return False


@dataclass(frozen=True)
class BoundarySemanticsState:
    """Period-level v2 workspace state, including reviews with zero boundaries."""

    reporting_period: ReportingPeriod
    purpose_reviews: tuple[PurposeReview, ...] = ()
    registration_candidates: tuple[OfficialRegistrationCandidate, ...] = ()
    canonical_sites: tuple[CanonicalSite, ...] = ()
    registration_reconciliations: tuple[RegistrationReconciliation, ...] = ()
    operating_facts: tuple[PeriodOperatingFact, ...] = ()
    authority_evidence: tuple[CompetentAuthorityBoundaryEvidence, ...] = ()
    financial_reporting_entity_evidence: (
        tuple[FinancialStatementReportingEntityEvidence, ...]
    ) = ()
    boundaries: tuple[InventoryBoundary, ...] = ()
    responsible_contact_name: str = ""
    responsible_job_title: str = ""
    confirmation_state: str = CONFIRMATION_DRAFT
    locally_confirmed_at: str = ""
    version: int = 0
    schema_version: str = "boundary-semantics-v2"
    legacy_source_category_snapshot: tuple[dict[str, Any], ...] = ()
    customer_asserted_related_pending_review: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != "boundary-semantics-v2":
            raise ValueError("unsupported boundary-semantics schema")
        if self.confirmation_state not in CONFIRMATION_STATES:
            raise ValueError("invalid semantics confirmation state")
        period_id = self.reporting_period.reporting_period_id
        if any(item.reporting_period_id != period_id for item in self.purpose_reviews):
            raise ValueError("purpose review crosses reporting-period identity")
        if any(
            item.reporting_period_id != period_id
            for item in self.registration_reconciliations
        ):
            raise ValueError("registration reconciliation crosses period identity")
        if any(item.reporting_period_id != period_id for item in self.operating_facts):
            raise ValueError("operating fact crosses reporting-period identity")
        if len({item.purpose for item in self.purpose_reviews}) != len(
            self.purpose_reviews
        ):
            raise ValueError(
                "only one purpose review is allowed per purpose and period"
            )
        site_ids = {item.site_id for item in self.canonical_sites}
        candidate_ids = {item.candidate_id for item in self.registration_candidates}
        if len(site_ids) != len(self.canonical_sites):
            raise ValueError("canonical site identities must be unique")
        if len(candidate_ids) != len(self.registration_candidates):
            raise ValueError("registration candidate identities must be unique")
        reconciliation_candidate_ids = [
            item.candidate_id for item in self.registration_reconciliations
        ]
        if (
            len(reconciliation_candidate_ids) != len(candidate_ids)
            or set(reconciliation_candidate_ids) != candidate_ids
        ):
            raise ValueError(
                "each registration candidate requires exactly one reconciliation"
            )
        if any(
            item.candidate_id not in candidate_ids
            for item in self.registration_reconciliations
        ):
            raise ValueError("reconciliation candidate does not exist")
        if any(
            item.canonical_site_id
            and item.canonical_site_id not in site_ids
            for item in self.registration_reconciliations
        ):
            raise ValueError("reconciliation canonical site does not exist")
        if any(item.canonical_site_id not in site_ids for item in self.operating_facts):
            raise ValueError("operating fact canonical site does not exist")
        operating_keys = [
            (item.canonical_site_id, item.reporting_period_id)
            for item in self.operating_facts
        ]
        if len(operating_keys) != len(set(operating_keys)):
            raise ValueError("only one operating fact is allowed per site and period")
        if self.reporting_period.is_explicitly_confirmed:
            period_start = date.fromisoformat(
                self.reporting_period.period_start_confirmed
            )
            period_end = date.fromisoformat(
                self.reporting_period.period_end_confirmed
            )
            if any(
                item.status in PARTIAL_PERIOD_OPERATING_STATUSES
                and not (
                    period_start
                    <= date.fromisoformat(item.effective_date)
                    <= period_end
                )
                for item in self.operating_facts
            ):
                raise ValueError(
                    "partial-period operating date must be in the reporting period"
                )
        if any(
            membership.canonical_site_id not in site_ids
            for boundary in self.boundaries
            for membership in boundary.facility_memberships
        ):
            raise ValueError("facility membership must use a canonical site identity")
        if len({item.boundary_id for item in self.boundaries}) != len(
            self.boundaries
        ):
            raise ValueError("boundary identities must be unique")

    @property
    def legal_or_official_review_unresolved(self) -> int:
        unresolved_reviews = sum(
            item.outcome == PURPOSE_OUTCOME_UNRESOLVED
            for item in self.purpose_reviews
        )
        pending_authority = sum(
            item.verification_state == EVIDENCE_CUSTOMER_PENDING
            for item in self.authority_evidence
        )
        return unresolved_reviews + pending_authority

    @property
    def company_actionable_facts_unresolved(self) -> int:
        reconciliations = sum(
            item.state == RECONCILIATION_UNRESOLVED
            for item in self.registration_reconciliations
        )
        operating = sum(
            item.status == OPERATING_UNCERTAIN for item in self.operating_facts
        )
        memberships = sum(
            item.state in {MEMBERSHIP_PENDING, MEMBERSHIP_UNCERTAIN}
            for boundary in self.boundaries
            for item in (*boundary.entity_memberships, *boundary.facility_memberships)
        )
        reporting_entities = sum(
            item.consolidation_basis == CONSOLIDATION_UNRESOLVED
            for item in self.financial_reporting_entity_evidence
        )
        return reconciliations + operating + memberships + reporting_entities

    def locally_confirmed(self, *, at: str | None = None) -> BoundarySemanticsState:
        self.reporting_period.require_explicit_confirmation()
        name, title = normalize_confirmer_details(
            self.responsible_contact_name, self.responsible_job_title
        )
        stamp = at or utc_now_iso()
        confirmed_boundaries = tuple(
            replace(
                boundary,
                responsible_contact_name=name,
                responsible_job_title=title,
            ).locally_confirmed(at=stamp)
            for boundary in self.boundaries
        )
        return replace(
            self,
            boundaries=confirmed_boundaries,
            responsible_contact_name=name,
            responsible_job_title=title,
            confirmation_state=CONFIRMATION_LOCAL,
            locally_confirmed_at=stamp,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> BoundarySemanticsState:
        data = dict(raw or {})
        return cls(
            reporting_period=ReportingPeriod(
                **dict(data.get("reporting_period") or {})
            ),
            purpose_reviews=tuple(
                PurposeReview.from_dict(item)
                for item in data.get("purpose_reviews") or ()
            ),
            registration_candidates=tuple(
                OfficialRegistrationCandidate.from_dict(item)
                for item in data.get("registration_candidates") or ()
            ),
            canonical_sites=tuple(
                CanonicalSite.from_dict(item)
                for item in data.get("canonical_sites") or ()
            ),
            registration_reconciliations=tuple(
                RegistrationReconciliation.from_dict(item)
                for item in data.get("registration_reconciliations") or ()
            ),
            operating_facts=tuple(
                PeriodOperatingFact.from_dict(item)
                for item in data.get("operating_facts") or ()
            ),
            authority_evidence=tuple(
                CompetentAuthorityBoundaryEvidence.from_dict(item)
                for item in data.get("authority_evidence") or ()
            ),
            financial_reporting_entity_evidence=tuple(
                FinancialStatementReportingEntityEvidence.from_dict(item)
                for item in data.get("financial_reporting_entity_evidence") or ()
            ),
            boundaries=tuple(
                InventoryBoundary.from_dict(item)
                for item in data.get("boundaries") or ()
            ),
            responsible_contact_name=str(
                data.get("responsible_contact_name") or ""
            ),
            responsible_job_title=str(data.get("responsible_job_title") or ""),
            confirmation_state=str(
                data.get("confirmation_state") or CONFIRMATION_DRAFT
            ),
            locally_confirmed_at=str(data.get("locally_confirmed_at") or ""),
            version=int(data.get("version") or 0),
            schema_version=str(
                data.get("schema_version") or "boundary-semantics-v2"
            ),
            legacy_source_category_snapshot=tuple(
                data.get("legacy_source_category_snapshot") or ()
            ),
            customer_asserted_related_pending_review=tuple(
                {
                    **item,
                    "related_registration_link_ids": tuple(
                        item.get("related_registration_link_ids") or ()
                    ),
                }
                for item in (
                    data.get("customer_asserted_related_pending_review") or ()
                )
            ),
        )


def government_registration_links(
    records: Iterable[FacilityMasterRecord],
) -> tuple[RegistrationLink, ...]:
    """Return one link per government registration, never grouped by UBN."""
    links: list[RegistrationLink] = []
    for record in records:
        if SOURCE_OFFICIAL_FACTORY not in record.discovered_from:
            continue
        identity = (
            record.official_factory_registration_number.strip()
            or _stable_id("registration", record.display_name, record.address)
        )
        links.append(
            RegistrationLink(
                registration_link_id=_stable_id(
                    "registration_link", identity, record.facility_id
                ),
                registration_identity=identity,
                facility_id=record.facility_id,
                official_source=SOURCE_OFFICIAL_FACTORY,
                location=record.address,
                company_ubn=record.company_unified_business_number,
            )
        )
    return tuple(links)


def official_registration_candidates(
    records: Iterable[FacilityMasterRecord],
) -> tuple[OfficialRegistrationCandidate, ...]:
    """Convert official rows to evidence candidates without creating sites."""
    candidates: list[OfficialRegistrationCandidate] = []
    for record in records:
        if SOURCE_OFFICIAL_FACTORY not in record.discovered_from:
            continue
        identity = (
            record.official_factory_registration_number.strip()
            or _stable_id("registration", record.display_name, record.address)
        )
        candidates.append(
            OfficialRegistrationCandidate(
                candidate_id=_stable_id(
                    "registration_candidate", identity, record.facility_id
                ),
                registration_identity=identity,
                official_source=SOURCE_OFFICIAL_FACTORY,
                source_record_id=record.facility_id,
                display_name=record.official_display_name or record.display_name,
                address=record.official_address or record.address,
                company_ubn=record.company_unified_business_number,
                provenance_reference=SOURCE_OFFICIAL_FACTORY,
            )
        )
    return tuple(candidates)


def _purpose_outcome(status: str, *, current_requires_more: bool = False) -> str:
    if status == "FUTURE_REQUIREMENT":
        return PURPOSE_OUTCOME_FUTURE
    if status == "APPLICABLE" and not current_requires_more:
        return PURPOSE_OUTCOME_CURRENT
    return PURPOSE_OUTCOME_UNRESOLVED


def purpose_reviews_from_assessment(
    *,
    assessment: Any,
    workspace_id: str,
    reporting_period_id: str,
) -> tuple[PurposeReview, ...]:
    """Map existing assessment outputs to purposes without company heuristics."""
    obligations = getattr(assessment, "obligations", {}) or {}
    timestamp = str(getattr(assessment, "assessment_timestamp", "") or "")
    reviews: list[PurposeReview] = []

    def append_review(
        *,
        purpose: str,
        obligation_id: str,
        obligation: Any,
        outcome: str,
    ) -> None:
        reviews.append(
            PurposeReview(
                purpose_review_id=_stable_id(
                    "purpose_review", purpose, workspace_id, reporting_period_id
                ),
                purpose=purpose,
                reporting_period_id=reporting_period_id,
                obligation_id=obligation_id,
                assessment_status=str(getattr(obligation, "status", "") or ""),
                outcome=outcome,
                assessment_timestamp=timestamp,
                effective_year=getattr(
                    obligation, "effective_reporting_year", None
                ),
                applied_rule_ids=tuple(
                    getattr(obligation, "applied_rule_ids", None) or ()
                ),
                source_ids=tuple(getattr(obligation, "source_ids", None) or ()),
                missing_information=tuple(
                    getattr(obligation, "missing_information", None) or ()
                ),
                official_authority=str(
                    getattr(obligation, "official_authority", "") or ""
                ),
                official_document=str(
                    getattr(obligation, "official_document", "") or ""
                ),
            )
        )

    inventory = obligations.get("ghg_inventory")
    inventory_status = str(getattr(inventory, "status", "") or "")
    if inventory is not None and inventory_status != "NOT_APPLICABLE":
        append_review(
            purpose=PURPOSE_MOENV_FACILITY,
            obligation_id="ghg_inventory",
            obligation=inventory,
            outcome=_purpose_outcome(inventory_status),
        )

    ifrs = obligations.get("ifrs_s1_s2")
    ifrs_status = str(getattr(ifrs, "status", "") or "")
    ifrs_rules = set(getattr(ifrs, "applied_rule_ids", None) or ())
    if (
        ifrs is not None
        and ifrs_status in {"APPLICABLE", "FUTURE_REQUIREMENT"}
        and ifrs_rules.intersection(IFRS_ADOPTION_RULE_IDS)
    ):
        append_review(
            purpose=PURPOSE_IFRS_REPORTING_ENTITY,
            obligation_id="ifrs_s1_s2",
            obligation=ifrs,
            outcome=_purpose_outcome(
                ifrs_status, current_requires_more=ifrs_status == "APPLICABLE"
            ),
        )

    verification = obligations.get("verification_assurance")
    verification_status = str(getattr(verification, "status", "") or "")
    verification_rules = set(
        getattr(verification, "applied_rule_ids", None) or ()
    )
    if (
        verification is not None
        and verification_status != "NOT_APPLICABLE"
        and verification_rules.intersection(CONSOLIDATED_ASSURANCE_RULE_IDS)
    ):
        append_review(
            purpose=PURPOSE_LISTED_CONSOLIDATED,
            obligation_id="verification_assurance",
            obligation=verification,
            outcome=_purpose_outcome(
                verification_status,
                current_requires_more=verification_status == "APPLICABLE",
            ),
        )

    return tuple(reviews)


def canonical_site_id(
    *, workspace_id: str, display_name: str, address: str
) -> str:
    """Create a company-local site ID that never reuses a registration ID."""
    return _stable_id("canonical_site", workspace_id, display_name, address)


def initial_boundary_semantics_state(
    *,
    assessment: Any,
    company: CompanyMaster,
    facilities: Iterable[FacilityMasterRecord],
    workspace_id: str,
    reporting_period: ReportingPeriod,
) -> BoundarySemanticsState:
    candidates = official_registration_candidates(facilities)
    reviews = purpose_reviews_from_assessment(
        assessment=assessment,
        workspace_id=workspace_id,
        reporting_period_id=reporting_period.reporting_period_id,
    )
    return BoundarySemanticsState(
        reporting_period=reporting_period,
        purpose_reviews=reviews,
        registration_candidates=candidates,
        registration_reconciliations=tuple(
            RegistrationReconciliation(
                reconciliation_id=_stable_id(
                    "registration_reconciliation",
                    candidate.candidate_id,
                    reporting_period.reporting_period_id,
                ),
                candidate_id=candidate.candidate_id,
                reporting_period_id=reporting_period.reporting_period_id,
            )
            for candidate in candidates
        ),
    )


@dataclass(frozen=True)
class BoundaryReviewQueues:
    purpose_reviews: tuple[str, ...]
    reporting_entity_reviews: tuple[str, ...]
    entity_memberships: tuple[tuple[str, str], ...]
    registration_reconciliations: tuple[str, ...]
    operating_facts: tuple[tuple[str, str], ...]
    facility_memberships: tuple[tuple[str, str], ...]


def build_boundary_review_queues(
    state: BoundarySemanticsState,
) -> BoundaryReviewQueues:
    """Build deduplicated queues without any boundary × all-sites product."""
    current_financial_purposes = {
        PURPOSE_IFRS_REPORTING_ENTITY,
        PURPOSE_LISTED_CONSOLIDATED,
    }
    reporting_entity_reviews = tuple(
        item.purpose_review_id
        for item in state.purpose_reviews
        if item.purpose in current_financial_purposes
        and item.outcome != PURPOSE_OUTCOME_FUTURE
    )
    entity_memberships = tuple(
        sorted(
            {
                (membership.entity_id, boundary.boundary_id)
                for boundary in state.boundaries
                for membership in boundary.entity_memberships
            }
        )
    )
    resolved_site_ids = {
        item.canonical_site_id
        for item in state.registration_reconciliations
        if item.state in {RECONCILIATION_MATCHED, RECONCILIATION_DUPLICATE}
        and item.canonical_site_id
    }
    operating_facts = tuple(
        sorted(
            (
                site_id,
                state.reporting_period.reporting_period_id,
            )
            for site_id in resolved_site_ids
        )
    )
    facility_memberships = tuple(
        sorted(
            {
                (membership.canonical_site_id, boundary.boundary_id)
                for boundary in state.boundaries
                for membership in boundary.facility_memberships
                if membership.canonical_site_id
                in {
                    site_id
                    for evidence in boundary.authority_evidence
                    for site_id in evidence.linked_canonical_site_ids
                }
            }
        )
    )
    return BoundaryReviewQueues(
        purpose_reviews=tuple(
            item.purpose_review_id for item in state.purpose_reviews
        ),
        reporting_entity_reviews=reporting_entity_reviews,
        entity_memberships=entity_memberships,
        registration_reconciliations=tuple(
            item.reconciliation_id for item in state.registration_reconciliations
        ),
        operating_facts=operating_facts,
        facility_memberships=facility_memberships,
    )


def _status_from_obligation(obligation: Any) -> str:
    status = str(getattr(obligation, "status", "") or "")
    if status == "APPLICABLE":
        return REQUIREMENT_ENGINE
    if status == "FUTURE_REQUIREMENT":
        return REQUIREMENT_FUTURE
    return REQUIREMENT_NEEDS_FACT


def _requirement_evidence(
    obligation: Any,
    *,
    missing_company_facts: Iterable[str] = (),
    missing_fact_resolution: str = "",
    prefer_supplied_missing_facts: bool = False,
) -> dict[str, Any]:
    supplied_missing = tuple(missing_company_facts)
    missing = tuple(
        str(item)
        for item in (
            supplied_missing
            if prefer_supplied_missing_facts and supplied_missing
            else (
                getattr(obligation, "missing_information", None)
                or supplied_missing
            )
        )
        if str(item).strip()
    )
    return {
        "requirement_engine_status": str(
            getattr(obligation, "status", "") or ""
        ),
        "requirement_effective_year": getattr(
            obligation, "effective_reporting_year", None
        ),
        "applied_rule_ids": tuple(
            getattr(obligation, "applied_rule_ids", None) or ()
        ),
        "legal_source_ids": tuple(
            getattr(obligation, "source_ids", None) or ()
        ),
        "legal_authority": str(
            getattr(obligation, "official_authority", "") or ""
        ),
        "legal_document": str(
            getattr(obligation, "official_document", "") or ""
        ),
        "missing_company_facts": missing,
        "missing_fact_resolution": missing_fact_resolution,
    }


def boundaries_from_reviews(
    *,
    reviews: Iterable[PurposeReview],
    reporting_period: ReportingPeriod,
    legal_entities: Iterable[LegalEntity],
    authority_evidence: Iterable[CompetentAuthorityBoundaryEvidence] = (),
    financial_statement_evidence: Iterable[
        FinancialStatementReportingEntityEvidence
    ] = (),
) -> tuple[InventoryBoundary, ...]:
    """Build only evidence-defined current boundaries; never create fallbacks."""
    entities = tuple(legal_entities)
    by_purpose = {item.purpose: item for item in reviews}
    boundaries: list[InventoryBoundary] = []

    moenv_review = by_purpose.get(PURPOSE_MOENV_FACILITY)
    if moenv_review is not None and moenv_review.outcome != PURPOSE_OUTCOME_FUTURE:
        grouped: dict[
            tuple[str, str], list[CompetentAuthorityBoundaryEvidence]
        ] = {}
        for evidence in authority_evidence:
            if not evidence.covers(reporting_period):
                continue
            key = (
                evidence.authority.strip().casefold(),
                evidence.described_reporting_or_operating_unit.strip().casefold(),
            )
            grouped.setdefault(key, []).append(evidence)
        for key, evidence_group in sorted(grouped.items()):
            site_ids = tuple(
                sorted(
                    {
                        site_id
                        for evidence in evidence_group
                        for site_id in evidence.linked_canonical_site_ids
                    }
                )
            )
            boundary_id = _stable_id(
                "boundary",
                PURPOSE_MOENV_FACILITY,
                "\x1e".join(key),
                reporting_period.reporting_period_id,
            )
            boundaries.append(
                InventoryBoundary(
                    boundary_id=boundary_id,
                    purpose=PURPOSE_MOENV_FACILITY,
                    purpose_review_id=moenv_review.purpose_review_id,
                    requirement_status=_status_from_obligation(
                        type(
                            "_Obligation",
                            (),
                            {"status": moenv_review.assessment_status},
                        )()
                    ),
                    display_name=evidence_group[
                        0
                    ].described_reporting_or_operating_unit,
                    reporting_period=reporting_period,
                    legal_entities=entities,
                    entity_memberships=tuple(
                        LegalEntityMembership(
                            entity_id=entity.entity_id,
                            reporting_purpose=PURPOSE_MOENV_FACILITY,
                        )
                        for entity in entities
                    ),
                    facility_memberships=tuple(
                        FacilityMembership(
                            facility_id=site_id,
                            reporting_purpose=PURPOSE_MOENV_FACILITY,
                        )
                        for site_id in site_ids
                    ),
                    authority_evidence=tuple(evidence_group),
                    requirement_engine_status=moenv_review.assessment_status,
                    requirement_effective_year=moenv_review.effective_year,
                    applied_rule_ids=moenv_review.applied_rule_ids,
                    legal_source_ids=moenv_review.source_ids,
                    legal_authority=moenv_review.official_authority,
                    legal_document=moenv_review.official_document,
                    schema_version="inventory-boundary-v2",
                )
            )

    evidence_for_period = tuple(
        item
        for item in financial_statement_evidence
        if item.reporting_period_id == reporting_period.reporting_period_id
        and item.confirms_reporting_entity
    )
    ifrs_review = by_purpose.get(PURPOSE_IFRS_REPORTING_ENTITY)
    if (
        ifrs_review is not None
        and ifrs_review.assessment_status == "APPLICABLE"
        and ifrs_review.outcome != PURPOSE_OUTCOME_FUTURE
        and evidence_for_period
    ):
        determination = evidence_for_period[0]
        boundary_id = _stable_id(
            "boundary",
            PURPOSE_IFRS_REPORTING_ENTITY,
            determination.reporting_entity_identifier,
            reporting_period.reporting_period_id,
        )
        member_ids = set(determination.included_legal_entity_ids)
        boundaries.append(
            InventoryBoundary(
                boundary_id=boundary_id,
                purpose=PURPOSE_IFRS_REPORTING_ENTITY,
                purpose_review_id=ifrs_review.purpose_review_id,
                requirement_status=REQUIREMENT_ENGINE,
                display_name=determination.reporting_entity_name,
                reporting_period=reporting_period,
                legal_entities=entities,
                entity_memberships=tuple(
                    LegalEntityMembership(
                        entity_id=entity.entity_id,
                        state=(
                            MEMBERSHIP_INCLUDED
                            if entity.entity_id in member_ids
                            else MEMBERSHIP_PENDING
                        ),
                        reporting_purpose=PURPOSE_IFRS_REPORTING_ENTITY,
                    )
                    for entity in entities
                ),
                financial_reporting_entity_evidence=(determination,),
                composition_basis=determination.consolidation_basis,
                requirement_engine_status=ifrs_review.assessment_status,
                requirement_effective_year=ifrs_review.effective_year,
                applied_rule_ids=ifrs_review.applied_rule_ids,
                legal_source_ids=ifrs_review.source_ids,
                schema_version="inventory-boundary-v2",
            )
        )

    consolidated_review = by_purpose.get(PURPOSE_LISTED_CONSOLIDATED)
    consolidated_evidence = next(
        (
            item
            for item in evidence_for_period
            if item.consolidation_basis == CONSOLIDATION_CONSOLIDATED
        ),
        None,
    )
    if (
        consolidated_review is not None
        and consolidated_review.assessment_status == "APPLICABLE"
        and consolidated_review.outcome != PURPOSE_OUTCOME_FUTURE
        and consolidated_evidence is not None
    ):
        boundary_id = _stable_id(
            "boundary",
            PURPOSE_LISTED_CONSOLIDATED,
            consolidated_evidence.reporting_entity_identifier,
            reporting_period.reporting_period_id,
        )
        member_ids = set(consolidated_evidence.included_legal_entity_ids)
        boundaries.append(
            InventoryBoundary(
                boundary_id=boundary_id,
                purpose=PURPOSE_LISTED_CONSOLIDATED,
                purpose_review_id=consolidated_review.purpose_review_id,
                requirement_status=REQUIREMENT_ENGINE,
                display_name=consolidated_evidence.reporting_entity_name,
                reporting_period=reporting_period,
                legal_entities=entities,
                entity_memberships=tuple(
                    LegalEntityMembership(
                        entity_id=entity.entity_id,
                        state=(
                            MEMBERSHIP_INCLUDED
                            if entity.entity_id in member_ids
                            else MEMBERSHIP_PENDING
                        ),
                        reporting_purpose=PURPOSE_LISTED_CONSOLIDATED,
                    )
                    for entity in entities
                ),
                financial_reporting_entity_evidence=(consolidated_evidence,),
                composition_basis=CONSOLIDATION_CONSOLIDATED,
                requirement_engine_status=consolidated_review.assessment_status,
                requirement_effective_year=consolidated_review.effective_year,
                applied_rule_ids=consolidated_review.applied_rule_ids,
                legal_source_ids=consolidated_review.source_ids,
                schema_version="inventory-boundary-v2",
            )
        )
    return tuple(boundaries)


def draft_boundaries_from_assessment(
    *,
    assessment: Any,
    company: CompanyMaster,
    facilities: Iterable[FacilityMasterRecord],
    reporting_period: ReportingPeriod | None = None,
    workspace_id: str = "",
    authority_evidence: Iterable[CompetentAuthorityBoundaryEvidence] = (),
    financial_statement_evidence: Iterable[
        FinancialStatementReportingEntityEvidence
    ] = (),
) -> tuple[InventoryBoundary, ...]:
    """Compatibility entry point using the v2 assessment/evidence gates."""
    del facilities  # Official rows are candidates, never boundary constructors.
    year = int(getattr(assessment, "reporting_year", 0) or 0)
    period = reporting_period or ReportingPeriod(
        reporting_period_id=_stable_id(
            "period_unconfirmed", workspace_id or company.company_id, str(year)
        ),
        reporting_year_suggested=year or None,
    )
    reviews = purpose_reviews_from_assessment(
        assessment=assessment,
        workspace_id=workspace_id or company.company_id or "workspace",
        reporting_period_id=period.reporting_period_id,
    )
    if not period.is_explicitly_confirmed:
        return ()
    snapshot = getattr(assessment, "company_profile_snapshot", {}) or {}
    legal_name = str(company.company_name or snapshot.get("company_name") or "").strip()
    if not legal_name:
        return ()
    entity = LegalEntity(
        entity_id=company.company_id
        or _stable_id("entity", company.unified_business_number, legal_name),
        legal_name=legal_name,
        jurisdiction=str(snapshot.get("jurisdiction") or "TW"),
        registration_id=company.unified_business_number,
        taiwan_ubn=company.unified_business_number,
        source="company_master",
    )
    return boundaries_from_reviews(
        reviews=reviews,
        reporting_period=period,
        legal_entities=(entity,),
        authority_evidence=authority_evidence,
        financial_statement_evidence=financial_statement_evidence,
    )


def migrate_legacy_scope_draft(
    *,
    company: CompanyMaster,
    facilities: Iterable[FacilityMasterRecord],
    reporting_year_suggested: int | None,
) -> InventoryBoundary | None:
    """Turn unreliable legacy inclusion booleans into hints in a draft only."""
    hinted = [
        item for item in facilities if item.included_in_current_reporting_scope
    ]
    if not hinted:
        return None
    boundary_id = _stable_id(
        "boundary", "legacy-review", company.unified_business_number
    )
    entity_id = company.company_id or _stable_id(
        "entity", company.unified_business_number, company.company_name
    )
    return InventoryBoundary(
        boundary_id=boundary_id,
        purpose=PURPOSE_IFRS_REPORTING_ENTITY,
        requirement_status=REQUIREMENT_NEEDS_FACT,
        display_name=EXISTING_SCOPE_DRAFT_ZH,
        reporting_period=_suggested_period(
            boundary_id, reporting_year_suggested
        ),
        legal_entities=(
            LegalEntity(
                entity_id=entity_id,
                legal_name=company.company_name,
                jurisdiction="TW",
                registration_id=company.unified_business_number,
                taiwan_ubn=company.unified_business_number,
                source="legacy_hint",
                confirmation_state=CONFIRMATION_DRAFT,
            ),
        ),
        entity_memberships=(
            LegalEntityMembership(
                entity_id=entity_id,
                state=MEMBERSHIP_PENDING,
                reason="legacy reporting-scope hint requires review",
                reporting_purpose=PURPOSE_IFRS_REPORTING_ENTITY,
            ),
        ),
        facility_memberships=tuple(
            FacilityMembership(
                facility_id=item.facility_id,
                state=MEMBERSHIP_PENDING,
                reason="legacy reporting-scope hint requires review",
                reporting_purpose=PURPOSE_IFRS_REPORTING_ENTITY,
            )
            for item in hinted
        ),
        expected_categories=_pending_categories(),
        confirmation_state=CONFIRMATION_DRAFT,
        schema_version="inventory-boundary-v1",
    )


def _suggested_period(boundary_id: str, year: int | None) -> ReportingPeriod:
    return ReportingPeriod(
        reporting_period_id=_stable_id(
            "period", boundary_id, str(year or "unconfirmed")
        ),
        reporting_year_suggested=year,
        confirmation_state=CONFIRMATION_PENDING,
    )


def _pending_categories() -> tuple[ExpectedSourceCategory, ...]:
    return tuple(
        ExpectedSourceCategory(category=category) for category in SOURCE_CATEGORIES
    )
