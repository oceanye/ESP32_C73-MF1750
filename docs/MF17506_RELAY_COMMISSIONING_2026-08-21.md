# MF17506 USB relay commissioning record

Recorded: `2026-08-21 19:00 +08:00`

Status: `R0 IDENTITY/PROTOCOL PARTIAL PASS / R1 SINGLE-CYCLE PRELIMINARY PASS / R2-R3 NOT PASSED`

This record covers only the two-channel Type-C relay supplied under
`参考资料/2路控制继电器Type-c/`. It does not authorize a panel refresh, ESP32 reset or
flash, unattended operation, or a production Stage-2 session.

## Documented device and protocol

- Project binding model: `ZAVE-2CH-TYPE-C-CH340-JQC-3FF-S-Z`.
- USB bridge: CH340, Windows driver provider `wch.cn`, driver version
  `3.9.2024.9`, driver date `2024-09-16`.
- USB identity: VID `1A86`, PID `7523`; this device exposes no unique USB serial
  descriptor.
- Serial settings: `9600 8N1`, raw hexadecimal bytes, no newline.
- Channel 1 OFF/ON/query: `A0 01 00 A1`, `A0 01 01 A2`, `A0 01 05 A6`.
- Channel 2 OFF/ON/query: `A0 02 00 A2`, `A0 02 01 A3`, `A0 02 05 A7`.
- Feedback commands used by the adapter: channel 1 OFF/ON
  `A0 01 02 A3` / `A0 01 03 A4`; channel 2 follows the documented checksum rule.
- The supplied material labels the relay as 5 V coil, JQC-3FF-S-Z, with printed
  contact ratings up to 10 A at the listed AC/DC voltages. Those markings and the
  exact seller SKU have not yet been confirmed from photographs of the delivered
  board itself.

Bound source evidence:

- `指令详情.png`: SHA-256
  `32860bbd707924d162671368ce2a5c3054148d2dfc05b817b8cba30b93c55770`.
- `注意事项.txt`: SHA-256
  `6d15d841711a74c5e310daad5273a862a1d4816341c95995c016dda1e05ac70f`.

## Enumeration evidence

The first observed attachment enumerated as:

- `COM7`;
- PnP instance `USB\VID_1A86&PID_7523\5&230B5917&0&10`.

After the operator deliberately moved the Type-C cable to another USB socket, the
present device enumerated as:

- `COM14`;
- PnP instance `USB\VID_1A86&PID_7523\5&230B5917&0&4`;
- location `Port_#0004.Hub_#0001`.

Both channels returned explicit OFF frames before and after the move. This proves
the queried commanded state after enumeration; it does not prove that no
sub-observation transient contact closure occurred. Because there is no USB
serial number, moving USB sockets is treated as an identity change and requires
explicit rebinding of COM, PnP instance and physical USB location.

## Software adapter

- Adapter: `tools/mf17506_stage23/relay_zave_ch340_2ch.py`, SHA-256
  `1e64699edc0d06c64c481c64bf86a8ff672083d90142230b2a653666d504faf9`.
- Extended identity contract: `tools/mf17506_stage23/relay_contract.py`, SHA-256
  `ead8b2d2d046a84d568f09940843a319fad174bd187a0e97159b1c43ac5fd5d8`.
- Targeted tests: `tests/test_mf17506_relay_zave_ch340.py`, SHA-256
  `2f9b9964fad1b63ed4fdbd607864d1addfe2a1f44c98a5c09d75606e0163bcdf`.
- Validation: targeted relay tests plus the existing static-photo relay tests
  reported `12 passed`; Ruff and `py_compile` passed.

The adapter uses feedback frames, exact checksum/state parsing, no automatic
retry, and closes the transport on malformed, partial or mismatched replies. It
binds the no-serial CH340 by model, VID/PID, COM, PnP instance and USB location.

## Physical observations

1. Both channels accepted ten consecutive OFF-with-feedback commands and ended
   in queried OFF. No ON command was used during this idempotence test.
2. The operator reported wiring the driver-board 3.3 V positive lead through
   channel 1 `COM1 -> NO1`; the upstream source remained at 3.3 V.
3. One channel-1 `OFF -> ON -> OFF` command cycle was executed. Each transition
   returned the expected feedback and the following query agreed.
4. At ON, the upstream power-supply current was reported as `0.001 A`; there was
   no indicator LED and no abnormal heating.
5. At OFF, the upstream power-supply current was reported as `0.000 A`.
6. The relay was left in commanded OFF. No COM8 access, firmware flash, reset,
   device HTTP request, or visible panel refresh was performed.

The `0.001 A -> 0.000 A` current change is preliminary evidence that the load is
being switched. The voltage sensor is upstream of the relay, so the reported 3.3
V does not prove the driver-board input voltage or contact voltage drop.

## Gate decision

| Gate | Decision | Remaining evidence |
|---|---|---|
| R0 identity/document | `PARTIAL PASS` | Photograph delivered board front/back and terminal markings; measure COM-NO default continuity; observe insertion/boot for transient closure. |
| R1 empty-contact behavior | `PARTIAL PASS` | ON/OFF endurance and unplug/process-exit/sleep behavior remain untested. |
| R2 safe dummy load | `NOT RUN` | Use a measured low-voltage dummy load for 100 cycles and fault-injection tests. |
| R3 driver board without panel | `NOT PASSED` | Measure downstream driver input at ON/OFF, OFF residual/decay and GPIO back-power; confirm panel is disconnected for the formal test. |

The relay must remain supervised. Until ON-state USB loss is characterized, it
must be treated as `NO_HARDWARE_FAILSAFE` for planning purposes.

