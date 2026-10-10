#!/usr/bin/env python3
"""Deeply analyze the exact five-result physical N7 SPI sweep."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Optional, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.visible_refresh_campaign import (  # noqa: E402
    ResultState,
    canonical_json_bytes,
)
from host.visible_refresh_campaign import production_profile as production  # noqa: E402
from tools import mf1750_n7_physical_once as runner  # noqa: E402
from tools import mf1750_n7_spi_sweep_campaign as frozen  # noqa: E402


SCHEMA_VERSION = 1
KIND = "mf1750-n7-physical-sweep-analysis"
HASH_SCOPE = (
    "entire N7 physical sweep analysis excluding integrity; UTF-8 JSON with "
    "sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)


class N7PhysicalAnalyzerError(ValueError):
    """The exact five-action physical N7 evidence set failed closed."""


def _sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return hashlib.sha256(payload).hexdigest()


def _load(
    result_dir: Path, *, reviewer_key_file: Path
) -> Mapping[str, Any]:
    try:
        runner.validate_physical_result(
            result_dir, reviewer_key_file=reviewer_key_file, require_finalized=True
        )
        return runner._validate_result_directory(
            result_dir, reviewer_key_file=reviewer_key_file, require_finalized=True
        )
    except runner.N7PhysicalOnceError as error:
        raise N7PhysicalAnalyzerError(
            f"N7 physical result {result_dir} failed deep validation: {error}"
        ) from error


def _authority_lineage(context: runner._Context) -> dict[str, Any]:
    """Return stable controls while allowing per-action validity envelopes.

    Each action is approved after its real usage snapshot exists.  The
    supervised policy file therefore has a fresh validity envelope and whole-
    file hash for every action.  The campaign lineage is the common issuer,
    panel, safety controls, limits, and field provenance -- never merely a
    self-asserted policy identifier or one copied file hash.
    """

    authority = context.production.inputs.limit_authority
    if authority.get("kind") != production.SUPERVISED_EXPERIMENTAL_PROCESS_POLICY_KIND:
        raise N7PhysicalAnalyzerError(
            "N7 physical sweep requires supervised experimental process authority"
        )
    return {
        "kind": authority["kind"],
        "classification": context.production.report[
            "limit_authority_classification"
        ],
        "issuer": authority["issuer"],
        "panel_model": authority["panel_model"],
        "not_a_supplier_rating": authority["not_a_supplier_rating"],
        "supervised_only": authority["supervised_only"],
        "automatic_execution": authority["automatic_execution"],
        "automatic_retry": authority["automatic_retry"],
        "automatic_recovery": authority["automatic_recovery"],
        "maximum_usage_snapshot_age_seconds": authority[
            "maximum_usage_snapshot_age_seconds"
        ],
        "limits": authority["limits"],
        "field_provenance": authority["field_provenance"],
    }


def analyze_physical_sweep(
    result_directories: Sequence[Path], *, reviewer_key_file: Path
) -> dict[str, Any]:
    """Analyze exactly one complete ordered 1/2/4/8/10 MHz campaign."""

    if (
        not isinstance(result_directories, Sequence)
        or isinstance(result_directories, (str, bytes))
        or len(result_directories) != len(frozen.FREQUENCIES)
        or any(not isinstance(path, Path) for path in result_directories)
    ):
        raise N7PhysicalAnalyzerError("exactly five pathlib result directories are required")
    stored = [
        _load(path, reviewer_key_file=reviewer_key_file)
        for path in result_directories
    ]
    if [item["frequency_hz"] for item in stored] != list(frozen.FREQUENCIES):
        raise N7PhysicalAnalyzerError("N7 results are not in exact frequency order")
    first = stored[0]["context"]
    authority_lineage = _authority_lineage(first)
    reviewer_id = first.production.profile["review"]["reviewer_id"]
    action_ids: set[str] = set()
    claim_files: set[str] = set()
    attempts: set[str] = set()
    result_files: set[str] = set()
    rows: list[dict[str, Any]] = []
    prior: Optional[Mapping[str, Any]] = None
    for index, item in enumerate(stored):
        context = item["context"]
        live = item["live"]
        final = item["final"]
        result = item["result"]
        if (
            context.manifest != first.manifest
            or context.campaign != first.campaign
            or context.campaign["panel"] != first.campaign["panel"]
            or context.campaign["firmware"] != first.campaign["firmware"]
            or _authority_lineage(context) != authority_lineage
            or context.production.reviewer_key_id != first.production.reviewer_key_id
            or context.production.profile["review"]["reviewer_id"] != reviewer_id
            or result["state"] != ResultState.PASS.value
            or final["outcome"] != "PASS"
        ):
            raise N7PhysicalAnalyzerError(
                "N7 physical results differ in lineage or contain a non-PASS action"
            )
        action_sha = str(context.action["action_identity_sha256"])
        claim_filename = str(live["claim"]["filename"])
        attempt_id = str(live["attempt_id"])
        result_sha = item["result_snapshot"].sha256
        if (
            action_sha in action_ids
            or claim_filename in claim_files
            or attempt_id in attempts
            or result_sha in result_files
        ):
            raise N7PhysicalAnalyzerError("N7 action/claim/attempt/result was replayed")
        action_ids.add(action_sha)
        claim_files.add(claim_filename)
        attempts.add(attempt_id)
        result_files.add(result_sha)
        usage = context.production.profile["usage"]
        if usage["session_visible_refresh_count"] != 0 or usage[
            "consecutive_visible_refresh_count"
        ] != 0:
            raise N7PhysicalAnalyzerError(
                "driver-cold N7 action profile must begin at session/consecutive count zero"
            )
        if prior is not None:
            prior_usage = prior["context"].production.profile["usage"]
            if (
                usage["cumulative_visible_refresh_count"]
                != prior_usage["cumulative_visible_refresh_count"] + 1
                or usage["last_visible_refresh_completed_at"]
                != prior["live"]["protocol_completed_at"]
                or live["predecessor_final_file_sha256"]
                != prior["final_snapshot"].sha256
                or live["predecessor_result_file_sha256"]
                != prior["result_snapshot"].sha256
            ):
                raise N7PhysicalAnalyzerError("N7 global usage/predecessor chain is discontinuous")
        analysis_rows = [
            value
            for value in final["analysis"]["results"]
            if value["spi_hz"] == item["frequency_hz"]
        ]
        if len(analysis_rows) != 1 or analysis_rows[0]["status"] != "PASS":
            raise N7PhysicalAnalyzerError("N7 final analyzer row is not PASS")
        diagnostic = live["protocol"]["target_diagnostic"]
        row = {
            "ordinal": index + 1,
            "frequency_hz": item["frequency_hz"],
            "action_identity_sha256": action_sha,
            "result_file_sha256": result_sha,
            "profile_file_sha256": context.production.profile_file.sha256,
            "limit_authority_file_sha256": (
                context.production.inputs.limit_authority_file.sha256
            ),
            "limit_authority_policy_id": context.production.inputs.limit_authority[
                "policy_id"
            ],
            "usage_evidence_file_sha256": (
                context.production.inputs.usage_evidence_file.sha256
            ),
            "cs1_upload_ms": diagnostic["cs1_upload_ms"],
            "cs2_upload_ms": diagnostic["cs2_upload_ms"],
            "driver_total_ms": diagnostic["total_ms"],
            "measured_sclk_hz": final["observation"]["measured_sclk_hz"],
            "peak_current_a": final["observation"]["peak_current_a"],
            "max_temperature_c": final["observation"]["max_temperature_c"],
            "visual_pass": final["observation"]["visual_pass"],
            "electrical_pass": bool(
                final["observation"]["cv_pass"]
                and final["observation"]["thermal_pass"]
                and final["observation"]["acoustic_pass"]
            ),
        }
        rows.append(row)
        prior = item
    last_analysis = stored[-1]["final"]["analysis"]
    if (
        last_analysis.get("highest_passed_hz") != frozen.FREQUENCIES[-1]
        or last_analysis.get("next_frequency_hz") is not None
    ):
        raise N7PhysicalAnalyzerError("final N7 cumulative analyzer did not close at 10 MHz")
    upload_totals = [row["cs1_upload_ms"] + row["cs2_upload_ms"] for row in rows]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "materialization_canonical_sha256": first.manifest["integrity"][
            "canonical_sha256"
        ],
        "campaign_canonical_sha256": first.campaign["integrity"][
            "canonical_sha256"
        ],
        "panel": dict(first.campaign["panel"]),
        "firmware": dict(first.campaign["firmware"]),
        "limit_authority_lineage": authority_lineage,
        "reviewer_id": reviewer_id,
        "reviewer_key_id": first.production.reviewer_key_id,
        "counts": {
            "frequencies": len(rows),
            "visible_actions": len(rows),
            "unique_actions": len(action_ids),
            "unique_claims": len(claim_files),
            "unique_attempts": len(attempts),
            "unique_results": len(result_files),
        },
        "rows": rows,
        "descriptive_summary": {
            "highest_passed_hz": last_analysis["highest_passed_hz"],
            "upload_total_ms_min": min(upload_totals),
            "upload_total_ms_max": max(upload_totals),
            "upload_total_ms_mean": statistics.fmean(upload_totals),
            "peak_current_a_max": max(row["peak_current_a"] for row in rows),
            "temperature_c_max": max(row["max_temperature_c"] for row in rows),
            "all_visual_pass": all(row["visual_pass"] for row in rows),
            "all_electrical_pass": all(row["electrical_pass"] for row in rows),
        },
        "classification": {
            "evidence_chain_complete": True,
            "descriptive_only": True,
            "production_frequency_setting_selected": False,
            "automatic_firmware_change_authorized": False,
            "hardware_qualification_claimed": False,
            "qualification_state": "NOT_QUALIFIED",
        },
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(unsigned),
            "canonical_sha256_scope": HASH_SCOPE,
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_directories", type=Path, nargs=5)
    parser.add_argument("--reviewer-key", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    value = analyze_physical_sweep(
        args.result_directories, reviewer_key_file=args.reviewer_key
    )
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["N7PhysicalAnalyzerError", "analyze_physical_sweep"]
