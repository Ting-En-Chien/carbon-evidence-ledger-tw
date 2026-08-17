"""Official regulatory change signals (Stage 3B.1).

Change signals detect that a source MAY have changed.
They MUST NEVER directly modify ACTIVE regulatory rules.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SIGNAL_TYPES = frozenset(
    {
        "OFFICIAL_EMAIL_ALERT",
        "OFFICIAL_API_CHANGE",
        "OFFICIAL_OPEN_DATA_CHANGE",
        "AUTHORIZED_WEB_CHANGE",
        "MANUAL_ADMIN_SIGNAL",
        "LICENSED_FEED_CHANGE",
    }
)

SIGNAL_STATUSES = frozenset(
    {
        "NEW",
        "POTENTIAL_REGULATORY_CHANGE",
        "PENDING_REVIEW",
        "REVIEWED_NO_RULE_CHANGE",
        "VERIFIED_REGULATORY_CHANGE",
        "DISMISSED",
    }
)

# Statuses that mean a human still needs to decide.
PENDING_SIGNAL_STATUSES = frozenset(
    {"NEW", "POTENTIAL_REGULATORY_CHANGE", "PENDING_REVIEW"}
)

# Official IFRS Foundation alert senders (email signal only — never scrape ifrs.org).
DEFAULT_IFRS_APPROVED_SENDERS = frozenset(
    {
        "noreply@ifrs.org",
        "alerts@ifrs.org",
        "info@ifrs.org",
        "communications@ifrs.org",
        "newsletter@ifrs.org",
    }
)
DEFAULT_IFRS_APPROVED_DOMAINS = frozenset({"ifrs.org"})
DEFAULT_IFRS_LABEL = "Regulatory-IFRS"

IFRS_TOPIC_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("IFRS_S1", ("ifrs s1", "ifrs sustainability disclosure standard s1", "issb s1")),
    ("IFRS_S2", ("ifrs s2", "climate-related disclosures", "issb s2")),
    (
        "IFRS_S2_GHG_AMENDMENTS",
        ("greenhouse gas emissions", "amendment", "amendments to ifrs s2"),
    ),
    ("IFRS_GENERAL", ("ifrs", "issb", "sustainability disclosure")),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_signals_state_path(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "data" / "regulatory" / "change_signals_state.json"


def normalize_subject(subject: str) -> str:
    text = re.sub(r"\s+", " ", str(subject or "").strip().lower())
    return text


def signal_fingerprint(
    *,
    source_id: str,
    external_message_id: str = "",
    subject: str = "",
    detected_date: str = "",
) -> str:
    """Stable dedupe key from message id, or subject+date fallback."""
    sid = str(source_id or "").strip()
    mid = str(external_message_id or "").strip()
    if mid:
        raw = f"{sid}|msg|{mid}"
    else:
        raw = f"{sid}|subj|{normalize_subject(subject)}|{str(detected_date or '')[:10]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_official_url_from_text(text: str) -> str:
    """Extract first http(s) URL without following it."""
    match = re.search(r"https?://[^\s<>\"']+", str(text or ""))
    if not match:
        return ""
    return match.group(0).rstrip(").,;")


def infer_ifrs_topics(subject: str, snippet: str = "") -> list[str]:
    blob = f"{subject} {snippet}".lower()
    topics: list[str] = []
    for topic, keys in IFRS_TOPIC_KEYWORDS:
        if any(k in blob for k in keys):
            topics.append(topic)
    if not topics and ("ifrs" in blob or "issb" in blob):
        topics.append("IFRS_GENERAL")
    return topics


def map_topics_to_source_ids(topics: Sequence[str]) -> list[str]:
    """Map alert topics to registry source_ids (metadata only)."""
    mapping = {
        "IFRS_S1": ["src_issb_ifrs_s1_2023"],
        "IFRS_S2": ["src_issb_ifrs_s2_2023"],
        "IFRS_S2_GHG_AMENDMENTS": [
            "src_issb_ifrs_s2_2023",
            "src_issb_ifrs_s2_ghg_amendments_2025",
        ],
        "IFRS_GENERAL": [
            "src_issb_ifrs_s1_2023",
            "src_issb_ifrs_s2_2023",
            "src_issb_knowledge_hub",
        ],
    }
    out: list[str] = []
    for topic in topics:
        for sid in mapping.get(topic, []):
            if sid not in out:
                out.append(sid)
    return out or ["src_issb_ifrs_s1_2023", "src_issb_ifrs_s2_2023"]


@dataclass
class RegulatoryChangeSignal:
    signal_id: str
    source_id: str
    signal_type: str
    detected_at: str
    official_sender: str = ""
    official_subject: str = ""
    official_reference_url: str = ""
    external_message_id: str = ""
    signal_fingerprint: str = ""
    affected_topics: list[str] = field(default_factory=list)
    status: str = "POTENTIAL_REGULATORY_CHANGE"
    reviewed_at: str = ""
    reviewed_by: str = ""
    notes: str = ""
    topic_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RegulatoryChangeSignal":
        topics = raw.get("affected_topics") or []
        if isinstance(topics, str):
            topics = [t.strip() for t in topics.split("|") if t.strip()]
        return cls(
            signal_id=str(raw.get("signal_id") or ""),
            source_id=str(raw.get("source_id") or ""),
            signal_type=str(raw.get("signal_type") or "MANUAL_ADMIN_SIGNAL"),
            detected_at=str(raw.get("detected_at") or ""),
            official_sender=str(raw.get("official_sender") or ""),
            official_subject=str(raw.get("official_subject") or ""),
            official_reference_url=str(raw.get("official_reference_url") or ""),
            external_message_id=str(raw.get("external_message_id") or ""),
            signal_fingerprint=str(raw.get("signal_fingerprint") or ""),
            affected_topics=list(topics),
            status=str(raw.get("status") or "NEW"),
            reviewed_at=str(raw.get("reviewed_at") or ""),
            reviewed_by=str(raw.get("reviewed_by") or ""),
            notes=str(raw.get("notes") or ""),
            topic_snippet=str(raw.get("topic_snippet") or ""),
        )


@dataclass(frozen=True)
class AlertMessage:
    """Minimal mailbox metadata — never store full standard text."""

    message_id: str
    sender: str
    subject: str
    received_at: str
    label: str = ""
    snippet: str = ""
    official_link: str = ""


class RegulatorySignalAdapter(ABC):
    """Mailbox / feed adapter interface."""

    @abstractmethod
    def fetch_candidate_messages(self) -> list[AlertMessage]:
        raise NotImplementedError


class MockMailboxAdapter(RegulatorySignalAdapter):
    """Deterministic fixture adapter for unit tests."""

    def __init__(self, messages: Sequence[AlertMessage] | None = None) -> None:
        self._messages = list(messages or [])

    def fetch_candidate_messages(self) -> list[AlertMessage]:
        return list(self._messages)


class GmailAlertAdapter(RegulatorySignalAdapter):
    """Optional Gmail adapter using env credentials (never stored in repo).

    Required env (when live):
      REGULATORY_GMAIL_CLIENT_ID
      REGULATORY_GMAIL_CLIENT_SECRET
      REGULATORY_GMAIL_REFRESH_TOKEN

    Optional:
      REGULATORY_GMAIL_LABEL (default Regulatory-IFRS)
    """

    def __init__(
        self,
        *,
        label: str | None = None,
        max_results: int = 25,
    ) -> None:
        self.label = label or os.environ.get(
            "REGULATORY_GMAIL_LABEL", DEFAULT_IFRS_LABEL
        )
        self.max_results = max_results
        self.client_id = os.environ.get("REGULATORY_GMAIL_CLIENT_ID", "")
        self.client_secret = os.environ.get("REGULATORY_GMAIL_CLIENT_SECRET", "")
        self.refresh_token = os.environ.get("REGULATORY_GMAIL_REFRESH_TOKEN", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def fetch_candidate_messages(self) -> list[AlertMessage]:
        if not self.is_configured:
            return []
        # Live Gmail API wiring is intentionally deferred: credentials must be
        # provided via secrets; unit tests use MockMailboxAdapter.
        # Returning empty keeps scheduled runs safe when secrets are absent.
        return []


def sender_allowed(
    sender: str,
    *,
    approved_senders: Iterable[str] = DEFAULT_IFRS_APPROVED_SENDERS,
    approved_domains: Iterable[str] = DEFAULT_IFRS_APPROVED_DOMAINS,
) -> bool:
    raw = str(sender or "").strip().lower()
    if not raw:
        return False
    # Extract email from "Name <email@domain>"
    match = re.search(r"[\w.+\-]+@[\w.\-]+", raw)
    email = match.group(0).lower() if match else raw
    if email in {s.lower() for s in approved_senders}:
        return True
    domain = email.split("@")[-1] if "@" in email else ""
    return domain in {d.lower() for d in approved_domains}


def label_allowed(label: str, *, required_label: str = DEFAULT_IFRS_LABEL) -> bool:
    return str(label or "").strip() == str(required_label).strip()


def ingest_ifrs_alert_message(
    message: AlertMessage,
    *,
    require_label: bool = True,
    required_label: str = DEFAULT_IFRS_LABEL,
    now_iso: str | None = None,
) -> RegulatoryChangeSignal | None:
    """Convert an approved IFRS alert email into a change signal.

    Does NOT fetch ifrs.org. Does NOT activate rules.
    """
    if not sender_allowed(message.sender):
        return None
    if require_label and not label_allowed(
        message.label, required_label=required_label
    ):
        return None

    topics = infer_ifrs_topics(message.subject, message.snippet)
    source_ids = map_topics_to_source_ids(topics)
    primary_source = source_ids[0]
    detected = now_iso or message.received_at or utc_now_iso()
    link = message.official_link or extract_official_url_from_text(
        f"{message.subject} {message.snippet}"
    )
    # Prefer ifrs.org links as reference metadata only — never HTTP-fetch them.
    fp = signal_fingerprint(
        source_id=primary_source,
        external_message_id=message.message_id,
        subject=message.subject,
        detected_date=detected,
    )
    signal_id = f"sig_{fp[:16]}"
    snippet = str(message.snippet or "")[:240]
    return RegulatoryChangeSignal(
        signal_id=signal_id,
        source_id=primary_source,
        signal_type="OFFICIAL_EMAIL_ALERT",
        detected_at=detected,
        official_sender=message.sender,
        official_subject=message.subject[:500],
        official_reference_url=link,
        external_message_id=message.message_id,
        signal_fingerprint=fp,
        affected_topics=topics,
        status="POTENTIAL_REGULATORY_CHANGE",
        notes=(
            "Official IFRS email alert ingested as signal only. "
            "No ifrs.org fetch. No automatic rule activation. "
            f"Related sources: {'|'.join(source_ids)}"
        ),
        topic_snippet=snippet,
    )


class RegulatorySignalStore:
    """Persist change signals without storing full email bodies."""

    def __init__(
        self, path: Path | None = None, *, repo_root: Path | None = None
    ) -> None:
        self.path = (
            Path(path)
            if path is not None
            else default_signals_state_path(repo_root)
        )

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "schema_version": 1,
                "updated_at": "",
                "last_verified_regulatory_update_at": "",
                "signals": [],
            }
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(payload)
        payload["updated_at"] = utc_now_iso()
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list_signals(self) -> list[RegulatoryChangeSignal]:
        raw = self.load().get("signals") or []
        return [RegulatoryChangeSignal.from_dict(item) for item in raw]

    def fingerprints(self) -> set[str]:
        return {
            s.signal_fingerprint
            for s in self.list_signals()
            if s.signal_fingerprint
        }

    def upsert_signal(
        self, signal: RegulatoryChangeSignal
    ) -> tuple[RegulatoryChangeSignal, bool]:
        """Insert signal if fingerprint is new. Returns (signal, created)."""
        payload = self.load()
        signals = [
            RegulatoryChangeSignal.from_dict(item)
            for item in (payload.get("signals") or [])
        ]
        for existing in signals:
            if existing.signal_fingerprint == signal.signal_fingerprint:
                return existing, False
        signals.append(signal)
        payload["signals"] = [s.to_dict() for s in signals]
        self.save(payload)
        return signal, True

    def update_signal_status(
        self,
        signal_id: str,
        *,
        status: str,
        reviewed_by: str = "",
        notes: str = "",
    ) -> RegulatoryChangeSignal | None:
        if status not in SIGNAL_STATUSES:
            raise ValueError(f"Invalid signal status: {status}")
        payload = self.load()
        signals = [
            RegulatoryChangeSignal.from_dict(item)
            for item in (payload.get("signals") or [])
        ]
        updated: RegulatoryChangeSignal | None = None
        for sig in signals:
            if sig.signal_id != signal_id:
                continue
            sig.status = status
            sig.reviewed_at = utc_now_iso()
            sig.reviewed_by = reviewed_by
            if notes:
                sig.notes = notes
            updated = sig
            if status in {
                "REVIEWED_NO_RULE_CHANGE",
                "VERIFIED_REGULATORY_CHANGE",
                "DISMISSED",
            }:
                payload["last_verified_regulatory_update_at"] = sig.reviewed_at
            break
        if updated is None:
            return None
        payload["signals"] = [s.to_dict() for s in signals]
        self.save(payload)
        return updated

    def pending_signals(self) -> list[RegulatoryChangeSignal]:
        return [s for s in self.list_signals() if s.status in PENDING_SIGNAL_STATUSES]

    def pending_count(self) -> int:
        return len(self.pending_signals())


def ingest_alerts_from_adapter(
    adapter: RegulatorySignalAdapter,
    store: RegulatorySignalStore,
    *,
    require_label: bool = True,
) -> dict[str, Any]:
    """Ingest approved alert messages into the signal store (deduped)."""
    created = 0
    skipped_unapproved = 0
    duplicates = 0
    for message in adapter.fetch_candidate_messages():
        signal = ingest_ifrs_alert_message(message, require_label=require_label)
        if signal is None:
            skipped_unapproved += 1
            continue
        _, was_created = store.upsert_signal(signal)
        if was_created:
            created += 1
        else:
            duplicates += 1
    return {
        "created": created,
        "duplicates": duplicates,
        "skipped_unapproved": skipped_unapproved,
        "pending_review": store.pending_count(),
    }


def pending_source_ids(store: RegulatorySignalStore) -> set[str]:
    """Sources referenced by pending signals (including notes-related sources)."""
    out: set[str] = set()
    for sig in store.pending_signals():
        out.add(sig.source_id)
        # Related sources encoded in notes: "Related sources: a|b|c"
        match = re.search(r"Related sources:\s*([^\n]+)", sig.notes or "")
        if match:
            for part in match.group(1).split("|"):
                part = part.strip()
                if part:
                    out.add(part)
        for topic in sig.affected_topics:
            for sid in map_topics_to_source_ids([topic]):
                out.add(sid)
    return out


def admin_review_no_rule_change(
    store: RegulatorySignalStore,
    signal_id: str,
    *,
    reviewed_by: str,
    notes: str = "",
) -> RegulatoryChangeSignal | None:
    """Mark signal reviewed with no registry mutation."""
    return store.update_signal_status(
        signal_id,
        status="REVIEWED_NO_RULE_CHANGE",
        reviewed_by=reviewed_by,
        notes=notes or "Admin confirmed no rule change required.",
    )


def admin_mark_verified_regulatory_change(
    store: RegulatorySignalStore,
    signal_id: str,
    *,
    reviewed_by: str,
    notes: str = "",
) -> RegulatoryChangeSignal | None:
    """Mark signal verified. Does NOT mutate rule CSV — caller creates new version."""
    return store.update_signal_status(
        signal_id,
        status="VERIFIED_REGULATORY_CHANGE",
        reviewed_by=reviewed_by,
        notes=notes
        or (
            "Admin verified regulatory change. "
            "Create/update a NEW rule version via registry workflow; "
            "do not mutate historical versions in place."
        ),
    )


__all__ = [
    "DEFAULT_IFRS_APPROVED_DOMAINS",
    "DEFAULT_IFRS_APPROVED_SENDERS",
    "DEFAULT_IFRS_LABEL",
    "AlertMessage",
    "GmailAlertAdapter",
    "MockMailboxAdapter",
    "PENDING_SIGNAL_STATUSES",
    "RegulatoryChangeSignal",
    "RegulatorySignalAdapter",
    "RegulatorySignalStore",
    "SIGNAL_STATUSES",
    "SIGNAL_TYPES",
    "admin_mark_verified_regulatory_change",
    "admin_review_no_rule_change",
    "ingest_alerts_from_adapter",
    "ingest_ifrs_alert_message",
    "label_allowed",
    "pending_source_ids",
    "sender_allowed",
    "signal_fingerprint",
]
