from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_once as once
from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_pack as pack


def _identity(kind: str) -> dict[str, object]:
    return {
        "kind": f"mf1750-ec5-p1-active-endpoint-atlas-4x8-v1-{kind}",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": pack.DEVICE_API_VERSION,
        "identity_revision": pack.IDENTITY_REVISION,
        "contract_id": once.REPORT["contract_id"],
        "classification": pack.CLASSIFICATION,
    }


def _capabilities() -> dict[str, bool]:
    value = {
        key: True
        for key in (
            "full_screen_global_refresh",
            "fresh_one_shot_endpoint_atlas",
            "complete_profile_tuple",
            "position_balanced_atlas",
            "busy_qualified_arm_execute_dispatch",
            "device_enforced_same_boot",
        )
    }
    value.update(
        {
            key: False
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
                "colour_qualification",
                "lightness_qualification",
                "history_sequence",
                "identical_target_repeat",
                "main_campaign_resume_after_containment",
            )
        }
    )
    return value


def _manifest() -> dict[str, object]:
    value: dict[str, object] = {
        **_identity("manifest"),
        "layout_id": pack.VARIANT_KEY,
        "actions": list(once.base.runner.ACTIONS),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
        "external_containment": once.REPORT["contract"]["external_containment"],
        "history_layout": {
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
            "cs2_position_mirrored": False,
            "spatial_dither": False,
            "fresh_one_shot": True,
            "source_history_actions": 0,
            "middle_history_actions": 0,
            "identical_target_repeat_actions": 0,
            "factory_otp_white_ordinals": [],
            "runtime_lut_ordinals": [1],
            "one_visible_refresh_per_action": True,
            "samples_per_code_per_controller_per_frame": 4,
            "qualified_colours": 0,
            "qualified_lightness_levels": 0,
            "active_global_tuple_id": once.REPORT["contract"]["profile"][
                "global_tuple_id"
            ],
        },
        **_capabilities(),
    }
    return value


def _complete_report() -> dict[str, object]:
    action = once.base.runner.ACTIONS[0]
    source = once.REPORT["actions"][0]
    return {
        **_identity("report"),
        "boot_nonce": "0123456789abcdef",
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "ordinal": 1,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": 2,
        "campaign_complete": True,
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
            "timeout_stage": "none",
            "busy_missing_stage": "none",
            "pre_command_busy_stage": "none",
            "spi_hz": 1_000_000,
            "operation_id": 1,
            "pon_busy_seen": True,
            "drf_busy_seen": True,
            "pof_busy_seen": True,
            "input_fnv1a": source["frame"]["fnv1a"],
            "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
            "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
            "pon_ms": 1,
            "drf_ms": 2,
            "pof_ms": 3,
            "safe_finish": {
                "busy_before_pins_low": 1,
                "busy_after_pins_low": 1,
                "busy_after_5ms": 1,
                "final_gpio": {"busy": 1, "rst": 0, "cs": 0, "cs2": 0},
            },
        },
    }


def test_pack_is_one_refresh_both_active_and_position_balanced() -> None:
    report = pack.build_report()
    contract = report["contract"]
    profile = contract["profile"]
    flat = [code for row in pack.CODE_ROWS for code in row]

    assert contract["action_count"] == 1
    assert contract["one_visible_refresh_per_action"] is True
    assert contract["fresh_one_shot"] is True
    assert contract["source_history_actions"] == 0
    assert contract["middle_history_actions"] == 0
    assert contract["identical_target_repeat_actions"] == 0
    assert contract["partial_refresh"] is False
    assert contract["local_hold_claimed"] is False
    assert contract["retry"] is False
    assert contract["recovery"] is False
    assert contract["automatic_chaining"] is False
    assert sorted(flat) == [code for code in range(8) for _ in range(4)]
    assert profile["complete_profile_tuple"] is True
    assert profile["cs1"] == profile["cs2"]
    assert profile["controller_payloads_byte_identical"] is True
    assert report["actions"][0]["cs1_dtm"] == report["actions"][0]["cs2_dtm"]


def test_source_white_authority_is_exactly_bound() -> None:
    authority = once.validate_source_white_authority()
    assert authority["sealed"] is True
    assert authority["source_action_id"] == once.SOURCE_WHITE_ACTION_ID
    assert authority["source_review_id"] == once.SOURCE_REVIEW_ID
    assert (
        authority["live_no_intervening_visible_refresh_confirmation_required"] is True
    )
    assert set(authority["files"]) == {
        "source_terminal_gate",
        "white_action",
        "clean_white_review",
        "relay_off",
    }


def test_exact_binding_is_one_candidate_no_device_api() -> None:
    path = once.SOURCE_ROOT / "exact-ipv4-mac-binding.json"
    result = once.validate_exact_ipv4_mac_binding(
        path, f"http://{once.EXPECTED_DEVICE_IPV4}"
    )
    assert result["outcome"] == "active_exact_mac_binding_pass"
    assert result["candidate_ipv4"] == "192.168.1.11"
    assert result["expected_mac"] == "A4-CB-8F-D9-FC-D4"
    assert result["fresh_binding_passed"] is True
    assert result["device_api_requests"] == 0
    assert result["mutation_requests"] == 0
    assert result["visible_refresh_requests"] == 0


def test_manifest_accepts_only_new_row_layout_and_four_samples() -> None:
    manifest = _manifest()
    once._validate_manifest(manifest)

    bad = deepcopy(manifest)
    bad["history_layout"]["row_codes"] = [  # type: ignore[index]
        [0, 1, 2, 3, 4, 5, 6, 7]
    ] * 4
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_manifest(bad)

    bad = deepcopy(manifest)
    bad["history_layout"][  # type: ignore[index]
        "samples_per_code_per_controller_per_frame"
    ] = 12
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_manifest(bad)


def test_complete_report_requires_one_driver_and_safe_finish() -> None:
    report = _complete_report()
    once._validate_complete_report(report, 1, "0123456789abcdef")

    bad = deepcopy(report)
    bad["driver_call_count_for_action"] = 2
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_complete_report(bad, 1, "0123456789abcdef")

    bad = deepcopy(report)
    bad["driver"]["safe_finish"]["busy_after_5ms"] = 0  # type: ignore[index]
    with pytest.raises(once.base.runner.RecheckError):
        once._validate_complete_report(bad, 1, "0123456789abcdef")


@pytest.mark.parametrize(
    ("j2", "source", "no_refresh"),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ],
)
def test_live_confirmations_fail_before_request_or_claim(
    j2: bool, source: bool, no_refresh: bool, tmp_path: Path
) -> None:
    calls = 0

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("requester must not be reached")

    missing_binding = tmp_path / "must-not-be-read.json"
    with pytest.raises(once.base.runner.RecheckError):
        once.run_once(
            f"http://{once.EXPECTED_DEVICE_IPV4}",
            1,
            claims=once.base.runner.DEFAULT_CLAIMS,
            output=once.ACTION_OUTPUTS[1],
            exact_ipv4_mac_binding=missing_binding,
            requester=requester,
            confirm_j2_on=j2,
            confirm_source_v3_clean_white=source,
            confirm_no_intervening_visible_refresh=no_refresh,
        )
    assert calls == 0
    assert not missing_binding.exists()


def test_tampered_binding_is_rejected_offline(tmp_path: Path) -> None:
    source = once.SOURCE_ROOT / "exact-ipv4-mac-binding.json"
    value = json.loads(source.read_text(encoding="utf-8"))
    value["candidate_ipv4"] = "192.168.1.12"
    path = tmp_path / "tampered-binding.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(once.base.runner.RecheckError):
        once.validate_exact_ipv4_mac_binding(
            path, f"http://{once.EXPECTED_DEVICE_IPV4}"
        )


def test_dry_validation_verifies_final_artifacts_without_io() -> None:
    result = once.dry_validate(verify_artifacts=True)
    assert result["result"] == "PASS"
    assert result["artifacts_verified"] is True
    assert result["network_requests"] == 0
    assert result["display_refreshed"] is False
    assert result["visible_refreshes_per_action"] == 1


def test_cli_forwards_all_live_gates_including_j2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(base_url: str, ordinal: int, **kwargs: object) -> dict[str, bool]:
        observed.update({"base_url": base_url, "ordinal": ordinal, **kwargs})
        return {"ok": True}

    monkeypatch.setattr(once, "run_once", fake_run)
    code = once.main(
        [
            "run",
            "--base-url",
            "http://192.168.1.11",
            "--ordinal",
            "1",
            "--exact-ipv4-mac-binding",
            "unused.json",
            "--confirm-j2-on",
            "--confirm-source-v3-clean-white",
            "--confirm-no-intervening-visible-refresh",
        ]
    )
    assert code == 0
    assert observed["confirm_j2_on"] is True
    assert observed["confirm_source_v3_clean_white"] is True
    assert observed["confirm_no_intervening_visible_refresh"] is True
