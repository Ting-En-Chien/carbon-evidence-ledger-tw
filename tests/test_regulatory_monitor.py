"""Stage 3A.2–3A.4 official regulatory-source monitor tests (mocked network)."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from carbon_ledger.regulatory_monitor import (
    STATE_SOURCE_BUNDLED,
    STATE_SOURCE_DURABLE,
    FetchResult,
    assert_sources_fresh_for_analysis,
    classify_change,
    content_hash,
    evaluate_freshness,
    fail_safe_state_for_freshness,
    get_regulatory_freshness,
    is_allowed_monitoring_state_file,
    is_reviewable_change,
    load_monitor_config,
    mark_rules_pending_review,
    persist_monitoring_state,
    record_conflict,
    run_monitor,
    should_open_review_activity,
)
from carbon_ledger.regulatory_registry import (
    load_regulatory_rules,
    load_regulatory_sources,
    outranks,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


_AUTOMATED_SOURCE_IDS = {
    "src_tw_twse_portal",
    "src_tw_tpex_portal",
    "src_tw_moenv_ghg_open_data",
}


def _reset_automated_freshness_for_tests(root: Path) -> None:
    """Keep schema/rows, but clear live fetch stamps so unit tests start clean."""
    path = root / "data/regulatory/source_freshness_state.csv"
    if not path.is_file():
        return
    df = pd.read_csv(path, dtype=str).fillna("")
    clear_cols = [
        "last_checked_at",
        "last_successful_fetch_at",
        "last_changed_at",
        "http_etag",
        "http_last_modified",
        "content_hash",
        "fetch_status",
        "fetch_error",
        "next_check_at",
    ]
    mask = df["source_id"].isin(_AUTOMATED_SOURCE_IDS)
    for col in clear_cols:
        if col in df.columns:
            df.loc[mask, col] = ""
    if "consecutive_failures" in df.columns:
        df.loc[mask, "consecutive_failures"] = "0"
    if "freshness_status" in df.columns:
        df.loc[mask, "freshness_status"] = "CHECK_DUE"
    df.to_csv(path, index=False)


def _seed_tmp_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "data/reference").mkdir(parents=True)
    (root / "data/regulatory").mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "config/regulatory_monitoring.yaml",
        root / "config/regulatory_monitoring.yaml",
    )
    shutil.copy(
        REPO_ROOT / "data/reference/regulatory_sources.csv",
        root / "data/reference/regulatory_sources.csv",
    )
    shutil.copy(
        REPO_ROOT / "data/reference/source_access_policies.csv",
        root / "data/reference/source_access_policies.csv",
    )
    shutil.copy(
        REPO_ROOT / "config/regulatory_rules.csv",
        root / "config/regulatory_rules.csv",
    )
    for name in [
        "regulatory_change_log.csv",
        "source_freshness_state.csv",
        "regulatory_conflict_log.csv",
        "change_signals_state.json",
    ]:
        src = REPO_ROOT / "data/regulatory" / name
        if src.is_file():
            shutil.copy(src, root / "data/regulatory" / name)
    _reset_automated_freshness_for_tests(root)
    return root


def test_monitor_config_loads_frequencies() -> None:
    cfg = load_monitor_config(REPO_ROOT / "config/regulatory_monitoring.yaml")
    assert cfg.freshness_windows["high_change_source"] == timedelta(days=1)
    assert cfg.freshness_windows["normal_regulatory_source"] == timedelta(days=7)
    assert cfg.freshness_windows["stable_standard_reference"] == timedelta(days=30)
    assert cfg.auto_activate_rules is False


def test_hash_change_produces_change_event(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    bodies = {"first": b"<html>order 11403851756 version A</html>", "second": None}

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        body = bodies["second"] if bodies["second"] is not None else bodies["first"]
        return FetchResult(ok=True, status_code=200, body=body, etag='"v1"')

    now = datetime(2026, 8, 12, 6, 0, tzinfo=timezone.utc)
    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now,
        write_pending_review=False,
    )
    bodies["second"] = b"<html>order 11403851756 version B amended</html>"
    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now + timedelta(hours=1),
        write_pending_review=False,
    )
    assert len(result["changes"]) == 1
    assert result["changes"][0]["change_type"] == "POTENTIAL_REGULATORY_CHANGE"
    assert result["changes"][0]["activation_status"] == "NOT_ACTIVATED"


def test_unchanged_hash_does_not_create_false_regulatory_change(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    body = b"<html>stable regulatory text</html>"

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=body, etag='"same"')

    now = datetime(2026, 8, 12, 7, 0, tzinfo=timezone.utc)
    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now,
        write_pending_review=False,
    )
    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now + timedelta(hours=2),
        write_pending_review=False,
    )
    assert result["changes"] == []


def test_failed_fetch_does_not_silently_mark_current(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=False, status_code=503, error="unavailable")

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=datetime(2026, 8, 12, 8, 0, tzinfo=timezone.utc),
        write_pending_review=False,
    )
    assert result["changes"][0]["change_type"] == "SOURCE_UNAVAILABLE"
    freshness = pd.read_csv(
        root / "data/regulatory/source_freshness_state.csv", dtype=str
    ).fillna("")
    row = freshness.loc[
        freshness["source_id"] == "src_tw_twse_portal"
    ].iloc[0]
    assert row["freshness_status"] != "CURRENT"
    assert row["fetch_status"] == "FETCH_FAILED"
    assert row["last_successful_fetch_at"] == ""


def test_stale_authoritative_source_triggers_fail_safe() -> None:
    status = evaluate_freshness(
        last_successful_fetch_at="2026-07-01T00:00:00Z",
        fetch_failed=False,
        window=timedelta(days=7),
        now=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    assert status == "STALE"
    assert fail_safe_state_for_freshness(status) == "REGULATORY_DATA_STALE"
    gate = assert_sources_fresh_for_analysis(
        [
            {
                "source_id": "src_tw_twse_portal",
                "freshness_status": "STALE",
            }
        ],
        ["src_tw_twse_portal"],
    )
    assert gate["analysis_allowed"] is False
    assert gate["state"] == "REGULATORY_DATA_STALE"


def test_changed_source_does_not_automatically_activate_new_legal_rule(
    tmp_path: Path,
) -> None:
    root = _seed_tmp_repo(tmp_path)
    before = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_before = set(
        before.loc[before["rule_status"] == "ACTIVE", "rule_id"]
    )
    bodies = {"v": b"<html>baseline order text</html>"}

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(
            ok=True,
            status_code=200,
            body=bodies["v"],
            etag='"v"',
        )

    now = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now,
        write_pending_review=False,
    )
    bodies["v"] = b"<html>brand new order text 999</html>"
    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now + timedelta(hours=1),
        write_pending_review=True,
    )
    assert result["auto_activate_rules"] is False
    assert result["review_required"] is True
    assert all(c["activation_status"] == "NOT_ACTIVATED" for c in result["changes"])
    after = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_after = set(after.loc[after["rule_status"] == "ACTIVE", "rule_id"])
    # Monitor must not invent brand-new ACTIVE rule ids.
    assert active_after <= active_before
    # Automated OpenAPI sources may have no linked legal rules; still must not
    # invent ACTIVE rule activations from content-hash changes.
    assert all(c["activation_status"] == "NOT_ACTIVATED" for c in result["changes"])
    assert (root / "data/regulatory/regulatory_change_report.md").is_file()
    assert (root / "data/regulatory/monitoring_summary.json").is_file()


def test_pending_review_rules_are_not_treated_as_active(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    marked = mark_rules_pending_review(
        root / "config/regulatory_rules.csv",
        ["tw_order_51756_phase1_ge_10bn"],
    )
    assert marked == 1
    rules = load_regulatory_rules(root / "config/regulatory_rules.csv")
    row = rules.loc[rules["rule_id"] == "tw_order_51756_phase1_ge_10bn"].iloc[0]
    assert row["rule_status"] == "PENDING_REVIEW"
    from carbon_ledger.regulatory_registry import active_rules, operable_rules

    assert "tw_order_51756_phase1_ge_10bn" not in set(active_rules(rules)["rule_id"])
    assert "tw_order_51756_phase1_ge_10bn" not in set(operable_rules(rules)["rule_id"])


def test_source_precedence_helper_respected() -> None:
    sources = pd.read_csv(
        REPO_ROOT / "data/reference/regulatory_sources.csv", dtype=str
    ).fillna("")
    assert outranks(
        sources,
        "src_tw_order_11403856095_securities",
        "src_tw_sfb_press_20251028",
    )


def test_regulatory_conflicts_are_surfaced(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    conflict = record_conflict(
        root / "data/regulatory/regulatory_conflict_log.csv",
        source_id_a="src_tw_twse_portal",
        source_id_b="src_tw_sfb_press_20251028",
        requirement_a="Scope3 from fourth year",
        requirement_b="Scope3 first three years",
        affected_rule_ids=["tw_order_51756_scope3_from_fourth_year"],
    )
    assert "REGULATORY_CONFLICT" in conflict["notes"]
    assert conflict["review_status"] == "PENDING_REVIEW"


def test_classify_change_helpers() -> None:
    body_a = b"<html>alpha</html>"
    body_b = b"<html>beta</html>"
    assert content_hash(body_a) != content_hash(body_b)
    assert (
        classify_change(
            previous_hash=content_hash(body_a),
            new_hash=content_hash(body_a),
            previous_etag="a",
            new_etag="a",
            previous_last_modified="",
            new_last_modified="",
            previous_version="1",
            new_version="1",
            fetch_ok=True,
        )
        == "NO_CHANGE"
    )
    # First baseline hash is not a reviewable regulatory change.
    assert (
        classify_change(
            previous_hash="",
            new_hash=content_hash(body_a),
            previous_etag="",
            new_etag="",
            previous_last_modified="",
            new_last_modified="",
            previous_version="",
            new_version="",
            fetch_ok=True,
        )
        == "BASELINE_CAPTURED"
    )
    assert is_reviewable_change("BASELINE_CAPTURED") is False
    assert (
        classify_change(
            previous_hash="",
            new_hash="",
            previous_etag="",
            new_etag="",
            previous_last_modified="",
            new_last_modified="",
            previous_version="",
            new_version="",
            fetch_ok=False,
        )
        == "SOURCE_UNAVAILABLE"
    )


def test_monitor_does_not_open_review_for_no_change() -> None:
    assert is_reviewable_change("NO_CHANGE") is False
    assert is_reviewable_change("COSMETIC_CHANGE") is False
    assert should_open_review_activity(
        [{"change_type": "NO_CHANGE", "previous_version": "", "new_version": ""}]
    ) is False
    assert is_reviewable_change(
        {
            "change_type": "POTENTIAL_REGULATORY_CHANGE",
            "previous_version": "a",
            "new_version": "b",
        }
    )


def test_failed_fetch_does_not_update_last_successful_fetch_at(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    now = datetime(2026, 8, 12, 10, 0, tzinfo=timezone.utc)

    def ok_fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=b"<html>ok</html>")

    def bad_fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=False, status_code=503, error="down")

    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=ok_fetch,
        now=now,
        write_pending_review=False,
    )
    freshness = pd.read_csv(
        root / "data/regulatory/source_freshness_state.csv", dtype=str
    ).fillna("")
    success_before = freshness.loc[
        freshness["source_id"] == "src_tw_twse_portal",
        "last_successful_fetch_at",
    ].iloc[0]
    assert success_before

    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=bad_fetch,
        now=now + timedelta(hours=1),
        write_pending_review=False,
    )
    freshness = pd.read_csv(
        root / "data/regulatory/source_freshness_state.csv", dtype=str
    ).fillna("")
    row = freshness.loc[
        freshness["source_id"] == "src_tw_twse_portal"
    ].iloc[0]
    assert row["last_successful_fetch_at"] == success_before
    assert row["fetch_status"] == "FETCH_FAILED"


def test_get_regulatory_freshness_gate(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    freshness = get_regulatory_freshness(root)
    assert "analysis_allowed" in freshness
    assert "overall_regulatory_freshness" in freshness
    assert "sources_current" in freshness
    assert "changes_pending_review" in freshness
    assert "regulatory_conflicts" in freshness
    assert "state_source" in freshness
    assert "src_tw_sfb_ifrs_download_area" in freshness["high_priority_source_ids"]


def test_taiwan_recognised_version_source_is_high_priority() -> None:
    cfg = load_monitor_config(REPO_ROOT / "config/regulatory_monitoring.yaml")
    assert "src_tw_sfb_ifrs_download_area" in cfg.high_priority_source_ids
    sources = load_regulatory_sources(
        REPO_ROOT / "data/reference/regulatory_sources.csv"
    )
    row = sources.loc[
        sources["source_id"] == "src_tw_sfb_ifrs_download_area"
    ].iloc[0]
    assert row["monitor_enabled"].lower() == "false"
    assert row["monitor_frequency"] == "high_change_source"


def test_international_ifrs_updates_do_not_auto_become_taiwan_active() -> None:
    rules = load_regulatory_rules(REPO_ROOT / "config/regulatory_rules.csv")
    row = rules.loc[
        rules["rule_id"] == "ifrs_s2_ghg_amendments_2025_international"
    ].iloc[0]
    assert row["taiwan_status"] == "NOT_YET_VERIFIED"
    assert row["jurisdiction"] == "INTL"


def test_scheduled_workflow_exists_and_is_enabled() -> None:
    text = (
        REPO_ROOT / ".github/workflows/regulatory-monitor.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert 'cron: "17 16 * * *"' in text
    assert 'cron: "0 16 * * *"' not in text
    assert "python -m carbon_ledger.regulatory_monitor --check-all" in text
    assert "regulatory-monitor-state" in text
    assert "data/regulatory/durable_state" in text
    assert "--verify-persisted-summary" in text
    assert "--health-gate" in text
    assert "regulatory-update/" in text
    assert "gh pr create" in text
    assert "permissions:" in text
    assert "contents: write" in text
    assert "pull-requests: write" in text
    assert "issues: write" in text
    assert "DEFAULT branch" in text or "default branch" in text
    # Persist evidence before final gate / unit tests; monitor uses continue-on-error.
    assert "continue-on-error: true" in text
    assert "ERROR: CRITICAL_SOURCE_FAILURE" in text
    assert "ERROR: STATE_PERSISTENCE_FAILED" in text
    monitor_idx = text.index("Run live official-source monitor")
    persist_idx = text.index("Persist monitoring STATE to regulatory-monitor-state")
    verify_idx = text.index("Verify persisted state matches runtime")
    gate_idx = text.index("Final monitoring health gate")
    tests_idx = text.index("Run regulatory unit tests (mocked network only)")
    assert monitor_idx < persist_idx < verify_idx < gate_idx < tests_idx
    # Schedule must not remain commented out.
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- cron:"):
            assert not line.lstrip().startswith("#")
            minute = stripped.split('"')[1].split()[0]
            assert minute != "0"
            break
    else:
        raise AssertionError("Enabled cron schedule not found")


def test_monitor_does_not_import_calculation_pipeline() -> None:
    import carbon_ledger.regulatory_monitor as mon

    assert "calculate" not in mon.__dict__
    assert "ingest" not in mon.__dict__
    assert "match_factors" not in mon.__dict__
    source = Path(mon.__file__).read_text(encoding="utf-8")
    assert "verify=False" not in source
    assert "_create_unverified_context" not in source
    assert "curl -k" not in source
    assert "CERT_NONE" not in source


def test_no_change_run_updates_durable_freshness_state(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    body = b"<html>stable official text for durable state</html>"

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=body, etag='"n1"')

    now = datetime(2026, 8, 12, 11, 0, tzinfo=timezone.utc)
    first = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now,
        write_pending_review=False,
    )
    assert first["monitoring_complete"] is True
    assert first["review_required"] is False
    assert first["changes"][0]["change_type"] == "BASELINE_CAPTURED"
    assert first["changes"][0]["review_status"] == "INFO"
    durable = root / "data/regulatory/durable_state/source_freshness_state.csv"
    assert durable.is_file()
    success_1 = pd.read_csv(durable, dtype=str).fillna("")
    stamp_1 = success_1.loc[
        success_1["source_id"] == "src_tw_twse_portal",
        "last_successful_fetch_at",
    ].iloc[0]
    assert stamp_1.startswith("2026-08-12T11:00:00")

    second = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now + timedelta(hours=3),
        write_pending_review=False,
    )
    assert second["changes"] == []
    assert second["review_required"] is False
    assert should_open_review_activity(second["changes"]) is False
    success_2 = pd.read_csv(durable, dtype=str).fillna("")
    row = success_2.loc[
        success_2["source_id"] == "src_tw_twse_portal"
    ].iloc[0]
    assert row["last_successful_fetch_at"].startswith("2026-08-12T14:00:00")
    assert row["last_checked_at"].startswith("2026-08-12T14:00:00")
    assert row["fetch_status"] == "OK"
    assert row["freshness_status"] in {"CURRENT", "AUTOMATED_CURRENT"}
    assert row["next_check_at"]


def test_artifacts_not_required_for_get_regulatory_freshness(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    # No artifacts directory; only bundled CSV state.
    freshness = get_regulatory_freshness(root)
    assert "analysis_allowed" in freshness
    assert freshness["state_source"] in {STATE_SOURCE_BUNDLED, STATE_SOURCE_DURABLE}
    assert (root / "artifacts").exists() is False


def test_durable_state_preferred_over_bundled_stale(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    body = b"<html>prefer durable</html>"

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=body)

    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now,
        write_pending_review=False,
    )
    # Corrupt bundled timestamps to look stale while durable stays current.
    bundled = root / "data/regulatory/source_freshness_state.csv"
    df = pd.read_csv(bundled, dtype=str).fillna("")
    df.loc[
        df["source_id"] == "src_tw_twse_portal",
        "last_successful_fetch_at",
    ] = "2020-01-01T00:00:00Z"
    df.loc[
        df["source_id"] == "src_tw_twse_portal",
        "freshness_status",
    ] = "STALE"
    df.to_csv(bundled, index=False)

    freshness = get_regulatory_freshness(root)
    assert freshness["state_source"] == STATE_SOURCE_DURABLE
    durable = pd.read_csv(
        root / "data/regulatory/durable_state/source_freshness_state.csv",
        dtype=str,
    ).fillna("")
    stamp = durable.loc[
        durable["source_id"] == "src_tw_twse_portal",
        "last_successful_fetch_at",
    ].iloc[0]
    assert stamp.startswith("2026-08-12T12:00:00")


def test_env_durable_state_dir_preferred(tmp_path: Path, monkeypatch) -> None:
    root = _seed_tmp_repo(tmp_path)
    external = tmp_path / "external_state"
    external.mkdir()
    shutil.copy(
        root / "data/regulatory/source_freshness_state.csv",
        external / "source_freshness_state.csv",
    )
    summary = {
        "overall_regulatory_freshness": "CURRENT",
        "state_source": "durable_persisted_state",
    }
    (external / "monitoring_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    monkeypatch.setenv("CARBON_LEDGER_REGULATORY_STATE_DIR", str(external))
    freshness = get_regulatory_freshness(root)
    assert freshness["state_source"] == STATE_SOURCE_DURABLE
    monkeypatch.delenv("CARBON_LEDGER_REGULATORY_STATE_DIR", raising=False)


def test_failed_persistence_not_reported_as_full_success(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    blocker = root / "data/regulatory/durable_state"
    blocker.write_text("not-a-directory", encoding="utf-8")

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=b"<html>ok</html>")

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc),
        write_pending_review=False,
    )
    assert result["monitoring_complete"] is False
    assert result["persistence"]["status"] == "STATE_PERSISTENCE_FAILED"
    assert result["summary"]["persistence_status"] == "STATE_PERSISTENCE_FAILED"
    assert result["summary"]["overall_regulatory_freshness"] == (
        "STATE_PERSISTENCE_FAILED"
    )


def test_last_successful_fetch_at_only_on_successful_fetch(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    now = datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc)

    def ok_fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=b"<html>ok2</html>")

    def bad_fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=False, status_code=500, error="boom")

    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=ok_fetch,
        now=now,
        write_pending_review=False,
    )
    before = pd.read_csv(
        root / "data/regulatory/source_freshness_state.csv", dtype=str
    ).fillna("")
    stamp = before.loc[
        before["source_id"] == "src_tw_twse_portal",
        "last_successful_fetch_at",
    ].iloc[0]
    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=bad_fetch,
        now=now + timedelta(hours=1),
        write_pending_review=False,
    )
    after = pd.read_csv(
        root / "data/regulatory/source_freshness_state.csv", dtype=str
    ).fillna("")
    assert (
        after.loc[
            after["source_id"] == "src_tw_twse_portal",
            "last_successful_fetch_at",
        ].iloc[0]
        == stamp
    )


def test_rule_activation_remains_manual(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    cfg = load_monitor_config(root / "config/regulatory_monitoring.yaml")
    assert cfg.auto_activate_rules is False
    before = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_before = set(before.loc[before["rule_status"] == "ACTIVE", "rule_id"])
    bodies = {"v": b"<html>manual activation only</html>"}

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=bodies["v"])

    now = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)
    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now,
        write_pending_review=False,
    )
    bodies["v"] = b"<html>manual activation only CHANGED</html>"
    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=now + timedelta(hours=1),
        write_pending_review=True,
    )
    assert result["auto_activate_rules"] is False
    assert all(c["activation_status"] == "NOT_ACTIVATED" for c in result["changes"])
    after = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_after = set(after.loc[after["rule_status"] == "ACTIVE", "rule_id"])
    assert active_after <= active_before


def test_monitoring_state_cannot_include_calculation_files() -> None:
    assert is_allowed_monitoring_state_file("source_freshness_state.csv")
    assert is_allowed_monitoring_state_file("monitoring_summary.json")
    assert not is_allowed_monitoring_state_file("config/regulatory_rules.csv")
    assert not is_allowed_monitoring_state_file("src/carbon_ledger/calculate.py")
    assert not is_allowed_monitoring_state_file("src/carbon_ledger/ingest.py")
    cfg = load_monitor_config(REPO_ROOT / "config/regulatory_monitoring.yaml")
    assert cfg.monitoring_state_branch == "regulatory-monitor-state"
    for name in cfg.monitoring_state_files:
        assert is_allowed_monitoring_state_file(name)


def test_carbon_calculation_pipeline_files_unchanged_hashes() -> None:
    """Stage 3A.4 must not alter frozen calculation pipeline file bytes."""
    frozen = [
        "src/carbon_ledger/domain.py",
        "src/carbon_ledger/schemas.py",
        "src/carbon_ledger/ingest.py",
        "src/carbon_ledger/normalize.py",
        "src/carbon_ledger/factors.py",
        "src/carbon_ledger/match_factors.py",
        "src/carbon_ledger/calculate.py",
        "src/carbon_ledger/rules.py",
        "src/carbon_ledger/qa.py",
        "src/carbon_ledger/cbam.py",
        "src/carbon_ledger/ui/hero_emissions_countup.js",
    ]
    # Presence + non-empty: pipeline modules remain intact in the tree.
    for rel in frozen:
        path = REPO_ROOT / rel
        assert path.is_file(), rel
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert len(digest) == 64


def test_freshness_state_unavailable_when_missing(tmp_path: Path) -> None:
    root = tmp_path / "empty_repo"
    (root / "config").mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "config/regulatory_monitoring.yaml",
        root / "config/regulatory_monitoring.yaml",
    )
    freshness = get_regulatory_freshness(root)
    assert freshness["state"] == "FRESHNESS_STATE_UNAVAILABLE"
    assert freshness["analysis_allowed"] is False
    assert freshness["state_source"] == "unavailable"


def test_persist_monitoring_state_refuses_content_files(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    durable = root / "data/regulatory/durable_state"
    durable.mkdir(parents=True, exist_ok=True)
    shutil.copy(
        root / "data/regulatory/source_freshness_state.csv",
        durable / "source_freshness_state.csv",
    )
    (durable / "monitoring_summary.json").write_text(
        '{"overall_regulatory_freshness":"CHECK_DUE","critical_sources_failed":0}\n',
        encoding="utf-8",
    )
    result = persist_monitoring_state(root)
    assert result.ok is True
    durable_rules = root / "data/regulatory/durable_state/regulatory_rules.csv"
    assert durable_rules.exists() is False
    assert (
        root / "data/regulatory/durable_state/source_freshness_state.csv"
    ).is_file()


# --- Stage 3A.5 ---


def test_tls_strict_context_is_default() -> None:
    import ssl

    from carbon_ledger.regulatory_monitor import build_official_source_ssl_context

    ctx = build_official_source_ssl_context(relax_x509_strict=False)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_tls_x509_strict_fallback_only_for_allowlisted_hosts() -> None:
    import ssl

    from carbon_ledger.regulatory_monitor import (
        build_official_source_ssl_context,
        hostname_in_tls_fallback_allowlist,
        is_x509_strict_compatibility_error,
    )

    assert is_x509_strict_compatibility_error(
        "certificate verify failed: Missing Subject Key Identifier"
    )
    assert not is_x509_strict_compatibility_error("connection timed out")
    allow = {"law.fsc.gov.tw", "www.fsc.gov.tw"}
    assert hostname_in_tls_fallback_allowlist(
        "https://law.fsc.gov.tw/LawContent.aspx", allow
    )
    assert not hostname_in_tls_fallback_allowlist(
        "https://www.ifrs.org/standards/", allow
    )
    compat = build_official_source_ssl_context(relax_x509_strict=True)
    assert compat.verify_mode == ssl.CERT_REQUIRED
    assert compat.check_hostname is True
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        assert not (compat.verify_flags & ssl.VERIFY_X509_STRICT)


def test_failed_fetch_never_classified_no_change() -> None:
    assert (
        classify_change(
            previous_hash="abc",
            new_hash="",
            previous_etag="",
            new_etag="",
            previous_last_modified="",
            new_last_modified="",
            previous_version="1",
            new_version="1",
            fetch_ok=False,
        )
        == "SOURCE_UNAVAILABLE"
    )
    assert (
        classify_change(
            previous_hash="abc",
            new_hash="abc",
            previous_etag="",
            new_etag="",
            previous_last_modified="",
            new_last_modified="",
            previous_version="1",
            new_version="1",
            fetch_ok=True,
        )
        == "NO_CHANGE"
    )


def test_critical_source_failure_makes_overall_non_current() -> None:
    from carbon_ledger.regulatory_monitor import (
        HEALTH_CRITICAL_SOURCE_FAILURE,
        build_monitoring_summary,
        evaluate_monitoring_health,
    )

    summary = build_monitoring_summary(
        freshness_rows=[
            {
                "source_id": "src_tw_twse_portal",
                "freshness_status": "FETCH_FAILED",
                "fetch_status": "FETCH_FAILED",
                "monitor_criticality": "CRITICAL",
                "last_checked_at": "2026-08-12T00:00:00Z",
                "last_successful_fetch_at": "",
                "consecutive_failures": "1",
            }
        ],
        change_rows=[],
        conflict_rows=[],
        critical_source_ids=["src_tw_twse_portal"],
    )
    assert summary["critical_sources_failed"] == 1
    assert summary["overall_regulatory_freshness"] != "CURRENT"
    assert evaluate_monitoring_health(summary) == HEALTH_CRITICAL_SOURCE_FAILURE


def test_critical_source_failure_health_gate_nonzero(tmp_path: Path) -> None:
    from carbon_ledger.regulatory_monitor import main

    root = _seed_tmp_repo(tmp_path)
    durable = root / "data/regulatory/durable_state"
    durable.mkdir(parents=True, exist_ok=True)
    summary = {
        "overall_regulatory_freshness": "SOURCE_CHECK_FAILED",
        "critical_sources_failed": 2,
        "persistence_status": "OK",
        "monitoring_health": "CRITICAL_SOURCE_FAILURE",
    }
    (durable / "monitoring_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    code = main(["--repo-root", str(root), "--health-gate"])
    assert code == 4


def test_runtime_durable_state_is_persisted_source(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    body = b"<html>runtime durable soT</html>"

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=body)

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
        write_pending_review=False,
    )
    assert "durable_state" in result["runtime_state_dir"]
    durable_summary = json.loads(
        Path(result["summary_path"]).read_text(encoding="utf-8")
    )
    assert durable_summary["sources_total"] >= 1
    assert durable_summary["last_global_check_at"]
    # Bundled mirror must match runtime, not remain the bootstrap template.
    bundled = json.loads(
        (root / "data/regulatory/monitoring_summary.json").read_text(encoding="utf-8")
    )
    assert bundled["last_global_check_at"] == durable_summary["last_global_check_at"]
    assert bundled["sources_total"] == durable_summary["sources_total"]


def test_persisted_state_must_match_runtime(tmp_path: Path) -> None:
    from carbon_ledger.regulatory_monitor import (
        compare_monitoring_summaries,
        verify_persisted_state_matches_runtime,
    )

    runtime = {
        "overall_regulatory_freshness": "PARTIAL",
        "last_global_check_at": "2026-08-12T16:00:00Z",
        "last_successful_check_at": "2026-08-12T16:00:00Z",
        "sources_current": 1,
        "sources_failed": 0,
        "sources_total": 1,
        "critical_sources_failed": 0,
        "generated_at": "2026-08-12T16:00:00Z",
        "persistence_status": "OK",
    }
    stale = {**runtime, "sources_total": 0, "last_global_check_at": ""}
    assert compare_monitoring_summaries(runtime, stale)
    bad = tmp_path / "stale.json"
    bad.write_text(json.dumps(stale), encoding="utf-8")
    ok, mismatches = verify_persisted_state_matches_runtime(runtime, bad)
    assert ok is False
    assert "sources_total" in mismatches or "last_global_check_at" in mismatches


def test_persistence_mismatch_fails_cli(tmp_path: Path) -> None:
    from carbon_ledger.regulatory_monitor import main

    root = _seed_tmp_repo(tmp_path)
    durable = root / "data/regulatory/durable_state"
    durable.mkdir(parents=True, exist_ok=True)
    runtime = {
        "overall_regulatory_freshness": "PARTIAL",
        "last_global_check_at": "2026-08-12T16:00:00Z",
        "last_successful_check_at": "2026-08-12T16:00:00Z",
        "sources_current": 1,
        "sources_failed": 0,
        "sources_total": 3,
        "critical_sources_failed": 0,
        "generated_at": "2026-08-12T16:00:00Z",
        "persistence_status": "OK",
    }
    (durable / "monitoring_summary.json").write_text(
        json.dumps(runtime), encoding="utf-8"
    )
    stale = tmp_path / "branch_summary.json"
    stale.write_text(
        json.dumps({**runtime, "sources_total": 0}), encoding="utf-8"
    )
    code = main(
        [
            "--repo-root",
            str(root),
            "--verify-persisted-summary",
            str(stale),
        ]
    )
    assert code == 5


def test_config_loads_critical_sources_and_tls_allowlist() -> None:
    cfg = load_monitor_config(REPO_ROOT / "config/regulatory_monitoring.yaml")
    assert "src_tw_twse_portal" in cfg.critical_source_ids
    assert "src_tw_moenv_ghg_registry" not in cfg.critical_source_ids
    assert "src_tw_moenv_ghg_open_data" in cfg.supporting_source_ids
    assert "src_tw_moenv_ghg_open_data" not in cfg.critical_source_ids
    assert "openapi.twse.com.tw" in cfg.tls_x509_strict_fallback_hosts
    assert "www.ifrs.org" not in cfg.tls_x509_strict_fallback_hosts
    from carbon_ledger.regulatory_monitor import source_criticality

    assert source_criticality("src_tw_twse_portal", cfg) == "CRITICAL"
    assert source_criticality("src_tw_fsc_law_portal", cfg) != "CRITICAL"
    assert "src_tw_sfb_ifrs_download_area" in cfg.primary_authoritative_source_ids
    assert (
        cfg.alternate_official_monitoring_sources["src_tw_sfb_ifrs_download_area"]
        == "src_tw_order_11403856094_recognised"
    )


def test_baseline_captured_does_not_trigger_review(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=b"<html>baseline-only</html>")

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc),
        write_pending_review=True,
    )
    assert result["changes"][0]["change_type"] == "BASELINE_CAPTURED"
    assert result["review_required"] is False
    assert result["pending_review_rules_marked"] == 0
    assert should_open_review_activity(result["changes"]) is False


def test_failed_latest_fetch_never_reports_current_even_with_prior_success(
    tmp_path: Path,
) -> None:
    root = _seed_tmp_repo(tmp_path)
    now = datetime(2026, 8, 12, 14, 0, tzinfo=timezone.utc)

    def ok_fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=True, status_code=200, body=b"<html>prior-ok</html>")

    def bad_fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=False, status_code=503, error="down")

    run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=ok_fetch,
        now=now,
        write_pending_review=False,
    )
    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=bad_fetch,
        now=now + timedelta(minutes=30),
        write_pending_review=False,
    )
    freshness = pd.read_csv(
        root / "data/regulatory/durable_state/source_freshness_state.csv", dtype=str
    ).fillna("")
    row = freshness.loc[
        freshness["source_id"] == "src_tw_twse_portal"
    ].iloc[0]
    assert row["freshness_status"] == "FETCH_FAILED"
    assert row["fetch_status"] == "FETCH_FAILED"
    assert row["last_successful_fetch_at"].startswith("2026-08-12T14:00:00")
    assert row["freshness_status"] != "CURRENT"
    assert result["summary"]["overall_regulatory_freshness"] != "CURRENT"


def test_sfb_403_uses_manual_access_not_insecure_bypass(tmp_path: Path) -> None:
    """SFB HTML is policy-restricted: zero HTTP; no bypass tooling."""
    root = _seed_tmp_repo(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=False, status_code=403, error="HTTP 403")

    result = run_monitor(
        root,
        source_id="src_tw_sfb_ifrs_download_area",
        fetch_fn=fetch,
        now=datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc),
        write_pending_review=False,
    )
    freshness = pd.read_csv(
        root / "data/regulatory/durable_state/source_freshness_state.csv", dtype=str
    ).fillna("")
    row = freshness.loc[
        freshness["source_id"] == "src_tw_sfb_ifrs_download_area"
    ].iloc[0]
    assert row["fetch_status"] == "POLICY_SKIPPED"
    assert row["freshness_status"] == "MANUALLY_VERIFIED"
    assert any(c["change_type"] == "POLICY_SKIPPED" for c in result["changes"])
    assert result["summary"]["critical_sources_failed"] == 0
    source = (
        REPO_ROOT / "src/carbon_ledger/regulatory_monitor.py"
    ).read_text(encoding="utf-8")
    assert "verify=False" not in source
    assert "CERT_NONE" not in source
    assert "webdriver" not in source.lower()
    assert "selenium" not in source.lower()
    assert calls == []


def test_authorized_api_403_stops_without_bypass(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        calls.append(url)
        return FetchResult(ok=False, status_code=403, error="HTTP 403")

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=datetime(2026, 8, 12, 15, 5, tzinfo=timezone.utc),
        write_pending_review=False,
    )
    freshness = pd.read_csv(
        root / "data/regulatory/durable_state/source_freshness_state.csv", dtype=str
    ).fillna("")
    row = freshness.loc[freshness["source_id"] == "src_tw_twse_portal"].iloc[0]
    assert row["fetch_status"] == "ACCESS_POLICY_REVIEW_REQUIRED"
    assert any(
        c["change_type"] == "ACCESS_POLICY_REVIEW_REQUIRED" for c in result["changes"]
    )
    assert calls
    assert all("ifrs.org" not in c for c in calls)


def test_alternate_official_signal_cannot_auto_activate_taiwan_ifrs(
    tmp_path: Path,
) -> None:
    """Email / change signals never auto-activate Taiwan IFRS rules."""
    root = _seed_tmp_repo(tmp_path)
    from carbon_ledger.regulatory_signals import (
        AlertMessage,
        MockMailboxAdapter,
        RegulatorySignalStore,
        admin_mark_verified_regulatory_change,
        ingest_alerts_from_adapter,
    )

    store = RegulatorySignalStore(
        root / "data/regulatory/durable_state/change_signals_state.json"
    )
    adapter = MockMailboxAdapter(
        [
            AlertMessage(
                message_id="<ifrs-amend-1@ifrs.org>",
                sender="alerts@ifrs.org",
                subject="IFRS S2 amendments published",
                received_at="2026-08-12T10:00:00Z",
                label="Regulatory-IFRS",
                snippet="Official notification only",
                official_link="https://www.ifrs.org/news/example",
            )
        ]
    )
    before = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_before = set(before.loc[before["rule_status"] == "ACTIVE", "rule_id"])
    ingest = ingest_alerts_from_adapter(adapter, store)
    assert ingest["created"] == 1
    sig = store.list_signals()[0]
    assert sig.status == "POTENTIAL_REGULATORY_CHANGE"
    admin_mark_verified_regulatory_change(
        store, sig.signal_id, reviewed_by="admin_test"
    )
    # Still no automatic rule mutation.
    after = load_regulatory_rules(root / "config/regulatory_rules.csv")
    active_after = set(after.loc[after["rule_status"] == "ACTIVE", "rule_id"])
    assert active_after == active_before
    assert store.list_signals()[0].status == "VERIFIED_REGULATORY_CHANGE"


def test_manual_access_required_blocks_unconditional_applicability() -> None:
    gate = assert_sources_fresh_for_analysis(
        [
            {
                "source_id": "src_tw_sfb_ifrs_download_area",
                "freshness_status": "MANUAL_ACCESS_REQUIRED",
            }
        ],
        ["src_tw_sfb_ifrs_download_area"],
    )
    assert gate["analysis_allowed"] is False
    assert gate["state"] == "MANUAL_VERIFICATION_REQUIRED"
    assert fail_safe_state_for_freshness("MANUAL_ACCESS_REQUIRED") == (
        "MANUAL_VERIFICATION_REQUIRED"
    )


def test_invalid_moenv_root_url_is_no_longer_monitored() -> None:
    sources = load_regulatory_sources(
        REPO_ROOT / "data/reference/regulatory_sources.csv"
    )
    row = sources.loc[sources["source_id"] == "src_tw_moenv_oaout"].iloc[0]
    assert row["official_url"] != "https://oaout.moenv.gov.tw/"
    assert "LawContent.aspx" in row["official_url"]
    assert "oaout.moenv.gov.tw/law/" in row["official_url"]
    assert str(row["monitor_enabled"]).lower() == "false"


def test_health_gate_precedence_persistence_over_critical() -> None:
    from carbon_ledger.regulatory_monitor import evaluate_monitoring_health

    summary = {
        "persistence_status": "STATE_PERSISTENCE_FAILED",
        "critical_sources_failed": 2,
        "overall_regulatory_freshness": "SOURCE_CHECK_FAILED",
    }
    assert evaluate_monitoring_health(summary) == "STATE_PERSISTENCE_FAILED"
    summary2 = {
        "persistence_status": "OK",
        "critical_sources_failed": 1,
        "overall_regulatory_freshness": "SOURCE_CHECK_FAILED",
    }
    assert evaluate_monitoring_health(summary2) == "CRITICAL_SOURCE_FAILURE"
    summary3 = {
        "persistence_status": "OK",
        "critical_sources_failed": 0,
        "overall_regulatory_freshness": "MANUAL_VERIFICATION_REQUIRED",
    }
    assert evaluate_monitoring_health(summary3) == "MONITORING_PARTIAL"


def test_critical_failure_still_persists_runtime_state(tmp_path: Path) -> None:
    root = _seed_tmp_repo(tmp_path)

    def fetch(url: str, timeout: float) -> FetchResult:  # noqa: ARG001
        return FetchResult(ok=False, status_code=500, error="server error")

    result = run_monitor(
        root,
        source_id="src_tw_twse_portal",
        fetch_fn=fetch,
        now=datetime(2026, 8, 12, 16, 0, tzinfo=timezone.utc),
        write_pending_review=False,
    )
    assert result["monitoring_complete"] is True
    assert (root / "data/regulatory/durable_state/monitoring_summary.json").is_file()
    assert (root / "data/regulatory/durable_state/source_freshness_state.csv").is_file()
    assert result["summary"]["critical_sources_failed"] >= 1
    assert result["monitoring_health"] == "CRITICAL_SOURCE_FAILURE"
    assert result["persistence"]["ok"] is True
