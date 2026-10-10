#!/usr/bin/env python3
"""Offline identities for the fresh T3 AC profile-following successor V2.

V2 preserves the V1 atlas bytes and AC waveform tuple.  It exists because the
V1 application was written and booted once, then its first read-only GET was
refused before any claim, POST, ARM, EXECUTE, or visible refresh.  V1 remains
immutable terminal evidence and is never re-authorized by this pack.
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
    mf1750_raw_p16_crossover_t3_ac_profile_following_successor_pack as frozen,
)


class T3ProfileFollowingPackError(RuntimeError):
    """Raised when the frozen V1 boundary or fresh V2 identity differs."""


@dataclass(frozen=True)
class StageConfig:
    key: str = "t3-ac-profile-following-successor-v2"
    suffix: str = "T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2"
    global_header: str = "active"
    cs1_profile: str = "active"
    cs2_profile: str = "commented"
    round: int = 3
    repeat_of: str = frozen.STAGE
    nvs_namespace: str = "p16t3pf_v2"
    nvs_key: str = "cur_t3pf2"
    nvs_boot_key: str = "boot_t3pf2"

    @property
    def variant_key(self) -> str:
        return "L535_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2"

    @property
    def build_tag(self) -> str:
        return (
            "MF1750_EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V2_2026-08-31"
        )

    @property
    def test_id(self) -> str:
        return "EC5-RAW-P16-CROSSOVER-T3-AC-PROFILE-FOLLOWING-SUCCESSOR-V2"

    @property
    def campaign_id(self) -> str:
        return "EC5_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_V2"

    @property
    def route_slug(self) -> str:
        return "raw-p16-crossover-t3-ac-profile-following-successor-v2"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"

    @property
    def environment(self) -> str:
        return "ec5_raw_p16_crossover_t3_ac_profile_following_successor_v2"

    @property
    def build_root(self) -> str:
        return "build-raw-p16-crossover-t3-ac-profile-following-successor-v2"


STAGE = "t3-ac-profile-following-successor-v2"
CONFIG = StageConfig()
STAGES = {STAGE: CONFIG}

DEVICE_API_VERSION = "MF1750_EC5_RAW_P16_CROSSOVER_T3_PROFILE_FOLLOWING_DEVICE_V2"
IDENTITY_REVISION = "raw-p16-crossover-t3-ac-profile-following-successor-v2"
CLASSIFICATION = (
    "EXPERIMENTAL_HUMAN_PRIMARY_PROFILE_FOLLOWING_REVIEW_ONLY_T3_AC_SWAP_"
    "SUCCESSOR_V2_AFTER_FAILED_UNMUTATED_V1_NOT_FORMAL_GATE_NOT_COLOUR_"
    "QUALIFICATION_ZERO_QUALIFIED_COLOURS"
)
FACTORY_WHITE_ANCHOR_ROLE = frozen.FACTORY_WHITE_ANCHOR_ROLE
ARM_INTENT = (
    "ARM_ONE_FIXED_RAW_P16_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ACTION_"
    "NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_ARMED_RAW_P16_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ACTION_ONCE"
)

CODE_ROWS = frozen.CODE_ROWS
GRID_Y_BY_ROW = frozen.GRID_Y_BY_ROW
HUMAN_OBSERVATION_PLAN = deepcopy(frozen.HUMAN_OBSERVATION_PLAN)

V1_ROOT = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260830_V1"
)
V1_FLASH_PATH = V1_ROOT / "app-only-single-boot-flash.json"
V1_FLASH_BYTES = 7_069
V1_FLASH_FILE_SHA256 = (
    "d72f41f9af347437a394e19cd59759a7331a4aa5496ee74cf84123992788897c"
)
V1_FLASH_CANONICAL_SHA256 = (
    "c26d53af7c7acba53fc5f6728acddcda88be17ba4b3d73e7c9073d6817987699"
)
V1_DIAGNOSTIC_PATH = V1_ROOT / "j2-off-diagnostic.json"
V1_DIAGNOSTIC_BYTES = 2_112
V1_DIAGNOSTIC_FILE_SHA256 = (
    "8bd0510a539a93d7a0d4740dd550c8d0535f06805061e7ee8708a944d63ae738"
)
V1_DIAGNOSTIC_CANONICAL_SHA256 = (
    "9fd138531d6ee762313904d30f86d26549a2519a43ea026a4c9c23f387f20194"
)
V1_RELAY_OFF_PATH = (
    V1_ROOT / "relay-post-diagnostic-failure-off-query-20260831-133811130.json"
)
V1_RELAY_OFF_BYTES = 1_248
V1_RELAY_OFF_FILE_SHA256 = (
    "345973ac5bde6f4488d66279f7072479512c4edbf1c8339b3af374b2f0ab49db"
)
V1_RELAY_OFF_CANONICAL_SHA256 = (
    "09975b2f3076f229f7f6b058cb9ea65f77107f075e2c3a90e8875999fc1f5231"
)

V1_ACTION_OUTPUT = V1_ROOT / "action-01-position-balanced-atlas.json"
V1_CLAIM_ROOT = (
    REPO_ROOT
    / ".test-output/hardware"
    / ".mf1750_raw_p16_crossover_t3_ac_profile_following_successor_v1_claims"
)

PASSIVE_ADDRESS_EVIDENCE_PATH = (
    REPO_ROOT
    / ".test-output/hardware"
    / "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_20260831_V2_PREP"
    / "passive-ipv4-mac-candidate-binding.json"
)
PASSIVE_ADDRESS_EVIDENCE_BYTES = 2_850
PASSIVE_ADDRESS_EVIDENCE_FILE_SHA256 = (
    "4c2fe6c04c90119a776099a187340fa91f8e7cb0b92482ada232af201ebe8fd8"
)
PASSIVE_ADDRESS_EVIDENCE_CANONICAL_SHA256 = (
    "704866219593232cfa737b2fd9134d4d305722d764d3a3024af42a0242628dbf"
)
V1_FAILED_BASE_URL_IPV4 = "192.168.1.7"
PASSIVE_CANDIDATE_IPV4 = "192.168.1.11"
PASSIVE_CANDIDATE_MAC = "A4-CB-8F-D9-FC-D4"

# Filled after the isolated V2 build is complete and re-read.
ARTIFACTS: dict[str, dict[str, int | str]] = {
    STAGE: {
        "bin_bytes": 808_336,
        "bin_sha256": (
            "94ea921532d44009c8e6aef645a51bd1a1f0386fb7d86ca8da115ad8c0fb2578"
        ),
        "elf_bytes": 13_303_616,
        "elf_sha256": (
            "bda4c0bdce15a5deefcb394ef10d021c542c0bdd2163989ae0f2f4607e8ae981"
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


def _read_exact_json(
    path: Path,
    *,
    byte_count: int,
    file_sha256: str,
    canonical_sha256: str,
    label: str,
) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise T3ProfileFollowingPackError(f"{label} is missing or not regular")
    payload = path.read_bytes()
    if len(payload) != byte_count or sha256_bytes(payload) != file_sha256:
        raise T3ProfileFollowingPackError(f"{label} file binding differs")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise T3ProfileFollowingPackError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise T3ProfileFollowingPackError(f"{label} root differs")
    body = dict(value)
    integrity = body.pop("integrity", None)
    observed = sha256_bytes(canonical_json(body))
    if observed != canonical_sha256 or not isinstance(integrity, Mapping):
        raise T3ProfileFollowingPackError(f"{label} canonical binding differs")
    recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
    if recorded != canonical_sha256:
        raise T3ProfileFollowingPackError(f"{label} recorded integrity differs")
    return value


def completed_t2_v2_action_binding() -> dict[str, Any]:
    return frozen.completed_t2_v2_action_binding()


def completed_w3_white_action_binding() -> dict[str, Any]:
    return frozen.completed_w3_white_action_binding()


def pre_white_authority_binding() -> dict[str, Any]:
    return frozen.pre_white_authority_binding()


def validate_completed_t2_v2_action() -> dict[str, Any]:
    return frozen.validate_completed_t2_v2_action()


def validate_completed_w3_white_action() -> dict[str, Any]:
    return frozen.validate_completed_w3_white_action()


def validate_pre_white_authority() -> dict[str, Any]:
    return frozen.validate_pre_white_authority()


@lru_cache(maxsize=1)
def _v1_identity() -> dict[str, str]:
    report = frozen.build_report()
    action = report["actions"][0]
    return {
        "campaign_id": report["contract"]["campaign_id"],
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
    }


def v1_failure_authority_binding() -> dict[str, Any]:
    identity = _v1_identity()
    return {
        "kind": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-successor-"
            "v1-terminal-failure-authority"
        ),
        "predecessor_campaign_id": identity["campaign_id"],
        "predecessor_contract_id": identity["contract_id"],
        "predecessor_descriptor_id": identity["descriptor_id"],
        "predecessor_action_id": identity["action_id"],
        "flash_evidence": {
            "path": _repo_relative(V1_FLASH_PATH),
            "bytes": V1_FLASH_BYTES,
            "file_sha256": V1_FLASH_FILE_SHA256,
            "canonical_integrity_sha256": V1_FLASH_CANONICAL_SHA256,
            "outcome": "app_only_write_verify_single_boot_pass",
        },
        "failed_diagnostic_evidence": {
            "path": _repo_relative(V1_DIAGNOSTIC_PATH),
            "bytes": V1_DIAGNOSTIC_BYTES,
            "file_sha256": V1_DIAGNOSTIC_FILE_SHA256,
            "canonical_integrity_sha256": V1_DIAGNOSTIC_CANONICAL_SHA256,
            "outcome": "j2_off_diagnostic_failed_no_claim",
            "network_get": 1,
            "network_post": 0,
            "permanent_claims_created": 0,
            "visible_refreshes": 0,
        },
        "final_relay_off_evidence": {
            "path": _repo_relative(V1_RELAY_OFF_PATH),
            "bytes": V1_RELAY_OFF_BYTES,
            "file_sha256": V1_RELAY_OFF_FILE_SHA256,
            "canonical_integrity_sha256": V1_RELAY_OFF_CANONICAL_SHA256,
            "commanded_state": "OFF",
            "off_gate_passed": True,
            "electrical_state_proven": False,
        },
        "predecessor_action_output_absent_required": True,
        "predecessor_claim_absent_required": True,
        "predecessor_action_never_claimed_or_executed": True,
        "not_retry_of_predecessor": True,
        "does_not_reauthorize_v1": True,
    }


def address_resolution_boundary_binding() -> dict[str, Any]:
    """Return passive address evidence without promoting it to device identity."""

    return {
        "kind": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-successor-"
            "v2-passive-address-resolution-boundary"
        ),
        "evidence": {
            "path": _repo_relative(PASSIVE_ADDRESS_EVIDENCE_PATH),
            "bytes": PASSIVE_ADDRESS_EVIDENCE_BYTES,
            "file_sha256": PASSIVE_ADDRESS_EVIDENCE_FILE_SHA256,
            "canonical_integrity_sha256": (
                PASSIVE_ADDRESS_EVIDENCE_CANONICAL_SHA256
            ),
        },
        "v1_failed_base_url_ipv4_is_host_owned": V1_FAILED_BASE_URL_IPV4,
        "passive_candidate_ipv4": PASSIVE_CANDIDATE_IPV4,
        "passive_candidate_mac": PASSIVE_CANDIDATE_MAC,
        "passive_neighbour_state": "STALE",
        "passive_network_layer_mac_binding_observed": True,
        "fresh_binding_proven": False,
        "device_application_identity_proven": False,
        "candidate_is_default_base_url": False,
        "live_base_url_must_be_explicit": True,
        "fresh_exact_binding_required_before_future_live_io": True,
        "does_not_authorize_network_or_device_io": True,
    }


def validate_address_resolution_boundary() -> dict[str, Any]:
    value = _read_exact_json(
        PASSIVE_ADDRESS_EVIDENCE_PATH,
        byte_count=PASSIVE_ADDRESS_EVIDENCE_BYTES,
        file_sha256=PASSIVE_ADDRESS_EVIDENCE_FILE_SHA256,
        canonical_sha256=PASSIVE_ADDRESS_EVIDENCE_CANONICAL_SHA256,
        label="T3 V2 passive IPv4/MAC candidate evidence",
    )
    local_ipv4 = value.get("local_ipv4")
    neighbours = value.get("neighbour_entries")
    if (
        value.get("kind") != "mf1750-exact-ipv4-mac-binding-attempt-v1"
        or value.get("candidate_ipv4") != PASSIVE_CANDIDATE_IPV4
        or value.get("expected_mac") != PASSIVE_CANDIDATE_MAC
        or value.get("active_probe_authorized") is not False
        or value.get("active_probe")
        != {"attempts": 0, "kind": "none_passive_neighbour_snapshot_only"}
        or value.get("binding_passed") is not True
        or value.get("fresh_binding_passed") is not False
        or value.get("network_layer_mac_binding_observed") is not True
        or value.get("device_application_identity_proven") is not False
        or value.get("outcome")
        != "passive_exact_mac_binding_observed_not_freshness_proof"
        or value.get("http_requests") != 0
        or value.get("device_api_requests") != 0
        or value.get("mutation_requests") != 0
        or value.get("visible_refresh_requests") != 0
        or value.get("retry") is not False
        or value.get("fallback") is not False
        or value.get("scan") is not False
        or not isinstance(local_ipv4, list)
        or not any(
            isinstance(item, Mapping)
            and item.get("IPAddress") == V1_FAILED_BASE_URL_IPV4
            for item in local_ipv4
        )
        or not isinstance(neighbours, list)
        or len(neighbours) != 1
        or neighbours[0].get("IPAddress") != PASSIVE_CANDIDATE_IPV4
        or neighbours[0].get("LinkLayerAddress") != PASSIVE_CANDIDATE_MAC
        # Windows' MSFT_NetNeighbor enum serializes STALE as integer 4 here.
        or neighbours[0].get("State") != 4
        or value.get("observed_state") != "4"
    ):
        raise T3ProfileFollowingPackError(
            "T3 V2 passive IPv4/MAC candidate semantics differ"
        )
    return {
        "binding": address_resolution_boundary_binding(),
        "passive_only": True,
        "freshness_proven": False,
        "device_application_identity_proven": False,
    }


def validate_v1_failure_authority() -> dict[str, Any]:
    flash = _read_exact_json(
        V1_FLASH_PATH,
        byte_count=V1_FLASH_BYTES,
        file_sha256=V1_FLASH_FILE_SHA256,
        canonical_sha256=V1_FLASH_CANONICAL_SHA256,
        label="T3 V1 app-only flash evidence",
    )
    diagnostic = _read_exact_json(
        V1_DIAGNOSTIC_PATH,
        byte_count=V1_DIAGNOSTIC_BYTES,
        file_sha256=V1_DIAGNOSTIC_FILE_SHA256,
        canonical_sha256=V1_DIAGNOSTIC_CANONICAL_SHA256,
        label="T3 V1 failed diagnostic evidence",
    )
    relay = _read_exact_json(
        V1_RELAY_OFF_PATH,
        byte_count=V1_RELAY_OFF_BYTES,
        file_sha256=V1_RELAY_OFF_FILE_SHA256,
        canonical_sha256=V1_RELAY_OFF_CANONICAL_SHA256,
        label="T3 V1 final relay OFF evidence",
    )
    v1_artifacts = frozen.ARTIFACTS[frozen.STAGE]
    binary = flash.get("binary")
    constraints = flash.get("constraints")
    if (
        flash.get("outcome") != "app_only_write_verify_single_boot_pass"
        or flash.get("success") is not True
        or flash.get("j2_confirmed_off") is not True
        or not isinstance(binary, Mapping)
        or binary.get("bytes") != v1_artifacts["bin_bytes"]
        or binary.get("expected_sha256") != v1_artifacts["bin_sha256"]
        or binary.get("observed_sha256") != v1_artifacts["bin_sha256"]
        or binary.get("preflight_verified") is not True
        or not isinstance(constraints, Mapping)
        or constraints.get("application_only") is not True
        or constraints.get("application_start_count_after_write") != 1
        or constraints.get("bootloader_write") is not False
        or constraints.get("partition_table_write") is not False
        or constraints.get("nvs_write_or_erase") is not False
        or constraints.get("retry") is not False
        or constraints.get("recovery") is not False
        or constraints.get("fallback") is not False
    ):
        raise T3ProfileFollowingPackError("T3 V1 flash semantics differ")
    error = diagnostic.get("error")
    transcript = diagnostic.get("transcript")
    if (
        diagnostic.get("outcome") != "j2_off_diagnostic_failed_no_claim"
        or diagnostic.get("claims_directory_accessed") is not False
        or diagnostic.get("permanent_claims_created") != 0
        or diagnostic.get("network") != {"get": 1, "post": 0}
        or diagnostic.get("visible_refreshes") != 0
        or diagnostic.get("no_retry") is not True
        or diagnostic.get("no_recovery") is not True
        or diagnostic.get("no_autochain") is not True
        or not isinstance(error, Mapping)
        or error.get("type") != "RecheckError"
        or "WinError 10061" not in str(error.get("message"))
        or not isinstance(transcript, list)
        or len(transcript) != 1
        or transcript[0].get("method") != "GET"
        or transcript[0].get("endpoint") != "version"
        or transcript[0].get("path") != f"{frozen.CONFIG.base_route}/version"
    ):
        raise T3ProfileFollowingPackError("T3 V1 failed diagnostic semantics differ")
    if (
        relay.get("commanded_state") != "OFF"
        or relay.get("off_gate_passed") is not True
        or relay.get("on_authorized") is not False
        or relay.get("contact_switch_performed") is not False
        or relay.get("automatic_retry_performed") is not False
        or relay.get("electrical_state_proven") is not False
    ):
        raise T3ProfileFollowingPackError("T3 V1 relay OFF semantics differ")
    v1_action_id = _v1_identity()["action_id"]
    claim = V1_CLAIM_ROOT / f"{v1_action_id}.json"
    if V1_ACTION_OUTPUT.exists() or claim.exists():
        raise T3ProfileFollowingPackError("T3 V1 action or claim is no longer absent")
    return {
        "binding": v1_failure_authority_binding(),
        "action_output_absent": True,
        "claim_absent": True,
    }


def validate_authorities() -> dict[str, Any]:
    return {
        **frozen.validate_authorities(),
        "v1_terminal_failure": validate_v1_failure_authority(),
        "address_resolution_boundary": validate_address_resolution_boundary(),
    }


def non_reusable_action_ids() -> tuple[str, ...]:
    values = (*frozen.non_reusable_action_ids(), _v1_identity()["action_id"])
    if len(values) != len(set(values)):
        raise T3ProfileFollowingPackError("V2 predecessor action registry overlaps")
    return values


def artifact_paths(stage: str = STAGE) -> tuple[Path, Path]:
    if stage != STAGE:
        raise KeyError(stage)
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def artifacts_are_sealed() -> bool:
    values = ARTIFACTS[STAGE]
    return (
        values["bin_bytes"] > 0
        and values["elf_bytes"] > 0
        and values["bin_sha256"] != "0" * 64
        and values["elf_sha256"] != "0" * 64
    )


def external_containment_contract() -> dict[str, Any]:
    return frozen.external_containment_contract()


def build_report(stage: str = STAGE) -> dict[str, Any]:
    if stage != STAGE:
        raise KeyError(stage)
    v1_report = frozen.build_report()
    v1_action = v1_report["actions"][0]
    failure = v1_failure_authority_binding()
    address_boundary = address_resolution_boundary_binding()

    action = deepcopy(v1_action)
    action.update(
        {
            "role": "RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ATLAS",
            "branch": (
                f"{CONFIG.variant_key}_"
                "RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_REVIEW_V2_ATLAS"
            ),
            "supersedes_failed_unmutated_v1_action_id": v1_action["action_id"],
            "v1_terminal_failure_authority": failure,
            "address_resolution_boundary": address_boundary,
            "boot_admission": {
                **v1_action["boot_admission"],
                "campaign_boot_binding_key": CONFIG.nvs_boot_key,
            },
        }
    )
    action.pop("descriptor_id", None)
    action.pop("action_id", None)
    descriptor = {
        "schema": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-"
            "successor-action-v2"
        ),
        "variant": CONFIG.variant_key,
        "build_tag": CONFIG.build_tag,
        **action,
        "non_reusable_action_ids": list(non_reusable_action_ids()),
    }
    action["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
    action["action_id"] = sha256_bytes(
        (
            "MF1750_RAW_P16_CROSSOVER_T3_AC_PROFILE_FOLLOWING_"
            f"SUCCESSOR_ACTION_V2|{CONFIG.variant_key}|1|"
            f"{action['descriptor_id']}"
        ).encode("ascii")
    )

    contract = deepcopy(v1_report["contract"])
    contract.update(
        {
            "schema": (
                "mf1750-raw-p16-crossover-t3-ac-profile-following-"
                "successor-contract-v2"
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
            "classification": CLASSIFICATION,
            "actions": [action],
            "v1_terminal_failure_authority": failure,
            "address_resolution_boundary": address_boundary,
            "non_reusable_action_ids": list(non_reusable_action_ids()),
        }
    )
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-"
            "successor-offline-identities-v2"
        ),
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "stage": STAGE,
        "source_action_authority": completed_t2_v2_action_binding(),
        "pre_white_action_evidence": completed_w3_white_action_binding(),
        "pre_white_authority": pre_white_authority_binding(),
        "v1_terminal_failure_authority": failure,
        "address_resolution_boundary": address_boundary,
        "actions": [action],
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


@lru_cache(maxsize=1)
def _prior_identity_values() -> frozenset[str]:
    values = set(frozen._prior_identity_values())  # noqa: SLF001
    report = frozen.build_report()
    action = report["actions"][0]
    values.update(
        {
            report["contract_id"],
            action["descriptor_id"],
            action["action_id"],
            report["contract"]["campaign_id"],
            report["contract"]["test_id"],
            report["contract"]["base_route"],
            report["contract"]["nvs_namespace"],
        }
    )
    return frozenset(values)


def dry_validate(*, verify_authorities: bool = True) -> dict[str, Any]:
    if verify_authorities:
        validate_authorities()
    report = build_report()
    action = report["actions"][0]
    v1_report = frozen.build_report()
    v1_action = v1_report["actions"][0]
    for key in ("frame", "cs1_dtm", "cs2_dtm", "waveform_binding", "profile_id"):
        if action[key] != v1_action[key]:
            raise T3ProfileFollowingPackError(f"T3 V2 frozen {key} differs")
    if (
        action["round"] != 3
        or action["global_header"] != "active"
        or action["waveform_binding"]["cs1"]["name"] != "active"
        or action["waveform_binding"]["cs2"]["name"] != "commented"
    ):
        raise T3ProfileFollowingPackError("T3 V2 AC profile tuple differs")
    if action["action_id"] in non_reusable_action_ids():
        raise T3ProfileFollowingPackError("T3 V2 reuses a predecessor action")
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
        raise T3ProfileFollowingPackError("T3 V2 identity overlaps a predecessor")
    if len(CONFIG.nvs_namespace) > 15:
        raise T3ProfileFollowingPackError("T3 V2 NVS namespace exceeds ESP32 limit")
    return {
        "schema_version": 1,
        "kind": (
            "mf1750-raw-p16-crossover-t3-ac-profile-following-"
            "successor-v2-dry-validation"
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
        "fresh_campaign_test_contract_descriptor_action_route_nvs": True,
        "predecessor_v1_not_reauthorized": True,
        "predecessor_actions_non_reusable": True,
        "non_reusable_action_count": len(non_reusable_action_ids()),
        "profile_tuple": "ACTIVE_GLOBAL__CS1_ACTIVE535__CS2_COMMENTED535",
        "round": 3,
        "action_count": 1,
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
        "contract_id": report["contract_id"],
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "v1_terminal_failure_authority": v1_failure_authority_binding(),
        "address_resolution_boundary": address_resolution_boundary_binding(),
        "artifacts_sealed": artifacts_are_sealed(),
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
