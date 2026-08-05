"""Smoke tests: confirm the package installs and reports its version."""

import carbon_ledger


def test_package_importable() -> None:
    """The carbon_ledger package can be imported."""
    assert carbon_ledger is not None


def test_version() -> None:
    """The package version matches the Phase 0 release."""
    assert carbon_ledger.__version__ == "0.1.0"
