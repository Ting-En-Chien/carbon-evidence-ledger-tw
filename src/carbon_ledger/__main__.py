"""Command-line entry point for the carbon_ledger package.

Run with:
    python -m carbon_ledger --version
"""

from __future__ import annotations

import argparse
import sys

from carbon_ledger import __version__


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="carbon_ledger",
        description=(
            "Carbon Evidence Ledger for Taiwanese Exporters "
            "(Phase 0 scaffold only)."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="Print the package version and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the requested command."""
    parser = build_parser()
    parser.parse_args(argv)
    # No subcommands yet in Phase 0; show help when no flags are given.
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
