from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_color_lab_campaign as campaign
from tools import mf1750_ec5_color_lab_contract as contract
from tools import mf1750_ec5_color_lab_physical_once as physical


BOOT_NONCE_A = "13579bdf2468ace0"
BOOT_NONCE_B = "02468ace13579bdf"
ARM_NONCE = "a1b2c3d4e5f60718"
BASE_URL = "http://offline-fake-device"


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
    value = _identity("not-present-in-mutation-response")
    value.pop("schema_version")
    value.pop("kind")
    return value


def _device_action(action: Mapping[str, Any]) -> dict[str, Any]:
    """Reproduce the firmware JSON independently of the host helper."""

    return {
        "ordinal": action["ordinal"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "prior_static_action_id": action["action_identity_preimage"][
            "prior_static_action_id"
        ],
        "role": action["role"],
        "round": action["round"],
        "branch": action["branch"],
        "frame_sha256": action["frame_sha256"],
        "cs1_dtm_sha256": action["cs1_dtm_sha256"],
        "cs2_dtm_sha256": action["cs2_dtm_sha256"],
    }


def _nvs_contract() -> dict[str, Any]:
    return {
        "namespace": contract.NVS_NAMESPACE,
        "key": contract.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 24,
    }


def _mutation_headers(
    action: Mapping[str, Any], *, intent: str, boot_nonce: str, arm_nonce: str | None
) -> dict[str, str]:
    headers = {
        "X-EC5-Build-Tag": contract.BUILD_TAG,
        "X-EC5-Test-Id": contract.TEST_ID,
        "X-EC5-Campaign-Id": contract.CAMPAIGN_ID,
        "X-EC5-Action-Id": str(action["action_id"]),
        "X-EC5-Ordinal": str(action["ordinal"]),
        "X-EC5-Descriptor-Id": str(action["descriptor_id"]),
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Intent": intent,
    }
    if arm_nonce is not None:
        headers["X-EC5-Arm-Nonce"] = arm_nonce
    return headers


def _context(tmp_path: Path) -> physical.ReleaseContext:
    compiled = campaign.build_campaign()
    return physical.ReleaseContext(
        release_file=(tmp_path / "offline-real-shaped-release.json").resolve(),
        release_root={
            "execution_eligible": True,
            "evidence_mode": campaign.REAL_MODE,
            "firmware": {
                "binary": {
                    "file": str((tmp_path / "never-flashed.bin").resolve()),
                    "bytes": 123456,
                    "file_sha256": "a" * 64,
                }
            },
            "predecessor_binding": {
                "compare_binding": {
                    "fixture": "offline-only",
                    "latest_visible_state": "u04_u05_compare_four_blue_patches",
                }
            },
        },
        release_file_sha256="b" * 64,
        release_canonical_sha256="c" * 64,
        campaign_file=(tmp_path / "offline-campaign.json").resolve(),
        campaign_root=compiled,
        actions=tuple(deepcopy(compiled["actions"])),
        execution_eligible=True,
        formal_u07_registry=(tmp_path / "never-touched-formal-u07").resolve(),
    )


def _install_offline_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the test synthetic while exercising the public physical workflow."""

    monkeypatch.setattr(physical, "_revalidate_real_release", lambda _context: None)
    monkeypatch.setattr(
        physical,
        "_formal_u07_snapshot",
        lambda _context: {
            "registry": "offline-synthetic-formal-u07-registry",
            "action_id": "d" * 64,
            "claim_absent": True,
            "entries": 0,
        },
    )


class StrictFakeDevice:
    """Stateful, schema-shaped COLOR_LAB device with no I/O side effects."""

    def __init__(
        self, context: physical.ReleaseContext, claim_registry: Path
    ) -> None:
        self.context = context
        self.claim_registry = claim_registry
        self.boot_nonce = BOOT_NONCE_A
        self.driver_powered = False
        self.next_ordinal = 1
        self.phase = 0
        self.key_present = False
        self.arm_request_count = 0
        self.execute_request_count = 0
        self.total_driver_call_count = 0
        self.last_completed_ordinal: int | None = None
        self.calls: list[dict[str, Any]] = []
        self.claim_seen_before_arm: list[str] = []
        self.driver_action_ordinals: list[int] = []
        self.extra_ready_arm_count = 0
        self.extra_terminal_driver_count = 0
        self.auto_chain_after_execute = False

    @property
    def current_action(self) -> Mapping[str, Any]:
        if not 1 <= self.next_ordinal <= len(self.context.actions):
            raise AssertionError("fake device has no current campaign action")
        return self.context.actions[self.next_ordinal - 1]

    def reboot_before_first_action(self, nonce: str) -> None:
        """Model a real reboot with virgin NVS but a new volatile boot nonce."""

        self.boot_nonce = nonce
        self.next_ordinal = 1
        self.phase = 0
        self.key_present = False
        self.arm_request_count = 0
        self.execute_request_count = 0
        self.total_driver_call_count = 0
        self.last_completed_ordinal = None

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
            "nvs_contract": _nvs_contract(),
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
            "actions": [_device_action(action) for action in self.context.actions],
            "nvs_contract": _nvs_contract(),
        }

    def _status(self) -> dict[str, Any]:
        if self.phase == 0:
            state = "complete" if self.next_ordinal == 24 else "ready"
            phase_name = "READY"
            current_action = None
        elif self.phase == 1:
            state = "armed"
            phase_name = "ARMED"
            current_action = _device_action(self.current_action)
        else:  # pragma: no cover - the fake never exposes transient CONSUMED
            raise AssertionError("fake phase is outside the exercised firmware states")
        return {
            **_identity("mf1750-ec5-color-lab-status"),
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "boot_nonce": self.boot_nonce,
            "state": state,
            "phase": self.phase,
            "phase_name": phase_name,
            "cursor_raw": self.phase * 256 + self.next_ordinal,
            "next_ordinal": self.next_ordinal,
            "current_action": current_action,
            "campaign_complete": self.phase == 0 and self.next_ordinal == 24,
            "fixture_self_check_passed": True,
            "cursor_valid": True,
            "persistent_key_present": self.key_present,
            "execute_pending": False,
            "arm_request_count": (
                self.arm_request_count + self.extra_ready_arm_count
                if self.phase == 0
                else self.arm_request_count
            ),
            "execute_request_count": self.execute_request_count,
            "total_driver_call_count": (
                self.total_driver_call_count
                + (
                    self.extra_terminal_driver_count
                    if self.last_completed_ordinal is not None
                    else 0
                )
            ),
            "gpio_initialized": True,
            "busy": 1 if self.driver_powered else 0,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "nvs_contract": _nvs_contract(),
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
            "error": "no_execute_report",
            "driver_called": False,
            "driver_call_count_for_action": 0,
            "total_driver_call_count": self.total_driver_call_count,
            "phase": self.phase,
            "next_ordinal": self.next_ordinal,
            "no_retry": True,
            "no_recovery": True,
        }

    def _driver_evidence(self, action: Mapping[str, Any]) -> dict[str, Any]:
        frame = action["frame"]["frame"]
        return {
            "driver_evidence_schema_version": contract.DRIVER_EVIDENCE_SCHEMA_VERSION,
            "operation_id": int(action["ordinal"]),
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "mapping_applied": True,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "post_psr_busy_seen": True,
            "pre_command_idle_failure": False,
            "failure_stage": "NONE",
            "failure_code": 0,
            "spi_hz": 8_000_000,
            "free_psram_before": 2_000_000,
            "largest_psram_block_before": 1_000_000,
            "input_fnv1a": int(frame["fnv1a"], 16),
            "cs1_dtm_fnv1a": int(frame["controllers"][0]["fnv1a"], 16),
            "cs2_dtm_fnv1a": int(frame["controllers"][1]["fnv1a"], 16),
            "total_ms": 1000,
            "cs1_upload_ms": 100,
            "cs2_upload_ms": 100,
            "pon_ms": 200,
            "drf_ms": 400,
            "pof_ms": 100,
            "post_psr_ms": 100,
            "last_wait_stage": "POST_PSR",
            "timeout_stage": "NONE",
            "busy_missing_stage": "NONE",
            "pre_command_busy_stage": "NONE",
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        }

    def _complete_report(self, action: Mapping[str, Any]) -> dict[str, Any]:
        ordinal = int(action["ordinal"])
        return {
            **_identity("mf1750-ec5-color-lab-report"),
            "valid": True,
            "classification": "TECHNICAL_EVALUATION_ONLY",
            "boot_nonce": self.boot_nonce,
            "ordinal": ordinal,
            "descriptor_id": action["descriptor_id"],
            "action_id": action["action_id"],
            "role": action["role"],
            "round": action["round"],
            "branch": action["branch"],
            "job_id": ordinal,
            "terminal_state": "COMPLETE",
            "result": True,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "total_driver_call_count": self.total_driver_call_count,
            "phase": 0,
            "phase_name": "READY",
            "next_ordinal": ordinal + 1,
            "campaign_complete": ordinal == campaign.ACTION_COUNT,
            "no_retry": True,
            "no_recovery": True,
            "job_queued_at_ms": ordinal * 1000,
            "job_started_at_ms": ordinal * 1000 + 1,
            "job_finished_at_ms": ordinal * 1000 + 2,
            "driver": self._driver_evidence(action),
        }

    def _report(self) -> dict[str, Any]:
        if self.last_completed_ordinal is None:
            return self._not_executed_report()
        action = self.context.actions[self.last_completed_ordinal - 1]
        return self._complete_report(action)

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

    def _assert_claim_precedes_arm(self, action: Mapping[str, Any]) -> None:
        path = self.claim_registry / f"{action['action_id']}.json"
        assert path.is_file(), "host must durably claim before its first ARM POST"
        claim = json.loads(path.read_text(encoding="utf-8"))
        assert claim["state"] == "permanently_claimed_before_first_arm_post"
        assert claim["action"]["ordinal"] == action["ordinal"]
        assert claim["action"]["action_id"] == action["action_id"]
        self.claim_seen_before_arm.append(str(action["action_id"]))

    def __call__(
        self,
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        assert base_url == BASE_URL
        assert timeout > 0
        self.calls.append(
            {"method": method, "path": path, "headers": dict(headers or {})}
        )
        if method == "GET":
            assert headers is None
            if path == campaign.ENDPOINTS["version"]:
                return 200, self._version()
            if path == campaign.ENDPOINTS["manifest"]:
                return 200, self._manifest()
            if path == campaign.ENDPOINTS["status"]:
                return 200, self._status()
            if path == campaign.ENDPOINTS["report"]:
                return 200, self._report()
        if method == "POST" and path == campaign.ENDPOINTS["arm"]:
            action = self.current_action
            self._assert_claim_precedes_arm(action)
            assert dict(headers or {}) == _mutation_headers(
                action,
                intent=campaign.ARM_INTENT,
                boot_nonce=self.boot_nonce,
                arm_nonce=None,
            )
            self.arm_request_count += 1
            self.key_present = True
            self.phase = 1
            return 201, self._arm_response(action)
        if method == "POST" and path == campaign.ENDPOINTS["execute"]:
            action = self.current_action
            assert self.phase == 1
            assert dict(headers or {}) == _mutation_headers(
                action,
                intent=campaign.EXECUTE_INTENT,
                boot_nonce=self.boot_nonce,
                arm_nonce=ARM_NONCE,
            )
            self.execute_request_count += 1
            self.total_driver_call_count += 1
            self.driver_action_ordinals.append(int(action["ordinal"]))
            response = self._execute_response(action)
            self.last_completed_ordinal = int(action["ordinal"])
            self.next_ordinal += 1
            self.phase = 0
            if self.auto_chain_after_execute:
                hidden_action = self.current_action
                self.total_driver_call_count += 1
                self.driver_action_ordinals.append(int(hidden_action["ordinal"]))
                self.last_completed_ordinal = int(hidden_action["ordinal"])
                self.next_ordinal += 1
            return 202, response
        raise AssertionError(f"unexpected fake request: {method} {path}")


def _diagnose(
    context: physical.ReleaseContext,
    device: StrictFakeDevice,
    registry: Path,
    diagnostic_file: Path,
) -> dict[str, Any]:
    device.driver_powered = False
    diagnostic = physical.diagnose_j2_off(
        context,
        BASE_URL,
        evidence_file=diagnostic_file,
        claim_registry=registry,
        confirm_j2_off=True,
        requester=device,
    )
    validated = physical.validate_j2_off_diagnostic(
        context, diagnostic_file, claim_registry=registry
    )
    assert validated == diagnostic
    assert diagnostic["network"] == {"get_requests": 4, "post_requests": 0}
    assert diagnostic["snapshot"]["status"]["busy"] == 0
    assert diagnostic["snapshot"]["status"]["current_action"] is None
    assert diagnostic["snapshot"]["status"]["cursor_raw"] == 1
    assert diagnostic["snapshot"]["status"]["persistent_key_present"] is False
    return diagnostic


def _run_ordinal_one(
    context: physical.ReleaseContext,
    device: StrictFakeDevice,
    registry: Path,
    diagnostic_file: Path,
    result_file: Path,
) -> dict[str, Any]:
    device.driver_powered = True
    return physical.run_once(
        context,
        BASE_URL,
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=36.5,
        requester=device,
        poll_count=1,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )


def _seal_observation(
    context: physical.ReleaseContext,
    *,
    result_file: Path,
    observation_file: Path,
    registry: Path,
    clean_white: bool,
) -> dict[str, Any]:
    observation = physical.seal_observation(
        context,
        result_file=result_file,
        observation_file=observation_file,
        claim_registry=registry,
        operator_report="offline fake display matched its frozen reference",
        temperature_c=36.5,
        confirm_reference_preview_checked=True,
        confirm_display_matches_reference=True,
        confirm_no_unexpected_residual=True,
        confirm_electrical_normal=True,
        confirm_esp32_no_restart=True,
        confirm_clean_white=clean_white,
    )
    assert physical.validate_observation(
        context,
        observation_file,
        result_file=result_file,
        claim_registry=registry,
    ) == observation
    return observation


def test_two_actions_e2e_share_boot_and_require_explicit_second_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_offline_boundaries(monkeypatch)
    context = _context(tmp_path)
    registry = tmp_path / "claims"
    diagnostic_file = tmp_path / "j2-off.json"
    device = StrictFakeDevice(context, registry)

    diagnostic = _diagnose(context, device, registry, diagnostic_file)
    assert [call["method"] for call in device.calls] == ["GET"] * 4
    assert not registry.exists()

    result1_file = tmp_path / "ordinal-1-result.json"
    result1 = _run_ordinal_one(
        context, device, registry, diagnostic_file, result1_file
    )
    assert result1["outcome"] == "complete_pass", result1["error"]
    assert result1["preflight"]["boot_nonce"] == diagnostic["boot_nonce"]
    assert result1["network"] == {
        "get_requests": 7,
        "arm_posts": 1,
        "execute_posts": 1,
        "maximum_arm_posts": 1,
        "maximum_execute_posts": 1,
        "automatic_retry": False,
        "automatic_recovery": False,
        "automatic_chaining": False,
    }
    assert result1["device"]["armed_status"]["current_action"] == _device_action(
        context.actions[0]
    )
    assert result1["device"]["armed_status"]["cursor_raw"] == 257
    assert result1["device"]["terminal_status"]["current_action"] is None
    assert result1["device"]["terminal_status"]["cursor_raw"] == 2
    assert result1["device"]["terminal_status"]["persistent_key_present"] is True
    assert result1["device"]["terminal_report"]["round"] == 0
    assert result1["device"]["terminal_report"]["branch"] == (
        "COMPARE_AFTER_WHITE"
    )
    assert physical.validate_result(
        context, result1_file, claim_registry=registry
    )["outcome"] == "complete_pass"
    assert device.claim_seen_before_arm == [context.actions[0]["action_id"]]
    assert device.driver_action_ordinals == [1]
    assert device.next_ordinal == 2
    assert [
        call["path"] for call in device.calls if call["method"] == "POST"
    ] == [campaign.ENDPOINTS["arm"], campaign.ENDPOINTS["execute"]]

    observation1_file = tmp_path / "ordinal-1-observation.json"
    _seal_observation(
        context,
        result_file=result1_file,
        observation_file=observation1_file,
        registry=registry,
        clean_white=True,
    )

    calls_before_ordinal2_preflight = len(device.calls)
    ordinal2_preflight = physical.preflight(
        context, BASE_URL, 2, requester=device
    )
    assert len(device.calls) - calls_before_ordinal2_preflight == 4
    assert ordinal2_preflight.boot_nonce == BOOT_NONCE_A
    assert ordinal2_preflight.status["current_action"] is None
    assert ordinal2_preflight.status["cursor_raw"] == 2
    assert ordinal2_preflight.status["arm_request_count"] == 1
    assert ordinal2_preflight.report["ordinal"] == 1
    assert ordinal2_preflight.report["branch"] == "COMPARE_AFTER_WHITE"
    assert device.driver_action_ordinals == [1]

    result2_file = tmp_path / "ordinal-2-result.json"
    result2 = physical.run_once(
        context,
        BASE_URL,
        2,
        authorization=physical.required_authorization(context, 2),
        result_file=result2_file,
        claim_registry=registry,
        prior_result_file=result1_file,
        prior_observation_file=observation1_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=36.5,
        requester=device,
        poll_count=1,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )
    assert result2["outcome"] == "complete_pass", result2["error"]
    assert result2["preflight"]["boot_nonce"] == BOOT_NONCE_A
    assert result2["preflight"]["status"]["cursor_raw"] == 2
    assert result2["preflight"]["status"]["persistent_key_present"] is True
    assert result2["device"]["terminal_status"]["cursor_raw"] == 3
    assert {
        key: result2["device"]["terminal_status"][key]
        for key in (
            "arm_request_count",
            "execute_request_count",
            "total_driver_call_count",
        )
    } == {
        "arm_request_count": 2,
        "execute_request_count": 2,
        "total_driver_call_count": 2,
    }
    assert result2["device"]["terminal_report"]["role"] == "U07_ISOLATED"
    assert result2["device"]["terminal_report"]["round"] == 0
    assert result2["device"]["terminal_report"]["branch"] == "ISOLATED_U07"
    assert physical.validate_result(
        context, result2_file, claim_registry=registry
    )["outcome"] == "complete_pass"
    assert device.claim_seen_before_arm == [
        context.actions[0]["action_id"],
        context.actions[1]["action_id"],
    ]
    assert device.driver_action_ordinals == [1, 2]

    _seal_observation(
        context,
        result_file=result2_file,
        observation_file=tmp_path / "ordinal-2-observation.json",
        registry=registry,
        clean_white=False,
    )


def test_real_urllib_preparation_keeps_post_truly_bodyless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise stdlib header preparation without opening a socket."""

    captured: dict[str, Any] = {}

    class HandlerParent:
        addheaders: list[tuple[str, str]] = []

    class OfflineResponse:
        def __enter__(self) -> OfflineResponse:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        @staticmethod
        def getcode() -> int:
            return 201

        @staticmethod
        def read(_maximum: int) -> bytes:
            return b'{"accepted":true}'

    def offline_urlopen(
        request: physical.urllib.request.Request, *, timeout: float
    ) -> OfflineResponse:
        handler = physical.urllib.request.HTTPHandler()
        handler.parent = HandlerParent()
        prepared = handler.do_request_(request)
        captured.update(
            {
                "data": prepared.data,
                "headers": {
                    key.lower(): value for key, value in prepared.header_items()
                },
                "method": prepared.get_method(),
                "timeout": timeout,
            }
        )
        return OfflineResponse()

    monkeypatch.setattr(physical.urllib.request, "urlopen", offline_urlopen)
    status, response = physical.http_request(
        BASE_URL,
        campaign.ENDPOINTS["arm"],
        method="POST",
        headers={"X-EC5-Intent": campaign.ARM_INTENT},
        timeout=2.5,
    )

    assert status == 201
    assert response == {"accepted": True}
    assert captured["method"] == "POST"
    assert captured["timeout"] == 2.5
    assert captured["data"] is None
    assert captured["headers"]["x-ec5-intent"] == campaign.ARM_INTENT
    assert "content-type" not in captured["headers"]
    assert "content-length" not in captured["headers"]


def test_v3_identity_derivation_can_isolate_burned_v2_without_nvs_erase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove the proposed fresh-namespace scheme before a V3 is released."""

    old_descriptors = tuple(deepcopy(contract.DESCRIPTORS))
    old_descriptor_ids = {item["descriptor_id"] for item in old_descriptors}
    old_action_ids = {
        item["hardware_action_id"] for item in old_descriptors
    }
    old_cursor_address = (contract.NVS_NAMESPACE, contract.NVS_KEY)
    registry = tmp_path / "claims"
    registry.mkdir()
    old_first_claim = (
        registry / f"{old_descriptors[0]['hardware_action_id']}.json"
    )
    old_first_claim.write_text("burned-v2-claim-must-remain", encoding="utf-8")

    proposed_namespace = "mf1750_ec5cl3"
    assert len(proposed_namespace.encode("utf-8")) <= 15
    monkeypatch.setattr(contract, "CAMPAIGN_ID", "EC5_COLOR_LAB_CAMPAIGN_V3")
    monkeypatch.setattr(
        contract, "BUILD_TAG", "MF1750_EC5_COLOR_LAB_V3_2026-08-10"
    )
    monkeypatch.setattr(contract, "TEST_ID", "EC5-COLOR-LAB-V3")
    monkeypatch.setattr(
        contract, "DEVICE_API_VERSION", "MF1750_EC5_COLOR_LAB_DEVICE_V3"
    )
    monkeypatch.setattr(contract, "IDENTITY_REVISION", "color-lab-v3")
    monkeypatch.setattr(contract, "NVS_NAMESPACE", proposed_namespace)

    proposed_descriptors = contract.action_descriptors()
    proposed_descriptor_ids = {
        item["descriptor_id"] for item in proposed_descriptors
    }
    proposed_action_ids = {
        item["hardware_action_id"] for item in proposed_descriptors
    }
    proposed_cursor_address = (contract.NVS_NAMESPACE, contract.NVS_KEY)

    assert proposed_cursor_address != old_cursor_address
    assert proposed_descriptor_ids.isdisjoint(old_descriptor_ids)
    assert proposed_action_ids.isdisjoint(old_action_ids)
    assert all(
        item["action_identity_preimage"]["nvs_namespace"]
        == proposed_namespace
        for item in proposed_descriptors
    )
    assert all(
        item["campaign_id"] == "EC5_COLOR_LAB_CAMPAIGN_V3"
        and item["build_tag"] == "MF1750_EC5_COLOR_LAB_V3_2026-08-10"
        and item["test_id"] == "EC5-COLOR-LAB-V3"
        and item["device_api_version"] == "MF1750_EC5_COLOR_LAB_DEVICE_V3"
        and item["identity_revision"] == "color-lab-v3"
        for item in proposed_descriptors
    )

    proposed_first_claim = (
        registry / f"{proposed_descriptors[0]['hardware_action_id']}.json"
    )
    assert proposed_first_claim != old_first_claim
    assert proposed_first_claim.exists() is False
    assert old_first_claim.read_text(encoding="utf-8") == (
        "burned-v2-claim-must-remain"
    )

    # Install the proposed table only inside this synthetic test.  The same
    # registry can retain the burned V2 claim because the V3 path is distinct.
    monkeypatch.setattr(contract, "DESCRIPTORS", tuple(proposed_descriptors))
    monkeypatch.setattr(campaign, "IDENTITY_REVISION", "color-lab-v3")
    monkeypatch.setattr(
        campaign, "BUILD_TAG", "MF1750_EC5_COLOR_LAB_V3_2026-08-10"
    )
    monkeypatch.setattr(campaign, "TEST_ID", "EC5-COLOR-LAB-V3")
    monkeypatch.setattr(
        campaign, "DEVICE_API_VERSION", "MF1750_EC5_COLOR_LAB_DEVICE_V3"
    )
    monkeypatch.setattr(campaign, "NVS_NAMESPACE", proposed_namespace)
    monkeypatch.setattr(
        physical, "CLAIM_REGISTRY_ID", "workspace-mf1750-ec5-color-lab-claims-v3"
    )
    _install_offline_boundaries(monkeypatch)

    context = _context(tmp_path)
    device = StrictFakeDevice(context, registry)
    diagnostic_file = tmp_path / "v3-j2-off.json"
    _diagnose(context, device, registry, diagnostic_file)
    result_file = tmp_path / "v3-ordinal-1.json"
    result = _run_ordinal_one(
        context, device, registry, diagnostic_file, result_file
    )

    assert result["outcome"] == "complete_pass", result["error"]
    assert result["action"]["action_id"] in proposed_action_ids
    assert result["action"]["action_id"] not in old_action_ids
    assert proposed_first_claim.is_file()
    assert old_first_claim.read_text(encoding="utf-8") == (
        "burned-v2-claim-must-remain"
    )
    new_claim = json.loads(proposed_first_claim.read_text(encoding="utf-8"))
    assert new_claim["registry_id"] == (
        "workspace-mf1750-ec5-color-lab-claims-v3"
    )
    assert new_claim["action"]["action_id"] == result["action"]["action_id"]


def test_rejected_v2_arm_burns_claim_and_cannot_be_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mirror the live HTTP-400 boundary without touching the live registry."""

    _install_offline_boundaries(monkeypatch)
    context = _context(tmp_path)
    registry = tmp_path / "claims"
    diagnostic_file = tmp_path / "j2-off.json"
    result_file = tmp_path / "v2-failed-result.json"
    device = StrictFakeDevice(context, registry)
    _diagnose(context, device, registry, diagnostic_file)

    def rejected_arm_requester(
        base_url: str,
        path: str,
        *,
        method: str,
        headers: Mapping[str, str] | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        if method == "POST" and path == campaign.ENDPOINTS["arm"]:
            action = device.current_action
            device._assert_claim_precedes_arm(action)
            device.calls.append(
                {"method": method, "path": path, "headers": dict(headers or {})}
            )
            device.arm_request_count += 1
            raise physical.ColorLabPhysicalError(
                "POST /api/ec5/color-lab/arm failed: HTTP Error 400: Bad Request"
            )
        return device(
            base_url,
            path,
            method=method,
            headers=headers,
            timeout=timeout,
        )

    device.driver_powered = True
    result = physical.run_once(
        context,
        BASE_URL,
        1,
        authorization=physical.required_authorization(context, 1),
        result_file=result_file,
        claim_registry=registry,
        j2_off_diagnostic_file=diagnostic_file,
        confirm_no_intervening_visible_refresh=True,
        confirm_j2_on=True,
        confirm_electrical_normal=True,
        temperature_c=36.0,
        requester=rejected_arm_requester,
        poll_count=1,
        poll_interval_seconds=0,
        sleeper=lambda _seconds: None,
    )

    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["network"]["get_requests"] == 4
    assert result["network"]["arm_posts"] == 0
    assert result["network"]["execute_posts"] == 0
    assert result["device"] == {
        "arm_response": None,
        "armed_status": None,
        "execute_response": None,
        "terminal_status": None,
        "terminal_report": None,
    }
    assert device.arm_request_count == 1
    assert device.execute_request_count == 0
    assert device.total_driver_call_count == 0
    assert device.driver_action_ordinals == []
    assert physical.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "unknown_do_not_retry_or_recover"

    calls_after_failure = deepcopy(device.calls)
    with pytest.raises(physical.ColorLabPhysicalError, match="claim.*already exists"):
        physical.run_once(
            context,
            BASE_URL,
            1,
            authorization=physical.required_authorization(context, 1),
            result_file=tmp_path / "forbidden-v2-retry.json",
            claim_registry=registry,
            j2_off_diagnostic_file=diagnostic_file,
            confirm_no_intervening_visible_refresh=True,
            confirm_j2_on=True,
            confirm_electrical_normal=True,
            temperature_c=36.0,
            requester=device,
        )
    assert device.calls == calls_after_failure
    assert not (tmp_path / "forbidden-v2-retry.json").exists()


def test_reboot_nonce_mismatch_rejects_before_claim_arm_or_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_offline_boundaries(monkeypatch)
    context = _context(tmp_path)
    registry = tmp_path / "claims"
    diagnostic_file = tmp_path / "j2-off.json"
    result_file = tmp_path / "must-not-exist.json"
    device = StrictFakeDevice(context, registry)
    _diagnose(context, device, registry, diagnostic_file)

    device.reboot_before_first_action(BOOT_NONCE_B)
    device.driver_powered = True
    with pytest.raises(
        physical.ColorLabPhysicalError,
        match="current device boot nonce differs",
    ):
        _run_ordinal_one(context, device, registry, diagnostic_file, result_file)
    assert [call["method"] for call in device.calls] == ["GET"] * 8
    assert not registry.exists()
    assert not result_file.exists()
    assert device.claim_seen_before_arm == []
    assert device.driver_action_ordinals == []


def test_extra_cumulative_count_rejects_before_claim_or_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_offline_boundaries(monkeypatch)
    context = _context(tmp_path)
    registry = tmp_path / "claims"
    diagnostic_file = tmp_path / "j2-off.json"
    result_file = tmp_path / "must-not-exist.json"
    device = StrictFakeDevice(context, registry)
    _diagnose(context, device, registry, diagnostic_file)
    device.driver_powered = True
    device.extra_ready_arm_count = 1

    with pytest.raises(physical.ColorLabPhysicalError, match="cumulative count"):
        _run_ordinal_one(context, device, registry, diagnostic_file, result_file)
    assert all(call["method"] == "GET" for call in device.calls)
    assert not registry.exists()
    assert not result_file.exists()
    assert device.claim_seen_before_arm == []
    assert device.driver_action_ordinals == []


def test_automatic_hidden_second_action_cannot_be_accepted_as_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_offline_boundaries(monkeypatch)
    context = _context(tmp_path)
    registry = tmp_path / "claims"
    diagnostic_file = tmp_path / "j2-off.json"
    result_file = tmp_path / "ordinal-1-unknown.json"
    device = StrictFakeDevice(context, registry)
    _diagnose(context, device, registry, diagnostic_file)
    device.auto_chain_after_execute = True

    result = _run_ordinal_one(
        context, device, registry, diagnostic_file, result_file
    )
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert result["error"] == "device did not reach terminal state"
    assert result["device"]["terminal_status"] is None
    assert result["device"]["terminal_report"] is None
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == 1
    assert result["network"]["automatic_chaining"] is False
    assert [
        call["path"] for call in device.calls if call["method"] == "POST"
    ] == [campaign.ENDPOINTS["arm"], campaign.ENDPOINTS["execute"]]
    assert device.driver_action_ordinals == [1, 2]
    assert device.next_ordinal == 3
    assert physical.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "unknown_do_not_retry_or_recover"


def test_extra_terminal_driver_count_is_sealed_as_unknown_not_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_offline_boundaries(monkeypatch)
    context = _context(tmp_path)
    registry = tmp_path / "claims"
    diagnostic_file = tmp_path / "j2-off.json"
    result_file = tmp_path / "ordinal-1-count-drift.json"
    device = StrictFakeDevice(context, registry)
    _diagnose(context, device, registry, diagnostic_file)
    device.extra_terminal_driver_count = 1

    result = _run_ordinal_one(
        context, device, registry, diagnostic_file, result_file
    )
    assert result["outcome"] == "unknown_do_not_retry_or_recover"
    assert "cumulative count differs" in str(result["error"])
    assert result["device"]["terminal_status"] is None
    assert result["network"]["arm_posts"] == 1
    assert result["network"]["execute_posts"] == 1
    assert physical.validate_result(
        context, result_file, claim_registry=registry
    )["outcome"] == "unknown_do_not_retry_or_recover"
