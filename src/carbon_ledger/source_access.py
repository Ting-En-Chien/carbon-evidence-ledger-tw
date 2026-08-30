"""Source access-policy registry and pre-HTTP enforcement (Stage 3B.1).

A public webpage is NOT automatically crawler-authorised.
Network I/O must not occur until an approved access basis is confirmed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode, urlparse

import pandas as pd

ACCESS_MODES = frozenset(
    {
        "OFFICIAL_API",
        "OFFICIAL_OPEN_DATA",
        "AUTHORIZED_WEB_MONITORING",
        "OFFICIAL_EMAIL_ALERT",
        "MANUAL_REFERENCE",
        "MANUAL_OR_LICENSED",
        "LICENSED_FEED",
        "DISABLED",
    }
)

ACCESS_POLICY_STATUSES = frozenset(
    {
        "EXPLICITLY_ALLOWED",
        "ALLOWED_VIA_OFFICIAL_OPEN_DATA",
        "RESTRICTED_AUTOMATION",
        "REQUIRES_PERMISSION",
        "TERMS_UNCLEAR",
        "MANUAL_ONLY",
    }
)

POLICY_COLUMNS = (
    "source_id",
    "hostname",
    "access_mode",
    "automated_access_allowed",
    "access_policy_status",
    "access_policy_url",
    "access_policy_checked_at",
    "content_use_status",
    "attribution_required",
    "preferred_access_method",
    "preferred_access_url",
    "change_signal_method",
    "notes",
)

# Fetch outcomes that are policy decisions — not network failures.
FETCH_STATUS_POLICY_SKIPPED = "POLICY_SKIPPED"
FETCH_STATUS_ACCESS_POLICY_REVIEW_REQUIRED = "ACCESS_POLICY_REVIEW_REQUIRED"
FETCH_STATUS_CREDENTIAL_REQUIRED = "CREDENTIAL_REQUIRED"
CHANGE_TYPE_POLICY_SKIPPED = "POLICY_SKIPPED"
CHANGE_TYPE_CREDENTIAL_REQUIRED = "CREDENTIAL_REQUIRED"

# Supporting MOENV open dataset (not a legal/regulatory identity).
MOENV_GHG_OPEN_DATA_SOURCE_ID = "src_tw_moenv_ghg_open_data"
MOENV_API_KEY_ENV = "MOENV_API_KEY"
MOENV_GHG_P01_ENDPOINT = "https://data.moenv.gov.tw/api/v2/ghg_p_01"


@dataclass(frozen=True)
class SourceAccessPolicy:
    source_id: str
    hostname: str = ""
    access_mode: str = "MANUAL_REFERENCE"
    automated_access_allowed: bool = False
    access_policy_status: str = "TERMS_UNCLEAR"
    access_policy_url: str = ""
    access_policy_checked_at: str = ""
    content_use_status: str = "METADATA_ONLY"
    attribution_required: bool = True
    preferred_access_method: str = "MANUAL_REFERENCE"
    preferred_access_url: str = ""
    change_signal_method: str = "MANUAL_ADMIN_SIGNAL"
    notes: str = ""

    @property
    def expects_scheduled_http(self) -> bool:
        return bool(self.automated_access_allowed) and self.access_mode in {
            "OFFICIAL_API",
            "OFFICIAL_OPEN_DATA",
            "AUTHORIZED_WEB_MONITORING",
            "LICENSED_FEED",
        }


def default_access_policies_path(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "data" / "reference" / "source_access_policies.csv"


def _as_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes"}


def load_source_access_policies(
    path: Path | None = None,
) -> dict[str, SourceAccessPolicy]:
    """Load access policies; unknown sources default to deny-automation."""
    policy_path = Path(path) if path is not None else default_access_policies_path()
    if not policy_path.is_file():
        return {}
    frame = pd.read_csv(policy_path, dtype=str).fillna("")
    policies: dict[str, SourceAccessPolicy] = {}
    for _, row in frame.iterrows():
        sid = str(row.get("source_id") or "").strip()
        if not sid:
            continue
        mode = str(row.get("access_mode") or "MANUAL_REFERENCE").strip()
        status = str(row.get("access_policy_status") or "TERMS_UNCLEAR").strip()
        allowed = _as_bool(row.get("automated_access_allowed"))
        # Unknown / unclear / restricted statuses can never allow automation.
        if status in {
            "TERMS_UNCLEAR",
            "REQUIRES_PERMISSION",
            "RESTRICTED_AUTOMATION",
            "MANUAL_ONLY",
        }:
            allowed = False
        if mode not in ACCESS_MODES:
            mode = "MANUAL_REFERENCE"
            allowed = False
        if status not in ACCESS_POLICY_STATUSES:
            status = "TERMS_UNCLEAR"
            allowed = False
        policies[sid] = SourceAccessPolicy(
            source_id=sid,
            hostname=str(row.get("hostname") or ""),
            access_mode=mode,
            automated_access_allowed=allowed,
            access_policy_status=status,
            access_policy_url=str(row.get("access_policy_url") or ""),
            access_policy_checked_at=str(row.get("access_policy_checked_at") or ""),
            content_use_status=str(row.get("content_use_status") or "METADATA_ONLY"),
            attribution_required=_as_bool(row.get("attribution_required")),
            preferred_access_method=str(
                row.get("preferred_access_method") or "MANUAL_REFERENCE"
            ),
            preferred_access_url=str(row.get("preferred_access_url") or ""),
            change_signal_method=str(
                row.get("change_signal_method") or "MANUAL_ADMIN_SIGNAL"
            ),
            notes=str(row.get("notes") or ""),
        )
    return policies


def policy_for_source(
    source_id: str,
    policies: dict[str, SourceAccessPolicy] | None = None,
    *,
    repo_root: Path | None = None,
) -> SourceAccessPolicy:
    """Return policy for source_id; default deny when missing/unknown."""
    table = policies if policies is not None else load_source_access_policies(
        default_access_policies_path(repo_root)
    )
    existing = table.get(str(source_id))
    if existing is not None:
        return existing
    return SourceAccessPolicy(
        source_id=str(source_id),
        automated_access_allowed=False,
        access_mode="MANUAL_REFERENCE",
        access_policy_status="TERMS_UNCLEAR",
        notes="No access policy row; default automated_access_allowed=false.",
    )


def resolve_fetch_url(source_row: dict[str, str], policy: SourceAccessPolicy) -> str:
    """Prefer approved access URL when automation is allowed."""
    if policy.expects_scheduled_http and policy.preferred_access_url:
        return str(policy.preferred_access_url)
    return str(source_row.get("official_url") or "").strip()


def required_credential_env(source_id: str) -> str:
    """Return env var name required before HTTP, or empty when none."""
    if str(source_id) == MOENV_GHG_OPEN_DATA_SOURCE_ID:
        return MOENV_API_KEY_ENV
    return ""


def redact_secrets(text: str, secrets: list[str] | None = None) -> str:
    """Remove credential values from logs / state notes."""
    out = str(text or "")
    for secret in secrets or []:
        if secret and secret in out:
            out = out.replace(secret, "[REDACTED]")
    out = re.sub(r"(api_key=)[^&\s]+", r"\1[REDACTED]", out, flags=re.IGNORECASE)
    return out


def build_moenv_ghg_p01_url(*, api_key: str, limit: int = 1) -> str:
    """Minimal authorised GHG_P_01 probe URL (never log with key)."""
    query = urlencode(
        {
            "format": "json",
            "offset": "0",
            "limit": str(max(1, int(limit))),
            "api_key": str(api_key),
        }
    )
    return f"{MOENV_GHG_P01_ENDPOINT}?{query}"


def resolve_authorized_request_url(
    source_id: str,
    source_row: dict[str, str],
    policy: SourceAccessPolicy,
    *,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Resolve fetch URL after credential checks.

    Returns (url, missing_credential_env).
    When missing_credential_env is non-empty, url is empty and no HTTP may occur.
    """
    env = environ if environ is not None else os.environ
    cred_env = required_credential_env(source_id)
    if cred_env:
        api_key = str(env.get(cred_env) or "").strip()
        if not api_key:
            return "", cred_env
        if source_id == MOENV_GHG_OPEN_DATA_SOURCE_ID:
            return build_moenv_ghg_p01_url(api_key=api_key, limit=1), ""
    return resolve_fetch_url(source_row, policy), ""


def hostname_of(url: str) -> str:
    return (urlparse(str(url)).hostname or "").lower()


def is_ifrs_foundation_host(host_or_url: str) -> bool:
    host = hostname_of(host_or_url) if "://" in host_or_url else host_or_url.lower()
    return host == "www.ifrs.org" or host.endswith(".ifrs.org")


def is_swagger_documentation_url(url: str) -> bool:
    text = str(url or "").lower()
    return "swagger" in text and "data.moenv.gov.tw" in text


def access_coverage_metrics(
    policies: dict[str, SourceAccessPolicy],
) -> dict[str, int]:
    values = list(policies.values())
    return {
        "total_reference_sources": len(values),
        "automated_sources_expected": sum(
            1 for p in values if p.expects_scheduled_http
        ),
        "official_api_sources": sum(
            1 for p in values if p.access_mode == "OFFICIAL_API"
        ),
        "official_open_data_sources": sum(
            1 for p in values if p.access_mode == "OFFICIAL_OPEN_DATA"
        ),
        "authorized_web_sources": sum(
            1 for p in values if p.access_mode == "AUTHORIZED_WEB_MONITORING"
        ),
        "manual_reference_sources": sum(
            1
            for p in values
            if p.access_mode in {"MANUAL_REFERENCE", "MANUAL_OR_LICENSED", "DISABLED"}
        ),
        "restricted_automation_sources": sum(
            1
            for p in values
            if p.access_policy_status == "RESTRICTED_AUTOMATION"
            or p.access_mode == "OFFICIAL_EMAIL_ALERT"
        ),
        "email_alert_signal_sources": sum(
            1 for p in values if p.change_signal_method == "OFFICIAL_EMAIL_ALERT"
        ),
        "supporting_open_data_sources": sum(
            1 for p in values if p.source_id == MOENV_GHG_OPEN_DATA_SOURCE_ID
        ),
    }


__all__ = [
    "ACCESS_MODES",
    "ACCESS_POLICY_STATUSES",
    "CHANGE_TYPE_CREDENTIAL_REQUIRED",
    "CHANGE_TYPE_POLICY_SKIPPED",
    "FETCH_STATUS_ACCESS_POLICY_REVIEW_REQUIRED",
    "FETCH_STATUS_CREDENTIAL_REQUIRED",
    "FETCH_STATUS_POLICY_SKIPPED",
    "MOENV_API_KEY_ENV",
    "MOENV_GHG_OPEN_DATA_SOURCE_ID",
    "MOENV_GHG_P01_ENDPOINT",
    "SourceAccessPolicy",
    "access_coverage_metrics",
    "build_moenv_ghg_p01_url",
    "hostname_of",
    "is_ifrs_foundation_host",
    "is_swagger_documentation_url",
    "load_source_access_policies",
    "policy_for_source",
    "redact_secrets",
    "required_credential_env",
    "resolve_authorized_request_url",
    "resolve_fetch_url",
]
