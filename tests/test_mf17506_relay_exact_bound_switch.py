from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.mf17506_stage23 import relay_exact_bound_switch as subject
from tools.mf17506_stage23 import relay_rebind
from tools.mf17506_stage23.relay_contract import (
    RelayCommandedState,
    RelayContractError,
    RelayIdentity,
)


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
    **{**PREVIOUS.mapping(), "usb_location": "Port_#0004.Hub_#0002"}
)
SWITCHED_AT = "2026-08-30T20:00:00+08:00"
AUTHORITY_ID = "user-turn-20260830-automated-t2-w2"


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


def _seal(tmp_path: Path) -> Path:
    previous = _write_json(tmp_path / "previous.json", PREVIOUS.mapping())
    discover = _write_json(tmp_path / "discover.json", [CURRENT.mapping()])
    query = _write_json(
        tmp_path / "query.json",
        {
            "identity": CURRENT.mapping(),
            "channel": 1,
            "commanded_state": "OFF",
            "electrical_state_proven": False,
            "contact_switch_performed": False,
        },
    )
    manual = _write_json(
        tmp_path / "manual.json",
        {
            "schema_version": 1,
            "kind": relay_rebind.MANUAL_DECLARATION_KIND,
            "declaration_id": "operator-relay-rebind-20260828-01",
            "declared_at": "2026-08-28T10:59:00+08:00",
            "operator_id": "operator-ye",
            "same_physical_relay_confirmed": True,
            "channel": 1,
            "contact_path": "COM1-NO1",
            "channel_1_com1_no1_wiring_confirmed": True,
            "previous_usb_location": PREVIOUS.usb_location,
            "current_usb_location": CURRENT.usb_location,
            "scope": relay_rebind.MANUAL_SCOPE,
            "on_authorized": False,
        },
    )
    value = relay_rebind.build_rebind(
        previous_identity_file=previous,
        discover_evidence_file=discover,
        query_evidence_file=query,
        manual_declaration_file=manual,
        created_at="2026-08-28T11:00:00+08:00",
    )
    seal = tmp_path / "rebind.json"
    relay_rebind.publish_rebind(seal, value)
    return seal


class FakeRelay:
    instances: list["FakeRelay"] = []
    observed = RelayCommandedState.OFF
    fail_connect = False
    fail_query = False

    def __init__(self, *, channel: int, port: str | None = None) -> None:
        self.channel = channel
        self.port = port
        self.connected_identity: RelayIdentity | None = None
        self.command_on_count = 0
        self.command_off_count = 0
        self.query_count = 0
        self.closed = False
        self.__class__.instances.append(self)

    def discover(self) -> RelayIdentity:
        return CURRENT

    def connect(self, expected_identity: RelayIdentity) -> None:
        self.connected_identity = expected_identity
        if self.fail_connect:
            raise RelayContractError("simulated identity mismatch")

    def command_off(self) -> None:
        self.command_off_count += 1

    def command_on(self) -> None:
        self.command_on_count += 1

    def read_commanded_state(self) -> RelayCommandedState:
        self.query_count += 1
        if self.fail_query:
            raise RelayContractError("simulated query failure")
        return self.observed

    def close(self) -> None:
        self.closed = True


def _reset_fake(state: RelayCommandedState) -> None:
    FakeRelay.instances.clear()
    FakeRelay.observed = state
    FakeRelay.fail_connect = False
    FakeRelay.fail_query = False


@pytest.mark.parametrize(
    ("target", "observed", "on_count", "off_count"),
    (
        (RelayCommandedState.ON, RelayCommandedState.ON, 1, 0),
        (RelayCommandedState.OFF, RelayCommandedState.OFF, 0, 1),
    ),
)
def test_exact_bound_switch_uses_frozen_identity_one_command_one_query_and_receipt(
    tmp_path: Path,
    target: RelayCommandedState,
    observed: RelayCommandedState,
    on_count: int,
    off_count: int,
) -> None:
    seal = _seal(tmp_path)
    output = tmp_path / f"{target.value.lower()}-receipt.json"
    _reset_fake(observed)

    receipt = subject.exact_bound_switch(
        rebind_file=seal,
        output_file=output,
        switched_at=SWITCHED_AT,
        target=target,
        authorization_id=AUTHORITY_ID if target is RelayCommandedState.ON else None,
        current_user_authorized_on=target is RelayCommandedState.ON,
        adapter_factory=FakeRelay,
    )

    adapter = FakeRelay.instances[0]
    assert adapter.channel == 1
    assert adapter.port == "COM14"
    assert adapter.connected_identity == CURRENT
    assert adapter.command_on_count == on_count
    assert adapter.command_off_count == off_count
    assert adapter.query_count == 1
    assert adapter.closed is True
    assert receipt["target_gate_passed"] is True
    assert receipt["feedback_command_count"] == 1
    assert receipt["independent_query_count"] == 1
    assert receipt["automatic_retry_performed"] is False
    assert receipt["automatic_recovery_performed"] is False
    assert receipt["electrical_state_proven"] is False
    assert output.read_bytes() == _canonical(receipt) + b"\n"
    assert subject.validate_receipt(json.loads(output.read_bytes())) == receipt


def test_on_requires_explicit_current_user_authority_before_output_or_io(
    tmp_path: Path,
) -> None:
    seal = _seal(tmp_path)
    output = tmp_path / "must-not-exist.json"
    _reset_fake(RelayCommandedState.ON)

    with pytest.raises(subject.RelayExactBoundSwitchError, match="requires"):
        subject.exact_bound_switch(
            rebind_file=seal,
            output_file=output,
            switched_at=SWITCHED_AT,
            target=RelayCommandedState.ON,
            authorization_id=AUTHORITY_ID,
            adapter_factory=FakeRelay,
        )

    assert output.exists() is False
    assert FakeRelay.instances == []


def test_output_collision_stops_before_device_io(tmp_path: Path) -> None:
    seal = _seal(tmp_path)
    output = tmp_path / "existing.json"
    output.write_bytes(b"existing")
    _reset_fake(RelayCommandedState.OFF)

    with pytest.raises(subject.RelayExactBoundSwitchError, match="already exists"):
        subject.exact_bound_switch(
            rebind_file=seal,
            output_file=output,
            switched_at=SWITCHED_AT,
            target=RelayCommandedState.OFF,
            adapter_factory=FakeRelay,
        )

    assert FakeRelay.instances == []
    assert output.read_bytes() == b"existing"


def test_query_failure_discards_reservation_without_retry(tmp_path: Path) -> None:
    seal = _seal(tmp_path)
    output = tmp_path / "failed.json"
    _reset_fake(RelayCommandedState.ON)
    FakeRelay.fail_query = True

    with pytest.raises(RelayContractError, match="query failure"):
        subject.exact_bound_switch(
            rebind_file=seal,
            output_file=output,
            switched_at=SWITCHED_AT,
            target=RelayCommandedState.ON,
            authorization_id=AUTHORITY_ID,
            current_user_authorized_on=True,
            adapter_factory=FakeRelay,
        )

    adapter = FakeRelay.instances[0]
    assert adapter.command_on_count == 1
    assert adapter.command_off_count == 0
    assert adapter.query_count == 1
    assert adapter.closed is True
    assert output.exists() is False


def test_mismatched_query_is_sealed_and_cli_style_gate_fails(tmp_path: Path) -> None:
    seal = _seal(tmp_path)
    _reset_fake(RelayCommandedState.OFF)
    receipt = subject.exact_bound_switch(
        rebind_file=seal,
        output_file=tmp_path / "mismatch.json",
        switched_at=SWITCHED_AT,
        target=RelayCommandedState.ON,
        authorization_id=AUTHORITY_ID,
        current_user_authorized_on=True,
        adapter_factory=FakeRelay,
    )
    assert receipt["target_gate_passed"] is False
    assert receipt["off_gate_passed"] is True
    assert receipt["commanded_state"] == "OFF"


def test_parser_separates_protective_off_and_authorized_on() -> None:
    off = subject._parser().parse_args(  # noqa: SLF001
        [
            "off-bound",
            "--rebind-seal",
            "seal.json",
            "--switched-at",
            SWITCHED_AT,
            "--output",
            "off.json",
        ]
    )
    assert off.command == "off-bound"
    assert not hasattr(off, "authorization_id")

    on = subject._parser().parse_args(  # noqa: SLF001
        [
            "on-bound",
            "--rebind-seal",
            "seal.json",
            "--switched-at",
            SWITCHED_AT,
            "--output",
            "on.json",
            "--authorization-id",
            AUTHORITY_ID,
            "--confirm-current-user-authorized-on",
        ]
    )
    assert on.command == "on-bound"
    assert on.authorization_id == AUTHORITY_ID
    assert on.confirm_current_user_authorized_on is True
