from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import mf1750_ec5_pilot_preview as preview


@pytest.mark.parametrize("candidate", [4, 7])
def test_preview_is_exact_pseudocolour_render_of_frozen_pilot(
    tmp_path: Path, candidate: int
) -> None:
    manifest_path = preview.generate(tmp_path, candidate)
    report = preview.validate(manifest_path)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert report["valid"] is True
    assert value["geometry"]["candidate_pixels"] == 8192
    assert value["geometry"]["dithering_present"] is False
    assert value["preview"]["semantic"].endswith(
        "not-physical-colour-prediction"
    )
    assert value["raw"]["sha256"] == preview.FROZEN[candidate]["frame_sha256"]
    assert value["controller_streams"]["CS1"] == value["controller_streams"]["CS2"]


def test_raw_or_preview_tamper_fails(tmp_path: Path) -> None:
    manifest_path = preview.generate(tmp_path, 4)
    raw = manifest_path.parent / "u04_pilot.raw"
    raw.write_bytes(raw.read_bytes()[:-1] + b"\x00")
    with pytest.raises(preview.PilotPreviewError, match="asset u04_pilot.raw differs"):
        preview.validate(manifest_path)


def test_manifest_tamper_fails_even_when_json_is_valid(tmp_path: Path) -> None:
    manifest_path = preview.generate(tmp_path, 7)
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    value["hardware_execution_authorized"] = True
    manifest_path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(preview.PilotPreviewError, match="manifest differs"):
        preview.validate(manifest_path)
