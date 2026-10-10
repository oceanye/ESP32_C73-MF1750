from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_raw_p16_crossover_position_balanced_once as legacy_once
from tools import mf1750_raw_p16_crossover_position_balanced_pack as legacy
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_pack as t2_v1
from tools import mf1750_raw_p16_crossover_t2_discovery_successor_v2_pack as t2_v2
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_once as t3_once,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as t3,
)
from tools import mf1750_raw_p16_crossover_w2_discovery_successor_pack as w2
from tools import (
    mf1750_raw_p16_crossover_w3_discovery_successor_v2_white_pack as w3,
)
from tools import (
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_once as w4_once,
)
from tools import (
    mf1750_raw_p16_crossover_w4_t3_ac_profile_following_successor_white_pack as w4,
)


ROOT = Path(__file__).resolve().parents[1]
BOOT_NONCE = "0123456789abcdef"


def _runner_identity(runner: Any, suffix: str) -> dict[str, Any]:
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


def _t3_review_boundary() -> dict[str, Any]:
    return {
        "source_action_authority": t3.completed_t2_v2_action_binding(),
        "pre_white_action_evidence": t3.completed_w3_white_action_binding(),
        "pre_white_authority": t3.pre_white_authority_binding(),
        "non_reusable_action_ids": list(t3.non_reusable_action_ids()),
        "human_observation_plan": deepcopy(t3.HUMAN_OBSERVATION_PLAN),
        "profile_following_review_only": True,
        "profile_following_proven": False,
        "human_primary_judgement_required": True,
        "human_observation_gate_after_every_action": True,
        "formal_gate_evaluated": False,
        "qualified_colour_count": 0,
    }


def _t3_capabilities() -> dict[str, Any]:
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


def _t3_nvs() -> dict[str, Any]:
    return {
        "namespace": t3.CONFIG.nvs_namespace,
        "key": t3.CONFIG.nvs_key,
        "encoding": "uint16 high_byte_phase low_byte_next_ordinal",
        "phases": {"READY": 0, "ARMED": 1, "CONSUMED": 2, "FAULT": 3},
        "initial_key_present": False,
        "initial_value": 1,
        "initial_next_ordinal": 1,
        "terminal_next_ordinal": 2,
        "campaign_boot_key": t3.CONFIG.nvs_boot_key,
        "campaign_boot_encoding": "uint64 high32_then_low32_hex_nonce",
        "campaign_boot_initial_key_present": False,
        "campaign_boot_initialize_only_when_cursor_key_absent_ready_ordinal1": True,
        "campaign_boot_readback_required": True,
        "current_boot_exact_match_required": True,
        "reboot_resume_allowed": False,
        "post_containment_resume_allowed": False,
    }


def _t3_layout() -> dict[str, Any]:
    return {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 4,
        "grid_columns_per_controller": 8,
        "row_codes": [list(row) for row in t3.CODE_ROWS],
        "grid_x0_local": 20,
        "grid_y_by_row": list(t3.GRID_Y_BY_ROW),
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


def _t3_responses(host: Any) -> dict[str, dict[str, Any]]:
    runner = host.base.runner
    report = t3.build_report()
    common = {
        **_t3_capabilities(),
        **_t3_review_boundary(),
    }
    version = {
        **_runner_identity(runner, "version"),
        **common,
        "layout_id": t3.CONFIG.variant_key,
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
        "nvs_contract": _t3_nvs(),
        "baseline_contract": {
            "ordinal": None,
            "role": t3.FACTORY_WHITE_ANCHOR_ROLE,
            "external_anchor_required": True,
            "one_visible_refresh_required": False,
        },
        "external_containment": report["contract"]["external_containment"],
    }
    manifest = {
        **_runner_identity(runner, "manifest"),
        **common,
        "layout_id": t3.CONFIG.variant_key,
        "actions": list(runner.ACTIONS),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "external_containment": report["contract"]["external_containment"],
        "history_layout": _t3_layout(),
    }
    status = {
        **_runner_identity(runner, "status"),
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
    }
    fresh_report = {
        **_runner_identity(runner, "report"),
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
    }
    return {
        "version": version,
        "manifest": manifest,
        "status": status,
        "report": fresh_report,
    }


def _w4_responses(host: Any) -> dict[str, dict[str, Any]]:
    identity = {
        "build_tag": host.pack.BUILD_TAG,
        "test_id": host.pack.TEST_ID,
        "campaign_id": host.pack.CAMPAIGN_ID,
        "profile_id": host.pack.PROFILE_ID,
        "environment": host.pack.ENVIRONMENT,
        "device_api_version": host.pack.DEVICE_API_VERSION,
        "identity_revision": host.pack.IDENTITY_REVISION,
        "running_app_elf_sha256": host.pack.FIRMWARE_ELF_SHA256,
        "contract_id": host.pack.CONTRACT_ID,
        "transaction_descriptor_sha256": host.pack.DESCRIPTOR_ID,
        "transaction_descriptor_marker": host.pack.DESCRIPTOR_MARKER,
    }
    return {
        "version": {
            "schema_version": 1,
            "kind": "mf1750-ec5-factory-otp-white-recovery-version",
            **identity,
            "classification": host.pack.CLASSIFICATION,
            "action_count": 1,
            "startup_refresh": False,
            "raw_ingress": False,
            "retry": False,
            "automatic_chaining": False,
            "profile_switch": False,
            "runtime_payload_present": False,
            "live_authorized": False,
        },
        "manifest": {
            "schema_version": 1,
            "kind": "mf1750-ec5-factory-otp-white-recovery-manifest",
            **identity,
            "classification": host.pack.CLASSIFICATION,
            "action_count": 1,
            "one_driver_call_per_action": True,
            "startup_refresh": False,
            "raw_frame_ingress": False,
            "raw_lut_ingress": False,
            "electrical_parameter_ingress": False,
            "timing_parameter_ingress": False,
            "runtime_payload_present": False,
            "generated_include": None,
            "runtime_psr_present": False,
            "hidden_lut_command_present": False,
            "r20_present": False,
            "r21_present": False,
            "vcom_write_or_sweep": False,
            "retry": False,
            "automatic_chaining": False,
            "automatic_recovery": False,
            "profile_switch": False,
            "requires_new_exact_authorization": True,
            "actions": [host.ACTION],
            "nvs_contract": {
                "namespace": host.pack.NVS_NAMESPACE,
                "key": host.pack.NVS_KEY,
                "initial_cursor": 1,
                "terminal_cursor": 2,
                "clear_route": False,
                "persistent_across_reboot": True,
            },
        },
        "status": {
            "schema_version": 1,
            "kind": "mf1750-ec5-factory-otp-white-recovery-status",
            **identity,
            "boot_nonce": BOOT_NONCE,
            "state": "ready",
            "phase": 0,
            "phase_name": "READY",
            "cursor_raw": 1,
            "next_ordinal": 1,
            "campaign_complete": False,
            "cursor_valid": True,
            "persistent_key_present": False,
            "fixture_self_check_passed": True,
            "execute_pending": False,
            "arm_request_count": 0,
            "execute_request_count": 0,
            "total_driver_call_count": 0,
            "gpio_initialized": True,
            "busy": 0,
            "rst": 0,
            "cs": 0,
            "cs2": 0,
            "sck": 0,
            "dc": 0,
            "mosi": 0,
        },
        "report": {
            "schema_version": 1,
            "kind": "mf1750-ec5-factory-otp-white-recovery-report",
            **identity,
            "valid": False,
            "terminal_state": "NOT_EXECUTED",
            "result": False,
            "driver_called": False,
            "driver_call_count_for_action": 0,
            "no_retry": True,
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


def _identity_values(report: Mapping[str, Any], *, white: bool) -> set[str]:
    action = report["action"] if white else report["actions"][0]
    contract = report["contract"]
    keys = (
        "campaign_id",
        "test_id",
        "base_route",
        "nvs_namespace",
        "nvs_key",
        "nvs_boot_key",
    )
    values = {
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
    }
    values.update(str(contract[key]) for key in keys if key in contract)
    return values


def test_fresh_t3_w4_identities_routes_nvs_claims_and_outputs_are_isolated() -> None:
    old_atlas = [legacy.build_report(stage) for stage in legacy.STAGES]
    old_atlas.extend((t2_v1.build_report(), t2_v2.build_report()))
    old_white = [legacy.build_white_report(stage) for stage in legacy.WHITES]
    old_white.extend((w2.build_white_report(), w3.build_white_report()))
    old_values: set[str] = set()
    for report in old_atlas:
        old_values.update(_identity_values(report, white=False))
    for report in old_white:
        old_values.update(_identity_values(report, white=True))

    t3_report = t3.build_report()
    w4_report = w4.build_white_report()
    t3_values = _identity_values(t3_report, white=False)
    w4_values = _identity_values(w4_report, white=True)
    assert not (t3_values & old_values)
    assert not (w4_values & (old_values | t3_values))

    fresh_paths = {
        t3_once._claim_root().resolve(),  # noqa: SLF001
        t3_once._output_root().resolve(),  # noqa: SLF001
        w4_once._claim_root().resolve(),  # noqa: SLF001
        w4_once._output_root().resolve(),  # noqa: SLF001
    }
    assert len(fresh_paths) == 4
    old_paths = {
        *(
            legacy_once._atlas_claim_root(config).resolve()  # noqa: SLF001
            for config in legacy.STAGES.values()
        ),
        *(
            legacy_once._white_claim_root(config).resolve()  # noqa: SLF001
            for config in legacy.WHITES.values()
        ),
    }
    assert not (fresh_paths & old_paths)


def test_legacy_t3_mutating_cli_is_tombstoned_before_configure_request_or_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def forbidden(_stage: str) -> object:
        events.append("configure")
        raise AssertionError("legacy T3 reached configuration")

    monkeypatch.setattr(legacy_once, "_configure_atlas", forbidden)
    result = legacy_once.main(
        [
            "run-atlas",
            "--stage",
            "t3-ac-repeat",
            "--base-url",
            "http://192.168.1.11",
            "--confirm-j2-on",
            "--confirm-external-pre-white",
        ]
    )
    assert result == 2
    assert events == []
    assert legacy_once.LEGACY_T3_TOMBSTONED_ACTION_ID in t3.non_reusable_action_ids()


def test_t3_real_wire_shape_positive_and_negative_gates() -> None:
    host = t3_once.configure()
    responses = _t3_responses(host)
    host._validate_version(responses["version"])  # noqa: SLF001
    host._validate_manifest(responses["manifest"])  # noqa: SLF001

    stale_version = deepcopy(responses["version"])
    stale_version["contract_id"] = "0" * 64
    with pytest.raises(host.base.runner.RecheckError, match="contract_id"):
        host._validate_version(stale_version)  # noqa: SLF001

    stale_manifest = deepcopy(responses["manifest"])
    stale_manifest["actions"][0]["action_id"] = t3.non_reusable_action_ids()[0]
    with pytest.raises(host.base.runner.RecheckError, match="manifest actions"):
        host._validate_manifest(stale_manifest)  # noqa: SLF001


def test_t3_fake_j2_off_is_four_get_zero_side_effect_and_oxcl(tmp_path: Path) -> None:
    host = t3_once.configure()
    fake = _ReadOnlyDevice(_t3_responses(host))
    output = tmp_path / "t3" / "j2-off-diagnostic.json"
    claims = tmp_path / "t3" / "claims"
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
    assert json.loads(output.read_text(encoding="utf-8"))["outcome"] == (
        "j2_off_diagnostic_pass"
    )

    calls = list(fake.calls)
    with pytest.raises(host.base.runner.RecheckError, match="overwrite"):
        host.diagnose_j2_off(
            "http://192.168.1.11",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert fake.calls == calls


def test_w4_exact_source_quartet_and_real_manifest_negative_gate() -> None:
    report = w4.build_white_report()
    source = t3.build_report()
    source_action = source["actions"][0]
    action = report["action"]
    assert (
        action["source_campaign_id"],
        action["source_contract_id"],
        action["source_descriptor_id"],
        action["source_action_id"],
    ) == (
        source["contract"]["campaign_id"],
        source["contract_id"],
        source_action["descriptor_id"],
        source_action["action_id"],
    )

    host = w4_once._configure_white()  # noqa: SLF001
    responses = _w4_responses(host)
    running_sha = host.base._validate_version(responses["version"])  # noqa: SLF001
    host.base._base._validate_manifest(  # noqa: SLF001
        responses["manifest"], running_sha
    )
    stale = deepcopy(responses["manifest"])
    stale["actions"][0]["source_action_id"] = "0" * 64
    with pytest.raises(host.ContainmentError, match="manifest"):
        host.base._base._validate_manifest(stale, running_sha)  # noqa: SLF001


def test_w4_fake_j2_off_is_four_get_zero_side_effect_and_oxcl(tmp_path: Path) -> None:
    host = w4_once._configure_white()  # noqa: SLF001
    fake = _ReadOnlyDevice(_w4_responses(host))
    output = tmp_path / "w4" / "j2-off-diagnostic.json"
    claims = tmp_path / "w4" / "claims"
    host.DEFAULT_CLAIMS = claims
    host.base.DEFAULT_CLAIMS = claims

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
    assert value["visible_refreshes"] == 0
    assert value["output_write_contract"] == "O_EXCL"
    assert not claims.exists()

    calls = list(fake.calls)
    with pytest.raises(host.ContainmentError, match="overwrite"):
        host.diagnose_j2_off(
            "http://192.168.1.11",
            output=output,
            confirm_j2_off=True,
            requester=fake,
        )
    assert fake.calls == calls


def test_t3_w4_platformio_configs_have_no_upload_surface() -> None:
    for relative in (
        "platformio.raw_p16_crossover_t3_ac_profile_following_successor_v1.ini",
        "platformio.raw_p16_crossover_w4_t3_ac_profile_following_successor_white_v1.ini",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8").lower()
        assert "upload_protocol" not in text
        assert "upload_command" not in text
        assert "targets = upload" not in text
        assert "upload_port" not in text
