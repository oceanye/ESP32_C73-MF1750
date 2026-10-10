#!/usr/bin/env python3
"""Sealed host-only successor pack for the Same-R20 AA-abort V1 diagnostic.

This pack does not define or build another firmware image.  It binds the
already successful V1 app-only flash and the immutable first diagnostic
failure, then permits one manually started replacement J2-OFF diagnostic.
The failed first diagnostic remains evidence and is never overwritten.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_same_r20_aa_abort_white_v1_pack as v1_pack  # noqa: E402


KIND = "mf1750-same-r20-aa-abort-white-v1b-host-successor-pack"
SUCCESSOR_ID = "b4f6b4e137e324d3a2c02aa75a52a17c6c18ffce7f7b1994f167b36671c8d40e"

V1_PACK_FILE = REPO_ROOT / "tools/mf1750_same_r20_aa_abort_white_v1_pack.py"
V1_PACK_BYTES = 23_157
V1_PACK_SHA256 = "3e0074b55e0b139a0f39733fb4af00cbb5b9938919a63ebbf91bdaad5082c98f"
V1_RUNNER_FILE = REPO_ROOT / "tools/mf1750_same_r20_aa_abort_white_v1_once.py"
V1_RUNNER_BYTES = 40_338
V1_RUNNER_SHA256 = "7e964121c4bd32c48b8fa1511ed94f8cc03b2fb332fabee96ec1ac9ddae02718"

V1_ROOT = REPO_ROOT / Path(
    ".test-output/hardware/MF1750_SAME_R20_AA_ABORT_WHITE_20260828_V1"
)
FLASH_FILE = V1_ROOT / "app-only-single-boot-flash.json"
FLASH_BYTES = 6_750
FLASH_SHA256 = "e16ce55791a55a06f951003dcda1cec750b71721ef991a589009b3bfbf2a0a4d"
FLASH_INTEGRITY_SHA256 = (
    "f7186c3c5bc3db1bcc3d4fba38057efaa40ad034e2c6297f7349fe3ca6406c97"
)
FAILED_DIAGNOSTIC_FILE = V1_ROOT / "j2-off-diagnostic.json"
FAILED_DIAGNOSTIC_BYTES = 3_905
FAILED_DIAGNOSTIC_SHA256 = (
    "d7905bbe3099b2b9ffd755afc4f200a2c29ac213045c0ef5a8d511ac8337bb05"
)
FAILED_DIAGNOSTIC_INTEGRITY_SHA256 = (
    "78491c830a3386b8b15788191667b434e3b0763fd11124fd3efdad81bc838ec4"
)
FAILED_DIAGNOSTIC_ERROR = (
    "GET version failed: direct GET /api/ec5/same-r20-aa-abort-white-v1/version "
    "response is not UTF-8 JSON"
)
FAILED_DIAGNOSTIC_TRANSPORT_ERROR = (
    "ContainmentError: direct GET /api/ec5/same-r20-aa-abort-white-v1/version "
    "response is not UTF-8 JSON"
)
MALFORMED_IDENTITY_MARKER = (
    b'"relay_off_receipt_is_command_query_not_load_voltage_proof":true","profile_id":"'
)
CORRECTED_IDENTITY_MARKER = (
    b'"relay_off_receipt_is_command_query_not_load_voltage_proof":true,"profile_id":"'
)
MALFORMED_IDENTITY_MARKER_BYTES = 80
MALFORMED_IDENTITY_MARKER_SHA256 = (
    "6ab04274a27c677e6cb0cbcd0ef3265f4ff0c070e59ec6e07b191f53f845d3fd"
)
CORRECTED_IDENTITY_MARKER_BYTES = 79
CORRECTED_IDENTITY_MARKER_SHA256 = (
    "98b01308f1690a0031464ca90438f4e5cdbb9898107cd0b9c0f5a089116e52f0"
)

SUCCESSOR_ROOT = REPO_ROOT / Path(
    ".test-output/hardware/"
    "MF1750_SAME_R20_AA_ABORT_WHITE_20260828_V1B_DIAGNOSTIC_SUCCESSOR"
)
SUCCESSOR_DIAGNOSTIC_FILE = SUCCESSOR_ROOT / "j2-off-diagnostic.json"
SUCCESSOR_DIAGNOSTIC_KIND = (
    "mf1750-same-r20-aa-abort-white-v1b-successor-j2-off-diagnostic"
)
SUCCESSOR_DIAGNOSTIC_ATTEMPT_KIND = f"{SUCCESSOR_DIAGNOSTIC_KIND}-attempt"

ACTION_OUTPUT = V1_ROOT / "action-01-factory-otp-white.json"
CLAIMS_ROOT = REPO_ROOT / Path(
    ".test-output/hardware/.mf1750_same_r20_aa_abort_white_v1_claims"
)
CLAIM_FILE = CLAIMS_ROOT / f"{v1_pack.ACTION_ID}.json"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def _read_sealed_json(path: Path, *, label: str) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is missing or not a regular file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} root is not an object")
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping):
        raise ValueError(f"{label} integrity is missing")
    body = dict(value)
    body.pop("integrity", None)
    if integrity.get(
        "algorithm"
    ) != "sha256-canonical-json-without-integrity" or integrity.get(
        "sha256"
    ) != _canonical_sha256(body):
        raise ValueError(f"{label} canonical integrity differs")
    return value


def _verify_exact_file(path: Path, *, byte_count: int, sha256: str, label: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != byte_count
        or _sha256(path) != sha256
    ):
        raise ValueError(f"{label} file binding differs")


SOURCE_MAIN_BINDING = {
    **v1_pack.SOURCE_TERMINATION_BINDING,
    "source_action_file_sha256": v1_pack.SOURCE_ACTION_FILE_SHA256,
    "source_camera_file_set_sha256": v1_pack._canonical_sha256(  # noqa: SLF001
        [dict(item) for item in v1_pack.CAMERA_FILE_BINDINGS]
    ),
}

SUCCESSOR_EVIDENCE_BINDING = {
    "manual_independent_diagnostic_successor": True,
    "predecessor_failure_preserved": True,
    "predecessor_failed_diagnostic_sha256": FAILED_DIAGNOSTIC_SHA256,
    "predecessor_failed_diagnostic_integrity_sha256": (
        FAILED_DIAGNOSTIC_INTEGRITY_SHA256
    ),
    "predecessor_flash_evidence_sha256": FLASH_SHA256,
    "predecessor_flash_evidence_integrity_sha256": FLASH_INTEGRITY_SHA256,
    "bound_v1_contract_id": v1_pack.CONTRACT_ID,
    "bound_v1_action_id": v1_pack.ACTION_ID,
    "bound_v1_firmware_bin_sha256": v1_pack.FIRMWARE_BIN_SHA256,
    "bound_v1_firmware_elf_sha256": v1_pack.FIRMWARE_ELF_SHA256,
}


def _validate_failed_diagnostic() -> Mapping[str, Any]:
    _verify_exact_file(
        FAILED_DIAGNOSTIC_FILE,
        byte_count=FAILED_DIAGNOSTIC_BYTES,
        sha256=FAILED_DIAGNOSTIC_SHA256,
        label="sealed predecessor failed diagnostic",
    )
    value = _read_sealed_json(
        FAILED_DIAGNOSTIC_FILE, label="sealed predecessor failed diagnostic"
    )
    exact = {
        "schema_version": 1,
        "kind": "mf1750-same-r20-aa-abort-white-v1-j2-off-diagnostic-attempt",
        "outcome": "j2_off_diagnostic_failed_no_claim",
        "stage": "preflight_get_version",
        "error": {"type": "ContainmentError", "message": FAILED_DIAGNOSTIC_ERROR},
        "firmware_sha256": v1_pack.FIRMWARE_BIN_SHA256,
        "running_app_elf_sha256": None,
        "boot_nonce": None,
        "action": v1_pack.build_report(verify_artifacts=False)["action"],
        "claim_file": None,
        "claim_state": "not_created",
        "permanent_claims_created": 0,
        "permanent_claims_created_by_this_invocation": 0,
        "network": {"get": 1, "post": 0},
        "visible_refreshes_confirmed": 0,
        "visible_refresh_may_have_occurred": False,
        "output_write_contract": "O_EXCL",
        "artifact_preflight_completed_before_network": True,
        "base_url": "http://192.168.1.11",
        "transport": {
            "mode": "direct_private_literal_ipv4_http",
            "proxy": False,
            "redirect": False,
        },
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "no_ordinal_skip": True,
    }
    for key, wanted in {**SOURCE_MAIN_BINDING, **exact}.items():
        if value.get(key) != wanted:
            raise ValueError(f"predecessor failed diagnostic {key} differs")
    if value["integrity"].get("sha256") != FAILED_DIAGNOSTIC_INTEGRITY_SHA256:
        raise ValueError("predecessor failed diagnostic recorded integrity differs")
    transcript = value.get("transcript")
    if transcript != [
        {
            "endpoint": "version",
            "headers": {},
            "method": "GET",
            "path": f"{v1_pack.BASE_ROUTE}/version",
            "transport_error": FAILED_DIAGNOSTIC_TRANSPORT_ERROR,
        }
    ]:
        raise ValueError("predecessor failed diagnostic transcript differs")
    return value


def _validate_flash() -> Mapping[str, Any]:
    _verify_exact_file(
        FLASH_FILE,
        byte_count=FLASH_BYTES,
        sha256=FLASH_SHA256,
        label="sealed predecessor app-only flash",
    )
    value = _read_sealed_json(FLASH_FILE, label="sealed predecessor app-only flash")
    binary = value.get("binary")
    constraints = value.get("constraints")
    steps = value.get("steps")
    if (
        value.get("integrity", {}).get("sha256") != FLASH_INTEGRITY_SHA256
        or value.get("schema_version") != 1
        or value.get("kind") != "mf1750-app-only-single-boot-flash-result"
        or value.get("outcome") != "app_only_write_verify_single_boot_pass"
        or value.get("success") is not True
        or value.get("j2_confirmed_off") is not True
        or value.get("output_write_contract") != "O_EXCL"
        or not isinstance(binary, Mapping)
        or binary.get("bytes") != v1_pack.FIRMWARE_BIN_BYTES
        or binary.get("expected_sha256") != v1_pack.FIRMWARE_BIN_SHA256
        or binary.get("observed_sha256") != v1_pack.FIRMWARE_BIN_SHA256
        or binary.get("preflight_verified") is not True
        or not isinstance(constraints, Mapping)
        or constraints.get("application_only") is not True
        or constraints.get("application_start_count_after_write") != 1
        or constraints.get("bootloader_write") is not False
        or constraints.get("partition_table_write") is not False
        or constraints.get("nvs_write_or_erase") is not False
        or constraints.get("erase_command") is not False
        or constraints.get("retry") is not False
        or constraints.get("recovery") is not False
        or constraints.get("fallback") is not False
        or constraints.get("subsequent_hardware_action_after_failure") is not False
        or constraints.get("write_after") != "no_reset"
        or constraints.get("verify_before") != "no_reset"
        or constraints.get("verify_after") != "hard_reset"
        or not isinstance(steps, list)
        or len(steps) != 2
        or [
            (item.get("name"), item.get("execution_state"), item.get("returncode"))
            for item in steps
        ]
        != [
            ("write_flash_stay_in_bootloader", "complete_pass", 0),
            ("verify_flash_then_single_hard_reset", "complete_pass", 0),
        ]
    ):
        raise ValueError("predecessor app-only flash semantics differ")
    return value


def validate_predecessor_evidence(*, require_unexecuted: bool = True) -> dict[str, Any]:
    _verify_exact_file(
        V1_PACK_FILE,
        byte_count=V1_PACK_BYTES,
        sha256=V1_PACK_SHA256,
        label="bound V1 pack",
    )
    _verify_exact_file(
        V1_RUNNER_FILE,
        byte_count=V1_RUNNER_BYTES,
        sha256=V1_RUNNER_SHA256,
        label="bound V1 runner",
    )
    v1 = v1_pack.build_report(verify_artifacts=True)
    contract = v1.get("contract")
    if (
        not isinstance(contract, Mapping)
        or contract.get("contract_id") != v1_pack.CONTRACT_ID
        or v1.get("action")
        != v1_pack.build_report(verify_artifacts=False).get("action")
    ):
        raise ValueError("bound V1 pack identity differs")
    firmware = v1_pack.FIRMWARE_BIN.read_bytes()
    malformed_count = firmware.count(MALFORMED_IDENTITY_MARKER)
    corrected_count = firmware.count(CORRECTED_IDENTITY_MARKER)
    if malformed_count != 1 or corrected_count != 0:
        raise ValueError("bound V1 firmware narrow malformed identity marker differs")
    _validate_flash()
    _validate_failed_diagnostic()
    if require_unexecuted and (ACTION_OUTPUT.exists() or CLAIM_FILE.exists()):
        raise ValueError("V1 white action is no longer unexecuted")
    return {
        "v1_contract_id": v1_pack.CONTRACT_ID,
        "v1_action_id": v1_pack.ACTION_ID,
        "v1_firmware_bin_sha256": v1_pack.FIRMWARE_BIN_SHA256,
        "v1_firmware_elf_sha256": v1_pack.FIRMWARE_ELF_SHA256,
        "failed_diagnostic_sha256": FAILED_DIAGNOSTIC_SHA256,
        "flash_sha256": FLASH_SHA256,
        "malformed_identity_marker_count": malformed_count,
        "corrected_identity_marker_count": corrected_count,
        "unexecuted_gate": require_unexecuted,
    }


def _successor_id_payload() -> dict[str, Any]:
    return {
        "schema": "mf1750-same-r20-aa-abort-white-v1b-host-successor-v1",
        **SUCCESSOR_EVIDENCE_BINDING,
        "successor_diagnostic_kind": SUCCESSOR_DIAGNOSTIC_KIND,
        "successor_diagnostic_network": {"get": 4, "post": 0},
        "successor_diagnostic_write_contract": "O_EXCL",
        "run_requires_same_boot_nonce": True,
        "run_action_id": v1_pack.ACTION_ID,
        "run_arm_max": 1,
        "run_execute_max": 1,
        "v1_firmware_malformed_marker_count": 1,
        "v1_firmware_corrected_marker_count": 0,
        "normalization_rule": "replace_exact_unique_malformed_marker_once",
        "malformed_marker_ascii": MALFORMED_IDENTITY_MARKER.decode("ascii"),
        "malformed_marker_bytes": MALFORMED_IDENTITY_MARKER_BYTES,
        "malformed_marker_sha256": MALFORMED_IDENTITY_MARKER_SHA256,
        "corrected_marker_ascii": CORRECTED_IDENTITY_MARKER.decode("ascii"),
        "corrected_marker_bytes": CORRECTED_IDENTITY_MARKER_BYTES,
        "corrected_marker_sha256": CORRECTED_IDENTITY_MARKER_SHA256,
        "retry": False,
        "recovery": False,
        "autochain": False,
    }


def build_report(
    *, verify_artifacts: bool = True, require_unexecuted: bool = True
) -> dict[str, Any]:
    calculated = _canonical_sha256(_successor_id_payload())
    if calculated != SUCCESSOR_ID:
        raise ValueError("V1B successor identity differs")
    evidence = (
        validate_predecessor_evidence(require_unexecuted=require_unexecuted)
        if verify_artifacts
        else None
    )
    return {
        "schema_version": 1,
        "kind": KIND,
        "successor_id": SUCCESSOR_ID,
        "host_only": True,
        "firmware_build_or_flash_required": False,
        "narrow_transport_normalization": {
            "malformed_marker_ascii": MALFORMED_IDENTITY_MARKER.decode("ascii"),
            "malformed_marker_bytes": MALFORMED_IDENTITY_MARKER_BYTES,
            "malformed_marker_sha256": MALFORMED_IDENTITY_MARKER_SHA256,
            "corrected_marker_ascii": CORRECTED_IDENTITY_MARKER.decode("ascii"),
            "corrected_marker_bytes": CORRECTED_IDENTITY_MARKER_BYTES,
            "corrected_marker_sha256": CORRECTED_IDENTITY_MARKER_SHA256,
            "malformed_marker_count_required": 1,
            "corrected_marker_count_required_before_replace": 0,
            "replacement_count": 1,
            "all_v1_validators_still_required": True,
            "any_other_decode_or_json_error": "fail_closed",
        },
        **SUCCESSOR_EVIDENCE_BINDING,
        "action": v1_pack.build_report(verify_artifacts=False)["action"],
        "source_main_binding": dict(SOURCE_MAIN_BINDING),
        "successor_diagnostic": {
            "path": _display_path(SUCCESSOR_DIAGNOSTIC_FILE),
            "kind": SUCCESSOR_DIAGNOSTIC_KIND,
            "network": {"get": 4, "post": 0},
            "write_contract": "O_EXCL",
        },
        "run": {
            "same_boot_nonce_required": True,
            "action_output": _display_path(ACTION_OUTPUT),
            "claims_root": _display_path(CLAIMS_ROOT),
            "arm_post_max": 1,
            "execute_post_max": 1,
        },
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "validated_evidence": evidence,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
