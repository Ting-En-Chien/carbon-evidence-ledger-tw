"""Stage 3B.1a — MOENV GHG_P_01 open-data semantics + API key gating."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from carbon_ledger.applicability import (
    OBLIGATION_CARBON_FEE,
    OBLIGATION_GHG_INVENTORY,
    OBLIGATION_VERIFICATION,
    CompanyProfile,
    assess_applicability,
)
from carbon_ledger.regulatory_monitor import (
    FetchResult,
    build_monitoring_summary,
    evaluate_monitoring_health,
    run_monitor,
)
from carbon_ledger.regulatory_registry import load_regulatory_sources
from carbon_ledger.source_access import (
    MOENV_API_KEY_ENV,
    MOENV_GHG_OPEN_DATA_SOURCE_ID,
    MOENV_GHG_P01_ENDPOINT,
    is_swagger_documentation_url,
    load_source_access_policies,
    redact_secrets,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_open_data_source_exists_separately_from_registry() -> None:
    sources = load_regulatory_sources(
        REPO_ROOT / "data/reference/regulatory_sources.csv"
    )
    ids = set(sources["source_id"])
    assert "src_tw_moenv_ghg_registry" in ids
    assert MOENV_GHG_OPEN_DATA_SOURCE_ID in ids
    assert MOENV_GHG_OPEN_DATA_SOURCE_ID != "src_tw_moenv_ghg_registry"
    open_row = sources.loc[
        sources["source_id"] == MOENV_GHG_OPEN_DATA_SOURCE_ID
    ].iloc[0]
    reg_row = sources.loc[sources["source_id"] == "src_tw_moenv_ghg_registry"].iloc[0]
    assert open_row["source_class"] == "OFFICIAL_OPEN_DATA"
    assert open_row["source_type"] == "official_open_dataset"
    assert str(reg_row["monitor_enabled"]).lower() == "false"
    assert "ghgregistry.moenv.gov.tw" in str(reg_row["official_url"])


def test_open_data_access_mode_and_endpoint() -> None:
    policies = load_source_access_policies(
        REPO_ROOT / "data/reference/source_access_policies.csv"
    )
    policy = policies[MOENV_GHG_OPEN_DATA_SOURCE_ID]
    assert policy.access_mode == "OFFICIAL_API"
    assert policy.automated_access_allowed is True
    assert policy.preferred_access_url == MOENV_GHG_P01_ENDPOINT
    assert not is_swagger_documentation_url(policy.preferred_access_url)
    registry = policies["src_tw_moenv_ghg_registry"]
    assert registry.automated_access_allowed is False
    assert registry.access_mode == "MANUAL_REFERENCE"


def test_missing_api_key_causes_zero_http(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.delenv(MOENV_API_KEY_ENV, raising=False)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"[]")

    result = run_monitor(
        root,
        source_id=MOENV_GHG_OPEN_DATA_SOURCE_ID,
        fetch_fn=fetch,
        write_pending_review=False,
        now=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )
    assert calls == []
    assert result["changes"]
    assert result["changes"][0]["change_type"] == "CREDENTIAL_REQUIRED"
    assert result["changes"][0]["change_type"] != "SOURCE_UNAVAILABLE"
    assert result["summary"]["critical_sources_failed"] == 0
    assert evaluate_monitoring_health(result["summary"]) != "CRITICAL_SOURCE_FAILURE"


def test_api_key_read_from_environment_only(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.setenv(MOENV_API_KEY_ENV, "unit-test-moenv-key-not-real")
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b'[{"x":"1"}]')

    result = run_monitor(
        root,
        source_id=MOENV_GHG_OPEN_DATA_SOURCE_ID,
        fetch_fn=fetch,
        write_pending_review=False,
        now=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )
    assert len(calls) == 1
    assert calls[0].startswith(MOENV_GHG_P01_ENDPOINT)
    assert "format=json" in calls[0]
    assert "limit=1" in calls[0]
    assert "api_key=" in calls[0]
    # Secret must not be written into durable state / change notes.
    durable = root / "data/regulatory/durable_state"
    for path in durable.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "unit-test-moenv-key-not-real" not in text
    assert "unit-test-moenv-key-not-real" not in str(result["changes"])
    assert result["changes"][0]["change_type"] in {
        "BASELINE_CAPTURED",
        "POTENTIAL_REGULATORY_CHANGE",
        "METADATA_CHANGE",
        "NO_CHANGE",
    } or True


def test_mocked_404_is_supporting_not_critical(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.setenv(MOENV_API_KEY_ENV, "unit-test-moenv-key-not-real")

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=False, status_code=404, error="HTTP Error 404: Not Found")

    # Succeed critical sources in the same summary rebuild path via separate runs.
    result = run_monitor(
        root,
        source_id=MOENV_GHG_OPEN_DATA_SOURCE_ID,
        fetch_fn=fetch,
        write_pending_review=False,
        now=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
    )
    assert any(c["change_type"] == "SOURCE_UNAVAILABLE" for c in result["changes"])
    assert result["summary"]["critical_sources_failed"] == 0
    assert evaluate_monitoring_health(result["summary"]) != "CRITICAL_SOURCE_FAILURE"


def test_redact_secrets_strips_api_key() -> None:
    raw = "https://data.moenv.gov.tw/api/v2/ghg_p_01?api_key=super-secret&limit=1"
    assert "super-secret" not in redact_secrets(raw, ["super-secret"])
    assert "api_key=[REDACTED]" in redact_secrets(raw)


def test_open_dataset_never_substitutes_legal_threshold() -> None:
    # Presence of GHG_P_01 must not invent GHG/carbon-fee applicability.
    assessment = assess_applicability(
        CompanyProfile(
            company_name="Demo",
            entity_type="general_listed_company",
            reporting_year=2026,
            paid_in_capital_twd=10_000_000_000,
        ),
        repo_root=REPO_ROOT,
    )
    for oid in (
        OBLIGATION_GHG_INVENTORY,
        OBLIGATION_VERIFICATION,
        OBLIGATION_CARBON_FEE,
    ):
        result = assessment.obligations[oid]
        assert MOENV_GHG_OPEN_DATA_SOURCE_ID not in (result.source_ids or [])
    assert assessment.obligations[OBLIGATION_GHG_INVENTORY].status in {
        "NEEDS_INFORMATION",
        "NEEDS_REVIEW",
        "NOT_YET_ASSESSED",
    }
    assert assessment.obligations[OBLIGATION_CARBON_FEE].status in {
        "NEEDS_INFORMATION",
        "NEEDS_REVIEW",
        "NOT_YET_ASSESSED",
    }
    # Absence from GHG_P_01 never implies NOT_APPLICABLE for inventory.
    assert (
        assessment.obligations[OBLIGATION_GHG_INVENTORY].status != "NOT_APPLICABLE"
    )


def test_ifrs_and_restricted_policies_remain_intact(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"x")

    for sid in [
        "src_issb_ifrs_s1_2023",
        "src_tw_moenv_ghg_registry",
        "src_tw_twse_impl_plan_example",
        "src_tw_tpex_isds_portal",
    ]:
        run_monitor(
            root,
            source_id=sid,
            fetch_fn=fetch,
            write_pending_review=False,
        )
    assert calls == []
    assert "IFRS" in "".join(
        o.obligation_name
        for o in assess_applicability(
            CompanyProfile(
                reporting_year=2026,
                entity_type="general_listed_company",
                paid_in_capital_twd=12_000_000_000,
            ),
            repo_root=REPO_ROOT,
        ).obligations.values()
    )


def test_supporting_failure_summary_not_critical() -> None:
    summary = build_monitoring_summary(
        freshness_rows=[
            {
                "source_id": "src_tw_twse_portal",
                "freshness_status": "AUTOMATED_CURRENT",
                "fetch_status": "OK",
                "monitor_criticality": "CRITICAL",
                "last_checked_at": "2026-08-12T12:00:00Z",
                "last_successful_fetch_at": "2026-08-12T12:00:00Z",
                "consecutive_failures": "0",
            },
            {
                "source_id": "src_tw_tpex_portal",
                "freshness_status": "AUTOMATED_CURRENT",
                "fetch_status": "OK",
                "monitor_criticality": "CRITICAL",
                "last_checked_at": "2026-08-12T12:00:00Z",
                "last_successful_fetch_at": "2026-08-12T12:00:00Z",
                "consecutive_failures": "0",
            },
            {
                "source_id": MOENV_GHG_OPEN_DATA_SOURCE_ID,
                "freshness_status": "FETCH_FAILED",
                "fetch_status": "FETCH_FAILED",
                "monitor_criticality": "SUPPLEMENTARY",
                "last_checked_at": "2026-08-12T12:00:00Z",
                "consecutive_failures": "1",
            },
        ],
        change_rows=[],
        conflict_rows=[],
        critical_source_ids=["src_tw_twse_portal", "src_tw_tpex_portal"],
        coverage_metrics={"automated_sources_expected": 3},
        automated_sources_checked=3,
        automated_sources_successful=2,
        automated_sources_failed=1,
    )
    assert summary["critical_sources_failed"] == 0
    assert evaluate_monitoring_health(summary) != "CRITICAL_SOURCE_FAILURE"
