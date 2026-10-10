from __future__ import annotations

from collections import Counter
import json

from tools.mf1750_ec5_chroma_grid import (
    CONTROLLER_BYTES,
    FRAME_BYTES,
    Role,
    build_manifest,
    controller_stream,
    semantic_sequences,
    write_bundle,
)


def test_chroma_grid_has_exact_five_action_history_and_coverage() -> None:
    manifest, frames = build_manifest()
    assert [action["role"] for action in manifest["actions"]] == [
        "white",
        "source",
        "mid",
        "target",
        "white",
    ]
    assert manifest["visible_action_count"] == 5
    assert manifest["automatic_chaining"] is False
    assert manifest["retry_allowed"] is False
    assert manifest["runtime_lut_write_present"] is False
    assert manifest["otp_write_present"] is False
    assert manifest["live_authorized"] is False
    assert all(len(frame) == FRAME_BYTES for frame in frames.values())

    sequences = semantic_sequences()
    assert len(sequences) == 128
    counts = Counter(
        (record["controller"], record["source"], record["mid"], record["target"])
        for record in sequences
    )
    assert set(counts.values()) == {1}
    assert len(counts) == 128


def test_histograms_and_controller_streams_are_exact() -> None:
    manifest, frames = build_manifest()
    assert manifest["frames"]["white"]["histogram"] == [
        0,
        614400,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert manifest["frames"]["source"]["histogram"] == [
        53248,
        241664,
        53248,
        53248,
        53248,
        53248,
        53248,
        53248,
    ]
    assert manifest["frames"]["mid"]["histogram"] == [
        0,
        188416,
        0,
        0,
        212992,
        0,
        0,
        212992,
    ]
    assert manifest["frames"]["target"]["histogram"] == [
        0,
        188416,
        106496,
        106496,
        0,
        106496,
        106496,
        0,
    ]
    for frame in frames.values():
        assert len(controller_stream(frame, 0)) == CONTROLLER_BYTES
        assert len(controller_stream(frame, 1)) == CONTROLLER_BYTES


def test_bundle_is_create_only_and_self_consistent(tmp_path) -> None:
    output = tmp_path / "bundle"
    manifest = write_bundle(output)
    stored = json.loads((output / "manifest.json").read_text("utf-8"))
    assert stored == manifest
    assert len(list(output.glob("*.bin"))) == 4
    assert len(list(output.glob("*.png"))) == 4
    for role in Role:
        assert (output / f"{role.value}.bin").stat().st_size == FRAME_BYTES
