from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Mapping

from PIL import Image
import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import (
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_pack as w4,
)
from tools import (
    mf1750_raw_p16_crossover_w11_t4_active_header_ca_r20_swap_confirmation_successor_v5_white_v1_pack as w11,
)


def _current_w11_action_result_path() -> Path:
    return (
        Path(__file__).resolve().parents[1]
        / ".test-output"
        / "hardware"
        / (
            "MF1750_RAW_P16_CROSSOVER_W11_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            "CONFIRMATION_SUCCESSOR_V5_WHITE_20260901_V1"
        )
        / "action-01-factory-otp-white.json"
    )


def _authenticated_device(*, index: int = 0) -> dict[str, Any]:
    alternative_name = (
        r"@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#"
        r"6&22675d4e&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    )
    return {
        "enumerator": camera.DIRECTSHOW_DEVICE_ENUMERATOR,
        "friendly_name": camera.TARGET_CAMERA_FRIENDLY_NAME,
        "alternative_name": alternative_name,
        "pnp_instance_id": (r"USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000"),
        "directshow_index": index,
        "usb_vid": "32E4",
        "usb_pid": "4801",
    }


def _jpeg(*, colour: tuple[int, int, int] = (210, 220, 230)) -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 48), colour).save(output, format="JPEG", quality=93)
    return output.getvalue()


def _action(path: Path) -> dict[str, Any]:
    action_id = "1" * 64
    descriptor_id = "2" * 64
    contract_id = "3" * 64
    frame_sha256 = "4" * 64
    root = {
        "schema_version": 1,
        "kind": "test-action-result",
        "created_at": "2026-08-28T07:20:48.000+08:00",
        "outcome": "complete_pass",
        "boot_nonce": "1ffa520a2537168d",
        "firmware_sha256": "5" * 64,
        "visible_refreshes": 1,
        "action": {
            "action_id": action_id,
            "descriptor_id": descriptor_id,
            "ordinal": 2,
            "role": "SOURCE_GRID",
            "frame_sha256": frame_sha256,
        },
        "terminal_report": {
            "terminal_state": "COMPLETE",
            "result": True,
            "valid": True,
            "campaign_id": "CAMPAIGN-V2",
            "test_id": "TEST-V2",
            "contract_id": contract_id,
            "build_tag": "BUILD-V2",
            "boot_nonce": "1ffa520a2537168d",
            "action_id": action_id,
            "descriptor_id": descriptor_id,
            "ordinal": 2,
            "role": "SOURCE_GRID",
        },
    }
    sealed = camera._seal(root)
    path.write_text(
        json.dumps(sealed, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return sealed


def _v3_factory_white_action(
    path: Path,
    *,
    action_role: str = camera.FACTORY_OTP_WHITE_ACTION_ROLE,
    marker_role: str = "BRIGHTNESS_REDPINK_OTP_WHITE_SUCCESSOR",
    marker_version: int = 3,
    profile_id: str = "WF23_25",
    campaign_id: str = "CAMPAIGN-V2",
    test_id: str = "TEST-V2",
    contract_id: str = "3" * 64,
    build_tag: str = "BUILD-V2",
    firmware_sha256: str = "5" * 64,
    action_id: str = "1" * 64,
    descriptor_id: str = "2" * 64,
) -> dict[str, Any]:
    root = dict(_action(path))
    root.pop("integrity")
    root["firmware_sha256"] = firmware_sha256
    root["action"] = {
        **root["action"],
        "action_id": action_id,
        "descriptor_id": descriptor_id,
    }
    terminal = dict(root["terminal_report"])
    terminal.pop("descriptor_id")
    terminal.pop("role")
    terminal.pop("boot_nonce")
    terminal.update(
        {
            "kind": camera.FACTORY_OTP_WHITE_REPORT_KIND,
            "profile_id": profile_id,
            "campaign_id": campaign_id,
            "test_id": test_id,
            "contract_id": contract_id,
            "build_tag": build_tag,
            "action_id": action_id,
            "transaction_descriptor_sha256": descriptor_id,
            "transaction_descriptor_marker": (
                f"MF1750_EC5_TX_DESCRIPTOR_V{marker_version}|PROFILE={profile_id}|"
                f"ROLE={marker_role}|SHA256=" + descriptor_id
            ),
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": 1,
            "no_retry": True,
            "campaign_complete": True,
            "driver": {
                "valid": True,
                "running": False,
                "sequence_ok": True,
                "wait_timeout": False,
                "failure_stage": "none",
                "failure_code": 0,
            },
        }
    )
    root["action"] = {
        **root["action"],
        "role": action_role,
    }
    root["terminal_report"] = terminal
    shared = {
        field: terminal[field]
        for field in (
            "campaign_id",
            "test_id",
            "contract_id",
            "build_tag",
            "transaction_descriptor_sha256",
            "transaction_descriptor_marker",
        )
    }
    mutation_headers = {
        "X-EC5-Action-Id": root["action"]["action_id"],
        "X-EC5-Boot-Nonce": root["boot_nonce"],
        "X-EC5-Build-Tag": terminal["build_tag"],
        "X-EC5-Campaign-Id": terminal["campaign_id"],
        "X-EC5-Descriptor-Id": root["action"]["descriptor_id"],
        "X-EC5-Ordinal": str(root["action"]["ordinal"]),
        "X-EC5-Test-Id": terminal["test_id"],
    }
    root["transcript"] = [
        {
            "endpoint": "status",
            "method": "GET",
            "status": 200,
            "headers": {},
            "body": {**shared, "boot_nonce": root["boot_nonce"]},
        },
        {
            "endpoint": "arm",
            "method": "POST",
            "status": 201,
            "headers": mutation_headers,
            "body": {
                **shared,
                "accepted": True,
                "boot_nonce": root["boot_nonce"],
                "action_id": root["action"]["action_id"],
                "ordinal": root["action"]["ordinal"],
            },
        },
        {
            "endpoint": "execute",
            "method": "POST",
            "status": 202,
            "headers": mutation_headers,
            "body": {
                **shared,
                "accepted": True,
                "action_id": root["action"]["action_id"],
            },
        },
        {
            "endpoint": "report",
            "method": "GET",
            "status": 200,
            "headers": {},
            "body": terminal,
        },
    ]
    sealed = camera._seal(root)
    path.write_text(
        json.dumps(sealed, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return sealed


def _raw_p16_endpoint_gallery_white_containment_action(
    path: Path, **updates: Any
) -> dict[str, Any]:
    binding = camera.RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_BINDING
    arguments = {
        "action_role": camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": camera.RAW_P16_ENDPOINT_GALLERY_OTP_WHITE_MARKER_ROLE,
        "marker_version": 1,
        "profile_id": binding["profile_id"],
        "campaign_id": binding["campaign_id"],
        "test_id": binding["test_id"],
        "contract_id": binding["contract_id"],
        "build_tag": binding["build_tag"],
        "action_id": binding["action_id"],
        "descriptor_id": binding["descriptor_id"],
    }
    arguments.update(updates)
    return _v3_factory_white_action(path, **arguments)


def _raw_p16_crossover_white_containment_action(
    path: Path, stage: str, **updates: Any
) -> dict[str, Any]:
    binding = next(
        item
        for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
        if item["stage"] == stage
    )
    arguments = {
        "action_role": binding["role"],
        "marker_role": binding["marker_role"],
        "marker_version": 1,
        "profile_id": binding["profile_id"],
        "campaign_id": binding["campaign_id"],
        "test_id": binding["test_id"],
        "contract_id": binding["contract_id"],
        "build_tag": binding["build_tag"],
        "firmware_sha256": binding["firmware_sha256"],
        "action_id": binding["action_id"],
        "descriptor_id": binding["descriptor_id"],
    }
    arguments.update(updates)
    return _v3_factory_white_action(path, **arguments)


def _stable_code0_luma_latin_v3_white_successor_action(
    path: Path, **updates: Any
) -> dict[str, Any]:
    binding = camera.STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_BINDING
    arguments = {
        "action_role": binding["role"],
        "marker_role": binding["marker_role"],
        "marker_version": 1,
        "profile_id": binding["profile_id"],
        "campaign_id": binding["campaign_id"],
        "test_id": binding["test_id"],
        "contract_id": binding["contract_id"],
        "build_tag": binding["build_tag"],
        "firmware_sha256": binding["firmware_sha256"],
        "action_id": binding["action_id"],
        "descriptor_id": binding["descriptor_id"],
    }
    arguments.update(updates)
    return _v3_factory_white_action(path, **arguments)


def _p1_active_endpoint_atlas_4x8_v1_white_successor_action(
    path: Path, **updates: Any
) -> dict[str, Any]:
    binding = camera.P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING
    arguments = {
        "action_role": binding["role"],
        "marker_role": binding["marker_role"],
        "marker_version": 1,
        "profile_id": binding["profile_id"],
        "campaign_id": binding["campaign_id"],
        "test_id": binding["test_id"],
        "contract_id": binding["contract_id"],
        "build_tag": binding["build_tag"],
        "firmware_sha256": binding["firmware_sha256"],
        "action_id": binding["action_id"],
        "descriptor_id": binding["descriptor_id"],
    }
    arguments.update(updates)
    return _v3_factory_white_action(path, **arguments)


def test_stable_code0_luma_latin_v3_white_successor_frozen_binding() -> None:
    assert camera.STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_BINDING == {
        "profile_id": "WF23_25",
        "campaign_id": (
            "EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1"
        ),
        "test_id": (
            "EC5-STABLE-CODE0-LUMA-LATIN-V3-FACTORY-OTP-WHITE-SUCCESSOR-V1"
        ),
        "contract_id": (
            "787c2898a841913ac009e0284a1f3680403cc77a05ec700cb17f1a4a08152377"
        ),
        "build_tag": (
            "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_"
            "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
        ),
        "firmware_sha256": (
            "804aadd5a9b82a02a01bc0431750790666d2ba56352d43b3add7f89245dff907"
        ),
        "action_id": (
            "7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f"
        ),
        "descriptor_id": (
            "8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0"
        ),
        "role": camera.FACTORY_OTP_WHITE_ACTION_ROLE,
        "marker_role": "OTP_WHITE_AFTER_STABLE_CODE0_LATIN_V3_L3_OR_L4_COMPLETE",
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_AFTER_STABLE_CODE0_LATIN_V3_L3_OR_L4_COMPLETE|"
            "SHA256=8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0"
        ),
    }


def test_stable_code0_luma_latin_v3_white_successor_exact_binding_is_accepted(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "stable-code0-luma-latin-v3-white-successor.json"
    root = _stable_code0_luma_latin_v3_white_successor_action(action_path)

    _payload, _loaded, identity = camera._load_action_result(action_path)

    binding = camera.STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_BINDING
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
    ):
        assert identity[field] == binding[field]
    assert root["terminal_report"]["transaction_descriptor_marker"] == binding["marker"]


@pytest.mark.parametrize(
    "updates",
    (
        {"profile_id": "WF20_25"},
        {
            "campaign_id": (
                "EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V2"
            )
        },
        {
            "test_id": (
                "EC5-STABLE-CODE0-LUMA-LATIN-V3-FACTORY-OTP-WHITE-SUCCESSOR-V2"
            )
        },
        {"contract_id": "9" * 64},
        {
            "build_tag": (
                "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_"
                "FACTORY_OTP_WHITE_SUCCESSOR_V2_2026-09-01"
            )
        },
        {"firmware_sha256": "8" * 64},
        {"action_id": "7" * 64},
        {"descriptor_id": "6" * 64},
        {"action_role": camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE},
        {"marker_version": 2},
        {
            "marker_role": (
                "OTP_WHITE_AFTER_STABLE_CODE0_LATIN_V3_L3_OR_L4_COMPLETE_EXTRA"
            )
        },
    ),
)
def test_stable_code0_luma_latin_v3_white_successor_near_matches_fail_closed(
    tmp_path: Path, updates: Mapping[str, Any]
) -> None:
    action_path = tmp_path / "stable-code0-luma-latin-v3-white-near-match.json"
    _stable_code0_luma_latin_v3_white_successor_action(action_path, **updates)

    with pytest.raises(
        camera.CameraCaptureEvidenceError,
        match="stable-code0 luma Latin V3 white successor allowlist|marker binding",
    ):
        camera._load_action_result(action_path)


def test_p1_active_endpoint_atlas_4x8_v1_white_successor_frozen_binding() -> None:
    assert camera.P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING == {
        "profile_id": "WF23_25",
        "campaign_id": (
            "EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1"
        ),
        "test_id": (
            "EC5-P1-ACTIVE-ENDPOINT-ATLAS-4X8-V1-FACTORY-OTP-WHITE-SUCCESSOR-V1"
        ),
        "contract_id": (
            "403dc7e4c0efab105eddbe3039c32f1b563494cc866410046f3038fec2bf09ab"
        ),
        "build_tag": (
            "MF1750_EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_"
            "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
        ),
        "firmware_sha256": (
            "4f67f065993dfce3f6ffaeb2b5afb5a89f82c4563c9ad83b79c505311af24ef3"
        ),
        "action_id": (
            "b28442077b06e959a9cf8bf4e588a5f463e5cfd004a71735e445916d9dbb80bc"
        ),
        "descriptor_id": (
            "4e921326c729bb66d744237662abe63604648834b68d4e82085c4284edb2cf9c"
        ),
        "role": camera.FACTORY_OTP_WHITE_ACTION_ROLE,
        "marker_role": "OTP_WHITE_AFTER_P1_ACTIVE_ENDPOINT_ATLAS_ORDINAL1_COMPLETE",
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_AFTER_P1_ACTIVE_ENDPOINT_ATLAS_ORDINAL1_COMPLETE|"
            "SHA256=4e921326c729bb66d744237662abe63604648834b68d4e82085c4284edb2cf9c"
        ),
    }


def test_p1_active_endpoint_atlas_4x8_v1_white_successor_exact_binding_is_accepted(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "p1-active-endpoint-atlas-white-successor.json"
    root = _p1_active_endpoint_atlas_4x8_v1_white_successor_action(action_path)

    _payload, _loaded, identity = camera._load_action_result(action_path)

    binding = camera.P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
    ):
        assert identity[field] == binding[field]
    assert root["terminal_report"]["transaction_descriptor_marker"] == binding["marker"]


@pytest.mark.parametrize(
    "updates",
    (
        {"profile_id": "WF20_25"},
        {"campaign_id": "EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V2_WHITE"},
        {"test_id": "EC5-P1-ACTIVE-ENDPOINT-ATLAS-4X8-V2-WHITE"},
        {"contract_id": "9" * 64},
        {"build_tag": "MF1750_EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V2_WHITE"},
        {"firmware_sha256": "8" * 64},
        {"action_id": "7" * 64},
        {"descriptor_id": "6" * 64},
        {"action_role": camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE},
        {"marker_version": 2},
        {"marker_role": "OTP_WHITE_AFTER_P1_ACTIVE_ENDPOINT_ATLAS_OTHER_COMPLETE"},
    ),
)
def test_p1_active_endpoint_atlas_4x8_v1_white_successor_near_matches_fail_closed(
    tmp_path: Path, updates: Mapping[str, Any]
) -> None:
    action_path = tmp_path / "p1-active-endpoint-atlas-white-near-match.json"
    _p1_active_endpoint_atlas_4x8_v1_white_successor_action(
        action_path, **updates
    )

    with pytest.raises(
        camera.CameraCaptureEvidenceError,
        match="P1 active-endpoint atlas 4x8 V1 white successor allowlist|marker binding",
    ):
        camera._load_action_result(action_path)


def test_w4_profile_following_allowlist_matches_frozen_pack_exactly() -> None:
    report = w4.build_white_report()
    action = report["action"]
    artifact = w4.WHITE_ARTIFACTS[w4.STAGE]
    matches = [
        item
        for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
        if item["stage"] == w4.STAGE
    ]
    assert len(matches) == 1
    binding = matches[0]

    assert binding == {
        "stage": w4.STAGE,
        "profile_id": report["contract"]["profile_id"],
        "campaign_id": report["contract"]["campaign_id"],
        "test_id": report["contract"]["test_id"],
        "contract_id": report["contract_id"],
        "build_tag": report["contract"]["build_tag"],
        "firmware_sha256": artifact["bin_sha256"],
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "role": action["role"],
        "marker_role": (
            "OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR"
        ),
        "marker": w4.marker(),
    }


def test_w11_allowlist_matches_frozen_pack_exactly() -> None:
    report = w11.build_white_report()
    action = report["action"]
    artifact = w11.WHITE_ARTIFACTS[w11.STAGE]
    matches = [
        item
        for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
        if item["stage"] == w11.STAGE
    ]
    assert len(matches) == 1
    binding = matches[0]

    assert binding == {
        "stage": w11.STAGE,
        "profile_id": report["contract"]["profile_id"],
        "campaign_id": report["contract"]["campaign_id"],
        "test_id": report["contract"]["test_id"],
        "contract_id": report["contract_id"],
        "build_tag": report["contract"]["build_tag"],
        "firmware_sha256": artifact["bin_sha256"],
        "action_id": action["action_id"],
        "descriptor_id": action["descriptor_id"],
        "role": action["role"],
        "marker_role": (
            "OTP_WHITE_RAW_P16_CROSSOVER_W11_T4_V5_COMPLETE_TERMINAL"
        ),
        "marker": w11.marker(),
    }


def test_w11_current_real_producer_is_accepted_by_capture_retained_offline_seam(
    tmp_path: Path,
) -> None:
    live_result = _current_w11_action_result_path()
    if not live_result.is_file():
        pytest.skip("current W11 live COMPLETE result is not present in this checkout")
    action_path = tmp_path / "action-01-factory-otp-white.json"
    action_path.write_bytes(live_result.read_bytes())
    requested = {
        "autofocus": 0,
        "focus": 79,
        "auto_exposure": 0.25,
        "exposure": -5,
        "auto_white_balance": 0,
        "white_balance_temperature": 6500,
    }
    effective = camera._normalise_requested_settings(requested)
    set_results = {
        field: True for field, value in effective.items() if value is not None
    }

    result = camera.capture_locked_retained(
        action_result_path=action_path,
        photo_path=tmp_path / "w11-retained.jpg",
        sidecar_path=tmp_path / "w11-retained.capture.json",
        camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
        camera_instance_id=_authenticated_device()["pnp_instance_id"],
        mount_id="w11-real-producer-offline-test-seam",
        coverage_scope=camera.COVERAGE_FULL,
        requested_settings=requested,
        warmup_frames=3,
        limitations=("offline injected camera seam; no hardware accessed",),
        capture_backend=lambda *_args: (
            _jpeg(),
            {
                "backend": "DSHOW",
                "authenticated_device": _authenticated_device(),
                "set_results": set_results,
                "effective_settings_before_frame": effective,
                "effective_settings_after_frame": dict(effective),
                "warmup_frames_completed": 3,
                "read_failures": 0,
                "frame_retrieved_at": "2026-09-01T08:30:00.000+08:00",
                "frame_retrieved_at_utc": "2026-09-01T00:30:00.000+00:00",
            },
        ),
        _device_resolver=_authenticated_device,
    )

    assert result["capture_binding"] == camera.BINDING_LOCKED_RETAINED
    assert result["campaign_id"] == w11.build_white_report()["contract"]["campaign_id"]
    assert result["action_id"] == w11.build_white_report()["action"]["action_id"]
    assert result["descriptor_id"] == w11.build_white_report()["action"]["descriptor_id"]
    assert result["action_result"]["terminal_state"] == "COMPLETE"
    assert result["action_result"]["visible_refreshes"] == 1
    assert camera.validate_capture_evidence(
        tmp_path / "w11-retained.capture.json"
    ) == result


def test_w11_current_real_producer_marker_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    live_result = _current_w11_action_result_path()
    if not live_result.is_file():
        pytest.skip("current W11 live COMPLETE result is not present in this checkout")
    root = json.loads(live_result.read_text(encoding="utf-8"))
    root.pop("integrity")
    original_marker = root["terminal_report"]["transaction_descriptor_marker"]
    tampered_marker = original_marker.replace(
        "W11_T4_V5_COMPLETE_TERMINAL|",
        "W11_T4_V5_COMPLETE_TERMINAL_EXTRA|",
    )
    assert tampered_marker != original_marker
    root["terminal_report"]["transaction_descriptor_marker"] = tampered_marker
    for entry in root["transcript"]:
        body = entry.get("body")
        if isinstance(body, dict) and "transaction_descriptor_marker" in body:
            body["transaction_descriptor_marker"] = tampered_marker
    action_path = tmp_path / "tampered-w11-factory-otp-white.json"
    action_path.write_text(
        json.dumps(camera._seal(root), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(camera.CameraCaptureEvidenceError, match="marker binding"):
        camera._load_action_result(action_path)


def test_w11_frozen_marker_near_match_fails_closed_without_live_fixture(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "w11-marker-near-match.json"
    _raw_p16_crossover_white_containment_action(
        action_path,
        w11.STAGE,
        marker_role=(
            "OTP_WHITE_RAW_P16_CROSSOVER_W11_T4_V5_COMPLETE_TERMINAL_EXTRA"
        ),
    )

    with pytest.raises(camera.CameraCaptureEvidenceError, match="marker binding"):
        camera._load_action_result(action_path)


def _diagnostics() -> Mapping[str, Any]:
    return {
        "backend": "DSHOW",
        "authenticated_device": _authenticated_device(),
        "set_results": {
            "fourcc": True,
            "frame_width": True,
            "frame_height": True,
            "fps": True,
        },
        "effective_settings_before_frame": {
            "fourcc": "MJPG",
            "frame_width": 1920,
            "frame_height": 1080,
        },
        "effective_settings_after_frame": {
            "fourcc": "MJPG",
            "frame_width": 1920,
            "frame_height": 1080,
        },
        "warmup_frames_completed": 3,
        "read_failures": 0,
        "frame_retrieved_at": "2026-08-28T08:00:00.000+08:00",
        "frame_retrieved_at_utc": "2026-08-28T00:00:00.000+00:00",
    }


def _live_inputs(tmp_path: Path) -> dict[str, Any]:
    action = tmp_path / "action.json"
    _action(action)
    return {
        "action_result_path": action,
        "photo_path": tmp_path / "camera-action-02.jpg",
        "sidecar_path": tmp_path / "camera-action-02.capture.json",
        "camera_id": camera.TARGET_CAMERA_LOGICAL_ID,
        "camera_instance_id": _authenticated_device()["pnp_instance_id"],
        "mount_id": "temporary-partial-v1",
        "coverage_scope": camera.COVERAGE_PARTIAL,
        "warmup_frames": 3,
        "_device_resolver": _authenticated_device,
    }


def test_import_has_no_eager_camera_module() -> None:
    assert "cv2" not in camera.__dict__


def _dshow_inventory(*devices: tuple[str, str]) -> str:
    lines: list[str] = []
    for friendly_name, alternative_name in devices:
        lines.extend(
            (
                f'[dshow @ 00000000] "{friendly_name}" (video)',
                f'[dshow @ 00000000]   Alternative name "{alternative_name}"',
            )
        )
    return "\n".join(lines)


def test_dshow_parser_binds_target_by_vid_pid_not_friendly_name_or_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binocular = (
        r"@device_pnp_\\?\usb#vid_1bcf&pid_0b15&mi_00#"
        r"7&1340e285&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
    )
    output = _dshow_inventory(
        ("USB Camera", binocular),
        (
            camera.TARGET_CAMERA_FRIENDLY_NAME,
            _authenticated_device(index=1)["alternative_name"],
        ),
        ("OBS Virtual Camera", "@device_sw_{virtual}"),
    )
    monkeypatch.setattr(camera.shutil, "which", lambda _name: "ffmpeg.exe")
    monkeypatch.setattr(
        camera.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=b"", stderr=output.encode("utf-8"), returncode=1
        ),
    )

    resolved = camera._resolve_exact_mf1750_camera()

    assert resolved == _authenticated_device(index=1)
    assert camera.EXCLUDED_BINOCULAR_USB_TOKEN not in resolved["alternative_name"]


@pytest.mark.parametrize(
    "devices, error",
    (
        (
            (("USB Camera", "@device_sw_{not-the-target}"),),
            "exactly one",
        ),
        (
            (
                (
                    camera.TARGET_CAMERA_FRIENDLY_NAME,
                    _authenticated_device()["alternative_name"],
                ),
                (
                    camera.TARGET_CAMERA_FRIENDLY_NAME,
                    _authenticated_device(index=1)["alternative_name"].replace(
                        "22675d4e", "aaaaaaaa"
                    ),
                ),
            ),
            "exactly one",
        ),
    ),
)
def test_exact_resolver_fails_closed_when_target_is_absent_or_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
    devices: tuple[tuple[str, str], ...],
    error: str,
) -> None:
    output = _dshow_inventory(*devices)
    monkeypatch.setattr(camera.shutil, "which", lambda _name: "ffmpeg.exe")
    monkeypatch.setattr(
        camera.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            stdout=b"", stderr=output.encode("utf-8"), returncode=1
        ),
    )

    with pytest.raises(camera.CameraCaptureEvidenceError, match=error):
        camera._resolve_exact_mf1750_camera()


@pytest.mark.parametrize(
    ("updates", "error"),
    (
        (
            {"camera_id": "USB_VID_1BCF_PID_0B15"},
            "excluded binocular",
        ),
        (
            {"camera_instance_id": (r"USB\VID_1BCF&PID_0B15&MI_00\7&1340E285&0&0000")},
            "excluded binocular",
        ),
        ({"camera_index": 1}, "index fallback is forbidden"),
    ),
)
def test_live_capture_rejects_caller_identity_or_index_spoof_before_backend(
    tmp_path: Path, updates: Mapping[str, Any], error: str
) -> None:
    inputs = _live_inputs(tmp_path)
    inputs.update(updates)
    called = False

    def backend(*_args: Any) -> tuple[bytes, Mapping[str, Any]]:
        nonlocal called
        called = True
        return _jpeg(), _diagnostics()

    with pytest.raises(camera.CameraCaptureEvidenceError, match=error):
        camera.capture(**inputs, capture_backend=backend)
    assert called is False
    assert not inputs["photo_path"].exists()
    assert not inputs["sidecar_path"].exists()


def test_live_capture_rejects_backend_identity_substitution(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    diagnostics = dict(_diagnostics())
    diagnostics["authenticated_device"] = {
        **_authenticated_device(),
        "alternative_name": (
            r"@device_pnp_\\?\usb#vid_1bcf&pid_0b15&mi_00#"
            r"7&1340e285&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
        ),
        "pnp_instance_id": (r"USB\VID_1BCF&PID_0B15&MI_00\7&1340E285&0&0000"),
        "usb_vid": "1BCF",
        "usb_pid": "0B15",
    }

    with pytest.raises(camera.CameraCaptureEvidenceError, match="48MP target"):
        camera.capture(
            **inputs,
            capture_backend=lambda *_args: (_jpeg(), diagnostics),
        )
    assert not inputs["photo_path"].exists()
    assert not inputs["sidecar_path"].exists()


def test_live_capture_rejects_non_directshow_backend_before_persist(
    tmp_path: Path,
) -> None:
    inputs = _live_inputs(tmp_path)
    diagnostics = {**_diagnostics(), "backend": "MSMF"}

    with pytest.raises(camera.CameraCaptureEvidenceError, match="not.*DirectShow"):
        camera.capture(
            **inputs,
            capture_backend=lambda *_args: (_jpeg(), diagnostics),
        )
    assert not inputs["photo_path"].exists()
    assert not inputs["sidecar_path"].exists()


def test_live_manual_profile_can_require_every_setting_write(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    diagnostics = dict(_diagnostics())
    diagnostics["set_results"] = {
        **diagnostics["set_results"],
        "frame_height": False,
    }

    with pytest.raises(camera.CameraCaptureEvidenceError, match="setting writes"):
        camera.capture(
            **inputs,
            require_all_setting_writes=True,
            capture_backend=lambda *_args: (_jpeg(), diagnostics),
        )
    assert not inputs["photo_path"].exists()
    assert not inputs["sidecar_path"].exists()


def test_v3_factory_white_terminal_descriptor_marker_role_binding_is_accepted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v3-white-action.json"
    root = _v3_factory_white_action(path)

    _payload, _loaded, identity = camera._load_action_result(path)

    assert identity["descriptor_id"] == root["action"]["descriptor_id"]
    assert identity["role"] == camera.FACTORY_OTP_WHITE_ACTION_ROLE


@pytest.mark.parametrize(
    "marker_role",
    (
        "OTP_WHITE_GUARD_DIRECTION_AB_CONTAINMENT",
        "OTP_WHITE_GUARD_DIRECTION_AB_SUCCESSOR",
    ),
)
def test_postfixed_factory_white_marker_order_is_strictly_accepted(
    tmp_path: Path, marker_role: str
) -> None:
    path = tmp_path / "guard-direction-ab-white-action.json"
    root = _v3_factory_white_action(
        path,
        marker_role=marker_role,
        marker_version=1,
    )

    _payload, _loaded, identity = camera._load_action_result(path)

    assert identity["descriptor_id"] == root["action"]["descriptor_id"]
    assert identity["role"] == camera.FACTORY_OTP_WHITE_ACTION_ROLE


@pytest.mark.parametrize(
    "marker_role",
    (
        "GUARD_DIRECTION_AB_CONTAINMENT",
        "OTP_WHITE_GUARD_DIRECTION_AB_RECOVERY",
        "OTP_WHITE_GUARD_DIRECTION_AB_CONTAINMENT_EXTRA",
        "OTP_WHITE__GUARD_DIRECTION_AB_CONTAINMENT",
    ),
)
def test_postfixed_factory_white_marker_order_rejects_malformed_roles(
    tmp_path: Path, marker_role: str
) -> None:
    path = tmp_path / "near-match-guard-direction-ab-white-action.json"
    _v3_factory_white_action(path, marker_role=marker_role, marker_version=1)

    with pytest.raises(camera.CameraCaptureEvidenceError, match="marker binding"):
        camera._load_action_result(path)


def test_same_r20_aa_abort_containment_is_strictly_accepted_for_retained_capture(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "aa-abort-white-action.json"
    root = _v3_factory_white_action(
        action_path,
        action_role=camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        marker_role=camera.SAME_R20_AA_ABORT_OTP_WHITE_MARKER_ROLE,
    )
    photo_path = tmp_path / "aa-abort-white-retained.jpg"
    sidecar_path = tmp_path / "aa-abort-white-retained.capture.json"
    requested = {
        "autofocus": 0,
        "focus": 79,
        "auto_exposure": 0.25,
        "exposure": -5,
        "auto_white_balance": 0,
        "white_balance_temperature": 6500,
    }
    effective = {
        **camera.DEFAULT_REQUESTED_SETTINGS,
        "fourcc": "MJPG",
        "frame_width": 1920,
        "frame_height": 1080,
        "fps": 30.0,
        **requested,
    }
    set_results = {
        field: True for field, value in effective.items() if value is not None
    }

    result = camera.capture_locked_retained(
        action_result_path=action_path,
        photo_path=photo_path,
        sidecar_path=sidecar_path,
        camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
        camera_instance_id=_authenticated_device()["pnp_instance_id"],
        mount_id="mf1750-g1",
        coverage_scope=camera.COVERAGE_FULL,
        requested_settings=requested,
        warmup_frames=3,
        automated_verdict="INCONCLUSIVE",
        assessment_confidence="low",
        capture_backend=lambda *_args: (
            _jpeg(),
            {
                "backend": "DSHOW",
                "authenticated_device": _authenticated_device(),
                "set_results": set_results,
                "effective_settings_before_frame": effective,
                "effective_settings_after_frame": dict(effective),
                "warmup_frames_completed": 3,
                "read_failures": 0,
                "frame_retrieved_at": "2026-08-28T08:00:00.000+08:00",
                "frame_retrieved_at_utc": "2026-08-28T00:00:00.000+00:00",
            },
        ),
        _device_resolver=_authenticated_device,
    )

    assert result["role"] == camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE
    assert result["descriptor_id"] == root["action"]["descriptor_id"]
    assert result["action_result"]["visible_refreshes"] == 1


def test_raw_p16_endpoint_gallery_containment_exact_binding_is_accepted(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "raw-p16-endpoint-gallery-white-action.json"
    root = _raw_p16_endpoint_gallery_white_containment_action(action_path)

    _payload, _loaded, identity = camera._load_action_result(action_path)

    binding = camera.RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_BINDING
    assert identity["campaign_id"] == binding["campaign_id"]
    assert identity["test_id"] == binding["test_id"]
    assert identity["contract_id"] == binding["contract_id"]
    assert identity["action_id"] == binding["action_id"]
    assert identity["descriptor_id"] == binding["descriptor_id"]
    assert identity["role"] == camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE
    assert root["terminal_report"]["transaction_descriptor_marker"] == binding["marker"]


@pytest.mark.parametrize(
    "updates",
    (
        {"profile_id": "WF20_25"},
        {"campaign_id": "EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V2"},
        {"test_id": "EC5-RAW-P16-ENDPOINT-GALLERY-WHITE-CONTAINMENT-V2"},
        {"contract_id": "9" * 64},
        {"build_tag": "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V2"},
        {"action_id": "8" * 64},
        {"descriptor_id": "7" * 64},
        {"marker_version": 2},
    ),
)
def test_raw_p16_endpoint_gallery_containment_near_matches_fail_closed(
    tmp_path: Path, updates: Mapping[str, Any]
) -> None:
    action_path = tmp_path / "raw-p16-near-match.json"
    _raw_p16_endpoint_gallery_white_containment_action(action_path, **updates)

    with pytest.raises(
        camera.CameraCaptureEvidenceError,
        match="RAW-P16 endpoint-gallery containment allowlist binding differs",
    ):
        camera._load_action_result(action_path)


def test_raw_p16_like_marker_does_not_widen_containment_admission(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "raw-p16-like-marker.json"
    _raw_p16_endpoint_gallery_white_containment_action(
        action_path,
        marker_role="OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_OTHER_CONTAINMENT",
    )

    with pytest.raises(camera.CameraCaptureEvidenceError, match="marker binding"):
        camera._load_action_result(action_path)


@pytest.mark.parametrize(
    "stage",
    tuple(
        item["stage"] for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
    ),
)
def test_raw_p16_crossover_white_exact_frozen_bindings_are_accepted(
    tmp_path: Path, stage: str
) -> None:
    action_path = tmp_path / f"{stage}-white-action.json"
    root = _raw_p16_crossover_white_containment_action(action_path, stage)

    _payload, _loaded, identity = camera._load_action_result(action_path)

    binding = next(
        item
        for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
        if item["stage"] == stage
    )
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "action_id",
        "descriptor_id",
        "role",
    ):
        assert identity[field] == binding[field]
    assert root["terminal_report"]["transaction_descriptor_marker"] == binding["marker"]


@pytest.mark.parametrize(
    "updates",
    (
        {"profile_id": "WF20_25"},
        {"campaign_id": "EC5_RAW_P16_CROSSOVER_W1_AFTER_T1_WHITE_V2"},
        {"test_id": "EC5-RAW-P16-CROSSOVER-W1-AFTER-T1-WHITE-V2"},
        {"contract_id": "9" * 64},
        {"build_tag": "MF1750_EC5_RAW_P16_CROSSOVER_W1_WHITE_V2"},
        {"firmware_sha256": "8" * 64},
        {"action_id": "7" * 64},
        {"descriptor_id": "6" * 64},
        {"action_role": "FACTORY_OTP_WHITE_RECOVERY"},
        {"marker_version": 2},
        {"marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W1_EXTRA"},
    ),
)
def test_raw_p16_crossover_white_near_matches_fail_closed(
    tmp_path: Path, updates: Mapping[str, Any]
) -> None:
    action_path = tmp_path / "crossover-white-near-match.json"
    _raw_p16_crossover_white_containment_action(action_path, "w1-after-t1", **updates)

    with pytest.raises(
        camera.CameraCaptureEvidenceError,
        match="crossover white containment allowlist|role binding|marker binding",
    ):
        camera._load_action_result(action_path)


@pytest.mark.parametrize(
    "updates",
    (
        {"profile_id": "WF20_25"},
        {
            "campaign_id": (
                "EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_"
                "SUCCESSOR_WHITE_V2"
            )
        },
        {
            "test_id": (
                "EC5-RAW-P16-CROSSOVER-W4-AFTER-T3-AC-PROFILE-FOLLOWING-"
                "SUCCESSOR-WHITE-V2"
            )
        },
        {"contract_id": "9" * 64},
        {
            "build_tag": (
                "MF1750_EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_"
                "FOLLOWING_SUCCESSOR_WHITE_V2"
            )
        },
        {"firmware_sha256": "8" * 64},
        {"action_id": "7" * 64},
        {"descriptor_id": "6" * 64},
        {"action_role": "FACTORY_OTP_WHITE_RECOVERY"},
        {"marker_version": 2},
        {
            "marker_role": (
                "OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_EXTRA"
            )
        },
    ),
)
def test_raw_p16_crossover_w4_profile_following_near_matches_fail_closed(
    tmp_path: Path, updates: Mapping[str, Any]
) -> None:
    action_path = tmp_path / "w4-profile-following-white-near-match.json"
    _raw_p16_crossover_white_containment_action(
        action_path,
        "w4-after-t3-ac-profile-following-successor-v1",
        **updates,
    )

    with pytest.raises(
        camera.CameraCaptureEvidenceError,
        match="crossover white containment allowlist|role binding|marker binding",
    ):
        camera._load_action_result(action_path)


def test_explicit_generic_containment_role_cannot_bypass_marker_allowlist(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "explicit-generic-containment-role.json"
    root = _v3_factory_white_action(
        action_path,
        action_role=camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        marker_role="OTP_WHITE_UNREVIEWED_CONTAINMENT",
    )
    unsigned = dict(root)
    unsigned.pop("integrity")
    terminal = {
        **unsigned["terminal_report"],
        "role": camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
    }
    unsigned["terminal_report"] = terminal
    transcript = [dict(item) for item in unsigned["transcript"]]
    transcript[-1] = {**transcript[-1], "body": terminal}
    unsigned["transcript"] = transcript
    action_path.write_text(json.dumps(camera._seal(unsigned)), encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match="marker binding"):
        camera._load_action_result(action_path)


@pytest.mark.parametrize(
    ("action_role", "marker_role"),
    (
        (
            camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
            "BRIGHTNESS_REDPINK_OTP_WHITE_SUCCESSOR",
        ),
        (
            "UNRELATED_CONTAINMENT",
            camera.SAME_R20_AA_ABORT_OTP_WHITE_MARKER_ROLE,
        ),
    ),
)
def test_same_r20_aa_abort_marker_does_not_admit_other_role_pairs(
    tmp_path: Path, action_role: str, marker_role: str
) -> None:
    path = tmp_path / "wrong-role-pair.json"
    _v3_factory_white_action(
        path,
        action_role=action_role,
        marker_role=marker_role,
    )

    with pytest.raises(camera.CameraCaptureEvidenceError, match="role binding|marker"):
        camera._load_action_result(path)


@pytest.mark.parametrize(
    ("root_update", "terminal_update", "driver_update", "error"),
    (
        ({"visible_refreshes": 2}, {}, {}, "exactly one visible refresh"),
        ({}, {"driver_called": False}, {}, "driver_called"),
        ({}, {"driver_call_count_for_action": 2}, {}, "driver_call_count"),
        ({}, {"total_driver_call_count": 2}, {}, "total_driver_call_count"),
        ({}, {}, {"sequence_ok": False}, "sequence_ok"),
        ({}, {}, {"wait_timeout": True}, "wait_timeout"),
    ),
)
def test_same_r20_aa_abort_containment_execution_gates_fail_closed(
    tmp_path: Path,
    root_update: Mapping[str, Any],
    terminal_update: Mapping[str, Any],
    driver_update: Mapping[str, Any],
    error: str,
) -> None:
    path = tmp_path / "tampered-aa-abort-white.json"
    root = _v3_factory_white_action(
        path,
        action_role=camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        marker_role=camera.SAME_R20_AA_ABORT_OTP_WHITE_MARKER_ROLE,
    )
    unsigned = dict(root)
    unsigned.pop("integrity")
    terminal = {**unsigned["terminal_report"], **terminal_update}
    terminal["driver"] = {**terminal["driver"], **driver_update}
    unsigned.update(root_update)
    unsigned["terminal_report"] = terminal
    transcript = [dict(item) for item in unsigned["transcript"]]
    transcript[-1] = {**transcript[-1], "body": terminal}
    unsigned["transcript"] = transcript
    path.write_text(json.dumps(camera._seal(unsigned)), encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match=error):
        camera._load_action_result(path)


def test_v3_factory_white_terminal_descriptor_must_match_action(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v3-white-action.json"
    root = _v3_factory_white_action(path)
    root = dict(root)
    root.pop("integrity")
    root["terminal_report"] = {
        **root["terminal_report"],
        "transaction_descriptor_sha256": "9" * 64,
    }
    path.write_text(json.dumps(camera._seal(root)), encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match="descriptor"):
        camera._load_action_result(path)


@pytest.mark.parametrize(
    "terminal_update, error",
    (
        ({"transaction_descriptor_marker": None}, "marker"),
        (
            {
                "transaction_descriptor_marker": (
                    "MF1750_EC5_TX_DESCRIPTOR_V3|PROFILE=OTHER|"
                    "ROLE=BRIGHTNESS_REDPINK_OTP_WHITE_SUCCESSOR|SHA256=" + "2" * 64
                )
            },
            "marker binding",
        ),
        (
            {
                "transaction_descriptor_marker": (
                    "MF1750_EC5_TX_DESCRIPTOR_V3|PROFILE=WF23_25|"
                    "ROLE=UNRELATED_ACTION|SHA256=" + "2" * 64
                )
            },
            "marker binding",
        ),
    ),
)
def test_missing_terminal_role_requires_strict_factory_white_marker_binding(
    tmp_path: Path, terminal_update: Mapping[str, Any], error: str
) -> None:
    path = tmp_path / "v3-white-action.json"
    root = _v3_factory_white_action(path)
    root = dict(root)
    root.pop("integrity")
    root["terminal_report"] = {**root["terminal_report"], **terminal_update}
    path.write_text(json.dumps(camera._seal(root)), encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match=error):
        camera._load_action_result(path)


def test_explicit_terminal_role_remains_strict_even_with_valid_v3_marker(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v3-white-action.json"
    root = _v3_factory_white_action(path)
    root = dict(root)
    root.pop("integrity")
    root["terminal_report"] = {**root["terminal_report"], "role": "TAMPERED"}
    path.write_text(json.dumps(camera._seal(root)), encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match="role differ"):
        camera._load_action_result(path)


def test_missing_terminal_boot_nonce_requires_bound_factory_white_transcript(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v3-white-action.json"
    root = _v3_factory_white_action(path)
    root = dict(root)
    root.pop("integrity")
    transcript = [dict(item) for item in root["transcript"]]
    transcript[0]["body"] = {**transcript[0]["body"], "boot_nonce": "wrong"}
    root["transcript"] = transcript
    path.write_text(json.dumps(camera._seal(root)), encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match="boot nonce differs"):
        camera._load_action_result(path)


def test_explicit_terminal_boot_nonce_remains_strict(tmp_path: Path) -> None:
    path = tmp_path / "legacy-action.json"
    root = _action(path)
    root = dict(root)
    root.pop("integrity")
    root["terminal_report"] = {
        **root["terminal_report"],
        "boot_nonce": "different",
    }
    path.write_text(json.dumps(camera._seal(root)), encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match="boot nonce differs"):
        camera._load_action_result(path)


def test_default_backend_records_every_cap_set_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    property_names = (
        "FRAME_WIDTH",
        "FRAME_HEIGHT",
        "FPS",
        "AUTOFOCUS",
        "FOCUS",
        "AUTO_EXPOSURE",
        "EXPOSURE",
        "AUTO_WB",
        "WB_TEMPERATURE",
        "BRIGHTNESS",
        "CONTRAST",
        "SATURATION",
        "HUE",
        "FOURCC",
    )
    properties = {name: index + 10 for index, name in enumerate(property_names)}
    set_calls: list[tuple[int, float | int]] = []
    fourcc_value = sum(ord(char) << (8 * index) for index, char in enumerate("MJPG"))

    class FakeCapture:
        def isOpened(self) -> bool:
            return True

        def set(self, prop: int, value: float | int) -> bool:
            set_calls.append((prop, value))
            return prop != properties["EXPOSURE"]

        def get(self, prop: int) -> float:
            if prop == properties["FOURCC"]:
                return float(fourcc_value)
            return 0.0

        def read(self):
            return True, object()

        def getBackendName(self) -> str:
            return "DSHOW"

        def release(self) -> None:
            pass

    fake = SimpleNamespace(
        CAP_DSHOW=700,
        VideoCapture=lambda *_args: FakeCapture(),
        VideoWriter_fourcc=lambda *_args: fourcc_value,
        imencode=lambda *_args: (True, bytearray(b"jpeg")),
        IMWRITE_JPEG_QUALITY=1,
        error=RuntimeError,
        **{f"CAP_PROP_{name}": value for name, value in properties.items()},
    )
    monkeypatch.setitem(sys.modules, "cv2", fake)
    settings = camera._normalise_requested_settings(
        {
            "autofocus": 0,
            "focus": 79,
            "auto_exposure": 0.25,
            "exposure": -5,
            "auto_white_balance": 0,
            "white_balance_temperature": 6500,
        }
    )

    payload, diagnostics = camera._default_capture_backend(
        0, settings, 1, 95, _device_resolver=_authenticated_device
    )

    assert payload == b"jpeg"
    assert diagnostics["authenticated_device"] == _authenticated_device()
    assert diagnostics["set_results"] == {
        "fourcc": True,
        "frame_width": True,
        "frame_height": True,
        "fps": True,
        "autofocus": True,
        "focus": True,
        "auto_exposure": True,
        "exposure": False,
        "auto_white_balance": True,
        "white_balance_temperature": True,
    }
    assert len(set_calls) == len(diagnostics["set_results"])


def test_live_capture_writes_one_photo_and_valid_sidecar(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    calls: list[tuple[int, Mapping[str, Any], int, int]] = []

    def backend(
        index: int, settings: Mapping[str, Any], warmup: int, quality: int
    ) -> tuple[bytes, Mapping[str, Any]]:
        calls.append((index, settings, warmup, quality))
        return _jpeg(), _diagnostics()

    result = camera.capture(**inputs, capture_backend=backend)

    assert len(calls) == 1
    assert result["capture_binding"] == camera.BINDING_LIVE
    assert result["action_id"] == "1" * 64
    assert result["photo"]["path"] == "camera-action-02.jpg"
    assert result["photo"]["origin"] == "captured_by_tool"
    assert result["photo"]["width"] == 64
    assert result["photo"]["height"] == 48
    assert result["coverage"]["full_panel_visible"] is False
    assert result["automated_assessment"]["verdict"] == "INCONCLUSIVE"
    assert result["automated_assessment"]["candidate_detected"] is None
    assert result["camera"]["camera_id"] == camera.TARGET_CAMERA_FRIENDLY_NAME
    assert (
        result["camera"]["instance_id"] == _authenticated_device()["alternative_name"]
    )
    assert result["camera"]["index"] == 0
    assert result["camera"]["set_results"] == {
        "fourcc": True,
        "frame_width": True,
        "frame_height": True,
        "fps": True,
    }
    assert camera.validate_capture_evidence(inputs["sidecar_path"]) == result


def test_locked_retained_capture_preserves_live_camera_diagnostics_without_live_claim(
    tmp_path: Path,
) -> None:
    inputs = _live_inputs(tmp_path)
    inputs["coverage_scope"] = camera.COVERAGE_FULL
    inputs["mount_id"] = "locked-full-panel-g1"
    requested = {
        "autofocus": 0,
        "focus": 79,
        "auto_exposure": 0.25,
        "exposure": -5,
        "auto_white_balance": 0,
        "white_balance_temperature": 6500,
    }
    effective = {
        "fourcc": "MJPG",
        "frame_width": 1920,
        "frame_height": 1080,
        "fps": 30,
        "autofocus": 2,
        "focus": 79,
        "auto_exposure": -1,
        "exposure": -5,
        "auto_white_balance": 0,
        "white_balance_temperature": 6500,
        "brightness": 32,
        "contrast": 34,
        "saturation": 32,
        "hue": 32,
    }
    set_results = {
        "fourcc": True,
        "frame_width": True,
        "frame_height": True,
        "fps": True,
        "autofocus": True,
        "focus": True,
        "auto_exposure": True,
        "exposure": True,
        "auto_white_balance": True,
        "white_balance_temperature": True,
    }

    result = camera.capture_locked_retained(
        **inputs,
        requested_settings=requested,
        limitations=("retained screen state; historical action continuity unproven",),
        capture_backend=lambda *_args: (
            _jpeg(),
            {
                "backend": "DSHOW",
                "authenticated_device": _authenticated_device(),
                "set_results": set_results,
                "effective_settings_before_frame": effective,
                "effective_settings_after_frame": dict(effective),
                "warmup_frames_completed": 3,
                "read_failures": 0,
                "frame_retrieved_at": "2026-08-28T08:00:00.000+08:00",
                "frame_retrieved_at_utc": "2026-08-28T00:00:00.000+00:00",
            },
        ),
    )

    assert result["capture_binding"] == camera.BINDING_LOCKED_RETAINED
    assert result["photo"]["origin"] == "captured_by_tool"
    assert result["capture_timing"]["clock_source"] == "host_wall_clock"
    assert result["camera"]["set_results"] == set_results
    assert result["camera"]["effective_settings_before_frame"] == effective
    assert result["automated_assessment"]["verdict"] == "INCONCLUSIVE"
    assert camera.validate_capture_evidence(inputs["sidecar_path"]) == result


def test_locked_retained_capture_fails_closed_when_a_setting_write_fails(
    tmp_path: Path,
) -> None:
    inputs = _live_inputs(tmp_path)
    diagnostics = dict(_diagnostics())
    diagnostics["set_results"] = {
        "fourcc": True,
        "frame_width": True,
        "frame_height": False,
        "fps": True,
        "autofocus": True,
        "focus": True,
        "auto_exposure": True,
        "exposure": True,
        "auto_white_balance": True,
        "white_balance_temperature": True,
    }

    with pytest.raises(
        camera.CameraCaptureEvidenceError, match="setting writes failed"
    ):
        camera.capture_locked_retained(
            **inputs,
            requested_settings={
                "autofocus": 0,
                "focus": 79,
                "auto_exposure": 0.25,
                "exposure": -5,
                "auto_white_balance": 0,
                "white_balance_temperature": 6500,
            },
            capture_backend=lambda *_args: (_jpeg(), diagnostics),
        )
    assert not inputs["photo_path"].exists()
    assert not inputs["sidecar_path"].exists()


def test_output_conflict_refuses_before_camera_access(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    inputs["photo_path"].write_bytes(b"occupied")
    called = False

    def backend(*_args: Any) -> tuple[bytes, Mapping[str, Any]]:
        nonlocal called
        called = True
        raise AssertionError("camera must not be accessed")

    with pytest.raises(camera.CameraCaptureEvidenceError, match="overwrite"):
        camera.capture(**inputs, capture_backend=backend)
    assert called is False
    assert inputs["photo_path"].read_bytes() == b"occupied"
    assert not inputs["sidecar_path"].exists()


def test_sidecar_conflict_cleans_only_new_photo_reservation(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    inputs["sidecar_path"].write_text("occupied", encoding="utf-8")

    with pytest.raises(camera.CameraCaptureEvidenceError, match="overwrite"):
        camera.capture(
            **inputs,
            capture_backend=lambda *_args: (_jpeg(), _diagnostics()),
        )
    assert not inputs["photo_path"].exists()
    assert inputs["sidecar_path"].read_text(encoding="utf-8") == "occupied"


def test_bad_jpeg_cleans_both_reserved_outputs(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)

    with pytest.raises(camera.CameraCaptureEvidenceError, match="JPEG"):
        camera.capture(
            **inputs,
            capture_backend=lambda *_args: (b"not a jpeg", _diagnostics()),
        )
    assert not inputs["photo_path"].exists()
    assert not inputs["sidecar_path"].exists()


def test_invalid_action_integrity_stops_before_camera_or_outputs(
    tmp_path: Path,
) -> None:
    inputs = _live_inputs(tmp_path)
    root = json.loads(inputs["action_result_path"].read_text(encoding="utf-8"))
    root["action"]["role"] = "TAMPERED"
    inputs["action_result_path"].write_text(json.dumps(root), encoding="utf-8")
    called = False

    def backend(*_args: Any) -> tuple[bytes, Mapping[str, Any]]:
        nonlocal called
        called = True
        return _jpeg(), _diagnostics()

    with pytest.raises(camera.CameraCaptureEvidenceError, match="integrity"):
        camera.capture(**inputs, capture_backend=backend)
    assert called is False
    assert not inputs["photo_path"].exists()
    assert not inputs["sidecar_path"].exists()


def test_low_confidence_cannot_claim_candidate(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    with pytest.raises(camera.CameraCaptureEvidenceError, match="partial-panel"):
        camera.capture(
            **inputs,
            automated_verdict="PASS",
            assessment_confidence="low",
            analysis_source="candidate-detector-v1",
            capture_backend=lambda *_args: (_jpeg(), _diagnostics()),
        )
    assert not inputs["photo_path"].exists()


def test_full_panel_conclusive_result_requires_analysis_source(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    inputs["coverage_scope"] = camera.COVERAGE_FULL
    inputs["mount_id"] = "full-panel-fixture-v1"
    with pytest.raises(camera.CameraCaptureEvidenceError, match="analysis_source"):
        camera.capture(
            **inputs,
            automated_verdict="PASS",
            assessment_confidence="high",
            capture_backend=lambda *_args: (_jpeg(), _diagnostics()),
        )


def test_bind_existing_is_retrospective_and_does_not_modify_photo(
    tmp_path: Path,
) -> None:
    action = tmp_path / "action.json"
    _action(action)
    photo = tmp_path / "legacy.jpg"
    original = _jpeg(colour=(100, 120, 140))
    photo.write_bytes(original)
    sidecar = tmp_path / "legacy.capture.json"

    result = camera.bind_existing(
        action_result_path=action,
        photo_path=photo,
        sidecar_path=sidecar,
        camera_id="48MP-USB-Camera",
        mount_id="temporary-partial-v1",
        coverage_scope=camera.COVERAGE_PARTIAL,
    )

    assert photo.read_bytes() == original
    assert result["capture_binding"] == camera.BINDING_RETROSPECTIVE
    assert result["photo"]["origin"] == "preexisting_read_only"
    assert result["camera"]["index"] is None
    assert result["capture_timing"]["clock_source"] == "filesystem_mtime_untrusted"
    assert result["automated_assessment"]["candidate_detected"] is None


def test_validator_detects_photo_or_sidecar_tampering(tmp_path: Path) -> None:
    inputs = _live_inputs(tmp_path)
    camera.capture(
        **inputs,
        capture_backend=lambda *_args: (_jpeg(), _diagnostics()),
    )
    inputs["photo_path"].write_bytes(_jpeg(colour=(1, 2, 3)))
    with pytest.raises(camera.CameraCaptureEvidenceError, match="byte count|SHA-256"):
        camera.validate_capture_evidence(inputs["sidecar_path"])

    second = tmp_path / "second"
    second.mkdir()
    inputs = _live_inputs(second)
    camera.capture(
        **inputs,
        capture_backend=lambda *_args: (_jpeg(), _diagnostics()),
    )
    root = json.loads(inputs["sidecar_path"].read_text(encoding="utf-8"))
    root["coverage"]["note"] = "tampered"
    inputs["sidecar_path"].write_text(json.dumps(root), encoding="utf-8")
    with pytest.raises(camera.CameraCaptureEvidenceError, match="integrity"):
        camera.validate_capture_evidence(inputs["sidecar_path"])
