from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from tools.mf17506_stage23.relay_contract import (
    RelayCommandedState,
    RelayContractError,
    RelayIdentity,
)
from tools.mf17506_stage23 import relay_rebind as subject


PREVIOUS = RelayIdentity(
    model="ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z",
    vid="1A86",
    pid="7523",
    serial_number="ABSENT-CH340-NO-ISERIAL",
    port="COM14",
    pnp_instance_id=r"USB\VID_1A86&PID_7523\5&230B5917&0&4",
    usb_location="Port_#0004.Hub_#0001",
)
CURRENT = RelayIdentity(
    **{
        **PREVIOUS.mapping(),
        "usb_location": "Port_#0004.Hub_#0002",
    }
)
CREATED_AT = "2026-08-28T11:00:00+08:00"
QUERIED_AT = "2026-08-28T11:01:00+08:00"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> Path:
    path.write_bytes(_canonical(value) + b"\n")
    return path


def _manual() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": subject.MANUAL_DECLARATION_KIND,
        "declaration_id": "operator-relay-rebind-20260828-01",
        "declared_at": "2026-08-28T10:59:00+08:00",
        "operator_id": "operator-ye",
        "same_physical_relay_confirmed": True,
        "channel": 1,
        "contact_path": "COM1-NO1",
        "channel_1_com1_no1_wiring_confirmed": True,
        "previous_usb_location": PREVIOUS.usb_location,
        "current_usb_location": CURRENT.usb_location,
        "scope": subject.MANUAL_SCOPE,
        "on_authorized": False,
    }


def _query(identity: RelayIdentity = CURRENT) -> dict[str, Any]:
    return {
        "identity": identity.mapping(),
        "channel": 1,
        "commanded_state": "OFF",
        "electrical_state_proven": False,
        "contact_switch_performed": False,
    }


def _inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "previous_identity_file": _write_json(
            tmp_path / "previous.json", PREVIOUS.mapping()
        ),
        "discover_evidence_file": _write_json(
            tmp_path / "discover.json", [CURRENT.mapping()]
        ),
        "query_evidence_file": _write_json(tmp_path / "query.json", _query()),
        "manual_declaration_file": _write_json(tmp_path / "manual.json", _manual()),
    }


def _build(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    paths = _inputs(tmp_path)
    value = subject.build_rebind(**paths, created_at=CREATED_AT)
    return value, paths


def _publish(tmp_path: Path) -> tuple[dict[str, Any], Path, dict[str, Path]]:
    value, paths = _build(tmp_path)
    seal = tmp_path / "relay-rebind.json"
    subject.publish_rebind(seal, value)
    return value, seal, paths


def test_build_binds_only_location_change_and_all_source_bytes(tmp_path: Path) -> None:
    value, paths = _build(tmp_path)

    assert value["schema_version"] == 1
    assert value["kind"] == subject.KIND
    assert value["binding"]["previous_identity"] == PREVIOUS.mapping()
    assert value["binding"]["current_identity"] == CURRENT.mapping()
    assert value["binding"]["changed_fields"] == ["usb_location"]
    assert "usb_location" not in value["binding"]["invariant_fields"]
    assert len(value["binding"]["invariant_fields"]) == 6
    assert value["manual_declaration"] == _manual()
    assert value["authority_boundaries"] == {
        "identity_rebind_only": True,
        "operator_same_physical_relay_declaration_bound": True,
        "on_authorized": False,
        "hardware_execution_authorized": False,
        "visible_refresh_authorized": False,
        "builder_device_io_performed": False,
        "builder_relay_io_performed": False,
        "automatic_retry_allowed": False,
    }
    assert value["observed_state"] == {
        "channel": 1,
        "commanded_state": "OFF",
        "electrical_state_proven": False,
        "contact_switch_performed": False,
    }
    assert value["output_write_contract"] == "O_EXCL"

    for role, path in {
        "previous_identity": paths["previous_identity_file"],
        "discover": paths["discover_evidence_file"],
        "query": paths["query_evidence_file"],
        "manual_declaration": paths["manual_declaration_file"],
    }.items():
        raw = path.read_bytes()
        assert value["evidence"][role] == {
            "path": str(path.resolve()),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    for role, path in {
        "adapter": subject.ADAPTER_SOURCE,
        "contract": subject.CONTRACT_SOURCE,
    }.items():
        raw = path.read_bytes()
        assert (
            value["software_binding"][role]["sha256"] == hashlib.sha256(raw).hexdigest()
        )
    unsigned = {key: item for key, item in value.items() if key != "integrity"}
    assert (
        value["integrity"]["canonical_sha256"]
        == hashlib.sha256(_canonical(unsigned)).hexdigest()
    )


def test_validator_reconstructs_sources_and_returns_expected_identity(
    tmp_path: Path,
) -> None:
    value, seal, _ = _publish(tmp_path)
    validated = subject.load_and_validate_rebind(seal)
    assert validated.seal == value
    assert validated.expected_identity == CURRENT
    assert validated.seal["authority_boundaries"]["on_authorized"] is False


def test_build_and_validate_cli_publish_canonical_exclusive_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _inputs(tmp_path)
    output = tmp_path / "published.json"
    argv = [
        "build",
        "--previous-identity",
        str(paths["previous_identity_file"]),
        "--discover-evidence",
        str(paths["discover_evidence_file"]),
        "--query-evidence",
        str(paths["query_evidence_file"]),
        "--manual-declaration",
        str(paths["manual_declaration_file"]),
        "--created-at",
        CREATED_AT,
        "--output",
        str(output),
    ]
    assert subject.main(argv) == 0
    first_stdout = json.loads(capsys.readouterr().out)
    assert first_stdout["on_authorized"] is False
    assert output.read_bytes() == _canonical(json.loads(output.read_bytes())) + b"\n"

    assert subject.main(["validate", "--rebind-seal", str(output)]) == 0
    validated_stdout = json.loads(capsys.readouterr().out)
    assert validated_stdout["expected_identity"] == CURRENT.mapping()
    assert validated_stdout["on_authorized"] is False

    original = output.read_bytes()
    assert subject.main(argv) == 2
    captured = capsys.readouterr()
    assert "exclusive output already exists" in captured.err
    assert output.read_bytes() == original


@pytest.mark.parametrize(
    "field,replacement",
    (
        ("port", "COM7"),
        ("pnp_instance_id", r"USB\VID_1A86&PID_7523\DIFFERENT"),
        ("model", "OTHER-RELAY"),
    ),
)
def test_builder_rejects_any_delta_beyond_usb_location(
    tmp_path: Path, field: str, replacement: str
) -> None:
    paths = _inputs(tmp_path)
    changed = {**CURRENT.mapping(), field: replacement}
    _write_json(paths["discover_evidence_file"], [changed])
    _write_json(paths["query_evidence_file"], _query(RelayIdentity(**changed)))
    with pytest.raises(subject.RelayRebindError):
        subject.build_rebind(**paths, created_at=CREATED_AT)


def test_builder_rejects_discover_query_identity_mismatch(tmp_path: Path) -> None:
    paths = _inputs(tmp_path)
    _write_json(paths["query_evidence_file"], _query(PREVIOUS))
    with pytest.raises(subject.RelayRebindError, match="discover and query"):
        subject.build_rebind(**paths, created_at=CREATED_AT)


@pytest.mark.parametrize(
    "field,value",
    (
        ("channel", 2),
        ("commanded_state", "ON"),
        ("electrical_state_proven", True),
        ("contact_switch_performed", True),
    ),
)
def test_builder_requires_read_only_channel1_off_query(
    tmp_path: Path, field: str, value: Any
) -> None:
    paths = _inputs(tmp_path)
    query = _query()
    query[field] = value
    _write_json(paths["query_evidence_file"], query)
    with pytest.raises(subject.RelayRebindError, match="channel 1 commanded OFF"):
        subject.build_rebind(**paths, created_at=CREATED_AT)


@pytest.mark.parametrize(
    "field,value,match",
    (
        (
            "same_physical_relay_confirmed",
            False,
            "same physical relay confirmation",
        ),
        (
            "channel_1_com1_no1_wiring_confirmed",
            False,
            "wiring confirmation",
        ),
        ("contact_path", "COM1-NC1", "channel 1 COM1-NO1"),
        ("on_authorized", True, "must not authorize"),
        ("current_usb_location", "wrong", "USB locations differ"),
    ),
)
def test_builder_requires_narrow_manual_physical_declaration(
    tmp_path: Path, field: str, value: Any, match: str
) -> None:
    paths = _inputs(tmp_path)
    declaration = _manual()
    declaration[field] = value
    _write_json(paths["manual_declaration_file"], declaration)
    with pytest.raises(subject.RelayRebindError, match=match):
        subject.build_rebind(**paths, created_at=CREATED_AT)


def test_validator_rejects_tampered_seal_and_stale_source_bytes(tmp_path: Path) -> None:
    value, seal, paths = _publish(tmp_path)
    tampered = deepcopy(value)
    tampered["authority_boundaries"]["on_authorized"] = True
    with pytest.raises(subject.RelayRebindError, match="canonical integrity"):
        subject.validate_rebind(tampered)

    _write_json(paths["query_evidence_file"], {**_query(), "commanded_state": "ON"})
    with pytest.raises(subject.RelayRebindError, match="byte identity differs"):
        subject.load_and_validate_rebind(seal)


class FakeQueryRelay:
    instances: list["FakeQueryRelay"] = []
    state = RelayCommandedState.OFF
    fail_connect = False
    fail_query = False

    def __init__(
        self,
        *,
        channel: int,
        port: str | None = None,
        discovery: Any = None,
    ) -> None:
        self.channel = channel
        self.port = port
        self.discovery = discovery
        self.connected_identity: RelayIdentity | None = None
        self.query_count = 0
        self.closed = False
        self.command_call_count = 0
        self.__class__.instances.append(self)

    def discover(self) -> RelayIdentity:
        return CURRENT

    def connect(self, expected_identity: RelayIdentity) -> None:
        self.connected_identity = expected_identity
        if self.fail_connect:
            raise RelayContractError("relay identity differs from expected binding")

    def command_off(self) -> None:
        self.command_call_count += 1

    def command_on(self) -> None:
        self.command_call_count += 1

    def read_commanded_state(self) -> RelayCommandedState:
        self.query_count += 1
        if self.fail_query:
            raise RelayContractError("simulated query failure")
        return self.state

    def close(self) -> None:
        self.closed = True


def test_exact_bound_query_uses_frozen_identity_and_never_commands_contact(
    tmp_path: Path,
) -> None:
    _, seal, _ = _publish(tmp_path)
    output = tmp_path / "bound-query.json"
    FakeQueryRelay.instances.clear()
    FakeQueryRelay.state = RelayCommandedState.OFF
    FakeQueryRelay.fail_connect = False
    FakeQueryRelay.fail_query = False

    receipt = subject.exact_bound_query(
        rebind_file=seal,
        output_file=output,
        queried_at=QUERIED_AT,
        adapter_factory=FakeQueryRelay,
    )

    assert len(FakeQueryRelay.instances) == 1
    adapter = FakeQueryRelay.instances[0]
    assert adapter.channel == 1
    assert adapter.port == "COM14"
    assert adapter.connected_identity == CURRENT
    assert adapter.query_count == 1
    assert adapter.command_call_count == 0
    assert adapter.closed is True
    assert receipt["commanded_state"] == "OFF"
    assert receipt["off_gate_passed"] is True
    assert receipt["on_authorized"] is False
    assert receipt["contact_switch_performed"] is False
    assert output.read_bytes() == _canonical(receipt) + b"\n"

    with pytest.raises(subject.RelayRebindError, match="already exists"):
        subject.exact_bound_query(
            rebind_file=seal,
            output_file=output,
            queried_at=QUERIED_AT,
            adapter_factory=FakeQueryRelay,
        )


def test_exact_bound_query_seals_non_off_result_without_authorizing_on(
    tmp_path: Path,
) -> None:
    _, seal, _ = _publish(tmp_path)
    FakeQueryRelay.instances.clear()
    FakeQueryRelay.state = RelayCommandedState.ON
    FakeQueryRelay.fail_connect = False
    FakeQueryRelay.fail_query = False
    receipt = subject.exact_bound_query(
        rebind_file=seal,
        output_file=tmp_path / "on-observation.json",
        queried_at=QUERIED_AT,
        adapter_factory=FakeQueryRelay,
    )
    assert receipt["commanded_state"] == "ON"
    assert receipt["off_gate_passed"] is False
    assert receipt["on_authorized"] is False
    assert FakeQueryRelay.instances[0].command_call_count == 0


def test_exact_bound_query_fails_closed_on_identity_mismatch_without_receipt(
    tmp_path: Path,
) -> None:
    _, seal, _ = _publish(tmp_path)
    output = tmp_path / "must-not-exist.json"
    FakeQueryRelay.instances.clear()
    FakeQueryRelay.state = RelayCommandedState.OFF
    FakeQueryRelay.fail_connect = True
    FakeQueryRelay.fail_query = False
    with pytest.raises(RelayContractError, match="identity differs"):
        subject.exact_bound_query(
            rebind_file=seal,
            output_file=output,
            queried_at=QUERIED_AT,
            adapter_factory=FakeQueryRelay,
        )
    assert output.exists() is False
    assert FakeQueryRelay.instances[0].query_count == 0
    assert FakeQueryRelay.instances[0].closed is True


def test_capture_current_reserves_two_files_and_only_discovers_and_queries_once(
    tmp_path: Path,
) -> None:
    discover_output = tmp_path / "discover.json"
    query_output = tmp_path / "query.json"
    discovery_calls = 0

    def discovery() -> list[RelayIdentity]:
        nonlocal discovery_calls
        discovery_calls += 1
        return [CURRENT]

    FakeQueryRelay.instances.clear()
    FakeQueryRelay.state = RelayCommandedState.OFF
    FakeQueryRelay.fail_connect = False
    FakeQueryRelay.fail_query = False
    result = subject.capture_current(
        discover_output_file=discover_output,
        query_output_file=query_output,
        port="com14",
        discovery=discovery,
        adapter_factory=FakeQueryRelay,
    )

    assert discovery_calls == 1
    assert result["discover_call_count"] == 1
    assert result["query_call_count"] == 1
    assert result["automatic_retry_performed"] is False
    assert result["contact_switch_performed"] is False
    assert json.loads(discover_output.read_bytes()) == [CURRENT.mapping()]
    assert json.loads(query_output.read_bytes()) == _query()
    adapter = FakeQueryRelay.instances[0]
    assert adapter.channel == 1
    assert adapter.port == "COM14"
    assert adapter.connected_identity == CURRENT
    assert adapter.query_count == 1
    assert adapter.command_call_count == 0
    assert adapter.closed is True
    assert adapter.discovery() == [CURRENT]


def test_capture_current_pre_reserves_both_and_preserves_existing_output(
    tmp_path: Path,
) -> None:
    discover_output = tmp_path / "discover.json"
    query_output = tmp_path / "query.json"
    query_output.write_bytes(b"pre-existing")
    discovery_calls = 0

    def discovery() -> list[RelayIdentity]:
        nonlocal discovery_calls
        discovery_calls += 1
        return [CURRENT]

    with pytest.raises(subject.RelayRebindError, match="already exists"):
        subject.capture_current(
            discover_output_file=discover_output,
            query_output_file=query_output,
            discovery=discovery,
            adapter_factory=FakeQueryRelay,
        )
    assert discovery_calls == 0
    assert discover_output.exists() is False
    assert query_output.read_bytes() == b"pre-existing"


@pytest.mark.parametrize("identities", ([], [PREVIOUS, CURRENT]))
def test_capture_current_requires_exactly_one_and_cleans_both_reservations(
    tmp_path: Path, identities: list[RelayIdentity]
) -> None:
    discover_output = tmp_path / "discover.json"
    query_output = tmp_path / "query.json"
    calls = 0

    def discovery() -> list[RelayIdentity]:
        nonlocal calls
        calls += 1
        return identities

    with pytest.raises(subject.RelayRebindError, match="exactly one"):
        subject.capture_current(
            discover_output_file=discover_output,
            query_output_file=query_output,
            discovery=discovery,
            adapter_factory=FakeQueryRelay,
        )
    assert calls == 1
    assert discover_output.exists() is False
    assert query_output.exists() is False


def test_capture_current_query_failure_cleans_both_without_retry(
    tmp_path: Path,
) -> None:
    discover_output = tmp_path / "discover.json"
    query_output = tmp_path / "query.json"
    calls = 0

    def discovery() -> list[RelayIdentity]:
        nonlocal calls
        calls += 1
        return [CURRENT]

    FakeQueryRelay.instances.clear()
    FakeQueryRelay.state = RelayCommandedState.OFF
    FakeQueryRelay.fail_connect = False
    FakeQueryRelay.fail_query = True
    with pytest.raises(RelayContractError, match="simulated query failure"):
        subject.capture_current(
            discover_output_file=discover_output,
            query_output_file=query_output,
            discovery=discovery,
            adapter_factory=FakeQueryRelay,
        )
    assert calls == 1
    assert FakeQueryRelay.instances[0].query_count == 1
    assert FakeQueryRelay.instances[0].command_call_count == 0
    assert FakeQueryRelay.instances[0].closed is True
    assert discover_output.exists() is False
    assert query_output.exists() is False


def test_capture_current_cli_contract_has_no_contact_command() -> None:
    args = subject._parser().parse_args(  # noqa: SLF001
        [
            "capture-current",
            "--port",
            "COM14",
            "--discover-output",
            "discover.json",
            "--query-output",
            "query.json",
        ]
    )
    assert args.command == "capture-current"
    assert vars(args) == {
        "command": "capture-current",
        "port": "COM14",
        "discover_output": Path("discover.json"),
        "query_output": Path("query.json"),
    }
