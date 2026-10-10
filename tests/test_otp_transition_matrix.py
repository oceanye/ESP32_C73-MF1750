from __future__ import annotations

import hashlib

import pytest

from host import otp_transition_matrix as matrix
from host.epd_frame import (
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    ControllerMapping,
    controller_stream_reference,
    fnv1a,
    pixel_counts,
)


def _roi(controller: str, old_code: int, new_code: int) -> matrix.TransitionROI:
    return next(
        roi
        for roi in matrix.transition_rois()
        if roi.controller == controller
        and roi.old_code == old_code
        and roi.new_code == new_code
    )


def test_layout_covers_all_pairs_per_controller_and_reverses_cs2() -> None:
    rois = matrix.transition_rois()
    assert len(rois) == 128
    expected_pairs = {(old, new) for old in range(8) for new in range(8)}
    for controller in ("CS1", "CS2"):
        own = [roi for roi in rois if roi.controller == controller]
        assert len(own) == 64
        assert {(roi.old_code, roi.new_code) for roi in own} == expected_pairs
        assert {(roi.display_row, roi.display_column) for roi in own} == expected_pairs
        assert {roi.width for roi in own} == {56}
        assert {roi.height for roi in own} == {64}

    assert (_roi("CS1", 0, 0).x, _roi("CS1", 0, 0).y) == (32, 44)
    assert (_roi("CS1", 7, 7).x1_exclusive, _roi("CS1", 7, 7).y1_exclusive) == (
        480,
        556,
    )
    assert (_roi("CS2", 7, 7).x, _roi("CS2", 7, 7).y) == (544, 44)
    assert (
        _roi("CS2", 0, 0).x1_exclusive,
        _roi("CS2", 0, 0).y1_exclusive,
    ) == (992, 556)


def test_primer_rows_target_columns_and_background_are_exact_codes() -> None:
    primer = matrix.build_frame("primer")
    target = matrix.build_frame("target")
    assert len(primer) == FRAME_BYTES
    assert len(target) == FRAME_BYTES
    assert matrix.pixel_code(primer, 0, 0) == matrix.BACKGROUND_CODE
    assert matrix.pixel_code(target, 1023, 599) == matrix.BACKGROUND_CODE

    for roi in matrix.transition_rois():
        samples = (
            (roi.x, roi.y),
            (roi.x + roi.width // 2, roi.y + roi.height // 2),
            (roi.x1_exclusive - 1, roi.y1_exclusive - 1),
        )
        assert all(matrix.pixel_code(primer, x, y) == roi.old_code for x, y in samples)
        assert all(matrix.pixel_code(target, x, y) == roi.new_code for x, y in samples)


def test_visible_orders_are_forward_on_cs1_and_reversed_on_cs2() -> None:
    primer = matrix.build_frame("primer")
    target = matrix.build_frame("target")
    x_centers = [matrix.GRID_X0_LOCAL + column * 56 + 28 for column in range(8)]
    y_centers = [matrix.GRID_Y0 + row * 64 + 32 for row in range(8)]

    assert [matrix.pixel_code(primer, 60, y) for y in y_centers] == list(range(8))
    assert [matrix.pixel_code(target, x, 76) for x in x_centers] == list(range(8))
    assert [matrix.pixel_code(primer, 572, y) for y in y_centers] == list(
        reversed(range(8))
    )
    assert [
        matrix.pixel_code(target, matrix.CONTROLLER_WIDTH + x, 76)
        for x in x_centers
    ] == list(reversed(range(8)))


def test_pixel_histograms_preserve_equal_grid_area_and_white_background() -> None:
    outside_grid = matrix.WIDTH * matrix.HEIGHT - (
        2
        * (matrix.GRID_X1_LOCAL - matrix.GRID_X0_LOCAL)
        * (matrix.GRID_Y1 - matrix.GRID_Y0)
    )
    expected_per_code_in_grid = 2 * matrix.CELL_WIDTH * matrix.CELL_HEIGHT * 8
    expected = [expected_per_code_in_grid] * 8
    expected[matrix.BACKGROUND_CODE] += outside_grid
    for role in matrix.ROLES:
        counts = pixel_counts(
            matrix.build_frame(role), allowed_colors=matrix.TRANSPORT_CODES
        )
        assert list(counts[:8]) == expected
        assert set(counts[8:]) == {0}


def test_full_frame_and_controller_dtm_identities_are_reproducible() -> None:
    frozen = {
        "primer": {
            "frame": "01529ea97197e5435370a0eb77a9cabff167c129237952b7a627a0f4903744dc",
            "cs1": "208c3d8e03329bbba08bb54cb5f84a9568349295ed750c749aad0e29f259017f",
            "cs2": "d66c999e89ace23dd3a112c53e9ca1f7bbbc984772e08af4359dcd843740cb1c",
        },
        "target": {
            "frame": "e3f476f24176e4b5d0f196e6c3d912dabf5044f2cbac0a59bf63806d8d051a38",
            "cs1": "4a980b33107b1d0c1da6282952d5adf8c32334af46be8f2e82aceb4c30a94387",
            "cs2": "70d4f642ec98bb034de65fb350d51285e7f644dd42c5aa3e89de5b607f4643c3",
        },
    }
    for role in matrix.ROLES:
        frame = matrix.build_frame(role)
        identity = matrix.frame_identity(role)
        assert identity.role == role
        assert identity.frame.byte_count == FRAME_BYTES
        assert identity.frame.sha256 == hashlib.sha256(frame).hexdigest()
        assert identity.frame.fnv1a_u32 == fnv1a(frame)
        for half, dtm_identity in enumerate((identity.cs1_dtm, identity.cs2_dtm)):
            stream = matrix.controller_stream(frame, half)
            assert stream == controller_stream_reference(
                frame,
                ControllerMapping(half),
                allowed_colors=matrix.TRANSPORT_CODES,
            )
            assert dtm_identity.byte_count == CONTROLLER_FRAME_BYTES
            assert dtm_identity.sha256 == hashlib.sha256(stream).hexdigest()
            assert dtm_identity.fnv1a_u32 == fnv1a(stream)
        assert identity.frame.sha256 == frozen[role]["frame"]
        assert identity.cs1_dtm.sha256 == frozen[role]["cs1"]
        assert identity.cs2_dtm.sha256 == frozen[role]["cs2"]


def test_invalid_role_half_and_pixel_inputs_fail_closed() -> None:
    with pytest.raises(matrix.OtpTransitionMatrixError, match="role"):
        matrix.build_frame("white")
    with pytest.raises(matrix.OtpTransitionMatrixError, match="half"):
        matrix.controller_stream(matrix.build_frame("primer"), 2)
    with pytest.raises(matrix.OtpTransitionMatrixError, match="outside"):
        matrix.pixel_code(matrix.build_frame("primer"), -1, 0)


def test_fixture_is_explicitly_factory_otp_and_host_only() -> None:
    assert matrix.CLASSIFICATION == "FACTORY_OTP_TRANSPORT_CODE_FIXTURE_OFFLINE_ONLY"
    assert matrix.PROFILE_SOURCE == "factory_otp"
    assert matrix.CUSTOM_LUT_OR_WAVEFORM is False
    assert matrix.HARDWARE_EXECUTION_AUTHORIZED is False
