from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_factory_white_reference_photo_gate as white_gate
from tools import mf1750_runtime_lut_same_r20_parity_v1_once as same_once
from tools import mf1750_runtime_lut_true_r20_partial_hold_v1_once as true_once
from tools import mf1750_same_r20_atlas_photo_analyzer as atlas
from tools import mf1750_same_r20_parity_evidence_bundle as bundle


def _seal(value: dict) -> dict:
    value = dict(value)
    value["integrity"] = {
        "algorithm": bundle.INTEGRITY_ALGORITHM,
        "sha256": bundle._sha256_bytes(bundle._canonical_json(value)),
    }
    return value


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _action(path: Path, ordinal: int) -> Path:
    action = same_once.base.runner.ACTIONS[ordinal - 1]
    return _write(
        path,
        _seal(
            {
                "schema_version": 1,
                "kind": bundle.ACTION_RESULT_KIND,
                "outcome": "complete_pass",
                "firmware_sha256": same_once.FIRMWARE_SHA256,
                "no_autochain": True,
                "no_retry": True,
                "no_recovery": True,
                "action": {
                    "ordinal": ordinal,
                    "action_id": action["action_id"],
                    "descriptor_id": action["descriptor_id"],
                },
                "terminal_report": {
                    "campaign_id": same_once.pack.CAMPAIGN_ID,
                    "contract_id": same_once.base.runner.CONTRACT_ID,
                    "action_id": action["action_id"],
                    "descriptor_id": action["descriptor_id"],
                    "driver_call_count_for_action": 1,
                    "driver_called": True,
                },
            }
        ),
    )


def _atlas(path: Path, role: str, *, passed: bool = True) -> Path:
    return _write(
        path,
        _seal(
            {
                "schema_version": atlas.SCHEMA_VERSION,
                "kind": atlas.KIND,
                "role": role,
                "layout": {"id": atlas.LAYOUT_ID},
                "source_photo": {"sha256": ("a" if role == "AA" else "c") * 64},
                "reference_geometry": {"file_sha256": "9" * 64},
                "geometry_guard": {
                    "reference_homography_alignment_guard_pass": True,
                },
                "cells": [{} for _ in range(16)],
                "left_right_pairs": [{} for _ in range(8)],
                "paired_summary": {
                    "repeat_noise_p95_de76": 1.0,
                    "all_pairs_within_exploratory_threshold": passed,
                },
                "classification": {
                    "state": (
                        "CAMERA_RELATIVE_CONTROLLER_MATCH_CANDIDATE"
                        if passed
                        else "CAMERA_RELATIVE_CONTROLLER_MISMATCH_CANDIDATE"
                    )
                },
            }
        ),
    )


def _white(path: Path, *, passed: bool = True) -> Path:
    photo_sha256 = "b" * 64 if "aa" in path.name else "d" * 64
    return _write(
        path,
        _seal(
            {
                "schema_version": white_gate.SCHEMA_VERSION,
                "kind": white_gate.KIND,
                "layout": {"id": white_gate.LAYOUT_ID, "patch_count": 60},
                "inputs": {
                    "candidate": {"sha256": photo_sha256},
                    "geometry_reference": {"sha256": "9" * 64},
                },
                "thresholds": {"repeat_noise_p95_de76": 1.0},
                "summary": {"all_panel_regions_match_reference": passed},
                "classification": {
                    "pass": passed,
                    "state": (
                        "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH"
                        if passed
                        else "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MISMATCH"
                    ),
                },
            }
        ),
    )


def _capture_sidecar(path: Path, action_path: Path, ordinal: int) -> Path:
    action = same_once.base.runner.ACTIONS[ordinal - 1]
    photo_sha256 = ("abcd"[ordinal - 1]) * 64
    captured_at = f"2026-08-28T10:0{ordinal}:00+08:00"
    settings = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
        "frame_width": 1920,
        "frame_height": 1080,
    }
    effective = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
        "frame_width": 1920,
        "frame_height": 1080,
    }
    return _write(
        path,
        {
            "capture_binding": bundle.camera.BINDING_LIVE,
            "campaign_id": same_once.pack.CAMPAIGN_ID,
            "contract_id": same_once.base.runner.CONTRACT_ID,
            "firmware_sha256": same_once.FIRMWARE_SHA256,
            "boot_nonce": "same-batch-boot",
            "ordinal": ordinal,
            "action_id": action["action_id"],
            "descriptor_id": action["descriptor_id"],
            "capture_id": f"{ordinal:064x}",
            "captured_at": captured_at,
            "action_result": {
                "file_sha256": bundle._sha256_bytes(action_path.read_bytes())
            },
            "camera": {
                "camera_id": "camera-1",
                "instance_id": "instance-1",
                "index": 0,
                "backend": "DSHOW",
                "requested_settings": settings,
                "effective_settings_before_frame": effective,
                "effective_settings_after_frame": effective,
                "read_failures": 0,
            },
            "photo": {
                "sha256": photo_sha256,
                "width": 1920,
                "height": 1080,
            },
            "coverage": {
                "scope": bundle.camera.COVERAGE_FULL,
                "full_panel_visible": True,
                "full_panel_uncropped": True,
                "mount_id": "fixed-mount-1",
            },
            "integrity": {"sha256": f"{ordinal + 4:064x}"},
        },
    )


def _noise_report(path: Path) -> Path:
    settings = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
        "frame_width": 1920,
        "frame_height": 1080,
    }
    return _write(
        path,
        _seal(
            {
                "schema_version": bundle.noise_report.SCHEMA_VERSION,
                "kind": bundle.noise_report.KIND,
                "baseline_id": "8" * 64,
                "layout": {"id": white_gate.LAYOUT_ID, "patch_count": 60},
                "geometry_reference": {"file_sha256": "9" * 64},
                "capture_contract": {
                    "capture_count": 3,
                    "capture_binding": bundle.camera.BINDING_LIVE,
                    "coverage_scope": bundle.camera.COVERAGE_FULL,
                    "same_factory_white_action": True,
                    "locked_camera_and_mount": {
                        "camera_id": "camera-1",
                        "camera_instance_id": "instance-1",
                        "camera_index": 0,
                        "backend": "DSHOW",
                        "mount_id": "fixed-mount-1",
                        "requested_settings": settings,
                        "effective_settings": settings,
                    },
                },
                "summary": {"repeat_noise_p95_de76": 1.0},
                "classification": {"valid_repeat_noise_baseline": True},
            }
        ),
    )


def _aa_cc_comparison(path: Path, aa: Path, cc: Path) -> Path:
    return _write(
        path,
        _seal(
            {
                "schema_version": bundle.aa_cc_comparison.SCHEMA_VERSION,
                "kind": bundle.aa_cc_comparison.KIND,
                "comparison_id": "7" * 64,
                "inputs": {
                    "aa": {
                        "file_sha256": bundle._sha256_bytes(aa.read_bytes()),
                        "role": "AA",
                    },
                    "cc": {
                        "file_sha256": bundle._sha256_bytes(cc.read_bytes()),
                        "role": "CC",
                    },
                },
                "shared_bindings": {
                    "reference_geometry": {"file_sha256": "9" * 64},
                    "repeat_noise_p95_de76": 1.0,
                    "aa_controller_pair_gate_pass": True,
                    "cc_controller_pair_gate_pass": True,
                },
                "controller_code_deltas": [{} for _ in range(16)],
                "code_results": [{} for _ in range(8)],
                "summary": {
                    "code_count": 8,
                    "controller_code_delta_count": 16,
                    "classification_counts": {
                        "R20_LINKED_EXPLORATORY_EFFECT": 0,
                        "NO_RESOLVED_EFFECT": 8,
                        "CONTROLLER_INCONSISTENT": 0,
                    },
                },
                "classification": {
                    "state": "NO_RESOLVED_AA_TO_CC_EFFECT",
                    "absolute_colour_proven": False,
                    "qualified_new_colour": False,
                    "r20_causality_proven": False,
                },
                "output_write_contract": "O_EXCL",
            }
        ),
    )


@pytest.fixture(autouse=True)
def _validated_sidecar_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate(path: Path) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    monkeypatch.setattr(bundle.camera, "validate_capture_evidence", validate)


def _inputs(
    tmp_path: Path,
) -> tuple[list[Path], list[Path], Path, Path, Path, Path, Path, Path]:
    actions = [
        _action(tmp_path / same_once.ACTION_OUTPUT_NAMES[ordinal], ordinal)
        for ordinal in range(1, 5)
    ]
    sidecars = [
        _capture_sidecar(
            tmp_path / f"capture-{ordinal}.json", actions[ordinal - 1], ordinal
        )
        for ordinal in range(1, 5)
    ]
    aa = _atlas(tmp_path / "aa.json", "AA")
    cc = _atlas(tmp_path / "cc.json", "CC")
    return (
        actions,
        sidecars,
        _noise_report(tmp_path / "repeat-noise.json"),
        _aa_cc_comparison(tmp_path / "aa-cc.json", aa, cc),
        aa,
        _white(tmp_path / "white-aa.json"),
        cc,
        _white(tmp_path / "white-cc.json"),
    )


def test_bundle_is_accepted_by_true_r20_runner(tmp_path: Path) -> None:
    report = bundle.build_bundle(*_inputs(tmp_path))
    output = tmp_path / "batch1-evidence.json"
    output.write_text(json.dumps(report), encoding="utf-8")
    loaded, digest = true_once._load_batch1_evidence(output)  # noqa: SLF001
    assert loaded["outcome"] == "PASS"
    assert loaded["candidate_transport_codes_authorized"] == [0, 0, 2]
    assert len(digest) == 64


def test_failed_atlas_gate_is_rejected(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, _, white_aa, cc, white_cc = _inputs(tmp_path)
    failed = _atlas(tmp_path / "aa-failed.json", "AA", passed=False)
    with pytest.raises(bundle.SameR20ParityEvidenceBundleError, match="did not pass"):
        bundle.build_bundle(
            actions,
            sidecars,
            noise,
            comparison,
            failed,
            white_aa,
            cc,
            white_cc,
        )


def test_failed_terminal_white_is_rejected(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, aa, white_aa, cc, _ = _inputs(tmp_path)
    failed = _white(tmp_path / "white-cc-failed.json", passed=False)
    with pytest.raises(bundle.SameR20ParityEvidenceBundleError, match="did not pass"):
        bundle.build_bundle(
            actions, sidecars, noise, comparison, aa, white_aa, cc, failed
        )


def test_action_tamper_is_rejected(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc = _inputs(tmp_path)
    value = json.loads(actions[0].read_text(encoding="utf-8"))
    value["action"]["ordinal"] = 2
    actions[0].write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(bundle.SameR20ParityEvidenceBundleError, match="integrity"):
        bundle.build_bundle(
            actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc
        )


def test_capture_photo_mismatch_is_rejected(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc = _inputs(tmp_path)
    value = json.loads(sidecars[2].read_text(encoding="utf-8"))
    value["photo"]["sha256"] = "e" * 64
    sidecars[2].write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(
        bundle.SameR20ParityEvidenceBundleError, match="binding differs"
    ):
        bundle.build_bundle(
            actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc
        )


def test_partial_or_unlocked_capture_is_rejected(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc = _inputs(tmp_path)
    value = json.loads(sidecars[0].read_text(encoding="utf-8"))
    value["coverage"]["scope"] = bundle.camera.COVERAGE_PARTIAL
    value["coverage"]["full_panel_visible"] = False
    value["coverage"]["full_panel_uncropped"] = False
    sidecars[0].write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(bundle.SameR20ParityEvidenceBundleError, match="full-panel"):
        bundle.build_bundle(
            actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc
        )


def test_camera_signature_drift_is_rejected(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc = _inputs(tmp_path)
    value = json.loads(sidecars[3].read_text(encoding="utf-8"))
    value["camera"]["effective_settings_before_frame"]["exposure"] = -5.0
    value["camera"]["effective_settings_after_frame"]["exposure"] = -5.0
    sidecars[3].write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(bundle.SameR20ParityEvidenceBundleError, match="signature"):
        bundle.build_bundle(
            actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc
        )


def test_analysis_noise_value_must_match_sealed_baseline(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, _, white_aa, cc, white_cc = _inputs(tmp_path)
    mismatched_aa = _atlas(tmp_path / "aa-noise-mismatch.json", "AA")
    value = json.loads(mismatched_aa.read_text(encoding="utf-8"))
    unsigned = dict(value)
    unsigned.pop("integrity")
    unsigned["paired_summary"]["repeat_noise_p95_de76"] = 2.0
    mismatched_aa.write_text(json.dumps(_seal(unsigned)), encoding="utf-8")
    with pytest.raises(
        bundle.SameR20ParityEvidenceBundleError,
        match="sealed baseline",
    ):
        bundle.build_bundle(
            actions,
            sidecars,
            noise,
            comparison,
            mismatched_aa,
            white_aa,
            cc,
            white_cc,
        )


def test_aa_cc_comparison_must_bind_exact_analysis_files(tmp_path: Path) -> None:
    actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc = _inputs(tmp_path)
    value = json.loads(comparison.read_text(encoding="utf-8"))
    unsigned = dict(value)
    unsigned.pop("integrity")
    unsigned["inputs"]["aa"]["file_sha256"] = "0" * 64
    comparison.write_text(json.dumps(_seal(unsigned)), encoding="utf-8")
    with pytest.raises(
        bundle.SameR20ParityEvidenceBundleError,
        match="paired comparison",
    ):
        bundle.build_bundle(
            actions, sidecars, noise, comparison, aa, white_aa, cc, white_cc
        )


def test_true_r20_loader_rejects_resealed_camera_binding_tamper(tmp_path: Path) -> None:
    report = bundle.build_bundle(*_inputs(tmp_path))
    unsigned = dict(report)
    unsigned.pop("integrity")
    unsigned["camera_lock"]["mount_id"] = "different-mount"
    tampered = _seal(unsigned)
    output = tmp_path / "tampered-batch1-evidence.json"
    output.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(true_once.base.runner.RecheckError, match="camera signature"):
        true_once._load_batch1_evidence(output)  # noqa: SLF001


def test_exclusive_output_refuses_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "bundle.json"
    bundle._write_exclusive(path, b"first")
    with pytest.raises(bundle.SameR20ParityEvidenceBundleError, match="overwrite"):
        bundle._write_exclusive(path, b"second")
