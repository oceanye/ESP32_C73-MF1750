#!/usr/bin/env python3
"""Compile and seal the two-action factory-OTP dither-atlas release.

This module is deliberately offline.  It creates no network client and performs
no device, serial, firmware-upload, or visible-refresh operation.  A real
release is eligible only after its exact firmware, panel, offline atlas bundle,
and the finalized ordinal-3 white result from the preceding OTP matrix have
all been replayed and sealed.
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

from tools import mf1750_ec5_dither_color_atlas as offline_bundle  # noqa: E402
from tools import mf1750_ec5_dither_color_atlas_contract as contract  # noqa: E402
from tools import mf1750_ec5_otp_transition_matrix_physical_once as matrix_once  # noqa: E402


SCHEMA_VERSION = 1
CAMPAIGN_KIND = "mf1750-ec5-dither-color-atlas-compiled-campaign"
RELEASE_KIND = "mf1750-ec5-dither-color-atlas-materialized-release"
REAL_MODE = "REAL_OTP_MATRIX_ORDINAL3_WHITE_ANCHOR_VALIDATED"
ACTION_COUNT = 2
CAMPAIGN_ROUNDS = 1
WHITE_CHECKPOINT_ORDINALS = (2,)
RECOMMENDED_SAFE_STOP_ORDINALS = (2,)
FIRST_SAFE_STOP_ORDINAL = 2
FIRST_COMPLETE_ROUND_STOP_ORDINAL = 2

# This is the already-consumed, manually finalized white action that currently
# defines the panel's visible starting state.  The associated byte identities
# below make "the matrix white result" an exact evidence object, not a role-only
# or latest-file lookup.
FIRST_PREDECESSOR_ACTION_ID = (
    "54190f82f4797d1e0d46b2e002f6cbad006bdcdd7eb73b6ae5c0325acbfcae77"
)
EXPECTED_MATRIX_RELEASE_FILE_SHA256 = (
    "3f03a022b603fc312d836093b8c94cd6d6f0e7be5a3ff32f71337673cca263e8"
)
EXPECTED_MATRIX_RELEASE_CANONICAL_SHA256 = (
    "9c38297823699b43aa007e557cf5c435a30e9ebf4b8d2fb23d14a2c45eecc628"
)
EXPECTED_MATRIX_RESULT_FILE_SHA256 = (
    "d525173ed358246b6890fcf871a5c3268675f4b9b922d66fdb6911725ecb635c"
)
EXPECTED_MATRIX_RESULT_CANONICAL_SHA256 = (
    "8e0deb157d58c1677394dd2b3eeb78047c182afb34c8aacf72627fb63cf8b717"
)
EXPECTED_MATRIX_OBSERVATION_FILE_SHA256 = (
    "5d5bf4414ac8d150e73bde393f438f069ba511f719808723156cf2ba66b68e41"
)
EXPECTED_MATRIX_OBSERVATION_CANONICAL_SHA256 = (
    "5f9f72ac1e5cde8fea2e970edfd029a4adc6d2f1a0599d0d51297d4a0df284c7"
)
EXPECTED_MATRIX_CLAIM_FILE_SHA256 = (
    "78cbd7d30d0b82476bd227a82fa879cfc1bc749c584a6f5c18500679f1e52e20"
)
EXPECTED_MATRIX_CLAIM_CANONICAL_SHA256 = (
    "2c8d0b2af0c997e01b99e54f9847a14e2715f0585a77dd6026dc52179f125b88"
)
EXPECTED_MATRIX_PANEL_FILE_SHA256 = (
    "8d0f6202282c16cfb32246812f50aecc964f5acfd643b65b049672a43cc03b05"
)
EXPECTED_MATRIX_BOOT_NONCE = "1a6941119534644a"

AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN"
MAX_JSON_BYTES = 16 * 1024 * 1024

ENDPOINTS = {
    "version": "/api/ec5/dither-color-atlas/version",
    "manifest": "/api/ec5/dither-color-atlas/manifest",
    "status": "/api/ec5/dither-color-atlas/status",
    "report": "/api/ec5/dither-color-atlas/report",
    "arm": "/api/ec5/dither-color-atlas/arm",
    "execute": "/api/ec5/dither-color-atlas/execute",
}
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_DITHER_COLOR_ATLAS_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_FACTORY_OTP_DITHER_COLOR_ATLAS_ACTION_ONCE"
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


class DitherColorAtlasCampaignError(RuntimeError):
    """An immutable campaign, artifact, or predecessor check failed."""


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
        raise DitherColorAtlasCampaignError(
            f"value is not canonical JSON: {error}"
        ) from error


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value) if isinstance(value, Mapping) else value
    return hashlib.sha256(payload).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DitherColorAtlasCampaignError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise DitherColorAtlasCampaignError(
                f"{label} must be a regular non-symlink file"
            )
        if before.st_size <= 0 or before.st_size > maximum:
            raise DitherColorAtlasCampaignError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise DitherColorAtlasCampaignError(
            f"could not read {label}: {error}"
        ) from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise DitherColorAtlasCampaignError(f"{label} changed while read")
    if len(payload) != after.st_size:
        raise DitherColorAtlasCampaignError(f"{label} read length differs")
    return payload


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                DitherColorAtlasCampaignError(f"{label} contains forbidden {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DitherColorAtlasCampaignError(
            f"{label} is invalid JSON: {error}"
        ) from error
    if not isinstance(root, Mapping):
        raise DitherColorAtlasCampaignError(f"{label} root must be an object")
    return root


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    path = Path(path)
    payload = canonical_json_bytes(value)
    try:
        parent_meta = path.parent.lstat()
        parent = path.parent.resolve(strict=True)
        if stat.S_ISLNK(parent_meta.st_mode) or not stat.S_ISDIR(parent_meta.st_mode):
            raise DitherColorAtlasCampaignError(
                "output parent must be a non-symlink directory"
            )
        with (parent / path.name).open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise DitherColorAtlasCampaignError(f"refusing to overwrite {path}") from error
    except OSError as error:
        raise DitherColorAtlasCampaignError(
            f"could not create {path}: {error}"
        ) from error
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
        raise DitherColorAtlasCampaignError(f"{label} integrity fields differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {
        "canonical_sha256": sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected:
        raise DitherColorAtlasCampaignError(f"{label} integrity differs")
    return str(integrity["canonical_sha256"])


def _frame_identity(role: str) -> dict[str, Any]:
    identity = contract.ROLE_IDENTITIES[role]
    return {
        "layout_id": contract.LAYOUT_ID,
        "frame": {
            "bytes": identity["frame"]["bytes"],
            "sha256": identity["frame"]["sha256"],
            "fnv1a": identity["frame"]["fnv1a_hex"],
            "encoding": "canonical-row-major-two-4bit-codes-per-byte",
            "controllers": [
                {
                    "controller": "CS1",
                    "source_half": 0,
                    "bytes": identity["cs1_dtm"]["bytes"],
                    "sha256": identity["cs1_dtm"]["sha256"],
                    "fnv1a": identity["cs1_dtm"]["fnv1a_hex"],
                },
                {
                    "controller": "CS2",
                    "source_half": 1,
                    "bytes": identity["cs2_dtm"]["bytes"],
                    "sha256": identity["cs2_dtm"]["sha256"],
                    "fnv1a": identity["cs2_dtm"]["fnv1a_hex"],
                },
            ],
        },
        "profile_source": "factory_otp",
        "runtime_lut_write": False,
        "spatial_dithering": role == contract.ROLE_ATLAS,
        "single_pixel_multi_pigment_claim": False,
        "physical_colour_claim": False,
    }


def build_actions() -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for descriptor in contract.DESCRIPTORS:
        action = deepcopy(dict(descriptor))
        action["action_id"] = action["hardware_action_id"]
        action["frame"] = _frame_identity(str(action["role"]))
        actions.append(action)
    return actions


def build_campaign() -> dict[str, Any]:
    manifest = contract.campaign_manifest()
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": CAMPAIGN_KIND,
        "identity_revision": contract.IDENTITY_REVISION,
        "classification": contract.CLASSIFICATION,
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "campaign_id": contract.CAMPAIGN_ID,
        "firmware_contract_id": manifest["contract_id"],
        "firmware_contract": manifest,
        "device_schema_version": contract.TOP_SCHEMA_VERSION,
        "driver_evidence_schema_version": contract.DRIVER_EVIDENCE_SCHEMA_VERSION,
        "first_predecessor_action_id": FIRST_PREDECESSOR_ACTION_ID,
        "first_predecessor_kind": (
            "exact_finalized_otp_transition_matrix_ordinal3_white"
        ),
        "action_count": ACTION_COUNT,
        "campaign_rounds": CAMPAIGN_ROUNDS,
        "first_safe_stop_ordinal": FIRST_SAFE_STOP_ORDINAL,
        "white_checkpoint_ordinals": list(WHITE_CHECKPOINT_ORDINALS),
        "recommended_safe_stop_ordinals": list(RECOMMENDED_SAFE_STOP_ORDINALS),
        "first_complete_round_stop_ordinal": FIRST_COMPLETE_ROUND_STOP_ORDINAL,
        "nvs_contract": {
            "namespace": contract.NVS_NAMESPACE,
            "key": contract.NVS_KEY,
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
        "actions": build_actions(),
        "classification_contract": {
            "profile_source": "factory_otp",
            "runtime_lut_or_waveform_changed": False,
            "spatial_dither_color_comparison": True,
            "single_pixel_multi_pigment_claim": False,
            "physical_colour_claim": False,
            "device_accessed_by_this_compiler": False,
            "visible_refresh_authorized_by_this_compiler": False,
        },
    }
    return _seal(unsigned)


def generate_campaign(output_file: Path) -> dict[str, Any]:
    root = build_campaign()
    _write_new(output_file, root)
    return root


def validate_campaign(manifest_file: Path) -> dict[str, Any]:
    payload = _read_regular(manifest_file, label="dither color-atlas campaign")
    root = _decode(payload, label="dither color-atlas campaign")
    canonical = _validate_seal(root, label="dither color-atlas campaign")
    if dict(root) != build_campaign():
        raise DitherColorAtlasCampaignError(
            "compiled dither color-atlas campaign differs"
        )
    return {
        "file": str(Path(manifest_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": canonical,
        "action_count": ACTION_COUNT,
        "first_safe_stop_ordinal": FIRST_SAFE_STOP_ORDINAL,
        "actions": deepcopy(root["actions"]),
    }


def _identity_needles() -> tuple[str, ...]:
    values = [
        contract.CLASSIFICATION,
        contract.BUILD_TAG,
        contract.TEST_ID,
        contract.CAMPAIGN_ID,
        contract.DEVICE_API_VERSION,
        contract.campaign_manifest()["contract_id"],
        contract.NVS_NAMESPACE,
        contract.NVS_KEY,
        *ENDPOINTS.values(),
    ]
    for descriptor in contract.DESCRIPTORS:
        values.extend(
            (
                str(descriptor["descriptor_id"]),
                str(descriptor["hardware_action_id"]),
            )
        )
    return tuple(values)


def _artifact(path: Path, *, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    payload = _read_regular(path, label=label, maximum=maximum)
    missing = [
        needle for needle in _identity_needles() if needle.encode() not in payload
    ]
    if missing:
        raise DitherColorAtlasCampaignError(
            f"{label} lacks frozen identity string {missing[0]!r}"
        )
    return (
        {
            "file": str(Path(path).resolve()),
            "bytes": len(payload),
            "sha256": sha256(payload),
        },
        payload,
    )


def _binary_elf_link(binary: bytes, elf: bytes) -> dict[str, Any]:
    """Verify the ESP-IDF app descriptor binds this BIN to this exact ELF."""

    app_descriptor_offset = 32
    embedded_elf_sha256_offset = 176
    app_descriptor_magic = bytes.fromhex("3254cdab")
    selected_elf_sha256 = hashlib.sha256(elf).digest()
    if (
        len(binary) < embedded_elf_sha256_offset + 32
        or not binary.startswith(b"\xe9")
        or not elf.startswith(b"\x7fELF")
        or binary[
            app_descriptor_offset : app_descriptor_offset + len(app_descriptor_magic)
        ]
        != app_descriptor_magic
        or binary[embedded_elf_sha256_offset : embedded_elf_sha256_offset + 32]
        != selected_elf_sha256
    ):
        raise DitherColorAtlasCampaignError(
            "firmware BIN app descriptor does not bind the selected ELF"
        )
    return {
        "app_descriptor_offset": app_descriptor_offset,
        "app_descriptor_magic_hex": app_descriptor_magic.hex(),
        "embedded_elf_sha256_offset": embedded_elf_sha256_offset,
        "embedded_elf_sha256": selected_elf_sha256.hex(),
        "selected_elf_sha256": hashlib.sha256(elf).hexdigest(),
        "exact_match": True,
    }


def _panel(path: Path) -> dict[str, str]:
    payload = _read_regular(path, label="live panel identity")
    root = _decode(payload, label="live panel identity")
    expected = {"model", "serial", "board_id", "pcb_revision"}
    if set(root) != expected or any(
        not isinstance(root[key], str) or not root[key].strip() for key in expected
    ):
        raise DitherColorAtlasCampaignError("live panel identity differs")
    return {key: str(root[key]) for key in sorted(expected)}


def _reference(path: Path, *, label: str) -> dict[str, Any]:
    payload = _read_regular(path, label=label)
    root = _decode(payload, label=label)
    canonical = _validate_seal(root, label=label)
    return {
        "file": str(Path(path).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "integrity_sha256": canonical,
    }


def _claim_registry(path: Path) -> Path:
    path = Path(path)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise DitherColorAtlasCampaignError(
            f"matrix claim registry cannot be resolved: {error}"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise DitherColorAtlasCampaignError(
            "matrix claim registry must be a non-symlink directory"
        )
    return resolved


def _matrix_white_anchor(
    *,
    matrix_release_file: Path,
    result_file: Path,
    observation_file: Path,
    claim_registry: Path,
) -> dict[str, Any]:
    try:
        context = matrix_once.load_release(matrix_release_file)
        result = matrix_once.validate_result(
            context, result_file, claim_registry=claim_registry
        )
        observation = matrix_once.validate_observation(
            context,
            observation_file,
            result_file=result_file,
            claim_registry=claim_registry,
        )
    except matrix_once.OtpTransitionMatrixPhysicalError as error:
        raise DitherColorAtlasCampaignError(
            f"matrix ordinal3 white predecessor replay failed: {error}"
        ) from error

    action = result.get("action")
    visual = observation.get("visual")
    supervised = observation.get("supervised")
    claim_value = result.get("claim")
    if (
        result.get("ordinal") != 3
        or result.get("outcome") != "complete_pass"
        or result.get("state") != "authorization_permanently_consumed_do_not_rerun"
        or not isinstance(action, Mapping)
        or action.get("action_id") != FIRST_PREDECESSOR_ACTION_ID
        or action.get("role") != "OTP_WHITE_RECOVERY"
        or observation.get("ordinal") != 3
        or observation.get("sequence_gate_pass") is not True
        or observation.get("automatic_next_action_authorized") is not False
        or observation.get("retry_authorized") is not False
        or observation.get("recovery_authorized") is not False
        or not isinstance(visual, Mapping)
        or visual.get("full_clean_white") is not True
        or visual.get("no_unexpected_residual") is not True
        or not isinstance(supervised, Mapping)
        or supervised.get("electrical_normal") is not True
        or supervised.get("esp32_did_not_restart") is not True
        or not isinstance(claim_value, Mapping)
        or claim_value.get("state") != "permanently_claimed_before_first_arm_post"
        or result.get("preflight", {}).get("boot_nonce") != EXPECTED_MATRIX_BOOT_NONCE
    ):
        raise DitherColorAtlasCampaignError(
            "predecessor is not the exact finalized matrix ordinal3 clean white"
        )

    release = _reference(matrix_release_file, label="matrix predecessor release")
    result_ref = _reference(result_file, label="matrix ordinal3 white result")
    observation_ref = _reference(
        observation_file, label="matrix ordinal3 white observation"
    )
    registry = _claim_registry(claim_registry)
    expected_claim_file = registry / f"{FIRST_PREDECESSOR_ACTION_ID}.json"
    try:
        actual_claim_file = Path(str(claim_value.get("file"))).resolve(strict=True)
    except OSError as error:
        raise DitherColorAtlasCampaignError(
            f"matrix ordinal3 claim cannot be resolved: {error}"
        ) from error
    if actual_claim_file != expected_claim_file:
        raise DitherColorAtlasCampaignError("matrix ordinal3 claim path differs")
    claim = _reference(actual_claim_file, label="matrix ordinal3 permanent claim")

    frozen = {
        "release": (
            EXPECTED_MATRIX_RELEASE_FILE_SHA256,
            EXPECTED_MATRIX_RELEASE_CANONICAL_SHA256,
        ),
        "result": (
            EXPECTED_MATRIX_RESULT_FILE_SHA256,
            EXPECTED_MATRIX_RESULT_CANONICAL_SHA256,
        ),
        "observation": (
            EXPECTED_MATRIX_OBSERVATION_FILE_SHA256,
            EXPECTED_MATRIX_OBSERVATION_CANONICAL_SHA256,
        ),
        "claim": (
            EXPECTED_MATRIX_CLAIM_FILE_SHA256,
            EXPECTED_MATRIX_CLAIM_CANONICAL_SHA256,
        ),
    }
    references = {
        "release": release,
        "result": result_ref,
        "observation": observation_ref,
        "claim": claim,
    }
    for name, reference in references.items():
        expected_file_sha, expected_integrity = frozen[name]
        if (
            reference["file_sha256"] != expected_file_sha
            or reference["integrity_sha256"] != expected_integrity
        ):
            raise DitherColorAtlasCampaignError(
                f"matrix ordinal3 {name} frozen identity differs"
            )
    if (
        claim_value.get("bytes") != claim["bytes"]
        or claim_value.get("file_sha256") != claim["file_sha256"]
        or claim_value.get("integrity_sha256") != claim["integrity_sha256"]
    ):
        raise DitherColorAtlasCampaignError("matrix ordinal3 claim reference differs")

    release_root = context.release_root
    if not isinstance(release_root, Mapping):
        raise DitherColorAtlasCampaignError("matrix predecessor release root differs")
    matrix_panel = release_root.get("panel")
    matrix_panel_file = release_root.get("panel_file")
    if (
        not isinstance(matrix_panel, Mapping)
        or not isinstance(matrix_panel_file, Mapping)
        or matrix_panel_file.get("file_sha256") != EXPECTED_MATRIX_PANEL_FILE_SHA256
    ):
        raise DitherColorAtlasCampaignError("matrix predecessor panel binding differs")
    return {
        "kind": "exact_finalized_otp_transition_matrix_ordinal3_white",
        "action_id": FIRST_PREDECESSOR_ACTION_ID,
        "ordinal": 3,
        "role": "OTP_WHITE_RECOVERY",
        "matrix_release": release,
        "result": result_ref,
        "observation": observation_ref,
        "claim": claim,
        "claim_registry": {
            "directory": str(registry),
            "registry_id": matrix_once.CLAIM_REGISTRY_ID,
        },
        "panel": deepcopy(dict(matrix_panel)),
        "panel_file_sha256": EXPECTED_MATRIX_PANEL_FILE_SHA256,
        "required_previous_boot_nonce": EXPECTED_MATRIX_BOOT_NONCE,
        "latest_visible_state": "clean_full_white_factory_otp",
        "clean_white_confirmed": True,
        "manual_no_intervening_refresh_confirmation_required": True,
    }


def _validated_offline_bundle(path: Path) -> dict[str, Any]:
    try:
        checked = offline_bundle.validate_bundle(path)
    except offline_bundle.DitherAtlasToolError as error:
        raise DitherColorAtlasCampaignError(
            f"offline atlas bundle validation failed: {error}"
        ) from error
    if (
        checked.get("hardware_tested") is not False
        or checked.get("visible_refresh_authorized") is not False
        or checked.get("roi_count") != 70
    ):
        raise DitherColorAtlasCampaignError("offline atlas bundle safety differs")
    return deepcopy(dict(checked))


def materialize_real_release(
    *,
    campaign_file: Path,
    firmware_binary: Path,
    firmware_elf: Path,
    panel_file: Path,
    offline_bundle_dir: Path,
    matrix_release_file: Path,
    anchor_result_file: Path,
    anchor_observation_file: Path,
    anchor_claim_registry: Path,
    output_file: Path,
) -> dict[str, Any]:
    checked_campaign = validate_campaign(campaign_file)
    binary, binary_payload = _artifact(
        firmware_binary,
        label="dither color-atlas firmware binary",
        maximum=4_000_000,
    )
    elf, elf_payload = _artifact(
        firmware_elf,
        label="dither color-atlas firmware ELF",
        maximum=32_000_000,
    )
    binary_elf_link = _binary_elf_link(binary_payload, elf_payload)
    panel = _panel(panel_file)
    panel_payload = _read_regular(panel_file, label="live panel identity")
    if sha256(panel_payload) != EXPECTED_MATRIX_PANEL_FILE_SHA256:
        raise DitherColorAtlasCampaignError(
            "live panel evidence is not the matrix-bound current panel file"
        )
    anchor = _matrix_white_anchor(
        matrix_release_file=matrix_release_file,
        result_file=anchor_result_file,
        observation_file=anchor_observation_file,
        claim_registry=anchor_claim_registry,
    )
    if anchor["panel"] != panel:
        raise DitherColorAtlasCampaignError(
            "live panel identity differs from the matrix predecessor panel"
        )
    bundle = _validated_offline_bundle(offline_bundle_dir)
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": RELEASE_KIND,
        "evidence_mode": REAL_MODE,
        "compiled_campaign": {
            key: checked_campaign[key]
            for key in (
                "file",
                "bytes",
                "file_sha256",
                "canonical_sha256",
                "action_count",
                "first_safe_stop_ordinal",
            )
        },
        "firmware": {
            "binary": binary,
            "elf": elf,
            "binary_elf_link": binary_elf_link,
        },
        "offline_atlas_bundle": bundle,
        "panel": panel,
        "panel_file": {
            "file": str(Path(panel_file).resolve()),
            "file_sha256": sha256(panel_payload),
        },
        "predecessor_binding": anchor,
        "execution_eligible": True,
        "safety": {
            "profile_source": "factory_otp",
            "spatial_dithering_only": True,
            "runtime_lut_or_waveform_write": False,
            "electrical_parameter_write": False,
            "new_nvs_namespace_and_key": True,
            "global_nvs_clear": False,
            "wifi_credentials_preserved": True,
            "automatic_chaining": False,
            "automatic_retry": False,
            "automatic_recovery": False,
            "one_exact_human_authorization_required_per_action": True,
            "same_boot_and_no_intervening_refresh_required": True,
            "materializer_device_access_performed": False,
            "materializer_network_requests": 0,
            "materializer_visible_refreshes": 0,
            "visible_refresh_authorized_by_release": 0,
        },
        "state": (
            "REAL_FACTORY_OTP_DITHER_COLOR_ATLAS_RELEASE_READY_FOR_"
            "J2_OFF_PREFLIGHT_ONLY"
        ),
    }
    release = _seal(unsigned)
    _write_new(output_file, release)
    validate_materialized_release(output_file)
    if len(binary_payload) != binary["bytes"]:
        raise DitherColorAtlasCampaignError("firmware binary changed while sealing")
    return release


def _validate_artifact_reference(value: Any, *, label: str, maximum: int) -> bytes:
    if not isinstance(value, Mapping) or set(value) != {"file", "bytes", "sha256"}:
        raise DitherColorAtlasCampaignError(f"{label} reference differs")
    payload = _read_regular(Path(str(value["file"])), label=label, maximum=maximum)
    if value["bytes"] != len(payload) or value["sha256"] != sha256(payload):
        raise DitherColorAtlasCampaignError(f"{label} bytes differ")
    return payload


def validate_materialized_release(release_file: Path) -> dict[str, Any]:
    payload = _read_regular(release_file, label="dither color-atlas release")
    root = _decode(payload, label="dither color-atlas release")
    canonical = _validate_seal(root, label="dither color-atlas release")
    expected_keys = {
        "schema_version",
        "kind",
        "evidence_mode",
        "compiled_campaign",
        "firmware",
        "offline_atlas_bundle",
        "panel",
        "panel_file",
        "predecessor_binding",
        "execution_eligible",
        "safety",
        "state",
        "integrity",
    }
    if set(root) != expected_keys:
        raise DitherColorAtlasCampaignError("release fields differ")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != RELEASE_KIND
        or root.get("evidence_mode") != REAL_MODE
        or root.get("execution_eligible") is not True
        or root.get("state")
        != "REAL_FACTORY_OTP_DITHER_COLOR_ATLAS_RELEASE_READY_FOR_J2_OFF_PREFLIGHT_ONLY"
    ):
        raise DitherColorAtlasCampaignError("release identity or state differs")

    compiled = root.get("compiled_campaign")
    if not isinstance(compiled, Mapping):
        raise DitherColorAtlasCampaignError("release campaign reference is absent")
    checked_campaign = validate_campaign(Path(str(compiled.get("file"))))
    expected_compiled = {
        key: checked_campaign[key]
        for key in (
            "file",
            "bytes",
            "file_sha256",
            "canonical_sha256",
            "action_count",
            "first_safe_stop_ordinal",
        )
    }
    if dict(compiled) != expected_compiled:
        raise DitherColorAtlasCampaignError("release campaign reference differs")

    firmware = root.get("firmware")
    if not isinstance(firmware, Mapping) or set(firmware) != {
        "binary",
        "elf",
        "binary_elf_link",
    }:
        raise DitherColorAtlasCampaignError("release firmware evidence differs")
    binary = _validate_artifact_reference(
        firmware.get("binary"),
        label="dither color-atlas firmware binary",
        maximum=4_000_000,
    )
    elf = _validate_artifact_reference(
        firmware.get("elf"),
        label="dither color-atlas firmware ELF",
        maximum=32_000_000,
    )
    if firmware.get("binary_elf_link") != _binary_elf_link(binary, elf):
        raise DitherColorAtlasCampaignError("firmware BIN/ELF link differs")
    for label, artifact in (("firmware binary", binary), ("firmware ELF", elf)):
        if any(needle.encode() not in artifact for needle in _identity_needles()):
            raise DitherColorAtlasCampaignError(f"{label} identity scan differs")

    bundle = root.get("offline_atlas_bundle")
    if not isinstance(bundle, Mapping) or bundle.get("bundle") is None:
        raise DitherColorAtlasCampaignError("offline atlas bundle binding is absent")
    if dict(bundle) != _validated_offline_bundle(Path(str(bundle["bundle"]))):
        raise DitherColorAtlasCampaignError("offline atlas bundle binding differs")

    panel_file = root.get("panel_file")
    if not isinstance(panel_file, Mapping) or set(panel_file) != {
        "file",
        "file_sha256",
    }:
        raise DitherColorAtlasCampaignError("panel file reference differs")
    panel_path = Path(str(panel_file["file"]))
    panel_payload = _read_regular(panel_path, label="live panel identity")
    if (
        panel_file["file_sha256"] != sha256(panel_payload)
        or panel_file["file_sha256"] != EXPECTED_MATRIX_PANEL_FILE_SHA256
        or root.get("panel") != _panel(panel_path)
    ):
        raise DitherColorAtlasCampaignError("release panel identity differs")

    anchor = root.get("predecessor_binding")
    if not isinstance(anchor, Mapping):
        raise DitherColorAtlasCampaignError("matrix white predecessor is absent")
    registry = anchor.get("claim_registry")
    if not isinstance(registry, Mapping) or set(registry) != {
        "directory",
        "registry_id",
    }:
        raise DitherColorAtlasCampaignError("matrix claim registry binding differs")
    replayed_anchor = _matrix_white_anchor(
        matrix_release_file=Path(str(anchor.get("matrix_release", {}).get("file"))),
        result_file=Path(str(anchor.get("result", {}).get("file"))),
        observation_file=Path(str(anchor.get("observation", {}).get("file"))),
        claim_registry=Path(str(registry.get("directory"))),
    )
    if dict(anchor) != replayed_anchor or anchor.get("panel") != root.get("panel"):
        raise DitherColorAtlasCampaignError(
            "matrix ordinal3 white predecessor binding differs"
        )

    expected_safety = {
        "profile_source": "factory_otp",
        "spatial_dithering_only": True,
        "runtime_lut_or_waveform_write": False,
        "electrical_parameter_write": False,
        "new_nvs_namespace_and_key": True,
        "global_nvs_clear": False,
        "wifi_credentials_preserved": True,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "one_exact_human_authorization_required_per_action": True,
        "same_boot_and_no_intervening_refresh_required": True,
        "materializer_device_access_performed": False,
        "materializer_network_requests": 0,
        "materializer_visible_refreshes": 0,
        "visible_refresh_authorized_by_release": 0,
    }
    if root.get("safety") != expected_safety:
        raise DitherColorAtlasCampaignError("release safety contract differs")
    return {
        "file": str(Path(release_file).resolve()),
        "bytes": len(payload),
        "file_sha256": sha256(payload),
        "canonical_sha256": canonical,
        "execution_eligible": True,
        "evidence_mode": REAL_MODE,
        "action_count": ACTION_COUNT,
        "firmware_binary_sha256": sha256(binary),
        "firmware_elf_sha256": sha256(elf),
        "predecessor_action_id": FIRST_PREDECESSOR_ACTION_ID,
        "visible_refresh_authorized_by_release": 0,
    }


def required_authorization(action: Mapping[str, Any]) -> str:
    ordinal = action.get("ordinal")
    action_id = action.get("action_id")
    if (
        isinstance(ordinal, bool)
        or not isinstance(ordinal, int)
        or not isinstance(action_id, str)
    ):
        raise DitherColorAtlasCampaignError("action is malformed")
    return (
        f"AUTHORIZE_ONE_VISIBLE_EC5_DITHER_ATLAS_ORDINAL_{ordinal:02d}__"
        f"ACTION_{action_id.upper()}{AUTHORIZATION_SUFFIX}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    compile_cmd = commands.add_parser("compile", allow_abbrev=False)
    compile_cmd.add_argument("--output", type=Path, required=True)
    validate_cmd = commands.add_parser("validate", allow_abbrev=False)
    validate_cmd.add_argument("--campaign", type=Path, required=True)
    materialize = commands.add_parser("materialize-real", allow_abbrev=False)
    materialize.add_argument("--campaign", type=Path, required=True)
    materialize.add_argument("--firmware-binary", type=Path, required=True)
    materialize.add_argument("--firmware-elf", type=Path, required=True)
    materialize.add_argument("--panel", type=Path, required=True)
    materialize.add_argument("--offline-bundle", type=Path, required=True)
    materialize.add_argument("--matrix-release", type=Path, required=True)
    materialize.add_argument("--anchor-result", type=Path, required=True)
    materialize.add_argument("--anchor-observation", type=Path, required=True)
    materialize.add_argument("--anchor-claim-registry", type=Path, required=True)
    materialize.add_argument("--output", type=Path, required=True)
    release = commands.add_parser("validate-release", allow_abbrev=False)
    release.add_argument("--release", type=Path, required=True)
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
        elif args.command == "materialize-real":
            output = materialize_real_release(
                campaign_file=args.campaign,
                firmware_binary=args.firmware_binary,
                firmware_elf=args.firmware_elf,
                panel_file=args.panel,
                offline_bundle_dir=args.offline_bundle,
                matrix_release_file=args.matrix_release,
                anchor_result_file=args.anchor_result,
                anchor_observation_file=args.anchor_observation,
                anchor_claim_registry=args.anchor_claim_registry,
                output_file=args.output,
            )
        elif args.command == "validate-release":
            output = validate_materialized_release(args.release)
        else:
            if not 1 <= args.ordinal <= ACTION_COUNT:
                raise DitherColorAtlasCampaignError("ordinal is outside campaign")
            action = build_actions()[args.ordinal - 1]
            output = {
                "action": action,
                "authorization": required_authorization(action),
                "external_predecessor_required": args.ordinal == 1,
                "visible_refresh_authorized": False,
            }
    except DitherColorAtlasCampaignError as error:
        print(f"dither color-atlas campaign error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
