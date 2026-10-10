from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_color_lab_campaign as campaign
from tools import mf1750_ec5_color_lab_contract as contract
from tools import mf1750_ec5_color_lab_physical_once as physical


BOOT_NONCE = "0123456789abcdef"
ARM_NONCE = "fedcba9876543210"


def _identity(kind: str) -> dict[str, Any]:
    return {
        "schema_version": contract.TOP_SCHEMA_VERSION,
        "kind": kind,
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "campaign_id": contract.CAMPAIGN_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "identity_revision": contract.IDENTITY_REVISION,
        "contract_id": contract.campaign_manifest()["contract_id"],
    }


def _response_identity() -> dict[str, Any]:
    root = _identity("unused")
    root.pop("schema_version")
    root.pop("kind")
    return root


def _context(tmp_path: Path) -> physical.ReleaseContext:
    root = campaign.build_campaign()
    return physical.ReleaseContext(
        release_file=(tmp_path / "real-release.json").resolve(),
        release_root={
            "execution_eligible": True,
            "evidence_mode": campaign.REAL_MODE,
            "firmware": {
                "binary": {
                    "file": str((tmp_path / "firmware.bin").resolve()),
                    "bytes": 791152,
                    "file_sha256": "a" * 64,
                }
            },
            "predecessor_binding": {
                "compare_binding": {"frozen": True, "action": "compare"}
            },
        },
        release_file_sha256="b" * 64,
        release_canonical_sha256="c" * 64,
        campaign_file=(tmp_path / "campaign.json").resolve(),
        campaign_root=root,
        actions=tuple(deepcopy(root["actions"])),
        execution_eligible=True,
        formal_u07_registry=(tmp_path / "formal-u07-claims").resolve(),
    )


class FakeDevice:
    def __init__(self, context: physical.ReleaseContext) -> None:
        self.context = context
        self.boot_nonce = BOOT_NONCE
        self.busy = 0
        self.ordinal = 1
        self.phase = "ready"
        self.arm_count = 0
        self.execute_count = 0
        self.driver_count = 0
        self.key_present = False
        self.last_report: dict[str, Any] = self._not_executed_report()
        self.calls: list[tuple[str, str, Mapping[str, str] | None]] = []

    @property
    def action(self) -> Mapping[str, Any]:
        return self.context.actions[self.ordinal - 1]

    def _version(self) -> dict[str, Any]:
        return {
            **_identity("mf1750-ec5-color-lab-version"),
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "layout_id": contract.LAYOUT_ID,
            "driver_api_version": "MF1750_EPD_DRIVER_V1",
            "action_count": campaign.ACTION_COUNT,
            "automatic_execute": False,
            "automatic_chaining": False,
            "startup_refresh": False,
            "raw_frame_ingress": False,
            "dither": False,
            "retry": False,
            "recovery": False,
            "nvs_contract": {
                "namespace": contract.NVS_NAMESPACE,
                "key": contract.NVS_KEY,
            },
        }

    def _manifest(self) -> dict[str, Any]:
        return {
            **_identity("mf1750-ec5-color-lab-manifest"),
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "layout_id": contract.LAYOUT_ID,
            "action_count": campaign.ACTION_COUNT,
            "round_count": 3,
            "round_one_safe_stop_completed_ordinal": 11,
            "round_one_safe_stop_next_ordinal": 12,
            "automatic_chaining": False,
            "startup_refresh": False,
            "raw_frame_ingress": False,
            "dither": False,
            "retry": False,
            "recovery": False,
            "actions": [
                physical._device_action(action) for action in self.context.actions
            ],
            "nvs_contract": {
                "namespace": contract.NVS_NAMESPACE,
                "key": contract.NVS_KEY,
            },
        }

    def _status(self) -> dict[str, Any]:
        action = self.action
        if self.phase == "ready":
            state = "ready"
            phase = 0
            next_ordinal = self.ordinal
            current = None
            execute_pending = False
        elif self.phase == "armed":
            state = "armed"
            phase = 1
            next_ordinal = self.ordinal
            current = physical._device_action(action)
            execute_pending = False
        else:
            state = "complete" if self.ordinal == 24 else "ready"
            phase = 0
            next_ordinal = self.ordinal
            current = None
            execute_pending = False
        return {
            **_identity("mf1750-ec5-color-lab-status"),
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "boot_nonce": self.boot_nonce,
            "state": state,
            "phase": phase,
            "phase_name": "ARMED" if phase == 1 else "READY",
            "cursor_raw": phase * 256 + next_ordinal,
            "next_ordinal": next_ordinal,
            "current_action": current,
            "campaign_complete": next_ordinal == 24,
            "fixture_self_check_passed": True,
            "cursor_valid": True,
            "persistent_key_present": self.key_present,
            "execute_pending": execute_pending,
            "arm_request_count": self.arm_count,
            "execute_request_count": self.execute_count,
            "total_driver_call_count": self.driver_count,
            "gpio_initialized": True,
            "busy": self.busy,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "nvs_contract": {
                "namespace": contract.NVS_NAMESPACE,
                "key": contract.NVS_KEY,
            },
        }

    def _not_executed_report(self) -> dict[str, Any]:
        return {
            **_identity("mf1750-ec5-color-lab-report"),
            "valid": False,
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "boot_nonce": self.boot_nonce,
            "ordinal": None,
            "descriptor_id": None,
            "action_id": None,
            "terminal_state": "NOT_EXECUTED",
            "result": False,
            "driver_called": False,
            "driver_call_count_for_action": 0,
            "total_driver_call_count": 0,
            "phase": 0,
            "next_ordinal": 1,
            "no_retry": True,
            "no_recovery": True,
        }

    def _arm_response(self, action: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "accepted": True,
            "armed": True,
            **_response_identity(),
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "ordinal": action["ordinal"],
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "role": action["role"],
            "round": action["round"],
            "branch": action["branch"],
            "boot_nonce": self.boot_nonce,
            "arm_nonce": ARM_NONCE,
            "phase": 1,
            "phase_name": "ARMED",
            "not_hardware_authorization": True,
        }

    def _execute_response(self, action: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "accepted": True,
            "job_id": action["ordinal"],
            **_response_identity(),
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "ordinal": action["ordinal"],
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "role": action["role"],
            "round": action["round"],
            "branch": action["branch"],
            "boot_nonce": self.boot_nonce,
            "execute_consumed": True,
            "phase": 2,
            "phase_name": "CONSUMED",
            "no_retry": True,
            "no_recovery": True,
        }

    def _complete_report(self, action: Mapping[str, Any]) -> dict[str, Any]:
        frame = action["frame"]["frame"]
        return {
            **_identity("mf1750-ec5-color-lab-report"),
            "valid": True,
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "boot_nonce": self.boot_nonce,
            "ordinal": action["ordinal"],
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "role": action["role"],
            "round": action["round"],
            "branch": action["branch"],
            "job_id": action["ordinal"],
            "terminal_state": "COMPLETE",
            "result": True,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": action["ordinal"],
            "phase": 0,
            "phase_name": "READY",
            "next_ordinal": action["ordinal"] + 1,
            "campaign_complete": action["ordinal"] == campaign.ACTION_COUNT,
            "no_retry": True,
            "no_recovery": True,
            "job_queued_at_ms": action["ordinal"] * 100,
            "job_started_at_ms": action["ordinal"] * 100 + 1,
            "job_finished_at_ms": action["ordinal"] * 100 + 2,
            "driver": {
                "driver_evidence_schema_version": (
                    contract.DRIVER_EVIDENCE_SCHEMA_VERSION
                ),
                "valid": True,
                "running": False,
                "sequence_ok": True,
                "mapping_applied": True,
                "input_fnv1a": int(frame["fnv1a"], 16),
                "cs1_dtm_fnv1a": int(frame["controllers"][0]["fnv1a"], 16),
                "cs2_dtm_fnv1a": int(frame["controllers"][1]["fnv1a"], 16),
                "safe_finish": {
                    "busy_before_pins_low": 1,
                    "busy_after_pins_low": 1,
                    "busy_after_5ms": 1,
                    "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
                },
            },
        }

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
        self.calls.append((method, path, headers))
        if method == "GET" and path == campaign.ENDPOINTS["version"]:
            return 200, self._version()
        if method == "GET" and path == campaign.ENDPOINTS["manifest"]:
            return 200, self._manifest()
        if method == "GET" and path == campaign.ENDPOINTS["status"]:
            return 200, self._status()
        if method == "GET" and path == campaign.ENDPOINTS["report"]:
            return 200, deepcopy(self.last_report)
        if method == "POST" and path == campaign.ENDPOINTS["arm"]:
            action = self.action
            self.arm_count += 1
            self.key_present = True
            self.phase = "armed"
            return 201, self._arm_response(action)
        if method == "POST" and path == campaign.ENDPOINTS["execute"]:
            action = self.action
            self.execute_count += 1
            self.driver_count += 1
            response = self._execute_response(action)
            self.last_report = self._complete_report(action)
            self.ordinal += 1
            self.phase = "ready"
            return 202, response
        raise AssertionError(f"unexpected request: {method} {path}")


def _bypass_offline_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(physical, "_revalidate_real_release", lambda _context: None)
    monkeypatch.setattr(
        physical,
        "_formal_u07_snapshot",
        lambda _context: {
            "registry": "synthetic-test-formal-u07-registry",
            "action_id": "8f427" + "0" * 59,
            "claim_absent": True,
        },
    )


def _seal_common_observation(
    context: physical.ReleaseContext,
    result: Path,
    observation: Path,
    registry: Path,
    *,
    clean_white: bool = False,
) -> dict[str, Any]:
    return physical.seal_observation(
        context,
        result_file=result,
        observation_file=observation,
        claim_registry=registry,
        operator_report="fake-device visual evidence matched the preview",
        temperature_c=37.0,
        confirm_reference_preview_checked=True,
        confirm_display_matches_reference=True,
        confirm_no_unexpected_residual=True,
        confirm_electrical_normal=True,
        confirm_esp32_no_restart=True,
        confirm_clean_white=clean_white,
    )


def _complete_first_action(
    context: physical.ReleaseContext,
    device: FakeDevice,
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    registry = tmp_path / "claims"
    diagnostic = tmp_path / "j2-off.json"
    result = tmp_path / "ordinal-1-result.json"
    physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1
    output = physical.run_once(
        context,
        "http://fake-device",
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=device,
        sleeper=lambda _seconds: None,
    )
    assert output["outcome"] == "complete_pass", output["error"]
    return registry, diagnostic, result


def test_j2_off_then_two_actions_same_boot_without_reset_or_reflash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    registry = tmp_path / "claims"
    diagnostic_file = tmp_path / "j2-off.json"
    device = FakeDevice(context)

    diagnostic = physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic_file,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    assert diagnostic["network"] == {"get_requests": 4, "post_requests": 0}
    assert not registry.exists()
    assert [method for method, _path, _headers in device.calls] == ["GET"] * 4

    device.busy = 1
    result1_file = tmp_path / "ordinal-1-result.json"
    result1 = physical.run_once(
        context,
        "http://fake-device",
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result1_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=device,
        sleeper=lambda _seconds: None,
    )
    assert result1["outcome"] == "complete_pass", result1["error"]
    assert result1["preflight"]["boot_nonce"] == diagnostic["boot_nonce"]
    assert result1["network"]["arm_posts"] == 1
    assert result1["network"]["execute_posts"] == 1
    assert physical.validate_result(
        context, result1_file, claim_registry=registry
    )["outcome"] == "complete_pass"
    observation1_file = tmp_path / "ordinal-1-observation.json"
    _seal_common_observation(
        context,
        result1_file,
        observation1_file,
        registry,
        clean_white=True,
    )

    result2_file = tmp_path / "ordinal-2-result.json"
    result2 = physical.run_once(
        context,
        "http://fake-device",
        2,
        authorization=physical.required_authorization(context, 2),
        result_file=result2_file,
        claim_registry=registry,
        prior_result_file=result1_file,
        prior_observation_file=observation1_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=device,
        sleeper=lambda _seconds: None,
    )
    assert result2["outcome"] == "complete_pass"
    assert result2["preflight"]["boot_nonce"] == BOOT_NONCE
    assert result2["device"]["terminal_status"]["arm_request_count"] == 2
    assert result2["device"]["terminal_status"]["execute_request_count"] == 2
    assert result2["device"]["terminal_status"]["total_driver_call_count"] == 2
    assert sum(method == "POST" for method, _path, _headers in device.calls) == 4
    assert physical.validate_result(
        context, result2_file, claim_registry=registry
    )["outcome"] == "complete_pass"


def test_cumulative_count_drift_fails_before_claim_or_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    device = FakeDevice(context)
    registry = tmp_path / "claims"
    diagnostic = tmp_path / "j2-off.json"
    physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1
    device.arm_count = 1
    with pytest.raises(physical.ColorLabPhysicalError, match="cumulative count"):
        physical.run_once(
            context,
            "http://fake-device",
            1,
            authorization=physical.required_authorization(context, 1),
            result_file=tmp_path / "result.json",
            claim_registry=registry,
            j2_off_diagnostic_file=diagnostic,
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=device,
        )
    assert not registry.exists()
    assert all(method == "GET" for method, _path, _headers in device.calls)


def test_cli_run_dispatches_j2_diagnostic_argument(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    context = _context(tmp_path)
    captured: dict[str, Any] = {}
    monkeypatch.setattr(physical, "load_release", lambda _path: context)

    def fake_run(
        _context: physical.ReleaseContext,
        _base_url: str,
        _ordinal: int,
        **kwargs: Any,
    ) -> dict[str, Any]:
        captured.update(kwargs)
        return {"outcome": "dispatch-only"}

    monkeypatch.setattr(physical, "run_once", fake_run)
    diagnostic = tmp_path / "diagnostic.json"
    assert physical.main(
        [
            "--release",
            str(tmp_path / "release.json"),
            "run",
            "--base-url",
            "http://fake-device",
            "--ordinal",
            "1",
            "--authorize",
            physical.required_authorization(context, 1),
            "--result",
            str(tmp_path / "result.json"),
            "--j2-off-diagnostic",
            str(diagnostic),
            "--confirm-no-intervening-visible-refresh",
            "--confirm-j2-on",
            "--confirm-electrical-normal",
            "--temperature-c",
            "37",
        ]
    ) == 0
    assert captured["j2_off_diagnostic_file"] == diagnostic
    assert "dispatch-only" in capsys.readouterr().out


def test_http_post_has_no_body_arguments_or_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class HandlerParent:
        addheaders: list[tuple[str, str]] = []

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        @staticmethod
        def getcode() -> int:
            return 200

        @staticmethod
        def read(_maximum: int) -> bytes:
            return b'{"accepted":true}'

    def fake_urlopen(
        request: physical.urllib.request.Request, *, timeout: float
    ) -> Response:
        handler = physical.urllib.request.HTTPHandler()
        handler.parent = HandlerParent()
        processed = handler.do_request_(request)
        captured.update(
            {
                "method": processed.get_method(),
                "url": processed.full_url,
                "data": processed.data,
                "headers": {
                    key.lower(): value for key, value in processed.header_items()
                },
                "timeout": timeout,
            }
        )
        return Response()

    monkeypatch.setattr(physical.urllib.request, "urlopen", fake_urlopen)
    status, response = physical.http_request(
        "http://192.0.2.1",
        campaign.ENDPOINTS["arm"],
        method="POST",
        headers={"X-EC5-Intent": campaign.ARM_INTENT},
        timeout=3.0,
    )

    assert status == 200
    assert response == {"accepted": True}
    assert captured["method"] == "POST"
    assert captured["url"] == "http://192.0.2.1/api/ec5/color-lab/arm"
    assert captured["data"] is None
    assert captured["timeout"] == 3.0
    assert captured["headers"]["x-ec5-intent"] == campaign.ARM_INTENT
    assert "content-length" not in captured["headers"]
    assert "content-type" not in captured["headers"]


def test_no_intervening_confirmation_fails_before_request_or_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    called = False

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        nonlocal called
        called = True
        raise AssertionError("requester must not be called")

    registry = tmp_path / "claims"
    with pytest.raises(
        physical.ColorLabPhysicalError,
        match="no-intervening-visible-refresh",
    ):
        physical.run_once(
            context,
            "http://fake-device",
            2,
            authorization=physical.required_authorization(context, 2),
            result_file=tmp_path / "result.json",
            claim_registry=registry,
            prior_result_file=tmp_path / "unused-result.json",
            prior_observation_file=tmp_path / "unused-observation.json",
            confirm_no_intervening_visible_refresh=False,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=requester,
        )
    assert called is False
    assert not registry.exists()


def test_boot_nonce_change_fails_after_four_gets_but_before_claim_or_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    device = FakeDevice(context)
    registry = tmp_path / "claims"
    diagnostic = tmp_path / "j2-off.json"
    physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1
    device.boot_nonce = "1111111111111111"
    device.last_report["boot_nonce"] = device.boot_nonce
    calls_before = len(device.calls)
    with pytest.raises(physical.ColorLabPhysicalError, match="boot nonce differs"):
        physical.run_once(
            context,
            "http://fake-device",
            1,
            authorization=physical.required_authorization(context, 1),
            result_file=tmp_path / "result.json",
            claim_registry=registry,
            j2_off_diagnostic_file=diagnostic,
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=device,
        )
    new_calls = device.calls[calls_before:]
    assert len(new_calls) == 4
    assert all(method == "GET" for method, _path, _headers in new_calls)
    assert not registry.exists()


@pytest.mark.parametrize("drift_endpoint", ["arm", "execute"])
def test_response_schema_drift_consumes_claim_once_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_endpoint: str,
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    device = FakeDevice(context)
    registry = tmp_path / "claims"
    diagnostic = tmp_path / "j2-off.json"
    physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1

    def drifting_requester(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        status, response = device(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )
        if method == "POST" and path == campaign.ENDPOINTS[drift_endpoint]:
            response = {**response, "unexpected_schema_drift": True}
        return status, response

    result_file = tmp_path / "unknown-result.json"
    result = physical.run_once(
        context,
        "http://fake-device",
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=drifting_requester,
    )
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == (drift_endpoint == "execute")
    assert physical.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "unknown_do_not_retry_or_recover"
    post_count = sum(method == "POST" for method, _path, _headers in device.calls)
    with pytest.raises(physical.ColorLabPhysicalError, match="claim.*already exists"):
        physical.run_once(
            context,
            "http://fake-device",
            1,
            authorization=physical.required_authorization(context, 1),
            result_file=tmp_path / "second-result.json",
            claim_registry=registry,
            j2_off_diagnostic_file=diagnostic,
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=drifting_requester,
        )
    assert sum(method == "POST" for method, _path, _headers in device.calls) == post_count


def test_terminal_timeout_is_unknown_with_one_arm_execute_and_no_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    device = FakeDevice(context)
    registry = tmp_path / "claims"
    diagnostic = tmp_path / "j2-off.json"
    physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1

    def timeout_requester(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        if (
            method == "GET"
            and path == campaign.ENDPOINTS["status"]
            and device.execute_count == 1
        ):
            device.calls.append((method, path, headers))
            return 200, {"state": "running", "phase": 2, "next_ordinal": 1}
        return device(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )

    result_file = tmp_path / "timeout-result.json"
    result = physical.run_once(
        context,
        "http://fake-device",
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=timeout_requester,
        poll_count=2,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["error"] == "device did not reach terminal state"
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == 1
    assert physical.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "unknown_do_not_retry_or_recover"


@pytest.mark.parametrize("transient_failures", [1, 3])
def test_terminal_get_exceptions_then_complete_do_not_repeat_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transient_failures: int,
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    device = FakeDevice(context)
    registry = tmp_path / "claims"
    diagnostic = tmp_path / "j2-off.json"
    physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1
    terminal_get_attempts = 0
    sleeps: list[float] = []

    def transient_timeout_requester(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        nonlocal terminal_get_attempts
        if (
            method == "GET"
            and path == campaign.ENDPOINTS["status"]
            and device.execute_count == 1
        ):
            terminal_get_attempts += 1
            if terminal_get_attempts <= transient_failures:
                device.calls.append((method, path, headers))
                raise TimeoutError("synchronous display driver owns the server")
        return device(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )

    result_file = tmp_path / "eventual-terminal-result.json"
    result = physical.run_once(
        context,
        "http://fake-device",
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=transient_timeout_requester,
        poll_count=transient_failures + 1,
        poll_interval_seconds=0.125,
        sleeper=sleeps.append,
    )

    assert result["outcome"] == "complete_pass", result["error"]
    assert terminal_get_attempts == transient_failures + 1
    assert sleeps == [0.125] * transient_failures
    assert device.arm_count == 1
    assert device.execute_count == 1
    assert device.driver_count == 1
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == 1
    assert result["network"]["get_requests"] == 7
    assert len(result["transcript"]) == 9
    assert physical.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "complete_pass"


def test_exhausted_terminal_get_exceptions_are_unknown_without_mutation_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    device = FakeDevice(context)
    registry = tmp_path / "claims"
    diagnostic = tmp_path / "j2-off.json"
    physical.diagnose_j2_off(
        context,
        "http://fake-device",
        evidence_file=diagnostic,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    device.busy = 1
    terminal_get_attempts = 0
    sleeps: list[float] = []

    def persistent_timeout_requester(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        nonlocal terminal_get_attempts
        if (
            method == "GET"
            and path == campaign.ENDPOINTS["status"]
            and device.execute_count == 1
        ):
            terminal_get_attempts += 1
            device.calls.append((method, path, headers))
            raise TimeoutError("synchronous display driver still owns the server")
        return device(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )

    result_file = tmp_path / "exhausted-terminal-result.json"
    result = physical.run_once(
        context,
        "http://fake-device",
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=37.0,
        requester=persistent_timeout_requester,
        poll_count=3,
        poll_interval_seconds=0.125,
        sleeper=sleeps.append,
    )

    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["error"] == "synchronous display driver still owns the server"
    assert terminal_get_attempts == 3
    assert sleeps == [0.125, 0.125]
    assert device.arm_count == 1
    assert device.execute_count == 1
    assert device.driver_count == 1
    assert sum(
        method == "POST" and path == campaign.ENDPOINTS["arm"]
        for method, path, _headers in device.calls
    ) == 1
    assert sum(
        method == "POST" and path == campaign.ENDPOINTS["execute"]
        for method, path, _headers in device.calls
    ) == 1
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == 1
    assert result["network"]["get_requests"] == 5
    assert len(result["transcript"]) == 7
    assert physical.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "unknown_do_not_retry_or_recover"


def test_synthetic_release_is_rejected_before_request_or_claim(
    tmp_path: Path,
) -> None:
    campaign_file = tmp_path / "campaign.json"
    release_file = tmp_path / "synthetic-release.json"
    campaign.generate_campaign(campaign_file)
    campaign.materialize_synthetic_release(
        campaign_file=campaign_file,
        fixture_directory=(
            Path(__file__).resolve().parent / "fixtures" / "ec5_color_lab"
        ),
        output_file=release_file,
    )
    context = physical.load_release(release_file)
    called = False

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        nonlocal called
        called = True
        raise AssertionError("requester must not be called")

    registry = tmp_path / "claims"
    with pytest.raises(physical.ColorLabPhysicalError, match="synthetic/offline"):
        physical.run_once(
            context,
            "http://fake-device",
            1,
            authorization=physical.required_authorization(context, 1),
            result_file=tmp_path / "result.json",
            claim_registry=registry,
            j2_off_diagnostic_file=tmp_path / "diagnostic.json",
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=requester,
        )
    assert called is False
    assert not registry.exists()


def test_describe_distinguishes_white_checkpoints_and_recommended_stops(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    assert physical.describe(context, 3)["white_checkpoint_after_this_action"] is True
    assert physical.describe(context, 3)["recommended_safe_stop_after_observation"] is False
    assert physical.describe(context, 5)["recommended_safe_stop_after_observation"] is True
    assert physical.describe(context, 11)["first_complete_u04_u07_round_finished"] is True
    assert physical.describe(context, 23)["recommended_safe_stop_after_observation"] is True


def test_resealed_operator_pre_action_tamper_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _bypass_offline_replay(monkeypatch)
    context = _context(tmp_path)
    device = FakeDevice(context)
    registry, _diagnostic, result_file = _complete_first_action(
        context, device, tmp_path
    )
    root = deepcopy(campaign._decode(result_file.read_bytes(), label="result"))
    root.pop("integrity")
    root["operator_pre_action"]["j2_on"] = False
    tampered = physical._seal(root)
    tampered_file = tmp_path / "tampered-result.json"
    tampered_file.write_bytes(campaign.canonical_json_bytes(tampered))
    with pytest.raises(
        physical.ColorLabPhysicalError, match="operator pre-action differs"
    ):
        physical.validate_result(context, tampered_file, claim_registry=registry)


def test_superseded_release_fails_before_request_or_claim(tmp_path: Path) -> None:
    context = _context(tmp_path)
    marker = {
        "schema_version": 1,
        "kind": campaign.SUPERSEDED_MARKER_KIND,
        "state": campaign.SUPERSEDED_MARKER_STATE,
        "reason": "firmware BIN and ELF references point to mutable .pio build output",
        "superseded_by": campaign.V2_SELF_CONTAINED_RELEASE_DIRECTORY,
        "visible_refresh_authorized": False,
        "device_access_performed": False,
        "claim_created": False,
    }
    (tmp_path / campaign.SUPERSEDED_MARKER_NAME).write_bytes(
        campaign.canonical_json_bytes(marker)
    )
    called = False

    def requester(*_args: Any, **_kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        nonlocal called
        called = True
        raise AssertionError("requester must not be called")

    registry = tmp_path / "claims"
    with pytest.raises(physical.ColorLabPhysicalError, match="release is superseded"):
        physical.run_once(
            context,
            "http://fake-device",
            1,
            authorization=physical.required_authorization(context, 1),
            result_file=tmp_path / "result.json",
            claim_registry=registry,
            j2_off_diagnostic_file=tmp_path / "diagnostic.json",
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=37.0,
            requester=requester,
        )
    assert called is False
    assert not registry.exists()


def test_role_specific_observation_templates_are_short_and_non_authorizing(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    expected_field = {
        1: "full_screen_clean_white",
        2: "observed_colour_name",
        4: "blind_left_visual_equivalence_groups_slots_0_to_7",
        6: "six_code_map_fidelity_pass",
        7: "blind_visual_equivalence_groups_rows_0_to_5",
        9: "six_code_map_fidelity_pass",
        10: "blind_visual_equivalence_groups_rows_0_to_5",
    }
    for ordinal, field in expected_field.items():
        template = physical.observation_template(context, ordinal)
        assert Path(template["preview"]["file"]).is_file()
        assert len(template["common_checks"]) == 7
        assert field in template["role_observation_fields"]
        assert template["one_operator_reply_may_cover_all_fields"] is True
        assert template["thirty_minute_hold_required"] is False
        assert template["visible_refresh_authorized"] is False
        assert template["automatic_next_action_authorized"] is False
