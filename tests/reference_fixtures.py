"""Immutable reference-registry fixtures for hermetic tests.

Live ``data/reference/`` may contain developer-activated Phase 10A rows
(e.g. an active 2025 enterprise electricity factor). Tests that need a
deterministic pre-activation starting state must seed from
``tests/fixtures/reference_baseline/`` instead of copying the live tree.
"""

from __future__ import annotations

import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_REFERENCE_DIR = REPO_ROOT / "tests" / "fixtures" / "reference_baseline"
LIVE_REFERENCE_DIR = REPO_ROOT / "data" / "reference"

REQUIRED_BASELINE_ELECTRICITY_FACTOR_IDS = (
    "ef_tw_grid_electricity_2024",
)


def copy_baseline_reference_tree(destination: Path) -> Path:
    """Copy the immutable baseline reference directory into ``destination``."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(BASELINE_REFERENCE_DIR, destination)
    return destination
