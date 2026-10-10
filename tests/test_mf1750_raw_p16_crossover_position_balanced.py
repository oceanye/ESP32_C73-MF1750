from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools import mf1750_raw_p16_crossover_position_balanced_build as builder
from tools import mf1750_raw_p16_crossover_position_balanced_once as once
from tools import mf1750_raw_p16_crossover_position_balanced_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def _fresh_white_responses(host: Any) -> dict[str, dict[str, Any]]:
    identity = {
        "build_tag": host.pack.BUILD_TAG,
        "test_id": host.pack.TEST_ID,
        "campaign_id": host.pack.CAMPAIGN_ID,
        "profile_id": host.pack.PROFILE_ID,
        "environment": host.pack.ENVIRONMENT,
        "device_api_version": host.pack.DEVICE_API_VERSION,
        "identity_revision": host.pack.IDENTITY_REVISION,
        "running_app_elf_sha256": host.pack.FIRMWARE_ELF_SHA256,
        "contract_id": host.pack.CONTRACT_ID,
        "transaction_descriptor_sha256": host.pack.DESCRIPTOR_ID,
        "transaction_descriptor_marker": host.pack.DESCRIPTOR_MARKER,
    }
    return {
        "version": {
            "schema_version": 1,
            "kind": "mf1750-ec5-factory-otp-white-recovery-version",
            **identity,
            "classification": host.pack.CLASSIFICATION,
            "action_count": 1,
            "startup_refresh": False,
            "raw_ingress": False,
            "retry": False,
            "automatic_chaining": False,
            "profile_switch": False,
            "runtime_payload_present": False,
            "live_authorized": False,
        },
        "manifest": {
            "schema_version": 1,
            "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
            **identity,
            "classification": host.pack.CLASSIFICATION,
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
            "actions": [host.ACTION],
            "nvs_contract": {
                "namespace": host.pack.NVS_NAMESPACE,
                "key": host.pack.NVS_KEY,
                "initial_cursor": 1,
                "terminal_cursor": 2,
                "clear_route": False,
                "persistent_across_reboot": True,
            },
        },
        "status": {
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
            "busy": 0,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "report": {
            "schema_version": 1,
            "kind": "mf1750-ec5-factory-otp-white-recovery-report",
            **identity,
            "valid": False,
            "terminal_state": "NOT_EXECUTED",
            "result": False,
            "driver_called": False,
            "driver_call_count_for_action": 0,
            "no_retry": True,
        },
    }


class _FreshWhiteDevice:
    def __init__(self, host: Any, *, wrong_contract: bool = False) -> None:
        self.responses = _fresh_white_responses(host)
        if wrong_contract:
            self.responses["manifest"]["contract_id"] = "0" * 64
        self.calls: list[tuple[str, str]] = []
        self.events: list[str] = []

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: object,
        timeout: float,
    ) -> tuple[int, dict[str, Any]]:
        del headers, timeout
        endpoint = path.rsplit("/", 1)[-1]
        self.calls.append((method, endpoint))
        self.events.append(f"network:{endpoint}")
        return 200, deepcopy(self.responses[endpoint])


def test_t1_t2_t3_reuse_exact_same_position_balanced_dtm() -> None:
    reports = [pack.build_report(stage) for stage in pack.STAGES]
    frames = [report["actions"][0]["frame"] for report in reports]
    cs1 = [report["actions"][0]["cs1_dtm"] for report in reports]
    cs2 = [report["actions"][0]["cs2_dtm"] for report in reports]
    assert frames[0] == frames[1] == frames[2]
    assert cs1[0] == cs1[1] == cs1[2] == cs2[0] == cs2[1] == cs2[2]
    assert frames[0]["histogram"] == [
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        41_600,
        323_200,
    ]
    flat = [code for row in pack.CODE_ROWS for code in row]
    assert {code: flat.count(code) for code in range(8)} == {
        code: 4 for code in range(8)
    }


def test_crossover_profile_swap_and_repeat_are_exact() -> None:
    t1 = pack.build_report("t1-ac")["contract"]["profile"]
    t2 = pack.build_report("t2-ca")["contract"]["profile"]
    t3 = pack.build_report("t3-ac-repeat")["contract"]["profile"]
    assert (t1["global_header"], t1["cs1"]["name"], t1["cs2"]["name"]) == (
        "active",
        "active",
        "commented",
    )
    assert (t2["global_header"], t2["cs1"]["name"], t2["cs2"]["name"]) == (
        "commented",
        "commented",
        "active",
    )
    assert t3 == t1
    assert t2["global_tuple_id"] != t1["global_tuple_id"]


def test_every_atlas_and_white_is_fresh_and_non_chained() -> None:
    reports = [pack.build_report(stage) for stage in pack.STAGES]
    whites = [pack.build_white_report(stage) for stage in pack.WHITES]
    namespaces = [
        *(item["contract"]["nvs_namespace"] for item in reports),
        *(item["contract"]["nvs_namespace"] for item in whites),
    ]
    action_ids = [
        *(item["actions"][0]["action_id"] for item in reports),
        *(item["action"]["action_id"] for item in whites),
    ]
    assert len(namespaces) == len(set(namespaces)) == 6
    assert len(action_ids) == len(set(action_ids)) == 6
    for item in reports:
        contract = item["contract"]
        assert contract["action_count"] == 1
        assert contract["automatic_chaining"] is False
        assert contract["retry"] is False
        assert contract["recovery"] is False
        assert contract["external_containment"]["white_actions_in_campaign"] == 0
    for item in whites:
        contract = item["contract"]
        assert contract["factory_otp_white_only"] is True
        assert contract["runtime_payload"] is False
        assert contract["autochain"] is False


def test_all_six_reviewed_artifact_bindings_match() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["network_requests"] == 0
    assert value["identical_frame_and_dtm_across_t1_t2_t3"] is True
    assert value["fresh_claim_root_count"] == 6
    for stage in pack.STAGES:
        binding = once._artifact_binding(stage)  # noqa: SLF001
        for item in binding.values():
            payload = Path(item["path"]).read_bytes()
            assert len(payload) == item["bytes"]
            assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_prebuild_validation_does_not_require_ignored_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(_binding: object) -> None:
        raise AssertionError("prebuild validation read an artifact")

    monkeypatch.setattr(once, "_verify_binding", forbidden)
    value = once.dry_validate(verify_artifacts=False)
    assert value["result"] == "PASS"
    assert value["artifacts_verified"] is False


def test_build_bootstrap_uses_six_compile_only_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pio = tmp_path / "pio.exe"
    pio.touch()
    commands: list[list[str]] = []
    validations: list[bool] = []

    def validate(*, verify_artifacts: bool = True) -> dict[str, object]:
        validations.append(verify_artifacts)
        return {"result": "PASS", "artifacts_verified": verify_artifacts}

    def run(command: list[str], **_kwargs: object) -> None:
        commands.append(command)

    monkeypatch.setattr(builder.campaign, "dry_validate", validate)
    monkeypatch.setattr(builder.subprocess, "run", run)
    value = builder.build_all(pio=pio)
    assert value["result"] == "PASS"
    assert validations == [False, True]
    assert len(commands) == len(builder.CONFIGS) == 6
    assert all(command[1:3] == ["run", "-c"] for command in commands)
    assert all("upload" not in command for command in commands)
    for stage in pack.WHITES:
        binding = once._white_artifact_binding(stage)  # noqa: SLF001
        for item in binding.values():
            payload = Path(item["path"]).read_bytes()
            assert len(payload) == item["bytes"]
            assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_runner_rejects_missing_external_prewhite_before_request(
    tmp_path: Path,
) -> None:
    host = once._configure_atlas("t1-ac")  # noqa: SLF001
    calls: list[tuple[object, ...]] = []

    def requester(*args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
        calls.append(args)
        return 500, {}

    with pytest.raises(host.base.runner.RecheckError, match="pre-white"):
        host.run_once(
            "http://192.168.1.11",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=requester,
            confirm_j2_on=True,
            confirm_external_pre_white=False,
        )
    assert calls == []


def test_atlas_runner_rejects_missing_j2_on_before_request(tmp_path: Path) -> None:
    host = once._configure_atlas("t1-ac")  # noqa: SLF001
    calls: list[tuple[object, ...]] = []

    def requester(*args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
        calls.append(args)
        return 500, {}

    with pytest.raises(host.base.runner.RecheckError, match="J2-ON"):
        host.run_once(
            "http://192.168.1.11",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=requester,
            confirm_external_pre_white=True,
        )
    assert calls == []


def test_atlas_runner_rejects_nonlocal_or_named_origin_before_request(
    tmp_path: Path,
) -> None:
    host = once._configure_atlas("t1-ac")  # noqa: SLF001
    calls: list[tuple[object, ...]] = []

    def requester(*args: object, **_kwargs: object) -> tuple[int, dict[str, object]]:
        calls.append(args)
        return 500, {}

    for origin in ("http://example.com", "http://203.0.113.5"):
        with pytest.raises(host.base.runner.RecheckError, match="literal IPv4|private"):
            host.run_once(
                origin,
                1,
                claims=tmp_path / "claims",
                output=tmp_path / "result.json",
                requester=requester,
                confirm_j2_on=True,
                confirm_external_pre_white=True,
            )
    assert calls == []


def test_legacy_t3_run_path_is_tombstoned_before_configure_or_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured: list[str] = []

    def forbidden(stage: str) -> object:
        configured.append(stage)
        raise AssertionError("tombstoned legacy T3 reached host configuration")

    monkeypatch.setattr(once, "_configure_atlas", forbidden)
    result = once.main(
        [
            "run-atlas",
            "--stage",
            "t3-ac-repeat",
            "--base-url",
            "http://192.168.1.11",
            "--confirm-j2-on",
            "--confirm-external-pre-white",
        ]
    )

    assert result == 2
    assert configured == []
    assert once.LEGACY_T3_TOMBSTONED_ACTION_ID == (
        "4a7c3d2816aca50e124049e048c7d7dbeec32a8c7bb825b9cd5294fdd23f144a"
    )


def test_cpp_binds_profile_swap_and_fresh_white_selectors() -> None:
    driver = (ROOT / "src/ec5_runtime_lut_same_r20_parity_4x8_v2_driver.inc").read_text(
        encoding="utf-8"
    )
    identity = (
        ROOT / "src/ec5_raw_p16_crossover_position_balanced_identity.inc"
    ).read_text(encoding="utf-8")
    white = (
        ROOT / "src/ec5_raw_p16_crossover_white_containment_identity.inc"
    ).read_text(encoding="utf-8")
    white_program = (
        ROOT / "src/ec5_raw_p16_endpoint_gallery_v1_white_containment_program.inc"
    ).read_text(encoding="utf-8")
    assert "ph::kGlobalUseCommented" in driver
    assert "ph::kCs1UseCommented" in driver
    assert "ph::kCs2UseCommented" in driver
    assert "ph_lut::commented::kPowerPayloadSha256" in driver
    assert "ph_lut::commented::kPllPayloadSha256" in driver
    assert r"\"source_campaign_id\"" in white_program
    assert r"\"source_contract_id\"" in white_program
    for report in (pack.build_report(stage) for stage in pack.STAGES):
        assert report["contract_id"] in identity
        assert report["actions"][0]["action_id"] in identity
    for report in (pack.build_white_report(stage) for stage in pack.WHITES):
        assert report["contract_id"] in white
        assert report["action"]["action_id"] in white
        assert report["action"]["source_contract_id"] in white


def test_white_host_rebinds_every_validator_layer_to_fresh_identity() -> None:
    for stage in pack.WHITES:
        host = once._configure_white(stage)  # noqa: SLF001
        report = pack.build_white_report(stage)
        assert host.pack.CAMPAIGN_ID == report["contract"]["campaign_id"]
        assert host.ACTION == report["action"]
        assert host.base.ACTION == report["action"]
        assert host.base._base.ACTION == report["action"]  # noqa: SLF001
        assert host.base._base.pack is host.pack  # noqa: SLF001
        assert host.base._base.REPORT == report  # noqa: SLF001
        assert host.base._base.ENDPOINTS == host.ENDPOINTS  # noqa: SLF001
        assert host.DEFAULT_CLAIMS == host.base.DEFAULT_CLAIMS
        assert host.DEFAULT_OUTPUT == host.base.DEFAULT_OUTPUT
        assert host.DIAGNOSTIC_OUTPUT == host.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
        assert host.base.DIAGNOSTIC_OUTPUT == host.DIAGNOSTIC_OUTPUT
        assert pack.WHITES[stage].suffix.lower() in host.base.ATTEMPT_KIND


@pytest.mark.parametrize("stage", tuple(pack.WHITES))
def test_white_diagnostic_is_artifact_first_four_get_zero_claim_and_oxcl(
    stage: pack.WhiteStage, tmp_path: Path
) -> None:
    host = once._configure_white(stage)  # noqa: SLF001
    fake = _FreshWhiteDevice(host)
    output = tmp_path / stage / "j2-off-diagnostic.json"
    host.DEFAULT_CLAIMS = tmp_path / stage / "claims"
    host.base.DEFAULT_CLAIMS = host.DEFAULT_CLAIMS
    original_build_report = host.pack.build_report

    def observed_build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
        fake.events.append(f"artifact:{verify_artifacts}")
        return original_build_report(verify_artifacts=verify_artifacts)

    host.pack.build_report = observed_build_report
    value = host.diagnose_j2_off(
        "http://192.168.1.11",
        output=output,
        confirm_j2_off=True,
        requester=fake,
    )

    assert fake.events[0] == "artifact:True"
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert value["network"] == {"get": 4, "post": 0}
    assert value["permanent_claims_created"] == 0
    assert value["visible_refreshes"] == 0
    assert value["fresh_nvs"] is True
    assert value["action"] == host.ACTION
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["kind"] == host.base.DIAGNOSTIC_KIND
    assert stored["output_write_contract"] == "O_EXCL"
    assert not host.DEFAULT_CLAIMS.exists()

    calls_before_reuse = list(fake.calls)
    with pytest.raises(host.ContainmentError, match="overwrite"):
        host.diagnose_j2_off(
            "http://192.168.1.11",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert fake.calls == calls_before_reuse


def test_white_diagnostic_rejects_wrong_manifest_after_four_gets_without_claim(
    tmp_path: Path,
) -> None:
    host = once._configure_white("w1-after-t1")  # noqa: SLF001
    fake = _FreshWhiteDevice(host, wrong_contract=True)
    output = tmp_path / "failed-j2-off-diagnostic.json"
    host.DEFAULT_CLAIMS = tmp_path / "claims"
    host.base.DEFAULT_CLAIMS = host.DEFAULT_CLAIMS

    with pytest.raises(host.ContainmentError, match="diagnostic failed"):
        host.diagnose_j2_off(
            "http://192.168.1.11",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )

    assert len(fake.calls) == 4
    attempt = json.loads(output.read_text(encoding="utf-8"))
    assert attempt["outcome"] == "j2_off_diagnostic_failed_no_claim"
    assert attempt["network"] == {"get": 4, "post": 0}
    assert attempt["permanent_claims_created"] == 0
    assert not host.DEFAULT_CLAIMS.exists()


def test_white_diagnostic_cli_uses_stage_specific_independent_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    diagnostic_output = tmp_path / "w2" / "j2-off-diagnostic.json"

    def diagnose_j2_off(_base_url: str, **kwargs: object) -> dict[str, str]:
        captured.update(kwargs)
        return {"result": "PASS"}

    fake = SimpleNamespace(
        DIAGNOSTIC_OUTPUT=diagnostic_output,
        diagnose_j2_off=diagnose_j2_off,
    )
    monkeypatch.setattr(once, "_configure_white", lambda _stage: fake)
    result = once.main(
        [
            "diagnose-white-j2-off",
            "--stage",
            "w2-after-t2",
            "--base-url",
            "http://192.0.2.1",
            "--confirm-j2-off",
            "--timeout",
            "7.5",
        ]
    )

    assert result == 0
    assert captured == {
        "output": diagnostic_output,
        "confirm_j2_off": True,
        "timeout": 7.5,
    }


def test_white_cli_propagates_explicit_j2_on_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def run_once(_base_url: str, **kwargs: object) -> dict[str, str]:
        captured.update(kwargs)
        return {"result": "PASS"}

    fake = SimpleNamespace(
        base=SimpleNamespace(
            DEFAULT_CLAIMS=tmp_path / "claims",
            DEFAULT_OUTPUT=tmp_path / "output",
        ),
        run_once=run_once,
    )
    monkeypatch.setattr(once, "_configure_white", lambda _stage: fake)
    result = once.main(
        [
            "run-white",
            "--stage",
            "w1-after-t1",
            "--base-url",
            "http://192.0.2.1",
            "--confirm-j2-on",
        ]
    )
    assert result == 0
    assert captured["confirm_j2_on"] is True


def test_documented_artifact_manifest_is_current() -> None:
    manifest = (
        ROOT / "docs/MF1750_RAW_P16_CROSSOVER_POSITION_BALANCED_SHA256_2026-08-30.txt"
    )
    entries = [
        line.split(maxsplit=3)
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert len(entries) == 12
    for sha256, byte_count, _stage, relative_path in entries:
        payload = (ROOT / relative_path).read_bytes()
        assert len(payload) == int(byte_count)
        assert hashlib.sha256(payload).hexdigest() == sha256
