"""In-memory relay fake; it never opens a serial port or touches hardware."""

from __future__ import annotations

from .relay_contract import (
    RelayCommandedState,
    RelayContractError,
    RelayIdentity,
)


FAKE_IDENTITY = RelayIdentity(
    model="MF17506-RELAY-FAKE",
    vid="FAKE",
    pid="FAKE",
    serial_number="FAKE-OFFLINE-ONLY",
    port="FAKE://NO-IO",
)


class FakeRelay:
    def __init__(self, *, fail_operation: str | None = None) -> None:
        self.identity = FAKE_IDENTITY
        self.fail_operation = fail_operation
        self.connected = False
        self.closed = False
        self.commanded_state = RelayCommandedState.OFF
        self.calls: list[str] = []

    def _call(self, operation: str) -> None:
        self.calls.append(operation)
        if self.fail_operation == operation:
            self.commanded_state = RelayCommandedState.UNKNOWN
            raise RelayContractError(f"fake injected failure at {operation}")

    def discover(self) -> RelayIdentity:
        self._call("discover")
        return self.identity

    def connect(self, expected_identity: RelayIdentity) -> None:
        self._call("connect")
        if expected_identity != self.identity:
            raise RelayContractError("fake relay identity differs")
        self.connected = True

    def command_off(self) -> None:
        self._call("command_off")
        if not self.connected:
            raise RelayContractError("fake relay is not connected")
        self.commanded_state = RelayCommandedState.OFF

    def command_on(self) -> None:
        self._call("command_on")
        if not self.connected:
            raise RelayContractError("fake relay is not connected")
        self.commanded_state = RelayCommandedState.ON

    def read_commanded_state(self) -> RelayCommandedState:
        self._call("read_commanded_state")
        if not self.connected:
            return RelayCommandedState.UNKNOWN
        return self.commanded_state

    def close(self) -> None:
        self._call("close")
        self.closed = True
        self.connected = False
