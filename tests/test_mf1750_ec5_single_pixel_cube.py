from __future__ import annotations

from collections import Counter
import json

from tools.mf1750_ec5_single_pixel_cube import (
    CELL_PIXELS,
    CONTROLLER_BYTES,
    FRAME_BYTES,
    RECIPE_COUNT,
    Role,
    SLOTS_PER_CONTROLLER,
    TOTAL_SLOTS,
    build_manifest,
    controller_stream,
    roi_records,
    write_bundle,
)


def test_cube_covers_all_8_cubed_histories_once_without_spatial_mixing() -> None:
    records = roi_records()
    recipes = [record for record in records if record["kind"] == "recipe"]
    references = [record for record in records if record["kind"] == "reference"]
    assert len(records) == TOTAL_SLOTS == 528
    assert len(recipes) == RECIPE_COUNT == 512
    assert len(references) == 16
    keys = Counter((r["source"], r["mid"], r["target"]) for r in recipes)
    assert len(keys) == 512
    assert set(keys.values()) == {1}
    assert all(
        len([r for r in records if r["controller"] == controller])
        == SLOTS_PER_CONTROLLER
        for controller in (1, 2)
    )
    for controller in (1, 2):
        subset = [r for r in recipes if r["controller"] == controller]
        for axis in ("source", "mid", "target"):
            assert [sum(r[axis] == code for r in subset) for code in range(8)] == [
                32
            ] * 8


def test_cube_has_exact_five_full_screen_factory_otp_actions() -> None:
    manifest, frames = build_manifest()
    assert [action["role"] for action in manifest["actions"]] == [
        "white",
        "source",
        "mid",
        "target",
        "white",
    ]
    assert manifest["visible_action_count"] == 5
    assert manifest["history_design"]["unique_three_step_recipes"] == 512
    assert manifest["history_design"]["uniform_code_inside_each_roi"] is True
    assert manifest["history_design"]["spatial_mixing"] is False
    for forbidden in (
        "runtime_lut_write_present",
        "otp_write_present",
        "partial_refresh_present",
        "window_command_present",
        "interlace_0x86_present",
        "power_cut_during_refresh_present",
        "spi_sweep_present",
        "automatic_chaining",
        "retry_allowed",
        "live_authorized",
    ):
        assert manifest[forbidden] is False
    assert manifest["spi_hz"] == 1_000_000
    assert all(len(frame) == FRAME_BYTES for frame in frames.values())


def test_cube_histograms_and_controller_streams_are_balanced() -> None:
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
    expected = [58_080, 207_840, 58_080, 58_080, 58_080, 58_080, 58_080, 58_080]
    for role in (Role.SOURCE, Role.MID, Role.TARGET):
        assert manifest["frames"][role.value]["histogram"] == expected
        for controller in (0, 1):
            stream = controller_stream(frames[role], controller)
            assert len(stream) == CONTROLLER_BYTES
            counts = Counter()
            for item in stream:
                counts.update((item >> 4, item & 0x0F))
            assert [counts[code] for code in range(8)] == [
                29_040,
                103_920,
                29_040,
                29_040,
                29_040,
                29_040,
                29_040,
                29_040,
            ]
    assert 528 * CELL_PIXELS == 464_640


def test_cube_bundle_is_create_only_and_contains_auditable_maps(tmp_path) -> None:
    output = tmp_path / "cube"
    manifest = write_bundle(output)
    stored = json.loads((output / "manifest.json").read_text("utf-8"))
    assert stored == manifest
    assert len(json.loads((output / "roi-map.json").read_text("utf-8"))) == 528
    assert len((output / "roi-map.csv").read_text("utf-8").splitlines()) == 529
    assert (output / "target-annotated-layout.png").is_file()
    assert len(list(output.glob("*.bin"))) == 4
    assert len(list(output.glob("*.png"))) == 5
