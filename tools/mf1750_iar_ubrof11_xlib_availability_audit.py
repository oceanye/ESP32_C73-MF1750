#!/usr/bin/env python3
"""Audit the availability boundary for an XLIB that can read three UBROF11 files.

The delivered ``DELAY.r43``, ``E6_73.r43``, and ``main.r43`` objects contain
stack-usage records.  The already identity-pinned XLIB 6.1.3.56 fails both
``LIST-EXTERNALS`` and ``LIST-ENTRIES`` with ``Unknown tag: E2``.  IAR's own
release notes say that issue EW25659 was fixed in XLINK/XLIB 6.3.4.78.

This tool makes the remaining acquisition boundary reproducible.  It:

* searches only explicitly named local roots for ``xlib.exe``;
* hashes candidates without executing unknown binaries;
* optionally reruns the known, SHA-pinned 6.1.3.56 boundary check;
* optionally performs GET-only checks of a small allowlist of official IAR
  and TI pages; and
* emits no object bytes, symbol tables, waveform bytes, or credentials.

It deliberately does not submit IAR's evaluation form, authenticate to My
Pages, guess protected installer URLs, install software, or run an
unattested executable.  A newly acquired XLIB must first be provenance- and
identity-pinned in code before it is ever executed.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import hashlib
from html import unescape
import http.cookiejar
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from host.application.durable_io import write_new_bytes_durable
from tools import mf1750_iar_r43_cross_object_graph as graph
from tools import mf1750_iar_xlib_external_index_audit as legacy_audit


KIND = "mf1750-iar-ubrof11-xlib-availability-audit"
SCHEMA_VERSION = 1
MINIMUM_FIXED_XLIB_VERSION = "6.3.4.78"

KNOWN_LEGACY_XLIB = {
    "version": "6.1.3.56",
    "size_bytes": 550_912,
    "sha256": "ea11101e1365065c5899dc1db644eb8d6f0ff769abc477119770355d98804284",
    "provenance": "TI_SLAC050_IAR_EW430_6_20_1",
}
KNOWN_SLAC050_ARCHIVE = {
    "version": "01.00.0B.0A",
    "iar_product_version": "6.20.1",
    "size_bytes": 385_225_224,
    "sha256": "af0453d7ea0b25975060ce160f079ffab5f6b84f103458fcbb036a933b338c6f",
}
UBROF11_OBJECTS = {
    "DELAY.r43": {
        "size_bytes": 1_774,
        "sha256": "82eaf1f5ae2ee28f7df7dafb7e9ecf8b46731d7f98784a4731d9b49f638c96da",
        "paired_external_index_call_sites": 0,
    },
    "E6_73.r43": {
        "size_bytes": 109_582,
        "sha256": "0f4d22c6d07f79d9ededffd50f155dc96d802b0e90bf908c30f2b85f1714ee2f",
        "paired_external_index_call_sites": 35,
    },
    "main.r43": {
        "size_bytes": 29_684,
        "sha256": "76ada9c8846226457ef74537a345ca1e057e8c11abc1002423424dfffd2640f4",
        "paired_external_index_call_sites": 17,
    },
}

XLINK_RELEASE_NOTES_URL = (
    "https://netstorage.iar.com/FileStore/STANDARD/001/000/603/ew/doc/"
    "infocenter/xlink.ENU.html"
)
IAR_TRIAL_URL = "https://www.iar.com/embedded-development-tools/free-trials"
IAR_UPDATE_INDEXES = {
    "standard": "https://updates.iar.com/?product=EW430",
    "baseline": "https://updates.iar.com/?product=EW430-BL",
}
TI_SLAC050_URL = "https://www.ti.com/tool/download/SLAC050"
EXPECTED_TI_ARCHIVE_URL = (
    "https://dr-download.ti.com/software-development/"
    "ide-configuration-compiler-or-debugger/MD-pEJzk8vQT9/"
    "01.00.0B.0A/slac050ba.zip"
)

NETWORK_HOST_ALLOWLIST = {
    "dr-download.ti.com",
    "netstorage.iar.com",
    "register.iar.com",
    "updates.iar.com",
    "www.iar.com",
    "www.ti.com",
}
USER_AGENT = "mf1750-official-source-audit/1.0"

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
ANCHOR_RE = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.I | re.S)
ATTR_RE = re.compile(
    r"(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*"
    r"(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.S,
)


class XlibAvailabilityError(RuntimeError):
    """An identity, official-source, or safety invariant changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise XlibAvailabilityError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _plain_text(fragment: str) -> str:
    return SPACE_RE.sub(" ", unescape(TAG_RE.sub(" ", fragment))).strip()


def _parse_attrs(raw: str) -> dict[str, str]:
    return {
        match.group("name").casefold(): unescape(match.group("value"))
        for match in ATTR_RE.finditer(raw)
    }


def _version_tuple(value: str) -> tuple[int, ...]:
    _require(
        re.fullmatch(r"\d+(?:\.\d+)+", value) is not None,
        f"invalid dotted version: {value}",
    )
    return tuple(int(part) for part in value.split("."))


def _version_at_least(value: str, minimum: str) -> bool:
    left = _version_tuple(value)
    right = _version_tuple(minimum)
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) >= right + (0,) * (width - len(right))


@dataclass(frozen=True)
class SearchRoot:
    label: str
    path: Path


def parse_search_root(value: str) -> SearchRoot:
    label, separator, raw_path = value.partition("=")
    _require(separator == "=" and label and raw_path, "search root must be LABEL=PATH")
    _require(
        re.fullmatch(r"[A-Za-z0-9_.-]+", label) is not None,
        "search-root label contains unsupported characters",
    )
    return SearchRoot(label=label, path=Path(raw_path).resolve())


def default_search_roots() -> list[SearchRoot]:
    home = Path.home()
    local_appdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
    roots = [
        SearchRoot("workspace", graph.REPO_ROOT),
        SearchRoot("downloads", home / "Downloads"),
        SearchRoot("local_temp", local_appdata / "Temp"),
        SearchRoot("local_programs", local_appdata / "Programs"),
        SearchRoot("user_cache", home / ".cache"),
        SearchRoot("programdata_package_cache", Path("C:/ProgramData/Package Cache")),
    ]
    for label, variable in (
        ("program_files", "ProgramFiles"),
        ("program_files_x86", "ProgramFiles(x86)"),
    ):
        if value := os.environ.get(variable):
            roots.append(SearchRoot(label, Path(value)))
    return roots


def _classify_candidate(payload: bytes) -> dict[str, Any]:
    digest = _sha256(payload)
    if (
        len(payload) == KNOWN_LEGACY_XLIB["size_bytes"]
        and digest == KNOWN_LEGACY_XLIB["sha256"]
    ):
        return {
            "attestation": "KNOWN_OFFICIAL_TI_SLAC050_IDENTITY",
            "version": KNOWN_LEGACY_XLIB["version"],
            "meets_EW25659_fixed_version_floor": False,
            "execution_permitted_by_this_audit": True,
        }
    return {
        "attestation": "UNATTESTED_IDENTITY_NOT_EXECUTED",
        "version": None,
        "meets_EW25659_fixed_version_floor": None,
        "execution_permitted_by_this_audit": False,
    }


def scan_local_candidates(roots: Iterable[SearchRoot]) -> dict[str, Any]:
    root_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    for root in roots:
        root_path = root.path.resolve()
        candidates: list[Path] = []
        scan_errors = 0

        def on_error(_error: OSError) -> None:
            nonlocal scan_errors
            scan_errors += 1

        if root_path.is_file():
            if root_path.name.casefold() == "xlib.exe":
                candidates.append(root_path)
        elif root_path.is_dir():
            for directory, _subdirs, filenames in os.walk(
                root_path,
                topdown=True,
                onerror=on_error,
                followlinks=False,
            ):
                for filename in filenames:
                    if filename.casefold() == "xlib.exe":
                        candidates.append(Path(directory) / filename)

        local_count = 0
        for path in sorted(candidates, key=lambda item: str(item).casefold()):
            resolved = path.resolve()
            path_key = str(resolved).casefold()
            if path_key in seen_paths:
                continue
            seen_paths.add(path_key)
            payload = resolved.read_bytes()
            try:
                relative = resolved.relative_to(root_path).as_posix()
            except ValueError:
                relative = resolved.name
            row = {
                "root_label": root.label,
                "relative_path": relative,
                "size_bytes": len(payload),
                "sha256": _sha256(payload),
                **_classify_candidate(payload),
            }
            candidate_rows.append(row)
            local_count += 1

        root_rows.append(
            {
                "label": root.label,
                "exists": root_path.exists(),
                "candidate_count": local_count,
                "scan_error_count": scan_errors,
            }
        )

    candidate_rows.sort(
        key=lambda row: (
            str(row["root_label"]).casefold(),
            str(row["relative_path"]).casefold(),
        )
    )
    total_scan_errors = sum(row["scan_error_count"] for row in root_rows)
    return {
        "roots": root_rows,
        "candidates": candidate_rows,
        "candidate_count": len(candidate_rows),
        "total_scan_error_count": total_scan_errors,
        "all_search_roots_fully_readable": total_scan_errors == 0,
        "known_legacy_candidate_count": sum(
            row["attestation"] == "KNOWN_OFFICIAL_TI_SLAC050_IDENTITY"
            for row in candidate_rows
        ),
        "attested_fixed_or_newer_candidate_count": 0,
        "unknown_candidates_were_executed": False,
    }


def pin_slac050_archive(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "provided": False,
            "identity_match": None,
            **KNOWN_SLAC050_ARCHIVE,
        }
    _require(path.is_file(), f"SLAC050 archive is missing: {path}")
    payload = path.read_bytes()
    identity_match = (
        len(payload) == KNOWN_SLAC050_ARCHIVE["size_bytes"]
        and _sha256(payload) == KNOWN_SLAC050_ARCHIVE["sha256"]
    )
    _require(identity_match, "SLAC050 archive identity changed")
    return {
        "provided": True,
        "identity_match": True,
        **KNOWN_SLAC050_ARCHIVE,
    }


def verify_known_legacy_boundary(
    xlib_path: Path | None,
    iar_root: Path,
    *,
    report_builder: Callable[[Path, Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if xlib_path is None:
        return {
            "performed": False,
            "known_identity": KNOWN_LEGACY_XLIB,
            "native_UBROF11_tables_recovered": False,
        }
    payload = xlib_path.read_bytes()
    _require(
        len(payload) == KNOWN_LEGACY_XLIB["size_bytes"]
        and _sha256(payload) == KNOWN_LEGACY_XLIB["sha256"],
        "legacy XLIB path is not the identity-pinned official 6.1.3.56 executable",
    )
    if report_builder is None:
        report = legacy_audit.build_report(xlib_path, iar_root)
    else:
        report = report_builder(xlib_path, iar_root)
    object_rows = {
        name: {
            "LIST_EXTERNALS_status": report["objects"][name]["xlib_status"],
            "LIST_ENTRIES_status": report["objects"][name]["xlib_status"],
            "diagnostic": report["objects"][name]["diagnostic"],
            "paired_external_index_call_sites": report["objects"][name][
                "external_index_calls"
            ],
            "empty_symbol_table_inferred": report["objects"][name][
                "empty_symbol_table_inferred"
            ],
        }
        for name in UBROF11_OBJECTS
    }
    _require(
        all(
            row["LIST_EXTERNALS_status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2"
            and row["LIST_ENTRIES_status"] == "UNSUPPORTED_STACK_USAGE_TAG_E2"
            and row["diagnostic"] == legacy_audit.UNKNOWN_E2
            and not row["empty_symbol_table_inferred"]
            for row in object_rows.values()
        ),
        "known legacy XLIB boundary changed",
    )
    _require(
        sum(row["paired_external_index_call_sites"] for row in object_rows.values())
        == 52,
        "UBROF11 paired external-index call count changed",
    )
    return {
        "performed": True,
        "known_identity": KNOWN_LEGACY_XLIB,
        "commands": ["LIST-EXTERNALS", "LIST-ENTRIES"],
        "temporary_copy_policy": "fresh_ASCII_only_directory_byte_identical_copy",
        "objects": object_rows,
        "native_UBROF11_tables_recovered": False,
        "diagnostic_is_version_boundary_not_empty_table": True,
    }


def parse_xlink_release_notes(payload: bytes) -> dict[str, Any]:
    text = _plain_text(payload.decode("utf-8", "replace"))
    markers = {
        "fix_heading_present": "XLINK 6.3.4.78 - 2015-Sep-22" in text,
        "issue_present": "EW25659" in text,
        "unknown_E2_present": "Unknown tag: E2" in text,
        "stack_usage_present": "stack usage information" in text,
        "UBROF11_support_floor_present": "XLIB supports UBROF 11 starting with version 6.0.0.46"
        in text,
    }
    _require(all(markers.values()), "official XLINK release-note semantics changed")
    return {
        "url": XLINK_RELEASE_NOTES_URL,
        "response_size_bytes": len(payload),
        "response_sha256": _sha256(payload),
        **markers,
        "EW25659_fixed_in": MINIMUM_FIXED_XLIB_VERSION,
        "fix_scope": "XLIB_READING_UBROF_WITH_STACK_USAGE_INFORMATION",
    }


def parse_update_index_for_640(index_url: str, payload: bytes) -> str:
    html = payload.decode("utf-8", "replace")
    links = [
        unescape(match.group("value"))
        for match in ATTR_RE.finditer(html)
        if match.group("name").casefold() == "href"
        and re.search(
            r"(?:^|[?&])version=6\.40(?:$|[&#])", unescape(match.group("value"))
        )
    ]
    _require(len(links) == 1, "IAR update index 6.40 link inventory changed")
    return urljoin(index_url, links[0])


def parse_ew430_640_update_page(payload: bytes) -> dict[str, Any]:
    html = payload.decode("utf-8", "replace")
    section_match = re.search(
        r'<p[^>]*class=["\'][^"\']*title[^"\']*["\'][^>]*>\s*'
        r"Install EW430 6\.40\s*</p>(?P<section>.*?)"
        r'(?=<p[^>]*class=["\'][^"\']*title[^"\']*["\']|\Z)',
        html,
        re.I | re.S,
    )
    _require(section_match is not None, "IAR EW430 6.40 install section is missing")
    section = section_match.group("section")
    section_text = _plain_text(section)
    download_anchors: list[dict[str, Any]] = []
    for match in ANCHOR_RE.finditer(section):
        if _plain_text(match.group("body")).startswith("Download installer"):
            attrs = _parse_attrs(match.group("attrs"))
            classes = attrs.get("class", "").split()
            download_anchors.append(
                {
                    "href_present": bool(attrs.get("href")),
                    "server_disabled": "aspNetDisabled" in classes,
                }
            )
    _require(len(download_anchors) == 1, "EW430 6.40 download-anchor inventory changed")
    row = download_anchors[0]
    _require("6.40.1" in section_text, "EW430 6.40.1 product marker is missing")
    _require(
        "A valid Support and Update Agreement is required for this download."
        in section_text,
        "EW430 6.40 SUA requirement marker is missing",
    )
    _require(
        row["server_disabled"] and not row["href_present"],
        "anonymous 6.40 installer boundary changed",
    )
    row = {
        "product_version": "6.40.1",
        "minimum_fixed_XLIB_expected_from_release_timeline": True,
        "valid_SUA_explicitly_required": True,
        "anonymous_download_href_present": row["href_present"],
        "download_anchor_server_disabled": row["server_disabled"],
    }
    row["semantic_sha256"] = _sha256(_canonical_bytes(row))
    return row


def parse_trial_page(payload: bytes) -> dict[str, Any]:
    html = payload.decode("utf-8", "replace")
    _require("14 days" in _plain_text(html), "IAR trial duration marker changed")
    section_match = re.search(
        r"IAR Embedded Workbench for MSP430(?P<section>.*?)"
        r"IAR Embedded Workbench for AVR",
        html,
        re.I | re.S,
    )
    _require(section_match is not None, "IAR MSP430 trial section is missing")
    section = section_match.group("section")
    links = []
    for match in ANCHOR_RE.finditer(section):
        attrs = _parse_attrs(match.group("attrs"))
        href = attrs.get("href", "")
        if urlparse(href).hostname == "register.iar.com":
            links.append(href)
    _require(len(links) == 1, "IAR MSP430 registration-link inventory changed")
    parsed = urlparse(links[0])
    query = parse_qs(parsed.query)
    features = query.get("features", [""])[0]
    _require(
        "430.EW.LINKER" in features, "MSP430 trial linker feature marker is missing"
    )
    canonical_query = urlencode(
        {
            "features": features,
            "lang": query.get("lang", ["en"])[0],
            "lms_name": query.get("lms_name", ["LMS2"])[0],
            "source": query.get("source", ["iar.com"])[0],
        }
    )
    return {
        "url": IAR_TRIAL_URL,
        "response_size_bytes": len(payload),
        "response_sha256": _sha256(payload),
        "trial_duration_days": 14,
        "registration_required": True,
        "msp430_linker_feature_present": True,
        "registration_get_url": f"https://register.iar.com/eval?{canonical_query}",
    }


def parse_registration_page(payload: bytes) -> dict[str, Any]:
    text = _plain_text(payload.decode("utf-8", "replace"))
    markers = [
        "Register for Evaluation",
        "IAR Embedded Workbench for MSP430, v. 8.10, Evaluation version",
        "First name",
        "Last name",
        "Email",
        "Phone",
        "Company",
        "Country",
        "Industry",
        "Please describe your project",
        "Software Licence Agreement",
    ]
    missing = [marker for marker in markers if marker not in text]
    _require(not missing, f"IAR registration-page markers missing: {missing}")
    return {
        "response_size_bytes": len(payload),
        "response_sha256": _sha256(payload),
        "product_version": "8.10",
        "required_identity_or_project_fields_present": True,
        "license_agreement_present": True,
        "form_submission_performed": False,
    }


def parse_ti_slac050_page(payload: bytes) -> dict[str, Any]:
    html = payload.decode("utf-8", "replace")
    text = _plain_text(html)
    _require(
        "IAR Embedded Workbench KickStart (IAR 6.20.1 / WIN)" in text,
        "TI SLAC050 version marker changed",
    )
    _require(
        KNOWN_SLAC050_ARCHIVE["version"] in text, "TI SLAC050 release version changed"
    )
    urls = re.findall(
        r'https://dr-download\.ti\.com/[^"\s<]+slac050ba\.zip', html, re.I
    )
    urls = [unescape(url) for url in urls]
    _require(EXPECTED_TI_ARCHIVE_URL in urls, "TI SLAC050 archive URL changed")
    return {
        "url": TI_SLAC050_URL,
        "response_size_bytes": len(payload),
        "response_sha256": _sha256(payload),
        "latest_listed_IAR_product_version": "6.20.1",
        "archive_release_version": KNOWN_SLAC050_ARCHIVE["version"],
        "archive_url": EXPECTED_TI_ARCHIVE_URL,
        "archive_downloaded_by_this_audit": False,
        "contains_fixed_or_newer_XLIB": False,
    }


def _fetch_get(opener: Any, url: str) -> bytes:
    parsed = urlparse(url)
    _require(parsed.scheme == "https", f"official source is not HTTPS: {url}")
    _require(
        parsed.hostname in NETWORK_HOST_ALLOWLIST,
        f"network host is not allowlisted: {url}",
    )
    request = Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    with opener.open(request, timeout=30) as response:
        final = urlparse(response.geturl())
        _require(final.scheme == "https", "official source redirected away from HTTPS")
        _require(
            final.hostname in NETWORK_HOST_ALLOWLIST,
            "official source redirected to an unallowlisted host",
        )
        _require(
            response.status == 200, f"official GET returned HTTP {response.status}"
        )
        return response.read()


def collect_official_network_evidence() -> dict[str, Any]:
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    release_payload = _fetch_get(opener, XLINK_RELEASE_NOTES_URL)

    updates: dict[str, Any] = {}
    for edition, index_url in IAR_UPDATE_INDEXES.items():
        index_payload = _fetch_get(opener, index_url)
        version_url = parse_update_index_for_640(index_url, index_payload)
        _require(
            urlparse(version_url).hostname == "updates.iar.com",
            "IAR version link host changed",
        )
        version_payload = _fetch_get(opener, version_url)
        updates[edition] = {
            "index_url": index_url,
            **parse_ew430_640_update_page(version_payload),
        }

    trial_payload = _fetch_get(opener, IAR_TRIAL_URL)
    trial = parse_trial_page(trial_payload)
    registration_payload = _fetch_get(opener, trial["registration_get_url"])
    registration = parse_registration_page(registration_payload)
    trial.pop("registration_get_url")

    ti_payload = _fetch_get(opener, TI_SLAC050_URL)
    evidence = {
        "network_accessed": True,
        "http_methods": ["GET"],
        "hosts": sorted(
            NETWORK_HOST_ALLOWLIST
            & {
                "netstorage.iar.com",
                "register.iar.com",
                "updates.iar.com",
                "www.iar.com",
                "www.ti.com",
            }
        ),
        "authentication_attempted": False,
        "form_submission_performed": False,
        "protected_URL_guessing_performed": False,
        "xlink_release_notes": parse_xlink_release_notes(release_payload),
        "ew430_6_40_update_pages": updates,
        "current_msp430_trial": trial,
        "current_msp430_registration_form": registration,
        "ti_public_slac050": parse_ti_slac050_page(ti_payload),
    }
    evidence["semantic_sha256"] = _sha256(_canonical_bytes(evidence))
    return evidence


def offline_network_boundary() -> dict[str, Any]:
    return {
        "network_accessed": False,
        "allowlisted_sources": [
            XLINK_RELEASE_NOTES_URL,
            *IAR_UPDATE_INDEXES.values(),
            IAR_TRIAL_URL,
            TI_SLAC050_URL,
        ],
        "authentication_attempted": False,
        "form_submission_performed": False,
        "protected_URL_guessing_performed": False,
        "semantic_validation_performed": False,
    }


def _pin_delivered_ubrof11(iar_root: Path) -> list[dict[str, Any]]:
    object_dir = iar_root / graph.OBJECT_DIR_REL
    rows = []
    for name, expected in UBROF11_OBJECTS.items():
        path = object_dir / name
        _require(path.is_file(), f"delivered UBROF11 object is missing: {path}")
        payload = path.read_bytes()
        _require(len(payload) == expected["size_bytes"], f"{name} size changed")
        _require(_sha256(payload) == expected["sha256"], f"{name} SHA-256 changed")
        rows.append(
            {
                "name": name,
                "UBROF_version_byte": 11,
                **expected,
            }
        )
    _require(
        sum(row["paired_external_index_call_sites"] for row in rows) == 52,
        "delivered UBROF11 paired call-site count changed",
    )
    return rows


def build_report(
    *,
    search_roots: Iterable[SearchRoot],
    iar_root: Path = graph.DEFAULT_IAR_ROOT,
    legacy_xlib: Path | None = None,
    slac050_archive: Path | None = None,
    network_evidence: dict[str, Any] | None = None,
    legacy_report_builder: Callable[[Path, Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    delivered = _pin_delivered_ubrof11(iar_root)
    local = scan_local_candidates(search_roots)
    legacy = verify_known_legacy_boundary(
        legacy_xlib,
        iar_root,
        report_builder=legacy_report_builder,
    )
    archive = pin_slac050_archive(slac050_archive)
    official = (
        network_evidence if network_evidence is not None else offline_network_boundary()
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "question": "is an official fixed-or-newer XLIB locally available for native UBROF11 symbol listing",
            "hardware_accessed": False,
            "serial_or_COM_accessed": False,
            "device_network_accessed": False,
            "firmware_written_or_flashed": False,
            "visible_refresh_requested": False,
            "software_installed": False,
            "unknown_binary_executed": False,
            "credentials_or_personal_data_submitted": False,
            "raw_object_or_symbol_table_emitted": False,
            "raw_waveform_or_LUT_emitted": False,
        },
        "delivered_UBROF11": {
            "objects": delivered,
            "object_count": 3,
            "paired_external_index_call_sites_total": 52,
            "native_LIST_EXTERNALS_or_LIST_ENTRIES_tables_recovered": False,
        },
        "local_search": local,
        "known_legacy_XLIB_boundary": legacy,
        "cached_public_TI_package": archive,
        "official_public_source_audit": official,
        "adjudication": {
            "official_fixed_or_newer_XLIB_found_and_identity_pinned": False,
            "three_original_UBROF11_objects_natively_parsed": False,
            "52_paired_indices_checked_against_native_EXTERNAL_tables": False,
            "verdict": "NO_UPDATED_OFFICIAL_XLIB_IN_READABLE_LOCAL_OR_ANONYMOUS_PUBLIC_SCOPE",
            "not_a_zero_symbol_result": True,
            "minimum_missing_artifact": {
                "artifact": "official_IAR_xlib.exe",
                "version_floor": MINIMUM_FIXED_XLIB_VERSION,
                "legitimate_acquisition_routes": [
                    "IAR_MSP430_8_10_evaluation_after_user_registration_and_license_acceptance",
                    "IAR_EW430_6_40_or_newer_product_update_with_valid_SUA",
                ],
                "required_identity_capture": [
                    "size_bytes",
                    "sha256",
                    "file_version",
                    "official_provenance",
                ],
                "required_read_only_validation": [
                    "LIST-EXTERNALS_on_original_DELAY_E6_73_main_ASCII_copies",
                    "LIST-ENTRIES_on_original_DELAY_E6_73_main_ASCII_copies",
                    "compare_52_paired_external_indices_to_native_ordered_EXTERNAL_tables",
                ],
                "installation_required_for_validation": False,
                "user_registration_or_valid_SUA_currently_required": True,
            },
        },
    }
    report["integrity"] = {
        "canonical_sha256_before_integrity": _sha256(_canonical_bytes(report))
    }
    return report


def _output_bytes(report: dict[str, Any], *, compact: bool) -> bytes:
    if compact:
        return _canonical_bytes(report) + b"\n"
    return (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _discover_legacy_xlib() -> Path | None:
    configured = os.environ.get("MF1750_IAR_XLIB_PATH")
    if configured:
        return Path(configured).resolve()
    candidate = (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        / "Temp/iar_ew430_6201_xlink_only/component_430_xlink_common/430/bin/xlib.exe"
    )
    return candidate.resolve() if candidate.is_file() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-root",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="explicit local root to scan; repeatable (defaults to workspace/user/tool roots)",
    )
    parser.add_argument("--iar-root", type=Path, default=graph.DEFAULT_IAR_ROOT)
    parser.add_argument("--legacy-xlib", type=Path, default=_discover_legacy_xlib())
    parser.add_argument("--slac050-archive", type=Path)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="perform GET-only checks of the hardcoded official IAR/TI allowlist",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)

    try:
        roots = (
            [parse_search_root(value) for value in args.search_root]
            if args.search_root
            else default_search_roots()
        )
        network = collect_official_network_evidence() if args.allow_network else None
        report = build_report(
            search_roots=roots,
            iar_root=args.iar_root.resolve(),
            legacy_xlib=args.legacy_xlib.resolve() if args.legacy_xlib else None,
            slac050_archive=(
                args.slac050_archive.resolve() if args.slac050_archive else None
            ),
            network_evidence=network,
        )
        payload = _output_bytes(report, compact=args.compact)
        if args.output:
            write_new_bytes_durable(args.output.resolve(), payload)
        else:
            sys.stdout.buffer.write(payload)
    except (
        XlibAvailabilityError,
        legacy_audit.XlibAuditError,
        OSError,
        TimeoutError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
