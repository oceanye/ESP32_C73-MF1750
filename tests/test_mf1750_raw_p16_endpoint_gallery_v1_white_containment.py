from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

import pytest

from tools import mf1750_raw_p16_endpoint_gallery_v1_white_containment_once as once
from tools import mf1750_raw_p16_endpoint_gallery_v1_white_containment_pack as pack


ROOT = Path(__file__).resolve().parents[1]
RUNNING_SHA = pack.FIRMWARE_ELF_SHA256


def _identity() -> dict[str, Any]:
    return {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "profile_id": pack.PROFILE_ID,
        "environment": pack.ENVIRONMENT,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "running_app_elf_sha256": RUNNING_SHA,
        "contract_id": pack.CONTRACT_ID,
        "transaction_descriptor_sha256": pack.DESCRIPTOR_ID,
        "transaction_descriptor_marker": pack.DESCRIPTOR_MARKER,
    }


def _version() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-version",
        **_identity(),
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


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
        **_identity(),
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
        "actions": [once.ACTION],
        "nvs_contract": {
            "namespace": pack.NVS_NAMESPACE,
            "key": pack.NVS_KEY,
            "initial_cursor": 1,
            "terminal_cursor": 2,
            "clear_route": False,
            "persistent_across_reboot": True,
        },
    }


def _status(*, busy: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-status",
        **_identity(),
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
        "busy": busy,
        "rst": 0,
        "cs": 0,
        "cs2": 0,
        "sck": 0,
        "dc": 0,
        "mosi": 0,
    }


def _fresh_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        **_identity(),
        "valid": False,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "no_retry": True,
    }


def _complete_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "mf1750-ec5-factory-otp-white-recovery-report",
        **_identity(),
        "valid": True,
        "ordinal": 1,
        "action_id": pack.ACTION_ID,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
        "campaign_complete": True,
        "no_retry": True,
        "driver": {
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "mapping_applied": True,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "pre_command_idle_failure": False,
            "input_fnv1a": pack.FRAME_FNV1A,
            "cs1_dtm_fnv1a": pack.DTM_FNV1A,
            "cs2_dtm_fnv1a": pack.DTM_FNV1A,
            "busy_trace": {
                "idle_level": 1,
                "safe_finish": {"busy_after_pins_low": 1, "busy_after_5ms": 1},
                "final_gpio": {
                    "busy": 1,
                    "rst": 0,
                    "cs": 0,
                    "cs2": 0,
                    "sck": 0,
                    "dc": 0,
                    "mosi": 0,
                },
            },
        },
    }


class FakeDevice:
    def __init__(
        self,
        *,
        busy: int,
        expected_claim: Path | None = None,
        wrong_contract: bool = False,
    ) -> None:
        self.busy = busy
        self.expected_claim = expected_claim
        self.wrong_contract = wrong_contract
        self.executed = False
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        assert timeout > 0
        assert path.startswith(f"{pack.BASE_ROUTE}/")
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        if self.expected_claim is not None:
            if len(self.calls) <= 4:
                assert not self.expected_claim.exists()
            elif method == "POST" and name == "arm":
                assert self.expected_claim.is_file()
        if method == "GET":
            if name == "version":
                value = _version()
                if self.wrong_contract:
                    value["contract_id"] = "f" * 64
                return 200, value
            if name == "manifest":
                return 200, _manifest()
            if name == "status":
                return 200, _status(busy=self.busy)
            if name == "report":
                return 200, _complete_report() if self.executed else _fresh_report()
        assert headers is not None
        if name == "arm":
            assert headers["X-EC5-Intent"] == pack.ARM_INTENT
            return 201, {
                "accepted": True,
                "armed": True,
                **_identity(),
                "ordinal": 1,
                "action_id": pack.ACTION_ID,
                "boot_nonce": "0123456789abcdef",
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            assert headers["X-EC5-Intent"] == pack.EXECUTE_INTENT
            self.executed = True
            return 202, {
                "accepted": True,
                "job_id": 1,
                **_identity(),
                "action_id": pack.ACTION_ID,
                "execute_consumed": True,
                "no_retry": True,
            }
        raise AssertionError((method, name))


def _read_sealed(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    integrity = value.pop("integrity")
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert integrity == {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }
    return value


def test_fresh_factory_otp_white_contract_is_independent() -> None:
    report = pack.build_report(verify_artifacts=True)
    contract = report["contract"]
    assert report["contract_id"] == pack.CONTRACT_ID
    assert contract["campaign_id"] == pack.CAMPAIGN_ID
    assert contract["source_campaign_id"] == pack.SOURCE_CAMPAIGN_ID
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["startup_refresh"] is False
    assert contract["autochain"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert pack.NVS_NAMESPACE == "rp16gw_v1"
    assert pack.NVS_KEY == "used_p16w"


def test_containment_action_and_artifacts_are_frozen() -> None:
    report = pack.build_report(verify_artifacts=True)
    action = report["action"]
    assert action["role"] == "FACTORY_OTP_WHITE_CONTAINMENT"
    assert action["frame_sha256"] == (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
    )
    for key, path, size, digest in (
        (
            "firmware_bin",
            pack.FIRMWARE_BIN,
            pack.FIRMWARE_BIN_BYTES,
            pack.FIRMWARE_BIN_SHA256,
        ),
        (
            "firmware_elf",
            pack.FIRMWARE_ELF,
            pack.FIRMWARE_ELF_BYTES,
            pack.FIRMWARE_ELF_SHA256,
        ),
    ):
        payload = path.read_bytes()
        assert report["artifact_binding_status"][key]["verified"] is True
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest


def test_containment_source_identity_and_isolated_platformio() -> None:
    source = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_v1_white_containment_program.inc"
    ).read_text(encoding="utf-8")
    identity = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_v1_white_containment_identity.inc"
    ).read_text(encoding="utf-8")
    platformio = (
        ROOT / "platformio.raw_p16_endpoint_gallery_v1_white_containment.ini"
    ).read_text(encoding="utf-8")
    assert pack.CONTRACT_ID in identity
    assert pack.ACTION_ID in identity
    assert "FACTORY_OTP_WHITE_CONTAINMENT" in source
    assert "MF1750_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT" in platformio
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in platformio


def test_containment_describe_is_offline() -> None:
    value = once.describe()
    assert value["offline_only"] is True
    assert value["hardware_accessed"] is False
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["contract"]["factory_otp_white_only"] is True
    assert value["j2_on_confirmation_enforced"] is True
    assert value["diagnose_j2_off"]["network"] == {"get": 4, "post": 0}
    assert value["diagnose_j2_off"]["permanent_claims_created"] == 0
    assert value["run"]["claim_timing"] == (
        "after_four_get_j2_on_preflight_before_first_arm"
    )


def test_describe_and_help_are_offline_and_expose_diagnostic(tmp_path: Path) -> None:
    script = ROOT / "tools/mf1750_raw_p16_endpoint_gallery_v1_white_containment_once.py"
    described = subprocess.run(
        [sys.executable, str(script), "describe"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert described.returncode == 0, described.stderr
    value = json.loads(described.stdout)
    assert value["network_requests"] == 0
    assert value["transport"] == {
        "mode": "direct_literal_private_ipv4_http",
        "proxy": False,
        "redirect": False,
    }
    helped = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert helped.returncode == 0, helped.stderr
    assert "diagnose-j2-off" in helped.stdout


def test_diagnostic_is_exact_four_get_zero_post_zero_claim(tmp_path: Path) -> None:
    output = tmp_path / "diagnostic.json"
    fake = FakeDevice(busy=0)
    value = once.diagnose_j2_off(
        "http://192.0.2.1",
        output=output,
        confirm_j2_off=True,
        requester=fake,
    )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert value["network"] == {"get": 4, "post": 0}
    assert value["permanent_claims_created"] == 0
    assert value["busy"] == 0
    assert value["fresh_nvs"] is True
    assert not (tmp_path / "claims").exists()
    assert _read_sealed(output)["output_write_contract"] == "O_EXCL"


def test_diagnostic_validates_exact_contract_after_four_gets_without_claim(
    tmp_path: Path,
) -> None:
    output = tmp_path / "diagnostic-failed.json"
    fake = FakeDevice(busy=0, wrong_contract=True)
    with pytest.raises(once.ContainmentError, match="diagnostic failed"):
        once.diagnose_j2_off(
            "http://192.0.2.1",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert len(fake.calls) == 4
    attempt = _read_sealed(output)
    assert attempt["outcome"] == "j2_off_diagnostic_failed_no_claim"
    assert attempt["network"] == {"get": 4, "post": 0}
    assert attempt["permanent_claims_created"] == 0


def test_run_requires_j2_on_before_artifacts_network_or_claim(tmp_path: Path) -> None:
    fake = FakeDevice(busy=1)
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    with pytest.raises(once.ContainmentError, match="confirm-j2-on"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=output,
            requester=fake,
        )
    assert fake.calls == []
    assert not claims.exists()
    assert not output.exists()


def test_cli_passes_explicit_j2_on_confirmation_to_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, Any] = {}

    def fake_run_once(
        base_url: str,
        *,
        claims: Path,
        output: Path,
        confirm_j2_on: bool,
        timeout: float,
        poll_seconds: float,
        poll_count: int,
    ) -> dict[str, Any]:
        observed.update(
            {
                "base_url": base_url,
                "claims": claims,
                "output": output,
                "confirm_j2_on": confirm_j2_on,
                "timeout": timeout,
                "poll_seconds": poll_seconds,
                "poll_count": poll_count,
            }
        )
        return {"outcome": "synthetic_no_hardware"}

    monkeypatch.setattr(once, "run_once", fake_run_once)
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    assert (
        once.main(
            [
                "run",
                "--base-url",
                "http://192.0.2.1",
                "--confirm-j2-on",
                "--claims",
                str(claims),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert observed["confirm_j2_on"] is True
    with pytest.raises(SystemExit):
        once._parser().parse_args(  # noqa: SLF001
            [
                "run",
                "--base-url",
                "http://192.0.2.1",
                "--claims",
                str(claims),
                "--output",
                str(output),
            ]
        )


def test_run_claims_only_after_four_gets_then_executes_once(tmp_path: Path) -> None:
    claims = tmp_path / "claims"
    claim = claims / f"{pack.ACTION_ID}.json"
    output = tmp_path / "result.json"
    fake = FakeDevice(busy=1, expected_claim=claim)
    value = once.run_once(
        "http://192.0.2.1",
        claims=claims,
        output=output,
        confirm_j2_on=True,
        requester=fake,
        poll_seconds=65,
        poll_count=1,
        sleeper=lambda _seconds: None,
    )
    assert value["network"] == {"get": 5, "post": 2}
    assert value["claim_timing"] == ("after_four_get_j2_on_preflight_before_first_arm")
    assert [call for call in fake.calls if call[0] == "POST"] == [
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    sealed_claim = _read_sealed(claim)
    assert sealed_claim["preflight"] == {
        "transport": "direct_no_proxy",
        "get": 4,
        "post": 0,
        "busy": 1,
        "fresh_nvs": True,
        "report_terminal_state": "NOT_EXECUTED",
    }
    assert _read_sealed(output)["outcome"] == "complete_pass"
