from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

import pytest

from tools import mf1750_ec5_h3_c_first_stage_b_phase_b_offline_gate as gate_mod
from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as physical


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE_A_ROOT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C_FIRST_LIVE_20260816_V10_PHASE_A_V2"
)
PHASE_A_ENVELOPE = PHASE_A_ROOT / "phase-a-live-execution-envelope.json"
PHASE_A_RECEIPT = PHASE_A_ROOT / "phase-a-live-terminal-receipt.json"
FACADE_BLUEPRINT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_H3_C_FIRST_STAGE_B_FACADE_BLUEPRINT_20260815_V2"
    / "WF20_25-blueprint.json"
)
PLANNED_PHASE_B_TERMINAL = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C_FIRST_LIVE_20260814_V10_RECOVERY_V1"
    / "c-j2-off-diagnostic.json"
)
V10_RELEASE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10"
    / "WF20_25-release.json"
)


@pytest.fixture(scope="module")
def gate_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], Path]:
    root = tmp_path_factory.mktemp("phase-b-offline-gate")
    gate = gate_mod.materialize_phase_b_offline_gate(
        phase_a_live_envelope_file=PHASE_A_ENVELOPE,
        phase_a_terminal_receipt_file=PHASE_A_RECEIPT,
        facade_blueprint_file=FACADE_BLUEPRINT,
        gate_blueprint_file=root / "phase-b-offline-gate.json",
        planned_phase_b_registry_file=(
            root / "planned-live" / "phase-b-live-attempt-registry.json"
        ),
        planned_phase_b_terminal_receipt_file=PLANNED_PHASE_B_TERMINAL,
    )
    return gate, root


@pytest.fixture(scope="module")
def validated_gate_bundle(
    gate_bundle: tuple[dict[str, Any], Path],
) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    gate, root = gate_bundle
    summary = gate_mod.validate_phase_b_offline_gate(gate)
    return gate, root, summary


class ValidPhaseBPayloads:
    def __init__(self) -> None:
        self.context = physical.load_release(V10_RELEASE)
        self.ordinal = 1
        self.boot_nonce = "0123456789abcdef"

    def manifest(self) -> dict[str, Any]:
        return facade._expected_manifest_surface(  # noqa: SLF001
            self.context, self.ordinal
        )

    def status(self) -> dict[str, Any]:
        return facade._expected_status_surface(  # noqa: SLF001
            self.context,
            boot_nonce=self.boot_nonce,
            busy=1,
            ordinal=self.ordinal,
        )

    def report(self) -> dict[str, Any]:
        return facade._expected_report_surface(  # noqa: SLF001
            self.context, self.ordinal
        )

    @staticmethod
    def raw(value: Mapping[str, Any]) -> bytes:
        return contract.canonical_json_bytes(value)

    def script(
        self, gate: Mapping[str, Any]
    ) -> list[tuple[str, gate_mod.ScriptedPhaseBFakeResponse]]:
        bodies = (self.manifest(), self.status(), self.report())
        return [
            (
                str(request["absolute_url"]),
                gate_mod.ScriptedPhaseBFakeResponse(200, self.raw(body)),
            )
            for request, body in zip(
                gate["phase_b_state_machine"]["ordered_requests"],
                bodies,
                strict=True,
            )
        ]


def test_gate_binds_exact_committed_phase_a_and_replays_raw_version(
    gate_bundle: tuple[dict[str, Any], Path],
) -> None:
    gate, root = gate_bundle
    predecessor = gate["phase_a_predecessor"]
    replay = gate["phase_a_version_raw_replay"]
    machine = gate["phase_b_state_machine"]
    planned = gate["planned_production_artifacts"]

    assert gate["schema_version"] == 1
    assert gate["kind"] == gate_mod.KIND
    assert gate["classification"] == gate_mod.CLASSIFICATION
    assert predecessor["live_envelope"]["sha256"] == (
        "4863bca303fe6692812e5ec065c0912c831504b2d423e2b643dd12aef06178c8"
    )
    assert predecessor["offline_authority"]["sha256"] == (
        "cadf1e925f33c718040bb4983ff2efa8e7a97371214e3c3d88720e7385da1cc4"
    )
    assert predecessor["immutable_registry"]["sha256"] == (
        "bc81e5772366b3f60a670336be8103ca32a37645c178f0889ebe72ce5f50c56d"
    )
    assert predecessor["committed_terminal_receipt"]["sha256"] == (
        "cb7c65c4f55069215cd638fac4b401421dd530cdabf263408fd5cc7d5fc57a94"
    )
    assert (
        predecessor["committed_terminal_receipt"]["terminal_outcome_committed"] is True
    )
    assert predecessor["phase_a_authorization_is_consumed_and_not_reusable"] is True
    assert predecessor["phase_b_generated_or_executed_by_predecessor"] is False

    assert replay["response_entity_body_bytes"] == 2448
    assert replay["response_entity_body_sha256"] == (
        "f83519943cafabc2035ff5d4d33b4c918925a2652d4116b133d52be7c3795870"
    )
    assert replay["strict_parsed_canonical_sha256"] == (
        "33ea4e0033485a05032993b278d4b0db9701cf378314ea8f0334654ea5b17e80"
    )
    assert replay["raw_body_replayed_through_exact_v10_decoder_now"] is True
    assert replay["responder_or_device_identity_proven"] is False

    assert machine["version_repeated"] is False
    assert [item["name"] for item in machine["ordered_requests"]] == [
        "manifest",
        "status",
        "report",
    ]
    assert [
        item["full_diagnostic_ordinal"] for item in machine["ordered_requests"]
    ] == [
        2,
        3,
        4,
    ]
    assert machine["maximum_get_count"] == 3
    assert machine["maximum_post_count"] == 0
    assert machine["request_body_count"] == 0
    assert machine["claim_count"] == 0
    assert machine["client_mutation_requests"] == 0
    assert machine["client_visible_refresh_requests"] == 0
    assert machine["retry"] is False
    assert machine["fallback"] is False
    assert machine["automatic_recovery"] is False
    assert machine["automatic_chaining"] is False
    assert all(
        item["request_wire_sha256"]
        == contract.sha256(item["request_wire_ascii"].encode("ascii"))
        for item in machine["ordered_requests"]
    )

    assert planned["phase_b_live_authority"]["present"] is False
    assert planned["fresh_onsite_gate_after_phase_a"]["present"] is False
    assert planned["separate_phase_b_user_authorization"]["present"] is False
    assert planned["phase_b_attempt_registry"]["present"] is False
    assert planned["phase_b_terminal_receipt"]["present"] is False
    assert not Path(planned["phase_b_attempt_registry"]["path"]).exists()
    assert not Path(planned["phase_b_terminal_receipt"]["path"]).exists()
    assert list(root.rglob("*")) == []


def test_gate_deep_rebuild_is_valid_but_not_executable(
    validated_gate_bundle: tuple[dict[str, Any], Path, dict[str, Any]],
) -> None:
    gate, _, summary = validated_gate_bundle

    assert summary == {
        "valid": True,
        "offline_gate_id": gate["offline_gate_id"],
        "canonical_sha256": gate["integrity"]["canonical_sha256"],
        "classification": gate_mod.CLASSIFICATION,
        "phase_a_predecessor_committed_success": True,
        "phase_a_raw_version_replayed": True,
        "phase_b_endpoints": ["manifest", "status", "report"],
        "phase_b_repeats_version": False,
        "maximum_get_count": 3,
        "maximum_post_body_claim_mutation_visible_refresh_count": 0,
        "production_authority_or_authorization_generated": False,
        "planned_registry_or_receipt_created": False,
        "execution_ready": False,
        "live_authorized": False,
        "device_io_performed": False,
        "unsatisfied_live_gates": gate["unsatisfied_live_gates"],
    }
    boundary = gate["response_validation_contract"]
    assert boundary["success_is_device_identity_proof"] is False
    assert boundary["success_is_trusted_ip_proof"] is False
    assert boundary["success_is_fresh_boot_or_active_slot_proof"] is False
    assert boundary["success_directly_authorizes_visible_action"] is False


def test_resealed_scope_tamper_fails_deterministic_reconstruction(
    validated_gate_bundle: tuple[dict[str, Any], Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate, _, _ = validated_gate_bundle
    tampered = deepcopy(gate)
    tampered["phase_b_state_machine"]["maximum_get_count"] = 4
    tampered = gate_mod._seal(  # noqa: SLF001
        {key: value for key, value in tampered.items() if key != "integrity"}
    )

    rebuilt = gate_mod.materialize_phase_b_offline_gate(
        phase_a_live_envelope_file=PHASE_A_ENVELOPE,
        phase_a_terminal_receipt_file=PHASE_A_RECEIPT,
        facade_blueprint_file=FACADE_BLUEPRINT,
        gate_blueprint_file=Path(gate["gate_blueprint_file"]),
        planned_phase_b_registry_file=Path(
            gate["planned_production_artifacts"]["phase_b_attempt_registry"]["path"]
        ),
        planned_phase_b_terminal_receipt_file=PLANNED_PHASE_B_TERMINAL,
    )
    monkeypatch.setattr(
        gate_mod,
        "materialize_phase_b_offline_gate",
        lambda **_: rebuilt,
    )
    with pytest.raises(gate_mod.PhaseBOfflineGateError, match="reconstruction"):
        gate_mod.validate_phase_b_offline_gate(tampered)


def test_scripted_fake_success_is_three_gets_after_predecessor_replay(
    validated_gate_bundle: tuple[dict[str, Any], Path, dict[str, Any]],
) -> None:
    gate, root, _ = validated_gate_bundle
    payloads = ValidPhaseBPayloads()
    requester = gate_mod.ScriptedPhaseBFakeRequester(payloads.script(gate))
    output = root / "success.phase-b-fake-only.json"

    result = gate_mod.run_phase_b_scripted_fake_only(
        gate,
        requester=requester,
        fake_output=output,
    )

    assert result["state"] == "COMPLETE_PHASE_B_FAKE_ONLY_VALIDATION"
    assert result["classification"] == gate_mod.FAKE_RESULT_CLASSIFICATION
    assert result["phase_a_version_raw_replay_performed_before_fake_requests"] is True
    assert result["phase_a_version_was_not_requested_again"] is True
    assert result["requests_attempted"] == 3
    assert result["validated_response_names"] == ["manifest", "status", "report"]
    assert result["status_boot_nonce"] == payloads.boot_nonce
    assert result["success_classification"] == gate_mod.SUCCESS_CLASSIFICATION
    assert result["success_is_responder_or_device_identity_proof"] is False
    assert result["success_is_trusted_ip_proof"] is False
    assert result["success_is_fresh_boot_or_active_slot_proof"] is False
    assert result["success_authorizes_visible_action"] is False
    assert result["get_requests_simulated"] == 3
    assert result["post_requests"] == 0
    assert result["request_bodies"] == 0
    assert result["claims"] == 0
    assert result["client_mutation_requests"] == 0
    assert result["client_visible_refresh_requests"] == 0
    assert result["network_requests"] == 0
    assert result["device_io_performed"] is False
    assert result["production_authority_or_authorization_generated"] is False
    assert result["planned_production_paths_touched"] is False
    assert output.read_bytes() == contract.canonical_json_bytes(result) + b"\n"
    planned = gate["planned_production_artifacts"]
    assert not Path(planned["phase_b_attempt_registry"]["path"]).exists()
    assert not Path(planned["phase_b_terminal_receipt"]["path"]).exists()


@pytest.mark.parametrize(
    ("failed_index", "expected_validated"),
    (
        (0, []),
        (1, ["manifest"]),
        (2, ["manifest", "status"]),
    ),
)
def test_scripted_fake_decode_failure_stops_before_next_endpoint(
    validated_gate_bundle: tuple[dict[str, Any], Path, dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    failed_index: int,
    expected_validated: list[str],
) -> None:
    gate, root, summary = validated_gate_bundle
    monkeypatch.setattr(
        gate_mod,
        "validate_phase_b_offline_gate",
        lambda *_args, **_kwargs: summary,
    )
    payloads = ValidPhaseBPayloads()
    script = payloads.script(gate)
    script[failed_index] = (
        script[failed_index][0],
        gate_mod.ScriptedPhaseBFakeResponse(200, b'{"duplicate":1,"duplicate":2}'),
    )
    requester = gate_mod.ScriptedPhaseBFakeRequester(script)
    output = root / f"failed-{failed_index}.phase-b-fake-only.json"

    result = gate_mod.run_phase_b_scripted_fake_only(
        gate,
        requester=requester,
        fake_output=output,
    )

    assert result["state"] == "TERMINAL_PHASE_B_FAKE_ONLY_FAILURE"
    assert result["outcome"] == "TERMINAL_FAKE_ONLY_FAILURE_NO_RETRY"
    assert result["requests_attempted"] == failed_index + 1
    assert result["validated_response_names"] == expected_validated
    assert len(result["validation_acknowledgements"]) == failed_index
    assert result["endpoint_outcomes"][-1]["validation_outcome"] == ("FAILED_TERMINAL")
    assert result["retry_allowed"] is False
    assert result["network_requests"] == 0
    assert result["success_authorizes_visible_action"] is False

    unused = gate_mod.ScriptedPhaseBFakeRequester(payloads.script(gate))
    with pytest.raises(gate_mod.PhaseBOfflineGateError, match="no retry"):
        gate_mod.run_phase_b_scripted_fake_only(
            gate,
            requester=unused,
            fake_output=output,
        )
    assert unused.calls == []


def test_fake_rejects_arbitrary_requester_before_output(
    gate_bundle: tuple[dict[str, Any], Path],
) -> None:
    gate, root = gate_bundle

    class ArbitraryRequester:
        pass

    output = root / "arbitrary.phase-b-fake-only.json"
    with pytest.raises(gate_mod.PhaseBOfflineGateError, match="exact"):
        gate_mod.run_phase_b_scripted_fake_only(  # type: ignore[arg-type]
            gate,
            requester=ArbitraryRequester(),
            fake_output=output,
        )
    assert not output.exists()


def test_source_and_cli_have_no_live_execution_surface() -> None:
    source = Path(gate_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        str(node.module).split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert imported_roots.isdisjoint(
        {"urllib", "requests", "httpx", "socket", "serial", "subprocess"}
    )
    assert "AUTHORIZE_" not in source
    assert "execute_phase_a_live_once" not in source
    assert ".connect(" not in source
    assert ".send" not in source
    assert not hasattr(gate_mod, "phase_a_live")
    assert not hasattr(gate_mod, "execute_phase_a_live_once")

    parser = gate_mod._parser()  # noqa: SLF001
    subparsers = [
        action
        for action in parser._actions  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
    ]
    assert len(subparsers) == 1
    assert set(subparsers[0].choices) == {"build", "validate"}
