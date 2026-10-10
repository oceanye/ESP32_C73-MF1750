from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from tools import mf1750_raw_p16_crossover_t2_discovery_successor_pack as t2_v1
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_v2_build as t2_build
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_v2_once as t2_once
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_v2_pack as t2
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_build as w3_build,
)
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_once as w3_once,
)
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3,
)


ROOT = Path(__file__).resolve().parents[1]


def test_t2_v2_repeat_authority_is_sealed_underexposure_only() -> None:
    value = t2.validate_repeat_authority()
    binding = t2.repeat_authority_binding()
    assert value["kind"] == binding["kind"]
    assert value["summary"]["classification_counts"] == {
        "PASS": 0,
        "REVIEW": 0,
        "FAIL": 16,
    }
    assert binding["underexposed_measurement_only"] is True
    assert binding["visible_payload_failure_claimed"] is False
    assert binding["authorizes_fresh_discovery_repeat_only"] is True
    assert binding["qualified_colour_count"] == 0


def test_t2_v2_payload_is_exact_v1_but_all_mutation_identities_are_fresh() -> None:
    report = t2.build_report()
    frozen = t2_v1.build_report()
    action = report["actions"][0]
    frozen_action = frozen["actions"][0]
    for key in ("frame", "cs1_dtm", "cs2_dtm", "waveform_binding"):
        assert action[key] == frozen_action[key]
    assert action["repeat_of_stage"] == t2_v1.STAGE
    assert action["prior_static_action_id"] == frozen_action["action_id"]
    assert report["contract_id"] != frozen["contract_id"]
    assert action["descriptor_id"] != frozen_action["descriptor_id"]
    assert action["action_id"] != frozen_action["action_id"]
    assert report["contract"]["campaign_id"] != frozen["contract"]["campaign_id"]
    assert report["contract"]["base_route"] != frozen["contract"]["base_route"]
    assert report["contract"]["nvs_namespace"] != frozen["contract"]["nvs_namespace"]


def test_t2_v2_capture_plan_is_exact_and_not_a_threshold_relaxation() -> None:
    assert t2.CAPTURE_PLAN == {
        "camera_logical_id": "USB_VID_32E4_PID_4801",
        "camera_friendly_name": "48MP USB Camera",
        "exposure": -3,
        "frame_width": 4000,
        "frame_height": 3000,
        "retained_atlas_frame_count": 3,
        "pre_white_reference_required": True,
        "post_white_reference_required": True,
        "white_reference_min_lstar": 25.0,
        "automatic_threshold_relaxation": False,
        "camera_relative_screening_only": True,
    }


def test_t2_v2_runner_and_artifacts_are_offline_ready() -> None:
    validation = t2_once.dry_validate()
    assert validation["result"] == "PASS"
    assert validation["artifacts_verified"] is True
    assert validation["network_requests"] == 0
    assert validation["relay_accessed"] is False
    assert validation["no_retry"] is True
    assert validation["no_autochain"] is True
    assert validation["default_evidence_root"].endswith(
        "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2"
    )
    for item in t2_once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_t2_v2_host_accepts_exact_exposure_bound_white_anchor() -> None:
    host = t2_once.configure()
    assert host._FACTORY_WHITE_ANCHOR_ROLE == t2.FACTORY_WHITE_ANCHOR_ROLE  # noqa: SLF001
    assert [item["round"] for item in host.base.runner.ACTIONS] == [2]
    report = t2.build_report()
    runner = host.base.runner
    identity = {
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
    }
    capabilities = {
        "full_screen_global_refresh": True,
        "crossover_r20_position_balanced_probe": True,
        "position_balanced_atlas": True,
        "busy_qualified_arm_execute_dispatch": True,
        "device_enforced_same_boot": True,
        "partial_refresh": False,
        "window_refresh": False,
        "command_0x83": False,
        "command_0x86": False,
        "unknown_commands": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "same_r20_controller_parity_probe": False,
        "same_palette_hold_probe": False,
        "cross_palette_hold_probe": False,
        "local_hold_claimed": False,
        "colour_qualification": False,
        "main_campaign_resume_after_containment": False,
    }
    discovery = {
        "coarse_discovery_authority": t2.coarse_authority_binding(),
        "coarse_discovery_only": True,
        "formal_gate_evaluated": False,
        "formal_advance_to_t2_permitted": False,
        "repeat_authority": {
            **t2.repeat_authority_binding(),
            "exposure": t2.CAPTURE_PLAN["exposure"],
            "automatic_threshold_relaxation": False,
        },
    }
    version = {
        "schema_version": 3,
        "kind": f"{runner.DEVICE_KIND_PREFIX}-version",
        **identity,
        **capabilities,
        **discovery,
        "layout_id": t2.CONFIG.variant_key,
        "action_count": 1,
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
        "nvs_contract": {
            "namespace": t2.CONFIG.nvs_namespace,
            "key": t2.CONFIG.nvs_key,
            "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
            "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
            "initial_key_present": False,
            "initial_value": 1,
            "initial_next_ordinal": 1,
            "terminal_next_ordinal": 2,
            "campaign_boot_key": t2.CONFIG.nvs_boot_key,
            "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
            "campaign_boot_initial_key_present": False,
            "campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1": True,
            "campaign_boot_readback_required": True,
            "current_boot_exact_match_required": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
        },
        "baseline_contract": {
            "ordinal": None,
            "role": t2.FACTORY_WHITE_ANCHOR_ROLE,
            "external_anchor_required": True,
            "one_visible_refresh_required": False,
        },
        "external_containment": report["contract"]["external_containment"],
    }
    layout = {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 4,
        "grid_columns_per_controller": 8,
        "row_codes": [list(row) for row in t2.CODE_ROWS],
        "grid_x0_local": 20,
        "grid_y_by_row": list(t2.GRID_Y_BY_ROW),
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 552,
        "cell_width": 52,
        "cell_height": 100,
        "gap_x": 8,
        "gap_y": 36,
        "background_code": 7,
        "border": False,
        "same_layout_both_controllers": True,
        "controller_dtm_byte_identical": True,
        "controller_r20_payloads_byte_identical": False,
        "cs2_position_mirrored": False,
        "spatial_dither": False,
        "factory_otp_white_ordinals": [],
        "runtime_lut_ordinals": [1],
        "one_visible_refresh_per_action": True,
        "samples_per_code_per_controller_per_frame": 4,
        "primary_codes": [3, 5, 6, 7],
        "guard_codes": [4],
        "control_codes": [0, 1, 2],
        "qualified_colours": 0,
        "colour_equivalence_claimed": False,
        "controller_bus_capture_claimed": False,
    }
    manifest = {
        "schema_version": 3,
        "kind": f"{runner.DEVICE_KIND_PREFIX}-manifest",
        **identity,
        **capabilities,
        **discovery,
        "layout_id": t2.CONFIG.variant_key,
        "actions": list(runner.ACTIONS),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "external_containment": report["contract"]["external_containment"],
        "history_layout": layout,
    }

    host._validate_version(version)  # noqa: SLF001
    host._validate_manifest(manifest)  # noqa: SLF001

    stale_version = deepcopy(version)
    stale_version["baseline_contract"]["role"] = (
        "EXTERNAL_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED"
    )
    with pytest.raises(runner.RecheckError, match="factory-white anchor"):
        host._validate_version(stale_version)  # noqa: SLF001

    stale_manifest = deepcopy(manifest)
    stale_manifest["actions"][0]["round"] = 1
    with pytest.raises(runner.RecheckError, match="manifest actions"):
        host._validate_manifest(stale_manifest)  # noqa: SLF001


def test_t2_v2_cpp_and_ini_bind_exact_identity_without_upload() -> None:
    report = t2.build_report()
    identity = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_v2_identity.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "platformio.raw_p16_crossover_t2_ca_coarse_discovery_successor_v2.ini"
    ).read_text(encoding="utf-8")
    adapter = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    for value in (
        t2.CONFIG.campaign_id,
        t2.CONFIG.test_id,
        report["contract_id"],
        report["actions"][0]["descriptor_id"],
        report["actions"][0]["action_id"],
        t2.CONFIG.nvs_namespace,
    ):
        assert value in identity
    assert t2.REPEAT_AUTHORITY_FILE_SHA256 in adapter
    assert '"exposure\\\":-3' in adapter
    assert "MF1750_RAW_P16_CROSSOVER_T2_DISCOVERY_SUCCESSOR_V2_BUILD=1" in config
    assert "upload_protocol" not in config
    assert "upload_command" not in config


def test_w3_exactly_binds_t2_v2_and_is_one_white_action() -> None:
    report = w3.build_white_report()
    source = t2.build_report()
    action = report["action"]
    source_action = source["actions"][0]
    assert action["source_campaign_id"] == source["contract"]["campaign_id"]
    assert action["source_contract_id"] == source["contract_id"]
    assert action["source_descriptor_id"] == source_action["descriptor_id"]
    assert action["source_action_id"] == source_action["action_id"]
    contract = report["contract"]
    assert contract["action_count"] == 1
    assert contract["one_visible_refresh_per_action"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_w3_runner_routes_roots_and_artifacts_are_fresh() -> None:
    validation = w3_once.dry_validate()
    assert validation["result"] == "PASS"
    assert validation["artifacts_verified"] is True
    assert validation["source_t2_v2_campaign_contract_descriptor_action_exact"] is True
    assert all(
        endpoint.startswith(w3.CONFIG.base_route + "/")
        for endpoint in validation["endpoint_set"].values()
    )
    assert "W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE" in validation["output_root"]
    for item in w3_once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_w3_cpp_and_ini_bind_exact_identity_and_six_routes() -> None:
    report = w3.build_white_report()
    identity = (
        ROOT / "src/ec5_raw_p16_crossover_w3_discovery_successor_v2_white_identity.inc"
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "platformio.raw_p16_crossover_w3_discovery_successor_v2_white_v1.ini"
    ).read_text(encoding="utf-8")
    for value in (
        w3.CONFIG.campaign_id,
        w3.CONFIG.build_tag,
        report["contract_id"],
        report["action"]["descriptor_id"],
        report["action"]["action_id"],
        report["action"]["source_contract_id"],
        report["action"]["source_descriptor_id"],
        report["action"]["source_action_id"],
        w3.marker(),
    ):
        assert value in identity
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f"w3-after-t2-coarse-discovery-successor-v2-white-v1/{endpoint}" in program
    assert "MF1750_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2_WHITE_BUILD=1" in config
    assert "upload_protocol" not in config
    assert "upload_command" not in config


@pytest.mark.parametrize(
    ("builder", "expected_config"),
    (
        (t2_build, t2_build.CONFIG),
        (w3_build, w3_build.CONFIG),
    ),
)
def test_builders_issue_one_compile_only_command(
    builder: object,
    expected_config: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pio = tmp_path / "pio.exe"
    pio.touch()
    commands: list[list[str]] = []

    monkeypatch.setattr(builder, "prebuild_validate", lambda: {"result": "PASS"})
    monkeypatch.setattr(
        builder.runner,
        "dry_validate",
        lambda **_kwargs: {"result": "PASS", "artifacts_verified": True},
    )
    monkeypatch.setattr(
        builder.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )
    result = builder.build(pio=pio)
    assert result["result"] == "PASS"
    assert commands == [[str(pio.resolve()), "run", "-c", expected_config]]
    assert "upload" not in commands[0]
