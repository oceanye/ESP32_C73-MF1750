from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from host import dither_color_atlas as atlas
from host.epd_frame import CONTROLLER_FRAME_BYTES, FRAME_BYTES, HEIGHT, WIDTH
from tools import mf1750_ec5_dither_color_atlas as tool


def _matching_roi(controller: str, row: int, column: int) -> atlas.AtlasROI:
    return next(
        roi
        for roi in atlas.atlas_rois()
        if roi.controller == controller
        and roi.display_row == row
        and roi.display_column == column
    )


def _roi_codes(frame: bytes, roi: atlas.AtlasROI) -> list[int]:
    return [
        atlas.pixel_code(frame, x, y)
        for y in range(roi.y, roi.y1_exclusive)
        for x in range(roi.x, roi.x1_exclusive)
    ]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def test_70_rois_are_in_bounds_nonoverlapping_and_all_gutters_are_white() -> None:
    rois = atlas.atlas_rois()
    assert len(rois) == 70
    assert len({roi.roi_id for roi in rois}) == 70
    assert {(roi.controller, roi.display_row, roi.display_column) for roi in rois} == {
        (controller, row, column)
        for controller in ("CS1", "CS2")
        for row in range(atlas.GRID_ROWS)
        for column in range(atlas.GRID_COLUMNS)
    }

    owned = bytearray(WIDTH * HEIGHT)
    for roi in rois:
        half_x0 = roi.source_half * atlas.CONTROLLER_WIDTH
        half_x1 = half_x0 + atlas.CONTROLLER_WIDTH
        assert roi.controller == ("CS1" if roi.source_half == 0 else "CS2")
        assert half_x0 <= roi.x < roi.x1_exclusive <= half_x1
        assert 0 <= roi.y < roi.y1_exclusive <= HEIGHT
        assert (roi.width, roi.height) == (atlas.CELL_WIDTH, atlas.CELL_HEIGHT)
        assert roi.x == (
            half_x0
            + atlas.GRID_X0_LOCAL
            + roi.display_column * (atlas.CELL_WIDTH + atlas.COLUMN_GAP)
        )
        assert roi.y == (
            atlas.GRID_Y0 + roi.display_row * (atlas.CELL_HEIGHT + atlas.ROW_GAP)
        )
        for y in range(roi.y, roi.y1_exclusive):
            start = y * WIDTH + roi.x
            stop = y * WIDTH + roi.x1_exclusive
            assert not any(owned[start:stop])
            owned[start:stop] = b"\x01" * roi.width

    frame = atlas.build_frame("atlas")
    for index, is_roi_pixel in enumerate(owned):
        if not is_roi_pixel:
            x, y = index % WIDTH, index // WIDTH
            assert atlas.pixel_code(frame, x, y) == 1


def test_controller_halves_have_identical_semantics_phase_and_dtm_bytes() -> None:
    frame = atlas.build_frame("atlas")
    for row in range(atlas.GRID_ROWS):
        for column in range(atlas.GRID_COLUMNS):
            left = _matching_roi("CS1", row, column)
            right = _matching_roi("CS2", row, column)
            assert (
                left.row_id,
                left.appearance_hypothesis,
                left.code_a,
                left.code_b,
                left.a_quarters,
                left.pattern,
                left.y,
            ) == (
                right.row_id,
                right.appearance_hypothesis,
                right.code_a,
                right.code_b,
                right.a_quarters,
                right.pattern,
                right.y,
            )
            assert right.x - left.x == atlas.CONTROLLER_WIDTH
            for local_y in range(left.height):
                for local_x in range(left.width):
                    assert atlas.pixel_code(
                        frame, left.x + local_x, left.y + local_y
                    ) == atlas.pixel_code(frame, right.x + local_x, right.y + local_y)

    cs1 = atlas.controller_stream(frame, 0)
    cs2 = atlas.controller_stream(frame, 1)
    assert len(cs1) == len(cs2) == CONTROLLER_FRAME_BYTES
    assert cs1 == cs2


def test_every_roi_has_the_exact_declared_a_b_pixel_ratio() -> None:
    frame = atlas.build_frame("atlas")
    for roi in atlas.atlas_rois():
        codes = _roi_codes(frame, roi)
        pixels = roi.width * roi.height
        assert len(codes) == pixels
        assert set(codes) <= {roi.code_a, roi.code_b}
        assert codes.count(roi.code_a) == pixels * roi.a_quarters // 4
        assert codes.count(roi.code_b) == pixels * roi.b_quarters // 4


def test_50_50_cells_are_one_pixel_checkerboards_with_fixed_top_left_phase() -> None:
    frame = atlas.build_frame("atlas")
    checkerboards = [roi for roi in atlas.atlas_rois() if roi.a_quarters == 2]
    assert len(checkerboards) == 2 * atlas.GRID_ROWS
    for roi in checkerboards:
        assert atlas.pixel_code(frame, roi.x, roi.y) == roi.code_a
        for local_y in range(roi.height):
            for local_x in range(roi.width):
                actual = atlas.pixel_code(frame, roi.x + local_x, roi.y + local_y)
                expected = roi.code_a if (local_x + local_y) % 2 == 0 else roi.code_b
                assert actual == expected
                if local_x + 1 < roi.width:
                    assert actual != atlas.pixel_code(
                        frame, roi.x + local_x + 1, roi.y + local_y
                    )
                if local_y + 1 < roi.height:
                    assert actual != atlas.pixel_code(
                        frame, roi.x + local_x, roi.y + local_y + 1
                    )


def test_frames_contain_only_factory_otp_legal_codes() -> None:
    legal = set(atlas.LEGAL_CODES)
    assert legal == {0, 1, 2, 3, 5, 6}
    for role in atlas.ROLES:
        frame = atlas.build_frame(role)
        codes = {nibble for value in frame for nibble in (value >> 4, value & 0x0F)}
        assert codes <= legal
        assert codes.isdisjoint({4, 7})


def test_frame_controller_and_layout_identities_are_frozen() -> None:
    frozen = {
        "atlas": {
            "frame": (
                "3b65803a558e91ad2112a75b158a1b696666c015829ce9fd0bce401ba96a44b7",
                0xE9ACC5C5,
            ),
            "cs1": (
                "d461f7d2473afc86410181484ef31d4f4899e1de06f518cefa15506512e6f8d1",
                0xAF615B0D,
            ),
            "cs2": (
                "d461f7d2473afc86410181484ef31d4f4899e1de06f518cefa15506512e6f8d1",
                0xAF615B0D,
            ),
            "histogram": (0, 271680, 85680, 114240, 0, 57120, 85680, 0),
        },
        "white": {
            "frame": (
                "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d",
                0x13340DC5,
            ),
            "cs1": (
                "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
                0xB7A855C5,
            ),
            "cs2": (
                "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158",
                0xB7A855C5,
            ),
            "histogram": (0, 614400, 0, 0, 0, 0, 0, 0),
        },
    }
    for role, expected in frozen.items():
        identity = atlas.frame_identity(role)
        assert (identity.frame.sha256, identity.frame.fnv1a_u32) == expected["frame"]
        assert (identity.cs1_dtm.sha256, identity.cs1_dtm.fnv1a_u32) == expected["cs1"]
        assert (identity.cs2_dtm.sha256, identity.cs2_dtm.fnv1a_u32) == expected["cs2"]
        assert identity.histogram == expected["histogram"]

    layout = atlas.layout_manifest()
    assert layout["integrity"]["canonical_sha256"] == (
        "ed7814ca126b61f7a947cc5254ecb29199114772ada1e8648d050ef80b85345f"
    )


def test_layout_manifest_is_sealed_offline_spatial_mixing_only() -> None:
    manifest = atlas.layout_manifest()
    unsigned = dict(manifest)
    integrity = unsigned.pop("integrity")
    assert integrity == {
        "canonical_sha256": hashlib.sha256(_canonical(unsigned)).hexdigest(),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    assert manifest["kind"] == "mf1750-ec5-factory-otp-dither-color-atlas-layout"
    assert manifest["profile_source"] == "factory_otp"
    assert manifest["runtime_lut_or_waveform_changed"] is False
    assert manifest["spatial_mixing_only"] is True
    assert manifest["single_pixel_multi_pigment_claim"] is False
    assert manifest["hardware_tested"] is False
    assert manifest["hardware_execution_authorized"] is False
    assert manifest["legal_codes"] == list(atlas.LEGAL_CODES)
    assert len(manifest["rois"]) == 70
    assert manifest["grid"]["controller_halves_are_semantically_identical"] is True
    assert manifest["grid"]["controller_pattern_phase_is_identical"] is True
    assert manifest["identities"] == {
        role: atlas.frame_identity(role).to_dict() for role in atlas.ROLES
    }


def test_bundle_build_validate_tamper_and_overwrite_fail_closed(tmp_path: Path) -> None:
    output = tmp_path / "atlas-bundle"
    built = tool.build_bundle(output)
    validated = tool.validate_bundle(output)
    assert built == validated
    assert built["file_count"] == len(tool.EXPECTED_FILES) == 7
    assert built["roi_count"] == 70
    assert built["hardware_tested"] is False
    assert built["visible_refresh_authorized"] is False
    assert {entry.name for entry in output.iterdir()} == tool.EXPECTED_FILES

    bundle_manifest = json.loads((output / "bundle-manifest.json").read_bytes())
    assert bundle_manifest["offline_only"] is True
    assert bundle_manifest["device_io_performed"] is False
    assert bundle_manifest["network_io_performed"] is False
    assert bundle_manifest["visible_refresh_authorized"] is False
    assert bundle_manifest["runtime_lut_or_waveform_changed"] is False
    assert bundle_manifest["spatial_mixing_only"] is True

    with pytest.raises(tool.DitherAtlasToolError, match="already exists"):
        tool.build_bundle(output)

    frame_path = output / "atlas.frame.bin"
    changed = bytearray(frame_path.read_bytes())
    changed[0] ^= 0x01
    frame_path.write_bytes(changed)
    with pytest.raises(tool.DitherAtlasToolError, match="differs"):
        tool.validate_bundle(output)

    manifest_output = tmp_path / "manifest-tamper"
    tool.build_bundle(manifest_output)
    manifest_path = manifest_output / "bundle-manifest.json"
    tampered = json.loads(manifest_path.read_bytes())
    tampered["visible_refresh_authorized"] = True
    manifest_path.write_bytes(_canonical(tampered))
    with pytest.raises(tool.DitherAtlasToolError, match="integrity differs"):
        tool.validate_bundle(manifest_output)


def test_cli_build_validate_and_rejects_all_hardware_shaped_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_args = tool.parse_args(["build", "--output-dir", str(tmp_path / "bundle")])
    validate_args = tool.parse_args(
        ["validate", "--bundle-dir", str(tmp_path / "bundle")]
    )
    assert vars(build_args) == {
        "command": "build",
        "output_dir": tmp_path / "bundle",
    }
    assert vars(validate_args) == {
        "command": "validate",
        "bundle_dir": tmp_path / "bundle",
    }

    for option in (
        "--url",
        "--serial-port",
        "--com",
        "--execute",
        "--refresh",
        "--lut",
        "--waveform",
        "--voltage",
    ):
        with pytest.raises(SystemExit):
            tool.parse_args(
                ["build", "--output-dir", str(tmp_path / "unused"), option, "x"]
            )

    output = tmp_path / "cli-bundle"
    assert tool.main(["build", "--output-dir", str(output)]) == 0
    build_report = json.loads(capsys.readouterr().out)
    assert build_report["hardware_tested"] is False
    assert build_report["visible_refresh_authorized"] is False
    assert tool.main(["validate", "--bundle-dir", str(output)]) == 0
    validate_report = json.loads(capsys.readouterr().out)
    assert validate_report == build_report


def test_white_role_is_exact_full_panel_white_and_identical_on_both_halves() -> None:
    white = atlas.build_frame("white")
    assert len(white) == FRAME_BYTES
    assert white == b"\x11" * FRAME_BYTES
    assert atlas.controller_stream(white, 0) == atlas.controller_stream(white, 1)
    assert atlas.pixel_code(white, 0, 0) == 1
    assert atlas.pixel_code(white, WIDTH - 1, HEIGHT - 1) == 1
