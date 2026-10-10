#!/usr/bin/env python3
"""Fresh T4 V5 after V4 was rejected by the host before any mutation.

V5 changes live identities and predecessor authorities only.  Its frame,
controller DTM streams, active global header, CA R20 assignment, and action
round remain byte-identical to V4.  V4 was never armed or executed, so the
completed W9 factory-white anchor remains the immediate pre-white authority.
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
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v4_pack as v4,
)
from tools import (  # noqa: E402
    mf1750_raw_p16_crossover_t4_v4_host_rejection_reconciliation_once as v4_rejection,
)


class T4MatchedSwapSuccessorV5PackError(RuntimeError):
    """Raised when a V5 identity, authority, or frozen payload differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t4-active-header-ca-r20-swap-confirmation-successor-v5"
    suffix: str = "T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V5"
    global_header: str = "active"
    cs1_profile: str = "commented"
    cs2_profile: str = "active"
    round: int = 4
    nvs_namespace: str = "p16t4ca_v5"
    nvs_key: str = "cur_t4ca5"
    nvs_boot_key: str = "boot_t4ca5"

    @property
    def variant_key(self) -> str:
        return (
            "L535_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V5"
        )

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V5_2026-09-01"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-T4-ACTIVE-HEADER-CA-R20-"
            "SWAP-CONFIRMATION-SUCCESSOR-V5"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V5"
        )

    @property
    def route_slug(self) -> str:
        return (
            "raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-v5"
        )

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_t4ca5"

    @property
    def build_root(self) -> str:
        return "b-t4ca5"


STAGE = "t4-active-header-ca-r20-swap-confirmation-successor-v5"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}
DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T4_MATCHED_SWAP_DEVICE_V5"
IDENTITY_REVISION = STAGE
CLASSIFICATION = v4.CLASSIFICATION
FACTORY_WHITE_ANCHOR_ROLE = v4.FACTORY_WHITE_ANCHOR_ROLE
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "SUCCESSOR_V5_ACTION_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_ARMED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "SUCCESSOR_V5_ACTION_ONCE"
)
CODE_ROWS = v4.CODE_ROWS
GRID_Y_BY_ROW = v4.GRID_Y_BY_ROW
PROFILE_ID = v4.PROFILE_ID
GLOBAL_TUPLE_ID = v4.GLOBAL_TUPLE_ID
HUMAN_OBSERVATION_PLAN = deepcopy(v4.HUMAN_OBSERVATION_PLAN)

v3 = v4.v3
V3_ACTION_ID = v4.V3_ACTION_ID
V4_ACTION_ID = v4.build_report()["actions"][0]["action_id"]

# This fixed evidence does not exist yet.  The all-zero binding is deliberate:
# build_report can describe the pre-authorized skeleton, but validate_authorities
# and every live/build postflight remain fail-closed until it is replaced with
# the independently sealed reconciliation file identity.
V4_HOST_REJECTION_BINDING: dict[str, int | str] = {
    "path": (
        ".test-output/hardware/MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_"
        "R20_SWAP_CONFIRMATION_SUCCESSOR_20260901_V4/"
        "action-01-host-runner-rejection-reconciled.json"
    ),
    "bytes": 28_704,
    "file_sha256": (
        "650576fa5506f6afe039296262c8bd76e15f73fb3d54aa4675507f36808114bb"
    ),
    "canonical_integrity_sha256": (
        "f4ed665890c9aed8ce8b70b56c8bffb97de4bd47a22ab2c6c8be1fd7141c2049"
    ),
}

ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 807_712,
        "bin_sha256": (
            "6302ae6c2ea234ea842dc281611b383cf746213d9d8790c7d8933be187b00672"
        ),
        "elf_bytes": 13_305_072,
        "elf_sha256": (
            "4c069dc14105a0f28093f2fa15288ca820dc0ff10b754cc87dfa7a3b7b970808"
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


def _read_bound(binding: Mapping[str, Any], label: str) -> dict[str, Any]:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or path.is_symlink():
        raise T4MatchedSwapSuccessorV5PackError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    if (
        len(payload) != binding["bytes"]
        or sha256_bytes(payload) != binding["file_sha256"]
    ):
        raise T4MatchedSwapSuccessorV5PackError(f"{label} file binding differs")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4MatchedSwapSuccessorV5PackError(
            f"{label} is not UTF-8 JSON"
        ) from error
    if not isinstance(value, dict):
        raise T4MatchedSwapSuccessorV5PackError(f"{label} JSON root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = (
        integrity.get("sha256", integrity.get("canonical_sha256"))
        if isinstance(integrity, Mapping)
        else None
    )
    if (
        recorded != binding["canonical_integrity_sha256"]
        or sha256_bytes(canonical_json(body)) != recorded
    ):
        raise T4MatchedSwapSuccessorV5PackError(
            f"{label} canonical binding differs"
        )
    return value


def rejection_binding_is_sealed() -> bool:
    item = V4_HOST_REJECTION_BINDING
    return (
        int(item["bytes"]) > 0
        and item["file_sha256"] != "0" * 64
        and item["canonical_integrity_sha256"] != "0" * 64
    )


@lru_cache(maxsize=1)
def _deep_validate_v4_rejection() -> tuple[int, str, str]:
    """Deep-check the immutable V4 evidence once without clobbering V5 host state."""

    mechanics = v4_rejection.once.mechanics
    mechanics_names = (
        "pack",
        "_output_root",
        "_claim_root",
        "source_route_leaked",
        "_bind_wire_action",
    )
    missing = object()
    saved_mechanics = {
        name: getattr(mechanics, name, missing) for name in mechanics_names
    }
    try:
        deeply_validated, payload = v4_rejection.validate_reconciliation(
            REPO_ROOT / str(V4_HOST_REJECTION_BINDING["path"])
        )
    except RuntimeError as error:
        raise T4MatchedSwapSuccessorV5PackError(
            "V4 host-runner rejection deep validation failed"
        ) from error
    finally:
        for name, prior in saved_mechanics.items():
            if prior is missing:
                try:
                    delattr(mechanics, name)
                except AttributeError:
                    pass
            else:
                setattr(mechanics, name, prior)
    validated_binding = deeply_validated.pop("_validated_file_binding", None)
    if not isinstance(validated_binding, Mapping):
        raise T4MatchedSwapSuccessorV5PackError(
            "V4 host-runner rejection validated binding missing"
        )
    return (
        len(payload),
        str(validated_binding.get("file_sha256")),
        str(validated_binding.get("canonical_integrity_sha256")),
    )


def v4_host_runner_rejection_binding(
    *, require_sealed: bool = True
) -> dict[str, Any]:
    """Return the exact zero-mutation V4 rejection authority."""

    if not rejection_binding_is_sealed():
        if require_sealed:
            raise T4MatchedSwapSuccessorV5PackError(
                "V4 host-runner rejection authority is not sealed"
            )
        return {
            **deepcopy(V4_HOST_REJECTION_BINDING),
            "sealed": False,
            "terminal_state": "NOT_EXECUTED",
            "host_rejected_before_network_claim_arm_execute": True,
            "network_requests": 0,
            "permanent_claims_created": 0,
            "arm_requests": 0,
            "execute_requests": 0,
            "driver_calls": 0,
            "visible_refreshes": 0,
            "w9_clean_white_remains_valid": True,
        }

    value = _read_bound(V4_HOST_REJECTION_BINDING, "V4 host-runner rejection")
    deep_bytes, deep_file_sha, deep_canonical_sha = _deep_validate_v4_rejection()
    if (
        deep_bytes != V4_HOST_REJECTION_BINDING["bytes"]
        or deep_file_sha != V4_HOST_REJECTION_BINDING["file_sha256"]
        or deep_canonical_sha
        != V4_HOST_REJECTION_BINDING["canonical_integrity_sha256"]
    ):
        raise T4MatchedSwapSuccessorV5PackError(
            "V4 host-runner rejection deep validation binding differs"
        )
    report = v4.build_report()
    action = report["actions"][0]
    # The exact kind is patched together with the sealed evidence.  These
    # mutation and lineage fields are invariant and already mandatory.
    if (
        value.get("campaign_id") != report["contract"]["campaign_id"]
        or value.get("contract_id") != report["contract_id"]
        or value.get("descriptor_id") != action["descriptor_id"]
        or value.get("action_id") != action["action_id"]
        or value.get("terminal_state") != "NOT_EXECUTED"
        or value.get("host_rejected_before_any_network_request") is not True
        or value.get("network_requests") != 0
        or value.get("permanent_claims_created") != 0
        or value.get("arm_requests") != 0
        or value.get("execute_requests") != 0
        or value.get("driver_call_count_for_action") != 0
        or value.get("total_driver_call_count") != 0
        or value.get("visible_refreshes") != 0
        or value.get("same_boot") is not True
        or value.get("w9_clean_white_remains_valid") is not True
        or value.get("v4_action_must_not_be_retried") is not True
    ):
        raise T4MatchedSwapSuccessorV5PackError(
            "V4 host-runner rejection semantics differ"
        )
    return {
        **deepcopy(V4_HOST_REJECTION_BINDING),
        "sealed": True,
        "kind": value.get("kind"),
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "terminal_state": "NOT_EXECUTED",
        "host_rejected_before_network_claim_arm_execute": True,
        "network_requests": 0,
        "permanent_claims_created": 0,
        "arm_requests": 0,
        "execute_requests": 0,
        "driver_calls": 0,
        "visible_refreshes": 0,
        "same_boot": True,
        "w9_clean_white_remains_valid": True,
        "retry_forbidden": True,
    }


def completed_t3_v2_action_binding() -> dict[str, Any]:
    return v4.completed_t3_v2_action_binding()


def completed_w9_white_action_binding() -> dict[str, Any]:
    return v4.completed_w9_white_action_binding()


def completed_w9_white_claim_binding() -> dict[str, Any]:
    return v4.completed_w9_white_claim_binding()


def w9_post_off_binding() -> dict[str, Any]:
    return v4.w9_post_off_binding()


def v3_terminal_fault_binding() -> dict[str, Any]:
    return v4.v3_terminal_fault_binding()


def completed_w4_white_action_binding() -> dict[str, Any]:
    """Compatibility name required by the inherited T4 host mechanics."""

    return completed_w9_white_action_binding()


OPERATOR_GND_ASSERTION = deepcopy(v4.OPERATOR_GND_ASSERTION)


def external_containment_contract() -> dict[str, Any]:
    return {
        "outside_campaign": True,
        "factory_otp_white_before_required": True,
        "factory_otp_white_after_required": True,
        "completed_w9_machine_white_anchor_present": True,
        "w9_clean_white_remains_valid_after_v4_host_rejection": True,
        "fresh_operator_clean_white_confirmation_required": True,
        "formal_full_panel_white_evidence": False,
        "human_observation_required": True,
        "white_actions_in_campaign": 0,
        "post_t4_v5_fresh_white_successor_required": True,
    }


def device_authority_surface(*, require_sealed: bool = True) -> dict[str, Any]:
    return {
        "t4_v3_terminal_fault": v3_terminal_fault_binding(),
        "pre_white_action_evidence": completed_w9_white_action_binding(),
        "w9_permanent_claim": completed_w9_white_claim_binding(),
        "w9_post_white_protective_off": w9_post_off_binding(),
        "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION),
        "t4_v4_host_runner_rejection": v4_host_runner_rejection_binding(
            require_sealed=require_sealed
        ),
    }


def validate_authorities() -> dict[str, Any]:
    return {
        "predecessor_chain": v4.validate_authorities(),
        **device_authority_surface(require_sealed=True),
    }


def non_reusable_action_ids() -> tuple[str, ...]:
    values = (*v4.non_reusable_action_ids(), V4_ACTION_ID)
    if len(values) != 19 or len(values) != len(set(values)):
        raise T4MatchedSwapSuccessorV5PackError(
            "V5 tombstone registry differs"
        )
    return values


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    item = ARTIFACTS[STAGE]
    return (
        int(item["bin_bytes"]) > 0
        and int(item["elf_bytes"]) > 0
        and item["bin_sha256"] != "0" * 64
        and item["elf_sha256"] != "0" * 64
    )


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    old_report = v4.build_report()
    old = old_report["actions"][0]
    action = deepcopy(old)
    for key in ("descriptor_id", "action_id"):
        action.pop(key, None)
    rejection = v4_host_runner_rejection_binding(require_sealed=False)
    action.update(
        {
            "role": (
                "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
                "SWAP_CONFIRMATION_SUCCESSOR_V5_ATLAS"
            ),
            "branch": (
                f"{CONFIG.variant_key}_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_"
                "R20_SWAP_CONFIRMATION_SUCCESSOR_V5_ATLAS"
            ),
            "pre_white_action_evidence": completed_w9_white_action_binding(),
            "pre_white_permanent_claim": completed_w9_white_claim_binding(),
            "supersedes_rejected_unconsumed_v4_action_id": V4_ACTION_ID,
            "v4_host_runner_rejection_authority": rejection,
            "w9_post_white_protective_off": w9_post_off_binding(),
            "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION),
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
        }
    )
    descriptor = {
        "schema": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-action-v5"
        ),
        "variant": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        **action,
        "non_reusable_action_ids": list(non_reusable_action_ids()),
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_ACTION_V5|"
            f"{CONFIG.variant_key}|1|{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = deepcopy(old_report["contract"])
    contract.update(
        {
            "schema": (
                "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-"
                "confirmation-successor-contract-v5"
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
            "external_containment": external_containment_contract(),
            "pre_white_action_evidence": completed_w9_white_action_binding(),
            "pre_white_permanent_claim": completed_w9_white_claim_binding(),
            "actions": [action],
            "v4_host_runner_rejection_authority": rejection,
            "v4_action_terminal_state": "NOT_EXECUTED",
            "v4_action_mutation_count": 0,
            "v4_action_must_not_be_retried": True,
            "w9_clean_white_anchor_remains_valid": True,
            "w9_post_white_protective_off": w9_post_off_binding(),
            "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION),
            "minimal_successor_fix": (
                "FRESH_IDENTITY_AFTER_V4_HOST_REJECTION_BEFORE_MUTATION_"
                "USING_STILL_VALID_W9_WHITE"
            ),
            "non_reusable_action_ids": list(non_reusable_action_ids()),
        }
    )
    return {
        "schema_version": 5,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-offline-identities-v5"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_action_authority": completed_t3_v2_action_binding(),
        "pre_white_action_evidence": completed_w9_white_action_binding(),
        "pre_white_permanent_claim": completed_w9_white_claim_binding(),
        "v4_host_runner_rejection_authority": rejection,
        "w9_post_white_protective_off": w9_post_off_binding(),
        "operator_gnd_assertion": deepcopy(OPERATOR_GND_ASSERTION),
        "actions": [action],
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


def dry_validate(*, verify_authorities: bool = True) -> dict[str, Any]:
    if verify_authorities:
        validate_authorities()
    report = build_report()
    action = report["actions"][0]
    old = v4.build_report()["actions"][0]
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
            raise T4MatchedSwapSuccessorV5PackError(
                f"V5 payload field {key} differs"
            )
    rejection = action["v4_host_runner_rejection_authority"]
    if (
        rejection["terminal_state"] != "NOT_EXECUTED"
        or rejection["network_requests"] != 0
        or rejection["permanent_claims_created"] != 0
        or rejection["arm_requests"] != 0
        or rejection["execute_requests"] != 0
        or rejection["driver_calls"] != 0
        or rejection["visible_refreshes"] != 0
        or rejection["w9_clean_white_remains_valid"] is not True
    ):
        raise T4MatchedSwapSuccessorV5PackError(
            "V5 zero-mutation rejection boundary differs"
        )
    if (
        non_reusable_action_ids()[-1] != V4_ACTION_ID
        or action["action_id"] in non_reusable_action_ids()
        or max(
            len(CONFIG.nvs_namespace),
            len(CONFIG.nvs_key),
            len(CONFIG.nvs_boot_key),
        )
        > 15
    ):
        raise T4MatchedSwapSuccessorV5PackError("V5 freshness gate differs")
    return {
        "schema_version": 5,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-swap-"
            "confirmation-successor-dry-validation-v5"
        ),
        "result": "PASS",
        "offline_only": True,
        "authority_verified": verify_authorities,
        "v4_rejection_authority_sealed": rejection_binding_is_sealed(),
        "hardware_accessed": False,
        "network_requests": 0,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "experimental_payload_byte_identical_to_v4": True,
        "experimental_payload_byte_identical_to_v3": True,
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "v4_action_terminal_state": "NOT_EXECUTED",
        "v4_mutation_count": 0,
        "w9_clean_white_anchor_remains_valid": True,
        "action_count": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "non_reusable_action_count": len(non_reusable_action_ids()),
        "artifacts_sealed": artifacts_are_sealed(),
    }


if __name__ == "__main__":
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
