"""Local prototype persistence for company inventory-boundary facts.

This is not an enterprise record store.  It provides no authenticated identity,
RBAC, server-side access control, concurrency control, cloud backup, or
encryption.  Files are local plaintext unless the operating system protects
them.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from carbon_ledger.inventory_boundary import (
    BoundarySemanticsState,
    InventoryBoundary,
    utc_now_iso,
)
from carbon_ledger.legal_entity import (
    CONFIRMATION_LOCAL,
    LOCAL_CONFIRMATION_METHOD,
)

WORKSPACE_ENV = "CEL_COMPANY_WORKSPACE_DIR"
_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,127}$")


def default_workspace_root(repo_root: Path | None = None) -> Path:
    configured = str(os.environ.get(WORKSPACE_ENV) or "").strip()
    if configured:
        return Path(configured).expanduser()
    root = Path(repo_root) if repo_root is not None else Path.cwd()
    return root / "private_data" / "company_workspaces"


def workspace_id_for_company(*, taiwan_ubn: str = "", entity_id: str = "") -> str:
    ubn = str(taiwan_ubn or "").strip()
    if re.fullmatch(r"\d{8}", ubn):
        return f"tw-ubn-{ubn}"
    entity = str(entity_id or "").strip()
    if _SAFE_ID.fullmatch(entity):
        return f"entity-{entity}"
    raise ValueError("a confirmed Taiwan UBN or stable entity_id is required")


class CompanyWorkspace:
    """Read and append one company's reporting-period-isolated local records."""

    def __init__(self, root: Path, workspace_id: str) -> None:
        if not _SAFE_ID.fullmatch(workspace_id):
            raise ValueError("unsafe workspace_id")
        self.root = Path(root)
        self.workspace_id = workspace_id
        self.path = self.root / workspace_id

    @classmethod
    def for_company(
        cls,
        *,
        root: Path,
        taiwan_ubn: str = "",
        entity_id: str = "",
    ) -> CompanyWorkspace:
        return cls(
            root,
            workspace_id_for_company(
                taiwan_ubn=taiwan_ubn, entity_id=entity_id
            ),
        )

    def write_draft(self, boundary: InventoryBoundary) -> Path:
        period_dir = self._period_dir(boundary)
        destination = period_dir / "boundaries" / "drafts" / (
            f"{boundary.boundary_id}.json"
        )
        self._atomic_json(destination, boundary.to_dict())
        return destination

    def load_draft(
        self, *, reporting_period_id: str, boundary_id: str
    ) -> InventoryBoundary | None:
        """Load one mutable draft from an exact reporting period."""
        period_dir = self._period_dir_from_id(reporting_period_id)
        if not _SAFE_ID.fullmatch(str(boundary_id or "")):
            raise ValueError("unsafe boundary_id")
        path = period_dir / "boundaries" / "drafts" / f"{boundary_id}.json"
        if not path.is_file():
            return None
        boundary = InventoryBoundary.from_dict(self._read_json(path))
        if boundary.reporting_period.reporting_period_id != reporting_period_id:
            raise ValueError("draft crosses reporting-period identity")
        if boundary.boundary_id != boundary_id:
            raise ValueError("draft crosses boundary identity")
        return boundary

    def append_locally_confirmed(
        self, boundary: InventoryBoundary
    ) -> InventoryBoundary:
        if boundary.confirmation_state != CONFIRMATION_LOCAL:
            raise ValueError("only locally_confirmed boundaries can be versioned")
        if boundary.confirmation_method != LOCAL_CONFIRMATION_METHOD:
            raise ValueError("unsupported confirmation_method")
        boundary.reporting_period.require_explicit_confirmation()
        boundary = boundary.with_normalized_confirmer_details()
        period_dir = self._period_dir(boundary)
        versions_dir = (
            period_dir / "boundaries" / "versions" / boundary.boundary_id
        )
        next_version = self._next_version(versions_dir)
        versioned = replace(boundary, version=next_version)
        destination = versions_dir / f"v{next_version:04d}.json"
        if destination.exists():
            raise FileExistsError(destination)
        self._atomic_json(destination, versioned.to_dict(), replace_existing=False)
        pointer = {
            "boundary_id": boundary.boundary_id,
            "reporting_period_id": boundary.reporting_period.reporting_period_id,
            "version": next_version,
            "relative_path": str(destination.relative_to(period_dir)),
            "confirmation_method": LOCAL_CONFIRMATION_METHOD,
            "updated_at": utc_now_iso(),
        }
        self._atomic_json(self._pointer_path(period_dir, boundary.boundary_id), pointer)
        self._append_event(
            period_dir,
            {
                "event": "locally_confirmed",
                "boundary_id": boundary.boundary_id,
                "version": next_version,
                "at": pointer["updated_at"],
                "confirmation_method": LOCAL_CONFIRMATION_METHOD,
            },
        )
        return versioned

    def load_current(
        self, *, reporting_period_id: str, boundary_id: str
    ) -> InventoryBoundary | None:
        period_dir = self._period_dir_from_id(reporting_period_id)
        pointer_path = self._pointer_path(period_dir, boundary_id)
        if not pointer_path.exists():
            return None
        pointer = self._read_json(pointer_path)
        relative = Path(str(pointer.get("relative_path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe current pointer")
        target = period_dir / relative
        if not target.is_file():
            raise FileNotFoundError(target)
        boundary = InventoryBoundary.from_dict(self._read_json(target))
        if boundary.reporting_period.reporting_period_id != reporting_period_id:
            raise ValueError("current pointer crosses reporting-period identity")
        return boundary

    def load_latest_current_for_boundary(
        self, *, boundary_id: str
    ) -> InventoryBoundary | None:
        """Load the newest current pointer across confirmed period directories."""
        if not _SAFE_ID.fullmatch(str(boundary_id or "")):
            raise ValueError("unsafe boundary_id")
        periods_dir = self.path / "periods"
        if not periods_dir.is_dir():
            return None
        candidates: list[tuple[str, str]] = []
        for period_dir in periods_dir.iterdir():
            if not period_dir.is_dir() or not _SAFE_ID.fullmatch(period_dir.name):
                continue
            pointer_path = self._pointer_path(period_dir, boundary_id)
            if not pointer_path.is_file():
                continue
            pointer = self._read_json(pointer_path)
            candidates.append(
                (str(pointer.get("updated_at") or ""), period_dir.name)
            )
        if not candidates:
            return None
        _, reporting_period_id = max(candidates)
        return self.load_current(
            reporting_period_id=reporting_period_id,
            boundary_id=boundary_id,
        )

    def list_current_for_boundary(
        self, *, boundary_id: str
    ) -> list[InventoryBoundary]:
        """List period-isolated current records without selecting a latest one."""
        if not _SAFE_ID.fullmatch(str(boundary_id or "")):
            raise ValueError("unsafe boundary_id")
        periods_dir = self.path / "periods"
        if not periods_dir.is_dir():
            return []
        boundaries: list[InventoryBoundary] = []
        for period_dir in sorted(periods_dir.iterdir(), key=lambda path: path.name):
            if not period_dir.is_dir() or not _SAFE_ID.fullmatch(period_dir.name):
                continue
            current = self.load_current(
                reporting_period_id=period_dir.name,
                boundary_id=boundary_id,
            )
            if current is not None:
                boundaries.append(current)
        return sorted(
            boundaries,
            key=lambda boundary: (
                boundary.reporting_period.reporting_year_confirmed or 0,
                boundary.reporting_period.period_start_confirmed,
                boundary.reporting_period.period_end_confirmed,
                boundary.reporting_period.reporting_period_id,
            ),
        )

    def list_drafts_for_boundary(
        self, *, boundary_id: str
    ) -> list[InventoryBoundary]:
        """List exact-period mutable drafts without treating them as current."""
        if not _SAFE_ID.fullmatch(str(boundary_id or "")):
            raise ValueError("unsafe boundary_id")
        periods_dir = self.path / "periods"
        if not periods_dir.is_dir():
            return []
        drafts: list[InventoryBoundary] = []
        for period_dir in sorted(periods_dir.iterdir(), key=lambda path: path.name):
            if not period_dir.is_dir() or not _SAFE_ID.fullmatch(period_dir.name):
                continue
            draft = self.load_draft(
                reporting_period_id=period_dir.name,
                boundary_id=boundary_id,
            )
            if draft is not None:
                drafts.append(draft)
        return sorted(
            drafts,
            key=lambda boundary: (
                boundary.reporting_period.reporting_year_confirmed or 0,
                boundary.reporting_period.period_start_confirmed,
                boundary.reporting_period.period_end_confirmed,
                boundary.reporting_period.reporting_period_id,
            ),
        )

    def list_current(self, *, reporting_period_id: str) -> list[InventoryBoundary]:
        period_dir = self._period_dir_from_id(reporting_period_id)
        current_dir = period_dir / "boundaries" / "current"
        if not current_dir.is_dir():
            return []
        boundaries: list[InventoryBoundary] = []
        for pointer_path in sorted(current_dir.glob("*.json")):
            boundary_id = pointer_path.stem
            current = self.load_current(
                reporting_period_id=reporting_period_id,
                boundary_id=boundary_id,
            )
            if current is not None:
                boundaries.append(current)
        return boundaries

    def rollback(
        self,
        *,
        reporting_period_id: str,
        boundary_id: str,
        version: int,
        reason: str,
    ) -> InventoryBoundary:
        if version < 1:
            raise ValueError("version must be positive")
        if not str(reason or "").strip():
            raise ValueError("rollback reason is required")
        period_dir = self._period_dir_from_id(reporting_period_id)
        target = (
            period_dir
            / "boundaries"
            / "versions"
            / boundary_id
            / f"v{version:04d}.json"
        )
        if not target.is_file():
            raise FileNotFoundError(target)
        boundary = InventoryBoundary.from_dict(self._read_json(target))
        if boundary.reporting_period.reporting_period_id != reporting_period_id:
            raise ValueError("rollback target crosses reporting-period identity")
        pointer = {
            "boundary_id": boundary_id,
            "reporting_period_id": reporting_period_id,
            "version": version,
            "relative_path": str(target.relative_to(period_dir)),
            "confirmation_method": LOCAL_CONFIRMATION_METHOD,
            "updated_at": utc_now_iso(),
        }
        self._atomic_json(self._pointer_path(period_dir, boundary_id), pointer)
        self._append_event(
            period_dir,
            {
                "event": "rollback",
                "boundary_id": boundary_id,
                "version": version,
                "reason": str(reason).strip(),
                "at": pointer["updated_at"],
                "confirmation_method": LOCAL_CONFIRMATION_METHOD,
            },
        )
        return boundary

    def write_semantics_draft(self, state: BoundarySemanticsState) -> Path:
        """Persist one mutable v2 period package without changing current."""
        period_dir = self._period_dir_from_id(
            state.reporting_period.reporting_period_id
        )
        destination = period_dir / "boundary_semantics_v2" / "draft.json"
        self._atomic_json(destination, state.to_dict())
        return destination

    def load_semantics_draft(
        self, *, reporting_period_id: str
    ) -> BoundarySemanticsState | None:
        period_dir = self._period_dir_from_id(reporting_period_id)
        path = period_dir / "boundary_semantics_v2" / "draft.json"
        if not path.is_file():
            return None
        state = BoundarySemanticsState.from_dict(self._read_json(path))
        if state.reporting_period.reporting_period_id != reporting_period_id:
            raise ValueError("v2 draft crosses reporting-period identity")
        return state

    def append_semantics_current(
        self, state: BoundarySemanticsState
    ) -> BoundarySemanticsState:
        """Append an immutable v2 package and atomically advance its pointer."""
        if state.confirmation_state != CONFIRMATION_LOCAL:
            raise ValueError("only locally confirmed v2 state can become current")
        state.reporting_period.require_explicit_confirmation()
        period_dir = self._period_dir_from_id(
            state.reporting_period.reporting_period_id
        )
        versions_dir = period_dir / "boundary_semantics_v2" / "versions"
        next_version = self._next_version(versions_dir)
        versioned = replace(state, version=next_version)
        destination = versions_dir / f"v{next_version:04d}.json"
        if destination.exists():
            raise FileExistsError(destination)
        self._atomic_json(destination, versioned.to_dict(), replace_existing=False)
        pointer = {
            "schema_version": "boundary-semantics-v2",
            "reporting_period_id": state.reporting_period.reporting_period_id,
            "version": next_version,
            "relative_path": str(destination.relative_to(period_dir)),
            "updated_at": utc_now_iso(),
        }
        self._atomic_json(
            period_dir / "boundary_semantics_v2" / "current.json", pointer
        )
        self._atomic_json(
            period_dir / "boundary_semantics_v2" / "migration_state.json",
            {
                "schema_version": "boundary-semantics-v2",
                "reporting_period_id": state.reporting_period.reporting_period_id,
                "activated_at": pointer["updated_at"],
                "version": next_version,
                "relative_path": pointer["relative_path"],
            },
        )
        self._append_event(
            period_dir,
            {
                "event": "boundary_semantics_v2_locally_confirmed",
                "version": next_version,
                "at": pointer["updated_at"],
                "legal_or_official_review_unresolved": (
                    versioned.legal_or_official_review_unresolved
                ),
                "company_actionable_facts_unresolved": (
                    versioned.company_actionable_facts_unresolved
                ),
            },
        )
        return versioned

    def load_semantics_current(
        self, *, reporting_period_id: str
    ) -> BoundarySemanticsState | None:
        period_dir = self._period_dir_from_id(reporting_period_id)
        migration_state_path = (
            period_dir / "boundary_semantics_v2" / "migration_state.json"
        )
        if migration_state_path.is_file():
            migration_state = self._read_json(migration_state_path)
            if migration_state.get("schema_version") == "inventory-boundary-v1":
                return None
            migration_relative = Path(
                str(migration_state.get("relative_path") or "")
            )
            if migration_relative.parts:
                if migration_relative.is_absolute() or ".." in migration_relative.parts:
                    raise ValueError("unsafe v2 migration pointer")
                migration_target = period_dir / migration_relative
                if not migration_target.is_file():
                    raise FileNotFoundError(migration_target)
                state = BoundarySemanticsState.from_dict(
                    self._read_json(migration_target)
                )
                if (
                    state.reporting_period.reporting_period_id
                    != reporting_period_id
                ):
                    raise ValueError(
                        "v2 migration pointer crosses reporting-period identity"
                    )
                return state
        pointer_path = period_dir / "boundary_semantics_v2" / "current.json"
        if not pointer_path.is_file():
            return None
        pointer = self._read_json(pointer_path)
        relative = Path(str(pointer.get("relative_path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe v2 current pointer")
        target = period_dir / relative
        if not target.is_file():
            raise FileNotFoundError(target)
        state = BoundarySemanticsState.from_dict(self._read_json(target))
        if state.reporting_period.reporting_period_id != reporting_period_id:
            raise ValueError("v2 current pointer crosses reporting-period identity")
        return state

    def list_semantics_periods(self) -> list[BoundarySemanticsState]:
        """List period-isolated v2 states, preferring resumable drafts."""
        periods_dir = self.path / "periods"
        if not periods_dir.is_dir():
            return []
        states: list[BoundarySemanticsState] = []
        for period_dir in sorted(periods_dir.iterdir(), key=lambda path: path.name):
            if not period_dir.is_dir() or not _SAFE_ID.fullmatch(period_dir.name):
                continue
            state = self.load_semantics_draft(reporting_period_id=period_dir.name)
            if state is None:
                state = self.load_semantics_current(
                    reporting_period_id=period_dir.name
                )
            if state is not None:
                states.append(state)
        return sorted(
            states,
            key=lambda item: (
                item.reporting_period.reporting_year_confirmed or 0,
                item.reporting_period.period_start_confirmed,
                item.reporting_period.period_end_confirmed,
            ),
        )

    def boundary_semantics_migration_status(
        self, *, reporting_period_id: str
    ) -> str:
        period_dir = self._period_dir_from_id(reporting_period_id)
        migration_state_path = (
            period_dir / "boundary_semantics_v2" / "migration_state.json"
        )
        if migration_state_path.is_file():
            active_schema = self._read_json(migration_state_path).get(
                "schema_version"
            )
            if active_schema == "inventory-boundary-v1":
                return "v1_detected"
            if active_schema == "boundary-semantics-v2":
                return "v2_current"
        current = period_dir / "boundary_semantics_v2" / "current.json"
        if current.is_file():
            return "v2_current"
        legacy = period_dir / "boundaries"
        if legacy.is_dir():
            return "v1_detected"
        return "not_required"

    def dry_run_boundary_semantics_migration(
        self, *, reporting_period_id: str
    ) -> dict[str, Any]:
        """Inspect v1 payloads without writing or promoting inferred facts."""
        period_dir = self._period_dir_from_id(reporting_period_id)
        payloads = self._legacy_boundary_payloads(period_dir)
        registration_ids = {
            str(link.get("registration_link_id") or "")
            for payload in payloads
            for link in payload.get("registration_links") or ()
            if str(link.get("registration_link_id") or "")
        }
        asserted_relationships = sum(
            bool(link.get("combined_with"))
            for payload in payloads
            for link in payload.get("registration_links") or ()
        )
        category_rows = sum(
            len(payload.get("expected_categories") or ()) for payload in payloads
        )
        professional_notes = sum(
            bool(link.get("combination_evidence"))
            for payload in payloads
            for link in payload.get("registration_links") or ()
        )
        return {
            "package": "boundary-semantics-v2",
            "reporting_period_id": reporting_period_id,
            "status": self.boundary_semantics_migration_status(
                reporting_period_id=reporting_period_id
            ),
            "legacy_boundary_records": len(payloads),
            "official_registration_candidates": len(registration_ids),
            "canonical_sites_auto_confirmed": 0,
            "customer_asserted_related_pending_review": asserted_relationships,
            "legacy_facility_memberships_auto_migrated": 0,
            "legacy_source_category_rows_preserved": category_rows,
            "professional_review_notes_not_authority_verified": professional_notes,
            "verified_official_authority_evidence": 0,
            "moenv_boundaries_creatable": 0,
        }

    def prepare_boundary_semantics_v2_migration(
        self, state: BoundarySemanticsState
    ) -> BoundarySemanticsState:
        """Preserve v1 hints without promoting sites, memberships, or evidence."""
        period_dir = self._period_dir_from_id(
            state.reporting_period.reporting_period_id
        )
        payloads = self._legacy_boundary_payloads(period_dir)
        categories = tuple(
            {
                "legacy_boundary_id": str(payload.get("boundary_id") or ""),
                "category": str(category.get("category") or ""),
                "state": str(category.get("state") or ""),
                "reason": str(category.get("reason") or ""),
            }
            for payload in payloads
            for category in payload.get("expected_categories") or ()
        )
        relationships = tuple(
            {
                "state": "customer_asserted_related_pending_review",
                "legacy_boundary_id": str(payload.get("boundary_id") or ""),
                "registration_link_id": str(
                    link.get("registration_link_id") or ""
                ),
                "related_registration_link_ids": tuple(
                    link.get("combined_with") or ()
                ),
                "supporting_note": str(link.get("combination_basis") or ""),
                "professional_review_note": str(
                    link.get("combination_evidence") or ""
                ),
                "verification_state": "customer_supplied_pending_review",
            }
            for payload in payloads
            for link in payload.get("registration_links") or ()
            if link.get("combined_with")
        )
        return replace(
            state,
            boundaries=(),
            canonical_sites=(),
            operating_facts=(),
            legacy_source_category_snapshot=categories,
            customer_asserted_related_pending_review=relationships,
            confirmation_state="draft",
            locally_confirmed_at="",
            version=0,
        )

    def migrate_boundary_semantics_v2(
        self,
        *,
        state: BoundarySemanticsState,
        dry_run_reviewed: bool,
    ) -> BoundarySemanticsState:
        """Explicit, idempotent migration; v1 remains rollback-compatible."""
        if not dry_run_reviewed:
            raise ValueError("migration requires an explicitly reviewed dry-run")
        period_id = state.reporting_period.reporting_period_id
        current = self.load_semantics_current(reporting_period_id=period_id)
        if current is not None:
            return current
        period_dir = self._period_dir_from_id(period_id)
        state.reporting_period.require_explicit_confirmation()
        versions_dir = period_dir / "boundary_semantics_v2" / "versions"
        next_version = self._next_version(versions_dir)
        migrated = replace(state, version=next_version)
        destination = versions_dir / f"v{next_version:04d}.json"
        self._atomic_json(destination, migrated.to_dict(), replace_existing=False)
        activated_at = utc_now_iso()
        self._atomic_json(
            period_dir / "boundary_semantics_v2" / "migration_state.json",
            {
                "schema_version": "boundary-semantics-v2",
                "reporting_period_id": period_id,
                "activated_at": activated_at,
                "version": next_version,
                "relative_path": str(destination.relative_to(period_dir)),
            },
        )
        self._append_event(
            period_dir,
            {
                "event": "boundary_semantics_v2_migrated",
                "version": migrated.version,
                "at": activated_at,
                "rollback_target": "v1",
                "confirmation_state": migrated.confirmation_state,
            },
        )
        return migrated

    def rollback_boundary_semantics_to_v1(
        self, *, reporting_period_id: str, reason: str
    ) -> None:
        """Change the package-selection pointer without deleting v2 history."""
        if not str(reason or "").strip():
            raise ValueError("rollback reason is required")
        period_dir = self._period_dir_from_id(reporting_period_id)
        marker = {
            "schema_version": "inventory-boundary-v1",
            "reporting_period_id": reporting_period_id,
            "rolled_back_at": utc_now_iso(),
            "reason": str(reason).strip(),
        }
        self._atomic_json(
            period_dir / "boundary_semantics_v2" / "migration_state.json",
            marker,
        )
        self._append_event(
            period_dir,
            {
                "event": "boundary_semantics_v2_rollback_to_v1",
                "at": marker["rolled_back_at"],
                "reason": marker["reason"],
            },
        )

    def _period_dir(self, boundary: InventoryBoundary) -> Path:
        return self._period_dir_from_id(
            boundary.reporting_period.reporting_period_id
        )

    def _period_dir_from_id(self, reporting_period_id: str) -> Path:
        value = str(reporting_period_id or "").strip()
        if not _SAFE_ID.fullmatch(value):
            raise ValueError("unsafe reporting_period_id")
        return self.path / "periods" / value

    @staticmethod
    def _pointer_path(period_dir: Path, boundary_id: str) -> Path:
        if not _SAFE_ID.fullmatch(str(boundary_id or "")):
            raise ValueError("unsafe boundary_id")
        return period_dir / "boundaries" / "current" / f"{boundary_id}.json"

    @staticmethod
    def _next_version(versions_dir: Path) -> int:
        if not versions_dir.is_dir():
            return 1
        versions = [
            int(path.stem[1:])
            for path in versions_dir.glob("v[0-9][0-9][0-9][0-9].json")
            if path.stem[1:].isdigit()
        ]
        return max(versions, default=0) + 1

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"expected JSON object: {path}")
        return value

    @classmethod
    def _legacy_boundary_payloads(
        cls, period_dir: Path
    ) -> list[dict[str, Any]]:
        payloads_by_id: dict[str, dict[str, Any]] = {}
        boundaries_dir = period_dir / "boundaries"
        if not boundaries_dir.is_dir():
            return []
        for path in sorted(boundaries_dir.glob("**/*.json")):
            if path.parent.name == "current":
                continue
            try:
                payload = cls._read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            boundary_id = str(payload.get("boundary_id") or "")
            if not boundary_id:
                continue
            previous = payloads_by_id.get(boundary_id)
            if previous is None or int(payload.get("version") or 0) >= int(
                previous.get("version") or 0
            ):
                payloads_by_id[boundary_id] = payload
        return [payloads_by_id[key] for key in sorted(payloads_by_id)]

    @staticmethod
    def _atomic_json(
        destination: Path,
        payload: dict[str, Any],
        *,
        replace_existing: bool = True,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not replace_existing and destination.exists():
            raise FileExistsError(destination)
        temporary = destination.with_name(f".{destination.name}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            if not replace_existing and destination.exists():
                raise FileExistsError(destination)
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _append_event(period_dir: Path, event: dict[str, Any]) -> None:
        path = period_dir / "boundaries" / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
