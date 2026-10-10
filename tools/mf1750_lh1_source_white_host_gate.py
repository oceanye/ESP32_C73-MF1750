#!/usr/bin/env python3
"""Offline host admission gate for one LH1 SOURCE-white terminal record.

The gate parses a candidate terminal report; it performs no device, network, or
relay I/O.  Only an exact contract-bound SOURCE ordinal 1 COMPLETE is accepted.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

OLD_LH4_ACTION = "677c37c9962f507e2110f644735c1a1c4be87286073b70d1babe8d42856e3b19"
OLD_LH4_CONTRACT = "bd58d575e4f56d7d77602716446d00cf1501c83021f209406d233071525234d3"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical(v: dict[str, Any]) -> bytes:
    return json.dumps(
        {k: x for k, x in v.items() if k != "integrity"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def _read(path: Path) -> tuple[bytes, dict[str, Any]]:
    b = path.read_bytes()
    d = json.loads(b.decode("utf-8-sig"))
    if not isinstance(d, dict):
        raise ValueError(f"{path}: JSON root must be object")
    i = d.get("integrity")
    if isinstance(i, dict) and i.get("sha256") and i["sha256"] != _sha(_canonical(d)):
        raise ValueError(f"{path}: integrity mismatch")
    return b, d


def _get(d: dict[str, Any], *keys: str):
    for k in keys:
        if k in d:
            return d[k]
    return None


def _ref(path: Path, b: bytes, d: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path).replace("\\", "/"),
        "bytes": len(b),
        "file_sha256": _sha(b),
        "canonical_sha256": _sha(_canonical(d)),
    }


def evaluate(contract_path: Path, candidate_path: Path) -> dict[str, Any]:
    cb, c = _read(contract_path)
    tb, t = _read(candidate_path)
    failures = []
    expected_action = c.get("action_id")
    expected_desc = c.get("descriptor_id")
    expected_profile = c.get("profile_id")
    if not all(
        isinstance(x, str) and x
        for x in (expected_action, expected_desc, expected_profile)
    ):
        failures.append("contract missing action_id/descriptor_id/profile_id")

    def eq(label, actual, expected):
        if actual != expected:
            failures.append(f"{label} mismatch: expected {expected!r}, got {actual!r}")

    eq("action_id", _get(t, "action_id"), expected_action)
    eq("descriptor_id", _get(t, "descriptor_id"), expected_desc)
    eq("profile_id", _get(t, "profile_id", "profile"), expected_profile)
    eq("source_state", _get(t, "source_state"), "FRESH_P2_FACTORY_WHITE")
    eq("target_state", _get(t, "target_state"), "LH1_SOURCE")
    eq("terminal_state", _get(t, "terminal_state", "state"), "COMPLETE")
    if _get(t, "result") is not True:
        failures.append("result is not true")
    if _get(t, "driver_call_count_for_action") != 1:
        failures.append("driver_call_count_for_action is not 1")
    if _get(t, "total_driver_call_count") != 1:
        failures.append("total_driver_call_count is not 1")
    if _get(t, "next_ordinal") != 2:
        failures.append("next_ordinal is not 2")
    boot = _get(t, "boot_nonce")
    if not isinstance(boot, str) or not boot:
        failures.append("boot_nonce missing")
    cursor = _get(t, "cursor", "complete_cursor")
    nvs = t.get("nvs") if isinstance(t.get("nvs"), dict) else {}
    if cursor is None:
        cursor = _get(nvs, "cursor", "complete_cursor")
    if cursor != 2:
        failures.append(f"cursor mismatch: expected 2, got {cursor!r}")
    if _get(t, "campaign_complete") is False:
        failures.append("campaign_complete is false")
    for key in ("action_id", "descriptor_id", "contract_id"):
        if _get(t, key) in {OLD_LH4_ACTION, OLD_LH4_CONTRACT}:
            failures.append("old LH4 claim identity reused")
    if _get(t, "contract_id") not in (None, c.get("contract_id")):
        failures.append("candidate contract_id differs from package")
    result = "PASS" if not failures else "FAIL_STOP"
    return {
        "schema_version": 1,
        "kind": "mf1750-lh1-source-white-host-review",
        "scope": "OFFLINE_READ_ONLY_HOST_GATE",
        "hardware_accessed": False,
        "network_accessed": False,
        "result": result,
        "live_ready": False,
        "qualified_count": 0,
        "contract": _ref(contract_path, cb, c),
        "candidate": _ref(candidate_path, tb, t),
        "checks": {
            "exact_package_action": not any("action_id" in x for x in failures),
            "exact_source_terminal": not any(
                x.startswith(("source_state", "target_state", "terminal_state"))
                for x in failures
            ),
            "complete_result": not any(
                x in failures for x in ("result is not true", "next_ordinal is not 2")
            ),
            "driver_count_one": not any("driver_call_count" in x for x in failures),
            "boot_bound": not any("boot_nonce" in x for x in failures),
            "cursor_complete_2": not any("cursor mismatch" in x for x in failures),
            "old_lh4_rejected": not any("old LH4" in x for x in failures),
        },
        "failures": failures,
        "evidence_boundary": "PASS means parser-level admission only. It does not prove hardware, optical, electrical, or live firmware behavior.",
    }


def write_review(path: Path, review: dict[str, Any]) -> dict[str, Any]:
    review = {
        **review,
        "integrity": {
            "algorithm": "sha256-canonical-json-without-integrity",
            "sha256": _sha(_canonical(review)),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as e:
        raise ValueError(f"output exists (O_EXCL): {path}") from e
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(review, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    return review


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True, type=Path)
    ap.add_argument("--candidate", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ns = ap.parse_args()
    try:
        r = write_review(ns.output, evaluate(ns.contract, ns.candidate))
        return 0 if r["result"] == "PASS" else 2
    except (OSError, ValueError, json.JSONDecodeError) as e:
        ap.error(str(e))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
