"""Fail-closed relay identity and panel-power state machine contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class RelayContractError(RuntimeError):
    """Raised when relay identity, acknowledgement, or state differs."""


class RelayCommandedState(str, Enum):
    ON = "ON"
    OFF = "OFF"
    UNKNOWN = "UNKNOWN"


class PowerState(str, Enum):
    SAFE_OFF = "SAFE_OFF"
    POWERING_ON = "POWERING_ON"
    ON_VERIFY = "ON_VERIFY"
    RUN_READY = "RUN_READY"
    ACTION_ACTIVE = "ACTION_ACTIVE"
    POWERING_OFF = "POWERING_OFF"
    OFF_VERIFY = "OFF_VERIFY"
    FAULT_LATCHED = "FAULT_LATCHED"


@dataclass(frozen=True)
class RelayIdentity:
    model: str
    vid: str
    pid: str
    serial_number: str
    port: str
    pnp_instance_id: str | None = None
    usb_location: str | None = None

    def __post_init__(self) -> None:
        for label in ("model", "vid", "pid", "serial_number", "port"):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip():
                raise RelayContractError(f"relay {label} must be a non-empty string")
        for label in ("pnp_instance_id", "usb_location"):
            value = getattr(self, label)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise RelayContractError(
                    f"relay {label} must be None or a non-empty string"
                )

    def mapping(self) -> dict[str, str]:
        return {
            "model": self.model,
            "vid": self.vid,
            "pid": self.pid,
            "serial_number": self.serial_number,
            "port": self.port,
            "pnp_instance_id": self.pnp_instance_id,
            "usb_location": self.usb_location,
        }


class RelayAdapter(Protocol):
    def discover(self) -> RelayIdentity: ...

    def connect(self, expected_identity: RelayIdentity) -> None: ...

    def command_off(self) -> None: ...

    def command_on(self) -> None: ...

    def read_commanded_state(self) -> RelayCommandedState: ...

    def close(self) -> None: ...


class PowerStateMachine:
    def __init__(self) -> None:
        self.state = PowerState.SAFE_OFF
        self.active_action: str | None = None
        self.events: list[dict[str, Any]] = []
        self._ordinal = 0

    def _transition(self, expected: PowerState, target: PowerState, event: str) -> None:
        if self.state is not expected:
            raise RelayContractError(
                f"{event} requires {expected.value}; current state is {self.state.value}"
            )
        self._ordinal += 1
        self.events.append(
            {
                "ordinal": self._ordinal,
                "event": event,
                "state_before": self.state.value,
                "state_after": target.value,
            }
        )
        self.state = target

    def begin_power_on(self) -> None:
        self._transition(PowerState.SAFE_OFF, PowerState.POWERING_ON, "begin_power_on")

    def relay_on_acknowledged(self) -> None:
        self._transition(
            PowerState.POWERING_ON, PowerState.ON_VERIFY, "relay_on_acknowledged"
        )

    def verify_on(self) -> None:
        self._transition(PowerState.ON_VERIFY, PowerState.RUN_READY, "verify_on")

    def start_action(self, action_id: str) -> None:
        if not isinstance(action_id, str) or not action_id.strip():
            raise RelayContractError("action_id must be non-empty")
        self._transition(PowerState.RUN_READY, PowerState.ACTION_ACTIVE, "start_action")
        self.active_action = action_id
        self.events[-1]["action_id"] = action_id

    def finish_action(self, action_id: str) -> None:
        if action_id != self.active_action:
            raise RelayContractError("finish action identity differs")
        self._transition(
            PowerState.ACTION_ACTIVE, PowerState.RUN_READY, "finish_action"
        )
        self.events[-1]["action_id"] = action_id
        self.active_action = None

    def begin_power_off(self) -> None:
        self._transition(
            PowerState.RUN_READY, PowerState.POWERING_OFF, "begin_power_off"
        )

    def relay_off_acknowledged(self) -> None:
        self._transition(
            PowerState.POWERING_OFF, PowerState.OFF_VERIFY, "relay_off_acknowledged"
        )

    def verify_off(self) -> None:
        self._transition(PowerState.OFF_VERIFY, PowerState.SAFE_OFF, "verify_off")

    def latch_fault(self, reason: str) -> None:
        if self.state is PowerState.FAULT_LATCHED:
            return
        self._ordinal += 1
        self.events.append(
            {
                "ordinal": self._ordinal,
                "event": "latch_fault",
                "reason": reason,
                "state_before": self.state.value,
                "state_after": PowerState.FAULT_LATCHED.value,
                "automatic_retry_allowed": False,
            }
        )
        self.state = PowerState.FAULT_LATCHED
        self.active_action = None
