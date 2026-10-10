"""Tests for the XOR-3 mechanism analysis: permutation-fit helper on synthetic
data, vendor table parsing/hash pins, and key assertions on the sealed analysis
output (per-frame robustness, side consistency, geometry rejection, static LUT)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from tools import mf1750_lh2_xor3_analysis as xa
from tools.mf1750_lh1_lh4_once import canonical, digest

OUT = Path(".test-output/offline/LH2_XOR3_MECHANISM_20260918_V1/xor3-analysis.json")
XOR3 = [3, 2, 1, 0, 7, 6, 5, 4]


def test_best_permutation_recovers_xor3():
    rng = np.random.default_rng(3)
    ref = rng.normal(size=(8, 3)) * 20
    errors = np.array([[np.linalg.norm(ref[c] - ref[j]) for j in range(8)]
                       for c in range(8)])
    perm, _ = xa.best_permutation(errors)
    assert list(perm) == list(range(8))
    # permute the reference by XOR-3: observed c matches ref[c^3]
    errors2 = np.array([[np.linalg.norm(ref[c ^ 3] - ref[j]) for j in range(8)]
                        for c in range(8)])
    perm2, _ = xa.best_permutation(errors2)
    assert list(perm2) == XOR3


def test_vendor_tables_parse_and_hash_pinned():
    vendor = xa.parse_vendor_tables(xa.VENDOR_SOURCE)
    assert len(vendor["active"]) == xa.TRANSMITTED == 535
    assert len(vendor["commented"]) == 535
    assert digest(vendor["active"]) == \
        "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
    assert digest(vendor["commented"]) == \
        "2cf66c2b5aa3533240e87190ef0abd7200a182f920494121bdaf2b5d30bbfd26"
    rows = xa.group_rows(vendor["commented"])
    assert len(rows) == 6 and all(len(r) == 8 for r in rows)
    assert all(len(g) == 11 for r in rows for g in r)


def test_sealed_analysis_output():
    doc = json.loads(OUT.read_text(encoding="utf-8"))
    claim = doc["integrity"]["sha256"]
    body = {k: v for k, v in doc.items() if k != "integrity"}
    assert digest(canonical(body)) == claim, "seal mismatch"

    assert doc["xor3_permutation"] == XOR3
    rob = doc["per_frame_robustness"]
    assert rob["every_frame_best_is_xor3"] is True
    assert rob["frames"] == 10 and rob["pair_count"] == 160
    assert rob["delta_e00"]["max"] < 3.0
    assert rob["identity_permutation_total_delta_e76_median"] > \
        10 * rob["xor3_total_delta_e76_median"]

    geo = doc["geometry_hypothesis"]
    assert geo["any_candidate_explains"] is False
    assert len(geo["candidate_relabelings"]) == 16  # 8 candidates x 2 controllers

    fits = doc["row_permutation_fits"]
    m7 = [f for f in fits if f["history"] == 7]
    assert all(f["best_is_xor3"] and f["best_mean_delta_e76"] < 1.5 for f in m7)
    colored = [f for f in fits if f["history"] != 7]
    assert all(f["identity_mean_delta_e76"] > 15 for f in colored)
    assert all(f["xor3_mean_delta_e76"] < f["identity_mean_delta_e76"] / 3
               for f in colored)

    sc = doc["side_consistency"]
    assert sc["xor3_direction_same_both_sides"] is True
    assert sc["CS1"]["max_delta_e00"] < 3.0 and sc["CS2"]["max_delta_e00"] < 3.0

    static = doc["static_lut_evidence"]
    assert static["matches_pinned_hashes"] == {"active": True, "commented": True}
    assert static["matches_generated_inc"] == {"active": True, "commented": True}
    assert static["same_category_order"] is True
    assert static["active_vs_commented_same_index_equal_blocks"]["equal"] == 0
    assert static["within_table_group_symmetry"]["commented"]["xor3"]["equal_blocks"] == 0
    assert doc["qualified_count"] == 0
