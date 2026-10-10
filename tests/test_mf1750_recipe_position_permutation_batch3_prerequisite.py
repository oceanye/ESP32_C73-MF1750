from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools import mf1750_recipe_position_permutation_batch3_prerequisite as gate
from tools import mf1750_recipe_position_permutation_evidence_bundle as batch2


def _sha(number: int) -> str:
    return f"{number:064x}"


def _sealed_root() -> dict[str, object]:
    settings = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
    }
    signature = {
        "camera_id": "camera-1",
        "instance_id": "instance-1",
        "index": 0,
        "backend": "DSHOW",
        "mount_id": "fixed-mount-1",
        "requested_settings": settings,
        "effective_settings": settings,
    }
    actions: list[dict[str, object]] = []
    captures: list[dict[str, object]] = []
    for ordinal, (expected, compiled) in enumerate(
        zip(
            batch2.once.base.runner.ACTIONS,
            batch2.pack.build_report()["actions"],
            strict=True,
        ),
        1,
    ):
        actions.append(
            {
                "ordinal": ordinal,
                "path": f"action-{ordinal}.json",
                "file_sha256": _sha(ordinal),
                "canonical_integrity_sha256": _sha(10 + ordinal),
                "created_at": f"2026-08-28T10:0{ordinal}:00+08:00",
                "action_id": expected["action_id"],
                "descriptor_id": expected["descriptor_id"],
                "role": expected["role"],
                "outcome": "complete_pass",
                "visible_refreshes": 1,
                "frame_sha256": compiled["frame"]["sha256"],
                "frame_fnv1a": compiled["frame"]["fnv1a"],
                "cs1_dtm_sha256": compiled["cs1_dtm"]["sha256"],
                "cs2_dtm_sha256": compiled["cs2_dtm"]["sha256"],
                "global_header": compiled["global_header"],
                "global_header_sha256": compiled["global_header_sha256"],
                "cs1_r20_prefix_sha256": compiled["cs1_r20_prefix_sha256"],
                "cs2_r20_prefix_sha256": compiled["cs2_r20_prefix_sha256"],
                "r21_sha256": compiled["r21_sha256"],
            }
        )
        captures.append(
            {
                "ordinal": ordinal,
                "path": f"capture-{ordinal}.json",
                "sidecar_file_sha256": _sha(20 + ordinal),
                "canonical_integrity_sha256": _sha(30 + ordinal),
                "capture_id": _sha(40 + ordinal),
                "captured_at": f"2026-08-28T10:0{ordinal}:30+08:00",
                "action_id": expected["action_id"],
                "descriptor_id": expected["descriptor_id"],
                "action_result_sha256": _sha(ordinal),
                "photo_sha256": _sha(50 + ordinal),
                "capture_binding": "live_synchronized",
                "coverage_scope": "full_panel",
            }
        )
    noise = {
        "path": "repeat-noise.json",
        "file_sha256": _sha(60),
        "canonical_integrity_sha256": _sha(61),
        "baseline_id": _sha(62),
        "reference_geometry_sha256": _sha(63),
        "capture_count": 3,
        "repeat_noise_p95_de76": 1.25,
        "camera_signature": signature,
    }
    terminal_evidence = {
        "ordinal": 4,
        "action_result_file_sha256": actions[3]["file_sha256"],
        "action_result_canonical_integrity_sha256": actions[3][
            "canonical_integrity_sha256"
        ],
        "capture_sidecar_file_sha256": captures[3]["sidecar_file_sha256"],
        "capture_canonical_integrity_sha256": captures[3]["canonical_integrity_sha256"],
        "capture_id": captures[3]["capture_id"],
        "captured_at": captures[3]["captured_at"],
        "photo_sha256": captures[3]["photo_sha256"],
        "white_gate_file_sha256": _sha(64),
        "white_gate_canonical_integrity_sha256": _sha(65),
        "white_gate_analysis_id": _sha(66),
        "reference_geometry_sha256": _sha(63),
        "repeat_noise_p95_de76": 1.25,
        "patch_count": 60,
        "campaign_boot_nonce": "batch2-boot",
    }
    terminal = {
        "prerequisite_id": hashlib.sha256(
            gate._canonical_json(terminal_evidence)  # noqa: SLF001
        ).hexdigest(),
        "eligible": True,
        **terminal_evidence,
        "classification_state": "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH",
        "terminal_is_latest_bound_batch2_capture": True,
        "external_refresh_after_terminal_capture_not_proven": True,
        "batch3_binding_contract": {
            "bind_bundle_kind": gate.KIND,
            "bind_bundle_schema_version": gate.SCHEMA_VERSION,
            "bind_bundle_id": "bundle_id",
            "bind_bundle_file_sha256": "whole bundle file bytes",
            "bind_bundle_canonical_integrity_sha256": "integrity.sha256",
            "bind_prerequisite_id": ("terminal_white_prerequisite.prerequisite_id"),
            "require_eligible_true": True,
            "deep_verify_terminal_subobject": True,
        },
    }
    input_hashes = {
        "actions": [item["file_sha256"] for item in actions],
        "captures": [item["sidecar_file_sha256"] for item in captures],
        "repeat_noise": noise["file_sha256"],
        "g1_anchor": _sha(67),
        "p1_grid": _sha(68),
        "comparison": _sha(69),
        "terminal_white_gate": terminal["white_gate_file_sha256"],
    }
    root: dict[str, object] = {
        "schema_version": gate.SCHEMA_VERSION,
        "kind": gate.KIND,
        "bundle_id": hashlib.sha256(
            gate._canonical_json({"kind": gate.KIND, "inputs": input_hashes})  # noqa: SLF001
        ).hexdigest(),
        "campaign_identity": {
            "campaign_id": batch2.pack.CAMPAIGN_ID,
            "test_id": batch2.pack.TEST_ID,
            "layout_id": batch2.P1_LAYOUT_ID,
            "contract_id": batch2.once.base.runner.CONTRACT_ID,
            "firmware_sha256": batch2.once.FIRMWARE_SHA256,
            "firmware_bytes": batch2.once.FIRMWARE_BYTES,
            "campaign_boot_nonce": "batch2-boot",
            "action_ids": list(batch2.once.base.runner.ACTION_IDS),
            "action_count": 4,
            "visible_refresh_count": 4,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        },
        "action_results": actions,
        "captures": captures,
        "p0_g_minus_1_anchor": {"file_sha256": _sha(67)},
        "p1_ordinal3_grid_analysis": {"file_sha256": _sha(68)},
        "recipe_comparison": {"file_sha256": _sha(69)},
        "terminal_white_prerequisite": terminal,
        "shared_camera_lock": {
            **signature,
            "photo_width": 1920,
            "photo_height": 1080,
            "manual_controls_required": dict(batch2.REQUIRED_MANUAL_CAMERA_SETTINGS),
            "g1_and_all_four_live_captures_same_signature": True,
            "all_effective_before_after_readbacks_equal": True,
            "all_four_live_captures_same_boot": True,
            "strictly_increasing_action_and_capture_timeline": True,
            "g1_captured_at": "2026-08-28T09:00:00+08:00",
            "live_capture_times": [item["captured_at"] for item in captures],
        },
        "shared_analysis_bindings": {
            "repeat_noise_baseline": noise,
            "reference_geometry_sha256": _sha(63),
            "repeat_noise_p95_de76": 1.25,
            "p0_grid_from_g1_anchor_file_sha256": _sha(70),
            "p0_grid_from_g1_anchor_canonical_integrity_sha256": _sha(71),
            "p1_grid_file_sha256": _sha(72),
            "p1_grid_canonical_integrity_sha256": _sha(73),
            "comparison_binds_exact_g1_p0_and_ordinal3_p1": True,
            "terminal_white_gate_binds_ordinal4_photo": True,
            "terminal_white_gate_binds_repeat_noise_geometry": True,
        },
        "classification": {
            "state": "NO_RECIPE_LINKED_EXPLORATORY_EFFECT",
            "recipe_comparison_state": "NO_RECIPE_LINKED_CANDIDATE",
            "recipe_linked_controller_count": 0,
            "recipe_linked_exploratory_only": True,
            "qualified_new_colour": False,
            "qualified_brightness_level": False,
            "absolute_colour_proven": False,
        },
        "evidence_boundaries": {
            "g1_is_zero_refresh_retrospective_geometry_and_p0_anchor_only": True,
            "g1_is_not_live_action_evidence": True,
            "camera_relative_only": True,
            "recipe_linkage_is_exploratory": True,
            "one_permutation_cannot_qualify_a_new_colour": True,
            "absolute_colour_or_new_colour_not_proven": True,
            "compiled_payload_identity_not_bus_capture": True,
            "all_four_batch2_captures_live_synchronized_and_full_panel": True,
            "external_refresh_after_terminal_capture_not_proven": True,
            "device_io_performed_by_bundle_builder": False,
        },
        "output_write_contract": "O_EXCL",
    }
    root["integrity"] = {
        "algorithm": batch2.INTEGRITY_ALGORITHM,
        "sha256": hashlib.sha256(gate._canonical_json(root)).hexdigest(),  # noqa: SLF001
    }
    return root


def _write(path: Path, root: dict[str, object]) -> None:
    path.write_text(json.dumps(root, sort_keys=True), encoding="utf-8")


def _reseal(root: dict[str, object]) -> None:
    root.pop("integrity", None)
    root["integrity"] = {
        "algorithm": batch2.INTEGRITY_ALGORITHM,
        "sha256": hashlib.sha256(gate._canonical_json(root)).hexdigest(),  # noqa: SLF001
    }


def test_deep_valid_batch2_terminal_white_prerequisite(tmp_path: Path) -> None:
    path = tmp_path / "batch2.json"
    root = _sealed_root()
    _write(path, root)
    observed, binding = gate.validate(path)
    assert observed["bundle_id"] == binding["bundle_id"]
    assert binding["file_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert binding["terminal_white_prerequisite"]["eligible"] is True
    assert binding["shared_analysis_bindings"]["repeat_noise_p95_de76"] == 1.25


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda root: root["terminal_white_prerequisite"].__setitem__(
                "photo_sha256", _sha(99)
            ),
            "prerequisite|terminal",
        ),
        (
            lambda root: root["shared_camera_lock"]["effective_settings"].__setitem__(
                "auto_white_balance", 1.0
            ),
            "white balance|camera",
        ),
        (
            lambda root: root.__setitem__("bundle_id", _sha(98)),
            "bundle_id",
        ),
    ],
)
def test_resealed_internal_tamper_is_rejected(
    tmp_path: Path, mutation: object, message: str
) -> None:
    root = _sealed_root()
    mutation(root)
    _reseal(root)
    path = tmp_path / "batch2.json"
    _write(path, root)
    with pytest.raises(gate.Batch3PrerequisiteError, match=message):
        gate.validate(path)
