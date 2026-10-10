from __future__ import annotations

import base64
import hashlib
import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_raw_p16_endpoint_gallery_pre_white_anchor_v1_pack as pack
from tools import mf1750_raw_p16_pre_white_v1_read_only_salvage as salvage


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def _claim(path: Path) -> None:
    body = {
        "schema_version": 1,
        "kind": pack.CLAIM_KIND,
        "created_at": "2026-08-28T14:48:27.547838+00:00",
        "firmware_sha256": pack.FIRMWARE_BIN_SHA256,
        "action": pack.build_report(verify_artifacts=True)["action"],
        "state": "claimed_before_first_network_request",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    body["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(_canonical(body)).hexdigest(),
    }
    path.write_text(json.dumps(body), encoding="utf-8")


def _identity() -> dict[str, Any]:
    return {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "target_campaign_id": pack.TARGET_CAMPAIGN_ID,
        "purpose": pack.PURPOSE,
        "profile_id": pack.PROFILE_ID,
        "environment": pack.ENVIRONMENT,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "running_app_elf_sha256": pack.FIRMWARE_ELF_SHA256,
        "contract_id": pack.CONTRACT_ID,
        "transaction_descriptor_sha256": pack.DESCRIPTOR_ID,
        "transaction_descriptor_marker": pack.DESCRIPTOR_MARKER,
    }


def _responses() -> dict[str, dict[str, Any]]:
    identity = _identity()
    version = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-version",
        **identity,
        "classification": pack.CLASSIFICATION,
        "action_count": 1,
        "startup_refresh": False,
        "raw_ingress": False,
        "retry": False,
        "automatic_chaining": False,
        "profile_switch": False,
        "runtime_payload_present": False,
        "live_authorized": False,
    }
    manifest = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
        **identity,
        "classification": pack.CLASSIFICATION,
        "action_count": 1,
        "one_driver_call_per_action": True,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "raw_lut_ingress": False,
        "electrical_parameter_ingress": False,
        "timing_parameter_ingress": False,
        "runtime_payload_present": False,
        "generated_include": None,
        "runtime_psr_present": False,
        "hidden_lut_command_present": False,
        "r20_present": False,
        "r21_present": False,
        "vcom_write_or_sweep": False,
        "retry": False,
        "automatic_chaining": False,
        "automatic_recovery": False,
        "profile_switch": False,
        "requires_new_exact_authorization": True,
        "actions": [pack.build_report(verify_artifacts=True)["action"]],
        "nvs_contract": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "initial_cursor": 1,
            "terminal_cursor": 2,
            "clear_route": False,
            "persistent_across_reboot": True,
        },
    }
    status = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-status",
        **identity,
        "boot_nonce": "0123456789abcdef",
        "state": "ready",
        "phase": 0,
        "phase_name": "READY",
        "cursor_raw": 1,
        "next_ordinal": 1,
        "campaign_complete": False,
        "cursor_valid": True,
        "persistent_key_present": False,
        "fixture_self_check_passed": True,
        "execute_pending": False,
        "arm_request_count": 0,
        "execute_request_count": 0,
        "total_driver_call_count": 0,
        "gpio_initialized": True,
        "busy": 1,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }
    report = {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        **identity,
        "valid": False,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "no_retry": True,
    }
    return {
        "version": version,
        "manifest": manifest,
        "status": status,
        "report": report,
    }


def test_collect_seals_exactly_four_raw_gets_and_zero_mutation(
    tmp_path: Path,
) -> None:
    claim = tmp_path / f"{pack.ACTION_ID}.json"
    output = tmp_path / "salvage.json"
    _claim(claim)
    responses = _responses()
    calls: list[tuple[str, str, float]] = []
    raw_by_name: dict[str, bytes] = {}

    def requester(origin: str, path: str, timeout: float) -> salvage.RawResponse:
        calls.append((origin, path, timeout))
        name = path.rsplit("/", 1)[-1]
        raw = json.dumps(responses[name], separators=(",", ":")).encode()
        raw_by_name[name] = raw
        return 200, {"Content-Type": "application/json"}, raw, f"{origin}{path}"

    value = salvage.collect(
        "http://192.168.1.7:80/",
        claim=claim,
        output=output,
        requester=requester,
    )

    assert [path.rsplit("/", 1)[-1] for _, path, _ in calls] == list(
        salvage.ENDPOINT_NAMES
    )
    assert value["network"] == {"get": 4, "post": 0}
    assert value["mutation"] == {
        "claim_created": 0,
        "arm_requested": 0,
        "execute_requested": 0,
        "visible_refresh_requested": 0,
    }
    assert value["validated_state"]["zero_arm_execute_driver_proven"] is True
    assert value["existing_claim"]["claim_created_by_salvage"] is False
    for item in value["transcript"]:
        raw = base64.b64decode(item["raw_body_base64"], validate=True)
        assert raw == raw_by_name[item["endpoint"]]
        assert item["raw_body_sha256"] == hashlib.sha256(raw).hexdigest()

    sealed = json.loads(output.read_text(encoding="utf-8"))
    integrity = sealed.pop("integrity")
    assert integrity["sha256"] == hashlib.sha256(_canonical(sealed)).hexdigest()


@pytest.mark.parametrize(
    "url",
    [
        "https://192.168.1.7",
        "http://example.com",
        "http://8.8.8.8",
        "http://127.0.0.1",
        "http://192.168.1.7:8080",
        "http://user@192.168.1.7",
        "http://192.168.1.7/api",
        "http://[::1]",
    ],
)
def test_strict_origin_rejects_every_non_frozen_transport(url: str) -> None:
    with pytest.raises(salvage.SalvageError):
        salvage._strict_origin(url)


def test_collect_rejects_running_elf_mismatch_and_seals_failure(
    tmp_path: Path,
) -> None:
    claim = tmp_path / f"{pack.ACTION_ID}.json"
    output = tmp_path / "failed.json"
    _claim(claim)
    responses = _responses()
    responses["version"]["running_app_elf_sha256"] = "0" * 64

    def requester(origin: str, path: str, timeout: float) -> salvage.RawResponse:
        del timeout
        name = path.rsplit("/", 1)[-1]
        raw = json.dumps(responses[name]).encode()
        return 200, {"Content-Type": "application/json"}, raw, f"{origin}{path}"

    with pytest.raises(salvage.SalvageError, match="ELF SHA-256 differs"):
        salvage.collect(
            "http://192.168.1.7",
            claim=claim,
            output=output,
            requester=requester,
        )
    sealed = json.loads(output.read_text(encoding="utf-8"))
    assert sealed["outcome"] == "read_only_salvage_failed"
    assert sealed["network"] == {"get": 4, "post": 0}
    assert sealed["mutation"] == {
        "claim_created": 0,
        "visible_refresh_requested": 0,
    }


def test_existing_output_fails_before_any_get(tmp_path: Path) -> None:
    claim = tmp_path / f"{pack.ACTION_ID}.json"
    output = tmp_path / "existing.json"
    _claim(claim)
    output.write_text("do not overwrite", encoding="utf-8")
    calls = 0

    def requester(origin: str, path: str, timeout: float) -> salvage.RawResponse:
        del origin, path, timeout
        nonlocal calls
        calls += 1
        raise AssertionError("must not run")

    with pytest.raises(salvage.SalvageError, match="refusing to overwrite"):
        salvage.collect(
            "http://192.168.1.7",
            claim=claim,
            output=output,
            requester=requester,
        )
    assert calls == 0
    assert output.read_text(encoding="utf-8") == "do not overwrite"


def test_source_has_no_proxy_no_redirect_and_no_post_surface() -> None:
    source = inspect.getsource(salvage)
    collect_source = inspect.getsource(salvage.collect)
    assert "ProxyHandler({})" in source
    assert "_RejectRedirects" in source
    assert 'method="GET"' in source
    assert 'method="POST"' not in source
    assert "_create_claim" not in source
    assert "requester(" in collect_source
    assert "ENDPOINT_NAMES" in collect_source
