from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import mf1750_runtime_lut_partial_hold_once as once
from tools import mf1750_runtime_lut_partial_hold_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def _identity(kind: str) -> dict[str, object]:
    return {
        "kind": f"mf1750-ec5-runtime-lut-partial-hold-{kind}",
        "build_tag": pack.BUILD_TAG,
        "test_id": pack.TEST_ID,
        "campaign_id": pack.CAMPAIGN_ID,
        "device_api_version": "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_DEVICE_V1",
        "identity_revision": "runtime-lut-partial-hold-v1",
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


def test_pack_is_disjoint_inclusive_and_exact_l535() -> None:
    report = pack.build_report()
    assert len(report["actions"]) == 5
    assert pack.WHITE_CODE == 3
    assert [item["ordinal"] for item in report["actions"]] == [1, 2, 3, 4, 5]
    assert report["contract"]["geometry"]["ptlw_endpoint"] == "inclusive"
    assert report["contract"]["cross_palette"] is False
    profile = report["contract"]["profile"]
    assert profile["cs1_r20_prefix_bytes"] == 535
    assert profile["cs2_r20_prefix_bytes"] == 535
    assert profile["cs1_r20_prefix_sha256"] == pack.ACTIVE_R20_PREFIX_SHA256
    assert profile["cs2_r20_prefix_sha256"] == pack.COMMENTED_R20_PREFIX_SHA256
    assert report["actions"][0]["frame"]["histogram"] == [
        0,
        0,
        0,
        614400,
        0,
        0,
        0,
        0,
    ]


def test_compiled_identity_matches_generated_pack() -> None:
    text = (ROOT / "src" / "ec5_runtime_lut_partial_hold_identity.inc").read_text()
    report = pack.build_report()
    assert report["contract_id"] in text
    for action in report["actions"]:
        assert action["descriptor_id"] in text
        assert action["action_id"] in text
        assert action["frame"]["sha256"] in text
        assert action["cs1_dtm"]["sha256"] in text


def test_driver_loads_exact_lut_before_window_and_uses_prefix() -> None:
    source = (ROOT / "src" / "ec5_partial_hold_driver.inc").read_text()
    body = source[source.index("bool epdDisplayCompiledChromaGrid") :]
    assert body.index("phApplyRuntimeLutGlobalConfig") < body.index(
        "phWritePartialWindow"
    )
    assert body.index("phUploadRuntimeLutToController(false)") < body.index(
        "phWritePartialWindow"
    )
    assert "ph_lut::active::kTransmittedR20PrefixBytes" in source
    assert "ph_lut::commented::kTransmittedR20PrefixBytes" in source
    assert "y + window.height - (ph::kPtlwYEndOneMore ? 0U : 1U)" in source


def test_runner_is_bound_to_built_binary() -> None:
    firmware = (
        ROOT
        / ".pio"
        / "build-runtime-lut-partial-hold"
        / "ec5_runtime_lut_partial_hold_l535_active"
        / "firmware.bin"
    )
    assert firmware.stat().st_size == once.runner.FIRMWARE_BYTES
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.runner.FIRMWARE_SHA256
    )


def test_runner_accepts_only_runtime_lut_partial_contract() -> None:
    version = {
        **_identity("version"),
        "action_count": 5,
        "automatic_execute": False,
        "automatic_chaining": False,
        "startup_refresh": False,
        "raw_frame_ingress": False,
        "runtime_lut_write": True,
        "electrical_parameter_write": False,
        "dither": False,
        "spatial_mixing": False,
        "retry": False,
        "recovery": False,
        "nvs_contract": {"namespace": pack.NVS_NAMESPACE, "key": "cursor_v1"},
        **_capabilities(),
    }
    once._validate_version(version)
    version["runtime_lut_write"] = False
    with pytest.raises(once.runner.RecheckError):
        once._validate_version(version)


def test_manifest_requires_exact_profile_and_actions() -> None:
    profile = pack.build_report()["contract"]["profile"]
    manifest = {
        **_identity("manifest"),
        "actions": list(once.runner.ACTIONS),
        "action_count": 5,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "history_layout": {
            "runtime_lut_profile_id": pack.PROFILE_ID,
            "ptlw_endpoint_contract": "xe=x+w-1;ye=y+h-1",
            "windows_disjoint": True,
            "white_transport_code": 3,
            **profile,
        },
        **_capabilities(),
    }
    once._validate_manifest(manifest)
    manifest["history_layout"]["cs2_r20_prefix_bytes"] = 799
    with pytest.raises(once.runner.RecheckError):
        once._validate_manifest(manifest)
