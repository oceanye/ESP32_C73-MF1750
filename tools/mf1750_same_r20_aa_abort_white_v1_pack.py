#!/usr/bin/env python3
"""Offline identity pack for the terminal Same-R20 AA-abort OTP-white action.

This successor is deliberately independent from the four-action Same-R20
campaign. It binds that campaign's completed ordinal 1 and the four camera
frames which all retained a camera-relative controller-mismatch candidate.
It never consumes ordinal 2 and never authorizes a source-campaign resume.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_same_r20_parity_v1_pack as source_pack  # noqa: E402


BUILD_TAG = "MF1750_EC5_SAME_R20_AA_ABORT_WHITE_V1_SINGLE_APP_BOOT_2026-08-28"
TEST_ID = "EC5-SAME-R20-AA-ABORT-WHITE-V1"
CAMPAIGN_ID = "EC5_SAME_R20_AA_ABORT_WHITE_V1"
ENVIRONMENT = "ec5_same_r20_aa_abort_white_v1"
PROFILE_ID = "WF23_25"
NVS_NAMESPACE = "sr20aaw_v1"
NVS_KEY = "used_aaw1"
BASE_ROUTE = "/api/ec5/same-r20-aa-abort-white-v1"
DEVICE_API_VERSION = "MF1750_EC5_SAME_R20_AA_ABORT_WHITE_DEVICE_V1"
IDENTITY_REVISION = "same-r20-aa-abort-white-v1"
CLASSIFICATION = (
    "FACTORY_OTP_WHITE_SAME_R20_AA_ABORT_TERMINAL_ONE_ACTION_NO_RUNTIME_PAYLOAD"
)

SOURCE_CAMPAIGN_ID = "EC5_SAME_R20_PARITY_2X4_V1"
SOURCE_CONTRACT_ID = "718d6cf628cd14a869b73f77f6414fcdd8a5b364863849899403afde2f3463f8"
SOURCE_FIRMWARE_BIN_SHA256 = (
    "d65fb20b3e3843563561340d6bb450fc469ade4e503fec87eec3f0369e30977f"
)
SOURCE_FIRMWARE_ELF_SHA256 = (
    "bf15d35d12af897d89afd2ab65141a50dd3dc4e2350877abc3ada530f8de94b6"
)
SOURCE_ACTION_ID = "7dd101c61553c9a10b97beeb7c3c8ce26e79c410d3b2ac3040db572065fd49f4"
SOURCE_ACTION_ROLE = "SAME_R20_ACTIVE_ACTIVE_ATLAS"
SOURCE_ROOT = REPO_ROOT / ".test-output/hardware/MF1750_SAME_R20_PARITY_20260828_V1"
SOURCE_ACTION_FILE = SOURCE_ROOT / "action-01-active-active-atlas.json"
SOURCE_ACTION_FILE_BYTES = 47_350
SOURCE_ACTION_FILE_SHA256 = (
    "80a6e7172967e15a87756a2d9c3478a821b357ed2d8d39845e9d5bf15dfef751"
)
SOURCE_ACTION_INTEGRITY_SHA256 = (
    "a77a2e501be089053ff5299047077430fd0abc360f01f55b673ac19a5f969d5d"
)
SOURCE_REPEAT_REPORT_FILE = SOURCE_ROOT / "aa-four-frame-retained-repeat-report.json"
SOURCE_REPEAT_REPORT_FILE_BYTES = 17_459
SOURCE_REPEAT_REPORT_FILE_SHA256 = (
    "172f3570e33701c9cf10a8d9f3c4fbb4c146e8fa8ee26d6f5a3e2f369809b67d"
)
SOURCE_REPEAT_REPORT_INTEGRITY_SHA256 = (
    "665f204c878303a3a0d5fc8de85545dc679a776a8e2eee420747ca887ed7ac02"
)
SOURCE_REPEAT_REPORT_ID = (
    "60b1c65ec69a28ab44b6c32547db2975199e2a74237463e86018abae494e91c1"
)
SOURCE_RELAY_OFF_RECEIPT_FILE = SOURCE_ROOT / "relay-channel1-off-post-aa-repeats.json"
SOURCE_RELAY_OFF_RECEIPT_BYTES = 1_251
SOURCE_RELAY_OFF_RECEIPT_SHA256 = (
    "c523566cf21a518108e27f47ceb7a030d3e19205a0abab0fa283f36461568c35"
)

CAMERA_MISMATCH_STATE = "CAMERA_RELATIVE_CONTROLLER_MISMATCH_CANDIDATE"
CAMERA_FILE_BINDINGS: tuple[dict[str, Any], ...] = (
    {
        "label": "synchronous_live",
        "power_state": "J2_ON_ACTION_SYNCHRONIZED_CAPTURE",
        "photo": "camera-action-01-aa.jpg",
        "photo_bytes": 726_757,
        "photo_sha256": "46e4c6e3855857be2b795b64e064ecfba11f973a9a93017478a29e574be55863",
        "analysis": "camera-action-01-aa.atlas-analysis.json",
        "analysis_bytes": 13_455,
        "analysis_sha256": "2ca5c78f466942aa64f829971bb68f6b90d4e89197f78160a651c5dcac4bf0fe",
        "analysis_integrity_sha256": "84871f169e9a2705d9002b8e0f5e79665b132e6152284b826e86142d76a03dae",
    },
    {
        "label": "retained_poweroff_repeat_01",
        "power_state": "J2_OFF_RETAINED_NO_REFRESH",
        "photo": "camera-action-01-aa-poweroff-repeat-01.jpg",
        "photo_bytes": 665_445,
        "photo_sha256": "16ff03396c9c59b91c6b5f4273bc2eb0bfd4aaa8b097647dd9d25052e6db43ac",
        "analysis": "camera-action-01-aa-poweroff-repeat-01.atlas-analysis.json",
        "analysis_bytes": 13_466,
        "analysis_sha256": "c4258b2321dc8b9d591df22797ad90dfbca311a23e2802c03cbefad5df85a921",
        "analysis_integrity_sha256": "ece72896769b26ec945e84a6134bc3c319b4f9e20b371c712bd1340c0fa56dac",
    },
    {
        "label": "retained_poweroff_repeat_02",
        "power_state": "J2_OFF_RETAINED_NO_REFRESH",
        "photo": "camera-action-01-aa-poweroff-repeat-02.jpg",
        "photo_bytes": 655_345,
        "photo_sha256": "0067d14acb81f16cf750fd832d02cbec7e7e890aa014327cc34c65764dfdd8de",
        "analysis": "camera-action-01-aa-poweroff-repeat-02.atlas-analysis.json",
        "analysis_bytes": 13_491,
        "analysis_sha256": "2e4c0d81d74c61a58b14469c88ff03354c9e5f9376787f85b687c0959f2d79dd",
        "analysis_integrity_sha256": "87b5d094d50810ddc03e01b00a10cfb7f765b5b0543294d8a08642fdc2189c9e",
    },
    {
        "label": "retained_poweroff_repeat_03",
        "power_state": "J2_OFF_RETAINED_NO_REFRESH",
        "photo": "camera-action-01-aa-poweroff-repeat-03.jpg",
        "photo_bytes": 653_264,
        "photo_sha256": "928112fbb4b7afb6524b7b845f06a982e58f07a7138b06e7b612a85b72fc79bb",
        "analysis": "camera-action-01-aa-poweroff-repeat-03.atlas-analysis.json",
        "analysis_bytes": 13_490,
        "analysis_sha256": "1adb82d392fcee58b012483526ec9f254bc8cbf09863fdd0bbaad29a313c3fe3",
        "analysis_integrity_sha256": "6e2a771e864f6870633d951138f904b925a063c44f5ffcb623dc4186e98c4228",
    },
)

FRAME_SHA256 = "91f1ed45bf609a23fbdcfd037027c2e271484f58321a4707e889d11859d8453d"
DTM_SHA256 = "8b8fe04d4d48ab9d1abb4a858f68544164d1a091998664eef06869c098a78158"
FRAME_FNV1A = 0x13340DC5
DTM_FNV1A = 0xB7A855C5

# Filled after the canonical payloads are finalized.
DESCRIPTOR_ID = "65e534e7632bab1320b2d40f531bb00c55bdfaaf56441e52b1920837ba12d66c"
ACTION_ID = "902629decf24660f7cbb7495336f8f15b250097398aa4965d1c3b1d4ec79b268"
CONTRACT_ID = "08e2683209d66e5f4a4149733e0b446abc81be29b2ed6cec1637ddafd66f0399"

CLAIM_KIND = "mf1750-same-r20-aa-abort-white-v1-claim"
RESULT_KIND = "mf1750-same-r20-aa-abort-white-v1-result"
DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
    "ROLE=SAME_R20_AA_ABORT_OTP_WHITE|SHA256=" + DESCRIPTOR_ID
)
ARM_INTENT = (
    "ARM_ONE_FIXED_SAME_R20_AA_ABORT_FACTORY_OTP_WHITE_NOT_HARDWARE_AUTHORIZATION"
)
EXECUTE_INTENT = "EXECUTE_ONE_FIXED_SAME_R20_AA_ABORT_FACTORY_OTP_WHITE_ONCE"

FIRMWARE_BIN = REPO_ROOT / Path(
    ".pio/build-sr20-aa-abort-white-v1/ec5_sr20_aa_abort_white_v1/firmware.bin"
)
FIRMWARE_ELF = REPO_ROOT / Path(
    ".pio/build-sr20-aa-abort-white-v1/ec5_sr20_aa_abort_white_v1/firmware.elf"
)
FIRMWARE_BIN_BYTES = 788_048
FIRMWARE_BIN_SHA256 = "1d7e83fcbc978392d4935120297797ea83529373cb98d865e2a257667e3be1dd"
FIRMWARE_ELF_BYTES = 13_215_292
FIRMWARE_ELF_SHA256 = "e3fc134167afd571a0ce1e6a83afb224d0f6e7c888b14873c4bc0f6f7ac2b87f"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


SOURCE_TERMINATION_BINDING = {
    "source_campaign_id": SOURCE_CAMPAIGN_ID,
    "source_contract_id": SOURCE_CONTRACT_ID,
    "source_firmware_bin_sha256": SOURCE_FIRMWARE_BIN_SHA256,
    "source_firmware_elf_sha256": SOURCE_FIRMWARE_ELF_SHA256,
    "source_completed_ordinal": 1,
    "source_completed_action_id": SOURCE_ACTION_ID,
    "source_completed_action_role": SOURCE_ACTION_ROLE,
    "source_action_outcome": "complete_pass",
    "source_next_ordinal_observed": 2,
    "source_ordinal2_consumption_forbidden": True,
    "source_resume_forbidden": True,
    "source_campaign_terminal_by_successor": True,
    "source_reflash_required_before_containment": True,
    "source_boot_resume_forbidden": True,
    "camera_frame_count": 4,
    "camera_bound_file_count": 8,
    "camera_mismatch_state": CAMERA_MISMATCH_STATE,
    "camera_controller_equivalence_proven": False,
    "camera_qualified_new_colour": False,
    "source_repeat_report_sha256": SOURCE_REPEAT_REPORT_FILE_SHA256,
    "source_repeat_report_id": SOURCE_REPEAT_REPORT_ID,
    "source_relay_off_receipt_sha256": SOURCE_RELAY_OFF_RECEIPT_SHA256,
    "relay_off_receipt_is_command_query_not_load_voltage_proof": True,
}


def _descriptor_payload() -> dict[str, Any]:
    return {
        "schema": "mf1750-same-r20-aa-abort-white-v1-action-descriptor",
        "profile_id": PROFILE_ID,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "classification": CLASSIFICATION,
        **SOURCE_TERMINATION_BINDING,
        "source_action_file_sha256": SOURCE_ACTION_FILE_SHA256,
        "camera_file_bindings": [dict(item) for item in CAMERA_FILE_BINDINGS],
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def _action() -> dict[str, Any]:
    return {
        "ordinal": 1,
        "role": "FACTORY_OTP_WHITE_CONTAINMENT",
        "descriptor_id": DESCRIPTOR_ID,
        "action_id": ACTION_ID,
        "frame_sha256": FRAME_SHA256,
        "cs1_dtm_sha256": DTM_SHA256,
        "cs2_dtm_sha256": DTM_SHA256,
    }


def _contract_payload(action: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "mf1750-same-r20-aa-abort-white-v1-contract",
        "build_tag": BUILD_TAG,
        "test_id": TEST_ID,
        "campaign_id": CAMPAIGN_ID,
        **SOURCE_TERMINATION_BINDING,
        "source_action_file_sha256": SOURCE_ACTION_FILE_SHA256,
        "camera_file_bindings": [dict(item) for item in CAMERA_FILE_BINDINGS],
        "environment": ENVIRONMENT,
        "profile_id": PROFILE_ID,
        "classification": CLASSIFICATION,
        "nvs_namespace": NVS_NAMESPACE,
        "nvs_key": NVS_KEY,
        "base_route": BASE_ROUTE,
        "actions": [dict(action)],
        "busy_qualification": {
            "raw_idle_level": 1,
            "host_preflight_required": True,
            "firmware_arm_required": True,
            "firmware_execute_required": True,
            "firmware_dispatch_required": True,
            "busy_zero_accepted": False,
        },
        "fresh_identity": True,
        "independent_nvs_and_claims": True,
        "source_campaign_nvs_dependency": False,
        "factory_otp_white_only": True,
        "runtime_payload": False,
        "startup_refresh": False,
        "retry": False,
        "automatic_recovery": False,
        "autochain": False,
        "ordinal_skip": False,
    }


def _verify_exact_file(path: Path, *, byte_count: int, sha256: str, label: str) -> None:
    if (
        not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != byte_count
        or _sha256(path) != sha256
    ):
        raise ValueError(f"{label} file binding differs")


def _validate_source_evidence() -> dict[str, Any]:
    if source_pack.build_report()["contract_id"] != SOURCE_CONTRACT_ID:
        raise ValueError("source Same-R20 contract binding differs")
    source_artifacts = (
        source_pack.REPO_ROOT / ".pio/build-runtime-lut-same-r20-parity-v1/"
        "ec5_runtime_lut_same_r20_parity_v1"
    )
    _verify_exact_file(
        source_artifacts / "firmware.bin",
        byte_count=801_712,
        sha256=SOURCE_FIRMWARE_BIN_SHA256,
        label="source firmware BIN",
    )
    _verify_exact_file(
        source_artifacts / "firmware.elf",
        byte_count=13_299_408,
        sha256=SOURCE_FIRMWARE_ELF_SHA256,
        label="source firmware ELF",
    )
    _verify_exact_file(
        SOURCE_ACTION_FILE,
        byte_count=SOURCE_ACTION_FILE_BYTES,
        sha256=SOURCE_ACTION_FILE_SHA256,
        label="source action 1",
    )
    _verify_exact_file(
        SOURCE_REPEAT_REPORT_FILE,
        byte_count=SOURCE_REPEAT_REPORT_FILE_BYTES,
        sha256=SOURCE_REPEAT_REPORT_FILE_SHA256,
        label="source four-frame repeat report",
    )
    _verify_exact_file(
        SOURCE_RELAY_OFF_RECEIPT_FILE,
        byte_count=SOURCE_RELAY_OFF_RECEIPT_BYTES,
        sha256=SOURCE_RELAY_OFF_RECEIPT_SHA256,
        label="source relay OFF query receipt",
    )
    action = _read_sealed_json(SOURCE_ACTION_FILE, label="source action 1")
    terminal = action.get("terminal_report")
    source_action = action.get("action")
    if (
        action.get("integrity", {}).get("sha256") != SOURCE_ACTION_INTEGRITY_SHA256
        or action.get("kind") != "mf1750-ec5-same-r20-parity-v1-result"
        or action.get("outcome") != "complete_pass"
        or action.get("firmware_sha256") != SOURCE_FIRMWARE_BIN_SHA256
        or action.get("visible_refreshes") != 1
        or action.get("no_retry") is not True
        or action.get("no_recovery") is not True
        or action.get("no_autochain") is not True
        or not isinstance(source_action, Mapping)
        or source_action.get("ordinal") != 1
        or source_action.get("action_id") != SOURCE_ACTION_ID
        or source_action.get("role") != SOURCE_ACTION_ROLE
        or not isinstance(terminal, Mapping)
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("contract_id") != SOURCE_CONTRACT_ID
        or terminal.get("next_ordinal") != 2
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
    ):
        raise ValueError("source action 1 complete-pass semantics differ")

    repeat = _read_sealed_json(
        SOURCE_REPEAT_REPORT_FILE, label="source four-frame repeat report"
    )
    repeat_classification = repeat.get("classification")
    repeat_summary = repeat.get("summary")
    campaign_control = repeat.get("campaign_control")
    if (
        repeat.get("integrity", {}).get("sha256")
        != SOURCE_REPEAT_REPORT_INTEGRITY_SHA256
        or repeat.get("kind")
        != "mf1750-same-r20-aa-four-frame-retained-repeat-report-v1"
        or repeat.get("report_id") != SOURCE_REPEAT_REPORT_ID
        or repeat.get("campaign_id") != SOURCE_CAMPAIGN_ID
        or repeat.get("contract_id") != SOURCE_CONTRACT_ID
        or repeat.get("firmware_sha256") != SOURCE_FIRMWARE_BIN_SHA256
        or not isinstance(repeat_classification, Mapping)
        or repeat_classification.get("state")
        != "CAMERA_RELATIVE_REPEAT_MISMATCH_CANDIDATE"
        or repeat_classification.get("controller_equivalence_proven") is not False
        or repeat_classification.get("qualified_new_colour") is not False
        or not isinstance(repeat_summary, Mapping)
        or repeat_summary.get("unanimous_threshold_exceedance_codes") != [1, 2]
        or not isinstance(campaign_control, Mapping)
        or campaign_control.get("next_same_campaign_ordinal_allowed") is not False
        or campaign_control.get("campaign_disposition")
        != "STOPPED_AT_ORDINAL_1_CAMERA_MISMATCH_CANDIDATE"
        or campaign_control.get("planned_ordinal_2_role")
        != "FACTORY_OTP_WHITE_AFTER_ACTIVE_ACTIVE"
        or campaign_control.get("planned_ordinal_2_must_not_be_used_as_recovery")
        is not True
    ):
        raise ValueError("source four-frame repeat report semantics differ")
    try:
        relay = json.loads(SOURCE_RELAY_OFF_RECEIPT_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("source relay OFF query receipt is malformed") from exc
    if (
        not isinstance(relay, Mapping)
        or relay.get("kind") != "mf17506-zave-relay-exact-bound-query-receipt"
        or relay.get("channel") != 1
        or relay.get("commanded_state") != "OFF"
        or relay.get("off_gate_passed") is not True
        or relay.get("on_authorized") is not False
        or relay.get("contact_switch_performed") is not False
        or relay.get("automatic_retry_performed") is not False
        or relay.get("electrical_state_proven") is not False
    ):
        raise ValueError("source relay OFF query receipt semantics differ")

    camera_results: list[dict[str, Any]] = []
    for item in CAMERA_FILE_BINDINGS:
        photo = SOURCE_ROOT / item["photo"]
        analysis_path = SOURCE_ROOT / item["analysis"]
        _verify_exact_file(
            photo,
            byte_count=item["photo_bytes"],
            sha256=item["photo_sha256"],
            label=f"{item['label']} photo",
        )
        _verify_exact_file(
            analysis_path,
            byte_count=item["analysis_bytes"],
            sha256=item["analysis_sha256"],
            label=f"{item['label']} analysis",
        )
        analysis = _read_sealed_json(analysis_path, label=f"{item['label']} analysis")
        classification = analysis.get("classification")
        geometry = analysis.get("geometry_guard")
        summary = analysis.get("paired_summary")
        source_photo = analysis.get("source_photo")
        if (
            analysis.get("integrity", {}).get("sha256")
            != item["analysis_integrity_sha256"]
            or analysis.get("kind")
            != "mf1750-same-r20-dual-controller-2x4-camera-relative-atlas-analysis"
            or analysis.get("role") != "AA"
            or not isinstance(source_photo, Mapping)
            or source_photo.get("sha256") != item["photo_sha256"]
            or source_photo.get("bytes") != item["photo_bytes"]
            or not isinstance(geometry, Mapping)
            or geometry.get("reference_homography_alignment_guard_pass") is not True
            or not isinstance(classification, Mapping)
            or classification.get("state") != CAMERA_MISMATCH_STATE
            or classification.get("controller_equivalence_proven") is not False
            or classification.get("qualified_new_colour") is not False
            or not isinstance(summary, Mapping)
            or summary.get("all_pairs_within_exploratory_threshold") is not False
        ):
            raise ValueError(f"{item['label']} mismatch classification differs")
        camera_results.append(
            {
                "label": item["label"],
                "power_state": item["power_state"],
                "photo_sha256": item["photo_sha256"],
                "analysis_sha256": item["analysis_sha256"],
                "classification": CAMERA_MISMATCH_STATE,
                "controller_equivalence_proven": False,
                "qualified_new_colour": False,
            }
        )
    return {
        "verified": True,
        "source_action_file_sha256": SOURCE_ACTION_FILE_SHA256,
        "source_action_outcome": "complete_pass",
        "source_repeat_report_file_sha256": SOURCE_REPEAT_REPORT_FILE_SHA256,
        "source_repeat_report_id": SOURCE_REPEAT_REPORT_ID,
        "source_relay_off_receipt_file_sha256": SOURCE_RELAY_OFF_RECEIPT_SHA256,
        "relay_off_receipt_electrical_state_proven": False,
        "source_next_ordinal_observed": 2,
        "source_ordinal2_consumption_forbidden": True,
        "source_resume_forbidden": True,
        "camera_frames": camera_results,
        "camera_mismatch_reproduced_in_all_four_frames": True,
    }


def artifact_binding_status() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, path, byte_count, wanted in (
        ("firmware_bin", FIRMWARE_BIN, FIRMWARE_BIN_BYTES, FIRMWARE_BIN_SHA256),
        ("firmware_elf", FIRMWARE_ELF, FIRMWARE_ELF_BYTES, FIRMWARE_ELF_SHA256),
    ):
        present = path.is_file() and not path.is_symlink()
        observed_bytes = path.stat().st_size if present else None
        observed_sha256 = _sha256(path) if present else None
        result[key] = {
            "present": present,
            "verified": (
                present
                and byte_count > 0
                and SHA256_RE.fullmatch(wanted) is not None
                and observed_bytes == byte_count
                and observed_sha256 == wanted
            ),
            "observed_bytes": observed_bytes,
            "observed_sha256": observed_sha256,
        }
    return result


def build_report(*, verify_artifacts: bool = True) -> dict[str, Any]:
    if _canonical_sha256(_descriptor_payload()) != DESCRIPTOR_ID:
        raise ValueError("AA-abort descriptor identity differs")
    wanted_action = hashlib.sha256(
        ("MF1750_SAME_R20_AA_ABORT_WHITE_ACTION_V1|" + DESCRIPTOR_ID).encode("ascii")
    ).hexdigest()
    if wanted_action != ACTION_ID:
        raise ValueError("AA-abort action identity differs")
    action = _action()
    contract_payload = _contract_payload(action)
    if _canonical_sha256(contract_payload) != CONTRACT_ID:
        raise ValueError("AA-abort contract identity differs")
    source_evidence = _validate_source_evidence()
    bindings = artifact_binding_status()
    if verify_artifacts:
        for key in ("firmware_bin", "firmware_elf"):
            if bindings[key]["verified"] is not True:
                raise ValueError(f"AA-abort {key} binding differs")
    return {
        "schema_version": 1,
        "kind": "mf1750-same-r20-aa-abort-white-v1-pack",
        "offline_only": True,
        "hardware_accessed": False,
        "device_network_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "contract": {**contract_payload, "contract_id": CONTRACT_ID},
        "action": action,
        "source_termination_binding": dict(SOURCE_TERMINATION_BINDING),
        "source_evidence": source_evidence,
        "artifacts": {
            "firmware_bin": {
                "path": str(FIRMWARE_BIN),
                "bytes": FIRMWARE_BIN_BYTES,
                "sha256": FIRMWARE_BIN_SHA256,
            },
            "firmware_elf": {
                "path": str(FIRMWARE_ELF),
                "bytes": FIRMWARE_ELF_BYTES,
                "sha256": FIRMWARE_ELF_SHA256,
            },
        },
        "artifact_binding_status": bindings,
    }


def main() -> int:
    print(json.dumps(build_report(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
