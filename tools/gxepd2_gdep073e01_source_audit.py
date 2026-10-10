#!/usr/bin/env python3
"""Audit a pinned GxEPD2 GDEP073E01 source snapshot.

The tool is deliberately bounded to public, immutable GitHub commit URLs.  It
cross-checks an adjacent 800x480 single-controller panel implementation against
the already recovered Good Display ESP32 firmware trace.  It never constructs
a waveform payload and has no serial, flashing, or device-network code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence
from urllib.request import Request, urlopen


KIND = "gxepd2-gdep073e01-pinned-source-audit"
SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CROSS_IMAGE_REPORT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "good_display_esp32e6_cross_image_panel_audit_20260812.json"
)
DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "gxepd2_gdep073e01_source_audit_20260812.json"
)
EXPECTED_CROSS_IMAGE_REPORT_SHA256 = (
    "3f82c21dca0d59f4c35bd8a390dbea26497dd29b3fb6e502a2ba2c95f1bd7f4b"
)
EXPECTED_CROSS_IMAGE_KIND = "good-display-esp32e6-e01-cross-image-panel-audit"

CURRENT_TAG = "1.6.9"
CURRENT_COMMIT = "de82887e77a78528ea386e68bba2cb0291d2c319"
PREVIOUS_TAG = "1.5.9"
PREVIOUS_COMMIT = "7cfc3671ef1802a067bb4c5e5ed4e2fb6e79abb6"
RAW_ROOT = "https://raw.githubusercontent.com/ZinggJM/GxEPD2"
SOURCE_RELATIVE = "src/epd7c/GxEPD2_730c_GDEP073E01.cpp"
HEADER_RELATIVE = "src/epd7c/GxEPD2_730c_GDEP073E01.h"
PROPERTIES_RELATIVE = "library.properties"

URLS = {
    "current_source": f"{RAW_ROOT}/{CURRENT_COMMIT}/{SOURCE_RELATIVE}",
    "current_header": f"{RAW_ROOT}/{CURRENT_COMMIT}/{HEADER_RELATIVE}",
    "current_properties": f"{RAW_ROOT}/{CURRENT_COMMIT}/{PROPERTIES_RELATIVE}",
    "previous_source": f"{RAW_ROOT}/{PREVIOUS_COMMIT}/{SOURCE_RELATIVE}",
}
EXPECTED_IDENTITIES: Mapping[str, tuple[int, str]] = {
    "current_source": (
        25_552,
        "7c864fd955a877f1841396294619c68a9ab22264654c0f03d76e23dedb23c07e",
    ),
    "current_header": (
        5_860,
        "bb98d5cc413a99878e0898ecaa468013fae33c70b327d53d204ab5d0fc8d39e6",
    ),
    "current_properties": (
        388,
        "6b31aec599921175a16e0e0c6ee6cb806f1539215c490a0d9f7de883806ed119",
    ),
    "previous_source": (
        24_695,
        "2f639bdcea42c9256ad0e970396de5dbf1453a00b6289537ca0db4ce604cd3fd",
    ),
}

EXPECTED_INIT_TRACE: tuple[tuple[int, tuple[int, ...]], ...] = (
    (0xAA, (0x49, 0x55, 0x20, 0x08, 0x09, 0x18)),
    (0x01, (0x3F,)),
    (0x00, (0x5F, 0x69)),
    (0x03, (0x00, 0x54, 0x00, 0x44)),
    (0x05, (0x40, 0x1F, 0x1F, 0x2C)),
    (0x06, (0x6F, 0x1F, 0x17, 0x49)),
    (0x08, (0x6F, 0x1F, 0x1F, 0x22)),
    (0x30, (0x08,)),
    (0x50, (0x3F,)),
    (0x60, (0x02, 0x00)),
    (0x61, (0x03, 0x20, 0x01, 0xE0)),
    (0x84, (0x01,)),
    (0xE3, (0x2F,)),
    (0x04, ()),
)
EXPECTED_CURRENT_NATIVE_BY_NAME = {
    "black": 0,
    "white": 1,
    "yellow": 2,
    "red": 3,
    "orange": 4,
    "blue": 5,
    "green": 6,
}
EXPECTED_PREVIOUS_NATIVE_BY_NAME = {
    "black": 0,
    "white": 1,
    "yellow": 5,
    "orange": 6,
    "red": 4,
    "blue": 3,
    "green": 2,
}


class AuditError(RuntimeError):
    """Raised when a pinned source or required semantic invariant differs."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fetch(url: str, timeout_seconds: float = 30.0) -> bytes:
    request = Request(url, headers={"User-Agent": "ESP32-C73-static-audit/1"})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.read()


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", source)


def _extract_function(source: str, name: str) -> str:
    marker = f"::{name}("
    return _extract_function_after(source, marker, name)


def _extract_function_after(source: str, marker: str, label: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise AuditError(f"function not found: {label}")
    opening = source.find("{", start)
    if opening < 0:
        raise AuditError(f"function body not found: {label}")
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1 : index]
    raise AuditError(f"unterminated function body: {label}")


def _defines(source: str) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^\s*#define\s+([A-Za-z_]\w*)\s+(0x[0-9A-Fa-f]+)\b",
            source,
            flags=re.MULTILINE,
        )
    }


def _resolve_byte(token: str, defines: Mapping[str, int]) -> int:
    token = token.strip()
    if token in defines:
        value = defines[token]
    elif re.fullmatch(r"0x[0-9A-Fa-f]+|\d+", token):
        value = int(token, 0)
    else:
        raise AuditError(f"non-literal byte token: {token}")
    if not 0 <= value <= 0xFF:
        raise AuditError(f"byte out of range: {token}")
    return value


def _trace_from_init(source: str) -> list[dict[str, str]]:
    clean = _strip_comments(source)
    body = _extract_function(clean, "_InitDisplay")
    defines = _defines(clean)
    events: list[tuple[int, list[int]]] = []
    for kind, token in re.findall(r"_write(Command|Data)\(([^()]*)\)\s*;", body):
        value = _resolve_byte(token, defines)
        if kind == "Command":
            events.append((value, []))
        else:
            if not events:
                raise AuditError("data precedes command in _InitDisplay")
            events[-1][1].append(value)
    if re.search(r"\b_PowerOn\s*\(\s*\)\s*;", body):
        power_on = _extract_function(clean, "_PowerOn")
        command_match = re.search(r"_writeCommand\(([^()]*)\)\s*;", power_on)
        if not command_match:
            raise AuditError("_PowerOn has no command")
        events.append((_resolve_byte(command_match.group(1), defines), []))
    return [
        {"command": f"0x{command:02x}", "data_hex": bytes(data).hex()}
        for command, data in events
    ]


def _mode0_native_mapping(source: str) -> dict[str, int]:
    body = _extract_function(source, "_colorOfDemoBitmap")
    match = re.search(
        r"case\s+0\s*:\s*\{(?P<body>.*?)\}\s*case\s+1\s*:",
        body,
        flags=re.DOTALL,
    )
    if not match:
        raise AuditError("mode-0 bitmap mapping not found")
    mapping: dict[str, int] = {}
    pattern = re.compile(
        r"case\s+0x[0-9A-Fa-f]+\s*:\s*return\s*\(\s*(0x[0-9A-Fa-f]+)\s*\)"
        r"\s*;\s*//\s*([A-Za-z]+)",
    )
    for native, label in pattern.findall(match.group("body")):
        mapping[label.lower()] = int(native, 16)
    return mapping


def _convert_to_native_mapping(source: str) -> dict[str, dict[str, Any]]:
    body = _extract_function(source, "_convert_to_native")
    mapping: dict[str, dict[str, Any]] = {}
    pattern = re.compile(
        r"case\s+(0x[0-9A-Fa-f]+)\s*:\s*result\s*\|=\s*"
        r"(0x[0-9A-Fa-f]+)\s*<<\s*4\s*;\s*break\s*;\s*//\s*([A-Za-z]+)",
    )
    for input_code, native_code, label in pattern.findall(body):
        mapping[str(int(input_code, 16))] = {
            "input_semantic_comment": label.lower(),
            "native_code": int(native_code, 16),
        }
    return mapping


def _command_inventory(source: str) -> list[int]:
    clean = _strip_comments(source)
    defines = _defines(clean)
    values = []
    for token in re.findall(r"_writeCommand\(([^()]*)\)\s*;", clean):
        try:
            values.append(_resolve_byte(token, defines))
        except AuditError:
            continue
    return sorted(set(values))


def _partial_window_contract(source: str) -> dict[str, Any]:
    clean = _strip_comments(source)
    body = _extract_function(clean, "_setPartialRamArea")
    command = re.search(r"_writeCommand\(([^()]*)\)\s*;", body)
    data = [
        re.sub(r"\s+", "", item)
        for item in re.findall(r"_writeData\((.*?)\)\s*;", body)
    ]
    return {
        "command": _resolve_byte(command.group(1), _defines(clean))
        if command
        else None,
        "data_expression_count": len(data),
        "data_expressions": data,
        "xe_inclusive": bool(re.search(r"\bxe\s*=\s*x\s*\+\s*w\s*-\s*1\s*;", body)),
        "ye_one_more": bool(re.search(r"\bye\s*=\s*y\s*\+\s*h\s*;", body)),
    }


def _partial_refresh_contract(source: str) -> dict[str, Any]:
    clean = _strip_comments(source)
    body = _extract_function_after(
        clean,
        "::refresh(int16_t",
        "refresh(int16_t x, int16_t y, int16_t w, int16_t h)",
    )
    compact = re.sub(r"\s+", "", body)
    native_dtm_starts_immediately = bool(
        re.search(
            r"_setPartialRamArea\([^;]+;\s*_writeCommand\(0x10\);"
            r"\s*_startTransfer\(\);",
            clean,
        )
    )
    return {
        "powers_on_before_refresh": compact.startswith("_PowerOn();"),
        "selects_requested_window": (
            "if(usePartialUpdate)_setPartialRamArea(x,y,w,h);" in compact
        ),
        "border_floating_cdi_ff": bool(
            re.search(
                r"_writeCommand\(0x50\);\s*_writeData\(0xFF\);"
                r"\s*_writeCommand\(0x12\);",
                body,
            )
        ),
        "display_refresh_command_0x12": "_writeCommand(0x12);" in compact,
        "waits_with_full_refresh_timeout": (
            '_waitWhileBusy("_refresh",full_refresh_time);' in compact
        ),
        "native_dtm_starts_transfer_immediately": native_dtm_starts_immediately,
        "native_dtm_prefix_bytes": 0 if native_dtm_starts_immediately else None,
    }


def _identity(name: str, data: bytes, *, enforce_pins: bool) -> dict[str, Any]:
    actual = {"bytes": len(data), "sha256": _sha256(data), "url": URLS[name]}
    expected_bytes, expected_sha = EXPECTED_IDENTITIES[name]
    actual["matches_pin"] = (
        len(data) == expected_bytes and actual["sha256"] == expected_sha
    )
    if enforce_pins and not actual["matches_pin"]:
        raise AuditError(
            f"identity mismatch for {name}: {len(data)}/{actual['sha256']}"
        )
    return actual


def _header_facts(header: str) -> dict[str, Any]:
    def number(name: str) -> int:
        match = re.search(rf"\b{name}\s*=\s*(\d+)\s*;", header)
        if not match:
            raise AuditError(f"header field not found: {name}")
        return int(match.group(1))

    def boolean(name: str) -> bool:
        match = re.search(rf"\b{name}\s*=\s*(true|false)\s*;", header)
        if not match:
            raise AuditError(f"header field not found: {name}")
        return match.group(1) == "true"

    return {
        "panel": "GDEP073E01",
        "width": number("WIDTH"),
        "height": number("HEIGHT"),
        "controller_comment": "unknown" if "// Controller: unknown" in header else None,
        "has_color": boolean("hasColor"),
        "has_partial_update": boolean("hasPartialUpdate"),
        "use_partial_update": boolean("usePartialUpdate"),
        "has_fast_partial_update": boolean("hasFastPartialUpdate"),
        "full_refresh_time_ms": number("full_refresh_time"),
        "partial_refresh_time_ms": number("partial_refresh_time"),
        "constructor_has_one_cs_argument": bool(
            re.search(r"GxEPD2_730c_GDEP073E01\(int16_t\s+cs,", header)
        ),
    }


def _cross_image_facts(
    path: Path, source_trace: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    if not path.is_file():
        return {"available": False, "path": str(path), "exact_trace_match": None}
    raw = path.read_bytes()
    if _sha256(raw) != EXPECTED_CROSS_IMAGE_REPORT_SHA256:
        raise AuditError("cross-image report SHA-256 differs from the pinned input")
    report = json.loads(raw.decode("utf-8"))
    if (
        report.get("kind") != EXPECTED_CROSS_IMAGE_KIND
        or report.get("schema_version") != 1
    ):
        raise AuditError("cross-image report kind/schema differs from the pinned input")
    safety = report.get("safety", {})
    if not safety.get("offline_static_analysis_only") or any(
        safety.get(field)
        for field in (
            "device_network_accessed",
            "display_refreshed",
            "flash_written",
            "hardware_accessed",
            "serial_or_com_accessed",
        )
    ):
        raise AuditError(
            "cross-image report does not assert the pinned offline boundary"
        )
    traces = [image["typed_init_trace"] for image in report["images"].values()]
    exact = bool(traces) and all(trace == list(source_trace) for trace in traces)
    tag_mapping = report["cross_image_findings"]["unpacked_tag_to_panel_code"]
    typed_panel_codes = sorted(set(tag_mapping.values()))
    if typed_panel_codes != [0, 1, 2, 3, 5, 6]:
        raise AuditError("cross-image typed panel-code set differs from the pin")
    try:
        display_path = path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        display_path = str(path)
    return {
        "available": True,
        "path": display_path,
        "bytes": len(raw),
        "sha256": _sha256(raw),
        "kind": report["kind"],
        "schema_version": report["schema_version"],
        "image_count": len(traces),
        "all_binary_traces_equal": bool(traces)
        and all(trace == traces[0] for trace in traces[1:]),
        "exact_trace_match": exact,
        "typed_panel_codes": typed_panel_codes,
        "typed_code4_present": 4 in typed_panel_codes,
        "typed_code7_present": 7 in typed_panel_codes,
        "official_binary_code4_label_recovered": False,
    }


def build_report(
    blobs: Mapping[str, bytes],
    *,
    cross_image_report: Path = DEFAULT_CROSS_IMAGE_REPORT,
    enforce_pins: bool = True,
    network_accessed: bool = False,
) -> dict[str, Any]:
    missing = sorted(set(URLS) - set(blobs))
    if missing:
        raise AuditError(f"missing source blobs: {', '.join(missing)}")

    identities = {
        name: _identity(name, blobs[name], enforce_pins=enforce_pins) for name in URLS
    }
    current = blobs["current_source"].decode("utf-8")
    previous = blobs["previous_source"].decode("utf-8")
    header = blobs["current_header"].decode("utf-8")
    properties = blobs["current_properties"].decode("utf-8")

    trace = _trace_from_init(current)
    expected_trace = [
        {"command": f"0x{command:02x}", "data_hex": bytes(data).hex()}
        for command, data in EXPECTED_INIT_TRACE
    ]
    current_mapping = _mode0_native_mapping(current)
    previous_mapping = _mode0_native_mapping(previous)
    if enforce_pins and trace != expected_trace:
        raise AuditError("pinned init trace differs from expected trace")
    if enforce_pins and current_mapping != EXPECTED_CURRENT_NATIVE_BY_NAME:
        raise AuditError("current native color mapping differs from pin")
    if enforce_pins and previous_mapping != EXPECTED_PREVIOUS_NATIVE_BY_NAME:
        raise AuditError("previous native color mapping differs from pin")

    commands = _command_inventory(current)
    partial = _partial_window_contract(current)
    partial_refresh = _partial_refresh_contract(current)
    header_facts = _header_facts(header)
    version_match = re.search(r"^version=(.+)$", properties, flags=re.MULTILINE)
    version = version_match.group(1).strip() if version_match else None
    cross = _cross_image_facts(cross_image_report, trace)

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source_identity": {
            "repository": "https://github.com/ZinggJM/GxEPD2",
            "current_tag": CURRENT_TAG,
            "current_commit": CURRENT_COMMIT,
            "previous_tag": PREVIOUS_TAG,
            "previous_commit": PREVIOUS_COMMIT,
            "library_properties_version": version,
            "files": identities,
        },
        "panel_scope": {
            **header_facts,
            "classification": "adjacent_single_controller_800x480_module",
            "same_as_mf17506_dual_1024x600": False,
            "controller_identity_known_by_source": False,
        },
        "typed_init": {
            "trace": trace,
            "matches_expected": trace == expected_trace,
            "ends_in_power_on_helper_command_0x04": trace[-1]
            == {"command": "0x04", "data_hex": ""},
        },
        "official_binary_cross_reference": cross,
        "native_color_mapping": {
            "current_mode0_bitmap_comment_to_native_code": current_mapping,
            "previous_mode0_bitmap_comment_to_native_code": previous_mapping,
            "mapping_changed_between_tags": current_mapping != previous_mapping,
            "current_convert_to_native": _convert_to_native_mapping(current),
            "current_code4_source_label": next(
                (name for name, code in current_mapping.items() if code == 4), None
            ),
            "current_code7_convert_comment": _convert_to_native_mapping(current).get(
                "7"
            ),
            "evidence_level": "third_party_library_source_for_exact_adjacent_panel",
            "portable_to_mf17506": False,
        },
        "partial_refresh": {
            **partial,
            **partial_refresh,
            "advertised_as_fast": header_facts["has_fast_partial_update"],
            "advertised_partial_equals_full_time": (
                header_facts["partial_refresh_time_ms"]
                == header_facts["full_refresh_time_ms"]
            ),
            "refresh_is_still_otp_path": True,
            "runtime_lut_upload_present": False,
        },
        "typed_command_inventory": [f"0x{command:02x}" for command in commands],
        "runtime_waveform_boundary": {
            "typed_command_0x20_present": 0x20 in commands,
            "typed_command_0x21_present": 0x21 in commands,
            "typed_command_0xe9_present": 0xE9 in commands,
            "literal_799_present": bool(
                re.search(r"(?<!\d)799(?!\d)", _strip_comments(current))
            ),
            "literal_704_present": bool(
                re.search(r"(?<!\d)704(?!\d)", _strip_comments(current))
            ),
            "literal_2508_present": bool(
                re.search(r"(?<!\d)2508(?!\d)", _strip_comments(current))
            ),
            "dual_controller_api_present": False,
            "runtime_waveform_abi_recovered": False,
            "mf17506_recovery_contract_recovered": False,
        },
        "bounded_conclusion": {
            "positive": (
                "Pinned GxEPD2 source independently matches the 14-event Good Display "
                "OTP init trace and labels native code 4 orange on GDEP073E01."
            ),
            "negative": (
                "The source identifies the controller as unknown, exposes one CS, and has "
                "no typed 0x20/0x21/E9 or 799/704/2508 runtime-waveform contract."
            ),
            "mf17506_interpretation": (
                "Code-4 semantics are not portable: the adjacent source label cannot "
                "override the observed MF-17506 OTP result or name any mode-1 category."
            ),
        },
        "safety": {
            "network_accessed": network_accessed,
            "network_scope": (
                "four immutable raw.githubusercontent.com commit URLs"
                if network_accessed
                else "none"
            ),
            "network_was_public_github_only": network_accessed,
            "serial_accessed": False,
            "device_network_accessed": False,
            "hardware_accessed": False,
            "flash_performed": False,
            "visible_refreshes": 0,
            "live_payload_generated": False,
            "live_test_authorized": False,
        },
    }
    report["report_canonical_sha256"] = _sha256(_canonical_bytes(report))
    return report


def _read_local_blobs(paths: Mapping[str, Path]) -> dict[str, bytes]:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.is_file()]
    if missing:
        raise AuditError("missing local source files: " + ", ".join(missing))
    return {name: path.read_bytes() for name, path in paths.items()}


def fetch_pinned_blobs(fetcher: Callable[[str], bytes] = _fetch) -> dict[str, bytes]:
    return {name: fetcher(url) for name, url in URLS.items()}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit pinned public GxEPD2 GDEP073E01 source (no device I/O)."
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="fetch only the four immutable GitHub raw URLs pinned by this tool",
    )
    parser.add_argument("--current-source", type=Path)
    parser.add_argument("--current-header", type=Path)
    parser.add_argument("--current-properties", type=Path)
    parser.add_argument("--previous-source", type=Path)
    parser.add_argument(
        "--cross-image-report",
        type=Path,
        default=DEFAULT_CROSS_IMAGE_REPORT,
        help="optional local Good Display binary audit JSON",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.allow_network:
            if any(
                value is not None
                for value in (
                    args.current_source,
                    args.current_header,
                    args.current_properties,
                    args.previous_source,
                )
            ):
                raise AuditError(
                    "do not combine --allow-network with local source paths"
                )
            blobs = fetch_pinned_blobs()
            network_accessed = True
        else:
            local = {
                "current_source": args.current_source,
                "current_header": args.current_header,
                "current_properties": args.current_properties,
                "previous_source": args.previous_source,
            }
            if any(path is None for path in local.values()):
                raise AuditError(
                    "use --allow-network or provide all four local source paths"
                )
            blobs = _read_local_blobs(local)  # type: ignore[arg-type]
            network_accessed = False
        report = build_report(
            blobs,
            cross_image_report=args.cross_image_report,
            enforce_pins=True,
            network_accessed=network_accessed,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (AuditError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
