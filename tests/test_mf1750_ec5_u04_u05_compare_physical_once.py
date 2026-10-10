from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
import urllib.parse

import pytest

from tools import mf1750_ec5_u04_u05_compare_identity as identity
from tools import mf1750_ec5_u04_u05_compare_physical_once as subject


BOOT = "1234567890abcdef"
ARM_NONCE = "fedcba0987654321"
PANEL = {
    "model": "MF1750-C73",
    "serial": "TEST-PANEL",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}


class Response:
    status = 200

    def __init__(self, value: Mapping[str, Any], status: int = 200) -> None:
        self.status = status
        self.payload = json.dumps(value, separators=(",", ":")).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self) -> int:
        return self.status

    def read(self, _maximum: int) -> bytes:
        return self.payload


def nvs(*, virgin: bool) -> dict[str, Any]:
    return {
        "nvs_contract": identity.nvs_contract(),
        "legacy_key_present": True,
        "legacy_phase": 2,
        "legacy_match": True,
        "active_key_present": not virgin,
        "active_phase": 0 if virgin else 2,
        "active_virgin": virgin,
        "migration_ready": True,
    }


def version() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "kind": "mf1750-ec5-u04-u05-compare-version",
        "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "driver_api_version": subject.DRIVER_API_VERSION,
        "layout_id": identity.LAYOUT_ID,
        "compiled_codes": [4, 5],
        "automatic_execute": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "dither": False,
        "lut_modification": False,
        "retry": False,
        "recovery": False,
        "boot_fixture_guard": "exact_driver_action_validator",
        "persistent_claim": True,
        "arm_required": True,
        "execute_limit_per_binary": 1,
        "safety_scope": "accidental_post_interlock_not_hardware_authorization",
    }


def manifest() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "kind": "mf1750-ec5-compiled-fixture-manifest",
        "scope": "experimental_scaffold_not_hardware_authorization",
        "layout_id": identity.LAYOUT_ID,
        "test_id": identity.TEST_ID,
        "action_id": identity.FROZEN_ACTION_ID,
        "sequence_class": "white_initial_fixed_nodither_diagonal_crossover",
        "repetition": 1,
        "width": 1024,
        "height": 600,
        "frame_bytes": 307_200,
        "pixel_packing": "row_major_4bpp_even_x_high_nibble",
        "background_code": 1,
        "rois": subject._manifest_rois(),
        "histogram": {"1": 598_016, "4": 8_192, "5": 8_192},
        "frame_sha256": identity.FRAME_SHA256,
        "frame_fnv1a": f"0x{identity.FRAME_FNV1A:08x}",
        "cs1_dtm_sha256": identity.CS1_DTM_SHA256,
        "cs1_dtm_fnv1a": f"0x{identity.CS1_DTM_FNV1A:08x}",
        "cs2_dtm_sha256": identity.CS2_DTM_SHA256,
        "cs2_dtm_fnv1a": f"0x{identity.CS2_DTM_FNV1A:08x}",
        "mapping_cs1": [0, 0, 0, 0],
        "mapping_cs2": [1, 0, 0, 0],
        "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "otp_mode": "existing_on_chip_otp_unchanged",
        "dither": False,
        "mutation_contract": {
            "bodyless": True,
            "exact_build_test_action_boot_nonce": True,
            "arm_nonce_required_for_execute": True,
            "not_hardware_authorization": True,
        },
        "exact_driver_fixture_guard_required": True,
        **nvs(virgin=True),
        "manifest_payload_sha256": None,
        "binary_sha256": None,
        "external_build_sidecar_required": True,
    }


def status(*, busy: int, virgin: bool, boot: str = BOOT) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "kind": "mf1750-ec5-u04-u05-compare-status",
        "boot_nonce": boot,
        "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "layout_id": identity.LAYOUT_ID,
        "test_id": identity.TEST_ID,
        "action_id": identity.FROZEN_ACTION_ID,
        "state": "ready" if virgin else "completed",
        "fixture_self_check_passed": True,
        "driver_fixture_guard_passed": True,
        "claim_store_ready": True,
        "persistent_phase": 0 if virgin else 2,
        "arm_request_count": 0 if virgin else 1,
        "execute_consumed": not virgin,
        "execute_pending": False,
        "execute_request_count": 0 if virgin else 1,
        "driver_call_count": 0 if virgin else 1,
        "gpio_initialized": True,
        "busy": busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        **nvs(virgin=virgin),
    }


def virgin_report(*, boot: str = BOOT) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "kind": "mf1750-ec5-u04-u05-compare-report",
        "valid": False,
        "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "layout_id": identity.LAYOUT_ID,
        "boot_nonce": boot,
        "action_id": identity.FROZEN_ACTION_ID,
        "terminal_state": "NOT_EXECUTED",
        "error": "no_execute_report",
        "driver_fixture_guard_passed": True,
        "execute_consumed": False,
        "driver_called": False,
        "persistent_phase": 0,
        "no_retry": True,
        "no_recovery": True,
        **nvs(virgin=True),
    }


def driver() -> dict[str, Any]:
    return {
        "driver_evidence_schema_version": 2,
        "operation_id": 1,
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "mapping_applied": True,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "post_psr_busy_seen": False,
        "pre_command_idle_failure": False,
        "failure_stage": "none",
        "failure_code": 0,
        "spi_hz": 1_000_000,
        "free_psram_before": 8_000_000,
        "largest_psram_block_before": 7_500_000,
        "input_fnv1a": identity.FRAME_FNV1A,
        "cs1_dtm_fnv1a": identity.CS1_DTM_FNV1A,
        "cs2_dtm_fnv1a": identity.CS2_DTM_FNV1A,
        "total_ms": 34_000,
        "cs1_upload_ms": 2_400,
        "cs2_upload_ms": 2_400,
        "pon_ms": 180,
        "drf_ms": 21_000,
        "pof_ms": 140,
        "post_psr_ms": 5,
        "last_wait_stage": "post-display PSR",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "pre_command_busy_stage": "none",
        "safe_finish": {
            "busy_before_pins_low": 1,
            "busy_after_pins_low": 1,
            "busy_after_5ms": 1,
            "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
        },
    }


def terminal_report() -> dict[str, Any]:
    return {
        "schema_version": 3,
        "kind": "mf1750-ec5-u04-u05-compare-report",
        "valid": True,
        "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "layout_id": identity.LAYOUT_ID,
        "boot_nonce": BOOT,
        "action_id": identity.FROZEN_ACTION_ID,
        "job_id": 1,
        "terminal_state": "completed",
        "result": True,
        "driver_fixture_guard_passed": True,
        "execute_consumed": True,
        "driver_called": True,
        "driver_call_count": 1,
        "persistent_phase": 2,
        "no_retry": True,
        "no_recovery": True,
        "job_queued_at_ms": 100,
        "job_started_at_ms": 110,
        "job_finished_at_ms": 34_110,
        "driver": driver(),
        **nvs(virgin=False),
    }


def arm_response() -> dict[str, Any]:
    return {
        "accepted": True,
        "armed": True,
        "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG,
        "action_id": identity.FROZEN_ACTION_ID,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "boot_nonce": BOOT,
        "arm_nonce": ARM_NONCE,
        "persistent_phase": 1,
        "migration_ready": True,
        "safety_scope": "accidental_post_interlock_not_hardware_authorization",
        "not_hardware_authorization": True,
    }


def execute_response() -> dict[str, Any]:
    return {
        "accepted": True,
        "job_id": 1,
        "test_id": identity.TEST_ID,
        "build_tag": identity.BUILD_TAG,
        "action_id": identity.FROZEN_ACTION_ID,
        "device_api_version": identity.DEVICE_API_VERSION,
        "identity_revision": identity.IDENTITY_REVISION,
        "boot_nonce": BOOT,
        "execute_consumed": True,
        "persistent_phase": 2,
        "migration_ready": True,
        "no_retry": True,
        "no_recovery": True,
    }


def context(tmp_path: Path) -> subject.ReleaseContext:
    release = tmp_path / "release-manifest.json"
    release.write_text("{}")
    binary = tmp_path / "firmware.bin"
    binary.write_bytes(b"firmware")
    elf = tmp_path / "firmware.elf"
    elf.write_bytes(b"elf")
    prerequisite_files = subject.PrerequisiteFiles(
        *(tmp_path / name for name in (
            "old-release", "u04-result", "short", "white-result",
            "white-observation", "rc2g", "candidate-claims", "white-claims"
        ))
    )
    return subject.ReleaseContext(
        path=release.resolve(),
        root={"compiled_identity_report": {"valid": True}},
        variant={},
        release_canonical_sha256="a" * 64,
        binary_path=binary.resolve(),
        binary_sha256="b" * 64,
        elf_path=elf.resolve(),
        elf_sha256="c" * 64,
        panel=PANEL,
        prerequisites={"deep": "validated"},
        prerequisite_files=prerequisite_files,
    )


class Device:
    def __init__(self, *, busy: int, claim_path: Path | None = None, boot: str = BOOT) -> None:
        self.busy = busy
        self.boot = boot
        self.claim_path = claim_path
        self.calls: list[tuple[str, str]] = []

    def __call__(self, request, **_kwargs):
        method = request.get_method()
        path = urllib.parse.urlsplit(request.full_url).path
        self.calls.append((method, path))
        if method == "POST" and self.claim_path is not None:
            assert self.claim_path.is_file(), "claim must precede first POST"
        if path == subject.ENDPOINTS["version"]:
            return Response(version())
        if path == subject.ENDPOINTS["manifest"]:
            return Response(manifest())
        if path == subject.ENDPOINTS["status"]:
            if method == "GET" and len([call for call in self.calls if call[0] == "POST"]) >= 2:
                return Response(status(busy=1, virgin=False, boot=self.boot))
            return Response(status(busy=self.busy, virgin=True, boot=self.boot))
        if path == subject.ENDPOINTS["report"]:
            if len([call for call in self.calls if call[0] == "POST"]) >= 2:
                value = terminal_report()
                value["boot_nonce"] = self.boot
                return Response(value)
            return Response(virgin_report(boot=self.boot))
        if path == subject.ENDPOINTS["arm"]:
            value = arm_response()
            value["boot_nonce"] = self.boot
            return Response(value, 201)
        if path == subject.ENDPOINTS["execute"]:
            value = execute_response()
            value["boot_nonce"] = self.boot
            return Response(value, 202)
        raise AssertionError(path)


def test_j2_off_diagnostic_is_four_get_zero_post_zero_claim(tmp_path) -> None:
    ctx = context(tmp_path)
    evidence = tmp_path / "diagnostic.json"
    claims = tmp_path / "claims"
    device = Device(busy=0)
    result = subject.diagnose_j2_off(
        ctx,
        "http://192.168.4.1",
        confirm_j2_off=True,
        evidence_file=evidence,
        claim_registry=claims,
        _urlopen=device,
    )
    assert device.calls == [
        ("GET", subject.ENDPOINTS[name])
        for name in ("version", "manifest", "status", "report")
    ]
    assert result["get_requests"] == 4
    assert result["post_requests"] == 0
    assert result["claim_created"] is False
    assert not claims.exists()
    assert subject.validate_diagnostic(ctx, evidence)["boot_nonce"] == BOOT


def test_same_boot_run_claims_before_one_arm_and_one_execute(tmp_path) -> None:
    ctx = context(tmp_path)
    evidence = tmp_path / "diagnostic.json"
    claims = tmp_path / "claims"
    subject.diagnose_j2_off(
        ctx,
        "http://192.168.4.1",
        confirm_j2_off=True,
        evidence_file=evidence,
        claim_registry=claims,
        _urlopen=Device(busy=0),
    )
    claim_path = claims / f"{identity.FROZEN_ACTION_ID}.json"
    device = Device(busy=1, claim_path=claim_path)
    result_file = tmp_path / "result.json"
    result = subject.run_once(
        ctx,
        "http://192.168.4.1",
        authorization=subject.required_authorization(),
        diagnostic_file=evidence,
        result_file=result_file,
        claim_registry=claims,
        poll_interval_seconds=0,
        _urlopen=device,
    )
    assert result["outcome"] == "complete_pass"
    assert result["post_requests"] == 2
    assert [call for call in device.calls if call[0] == "POST"] == [
        ("POST", subject.ENDPOINTS["arm"]),
        ("POST", subject.ENDPOINTS["execute"]),
    ]
    assert subject.validate_result(ctx, result_file, claim_registry=claims)[
        "outcome"
    ] == "complete_pass"
    with pytest.raises(subject.ComparePhysicalError, match="already permanently claimed"):
        subject.diagnose_j2_off(
            ctx,
            "http://192.168.4.1",
            confirm_j2_off=True,
            evidence_file=tmp_path / "second-diagnostic.json",
            claim_registry=claims,
            _urlopen=Device(busy=0),
        )


def test_run_rejects_different_boot_before_claim_or_post(tmp_path) -> None:
    ctx = context(tmp_path)
    evidence = tmp_path / "diagnostic.json"
    claims = tmp_path / "claims"
    subject.diagnose_j2_off(
        ctx,
        "http://192.168.4.1",
        confirm_j2_off=True,
        evidence_file=evidence,
        claim_registry=claims,
        _urlopen=Device(busy=0),
    )
    device = Device(busy=1, boot="1111111111111111")
    with pytest.raises(subject.ComparePhysicalError, match="not the diagnostic boot"):
        subject.run_once(
            ctx,
            "http://192.168.4.1",
            authorization=subject.required_authorization(),
            diagnostic_file=evidence,
            result_file=tmp_path / "result.json",
            claim_registry=claims,
            poll_interval_seconds=0,
            _urlopen=device,
        )
    assert not claims.exists()
    assert all(method == "GET" for method, _ in device.calls)


def test_manifest_rejects_cs2_identity_replaced_by_cs1() -> None:
    value = manifest()
    value["cs2_dtm_sha256"] = value["cs1_dtm_sha256"]
    value["cs2_dtm_fnv1a"] = value["cs1_dtm_fnv1a"]
    with pytest.raises(subject.ComparePhysicalError, match="cs2_dtm_sha256"):
        subject._validate_manifest(value)


def test_authorization_is_exact() -> None:
    assert subject.required_authorization() == (
        "AUTHORIZE_ONE_VISIBLE_EC5_U04_U05_COMPARE__ACTION_"
        "70DB952B1D708511E1FDCB166B43CD5828FE232562B14D341D848942787D1700"
        "__NO_RETRY_NO_RECOVERY"
    )
