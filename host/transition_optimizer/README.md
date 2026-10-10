# C3 transition-aware optimizer

This host-only package implements deterministic, measured-profile transition-
aware error diffusion.  It cannot access the network or a device and never
creates a visible-refresh authorization.

The objective is:

```text
J = alpha * CIEDE2000 perceptual error
  + beta  * normalized measured transition cost
  + gamma * changed-pixel penalty
  + delta * local spatial-clustering penalty
```

`beta` consumes a complete, semantically validated 6x6 profile from
`host.extended_color`.  Missing cells fail closed unless the caller explicitly
requests a report-marked perceptual-only fallback.  An unknown old frame also
fails closed unless a conservative worst-case or unqualified perceptual-only
mode is selected.

A calibrated palette and a measured transition profile are not assumed to
belong to the same panel.  Formal-input eligibility additionally requires a
`TransitionInputBinding` that matches both canonical identities and the exact
panel/build/waveform context.  Even then, an output remains offline and not
hardware-qualified until independently tested.

The current fixed global waveform means pixel choices cannot be claimed to
shorten BUSY time.  `build_pareto_report()` preserves every evaluated weight
point and deliberately selects no single winner.
