from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_partial_hold_v2_once as once
from tools import mf1750_runtime_lut_partial_hold_v2_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def _identity(kind: str) -> dict[str, object]:
    return {
        "kind": f"mf1750-ec5-runtime-lut-partial-hold-{kind}",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V2",
        "identity_revision": "runtime-lut-partial-hold-v2",
        "contract_id": pack.build_report()["contract_id"],
        "classification": (
            "EXPERIMENTAL_SPD1657_L535_RUNTIME_LUT_PTLW_LOCAL_HOLD_CANDIDATE"
        ),
    }


def _capabilities() -> dict[str, bool]:
    return {
        "partial_refresh": True,
        "window_refresh": True,
        "command_0x83": True,
        "command_0x86": False,
        "mid_refresh_power_cut": False,
        "spi_frequency_sweep": False,
        "full_screen_global_refresh": True,
        "same_palette_hold_probe": True,
        "cross_palette_hold_probe": False,
    }


def test_v2_pack_changes_only_isolated_identity_and_white_baseline() -> None:
    report = pack.build_report()
    assert pack.WHITE_CODE == 1
    assert pack.NVS_NAMESPACE == "rlph_l535a_v2"
    assert report["contract"]["supersedes"]["reason"] == (
        "V1 code3 baseline observed full black"
    )
    assert report["actions"][0]["frame"]["histogram"] == [
        0,
        614400,
        0,
        0,
        0,
        0,
        0,
        0,
    ]
    assert report["actions"][0]["frame"]["sha256"] == (
        "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
    )


def test_v2_compiled_identity_matches_pack() -> None:
    text = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_v2_identity.inc"
    ).read_text()
    report = pack.build_report()
    assert report["contract_id"] in text
    for action in report["actions"]:
        assert action["descriptor_id"] in text
        assert action["action_id"] in text
        assert action["frame"]["sha256"] in text
        assert f"0x{action['frame']['fnv1a']:08X}UL" in text


def test_v2_runner_is_exactly_bound() -> None:
    assert once.v1.runner.FIRMWARE_SHA256 == (
        "a64cb04e9cc05eb6af65c7700c1fcf7bb9a769f00018648fc825545422115c9a"
    )
    assert once.v1.runner.FIRMWARE_BYTES == 793328


def test_v2_manifest_requires_code1_and_exact_profile() -> None:
    profile = pack.build_report()["contract"]["profile"]
    manifest = {
        **_identity("manifest"),
        "actions": list(once.v1.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "history_layout": {
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "windows_disjoint": True,
            "white_transport_code": 1,
            **profile,
        },
        **_capabilities(),
    }
    once.v1._validate_manifest(manifest)
    manifest["history_layout"]["white_transport_code"] = 3
    with pytest.raises(once.v1.runner.RecheckError):
        once.v1._validate_manifest(manifest)


def test_v2_runner_binding_matches_build_after_release() -> None:
    firmware = (
        ROOT
        / ".pio"
        / "build-runtime-lut-partial-hold-v2"
        / "ec5_runtime_lut_partial_hold_l535_active_v2"
        / "firmware.bin"
    )
    assert firmware.stat().st_size == once.v1.runner.FIRMWARE_BYTES
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.v1.runner.FIRMWARE_SHA256
    )
