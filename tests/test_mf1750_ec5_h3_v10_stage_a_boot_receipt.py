from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_v10_stage_a_boot_receipt as receipt


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_H3_C_FIRST_DIAGNOSTIC_RECOVERY_PLAN_20260814_V1"
    / "WF20_25-plan.json"
)
TRANSCRIPT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C_FIRST_LIVE_20260815_V10_RECOVERY_V1"
    / "stage-a-chip-id-transcript.txt"
)


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> dict:
    output = tmp_path_factory.mktemp("stage-a-receipt") / "receipt.json"
    return receipt.materialize_receipt(
        plan_file=PLAN, transcript_file=TRANSCRIPT, receipt_file=output
    )


def test_exact_plan_command_port_and_transcript_bindings(root: dict) -> None:
    assert root["classification"] == receipt.CLASSIFICATION
    assert root["plan_binding"]["plan_id"] == receipt.EXPECTED_PLAN_ID
    assert (
        root["plan_binding"]["stage_a_intent_canonical_sha256"]
        == receipt.EXPECTED_STAGE_A_INTENT_SHA256
    )
    assert root["command_observation"]["exact_argv"] == list(receipt.EXACT_ARGV)
    assert root["command_observation"]["chip_id_process_invocations"] == 1
    assert root["command_observation"]["shell_exit_code"] == 0
    assert (
        root["command_observation"]["raw_stdout_stderr_capture_independently_sealed"]
        is False
    )
    port = root["serial_port_identity_observation"]
    assert (
        port["port"],
        port["vid_hex"],
        port["pid_hex"],
        port["usb_serial_number"],
    ) == (
        "COM8",
        "1A86",
        "55D3",
        "5C4C165475",
    )
    transcript = root["transcript_binding"]
    assert transcript["bytes"] == 339
    assert transcript["sha256"] == receipt.EXPECTED_TRANSCRIPT_SHA256
    assert transcript["mac_exact_occurrences_in_one_invocation"] == 2
    assert transcript["file_mtime_is_acquisition_time_proof"] is False


def test_reset_scope_is_partial_and_does_not_satisfy_stage_a(root: dict) -> None:
    accounting = root["boot_control_accounting"]
    assert accounting["bootloader_entry_reset_control_sequence_requested"] == 1
    assert accounting["bootloader_entry_single_electrical_reset_proven"] is False
    assert accounting["final_application_hard_reset_message_count"] == 1
    assert accounting["final_application_hard_reset_requested"] is True
    assert accounting["post_reset_application_handshake_observed"] is False
    assert accounting["post_reset_application_boot_proven"] is False
    assert accounting["total_low_level_reset_control_transitions"] == "UNKNOWN"
    assert accounting["total_reset_or_boot_count_claimed_exactly_one"] is False
    assert accounting["plan_new_boot_operations_exactly_one_satisfied"] is False
    assert accounting["persistent_flash_or_nvs_mutations_requested_by_command"] == 0
    assert accounting["post_reset_application_persistent_mutations"] == "UNKNOWN"
    assert root["gate_outcome"]["stage_a_intent_satisfied"] is False
    assert (
        root["gate_outcome"]["sealed_new_boot_completion_receipt_gate_satisfied"]
        is False
    )
    assert root["gate_outcome"]["stage_b_diagnostic_authorization_derivable"] is False


def test_proof_boundary_refuses_active_v10_ip_and_api_claims(root: dict) -> None:
    boundary = root["proof_boundary"]
    for key in (
        "proves_active_application_boot",
        "proves_active_ota_slot",
        "proves_active_v10_binary",
        "proves_firmware_at_0x10000_is_running",
        "proves_wifi_sta_connected",
        "proves_ip_192_168_1_7",
        "proves_ip_192_168_1_14",
        "proves_http_server_or_api_routes_ready",
        "proves_boot_nonce",
        "proves_device_profile_manifest_status_or_report",
        "proves_no_post_reset_application_nvs_or_otadata_mutation",
    ):
        assert boundary[key] is False
    assert root["offline_materialization"] == {
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "device_network_accessed": False,
        "subprocess_executed": False,
        "device_mutations": 0,
    }


def test_validation_round_trip_and_resealed_tamper_rejected(root: dict) -> None:
    summary = receipt.validate_receipt(root)
    assert summary["valid"] is True
    assert summary["stage_a_intent_satisfied"] is False
    assert summary["active_v10_proven"] is False
    assert summary["ip_proven"] is False
    assert summary["stage_b_authorization_derivable"] is False

    tampered = deepcopy(root)
    tampered["proof_boundary"]["proves_active_v10_binary"] = True
    tampered = receipt._seal(  # noqa: SLF001
        {key: value for key, value in tampered.items() if key != "integrity"}
    )
    with pytest.raises(receipt.StageABootReceiptError, match="reconstruction"):
        receipt.validate_receipt(tampered)


def test_transcript_tamper_and_exclusive_output_rejected(
    root: dict, tmp_path: Path
) -> None:
    changed = tmp_path / "changed.txt"
    changed.write_bytes(TRANSCRIPT.read_bytes() + b"x")
    with pytest.raises(receipt.StageABootReceiptError, match="transcript exact bytes"):
        receipt.materialize_receipt(
            plan_file=PLAN,
            transcript_file=changed,
            receipt_file=tmp_path / "unused.json",
        )

    output = Path(root["receipt_file"])
    receipt.write_new_receipt(output, root)
    assert output.read_bytes() == contract.canonical_json_bytes(root) + b"\n"
    with pytest.raises(receipt.StageABootReceiptError, match="already exists"):
        receipt.write_new_receipt(output, root)
