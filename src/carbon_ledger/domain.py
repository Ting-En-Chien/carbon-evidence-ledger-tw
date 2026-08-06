"""Controlled vocabularies for raw source-document and activity-record tables.

These constants define the only allowed values for categorical fields in
Phase 1A. They are used by Pandera schemas and tests.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# source_documents
# ---------------------------------------------------------------------------

DOCUMENT_TYPES: tuple[str, ...] = (
    "electricity_bill",
    "natural_gas_invoice",
    "fuel_receipt",
    "material_purchase_invoice",
    "transport_invoice",
    "production_log",
    "other",
    "unknown",
)

DATA_ORIGINS: tuple[str, ...] = (
    "synthetic_generated",
    "public_reference",
    "company_provided",
    "unknown",
)

# ---------------------------------------------------------------------------
# activity_records — record classification
# ---------------------------------------------------------------------------

RECORD_TYPES: tuple[str, ...] = (
    "emission_activity",
    "material_input",
    "transport_activity",
    "production_output",
    "scrap_output",
    "other",
    "unknown",
)

ACTIVITY_TYPES: tuple[str, ...] = (
    "grid_electricity",
    "natural_gas",
    "diesel",
    "purchased_steel",
    "third_party_transport",
    "finished_goods_output",
    "scrap_output",
    "other",
    "unknown",
)

PROCESS_USES: tuple[str, ...] = (
    "heat_treatment",
    "forging",
    "company_vehicle",
    "office_heating",
    "general_factory",
    "other",
    "unknown",
    "not_applicable",
)

TRANSPORT_PAYERS: tuple[str, ...] = (
    "exporter",
    "supplier",
    "customer",
    "third_party",
    "unknown",
    "not_applicable",
)

OWNERSHIP_CONTROLS: tuple[str, ...] = (
    "owned",
    "controlled",
    "third_party",
    "unknown",
    "not_applicable",
)

ORGANIZATIONAL_BOUNDARY_STATUSES: tuple[str, ...] = (
    "inside",
    "outside",
    "unknown",
    "not_applicable",
)

CBAM_PROCESS_BOUNDARY_STATUSES: tuple[str, ...] = (
    "inside",
    "outside",
    "unknown",
    "not_applicable",
)

MEASUREMENT_METHODS: tuple[str, ...] = (
    "invoice",
    "meter",
    "purchase_record",
    "production_log",
    "supplier_data",
    "estimate",
    "other",
    "unknown",
)

DATA_QUALITY_TIERS: tuple[str, ...] = (
    "primary",
    "secondary",
    "estimated",
    "synthetic_test",
    "unknown",
)

HUMAN_REVIEW_STATUSES: tuple[str, ...] = (
    "not_required",
    "needs_review",
    "approved",
    "rejected",
)

SUPPORTED_UNITS: tuple[str, ...] = (
    "kWh",
    "MWh",
    "m3",
    "L",
    "kg",
    "t",
)

# activity_type -> allowed units
# (rows not listed are checked against SUPPORTED_UNITS only)
ACTIVITY_TYPE_UNIT_COMPATIBILITY: dict[str, tuple[str, ...]] = {
    "grid_electricity": ("kWh", "MWh"),
    "natural_gas": ("m3",),
    "diesel": ("L",),
    "purchased_steel": ("kg", "t"),
    "finished_goods_output": ("kg", "t"),
    "scrap_output": ("kg", "t"),
}

# Fields where value "unknown" triggers human_review_status = needs_review
ACTIVITY_UNKNOWN_REVIEW_FIELDS: tuple[str, ...] = (
    "record_type",
    "activity_type",
    "process_use",
    "ownership_control",
    "organizational_boundary_status",
    "cbam_process_boundary_status",
)

# Fields where value "other" requires a non-empty notes explanation
ACTIVITY_OTHER_NOTES_FIELDS: tuple[str, ...] = (
    "record_type",
    "activity_type",
    "process_use",
    "measurement_method",
)

# Derived fields that must never appear on raw activity_records
FORBIDDEN_ACTIVITY_DERIVED_COLUMNS: frozenset[str] = frozenset(
    {
        "calculated_tco2e",
        "calculated_kgco2e",
        "emission_factor",
        "ghg_scope",
        "scope3_category",
        "cbam_data_role",
        "cbam_relevance",
        "ifrs_s2_relevance",
    }
)
