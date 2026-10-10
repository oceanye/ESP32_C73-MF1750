from __future__ import annotations

import json

import pytest

from tools import mf1750_ec5_u04_u05_compare_identity as identity
from tools import mf1750_ec5_u04_u05_compare_preview as subject


def test_bundle_is_exact_diagonal_pseudocolour_preview() -> None:
    manifest, assets = subject.build_bundle()
    assert manifest["action_id"] == identity.FROZEN_ACTION_ID
    assert manifest["layout_id"] == identity.LAYOUT_ID
    assert manifest["geometry"]["rois"] == [dict(roi) for roi in identity.ROIS]
    assert manifest["geometry"]["dithering_present"] is False
    assert manifest["geometry"]["spatial_mixing_present"] is False
    assert "not-physical-colour-prediction" in manifest["preview"]["semantic"]
    assert assets[subject.RAW_FILE] == identity.generate_frame()
    assert json.loads(assets[subject.MANIFEST_FILE]) == manifest


def test_generate_validate_and_tamper_fail_closed(tmp_path) -> None:
    manifest = subject.generate(tmp_path)
    report = subject.validate(manifest)
    assert report["valid"] is True
    assert report["action_id"] == identity.FROZEN_ACTION_ID
    raw = manifest.parent / subject.RAW_FILE
    raw.write_bytes(b"\x11" * 307_200)
    with pytest.raises(subject.ComparePreviewError, match="differs"):
        subject.validate(manifest)


def test_generate_refuses_existing_destination(tmp_path) -> None:
    subject.generate(tmp_path)
    with pytest.raises(subject.ComparePreviewError, match="publish"):
        subject.generate(tmp_path)

