from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_true_r20_partial_hold_evidence_bundle as bundle


def _sha(number: int) -> str:
    return f"{number:064x}"


def _sealed_file(path: Path, root: dict[str, Any]) -> bytes:
    unsigned = deepcopy(root)
    unsigned.pop("integrity", None)
    root = deepcopy(unsigned)
    root["integrity"] = {
        "algorithm": bundle.INTEGRITY_ALGORITHM,
        "sha256": hashlib.sha256(bundle._canonical_json(unsigned)).hexdigest(),  # noqa: SLF001
    }
    payload = json.dumps(root, sort_keys=True).encode("utf-8")
    path.write_bytes(payload)
    return payload


def _camera_signature() -> dict[str, Any]:
    settings = {
        "autofocus": 0.0,
        "auto_exposure": 0.25,
        "auto_white_balance": 0.0,
        "focus": 12.0,
        "exposure": -6.0,
        "white_balance_temperature": 4600.0,
    }
    return {
        "camera_id": "camera-1",
        "instance_id": "instance-1",
        "index": 0,
        "backend": "DSHOW",
        "mount_id": "fixed-mount-1",
        "requested_settings": settings,
        "effective_settings": settings,
    }


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    reference_path = tmp_path / "reference.json"
    reference_payload = _sealed_file(reference_path, {"reference": True})
    geometry_sha = hashlib.sha256(reference_payload).hexdigest()
    camera_signature = _camera_signature()
    repeat_noise = 1.25
    noise_binding = {
        "path": "repeat-noise.json",
        "file_sha256": _sha(1),
        "canonical_integrity_sha256": _sha(2),
        "baseline_id": _sha(3),
        "reference_geometry_sha256": geometry_sha,
        "capture_count": 3,
        "repeat_noise_p95_de76": repeat_noise,
        "camera_signature": camera_signature,
    }
    batch1_binding = {
        "path": "batch1.json",
        "file_sha256": _sha(4),
        "canonical_integrity_sha256": _sha(5),
        "campaign_id": "BATCH1",
        "contract_id": _sha(6),
        "requirements_id": bundle.true_pack.BATCH1_EVIDENCE_REQUIREMENTS_ID,
    }
    batch1_root = {"repeat_noise_baseline": deepcopy(noise_binding)}
    terminal = {
        "prerequisite_id": _sha(7),
        "eligible": True,
        "capture_sidecar_file_sha256": _sha(100),
        "photo_sha256": _sha(101),
        "action_result_file_sha256": _sha(102),
        "campaign_boot_nonce": "batch2-boot",
        "captured_at": "2026-08-28T10:00:00+08:00",
    }
    batch2_binding = {
        "input_file": "batch2.json",
        "file_sha256": _sha(8),
        "canonical_integrity_sha256": _sha(9),
        "bundle_id": _sha(10),
        "campaign_identity": {},
        "terminal_white_prerequisite": terminal,
        "shared_camera_lock": camera_signature,
        "shared_analysis_bindings": {
            "repeat_noise_baseline": deepcopy(noise_binding),
            "reference_geometry_sha256": geometry_sha,
            "repeat_noise_p95_de76": repeat_noise,
        },
    }
    monkeypatch.setattr(
        bundle,
        "_load_batch1",
        lambda _path: (deepcopy(batch1_root), deepcopy(batch1_binding)),
    )
    monkeypatch.setattr(
        bundle,
        "_validate_batch2",
        lambda _path: ({}, deepcopy(batch2_binding)),
    )
    monkeypatch.setattr(
        bundle.batch1_builder,
        "_validate_noise_report",
        lambda _path: (deepcopy(noise_binding), repeat_noise),
    )

    actions = [
        {
            "ordinal": ordinal,
            "path": f"action-{ordinal}.json",
            "file_sha256": _sha(200 + ordinal),
            "canonical_integrity_sha256": _sha(210 + ordinal),
            "action_id": bundle.true_pack.ACTION_IDS[ordinal - 1],
            "descriptor_id": bundle.true_pack.DESCRIPTOR_IDS[ordinal - 1],
            "role": bundle.true_pack.ROLES[ordinal - 1],
            "boot_nonce": "batch3-boot",
            "created_at": f"2026-08-28T10:{ordinal * 2 - 1:02d}:30+08:00",
            "outcome": "complete_pass",
            "visible_refreshes": 1,
        }
        for ordinal in range(1, 5)
    ]
    monkeypatch.setattr(
        bundle,
        "_validate_action_results",
        lambda _paths, _batch1, _batch2: (deepcopy(actions), "batch3-boot"),
    )

    start = datetime(2026, 8, 28, 10, 0, tzinfo=timezone(timedelta(hours=8)))
    pre: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    for index in range(4):
        if index == 0:
            pre_item = {
                "sidecar_file_sha256": terminal["capture_sidecar_file_sha256"],
                "capture_id": _sha(110),
                "photo_sha256": terminal["photo_sha256"],
                "action_result_file_sha256": terminal["action_result_file_sha256"],
                "boot_nonce": terminal["campaign_boot_nonce"],
                "captured_at": terminal["captured_at"],
                "camera_signature": camera_signature,
            }
        else:
            pre_item = deepcopy(after[index - 1])
        pre.append(pre_item)
        action = actions[index]
        video_start = start + timedelta(minutes=index * 2 + 1)
        videos.append(
            {
                "sidecar_file_sha256": _sha(300 + index),
                "canonical_integrity_sha256": _sha(310 + index),
                "capture_id": _sha(320 + index),
                "stage": bundle.STAGES[index],
                "ordinal": index + 1,
                "action_id": action["action_id"],
                "descriptor_id": action["descriptor_id"],
                "action_result_file_sha256": action["file_sha256"],
                "boot_nonce": "batch3-boot",
                "video_sha256": _sha(330 + index),
                "video_bytes": 1000,
                "video_width": 1920,
                "video_height": 1080,
                "fps": 10.0,
                "decoded_frame_count": 300,
                "duration_seconds": 30.0,
                "pre_roll_frames": 20,
                "minimum_duration_seconds": 25.0,
                "started_at": video_start.isoformat(),
                "completed_at": (video_start + timedelta(seconds=30)).isoformat(),
                "camera_signature": camera_signature,
            }
        )
        captured = start + timedelta(minutes=index * 2 + 2)
        after.append(
            {
                "sidecar_file_sha256": _sha(400 + index),
                "canonical_integrity_sha256": _sha(410 + index),
                "capture_id": _sha(420 + index),
                "photo_sha256": _sha(430 + index),
                "action_result_file_sha256": action["file_sha256"],
                "boot_nonce": "batch3-boot",
                "captured_at": captured.isoformat(),
                "ordinal": index + 1,
                "action_id": action["action_id"],
                "descriptor_id": action["descriptor_id"],
                "camera_signature": camera_signature,
            }
        )
    pre_paths = [tmp_path / f"pre-{index}.json" for index in range(4)]
    after_paths = [tmp_path / f"after-{index}.json" for index in range(4)]
    video_paths = [tmp_path / f"video-{index}.json" for index in range(4)]
    photo_lookup = {
        **{str(path): value for path, value in zip(pre_paths, pre, strict=True)},
        **{str(path): value for path, value in zip(after_paths, after, strict=True)},
    }
    video_lookup = {
        str(path): value for path, value in zip(video_paths, videos, strict=True)
    }
    monkeypatch.setattr(
        bundle, "_photo_capture", lambda path: deepcopy(photo_lookup[str(path)])
    )
    monkeypatch.setattr(
        bundle, "_video_capture", lambda path: deepcopy(video_lookup[str(path)])
    )
    monkeypatch.setattr(
        bundle,
        "_validate_static_gate",
        lambda path, **kwargs: {
            "path": str(path),
            "file_sha256": _sha(500 + bundle.STAGES.index(kwargs["stage"])),
            "canonical_integrity_sha256": _sha(
                510 + bundle.STAGES.index(kwargs["stage"])
            ),
            "stage": kwargs["stage"],
            "analysis_id": _sha(520 + bundle.STAGES.index(kwargs["stage"])),
            "before_photo_sha256": kwargs["before_photo_sha256"],
            "after_photo_sha256": kwargs["after_photo_sha256"],
            "static_gate_pass": True,
        },
    )
    monkeypatch.setattr(
        bundle,
        "_validate_video_gate",
        lambda path, **kwargs: {
            "path": str(path),
            "file_sha256": _sha(530 + bundle.STAGES.index(kwargs["stage"])),
            "canonical_integrity_sha256": _sha(
                540 + bundle.STAGES.index(kwargs["stage"])
            ),
            "stage": kwargs["stage"],
            "analysis_id": _sha(550 + bundle.STAGES.index(kwargs["stage"])),
            "source_video_sha256": kwargs["capture"]["video_sha256"],
            "duration_seconds": 30.0,
            "protected_rois": list(bundle.EXPECTED_PROTECTED[kwargs["stage"]]),
            "background_stability_pass": True,
            "transient_gate_pass": True,
        },
    )
    monkeypatch.setattr(
        bundle,
        "_validate_terminal_white",
        lambda path, **kwargs: {
            "path": str(path),
            "file_sha256": _sha(560),
            "canonical_integrity_sha256": _sha(561),
            "analysis_id": _sha(562),
            "candidate_photo_sha256": kwargs["candidate_photo_sha256"],
            "patch_count": 60,
            "camera_relative_factory_white_match": True,
        },
    )
    return {
        "reference_path": reference_path,
        "pre_paths": pre_paths,
        "after_paths": after_paths,
        "video_paths": video_paths,
        "pre": pre,
        "after": after,
        "videos": videos,
        "photo_lookup": photo_lookup,
        "video_lookup": video_lookup,
        "kwargs": {
            "batch1_bundle_path": tmp_path / "batch1.json",
            "batch2_bundle_path": tmp_path / "batch2.json",
            "repeat_noise_report_path": tmp_path / "noise.json",
            "reference_grid_analysis_path": reference_path,
            "action_paths": [tmp_path / f"action-{index}.json" for index in range(4)],
            "pre_capture_paths": pre_paths,
            "after_capture_paths": after_paths,
            "static_gate_paths": [
                tmp_path / f"static-{index}.json" for index in range(4)
            ],
            "video_capture_paths": video_paths,
            "video_gate_paths": [
                tmp_path / f"video-gate-{index}.json" for index in range(4)
            ],
            "terminal_white_gate_path": tmp_path / "terminal-white.json",
        },
    }


def test_aggregate_binds_four_stages_and_conservative_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    report = bundle.build_bundle(**fixture["kwargs"])
    assert report["kind"] == bundle.KIND
    assert [item["stage"] for item in report["stages"]] == list(bundle.STAGES)
    assert report["stages"][0]["protected_rois"] == []
    assert report["stages"][0]["duration_gate_pass"] is True
    assert report["stages"][0]["background_stability_pass"] is True
    assert report["terminal_white_60_patch_gate"]["patch_count"] == 60
    assert report["classification"]["qualified_cross_r20_hold"] is False
    assert (
        report["evidence_boundaries"]["no_area_percentage_or_full_pixel_hold_claim"]
        is True
    )
    assert (
        report["evidence_boundaries"]["center_seam_not_specifically_qualified"] is True
    )
    assert report["evidence_boundaries"]["long_term_retention_not_tested"] is True


def test_aggregate_rejects_terminal_anchor_or_camera_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    fixture["pre"][0]["photo_sha256"] = _sha(999)
    with pytest.raises(bundle.TrueR20PartialHoldEvidenceBundleError, match="terminal"):
        bundle.build_bundle(**fixture["kwargs"])

    fixture = _fixture(tmp_path / "second", monkeypatch)
    fixture["videos"][1]["camera_signature"] = {
        **fixture["videos"][1]["camera_signature"],
        "mount_id": "moved-mount",
    }
    with pytest.raises(bundle.TrueR20PartialHoldEvidenceBundleError, match="camera"):
        bundle.build_bundle(**fixture["kwargs"])


def _video_gate_root(
    *, duration_pass: bool = True, background_pass: bool = True
) -> dict[str, Any]:
    series = [
        {"key": f"C{controller}-{name}", "within_threshold": background_pass}
        for controller in range(2)
        for name in bundle.static_gate.BACKGROUND_LOCAL
    ]
    return {
        "schema_version": bundle.video_gate.SCHEMA_VERSION,
        "kind": bundle.video_gate.KIND,
        "analysis_id": _sha(700),
        "stage": "A",
        "source_video": {
            "sha256": _sha(701),
            "bytes": 1000,
            "width": 1920,
            "height": 1080,
            "fps": 10.0,
            "decoded_frame_count": 300,
            "duration_seconds": 30.0,
        },
        "reference_grid": {"sha256": _sha(702)},
        "thresholds": {
            "repeat_noise_p95_de76": 1.25,
            "pre_roll_frames": 20,
            "minimum_duration_seconds": 25.0,
        },
        "protected_rois": [],
        "evaluation": {
            "series": series,
            "protected_pass": True,
            "background_stability_pass": background_pass,
            "transient_gate_pass": duration_pass and background_pass,
        },
        "duration_gate_pass": duration_pass,
        "classification": {
            "state": "NO_PROTECTED_ROI_AT_THIS_STAGE",
            "transient_gate_pass": duration_pass and background_pass,
            "qualified_cross_r20_hold": False,
        },
        "output_write_contract": "O_EXCL",
    }


def test_stage_a_has_no_protected_roi_but_still_requires_duration_and_background(
    tmp_path: Path,
) -> None:
    capture = {
        "video_sha256": _sha(701),
        "video_bytes": 1000,
        "video_width": 1920,
        "video_height": 1080,
        "fps": 10.0,
        "decoded_frame_count": 300,
        "duration_seconds": 30.0,
        "pre_roll_frames": 20,
        "minimum_duration_seconds": 25.0,
    }
    passing = tmp_path / "passing.json"
    _sealed_file(passing, _video_gate_root())
    binding = bundle._validate_video_gate(  # noqa: SLF001
        passing,
        stage="A",
        capture=capture,
        geometry_sha256=_sha(702),
        repeat_noise_p95_de76=1.25,
    )
    assert binding["protected_rois"] == []
    assert binding["background_stability_pass"] is True

    for name, root in (
        ("duration", _video_gate_root(duration_pass=False)),
        ("background", _video_gate_root(background_pass=False)),
    ):
        path = tmp_path / f"{name}.json"
        _sealed_file(path, root)
        with pytest.raises(
            bundle.TrueR20PartialHoldEvidenceBundleError,
            match="duration/background/protected",
        ):
            bundle._validate_video_gate(  # noqa: SLF001
                path,
                stage="A",
                capture=capture,
                geometry_sha256=_sha(702),
                repeat_noise_p95_de76=1.25,
            )


def test_bundle_output_is_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "bundle.json"
    bundle._write_exclusive(output, b"first")  # noqa: SLF001
    with pytest.raises(bundle.TrueR20PartialHoldEvidenceBundleError, match="overwrite"):
        bundle._write_exclusive(output, b"second")  # noqa: SLF001
    assert output.read_bytes() == b"first"


def _terminal_white_root() -> dict[str, Any]:
    patches = [
        {
            "controller": controller,
            "row": row,
            "column": column,
            "camera_relative_de76": 0.0,
        }
        for controller in range(2)
        for row in range(5)
        for column in range(6)
    ]
    return {
        "schema_version": bundle.white_gate.SCHEMA_VERSION,
        "kind": bundle.white_gate.KIND,
        "analysis_id": _sha(800),
        "layout": {
            "id": bundle.white_gate.LAYOUT_ID,
            "controllers": 2,
            "patch_count": 60,
            "panel_wide_discrete_patch_sampling": True,
        },
        "inputs": {
            "candidate": {"sha256": _sha(801)},
            "factory_white_reference": {"sha256": _sha(802)},
            "geometry_reference": {"sha256": _sha(803)},
        },
        "thresholds": {
            "repeat_noise_p95_de76": 1.25,
            "patch_grid_p95_de76": 4.0,
            "patch_grid_max_de76": 8.0,
        },
        "patches": patches,
        "summary": {
            "patch_count": 60,
            "camera_relative_de76_median": 0.0,
            "camera_relative_de76_p95": 0.0,
            "camera_relative_de76_max": 0.0,
            "all_panel_regions_match_reference": True,
        },
        "classification": {
            "state": "PANEL_WIDE_CAMERA_RELATIVE_FACTORY_WHITE_MATCH",
            "pass": True,
            "absolute_white_proven": False,
        },
        "output_write_contract": "O_EXCL",
    }


def test_terminal_white_gate_deep_checks_all_sixty_unique_patches(
    tmp_path: Path,
) -> None:
    path = tmp_path / "white.json"
    root = _terminal_white_root()
    _sealed_file(path, root)
    result = bundle._validate_terminal_white(  # noqa: SLF001
        path,
        candidate_photo_sha256=_sha(801),
        reference_photo_sha256=_sha(802),
        geometry_sha256=_sha(803),
        repeat_noise_p95_de76=1.25,
    )
    assert result["patch_count"] == 60

    root["patches"][1] = deepcopy(root["patches"][0])
    _sealed_file(path, root)
    with pytest.raises(
        bundle.TrueR20PartialHoldEvidenceBundleError, match="coordinates"
    ):
        bundle._validate_terminal_white(  # noqa: SLF001
            path,
            candidate_photo_sha256=_sha(801),
            reference_photo_sha256=_sha(802),
            geometry_sha256=_sha(803),
            repeat_noise_p95_de76=1.25,
        )
