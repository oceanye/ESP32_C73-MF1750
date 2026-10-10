from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest import mock

from tools import mf1750_spd1657_wrapper_alignment_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CANONICAL_SHA256 = (
    "69832c37a0cb043078401955bc834dbca60de9c3550bb2b7a7bd8047e36ca7c8"
)


def test_exact_block_alignment_relations_do_not_promote_padding_semantics() -> None:
    report = audit.build_report()
    mode0 = report["known_mode0_loader"]
    assert mode0["exact_equation"] == "544 = ceil(535/16)*16 = 535 + 9"
    assert mode0["decoded_ciphertext_bytes"] == 544
    assert mode0["forwarded_R20_bytes"] == 535
    assert mode0["unforwarded_decoded_suffix_bytes"] == 9
    assert mode0["decoded_is_minimal_AES_multiple_for_forwarded_R20"] is True
    assert mode0["matching_mode0_wrapper_supplied_to_this_audit"] is False
    assert mode0["matching_mode0_wrapper_global_absence_proven_by_this_audit"] is False
    assert (
        mode0["unforwarded_suffix_values_observed_from_supplied_mode0_wrapper"] is False
    )
    assert mode0["plaintext_padding_checked_by_loader"] is False
    assert mode0["unforwarded_suffix_named_as_padding_by_loader"] is False

    cross = report["cross_mode_alignment"]
    assert cross["mode1_candidate_equation"] == "800 = ceil(799/16)*16 = 799 + 1"
    assert cross[
        "both_decoded_sizes_are_minimal_block_roundups_of_mode0_forwarded_and_mode1_candidate_lengths"
    ]
    assert cross["known_mode0_loader_forwards_only_logical_prefix"]
    assert cross["mode1_candidate_geometries_share_one_zero_outer_byte"]
    assert cross["mode1_candidate_outer_byte_is_AES_zero_fill_compatible"]
    assert cross["same_build_mode1_loader_or_generator_proves_padding"] is False
    assert cross["mode1_799_candidate_length_is_cross_generation_H3"] is True

    decision = report["adjudication"]
    assert (
        decision["candidate_outer_byte_role"]
        == "UNRESOLVED_AES_BLOCK_ALIGNMENT_COMPATIBLE"
    )
    assert decision["candidate_outer_byte_is_encryption_padding_proven"] is False
    assert decision["candidate_outer_byte_is_controller_terminator_proven"] is False
    assert decision["candidate_outer_byte_is_checksum_proven"] is False
    assert decision["same_version_799_byte_loader_proven"] is False
    assert (
        decision["matching_mode0_wrapper_global_absence_proven_by_this_audit"] is False
    )
    assert decision["H3_evidence_grade_changed"] is False


def test_two_profiles_are_pinned_without_raw_material() -> None:
    report = audit.build_report()
    profiles = report["vendor_mode1_profiles"]
    assert set(profiles) == {"WF20_25", "WF23_25"}
    assert {row["wrapper_bytes"] for row in profiles.values()} == {842, 876}
    assert {row["wrapped_key_bytes"] for row in profiles.values()} == {40, 74}
    for row in profiles.values():
        assert row["ciphertext_bytes"] == 800
        assert row["ciphertext_is_whole_AES_blocks"] is True
        assert row["candidate_first799_bytes"] == 799
        assert row["candidate_outer_byte_count"] == 1
        assert row["candidate_outer_byte_is_zero"] is True
        assert row["candidate_outer_byte_outside_7_plus_9x8x11_geometry"] is True
        assert row["raw_wrapper_key_plaintext_or_waveform_bytes_emitted"] is False
        for key in (
            "source_artifact_sha256",
            "wrapper_sha256",
            "decoded_sha256",
            "candidate_first799_sha256",
        ):
            assert len(row[key]) == 64
    assert profiles["WF20_25"]["external_key_source_path"] == "Sample Code/E28xx.c"
    assert len(profiles["WF20_25"]["external_key_source_sha256"]) == 64
    assert profiles["WF20_25"]["external_key_source_identity_pinned"] is True
    assert profiles["WF20_25"]["recovered_key_identity_pinned_by_hash"] is False
    assert profiles["WF23_25"]["external_key_source_path"] is None
    assert profiles["WF23_25"]["external_key_source_sha256"] is None
    assert profiles["WF23_25"]["external_key_source_identity_pinned"] is False
    assert profiles["WF23_25"]["recovered_key_identity_pinned_by_hash"] is True


def test_build_cannot_enter_profile_render_or_write_paths() -> None:
    with (
        mock.patch.object(
            audit.profile_pack,
            "render_include",
            side_effect=AssertionError("render path must remain unreachable"),
        ),
        mock.patch.object(
            audit.profile_pack,
            "write_include",
            side_effect=AssertionError("write path must remain unreachable"),
        ),
    ):
        report = audit.build_report()
    handling = report["material_handling"]
    assert handling["existing_vendor_profiles_decrypted_in_memory"] is True
    assert handling["profile_pack_render_or_write_path_called"] is False
    assert handling["raw_key_plaintext_waveform_or_payload_emitted"] is False
    assert handling["raw_key_plaintext_waveform_or_payload_written"] is False
    assert handling["include_firmware_or_release_generated"] is False
    assert (
        handling["dependency_legacy_padding_or_sentinel_names_are_semantic_evidence"]
        is False
    )


def test_report_is_deterministic_metadata_only_and_cli_reproduces_it(
    tmp_path: Path,
) -> None:
    report = audit.build_report()
    assert report["schema_version"] == 1
    assert report["scope"] == "offline_identity_pinned_metadata_only"
    assert report["integrity"]["canonical_sha256"] == EXPECTED_CANONICAL_SHA256
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in (
        '"raw_key"',
        '"key_bytes"',
        '"plaintext_bytes"',
        '"waveform_bytes"',
        '"payload_bytes"',
        '"authorization_token"',
    ):
        assert forbidden not in serialized

    output = tmp_path / "alignment.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.mf1750_spd1657_wrapper_alignment_audit",
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_safety_contract_is_explicit() -> None:
    safety = audit.build_report()["safety"]
    assert safety == {
        "offline_only": True,
        "hardware_accessed": False,
        "serial_or_COM8_accessed": False,
        "device_network_accessed": False,
        "firmware_or_flash_written": False,
        "display_refresh_attempted": False,
        "authorization_token_generated_or_claimed": False,
        "vendor_evidence_modified": False,
    }


def test_checked_in_report_matches_builder() -> None:
    path = (
        REPO_ROOT
        / ".test-output/offline/mf1750_spd1657_wrapper_alignment_audit_20260812.json"
    )
    assert path.is_file()
    payload = path.read_bytes()
    assert json.loads(payload.decode("utf-8")) == audit.build_report()
    assert payload.endswith(b"\n")
    assert (
        hashlib.sha256(payload).hexdigest()
        == "0795b79ee6c29a1d987c233c311a124e81c72bbd04e2f17b3d4d15b6eb643534"
    )
