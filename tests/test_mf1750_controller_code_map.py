from __future__ import annotations

import hashlib
from pathlib import Path

from tools import mf1750_controller_code_map_once as once


ROOT = Path(__file__).resolve().parents[1]


def test_controller_map_artifacts_are_exactly_bound() -> None:
    binary = ROOT / once.FIRMWARE_BIN
    elf = ROOT / once.FIRMWARE_ELF
    assert binary.stat().st_size == 797616
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == once.FIRMWARE_BIN_SHA256
    assert hashlib.sha256(elf.read_bytes()).hexdigest() == once.FIRMWARE_ELF_SHA256
    once._validate_artifacts()


def test_controller_map_describe_exposes_one_unmixed_action() -> None:
    value = once.describe()
    assert value["visible_actions"] == 1
    assert value["layout"]["cs1_slot_order"] == list(range(8))
    assert value["layout"]["cs2_slot_order"] == list(reversed(range(8)))
    assert value["runtime_lut"] is True
    assert value["partial_refresh"] is False
    assert value["spatial_dithering"] is False
    assert value["automatic_chaining"] is False


def test_controller_map_context_uses_fresh_identity_and_reference_frame() -> None:
    _release, _candidate, context = once._context()
    action = context.action(1)
    binding = context.binding(1)
    assert context.release_id == once.RELEASE_ID
    assert action["hardware_action_id"] == once.ACTION_ID
    assert action["transaction_descriptor_sha256"] == once.DESCRIPTOR_ID
    assert action["payload_identity"]["frame_fnv1a"] == 0x52FA55C5
    assert binding["firmware_binary_sha256"] == once.FIRMWARE_BIN_SHA256
    assert binding["nvs_namespace"] == "ccmaplga1"
