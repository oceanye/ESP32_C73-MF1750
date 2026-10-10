from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from host.runtime_waveform import contracts
from host.runtime_waveform import virtual_palette


CREATED_AT = "2026-08-09T23:30:00+08:00"


def _template() -> dict:
    return contracts.build_reference_blocked_candidate(created_at=CREATED_AT)


def _reviewed_payload() -> bytes:
    return bytes(range(256)) * 3


def _ready_candidate(payload: bytes) -> dict:
    candidate = _template()
    candidate["profile_id"] = "reviewed-dual-controller-3bit-v1"
    candidate["panel"]["batch_id"] = "reviewed-batch"
    candidate["panel"]["controller_revision"] = "reviewed-revision"
    candidate["payload"] = {
        "representation": "plaintext_decoded_3bit_lut",
        "format_id": "reviewed-3bit-layout-v1",
        "format_document_sha256": "1" * 64,
        "controller_payloads": [
            {
                "controller": "CS1",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            {
                "controller": "CS2",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        ],
    }
    candidate["electrical"] = {
        "temperature_min_c": 20.0,
        "temperature_max_c": 25.0,
        "vcom_mv": -2000.0,
        "vgh_mv": 20_000.0,
        "vgl_mv": -20_000.0,
        "vsh_mv": 15_000.0,
        "vsl_mv": -15_000.0,
        "frame_rate_hz": 50.0,
        "phase_timing_documented": True,
    }
    candidate["provenance"] = {
        "reference_artifact_sha256": "2" * 64,
        "source_payload_sha256": hashlib.sha256(payload).hexdigest(),
        "loader_source_sha256": "3" * 64,
        "vendor_or_panel_owner_review_id": "review-001",
        "source_is_current_panel_3bit": True,
    }
    candidate["recovery"] = {
        "known_good_profile_sha256": "4" * 64,
        "white_recovery_contract_sha256": "5" * 64,
        "restore_otp_mode_without_programming": True,
        "validated_on_sacrificial_panel": True,
    }
    candidate["qualification_gates"] = {name: True for name in contracts.GATE_NAMES}
    return candidate


def test_reference_template_is_valid_but_hard_blocked() -> None:
    candidate = _template()
    report = contracts.evaluate_candidate(candidate)
    assert report["valid"] is True
    assert report["offline_contract_complete"] is False
    assert report["execution_ready"] is False
    assert report["classification"] == contracts.BLOCKED_CLASSIFICATION
    assert "decoded_3bit_payload_missing" in report["blocker_codes"]
    assert "gate_false:dual_controller_3bit_format_documented" in report[
        "blocker_codes"
    ]
    assert report["hardware_io_performed"] is False
    assert report["visible_refresh_authorized"] is False


def test_channel_model_distinguishes_palette_states_from_rgb_channels() -> None:
    candidate = _template()
    encoding = candidate["encoding"]
    assert encoding["transport_codes"] == list(range(8))
    assert encoding["formal_codes"] == [0, 1, 2, 3, 5, 6]
    assert encoding["experimental_codes"] == [4, 7]
    assert (
        encoding["channel_model"]
        == "indexed_particle_target_states_not_independent_rgb_channels"
    )


def test_exact_dual_payload_identity_can_complete_only_manifest_contract() -> None:
    payload = _reviewed_payload()
    candidate = _ready_candidate(payload)
    report = contracts.evaluate_candidate(
        candidate, controller_payload_bytes={"CS1": payload, "CS2": payload}
    )
    assert report["manifest_contract_complete"] is True
    assert report["offline_contract_complete"] is False
    assert report["offline_blocker_codes"] == ["deep_evidence_bundle_not_supplied"]
    assert report["execution_ready"] is False
    assert report["blocker_codes"] == [
        "deep_evidence_bundle_not_supplied",
        contracts.HARDWARE_EXECUTION_BLOCKER,
    ]
    assert report["hardware_execution_blocker_codes"] == [
        contracts.HARDWARE_EXECUTION_BLOCKER
    ]
    assert report["qualification_gates_are_candidate_attestations"] is True
    assert report["visible_refresh_authorized"] is False
    assert report["classification"] == contracts.BLOCKED_CLASSIFICATION


def test_payload_tampering_is_a_stable_blocker() -> None:
    payload = _reviewed_payload()
    candidate = _ready_candidate(payload)
    report = contracts.evaluate_candidate(
        candidate,
        controller_payload_bytes={"CS1": payload, "CS2": payload + b"tampered"},
    )
    assert report["execution_ready"] is False
    assert "cs2_payload_identity_mismatch" in report["blocker_codes"]


def test_one_controller_payload_is_rejected() -> None:
    payload = _reviewed_payload()
    candidate = _ready_candidate(payload)
    report = contracts.evaluate_candidate(
        candidate, controller_payload_bytes={"CS1": payload}
    )
    assert report["execution_ready"] is False
    assert "both_controller_payload_bytes_not_supplied" in report["blocker_codes"]


def test_one_byte_payload_cannot_complete_offline_contract() -> None:
    payload = b"x"
    candidate = _ready_candidate(payload)
    report = contracts.evaluate_candidate(
        candidate, controller_payload_bytes={"CS1": payload, "CS2": payload}
    )
    assert report["offline_contract_complete"] is False
    assert report["execution_ready"] is False
    assert "cs1_payload_too_short" in report["offline_blocker_codes"]
    assert "cs2_payload_too_short" in report["offline_blocker_codes"]


def test_required_e9_and_20_commands_are_offline_blockers() -> None:
    payload = _reviewed_payload()
    candidate = _ready_candidate(payload)
    candidate["operation_contract"]["commands"] = []
    report = contracts.evaluate_candidate(
        candidate, controller_payload_bytes={"CS1": payload, "CS2": payload}
    )
    assert report["offline_contract_complete"] is False
    assert "required_runtime_opcode_missing:0x20" in report["offline_blocker_codes"]
    assert "required_runtime_opcode_missing:0xe9" in report["offline_blocker_codes"]


def test_otp_or_nonvolatile_command_is_structurally_forbidden() -> None:
    candidate = _template()
    candidate["operation_contract"]["commands"].append(
        {"name": "otp_program", "opcode": 165, "purpose": "program_nonvolatile"}
    )
    with pytest.raises(contracts.RuntimeWaveformContractError, match="forbidden"):
        contracts.validate_candidate(candidate)


def test_unknown_opcode_with_harmless_name_is_structurally_forbidden() -> None:
    candidate = _template()
    candidate["operation_contract"]["commands"].append(
        {"name": "status_check", "opcode": 165, "purpose": "read_status"}
    )
    with pytest.raises(contracts.RuntimeWaveformContractError, match="allowlist"):
        contracts.validate_candidate(candidate)


def test_allowed_opcode_cannot_be_renamed_to_change_its_semantics() -> None:
    candidate = _template()
    candidate["operation_contract"]["commands"][0] = {
        "name": "harmless",
        "opcode": 233,
        "purpose": "status_check",
    }
    with pytest.raises(contracts.RuntimeWaveformContractError, match="differs"):
        contracts.validate_candidate(candidate)


def test_identity_and_basic_electrical_polarity_are_independent_blockers() -> None:
    payload = _reviewed_payload()
    candidate = _ready_candidate(payload)
    candidate["panel"]["batch_id"] = None
    candidate["panel"]["controller_revision"] = None
    candidate["provenance"]["vendor_or_panel_owner_review_id"] = None
    candidate["electrical"]["vgh_mv"] = 0.0
    report = contracts.evaluate_candidate(
        candidate, controller_payload_bytes={"CS1": payload, "CS2": payload}
    )
    assert report["offline_contract_complete"] is False
    assert "panel_batch_identity_missing" in report["offline_blocker_codes"]
    assert "controller_revision_identity_missing" in report["offline_blocker_codes"]
    assert "vendor_or_panel_owner_review_missing" in report["offline_blocker_codes"]
    assert "electrical_polarity_invalid:vgh_mv" in report["offline_blocker_codes"]


def test_unknown_key_and_nonfinite_number_fail_closed() -> None:
    candidate = _template()
    candidate["unexpected"] = True
    with pytest.raises(contracts.RuntimeWaveformContractError, match="keys differ"):
        contracts.validate_candidate(candidate)
    candidate = _template()
    candidate["electrical"]["vcom_mv"] = float("nan")
    with pytest.raises(contracts.RuntimeWaveformContractError, match="finite"):
        contracts.validate_candidate(candidate)


def test_manifest_hash_is_canonical_and_order_independent() -> None:
    candidate = _template()
    reordered = dict(reversed(list(candidate.items())))
    left = contracts.evaluate_candidate(candidate)["candidate_manifest_sha256"]
    right = contracts.evaluate_candidate(reordered)["candidate_manifest_sha256"]
    assert left == right


def test_cli_rejects_duplicate_keys_and_require_ready_returns_two(tmp_path: Path) -> None:
    tool = Path("tools/mf1750_runtime_waveform_contract.py")
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, str(tool), "inspect", "--manifest", str(duplicate)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode == 2
    assert "duplicate JSON key" in rejected.stderr

    manifest = tmp_path / "blocked.json"
    manifest.write_text(json.dumps(_template()), encoding="utf-8")
    blocked = subprocess.run(
        [sys.executable, str(tool), "require-ready", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert blocked.returncode == 2
    report = json.loads(blocked.stdout)
    assert report["execution_ready"] is False

    payload = _reviewed_payload()
    complete_manifest = tmp_path / "offline-complete.json"
    cs1 = tmp_path / "cs1.bin"
    cs2 = tmp_path / "cs2.bin"
    complete_manifest.write_text(
        json.dumps(_ready_candidate(payload)), encoding="utf-8"
    )
    cs1.write_bytes(payload)
    cs2.write_bytes(payload)
    complete = subprocess.run(
        [
            sys.executable,
            str(tool),
            "require-ready",
            "--manifest",
            str(complete_manifest),
            "--cs1-payload",
            str(cs1),
            "--cs2-payload",
            str(cs2),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert complete.returncode == 2
    complete_report = json.loads(complete.stdout)
    assert complete_report["manifest_contract_complete"] is True
    assert complete_report["offline_contract_complete"] is False
    assert complete_report["execution_ready"] is False


def test_cli_template_and_inspect_never_require_hardware(tmp_path: Path) -> None:
    tool = Path("tools/mf1750_runtime_waveform_contract.py")
    generated = subprocess.run(
        [sys.executable, str(tool), "template", "--created-at", CREATED_AT],
        capture_output=True,
        text=True,
        check=False,
    )
    assert generated.returncode == 0
    candidate = json.loads(generated.stdout)
    manifest = tmp_path / "candidate.json"
    manifest.write_text(json.dumps(candidate), encoding="utf-8")
    inspected = subprocess.run(
        [sys.executable, str(tool), "inspect", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert inspected.returncode == 0
    report = json.loads(inspected.stdout)
    assert report["hardware_io_performed"] is False
    assert report["network_io_performed"] is False


def test_cli_compiles_twelve_virtual_channels_as_multi_profile_plan(
    tmp_path: Path,
) -> None:
    tool = Path("tools/mf1750_runtime_waveform_contract.py")
    first = "a" * 64
    second = "b" * 64
    colors = [_virtual(f"p1-{code}", first, code) for code in range(8)]
    colors += [_virtual(f"p2-{code}", second, code) for code in range(4)]
    path = tmp_path / "virtual-colors.json"
    path.write_text(json.dumps(colors), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(tool), "palette", "--colors", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["virtual_color_count"] == 12
    assert report["single_refresh_all_colors_possible_by_addressing"] is False
    assert report["visible_refresh_authorized"] is False


def test_copy_does_not_accidentally_mutate_template() -> None:
    original = _template()
    changed = copy.deepcopy(original)
    changed["qualification_gates"][contracts.GATE_NAMES[0]] = True
    assert original["qualification_gates"][contracts.GATE_NAMES[0]] is False


def _virtual(
    color_id: str,
    profile: str,
    target: int,
    *,
    primer: int | None = None,
    qualification: str = "unmeasured_candidate",
) -> dict:
    return {
        "schema_version": 1,
        "kind": virtual_palette.VIRTUAL_COLOR_KIND,
        "color_id": color_id,
        "waveform_profile_sha256": profile,
        "target_code": target,
        "primer_code": primer,
        "expected_lab": None,
        "qualification": qualification,
    }


def test_one_profile_has_eight_direct_addresses_not_a_physical_color_claim() -> None:
    profile = "a" * 64
    plan = virtual_palette.compile_virtual_palette(
        [_virtual(f"otp-{code}", profile, code) for code in range(8)]
    )
    assert plan["virtual_color_count"] == 8
    assert plan["direct_capacity_per_profile"] == 8
    assert plan["single_refresh_all_colors_possible_by_addressing"] is True
    assert plan["optical_distinctness_inferred"] is False


def test_twelve_virtual_channels_can_exist_but_need_profile_switching() -> None:
    first = "a" * 64
    second = "b" * 64
    colors = [_virtual(f"p1-{code}", first, code) for code in range(8)]
    colors += [_virtual(f"p2-{code}", second, code) for code in range(4)]
    plan = virtual_palette.compile_virtual_palette(colors)
    assert plan["virtual_color_count"] == 12
    assert plan["waveform_profile_count"] == 2
    assert plan["single_refresh_all_colors_possible_by_addressing"] is False
    assert plan["multi_pass_or_profile_switch_required"] is True
    assert "cross_profile_coexistence_not_proven" in plan["blocker_codes"]


def test_primer_target_address_is_a_sequence_color_not_direct_channel() -> None:
    profile = "c" * 64
    plan = virtual_palette.compile_virtual_palette(
        [
            _virtual("direct-u04", profile, 4),
            _virtual("black-to-u04", profile, 4, primer=0),
            _virtual("white-to-u04", profile, 4, primer=1),
        ]
    )
    assert plan["direct_color_count"] == 1
    assert plan["sequence_color_count"] == 2
    assert "primer_history_state_control_required" in plan["blocker_codes"]


def test_duplicate_virtual_address_and_invalid_code_fail_closed() -> None:
    profile = "d" * 64
    with pytest.raises(virtual_palette.VirtualPaletteError, match="addresses"):
        virtual_palette.compile_virtual_palette(
            [
                _virtual("first", profile, 4),
                _virtual("second", profile, 4),
            ]
        )
    invalid = _virtual("invalid", profile, 8)
    with pytest.raises(virtual_palette.VirtualPaletteError, match="3-bit"):
        virtual_palette.validate_virtual_color(invalid)
