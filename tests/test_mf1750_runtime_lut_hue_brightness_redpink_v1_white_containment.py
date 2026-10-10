from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping

import pytest

from tools import (
    mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_pack as old_pack,
)
from tools import (
    mf1750_runtime_lut_hue_brightness_redpink_v1_pack as brightness_pack,
)
from tools import (
    mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment_once as once,
)
from tools import (
    mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment_pack as pack,
)
from tools import (
    mf1750_runtime_lut_hue_brightness_yellow_olive_v1_white_containment_pack as yellow_pack,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNING_SHA = pack.FIRMWARE_ELF_SHA256


def _identity() -> dict[str, Any]:
    return {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "source_main_contract_exact_binding": True,
        "source_main_device_enforced_same_boot": True,
        "source_main_direct_exact_post_resume_after_reboot": False,
        "source_main_nvs_boot_key": brightness_pack.NVS_BOOT_KEY,
        "main_campaign_resume_after_containment": False,
        "containment_terminal_for_source_campaign": True,
        "ordinal4_no_visible_difference_branch": True,
        "source_main_ordinals_5_and_6_forbidden_after_branch": True,
        "relay_off_required_before_containment": True,
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


def _status(*, busy: int = 1) -> dict[str, Any]:
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
        "valid": False,
        **_identity(),
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
        "valid": True,
        **_identity(),
        "profile_id": pack.PROFILE_ID,
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
    def __init__(self, *, busy: int = 1, expected_claim: Path | None = None) -> None:
        self.busy = busy
        self.expected_claim = expected_claim
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
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        if self.expected_claim is not None:
            if len(self.calls) <= 4:
                assert method == "GET"
                assert not self.expected_claim.exists()
            elif method == "POST" and name == "arm":
                assert self.expected_claim.is_file()
        if method == "GET":
            if name == "version":
                return 200, _version()
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


def test_artifacts_are_exact_and_identity_is_embedded() -> None:
    report = pack.build_report()
    assert pack.FIRMWARE_BIN.is_absolute() and pack.FIRMWARE_ELF.is_absolute()
    assert pack.FIRMWARE_BIN.stat().st_size == pack.FIRMWARE_BIN_BYTES == 787_216
    assert hashlib.sha256(pack.FIRMWARE_BIN.read_bytes()).hexdigest() == (
        pack.FIRMWARE_BIN_SHA256
    )
    assert pack.FIRMWARE_ELF.stat().st_size == pack.FIRMWARE_ELF_BYTES == 13_214_292
    elf = pack.FIRMWARE_ELF.read_bytes()
    assert hashlib.sha256(elf).hexdigest() == pack.FIRMWARE_ELF_SHA256
    for marker in (
        pack.BUILD_TAG,
        pack.CONTRACT_ID,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        pack.DESCRIPTOR_MARKER,
    ):
        assert marker.encode("ascii") in elf
    assert report["contract"]["campaign_nvs_dependency"] is False


def test_identity_nvs_route_action_and_claim_are_not_reused() -> None:
    for dedicated, old in (
        (pack.BUILD_TAG, old_pack.BUILD_TAG),
        (pack.TEST_ID, old_pack.TEST_ID),
        (pack.CAMPAIGN_ID, old_pack.CAMPAIGN_ID),
        (pack.CONTRACT_ID, old_pack.CONTRACT_ID),
        (pack.NVS_NAMESPACE, old_pack.NVS_NAMESPACE),
        (pack.NVS_KEY, old_pack.NVS_KEY),
        (pack.BASE_ROUTE, old_pack.BASE_ROUTE),
        (pack.DESCRIPTOR_ID, old_pack.DESCRIPTOR_ID),
        (pack.ACTION_ID, old_pack.ACTION_ID),
        (pack.FIRMWARE_BIN_SHA256, old_pack.FIRMWARE_BIN_SHA256),
    ):
        assert dedicated != old
    for dedicated, sibling in (
        (pack.BUILD_TAG, yellow_pack.BUILD_TAG),
        (pack.TEST_ID, yellow_pack.TEST_ID),
        (pack.CAMPAIGN_ID, yellow_pack.CAMPAIGN_ID),
        (pack.CONTRACT_ID, yellow_pack.CONTRACT_ID),
        (pack.NVS_NAMESPACE, yellow_pack.NVS_NAMESPACE),
        (pack.NVS_KEY, yellow_pack.NVS_KEY),
        (pack.BASE_ROUTE, yellow_pack.BASE_ROUTE),
        (pack.DESCRIPTOR_ID, yellow_pack.DESCRIPTOR_ID),
        (pack.ACTION_ID, yellow_pack.ACTION_ID),
        (pack.ARM_INTENT, yellow_pack.ARM_INTENT),
        (pack.EXECUTE_INTENT, yellow_pack.EXECUTE_INTENT),
        (pack.CLAIM_KIND, yellow_pack.CLAIM_KIND),
    ):
        assert dedicated != sibling
    assert once.DEFAULT_CLAIMS.is_absolute()
    assert "redpink" in str(once.DEFAULT_CLAIMS)
    assert pack.CLAIM_KIND.startswith("mf1750-target-hue-redpink-brightness")


def test_containment_exactly_binds_frozen_main_contract_and_forbids_resume() -> None:
    main_contract_id = brightness_pack.build_report()["contract_id"]
    report = pack.build_report()
    contract = report["contract"]
    assert main_contract_id == pack.SOURCE_MAIN_CONTRACT_ID
    assert contract["source_campaign_id"] == brightness_pack.CAMPAIGN_ID
    assert contract["source_main_contract_id"] == main_contract_id
    assert contract["source_main_contract_exact_binding"] is True
    assert contract["source_main_device_enforced_same_boot"] is True
    assert contract["source_main_direct_exact_post_resume_after_reboot"] is False
    assert contract["source_main_nvs_boot_key"] == brightness_pack.NVS_BOOT_KEY
    assert contract["ordinal4_no_visible_difference_branch"] is True
    assert contract["source_main_ordinals_5_and_6_forbidden_after_branch"] is True
    assert contract["relay_off_required_before_containment"] is True
    assert contract["main_campaign_resume_after_containment"] is False
    assert contract["containment_terminal_for_source_campaign"] is True
    assert report["source_main_binding"] == {
        "expected_contract_id": main_contract_id,
        "observed_contract_id": main_contract_id,
        "exact": True,
        "device_enforced_same_boot": True,
        "direct_exact_post_resume_after_reboot": False,
        "nvs_boot_key": brightness_pack.NVS_BOOT_KEY,
        "resume_allowed_after_containment": False,
        "ordinal4_no_visible_difference_branch": True,
        "source_main_ordinals_5_and_6_forbidden_after_branch": True,
        "relay_off_required_before_containment": True,
    }


def test_descriptor_action_and_contract_ids_are_deterministic() -> None:
    assert pack._canonical_sha256(pack._descriptor_payload()) == pack.DESCRIPTOR_ID
    wanted_action = hashlib.sha256(
        (
            "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_ACTION_V1|"
            + pack.DESCRIPTOR_ID
        ).encode("ascii")
    ).hexdigest()
    assert wanted_action == pack.ACTION_ID
    assert (
        pack._canonical_sha256(pack._contract_payload(pack._action()))
        == pack.CONTRACT_ID
    )


def test_source_main_contract_drift_fails_pack_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pack.source_pack,
        "build_report",
        lambda: {"contract_id": "0" * 64},
    )
    with pytest.raises(ValueError, match="source main contract binding differs"):
        pack.build_report(verify_artifacts=False)


def test_describe_works_from_arbitrary_cwd_without_network(tmp_path: Path) -> None:
    script = (
        ROOT
        / "tools/mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment_once.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "describe"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["source_main_contract_id"] == pack.SOURCE_MAIN_CONTRACT_ID
    assert value["source_main_contract_exact_binding"] is True
    assert value["source_main_device_enforced_same_boot"] is True
    assert value["source_main_direct_exact_post_resume_after_reboot"] is False
    assert value["source_main_nvs_boot_key"] == brightness_pack.NVS_BOOT_KEY
    assert value["main_campaign_resume_after_containment"] is False
    assert value["containment_terminal_for_source_campaign"] is True
    assert value["independent_nvs_and_claims"] is True
    assert value["transport"] == {
        "mode": "direct_literal_private_ipv4_http",
        "proxy": False,
        "redirect": False,
    }
    assert value["diagnose_j2_off"]["network"] == {"get": 4, "post": 0}
    assert value["diagnose_j2_off"]["permanent_claims_created"] == 0
    assert value["run"]["claim_timing"] == (
        "after_four_get_j2_on_preflight_before_first_arm"
    )
    assert value["artifact_binding_status"]["firmware_bin"]["verified"] is True
    assert value["artifact_binding_status"]["firmware_elf"]["verified"] is True
    assert value["mature_host_binding"]["verified_before_import"] is True


def test_dry_validate_is_zero_io_and_all_bindings_pass() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["offline_only"] is True
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["device_network_accessed"] is False
    assert value["serial_or_com_accessed"] is False
    assert value["relay_accessed"] is False
    assert value["firmware_flashed"] is False
    assert value["display_refreshed"] is False
    assert value["source_main_contract_id"] == pack.SOURCE_MAIN_CONTRACT_ID
    assert value["source_main_contract_exact_binding"] is True
    assert value["source_main_device_enforced_same_boot"] is True
    assert value["source_main_direct_exact_post_resume_after_reboot"] is False
    assert value["main_campaign_resume_after_containment"] is False
    assert all(
        item["verified"] is True for item in value["artifact_binding_status"].values()
    )


def test_help_is_redpink_specific_and_exposes_strict_j2_off_diagnostic() -> None:
    script = (
        ROOT
        / "tools/mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment_once.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert "diagnose-j2-off" in completed.stdout
    assert "dry-validate" in completed.stdout
    assert "Red/pink-brightness" in completed.stdout
    assert "cross-palette" not in completed.stdout.lower()


def test_diagnose_j2_off_is_four_get_zero_post_zero_claim_oxcl(
    tmp_path: Path,
) -> None:
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
    assert value["report_terminal_state"] == "NOT_EXECUTED"
    sealed = _read_sealed(output)
    assert sealed["output_write_contract"] == "O_EXCL"

    second = FakeDevice(busy=0)
    with pytest.raises(once.ContainmentError, match="overwrite"):
        once.diagnose_j2_off(
            "http://192.0.2.1",
            output=output,
            confirm_j2_off=True,
            requester=second,
        )
    assert second.calls == []


def test_exact_one_action_and_duplicate_claim_are_fail_closed(tmp_path: Path) -> None:
    claims = tmp_path / "claims"
    claim_path = claims / f"{pack.ACTION_ID}.json"
    fake = FakeDevice(expected_claim=claim_path)
    result = once.run_once(
        "http://192.0.2.1",
        claims=claims,
        output=tmp_path / "result.json",
        requester=fake,
        poll_seconds=65,
        poll_count=1,
        sleeper=lambda _seconds: None,
    )
    assert result["kind"] == pack.RESULT_KIND
    assert result["running_app_elf_sha256"] == pack.FIRMWARE_ELF_SHA256
    assert result["source_main_contract_id"] == pack.SOURCE_MAIN_CONTRACT_ID
    assert result["main_campaign_resume_after_containment"] is False
    assert result["containment_terminal_for_source_campaign"] is True
    assert result["claim_timing"] == ("after_four_get_j2_on_preflight_before_first_arm")
    assert result["network"] == {"get": 5, "post": 2}
    assert [call for call in fake.calls if call[0] == "POST"] == [
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    claim = _read_sealed(claim_path)
    assert claim["kind"] == pack.CLAIM_KIND
    assert claim["state"] == (
        "permanently_claimed_after_j2_on_preflight_before_first_arm"
    )
    assert claim["source_main_contract_id"] == pack.SOURCE_MAIN_CONTRACT_ID
    assert claim["source_main_contract_exact_binding"] is True
    assert claim["main_campaign_resume_after_containment"] is False
    assert claim["preflight"] == {
        "transport": "direct_no_proxy",
        "get": 4,
        "post": 0,
        "busy": 1,
        "fresh_nvs": True,
        "report_terminal_state": "NOT_EXECUTED",
    }
    second = FakeDevice()
    with pytest.raises(once.ContainmentConsumedError, match="permanently claimed"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=tmp_path / "second.json",
            requester=second,
        )
    assert second.calls == []


def test_busy_low_fails_before_arm_and_dispatch_gate_is_compiled(
    tmp_path: Path,
) -> None:
    fake = FakeDevice(busy=0)
    claims = tmp_path / "claims"
    output = tmp_path / "result.json"
    with pytest.raises(once.ContainmentError, match="busy"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=output,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
            sleeper=lambda _seconds: None,
        )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert not [call for call in fake.calls if call[0] == "POST"]
    assert not (claims / f"{pack.ACTION_ID}.json").exists()
    attempt = _read_sealed(output)
    assert attempt["outcome"] == "preflight_failed_no_claim"
    assert attempt["claim_state"] == "not_created"
    assert attempt["network"] == {"get": 4, "post": 0}
    source = (
        ROOT
        / "src/ec5_runtime_lut_hue_brightness_redpink_v1_white_containment_main.cpp"
    ).read_text(encoding="utf-8") + (
        ROOT
        / "src/ec5_runtime_lut_hue_brightness_redpink_v1_white_containment_identity.inc"
    ).read_text(encoding="utf-8")
    for gate in (
        "arm_busy_not_idle_high",
        "execute_busy_not_idle_high",
        "dispatch_busy_not_idle_high",
    ):
        assert gate in source
    assert pack.SOURCE_MAIN_CONTRACT_ID in source
    assert 'main_campaign_resume_after_containment\\":false' in source
    assert 'source_main_device_enforced_same_boot\\":true' in source
    assert 'source_main_ordinals_5_and_6_forbidden_after_branch\\":true' in source
    for stale in (
        "target-hue-yellow-olive",
        "runtime-lut-cross-palette-partial-hold-v1/white-containment",
        "runtime-lut-ptlw-yend-ab-v1/white-containment",
        "used_yocw1",
    ):
        assert stale not in source


def test_mature_host_is_hash_bound_before_reuse() -> None:
    host = (
        ROOT
        / "tools/mf1750_runtime_lut_cross_palette_partial_hold_v1_white_containment_once.py"
    )
    assert host.stat().st_size == once.MATURE_HOST_BYTES
    assert hashlib.sha256(host.read_bytes()).hexdigest() == once.MATURE_HOST_SHA256
    runner_source = (
        ROOT
        / "tools/mf1750_runtime_lut_hue_brightness_redpink_v1_white_containment_once.py"
    ).read_text(encoding="utf-8")
    assert runner_source.index("MATURE_HOST_SHA256") < runner_source.index(
        "_SPEC.loader.exec_module(_base)"
    )


def test_wrong_running_elf_fails_after_four_gets_without_claim(tmp_path: Path) -> None:
    class WrongElfDevice(FakeDevice):
        def __call__(self, *args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
            status, value = super().__call__(*args, **kwargs)
            if args[1].endswith("/version"):
                value = dict(value)
                value["running_app_elf_sha256"] = "a" * 64
            return status, value

    fake = WrongElfDevice()
    claims = tmp_path / "claims"
    output = tmp_path / "attempt.json"
    with pytest.raises(once.ContainmentError, match="bound Red/pink artifact"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=output,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
            sleeper=lambda _seconds: None,
        )
    assert len(fake.calls) == 4
    assert not (claims / f"{pack.ACTION_ID}.json").exists()
    assert _read_sealed(output)["outcome"] == "preflight_failed_no_claim"


def test_wrong_source_main_contract_fails_after_four_gets_without_claim(
    tmp_path: Path,
) -> None:
    class WrongMainContractDevice(FakeDevice):
        def __call__(self, *args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
            status, value = super().__call__(*args, **kwargs)
            if args[1].endswith("/manifest"):
                value = dict(value)
                value["source_main_contract_id"] = "0" * 64
            return status, value

    fake = WrongMainContractDevice()
    claims = tmp_path / "claims"
    output = tmp_path / "attempt.json"
    with pytest.raises(once.ContainmentError, match="source main binding"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=output,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
            sleeper=lambda _seconds: None,
        )
    assert len(fake.calls) == 4
    assert not (claims / f"{pack.ACTION_ID}.json").exists()
    attempt = _read_sealed(output)
    assert attempt["outcome"] == "preflight_failed_no_claim"
    assert attempt["main_campaign_resume_after_containment"] is False


def test_arm_transport_error_keeps_claim_seals_attempt_and_never_retries(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims"
    claim_path = claims / f"{pack.ACTION_ID}.json"

    class ArmFailure(FakeDevice):
        def __call__(
            self,
            base_url: str,
            path: str,
            *,
            method: str,
            headers: Mapping[str, str] | None,
            timeout: float,
        ) -> tuple[int, Mapping[str, Any]]:
            if method == "POST" and path.endswith("/arm"):
                self.calls.append((method, "arm"))
                assert claim_path.is_file()
                raise OSError("synthetic ARM transport loss")
            return super().__call__(
                base_url,
                path,
                method=method,
                headers=headers,
                timeout=timeout,
            )

    fake = ArmFailure(expected_claim=claim_path)
    output = tmp_path / "attempt.json"
    with pytest.raises(once.ContainmentConsumedError, match="forbids retry"):
        once.run_once(
            "http://192.0.2.1",
            claims=claims,
            output=output,
            requester=fake,
            poll_seconds=65,
            poll_count=1,
            sleeper=lambda _seconds: None,
        )
    assert fake.calls.count(("POST", "arm")) == 1
    assert ("POST", "execute") not in fake.calls
    attempt = _read_sealed(output)
    assert attempt["outcome"] == "claimed_attempt_failed_do_not_retry"
    assert attempt["claim_state"] == "permanently_consumed_by_this_invocation"
    assert attempt["network"] == {"get": 4, "post": 1}
    assert attempt["no_retry"] is True


def test_default_requester_installs_empty_proxy_map_and_rejects_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, Any] = {}

    class Response:
        status = 200

        def read(self, _limit: int) -> bytes:
            return b'{"ok":true}'

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    class Opener:
        def open(self, request: Any, *, timeout: float) -> Response:
            observed["url"] = request.full_url
            observed["timeout"] = timeout
            return Response()

    def build_opener(*handlers: Any) -> Opener:
        observed["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(once.urllib_request, "build_opener", build_opener)
    status, value = once._default_requester(  # noqa: SLF001
        "http://192.0.2.1",
        "/api/read-only",
        method="GET",
        headers=None,
        timeout=3,
    )
    assert status == 200 and value == {"ok": True}
    handlers = observed["handlers"]
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1], once._NoRedirect)  # noqa: SLF001
    assert observed["url"] == "http://192.0.2.1/api/read-only"


def test_old_af13_artifact_is_not_a_brightness_containment_dependency() -> None:
    old_sha = old_pack.FIRMWARE_BIN_SHA256
    targets = (
        ROOT / "tools/mf1750_runtime_lut_hue_brightness_redpink_v1_pack.py",
        ROOT / "tools/mf1750_runtime_lut_hue_brightness_redpink_v1_once.py",
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_main_config.inc",
        ROOT
        / "docs/MF1750_STAGE3_TARGET_HUE_REDPINK_BRIGHTNESS_LADDER_V1_2026-08-27.md",
    )
    assert all(old_sha not in path.read_text(encoding="utf-8") for path in targets)
