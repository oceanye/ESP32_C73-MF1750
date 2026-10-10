# Extended-color record contracts

These schemas are host-side evidence contracts. They do not authorize or
perform a display refresh. Unknown or unmeasured values stay JSON `null`; a
target color, simulated value, intended voltage, or operator impression must
not be substituted for a measurement.

The run, optical, electrical and event/recovery records use the same
fail-closed evidence state:

- `not_run`: `hardware_tested=false`, `generated_at=null`, evidence hashes and
  authorization identities are null, and `null_reason` is mandatory;
- `partial` or `invalid`: hardware was involved, immutable time/hash/
  authorization evidence is mandatory, and `null_reason` explains every
  missing or rejected result;
- `complete`: hardware, time, authorization and evidence hashes are present,
  `null_reason=null`, and all record-specific measurements/safe-finish fields
  are complete. `electrical` is the deliberate exception in v2: because no
  reviewed absolute-limit profile is allowlisted yet, `complete` is
  unreachable and hardware acquisitions must remain `partial` or `invalid`.

`host.extended_color.records` supplies semantic validators for all four record
types. Call the matching validator after JSON parsing and before accepting,
aggregating or publishing a record. The validators reject booleans disguised
as integers, NaN/infinity, timestamp/hash/authorization gaps, identity
mismatches, unsafe ROI geometry, incomplete acquisition evidence and
inconsistent recovery or final-power claims. JSON Schema validation alone is
not a substitute for these cross-field checks.

All v2 timestamps use strict RFC 3339 (`T` separator, seconds present, and
`Z` or an `HH:MM` numeric offset). A run authorization scope binds the exact
`test_id` and frame SHA-256 through a recomputed canonical SHA-256. The frame
identity validator likewise recomputes the canonical digest over the frame
and ordered CS1/CS2 identities; matching FNV integer/hex spelling alone is not
accepted as integrity evidence.

## Version 2 migration

The fail-closed rules are a breaking contract change. `run`, `optical`,
`electrical`, `event_recovery` and `transition_profile` therefore use
`schema_version: 2`; the Python validators reject version 1 records. Do not
edit a v1 file in place or merely change its version number. Rebuild it as a
v2 record, add the required evidence state/reason and provenance fields, keep
unknown values null, then run both the matching JSON Schema and Python
semantic validator. The offline transition-profile generator now emits the
same all-null 36-cell scaffold as v2.

The canonical optical v2 record is fixed to CIE Lab under D65/2deg and 45/0.
Any D50, 10-degree or other secondary/raw-derived result needs a separately
named contract and must not be inserted into this canonical record.

## N5 external-table and aggregation contracts

N5 adds canonical semantic contracts in
`host.extended_color.spectral`, `host.extended_color.aggregation`, and
`host.extended_color.execution`. These
contracts deliberately do **not** bundle CIE D65 SPD or CIE 1931 2-degree CMF
samples. A standard table is accepted only after caller-supplied raw CIE CSV
bytes match reviewed primary-source SHA-256 identities. The compiler then
requires the exact 360..830 nm, 1 nm or 5 nm grid and recomputes the D65 white,
XYZ and CIE 1976 Lab without interpolation or extrapolation. The Python
semantic validator, not a flag in a JSON file, is the authority for the
cross-document source/table/reflectance/report bindings.

The formal palette plan is 36 raw observations: six codes, two frozen fixture
orientations and three independent formal runs. It is intentionally not 72.
`global-v-bars` contains a given colour on only one controller; the horizontal
fixture uses the opposite controller ROI, so each colour ends with three CS1
and three CS2 observations. Attempting to label the other vertical half as the
same colour is rejected. Both pilots are excluded, every run has six ordered
readings in the POF+55..65 s window, and missing/outlier/weight/U95/R&R rules
are preregistered.

The descriptive 72-ROI transition atlas cannot emit a measured profile. The
formal plan contains 360 raw observations (36 pairs x five repeats x two
paired controllers). Primary statistics use five CS1/CS2 repeat aggregates,
therefore n=5 and P95/P99 remain null; raw n=10 controller values are retained
only as paired descriptive diagnostics, also without population percentiles.
All 36 output cells require five repeat evidence identities.

The JSON shapes are intentionally validated together with their referenced
table, qualification, P0 action/result and raw evidence objects. A standalone
JSON Schema cannot establish these cross-file identities or measurement
authenticity. Use the sealing/validation APIs and the frozen N5 campaign
compiler described in
`docs/N5_MEASUREMENT_OFFLINE_HANDOFF_2026-08-08.md`; do not hand-edit
`qualified`, `measured`, `calibrated` or `hardware_ready`.

Formal aggregation additionally requires a deeply validated finalized execution
bundle. That bundle separately binds the external authorization, atomic
workspace-global claim, reviewed limit profile, protocol evidence, manual
observation, action finalization, P0 result, and session finalization by
whole-file SHA-256. Every formal measurement must match one frozen action slot;
a standalone or hand-edited PASS result is not sufficient. The read-only N5
CLI only lists/describes frozen actions. Live callers must explicitly invoke
the one-action engine with a caller-supplied authorization and transport; the
engine never auto-advances, retries, or recovers.

Files:

- `run.schema.json`: specimen, authorization, build, frame and run identity;
- `optical.schema.json`: actual initial/final Lab, Delta E00, uniformity and ghosting by ROI;
- `electrical.schema.json`: synchronized BUSY, input power, TP1/TP3/TP5/TP6 and thermal data;
- `event_recovery.schema.json`: ordered events, immutable no-retry record and separately authorized recovery;
- `asset_manifest.schema.json`: SHA-256 identities for explicitly listed RAW/scope/colorimeter evidence;
- `transition_profile.schema.json`: exactly 36 old-to-new cells for downstream C3 optimization.
- `area_mix.schema.json`: offline six-primary tile recipes, calibrated-palette
  provenance, XYZ prediction limits, frame-contract identity and both DTM hashes.

`tools/mf1750_asset_manifest.py` accepts only an explicit asset plan, reads
those files, hashes them, and creates a new manifest. It has no recursive scan,
network, serial, device, refresh, delete, or overwrite function.

`tools/mf1750_transition_profile.py` emits the complete 36-cell profile
scaffold. Until Stage E measurements exist, `sample_count` is zero and every
measurement is explicitly `null`. The tool also applies
`host.extended_color.validate_transition_profile()` so every old/new pair must
occur exactly once; this cross-item rule is stronger than `uniqueItems` alone.
When any cell has `sample_count>0`, all of its Lab, delta, timing, electrical,
thermal and recovery fields must be present, finite and in range;
`hardware_tested=true` and a timezone-bearing `generated_at` then become
mandatory. Each sample also carries one source-run hash, asset-manifest hash
and authorization identity. Panel serial, firmware/binary identity, waveform
identity, environment record, and canonical `D65`/`2deg`/`45/0` measurement
conditions are mandatory profile-level provenance. The original all-null
36-cell offline scaffold remains valid and keeps every provenance field null.

Electrical v2 freezes `absolute_limit_known=false` and
`limit_profile.qualified=false`. A candidate profile may be identified by its
version, SHA-256 and source, but these self-reported fields cannot qualify it.
TP3 is a positive rail; TP5 and TP6 are negative rails. A polarity violation
must be saved as `invalid` evidence rather than discarded, while `partial`
evidence rejects the wrong polarity. `complete` remains hard blocked in both
JSON Schema and the Python validator until a reviewed allowlist is introduced
through an explicit future contract change.

A complete event/recovery record contains exactly one passed occurrence of
the frozen refresh chain from power-off confirmation through PON/DRF/POF,
operator observation, separately authorized power-off, and final TP1-zero
confirmation, in that order. Flash and recovery events are optional, but when
present their action records must match their authorization identities. Flash
must remain between confirmed power-off and power-on authorization. Recovery
must remain as one contiguous block after observation and before final
power-off authorization; it requires one authorization, four B/W/B/W frames,
one confirmation, and measured pass metrics. A fault, failed, missing,
duplicated, misplaced or reordered event cannot be labelled complete.

`tools/mf1750_area_mix.py` enumerates exact 2x2 or 4x4 six-primary area
recipes and ranks their first-order CIE XYZ predictions with CIEDE2000. A
calibrated D65/2deg panel palette is mandatory unless the caller explicitly
selects uncalibrated simulation. Palette schema v2 provenance alone does not
bind panel/batch, firmware/waveform, environment, geometry, backing and the
raw measurement artifact, so area-mix schema v2 always records
`hardware_formal_qualified=false`. `frame_contract_compatible=true` means only
that generated bytes obey the 1024x600 4bpp six-code contract; it is not a
hardware qualification or authorization. The former v1 name
`formal_api_compatible` is deprecated and forbidden in v2 reports.
Predictions are never labelled as measured data. Its semantic validator
recomputes the deterministic top-N recipes,
predictions, tile layout, report identity, legal six-code frame identity, and both DTM
identities. A rendered frame requires a report sidecar and both files use
exclusive-create semantics. Input and output guards reject `.test-output/`,
the frozen production directory, Windows device names, UNC/device namespaces,
NTFS alternate streams, and mapped network drives. The tool has no device,
serial, HTTP, refresh, waveform, or voltage path.
