from __future__ import annotations

from copy import deepcopy

import pytest

from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_once as once
from tools import mf1750_p2_commented_endpoint_atlas_4x8_v1_pack as pack


def _firmware_status_transcript() -> list[dict]:
    # P2 handleArm sends 201; handleExecute sends 202 after durable consume.
    return [
        {
            "method": method,
            "endpoint": endpoint,
            "path": once.base.runner.ENDPOINTS[endpoint],
            "status": status,
            "response": {"boot_nonce": "0123456789abcdef"},
            "headers": {},
        }
        for method, endpoint, status in (
            ("GET", "version", 200),
            ("GET", "manifest", 200),
            ("GET", "status", 200),
            ("GET", "report", 200),
            ("POST", "arm", 201),
            ("POST", "execute", 202),
            ("GET", "report", 200),
        )
    ]


def test_transcript_accepts_sealed_firmware_http_statuses() -> None:
    transcript = _firmware_status_transcript()
    once._validate_transcript_prefix(
        transcript, boot_nonce="0123456789abcdef", terminal=transcript[-1]["response"]
    )
    once._validate_transcript_prefix(transcript[:4])


@pytest.mark.parametrize(
    "index,field,value",
    [
        (4, "status", 200),
        (4, "status", 202),
        (4, "status", 409),
        (5, "status", 200),
        (5, "status", 201),
        (5, "status", 503),
        (6, "status", 202),
        (4, "status", 201.0),
        (4, "method", "GET"),
        (6, "method", "POST"),
        (4, "path", "/api/foreign/arm"),
        (4, "observation_error", "timeout"),
        (6, "headers", {"unexpected": "value"}),
        (5, "response", {"boot_nonce": "fedcba9876543210"}),
    ],
)
def test_transcript_rejects_wrong_wire_status_method_and_binding(
    index: int, field: str, value: object
) -> None:
    transcript = deepcopy(_firmware_status_transcript())
    transcript[index][field] = value
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_transcript_prefix(transcript, boot_nonce="0123456789abcdef")


def test_runner_identity_and_no_io_dry_validation() -> None:
    value = once.dry_validate(verify_artifacts=True)
    assert value["result"] == "PASS"
    assert value["campaign_id"] == pack.CAMPAIGN_ID
    assert value["contract_id"] == pack.CONTRACT_SHA256
    assert value["complete_commented_profile_both_controllers"] is True
    assert value["network_requests"] == 0
    assert value["device_requests_made"] == 0
    assert value["hardware_accessed"] is False
    assert value["serial_or_com_accessed"] is False
    assert value["relay_accessed"] is False
    assert value["camera_accessed"] is False
    assert value["firmware_flashed"] is False
    assert value["display_refreshed"] is False


def test_runner_surface_is_fresh_and_single_action() -> None:
    action = once.base.runner.ACTIONS[0]
    assert len(once.base.runner.ACTIONS) == 1
    assert once.base.runner.NVS_NAMESPACE == "p2ce4x8v1"
    assert once.base.runner.NVS_KEY == "cursor_p2c"
    assert action["action_id"] == pack.ACTION_SHA256
    assert action["descriptor_id"] == pack.ACTION_DESCRIPTOR_SHA256
    assert action["global_header"] == "commented"
    assert action["waveform_binding"] == pack.commented_profile()
    assert once.ACTION_OUTPUTS[1].name.startswith("action-01-commented")


def test_manifest_adapter_accepts_only_commented_tuple_key() -> None:
    layout = {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 4,
        "grid_columns_per_controller": 8,
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "grid_x0_local": 20,
        "grid_y_by_row": list(pack.GRID_Y_BY_ROW),
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 552,
        "cell_width": 52,
        "cell_height": 100,
        "gap_x": 8,
        "gap_y": 36,
        "background_code": 7,
        "border": False,
        "same_layout_both_controllers": True,
        "controller_dtm_byte_identical": True,
        "cs2_position_mirrored": False,
        "spatial_dither": False,
        "fresh_one_shot": True,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "factory_otp_white_ordinals": [],
        "runtime_lut_ordinals": [1],
        "one_visible_refresh_per_action": True,
        "samples_per_code_per_controller_per_frame": 4,
        "qualified_colours": 0,
        "qualified_lightness_levels": 0,
        "commented_global_tuple_id": pack.commented_profile()["global_tuple_id"],
    }
    manifest = {
        "kind": "mf1750-ec5-p2-commented-endpoint-atlas-4x8-v1-manifest",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "contract_id": pack.CONTRACT_SHA256,
        "classification": pack.CLASSIFICATION,
        "layout_id": pack.VARIANT_KEY,
        "profile_source": "legacy_complete_535_commented_symmetric_controller_tuple",
        "global_header": "commented",
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "external_containment": once.REPORT["contract"]["external_containment"],
        "history_layout": layout,
    }
    for key in (
        "full_screen_global_refresh",
        "fresh_one_shot_endpoint_atlas",
        "complete_profile_tuple",
        "position_balanced_atlas",
        "busy_qualified_arm_execute_dispatch",
        "device_enforced_same_boot",
    ):
        manifest[key] = True
    for key in (
        "partial_refresh", "window_refresh", "command_0x83", "command_0x86",
        "unknown_commands", "mid_refresh_power_cut", "spi_frequency_sweep",
        "same_palette_hold_probe", "cross_palette_hold_probe", "local_hold_claimed",
        "colour_qualification", "lightness_qualification", "history_sequence",
        "identical_target_repeat", "main_campaign_resume_after_containment",
    ):
        manifest[key] = False
    once._validate_manifest(manifest)


def test_private_origin_accepts_fresh_lan_and_rejects_special_or_non80() -> None:
    # A fresh DHCP/ARP result is allowed to select a different RFC1918 host;
    # the historical P1 address is not part of the P2 contract.
    assert once._private_origin("http://192.168.1.77") == "http://192.168.1.77"
    assert once._private_origin("http://192.168.1.77:80/") == "http://192.168.1.77"

    for value in (
        "http://192.168.1.77:8080",
        "http://127.0.0.1",
        "http://169.254.1.77",
        "http://224.0.0.1",
        "http://0.0.0.0",
        "http://192.0.2.77",
        "http://device.local",
        "https://192.168.1.77",
    ):
        with pytest.raises(once.base.runner.RecheckError):
            once._private_origin(value)
