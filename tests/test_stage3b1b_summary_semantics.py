"""Stage 3B.1b — monitoring-summary semantics for CREDENTIAL_REQUIRED."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from carbon_ledger.applicability import (
    OBLIGATION_CARBON_FEE,
    OBLIGATION_GHG_INVENTORY,
    CompanyProfile,
    assess_applicability,
)
from carbon_ledger.regulatory_monitor import (
    HEALTH_MONITORING_CURRENT,
    HEALTH_MONITORING_PARTIAL,
    build_monitoring_summary,
    evaluate_monitoring_health,
    run_monitor,
)
from carbon_ledger.source_access import (
    MOENV_API_KEY_ENV,
    MOENV_GHG_OPEN_DATA_SOURCE_ID,
)
from carbon_ledger.ui.view_models_compliance import regulatory_freshness_banner

REPO_ROOT = Path(__file__).resolve().parents[1]

CRITICAL_TWSE = "src_tw_twse_portal"
CRITICAL_TPEX = "src_tw_tpex_portal"


def _seed(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data/reference").mkdir(parents=True)
    (root / "data/regulatory").mkdir(parents=True)
    for rel in [
        "config/regulatory_monitoring.yaml",
        "config/regulatory_rules.csv",
        "data/reference/regulatory_sources.csv",
        "data/reference/source_access_policies.csv",
        "data/regulatory/regulatory_change_log.csv",
        "data/regulatory/source_freshness_state.csv",
        "data/regulatory/regulatory_conflict_log.csv",
        "data/regulatory/change_signals_state.json",
    ]:
        src = REPO_ROOT / rel
        if src.is_file():
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)
    return root


def _credential_gap_rows() -> list[dict[str, str]]:
    return [
        {
            "source_id": CRITICAL_TWSE,
            "freshness_status": "AUTOMATED_CURRENT",
            "fetch_status": "OK",
            "monitor_criticality": "CRITICAL",
            "last_checked_at": "2026-08-12T12:00:00Z",
            "last_successful_fetch_at": "2026-08-12T12:00:00Z",
            "consecutive_failures": "0",
        },
        {
            "source_id": CRITICAL_TPEX,
            "freshness_status": "AUTOMATED_CURRENT",
            "fetch_status": "OK",
            "monitor_criticality": "CRITICAL",
            "last_checked_at": "2026-08-12T12:00:00Z",
            "last_successful_fetch_at": "2026-08-12T12:00:00Z",
            "consecutive_failures": "0",
        },
        {
            "source_id": MOENV_GHG_OPEN_DATA_SOURCE_ID,
            "freshness_status": "MANUAL_ACCESS_REQUIRED",
            "fetch_status": "CREDENTIAL_REQUIRED",
            "monitor_criticality": "SUPPLEMENTARY",
            "last_checked_at": "2026-08-12T12:00:00Z",
            "last_successful_fetch_at": "",
            "consecutive_failures": "0",
        },
        {
            "source_id": "src_manual_ref_example",
            "freshness_status": "MANUALLY_VERIFIED",
            "fetch_status": "POLICY_SKIPPED",
            "monitor_criticality": "SUPPLEMENTARY",
            "last_checked_at": "",
            "last_successful_fetch_at": "",
            "consecutive_failures": "0",
        },
    ]


def test_credential_required_summary_semantics() -> None:
    summary = build_monitoring_summary(
        freshness_rows=_credential_gap_rows(),
        change_rows=[],
        conflict_rows=[],
        critical_source_ids=[CRITICAL_TWSE, CRITICAL_TPEX],
        coverage_metrics={
            "automated_sources_expected": 3,
            "manual_reference_sources": 24,
            "total_reference_sources": 34,
        },
        automated_sources_checked=3,
        automated_sources_successful=2,
        automated_sources_failed=0,
        automated_sources_configuration_required=1,
    )
    assert summary["sources_current"] == 2
    assert summary["automated_sources_successful"] == 2
    assert summary["automated_sources_failed"] == 0
    assert summary["automated_sources_configuration_required"] == 1
    assert summary["critical_sources_failed"] == 0
    assert summary["overall_regulatory_freshness"] == "CURRENT"
    assert summary["monitoring_health"] == HEALTH_MONITORING_PARTIAL
    assert evaluate_monitoring_health(summary) == HEALTH_MONITORING_PARTIAL
    # sources_manual_access = current-run manual action (non-supplementary).
    assert summary["sources_manual_access"] == 0
    # manual_reference_sources = policy coverage total, not current-run action.
    assert summary["manual_reference_sources"] == 24


def test_all_success_is_monitoring_current() -> None:
    summary = build_monitoring_summary(
        freshness_rows=[
            {
                "source_id": CRITICAL_TWSE,
                "freshness_status": "AUTOMATED_CURRENT",
                "fetch_status": "OK",
                "monitor_criticality": "CRITICAL",
                "last_checked_at": "2026-08-12T12:00:00Z",
                "last_successful_fetch_at": "2026-08-12T12:00:00Z",
                "consecutive_failures": "0",
            },
            {
                "source_id": CRITICAL_TPEX,
                "freshness_status": "AUTOMATED_CURRENT",
                "fetch_status": "OK",
                "monitor_criticality": "CRITICAL",
                "last_checked_at": "2026-08-12T12:00:00Z",
                "last_successful_fetch_at": "2026-08-12T12:00:00Z",
                "consecutive_failures": "0",
            },
            {
                "source_id": MOENV_GHG_OPEN_DATA_SOURCE_ID,
                "freshness_status": "AUTOMATED_CURRENT",
                "fetch_status": "OK",
                "monitor_criticality": "SUPPLEMENTARY",
                "last_checked_at": "2026-08-12T12:00:00Z",
                "last_successful_fetch_at": "2026-08-12T12:00:00Z",
                "consecutive_failures": "0",
            },
        ],
        change_rows=[],
        conflict_rows=[],
        critical_source_ids=[CRITICAL_TWSE, CRITICAL_TPEX],
        coverage_metrics={"automated_sources_expected": 3},
        automated_sources_checked=3,
        automated_sources_successful=3,
        automated_sources_failed=0,
        automated_sources_configuration_required=0,
    )
    assert summary["sources_current"] == 3
    assert summary["overall_regulatory_freshness"] == "CURRENT"
    assert summary["monitoring_health"] == HEALTH_MONITORING_CURRENT


def test_run_monitor_missing_key_counts_configuration_required(
    tmp_path: Path, monkeypatch
) -> None:
    root = _seed(tmp_path)
    monkeypatch.delenv(MOENV_API_KEY_ENV, raising=False)
    calls: list[str] = []

    def fetch(url: str, timeout: float):  # noqa: ARG001
        from carbon_ledger.regulatory_monitor import FetchResult

        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"ok")

    # Seed critical sources as already current so only MOENV is exercised.
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    result = run_monitor(
        root,
        source_id=MOENV_GHG_OPEN_DATA_SOURCE_ID,
        fetch_fn=fetch,
        write_pending_review=False,
        now=now,
    )
    assert calls == []
    summary = result["summary"]
    assert summary["automated_sources_configuration_required"] >= 1
    assert summary["automated_sources_failed"] == 0
    assert summary["critical_sources_failed"] == 0
    assert evaluate_monitoring_health(summary) != "CRITICAL_SOURCE_FAILURE"
    assert summary["monitoring_health"] == HEALTH_MONITORING_PARTIAL


def test_company_banner_hides_credential_gap_from_users() -> None:
    banner = regulatory_freshness_banner(
        REPO_ROOT,
        lang="zh-TW",
        freshness={
            "overall_regulatory_freshness": "CURRENT",
            "state": "CURRENT",
            "changes_pending_review": 0,
            "change_signals_pending_review": 0,
            "last_verified_regulatory_update_at": "2026-08-12",
            "automated_sources_expected": 3,
            "automated_sources_successful": 2,
            "automated_sources_failed": 0,
            "automated_sources_configuration_required": 1,
            "summary": {
                "critical_sources_failed": 0,
                "manual_reference_sources": 24,
                "sources_manual_access": 0,
                "restricted_automation_sources": 8,
                "monitoring_health": HEALTH_MONITORING_PARTIAL,
                "automated_sources_configuration_required": 1,
                "automated_sources_successful": 2,
                "automated_sources_failed": 0,
                "automated_sources_expected": 3,
            },
        },
    )
    assert banner["state_label"] == "已驗證"
    assert banner["auto_label"] == "核心法規監控"
    assert banner["auto_status"] == "正常"
    note = banner["admin_details"].get("supporting_sources_note", "")
    assert "尚未設定" in note
    assert "API" not in note
    assert "金鑰" not in note


def test_stage3b_applicability_unchanged() -> None:
    assessment = assess_applicability(
        CompanyProfile(
            company_name="Demo",
            entity_type="general_listed_company",
            reporting_year=2026,
            paid_in_capital_twd=10_000_000_000,
        ),
        repo_root=REPO_ROOT,
    )
    for oid in (OBLIGATION_GHG_INVENTORY, OBLIGATION_CARBON_FEE):
        result = assessment.obligations[oid]
        assert MOENV_GHG_OPEN_DATA_SOURCE_ID not in (result.source_ids or [])
        assert result.status != "NOT_APPLICABLE"
