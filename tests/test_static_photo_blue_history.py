from __future__ import annotations

import json
from pathlib import Path

from host.epd_frame import FRAME_BYTES, unpack_pixels
from host.static_photo.blue_history import (
    batch_rois,
    build_batch_frame,
    build_blue_history_bundle,
)
from host.static_photo.history_palette import TRANSPORT_CODES


def test_blue_history_batches_cover_each_recipe_on_both_controllers() -> None:
    first = batch_rois("A")
    mirrored = batch_rois("A-prime")
    assert len(first) == len(mirrored) == 16
    assert {roi.recipe_id for roi in first} == {roi.recipe_id for roi in mirrored}
    first_controller = {roi.recipe_id: roi.controller for roi in first}
    mirrored_controller = {roi.recipe_id: roi.controller for roi in mirrored}
    assert all(
        first_controller[key] != mirrored_controller[key] for key in first_controller
    )
    assert {(roi.source_code, roi.target_code) for roi in first} == {
        (source, target) for source in range(8) for target in (4, 7)
    }


def test_blue_history_frames_and_bundle_are_exact(tmp_path: Path) -> None:
    for batch in ("A", "A-prime"):
        for role in ("primer", "target", "white"):
            frame = build_batch_frame(batch, role)  # type: ignore[arg-type]
            assert len(frame) == FRAME_BYTES
            codes = unpack_pixels(frame, allowed_colors=TRANSPORT_CODES)
            assert set(codes).issubset(set(TRANSPORT_CODES))
            if role == "white":
                assert set(codes) == {1}
    result = build_blue_history_bundle(tmp_path / "bundle")
    manifest = json.loads(
        (tmp_path / "bundle" / "BLUE-HISTORY-MANIFEST.json").read_text("utf-8")
    )
    assert result["recipe_count"] == 16
    assert result["visible_action_count"] == 6
    assert manifest["normal_action_relay_cycles"] == 0
    assert manifest["live_authorized"] is False
    assert manifest["device_io_performed"] is False
    assert len(list((tmp_path / "bundle").glob("*.bin"))) == 6
    assert len(list((tmp_path / "bundle").glob("*.png"))) == 6
