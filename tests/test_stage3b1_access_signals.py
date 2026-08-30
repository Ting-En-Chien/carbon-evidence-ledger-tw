"""Stage 3B.1 — access policy enforcement + official change signals."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from carbon_ledger.applicability import (
    CompanyProfile,
    assess_applicability,
)
from carbon_ledger.regulatory_monitor import (
    FetchResult,
    get_regulatory_freshness,
    run_monitor,
)
from carbon_ledger.regulatory_registry import (
    load_regulatory_rules,
    load_regulatory_sources,
)
from carbon_ledger.regulatory_signals import (
    AlertMessage,
    MockMailboxAdapter,
    RegulatorySignalStore,
    admin_mark_verified_regulatory_change,
    admin_review_no_rule_change,
    ingest_alerts_from_adapter,
    ingest_ifrs_alert_message,
    signal_fingerprint,
)
from carbon_ledger.source_access import (
    load_source_access_policies,
    policy_for_source,
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


def test_ifrs_sources_cause_zero_network_requests(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"should-not-run")

    for sid in [
        "src_issb_ifrs_s1_2023",
        "src_issb_ifrs_s2_2023",
        "src_issb_ifrs_s2_ghg_amendments_2025",
        "src_issb_s1_s2_mapping_education",
        "src_issb_knowledge_hub",
        "src_issb_sasb_hub",
        "src_ifrs_org_portal",
    ]:
        result = run_monitor(
            root,
            source_id=sid,
            fetch_fn=fetch,
            write_pending_review=False,
            now=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
        )
        assert result["changes"]
        assert result["changes"][0]["change_type"] == "POLICY_SKIPPED"
    assert calls == []


def test_ifrs_sources_remain_in_official_registry() -> None:
    sources = load_regulatory_sources(
        REPO_ROOT / "data/reference/regulatory_sources.csv"
    )
    for sid in [
        "src_issb_ifrs_s1_2023",
        "src_issb_ifrs_s2_2023",
        "src_ifrs_org_portal",
    ]:
        row = sources.loc[sources["source_id"] == sid].iloc[0]
        assert "ifrs.org" in str(row["official_url"])
        assert str(row["monitor_enabled"]).lower() == "false"


def test_missing_policy_defaults_to_deny_automation(tmp_path: Path) -> None:
    policy = policy_for_source("src_does_not_exist", {}, repo_root=tmp_path)
    assert policy.automated_access_allowed is False


def test_restricted_source_skipped_before_http(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"x")

    result = run_monitor(
        root,
        source_id="src_tw_fsc_law_portal",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert calls == []
    assert result["changes"][0]["change_type"] == "POLICY_SKIPPED"
    assert result["changes"][0]["change_type"] != "SOURCE_UNAVAILABLE"
    assert result["summary"]["critical_sources_failed"] == 0


def test_twse_direct_webpage_not_auto_fetched_without_policy(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    # TWSE implementation-plan pages remain MANUAL_REFERENCE.
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"x")

    run_monitor(
        root,
        source_id="src_tw_twse_impl_plan_example",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert calls == []


def test_approved_twse_openapi_source_can_be_fetched(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b'{"openapi":"3.0"}')

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert calls
    assert all("openapi.twse.com.tw" in u for u in calls)
    assert all("www.twse.com.tw" not in u for u in calls)
    assert result["changes"][0]["change_type"] in {
        "BASELINE_CAPTURED",
        "POTENTIAL_REGULATORY_CHANGE",
        "NO_CHANGE",
        "METADATA_CHANGE",
    } or result["summary"]


def test_tpex_restricted_page_not_fetched(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"x")

    run_monitor(
        root,
        source_id="src_tw_tpex_isds_portal",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert calls == []


def test_approved_tpex_openapi_can_be_fetched(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b'{"swagger":"2.0"}')

    run_monitor(
        root,
        source_id="src_tw_tpex_portal",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert calls
    assert all("tpex.org.tw/openapi" in u for u in calls)


def test_approved_moenv_open_data_can_be_fetched(tmp_path: Path, monkeypatch) -> None:
    root = _seed(tmp_path)
    monkeypatch.setenv("MOENV_API_KEY", "unit-test-moenv-key-not-real")
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b'[{"ok":"1"}]')

    run_monitor(
        root,
        source_id="src_tw_moenv_ghg_open_data",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert calls
    assert all("data.moenv.gov.tw/api/v2/ghg_p_01" in u for u in calls)
    assert all("swagger" not in u for u in calls)


def test_api_rate_limit_handling_is_bounded(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    attempts = {"n": 0}

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        attempts["n"] += 1
        return FetchResult(ok=False, status_code=429, error="rate limited")

    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert attempts["n"] <= 3


def test_403_never_causes_browser_impersonation_or_bypass(tmp_path: Path) -> None:
    root = _seed(tmp_path)

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=False, status_code=403, error="HTTP 403")

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        write_pending_review=False,
    )
    assert any(
        c["change_type"] == "ACCESS_POLICY_REVIEW_REQUIRED" for c in result["changes"]
    )
    monitor_src = (
        REPO_ROOT / "src/carbon_ledger/regulatory_monitor.py"
    ).read_text(encoding="utf-8")
    assert "Mozilla/5.0 (Windows" not in monitor_src
    assert "selenium" not in monitor_src.lower()
    assert "playwright" not in monitor_src.lower()


def test_approved_ifrs_email_creates_potential_change(tmp_path: Path) -> None:
    store = RegulatorySignalStore(tmp_path / "signals.json")
    msg = AlertMessage(
        message_id="<m1@ifrs.org>",
        sender="alerts@ifrs.org",
        subject="IFRS S1 update available",
        received_at="2026-08-12T09:00:00Z",
        label="Regulatory-IFRS",
        snippet="Topic notice only",
    )
    signal = ingest_ifrs_alert_message(msg)
    assert signal is not None
    assert signal.status == "POTENTIAL_REGULATORY_CHANGE"
    store.upsert_signal(signal)
    assert store.pending_count() == 1


def test_ifrs_email_does_not_trigger_ifrs_http(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=True, status_code=200, body=b"x")

    adapter = MockMailboxAdapter(
        [
            AlertMessage(
                message_id="<m2@ifrs.org>",
                sender="alerts@ifrs.org",
                subject="IFRS S2 climate disclosures",
                received_at="2026-08-12T09:00:00Z",
                label="Regulatory-IFRS",
                snippet="https://www.ifrs.org/news/demo",
                official_link="https://www.ifrs.org/news/demo",
            )
        ]
    )
    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        signal_adapter=adapter,
        write_pending_review=False,
    )
    assert all("ifrs.org" not in u for u in calls)


def test_unapproved_sender_cannot_become_official_signal() -> None:
    msg = AlertMessage(
        message_id="<spam@example.com>",
        sender="random@example.com",
        subject="IFRS S2 amendment",
        received_at="2026-08-12T09:00:00Z",
        label="Regulatory-IFRS",
    )
    assert ingest_ifrs_alert_message(msg) is None


def test_duplicate_email_is_deduplicated(tmp_path: Path) -> None:
    store = RegulatorySignalStore(tmp_path / "signals.json")
    adapter = MockMailboxAdapter(
        [
            AlertMessage(
                message_id="<dup@ifrs.org>",
                sender="alerts@ifrs.org",
                subject="IFRS S2",
                received_at="2026-08-12T09:00:00Z",
                label="Regulatory-IFRS",
            ),
            AlertMessage(
                message_id="<dup@ifrs.org>",
                sender="alerts@ifrs.org",
                subject="IFRS S2",
                received_at="2026-08-12T09:00:00Z",
                label="Regulatory-IFRS",
            ),
        ]
    )
    stats = ingest_alerts_from_adapter(adapter, store)
    assert stats["created"] == 1
    assert stats["duplicates"] == 1
    assert len(store.list_signals()) == 1
    fp = signal_fingerprint(
        source_id="src_issb_ifrs_s2_2023",
        external_message_id="<dup@ifrs.org>",
    )
    assert store.list_signals()[0].signal_fingerprint == fp


def test_email_does_not_auto_activate_rule(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    before = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_before = set(before.loc[before["rule_status"] == "ACTIVE", "rule_id"])
    store = RegulatorySignalStore(tmp_path / "signals.json")
    adapter = MockMailboxAdapter(
        [
            AlertMessage(
                message_id="<act@ifrs.org>",
                sender="alerts@ifrs.org",
                subject="IFRS S2 amendments published",
                received_at="2026-08-12T09:00:00Z",
                label="Regulatory-IFRS",
            )
        ]
    )
    ingest_alerts_from_adapter(adapter, store)
    after = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_after = set(after.loc[after["rule_status"] == "ACTIVE", "rule_id"])
    assert active_after == active_before


def test_signal_persists_across_runs(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    store = RegulatorySignalStore(path)
    msg = AlertMessage(
        message_id="<persist@ifrs.org>",
        sender="alerts@ifrs.org",
        subject="IFRS S1",
        received_at="2026-08-12T09:00:00Z",
        label="Regulatory-IFRS",
    )
    signal = ingest_ifrs_alert_message(msg)
    assert signal is not None
    store.upsert_signal(signal)
    reloaded = RegulatorySignalStore(path)
    assert len(reloaded.list_signals()) == 1


def test_reviewed_no_change_does_not_modify_registry(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    store = RegulatorySignalStore(tmp_path / "signals.json")
    signal = ingest_ifrs_alert_message(
        AlertMessage(
            message_id="<nochg@ifrs.org>",
            sender="alerts@ifrs.org",
            subject="IFRS S2",
            received_at="2026-08-12T09:00:00Z",
            label="Regulatory-IFRS",
        )
    )
    assert signal is not None
    store.upsert_signal(signal)
    before = (root / "config/regulatory_rules.csv").read_text(encoding="utf-8")
    admin_review_no_rule_change(store, signal.signal_id, reviewed_by="admin")
    after = (root / "config/regulatory_rules.csv").read_text(encoding="utf-8")
    assert before == after
    assert store.list_signals()[0].status == "REVIEWED_NO_RULE_CHANGE"


def test_verified_change_workflow_does_not_mutate_history(tmp_path: Path) -> None:
    root = _seed(tmp_path)
    store = RegulatorySignalStore(tmp_path / "signals.json")
    signal = ingest_ifrs_alert_message(
        AlertMessage(
            message_id="<ver@ifrs.org>",
            sender="alerts@ifrs.org",
            subject="IFRS S2",
            received_at="2026-08-12T09:00:00Z",
            label="Regulatory-IFRS",
        )
    )
    assert signal is not None
    store.upsert_signal(signal)
    before_rules = load_regulatory_rules(root / "config/regulatory_rules.csv")
    admin_mark_verified_regulatory_change(
        store, signal.signal_id, reviewed_by="admin"
    )
    after_rules = load_regulatory_rules(root / "config/regulatory_rules.csv")
    assert list(before_rules["rule_id"]) == list(after_rules["rule_id"])
    assert list(before_rules["rule_status"]) == list(after_rules["rule_status"])
    assert "Create/update a NEW rule version" in store.list_signals()[0].notes


def test_unrelated_pending_signal_does_not_block_unrelated_applicability(
    tmp_path: Path,
) -> None:
    root = _seed(tmp_path)
    durable = root / "data/regulatory/durable_state"
    durable.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        root / "data/regulatory/source_freshness_state.csv",
        durable / "source_freshness_state.csv",
    )
    store = RegulatorySignalStore(durable / "change_signals_state.json")
    signal = ingest_ifrs_alert_message(
        AlertMessage(
            message_id="<pending@ifrs.org>",
            sender="alerts@ifrs.org",
            subject="IFRS S2 amendments",
            received_at="2026-08-12T09:00:00Z",
            label="Regulatory-IFRS",
        )
    )
    assert signal is not None
    store.upsert_signal(signal)
    # Unrelated MOENV portal dependency should not be blocked by IFRS signal.
    gate = get_regulatory_freshness(
        root, required_source_ids=["src_tw_moenv_ghg_registry"]
    )
    assert gate["state"] != "MANUAL_VERIFICATION_REQUIRED"


def test_directly_affected_dependency_can_require_manual_verification(
    tmp_path: Path,
) -> None:
    root = _seed(tmp_path)
    durable = root / "data/regulatory/durable_state"
    durable.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        root / "data/regulatory/source_freshness_state.csv",
        durable / "source_freshness_state.csv",
    )
    for name in [
        "regulatory_change_log.csv",
        "regulatory_conflict_log.csv",
        "persistence_status.json",
    ]:
        src = root / "data/regulatory" / name
        if src.is_file():
            shutil.copy(src, durable / name)
    # Ensure persistence status OK
    (durable / "persistence_status.json").write_text(
        json.dumps(
            {
                "status": "OK",
                "consecutive_persistence_failures": 0,
            }
        ),
        encoding="utf-8",
    )
    store = RegulatorySignalStore(durable / "change_signals_state.json")
    signal = ingest_ifrs_alert_message(
        AlertMessage(
            message_id="<aff@ifrs.org>",
            sender="alerts@ifrs.org",
            subject="IFRS S2 amendments",
            received_at="2026-08-12T09:00:00Z",
            label="Regulatory-IFRS",
        )
    )
    assert signal is not None
    store.upsert_signal(signal)
    gate = get_regulatory_freshness(
        root, required_source_ids=["src_issb_ifrs_s2_2023"]
    )
    assert gate["state"] == "MANUAL_VERIFICATION_REQUIRED"


def test_stage3b_company_profile_still_works() -> None:
    profile = CompanyProfile(
        company_name="Demo Co",
        entity_type="general_listed_company",
        reporting_year=2026,
        paid_in_capital_twd=10_000_000_000,
    )
    assessment = assess_applicability(profile, repo_root=REPO_ROOT)
    assert assessment.obligations
    assert "IFRS" in "".join(
        o.obligation_name for o in assessment.obligations.values()
    )


def test_access_policies_cover_all_sources() -> None:
    sources = load_regulatory_sources(
        REPO_ROOT / "data/reference/regulatory_sources.csv"
    )
    policies = load_source_access_policies(
        REPO_ROOT / "data/reference/source_access_policies.csv"
    )
    assert len(policies) == len(sources)
    enabled = sources[sources["monitor_enabled"].astype(str).str.lower() == "true"]
    for _, row in enabled.iterrows():
        policy = policies[str(row["source_id"])]
        assert policy.automated_access_allowed is True
        assert policy.expects_scheduled_http is True
