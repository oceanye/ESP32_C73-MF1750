# MF1750 Same-R20 AA-abort White V1B Successor Record

Date: 2026-08-28  
Status: V1B diagnostic **PASS**; the single original V1 factory-OTP-white action **complete_pass**; action permanently consumed; relay command/query state returned to **OFF**.

## Outcome

The V1 firmware was not rebuilt, reflashed, or reset for this successor. The first diagnostic failure is retained unchanged. A manually started host-only V1B diagnostic repaired only the one proven malformed JSON byte sequence in transport, applied every original V1 identity/state validator, and wrote a new immutable four-GET receipt.

That successor diagnostic and the action used the same boot nonce, `93d389c6f5323145`. The action then completed one ARM, one EXECUTE, one driver call, and one visible refresh. It must not be retried.

The action driver report records:

- `total_ms=35013`
- `PON=180 ms`
- `DRF=22520 ms`
- `POF=140 ms`
- CS1/CS2 upload `2444/2444 ms`
- `sequence_ok=true`
- no wait timeout and no missing BUSY assertion

This record does not itself claim camera- or human-confirmed clean white. It records the controller/driver completion and host evidence chain only.

## Root cause and narrow repair

The exact bound BIN contains the malformed marker once and the corrected marker zero times:

```text
bad  (80 bytes): "relay_off_receipt_is_command_query_not_load_voltage_proof":true","profile_id":"
good (79 bytes): "relay_off_receipt_is_command_query_not_load_voltage_proof":true,"profile_id":"
```

The V1B requester accepts a response only when the bad marker occurs exactly once and the good marker occurs zero times. It replaces that one occurrence, decodes UTF-8 JSON, and then runs all original validators. Zero markers, multiple markers, a pre-existing good marker, non-UTF-8 data, or any remaining JSON error fails closed.

Every accepted response records raw byte length, raw SHA-256, raw base64, marker offset, normalized length/SHA-256, and HTTP content type/length. Offline replay verified all four diagnostic responses and all seven action responses, including ARM, EXECUTE, and the terminal report.

## Immutable evidence

| Evidence | SHA-256 | Result |
|---|---|---|
| Original app-only flash | `e16ce55791a55a06f951003dcda1cec750b71721ef991a589009b3bfbf2a0a4d` | pass |
| Preserved first V1 diagnostic | `d7905bbe3099b2b9ffd755afc4f200a2c29ac213045c0ef5a8d511ac8337bb05` | failed, 1 GET / 0 POST / 0 claim / 0 refresh |
| V1B successor diagnostic | `6ee4085ac0dff49804d98bdec956ad515fac2a50602053bff50756e4747676ef` | pass, 4 GET / 0 POST / 0 claim / 0 refresh |
| Permanent original V1 claim | `240a371a34186d7879605a9a892ef4f47b771187df4f5d234371b2201129d340` | permanently consumed |
| Original V1 action output | `57785a566bccf35a1f404d4e01e5bf9f107df906c3a8f193009d21ee52c66cb7` | complete_pass, 5 GET / 2 POST / 1 refresh |
| Post-action relay OFF query | `bebe90b9831f201c11efc4e5d8acdcb32f7691286a9e60a3e8de3b605b829679` | commanded OFF; not electrical proof |

The full machine-readable paths, byte counts, canonical-integrity hashes, validation results, and evidence boundaries are in [MF1750_SAME_R20_AA_ABORT_WHITE_V1B_OFFLINE_AND_LIVE_MANIFEST_2026-08-28.json](MF1750_SAME_R20_AA_ABORT_WHITE_V1B_OFFLINE_AND_LIVE_MANIFEST_2026-08-28.json).

## Final host code

- `tools/mf1750_same_r20_aa_abort_white_v1b_successor_pack.py`
- `tools/mf1750_same_r20_aa_abort_white_v1b_successor_once.py`
- `tests/test_mf1750_same_r20_aa_abort_white_v1b_successor.py`

Validation after the final fail-closed hardening:

- focused tests: `14 passed`
- V1B + original V1 + app-flash regression: `38 passed`
- Ruff check: pass
- Ruff format check: pass
- Python compile: pass
- live raw-evidence replay: diagnostic `4/4`, action `7/7`

The live CLI used the strict default requester. The final source additionally rejects raw-evidence-free requesters injected through the Python API. The final source hash was not separately sealed at live invocation, so this record does not falsely claim that the final post-run source bytes are the exact executed host bytes.

## Lineage and boundaries

The action output uses the original V1 result schema and therefore does not directly contain the V1B successor ID. Its V1B lineage is established by all of the following together:

1. the fixed V1B O_EXCL diagnostic path;
2. the fixed original V1 action and shared permanent-claim paths;
3. the same boot nonce in diagnostic and action;
4. exact firmware, ELF, contract, descriptor, action, and source bindings;
5. replay-valid raw-response evidence in both transcripts.

The relay receipts prove command/query state only. They do not prove load-side voltage or current. The action is permanently claimed, so no retry, recovery, or automatic chaining is permitted.
