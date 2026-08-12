"""Stage 3A.2 regulatory source/rule registry loaders (no compliance decisions).

Loads and validates machine-readable regulatory metadata only.
Does not determine applicability, compliance scores, or pass/fail outcomes.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SOURCE_REQUIRED_COLUMNS = (
    "source_id",
    "jurisdiction",
    "authority",
    "source_class",
    "source_type",
    "document_title",
    "official_url",
    "retrieved_date",
    "authority_level",
    "authority_rank",
    "status",
    "monitor_enabled",
    "monitor_frequency",
    "freshness_status",
)

RULE_REQUIRED_COLUMNS = (
    "rule_id",
    "jurisdiction",
    "framework",
    "authority",
    "source_id",
    "citation",
    "content_area",
    "requirement_title",
    "requirement_summary",
    "entity_type",
    "concept_layer",
    "publication_date",
    "source_version",
    "rule_effective_from",
    "rule_effective_to",
    "rule_status",
    "supersedes_rule_id",
    "superseded_by_rule_id",
    "last_verified_at",
    "verification_status",
    "international_standard_version",
    "taiwan_recognised_version",
    "taiwan_status",
    "version",
)

SOURCE_CLASSES = {
    "LAW_REGULATION",
    "FSC_ORDER",
    "TWSE_TPEX_OFFICIAL_RULE_OR_ANNOUNCEMENT",
    "OFFICIAL_GUIDANCE",
    "OFFICIAL_EXAMPLE",
    "EXPLANATORY_MATERIAL",
}

AUTHORITY_LEVELS = {
    "AUTHORITATIVE",
    "OFFICIAL_GUIDANCE",
    "OFFICIAL_EXAMPLE",
    "EXPLANATORY",
}

RULE_STATUSES = {
    "ACTIVE",
    "FUTURE",
    "SUPERSEDED",
    "PENDING_REVIEW",
    "UNVERIFIED",
}

VERIFICATION_STATUSES = {
    "VERIFIED_AUTHORITATIVE",
    "VERIFIED_OFFICIAL_GUIDANCE",
    "REQUIRES_MANUAL_IFRS_ACCESS",
    "PARTIAL",
    "SOURCE_NOT_YET_VERIFIED",
    "NOT_COVERED_BY_CURRENT_ORDER",
    "PENDING_REVIEW",
    "SUPERSEDED",
}

CONCEPT_LAYERS = {
    "INTERNATIONAL_IFRS",
    "TAIWAN_ADOPTION",
    "IMPLEMENTATION_GUIDANCE",
}

ENTITY_TYPES = {
    "general_listed_company",
    "general_otc_company",
    "general_listed_company|general_otc_company",
    "financial_holding_company",
    "bank",
    "bills_finance_company",
    "securities_firm",
    "futures_commission_merchant",
    "financial_holding_company|bank|bills_finance_company",
    "securities_firm|futures_commission_merchant",
    "other",
    "unresolved",
}

FRESHNESS_STATUSES = {
    "CURRENT",
    "CHECK_DUE",
    "STALE",
    "FETCH_FAILED",
    "MANUAL_ACCESS_REQUIRED",
}

FAIL_SAFE_STATES = {
    "REGULATORY_DATA_STALE",
    "UPDATE_REQUIRED",
    "SOURCE_CHECK_FAILED",
    "REGULATORY_CONFLICT",
    "FRESHNESS_STATE_UNAVAILABLE",
    "STATE_PERSISTENCE_FAILED",
    "STATE_PERSISTENCE_MISMATCH",
    "CRITICAL_SOURCE_FAILURE",
}


def default_sources_path(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "data" / "reference" / "regulatory_sources.csv"


def default_rules_path(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "config" / "regulatory_rules.csv"


def load_regulatory_sources(path: Path | None = None) -> pd.DataFrame:
    """Load the regulatory source registry CSV."""
    csv_path = Path(path) if path is not None else default_sources_path()
    frame = pd.read_csv(csv_path, dtype=str).fillna("")
    missing = [col for col in SOURCE_REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"regulatory_sources.csv missing columns: {missing}")
    if frame["source_id"].duplicated().any():
        dupes = frame.loc[frame["source_id"].duplicated(), "source_id"].tolist()
        raise ValueError(f"Duplicate source_id values: {dupes}")
    bad_levels = sorted(set(frame["authority_level"]) - AUTHORITY_LEVELS - {""})
    if bad_levels:
        raise ValueError(f"Invalid authority_level values: {bad_levels}")
    bad_classes = sorted(set(frame["source_class"]) - SOURCE_CLASSES - {""})
    if bad_classes:
        raise ValueError(f"Invalid source_class values: {bad_classes}")
    return frame


def load_regulatory_rules(path: Path | None = None) -> pd.DataFrame:
    """Load the regulatory rules registry CSV."""
    csv_path = Path(path) if path is not None else default_rules_path()
    frame = pd.read_csv(csv_path, dtype=str).fillna("")
    missing = [col for col in RULE_REQUIRED_COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError(f"regulatory_rules.csv missing columns: {missing}")
    if frame["rule_id"].duplicated().any():
        dupes = frame.loc[frame["rule_id"].duplicated(), "rule_id"].tolist()
        raise ValueError(f"Duplicate rule_id values: {dupes}")
    bad_status = sorted(set(frame["rule_status"]) - RULE_STATUSES - {""})
    if bad_status:
        raise ValueError(f"Invalid rule_status values: {bad_status}")
    bad_verify = sorted(
        set(frame["verification_status"]) - VERIFICATION_STATUSES - {""}
    )
    if bad_verify:
        raise ValueError(f"Invalid verification_status values: {bad_verify}")
    bad_layer = sorted(set(frame["concept_layer"]) - CONCEPT_LAYERS - {""})
    if bad_layer:
        raise ValueError(f"Invalid concept_layer values: {bad_layer}")
    bad_entities = sorted(set(frame["entity_type"]) - ENTITY_TYPES - {""})
    if bad_entities:
        raise ValueError(f"Invalid entity_type values: {bad_entities}")
    return frame


def active_rules(rules: pd.DataFrame) -> pd.DataFrame:
    """Return rules that may be treated as live (not superseded / pending)."""
    return rules[
        ~rules["rule_status"].isin({"SUPERSEDED", "PENDING_REVIEW"})
    ].copy()


def operable_rules(rules: pd.DataFrame) -> pd.DataFrame:
    """Rules eligible for future applicability engines (ACTIVE or FUTURE only)."""
    return rules[rules["rule_status"].isin({"ACTIVE", "FUTURE"})].copy()


def source_authority_rank(sources: pd.DataFrame, source_id: str) -> int:
    """Return numeric authority rank for a source (lower = higher precedence)."""
    matches = sources.loc[sources["source_id"] == source_id, "authority_rank"]
    if matches.empty:
        raise KeyError(f"Unknown source_id: {source_id}")
    raw = str(matches.iloc[0]).strip()
    if not raw:
        raise ValueError(f"Missing authority_rank for source_id={source_id}")
    return int(raw)


def outranks(
    sources: pd.DataFrame, higher_source_id: str, lower_source_id: str
) -> bool:
    """True when higher_source_id has stricter (lower) authority rank."""
    higher = source_authority_rank(sources, higher_source_id)
    lower = source_authority_rank(sources, lower_source_id)
    return higher < lower


def entity_type_tokens(entity_type: str) -> set[str]:
    """Split pipe-joined entity_type values."""
    return {part.strip() for part in str(entity_type).split("|") if part.strip()}


def rules_for_entity_type(rules: pd.DataFrame, entity_type: str) -> pd.DataFrame:
    """Return operable rules whose entity_type includes the requested type."""
    wanted = str(entity_type).strip()
    mask = rules["entity_type"].map(lambda value: wanted in entity_type_tokens(value))
    return operable_rules(rules.loc[mask].copy())


def validate_registry_integrity(
    sources: pd.DataFrame,
    rules: pd.DataFrame,
) -> list[str]:
    """Return human-readable integrity issues (empty list means OK)."""
    issues: list[str] = []
    source_ids = set(sources["source_id"])
    orphan_rules = sorted(set(rules["source_id"]) - source_ids - {""})
    if orphan_rules:
        issues.append(f"Rules reference unknown source_id values: {orphan_rules}")
    banned = ("compliant", "non-compliant", "pass", "fail", "penalty")
    blob = " ".join(
        rules["requirement_summary"].str.lower().tolist()
        + rules["requirement_title"].str.lower().tolist()
    )
    for token in banned:
        if token in blob:
            issues.append(
                f"Registry text appears to encode a compliance conclusion ({token})."
            )
    return issues


def ui_rule_freshness_payload(
    rule_row: pd.Series, freshness_status: str
) -> dict[str, str]:
    """Backend payload for future UI last-updated / rule metadata display."""
    return {
        "official_source": str(rule_row.get("source_id", "")),
        "citation": str(rule_row.get("citation", "")),
        "effective_date": str(rule_row.get("rule_effective_from", "")),
        "rule_version": str(rule_row.get("source_version", "")),
        "last_verified_date": str(rule_row.get("last_verified_at", "")),
        "freshness_status": str(freshness_status),
    }
