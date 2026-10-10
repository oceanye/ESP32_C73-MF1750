# MF1750 RAW-P16 T1/T2 offline comparator

Date: 2026-08-30  
Status: offline implementation complete; no live or colour-qualification result is claimed.

## Purpose and boundary

`tools/mf1750_raw_p16_crossover_t1_t2_profile_comparison.py` provides two
strict offline operations. First, it seals the mandatory three-frame T1-only
position/temporal preflight that always requires W1 safety containment and
either permits or blocks subsequent T2. Second, after
T2 exists, it compares exactly three new T1 AC and three new T2 CA single-frame
analysis JSON files. The comparison tests whether the camera-relative
appearance for each transport code follows the active/commented waveform
profile as that profile swaps controllers, remains attached to physical
CS1/CS2, or is inconclusive.

The comparator performs no camera, device, network, COM, relay, flash, reset,
J2, or display operation. Its strongest positive result is
`PROFILE_FOLLOWING_CANDIDATE`; it never claims an absolute colour, a stable or
repeatable new colour, or a qualified palette entry.

## Strict input contract

Each file must have:

- `schema_version = 1` and kind
  `mf1750-raw-p16-crossover-position-balanced-single-frame-analysis-v1`;
- a canonical-integrity-covered `comparison_projection` with exactly the T1
  or T2 stage, campaign, contract, action, packed-frame SHA-256, and both
  controller DTM SHA-256 bindings from the fresh crossover pack;
- the reviewed same-R20 V2 4x8 row-code matrix, four positions per code per
  controller, and identical DTM layout declaration in that projection;
- admitted current-photo geometry: one shared canonical camera-lock ID,
  nonsingular 3x3 homography, panel area at least 0.08 of the photo, projected
  cell side at least 20 px, all cells inside the photo, no historical G1
  homography reuse, and an explicit statement that automatic cell-lattice
  reprojection is not proven;
- codes 0 through 7 in order, CS1 and CS2 in order, the exact profile for the
  stage, four exact row/column positions, camera-relative Lab samples, and
  center/dispersion statistics that recompute exactly from those samples;
- rich source/action/camera/cell evidence consistent with the projection, an
  analyzer safety boundary that records no hardware or camera I/O, and a valid
  canonical SHA-256 integrity seal using
  `sha256-canonical-json-without-integrity`.

The six input paths and six raw file SHA-256 values must all be distinct. T1
and T2 must use the same camera-lock ID. Old mixed-R20 4x2 gallery analyses are
not accepted.

## Decision model

Codes are computed independently. Review priority is `3,5,6,7`, then guard
code `4`, then controls `0,1,2`.

For each stage/controller/code, the comparator takes the median of each fixed
position over three frames and then the component-wise median across four
positions. It also calculates within-position and between-frame dispersion.
Any position or temporal consistency maximum above the fixed
`6.603186815816113` Delta-E76 tolerance yields `INCONCLUSIVE`.

For consistent inputs it compares:

- T1-CS1(active) against T2-CS2(active), and T1-CS2(commented) against
  T2-CS1(commented): the profile-following model;
- T1-CS1 against T2-CS1, and T1-CS2 against T2-CS2: the fixed-side model;
- the corresponding A-minus-C and left-minus-right Lab-vector agreement.

A model is only a candidate when its paired distances and vector disagreement
are within the consistency tolerance, while both stage separations and the
opposing model distances exceed twice the effective tolerance. All other
patterns remain `INCONCLUSIVE` with a diagnostic reason.

## Mandatory T1-only admission gate

This command consumes exactly three distinct T1 analysis records. The current
corrected schema emits version 2 and kind
`mf1750-raw-p16-crossover-position-balanced-t1-position-temporal-preflight-v2`.
Every one of the 16 controller/code groups must pass the fixed position and
temporal tolerance. The only passing state is
`PASS_T1_POSITION_TEMPORAL_PREFLIGHT` with
`advance_to_t2_permitted=true`. In both PASS and FAIL reports,
`w1_containment_required=true`: the white safety containment is never blocked.
A failed gate is still sealed to the requested output, returns process status
3, uses reason `POSITION_DEPENDENT_INCONCLUSIVE`, and forbids T2 only.

```powershell
python -B tools/mf1750_raw_p16_crossover_t1_t2_profile_comparison.py `
  --t1-analysis T1-frame-01.analysis.json T1-frame-02.analysis.json T1-frame-03.analysis.json `
  --t1-only-preflight `
  --supersedes-preflight T1.position-temporal-preflight.json `
  --output T1.position-temporal-preflight-v2.json
```

The T1-only report does not classify profile-following or side-following and
does not claim a colour. When `--supersedes-preflight` is supplied, the v2
report verifies the old v1 record's canonical integrity and exact T1 input
bindings, then records `supersedes_source_path`, `supersedes_file_sha256`, and
`supersedes_canonical_integrity_sha256`. The old O_EXCL file remains immutable.

## T1/T2 comparison invocation

The output parent directory must already exist. The output is immutable and
created once with `O_EXCL`:

```powershell
python -B tools/mf1750_raw_p16_crossover_t1_t2_profile_comparison.py `
  --t1-analysis T1-frame-01.analysis.json T1-frame-02.analysis.json T1-frame-03.analysis.json `
  --t2-analysis T2-frame-01.analysis.json T2-frame-02.analysis.json T2-frame-03.analysis.json `
  --output T1-vs-T2.profile-comparison.json
```

The comparison output kind is
`mf1750-raw-p16-crossover-t1-t2-profile-comparison-v1`. It embeds the raw file
SHA-256, canonical integrity SHA-256, and source-evidence SHA-256 values of all
six inputs, per-code controller statistics and model metrics, strict candidate
classifications, evidence boundaries, `output_write_contract=O_EXCL`, and its
own canonical integrity seal. Both modes refuse to overwrite an existing
output.

## Offline verification

On 2026-08-30 the analyzer/comparator joint suite passed 25 tests after the
canonical `comparison_projection` integration. Ruff check and Ruff format
check passed for both implementations and both focused test modules. No
hardware, camera, network, COM, relay, flash, or display operation was used.

## Current T1 three-frame preflight result

The three sealed T1 analyses under
`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T1_AC_20260830_V1/` were read
offline through the formal preflight. Identity, integrity, geometry admission,
camera lock, exact action/DTM binding, and distinct-input checks passed, but the
position/temporal admission gate failed. Therefore
`w1_containment_required=true`, `advance_to_t2_permitted=false`, and the reason
is `POSITION_DEPENDENT_INCONCLUSIVE`. W1 remains required; only T2 is blocked
by these three records.

The five failed controller/code groups, against the fixed
`6.603186815816113` Delta-E76 tolerance, are:

| controller | code | consistency maximum Delta-E76 |
| --- | ---: | ---: |
| CS1 | 1 | 7.158026 |
| CS1 | 2 | 8.963159 |
| CS1 | 3 | 27.224901 |
| CS2 | 3 | 6.655854 |
| CS2 | 5 | 7.393698 |

Their temporal P95 values are only 0 to 0.384 Delta-E76; the failure is driven
by four-position dispersion rather than capture-to-capture drift. The original
v1 O_EXCL report is
`.test-output/hardware/MF1750_RAW_P16_CROSSOVER_T1_AC_20260830_V1/T1.position-temporal-preflight.json`:

- file SHA-256:
  `15cde97b902f9f1b123a898d18f85e0457b459e4c71a184a2ecba21fc2cb3d66`;
- canonical integrity SHA-256:
  `9028712905bda075d046f3fa67b066f29088777d4c6cdd0f17735a266ba364d9`;
- expected process status: `3`, meaning a sealed gate failure rather than an
  input-validation or write error.

That v1 file is retained only as superseded audit evidence because its combined
W1/T2 permission field had incorrect containment semantics. The corrected
report is written separately as `T1.position-temporal-preflight-v2.json`. It
binds the v1 source path, file SHA-256, and canonical integrity SHA-256; states
`w1_containment_required=true`; states `advance_to_t2_permitted=false`; and
gives reason `POSITION_DEPENDENT_INCONCLUSIVE`. The v1 artifact is never
overwritten. The corrected v2 report has:

- file SHA-256:
  `18856952b913768cc4c946daae1039ac37096ac5f0baa0b360bf48921c0aebc4`;
- canonical integrity SHA-256:
  `619efdec2af37254a2a183a6212b96ec32b4733efa35e9236ff28b9872bc0005`;
- `supersedes_file_sha256`:
  `15cde97b902f9f1b123a898d18f85e0457b459e4c71a184a2ecba21fc2cb3d66`;
- expected process status: `3`, because T2 remains blocked while W1 remains
  required.

This result is camera-relative and does not establish colour instability by
itself. It requires geometry/position-effect review or replacement T1 captures
before the T1/T2 profile-swap comparator may be used.
