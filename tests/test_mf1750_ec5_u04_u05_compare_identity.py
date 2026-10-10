from __future__ import annotations

from copy import deepcopy
import hashlib

import pytest

from host.epd_frame import unpack_pixels
from tools import mf1750_ec5_u04_u05_compare_identity as subject


def test_frozen_action_and_generated_stream_identities() -> None:
    assert subject.action_id() == subject.FROZEN_ACTION_ID
    assert subject.FROZEN_ACTION_ID == (
        "70db952b1d708511e1fdcb166b43cd5828fe232562b14d341d848942787d1700"
    )
    generated = subject.generated_identity()
    assert generated == {
        "frame_bytes": 307_200,
        "frame_sha256": subject.FRAME_SHA256,
        "frame_fnv1a": subject.FRAME_FNV1A,
        "cs1_dtm_bytes": 153_600,
        "cs1_dtm_sha256": subject.CS1_DTM_SHA256,
        "cs1_dtm_fnv1a": subject.CS1_DTM_FNV1A,
        "cs2_dtm_bytes": 153_600,
        "cs2_dtm_sha256": subject.CS2_DTM_SHA256,
        "cs2_dtm_fnv1a": subject.CS2_DTM_FNV1A,
        "histogram": {"white": 598_016, "u04": 8_192, "u05": 8_192},
    }
    assert generated["cs1_dtm_sha256"] != generated["cs2_dtm_sha256"]
    assert generated["cs1_dtm_fnv1a"] != generated["cs2_dtm_fnv1a"]


def test_diagonal_crossover_pixels_and_white_background() -> None:
    pixels = unpack_pixels(subject.generate_frame(), allowed_colors=(1, 4, 5))

    def code(x: int, y: int) -> int:
        return pixels[y * 1024 + x]

    assert code(224, 188) == code(287, 251) == 4
    assert code(224, 348) == code(287, 411) == 5
    assert code(736, 188) == code(799, 251) == 5
    assert code(736, 348) == code(799, 411) == 4
    assert code(223, 188) == code(288, 251) == 1
    assert code(735, 348) == code(800, 411) == 1
    assert code(512, 300) == 1


def test_action_preimage_is_complete_and_mutation_sensitive() -> None:
    preimage = subject.action_identity_preimage()
    assert preimage["layout_id"] == "EC5_U04_U05_QUAD64_DIAGONAL_V1"
    assert preimage["operator_short_hold_skip_boundary_required"] is True
    assert preimage["thirty_minute_hold_required"] is False
    assert preimage["j2_off_diagnostic_get_requests"] == 4
    assert preimage["j2_off_diagnostic_post_requests"] == 0
    assert preimage["cs1_dtm_sha256"] != preimage["cs2_dtm_sha256"]
    mutated = deepcopy(preimage)
    mutated["cs1_dtm_fnv1a"] += 1
    assert subject.derive_action_id(mutated) != subject.FROZEN_ACTION_ID
    assert hashlib.sha256(subject.canonical_json_bytes(preimage)).hexdigest() == (
        subject.FROZEN_ACTION_ID
    )


def test_exact_frame_validator_rejects_single_pixel_change() -> None:
    changed = bytearray(subject.generate_frame())
    changed[0] = 0x14
    with pytest.raises(ValueError, match="differs"):
        subject.validate_exact_frame(bytes(changed))

