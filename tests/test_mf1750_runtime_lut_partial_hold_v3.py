from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_partial_hold_v3_once as once
from tools import mf1750_runtime_lut_partial_hold_v3_pack as pack


ROOT = Path(__file__).resolve().parents[1]


def test_v3_uses_evidence_derived_common_codes() -> None:
    report = pack.build_report()
    roles = report["contract"]["evidence_derived_code_roles"]
    assert roles == {
        "common_white": 7,
        "common_black": 3,
        "common_blue": 5,
        "common_green": 6,
        "code1_rejected_as_common_white": True,
    }
    assert pack.NVS_NAMESPACE == "rlph_l535a_v3"
    assert [
        (window.cs1_code, window.cs2_code) for window in pack.WINDOWS
    ] == [(3, 3), (5, 5), (6, 6)]
    assert report["actions"][0]["frame"]["histogram"] == [
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        614400,
    ]


def test_v3_compiled_identity_matches_pack() -> None:
    text = (
        ROOT / "src" / "ec5_runtime_lut_partial_hold_v3_identity.inc"
    ).read_text()
    report = pack.build_report()
    assert report["contract_id"] in text
    for action in report["actions"]:
        assert action["descriptor_id"] in text
        assert action["action_id"] in text
        assert action["frame"]["sha256"] in text
        assert f"0x{action['frame']['fnv1a']:08X}UL" in text
        assert f"0x{action['cs1_dtm']['fnv1a']:08X}UL" in text


def test_v3_runner_is_exactly_bound() -> None:
    assert once.base.runner.FIRMWARE_SHA256 == (
        "52a46202c2897450f5356d026e64e647880e35a3f523f1bab9f9db61fda1649e"
    )
    assert once.base.runner.FIRMWARE_BYTES == 793360
    assert once.base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS == 55.0


def test_v3_runner_binding_matches_build_after_release() -> None:
    firmware = (
        ROOT
        / ".pio"
        / "build-runtime-lut-partial-hold-v3"
        / "ec5_runtime_lut_partial_hold_l535_active_v3"
        / "firmware.bin"
    )
    assert firmware.stat().st_size == once.base.runner.FIRMWARE_BYTES
    assert hashlib.sha256(firmware.read_bytes()).hexdigest() == (
        once.base.runner.FIRMWARE_SHA256
    )
