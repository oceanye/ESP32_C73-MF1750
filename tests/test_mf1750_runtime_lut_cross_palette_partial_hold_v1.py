from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_cross_palette_partial_hold_v1_once as once
from tools import mf1750_runtime_lut_cross_palette_partial_hold_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = (
    ROOT
    / ".pio"
    / "build-runtime-lut-cross-palette-partial-hold-v1"
    / "ec5_runtime_lut_cross_palette_partial_hold_v1"
)

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
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "factory_otp_white_actions": True,
        "same_palette_hold_probe": False,
        "cross_palette_hold_probe": True,
        "busy_qualified_arm_execute_dispatch": True,
    }


def _baseline() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "external_anchor_required": False,
        "anchor_established_by_firmware": True,
        "one_visible_refresh_required": True,
        "runtime_code7_action_reachable": False,
        "factory_otp_recovery_ordinal": 5,
    }


def _version() -> dict[str, Any]:
    runner = once.base.runner
    return {
        **_identity("version"),
        "layout_id": pack.VARIANT_KEY,
        "profile_source": once._PROFILE_SOURCE,  # noqa: SLF001
        "action_count": 5,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
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
            "terminal_next_ordinal": 6,
        },
        "baseline_contract": _baseline(),
        **_capabilities(),
    }


def _manifest() -> dict[str, Any]:
    return {
        **_identity("manifest"),
        "layout_id": pack.VARIANT_KEY,
        "profile_source": once._PROFILE_SOURCE,  # noqa: SLF001
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "baseline_contract": _baseline(),
        "history_layout": {
            "factory_otp_anchor_ordinal": 1,
            "factory_otp_recovery_ordinal": 5,
            "factory_otp_white_frame_fill_byte": 0x11,
            "factory_otp_white_frame_bytes": 307_200,
            "anchor_established_by_firmware": True,
            "external_factory_white_anchor_required": False,
            "runtime_code7_action_reachable": False,
            "runtime_transport_codes": [5, 6, 3],
            "ptlw_command": 0x83,
            "ptlw_payload_bytes": 9,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "ptlw_mode": 1,
            "ptlw_writes_per_controller": 2,
            "initial_ptlw_before_cropped_dtm": True,
            "repeat_ptlw_after_pon_busy": True,
            "pre_pon_cdi_ff_preserved": True,
            "post_pon_sequence": [
                "PTLW_CS1",
                "PTLW_CS2",
                "CDI_FF_BOTH",
                "BTST2",
                "DRF",
            ],
            "pon_timeout_ms": 60_000,
            "cropped_dtm": True,
            "packed_bpp": 4,
            "windows_disjoint": True,
            "cs2_position_mirrored": False,
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "global_header_profile_sequence": [
                None,
                "active",
                "commented",
                "active",
                None,
            ],
            "global_header_switching": True,
            "sequential_hold_observation_required": True,
            "camera_required": False,
            "busy_idle_level_required": 1,
            "busy_zero_accepted": False,
            **{
                key: once.REPORT["contract"]["profiles"]["active"][key]
                for key in (
                    "cs1_r20_prefix_bytes",
                    "cs1_r20_prefix_sha256",
                    "cs2_r20_prefix_bytes",
                    "cs2_r20_prefix_sha256",
                    "r21_bytes",
                    "r21_sha256",
                )
            },
        },
        **_capabilities(),
    }


def _fresh_report(boot_nonce: str) -> dict[str, Any]:
    return {
        **_identity("report"),
        "boot_nonce": boot_nonce,
        "valid": False,
        "ordinal": None,
        "descriptor_id": None,
        "action_id": None,
        "terminal_state": "NOT_EXECUTED",
        "result": False,
        "error": "no_execute_report",
        "driver_called": False,
        "driver_call_count_for_action": 0,
        "total_driver_call_count": 0,
        "phase": 0,
        "next_ordinal": 1,
        "no_retry": True,
        "no_recovery": True,
    }


def _complete_report(ordinal: int, boot_nonce: str) -> dict[str, Any]:
    action = once.base.runner.ACTIONS[ordinal - 1]
    source = once.REPORT["actions"][ordinal - 1]
    return {
        **_identity("report"),
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "ordinal": ordinal,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == 5,
        "no_retry": True,
        "no_recovery": True,
        "driver": {
            "operation_id": ordinal,
            "valid": True,
            "running": False,
            "sequence_ok": True,
            "wait_timeout": False,
            "busy_assertion_missing": False,
            "pre_command_idle_failure": False,
            "failure_stage": "none",
            "timeout_stage": "none",
            "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
            "spi_hz": 1_000_000,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "pon_ms": 260,
            "drf_ms": 33_930,
            "pof_ms": 150,
            "input_fnv1a": source["frame"]["fnv1a"],
            "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
            "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        },
    }


class FakeDevice:
    def __init__(self, ordinal: int, *, busy: int = 1) -> None:
        self.ordinal = ordinal
        self.busy = busy
        self.boot_nonce = "0123456789abcdef"
        self.executed = False
        self.calls: list[tuple[str, str]] = []

    def status(self) -> dict[str, Any]:
        return {
            **_identity("status"),
            "boot_nonce": self.boot_nonce,
            "state": "ready",
            "phase": 0,
            "phase_name": "READY",
            "cursor_raw": self.ordinal,
            "next_ordinal": self.ordinal,
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
            "persistent_key_present": self.ordinal != 1,
            "arm_request_count": self.ordinal - 1,
            "execute_request_count": self.ordinal - 1,
            "total_driver_call_count": self.ordinal - 1,
        }

    def report(self) -> dict[str, Any]:
        if self.executed:
            return _complete_report(self.ordinal, self.boot_nonce)
        if self.ordinal == 1:
            return _fresh_report(self.boot_nonce)
        return _complete_report(self.ordinal - 1, self.boot_nonce)

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
        if method == "GET":
            assert headers is None
            values = {
                "version": _version(),
                "manifest": _manifest(),
                "status": self.status(),
                "report": self.report(),
            }
            return 200, values[name]
        assert method == "POST" and headers is not None
        action = once.base.runner.ACTIONS[self.ordinal - 1]
        if name == "arm":
            return 200, {
                "accepted": True,
                "armed": True,
                "action_id": action["action_id"],
                "boot_nonce": self.boot_nonce,
                "arm_nonce": "fedcba9876543210",
            }
        if name == "execute":
            self.executed = True
            return 200, {
                "accepted": True,
                "execute_consumed": True,
                "action_id": action["action_id"],
                "boot_nonce": self.boot_nonce,
            }
        raise AssertionError(name)


def test_pack_freezes_cross_palette_local_hold_sequence() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert report["contract_id"] == (
        "81ee6e25c412e59d096f40554aaeb252e8e83f21b0060708afee11de5404a3d5"
    )
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert [item["global_header"] for item in report["actions"]] == [
        None,
        "active",
        "commented",
        "active",
        None,
    ]
    assert [
        item["window"]["cs1_code"]
        for item in report["actions"][1:4]
    ] == [5, 6, 3]
    assert contract["cross_palette_hold_probe"] is True
    assert contract["partial_refresh"] is True
    assert contract["spatial_dither"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False
    assert contract["busy_qualification"]["busy_zero_accepted"] is False


def test_cumulative_model_and_cropped_transport_identities_are_distinct() -> None:
    actions = pack.build_report()["actions"]
    assert len({item["frame"]["sha256"] for item in actions[1:4]}) == 3
    assert [item["cs1_dtm"]["bytes"] for item in actions[1:4]] == [9600] * 3
    assert all(
        item["cs1_dtm"] == item["cs2_dtm"] for item in actions[1:4]
    )
    assert all(item["ptlw_writes_per_controller"] == 2 for item in actions[1:4])
    assert actions[0]["window"] is None and actions[4]["window"] is None


def test_describe_is_bound_and_exposes_strict_busy_contract() -> None:
    value = once.describe()
    assert value["firmware_binding"] == {
        "bound": True,
        "bytes": 797_152,
        "sha256": (
            "7f5870b065b72d865a42bb90887a160940ccfd572576f2fc6c12d652943cd79e"
        ),
    }
    assert value["device_access_fail_closed_until_firmware_bound"] is True
    assert value["preflight_busy_contract"] == {
        "ordinals_1_to_5": "RAW_READY_BUSY_1_ONLY",
        "busy_zero_accepted": False,
        "firmware_gates": ["ARM", "EXECUTE", "DISPATCH"],
    }
    assert value["fixed_transport"]["profile_sequence"] == [
        None,
        "active",
        "commented",
        "active",
        None,
    ]
    assert value["ordinal_progression"] == {
        "strict_same_boot_prior_complete_required": True,
        "skip_to_factory_white_recovery": False,
        "ordinal_5_requires_ordinal_4_complete": True,
        "fault_containment_requires_separate_fresh_firmware": True,
    }


def test_runner_binding_matches_clean_build_and_compiled_identities() -> None:
    firmware = BUILD_DIR / "firmware.bin"
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES == 797_152
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )
    binary = firmware.read_bytes()
    for item in pack.build_report()["actions"]:
        assert item["descriptor_id"].encode("ascii") in binary
        assert item["action_id"].encode("ascii") in binary


def test_cross_fixture_role_table_excludes_white_regression() -> None:
    source = (
        ROOT / "src/ec5_runtime_lut_cross_palette_partial_hold_v1_driver.inc"
    ).read_text(encoding="utf-8")
    table_start = source.index("static constexpr EpdChromaGridRole kRoles[]")
    table_end = source.index("};", table_start)
    table = source[table_start:table_end]
    assert "!defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)" in table
    assert table.count("EpdChromaGridRole::White") == 1
    assert table.count("EpdChromaGridRole::Source") == 1
    assert table.count("EpdChromaGridRole::Mid") == 1
    assert table.count("EpdChromaGridRole::Target") == 1
    lines = table.splitlines()
    cross_line = next(
        index
        for index, line in enumerate(lines)
        if "!defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)"
        in line
    )
    assert lines[cross_line - 1].rstrip().endswith("&& \\")
    assert source.index(
        "!defined(MF1750_RUNTIME_LUT_CROSS_PALETTE_PARTIAL_HOLD_V1_BUILD)",
        table_start,
        table_end,
    ) < source.index("EpdChromaGridRole::White", table_start, table_end)


def test_malformed_firmware_binding_refuses_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDevice(1)
    monkeypatch.setattr(once.base.runner, "FIRMWARE_SHA256", None)
    with pytest.raises(once.base.runner.RecheckError, match="not bound"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
        )
    assert fake.calls == []


@pytest.mark.parametrize("ordinal", (1, 2, 3, 4, 5))
def test_every_ordinal_requires_raw_ready_busy_high(ordinal: int) -> None:
    high = FakeDevice(ordinal, busy=1)
    boot_nonce, transcript, _ = once._preflight(  # noqa: SLF001
        "http://192.0.2.1", ordinal, expected_busy=1, requester=high
    )
    assert boot_nonce == high.boot_nonce
    assert len(transcript) == 4
    low = FakeDevice(ordinal, busy=0)
    with pytest.raises(once.base.runner.RecheckError, match="BUSY=1"):
        once._preflight(  # noqa: SLF001
            "http://192.0.2.1", ordinal, expected_busy=1, requester=low
        )


def test_recovery_ordinal_cannot_skip_failed_or_incomplete_ordinal4() -> None:
    fake = FakeDevice(5)
    fake.report = lambda: _complete_report(3, fake.boot_nonce)  # type: ignore[method-assign]
    with pytest.raises(once.base.runner.RecheckError, match="differs"):
        once._preflight(  # noqa: SLF001
            "http://192.0.2.1", 5, expected_busy=1, requester=fake
        )


@pytest.mark.parametrize("ordinal", (1, 2, 3, 4, 5))
def test_strict_complete_accepts_all_five_exact_actions(ordinal: int) -> None:
    once._validate_complete_report(  # noqa: SLF001
        _complete_report(ordinal, "0123456789abcdef"),
        ordinal,
        "0123456789abcdef",
    )


@pytest.mark.parametrize(
    ("key", "bad"),
    (
        ("sequence_ok", False),
        ("wait_timeout", True),
        ("pon_busy_seen", False),
        ("drf_busy_seen", False),
        ("pof_busy_seen", False),
        ("input_fnv1a", 0),
        ("cs1_dtm_fnv1a", 0),
        ("cs2_dtm_fnv1a", 0),
    ),
)
def test_strict_complete_rejects_corrupt_driver_evidence(key: str, bad: Any) -> None:
    report = _complete_report(3, "0123456789abcdef")
    report["driver"][key] = bad
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_complete_report(  # noqa: SLF001
            report, 3, "0123456789abcdef"
        )


def test_exact_action_run_promotes_staging_and_never_autochains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.base.runner, "FIRMWARE_SHA256", "a" * 64)
    monkeypatch.setattr(once.base.runner, "FIRMWARE_BYTES", 1)
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1)
    output = tmp_path / "pass.json"
    result = once.run_once(
        "http://192.0.2.1",
        1,
        claims=tmp_path / "claims",
        output=output,
        requester=fake,
        poll_seconds=65,
        poll_count=1,
    )
    assert result["outcome"] == "complete_pass"
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["outcome"] == "complete_pass"
    assert [call for call in fake.calls if call[0] == "POST"] == [
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    assert not output.with_name(
        f".{output.name}.cross-hold-v1-terminal-staging"
    ).exists()
