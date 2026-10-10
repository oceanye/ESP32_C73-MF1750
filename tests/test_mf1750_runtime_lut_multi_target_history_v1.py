from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_runtime_lut_multi_target_history_v1_pack as pack
from tools import mf1750_runtime_lut_multi_target_history_v1_runner as runner


ROOT = Path(__file__).resolve().parents[1]


def _identity(kind: str) -> dict[str, Any]:
    host = runner.base.runner
    return {
        "kind": f"{host.DEVICE_KIND_PREFIX}-{kind}",
        "build_tag": host.BUILD_TAG,
        "test_id": host.TEST_ID,
        "campaign_id": host.CAMPAIGN_ID,
        "device_api_version": host.DEVICE_API_VERSION,
        "identity_revision": host.IDENTITY_REVISION,
        "contract_id": host.CONTRACT_ID,
        "classification": host.CLASSIFICATION,
    }


def _capabilities() -> dict[str, Any]:
    return {
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "unknown_commands": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "same_palette_hold_probe": False,
        "cross_palette_hold_probe": False,
        "local_hold_claimed": False,
        "multi_target_history_screening": True,
        "target_repeat_stability_probe": True,
        "brightness_candidates_only": True,
        "qualified_colours": 0,
        "human_observation_gate_after_every_action": True,
        "busy_qualified_arm_execute_dispatch": True,
        "independent_failure_containment_bound": True,
        "runtime_code7_used_as_white": False,
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
        "terminal_next_ordinal": 10,
    }


def _baseline() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_HEALTH_ANCHOR",
        "external_anchor_required": False,
        "one_visible_refresh_required": True,
    }


def _history_layout() -> dict[str, Any]:
    active = runner.REPORT["contract"]["profiles"]["active"]
    return {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 8,
        "grid_columns_per_controller": 8,
        "cells_per_controller_per_direction": 64,
        "directional_recipes": 128,
        "total_controller_observations": 256,
        "duplicate_recipe_across_controllers": True,
        "controller_color_equivalence_claimed": False,
        "paired_controller_observations_not_waveform_identical": True,
        "controller_payload_binding": ("CS1_ACTIVE535_AND_CS2_COMMENTED535_FIXED"),
        "cs2_position_mirrored": False,
        "grid_x0_local": 20,
        "grid_y0": 40,
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 560,
        "cell_width": 52,
        "cell_height": 58,
        "gap_x": 8,
        "gap_y": 8,
        "row_axis": "target_code_0_to_7",
        "column_axis": "source_code_0_to_7",
        "horizontal_comparison_group": (
            "eight_adjacent_cells_same_target_different_source"
        ),
        "global_header_sequence": list(pack.GLOBAL_HEADERS),
        "palette_source_sequence": [
            "FACTORY_OTP",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "FACTORY_OTP",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "L535_RUNTIME",
            "FACTORY_OTP",
        ],
        "factory_otp_white_ordinals": [1, 5, 9],
        "factory_otp_white_fill_byte": 17,
        "runtime_code7_semantics": (
            "unqualified_separator_and_background_transport_code_not_white"
        ),
        "runtime_code7_used_as_white": False,
        "ptlw_command_issued": False,
        "cropped_dtm": False,
        "all_action_dtm_transport": "packed_frame_per_controller",
        "cs1_r20_prefix_bytes": active["cs1_r20_prefix_bytes"],
        "cs1_r20_prefix_sha256": active["cs1_r20_prefix_sha256"],
        "cs2_r20_prefix_bytes": active["cs2_r20_prefix_bytes"],
        "cs2_r20_prefix_sha256": active["cs2_r20_prefix_sha256"],
        "r21_bytes": active["r21_bytes"],
        "r21_sha256": active["r21_sha256"],
        "same_boot_prior_complete_required": True,
        "skip_to_factory_white_allowed": False,
        "failure_containment_kind": runner._CONTAINMENT["kind"],  # noqa: SLF001
        "failure_containment_campaign_id": runner._CONTAINMENT[  # noqa: SLF001
            "campaign_id"
        ],
        "failure_containment_contract_id": runner._CONTAINMENT[  # noqa: SLF001
            "contract_id"
        ],
        "failure_containment_firmware_bytes": runner._CONTAINMENT[  # noqa: SLF001
            "firmware_bytes"
        ],
        "failure_containment_firmware_sha256": runner._CONTAINMENT[  # noqa: SLF001
            "firmware_sha256"
        ],
        "failure_containment_elf_bytes": runner._CONTAINMENT[  # noqa: SLF001
            "elf_bytes"
        ],
        "failure_containment_elf_sha256": runner._CONTAINMENT[  # noqa: SLF001
            "elf_sha256"
        ],
        "failure_containment_nvs_namespace": runner._CONTAINMENT[  # noqa: SLF001
            "nvs_namespace"
        ],
        "failure_containment_nvs_key": runner._CONTAINMENT["nvs_key"],  # noqa: SLF001
        "failure_containment_base_route": runner._CONTAINMENT[  # noqa: SLF001
            "base_route"
        ],
        "failure_containment_descriptor_id": runner._CONTAINMENT[  # noqa: SLF001
            "descriptor_id"
        ],
        "failure_containment_action_id": runner._CONTAINMENT[  # noqa: SLF001
            "action_id"
        ],
        "failure_containment_campaign_nvs_dependency": False,
        "failure_containment_automatic_dispatch": False,
        "main_campaign_resume_after_containment": False,
    }


def _version() -> dict[str, Any]:
    return {
        **_identity("version"),
        "layout_id": pack.VARIANT_KEY,
        "action_count": 9,
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
        "actions": runner._device_actions(),  # noqa: SLF001
        "action_count": 9,
        "one_driver_call_per_action": True,
        "factory_otp": True,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "automatic_chaining": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "electrical_parameter_write": False,
        "dither": False,
        "spatial_mixing": False,
        "retry": False,
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
    action = runner.base.runner.ACTIONS[ordinal - 1]
    source = runner.REPORT["actions"][ordinal - 1]
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
        "palette_source": source["palette_source"],
        "global_header": source["global_header"],
        "driver_entry": (
            "epdDisplayCompiledFactoryOtpWhiteRecovery"
            if source["driver_role"] == "FactoryWhite"
            else "epdDisplayCompiledChromaGrid"
        ),
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": ordinal + 1,
        "campaign_complete": ordinal == 9,
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
        action = runner.base.runner.ACTIONS[self.ordinal - 1]
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
    return frame[y * 512 + global_x // 2]


def test_pack_freezes_nine_actions_and_128_directional_recipes() -> None:
    report = pack.build_report()
    contract = report["contract"]
    assert report["contract_id"] == (
        "7f653cc9412d9b90a2c17a471dd54bfe0605c4abad41eeabe76ba1828f1958da"
    )
    assert report["offline_only"] is True
    assert report["hardware_accessed"] is False
    assert report["device_network_accessed"] is False
    assert report["serial_or_com_accessed"] is False
    assert len(report["actions"]) == 9
    assert len(contract["recipes"]) == 128
    assert contract["geometry"]["total_controller_observations"] == 256
    assert (
        contract["geometry"]["paired_controller_observations_not_waveform_identical"]
        is True
    )
    assert contract["global_header_sequence"] == list(pack.GLOBAL_HEADERS)
    assert contract["factory_otp_white"]["ordinals"] == [1, 5, 9]
    assert contract["factory_otp_white"]["runtime_code7_used_as_white"] is False
    assert contract["partial_refresh"] is False
    assert contract["unknown_commands"] is False
    assert contract["autochain"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False


def test_source_columns_and_target_rows_encode_horizontal_comparisons() -> None:
    source = pack._grid_frame("source_columns")  # noqa: SLF001
    target = pack._grid_frame("target_rows")  # noqa: SLF001
    for controller in (0, 1):
        for row in range(8):
            assert [
                _cell_pair(source, controller, row, column) for column in range(8)
            ] == [(code << 4) | code for code in range(8)]
            assert [
                _cell_pair(target, controller, row, column) for column in range(8)
            ] == [(row << 4) | row] * 8
    assert source[0] == 0x77
    assert target[0] == 0x77


def test_factory_white_and_repeat_identities_are_exact_but_action_ids_differ() -> None:
    actions = pack.build_report()["actions"]
    for ordinals in ((1, 5, 9), (3, 4), (7, 8)):
        selected = [actions[ordinal - 1] for ordinal in ordinals]
        assert len({item["frame"]["sha256"] for item in selected}) == 1
        assert len({item["cs1_dtm"]["sha256"] for item in selected}) == 1
        assert len({item["action_id"] for item in selected}) == len(selected)
    assert actions[0]["frame"]["sha256"] == (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
    )
    assert actions[0]["frame"]["histogram"] == [0, 614400, 0, 0, 0, 0, 0, 0]


def test_cpp_contract_has_six_roles_exact_profile_map_and_factory_dispatch() -> None:
    header = (ROOT / "src/ec5_chroma_grid_epd_driver.h").read_text(encoding="utf-8")
    driver = (ROOT / "src/ec5_runtime_lut_cross_palette_v1_driver.inc").read_text(
        encoding="utf-8"
    )
    main = (ROOT / "src/ec5_runtime_lut_cross_palette_v1_main.cpp").read_text(
        encoding="utf-8"
    )
    identity = (
        ROOT / "src/ec5_runtime_lut_multi_target_history_v1_identity.inc"
    ).read_text(encoding="utf-8")
    assert "ReverseSource = 4" in header
    assert "ReverseTarget = 5" in header
    assert "PH_ROLE_COUNT = 6" in driver
    assert "role == EpdChromaGridRole::ReverseSource" in driver
    assert "role == EpdChromaGridRole::ReverseTarget" in driver
    assert "const ph::Window *window = nullptr;" in driver
    assert "ph::kSeparatorCode" in driver
    assert "kWhiteCode" not in identity
    assert main.count("epdReadBusy() != 1") >= 3
    assert "epdDisplayCompiledFactoryOtpWhiteRecovery()" in main
    assert "epdValidateCompiledFactoryOtpWhiteRecoveryFixture()" in main


def test_config_and_build_surface_are_isolated() -> None:
    config = (
        ROOT / "src/ec5_runtime_lut_multi_target_history_v1_main_config.inc"
    ).read_text(encoding="utf-8")
    identity = (
        ROOT / "src/ec5_runtime_lut_multi_target_history_v1_identity.inc"
    ).read_text(encoding="utf-8")
    pio = (ROOT / "platformio.runtime_lut_multi_target_history_v1.ini").read_text(
        encoding="utf-8"
    )
    actions = pack.build_report()["actions"]
    assert config.count("RLMTH_ACTION(") == 10  # macro plus nine actions
    for action in actions:
        assert action["descriptor_id"] in config
        assert action["action_id"] in config
    assert "kNvsNamespace = rlmth::kNvsNamespace" in config
    assert 'kNvsNamespace[] = "rlmth_v1"' in identity
    assert "cursor_mth1" in config
    assert "/api/ec5/multi-target-history-v1/" in config
    assert "build-runtime-lut-multi-target-history-v1" in pio
    assert "MF1750_RUNTIME_LUT_MULTI_TARGET_HISTORY_V1_BUILD=1" in pio
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in pio


def test_runner_describe_and_artifact_binding_are_exact() -> None:
    value = runner.describe()
    binding = value["firmware_binding"]
    assert binding["bound"] is True
    assert value["preflight_busy_contract"]["ordinals_1_to_9"] == (
        "RAW_READY_BUSY_1_ONLY"
    )
    assert value["fixed_transport"]["factory_otp_white_ordinals"] == [1, 5, 9]
    assert value["fixed_transport"]["runtime_code7_used_as_white"] is False
    assert value["ordinal_progression"]["terminal_next_ordinal"] == 10
    assert value["ordinal_progression"]["automatic_chaining"] is False
    containment = value["ordinal_progression"]["visual_or_terminal_failure_containment"]
    assert containment["campaign_id"] == pack.containment.CAMPAIGN_ID
    assert containment["contract_id"] == pack.containment.CONTRACT_ID
    assert containment["nvs_namespace"] != pack.NVS_NAMESPACE
    assert containment["artifact_binding_status"]["firmware_bin"]["verified"]
    assert containment["artifact_binding_status"]["firmware_elf"]["verified"]
    for name, expected_bytes, expected_sha in (
        ("firmware.bin", runner.FIRMWARE_BYTES, runner.FIRMWARE_SHA256),
        ("firmware.elf", runner.ELF_BYTES, runner.ELF_SHA256),
    ):
        artifact = runner.BUILD_DIR / name
        assert artifact.stat().st_size == expected_bytes
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_sha
    binary = (runner.BUILD_DIR / "firmware.bin").read_bytes()
    for action in pack.build_report()["actions"]:
        assert action["descriptor_id"].encode("ascii") in binary
        assert action["action_id"].encode("ascii") in binary


def test_version_and_manifest_accept_only_mixed_factory_runtime_contract() -> None:
    runner._validate_version(_version())  # noqa: SLF001
    runner._validate_manifest(_manifest())  # noqa: SLF001
    bad = _manifest()
    bad["factory_otp"] = False
    with pytest.raises(runner.base.runner.RecheckError, match="factory_otp"):
        runner._validate_manifest(bad)  # noqa: SLF001
    bad = _manifest()
    bad["history_layout"]["runtime_code7_used_as_white"] = True
    with pytest.raises(runner.base.runner.RecheckError, match="code7"):
        runner._validate_manifest(bad)  # noqa: SLF001


def test_missing_artifact_refuses_before_any_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeDevice(1)
    monkeypatch.setattr(runner, "BUILD_DIR", tmp_path)
    with pytest.raises(runner.base.runner.RecheckError, match="artifact is missing"):
        runner.run_once(
            "http://192.168.4.1",
            1,
            claims=tmp_path / "claims",
            output=tmp_path / "result.json",
            requester=fake,
        )
    assert fake.calls == []


@pytest.mark.parametrize("ordinal", range(1, 10))
def test_every_ordinal_requires_raw_ready_busy_high(ordinal: int) -> None:
    high = FakeDevice(ordinal, busy=1)
    boot_nonce, transcript, _ = runner._preflight(  # noqa: SLF001
        "http://192.168.4.1", ordinal, expected_busy=1, requester=high
    )
    assert boot_nonce == high.boot_nonce
    assert len(transcript) == 4
    low = FakeDevice(ordinal, busy=0)
    with pytest.raises(runner.base.runner.RecheckError, match="BUSY=1"):
        runner._preflight(  # noqa: SLF001
            "http://192.168.4.1", ordinal, expected_busy=1, requester=low
        )


@pytest.mark.parametrize("ordinal", range(1, 10))
def test_strict_complete_accepts_all_nine_actions(ordinal: int) -> None:
    runner.v3._validate_complete_report(  # noqa: SLF001
        _complete_report(ordinal, "0123456789abcdef"),
        ordinal,
        "0123456789abcdef",
    )


def test_action_six_cannot_skip_factory_direction_separator() -> None:
    fake = FakeDevice(6)
    fake.report = lambda: _complete_report(4, fake.boot_nonce)  # type: ignore[method-assign]
    with pytest.raises(runner.base.runner.RecheckError):
        runner._preflight(  # noqa: SLF001
            "http://192.168.4.1", 6, expected_busy=1, requester=fake
        )


def test_one_invocation_performs_one_arm_and_one_execute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner.v1.time, "sleep", lambda _seconds: None)
    fake = FakeDevice(1)
    output = tmp_path / "pass.json"
    result = runner.run_once(
        "http://192.168.4.1",
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
    assert fake.calls[:4] == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]


@pytest.mark.parametrize(
    "value",
    (
        "https://192.168.4.1",
        "http://example.com",
        "http://8.8.8.8",
        "http://user@192.168.4.1",
        "http://192.168.4.1/path",
        "http://[::1]",
    ),
)
def test_runner_rejects_nonlocal_or_nonliteral_origins(value: str) -> None:
    with pytest.raises(runner.base.runner.RecheckError):
        runner._private_origin(value)  # noqa: SLF001


def test_runner_origin_and_http_transport_are_fail_closed() -> None:
    assert runner._private_origin("http://192.168.4.1:80/") == (  # noqa: SLF001
        "http://192.168.4.1:80"
    )
    source = inspect.getsource(runner._direct_http_request)  # noqa: SLF001
    assert "ProxyHandler({})" in source
    assert "_NoRedirect()" in source
    salvage = inspect.getsource(runner.v1.salvage_fault_once)
    assert '"network": {"get": 4, "post": 0}' in salvage
    assert 'method="POST"' not in salvage


def test_cli_requires_explicit_human_observation_gate() -> None:
    with pytest.raises(SystemExit):
        runner._parse_args(  # noqa: SLF001
            [
                "run",
                "--base-url",
                "http://192.168.4.1",
                "--ordinal",
                "1",
                "--confirm-j2-on",
                "--output",
                "unused.json",
            ]
        )
    parsed = runner._parse_args(  # noqa: SLF001
        [
            "run",
            "--base-url",
            "http://192.168.4.1",
            "--ordinal",
            "1",
            "--confirm-j2-on",
            "--confirm-human-observation-gate",
            "--output",
            "unused.json",
        ]
    )
    assert parsed.confirm_human_observation_gate is True
