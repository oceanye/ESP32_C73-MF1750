from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_ec5_eightcode_atlas as atlas


def test_preview_palette_freezes_known_codes_and_labels_u04_u07_as_locators() -> None:
    assert atlas.PREVIEW_PALETTE == (
        (0, 0, 0),
        (255, 255, 255),
        (245, 210, 35),
        (230, 45, 45),
        (0, 190, 220),
        (40, 80, 220),
        (40, 180, 75),
        (210, 55, 210),
    )
    manifest, _ = atlas.build_manifest()
    notice = manifest["preview_notice"]
    assert "codes 0/1/2/3/5/6 use the frozen" in notice
    assert "RGB values for codes 0x4 and 0x7 are locators only" in notice
    assert "do not predict physical panel colours" in notice


def test_frozen_roles_replay_frame_and_dual_dtm_identities() -> None:
    for role in atlas.ROLES:
        frame = atlas.build_frame(role)
        atlas.validate_frame(role, frame)
        streams = {
            "frame": frame,
            "cs1": atlas.controller_stream(frame, 0),
            "cs2": atlas.controller_stream(frame, 1),
        }
        for name, payload in streams.items():
            expected_sha, expected_fnv = atlas.FROZEN_IDENTITIES[role][name]
            actual = atlas.identity(payload)
            assert actual["sha256"] == expected_sha
            assert actual["fnv1a_u32"] == expected_fnv
        assert atlas.histogram(frame) == atlas.FROZEN_HISTOGRAMS[role]


def test_atlas_is_equal_area_and_position_counterbalanced() -> None:
    rois = atlas.frozen_rois()
    assert len(rois) == 16
    for controller in ("CS1", "CS2"):
        own = [roi for roi in rois if roi["controller"] == controller]
        assert [roi["code"] for roi in own] == (
            list(range(8)) if controller == "CS1" else list(reversed(range(8)))
        )
        assert {roi["payload_pixels"] for roi in own} == {atlas.PATCH_PIXELS}
    for code in range(8):
        pair = [roi for roi in rois if roi["code"] == code]
        assert len(pair) == 2
        assert {roi["controller"] for roi in pair} == {"CS1", "CS2"}
        assert sum(roi["payload_pixels"] for roi in pair) == 8192
        assert sum(roi["slot"] for roi in pair) == 7


def test_manifest_is_hardware_blocked_and_does_not_claim_colours() -> None:
    manifest, _ = atlas.build_manifest()
    assert manifest["execution_eligible"] is False
    assert manifest["hardware_action_id"] is None
    assert manifest["classification"] == (
        "OFFLINE_TECHNICAL_CODES_NOT_PHYSICAL_COLOUR_CLAIMS"
    )
    assert manifest["hardware_gate"] == {
        "blocked": True,
        "required_before_refreeze": [
            "isolated_u07t_v2_complete_pass_result_and_permanent_technical_claim",
            "u07t_manual_observation",
            "newer_post_u07t_rc2g_white_result_and_permanent_claim",
            "newer_post_u07t_clean_white_and_electrical_manual_observation",
            "fresh_formal_u07_claim_absence",
            "new_action_identity_and_release",
        ],
        "startup_refresh": False,
        "automatic_execute": False,
        "retry": False,
        "recovery": False,
        "raw_frame_ingress": False,
        "dithering_present": False,
        "spatial_mixing_present": False,
        "custom_lut_or_waveform": False,
    }
    assert "do not predict physical panel colours" in manifest["preview_notice"]
    assert manifest["device_io_performed"] is False
    assert manifest["network_io_performed"] is False
    assert manifest["claims_created"] is False


def test_transition_routes_reuse_stage_b_and_keep_directional_branches() -> None:
    manifest, _ = atlas.build_manifest()
    reuse = manifest["existing_stage_b_reuse"]
    assert reuse["release_canonical_sha256"] == (
        "b500fee26d57b11b0bf9f8441076dce5982516429794bed49f04f4ae2bcbdb04"
    )
    assert reuse["initial_codes"] == [1, 0, 3, 2, 5, 6]
    branches = {
        item["branch_id"]: item for item in manifest["transition_candidates"]
    }
    assert branches["ATLAS_ONLY_VISUAL"]["visible_refreshes"] == 2
    assert branches["STAGE_B_KNOWN6_TO_U04"]["visible_refreshes"] == 3
    assert branches["STAGE_B_KNOWN6_TO_U07"]["visible_refreshes"] == 3
    assert branches["ATLAS_TO_U04_TO_U07"]["roles"] == [
        "atlas",
        "target_u04",
        "target_u07",
        "external_rc2g_white",
    ]
    assert branches["ATLAS_TO_U07_TO_U04"]["roles"] == [
        "atlas",
        "target_u07",
        "target_u04",
        "external_rc2g_white",
    ]


def test_publish_validate_and_tamper_fail_closed(tmp_path: Path) -> None:
    output = tmp_path / "atlas"
    manifest = atlas.generate(output)
    report = atlas.validate(manifest)
    assert report["valid"] is True
    assert report["execution_eligible"] is False
    assert report["claims_created"] is False
    with pytest.raises(atlas.EightCodeAtlasError, match="already exists"):
        atlas.generate(output)

    raw = output / "eightcode-atlas.raw"
    payload = bytearray(raw.read_bytes())
    payload[0] ^= 0x01
    raw.write_bytes(payload)
    with pytest.raises(atlas.EightCodeAtlasError, match="bytes differ"):
        atlas.validate(manifest)


def test_white_and_targets_are_pure_compiled_candidate_roles() -> None:
    white = atlas.build_frame("white")
    assert set(white) == {0x11}
    for role, candidate in (("target_u04", 4), ("target_u07", 7)):
        frame = atlas.build_frame(role)
        for roi in atlas.frozen_rois():
            rect = roi["rect"]
            codes = {
                atlas._pixel(frame, x, y)  # noqa: SLF001 - exact fixture audit
                for y in range(rect["y0"], rect["y1_exclusive"])
                for x in range(rect["x0"], rect["x1_exclusive"])
            }
            assert codes == {candidate}
