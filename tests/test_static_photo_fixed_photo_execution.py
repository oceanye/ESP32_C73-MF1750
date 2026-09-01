from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from host.static_photo.fixed_photo_execution import (
    ACTION_KIND,
    CODEGEN_KIND,
    FixedPhotoExecutionError,
    SOURCE_WHITE_KIND,
    WHITE_SUCCESSOR_KIND,
    build_fixed_photo_execution_bundle,
    seal_source_white_authority_summary,
    seal_white_successor_requirement,
    verify_fixed_photo_execution_bundle,
)
from host.static_photo.history_palette import QualificationLevel
from host.static_photo.multi_lut_hold_schedule import (
    Controller,
    LutHoldCapability,
    MultiLutRecipe,
    build_multi_lut_hold_schedule,
)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _recipe(
    recipe_id: str,
    controller: Controller,
    profile: str,
    source: int,
    middle: int | None,
    target: int,
    *,
    qualified: bool = True,
) -> MultiLutRecipe:
    return MultiLutRecipe(
        recipe_id=recipe_id,
        controller=controller,
        lut_profile_id=profile,
        source_code=source,
        middle_code=middle,
        target_code=target,
        target_repeat_count=2,
        qualification_level=(
            QualificationLevel.QUALIFIED if qualified else QualificationLevel.CANDIDATE
        ),
        identical_target_repeat_qualified=qualified,
        local_hold_qualified=qualified,
        factory_white_recovery_qualified=qualified,
        measurement_artifact_sha256=SHA_A,
    )


def _schedule(*, include_unused_candidate: bool = False):
    recipes = [
        _recipe("A1", Controller.CS1, "profile-A", 7, 2, 0),
        _recipe("B1", Controller.CS1, "profile-B", 1, None, 4),
        _recipe("A2", Controller.CS2, "profile-A", 7, 3, 0),
        _recipe("B2", Controller.CS2, "profile-B", 1, None, 4),
    ]
    if include_unused_candidate:
        recipes.append(
            _recipe(
                "UNUSED-CANDIDATE",
                Controller.CS1,
                "not-scheduled",
                3,
                4,
                5,
                qualified=False,
            )
        )
    return build_multi_lut_hold_schedule(
        tuple(recipes),
        bytes((0, 1, 2, 3, 0, 1, 2, 3)),
        (
            LutHoldCapability("profile-A", 7, 6, True, True, (), SHA_B),
            LutHoldCapability("profile-B", 7, 6, True, True, ("profile-A",), SHA_C),
        ),
        profile_order=("profile-A", "profile-B"),
        width=4,
        height=2,
    )


def _source_white():
    return seal_source_white_authority_summary(
        {
            "schema_version": 1,
            "kind": SOURCE_WHITE_KIND,
            "authority_id": "source-white-evidence-v1",
            "source_action_id": "factory-white-action-v1",
            "source_descriptor_id": "factory-white-descriptor-v1",
            "evidence_file_sha256": SHA_A,
            "controllers": ["CS1", "CS2"],
            "factory_otp_white_complete": True,
            "screen_clean_white_observed": True,
            "sealed_offline_evidence": True,
            "live_authority": False,
        }
    )


def _successor():
    return seal_white_successor_requirement(
        {
            "schema_version": 1,
            "kind": WHITE_SUCCESSOR_KIND,
            "requirement_id": "external-factory-white-after-f7-v1",
            "required_successor_kind": "INDEPENDENT_FACTORY_OTP_WHITE_ONE_SHOT",
            "required": True,
            "independent": True,
            "must_follow_final_photo_pass": True,
            "identity_owner": "EXTERNAL_SUCCESSOR_MODULE",
            "identity_status": "REQUIRED_NOT_ASSIGNED_HERE",
            "one_shot_required": True,
            "autochain_allowed": False,
            "live_authority": False,
        }
    )


def _all_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_builds_fixed_one_shot_bundle_and_binds_exact_schedule(tmp_path: Path) -> None:
    schedule = _schedule(include_unused_candidate=True)
    output = tmp_path / "bundle"
    result = build_fixed_photo_execution_bundle(
        schedule,
        _source_white(),
        _successor(),
        output_dir=output,
    )
    assert result["pass_count"] == len(schedule.passes)
    assert result["codegen_ready"] is True
    assert result["live_execution_admitted"] is False
    assert result["live_authority_generated"] is False
    assert len(list((output / "frames").glob("*.bin"))) == len(schedule.passes)

    manifest = json.loads((output / "EXECUTION-MANIFEST.json").read_text())
    assert (
        manifest["schedule"]["canonical_sha256"]
        == schedule.mapping()["integrity"]["canonical_sha256"]
    )
    assert manifest["schedule"]["profile_order"] == ["profile-A", "profile-B"]
    assert manifest["white_successor_gate"]["identity_status"] == (
        "REQUIRED_NOT_ASSIGNED_HERE"
    )
    assert manifest["white_successor_gate"]["live_execution_admitted"] is False
    assert manifest["fixed_execution_contract"] == {
        "one_firmware_unit_per_pass": True,
        "manual_one_shot_per_pass": True,
        "driver_calls_per_pass": 1,
        "visible_refresh_requests_per_pass": 1,
        "retry_allowed": False,
        "fallback_allowed": False,
        "recovery_embedded": False,
        "autochain_allowed": False,
        "runtime_raw_frame_allowed": False,
        "runtime_lut_or_payload_allowed": False,
    }
    for expected, record in zip(schedule.passes, manifest["ordered_passes"]):
        assert record["ordinal"] == expected.ordinal
        assert record["lut_profile_id"] == expected.lut_profile_id
        assert record["committed_profiles_before"] == list(
            expected.committed_profiles_before
        )
        assert (output / record["frame_file"]).read_bytes() == expected.packed_frame


def test_action_and_codegen_have_no_dynamic_or_autochain_entry(tmp_path: Path) -> None:
    schedule = _schedule()
    output = tmp_path / "bundle"
    build_fixed_photo_execution_bundle(
        schedule, _source_white(), _successor(), output_dir=output
    )
    actions = sorted((output / "actions").glob("*.json"))
    predecessor = None
    for path in actions:
        action = json.loads(path.read_text())
        assert action["kind"] == ACTION_KIND
        assert action["predecessor_action_id"] == predecessor
        assert action["invocation"] == "EXPLICIT_MANUAL_ONE_SHOT"
        assert action["driver_call_count"] == 1
        assert action["visible_refresh_request_count"] == 1
        assert action["retry_count"] == 0
        assert action["fallback_allowed"] is False
        assert action["recovery_embedded"] is False
        assert action["autochain_allowed"] is False
        assert action["live_authority"] is False
        predecessor = action["action_id"]
    codegen = json.loads((output / "CODEGEN-READY.json").read_text())
    assert codegen["kind"] == CODEGEN_KIND
    assert codegen["compile_time_fixed_frames_only"] is True
    assert codegen["runtime_raw_frame_entry"] is False
    assert codegen["runtime_lut_entry"] is False
    assert codegen["runtime_payload_entry"] is False
    assert codegen["firmware_compiled"] is False


def test_two_empty_directories_receive_byte_identical_bundles(tmp_path: Path) -> None:
    schedule = _schedule()
    first = tmp_path / "first"
    second = tmp_path / "second"
    one = build_fixed_photo_execution_bundle(
        schedule, _source_white(), _successor(), output_dir=first
    )
    two = build_fixed_photo_execution_bundle(
        schedule, _source_white(), _successor(), output_dir=second
    )
    assert _all_files(first) == _all_files(second)
    assert one["manifest_canonical_sha256"] == two["manifest_canonical_sha256"]
    assert one["sha256sums_file_sha256"] == two["sha256sums_file_sha256"]


def test_refuses_to_overwrite_any_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    output.mkdir()
    (output / "keep.txt").write_text("owned by user")
    with pytest.raises(FixedPhotoExecutionError, match="must be empty"):
        build_fixed_photo_execution_bundle(
            _schedule(), _source_white(), _successor(), output_dir=output
        )
    assert (output / "keep.txt").read_text() == "owned by user"


def test_tampered_frame_and_checksum_fail_closed(tmp_path: Path) -> None:
    schedule = _schedule()
    output = tmp_path / "bundle"
    build_fixed_photo_execution_bundle(
        schedule, _source_white(), _successor(), output_dir=output
    )
    frame = output / "frames" / "pass-0001.bin"
    payload = bytearray(frame.read_bytes())
    payload[0] ^= 0x10
    frame.write_bytes(payload)
    with pytest.raises(FixedPhotoExecutionError, match="SHA-256|content differs"):
        verify_fixed_photo_execution_bundle(
            output, schedule, _source_white(), _successor()
        )


def test_drifted_frame_or_order_in_schedule_fails_before_output(tmp_path: Path) -> None:
    schedule = _schedule()
    changed_frame = bytearray(schedule.passes[0].packed_frame)
    changed_frame[0] ^= 0x10
    drifted_pass = replace(schedule.passes[0], packed_frame=bytes(changed_frame))
    drifted = replace(schedule, passes=(drifted_pass, *schedule.passes[1:]))
    with pytest.raises(FixedPhotoExecutionError, match="packed frame SHA-256"):
        build_fixed_photo_execution_bundle(
            drifted,
            _source_white(),
            _successor(),
            output_dir=tmp_path / "frame-drift",
        )

    swapped = replace(
        schedule, passes=(schedule.passes[1], schedule.passes[0], *schedule.passes[2:])
    )
    with pytest.raises(FixedPhotoExecutionError, match="begin with source|ordinal"):
        build_fixed_photo_execution_bundle(
            swapped,
            _source_white(),
            _successor(),
            output_dir=tmp_path / "order-drift",
        )


def test_active_mask_and_recipe_assignment_drift_fail_closed(tmp_path: Path) -> None:
    schedule = _schedule()
    mask_drift = replace(
        schedule,
        passes=(
            replace(schedule.passes[0], active_mask_sha256="d" * 64),
            *schedule.passes[1:],
        ),
    )
    with pytest.raises(FixedPhotoExecutionError, match="active mask SHA-256"):
        build_fixed_photo_execution_bundle(
            mask_drift,
            _source_white(),
            _successor(),
            output_dir=tmp_path / "mask-drift",
        )

    assignment_drift = replace(schedule, recipe_assignment_sha256="e" * 64)
    with pytest.raises(FixedPhotoExecutionError, match="recipe assignment SHA-256"):
        build_fixed_photo_execution_bundle(
            assignment_drift,
            _source_white(),
            _successor(),
            output_dir=tmp_path / "assignment-drift",
        )


def test_unready_recipe_trajectory_cannot_enter_bundle(tmp_path: Path) -> None:
    schedule = _schedule()
    candidate = replace(
        schedule.recipes[0],
        qualification_level=QualificationLevel.CANDIDATE,
        identical_target_repeat_qualified=False,
        local_hold_qualified=False,
        factory_white_recovery_qualified=False,
    )
    drifted = replace(schedule, recipes=(candidate, *schedule.recipes[1:]))
    with pytest.raises(FixedPhotoExecutionError, match="READY.*recipe or HOLD"):
        build_fixed_photo_execution_bundle(
            drifted,
            _source_white(),
            _successor(),
            output_dir=tmp_path / "unready",
        )


def test_tampered_sealed_inputs_and_unsealed_inputs_are_rejected(
    tmp_path: Path,
) -> None:
    source = _source_white()
    source["screen_clean_white_observed"] = False
    with pytest.raises(FixedPhotoExecutionError, match="canonical SHA-256"):
        build_fixed_photo_execution_bundle(
            _schedule(), source, _successor(), output_dir=tmp_path / "source"
        )
    unsigned_successor = dict(_successor())
    unsigned_successor.pop("integrity")
    with pytest.raises(FixedPhotoExecutionError, match="requires integrity"):
        build_fixed_photo_execution_bundle(
            _schedule(),
            _source_white(),
            unsigned_successor,
            output_dir=tmp_path / "successor",
        )


def test_checksum_list_is_complete_and_excludes_itself(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    build_fixed_photo_execution_bundle(
        _schedule(), _source_white(), _successor(), output_dir=output
    )
    records = {}
    for line in (output / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        records[name] = digest
    all_files = set(_all_files(output))
    assert set(records) == all_files - {"SHA256SUMS.txt"}
    assert all(
        hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
        for name, digest in records.items()
    )
