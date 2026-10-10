from __future__ import annotations

from pathlib import Path

import pytest

from tools import mf1750_ec5_dither_effects_extension_compiled_identity as gate
from tools import mf1750_ec5_dither_effects_extension_contract as contract


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".pio/build/esp32-s3-devkitc-1-ec5-dither-effects-extension"


def test_real_build_deep_identity_is_exact() -> None:
    report = gate.validate_artifacts(BUILD / "firmware.elf", BUILD / "firmware.bin")
    assert report["valid"] is True
    assert report["offline"] is True
    assert report["device_io_performed"] is False
    assert report["network_io_performed"] is False
    assert report["upload_performed"] is False
    assert report["visible_refreshes"] == 0
    assert report["contract_id"] == contract.campaign_manifest()["contract_id"]
    assert report["main"]["action_count"] == 4
    assert report["driver"]["role_count"] == 3
    assert [row["action_id"] for row in report["main"]["actions"]] == [
        row["hardware_action_id"] for row in contract.DESCRIPTORS
    ]
    assert report["executable"]["display_direct_call_count"] == 1
    assert report["executable"]["fixture_validator_direct_call_count"] == 1
    assert report["executable"]["fixture_main_files"] == [
        "ec5_dither_effects_extension_main.cpp"
    ]
    assert report["firmware"]["binary_elf_link"]["exact_match"] is True


def test_binary_with_appended_raw_frame_endpoint_fails_closed(tmp_path: Path) -> None:
    tampered = tmp_path / "firmware.bin"
    tampered.write_bytes((BUILD / "firmware.bin").read_bytes() + b"/api/frame\0")
    with pytest.raises(
        gate.DitherEffectsExtensionCompiledIdentityError,
        match="forbidden fixture identity or mutation endpoint",
    ):
        gate.validate_artifacts(BUILD / "firmware.elf", tampered)


def test_reusing_atlas_gate_does_not_leak_the_extension_profile() -> None:
    from tools import mf1750_ec5_dither_color_atlas_compiled_identity as atlas_gate

    original_contract = atlas_gate.contract
    gate.required_identity_strings()
    assert atlas_gate.contract is original_contract
    assert atlas_gate.EXPECTED_MAIN_FILE == "ec5_dither_color_atlas_main.cpp"
