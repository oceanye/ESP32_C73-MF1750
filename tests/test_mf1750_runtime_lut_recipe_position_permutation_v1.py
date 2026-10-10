from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from tools import mf1750_runtime_lut_hue_brightness_redpink_v2_pack as old_v2
from tools import mf1750_runtime_lut_recipe_position_permutation_v1_once as once
from tools import mf1750_runtime_lut_recipe_position_permutation_v1_pack as pack


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ROOT / "src" / "ec5_runtime_lut_recipe_position_permutation_v1_identity.inc"
CONFIG = ROOT / "src" / "ec5_runtime_lut_recipe_position_permutation_v1_main_config.inc"
MAIN = ROOT / "src" / "ec5_runtime_lut_recipe_position_permutation_v1_main.cpp"
DRIVER = ROOT / "src" / "ec5_runtime_lut_recipe_position_permutation_v1_driver.inc"
PIO = ROOT / "platformio.runtime_lut_recipe_position_permutation_v1.ini"


def _report() -> dict:
    return pack.build_report()


def _version_fixture() -> dict:
    value = {
        "kind": f"{once.KIND_PREFIX}-version",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": once.DEVICE_API_VERSION,
        "identity_revision": once.IDENTITY_REVISION,
        "contract_id": _report()["contract_id"],
        "classification": once.CLASSIFICATION,
        "layout_id": pack.VARIANT_KEY,
        "action_count": 4,
        "runtime_lut_write": True,
        "nvs_contract": once._expected_nvs_contract(),
        "baseline_contract": once._expected_baseline_contract(),
    }
    for key in (
        "full_screen_global_refresh",
        "recipe_position_permutation",
        "recipe_linked_candidates_only",
        "human_observation_gate_after_every_action",
        "busy_qualified_arm_execute_dispatch",
        "external_factory_white_precondition_required",
        "one_visible_refresh_per_ordinal",
    ):
        value[key] = True
    for key in (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "unknown_commands",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "local_hold_claimed",
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    ):
        value[key] = False
    return value


def _manifest_fixture() -> dict:
    report = _report()
    value = _version_fixture()
    value["kind"] = f"{once.KIND_PREFIX}-manifest"
    value.update(
        {
            "actions": list(once.base.runner.ACTIONS),
            "round_count": 1,
            "factory_otp": True,
            "custom_lut_or_waveform": True,
            "synchronous_both_controllers": True,
            "one_driver_call_per_action": True,
            "history_layout": {
                "permutation_id": "P1_SOURCE_SHIFT3_MIDDLE_REVERSE",
                "source_physical_to_code": "(column+3)%8",
                "middle_physical_to_code": "7-row",
                "fixed_target": "active_code_0",
                "candidate_cells_total_observations": 128,
                "unique_recipes": 64,
                "mixed_controller_r20_intentionally_preserved": True,
                "controller_color_equivalence_claimed": False,
                "external_factory_white_precondition_required": True,
                "factory_otp_white_ordinal": 4,
                "one_visible_refresh_per_ordinal": True,
                "active_global_header_sha256": report["contract"]["profiles"]["active"][
                    "global_header_sha256"
                ],
                "commented_global_header_sha256": report["contract"]["profiles"][
                    "commented"
                ]["global_header_sha256"],
                "cs1_r20_prefix_sha256": report["contract"]["profiles"]["active"][
                    "cs1_r20_prefix_sha256"
                ],
                "cs2_r20_prefix_sha256": report["contract"]["profiles"]["active"][
                    "cs2_r20_prefix_sha256"
                ],
                "r21_sha256": report["contract"]["profiles"]["active"]["r21_sha256"],
            },
        }
    )
    return value


def test_pack_is_deterministic_and_offline() -> None:
    first = _report()
    second = _report()
    assert first == second
    assert first["offline_only"] is True
    assert first["hardware_accessed"] is False
    assert first["device_network_accessed"] is False
    assert first["serial_or_com_accessed"] is False
    assert first["firmware_flashed"] is False
    assert first["display_refreshed"] is False
    assert re.fullmatch(r"[0-9a-f]{64}", first["contract_id"])


def test_layout_id_and_permutation_are_frozen() -> None:
    report = _report()
    assert pack.VARIANT_KEY == (
        "L535_TARGET_HUE_REDPINK_BRIGHTNESS_HISTORY_8X8_ABA_RECIPE_PERMUTATION_V1"
    )
    assert report["contract"]["permutation"] == {
        "id": "P1_SOURCE_SHIFT3_MIDDLE_REVERSE",
        "source_column_shift_mod8": 3,
        "middle_physical_row_to_code": "7-r",
        "bijective": True,
        "p0_to_p1_has_no_fixed_cells": True,
    }
    assert [pack.source_code_at_physical_column(c) for c in range(8)] == [
        3,
        4,
        5,
        6,
        7,
        0,
        1,
        2,
    ]
    assert [pack.middle_code_at_physical_row(r) for r in range(8)] == [
        7,
        6,
        5,
        4,
        3,
        2,
        1,
        0,
    ]


def test_recipe_and_128_observation_maps_are_bijective() -> None:
    contract = _report()["contract"]
    recipes = contract["recipe_map"]
    observations = contract["observation_map"]
    physical = contract["physical_to_recipe_map"]
    assert len(recipes) == 64
    assert len(observations) == 128
    assert len(physical) == 128
    assert len({item["recipe_id"] for item in recipes}) == 64
    assert len({item["observation_id"] for item in observations}) == 128
    assert Counter(item["controller"] for item in observations) == {0: 64, 1: 64}
    for controller in (0, 1):
        subset = [item for item in physical if item["controller"] == controller]
        assert (
            len({(item["physical_row"], item["physical_column"]) for item in subset})
            == 64
        )
        assert len({item["recipe_id"] for item in subset}) == 64
    for item in physical:
        assert item["source_code"] == (item["physical_column"] + 3) % 8
        assert item["middle_code"] == 7 - item["physical_row"]
        assert item["target_code"] == 0


def test_p0_to_p1_inverse_mapping_is_exact() -> None:
    for item in _report()["contract"]["recipe_map"]:
        source = item["source"]["code"]
        middle = item["middle"]["code"]
        assert item["p0_physical"]["column"] == source
        assert item["p0_physical"]["row"] == middle
        assert item["p1_physical"]["column"] == (source - 3) % 8
        assert item["p1_physical"]["row"] == 7 - middle
        assert item["p0_physical"] != item["p1_physical"]


def test_four_manual_actions_and_payload_hashes_are_explicit() -> None:
    report = _report()
    actions = report["actions"]
    assert [item["ordinal"] for item in actions] == [1, 2, 3, 4]
    assert [item["driver_role"] for item in actions] == [
        "Source",
        "Mid",
        "Target",
        "FactoryWhite",
    ]
    assert [item["global_header"] for item in actions] == [
        "active",
        "commented",
        "active",
        None,
    ]
    for item in actions[:3]:
        assert re.fullmatch(r"[0-9a-f]{64}", item["frame"]["sha256"])
        assert re.fullmatch(r"[0-9a-f]{64}", item["global_header_sha256"])
        assert item["cs1_r20_prefix_bytes"] == 535
        assert item["cs2_r20_prefix_bytes"] == 535
        assert re.fullmatch(r"[0-9a-f]{64}", item["cs1_r20_prefix_sha256"])
        assert re.fullmatch(r"[0-9a-f]{64}", item["cs2_r20_prefix_sha256"])
        assert item["r21_bytes"] == 704
        assert re.fullmatch(r"[0-9a-f]{64}", item["r21_sha256"])
    assert actions[3]["palette_source"] == "FACTORY_OTP"
    assert actions[3]["global_header_sha256"] is None
    assert report["contract"]["one_visible_refresh_per_ordinal"] is True
    assert report["contract"]["autochain"] is False
    assert report["contract"]["retry"] is False
    assert report["contract"]["automatic_recovery"] is False


def test_new_campaign_does_not_reuse_old_v2_identity_or_outputs() -> None:
    current = _report()
    old = old_v2.build_report()
    assert current["campaign_id"] != old["campaign_id"]
    assert current["contract_id"] != old["contract_id"]
    assert current["nvs_namespace"] != old["nvs_namespace"]
    assert current["nvs_key"] != old["nvs_key"]
    assert current["nvs_boot_key"] != old["contract"]["nvs_boot_key"]
    assert not (
        {item["action_id"] for item in current["actions"]}
        & {item["action_id"] for item in old["actions"]}
    )
    assert not (
        {item["descriptor_id"] for item in current["actions"]}
        & {item["descriptor_id"] for item in old["actions"]}
    )
    assert "recipe_position_permutation_v1" in once.base.runner.DEFAULT_CLAIMS.name
    assert "RECIPE_POSITION_PERMUTATION" in once.base.runner.DEFAULT_OUTPUT.name


def test_analysis_input_contract_is_fail_closed() -> None:
    analysis = _report()["analysis_input_contract"]
    assert analysis["expected_observations"] == 128
    assert analysis["expected_unique_recipes"] == 64
    assert analysis["join_key"] == [
        "controller",
        "physical_row",
        "physical_column",
    ]
    assert analysis["exploratory_gate"] == {
        "recipe_correlation_min": 0.8,
        "recipe_minus_physical_correlation_min": 0.25,
        "pass_label": "RECIPE_LINKED_CANDIDATE_ONLY",
        "not_a_qualified_new_colour": True,
    }
    assert analysis["qualification_limits"]["single_permutation_cannot_qualify"] is True


def test_cpp_identity_matches_offline_contract() -> None:
    report = _report()
    identity = IDENTITY.read_text(encoding="utf-8")
    joined_identity = re.sub(r'"\s*"', "", identity)
    config = CONFIG.read_text(encoding="utf-8")
    for token in (
        pack.VARIANT_KEY,
        pack.BUILD_TAG,
        pack.TEST_ID,
        pack.CAMPAIGN_ID,
        report["contract_id"],
        pack.NVS_NAMESPACE,
        pack.NVS_BOOT_KEY,
    ):
        assert token in joined_identity
    for action in report["actions"]:
        for token in (
            action["descriptor_id"],
            action["action_id"],
            action["frame"]["sha256"],
            action["cs1_dtm"]["sha256"],
        ):
            assert token in identity
            assert token in config


def test_cpp_driver_builds_shifted_and_reversed_frames() -> None:
    driver = DRIVER.read_text(encoding="utf-8")
    assert "MF1750_RUNTIME_LUT_RECIPE_POSITION_PERMUTATION_V1_BUILD" in driver
    assert "(column + ph::kSourceColumnShift) % ph::kGridColumns" in driver
    assert "ph::kGridRows - 1U - row" in driver
    assert "ec5_runtime_lut_hue_brightness_redpink_v2_identity.inc" not in driver
    assert "MF1750_RUNTIME_LUT_HUE_BRIGHTNESS_REDPINK_V2_BUILD" not in driver


def test_main_has_isolated_routes_nvs_and_no_startup_refresh() -> None:
    main = MAIN.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    pio = PIO.read_text(encoding="utf-8")
    assert "static constexpr uint8_t kActionCount = 4;" in main
    assert 'external_anchor_required\\":true' in main
    assert "/api/ec5/redpink-recipe-permutation-v1/" in config
    assert 'static constexpr const char *kNvsKey = "cursor_rpp1";' in config
    assert "MF1750_RUNTIME_LUT_RECIPE_POSITION_PERMUTATION_V1_BUILD=1" in pio
    assert "EPD_ENABLE_TEST_PATTERN=0" in pio
    assert "automatic chaining, retry, recovery" in main


def test_runner_version_and_manifest_validators_accept_exact_contract() -> None:
    once._validate_version(_version_fixture())
    once._validate_manifest(_manifest_fixture())


def test_runner_validators_reject_permutation_or_payload_drift() -> None:
    manifest = _manifest_fixture()
    changed = deepcopy(manifest)
    changed["history_layout"]["source_physical_to_code"] = "column"
    with pytest.raises(once.base.runner.RecheckError, match="source_physical"):
        once._validate_manifest(changed)
    changed = deepcopy(manifest)
    changed["history_layout"]["cs2_r20_prefix_sha256"] = "0" * 64
    with pytest.raises(once.base.runner.RecheckError, match="cs2_r20"):
        once._validate_manifest(changed)


def test_runner_outputs_claims_and_routes_are_independent() -> None:
    assert once.base.runner.ENDPOINTS == {
        name: f"/api/ec5/redpink-recipe-permutation-v1/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    assert len(once.ACTION_OUTPUTS) == 4
    assert len(set(once.ACTION_OUTPUTS.values())) == 4
    assert once.DIAGNOSTIC_OUTPUT not in once.ACTION_OUTPUTS.values()
    assert all(
        path.parent == once.base.runner.DEFAULT_OUTPUT
        for path in once.ACTION_OUTPUTS.values()
    )


def test_ordinal1_requires_explicit_external_clean_white() -> None:
    with pytest.raises(
        once.base.runner.RecheckError,
        match="verified external factory-OTP clean white",
    ):
        once.run_once(
            "http://192.0.2.1",
            1,
            claims=once.base.runner.DEFAULT_CLAIMS,
            output=once.ACTION_OUTPUTS[1],
            requester=lambda *args, **kwargs: pytest.fail("network requester called"),
            external_clean_white_confirmed=False,
        )


def test_runner_artifact_binding_matches_clean_build() -> None:
    binding = once._firmware_binding()
    assert binding["bound"] is True
    for name, expected in (
        ("firmware.bin", binding["bin"]),
        ("firmware.elf", binding["elf"]),
    ):
        path = once.BUILD_DIR / name
        assert path.stat().st_size == expected["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]


def test_dry_validation_is_offline_and_exposes_mapping_contract() -> None:
    value = once.dry_validate()
    assert value["offline_only"] is True
    assert value["hardware_accessed"] is False
    assert value["device_network_accessed"] is False
    assert value["serial_or_com_accessed"] is False
    assert value["firmware_flashed"] is False
    assert value["display_refreshed"] is False
    assert value["recipe_count"] == 64
    assert value["observation_count"] == 128
    assert value["physical_mapping_count"] == 128


def test_describe_is_json_serializable_and_contains_full_mapping() -> None:
    value = once.describe()
    encoded = json.dumps(value, sort_keys=True)
    assert pack.VARIANT_KEY in encoded
    assert len(value["variant"]["observation_map"]) == 128
    assert len(value["variant"]["physical_to_recipe_map"]) == 128
    assert value["preflight"]["no_retry"] is True
    assert value["preflight"]["no_recovery"] is True
    assert value["preflight"]["no_autochain"] is True
    assert (
        value["preflight"][
            "ordinal1_explicit_external_clean_white_confirmation_required"
        ]
        is True
    )


def test_staged_action_output_embeds_128_cell_mapping(tmp_path: Path) -> None:
    staged = tmp_path / ".staged.json"
    output = tmp_path / "action.json"
    staged.write_text(json.dumps({"ordinal": 3}), encoding="utf-8")
    once._write_staged_result(output, staged)
    saved = json.loads(output.read_text(encoding="utf-8"))
    binding = saved["recipe_position_permutation_binding"]
    assert len(binding["recipe_map"]) == 64
    assert len(binding["observation_map"]) == 128
    assert len(binding["physical_to_recipe_map"]) == 128
    assert binding["runtime_payload"]["global_header"] == "active"
    assert binding["frame"]["sha256"] == _report()["actions"][2]["frame"]["sha256"]
    assert saved["integrity"]["algorithm"] == "sha256-canonical-json-without-integrity"
    assert staged.exists() is False
