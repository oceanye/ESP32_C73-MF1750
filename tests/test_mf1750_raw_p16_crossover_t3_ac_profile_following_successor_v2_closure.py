from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_once as v1_once,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as v1,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_build as builder,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_pack as pack,
)


ROOT = Path(__file__).resolve().parents[1]
BOOT_NONCE = "0123456789abcdef"


def _identity(runner: Any, suffix: str) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "kind": f"{runner.DEVICE_KIND_PREFIX}-{suffix}",
        "build_tag": runner.BUILD_TAG,
        "test_id": runner.TEST_ID,
        "campaign_id": runner.CAMPAIGN_ID,
        "device_api_version": runner.DEVICE_API_VERSION,
        "identity_revision": runner.IDENTITY_REVISION,
        "contract_id": runner.CONTRACT_ID,
        "classification": runner.CLASSIFICATION,
    }


def _capabilities() -> dict[str, Any]:
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


def _review_boundary() -> dict[str, Any]:
    return {
        "source_action_authority": pack.completed_t2_v2_action_binding(),
        "pre_white_action_evidence": pack.completed_w3_white_action_binding(),
        "pre_white_authority": pack.pre_white_authority_binding(),
        "v1_terminal_failure_authority": pack.v1_failure_authority_binding(),
        "address_resolution_boundary": pack.address_resolution_boundary_binding(),
        "non_reusable_action_ids": list(pack.non_reusable_action_ids()),
        "human_observation_plan": deepcopy(pack.HUMAN_OBSERVATION_PLAN),
        "profile_following_review_only": True,
        "profile_following_proven": False,
        "human_primary_judgement_required": True,
        "human_observation_gate_after_every_action": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
    }


def _nvs_contract() -> dict[str, Any]:
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


def _layout() -> dict[str, Any]:
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


def _responses(host: Any) -> dict[str, dict[str, Any]]:
    runner = host.base.runner
    report = pack.build_report()
    common = {**_capabilities(), **_review_boundary()}
    return {
        "version": {
            **_identity(runner, "version"),
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
        },
        "manifest": {
            **_identity(runner, "manifest"),
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
        },
        "status": {
            **_identity(runner, "status"),
            "boot_nonce": BOOT_NONCE,
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
            "busy": 0,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "execute_pending": False,
            "persistent_key_present": False,
            "campaign_boot_key_present": True,
            "persisted_campaign_boot_nonce": BOOT_NONCE,
            "campaign_boot_matches_current": True,
            "device_enforced_same_boot": True,
            "reboot_resume_allowed": False,
            "post_containment_resume_allowed": False,
            "arm_request_count": 0,
            "execute_request_count": 0,
            "total_driver_call_count": 0,
        },
        "report": {
            **_identity(runner, "report"),
            "boot_nonce": BOOT_NONCE,
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
        },
    }


class _ReadOnlyDevice:
    def __init__(self, responses: Mapping[str, Mapping[str, Any]]) -> None:
        self.responses = deepcopy(dict(responses))
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self,
        _base_url: str,
        path: str,
        *,
        method: str,
        headers: object,
        timeout: float,
    ) -> tuple[int, dict[str, Any]]:
        assert timeout > 0
        assert headers is None
        endpoint = path.rsplit("/", 1)[-1]
        self.calls.append((method, endpoint))
        if method != "GET":
            raise AssertionError("J2-OFF diagnostic attempted a mutation")
        return 200, deepcopy(self.responses[endpoint])


def test_v1_terminal_failure_and_passive_address_evidence_are_exact() -> None:
    failure = pack.validate_v1_failure_authority()
    address = pack.validate_address_resolution_boundary()
    binding = failure["binding"]
    assert failure["action_output_absent"] is True
    assert failure["claim_absent"] is True
    assert binding["failed_diagnostic_evidence"]["network_get"] == 1
    assert binding["failed_diagnostic_evidence"]["network_post"] == 0
    assert binding["failed_diagnostic_evidence"]["visible_refreshes"] == 0
    assert binding["final_relay_off_evidence"]["off_gate_passed"] is True
    assert binding["final_relay_off_evidence"]["electrical_state_proven"] is False
    assert binding["does_not_reauthorize_v1"] is True
    assert address["passive_only"] is True
    assert address["freshness_proven"] is False
    assert address["device_application_identity_proven"] is False
    assert pack.address_resolution_boundary_binding()["candidate_is_default_base_url"] is False


def test_v2_preserves_payload_but_all_mutation_identities_are_fresh() -> None:
    report = pack.build_report()
    old = v1.build_report()
    action = report["actions"][0]
    old_action = old["actions"][0]
    for key in ("frame", "cs1_dtm", "cs2_dtm", "waveform_binding", "profile_id"):
        assert action[key] == old_action[key]
    assert action["prior_static_action_id"] == old_action["prior_static_action_id"]
    assert action["supersedes_failed_unmutated_v1_action_id"] == old_action["action_id"]
    assert len(pack.non_reusable_action_ids()) == 11
    assert pack.non_reusable_action_ids()[-1] == old_action["action_id"]
    assert action["action_id"] not in pack.non_reusable_action_ids()
    for old_value, fresh_value in (
        (old["contract_id"], report["contract_id"]),
        (old_action["descriptor_id"], action["descriptor_id"]),
        (old_action["action_id"], action["action_id"]),
        (old["contract"]["campaign_id"], report["contract"]["campaign_id"]),
        (old["contract"]["base_route"], report["contract"]["base_route"]),
        (old["contract"]["nvs_namespace"], report["contract"]["nvs_namespace"]),
    ):
        assert fresh_value != old_value


def test_v2_wire_boundary_and_fake_four_get_diagnostic_are_closed(tmp_path: Path) -> None:
    host = once.configure()
    responses = _responses(host)
    host._validate_version(responses["version"])  # noqa: SLF001
    host._validate_manifest(responses["manifest"])  # noqa: SLF001

    stale = deepcopy(responses["version"])
    stale["address_resolution_boundary"]["fresh_binding_proven"] = True
    with pytest.raises(host.base.runner.RecheckError, match="address_resolution"):
        host._validate_version(stale)  # noqa: SLF001

    fake = _ReadOnlyDevice(responses)
    output = tmp_path / "diagnostic.json"
    claims = tmp_path / "claims"
    host.DEFAULT_CLAIMS = claims
    host.base.runner.DEFAULT_CLAIMS = claims
    value = host.diagnose_j2_off(
        "http://192.168.1.11",
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
    assert value["network"] == {"get": 4, "post": 0}
    assert value["permanent_claims_created"] == 0
    assert value["claims_directory_accessed"] is False
    assert value["visible_refreshes"] == 0
    assert value["output_write_contract"] == "O_EXCL"
    assert not claims.exists()
    calls = list(fake.calls)
    with pytest.raises(host.base.runner.RecheckError, match="overwrite"):
        host.diagnose_j2_off(
            "http://192.168.1.11",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert fake.calls == calls


def test_v2_source_selector_ini_roots_and_artifacts_are_exact() -> None:
    report = pack.build_report()
    action = report["actions"][0]
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_t3_ac_profile_following_successor_v2_identity.inc"
    ).read_text(encoding="utf-8")
    selector = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_identity.inc"
    ).read_text(encoding="utf-8")
    main_config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    ini = (
        ROOT / "platformio.raw_p16_crossover_t3_ac_profile_following_successor_v2.ini"
    ).read_text(encoding="utf-8")
    for value in (
        pack.CONFIG.campaign_id,
        pack.CONFIG.test_id,
        pack.CONFIG.build_tag,
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        pack.CONFIG.nvs_namespace,
        pack.CONFIG.nvs_key,
        pack.CONFIG.nvs_boot_key,
        action["profile_id"],
        action["global_tuple_id"],
    ):
        assert value in identity
    v2_include = "ec5_raw_p16_crossover_t3_ac_profile_following_successor_v2_identity.inc"
    assert selector.index(v2_include) < selector.index(
        "ec5_raw_p16_crossover_t3_ac_profile_following_successor_identity.inc"
    )
    for value in (
        pack.CONFIG.base_route,
        v1.build_report()["actions"][0]["action_id"],
        pack.V1_FLASH_FILE_SHA256,
        pack.V1_DIAGNOSTIC_FILE_SHA256,
        pack.V1_RELAY_OFF_FILE_SHA256,
        pack.PASSIVE_ADDRESS_EVIDENCE_FILE_SHA256,
        pack.PASSIVE_CANDIDATE_MAC,
    ):
        assert value in main_config
    assert "fresh_binding_proven\\\":false" in main_config
    assert "device_application_identity_proven\\\":false" in main_config
    assert "electrical_state_proven\\\":false" in main_config
    assert (
        "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2_BUILD=1"
        in ini
    )
    assert "upload_protocol" not in ini
    assert "upload_command" not in ini

    validation = once.dry_validate()
    assert validation["result"] == "PASS"
    assert validation["default_base_url"] is None
    assert validation["explicit_base_url_required_for_live_cli"] is True
    assert validation["default_evidence_root"].endswith(
        "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2"
    )
    assert validation["claim_root"].endswith(
        ".mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_claims"
    )
    once_source = (
        ROOT / "tools/mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_once.py"
    ).read_text(encoding="utf-8")
    assert "192.168.1.7" not in once_source
    assert "192.168.1.11" not in once_source
    for item in once._artifact_binding().values():  # noqa: SLF001
        payload = Path(item["path"]).read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


@pytest.mark.parametrize(
    "argv",
    (
        ["diagnose-j2-off", "--confirm-j2-off"],
        ["run", "--confirm-j2-on", "--confirm-external-pre-white"],
    ),
)
def test_v2_live_cli_has_no_default_base_url(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        once._parse_args(argv)  # noqa: SLF001


@pytest.mark.parametrize(
    "argv",
    (
        [
            "diagnose-j2-off",
            "--base-url",
            "http://192.168.1.11",
            "--confirm-j2-off",
        ],
        [
            "run",
            "--base-url",
            "http://192.168.1.11",
            "--confirm-j2-on",
            "--confirm-external-pre-white",
        ],
    ),
)
def test_v1_live_cli_is_tombstoned_before_configure(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    monkeypatch.setattr(v1_once, "configure", lambda: events.append("configured"))
    assert v1_once.main(argv) == 2
    assert events == []


def test_builder_issues_compile_only_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    assert commands == [[str(pio.resolve()), "run", "-c", builder.CONFIG]]
    assert "upload" not in commands[0]
