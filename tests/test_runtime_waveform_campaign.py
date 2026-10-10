from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest

from host.runtime_waveform import campaign, contracts


CREATED_AT = "2026-08-10T09:10:00+08:00"


def test_campaign_has_exact_twelve_action_order_and_safe_stops() -> None:
    manifest = campaign.build_placeholder_campaign(created_at=CREATED_AT)
    assert manifest["action_count"] == 12
    assert manifest["materialized_action_count"] == 0
    assert [action["ordinal"] for action in manifest["actions"]] == list(range(1, 13))
    assert [action["safe_stop_after"] for action in manifest["actions"]] == [
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
        False,
        False,
        True,
    ]
    assert [action["predecessor_ordinal"] for action in manifest["actions"]] == [
        None,
        *range(1, 12),
    ]


def test_profiles_and_actions_remain_unmaterialized_without_fake_hashes() -> None:
    manifest = campaign.build_placeholder_campaign(created_at=CREATED_AT)
    assert [profile["profile_slot"] for profile in manifest["profile_placeholders"]] == [
        "K0",
        "C1",
        "C2",
    ]
    for profile in manifest["profile_placeholders"]:
        assert profile["profile_manifest_sha256"] is None
        assert profile["payload_identity_available"] is False
    for action in manifest["actions"]:
        assert action["materialized"] is False
        assert action["profile_manifest_sha256"] is None
        assert action["cs1_payload_sha256"] is None
        assert action["cs2_payload_sha256"] is None
        assert action["action_identity_sha256"] is None
        assert action["visible_refresh_authorized"] is False
    assert manifest["firmware_binary_generated"] is False
    assert manifest["authorization_token_generated"] is False


def test_atlas_and_matrix_cover_both_controllers_with_reversal() -> None:
    layouts = campaign.build_layouts()
    atlas = layouts["atlas"]["rois"]
    for controller in ("CS1", "CS2"):
        subset = [roi for roi in atlas if roi["controller"] == controller]
        assert len(subset) == 8
        assert sorted(roi["transport_code"] for roi in subset) == list(range(8))
        assert all(roi["contains_text"] is False for roi in subset)
    assert [roi["transport_code"] for roi in atlas[:8]] == list(range(8))
    assert [roi["transport_code"] for roi in atlas[8:]] == list(reversed(range(8)))

    matrix = layouts["transition_matrix"]["rois"]
    for controller in ("CS1", "CS2"):
        subset = [roi for roi in matrix if roi["controller"] == controller]
        assert len(subset) == 64
        assert {(roi["old_code"], roi["new_code"]) for roi in subset} == {
            (old, new) for old in range(8) for new in range(8)
        }
        assert all(roi["contains_text"] is False for roi in subset)
    cs1_zero = next(
        roi for roi in matrix if roi["controller"] == "CS1" and roi["old_code"] == 0 and roi["new_code"] == 0
    )
    cs2_zero = next(
        roi for roi in matrix if roi["controller"] == "CS2" and roi["old_code"] == 0 and roi["new_code"] == 0
    )
    assert cs1_zero["x"] < 256 and cs1_zero["y"] < 300
    assert cs2_zero["x"] > 768 and cs2_zero["y"] > 300


def test_bundle_build_is_deterministic_and_contains_no_firmware(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    left = campaign.write_placeholder_bundle(first, created_at=CREATED_AT)
    right = campaign.write_placeholder_bundle(second, created_at=CREATED_AT)
    assert left == right
    assert left["valid"] is True
    assert left["file_count"] == 9
    assert left["firmware_binary_generated"] is False
    first_files = {
        str(path.relative_to(first)): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        str(path.relative_to(second)): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    assert not any(path.suffix.lower() in {".bin", ".elf"} for path in first.rglob("*"))
    assert not any("runtime-waveform-live" in str(path) for path in first.rglob("*"))


def test_previews_are_exact_panel_geometry_and_declared_pseudocolor(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    campaign.write_placeholder_bundle(bundle, created_at=CREATED_AT)
    previews = sorted((bundle / "preview").glob("*.png"))
    assert len(previews) == 4
    assert all("PSEUDOCOLOR-NOT-PHYSICAL" in path.name for path in previews)
    for path in previews:
        with Image.open(path) as image:
            assert image.size == (1024, 600)
            assert image.mode == "RGB"
    manual = (bundle / "MANUAL-OBSERVATION-TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    assert "不得据此授权" in manual
    assert "Pseudocolor 不是物理颜色预测" in manual


def test_bundle_validator_rejects_materialization_tamper(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    campaign.write_placeholder_bundle(bundle, created_at=CREATED_AT)
    manifest_path = bundle / "campaign.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["actions"][0]["materialized"] = True
    manifest_path.write_bytes(contracts.canonical_json_bytes(manifest))
    with pytest.raises(campaign.PlaceholderCampaignError, match="frozen contract"):
        campaign.validate_placeholder_bundle_directory(bundle)


def test_cli_build_validate_and_exclusive_output(tmp_path: Path) -> None:
    tool = Path("tools/mf1750_runtime_waveform_campaign.py")
    bundle = tmp_path / "cli-bundle"
    built = subprocess.run(
        [
            sys.executable,
            str(tool),
            "build",
            "--output",
            str(bundle),
            "--created-at",
            CREATED_AT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert built.returncode == 0
    assert json.loads(built.stdout)["visible_refresh_authorized"] is False
    validated = subprocess.run(
        [sys.executable, str(tool), "validate", "--bundle", str(bundle)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 0
    assert json.loads(validated.stdout)["materialized_action_count"] == 0
    duplicate = subprocess.run(
        [
            sys.executable,
            str(tool),
            "build",
            "--output",
            str(bundle),
            "--created-at",
            CREATED_AT,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert duplicate.returncode == 2
    assert "already exists" in duplicate.stderr
