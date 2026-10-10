from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_runtime_lut_partial_hold_v3_containment_white_once as once


ROOT = Path(__file__).resolve().parents[1]


def test_containment_firmware_is_bound_and_contains_fresh_identity() -> None:
    binary = ROOT / once.base.FIRMWARE_BIN
    elf = ROOT / once.base.FIRMWARE_ELF
    assert binary.stat().st_size == 785936
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == (
        once.base.FIRMWARE_BIN_SHA256
    )
    assert hashlib.sha256(elf.read_bytes()).hexdigest() == (
        once.base.FIRMWARE_ELF_SHA256
    )
    for marker in (
        once.base.BUILD_TAG,
        once.base.NVS_NAMESPACE,
        once.base.DESCRIPTOR_MARKER,
    ):
        assert marker.encode("ascii") in elf.read_bytes()


def test_containment_describe_is_offline_and_not_automatic() -> None:
    value = once.describe()
    assert value["hardware_action_id"] == once.base.ACTION_ID
    assert value["nvs_namespace"] == "rlphv3cw"
    assert value["automatic_execution"] is False
    assert value["network_requests"] == 0
    assert value["visible_refreshes"] == 0
    assert value["prior_runtime_claim_sha256"] == once.PRIOR_RUNTIME_CLAIM_SHA256
    assert value["prior_runtime_result_sha256"] == once.PRIOR_RUNTIME_RESULT_SHA256


def test_containment_accepts_only_exact_v3_runtime_evidence() -> None:
    once._validate_v3_runtime_evidence()
