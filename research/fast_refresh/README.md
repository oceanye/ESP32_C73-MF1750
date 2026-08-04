# Fast-refresh offline workflow

This directory records evidence and hardware gates for MF-1750 fast-refresh
work. None of the included tools connects to a panel.

Generate the mandatory 1/2/4/8/10 MHz sweep plan:

```powershell
python tools\mf1750_refresh_analyzer.py plan --output sweep.json
```

At home, capture exactly one run's serial log, `GET /api/job`, and
`GET /api/diagnostic/report` responses after one cold-start MAP_ORIENT_V1 run.
Merge them only after recording the panel, supply, temperature, and acoustic
observations:

```powershell
python tools\mf1750_refresh_analyzer.py extract sweep.json `
  --serial-log run-1mhz.log `
  --report run-1mhz-report.json `
  --job-report run-1mhz-job.json `
  --spi-hz 1000000 `
  --firmware-build-tag MF1750_DRIVER_RC1_R16_CCSET_MAPHASH_2026-08-04 `
  --cold-start --power-off-s 10 `
  --supply-voltage-v 3.30 --current-limit-a 1.0 `
  --peak-current-a 0.20 --max-temperature-c 30.0 `
  --visual-pass --cv-pass --thermal-pass --acoustic-pass `
  --output sweep-1mhz.json
```

For a failed observation, explicitly use the corresponding `--no-...` flag,
for example `--no-visual-pass`; never omit or convert a failed run into a
pending row. Schema version 2 rejects logs containing multiple refresh runs,
cross-checks duplicate log/report hashes and timings, and requires a completed
job plus a valid, non-running, mapping-applied diagnostic report. It also
records PON/DRF/POF/post-PSR timings and SHA-256 provenance for all captures.

Validate progress:

```powershell
python tools\mf1750_refresh_analyzer.py analyze sweep-1mhz.json
```

Exit code `0` means all runs in the file passed, `1` means a safety or
correctness gate failed, and `2` means the plan is incomplete or malformed.
Generate a 20 MHz row only after 1/2/4/8/10 MHz all pass:

```powershell
python tools\mf1750_refresh_analyzer.py plan --include-20mhz --output sweep-20mhz.json
```

The tool always reports `waveform_fast_refresh_tested: false`; an SPI upload
sweep is not evidence that DRF waveform time improved.

## Controller-neutral partial-update planning

Two canonical raw files are not, by themselves, proof of the pixels currently
held by the panel. Without trusted last-success provenance the planner therefore
returns a conservative full-screen protection region, leaves the true changed
pixel count unknown, and does not create a transition histogram:

```powershell
python -m tools.mf1750_partial_plan new.raw `
  --old-frame old.raw `
  --neighbor-radius 1 `
  --output partial-plan.json
```

Only a frame tied to the last successful physical display operation may enable
pixel comparison:

```powershell
python -m tools.mf1750_partial_plan new.raw `
  --old-frame old.raw `
  --last-success-operation-id <operation-id> `
  --last-success-frame-fnv1a <0x-hash> `
  --trust-last-success `
  --neighbor-radius 1 `
  --output partial-plan.json
```

That trusted report contains the changed-pixel count, a 6x6 old-to-new
transition histogram, cardinal-neighbor protection, packed-byte-aligned
bounding boxes, and logical-half regions. It does not call those logical halves
CS1/CS2. Physical-controller coordinates are added only when the caller also
provides two reviewed, bijective `--frozen-controller-mapping` values in
physical-controller order.

This planner never creates SPI commands. Its output cannot be sent to the panel
until the matching SPD1657B partial-update definition and waveform are supplied.
