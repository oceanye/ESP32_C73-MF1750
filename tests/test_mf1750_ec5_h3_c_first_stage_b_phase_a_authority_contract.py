from __future__ import annotations

import argparse
import ast
import base64
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import socket
from typing import Any

import pytest

from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_authority_contract as phase_a
from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract


REPO_ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_H3_C_FIRST_STAGE_B_FACADE_BLUEPRINT_20260815_V2"
    / "WF20_25-blueprint.json"
)
STAGE_A_RECEIPT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C_FIRST_LIVE_20260815_V10_RECOVERY_V1"
    / "stage-a-partial-boot-control-receipt.json"
)


def valid_kwargs(root: Path) -> dict[str, Any]:
    return {
        "blueprint_file": BLUEPRINT,
        "stage_a_receipt_file": STAGE_A_RECEIPT,
        "authority_file": root / "phase-a-authority.json",
        "attempt_registry_file": root / "phase-a-attempt-registry.json",
        "terminal_receipt_file": root / "phase-a-terminal-receipt.json",
        "observed_at": "2026-08-15T22:00:00+08:00",
        "prepared_at": "2026-08-15T22:01:00+08:00",
        "current_reading_a": "0.000",
        "locator_selection_phrase": phase_a.LOCATOR_SELECTION_PHRASE,
        "j2_off": True,
        "screen_clean_white": True,
        "esp32_usb_connected": True,
        "supply_3v3_cv_normal": True,
        "temperature_exact_25c": True,
        "current_limit_exact_1a": True,
        "current_and_temperature_monitors_ready": True,
        "physical_cutoff_ready": True,
        "no_reset_since_stage_a": True,
        "no_flash_since_stage_a": True,
        "no_refresh_since_stage_a": True,
        "no_rewire_since_stage_a": True,
    }


def fake_kwargs(root: Path) -> dict[str, Any]:
    kwargs = valid_kwargs(root)
    kwargs["attempt_registry_file"] = root / "phase-a-registry.fake-only.json"
    kwargs["terminal_receipt_file"] = root / "phase-a-receipt.fake-only.json"
    return kwargs


def write_fake_authority(root: Path) -> tuple[dict[str, Any], str]:
    authority = phase_a.materialize_phase_a_authority(**fake_kwargs(root))
    authority_file = Path(authority["authority_file"])
    authority_file.parent.mkdir(parents=True, exist_ok=True)
    authority_payload = contract.canonical_json_bytes(authority) + b"\n"
    authority_file.write_bytes(authority_payload)
    token = phase_a._authorization_phrase(  # noqa: SLF001
        authority,
        authority_file_sha256=contract.sha256(authority_payload),
    )
    return authority, token


@lru_cache(maxsize=1)
def valid_v10_context() -> Any:
    blueprint = facade.load_blueprint(BLUEPRINT)
    return facade._load_frozen_v10_release(  # noqa: SLF001
        Path(str(blueprint["frozen_v10_validator_binding"]["release_file"]))
    )


@lru_cache(maxsize=1)
def valid_version_raw() -> bytes:
    return contract.canonical_json_bytes(
        facade.expected_v10_response_fixture("version", valid_v10_context())
    )


def fake_response(
    body: bytes, *, status: int = 200, extra_headers: tuple[tuple[str, str], ...] = ()
) -> phase_a.ScriptedPhaseAFakeResponse:
    return phase_a.ScriptedPhaseAFakeResponse(
        status=status,
        headers=(
            ("Content-Type", "application/json"),
            ("Content-Length", str(len(body))),
            *extra_headers,
        ),
        entity_body=body,
    )


@pytest.fixture(scope="module")
def authority_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, Any], Path]:
    root = tmp_path_factory.mktemp("phase-a-authority")
    return phase_a.materialize_phase_a_authority(**valid_kwargs(root)), root


def test_phase_a_is_non_authorizing_one_version_only_and_keeps_stage_a_partial(
    authority_bundle: tuple[dict[str, Any], Path],
) -> None:
    authority, _ = authority_bundle
    scope = authority["authority_scope"]
    partial = authority["partial_stage_a_receipt_binding"]
    challenge = authority["authorization_challenge"]

    assert authority["schema_version"] == 1
    assert authority["kind"] == phase_a.KIND
    assert authority["classification"] == phase_a.CLASSIFICATION
    assert scope["stage_a_remains_incomplete"] is True
    assert scope["partial_stage_a_intent_satisfied"] is False
    assert scope["maximum_get_requests"] == 1
    assert scope["maximum_post_requests"] == 0
    assert scope["request_bodies"] == 0
    assert partial["stage_a_intent_satisfied"] is False
    assert partial["active_application_boot_proven"] is False
    assert authority["ordered_requests"] == [
        {
            "ordinal": 1,
            "method": "GET",
            "path": "/api/ec5/h3-matched-control-v2/version",
            "absolute_url": (
                "http://192.168.1.7/api/ec5/h3-matched-control-v2/version"
            ),
        }
    ]
    assert challenge["copyable_authorization_token_present"] is False
    grammar = challenge["exact_authorization_grammar_not_a_token"]
    assert "{64_HEX_UPPER}" in grammar
    assert "__UNVERIFIED_HTTP_192_168_1_7_PORT_80" in grammar
    assert "__NOT_DEVICE_IDENTITY_TRUST_OR_BOOT_PROOF" in grammar
    assert "__CLAIM_0_MUTATION_REQUEST_0_VISIBLE_REFRESH_REQUEST_0" in grammar
    assert challenge["placeholder_grammar_is_not_copyable_user_authorization"] is True
    assert challenge["phase_b_token_issued"] is False
    assert authority["implementation_surface"]["execution_ready"] is False
    assert authority["implementation_surface"]["live_authorized"] is False


def test_locator_is_fresh_explicit_dot7_superseding_dot14_without_trust(
    authority_bundle: tuple[dict[str, Any], Path],
) -> None:
    authority, _ = authority_bundle
    candidate = authority["candidate_origin"]
    gate = authority["fresh_phase_a_onsite_gate"]

    assert candidate["base_url"] == "http://192.168.1.7"
    assert candidate["literal_ipv4"] == "192.168.1.7"
    assert candidate["port"] == 80
    assert candidate["prior_operator_url_superseded_for_this_attempt"] == (
        "http://192.168.1.14"
    )
    assert gate["candidate_selection_phrase"] == phase_a.LOCATOR_SELECTION_PHRASE
    assert candidate["trusted"] is False
    assert candidate["identity_proven"] is False
    assert candidate["arp_is_identity_or_reachability_proof"] is False
    assert candidate["dns_allowed"] is False
    assert candidate["scan_allowed"] is False
    assert candidate["fallback_allowed"] is False


def test_fresh_gate_has_short_expiry_and_every_condition_change_invalidates(
    authority_bundle: tuple[dict[str, Any], Path],
) -> None:
    authority, _ = authority_bundle
    gate = authority["fresh_phase_a_onsite_gate"]

    assert gate["observed_at"] == "2026-08-15T22:00:00+08:00"
    assert gate["prepared_at"] == "2026-08-15T22:01:00+08:00"
    assert gate["not_before_utc"] == "2026-08-15T14:01:00Z"
    assert gate["not_after_utc"] == "2026-08-15T14:10:00Z"
    assert gate["fresh_ttl_seconds"] == 600
    assert gate["maximum_observation_to_prepare_seconds"] == 120
    assert (
        gate["live_consumer_must_reject_when_now_greater_than_or_equal_to_not_after"]
        is True
    )
    assert gate["live_consumer_must_reject_when_now_less_than_not_before"] is True
    assert gate["live_consumer_time_window_rule"] == (
        "not_before_utc <= now_utc < not_after_utc"
    )
    assert gate["any_onsite_condition_change_invalidates_gate"] is True
    assert gate["current_reading_a"] == "0.000"
    for field in (
        "j2_off",
        "screen_clean_white",
        "esp32_usb_connected",
        "supply_3v3_cv_normal",
        "temperature_exact_25c",
        "current_limit_exact_1a",
        "current_and_temperature_monitors_ready",
        "physical_cutoff_ready",
        "no_reset_since_stage_a",
        "no_flash_since_stage_a",
        "no_refresh_since_stage_a",
        "no_rewire_since_stage_a",
    ):
        assert gate[field] is True


@pytest.mark.parametrize(
    ("observed_at", "prepared_at", "match"),
    (
        ("2026-08-15T22:00:00", "2026-08-15T22:01:00+08:00", "UTC offset"),
        ("2026-08-15T22:02:00+08:00", "2026-08-15T22:01:00+08:00", "future"),
        ("2026-08-15T22:00:00+08:00", "2026-08-15T22:03:00+08:00", "stale"),
    ),
)
def test_fresh_gate_rejects_naive_future_and_stale_observations(
    observed_at: str, prepared_at: str, match: str
) -> None:
    kwargs = valid_kwargs(Path("unused"))
    kwargs["observed_at"] = observed_at
    kwargs["prepared_at"] = prepared_at
    onsite_keys = {
        key: value
        for key, value in kwargs.items()
        if key
        not in {
            "blueprint_file",
            "stage_a_receipt_file",
            "authority_file",
            "attempt_registry_file",
            "terminal_receipt_file",
        }
    }
    with pytest.raises(phase_a.PhaseAAuthorityError, match=match):
        phase_a._onsite_gate(**onsite_keys)  # noqa: SLF001


def test_fresh_gate_rejects_missing_assertion_bad_locator_and_bad_current() -> None:
    kwargs = valid_kwargs(Path("unused"))
    onsite_keys = {
        key: value
        for key, value in kwargs.items()
        if key
        not in {
            "blueprint_file",
            "stage_a_receipt_file",
            "authority_file",
            "attempt_registry_file",
            "terminal_receipt_file",
        }
    }

    bad_bool = dict(onsite_keys)
    bad_bool["no_reset_since_stage_a"] = False
    with pytest.raises(phase_a.PhaseAAuthorityError, match="must be true"):
        phase_a._onsite_gate(**bad_bool)  # noqa: SLF001

    bad_locator = dict(onsite_keys)
    bad_locator["locator_selection_phrase"] = "http://192.168.1.14"
    with pytest.raises(phase_a.PhaseAAuthorityError, match="supersession"):
        phase_a._onsite_gate(**bad_locator)  # noqa: SLF001

    bad_current = dict(onsite_keys)
    bad_current["current_reading_a"] = "0.0001"
    with pytest.raises(phase_a.PhaseAAuthorityError, match="0.001 A"):
        phase_a._onsite_gate(**bad_current)  # noqa: SLF001


def test_current_three_field_partial_gate_cli_is_zero_io_and_zero_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """J2 OFF + white + 0 A must not be promoted by the production CLI."""

    def forbid_socket(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("partial Phase-A gate attempted network I/O")

    monkeypatch.setattr(socket, "socket", forbid_socket)
    authority = tmp_path / "phase-a-authority.json"
    registry = tmp_path / "phase-a-attempt-registry.json"
    receipt = tmp_path / "phase-a-terminal-receipt.json"

    exit_code = phase_a.main(
        [
            "build-phase-a",
            "--blueprint",
            str(BLUEPRINT),
            "--stage-a-receipt",
            str(STAGE_A_RECEIPT),
            "--authority-output",
            str(authority),
            "--attempt-registry",
            str(registry),
            "--terminal-receipt",
            str(receipt),
            "--observed-at",
            "2026-08-15T20:59:00+08:00",
            "--prepared-at",
            "2026-08-15T21:00:00+08:00",
            "--current-reading-a",
            "0",
            "--locator-selection-phrase",
            phase_a.LOCATOR_SELECTION_PHRASE,
            "--j2-off",
            "--screen-clean-white",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "every fresh onsite Phase-A assertion must be true" in captured.err
    assert captured.out == ""
    assert not authority.exists()
    assert not registry.exists()
    assert not receipt.exists()
    assert list(tmp_path.iterdir()) == []


def test_phase_a_artifacts_are_distinct_and_cannot_occupy_plan_final(
    authority_bundle: tuple[dict[str, Any], Path], tmp_path: Path
) -> None:
    authority, _ = authority_bundle
    attempt = authority["attempt"]
    original = Path(attempt["original_plan_final_output"])
    assert Path(authority["authority_file"]) != original
    assert Path(attempt["registry_file"]) != original
    assert Path(attempt["terminal_receipt_file"]) != original
    assert attempt["phase_a_must_not_occupy_original_plan_final_output"] is True
    assert attempt["reservation_implemented_by_this_offline_contract"] is False

    kwargs = valid_kwargs(tmp_path)
    kwargs["authority_file"] = original
    with pytest.raises(phase_a.PhaseAAuthorityError, match="no Phase-A artifact"):
        phase_a.materialize_phase_a_authority(**kwargs)


def test_phase_b_is_a_distinct_future_gate_and_never_automatic(
    authority_bundle: tuple[dict[str, Any], Path],
) -> None:
    authority, _ = authority_bundle
    success = authority["phase_a_success_boundary"]
    future = authority["future_phase_b_gate"]

    assert success["success_classification"] == "V10_PROTOCOL_RESPONSE_CONFORMANCE"
    for field in (
        "responder_or_device_identity_proven",
        "trusted_ip_binding_proven",
        "fresh_post_reset_application_boot_proven",
        "active_application_or_ota_slot_proven",
    ):
        assert success[field] is False
    assert success["may_only_unlock_request_for_phase_b_authority"] is True
    assert success["phase_b_authority_automatically_generated"] is False
    assert success["phase_b_automatically_executed"] is False
    assert future["phase_b_endpoints_exactly"] == ["manifest", "status", "report"]
    assert future["phase_b_repeats_version"] is False
    assert future["requires_lossless_base64_phase_a_version_raw_body"] is True
    assert (
        future["phase_b_loader_must_replay_phase_a_raw_body_through_exact_decoder"]
        is True
    )
    assert future["requires_phase_a_registry_whole_file_sha256"] is True


def test_transport_and_terminal_receipt_policy_is_exact_but_not_implemented(
    authority_bundle: tuple[dict[str, Any], Path],
) -> None:
    authority, _ = authority_bundle
    transport = authority["future_live_transport_policy"]
    response = authority["raw_response_contract"]
    evidence = authority["future_terminal_receipt_evidence"]

    assert transport["implemented_by_this_offline_contract"] is False
    assert transport["application_transport_attempts_maximum"] == 1
    assert transport["literal_af_inet_ipv4_only"] is True
    assert transport["dns_or_getaddrinfo_allowed"] is False
    assert transport["proxy_or_environment_routing_allowed"] is False
    assert transport["redirect_allowed"] is False
    assert transport["exact_body_bytes"] == 0
    assert transport["exact_headers"] == {
        "Host": "192.168.1.7",
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    assert transport["request_wire_emitted_on_transport_error"] == "UNKNOWN"
    assert transport["peer_received_request_on_transport_error"] == "UNKNOWN"
    assert response["body_bytes_meaning"] == (
        "HTTP_RESPONSE_ENTITY_BYTES_AFTER_HTTP_FRAMING_NOT_RAW_WIRE_BYTES"
    )
    assert evidence["lossless_base64_response_entity_body_required"] is True
    assert evidence["peer_received_request_must_remain_unknown"] is True


def test_authority_round_trip_o_excl_and_resealed_tamper_fail(
    authority_bundle: tuple[dict[str, Any], Path],
) -> None:
    authority, root = authority_bundle
    summary = phase_a.validate_phase_a_authority(authority)
    assert summary["valid"] is True
    assert summary["execution_ready"] is False
    assert summary["live_authorized"] is False
    assert summary["copyable_authorization_token_present"] is False

    phase_a.write_new_phase_a_authority(Path(authority["authority_file"]), authority)
    output = Path(authority["authority_file"])
    assert output.read_bytes() == contract.canonical_json_bytes(authority) + b"\n"
    derived = phase_a.required_phase_a_authorization(output)
    assert derived.startswith(phase_a.PHASE_A_AUTHORIZATION_PREFIX)
    assert "__UNVERIFIED_HTTP_192_168_1_7_PORT_80" in derived
    with pytest.raises(phase_a.PhaseAAuthorityError, match="already exists"):
        phase_a.write_new_phase_a_authority(output, authority)

    tampered = deepcopy(authority)
    tampered["candidate_origin"]["trusted"] = True
    tampered = phase_a._seal(  # noqa: SLF001
        {key: value for key, value in tampered.items() if key != "integrity"}
    )
    with pytest.raises(phase_a.PhaseAAuthorityError, match="reconstruction"):
        phase_a.validate_phase_a_authority(tampered)
    assert not Path(authority["attempt"]["registry_file"]).exists()
    assert not Path(authority["attempt"]["terminal_receipt_file"]).exists()


def test_source_and_cli_have_no_live_transport_execute_or_token_output() -> None:
    source = Path(phase_a.__file__).read_text(encoding="utf-8")
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
        {"socket", "http", "urllib", "requests", "httpx", "serial", "subprocess"}
    )
    assert "AUTHORIZE_STAGE_B_PHASE_B" not in source
    parser = phase_a._parser()  # noqa: SLF001
    subparsers = [
        action
        for action in parser._actions  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
    ]
    assert len(subparsers) == 1
    assert set(subparsers[0].choices) == {"build-phase-a", "validate-phase-a"}


def test_phase_a_raw_fake_success_reserves_registry_then_output_and_seals_raw_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority, token = write_fake_authority(tmp_path)
    raw = valid_version_raw()
    request = authority["ordered_requests"][0]
    requester = phase_a.ScriptedPhaseAFakeRequester(
        expected_absolute_url=request["absolute_url"],
        response=fake_response(raw),
    )
    original_final = Path(authority["attempt"]["original_plan_final_output"])

    cached_context = valid_v10_context()
    preflight_loads: list[Path] = []

    def tracked_preflight_load(path: Path) -> Any:
        assert requester.calls == []
        preflight_loads.append(path)
        return cached_context

    with monkeypatch.context() as context:
        context.setattr(facade, "_load_frozen_v10_release", tracked_preflight_load)
        receipt = phase_a.run_phase_a_scripted_fake_only(
            Path(authority["authority_file"]),
            authorization=token,
            now="2026-08-15T14:02:00Z",
            requester=requester,
        )
    # One load is the frozen blueprint's deep authority reconstruction; the
    # second yields the context cached for both response and disk replay.  Both
    # must complete before the fake fetch, and there must be no post-fetch load.
    assert len(preflight_loads) == 2

    assert receipt["state"] == "TERMINAL_SUCCESS_FAKE_ONLY"
    assert receipt["classification"] == phase_a.PHASE_A_FAKE_CLASSIFICATION
    assert receipt["fake_fetch_calls"] == 1
    assert receipt["fake_validation_acknowledged"] is True
    assert receipt["version_protocol_response_conformance"] is True
    outcome = receipt["endpoint_outcomes"][0]
    assert outcome["name"] == "version"
    assert outcome["response_received"] is True
    assert outcome["http_status"] == 200
    assert outcome["response_entity_body_bytes"] == len(raw)
    assert outcome["response_entity_body_sha256"] == contract.sha256(raw)
    assert base64.b64decode(outcome["response_entity_body_base64"]) == raw
    parsed = json.loads(raw)
    assert outcome["strict_parsed_canonical_sha256"] == contract.sha256(parsed)
    assert outcome["validation_outcome"] == "PASS"
    assert receipt["phase_b_authority_generated"] is False
    assert receipt["phase_b_requests"] == 0
    assert receipt["original_plan_final_output_touched"] is False
    assert not original_final.exists()
    registry = Path(authority["attempt"]["registry_file"])
    output = Path(authority["attempt"]["terminal_receipt_file"])
    assert registry.exists()
    assert output.read_bytes() == contract.canonical_json_bytes(receipt) + b"\n"
    registry_root = json.loads(registry.read_bytes())
    assert registry_root["state"] == (
        "PERMANENTLY_CONSUMED_BEFORE_OUTPUT_OR_FAKE_FETCH"
    )
    assert registry_root["immutable_after_initial_o_excl_write"] is True
    registry_summary = phase_a.validate_phase_a_attempt_registry(
        registry, authority_file=Path(authority["authority_file"])
    )
    assert registry_summary["sha256"] == contract.sha256(registry.read_bytes())
    receipt_summary = phase_a.validate_phase_a_fake_terminal_receipt(
        output,
        authority_file=Path(authority["authority_file"]),
        require_success=True,
    )
    assert receipt_summary["terminal_success"] is True
    assert receipt_summary["raw_version_replayed"] is True
    assert receipt_summary["eligible_for_live_phase_b_authority"] is False
    with pytest.raises(phase_a.PhaseAAuthorityError, match="never eligible"):
        phase_a.require_live_phase_b_eligible_phase_a_receipt(
            output,
            authority_file=Path(authority["authority_file"]),
            _v10_context=valid_v10_context(),
        )
    for field in (
        "responder_or_device_identity_proven",
        "trusted_ip_binding_proven",
        "fresh_post_reset_application_boot_proven",
        "active_application_or_ota_slot_proven",
    ):
        assert receipt[field] is False

    unused = phase_a.ScriptedPhaseAFakeRequester(
        expected_absolute_url=request["absolute_url"],
        response=fake_response(raw),
    )
    with pytest.raises(phase_a.PhaseAAuthorityError, match="registry exists"):
        phase_a.run_phase_a_scripted_fake_only(
            Path(authority["authority_file"]),
            authorization=token,
            now="2026-08-15T14:03:00Z",
            requester=unused,
        )
    assert unused.calls == []

    tampered = deepcopy(receipt)
    encoded = tampered["endpoint_outcomes"][0]["response_entity_body_base64"]
    tampered["endpoint_outcomes"][0]["response_entity_body_base64"] = (
        "A" if encoded[0] != "A" else "B"
    ) + encoded[1:]
    tampered = phase_a._seal(  # noqa: SLF001
        {key: value for key, value in tampered.items() if key != "integrity"}
    )
    output.write_bytes(contract.canonical_json_bytes(tampered) + b"\n")
    with pytest.raises(phase_a.PhaseAAuthorityError, match="entity binding"):
        phase_a.validate_phase_a_fake_terminal_receipt(
            output,
            authority_file=Path(authority["authority_file"]),
            require_success=True,
            _v10_context=valid_v10_context(),
        )

    for field, match in (
        ("response_entity_body_sha256", "orphaned"),
        ("synthetic_canonical_status_and_header_sha256", "orphaned"),
        ("strict_parsed_canonical_sha256", "parsed evidence"),
    ):
        orphaned = deepcopy(receipt)
        orphaned["endpoint_outcomes"][0][field] = None
        orphaned = phase_a._seal(  # noqa: SLF001
            {key: value for key, value in orphaned.items() if key != "integrity"}
        )
        output.write_bytes(contract.canonical_json_bytes(orphaned) + b"\n")
        with pytest.raises(phase_a.PhaseAAuthorityError, match=match):
            phase_a.validate_phase_a_fake_terminal_receipt(
                output,
                authority_file=Path(authority["authority_file"]),
                require_success=False,
                _v10_context=valid_v10_context(),
            )

    false_failure = deepcopy(receipt)
    false_failure["state"] = "TERMINAL_FAILURE_FAKE_ONLY_NO_RETRY"
    false_failure["error_type"] = "InjectedError"
    false_failure["error"] = "falsely relabeled"
    false_failure["fake_validation_acknowledged"] = False
    false_failure["version_protocol_response_conformance"] = False
    false_failure["endpoint_outcomes"][0]["last_completed_gate"] = "HTTP_ENVELOPE_OK"
    false_failure["endpoint_outcomes"][0]["failure_stage"] = (
        "STRICT_JSON_OR_EXACT_V10_GATE"
    )
    false_failure["endpoint_outcomes"][0]["validation_outcome"] = (
        "FAILED_TERMINAL_NO_RETRY"
    )
    false_failure["endpoint_outcomes"][0]["strict_parsed_canonical_sha256"] = None
    false_failure = phase_a._seal(  # noqa: SLF001
        {key: value for key, value in false_failure.items() if key != "integrity"}
    )
    output.write_bytes(contract.canonical_json_bytes(false_failure) + b"\n")
    with pytest.raises(phase_a.PhaseAAuthorityError, match="falsely classified"):
        phase_a.validate_phase_a_fake_terminal_receipt(
            output,
            authority_file=Path(authority["authority_file"]),
            require_success=False,
            _v10_context=valid_v10_context(),
        )


def test_wrong_or_expired_authorization_stops_before_reservation_and_fake_fetch(
    tmp_path: Path,
) -> None:
    wrong_root = tmp_path / "wrong"
    authority, token = write_fake_authority(wrong_root)
    request = authority["ordered_requests"][0]
    requester = phase_a.ScriptedPhaseAFakeRequester(
        expected_absolute_url=request["absolute_url"],
        response=fake_response(valid_version_raw()),
    )
    with pytest.raises(phase_a.PhaseAAuthorityError, match="authorization differs"):
        phase_a.run_phase_a_scripted_fake_only(
            Path(authority["authority_file"]),
            authorization=token.lower(),
            now="2026-08-15T14:02:00Z",
            requester=requester,
        )
    assert requester.calls == []
    assert not Path(authority["attempt"]["registry_file"]).exists()
    assert not Path(authority["attempt"]["terminal_receipt_file"]).exists()

    expired_root = tmp_path / "expired"
    expired, expired_token = write_fake_authority(expired_root)
    expired_requester = phase_a.ScriptedPhaseAFakeRequester(
        expected_absolute_url=expired["ordered_requests"][0]["absolute_url"],
        response=fake_response(valid_version_raw()),
    )
    with pytest.raises(phase_a.PhaseAAuthorityError, match="not currently valid"):
        phase_a.run_phase_a_scripted_fake_only(
            Path(expired["authority_file"]),
            authorization=expired_token,
            now="2026-08-15T14:10:00Z",
            requester=expired_requester,
        )
    assert expired_requester.calls == []
    assert not Path(expired["attempt"]["registry_file"]).exists()


@pytest.mark.parametrize(
    ("mode", "match"),
    (
        ("transport", "scripted fake transport error"),
        ("http", "HTTP 500"),
        ("encoding", "content encoding"),
        ("non-ascii-header", "not ASCII"),
        ("oversize", "body size"),
        ("duplicate-json", "strict UTF-8 JSON"),
        ("semantic", "classification"),
    ),
)
def test_phase_a_fake_transport_http_raw_and_exact_failures_are_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, match: str
) -> None:
    root = tmp_path / mode
    authority, token = write_fake_authority(root)
    request = authority["ordered_requests"][0]
    raw = valid_version_raw()
    if mode == "transport":
        requester = phase_a.ScriptedPhaseAFakeRequester(
            expected_absolute_url=request["absolute_url"],
            transport_error="connect timeout",
        )
    elif mode == "http":
        requester = phase_a.ScriptedPhaseAFakeRequester(
            expected_absolute_url=request["absolute_url"],
            response=fake_response(raw, status=500),
        )
    elif mode == "encoding":
        requester = phase_a.ScriptedPhaseAFakeRequester(
            expected_absolute_url=request["absolute_url"],
            response=fake_response(raw, extra_headers=(("Content-Encoding", "gzip"),)),
        )
    elif mode == "oversize":
        requester = phase_a.ScriptedPhaseAFakeRequester(
            expected_absolute_url=request["absolute_url"],
            response=fake_response(b" " * (facade.MAX_JSON_BYTES + 1)),
        )
    elif mode == "non-ascii-header":
        requester = phase_a.ScriptedPhaseAFakeRequester(
            expected_absolute_url=request["absolute_url"],
            response=fake_response(raw, extra_headers=(("X-Test", "\N{SNOWMAN}"),)),
        )
    elif mode == "duplicate-json":
        requester = phase_a.ScriptedPhaseAFakeRequester(
            expected_absolute_url=request["absolute_url"],
            response=fake_response(b'{"a":1,"a":2}'),
        )
    else:
        parsed = json.loads(raw)
        parsed["classification"] = "WRONG"
        requester = phase_a.ScriptedPhaseAFakeRequester(
            expected_absolute_url=request["absolute_url"],
            response=fake_response(contract.canonical_json_bytes(parsed)),
        )

    monkeypatch.setattr(
        facade,
        "_load_frozen_v10_release",
        lambda _: valid_v10_context(),
    )

    receipt = phase_a.run_phase_a_scripted_fake_only(
        Path(authority["authority_file"]),
        authorization=token,
        now="2026-08-15T14:02:00Z",
        requester=requester,
    )

    assert receipt["state"] == "TERMINAL_FAILURE_FAKE_ONLY_NO_RETRY"
    assert match.lower() in receipt["error"].lower()
    assert receipt["version_protocol_response_conformance"] is False
    assert receipt["phase_b_authority_generated"] is False
    assert receipt["phase_b_requests"] == 0
    assert receipt["eligible_for_live_phase_b_authority"] is False
    assert Path(authority["attempt"]["registry_file"]).exists()
    assert Path(authority["attempt"]["terminal_receipt_file"]).exists()
    assert not Path(authority["attempt"]["original_plan_final_output"]).exists()
    outcome = receipt["endpoint_outcomes"][0]
    if mode == "oversize":
        assert outcome["response_entity_body_bytes"] == facade.MAX_JSON_BYTES + 1
        assert outcome["response_entity_body_sha256"] is None
        assert outcome["response_entity_body_base64"] is None
    if mode == "encoding":
        assert outcome["response_headers_bounded"] is not None
        assert outcome["synthetic_canonical_status_and_header_sha256"] is not None
    if mode == "non-ascii-header":
        assert outcome["last_completed_gate"] == "BODY_SIZE_OK"
        assert outcome["response_header_count"] is None
        assert outcome["response_headers_bounded"] is None


def test_preexisting_registry_or_output_blocks_before_fake_fetch(
    tmp_path: Path,
) -> None:
    registry_root = tmp_path / "registry-collision"
    authority, token = write_fake_authority(registry_root)
    registry = Path(authority["attempt"]["registry_file"])
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text("occupied", encoding="utf-8")
    requester = phase_a.ScriptedPhaseAFakeRequester(
        expected_absolute_url=authority["ordered_requests"][0]["absolute_url"],
        response=fake_response(valid_version_raw()),
    )
    with pytest.raises(phase_a.PhaseAAuthorityError, match="registry exists"):
        phase_a.run_phase_a_scripted_fake_only(
            Path(authority["authority_file"]),
            authorization=token,
            now="2026-08-15T14:02:00Z",
            requester=requester,
        )
    assert requester.calls == []
    assert not Path(authority["attempt"]["terminal_receipt_file"]).exists()

    output_root = tmp_path / "output-collision"
    output_authority, output_token = write_fake_authority(output_root)
    output = Path(output_authority["attempt"]["terminal_receipt_file"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("occupied", encoding="utf-8")
    output_requester = phase_a.ScriptedPhaseAFakeRequester(
        expected_absolute_url=output_authority["ordered_requests"][0]["absolute_url"],
        response=fake_response(valid_version_raw()),
    )
    with pytest.raises(phase_a.PhaseAAuthorityError, match="output exists"):
        phase_a.run_phase_a_scripted_fake_only(
            Path(output_authority["authority_file"]),
            authorization=output_token,
            now="2026-08-15T14:02:00Z",
            requester=output_requester,
        )
    assert output_requester.calls == []
    assert not Path(output_authority["attempt"]["registry_file"]).exists()


def test_registry_survives_output_reservation_failure_without_fake_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority, token = write_fake_authority(tmp_path)
    request = authority["ordered_requests"][0]
    requester = phase_a.ScriptedPhaseAFakeRequester(
        expected_absolute_url=request["absolute_url"],
        response=fake_response(valid_version_raw()),
    )
    monkeypatch.setattr(
        facade,
        "_load_frozen_v10_release",
        lambda _: valid_v10_context(),
    )
    original_reserve = phase_a._reserve_sink  # noqa: SLF001

    def fail_second_reservation(
        path: Path, *, label: str, initial: dict[str, Any]
    ) -> Any:
        if label == "Phase-A terminal receipt":
            raise phase_a.PhaseAAuthorityError("injected output fsync failure")
        return original_reserve(path, label=label, initial=initial)

    monkeypatch.setattr(phase_a, "_reserve_sink", fail_second_reservation)
    with pytest.raises(phase_a.PhaseAAuthorityError, match="output fsync failure"):
        phase_a.run_phase_a_scripted_fake_only(
            Path(authority["authority_file"]),
            authorization=token,
            now="2026-08-15T14:02:00Z",
            requester=requester,
        )
    assert requester.calls == []
    registry = Path(authority["attempt"]["registry_file"])
    assert registry.exists()
    registry_root = json.loads(registry.read_bytes())
    assert registry_root["state"] == (
        "PERMANENTLY_CONSUMED_BEFORE_OUTPUT_OR_FAKE_FETCH"
    )
    assert registry_root["immutable_after_initial_o_excl_write"] is True
    assert not Path(authority["attempt"]["terminal_receipt_file"]).exists()
    assert not Path(authority["attempt"]["original_plan_final_output"]).exists()


def test_fake_runner_rejects_arbitrary_requester_before_reservation(
    tmp_path: Path,
) -> None:
    authority, token = write_fake_authority(tmp_path)

    class ArbitraryRequester:
        pass

    with pytest.raises(phase_a.PhaseAAuthorityError, match="exact scripted fake"):
        phase_a.run_phase_a_scripted_fake_only(  # type: ignore[arg-type]
            Path(authority["authority_file"]),
            authorization=token,
            now="2026-08-15T14:02:00Z",
            requester=ArbitraryRequester(),
        )
    assert not Path(authority["attempt"]["registry_file"]).exists()
    assert not Path(authority["attempt"]["terminal_receipt_file"]).exists()
