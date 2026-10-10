#!/usr/bin/env python3
"""Fresh T4 V2 successor after the V1 no-mutation manifest diagnostic failure.

V2 preserves the V1 experimental payload byte-for-byte.  It changes every
live identity and adds the two explicit ``null`` prior-action fields which the
firmware serializes for ordinal one.  The sealed V1 diagnostic is an authority:
it proves four GETs, no POST, no claim, no driver call, and no visible refresh.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_v1_pack as v1,
)


class T4MatchedSwapSuccessorPackError(RuntimeError):
    """Raised when the V1 failure authority or fresh V2 closure differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t4-active-header-ca-r20-swap-confirmation-successor-v2"
    suffix: str = "T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V2"
    global_header: str = "active"
    cs1_profile: str = "commented"
    cs2_profile: str = "active"
    round: int = 4
    nvs_namespace: str = "p16t4ca_v2"
    nvs_key: str = "cur_t4ca2"
    nvs_boot_key: str = "boot_t4ca2"

    @property
    def variant_key(self) -> str:
        return (
            "L535_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V2"
        )

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V2_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-T4-ACTIVE-HEADER-CA-R20-"
            "SWAP-CONFIRMATION-SUCCESSOR-V2"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V2"
        )

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v2"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_t4ca2"

    @property
    def build_root(self) -> str:
        return "b-t4ca2"


STAGE = "t4-active-header-ca-r20-swap-confirmation-successor-v2"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T4_MATCHED_SWAP_DEVICE_V2"
IDENTITY_REVISION = STAGE
CLASSIFICATION = v1.CLASSIFICATION
FACTORY_WHITE_ANCHOR_ROLE = v1.FACTORY_WHITE_ANCHOR_ROLE
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "SUCCESSOR_V2_ACTION_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_ARMED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "SUCCESSOR_V2_ACTION_ONCE"
)
CODE_ROWS = v1.CODE_ROWS
GRID_Y_BY_ROW = v1.GRID_Y_BY_ROW
PROFILE_ID = v1.PROFILE_ID
GLOBAL_TUPLE_ID = v1.GLOBAL_TUPLE_ID
HUMAN_OBSERVATION_PLAN = deepcopy(v1.HUMAN_OBSERVATION_PLAN)

V1_DIAGNOSTIC_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_20260831_V1"
    / "j2-off-diagnostic.json"
)
V1_DIAGNOSTIC_BYTES = 29_355
V1_DIAGNOSTIC_FILE_SHA256 = (
    "615e82c79c527f3431669a1c29ce99d470bc50b92c921dcd2d8eea94e5617b21"
)
V1_DIAGNOSTIC_CANONICAL_SHA256 = (
    "5ea017045b3535b4a417e8917990f07d4beca8e7390cd3f899898b417e60897a"
)

# Filled only after an isolated compile and independent readback.
ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 803_888,
        "bin_sha256": (
            "861bf9f334a2a929ba4f126fa4ca64dfb62ff03ea1e4d4bda3e60e37f9981c1a"
        ),
        "elf_bytes": 13_300_488,
        "elf_sha256": (
            "c6c5736553559b336c922e85bbf385f0370c5a55512d680a59b55d6df8a38742"
        ),
    }
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


def _repo_relative(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


@lru_cache(maxsize=1)
def _v1_report() -> dict[str, Any]:
    return v1.build_report()


def v1_diagnostic_failure_binding() -> dict[str, Any]:
    action = _v1_report()["actions"][0]
    return {
        "kind": (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-v1-j2-off-diagnostic-attempt"
        ),
        "path": _repo_relative(V1_DIAGNOSTIC_PATH),
        "bytes": V1_DIAGNOSTIC_BYTES,
        "file_sha256": V1_DIAGNOSTIC_FILE_SHA256,
        "canonical_integrity_sha256": V1_DIAGNOSTIC_CANONICAL_SHA256,
        "campaign_id": _v1_report()["contract"]["campaign_id"],
        "contract_id": _v1_report()["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "outcome": "j2_off_diagnostic_failed_no_claim",
        "error_type": "RecheckError",
        "error_message": "crossover manifest actions differs",
        "get": 4,
        "post": 0,
        "permanent_claims_created": 0,
        "visible_refreshes": 0,
        "driver_calls": 0,
        "terminal_state": "NOT_EXECUTED",
        "safe_to_supersede_without_containment": True,
    }


def validate_v1_diagnostic_failure() -> dict[str, Any]:
    if not V1_DIAGNOSTIC_PATH.is_file() or V1_DIAGNOSTIC_PATH.is_symlink():
        raise T4MatchedSwapSuccessorPackError("sealed T4 V1 diagnostic missing")
    payload = V1_DIAGNOSTIC_PATH.read_bytes()
    if (
        len(payload) != V1_DIAGNOSTIC_BYTES
        or sha256_bytes(payload) != V1_DIAGNOSTIC_FILE_SHA256
    ):
        raise T4MatchedSwapSuccessorPackError("T4 V1 diagnostic file binding differs")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4MatchedSwapSuccessorPackError(
            "T4 V1 diagnostic is not UTF-8 JSON"
        ) from error
    body = dict(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("sha256") != V1_DIAGNOSTIC_CANONICAL_SHA256
        or sha256_bytes(canonical_json(body)) != V1_DIAGNOSTIC_CANONICAL_SHA256
    ):
        raise T4MatchedSwapSuccessorPackError(
            "T4 V1 diagnostic canonical binding differs"
        )
    status = next(
        item.get("response", {})
        for item in value.get("transcript", [])
        if item.get("endpoint") == "status"
    )
    report = next(
        item.get("response", {})
        for item in value.get("transcript", [])
        if item.get("endpoint") == "report"
    )
    binding = v1_diagnostic_failure_binding()
    if (
        value.get("kind") != binding["kind"]
        or value.get("campaign_id") != binding["campaign_id"]
        or value.get("contract_id") != binding["contract_id"]
        or value.get("outcome") != binding["outcome"]
        or value.get("error")
        != {"type": binding["error_type"], "message": binding["error_message"]}
        or value.get("j2_confirmed_off") is not True
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("claims_directory_accessed") is not False
        or value.get("permanent_claims_created") != 0
        or value.get("visible_refreshes") != 0
        or len(value.get("transcript", [])) != 4
        or [item.get("method") for item in value.get("transcript", [])]
        != ["GET", "GET", "GET", "GET"]
        or status.get("state") != "ready"
        or status.get("phase") != 0
        or status.get("arm_request_count") != 0
        or status.get("execute_request_count") != 0
        or status.get("total_driver_call_count") != 0
        or status.get("busy") != 0
        or report.get("terminal_state") != "NOT_EXECUTED"
        or report.get("driver_called") is not False
        or report.get("total_driver_call_count") != 0
    ):
        raise T4MatchedSwapSuccessorPackError(
            "T4 V1 diagnostic no-mutation semantics differ"
        )
    return {"binding": binding, "validated": True}


def validate_authorities() -> dict[str, Any]:
    return {
        "predecessor_chain": v1.validate_authorities(),
        "failed_v1_j2_off_diagnostic": validate_v1_diagnostic_failure(),
    }


def non_reusable_action_ids() -> tuple[str, ...]:
    values = (*v1.non_reusable_action_ids(), _v1_report()["actions"][0]["action_id"])
    if len(values) != len(set(values)):
        raise T4MatchedSwapSuccessorPackError(
            "T4 V2 non-reusable action registry overlaps"
        )
    return values


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    values = ARTIFACTS[STAGE]
    return (
        int(values["bin_bytes"]) > 0
        and int(values["elf_bytes"]) > 0
        and values["bin_sha256"] != "0" * 64
        and values["elf_sha256"] != "0" * 64
    )


def external_containment_contract() -> dict[str, Any]:
    return deepcopy(v1.external_containment_contract())


def completed_t3_v2_action_binding() -> dict[str, Any]:
    return v1.completed_t3_v2_action_binding()


def completed_w4_white_action_binding() -> dict[str, Any]:
    return v1.completed_w4_white_action_binding()


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    v1_report = _v1_report()
    v1_action = v1_report["actions"][0]
    failure = v1_diagnostic_failure_binding()
    action = deepcopy(v1_action)
    for key in ("descriptor_id", "action_id"):
        action.pop(key, None)
    action.update(
        {
            "role": (
                "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
                "SWAP_CONFIRMATION_SUCCESSOR_ATLAS"
            ),
            "branch": (
                f"{CONFIG.variant_key}_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_"
                "R20_SWAP_CONFIRMATION_SUCCESSOR_ATLAS"
            ),
            "boot_admission": {
                "campaign_boot_binding_key": CONFIG.nvs_boot_key,
                "admission": "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY",
                "required_prior_terminal_state": None,
                "required_prior_ordinal": None,
                "firmware_arm_gate": True,
                "firmware_execute_gate": True,
                "firmware_dispatch_gate": True,
                "reboot_resume_allowed": False,
                "post_containment_resume_allowed": False,
            },
            "supersedes_failed_unmutated_v1_action_id": v1_action["action_id"],
            "v1_diagnostic_failure_authority": failure,
        }
    )
    descriptor = {
        "schema": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-action-v2"
        ),
        "variant": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        **action,
        "non_reusable_action_ids": list(non_reusable_action_ids()),
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            f"CONFIRMATION_SUCCESSOR_ACTION_V2|{CONFIG.variant_key}|1|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = deepcopy(v1_report["contract"])
    contract.update(
        {
            "schema": (
                "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
                "swap-confirmation-successor-contract-v2"
            ),
            "stage": STAGE,
            "variant_key": CONFIG.variant_key,
            "build_tag": CONFIG.build_tag,
            "test_id": CONFIG.test_id,
            "campaign_id": CONFIG.campaign_id,
            "base_route": CONFIG.base_route,
            "nvs_namespace": CONFIG.nvs_namespace,
            "nvs_key": CONFIG.nvs_key,
            "nvs_boot_key": CONFIG.nvs_boot_key,
            "actions": [action],
            "v1_diagnostic_failure_authority": failure,
            "failed_v1_action_never_executed": True,
            "minimal_successor_fix": (
                "HOST_BOOT_ADMISSION_EXPLICIT_NULL_PRIOR_FIELDS"
            ),
            "non_reusable_action_ids": list(non_reusable_action_ids()),
        }
    )
    return {
        "schema_version": 2,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-offline-identities-v2"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_action_authority": v1.completed_t3_v2_action_binding(),
        "pre_white_action_evidence": v1.completed_w4_white_action_binding(),
        "v1_diagnostic_failure_authority": failure,
        "actions": [action],
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


def _prior_identity_values() -> frozenset[str]:
    report = _v1_report()
    action = report["actions"][0]
    return frozenset(
        {
            *v1._prior_identity_values(),  # noqa: SLF001
            report["contract_id"],
            action["descriptor_id"],
            action["action_id"],
            report["contract"]["campaign_id"],
            report["contract"]["test_id"],
            report["contract"]["base_route"],
            report["contract"]["nvs_namespace"],
        }
    )


def dry_validate(*, verify_authorities: bool = True) -> dict[str, Any]:
    if verify_authorities:
        validate_authorities()
    report = build_report()
    action = report["actions"][0]
    old = _v1_report()["actions"][0]
    for key in (
        "frame",
        "cs1_dtm",
        "cs2_dtm",
        "waveform_binding",
        "profile_id",
        "global_header",
        "global_tuple_id",
        "round",
    ):
        if action[key] != old[key]:
            raise T4MatchedSwapSuccessorPackError(
                f"T4 V2 experimental payload field {key} differs"
            )
    admission = action["boot_admission"]
    if (
        set(admission)
        != {
            "campaign_boot_binding_key",
            "admission",
            "required_prior_terminal_state",
            "required_prior_ordinal",
            "firmware_arm_gate",
            "firmware_execute_gate",
            "firmware_dispatch_gate",
            "reboot_resume_allowed",
            "post_containment_resume_allowed",
        }
        or admission["required_prior_terminal_state"] is not None
        or admission["required_prior_ordinal"] is not None
    ):
        raise T4MatchedSwapSuccessorPackError(
            "T4 V2 explicit-null boot admission differs"
        )
    fresh_values = {
        report["contract_id"],
        action["descriptor_id"],
        action["action_id"],
        report["contract"]["campaign_id"],
        report["contract"]["test_id"],
        report["contract"]["base_route"],
        report["contract"]["nvs_namespace"],
    }
    if fresh_values & _prior_identity_values():
        raise T4MatchedSwapSuccessorPackError("T4 V2 identity overlaps predecessor")
    if action["action_id"] in non_reusable_action_ids():
        raise T4MatchedSwapSuccessorPackError("fresh T4 V2 action is non-reusable")
    if len(CONFIG.nvs_namespace) > 15:
        raise T4MatchedSwapSuccessorPackError("T4 V2 NVS namespace too long")
    return {
        "schema_version": 2,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-dry-validation-v2"
        ),
        "result": "PASS",
        "offline_only": True,
        "authority_verified": verify_authorities,
        "device_requests_made": 0,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "v1_diagnostic_failed_without_mutation": True,
        "explicit_null_prior_fields_aligned": True,
        "experimental_payload_byte_identical_to_v1": True,
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "consumed_and_failed_v1_actions_non_reusable": True,
        "action_count": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "v1_diagnostic_failure_authority": v1_diagnostic_failure_binding(),
        "non_reusable_action_count": len(non_reusable_action_ids()),
        "artifacts_sealed": artifacts_are_sealed(),
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
