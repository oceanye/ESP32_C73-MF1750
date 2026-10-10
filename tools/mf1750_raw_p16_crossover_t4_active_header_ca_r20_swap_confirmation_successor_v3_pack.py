#!/usr/bin/env python3
"""Fresh T4 V3 successor after two read-only diagnostic failures.

V3 keeps the matched-swap experimental payload byte-identical to V1/V2.  It
permanently tombstones both failed actions and aligns the firmware-emitted
``non_reusable_action_ids`` registry with the host's 15-entry registry.  The
sealed V2 four-GET transcript is replayed through every host validator after
normalizing only the already-proven V2 registry omission.
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
    mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_pack as v2,
)


class T4MatchedSwapSuccessorV3PackError(RuntimeError):
    """Raised when a failure authority or the fresh V3 closure differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t4-active-header-ca-r20-swap-confirmation-successor-v3"
    suffix: str = "T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_V3"
    global_header: str = "active"
    cs1_profile: str = "commented"
    cs2_profile: str = "active"
    round: int = 4
    nvs_namespace: str = "p16t4ca_v3"
    nvs_key: str = "cur_t4ca3"
    nvs_boot_key: str = "boot_t4ca3"

    @property
    def variant_key(self) -> str:
        return (
            "L535_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V3"
        )

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V3_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return (
            "EC5-RAW-P16-CROSSOVER-T4-ACTIVE-HEADER-CA-R20-"
            "SWAP-CONFIRMATION-SUCCESSOR-V3"
        )

    @property
    def campaign_id(self) -> str:
        return (
            "EC5_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V3"
        )

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t4-active-header-ca-r20-swap-confirmation-successor-v3"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_p16_t4ca3"

    @property
    def build_root(self) -> str:
        return "b-t4ca3"


STAGE = "t4-active-header-ca-r20-swap-confirmation-successor-v3"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T4_MATCHED_SWAP_DEVICE_V3"
IDENTITY_REVISION = STAGE
CLASSIFICATION = v2.CLASSIFICATION
FACTORY_WHITE_ANCHOR_ROLE = v2.FACTORY_WHITE_ANCHOR_ROLE
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "SUCCESSOR_V3_ACTION_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_ARMED_RAW_P16_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_"
    "SUCCESSOR_V3_ACTION_ONCE"
)
CODE_ROWS = v2.CODE_ROWS
GRID_Y_BY_ROW = v2.GRID_Y_BY_ROW
PROFILE_ID = v2.PROFILE_ID
GLOBAL_TUPLE_ID = v2.GLOBAL_TUPLE_ID
HUMAN_OBSERVATION_PLAN = deepcopy(v2.HUMAN_OBSERVATION_PLAN)

V2_DIAGNOSTIC_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_SWAP_CONFIRMATION_SUCCESSOR_20260831_V2"
    / "j2-off-diagnostic.json"
)
V2_DIAGNOSTIC_BYTES = 29_616
V2_DIAGNOSTIC_FILE_SHA256 = (
    "7abe07fb9641b504ba7a8b864588c182babcc7b1e928e2f3a8789ede3c3bb3e9"
)
V2_DIAGNOSTIC_CANONICAL_SHA256 = (
    "37bf7feff9e39bded9beb62ce87a945076a46fd62dc0bdbe5f2dd07efc135ebb"
)

# Sealed after an isolated compile and independent hash readback.
ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 804_032,
        "bin_sha256": (
            "c3af3f805a78b586f035c2cbf20b8948fe8ff2f79ccb33b956b3eb79adb6765f"
        ),
        "elf_bytes": 13_300_688,
        "elf_sha256": (
            "9d0bf06fb975f1739efff513a44e0c6980db99d8f4b7ab2819b1d79af3f6522c"
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
def _v2_report() -> dict[str, Any]:
    return v2.build_report()


def v1_diagnostic_failure_binding() -> dict[str, Any]:
    return deepcopy(v2.v1_diagnostic_failure_binding())


def v2_diagnostic_failure_binding() -> dict[str, Any]:
    action = _v2_report()["actions"][0]
    return {
        "kind": (
            "mf1750-ec5-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-v2-j2-off-diagnostic-attempt"
        ),
        "path": _repo_relative(V2_DIAGNOSTIC_PATH),
        "bytes": V2_DIAGNOSTIC_BYTES,
        "file_sha256": V2_DIAGNOSTIC_FILE_SHA256,
        "canonical_integrity_sha256": V2_DIAGNOSTIC_CANONICAL_SHA256,
        "campaign_id": _v2_report()["contract"]["campaign_id"],
        "contract_id": _v2_report()["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "outcome": "j2_off_diagnostic_failed_no_claim",
        "error_type": "RecheckError",
        "error_message": "T4 matched-swap non_reusable_action_ids differs",
        "get": 4,
        "post": 0,
        "permanent_claims_created": 0,
        "visible_refreshes": 0,
        "driver_calls": 0,
        "terminal_state": "NOT_EXECUTED",
        "safe_to_supersede_without_containment": True,
    }


def _load_bound_v2_diagnostic() -> dict[str, Any]:
    if not V2_DIAGNOSTIC_PATH.is_file() or V2_DIAGNOSTIC_PATH.is_symlink():
        raise T4MatchedSwapSuccessorV3PackError("sealed T4 V2 diagnostic missing")
    payload = V2_DIAGNOSTIC_PATH.read_bytes()
    if (
        len(payload) != V2_DIAGNOSTIC_BYTES
        or sha256_bytes(payload) != V2_DIAGNOSTIC_FILE_SHA256
    ):
        raise T4MatchedSwapSuccessorV3PackError(
            "T4 V2 diagnostic file binding differs"
        )
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T4MatchedSwapSuccessorV3PackError(
            "T4 V2 diagnostic is not UTF-8 JSON"
        ) from error
    body = dict(value)
    integrity = body.pop("integrity", None)
    if (
        not isinstance(integrity, Mapping)
        or integrity.get("sha256") != V2_DIAGNOSTIC_CANONICAL_SHA256
        or sha256_bytes(canonical_json(body)) != V2_DIAGNOSTIC_CANONICAL_SHA256
    ):
        raise T4MatchedSwapSuccessorV3PackError(
            "T4 V2 diagnostic canonical binding differs"
        )
    return value


@lru_cache(maxsize=1)
def replay_v2_transcript_after_known_registry_normalization() -> dict[str, Any]:
    """Replay all four host validators while normalizing only V2's known list."""

    value = _load_bound_v2_diagnostic()
    binding = v2_diagnostic_failure_binding()
    transcript = value.get("transcript", [])
    observed = {item.get("endpoint"): item.get("response", {}) for item in transcript}
    status = observed.get("status", {})
    report = observed.get("report", {})
    v2_device_registry = list(v2.v1.non_reusable_action_ids())
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
        or len(transcript) != 4
        or [item.get("method") for item in transcript]
        != ["GET", "GET", "GET", "GET"]
        or set(observed) != {"version", "manifest", "status", "report"}
        or observed["version"].get("non_reusable_action_ids")
        != v2_device_registry
        or observed["manifest"].get("non_reusable_action_ids")
        != v2_device_registry
        or status.get("state") != "ready"
        or status.get("total_driver_call_count") != 0
        or report.get("terminal_state") != "NOT_EXECUTED"
        or report.get("driver_called") is not False
    ):
        raise T4MatchedSwapSuccessorV3PackError(
            "T4 V2 diagnostic no-mutation or known-registry shape differs"
        )

    # The live failure happened only because the firmware emitted the 13-entry
    # predecessor registry while the V2 host expected 14 entries.  Preserve all
    # other bytes semantically and replay every validator with only that field
    # normalized in the review-boundary layer.
    from tools import (  # noqa: PLC0415
        mf1750_raw_p16_crossover_t4_active_header_ca_r20_swap_confirmation_successor_v2_once as v2_once,
    )

    # ``v2_once.configure()`` installs the V2 pack and roots into the shared
    # V1 mechanics module.  A V3 cold-process configure can enter this replay
    # while those globals are already bound to V3, so restoring only the
    # review callback would silently leave the outer V3 configure on V2.
    # Snapshot every global touched by ``_install_v2_mechanics`` and restore
    # them unconditionally after the read-only replay.
    mechanics = v2_once.mechanics
    original_mechanics = {
        "pack": mechanics.pack,
        "_output_root": mechanics._output_root,  # noqa: SLF001
        "_claim_root": mechanics._claim_root,  # noqa: SLF001
        "source_route_leaked": mechanics.source_route_leaked,
        "_bind_wire_action": mechanics._bind_wire_action,  # noqa: SLF001
        "_validate_review_boundary": mechanics._validate_review_boundary,  # noqa: SLF001
    }
    original_boundary = original_mechanics["_validate_review_boundary"]

    def normalized_boundary(host: Any, response: Mapping[str, Any]) -> None:
        normalized = deepcopy(dict(response))
        normalized["non_reusable_action_ids"] = list(v2.non_reusable_action_ids())
        original_boundary(host, normalized)

    try:
        v2_once.mechanics._validate_review_boundary = normalized_boundary  # noqa: SLF001
        host = v2_once.configure()
        host._validate_version(observed["version"])  # noqa: SLF001
        host._validate_manifest(observed["manifest"])  # noqa: SLF001
        boot_nonce = host._validate_ready_status(  # noqa: SLF001
            observed["status"], 1, expected_busy=0
        )
        host.v3.v1._validate_fresh_no_execute_report(  # noqa: SLF001
            observed["report"], boot_nonce
        )
    finally:
        for name, original in original_mechanics.items():
            setattr(mechanics, name, original)
    return {
        "result": "PASS",
        "offline_only": True,
        "normalized_field": "non_reusable_action_ids",
        "device_registry_count": len(v2_device_registry),
        "v2_host_registry_count": len(v2.non_reusable_action_ids()),
        "validators": ["version", "manifest", "status", "report"],
        "network_requests": 0,
        "hardware_accessed": False,
        "relay_accessed": False,
        "display_refreshed": False,
    }


def validate_v2_diagnostic_failure() -> dict[str, Any]:
    replay = replay_v2_transcript_after_known_registry_normalization()
    return {
        "binding": v2_diagnostic_failure_binding(),
        "validated": True,
        "full_transcript_replay": replay,
    }


def validate_authorities() -> dict[str, Any]:
    return {
        "predecessor_chain": v2.validate_authorities(),
        "failed_v2_j2_off_diagnostic": validate_v2_diagnostic_failure(),
    }


def non_reusable_action_ids() -> tuple[str, ...]:
    values = (*v2.non_reusable_action_ids(), _v2_report()["actions"][0]["action_id"])
    if len(values) != 15 or len(values) != len(set(values)):
        raise T4MatchedSwapSuccessorV3PackError(
            "T4 V3 non-reusable action registry must contain 15 unique entries"
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
    return deepcopy(v2.external_containment_contract())


def completed_t3_v2_action_binding() -> dict[str, Any]:
    return v2.completed_t3_v2_action_binding()


def completed_w4_white_action_binding() -> dict[str, Any]:
    return v2.completed_w4_white_action_binding()


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    v2_report = _v2_report()
    v2_action = v2_report["actions"][0]
    action = deepcopy(v2_action)
    for key in ("descriptor_id", "action_id"):
        action.pop(key, None)
    action.update(
        {
            "role": (
                "RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_R20_"
                "SWAP_CONFIRMATION_SUCCESSOR_V3_ATLAS"
            ),
            "branch": (
                f"{CONFIG.variant_key}_RAW_P16_CROSSOVER_T4_ACTIVE_HEADER_CA_"
                "R20_SWAP_CONFIRMATION_SUCCESSOR_V3_ATLAS"
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
            "supersedes_failed_unmutated_v2_action_id": v2_action["action_id"],
            "v1_diagnostic_failure_authority": v1_diagnostic_failure_binding(),
            "v2_diagnostic_failure_authority": v2_diagnostic_failure_binding(),
        }
    )
    descriptor = {
        "schema": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-action-v3"
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
            f"CONFIRMATION_SUCCESSOR_ACTION_V3|{CONFIG.variant_key}|1|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )
    contract = deepcopy(v2_report["contract"])
    contract.update(
        {
            "schema": (
                "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
                "swap-confirmation-successor-contract-v3"
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
            "v1_diagnostic_failure_authority": v1_diagnostic_failure_binding(),
            "v2_diagnostic_failure_authority": v2_diagnostic_failure_binding(),
            "failed_v1_action_never_executed": True,
            "failed_v2_action_never_executed": True,
            "minimal_successor_fix": (
                "DEVICE_AND_HOST_NON_REUSABLE_ACTION_REGISTRY_ALIGNED"
            ),
            "non_reusable_action_ids": list(non_reusable_action_ids()),
        }
    )
    return {
        "schema_version": 3,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-offline-identities-v3"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_action_authority": v2.completed_t3_v2_action_binding(),
        "pre_white_action_evidence": v2.completed_w4_white_action_binding(),
        "v1_diagnostic_failure_authority": v1_diagnostic_failure_binding(),
        "v2_diagnostic_failure_authority": v2_diagnostic_failure_binding(),
        "actions": [action],
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


def _prior_identity_values() -> frozenset[str]:
    report = _v2_report()
    action = report["actions"][0]
    return frozenset(
        {
            *v2._prior_identity_values(),  # noqa: SLF001
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
    old = _v2_report()["actions"][0]
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
            raise T4MatchedSwapSuccessorV3PackError(
                f"T4 V3 experimental payload field {key} differs"
            )
    expected_tail = (
        v2.v1.build_report()["actions"][0]["action_id"],
        old["action_id"],
    )
    if non_reusable_action_ids()[-2:] != expected_tail:
        raise T4MatchedSwapSuccessorV3PackError(
            "T4 V3 failure tombstone order differs"
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
        raise T4MatchedSwapSuccessorV3PackError(
            "T4 V3 identity overlaps predecessor"
        )
    if action["action_id"] in non_reusable_action_ids():
        raise T4MatchedSwapSuccessorV3PackError("fresh T4 V3 action is non-reusable")
    if len(CONFIG.nvs_namespace) > 15:
        raise T4MatchedSwapSuccessorV3PackError("T4 V3 NVS namespace too long")
    return {
        "schema_version": 3,
        "kind": (
            "mf1750-raw-p16-crossover-t4-active-header-ca-r20-"
            "swap-confirmation-successor-dry-validation-v3"
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
        "v1_and_v2_diagnostics_failed_without_mutation": True,
        "v2_full_four_get_transcript_replayed": True,
        "v2_only_known_registry_mismatch_normalized": True,
        "device_and_host_registry_count": 15,
        "experimental_payload_byte_identical_to_v1_v2": True,
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "consumed_and_failed_actions_non_reusable": True,
        "action_count": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "v1_diagnostic_failure_authority": v1_diagnostic_failure_binding(),
        "v2_diagnostic_failure_authority": v2_diagnostic_failure_binding(),
        "non_reusable_action_count": len(non_reusable_action_ids()),
        "artifacts_sealed": artifacts_are_sealed(),
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
