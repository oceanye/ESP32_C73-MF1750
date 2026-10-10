from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from tools import (
    mf1750_raw_p16_crossover_profile_following_human_observation as human,
)
from tools import (
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as ac_pack,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CA_ROOT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RAW_P16_CROSSOVER_T2_CA_COARSE_DISCOVERY_SUCCESSOR_20260830_V2"
)
CA_ACTION = CA_ROOT / "action-01-position-balanced-atlas.json"
W3_ROOT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_RAW_P16_CROSSOVER_W3_T2_DISCOVERY_SUCCESSOR_V2_WHITE_20260830_V1"
)
W3_ACTION = W3_ROOT / "action-01-factory-otp-white.json"
W3_RELAY_OFF = W3_ROOT / "relay-post-action-protective-off-20260830-204303.json"
W3_INPUT = W3_ROOT / "human-clean-white-input-v1.json"
W3_AUTHORITY = W3_ROOT / "human-clean-white-authority-v1.json"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _integrity(value: dict[str, Any]) -> dict[str, Any]:
    root = deepcopy(value)
    root.pop("integrity", None)
    root["integrity"] = {
        "algorithm": human.INTEGRITY_ALGORITHM,
        "sha256": human.strict.sha256_bytes(human.strict.canonical_json(root)),
    }
    return root


def _ready_input(
    stage: str,
    labels: dict[str, dict[int, str]],
) -> dict[str, Any]:
    cells = []
    for controller in human.CONTROLLERS:
        for row, codes in enumerate(human.CODE_ROWS):
            for column, code in enumerate(codes):
                cells.append(
                    {
                        "controller": controller,
                        "row": row,
                        "column": column,
                        "code": code,
                        "label_verbatim": labels[controller][code],
                        "confidence": "HIGH",
                        "stable": True,
                    }
                )
    return {
        "schema_version": 1,
        "kind": human.INPUT_KIND,
        "stage": stage,
        "observed_at": "2026-08-30T21:00:00+08:00",
        "operator": {
            "operator_id": "operator-1",
            "operator_verbatim": "raw labels recorded before prediction review",
        },
        "supervision": {
            "supervisor_id": "supervisor-1",
            "continuous_supervision": True,
            "action_complete_reviewed": True,
            "no_intervening_visible_refresh": True,
            "ambient_light_stable": True,
            "viewing_angle_stable": True,
            "display_stable_through_observation": True,
            "four_replicates_checked": True,
            "electrical_state_normal": True,
            "esp32_restart_observed": False,
            "j2_state_during_observation": "ON",
            "supervision_verbatim": "continuous supervised observation",
        },
        "controls_verbatim": "codes 2, 3, and 5 match across controllers",
        "artifacts": {
            field: {"observed": False, "operator_verbatim": "not observed"}
            for field in human.ARTIFACT_FIELDS
        },
        "cells": cells,
    }


def _compact_ready_input(
    stage: str,
    labels: dict[str, dict[int, str]],
) -> dict[str, Any]:
    value = _ready_input(stage, labels)
    value["kind"] = human.COMPACT_INPUT_KIND
    value.pop("cells")
    value["controllers"] = {
        controller: {
            "code_labels_verbatim": [labels[controller][code] for code in range(8)],
            "all_four_replicates_consistent": True,
            "four_replicates_consistent_by_code": None,
            "all_labels_stable": True,
            "stable_by_code": None,
        }
        for controller in human.CONTROLLERS
    }
    return value


def _seal_known_ca(tmp_path: Path) -> Path:
    input_path = tmp_path / "ca-input.json"
    output_path = tmp_path / "ca-observation.json"
    _write_json(input_path, human.known_ca_operator_input())
    report = human.seal_observation(
        stage=human.CA_STAGE,
        action_result_path=CA_ACTION,
        operator_input_path=input_path,
    )
    human.write_exclusive(output_path, human._serialize(report))  # noqa: SLF001
    return output_path


def _fake_ac_contract() -> dict[str, Any]:
    report = ac_pack.build_report()
    return {
        "stage": human.AC_STAGE,
        "pack": ac_pack,
        "report": report,
        "action": report["actions"][0],
        "config": ac_pack.CONFIG,
        "firmware_sha256": "b" * 64,
        "profile_map": {
            "global_header": "active",
            "CS1": "active",
            "CS2": "commented",
        },
    }


def _install_fake_ac(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    original = human._stage_contract  # noqa: SLF001
    contract = _fake_ac_contract()

    def staged(stage: str) -> dict[str, Any]:
        return contract if stage == human.AC_STAGE else original(stage)

    monkeypatch.setattr(human, "_stage_contract", staged)
    return contract


def _ac_action_result(contract: dict[str, Any]) -> dict[str, Any]:
    expected = contract["action"]
    action = human._expected_runtime_action(expected)  # noqa: SLF001
    action["prior_static_action_id"] = expected["prior_static_action_id"]
    config = contract["config"]
    terminal = {
        "terminal_state": "COMPLETE",
        "result": True,
        "valid": True,
        "campaign_id": config.campaign_id,
        "test_id": config.test_id,
        "contract_id": contract["report"]["contract_id"],
        "build_tag": config.build_tag,
        "action_id": expected["action_id"],
        "descriptor_id": expected["descriptor_id"],
        "ordinal": 1,
        "role": expected["role"],
        "round": expected["round"],
        "profile_id": expected["profile_id"],
        "global_header": expected["global_header"],
        "global_tuple_id": expected["global_tuple_id"],
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "driver": {
            "valid": True,
            "sequence_ok": True,
            "wait_timeout": False,
            "failure_stage": "none",
        },
    }
    return _integrity(
        {
            "schema_version": 1,
            "kind": f"mf1750-ec5-{config.route_slug}-result",
            "outcome": "complete_pass",
            "visible_refreshes": 1,
            "firmware_sha256": contract["firmware_sha256"],
            "no_autochain": True,
            "no_retry": True,
            "no_recovery": True,
            "action": action,
            "terminal_report": terminal,
        }
    )


def _seal_ac(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    labels: dict[str, dict[int, str]],
) -> Path:
    contract = _install_fake_ac(monkeypatch)
    action_path = tmp_path / "ac-action.json"
    input_path = tmp_path / "ac-input.json"
    output_path = tmp_path / "ac-observation.json"
    _write_json(action_path, _ac_action_result(contract))
    _write_json(input_path, _compact_ready_input(human.AC_STAGE, labels))
    report = human.seal_observation(
        stage=human.AC_STAGE,
        action_result_path=action_path,
        operator_input_path=input_path,
    )
    human.write_exclusive(output_path, human._serialize(report))  # noqa: SLF001
    assert report["compact_operator_input_preserved"]["kind"] == (
        human.COMPACT_INPUT_KIND
    )
    assert report["compact_input_expansion"]["expanded_cell_count"] == 64
    return output_path


def test_known_ca_fact_is_preserved_and_unknowns_fail_closed(tmp_path: Path) -> None:
    source = human.known_ca_operator_input()
    assert source["observed_at"] is None
    assert source["operator"]["operator_verbatim"].startswith("CS1=C=[橄榄")
    assert source["supervision"]["continuous_supervision"] is None
    assert all(item["observed"] is None for item in source["artifacts"].values())
    assert len(source["cells"]) == 64

    path = _seal_known_ca(tmp_path)
    root, _payload = human.validate_observation(path)
    derived = root["derived_observation"]
    assert derived["reported_ca_baseline_match"] is True
    assert derived["replicate_summary"]["eligible_group_count"] == 16
    assert derived["control_summary"]["all_controls_pass"] is True
    assert (
        derived["artifact_summary"]["edge_stripe_residual_and_instability_all_explicit"]
        is False
    )
    assert derived["comparison_ready"] is False


def test_final_ac_identity_is_exactly_frozen() -> None:
    contract = human._stage_contract(human.AC_STAGE)  # noqa: SLF001
    assert contract["report"]["contract_id"] == human.T3_EXACT_CONTRACT_ID
    assert contract["action"]["descriptor_id"] == human.T3_EXACT_DESCRIPTOR_ID
    assert contract["action"]["action_id"] == human.T3_EXACT_ACTION_ID
    assert contract["firmware_sha256"] == human.T3_EXACT_BIN_SHA256


@pytest.mark.parametrize("failure", ["missing", "duplicate", "wrong_code"])
def test_cell_coverage_and_fixed_code_fail_closed(
    tmp_path: Path,
    failure: str,
) -> None:
    source = human.known_ca_operator_input()
    if failure == "missing":
        source["cells"].pop()
    elif failure == "duplicate":
        source["cells"][-1] = deepcopy(source["cells"][0])
    else:
        source["cells"][0]["code"] = 7
    path = tmp_path / f"{failure}.json"
    _write_json(path, source)
    with pytest.raises(human.HumanObservationError):
        human.seal_observation(
            stage=human.CA_STAGE,
            action_result_path=CA_ACTION,
            operator_input_path=path,
        )


def test_compact_input_requires_expanded_form_for_any_mismatch() -> None:
    source = _compact_ready_input(human.CA_STAGE, human.CA_REPORTED_LABELS)
    source["controllers"]["CS1"]["all_four_replicates_consistent"] = False
    with pytest.raises(human.HumanObservationError, match="expanded 64-cell"):
        human._expand_compact_operator_input(  # noqa: SLF001
            source,
            expected_stage=human.CA_STAGE,
        )


def test_ca_action_lookalike_is_rejected_even_when_resealed(tmp_path: Path) -> None:
    action = json.loads(CA_ACTION.read_text(encoding="utf-8"))
    action["created_at"] = "2026-08-30T00:00:00+00:00"
    action = _integrity(action)
    action_path = tmp_path / "lookalike-action.json"
    input_path = tmp_path / "input.json"
    _write_json(action_path, action)
    _write_json(input_path, human.known_ca_operator_input())
    with pytest.raises(human.HumanObservationError, match="bytes|file SHA-256"):
        human.seal_observation(
            stage=human.CA_STAGE,
            action_result_path=action_path,
            operator_input_path=input_path,
        )


def test_o_excl_never_overwrites(tmp_path: Path) -> None:
    output = tmp_path / "sealed.json"
    human.write_exclusive(output, b"first")
    with pytest.raises(human.HumanObservationError, match="refusing to overwrite"):
        human.write_exclusive(output, b"second")
    assert output.read_bytes() == b"first"


def test_existing_w3_clean_white_authority_deep_validates() -> None:
    root, payload = human.validate_clean_white_observation(W3_AUTHORITY)
    assert len(payload) == 4072
    assert root["raw_operator_report"]["operator_verbatim"] == "白屏，干净"
    assert root["action_result_binding"]["action_id"].startswith("b37e6e")
    relay = root["final_relay_off_receipt_binding"]
    assert relay["commanded_state"] == "OFF"
    assert relay["electrical_state_proven"] is False
    assert (
        root["authority"]["final_relay_off_is_command_query_not_load_voltage_proof"]
        is True
    )


def test_white_fact_requires_exact_words_and_exact_receipt(tmp_path: Path) -> None:
    source = json.loads(W3_INPUT.read_text(encoding="utf-8"))
    source["operator_verbatim"] = "looks white"
    input_path = tmp_path / "wrong-input.json"
    _write_json(input_path, source)
    with pytest.raises(human.HumanObservationError, match="verbatim differs"):
        human.seal_clean_white_observation(
            action_result_path=W3_ACTION,
            relay_off_receipt_path=W3_RELAY_OFF,
            operator_input_path=input_path,
        )

    receipt = json.loads(W3_RELAY_OFF.read_text(encoding="utf-8"))
    receipt["switched_at"] = "2026-08-30T20:44:00+08:00"
    unsigned = {key: value for key, value in receipt.items() if key != "integrity"}
    receipt["integrity"]["canonical_sha256"] = human.strict.sha256_bytes(
        human.strict.canonical_json(unsigned)
    )
    receipt_path = tmp_path / "lookalike-receipt.json"
    _write_json(receipt_path, receipt)
    with pytest.raises(human.HumanObservationError, match="bytes|file SHA-256"):
        human.seal_clean_white_observation(
            action_result_path=W3_ACTION,
            relay_off_receipt_path=receipt_path,
            operator_input_path=W3_INPUT,
        )


def test_profile_following_human_screen_survives_historical_ca_unknowns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ca_path = _seal_known_ca(tmp_path)
    labels = {
        "CS1": deepcopy(human.CA_REPORTED_LABELS["CS2"]),
        "CS2": deepcopy(human.CA_REPORTED_LABELS["CS1"]),
    }
    ac_path = _seal_ac(tmp_path, monkeypatch, labels)
    report = human.compare_observations(ca_path, ac_path)
    assert report["summary"]["classification"] == (
        "HUMAN_SCREEN_PROFILE_FOLLOWING_STRONG"
    )
    assert report["summary"]["formal_classification"] == "FORMAL_NOT_EVALUATED"
    assert report["summary"]["both_observations_comparison_ready"] is False
    assert report["summary"]["human_screening_inputs_ready"] is True
    assert report["evidence_boundaries"]["physical_colour_calibrated"] is False
    output = tmp_path / "comparison.json"
    human.write_exclusive(output, human._serialize(report))  # noqa: SLF001
    validated, _payload = human.validate_comparison(output)
    assert validated == report


def test_physical_side_following_human_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ca_path = _seal_known_ca(tmp_path)
    labels = deepcopy(human.CA_REPORTED_LABELS)
    ac_path = _seal_ac(tmp_path, monkeypatch, labels)
    report = human.compare_observations(ca_path, ac_path)
    assert report["summary"]["classification"] == (
        "HUMAN_SCREEN_PHYSICAL_SIDE_FOLLOWING_STRONG"
    )


def test_ac_control_mismatch_closes_human_screen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ca_path = _seal_known_ca(tmp_path)
    labels = {
        "CS1": deepcopy(human.CA_REPORTED_LABELS["CS2"]),
        "CS2": deepcopy(human.CA_REPORTED_LABELS["CS1"]),
    }
    labels["CS2"][2] = "unexpected-control"
    ac_path = _seal_ac(tmp_path, monkeypatch, labels)
    report = human.compare_observations(ca_path, ac_path)
    assert report["summary"]["classification"] == (
        "HUMAN_SCREEN_INCONCLUSIVE_INPUT_OR_CONTROL_GATE"
    )
    assert report["summary"]["controls_pass"] is False


def test_sealed_observation_tamper_is_rejected(tmp_path: Path) -> None:
    path = _seal_known_ca(tmp_path)
    root = json.loads(path.read_text(encoding="utf-8"))
    root["raw_observation"]["operator"]["operator_verbatim"] = "tampered"
    _write_json(path, root)
    with pytest.raises(human.HumanObservationError, match="integrity SHA differs"):
        human.validate_observation(path)


def test_cli_surface_and_blind_card() -> None:
    parsed = human.parse_args(
        [
            "seal-clean-white",
            "--action-result",
            "action.json",
            "--relay-off-receipt",
            "off.json",
            "--input",
            "input.json",
            "--output",
            "authority.json",
        ]
    )
    assert parsed.command == "seal-clean-white"
    card = (
        REPO_ROOT
        / "docs"
        / "MF1750-RAW-P16-PROFILE-FOLLOWING-HUMAN-OBSERVATION-CARD.md"
    ).read_text(encoding="utf-8")
    assert "先封存、后揭盲" in card
    assert "0 1 2 3 4 5 6 7" in card
    assert "6 7 0 1 2 3 4 5" in card
    for leaked_label in ("橄榄", "浅黄", "深粉", "深蓝"):
        assert leaked_label not in card
