"""Tests for provenance helpers (SHA-256, safe paths, JSON access)."""

from __future__ import annotations

from pathlib import Path

import pytest

from carbon_ledger.provenance import (
    compute_sha256,
    extract_top_level_json_value,
    load_json_document,
    resolve_source_file,
)


def test_sha256_is_lowercase_64_hex(tmp_path: Path) -> None:
    path = tmp_path / "sample.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    digest = compute_sha256(path)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(character in "0123456789abcdef" for character in digest)


def test_same_file_content_same_hash(tmp_path: Path) -> None:
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    payload = '{"value": 1}\n'
    first.write_text(payload, encoding="utf-8")
    second.write_text(payload, encoding="utf-8")
    assert compute_sha256(first) == compute_sha256(second)


def test_changing_one_byte_changes_hash(tmp_path: Path) -> None:
    path = tmp_path / "mutable.json"
    path.write_bytes(b'{"value": 1}')
    original = compute_sha256(path)
    path.write_bytes(b'{"value": 2}')
    assert compute_sha256(path) != original


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        compute_sha256(missing)


def test_safe_source_path_resolves_correctly(tmp_path: Path) -> None:
    documents = tmp_path / "synthetic_documents"
    documents.mkdir()
    target = documents / "electricity_bill_2024_01.json"
    target.write_text("{}", encoding="utf-8")
    resolved = resolve_source_file(documents, "electricity_bill_2024_01.json")
    assert resolved == target.resolve()


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    documents = tmp_path / "synthetic_documents"
    documents.mkdir()
    outside = tmp_path / "secret.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="traversal|Unsafe|escapes"):
        resolve_source_file(documents, "../secret.json")


def test_valid_json_loads_correctly(tmp_path: Path) -> None:
    path = tmp_path / "doc.json"
    path.write_text('{"source_document_id": "doc_1", "value": 3}', encoding="utf-8")
    payload = load_json_document(path)
    assert payload["source_document_id"] == "doc_1"
    assert payload["value"] == 3


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_json_document(path)


def test_valid_top_level_locator_extracts_value() -> None:
    document = {"electricity_usage_kwh": 50000.0, "other": 1}
    value = extract_top_level_json_value(
        document, "json_path:$.electricity_usage_kwh"
    )
    assert value == 50000.0


def test_missing_source_field_is_rejected() -> None:
    document = {"electricity_usage_kwh": 50000.0}
    with pytest.raises(ValueError, match="not found"):
        extract_top_level_json_value(document, "json_path:$.missing_field")


def test_unsupported_or_nested_locator_is_rejected() -> None:
    document = {"a": {"b": 1}}
    with pytest.raises(ValueError, match="Unsupported|nested"):
        extract_top_level_json_value(document, "json_path:$.a.b")
    with pytest.raises(ValueError, match="Unsupported"):
        extract_top_level_json_value(document, "$.electricity_usage_kwh")
