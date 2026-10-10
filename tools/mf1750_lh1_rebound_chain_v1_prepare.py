"""Prepare an offline LH1 chain rebound to the completed fault-white R4.

This wrapper intentionally never opens a device, relay, camera, or network
socket.  It reuses the sealed LH1 frame/profile construction while changing
the source anchor and persistent namespace.  The package remains
``live_ready=false`` until a separate native audit and host runner review pass.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import hashlib
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools/mf1750_lightness_history_firmware.py"
OUT = ROOT / ".test-output/offline/LH1_REBOUND_20260914_R4"
WHITE = ROOT / ".test-output/hardware/LH1_FAULT_REENTRY_20260914_V1/WHITE_ONCE_V1"

NEW_NAMESPACE = "lhist_lh1_rebound_v1"
NEW_CURSOR = "cur_lh1_rebound"
NEW_BOOT = "boot_lh1_rebound"
OLD_NAMESPACE = "lhist_v1"
OLD_CURSOR = "cur_lh1"
OLD_BOOT = "boot_lh1"


def _load():
    spec = importlib.util.spec_from_file_location("_lh1_rebound_base", SRC)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load LH1 generator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _binding(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path.resolve()), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _seal(value: dict) -> dict:
    body = dict(value)
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    body["integrity"] = {"algorithm": "sha256-canonical-json-without-integrity", "sha256": hashlib.sha256(canonical).hexdigest()}
    return body


def prepare(out: Path = OUT) -> dict:
    if out.exists():
        raise FileExistsError(out)
    base = _load()
    close = json.loads((WHITE / "close-review-v5.json").read_text(encoding="utf-8"))
    result = json.loads((WHITE / "live-reopen-v2/result.json").read_text(encoding="utf-8"))
    flash = json.loads((WHITE / "app-flash-raw.json").read_text(encoding="utf-8"))
    base.SOURCE_WHITE = {
        "campaign_id": result["terminal_report"]["campaign_id"],
        "action_id": result["terminal_report"]["action_id"],
        "contract_id": result["terminal_report"]["contract_id"],
        "firmware_sha256": flash["binary"]["observed_sha256"],
        "nvs_namespace": "lh1srcw_v1",
        "nvs_key": "used_lh1sw1",
        "complete_cursor": 2,
        "terminal_evidence": base.bind(WHITE / "live-reopen-v2/result.json"),
        "clean_white_review": base.bind(WHITE / "postwhite-optical-review-v4.json"),
        "close_review": base.bind(WHITE / "close-review-v5.json"),
        "nvs_is_not_optical_or_electrical_proof": True,
    }
    base.CAMPAIGN = "EC5_LIGHTNESS_HISTORY_LH1_REBOUND_V1_20260914"
    base.BUILD_TAG = "MF1750_EC5_LIGHTNESS_HISTORY_LH1_REBOUND_V1_2026-09-14"
    base.PREFIX = "ec5_lightness_lh1_rebound_v1"
    base.MACRO = "MF1750_LIGHTNESS_LH1_REBOUND_V1_BUILD"
    base.NAMESPACE = NEW_NAMESPACE
    base.prepare(out)

    contract_path = out / "contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["nvs"] = {"namespace": NEW_NAMESPACE, "cursor": NEW_CURSOR, "boot": NEW_BOOT}
    contract["old_fault_preservation"] = {"namespace": OLD_NAMESPACE, "cursor": OLD_CURSOR, "boot": OLD_BOOT, "must_remain_untouched": True, "expected_cursor_raw": 770}
    contract["source_white"] = base.SOURCE_WHITE
    contract["live_ready"] = False
    contract["rebound_source_anchor"] = _binding(WHITE / "close-review-v5.json")
    contract_body = dict(contract)
    contract_body.pop("integrity", None)
    contract_body["contract_id"] = hashlib.sha256(json.dumps({k: v for k, v in contract_body.items() if k != "contract_id"}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    contract_path.write_text(json.dumps(_seal(contract_body), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    sources = list((out / "generated").glob("*.cpp")) + list((out / "generated").glob("*.inc")) + list((out / "generated").glob("*.hpp"))
    for source in sources:
        text = source.read_text(encoding="utf-8")
        text = text.replace("p2catwsv1", "lh1srcw_v1").replace("used_p2cw1", "used_lh1sw1")
        text = text.replace("ec5_lightness_history_v1_identity.inc", "ec5_lightness_lh1_rebound_v1_identity.inc")
        text = text.replace("mf1750_lightness_history_v1", "lhist_lh1_rebound_v1")
        text = re.sub(r'kContractId="[0-9a-f]{64}"', f'kContractId="{contract_body["contract_id"]}"', text)
        text = re.sub(r'CONTRACT=[0-9a-f]{64}', f'CONTRACT={contract_body["contract_id"]}', text)
        text = text.replace('"lhist_v1"', f'"{NEW_NAMESPACE}"').replace('"cur_lh1"', f'"{NEW_CURSOR}"').replace('"boot_lh1"', f'"{NEW_BOOT}"')
        source.write_text(text, encoding="utf-8")

    # Rebuild the manifest after the deliberate source/contract rebinding.
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("integrity", None)
    manifest["contract_id"] = contract_body["contract_id"]
    manifest["live_ready"] = False
    manifest["rebound_source_anchor"] = _binding(WHITE / "close-review-v5.json")
    manifest["outputs"] = [_binding(path) for path in sorted(out.rglob("*")) if path.is_file() and path.name != "manifest.json"]
    manifest_path.write_text(json.dumps(_seal(manifest), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"result": "PASS_OFFLINE_REBOUND_PREPARED", "output": str(out), "contract_id": contract_body["contract_id"], "live_ready": False, "hardware_accessed": False, "network_accessed": False, "old_fault_preserved": True}


if __name__ == "__main__":
    print(json.dumps(prepare(), ensure_ascii=False, sort_keys=True))
