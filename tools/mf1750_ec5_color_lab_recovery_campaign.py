#!/usr/bin/env python3
"""Compile the isolated EC5 colour-lab recovery campaign offline.

The compiled campaign is deliberately independent of the live predecessor
evidence.  A later materialization step binds the frozen action table to the
latest validated clean-white observation and the exact firmware artifacts.
Synthetic materializations exist only to exercise host code and are never
execution eligible.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_ec5_color_lab_recovery_contract as device_contract  # noqa: E402
from tools import (  # noqa: E402
    mf1750_ec5_color_lab_recovery_compiled_identity as compiled_identity,
)
from tools import mf1750_ec5_compare_white_recovery_once as white_guard  # noqa: E402


SCHEMA_VERSION = 1
CAMPAIGN_KIND = "mf1750-ec5-color-lab-recovery-compiled-campaign"
RELEASE_KIND = "mf1750-ec5-color-lab-recovery-materialized-release"
IDENTITY_REVISION = device_contract.IDENTITY_REVISION
BUILD_TAG = device_contract.BUILD_TAG
TEST_ID = device_contract.TEST_ID
DEVICE_API_VERSION = device_contract.DEVICE_API_VERSION
DRIVER_EVIDENCE_SCHEMA_VERSION = device_contract.DRIVER_EVIDENCE_SCHEMA_VERSION
DEVICE_SCHEMA_VERSION = device_contract.TOP_SCHEMA_VERSION
ACTION_COUNT = 23
FIRST_SAFE_STOP_ORDINAL = 5
FIRST_FULL_ROUND_STOP_ORDINAL = 11
WHITE_CHECKPOINT_ORDINALS = (1, 3, 5, 8, 11, 14, 17, 20, 23)
RECOMMENDED_SAFE_STOP_ORDINALS = (5, 11, 23)
SUPERSEDED_MARKER_NAME = "SUPERSEDED.json"
SUPERSEDED_MARKER_KIND = (
    "mf1750-ec5-color-lab-recovery-release-supersession-marker"
)
SUPERSEDED_MARKER_STATE = "SUPERSEDED_DO_NOT_USE_OR_FLASH"
V3_SELF_CONTAINED_RELEASE_DIRECTORY = (
    "MF1750_EC5_COLOR_LAB_RECOVERY_REAL_COMPARE_BOUND_20260810_V3_SELF_CONTAINED"
)
CAMPAIGN_ROUNDS = 3
NVS_NAMESPACE = device_contract.NVS_NAMESPACE
NVS_KEY = device_contract.NVS_KEY
FIRST_PREDECESSOR_ACTION_ID = (
    "70db952b1d708511e1fdcb166b43cd5828fe232562b14d341d848942787d1700"
)
INVALIDATED_U07T_ACTION_ID = (
    "303bb39e496f39caef782aadacb0d63e6d4f9b42df550d4c799a4248a8041310"
)
FORMAL_U07_ACTION_ID = (
    "8f427d1262afb4d4d430033451cf7afc6f319b172c836fcdf1e16a02a13746ae"
)
SUPERSEDED_COLOR_LAB_CONTRACT_ID = (
    "7a5c7f1ecf5265fdffe0b3b3d2448c00106d49f128cb3a15e5b41ad7e97b968a"
)
SUPERSEDED_COLOR_LAB_ACTION_1_ID = (
    "ecbd9684f901a33c2a8f483b9cdd2795c3a759aa6f5fd4e0ea514b658fbfcdbf"
)
SUPERSEDED_COLOR_LAB_RELEASE_FILE_SHA256 = (
    "9121a5e244fb67923ccb6791cf4f20fbf3c840f46b8dc437fad36c43e93752d2"
)
SUPERSEDED_COLOR_LAB_RELEASE_CANONICAL_SHA256 = (
    "190aee5f791b86abe8b19a02286e09f791efb25d48fe856eb385386de32c2132"
)
SYNTHETIC_MODE = "SYNTHETIC_OFFLINE_FIXTURE_NOT_FOR_DEVICE"
REAL_MODE = "REAL_GUARD_VALIDATED"
MAX_JSON_BYTES = 16 * 1024 * 1024
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY"

ENDPOINTS = {
    name: f"/api/ec5/color-lab/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
ARM_INTENT = (
    "ARM_ONE_FIXED_COLOR_LAB_RECOVERY_ACTION_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = (
    "EXECUTE_ONE_FIXED_COLOR_LAB_RECOVERY_ACTION_NOT_HARDWARE_AUTHORIZATION"
)
MUTATION_HEADERS = (
    "X-EC5-Build-Tag",
    "X-EC5-Test-Id",
    "X-EC5-Campaign-Id",
    "X-EC5-Action-Id",
    "X-EC5-Ordinal",
    "X-EC5-Descriptor-Id",
    "X-EC5-Boot-Nonce",
    "X-EC5-Intent",
    "X-EC5-Arm-Nonce",
)

SYNTHETIC_FIXTURES = {
    "result": {
        "file": "synthetic-compare-result.json",
        "sha256": "513f76682b55f4fb3c74f8e6fddfe58d6ffc8a8cf333467733a6e5b8c4b76b2b",
        "kind": "mf1750-ec5-u04-u05-compare-synthetic-result-fixture",
    },
    "claim": {
        "file": "synthetic-compare-claim.json",
        "sha256": "c1d0894a446abcd8463389e3b8222df502d3fc9da56a2a1703d7e6e671c48f59",
        "kind": "mf1750-ec5-u04-u05-compare-synthetic-claim-fixture",
    },
    "manual_observation": {
        "file": "synthetic-compare-manual-observation.json",
        "sha256": "a849e89dc556c8d354cd6fa750838ad0dca507096359a612713db6c8814f9884",
        "kind": "mf1750-ec5-u04-u05-compare-synthetic-manual-observation-fixture",
    },
}


class ColorLabCampaignError(RuntimeError):
    """A campaign identity, evidence, or immutable-output check failed."""


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ColorLabCampaignError(f"value is not canonical JSON: {error}") from error


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value) if isinstance(value, Mapping) else value
    return hashlib.sha256(payload).hexdigest()


def fnv1a(payload: bytes) -> str:
    value = 0x811C9DC5
    for byte in payload:
        value ^= byte
        value = (value * 0x01000193) & 0xFFFFFFFF
    return f"0x{value:08x}"


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ColorLabCampaignError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise ColorLabCampaignError(f"{label} must be a regular non-symlink file")
        if before.st_size <= 0 or before.st_size > maximum:
            raise ColorLabCampaignError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise ColorLabCampaignError(f"could not read {label}: {error}") from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ColorLabCampaignError(f"{label} changed while read")
    if len(payload) != after.st_size:
        raise ColorLabCampaignError(f"{label} read length differs")
    return payload


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ColorLabCampaignError(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ColorLabCampaignError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(root, Mapping):
        raise ColorLabCampaignError(f"{label} root must be an object")
    return root


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    path = Path(path)
    payload = canonical_json_bytes(value)
    try:
        parent = path.parent.resolve(strict=True)
        if parent.is_symlink() or not parent.is_dir():
            raise ColorLabCampaignError("output parent must be a non-symlink directory")
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise ColorLabCampaignError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise ColorLabCampaignError(f"could not create {path}: {error}") from error
    return payload


def _seal(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(unsigned))
    result["integrity"] = {
        "canonical_sha256": sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    return result


def _validate_seal(root: Mapping[str, Any], *, label: str) -> str:
    integrity = root.get("integrity")
    if not isinstance(integrity, Mapping) or set(integrity) != {
        "canonical_sha256",
        "scope",
    }:
        raise ColorLabCampaignError(f"{label} integrity fields differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {
        "canonical_sha256": sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected:
        raise ColorLabCampaignError(f"{label} integrity differs")
    return str(integrity["canonical_sha256"])


def _controller_stream(frame: bytes, half: int) -> bytes:
    if len(frame) != 307_200 or half not in (0, 1):
        raise ColorLabCampaignError("frame/controller selection differs")
    output = bytearray()
    for row in range(600):
        start = row * 512 + half * 256
        output.extend(frame[start : start + 256])
    return bytes(output)


def _frame_identity(frame: bytes) -> dict[str, Any]:
    if len(frame) != 307_200:
        raise ColorLabCampaignError("colour-lab frame must contain 307200 bytes")
    controllers = []
    for index in range(2):
        stream = _controller_stream(frame, index)
        controllers.append(
            {
                "controller": f"CS{index + 1}",
                "bytes": len(stream),
                "sha256": sha256(stream),
                "fnv1a": fnv1a(stream),
                "source_half": index,
            }
        )
    return {
        "bytes": len(frame),
        "sha256": sha256(frame),
        "fnv1a": fnv1a(frame),
        "encoding": "canonical-row-major-two-4bit-codes-per-byte",
        "controllers": controllers,
    }


def frozen_frames() -> dict[str, dict[str, Any]]:
    # Recompute bytes locally as a cross-check, then expose the exact contract
    # identities consumed by the firmware.  This keeps one identity authority.
    device_contract.validate_contract()
    result: dict[str, dict[str, Any]] = {}
    for role in device_contract.ROLES:
        generated = _frame_identity(device_contract.role_frame(role))
        frozen = device_contract.ROLE_IDENTITIES[role]
        if (
            generated["sha256"] != frozen["frame"]["sha256"]
            or generated["controllers"][0]["sha256"]
            != frozen["cs1_dtm"]["sha256"]
            or generated["controllers"][1]["sha256"]
            != frozen["cs2_dtm"]["sha256"]
        ):
            raise ColorLabCampaignError(f"firmware role {role} identity differs")
        result[role] = {
            "layout_id": device_contract.LAYOUT_ID,
            "frame": generated,
            "spatial_dithering": False,
            "physical_colour_claim": False,
        }
    return result


def build_actions() -> list[dict[str, Any]]:
    frames = frozen_frames()
    actions: list[dict[str, Any]] = []
    for frozen in device_contract.DESCRIPTORS:
        action = deepcopy(dict(frozen))
        role = str(action["role"])
        action["action_id"] = action["hardware_action_id"]
        action["frame"] = deepcopy(frames[role])
        actions.append(action)
    if len(actions) != ACTION_COUNT:
        raise ColorLabCampaignError("firmware action table count differs")
    return actions


def build_campaign() -> dict[str, Any]:
    actions = build_actions()
    contract_manifest = device_contract.campaign_manifest()
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": CAMPAIGN_KIND,
        "identity_revision": IDENTITY_REVISION,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "device_api_version": DEVICE_API_VERSION,
        "campaign_id": device_contract.CAMPAIGN_ID,
        "firmware_contract_id": contract_manifest["contract_id"],
        "firmware_contract": contract_manifest,
        "device_schema_version": DEVICE_SCHEMA_VERSION,
        "driver_evidence_schema_version": DRIVER_EVIDENCE_SCHEMA_VERSION,
        "first_predecessor_action_id": FIRST_PREDECESSOR_ACTION_ID,
        "invalidated_prior_u07t_action_id": INVALIDATED_U07T_ACTION_ID,
        "action_count": ACTION_COUNT,
        "campaign_rounds": CAMPAIGN_ROUNDS,
        "first_safe_stop_ordinal": FIRST_SAFE_STOP_ORDINAL,
        "first_safe_stop_semantics": (
            "first recommended pause after atlas and its clean-white checkpoint"
        ),
        "white_checkpoint_ordinals": list(WHITE_CHECKPOINT_ORDINALS),
        "recommended_safe_stop_ordinals": list(RECOMMENDED_SAFE_STOP_ORDINALS),
        "first_complete_round_stop_ordinal": FIRST_FULL_ROUND_STOP_ORDINAL,
        "nvs_contract": {
            "namespace": NVS_NAMESPACE,
            "key": NVS_KEY,
            "ordinal_base": 1,
            "initial_next_ordinal": 1,
            "terminal_next_ordinal": ACTION_COUNT + 1,
            "phase_encoding": ["READY", "ARMED", "CONSUMED", "FAULT"],
        },
        "device_contract": {
            "endpoints": ENDPOINTS,
            "mutation_headers": list(MUTATION_HEADERS),
            "arm_intent": ARM_INTENT,
            "execute_intent": EXECUTE_INTENT,
            "maximum_arm_posts_per_action": 1,
            "maximum_execute_posts_per_action": 1,
            "automatic_chaining": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "startup_refresh": False,
            "raw_frame_ingress": False,
            "same_firmware_without_reset_or_reflash": True,
        },
        "actions": actions,
        "classification": {
            "technical_experiment": True,
            "physical_colour_claim": False,
            "hardware_tested_by_this_compiler": False,
            "device_accessed_by_this_compiler": False,
            "visible_refresh_authorized_by_this_compiler": False,
        },
    }
    return _seal(unsigned)


def generate_campaign(output_file: Path) -> dict[str, Any]:
    campaign = build_campaign()
    _write_new(output_file, campaign)
    return campaign


def validate_campaign(manifest_file: Path) -> dict[str, Any]:
    payload = _read_regular(manifest_file, label="compiled colour-lab campaign")
    root = _decode(payload, label="compiled colour-lab campaign")
    _validate_seal(root, label="compiled colour-lab campaign")
    expected = build_campaign()
    if dict(root) != expected:
        raise ColorLabCampaignError("compiled colour-lab campaign differs")
    return {
        "file": str(Path(manifest_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": root["integrity"]["canonical_sha256"],
        "action_count": ACTION_COUNT,
        "first_safe_stop_ordinal": FIRST_SAFE_STOP_ORDINAL,
        "actions": deepcopy(root["actions"]),
    }


def _validate_synthetic_fixture(path: Path, spec: Mapping[str, str]) -> dict[str, Any]:
    payload = _read_regular(path, label=f"synthetic {path.name}")
    root = _decode(payload, label=f"synthetic {path.name}")
    if (
        sha256(payload) != spec["sha256"]
        or root.get("schema_version") != 0
        or root.get("kind") != spec["kind"]
        or root.get("synthetic") is not True
        or root.get("hardware_execution_performed") is not False
        or root.get("action_id") != FIRST_PREDECESSOR_ACTION_ID
    ):
        raise ColorLabCampaignError(f"synthetic fixture {path.name} differs")
    if path.name.endswith("claim.json") and root.get("claim_created") is not False:
        raise ColorLabCampaignError("synthetic fixture must not represent a real claim")
    return {
        "file": str(path.resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "kind": root["kind"],
    }


def _panel(path: Path) -> dict[str, str]:
    payload = _read_regular(path, label="live panel identity")
    root = _decode(payload, label="live panel identity")
    expected = {"model", "serial", "board_id", "pcb_revision"}
    if set(root) != expected or any(
        not isinstance(root[key], str) or not root[key].strip() for key in expected
    ):
        raise ColorLabCampaignError("live panel identity differs")
    return {key: str(root[key]) for key in sorted(expected)}


def _formal_u07_absence(registry: Path) -> dict[str, Any]:
    registry = Path(registry)
    try:
        metadata = registry.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise ColorLabCampaignError(
                "formal U07 claim registry must be a non-symlink directory"
            )
        resolved = registry.resolve(strict=True)
        claim = resolved / f"{FORMAL_U07_ACTION_ID}.json"
        try:
            claim.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ColorLabCampaignError("formal U07 action is already claimed")
    except OSError as error:
        raise ColorLabCampaignError(
            f"could not inspect formal U07 claim registry: {error}"
        ) from error
    return {
        "registry": str(resolved),
        "action_id": FORMAL_U07_ACTION_ID,
        "claim_file": str(claim),
        "entry_absent_by_lstat": True,
    }


def _artifact(path: Path, *, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    payload = _read_regular(path, label=label, maximum=maximum)
    required_needles = (
        BUILD_TAG,
        TEST_ID,
        DEVICE_API_VERSION,
        device_contract.CAMPAIGN_ID,
        device_contract.campaign_manifest()["contract_id"],
        NVS_NAMESPACE,
        NVS_KEY,
    )
    missing = [needle for needle in required_needles if needle.encode() not in payload]
    if missing:
        raise ColorLabCampaignError(
            f"{label} lacks frozen identity string {missing[0]!r}"
        )
    for descriptor in device_contract.DESCRIPTORS:
        for key in ("hardware_action_id", "descriptor_id"):
            if str(descriptor[key]).encode() not in payload:
                raise ColorLabCampaignError(
                    f"{label} lacks ordinal {descriptor['ordinal']} {key}"
                )
    return (
        {
            "file": str(Path(path).resolve()),
            "bytes": len(payload),
            "sha256": sha256(payload),
        },
        payload,
    )


def _superseded_incident_binding(
    *, release_file: Path, result_file: Path, claim_registry: Path
) -> dict[str, Any]:
    release_payload = _read_regular(
        release_file, label="superseded COLOR_LAB release"
    )
    release_root = _decode(
        release_payload, label="superseded COLOR_LAB release"
    )
    release_canonical = _validate_seal(
        release_root, label="superseded COLOR_LAB release"
    )
    if (
        sha256(release_payload) != SUPERSEDED_COLOR_LAB_RELEASE_FILE_SHA256
        or release_canonical != SUPERSEDED_COLOR_LAB_RELEASE_CANONICAL_SHA256
        or release_root.get("kind") != "mf1750-ec5-color-lab-materialized-release"
        or release_root.get("execution_eligible") is not True
    ):
        raise ColorLabCampaignError("superseded COLOR_LAB release identity differs")

    result_payload = _read_regular(
        result_file, label="superseded COLOR_LAB incident result"
    )
    result_root = _decode(
        result_payload, label="superseded COLOR_LAB incident result"
    )
    result_canonical = _validate_seal(
        result_root, label="superseded COLOR_LAB incident result"
    )
    if (
        result_root.get("kind")
        != "mf1750-ec5-color-lab-physical-once-result"
        or result_root.get("ordinal") != 1
        or result_root.get("action", {}).get("action_id")
        != SUPERSEDED_COLOR_LAB_ACTION_1_ID
        or result_root.get("outcome") != "unknown_do_not_retry_or_recover"
        or result_root.get("state")
        != "authorization_permanently_consumed_do_not_rerun"
        or result_root.get("release", {}).get("file_sha256")
        != SUPERSEDED_COLOR_LAB_RELEASE_FILE_SHA256
        or result_root.get("release", {}).get("canonical_sha256")
        != SUPERSEDED_COLOR_LAB_RELEASE_CANONICAL_SHA256
        or result_root.get("network", {}).get("execute_posts") != 0
        or any(value is not None for value in result_root.get("device", {}).values())
    ):
        raise ColorLabCampaignError("superseded COLOR_LAB incident boundary differs")

    registry = Path(claim_registry).resolve(strict=True)
    claim_file = registry / f"{SUPERSEDED_COLOR_LAB_ACTION_1_ID}.json"
    claim_payload = _read_regular(
        claim_file, label="superseded COLOR_LAB permanent claim"
    )
    claim_root = _decode(
        claim_payload, label="superseded COLOR_LAB permanent claim"
    )
    claim_canonical = _validate_seal(
        claim_root, label="superseded COLOR_LAB permanent claim"
    )
    expected_claim_ref = {
        "file": str(claim_file),
        "bytes": len(claim_payload),
        "file_sha256": sha256(claim_payload),
        "integrity_sha256": claim_canonical,
        "state": "permanently_claimed_before_first_arm_post",
    }
    if (
        result_root.get("claim") != expected_claim_ref
        or claim_root.get("action", {}).get("action_id")
        != SUPERSEDED_COLOR_LAB_ACTION_1_ID
        or claim_root.get("attempt_id") != result_root.get("attempt_id")
        or claim_root.get("state")
        != "permanently_claimed_before_first_arm_post"
    ):
        raise ColorLabCampaignError("superseded COLOR_LAB claim binding differs")
    return {
        "superseded_release": {
            "file": str(Path(release_file).resolve()),
            "bytes": len(release_payload),
            "file_sha256": sha256(release_payload),
            "canonical_sha256": release_canonical,
            "contract_id": SUPERSEDED_COLOR_LAB_CONTRACT_ID,
        },
        "incident_result": {
            "file": str(Path(result_file).resolve()),
            "bytes": len(result_payload),
            "file_sha256": sha256(result_payload),
            "integrity_sha256": result_canonical,
            "attempt_id": result_root["attempt_id"],
            "outcome": result_root["outcome"],
            "error": result_root["error"],
        },
        "permanent_claim": expected_claim_ref,
        "old_action_id": SUPERSEDED_COLOR_LAB_ACTION_1_ID,
        "old_authorization_remains_consumed": True,
        "old_claim_must_not_be_removed_or_reused": True,
        "old_nvs_namespace": "mf1750_ec5cl",
        "old_nvs_key": "cursor",
        "new_nvs_namespace": NVS_NAMESPACE,
        "new_nvs_key": NVS_KEY,
        "old_fault_state_ignored_not_cleared": True,
        "global_nvs_clear": False,
        "wifi_credentials_preserved": True,
    }


def _binary_elf_link(binary: bytes, elf: bytes) -> dict[str, Any]:
    app_desc_offset = 32
    elf_sha_offset = 176
    app_desc_magic = bytes.fromhex("3254cdab")
    elf_sha = hashlib.sha256(elf).digest()
    if (
        len(binary) < elf_sha_offset + 32
        or binary[app_desc_offset : app_desc_offset + 4] != app_desc_magic
        or binary[elf_sha_offset : elf_sha_offset + 32] != elf_sha
    ):
        raise ColorLabCampaignError(
            "firmware BIN app descriptor does not bind the selected ELF"
        )
    return {
        "app_descriptor_offset": app_desc_offset,
        "app_descriptor_magic_hex": app_desc_magic.hex(),
        "embedded_elf_sha256_offset": elf_sha_offset,
        "embedded_elf_sha256": elf_sha.hex(),
        "selected_elf_sha256": hashlib.sha256(elf).hexdigest(),
        "exact_match": True,
    }


def _absolute_guard_kwargs(
    validation_kwargs: Mapping[str, Any],
) -> dict[str, str]:
    expected = {
        "flash_gate_file",
        "preflight_file",
        "compare_release_file",
        "compare_result_file",
        "compare_claim_registry",
        "compare_observation_file",
        "panel_file",
        "rc2g_binary_file",
        "claim_registry",
        "formal_white_claim_registry",
    }
    if set(validation_kwargs) != expected:
        raise ColorLabCampaignError("white guard replay paths differ")
    return {
        key: str(Path(validation_kwargs[key]).resolve()) for key in sorted(expected)
    }


def materialize_synthetic_release(
    *,
    campaign_file: Path,
    fixture_directory: Path,
    output_file: Path,
) -> dict[str, Any]:
    campaign = validate_campaign(campaign_file)
    fixtures = {
        name: _validate_synthetic_fixture(
            Path(fixture_directory) / spec["file"], spec
        )
        for name, spec in SYNTHETIC_FIXTURES.items()
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": RELEASE_KIND,
        "evidence_mode": SYNTHETIC_MODE,
        "execution_eligible": False,
        "state": "SYNTHETIC_OFFLINE_NOT_FOR_DEVICE",
        "compiled_campaign": {
            key: campaign[key]
            for key in (
                "file",
                "bytes",
                "file_sha256",
                "canonical_sha256",
                "action_count",
                "first_safe_stop_ordinal",
            )
        },
        "predecessor_binding": {
            "action_id": FIRST_PREDECESSOR_ACTION_ID,
            "mode": SYNTHETIC_MODE,
            "fixtures": fixtures,
            "latest_visible_state": "synthetic_shape_only_not_observed",
            "manual_live_no_intervening_refresh_confirmation_required": True,
        },
        "recovery_boundary": None,
        "firmware": None,
        "panel": None,
        "safety": {
            "device_access_performed": False,
            "network_requests": 0,
            "claim_created": False,
            "hardware_execution_performed": False,
            "visible_refresh_authorized": False,
            "runner_must_reject_before_network_or_claim": True,
            "real_guard_evidence_must_be_materialized_later": True,
        },
    }
    release = _seal(unsigned)
    _write_new(output_file, release)
    return release


def materialize_real_release(
    *,
    campaign_file: Path,
    compare_release_file: Path,
    compare_result_file: Path,
    compare_claim_registry: Path,
    compare_observation_file: Path,
    superseded_release_file: Path,
    superseded_result_file: Path,
    superseded_claim_registry: Path,
    firmware_binary_file: Path,
    firmware_elf_file: Path,
    panel_file: Path,
    formal_u07_claim_registry: Path,
    output_file: Path,
) -> dict[str, Any]:
    """Bind ordinal 1 directly to the completed four-patch comparison."""

    campaign = validate_campaign(campaign_file)
    try:
        predecessor = white_guard.load_compare_binding(
            compare_release_file=Path(compare_release_file),
            compare_result_file=Path(compare_result_file),
            compare_claim_registry=Path(compare_claim_registry),
            compare_observation_file=Path(compare_observation_file),
            panel_file=Path(panel_file),
        ).binding
    except white_guard.CompareWhiteError as error:
        raise ColorLabCampaignError(
            f"U04/U05 comparison replay failed: {error}"
        ) from error
    panel = _panel(panel_file)
    if predecessor.get("panel") != panel:
        raise ColorLabCampaignError("comparison panel differs")
    binary, binary_payload = _artifact(
        firmware_binary_file, label="COLOR_LAB firmware binary", maximum=32 << 20
    )
    elf, elf_payload = _artifact(
        firmware_elf_file, label="COLOR_LAB firmware ELF", maximum=64 << 20
    )
    binary_elf_link = _binary_elf_link(binary_payload, elf_payload)
    try:
        compiled_report = compiled_identity.validate(firmware_elf_file)
    except compiled_identity.ColorLabCompiledIdentityError as error:
        raise ColorLabCampaignError(
            f"compiled COLOR_LAB identity replay failed: {error}"
        ) from error
    formal_u07 = _formal_u07_absence(formal_u07_claim_registry)
    recovery_boundary = _superseded_incident_binding(
        release_file=superseded_release_file,
        result_file=superseded_result_file,
        claim_registry=superseded_claim_registry,
    )
    predecessor_binding = {
        "action_id": FIRST_PREDECESSOR_ACTION_ID,
        "mode": REAL_MODE,
        "compare_binding": deepcopy(dict(predecessor)),
        "compare_replay_paths": {
            "compare_release_file": str(Path(compare_release_file).resolve()),
            "compare_result_file": str(Path(compare_result_file).resolve()),
            "compare_claim_registry": str(Path(compare_claim_registry).resolve()),
            "compare_observation_file": str(
                Path(compare_observation_file).resolve()
            ),
            "panel_file": str(Path(panel_file).resolve()),
        },
        "latest_visible_state": "u04_u05_compare_four_blue_patches",
        "ordinal_1_compiled_white_establishes_clean_baseline": True,
        "manual_live_no_intervening_refresh_confirmation_required": True,
    }
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": RELEASE_KIND,
        "evidence_mode": REAL_MODE,
        "execution_eligible": True,
        "state": (
            "REAL_COMPARE_AND_SUPERSEDED_INCIDENT_BOUND_READY_FOR_"
            "RECOVERY_ORDINAL_1_WHITE_AUTHORIZATION"
        ),
        "compiled_campaign": {
            key: campaign[key]
            for key in (
                "file",
                "bytes",
                "file_sha256",
                "canonical_sha256",
                "action_count",
                "first_safe_stop_ordinal",
            )
        },
        "predecessor_binding": predecessor_binding,
        "recovery_boundary": recovery_boundary,
        "firmware": {
            "binary": binary,
            "elf": elf,
            "binary_elf_link": binary_elf_link,
            "compiled_identity_report": compiled_report,
        },
        "panel": panel,
        "formal_u07_claim_absence": formal_u07,
        "safety": {
            "materializer_device_access_performed": False,
            "materializer_network_requests": 0,
            "materializer_claim_created": False,
            "materializer_hardware_execution_performed": False,
            "visible_refresh_authorized_by_release": False,
            "one_exact_human_authorization_required_per_action": True,
            "runner_must_recheck_formal_u07_absence": True,
            "ordinal_1_is_the_only_planned_compare_to_white_recovery": True,
            "standalone_compare_white_is_fallback_only": True,
            "old_fault_namespace_ignored_not_cleared": True,
            "old_action_claim_remains_permanently_consumed": True,
            "new_nvs_namespace_and_key": True,
            "global_nvs_clear": False,
            "wifi_credentials_preserved": True,
            "all_action_ids_regenerated": True,
            "automatic_chaining": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        },
    }
    release = _seal(unsigned)
    _write_new(output_file, release)
    return release


def _reject_superseded_release(release_file: Path) -> None:
    marker = Path(release_file).parent / SUPERSEDED_MARKER_NAME
    try:
        marker.lstat()
    except FileNotFoundError:
        return
    except OSError as error:
        raise ColorLabCampaignError(
            f"could not inspect release supersession marker: {error}"
        ) from error
    root = _decode(
        _read_regular(marker, label="release supersession marker", maximum=64 << 10),
        label="release supersession marker",
    )
    expected = {
        "schema_version": 1,
        "kind": SUPERSEDED_MARKER_KIND,
        "state": SUPERSEDED_MARKER_STATE,
        "reason": "firmware BIN and ELF references point to mutable .pio build output",
        "superseded_by": V3_SELF_CONTAINED_RELEASE_DIRECTORY,
        "visible_refresh_authorized": False,
        "device_access_performed": False,
        "claim_created": False,
    }
    if dict(root) != expected:
        raise ColorLabCampaignError(
            "release supersession marker is present but malformed; refusing release"
        )
    raise ColorLabCampaignError(
        f"release is superseded; use {V3_SELF_CONTAINED_RELEASE_DIRECTORY}"
    )


def validate_materialized_release(release_file: Path) -> dict[str, Any]:
    _reject_superseded_release(release_file)
    payload = _read_regular(release_file, label="colour-lab materialized release")
    root = _decode(payload, label="colour-lab materialized release")
    expected_keys = {
        "schema_version",
        "kind",
        "evidence_mode",
        "execution_eligible",
        "state",
        "compiled_campaign",
        "predecessor_binding",
        "recovery_boundary",
        "firmware",
        "panel",
        "formal_u07_claim_absence",
        "safety",
        "integrity",
    }
    if root.get("evidence_mode") == SYNTHETIC_MODE:
        expected_keys.remove("formal_u07_claim_absence")
    if set(root) != expected_keys:
        raise ColorLabCampaignError("materialized release fields differ")
    canonical = _validate_seal(root, label="colour-lab materialized release")
    if root["schema_version"] != SCHEMA_VERSION or root["kind"] != RELEASE_KIND:
        raise ColorLabCampaignError("materialized release schema/kind differs")
    campaign_ref = root["compiled_campaign"]
    if not isinstance(campaign_ref, Mapping) or set(campaign_ref) != {
        "file",
        "bytes",
        "file_sha256",
        "canonical_sha256",
        "action_count",
        "first_safe_stop_ordinal",
    }:
        raise ColorLabCampaignError("materialized campaign reference differs")
    campaign = validate_campaign(Path(str(campaign_ref["file"])))
    if any(campaign_ref[key] != campaign[key] for key in campaign_ref):
        raise ColorLabCampaignError("materialized campaign reference changed")
    if root["evidence_mode"] == SYNTHETIC_MODE:
        if (
            root["execution_eligible"] is not False
            or root["state"] != "SYNTHETIC_OFFLINE_NOT_FOR_DEVICE"
            or root["recovery_boundary"] is not None
            or root["firmware"] is not None
            or root["panel"] is not None
        ):
            raise ColorLabCampaignError("synthetic release safety boundary differs")
        predecessor = root["predecessor_binding"]
        if not isinstance(predecessor, Mapping) or predecessor.get("mode") != SYNTHETIC_MODE:
            raise ColorLabCampaignError("synthetic predecessor binding differs")
        fixture_refs = predecessor.get("fixtures")
        if not isinstance(fixture_refs, Mapping) or set(fixture_refs) != set(
            SYNTHETIC_FIXTURES
        ):
            raise ColorLabCampaignError("synthetic fixture references differ")
        for name, spec in SYNTHETIC_FIXTURES.items():
            reference = fixture_refs[name]
            if not isinstance(reference, Mapping):
                raise ColorLabCampaignError("synthetic fixture reference is malformed")
            actual = _validate_synthetic_fixture(Path(str(reference["file"])), spec)
            if dict(reference) != actual:
                raise ColorLabCampaignError("synthetic fixture reference changed")
        safety = root["safety"]
        if not isinstance(safety, Mapping) or any(
            safety.get(key) is not wanted
            for key, wanted in {
                "device_access_performed": False,
                "network_requests": 0,
                "claim_created": False,
                "hardware_execution_performed": False,
                "visible_refresh_authorized": False,
                "runner_must_reject_before_network_or_claim": True,
                "real_guard_evidence_must_be_materialized_later": True,
            }.items()
        ):
            raise ColorLabCampaignError("synthetic release safety fields differ")
    elif root["evidence_mode"] == REAL_MODE:
        if (
            root["execution_eligible"] is not True
            or root["state"]
            != (
                "REAL_COMPARE_AND_SUPERSEDED_INCIDENT_BOUND_READY_FOR_"
                "RECOVERY_ORDINAL_1_WHITE_AUTHORIZATION"
            )
        ):
            raise ColorLabCampaignError("real release execution boundary differs")
        predecessor = root["predecessor_binding"]
        if not isinstance(predecessor, Mapping) or set(predecessor) != {
            "action_id",
            "mode",
            "compare_binding",
            "compare_replay_paths",
            "latest_visible_state",
            "ordinal_1_compiled_white_establishes_clean_baseline",
            "manual_live_no_intervening_refresh_confirmation_required",
        }:
            raise ColorLabCampaignError("real predecessor binding fields differ")
        replay_paths = predecessor["compare_replay_paths"]
        expected_replay_keys = {
            "compare_release_file",
            "compare_result_file",
            "compare_claim_registry",
            "compare_observation_file",
            "panel_file",
        }
        if not isinstance(replay_paths, Mapping) or set(replay_paths) != expected_replay_keys:
            raise ColorLabCampaignError("real predecessor compare paths differ")
        absolute_paths = {
            key: str(Path(replay_paths[key]).resolve()) for key in expected_replay_keys
        }
        if dict(replay_paths) != absolute_paths:
            raise ColorLabCampaignError("real predecessor compare paths are not canonical")
        try:
            replay = white_guard.load_compare_binding(
                compare_release_file=Path(absolute_paths["compare_release_file"]),
                compare_result_file=Path(absolute_paths["compare_result_file"]),
                compare_claim_registry=Path(absolute_paths["compare_claim_registry"]),
                compare_observation_file=Path(
                    absolute_paths["compare_observation_file"]
                ),
                panel_file=Path(absolute_paths["panel_file"]),
            ).binding
        except white_guard.CompareWhiteError as error:
            raise ColorLabCampaignError(
                f"real predecessor replay failed: {error}"
            ) from error
        if (
            predecessor["action_id"] != FIRST_PREDECESSOR_ACTION_ID
            or predecessor["mode"] != REAL_MODE
            or predecessor["compare_binding"] != replay
            or predecessor["latest_visible_state"]
            != "u04_u05_compare_four_blue_patches"
            or predecessor[
                "ordinal_1_compiled_white_establishes_clean_baseline"
            ]
            is not True
            or predecessor[
                "manual_live_no_intervening_refresh_confirmation_required"
            ]
            is not True
        ):
            raise ColorLabCampaignError("real predecessor binding differs")
        panel = _panel(Path(absolute_paths["panel_file"]))
        if root["panel"] != panel:
            raise ColorLabCampaignError("real release panel differs")
        recovery_boundary = root["recovery_boundary"]
        if not isinstance(recovery_boundary, Mapping):
            raise ColorLabCampaignError("real recovery boundary differs")
        current_recovery_boundary = _superseded_incident_binding(
            release_file=Path(
                str(recovery_boundary.get("superseded_release", {}).get("file"))
            ),
            result_file=Path(
                str(recovery_boundary.get("incident_result", {}).get("file"))
            ),
            claim_registry=Path(
                str(recovery_boundary.get("permanent_claim", {}).get("file"))
            ).parent,
        )
        if dict(recovery_boundary) != current_recovery_boundary:
            raise ColorLabCampaignError("real recovery incident replay changed")
        firmware = root["firmware"]
        if not isinstance(firmware, Mapping) or set(firmware) != {
            "binary",
            "elf",
            "binary_elf_link",
            "compiled_identity_report",
        }:
            raise ColorLabCampaignError("real release firmware fields differ")
        artifact_payloads: dict[str, bytes] = {}
        for key, maximum in (("binary", 32 << 20), ("elf", 64 << 20)):
            reference = firmware[key]
            if not isinstance(reference, Mapping) or set(reference) != {
                "file",
                "bytes",
                "sha256",
            }:
                raise ColorLabCampaignError("real firmware reference fields differ")
            actual, artifact_payloads[key] = _artifact(
                Path(str(reference["file"])),
                label=f"COLOR_LAB firmware {key}",
                maximum=maximum,
            )
            if dict(reference) != actual:
                raise ColorLabCampaignError("real firmware reference changed")
        if firmware["binary_elf_link"] != _binary_elf_link(
            artifact_payloads["binary"], artifact_payloads["elf"]
        ):
            raise ColorLabCampaignError("firmware BIN/ELF link changed")
        try:
            compiled_report = compiled_identity.validate(
                Path(str(firmware["elf"]["file"]))
            )
        except compiled_identity.ColorLabCompiledIdentityError as error:
            raise ColorLabCampaignError(
                f"compiled COLOR_LAB identity replay failed: {error}"
            ) from error
        if firmware["compiled_identity_report"] != compiled_report:
            raise ColorLabCampaignError("compiled COLOR_LAB identity report changed")
        formal = root["formal_u07_claim_absence"]
        if not isinstance(formal, Mapping):
            raise ColorLabCampaignError("formal U07 absence reference differs")
        current_formal = _formal_u07_absence(Path(str(formal.get("registry"))))
        if dict(formal) != current_formal:
            raise ColorLabCampaignError("formal U07 absence reference changed")
        expected_safety = {
            "materializer_device_access_performed": False,
            "materializer_network_requests": 0,
            "materializer_claim_created": False,
            "materializer_hardware_execution_performed": False,
            "visible_refresh_authorized_by_release": False,
            "one_exact_human_authorization_required_per_action": True,
            "runner_must_recheck_formal_u07_absence": True,
            "ordinal_1_is_the_only_planned_compare_to_white_recovery": True,
            "standalone_compare_white_is_fallback_only": True,
            "old_fault_namespace_ignored_not_cleared": True,
            "old_action_claim_remains_permanently_consumed": True,
            "new_nvs_namespace_and_key": True,
            "global_nvs_clear": False,
            "wifi_credentials_preserved": True,
            "all_action_ids_regenerated": True,
            "automatic_chaining": False,
            "automatic_retry": False,
            "automatic_recovery": False,
        }
        if root["safety"] != expected_safety:
            raise ColorLabCampaignError("real release safety fields differ")
    else:
        raise ColorLabCampaignError("materialized release evidence mode differs")
    return {
        "file": str(Path(release_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": canonical,
        "evidence_mode": root["evidence_mode"],
        "execution_eligible": root["execution_eligible"],
        "state": root["state"],
        "campaign": campaign,
    }


def validate_bundle(bundle_manifest_file: Path) -> dict[str, Any]:
    payload = _read_regular(
        bundle_manifest_file, label="COLOR_LAB recovery bundle manifest"
    )
    root = _decode(payload, label="COLOR_LAB recovery bundle manifest")
    expected_keys = {
        "schema_version",
        "kind",
        "state",
        "execution_authority",
        "supersedes",
        "firmware_uploads_planned",
        "visible_refreshes_authorized_by_bundle",
        "same_firmware_without_reset_or_reflash",
        "one_exact_human_authorization_required_per_action",
        "automatic_chaining",
        "automatic_retry",
        "automatic_recovery",
        "nvs_isolation",
        "files",
        "binary_elf_link",
        "offline_materialization",
        "integrity",
    }
    if set(root) != expected_keys:
        raise ColorLabCampaignError("recovery bundle fields differ")
    canonical = _validate_seal(root, label="COLOR_LAB recovery bundle manifest")
    exact = {
        "schema_version": 1,
        "kind": "mf1750-ec5-color-lab-recovery-self-contained-firmware-bundle",
        "state": (
            "READY_FOR_J2_OFF_FLASH_AND_DIAGNOSTIC_ONLY_"
            "NO_VISIBLE_REFRESH_AUTHORIZED"
        ),
        "execution_authority": "color-lab-recovery-real-release.json",
        "supersedes": "MF1750_EC5_COLOR_LAB_REAL_COMPARE_BOUND_20260809_V2_SELF_CONTAINED",
        "firmware_uploads_planned": 1,
        "visible_refreshes_authorized_by_bundle": 0,
        "same_firmware_without_reset_or_reflash": True,
        "one_exact_human_authorization_required_per_action": True,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "nvs_isolation": {
            "old_namespace": "mf1750_ec5cl",
            "old_key": "cursor",
            "new_namespace": NVS_NAMESPACE,
            "new_key": NVS_KEY,
            "old_state_ignored_not_cleared": True,
            "global_nvs_clear": False,
            "wifi_credentials_preserved": True,
        },
        "offline_materialization": {
            "device_access_performed": False,
            "network_requests": 0,
            "claim_created": False,
            "hardware_execution_performed": False,
        },
    }
    for key, wanted in exact.items():
        if root[key] != wanted:
            raise ColorLabCampaignError(f"recovery bundle {key} differs")
    files = root["files"]
    if not isinstance(files, Mapping) or set(files) != {
        "campaign",
        "release",
        "compiled_identity_sidecar",
        "firmware_binary",
        "firmware_elf",
    }:
        raise ColorLabCampaignError("recovery bundle file table differs")
    parent = Path(bundle_manifest_file).resolve().parent
    payloads: dict[str, bytes] = {}
    for key, reference in files.items():
        if not isinstance(reference, Mapping):
            raise ColorLabCampaignError("recovery bundle file reference is malformed")
        expected_reference_keys = {"name", "bytes", "sha256"}
        if key in ("campaign", "release"):
            expected_reference_keys.add("canonical_sha256")
        if set(reference) != expected_reference_keys:
            raise ColorLabCampaignError("recovery bundle file reference fields differ")
        name = reference["name"]
        if not isinstance(name, str) or Path(name).name != name:
            raise ColorLabCampaignError("recovery bundle filename is unsafe")
        observed = _read_regular(parent / name, label=f"recovery bundle {key}")
        if (
            reference["bytes"] != len(observed)
            or reference["sha256"] != sha256(observed)
        ):
            raise ColorLabCampaignError(f"recovery bundle {key} changed")
        payloads[key] = observed
    checked_campaign = validate_campaign(parent / files["campaign"]["name"])
    checked_release = validate_materialized_release(
        parent / files["release"]["name"]
    )
    if (
        files["campaign"]["canonical_sha256"]
        != checked_campaign["canonical_sha256"]
        or files["release"]["canonical_sha256"]
        != checked_release["canonical_sha256"]
        or root["execution_authority"] != files["release"]["name"]
    ):
        raise ColorLabCampaignError("recovery bundle authority differs")
    link = _binary_elf_link(
        payloads["firmware_binary"], payloads["firmware_elf"]
    )
    if root["binary_elf_link"] != link:
        raise ColorLabCampaignError("recovery bundle BIN/ELF link differs")
    report = compiled_identity.validate(parent / files["firmware_elf"]["name"])
    sidecar = _decode(
        payloads["compiled_identity_sidecar"],
        label="recovery bundle compiled identity sidecar",
    )
    if (
        sidecar.get("valid") is not True
        or sidecar.get("contract_id") != report["contract_id"]
        or sidecar.get("firmware", {}).get("elf", {}).get("sha256")
        != report["elf_sha256"]
    ):
        raise ColorLabCampaignError("recovery bundle identity sidecar differs")
    return {
        "file": str(Path(bundle_manifest_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": canonical,
        "execution_authority": str(
            (parent / root["execution_authority"]).resolve()
        ),
        "release_file_sha256": checked_release["file_sha256"],
        "firmware_binary_sha256": files["firmware_binary"]["sha256"],
        "firmware_elf_sha256": files["firmware_elf"]["sha256"],
        "execution_eligible": checked_release["execution_eligible"],
        "visible_refresh_authorized_by_bundle": 0,
    }


def required_authorization(action: Mapping[str, Any]) -> str:
    ordinal = action.get("ordinal")
    action_id = action.get("action_id")
    if not isinstance(ordinal, int) or not isinstance(action_id, str):
        raise ColorLabCampaignError("action is malformed")
    return (
        f"AUTHORIZE_ONE_VISIBLE_EC5_COLOR_LAB_RECOVERY_ORDINAL_{ordinal:02d}__"
        f"ACTION_{action_id.upper()}{AUTHORIZATION_SUFFIX}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_parser = commands.add_parser("compile", allow_abbrev=False)
    compile_parser.add_argument("--output", type=Path, required=True)
    validate_parser = commands.add_parser("validate", allow_abbrev=False)
    validate_parser.add_argument("--campaign", type=Path, required=True)
    synthetic = commands.add_parser("materialize-synthetic", allow_abbrev=False)
    synthetic.add_argument("--campaign", type=Path, required=True)
    synthetic.add_argument("--fixture-directory", type=Path, required=True)
    synthetic.add_argument("--output", type=Path, required=True)
    real = commands.add_parser("materialize-real", allow_abbrev=False)
    real.add_argument("--campaign", type=Path, required=True)
    real.add_argument("--compare-release", type=Path, required=True)
    real.add_argument("--compare-result", type=Path, required=True)
    real.add_argument("--compare-claim-registry", type=Path, required=True)
    real.add_argument("--compare-observation", type=Path, required=True)
    real.add_argument("--superseded-release", type=Path, required=True)
    real.add_argument("--superseded-result", type=Path, required=True)
    real.add_argument(
        "--superseded-claim-registry", type=Path, required=True
    )
    real.add_argument("--firmware-binary", type=Path, required=True)
    real.add_argument("--firmware-elf", type=Path, required=True)
    real.add_argument("--panel", type=Path, required=True)
    real.add_argument("--formal-u07-claim-registry", type=Path, required=True)
    real.add_argument("--output", type=Path, required=True)
    release = commands.add_parser("validate-release", allow_abbrev=False)
    release.add_argument("--release", type=Path, required=True)
    bundle = commands.add_parser("validate-bundle", allow_abbrev=False)
    bundle.add_argument("--manifest", type=Path, required=True)
    describe = commands.add_parser("describe", allow_abbrev=False)
    describe.add_argument("--ordinal", type=int, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "compile":
            output = generate_campaign(args.output)
        elif args.command == "validate":
            output = validate_campaign(args.campaign)
        elif args.command == "materialize-synthetic":
            output = materialize_synthetic_release(
                campaign_file=args.campaign,
                fixture_directory=args.fixture_directory,
                output_file=args.output,
            )
        elif args.command == "materialize-real":
            output = materialize_real_release(
                campaign_file=args.campaign,
                compare_release_file=args.compare_release,
                compare_result_file=args.compare_result,
                compare_claim_registry=args.compare_claim_registry,
                compare_observation_file=args.compare_observation,
                superseded_release_file=args.superseded_release,
                superseded_result_file=args.superseded_result,
                superseded_claim_registry=args.superseded_claim_registry,
                firmware_binary_file=args.firmware_binary,
                firmware_elf_file=args.firmware_elf,
                panel_file=args.panel,
                formal_u07_claim_registry=args.formal_u07_claim_registry,
                output_file=args.output,
            )
        elif args.command == "validate-release":
            output = validate_materialized_release(args.release)
        elif args.command == "validate-bundle":
            output = validate_bundle(args.manifest)
        else:
            actions = build_actions()
            if not 1 <= args.ordinal <= len(actions):
                raise ColorLabCampaignError("ordinal is outside 1..23")
            action = actions[args.ordinal - 1]
            output = {
                "action": action,
                "authorization": required_authorization(action),
                "execution_eligible": False,
                "reason": "compiled identity only; real release not materialized",
            }
    except ColorLabCampaignError as error:
        print(f"EC5 colour-lab campaign error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
