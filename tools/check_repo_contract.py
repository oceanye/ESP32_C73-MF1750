#!/usr/bin/env python3
"""Check immutable manufacturing inputs and firmware repository contracts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence


PRODUCTION_RELATIVE = Path("hardware/mf1750_production_v1/production")
MANIFEST_NAME = "manufacturing_manifest.json"
FROZEN_FILES = {
    "Gerber_mf1750_revA1_Q1FIX.zip": (
        84183,
        "64931dec6c747119b3f4dffbc625d600d28be59d1be35d3213807106c5153f18",
    ),
    "BOM_mf1750_revA1_Q1FIX.csv": (
        2588,
        "06cfe61df14055d9ef3ea94f333c7e776e11984b8d0c519957dcd7439fb3bdf8",
    ),
    "CPL_mf1750_revA1_Q1FIX.csv": (
        1625,
        "ef9c46262f8689156fefc4724699522d60560ccb20ec6adfa33fc75b080f91ed",
    ),
}
TEXT_SUFFIXES = {
    ".csv",
    ".drl",
    ".gbl",
    ".gbo",
    ".gbrjob",
    ".gbs",
    ".gm1",
    ".gtl",
    ".gto",
    ".gts",
    ".md",
    ".rpt",
    ".txt",
}
MANIFEST_BASELINE_EXCEPTIONS = {
    "PCB下单与首板检查.md": {
        "manifest_bytes": 2101,
        "manifest_sha256": "9bf8f5c01af7541ce494707c6e98b0da147b66b43bd2d2f7fca1a9a75a3e33a0",
        "baseline_bytes": 2069,
        "baseline_sha256": "86315f41ab9dd34f962cf108c1568b69f3db87a14d1c1e06497d251522d3e67f",
        "reason": "manifest predates the file in baseline commit 3033da0",
    }
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    checked_items: int
    errors: List[str]
    warnings: List[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_fingerprints(path: Path) -> set[tuple[int, str]]:
    """Return raw, LF, and CRLF fingerprints for a tracked text file."""

    data = path.read_bytes()
    normalized_lf = data.replace(b"\r\n", b"\n")
    normalized_crlf = normalized_lf.replace(b"\n", b"\r\n")
    return {
        (len(candidate), hashlib.sha256(candidate).hexdigest())
        for candidate in (data, normalized_lf, normalized_crlf)
    }


def _matches_fingerprint(path: Path, expected_bytes: int, expected_sha256: str) -> bool:
    actual_bytes = path.stat().st_size
    actual_sha256 = _sha256(path)
    if actual_bytes == expected_bytes and actual_sha256.lower() == expected_sha256.lower():
        return True
    # Git may materialize tracked text as LF on Linux or CRLF on Windows. Accept
    # only those two line-ending forms; all other byte changes still fail.
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    expected = (expected_bytes, expected_sha256.lower())
    return expected in _text_fingerprints(path)


def _contained_file(base: Path, relative: str) -> Optional[Path]:
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate


def check_manifest(production_dir: Path, manifest_path: Optional[Path] = None) -> CheckResult:
    manifest_path = manifest_path or production_dir / MANIFEST_NAME
    errors: List[str] = []
    warnings: List[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return CheckResult("manufacturing_manifest", False, 0, [str(error)])
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return CheckResult("manufacturing_manifest", False, 0, ["files must be a list"])
    seen = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index} must be an object")
            continue
        relative = entry.get("file")
        expected_bytes = entry.get("bytes")
        expected_sha256 = entry.get("sha256")
        if not isinstance(relative, str) or not relative:
            errors.append(f"entry {index} has invalid file")
            continue
        if relative in seen:
            errors.append(f"duplicate manifest path: {relative}")
            continue
        seen.add(relative)
        path = _contained_file(production_dir, relative)
        if path is None:
            errors.append(f"path escapes production directory: {relative}")
            continue
        if not path.is_file():
            errors.append(f"missing file: {relative}")
            continue
        if not isinstance(expected_bytes, int) or not isinstance(expected_sha256, str):
            errors.append(f"invalid fingerprint in manifest: {relative}")
            continue
        check_bytes = expected_bytes
        check_sha256 = expected_sha256
        exception = MANIFEST_BASELINE_EXCEPTIONS.get(relative)
        if exception is not None:
            if (
                expected_bytes != exception["manifest_bytes"]
                or expected_sha256.lower() != exception["manifest_sha256"]
            ):
                errors.append(f"known manifest exception metadata changed: {relative}")
                continue
            check_bytes = exception["baseline_bytes"]
            check_sha256 = exception["baseline_sha256"]
            warnings.append(f"{relative}: {exception['reason']}")
        if not _matches_fingerprint(path, check_bytes, check_sha256):
            actual_bytes = path.stat().st_size
            actual_sha256 = _sha256(path)
            errors.append(
                f"fingerprint mismatch {relative}: bytes={actual_bytes}, sha256={actual_sha256}"
            )
    if len(entries) != 28:
        errors.append(f"manifest must retain 28 entries; got {len(entries)}")
    return CheckResult("manufacturing_manifest", not errors, len(entries), errors, warnings)


def check_frozen_order_files(production_dir: Path) -> CheckResult:
    errors: List[str] = []
    for name, (expected_bytes, expected_sha256) in FROZEN_FILES.items():
        path = production_dir / name
        if not path.is_file():
            errors.append(f"missing frozen order file: {name}")
            continue
        if not _matches_fingerprint(path, expected_bytes, expected_sha256):
            actual_bytes = path.stat().st_size
            actual_sha256 = _sha256(path)
            errors.append(
                f"fingerprint mismatch {name}: bytes={actual_bytes}, sha256={actual_sha256}"
            )
    return CheckResult("frozen_order_files", not errors, len(FROZEN_FILES), errors)


def check_release_build_flags(platformio_ini: Path) -> CheckResult:
    errors: List[str] = []
    try:
        content = platformio_ini.read_text(encoding="utf-8")
    except OSError as error:
        return CheckResult("release_build_flags", False, 0, [str(error)])
    definitions = re.findall(r"(?m)^\s*-D\s*EPD_ENABLE_TEST_PATTERN\s*=\s*([^\s;]+)", content)
    if definitions != ["0"]:
        errors.append(f"EPD_ENABLE_TEST_PATTERN must be defined exactly once as 0; got {definitions}")
    return CheckResult("release_build_flags", not errors, len(definitions), errors)


def check_public_driver_header(header_path: Path) -> CheckResult:
    errors: List[str] = []
    try:
        content = header_path.read_text(encoding="utf-8")
    except OSError as error:
        return CheckResult("public_driver_header", False, 0, [str(error)])
    names = sorted(set(re.findall(r"\b(epd[A-Za-z0-9_]+)\s*\(", content)))
    required = {
        "epdBegin",
        "epdReadBusy",
        "epdGetLastOperationReport",
        "epdDisplayFrame",
        "epdDisplayFrameAtFrequency",
        "epdClearWhite",
        "epdClearBlack",
    }
    missing = sorted(required - set(names))
    if missing:
        errors.append(f"missing public APIs: {missing}")
    forbidden = [
        name
        for name in names
        if name.startswith("epdDiagnostic")
        or "512" in name
        or "800" in name
        or "Legacy" in name
        or "Bars" in name
    ]
    if forbidden:
        errors.append(f"legacy/diagnostic APIs exposed in epd_driver.h: {forbidden}")
    if '#include "epd_diagnostics.h"' in content:
        errors.append("epd_driver.h must not include epd_diagnostics.h")
    return CheckResult("public_driver_header", not errors, len(names), errors)


def check_upload_contract(main_cpp: Path) -> CheckResult:
    errors: List[str] = []
    try:
        content = main_cpp.read_text(encoding="utf-8")
    except OSError as error:
        return CheckResult("binary_upload_contract", False, 0, [str(error)])
    required_markers = {
        "content type": 'contentType.startsWith("application/octet-stream")',
        "declared length": "server.clientContentLength() != static_cast<int>(EPD_FRAME_BYTES)",
        "write upper bound": "offset + raw.currentSize > EPD_FRAME_BYTES",
        "exact final length": "raw.totalSize == EPD_FRAME_BYTES",
        "binary copy": "memcpy(frameBuffer + offset, raw.buf, raw.currentSize)",
        "frame route": 'server.on("/api/frame", HTTP_POST',
        "queued response": "server.send(202, \"application/json\"",
    }
    for label, marker in required_markers.items():
        if marker not in content:
            errors.append(f"missing {label} contract marker")
    forbidden_markers = ("strlen(raw.buf)", "String(raw.buf)", "String((char *)raw.buf)")
    for marker in forbidden_markers:
        if marker in content:
            errors.append(f"binary body incorrectly treated as C string: {marker}")
    return CheckResult("binary_upload_contract", not errors, len(required_markers), errors)


def run_checks(repo_root: Path) -> Dict[str, Any]:
    repo_root = repo_root.resolve()
    production_dir = repo_root / PRODUCTION_RELATIVE
    results = [
        check_manifest(production_dir),
        check_frozen_order_files(production_dir),
        check_release_build_flags(repo_root / "platformio.ini"),
        check_public_driver_header(repo_root / "src/epd_driver.h"),
        check_upload_contract(repo_root / "src/main.cpp"),
    ]
    return {
        "schema_version": 1,
        "kind": "mf1750-repository-contract-report",
        "passed": all(result.passed for result in results),
        "hardware_tested": False,
        "checks": [asdict(result) for result in results],
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: inferred from this script)",
    )
    parser.add_argument("--output", type=Path, help="also write the JSON report to this path")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    report = run_checks(args.repo_root)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    sys.stdout.write(rendered)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
