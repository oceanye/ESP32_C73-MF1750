from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_authority_contract as phase_a
from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_live_once as phase_a_live
from tools import mf1750_ec5_h3_c_first_stage_b_phase_b_live_once as live
from tools import mf1750_ec5_h3_c_first_stage_b_phase_b_offline_gate as gate_mod
from tools import mf1750_ec5_h3_c_first_stage_b_read_only_facade_contract as facade
from tools import mf1750_ec5_h3_matched_control_contract as contract
from tools import mf1750_ec5_h3_matched_control_physical_once as physical


REPO_ROOT = Path(__file__).resolve().parents[1]
OFFLINE_GATE = (
    REPO_ROOT
    / ".test-output"
    / "offline"
    / "MF1750_EC5_H3_C_FIRST_PHASE_B_OFFLINE_GATE_20260816_V1"
    / "WF20_25-phase-b-offline-gate.json"
)
V10_RELEASE = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_MATCHED_CONTROL_C_FIRST_RELEASES_20260813_V10"
    / "WF20_25-release.json"
)
OBSERVED = "2026-08-16T09:42:00+08:00"
PREPARED = "2026-08-16T09:42:10+08:00"
BUILT = "2026-08-16T09:42:15+08:00"
RUN = datetime(2026, 8, 16, 1, 42, 20, tzinfo=timezone.utc)


def _http_response(body: bytes) -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("ascii")
        + b"Content-Type: application/json\r\n"
        + b"Connection: close\r\n\r\n"
        + body
    )


def _valid_script() -> list[tuple[str, bytes]]:
    context = physical.load_release(V10_RELEASE)
    bodies = [
        facade.expected_v10_response_fixture("manifest", context),
        facade.expected_v10_response_fixture(
            "status", context, boot_nonce="0123456789abcdef", busy=1
        ),
        facade.expected_v10_response_fixture("report", context),
    ]
    return [
        (name, _http_response(contract.canonical_json_bytes(body)))
        for name, body in zip(live.ENDPOINT_NAMES, bodies, strict=True)
    ]


def _authority_args(root: Path, suffix: str) -> dict[str, Any]:
    return {
        "offline_gate_file": OFFLINE_GATE,
        "live_authority_file": root / f"authority-{suffix}.synthetic-test-only.json",
        "observed_at": OBSERVED,
        "prepared_at": PREPARED,
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
        "_synthetic_test_only": True,
        "_synthetic_registry_file": (
            root / f"registry-{suffix}.synthetic-test-only.json"
        ),
        "_synthetic_terminal_receipt_file": (
            root / f"receipt-{suffix}.synthetic-test-only.json"
        ),
    }


def _write_synthetic_bundle(
    root: Path, suffix: str
) -> tuple[Path, str, dict[str, Any]]:
    args = _authority_args(root, suffix)
    authority = live.materialize_phase_b_live_authority(**args)
    authority_path = Path(args["live_authority_file"])
    live._write_new_json(  # noqa: SLF001
        authority_path, authority, label="synthetic Phase-B authority"
    )
    envelope_path = root / f"envelope-{suffix}.synthetic-test-only.json"
    envelope = live.materialize_phase_b_live_execution_envelope(
        live_authority_file=authority_path,
        live_envelope_file=envelope_path,
        built_at=BUILT,
        _allow_synthetic_test_only=True,
    )
    live._write_new_json(  # noqa: SLF001
        envelope_path, envelope, label="synthetic Phase-B envelope"
    )
    token = live._authorization_phrase(  # noqa: SLF001
        envelope,
        envelope_file_sha256=contract.sha256(envelope_path.read_bytes()),
    )
    return envelope_path, token, authority


@pytest.fixture(scope="module")
def fast_gate_validation() -> Any:
    gate = gate_mod.load_phase_b_offline_gate(OFFLINE_GATE)
    summary = gate_mod.validate_phase_b_offline_gate(gate)
    patch = pytest.MonkeyPatch()

    def cached(root: Any, *, require_attempt_paths_absent: bool) -> dict[str, Any]:
        live._validate_seal(root, label="cached offline Phase-B gate")  # noqa: SLF001
        assert root["offline_gate_id"] == gate["offline_gate_id"]
        return {
            **summary,
            "phase_a_raw_version_replayed": True,
            "phase_b_endpoints": list(live.ENDPOINT_NAMES),
        }

    patch.setattr(live, "_validate_offline_gate_bound", cached)
    yield summary
    patch.undo()


def test_fixed_surface_and_public_cli_have_no_network_overrides() -> None:
    parser = live._parser()  # noqa: SLF001
    execute = next(
        action.choices["execute"]
        for action in parser._actions  # noqa: SLF001
        if hasattr(action, "choices") and action.choices
    )
    option_strings = {
        option
        for action in execute._actions  # noqa: SLF001
        for option in action.option_strings
    }
    assert option_strings == {"-h", "--help", "--envelope", "--authorization"}
    assert live.LITERAL_IPV4 == "192.168.1.7"
    assert live.ENDPOINT_NAMES == ("manifest", "status", "report")
    assert live.MAX_RESPONSE_ENTITY_BYTES == 65_536
    assert not hasattr(live, "execute_phase_a_live_once")


def test_runner_review_deep_binds_p0_source_and_tests(tmp_path: Path) -> None:
    review_path = tmp_path / "phase-b-runner-review.json"
    root = live.materialize_runner_review(
        offline_gate_file=OFFLINE_GATE,
        runner_review_file=review_path,
        test_file=Path(__file__),
    )
    assert root["classification"] == live.RUNNER_REVIEW_CLASSIFICATION
    assert root["reviewed_network_surface"]["ordered_endpoint_names"] == [
        "manifest",
        "status",
        "report",
    ]
    assert root["reviewed_network_surface"]["maximum_gets"] == 3
    assert (
        root["reviewed_network_surface"][
            "post_body_claim_mutation_visible_refresh_requests"
        ]
        == 0
    )
    assert root["authority_boundary"]["execution_ready"] is False
    assert root["authority_boundary"]["live_authorized"] is False
    assert root["device_io_performed"] is False


def test_post_attempt_validator_can_replay_sealed_gate_without_absence_claim() -> None:
    gate = gate_mod.load_phase_b_offline_gate(OFFLINE_GATE)
    summary = live._validate_offline_gate_bound(  # noqa: SLF001
        gate, require_attempt_paths_absent=False
    )
    assert summary["valid"] is True
    assert summary["phase_a_predecessor_committed_success"] is True
    assert summary["phase_a_raw_version_replayed"] is True
    assert summary["phase_b_endpoints"] == ["manifest", "status", "report"]


def test_synthetic_three_get_success_and_committed_deep_replay(
    tmp_path: Path, fast_gate_validation: Any
) -> None:
    envelope_path, token, _ = _write_synthetic_bundle(tmp_path, "success")
    transport = live._ScriptedPhaseBTransport(_valid_script())  # noqa: SLF001
    clock = phase_a_live._ScriptedUTCClock([RUN] * 8)  # noqa: SLF001

    result = live._execute_phase_b_synthetic_test_only(  # noqa: SLF001
        envelope_path,
        authorization=token,
        clock=clock,
        transport=transport,
    )

    assert result["state"] == (
        "TERMINAL_SUCCESS_V10_MANIFEST_STATUS_REPORT_PROTOCOL_RESPONSE_CONFORMANCE"
    )
    assert transport.calls == ["manifest", "status", "report"]
    assert result["validated_response_names"] == ["manifest", "status", "report"]
    assert result["application_transport_attempts"] == 3
    assert result["fully_written_gets"] == 3
    assert result["post_requests"] == 0
    assert result["request_bodies"] == 0
    assert result["device_api_claim_requests"] == 0
    assert result["client_mutation_requests"] == 0
    assert result["client_visible_refresh_requests"] == 0
    assert result["responder_or_device_identity_proven"] is False
    assert result["fresh_post_reset_application_boot_proven"] is False
    assert result["visible_action_authorized"] is False
    summary = live._validate_terminal_file(  # noqa: SLF001
        envelope_path,
        require_success=True,
        allow_synthetic_test_only=True,
    )
    assert summary["terminal_outcome_committed"] is True
    assert summary["validated_response_names"] == ["manifest", "status", "report"]
    assert summary["phase_a_version_repeated"] is False


def test_failure_at_status_stops_report_and_attempt_cannot_retry(
    tmp_path: Path, fast_gate_validation: Any
) -> None:
    envelope_path, token, _ = _write_synthetic_bundle(tmp_path, "failure")
    script = _valid_script()
    script[1] = (
        "status",
        _http_response(b'{"duplicate":1,"duplicate":2}'),
    )
    transport = live._ScriptedPhaseBTransport(script)  # noqa: SLF001
    result = live._execute_phase_b_synthetic_test_only(  # noqa: SLF001
        envelope_path,
        authorization=token,
        clock=phase_a_live._ScriptedUTCClock([RUN] * 8),  # noqa: SLF001
        transport=transport,
    )
    assert result["state"] == "TERMINAL_FAILURE_NO_RETRY"
    assert transport.calls == ["manifest", "status"]
    assert result["validated_response_names"] == ["manifest"]
    assert result["endpoint_outcomes"][-1]["validation_outcome"] == (
        "FAILED_TERMINAL_NO_RETRY"
    )
    assert result["retry_allowed"] is False
    second = live._ScriptedPhaseBTransport(_valid_script())  # noqa: SLF001
    with pytest.raises(live.PhaseBLiveError, match="already exists|no retry"):
        live._execute_phase_b_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            clock=phase_a_live._ScriptedUTCClock([RUN] * 8),  # noqa: SLF001
            transport=second,
        )
    assert second.calls == []


def test_broad_authorization_fails_before_registry_or_socket(
    tmp_path: Path, fast_gate_validation: Any
) -> None:
    envelope_path, _, authority = _write_synthetic_bundle(tmp_path, "broad")
    transport = live._ScriptedPhaseBTransport(_valid_script())  # noqa: SLF001
    with pytest.raises(live.PhaseBLiveError, match="exact runner-bound"):
        live._execute_phase_b_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization="授权完整给你，我需要快速进入真屏测试",
            clock=phase_a_live._ScriptedUTCClock([RUN] * 8),  # noqa: SLF001
            transport=transport,
        )
    assert transport.calls == []
    assert not Path(authority["attempt"]["registry_file"]).exists()
    assert not Path(authority["attempt"]["terminal_receipt_file"]).exists()


def test_resealed_envelope_tamper_and_stale_gate_fail_closed(
    tmp_path: Path, fast_gate_validation: Any
) -> None:
    envelope_path, _, _ = _write_synthetic_bundle(tmp_path, "tamper")
    _, _, envelope = live._read_json(  # noqa: SLF001
        envelope_path, label="synthetic envelope"
    )
    tampered = deepcopy(envelope)
    tampered["transport_policy"]["maximum_gets"] = 4
    tampered = live._seal(  # noqa: SLF001
        {key: value for key, value in tampered.items() if key != "integrity"}
    )
    with pytest.raises(live.PhaseBLiveError, match="reconstruction|ID"):
        live._validate_envelope_root(  # noqa: SLF001
            tampered,
            require_attempt_paths_absent=True,
            allow_synthetic_test_only=True,
        )

    _, _, valid = live._read_json(envelope_path, label="synthetic envelope")  # noqa: SLF001
    token = live._authorization_phrase(  # noqa: SLF001
        valid, envelope_file_sha256=contract.sha256(envelope_path.read_bytes())
    )
    late = datetime(2026, 8, 16, 1, 53, 0, tzinfo=timezone.utc)
    transport = live._ScriptedPhaseBTransport(_valid_script())  # noqa: SLF001
    with pytest.raises(live.PhaseBLiveError, match="outside"):
        live._execute_phase_b_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            clock=phase_a_live._ScriptedUTCClock([late] * 4),  # noqa: SLF001
            transport=transport,
        )
    assert transport.calls == []
