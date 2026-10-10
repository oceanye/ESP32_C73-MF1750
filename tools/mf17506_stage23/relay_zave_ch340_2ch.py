"""Adapter for the documented ZAVE two-channel Type-C CH340 relay.

The relay board has no unique USB serial descriptor.  Live use therefore binds
the documented model and VID/PID together with the current Windows PnP instance,
physical USB location and COM port.  Moving the board to another USB socket is
an identity change that must be commissioned explicitly.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import sys
import time
from collections.abc import Callable
from typing import Protocol

from .relay_contract import (
    RelayAdapter,
    RelayCommandedState,
    RelayContractError,
    RelayIdentity,
)


MODEL = "ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z"
VID = "1A86"
PID = "7523"
NO_USB_SERIAL = "ABSENT-CH340-NO-ISERIAL"
BAUD = 9600

OP_OFF = 0x00
OP_ON = 0x01
OP_OFF_WITH_FEEDBACK = 0x02
OP_ON_WITH_FEEDBACK = 0x03
OP_TOGGLE = 0x04
OP_QUERY = 0x05


class RelaySerialTransport(Protocol):
    def open(self) -> None: ...

    def exchange(self, request: bytes, response_bytes: int) -> bytes: ...

    def close(self) -> None: ...


def command_frame(channel: int, operation: int) -> bytes:
    if channel not in (1, 2):
        raise RelayContractError("relay channel must be 1 or 2")
    if operation not in range(6):
        raise RelayContractError("relay operation must be in the documented range 0..5")
    prefix = bytes((0xA0, channel, operation))
    return prefix + bytes((sum(prefix) & 0xFF,))


def parse_state_frame(response: bytes, channel: int) -> RelayCommandedState:
    if len(response) != 4:
        raise RelayContractError(
            f"relay response must contain exactly 4 bytes; received {len(response)}"
        )
    if response[0] != 0xA0 or response[1] != channel:
        raise RelayContractError(
            f"relay response identity differs: {response.hex(' ').upper()}"
        )
    if response[3] != (sum(response[:3]) & 0xFF):
        raise RelayContractError(
            f"relay response checksum differs: {response.hex(' ').upper()}"
        )
    if response[2] == OP_OFF:
        return RelayCommandedState.OFF
    if response[2] == OP_ON:
        return RelayCommandedState.ON
    raise RelayContractError(
        f"relay returned undocumented state byte 0x{response[2]:02X}"
    )


def _present_serial_ports() -> set[str]:
    if sys.platform != "win32":
        raise RelayContractError("the commissioned relay adapter requires Windows")
    import winreg

    ports: set[str] = set()
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DEVICEMAP\SERIALCOMM",
        ) as key:
            index = 0
            while True:
                try:
                    _, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                if isinstance(value, str) and value.upper().startswith("COM"):
                    ports.add(value.upper())
                index += 1
    except FileNotFoundError:
        return set()
    return ports


def discover_present_bindings() -> list[RelayIdentity]:
    if sys.platform != "win32":
        raise RelayContractError("the commissioned relay adapter requires Windows")
    import winreg

    present_ports = _present_serial_ports()
    base_path = rf"SYSTEM\CurrentControlSet\Enum\USB\VID_{VID}&PID_{PID}"
    identities: list[RelayIdentity] = []
    try:
        base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path)
    except FileNotFoundError:
        return identities
    with base:
        index = 0
        while True:
            try:
                instance = winreg.EnumKey(base, index)
            except OSError:
                break
            index += 1
            instance_path = f"{base_path}\\{instance}"
            try:
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    instance_path,
                ) as instance_key:
                    location = str(
                        winreg.QueryValueEx(instance_key, "LocationInformation")[0]
                    )
                with winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    instance_path + r"\Device Parameters",
                ) as parameters:
                    port = str(winreg.QueryValueEx(parameters, "PortName")[0]).upper()
            except (FileNotFoundError, OSError):
                continue
            if port not in present_ports:
                continue
            identities.append(
                RelayIdentity(
                    model=MODEL,
                    vid=VID,
                    pid=PID,
                    serial_number=NO_USB_SERIAL,
                    port=port,
                    pnp_instance_id=(
                        rf"USB\VID_{VID}&PID_{PID}\{instance}".upper()
                    ),
                    usb_location=location,
                )
            )
    return sorted(identities, key=lambda item: item.port)


class Win32SerialTransport:
    """Small dependency-free synchronous 9600-8-N-1 Windows transport."""

    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _OPEN_EXISTING = 3
    _PURGE_TXABORT = 0x0001
    _PURGE_RXABORT = 0x0002
    _PURGE_TXCLEAR = 0x0004
    _PURGE_RXCLEAR = 0x0008

    class _DCB(ctypes.Structure):
        _fields_ = (
            ("DCBlength", wintypes.DWORD),
            ("BaudRate", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("wReserved", wintypes.WORD),
            ("XonLim", wintypes.WORD),
            ("XoffLim", wintypes.WORD),
            ("ByteSize", ctypes.c_ubyte),
            ("Parity", ctypes.c_ubyte),
            ("StopBits", ctypes.c_ubyte),
            ("XonChar", ctypes.c_char),
            ("XoffChar", ctypes.c_char),
            ("ErrorChar", ctypes.c_char),
            ("EofChar", ctypes.c_char),
            ("EvtChar", ctypes.c_char),
            ("wReserved1", wintypes.WORD),
        )

    class _COMMTIMEOUTS(ctypes.Structure):
        _fields_ = (
            ("ReadIntervalTimeout", wintypes.DWORD),
            ("ReadTotalTimeoutMultiplier", wintypes.DWORD),
            ("ReadTotalTimeoutConstant", wintypes.DWORD),
            ("WriteTotalTimeoutMultiplier", wintypes.DWORD),
            ("WriteTotalTimeoutConstant", wintypes.DWORD),
        )

    def __init__(self, port: str, *, timeout_ms: int = 500) -> None:
        if sys.platform != "win32":
            raise RelayContractError("the serial transport requires Windows")
        if not port.upper().startswith("COM"):
            raise RelayContractError("relay port must be a Windows COM port")
        if timeout_ms < 1:
            raise RelayContractError("relay serial timeout must be positive")
        self.port = port.upper()
        self.timeout_ms = timeout_ms
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._handle: int | None = None

    def _raise_last_error(self, operation: str) -> None:
        error = ctypes.WinError(ctypes.get_last_error())
        raise RelayContractError(f"relay serial {operation} failed: {error}")

    def open(self) -> None:
        if self._handle is not None:
            raise RelayContractError("relay serial port is already open")
        create_file = self._kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            rf"\\.\{self.port}",
            self._GENERIC_READ | self._GENERIC_WRITE,
            0,
            None,
            self._OPEN_EXISTING,
            0,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            self._raise_last_error("open")
        self._handle = int(handle)
        try:
            dcb = self._DCB()
            dcb.DCBlength = ctypes.sizeof(self._DCB)
            if not self._kernel32.GetCommState(self._handle, ctypes.byref(dcb)):
                self._raise_last_error("GetCommState")
            dcb.BaudRate = BAUD
            dcb.flags = 0x00000001  # fBinary; DTR/RTS and flow control disabled.
            dcb.ByteSize = 8
            dcb.Parity = 0
            dcb.StopBits = 0
            if not self._kernel32.SetCommState(self._handle, ctypes.byref(dcb)):
                self._raise_last_error("SetCommState")
            timeouts = self._COMMTIMEOUTS(50, 0, self.timeout_ms, 0, self.timeout_ms)
            if not self._kernel32.SetCommTimeouts(
                self._handle, ctypes.byref(timeouts)
            ):
                self._raise_last_error("SetCommTimeouts")
            self._kernel32.PurgeComm(
                self._handle,
                self._PURGE_TXABORT
                | self._PURGE_RXABORT
                | self._PURGE_TXCLEAR
                | self._PURGE_RXCLEAR,
            )
        except Exception:
            self.close()
            raise

    def exchange(self, request: bytes, response_bytes: int) -> bytes:
        if self._handle is None:
            raise RelayContractError("relay serial port is not open")
        if len(request) != 4 or response_bytes < 0:
            raise RelayContractError("invalid relay serial exchange contract")
        self._kernel32.PurgeComm(
            self._handle, self._PURGE_TXCLEAR | self._PURGE_RXCLEAR
        )
        payload = ctypes.create_string_buffer(request)
        written = wintypes.DWORD()
        if not self._kernel32.WriteFile(
            self._handle,
            payload,
            len(request),
            ctypes.byref(written),
            None,
        ):
            self._raise_last_error("write")
        if written.value != len(request):
            raise RelayContractError(
                f"relay serial short write: {written.value}/{len(request)} bytes"
            )
        response = bytearray()
        deadline = time.monotonic() + (self.timeout_ms / 1000)
        while len(response) < response_bytes and time.monotonic() < deadline:
            buffer = ctypes.create_string_buffer(response_bytes - len(response))
            read = wintypes.DWORD()
            if not self._kernel32.ReadFile(
                self._handle,
                buffer,
                len(buffer),
                ctypes.byref(read),
                None,
            ):
                self._raise_last_error("read")
            if read.value:
                response.extend(buffer.raw[: read.value])
        if len(response) != response_bytes:
            raise RelayContractError(
                f"relay serial short response: {len(response)}/{response_bytes} bytes"
            )
        return bytes(response)

    def close(self) -> None:
        if self._handle is None:
            return
        self._kernel32.CloseHandle(self._handle)
        self._handle = None


class ZaveCh340TwoChannelRelay(RelayAdapter):
    def __init__(
        self,
        *,
        channel: int,
        port: str | None = None,
        discovery: Callable[[], list[RelayIdentity]] = discover_present_bindings,
        transport_factory: Callable[[str], RelaySerialTransport] = Win32SerialTransport,
    ) -> None:
        if channel not in (1, 2):
            raise RelayContractError("relay channel must be 1 or 2")
        self.channel = channel
        self.port = port.upper() if port else None
        self._discovery = discovery
        self._transport_factory = transport_factory
        self._transport: RelaySerialTransport | None = None

    def discover(self) -> RelayIdentity:
        candidates = self._discovery()
        if self.port is not None:
            candidates = [item for item in candidates if item.port == self.port]
        if len(candidates) != 1:
            raise RelayContractError(
                "relay discovery requires exactly one present matching device; "
                f"found {len(candidates)}"
            )
        identity = candidates[0]
        if identity.serial_number == NO_USB_SERIAL and (
            identity.pnp_instance_id is None or identity.usb_location is None
        ):
            raise RelayContractError(
                "relay without USB serial requires PnP instance and USB location"
            )
        return identity

    def connect(self, expected_identity: RelayIdentity) -> None:
        if self._transport is not None:
            raise RelayContractError("relay adapter is already connected")
        discovered = self.discover()
        if discovered != expected_identity:
            raise RelayContractError("relay identity differs from expected binding")
        transport = self._transport_factory(discovered.port)
        transport.open()
        self._transport = transport

    def _exchange_state(self, operation: int) -> RelayCommandedState:
        if self._transport is None:
            raise RelayContractError("relay adapter is not connected")
        try:
            response = self._transport.exchange(
                command_frame(self.channel, operation), 4
            )
            return parse_state_frame(response, self.channel)
        except RelayContractError:
            self.close()
            raise

    def command_off(self) -> None:
        state = self._exchange_state(OP_OFF_WITH_FEEDBACK)
        if state is not RelayCommandedState.OFF:
            self.close()
            raise RelayContractError("relay OFF acknowledgement returned a non-OFF state")

    def command_on(self) -> None:
        state = self._exchange_state(OP_ON_WITH_FEEDBACK)
        if state is not RelayCommandedState.ON:
            self.close()
            raise RelayContractError("relay ON acknowledgement returned a non-ON state")

    def read_commanded_state(self) -> RelayCommandedState:
        return self._exchange_state(OP_QUERY)

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None


def _query(channel: int, port: str | None) -> dict[str, object]:
    adapter = ZaveCh340TwoChannelRelay(channel=channel, port=port)
    identity = adapter.discover()
    adapter.connect(identity)
    try:
        state = adapter.read_commanded_state()
    finally:
        adapter.close()
    return {
        "identity": identity.mapping(),
        "channel": channel,
        "commanded_state": state.value,
        "electrical_state_proven": False,
        "contact_switch_performed": False,
    }


def _set_state(
    channel: int, port: str | None, wanted: RelayCommandedState
) -> dict[str, object]:
    """Issue one feedback command and independently query the commanded state."""

    adapter = ZaveCh340TwoChannelRelay(channel=channel, port=port)
    identity = adapter.discover()
    adapter.connect(identity)
    try:
        if wanted is RelayCommandedState.ON:
            adapter.command_on()
        else:
            adapter.command_off()
        observed = adapter.read_commanded_state()
    finally:
        adapter.close()
    if observed is not wanted:
        raise RelayContractError("relay post-command query differs")
    return {
        "identity": identity.mapping(),
        "channel": channel,
        "commanded_state": observed.value,
        "electrical_state_proven": False,
        "contact_switch_performed": True,
        "feedback_command_count": 1,
        "independent_query_count": 1,
        "retry_performed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover, query, or feedback-command the ZAVE CH340 relay."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("discover")
    query = subparsers.add_parser("query")
    query.add_argument("--channel", type=int, choices=(1, 2), required=True)
    query.add_argument("--port")
    for name in ("off", "on"):
        command = subparsers.add_parser(name)
        command.add_argument("--channel", type=int, choices=(1, 2), required=True)
        command.add_argument("--port")
    args = parser.parse_args(argv)
    if args.command == "discover":
        payload: object = [item.mapping() for item in discover_present_bindings()]
    elif args.command == "query":
        payload = _query(args.channel, args.port)
    else:
        wanted = (
            RelayCommandedState.ON
            if args.command == "on"
            else RelayCommandedState.OFF
        )
        payload = _set_state(args.channel, args.port, wanted)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
