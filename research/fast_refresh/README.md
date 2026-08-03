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

