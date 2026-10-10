from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
import inspect
import os
from pathlib import Path
from typing import Any

import pytest

from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_authority_contract as phase_a
from tools import mf1750_ec5_h3_c_first_stage_b_phase_a_live_once as live
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
NOW = datetime(2026, 8, 15, 14, 2, 0, tzinfo=timezone.utc)
NOW_TEXT = "2026-08-15T14:02:00Z"


def _offline_authority_kwargs(root: Path) -> dict[str, Any]:
    return {
        "blueprint_file": BLUEPRINT,
        "stage_a_receipt_file": STAGE_A_RECEIPT,
        "authority_file": root / "offline-phase-a-authority.json",
        "attempt_registry_file": root / "unused-live-registry.json",
        "terminal_receipt_file": root / "unused-live-receipt.json",
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


@pytest.fixture(scope="module")
def offline_authority_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("phase-a-live-offline-authority")
    authority = phase_a.materialize_phase_a_authority(**_offline_authority_kwargs(root))
    path = Path(authority["authority_file"])
    path.write_bytes(contract.canonical_json_bytes(authority) + b"\n")
    return path


def _make_synthetic_envelope(
    root: Path, offline_authority_file: Path, *, tag: str
) -> tuple[Path, dict[str, Any], str, live._LiveBundle]:  # noqa: SLF001
    envelope_path = root / f"{tag}-live-envelope.synthetic-test-only.json"
    registry_path = root / f"{tag}-registry.synthetic-test-only.json"
    receipt_path = root / f"{tag}-receipt.synthetic-test-only.json"
    envelope = live.materialize_live_execution_envelope(
        phase_a_authority_file=offline_authority_file,
        live_envelope_file=envelope_path,
        built_at="2026-08-15T14:01:30Z",
        _synthetic_test_only=True,
        _synthetic_registry_file=registry_path,
        _synthetic_terminal_receipt_file=receipt_path,
    )
    envelope_path.write_bytes(contract.canonical_json_bytes(envelope) + b"\n")
    live._validate_live_envelope_root(  # noqa: SLF001
        envelope,
        require_attempt_paths_absent=True,
        allow_synthetic_test_only=True,
    )
    token = live._authorization_phrase(  # noqa: SLF001
        envelope,
        envelope_file_sha256=contract.sha256(envelope_path.read_bytes()),
    )
    bundle = live._load_live_bundle(  # noqa: SLF001
        envelope_path,
        require_attempt_paths_absent=True,
        allow_synthetic_test_only=True,
    )
    return envelope_path, envelope, token, bundle


def _http_response(
    body: bytes,
    *,
    status: bytes = b"HTTP/1.1 200 OK",
    headers: tuple[bytes, ...] = (),
    append: bytes = b"",
) -> bytes:
    return (
        b"\r\n".join(
            (
                status,
                b"Content-Type: application/json",
                f"Content-Length: {len(body)}".encode("ascii"),
                b"Connection: close",
                *headers,
                b"",
                b"",
            )
        )
        + body
        + append
    )


def _version_body(context: Any) -> bytes:
    return contract.canonical_json_bytes(
        facade.expected_v10_response_fixture("version", context)
    )


@pytest.fixture(scope="module")
def success_run(
    tmp_path_factory: pytest.TempPathFactory, offline_authority_file: Path
) -> dict[str, Any]:
    root = tmp_path_factory.mktemp("phase-a-live-success")
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        root, offline_authority_file, tag="success"
    )
    body = _version_body(bundle.v10_context)
    raw = _http_response(body)
    transport = live._BuiltInScriptedTestTransport(  # noqa: SLF001
        response_chunks=(raw[:1], raw[1:19], raw[19:])
    )
    clock = live._ScriptedUTCClock((NOW, NOW))  # noqa: SLF001
    receipt = live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
        envelope_path,
        authorization=token,
        now=NOW_TEXT,
        clock=clock,
        transport=transport,
        _preloaded_bundle=bundle,
    )
    return {
        "root": root,
        "envelope_path": envelope_path,
        "envelope": envelope,
        "token": token,
        "bundle": bundle,
        "body": body,
        "raw": raw,
        "transport": transport,
        "receipt": receipt,
        "registry_path": Path(envelope["attempt"]["registry_file"]),
        "receipt_path": Path(envelope["attempt"]["terminal_receipt_file"]),
    }


def test_live_envelope_binds_runner_all_sources_wire_and_old_token_is_insufficient(
    success_run: dict[str, Any], offline_authority_file: Path
) -> None:
    envelope = success_run["envelope"]
    sources = envelope["source_bindings"]
    policy = envelope["transport_policy"]
    grammar = envelope["authorization_challenge"]["placeholder_grammar_not_a_token"]

    assert sources["phase_a_live_runner_module"]["sha256"] == contract.sha256(
        Path(live.__file__).read_bytes()
    )
    assert {
        "offline_phase_a_authority_module",
        "v2_exact_surface_facade_module",
        "phase_a_live_runner_module",
        "matched_control_contract_module",
        "frozen_physical_validator_module",
        "diagnostic_recovery_contract_module",
        "stage_a_receipt_contract_module",
    } <= set(sources)
    assert policy["literal_ipv4"] == "192.168.1.7"
    assert policy["port"] == 80
    assert policy["dns_or_getaddrinfo"] is False
    assert policy["proxy_or_environment_routing"] is False
    assert policy["application_retry"] is False
    assert policy["request_wire_sha256"] == contract.sha256(live.REQUEST_WIRE_BYTES)
    assert policy["maximum_response_entity_bytes"] == 65_536
    assert "__UNVERIFIED_HTTP_192_168_1_7_PORT_80" in grammar
    assert "__NOT_DEVICE_IDENTITY_TRUST_OR_BOOT_PROOF" in grammar
    assert "__CLAIM_0_MUTATION_REQUEST_0_VISIBLE_REFRESH_REQUEST_0" in grammar

    old = phase_a.required_phase_a_authorization(offline_authority_file)
    assert old != success_run["token"]
    assert envelope["offline_phase_a_authorization_is_not_live_authorization"] is True

    copied = success_run["root"] / "copied-envelope.synthetic-test-only.json"
    copied.write_bytes(success_run["envelope_path"].read_bytes())
    with pytest.raises(live.PhaseALiveError, match="actual live envelope path differs"):
        live._required_authorization_for_file(  # noqa: SLF001
            copied, allow_synthetic_test_only=True
        )


def test_production_public_and_cli_have_no_clock_network_or_origin_injection() -> None:
    signature = inspect.signature(live.execute_phase_a_live_once)
    assert tuple(signature.parameters) == ("envelope_file", "authorization")
    source = Path(live.__file__).read_text(encoding="utf-8")
    assert "socket.getaddrinfo" not in source
    assert "socket.create_connection" not in source
    assert "requests." not in source
    assert "urllib" not in source
    assert "http.client" not in source
    assert (
        "socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)"
        in source
    )

    parser = live._parser()  # noqa: SLF001
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "execute-phase-a-live",
                "--authority",
                "x.json",
                "--authorization",
                "bad",
                "--now",
                NOW_TEXT,
            ]
        )
    for forbidden in ("--host", "--port", "--timeout", "--requester", "--proxy"):
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "execute-phase-a-live",
                    "--authority",
                    "x.json",
                    "--authorization",
                    "bad",
                    forbidden,
                    "x",
                ]
            )


def test_file_snapshot_rejects_byte_replacement_and_hardlinks(tmp_path: Path) -> None:
    target = tmp_path / "evidence.json"
    target.write_bytes(b"first")
    snapshot = live._snapshot(target, label="test evidence")  # noqa: SLF001
    target.write_bytes(b"other")
    with pytest.raises(live.PhaseALiveError, match="changed"):
        snapshot.assert_unchanged()

    target.write_bytes(b"first")
    alias = tmp_path / "hardlink.json"
    try:
        os.link(target, alias)
    except OSError as error:
        pytest.skip(f"hard links unavailable: {error}")
    with pytest.raises(live.PhaseALiveError, match="regular file"):
        live._snapshot(target, label="hardlinked evidence")  # noqa: SLF001


@pytest.mark.parametrize(
    "raw",
    (
        b"HTTP/1.1 200 OK\nContent-Length: 2\n\n",
        b"HTTP/1.1 200 OK\r\n Content-Length: 2\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nBad Name: x\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nX: \xff\r\n\r\n",
        b"HTTP/1.1 302 Found\r\nContent-Length: 2\r\n\r\n",
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: 2\r\nContent-Length: 2\r\nConnection: close\r\n\r\n"
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Type: application/json\r\nContent-Length: 2\r\n"
            b"Connection: close\r\n\r\n"
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n"
            b"Connection: close\r\n\r\n"
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: 2\r\nContent-Encoding: gzip\r\n"
            b"Connection: close\r\n\r\n"
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=latin1\r\n"
            b"Content-Length: 2\r\nConnection: close\r\n\r\n"
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: 02\r\nConnection: close\r\n\r\n"
        ),
        (
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + b"Content-Length: "
            + (b"9" * 5_000)
            + b"\r\nConnection: close\r\n\r\n"
        ),
    ),
)
def test_raw_http_parser_rejects_ambiguous_or_unsafe_envelopes(raw: bytes) -> None:
    with pytest.raises(live.PhaseALiveTransportError):
        live._parse_status_and_headers(raw)  # noqa: SLF001


def test_raw_http_reader_handles_one_byte_fragmentation_and_retains_failures() -> None:
    body = b"{}"
    raw = _http_response(body)
    endpoint = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    endpoint["application_transport_attempts"] = 1
    endpoint["request_write_called"] = True
    endpoint["request_write_completed"] = True
    endpoint["request_bytes_handed_to_socket_api"] = len(live.REQUEST_WIRE_BYTES)
    endpoint["last_completed_gate"] = "REQUEST_WRITE_COMPLETED"
    response = live._read_exact_http_response(  # noqa: SLF001
        live._ScriptedReader(
            tuple(bytes((item,)) for item in raw), terminal_error=None
        ),  # noqa: SLF001
        endpoint=endpoint,
    )
    live._finalize_bounded_response_evidence(endpoint)  # noqa: SLF001
    assert response.entity_body == body
    assert (
        base64.b64decode(endpoint["bounded_response_prefix_base64"], validate=True)
        == raw
    )
    assert endpoint["bounded_response_prefix_truncated"] is False

    early = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    with pytest.raises(live.PhaseALiveTransportError, match="EOF"):
        live._read_exact_http_response(  # noqa: SLF001
            live._ScriptedReader((raw[:-2],), terminal_error=None),  # noqa: SLF001
            endpoint=early,
        )
    live._finalize_bounded_response_evidence(early)  # noqa: SLF001
    assert early["bounded_response_prefix_bytes"] == len(raw) - 2
    assert (
        base64.b64decode(early["bounded_response_prefix_base64"], validate=True)
        == raw[:-2]
    )


def test_header_budget_boundary_roundtrips_reachable_rank5_and_rank6(
    success_run: dict[str, Any],
) -> None:
    incomplete = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    incomplete.update(
        {
            "last_completed_gate": "REQUEST_WRITE_COMPLETED",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
        }
    )
    unresolved = b"A" * live.MAX_STATUS_HEADER_BYTES
    with pytest.raises(live.PhaseALiveTransportError, match="exceed byte budget"):
        live._read_exact_http_response(  # noqa: SLF001
            live._ScriptedReader((unresolved,), terminal_error=None),  # noqa: SLF001
            endpoint=incomplete,
        )
    live._finalize_bounded_response_evidence(incomplete)  # noqa: SLF001
    incomplete["failure_stage"] = "RESPONSE_STATUS_HEADER_READ"
    incomplete["validation_outcome"] = "FAILED_TERMINAL_NO_RETRY"
    live._validate_endpoint_evidence(  # noqa: SLF001
        incomplete,
        bundle=success_run["bundle"],
        terminal_success=False,
    )

    received = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    received.update(
        {
            "last_completed_gate": "REQUEST_WRITE_COMPLETED",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
        }
    )
    header_prefix = b"HTTP/1.1 200 OK\r\nX: "
    terminal_delimiter = b"\r\n\r\n"
    exact_budget_header = (
        header_prefix
        + b"A"
        * (live.MAX_STATUS_HEADER_BYTES - len(header_prefix) - len(terminal_delimiter))
        + terminal_delimiter
    )
    assert len(exact_budget_header) == live.MAX_STATUS_HEADER_BYTES
    with pytest.raises(
        live.PhaseALiveTransportError,
        match="exactly one Content-Length",
    ):
        live._read_exact_http_response(  # noqa: SLF001
            live._ScriptedReader(  # noqa: SLF001
                (exact_budget_header,), terminal_error=None
            ),
            endpoint=received,
        )
    live._finalize_bounded_response_evidence(received)  # noqa: SLF001
    received["failure_stage"] = "HTTP_ENVELOPE_VALIDATION"
    received["validation_outcome"] = "FAILED_TERMINAL_NO_RETRY"
    live._validate_endpoint_evidence(  # noqa: SLF001
        received,
        bundle=success_run["bundle"],
        terminal_success=False,
    )


def test_pre_header_gate_rejects_hidden_complete_delimiter(
    success_run: dict[str, Any],
) -> None:
    endpoint = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    hidden = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n"
    endpoint.update(
        {
            "last_completed_gate": "REQUEST_WRITE_COMPLETED",
            "failure_stage": "RESPONSE_STATUS_HEADER_READ",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
            "observed_response_octets_total": len(hidden),
            "bounded_response_prefix_bytes": len(hidden),
            "bounded_response_prefix_sha256": contract.sha256(hidden),
            "bounded_response_prefix_base64": base64.b64encode(hidden).decode("ascii"),
            "validation_outcome": "FAILED_TERMINAL_NO_RETRY",
        }
    )
    with pytest.raises(live.PhaseALiveError, match="pre-header-completion"):
        live._validate_endpoint_evidence(  # noqa: SLF001
            endpoint,
            bundle=success_run["bundle"],
            terminal_success=False,
        )


def test_failed_http_envelope_gate_rejects_impossible_large_prefix(
    success_run: dict[str, Any],
) -> None:
    endpoint = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    raw_headers = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n"
        b"Connection: close\r\n\r\n"
    )
    prefix = raw_headers + (
        b"x" * (live.MAX_STATUS_HEADER_BYTES + 2 - len(raw_headers))
    )
    endpoint.update(
        {
            "last_completed_gate": "STATUS_HEADERS_RECEIVED",
            "failure_stage": "HTTP_ENVELOPE_VALIDATION",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
            "observed_response_octets_total": len(prefix),
            "bounded_response_prefix_bytes": len(prefix),
            "bounded_response_prefix_sha256": contract.sha256(prefix),
            "bounded_response_prefix_base64": base64.b64encode(prefix).decode("ascii"),
            "raw_status_and_header_bytes": len(raw_headers),
            "raw_status_and_header_sha256": contract.sha256(raw_headers),
            "raw_status_and_header_base64": base64.b64encode(raw_headers).decode(
                "ascii"
            ),
            "validation_outcome": "FAILED_TERMINAL_NO_RETRY",
        }
    )
    with pytest.raises(live.PhaseALiveError, match="reachable parser read"):
        live._validate_endpoint_evidence(  # noqa: SLF001
            endpoint,
            bundle=success_run["bundle"],
            terminal_success=False,
        )


def test_raw_header_bundle_is_exactly_bound_to_status_headers_received_gate(
    success_run: dict[str, Any],
) -> None:
    missing = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    missing.update(
        {
            "last_completed_gate": "STATUS_HEADERS_RECEIVED",
            "failure_stage": "HTTP_ENVELOPE_VALIDATION",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
            "validation_outcome": "FAILED_TERMINAL_NO_RETRY",
        }
    )
    with pytest.raises(live.PhaseALiveError, match="lacks raw status/header"):
        live._validate_endpoint_evidence(  # noqa: SLF001
            missing,
            bundle=success_run["bundle"],
            terminal_success=False,
        )

    present = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    raw_headers = b"INVALID\r\n\r\n"
    present.update(
        {
            "last_completed_gate": "REQUEST_WRITE_COMPLETED",
            "failure_stage": "RESPONSE_STATUS_HEADER_READ",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
            "observed_response_octets_total": len(raw_headers),
            "bounded_response_prefix_bytes": len(raw_headers),
            "bounded_response_prefix_sha256": contract.sha256(raw_headers),
            "bounded_response_prefix_base64": base64.b64encode(raw_headers).decode(
                "ascii"
            ),
            "raw_status_and_header_bytes": len(raw_headers),
            "raw_status_and_header_sha256": contract.sha256(raw_headers),
            "raw_status_and_header_base64": base64.b64encode(raw_headers).decode(
                "ascii"
            ),
            "validation_outcome": "FAILED_TERMINAL_NO_RETRY",
        }
    )
    with pytest.raises(live.PhaseALiveError, match="before its receive gate"):
        live._validate_endpoint_evidence(  # noqa: SLF001
            present,
            bundle=success_run["bundle"],
            terminal_success=False,
        )

    embedded = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    impossible_raw = b"HTTP/1.1 200 OK\r\nX: x\r\n\r\nY: y\r\n\r\n"
    embedded.update(
        {
            "last_completed_gate": "STATUS_HEADERS_RECEIVED",
            "failure_stage": "HTTP_ENVELOPE_VALIDATION",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
            "observed_response_octets_total": len(impossible_raw),
            "bounded_response_prefix_bytes": len(impossible_raw),
            "bounded_response_prefix_sha256": contract.sha256(impossible_raw),
            "bounded_response_prefix_base64": base64.b64encode(impossible_raw).decode(
                "ascii"
            ),
            "raw_status_and_header_bytes": len(impossible_raw),
            "raw_status_and_header_sha256": contract.sha256(impossible_raw),
            "raw_status_and_header_base64": base64.b64encode(impossible_raw).decode(
                "ascii"
            ),
            "validation_outcome": "FAILED_TERMINAL_NO_RETRY",
        }
    )
    with pytest.raises(live.PhaseALiveError, match="first delimiter"):
        live._validate_endpoint_evidence(  # noqa: SLF001
            embedded,
            bundle=success_run["bundle"],
            terminal_success=False,
        )

    too_short = deepcopy(embedded)
    impossible_short_raw = b"abc"
    too_short.update(
        {
            "observed_response_octets_total": len(impossible_short_raw),
            "bounded_response_prefix_bytes": len(impossible_short_raw),
            "bounded_response_prefix_sha256": contract.sha256(impossible_short_raw),
            "bounded_response_prefix_base64": base64.b64encode(
                impossible_short_raw
            ).decode("ascii"),
            "raw_status_and_header_bytes": len(impossible_short_raw),
            "raw_status_and_header_sha256": contract.sha256(impossible_short_raw),
            "raw_status_and_header_base64": base64.b64encode(
                impossible_short_raw
            ).decode("ascii"),
        }
    )
    with pytest.raises(live.PhaseALiveError, match="first delimiter"):
        live._validate_endpoint_evidence(  # noqa: SLF001
            too_short,
            bundle=success_run["bundle"],
            terminal_success=False,
        )


@pytest.mark.parametrize(
    ("partial", "beyond", "message"),
    (
        (b"xxx", b"", "exceeds"),
        (b"x", b"!", "complete Content-Length"),
    ),
)
def test_rank7_rejects_unreachable_partial_and_overlong_body_bundles(
    success_run: dict[str, Any],
    partial: bytes,
    beyond: bytes,
    message: str,
) -> None:
    endpoint = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    raw_headers = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        b"Content-Length: 2\r\nConnection: close\r\n\r\n"
    )
    prefix = raw_headers + partial + beyond
    endpoint.update(
        {
            "last_completed_gate": "HTTP_ENVELOPE_VALIDATED",
            "failure_stage": "RESPONSE_ENTITY_READ_OR_CONNECTION_CLOSE",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
            "observed_response_octets_total": len(prefix),
            "bounded_response_prefix_bytes": len(prefix),
            "bounded_response_prefix_sha256": contract.sha256(prefix),
            "bounded_response_prefix_base64": base64.b64encode(prefix).decode("ascii"),
            "raw_status_and_header_bytes": len(raw_headers),
            "raw_status_and_header_sha256": contract.sha256(raw_headers),
            "raw_status_and_header_base64": base64.b64encode(raw_headers).decode(
                "ascii"
            ),
            "http_status": 200,
            "response_headers": [
                ["Content-Type", "application/json"],
                ["Content-Length", "2"],
                ["Connection", "close"],
            ],
            "partial_response_entity_bytes": len(partial),
            "partial_response_entity_sha256": contract.sha256(partial),
            "partial_response_entity_base64": base64.b64encode(partial).decode("ascii"),
            "beyond_content_length_bytes": len(beyond),
            "beyond_content_length_sha256": (
                contract.sha256(beyond) if beyond else None
            ),
            "beyond_content_length_base64": (
                base64.b64encode(beyond).decode("ascii") if beyond else None
            ),
            "validation_outcome": "FAILED_TERMINAL_NO_RETRY",
        }
    )
    with pytest.raises(live.PhaseALiveError, match=message):
        live._validate_endpoint_evidence(  # noqa: SLF001
            endpoint,
            bundle=success_run["bundle"],
            terminal_success=False,
        )


class _NoNetworkFakeSocket:
    def __init__(
        self,
        response_chunks: tuple[bytes, ...],
        *,
        send_chunk: int = 7,
        connect_error: BaseException | None = None,
        send_error_after_calls: int | None = None,
        recv_error_after_calls: int | None = None,
    ) -> None:
        self.response_chunks = list(response_chunks)
        self.send_chunk = send_chunk
        self.connect_error = connect_error
        self.send_error_after_calls = send_error_after_calls
        self.recv_error_after_calls = recv_error_after_calls
        self.constructor_args: tuple[Any, ...] | None = None
        self.connect_calls: list[tuple[str, int]] = []
        self.sent = bytearray()
        self.send_calls = 0
        self.recv_calls = 0
        self.timeouts: list[float] = []
        self.closed = False

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def connect(self, peer: tuple[str, int]) -> None:
        self.connect_calls.append(peer)
        if self.connect_error is not None:
            raise self.connect_error

    def send(self, value: memoryview) -> int:
        self.send_calls += 1
        if (
            self.send_error_after_calls is not None
            and self.send_calls > self.send_error_after_calls
        ):
            raise BrokenPipeError("synthetic broken pipe")
        count = min(self.send_chunk, len(value))
        self.sent.extend(bytes(value[:count]))
        return count

    def recv(self, maximum: int) -> bytes:
        self.recv_calls += 1
        if (
            self.recv_error_after_calls is not None
            and self.recv_calls > self.recv_error_after_calls
        ):
            raise TimeoutError("synthetic receive timeout/reset")
        if not self.response_chunks:
            return b""
        chunk = self.response_chunks.pop(0)
        if len(chunk) > maximum:
            self.response_chunks.insert(0, chunk[maximum:])
            return chunk[:maximum]
        return chunk

    def close(self) -> None:
        self.closed = True


def test_production_raw_transport_uses_one_literal_af_inet_socket_and_exact_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"{}"
    raw = _http_response(body)
    fake = _NoNetworkFakeSocket(tuple(bytes((item,)) for item in raw))
    constructor_calls: list[tuple[Any, ...]] = []

    def fake_constructor(*args: Any) -> _NoNetworkFakeSocket:
        constructor_calls.append(args)
        fake.constructor_args = args
        return fake

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("DNS/helper routing must not be called")

    monkeypatch.setattr(live.socket, "socket", fake_constructor)
    monkeypatch.setattr(live.socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(live.socket, "create_connection", forbidden)
    monkeypatch.setenv("HTTP_PROXY", "http://malicious.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://malicious.invalid:8080")
    endpoint = live._new_endpoint(synthetic_test_only=False)  # noqa: SLF001
    response = live._RawIPv4SingleVersionTransport().perform(  # noqa: SLF001
        endpoint=endpoint,
        clock=live._SystemUTCClock(),  # noqa: SLF001
    )
    live._finalize_bounded_response_evidence(endpoint)  # noqa: SLF001

    assert constructor_calls == [
        (live.socket.AF_INET, live.socket.SOCK_STREAM, live.socket.IPPROTO_TCP)
    ]
    assert fake.connect_calls == [("192.168.1.7", 80)]
    assert bytes(fake.sent) == live.REQUEST_WIRE_BYTES
    assert fake.send_calls > 1
    assert fake.closed is True
    assert response.entity_body == body
    assert endpoint["request_wire_emitted"] == "UNKNOWN"
    assert endpoint["peer_received_request"] == "UNKNOWN"
    assert endpoint["application_transport_attempts"] == 1
    assert endpoint["request_bytes_handed_to_socket_api"] == len(
        live.REQUEST_WIRE_BYTES
    )


@pytest.mark.parametrize(
    "stage",
    (
        "constructor",
        "connect",
        "partial-send",
        "header-eof",
        "body-timeout",
        "close-timeout",
    ),
)
def test_production_raw_transport_closes_and_preserves_stage_evidence(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    body = b"{}"
    chunks = (b"HTTP/1.1 200",)
    if stage == "body-timeout":
        chunks = (_http_response(body)[:-1],)
    elif stage == "close-timeout":
        chunks = (_http_response(body),)
    fake = _NoNetworkFakeSocket(
        chunks,
        connect_error=(
            ConnectionRefusedError("refused") if stage == "connect" else None
        ),
        send_error_after_calls=(1 if stage == "partial-send" else None),
        recv_error_after_calls=(
            1 if stage in {"body-timeout", "close-timeout"} else None
        ),
    )

    def constructor(*_args: Any) -> _NoNetworkFakeSocket:
        if stage == "constructor":
            raise OSError("constructor failed")
        return fake

    monkeypatch.setattr(live.socket, "socket", constructor)
    endpoint = live._new_endpoint(synthetic_test_only=False)  # noqa: SLF001
    with pytest.raises((OSError, live.PhaseALiveTransportError)):
        live._RawIPv4SingleVersionTransport().perform(  # noqa: SLF001
            endpoint=endpoint,
            clock=live._SystemUTCClock(),  # noqa: SLF001
        )
    live._finalize_bounded_response_evidence(endpoint)  # noqa: SLF001
    assert endpoint["application_transport_attempts"] == 1
    assert endpoint["request_wire_emitted"] == "UNKNOWN"
    assert endpoint["peer_received_request"] == "UNKNOWN"
    if stage != "constructor":
        assert fake.closed is True
    if stage == "partial-send":
        assert (
            0
            < endpoint["request_bytes_handed_to_socket_api"]
            < len(live.REQUEST_WIRE_BYTES)
        )
        assert endpoint["request_write_completed"] is False
    if stage == "header-eof":
        assert (
            base64.b64decode(endpoint["bounded_response_prefix_base64"], validate=True)
            == b"HTTP/1.1 200"
        )
    if stage == "body-timeout":
        assert endpoint["last_completed_gate"] == "HTTP_ENVELOPE_VALIDATED"
        assert endpoint["partial_response_entity_bytes"] == 1
    if stage == "close-timeout":
        assert endpoint["last_completed_gate"] == "HTTP_ENVELOPE_VALIDATED"
        assert endpoint["partial_response_entity_bytes"] == len(body)


def test_public_production_executor_uses_fixed_socket_and_seals_connect_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = phase_a.materialize_phase_a_authority(
        **_offline_authority_kwargs(tmp_path)
    )
    authority_path = Path(authority["authority_file"])
    authority_path.write_bytes(contract.canonical_json_bytes(authority) + b"\n")
    envelope_path = tmp_path / "production-live-envelope.json"
    envelope = live.materialize_live_execution_envelope(
        phase_a_authority_file=authority_path,
        live_envelope_file=envelope_path,
        built_at="2026-08-15T14:01:30Z",
    )
    live.write_new_live_execution_envelope(envelope_path, envelope)
    token = live._authorization_phrase(  # noqa: SLF001
        envelope,
        envelope_file_sha256=contract.sha256(envelope_path.read_bytes()),
    )
    fake = _NoNetworkFakeSocket(
        (), connect_error=ConnectionRefusedError("synthetic refused")
    )

    def constructor(*args: Any) -> _NoNetworkFakeSocket:
        fake.constructor_args = args
        return fake

    def fixed_wall_now(_self: Any) -> datetime:
        return NOW

    monkeypatch.setattr(live.socket, "socket", constructor)
    monkeypatch.setattr(live._SystemUTCClock, "wall_now", fixed_wall_now)  # noqa: SLF001
    receipt = live.execute_phase_a_live_once(
        envelope_path,
        authorization=token,
    )
    assert receipt["state"] == "TERMINAL_FAILURE_NO_RETRY"
    assert receipt["kind"] == live.LIVE_RECEIPT_KIND
    assert receipt["application_transport_attempts"] == 1
    assert receipt["fully_written_version_gets"] == 0
    assert receipt["version_protocol_response_conformance"] is False
    assert fake.constructor_args == (
        live.socket.AF_INET,
        live.socket.SOCK_STREAM,
        live.socket.IPPROTO_TCP,
    )
    assert fake.connect_calls == [("192.168.1.7", 80)]
    assert fake.closed is True
    summary = live.validate_phase_a_live_terminal_receipt(
        Path(envelope["attempt"]["terminal_receipt_file"]),
        live_envelope_file=envelope_path,
        require_success=False,
    )
    assert summary["terminal_outcome_committed"] is True
    assert summary["may_request_separate_phase_b_authority"] is False


def test_success_is_synthetic_conformance_only_and_permanently_consumed(
    success_run: dict[str, Any],
) -> None:
    receipt = success_run["receipt"]
    endpoint = receipt["endpoint_outcomes"][0]
    assert receipt["state"] == "TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE"
    assert receipt["kind"] == live.SYNTHETIC_RECEIPT_KIND
    assert receipt["version_protocol_response_conformance"] is True
    assert receipt["responder_or_device_identity_proven"] is False
    assert receipt["trusted_ip_binding_proven"] is False
    assert receipt["fresh_post_reset_application_boot_proven"] is False
    assert receipt["active_application_or_ota_slot_proven"] is False
    assert receipt["phase_b_authority_generated"] is False
    assert receipt["eligible_for_direct_phase_b_execution"] is False
    assert receipt["synthetic_receipt_never_phase_b_eligible"] is True
    assert receipt["fully_written_version_gets"] == 1
    assert endpoint["last_completed_gate"] == "EXACT_V10_VALIDATED"
    assert endpoint["request_wire_emitted"] == "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY"
    assert success_run["transport"].calls == 1
    assert success_run["registry_path"].exists()
    assert success_run["receipt_path"].stat().st_size < live.MAX_TERMINAL_RECEIPT_BYTES
    assert not Path(
        success_run["envelope"]["attempt"]["finalization_temp_file"]
    ).exists()
    assert not Path(
        success_run["envelope"]["attempt"]["original_plan_final_output"]
    ).exists()

    validated = live._validate_terminal_receipt_file(  # noqa: SLF001
        success_run["receipt_path"],
        bundle=success_run["bundle"],
        require_success=True,
        registry_file=success_run["registry_path"],
    )
    assert validated["terminal_success"] is True
    assert validated["terminal_outcome_committed"] is True
    assert validated["may_request_separate_phase_b_authority"] is False

    second = live._BuiltInScriptedTestTransport(  # noqa: SLF001
        response_chunks=(success_run["raw"],)
    )
    with pytest.raises(live.PhaseALiveError, match="registry exists"):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            success_run["envelope_path"],
            authorization=success_run["token"],
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=second,
            _preloaded_bundle=success_run["bundle"],
        )
    assert second.calls == 0

    finalization_temp_path = Path(
        success_run["envelope"]["attempt"]["finalization_temp_file"]
    )
    finalization_temp_path.write_bytes(b"foreign-surviving-temp-entry")
    try:
        with pytest.raises(live.PhaseALiveError, match="surviving finalization temp"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                success_run["receipt_path"],
                bundle=success_run["bundle"],
                require_success=True,
                registry_file=success_run["registry_path"],
            )
    finally:
        finalization_temp_path.unlink()


def test_wrong_expired_and_preexisting_output_are_zero_attempt(
    tmp_path: Path, offline_authority_file: Path
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="preflight-collision"
    )
    transport = live._BuiltInScriptedTestTransport(transport_error="must not run")  # noqa: SLF001
    registry_path = Path(envelope["attempt"]["registry_file"])
    output_path = Path(envelope["attempt"]["terminal_receipt_file"])

    with pytest.raises(live.PhaseALiveError, match="authorization differs"):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=f"{token}X",
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=transport,
            _preloaded_bundle=bundle,
        )
    assert transport.calls == 0
    assert not registry_path.exists()
    assert not output_path.exists()

    expired = datetime(2026, 8, 15, 14, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(live.PhaseALiveError, match="outside"):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            now="2026-08-15T14:10:00Z",
            clock=live._ScriptedUTCClock((expired, expired)),  # noqa: SLF001
            transport=transport,
            _preloaded_bundle=bundle,
        )
    assert transport.calls == 0
    assert not registry_path.exists()

    output_path.write_bytes(b"preexisting-output")
    with pytest.raises(
        live.PhaseALiveError, match="output already exists before registry"
    ):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=transport,
            _preloaded_bundle=bundle,
        )
    assert not registry_path.exists()
    assert output_path.read_bytes() == b"preexisting-output"
    assert transport.calls == 0


def test_output_race_after_registry_permanently_consumes_without_transport(
    tmp_path: Path,
    offline_authority_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="post-registry-output-race"
    )
    registry_path = Path(envelope["attempt"]["registry_file"])
    output_path = Path(envelope["attempt"]["terminal_receipt_file"])
    original_reserve = live._reserve_empty_sink  # noqa: SLF001

    def collide(path: Path, *, label: str) -> tuple[Any, dict[str, int]]:
        if path == output_path:
            path.write_bytes(b"post-registry-race")
        return original_reserve(path, label=label)

    monkeypatch.setattr(live, "_reserve_empty_sink", collide)  # noqa: SLF001
    transport = live._BuiltInScriptedTestTransport(transport_error="must not run")  # noqa: SLF001
    with pytest.raises(live.PhaseALiveError, match="already exists; no retry"):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=transport,
            _preloaded_bundle=bundle,
        )
    assert registry_path.exists()
    assert output_path.read_bytes() == b"post-registry-race"
    assert transport.calls == 0
    registry_summary = live._validate_registry_file(  # noqa: SLF001
        registry_path, bundle=bundle
    )
    assert registry_summary[2]["creation_identity"]["st_nlink"] == 1


def test_expiry_crossed_after_checkpoint_is_terminal_and_zero_transport(
    tmp_path: Path, offline_authority_file: Path
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="pre-connect-expiry"
    )
    expired = datetime(2026, 8, 15, 14, 10, 0, tzinfo=timezone.utc)
    transport = live._BuiltInScriptedTestTransport(transport_error="must not run")  # noqa: SLF001
    receipt = live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
        envelope_path,
        authorization=token,
        now=NOW_TEXT,
        clock=live._ScriptedUTCClock((NOW, expired)),  # noqa: SLF001
        transport=transport,
        _preloaded_bundle=bundle,
    )
    endpoint = receipt["endpoint_outcomes"][0]
    assert receipt["state"] == "TERMINAL_FAILURE_NO_RETRY"
    assert endpoint["last_completed_gate"] == "ATTEMPT_CHECKPOINT_PERSISTED"
    assert endpoint["application_transport_attempts"] == 0
    assert receipt["pre_connect_host_now_utc"] is None
    assert transport.calls == 0
    assert Path(envelope["attempt"]["registry_file"]).exists()


def test_post_checkpoint_verification_failure_leaves_strict_indeterminate_no_retry(
    tmp_path: Path,
    offline_authority_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="checkpoint-write-fail"
    )
    original_assert = live._assert_sink_exact  # noqa: SLF001

    def fail_after_exact_write(sink: Any, payload: bytes, *, label: str) -> str:
        result = original_assert(sink, payload, label=label)
        if label == "persisted attempt checkpoint":
            raise live.PhaseALiveError("checkpoint verification failed")
        return result

    monkeypatch.setattr(live, "_assert_sink_exact", fail_after_exact_write)  # noqa: SLF001
    transport = live._BuiltInScriptedTestTransport(transport_error="must not run")  # noqa: SLF001
    with pytest.raises(live.PhaseALiveError, match="checkpoint verification failed"):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=transport,
            _preloaded_bundle=bundle,
        )
    assert transport.calls == 0
    registry_path = Path(envelope["attempt"]["registry_file"])
    receipt_path = Path(envelope["attempt"]["terminal_receipt_file"])
    assert registry_path.exists() and receipt_path.exists()
    summary = live._validate_indeterminate_checkpoint_file(  # noqa: SLF001
        receipt_path,
        bundle=bundle,
        registry_file=registry_path,
    )
    assert summary["attempt_permanently_consumed"] is True
    assert summary["phase_b_eligible"] is False


def test_same_inode_checkpoint_mutation_at_final_preconnect_gate_blocks_transport(
    tmp_path: Path,
    offline_authority_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="preconnect-byte-mutation"
    )
    output_path = Path(envelope["attempt"]["terminal_receipt_file"])
    original_time_check = live._check_execution_time  # noqa: SLF001

    def mutate_after_time_check(*args: Any, **kwargs: Any) -> tuple[str, str]:
        result = original_time_check(*args, **kwargs)
        if kwargs["label"] == "pre-connect":
            output_path.write_bytes(b"same-inode-corruption")
        return result

    monkeypatch.setattr(live, "_check_execution_time", mutate_after_time_check)  # noqa: SLF001
    transport = live._BuiltInScriptedTestTransport(transport_error="must not run")  # noqa: SLF001
    with pytest.raises(live.PhaseALiveError):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=transport,
            _preloaded_bundle=bundle,
        )
    assert transport.calls == 0
    assert Path(envelope["attempt"]["registry_file"]).exists()
    assert not Path(envelope["attempt"]["finalization_temp_file"]).exists()


def test_keyboard_interrupt_after_request_preserves_checkpoint_then_reraises(
    tmp_path: Path,
    offline_authority_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="keyboard-interrupt"
    )

    def interrupt(
        self: live._BuiltInScriptedTestTransport,  # noqa: SLF001
        *,
        endpoint: dict[str, Any],
        clock: Any,
    ) -> Any:
        del clock
        self.calls += 1
        endpoint["application_transport_attempts"] = 1
        endpoint["request_write_called"] = True
        endpoint["request_write_completed"] = True
        endpoint["request_bytes_handed_to_socket_api"] = len(live.REQUEST_WIRE_BYTES)
        endpoint["last_completed_gate"] = "REQUEST_WRITE_COMPLETED"
        raise KeyboardInterrupt()

    monkeypatch.setattr(live._BuiltInScriptedTestTransport, "perform", interrupt)  # noqa: SLF001
    transport = live._BuiltInScriptedTestTransport(response_chunks=())  # noqa: SLF001
    with pytest.raises(KeyboardInterrupt):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=transport,
            _preloaded_bundle=bundle,
        )
    receipt_path = Path(envelope["attempt"]["terminal_receipt_file"])
    summary = live._validate_indeterminate_checkpoint_file(  # noqa: SLF001
        receipt_path,
        bundle=bundle,
        registry_file=Path(envelope["attempt"]["registry_file"]),
    )
    assert summary["terminal_success"] is False
    assert summary["network_outcome"] == "UNKNOWN_OR_NOT_STARTED"
    assert transport.calls == 1
    copied = receipt_path.with_name("copied-checkpoint.json")
    copied.write_bytes(receipt_path.read_bytes())
    with pytest.raises(live.PhaseALiveError, match="checkpoint path differs"):
        live._validate_indeterminate_checkpoint_file(  # noqa: SLF001
            copied,
            bundle=bundle,
            registry_file=Path(envelope["attempt"]["registry_file"]),
        )


def test_atomic_replace_failure_leaves_checkpoint_and_auditable_uncommitted_temp(
    tmp_path: Path,
    offline_authority_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="atomic-replace-fail"
    )
    body = _version_body(bundle.v10_context)
    output_path = Path(envelope["attempt"]["terminal_receipt_file"])
    temp_path = Path(envelope["attempt"]["finalization_temp_file"])
    original_replace = live.os.replace

    def fail_exact_atomic_replace(source: Any, destination: Any) -> None:
        if Path(source) == temp_path and Path(destination) == output_path:
            raise OSError("synthetic atomic replace failure")
        original_replace(source, destination)

    monkeypatch.setattr(live.os, "replace", fail_exact_atomic_replace)
    with pytest.raises(OSError, match="synthetic atomic replace failure"):
        live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
            envelope_path,
            authorization=token,
            now=NOW_TEXT,
            clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
            transport=live._BuiltInScriptedTestTransport(  # noqa: SLF001
                response_chunks=(_http_response(body),)
            ),
            _preloaded_bundle=bundle,
        )
    assert output_path.exists() and temp_path.exists()
    checkpoint = live._validate_indeterminate_checkpoint_file(  # noqa: SLF001
        output_path,
        bundle=bundle,
        registry_file=Path(envelope["attempt"]["registry_file"]),
    )
    assert checkpoint["phase_b_eligible"] is False
    prepared = live._validate_terminal_receipt_file(  # noqa: SLF001
        temp_path,
        bundle=bundle,
        require_success=True,
        registry_file=Path(envelope["attempt"]["registry_file"]),
        evidence_location="UNCOMMITTED_FINALIZATION_TEMP",
    )
    assert prepared["terminal_outcome_committed"] is False
    assert prepared["may_request_separate_phase_b_authority"] is False


def test_success_receipt_rejects_orphan_and_false_failure_tampering(
    success_run: dict[str, Any],
) -> None:
    path = success_run["receipt_path"]
    original = path.read_bytes()
    try:
        path.write_bytes(b" " + original)
        with pytest.raises(live.PhaseALiveError, match="canonical JSON"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        noncanonical_time = deepcopy(success_run["receipt"])
        noncanonical_time.pop("integrity")
        noncanonical_time["pre_connect_host_now_utc"] = "2026-08-15T22:02:00+08:00"
        path.write_bytes(
            contract.canonical_json_bytes(live._seal(noncanonical_time))  # noqa: SLF001
            + b"\n"
        )
        with pytest.raises(live.PhaseALiveError, match="UTC Z form"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        root_bool_alias = deepcopy(success_run["receipt"])
        root_bool_alias.pop("integrity")
        root_bool_alias["schema_version"] = True
        path.write_bytes(
            contract.canonical_json_bytes(live._seal(root_bool_alias)) + b"\n"  # noqa: SLF001
        )
        with pytest.raises(live.PhaseALiveError, match="schema_version differs"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        endpoint_bool_alias = deepcopy(success_run["receipt"])
        endpoint_bool_alias.pop("integrity")
        endpoint_bool_alias["endpoint_outcomes"][0]["ordinal"] = True
        path.write_bytes(
            contract.canonical_json_bytes(live._seal(endpoint_bool_alias)) + b"\n"  # noqa: SLF001
        )
        with pytest.raises(live.PhaseALiveError, match="endpoint ordinal differs"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        tampered = deepcopy(success_run["receipt"])
        tampered.pop("integrity")
        endpoint = tampered["endpoint_outcomes"][0]
        endpoint["bounded_response_prefix_sha256"] = None
        path.write_bytes(contract.canonical_json_bytes(live._seal(tampered)) + b"\n")  # noqa: SLF001
        with pytest.raises(live.PhaseALiveError, match="bundle type|orphan"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        bool_length = deepcopy(success_run["receipt"])
        bool_length.pop("integrity")
        bool_length["endpoint_outcomes"][0]["beyond_content_length_bytes"] = False
        path.write_bytes(
            contract.canonical_json_bytes(live._seal(bool_length)) + b"\n"  # noqa: SLF001
        )
        with pytest.raises(live.PhaseALiveError, match="byte length type"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        checkpoint_binding = deepcopy(success_run["receipt"])
        checkpoint_binding.pop("integrity")
        checkpoint_binding["output_checkpoint_whole_file_sha256"] = "1" * 64
        path.write_bytes(
            contract.canonical_json_bytes(live._seal(checkpoint_binding)) + b"\n"  # noqa: SLF001
        )
        with pytest.raises(
            live.PhaseALiveError, match="unique reconstructed checkpoint"
        ):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        identity_collision = deepcopy(success_run["receipt"])
        identity_collision.pop("integrity")
        collided_identity = deepcopy(identity_collision["registry_creation_identity"])
        reconstructed = live._checkpoint_receipt(  # noqa: SLF001
            success_run["bundle"],
            authorization_sha256=identity_collision["authorization_phrase_sha256"],
            registry_file=success_run["registry_path"],
            registry_canonical_sha256=identity_collision[
                "registry_initial_canonical_sha256"
            ],
            registry_whole_file_sha256=identity_collision["registry_whole_file_sha256"],
            registry_creation_identity=identity_collision["registry_creation_identity"],
            registry_parent_fsync=identity_collision[
                "registry_parent_directory_fsync_status"
            ],
            output_parent_fsync=identity_collision[
                "output_parent_directory_fsync_status"
            ],
            output_checkpoint_creation_identity=collided_identity,
            execution_observed_now_utc=identity_collision["execution_observed_now_utc"],
            pre_registry_host_now_utc=identity_collision["pre_registry_host_now_utc"],
            endpoint=live._new_endpoint(synthetic_test_only=True),  # noqa: SLF001
            state=(
                "TERMINAL_INDETERMINATE_ATTEMPT_CHECKPOINT_PERSISTED_"
                "NETWORK_OUTCOME_MAY_BECOME_UNKNOWN_NO_RETRY"
            ),
        )
        reconstructed_payload = contract.canonical_json_bytes(reconstructed) + b"\n"
        identity_collision["output_checkpoint_creation_identity"] = collided_identity
        identity_collision["output_checkpoint_whole_file_bytes"] = len(
            reconstructed_payload
        )
        identity_collision["output_checkpoint_whole_file_sha256"] = contract.sha256(
            reconstructed_payload
        )
        identity_collision["output_checkpoint_canonical_sha256"] = reconstructed[
            "integrity"
        ]["canonical_sha256"]
        path.write_bytes(
            contract.canonical_json_bytes(live._seal(identity_collision))  # noqa: SLF001
            + b"\n"
        )
        with pytest.raises(live.PhaseALiveError, match="pairwise distinct"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )

        false_failure = deepcopy(success_run["receipt"])
        false_failure.pop("integrity")
        false_failure["state"] = "TERMINAL_FAILURE_NO_RETRY"
        false_failure["version_protocol_response_conformance"] = False
        false_failure["may_request_separate_phase_b_authority"] = False
        false_failure["error_type"] = "PhaseALiveError"
        false_failure["error"] = "false failure"
        endpoint = false_failure["endpoint_outcomes"][0]
        endpoint["validation_outcome"] = "FAILED_TERMINAL_NO_RETRY"
        endpoint["failure_stage"] = "POST_VALIDATION_EVIDENCE"
        path.write_bytes(
            contract.canonical_json_bytes(live._seal(false_failure)) + b"\n"  # noqa: SLF001
        )
        with pytest.raises(live.PhaseALiveError, match="relabeled failure"):
            live._validate_terminal_receipt_file(  # noqa: SLF001
                path,
                bundle=success_run["bundle"],
                require_success=None,
                registry_file=success_run["registry_path"],
            )
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize(
    ("tag", "raw_factory", "match_gate"),
    (
        (
            "bad-header",
            lambda body: _http_response(body, headers=(b"Transfer-Encoding: chunked",)),
            "STATUS_HEADERS_RECEIVED",
        ),
        (
            "overlong",
            lambda body: _http_response(body, append=b"X"),
            "HTTP_ENVELOPE_VALIDATED",
        ),
    ),
)
def test_http_failures_roundtrip_with_bounded_lossless_evidence(
    tmp_path: Path,
    offline_authority_file: Path,
    tag: str,
    raw_factory: Any,
    match_gate: str,
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag=tag
    )
    body = _version_body(bundle.v10_context)
    raw = raw_factory(body)
    receipt = live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
        envelope_path,
        authorization=token,
        now=NOW_TEXT,
        clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
        transport=live._BuiltInScriptedTestTransport(response_chunks=(raw,)),  # noqa: SLF001
        _preloaded_bundle=bundle,
    )
    endpoint = receipt["endpoint_outcomes"][0]
    assert receipt["state"] == "TERMINAL_FAILURE_NO_RETRY"
    assert endpoint["last_completed_gate"] == match_gate
    assert endpoint["validation_outcome"] == "FAILED_TERMINAL_NO_RETRY"
    prefix = base64.b64decode(endpoint["bounded_response_prefix_base64"], validate=True)
    assert prefix == raw
    if tag == "overlong":
        assert endpoint["beyond_content_length_bytes"] == 1
        assert (
            base64.b64decode(endpoint["beyond_content_length_base64"], validate=True)
            == b"X"
        )
    summary = live._validate_terminal_receipt_file(  # noqa: SLF001
        Path(envelope["attempt"]["terminal_receipt_file"]),
        bundle=bundle,
        require_success=False,
        registry_file=Path(envelope["attempt"]["registry_file"]),
    )
    assert summary["terminal_success"] is False


def test_deeply_nested_json_is_terminal_and_strictly_replayable(
    tmp_path: Path, offline_authority_file: Path
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="deep-json"
    )
    body = (b"[" * 2_000) + b"0" + (b"]" * 2_000)
    receipt = live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
        envelope_path,
        authorization=token,
        now=NOW_TEXT,
        clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
        transport=live._BuiltInScriptedTestTransport(  # noqa: SLF001
            response_chunks=(_http_response(body),)
        ),
        _preloaded_bundle=bundle,
    )
    assert receipt["state"] == "TERMINAL_FAILURE_NO_RETRY"
    assert receipt["endpoint_outcomes"][0]["last_completed_gate"] == (
        "RESPONSE_ENTITY_RECEIVED"
    )
    summary = live._validate_terminal_receipt_file(  # noqa: SLF001
        Path(envelope["attempt"]["terminal_receipt_file"]),
        bundle=bundle,
        require_success=False,
        registry_file=Path(envelope["attempt"]["registry_file"]),
    )
    assert summary["terminal_outcome_committed"] is True


def test_transport_failure_and_indeterminate_checkpoints_never_unlock_phase_b(
    tmp_path: Path, offline_authority_file: Path
) -> None:
    envelope_path, envelope, token, bundle = _make_synthetic_envelope(
        tmp_path, offline_authority_file, tag="transport"
    )
    receipt = live._execute_phase_a_synthetic_test_only(  # noqa: SLF001
        envelope_path,
        authorization=token,
        now=NOW_TEXT,
        clock=live._ScriptedUTCClock((NOW, NOW)),  # noqa: SLF001
        transport=live._BuiltInScriptedTestTransport(  # noqa: SLF001
            transport_error="测" * 5_000
        ),
        _preloaded_bundle=bundle,
    )
    endpoint = receipt["endpoint_outcomes"][0]
    assert receipt["state"] == "TERMINAL_FAILURE_NO_RETRY"
    assert endpoint["request_wire_emitted"] == "NOT_APPLICABLE_SYNTHETIC_TEST_ONLY"
    assert receipt["phase_b_authority_generated"] is False
    assert receipt["may_request_separate_phase_b_authority"] is False
    assert len(receipt["error"].encode("utf-8")) <= live.MAX_ERROR_TEXT_BYTES

    # Recreate the one complete durable checkpoint.  A crash before its full
    # write is represented only by the immutable registry and never promoted.
    sub = tmp_path / "checkpoint"
    sub.mkdir()
    env_path, env, auth, checkpoint_bundle = _make_synthetic_envelope(
        sub, offline_authority_file, tag="checkpoint"
    )
    auth_hash = contract.sha256(auth.encode("ascii"))
    pre_time = NOW_TEXT
    registry_path = Path(env["attempt"]["registry_file"])
    registry_sink, registry_root, registry_payload = live._reserve_registry_once(  # noqa: SLF001
        registry_path,
        bundle=checkpoint_bundle,
        authorization_sha256=auth_hash,
        pre_registry_host_now_utc=pre_time,
    )
    registry_fsync = registry_sink.parent_directory_fsync_status
    registry_sink.close()
    receipt_path = Path(env["attempt"]["terminal_receipt_file"])
    output_sink, output_identity = live._reserve_empty_sink(  # noqa: SLF001
        receipt_path, label="synthetic manual checkpoint"
    )
    endpoint_value = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    checkpoint = live._checkpoint_receipt(  # noqa: SLF001
        checkpoint_bundle,
        authorization_sha256=auth_hash,
        registry_file=registry_path,
        registry_canonical_sha256=registry_root["integrity"]["canonical_sha256"],
        registry_whole_file_sha256=contract.sha256(registry_payload),
        registry_creation_identity=registry_root["creation_identity"],
        registry_parent_fsync=registry_fsync,
        output_parent_fsync=output_sink.parent_directory_fsync_status,
        output_checkpoint_creation_identity=output_identity,
        execution_observed_now_utc=pre_time,
        pre_registry_host_now_utc=pre_time,
        endpoint=endpoint_value,
        state=(
            "TERMINAL_INDETERMINATE_ATTEMPT_CHECKPOINT_PERSISTED_"
            "NETWORK_OUTCOME_MAY_BECOME_UNKNOWN_NO_RETRY"
        ),
    )
    output_sink.replace(checkpoint)
    output_sink.close()
    summary = live._validate_indeterminate_checkpoint_file(  # noqa: SLF001
        receipt_path,
        bundle=checkpoint_bundle,
        registry_file=registry_path,
    )
    assert summary["terminal_success"] is False
    assert summary["phase_b_eligible"] is False
    assert summary["attempt_permanently_consumed"] is True
    assert env_path.exists()


def test_version_cap_and_exact_worst_case_receipt_fit_strict_loader(
    success_run: dict[str, Any],
) -> None:
    assert len(success_run["body"]) < live.MAX_VERSION_ENTITY_BYTES
    bundle = success_run["bundle"]
    endpoint = live._new_endpoint(synthetic_test_only=True)  # noqa: SLF001
    body = b"x" * live.MAX_VERSION_ENTITY_BYTES
    raw_headers = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
    )
    prefix = raw_headers + body
    endpoint.update(
        {
            "last_completed_gate": "EXACT_V10_VALIDATED",
            "application_transport_attempts": 1,
            "request_write_called": True,
            "request_write_completed": True,
            "request_bytes_handed_to_socket_api": len(live.REQUEST_WIRE_BYTES),
            "observed_response_octets_total": len(prefix),
            "bounded_response_prefix_bytes": len(prefix),
            "bounded_response_prefix_sha256": contract.sha256(prefix),
            "bounded_response_prefix_base64": base64.b64encode(prefix).decode("ascii"),
            "raw_status_and_header_bytes": len(raw_headers),
            "raw_status_and_header_sha256": contract.sha256(raw_headers),
            "raw_status_and_header_base64": base64.b64encode(raw_headers).decode(
                "ascii"
            ),
            "http_status": 200,
            "response_headers": [
                ["Content-Type", "application/json"],
                ["Content-Length", str(len(body))],
                ["Connection", "close"],
            ],
            "partial_response_entity_bytes": len(body),
            "partial_response_entity_sha256": contract.sha256(body),
            "partial_response_entity_base64": base64.b64encode(body).decode("ascii"),
            "response_entity_body_bytes": len(body),
            "response_entity_body_sha256": contract.sha256(body),
            "response_entity_body_base64": base64.b64encode(body).decode("ascii"),
            "strict_parsed_canonical_sha256": "0" * 64,
            "validation_outcome": "PASS",
        }
    )
    root = live._receipt_root(  # noqa: SLF001
        bundle,
        state="TERMINAL_SUCCESS_V10_PROTOCOL_RESPONSE_CONFORMANCE",
        authorization_sha256="0" * 64,
        registry_file=Path(bundle.envelope["attempt"]["registry_file"]),
        registry_canonical_sha256="0" * 64,
        registry_whole_file_sha256="0" * 64,
        registry_creation_identity={"st_dev": 0, "st_ino": 0, "st_nlink": 1},
        registry_parent_fsync="ATTEMPTED_SUCCESS_NOT_POWER_LOSS_DURABILITY_PROOF",
        output_parent_fsync="ATTEMPTED_SUCCESS_NOT_POWER_LOSS_DURABILITY_PROOF",
        output_checkpoint_creation_identity={
            "st_dev": 0,
            "st_ino": 0,
            "st_nlink": 1,
        },
        output_checkpoint_whole_file_bytes=1,
        output_checkpoint_whole_file_sha256="0" * 64,
        output_checkpoint_canonical_sha256="0" * 64,
        finalization_temp_creation_identity={
            "st_dev": 0,
            "st_ino": 0,
            "st_nlink": 1,
        },
        finalization_temp_parent_fsync=(
            "ATTEMPTED_SUCCESS_NOT_POWER_LOSS_DURABILITY_PROOF"
        ),
        execution_observed_now_utc=NOW_TEXT,
        pre_registry_host_now_utc=NOW_TEXT,
        pre_connect_host_now_utc=NOW_TEXT,
        endpoint=endpoint,
        success=True,
        error=None,
    )
    assert (
        len(contract.canonical_json_bytes(root) + b"\n")
        < live.MAX_TERMINAL_RECEIPT_BYTES
    )


def test_registry_identical_byte_replacement_does_not_preserve_creation_identity(
    success_run: dict[str, Any],
) -> None:
    registry_path = success_run["registry_path"]
    original_alias = registry_path.with_name("registry-original-identity.hold")
    replacement = registry_path.with_name("registry-identical-replacement.tmp")
    payload = registry_path.read_bytes()
    try:
        os.link(registry_path, original_alias)
    except OSError as error:
        pytest.skip(f"hard links unavailable for identity restoration: {error}")
    try:
        replacement.write_bytes(payload)
        os.replace(replacement, registry_path)
        with pytest.raises(live.PhaseALiveError, match="creation identity"):
            live._validate_registry_file(  # noqa: SLF001
                registry_path, bundle=success_run["bundle"]
            )
    finally:
        if original_alias.exists():
            os.replace(original_alias, registry_path)
        if replacement.exists():
            replacement.unlink()
