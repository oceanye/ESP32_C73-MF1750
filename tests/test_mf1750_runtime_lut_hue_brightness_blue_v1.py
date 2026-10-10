from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_hue_brightness_blue_v1_once as once
from tools import mf1750_runtime_lut_hue_brightness_blue_v1_pack as pack


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
        "history_brightness_screening": True,
        "target_repeat_stability_probe": True,
        "busy_qualified_arm_execute_dispatch": True,
        "local_hold_claimed": False,
    }


def _nvs_contract() -> dict[str, Any]:
    return {
        "namespace": pack.NVS_NAMESPACE,
        "key": pack.NVS_KEY,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 7,
    }


def _baseline() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "RUNTIME_LUT_WHITE_BASELINE",
        "external_anchor_required": False,
        "one_visible_refresh_required": True,
    }


def _history_layout() -> dict[str, Any]:
    active = once.REPORT["contract"]["profiles"]["active"]
    return {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "candidate_cells_per_controller": 64,
        "candidate_cells_total_observations": 128,
        "unique_recipes": 64,
        "duplicate_recipe_across_controllers": True,
        "controller_color_equivalence_claimed": False,
        "cs2_position_mirrored": False,
        "grid_rows": 8,
        "grid_columns_per_controller": 8,
        "grid_x0_local": 20,
        "grid_y0": 40,
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 560,
        "cell_width": 52,
        "cell_height": 58,
        "gap_x": 8,
        "gap_y": 8,
        "row_axis": "commented_middle_code_0_to_7",
        "column_axis": "active_source_code_0_to_7",
        "horizontal_comparison_group": (
            "eight_adjacent_source_histories_same_middle_and_target"
        ),
        "target_hue_id": pack.TARGET_HUE_ID,
        "target_global_header": "active",
        "target_transport_code": 5,
        "target_repeat_count": 2,
        "qualified_brightness_levels": 0,
        "brightness_candidates_only": True,
        "spatial_dither": False,
        "white_gutter_history_interaction_qualified": False,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "all_action_dtm_transport": "packed_frame_per_controller",
        "global_header_sequence": list(pack.GLOBAL_HEADERS),
        "cs1_r20_prefix_bytes": active["cs1_r20_prefix_bytes"],
        "cs1_r20_prefix_sha256": active["cs1_r20_prefix_sha256"],
        "cs2_r20_prefix_bytes": active["cs2_r20_prefix_bytes"],
        "cs2_r20_prefix_sha256": active["cs2_r20_prefix_sha256"],
        "r21_bytes": active["r21_bytes"],
        "r21_sha256": active["r21_sha256"],
        "strict_same_boot_prior_complete_required": True,
        "skip_to_white_recovery_allowed": False,
        "failure_containment_firmware_sha256": (pack.containment.FIRMWARE_BIN_SHA256),
        "failure_containment_contract_id": pack.containment.CONTRACT_ID,
        "failure_containment_nvs_namespace": pack.containment.NVS_NAMESPACE,
        "failure_containment_campaign_nvs_dependency": False,
    }


def _version() -> dict[str, Any]:
    return {
        **_identity("version"),
        "layout_id": pack.VARIANT_KEY,
        "action_count": 6,
        "runtime_lut_write": True,
        "automatic_execute": False,
        "automatic_chaining": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "electrical_parameter_write": False,
        "dither": False,
        "spatial_mixing": False,
        "retry": False,
        "recovery": False,
        "nvs_contract": _nvs_contract(),
        "baseline_contract": _baseline(),
        **_capabilities(),
    }


def _manifest() -> dict[str, Any]:
    return {
        **_identity("manifest"),
        "layout_id": pack.VARIANT_KEY,
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 6,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "history_layout": _history_layout(),
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
        "campaign_complete": ordinal == 6,
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
            "drf_ms": 41_000,
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
            return 200, {
                "version": _version(),
                "manifest": _manifest(),
                "status": self.status(),
                "report": self.report(),
            }[name]
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


def _cell_pair(frame: bytes, controller: int, row: int, column: int) -> int:
    x, y, _, _ = pack._cell_bounds(row, column)  # noqa: SLF001
    global_x = controller * 512 + x
    return frame[y * (1024 // 2) + global_x // 2]


def test_pack_freezes_64_unique_recipes_and_128_repeat_observations() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert report["contract_id"] == (
        "3d5dee5165a86ec470205bcd970c4d76fceb68599d4a54cc1aea882dae2bfee7"
    )
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert contract["geometry"]["unique_recipes"] == 64
    assert contract["geometry"]["candidate_cells_total_observations"] == 128
    assert contract["geometry"]["controller_color_equivalence_claimed"] is False
    assert contract["brightness_candidates_only"] is True
    assert contract["qualified_brightness_levels"] == 0
    assert contract["spatial_dither"] is False
    assert len(contract["recipes"]) == 64
    assert all(len(recipe["controller_repeats"]) == 2 for recipe in contract["recipes"])


def test_horizontal_groups_are_source_0_to_7_and_cells_are_uniform() -> None:
    source = pack._grid_frame("source")  # noqa: SLF001
    middle = pack._grid_frame("middle")  # noqa: SLF001
    target = pack._grid_frame("target")  # noqa: SLF001
    for controller in (0, 1):
        for row in range(8):
            assert [
                _cell_pair(source, controller, row, column) for column in range(8)
            ] == [(code << 4) | code for code in range(8)]
            assert [
                _cell_pair(middle, controller, row, column) for column in range(8)
            ] == [(row << 4) | row] * 8
            assert [
                _cell_pair(target, controller, row, column) for column in range(8)
            ] == [0x55] * 8


def test_white_gutters_are_separators_not_candidate_measurement_pixels() -> None:
    for stage in ("source", "middle", "target"):
        frame = pack._grid_frame(stage)  # noqa: SLF001
        row_bytes = 512
        # First horizontal and vertical gutters in both controller-local grids.
        for controller in (0, 1):
            gx = controller * 512 + pack.GRID_X0 + pack.CELL_WIDTH
            gy = pack.GRID_Y0 + pack.CELL_HEIGHT
            assert frame[pack.GRID_Y0 * row_bytes + gx // 2] == 0x77
            assert (
                frame[gy * row_bytes + (controller * 512 + pack.GRID_X0) // 2] == 0x77
            )


def test_role_identity_count_is_four_but_campaign_has_six_ordinals() -> None:
    identity = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_blue_v1_identity.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_blue_v1_main_config.inc"
    ).read_text(encoding="utf-8")
    assert "kRoleIdentityCount = 4" in identity
    assert "kActionCount = 4" not in identity
    assert pack.build_report()["contract_id"] in identity
    assert config.count("EpdChromaGridRole::White") == 2
    assert config.count("EpdChromaGridRole::Target") == 2


def test_firmware_has_raw_busy_gates_at_arm_execute_and_dispatch() -> None:
    source = (ROOT / "src/ec5_runtime_lut_cross_palette_v1_main.cpp").read_text(
        encoding="utf-8"
    )
    assert source.count("MF1750_RUNTIME_LUT_HUE_BRIGHTNESS_BLUE_V1_BUILD") >= 4
    assert source.count("epdReadBusy() != 1") >= 3
    for error in (
        "arm_busy_not_idle_high",
        "execute_busy_not_idle_high",
        "dispatch_busy_not_idle_high",
    ):
        assert error in source


def test_runner_binding_matches_clean_build_and_compiled_action_ids() -> None:
    firmware = once.BUILD_DIR / "firmware.bin"
    elf = once.BUILD_DIR / "firmware.elf"
    assert firmware.stat().st_size == once.FIRMWARE_BYTES
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == once.FIRMWARE_SHA256
    assert elf.stat().st_size == once.ELF_BYTES
    assert hashlib.sha256(elf.read_bytes()).hexdigest() == once.ELF_SHA256
    binary = firmware.read_bytes()
    for item in pack.build_report()["actions"]:
        assert item["descriptor_id"].encode("ascii") in binary
        assert item["action_id"].encode("ascii") in binary


def test_describe_has_candidate_and_containment_boundaries() -> None:
    value = once.describe()
    assert value["fixed_transport"]["candidate_recipes"] == 64
    assert value["fixed_transport"]["physical_observations"] == 128
    assert value["fixed_transport"]["qualified_brightness_levels"] == 0
    assert value["evidence_boundary"]["brightness_candidates_not_levels"] is True
    assert value["ordinal_progression"]["skip_to_runtime_white_recovery"] is False
    containment = value["ordinal_progression"]["visual_fail_containment"]
    assert containment["kind"] == "independent_fresh_identity_factory_otp_white"
    assert containment["campaign_nvs_dependency"] is False
    assert containment["campaign_id"] == pack.containment.CAMPAIGN_ID
    assert containment["nvs_namespace"] == pack.containment.NVS_NAMESPACE
    assert containment["nvs_key"] == pack.containment.NVS_KEY
    assert containment["action_id"] == pack.containment.ACTION_ID
    assert containment["firmware_sha256"] == pack.containment.FIRMWARE_BIN_SHA256
    assert containment["artifact_binding_status"]["firmware_bin"]["verified"] is True
    assert containment["artifact_binding_status"]["firmware_elf"]["verified"] is True


def test_missing_local_artifact_refuses_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDevice(1)
    monkeypatch.setattr(once, "BUILD_DIR", tmp_path)
    with pytest.raises(once.base.runner.RecheckError, match="artifact is missing"):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
        )
    assert fake.calls == []


@pytest.mark.parametrize("ordinal", (1, 2, 3, 4, 5, 6))
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


def test_ordinal6_cannot_skip_failed_or_unaccepted_target_repeat() -> None:
    fake = FakeDevice(6)
    fake.report = lambda: _complete_report(4, fake.boot_nonce)  # type: ignore[method-assign]
    with pytest.raises(once.base.runner.RecheckError, match="differs"):
        once._preflight(  # noqa: SLF001
            "http://192.0.2.1", 6, expected_busy=1, requester=fake
        )


@pytest.mark.parametrize("ordinal", (1, 2, 3, 4, 5, 6))
def test_strict_complete_accepts_all_six_exact_actions(ordinal: int) -> None:
    once.v3._validate_complete_report(  # noqa: SLF001
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
    report = _complete_report(4, "0123456789abcdef")
    report["driver"][key] = bad
    with pytest.raises(once.base.runner.RecheckError):
        once.v3._validate_complete_report(  # noqa: SLF001
            report, 4, "0123456789abcdef"
        )


def test_exact_action_run_promotes_one_arm_and_execute_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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


def test_device_cannot_claim_qualified_brightness_levels() -> None:
    manifest = _manifest()
    manifest["history_layout"]["qualified_brightness_levels"] = 1
    with pytest.raises(once.base.runner.RecheckError, match="qualified"):
        once._validate_manifest(manifest)  # noqa: SLF001
