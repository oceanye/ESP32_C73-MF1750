from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import mf1750_ec5_dither_effects_fixed_action_contract as contract
from tools import mf1750_ec5_dither_fallback_readiness as readiness


def test_extension_contract_is_four_unique_fixed_non_live_actions() -> None:
    manifest = contract.contract_manifest()
    assert len(contract.DESCRIPTORS) == 4
    assert manifest["action_count"] == 4
    assert manifest["target_count"] == 2
    assert manifest["white_recovery_count"] == 2
    assert manifest["safe_stop_ordinals"] == [2, 4]
    assert manifest["execution_eligible"] is False
    assert manifest["live_authorized"] is False
    assert manifest["runtime_lut_or_waveform_write"] is False
    assert manifest["spatial_mixing_only"] is True
    assert (
        manifest["transport_candidate"]["dedicated_extension_adapter_materialized"]
        is False
    )

    action_ids = [item["hardware_action_id"] for item in contract.DESCRIPTORS]
    assert len(set(action_ids)) == 4
    for index, item in enumerate(contract.DESCRIPTORS):
        assert item["ordinal"] == index + 1
        assert item["prior_static_action_id"] == (
            None if index == 0 else action_ids[index - 1]
        )
        assert item["request"] == {
            "method": "POST",
            "endpoint": "/api/frame",
            "body": "exact-contract-bound-canonical-frame-bytes",
            "maximum_posts": 1,
        }
        assert item["fresh_app_boot_required"] is True
        assert item["automatic_retry"] is False
        assert item["automatic_recovery"] is False
        assert item["automatic_chaining"] is False
        assert item["execution_eligible"] is False
        assert item["live_authorized"] is False


def test_readiness_deep_rebuild_materialize_and_tamper_rejection(
    tmp_path: Path,
) -> None:
    root = readiness.build_readiness()
    report = readiness.validate_readiness(root)
    assert report["valid"] is True
    assert report["full_fallback_visible_actions"] == 6
    assert report["full_fallback_targets"] == 3
    assert report["full_fallback_white_recoveries"] == 3
    assert report["additional_visible_actions_after_core"] == 4
    assert report["test_assets_ready"] is True
    assert report["full_live_execution_chain_ready"] is False
    assert report["execution_gate_reached"] is False
    assert report["live_authorized"] is False
    assert report["device_io_performed"] is False
    assert report["network_io_performed"] is False
    assert report["visible_refreshes"] == 0

    actions = root["action_sequence"]
    assert [item["fallback_ordinal"] for item in actions] == list(range(1, 7))
    assert sum(item["already_in_ten_action_core_screening"] for item in actions) == 2
    assert root["schedule"]["safe_stop_ordinals"] == [2, 4, 6]
    assert root["schedule"]["if_core_actions_9_and_10_are_committed_pass_start_at"] == 3
    assert root["schedule"]["may_be_autoappended_to_core"] is False

    path = tmp_path / "readiness.json"
    payload = readiness._write_new(path, root)
    assert readiness.validate_readiness(readiness._load(path)) == report
    assert json.loads(payload)["readiness_id"] == report["readiness_id"]

    mutated = json.loads(path.read_text("utf-8"))
    mutated["readiness"]["live_authorized"] = True
    path.write_text(
        json.dumps(mutated, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(
        readiness.DitherFallbackReadinessError,
        match="integrity differs",
    ):
        readiness.validate_readiness(readiness._load(path))
