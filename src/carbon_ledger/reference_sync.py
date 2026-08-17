"""Official reference synchronization for Carbon Evidence Ledger (Phase 10A).

Network-aware maintenance stays here. Calculation modules must never import
HTTP clients or require live internet access.

Flow: discover → download → hash/version → parse → candidate → validate →
activate. Newly fetched numbers never become active automatically.
"""

from __future__ import annotations

import csv
import hashlib
import html as html_module
import io
import math
import re
import ssl
from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)

import pandas as pd

PARSER_VERSION = "reference_sync_v1"
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0

# Transparent application identity for official-source GETs (not a browser UA).
OFFICIAL_USER_AGENT = (
    "CarbonEvidenceLedger/0.1 "
    "(+https://github.com/AppleJustin/carbon-evidence-ledger-tw)"
)
OFFICIAL_REQUEST_HEADERS = {
    "User-Agent": OFFICIAL_USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
}

TLS_MODE_DEFAULT = "default"
TLS_MODE_PYTHON313_RELAXED_X509_STRICT = "python313_relaxed_x509_strict"
TLS_VERIFICATION_VERIFIED = "verified"
ALLOWED_TLS_COMPATIBILITY_MODES = frozenset(
    {
        TLS_MODE_DEFAULT,
        TLS_MODE_PYTHON313_RELAXED_X509_STRICT,
    }
)

FETCH_MODE_FETCH = "fetch"
FETCH_MODE_PROVENANCE_ONLY = "provenance_only"
ALLOWED_FETCH_MODES = frozenset(
    {
        FETCH_MODE_FETCH,
        FETCH_MODE_PROVENANCE_ONLY,
    }
)

RETRIEVAL_PARSE_LANDING = "parse_landing"
RETRIEVAL_DISCOVER_ATTACHMENT = "discover_attachment"
RETRIEVAL_PROVENANCE_ONLY = "provenance_only"
ALLOWED_RETRIEVAL_STRATEGIES = frozenset(
    {
        RETRIEVAL_PARSE_LANDING,
        RETRIEVAL_DISCOVER_ATTACHMENT,
        RETRIEVAL_PROVENANCE_ONLY,
    }
)

REF_TYPE_ELECTRICITY = "electricity_factor"
REF_TYPE_ELECTRICITY_ENTERPRISE = "electricity_factor_enterprise_inventory"
REF_TYPE_ELECTRICITY_UPSTREAM = "electricity_factor_upstream"
ELECTRICITY_CANDIDATE_REF_TYPES = frozenset(
    {
        REF_TYPE_ELECTRICITY,
        REF_TYPE_ELECTRICITY_ENTERPRISE,
    }
)

SOURCE_COLUMNS = [
    "source_id",
    "authority",
    "reference_type",
    "canonical_url",
    "upstream_canonical_url",
    "upstream_factor_authority",
    "landing_url",
    "expected_file_type",
    "parser_type",
    "allowed_domain",
    "tls_compatibility_mode",
    "fetch_mode",
    "retrieval_strategy",
    "active",
    "notes",
]

SNAPSHOT_COLUMNS = [
    "snapshot_id",
    "source_id",
    "authority",
    "reference_type",
    "canonical_url",
    "upstream_canonical_url",
    "upstream_factor_authority",
    "discovered_url",
    "retrieved_url",
    "retrieved_host",
    "retrieved_at",
    "publication_date",
    "file_name",
    "media_type",
    "sha256",
    "byte_size",
    "parser_version",
    "local_path",
    "status",
    "tls_verification",
    "tls_compatibility_mode",
    "notes",
]

CANDIDATE_COLUMNS = [
    "candidate_id",
    "snapshot_id",
    "source_id",
    "reference_type",
    "factor_year",
    "valid_from",
    "valid_to",
    "geography",
    "activity_type",
    "combustion_context",
    "gas",
    "factor_value",
    "numerator_unit",
    "denominator_unit",
    "factor_category",
    "intended_use",
    "applicability_notes",
    "upstream_factor_authority",
    "publication_date",
    "source_locator",
    "validation_status",
    "lifecycle_status",
    "parser_version",
    "reason",
    "notes",
]

ACTIVATION_COLUMNS = [
    "activation_id",
    "candidate_id",
    "snapshot_id",
    "factor_id",
    "factor_year",
    "factor_category",
    "factor_value",
    "numerator_unit",
    "denominator_unit",
    "activated_at",
    "activated_by",
    "registry_table",
    "sha256",
    "source_id",
    "upstream_factor_authority",
    "retrieved_url",
    "notes",
]

RULE_COLUMNS = [
    "rule_id",
    "reference_type",
    "jurisdiction",
    "condition",
    "fallback_behavior",
    "valid_from",
    "valid_to",
    "source_reference_id",
    "source_locator",
    "rule_version",
    "active",
    "notes",
]

HEATING_VALUE_COLUMNS = [
    "heating_value_id",
    "fuel_type",
    "fuel_subtype",
    "heating_value",
    "unit",
    "high_heating_value",
    "high_heating_value_unit",
    "factor_year",
    "geography",
    "authority",
    "valid_from",
    "valid_to",
    "source_reference_id",
    "source_locator",
    "snapshot_id",
    "snapshot_sha256",
    "snapshot_local_path",
    "status",
    "notes",
]

LIFECYCLE_DISCOVERED = "discovered"
LIFECYCLE_DOWNLOADED = "downloaded"
LIFECYCLE_PARSED = "parsed"
LIFECYCLE_VALIDATED = "validated"
LIFECYCLE_CANDIDATE = "candidate"
LIFECYCLE_ACTIVE = "active"
LIFECYCLE_REJECTED = "rejected"
LIFECYCLE_SUPERSEDED = "superseded"
LIFECYCLE_NEEDS_PARSER_REVIEW = "needs_parser_review"

VALIDATION_PASSED = "passed"
VALIDATION_FAILED = "failed"
VALIDATION_PENDING = "pending"

SUPPORTED_ELECTRICITY_CATEGORIES = frozenset(
    {
        # MOENV enterprise-inventory announcement categories
        "public_sales_average",
        "industrial_enterprise_inventory",
        "residential",
        # Legacy / CSV / MOEA landing categories still accepted
        "utility_average",
        "industry",
        "inventory_specific",
        "unspecified",
    }
)

ENTERPRISE_INVENTORY_CATEGORIES = frozenset(
    {
        "industrial_enterprise_inventory",
        "industry",
    }
)
ENTERPRISE_INVENTORY_INTENDED_USES = frozenset(
    {
        "enterprise_inventory",
        "enterprise GHG inventory / disclosure",
    }
)

SUPPORTED_NUMERATOR_UNITS = frozenset({"kgCO2e", "kgCO2", "kgCH4", "kgN2O"})
SUPPORTED_DENOMINATOR_UNITS = frozenset({"kWh", "MWh", "TJ", "m3", "L"})
SUPPORTED_HEATING_UNITS = frozenset({"kcal/m3", "kcal/L", "MJ/m3", "MJ/L"})

LANDING_DISCOVERY_PARSERS = frozenset(
    {
        "tw_moea_electricity_landing_v1",
        "tw_moenv_file_downloads_landing_v1",
        "tw_moenv_news_heating_values_landing_v1",
    }
)

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Label → factor_category mappings for official electricity news HTML.
# Values are extracted from the fetched page; never hard-coded here.
_ELECTRICITY_HTML_CATEGORY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"公用售電業[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*公斤",
            re.IGNORECASE,
        ),
        "utility_average",
    ),
    (
        re.compile(
            r"工業部門[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*公斤",
            re.IGNORECASE,
        ),
        "industry",
    ),
    (
        re.compile(
            r"住宅部門[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*公斤",
            re.IGNORECASE,
        ),
        "residential",
    ),
    (
        re.compile(
            r"public\s+electricity[- ]sales\s+average[^0-9]{0,80}?"
            r"([0-9]+(?:\.[0-9]+)?)",
            re.IGNORECASE,
        ),
        "utility_average",
    ),
    (
        re.compile(
            r"industrial\s+electricity[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)",
            re.IGNORECASE,
        ),
        "industry",
    ),
    (
        re.compile(
            r"residential\s+electricity[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)",
            re.IGNORECASE,
        ),
        "residential",
    ),
)
_MOEA_HTML_PUBLICATION_DATE_RE = re.compile(
    r"(?:發布日期|刊載日期|日期)[：:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})"
)
_MOEA_HTML_ROC_YEAR_RE = re.compile(r"(?:民國)?\s*([0-9]{2,3})\s*年度")

_MOENV_NEWS_ITEM_RE = re.compile(
    r"(?is)(<div[^>]*class=[\"'][^\"']*news-item[^\"']*[\"'][^>]*>.*?</div>\s*</div>)"
)
_MOENV_NEWS_DATE_RE = re.compile(
    r"(?is)class=[\"'][^\"']*news-date[^\"']*[\"'][^>]*>\s*"
    r"([0-9]{4})[/-]([0-9]{2})[/-]([0-9]{2})"
)
_MOENV_NEWS_TITLE_RE = re.compile(
    r"(?is)class=[\"'][^\"']*news-title[^\"']*[\"'][^>]*>(.*?)</a>"
)
# Live ASP.NET NewsList markup uses news-list-* classes, not news-item.
_MOENV_LIST_ITEM_RE = re.compile(
    r"(?is)<li>\s*<span[^>]*class=(['\"])[^'\"]*news-list-date[^'\"]*\1[^>]*>"
    r"(.*?)</span>(.*?)</li>"
)
_MOENV_DATE_TOKEN_RE = re.compile(
    r"(?<!\d)(20[0-9]{2})\s*[/-]\s*(0?[1-9]|1[0-2])\s*[/-]\s*"
    r"(0?[1-9]|[12][0-9]|3[01])(?!\d)"
)
_MOENV_ANNOUNCEMENT_TITLE_TOKEN = "114年度電力排碳係數"
_MOENV_ANNOUNCEMENT_DATE = "2026-06-17"
_MOENV_FACTOR_YEAR_RE = re.compile(
    r"([0-9]{2,3})\s*年(?:度)?\s*電力排碳係數"
)
# Label → factor_category for the MOENV enterprise electricity announcement.
# Values are extracted from the bounded announcement text only.
_MOENV_ELECTRICITY_CATEGORY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Live NewsList: value appears before the "公用售電業整體" label.
    (
        re.compile(
            r"([0-9]+(?:\.[0-9]+)?)\s*公斤\s*CO2e\s*/\s*度"
            r"[^。\n]{0,80}?公用售電業整體"
        ),
        "public_sales_average",
    ),
    # Simplified fixture / alternate wording: label then value.
    (
        re.compile(
            r"公用售電業[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*公斤"
        ),
        "public_sales_average",
    ),
    (
        re.compile(
            r"產業電力排碳係數[^0-9]{0,24}?([0-9]+(?:\.[0-9]+)?)\s*公斤"
        ),
        "industrial_enterprise_inventory",
    ),
    (
        re.compile(
            r"工業部門[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*公斤"
        ),
        "industrial_enterprise_inventory",
    ),
    (
        re.compile(
            r"民生住宅電力排碳係數[^0-9]{0,24}?([0-9]+(?:\.[0-9]+)?)\s*公斤"
        ),
        "residential",
    ),
    (
        re.compile(
            r"住宅部門[^0-9]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*公斤"
        ),
        "residential",
    ),
)


class ReferenceSyncError(ValueError):
    """Structured sync failure with a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FetchResult:
    """Bytes and metadata from one allowlisted fetch."""

    url: str
    final_url: str
    content: bytes
    media_type: str
    sha256: str
    byte_size: int
    tls_verification: str = TLS_VERIFICATION_VERIFIED
    tls_compatibility_mode: str = TLS_MODE_DEFAULT
    discovered_url: str = ""


@dataclass
class ParseResult:
    """Deterministic parser output or an explicit review requirement."""

    parser_type: str
    status: str
    records: list[dict[str, Any]] = field(default_factory=list)
    publication_date: str = ""
    reason: str = ""


@dataclass
class DiscoveryResult:
    """Result of discovering an official attachment from a landing page."""

    parser_type: str
    status: str
    landing_url: str
    artifact_url: str = ""
    preferred_extension: str = ""
    candidate_urls: tuple[str, ...] = ()
    reason: str = ""


@dataclass
class ChangeReport:
    """Human-readable comparison between known and new artifacts."""

    source_id: str
    reference_type: str
    previous_snapshot_id: str
    new_snapshot_id: str
    previous_years: tuple[str, ...]
    new_years: tuple[str, ...]
    changes: tuple[str, ...]
    activated: bool = False

    def to_text(self) -> str:
        lines = [
            "Official reference update detected",
            "",
            f"Source: {self.source_id}",
            f"Reference type: {self.reference_type}",
            f"Previous snapshot: {self.previous_snapshot_id or '(none)'}",
            f"New snapshot: {self.new_snapshot_id}",
            f"Previous known years: {', '.join(self.previous_years) or '(none)'}",
            f"New candidate years: {', '.join(self.new_years) or '(none)'}",
            "Changes:",
        ]
        if self.changes:
            lines.extend(f"- {item}" for item in self.changes)
        else:
            lines.append("- (no structured field differences detected)")
        lines.append("")
        lines.append("No automatic activation has occurred yet.")
        return "\n".join(lines)


@dataclass
class SyncStatus:
    """Beginner/admin facing registry status summary."""

    electricity_years: dict[str, str]
    heating_value_latest: dict[str, str]
    last_checked_at: str
    snapshot_count: int
    candidate_count: int
    active_candidate_count: int
    source_count: int
    upstream_factor_authority: str = (
        "Taiwan Ministry of Economic Affairs / Energy Administration"
    )
    operational_source_authority: str = (
        "Taiwan Ministry of Environment / Climate Change Administration"
    )
    upstream_source_status: str = "recorded / access restricted"
    operational_source_status: str = "unchecked"
    upstream_canonical_url: str = ""
    operational_source_url: str = ""
    electricity_categories: dict[str, str] = field(default_factory=dict)


FetchCallable = Callable[..., FetchResult]


def compute_bytes_sha256(data: bytes) -> str:
    """Return lowercase SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def _blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _text(value: Any) -> str:
    if _blank(value):
        return ""
    return str(value).strip()


def _truthy(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes", "y", "active"}


def _read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame.loc[:, columns].copy()


def _write_csv(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = ""
    out.loc[:, columns].to_csv(path, index=False)


def default_paths(repo_root: Path) -> dict[str, Path]:
    """Return canonical Phase 10A path layout under a repository root."""
    root = Path(repo_root)
    return {
        "sources": root / "config" / "official_reference_sources.csv",
        "rules": root / "config" / "official_reference_rules.csv",
        "reference_dir": root / "data" / "reference",
        "snapshots_csv": root / "data" / "reference" / "reference_snapshots.csv",
        "candidates_csv": root / "data" / "reference" / "reference_candidates.csv",
        "activations_csv": root / "data" / "reference" / "reference_activations.csv",
        "emission_factors": root / "data" / "reference" / "emission_factors.csv",
        "fuel_heating_values": root / "data" / "reference" / "fuel_heating_values.csv",
        "artifact_dir": root / "data" / "reference_snapshots",
    }


def load_official_sources(path: Path | str) -> pd.DataFrame:
    """Load the allowlisted official source registry."""
    frame = _read_csv(Path(path), SOURCE_COLUMNS)
    if frame.empty:
        return frame
    required = ("source_id", "allowed_domain", "landing_url")
    missing = [col for col in required if col not in frame.columns]
    if missing:
        raise ReferenceSyncError(
            "INVALID_SOURCE_REGISTRY",
            f"Source registry missing columns: {missing}",
        )
    return frame


def load_official_reference_rules(path: Path | str) -> pd.DataFrame:
    """Load explicit official fallback/applicability rules."""
    return _read_csv(Path(path), RULE_COLUMNS)


def active_sources(sources: pd.DataFrame) -> pd.DataFrame:
    """Return rows marked active."""
    if sources.empty:
        return sources.copy()
    mask = sources["active"].map(_truthy)
    return sources.loc[mask].copy()


def normalize_fetch_mode(value: Any) -> str:
    """Return a supported fetch mode (default fetch when blank)."""
    text = _text(value) or FETCH_MODE_FETCH
    if text not in ALLOWED_FETCH_MODES:
        raise ReferenceSyncError(
            "INVALID_FETCH_MODE",
            f"Unsupported fetch_mode {text!r}.",
        )
    return text


def normalize_retrieval_strategy(value: Any) -> str:
    """Return a supported retrieval strategy for an official source."""
    text = _text(value)
    if not text:
        raise ReferenceSyncError(
            "MISSING_RETRIEVAL_STRATEGY",
            "Official source is missing retrieval_strategy.",
        )
    if text not in ALLOWED_RETRIEVAL_STRATEGIES:
        raise ReferenceSyncError(
            "INVALID_RETRIEVAL_STRATEGY",
            f"Unsupported retrieval_strategy {text!r}.",
        )
    return text


def fetchable_sources(sources: pd.DataFrame) -> pd.DataFrame:
    """Return active sources that are eligible for network fetch/check."""
    active = active_sources(sources)
    if active.empty:
        return active
    if "fetch_mode" not in active.columns:
        return active.copy()
    modes = active["fetch_mode"].map(normalize_fetch_mode)
    return active.loc[modes == FETCH_MODE_FETCH].copy()


def extract_hostname(url: str) -> str:
    """Return lowercase hostname from a URL."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ReferenceSyncError("INVALID_URL", f"URL has no hostname: {url!r}")
    return host


def assert_url_allowlisted(url: str, allowed_domain: str) -> None:
    """Reject URLs outside the configured official domain."""
    host = extract_hostname(url)
    allowed = _text(allowed_domain).lower().lstrip(".")
    if not allowed:
        raise ReferenceSyncError(
            "MISSING_ALLOWLIST",
            "Official source is missing allowed_domain.",
        )
    if host != allowed and not host.endswith("." + allowed):
        raise ReferenceSyncError(
            "DOMAIN_NOT_ALLOWLISTED",
            f"Domain {host!r} is not allowlisted for official sync "
            f"(allowed: {allowed!r}).",
        )


def normalize_request_url(url: str) -> str:
    """Convert an official IRI/URL into an ASCII-safe URI for urllib.

    Encodes non-ASCII characters in path/query/fragment separately so scheme
    separators and already-valid percent escapes are preserved. Does not alter
    hostname validation semantics; call after allowlist checks.
    """
    text = _text(url)
    if not text:
        return text
    parts = urlsplit(text)
    hostname = parts.hostname
    if hostname:
        try:
            ascii_host = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ReferenceSyncError(
                "INVALID_URL_HOST",
                f"Official URL host cannot be encoded for HTTP: {hostname!r}.",
            ) from exc
        userinfo = ""
        if parts.username is not None:
            password = "" if parts.password is None else f":{parts.password}"
            userinfo = f"{parts.username}{password}@"
        port = f":{parts.port}" if parts.port is not None else ""
        netloc = f"{userinfo}{ascii_host}{port}"
    else:
        netloc = parts.netloc

    # Keep already-encoded % sequences intact; encode only unsafe octets.
    path = quote(parts.path, safe="/%:@-._~!$&'()*+,;=")
    query = quote(parts.query, safe="%&=+!$'()*,;:@/?")
    fragment = quote(parts.fragment, safe="%:@-._~!$&'()*+,;=/?")
    return urlunsplit((parts.scheme, netloc, path, query, fragment))


# Backward-compatible alias for the IRI→URI helper.
iri_to_uri = normalize_request_url


def assert_not_company_upload_as_official(
    *,
    source_kind: str,
    column_names: list[str] | tuple[str, ...] | None = None,
) -> None:
    """Guard: company Excel factor columns never become official registry truth."""
    kind = _text(source_kind).lower()
    if kind in {"company_upload", "user_upload", "intake_upload", "excel_upload"}:
        raise ReferenceSyncError(
            "COMPANY_UPLOAD_NOT_OFFICIAL",
            "Uploaded company spreadsheets cannot update the official "
            "reference registry.",
        )
    if column_names:
        joined = " ".join(str(item) for item in column_names)
        if any(token in joined for token in ("排放係數", "排放量", "CO2e", "計算結果")):
            # Presence in a company file is fine; promoting them is not.
            pass


class _AllowlistRedirectHandler(HTTPRedirectHandler):
    """Follow redirects only while the target remains allowlisted."""

    def __init__(self, allowed_domain: str) -> None:
        super().__init__()
        self.allowed_domain = allowed_domain

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        assert_url_allowlisted(newurl, self.allowed_domain)
        normalized = normalize_request_url(newurl)
        return super().redirect_request(
            req, fp, code, msg, headers, normalized
        )


def normalize_tls_compatibility_mode(value: Any) -> str:
    """Return a supported TLS compatibility mode (default when blank)."""
    text = _text(value) or TLS_MODE_DEFAULT
    if text not in ALLOWED_TLS_COMPATIBILITY_MODES:
        raise ReferenceSyncError(
            "INVALID_TLS_COMPATIBILITY_MODE",
            f"Unsupported tls_compatibility_mode {text!r}.",
        )
    return text


def build_official_ssl_context(
    *,
    tls_compatibility_mode: str = TLS_MODE_DEFAULT,
) -> ssl.SSLContext:
    """Build a verified SSL context for allowlisted official-source fetches.

    Always keeps CA validation and hostname checking enabled. Never uses
    ``verify=False`` or an unverified context.

    ``python313_relaxed_x509_strict`` clears only ``VERIFY_X509_STRICT`` for
    explicitly configured official sources that need Python 3.13 certificate
    chain compatibility. It does not disable certificate verification.
    """
    mode = normalize_tls_compatibility_mode(tls_compatibility_mode)
    context = ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    if mode == TLS_MODE_PYTHON313_RELAXED_X509_STRICT:
        strict_flag = getattr(ssl, "VERIFY_X509_STRICT", None)
        if strict_flag is not None:
            context.verify_flags &= ~strict_flag
    return context


def build_official_https_opener(
    *,
    allowed_domain: str,
    tls_compatibility_mode: str = TLS_MODE_DEFAULT,
) -> Any:
    """Build an opener with verified HTTPS + allowlisted redirects."""
    context = build_official_ssl_context(
        tls_compatibility_mode=tls_compatibility_mode,
    )
    return build_opener(
        HTTPSHandler(context=context),
        _AllowlistRedirectHandler(allowed_domain),
    )


def build_official_request_headers() -> dict[str, str]:
    """Return conservative headers for official-source GET requests.

    Uses a transparent application User-Agent. Does not impersonate a browser,
    and does not add cookies, authentication, or Sec-* client hints.
    """
    return dict(OFFICIAL_REQUEST_HEADERS)


def _http_status_error(status: int, url: str) -> ReferenceSyncError:
    """Map HTTP status codes to structured sync errors."""
    if int(status) == 403:
        return ReferenceSyncError(
            "SOURCE_ACCESS_RESTRICTED",
            (
                f"Official source restricted access (HTTP 403) for {url}. "
                "Transparent application identity was used; no browser "
                "impersonation retry is attempted."
            ),
        )
    return ReferenceSyncError(
        "HTTP_ERROR",
        f"Official source returned HTTP {status} for {url}.",
    )


def fetch_official_artifact(
    url: str,
    *,
    allowed_domain: str,
    tls_compatibility_mode: str = TLS_MODE_DEFAULT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    opener: Any | None = None,
) -> FetchResult:
    """Fetch bytes from an allowlisted official URL with safety bounds.

    TLS failures are not automatically retried with a relaxed context.
    Compatibility mode must be configured explicitly on the source.
    HTTP 403 is reported as SOURCE_ACCESS_RESTRICTED without browser
    impersonation retries.

    Flow: allowlist hostname → normalize Unicode IRI to ASCII URI → HTTPS GET.
    """
    discovered_url = _text(url)
    assert_url_allowlisted(discovered_url, allowed_domain)
    if urlparse(discovered_url).scheme.lower() != "https":
        raise ReferenceSyncError(
            "HTTPS_REQUIRED",
            f"Official sync requires HTTPS URLs; got {discovered_url!r}.",
        )
    request_url = normalize_request_url(discovered_url)
    mode = normalize_tls_compatibility_mode(tls_compatibility_mode)
    request = Request(
        request_url,
        headers=build_official_request_headers(),
        method="GET",
    )
    try:
        if opener is None:
            opener = build_official_https_opener(
                allowed_domain=allowed_domain,
                tls_compatibility_mode=mode,
            )
        with opener.open(request, timeout=timeout_seconds) as response:
            return _read_response(
                response,
                url=request_url,
                discovered_url=discovered_url,
                max_bytes=max_bytes,
                tls_compatibility_mode=mode,
            )
    except ReferenceSyncError:
        raise
    except HTTPError as exc:
        raise _http_status_error(exc.code, request_url) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        message = str(reason)
        code = (
            "NETWORK_TIMEOUT"
            if "timed out" in message.lower()
            else "NETWORK_ERROR"
        )
        # Intentionally no automatic retry with relaxed TLS settings.
        raise ReferenceSyncError(
            code,
            f"Network error fetching {request_url}: {reason}",
        ) from exc


def _read_response(
    response: Any,
    *,
    url: str,
    max_bytes: int,
    tls_compatibility_mode: str = TLS_MODE_DEFAULT,
    discovered_url: str = "",
) -> FetchResult:
    raw_final = _text(getattr(response, "geturl", lambda: url)()) or url
    final_url = normalize_request_url(raw_final)
    status = getattr(response, "status", None)
    if status is None and hasattr(response, "getcode"):
        status = response.getcode()
    if status is not None and int(status) >= 400:
        raise _http_status_error(int(status), final_url)
    headers = getattr(response, "headers", {}) or {}
    media_type = _text(headers.get("Content-Type", "")).split(";")[0]
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = response.read(64 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            raise ReferenceSyncError(
                "RESPONSE_TOO_LARGE",
                f"Official artifact exceeds {max_bytes} byte limit.",
            )
        chunks.append(piece)
    content = b"".join(chunks)
    digest = compute_bytes_sha256(content)
    return FetchResult(
        url=url,
        final_url=final_url,
        content=content,
        media_type=media_type or "application/octet-stream",
        sha256=digest,
        byte_size=len(content),
        tls_verification=TLS_VERIFICATION_VERIFIED,
        tls_compatibility_mode=normalize_tls_compatibility_mode(
            tls_compatibility_mode
        ),
        discovered_url=_text(discovered_url) or url,
    )


def artifact_filename(
    *,
    source_id: str,
    sha256: str,
    expected_file_type: str,
    publication_date: str = "",
) -> str:
    """Deterministic artifact filename (never overwrites differing bytes)."""
    safe_source = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_id).strip("_") or "source"
    pub = re.sub(r"[^0-9A-Za-z_-]+", "", publication_date) or "unknown-pub"
    ext = _text(expected_file_type).lower().lstrip(".") or "bin"
    return f"{safe_source}__{pub}__{sha256[:12]}.{ext}"


def find_snapshot_by_sha(
    snapshots: pd.DataFrame,
    sha256: str,
) -> dict[str, str] | None:
    """Return an existing snapshot row dict when SHA-256 already known."""
    if snapshots.empty:
        return None
    matches = snapshots.loc[snapshots["sha256"] == sha256]
    if matches.empty:
        return None
    return {col: _text(matches.iloc[0][col]) for col in SNAPSHOT_COLUMNS}


def register_snapshot(
    *,
    snapshots_csv: Path,
    artifact_dir: Path,
    source_row: pd.Series | dict[str, Any],
    fetch: FetchResult,
    retrieved_at: str,
    publication_date: str = "",
    status: str = LIFECYCLE_DOWNLOADED,
    notes: str = "",
) -> dict[str, str]:
    """Persist artifact bytes and snapshot metadata; dedupe by SHA-256."""
    snapshots = _read_csv(snapshots_csv, SNAPSHOT_COLUMNS)
    existing = find_snapshot_by_sha(snapshots, fetch.sha256)
    if existing is not None:
        return existing

    source_id = _text(source_row.get("source_id"))
    file_name = artifact_filename(
        source_id=source_id,
        sha256=fetch.sha256,
        expected_file_type=_text(source_row.get("expected_file_type")),
        publication_date=publication_date,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    local_path = artifact_dir / file_name
    if local_path.exists():
        prior = compute_bytes_sha256(local_path.read_bytes())
        if prior != fetch.sha256:
            raise ReferenceSyncError(
                "ARTIFACT_PATH_CONFLICT",
                f"Refusing to overwrite {local_path} with different bytes.",
            )
    else:
        local_path.write_bytes(fetch.content)

    retrieved_url = fetch.final_url
    discovered_url = _text(fetch.discovered_url) or retrieved_url
    retrieved_host = extract_hostname(retrieved_url)
    canonical_url = _text(source_row.get("canonical_url"))
    upstream_canonical_url = _text(
        source_row.get("upstream_canonical_url")
    ) or canonical_url
    upstream_factor_authority = _text(
        source_row.get("upstream_factor_authority")
    )
    provenance_notes = _text(notes)
    if discovered_url != retrieved_url:
        encode_note = (
            "Discovered official URL retained separately from the "
            "percent-encoded transport URI used for HTTPS retrieval."
        )
        if encode_note not in provenance_notes:
            provenance_notes = (
                f"{provenance_notes}; {encode_note}"
                if provenance_notes
                else encode_note
            )
    if retrieved_host == "ghgregistry.moenv.gov.tw" and upstream_canonical_url:
        moenv_note = (
            "Retrieved from operational MOENV GHG Registry source; "
            "upstream MOEA canonical URL retained separately and was not "
            "required for this fetch."
        )
        if moenv_note not in provenance_notes:
            provenance_notes = (
                f"{provenance_notes}; {moenv_note}"
                if provenance_notes
                else moenv_note
            )

    snapshot_id = f"snap_{source_id}_{fetch.sha256[:12]}"
    row = {
        "snapshot_id": snapshot_id,
        "source_id": source_id,
        "authority": _text(source_row.get("authority")),
        "reference_type": _text(source_row.get("reference_type")),
        "canonical_url": canonical_url or upstream_canonical_url,
        "upstream_canonical_url": upstream_canonical_url,
        "upstream_factor_authority": upstream_factor_authority,
        "discovered_url": discovered_url,
        "retrieved_url": retrieved_url,
        "retrieved_host": retrieved_host,
        "retrieved_at": retrieved_at,
        "publication_date": publication_date,
        "file_name": file_name,
        "media_type": fetch.media_type,
        "sha256": fetch.sha256,
        "byte_size": str(fetch.byte_size),
        "parser_version": PARSER_VERSION,
        "local_path": str(local_path),
        "status": status,
        "tls_verification": (
            _text(fetch.tls_verification) or TLS_VERIFICATION_VERIFIED
        ),
        "tls_compatibility_mode": normalize_tls_compatibility_mode(
            fetch.tls_compatibility_mode
        ),
        "notes": provenance_notes,
    }
    snapshots = pd.concat([snapshots, pd.DataFrame([row])], ignore_index=True)
    _write_csv(snapshots_csv, snapshots, SNAPSHOT_COLUMNS)
    return row


def parse_electricity_factor_csv(content: bytes) -> ParseResult:
    """Parse the supported Taiwan electricity-factor CSV fixture format."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return ParseResult(
            parser_type="tw_electricity_factor_csv_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason="CSV has no header row.",
        )
    required = {
        "factor_year",
        "factor_value",
        "numerator_unit",
        "denominator_unit",
        "geography",
    }
    present = {name.strip() for name in reader.fieldnames if name}
    if not required.issubset(present):
        return ParseResult(
            parser_type="tw_electricity_factor_csv_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "CSV headers are not the supported electricity-factor format."
            ),
        )

    records: list[dict[str, Any]] = []
    publication_dates: list[str] = []
    for raw in reader:
        category = _text(raw.get("factor_category") or raw.get("category")) or (
            "unspecified"
        )
        publication_date = _text(raw.get("publication_date"))
        if publication_date:
            publication_dates.append(publication_date)
        records.append(
            {
                "reference_type": "electricity_factor",
                "factor_year": _text(raw.get("factor_year")),
                "factor_value": _text(raw.get("factor_value")),
                "numerator_unit": _text(raw.get("numerator_unit")),
                "denominator_unit": _text(raw.get("denominator_unit")),
                "geography": _text(raw.get("geography")) or "TW",
                "activity_type": "grid_electricity",
                "combustion_context": "not_applicable",
                "gas": _text(raw.get("gas")) or "CO2e",
                "factor_category": category,
                "valid_from": _text(raw.get("valid_from")),
                "valid_to": _text(raw.get("valid_to")),
                "publication_date": publication_date,
                "source_locator": _text(raw.get("source_locator"))
                or f"electricity_factor_year={_text(raw.get('factor_year'))}",
            }
        )

    if not records:
        return ParseResult(
            parser_type="tw_electricity_factor_csv_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason="CSV contained no electricity-factor rows.",
        )

    pub = sorted(set(publication_dates))[0] if publication_dates else ""
    return ParseResult(
        parser_type="tw_electricity_factor_csv_v1",
        status=LIFECYCLE_PARSED,
        records=records,
        publication_date=pub,
        reason="Parsed supported electricity-factor CSV.",
    )


def _roc_year_to_gregorian(roc_year_text: str) -> str:
    """Convert a Republic of China year string to Gregorian year text."""
    try:
        roc_year = int(roc_year_text)
    except ValueError:
        return ""
    if roc_year <= 0:
        return ""
    return str(roc_year + 1911)


def parse_moea_electricity_news_html(content: bytes) -> ParseResult:
    """Extract categorized electricity factors from official MOEA news HTML.

    Values and categories come from the fetched page text. This function does
    not write to the active factor registry.
    """
    text = content.decode("utf-8", errors="replace")
    compact = re.sub(r"\s+", " ", text)
    publication_match = _MOEA_HTML_PUBLICATION_DATE_RE.search(compact)
    publication_date = publication_match.group(1) if publication_match else ""
    roc_match = _MOEA_HTML_ROC_YEAR_RE.search(compact)
    factor_year = (
        _roc_year_to_gregorian(roc_match.group(1)) if roc_match else ""
    )
    valid_from = f"{factor_year}-01-01" if factor_year else ""
    valid_to = f"{factor_year}-12-31" if factor_year else ""

    records: list[dict[str, Any]] = []
    seen_categories: set[str] = set()
    for pattern, category in _ELECTRICITY_HTML_CATEGORY_PATTERNS:
        if category in seen_categories:
            continue
        match = pattern.search(compact)
        if match is None:
            continue
        value = match.group(1)
        seen_categories.add(category)
        records.append(
            {
                "reference_type": "electricity_factor",
                "factor_year": factor_year,
                "factor_value": value,
                "numerator_unit": "kgCO2e",
                "denominator_unit": "kWh",
                "geography": "TW",
                "activity_type": "grid_electricity",
                "combustion_context": "not_applicable",
                "gas": "CO2e",
                "factor_category": category,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "publication_date": publication_date,
                "source_locator": (
                    f"moea_electricity_news;category={category};"
                    f"year={factor_year or 'unknown'}"
                ),
            }
        )

    if len(records) < 2:
        return ParseResult(
            parser_type="tw_moea_electricity_landing_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "MOEA electricity news HTML did not contain enough "
                "categorized factor values for deterministic parsing."
            ),
        )
    return ParseResult(
        parser_type="tw_moea_electricity_landing_v1",
        status=LIFECYCLE_PARSED,
        records=records,
        publication_date=publication_date,
        reason=(
            "Parsed categorized electricity factors from official MOEA "
            "news HTML."
        ),
    )


def _strip_html_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


class _VisibleTextHTMLParser(HTMLParser):
    """Deterministic HTML → visible-text converter (stdlib only)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if lowered in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "td", "th"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if lowered in {"p", "div", "li", "tr", "h1", "h2", "h3", "td", "th"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def _html_to_visible_text(value: str) -> str:
    """Convert HTML to normalized visible text without relying on CSS classes."""
    parser = _VisibleTextHTMLParser()
    try:
        parser.feed(value)
        parser.close()
        text = parser.text()
    except Exception:
        text = _strip_html_tags(value)
    text = html_module.unescape(text)
    text = (
        text.replace("\xa0", " ")
        .replace("\u3000", " ")
        .replace("\u200b", "")
    )
    # Tolerate broken official markup such as "</ div >".
    text = re.sub(r"</\s+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def _normalize_moenv_date_token(year: str, month: str, day: str) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _extract_moenv_announcement_block(raw_html: str) -> str:
    """Return visible text for the single 2026-06-17 electricity announcement."""
    # 1) Live ASP.NET NewsList items (news-list-date / news-list-title).
    for match in _MOENV_LIST_ITEM_RE.finditer(raw_html):
        date_text = _html_to_visible_text(match.group(2))
        date_match = _MOENV_DATE_TOKEN_RE.search(date_text)
        if date_match is None:
            continue
        date_norm = _normalize_moenv_date_token(
            date_match.group(1), date_match.group(2), date_match.group(3)
        )
        item_text = _html_to_visible_text(match.group(0))
        if (
            date_norm == _MOENV_ANNOUNCEMENT_DATE
            and _MOENV_ANNOUNCEMENT_TITLE_TOKEN in item_text
        ):
            return item_text

    # 2) Simplified fixture markup (news-item / news-date / news-title).
    for item in _MOENV_NEWS_ITEM_RE.findall(raw_html):
        date_match = _MOENV_NEWS_DATE_RE.search(item)
        title_match = _MOENV_NEWS_TITLE_RE.search(item)
        if date_match is None or title_match is None:
            continue
        date_text = _normalize_moenv_date_token(
            date_match.group(1), date_match.group(2), date_match.group(3)
        )
        title_text = _html_to_visible_text(title_match.group(1))
        if (
            date_text == _MOENV_ANNOUNCEMENT_DATE
            and _MOENV_ANNOUNCEMENT_TITLE_TOKEN in title_text
        ):
            return _html_to_visible_text(item)

    # 3) CSS-independent fallback on full-page visible text.
    # Require both the announcement date and the stable title phrase, then
    # bound the block to the next news-date token when present.
    visible = _html_to_visible_text(raw_html)
    title_idx = visible.find(_MOENV_ANNOUNCEMENT_TITLE_TOKEN)
    if title_idx < 0:
        return ""
    date_matches = list(_MOENV_DATE_TOKEN_RE.finditer(visible))
    announcement_date = None
    for date_match in date_matches:
        date_norm = _normalize_moenv_date_token(
            date_match.group(1), date_match.group(2), date_match.group(3)
        )
        if date_norm != _MOENV_ANNOUNCEMENT_DATE:
            continue
        # Prefer a date token near the title phrase.
        if abs(date_match.start() - title_idx) <= 400:
            announcement_date = date_match
            break
        if announcement_date is None:
            announcement_date = date_match
    if announcement_date is None:
        return ""
    start = max(0, min(announcement_date.start(), title_idx) - 80)
    end = max(announcement_date.end(), title_idx) + 1800
    for date_match in date_matches:
        if date_match.start() <= max(announcement_date.start(), title_idx):
            continue
        end = min(end, date_match.start())
        break
    block = visible[start:end].strip()
    if _MOENV_ANNOUNCEMENT_TITLE_TOKEN not in block:
        return ""
    return block


def parse_moenv_electricity_news_html(content: bytes) -> ParseResult:
    """Parse MOENV GHG Registry news for the enterprise electricity announcement.

    Locates only the 2026-06-17 announcement by date/title evidence, then
    extracts categorized factors from that bounded block. Does not scrape
    unrelated news entries or invent values.
    """
    raw_html = content.decode("utf-8", errors="replace")
    block = _extract_moenv_announcement_block(raw_html)
    if not block:
        return ParseResult(
            parser_type="tw_moenv_electricity_news_landing_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "Expected MOENV 2026-06-17 electricity-factor announcement "
                "was not found; source format may have changed."
            ),
        )

    compact = re.sub(r"\s+", " ", block)
    roc_match = _MOENV_FACTOR_YEAR_RE.search(compact)
    if roc_match is None:
        roc_match = _MOEA_HTML_ROC_YEAR_RE.search(compact)
    factor_year = (
        _roc_year_to_gregorian(roc_match.group(1)) if roc_match else ""
    )
    # Annual validity follows explicit ROC "114年度" semantics, not publication.
    valid_from = f"{factor_year}-01-01" if factor_year else ""
    valid_to = f"{factor_year}-12-31" if factor_year else ""
    publication_date = _MOENV_ANNOUNCEMENT_DATE
    upstream = (
        "Taiwan Ministry of Economic Affairs / Energy Administration"
    )

    intended_use_by_category = {
        "public_sales_average": "public_electricity_sales_average",
        "industrial_enterprise_inventory": (
            "enterprise GHG inventory / disclosure"
        ),
        "residential": "residential_electricity",
    }
    applicability_by_category = {
        "public_sales_average": (
            "Public electricity-sales average factor. Not interchangeable "
            "with industrial or residential factors."
        ),
        "industrial_enterprise_inventory": (
            "Enterprise inventory / disclosure uses the industrial "
            "electricity factor for applicable business electricity tariff "
            "categories. Do not assume applicability for every grid-"
            "electricity activity without tariff/use context."
        ),
        "residential": (
            "Residential electricity factor. Not interchangeable with "
            "industrial/enterprise-inventory factor."
        ),
    }

    records: list[dict[str, Any]] = []
    seen_categories: set[str] = set()
    for pattern, category in _MOENV_ELECTRICITY_CATEGORY_PATTERNS:
        if category in seen_categories:
            continue
        match = pattern.search(compact)
        if match is None:
            continue
        value = match.group(1)
        seen_categories.add(category)
        records.append(
            {
                "reference_type": REF_TYPE_ELECTRICITY_ENTERPRISE,
                "factor_year": factor_year,
                "factor_value": value,
                "numerator_unit": "kgCO2e",
                "denominator_unit": "kWh",
                "geography": "TW",
                "activity_type": "grid_electricity",
                "combustion_context": "not_applicable",
                "gas": "CO2e",
                "factor_category": category,
                "intended_use": intended_use_by_category.get(category, ""),
                "applicability_notes": applicability_by_category.get(
                    category, ""
                ),
                "upstream_factor_authority": upstream,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "publication_date": publication_date,
                "source_locator": (
                    "moenv_ghg_registry_news;"
                    f"date={publication_date};"
                    f"category={category};"
                    f"year={factor_year or 'unknown'}"
                ),
            }
        )

    required = {
        "public_sales_average",
        "industrial_enterprise_inventory",
        "residential",
    }
    if seen_categories != required:
        missing = sorted(required - seen_categories)
        return ParseResult(
            parser_type="tw_moenv_electricity_news_landing_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "MOENV electricity announcement was found but categorized "
                "factor values could not be extracted deterministically; "
                f"missing categories: {', '.join(missing) or 'ambiguous'}; "
                "source format may have changed."
            ),
        )
    if not factor_year:
        return ParseResult(
            parser_type="tw_moenv_electricity_news_landing_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "MOENV electricity announcement categories were found but "
                "ROC factor year (114年度) could not be determined "
                "deterministically."
            ),
        )
    return ParseResult(
        parser_type="tw_moenv_electricity_news_landing_v1",
        status=LIFECYCLE_PARSED,
        records=records,
        publication_date=publication_date,
        reason=(
            "Parsed categorized enterprise-inventory electricity factors "
            "from the official MOENV 2026-06-17 announcement."
        ),
    )


def parse_fuel_heating_values_csv(content: bytes) -> ParseResult:
    """Parse a supported structured fuel-heating-value CSV."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return ParseResult(
            parser_type="tw_fuel_heating_values_csv_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason="CSV has no header row.",
        )
    required = {"fuel_type", "heating_value", "unit", "factor_year"}
    present = {name.strip() for name in reader.fieldnames if name}
    if not required.issubset(present):
        return ParseResult(
            parser_type="tw_fuel_heating_values_csv_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason="CSV headers are not the supported heating-value format.",
        )

    records: list[dict[str, Any]] = []
    for raw in reader:
        records.append(
            {
                "reference_type": "fuel_heating_values",
                "fuel_type": _text(raw.get("fuel_type")),
                "factor_value": _text(raw.get("heating_value")),
                "numerator_unit": _text(raw.get("unit")),
                "denominator_unit": "",
                "factor_year": _text(raw.get("factor_year")),
                "geography": _text(raw.get("geography")) or "TW",
                "activity_type": _text(raw.get("activity_type")),
                "combustion_context": _text(raw.get("combustion_context")),
                "gas": "",
                "factor_category": _text(raw.get("fuel_type")),
                "valid_from": _text(raw.get("valid_from")),
                "valid_to": _text(raw.get("valid_to")),
                "publication_date": _text(raw.get("publication_date")),
                "source_locator": _text(raw.get("source_locator"))
                or (
                    f"fuel={_text(raw.get('fuel_type'))};"
                    f"year={_text(raw.get('factor_year'))}"
                ),
            }
        )
    if not records:
        return ParseResult(
            parser_type="tw_fuel_heating_values_csv_v1",
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason="CSV contained no heating-value rows.",
        )
    return ParseResult(
        parser_type="tw_fuel_heating_values_csv_v1",
        status=LIFECYCLE_PARSED,
        records=records,
        publication_date="",
        reason="Parsed supported fuel-heating-value CSV.",
    )


def extract_html_hrefs(content: bytes) -> list[str]:
    """Extract raw href values from an HTML document."""
    text = content.decode("utf-8", errors="replace")
    return [match.strip() for match in _HREF_RE.findall(text) if match.strip()]


def resolve_and_filter_allowlisted_urls(
    hrefs: list[str] | tuple[str, ...],
    *,
    landing_url: str,
    allowed_domain: str,
) -> list[str]:
    """Resolve hrefs and keep only allowlisted absolute URLs.

    Non-allowlisted links are ignored (never followed).
    """
    accepted: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        absolute = urljoin(landing_url, href)
        try:
            assert_url_allowlisted(absolute, allowed_domain)
        except ReferenceSyncError:
            continue
        if absolute not in seen:
            seen.add(absolute)
            accepted.append(absolute)
    return accepted


def _extension_rank(url: str, prefer_extensions: tuple[str, ...]) -> int:
    path = urlparse(url).path.lower()
    for index, extension in enumerate(prefer_extensions):
        if path.endswith(extension.lower()):
            return index
    return len(prefer_extensions) + 1


def discover_official_attachments(
    content: bytes,
    *,
    landing_url: str,
    allowed_domain: str,
    parser_type: str,
    prefer_extensions: tuple[str, ...] = (".ods", ".csv", ".xlsx", ".pdf"),
    required_url_keywords: tuple[str, ...] = (),
) -> DiscoveryResult:
    """Discover allowlisted official attachment URLs from a landing page."""
    hrefs = extract_html_hrefs(content)
    allowlisted = resolve_and_filter_allowlisted_urls(
        hrefs,
        landing_url=landing_url,
        allowed_domain=allowed_domain,
    )
    if required_url_keywords:
        lowered = [item.lower() for item in required_url_keywords]
        allowlisted = [
            url
            for url in allowlisted
            if any(token in url.lower() for token in lowered)
        ]
    ranked = sorted(
        allowlisted,
        key=lambda url: (
            _extension_rank(url, prefer_extensions),
            url,
        ),
    )
    if not ranked:
        return DiscoveryResult(
            parser_type=parser_type,
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            landing_url=landing_url,
            reason=(
                "No allowlisted official attachment URL was discovered "
                "on the landing page."
            ),
        )
    chosen = ranked[0]
    path = urlparse(chosen).path.lower()
    extension = ""
    for item in prefer_extensions:
        if path.endswith(item.lower()):
            extension = item.lower()
            break
    return DiscoveryResult(
        parser_type=parser_type,
        status=LIFECYCLE_DISCOVERED,
        landing_url=landing_url,
        artifact_url=chosen,
        preferred_extension=extension,
        candidate_urls=tuple(ranked),
        reason=(
            f"Discovered allowlisted attachment {chosen!r} "
            f"from official landing page."
        ),
    )


def discover_from_landing_parser(
    content: bytes,
    *,
    landing_url: str,
    allowed_domain: str,
    parser_type: str,
) -> DiscoveryResult:
    """Dispatch landing-page discovery for a configured parser_type."""
    parser = _text(parser_type)
    if parser == "tw_moea_electricity_landing_v1":
        return discover_official_attachments(
            content,
            landing_url=landing_url,
            allowed_domain=allowed_domain,
            parser_type=parser,
            prefer_extensions=(".csv", ".ods", ".xlsx", ".pdf"),
        )
    if parser == "tw_moenv_electricity_news_landing_v1":
        # Production enterprise electricity uses retrieval_strategy=parse_landing
        # and does not call this path. Kept for explicit discovery unit tests.
        return discover_official_attachments(
            content,
            landing_url=landing_url,
            allowed_domain=allowed_domain,
            parser_type=parser,
            prefer_extensions=(".csv", ".ods", ".xlsx", ".pdf"),
        )
    if parser == "tw_moenv_file_downloads_landing_v1":
        return discover_official_attachments(
            content,
            landing_url=landing_url,
            allowed_domain=allowed_domain,
            parser_type=parser,
            prefer_extensions=(".ods", ".pdf", ".csv", ".xlsx"),
        )
    if parser == "tw_moenv_news_heating_values_landing_v1":
        # Discover allowlisted attachments from the official registry/news site.
        return discover_official_attachments(
            content,
            landing_url=landing_url,
            allowed_domain=allowed_domain,
            parser_type=parser,
            prefer_extensions=(".csv", ".ods", ".xlsx", ".pdf"),
        )
    return DiscoveryResult(
        parser_type=parser or "unknown",
        status=LIFECYCLE_NEEDS_PARSER_REVIEW,
        landing_url=landing_url,
        reason=f"Unsupported landing discovery parser_type {parser!r}.",
    )


def is_landing_discovery_parser(parser_type: str) -> bool:
    """Return True when the source uses landing-page attachment discovery."""
    return _text(parser_type) in LANDING_DISCOVERY_PARSERS


def artifact_parser_for_discovery(
    *,
    landing_parser_type: str,
    artifact_url: str,
    reference_type: str,
) -> str:
    """Choose a deterministic artifact parser after discovery, if available."""
    path = urlparse(artifact_url).path.lower()
    if landing_parser_type == "tw_moea_electricity_landing_v1" and path.endswith(
        ".csv"
    ):
        return "tw_electricity_factor_csv_v1"
    if (
        landing_parser_type == "tw_moenv_electricity_news_landing_v1"
        and path.endswith(".csv")
    ):
        return "tw_electricity_factor_csv_v1"
    if (
        landing_parser_type == "tw_moenv_news_heating_values_landing_v1"
        and path.endswith(".csv")
    ):
        return "tw_fuel_heating_values_csv_v1"
    if reference_type in ELECTRICITY_CANDIDATE_REF_TYPES and path.endswith(
        ".csv"
    ):
        return "tw_electricity_factor_csv_v1"
    return "needs_parser_review"


def parse_artifact(
    content: bytes,
    *,
    parser_type: str,
    expected_file_type: str = "",
) -> ParseResult:
    """Dispatch to a deterministic parser or return needs_parser_review."""
    parser = _text(parser_type)
    if parser == "tw_electricity_factor_csv_v1":
        return parse_electricity_factor_csv(content)
    if parser == "tw_fuel_heating_values_csv_v1":
        return parse_fuel_heating_values_csv(content)
    if parser == "tw_moenv_electricity_news_landing_v1":
        html_parsed = parse_moenv_electricity_news_html(content)
        if html_parsed.status == LIFECYCLE_PARSED:
            return html_parsed
        return html_parsed
    if parser == "tw_moea_electricity_landing_v1":
        html_parsed = parse_moea_electricity_news_html(content)
        if html_parsed.status == LIFECYCLE_PARSED:
            return html_parsed
        return ParseResult(
            parser_type=parser,
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "MOEA landing HTML did not yield categorized factors; "
                "use attachment discovery when available. "
                f"{html_parsed.reason}"
            ),
        )
    if parser in LANDING_DISCOVERY_PARSERS:
        return ParseResult(
            parser_type=parser,
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "Landing-page HTML was supplied to parse_artifact; "
                "use discover_from_landing_parser then parse the artifact."
            ),
        )
    if parser == "needs_parser_review":
        return ParseResult(
            parser_type=parser,
            status=LIFECYCLE_NEEDS_PARSER_REVIEW,
            reason=(
                "Source is registered for discovery/snapshot/versioning only. "
                f"No deterministic parser is available yet "
                f"(expected_file_type={expected_file_type or 'unknown'})."
            ),
        )
    return ParseResult(
        parser_type=parser or "unknown",
        status=LIFECYCLE_NEEDS_PARSER_REVIEW,
        reason=f"Unsupported parser_type {parser!r}.",
    )


def _candidate_id(snapshot_id: str, record: dict[str, Any]) -> str:
    basis = "|".join(
        [
            snapshot_id,
            _text(record.get("reference_type")),
            _text(record.get("factor_year")),
            _text(record.get("factor_category") or record.get("fuel_type")),
            _text(record.get("geography")),
            _text(record.get("activity_type")),
            _text(record.get("gas")),
            _text(record.get("factor_value")),
            _text(record.get("valid_from")),
            _text(record.get("valid_to")),
        ]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]
    return f"cand_{digest}"


def upsert_candidates_from_parse(
    *,
    candidates_csv: Path,
    snapshot: dict[str, str],
    source_row: pd.Series | dict[str, Any],
    parsed: ParseResult,
) -> list[dict[str, str]]:
    """Create or reuse candidate rows from parser output (inactive by default)."""
    candidates = _read_csv(candidates_csv, CANDIDATE_COLUMNS)
    existing_ids = (
        set(candidates["candidate_id"].tolist())
        if not candidates.empty
        else set()
    )
    created: list[dict[str, str]] = []

    if parsed.status == LIFECYCLE_NEEDS_PARSER_REVIEW:
        review_id = f"cand_review_{snapshot['snapshot_id'][-12:]}"
        if review_id not in existing_ids:
            row = {
                "candidate_id": review_id,
                "snapshot_id": snapshot["snapshot_id"],
                "source_id": _text(source_row.get("source_id")),
                "reference_type": _text(source_row.get("reference_type")),
                "factor_year": "",
                "valid_from": "",
                "valid_to": "",
                "geography": "",
                "activity_type": "",
                "combustion_context": "",
                "gas": "",
                "factor_value": "",
                "numerator_unit": "",
                "denominator_unit": "",
                "factor_category": "",
                "intended_use": "",
                "applicability_notes": "",
                "upstream_factor_authority": _text(
                    source_row.get("upstream_factor_authority")
                )
                or _text(snapshot.get("upstream_factor_authority")),
                "publication_date": _text(snapshot.get("publication_date")),
                "source_locator": snapshot.get("retrieved_url", ""),
                "validation_status": VALIDATION_PENDING,
                "lifecycle_status": LIFECYCLE_NEEDS_PARSER_REVIEW,
                "parser_version": PARSER_VERSION,
                "reason": parsed.reason,
                "notes": (
                    "Snapshot retained; values not guessed "
                    "from unstructured text."
                ),
            }
            candidates = pd.concat([candidates, pd.DataFrame([row])], ignore_index=True)
            created.append(row)
        _write_csv(candidates_csv, candidates, CANDIDATE_COLUMNS)
        return created

    for record in parsed.records:
        cand_id = _candidate_id(snapshot["snapshot_id"], record)
        if cand_id in existing_ids:
            continue
        row = {
            "candidate_id": cand_id,
            "snapshot_id": snapshot["snapshot_id"],
            "source_id": _text(source_row.get("source_id")),
            "reference_type": _text(record.get("reference_type"))
            or _text(source_row.get("reference_type")),
            "factor_year": _text(record.get("factor_year")),
            "valid_from": _text(record.get("valid_from")),
            "valid_to": _text(record.get("valid_to")),
            "geography": _text(record.get("geography")),
            "activity_type": _text(record.get("activity_type")),
            "combustion_context": _text(record.get("combustion_context")),
            "gas": _text(record.get("gas")),
            "factor_value": _text(record.get("factor_value")),
            "numerator_unit": _text(record.get("numerator_unit")),
            "denominator_unit": _text(record.get("denominator_unit")),
            "factor_category": _text(record.get("factor_category")),
            "intended_use": _text(record.get("intended_use")),
            "applicability_notes": _text(record.get("applicability_notes")),
            "upstream_factor_authority": _text(
                record.get("upstream_factor_authority")
            )
            or _text(source_row.get("upstream_factor_authority"))
            or _text(snapshot.get("upstream_factor_authority")),
            "publication_date": _text(record.get("publication_date"))
            or _text(snapshot.get("publication_date")),
            "source_locator": _text(record.get("source_locator")),
            "validation_status": VALIDATION_PENDING,
            "lifecycle_status": LIFECYCLE_CANDIDATE,
            "parser_version": PARSER_VERSION,
            "reason": "Awaiting deterministic validation before activation.",
            "notes": _text(record.get("applicability_notes")),
        }
        candidates = pd.concat([candidates, pd.DataFrame([row])], ignore_index=True)
        existing_ids.add(cand_id)
        created.append(row)

    _write_csv(candidates_csv, candidates, CANDIDATE_COLUMNS)
    return created


def _parse_date(value: str) -> date | None:
    text = _text(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    stamp = pd.Timestamp(parsed)
    return date(int(stamp.year), int(stamp.month), int(stamp.day))


def validate_candidate_row(candidate: dict[str, Any] | pd.Series) -> list[str]:
    """Return validation issue messages; empty list means passed."""
    issues: list[str] = []
    lifecycle = _text(candidate.get("lifecycle_status"))
    if lifecycle == LIFECYCLE_NEEDS_PARSER_REVIEW:
        issues.append("Candidate requires parser review; values were not extracted.")
        return issues

    ref_type = _text(candidate.get("reference_type"))
    value_text = _text(candidate.get("factor_value"))
    try:
        number = float(value_text)
    except ValueError:
        issues.append("factor_value is not numeric")
        number = math.nan
    if not math.isfinite(number) or number <= 0:
        issues.append("factor_value must be a finite number greater than zero")

    if not _text(candidate.get("factor_year")):
        issues.append("factor_year is required")
    if not _text(candidate.get("geography")):
        issues.append("geography is required")
    if not _text(candidate.get("source_locator")):
        issues.append("source_locator is required")
    if not _text(candidate.get("snapshot_id")):
        issues.append("snapshot_id is required")
    if not _text(candidate.get("parser_version")):
        issues.append("parser_version is required")

    if ref_type in ELECTRICITY_CANDIDATE_REF_TYPES:
        if _text(candidate.get("activity_type")) != "grid_electricity":
            issues.append(
                f"{ref_type} activity_type must be grid_electricity"
            )
        if _text(candidate.get("numerator_unit")) not in SUPPORTED_NUMERATOR_UNITS:
            issues.append("unsupported numerator_unit")
        if _text(candidate.get("denominator_unit")) not in SUPPORTED_DENOMINATOR_UNITS:
            issues.append("unsupported denominator_unit")
        category = _text(candidate.get("factor_category")) or "unspecified"
        if category not in SUPPORTED_ELECTRICITY_CATEGORIES:
            issues.append(f"unsupported electricity factor_category {category!r}")
        valid_from = _parse_date(_text(candidate.get("valid_from")))
        valid_to = _parse_date(_text(candidate.get("valid_to")))
        if valid_from is None or valid_to is None:
            issues.append(
                f"{ref_type} requires explicit valid_from and valid_to "
                "(publication_date is not a substitute)"
            )
        elif valid_from > valid_to:
            issues.append("valid_from must be on or before valid_to")
        publication_date = _parse_date(_text(candidate.get("publication_date")))
        if (
            publication_date is not None
            and valid_from is not None
            and publication_date == valid_from
            and _text(candidate.get("notes")).find("publication_as_validity") >= 0
        ):
            issues.append("publication_date must not be used as validity")
        if (
            ref_type == REF_TYPE_ELECTRICITY_ENTERPRISE
            and category in ENTERPRISE_INVENTORY_CATEGORIES
        ):
            intended_use = _text(candidate.get("intended_use"))
            if intended_use not in ENTERPRISE_INVENTORY_INTENDED_USES:
                issues.append(
                    "industrial enterprise-inventory factor requires "
                    "intended_use for enterprise GHG inventory / disclosure"
                )

    if ref_type == "fuel_heating_values":
        if not _text(candidate.get("factor_category")):
            issues.append("fuel_type/factor_category is required")
        if _text(candidate.get("numerator_unit")) not in SUPPORTED_HEATING_UNITS:
            issues.append("unsupported heating-value unit")

    return issues


def validate_candidates(
    candidates_csv: Path,
    *,
    candidate_ids: list[str] | None = None,
) -> pd.DataFrame:
    """Validate pending candidates and update lifecycle/validation fields."""
    candidates = _read_csv(candidates_csv, CANDIDATE_COLUMNS)
    if candidates.empty:
        return candidates
    for index, row in candidates.iterrows():
        if candidate_ids is not None and row["candidate_id"] not in candidate_ids:
            continue
        if _text(row.get("lifecycle_status")) == LIFECYCLE_ACTIVE:
            continue
        issues = validate_candidate_row(row)
        if issues:
            candidates.at[index, "validation_status"] = VALIDATION_FAILED
            if _text(row.get("lifecycle_status")) != LIFECYCLE_NEEDS_PARSER_REVIEW:
                candidates.at[index, "lifecycle_status"] = LIFECYCLE_REJECTED
            candidates.at[index, "reason"] = "; ".join(issues)
        else:
            candidates.at[index, "validation_status"] = VALIDATION_PASSED
            candidates.at[index, "lifecycle_status"] = LIFECYCLE_VALIDATED
            candidates.at[index, "reason"] = (
                "Passed deterministic validation; not active until activation."
            )
    _write_csv(candidates_csv, candidates, CANDIDATE_COLUMNS)
    return candidates


def _active_duplicate_exists(
    emission_factors: pd.DataFrame,
    candidate: dict[str, Any],
) -> bool:
    if emission_factors.empty:
        return False
    category = _text(candidate.get("factor_category")) or "unspecified"
    year = _text(candidate.get("factor_year"))
    mask = (
        (emission_factors["activity_type"] == _text(candidate.get("activity_type")))
        & (emission_factors["geography"] == _text(candidate.get("geography")))
        & (emission_factors["factor_year"] == year)
        & (emission_factors["gas"] == _text(candidate.get("gas")))
        & (emission_factors["numerator_unit"] == _text(candidate.get("numerator_unit")))
        & (
            emission_factors["denominator_unit"]
            == _text(candidate.get("denominator_unit"))
        )
        & (emission_factors["valid_from"] == _text(candidate.get("valid_from")))
        & (emission_factors["valid_to"] == _text(candidate.get("valid_to")))
        & (emission_factors["factor_status"] != "inactive")
    )
    matches = emission_factors.loc[mask]
    if matches.empty:
        return False
    # Categories are not interchangeable: only the same category counts as
    # an equivalent active factor. Legacy 2024 rows without a category suffix
    # still collide within the same year/dates when category is unspecified.
    category_token = f"category={category}"
    id_token = f"ef_tw_grid_electricity_{year}_{category}"
    for _, row in matches.iterrows():
        factor_id = _text(row.get("factor_id"))
        notes = _text(row.get("notes"))
        if category_token in notes or factor_id == id_token or factor_id.startswith(
            f"{id_token}_"
        ):
            return True
        if category in {"unspecified", "utility_average"} and factor_id == (
            f"ef_tw_grid_electricity_{year}"
        ):
            return True
    return False


def format_candidate_activation_summary(
    candidate: dict[str, Any] | pd.Series,
    *,
    snapshot: dict[str, Any] | pd.Series | None = None,
) -> str:
    """Return the human-readable pre-activation review summary."""
    row = {
        key: _text(candidate.get(key))
        for key in (
            "candidate_id",
            "factor_year",
            "factor_category",
            "factor_value",
            "numerator_unit",
            "denominator_unit",
            "intended_use",
            "lifecycle_status",
            "validation_status",
            "upstream_factor_authority",
            "source_id",
        )
    }
    authority = ""
    upstream = row["upstream_factor_authority"]
    if snapshot is not None:
        authority = _text(snapshot.get("authority"))
        upstream = upstream or _text(snapshot.get("upstream_factor_authority"))
    units = ""
    if row["numerator_unit"] and row["denominator_unit"]:
        units = f"{row['numerator_unit']}/{row['denominator_unit']}"
    value_line = row["factor_value"]
    if value_line and units:
        value_line = f"{value_line} {units}"
    lines = [
        "Candidate to activate",
        "",
        f"Candidate ID: {row['candidate_id'] or '(missing)'}",
        "",
        "Year:",
        row["factor_year"] or "(missing)",
        "",
        "Category:",
        row["factor_category"] or "(missing)",
        "",
        "Value:",
        value_line or "(missing)",
        "",
        "Intended use:",
        row["intended_use"] or "(missing)",
        "",
        "Source:",
        authority
        or "Taiwan Ministry of Environment / Climate Change Administration",
        "",
        "Upstream authority:",
        upstream
        or "Taiwan Ministry of Economic Affairs / Energy Administration",
        "",
        "Status:",
        row["lifecycle_status"] or "(missing)",
    ]
    return "\n".join(lines)


def assert_candidate_ready_for_activation(
    candidate: dict[str, Any] | pd.Series,
    *,
    snapshot: dict[str, Any] | pd.Series | None = None,
) -> None:
    """Raise ReferenceSyncError when a candidate is not activation-ready."""
    candidate_id = _text(candidate.get("candidate_id"))
    lifecycle = _text(candidate.get("lifecycle_status"))
    validation = _text(candidate.get("validation_status"))

    if lifecycle == LIFECYCLE_NEEDS_PARSER_REVIEW:
        raise ReferenceSyncError(
            "CANDIDATE_NEEDS_PARSER_REVIEW",
            f"Candidate {candidate_id} needs parser review and cannot activate.",
        )
    if lifecycle in {LIFECYCLE_REJECTED, LIFECYCLE_SUPERSEDED}:
        raise ReferenceSyncError(
            "CANDIDATE_NOT_ACTIVATABLE",
            f"Candidate {candidate_id} has lifecycle_status={lifecycle!r}.",
        )
    if validation != VALIDATION_PASSED:
        raise ReferenceSyncError(
            "CANDIDATE_NOT_VALIDATED",
            f"Candidate {candidate_id} is not validated "
            f"(validation_status={validation!r}).",
        )
    if lifecycle != LIFECYCLE_VALIDATED:
        if lifecycle == LIFECYCLE_ACTIVE:
            raise ReferenceSyncError(
                "CANDIDATE_ALREADY_ACTIVE",
                f"Candidate {candidate_id} is already active.",
            )
        raise ReferenceSyncError(
            "CANDIDATE_NOT_VALIDATED",
            f"Candidate {candidate_id} lifecycle_status must be "
            f"{LIFECYCLE_VALIDATED!r} (found {lifecycle!r}).",
        )
    if not _text(candidate.get("factor_value")):
        raise ReferenceSyncError(
            "CANDIDATE_MISSING_VALUE",
            f"Candidate {candidate_id} is missing factor_value.",
        )
    if not _text(candidate.get("factor_year")):
        raise ReferenceSyncError(
            "CANDIDATE_MISSING_YEAR",
            f"Candidate {candidate_id} is missing factor_year.",
        )
    ref_type = _text(candidate.get("reference_type"))
    if ref_type == "fuel_heating_values":
        if not _text(candidate.get("numerator_unit")):
            raise ReferenceSyncError(
                "CANDIDATE_MISSING_UNITS",
                f"Candidate {candidate_id} is missing heating-value unit.",
            )
    elif not _text(candidate.get("numerator_unit")) or not _text(
        candidate.get("denominator_unit")
    ):
        raise ReferenceSyncError(
            "CANDIDATE_MISSING_UNITS",
            f"Candidate {candidate_id} is missing numerator/denominator units.",
        )
    if not _text(candidate.get("snapshot_id")):
        raise ReferenceSyncError(
            "SNAPSHOT_MISSING",
            f"Candidate {candidate_id} is missing snapshot_id.",
        )
    if snapshot is None:
        raise ReferenceSyncError(
            "SNAPSHOT_MISSING",
            f"Snapshot for candidate {candidate_id} is missing.",
        )
    if not _text(snapshot.get("sha256")):
        raise ReferenceSyncError(
            "SNAPSHOT_INCOMPLETE",
            f"Snapshot {candidate.get('snapshot_id')!r} is missing sha256.",
        )
    if not (
        _text(snapshot.get("retrieved_url"))
        or _text(candidate.get("source_locator"))
    ):
        raise ReferenceSyncError(
            "PROVENANCE_INCOMPLETE",
            f"Candidate {candidate_id} lacks retrieved_url / source_locator.",
        )
    if not (
        _text(candidate.get("upstream_factor_authority"))
        or _text(snapshot.get("upstream_factor_authority"))
        or _text(snapshot.get("authority"))
    ):
        raise ReferenceSyncError(
            "PROVENANCE_INCOMPLETE",
            f"Candidate {candidate_id} lacks source/upstream authority.",
        )
    valid_from = _parse_date(_text(candidate.get("valid_from")))
    valid_to = _parse_date(_text(candidate.get("valid_to")))
    if valid_from is None or valid_to is None:
        raise ReferenceSyncError(
            "CANDIDATE_MISSING_VALIDITY",
            f"Candidate {candidate_id} requires valid_from and valid_to.",
        )
    if valid_from > valid_to:
        raise ReferenceSyncError(
            "CANDIDATE_INVALID_VALIDITY",
            f"Candidate {candidate_id} has valid_from after valid_to.",
        )


def activate_candidate(
    *,
    candidate_id: str,
    candidates_csv: Path,
    snapshots_csv: Path,
    activations_csv: Path,
    emission_factors_csv: Path,
    fuel_heating_values_csv: Path,
    activated_at: str | pd.Timestamp | datetime,
    activated_by: str = "reference_sync",
) -> dict[str, str]:
    """Activate one validated candidate into the local versioned registry.

    Never deletes historical rows. Never activates from publication date alone.
    ``activated_at`` must be provided explicitly. Activates exactly one
    ``candidate_id`` — never all validated candidates.
    """
    if _blank(activated_at):
        raise ReferenceSyncError(
            "ACTIVATION_TIME_REQUIRED",
            "activated_at must be provided explicitly for reproducibility.",
        )
    activated_stamp = pd.Timestamp(activated_at)
    if pd.isna(activated_stamp):
        raise ReferenceSyncError(
            "INVALID_ACTIVATION_TIME",
            f"Invalid activated_at value: {activated_at!r}",
        )
    activated_text = activated_stamp.isoformat()

    candidates = _read_csv(candidates_csv, CANDIDATE_COLUMNS)
    match = candidates.loc[candidates["candidate_id"] == candidate_id]
    if match.empty:
        raise ReferenceSyncError(
            "CANDIDATE_NOT_FOUND",
            f"Unknown candidate_id {candidate_id!r}.",
        )
    candidate = match.iloc[0].to_dict()

    snapshots = _read_csv(snapshots_csv, SNAPSHOT_COLUMNS)
    snap = snapshots.loc[snapshots["snapshot_id"] == candidate["snapshot_id"]]
    snapshot_row = snap.iloc[0].to_dict() if not snap.empty else None
    assert_candidate_ready_for_activation(candidate, snapshot=snapshot_row)
    assert snapshot_row is not None
    sha256 = _text(snapshot_row["sha256"])
    ref_type = _text(candidate.get("reference_type"))

    if ref_type in ELECTRICITY_CANDIDATE_REF_TYPES:
        factors = _read_csv(
            emission_factors_csv,
            [
                "factor_id",
                "activity_type",
                "combustion_context",
                "gas",
                "factor_value",
                "numerator_unit",
                "denominator_unit",
                "geography",
                "factor_year",
                "valid_from",
                "valid_to",
                "source_reference_id",
                "source_locator",
                "factor_status",
                "required_conversion",
                "notes",
            ],
        )
        if _active_duplicate_exists(factors, candidate):
            raise ReferenceSyncError(
                "DUPLICATE_ACTIVE_FACTOR",
                "An active factor with identical applicability dimensions "
                "already exists.",
            )
        year = _text(candidate.get("factor_year"))
        category = _text(candidate.get("factor_category")) or "unspecified"
        factor_id = f"ef_tw_grid_electricity_{year}_{category}"
        if factor_id in set(factors["factor_id"].tolist()):
            factor_id = f"{factor_id}_{sha256[:8]}"
        source_reference_id = (
            f"ref_sync_{_text(candidate.get('source_id'))}_{year}"
        )
        intended_use = _text(candidate.get("intended_use"))
        applicability = _text(candidate.get("applicability_notes"))
        upstream = _text(candidate.get("upstream_factor_authority")) or _text(
            snapshot_row.get("upstream_factor_authority")
        )
        factor_row = {
            "factor_id": factor_id,
            "activity_type": "grid_electricity",
            "combustion_context": "not_applicable",
            "gas": _text(candidate.get("gas")) or "CO2e",
            "factor_value": _text(candidate.get("factor_value")),
            "numerator_unit": _text(candidate.get("numerator_unit")),
            "denominator_unit": _text(candidate.get("denominator_unit")),
            "geography": _text(candidate.get("geography")) or "TW",
            "factor_year": year,
            "valid_from": _text(candidate.get("valid_from")),
            "valid_to": _text(candidate.get("valid_to")),
            "source_reference_id": source_reference_id,
            "source_locator": (
                f"{_text(candidate.get('source_locator'))}; "
                f"snapshot={candidate['snapshot_id']}; sha256={sha256}"
            ),
            "factor_status": "ready",
            "required_conversion": "not_required",
            "notes": (
                f"Activated from official sync candidate {candidate_id}. "
                f"category={category}. intended_use={intended_use or 'n/a'}. "
                f"upstream_factor_authority={upstream or 'n/a'}. "
                f"applicability={applicability or 'n/a'}. "
                f"publication_date="
                f"{_text(candidate.get('publication_date')) or 'unknown'} "
                "(publication_date is not validity)."
            ),
        }
        factors = pd.concat([factors, pd.DataFrame([factor_row])], ignore_index=True)
        _write_csv(
            emission_factors_csv,
            factors,
            list(factor_row.keys()),
        )
        references_csv = emission_factors_csv.parent / "regulatory_references.csv"
        references = _read_csv(
            references_csv,
            [
                "reference_id",
                "framework",
                "title",
                "publisher",
                "identifier",
                "publication_date",
                "effective_from",
                "authority_level",
                "binding_status",
                "source_location",
                "notes",
            ],
        )
        if source_reference_id not in set(references["reference_id"].tolist()):
            ref_row = {
                "reference_id": source_reference_id,
                "framework": "corporate_ghg",
                "title": (
                    f"Official sync electricity factor {year} "
                    f"({category})"
                ),
                "publisher": _text(snapshot_row.get("authority")),
                "identifier": "",
                "publication_date": _text(candidate.get("publication_date")),
                "effective_from": _text(candidate.get("valid_from")),
                "authority_level": "official_government_publication",
                "binding_status": "official",
                "source_location": _text(snapshot_row.get("retrieved_url")),
                "notes": (
                    f"Created by reference sync activation. "
                    f"snapshot={candidate['snapshot_id']}; sha256={sha256}"
                ),
            }
            references = pd.concat(
                [references, pd.DataFrame([ref_row])],
                ignore_index=True,
            )
            _write_csv(references_csv, references, list(ref_row.keys()))
        registry_table = "emission_factors"
        registry_id = factor_id
    elif ref_type == "fuel_heating_values":
        heating = _read_csv(fuel_heating_values_csv, HEATING_VALUE_COLUMNS)
        fuel = _text(candidate.get("factor_category"))
        year = _text(candidate.get("factor_year"))
        heating_id = f"hv_{fuel}_{year}_{sha256[:8]}"
        heating_row = {
            "heating_value_id": heating_id,
            "fuel_type": fuel,
            "fuel_subtype": "",
            "heating_value": _text(candidate.get("factor_value")),
            "unit": _text(candidate.get("numerator_unit")),
            "high_heating_value": "",
            "high_heating_value_unit": "",
            "factor_year": year,
            "geography": _text(candidate.get("geography")) or "TW",
            "authority": _text(snapshot_row.get("authority")),
            "valid_from": _text(candidate.get("valid_from")),
            "valid_to": _text(candidate.get("valid_to")),
            "source_reference_id": f"ref_sync_{_text(candidate.get('source_id'))}",
            "source_locator": _text(candidate.get("source_locator")),
            "snapshot_id": _text(candidate.get("snapshot_id")),
            "snapshot_sha256": sha256,
            "snapshot_local_path": _text(snapshot_row.get("local_path")),
            "status": "registered",
            "notes": (
                "Versioned heating-value reference. Does not automatically "
                "clear calculation_dependencies or invent conversions."
            ),
        }
        heating = pd.concat([heating, pd.DataFrame([heating_row])], ignore_index=True)
        _write_csv(fuel_heating_values_csv, heating, HEATING_VALUE_COLUMNS)
        registry_table = "fuel_heating_values"
        registry_id = heating_id
    else:
        raise ReferenceSyncError(
            "UNSUPPORTED_ACTIVATION_TYPE",
            f"Cannot activate reference_type {ref_type!r} in Phase 10A.",
        )

    activations = _read_csv(activations_csv, ACTIVATION_COLUMNS)
    # Reject duplicate activation of the same candidate (audit + lifecycle).
    prior = activations.loc[activations["candidate_id"] == candidate_id]
    if not prior.empty:
        raise ReferenceSyncError(
            "CANDIDATE_ALREADY_ACTIVE",
            f"Candidate {candidate_id} already has an activation audit row.",
        )
    activation_id = f"act_{candidate_id[-12:]}_{sha256[:8]}"
    activation_row = {
        "activation_id": activation_id,
        "candidate_id": candidate_id,
        "snapshot_id": _text(candidate.get("snapshot_id")),
        "factor_id": registry_id,
        "factor_year": _text(candidate.get("factor_year")),
        "factor_category": _text(candidate.get("factor_category")),
        "factor_value": _text(candidate.get("factor_value")),
        "numerator_unit": _text(candidate.get("numerator_unit")),
        "denominator_unit": _text(candidate.get("denominator_unit")),
        "activated_at": activated_text,
        "activated_by": activated_by,
        "registry_table": registry_table,
        "sha256": sha256,
        "source_id": _text(candidate.get("source_id")),
        "upstream_factor_authority": _text(
            candidate.get("upstream_factor_authority")
        )
        or _text(snapshot_row.get("upstream_factor_authority")),
        "retrieved_url": _text(snapshot_row.get("retrieved_url")),
        "notes": (
            "Historical rows preserved; prior years not overwritten. "
            "Activated exactly one selected candidate_id."
        ),
    }
    activations = pd.concat(
        [activations, pd.DataFrame([activation_row])],
        ignore_index=True,
    )
    _write_csv(activations_csv, activations, ACTIVATION_COLUMNS)

    idx = candidates.index[candidates["candidate_id"] == candidate_id][0]
    candidates.at[idx, "lifecycle_status"] = LIFECYCLE_ACTIVE
    candidates.at[idx, "reason"] = (
        f"Activated into {registry_table} as {registry_id}."
    )
    _write_csv(candidates_csv, candidates, CANDIDATE_COLUMNS)
    return {key: _text(value) for key, value in activation_row.items()}


def build_change_report(
    *,
    source_id: str,
    reference_type: str,
    previous_snapshot: dict[str, str] | None,
    new_snapshot: dict[str, str],
    previous_candidates: pd.DataFrame,
    new_candidates: list[dict[str, str]],
) -> ChangeReport:
    """Compare previous known years/values with newly created candidates."""
    previous_year_series = previous_candidates.get(
        "factor_year",
        pd.Series(dtype=str),
    )
    prev_years = tuple(
        sorted(
            {
                _text(value)
                for value in previous_year_series.tolist()
                if _text(value)
            }
        )
    )
    new_years = tuple(
        sorted(
            {
                _text(item.get("factor_year"))
                for item in new_candidates
                if _text(item.get("factor_year"))
            }
        )
    )
    changes: list[str] = []
    if previous_snapshot is None:
        changes.append("first snapshot for this source")
    elif previous_snapshot.get("sha256") != new_snapshot.get("sha256"):
        changes.append("artifact bytes changed")
    if prev_years != new_years:
        changes.append("factor year changed")
    if new_candidates:
        changes.append("new candidate row(s) created")
        if any(_text(item.get("valid_from")) for item in new_candidates):
            changes.append("applicability dates present on candidates")
        if any(_text(item.get("factor_value")) for item in new_candidates):
            changes.append("factor value changed or newly observed")
    return ChangeReport(
        source_id=source_id,
        reference_type=reference_type,
        previous_snapshot_id=_text((previous_snapshot or {}).get("snapshot_id")),
        new_snapshot_id=new_snapshot["snapshot_id"],
        previous_years=prev_years,
        new_years=new_years,
        changes=tuple(changes),
        activated=False,
    )


def check_official_sources(
    repo_root: Path,
    *,
    retrieved_at: str,
    fetch: FetchCallable | None = None,
) -> list[dict[str, Any]]:
    """Inspect allowlisted sources and report availability without activating."""
    paths = default_paths(repo_root)
    sources = active_sources(load_official_sources(paths["sources"]))
    results: list[dict[str, Any]] = []
    fetch_fn = fetch or (
        lambda url, allowed_domain, **kwargs: fetch_official_artifact(
            url,
            allowed_domain=allowed_domain,
            **kwargs,
        )
    )
    for _, source in sources.iterrows():
        tls_mode = normalize_tls_compatibility_mode(
            source.get("tls_compatibility_mode")
        )
        fetch_mode = normalize_fetch_mode(source.get("fetch_mode"))
        item: dict[str, Any] = {
            "source_id": _text(source["source_id"]),
            "reference_type": _text(source["reference_type"]),
            "status": "unchecked",
            "message": "",
            "sha256": "",
            "tls_verification": TLS_VERIFICATION_VERIFIED,
            "tls_compatibility_mode": tls_mode,
            "fetch_mode": fetch_mode,
            "upstream_canonical_url": _text(
                source.get("upstream_canonical_url")
            )
            or _text(source.get("canonical_url")),
            "upstream_factor_authority": _text(
                source.get("upstream_factor_authority")
            ),
        }
        if fetch_mode == FETCH_MODE_PROVENANCE_ONLY:
            item["status"] = "recorded_access_restricted"
            item["message"] = (
                "Upstream/canonical source recorded for provenance; "
                "runtime machine-fetch is disabled because official host "
                "access is restricted (HTTP 403). Normal sync uses the "
                "MOENV operational source instead."
            )
            results.append(item)
            continue
        try:
            fetched = fetch_fn(
                _text(source["landing_url"]),
                allowed_domain=_text(source["allowed_domain"]),
                tls_compatibility_mode=tls_mode,
            )
            item["status"] = "available"
            item["sha256"] = fetched.sha256
            item["tls_compatibility_mode"] = fetched.tls_compatibility_mode
            item["tls_verification"] = fetched.tls_verification
            item["message"] = (
                f"Reachable at check time {retrieved_at}; "
                f"{fetched.byte_size} bytes."
            )
        except ReferenceSyncError as exc:
            item["status"] = "unavailable"
            item["message"] = f"{exc.code}: {exc.message}"
        results.append(item)
    return results


def fetch_and_stage_sources(
    repo_root: Path,
    *,
    retrieved_at: str,
    source_ids: list[str] | None = None,
    fetch: FetchCallable | None = None,
) -> list[dict[str, Any]]:
    """Download allowlisted artifacts, register snapshots, and stage candidates.

    Retrieval behavior is controlled by each source's explicit
    ``retrieval_strategy``:

    - ``parse_landing`` — fetch and parse the landing HTML itself; never
      auto-discover or substitute an attachment (e.g. PDF).
    - ``discover_attachment`` — fetch landing HTML, discover an allowlisted
      attachment, then download/parse that artifact.
    - ``provenance_only`` — no network fetch (aligned with fetch_mode).

    Direct invented CSV endpoints are not assumed.
    """
    paths = default_paths(repo_root)
    all_active = active_sources(load_official_sources(paths["sources"]))
    if source_ids is not None:
        sources = all_active.loc[all_active["source_id"].isin(source_ids)].copy()
    else:
        sources = fetchable_sources(all_active)
    snapshots = _read_csv(paths["snapshots_csv"], SNAPSHOT_COLUMNS)
    candidates = _read_csv(paths["candidates_csv"], CANDIDATE_COLUMNS)
    fetch_fn = fetch or (
        lambda url, allowed_domain, **kwargs: fetch_official_artifact(
            url,
            allowed_domain=allowed_domain,
            **kwargs,
        )
    )
    reports: list[dict[str, Any]] = []

    for _, source in sources.iterrows():
        source_id = _text(source["source_id"])
        allowed_domain = _text(source["allowed_domain"])
        landing_url = _text(source["landing_url"])
        parser_type = _text(source["parser_type"])
        tls_mode = normalize_tls_compatibility_mode(
            source.get("tls_compatibility_mode")
        )
        fetch_mode = normalize_fetch_mode(source.get("fetch_mode"))
        retrieval_strategy = normalize_retrieval_strategy(
            source.get("retrieval_strategy")
        )
        if (
            fetch_mode == FETCH_MODE_PROVENANCE_ONLY
            or retrieval_strategy == RETRIEVAL_PROVENANCE_ONLY
        ):
            reports.append(
                {
                    "source_id": source_id,
                    "status": "skipped_provenance_only",
                    "message": (
                        "Upstream/canonical source is provenance-only; "
                        "no network fetch attempted."
                    ),
                    "upstream_canonical_url": _text(
                        source.get("upstream_canonical_url")
                    )
                    or _text(source.get("canonical_url")),
                    "candidates_created": 0,
                }
            )
            continue
        try:
            landing_fetch = fetch_fn(
                landing_url,
                allowed_domain=allowed_domain,
                tls_compatibility_mode=tls_mode,
            )
        except ReferenceSyncError as exc:
            reports.append(
                {
                    "source_id": source_id,
                    "status": "unavailable",
                    "message": f"{exc.code}: {exc.message}",
                }
            )
            continue

        artifact_parser = parser_type
        fetched = landing_fetch
        discovery_message = ""
        used_attachment_discovery = False

        if retrieval_strategy == RETRIEVAL_PARSE_LANDING:
            previous = None
            prior_rows = snapshots.loc[snapshots["source_id"] == source_id]
            if not prior_rows.empty:
                previous = {
                    col: _text(prior_rows.iloc[-1][col])
                    for col in SNAPSHOT_COLUMNS
                }
            existing = find_snapshot_by_sha(snapshots, landing_fetch.sha256)
            already_known = existing is not None
            source_for_snapshot = {
                column: _text(source.get(column)) for column in SOURCE_COLUMNS
            }
            parsed = parse_artifact(
                landing_fetch.content,
                parser_type=parser_type,
                expected_file_type=_text(source["expected_file_type"]),
            )
            snapshot = register_snapshot(
                snapshots_csv=paths["snapshots_csv"],
                artifact_dir=paths["artifact_dir"],
                source_row=source_for_snapshot,
                fetch=landing_fetch,
                retrieved_at=retrieved_at,
                publication_date=parsed.publication_date,
                status=LIFECYCLE_DOWNLOADED,
                notes=(
                    "Downloaded official landing HTML for parse_landing "
                    "retrieval; attachment discovery was not used."
                ),
            )
            snapshots = _read_csv(paths["snapshots_csv"], SNAPSHOT_COLUMNS)
            created = []
            if not already_known:
                created = upsert_candidates_from_parse(
                    candidates_csv=paths["candidates_csv"],
                    snapshot=snapshot,
                    source_row=source,
                    parsed=parsed,
                )
            prev_candidates = candidates.loc[
                candidates["source_id"] == source_id
            ]
            report = build_change_report(
                source_id=source_id,
                reference_type=_text(source["reference_type"]),
                previous_snapshot=previous,
                new_snapshot=snapshot,
                previous_candidates=prev_candidates,
                new_candidates=created,
            )
            reports.append(
                {
                    "source_id": source_id,
                    "status": (
                        "already_known" if already_known else "staged"
                    ),
                    "snapshot_id": snapshot["snapshot_id"],
                    "sha256": snapshot["sha256"],
                    "candidates_created": len(created),
                    "parser_status": parsed.status,
                    "discovered_artifact_url": "",
                    "canonical_url": snapshot.get("canonical_url", ""),
                    "upstream_canonical_url": snapshot.get(
                        "upstream_canonical_url", ""
                    ),
                    "upstream_factor_authority": snapshot.get(
                        "upstream_factor_authority", ""
                    ),
                    "retrieved_url": snapshot["retrieved_url"],
                    "retrieved_host": snapshot["retrieved_host"],
                    "retrieval_strategy": retrieval_strategy,
                    "change_report": report.to_text(),
                    "message": parsed.reason,
                }
            )
            candidates = _read_csv(paths["candidates_csv"], CANDIDATE_COLUMNS)
            continue

        if retrieval_strategy == RETRIEVAL_DISCOVER_ATTACHMENT:
            discovery = discover_from_landing_parser(
                landing_fetch.content,
                landing_url=landing_url,
                allowed_domain=allowed_domain,
                parser_type=parser_type,
            )
            discovery_message = discovery.reason
            if discovery.status != LIFECYCLE_DISCOVERED or not discovery.artifact_url:
                snapshot = register_snapshot(
                    snapshots_csv=paths["snapshots_csv"],
                    artifact_dir=paths["artifact_dir"],
                    source_row=source,
                    fetch=landing_fetch,
                    retrieved_at=retrieved_at,
                    publication_date="",
                    status=LIFECYCLE_DOWNLOADED,
                    notes=(
                        "Landing page snapshot retained; no allowlisted "
                        "attachment discovered yet."
                    ),
                )
                parsed = ParseResult(
                    parser_type=parser_type,
                    status=LIFECYCLE_NEEDS_PARSER_REVIEW,
                    reason=discovery.reason,
                )
                created = upsert_candidates_from_parse(
                    candidates_csv=paths["candidates_csv"],
                    snapshot=snapshot,
                    source_row=source,
                    parsed=parsed,
                )
                reports.append(
                    {
                        "source_id": source_id,
                        "status": "staged",
                        "snapshot_id": snapshot["snapshot_id"],
                        "sha256": snapshot["sha256"],
                        "candidates_created": len(created),
                        "parser_status": parsed.status,
                        "discovered_artifact_url": "",
                        "retrieval_strategy": retrieval_strategy,
                        "change_report": "",
                        "message": discovery.reason,
                    }
                )
                snapshots = _read_csv(paths["snapshots_csv"], SNAPSHOT_COLUMNS)
                candidates = _read_csv(paths["candidates_csv"], CANDIDATE_COLUMNS)
                continue

            # Separately validate the discovered attachment before download.
            assert_url_allowlisted(discovery.artifact_url, allowed_domain)
            try:
                fetched = fetch_fn(
                    discovery.artifact_url,
                    allowed_domain=allowed_domain,
                    tls_compatibility_mode=tls_mode,
                )
            except ReferenceSyncError as exc:
                reports.append(
                    {
                        "source_id": source_id,
                        "status": "unavailable",
                        "message": (
                            "Landing page reachable but artifact fetch failed: "
                            f"{exc.code}: {exc.message}"
                        ),
                        "discovered_artifact_url": discovery.artifact_url,
                        "retrieval_strategy": retrieval_strategy,
                    }
                )
                continue
            artifact_parser = artifact_parser_for_discovery(
                landing_parser_type=parser_type,
                artifact_url=discovery.artifact_url,
                reference_type=_text(source["reference_type"]),
            )
            used_attachment_discovery = True

        previous = None
        prior_rows = snapshots.loc[snapshots["source_id"] == source_id]
        if not prior_rows.empty:
            previous = {
                col: _text(prior_rows.iloc[-1][col]) for col in SNAPSHOT_COLUMNS
            }

        existing = find_snapshot_by_sha(snapshots, fetched.sha256)
        already_known = existing is not None
        expected_type = _text(source["expected_file_type"])
        if used_attachment_discovery:
            path = urlparse(fetched.final_url).path.lower()
            if path.endswith(".ods"):
                expected_type = "ods"
            elif path.endswith(".csv"):
                expected_type = "csv"
            elif path.endswith(".pdf"):
                expected_type = "pdf"
            elif path.endswith(".xlsx"):
                expected_type = "xlsx"
        source_for_snapshot = {
            column: _text(source.get(column)) for column in SOURCE_COLUMNS
        }
        source_for_snapshot["expected_file_type"] = expected_type
        snapshot = register_snapshot(
            snapshots_csv=paths["snapshots_csv"],
            artifact_dir=paths["artifact_dir"],
            source_row=source_for_snapshot,
            fetch=fetched,
            retrieved_at=retrieved_at,
            publication_date="",
            status=LIFECYCLE_DOWNLOADED,
            notes=(
                "Downloaded by official reference sync from allowlisted "
                "landing-page discovery."
                if used_attachment_discovery
                else "Downloaded by official reference sync."
            ),
        )
        snapshots = _read_csv(paths["snapshots_csv"], SNAPSHOT_COLUMNS)

        parsed = parse_artifact(
            fetched.content,
            parser_type=artifact_parser,
            expected_file_type=expected_type,
        )
        if parsed.publication_date and not snapshot.get("publication_date"):
            snap_frame = snapshots
            idx = snap_frame.index[
                snap_frame["snapshot_id"] == snapshot["snapshot_id"]
            ][0]
            snap_frame.at[idx, "publication_date"] = parsed.publication_date
            _write_csv(paths["snapshots_csv"], snap_frame, SNAPSHOT_COLUMNS)
            snapshot["publication_date"] = parsed.publication_date

        created = []
        if not already_known:
            created = upsert_candidates_from_parse(
                candidates_csv=paths["candidates_csv"],
                snapshot=snapshot,
                source_row=source,
                parsed=parsed,
            )
        else:
            created = []

        prev_candidates = candidates.loc[candidates["source_id"] == source_id]
        report = build_change_report(
            source_id=source_id,
            reference_type=_text(source["reference_type"]),
            previous_snapshot=previous,
            new_snapshot=snapshot,
            previous_candidates=prev_candidates,
            new_candidates=created,
        )
        reports.append(
            {
                "source_id": source_id,
                "status": "already_known" if already_known else "staged",
                "snapshot_id": snapshot["snapshot_id"],
                "sha256": snapshot["sha256"],
                "candidates_created": len(created),
                "parser_status": parsed.status,
                "discovered_artifact_url": (
                    fetched.final_url if used_attachment_discovery else ""
                ),
                "retrieval_strategy": retrieval_strategy,
                "change_report": report.to_text(),
                "message": discovery_message or parsed.reason,
            }
        )
        candidates = _read_csv(paths["candidates_csv"], CANDIDATE_COLUMNS)
    return reports


def reference_sync_status(repo_root: Path) -> SyncStatus:
    """Summarize local official-reference maintenance state."""
    paths = default_paths(repo_root)
    sources = load_official_sources(paths["sources"])
    snapshots = _read_csv(paths["snapshots_csv"], SNAPSHOT_COLUMNS)
    candidates = _read_csv(paths["candidates_csv"], CANDIDATE_COLUMNS)
    factors = _read_csv(
        paths["emission_factors"],
        [
            "factor_id",
            "activity_type",
            "factor_year",
            "factor_status",
            "valid_from",
            "valid_to",
        ],
    )
    heating = _read_csv(paths["fuel_heating_values"], HEATING_VALUE_COLUMNS)

    electricity_years: dict[str, str] = {}
    elec = factors.loc[
        (factors.get("activity_type", pd.Series(dtype=str)) == "grid_electricity")
        & (factors.get("factor_status", pd.Series(dtype=str)) != "inactive")
    ]
    for _, row in elec.iterrows():
        year = _text(row.get("factor_year"))
        if year:
            electricity_years[year] = "available"

    for _, row in candidates.iterrows():
        if _text(row.get("reference_type")) not in ELECTRICITY_CANDIDATE_REF_TYPES:
            continue
        year = _text(row.get("factor_year"))
        if not year:
            continue
        lifecycle = _text(row.get("lifecycle_status"))
        if year in electricity_years and electricity_years[year] == "available":
            continue
        if lifecycle == LIFECYCLE_ACTIVE:
            electricity_years[year] = "available"
        elif lifecycle in {LIFECYCLE_CANDIDATE, LIFECYCLE_VALIDATED}:
            electricity_years[year] = "candidate"
        elif lifecycle == LIFECYCLE_NEEDS_PARSER_REVIEW:
            electricity_years[year] = "needs_parser_review"
        else:
            electricity_years.setdefault(year, "unavailable")

    if "2024" not in electricity_years and not elec.empty:
        electricity_years["2024"] = "available"
    if "2025" not in electricity_years:
        electricity_years["2025"] = "unavailable"

    heating_latest: dict[str, str] = {}
    for _, row in heating.iterrows():
        fuel = _text(row.get("fuel_type"))
        year = _text(row.get("factor_year"))
        if fuel and year:
            prior = heating_latest.get(fuel, "")
            if not prior or year > prior:
                heating_latest[fuel] = year
    for fuel in ("natural_gas", "diesel", "gasoline", "lpg"):
        heating_latest.setdefault(fuel, "unregistered")

    last_checked = ""
    if not snapshots.empty and "retrieved_at" in snapshots.columns:
        values = [
            _text(value)
            for value in snapshots["retrieved_at"].tolist()
            if _text(value)
        ]
        last_checked = max(values) if values else ""

    active_candidates = 0
    if not candidates.empty:
        active_candidates = int(
            (candidates["lifecycle_status"] == LIFECYCLE_ACTIVE).sum()
        )

    category_rank = {
        LIFECYCLE_ACTIVE: 40,
        LIFECYCLE_VALIDATED: 30,
        LIFECYCLE_CANDIDATE: 20,
        LIFECYCLE_NEEDS_PARSER_REVIEW: 10,
        LIFECYCLE_REJECTED: 5,
        LIFECYCLE_SUPERSEDED: 1,
    }
    electricity_categories: dict[str, str] = {}
    category_scores: dict[str, int] = {}
    for _, row in candidates.iterrows():
        if _text(row.get("reference_type")) not in ELECTRICITY_CANDIDATE_REF_TYPES:
            continue
        category = _text(row.get("factor_category"))
        if not category:
            continue
        lifecycle = _text(row.get("lifecycle_status"))
        if lifecycle == LIFECYCLE_ACTIVE:
            label = "active"
        elif lifecycle == LIFECYCLE_VALIDATED:
            label = "validated / not active"
        elif lifecycle == LIFECYCLE_CANDIDATE:
            label = "candidate / not active"
        elif lifecycle == LIFECYCLE_NEEDS_PARSER_REVIEW:
            label = "needs_parser_review"
        else:
            label = lifecycle or "unknown"
        score = category_rank.get(lifecycle, 0)
        if score >= category_scores.get(category, -1):
            category_scores[category] = score
            electricity_categories[category] = label

    moea = sources.loc[
        sources["source_id"] == "src_tw_moea_electricity_factor"
    ]
    moenv = sources.loc[
        sources["source_id"] == "src_tw_moenv_electricity_factor_enterprise"
    ]
    upstream_status = "recorded / access restricted"
    if not moea.empty and normalize_fetch_mode(
        moea.iloc[0].get("fetch_mode")
    ) == FETCH_MODE_PROVENANCE_ONLY:
        upstream_status = "recorded / access restricted"
    operational_status = "configured"
    if not moenv.empty:
        operational_status = "available"
        # Prefer latest operational snapshot host as evidence of successful sync.
        op_snaps = snapshots.loc[
            snapshots["source_id"] == "src_tw_moenv_electricity_factor_enterprise"
        ]
        if op_snaps.empty:
            operational_status = "configured (not yet fetched)"

    return SyncStatus(
        electricity_years=dict(sorted(electricity_years.items())),
        heating_value_latest=heating_latest,
        last_checked_at=last_checked or "never",
        snapshot_count=int(len(snapshots)),
        candidate_count=int(len(candidates)),
        active_candidate_count=active_candidates,
        source_count=int(len(active_sources(sources))),
        upstream_factor_authority=(
            _text(moea.iloc[0].get("authority"))
            if not moea.empty
            else "Taiwan Ministry of Economic Affairs / Energy Administration"
        ),
        operational_source_authority=(
            _text(moenv.iloc[0].get("authority"))
            if not moenv.empty
            else (
                "Taiwan Ministry of Environment / Climate Change Administration"
            )
        ),
        upstream_source_status=upstream_status,
        operational_source_status=operational_status,
        upstream_canonical_url=(
            _text(moea.iloc[0].get("canonical_url"))
            if not moea.empty
            else ""
        ),
        operational_source_url=(
            _text(moenv.iloc[0].get("landing_url"))
            if not moenv.empty
            else ""
        ),
        electricity_categories=dict(sorted(electricity_categories.items())),
    )


def format_missing_year_factor_message(
    *,
    activity_year: str,
    registered_years: list[str] | tuple[str, ...],
) -> str:
    """Beginner-facing blocked message when the activity year has no factor."""
    registered = ", ".join(registered_years) if registered_years else "(none)"
    return (
        "尚未找到適用於這筆活動期間的官方排放係數。\n"
        f"活動期間：\n{activity_year}\n"
        f"目前已登錄：\n{registered}\n"
        "系統不會自動使用不同年度的係數。"
    )


def list_registered_electricity_years(emission_factors: pd.DataFrame) -> list[str]:
    """Return sorted electricity factor years from the local registry."""
    if emission_factors is None or emission_factors.empty:
        return []
    frame = emission_factors
    if "activity_type" not in frame.columns:
        return []
    rows = frame.loc[frame["activity_type"].astype(str) == "grid_electricity"]
    years = sorted(
        {
            _text(value)
            for value in rows.get("factor_year", pd.Series(dtype=str)).tolist()
            if _text(value)
        }
    )
    return years


def explicit_fallback_rule_applies(
    rules: pd.DataFrame,
    *,
    reference_type: str,
    activity_date: str | date | pd.Timestamp,
) -> dict[str, str] | None:
    """Return an active explicit fallback rule when one covers the activity date.

    Matching engines must not invent previous-year fallback. This helper only
    exposes rules that were registered with provenance.
    """
    if rules is None or rules.empty:
        return None
    activity = _parse_date(str(activity_date))
    if activity is None:
        return None
    for _, row in rules.iterrows():
        if not _truthy(row.get("active")):
            continue
        if _text(row.get("reference_type")) != reference_type:
            continue
        start = _parse_date(_text(row.get("valid_from")))
        end = _parse_date(_text(row.get("valid_to")))
        if start and activity < start:
            continue
        if end and activity > end:
            continue
        return {column: _text(row.get(column)) for column in RULE_COLUMNS}
    return None
