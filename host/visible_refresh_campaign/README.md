# Visible-refresh campaign contracts

This package is the shared offline contract layer for future N2/N3/N4/N5
campaigns. It deliberately does not import an HTTP client, inspect a device,
write a claim, create an authorization, flash firmware, retry, or recover.
The frozen N0/N1 runners do not depend on it and are unchanged.

Public construction and validation flow:

1. `build_fixed_action_declaration()` freezes the frame, CS1/CS2 mappings,
   one exact POST, one action identity SHA-256, its DAG predecessor, and its
   workspace-global claim *declaration*.
2. `build_session_contract()` states separately whether a controller fresh
   boot or a physical panel/J2 cycle is required and orders the actions.
3. `seal_campaign_contract()` validates every session/action binding and the
   prior-action DAG, then seals the canonical campaign.
4. `seal_limit_profile()` seals the panel/build allowlist, usage counters,
   numerical limits, validity window, and review evidence. Nullable draft
   values remain auditable, but `evaluate_limit_profile()` fails them closed.
5. `build_result_record()` creates a terminal immutable result in one of
   `PASS`, `FAIL`, `INVALID`, `STOP`, or `UNKNOWN_DO_NOT_RETRY`. A dependent
   action is bound to the canonical whole-file result SHA-256.
6. `describe_action_offline()` and `validate_action_description()` produce
   and validate a zero-I/O plan. Even a fully valid plan retains
   `hardware_ready=false` and `hardware_execution_authorized=false`, because
   current electrical/temperature gates and an exact user authorization are
   runtime facts outside this package.

Run its focused tests with:

```powershell
python -B -m unittest tests.test_visible_refresh_campaign_contract -v
```

The first concrete consumer is the N2P V2 fixed executor in
`tools/g1_s1_rc2g_n2_photo_campaign_once.py`. Its separately sealed
`docs/N2P_RC2G_FIXED_EXECUTION_SUPPLEMENT_V2.json` binds the frozen N2P
compiler/P0 identities to exactly eight CLI-selected actions, the shared
workspace claim registry, and the frozen score/camera contracts. This does
not change the source manifest's `hardware_ready=false`: describe-only stays
fail-closed, and live eligibility additionally requires a reviewed limit
profile, current physical gates, phase-specific prior evidence, and one exact
operator authorization.

N4 V3 uses the same audited execution machinery through
`tools/g1_s1_n4_v3_execution_contract.py` and
`tools/g1_s1_rc2g_n4_v3_once.py`. The shared contract preserves the V3
manifest/proof and all eight P0 action identities while superseding only the
historical per-session final-power-off flag. J2 may remain on between cells;
same-cell MAP-to-target continuity forbids controller reboot, panel power
cycle, J2 disconnect, or another visible refresh. The pure finalized-bundle
validator replays the MAP/target RC2G protocol validators and binds claim,
lock, reviewed profile, observation, finalization, and result whole-file
hashes before the N4 analyzer accepts a cell.

N3 adds a decision-gated exact-plan layer in
`tools/g1_s1_n3_execution_contract.py`. N3A cannot expose the 72-action
planning tree as one executable campaign: `compile_n3a_exact_plan()` first
deep-analyzes all eight N2P finalized bundles, rejects a tie/null winner, and
then selects exactly one manually chosen repeat-2/3/4 template. N3B selects
all four frozen Williams blocks (16 MAP→target routes, 32 actions).
`tools/g1_s1_rc2g_n3_once.py` applies the same global-pre-network claim,
single-POST, no-retry/no-recovery and same-session MAP PASS rules. The N3
analyzer accepts only exact-plan MAP/target deep bundle pairs; loose result or
observation lists are not an input surface.
