#!/usr/bin/env python3
"""Fresh W9 factory-white successor after the consumed W8 ARM-400 attempt.

This module is offline-only.  It binds the original T4 terminal-FAULT chain,
the W8 consumed ARM intent-mismatch attempt, its permanent claim, and the
protective relay-OFF receipt.  It never performs device, COM, relay, network,
flash, or display I/O.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_pack as w8,
)


class W9PackError(RuntimeError):
    """Raised when W9 identity or predecessor authority differs."""


@dataclass(frozen=True)
class WhiteConfig:
    key: str = "w9-after-w8-arm400-successor-factory-otp-white-v1"
    suffix: str = "W9_AFTER_W8_ARM400_SUCCESSOR_FACTORY_OTP_WHITE"
    nvs_namespace: str = "p16w9a400_v1"
    nvs_key: str = "used_w9a400"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_W9_AFTER_W8_ARM400_"
            "SUCCESSOR_FACTORY_OTP_WHITE_V1_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-W9-AFTER-W8-ARM400-SUCCESSOR-WHITE-V1"

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_W9_AFTER_W8_ARM400_"
            "SUCCESSOR_FACTORY_OTP_WHITE_V1"
        )

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-w9-after-w8-arm400-successor-factory-otp-white-v1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_w9a400_w1"

    @property
    def build_root(self) -> str:
        return "b-w9a400-w1"


STAGE = "w9-after-w8-arm400-successor-factory-otp-white-v1"
CONFIG = WhiteConfig()
WHITES = {STAGE: CONFIG}
STAGES: dict[str, Any] = {}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR_WHITE_DEVICE_V1"
IDENTITY_REVISION = "raw-p16-crossover-w9-w8-arm400-successor-white-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_RAW_P16_CROSSOVER_W9_AFTER_W8_ARM400_"
    "ONE_ACTION_NO_RUNTIME_PAYLOAD"
)

# These host literals must equal the shared firmware literals byte-for-byte.
WHITE_ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
WHITE_EXECUTE_INTENT = "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE"

FACTORY_WHITE_FRAME_SHA256 = w8.FACTORY_WHITE_FRAME_SHA256
FACTORY_WHITE_DTM_SHA256 = w8.FACTORY_WHITE_DTM_SHA256
FACTORY_WHITE_FRAME_FNV1A = w8.FACTORY_WHITE_FRAME_FNV1A
FACTORY_WHITE_DTM_FNV1A = w8.FACTORY_WHITE_DTM_FNV1A

# Filled only after compile, clean rebuild, and independent re-read.
WHITE_ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 787_104,
        "bin_sha256": "f450f3f1293de0f103ac0593895d0cedc25cc6c43f219d11c9e303ba80b5b0d9",
        "elf_bytes": 13_214_976,
        "elf_sha256": "a47fff6cfed1a997efaed6f5bd14a094a5246e5a3f4a6d9a1c96c2be656e7c44",
    }
}

# Preserve the exact original T4 terminal-FAULT four-chain aliases used by
# the generic live runner guard.  W9 additionally validates the W8 failure.
SOURCE_FAILURE_BINDING = deepcopy(w8.SOURCE_FAILURE_BINDING)
CLAIM_BINDING = deepcopy(w8.CLAIM_BINDING)
RAW_SALVAGE_BINDING = deepcopy(w8.RAW_SALVAGE_BINDING)
FAULT_RECONCILIATION_BINDING = deepcopy(w8.FAULT_RECONCILIATION_BINDING)
RELAY_OFF_QUERY_BINDING = deepcopy(w8.RELAY_OFF_QUERY_BINDING)
LATEST_REPOWER_ON_BINDING = deepcopy(w8.LATEST_REPOWER_ON_BINDING)
PROTECTIVE_OFF_BINDING = deepcopy(w8.PROTECTIVE_OFF_BINDING)

W8_ATTEMPT_BINDING = {
    "path": str(
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_20260831_V1"
        / "action-01-factory-otp-white.json"
    ),
    "bytes": 14_228,
    "file_sha256": "84b1f3ecf51dc99b3efd91e0c71decca245ce9f358cc034241ee29554b980e0f",
    "canonical_integrity_sha256": "4f0a4e427efebd367739dbe66e00ccb8315461d1be5065054f003021f6567b8e",
}
W8_CLAIM_BINDING = {
    "path": str(
        REPO_ROOT
        / ".test-output/hardware"
        / ".mf1750_raw_p16_crossover_w8_t4_v3_fault_white_v1_claims"
        / "46f0ee263d7d6e2759d0078ba523878f29bf095bab4f9928288c9ccf76d1c348.json"
    ),
    "bytes": 1_841,
    "file_sha256": "806862a8333322bb244e33e0dd8881f1e038150d13402b2fce5cea62db9aa0a8",
    "canonical_integrity_sha256": "ea15fcd6ccec0c87910a415427d62b7ccccbb4cda5e5176fcbd0cbee82ea1286",
}
W8_POST_ARM400_PROTECTIVE_OFF_BINDING = {
    "path": str(
        REPO_ROOT
        / ".test-output/hardware"
        / "MF1750_RAW_P16_CROSSOVER_W8_T4_V3_FAULT_WHITE_20260831_V1"
        / "relay-post-arm400-protective-off.json"
    ),
    "bytes": 1_802,
    "file_sha256": "4744f94a169a8c2befc7d7c430b92537dcff36a07ca9ce931d9596170fe33ce6",
    "canonical_integrity_sha256": "c6a1149301a00adef2473e84c78144470d88a64b90ce167759568141d9eba360",
    "switched_at": "2026-08-31T15:33:04.268Z",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def white_artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    values = WHITE_ARTIFACTS[STAGE]
    return (
        int(values["bin_bytes"]) > 0
        and int(values["elf_bytes"]) > 0
        and values["bin_sha256"] != "0" * 64
        and values["elf_sha256"] != "0" * 64
    )


def _read_fixed_json(binding: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    path = Path(str(binding["path"])).resolve()
    if not path.is_file() or path.is_symlink():
        raise W9PackError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["file_sha256"]:
        raise W9PackError(f"{label} sealed file binding differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise W9PackError(f"{label} is not JSON") from error
    if not isinstance(value, dict):
        raise W9PackError(f"{label} JSON root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    actual = sha256_bytes(canonical_json(body))
    expected = binding["canonical_integrity_sha256"]
    recorded = None
    if isinstance(integrity, Mapping):
        recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
    if recorded != expected or actual != expected:
        raise W9PackError(f"{label} canonical integrity differs")
    return value


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def shared_firmware_intents() -> dict[str, str]:
    """Extract the actual device literals from the shared firmware source."""

    path = REPO_ROOT / "src/ec5_raw_p16_crossover_w2_discovery_successor_white_program.inc"
    text = path.read_text(encoding="utf-8")
    patterns = {
        "arm": r'kArmIntent\s*=\s*\n\s*"([^"]+)";',
        "execute": r'kExecuteIntent\s*=\s*\n\s*"([^"]+)";',
    }
    values: dict[str, str] = {}
    for name, pattern in patterns.items():
        matches = re.findall(pattern, text)
        if len(matches) != 1:
            raise W9PackError(f"shared firmware {name} intent cardinality differs")
        values[name] = matches[0]
    return values


def validate_intent_parity() -> dict[str, str]:
    device = shared_firmware_intents()
    expected = {
        "arm": "ARM_ONE_FIXED_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION",
        "execute": "EXECUTE_ONE_FIXED_FACTORY_OTP_WHITE_ONCE",
    }
    host = {"arm": WHITE_ARM_INTENT, "execute": WHITE_EXECUTE_INTENT}
    if host != device or device != expected:
        raise W9PackError("W9 host/device shared intent literals differ")
    return device


def validate_predecessor_authority() -> dict[str, Any]:
    """Deep-validate the T4 FAULT and consumed W8 ARM-400 predecessor."""

    t4_fault = w8.validate_fault_authority()
    attempt = _read_fixed_json(W8_ATTEMPT_BINDING, label="W8 consumed ARM-400 attempt")
    claim = _read_fixed_json(W8_CLAIM_BINDING, label="W8 permanent claim")
    protective_off = _read_fixed_json(
        W8_POST_ARM400_PROTECTIVE_OFF_BINDING,
        label="W8 post-ARM400 protective OFF",
    )
    w8_report = w8.build_white_report()
    transcript = attempt.get("transcript")
    arm = transcript[-1] if isinstance(transcript, list) and transcript else None
    status = transcript[2].get("body") if isinstance(transcript, list) and len(transcript) == 5 else None
    report = transcript[3].get("body") if isinstance(transcript, list) and len(transcript) == 5 else None
    if (
        t4_fault.get("terminal_state") != "FAULT"
        or attempt.get("kind")
        != "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-v1-attempt"
        or attempt.get("outcome") != "claimed_attempt_failed_do_not_retry"
        or attempt.get("stage") != "arm_post"
        or attempt.get("network") != {"get": 4, "post": 1}
        or attempt.get("no_retry") is not True
        or attempt.get("no_recovery") is not True
        or attempt.get("no_autochain") is not True
        or attempt.get("no_ordinal_skip") is not True
        or attempt.get("visible_refresh_may_have_occurred") is not False
        or attempt.get("visible_refreshes_confirmed") != 0
        or attempt.get("claim_state") != "permanently_consumed_by_this_invocation"
        or attempt.get("action") != w8_report["action"]
        or attempt.get("error")
        != {"message": "POST arm returned HTTP 400", "type": "ContainmentError"}
        or not isinstance(transcript, list)
        or len(transcript) != 5
        or [(item.get("method"), item.get("endpoint"), item.get("status")) for item in transcript]
        != [
            ("GET", "version", 200),
            ("GET", "manifest", 200),
            ("GET", "status", 200),
            ("GET", "report", 200),
            ("POST", "arm", 400),
        ]
        or not isinstance(arm, Mapping)
        or arm.get("body")
        != {
            "accepted": False,
            "error": "intent_mismatch",
            "fault_locked": True,
            "no_retry": True,
        }
        or arm.get("headers", {}).get("X-EC5-Intent") != w8.WHITE_ARM_INTENT
        or not isinstance(status, Mapping)
        or status.get("arm_request_count") != 0
        or status.get("execute_request_count") != 0
        or status.get("total_driver_call_count") != 0
        or status.get("phase_name") != "READY"
        or not isinstance(report, Mapping)
        or report.get("terminal_state") != "NOT_EXECUTED"
        or report.get("driver_called") is not False
        or report.get("driver_call_count_for_action") != 0
        or report.get("valid") is not False
        or claim.get("kind")
        != "mf1750-raw-p16-crossover-w8-t4-v3-fault-white-v1-claim"
        or claim.get("state")
        != "permanently_claimed_after_j2_on_preflight_before_first_arm"
        or claim.get("write_contract") != "O_EXCL"
        or claim.get("action") != w8_report["action"]
        or claim.get("boot_nonce") != attempt.get("boot_nonce")
        or protective_off.get("kind")
        != "mf17506-zave-relay-exact-bound-switch-receipt"
        or protective_off.get("commanded_state") != "OFF"
        or protective_off.get("target_state") != "OFF"
        or protective_off.get("off_gate_passed") is not True
        or protective_off.get("contact_switch_performed") is not True
        or protective_off.get("electrical_state_proven") is not False
        or protective_off.get("automatic_retry_performed") is not False
        or protective_off.get("automatic_recovery_performed") is not False
        or protective_off.get("switched_at")
        != W8_POST_ARM400_PROTECTIVE_OFF_BINDING["switched_at"]
        or _parse_time(protective_off["switched_at"])
        <= _parse_time(attempt["created_at"])
    ):
        raise W9PackError("W8 ARM-400 predecessor authority semantics differ")
    return {
        "t4_fault": deepcopy(t4_fault),
        "w8_attempt": deepcopy(attempt),
        "w8_claim": deepcopy(claim),
        "w8_post_arm400_protective_off": deepcopy(protective_off),
    }


# Compatibility name used by the generic runner guard.
def validate_fault_authority() -> dict[str, Any]:
    return validate_predecessor_authority()["t4_fault"]


def _source_binding() -> dict[str, Any]:
    report = w8.build_white_report()
    action = report["action"]
    return {
        "stage": w8.STAGE,
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "profile_id": report["contract"]["profile_id"],
        "predecessor_outcome_required": "claimed_attempt_failed_do_not_retry",
        "predecessor_arm_http_status_required": 400,
    }


def _obsolete_white_actions() -> list[str]:
    return [
        *w8.build_white_report()["contract"]["rejected_obsolete_white_action_ids"],
        w8.build_white_report()["action"]["action_id"],
    ]


def build_white_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    bound = _source_binding()
    action_seed = {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "source_campaign_id": bound["campaign_id"],
        "source_contract_id": bound["contract_id"],
        "source_descriptor_id": bound["descriptor_id"],
        "source_action_id": bound["action_id"],
        "frame_sha256": FACTORY_WHITE_FRAME_SHA256,
        "cs1_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
        "cs2_dtm_sha256": FACTORY_WHITE_DTM_SHA256,
    }
    authority_bindings = {
        "t4_terminal_fault_four_chain": {
            "source_failure": deepcopy(SOURCE_FAILURE_BINDING),
            "claim": deepcopy(CLAIM_BINDING),
            "raw_salvage": deepcopy(RAW_SALVAGE_BINDING),
            "reconciliation": deepcopy(FAULT_RECONCILIATION_BINDING),
        },
        "w8_consumed_arm400": {
            "attempt": deepcopy(W8_ATTEMPT_BINDING),
            "claim": deepcopy(W8_CLAIM_BINDING),
            "protective_off": deepcopy(W8_POST_ARM400_PROTECTIVE_OFF_BINDING),
        },
    }
    descriptor = {
        "schema": "mf1750-raw-p16-crossover-w9-w8-arm400-successor-white-descriptor-v1",
        "build_tag": CONFIG.build_tag,
        **action_seed,
        "predecessor_authority": authority_bindings,
        "rejected_obsolete_white_action_ids": _obsolete_white_actions(),
        "host_device_intent_parity_required": True,
        "arm_intent": WHITE_ARM_INTENT,
        "execute_intent": WHITE_EXECUTE_INTENT,
    }
    action = {**action_seed, "descriptor_id": sha256_bytes(canonical_json(descriptor))}
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR_WHITE_ACTION_V1|"
            f"{CONFIG.campaign_id}|{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = {
        "schema": "mf1750-raw-p16-crossover-w9-w8-arm400-successor-white-contract-v1",
        "white_stage": STAGE,
        "build_tag": CONFIG.build_tag,
        "test_id": CONFIG.test_id,
        "campaign_id": CONFIG.campaign_id,
        "source": bound,
        "source_campaign_id": bound["campaign_id"],
        "source_contract_id": bound["contract_id"],
        "source_descriptor_id": bound["descriptor_id"],
        "source_action_id": bound["action_id"],
        "predecessor_authority": authority_bindings,
        "original_t4_terminal_state_required": "FAULT",
        "original_t4_driver_call_count_required": 1,
        "original_t4_action_must_not_be_retried": True,
        "immediate_w8_outcome_required": "claimed_attempt_failed_do_not_retry",
        "immediate_w8_arm_http_status_required": 400,
        "immediate_w8_terminal_state_required": "NOT_EXECUTED",
        "immediate_w8_driver_call_count_required": 0,
        "immediate_w8_visible_refreshes_required": 0,
        "immediate_w8_action_must_not_be_retried": True,
        "immediate_w8_permanent_claim_required": True,
        "immediate_w8_post_arm400_protective_off_required": True,
        "source_terminal_state_required": "NOT_EXECUTED",
        "source_driver_call_count_required": 0,
        "source_complete_path_forbidden": True,
        "source_action_must_not_be_retried": True,
        "partial_visible_panel_mutation_possible": True,
        "panel_state_qualified": False,
        "fresh_fault_bound_white_containment_required": True,
        "protective_off_switch_receipt_required_before_live": True,
        "w8_post_arm400_protective_off_postdates_attempt": True,
        "fresh_user_physical_gnd_confirmation_required_before_j2_on": True,
        "operator_confirmed_disconnected_gnd": True,
        "operator_reported_physical_observation": "GND_WAS_RESEATED_AND_RECHECKED_OK",
        "disconnected_gnd_is_plausible_electrical_root_cause": True,
        "plausible_root_cause_is_not_retrospective_success_proof": True,
        "operator_report_does_not_retroactively_qualify_t4_or_w8": True,
        "rejected_obsolete_white_action_ids": _obsolete_white_actions(),
        "obsolete_white_execution_forbidden": True,
        "host_device_intent_parity_required": True,
        "arm_intent": WHITE_ARM_INTENT,
        "execute_intent": WHITE_EXECUTE_INTENT,
        "profile_id": "WF23_25",
        "base_route": CONFIG.base_route,
        "nvs_namespace": CONFIG.nvs_namespace,
        "nvs_key": CONFIG.nvs_key,
        "classification": CLASSIFICATION,
        "action": action,
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-w9-w8-arm400-successor-white-offline-identities-v1",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "white_stage": STAGE,
        "contract_id": sha256_bytes(canonical_json(contract)),
        "action": action,
        "contract": contract,
    }


def marker() -> str:
    return (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W9_W8_ARM400_SUCCESSOR|"
        f"SHA256={build_white_report()['action']['descriptor_id']}"
    )


def dry_validate(*, verify_source: bool = True, verify_authority: bool = True) -> dict[str, Any]:
    if verify_source and w8.dry_validate().get("result") != "PASS":
        raise W9PackError("W8 source dry validation did not PASS")
    authority = validate_predecessor_authority() if verify_authority else None
    intents = validate_intent_parity()
    report = build_white_report()
    action = report["action"]
    expected_action_keys = {
        "ordinal",
        "role",
        "source_campaign_id",
        "source_contract_id",
        "source_descriptor_id",
        "source_action_id",
        "descriptor_id",
        "action_id",
        "frame_sha256",
        "cs1_dtm_sha256",
        "cs2_dtm_sha256",
    }
    if set(action) != expected_action_keys:
        raise W9PackError("W9 wire action shape differs")
    w8_report = w8.build_white_report()
    if (
        action["source_campaign_id"] != w8_report["contract"]["campaign_id"]
        or action["source_contract_id"] != w8_report["contract_id"]
        or action["source_descriptor_id"] != w8_report["action"]["descriptor_id"]
        or action["source_action_id"] != w8_report["action"]["action_id"]
    ):
        raise W9PackError("W9 exact W8 predecessor tuple differs")
    obsolete = _obsolete_white_actions()
    if len(obsolete) != 4 or len(set(obsolete)) != 4 or action["action_id"] in obsolete:
        raise W9PackError("W9 obsolete white registry differs")
    if len(CONFIG.nvs_namespace) > 15 or len(CONFIG.nvs_key) > 15:
        raise W9PackError("W9 NVS name exceeds ESP32 limit")
    if CONFIG.base_route != (
        "/api/ec5/raw-p16-crossover-w9-after-w8-arm400-"
        "successor-factory-otp-white-v1"
    ):
        raise W9PackError("W9 route differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-raw-p16-crossover-w9-w8-arm400-successor-white-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "source_validation_required": verify_source,
        "predecessor_authority_required": verify_authority,
        "predecessor_authority_verified": verify_authority,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "factory_otp_white_only": True,
        "action_count": 1,
        "one_visible_refresh_per_action": True,
        "t4_fault_chain_bound": True,
        "w8_arm400_attempt_bound": True,
        "w8_claim_bound": True,
        "w8_post_arm400_protective_off_bound": True,
        "w8_retry_forbidden": True,
        "host_device_intent_parity": intents,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "artifacts_sealed": artifacts_are_sealed(),
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "authority_terminal_state": (
            None if authority is None else authority["t4_fault"]["terminal_state"]
        ),
    }


def main() -> int:
    print(json.dumps(build_white_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
