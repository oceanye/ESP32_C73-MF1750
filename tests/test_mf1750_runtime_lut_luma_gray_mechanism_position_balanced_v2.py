from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_observation as observation,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_pack as pack,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_white_successor_v1_once as white_once,
)
from tools import (
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v2_white_successor_v1_pack as white_pack,
)


def test_position_balanced_layout_and_effective_g3_g4_profile() -> None:
    report = pack.build_report()
    assert len(report["contract"]["recipes"]) == 16
    assert all(pack.CS1_RECIPE_AT_CELL.count(recipe) == 4 for recipe in range(16))
    assert pack.CS2_RECIPE_AT_CELL == tuple(reversed(pack.CS1_RECIPE_AT_CELL))
    g3, g4 = report["actions"][2:]
    assert g3["frame"] == g4["frame"]
    assert g3["cs1_dtm"] == g4["cs1_dtm"]
    assert g3["cs2_dtm"] == g4["cs2_dtm"]
    assert g3["effective_driver_profile"] == g4["effective_driver_profile"]
    assert g3["effective_driver_profile"]["id"] == (
        "LEGACY_ACTIVE_HEADER__CS1_ACTIVE535__CS2_COMMENTED535"
    )
    assert g3["action_id"] != g4["action_id"]


def test_w11_branch_is_alternative_not_sequential() -> None:
    contract = pack.build_report()["contract"]
    assert contract["w11_successor_branch_mode"] == "ALTERNATIVE_NOT_SEQUENTIAL"
    assert contract["alternative_branch_campaign_id"] == "EC5_STABLE_CODE0_LUMA_LATIN_V3"
    assert contract["old_w11_anchor_invalid_after_either_branch_mutates"] is True
    assert contract["cross_branch_after_containment_requires_fresh_bound_white_anchor"] is True


def test_compiled_sources_and_reproducible_artifacts_are_sealed() -> None:
    validation = pack.dry_validate(verify_artifacts=True)
    assert validation["result"] == "PASS"
    assert validation["compiled_identity_binary"]["counts"] == {"bin": 1, "elf": 1}
    white = white_pack.dry_validate(verify_artifacts=True)
    assert white["result"] == "PASS"
    assert white["compiled_identity_binary"]["counts"] == {"bin": 1, "elf": 1}
    for path, size, digest in (
        (pack.artifact_paths()[0], pack.ARTIFACTS["bin_bytes"], pack.ARTIFACTS["bin_sha256"]),
        (pack.artifact_paths()[1], pack.ARTIFACTS["elf_bytes"], pack.ARTIFACTS["elf_sha256"]),
        (white_pack.FIRMWARE_BIN, white_pack.FIRMWARE_BIN_BYTES, white_pack.FIRMWARE_BIN_SHA256),
        (white_pack.FIRMWARE_ELF, white_pack.FIRMWARE_ELF_BYTES, white_pack.FIRMWARE_ELF_SHA256),
    ):
        payload = path.read_bytes()
        assert len(payload) == size
        assert hashlib.sha256(payload).hexdigest() == digest


def _deep_source(ordinal: int) -> dict[str, object]:
    item = pack.build_report()["actions"][ordinal - 1]
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.build_report()["contract_id"],
        "ordinal": ordinal,
        "descriptor_id": item["descriptor_id"],
        "action_id": item["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "visible_refreshes": 1,
        "source_success_claimed": True,
        "canonical_integrity_sha256": "1" * 64,
        "boot_nonce": "0123456789abcdef",
        "claim_file_sha256": "2" * 64,
    }


def test_white_source_gate_accepts_only_fixed_g3_or_confirmed_g4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    g3 = tmp_path / "g3.json"
    g4 = tmp_path / "g4.json"
    g3.write_bytes(b"g3")
    paths = {3: g3.resolve(), 4: g4.resolve()}
    monkeypatch.setattr(white_once, "_source_terminal_paths", lambda: paths)
    monkeypatch.setattr(white_once, "_repo_relative", lambda path: Path(path).name)
    monkeypatch.setattr(
        white_once.source_once,
        "validate_terminal_evidence",
        lambda path: _deep_source(3 if Path(path).resolve() == g3.resolve() else 4),
    )
    assert white_once._validate_source_terminal_evidence(g3)["ordinal"] == 3
    g4.write_bytes(b"g4")
    with pytest.raises(white_once.WhiteSuccessorV1Error, match="stale G3"):
        white_once._validate_source_terminal_evidence(g3)
    with pytest.raises(white_once.WhiteSuccessorV1Error, match="explicit"):
        white_once._validate_source_terminal_evidence(g4)
    assert white_once._validate_source_terminal_evidence(
        g4, confirm_optional_g4_source=True
    )["ordinal"] == 4


def test_white_run_requires_gnd_before_any_request() -> None:
    calls = 0

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    with pytest.raises(white_once.WhiteSuccessorV1Error, match="GND"):
        white_once.run_once(
            "http://192.168.1.7",
            source_terminal_evidence=Path("unused"),
            confirm_j2_on=True,
            confirm_gnd_normal=False,
            requester=requester,
        )
    assert calls == 0


def test_white_run_requires_fixed_same_boot_diagnostic_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def requester(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError((args, kwargs))

    monkeypatch.setattr(white_once, "_verify_artifacts", lambda: None)
    monkeypatch.setattr(
        white_once,
        "_validate_source_terminal_evidence",
        lambda *args, **kwargs: _deep_source(3),
    )
    monkeypatch.setattr(
        white_once,
        "_validate_source_gate_receipt",
        lambda source: {"verified": True, "source_terminal_gate": source},
    )
    monkeypatch.setattr(white_once.host, "DIAGNOSTIC_OUTPUT", tmp_path / "missing.json")
    with pytest.raises(white_once.WhiteSuccessorV1Error, match="missing"):
        white_once.run_once(
            "http://192.168.1.7",
            source_terminal_evidence=Path("unused"),
            confirm_j2_on=True,
            confirm_gnd_normal=True,
            requester=requester,
        )
    assert calls == 0


def test_same_boot_requester_rejects_changed_boot() -> None:
    guarded = white_once._same_boot_requester(
        lambda *args, **kwargs: (200, {"boot_nonce": "ffffffffffffffff"}),
        "0123456789abcdef",
    )
    with pytest.raises(white_once.WhiteSuccessorV1Error, match="boot nonce"):
        guarded("http://192.168.1.7", "/status", method="GET", headers=None, timeout=1)


def test_roi_manifest_has_four_samples_per_recipe_per_controller() -> None:
    manifest = observation.roi_manifest()
    assert manifest["sample_count"] == 128
    for controller in ("CS1", "CS2"):
        for recipe in range(16):
            assert sum(
                item["controller"] == controller and item["recipe"] == recipe
                for item in manifest["samples"]
            ) == 4
    assert manifest["controller_policy"] == "CS1_AND_CS2_EVALUATED_SEPARATELY"


def _observed_envelope(ordinal: int) -> dict[str, object]:
    measurements = []
    for item in observation.roi_manifest()["samples"]:
        recipe = item["recipe"]
        measurements.append(
            {
                **deepcopy(item),
                "lab": [20.0 + float(recipe % 8), 2.0, 1.0],
                "bottom_edge_clean": True,
                "horizontal_stripe_absent": True,
                "vertical_stripe_absent": True,
                "roi_visible": True,
                "operator_note": None,
            }
        )
    return {
        "schema_version": 1,
        "kind": observation.KIND,
        "state": "OBSERVED",
        "action_evidence": {"ordinal": ordinal},
        "measurements": measurements,
        "qualified_colour_count": 0,
    }


def test_observation_evaluator_is_candidate_only_and_checks_g3_g4_repeat(
    tmp_path: Path,
) -> None:
    g3 = tmp_path / "g3-observation.json"
    g4 = tmp_path / "g4-observation.json"
    result_path = tmp_path / "evaluation.json"
    observation._write_new(g3, _observed_envelope(3))
    observation._write_new(g4, _observed_envelope(4))
    result = observation.evaluate(g3, result_path, repeat_input=g4)
    assert result["state"] == "CANDIDATE_MECHANISM_PASS_REQUIRES_HUMAN_REVIEW"
    assert result["g3_g4_repeat_gate"]["passed"] is True
    assert result["qualified_colour_count"] == 0
    assert result["qualified_gray_levels"] == 0
    assert result["qualified_brightness_levels"] == 0
