from __future__ import annotations

from collections.abc import Iterable

import pytest

from tools.mf17506_stage23.relay_contract import (
    RelayCommandedState,
    RelayContractError,
    RelayIdentity,
)
from tools.mf17506_stage23.relay_zave_ch340_2ch import (
    MODEL,
    NO_USB_SERIAL,
    OP_OFF_WITH_FEEDBACK,
    OP_ON_WITH_FEEDBACK,
    OP_QUERY,
    ZaveCh340TwoChannelRelay,
    _set_state,
    command_frame,
    parse_state_frame,
)


IDENTITY = RelayIdentity(
    model=MODEL,
    vid="1A86",
    pid="7523",
    serial_number=NO_USB_SERIAL,
    port="COM14",
    pnp_instance_id=r"USB\VID_1A86&PID_7523\TEST",
    usb_location="Port_#0004.Hub_#0001",
)


class ScriptedTransport:
    def __init__(self, responses: Iterable[bytes]) -> None:
        self.responses = list(responses)
        self.requests: list[bytes] = []
        self.opened = False
        self.closed = False

    def open(self) -> None:
        self.opened = True

    def exchange(self, request: bytes, response_bytes: int) -> bytes:
        assert self.opened and not self.closed
        self.requests.append(request)
        response = self.responses.pop(0)
        assert len(response) == response_bytes
        return response

    def close(self) -> None:
        self.closed = True


def state_frame(channel: int, state: RelayCommandedState) -> bytes:
    operation = 1 if state is RelayCommandedState.ON else 0
    return command_frame(channel, operation)


def test_documented_command_frames_and_state_parser() -> None:
    assert command_frame(1, OP_QUERY) == bytes.fromhex("A0 01 05 A6")
    assert command_frame(2, OP_QUERY) == bytes.fromhex("A0 02 05 A7")
    assert command_frame(1, OP_OFF_WITH_FEEDBACK) == bytes.fromhex("A0 01 02 A3")
    assert command_frame(2, OP_ON_WITH_FEEDBACK) == bytes.fromhex("A0 02 03 A5")
    assert parse_state_frame(bytes.fromhex("A0 01 00 A1"), 1) is RelayCommandedState.OFF
    assert parse_state_frame(bytes.fromhex("A0 02 01 A3"), 2) is RelayCommandedState.ON


@pytest.mark.parametrize(
    "response",
    (
        b"",
        bytes.fromhex("A0 02 00 A2"),
        bytes.fromhex("A0 01 00 FF"),
        bytes.fromhex("A0 01 05 A6"),
    ),
)
def test_state_parser_rejects_short_wrong_identity_checksum_and_state(
    response: bytes,
) -> None:
    with pytest.raises(RelayContractError):
        parse_state_frame(response, 1)


def test_adapter_binds_identity_and_uses_feedback_commands() -> None:
    transport = ScriptedTransport(
        (
            state_frame(1, RelayCommandedState.OFF),
            state_frame(1, RelayCommandedState.ON),
            state_frame(1, RelayCommandedState.ON),
        )
    )
    adapter = ZaveCh340TwoChannelRelay(
        channel=1,
        discovery=lambda: [IDENTITY],
        transport_factory=lambda _port: transport,
    )
    assert adapter.discover() == IDENTITY
    adapter.connect(IDENTITY)
    adapter.command_off()
    adapter.command_on()
    assert adapter.read_commanded_state() is RelayCommandedState.ON
    adapter.close()
    assert transport.requests == [
        command_frame(1, OP_OFF_WITH_FEEDBACK),
        command_frame(1, OP_ON_WITH_FEEDBACK),
        command_frame(1, OP_QUERY),
    ]
    assert transport.closed is True


@pytest.mark.parametrize(
    "wanted,expected_request",
    (
        (RelayCommandedState.OFF, OP_OFF_WITH_FEEDBACK),
        (RelayCommandedState.ON, OP_ON_WITH_FEEDBACK),
    ),
)
def test_set_state_uses_one_feedback_command_then_one_query(
    wanted: RelayCommandedState, expected_request: int
) -> None:
    transport = ScriptedTransport((state_frame(1, wanted), state_frame(1, wanted)))

    def adapter_factory(_port: str) -> ScriptedTransport:
        return transport

    original = ZaveCh340TwoChannelRelay

    class BoundRelay(original):
        def __init__(self, *, channel: int, port: str | None = None) -> None:
            super().__init__(
                channel=channel,
                port=port,
                discovery=lambda: [IDENTITY],
                transport_factory=adapter_factory,
            )

    import tools.mf17506_stage23.relay_zave_ch340_2ch as subject

    saved = subject.ZaveCh340TwoChannelRelay
    subject.ZaveCh340TwoChannelRelay = BoundRelay
    try:
        result = _set_state(1, "COM14", wanted)
    finally:
        subject.ZaveCh340TwoChannelRelay = saved
    assert result["commanded_state"] == wanted.value
    assert result["feedback_command_count"] == 1
    assert result["independent_query_count"] == 1
    assert transport.requests == [
        command_frame(1, expected_request),
        command_frame(1, OP_QUERY),
    ]


def test_adapter_rejects_identity_change_and_missing_physical_binding() -> None:
    moved = RelayIdentity(
        **{
            **IDENTITY.mapping(),
            "port": "COM7",
            "pnp_instance_id": r"USB\VID_1A86&PID_7523\MOVED",
            "usb_location": "Port_#0010.Hub_#0001",
        }
    )
    adapter = ZaveCh340TwoChannelRelay(channel=1, discovery=lambda: [moved])
    with pytest.raises(RelayContractError, match="identity differs"):
        adapter.connect(IDENTITY)

    incomplete = RelayIdentity(
        model=MODEL,
        vid="1A86",
        pid="7523",
        serial_number=NO_USB_SERIAL,
        port="COM14",
    )
    adapter = ZaveCh340TwoChannelRelay(channel=1, discovery=lambda: [incomplete])
    with pytest.raises(RelayContractError, match="PnP instance"):
        adapter.discover()


def test_protocol_error_closes_transport_without_retry() -> None:
    transport = ScriptedTransport((bytes.fromhex("A0 01 00 FF"),))
    adapter = ZaveCh340TwoChannelRelay(
        channel=1,
        discovery=lambda: [IDENTITY],
        transport_factory=lambda _port: transport,
    )
    adapter.connect(IDENTITY)
    with pytest.raises(RelayContractError, match="checksum"):
        adapter.read_commanded_state()
    assert transport.requests == [command_frame(1, OP_QUERY)]
    assert transport.closed is True
