#!/usr/bin/env python3
"""Audit AES-block alignment around the 535/544 and 799/800 boundaries.

This offline, metadata-only audit combines the identity-pinned ArmCC mode-0
loader with the two already-supported vendor wrapper profiles.  It establishes
which bytes are consumed by AES-CBC and which bytes are forwarded by the known
loader, but deliberately does not name an unconsumed byte as padding, a
sentinel, a checksum, or a controller terminator without a matching generator
or same-build mode-1 loader.

No key, plaintext, waveform record, payload, firmware, release, authorization,
hardware, serial, or device-network material is emitted or created.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Final

from host.application.durable_io import DurableWriteError, write_new_bytes_durable
from tools import mf1750_armcc_loadwf_deep_audit as armcc
from tools import mf1750_spd1657_vendor_profile_pack as profile_pack


KIND: Final = "mf1750-spd1657-wrapper-alignment-audit"
SCHEMA_VERSION: Final = 1
AES_BLOCK_BYTES: Final = 16
MODE0_DECODED_BYTES: Final = 544
MODE0_FORWARDED_R20_BYTES: Final = 535
MODE1_DECODED_BYTES: Final = 800
MODE1_H3_CANDIDATE_R20_BYTES: Final = 799


class WrapperAlignmentAuditError(RuntimeError):
    """Raised when a pinned input or structural invariant changes."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WrapperAlignmentAuditError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_bytes(report: dict[str, Any]) -> bytes:
    return json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _round_up(value: int, quantum: int) -> int:
    _require(value >= 0, "alignment value must be non-negative")
    _require(quantum > 0, "alignment quantum must be positive")
    return ((value + quantum - 1) // quantum) * quantum


def _macro_values(report: dict[str, Any]) -> dict[str, str]:
    return {
        str(row["name"]): str(row["value"])
        for row in report["compiler_and_macros"]["source_macro_records"]
    }


def _transaction_by_command(report: dict[str, Any], command: str) -> dict[str, Any]:
    matches = [
        row
        for row in report["loadwf"]["success_transactions"]
        if row["command"] == command
    ]
    _require(len(matches) == 1, f"expected one {command} transaction")
    return matches[0]


def build_report() -> dict[str, Any]:
    """Build a deterministic report without exposing decrypted bytes."""

    armcc_report = armcc.build_report()
    macros = _macro_values(armcc_report)
    _require(macros.get("AES_BLOCKLEN") == "16", "AES block macro changed")
    _require(
        macros.get("WF_DeCode_SIZE") == str(MODE0_DECODED_BYTES),
        "mode-0 decoded size changed",
    )
    _require(
        macros.get("WF_SIZE") == str(MODE0_FORWARDED_R20_BYTES),
        "mode-0 forwarded waveform size changed",
    )
    mode0_r20 = _transaction_by_command(armcc_report, "0x20")
    _require(
        mode0_r20["parameter_bytes"] == MODE0_FORWARDED_R20_BYTES
        and mode0_r20["pointer"] == "in"
        and mode0_r20["source"] == "decoded in[0..534]",
        "mode-0 R20 source contract changed",
    )
    wrapper_contract = armcc_report["decrypt_gate"]["wrapper_contract"]
    _require(
        wrapper_contract["fixed_ciphertext_copy_bytes"] == MODE0_DECODED_BYTES,
        "mode-0 ciphertext copy size changed",
    )
    _require(
        armcc_report["decrypt_gate"]["padding_checked"] is False,
        "mode-0 loader unexpectedly acquired a padding check",
    )

    mode0_slack = MODE0_DECODED_BYTES - MODE0_FORWARDED_R20_BYTES
    _require(mode0_slack == 9, "mode-0 AES alignment slack changed")
    _require(
        _round_up(MODE0_FORWARDED_R20_BYTES, AES_BLOCK_BYTES) == MODE0_DECODED_BYTES,
        "mode-0 decoded size is no longer the minimal AES block multiple",
    )

    profile_rows: dict[str, dict[str, Any]] = {}
    for profile_id in sorted(profile_pack.PROFILES):
        material = profile_pack.load_profile(profile_id)
        plaintext = material.plaintext
        spec = material.spec
        _require(len(plaintext) == MODE1_DECODED_BYTES, "profile decoded size changed")
        _require(
            len(plaintext[:MODE1_H3_CANDIDATE_R20_BYTES])
            == MODE1_H3_CANDIDATE_R20_BYTES,
            "profile candidate R20 extent changed",
        )
        suffix = plaintext[MODE1_H3_CANDIDATE_R20_BYTES:]
        _require(len(suffix) == 1, "profile candidate outer-byte extent changed")
        _require(suffix == b"\x00", "profile candidate outer-byte value changed")
        profile_rows[profile_id] = {
            "source_artifact_sha256": spec.source_sha256,
            "external_key_source_path": (
                None
                if spec.external_key_source_relative is None
                else spec.external_key_source_relative.as_posix()
            ),
            "external_key_source_sha256": spec.external_key_source_sha256,
            "external_key_source_identity_pinned": (
                spec.external_key_source_relative is not None
                and spec.external_key_source_sha256 is not None
            ),
            "recovered_key_identity_pinned_by_hash": (
                spec.recovered_key_sha256 is not None
            ),
            "wrapper_sha256": material.wrapper_sha256,
            "wrapper_bytes": spec.wrapper_bytes,
            "ciphertext_bytes": MODE1_DECODED_BYTES,
            "ciphertext_is_whole_AES_blocks": (
                MODE1_DECODED_BYTES % AES_BLOCK_BYTES == 0
            ),
            "wrapped_key_bytes": spec.wrapped_key_bytes,
            "decoded_sha256": spec.plaintext_sha256,
            "candidate_first799_sha256": spec.r20_sha256,
            "candidate_first799_bytes": MODE1_H3_CANDIDATE_R20_BYTES,
            "candidate_outer_byte_count": len(suffix),
            "candidate_outer_byte_is_zero": suffix == b"\x00",
            "candidate_outer_byte_outside_7_plus_9x8x11_geometry": True,
            "raw_wrapper_key_plaintext_or_waveform_bytes_emitted": False,
        }

    mode1_slack = MODE1_DECODED_BYTES - MODE1_H3_CANDIDATE_R20_BYTES
    _require(mode1_slack == 1, "mode-1 candidate AES alignment slack changed")
    _require(
        _round_up(MODE1_H3_CANDIDATE_R20_BYTES, AES_BLOCK_BYTES) == MODE1_DECODED_BYTES,
        "mode-1 decoded size is no longer the minimal AES block multiple",
    )

    report: dict[str, Any] = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "scope": "offline_identity_pinned_metadata_only",
        "known_mode0_loader": {
            "library_sha256": armcc_report["archive"]["sha256"],
            "object_sha256": armcc_report["archive"]["object"]["sha256"],
            "compile_mode": int(macros["E5_3Bit_Mode"]),
            "aes_block_bytes": int(macros["AES_BLOCKLEN"]),
            "decoded_ciphertext_bytes": MODE0_DECODED_BYTES,
            "forwarded_R20_bytes": MODE0_FORWARDED_R20_BYTES,
            "unforwarded_decoded_suffix_bytes": mode0_slack,
            "decoded_is_minimal_AES_multiple_for_forwarded_R20": True,
            "exact_equation": "544 = ceil(535/16)*16 = 535 + 9",
            "unforwarded_suffix_values_observed_from_supplied_mode0_wrapper": False,
            "matching_mode0_wrapper_supplied_to_this_audit": False,
            "matching_mode0_wrapper_global_absence_proven_by_this_audit": False,
            "plaintext_padding_checked_by_loader": False,
            "plaintext_format_checked_by_loader": False,
            "unforwarded_suffix_named_as_padding_by_loader": False,
        },
        "vendor_mode1_profiles": profile_rows,
        "cross_mode_alignment": {
            "mode0_exact_equation": "544 = ceil(535/16)*16 = 535 + 9",
            "mode1_candidate_equation": "800 = ceil(799/16)*16 = 799 + 1",
            "both_decoded_sizes_are_AES_block_multiples": True,
            "mode0_forwarded_and_mode1_candidate_lengths_are_not_AES_block_multiples": True,
            "both_decoded_sizes_are_minimal_block_roundups_of_mode0_forwarded_and_mode1_candidate_lengths": True,
            "known_mode0_loader_forwards_only_logical_prefix": True,
            "mode1_candidate_geometries_share_one_zero_outer_byte": True,
            "mode1_candidate_outer_byte_is_AES_zero_fill_compatible": True,
            "same_build_mode1_loader_or_generator_proves_padding": False,
            "mode1_799_candidate_length_is_cross_generation_H3": True,
        },
        "adjudication": {
            "new_bounded_fact": (
                "535->544 and candidate 799->800 are both exact minimal 16-byte "
                "AES-CBC roundups; the known mode-0 loader forwards only its 535-byte "
                "prefix, while both mode-1 candidate geometries have a one-byte zero "
                "candidate outer byte"
            ),
            "candidate_outer_byte_role": "UNRESOLVED_AES_BLOCK_ALIGNMENT_COMPATIBLE",
            "candidate_outer_byte_is_encryption_padding_proven": False,
            "candidate_outer_byte_is_controller_terminator_proven": False,
            "candidate_outer_byte_is_checksum_proven": False,
            "same_version_799_byte_loader_proven": False,
            "matching_mode0_wrapper_global_absence_proven_by_this_audit": False,
            "H3_evidence_grade_changed": False,
            "safe_use": (
                "retain decoded[0:799] only as the pinned empirical H3 candidate; "
                "do not transmit or interpret decoded[799] without a same-build loader"
            ),
            "next_direct_evidence_needed": [
                "matching mode-0 wrapper or waveform generator showing its outer-byte construction",
                "same-build E5_3Bit_Mode=1 loader proving its decoded and forwarded extents",
                "vendor wrapper-format documentation naming the candidate outer byte",
            ],
        },
        "material_handling": {
            "existing_vendor_profiles_decrypted_in_memory": True,
            "profile_pack_render_or_write_path_called": False,
            "raw_key_plaintext_waveform_or_payload_emitted": False,
            "raw_key_plaintext_waveform_or_payload_written": False,
            "include_firmware_or_release_generated": False,
            "dependency_legacy_padding_or_sentinel_names_are_semantic_evidence": False,
        },
        "safety": {
            "offline_only": True,
            "hardware_accessed": False,
            "serial_or_COM8_accessed": False,
            "device_network_accessed": False,
            "firmware_or_flash_written": False,
            "display_refresh_attempted": False,
            "authorization_token_generated_or_claimed": False,
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
        WrapperAlignmentAuditError,
        armcc.DeepAuditError,
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
