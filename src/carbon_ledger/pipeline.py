"""Reproducible end-to-end pipeline orchestration.

Phase 7C wires existing tested modules into one structured demo run. It does
not add carbon-accounting or regulatory rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from carbon_ledger.calculate import calculate_activity_emissions
from carbon_ledger.cbam import OUTPUT_COLUMNS as CBAM_OUTPUT_COLUMNS
from carbon_ledger.cbam import (
    evaluate_cbam,
    load_cbam_product_scenario,
    load_cbam_references,
    load_cbam_rules,
)
from carbon_ledger.factors import validate_factor_registry
from carbon_ledger.ifrs_s2 import OUTPUT_COLUMNS as IFRS_S2_OUTPUT_COLUMNS
from carbon_ledger.ifrs_s2 import (
    evaluate_ifrs_s2_readiness,
    load_ifrs_s2_references,
    load_ifrs_s2_reporting_context,
    load_ifrs_s2_rules,
)
from carbon_ledger.ingest import ingest_evidence
from carbon_ledger.match_factors import match_activity_factors
from carbon_ledger.normalize import normalize_activity_records
from carbon_ledger.qa import build_core_qa_issues, load_qa_rules
from carbon_ledger.rules import OUTPUT_COLUMNS as GHG_OUTPUT_COLUMNS
from carbon_ledger.rules import (
    evaluate_ghg_protocol,
    load_ghg_protocol_references,
    load_ghg_protocol_rules,
)

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass
class PipelineRunResult:
    """Complete structured result of one demo pipeline run."""

    run_id: str
    ingested_at: pd.Timestamp
    include_ghg: bool
    include_cbam: bool
    include_ifrs_s2: bool
    source_documents_accepted: pd.DataFrame
    source_documents_rejected: pd.DataFrame
    activity_records_accepted: pd.DataFrame
    activity_records_rejected: pd.DataFrame
    normalized_records: pd.DataFrame
    candidate_matches: pd.DataFrame
    activity_readiness: pd.DataFrame
    calculation_results: pd.DataFrame
    core_qa_issues: pd.DataFrame
    ghg_evaluations: pd.DataFrame
    cbam_evaluations: pd.DataFrame
    ifrs_s2_evaluations: pd.DataFrame


def validate_run_id(run_id: str) -> str:
    """Validate and return a safe run_id or raise ValueError."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string.")
    cleaned = run_id.strip()
    if "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError(
            "run_id must not contain path separators or path traversal."
        )
    if not RUN_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "run_id must be 1-64 characters using only letters, numbers, "
            "underscore, hyphen, or period."
        )
    return cleaned


def run_demo_pipeline(
    repo_root: Path,
    *,
    run_id: str,
    ingested_at: pd.Timestamp,
    include_ghg: bool = False,
    include_cbam: bool = False,
    include_ifrs_s2: bool = False,
) -> PipelineRunResult:
    """Run the reproducible demo pipeline without writing files.

    Optional adapters never alter the framework-neutral core outputs.
    """
    validated_run_id = validate_run_id(run_id)
    if not isinstance(ingested_at, pd.Timestamp):
        raise ValueError("ingested_at must be a pandas.Timestamp.")

    root = Path(repo_root)
    raw_directory = root / "data" / "raw"
    reference_directory = root / "data" / "reference"
    config_directory = root / "config"

    run_ghg = bool(include_ghg or include_ifrs_s2)
    run_cbam = bool(include_cbam)
    run_ifrs = bool(include_ifrs_s2)

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------
    ingestion = ingest_evidence(
        raw_directory=raw_directory,
        ingestion_run_id=f"ingestion_{validated_run_id}",
        ingested_at=pd.Timestamp(ingested_at),
    )
    accepted_documents = ingestion.source_documents.accepted
    rejected_documents = ingestion.source_documents.rejected
    accepted_activities = ingestion.activity_records.accepted
    rejected_activities = ingestion.activity_records.rejected

    normalized = normalize_activity_records(accepted_activities)

    registry = validate_factor_registry(reference_directory)
    activities_for_matching = accepted_activities.merge(
        normalized[["record_id", "normalized_unit", "normalization_status"]],
        on="record_id",
        how="left",
    )
    matching = match_activity_factors(
        activities_for_matching,
        registry.emission_factors,
        registry.calculation_dependencies,
    )
    calculations = calculate_activity_emissions(
        normalized,
        matching.candidate_matches,
        matching.activity_readiness,
        registry.emission_factors,
    )

    ingestion_rejections = pd.concat(
        [rejected_documents, rejected_activities],
        ignore_index=True,
    )
    core_qa_issues = build_core_qa_issues(
        accepted_activities,
        ingestion_rejections,
        normalized,
        matching.activity_readiness,
        calculations,
        load_qa_rules(config_directory),
    )

    # ------------------------------------------------------------------
    # Optional adapters
    # ------------------------------------------------------------------
    if run_ghg:
        ghg_evaluations = evaluate_ghg_protocol(
            accepted_activities,
            load_ghg_protocol_rules(config_directory),
            load_ghg_protocol_references(reference_directory),
        )
    else:
        ghg_evaluations = pd.DataFrame(columns=GHG_OUTPUT_COLUMNS)

    if run_cbam:
        cbam_evaluations = evaluate_cbam(
            accepted_activities,
            load_cbam_rules(config_directory),
            load_cbam_references(reference_directory),
            load_cbam_product_scenario(config_directory),
        )
    else:
        cbam_evaluations = pd.DataFrame(columns=CBAM_OUTPUT_COLUMNS)

    if run_ifrs:
        ifrs_s2_evaluations = evaluate_ifrs_s2_readiness(
            accepted_activities,
            calculations,
            ghg_evaluations,
            load_ifrs_s2_rules(config_directory),
            load_ifrs_s2_references(reference_directory),
            load_ifrs_s2_reporting_context(config_directory),
        )
    else:
        ifrs_s2_evaluations = pd.DataFrame(columns=IFRS_S2_OUTPUT_COLUMNS)

    return PipelineRunResult(
        run_id=validated_run_id,
        ingested_at=pd.Timestamp(ingested_at),
        include_ghg=run_ghg,
        include_cbam=run_cbam,
        include_ifrs_s2=run_ifrs,
        source_documents_accepted=accepted_documents,
        source_documents_rejected=rejected_documents,
        activity_records_accepted=accepted_activities,
        activity_records_rejected=rejected_activities,
        normalized_records=normalized,
        candidate_matches=matching.candidate_matches,
        activity_readiness=matching.activity_readiness,
        calculation_results=calculations,
        core_qa_issues=core_qa_issues,
        ghg_evaluations=ghg_evaluations,
        cbam_evaluations=cbam_evaluations,
        ifrs_s2_evaluations=ifrs_s2_evaluations,
    )
