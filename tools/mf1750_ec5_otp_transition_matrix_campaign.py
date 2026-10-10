#!/usr/bin/env python3
"""Compile and seal the three-action factory-OTP transition-matrix release."""

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

from tools import mf1750_ec5_color_lab_recovery_campaign as recovery_campaign  # noqa: E402
from tools import mf1750_ec5_color_lab_recovery_physical_once as recovery_once  # noqa: E402
from tools import mf1750_ec5_otp_transition_matrix_contract as contract  # noqa: E402


SCHEMA_VERSION = 1
CAMPAIGN_KIND = "mf1750-ec5-otp-transition-matrix-compiled-campaign"
RELEASE_KIND = "mf1750-ec5-otp-transition-matrix-materialized-release"
REAL_MODE = "REAL_CLEAN_WHITE_ANCHOR_GUARD_VALIDATED"
ACTION_COUNT = 3
WHITE_CHECKPOINT_ORDINALS = (3,)
RECOMMENDED_SAFE_STOP_ORDINALS = (3,)
FIRST_FULL_ROUND_STOP_ORDINAL = 3
FIRST_SAFE_STOP_ORDINAL = 3
CAMPAIGN_ROUNDS = 1
FIRST_PREDECESSOR_ACTION_ID = (
    "98881513368c332d8d685b4882c18e478ae160809bb98d9f5028258d7ed0e882"
)
FORMAL_U07_ACTION_ID = recovery_campaign.FORMAL_U07_ACTION_ID
AUTHORIZATION_SUFFIX = "__NO_RETRY_NO_RECOVERY_NO_AUTOCHAIN"
MAX_JSON_BYTES = 16 * 1024 * 1024

ENDPOINTS = {
    "version": "/api/ec5/otp-transition-matrix/version",
    "manifest": "/api/ec5/otp-transition-matrix/manifest",
    "status": "/api/ec5/otp-transition-matrix/status",
    "report": "/api/ec5/otp-transition-matrix/report",
    "arm": "/api/ec5/otp-transition-matrix/arm",
    "execute": "/api/ec5/otp-transition-matrix/execute",
}
ARM_INTENT = "ARM_ONE_FIXED_FACTORY_OTP_TRANSITION_MATRIX_ACTION"
EXECUTE_INTENT = "EXECUTE_ARMED_FACTORY_OTP_TRANSITION_MATRIX_ACTION_ONCE"
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


class OtpTransitionMatrixCampaignError(RuntimeError):
    """An immutable campaign or evidence identity check failed."""


# The audited physical engine catches this historical name.  Keeping the alias
# avoids changing that engine while all new artifacts retain OTP-specific kinds.
ColorLabCampaignError = OtpTransitionMatrixCampaignError


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
        raise OtpTransitionMatrixCampaignError(
            f"value is not canonical JSON: {error}"
        ) from error


def sha256(value: bytes | Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(value) if isinstance(value, Mapping) else value
    return hashlib.sha256(payload).hexdigest()


def fnv1a(payload: bytes) -> str:
    value = 0x811C9DC5
    for byte in payload:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return f"0x{value:08x}"


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise OtpTransitionMatrixCampaignError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_regular(path: Path, *, label: str, maximum: int = MAX_JSON_BYTES) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise OtpTransitionMatrixCampaignError(
                f"{label} must be a regular non-symlink file"
            )
        if before.st_size <= 0 or before.st_size > maximum:
            raise OtpTransitionMatrixCampaignError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise OtpTransitionMatrixCampaignError(
            f"could not read {label}: {error}"
        ) from error
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise OtpTransitionMatrixCampaignError(f"{label} changed while read")
    if len(payload) != after.st_size:
        raise OtpTransitionMatrixCampaignError(f"{label} read length differs")
    return payload


def _decode(payload: bytes, *, label: str) -> Mapping[str, Any]:
    try:
        root = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                OtpTransitionMatrixCampaignError(
                    f"{label} contains forbidden {token}"
                )
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OtpTransitionMatrixCampaignError(
            f"{label} is invalid JSON: {error}"
        ) from error
    if not isinstance(root, Mapping):
        raise OtpTransitionMatrixCampaignError(f"{label} root must be an object")
    return root


def _write_new(path: Path, value: Mapping[str, Any]) -> bytes:
    path = Path(path)
    payload = canonical_json_bytes(value)
    try:
        parent_meta = path.parent.lstat()
        parent = path.parent.resolve(strict=True)
        if stat.S_ISLNK(parent_meta.st_mode) or not stat.S_ISDIR(parent_meta.st_mode):
            raise OtpTransitionMatrixCampaignError(
                "output parent must be a non-symlink directory"
            )
        with (parent / path.name).open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise OtpTransitionMatrixCampaignError(
            f"refusing to overwrite {path}"
        ) from error
    except OSError as error:
        raise OtpTransitionMatrixCampaignError(
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
        raise OtpTransitionMatrixCampaignError(f"{label} integrity fields differ")
    unsigned = dict(root)
    unsigned.pop("integrity")
    expected = {
        "canonical_sha256": sha256(unsigned),
        "scope": "entire object excluding integrity; canonical UTF-8 JSON",
    }
    if dict(integrity) != expected:
        raise OtpTransitionMatrixCampaignError(f"{label} integrity differs")
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
        "spatial_dithering": False,
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
        "build_tag": contract.BUILD_TAG,
        "test_id": contract.TEST_ID,
        "device_api_version": contract.DEVICE_API_VERSION,
        "campaign_id": contract.CAMPAIGN_ID,
        "firmware_contract_id": manifest["contract_id"],
        "firmware_contract": manifest,
        "device_schema_version": contract.TOP_SCHEMA_VERSION,
        "driver_evidence_schema_version": contract.DRIVER_EVIDENCE_SCHEMA_VERSION,
        "first_predecessor_action_id": FIRST_PREDECESSOR_ACTION_ID,
        "action_count": ACTION_COUNT,
        "campaign_rounds": CAMPAIGN_ROUNDS,
        "first_safe_stop_ordinal": FIRST_SAFE_STOP_ORDINAL,
        "white_checkpoint_ordinals": list(WHITE_CHECKPOINT_ORDINALS),
        "recommended_safe_stop_ordinals": list(RECOMMENDED_SAFE_STOP_ORDINALS),
        "first_complete_round_stop_ordinal": FIRST_FULL_ROUND_STOP_ORDINAL,
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
        "classification": {
            "profile_source": "factory_otp",
            "runtime_lut_or_waveform_changed": False,
            "transition_history_experiment": True,
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
    payload = _read_regular(manifest_file, label="OTP transition-matrix campaign")
    root = _decode(payload, label="OTP transition-matrix campaign")
    canonical = _validate_seal(root, label="OTP transition-matrix campaign")
    if dict(root) != build_campaign():
        raise OtpTransitionMatrixCampaignError(
            "compiled OTP transition-matrix campaign differs"
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


def _artifact(path: Path, *, label: str, maximum: int) -> tuple[dict[str, Any], bytes]:
    payload = _read_regular(path, label=label, maximum=maximum)
    needles = (
        contract.BUILD_TAG,
        contract.TEST_ID,
        contract.CAMPAIGN_ID,
        contract.DEVICE_API_VERSION,
        contract.campaign_manifest()["contract_id"],
        contract.NVS_NAMESPACE,
        contract.NVS_KEY,
        *ENDPOINTS.values(),
    )
    for descriptor in contract.DESCRIPTORS:
        needles += (
            str(descriptor["descriptor_id"]),
            str(descriptor["hardware_action_id"]),
        )
    missing = [needle for needle in needles if needle.encode() not in payload]
    if missing:
        raise OtpTransitionMatrixCampaignError(
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
        or not binary.startswith(b"\xE9")
        or not elf.startswith(b"\x7fELF")
        or binary[
            app_descriptor_offset : app_descriptor_offset
            + len(app_descriptor_magic)
        ]
        != app_descriptor_magic
        or binary[
            embedded_elf_sha256_offset : embedded_elf_sha256_offset + 32
        ]
        != selected_elf_sha256
    ):
        raise OtpTransitionMatrixCampaignError(
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
        raise OtpTransitionMatrixCampaignError("live panel identity differs")
    return {key: str(root[key]) for key in sorted(expected)}


def _formal_u07_absence(registry: Path) -> dict[str, Any]:
    try:
        return recovery_campaign._formal_u07_absence(registry)  # noqa: SLF001
    except recovery_campaign.ColorLabCampaignError as error:
        raise OtpTransitionMatrixCampaignError(str(error)) from error


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


def _clean_white_anchor(
    *,
    recovery_release_file: Path,
    result_file: Path,
    observation_file: Path,
    claim_registry: Path,
) -> dict[str, Any]:
    try:
        context = recovery_once.load_release(recovery_release_file)
        result = recovery_once.validate_result(
            context, result_file, claim_registry=claim_registry
        )
        observation = recovery_once.validate_observation(
            context,
            observation_file,
            result_file=result_file,
            claim_registry=claim_registry,
        )
    except recovery_once.ColorLabRecoveryPhysicalError as error:
        raise OtpTransitionMatrixCampaignError(
            f"clean-white predecessor replay failed: {error}"
        ) from error
    if (
        result.get("ordinal") != 11
        or result.get("outcome") != "complete_pass"
        or result.get("action", {}).get("role") != "WHITE"
        or observation.get("ordinal") != 11
        or observation.get("visual", {}).get("full_clean_white") is not True
        or observation.get("sequence_gate_pass") is not True
    ):
        raise OtpTransitionMatrixCampaignError(
            "predecessor is not the exact finalized ordinal11 clean-white anchor"
        )
    claim_file = Path(str(result["claim"]["file"]))
    expected_claim = Path(claim_registry).resolve(strict=True) / (
        f"{FIRST_PREDECESSOR_ACTION_ID}.json"
    )
    if claim_file.resolve(strict=True) != expected_claim:
        raise OtpTransitionMatrixCampaignError("clean-white anchor claim path differs")
    claim = _reference(claim_file, label="ordinal11 permanent claim")
    if (
        result["claim"].get("file_sha256") != claim["file_sha256"]
        or result["claim"].get("integrity_sha256") != claim["integrity_sha256"]
        or result["action"].get("action_id") != FIRST_PREDECESSOR_ACTION_ID
    ):
        raise OtpTransitionMatrixCampaignError("clean-white anchor claim differs")
    return {
        "action_id": FIRST_PREDECESSOR_ACTION_ID,
        "release": _reference(
            recovery_release_file, label="ordinal11 recovery release"
        ),
        "result": _reference(result_file, label="ordinal11 clean-white result"),
        "observation": _reference(
            observation_file, label="ordinal11 clean-white observation"
        ),
        "claim": claim,
        "latest_visible_state": "clean_full_white_factory_otp",
        "clean_white_confirmed": True,
        "manual_no_intervening_refresh_confirmation_required": True,
    }


def materialize_real_release(
    *,
    campaign_file: Path,
    firmware_binary: Path,
    firmware_elf: Path,
    panel_file: Path,
    recovery_release_file: Path,
    anchor_result_file: Path,
    anchor_observation_file: Path,
    anchor_claim_registry: Path,
    formal_u07_claim_registry: Path,
    output_file: Path,
) -> dict[str, Any]:
    checked_campaign = validate_campaign(campaign_file)
    binary, binary_payload = _artifact(
        firmware_binary, label="OTP transition-matrix firmware binary", maximum=4_000_000
    )
    elf, _elf_payload = _artifact(
        firmware_elf, label="OTP transition-matrix firmware ELF", maximum=32_000_000
    )
    binary_elf_link = _binary_elf_link(binary_payload, _elf_payload)
    anchor = _clean_white_anchor(
        recovery_release_file=recovery_release_file,
        result_file=anchor_result_file,
        observation_file=anchor_observation_file,
        claim_registry=anchor_claim_registry,
    )
    formal = _formal_u07_absence(formal_u07_claim_registry)
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
        "panel": _panel(panel_file),
        "panel_file": {
            "file": str(Path(panel_file).resolve()),
            "file_sha256": sha256(_read_regular(panel_file, label="live panel identity")),
        },
        "predecessor_binding": anchor,
        "formal_u07_claim_absence": formal,
        "execution_eligible": True,
        "safety": {
            "profile_source": "factory_otp",
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
        "state": "REAL_FACTORY_OTP_MATRIX_RELEASE_READY_FOR_J2_OFF_PREFLIGHT_ONLY",
    }
    release = _seal(unsigned)
    _write_new(output_file, release)
    # Re-read every byte so a successful return always means the on-disk release
    # passed the same validator used by the physical runner.
    validate_materialized_release(output_file)
    if len(binary_payload) != binary["bytes"]:
        raise OtpTransitionMatrixCampaignError("firmware binary changed while sealing")
    return release


def _validate_artifact_reference(value: Any, *, label: str, maximum: int) -> bytes:
    if not isinstance(value, Mapping) or set(value) != {"file", "bytes", "sha256"}:
        raise OtpTransitionMatrixCampaignError(f"{label} reference differs")
    payload = _read_regular(Path(str(value["file"])), label=label, maximum=maximum)
    if value["bytes"] != len(payload) or value["sha256"] != sha256(payload):
        raise OtpTransitionMatrixCampaignError(f"{label} bytes differ")
    return payload


def validate_materialized_release(release_file: Path) -> dict[str, Any]:
    payload = _read_regular(release_file, label="OTP transition-matrix release")
    root = _decode(payload, label="OTP transition-matrix release")
    canonical = _validate_seal(root, label="OTP transition-matrix release")
    if (
        root.get("schema_version") != SCHEMA_VERSION
        or root.get("kind") != RELEASE_KIND
        or root.get("evidence_mode") != REAL_MODE
        or root.get("execution_eligible") is not True
        or root.get("state")
        != "REAL_FACTORY_OTP_MATRIX_RELEASE_READY_FOR_J2_OFF_PREFLIGHT_ONLY"
    ):
        raise OtpTransitionMatrixCampaignError("release identity or state differs")
    compiled = root.get("compiled_campaign")
    if not isinstance(compiled, Mapping):
        raise OtpTransitionMatrixCampaignError("release campaign reference is absent")
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
        raise OtpTransitionMatrixCampaignError("release campaign reference differs")
    firmware = root.get("firmware")
    if not isinstance(firmware, Mapping):
        raise OtpTransitionMatrixCampaignError("release firmware evidence is absent")
    binary = _validate_artifact_reference(
        firmware.get("binary"), label="OTP firmware binary", maximum=4_000_000
    )
    elf = _validate_artifact_reference(
        firmware.get("elf"), label="OTP firmware ELF", maximum=32_000_000
    )
    if firmware.get("binary_elf_link") != _binary_elf_link(binary, elf):
        raise OtpTransitionMatrixCampaignError("firmware BIN/ELF link differs")
    # Re-scan both immutable artifacts on every validation, not just at sealing.
    for label, artifact in (("firmware binary", binary), ("firmware ELF", elf)):
        required = (
            contract.BUILD_TAG,
            contract.TEST_ID,
            contract.CAMPAIGN_ID,
            contract.DEVICE_API_VERSION,
            contract.campaign_manifest()["contract_id"],
            contract.NVS_NAMESPACE,
            contract.NVS_KEY,
            *ENDPOINTS.values(),
        )
        required += tuple(
            text
            for descriptor in contract.DESCRIPTORS
            for text in (
                str(descriptor["descriptor_id"]),
                str(descriptor["hardware_action_id"]),
            )
        )
        if any(text.encode() not in artifact for text in required):
            raise OtpTransitionMatrixCampaignError(f"{label} identity scan differs")
    panel_file = root.get("panel_file")
    if not isinstance(panel_file, Mapping) or set(panel_file) != {"file", "file_sha256"}:
        raise OtpTransitionMatrixCampaignError("panel file reference differs")
    panel_path = Path(str(panel_file["file"]))
    panel_payload = _read_regular(panel_path, label="live panel identity")
    if panel_file["file_sha256"] != sha256(panel_payload):
        raise OtpTransitionMatrixCampaignError("live panel file hash differs")
    if root.get("panel") != _panel(panel_path):
        raise OtpTransitionMatrixCampaignError("release panel identity differs")
    anchor = root.get("predecessor_binding")
    if not isinstance(anchor, Mapping):
        raise OtpTransitionMatrixCampaignError("clean-white predecessor is absent")
    replayed_anchor = _clean_white_anchor(
        recovery_release_file=Path(str(anchor.get("release", {}).get("file"))),
        result_file=Path(str(anchor.get("result", {}).get("file"))),
        observation_file=Path(str(anchor.get("observation", {}).get("file"))),
        claim_registry=Path(str(anchor.get("claim", {}).get("file"))).parent,
    )
    if dict(anchor) != replayed_anchor:
        raise OtpTransitionMatrixCampaignError("clean-white predecessor binding differs")
    formal = root.get("formal_u07_claim_absence")
    if not isinstance(formal, Mapping) or dict(formal) != _formal_u07_absence(
        Path(str(formal.get("registry")))
    ):
        raise OtpTransitionMatrixCampaignError("formal U07 absence snapshot differs")
    expected_safety = {
        "profile_source": "factory_otp",
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
        raise OtpTransitionMatrixCampaignError("release safety contract differs")
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
        "visible_refresh_authorized_by_release": 0,
    }


def required_authorization(action: Mapping[str, Any]) -> str:
    ordinal = action.get("ordinal")
    action_id = action.get("action_id")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or not isinstance(
        action_id, str
    ):
        raise OtpTransitionMatrixCampaignError("action is malformed")
    return (
        f"AUTHORIZE_ONE_VISIBLE_EC5_OTP_MATRIX_ORDINAL_{ordinal:02d}__"
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
    materialize.add_argument("--recovery-release", type=Path, required=True)
    materialize.add_argument("--anchor-result", type=Path, required=True)
    materialize.add_argument("--anchor-observation", type=Path, required=True)
    materialize.add_argument("--anchor-claim-registry", type=Path, required=True)
    materialize.add_argument("--formal-u07-claim-registry", type=Path, required=True)
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
                recovery_release_file=args.recovery_release,
                anchor_result_file=args.anchor_result,
                anchor_observation_file=args.anchor_observation,
                anchor_claim_registry=args.anchor_claim_registry,
                formal_u07_claim_registry=args.formal_u07_claim_registry,
                output_file=args.output,
            )
        elif args.command == "validate-release":
            output = validate_materialized_release(args.release)
        else:
            if not 1 <= args.ordinal <= ACTION_COUNT:
                raise OtpTransitionMatrixCampaignError("ordinal is outside campaign")
            action = build_actions()[args.ordinal - 1]
            output = {
                "action": action,
                "authorization": required_authorization(action),
                "visible_refresh_authorized": False,
            }
    except OtpTransitionMatrixCampaignError as error:
        print(f"OTP transition-matrix campaign error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
