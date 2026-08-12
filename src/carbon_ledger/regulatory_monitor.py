"""Official regulatory-source monitor (Stage 3A.5).

Fetch → record metadata → compare → detect change → create change record →
classify → flag affected rules for review → persist durable monitoring STATE.

Does NOT auto-activate legal rules. Does NOT modify the carbon calculation
pipeline. Network logic is injectable for unit tests.

REGULATORY CONTENT (rules / source definitions) is separate from MONITORING
STATE (freshness timestamps, hashes, summaries). Automatic monitoring may
update STATE only.

TLS note (Python 3.13+): default fetch uses strict create_default_context().
If and only if an allowlisted official Taiwan host fails with an X509 strict
compatibility error (e.g. Missing Subject Key Identifier), retry with CA +
hostname verification still enabled but VERIFY_X509_STRICT cleared. Never
disable certificate verification or hostname checks.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import ssl
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from carbon_ledger.regulatory_registry import (
    FAIL_SAFE_STATES,
    active_rules,
    load_regulatory_rules,
    load_regulatory_sources,
    operable_rules,
    outranks,
)

REVIEWABLE_CHANGE_TYPES = frozenset(
    {
        "POTENTIAL_REGULATORY_CHANGE",
        "CONFIRMED_REGULATORY_CHANGE",
        "REGULATORY_CONFLICT",
    }
)

STATE_SOURCE_DURABLE = "durable_persisted_state"
STATE_SOURCE_BUNDLED = "bundled_fallback"
STATE_SOURCE_UNAVAILABLE = "unavailable"

CRITICALITY_CRITICAL = "CRITICAL"
CRITICALITY_IMPORTANT = "IMPORTANT"
CRITICALITY_SUPPLEMENTARY = "SUPPLEMENTARY"

HEALTH_MONITORING_CURRENT = "MONITORING_CURRENT"
HEALTH_MONITORING_PARTIAL = "MONITORING_PARTIAL"
HEALTH_CRITICAL_SOURCE_FAILURE = "CRITICAL_SOURCE_FAILURE"
HEALTH_STATE_PERSISTENCE_FAILED = "STATE_PERSISTENCE_FAILED"
HEALTH_STATE_PERSISTENCE_MISMATCH = "STATE_PERSISTENCE_MISMATCH"

SUMMARY_INTEGRITY_KEYS = (
    "overall_regulatory_freshness",
    "last_global_check_at",
    "last_successful_check_at",
    "sources_current",
    "sources_failed",
    "sources_total",
    "critical_sources_failed",
    "generated_at",
    "persistence_status",
)

DEFAULT_MONITORING_STATE_FILES = (
    "source_freshness_state.csv",
    "monitoring_summary.json",
    "regulatory_change_log.csv",
    "regulatory_conflict_log.csv",
    "persistence_status.json",
    "regulatory_change_report.md",
)

# Never auto-persist these as monitoring state (legal / calculation CONTENT).
FORBIDDEN_STATE_PATH_FRAGMENTS = (
    "config/regulatory_rules.csv",
    "data/reference/regulatory_sources.csv",
    "src/carbon_ledger/calculate.py",
    "src/carbon_ledger/ingest.py",
    "src/carbon_ledger/normalize.py",
    "src/carbon_ledger/factors.py",
    "src/carbon_ledger/match_factors.py",
    "src/carbon_ledger/rules.py",
    "src/carbon_ledger/qa.py",
    "src/carbon_ledger/cbam.py",
    "src/carbon_ledger/domain.py",
    "src/carbon_ledger/schemas.py",
)

CHANGE_TYPES = {
    "NO_CHANGE",
    "BASELINE_CAPTURED",
    "COSMETIC_CHANGE",
    "METADATA_CHANGE",
    "POTENTIAL_REGULATORY_CHANGE",
    "CONFIRMED_REGULATORY_CHANGE",
    "SOURCE_UNAVAILABLE",
    "MANUAL_ACCESS_REQUIRED",
    "ALTERNATE_OFFICIAL_SIGNAL",
    "REGULATORY_CONFLICT",
}

CHANGE_LOG_COLUMNS = [
    "change_id",
    "source_id",
    "detected_at",
    "previous_hash",
    "new_hash",
    "change_type",
    "previous_version",
    "new_version",
    "affected_rule_ids",
    "review_status",
    "reviewed_by",
    "reviewed_at",
    "activation_status",
    "notes",
]

FRESHNESS_COLUMNS = [
    "source_id",
    "last_checked_at",
    "last_successful_fetch_at",
    "last_changed_at",
    "http_etag",
    "http_last_modified",
    "content_hash",
    "fetch_status",
    "fetch_error",
    "consecutive_failures",
    "freshness_status",
    "next_check_at",
    "current_source_version",
    "previous_source_version",
    "monitor_criticality",
]

CONFLICT_COLUMNS = [
    "conflict_id",
    "detected_at",
    "source_id_a",
    "source_id_b",
    "requirement_a",
    "requirement_b",
    "publication_date_a",
    "publication_date_b",
    "effective_date_a",
    "effective_date_b",
    "affected_rule_ids",
    "review_status",
    "notes",
]

FetchFn = Callable[[str, float], "FetchResult"]


@dataclass
class FetchResult:
    ok: bool
    status_code: int = 0
    body: bytes = b""
    etag: str = ""
    last_modified: str = ""
    error: str = ""
    final_url: str = ""
    tls_mode: str = "strict"  # strict | x509_strict_compat


@dataclass
class MonitorConfig:
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_seconds: float = 1.5
    rate_limit_seconds: float = 1.0
    user_agent: str = (
        "Mozilla/5.0 (compatible; CarbonEvidenceLedger-RegulatoryMonitor/3A.6; "
        "+https://github.com/AppleJustin/carbon-evidence-ledger-tw)"
    )
    freshness_windows: dict[str, timedelta] = field(default_factory=dict)
    auto_activate_rules: bool = False
    mark_affected_rules_pending_review: bool = True
    change_log_path: str = "data/regulatory/regulatory_change_log.csv"
    freshness_state_path: str = "data/regulatory/source_freshness_state.csv"
    conflict_log_path: str = "data/regulatory/regulatory_conflict_log.csv"
    summary_path: str = "data/regulatory/monitoring_summary.json"
    change_report_path: str = "data/regulatory/regulatory_change_report.md"
    persistence_status_path: str = "data/regulatory/persistence_status.json"
    high_priority_source_ids: list[str] = field(default_factory=list)
    required_authoritative_source_ids: list[str] = field(default_factory=list)
    critical_source_ids: list[str] = field(default_factory=list)
    important_source_ids: list[str] = field(default_factory=list)
    primary_authoritative_source_ids: list[str] = field(default_factory=list)
    alternate_official_monitoring_sources: dict[str, str] = field(
        default_factory=dict
    )
    manual_access_http_statuses: list[int] = field(
        default_factory=lambda: [401, 403, 407]
    )
    tls_x509_strict_fallback_hosts: list[str] = field(default_factory=list)
    reviewable_change_types: frozenset[str] = REVIEWABLE_CHANGE_TYPES
    schedule_cron_utc: str = "17 16 * * *"
    schedule_cadence: str = "daily"
    monitoring_state_branch: str = "regulatory-monitor-state"
    durable_state_dir: str = "data/regulatory/durable_state"
    bundled_state_dir: str = "data/regulatory"
    monitoring_state_files: list[str] = field(
        default_factory=lambda: list(DEFAULT_MONITORING_STATE_FILES)
    )


@dataclass
class PersistenceResult:
    ok: bool
    status: str
    destination: str = ""
    error: str = ""
    consecutive_persistence_failures: int = 0
    files_written: list[str] = field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_duration(token: str) -> timedelta:
    raw = str(token).strip().lower()
    match = re.fullmatch(r"(\d+)([dhms])", raw)
    if not match:
        raise ValueError(f"Unsupported duration: {token!r}")
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    return timedelta(seconds=amount)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        # YAML list under a key may parse as numbered dict in minimal loader.
        return [str(v).strip() for v in value.values() if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def load_monitor_config(path: Path) -> MonitorConfig:
    """Load a minimal YAML subset used by regulatory_monitoring.yaml."""
    text = Path(path).read_text(encoding="utf-8")
    data = _parse_simple_yaml(text)
    defaults = data.get("defaults", {}) or {}
    windows_raw = data.get("freshness_windows", {}) or {}
    windows = {key: _parse_duration(str(val)) for key, val in windows_raw.items()}
    if not windows:
        windows = {
            "high_change_source": timedelta(days=1),
            "normal_regulatory_source": timedelta(days=7),
            "stable_standard_reference": timedelta(days=30),
        }
    schedule = data.get("schedule", {}) or {}
    monitoring_state = data.get("monitoring_state", {}) or {}
    reviewable = _as_str_list(data.get("reviewable_change_types"))
    state_files = _as_str_list(data.get("monitoring_state_files"))
    return MonitorConfig(
        timeout_seconds=float(defaults.get("timeout_seconds", 30)),
        max_retries=int(defaults.get("max_retries", 3)),
        backoff_seconds=float(defaults.get("backoff_seconds", 1.5)),
        rate_limit_seconds=float(defaults.get("rate_limit_seconds", 1.0)),
        user_agent=str(
            defaults.get(
                "user_agent",
                MonitorConfig().user_agent,
            )
        ),
        freshness_windows=windows,
        auto_activate_rules=bool(data.get("auto_activate_rules", False)),
        mark_affected_rules_pending_review=bool(
            data.get("mark_affected_rules_pending_review", True)
        ),
        change_log_path=str(
            data.get("change_log_path", "data/regulatory/regulatory_change_log.csv")
        ),
        freshness_state_path=str(
            data.get(
                "freshness_state_path",
                "data/regulatory/source_freshness_state.csv",
            )
        ),
        conflict_log_path=str(
            data.get(
                "conflict_log_path",
                "data/regulatory/regulatory_conflict_log.csv",
            )
        ),
        summary_path=str(
            data.get("summary_path", "data/regulatory/monitoring_summary.json")
        ),
        change_report_path=str(
            data.get(
                "change_report_path",
                "data/regulatory/regulatory_change_report.md",
            )
        ),
        persistence_status_path=str(
            data.get(
                "persistence_status_path",
                "data/regulatory/persistence_status.json",
            )
        ),
        high_priority_source_ids=_as_str_list(
            data.get("high_priority_source_ids")
        ),
        required_authoritative_source_ids=_as_str_list(
            data.get("required_authoritative_source_ids")
        ),
        critical_source_ids=_as_str_list(data.get("critical_source_ids")),
        important_source_ids=_as_str_list(data.get("important_source_ids")),
        primary_authoritative_source_ids=_as_str_list(
            data.get("primary_authoritative_source_ids")
        ),
        alternate_official_monitoring_sources={
            str(k): str(v)
            for k, v in (
                (data.get("alternate_official_monitoring_sources") or {})
                if isinstance(
                    data.get("alternate_official_monitoring_sources"), dict
                )
                else {}
            ).items()
            if str(k).strip() and str(v).strip()
        },
        manual_access_http_statuses=[
            int(x)
            for x in _as_str_list(data.get("manual_access_http_statuses"))
            or ["401", "403", "407"]
        ],
        tls_x509_strict_fallback_hosts=_as_str_list(
            data.get("tls_x509_strict_fallback_hosts")
        ),
        reviewable_change_types=frozenset(reviewable or REVIEWABLE_CHANGE_TYPES),
        schedule_cron_utc=str(schedule.get("cron_utc", "17 16 * * *")),
        schedule_cadence=str(schedule.get("cadence", "daily")),
        monitoring_state_branch=str(
            monitoring_state.get("branch", "regulatory-monitor-state")
        ),
        durable_state_dir=str(
            monitoring_state.get("durable_dir", "data/regulatory/durable_state")
        ),
        bundled_state_dir=str(
            monitoring_state.get("bundled_dir", "data/regulatory")
        ),
        monitoring_state_files=state_files or list(DEFAULT_MONITORING_STATE_FILES),
    )


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Minimal indentation-based YAML loader for this project's config shape."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    pending_list_key: tuple[int, dict[str, Any], str] | None = None

    def _coerce_scalar(value: str) -> Any:
        if value.lower() in {"true", "false"}:
            return value.lower() == "true"
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if line.startswith("- "):
            item = line[2:].strip().strip('"').strip("'")
            while stack and indent < stack[-1][0]:
                stack.pop()
            parent = stack[-1][1]
            if pending_list_key and indent > pending_list_key[0]:
                container = pending_list_key[1]
                key = pending_list_key[2]
                if not isinstance(container.get(key), list):
                    container[key] = []
                container[key].append(_coerce_scalar(item))
                continue
            if isinstance(parent, list):
                parent.append(_coerce_scalar(item))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not isinstance(parent, dict):
            continue
        if value == "":
            # Assume a nested mapping; may become a list via subsequent "- " rows.
            nested: dict[str, Any] = {}
            parent[key] = nested
            stack.append((indent, nested))
            pending_list_key = (indent, parent, key)
            continue
        pending_list_key = None
        parent[key] = _coerce_scalar(value)
    return root


def normalize_content(body: bytes) -> str:
    """Normalize fetched bytes for stable hashing (ignore pure layout noise)."""
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        text = body.decode("latin-1", errors="replace")
    text = text.lower()
    text = re.sub(r"<script[\s\S]*?</script>", " ", text)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text)
    text = re.sub(r"<!--.*?-->", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def content_hash(body: bytes) -> str:
    return hashlib.sha256(normalize_content(body).encode("utf-8")).hexdigest()


def classify_change(
    *,
    previous_hash: str,
    new_hash: str,
    previous_etag: str,
    new_etag: str,
    previous_last_modified: str,
    new_last_modified: str,
    previous_version: str,
    new_version: str,
    fetch_ok: bool,
) -> str:
    if not fetch_ok:
        return "SOURCE_UNAVAILABLE"
    # First successful baseline: store hash without treating as a legal amendment.
    if not previous_hash:
        return "BASELINE_CAPTURED"
    if previous_hash == new_hash:
        if previous_version != new_version and (previous_version or new_version):
            # Version/effective-date metadata shift is reviewable later.
            return "METADATA_CHANGE"
        if previous_etag != new_etag or previous_last_modified != new_last_modified:
            return "METADATA_CHANGE"
        return "NO_CHANGE"
    # Hash changed: potential regulatory change pending human review.
    return "POTENTIAL_REGULATORY_CHANGE"


def is_reviewable_change(change: dict[str, str] | str) -> bool:
    """True when a change should open PR/Issue review activity."""
    if isinstance(change, str):
        change_type = change
        previous_version = ""
        new_version = ""
    else:
        change_type = str(change.get("change_type", ""))
        previous_version = str(change.get("previous_version", ""))
        new_version = str(change.get("new_version", ""))
    if change_type in {"BASELINE_CAPTURED", "NO_CHANGE", "COSMETIC_CHANGE"}:
        return False
    if change_type in REVIEWABLE_CHANGE_TYPES:
        return True
    if change_type == "ALTERNATE_OFFICIAL_SIGNAL":
        return True
    # Metadata-only review only when version identifiers differ.
    if change_type == "METADATA_CHANGE" and previous_version != new_version:
        return bool(previous_version or new_version)
    return False


def should_open_review_activity(changes: list[dict[str, str]]) -> bool:
    """Avoid notification spam for NO_CHANGE / COSMETIC_CHANGE."""
    return any(is_reviewable_change(change) for change in changes)


def source_criticality(source_id: str, config: MonitorConfig) -> str:
    sid = str(source_id or "")
    if sid in set(config.critical_source_ids):
        return CRITICALITY_CRITICAL
    if sid in set(config.important_source_ids):
        return CRITICALITY_IMPORTANT
    return CRITICALITY_SUPPLEMENTARY


def is_x509_strict_compatibility_error(error: object) -> bool:
    """True only for Python 3.13 VERIFY_X509_STRICT / missing SKI style failures."""
    text = str(error or "").upper()
    markers = (
        "MISSING SUBJECT KEY IDENTIFIER",
        "SUBJECT KEY IDENTIFIER",
        "VERIFY_X509_STRICT",
    )
    return any(marker in text for marker in markers)


def hostname_in_tls_fallback_allowlist(
    url: str, allowlist: list[str] | set[str] | frozenset[str]
) -> bool:
    host = (urlparse(str(url)).hostname or "").lower()
    if not host:
        return False
    allowed = {str(item).strip().lower() for item in allowlist if str(item).strip()}
    return host in allowed


def build_official_source_ssl_context(
    *, relax_x509_strict: bool = False
) -> ssl.SSLContext:
    """TLS context that always keeps CA trust + hostname verification.

    When relax_x509_strict=True, only clears VERIFY_X509_STRICT for known
    official-source certificate-chain quirks. Never disables verification.
    """
    ctx = ssl.create_default_context()
    # Hard invariants — never ship an unverified context.
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    if relax_x509_strict and hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def _fetch_once(
    url: str,
    timeout: float,
    user_agent: str,
    *,
    context: ssl.SSLContext,
    tls_mode: str,
) -> FetchResult:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "application/pdf,*/*;q=0.8"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        method="GET",
    )
    try:
        with urlopen(  # noqa: S310 — official URLs only; TLS context required
            request, timeout=timeout, context=context
        ) as response:
            body = response.read(10 * 1024 * 1024)
            headers = {k.lower(): v for k, v in response.headers.items()}
            return FetchResult(
                ok=True,
                status_code=getattr(response, "status", 200) or 200,
                body=body,
                etag=headers.get("etag", ""),
                last_modified=headers.get("last-modified", ""),
                final_url=str(getattr(response, "url", url)),
                tls_mode=tls_mode,
            )
    except HTTPError as exc:
        return FetchResult(
            ok=False, status_code=int(exc.code), error=str(exc), tls_mode=tls_mode
        )
    except URLError as exc:
        reason = exc.reason if hasattr(exc, "reason") else exc
        return FetchResult(ok=False, error=str(reason), tls_mode=tls_mode)
    except ssl.SSLError as exc:
        return FetchResult(ok=False, error=str(exc), tls_mode=tls_mode)
    except Exception as exc:  # noqa: BLE001
        return FetchResult(ok=False, error=str(exc), tls_mode=tls_mode)


def default_fetch(
    url: str,
    timeout: float,
    user_agent: str,
    *,
    tls_fallback_hosts: list[str] | None = None,
) -> FetchResult:
    """Fetch with strict TLS first; optional allowlisted X509-strict compat retry."""
    strict_ctx = build_official_source_ssl_context(relax_x509_strict=False)
    first = _fetch_once(
        url, timeout, user_agent, context=strict_ctx, tls_mode="strict"
    )
    if first.ok:
        return first
    if not is_x509_strict_compatibility_error(first.error):
        return first
    allowlist = tls_fallback_hosts or []
    if not hostname_in_tls_fallback_allowlist(url, allowlist):
        return first
    compat_ctx = build_official_source_ssl_context(relax_x509_strict=True)
    # Invariants still hold on the compatibility context.
    if (
        compat_ctx.verify_mode != ssl.CERT_REQUIRED
        or not compat_ctx.check_hostname
    ):
        return FetchResult(
            ok=False,
            error="TLS compatibility context failed security invariants",
            tls_mode="x509_strict_compat",
        )
    return _fetch_once(
        url,
        timeout,
        user_agent,
        context=compat_ctx,
        tls_mode="x509_strict_compat",
    )


def fetch_with_retries(
    url: str,
    config: MonitorConfig,
    fetch_fn: FetchFn | None = None,
) -> FetchResult:
    last = FetchResult(ok=False, error="not attempted")
    for attempt in range(config.max_retries):
        if fetch_fn is None:
            last = default_fetch(
                url,
                config.timeout_seconds,
                config.user_agent,
                tls_fallback_hosts=config.tls_x509_strict_fallback_hosts,
            )
        else:
            last = fetch_fn(url, config.timeout_seconds)
        if last.ok:
            return last
        # Access-denied / auth challenges: do not retry aggressively.
        if int(last.status_code or 0) in set(config.manual_access_http_statuses):
            return last
        sleep_for = config.backoff_seconds * (2**attempt)
        time.sleep(min(sleep_for, 30.0))
    return last


def _read_csv_dict(path: Path, columns: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            item = {col: "" for col in columns}
            item.update({k: str(v or "") for k, v in row.items() if k})
            rows.append(item)
        return rows


def _write_csv_dict(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def freshness_window_for(
    source_row: dict[str, str], config: MonitorConfig
) -> timedelta:
    profile = str(
        source_row.get("monitor_frequency") or "normal_regulatory_source"
    )
    default = config.freshness_windows.get(
        "normal_regulatory_source", timedelta(days=7)
    )
    return config.freshness_windows.get(profile, default)


def evaluate_freshness(
    *,
    last_successful_fetch_at: str,
    fetch_failed: bool,
    window: timedelta,
    now: datetime | None = None,
    consecutive_failures: int = 0,
    manual_access_required: bool = False,
) -> str:
    """Freshness status for the *latest check attempt*.

    CURRENT requires a successful official fetch on this check.
    A failed latest check is never reported as CURRENT, even when a prior
    successful fetch remains within the freshness window (that prior stamp is
    preserved separately in last_successful_fetch_at).
    """
    if manual_access_required:
        return "MANUAL_ACCESS_REQUIRED"
    stamp = _parse_iso(last_successful_fetch_at)
    current = now or _utc_now()
    if fetch_failed or consecutive_failures > 0:
        # Latest attempt failed — never present as CURRENT.
        if stamp is None:
            return "FETCH_FAILED"
        age = current - stamp
        if age <= window * 2:
            return "FETCH_FAILED"
        return "FETCH_FAILED"
    if stamp is None:
        return "CHECK_DUE"
    age = current - stamp
    if age <= window:
        return "CURRENT"
    if age <= window * 2:
        return "CHECK_DUE"
    return "STALE"


def fail_safe_state_for_freshness(freshness_status: str) -> str | None:
    if freshness_status in {"STALE", "REGULATORY_DATA_STALE"}:
        return "REGULATORY_DATA_STALE"
    if freshness_status in {"CHECK_DUE", "UPDATE_REQUIRED"}:
        return "UPDATE_REQUIRED"
    if freshness_status in {"MANUAL_ACCESS_REQUIRED", "MANUAL_VERIFICATION_REQUIRED"}:
        return "MANUAL_VERIFICATION_REQUIRED"
    if freshness_status in {
        "FETCH_FAILED",
        "SOURCE_CHECK_FAILED",
        "CRITICAL_SOURCE_FAILURE",
    }:
        return "SOURCE_CHECK_FAILED"
    if freshness_status in {"FRESHNESS_STATE_UNAVAILABLE"}:
        return "FRESHNESS_STATE_UNAVAILABLE"
    if freshness_status in {"STATE_PERSISTENCE_FAILED"}:
        return "STATE_PERSISTENCE_FAILED"
    if freshness_status in {"STATE_PERSISTENCE_MISMATCH"}:
        return "STATE_PERSISTENCE_MISMATCH"
    return None


def assert_sources_fresh_for_analysis(
    freshness_rows: list[dict[str, str]],
    required_source_ids: list[str],
    *,
    state_available: bool = True,
    persistence_failed: bool = False,
) -> dict[str, Any]:
    """Pre-analysis gate used by future applicability/compliance workflows."""
    if not state_available:
        return {
            "analysis_allowed": False,
            "state": "FRESHNESS_STATE_UNAVAILABLE",
            "stale_sources": [],
            "failed_sources": list(required_source_ids),
            "due_sources": [],
            "message": (
                "Durable regulatory freshness state is unavailable; "
                "do not present unconditional regulatory conclusions."
            ),
        }
    if persistence_failed and not freshness_rows:
        return {
            "analysis_allowed": False,
            "state": "STATE_PERSISTENCE_FAILED",
            "stale_sources": [],
            "failed_sources": list(required_source_ids),
            "due_sources": [],
            "message": (
                "Monitoring state persistence failed; runner-local timestamps "
                "must not be treated as durable freshness proof."
            ),
        }
    by_id = {row["source_id"]: row for row in freshness_rows}
    stale: list[str] = []
    failed: list[str] = []
    due: list[str] = []
    manual: list[str] = []
    for source_id in required_source_ids:
        row = by_id.get(source_id)
        if row is None:
            failed.append(source_id)
            continue
        status = row.get("freshness_status", "CHECK_DUE")
        if status in {"STALE", "REGULATORY_DATA_STALE"}:
            stale.append(source_id)
        elif status in {
            "FETCH_FAILED",
            "SOURCE_CHECK_FAILED",
            "FRESHNESS_STATE_UNAVAILABLE",
            "STATE_PERSISTENCE_FAILED",
        }:
            failed.append(source_id)
        elif status in {"MANUAL_ACCESS_REQUIRED", "MANUAL_VERIFICATION_REQUIRED"}:
            manual.append(source_id)
        elif status in {"CHECK_DUE", "UPDATE_REQUIRED"}:
            due.append(source_id)
    if failed:
        state = "SOURCE_CHECK_FAILED"
    elif stale:
        state = "REGULATORY_DATA_STALE"
    elif manual:
        state = "MANUAL_VERIFICATION_REQUIRED"
    elif due:
        state = "UPDATE_REQUIRED"
    elif persistence_failed:
        state = "STATE_PERSISTENCE_FAILED"
    else:
        state = "CURRENT"
    return {
        "analysis_allowed": state == "CURRENT",
        "state": state,
        "stale_sources": stale,
        "failed_sources": failed,
        "due_sources": due + manual,
        "message": (
            "Official regulatory sources are current."
            if state == "CURRENT"
            else (
                "Official regulatory source could not be confirmed recently enough; "
                "do not present unconditional Applicable / Not applicable / "
                "Compliant / No action required conclusions."
            )
        ),
    }


def _max_int_field(rows: list[dict[str, str]], field_name: str) -> int:
    values: list[int] = []
    for row in rows:
        raw = str(row.get(field_name) or "0").strip()
        try:
            values.append(int(raw))
        except ValueError:
            values.append(0)
    return max(values) if values else 0


def build_monitoring_summary(
    *,
    freshness_rows: list[dict[str, str]],
    change_rows: list[dict[str, str]],
    conflict_rows: list[dict[str, str]],
    new_changes: list[dict[str, str]] | None = None,
    now: datetime | None = None,
    state_source: str = STATE_SOURCE_BUNDLED,
    consecutive_persistence_failures: int = 0,
    persistence_status: str = "OK",
    critical_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Machine-readable summary for future Compliance Overview / Stage 3B."""
    current_now = now or _utc_now()
    critical_ids = set(critical_source_ids or [])
    statuses = [row.get("freshness_status", "CHECK_DUE") for row in freshness_rows]
    sources_current = sum(1 for status in statuses if status == "CURRENT")
    sources_stale = sum(
        1 for status in statuses if status in {"STALE", "REGULATORY_DATA_STALE"}
    )
    sources_failed = sum(
        1
        for status in statuses
        if status in {"FETCH_FAILED", "SOURCE_CHECK_FAILED"}
    )
    sources_manual_access = sum(
        1
        for status in statuses
        if status in {"MANUAL_ACCESS_REQUIRED", "MANUAL_VERIFICATION_REQUIRED"}
    )
    critical_sources_failed = 0
    for row in freshness_rows:
        sid = row.get("source_id", "")
        criticality = row.get("monitor_criticality") or (
            CRITICALITY_CRITICAL if sid in critical_ids else ""
        )
        # MANUAL_ACCESS_REQUIRED is a managed limitation, not a hard fetch crash.
        failed = row.get("fetch_status") == "FETCH_FAILED" or row.get(
            "freshness_status"
        ) in {"FETCH_FAILED", "SOURCE_CHECK_FAILED"}
        if criticality == CRITICALITY_CRITICAL and failed:
            critical_sources_failed += 1
    checked_at_values = [
        row.get("last_checked_at", "")
        for row in freshness_rows
        if row.get("last_checked_at")
    ]
    success_at_values = [
        row.get("last_successful_fetch_at", "")
        for row in freshness_rows
        if row.get("last_successful_fetch_at")
    ]
    pending_changes = [
        row
        for row in change_rows
        if row.get("review_status") == "PENDING_REVIEW"
        and is_reviewable_change(row)
    ]
    open_conflicts = [
        row for row in conflict_rows if row.get("review_status") == "PENDING_REVIEW"
    ]
    consecutive_fetch_failures = _max_int_field(freshness_rows, "consecutive_failures")
    if persistence_status in {
        "STATE_PERSISTENCE_FAILED",
        "STATE_PERSISTENCE_MISMATCH",
    }:
        overall = persistence_status
    elif state_source == STATE_SOURCE_UNAVAILABLE:
        overall = "FRESHNESS_STATE_UNAVAILABLE"
    elif critical_sources_failed > 0:
        # CRITICAL failures can never be reported as CURRENT.
        overall = "SOURCE_CHECK_FAILED"
    elif sources_failed and not sources_current:
        overall = "SOURCE_CHECK_FAILED"
    elif sources_stale:
        overall = "STALE"
    elif sources_manual_access:
        overall = "MANUAL_VERIFICATION_REQUIRED"
    elif any(status in {"CHECK_DUE", "UPDATE_REQUIRED"} for status in statuses):
        overall = "UPDATE_REQUIRED"
    elif consecutive_persistence_failures >= 3:
        overall = "UPDATE_REQUIRED"
    elif sources_current and sources_current == len(freshness_rows):
        overall = "CURRENT"
    elif sources_current:
        overall = "PARTIAL"
    else:
        overall = "CHECK_DUE"
    reviewable_new = [c for c in (new_changes or []) if is_reviewable_change(c)]
    summary = {
        "overall_regulatory_freshness": overall,
        "last_global_check_at": max(checked_at_values) if checked_at_values else "",
        "last_successful_check_at": (
            max(success_at_values) if success_at_values else ""
        ),
        "sources_current": sources_current,
        "sources_stale": sources_stale,
        "sources_failed": sources_failed,
        "sources_manual_access": sources_manual_access,
        "sources_total": len(freshness_rows),
        "critical_sources_failed": critical_sources_failed,
        "changes_pending_review": len(pending_changes),
        "regulatory_conflicts": len(open_conflicts),
        "review_required": bool(reviewable_new or open_conflicts),
        "reviewable_new_changes": len(reviewable_new),
        "generated_at": _iso(current_now),
        "fail_safe_state": fail_safe_state_for_freshness(overall),
        "state_source": state_source,
        "consecutive_fetch_failures": consecutive_fetch_failures,
        "consecutive_persistence_failures": consecutive_persistence_failures,
        "persistence_status": persistence_status,
    }
    summary["monitoring_health"] = evaluate_monitoring_health(summary)
    return summary


def evaluate_monitoring_health(summary: dict[str, Any]) -> str:
    """Workflow health independent of Python process crash status.

    Precedence:
    1. STATE_PERSISTENCE_FAILED
    2. STATE_PERSISTENCE_MISMATCH
    3. CRITICAL_SOURCE_FAILURE
    4. PARTIAL (incl. manual verification / supplementary issues)
    5. CURRENT
    """
    persistence = str(summary.get("persistence_status") or "")
    overall = str(summary.get("overall_regulatory_freshness") or "")
    if (
        persistence == "STATE_PERSISTENCE_FAILED"
        or overall == "STATE_PERSISTENCE_FAILED"
    ):
        return HEALTH_STATE_PERSISTENCE_FAILED
    if (
        persistence == "STATE_PERSISTENCE_MISMATCH"
        or overall == "STATE_PERSISTENCE_MISMATCH"
    ):
        return HEALTH_STATE_PERSISTENCE_MISMATCH
    if int(summary.get("critical_sources_failed") or 0) > 0:
        return HEALTH_CRITICAL_SOURCE_FAILURE
    if overall in {"FRESHNESS_STATE_UNAVAILABLE"}:
        return HEALTH_STATE_PERSISTENCE_FAILED
    if overall == "CURRENT":
        return HEALTH_MONITORING_CURRENT
    return HEALTH_MONITORING_PARTIAL


def compare_monitoring_summaries(
    runtime: dict[str, Any],
    persisted: dict[str, Any],
) -> list[str]:
    """Return mismatched integrity keys between runtime and persisted summaries."""
    mismatches: list[str] = []
    for key in SUMMARY_INTEGRITY_KEYS:
        left = runtime.get(key)
        right = persisted.get(key)
        if str(left) != str(right):
            mismatches.append(key)
    return mismatches


def write_monitoring_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def is_allowed_monitoring_state_file(path_or_name: str) -> bool:
    """True only for operational monitoring STATE files (never legal CONTENT)."""
    text = str(path_or_name or "").replace("\\", "/").strip()
    if not text:
        return False
    for fragment in FORBIDDEN_STATE_PATH_FRAGMENTS:
        if fragment in text:
            return False
    basename = Path(text).name
    return basename in DEFAULT_MONITORING_STATE_FILES


def read_persistence_status(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_persistence_status(path: Path, status: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _state_dir_has_freshness(state_dir: Path) -> bool:
    freshness = state_dir / "source_freshness_state.csv"
    return freshness.is_file() and freshness.stat().st_size > 0


def resolve_monitoring_state_dir(
    repo_root: Path,
    config: MonitorConfig | None = None,
) -> tuple[Path | None, str]:
    """Resolve durable monitoring STATE directory for freshness reads.

    Preference order (source of truth):
    1. CARBON_LEDGER_REGULATORY_STATE_DIR (production mount of latest durable state)
    2. repo durable_state_dir (local checkout of regulatory-monitor-state export)
    3. bundled data/regulatory fallback (may be stale with a deployment)

    Returns (directory_or_None, state_source).
    """
    root = Path(repo_root)
    cfg = config or load_monitor_config(root / "config" / "regulatory_monitoring.yaml")
    env_raw = os.environ.get("CARBON_LEDGER_REGULATORY_STATE_DIR", "").strip()
    if env_raw:
        env_dir = Path(env_raw)
        if _state_dir_has_freshness(env_dir):
            return env_dir, STATE_SOURCE_DURABLE
    durable = root / cfg.durable_state_dir
    if _state_dir_has_freshness(durable):
        return durable, STATE_SOURCE_DURABLE
    bundled = root / cfg.bundled_state_dir
    if _state_dir_has_freshness(bundled):
        return bundled, STATE_SOURCE_BUNDLED
    return None, STATE_SOURCE_UNAVAILABLE


def persist_monitoring_state(
    repo_root: Path,
    *,
    destination: Path | None = None,
    config: MonitorConfig | None = None,
    now: datetime | None = None,
) -> PersistenceResult:
    """Finalize runtime durable STATE and mirror to bundled fallback.

    Runtime source of truth is durable_dir (data/regulatory/durable_state/).
    The regulatory-monitor-state branch must be populated from that directory,
    never from a stale bundled template.
    """
    root = Path(repo_root)
    cfg = config or load_monitor_config(root / "config" / "regulatory_monitoring.yaml")
    durable = (
        Path(destination)
        if destination is not None
        else root / cfg.durable_state_dir
    )
    bundled = root / cfg.bundled_state_dir
    prior = read_persistence_status(durable / "persistence_status.json")
    if not prior:
        prior = read_persistence_status(root / cfg.persistence_status_path)
    prior_failures = int(prior.get("consecutive_persistence_failures") or 0)
    stamp = _iso(now or _utc_now())
    written: list[str] = []
    try:
        durable.mkdir(parents=True, exist_ok=True)
        for name in cfg.monitoring_state_files:
            if not is_allowed_monitoring_state_file(name):
                raise RuntimeError(
                    f"Refusing to persist non-monitoring file as state: {name}"
                )
            src = durable / name
            if not src.is_file():
                continue
            resolved = src.resolve()
            if not str(resolved).startswith(str(durable.resolve())):
                raise RuntimeError(f"State source escaped durable dir: {name}")
            for fragment in FORBIDDEN_STATE_PATH_FRAGMENTS:
                if fragment in str(resolved).replace("\\", "/"):
                    raise RuntimeError(
                        f"Refusing forbidden CONTENT path in state persist: {fragment}"
                    )
            written.append(name)
        if not (durable / "source_freshness_state.csv").is_file():
            raise RuntimeError(
                "source_freshness_state.csv missing in durable runtime state"
            )
        if not (durable / "monitoring_summary.json").is_file():
            raise RuntimeError(
                "monitoring_summary.json missing in durable runtime state"
            )
        # Mirror durable → bundled fallback (never the reverse for SoT).
        bundled.mkdir(parents=True, exist_ok=True)
        for name in written:
            shutil.copy2(durable / name, bundled / name)
        status = {
            "status": "OK",
            "persisted_at": stamp,
            "destination": str(durable),
            "files": written,
            "consecutive_persistence_failures": 0,
            "monitoring_state_branch": cfg.monitoring_state_branch,
            "runtime_state_dir": str(durable),
            "error": "",
        }
        write_persistence_status(durable / "persistence_status.json", status)
        write_persistence_status(bundled / "persistence_status.json", status)
        write_persistence_status(root / cfg.persistence_status_path, status)
        if "persistence_status.json" not in written:
            written.append("persistence_status.json")
        return PersistenceResult(
            ok=True,
            status="OK",
            destination=str(durable),
            consecutive_persistence_failures=0,
            files_written=written,
        )
    except Exception as exc:  # noqa: BLE001 — persistence boundary
        failures = prior_failures + 1
        status = {
            "status": "STATE_PERSISTENCE_FAILED",
            "persisted_at": "",
            "destination": str(durable),
            "files": written,
            "consecutive_persistence_failures": failures,
            "monitoring_state_branch": cfg.monitoring_state_branch,
            "runtime_state_dir": str(durable),
            "error": str(exc),
            "failed_at": stamp,
        }
        try:
            write_persistence_status(root / cfg.persistence_status_path, status)
        except OSError:
            pass
        return PersistenceResult(
            ok=False,
            status="STATE_PERSISTENCE_FAILED",
            destination=str(durable),
            error=str(exc),
            consecutive_persistence_failures=failures,
            files_written=written,
        )


def verify_persisted_state_matches_runtime(
    runtime_summary: dict[str, Any],
    persisted_summary_path: Path,
) -> tuple[bool, list[str]]:
    """Compare persisted monitoring_summary.json to the runtime summary."""
    if not persisted_summary_path.is_file():
        return False, ["monitoring_summary.json_missing"]
    try:
        persisted = json.loads(
            persisted_summary_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False, ["monitoring_summary.json_unreadable"]
    if not isinstance(persisted, dict):
        return False, ["monitoring_summary.json_invalid"]
    mismatches = compare_monitoring_summaries(runtime_summary, persisted)
    return (not mismatches), mismatches


def write_change_report(
    path: Path,
    *,
    summary: dict[str, Any],
    changes: list[dict[str, str]],
) -> None:
    """Human-readable report for PR/Issue review (untrusted source data)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    reviewable = [c for c in changes if is_reviewable_change(c)]
    lines = [
        "# Regulatory change report",
        "",
        f"Generated at: {summary.get('generated_at', '')}",
        f"Overall freshness: {summary.get('overall_regulatory_freshness', '')}",
        f"Review required: {summary.get('review_required', False)}",
        "",
        "## Reviewable changes",
        "",
    ]
    if not reviewable:
        lines.append("None.")
    else:
        for change in reviewable:
            lines.extend(
                [
                    f"### {change.get('change_id', '')}",
                    f"- source_id: `{change.get('source_id', '')}`",
                    f"- change_type: `{change.get('change_type', '')}`",
                    f"- previous_hash: `{change.get('previous_hash', '')}`",
                    f"- new_hash: `{change.get('new_hash', '')}`",
                    f"- previous_version: `{change.get('previous_version', '')}`",
                    f"- new_version: `{change.get('new_version', '')}`",
                    f"- affected_rule_ids: `{change.get('affected_rule_ids', '')}`",
                    f"- activation_status: `{change.get('activation_status', '')}`",
                    f"- notes: {change.get('notes', '')}",
                    "",
                ]
            )
    lines.extend(
        [
            "## Reviewer workflow",
            "",
            "1. Verify the official source text manually.",
            "2. Confirm whether a legal rule change is required.",
            "3. Add/update rule rows with new `source_version` / "
            "`rule_effective_from`.",
            "4. Set the new rule `rule_status=ACTIVE` (or FUTURE).",
            "5. Set the previous rule `rule_status=SUPERSEDED` and link "
            "`superseded_by_rule_id`.",
            "6. Never auto-merge monitoring PRs into production compliance logic.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def get_regulatory_freshness(
    repo_root: Path | None = None,
    *,
    required_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Callable freshness gate for future Stage 3B applicability logic.

    Source of truth preference:
    - production / preferred: latest durable persisted monitoring state
      (CARBON_LEDGER_REGULATORY_STATE_DIR or data/regulatory/durable_state)
    - fallback: repository-bundled data/regulatory (may lag a deployment)

    Artifacts / workflow logs are never consulted. If no durable or bundled
    freshness file is available, returns FRESHNESS_STATE_UNAVAILABLE and does
    not pretend the sources are current.
    """
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    config = load_monitor_config(root / "config" / "regulatory_monitoring.yaml")
    state_dir, state_source = resolve_monitoring_state_dir(root, config)
    required = required_source_ids or list(config.required_authoritative_source_ids)

    if state_dir is None:
        empty_summary = build_monitoring_summary(
            freshness_rows=[],
            change_rows=[],
            conflict_rows=[],
            state_source=STATE_SOURCE_UNAVAILABLE,
            persistence_status="FRESHNESS_STATE_UNAVAILABLE",
        )
        gate = assert_sources_fresh_for_analysis(
            [], required, state_available=False
        )
        return {
            **gate,
            "summary": empty_summary,
            "required_source_ids": required,
            "high_priority_source_ids": list(config.high_priority_source_ids),
            "overall_regulatory_freshness": "FRESHNESS_STATE_UNAVAILABLE",
            "last_global_check_at": "",
            "last_successful_check_at": "",
            "sources_current": 0,
            "sources_stale": 0,
            "sources_failed": 0,
            "changes_pending_review": 0,
            "regulatory_conflicts": 0,
            "state_source": STATE_SOURCE_UNAVAILABLE,
            "consecutive_fetch_failures": 0,
            "consecutive_persistence_failures": 0,
            "persistence_status": "FRESHNESS_STATE_UNAVAILABLE",
        }

    freshness_rows = _read_csv_dict(
        state_dir / "source_freshness_state.csv", FRESHNESS_COLUMNS
    )
    change_rows = _read_csv_dict(
        state_dir / "regulatory_change_log.csv", CHANGE_LOG_COLUMNS
    )
    conflict_rows = _read_csv_dict(
        state_dir / "regulatory_conflict_log.csv", CONFLICT_COLUMNS
    )
    persistence = read_persistence_status(state_dir / "persistence_status.json")
    if not persistence:
        persistence = read_persistence_status(root / config.persistence_status_path)
    persistence_status = str(persistence.get("status") or "OK")
    consecutive_persistence_failures = int(
        persistence.get("consecutive_persistence_failures") or 0
    )
    persistence_failed = persistence_status == "STATE_PERSISTENCE_FAILED"
    gate = assert_sources_fresh_for_analysis(
        freshness_rows,
        required,
        state_available=True,
        persistence_failed=persistence_failed,
    )
    # Prefer on-disk summary when present; rebuild to refresh derived fields.
    summary = build_monitoring_summary(
        freshness_rows=freshness_rows,
        change_rows=change_rows,
        conflict_rows=conflict_rows,
        state_source=state_source,
        consecutive_persistence_failures=consecutive_persistence_failures,
        persistence_status=persistence_status,
        critical_source_ids=list(config.critical_source_ids),
    )
    on_disk = state_dir / "monitoring_summary.json"
    if on_disk.is_file():
        try:
            loaded = json.loads(on_disk.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                # Keep rebuilt fields authoritative for state_source / counts.
                merged = {**loaded, **summary}
                summary = merged
        except (OSError, json.JSONDecodeError):
            pass
    if state_source == STATE_SOURCE_BUNDLED and gate["state"] == "CURRENT":
        # Bundled fallback may be stale relative to production; surface provenance.
        summary["state_source"] = STATE_SOURCE_BUNDLED
        summary["bundled_fallback_warning"] = (
            "Using repository-bundled monitoring state; prefer durable "
            "regulatory-monitor-state / CARBON_LEDGER_REGULATORY_STATE_DIR."
        )
    return {
        **gate,
        "summary": summary,
        "required_source_ids": required,
        "high_priority_source_ids": list(config.high_priority_source_ids),
        "overall_regulatory_freshness": summary["overall_regulatory_freshness"],
        "last_global_check_at": summary["last_global_check_at"],
        "last_successful_check_at": summary["last_successful_check_at"],
        "sources_current": summary["sources_current"],
        "sources_stale": summary["sources_stale"],
        "sources_failed": summary["sources_failed"],
        "changes_pending_review": summary["changes_pending_review"],
        "regulatory_conflicts": summary["regulatory_conflicts"],
        "state_source": state_source,
        "consecutive_fetch_failures": summary["consecutive_fetch_failures"],
        "consecutive_persistence_failures": consecutive_persistence_failures,
        "persistence_status": persistence_status,
    }


def mark_rules_pending_review(
    rules_path: Path,
    affected_rule_ids: list[str],
) -> int:
    """Mark affected rules PENDING_REVIEW without activating replacements."""
    if not affected_rule_ids:
        return 0
    rules = load_regulatory_rules(rules_path)
    changed = 0
    ids = set(affected_rule_ids)
    for idx, row in rules.iterrows():
        if row["rule_id"] in ids and row["rule_status"] in {"ACTIVE", "FUTURE"}:
            rules.at[idx, "rule_status"] = "PENDING_REVIEW"
            rules.at[idx, "verification_status"] = "PENDING_REVIEW"
            changed += 1
    if changed:
        rules.to_csv(rules_path, index=False)
    return changed


def record_conflict(
    conflict_path: Path,
    *,
    source_id_a: str,
    source_id_b: str,
    requirement_a: str,
    requirement_b: str,
    publication_date_a: str = "",
    publication_date_b: str = "",
    effective_date_a: str = "",
    effective_date_b: str = "",
    affected_rule_ids: list[str] | None = None,
    notes: str = "",
) -> dict[str, str]:
    """Surface REGULATORY_CONFLICT without silently resolving it."""
    rows = _read_csv_dict(conflict_path, CONFLICT_COLUMNS)
    stamp = _iso(_utc_now()).replace(":", "").replace("-", "")
    conflict = {
        "conflict_id": f"conflict_{stamp}_{len(rows) + 1}",
        "detected_at": _iso(_utc_now()),
        "source_id_a": source_id_a,
        "source_id_b": source_id_b,
        "requirement_a": requirement_a,
        "requirement_b": requirement_b,
        "publication_date_a": publication_date_a,
        "publication_date_b": publication_date_b,
        "effective_date_a": effective_date_a,
        "effective_date_b": effective_date_b,
        "affected_rule_ids": ";".join(affected_rule_ids or []),
        "review_status": "PENDING_REVIEW",
        "notes": notes or "REGULATORY_CONFLICT — manual review required",
    }
    rows.append(conflict)
    _write_csv_dict(conflict_path, CONFLICT_COLUMNS, rows)
    return conflict


def is_manual_access_block(
    *,
    source_id: str,
    status_code: int,
    config: MonitorConfig,
) -> bool:
    """True when a primary authoritative source is blocked (e.g. HTTP 403)."""
    if source_id not in set(config.primary_authoritative_source_ids):
        return False
    return int(status_code or 0) in set(config.manual_access_http_statuses)


def check_source(
    source_row: dict[str, str],
    *,
    prior: dict[str, str],
    config: MonitorConfig,
    fetch_fn: FetchFn | None = None,
    now: datetime | None = None,
    alternate_source_row: dict[str, str] | None = None,
    alternate_prior: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Check one source; return updated freshness row and zero+ change events."""
    current = now or _utc_now()
    checked_at = _iso(current)
    url = str(source_row.get("official_url", "")).strip()
    fetch = fetch_with_retries(url, config, fetch_fn=fetch_fn)
    window = freshness_window_for(source_row, config)
    next_check = _iso(current + window)
    source_id = str(source_row["source_id"])

    updated = dict(prior)
    updated["source_id"] = source_id
    updated["monitor_criticality"] = source_criticality(source_id, config)
    updated["last_checked_at"] = checked_at
    updated["next_check_at"] = next_check

    if not fetch.ok:
        prior_success = prior.get("last_successful_fetch_at", "")
        failures = int(updated.get("consecutive_failures") or "0") + 1
        updated["consecutive_failures"] = str(failures)
        updated["last_successful_fetch_at"] = prior_success
        change_stamp = checked_at.replace(":", "").replace("-", "")
        changes: list[dict[str, str]] = []

        if is_manual_access_block(
            source_id=source_id,
            status_code=fetch.status_code,
            config=config,
        ):
            updated["fetch_status"] = "MANUAL_ACCESS_REQUIRED"
            updated["fetch_error"] = fetch.error or f"HTTP {fetch.status_code}"
            updated["freshness_status"] = evaluate_freshness(
                last_successful_fetch_at=prior_success,
                fetch_failed=True,
                window=window,
                now=current,
                consecutive_failures=failures,
                manual_access_required=True,
            )
            alt_id = config.alternate_official_monitoring_sources.get(source_id, "")
            notes = (
                "PRIMARY_AUTHORITATIVE_SOURCE returned HTTP "
                f"{fetch.status_code}; fetch_status=MANUAL_ACCESS_REQUIRED "
                "(not endless SOURCE_UNAVAILABLE). "
                "Do not treat as CURRENT. Taiwan-recognised IFRS conclusions "
                "require manual confirmation against the authoritative SFB source."
            )
            if alt_id:
                notes += (
                    f" ALTERNATE_OFFICIAL_MONITORING_SOURCE={alt_id} may provide "
                    "early-warning only; never auto-activates recognition."
                )
            changes.append(
                {
                    "change_id": f"chg_{source_id}_{change_stamp}",
                    "source_id": source_id,
                    "detected_at": checked_at,
                    "previous_hash": prior.get("content_hash", ""),
                    "new_hash": "",
                    "change_type": "MANUAL_ACCESS_REQUIRED",
                    "previous_version": prior.get("current_source_version", ""),
                    "new_version": prior.get("current_source_version", ""),
                    "affected_rule_ids": "",
                    "review_status": "INFO",
                    "reviewed_by": "",
                    "reviewed_at": "",
                    "activation_status": "NOT_ACTIVATED",
                    "notes": notes,
                }
            )
            # Early-warning probe of alternate official source (no TLS weakening).
            if alternate_source_row is not None:
                alt_url = str(alternate_source_row.get("official_url", "")).strip()
                alt_sid = str(alternate_source_row.get("source_id", alt_id))
                if alt_url:
                    alt_fetch = fetch_with_retries(alt_url, config, fetch_fn=fetch_fn)
                    if alt_fetch.ok:
                        alt_hash = content_hash(alt_fetch.body)
                        alt_prior_hash = (alternate_prior or {}).get("content_hash", "")
                        if alt_prior_hash and alt_prior_hash != alt_hash:
                            changes.append(
                                {
                                    "change_id": (
                                        f"chg_{source_id}_alt_{change_stamp}"
                                    ),
                                    "source_id": source_id,
                                    "detected_at": checked_at,
                                    "previous_hash": alt_prior_hash,
                                    "new_hash": alt_hash,
                                    "change_type": "ALTERNATE_OFFICIAL_SIGNAL",
                                    "previous_version": "",
                                    "new_version": "",
                                    "affected_rule_ids": "",
                                    "review_status": "PENDING_REVIEW",
                                    "reviewed_by": "",
                                    "reviewed_at": "",
                                    "activation_status": "NOT_ACTIVATED",
                                    "notes": (
                                        "ALTERNATE_OFFICIAL_SIGNAL from "
                                        f"{alt_sid}. PENDING_REVIEW only — does "
                                        "NOT auto-activate Taiwan-recognised IFRS "
                                        "version. Confirm against primary "
                                        "authoritative SFB source "
                                        f"({source_id})."
                                    ),
                                }
                            )
            return updated, changes

        updated["fetch_status"] = "FETCH_FAILED"
        updated["fetch_error"] = fetch.error or f"HTTP {fetch.status_code}"
        updated["freshness_status"] = evaluate_freshness(
            last_successful_fetch_at=prior_success,
            fetch_failed=True,
            window=window,
            now=current,
            consecutive_failures=failures,
        )
        changes.append(
            {
                "change_id": f"chg_{source_id}_{change_stamp}",
                "source_id": source_id,
                "detected_at": checked_at,
                "previous_hash": prior.get("content_hash", ""),
                "new_hash": "",
                "change_type": "SOURCE_UNAVAILABLE",
                "previous_version": prior.get("current_source_version", ""),
                "new_version": prior.get("current_source_version", ""),
                "affected_rule_ids": "",
                "review_status": "INFO",
                "reviewed_by": "",
                "reviewed_at": "",
                "activation_status": "NOT_ACTIVATED",
                "notes": (
                    "Fetch failed; last_successful_fetch_at unchanged. "
                    f"Error: {updated['fetch_error']}"
                ),
            }
        )
        return updated, changes

    new_hash = content_hash(fetch.body)
    new_version = str(
        source_row.get("current_source_version")
        or source_row.get("version")
        or ""
    )
    change_type = classify_change(
        previous_hash=prior.get("content_hash", ""),
        new_hash=new_hash,
        previous_etag=prior.get("http_etag", ""),
        new_etag=fetch.etag,
        previous_last_modified=prior.get("http_last_modified", ""),
        new_last_modified=fetch.last_modified,
        previous_version=prior.get("current_source_version", ""),
        new_version=new_version,
        fetch_ok=True,
    )

    updated["last_successful_fetch_at"] = checked_at
    updated["http_etag"] = fetch.etag
    updated["http_last_modified"] = fetch.last_modified
    updated["fetch_status"] = "OK"
    updated["fetch_error"] = ""
    updated["consecutive_failures"] = "0"
    updated["freshness_status"] = "CURRENT"
    updated["previous_source_version"] = prior.get("current_source_version", "")
    updated["current_source_version"] = str(
        source_row.get("current_source_version") or source_row.get("version") or ""
    )

    changes = []
    if change_type != "NO_CHANGE":
        if change_type in {
            "POTENTIAL_REGULATORY_CHANGE",
            "CONFIRMED_REGULATORY_CHANGE",
            "METADATA_CHANGE",
            "COSMETIC_CHANGE",
            "BASELINE_CAPTURED",
        }:
            if change_type != "BASELINE_CAPTURED":
                updated["last_changed_at"] = checked_at
            updated["content_hash"] = new_hash
        else:
            updated["content_hash"] = new_hash
        change_stamp = checked_at.replace(":", "").replace("-", "")
        reviewable = is_reviewable_change(
            {
                "change_type": change_type,
                "previous_version": prior.get("current_source_version", ""),
                "new_version": updated["current_source_version"],
            }
        )
        changes.append(
            {
                "change_id": f"chg_{source_id}_{change_stamp}",
                "source_id": source_id,
                "detected_at": checked_at,
                "previous_hash": prior.get("content_hash", ""),
                "new_hash": new_hash,
                "change_type": change_type,
                "previous_version": prior.get("current_source_version", ""),
                "new_version": updated["current_source_version"],
                "affected_rule_ids": "",
                "review_status": "PENDING_REVIEW" if reviewable else "INFO",
                "reviewed_by": "",
                "reviewed_at": "",
                "activation_status": "NOT_ACTIVATED",
                "notes": (
                    "Detected change recorded; legal rules are NOT auto-activated."
                    if reviewable
                    else (
                        "BASELINE_CAPTURED: first successful hash stored; "
                        "not a legal amendment."
                        if change_type == "BASELINE_CAPTURED"
                        else "Non-reviewable / non-activating change event."
                    )
                ),
            }
        )
    else:
        # Preserve prior hash on no-change; seed hash if first successful check.
        if not updated.get("content_hash"):
            updated["content_hash"] = new_hash
        else:
            updated["content_hash"] = prior.get("content_hash", new_hash)

    return updated, changes


def run_monitor(
    repo_root: Path,
    *,
    authority: str | None = None,
    source_id: str | None = None,
    fetch_fn: FetchFn | None = None,
    config_path: Path | None = None,
    now: datetime | None = None,
    write_pending_review: bool = True,
) -> dict[str, Any]:
    """Run on-demand / scheduler-ready official-source monitoring.

    Runtime STATE is written to durable_state first, then mirrored to bundled
    fallback. Workflow persistence must copy from durable_state.
    """
    root = Path(repo_root)
    cfg_path = config_path or (root / "config" / "regulatory_monitoring.yaml")
    config = load_monitor_config(cfg_path)
    sources = load_regulatory_sources(root / "data/reference/regulatory_sources.csv")
    rules = load_regulatory_rules(root / "config/regulatory_rules.csv")
    durable_dir = root / config.durable_state_dir
    try:
        durable_dir.mkdir(parents=True, exist_ok=True)
        if not durable_dir.is_dir():
            raise OSError(f"durable_state path is not a directory: {durable_dir}")
    except OSError as exc:
        failed_summary = build_monitoring_summary(
            freshness_rows=[],
            change_rows=[],
            conflict_rows=[],
            now=now,
            state_source=STATE_SOURCE_BUNDLED,
            persistence_status="STATE_PERSISTENCE_FAILED",
            critical_source_ids=list(config.critical_source_ids),
        )
        return {
            "checked": 0,
            "changes": [],
            "reviewable_changes": [],
            "review_required": False,
            "pending_review_rules_marked": 0,
            "auto_activate_rules": config.auto_activate_rules,
            "freshness_path": str(durable_dir / "source_freshness_state.csv"),
            "change_log_path": str(durable_dir / "regulatory_change_log.csv"),
            "summary_path": str(durable_dir / "monitoring_summary.json"),
            "change_report_path": str(durable_dir / "regulatory_change_report.md"),
            "runtime_state_dir": str(durable_dir),
            "summary": failed_summary,
            "monitoring_health": HEALTH_STATE_PERSISTENCE_FAILED,
            "fail_safe_states": sorted(FAIL_SAFE_STATES),
            "operable_rule_count": int(len(operable_rules(rules))),
            "active_non_pending_count": int(len(active_rules(rules))),
            "high_priority_source_ids": list(config.high_priority_source_ids),
            "critical_source_ids": list(config.critical_source_ids),
            "persistence": {
                "ok": False,
                "status": "STATE_PERSISTENCE_FAILED",
                "destination": str(durable_dir),
                "error": str(exc),
                "consecutive_persistence_failures": 1,
                "files_written": [],
                "monitoring_state_branch": config.monitoring_state_branch,
            },
            "monitoring_complete": False,
            "state_source": STATE_SOURCE_BUNDLED,
        }
    # Primary runtime paths (source of truth for regulatory-monitor-state).
    freshness_path = durable_dir / "source_freshness_state.csv"
    change_path = durable_dir / "regulatory_change_log.csv"
    conflict_path = durable_dir / "regulatory_conflict_log.csv"
    summary_path = durable_dir / "monitoring_summary.json"
    report_path = durable_dir / "regulatory_change_report.md"
    # Seed from prior durable state, else bundled bootstrap.
    if not freshness_path.is_file():
        bundled_fresh = root / config.freshness_state_path
        if bundled_fresh.is_file():
            shutil.copy2(bundled_fresh, freshness_path)
    if not change_path.is_file():
        bundled_change = root / config.change_log_path
        if bundled_change.is_file():
            shutil.copy2(bundled_change, change_path)
    if not conflict_path.is_file():
        bundled_conflict = root / config.conflict_log_path
        if bundled_conflict.is_file():
            shutil.copy2(bundled_conflict, conflict_path)

    prior_rows = {
        row["source_id"]: row
        for row in _read_csv_dict(freshness_path, FRESHNESS_COLUMNS)
    }
    change_rows = _read_csv_dict(change_path, CHANGE_LOG_COLUMNS)
    updated_freshness: list[dict[str, str]] = []
    new_changes: list[dict[str, str]] = []
    pending_rule_ids: list[str] = []

    selected = sources
    if authority:
        selected = selected[
            selected["authority"].str.contains(authority, case=False, na=False)
        ]
    if source_id:
        selected = selected[selected["source_id"] == source_id]
    selected = selected[selected["monitor_enabled"].str.lower() == "true"]

    for _, source in selected.iterrows():
        source_dict = source.to_dict()
        prior = prior_rows.get(
            source_dict["source_id"],
            {col: "" for col in FRESHNESS_COLUMNS},
        )
        alt_id = config.alternate_official_monitoring_sources.get(
            str(source_dict["source_id"]), ""
        )
        alternate_source_row = None
        alternate_prior = None
        if alt_id:
            alt_matches = sources[sources["source_id"] == alt_id]
            if not alt_matches.empty:
                alternate_source_row = alt_matches.iloc[0].to_dict()
                alternate_prior = prior_rows.get(
                    alt_id, {col: "" for col in FRESHNESS_COLUMNS}
                )
        updated, changes = check_source(
            source_dict,
            prior=prior,
            config=config,
            fetch_fn=fetch_fn,
            now=now,
            alternate_source_row=alternate_source_row,
            alternate_prior=alternate_prior,
        )
        prior_rows[source_dict["source_id"]] = updated
        for change in changes:
            affected = rules.loc[
                rules["source_id"] == source_dict["source_id"], "rule_id"
            ].tolist()
            change["affected_rule_ids"] = ";".join(affected)
            new_changes.append(change)
            change_rows.append(change)
            if (
                write_pending_review
                and config.mark_affected_rules_pending_review
                and not config.auto_activate_rules
                and is_reviewable_change(change)
            ):
                pending_rule_ids.extend(affected)
        if config.rate_limit_seconds > 0 and fetch_fn is None:
            time.sleep(config.rate_limit_seconds)

    for sid, row in prior_rows.items():
        if row.get("source_id"):
            if not row.get("monitor_criticality"):
                row = {
                    **row,
                    "monitor_criticality": source_criticality(sid, config),
                }
            updated_freshness.append(row)
        else:
            updated_freshness.append(
                {
                    **row,
                    "source_id": sid,
                    "monitor_criticality": source_criticality(sid, config),
                }
            )

    dedup: dict[str, dict[str, str]] = {}
    for row in updated_freshness:
        dedup[row["source_id"]] = row
    freshness_list = list(dedup.values())
    _write_csv_dict(freshness_path, FRESHNESS_COLUMNS, freshness_list)
    _write_csv_dict(change_path, CHANGE_LOG_COLUMNS, change_rows)

    pending_count = 0
    if pending_rule_ids:
        pending_count = mark_rules_pending_review(
            root / "config/regulatory_rules.csv",
            sorted(set(pending_rule_ids)),
        )

    if not conflict_path.exists():
        _write_csv_dict(conflict_path, CONFLICT_COLUMNS, [])
    conflict_rows = _read_csv_dict(conflict_path, CONFLICT_COLUMNS)

    review_needed = should_open_review_activity(new_changes)
    interim_summary = build_monitoring_summary(
        freshness_rows=freshness_list,
        change_rows=change_rows,
        conflict_rows=conflict_rows,
        new_changes=new_changes,
        now=now,
        state_source=STATE_SOURCE_DURABLE,
        persistence_status="PENDING",
        critical_source_ids=list(config.critical_source_ids),
    )
    review_needed = review_needed or bool(
        interim_summary.get("regulatory_conflicts")
    )
    write_monitoring_summary(summary_path, interim_summary)
    if review_needed:
        write_change_report(
            report_path,
            summary=interim_summary,
            changes=new_changes,
        )

    persistence = persist_monitoring_state(root, config=config, now=now)
    summary = build_monitoring_summary(
        freshness_rows=freshness_list,
        change_rows=change_rows,
        conflict_rows=conflict_rows,
        new_changes=new_changes,
        now=now,
        state_source=(
            STATE_SOURCE_DURABLE if persistence.ok else STATE_SOURCE_BUNDLED
        ),
        consecutive_persistence_failures=persistence.consecutive_persistence_failures,
        persistence_status=persistence.status,
        critical_source_ids=list(config.critical_source_ids),
    )
    write_monitoring_summary(summary_path, summary)
    if persistence.ok:
        persistence = persist_monitoring_state(root, config=config, now=now)
        if not persistence.ok:
            summary = build_monitoring_summary(
                freshness_rows=freshness_list,
                change_rows=change_rows,
                conflict_rows=conflict_rows,
                new_changes=new_changes,
                now=now,
                state_source=STATE_SOURCE_BUNDLED,
                consecutive_persistence_failures=(
                    persistence.consecutive_persistence_failures
                ),
                persistence_status=persistence.status,
                critical_source_ids=list(config.critical_source_ids),
            )
            write_monitoring_summary(summary_path, summary)

    health = evaluate_monitoring_health(summary)
    monitoring_complete = bool(persistence.ok) and health not in {
        HEALTH_STATE_PERSISTENCE_FAILED,
        HEALTH_STATE_PERSISTENCE_MISMATCH,
    }
    return {
        "checked": int(len(selected)),
        "changes": new_changes,
        "reviewable_changes": [
            c for c in new_changes if is_reviewable_change(c)
        ],
        "review_required": review_needed,
        "pending_review_rules_marked": pending_count,
        "auto_activate_rules": config.auto_activate_rules,
        "freshness_path": str(freshness_path),
        "change_log_path": str(change_path),
        "summary_path": str(summary_path),
        "change_report_path": str(report_path),
        "runtime_state_dir": str(durable_dir),
        "summary": summary,
        "monitoring_health": health,
        "fail_safe_states": sorted(FAIL_SAFE_STATES),
        "operable_rule_count": int(len(operable_rules(rules))),
        "active_non_pending_count": int(len(active_rules(rules))),
        "high_priority_source_ids": list(config.high_priority_source_ids),
        "critical_source_ids": list(config.critical_source_ids),
        "persistence": {
            "ok": persistence.ok,
            "status": persistence.status,
            "destination": persistence.destination,
            "error": persistence.error,
            "consecutive_persistence_failures": (
                persistence.consecutive_persistence_failures
            ),
            "files_written": list(persistence.files_written),
            "monitoring_state_branch": config.monitoring_state_branch,
        },
        "monitoring_complete": monitoring_complete,
        "state_source": summary.get("state_source"),
    }


def last_checked_summary(repo_root: Path) -> dict[str, Any]:
    """Backend payload for future UI 'Regulatory data last checked' display."""
    cfg = load_monitor_config(Path(repo_root) / "config/regulatory_monitoring.yaml")
    rows = _read_csv_dict(Path(repo_root) / cfg.freshness_state_path, FRESHNESS_COLUMNS)
    if not rows:
        return {
            "regulatory_data_last_checked": "",
            "source": "",
            "status": "CHECK_DUE",
        }
    successful = [r for r in rows if r.get("last_successful_fetch_at")]
    if not successful:
        return {
            "regulatory_data_last_checked": "",
            "source": "",
            "status": "FETCH_FAILED",
        }
    latest = max(successful, key=lambda r: r.get("last_successful_fetch_at", ""))
    sources = load_regulatory_sources(
        Path(repo_root) / "data/reference/regulatory_sources.csv"
    )
    match = sources.loc[sources["source_id"] == latest["source_id"]]
    authority = (
        str(match.iloc[0]["authority"]) if not match.empty else latest["source_id"]
    )
    return {
        "regulatory_data_last_checked": latest.get("last_successful_fetch_at", ""),
        "source": authority,
        "status": latest.get("freshness_status", "CHECK_DUE"),
        "source_id": latest.get("source_id", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="carbon_ledger.regulatory_monitor",
        description=(
            "Official regulatory-source monitor. Detects changes and records "
            "reviewable events; never auto-activates legal rules."
        ),
    )
    parser.add_argument(
        "--check-all",
        action="store_true",
        help="Check all monitor-enabled official sources.",
    )
    parser.add_argument(
        "--authority",
        default=None,
        help="Filter sources by authority substring (e.g. FSC).",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Check a single source_id.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root (default: current directory).",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print last-checked / freshness summary and exit.",
    )
    parser.add_argument(
        "--health-gate",
        action="store_true",
        help=(
            "Evaluate durable monitoring health and exit non-zero on "
            "CRITICAL_SOURCE_FAILURE or persistence failures."
        ),
    )
    parser.add_argument(
        "--verify-persisted-summary",
        default=None,
        help=(
            "Path to persisted monitoring_summary.json to compare against "
            "runtime durable summary (STATE_PERSISTENCE_MISMATCH on diff)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    config = load_monitor_config(root / "config" / "regulatory_monitoring.yaml")
    durable_summary_path = (
        root / config.durable_state_dir / "monitoring_summary.json"
    )
    if args.status:
        freshness = get_regulatory_freshness(root)
        print("Regulatory data last checked:", freshness["last_global_check_at"])
        print("Last successful check:", freshness["last_successful_check_at"])
        print("Overall freshness:", freshness["overall_regulatory_freshness"])
        print("Analysis allowed:", freshness["analysis_allowed"])
        print("State:", freshness["state"])
        print("State source:", freshness.get("state_source"))
        print("Persistence status:", freshness.get("persistence_status"))
        print(
            "Critical sources failed:",
            freshness.get("summary", {}).get("critical_sources_failed"),
        )
        print(
            "Monitoring health:",
            freshness.get("summary", {}).get("monitoring_health"),
        )
        print("Sources current/stale/failed:",
              freshness["sources_current"],
              freshness["sources_stale"],
              freshness["sources_failed"])
        print("Changes pending review:", freshness["changes_pending_review"])
        print("Regulatory conflicts:", freshness["regulatory_conflicts"])
        return 0
    if args.verify_persisted_summary:
        if not durable_summary_path.is_file():
            print(
                "ERROR: runtime durable monitoring_summary.json missing",
                file=sys.stderr,
            )
            return 5
        runtime = json.loads(durable_summary_path.read_text(encoding="utf-8"))
        ok, mismatches = verify_persisted_state_matches_runtime(
            runtime, Path(args.verify_persisted_summary)
        )
        if not ok:
            print(
                "ERROR: STATE_PERSISTENCE_MISMATCH — "
                f"keys={mismatches}",
                file=sys.stderr,
            )
            return 5
        print("Persisted summary matches runtime durable summary.")
        return 0
    if args.health_gate:
        if not durable_summary_path.is_file():
            print(
                "ERROR: FRESHNESS_STATE_UNAVAILABLE — durable summary missing",
                file=sys.stderr,
            )
            return 4
        summary = json.loads(durable_summary_path.read_text(encoding="utf-8"))
        health = evaluate_monitoring_health(summary)
        print("Monitoring health:", health)
        print("Overall freshness:", summary.get("overall_regulatory_freshness"))
        print("Critical sources failed:", summary.get("critical_sources_failed"))
        print("Persistence status:", summary.get("persistence_status"))
        if health == HEALTH_STATE_PERSISTENCE_MISMATCH:
            return 5
        if health == HEALTH_STATE_PERSISTENCE_FAILED:
            return 3
        if health == HEALTH_CRITICAL_SOURCE_FAILURE:
            print(
                "ERROR: CRITICAL_SOURCE_FAILURE — not a successful monitoring run.",
                file=sys.stderr,
            )
            return 4
        return 0
    if not (args.check_all or args.authority or args.source):
        parser.print_help()
        return 2
    result = run_monitor(
        root,
        authority=args.authority,
        source_id=args.source,
    )
    print(f"Checked sources: {result['checked']}")
    print(f"Change events: {len(result['changes'])}")
    print(f"Reviewable changes: {len(result['reviewable_changes'])}")
    print(f"Review required: {result['review_required']}")
    for change in result["changes"]:
        print(
            f"- {change['source_id']}: {change['change_type']} "
            f"(activation={change['activation_status']})"
        )
    print(
        "Pending-review rules marked:",
        result["pending_review_rules_marked"],
    )
    print("Auto-activate rules:", result["auto_activate_rules"])
    print("Summary:", result["summary_path"])
    print("Runtime state dir:", result.get("runtime_state_dir"))
    persistence = result.get("persistence") or {}
    print("Persistence status:", persistence.get("status"))
    print("Durable state destination:", persistence.get("destination"))
    print("Monitoring health:", result.get("monitoring_health"))
    print("Monitoring complete:", result.get("monitoring_complete"))
    print(
        "Critical sources failed:",
        (result.get("summary") or {}).get("critical_sources_failed"),
    )
    if not result.get("monitoring_complete", False):
        print(
            "ERROR: STATE_PERSISTENCE_FAILED — run is not fully successful.",
            file=sys.stderr,
        )
        return 3
    health = str(result.get("monitoring_health") or "")
    if health == HEALTH_CRITICAL_SOURCE_FAILURE:
        print(
            "ERROR: CRITICAL_SOURCE_FAILURE — workflow must not report green success.",
            file=sys.stderr,
        )
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())


# Keep imported helpers referenced for external tests / future engines.
__all__ = [
    "CHANGE_TYPES",
    "REVIEWABLE_CHANGE_TYPES",
    "STATE_SOURCE_BUNDLED",
    "STATE_SOURCE_DURABLE",
    "STATE_SOURCE_UNAVAILABLE",
    "HEALTH_CRITICAL_SOURCE_FAILURE",
    "HEALTH_MONITORING_CURRENT",
    "HEALTH_MONITORING_PARTIAL",
    "HEALTH_STATE_PERSISTENCE_FAILED",
    "HEALTH_STATE_PERSISTENCE_MISMATCH",
    "FetchResult",
    "MonitorConfig",
    "PersistenceResult",
    "assert_sources_fresh_for_analysis",
    "build_monitoring_summary",
    "build_official_source_ssl_context",
    "classify_change",
    "compare_monitoring_summaries",
    "content_hash",
    "default_fetch",
    "evaluate_freshness",
    "evaluate_monitoring_health",
    "fail_safe_state_for_freshness",
    "get_regulatory_freshness",
    "hostname_in_tls_fallback_allowlist",
    "is_allowed_monitoring_state_file",
    "is_reviewable_change",
    "is_x509_strict_compatibility_error",
    "last_checked_summary",
    "load_monitor_config",
    "main",
    "mark_rules_pending_review",
    "normalize_content",
    "outranks",
    "persist_monitoring_state",
    "read_persistence_status",
    "record_conflict",
    "resolve_monitoring_state_dir",
    "run_monitor",
    "should_open_review_activity",
    "source_criticality",
    "verify_persisted_state_matches_runtime",
    "write_change_report",
    "write_monitoring_summary",
    "write_persistence_status",
]
