"""Shared deterministic helpers for static-photo evidence."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
CANONICAL_SCOPE = (
    "entire object excluding integrity; UTF-8 JSON, sorted keys, no whitespace, "
    "ensure_ascii=false, allow_nan=false"
)


class StaticPhotoContractError(ValueError):
    """Raised when an offline static-photo contract differs."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(payload: bytes | bytearray | memoryview) -> str:
    return hashlib.sha256(bytes(payload)).hexdigest()


def require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise StaticPhotoContractError(f"{label} must be 64 lowercase hex digits")
    return value


def require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StaticPhotoContractError(f"{label} must be a non-empty string")
    result = value.strip()
    if any(ord(character) < 0x20 for character in result):
        raise StaticPhotoContractError(f"{label} must not contain controls")
    return result


def finite_triple(values: object, label: str) -> tuple[float, float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise StaticPhotoContractError(f"{label} must contain exactly three numbers")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ):
        raise StaticPhotoContractError(f"{label} components must be numeric")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise StaticPhotoContractError(f"{label} components must be finite")
    return result  # type: ignore[return-value]


def require_exact_keys(
    mapping: Mapping[str, Any], expected: Sequence[str] | set[str], label: str
) -> None:
    expected_set = set(expected)
    actual = set(mapping)
    if actual != expected_set:
        missing = sorted(expected_set - actual)
        extra = sorted(actual - expected_set)
        raise StaticPhotoContractError(
            f"{label} keys differ; missing={missing}, extra={extra}"
        )


def attach_integrity(mapping: Mapping[str, Any]) -> dict[str, Any]:
    if "integrity" in mapping:
        raise StaticPhotoContractError("unsigned mapping must not contain integrity")
    result = dict(mapping)
    result["integrity"] = {
        "canonical_sha256": canonical_sha256(mapping),
        "scope": CANONICAL_SCOPE,
    }
    return result


def verify_integrity(mapping: Mapping[str, Any], label: str) -> dict[str, Any]:
    raw_integrity = mapping.get("integrity")
    if not isinstance(raw_integrity, Mapping):
        raise StaticPhotoContractError(f"{label} requires integrity")
    require_exact_keys(
        raw_integrity, {"canonical_sha256", "scope"}, f"{label} integrity"
    )
    expected = require_sha256(
        raw_integrity.get("canonical_sha256"), f"{label} integrity canonical_sha256"
    )
    if raw_integrity.get("scope") != CANONICAL_SCOPE:
        raise StaticPhotoContractError(f"{label} integrity scope differs")
    unsigned = dict(mapping)
    unsigned.pop("integrity")
    if canonical_sha256(unsigned) != expected:
        raise StaticPhotoContractError(f"{label} canonical SHA-256 differs")
    return unsigned


def prepare_empty_output_dir(path: str | Path) -> Path:
    output = Path(path)
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise StaticPhotoContractError("output directory boundary differs")
        if any(output.iterdir()):
            raise StaticPhotoContractError("output directory must be empty")
    else:
        output.mkdir(parents=True)
    return output
