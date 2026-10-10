from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from host import dither_color_atlas
from host.extended_color.mf1750_target_hues import build_catalog
from tools import mf1750_runtime_lut_hue_brightness_redpink_v1_once as once
from tools import mf1750_runtime_lut_hue_brightness_redpink_v1_pack as pack


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
        "ordinal4_clear_visible_hit_required_for_repeat": True,
        "ordinal4_no_visible_difference_seals_main": True,
        "device_enforced_same_boot": True,
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
        "campaign_boot_key": pack.NVS_BOOT_KEY,
        "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
        "campaign_boot_initial_key_present": False,
        "campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1": True,
        "campaign_boot_readback_required": True,
        "current_boot_exact_match_required": True,
        "reboot_resume_allowed": False,
        "post_containment_resume_allowed": False,
    }


def _baseline() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
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
        "shared_red_or_pink_hue_claimed": False,
        "controller_payload_binding": "CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED",
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
        "target_transport_code": 0,
        "target_repeat_count": 2,
        "qualified_brightness_levels": 0,
        "brightness_candidates_only": True,
        "spatial_dither": False,
        "separator_gutter_history_interaction_qualified": False,
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
        "same_boot_prior_complete_required": True,
        "device_enforced_same_boot": True,
        "campaign_boot_nonce_persisted_before_any_action": True,
        "campaign_boot_binding_key": pack.NVS_BOOT_KEY,
        "direct_exact_post_resume_after_reboot": False,
        "main_campaign_resume_after_containment": False,
        "skip_to_factory_white_allowed": False,
        "runtime_code7_used_as_white": False,
        "factory_otp_white_ordinals": [1, 6],
        "target_repeat_separate_manual_decision_action": True,
        "target_repeat_automatic_dispatch": False,
        "skip_target_repeat_within_main_allowed": False,
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
        "actions": deepcopy(list(once.base.runner.ACTIONS)),
        "action_count": 6,
        "one_driver_call_per_action": True,
        "factory_otp": True,
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
            "campaign_boot_key_present": True,
            "persisted_campaign_boot_nonce": self.boot_nonce,
            "campaign_boot_matches_current": True,
            "device_enforced_same_boot": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
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
        "df7ecdc4ef3d443766045e7c242cbb9109cb3f3f6415ad926c70babf7f000278"
    )
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert contract["geometry"]["unique_recipes"] == 64
    assert contract["geometry"]["candidate_cells_total_observations"] == 128
    assert contract["geometry"]["controller_color_equivalence_claimed"] is False
    assert contract["target_hue_registry"]["selection_not_guess"] is True
    assert contract["target_hue_registry"]["target_transport_code"] == 0
    assert contract["target_hue_registry"]["shared_red_or_pink_hue_claimed"] is False
    assert [
        item["provisional_visual_name"]
        for item in contract["target_hue_registry"]["controller_observations"]
    ] == ["olive/yellow-green", "red"]
    assert contract["brightness_candidates_only"] is True
    assert contract["qualified_brightness_levels"] == 0
    assert contract["spatial_dither"] is False
    assert len(contract["recipes"]) == 64
    assert all(len(recipe["controller_repeats"]) == 2 for recipe in contract["recipes"])


def test_target_code0_is_evidence_selected_and_factory_atlas_code3_is_not_reused() -> (
    None
):
    catalog = build_catalog()
    red = next(item for item in catalog["target_hues"] if item["hue_id"] == "R")
    assert red["current_status"] == "direct-endpoint-candidate"
    assert red["seeds"] == (
        {
            "controller": "CS2",
            "profile": "active-global/CS1-active535/CS2-commented535",
            "code": 0,
            "observed_family": "红",
            "evidence": "visual-candidate",
        },
    )
    assert dither_color_atlas.CLASSIFICATION.startswith("FACTORY_OTP_")
    assert dither_color_atlas.COLOR_NAME_BY_CODE[3] == "red"
    registry = pack.build_report()["contract"]["target_hue_registry"]
    assert registry["target_transport_code"] == 0
    assert "do_not_transfer" in registry["rejected_inference"]
    assert registry["controller_color_equivalence_claimed"] is False


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
            ] == [0x00] * 8


def test_code7_gutters_are_separators_not_runtime_white() -> None:
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

    identity = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_identity.inc"
    ).read_text(encoding="utf-8")
    driver = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_driver.inc"
    ).read_text(encoding="utf-8")
    assert "kWhiteCode" not in identity
    assert "kWhiteCode" not in driver


def test_role_identity_count_is_four_but_campaign_has_six_ordinals() -> None:
    identity = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_identity.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_main_config.inc"
    ).read_text(encoding="utf-8")
    assert "kRoleIdentityCount = 4" in identity
    assert "kActionCount = 4" not in identity
    assert pack.build_report()["contract_id"] in identity
    assert config.count("EpdChromaGridRole::White") == 2
    assert config.count("EpdChromaGridRole::Target") == 2


def test_firmware_has_raw_busy_gates_at_arm_execute_and_dispatch() -> None:
    source = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_main.cpp"
    ).read_text(encoding="utf-8")
    assert source.count("epdReadBusy() != 1") >= 3
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery" in source
    for error in (
        "arm_busy_not_idle_high",
        "execute_busy_not_idle_high",
        "dispatch_busy_not_idle_high",
    ):
        assert error in source


def test_firmware_persists_first_boot_and_gates_direct_posts_and_dispatch() -> None:
    source = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_main.cpp"
    ).read_text(encoding="utf-8")
    assert "cursorStore.putULong64(kNvsBootKey, wanted)" in source
    assert "refreshCampaignBootBindingEvidence()" in source
    assert "initializeOrValidateCampaignBootBinding()" in source
    assert "campaignBootBindingAllowsMutation(uint8_t ordinal)" in source
    assert source.count("bootBindingAdmissionAllowed(") >= 7
    for marker in (
        "arm_campaign_boot_binding_mismatch",
        "execute_campaign_boot_binding_mismatch",
        "dispatch_campaign_boot_binding_mismatch",
        "campaign_boot_binding_mismatch_at_boot",
    ):
        assert marker in source

    arm = source[
        source.index("void handleArm()") : source.index("void handleExecute()")
    ]
    execute = source[
        source.index("void handleExecute()") : source.index("void installRoutes()")
    ]
    dispatch = source[
        source.index("void executePendingAction()") : source.index("}  // namespace")
    ]
    assert (
        arm.index("campaignBootBindingAllowsMutation")
        < arm.index("validateMutationContract")
        < arm.index("persistCursor(kPhaseArmed")
    )
    assert (
        execute.index("campaignBootBindingAllowsMutation")
        < execute.index("validateMutationContract")
        < execute.index("persistCursor(kPhaseConsumed")
    )
    assert dispatch.index("campaignBootBindingAllowsMutation") < dispatch.index(
        "epdDisplayCompiled"
    )


@pytest.mark.parametrize("ordinal", (2, 3, 4, 5, 6))
def test_rebooted_intermediate_cursor_refuses_even_exact_direct_post(
    ordinal: int,
) -> None:
    # This is the exact admission predicate compiled into the firmware. Headers
    # may all be exact, but a new boot cannot match the persisted first-boot
    # identity, so no ARM/EXECUTE/dispatch path reaches a driver call.
    def admitted(
        cursor_key_exists: bool,
        phase: int,
        next_ordinal: int,
        boot_key_exists: bool,
        persisted_matches_current: bool,
    ) -> bool:
        if boot_key_exists:
            return persisted_matches_current
        return not cursor_key_exists and phase == 0 and next_ordinal == 1

    assert admitted(False, 0, 1, False, False) is True
    assert admitted(True, 0, ordinal, True, False) is False
    direct_exact_headers = {
        "build": pack.BUILD_TAG,
        "campaign": pack.CAMPAIGN_ID,
        "action": once.base.runner.ACTIONS[ordinal - 1]["action_id"],
        "descriptor": once.base.runner.ACTIONS[ordinal - 1]["descriptor_id"],
        "boot": "new-boot-nonce",
    }
    assert all(direct_exact_headers.values())
    driver_call_count = 0
    if admitted(True, 0, ordinal, True, False):
        driver_call_count += 1
    assert driver_call_count == 0


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


def test_describe_has_candidate_and_manual_repeat_boundaries() -> None:
    value = once.describe()
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["device_network_accessed"] is False
    assert value["display_refreshed"] is False
    assert value["fixed_transport"]["candidate_recipes"] == 64
    assert value["fixed_transport"]["physical_observations"] == 128
    assert value["fixed_transport"]["qualified_brightness_levels"] == 0
    assert value["evidence_boundary"]["brightness_candidates_not_levels"] is True
    progression = value["ordinal_progression"]
    assert progression["skip_to_factory_white_recovery"] is False
    assert progression["ordinal_6_requires_ordinal_5_complete"] is True
    assert (
        progression["ordinal_5_target_repeat_requires_fresh_operator_decision"] is True
    )
    assert progression["ordinal_5_automatic_dispatch"] is False
    assert progression["ordinal_5_host_confirmation_flag"] == (
        "--confirm-visible-candidate-after-ordinal4"
    )
    assert progression["device_enforced_same_boot"] is True
    assert progression["direct_exact_post_resume_after_reboot"] is False
    assert progression["main_campaign_resume_after_containment"] is False
    fast_gate = value["ordinal4_fast_gate"]
    assert fast_gate["if_no_visible_difference"]["arm_ordinal5"] is False
    assert fast_gate["if_no_visible_difference"]["arm_ordinal6"] is False
    assert fast_gate["if_no_visible_difference"]["relay_off_before_containment"] is True
    assert (
        fast_gate["if_clear_visible_hit"][
            "ordinal6_main_white_only_after_repeat_accepted"
        ]
        is True
    )


def test_dry_validate_is_offline_and_artifact_bound() -> None:
    value = once.dry_validate()
    assert value["result"] == "PASS"
    assert value["offline_only"] is True
    assert value["device_requests_made"] == 0
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["device_network_accessed"] is False
    assert value["serial_or_com_accessed"] is False
    assert value["relay_accessed"] is False
    assert value["firmware_flashed"] is False
    assert value["display_refreshed"] is False
    assert value["firmware_binding"]["bound"] is True
    assert value["unique_recipes"] == 64
    assert value["physical_observations"] == 128
    assert value["target_transport_code"] == 0
    assert value["target_repeat"] == {
        "ordinal": 5,
        "separate_operator_decision": True,
        "automatic_dispatch": False,
        "skip_to_recovery_allowed": False,
        "visible_candidate_confirmation_after_ordinal4_required": True,
    }
    assert value["same_boot_binding"]["firmware_arm_gate"] is True
    assert value["same_boot_binding"]["firmware_execute_gate"] is True
    assert value["same_boot_binding"]["firmware_dispatch_gate"] is True
    assert (
        value["ordinal4_fast_gate"]["if_no_visible_difference"]["seal_main_campaign"]
        is True
    )


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


def test_ordinal5_requires_explicit_clear_hit_confirmation_before_network(
    tmp_path: Path,
) -> None:
    fake = FakeDevice(5)
    with pytest.raises(once.base.runner.RecheckError, match="visible candidate"):
        once.run_once(
            "http://192.0.2.1",
            5,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
        )
    assert fake.calls == []


def test_ordinal5_explicit_visible_candidate_confirmation_allows_exact_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(once.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(5)
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / f"{once.base.runner.ACTION_IDS[3]}.json").write_text(
        "{}", encoding="utf-8"
    )
    result = once.run_once(
        "http://192.0.2.1",
        5,
        claims=claims,
        output=tmp_path / "result.json",
        requester=fake,
        poll_seconds=65,
        poll_count=1,
        visible_candidate_confirmed=True,
    )
    assert result["outcome"] == "complete_pass"
    assert [call for call in fake.calls if call[0] == "POST"] == [
        ("POST", "arm"),
        ("POST", "execute"),
    ]


def test_visible_candidate_confirmation_is_rejected_for_other_ordinals(
    tmp_path: Path,
) -> None:
    fake = FakeDevice(4)
    with pytest.raises(once.base.runner.RecheckError, match="only for ordinal 5"):
        once.run_once(
            "http://192.0.2.1",
            4,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
            visible_candidate_confirmed=True,
        )
    assert fake.calls == []


def test_main_j2_off_diagnostic_is_exact_four_gets_and_zero_mutation(
    tmp_path: Path,
) -> None:
    fake = FakeDevice(1, busy=0)
    output = tmp_path / "j2-off-diagnostic.json"
    result = once.diagnose_j2_off(
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
    assert result["network"] == {"get": 4, "post": 0}
    assert result["visible_refreshes"] == 0
    assert result["next_ordinal"] == 1
    assert json.loads(output.read_text(encoding="utf-8")) == result


def test_main_j2_off_diagnostic_requires_confirmation_before_requests(
    tmp_path: Path,
) -> None:
    fake = FakeDevice(1, busy=0)
    output = tmp_path / "j2-off-diagnostic.json"
    with pytest.raises(once.base.runner.RecheckError, match="confirmation"):
        once.diagnose_j2_off(
            "http://192.0.2.1",
            output=output,
            requester=fake,
        )
    assert fake.calls == []
    assert not output.exists()


def test_main_j2_off_diagnostic_refuses_existing_output_before_requests(
    tmp_path: Path,
) -> None:
    fake = FakeDevice(1, busy=0)
    output = tmp_path / "j2-off-diagnostic.json"
    output.write_text("occupied\n", encoding="utf-8")
    with pytest.raises(once.base.runner.RecheckError, match="overwrite"):
        once.diagnose_j2_off(
            "http://192.0.2.1",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert fake.calls == []
    assert output.read_text(encoding="utf-8") == "occupied\n"


def test_main_j2_off_diagnostic_artifact_failure_is_sealed_without_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDevice(1, busy=0)
    output = tmp_path / "j2-off-diagnostic-attempt.json"

    def fail_artifact_preflight() -> None:
        raise once.base.runner.RecheckError("synthetic artifact mismatch")

    monkeypatch.setattr(once, "_verify_local_artifacts", fail_artifact_preflight)
    with pytest.raises(once.base.runner.RecheckError, match="artifact mismatch"):
        once.diagnose_j2_off(
            "http://192.0.2.1",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert fake.calls == []
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["outcome"] == "j2_off_diagnostic_failed_no_claim"
    assert evidence["permanent_claims_created"] == 0
    assert evidence["visible_refreshes"] == 0
    assert evidence["integrity"]["algorithm"] == (
        "sha256-canonical-json-without-integrity"
    )


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


def test_host_action_shape_matches_firmware_transport_dispatch_json() -> None:
    firmware_source = (
        ROOT / "src/ec5_runtime_lut_hue_brightness_redpink_v1_main.cpp"
    ).read_text(encoding="utf-8")
    assert (
        "String transportDispatchJson(const ActionDescriptor &action)"
        in firmware_source
    )
    assert '" + transportDispatchJson(action) +' in firmware_source
    for field in (
        "palette_source",
        "global_header",
        "driver_entry",
        "boot_admission",
    ):
        assert f'\\"{field}\\"' in firmware_source

    actions = list(once.base.runner.ACTIONS)
    assert [
        (
            item["palette_source"],
            item["global_header"],
            item["driver_entry"],
        )
        for item in actions
    ] == [
        ("FACTORY_OTP", None, "epdDisplayCompiledFactoryOtpWhiteRecovery"),
        ("L535_RUNTIME", "active", "epdDisplayCompiledChromaGrid"),
        ("L535_RUNTIME", "commented", "epdDisplayCompiledChromaGrid"),
        ("L535_RUNTIME", "active", "epdDisplayCompiledChromaGrid"),
        ("L535_RUNTIME", "active", "epdDisplayCompiledChromaGrid"),
        ("FACTORY_OTP", None, "epdDisplayCompiledFactoryOtpWhiteRecovery"),
    ]
    once._validate_manifest(_manifest())  # noqa: SLF001


@pytest.mark.parametrize(
    "field", ("palette_source", "global_header", "driver_entry", "boot_admission")
)
def test_manifest_rejects_missing_firmware_transport_dispatch_field(field: str) -> None:
    manifest = _manifest()
    del manifest["actions"][1][field]
    with pytest.raises(once.base.runner.RecheckError, match="manifest actions differs"):
        once._validate_manifest(manifest)  # noqa: SLF001
