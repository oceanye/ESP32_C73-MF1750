# Extended-color record contracts

These schemas are host-side evidence contracts. They do not authorize or
perform a display refresh. Unknown or unmeasured values stay JSON `null`; a
target color, simulated value, intended voltage, or operator impression must
not be substituted for a measurement.

Files:

- `run.schema.json`: specimen, authorization, build, frame and run identity;
- `optical.schema.json`: actual initial/final Lab, Delta E00, uniformity and ghosting by ROI;
- `electrical.schema.json`: synchronized BUSY, input power, TP1/TP3/TP5/TP6 and thermal data;
- `event_recovery.schema.json`: ordered events, immutable no-retry record and separately authorized recovery;
- `asset_manifest.schema.json`: SHA-256 identities for explicitly listed RAW/scope/colorimeter evidence;
- `transition_profile.schema.json`: exactly 36 old-to-new cells for downstream C3 optimization.
- `area_mix.schema.json`: offline six-primary tile recipes, calibrated-palette
  provenance, XYZ prediction limits, formal frame identity and both DTM hashes.

`tools/mf1750_asset_manifest.py` accepts only an explicit asset plan, reads
those files, hashes them, and creates a new manifest. It has no recursive scan,
network, serial, device, refresh, delete, or overwrite function.

`tools/mf1750_transition_profile.py` emits the complete 36-cell profile
scaffold. Until Stage E measurements exist, `sample_count` is zero and every
measurement is explicitly `null`. The tool also applies
`host.extended_color.validate_transition_profile()` so every old/new pair must
occur exactly once; this cross-item rule is stronger than `uniqueItems` alone.

`tools/mf1750_area_mix.py` enumerates exact 2x2 or 4x4 six-primary area
recipes and ranks their first-order CIE XYZ predictions with CIEDE2000. A
calibrated D65/2deg panel palette is mandatory unless the caller explicitly
selects uncalibrated simulation. Predictions are never labelled as measured
data. Its semantic validator recomputes the deterministic top-N recipes,
predictions, tile layout, report identity, formal frame identity, and both DTM
identities. A rendered frame requires a report sidecar and both files use
exclusive-create semantics. Input and output guards reject `.test-output/`,
the frozen production directory, Windows device names, UNC/device namespaces,
NTFS alternate streams, and mapped network drives. The tool has no device,
serial, HTTP, refresh, waveform, or voltage path.
