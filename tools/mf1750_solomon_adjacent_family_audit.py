#!/usr/bin/env python3
"""Pin adjacent Solomon waveform/cascade manuals and their transfer boundary.

The four public manuals are useful because they expose two independent
counterexamples to field migration: SSD1681 and SSD1683 assign different zero
semantics to fields with the same names, while SSD2677 advertises programmable
waveforms and cascade operation without publishing a runtime waveform-write
ABI.  The report is metadata-only and never emits page text or waveform bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import unicodedata
from typing import Any, Final


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.durable_io import (  # noqa: E402
    DurableWriteError,
    write_new_bytes_durable,
)


KIND: Final = "mf1750-solomon-adjacent-family-audit"
SCHEMA_VERSION: Final = 1
PYMUPDF_VERSION: Final = "1.28.2"
PUBLIC_SOURCE_ROOT: Final = REPO_ROOT / ".test-output" / "offline" / "public_sources"


DOCUMENTS: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "SSD1683_REV1_0_JAN2021",
        "filename": "SSD1683_Rev1.0_Jan2021.pdf",
        "source_url": (
            "https://files.seeedstudio.com/wiki/Other_Display/42-epaper/"
            "IC%20Driver%20SSD1683%20Datasheet.PDF"
        ),
        "bytes": 3_931_534,
        "sha256": "77c188ba55b1b81129f8c0557f845fde25ca97d73ee86ed1ba907ea87a0b5e9c",
        "page_count": 49,
        "revision": "Rev 1.0, Jan 2021",
        "pages": {
            14: {
                "sha256": "8b853ce53897539c4ae5bf7898612ef7e17fc12e41f45be2848b49bb7713a021",
                "anchors": (
                    "In 3-color mode, there are 8 groups (Group0 to Group7) for 4 LUTs.",
                    "RP[n] = 0 indicates that the group is skipped",
                    "SR[nXY] = 0 indicates that the sub-group is skipped",
                ),
            },
            16: {
                "sha256": "3a1ea857bd3fcab73f0204f5fd2b7cab9cfd44634373433d91e65c11873bff8e",
                "anchors": (
                    "WS byte 0~226",
                    "defined by Register 0x32",
                    "WS byte 227",
                ),
            },
            28: {
                "sha256": "c4eb7160e86c612bda8898c2b5b43306a69c60981b81f08a6c17a06baf974497",
                "anchors": (
                    "0 0 20 0 0 1 0 0 0 0 0 Master Activation",
                    "0 0 21 0 0 1 0 0 0 0 1 Display Update Control 1",
                ),
            },
            32: {
                "sha256": "ad885ff393f82270a1878b3e688e48f749db40510218b628b83613a7f49ab5da",
                "anchors": ("Write LUT register from MCU interface [227 bytes]",),
            },
        },
        "facts": {
            "colour_mode": "three-colour adjacent controller",
            "lut_count": 4,
            "groups_per_lut": 8,
            "phases_per_group": 4,
            "state_repeat_fields_per_group": 2,
            "bytes_per_group_per_lut": 7,
            "group_formula": "1 RP + 4 packed VS|TP + 2 SR",
            "register_0x32_payload_bytes": 227,
            "register_0x20_role": "Master Activation",
            "register_0x21_role": "Display Update Control 1",
            "RP_zero_semantics": "group skipped",
            "SR_zero_semantics": "sub-group skipped",
        },
    },
    {
        "id": "SSD1683A_REV1_1_MAR2023",
        "filename": "SSD1683A_Rev1.1_Mar2023.pdf",
        "source_url": (
            "https://support.newhavendisplay.com/hc/en-us/"
            "article_attachments/41742409400983"
        ),
        "bytes": 2_880_342,
        "sha256": "7946b986783b7c4feba2d388290bf6d36ec20d83f43effb538b85b8d4cab7585",
        "page_count": 50,
        "revision": "Rev 1.1, Mar 2023",
        "pages": {
            14: {
                "sha256": "330df4f44c221d950d1e8836a359935a4d594feb77f83380afaffa16ff998188",
                "anchors": (
                    "In 3-color mode, there are 8 groups (Group0 to Group7) for 4 LUTs.",
                    "RP[n] = 0 indicates that the group is skipped",
                    "SR[nXY] = 0 indicates that the sub-group is skipped",
                ),
            },
            16: {
                "sha256": "d52cf87c358ca8f5bdd0fdca05de651532d576d3f62853fbd57c6447416fe85f",
                "anchors": (
                    "WS byte 0~226",
                    "defined by Register 0x32",
                    "WS byte 227",
                ),
            },
            28: {
                "sha256": "bc2689de6ab04cca390880b71758b3397b3ab7b34ded8208f8c98cb42b3ac0c8",
                "anchors": (
                    "0 0 20 0 0 1 0 0 0 0 0 Master Activation",
                    "0 0 21 0 0 1 0 0 0 0 1 Display Update Control 1",
                ),
            },
            32: {
                "sha256": "27b8e43f1252209a7dcc64becb42264deff2c7d046fbed80b07c1d725cd3679a",
                "anchors": ("Write LUT register from MCU interface [227 bytes]",),
            },
        },
        "facts": {
            "colour_mode": "three-colour adjacent controller",
            "lut_count": 4,
            "groups_per_lut": 8,
            "phases_per_group": 4,
            "state_repeat_fields_per_group": 2,
            "bytes_per_group_per_lut": 7,
            "group_formula": "1 RP + 4 packed VS|TP + 2 SR",
            "register_0x32_payload_bytes": 227,
            "register_0x20_role": "Master Activation",
            "register_0x21_role": "Display Update Control 1",
            "RP_zero_semantics": "group skipped",
            "SR_zero_semantics": "sub-group skipped",
        },
    },
    {
        "id": "SSD1681_REV1_1_APR2021",
        "filename": "SSD1681_Rev1.1_Apr2021.pdf",
        "source_url": (
            "https://support.newhavendisplay.com/hc/en-us/"
            "article_attachments/41742572114967"
        ),
        "bytes": 2_783_721,
        "sha256": "da23b888cdc9b7f7fe1ecd2c2f500add5683b00c4c4116465cc78deb530d07dd",
        "page_count": 43,
        "revision": "Rev 1.1, Apr 2021",
        "pages": {
            15: {
                "sha256": "8665502d21bcfe84e8ea93d5448425f5aa97bc6fed22a89b34ad939605487d3f",
                "anchors": (
                    "there are 12 groups (Group0 to Group11)",
                    "RP[n] = 0 indicates that the repeat times =1",
                    "SR[nXY] = 0 indicates that the repeat times =1",
                ),
            },
            16: {
                "sha256": "e5ad6c496e6905d22ec22358d5e4375574bba7d4e05c1e7a2e4aaae2998f9514",
                "anchors": (
                    "there are 159 bytes in the waveform setting",
                    "WS byte 0~152",
                    "defined by Register 0x32",
                ),
            },
            26: {
                "sha256": "c6457401d7a5bbd6d87eab4ee8d93be07bdcae3304f9cdc8b06cf83d83f81996",
                "anchors": (
                    "0 0 20 0 0 1 0 0 0 0 0 Master Activation",
                    "0 0 21 0 0 1 0 0 0 0 1 Display Update Control 1",
                ),
            },
            30: {
                "sha256": "f6bd590b5771273a96aaa4d5ab3240bb9d8bcb52cd3e46e242ef949aa3539e7a",
                "anchors": ("Write LUT register from MCU interface [153 bytes]",),
            },
        },
        "facts": {
            "colour_mode": "three-colour adjacent controller",
            "lut_count": 5,
            "groups_per_lut": 12,
            "phases_per_group": 4,
            "state_repeat_fields_per_group": 2,
            "bytes_per_group_per_lut": 7,
            "group_formula": "1 RP + 4 packed VS|TP + 2 SR",
            "register_0x32_payload_bytes": 153,
            "full_waveform_setting_bytes": 159,
            "register_0x20_role": "Master Activation",
            "register_0x21_role": "Display Update Control 1",
            "RP_zero_semantics": "repeat times = 1",
            "SR_zero_semantics": "repeat times = 1",
        },
    },
    {
        "id": "SSD2677_REV1_0_MAR2024",
        "filename": "SSD2677_Rev1.0_Mar2024.pdf",
        "source_url": "https://files.waveshare.com/wiki/common/SSD2677_1.0.pdf",
        "bytes": 1_066_162,
        "sha256": "a2245bbaef593b14fc1ca9c42ea6dfcfb1ef6799a966246b5f23388b0f49ce2a",
        "page_count": 35,
        "revision": "Rev 1.0, Mar 2024",
        "pages": {
            5: {
                "sha256": "830e769b43b21e833281043ca923a3ccea47ca36f020161287030889220f7735",
                "anchors": (
                    "Programmable output Waveform Settings.",
                    "Embedded 6k Bytes OTP to store the waveform settings and parameters.",
                ),
            },
            12: {
                "sha256": "5bff33cc48bd2a12f61950e662874478056823925741b1de518ded95c8a41b58",
                "anchors": (
                    "The SSD2677 has a cascade mode that can cascade 2 chips",
                    "The pin M/S# is used to configure the chip.",
                    "TSDA, TSCL, SYNC[0:1], VCORE, VGH, VGL, VSH1, VSL, VSH2 and VCOM",
                ),
            },
            14: {
                "sha256": "ab206cfce72bac35264954d2ce327ea6e33f3407e216d7657c777642096f5cba",
                "anchors": (
                    "Commands or parameters not shown on above table are for “Reserve” usage.",
                ),
            },
            16: {
                "sha256": "d62b35738b03249dfa173cf0d63ca159239d3695cb2fe8e05c98ab551dddda79",
                "anchors": (
                    "During reset, auto load LUT from OTP if it is valid.",
                    "When PON/DRF, analog setting will follow the content of OTP.",
                    "During reset, no action to load LUT from OTP.",
                ),
            },
        },
        "facts": {
            "colour_system": "E5 Spectra3100 SE adjacent controller",
            "resolution": {"source": 960, "gate": 680},
            "bits_per_pixel": 2,
            "programmable_waveform_advertised": True,
            "waveform_otp_bytes": 6_144,
            "two_chip_cascade_documented": True,
            "cascade_max_resolution": {"source": 1920, "gate": 680},
            "master_slave_pin": "M/S#",
            "shared_cascade_nets": [
                "TSDA",
                "TSCL",
                "SYNC0",
                "SYNC1",
                "VCORE",
                "VGH",
                "VGL",
                "VSH1",
                "VSL",
                "VSH2",
                "VCOM",
            ],
            "public_runtime_waveform_write_command_found": False,
            "unshown_commands_declared_reserved": True,
            "LUT_EN_public_role": "reset-time OTP auto-load selection",
        },
    },
)


class SolomonAdjacentFamilyAuditError(RuntimeError):
    """Raised when a pinned primary input or invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SolomonAdjacentFamilyAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _normalize_pdf_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _document_evidence(spec: dict[str, Any], pymupdf: Any) -> dict[str, Any]:
    path = PUBLIC_SOURCE_ROOT / spec["filename"]
    _require(path.is_file(), f"missing adjacent manual: {path}")
    payload = path.read_bytes()
    _require(len(payload) == spec["bytes"], f"{spec['id']} size changed")
    _require(_sha256(payload) == spec["sha256"], f"{spec['id']} identity changed")
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")
    except Exception as error:  # pragma: no cover - library failure path
        raise SolomonAdjacentFamilyAuditError(
            f"cannot parse pinned {spec['id']} PDF"
        ) from error
    pages = []
    try:
        _require(
            document.page_count == spec["page_count"],
            f"{spec['id']} page count changed",
        )
        for page_number, page_spec in spec["pages"].items():
            normalized = _normalize_pdf_text(
                document.load_page(page_number - 1).get_text("text")
            )
            digest = _sha256(normalized.encode("utf-8"))
            _require(digest == page_spec["sha256"], f"{spec['id']} page changed")
            missing = [
                anchor for anchor in page_spec["anchors"] if anchor not in normalized
            ]
            _require(
                not missing,
                f"{spec['id']} page {page_number} lost required anchors: {missing}",
            )
            pages.append(
                {
                    "pdf_page_1_based": page_number,
                    "normalized_text_utf8_bytes": len(normalized.encode("utf-8")),
                    "normalized_text_sha256": digest,
                    "required_anchor_count": len(page_spec["anchors"]),
                    "all_required_anchors_present": True,
                    "page_text_emitted": False,
                }
            )
    finally:
        document.close()
    return {
        "id": spec["id"],
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "source_url": spec["source_url"],
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "page_count": spec["page_count"],
        "revision": spec["revision"],
        "pages": pages,
        "facts": spec["facts"],
        "facts_canonical_sha256": _sha256(_canonical_bytes(spec["facts"])),
        "raw_pdf_or_full_page_text_emitted": False,
    }


def build_report() -> dict[str, Any]:
    """Build a deterministic metadata-only adjacent-family report."""

    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - environment failure path
        raise SolomonAdjacentFamilyAuditError(
            "PyMuPDF is required for pinned primary-document text extraction"
        ) from error
    _require(
        str(getattr(pymupdf, "__version__", "unknown")) == PYMUPDF_VERSION,
        "PyMuPDF version changed; revalidate pinned page-text extraction",
    )
    documents = [_document_evidence(spec, pymupdf) for spec in DOCUMENTS]
    by_id = {item["id"]: item for item in documents}
    ssd1681 = by_id["SSD1681_REV1_1_APR2021"]["facts"]
    ssd1683 = by_id["SSD1683_REV1_0_JAN2021"]["facts"]
    ssd1683a = by_id["SSD1683A_REV1_1_MAR2023"]["facts"]
    ssd2677 = by_id["SSD2677_REV1_0_MAR2024"]["facts"]
    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_adjacent_family_non_portability_audit",
        "extractor": {
            "name": "PyMuPDF",
            "version": str(getattr(pymupdf, "__version__", "unknown")),
            "network_accessed_by_offline_audit": False,
        },
        "documents": documents,
        "cross_document_findings": {
            "ssd1683_and_ssd1683a_selected_waveform_geometry_equal": (
                ssd1683["groups_per_lut"],
                ssd1683["phases_per_group"],
                ssd1683["bytes_per_group_per_lut"],
                ssd1683["register_0x32_payload_bytes"],
            )
            == (
                ssd1683a["groups_per_lut"],
                ssd1683a["phases_per_group"],
                ssd1683a["bytes_per_group_per_lut"],
                ssd1683a["register_0x32_payload_bytes"],
            ),
            "eight_group_public_lineage_reaches_2023": True,
            "eight_group_public_lineage_uses_seven_not_eleven_bytes_per_group": True,
            "same_named_zero_semantics_conflict": {
                "fields": ["RP", "SR"],
                "SSD1681": {
                    "RP_zero": ssd1681["RP_zero_semantics"],
                    "SR_zero": ssd1681["SR_zero_semantics"],
                },
                "SSD1683": {
                    "RP_zero": ssd1683["RP_zero_semantics"],
                    "SR_zero": ssd1683["SR_zero_semantics"],
                },
                "semantics_equal": False,
            },
            "register_0x20_and_0x21_roles_stable_across_selected_168x": True,
            "register_0x20_role": "Master Activation; not waveform payload",
            "register_0x21_role": "Display Update Control 1; not waveform payload",
            "ssd2677_programmable_waveform_and_cascade_public": (
                ssd2677["programmable_waveform_advertised"]
                and ssd2677["two_chip_cascade_documented"]
            ),
            "ssd2677_runtime_waveform_write_ABI_public": False,
            "local_candidate_geometry": {
                "groups_per_category": 8,
                "bytes_per_group": 11,
                "candidate_R20_payload_bytes": 799,
                "candidate_R21_payload_bytes": 704,
            },
            "target_numbers_found_in_selected_manual_text": {
                "799": False,
                "704": False,
                "1503": False,
                "2508": False,
                "535": False,
            },
        },
        "adjudication": {
            "SPD1657_or_E2802_runtime_ABI_recovered": False,
            "local_11_byte_field_layout_recovered": False,
            "local_phase_count_recovered": False,
            "local_zero_or_FF_semantics_recovered": False,
            "controller_side_complement_decode_recovered": False,
            "dual_controller_load_commit_or_rollback_contract_recovered": False,
            "adjacent_command_field_or_electrical_transfer_allowed": False,
            "ssd2677_cascade_wiring_is_SPD1657_as_built_proof": False,
            "strongest_positive_conclusion": (
                "adjacent Solomon controllers publicly confirm programmable-waveform "
                "and cascade architectures while independently falsifying direct "
                "migration of group width, zero semantics, command roles, and ABI"
            ),
            "safe_next_evidence": [
                "same-version SPD1657/E2802 command and waveform specification",
                "same-version loader or decoder that consumes individual fields",
                "known-good dual-CS logic capture bound to one exact profile",
                "paired vendor profiles that vary one documented field only",
            ],
            "hardware_experiment_or_payload_generation_authorized": False,
        },
        "material_handling": {
            "manual_pages_text_extracted_in_memory": True,
            "manual_page_text_or_raw_pdf_emitted": False,
            "raw_key_plaintext_record_or_waveform_bytes_emitted": False,
            "runtime_payload_include_or_firmware_generated": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_COM8_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "runtime_payload_generated_or_modified": False,
            "vendor_evidence_modified": False,
        },
    }
    report["integrity"] = {
        "canonical_encoding": "UTF-8 sorted-key compact JSON excluding integrity",
        "canonical_sha256": _sha256(_canonical_bytes(report)),
    }
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = build_report()
        payload = (
            json.dumps(
                report,
                ensure_ascii=False,
                indent=None if args.compact else 2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            write_new_bytes_durable(args.output, payload)
    except (
        SolomonAdjacentFamilyAuditError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
