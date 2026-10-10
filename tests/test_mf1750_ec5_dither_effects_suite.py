from __future__ import annotations

import json
from pathlib import Path

import pytest

from host import dither_effects_suite as suite
from host.epd_frame import FRAME_BYTES, HEIGHT, ROW_BYTES
from tools import mf1750_ec5_dither_effects_suite as bundle_tool


def _half_rows(frame: bytes, half: int) -> bytes:
    start = half * (suite.CONTROLLER_WIDTH // 2)
    width = suite.CONTROLLER_WIDTH // 2
    return b"".join(
        frame[y * ROW_BYTES + start : y * ROW_BYTES + start + width]
        for y in range(HEIGHT)
    )


def test_roles_have_frozen_legal_identical_half_identities() -> None:
    assert sorted(rank for row in suite.BAYER_8X8 for rank in row) == list(range(64))
    for role in suite.ROLES:
        frame = suite.build_frame(role)
        assert len(frame) == FRAME_BYTES
        assert all(
            nibble in suite.LEGAL_CODES
            for value in frame
            for nibble in (value >> 4, value & 0x0F)
        )
        assert _half_rows(frame, 0) == _half_rows(frame, 1)
        identity = suite.frame_identity(role)
        assert (
            identity.frame.sha256,
            identity.cs1_dtm.sha256,
            identity.cs2_dtm.sha256,
        ) == suite.FROZEN_ROLE_SHA256[role]
        assert identity.cs1_dtm == identity.cs2_dtm

    white = suite.build_frame(suite.ROLE_WHITE)
    assert white == b"\x11" * FRAME_BYTES


def test_pair_gradients_have_exact_endpoints_and_monotonic_window_means() -> None:
    frame = suite.build_frame(suite.ROLE_PAIR_GRADIENTS)
    for row, family in enumerate(suite.MIX_FAMILIES):
        y0 = suite.GRADIENT_Y0 + row * (
            suite.GRADIENT_ROW_HEIGHT + suite.GRADIENT_ROW_GAP
        )
        for y in range(y0, y0 + suite.GRADIENT_ROW_HEIGHT):
            assert suite.pixel_code(frame, suite.GRADIENT_X0_LOCAL, y) == family.code_a
            assert (
                suite.pixel_code(
                    frame,
                    suite.GRADIENT_X0_LOCAL + suite.GRADIENT_WIDTH - 1,
                    y,
                )
                == family.code_b
            )

        # Average 32x64 windows. Ordered-mask quantization may move one pixel
        # at a boundary, but the broad A fraction must never rise left->right.
        fractions: list[float] = []
        for x0 in range(0, suite.GRADIENT_WIDTH - 31, 32):
            a_count = 0
            total = 0
            for local_y in range(64):
                for local_x in range(x0, x0 + 32):
                    code = suite.pixel_code(
                        frame,
                        suite.GRADIENT_X0_LOCAL + local_x,
                        y0 + local_y,
                    )
                    assert code in (family.code_a, family.code_b)
                    a_count += code == family.code_a
                    total += 1
            fractions.append(a_count / total)
        assert all(
            later <= earlier + 1 / 64
            for earlier, later in zip(fractions, fractions[1:])
        )
        assert fractions[0] > 0.9
        assert fractions[-1] < 0.12


def test_effects_chart_geometry_and_diagnostic_regions_are_exact() -> None:
    frame = suite.build_frame(suite.ROLE_EFFECTS_CHART)

    # Warm triangle corners: red, yellow, then white along the bottom.
    assert suite.pixel_code(frame, 24, 24) == 3
    assert suite.pixel_code(frame, 24 + 223, 24) == 2
    assert suite.pixel_code(frame, 24, 24 + 223) == 1
    assert suite.pixel_code(frame, 24 + 223, 24 + 223) == 1

    # Cool triangle corners: blue, green, then white.
    assert suite.pixel_code(frame, 264, 24) == 5
    assert suite.pixel_code(frame, 264 + 223, 24) == 6
    assert suite.pixel_code(frame, 264, 24 + 223) == 1
    assert suite.pixel_code(frame, 264 + 223, 24 + 223) == 1

    # Neutral ramp endpoints and the six native flat blocks.
    assert suite.pixel_code(frame, 24, suite.NEUTRAL_Y0) == 0
    assert suite.pixel_code(frame, 487, suite.NEUTRAL_Y0) == 1
    for index, code in enumerate(suite.LEGAL_CODES):
        center_x = (
            suite.CHART_X0_LOCAL
            + index * (suite.BLOCK_WIDTH + suite.BLOCK_GAP)
            + suite.BLOCK_WIDTH // 2
        )
        assert (
            suite.pixel_code(frame, center_x, suite.BLOCK_Y0 + suite.BLOCK_HEIGHT // 2)
            == code
        )

    # Each edge zone must contain both black and white and repeat by its
    # declared 1/2/4/8-pixel feature width.
    zone_width = suite.CHART_WIDTH // 4
    for zone, feature_width in enumerate((1, 2, 4, 8)):
        x0 = suite.CHART_X0_LOCAL + zone * zone_width
        samples = [
            suite.pixel_code(frame, x0 + x, suite.DETAIL_Y0)
            for x in range(feature_width * 2)
        ]
        assert samples == [1] * feature_width + [0] * feature_width


def test_layout_manifest_is_explicitly_offline_and_non_colorimetric() -> None:
    manifest = suite.layout_manifest()
    assert manifest["hardware_tested"] is False
    assert manifest["hardware_execution_authorized"] is False
    assert manifest["runtime_lut_or_waveform_changed"] is False
    assert manifest["spatial_mixing_only"] is True
    assert manifest["single_pixel_multi_pigment_claim"] is False
    assert manifest["controller_halves_are_semantically_identical"] is True
    interpretation = manifest["interpretation"]
    assert interpretation["nominal_rgb_preview_is_not_colorimetric_prediction"]
    assert not interpretation["new_physical_pixel_state_claimed"]
    assert not interpretation["measured_colour_claimed"]
    assert (
        manifest["integrity"]["canonical_sha256"]
        == "6916cec7b87d8ad7c80b44d6f9a1c95f556320a90ef2ad28da36319773bbf56c"
    )


def test_bundle_build_validate_and_tamper_rejection(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    built = bundle_tool.build_bundle(output)
    assert built["file_count"] == 9
    assert built["hardware_tested"] is False
    assert built["device_io_performed"] is False
    assert built["network_io_performed"] is False
    assert built["visible_refresh_authorized"] is False
    assert bundle_tool.validate_bundle(output) == built

    manifest = json.loads((output / "bundle-manifest.json").read_text("utf-8"))
    assert manifest["new_target_frame_count"] == 2
    assert manifest["planned_new_visible_actions"] == 4
    assert manifest["extends_existing_block_atlas_pair_without_modifying_it"]

    frame = output / "pair-gradients.frame.bin"
    payload = bytearray(frame.read_bytes())
    payload[1234] ^= 0x10
    frame.write_bytes(payload)
    with pytest.raises(
        bundle_tool.DitherEffectsBundleError,
        match="differs from deterministic regeneration",
    ):
        bundle_tool.validate_bundle(output)
