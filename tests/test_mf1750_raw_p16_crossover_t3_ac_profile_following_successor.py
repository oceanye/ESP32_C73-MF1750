from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

import pytest

from tools import mf1750_raw_p16_crossover_position_balanced_pack as legacy
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_build as builder,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as pack,
)


ROOT = Path(__file__).resolve().parents[1]


def _identity(host: object) -> dict[str, object]:
    runner = host.base.runner
    return {
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
    }


def _capabilities() -> dict[str, object]:
    return {
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
        "coarse_discovery_only": False,
        "profile_following_review_only": True,
        "profile_following_proven": False,
        "human_primary_judgement_required": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
        "human_observation_gate_after_every_action": True,
        "main_campaign_resume_after_containment": False,
    }


def _review_boundary() -> dict[str, object]:
    return {
        "source_action_authority": pack.completed_t2_v2_action_binding(),
        "pre_white_action_evidence": pack.completed_w3_white_action_binding(),
        "pre_white_authority": pack.pre_white_authority_binding(),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
        "human_observation_plan": deepcopy(pack.HUMAN_OBSERVATION_PLAN),
        "profile_following_review_only": True,
        "profile_following_proven": False,
        "human_primary_judgement_required": True,
        "human_observation_gate_after_every_action": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
    }


def _nvs_contract() -> dict[str, object]:
    return {
        "namespace": pack.CONFIG.nvs_namespace,
        "key": pack.CONFIG.nvs_key,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 2,
        "campaign_boot_key": pack.CONFIG.nvs_boot_key,
        "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
        "campaign_boot_initial_key_present": False,
        "campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1": True,
        "campaign_boot_readback_required": True,
        "current_boot_exact_match_required": True,
        "reboot_resume_allowed": False,
        "post_containment_resume_allowed": False,
    }


def _layout() -> dict[str, object]:
    return {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 4,
        "grid_columns_per_controller": 8,
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "grid_x0_local": 20,
        "grid_y_by_row": list(pack.GRID_Y_BY_ROW),
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


def _wire_documents(host: object) -> tuple[dict[str, object], dict[str, object]]:
    report = pack.build_report()
    runner = host.base.runner
    common = {
        **_identity(host),
        **_capabilities(),
        **_review_boundary(),
    }
    version = {
        "schema_version": 3,
        "kind": f"{runner.DEVICE_KIND_PREFIX}-version",
        **common,
        "layout_id": pack.CONFIG.variant_key,
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
        "nvs_contract": _nvs_contract(),
        "baseline_contract": {
            "ordinal": None,
            "role": pack.FACTORY_WHITE_ANCHOR_ROLE,
            "external_anchor_required": True,
            "one_visible_refresh_required": False,
        },
        "external_containment": report["contract"]["external_containment"],
    }
    manifest = {
        "schema_version": 3,
        "kind": f"{runner.DEVICE_KIND_PREFIX}-manifest",
        **common,
        "layout_id": pack.CONFIG.variant_key,
        "actions": list(runner.ACTIONS),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "external_containment": report["contract"]["external_containment"],
        "history_layout": _layout(),
    }
    return version, manifest


def test_authorities_are_exact_completed_evidence() -> None:
    completed = pack.validate_completed_t2_v2_action()
    white_action = pack.validate_completed_w3_white_action()
    pre_white = pack.validate_pre_white_authority()
    assert completed["outcome"] == "complete_pass"
    assert completed["terminal_report"]["terminal_state"] == "COMPLETE"
    assert white_action["outcome"] == "complete_pass"
    assert white_action["terminal_report"]["terminal_state"] == "COMPLETE"
    assert pre_white["raw_operator_report"]["operator_verbatim"] == "白屏，干净"
    assert pre_white["authority"]["operator_reported_clean_white"] is True
    assert pre_white["authority"]["action_complete_exactly_bound"] is True
    assert pre_white["authority"]["final_relay_commanded_off_exactly_bound"] is True
    assert pre_white["authority"]["camera_confirmation_claimed"] is False
    assert pre_white["final_relay_off_receipt_binding"]["target_state"] == "OFF"
    assert (
        pre_white["final_relay_off_receipt_binding"]["electrical_state_proven"] is False
    )


def test_t3_is_exact_ac_payload_under_fresh_non_reusable_identity() -> None:
    validation = pack.dry_validate()
    report = pack.build_report()
    action = report["actions"][0]
    legacy_ac = legacy.build_report("t3-ac-repeat")["actions"][0]
    assert validation["result"] == "PASS"
    assert action["round"] == 3
    assert action["profile_id"] == (
        "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
    )
    assert action["global_header"] == "active"
    assert action["waveform_binding"]["cs1"]["name"] == "active"
    assert action["waveform_binding"]["cs2"]["name"] == "commented"
    for key in ("frame", "cs1_dtm", "cs2_dtm", "waveform_binding"):
        assert action[key] == legacy_ac[key]
    assert action["action_id"] not in pack.non_reusable_action_ids()
    assert len(pack.non_reusable_action_ids()) == 10


def test_human_judgement_has_zero_required_camera_frames() -> None:
    assert pack.HUMAN_OBSERVATION_PLAN == {
        "primary_judgement": "HUMAN_VISUAL_PROFILE_FOLLOWING_REVIEW",
        "operator_observation_required": True,
        "camera_required_for_decision": False,
        "camera_evidence_optional": True,
        "camera_evidence_only": True,
        "required_retained_camera_frame_count": 0,
        "absolute_colour_claimed": False,
        "stable_new_colour_claimed": False,
        "profile_following_proven_by_this_action": False,
        "qualified_colour_count": 0,
    }
    containment = pack.external_containment_contract()
    assert containment["off_white_photos_before_atlas_required"] == 0
    assert containment["off_retained_atlas_photos_required"] == 0
    assert containment["camera_evidence_optional"] is True


def test_direct_host_accepts_exact_wire_contract_and_rejects_predecessors() -> None:
    host = once.configure()
    version, manifest = _wire_documents(host)
    host._validate_version(version)  # noqa: SLF001
    host._validate_manifest(manifest)  # noqa: SLF001
    expected = pack.build_report()["actions"][0]
    assert tuple(host.base.runner.ACTION_IDS) == (expected["action_id"],)
    assert host.base.runner.ACTIONS[0]["round"] == 3
    assert (
        host.base.runner.ACTIONS[0]["prior_static_action_id"]
        == (pack.completed_t2_v2_action_binding()["action_id"])
    )

    stale_action = deepcopy(manifest)
    stale_action["actions"][0]["action_id"] = pack.non_reusable_action_ids()[2]
    with pytest.raises(host.base.runner.RecheckError, match="manifest actions"):
        host._validate_manifest(stale_action)  # noqa: SLF001

    stale_round = deepcopy(manifest)
    stale_round["actions"][0]["round"] = 2
    with pytest.raises(host.base.runner.RecheckError, match="manifest actions"):
        host._validate_manifest(stale_round)  # noqa: SLF001

    camera_gate = deepcopy(version)
    camera_gate["human_observation_plan"]["camera_required_for_decision"] = True
    with pytest.raises(host.base.runner.RecheckError, match="human_observation_plan"):
        host._validate_version(camera_gate)  # noqa: SLF001

    old_anchor = deepcopy(version)
    old_anchor["baseline_contract"]["role"] = (
        "EXTERNAL_EXPOSURE_MINUS3_FACTORY_OTP_WHITE_BEFORE_AND_AFTER_REQUIRED"
    )
    with pytest.raises(host.base.runner.RecheckError, match="factory-white anchor"):
        host._validate_version(old_anchor)  # noqa: SLF001


def test_artifacts_cpp_identity_and_ini_are_exact() -> None:
    validation = once.dry_validate()
    report = pack.build_report()
    action = report["actions"][0]
    assert validation["artifacts_verified"] is True
    for item in once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]

    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_t3_ac_profile_following_successor_identity.inc"
    ).read_text(encoding="utf-8")
    selector = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_identity.inc"
    ).read_text(encoding="utf-8")
    main_config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "platformio.raw_p16_crossover_t3_ac_profile_following_successor_v1.ini"
    ).read_text(encoding="utf-8")
    for value in (
        pack.CONFIG.campaign_id,
        pack.CONFIG.test_id,
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        pack.CONFIG.nvs_namespace,
        action["profile_id"],
        action["global_tuple_id"],
    ):
        assert value in identity
    assert (
        "ec5_raw_p16_crossover_t3_ac_profile_following_successor_identity.inc"
        in selector
    )
    assert pack.CONFIG.base_route in main_config
    assert 'required_retained_camera_frame_count\\":0' in main_config
    assert pack.W3_HUMAN_CLEAN_WHITE_AUTHORITY_FILE_SHA256 in main_config
    assert "clean_white_operator_confirmed" not in main_config
    assert (
        "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD=1" in config
    )
    assert "upload_protocol" not in config
    assert "upload_command" not in config

    anchor_start = main_config.index(
        "static constexpr const char *kExternalWhiteAnchorJson =",
        main_config.index(
            "#if defined("
            "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_BUILD)"
        ),
    )
    anchor_end = main_config.index("\n#else", anchor_start)
    fragments = re.findall(r'"(?:\\.|[^"\\])*"', main_config[anchor_start:anchor_end])
    embedded = json.loads("{" + "".join(ast.literal_eval(x) for x in fragments) + "}")
    report_boundary = _review_boundary()
    assert (
        embedded["external_containment"] == report["contract"]["external_containment"]
    )
    for key in (
        "source_action_authority",
        "pre_white_action_evidence",
        "pre_white_authority",
        "non_reusable_action_ids",
        "human_observation_plan",
    ):
        assert embedded[key] == report_boundary[key]


def test_builder_preflight_and_compile_command_are_offline_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preflight = builder.prebuild_validate()
    assert preflight["result"] == "PASS"
    assert preflight["network_requests"] == 0
    assert preflight["relay_accessed"] is False

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
    value = builder.build(pio=pio)
    assert value["result"] == "PASS"
    assert commands == [[str(pio.resolve()), "run", "-c", builder.CONFIG]]
    assert "upload" not in commands[0]
