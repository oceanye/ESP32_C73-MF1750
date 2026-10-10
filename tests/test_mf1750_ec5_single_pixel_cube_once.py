from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_single_pixel_cube_once as cube


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "src" / "ec5_single_pixel_cube_main_config.inc"
BUNDLE_MANIFEST_PATH = (
    ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_SINGLE_PIXEL_CUBE_V1_20260821"
    / "manifest.json"
)


def _identity(kind: str) -> dict[str, Any]:
    runner = cube.runner
    return {
        "kind": f"mf1750-ec5-single-pixel-cube-{kind}",
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
    }


class FakeCubeDevice:
    def __init__(self, *, busy: int = 1, forbidden_true: str | None = None) -> None:
        self.busy = busy
        self.forbidden_true = forbidden_true
        self.boot_nonce = "0123456789abcdef"
        self.armed = False
        self.executed = False
        self.calls: list[tuple[str, str]] = []

    def _safety(self) -> dict[str, bool]:
        value = {
            key: False
            for key in (
                "automatic_execute",
                "automatic_chaining",
                "startup_refresh",
                "raw_frame_ingress",
                "runtime_lut_write",
                "electrical_parameter_write",
                "dither",
                "spatial_mixing",
                "retry",
                "recovery",
                "partial_refresh",
                "window_refresh",
                "command_0x86",
                "mid_refresh_power_cut",
                "spi_frequency_sweep",
            )
        }
        if self.forbidden_true is not None:
            value[self.forbidden_true] = True
        value["full_screen_global_refresh"] = True
        return value

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
        if name == "version":
            return 200, {
                **_identity("version"),
                "action_count": 5,
                **self._safety(),
                "nvs_contract": {
                    "namespace": cube.runner.NVS_NAMESPACE,
                    "key": cube.runner.NVS_KEY,
                },
            }
        if name == "manifest":
            return 200, {
                **_identity("manifest"),
                "action_count": 5,
                "one_driver_call_per_action": True,
                **self._safety(),
                "actions": list(cube.runner.ACTIONS),
            }
        if name == "status":
            return 200, {
                **_identity("status"),
                "boot_nonce": self.boot_nonce,
                "state": "ready",
                "phase": 0,
                "phase_name": "READY",
                "cursor_raw": 1,
                "next_ordinal": 1,
                "current_action": None,
                "campaign_complete": False,
                "fixture_self_check_passed": True,
                "cursor_valid": True,
                "gpio_initialized": True,
                "busy": self.busy,
                "rst": 0,
                "cs": 0,
                "cs2": 0,
                "execute_pending": False,
                "persistent_key_present": False,
            }
        if name == "report":
            if self.executed:
                return 200, {
                    **_identity("report"),
                    "boot_nonce": self.boot_nonce,
                    "ordinal": 1,
                    "action_id": cube.runner.ACTION_IDS[0],
                    "terminal_state": "COMPLETE",
                    "result": True,
                    "driver_called": True,
                    "driver_call_count_for_action": 1,
                }
            return 200, {
                **_identity("report"),
                "boot_nonce": self.boot_nonce,
                "terminal_state": "NOT_EXECUTED",
                "valid": False,
            }
        if name == "arm":
            assert method == "POST"
            assert headers is not None
            assert headers["X-EC5-Intent"] == cube.runner.ARM_INTENT
            assert "X-EC5-Arm-Nonce" not in headers
            self.armed = True
            return 201, {
                "accepted": True,
                "armed": True,
                "action_id": cube.runner.ACTION_IDS[0],
                "boot_nonce": self.boot_nonce,
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            assert method == "POST" and self.armed
            assert headers is not None
            assert headers["X-EC5-Intent"] == cube.runner.EXECUTE_INTENT
            assert headers["X-EC5-Arm-Nonce"] == "fedcba9876543210"
            self.executed = True
            return 202, {
                "accepted": True,
                "execute_consumed": True,
                "action_id": cube.runner.ACTION_IDS[0],
                "boot_nonce": self.boot_nonce,
            }
        raise AssertionError(name)


@pytest.fixture
def bound_firmware(monkeypatch: pytest.MonkeyPatch) -> None:
    # A hypothetical valid binding exercises the live state machine without
    # claiming the checked-in placeholder is a real firmware identity.
    monkeypatch.setattr(cube.runner, "FIRMWARE_SHA256", "a" * 64)
    monkeypatch.setattr(cube.runner, "FIRMWARE_BYTES", 123456)


def test_missing_firmware_binding_fails_closed_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cube.runner, "FIRMWARE_SHA256", None)
    monkeypatch.setattr(cube.runner, "FIRMWARE_BYTES", None)
    description = cube.describe()
    assert description["firmware"] == {
        "bound": False,
        "bytes": None,
        "sha256": None,
    }
    assert description["live_authorized"] is False
    fake = FakeCubeDevice()
    with pytest.raises(cube.runner.RecheckError, match="offline-only"):
        cube.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
            poll_seconds=0,
            poll_count=1,
        )
    assert fake.calls == []


def test_checked_in_runner_has_the_exact_offline_build_identity() -> None:
    assert cube.describe()["firmware"] == {
        "bound": True,
        "bytes": 789456,
        "sha256": (
            "ffa6e082c3763dc22207a2565b1b47f81014d5fd93b8c5cd1a60636ea362b59b"
        ),
    }


def test_five_actions_match_config_and_offline_bundle() -> None:
    config = CONFIG_PATH.read_text("utf-8")
    bundle = json.loads(BUNDLE_MANIFEST_PATH.read_text("utf-8"))
    assert len(cube.runner.ACTIONS) == bundle["visible_action_count"] == 5
    assert cube.runner.CONTRACT_ID == bundle["integrity"]["canonical_sha256"]
    assert cube.runner.CAMPAIGN_ID == bundle["campaign_id"]
    assert cube.runner.CLASSIFICATION == bundle["classification"]
    assert bundle["history_design"]["unique_three_step_recipes"] == 512
    for action, offline in zip(cube.runner.ACTIONS, bundle["actions"], strict=True):
        for key in (
            "ordinal",
            "descriptor_id",
            "action_id",
            "frame_sha256",
            "cs1_dtm_sha256",
            "cs2_dtm_sha256",
        ):
            assert action[key] == offline[key]
        assert action["action_id"] in config
        assert action["descriptor_id"] in config
    assert [item["prior_static_action_id"] for item in cube.runner.ACTIONS] == [
        None,
        *cube.runner.ACTION_IDS[:-1],
    ]


def test_description_declares_uniform_roi_and_all_forbidden_paths() -> None:
    value = cube.describe()
    assert value["visible_actions"] == 5
    assert value["single_pixel_history"] == {
        "codes": 8,
        "unique_source_mid_target_recipes": 512,
        "uniform_transport_code_per_roi": True,
        "spatial_mixing": False,
        "visible_actions": 5,
    }
    assert value["fixed_transport"] == {
        "spi_hz": 1_000_000,
        "full_screen_global_refresh": True,
    }
    assert all(value["forbidden_operations"].values())
    assert value["automatic_chaining"] is False
    assert value["automatic_retry"] is False
    assert value["automatic_recovery"] is False
    assert value["firmware_flash_performed_by_runner"] is False


def test_one_invocation_claims_then_exactly_one_arm_and_execute(
    tmp_path: Path, bound_firmware: None
) -> None:
    fake = FakeCubeDevice()
    claims = tmp_path / "claims"
    result = cube.run_once(
        "http://192.0.2.1",
        1,
        claims=claims,
        output=tmp_path / "result.json",
        requester=fake,
        poll_seconds=0,
        poll_count=1,
    )
    assert result["outcome"] == "complete_pass"
    assert result["visible_refreshes"] == 1
    assert result["network"]["arm_post"] == 1
    assert result["network"]["execute_post"] == 1
    assert fake.calls.count(("POST", "arm")) == 1
    assert fake.calls.count(("POST", "execute")) == 1
    assert (claims / f"{cube.runner.ACTION_IDS[0]}.json").is_file()
    with pytest.raises(cube.runner.RecheckError, match="already permanently claimed"):
        cube.run_once(
            "http://192.0.2.1",
            1,
            claims=claims,
            output=tmp_path / "retry.json",
            requester=FakeCubeDevice(),
            poll_seconds=0,
            poll_count=1,
        )


@pytest.mark.parametrize(
    "forbidden",
    [
        "partial_refresh",
        "window_refresh",
        "command_0x86",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
    ],
)
def test_preflight_rejects_every_forbidden_device_capability(
    tmp_path: Path, bound_firmware: None, forbidden: str
) -> None:
    fake = FakeCubeDevice(forbidden_true=forbidden)
    with pytest.raises(cube.runner.RecheckError, match="forbidden-operation"):
        cube.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
            poll_seconds=0,
            poll_count=1,
        )
    assert ("POST", "arm") not in fake.calls
    assert ("POST", "execute") not in fake.calls


def test_fixed_routes_and_no_power_or_install_control_surface() -> None:
    assert cube.runner.ENDPOINTS == {
        name: f"/api/ec5/single-pixel-cube/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    source = (ROOT / "tools" / "mf1750_ec5_single_pixel_cube_once.py").read_text(
        "utf-8"
    ).lower()
    for forbidden in (
        "serial.serial",
        "subprocess",
        "requests.post",
        "upload_port",
        "monitor_port",
        "esptool",
    ):
        assert forbidden not in source
