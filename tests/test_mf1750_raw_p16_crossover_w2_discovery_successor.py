from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image
import pytest

from tools import mf1750_camera_capture_evidence as camera
from tools import mf1750_camera_post_capture_analysis as post_analysis
from tools import mf1750_raw_p16_crossover_position_balanced_pack as legacy
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_pack as source
from tools import mf1750_raw_p16_crossover_w2_discovery_successor_once as once
from tools import mf1750_raw_p16_crossover_w2_discovery_successor_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def _device() -> dict[str, Any]:
    return {
        "enumerator": camera.DIRECTSHOW_DEVICE_ENUMERATOR,
        "friendly_name": camera.TARGET_CAMERA_FRIENDLY_NAME,
        "alternative_name": (
            r"@device_pnp_\\?\usb#vid_32e4&pid_4801&mi_00#"
            r"6&22675d4e&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global"
        ),
        "pnp_instance_id": r"USB\VID_32E4&PID_4801&MI_00\6&22675D4E&0&0000",
        "directshow_index": 0,
        "usb_vid": "32E4",
        "usb_pid": "4801",
    }


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (64, 48), (224, 226, 221)).save(output, format="JPEG", quality=93)
    return output.getvalue()


def _diagnostics() -> Mapping[str, Any]:
    return {
        "backend": "DSHOW",
        "authenticated_device": _device(),
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
        "frame_retrieved_at": "2026-08-30T18:00:00.000+08:00",
        "frame_retrieved_at_utc": "2026-08-30T10:00:00.000+00:00",
    }


def _write_action(path: Path, *, firmware_sha256: str | None = None) -> None:
    report = pack.build_white_report()
    action = report["action"]
    binding = pack.WHITE_ARTIFACTS[pack.STAGE]
    boot_nonce = "1ffa520a2537168d"
    terminal = {
        "kind": camera.FACTORY_OTP_WHITE_REPORT_KIND,
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "profile_id": "WF23_25",
        "campaign_id": pack.CONFIG.campaign_id,
        "test_id": pack.CONFIG.test_id,
        "contract_id": report["contract_id"],
        "build_tag": pack.CONFIG.build_tag,
        "action_id": action["action_id"],
        "ordinal": 1,
        "transaction_descriptor_sha256": action["descriptor_id"],
        "transaction_descriptor_marker": pack.marker(),
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
    headers = {
        "X-EC5-Action-Id": action["action_id"],
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Build-Tag": pack.CONFIG.build_tag,
        "X-EC5-Campaign-Id": pack.CONFIG.campaign_id,
        "X-EC5-Descriptor-Id": action["descriptor_id"],
        "X-EC5-Ordinal": "1",
        "X-EC5-Test-Id": pack.CONFIG.test_id,
    }
    root = {
        "schema_version": 1,
        "kind": "test-w2-discovery-successor-white-action-result",
        "created_at": "2026-08-30T17:59:00.000+08:00",
        "outcome": "complete_pass",
        "boot_nonce": boot_nonce,
        "firmware_sha256": firmware_sha256 or binding["bin_sha256"],
        "visible_refreshes": 1,
        "action": {
            **action,
            "frame_sha256": pack.FACTORY_WHITE_FRAME_SHA256,
        },
        "terminal_report": terminal,
        "transcript": [
            {
                "endpoint": "status",
                "method": "GET",
                "status": 200,
                "headers": {},
                "body": {**shared, "boot_nonce": boot_nonce},
            },
            {
                "endpoint": "arm",
                "method": "POST",
                "status": 201,
                "headers": headers,
                "body": {
                    **shared,
                    "accepted": True,
                    "boot_nonce": boot_nonce,
                    "action_id": action["action_id"],
                    "ordinal": 1,
                },
            },
            {
                "endpoint": "execute",
                "method": "POST",
                "status": 202,
                "headers": headers,
                "body": {
                    **shared,
                    "accepted": True,
                    "action_id": action["action_id"],
                },
            },
            {
                "endpoint": "report",
                "method": "GET",
                "status": 200,
                "headers": {},
                "body": terminal,
            },
        ],
    }
    path.write_text(json.dumps(camera._seal(root), sort_keys=True), encoding="utf-8")


def test_white_contract_exactly_binds_fresh_t2_and_not_frozen_w2() -> None:
    report = pack.build_white_report()
    source_report = source.build_report()
    frozen = legacy.build_white_report("w2-after-t2")
    action = report["action"]

    assert action["source_campaign_id"] == source_report["contract"]["campaign_id"]
    assert action["source_contract_id"] == source_report["contract_id"]
    assert (
        action["source_descriptor_id"] == source_report["actions"][0]["descriptor_id"]
    )
    assert action["source_action_id"] == source_report["actions"][0]["action_id"]
    assert report["contract_id"] != frozen["contract_id"]
    assert action["descriptor_id"] != frozen["action"]["descriptor_id"]
    assert action["action_id"] != frozen["action"]["action_id"]
    assert report["contract"]["base_route"] != frozen["contract"]["base_route"]
    assert report["contract"]["nvs_namespace"] != frozen["contract"]["nvs_namespace"]
    assert pack.dry_validate()["result"] == "PASS"


def test_white_contract_is_one_factory_otp_action_without_chaining() -> None:
    contract = pack.build_white_report()["contract"]
    assert contract["action_count"] == 1
    assert contract["one_visible_refresh_per_action"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["startup_refresh"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_cpp_and_ini_bind_only_fresh_identity_and_all_six_routes() -> None:
    identity = (
        ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_identity.inc"
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    ).read_text(encoding="utf-8")
    frozen_program = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_v1_white_containment_program.inc"
    ).read_text(encoding="utf-8")
    ini = (
        ROOT / "platformio.raw_p16_crossover_w2_discovery_successor_white_v1.ini"
    ).read_text(encoding="utf-8")
    report = pack.build_white_report()

    for value in (
        pack.CONFIG.campaign_id,
        pack.CONFIG.build_tag,
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_contract_id"],
        report["action"]["source_descriptor_id"],
        report["action"]["source_action_id"],
        pack.marker(),
    ):
        assert value in identity
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f"w2-after-t2-coarse-discovery-successor-white-v1/{endpoint}" in program
    assert "MF1750_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR_WHITE_BUILD=1" in ini
    assert "EPD_ENABLE_TEST_PATTERN=0" in ini
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in ini
    assert (
        "MF1750_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR_WHITE_BUILD"
        not in frozen_program
    )


def test_runner_uses_fresh_route_claim_output_and_sealed_artifacts() -> None:
    validation = once.dry_validate()
    assert validation["result"] == "PASS"
    assert validation["artifacts_verified"] is True
    assert pack.CONFIG.base_route not in set(validation["endpoint_set"].values())
    assert all(
        endpoint.startswith(pack.CONFIG.base_route + "/")
        for endpoint in validation["endpoint_set"].values()
    )
    assert "discovery_successor" in validation["claim_root"]
    assert "DISCOVERY_SUCCESSOR" in validation["output_root"]


def test_camera_capture_and_post_analysis_accept_only_exact_successor(
    tmp_path: Path,
) -> None:
    action_path = tmp_path / "action-01-factory-otp-white.json"
    _write_action(action_path)
    _payload, _root, identity = camera._load_action_result(action_path)
    assert identity["campaign_id"] == pack.CONFIG.campaign_id
    assert identity["contract_id"] == pack.build_white_report()["contract_id"]
    assert identity["firmware_sha256"] == pack.WHITE_ARTIFACTS[pack.STAGE]["bin_sha256"]

    photo_path = tmp_path / "camera-action-01.jpg"
    capture_path = tmp_path / "camera-action-01.capture.json"
    camera.capture(
        action_result_path=action_path,
        photo_path=photo_path,
        sidecar_path=capture_path,
        camera_id=camera.TARGET_CAMERA_LOGICAL_ID,
        mount_id="mf1750-48mp-fixed-mount-v1",
        coverage_scope=camera.COVERAGE_FULL,
        warmup_frames=3,
        capture_backend=lambda *_args: (_jpeg(), _diagnostics()),
        _device_resolver=_device,
    )
    analysis_path = tmp_path / "camera-action-01.analysis.json"
    record = post_analysis.create_post_capture_analysis(
        capture_sidecar_path=capture_path,
        analysis_path=analysis_path,
        analysis_source="mf1750-white-post-capture-gate",
        model_or_algorithm_id="factory-white-relative-review-v1",
        parameters={"absolute_colour": False},
        roi={"kind": "entire_captured_frame"},
        verdict="INCONCLUSIVE",
        confidence="low",
        candidate_detected=None,
        limitations=["white confirmation remains camera-relative"],
        analyzed_at="2026-08-30T18:01:00.000+08:00",
    )
    assert record["campaign_id"] == pack.CONFIG.campaign_id
    assert post_analysis.validate_post_capture_analysis(analysis_path) == record

    tampered_path = tmp_path / "tampered-white-action.json"
    _write_action(tampered_path, firmware_sha256="f" * 64)
    with pytest.raises(
        camera.CameraCaptureEvidenceError,
        match="crossover white containment allowlist",
    ):
        camera._load_action_result(tampered_path)


def test_camera_allowlist_entry_is_a_complete_exact_tuple() -> None:
    binding = next(
        item
        for item in camera.RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
        if item["stage"] == pack.STAGE
    )
    report = pack.build_white_report()
    assert binding == {
        "stage": pack.STAGE,
        "profile_id": "WF23_25",
        "campaign_id": pack.CONFIG.campaign_id,
        "test_id": pack.CONFIG.test_id,
        "contract_id": report["contract_id"],
        "build_tag": pack.CONFIG.build_tag,
        "firmware_sha256": pack.WHITE_ARTIFACTS[pack.STAGE]["bin_sha256"],
        "action_id": report["action"]["action_id"],
        "descriptor_id": report["action"]["descriptor_id"],
        "role": camera.FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR",
        "marker": pack.marker(),
    }
