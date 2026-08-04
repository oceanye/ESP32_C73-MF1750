# MF-1750 host frame core

This package is the hardware-independent reference for the application frame
contract. It has no third-party dependencies and performs no network, GPIO, or
serial I/O.

The canonical frame is `1024x600`, row-major, and 4 bits per pixel. Logical
`(0, 0)` is the top-left pixel; even x occupies the high nibble and odd x the
low nibble. Valid physical codes are black `0`, white `1`, yellow `2`, red `3`,
blue `5`, and green `6`.

Example:

```python
from host.epd_frame import ControllerMapping, controller_stream, generate_fixture, split_controllers

frame = generate_fixture("map-orient-v1")
logical_left, logical_right = split_controllers(frame)

# Physical CS hashes exist only after mappings are explicit and accepted.
cs1_dtm = controller_stream(frame, ControllerMapping(source_half=0))
cs2_dtm = controller_stream(frame, ControllerMapping(source_half=1))
```

Run the host regression suite from the repository root:

```powershell
python -m unittest discover -s tests -v
```

The package does not claim hardware validation. Physical mapping remains owned
by the firmware configuration and must be accepted on the panel at home.

`tools/mf1750_frame_tool.py` imports this package rather than maintaining a
second frame implementation. Its offline report names the default split
`logical_left_fnv1a` / `logical_right_fnv1a`; it emits physical CS1/CS2 hashes
only when two ordered `--controller-mapping` values are supplied.

Offline generation and non-refreshing ingress may omit mappings. A refresh may
not: it requires exactly two explicit `--controller-mapping` arguments in CS1,
CS2 order, plus `--confirm-cold-start`. Before `/api/frame` is posted, the tool
validates the complete frame with the canonical `validate_frame` contract and
requires `/api/version` to report matching `CS1 Mapping` / `CS2 Mapping`
four-bit tuples and `Refresh SPI Hz: 1000000`. Missing or mismatched preflight
fields stop the operation before the frame POST; the later diagnostic mapping
and both physical DTM hashes are still checked independently. Ingress is
accepted only when its response explicitly says `epd_action: "none"`.

A refresh diagnostic is not accepted on sequence labels alone. It must report
`pon_ms`, `drf_ms`, `pof_ms`, and `post_psr_ms`, with each matching
its `*_busy_seen` field. PON, DRF, and POF must each report `busy_seen=true`;
the post-POF PSR register write is informational and may remain false, as
confirmed on Rev A1 hardware. `drf_ms` must be within 10000..60000 ms,
`last_wait_ms` must equal `post_psr_ms`, and `total_ms` cannot be shorter than
the two controller upload times plus all four recorded wait times.

Tool reports never claim a hardware acceptance test: offline JSON uses
`offline_verified`, network JSON uses `protocol_verified`, and both explicitly
carry `hardware_tested: false` plus a bounded `verified_scope`. A refresh also
lists the still-required manual observations for the full-panel visual result,
power-supply CV/current, and L1/L2 temperature.

The completed `/api/job` timestamps must be u32 values in queue/start/finish
order (including normal `millis()` wrap), and the diagnostic wrapper's
`job_queued_at_ms`, `job_started_at_ms`, and `job_finished_at_ms` must match
them exactly. A schema-v2 diagnostic must also carry non-zero u32
`operation_id` and `job_operation_id` values that match exactly; the accepted
protocol report preserves this immutable job-to-driver operation identity.
`busy_assertion_missing` must be strictly false and `busy_missing_stage` must
be the literal `none`, independently of the four per-stage BUSY sample fields.

The refresh preflight accepts only the exact build tag in the tool's safety
allowlist; prefix or substring lookalikes are rejected before upload. Malformed
URLs are reported as `FrameToolError`. Output protection also rejects `--force`
when the destination is a hard-link alias of any frozen production file.
