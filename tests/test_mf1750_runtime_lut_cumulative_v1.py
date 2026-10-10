from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_cumulative_v1_once as once
from tools import mf1750_runtime_lut_cumulative_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def _identity(kind: str) -> dict[str, Any]:
    runner = once.base.runner
    return {
        "kind": f"{runner.DEVICE_KIND_PREFIX}-{kind}",
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
    }


def _capabilities() -> dict[str, bool]:
    return {
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "same_palette_hold_probe": False,
        "cross_palette_hold_probe": False,
        "full_frame_cumulative_redraw": True,
    }


def _version() -> dict[str, Any]:
    runner = once.base.runner
    return {
        **_identity("version"),
        "action_count": len(runner.ACTIONS),
        "runtime_lut_write": True,
        **{
            key: False
            for key in (
                "automatic_execute",
                "automatic_chaining",
                "startup_refresh",
                "raw_frame_ingress",
                "electrical_parameter_write",
                "dither",
                "spatial_mixing",
                "retry",
                "recovery",
            )
        },
        "nvs_contract": {
            "namespace": runner.NVS_NAMESPACE,
            "key": runner.NVS_KEY,
        },
        **_capabilities(),
    }


def _manifest() -> dict[str, Any]:
    profile = pack.build_report()["contract"]["profile"]
    return {
        **_identity("manifest"),
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "history_layout": {
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "ptlw_command_issued": False,
            "cropped_dtm": False,
            "all_action_dtm_transport": "packed_frame_per_controller",
            "full_frame_cumulative_redraw": True,
            "white_transport_code": pack.WHITE_CODE,
            **profile,
        },
        **_capabilities(),
    }


class CumulativeFakeDevice:
    def __init__(
        self,
        *,
        busy: int = 0,
        status_overrides: Mapping[str, Any] | None = None,
        safe_busy_after_5ms: int = 1,
    ) -> None:
        self.busy = busy
        self.status_overrides = dict(status_overrides or {})
        self.safe_busy_after_5ms = safe_busy_after_5ms
        self.boot_nonce = "0123456789abcdef"
        self.armed = False
        self.executed = False
        self.calls: list[tuple[str, str]] = []

    def _prior_report(self) -> dict[str, Any]:
        return {
            **_identity("report"),
            "boot_nonce": self.boot_nonce,
            "valid": True,
            "terminal_state": "COMPLETE",
            "result": True,
            "driver_called": True,
            "driver_call_count_for_action": 1,
            "ordinal": 2,
            "action_id": once.base.runner.ACTION_IDS[1],
            "next_ordinal": 3,
            "campaign_complete": False,
            "no_retry": True,
            "no_recovery": True,
            "driver": {
                "valid": True,
                "running": False,
                "sequence_ok": True,
                "wait_timeout": False,
                "busy_assertion_missing": False,
                "pre_command_idle_failure": False,
                "failure_stage": "none",
                "spi_hz": 1_000_000,
                "safe_finish": {
                    "busy_before_pins_low": 1,
                    "busy_after_pins_low": 1,
                    "busy_after_5ms": self.safe_busy_after_5ms,
                    "final_gpio": {
                        "busy": 1,
                        "rst": 0,
                        "cs": 0,
                        "cs2": 0,
                    },
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
        name = path.rsplit("/", 1)[-1]
        self.calls.append((method, name))
        if name == "version":
            return 200, _version()
        if name == "manifest":
            return 200, _manifest()
        if name == "status":
            status = {
                **_identity("status"),
                "boot_nonce": self.boot_nonce,
                "state": "ready",
                "phase": 0,
                "phase_name": "READY",
                "cursor_raw": 3,
                "next_ordinal": 3,
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
                "persistent_key_present": True,
            }
            status.update(self.status_overrides)
            return 200, status
        if name == "report":
            if not self.executed:
                return 200, self._prior_report()
            return 200, {
                **_identity("report"),
                "boot_nonce": self.boot_nonce,
                "ordinal": 3,
                "action_id": once.base.runner.ACTION_IDS[2],
                "terminal_state": "COMPLETE",
                "result": True,
                "driver_called": True,
                "driver_call_count_for_action": 1,
            }
        if name == "arm":
            assert method == "POST"
            assert headers is not None and "X-EC5-Arm-Nonce" not in headers
            self.armed = True
            return 201, {
                "accepted": True,
                "armed": True,
                "action_id": once.base.runner.ACTION_IDS[2],
                "boot_nonce": self.boot_nonce,
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            assert method == "POST" and self.armed
            assert headers is not None
            assert headers["X-EC5-Arm-Nonce"] == "fedcba9876543210"
            self.executed = True
            return 202, {
                "accepted": True,
                "execute_consumed": True,
                "action_id": once.base.runner.ACTION_IDS[2],
                "boot_nonce": self.boot_nonce,
            }
        raise AssertionError(name)


def test_cumulative_pack_uses_full_controller_streams_for_every_action() -> None:
    report = pack.build_report()
    assert report["contract"]["partial_refresh"] is False
    assert report["contract"]["full_frame_cumulative_redraw"] is True
    assert all(
        item["dtm_transport"] == "PACKED_FULL_FRAME_PER_CONTROLLER"
        for item in report["actions"]
    )
    assert [item["frame"]["histogram"][3] for item in report["actions"]] == [
        0,
        38400,
        38400,
        38400,
        0,
    ]


def test_cumulative_compiled_identity_matches_pack() -> None:
    text = (ROOT / "src" / "ec5_runtime_lut_cumulative_v1_identity.inc").read_text()
    report = pack.build_report()
    assert report["contract_id"] in text
    for action in report["actions"]:
        assert action["descriptor_id"] in text
        assert action["action_id"] in text
        assert action["frame"]["sha256"] in text
        assert action["cs1_dtm"]["sha256"] in text
        assert action["cs2_dtm"]["sha256"] in text
        assert f"0x{action['frame']['fnv1a']:08X}UL" in text


def test_cumulative_driver_never_issues_partial_window_in_selected_branch() -> None:
    text = (ROOT / "src" / "ec5_runtime_lut_cumulative_v1_driver.inc").read_text()
    assert "static constexpr bool fullFrame = true;" in text
    assert "if (!fullFrame && !fullWhite) phWritePartialWindow(*window);" in text
    assert "(fullFrame || fullWhite)" in text
    config = (
        ROOT / "src" / "ec5_runtime_lut_cumulative_v1_main_config.inc"
    ).read_text()
    assert '"command_0x83\\":false' in config
    assert '"full_frame_cumulative_redraw\\":true' in config


def test_cumulative_runner_binding_gate() -> None:
    firmware = (
        ROOT
        / ".pio"
        / "build-runtime-lut-cumulative-v1"
        / "ec5_runtime_lut_cumulative_l535_active_v1"
        / "firmware.bin"
    )
    if once.base.runner.FIRMWARE_SHA256 is None:
        with pytest.raises(SystemExit):
            once.main(["describe"])
        return
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )


def test_cumulative_manifest_rejects_partial_capability() -> None:
    manifest = _manifest()
    once._validate_manifest(manifest)
    manifest["partial_refresh"] = True
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_manifest(manifest)


def test_v5_firmware_resets_before_first_busy_gate_after_safe_pins_low() -> None:
    driver = (ROOT / "src" / "epd_driver.cpp").read_text(encoding="utf-8")
    post_cut = driver[driver.index("bool epdPostDisplayPowerCut()") :]
    assert post_cut.index("epdHoldPanelPinsLow();") < post_cut.index(
        "safeFinishBusyAfter5Ms"
    )
    prepare = driver[driver.index("static bool epdInitResolutionSelected") :]
    assert prepare.index("epdReset();") < prepare.index('epdWaitIdle("reset")')


def test_v5_ordinal3_accepts_late_busy_low_with_valid_prior_safe_finish() -> None:
    fake = CumulativeFakeDevice(busy=0)
    boot_nonce, transcript, report = once._preflight(
        "http://192.0.2.1",
        3,
        expected_busy=1,
        requester=fake,
    )
    assert boot_nonce == fake.boot_nonce
    assert report["ordinal"] == 2
    assert len(transcript) == 4
    assert fake.calls == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]


def test_v5_late_busy_low_rejects_invalid_prior_safe_finish_before_post() -> None:
    fake = CumulativeFakeDevice(busy=0, safe_busy_after_5ms=0)
    with pytest.raises(
        once.base.runner.RecheckError, match="prior safe-finish BUSY differs"
    ):
        once._preflight(
            "http://192.0.2.1",
            3,
            expected_busy=1,
            requester=fake,
        )
    assert len(fake.calls) == 4
    assert all(method == "GET" for method, _ in fake.calls)


@pytest.mark.parametrize(
    ("field", "bad"),
    (("state", "armed"), ("phase", 1), ("rst", 1), ("cs", 1), ("cs2", 1)),
)
def test_v5_late_busy_low_keeps_ready_phase_and_gpio_gates(
    field: str, bad: Any
) -> None:
    fake = CumulativeFakeDevice(busy=0, status_overrides={field: bad})
    with pytest.raises(once.base.runner.RecheckError, match="device ready status"):
        once._preflight(
            "http://192.0.2.1",
            3,
            expected_busy=1,
            requester=fake,
        )
    assert all(method == "GET" for method, _ in fake.calls)


def test_v5_ordinal3_run_with_late_busy_low_posts_once_each(tmp_path: Path) -> None:
    fake = CumulativeFakeDevice(busy=0)
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / f"{once.base.runner.ACTION_IDS[1]}.json").write_text(
        "local prior claim exists\n", encoding="utf-8"
    )
    result = once.base.runner.run_once(
        "http://192.0.2.1",
        3,
        claims=claims,
        output=tmp_path / "ordinal3.json",
        requester=fake,
        poll_seconds=0,
        poll_count=1,
    )
    assert result["outcome"] == "complete_pass"
    assert fake.calls.count(("POST", "arm")) == 1
    assert fake.calls.count(("POST", "execute")) == 1
