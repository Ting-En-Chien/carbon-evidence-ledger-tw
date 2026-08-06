"""Evidence-file provenance helpers: hashing, safe paths, and JSON access.

These functions support Phase 3 ingestion. They do not calculate emissions or
apply framework mappings.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

LOCATOR_PREFIX = "json_path:$."


def compute_sha256(file_path: Path) -> str:
    """Return the lowercase SHA-256 hex digest of a file's bytes.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File not found for SHA-256 hashing: {path}")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def resolve_source_file(documents_directory: Path, file_name: str) -> Path:
    """Resolve a source file path safely under documents_directory.

    Rejects empty names and path-traversal attempts such as ``../secret.json``.

    Raises:
        ValueError: If the file name is empty or resolves outside the directory.
    """
    if file_name is None or not str(file_name).strip():
        raise ValueError("Source file_name must be a non-empty string.")

    relative_name = str(file_name).strip()
    relative_path = Path(relative_name)

    if relative_path.is_absolute():
        raise ValueError(
            f"Absolute source paths are not allowed: {relative_name!r}"
        )

    if ".." in relative_path.parts:
        raise ValueError(
            f"Unsafe source path rejected (path traversal): {relative_name!r}"
        )

    base_directory = Path(documents_directory).resolve()
    resolved = (base_directory / relative_path).resolve()

    try:
        resolved.relative_to(base_directory)
    except ValueError as exc:
        raise ValueError(
            f"Unsafe source path rejected (escapes documents directory): "
            f"{relative_name!r}"
        ) from exc

    return resolved


def load_json_document(file_path: Path) -> dict[str, Any]:
    """Load a UTF-8 JSON object from disk.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not valid JSON or is not a JSON object.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"JSON document not found: {path}")

    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"JSON document must be an object/dictionary: {path}"
        )
    return payload


def extract_top_level_json_value(
    document: dict[str, Any],
    source_locator: str,
) -> Any:
    """Extract one top-level JSON field from a simple locator string.

    Supported form only::

        json_path:$.field_name

    Nested paths such as ``json_path:$.a.b`` are rejected.

    Raises:
        ValueError: If the locator syntax is unsupported or the field is missing.
    """
    if source_locator is None or not str(source_locator).strip():
        raise ValueError("source_locator must be a non-empty string.")

    locator = str(source_locator).strip()
    if not locator.startswith(LOCATOR_PREFIX):
        raise ValueError(
            "Unsupported source_locator. Expected form "
            f"'{LOCATOR_PREFIX}field_name', got: {locator!r}"
        )

    field_name = locator[len(LOCATOR_PREFIX) :]
    if not field_name:
        raise ValueError(f"Unsupported source_locator (empty field): {locator!r}")

    # Reject nested / complex JSONPath-like syntax.
    forbidden_markers = (".", "[", "]", "*", "(", ")", " ", "/")
    if any(marker in field_name for marker in forbidden_markers):
        raise ValueError(
            "Unsupported or nested source_locator syntax: "
            f"{locator!r}. Only top-level fields are allowed."
        )

    if field_name not in document:
        raise ValueError(
            f"Source field not found in JSON document: {field_name!r}"
        )

    return document[field_name]
