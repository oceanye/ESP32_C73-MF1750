#!/usr/bin/env python3
"""Audit second-generation Spectra/T2000 claims against the local MF1750 path.

This offline, identity-pinned audit keeps three questions separate:

* what E Ink and Himax publicly say about the second-generation waveform and
  the T2000 timing-controller architecture;
* what a supplier board and the MF-17506 module documents physically place on
  their respective controller paths; and
* what the local WF20/WF23 800-byte profiles and archived E2802 library
  actually establish.

The report intentionally emits metadata and adjudications only.  It neither
emits waveform bytes nor creates a firmware, payload, authorization, or live
hardware action.
"""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
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
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack  # noqa: E402


KIND: Final = "mf1750-second-generation-waveform-architecture-audit"
SCHEMA_VERSION: Final = 1
PYMUPDF_VERSION: Final = "1.28.2"
PUBLIC_SOURCE_ROOT: Final = REPO_ROOT / ".test-output" / "offline" / "public_sources"
MODULE_SPEC_PATH: Final = REPO_ROOT / "参考资料" / "MF-1750..1).pdf"
E2802_LIBRARY_PATH: Final = (
    REPO_ROOT
    / "参考资料"
    / "REG-API-oqc(1)(1)"
    / "REG-API-oqc"
    / "lib"
    / "eload_3bits_M3_E2802_20251229.lib"
)

PROFILE_BYTES: Final = 800
OPAQUE_PREFIX_BYTES: Final = 7
STRUCTURAL_BLOCKS: Final = 9
STRUCTURAL_RECORDS_PER_BLOCK: Final = 8
STRUCTURAL_RECORD_BYTES: Final = 11
OPAQUE_SUFFIX_BYTES: Final = 1
CANDIDATE_R20_BYTES: Final = 799
CONSTRUCTED_R21_BYTES: Final = 704
CONSTRUCTED_R21_SHA256: Final = (
    "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"
)

RUNTIME_ABI_TERMS: Final = (
    "SPD1657",
    "E2802",
    "WF20_25",
    "WF23_25",
    "799-byte",
    "704-byte",
    "535-byte",
    "1503-byte",
    "2508-byte",
    "0x20",
    "0x21",
)


PDF_DOCUMENTS: Final[tuple[dict[str, Any], ...]] = (
    {
        "id": "EINK_HIMAX_T2000_2024",
        "evidence_tier": "first-party joint E Ink/Himax announcement",
        "path": PUBLIC_SOURCE_ROOT / "T2000_EInk_Himax_2024.pdf",
        "source_url": (
            "https://www.himax.com.tw/wp-content/uploads/2024/07/"
            "E-Ink-and-Himax-Unveil-Advanced-Color-ePaper-Timing-Controller-"
            "ASIC-T2000-20240731-Final.pdf"
        ),
        "bytes": 318_348,
        "sha256": "11776df464e4aa7ff6ec058ec2bdd5c236ac4e8cda86af383fe270ed2b1fc8da",
        "page_count": 5,
        "pages": {
            1: {
                "utf8_bytes": 1_151,
                "sha256": "abc1f3aceb68a17a348932a8e9acac822fcced5205e64ce875139689a3b07026",
                "anchors": (
                    "joint debut of next generation color ePaper timing controller ASIC",
                    "the T2000",
                ),
            },
            2: {
                "utf8_bytes": 2_677,
                "sha256": "5419c6a86ae26f336c08226a69334c3e3d771c2703e2cb1ea368f9b147f898ec",
                "anchors": (
                    "The T2000 integrates E Ink’s proprietary color imaging algorithm",
                    "responsible for generating and managing timing signals",
                    "controlling the timing and duration of voltages",
                ),
            },
            3: {
                "utf8_bytes": 2_840,
                "sha256": "95eb004f0034a777538518740ea6d108e93740e0a3670d1c02ff88b1b195d02c",
                "anchors": (
                    "T2000’s supported interfaces include MIPI-DSI, USB 3.0, and SPI",
                    "converted into mLVDS or TTL signal formats",
                    "integrates a Himax DRAM controller that interfaces with LPDDR",
                ),
            },
        },
        "facts": {
            "hardware_type": "standalone color-ePaper timing-controller ASIC (TCON)",
            "proprietary_color_imaging_algorithm_integrated": True,
            "supported_eink_families_named": ["Kaleido 3", "Gallery 3", "Spectra 6"],
            "controls_voltage_timing_and_duration": True,
            "temperature_compensation": True,
            "host_inputs": ["MIPI-DSI", "USB 3.0", "SPI"],
            "panel_side_outputs": ["mLVDS", "TTL"],
            "external_memory_interface": "LPDDR through integrated DRAM controller",
            "active_power_claim_mw_less_than": 300,
            "sleep_power_claim_mw_less_than": 2,
        },
        "scan_runtime_abi_terms": True,
    },
    {
        "id": "HIMAX_T2000_2026",
        "evidence_tier": "first-party Himax deployment announcement",
        "path": PUBLIC_SOURCE_ROOT / "T2000_Himax_2026.pdf",
        "source_url": (
            "https://www.himax.com.tw/wp-content/uploads/2026/06/"
            "PR-Himax-Latest-T2000-Tcon-to-Power-the-Evolution-of-E-Ink-"
            "Next-Generation-Color-ePaper-into-Dynamic-Content-Applications-"
            "Final.pdf"
        ),
        "bytes": 257_100,
        "sha256": "5814d37e0c68015b61d5adb76e12c08b0e0c98ee4a4da08883fb682923025642",
        "page_count": 2,
        "pages": {
            1: {
                "utf8_bytes": 4_025,
                "sha256": "345cc74ce59d7712b787f9885be3f3a42f828c4f321b5c6ccbfd2cb0e90f1f28",
                "anchors": (
                    "successfully adopted into the latest ePaper controller architecture launched by E Ink",
                    "offering TTL, mini- LVDS outputs",
                    "USB 3.0, SPI, and I2C control interfaces",
                    "display refresh and data transmission operate simultaneously",
                ),
            },
        },
        "facts": {
            "adopted_in_eink_controller_architecture": True,
            "host_data_input": "four-lane MIPI",
            "panel_side_outputs": ["TTL", "mini-LVDS"],
            "control_interfaces": ["USB 3.0", "SPI", "I2C"],
            "synchronized_refresh_and_next_frame_preparation": True,
        },
        "scan_runtime_abi_terms": True,
    },
    {
        "id": "OKRA_OK_TC04A_T2000_V4",
        "evidence_tier": "third-party T2000 evaluation/finished-board specification",
        "path": PUBLIC_SOURCE_ROOT / "OKRA_OK_TC04A_T2000_V4_specs.pdf",
        "source_url": "https://okratechnologies.com/ok-tc04a.html",
        "download_url": (
            "https://28568182.s21i.faiusr.com/61/ABUIABA9GAAg542cywYo4OmpjQY.pdf"
        ),
        "bytes": 742_413,
        "sha256": "5def57fb11c018004ce047edb94a00283724167c6540976c1a5df642cc20318a",
        "page_count": 6,
        "pages": {
            1: {
                "utf8_bytes": 328,
                "sha256": "8d9d1b756d9584932d11e817aa3544b5722adb1e78148324774da4b5f5447be9",
                "anchors": (
                    "evaluation board designed and developed",
                    "large-size mini- LVDS interface E-paper displays",
                    "finished motherboard or T-con board",
                ),
            },
            2: {
                "utf8_bytes": 1_184,
                "sha256": "9f1bc068986156fabc86d1453820de2b7791697a3d86ac7dc3a3c4726e2ef569",
                "anchors": (
                    "Based on E Ink T2000 ink screen timing control chip",
                    "Onboard ESP32S3-WROOM-1-N16R8",
                    "six source drive voltages, three gate drive voltages, and three VCOM voltages",
                ),
            },
            3: {
                "utf8_bytes": 697,
                "sha256": "936d3d9f409b76774d3b7b2ed0e5c06147c5b65e7135d5374c8c06999a87c8bf",
                "anchors": (
                    "Package Size 10x10mm QFN104",
                    "Memory Size 256/512 M b with SiP",
                    "I2C up to 1Mbps",
                    "MIPI-DSI 4 lanes",
                ),
            },
            4: {
                "utf8_bytes": 635,
                "sha256": "2a9229e2b1f4c9ac7c18cf5481015f1b1a299714497050bf935248bee4debcc5",
                "anchors": (
                    "powered by a 12V DC interface",
                    "Source Code & Libraries",
                ),
            },
        },
        "facts": {
            "external_tcon_board_demonstrated": True,
            "target_panel_interface": "large-panel mini-LVDS",
            "t2000_package_claim": "10x10 mm QFN104",
            "onboard_host_mcu": "ESP32-S3-WROOM-1-N16R8",
            "onboard_waveform_memory_claim": "256/512 Mbit SiP",
            "onboard_epd_power_and_protection": True,
            "power_input": "12 V DC",
            "host_interfaces": ["USB", "SPI", "MIPI-DSI", "I2C"],
            "software_or_libraries_supplier_claimed": True,
            "public_open_source_or_bare_chip_reference_design_proven": False,
        },
        "scan_runtime_abi_terms": False,
    },
    {
        "id": "MF17506_M009F_T_VENDOR_SPEC",
        "evidence_tier": "vendor-provided module specification",
        "path": MODULE_SPEC_PATH,
        "source_url": None,
        "bytes": 2_189_983,
        "sha256": "c03ef3c34bbf4ece7d280d37197add64c67d0e13c26bff0861a1d399abbed187",
        "page_count": 24,
        "pages": {
            1: {
                "utf8_bytes": 339,
                "sha256": "a09f8278acc2d22100572f4c32b3397a6695a541367dcf59bff6d60271f6d02f",
                "anchors": (
                    "EPD NO: MF-17506-M009F-T",
                    "Module Number M009F-T",
                ),
            },
            4: {
                "utf8_bytes": 1_551,
                "sha256": "02ea58dd5b714e21f6a92d66a06acdd2cf7dd489da2895647f0a0173c43b5d18",
                "anchors": (
                    "1024×600 pixels",
                    "3-bit E6 full display capabilities",
                    "Waveform stored in On-chip OTP",
                    "Serial peripheral interface available",
                ),
            },
            5: {
                "utf8_bytes": 866,
                "sha256": "9f31105dd97bf0d2e9c9bdd6ce23f47c900480f6a422db78d96c994e64423b0a",
                "anchors": ("SPD1657*2ea",),
            },
            10: {
                "utf8_bytes": 709,
                "sha256": "0cc9d1304d9f5616407e2bbc54bf66eda48fc1b2e5d7b298dcc144f85d3cb2d9",
                "anchors": ("Part Name SPD1657B",),
            },
        },
        "facts": {
            "module": "MF-17506-M009F-T / M009F-T / A1",
            "active_area_inches": 7.5,
            "resolution": {"source": 1024, "gate": 600},
            "pixel_input_bits": 3,
            "eink_generation_marking": "E6",
            "integrated_functions": [
                "gate driver",
                "source driver",
                "interface",
                "timing controller",
                "DC-DC",
                "SRAM",
                "LUT",
                "VCOM",
            ],
            "waveform_storage": "on-chip OTP",
            "host_interface": "SPI",
            "documented_driver_topology": "SPD1657 x2",
            "reference_circuit_part_name": "SPD1657B",
        },
        "scan_runtime_abi_terms": False,
    },
)


ANNOUNCEMENT_SPEC: Final[dict[str, Any]] = {
    "id": "EINK_RIPPLE_SECOND_GENERATION_2025",
    "evidence_tier": "first-party E Ink product-architecture announcement",
    "path": PUBLIC_SOURCE_ROOT / "EInk_Ripple_Second_Generation_2025.html",
    "source_url": (
        "https://www.eink.com/news/detail/"
        "E-Ink-Ripple-Second-Generation-Waveform-Architecture-"
        "E%20Ink-Spectra-Displays"
    ),
    "bytes": 58_503,
    "sha256": "333fd4a714049086ff04ed24bca12dc6802c136a5f87f9cf6114228be96f6dfb",
    "normalized_visible_utf8_bytes": 7_692,
    "normalized_visible_sha256": (
        "51b32b88de0fa5b3d95ec51ff28bafa8597fb97383291a0720692cb77d85ffa6"
    ),
    "anchors": (
        "E Ink Introduces E Ink RippleTM and Second-Generation Waveform Architecture for E Ink SpectraTM Displays",
        "newly developed waveform driving architecture",
        "upgraded integrated chipset system to 3-bit processing",
        "eight primary colors",
        "Fitipower, Solomon Systech, Himax Technologies, Novatek, Integrated Solutions Technology, and UltraChip",
        "standalone T2000 controller",
        "include cyan, light green, and orange",
    ),
    "facts": {
        "ripple_is_presented_before_and_separately_from_new_color_mixing_waveform": True,
        "new_waveform_uses_existing_particles_for_color_mixing": True,
        "new_waveform_plus_upgraded_three_bit_chipset_claims_eight_primary_colors": True,
        "compatible_chip_ecosystem_names_solomon_systech": True,
        "standalone_t2000_can_further_expand_color_possibilities": True,
        "t2000_spectra6_new_colors_named": ["cyan", "light green", "orange"],
        "eight_primary_and_t2000_color_statements_are_not_arithmetically_merged": True,
    },
}


PROFILE_INCLUDES: Final[dict[str, dict[str, Any]]] = {
    "WF20_25": {
        "path": REPO_ROOT / "src" / "generated" / "spd1657_wf20_25_empirical_h3.inc",
        "bytes": 13_536,
        "sha256": "8009f2c5523bd4c592474cc15e6b0b4a8b0a74053a09e69d4926d9f5abffb626",
    },
    "WF23_25": {
        "path": REPO_ROOT / "src" / "generated" / "spd1657_wf23_25_empirical_h3.inc",
        "bytes": 13_534,
        "sha256": "ee289bc89e9f76f936ca5f2dd0c503f8cc8c8d786c01fc26615c33b9251cb9ff",
    },
}


class SecondGenerationArchitectureAuditError(RuntimeError):
    """Raised when a pinned input, extractor, or evidence boundary changes."""


class _VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "svg"}:
            self.suppressed_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.suppressed_depth = max(0, self.suppressed_depth - 1)

    def handle_data(self, data: str) -> None:
        if self.suppressed_depth == 0:
            self.parts.append(data)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SecondGenerationArchitectureAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _read_pinned(
    path: Path, *, expected_bytes: int, expected_sha256: str, label: str
) -> bytes:
    _require(path.is_file(), f"missing {label}: {path}")
    payload = path.read_bytes()
    _require(len(payload) == expected_bytes, f"{label} size changed")
    _require(_sha256(payload) == expected_sha256, f"{label} identity changed")
    return payload


def _pdf_evidence(spec: dict[str, Any], pymupdf: Any) -> dict[str, Any]:
    path = Path(spec["path"])
    payload = _read_pinned(
        path,
        expected_bytes=spec["bytes"],
        expected_sha256=spec["sha256"],
        label=spec["id"],
    )
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")
    except Exception as error:  # pragma: no cover - extractor failure path
        raise SecondGenerationArchitectureAuditError(
            f"cannot parse pinned {spec['id']} PDF"
        ) from error
    pages: list[dict[str, Any]] = []
    whole_document_parts: list[str] = []
    try:
        _require(
            document.page_count == spec["page_count"],
            f"{spec['id']} page count changed",
        )
        for page_index in range(document.page_count):
            normalized = _normalize_text(
                document.load_page(page_index).get_text("text")
            )
            whole_document_parts.append(normalized)
            page_number = page_index + 1
            if page_number not in spec["pages"]:
                continue
            page_spec = spec["pages"][page_number]
            encoded = normalized.encode("utf-8")
            _require(
                len(encoded) == page_spec["utf8_bytes"],
                f"{spec['id']} page {page_number} normalized size changed",
            )
            _require(
                _sha256(encoded) == page_spec["sha256"],
                f"{spec['id']} page {page_number} text changed",
            )
            missing = [
                anchor for anchor in page_spec["anchors"] if anchor not in normalized
            ]
            _require(
                not missing,
                f"{spec['id']} page {page_number} lost anchors: {missing}",
            )
            pages.append(
                {
                    "pdf_page_1_based": page_number,
                    "normalized_text_utf8_bytes": len(encoded),
                    "normalized_text_sha256": _sha256(encoded),
                    "required_anchor_count": len(page_spec["anchors"]),
                    "all_required_anchors_present": True,
                    "page_text_emitted": False,
                }
            )
    finally:
        document.close()

    whole_document = " ".join(whole_document_parts)
    term_presence = (
        {term: term in whole_document for term in RUNTIME_ABI_TERMS}
        if spec["scan_runtime_abi_terms"]
        else None
    )
    evidence = {
        "id": spec["id"],
        "evidence_tier": spec["evidence_tier"],
        "path": _relative(path),
        "source_url": spec["source_url"],
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "page_count": spec["page_count"],
        "pages": pages,
        "facts": spec["facts"],
        "facts_canonical_sha256": _sha256(_canonical_bytes(spec["facts"])),
        "runtime_abi_term_presence": term_presence,
        "raw_pdf_or_full_page_text_emitted": False,
    }
    if "download_url" in spec:
        evidence["download_url"] = spec["download_url"]
    return evidence


def _announcement_evidence() -> dict[str, Any]:
    spec = ANNOUNCEMENT_SPEC
    path = Path(spec["path"])
    payload = _read_pinned(
        path,
        expected_bytes=spec["bytes"],
        expected_sha256=spec["sha256"],
        label=spec["id"],
    )
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SecondGenerationArchitectureAuditError(
            "cannot decode pinned E Ink announcement as UTF-8"
        ) from error
    extractor = _VisibleTextExtractor()
    extractor.feed(decoded)
    extractor.close()
    normalized = _normalize_text(" ".join(extractor.parts))
    encoded = normalized.encode("utf-8")
    _require(
        len(encoded) == spec["normalized_visible_utf8_bytes"],
        "E Ink announcement normalized size changed",
    )
    _require(
        _sha256(encoded) == spec["normalized_visible_sha256"],
        "E Ink announcement normalized text changed",
    )
    missing = [anchor for anchor in spec["anchors"] if anchor not in normalized]
    _require(not missing, f"E Ink announcement lost anchors: {missing}")
    term_presence = {term: term in normalized for term in RUNTIME_ABI_TERMS}
    return {
        "id": spec["id"],
        "evidence_tier": spec["evidence_tier"],
        "path": _relative(path),
        "source_url": spec["source_url"],
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "normalized_visible_utf8_bytes": len(encoded),
        "normalized_visible_sha256": _sha256(encoded),
        "required_anchor_count": len(spec["anchors"]),
        "all_required_anchors_present": True,
        "facts": spec["facts"],
        "facts_canonical_sha256": _sha256(_canonical_bytes(spec["facts"])),
        "runtime_abi_term_presence": term_presence,
        "raw_html_or_visible_text_emitted": False,
    }


def _profile_evidence() -> dict[str, Any]:
    materials = {
        profile_id: profile_pack.load_profile(profile_id)
        for profile_id in sorted(PROFILE_INCLUDES)
    }
    body_bytes = (
        STRUCTURAL_BLOCKS * STRUCTURAL_RECORDS_PER_BLOCK * STRUCTURAL_RECORD_BYTES
    )
    _require(
        OPAQUE_PREFIX_BYTES + body_bytes + OPAQUE_SUFFIX_BYTES == PROFILE_BYTES,
        "local structural arithmetic changed",
    )
    profiles: dict[str, Any] = {}
    for profile_id, material in materials.items():
        include_spec = PROFILE_INCLUDES[profile_id]
        include_path = Path(include_spec["path"])
        include_payload = _read_pinned(
            include_path,
            expected_bytes=include_spec["bytes"],
            expected_sha256=include_spec["sha256"],
            label=f"{profile_id} generated include",
        )
        _require(len(material.plaintext) == PROFILE_BYTES, f"{profile_id} size changed")
        _require(
            _sha256(material.plaintext) == material.spec.plaintext_sha256,
            f"{profile_id} decoded identity changed",
        )
        _require(
            len(material.r20) == CANDIDATE_R20_BYTES,
            f"{profile_id} candidate R20 length changed",
        )
        _require(
            _sha256(material.r20) == material.spec.r20_sha256,
            f"{profile_id} candidate R20 identity changed",
        )
        _require(
            "E5 2-bit DEvelopment Environment" in material.spec.required_source_markers,
            f"{profile_id} source marker changed",
        )
        profiles[profile_id] = {
            "source_path": material.spec.source_relative.as_posix(),
            "source_bytes": material.source_bytes,
            "source_sha256": material.spec.source_sha256,
            "wrapper_bytes": material.spec.wrapper_bytes,
            "wrapper_sha256": material.spec.wrapper_sha256,
            "decoded_bytes": len(material.plaintext),
            "decoded_sha256": material.spec.plaintext_sha256,
            "candidate_r20_bytes": len(material.r20),
            "candidate_r20_sha256": material.spec.r20_sha256,
            "generated_include_path": _relative(include_path),
            "generated_include_bytes": len(include_payload),
            "generated_include_sha256": _sha256(include_payload),
            "source_declares_e5_two_bit_development_environment": True,
            "raw_profile_wrapper_plaintext_or_include_bytes_emitted": False,
        }

    wf20 = materials["WF20_25"].plaintext
    wf23 = materials["WF23_25"].plaintext
    differing_positions = sum(left != right for left, right in zip(wf20, wf23))
    _require(differing_positions == 357, "WF20/WF23 positional delta changed")
    constructed_r21 = b"\xff" * CONSTRUCTED_R21_BYTES
    _require(
        _sha256(constructed_r21) == CONSTRUCTED_R21_SHA256,
        "constructed R21 identity changed",
    )
    return {
        "profiles": profiles,
        "shared_geometry": {
            "decoded_bytes": PROFILE_BYTES,
            "opaque_prefix_bytes": OPAQUE_PREFIX_BYTES,
            "structural_block_count": STRUCTURAL_BLOCKS,
            "records_per_structural_block": STRUCTURAL_RECORDS_PER_BLOCK,
            "structural_record_bytes": STRUCTURAL_RECORD_BYTES,
            "structural_body_bytes": body_bytes,
            "opaque_suffix_bytes": OPAQUE_SUFFIX_BYTES,
            "arithmetic": "7 + 9 * 8 * 11 + 1 = 800",
            "candidate_r20_bytes": CANDIDATE_R20_BYTES,
            "constructed_r21_bytes": CONSTRUCTED_R21_BYTES,
            "constructed_r21_sha256": CONSTRUCTED_R21_SHA256,
            "constructed_r21_is_vendor_profile_bytes": False,
            "raw_values_emitted": False,
        },
        "wf20_wf23_positional_byte_differences": differing_positions,
        "profile_filename_numeric_tokens_have_proven_temperature_semantics": False,
        "block_or_record_color_phase_or_electrical_semantics_assigned": False,
    }


def _legacy_library_evidence() -> dict[str, Any]:
    payload = _read_pinned(
        E2802_LIBRARY_PATH,
        expected_bytes=65_082,
        expected_sha256="f6862110533d94b4b0bbc6a864d7b0c936c7402bb83dbd6fc425f0967c8ff06b",
        label="archived E2802 ArmCC library",
    )
    marker_presence = {
        "E5_3Bit_Mode 0": b"E5_3Bit_Mode 0" in payload,
        "WF_DeCode_SIZE 544": b"WF_DeCode_SIZE 544" in payload,
        "WF_SIZE 535": b"WF_SIZE 535" in payload,
        "E5_3Bit_Mode 1": b"E5_3Bit_Mode 1" in payload,
    }
    _require(marker_presence["E5_3Bit_Mode 0"], "mode-0 marker disappeared")
    _require(
        marker_presence["WF_DeCode_SIZE 544"], "544 decode-size marker disappeared"
    )
    _require(marker_presence["WF_SIZE 535"], "535 waveform-size marker disappeared")
    _require(not marker_presence["E5_3Bit_Mode 1"], "unexpected mode-1 marker appeared")
    return {
        "path": _relative(E2802_LIBRARY_PATH),
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "ascii_marker_presence": marker_presence,
        "active_marker_projection": {
            "E5_3Bit_Mode": 0,
            "WF_DeCode_SIZE": 544,
            "WF_SIZE": 535,
        },
        "mode_1_or_800_byte_loader_bound_by_these_markers": False,
        "incidental_untyped_decimal_occurrences_interpreted_as_abi": False,
        "raw_library_or_object_bytes_emitted": False,
    }


def build_report() -> dict[str, Any]:
    """Build a deterministic, metadata-only architecture-boundary report."""

    try:
        import pymupdf
    except ImportError as error:  # pragma: no cover - environment failure path
        raise SecondGenerationArchitectureAuditError(
            "PyMuPDF is required for pinned primary-document extraction"
        ) from error
    _require(
        str(getattr(pymupdf, "__version__", "unknown")) == PYMUPDF_VERSION,
        "PyMuPDF version changed; revalidate pinned page extraction",
    )

    documents = [_pdf_evidence(spec, pymupdf) for spec in PDF_DOCUMENTS]
    by_id = {document["id"]: document for document in documents}
    announcement = _announcement_evidence()
    profiles = _profile_evidence()
    legacy_library = _legacy_library_evidence()
    official_t2000_ids = ("EINK_HIMAX_T2000_2024", "HIMAX_T2000_2026")
    official_term_presence = {
        identity: by_id[identity]["runtime_abi_term_presence"]
        for identity in official_t2000_ids
    }
    _require(
        not any(
            found
            for term_map in official_term_presence.values()
            for found in term_map.values()
        ),
        "a pinned official T2000 source gained a selected runtime-ABI term",
    )
    _require(
        not any(announcement["runtime_abi_term_presence"].values()),
        "the pinned E Ink architecture announcement gained a selected ABI term",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_second_generation_architecture_and_local_abi_boundary",
        "extractor": {
            "pdf": {"name": "PyMuPDF", "version": PYMUPDF_VERSION},
            "html": {"name": "Python HTMLParser visible-text projection"},
            "network_accessed_by_offline_audit": False,
        },
        "documents": documents,
        "eink_second_generation_announcement": announcement,
        "local_vendor_profiles": profiles,
        "archived_e2802_library": legacy_library,
        "architecture_findings": {
            "t2000_hardware_asic_confirmed_by_first_party": True,
            "t2000_role": "timing controller between host data/control inputs and panel-side mLVDS/TTL",
            "t2000_is_controller_silicon_not_electrophoretic_film": True,
            "external_t2000_pcb_implementation_demonstrated_by_supplier": True,
            "external_board_contains_t2000_memory_host_mcu_epd_power_and_protection": True,
            "current_module_documented_path": (
                "host SPI -> integrated dual SPD1657/SPD1657B module -> panel"
            ),
            "t2000_reference_path": (
                "host MIPI/USB/SPI/control -> T2000 plus memory/power -> mini-LVDS/TTL panel path"
            ),
            "documented_current_module_reference_design_contains_t2000": False,
            "absolute_as_built_t2000_absence_proven": False,
            "documented_drop_in_t2000_compatibility_with_current_spi_module": False,
            "bare_t2000_chip_diy_possible_in_principle": True,
            "complete_public_bare_chip_design_package_proven": False,
            "required_for_practical_t2000_path": [
                "obtainable T2000 board or qualified chip channel",
                "matching raw mini-LVDS/TTL Spectra panel",
                "panel-specific power and timing specification",
                "vendor firmware, color algorithm, waveform package, and applicable license",
            ],
        },
        "second_generation_to_local_abi_adjudication": {
            "second_generation_three_bit_color_mixing_architecture_public": True,
            "solomon_systech_named_as_compatible_chip_ecosystem_member": True,
            "announcement_names_spd1657": False,
            "announcement_names_e2802": False,
            "official_t2000_documents_selected_runtime_abi_term_presence": official_term_presence,
            "official_t2000_runtime_waveform_write_abi_disclosed_in_pinned_sources": False,
            "local_module_three_bit_input_proves_second_generation_waveform": False,
            "local_profile_800_byte_length_proves_second_generation_waveform": False,
            "nine_local_structural_blocks_map_to_eight_primary_colors": False,
            "nine_local_structural_blocks_map_to_one_plus_eight_categories": False,
            "wf20_or_wf23_proven_t2000_profile": False,
            "wf20_or_wf23_proven_spd1657_second_generation_profile": False,
            "archived_mode_0_535_marker_closes_mode_1_800_loader": False,
            "eight_primary_statement_and_t2000_three_named_colors_may_be_added": False,
            "category_order_recovered": False,
            "eleven_byte_record_field_layout_recovered": False,
            "phase_repeat_level_duration_or_voltage_fields_recovered": False,
            "controller_side_decode_recovered": False,
            "dual_controller_load_commit_or_rollback_recovered": False,
            "runtime_to_otp_recovery_contract_recovered": False,
            "strongest_positive_conclusion": (
                "second-generation waveform color mixing and an external T2000 TCON are real "
                "product architectures, but the pinned public sources do not bind that "
                "architecture to SPD1657/E2802, the local 800-byte envelope, or its 11-byte records"
            ),
        },
        "safe_path_decision": {
            "current_mf1750_path": (
                "continue identity-preserved WF20/WF23 matched-control experiments and "
                "same-version SPD1657/E2802 ABI recovery; do not splice or name fields"
            ),
            "separate_t2000_path": (
                "start with a supplier-supported T2000 TCON board plus an explicitly "
                "compatible raw panel and vendor waveform/software package, not a bare-chip PCB"
            ),
            "t2000_route_is_add_on_to_current_dual_spd1657_module": False,
            "runtime_payload_or_live_test_authorized_by_this_audit": False,
        },
        "material_handling": {
            "pdf_and_html_text_extracted_in_memory": True,
            "document_text_or_raw_documents_emitted": False,
            "profile_plaintext_or_waveform_bytes_emitted": False,
            "runtime_payload_include_or_firmware_generated": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_com_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
            "runtime_payload_generated_or_modified": False,
            "profile_hybrid_or_splice_generated": False,
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
        SecondGenerationArchitectureAuditError,
        profile_pack.ProfilePackError,
        DurableWriteError,
        OSError,
        UnicodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
