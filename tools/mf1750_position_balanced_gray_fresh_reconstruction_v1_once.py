#!/usr/bin/env python3
"""Fail-closed one-action host for the fresh reconstruction campaign.

Importing and describing this module performs no I/O.  Live mechanics are
loaded only after both source authorities and local firmware artifacts seal.
There is no G4 ordinal, boot action, flash, power control, retry, recovery, or
automatic chain in this host.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_position_balanced_gray_fresh_reconstruction_v1_pack as pack,
)

OUTPUT_ROOT = (
    REPO_ROOT
    / ".test-output/hardware/MF1750_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_20260901_V1"
)
CLAIMS_ROOT = (
    REPO_ROOT
    / ".test-output/hardware/.mf1750_position_balanced_gray_fresh_reconstruction_v1_claims"
)
DIAGNOSTIC_OUTPUT = OUTPUT_ROOT / "j2-off-diagnostic.json"
ACTION_OUTPUTS = {
    1: OUTPUT_ROOT / "action-01-r1-active-c7-source.json",
    2: OUTPUT_ROOT / "action-02-r2-commented-c0-to-c7-position-balanced-middle.json",
    3: OUTPUT_ROOT / "action-03-r3-active-c3-c7-target.json",
}
_NONCE = re.compile(r"^[0-9a-f]{16}$")
_DELEGATE: Any = None


class FreshReconstructionRunnerError(RuntimeError):
    """Raised before an unsafe, unsealed, or mismatched host action."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _runner_actions(report: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    actions: list[dict[str, Any]] = []
    for source in report["actions"]:
        ordinal = source["ordinal"]
        actions.append(
            {
                "ordinal": ordinal,
                "descriptor_id": source["descriptor_id"],
                "action_id": source["action_id"],
                "prior_static_action_id": source["prior_static_action_id"],
                "role": source["role"],
                "round": 1,
                "branch": source["branch"],
                "frame_sha256": source["frame"]["sha256"],
                "cs1_dtm_sha256": source["cs1_dtm"]["sha256"],
                "cs2_dtm_sha256": source["cs2_dtm"]["sha256"],
                "transport_code_histogram": deepcopy(
                    source["frame"]["histogram"]
                ),
                "boot_admission": {
                    "campaign_boot_binding_key": pack.NVS_BOOT_KEY,
                    "admission": (
                        "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
                        if ordinal == 1
                        else "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY"
                    ),
                    "required_prior_terminal_state": (
                        None if ordinal == 1 else "COMPLETE"
                    ),
                    "required_prior_ordinal": None if ordinal == 1 else ordinal - 1,
                    "firmware_arm_gate": True,
                    "firmware_execute_gate": True,
                    "firmware_dispatch_gate": True,
                    "reboot_resume_allowed": False,
                    "post_containment_resume_allowed": False,
                },
                "palette_source": "L535_RUNTIME",
                "global_header": source["global_header"],
                "driver_entry": "epdDisplayCompiledChromaGrid",
            }
        )
    return tuple(actions)


def _load_delegate() -> Any:
    global _DELEGATE  # noqa: PLW0603
    if _DELEGATE is not None:
        return _DELEGATE
    report = pack.build_report()
    pack.validate_live_execution_gate()
    pack.verify_artifact_files()
    old = importlib.import_module(
        "tools.mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_once"
    )
    old.pack = pack
    old.REPORT = report
    old.v3.pack = pack
    old.v3.REPORT = report
    old.base.pack = pack
    old.base._REPORT = report  # noqa: SLF001
    runner = old.base.runner
    runner.BUILD_TAG = pack.BUILD_TAG
    runner.TEST_ID = pack.TEST_ID
    runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
    runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
    runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
    runner.CONTRACT_ID = report["contract_id"]
    runner.CLASSIFICATION = pack.CLASSIFICATION
    runner.DEVICE_KIND_PREFIX = pack.CLAIM_KIND_PREFIX
    runner.EVIDENCE_KIND_PREFIX = pack.CLAIM_KIND_PREFIX
    runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
    runner.NVS_KEY = pack.NVS_KEY
    runner.FIRMWARE_SHA256 = str(pack.ARTIFACTS["bin_sha256"])
    runner.FIRMWARE_BYTES = int(pack.ARTIFACTS["bin_bytes"])
    runner.ENDPOINTS = {
        name: f"{pack.BASE_ROUTE}/{name}"
        for name in ("version", "manifest", "status", "report", "arm", "execute")
    }
    runner.ARM_INTENT = pack.ARM_INTENT
    runner.EXECUTE_INTENT = pack.EXECUTE_INTENT
    runner.ACTIONS = _runner_actions(report)
    runner.DESCRIPTOR_IDS = tuple(item["descriptor_id"] for item in runner.ACTIONS)
    runner.ACTION_IDS = tuple(item["action_id"] for item in runner.ACTIONS)
    runner.DEFAULT_CLAIMS = CLAIMS_ROOT
    runner.DEFAULT_OUTPUT = OUTPUT_ROOT
    old.DIAGNOSTIC_OUTPUT = DIAGNOSTIC_OUTPUT
    old.ACTION_OUTPUTS = ACTION_OUTPUTS

    def validate_prior(value: Mapping[str, Any], ordinal: int, nonce: str) -> None:
        if ordinal <= 1:
            raise runner.RecheckError("reconstruction prior ordinal differs")
        old.v3._validate_complete_report(value, ordinal - 1, nonce)  # noqa: SLF001

    def preflight(
        base_url: str,
        ordinal: int,
        *,
        expected_busy: int,
        requester: Any,
    ) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
        nonce, transcript, prior = old.v3.v1._BASE_PREFLIGHT(  # noqa: SLF001
            base_url,
            ordinal,
            expected_busy=expected_busy,
            requester=requester,
        )
        if ordinal == 1:
            old.v3.v1._validate_fresh_no_execute_report(prior, nonce)  # noqa: SLF001
        else:
            validate_prior(prior, ordinal, nonce)
        return nonce, transcript, prior

    old.v3._validate_prior_terminal_report = validate_prior  # noqa: SLF001
    old.v3._preflight = preflight  # noqa: SLF001
    old.v3.v1._preflight = preflight  # noqa: SLF001
    old.v3.base.runner._preflight = preflight  # noqa: SLF001
    _DELEGATE = old
    return old


def dry_validate(
    *, require_sealed: bool = False, verify_artifacts: bool = False
) -> dict[str, Any]:
    validation = pack.dry_validate(
        require_sealed=require_sealed,
        verify_artifacts=verify_artifacts,
    )
    report = pack.build_report() if require_sealed else pack.template_report()
    actions = _runner_actions(report)
    if (
        len(actions) != 3
        or set(ACTION_OUTPUTS) != {1, 2, 3}
        or any(item["ordinal"] == 4 for item in actions)
    ):
        raise FreshReconstructionRunnerError("three-action runner surface differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-position-balanced-gray-fresh-reconstruction-v1-runner-validation",
        "result": (
            "PASS"
            if validation["live_execution_gate_passed"]
            else "OFFLINE_IDENTITY_PASS_LIVE_EXECUTION_BLOCKED"
        ),
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract_id": report["contract_id"],
        "action_count": 3,
        "accepted_ordinals": [1, 2, 3],
        "g4_accepted": False,
        "offline_predecessor_package_sealed": validation[
            "source_predecessor_package_sealed"
        ],
        "live_execution_gate_passed": validation["live_execution_gate_passed"],
        "no_boot_action": True,
        "no_retry": True,
        "no_fallback": True,
        "no_recovery": True,
        "no_autochain": True,
        "claims_root": CLAIMS_ROOT.relative_to(REPO_ROOT).as_posix(),
        "output_root": OUTPUT_ROOT.relative_to(REPO_ROOT).as_posix(),
        "actions": deepcopy(list(actions)),
    }


def diagnose_j2_off(
    base_url: str, *, confirm_j2_off: bool, output: Path = DIAGNOSTIC_OUTPUT
) -> dict[str, Any]:
    if confirm_j2_off is not True:
        raise FreshReconstructionRunnerError("explicit J2-OFF confirmation required")
    delegate = _load_delegate()
    return delegate.diagnose_j2_off(
        base_url,
        confirm_j2_off=True,
        output=Path(output),
    )


def run_once(
    base_url: str,
    ordinal: int,
    *,
    confirm_j2_on: bool,
    confirm_gnd_normal: bool,
    confirm_current_post_hold_camera_relative_clean_white: bool,
    claims: Path = CLAIMS_ROOT,
    output: Path | None = None,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
) -> dict[str, Any]:
    if ordinal not in (1, 2, 3):
        raise FreshReconstructionRunnerError("only reconstruction ordinals 1-3 exist")
    if confirm_current_post_hold_camera_relative_clean_white is not True:
        raise FreshReconstructionRunnerError(
            "fresh reconstruction requires bound post-HOLD clean-white authority"
        )
    delegate = _load_delegate()
    return delegate.run_once(
        base_url,
        ordinal,
        claims=Path(claims),
        output=Path(output) if output is not None else ACTION_OUTPUTS[ordinal],
        requester=requester,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
        confirm_j2_on=confirm_j2_on,
        confirm_gnd_normal=confirm_gnd_normal,
        confirm_current_v3_camera_relative_white=True,
        confirm_optional_g4_repeat=False,
    )


def _read_integrity_json(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise FreshReconstructionRunnerError("terminal evidence missing or unsafe")
    try:
        value = json.loads(path.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreshReconstructionRunnerError("terminal evidence is not JSON") from error
    if not isinstance(value, dict):
        raise FreshReconstructionRunnerError("terminal evidence root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("sha256") != hashlib.sha256(_canonical(body)).hexdigest()
    ):
        raise FreshReconstructionRunnerError("terminal evidence integrity differs")
    return value


def validate_terminal_evidence(path: Path) -> dict[str, Any]:
    delegate = _load_delegate()
    value = _read_integrity_json(path)
    action = value.get("action")
    terminal = value.get("terminal_report")
    if not isinstance(action, Mapping) or not isinstance(terminal, Mapping):
        raise FreshReconstructionRunnerError("terminal action/report missing")
    ordinal = action.get("ordinal")
    if ordinal not in (1, 2, 3):
        raise FreshReconstructionRunnerError("terminal ordinal differs")
    expected = delegate.base.runner.ACTIONS[ordinal - 1]
    if dict(action) != expected:
        raise FreshReconstructionRunnerError("terminal action identity differs")
    nonce = value.get("boot_nonce")
    if not isinstance(nonce, str) or _NONCE.fullmatch(nonce) is None:
        raise FreshReconstructionRunnerError("terminal boot nonce differs")
    try:
        delegate.v3._validate_complete_report(terminal, ordinal, nonce)  # noqa: SLF001
    except RuntimeError as error:
        raise FreshReconstructionRunnerError("terminal COMPLETE differs") from error
    if (
        value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or terminal.get("campaign_id") != pack.CAMPAIGN_ID
        or terminal.get("contract_id") != pack.build_report()["contract_id"]
        or terminal.get("ordinal") != ordinal
        or terminal.get("driver_call_count_for_action") != 1
    ):
        raise FreshReconstructionRunnerError("terminal campaign semantics differ")
    claim_path = CLAIMS_ROOT / f"{expected['action_id']}.json"
    try:
        claim, claim_file_sha256 = delegate.v3.v1._load_permanent_claim(  # noqa: SLF001
            claim_path, expected
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise FreshReconstructionRunnerError("permanent claim differs") from error
    if (
        claim.get("action") != expected
        or claim.get("firmware_sha256") != pack.ARTIFACTS["bin_sha256"]
        or claim.get("boot_nonce") != nonce
        or claim.get("state") != "claimed_before_first_mutation"
    ):
        raise FreshReconstructionRunnerError("permanent claim semantics differ")
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": pack.build_report()["contract_id"],
        "ordinal": ordinal,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": ordinal,
        "visible_refreshes": 1,
        "source_success_claimed": True,
        "boot_nonce": nonce,
        "claim_path": claim_path.relative_to(REPO_ROOT).as_posix(),
        "claim_bytes": claim_path.stat().st_size,
        "claim_file_sha256": claim_file_sha256,
        "claim_canonical_integrity_sha256": claim["integrity"]["sha256"],
        "file_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "canonical_integrity_sha256": value["integrity"]["sha256"],
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("dry-validate")
    diag = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diag.add_argument("--base-url", required=True)
    diag.add_argument("--confirm-j2-off", action="store_true", required=True)
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=(1, 2, 3), required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument("--confirm-gnd-normal", action="store_true", required=True)
    run.add_argument(
        "--confirm-current-post-hold-camera-relative-clean-white",
        action="store_true",
        required=True,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "dry-validate":
            value = dry_validate(require_sealed=False, verify_artifacts=False)
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                confirm_j2_off=args.confirm_j2_off,
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                confirm_j2_on=args.confirm_j2_on,
                confirm_gnd_normal=args.confirm_gnd_normal,
                confirm_current_post_hold_camera_relative_clean_white=(
                    args.confirm_current_post_hold_camera_relative_clean_white
                ),
            )
    except (FreshReconstructionRunnerError, RuntimeError, OSError) as error:
        print(f"fresh reconstruction runner blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
