from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from tools import (
    mf1750_raw_p16_crossover_t4_v3_terminal_salvage_once as salvage,
)
from tools import (
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v3_once as once,
)
from tools import (
    mf1750_raw_p16_crossover_w7_t4_active_header_ca_r20_swap_confirmation_successor_v3_white_v1_once as w7,
)
from tools import mf1750_raw_p16_crossover_t4_matched_swap_human_observation as human


def test_local_authorities_bind_exact_consumed_action_and_same_boot() -> None:
    host = once.configure()
    context = salvage._validate_source_and_claim(host)  # noqa: SLF001

    assert context["boot_nonce"] == "63f251f6a2ed5fc1"
    assert (
        context["action"]["action_id"]
        == "90d769f4e139829bd5aed23ae03aa831be8b4b67159a3463f8747dbeb2c2baee"
    )
    assert context["source_binding"] == {
        "path": str(salvage.SOURCE_FAILURE),
        "bytes": 43486,
        "file_sha256": (
            "3efd366a3da763ce2dfaa144f9a15debea0c31826025808772982d668932d4dc"
        ),
        "canonical_integrity_sha256": (
            "7d418afd3651a22f3f19b3471fe973c08d0b8a21bd399a6a18fb8a49b7ffc99e"
        ),
        "outcome": "terminal_report_read_error",
    }
    assert context["claim_binding"]["file_sha256"] == (
        "e6fa56a132e65733e2987b3bac9e98bead4ee2098954d11e95c6d7201676499e"
    )


def test_raw_four_get_is_immutable_and_reconciled_fault_is_strict() -> None:
    raw_payload = salvage.SALVAGE_OUTPUT.read_bytes()
    raw = json.loads(raw_payload)
    reconciled, payload = salvage.validate_fault_reconciliation()

    assert hashlib.sha256(raw_payload).hexdigest() == (
        "48a809eaad5e0660a4a1474b051d9ed7d732f390b429a41f23c6299ea4d788a4"
    )
    assert raw["network"] == {"get": 4, "post": 0}
    assert [(item["method"], item["endpoint"]) for item in raw["transcript"]] == [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
    ]
    assert reconciled["outcome"] == "fault_salvaged_read_only"
    assert reconciled["network"] == {"get": 0, "post": 0}
    assert reconciled["reconciled_historical_network"] == {"get": 4, "post": 0}
    assert reconciled["terminal_state"] == "FAULT"
    assert reconciled["driver_call_count_for_action"] == 1
    assert reconciled["terminal_report"]["driver"]["timeout_stage"] == "DRF"
    assert reconciled["terminal_report"]["driver"]["drf_ms"] == 60001
    assert reconciled["partial_visible_panel_mutation_possible"] is True
    assert reconciled["panel_state_qualified"] is False
    assert reconciled["matched_swap_complete"] is False
    assert reconciled["human_profile_following_decision_allowed"] is False
    assert len(payload) == 54647
    assert hashlib.sha256(payload).hexdigest() == (
        "d1c5b1dbdc67712703dd64bbdff7ebc9c9d862789f6db398714c4b0d7cc28e5c"
    )


def test_live_entry_has_four_get_calls_and_no_mutating_request() -> None:
    source = inspect.getsource(salvage.salvage_terminal_once)

    assert source.count("host.base.runner._request(") == 4
    assert '"version"' in source
    assert '"manifest"' in source
    assert '"status"' in source
    assert '"report"' in source
    assert "method=\"POST\"" not in source
    assert ".run_once(" not in source
    assert "relay_exact_bound_switch" not in source
    assert "relay_rebind" not in source
    assert "serial.Serial" not in source
    assert "subprocess" not in source


def test_complete_only_w7_and_human_paths_reject_fault_authorities() -> None:
    with pytest.raises(w7.W7RunnerError, match="fixed T4 V3 action output"):
        w7._validate_source_complete_evidence(  # noqa: SLF001
            salvage.RECONCILED_OUTPUT
        )
    with pytest.raises(
        human.T4MatchedSwapHumanObservationError,
        match="action-result envelope differs|terminal",
    ):
        human._validate_t4_action_result(salvage.RECONCILED_OUTPUT)  # noqa: SLF001


def test_fixed_outputs_are_distinct_and_original_failure_is_unchanged() -> None:
    assert salvage.SOURCE_FAILURE != salvage.SALVAGE_OUTPUT
    assert salvage.SALVAGE_OUTPUT != salvage.RECONCILED_OUTPUT
    assert salvage.SOURCE_FAILURE != salvage.RECONCILED_OUTPUT
    assert Path(salvage.SOURCE_FAILURE).name == "action-01-position-balanced-atlas.json"
    assert Path(salvage.SALVAGE_OUTPUT).name == (
        "action-01-terminal-read-only-salvage.json"
    )
    assert Path(salvage.RECONCILED_OUTPUT).name == (
        "action-01-terminal-read-only-salvage-reconciled.json"
    )


def test_existing_o_excl_salvage_blocks_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(salvage.once, "configure", lambda: object())
    monkeypatch.setattr(
        salvage,
        "_validate_source_and_claim",
        lambda _host: {"locally_validated": True},
    )

    def requester(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("requester must not be reached")

    with pytest.raises(
        salvage.T4V3TerminalSalvageError,
        match="already exists; no retry",
    ):
        salvage.salvage_terminal_once(
            "http://192.0.2.1",
            confirm_j2_off=True,
            requester=requester,
        )
    assert calls == []
