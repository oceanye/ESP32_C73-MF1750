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
# Raw Windows-checkout fingerprint at the frozen 3033da0 baseline. The text
# matcher below also accepts its content-identical LF checkout form.
FROZEN_MANIFEST = (
    5076,
    "2867521c6f3874a6e1cb9a57b764509c68b0e441cec735cfe406ef2698ebb69e",
)
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
    ".json",
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
    frozen_manifest = manifest_path.name == MANIFEST_NAME
    if frozen_manifest:
        expected_bytes, expected_sha256 = FROZEN_MANIFEST
        if not manifest_path.is_file():
            return CheckResult(
                "manufacturing_manifest",
                False,
                0,
                [f"missing frozen manifest: {manifest_path}"],
            )
        if not _matches_fingerprint(manifest_path, expected_bytes, expected_sha256):
            errors.append(
                "frozen manufacturing manifest fingerprint changed: "
                f"bytes={manifest_path.stat().st_size}, sha256={_sha256(manifest_path)}"
            )
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
    if frozen_manifest:
        actual_files = {
            path.relative_to(production_dir).as_posix()
            for path in production_dir.rglob("*")
            if path.is_file()
        }
        expected_files = set(seen) | {MANIFEST_NAME}
        for relative in sorted(actual_files - expected_files):
            errors.append(f"unlisted file in frozen production directory: {relative}")
        for relative in sorted(expected_files - actual_files):
            errors.append(f"listed file absent from frozen production directory: {relative}")
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
        "epdIsSupportedColorCode",
        "epdValidateFrameColors",
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
    if "uint32_t operationId = 0;" not in content:
        errors.append("operationId must be a non-zero-on-use u32 report field")
    if "uint64_t operationId" in content:
        errors.append("operationId must not exceed the host u32 contract")
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
        "physical color validation": 'frameUploadError = "unsupported_color_code"',
        "frame route": 'server.on("/api/frame", HTTP_POST',
        "queued response": "server.send(202, \"application/json\"",
        "diagnostic report wrapper": "epdDiagnosticReportWithJobJson()",
        "diagnostic firmware correlation": '\\"firmware_build_tag\\":\\"',
        "diagnostic job id correlation": '\\"job_id\\":',
        "diagnostic job action correlation": '\\"job_action\\":\\"',
        "diagnostic job state correlation": '\\"job_state\\":\\"',
        "diagnostic job result correlation": '\\"job_result\\":',
        "diagnostic operation correlation": '\\"job_operation_id\\":',
        "operation id pre-capture": (
            "operationIdBefore = epdGetLastOperationReport().operationId;"
        ),
        "fresh completed report gate": "report.valid && !report.running",
        "fresh operation id gate": "report.operationId > operationIdBefore",
        "immutable driver report capture": (
            "completedDriverReport = epdDiagnosticReportJson();"
        ),
        "atomic completed report publish": (
            "epdPublishedReportJson = completedJobSnapshot;"
        ),
        "snapshot-only diagnostic GET": "return epdPublishedReportJson;",
        "preflight refresh SPI": '"\\nRefresh SPI Hz: "',
        "preflight CS1 mapping": '"\\nCS1 Mapping: "',
        "preflight CS2 mapping": '"\\nCS2 Mapping: "',
        "non-refreshing ingress declaration": 'ingressResult += ",\\"epd_action\\":\\"none\\"}"',
    }
    for label, marker in required_markers.items():
        if marker not in content:
            errors.append(f"missing {label} contract marker")
    forbidden_markers = ("strlen(raw.buf)", "String(raw.buf)", "String((char *)raw.buf)")
    for marker in forbidden_markers:
        if marker in content:
            errors.append(f"binary body incorrectly treated as C string: {marker}")
    report_getter = re.search(
        r"static String epdDiagnosticReportWithJobJson\(\)\s*\{(?P<body>.*?)\n\}",
        content,
        flags=re.DOTALL,
    )
    if report_getter is None:
        errors.append("missing diagnostic report snapshot getter")
    elif "epdDiagnosticReportJson()" in report_getter.group("body"):
        errors.append("diagnostic GET must not read mutable live driver report")
    return CheckResult("binary_upload_contract", not errors, len(required_markers), errors)


def check_driver_frame_contract(driver_cpp: Path) -> CheckResult:
    errors: List[str] = []
    try:
        content = driver_cpp.read_text(encoding="utf-8")
    except OSError as error:
        return CheckResult("driver_frame_contract", False, 0, [str(error)])
    display_start = content.find("bool epdDisplayFrameAtFrequency")
    if display_start < 0:
        return CheckResult(
            "driver_frame_contract",
            False,
            0,
            ["missing epdDisplayFrameAtFrequency implementation"],
        )
    display_body = content[display_start:]
    required_markers = {
        "packed color validator": "epdValidateFrameColors(frame, len, &invalidPixel, &invalidCode)",
        "invalid pixel diagnostic": "Invalid EPD frame color at pixel",
        "mapping after validation": "diagnosticReport.mappingApplied = true",
        "cascade preparation": "epdPrepareCascade(spiHz)",
        "second controller stream": (
            "diagnosticReport.cs2DtmFnv1a = epdStreamPackedFrameController(frame, true)"
        ),
    }
    positions: Dict[str, int] = {}
    for label, marker in required_markers.items():
        position = display_body.find(marker)
        positions[label] = position
        if position < 0:
            errors.append(f"missing {label} contract marker")
    validator = positions["packed color validator"]
    mapping = positions["mapping after validation"]
    cascade = positions["cascade preparation"]
    second_stream = positions["second controller stream"]
    if validator >= 0 and mapping >= 0 and validator > mapping:
        errors.append("mapping must not be marked applied before frame colors validate")
    if validator >= 0 and cascade >= 0 and validator > cascade:
        errors.append("frame colors must validate before cascade initialization or DTM")
    if mapping >= 0 and second_stream >= 0 and mapping < second_stream:
        errors.append("mapping must be marked applied only after both controller streams")
    evidence_markers = {
        "wait evidence recorder": "recordWaitEvidence(stage, elapsed, sawBusy)",
        "two-stage BUSY helper": "bool epdWaitBusyThenIdle(",
        "PON strict BUSY wait": 'epdWaitBusyThenIdle("PON")',
        "DRF strict BUSY wait": 'epdWaitBusyThenIdle("DRF")',
        "POF strict BUSY wait": 'epdWaitBusyThenIdle("POF")',
        "post-PSR informational idle wait": (
            'epdWaitIdle("post-display PSR")'
        ),
        "BUSY assertion grace": "EPD_BUSY_ASSERT_GRACE_MS",
        "BUSY assertion failure": "diagnosticReport.busyAssertionMissing = true",
        "fail-safe POF helper": "void epdRequestFailSafePowerOff(",
        "PON fail-safe POF": (
            'epdRequestFailSafePowerOff("POF cleanup after PON failure")'
        ),
        "DRF fail-safe POF": (
            'epdRequestFailSafePowerOff("POF cleanup after DRF failure")'
        ),
        "safe panel shutdown": "epdHoldPanelPinsLow()",
        "operation begin helper": "uint32_t epdBeginOperation(uint32_t spiHz)",
        "operation finish helper": (
            "bool epdFinishOperation(uint32_t startedAtMs, bool sequenceOk)"
        ),
        "operation id report": '\\"operation_id\\":',
        "BUSY missing report": '\\"busy_assertion_missing\\":',
        "PON BUSY evidence": '\\"pon_busy_seen\\":',
        "DRF BUSY evidence": '\\"drf_busy_seen\\":',
        "POF BUSY evidence": '\\"pof_busy_seen\\":',
        "post-PSR BUSY evidence": '\\"post_psr_busy_seen\\":',
        "DRF duration evidence": '\\"drf_ms\\":',
    }
    for label, marker in evidence_markers.items():
        if marker not in content:
            errors.append(f"missing {label} contract marker")
    if 'epdWaitBusyThenIdle("post-display PSR")' in content:
        errors.append("post-display PSR must not require a BUSY assertion after POF")
    solid_match = re.search(
        r"bool epdDiagnosticSolid\([^)]*\)\s*\{(?P<body>.*?)\n\}",
        content,
        flags=re.DOTALL,
    )
    if solid_match is None:
        errors.append("missing epdDiagnosticSolid implementation")
    else:
        solid_body = solid_match.group("body")
        if "epdBeginOperation(spiHz)" not in solid_body:
            errors.append("epdDiagnosticSolid must begin a fresh operation report")
        if "epdFinishOperation(diagnosticStarted" not in solid_body:
            errors.append("epdDiagnosticSolid must complete its operation report")
    if (
        'epdWaitBusyThenIdle("reset")' in content
        or 'epdWaitBusyThenIdle(secondController ? "REV CS2 reset"' in content
    ):
        errors.append("reset/REV waits must not require formal BUSY assertion")
    return CheckResult(
        "driver_frame_contract",
        not errors,
        len(required_markers) + len(evidence_markers),
        errors,
    )


def run_checks(repo_root: Path) -> Dict[str, Any]:
    repo_root = repo_root.resolve()
    production_dir = repo_root / PRODUCTION_RELATIVE
    results = [
        check_manifest(production_dir),
        check_frozen_order_files(production_dir),
        check_release_build_flags(repo_root / "platformio.ini"),
        check_public_driver_header(repo_root / "src/epd_driver.h"),
        check_upload_contract(repo_root / "src/main.cpp"),
        check_driver_frame_contract(repo_root / "src/epd_driver.cpp"),
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
