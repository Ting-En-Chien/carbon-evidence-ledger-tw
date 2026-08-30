"""Company-isolated legal-entity facts for inventory-boundary confirmation.

These records capture local workspace confirmation only.  They do not model
authenticated users, review roles, or audit-grade approval.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

CONFIRMATION_DRAFT = "draft"
CONFIRMATION_PENDING = "pending_confirmation"
CONFIRMATION_LOCAL = "locally_confirmed"
CONFIRMATION_SUPERSEDED = "superseded"
CONFIRMATION_STATES = frozenset(
    {
        CONFIRMATION_DRAFT,
        CONFIRMATION_PENDING,
        CONFIRMATION_LOCAL,
        CONFIRMATION_SUPERSEDED,
    }
)
LOCAL_CONFIRMATION_METHOD = "local_workspace_unverified"


@dataclass(frozen=True)
class LegalEntity:
    """One legal company; Taiwan UBN is optional for overseas entities."""

    entity_id: str
    legal_name: str
    jurisdiction: str
    registration_id: str = ""
    taiwan_ubn: str = ""
    parent_entity_id: str = ""
    source: str = "customer_entered"
    confirmation_state: str = CONFIRMATION_PENDING
    confirmation_method: str = LOCAL_CONFIRMATION_METHOD
    locally_confirmed_at: str = ""
    responsible_contact_name: str = ""
    responsible_job_title: str = ""

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            raise ValueError("entity_id is required")
        if not self.legal_name.strip():
            raise ValueError("legal_name is required")
        if not self.jurisdiction.strip():
            raise ValueError("jurisdiction is required")
        if self.confirmation_state not in CONFIRMATION_STATES:
            raise ValueError("invalid confirmation_state")
        if self.confirmation_method != LOCAL_CONFIRMATION_METHOD:
            raise ValueError("unsupported confirmation_method")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> LegalEntity:
        values = dict(raw or {})
        return cls(
            entity_id=str(values.get("entity_id") or ""),
            legal_name=str(values.get("legal_name") or ""),
            jurisdiction=str(values.get("jurisdiction") or ""),
            registration_id=str(values.get("registration_id") or ""),
            taiwan_ubn=str(values.get("taiwan_ubn") or ""),
            parent_entity_id=str(values.get("parent_entity_id") or ""),
            source=str(values.get("source") or "customer_entered"),
            confirmation_state=str(
                values.get("confirmation_state") or CONFIRMATION_PENDING
            ),
            confirmation_method=str(
                values.get("confirmation_method") or LOCAL_CONFIRMATION_METHOD
            ),
            locally_confirmed_at=str(values.get("locally_confirmed_at") or ""),
            responsible_contact_name=str(
                values.get("responsible_contact_name") or ""
            ),
            responsible_job_title=str(values.get("responsible_job_title") or ""),
        )
