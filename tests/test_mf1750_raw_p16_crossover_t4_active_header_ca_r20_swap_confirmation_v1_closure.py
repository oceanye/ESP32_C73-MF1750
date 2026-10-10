from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v2_pack as source,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_build as builder,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_pack as pack,
)


ROOT = Path(__file__).resolve().parents[1]


def test_fresh_matched_swap_is_byte_identical_except_controller_r20_assignment() -> (
    None
):
    validation = pack.dry_validate()
    report = pack.build_report()
    action = report["actions"][0]
    source_action = source.build_report()["actions"][0]

    assert validation["result"] == "PASS"
    assert validation["profile_tuple"] == (
        "ACTIVE_GLOBAL__CS1_COMMENTED535__CS2_ACTIVE535"
    )
    assert action["global_header"] == source_action["global_header"] == "active"
    assert action["frame"] == source_action["frame"]
    assert action["cs1_dtm"] == source_action["cs1_dtm"]
    assert action["cs2_dtm"] == source_action["cs2_dtm"]
    assert action["waveform_binding"]["cs1"] == source_action["waveform_binding"]["cs2"]
    assert action["waveform_binding"]["cs2"] == source_action["waveform_binding"]["cs1"]
    assert action["action_id"] not in pack.non_reusable_action_ids()


def test_consumed_t3_and_w4_actions_are_exactly_bound_and_non_reusable() -> None:
    t3 = pack.validate_completed_t3_v2_action()
    w4 = pack.validate_completed_w4_white_action()
    blocked = pack.non_reusable_action_ids()

    assert t3["validated"] is True
    assert w4["validated"] is True
    assert t3["binding"]["action_id"] in blocked
    assert w4["binding"]["action_id"] in blocked
    assert w4["binding"]["source_action_id"] == t3["binding"]["action_id"]
    assert w4["binding"]["formal_full_panel_white_evidence"] is False
    assert w4["binding"]["fresh_operator_clean_white_confirmation_required"] is True


def test_identity_ini_and_shared_selectors_are_exact() -> None:
    report = pack.build_report()
    action = report["actions"][0]
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_identity.inc"
    ).read_text(encoding="utf-8")
    selector = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_identity.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT / "src/ec5_raw_p16_crossover_t2_discovery_successor_main_config.inc"
    ).read_text(encoding="utf-8")
    ini = (ROOT / builder.CONFIG).read_text(encoding="utf-8")

    for value in (
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        action["prior_static_action_id"],
        pack.PROFILE_ID,
        pack.GLOBAL_TUPLE_ID,
        pack.CONFIG.campaign_id,
        pack.CONFIG.base_route,
        pack.CONFIG.nvs_namespace,
    ):
        assert value in identity or value in config
    assert "kGlobalUseCommented = false" in identity
    assert "kCs1UseCommented = true" in identity
    assert "kCs2UseCommented = false" in identity
    assert pack.completed_t3_v2_action_binding()["action_id"] in config
    assert pack.completed_w4_white_action_binding()["action_id"] in config
    assert (
        "ec5_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_identity.inc"
        in selector
    )
    assert (
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_V1_BUILD=1"
        in ini
    )
    assert "upload" not in ini.lower()


def test_runner_routes_claims_outputs_and_artifacts_are_fresh_and_sealed() -> None:
    value = once.dry_validate()
    host = once.configure()

    assert value["artifacts_verified"] is True
    assert value["default_base_url"] is None
    assert value["explicit_base_url_required_for_live_cli"] is True
    assert str(host.DEFAULT_OUTPUT).endswith(
        "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_20260831_V1"
    )
    assert str(host.DEFAULT_CLAIMS).endswith(
        ".mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_claims"
    )
    assert host.base.runner.ENDPOINTS == {
        name: f"{pack.CONFIG.base_route}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    for artifact in value["firmware_binding"].values():
        path = Path(artifact["path"])
        payload = path.read_bytes()
        assert len(payload) == artifact["bytes"]
        assert hashlib.sha256(payload).hexdigest() == artifact["sha256"]


def test_artifact_tamper_fails_before_any_live_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = pack.artifact_paths
    firmware_bin, firmware_elf = original()
    bad_bin = tmp_path / "firmware.bin"
    bad_elf = tmp_path / "firmware.elf"
    bad_bin.write_bytes(firmware_bin.read_bytes() + b"tamper")
    bad_elf.write_bytes(firmware_elf.read_bytes())
    monkeypatch.setattr(
        pack, "artifact_paths", lambda stage=pack.STAGE: (bad_bin, bad_elf)
    )

    with pytest.raises(once.T4MatchedSwapRunnerError, match="identity differs"):
        once.dry_validate()


def test_build_tool_is_compile_only_and_preflight_makes_zero_device_requests() -> None:
    value = builder.prebuild_validate()
    source_text = (
        ROOT
        / "tools/mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_build.py"
    ).read_text(encoding="utf-8")

    assert value["result"] == "PASS"
    assert value["device_requests_made"] == 0
    assert value["network_requests"] == 0
    assert value["serial_or_com_accessed"] is False
    assert value["relay_accessed"] is False
    assert value["firmware_flashed"] is False
    assert value["display_refreshed"] is False
    assert '"run", "-c", CONFIG' in source_text
    assert "upload" not in source_text.lower()
