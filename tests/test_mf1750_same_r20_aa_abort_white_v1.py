from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

import pytest

from tools import (
    mf1750_same_r20_aa_abort_white_v1_once as once,
)
from tools import (
    mf1750_same_r20_aa_abort_white_v1_pack as pack,
)
from tools import (
    mf1750_runtime_lut_hue_brightness_redpink_v2_white_containment_pack as v2_pack,
)


ROOT = Path(__file__).resolve().parents[1]
RUNNING_SHA = pack.FIRMWARE_ELF_SHA256


def _identity() -> dict[str, Any]:
    return {
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        **once.SOURCE_MAIN_BINDING,
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


def _write_sealed(path: Path, value: Mapping[str, Any]) -> tuple[int, str, str]:
    body = dict(value)
    canonical = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    integrity_sha = hashlib.sha256(canonical).hexdigest()
    body["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": integrity_sha,
    }
    encoded = json.dumps(
        body, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False
    ).encode("utf-8")
    path.write_bytes(encoded)
    return len(encoded), hashlib.sha256(encoded).hexdigest(), integrity_sha


def test_pack_contract_and_source_termination_are_exact() -> None:
    report = pack.build_report()
    assert report["contract"]["classification"] == pack.CLASSIFICATION
    assert report["contract"]["contract_id"] == pack.CONTRACT_ID
    assert report["contract"]["source_completed_ordinal"] == 1
    assert report["contract"]["source_next_ordinal_observed"] == 2
    assert report["contract"]["source_ordinal2_consumption_forbidden"] is True
    assert report["contract"]["source_resume_forbidden"] is True
    assert report["contract"]["camera_bound_file_count"] == 8
    assert report["source_evidence"]["verified"] is True
    assert (
        report["source_evidence"]["camera_mismatch_reproduced_in_all_four_frames"]
        is True
    )
    assert len(report["source_evidence"]["camera_frames"]) == 4


def test_classification_is_cross_checked_against_cpp_and_compiled_elf() -> None:
    main = (ROOT / "src/ec5_same_r20_aa_abort_white_v1_main.cpp").read_text(
        encoding="utf-8"
    )
    match = re.search(r'kClassification\s*=\s*\n\s*"([^"]+)";', main)
    assert match is not None
    assert match.group(1) == pack.CLASSIFICATION
    elf = pack.FIRMWARE_ELF.read_bytes()
    for marker in (
        pack.CLASSIFICATION,
        pack.BUILD_TAG,
        pack.DEVICE_API_VERSION,
        pack.IDENTITY_REVISION,
        pack.BASE_ROUTE,
        pack.NVS_NAMESPACE,
        pack.NVS_KEY,
        pack.DESCRIPTOR_MARKER,
        pack.SOURCE_ACTION_FILE_SHA256,
        pack.SOURCE_REPEAT_REPORT_FILE_SHA256,
        pack.SOURCE_RELAY_OFF_RECEIPT_SHA256,
    ):
        assert marker.encode("ascii") in elf


def test_classification_is_cryptographically_inside_descriptor_and_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_descriptor = pack._canonical_sha256(pack._descriptor_payload())  # noqa: SLF001
    original_contract = pack._canonical_sha256(  # noqa: SLF001
        pack._contract_payload(pack._action())  # noqa: SLF001
    )
    assert original_descriptor == pack.DESCRIPTOR_ID
    assert original_contract == pack.CONTRACT_ID
    monkeypatch.setattr(pack, "CLASSIFICATION", f"{pack.CLASSIFICATION}_DRIFT")
    assert pack._canonical_sha256(pack._descriptor_payload()) != original_descriptor  # noqa: SLF001
    assert (  # noqa: SLF001
        pack._canonical_sha256(pack._contract_payload(pack._action()))
        != original_contract
    )
    with pytest.raises(ValueError, match="descriptor identity differs"):
        pack.build_report(verify_artifacts=False)


def test_identity_route_nvs_artifacts_outputs_and_claims_are_isolated() -> None:
    for v3, v2 in (
        (pack.BUILD_TAG, v2_pack.BUILD_TAG),
        (pack.TEST_ID, v2_pack.TEST_ID),
        (pack.CAMPAIGN_ID, v2_pack.CAMPAIGN_ID),
        (pack.CONTRACT_ID, v2_pack.CONTRACT_ID),
        (pack.NVS_NAMESPACE, v2_pack.NVS_NAMESPACE),
        (pack.NVS_KEY, v2_pack.NVS_KEY),
        (pack.BASE_ROUTE, v2_pack.BASE_ROUTE),
        (pack.DESCRIPTOR_ID, v2_pack.DESCRIPTOR_ID),
        (pack.ACTION_ID, v2_pack.ACTION_ID),
        (pack.DEVICE_API_VERSION, v2_pack.DEVICE_API_VERSION),
        (pack.IDENTITY_REVISION, v2_pack.IDENTITY_REVISION),
        (pack.FIRMWARE_BIN_SHA256, v2_pack.FIRMWARE_BIN_SHA256),
        (pack.FIRMWARE_ELF_SHA256, v2_pack.FIRMWARE_ELF_SHA256),
    ):
        assert v3 != v2
    assert once.DEFAULT_OUTPUT != (
        ROOT / ".test-output/hardware/"
        "MF1750_TARGET_HUE_REDPINK_BRIGHTNESS_WHITE_CONTAINMENT_20260827_V2"
    )
    assert "same_r20_aa_abort_white_v1_claims" in once.DEFAULT_CLAIMS.name
    assert once.FLASH_OUTPUT.parent == once.DEFAULT_OUTPUT
    assert once.FLASH_OUTPUT.name == "app-only-single-boot-flash.json"
    assert pack.SOURCE_ACTION_FILE != once.ACTION_OUTPUT
    assert pack.SOURCE_ROOT != once.DEFAULT_OUTPUT


def test_source_action_file_tamper_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = tmp_path / "action.json"
    data = bytearray(pack.SOURCE_ACTION_FILE.read_bytes())
    data[-2] ^= 1
    tampered.write_bytes(data)
    monkeypatch.setattr(pack, "SOURCE_ACTION_FILE", tampered)
    with pytest.raises(ValueError, match="file binding differs"):
        pack._validate_source_evidence()  # noqa: SLF001


def test_source_action_semantic_drift_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = json.loads(pack.SOURCE_ACTION_FILE.read_text(encoding="utf-8"))
    value.pop("integrity")
    value["outcome"] = "not_complete"
    path = tmp_path / "semantic-drift.json"
    byte_count, file_sha, integrity_sha = _write_sealed(path, value)
    monkeypatch.setattr(pack, "SOURCE_ACTION_FILE", path)
    monkeypatch.setattr(pack, "SOURCE_ACTION_FILE_BYTES", byte_count)
    monkeypatch.setattr(pack, "SOURCE_ACTION_FILE_SHA256", file_sha)
    monkeypatch.setattr(pack, "SOURCE_ACTION_INTEGRITY_SHA256", integrity_sha)
    with pytest.raises(ValueError, match="complete-pass semantics differ"):
        pack._validate_source_evidence()  # noqa: SLF001


def test_repeat_report_file_tamper_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "repeat.json"
    marker.write_bytes(pack.SOURCE_REPEAT_REPORT_FILE.read_bytes() + b"\n")
    monkeypatch.setattr(pack, "SOURCE_REPEAT_REPORT_FILE", marker)
    with pytest.raises(ValueError, match="file binding differs"):
        pack._validate_source_evidence()  # noqa: SLF001


def test_diagnostic_then_same_boot_run_is_one_shot_and_claim_before_arm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic = tmp_path / "j2-off-diagnostic.json"
    read_only = FakeDevice(busy=0)
    observed = once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=read_only,
    )
    assert observed["network"] == {"get": 4, "post": 0}
    assert read_only.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    monkeypatch.setattr(once, "DIAGNOSTIC_OUTPUT", diagnostic)
    claims = tmp_path / "claims"
    claim = claims / f"{pack.ACTION_ID}.json"
    device = FakeDevice(busy=1, expected_claim=claim)
    output = tmp_path / "action.json"
    result = once.run_once(
        "http://192.168.1.11",
        claims=claims,
        output=output,
        confirm_j2_on=True,
        requester=device,
        poll_seconds=65,
        poll_count=1,
        sleeper=lambda _seconds: None,
    )
    assert result["outcome"] == "complete_pass"
    assert result["visible_refreshes"] == 1
    assert result["network"] == {"get": 5, "post": 2}
    assert claim.is_file()
    sealed = _read_sealed(output)
    assert sealed["source_ordinal2_consumption_forbidden"] is True
    assert sealed["source_resume_forbidden"] is True


def test_run_requires_sealed_diagnostic_before_network_or_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-diagnostic.json"
    monkeypatch.setattr(once, "DIAGNOSTIC_OUTPUT", missing)
    calls: list[str] = []

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        calls.append("network")
        raise AssertionError("network must not be reached")

    claims = tmp_path / "claims"
    with pytest.raises(once.ContainmentError, match="diagnostic is missing"):
        once.run_once(
            "http://192.168.1.11",
            claims=claims,
            output=tmp_path / "action.json",
            confirm_j2_on=True,
            requester=requester,
        )
    assert calls == []
    assert not claims.exists()


def test_run_requires_explicit_j2_on_before_diagnostic_or_network(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        calls.append("network")
        raise AssertionError("network must not be reached")

    with pytest.raises(once.ContainmentError, match="J2-ON confirmation"):
        once.run_once(
            "http://192.168.1.11",
            claims=tmp_path / "claims",
            output=tmp_path / "action.json",
            confirm_j2_on=False,
            requester=requester,
        )
    assert calls == []


def test_boot_nonce_drift_after_diagnostic_stops_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic = tmp_path / "diagnostic.json"
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=FakeDevice(busy=0),
    )
    monkeypatch.setattr(once, "DIAGNOSTIC_OUTPUT", diagnostic)
    fake = FakeDevice(busy=1)

    def requester(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        status, value = fake(*args, **kwargs)
        if str(args[1]).endswith("/status"):
            value = dict(value)
            value["boot_nonce"] = "1111111111111111"
        return status, value

    claims = tmp_path / "claims"
    output = tmp_path / "action.json"
    with pytest.raises(once.ContainmentError, match="boot nonce differs"):
        once.run_once(
            "http://192.168.1.11",
            claims=claims,
            output=output,
            confirm_j2_on=True,
            requester=requester,
        )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert not (claims / f"{pack.ACTION_ID}.json").exists()
    assert _read_sealed(output)["outcome"] == "preflight_failed_no_claim"


def test_resealed_diagnostic_body_nonce_drift_fails_before_network_or_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic = tmp_path / "diagnostic.json"
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=FakeDevice(busy=0),
    )
    value = json.loads(diagnostic.read_text(encoding="utf-8"))
    value.pop("integrity")
    value["transcript"][2]["body"]["boot_nonce"] = "1111111111111111"
    _write_sealed(diagnostic, value)
    monkeypatch.setattr(once, "DIAGNOSTIC_OUTPUT", diagnostic)
    calls: list[str] = []

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        calls.append("network")
        raise AssertionError("run-side network must not be reached")

    claims = tmp_path / "claims"
    with pytest.raises(once.ContainmentError, match="boot nonce differ"):
        once.run_once(
            "http://192.168.1.11",
            claims=claims,
            output=tmp_path / "action.json",
            confirm_j2_on=True,
            requester=requester,
        )
    assert calls == []
    assert not claims.exists()


def test_diagnostic_origin_is_bound_before_run_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic = tmp_path / "diagnostic.json"
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=FakeDevice(busy=0),
    )
    monkeypatch.setattr(once, "DIAGNOSTIC_OUTPUT", diagnostic)
    calls: list[str] = []

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        calls.append("network")
        raise AssertionError("run-side network must not be reached")

    with pytest.raises(once.ContainmentError, match="base_url differs"):
        once.run_once(
            "http://192.168.1.12",
            claims=tmp_path / "claims",
            output=tmp_path / "action.json",
            confirm_j2_on=True,
            requester=requester,
        )
    assert calls == []


def test_v3_sealed_writer_handles_short_writes_and_fsyncs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sealed.json"
    real_write = once.os.write
    real_fsync = once.os.fsync
    writes: list[int] = []
    fsyncs: list[int] = []

    def short_write(descriptor: int, data: bytes) -> int:
        writes.append(len(data))
        return real_write(descriptor, data[:7])

    def observed_fsync(descriptor: int) -> None:
        fsyncs.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(once.os, "write", short_write)
    monkeypatch.setattr(once.os, "fsync", observed_fsync)
    once._write_new(path, {"schema_version": 1, "kind": "short-write-test"})  # noqa: SLF001
    assert _read_sealed(path)["kind"] == "short-write-test"
    assert len(writes) > 1
    assert len(fsyncs) == 1
    with pytest.raises(FileExistsError):
        once._write_new(path, {"schema_version": 1})  # noqa: SLF001


def test_arm_transport_doubt_permanently_claims_and_never_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    diagnostic = tmp_path / "diagnostic.json"
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=diagnostic,
        confirm_j2_off=True,
        requester=FakeDevice(busy=0),
    )
    monkeypatch.setattr(once, "DIAGNOSTIC_OUTPUT", diagnostic)
    fake = FakeDevice(busy=1)

    def requester(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        if str(args[1]).endswith("/arm"):
            fake.calls.append(("POST", "arm"))
            raise OSError("synthetic transport doubt")
        return fake(*args, **kwargs)

    claims = tmp_path / "claims"
    claim = claims / f"{pack.ACTION_ID}.json"
    output = tmp_path / "action.json"
    with pytest.raises(once.ContainmentConsumedError, match="permanent claim"):
        once.run_once(
            "http://192.168.1.11",
            claims=claims,
            output=output,
            confirm_j2_on=True,
            requester=requester,
        )
    assert claim.is_file()
    attempt = _read_sealed(output)
    assert attempt["outcome"] == "claimed_attempt_failed_do_not_retry"
    assert attempt["claim_state"] == "permanently_consumed_by_this_invocation"
    assert attempt["network"] == {"get": 4, "post": 1}
    assert attempt["no_retry"] is True


def test_wrong_compiled_classification_fails_after_four_gets_without_claim(
    tmp_path: Path,
) -> None:
    output = tmp_path / "diagnostic.json"
    fake = FakeDevice(busy=0)

    def requester(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        status, value = fake(*args, **kwargs)
        if str(args[1]).endswith("/version"):
            value = dict(value)
            value["classification"] = f"{pack.CLASSIFICATION}_DRIFT"
        return status, value

    with pytest.raises(once.ContainmentError, match="classification differs"):
        once.diagnose_j2_off(
            "http://192.168.1.11",
            output=output,
            confirm_j2_off=True,
            requester=requester,
        )
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    attempt = _read_sealed(output)
    assert attempt["outcome"] == "j2_off_diagnostic_failed_no_claim"
    assert attempt["network"] == {"get": 4, "post": 0}
    assert attempt["visible_refresh_may_have_occurred"] is False


def test_diagnostic_output_is_immutable_and_not_retried(tmp_path: Path) -> None:
    output = tmp_path / "diagnostic.json"
    first = FakeDevice(busy=0)
    once.diagnose_j2_off(
        "http://192.168.1.11",
        output=output,
        confirm_j2_off=True,
        requester=first,
    )
    before = output.read_bytes()
    second = FakeDevice(busy=0)
    with pytest.raises(once.ContainmentError, match="refusing to overwrite"):
        once.diagnose_j2_off(
            "http://192.168.1.11",
            output=output,
            confirm_j2_off=True,
            requester=second,
        )
    assert second.calls == []
    assert output.read_bytes() == before


def test_platformio_selects_only_aa_abort_entrypoint() -> None:
    config = (ROOT / "platformio.same_r20_aa_abort_white_v1.ini").read_text(
        encoding="utf-8"
    )
    assert "+<ec5_sr20_aa_abort_white_v1.cpp>" in config
    assert "MF1750_SAME_R20_AA_ABORT_WHITE_V1=1" in config
    assert "EPD_ENABLE_TEST_PATTERN=0" in config
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in config
