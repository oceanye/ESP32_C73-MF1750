#!/usr/bin/env python3
"""Fresh factory-OTP white containment runner for LUMA-GRAY-V1."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_runtime_lut_luma_gray_v1_white_containment_pack as pack  # noqa: E402

_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_hue_brightness_redpink_v2_white_containment_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_luma_gray_v1_containment_host", _PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reviewed containment mechanics: {_PATH}")
host = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(host)

# Rebind the private mature host to this fresh identity only.
host.pack = pack
host.REPORT = pack.build_report(verify_artifacts=False)
host._base.pack = pack
host._base.REPORT = host.REPORT
host._base.ACTION = host.REPORT["action"]
host._base.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
host.ACTION = host._base.ACTION
host.ENDPOINTS = host._base.ENDPOINTS
host.DEFAULT_CLAIMS = (
    REPO_ROOT / ".test-output/hardware/.mf1750_luma_gray_v1_white_containment_claims"
)
host.DEFAULT_OUTPUT = (
    REPO_ROOT / ".test-output/hardware/MF1750_LUMA_GRAY_V1_WHITE_CONTAINMENT"
)
host.DIAGNOSTIC_OUTPUT = host.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
host.ACTION_OUTPUT = host.DEFAULT_OUTPUT / "action-01-factory-otp-white.json"
host.SOURCE_MAIN_BINDING = {
    "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
    "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
    "source_main_contract_exact_binding": True,
    "source_main_device_enforced_same_boot": True,
    "source_main_direct_exact_post_resume_after_reboot": False,
    "source_main_nvs_boot_key": pack.source_pack.NVS_BOOT_KEY,
    "main_campaign_resume_after_containment": False,
    "containment_terminal_for_source_campaign": True,
    "source_main_interrupted_or_completed_branch": True,
    "source_main_resume_forbidden_after_containment": True,
    "relay_off_required_before_containment": True,
}


def dry_validate() -> dict[str, Any]:
    for path, size, digest in (
        (pack.FIRMWARE_BIN, pack.FIRMWARE_BIN_BYTES, pack.FIRMWARE_BIN_SHA256),
        (pack.FIRMWARE_ELF, pack.FIRMWARE_ELF_BYTES, pack.FIRMWARE_ELF_SHA256),
    ):
        import hashlib

        data = Path(path).read_bytes()
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise host.ContainmentError(
                f"reviewed containment artifact differs: {path}"
            )
    return {
        "kind": "mf1750-luma-gray-v1-white-containment-dry-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "hardware_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "source_campaign_id": pack.SOURCE_CAMPAIGN_ID,
        "source_main_contract_id": pack.SOURCE_MAIN_CONTRACT_ID,
        "contract_id": pack.CONTRACT_ID,
        "descriptor_id": pack.DESCRIPTOR_ID,
        "action_id": pack.ACTION_ID,
        "firmware": {
            "bytes": pack.FIRMWARE_BIN_BYTES,
            "sha256": pack.FIRMWARE_BIN_SHA256,
        },
        "elf": {"bytes": pack.FIRMWARE_ELF_BYTES, "sha256": pack.FIRMWARE_ELF_SHA256},
        "main_campaign_resume_after_containment": False,
    }


def describe() -> dict[str, Any]:
    return {
        **dry_validate(),
        "contract": host.REPORT["contract"],
        "action": host.REPORT["action"],
        "source_main_binding": host.SOURCE_MAIN_BINDING,
        "endpoints": host.ENDPOINTS,
        "claims_root": str(host.DEFAULT_CLAIMS),
        "output_root": str(host.DEFAULT_OUTPUT),
        "automatic_execution": False,
        "automatic_chaining": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "one_visible_refresh": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["dry-validate"]:
        print(json.dumps(dry_validate(), sort_keys=True))
        return 0
    if argv == ["describe"]:
        print(json.dumps(describe(), sort_keys=True))
        return 0
    # The mature CLI provides describe, diagnose-j2-off, run and salvage.
    return host.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
