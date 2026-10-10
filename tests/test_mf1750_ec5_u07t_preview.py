from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import mf1750_ec5_u07t_identity as identity
from tools import mf1750_ec5_u07t_preview as preview


def test_preview_exact_frame_and_no_dither_contract() -> None:
    manifest, files = preview.build_bundle()
    assert manifest["classification"] == "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED"
    assert manifest["action_id"] == identity.FROZEN_ACTION_ID
    assert manifest["raw"]["sha256"] == identity.FRAME_SHA256
    assert manifest["geometry"]["candidate_pixels"] == 8192
    assert manifest["geometry"]["dithering_present"] is False
    assert manifest["geometry"]["spatial_mixing_present"] is False
    assert files[preview.RAW_FILE] == preview.generate_frame()


def test_preview_publish_and_deep_validate(tmp_path: Path) -> None:
    manifest = preview.generate(tmp_path)
    report = preview.validate(manifest)
    assert report["valid"] is True
    assert report["classification"] == "TECHNICAL_DESCRIPTIVE_NOT_QUALIFIED"
    assert report["hardware_execution_authorized"] is False


def test_preview_rejects_manifest_tamper(tmp_path: Path) -> None:
    manifest = preview.generate(tmp_path)
    value = json.loads(manifest.read_text(encoding="utf-8"))
    value["formal_u07_qualification_inferred"] = True
    manifest.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(preview.U07TPreviewError):
        preview.validate(manifest)


def test_preview_rejects_raw_tamper(tmp_path: Path) -> None:
    manifest = preview.generate(tmp_path)
    raw = manifest.parent / preview.RAW_FILE
    payload = bytearray(raw.read_bytes())
    payload[0] ^= 1
    raw.write_bytes(payload)
    with pytest.raises(preview.U07TPreviewError):
        preview.validate(manifest)
