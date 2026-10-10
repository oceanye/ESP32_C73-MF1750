#!/usr/bin/env python3
"""Coarsely compare locked T1/W1 with fresh successor T2/W2 evidence.

The exact sealed T1 coarse-screen authority and a fully recomputed successor
T2 coarse screen are compared position by position.  Two models are scored:
endpoint appearance follows the active/commented profile as it swaps sides, or
appearance remains attached to physical CS1/CS2.  PASS/REVIEW/FAIL here labels
camera-relative *candidates only*.  It does not reverse the formal T1 failure,
advance a formal gate, or qualify any colour.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import json
import math
import os
from pathlib import Path
import statistics
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.color import delta_e_ciede2000  # noqa: E402
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t1_t2_profile_comparison as strict,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t2_discovery_successor_pack as successor_pack,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t2_discovery_successor_white_normalized_coarse_screen as t2_screen,
)


SCHEMA_VERSION = 1
KIND = (
    "mf1750-raw-p16-crossover-t1-vs-successor-t2-white-normalized-coarse-comparison-v1"
)
METHOD_ID = "t1-ac-vs-successor-t2-ca-position-level-flat-field-model-screen-v1"
INTEGRITY_ALGORITHM = strict.INTEGRITY_ALGORITHM

MODEL_P95_PASS_DE00 = 8.0
MODEL_P95_REVIEW_DE00 = 12.0
MODEL_DECISION_MARGIN_DE00 = 2.0

PROFILE_FOLLOWING = "PROFILE_FOLLOWING_COARSE_CANDIDATE"
POSITION_FOLLOWING = "POSITION_FOLLOWING_COARSE_CANDIDATE"
INCONCLUSIVE = "PROFILE_VS_POSITION_COARSE_INCONCLUSIVE"


class DiscoveryCoarseComparisonError(RuntimeError):
    """Raised when an input or derived candidate report is not exact."""


def _p95(values: Sequence[float]) -> float:
    if not values:
        raise DiscoveryCoarseComparisonError("cannot calculate P95 of an empty set")
    ordered = sorted(float(value) for value in values)
    position = 0.95 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _model_classification(p95: float) -> str:
    if p95 <= MODEL_P95_PASS_DE00:
        return "PASS"
    if p95 <= MODEL_P95_REVIEW_DE00:
        return "REVIEW"
    return "FAIL"


def _groups(report: Mapping[str, Any]) -> dict[tuple[int, int], Mapping[str, Any]]:
    raw = report.get("group_results")
    if not isinstance(raw, list) or len(raw) != 16:
        raise DiscoveryCoarseComparisonError(
            "coarse screen must contain exactly sixteen controller/code groups"
        )
    result: dict[tuple[int, int], Mapping[str, Any]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            raise DiscoveryCoarseComparisonError("coarse group is not an object")
        key = (item.get("controller"), item.get("code"))
        if (
            key[0] not in (0, 1)
            or key[1] not in range(8)
            or key in result
            or item.get("classification") not in {"PASS", "REVIEW", "FAIL"}
        ):
            raise DiscoveryCoarseComparisonError("coarse group identity differs")
        result[key] = item
    if set(result) != {
        (controller, code) for controller in range(2) for code in range(8)
    }:
        raise DiscoveryCoarseComparisonError("coarse group set differs")
    return result


def _position_labs(group: Mapping[str, Any]) -> dict[tuple[int, int], list[float]]:
    raw = group.get("position_results")
    if not isinstance(raw, list) or len(raw) != 4:
        raise DiscoveryCoarseComparisonError("coarse group must contain four positions")
    result: dict[tuple[int, int], list[float]] = {}
    for item in raw:
        if (
            not isinstance(item, Mapping)
            or item.get("position_eligible") is not True
            or not isinstance(item.get("normalized_lab_median"), list)
            or len(item["normalized_lab_median"]) != 3
        ):
            raise DiscoveryCoarseComparisonError(
                "coarse comparison requires four eligible normalized positions"
            )
        key = (item.get("row"), item.get("column"))
        if key in result:
            raise DiscoveryCoarseComparisonError("duplicate normalized position")
        lab = []
        for value in item["normalized_lab_median"]:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise DiscoveryCoarseComparisonError("normalized Lab is invalid")
            component = float(value)
            if not math.isfinite(component):
                raise DiscoveryCoarseComparisonError("normalized Lab is non-finite")
            lab.append(component)
        result[key] = lab
    return result


def _paired_distances(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> list[float]:
    left = _position_labs(first)
    right = _position_labs(second)
    if set(left) != set(right):
        raise DiscoveryCoarseComparisonError(
            "T1/T2 normalized position identities differ"
        )
    return [
        float(delta_e_ciede2000(left[position], right[position]))
        for position in sorted(left)
    ]


def _code_result(
    code: int,
    t1: Mapping[tuple[int, int], Mapping[str, Any]],
    t2: Mapping[tuple[int, int], Mapping[str, Any]],
) -> dict[str, Any]:
    source_groups = [t1[(0, code)], t1[(1, code)], t2[(0, code)], t2[(1, code)]]
    source_classes = [group["classification"] for group in source_groups]
    profile_distances = [
        *_paired_distances(t1[(0, code)], t2[(1, code)]),
        *_paired_distances(t1[(1, code)], t2[(0, code)]),
    ]
    position_distances = [
        *_paired_distances(t1[(0, code)], t2[(0, code)]),
        *_paired_distances(t1[(1, code)], t2[(1, code)]),
    ]
    profile_p95 = _p95(profile_distances)
    position_p95 = _p95(position_distances)
    profile_class = _model_classification(profile_p95)
    position_class = _model_classification(position_p95)

    if profile_p95 + MODEL_DECISION_MARGIN_DE00 < position_p95:
        judgement = PROFILE_FOLLOWING
        winning_p95 = profile_p95
    elif position_p95 + MODEL_DECISION_MARGIN_DE00 < profile_p95:
        judgement = POSITION_FOLLOWING
        winning_p95 = position_p95
    else:
        judgement = INCONCLUSIVE
        winning_p95 = min(profile_p95, position_p95)

    if "FAIL" in source_classes or winning_p95 > MODEL_P95_REVIEW_DE00:
        classification = "FAIL"
        reason = "SOURCE_GROUP_FAILED_OR_BOTH_MODELS_OUTSIDE_REVIEW"
    elif (
        "REVIEW" in source_classes
        or winning_p95 > MODEL_P95_PASS_DE00
        or judgement == INCONCLUSIVE
    ):
        classification = "REVIEW"
        reason = "MODEL_OR_SOURCE_REQUIRES_COARSE_REVIEW"
    else:
        classification = "PASS"
        reason = "ONE_COARSE_MODEL_DECISIVELY_FITS_WITHIN_PASS_THRESHOLD"

    return {
        "code": code,
        "candidate_classification": classification,
        "diagnostic_reason": reason,
        "coarse_judgement": judgement,
        "source_group_classifications": {
            "t1_cs1_active": source_classes[0],
            "t1_cs2_commented": source_classes[1],
            "t2_cs1_commented": source_classes[2],
            "t2_cs2_active": source_classes[3],
        },
        "profile_following_model": {
            "pairs": [
                "T1_CS1_ACTIVE_TO_T2_CS2_ACTIVE",
                "T1_CS2_COMMENTED_TO_T2_CS1_COMMENTED",
            ],
            "position_delta_e00": [round(value, 9) for value in profile_distances],
            "median_delta_e00": round(statistics.median(profile_distances), 9),
            "p95_delta_e00": round(profile_p95, 9),
            "classification": profile_class,
        },
        "position_following_model": {
            "pairs": ["T1_CS1_TO_T2_CS1", "T1_CS2_TO_T2_CS2"],
            "position_delta_e00": [round(value, 9) for value in position_distances],
            "median_delta_e00": round(statistics.median(position_distances), 9),
            "p95_delta_e00": round(position_p95, 9),
            "classification": position_class,
        },
        "camera_relative_candidate_only": True,
        "qualification_effect": "NONE",
    }


def compare_reports(
    t1_report: Mapping[str, Any], t2_report: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare two already deep-validated coarse-screen records."""

    t1_groups = _groups(t1_report)
    t2_groups = _groups(t2_report)
    results = [_code_result(code, t1_groups, t2_groups) for code in range(8)]
    class_counts = Counter(item["candidate_classification"] for item in results)
    judgement_counts = Counter(item["coarse_judgement"] for item in results)
    if judgement_counts[PROFILE_FOLLOWING] and not judgement_counts[POSITION_FOLLOWING]:
        state = "PROFILE_FOLLOWING_COARSE_CANDIDATES_PRESENT"
    elif (
        judgement_counts[POSITION_FOLLOWING] and not judgement_counts[PROFILE_FOLLOWING]
    ):
        state = "POSITION_FOLLOWING_COARSE_CANDIDATES_PRESENT"
    else:
        state = "MIXED_OR_INCONCLUSIVE_COARSE_CANDIDATES"
    return {
        "code_results": results,
        "summary": {
            "state": state,
            "candidate_classification_counts": {
                name: class_counts[name] for name in ("PASS", "REVIEW", "FAIL")
            },
            "coarse_judgement_counts": {
                name: judgement_counts[name]
                for name in (PROFILE_FOLLOWING, POSITION_FOLLOWING, INCONCLUSIVE)
            },
            "screening_only": True,
            "formal_gate_evaluated": False,
            "formal_gate_changed": False,
            "formal_advance_to_t2_permitted": False,
            "qualified_colour_count": 0,
            "profile_following_proven": False,
            "position_following_proven": False,
        },
    }


def compare(t1_path: Path, t2_path: Path) -> dict[str, Any]:
    """Deep-validate both inputs, compare, bind bytes, and seal one report."""

    try:
        t1_root = successor_pack.validate_coarse_authority(Path(t1_path))
    except successor_pack.DiscoveryPackError as error:
        raise DiscoveryCoarseComparisonError(
            f"locked T1 coarse authority rejected: {error}"
        ) from error
    try:
        t1_payload = strict._read_stable_regular(  # noqa: SLF001
            Path(t1_path), label="T1 coarse authority"
        )
    except strict.CrossoverProfileComparisonError as error:
        raise DiscoveryCoarseComparisonError(str(error)) from error
    try:
        t2_root, t2_payload = t2_screen.validate_report(Path(t2_path))
    except t2_screen.T2CoarseScreenError as error:
        raise DiscoveryCoarseComparisonError(
            f"successor T2 coarse screen rejected: {error}"
        ) from error
    comparison = compare_reports(t1_root, t2_root)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "method_id": METHOD_ID,
        "input_bindings": {
            "locked_t1_w1_coarse_screen": {
                "path": Path(t1_path).resolve().as_posix(),
                "bytes": len(t1_payload),
                "file_sha256": strict.sha256_bytes(t1_payload),
                "canonical_integrity_sha256": t1_root["integrity"]["sha256"],
                "formal_gate_evaluated": False,
                "formal_advance_to_t2_permitted": False,
                "qualified_colour_count": 0,
            },
            "fresh_t2_w2_coarse_screen": {
                "path": Path(t2_path).resolve().as_posix(),
                "bytes": len(t2_payload),
                "file_sha256": strict.sha256_bytes(t2_payload),
                "canonical_integrity_sha256": t2_root["integrity"]["sha256"],
                "formal_gate_evaluated": False,
                "qualified_colour_count": 0,
            },
        },
        "model_contract": {
            "t1_profiles": {"CS1": "active", "CS2": "commented"},
            "t2_profiles": {"CS1": "commented", "CS2": "active"},
            "position_pairs_per_model_per_code": 8,
            "model_metric": "P95_CIEDE2000_OF_MATCHED_NORMALIZED_POSITIONS",
            "model_pass_maximum_de00": MODEL_P95_PASS_DE00,
            "model_review_maximum_de00": MODEL_P95_REVIEW_DE00,
            "decision_margin_de00": MODEL_DECISION_MARGIN_DE00,
            "automatic_threshold_relaxation": False,
        },
        **comparison,
        "evidence_boundaries": {
            "camera_relative_white_normalized_screening_only": True,
            "absolute_colour_proven": False,
            "stable_colour_proven": False,
            "repeatable_colour_proven": False,
            "qualified_new_colour": False,
            "qualified_colour_count": 0,
            "formal_t1_gate_unchanged": True,
            "consumed_t1_state_changed": False,
            "device_io_performed": False,
            "network_accessed": False,
            "camera_accessed": False,
            "serial_or_com_accessed": False,
            "relay_accessed": False,
            "firmware_flashed": False,
            "display_refreshed": False,
        },
        "output_write_contract": "O_EXCL",
    }
    report["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": strict.sha256_bytes(strict.canonical_json(report)),
    }
    return report


def validate_report(path: Path) -> tuple[dict[str, Any], bytes]:
    """Deep-recompute a comparison from its bound coarse-screen sources."""

    try:
        payload, root = strict._load_json(Path(path), label="coarse comparison")  # noqa: SLF001
        strict._verify_integrity(root, label="coarse comparison")  # noqa: SLF001
    except strict.CrossoverProfileComparisonError as error:
        raise DiscoveryCoarseComparisonError(str(error)) from error
    if root.get("schema_version") != SCHEMA_VERSION or root.get("kind") != KIND:
        raise DiscoveryCoarseComparisonError("coarse comparison schema or kind differs")
    bindings = root["input_bindings"]
    recomputed = compare(
        Path(bindings["locked_t1_w1_coarse_screen"]["path"]),
        Path(bindings["fresh_t2_w2_coarse_screen"]["path"]),
    )
    if recomputed != root:
        raise DiscoveryCoarseComparisonError(
            "coarse comparison differs from source-evidence recomputation"
        )
    return root, payload


def _serialize(report: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise DiscoveryCoarseComparisonError(
            f"refusing to overwrite output: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--t1-coarse-screen", type=Path, required=True)
    parser.add_argument("--t2-coarse-screen", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = compare(args.t1_coarse_screen, args.t2_coarse_screen)
        payload = _serialize(report)
        _write_exclusive(args.output, payload)
    except DiscoveryCoarseComparisonError as error:
        print(f"RAW-P16 discovery coarse-comparison error: {error}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(payload)
    return 0 if report["summary"]["candidate_classification_counts"]["FAIL"] == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
