# MF17506 Stage-III dual-R20 discovery-first runbook

Recorded: `2026-08-21 23:36 +08:00`

Status: `OFFLINE READY / NOT FLASHED / NOT LIVE AUTHORIZED`

## Fast decision rule

Each candidate receives one fixed atlas refresh only.  The two controllers
display the same eight technical pixel codes, but use different native R20
payloads:

- CS1: `WF20_25` native R20/R21;
- CS2: `WF23_25` native R20/R21.

The global header is shared by both controllers, so two candidates are staged:

1. `H20`: native WF20 PWR/PLL header;
2. `H23`: native WF23 PWR/PLL header.

This yields 16 profile-code outcomes per visible atlas refresh.  It is not
spatial dithering and does not claim 16 independently programmable LUTs.

After the operator looks at one candidate:

- `no_new_color`: execute its independent factory-OTP white recovery, then
  advance to the next candidate;
- `suspected_new_color`: execute white recovery, stop the unswapped sequence,
  and only then build a left/right-swapped replication;
- brightness-only differences are recorded but follow `no_new_color`.

## Frozen artifacts

| Candidate | Image | BIN SHA-256 | ELF SHA-256 |
|---|---|---|---|
| H20 | treatment | `315bffd51a4d8279f96e109adf3a5864b3945f8ce3091b4868fa72f0c956a98e` | `2c2d9f44537340b094d18e9111908a26b490c741d9bee6cc87823736c2e83919` |
| H20 | white | `d042c9127e00c2f64e68390fbd57d0295fa46987b4bd6bee29a571286fd3585a` | `5d3860694c7574a0fb8ff1199359d8e11c199ed63347bc2fadb848427fb0ed55` |
| H23 | treatment | `87bb4ae4cfe89b655e6b85138a6ecf2391e25b00fe758a0a3ad9124bd38ac184` | `89d415f88a3315ae7f3e7979e7f6f3f2f64fbbc563953571fbf3214118cac14d` |
| H23 | white | `f25f00f55c979272b7d01dd3b5f67b86b6b27150c0f35333e4a60e7fee59fc43` | `ba2bf9e1807ca2fce4870990a8b2d81a73cc0736abbbf97cb7fadcb5588b4ff5` |

All four PlatformIO environments build successfully and every BIN app
descriptor exactly binds its selected ELF.  The paired generated-include SHA
is `86981885b2d4a0eece7060d843eaed3f942cfc62c6046620130b3c83bd58290f`.

Host gate: `tools/mf1750_dual_r20_discovery_once.py`.

## Live boundaries

The runner does not flash firmware or control J2.  Each live action still
requires an app-only flash/verify while J2 is OFF, a virgin GET-only diagnostic,
and exactly one ARM plus one EXECUTE after the separate live gate.  Recovery is
a separate binary and action.  There is no retry, automatic recovery, automatic
candidate chaining, raw payload ingress, profile parameter, unknown command,
partial refresh, pixel dithering, SPI sweep, VCOM write, or mid-refresh cut.

H23 treatment is fail-closed unless stored evidence proves both:

1. H20 operator decision is exactly `no_new_color`;
2. H20 factory-OTP white action completed successfully.

If H20 is `suspected_new_color`, H23 is blocked and a separately identified
left/right swap image must be built instead.
