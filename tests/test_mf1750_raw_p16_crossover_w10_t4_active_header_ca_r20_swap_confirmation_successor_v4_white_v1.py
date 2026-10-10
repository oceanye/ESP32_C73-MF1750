from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_pack as source,
)
from tools import (
    mf1750_raw_p16_crossover_w10_t4_active_header_ca_r20_swap_confirmation_successor_v4_white_v1_build as build,
)
from tools import (
    mf1750_raw_p16_crossover_w10_t4_active_header_ca_r20_swap_confirmation_successor_v4_white_v1_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w10_t4_active_header_ca_r20_swap_confirmation_successor_v4_white_v1_pack as w10,
)
from tools import (
    mf1750_raw_p16_crossover_w9_w8_arm400_successor_white_v1_pack as w9,
)


ROOT = Path(__file__).resolve().parents[1]


def _deep_result(state: str) -> dict[str, Any]:
    bound = w10.build_white_report()["contract"]["source"]
    return {
        "verified": True,
        "terminal_state": state,
        "campaign_id": bound["campaign_id"],
        "contract_id": bound["contract_id"],
        "descriptor_id": bound["descriptor_id"],
        "action_id": bound["action_id"],
        "firmware_sha256": bound["firmware"]["bin_sha256"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "action_must_not_be_retried": True,
        "source_success_claimed": state == "COMPLETE",
    }


def _terminal_evidence(state: str) -> dict[str, Any]:
    report = source.build_report()
    action = deepcopy(report["actions"][0])
    terminal = {
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "terminal_state": state,
        "result": state == "COMPLETE",
        "campaign_complete": state == "COMPLETE",
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "next_ordinal": 2,
        "no_retry": True,
    }
    common: dict[str, Any] = {
        "action": action,
        "action_must_not_be_retried": True,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "terminal_report": terminal,
    }
    if state == "COMPLETE":
        common.update(
            {
                "kind": (
                    "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
                    "swap-confirmation-successor-v4-result"
                ),
                "outcome": "complete_pass",
                "visible_refreshes": 1,
            }
        )
    else:
        common.update(
            {
                "kind": (
                    "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
                    "swap-confirmation-successor-v4-terminal-fault-reconciliation"
                ),
                "outcome": "fault_salvaged_read_only",
                "terminal_state": "FAULT",
                "terminal_report_strictly_validated": True,
                "partial_visible_panel_mutation_possible": True,
                "panel_state_qualified": False,
                "matched_swap_complete": False,
            }
        )
    unsigned = deepcopy(common)
    common["integrity"] = {
        "algorithm": "sha256-canonical-json-without-integrity",
        "sha256": w10.sha256_bytes(w10.canonical_json(unsigned)),
    }
    return common


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_w10_exactly_binds_fresh_t4_v4_and_one_factory_white() -> None:
    report = w10.build_white_report()
    source_report = source.build_report()
    source_action = source_report["actions"][0]
    action = report["action"]
    contract = report["contract"]

    assert (
        action["source_campaign_id"],
        action["source_contract_id"],
        action["source_descriptor_id"],
        action["source_action_id"],
    ) == (
        source_report["contract"]["campaign_id"],
        source_report["contract_id"],
        source_action["descriptor_id"],
        source_action["action_id"],
    )
    assert contract["accepted_source_terminal_states"] == ["COMPLETE"]
    assert contract["source_fault_policy"] == (
        "FAULT_RESERVED_FAIL_CLOSED_NOT_CURRENTLY_ADMISSIBLE"
    )
    assert contract["source_fault_is_not_success"] is True
    assert contract["action_count"] == 1
    assert contract["one_visible_refresh_per_action"] is True
    assert contract["factory_otp_white_only"] is True
    assert contract["runtime_payload"] is False
    assert contract["runtime_lut_write"] is False
    assert contract["custom_waveform_write"] is False
    assert contract["retry"] is False
    assert contract["automatic_recovery"] is False
    assert contract["autochain"] is False


def test_w10_has_fresh_route_nvs_action_and_complete_tombstones() -> None:
    report = w10.build_white_report()
    contract = report["contract"]
    action = report["action"]
    source_action = source.build_report()["actions"][0]

    assert w10.CONFIG.nvs_namespace == "p16w10t4ca4v1"
    assert w10.CONFIG.nvs_key == "used_w10t4ca4"
    assert len(w10.CONFIG.nvs_namespace) <= 15
    assert len(w10.CONFIG.nvs_key) <= 15
    assert w10.CONFIG.base_route.endswith(
        "/raw-p16-crossover-w10-after-t4-active-header-ca-r20-"
        "swap-confirmation-successor-v4-white-v1"
    )
    assert w9.build_white_report()["action"]["action_id"] in contract[
        "rejected_obsolete_white_action_ids"
    ]
    assert source_action["action_id"] in contract[
        "rejected_obsolete_experimental_action_ids"
    ]
    assert action["action_id"] not in {
        *contract["rejected_obsolete_white_action_ids"],
        *contract["rejected_obsolete_experimental_action_ids"],
    }


def test_w10_identity_selector_routes_and_intents_are_exact() -> None:
    identity = (
        ROOT
        / "src/ec5_raw_p16_crossover_w10_t4_active_header_ca_r20_swap_"
        "confirmation_successor_v4_white_v1_identity.inc"
    ).read_text(encoding="utf-8")
    program = (
        ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    ).read_text(encoding="utf-8")
    config = (
        ROOT
        / "platformio.raw_p16_crossover_w10_t4_active_header_ca_r20_swap_"
        "confirmation_successor_v4_white_v1.ini"
    ).read_text(encoding="utf-8")
    selector = (
        "MF1750_RAW_P16_CROSSOVER_W10_T4_ACTIVE_HEADER_CA_R20_SWAP_"
        "CONFIRMATION_SUCCESSOR_V4_WHITE_V1_BUILD"
    )
    assert w10.validate_identity_source()["marker"] == w10.marker()
    assert "0" * 64 not in identity
    assert selector in program
    assert f"{selector}=1" in config
    assert "upload_protocol" not in config
    assert "upload_command" not in config
    assert "MF1750_ENABLE_FACTORY_OTP_WHITE_RECOVERY=1" in config
    assert "MF1750_RAW_P16_CROSSOVER_WHITE_CONTAINMENT=1" in config
    assert '"/api/ec5/raw-p16-crossover-"' in program
    route_tail = w10.CONFIG.route_slug.removeprefix("raw-p16-crossover-")
    for endpoint in ("version", "manifest", "status", "report", "arm", "execute"):
        assert f'"{route_tail}/{endpoint}"' in program
    assert w10.shared_firmware_intents() == {
        "arm": w10.WHITE_ARM_INTENT,
        "execute": w10.WHITE_EXECUTE_INTENT,
    }


def test_w10_accepts_only_deep_validated_complete_terminal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    complete = tmp_path / "action-01-position-balanced-atlas.json"
    fault = tmp_path / "action-01-terminal-read-only-salvage-reconciled.json"
    _write_json(complete, _terminal_evidence("COMPLETE"))
    monkeypatch.setattr(
        once,
        "_source_terminal_paths",
        lambda: {"COMPLETE": complete, "FAULT": fault},
    )
    monkeypatch.setattr(
        once.source_once,
        "validate_terminal_evidence",
        lambda path: _deep_result("COMPLETE") if path == complete.resolve() else None,
        raising=False,
    )

    value = once._validate_source_terminal_evidence()  # noqa: SLF001
    assert value["verified"] is True
    assert value["source_terminal_state"] == "COMPLETE"
    assert value["source_success_claimed"] is True
    assert value["branch"] == "SOURCE_COMPLETE_SUCCESS_BOUND_WHITE"
    assert value["source_fault_policy"] == w10.FAULT_POLICY


def test_w10_rejects_fault_as_reserved_and_not_currently_admissible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    complete = tmp_path / "action-01-position-balanced-atlas.json"
    fault = tmp_path / "action-01-terminal-read-only-salvage-reconciled.json"
    _write_json(fault, _terminal_evidence("FAULT"))
    monkeypatch.setattr(
        once,
        "_source_terminal_paths",
        lambda: {"COMPLETE": complete, "FAULT": fault},
    )
    with pytest.raises(once.W10RunnerError, match=w10.FAULT_POLICY):
        once._validate_source_terminal_evidence()  # noqa: SLF001


def test_w10_rejects_ambiguous_complete_and_fault_even_with_explicit_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    complete = tmp_path / "action-01-position-balanced-atlas.json"
    fault = tmp_path / "action-01-terminal-read-only-salvage-reconciled.json"
    _write_json(complete, _terminal_evidence("COMPLETE"))
    _write_json(fault, _terminal_evidence("FAULT"))
    monkeypatch.setattr(
        once,
        "_source_terminal_paths",
        lambda: {"COMPLETE": complete, "FAULT": fault},
    )
    with pytest.raises(once.W10RunnerError, match=w10.FAULT_POLICY):
        once._validate_source_terminal_evidence(complete)  # noqa: SLF001


def test_w10_rejects_shallow_valid_terminal_when_deep_firmware_differs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    complete = tmp_path / "action-01-position-balanced-atlas.json"
    fault = tmp_path / "action-01-terminal-read-only-salvage-reconciled.json"
    _write_json(complete, _terminal_evidence("COMPLETE"))
    monkeypatch.setattr(
        once,
        "_source_terminal_paths",
        lambda: {"COMPLETE": complete, "FAULT": fault},
    )
    deep = _deep_result("COMPLETE")
    deep["firmware_sha256"] = "f" * 64
    monkeypatch.setattr(
        once.source_once,
        "validate_terminal_evidence",
        lambda _path: deep,
        raising=False,
    )
    with pytest.raises(once.W10RunnerError, match="firmware_sha256"):
        once._validate_source_terminal_evidence()  # noqa: SLF001


def test_w10_live_cli_rejects_missing_source_before_host_or_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(once, "_verify_artifacts", lambda: events.append("artifacts"))
    monkeypatch.setattr(
        once,
        "_source_terminal_paths",
        lambda: {
            "COMPLETE": tmp_path / "missing-complete.json",
            "FAULT": tmp_path / "missing-fault.json",
        },
    )
    monkeypatch.setattr(once, "_configure_white", lambda: events.append("host"))
    assert (
        once.main(
            [
                "diagnose-white-j2-off",
                "--base-url",
                "http://must-not-be-used.invalid",
                "--confirm-j2-off",
            ]
        )
        == 2
    )
    assert events == ["artifacts"]


def test_w10_sealed_artifacts_match_and_embed_exact_identity() -> None:
    if not w10.artifacts_are_sealed():
        pytest.skip("isolated W10 artifacts not sealed yet")
    report = w10.build_white_report()
    expected = w10.WHITE_ARTIFACTS[w10.STAGE]
    for label, path, byte_key, sha_key in (
        ("bin", w10.white_artifact_paths()[0], "bin_bytes", "bin_sha256"),
        ("elf", w10.white_artifact_paths()[1], "elf_bytes", "elf_sha256"),
    ):
        payload = path.read_bytes()
        assert len(payload) == expected[byte_key], label
        assert hashlib.sha256(payload).hexdigest() == expected[sha_key], label
        for value in (
            w10.CONFIG.campaign_id,
            w10.CONFIG.build_tag,
            report["contract_id"],
            report["action"]["descriptor_id"],
            report["action"]["action_id"],
            report["action"]["source_contract_id"],
            w10.marker(),
            w10.WHITE_ARM_INTENT,
            w10.WHITE_EXECUTE_INTENT,
        ):
            assert value.encode("ascii") in payload, (label, value)


def test_w10_builder_is_compile_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pio = tmp_path / "pio.exe"
    pio.touch()
    commands: list[list[str]] = []
    monkeypatch.setattr(build, "prebuild_validate", lambda: {"result": "PASS"})
    monkeypatch.setattr(
        build.runner,
        "dry_validate",
        lambda **_kwargs: {"result": "PASS", "artifacts_verified": True},
    )
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda command, **_kwargs: commands.append(command),
    )
    result = build.build(pio=pio)
    assert result["result"] == "PASS"
    assert commands == [[str(pio.resolve()), "run", "-c", build.CONFIG]]
    assert "upload" not in commands[0]
