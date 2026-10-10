#!/usr/bin/env python3
"""Fail-closed architecture pack for a second fresh-white F1 construction.

R1/R2/R3 reuse the exact optical frame and controller DTM bytes of the sealed
F1 V3 G1/G2/G3 actions.  Their campaign identities are intentionally new and
G4 does not exist.  Offline identities bind the sealed post-HOLD white package;
live execution remains blocked until the post-HOLD clean-white evidence and
first-construction G3 camera reference are bound with real hashes.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import (  # noqa: E402
    mf1750_runtime_lut_luma_gray_mechanism_position_balanced_v3_pack as first_pack,
)


class FreshReconstructionV1PackError(RuntimeError):
    """Raised before an unbound or mismatched reconstruction can be sealed."""


@dataclass(frozen=True)
class Config:
    stage: str = "position-balanced-gray-fresh-reconstruction-v1"
    variant_key: str = "POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1"
    build_tag: str = "MF1750_EC5_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_2026-09-01"
    test_id: str = "EC5-POSITION-BALANCED-GRAY-FRESH-RECONSTRUCTION-V1"
    campaign_id: str = "EC5_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1"
    route_slug: str = "position-balanced-gray-fresh-reconstruction-v1"
    environment: str = "ec5_position_balanced_gray_fresh_reconstruction_v1"
    build_root: str = "b-position-balanced-gray-fresh-reconstruction-v1"
    generated_src_root: str = "generated-position-balanced-gray-fresh-reconstruction-v1"
    nvs_namespace: str = "pbgfr_v1"
    nvs_key: str = "cur_pbgfr1"
    nvs_boot_key: str = "boot_pbgfr1"

    @property
    def base_route(self) -> str:
        return f"/api/ec5/{self.route_slug}"


CONFIG = Config()
STAGE = CONFIG.stage
VARIANT_KEY = CONFIG.variant_key
BUILD_TAG = CONFIG.build_tag
TEST_ID = CONFIG.test_id
CAMPAIGN_ID = CONFIG.campaign_id
BASE_ROUTE = CONFIG.base_route
NVS_NAMESPACE = CONFIG.nvs_namespace
NVS_KEY = CONFIG.nvs_key
NVS_BOOT_KEY = CONFIG.nvs_boot_key
DEVICE_API_VERSION = "MF1750_EC5_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_DEVICE_V1"
IDENTITY_REVISION = "position-balanced-gray-fresh-reconstruction-v1"
CLASSIFICATION = (
    "SECOND_FRESH_WHITE_POSITION_BALANCED_GRAY_CONSTRUCTION_"
    "ZERO_QUALIFIED_UNTIL_TWO_CONSTRUCTIONS_COMPARE"
)
ARM_INTENT = "ARM_ONE_FIXED_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_ACTION"
EXECUTE_INTENT = (
    "EXECUTE_ARMED_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_ACTION_ONCE"
)
CLAIM_KIND_PREFIX = "mf1750-position-balanced-gray-fresh-reconstruction-v1"
PROFILE_ID = "L535_RUNTIME_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1"

SOURCE_WHITE_PACK_MODULE = (
    "tools.mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_pack"
)
SOURCE_AUTHORITY_REQUIRED_FILES = (
    "completed_action",
    "permanent_claim",
    "relay_protective_off",
    "capture_sidecar",
    "capture_jpeg",
    "camera_white_review",
)
FIRST_CONSTRUCTION_REQUIRED_FILES = (
    "g3_completed_action",
    "g3_permanent_claim",
    "g3_capture_sidecar",
    "g3_capture_jpeg",
    "g3_camera_relative_observation",
)


def _unbound_json_binding() -> dict[str, Any]:
    return {
        "path": None,
        "bytes": None,
        "file_sha256": None,
        "canonical_integrity_sha256": None,
    }


# These values bind the reviewed, independently sealed HOLD-white offline
# package.  Its future live retained evidence remains deliberately unbound.
SOURCE_PACKAGE_BINDING: dict[str, Any] = {
    "campaign_id": "EC5_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1",
    "contract_id": "79ac7bae08b912cdcbf3d959029d56c740407275ef70c91de738b8205dcaa433",
    "descriptor_id": "c8492ebc83abd0a1721abfd4ae001f405bb21e0e1d87ae1ae20fb076f6be41c6",
    "action_id": "934330c22eb1057c7595c5db6711bfcbc7647291e56f5bd8acd059aa6a65e21d",
    "firmware_bin_bytes": 787632,
    "firmware_bin_sha256": "7fe34992e9f0060d5b164d5c6f761ad38b755446854bd4bd22a65e52716a769b",
    "firmware_elf_bytes": 13214432,
    "firmware_elf_sha256": "1d16602e13fe29d9c025c6da78ea6ff3e10d0bc8a4d38139f1ab541ca3a0f33e",
}
SOURCE_PACKAGE_FILES: dict[str, dict[str, Any]] = {
    "pack": {
        "path": "tools/mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_pack.py",
        "bytes": 15112,
        "file_sha256": "7f99682512f2ec2981313c8d28ef8bff4db644e1397e11cc268826b4154d6b5d",
    },
    "build": {
        "path": "tools/mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_build.py",
        "bytes": 2880,
        "file_sha256": "a870a3b7ae41a709fbbd5614f1445a2ce713addc4a4255557c9bdc512637e31b",
    },
    "runner": {
        "path": "tools/mf1750_position_balanced_gray_hold_successor_v1_white_successor_v1_once.py",
        "bytes": 17689,
        "file_sha256": "cb84b7c33207c4747adf2bc25825338a76a817291c527e2f1a3bc8ffbffa00f4",
    },
    "offline_report": {
        "path": "docs/MF1750_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_OFFLINE_BUILD_2026-09-01.json",
        "bytes": 8582,
        "file_sha256": "e3ea8836899f6ec993e1b7a461b48971d652af89b75c0352dc20a0a8adee3c2b",
        "canonical_integrity_sha256": "15c4235749d754904c511e3523a8afb00add8890531f253a3260251b25e02e3f",
    },
    "sha256_manifest": {
        "path": "docs/MF1750_POSITION_BALANCED_GRAY_HOLD_SUCCESSOR_V1_SHA256_2026-09-01.txt",
        "bytes": 3391,
        "file_sha256": "221d69a5b681d0016f54b3a67875cd941d90a814a531f0d0477a4e727c76c615",
        "verified_entries": 24,
    },
}
SOURCE_BINDINGS = {
    name: _unbound_json_binding() for name in SOURCE_AUTHORITY_REQUIRED_FILES
}
SOURCE_BINDINGS["capture_jpeg"].pop("canonical_integrity_sha256")

# The first-construction G3 camera reference is independently required for the
# later same-geometry/same-settings comparison.  It is not white authority.
FIRST_CONSTRUCTION_BINDINGS = {
    name: _unbound_json_binding() for name in FIRST_CONSTRUCTION_REQUIRED_FILES
}
FIRST_CONSTRUCTION_BINDINGS["g3_capture_jpeg"].pop(
    "canonical_integrity_sha256"
)

ROLES = (
    "G1_ACTIVE_C7_SOURCE",
    "G2_COMMENTED_C0_TO_C7_POSITION_BALANCED_MIDDLE",
    "G3_ACTIVE_C3_C7_TARGET",
)
DRIVER_ROLES = ("Source", "Mid", "Target")
GLOBAL_HEADERS = ("active", "commented", "active")
ZERO_SHA256 = "0" * 64
ARTIFACTS: dict[str, int | str] = {
    "bin_bytes": 801680,
    "bin_sha256": "9b8493903baa1c656cf387481a52f217293d2f2ccedb09afebd2cdeda400f2a3",
    "elf_bytes": 13297000,
    "elf_sha256": "11019eb525d00c37c6b26b805561016f14b60dbdbc136878196dd42f4a2689a0",
}

# Read-only aliases let the reviewed V3 host mechanics check the unchanged
# balanced placement without importing any new recipe map.
CS1_RECIPE_AT_CELL = first_pack.CS1_RECIPE_AT_CELL
CS2_RECIPE_AT_CELL = first_pack.CS2_RECIPE_AT_CELL


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


def _binding_complete(binding: Mapping[str, Any], *, canonical: bool) -> bool:
    required = ("path", "bytes", "file_sha256")
    if canonical:
        required += ("canonical_integrity_sha256",)
    return (
        all(binding.get(key) not in (None, "") for key in required)
        and isinstance(binding.get("bytes"), int)
        and not isinstance(binding.get("bytes"), bool)
        and binding["bytes"] > 0
        and all(
            isinstance(binding.get(key), str)
            and len(binding[key]) == 64
            and set(binding[key]) <= set("0123456789abcdef")
            for key in required
            if key.endswith("sha256")
        )
    )


def source_package_is_sealed() -> bool:
    package_required = (
        "campaign_id",
        "contract_id",
        "descriptor_id",
        "action_id",
        "firmware_bin_bytes",
        "firmware_bin_sha256",
        "firmware_elf_bytes",
        "firmware_elf_sha256",
    )
    return not any(
        SOURCE_PACKAGE_BINDING.get(key) in (None, "") for key in package_required
    )


def live_source_evidence_is_sealed() -> bool:
    return all(
        _binding_complete(binding, canonical=name != "capture_jpeg")
        for name, binding in SOURCE_BINDINGS.items()
    )


def source_authority_is_sealed() -> bool:
    return source_package_is_sealed() and live_source_evidence_is_sealed()


def artifacts_are_sealed() -> bool:
    return (
        int(ARTIFACTS["bin_bytes"]) > 0
        and int(ARTIFACTS["elf_bytes"]) > 0
        and ARTIFACTS["bin_sha256"] != ZERO_SHA256
        and ARTIFACTS["elf_sha256"] != ZERO_SHA256
    )


def first_construction_reference_is_sealed() -> bool:
    return all(
        _binding_complete(binding, canonical=name != "g3_capture_jpeg")
        for name, binding in FIRST_CONSTRUCTION_BINDINGS.items()
    )


def _read_bound_bytes(binding: Mapping[str, Any], label: str) -> bytes:
    path = REPO_ROOT / str(binding["path"])
    if not path.is_file() or path.is_symlink():
        raise FreshReconstructionV1PackError(f"{label} missing or unsafe")
    payload = path.read_bytes()
    if len(payload) != binding["bytes"] or sha256_bytes(payload) != binding["file_sha256"]:
        raise FreshReconstructionV1PackError(f"{label} file binding differs")
    return payload


def _read_bound_json(binding: Mapping[str, Any], label: str) -> dict[str, Any]:
    payload = _read_bound_bytes(binding, label)
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreshReconstructionV1PackError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise FreshReconstructionV1PackError(f"{label} root differs")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = None
    if isinstance(integrity, Mapping):
        recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
    if (
        recorded != binding["canonical_integrity_sha256"]
        or sha256_bytes(canonical_json(body)) != recorded
    ):
        raise FreshReconstructionV1PackError(f"{label} canonical binding differs")
    return value


def _waiting_source_authority() -> dict[str, Any]:
    return {
        "state": "WAITING_FOR_HOLD_WHITE_COMPLETE_CLAIM_RELAY_OFF_48MP_CLEAN_WHITE_REVIEW",
        "sealed": False,
        "required_before_identity_seal_or_build": True,
        "source_pack_module": SOURCE_WHITE_PACK_MODULE,
        "source_package_binding": deepcopy(SOURCE_PACKAGE_BINDING),
        "evidence_bindings": deepcopy(SOURCE_BINDINGS),
        "missing_binding_names": [
            name
            for name, binding in SOURCE_BINDINGS.items()
            if not _binding_complete(binding, canonical=name != "capture_jpeg")
        ],
    }


def validate_source_package() -> dict[str, Any]:
    if not source_package_is_sealed():
        raise FreshReconstructionV1PackError(
            "HOLD-white predecessor package identity is unsealed"
        )
    try:
        source_pack = importlib.import_module(SOURCE_WHITE_PACK_MODULE)
    except (ImportError, ModuleNotFoundError) as error:
        raise FreshReconstructionV1PackError(
            "bound HOLD-white pack is unavailable"
        ) from error
    source_validation = source_pack.dry_validate(verify_artifacts=True)
    source_report = source_pack.build_report(verify_artifacts=True)
    observed = {
        "campaign_id": source_pack.CAMPAIGN_ID,
        "contract_id": source_report["contract_id"],
        "descriptor_id": source_report["descriptor_id"],
        "action_id": source_report["action_id"],
        "firmware_bin_bytes": source_pack.FIRMWARE_BIN_BYTES,
        "firmware_bin_sha256": source_pack.FIRMWARE_BIN_SHA256,
        "firmware_elf_bytes": source_pack.FIRMWARE_ELF_BYTES,
        "firmware_elf_sha256": source_pack.FIRMWARE_ELF_SHA256,
    }
    if source_validation.get("result") != "PASS" or observed != SOURCE_PACKAGE_BINDING:
        raise FreshReconstructionV1PackError(
            "bound HOLD-white predecessor package differs"
        )
    for label, binding in SOURCE_PACKAGE_FILES.items():
        _read_bound_bytes(binding, f"source package {label}")
    return {
        "state": "SEALED_OFFLINE_PREDECESSOR_PACKAGE",
        "sealed": True,
        "source_pack_module": SOURCE_WHITE_PACK_MODULE,
        "source_tuple": {
            key: SOURCE_PACKAGE_BINDING[key]
            for key in ("campaign_id", "contract_id", "descriptor_id", "action_id")
        },
        "source_artifacts": {
            "bin": {
                "bytes": SOURCE_PACKAGE_BINDING["firmware_bin_bytes"],
                "sha256": SOURCE_PACKAGE_BINDING["firmware_bin_sha256"],
            },
            "elf": {
                "bytes": SOURCE_PACKAGE_BINDING["firmware_elf_bytes"],
                "sha256": SOURCE_PACKAGE_BINDING["firmware_elf_sha256"],
            },
        },
        "package_files": deepcopy(SOURCE_PACKAGE_FILES),
        "live_evidence_required_before_any_device_request": list(
            SOURCE_AUTHORITY_REQUIRED_FILES
        ),
        "live_evidence_hashes_embedded_in_firmware_identity": False,
        "live_evidence_state": (
            "SEALED" if live_source_evidence_is_sealed() else "PENDING"
        ),
    }


def first_construction_reference_contract() -> dict[str, Any]:
    first = first_pack.build_report()
    expected = first["actions"][2]
    return {
        "state": "OFFLINE_EXPECTATION_SEALED_LIVE_REFERENCE_PENDING",
        "source_campaign_id": first_pack.CAMPAIGN_ID,
        "source_contract_id": first["contract_id"],
        "source_ordinal": 3,
        "source_descriptor_id": expected["descriptor_id"],
        "source_action_id": expected["action_id"],
        "geometry": deepcopy(first["contract"]["geometry"]),
        "camera_id": "48MP USB Camera",
        "same_geometry_and_settings_required": True,
        "required_live_evidence": list(FIRST_CONSTRUCTION_REQUIRED_FILES),
        "live_evidence_hashes_embedded_in_firmware_identity": False,
        "live_evidence_state": (
            "SEALED" if first_construction_reference_is_sealed() else "PENDING"
        ),
    }


def validate_source_authority(*, require_sealed: bool = True) -> dict[str, Any]:
    package_authority = validate_source_package()
    if not live_source_evidence_is_sealed():
        waiting = _waiting_source_authority()
        waiting["offline_predecessor_package"] = package_authority
        if require_sealed:
            raise FreshReconstructionV1PackError(waiting["state"])
        return waiting
    try:
        source_pack = importlib.import_module(SOURCE_WHITE_PACK_MODULE)
    except (ImportError, ModuleNotFoundError) as error:
        raise FreshReconstructionV1PackError("bound HOLD-white pack is unavailable") from error
    source_validation = source_pack.dry_validate(verify_artifacts=True)
    source_report = source_pack.build_report(verify_artifacts=True)
    action = _read_bound_json(SOURCE_BINDINGS["completed_action"], "source white action")
    claim = _read_bound_json(SOURCE_BINDINGS["permanent_claim"], "source white claim")
    relay = _read_bound_json(SOURCE_BINDINGS["relay_protective_off"], "source relay OFF")
    capture = _read_bound_json(SOURCE_BINDINGS["capture_sidecar"], "source 48MP capture")
    jpeg = _read_bound_bytes(SOURCE_BINDINGS["capture_jpeg"], "source 48MP JPEG")
    review = _read_bound_json(SOURCE_BINDINGS["camera_white_review"], "source clean-white review")
    expected = (
        SOURCE_PACKAGE_BINDING["campaign_id"],
        SOURCE_PACKAGE_BINDING["contract_id"],
        SOURCE_PACKAGE_BINDING["descriptor_id"],
        SOURCE_PACKAGE_BINDING["action_id"],
    )
    report_tuple = (
        source_pack.CAMPAIGN_ID,
        source_report["contract_id"],
        source_report["descriptor_id"],
        source_report["action_id"],
    )
    terminal = action.get("terminal_report")
    observed = (
        terminal.get("campaign_id") if isinstance(terminal, Mapping) else None,
        terminal.get("contract_id") if isinstance(terminal, Mapping) else None,
        terminal.get("transaction_descriptor_sha256")
        if isinstance(terminal, Mapping)
        else None,
        terminal.get("action_id") if isinstance(terminal, Mapping) else None,
    )
    if (
        source_validation.get("result") != "PASS"
        or report_tuple != expected
        or observed != expected
        or action.get("outcome") != "complete_pass"
        or action.get("visible_refreshes") != 1
        or not isinstance(terminal, Mapping)
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("driver_call_count_for_action") != 1
        or claim.get("action", {}).get("action_id") != expected[3]
        or relay.get("commanded_state") != "OFF"
        or relay.get("off_gate_passed") is not True
        or capture.get("campaign_id") != expected[0]
        or capture.get("action_id") != expected[3]
        or capture.get("camera", {}).get("camera_id") != "48MP USB Camera"
        or capture.get("photo", {}).get("sha256") != sha256_bytes(jpeg)
        or review.get("campaign_id") != expected[0]
        or review.get("action_id") != expected[3]
        or review.get("classification", {}).get(
            "camera_visible_clean_white_review_passed"
        )
        is not True
    ):
        raise FreshReconstructionV1PackError("post-HOLD white authority differs")
    return {
        "state": "SEALED",
        "sealed": True,
        "source_tuple": dict(
            zip(("campaign_id", "contract_id", "descriptor_id", "action_id"), expected)
        ),
        "offline_predecessor_package": package_authority,
        "camera_id": "48MP USB Camera",
        "camera_relative_only": True,
        "absolute_white_or_uniformity_qualified": False,
        "bindings": deepcopy(SOURCE_BINDINGS),
    }


def validate_first_construction_reference(
    *, require_sealed: bool = True
) -> dict[str, Any]:
    if not first_construction_reference_is_sealed():
        value = {
            "state": "WAITING_FOR_FIRST_F1_V3_G3_ACTION_AND_48MP_REFERENCE",
            "sealed": False,
            "required_before_identity_seal_or_build": True,
            "bindings": deepcopy(FIRST_CONSTRUCTION_BINDINGS),
        }
        if require_sealed:
            raise FreshReconstructionV1PackError(value["state"])
        return value
    action = _read_bound_json(
        FIRST_CONSTRUCTION_BINDINGS["g3_completed_action"], "first G3 action"
    )
    claim = _read_bound_json(
        FIRST_CONSTRUCTION_BINDINGS["g3_permanent_claim"], "first G3 claim"
    )
    capture = _read_bound_json(
        FIRST_CONSTRUCTION_BINDINGS["g3_capture_sidecar"], "first G3 48MP capture"
    )
    jpeg = _read_bound_bytes(
        FIRST_CONSTRUCTION_BINDINGS["g3_capture_jpeg"], "first G3 48MP JPEG"
    )
    observation = _read_bound_json(
        FIRST_CONSTRUCTION_BINDINGS["g3_camera_relative_observation"],
        "first G3 camera-relative observation",
    )
    first = first_pack.build_report()
    expected = first["actions"][2]
    terminal = action.get("terminal_report")
    before = capture.get("camera", {}).get("effective_settings_before_frame")
    after = capture.get("camera", {}).get("effective_settings_after_frame")
    completed_action = action.get("action")
    if (
        not isinstance(completed_action, Mapping)
        or completed_action.get("ordinal") != 3
        or completed_action.get("role") != expected["role"]
        or completed_action.get("descriptor_id") != expected["descriptor_id"]
        or completed_action.get("action_id") != expected["action_id"]
        or action.get("outcome") != "complete_pass"
        or action.get("visible_refreshes") != 1
        or not isinstance(terminal, Mapping)
        or terminal.get("campaign_id") != first_pack.CAMPAIGN_ID
        or terminal.get("contract_id") != first["contract_id"]
        or terminal.get("ordinal") != 3
        or terminal.get("action_id") != expected["action_id"]
        or terminal.get("terminal_state") != "COMPLETE"
        or claim.get("action", {}).get("action_id") != expected["action_id"]
        or capture.get("campaign_id") != first_pack.CAMPAIGN_ID
        or capture.get("ordinal") != 3
        or capture.get("action_id") != expected["action_id"]
        or capture.get("camera", {}).get("camera_id") != "48MP USB Camera"
        or not isinstance(before, Mapping)
        or dict(before) != after
        or capture.get("photo", {}).get("sha256") != sha256_bytes(jpeg)
        or observation.get("camera_relative_only") is not True
    ):
        raise FreshReconstructionV1PackError("first-construction G3 reference differs")
    return {
        "state": "SEALED",
        "sealed": True,
        "campaign_id": first_pack.CAMPAIGN_ID,
        "contract_id": first["contract_id"],
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "camera_id": "48MP USB Camera",
        "same_geometry_and_settings_required": True,
        "geometry": deepcopy(first["contract"]["geometry"]),
        "camera_effective_settings": deepcopy(dict(after)),
        "camera_effective_settings_sha256": sha256_bytes(canonical_json(after)),
        "mount_id": capture.get("coverage", {}).get("mount_id"),
        "bindings": deepcopy(FIRST_CONSTRUCTION_BINDINGS),
    }


def _frame_bytes(stage: str) -> bytes:
    return first_pack._grid_frame(stage)  # noqa: SLF001


def _identity(value: bytes) -> dict[str, Any]:
    return deepcopy(first_pack.base.frame_identity(value))


def _controller_identity(frame: bytes, controller: int) -> dict[str, Any]:
    return deepcopy(first_pack.cross.payload_identity(
        first_pack.cross.controller_stream(frame, controller)
    ))


def _build_report(
    source_authority: Mapping[str, Any], first_reference: Mapping[str, Any]
) -> dict[str, Any]:
    first = first_pack.build_report()
    stages = ("source", "middle", "target")
    actions: list[dict[str, Any]] = []
    prior: str | None = None
    for ordinal, (role, driver_role, header, stage) in enumerate(
        zip(ROLES, DRIVER_ROLES, GLOBAL_HEADERS, stages, strict=True), 1
    ):
        frame = _frame_bytes(stage)
        item: dict[str, Any] = {
            "ordinal": ordinal,
            "role": role,
            "driver_role": driver_role,
            "round": 1,
            "branch": f"{VARIANT_KEY}_{role}",
            "palette_source": "L535_RUNTIME",
            "global_header": header,
            "effective_driver_profile": deepcopy(first["actions"][ordinal - 1]["effective_driver_profile"]),
            "frame": _identity(frame),
            "cs1_dtm": _controller_identity(frame, 0),
            "cs2_dtm": _controller_identity(frame, 1),
            "prior_static_action_id": prior,
            "manual_or_host_selection_required": True,
            "automatic_chain_from_prior": False,
            "boot_admission": {
                "campaign_boot_binding_key": NVS_BOOT_KEY,
                "admission": (
                    "FRESH_CURSOR_AND_BOOT_KEY_ABSENT_ONLY"
                    if ordinal == 1
                    else "SAME_PERSISTED_CAMPAIGN_BOOT_ONLY"
                ),
                "required_prior_terminal_state": None if ordinal == 1 else "COMPLETE",
                "required_prior_ordinal": None if ordinal == 1 else ordinal - 1,
                "reboot_resume_allowed": False,
            },
            "byte_identity_with_first_f1_v3": {
                "source_ordinal": ordinal,
                "source_action_id": first["actions"][ordinal - 1]["action_id"],
                "frame_sha256": first["actions"][ordinal - 1]["frame"]["sha256"],
                "cs1_dtm_sha256": first["actions"][ordinal - 1]["cs1_dtm"]["sha256"],
                "cs2_dtm_sha256": first["actions"][ordinal - 1]["cs2_dtm"]["sha256"],
            },
        }
        if ordinal == 1:
            item["source_authority"] = deepcopy(dict(source_authority))
            item["first_construction_reference"] = deepcopy(dict(first_reference))
        descriptor = {
            "schema": "mf1750-position-balanced-gray-fresh-reconstruction-v1-action",
            "variant": VARIANT_KEY,
            "build_tag": BUILD_TAG,
            **item,
        }
        item["descriptor_id"] = sha256_bytes(canonical_json(descriptor))
        item["action_id"] = sha256_bytes(
            (
                "MF1750_POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1|"
                f"{ordinal}|{item['descriptor_id']}"
            ).encode("ascii")
        )
        prior = item["action_id"]
        actions.append(item)
    contract = {
        "schema": "mf1750-position-balanced-gray-fresh-reconstruction-v1-contract",
        "stage": STAGE,
        "variant_key": VARIANT_KEY,
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        "base_route": BASE_ROUTE,
        "device_api_version": DEVICE_API_VERSION,
        "identity_revision": IDENTITY_REVISION,
        "classification": CLASSIFICATION,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "nvs_boot_key": NVS_BOOT_KEY,
        "source_authority": deepcopy(dict(source_authority)),
        "first_construction_reference": deepcopy(dict(first_reference)),
        "geometry": deepcopy(first["contract"]["geometry"]),
        "recipes": deepcopy(first["contract"]["recipes"]),
        "actions": actions,
        "action_count": 3,
        "required_ordinals": [1, 2, 3],
        "g4_present": False,
        "same_geometry_and_camera_settings_as_first_construction_required": True,
        "comparison_scope": "CONTROLLER_LOCAL_RECIPE_AND_POSITION_MATCHED",
        "camera_id": "48MP USB Camera",
        "spatial_dither": False,
        "full_screen_global_refresh": True,
        "partial_refresh": False,
        "startup_refresh": False,
        "boot_action": False,
        "retry": False,
        "fallback": False,
        "automatic_recovery": False,
        "autochain": False,
        "j2_off_app_only_flash_required": True,
        "independent_factory_otp_white_successor_required": True,
        "reproducible_held_candidate_claimed": False,
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
    }
    return {
        "schema_version": 1,
        "kind": "mf1750-position-balanced-gray-fresh-reconstruction-v1-offline-identities",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "actions": actions,
        "contract": contract,
        "contract_id": sha256_bytes(canonical_json(contract)),
    }


def template_report() -> dict[str, Any]:
    value = _build_report(
        validate_source_package(),
        first_construction_reference_contract(),
    )
    value["identity_status"] = "SEALED_OFFLINE_LIVE_RUN_GATES_PENDING"
    return value


def build_report() -> dict[str, Any]:
    return _build_report(
        validate_source_package(),
        first_construction_reference_contract(),
    )


def artifact_paths() -> tuple[Path, Path]:
    root = REPO_ROOT / ".pio" / CONFIG.build_root / CONFIG.environment
    return root / "firmware.bin", root / "firmware.elf"


def verify_artifact_files() -> dict[str, Any]:
    if not artifacts_are_sealed():
        raise FreshReconstructionV1PackError("reconstruction artifacts are unsealed")
    observed: dict[str, dict[str, Any]] = {}
    for label, path, size_key, sha_key in (
        ("bin", artifact_paths()[0], "bin_bytes", "bin_sha256"),
        ("elf", artifact_paths()[1], "elf_bytes", "elf_sha256"),
    ):
        if not path.is_file() or path.is_symlink():
            raise FreshReconstructionV1PackError(f"reconstruction {label} missing")
        payload = path.read_bytes()
        if (
            len(payload) != ARTIFACTS[size_key]
            or sha256_bytes(payload) != ARTIFACTS[sha_key]
        ):
            raise FreshReconstructionV1PackError(
                f"reconstruction {label} artifact binding differs"
            )
        observed[label] = {
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
            "path": path.relative_to(REPO_ROOT).as_posix(),
        }
    return observed


def validate_source_gate() -> dict[str, Any]:
    """Compatibility facade used only by the reviewed one-action host."""

    return validate_live_execution_gate()


def validate_live_execution_gate() -> dict[str, Any]:
    return {
        "source_authority": validate_source_authority(require_sealed=True),
        "first_construction_reference": validate_first_construction_reference(
            require_sealed=True
        ),
        "state": "SEALED_FOR_ONE_EXPLICIT_LIVE_ACTION",
    }


def dry_validate(
    *, require_sealed: bool = True, verify_artifacts: bool = False
) -> dict[str, Any]:
    if require_sealed:
        report = build_report()
        state = "SEALED"
    else:
        report = template_report()
        state = report["identity_status"]
    first = first_pack.build_report()
    if (
        len(report["actions"]) != 3
        or report["contract"]["g4_present"] is not False
        or report["contract"]["autochain"] is not False
        or report["contract"]["qualified_gray_levels"] != 0
    ):
        raise FreshReconstructionV1PackError("reconstruction contract invariant differs")
    for index, action in enumerate(report["actions"]):
        original = first["actions"][index]
        if (
            action["frame"] != original["frame"]
            or action["cs1_dtm"] != original["cs1_dtm"]
            or action["cs2_dtm"] != original["cs2_dtm"]
            or action["descriptor_id"] == original["descriptor_id"]
            or action["action_id"] == original["action_id"]
        ):
            raise FreshReconstructionV1PackError(
                f"R{index + 1}/G{index + 1} byte parity or identity isolation differs"
            )
    artifact_evidence = verify_artifact_files() if verify_artifacts else None
    return {
        "schema_version": 1,
        "kind": "mf1750-position-balanced-gray-fresh-reconstruction-v1-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "identity_status": state,
        "action_count": 3,
        "g4_present": False,
        "byte_identical_to_first_f1_v3_g1_g2_g3": True,
        "new_action_and_descriptor_identities": True,
        "source_authority_sealed": source_authority_is_sealed(),
        "source_predecessor_package_sealed": source_package_is_sealed(),
        "first_construction_reference_sealed": first_construction_reference_is_sealed(),
        "live_execution_gate_passed": (
            source_authority_is_sealed()
            and first_construction_reference_is_sealed()
        ),
        "qualified_colors": 0,
        "qualified_gray_levels": 0,
        "qualified_brightness_levels": 0,
        "artifacts_verified": verify_artifacts,
        "artifact_evidence": artifact_evidence,
        "no_retry": True,
        "no_fallback": True,
        "no_recovery": True,
        "no_autochain": True,
    }


if __name__ == "__main__":
    print(json.dumps(dry_validate(require_sealed=False), indent=2, sort_keys=True))
