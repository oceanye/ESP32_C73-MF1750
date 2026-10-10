#!/usr/bin/env python3
"""Analyze a blinded physical-slot grouping for the balanced eight-code atlas."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_eightcode_atlas as atlas  # noqa: E402


SCHEMA_VERSION = 1
OBSERVATION_KIND = "mf1750-ec5-eightcode-atlas-blind-slot-observation"
ANALYSIS_KIND = "mf1750-ec5-eightcode-atlas-blind-analysis"
SLOT_IDS = tuple([f"L{index}" for index in range(8)] + [f"R{index}" for index in range(8)])
FORMAL_CODES = (0, 1, 2, 3, 5, 6)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GROUP = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}$")
_TOP_KEYS = {
    "schema_version",
    "kind",
    "layout_id",
    "atlas_action_id",
    "atlas_result_sha256",
    "operator_blinded_to_code_positions",
    "pseudocolor_preview_withheld",
    "slots",
    "supervised_safety",
}
_SLOT_KEYS = {"slot_id", "appearance_group", "uncertain"}
_SAFETY_KEYS = {"electrical_normal", "temperature_c", "esp32_did_not_restart"}


class EightCodeAtlasAnalysisError(ValueError):
    """One blind observation or exact atlas binding is invalid."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EightCodeAtlasAnalysisError("observation is not canonical JSON") from error


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _boolean(value: Any, *, label: str) -> bool:
    if type(value) is not bool:
        raise EightCodeAtlasAnalysisError(f"{label} must be boolean")
    return value


def _hash(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise EightCodeAtlasAnalysisError(f"{label} must be a lowercase SHA-256")
    return value


def _temperature(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EightCodeAtlasAnalysisError("temperature_c must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < -40.0 or result > 100.0:
        raise EightCodeAtlasAnalysisError("temperature_c is outside its finite range")
    return result


def _slot_to_code(slot_id: str) -> int:
    index = int(slot_id[1:])
    return index if slot_id[0] == "L" else 7 - index


def _validate_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise EightCodeAtlasAnalysisError("observation keys differ")
    if value["schema_version"] != SCHEMA_VERSION or value["kind"] != OBSERVATION_KIND:
        raise EightCodeAtlasAnalysisError("observation identity differs")
    if value["layout_id"] != atlas.LAYOUT_ID:
        raise EightCodeAtlasAnalysisError("atlas layout differs")
    _hash(value["atlas_action_id"], label="atlas_action_id")
    _hash(value["atlas_result_sha256"], label="atlas_result_sha256")
    if not _boolean(
        value["operator_blinded_to_code_positions"],
        label="operator_blinded_to_code_positions",
    ):
        raise EightCodeAtlasAnalysisError("operator was not blinded to code positions")
    if not _boolean(
        value["pseudocolor_preview_withheld"],
        label="pseudocolor_preview_withheld",
    ):
        raise EightCodeAtlasAnalysisError("pseudocolor preview was not withheld")
    slots = value["slots"]
    if not isinstance(slots, list) or len(slots) != 16:
        raise EightCodeAtlasAnalysisError("exactly sixteen physical slot observations are required")
    indexed: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(slots):
        if not isinstance(raw, Mapping) or set(raw) != _SLOT_KEYS:
            raise EightCodeAtlasAnalysisError(f"slot {index} keys differ")
        slot_id = raw["slot_id"]
        if slot_id not in SLOT_IDS or slot_id in indexed:
            raise EightCodeAtlasAnalysisError("slot IDs must be unique L0..L7/R0..R7")
        uncertain = _boolean(raw["uncertain"], label=f"{slot_id}.uncertain")
        group = raw["appearance_group"]
        if uncertain:
            if group is not None:
                raise EightCodeAtlasAnalysisError(
                    f"{slot_id} uncertain observation must have null group"
                )
        elif not isinstance(group, str) or _GROUP.fullmatch(group) is None:
            raise EightCodeAtlasAnalysisError(
                f"{slot_id} appearance_group is invalid"
            )
        indexed[slot_id] = {
            "slot_id": slot_id,
            "appearance_group": group,
            "uncertain": uncertain,
            "code": _slot_to_code(slot_id),
        }
    if set(indexed) != set(SLOT_IDS):
        raise EightCodeAtlasAnalysisError("physical slot coverage differs")
    safety = value["supervised_safety"]
    if not isinstance(safety, Mapping) or set(safety) != _SAFETY_KEYS:
        raise EightCodeAtlasAnalysisError("supervised safety keys differ")
    _boolean(safety["electrical_normal"], label="electrical_normal")
    _temperature(safety["temperature_c"])
    _boolean(safety["esp32_did_not_restart"], label="esp32_did_not_restart")
    return {"root": value, "slots": indexed, "safety": safety}


def analyze_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Decode physical slots only after validating that the report was blind."""

    validated = _validate_observation(value)
    slots = validated["slots"]
    per_code: dict[str, dict[str, Any]] = {}
    mismatched: list[int] = []
    uncertain_codes: list[int] = []
    for code in range(8):
        left = slots[f"L{code}"]
        right = slots[f"R{7 - code}"]
        if left["uncertain"] or right["uncertain"]:
            uncertain_codes.append(code)
            consistent = False
            group = None
        else:
            consistent = left["appearance_group"] == right["appearance_group"]
            group = left["appearance_group"] if consistent else None
            if not consistent:
                mismatched.append(code)
        per_code[f"0x{code:x}"] = {
            "left_slot": left["slot_id"],
            "right_slot": right["slot_id"],
            "left_group": left["appearance_group"],
            "right_group": right["appearance_group"],
            "cross_controller_consistent": consistent,
            "decoded_group": group,
        }
    conclusive = not mismatched and not uncertain_codes
    alias_clusters: list[dict[str, Any]] = []
    distinct_count: int | None = None
    u04_distinct_u05: bool | None = None
    u07_distinct_formal: bool | None = None
    if conclusive:
        grouped: dict[str, list[int]] = {}
        for code in range(8):
            group = per_code[f"0x{code:x}"]["decoded_group"]
            assert isinstance(group, str)
            grouped.setdefault(group, []).append(code)
        distinct_count = len(grouped)
        alias_clusters = [
            {"appearance_group": group, "codes": codes, "is_alias_cluster": len(codes) > 1}
            for group, codes in sorted(grouped.items())
        ]
        group4 = per_code["0x4"]["decoded_group"]
        group5 = per_code["0x5"]["decoded_group"]
        group7 = per_code["0x7"]["decoded_group"]
        u04_distinct_u05 = group4 != group5
        u07_distinct_formal = all(
            group7 != per_code[f"0x{code:x}"]["decoded_group"]
            for code in FORMAL_CODES
        )
    safety_pass = (
        validated["safety"]["electrical_normal"] is True
        and validated["safety"]["esp32_did_not_restart"] is True
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "layout_id": atlas.LAYOUT_ID,
        "atlas_action_id": value["atlas_action_id"],
        "atlas_result_sha256": value["atlas_result_sha256"],
        "observation_canonical_sha256": _sha(_canonical(value)),
        "conclusive_cross_controller_grouping": conclusive,
        "mismatched_codes": mismatched,
        "uncertain_codes": uncertain_codes,
        "per_code": per_code,
        "alias_clusters": alias_clusters,
        "visually_distinct_direct_state_count": distinct_count,
        "u04_distinct_from_u05": u04_distinct_u05,
        "u07_distinct_from_all_formal_codes": u07_distinct_formal,
        "supervised_safety_pass": safety_pass,
        "classification": (
            "BLIND_DIRECT_STATE_GROUPING_COMPLETE"
            if conclusive and safety_pass
            else "INCONCLUSIVE_OR_SAFETY_INCOMPLETE"
        ),
        "formal_color_qualification": False,
        "optical_measurement_performed": False,
        "hardware_io_performed_by_analyzer": False,
        "visible_refresh_authorized": False,
    }
    result["integrity"] = {
        "canonical_sha256": _sha(_canonical(result)),
    }
    return result


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EightCodeAtlasAnalysisError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load(path: Path) -> Mapping[str, Any]:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise EightCodeAtlasAnalysisError("observation must be a regular file")
        if before.st_size <= 0 or before.st_size > 4 * 1024 * 1024:
            raise EightCodeAtlasAnalysisError("observation size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise EightCodeAtlasAnalysisError(f"could not read observation: {error}") from error
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise EightCodeAtlasAnalysisError("observation changed while read")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=lambda token: (_ for _ in ()).throw(
                EightCodeAtlasAnalysisError(f"forbidden JSON constant {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EightCodeAtlasAnalysisError("observation is invalid JSON") from error
    if not isinstance(value, Mapping):
        raise EightCodeAtlasAnalysisError("observation top level must be an object")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--observation", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = analyze_observation(_load(args.observation))
    except EightCodeAtlasAnalysisError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
