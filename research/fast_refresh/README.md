# Fast-refresh offline workflow

This directory records evidence and hardware gates for MF-1750 fast-refresh
work. None of the included tools connects to a panel.

Generate the mandatory 1/2/4/8/10 MHz sweep plan:

```powershell
python tools\mf1750_refresh_analyzer.py plan --output sweep.json
```

At home, capture the serial log and `GET /api/diagnostic/report` response after
one cold-start MAP_ORIENT_V1 run. Merge them into the plan only after visually
checking the panel, supply CV/current, and temperature:

```powershell
python tools\mf1750_refresh_analyzer.py extract sweep.json `
  --serial-log run-1mhz.log `
  --report run-1mhz-report.json `
  --spi-hz 1000000 `
  --cold-start --power-off-s 10 `
  --visual-pass --cv-pass --thermal-pass `
  --output sweep-1mhz.json
```

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

Once two canonical raw frames are available, compare them without contacting a
device:

```powershell
python -m tools.mf1750_partial_plan new.raw `
  --old-frame old.raw `
  --neighbor-radius 1 `
  --output partial-plan.json
```

The report contains the changed-pixel count, a 6x6 old-to-new transition
histogram, cardinal-neighbor protection, packed-byte-aligned bounding boxes,
and separate CS1/CS2 regions. If the old state is unknown, omit `--old-frame`;
the planner conservatively marks the full display changed and leaves the
transition histogram null.

This planner never creates SPI commands. Its output cannot be sent to the panel
until the matching SPD1657B partial-update definition and waveform are supplied.
