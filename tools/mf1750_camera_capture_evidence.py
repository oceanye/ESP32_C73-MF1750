#!/usr/bin/env python3
"""Capture and seal one camera frame against one completed MF1750 action.

Importing this module performs no filesystem, camera, serial, network, relay,
or display access.  The DirectShow/OpenCV dependency is imported lazily only
by :func:`capture` when the default live capture backend is selected.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
from typing import Any


SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({LEGACY_SCHEMA_VERSION, SCHEMA_VERSION})
KIND = "mf1750-camera-capture-evidence"
INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
BINDING_LIVE = "live_synchronized"
BINDING_RETROSPECTIVE = "retrospective_unproven"
BINDING_LOCKED_RETAINED = "locked_retained_retrospective"
LOCKED_RETAINED_MANUAL_CONTROLS = {
    "autofocus": 0.0,
    "auto_exposure": 0.25,
    "auto_white_balance": 0.0,
}
LOCKED_RETAINED_VALUE_FIELDS = ("focus", "exposure", "white_balance_temperature")
LOCKED_RETAINED_LIMITATION = (
    "live camera acquisition of retained screen state does not prove continuity "
    "with the historical display action"
)
COVERAGE_PARTIAL = "partial_panel"
COVERAGE_FULL = "full_panel"
VERDICTS = frozenset({"INCONCLUSIVE", "PASS", "FAIL"})
CONFIDENCES = frozenset({"low", "medium", "high"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRANSACTION_DESCRIPTOR_MARKER_RE = re.compile(
    r"^MF1750_EC5_TX_DESCRIPTOR_V(?P<version>[1-9][0-9]*)"
    r"\|PROFILE=(?P<profile>[A-Z0-9_]+)"
    r"\|ROLE=(?P<role>[A-Z0-9_]+)"
    r"\|SHA256=(?P<sha256>[0-9a-f]{64})$"
)
FACTORY_OTP_WHITE_ACTION_ROLE = "FACTORY_OTP_WHITE_RECOVERY"
FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE = "FACTORY_OTP_WHITE_CONTAINMENT"
SAME_R20_AA_ABORT_OTP_WHITE_MARKER_ROLE = "SAME_R20_AA_ABORT_OTP_WHITE"
RAW_P16_ENDPOINT_GALLERY_OTP_WHITE_MARKER_ROLE = (
    "OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_CONTAINMENT"
)
RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_BINDING = {
    "profile_id": "WF23_25",
    "campaign_id": "EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1",
    "test_id": "EC5-RAW-P16-ENDPOINT-GALLERY-WHITE-CONTAINMENT-V1",
    "contract_id": "1d08798ba1a4012623c64625cec2edfaeb160aa3b20f0a2a98406994b55cce14",
    "build_tag": "MF1750_EC5_RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_V1_2026-08-28",
    "action_id": "12a146d8ad678165e1061fda3e7569743e28d663ee349b46ee900196b95d8cd6",
    "descriptor_id": "03920a12ad8f0b96e2dc6ae8281fa07da3cfb8ccc84da86dfb3f2cf2334f84dc",
    "marker": (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_RAW_P16_ENDPOINT_GALLERY_CONTAINMENT|"
        "SHA256=03920a12ad8f0b96e2dc6ae8281fa07da3cfb8ccc84da86dfb3f2cf2334f84dc"
    ),
}
RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS = (
    {
        "stage": "w1-after-t1",
        "profile_id": "WF23_25",
        "campaign_id": "EC5_RAW_P16_CROSSOVER_W1_AFTER_T1_WHITE_V1",
        "test_id": "EC5-RAW-P16-CROSSOVER-W1-AFTER-T1-WHITE-V1",
        "contract_id": "7c6afcd9dd4bfd26d52659d22687bdfe3bf8b891ed86cd0783538a720ddddd70",
        "build_tag": "MF1750_EC5_RAW_P16_CROSSOVER_W1_AFTER_T1_WHITE_V1_2026-08-30",
        "firmware_sha256": "4dc8e0333b9a37839af18cca0c76ad36d94bd621b6cbc7510b8d775dfd3e2b81",
        "action_id": "f8cf26e3c344d78ddebd06a570ad19f7cad879cf8b5d6d3f9ce620e86bd850a5",
        "descriptor_id": "c5314b8fede1a88e8e468d142856c6c2d79252a8acbd242749808161f50e1bbb",
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W1",
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W1|"
            "SHA256=c5314b8fede1a88e8e468d142856c6c2d79252a8acbd242749808161f50e1bbb"
        ),
    },
    {
        "stage": "w2-after-t2",
        "profile_id": "WF23_25",
        "campaign_id": "EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_WHITE_V1",
        "test_id": "EC5-RAW-P16-CROSSOVER-W2-AFTER-T2-WHITE-V1",
        "contract_id": "2888c7cdcb0ff22850ecfa25efcd722646cc21b68f4da43347d9af98a94a8615",
        "build_tag": "MF1750_EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_WHITE_V1_2026-08-30",
        "firmware_sha256": "76b13e8257390c6657178c305828f1725782121cc2c7991c6cc241e3119a846c",
        "action_id": "b0c81939e444c2e9d062e9d54850604409d89e81d59b521f28f8f46c1d456a4f",
        "descriptor_id": "aa326121718e574ff02bf373e80ca7ac3bfc2caef4aa05259be14f9a049884c2",
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W2",
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W2|"
            "SHA256=aa326121718e574ff02bf373e80ca7ac3bfc2caef4aa05259be14f9a049884c2"
        ),
    },
    {
        "stage": "w2-after-t2-coarse-discovery-successor",
        "profile_id": "WF23_25",
        "campaign_id": (
            "EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_WHITE_V1"
        ),
        "test_id": (
            "EC5-RAW-P16-CROSSOVER-W2-AFTER-T2-COARSE-DISCOVERY-SUCCESSOR-WHITE-V1"
        ),
        "contract_id": "00e1c99602f1ecef2e632647eec096f7c33a35eede00e19ebf0e255576742c4f",
        "build_tag": (
            "MF1750_EC5_RAW_P16_CROSSOVER_W2_AFTER_T2_COARSE_DISCOVERY_"
            "SUCCESSOR_WHITE_V1_2026-08-30"
        ),
        "firmware_sha256": "69cee9a616042fed9a709270bb46ee6d58bac66ca368b83c0a1796e3691ad5bd",
        "action_id": "26265cb3f26a9ae9f0b106822d163bad6cdc9776d18618726064729bcb280f6a",
        "descriptor_id": "97123851be38427788fa407a7b702c4fbbc3f94eef090db211820a0ae2b9b910",
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR",
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W2_DISCOVERY_SUCCESSOR|"
            "SHA256=97123851be38427788fa407a7b702c4fbbc3f94eef090db211820a0ae2b9b910"
        ),
    },
    {
        "stage": "w3-after-t2-coarse-discovery-successor-v2",
        "profile_id": "WF23_25",
        "campaign_id": (
            "EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_SUCCESSOR_V2_WHITE_V1"
        ),
        "test_id": (
            "EC5-RAW-P16-CROSSOVER-W3-AFTER-T2-COARSE-DISCOVERY-SUCCESSOR-V2-WHITE-V1"
        ),
        "contract_id": (
            "69be4f9fa69df03d861b1de6f01e289aca492fd4ad87a5ea1ef18f99dc2516a4"
        ),
        "build_tag": (
            "MF1750_EC5_RAW_P16_CROSSOVER_W3_AFTER_T2_COARSE_DISCOVERY_"
            "SUCCESSOR_V2_WHITE_V1_2026-08-30"
        ),
        "firmware_sha256": (
            "40c4be2f1213b61e68482e94d482217e8e4f8db4c7102074575a9da81a3f0ee2"
        ),
        "action_id": (
            "b37e6e5846eecff74b0d478dcdcf5223cdb20f2aa794a2b7f264c42bc21a87e9"
        ),
        "descriptor_id": (
            "5f14f576721f5f4143f7a577d92bc97d4ce5646aa98bc3f4edb52cfb9da7b24f"
        ),
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": ("OTP_WHITE_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2"),
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W3_DISCOVERY_SUCCESSOR_V2|"
            "SHA256=5f14f576721f5f4143f7a577d92bc97d4ce5646aa98bc3f4edb52cfb9da7b24f"
        ),
    },
    {
        "stage": "w3-final-after-t3",
        "profile_id": "WF23_25",
        "campaign_id": "EC5_RAW_P16_CROSSOVER_W3_FINAL_AFTER_T3_WHITE_V1",
        "test_id": "EC5-RAW-P16-CROSSOVER-W3-FINAL-AFTER-T3-WHITE-V1",
        "contract_id": "b7e984233f33c826f7882e44ede6297f38b5308947c02cd7561f2883e247ee6c",
        "build_tag": "MF1750_EC5_RAW_P16_CROSSOVER_W3_FINAL_AFTER_T3_WHITE_V1_2026-08-30",
        "firmware_sha256": "6ffce0798428f41205f26db7dc8e7d7da89939f6b0a775c117c3989e8e1b0804",
        "action_id": "c8e00dcb3a5d3bff11c192b56d7fc3074605be561fec1fb5688a065444365c63",
        "descriptor_id": "0d04b8ba84fa729a7a525bd598a94a42b713be0518c832e670fda4b6e90da462",
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": "OTP_WHITE_RAW_P16_CROSSOVER_W3",
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W3|"
            "SHA256=0d04b8ba84fa729a7a525bd598a94a42b713be0518c832e670fda4b6e90da462"
        ),
    },
    {
        "stage": "w4-after-t3-ac-profile-following-successor-v1",
        "profile_id": "WF23_25",
        "campaign_id": (
            "EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_SUCCESSOR_WHITE_V1"
        ),
        "test_id": (
            "EC5-RAW-P16-CROSSOVER-W4-AFTER-T3-AC-PROFILE-FOLLOWING-SUCCESSOR-WHITE-V1"
        ),
        "contract_id": (
            "7edf2e1916d536aa8b7d6d77be19899aab4fc6816e8c48de1e1b621bff0b7d52"
        ),
        "build_tag": (
            "MF1750_EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_WHITE_V1_2026-08-30"
        ),
        "firmware_sha256": (
            "9f3ab672c214cdf128a01a51b2803d5a586f72fab1cad065373eead30ee63bf7"
        ),
        "action_id": (
            "e621ea9a05da45da4a120c2b68fbdefcad5f4a48274a5ac5290f5fcc25d7c55b"
        ),
        "descriptor_id": (
            "398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45"
        ),
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": (
            "OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_SUCCESSOR"
        ),
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR|"
            "SHA256=398b8a86224185b6c6ca7b2d49bc83861f64f2a8c69afa03fbb430b9077c1f45"
        ),
    },
    {
        "stage": "w4-after-t3-ac-profile-following-successor-v2",
        "profile_id": "WF23_25",
        "campaign_id": (
            "EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V2_WHITE_V1"
        ),
        "test_id": (
            "EC5-RAW-P16-CROSSOVER-W4-AFTER-T3-AC-PROFILE-FOLLOWING-"
            "SUCCESSOR-V2-WHITE-V1"
        ),
        "contract_id": (
            "a75af9d7fcfc425ffff18f08d2c6f59eec61b1a4e8e53a3c18bcf2783767e6bb"
        ),
        "build_tag": (
            "MF1750_EC5_RAW_P16_CROSSOVER_W4_AFTER_T3_AC_PROFILE_"
            "FOLLOWING_SUCCESSOR_V2_WHITE_V1_2026-08-31"
        ),
        "firmware_sha256": (
            "311c30e3e3541108292bd135716d398e22942c34b7b2f25eaa90dcf486215093"
        ),
        "action_id": (
            "7d600b1a0072a1966e5240dec8756094962066d2ebd3fff555af2d93da3407f4"
        ),
        "descriptor_id": (
            "45e796933c4006b6b7afa050e2a4ba25fd9d78a922bf00ba11f0193002909e04"
        ),
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": (
            "OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V2"
        ),
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W4_T3_AC_PROFILE_FOLLOWING_"
            "SUCCESSOR_V2|"
            "SHA256=45e796933c4006b6b7afa050e2a4ba25fd9d78a922bf00ba11f0193002909e04"
        ),
    },
    {
        "stage": (
            "w11-after-t4-active-header-ca-r20-swap-confirmation-successor-"
            "v5-white-v1"
        ),
        "profile_id": "WF23_25",
        "campaign_id": (
            "EC5_RAW_P16_CROSSOVER_W11_AFTER_T4_ACTIVE_HEADER_CA_R20_SWAP_"
            "CONFIRMATION_SUCCESSOR_V5_WHITE_V1"
        ),
        "test_id": (
            "EC5-RAW-P16-CROSSOVER-W11-AFTER-T4-ACTIVE-HEADER-CA-R20-SWAP-"
            "CONFIRMATION-SUCCESSOR-V5-WHITE-V1"
        ),
        "contract_id": (
            "52aa5c78ba61abef70327a3e86df368668857e8d99e67c59c406371f757ba85f"
        ),
        "build_tag": (
            "MF1750_EC5_RAW_P16_CROSSOVER_W11_AFTER_T4_ACTIVE_HEADER_CA_R20_"
            "SWAP_CONFIRMATION_SUCCESSOR_V5_WHITE_V1_2026-09-01"
        ),
        "firmware_sha256": (
            "e10d4ba6063e885ca4ce1669b343ba9ece6451dc24cbdefafd16732ffa140f3e"
        ),
        "action_id": (
            "80a9fd85ff4b93ce365b699f1caa8d7835cbeeeaf738194f70cccc0f7500b595"
        ),
        "descriptor_id": (
            "076563342d74ff2aae8439c084b98a97fa7823cb54e29394ab859e0a716fc411"
        ),
        "role": FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
        "marker_role": (
            "OTP_WHITE_RAW_P16_CROSSOVER_W11_T4_V5_COMPLETE_TERMINAL"
        ),
        "marker": (
            "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
            "ROLE=OTP_WHITE_RAW_P16_CROSSOVER_W11_T4_V5_COMPLETE_TERMINAL|"
            "SHA256=076563342d74ff2aae8439c084b98a97fa7823cb54e29394ab859e0a716fc411"
        ),
    },
)
STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_BINDING = {
    "profile_id": "WF23_25",
    "campaign_id": "EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1",
    "test_id": "EC5-STABLE-CODE0-LUMA-LATIN-V3-FACTORY-OTP-WHITE-SUCCESSOR-V1",
    "contract_id": "787c2898a841913ac009e0284a1f3680403cc77a05ec700cb17f1a4a08152377",
    "build_tag": (
        "MF1750_EC5_STABLE_CODE0_LUMA_LATIN_V3_"
        "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
    ),
    "firmware_sha256": "804aadd5a9b82a02a01bc0431750790666d2ba56352d43b3add7f89245dff907",
    "action_id": "7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f",
    "descriptor_id": "8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0",
    "role": FACTORY_OTP_WHITE_ACTION_ROLE,
    "marker_role": "OTP_WHITE_AFTER_STABLE_CODE0_LATIN_V3_L3_OR_L4_COMPLETE",
    "marker": (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_AFTER_STABLE_CODE0_LATIN_V3_L3_OR_L4_COMPLETE|"
        "SHA256=8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0"
    ),
}
P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING = {
    "profile_id": "WF23_25",
    "campaign_id": "EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_FACTORY_OTP_WHITE_SUCCESSOR_V1",
    "test_id": "EC5-P1-ACTIVE-ENDPOINT-ATLAS-4X8-V1-FACTORY-OTP-WHITE-SUCCESSOR-V1",
    "contract_id": "403dc7e4c0efab105eddbe3039c32f1b563494cc866410046f3038fec2bf09ab",
    "build_tag": (
        "MF1750_EC5_P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_"
        "FACTORY_OTP_WHITE_SUCCESSOR_V1_2026-09-01"
    ),
    "firmware_sha256": "4f67f065993dfce3f6ffaeb2b5afb5a89f82c4563c9ad83b79c505311af24ef3",
    "action_id": "b28442077b06e959a9cf8bf4e588a5f463e5cfd004a71735e445916d9dbb80bc",
    "descriptor_id": "4e921326c729bb66d744237662abe63604648834b68d4e82085c4284edb2cf9c",
    "role": FACTORY_OTP_WHITE_ACTION_ROLE,
    "marker_role": "OTP_WHITE_AFTER_P1_ACTIVE_ENDPOINT_ATLAS_ORDINAL1_COMPLETE",
    "marker": (
        "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|"
        "ROLE=OTP_WHITE_AFTER_P1_ACTIVE_ENDPOINT_ATLAS_ORDINAL1_COMPLETE|"
        "SHA256=4e921326c729bb66d744237662abe63604648834b68d4e82085c4284edb2cf9c"
    ),
}
FACTORY_OTP_WHITE_REPORT_KIND = "mf1750-ec5-factory-otp-white-recovery-report"
FACTORY_OTP_WHITE_MARKER_ROLE_RE = re.compile(
    r"^(?:"
    r"[A-Z0-9]+(?:_[A-Z0-9]+)*_OTP_WHITE"
    r"|OTP_WHITE_[A-Z0-9]+(?:_[A-Z0-9]+)*"
    r")_(?:CONTAINMENT|SUCCESSOR)$"
)
DEFAULT_REQUESTED_SETTINGS: dict[str, Any] = {
    "fourcc": "MJPG",
    "frame_width": 1920,
    "frame_height": 1080,
    "fps": 30.0,
    "autofocus": None,
    "focus": None,
    "auto_exposure": None,
    "exposure": None,
    "auto_white_balance": None,
    "white_balance_temperature": None,
    "brightness": None,
    "contrast": None,
    "saturation": None,
    "hue": None,
}
TARGET_CAMERA_LOGICAL_ID = "USB_VID_32E4_PID_4801"
TARGET_CAMERA_FRIENDLY_NAME = "48MP USB Camera"
TARGET_CAMERA_USB_TOKEN = "vid_32e4&pid_4801"
EXCLUDED_BINOCULAR_USB_TOKEN = "vid_1bcf&pid_0b15"
DIRECTSHOW_DEVICE_ENUMERATOR = "ffmpeg-dshow-alternative-name-v1"
_DSHOW_VIDEO_RE = re.compile(r'^\[dshow @ [^]]+\] "(?P<name>.*)" \(video\)\s*$')
_DSHOW_ALTERNATIVE_RE = re.compile(
    r'^\[dshow @ [^]]+\]\s+Alternative name "(?P<name>.*)"\s*$'
)
_DSHOW_PNP_PREFIX = r"@device_pnp_\\?\usb#"
_DSHOW_PNP_SUFFIX_RE = re.compile(
    r"#\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}\\global$",
    re.IGNORECASE,
)


class CameraCaptureEvidenceError(RuntimeError):
    """The requested capture or evidence binding is invalid or incomplete."""


CaptureBackend = Callable[
    [int, Mapping[str, Any], int, int], tuple[bytes, Mapping[str, Any]]
]
DeviceResolver = Callable[[], Mapping[str, Any]]


class _DuplicateKeyError(ValueError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CameraCaptureEvidenceError(
            f"evidence contains a non-canonical JSON value: {error}"
        ) from error


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if "integrity" in result:
        raise CameraCaptureEvidenceError("cannot seal an object that has integrity")
    result["integrity"] = {
        "algorithm": INTEGRITY_ALGORITHM,
        "sha256": _canonical_sha256(result),
    }
    return result


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _read_stable_regular(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise CameraCaptureEvidenceError(
                f"{label} must be a regular non-symlink file: {path}"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise CameraCaptureEvidenceError(f"cannot read {label}: {error}") from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity or len(payload) != after.st_size:
        raise CameraCaptureEvidenceError(f"{label} changed while it was read")
    return payload


def _load_strict_json(path: Path, *, label: str) -> tuple[bytes, Mapping[str, Any]]:
    payload = _read_stable_regular(path, label=label)
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda item: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {item}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise CameraCaptureEvidenceError(
            f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise CameraCaptureEvidenceError(f"{label} root must be an object")
    return payload, value


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CameraCaptureEvidenceError(f"{label} must be an object")
    return value


def _require_text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CameraCaptureEvidenceError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    text = _require_text(value, label=label)
    if not SHA256_RE.fullmatch(text):
        raise CameraCaptureEvidenceError(f"{label} is not lowercase SHA-256")
    return text


def _verify_integrity(root: Mapping[str, Any], *, label: str) -> str:
    integrity = _require_mapping(root.get("integrity"), label=f"{label}.integrity")
    if set(integrity) != {"algorithm", "sha256"}:
        raise CameraCaptureEvidenceError(f"{label}.integrity keys differ")
    if integrity.get("algorithm") != INTEGRITY_ALGORITHM:
        raise CameraCaptureEvidenceError(f"{label}.integrity algorithm differs")
    declared = _require_sha256(integrity.get("sha256"), label=f"{label}.integrity")
    unsigned = dict(root)
    unsigned.pop("integrity", None)
    if _canonical_sha256(unsigned) != declared:
        raise CameraCaptureEvidenceError(f"{label}.integrity SHA-256 differs")
    return declared


def _validate_terminal_descriptor_binding(
    terminal: Mapping[str, Any], *, descriptor_id: str
) -> None:
    fields = (
        field
        for field in ("descriptor_id", "transaction_descriptor_sha256")
        if field in terminal
    )
    found = False
    for field in fields:
        found = True
        terminal_descriptor = _require_sha256(
            terminal.get(field), label=f"terminal {field}"
        )
        if terminal_descriptor != descriptor_id:
            raise CameraCaptureEvidenceError(
                f"action and terminal report {field} differ"
            )
    if not found:
        raise CameraCaptureEvidenceError(
            "terminal report has no authenticated descriptor identity"
        )


def _validate_terminal_role_binding(
    terminal: Mapping[str, Any],
    *,
    action_id: str,
    descriptor_id: str,
    firmware_sha256: str,
    role: str,
) -> None:
    if "role" in terminal:
        terminal_role = _require_text(terminal.get("role"), label="terminal role")
        if terminal_role != role:
            raise CameraCaptureEvidenceError("action and terminal report role differ")
        if role != FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE:
            return
        # An explicit matching role must not bypass the two reviewed
        # containment admissions below.  In particular, an arbitrary result
        # cannot become camera-bindable merely by repeating the generic
        # FACTORY_OTP_WHITE_CONTAINMENT string in both objects.

    # The reviewed EC5 factory-white terminal schema omits ``role``.  Accept
    # that narrow schema only when its device-returned transaction identity and
    # marker jointly authenticate the factory-white role family.  This keeps
    # the legacy explicit-role path strict and does not turn a missing role into
    # an unconditional bypass.
    if terminal.get("kind") != FACTORY_OTP_WHITE_REPORT_KIND or role not in {
        FACTORY_OTP_WHITE_ACTION_ROLE,
        FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE,
    }:
        raise CameraCaptureEvidenceError(
            "terminal report role is missing without factory-white role binding"
        )
    transaction_descriptor = _require_sha256(
        terminal.get("transaction_descriptor_sha256"),
        label="terminal transaction_descriptor_sha256",
    )
    if transaction_descriptor != descriptor_id:
        raise CameraCaptureEvidenceError(
            "action and terminal report transaction_descriptor_sha256 differ"
        )
    profile_id = _require_text(terminal.get("profile_id"), label="terminal profile_id")
    marker = _require_text(
        terminal.get("transaction_descriptor_marker"),
        label="terminal transaction_descriptor_marker",
    )
    match = TRANSACTION_DESCRIPTOR_MARKER_RE.fullmatch(marker)
    if match is None:
        raise CameraCaptureEvidenceError(
            "terminal transaction descriptor marker is malformed"
        )
    marker_role = match.group("role")
    marker_role_matches_action = (
        role == FACTORY_OTP_WHITE_ACTION_ROLE
        and FACTORY_OTP_WHITE_MARKER_ROLE_RE.fullmatch(marker_role) is not None
    ) or (
        role == FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE
        and marker_role == SAME_R20_AA_ABORT_OTP_WHITE_MARKER_ROLE
    )
    if (
        role == FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE
        and marker_role == RAW_P16_ENDPOINT_GALLERY_OTP_WHITE_MARKER_ROLE
    ):
        # This is a frozen one-action campaign, not a generic admission for
        # similarly named containment markers.  Require the complete reviewed
        # identity tuple so a self-consistent but different campaign, contract,
        # action, or descriptor cannot reuse the retained-camera evidence gate.
        actual_binding = {
            "profile_id": profile_id,
            "campaign_id": terminal.get("campaign_id"),
            "test_id": terminal.get("test_id"),
            "contract_id": terminal.get("contract_id"),
            "build_tag": terminal.get("build_tag"),
            "action_id": action_id,
            "descriptor_id": descriptor_id,
            "marker": marker,
        }
        if actual_binding != RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_BINDING:
            differing = sorted(
                field
                for field, expected in (
                    RAW_P16_ENDPOINT_GALLERY_WHITE_CONTAINMENT_BINDING.items()
                )
                if actual_binding.get(field) != expected
            )
            raise CameraCaptureEvidenceError(
                "RAW-P16 endpoint-gallery containment allowlist binding differs: "
                + ", ".join(differing)
            )
        marker_role_matches_action = True
    crossover_binding = next(
        (
            binding
            for binding in RAW_P16_CROSSOVER_WHITE_CONTAINMENT_BINDINGS
            if binding["marker_role"] == marker_role
        ),
        None,
    )
    if crossover_binding:
        # A reviewed marker is part of one frozen containment tuple.  Do not
        # let its ``...SUCCESSOR`` suffix fall back to the broader historical
        # FACTORY_OTP_WHITE_RECOVERY marker-family admission when the action
        # role has been changed.  Every field below, including role, must
        # match the reviewed crossover binding.
        actual_binding = {
            "stage": crossover_binding["stage"],
            "profile_id": profile_id,
            "campaign_id": terminal.get("campaign_id"),
            "test_id": terminal.get("test_id"),
            "contract_id": terminal.get("contract_id"),
            "build_tag": terminal.get("build_tag"),
            "firmware_sha256": firmware_sha256,
            "action_id": action_id,
            "descriptor_id": descriptor_id,
            "role": role,
            "marker_role": marker_role,
            "marker": marker,
        }
        if actual_binding != crossover_binding:
            differing = sorted(
                field
                for field, expected in crossover_binding.items()
                if actual_binding.get(field) != expected
            )
            raise CameraCaptureEvidenceError(
                "RAW-P16 crossover white containment allowlist binding differs: "
                + ", ".join(differing)
            )
        marker_role_matches_action = True
    if marker_role == STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_BINDING["marker_role"]:
        # This completed-source successor has a reviewed marker that deliberately
        # does not belong to the broader ``...CONTAINMENT|SUCCESSOR`` family.
        # Admit only its complete frozen identity tuple; do not widen the regex.
        actual_binding = {
            "profile_id": profile_id,
            "campaign_id": terminal.get("campaign_id"),
            "test_id": terminal.get("test_id"),
            "contract_id": terminal.get("contract_id"),
            "build_tag": terminal.get("build_tag"),
            "firmware_sha256": firmware_sha256,
            "action_id": action_id,
            "descriptor_id": descriptor_id,
            "role": role,
            "marker_role": marker_role,
            "marker": marker,
        }
        if actual_binding != STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_BINDING:
            differing = sorted(
                field
                for field, expected in (
                    STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_BINDING.items()
                )
                if actual_binding.get(field) != expected
            )
            raise CameraCaptureEvidenceError(
                "stable-code0 luma Latin V3 white successor allowlist binding "
                "differs: " + ", ".join(differing)
            )
        marker_role_matches_action = True
    if marker_role == P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING[
        "marker_role"
    ]:
        # This retained clean-white source is one already executed successor.
        # Its marker deliberately names the completed source ordinal, so admit
        # only the complete frozen identity tuple rather than widening the
        # generic marker-family expression.
        actual_binding = {
            "profile_id": profile_id,
            "campaign_id": terminal.get("campaign_id"),
            "test_id": terminal.get("test_id"),
            "contract_id": terminal.get("contract_id"),
            "build_tag": terminal.get("build_tag"),
            "firmware_sha256": firmware_sha256,
            "action_id": action_id,
            "descriptor_id": descriptor_id,
            "role": role,
            "marker_role": marker_role,
            "marker": marker,
        }
        if actual_binding != P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING:
            differing = sorted(
                field
                for field, expected in (
                    P1_ACTIVE_ENDPOINT_ATLAS_4X8_V1_WHITE_SUCCESSOR_BINDING.items()
                )
                if actual_binding.get(field) != expected
            )
            raise CameraCaptureEvidenceError(
                "P1 active-endpoint atlas 4x8 V1 white successor allowlist "
                "binding differs: " + ", ".join(differing)
            )
        marker_role_matches_action = True
    if (
        match.group("profile") != profile_id
        or match.group("sha256") != descriptor_id
        or not marker_role_matches_action
    ):
        raise CameraCaptureEvidenceError(
            "terminal transaction descriptor marker binding differs"
        )


def _validate_same_r20_aa_abort_white_execution(
    root: Mapping[str, Any],
    terminal: Mapping[str, Any],
    *,
    role: str,
    visible_refreshes: int,
) -> None:
    """Keep the AA-abort containment admission narrower than generic white."""

    if role != FACTORY_OTP_WHITE_CONTAINMENT_ACTION_ROLE:
        return
    if terminal.get("kind") != FACTORY_OTP_WHITE_REPORT_KIND:
        raise CameraCaptureEvidenceError(
            "AA-abort containment terminal report kind differs"
        )
    if visible_refreshes != 1:
        raise CameraCaptureEvidenceError(
            "AA-abort containment must have exactly one visible refresh"
        )
    expected_terminal_fields = {
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "no_retry": True,
        "campaign_complete": True,
    }
    for field, expected in expected_terminal_fields.items():
        if terminal.get(field) != expected:
            raise CameraCaptureEvidenceError(
                f"AA-abort containment terminal {field} differs"
            )
    driver = _require_mapping(
        terminal.get("driver"), label="AA-abort containment terminal driver"
    )
    expected_driver_fields = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "failure_stage": "none",
        "failure_code": 0,
    }
    for field, expected in expected_driver_fields.items():
        if driver.get(field) != expected:
            raise CameraCaptureEvidenceError(
                f"AA-abort containment driver {field} differs"
            )
    if root.get("outcome") != "complete_pass":
        raise CameraCaptureEvidenceError(
            "AA-abort containment outcome is not complete_pass"
        )


def _validate_terminal_boot_nonce_binding(
    root: Mapping[str, Any],
    terminal: Mapping[str, Any],
    *,
    boot_nonce: str,
    descriptor_id: str,
    action_id: str,
    ordinal: int,
) -> None:
    if "boot_nonce" in terminal:
        terminal_boot_nonce = _require_text(
            terminal.get("boot_nonce"), label="terminal boot_nonce"
        )
        if terminal_boot_nonce != boot_nonce:
            raise CameraCaptureEvidenceError("action boot nonce differs")
        return

    if terminal.get("kind") != FACTORY_OTP_WHITE_REPORT_KIND:
        raise CameraCaptureEvidenceError(
            "terminal boot nonce is missing without factory-white transcript binding"
        )
    transcript = root.get("transcript")
    if not isinstance(transcript, list) or not transcript:
        raise CameraCaptureEvidenceError(
            "terminal boot nonce is missing without an authenticated transcript"
        )
    entries = [
        _require_mapping(item, label=f"transcript[{index}]")
        for index, item in enumerate(transcript)
    ]

    def one(endpoint: str, method: str, status: int) -> Mapping[str, Any]:
        matches = [
            item
            for item in entries
            if item.get("endpoint") == endpoint
            and item.get("method") == method
            and item.get("status") == status
        ]
        if len(matches) != 1:
            raise CameraCaptureEvidenceError(
                f"factory-white transcript {endpoint} identity differs"
            )
        return matches[0]

    status_entry = one("status", "GET", 200)
    arm_entry = one("arm", "POST", 201)
    execute_entry = one("execute", "POST", 202)
    final_entry = entries[-1]
    if (
        final_entry.get("endpoint") != "report"
        or final_entry.get("method") != "GET"
        or final_entry.get("status") != 200
        or final_entry.get("body") != terminal
    ):
        raise CameraCaptureEvidenceError(
            "factory-white transcript final terminal report differs"
        )

    status_body = _require_mapping(
        status_entry.get("body"), label="transcript status body"
    )
    arm_body = _require_mapping(arm_entry.get("body"), label="transcript arm body")
    execute_body = _require_mapping(
        execute_entry.get("body"), label="transcript execute body"
    )
    if (
        status_body.get("boot_nonce") != boot_nonce
        or arm_body.get("boot_nonce") != boot_nonce
    ):
        raise CameraCaptureEvidenceError("factory-white transcript boot nonce differs")
    if (
        arm_body.get("accepted") is not True
        or arm_body.get("action_id") != action_id
        or arm_body.get("ordinal") != ordinal
        or execute_body.get("accepted") is not True
        or execute_body.get("action_id") != action_id
    ):
        raise CameraCaptureEvidenceError(
            "factory-white transcript mutation identity differs"
        )

    marker = terminal.get("transaction_descriptor_marker")
    shared_identity = {
        "campaign_id": terminal.get("campaign_id"),
        "test_id": terminal.get("test_id"),
        "contract_id": terminal.get("contract_id"),
        "build_tag": terminal.get("build_tag"),
        "transaction_descriptor_sha256": descriptor_id,
        "transaction_descriptor_marker": marker,
    }
    for label, body in (
        ("status", status_body),
        ("arm", arm_body),
        ("execute", execute_body),
    ):
        if any(
            body.get(field) != expected for field, expected in shared_identity.items()
        ):
            raise CameraCaptureEvidenceError(
                f"factory-white transcript {label} binding differs"
            )

    expected_headers = {
        "X-EC5-Action-Id": action_id,
        "X-EC5-Boot-Nonce": boot_nonce,
        "X-EC5-Build-Tag": terminal.get("build_tag"),
        "X-EC5-Campaign-Id": terminal.get("campaign_id"),
        "X-EC5-Descriptor-Id": descriptor_id,
        "X-EC5-Ordinal": str(ordinal),
        "X-EC5-Test-Id": terminal.get("test_id"),
    }
    for label, entry in (("arm", arm_entry), ("execute", execute_entry)):
        headers = _require_mapping(
            entry.get("headers"), label=f"transcript {label} headers"
        )
        if any(
            headers.get(field) != expected
            for field, expected in expected_headers.items()
        ):
            raise CameraCaptureEvidenceError(
                f"factory-white transcript {label} header binding differs"
            )


def _load_action_result(path: Path) -> tuple[bytes, Mapping[str, Any], dict[str, Any]]:
    payload, root = _load_strict_json(path, label="action result")
    canonical_integrity = _verify_integrity(root, label="action result")
    action = _require_mapping(root.get("action"), label="action result.action")
    terminal = _require_mapping(
        root.get("terminal_report"), label="action result.terminal_report"
    )
    action_id = _require_sha256(action.get("action_id"), label="action.action_id")
    descriptor_id = _require_sha256(
        action.get("descriptor_id"), label="action.descriptor_id"
    )
    frame_sha256 = _require_sha256(
        action.get("frame_sha256"), label="action.frame_sha256"
    )
    ordinal = action.get("ordinal")
    if type(ordinal) is not int or ordinal < 1:
        raise CameraCaptureEvidenceError("action.ordinal must be a positive integer")
    role = _require_text(action.get("role"), label="action.role")
    if root.get("outcome") != "complete_pass":
        raise CameraCaptureEvidenceError("action result outcome is not complete_pass")
    if (
        terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("valid") is not True
    ):
        raise CameraCaptureEvidenceError(
            "action terminal report is not a valid COMPLETE"
        )
    comparisons = {"action_id": action_id, "ordinal": ordinal}
    for field, expected in comparisons.items():
        if terminal.get(field) != expected:
            raise CameraCaptureEvidenceError(
                f"action and terminal report {field} differ"
            )
    _validate_terminal_descriptor_binding(terminal, descriptor_id=descriptor_id)
    firmware_sha256 = _require_sha256(
        root.get("firmware_sha256"), label="action result.firmware_sha256"
    )
    _validate_terminal_role_binding(
        terminal,
        action_id=action_id,
        descriptor_id=descriptor_id,
        firmware_sha256=firmware_sha256,
        role=role,
    )
    boot_nonce = _require_text(root.get("boot_nonce"), label="action result.boot_nonce")
    _validate_terminal_boot_nonce_binding(
        root,
        terminal,
        boot_nonce=boot_nonce,
        descriptor_id=descriptor_id,
        action_id=action_id,
        ordinal=ordinal,
    )
    visible_refreshes = root.get("visible_refreshes")
    if type(visible_refreshes) is not int or visible_refreshes < 0:
        raise CameraCaptureEvidenceError(
            "action result.visible_refreshes must be a non-negative integer"
        )
    _validate_same_r20_aa_abort_white_execution(
        root,
        terminal,
        role=role,
        visible_refreshes=visible_refreshes,
    )
    identity = {
        "campaign_id": _require_text(
            terminal.get("campaign_id"), label="terminal campaign_id"
        ),
        "test_id": _require_text(terminal.get("test_id"), label="terminal test_id"),
        "contract_id": _require_sha256(
            terminal.get("contract_id"), label="terminal contract_id"
        ),
        "firmware_sha256": firmware_sha256,
        "boot_nonce": boot_nonce,
        "ordinal": ordinal,
        "action_id": action_id,
        "descriptor_id": descriptor_id,
        "role": role,
        "frame_sha256": frame_sha256,
        "build_tag": _require_text(
            terminal.get("build_tag"), label="terminal build_tag"
        ),
        "action_result_created_at": _require_text(
            root.get("created_at"), label="action result.created_at"
        ),
        "visible_refreshes": visible_refreshes,
        "terminal_state": terminal["terminal_state"],
        "outcome": root["outcome"],
        "canonical_integrity_sha256": canonical_integrity,
    }
    return payload, root, identity


def _decode_jpeg(payload: bytes) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat

        with Image.open(BytesIO(payload)) as opened:
            if opened.format != "JPEG":
                raise CameraCaptureEvidenceError("photo bytes are not JPEG")
            opened.load()
            rgb = opened.convert("RGB")
            width, height = rgb.size
            if width < 1 or height < 1:
                raise CameraCaptureEvidenceError("JPEG dimensions are invalid")
            stat_summary = ImageStat.Stat(rgb)
            histogram = rgb.histogram()
    except CameraCaptureEvidenceError:
        raise
    except (OSError, ValueError) as error:
        raise CameraCaptureEvidenceError(f"JPEG decode failed: {error}") from error
    pixels = width * height
    high: list[float] = []
    low: list[float] = []
    for channel in range(3):
        channel_histogram = histogram[channel * 256 : (channel + 1) * 256]
        high.append(sum(channel_histogram[250:]) / pixels)
        low.append(sum(channel_histogram[:6]) / pixels)
    return {
        "decoded_format": "JPEG",
        "width": width,
        "height": height,
        "mode": "RGB",
        "quality_metrics": {
            "mean_rgb": [round(float(item), 6) for item in stat_summary.mean],
            "stddev_rgb": [round(float(item), 6) for item in stat_summary.stddev],
            "high_clip_fraction_rgb_at_or_above_250": [round(item, 9) for item in high],
            "low_clip_fraction_rgb_at_or_below_5": [round(item, 9) for item in low],
            "camera_relative_only": True,
            "absolute_colour_qualification": False,
        },
    }


def _normalise_requested_settings(value: Mapping[str, Any] | None) -> dict[str, Any]:
    settings = dict(DEFAULT_REQUESTED_SETTINGS)
    if value is not None:
        unknown = set(value) - set(settings)
        if unknown:
            raise CameraCaptureEvidenceError(
                f"unknown requested camera settings: {sorted(unknown)!r}"
            )
        settings.update(value)
    if settings["fourcc"] != "MJPG":
        raise CameraCaptureEvidenceError("only MJPG camera capture is supported")
    for field in ("frame_width", "frame_height"):
        item = settings[field]
        if type(item) is not int or item < 1:
            raise CameraCaptureEvidenceError(f"{field} must be a positive integer")
    fps = settings["fps"]
    if not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0:
        raise CameraCaptureEvidenceError("fps must be positive")
    for field, item in settings.items():
        if field in {"fourcc", "frame_width", "frame_height", "fps"} or item is None:
            continue
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise CameraCaptureEvidenceError(f"{field} must be numeric or null")
        if not math.isfinite(float(item)):
            raise CameraCaptureEvidenceError(f"{field} must be finite")
    _canonical_json_bytes(settings)
    return settings


def _expected_set_result_keys(settings: Mapping[str, Any]) -> set[str]:
    return {
        field
        for field, value in settings.items()
        if field == "fourcc" or value is not None
    }


def _validated_set_results(
    value: Any, *, settings: Mapping[str, Any], label: str
) -> dict[str, bool]:
    results = _require_mapping(value, label=label)
    expected = _expected_set_result_keys(settings)
    if set(results) != expected:
        raise CameraCaptureEvidenceError(
            f"{label} keys differ from attempted camera settings"
        )
    if any(type(result) is not bool for result in results.values()):
        raise CameraCaptureEvidenceError(f"{label} values must be booleans")
    return dict(results)


def _validate_locked_retained_request(settings: Mapping[str, Any]) -> None:
    for field, expected in LOCKED_RETAINED_MANUAL_CONTROLS.items():
        value = settings.get(field)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) != expected
        ):
            raise CameraCaptureEvidenceError(
                f"locked-retained {field} must equal {expected:g}"
            )
    for field in LOCKED_RETAINED_VALUE_FIELDS:
        value = settings.get(field)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
        ):
            raise CameraCaptureEvidenceError(
                f"locked-retained {field} must be an explicit finite value"
            )


def _normalise_diagnostic_number(value: Any) -> int | float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _fourcc_text(value: Any) -> str | None:
    number = _normalise_diagnostic_number(value)
    if number is None:
        return None
    raw = int(number)
    text = "".join(chr((raw >> (8 * index)) & 0xFF) for index in range(4))
    return text if all(32 <= ord(character) <= 126 for character in text) else None


def _parse_dshow_video_devices(output: str) -> list[dict[str, Any]]:
    """Parse FFmpeg's DirectShow video-device/alternative-name pairs.

    The alternative name is the only enumerated value in this workflow that
    carries the underlying USB VID/PID.  A friendly name or OpenCV index alone
    is deliberately insufficient.
    """

    devices: list[dict[str, Any]] = []
    pending_name: str | None = None
    for line in output.splitlines():
        video_match = _DSHOW_VIDEO_RE.fullmatch(line.strip())
        if video_match is not None:
            if pending_name is not None:
                raise CameraCaptureEvidenceError(
                    "DirectShow video device is missing its alternative name"
                )
            pending_name = video_match.group("name")
            continue
        alternative_match = _DSHOW_ALTERNATIVE_RE.fullmatch(line.strip())
        if alternative_match is None or pending_name is None:
            continue
        alternative_name = alternative_match.group("name")
        devices.append(
            {
                "friendly_name": pending_name,
                "alternative_name": alternative_name,
                "directshow_index": len(devices),
            }
        )
        pending_name = None
    if pending_name is not None:
        raise CameraCaptureEvidenceError(
            "DirectShow video device is missing its alternative name"
        )
    if not devices:
        raise CameraCaptureEvidenceError(
            "FFmpeg returned no parseable DirectShow video devices"
        )
    alternatives = [str(item["alternative_name"]).casefold() for item in devices]
    if len(set(alternatives)) != len(alternatives):
        raise CameraCaptureEvidenceError(
            "DirectShow returned duplicate alternative device names"
        )
    return devices


def _pnp_instance_from_alternative_name(alternative_name: str) -> str:
    lower = alternative_name.casefold()
    if not lower.startswith(_DSHOW_PNP_PREFIX.casefold()):
        raise CameraCaptureEvidenceError(
            "target DirectShow alternative name is not a USB PnP path"
        )
    body = alternative_name[len(_DSHOW_PNP_PREFIX) :]
    suffix = _DSHOW_PNP_SUFFIX_RE.search(body)
    if suffix is None:
        raise CameraCaptureEvidenceError(
            "target DirectShow alternative name has an invalid PnP suffix"
        )
    device_path = body[: suffix.start()]
    if not device_path or "#" not in device_path:
        raise CameraCaptureEvidenceError(
            "target DirectShow alternative name has an invalid USB instance path"
        )
    return ("USB\\" + device_path.replace("#", "\\")).upper()


def _alternative_has_usb_id(value: str, *, vid: str, pid: str) -> bool:
    return (
        re.search(
            rf"(?:^|#)vid_{re.escape(vid.casefold())}&"
            rf"pid_{re.escape(pid.casefold())}(?:&|#)",
            value.casefold(),
        )
        is not None
    )


def _validated_authenticated_device(value: Any) -> dict[str, Any]:
    device = _require_mapping(value, label="authenticated camera device")
    expected_keys = {
        "enumerator",
        "friendly_name",
        "alternative_name",
        "pnp_instance_id",
        "directshow_index",
        "usb_vid",
        "usb_pid",
    }
    if set(device) != expected_keys:
        raise CameraCaptureEvidenceError("authenticated camera device keys differ")
    if device.get("enumerator") != DIRECTSHOW_DEVICE_ENUMERATOR:
        raise CameraCaptureEvidenceError("camera enumerator identity differs")
    if device.get("friendly_name") != TARGET_CAMERA_FRIENDLY_NAME:
        raise CameraCaptureEvidenceError("authenticated camera friendly name differs")
    alternative_name = _require_text(
        device.get("alternative_name"), label="camera alternative_name"
    )
    if not _alternative_has_usb_id(
        alternative_name, vid="32E4", pid="4801"
    ) or _alternative_has_usb_id(alternative_name, vid="1BCF", pid="0B15"):
        raise CameraCaptureEvidenceError(
            "authenticated camera alternative name is not the MF1750 48MP target"
        )
    expected_pnp = _pnp_instance_from_alternative_name(alternative_name)
    if device.get("pnp_instance_id") != expected_pnp:
        raise CameraCaptureEvidenceError("camera PnP instance identity differs")
    if device.get("usb_vid") != "32E4" or device.get("usb_pid") != "4801":
        raise CameraCaptureEvidenceError("authenticated camera VID/PID differs")
    index = device.get("directshow_index")
    if type(index) is not int or index < 0:
        raise CameraCaptureEvidenceError("authenticated DirectShow index is invalid")
    return dict(device)


def _resolve_exact_mf1750_camera() -> dict[str, Any]:
    """Resolve the sole allowed camera without opening any video stream."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise CameraCaptureEvidenceError(
            "ffmpeg is required to authenticate the DirectShow USB device"
        )
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-list_devices",
                "true",
                "-f",
                "dshow",
                "-i",
                "dummy",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CameraCaptureEvidenceError(
            f"cannot enumerate DirectShow devices with ffmpeg: {error}"
        ) from error
    try:
        output = (completed.stdout + completed.stderr).decode("utf-8")
    except UnicodeDecodeError as error:
        raise CameraCaptureEvidenceError(
            "FFmpeg DirectShow enumeration is not strict UTF-8"
        ) from error
    devices = _parse_dshow_video_devices(output)
    matches = [
        item
        for item in devices
        if _alternative_has_usb_id(
            str(item["alternative_name"]), vid="32E4", pid="4801"
        )
    ]
    if len(matches) != 1:
        raise CameraCaptureEvidenceError(
            "MF1750 requires exactly one DirectShow VID_32E4:PID_4801 camera; "
            f"found {len(matches)}"
        )
    selected = matches[0]
    if selected["friendly_name"] != TARGET_CAMERA_FRIENDLY_NAME:
        raise CameraCaptureEvidenceError(
            "VID_32E4:PID_4801 DirectShow friendly name differs from 48MP USB Camera"
        )
    alternative_name = str(selected["alternative_name"])
    if _alternative_has_usb_id(alternative_name, vid="1BCF", pid="0B15"):
        raise CameraCaptureEvidenceError(
            "refusing the excluded binocular VID_1BCF:PID_0B15 camera"
        )
    return _validated_authenticated_device(
        {
            "enumerator": DIRECTSHOW_DEVICE_ENUMERATOR,
            "friendly_name": selected["friendly_name"],
            "alternative_name": alternative_name,
            "pnp_instance_id": _pnp_instance_from_alternative_name(alternative_name),
            "directshow_index": selected["directshow_index"],
            "usb_vid": "32E4",
            "usb_pid": "4801",
        }
    )


def _validate_camera_claims(
    *,
    camera_id: str,
    camera_instance_id: str | None,
    authenticated_device: Mapping[str, Any],
) -> None:
    claimed_id = _require_text(camera_id, label="camera_id")
    compact_claimed_id = re.sub(r"[^0-9a-z]", "", claimed_id.casefold())
    if "vid1bcfpid0b15" in compact_claimed_id:
        raise CameraCaptureEvidenceError(
            "refusing the excluded binocular VID_1BCF:PID_0B15 camera"
        )
    if claimed_id not in {TARGET_CAMERA_LOGICAL_ID, TARGET_CAMERA_FRIENDLY_NAME}:
        raise CameraCaptureEvidenceError(
            "camera_id must name the MF1750 48MP VID_32E4:PID_4801 target"
        )
    if camera_instance_id is None:
        return
    claimed_instance = _require_text(camera_instance_id, label="camera_instance_id")
    if EXCLUDED_BINOCULAR_USB_TOKEN in claimed_instance.casefold():
        raise CameraCaptureEvidenceError(
            "refusing the excluded binocular VID_1BCF:PID_0B15 camera"
        )
    allowed_instances = {
        str(authenticated_device["alternative_name"]).casefold(),
        str(authenticated_device["pnp_instance_id"]).casefold(),
    }
    if claimed_instance.casefold() not in allowed_instances:
        raise CameraCaptureEvidenceError(
            "caller camera_instance_id differs from the authenticated target"
        )


def _default_capture_backend(
    camera_index: int,
    requested_settings: Mapping[str, Any],
    warmup_frames: int,
    jpeg_quality: int,
    *,
    _device_resolver: DeviceResolver = _resolve_exact_mf1750_camera,
) -> tuple[bytes, Mapping[str, Any]]:
    try:
        import cv2
    except ImportError as error:
        raise CameraCaptureEvidenceError(
            "OpenCV is required for live DirectShow capture"
        ) from error

    authenticated_before = _validated_authenticated_device(_device_resolver())
    if camera_index != authenticated_before["directshow_index"]:
        raise CameraCaptureEvidenceError(
            "OpenCV index differs from the immediately authenticated DirectShow target"
        )
    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap.release()
        raise CameraCaptureEvidenceError(
            f"cannot open DirectShow camera index {camera_index}"
        )
    properties = {
        "frame_width": cv2.CAP_PROP_FRAME_WIDTH,
        "frame_height": cv2.CAP_PROP_FRAME_HEIGHT,
        "fps": cv2.CAP_PROP_FPS,
        "autofocus": cv2.CAP_PROP_AUTOFOCUS,
        "focus": cv2.CAP_PROP_FOCUS,
        "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
        "exposure": cv2.CAP_PROP_EXPOSURE,
        "auto_white_balance": cv2.CAP_PROP_AUTO_WB,
        "white_balance_temperature": cv2.CAP_PROP_WB_TEMPERATURE,
        "brightness": cv2.CAP_PROP_BRIGHTNESS,
        "contrast": cv2.CAP_PROP_CONTRAST,
        "saturation": cv2.CAP_PROP_SATURATION,
        "hue": cv2.CAP_PROP_HUE,
    }

    def effective() -> dict[str, Any]:
        values = {
            key: _normalise_diagnostic_number(cap.get(prop))
            for key, prop in properties.items()
        }
        raw_fourcc = cap.get(cv2.CAP_PROP_FOURCC)
        values["fourcc"] = _fourcc_text(raw_fourcc)
        return values

    read_failures = 0
    set_results: dict[str, bool] = {}
    try:
        set_results["fourcc"] = bool(
            cap.set(
                cv2.CAP_PROP_FOURCC,
                cv2.VideoWriter_fourcc(*str(requested_settings["fourcc"])),
            )
        )
        for key, prop in properties.items():
            requested = requested_settings.get(key)
            if requested is not None:
                set_results[key] = bool(cap.set(prop, float(requested)))
        before = effective()
        completed = 0
        while completed < warmup_frames:
            ok, _discarded = cap.read()
            if ok:
                completed += 1
                continue
            read_failures += 1
            if read_failures > 3:
                raise CameraCaptureEvidenceError(
                    "camera failed repeatedly during warmup"
                )
        ok, frame = cap.read()
        frame_retrieved_at = _now()
        frame_retrieved_at_utc = _utc_now()
        if not ok or frame is None:
            raise CameraCaptureEvidenceError("formal camera frame read failed")
        encoded, buffer = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
        )
        if not encoded:
            raise CameraCaptureEvidenceError("OpenCV JPEG encoding failed")
        after = effective()
        try:
            backend_name = cap.getBackendName()
        except cv2.error:
            backend_name = "DSHOW"
        if str(backend_name).casefold() != "dshow":
            raise CameraCaptureEvidenceError(
                "OpenCV opened a backend other than DirectShow"
            )
        authenticated_after = _validated_authenticated_device(_device_resolver())
        if authenticated_after != authenticated_before:
            raise CameraCaptureEvidenceError(
                "DirectShow device mapping changed while the camera was open"
            )
        return bytes(buffer), {
            "backend": backend_name,
            "authenticated_device": authenticated_after,
            "set_results": set_results,
            "effective_settings_before_frame": before,
            "effective_settings_after_frame": after,
            "warmup_frames_completed": completed,
            "read_failures": read_failures,
            "frame_retrieved_at": frame_retrieved_at,
            "frame_retrieved_at_utc": frame_retrieved_at_utc,
        }
    finally:
        cap.release()


def _reserve_output(path: Path, *, label: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise CameraCaptureEvidenceError(
            f"refusing to overwrite {label}: {path}"
        ) from error
    except OSError as error:
        raise CameraCaptureEvidenceError(f"cannot reserve {label}: {error}") from error


def _write_reserved(fd: int, payload: bytes) -> None:
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    written = 0
    while written < len(payload):
        count = os.write(fd, payload[written:])
        if count < 1:
            raise CameraCaptureEvidenceError("short write to reserved evidence file")
        written += count
    os.fsync(fd)


def _close_reserved(fd: int | None) -> None:
    if fd is not None:
        os.close(fd)


def _relative_evidence_path(path: Path, *, sidecar_path: Path, label: str) -> str:
    base = sidecar_path.parent.resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError as error:
        raise CameraCaptureEvidenceError(
            f"{label} must be inside the sidecar directory tree"
        ) from error
    if not relative.parts:
        raise CameraCaptureEvidenceError(f"{label} cannot be the sidecar directory")
    return PurePosixPath(*relative.parts).as_posix()


def _resolve_evidence_path(text: Any, *, sidecar_path: Path, label: str) -> Path:
    value = _require_text(text, label=label)
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise CameraCaptureEvidenceError(f"{label} must be a safe relative POSIX path")
    candidate = sidecar_path.parent.joinpath(*pure.parts).resolve()
    base = sidecar_path.parent.resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise CameraCaptureEvidenceError(
            f"{label} escapes the sidecar directory"
        ) from error
    return candidate


def _coverage(*, scope: str, mount_id: str, note: str | None) -> dict[str, Any]:
    if scope not in {COVERAGE_PARTIAL, COVERAGE_FULL}:
        raise CameraCaptureEvidenceError("coverage_scope is invalid")
    mount = _require_text(mount_id, label="mount_id")
    if note is not None and (not isinstance(note, str) or not note):
        raise CameraCaptureEvidenceError("coverage note must be null or non-empty")
    full = scope == COVERAGE_FULL
    return {
        "scope": scope,
        "full_panel_visible": full,
        "full_panel_uncropped": full,
        "mount_id": mount,
        "note": note,
    }


def _assessment(
    *,
    verdict: str,
    confidence: str,
    limitations: Sequence[str],
    analysis_source: str,
    coverage_scope: str,
    capture_binding: str,
) -> dict[str, Any]:
    if verdict not in VERDICTS:
        raise CameraCaptureEvidenceError("automated assessment verdict is invalid")
    if confidence not in CONFIDENCES:
        raise CameraCaptureEvidenceError("assessment confidence is invalid")
    source = _require_text(analysis_source, label="assessment analysis_source")
    clean_limitations: list[str] = []
    for item in limitations:
        clean_limitations.append(_require_text(item, label="assessment limitation"))
    if coverage_scope == COVERAGE_PARTIAL:
        if confidence != "low" or verdict != "INCONCLUSIVE":
            raise CameraCaptureEvidenceError(
                "partial-panel evidence must be low-confidence INCONCLUSIVE"
            )
        if not clean_limitations:
            clean_limitations.append("full panel is not visible in the camera frame")
    if capture_binding in {BINDING_RETROSPECTIVE, BINDING_LOCKED_RETAINED}:
        if confidence != "low" or verdict != "INCONCLUSIVE":
            raise CameraCaptureEvidenceError(
                "retrospective evidence must be low-confidence INCONCLUSIVE"
            )
        if (
            capture_binding == BINDING_LOCKED_RETAINED
            and LOCKED_RETAINED_LIMITATION not in clean_limitations
        ):
            clean_limitations.append(LOCKED_RETAINED_LIMITATION)
        elif not clean_limitations:
            clean_limitations.append(
                "capture time and action continuity were not synchronized by this tool"
            )
    if confidence == "low" and verdict != "INCONCLUSIVE":
        raise CameraCaptureEvidenceError(
            "low-confidence automated assessment must be INCONCLUSIVE"
        )
    candidate_detected = (
        True if verdict == "PASS" else False if verdict == "FAIL" else None
    )
    if verdict == "INCONCLUSIVE" and source == "none":
        pass
    elif source == "none":
        raise CameraCaptureEvidenceError(
            "a conclusive automated assessment requires an analysis_source"
        )
    return {
        "verdict": verdict,
        "confidence": confidence,
        "analysis_source": source,
        "candidate_detected": candidate_detected,
        "limitations": clean_limitations,
    }


def _build_record(
    *,
    action_path: Path,
    action_payload: bytes,
    identity: Mapping[str, Any],
    photo_path: Path,
    sidecar_path: Path,
    photo_payload: bytes,
    decoded: Mapping[str, Any],
    capture_binding: str,
    captured_at: str,
    capture_timing: Mapping[str, Any],
    camera_id: str,
    camera_instance_id: str | None,
    camera_index: int | None,
    backend: str | None,
    requested_settings: Mapping[str, Any],
    effective_before: Mapping[str, Any],
    effective_after: Mapping[str, Any],
    warmup_frames_requested: int | None,
    warmup_frames_completed: int | None,
    read_failures: int | None,
    set_results: Mapping[str, Any] | None,
    coverage: Mapping[str, Any],
    assessment: Mapping[str, Any],
    photo_origin: str,
) -> dict[str, Any]:
    photo_sha256 = _sha256_bytes(photo_payload)
    capture_id = _canonical_sha256(
        {
            "action_id": identity["action_id"],
            "capture_binding": capture_binding,
            "captured_at": captured_at,
            "photo_sha256": photo_sha256,
        }
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "capture_id": capture_id,
        "capture_binding": capture_binding,
        "campaign_id": identity["campaign_id"],
        "test_id": identity["test_id"],
        "contract_id": identity["contract_id"],
        "firmware_sha256": identity["firmware_sha256"],
        "boot_nonce": identity["boot_nonce"],
        "ordinal": identity["ordinal"],
        "action_id": identity["action_id"],
        "descriptor_id": identity["descriptor_id"],
        "role": identity["role"],
        "frame_sha256": identity["frame_sha256"],
        "captured_at": captured_at,
        "capture_timing": dict(capture_timing),
        "action_result": {
            "path": _relative_evidence_path(
                action_path, sidecar_path=sidecar_path, label="action result"
            ),
            "bytes": len(action_payload),
            "file_sha256": _sha256_bytes(action_payload),
            "canonical_integrity_sha256": identity["canonical_integrity_sha256"],
            "outcome": identity["outcome"],
            "terminal_state": identity["terminal_state"],
            "visible_refreshes": identity["visible_refreshes"],
        },
        "camera": {
            "camera_id": _require_text(camera_id, label="camera_id"),
            "instance_id": camera_instance_id,
            "index": camera_index,
            "backend": backend,
            "requested_settings": dict(requested_settings),
            "effective_settings_before_frame": dict(effective_before),
            "effective_settings_after_frame": dict(effective_after),
            "warmup_frames_requested": warmup_frames_requested,
            "warmup_frames_completed": warmup_frames_completed,
            "read_failures": read_failures,
            **({"set_results": dict(set_results)} if set_results is not None else {}),
        },
        "photo": {
            "path": _relative_evidence_path(
                photo_path, sidecar_path=sidecar_path, label="photo"
            ),
            "origin": photo_origin,
            "bytes": len(photo_payload),
            "sha256": photo_sha256,
            **dict(decoded),
        },
        "coverage": dict(coverage),
        "automated_assessment": dict(assessment),
        "output_write_contract": "O_EXCL",
    }
    return _seal(record)


def capture(
    *,
    action_result_path: Path,
    photo_path: Path,
    sidecar_path: Path,
    camera_id: str,
    mount_id: str,
    coverage_scope: str,
    camera_instance_id: str | None = None,
    camera_index: int | None = None,
    requested_settings: Mapping[str, Any] | None = None,
    warmup_frames: int = 10,
    jpeg_quality: int = 95,
    automated_verdict: str = "INCONCLUSIVE",
    assessment_confidence: str = "low",
    limitations: Sequence[str] = (),
    analysis_source: str = "none",
    coverage_note: str | None = None,
    capture_backend: CaptureBackend | None = None,
    require_all_setting_writes: bool = False,
    _capture_binding: str = BINDING_LIVE,
    _device_resolver: DeviceResolver | None = None,
) -> dict[str, Any]:
    """Capture and seal exactly one persisted frame after a completed action.

    Warmup frames are discarded.  ``capture_backend`` and
    ``_device_resolver`` are paired test seams; the command-line live path
    exposes neither identity injection nor index fallback.  The production
    resolver authenticates one exact DirectShow USB alternative name before
    OpenCV is allowed to open its resolver-derived index.
    """

    action_result_path = Path(action_result_path)
    photo_path = Path(photo_path)
    sidecar_path = Path(sidecar_path)
    if photo_path.resolve() == sidecar_path.resolve():
        raise CameraCaptureEvidenceError("photo and sidecar paths must differ")
    if camera_index is not None and (type(camera_index) is not int or camera_index < 0):
        raise CameraCaptureEvidenceError(
            "camera_index must be null or a non-negative assertion"
        )
    if type(warmup_frames) is not int or not 0 <= warmup_frames <= 300:
        raise CameraCaptureEvidenceError("warmup_frames must be in range 0..300")
    if type(jpeg_quality) is not int or not 1 <= jpeg_quality <= 100:
        raise CameraCaptureEvidenceError("jpeg_quality must be in range 1..100")
    if type(require_all_setting_writes) is not bool:
        raise CameraCaptureEvidenceError("require_all_setting_writes must be a boolean")
    if _capture_binding not in {BINDING_LIVE, BINDING_LOCKED_RETAINED}:
        raise CameraCaptureEvidenceError("live-camera capture binding is invalid")
    settings = _normalise_requested_settings(requested_settings)
    if _capture_binding == BINDING_LOCKED_RETAINED:
        _validate_locked_retained_request(settings)
    coverage = _coverage(scope=coverage_scope, mount_id=mount_id, note=coverage_note)
    assessment = _assessment(
        verdict=automated_verdict,
        confidence=assessment_confidence,
        limitations=limitations,
        analysis_source=analysis_source,
        coverage_scope=coverage_scope,
        capture_binding=_capture_binding,
    )
    action_payload, _action_root, identity = _load_action_result(action_result_path)
    _relative_evidence_path(
        action_result_path, sidecar_path=sidecar_path, label="action result"
    )
    _relative_evidence_path(photo_path, sidecar_path=sidecar_path, label="photo")

    resolver = _device_resolver or _resolve_exact_mf1750_camera
    authenticated_device = _validated_authenticated_device(resolver())
    _validate_camera_claims(
        camera_id=camera_id,
        camera_instance_id=camera_instance_id,
        authenticated_device=authenticated_device,
    )
    selected_index = authenticated_device["directshow_index"]
    if camera_index is not None and camera_index != selected_index:
        raise CameraCaptureEvidenceError(
            "caller camera_index differs from the authenticated DirectShow target; "
            "index fallback is forbidden"
        )

    photo_fd: int | None = _reserve_output(photo_path, label="photo")
    try:
        sidecar_fd: int | None = _reserve_output(sidecar_path, label="capture sidecar")
    except Exception:
        _close_reserved(photo_fd)
        photo_fd = None
        photo_path.unlink(missing_ok=True)
        raise
    started_at = _now()
    started_at_utc = _utc_now()
    try:
        backend_function = capture_backend or _default_capture_backend
        photo_payload, diagnostics_root = backend_function(
            selected_index, settings, warmup_frames, jpeg_quality
        )
        if not isinstance(photo_payload, bytes) or not photo_payload:
            raise CameraCaptureEvidenceError(
                "capture backend did not return non-empty JPEG bytes"
            )
        diagnostics = _require_mapping(
            diagnostics_root, label="capture backend diagnostics"
        )
        backend_device = _validated_authenticated_device(
            diagnostics.get("authenticated_device")
        )
        if backend_device != authenticated_device:
            raise CameraCaptureEvidenceError(
                "capture backend device identity differs from pre-open authentication"
            )
        backend_name = _require_text(
            diagnostics.get("backend"), label="diagnostics.backend"
        )
        if backend_name.casefold() != "dshow":
            raise CameraCaptureEvidenceError(
                "capture backend is not authenticated DirectShow"
            )
        raw_set_results = diagnostics.get("set_results")
        set_results = (
            None
            if raw_set_results is None and _capture_binding == BINDING_LIVE
            else _validated_set_results(
                raw_set_results,
                settings=settings,
                label="diagnostics.set_results",
            )
        )
        if (
            _capture_binding == BINDING_LOCKED_RETAINED or require_all_setting_writes
        ) and (set_results is None or not all(set_results.values())):
            failed = (
                ["<missing set_results>"]
                if set_results is None
                else sorted(
                    field for field, success in set_results.items() if not success
                )
            )
            raise CameraCaptureEvidenceError(
                f"required camera setting writes failed: {failed!r}"
            )
        decoded = _decode_jpeg(photo_payload)
        captured_at = _require_text(
            diagnostics.get("frame_retrieved_at"),
            label="diagnostics.frame_retrieved_at",
        )
        frame_retrieved_at_utc = _require_text(
            diagnostics.get("frame_retrieved_at_utc"),
            label="diagnostics.frame_retrieved_at_utc",
        )
        completed_at = _now()
        completed_at_utc = _utc_now()
        effective_before = _require_mapping(
            diagnostics.get("effective_settings_before_frame"),
            label="diagnostics.effective_settings_before_frame",
        )
        effective_after = _require_mapping(
            diagnostics.get("effective_settings_after_frame"),
            label="diagnostics.effective_settings_after_frame",
        )
        completed_warmup = diagnostics.get("warmup_frames_completed")
        read_failures = diagnostics.get("read_failures")
        if type(completed_warmup) is not int or completed_warmup != warmup_frames:
            raise CameraCaptureEvidenceError(
                "capture backend did not complete the requested warmup frames"
            )
        if type(read_failures) is not int or read_failures < 0:
            raise CameraCaptureEvidenceError("capture backend read_failures is invalid")
        record = _build_record(
            action_path=action_result_path,
            action_payload=action_payload,
            identity=identity,
            photo_path=photo_path,
            sidecar_path=sidecar_path,
            photo_payload=photo_payload,
            decoded=decoded,
            capture_binding=_capture_binding,
            captured_at=captured_at,
            capture_timing={
                "started_at": started_at,
                "started_at_utc": started_at_utc,
                "frame_retrieved_at": captured_at,
                "frame_retrieved_at_utc": frame_retrieved_at_utc,
                "completed_at": completed_at,
                "completed_at_utc": completed_at_utc,
                "clock_source": "host_wall_clock",
                "hardware_frame_timestamp": None,
                "hardware_frame_timestamp_null_reason": (
                    "DirectShow/OpenCV backend exposes no authenticated hardware frame timestamp"
                ),
            },
            camera_id=TARGET_CAMERA_FRIENDLY_NAME,
            camera_instance_id=str(authenticated_device["alternative_name"]),
            camera_index=selected_index,
            backend=backend_name,
            requested_settings=settings,
            effective_before=effective_before,
            effective_after=effective_after,
            warmup_frames_requested=warmup_frames,
            warmup_frames_completed=completed_warmup,
            read_failures=read_failures,
            set_results=set_results,
            coverage=coverage,
            assessment=assessment,
            photo_origin="captured_by_tool",
        )
        assert photo_fd is not None
        _write_reserved(photo_fd, photo_payload)
        _close_reserved(photo_fd)
        photo_fd = None
        persisted = _read_stable_regular(photo_path, label="persisted photo")
        if persisted != photo_payload:
            raise CameraCaptureEvidenceError("persisted photo bytes differ")
        assert sidecar_fd is not None
        _write_reserved(
            sidecar_fd,
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n",
        )
        _close_reserved(sidecar_fd)
        sidecar_fd = None
    except Exception:
        _close_reserved(photo_fd)
        _close_reserved(sidecar_fd)
        photo_path.unlink(missing_ok=True)
        sidecar_path.unlink(missing_ok=True)
        raise
    return validate_capture_evidence(sidecar_path)


def capture_locked_retained(**kwargs: Any) -> dict[str, Any]:
    """Capture retained screen state without claiming historical action continuity.

    Unlike :func:`bind_existing`, this performs a live camera acquisition and
    therefore preserves every requested setting, every ``cap.set`` result,
    stable before/after effective readback, and the host acquisition time.
    """

    return capture(**kwargs, _capture_binding=BINDING_LOCKED_RETAINED)


def bind_existing(
    *,
    action_result_path: Path,
    photo_path: Path,
    sidecar_path: Path,
    camera_id: str,
    mount_id: str,
    coverage_scope: str,
    camera_instance_id: str | None = None,
    automated_verdict: str = "INCONCLUSIVE",
    assessment_confidence: str = "low",
    limitations: Sequence[str] = (),
    analysis_source: str = "none",
    coverage_note: str | None = None,
) -> dict[str, Any]:
    """Bind a pre-existing JPEG without claiming synchronized acquisition."""

    action_result_path = Path(action_result_path)
    photo_path = Path(photo_path)
    sidecar_path = Path(sidecar_path)
    if camera_instance_id is not None:
        _require_text(camera_instance_id, label="camera_instance_id")
    coverage = _coverage(scope=coverage_scope, mount_id=mount_id, note=coverage_note)
    assessment = _assessment(
        verdict=automated_verdict,
        confidence=assessment_confidence,
        limitations=limitations,
        analysis_source=analysis_source,
        coverage_scope=coverage_scope,
        capture_binding=BINDING_RETROSPECTIVE,
    )
    action_payload, _action_root, identity = _load_action_result(action_result_path)
    photo_payload = _read_stable_regular(photo_path, label="existing photo")
    decoded = _decode_jpeg(photo_payload)
    _relative_evidence_path(
        action_result_path, sidecar_path=sidecar_path, label="action result"
    )
    _relative_evidence_path(photo_path, sidecar_path=sidecar_path, label="photo")
    try:
        captured_at = (
            datetime.fromtimestamp(photo_path.stat().st_mtime, tz=timezone.utc)
            .astimezone()
            .isoformat(timespec="milliseconds")
        )
    except OSError as error:
        raise CameraCaptureEvidenceError(
            f"cannot read existing photo timestamp: {error}"
        ) from error
    record = _build_record(
        action_path=action_result_path,
        action_payload=action_payload,
        identity=identity,
        photo_path=photo_path,
        sidecar_path=sidecar_path,
        photo_payload=photo_payload,
        decoded=decoded,
        capture_binding=BINDING_RETROSPECTIVE,
        captured_at=captured_at,
        capture_timing={
            "started_at": None,
            "started_at_utc": None,
            "frame_retrieved_at": captured_at,
            "frame_retrieved_at_utc": None,
            "completed_at": _now(),
            "completed_at_utc": _utc_now(),
            "clock_source": "filesystem_mtime_untrusted",
            "hardware_frame_timestamp": None,
            "hardware_frame_timestamp_null_reason": (
                "pre-existing JPEG has no authenticated acquisition timestamp"
            ),
        },
        camera_id=camera_id,
        camera_instance_id=camera_instance_id,
        camera_index=None,
        backend=None,
        requested_settings={},
        effective_before={},
        effective_after={},
        warmup_frames_requested=None,
        warmup_frames_completed=None,
        read_failures=None,
        set_results=None,
        coverage=coverage,
        assessment=assessment,
        photo_origin="preexisting_read_only",
    )
    sidecar_fd: int | None = _reserve_output(sidecar_path, label="capture sidecar")
    try:
        assert sidecar_fd is not None
        _write_reserved(
            sidecar_fd,
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ).encode("utf-8")
            + b"\n",
        )
        _close_reserved(sidecar_fd)
        sidecar_fd = None
    except Exception:
        _close_reserved(sidecar_fd)
        sidecar_path.unlink(missing_ok=True)
        raise
    return validate_capture_evidence(sidecar_path)


def validate_capture_evidence(sidecar_path: Path) -> dict[str, Any]:
    """Deep-validate one sidecar, its action JSON, and its exact JPEG bytes."""

    sidecar_path = Path(sidecar_path)
    _payload, root = _load_strict_json(sidecar_path, label="capture sidecar")
    expected_keys = {
        "schema_version",
        "kind",
        "capture_id",
        "capture_binding",
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "boot_nonce",
        "ordinal",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
        "captured_at",
        "capture_timing",
        "action_result",
        "camera",
        "photo",
        "coverage",
        "automated_assessment",
        "output_write_contract",
        "integrity",
    }
    if set(root) != expected_keys:
        raise CameraCaptureEvidenceError("capture sidecar top-level keys differ")
    schema_version = root.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS or root.get("kind") != KIND:
        raise CameraCaptureEvidenceError("capture sidecar schema identity differs")
    _verify_integrity(root, label="capture sidecar")
    binding = root.get("capture_binding")
    if binding not in {
        BINDING_LIVE,
        BINDING_RETROSPECTIVE,
        BINDING_LOCKED_RETAINED,
    }:
        raise CameraCaptureEvidenceError("capture binding is invalid")
    if root.get("output_write_contract") != "O_EXCL":
        raise CameraCaptureEvidenceError("output write contract differs")
    captured_at = _require_text(root.get("captured_at"), label="captured_at")

    action_record = _require_mapping(root.get("action_result"), label="action_result")
    expected_action_keys = {
        "path",
        "bytes",
        "file_sha256",
        "canonical_integrity_sha256",
        "outcome",
        "terminal_state",
        "visible_refreshes",
    }
    if set(action_record) != expected_action_keys:
        raise CameraCaptureEvidenceError("action_result keys differ")
    action_path = _resolve_evidence_path(
        action_record.get("path"), sidecar_path=sidecar_path, label="action_result.path"
    )
    action_payload, _action_root, identity = _load_action_result(action_path)
    if action_record.get("bytes") != len(action_payload):
        raise CameraCaptureEvidenceError("action result byte count differs")
    if action_record.get("file_sha256") != _sha256_bytes(action_payload):
        raise CameraCaptureEvidenceError("action result file SHA-256 differs")
    if (
        action_record.get("canonical_integrity_sha256")
        != identity["canonical_integrity_sha256"]
        or action_record.get("outcome") != identity["outcome"]
        or action_record.get("terminal_state") != identity["terminal_state"]
        or action_record.get("visible_refreshes") != identity["visible_refreshes"]
    ):
        raise CameraCaptureEvidenceError("action result binding fields differ")
    for field in (
        "campaign_id",
        "test_id",
        "contract_id",
        "firmware_sha256",
        "boot_nonce",
        "ordinal",
        "action_id",
        "descriptor_id",
        "role",
        "frame_sha256",
    ):
        if root.get(field) != identity[field]:
            raise CameraCaptureEvidenceError(f"sidecar {field} differs from action")

    camera = _require_mapping(root.get("camera"), label="camera")
    expected_camera_keys = {
        "camera_id",
        "instance_id",
        "index",
        "backend",
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
        "warmup_frames_requested",
        "warmup_frames_completed",
        "read_failures",
    }
    camera_keys = frozenset(camera)
    if camera_keys not in {
        frozenset(expected_camera_keys),
        frozenset(expected_camera_keys | {"set_results"}),
    }:
        raise CameraCaptureEvidenceError("camera keys differ")
    camera_id = _require_text(camera.get("camera_id"), label="camera.camera_id")
    for field in (
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
    ):
        _require_mapping(camera.get(field), label=f"camera.{field}")
    requested_settings = _require_mapping(
        camera.get("requested_settings"), label="camera.requested_settings"
    )
    validated_set_results: dict[str, bool] | None = None
    if "set_results" in camera:
        validated_set_results = _validated_set_results(
            camera.get("set_results"),
            settings=requested_settings,
            label="camera.set_results",
        )
    elif binding == BINDING_LOCKED_RETAINED:
        raise CameraCaptureEvidenceError(
            "locked-retained capture is missing camera.set_results"
        )
    if binding == BINDING_LOCKED_RETAINED:
        _require_text(camera.get("instance_id"), label="camera.instance_id")
        _validate_locked_retained_request(requested_settings)
        assert validated_set_results is not None
        if not all(validated_set_results.values()):
            failed = sorted(
                field for field, success in validated_set_results.items() if not success
            )
            raise CameraCaptureEvidenceError(
                f"locked-retained camera setting writes failed: {failed!r}"
            )
    if binding in {BINDING_LIVE, BINDING_LOCKED_RETAINED}:
        if schema_version == SCHEMA_VERSION:
            if camera_id != TARGET_CAMERA_FRIENDLY_NAME:
                raise CameraCaptureEvidenceError(
                    "live evidence camera_id is not the MF1750 48MP target"
                )
            camera_instance = _require_text(
                camera.get("instance_id"), label="camera.instance_id"
            )
            if not _alternative_has_usb_id(
                camera_instance, vid="32E4", pid="4801"
            ) or _alternative_has_usb_id(camera_instance, vid="1BCF", pid="0B15"):
                raise CameraCaptureEvidenceError(
                    "live evidence camera instance is not VID_32E4:PID_4801"
                )
            _pnp_instance_from_alternative_name(camera_instance)
        if type(camera.get("index")) is not int or camera["index"] < 0:
            raise CameraCaptureEvidenceError("live camera index is invalid")
        backend = _require_text(camera.get("backend"), label="camera.backend")
        if schema_version == SCHEMA_VERSION and backend.casefold() != "dshow":
            raise CameraCaptureEvidenceError("live camera backend is not DirectShow")
        for field in (
            "warmup_frames_requested",
            "warmup_frames_completed",
            "read_failures",
        ):
            if type(camera.get(field)) is not int or camera[field] < 0:
                raise CameraCaptureEvidenceError(f"camera.{field} is invalid")
        if camera["warmup_frames_requested"] != camera["warmup_frames_completed"]:
            raise CameraCaptureEvidenceError("camera warmup count differs")

    photo = _require_mapping(root.get("photo"), label="photo")
    expected_photo_keys = {
        "path",
        "origin",
        "bytes",
        "sha256",
        "decoded_format",
        "width",
        "height",
        "mode",
        "quality_metrics",
    }
    if set(photo) != expected_photo_keys:
        raise CameraCaptureEvidenceError("photo keys differ")
    expected_origin = (
        "captured_by_tool"
        if binding in {BINDING_LIVE, BINDING_LOCKED_RETAINED}
        else "preexisting_read_only"
    )
    if photo.get("origin") != expected_origin:
        raise CameraCaptureEvidenceError("photo origin differs from binding")
    photo_path = _resolve_evidence_path(
        photo.get("path"), sidecar_path=sidecar_path, label="photo.path"
    )
    photo_payload = _read_stable_regular(photo_path, label="bound photo")
    if photo.get("bytes") != len(photo_payload):
        raise CameraCaptureEvidenceError("photo byte count differs")
    if photo.get("sha256") != _sha256_bytes(photo_payload):
        raise CameraCaptureEvidenceError("photo SHA-256 differs")
    decoded = _decode_jpeg(photo_payload)
    for field in (
        "decoded_format",
        "width",
        "height",
        "mode",
        "quality_metrics",
    ):
        if photo.get(field) != decoded[field]:
            raise CameraCaptureEvidenceError(f"decoded photo {field} differs")

    coverage = _require_mapping(root.get("coverage"), label="coverage")
    if set(coverage) != {
        "scope",
        "full_panel_visible",
        "full_panel_uncropped",
        "mount_id",
        "note",
    }:
        raise CameraCaptureEvidenceError("coverage keys differ")
    expected_coverage = _coverage(
        scope=coverage.get("scope"),
        mount_id=coverage.get("mount_id"),
        note=coverage.get("note"),
    )
    if dict(coverage) != expected_coverage:
        raise CameraCaptureEvidenceError("coverage contract differs")
    assessment = _require_mapping(
        root.get("automated_assessment"), label="automated_assessment"
    )
    if set(assessment) != {
        "verdict",
        "confidence",
        "analysis_source",
        "candidate_detected",
        "limitations",
    }:
        raise CameraCaptureEvidenceError("automated_assessment keys differ")
    limitations = assessment.get("limitations")
    if not isinstance(limitations, list):
        raise CameraCaptureEvidenceError("assessment limitations must be an array")
    expected_assessment = _assessment(
        verdict=assessment.get("verdict"),
        confidence=assessment.get("confidence"),
        limitations=limitations,
        analysis_source=assessment.get("analysis_source"),
        coverage_scope=coverage["scope"],
        capture_binding=binding,
    )
    if dict(assessment) != expected_assessment:
        raise CameraCaptureEvidenceError("automated assessment contract differs")

    timing = _require_mapping(root.get("capture_timing"), label="capture_timing")
    if set(timing) != {
        "started_at",
        "started_at_utc",
        "frame_retrieved_at",
        "frame_retrieved_at_utc",
        "completed_at",
        "completed_at_utc",
        "clock_source",
        "hardware_frame_timestamp",
        "hardware_frame_timestamp_null_reason",
    }:
        raise CameraCaptureEvidenceError("capture_timing keys differ")
    if timing.get("frame_retrieved_at") != captured_at:
        raise CameraCaptureEvidenceError("captured_at and frame retrieval time differ")
    expected_clock = (
        "host_wall_clock"
        if binding in {BINDING_LIVE, BINDING_LOCKED_RETAINED}
        else "filesystem_mtime_untrusted"
    )
    if timing.get("clock_source") != expected_clock:
        raise CameraCaptureEvidenceError("capture clock source differs from binding")
    if timing.get("hardware_frame_timestamp") is not None:
        raise CameraCaptureEvidenceError("hardware frame timestamp must be null")
    _require_text(
        timing.get("hardware_frame_timestamp_null_reason"),
        label="hardware frame timestamp null reason",
    )

    capture_id = _canonical_sha256(
        {
            "action_id": identity["action_id"],
            "capture_binding": binding,
            "captured_at": captured_at,
            "photo_sha256": photo["sha256"],
        }
    )
    if root.get("capture_id") != capture_id:
        raise CameraCaptureEvidenceError("capture_id differs")
    return dict(root)


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--action-result", type=Path, required=True)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--camera-id", default=TARGET_CAMERA_LOGICAL_ID)
    parser.add_argument("--camera-instance-id")
    parser.add_argument("--mount-id", required=True)
    parser.add_argument(
        "--coverage", choices=(COVERAGE_PARTIAL, COVERAGE_FULL), required=True
    )
    parser.add_argument("--coverage-note")
    parser.add_argument(
        "--assessment", choices=tuple(sorted(VERDICTS)), default="INCONCLUSIVE"
    )
    parser.add_argument(
        "--confidence", choices=tuple(sorted(CONFIDENCES)), default="low"
    )
    parser.add_argument("--limitation", action="append", default=[])
    parser.add_argument("--analysis-source", default="none")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)

    def add_live_camera_arguments(command: argparse.ArgumentParser) -> None:
        _add_common_arguments(command)
        command.add_argument(
            "--camera-index",
            type=int,
            help=(
                "optional fail-closed assertion only; the target index is always "
                "derived from its exact VID_32E4:PID_4801 DirectShow path"
            ),
        )
        command.add_argument("--width", type=int, default=1920)
        command.add_argument("--height", type=int, default=1080)
        command.add_argument("--fps", type=float, default=30.0)
        command.add_argument("--warmup-frames", type=int, default=10)
        command.add_argument("--jpeg-quality", type=int, default=95)
        command.add_argument(
            "--require-all-setting-writes",
            action="store_true",
            help="fail before persistence if any requested DirectShow property write fails",
        )
        command.add_argument("--autofocus", type=float)
        command.add_argument("--focus", type=float)
        command.add_argument("--auto-exposure", type=float)
        command.add_argument("--exposure", type=float)
        command.add_argument("--auto-white-balance", type=float)
        command.add_argument("--white-balance-temperature", type=float)

    capture_parser = commands.add_parser("capture", help="capture one live frame")
    add_live_camera_arguments(capture_parser)
    retained_parser = commands.add_parser(
        "capture-retained",
        help="capture retained screen state without historical action continuity claim",
    )
    add_live_camera_arguments(retained_parser)

    bind_parser = commands.add_parser(
        "bind-existing", help="seal a pre-existing JPEG as retrospective evidence"
    )
    _add_common_arguments(bind_parser)

    validate_parser = commands.add_parser("validate", help="deep-validate a sidecar")
    validate_parser.add_argument("sidecar", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_capture_evidence(args.sidecar)
        else:
            common = {
                "action_result_path": args.action_result,
                "photo_path": args.photo,
                "sidecar_path": args.sidecar,
                "camera_id": args.camera_id,
                "camera_instance_id": args.camera_instance_id,
                "mount_id": args.mount_id,
                "coverage_scope": args.coverage,
                "coverage_note": args.coverage_note,
                "automated_verdict": args.assessment,
                "assessment_confidence": args.confidence,
                "limitations": args.limitation,
                "analysis_source": args.analysis_source,
            }
            if args.command in {"capture", "capture-retained"}:
                settings = {
                    "frame_width": args.width,
                    "frame_height": args.height,
                    "fps": args.fps,
                    "autofocus": args.autofocus,
                    "focus": args.focus,
                    "auto_exposure": args.auto_exposure,
                    "exposure": args.exposure,
                    "auto_white_balance": args.auto_white_balance,
                    "white_balance_temperature": args.white_balance_temperature,
                }
                capture_function = (
                    capture if args.command == "capture" else capture_locked_retained
                )
                result = capture_function(
                    **common,
                    camera_index=args.camera_index,
                    requested_settings=settings,
                    warmup_frames=args.warmup_frames,
                    jpeg_quality=args.jpeg_quality,
                    require_all_setting_writes=args.require_all_setting_writes,
                )
            else:
                result = bind_existing(**common)
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
    except CameraCaptureEvidenceError as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "mf1750-camera-capture-evidence-error",
                    "valid": False,
                    "error": str(error),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=os.sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
