"""Application product modes (Stage 3B.3).

CUSTOMER — default company-facing experience (empty workspace).
DEMO — explicit synthetic-data demonstration.
ADMIN — development/ops visibility for monitoring internals.

Real authentication / RBAC is future production work. This module is an
application-mode abstraction only — not a security boundary.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

STATE_APP_MODE = "cel_app_mode"
ENV_APP_MODE = "CEL_APP_MODE"


class AppMode(str, Enum):
    CUSTOMER = "customer"
    DEMO = "demo"
    ADMIN = "admin"


def _normalize_mode(value: Any) -> AppMode:
    text = str(value or "").strip().lower()
    if text in {AppMode.DEMO.value, "demonstration"}:
        return AppMode.DEMO
    if text in {AppMode.ADMIN.value, "administrator", "ops"}:
        return AppMode.ADMIN
    return AppMode.CUSTOMER


def resolve_boot_mode() -> AppMode:
    """Boot mode from environment. Default CUSTOMER. Never auto-admin from UI."""
    return _normalize_mode(os.environ.get(ENV_APP_MODE, AppMode.CUSTOMER.value))


def get_app_mode(session_state: Any) -> AppMode:
    try:
        if STATE_APP_MODE in session_state:
            return _normalize_mode(session_state[STATE_APP_MODE])
    except Exception:  # noqa: BLE001
        pass
    return resolve_boot_mode()


def set_app_mode(session_state: Any, mode: AppMode | str) -> AppMode:
    resolved = _normalize_mode(mode)
    # Admin cannot be enabled from customer UI — only boot env or explicit API.
    if resolved is AppMode.ADMIN and resolve_boot_mode() is not AppMode.ADMIN:
        resolved = AppMode.CUSTOMER
    session_state[STATE_APP_MODE] = resolved.value
    return resolved


def is_customer_mode(session_state: Any) -> bool:
    return get_app_mode(session_state) is AppMode.CUSTOMER


def is_demo_mode(session_state: Any) -> bool:
    return get_app_mode(session_state) is AppMode.DEMO


def is_admin_mode(session_state: Any) -> bool:
    """True only when boot env requested admin (or session already admin)."""
    if resolve_boot_mode() is AppMode.ADMIN:
        return True
    return get_app_mode(session_state) is AppMode.ADMIN


def ensure_app_mode(session_state: Any) -> AppMode:
    mode = get_app_mode(session_state)
    try:
        if STATE_APP_MODE not in session_state:
            session_state[STATE_APP_MODE] = mode.value
    except Exception:  # noqa: BLE001
        pass
    return mode
