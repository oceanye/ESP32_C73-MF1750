from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools import mf1750_ec5_sixstate_nodither as assets
from tools import mf1750_ec5_sixstate_physical_once as runner
from tools import mf1750_ec5_sixstate_release as release


PANEL = {
    "board_id": "ESP32-C73",
    "model": "MF1750-C73",
    "pcb_revision": "rev-a1",
    "serial": "MF750M009T6420/1582643AGY44",
}


def source_snapshot() -> dict:
    return {
        "git_head": "a" * 40,
        "git_dirty": True,
        "git_status_sha256": runner.sha256(b" M test\n"),
        "git_status_line_count": 1,
        "relevant_sources": [
            {
                "path": path,
                "bytes": (runner.REPO_ROOT / path).stat().st_size,
                "sha256": runner.sha256((runner.REPO_ROOT / path).read_bytes()),
            }
            for path in runner.SOURCE_PATHS
        ],
    }


def firmware(candidate_id: str) -> bytes:
    variant = runner.FROZEN_VARIANTS[candidate_id]
    tokens = {variant["build_tag"], variant["test_id"], variant["layout_id"]}
    for action in runner.expected_actions(candidate_id):
        tokens.update((action["action_id"], action["frame_sha256"], action["cs1_dtm_sha256"]))
    return (f"SIXSTATE-{candidate_id}\0" + "\0".join(sorted(tokens)) + "\0END").encode("ascii")


def build_fixture(tmp_path: Path) -> tuple[Path, Path]:
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps(PANEL), encoding="utf-8")
    inputs = tmp_path / "asset-input"
    inputs.mkdir()
    manifests = {
        candidate: assets.generate_bundle(inputs, code)
        for candidate, code in (("U04", 4), ("U07", 7))
    }
    binaries = {}
    for candidate in ("U04", "U07"):
        path = tmp_path / f"{candidate}.bin"
        path.write_bytes(firmware(candidate))
        binaries[candidate] = path
    manifest, payloads = release.build_release(
        panel_file=panel,
        u04_binary=binaries["U04"],
        u07_binary=binaries["U07"],
        u04_asset_manifest=manifests["U04"],
        u07_asset_manifest=manifests["U07"],
        created_at="2026-08-09T12:00:00+08:00",
        _source_snapshot=source_snapshot(),
    )
    output = tmp_path / "release"
    manifest_path = release.publish_release(output, manifest, payloads)
    return manifest_path, panel


def test_build_publish_and_deep_validate_binds_both_candidates(tmp_path: Path) -> None:
    manifest, panel = build_fixture(tmp_path)
    report = release.validate_release(manifest, panel_file=panel)
    assert report["valid"] is True
    assert report["hardware_actions_performed"] == 0
    assert report["variants"]["U04"]["action_count"] == 9
    assert report["variants"]["U07"]["action_count"] == 9
    assert report["variants"]["U04"]["binary_sha256"] != report["variants"]["U07"]["binary_sha256"]
    for candidate in ("U04", "U07"):
        context = runner.load_release(manifest, candidate, panel_file=panel)
        assert context.panel_verified is True
        assert len(context.actions) == 9


def test_publish_refuses_overwrite(tmp_path: Path) -> None:
    manifest_path, panel = build_fixture(tmp_path)
    root = json.loads(manifest_path.read_text(encoding="utf-8"))
    with pytest.raises(release.SixStateReleaseError, match="overwrite"):
        release.publish_release(manifest_path.parent, root, {})
    assert release.validate_release(manifest_path, panel_file=panel)["valid"] is True


@pytest.mark.parametrize("target", ["binary", "asset", "manifest"])
def test_tamper_is_rejected(target: str, tmp_path: Path) -> None:
    manifest_path, panel = build_fixture(tmp_path)
    if target == "binary":
        path = manifest_path.parent / runner.FROZEN_VARIANTS["U04"]["firmware_file"]
        path.write_bytes(path.read_bytes() + b"x")
    elif target == "asset":
        path = manifest_path.parent / "assets" / "U04" / "u04_target.raw"
        payload = bytearray(path.read_bytes())
        payload[0] ^= 1
        path.write_bytes(payload)
    else:
        root = json.loads(manifest_path.read_text(encoding="utf-8"))
        root["variants"]["U04"]["actions"][0]["role"] = "target"
        unsigned = copy.deepcopy(root)
        unsigned.pop("integrity")
        root["integrity"] = {
            "canonical_sha256": runner.sha256(runner.canonical_json_bytes(unsigned)),
            "scope": runner.HASH_SCOPE,
        }
        manifest_path.write_bytes(runner.canonical_json_bytes(root) + b"\n")
    with pytest.raises(release.SixStateReleaseError):
        release.validate_release(manifest_path, panel_file=panel)


def test_wrong_panel_and_nonisolated_binary_fail(tmp_path: Path) -> None:
    manifest_path, panel = build_fixture(tmp_path)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({**PANEL, "serial": "OTHER"}), encoding="utf-8")
    with pytest.raises(release.SixStateReleaseError, match="panel"):
        release.validate_release(manifest_path, panel_file=wrong)

    # Construction itself rejects a U04 image passed as U07; no manifest is emitted.
    inputs = tmp_path / "second-assets"
    inputs.mkdir()
    u04_assets = assets.generate_bundle(inputs, 4)
    u07_assets = assets.generate_bundle(inputs, 7)
    u04_binary = tmp_path / "same.bin"
    u04_binary.write_bytes(firmware("U04"))
    with pytest.raises(release.SixStateReleaseError, match="U07 binary"):
        release.build_release(
            panel_file=panel,
            u04_binary=u04_binary,
            u07_binary=u04_binary,
            u04_asset_manifest=u04_assets,
            u07_asset_manifest=u07_assets,
            created_at="2026-08-09T12:00:00+08:00",
            _source_snapshot=source_snapshot(),
        )


@pytest.mark.parametrize(
    "forbidden",
    [
        b"MF1750_EC5_U04_MIRROR64_CENTER_V1_EXPERIMENTAL_2026-08-09",
        b"EC5-U07-I01-P01-L64M1",
        b"/api/ec5/arm\0",
        b"/api/ec5/execute\0",
        b"/api/frame\0",
    ],
)
def test_binary_rejects_stage_a_and_raw_mutation_surfaces(forbidden: bytes) -> None:
    with pytest.raises(runner.SixStatePhysicalError, match="Stage-A|forbidden route"):
        runner._validate_binary(firmware("U04") + b"\0" + forbidden, "U04")


@pytest.mark.parametrize(
    "script",
    [
        "tools/mf1750_ec5_sixstate_release.py",
        "tools/mf1750_ec5_sixstate_physical_once.py",
    ],
)
def test_stage_b_cli_starts_from_the_repository_root(script: str) -> None:
    completed = subprocess.run(
        [sys.executable, script, "--help"],
        cwd=runner.REPO_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.lower()
