#!/usr/bin/env python3
"""One-shot WF23 white-containment entry after the sealed C23 DRF fault.

This adapter never retries the consumed C23 action.  It permits only ordinal
2 of the still-unused, independently namespaced WF23 factory-OTP recovery
image from the pinned empirical-H3 release.  The ordinary runtime-before-white
host gate is replaced by an exact binding to the C23 fault output, permanent
claim, read-only terminal snapshots, and operator J2-OFF containment record.

The device protocol, firmware, ARM/EXECUTE count, permanent recovery claim,
terminal validator, BUSY timeouts, and no-retry behavior remain unchanged.
The resulting action is emergency white containment only and is never T23
treatment or pair evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
import stat
import sys
from typing import Any, Final, Mapping, Sequence

from tools import mf1750_ec5_runtime_lut_contract as contract
from tools import mf1750_ec5_runtime_lut_physical_once as physical


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
FAULT_DIR: Final = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_EC5_H3_C23_WHITE_VISIBLE_20260817_V1"
)
EXPECTED_RELEASE_ID: Final = (
    "9ea2100e3934f95edd08a367d979c1eb340e5c67c316873806749a4a57de16f4"
)
EXPECTED_PROFILE_ID: Final = "WF23_25"
EXPECTED_RECOVERY_ACTION_ID: Final = (
    "4acae8345b3084657c50f1babc1a5fc3f91898e0b5c64ee6be67459d730c9856"
)
EXPECTED_RECOVERY_BINARY_SHA256: Final = (
    "2712984d39f1c295841a4b9994c72ee13f6c6935e514ce918648cce2a6159e7c"
)
EXPECTED_RECOVERY_ELF_SHA256: Final = (
    "9c3587285d2b4748ca1594dffbc0848dd394d48c74bd205d6d7ce90699bd3939"
)
EXPECTED_RECOVERY_NAMESPACE: Final = "otpw_w23_v1"
EXPECTED_BASE_ROUTE: Final = "/api/ec5/factory-otp-white"
SCREEN_STATE: Final = "post_c23_fault_atlas_unrecovered_emergency_containment"

BOUND_FILES: Final = {
    "output_attempt": (
        FAULT_DIR / "c23-white-once-result.json",
        "1255567af4ce748328af80a3bf200ceb6f126d8270a4f8cc3c88a31607558d94",
        "a27c1ccb64711b2cdc3931804c9ce7bbee0eda380354191d1152a255ee013139",
        True,
    ),
    "status_snapshot": (
        FAULT_DIR / "c23-white-status-raw.json",
        "7945af15539bc51b497b31dd8d3da3fef090ef9a228b1a4abc2626323b6b45a1",
        "e083637b6cc5b602fbbcb905dd3f0bf130d41227628e3c641df18d04b83fc969",
        False,
    ),
    "terminal_snapshot": (
        FAULT_DIR / "c23-white-terminal-report-raw.json",
        "42b4803aaa246d43a4edab09a1bf30cef85bee04ac01ebd519eb1b035a0848a8",
        "69687c77c11a6c09b3b516fcb8d033d68d5ee744f7e553731772d8647a4b3095",
        False,
    ),
    "manual_observation": (
        FAULT_DIR / "c23-white-fault-manual-observation.json",
        "4f2f2b877c31b16fc3bf08e5d0505e9882268ea84a883f65aabe8d6e9a76cb92",
        "674619f47764eb1c83cf95c9ff5001ace988105acde0d4a03b5915ea89ccd4ef",
        True,
    ),
    "forensic_supplement": (
        FAULT_DIR / "c23-white-fault-forensic-supplement.json",
        "a155e78323c24ede8144564d4b697772c367aa295a3397c1d4a4da6139a64c68",
        "5c5eba15caed1d1ae085c1a3a329f49bbd8db5a45886ca6b5e36c188f09b804f",
        True,
    ),
}
CLAIM_PATH: Final = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_ec5_h3_c23_matched_control_claims_v2"
    / "matched-c-first-WF23_25-02-"
    "2cb2a1ae5e80ca96455a565d3a448268f5b54ea52cb45b13ef7f0c35cd13ac82.json"
)
EXPECTED_C23_CLAIM_FILE_SHA256: Final = (
    "57c19106d1821e0f589989546edc61a25e55ccd3a195cb92ab5e1245ba855b68"
)
EXPECTED_C23_CLAIM_CANONICAL_SHA256: Final = (
    "5823e2b56632da3a252c0b90ef677fd1287752d74b31d17423a0b955149840ca"
)

_ORIGINAL_REQUIRED_AUTHORIZATION = physical.required_authorization


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _strict_json(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise physical.PhysicalOnceError(f"{label} must be a regular non-symlink")
    payload = path.read_bytes()
    after = path.lstat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(payload) != after.st_size:
        raise physical.PhysicalOnceError(f"{label} changed while read")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise physical.PhysicalOnceError(f"{label} is not strict UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise physical.PhysicalOnceError(f"{label} root is not an object")
    return payload, value


def _canonical_sha256(value: Mapping[str, Any], *, sealed: bool, label: str) -> str:
    if sealed:
        return physical._validate_seal(value, label=label)  # noqa: SLF001
    return contract.sha256(value)


def validate_fault_evidence() -> str:
    """Deep-check the immutable C23 fault boundary and return its binding ID."""

    roots: dict[str, Mapping[str, Any]] = {}
    records: dict[str, str] = {}
    for label, (path, wanted_file, wanted_canonical, sealed) in BOUND_FILES.items():
        payload, root = _strict_json(path, label=label)
        file_sha = contract.sha256(payload)
        canonical = _canonical_sha256(root, sealed=sealed, label=label)
        if file_sha != wanted_file or canonical != wanted_canonical:
            raise physical.PhysicalOnceError(f"bound {label} identity differs")
        roots[label] = root
        records[label] = file_sha

    claim_payload, claim = _strict_json(CLAIM_PATH, label="C23 permanent claim")
    claim_file_sha = contract.sha256(claim_payload)
    claim_canonical = physical._validate_seal(  # noqa: SLF001
        claim, label="C23 permanent claim"
    )
    if (
        claim_file_sha != EXPECTED_C23_CLAIM_FILE_SHA256
        or claim_canonical != EXPECTED_C23_CLAIM_CANONICAL_SHA256
        or claim.get("state") != "permanently_consumed_do_not_retry"
        or claim.get("ordinal") != 2
    ):
        raise physical.PhysicalOnceError("C23 permanent fault claim differs")

    attempt = roots["output_attempt"]
    status = roots["status_snapshot"]
    report = roots["terminal_snapshot"]
    observation = roots["manual_observation"]
    supplement = roots["forensic_supplement"]
    if (
        attempt.get("state") != "TERMINAL_UNKNOWN_CLAIM_MAY_BE_CONSUMED"
        or attempt.get("retry_allowed") is not False
        or status.get("state") != "fault_locked"
        or status.get("arm_request_count") != 1
        or status.get("execute_request_count") != 1
        or status.get("total_driver_call_count") != 1
        or report.get("terminal_state") != "FAULT"
        or report.get("result") is not False
        or report.get("no_retry") is not True
        or report.get("driver", {}).get("timeout_stage") != "DRF"
        or observation.get("state")
        != "FAULT_OBSERVATION_RECORDED_J2_OFF_NO_RECOVERY_AUTHORIZED"
        or observation.get("electrical", {}).get("j2_after_observation") != "OFF"
        or observation.get("electrical", {}).get("current_after_j2_off_a") != 0.0
        or supplement.get("containment", {}).get("operator_j2_off") is not True
        or supplement.get("containment", {}).get("action_retry_forbidden") is not True
    ):
        raise physical.PhysicalOnceError("C23 fault evidence semantics differ")
    return contract.sha256(
        {
            "files": records,
            "c23_claim_file_sha256": claim_file_sha,
            "c23_claim_canonical_sha256": claim_canonical,
            "classification": "C23_DRF_TIMEOUT_J2_OFF_STANDALONE_WHITE_CONTAINMENT",
        }
    )


def _require_fault_recovery_evidence(
    context: physical.ReleaseContext, registry: Path
) -> None:
    evidence_id = validate_fault_evidence()
    if len(evidence_id) != 64:
        raise physical.PhysicalOnceError("C23 fault evidence ID is invalid")
    binding = context.binding(2)
    if (
        context.release_id != EXPECTED_RELEASE_ID
        or context.profile_id != EXPECTED_PROFILE_ID
        or context.action(2).get("hardware_action_id") != EXPECTED_RECOVERY_ACTION_ID
        or binding.get("firmware_binary_sha256") != EXPECTED_RECOVERY_BINARY_SHA256
        or binding.get("firmware_elf_sha256") != EXPECTED_RECOVERY_ELF_SHA256
        or binding.get("nvs_namespace") != EXPECTED_RECOVERY_NAMESPACE
        or binding.get("base_route") != EXPECTED_BASE_ROUTE
    ):
        raise physical.PhysicalOnceError("standalone WF23 recovery binding differs")
    selected_registry = Path(registry).resolve()
    if selected_registry != physical.DEFAULT_CLAIM_REGISTRY.resolve():
        raise physical.PhysicalOnceError("fault recovery claim registry differs")
    runtime_claim = physical._claim_path(context, 1, selected_registry)  # noqa: SLF001
    recovery_claim = physical._claim_path(context, 2, selected_registry)  # noqa: SLF001
    if runtime_claim.exists():
        raise physical.PhysicalOnceError(
            "WF23 runtime claim unexpectedly exists; containment boundary differs"
        )
    if recovery_claim.exists():
        raise physical.PhysicalOnceError(
            "standalone WF23 white containment action is already consumed"
        )


def required_authorization(
    context: physical.ReleaseContext,
    ordinal: int,
    operator_temperature_c: str | float | int,
    diagnostic: Mapping[str, Any],
) -> str:
    if ordinal != 2:
        raise physical.PhysicalOnceError("fault recovery entry permits only ordinal 2")
    _require_fault_recovery_evidence(context, physical.DEFAULT_CLAIM_REGISTRY)
    base = _ORIGINAL_REQUIRED_AUTHORIZATION(
        context, ordinal, operator_temperature_c, diagnostic
    )
    return (
        f"{base}__C23_FAULT_EVIDENCE_{validate_fault_evidence().upper()}"
        "__STANDALONE_WHITE_CONTAINMENT_NOT_T23_EVIDENCE"
    )


def install_overrides() -> None:
    physical._require_runtime_claim = _require_fault_recovery_evidence  # noqa: SLF001
    physical.required_authorization = required_authorization
    physical.SCREEN_RECOVERY = SCREEN_STATE


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else None
    if command in {"diagnose", "authorize", "run"}:
        try:
            ordinal = args[args.index("--ordinal") + 1]
        except (ValueError, IndexError) as error:
            raise physical.PhysicalOnceError(
                "fault recovery command requires --ordinal 2"
            ) from error
        if ordinal != "2":
            raise physical.PhysicalOnceError(
                "fault recovery entry permits only ordinal 2"
            )
    if "--claim-registry" in args:
        raise physical.PhysicalOnceError(
            "fault recovery entry fixes the permanent claim registry"
        )
    validate_fault_evidence()
    install_overrides()
    return physical.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
