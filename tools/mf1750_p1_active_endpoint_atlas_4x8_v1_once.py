#!/usr/bin/env python3
"""Fail-closed host for the fresh P1 active-profile endpoint atlas.

The host performs no flash, reset, relay, camera, or automatic containment
operation.  One invocation can consume exactly one immutable full-screen
action.  Before any device GET, permanent claim, ARM, or EXECUTE it verifies:

* the reviewed BIN and ELF;
* the exact retained V3 factory-white action, clean-white review, and relay-OFF
  receipt (plus the white successor's source-terminal gate);
* a fresh, single-candidate, exact IPv4-to-MAC binding;
* a same-boot J2-OFF diagnostic; and
* explicit live J2-ON and no-intervening-visible-refresh confirmations.

The only visible action is a complete active/active L535 4x8 endpoint atlas.
There is no source/middle history, target repeat, partial refresh, HOLD, retry,
recovery, or automatic white successor in this campaign.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import ipaddress
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import mf1750_p1_active_endpoint_atlas_4x8_v1_pack as pack  # noqa: E402


# Load a private copy of the reviewed BUSY-qualified one-shot mechanics.  The
# private import avoids rewriting the public globals of any predecessor runner.
_HOST_PATH = Path(__file__).with_name(
    "mf1750_runtime_lut_partial_hold_repeat_ptlw_v3_once.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_p1_active_endpoint_atlas_4x8_v1_private_host", _HOST_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load reviewed one-shot mechanics: {_HOST_PATH}")
host = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(host)
v1 = host.v1
base = host.base


REPORT = pack.build_report()
host.pack = pack
host.REPORT = REPORT
base.pack = pack
base._REPORT = REPORT
base._BLOCKING_REFRESH_POLL_FLOOR_SECONDS = 65.0


ARTIFACTS = pack.ARTIFACTS
BUILD_DIR = pack.BUILD_DIR

base.runner.BUILD_TAG = pack.BUILD_TAG
base.runner.TEST_ID = pack.TEST_ID
base.runner.CAMPAIGN_ID = pack.CAMPAIGN_ID
base.runner.DEVICE_API_VERSION = pack.DEVICE_API_VERSION
base.runner.IDENTITY_REVISION = pack.IDENTITY_REVISION
base.runner.CONTRACT_ID = REPORT["contract_id"]
base.runner.CLASSIFICATION = pack.CLASSIFICATION
base.runner.DEVICE_KIND_PREFIX = "mf1750-ec5-p1-active-endpoint-atlas-4x8-v1"
base.runner.EVIDENCE_KIND_PREFIX = "mf1750-ec5-p1-active-endpoint-atlas-4x8-v1"
base.runner.NVS_NAMESPACE = pack.NVS_NAMESPACE
base.runner.NVS_KEY = pack.NVS_KEY
base.runner.FIRMWARE_SHA256 = ARTIFACTS["firmware.bin"]["sha256"]
base.runner.FIRMWARE_BYTES = ARTIFACTS["firmware.bin"]["bytes"]
base.runner.ENDPOINTS = {
    name: f"{pack.BASE_ROUTE}/{name}"
    for name in ("version", "manifest", "status", "report", "arm", "execute")
}
base.runner.ARM_INTENT = (
    "ARM_ONE_FIXED_P1_ACTIVE_ENDPOINT_ATLAS_NOT_HARDWARE_AUTHORIZATION"
)
base.runner.EXECUTE_INTENT = "EXECUTE_ONE_ARMED_P1_ACTIVE_ENDPOINT_ATLAS_ONCE"


def _runner_actions() -> tuple[dict[str, Any], ...]:
    """Return the exact action surface serialized by the P1 firmware."""

    generic = deepcopy(base._actions())
    sources = REPORT["contract"]["actions"]
    if len(generic) != 1 or len(sources) != 1:
        raise base.runner.RecheckError(
            "P1 action table must contain exactly one action"
        )
    for action, source in zip(generic, sources, strict=True):
        action["palette_source"] = source["palette_source"]
        action["global_header"] = source["global_header"]
        action["profile_id"] = source["profile_id"]
        action["global_tuple_id"] = source["global_tuple_id"]
        action["waveform_binding"] = deepcopy(source["waveform_binding"])
        action["boot_admission"] = deepcopy(source["boot_admission"])
        action["driver_entry"] = "epdDisplayCompiledChromaGrid"
    return tuple(generic)


base.runner.ACTIONS = _runner_actions()
base.runner.DESCRIPTOR_IDS = tuple(
    item["descriptor_id"] for item in base.runner.ACTIONS
)
base.runner.ACTION_IDS = tuple(item["action_id"] for item in base.runner.ACTIONS)
base.runner.DEFAULT_CLAIMS = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / ".mf1750_p1_active_endpoint_atlas_4x8_v1_claims"
)
base.runner.DEFAULT_OUTPUT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_P1_COMPLETE_ACTIVE_ENDPOINT_20260901_V1"
)
DIAGNOSTIC_OUTPUT = base.runner.DEFAULT_OUTPUT / "j2-off-diagnostic.json"
RUN_ADMISSION_OUTPUT = base.runner.DEFAULT_OUTPUT / "action-01-live-admission.json"
ACTION_OUTPUTS = {
    1: base.runner.DEFAULT_OUTPUT
    / "action-01-active-complete-position-balanced-4x8-endpoint-atlas.json"
}


EXPECTED_DEVICE_IPV4 = "192.168.1.11"
EXPECTED_DEVICE_MAC = "A4-CB-8F-D9-FC-D4"
SOURCE_ROOT = (
    REPO_ROOT
    / ".test-output"
    / "hardware"
    / "MF1750_STABLE_CODE0_LUMA_LATIN_V3_WHITE_SUCCESSOR_20260901_V1"
)
SOURCE_BINDINGS: dict[str, dict[str, Any]] = {
    "source_terminal_gate": {
        "path": "source-terminal-gate.json",
        "bytes": 2_119,
        "file_sha256": (
            "d86e2ce71523d12b0b42da9048d2a7bfd3bd8151101bffcb2dd2b7ddc0c50a5a"
        ),
        "canonical_sha256": (
            "c7bfc6caab657e2bbda9286a83d712b0223486aac741e4263d0e77f2464ea76f"
        ),
    },
    "white_action": {
        "path": "action-01-factory-otp-white.json",
        "bytes": 36_987,
        "file_sha256": (
            "9ebc3ca4f32ceba8cbb356aece938d28e922e016f875ab10aa082338993b509b"
        ),
        "canonical_sha256": (
            "555b94739704096bde278ee3e0c3eb5ac901ccc7d390481f725093467a6c414b"
        ),
    },
    "clean_white_review": {
        "path": (
            "post-white-retained-camera-attempt-01-exposure-m4.clean-white-review.json"
        ),
        "bytes": 4_367,
        "file_sha256": (
            "50ce755e3ed04790819c326bbbb1e6a2fdc3c6b587899f02b00da588d5e2d625"
        ),
        "canonical_sha256": (
            "7de626ce68c5dc2952a0c17cdc41cd59ced97191f14344713f71bcb6b4a5ab40"
        ),
    },
    "relay_off": {
        "path": "relay-post-white-off.json",
        "bytes": 1_803,
        "file_sha256": (
            "1fa84d45b7374fce680bdadcde0edb2142adfa408b5511edfa75dd20f0b09626"
        ),
        "canonical_sha256": (
            "5ebe1472699eccfd53b4b7013f67de6e818734342d6a4f680b148f7a5ce19400"
        ),
    },
}
SOURCE_WHITE_CAMPAIGN_ID = (
    "EC5_STABLE_CODE0_LUMA_LATIN_V3_FACTORY_OTP_WHITE_SUCCESSOR_V1"
)
SOURCE_WHITE_CONTRACT_ID = (
    "787c2898a841913ac009e0284a1f3680403cc77a05ec700cb17f1a4a08152377"
)
SOURCE_WHITE_DESCRIPTOR_ID = (
    "8e74da212546b89bfdeba9e6638b30a8d4aa75114d394387c3d2a3b73f8276e0"
)
SOURCE_WHITE_ACTION_ID = (
    "7d68be7197e6af89e6a7d500010160b6c11343ae5f92d990e1b982275fb5245f"
)
SOURCE_CAPTURE_ID = "85d78b0fbcf78162e5c9a6a0c618e2ae8f9f815ade2e61d4ff481b80cef80e34"
SOURCE_REVIEW_ID = "b0a62b0c7dbf178fa6a2763d0bebf417b61dda6bd86bab701c84f658ae2ba96f"


_MAX_JSON_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NONCE = re.compile(r"^[0-9a-f]{16}$")
_FRESH_NEIGHBOUR_STATES = frozenset({"REACHABLE", "DELAY", "PROBE", "PERMANENT"})
_BASELINE_ROLE = (
    "EXTERNAL_FRESH_FACTORY_OTP_WHITE_BEFORE_AND_INDEPENDENT_SUCCESSOR_AFTER_REQUIRED"
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _repo_relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as error:
        raise base.runner.RecheckError(
            f"P1 evidence path must remain inside the repository: {path}"
        ) from error


def _fixed_path(value: Path, expected: Path, *, label: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    if candidate.resolve() != expected.resolve():
        raise base.runner.RecheckError(
            f"{label} is fixed at {_repo_relative(expected)}"
        )
    return expected.resolve()


def _read_exact_json(
    path: Path,
    *,
    byte_count: int | None = None,
    file_sha256: str | None = None,
    canonical_sha256: str | None = None,
    label: str,
) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise base.runner.RecheckError(f"{label} missing or unsafe: {path}")
    payload = path.read_bytes()
    if byte_count is not None and len(payload) != byte_count:
        raise base.runner.RecheckError(f"{label} byte count differs")
    digest = hashlib.sha256(payload).hexdigest()
    if file_sha256 is not None and digest != file_sha256:
        raise base.runner.RecheckError(f"{label} file SHA-256 differs")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise base.runner.RecheckError(f"{label} root differs")
    if canonical_sha256 is not None:
        body = deepcopy(value)
        integrity = body.pop("integrity", None)
        recorded = None
        if isinstance(integrity, Mapping):
            recorded = integrity.get("sha256", integrity.get("canonical_sha256"))
        actual = hashlib.sha256(_canonical(body)).hexdigest()
        if recorded != canonical_sha256 or actual != canonical_sha256:
            raise base.runner.RecheckError(f"{label} canonical integrity differs")
    return value


def _verify_local_artifacts() -> dict[str, Any]:
    try:
        return pack.validate_artifacts()
    except (OSError, ValueError) as error:
        raise base.runner.RecheckError(str(error)) from error


def validate_source_white_authority() -> dict[str, Any]:
    """Deeply replay the exact V3 clean-white source, without device I/O."""

    loaded: dict[str, dict[str, Any]] = {}
    verified_files: dict[str, Any] = {}
    for name, binding in SOURCE_BINDINGS.items():
        path = SOURCE_ROOT / str(binding["path"])
        loaded[name] = _read_exact_json(
            path,
            byte_count=int(binding["bytes"]),
            file_sha256=str(binding["file_sha256"]),
            canonical_sha256=str(binding["canonical_sha256"]),
            label=f"P1 source {name}",
        )
        verified_files[name] = {
            "path": _repo_relative(path),
            "bytes": binding["bytes"],
            "file_sha256": binding["file_sha256"],
            "canonical_sha256": binding["canonical_sha256"],
        }

    gate = loaded["source_terminal_gate"]
    selected = gate.get("selected_source_terminal_evidence")
    if (
        gate.get("kind")
        != "mf1750-stable-code0-luma-latin-v3-white-successor-v1-source-gate"
        or gate.get("state") != "DEEPLY_VALIDATED_BEFORE_ANY_WHITE_LIVE_REQUEST"
        or gate.get("white_campaign_id") != SOURCE_WHITE_CAMPAIGN_ID
        or gate.get("white_contract_id") != SOURCE_WHITE_CONTRACT_ID
        or gate.get("white_descriptor_id") != SOURCE_WHITE_DESCRIPTOR_ID
        or gate.get("white_action_id") != SOURCE_WHITE_ACTION_ID
        or gate.get("write_contract") != "O_EXCL"
        or gate.get("no_retry") is not True
        or gate.get("no_recovery") is not True
        or gate.get("no_autochain") is not True
        or not isinstance(selected, Mapping)
        or selected.get("verified") is not True
        or selected.get("terminal_state") != "COMPLETE"
    ):
        raise base.runner.RecheckError("P1 source white terminal gate semantics differ")

    white = loaded["white_action"]
    action = white.get("action")
    terminal = white.get("terminal_report")
    driver = terminal.get("driver") if isinstance(terminal, Mapping) else None
    if (
        white.get("kind")
        != "mf1750-stable-code0-luma-latin-v3-white-successor-v1-result"
        or white.get("outcome") != "complete_pass"
        or white.get("visible_refreshes") != 1
        or white.get("no_retry") is not True
        or white.get("no_recovery") is not True
        or white.get("no_autochain") is not True
        or not isinstance(action, Mapping)
        or action.get("ordinal") != 1
        or action.get("role") != "FACTORY_OTP_WHITE_RECOVERY"
        or action.get("descriptor_id") != SOURCE_WHITE_DESCRIPTOR_ID
        or action.get("action_id") != SOURCE_WHITE_ACTION_ID
        or not isinstance(terminal, Mapping)
        or terminal.get("campaign_id") != SOURCE_WHITE_CAMPAIGN_ID
        or terminal.get("contract_id") != SOURCE_WHITE_CONTRACT_ID
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("valid") is not True
        or terminal.get("result") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or terminal.get("campaign_complete") is not True
        or not isinstance(driver, Mapping)
        or driver.get("sequence_ok") is not True
        or driver.get("wait_timeout") is not False
        or driver.get("busy_assertion_missing") is not False
    ):
        raise base.runner.RecheckError("P1 source white COMPLETE semantics differ")

    relay = loaded["relay_off"]
    if (
        relay.get("kind") != "mf17506-zave-relay-exact-bound-switch-receipt"
        or relay.get("channel") != 1
        or relay.get("contact_path") != "COM1-NO1"
        or relay.get("target_state") != "OFF"
        or relay.get("commanded_state") != "OFF"
        or relay.get("target_gate_passed") is not True
        or relay.get("off_gate_passed") is not True
        or relay.get("contact_switch_performed") is not True
        or relay.get("automatic_retry_performed") is not False
        or relay.get("automatic_recovery_performed") is not False
        or relay.get("electrical_state_proven") is not False
    ):
        raise base.runner.RecheckError("P1 source white relay-OFF semantics differ")

    review = loaded["clean_white_review"]
    classification = review.get("classification")
    capture = review.get("capture_binding")
    review_relay = review.get("relay_post_action_off")
    if (
        review.get("kind") != "mf1750-camera-visible-clean-white-review"
        or review.get("campaign_id") != SOURCE_WHITE_CAMPAIGN_ID
        or review.get("contract_id") != SOURCE_WHITE_CONTRACT_ID
        or review.get("descriptor_id") != SOURCE_WHITE_DESCRIPTOR_ID
        or review.get("action_id") != SOURCE_WHITE_ACTION_ID
        or review.get("capture_id") != SOURCE_CAPTURE_ID
        or review.get("review_id") != SOURCE_REVIEW_ID
        or not isinstance(classification, Mapping)
        or classification.get("verdict") != "PASS"
        or classification.get("camera_visible_clean_white_review_passed") is not True
        or classification.get("camera_relative_only") is not True
        or classification.get("qualified_level_count") != 0
        or classification.get("retained_action_to_capture_continuity_proven")
        is not False
        or not isinstance(capture, Mapping)
        or capture.get("camera_id") != "48MP USB Camera"
        or "vid_32e4&pid_4801" not in str(capture.get("camera_instance_id", "")).lower()
        or capture.get("full_panel_uncropped") is not True
        or capture.get("full_panel_visible") is not True
        or not isinstance(review_relay, Mapping)
        or review_relay.get("commanded_state") != "OFF"
        or review_relay.get("off_gate_passed") is not True
        or review_relay.get("contact_path") != "COM1-NO1"
    ):
        raise base.runner.RecheckError("P1 clean-white review semantics differ")

    return {
        "kind": "mf1750-p1-v3-clean-white-source-authority-v1",
        "sealed": True,
        "state": "EXACT_V3_WHITE_ACTION_REVIEW_AND_RELAY_OFF_DEEPLY_VALIDATED",
        "source_campaign_id": SOURCE_WHITE_CAMPAIGN_ID,
        "source_contract_id": SOURCE_WHITE_CONTRACT_ID,
        "source_descriptor_id": SOURCE_WHITE_DESCRIPTOR_ID,
        "source_action_id": SOURCE_WHITE_ACTION_ID,
        "source_capture_id": SOURCE_CAPTURE_ID,
        "source_review_id": SOURCE_REVIEW_ID,
        "files": verified_files,
        "camera_relative_only": True,
        "absolute_white_point_proven": False,
        "retained_action_to_capture_continuity_proven": False,
        "live_no_intervening_visible_refresh_confirmation_required": True,
        "network_accessed": False,
        "hardware_accessed": False,
    }


def _private_origin(value: str) -> str:
    if not isinstance(value, str):
        raise base.runner.RecheckError("base URL must be an exact private IPv4 origin")
    parsed = urllib_parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise base.runner.RecheckError("base URL port differs") from error
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or (port is not None and port != 80)
    ):
        raise base.runner.RecheckError("base URL must be exact plain HTTP port 80")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as error:
        raise base.runner.RecheckError("base URL must use literal IPv4") from error
    if (
        not isinstance(address, ipaddress.IPv4Address)
        or str(address) != EXPECTED_DEVICE_IPV4
    ):
        raise base.runner.RecheckError(
            f"P1 base URL is fixed to http://{EXPECTED_DEVICE_IPV4}"
        )
    return f"http://{address}"


def _request_timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0 < float(value) <= 30
    ):
        raise base.runner.RecheckError("HTTP timeout must be in (0,30]")
    return float(value)


class _NoRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _direct_http_request(
    base_url: str,
    path: str,
    *,
    method: str,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> tuple[int, Mapping[str, Any]]:
    request = urllib_request.Request(
        base_url + path,
        method=method,
        headers={"Accept": "application/json", **dict(headers or {})},
    )
    opener = urllib_request.build_opener(urllib_request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=_request_timeout(timeout)) as response:  # noqa: S310
            status = response.status
            payload = response.read(_MAX_JSON_BYTES + 1)
    except urllib_error.HTTPError as error:
        status = error.code
        payload = error.read(_MAX_JSON_BYTES + 1)
    except (OSError, urllib_error.URLError) as error:
        raise base.runner.RecheckError(
            f"direct {method} {path} failed: {error}"
        ) from error
    if len(payload) > _MAX_JSON_BYTES:
        raise base.runner.RecheckError("device response is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.runner.RecheckError("device response is not UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise base.runner.RecheckError("device response root is not an object")
    return status, value


def validate_exact_ipv4_mac_binding(path: Path, base_url: str) -> dict[str, Any]:
    value = _read_exact_json(path, label="P1 exact IPv4/MAC binding")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = integrity.get("sha256") if isinstance(integrity, Mapping) else None
    actual = hashlib.sha256(_canonical(body)).hexdigest()
    neighbours = value.get("neighbour_entries")
    active_probe = value.get("active_probe")
    if (
        _SHA256.fullmatch(str(recorded)) is None
        or recorded != actual
        or value.get("kind") != "mf1750-exact-ipv4-mac-binding-attempt-v1"
        or value.get("candidate_ipv4") != EXPECTED_DEVICE_IPV4
        or value.get("expected_mac") != EXPECTED_DEVICE_MAC
        or value.get("active_probe_authorized") is not True
        or value.get("single_candidate_confirmed") is not True
        or value.get("candidate_count") != 1
        or value.get("binding_passed") is not True
        or value.get("fresh_binding_passed") is not True
        or value.get("network_layer_mac_binding_observed") is not True
        or value.get("device_application_identity_proven") is not False
        or value.get("outcome") != "active_exact_mac_binding_pass"
        or value.get("http_requests") != 0
        or value.get("device_api_requests") != 0
        or value.get("mutation_requests") != 0
        or value.get("visible_refresh_requests") != 0
        or value.get("retry") is not False
        or value.get("fallback") is not False
        or value.get("scan") is not False
        or value.get("output_contract") != "O_EXCL_TERMINAL"
        or not isinstance(active_probe, Mapping)
        or active_probe.get("kind") != "one_icmp_echo_to_exact_literal_ipv4"
        or active_probe.get("attempts") != 1
        or active_probe.get("returncode") != 0
        or value.get("observed_state") not in _FRESH_NEIGHBOUR_STATES
        or not isinstance(neighbours, list)
        or len(neighbours) != 1
        or neighbours[0].get("IPAddress") != EXPECTED_DEVICE_IPV4
        or neighbours[0].get("LinkLayerAddress") != EXPECTED_DEVICE_MAC
        or _private_origin(base_url) != f"http://{EXPECTED_DEVICE_IPV4}"
    ):
        raise base.runner.RecheckError("P1 exact IPv4/MAC binding semantics differ")
    payload = Path(path).read_bytes()
    return {
        "path": _repo_relative(Path(path)),
        "bytes": len(payload),
        "file_sha256": hashlib.sha256(payload).hexdigest(),
        "canonical_integrity_sha256": recorded,
        "candidate_ipv4": EXPECTED_DEVICE_IPV4,
        "expected_mac": EXPECTED_DEVICE_MAC,
        "outcome": "active_exact_mac_binding_pass",
        "fresh_binding_passed": True,
        "device_application_identity_proven": False,
        "device_api_requests": 0,
        "mutation_requests": 0,
        "visible_refresh_requests": 0,
    }


def _validate_capabilities(value: Mapping[str, Any]) -> None:
    required_true = (
        "full_screen_global_refresh",
        "fresh_one_shot_endpoint_atlas",
        "complete_profile_tuple",
        "position_balanced_atlas",
        "busy_qualified_arm_execute_dispatch",
        "device_enforced_same_boot",
    )
    required_false = (
        "partial_refresh",
        "window_refresh",
        "command_0x83",
        "command_0x86",
        "unknown_commands",
        "mid_refresh_power_cut",
        "spi_frequency_sweep",
        "same_palette_hold_probe",
        "cross_palette_hold_probe",
        "local_hold_claimed",
        "colour_qualification",
        "lightness_qualification",
        "history_sequence",
        "identical_target_repeat",
        "main_campaign_resume_after_containment",
    )
    if any(value.get(key) is not True for key in required_true):
        raise base.runner.RecheckError("P1 required capability differs")
    if any(value.get(key) is not False for key in required_false):
        raise base.runner.RecheckError("P1 forbidden capability differs")


def _validate_version(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="version")  # noqa: SLF001
    if (
        value.get("layout_id") != pack.VARIANT_KEY
        or value.get("action_count") != 1
        or value.get("runtime_lut_write") is not True
    ):
        raise base.runner.RecheckError("P1 version identity/action contract differs")
    for key in (
        "automatic_execute",
        "automatic_chaining",
        "startup_refresh",
        "raw_frame_ingress",
        "electrical_parameter_write",
        "dither",
        "spatial_mixing",
        "retry",
        "recovery",
    ):
        if value.get(key) is not False:
            raise base.runner.RecheckError(f"P1 version safety {key} differs")
    nvs = value.get("nvs_contract")
    if (
        not isinstance(nvs, Mapping)
        or nvs.get("namespace") != pack.NVS_NAMESPACE
        or nvs.get("key") != pack.NVS_KEY
        or nvs.get("campaign_boot_key") != pack.NVS_BOOT_KEY
        or nvs.get("initial_key_present") is not False
        or nvs.get("initial_next_ordinal") != 1
        or nvs.get("terminal_next_ordinal") != 2
        or nvs.get("reboot_resume_allowed") is not False
        or nvs.get("post_containment_resume_allowed") is not False
    ):
        raise base.runner.RecheckError("P1 fresh NVS isolation differs")
    baseline = value.get("baseline_contract")
    if (
        not isinstance(baseline, Mapping)
        or baseline.get("ordinal") is not None
        or baseline.get("role") != _BASELINE_ROLE
        or baseline.get("external_anchor_required") is not True
        or baseline.get("one_visible_refresh_required") is not False
    ):
        raise base.runner.RecheckError("P1 external white anchor surface differs")
    if value.get("external_containment") != REPORT["contract"]["external_containment"]:
        raise base.runner.RecheckError("P1 external containment differs")
    _validate_capabilities(value)


def _validate_manifest(value: Mapping[str, Any]) -> None:
    base.runner._identity(value, kind_suffix="manifest")  # noqa: SLF001
    exact = {
        "layout_id": pack.VARIANT_KEY,
        "actions": list(base.runner.ACTIONS),
        "action_count": 1,
        "one_driver_call_per_action": True,
        "factory_otp": False,
        "custom_lut_or_waveform": True,
        "runtime_lut_write": True,
        "recovery": False,
    }
    if any(value.get(key) != wanted for key, wanted in exact.items()):
        raise base.runner.RecheckError("P1 manifest identity/action surface differs")
    if value.get("external_containment") != REPORT["contract"]["external_containment"]:
        raise base.runner.RecheckError("P1 manifest external containment differs")
    layout = value.get("history_layout")
    expected = {
        "controller_count": 2,
        "controller_width": 512,
        "height": 600,
        "grid_rows": 4,
        "grid_columns_per_controller": 8,
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "grid_x0_local": 20,
        "grid_y_by_row": list(pack.GRID_Y_BY_ROW),
        "grid_x1_local_exclusive": 492,
        "grid_y1_exclusive": 552,
        "cell_width": 52,
        "cell_height": 100,
        "gap_x": 8,
        "gap_y": 36,
        "background_code": 7,
        "border": False,
        "same_layout_both_controllers": True,
        "controller_dtm_byte_identical": True,
        "cs2_position_mirrored": False,
        "spatial_dither": False,
        "fresh_one_shot": True,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "factory_otp_white_ordinals": [],
        "runtime_lut_ordinals": [1],
        "one_visible_refresh_per_action": True,
        "samples_per_code_per_controller_per_frame": 4,
        "qualified_colours": 0,
        "qualified_lightness_levels": 0,
        "active_global_tuple_id": REPORT["contract"]["profile"]["global_tuple_id"],
    }
    if not isinstance(layout, Mapping) or any(
        layout.get(key) != wanted for key, wanted in expected.items()
    ):
        raise base.runner.RecheckError("P1 manifest 4x8/history-free layout differs")
    _validate_capabilities(value)


def _validate_ready_status(
    value: Mapping[str, Any], ordinal: int, *, expected_busy: int
) -> str:
    if (
        ordinal != 1
        or expected_busy not in (0, 1)
        or value.get("busy") != expected_busy
    ):
        raise base.runner.RecheckError("P1 ready ordinal/BUSY admission differs")
    nonce = v1._BASE_VALIDATE_READY_STATUS(  # noqa: SLF001
        value, ordinal, expected_busy=expected_busy
    )
    for key in (
        "arm_request_count",
        "execute_request_count",
        "total_driver_call_count",
    ):
        if value.get(key) != 0:
            raise base.runner.RecheckError(f"P1 fresh ready {key} differs")
    if (
        value.get("campaign_boot_key_present") is not True
        or value.get("persisted_campaign_boot_nonce") != nonce
        or value.get("campaign_boot_matches_current") is not True
        or value.get("device_enforced_same_boot") is not True
        or value.get("reboot_resume_allowed") is not False
        or value.get("post_containment_resume_allowed") is not False
    ):
        raise base.runner.RecheckError("P1 same-boot binding differs")
    return nonce


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_complete_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    if ordinal != 1:
        raise base.runner.RecheckError("P1 COMPLETE ordinal differs")
    action = base.runner.ACTIONS[0]
    source = REPORT["actions"][0]
    base.runner._identity(value, kind_suffix="report")  # noqa: SLF001
    exact = {
        "boot_nonce": boot_nonce,
        "valid": True,
        "terminal_state": "COMPLETE",
        "result": True,
        "driver_called": True,
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "ordinal": 1,
        "descriptor_id": action["descriptor_id"],
        "action_id": action["action_id"],
        "role": action["role"],
        "branch": action["branch"],
        "phase": 0,
        "phase_name": "READY",
        "next_ordinal": 2,
        "campaign_complete": True,
        "no_retry": True,
        "no_recovery": True,
    }
    if any(value.get(key) != wanted for key, wanted in exact.items()):
        raise base.runner.RecheckError("P1 COMPLETE terminal semantics differ")
    driver = value.get("driver")
    driver_exact = {
        "valid": True,
        "running": False,
        "sequence_ok": True,
        "wait_timeout": False,
        "busy_assertion_missing": False,
        "pre_command_idle_failure": False,
        "failure_stage": "none",
        "timeout_stage": "none",
        "busy_missing_stage": "none",
        "pre_command_busy_stage": "none",
        "spi_hz": 1_000_000,
        "operation_id": 1,
        "pon_busy_seen": True,
        "drf_busy_seen": True,
        "pof_busy_seen": True,
        "input_fnv1a": source["frame"]["fnv1a"],
        "cs1_dtm_fnv1a": source["cs1_dtm"]["fnv1a"],
        "cs2_dtm_fnv1a": source["cs2_dtm"]["fnv1a"],
    }
    if not isinstance(driver, Mapping) or any(
        driver.get(key) != wanted for key, wanted in driver_exact.items()
    ):
        raise base.runner.RecheckError("P1 COMPLETE driver evidence differs")
    if any(
        not _positive_int(driver.get(key)) for key in ("pon_ms", "drf_ms", "pof_ms")
    ):
        raise base.runner.RecheckError("P1 COMPLETE BUSY duration evidence differs")
    safe = driver.get("safe_finish")
    gpio = safe.get("final_gpio") if isinstance(safe, Mapping) else None
    if (
        not isinstance(safe, Mapping)
        or any(
            safe.get(key) != 1
            for key in ("busy_before_pins_low", "busy_after_pins_low", "busy_after_5ms")
        )
        or gpio != {"busy": 1, "rst": 0, "cs": 0, "cs2": 0}
    ):
        raise base.runner.RecheckError("P1 COMPLETE safe-finish evidence differs")


def _validate_prior_terminal_report(
    value: Mapping[str, Any], ordinal: int, boot_nonce: str
) -> None:
    del value, ordinal, boot_nonce
    raise base.runner.RecheckError("P1 fresh one-shot has no prior ordinal")


def _preflight(
    base_url: str,
    ordinal: int,
    *,
    expected_busy: int,
    requester: Any,
) -> tuple[str, list[dict[str, Any]], Mapping[str, Any]]:
    boot_nonce, transcript, report = v1._BASE_PREFLIGHT(  # noqa: SLF001
        base_url, ordinal, expected_busy=expected_busy, requester=requester
    )
    if ordinal != 1:
        raise base.runner.RecheckError("P1 ordinal must be exactly 1")
    v1._validate_fresh_no_execute_report(report, boot_nonce)  # noqa: SLF001
    return boot_nonce, transcript, report


# Rebind every validator consumed by the isolated reviewed runner facade.
host._validate_capabilities = _validate_capabilities
host._validate_version = _validate_version
host._validate_manifest = _validate_manifest
host._validate_ready_status = _validate_ready_status
host._validate_complete_report = _validate_complete_report
host._validate_prior_terminal_report = _validate_prior_terminal_report
host._preflight = _preflight
host._require_firmware_binding = lambda: _verify_local_artifacts()
host._FACTORY_HEALTH_ROLE = "__NO_FACTORY_ACTION_IN_P1__"
base._validate_capabilities = _validate_capabilities
base._validate_version = _validate_version
base._validate_manifest = _validate_manifest
base.runner._validate_version = _validate_version
base.runner._validate_manifest = _validate_manifest
base.runner._validate_ready_status = _validate_ready_status
base.runner._preflight = _preflight
base.runner._origin = _private_origin
base.runner._http_request = _direct_http_request
v1._validate_version = _validate_version
v1._validate_manifest = _validate_manifest
v1._preflight = _preflight


def diagnose_j2_off(
    base_url: str,
    *,
    exact_ipv4_mac_binding: Path,
    confirm_j2_off: bool = False,
    confirm_source_v3_clean_white_retained: bool = False,
    output: Path = DIAGNOSTIC_OUTPUT,
    requester: Any = None,
) -> dict[str, Any]:
    if confirm_j2_off is not True:
        raise base.runner.RecheckError("P1 diagnostic requires explicit J2-OFF")
    if confirm_source_v3_clean_white_retained is not True:
        raise base.runner.RecheckError(
            "P1 diagnostic requires retained V3 clean-white confirmation"
        )
    output = _fixed_path(output, DIAGNOSTIC_OUTPUT, label="P1 diagnostic output")
    origin = _private_origin(base_url)
    source = validate_source_white_authority()
    artifacts = _verify_local_artifacts()
    address = validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, origin)
    selected = requester or _direct_http_request
    boot_nonce, transcript, report = _preflight(
        origin, 1, expected_busy=0, requester=selected
    )
    result = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-p1-active-endpoint-atlas-4x8-v1-j2-off-diagnostic",
            "created_at": base.runner._now(),  # noqa: SLF001
            "campaign_id": pack.CAMPAIGN_ID,
            "contract_id": REPORT["contract_id"],
            "source_white_authority": source,
            "artifacts": artifacts,
            "exact_ipv4_mac_binding": address,
            "base_url": origin,
            "boot_nonce": boot_nonce,
            "j2_confirmed_off": True,
            "source_v3_clean_white_retained_confirmed": True,
            "next_ordinal": 1,
            "report": deepcopy(dict(report)),
            "transcript": transcript,
            "network": {"get": 4, "post": 0},
            "permanent_claims_created": 0,
            "visible_refreshes": 0,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
        }
    )
    base.runner._write_new(output, result)  # noqa: SLF001
    return result


def _validate_diagnostic(
    path: Path, base_url: str, exact_ipv4_mac_binding: Path
) -> dict[str, Any]:
    value = _read_exact_json(path, label="P1 J2-OFF diagnostic")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = integrity.get("sha256") if isinstance(integrity, Mapping) else None
    if recorded != hashlib.sha256(_canonical(body)).hexdigest():
        raise base.runner.RecheckError("P1 diagnostic canonical integrity differs")
    if (
        value.get("kind") != "mf1750-p1-active-endpoint-atlas-4x8-v1-j2-off-diagnostic"
        or value.get("campaign_id") != pack.CAMPAIGN_ID
        or value.get("contract_id") != REPORT["contract_id"]
        or value.get("source_white_authority") != validate_source_white_authority()
        or value.get("artifacts") != _verify_local_artifacts()
        or value.get("exact_ipv4_mac_binding")
        != validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, base_url)
        or value.get("base_url") != _private_origin(base_url)
        or value.get("j2_confirmed_off") is not True
        or value.get("source_v3_clean_white_retained_confirmed") is not True
        or value.get("next_ordinal") != 1
        or value.get("network") != {"get": 4, "post": 0}
        or value.get("permanent_claims_created") != 0
        or value.get("visible_refreshes") != 0
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
    ):
        raise base.runner.RecheckError("P1 J2-OFF diagnostic semantics differ")
    nonce = value.get("boot_nonce")
    if not isinstance(nonce, str) or _NONCE.fullmatch(nonce) is None:
        raise base.runner.RecheckError("P1 diagnostic boot nonce differs")
    return value


def _same_boot_requester(expected_boot_nonce: str, requester: Any) -> Any:
    def checked(*args: Any, **kwargs: Any) -> tuple[int, Mapping[str, Any]]:
        status, value = requester(*args, **kwargs)
        observed = value.get("boot_nonce") if isinstance(value, Mapping) else None
        if observed is not None and observed != expected_boot_nonce:
            raise base.runner.RecheckError(
                "P1 live boot differs from J2-OFF diagnostic"
            )
        return status, value

    return checked


def run_once(
    base_url: str,
    ordinal: int,
    *,
    claims: Path,
    output: Path,
    exact_ipv4_mac_binding: Path,
    requester: Any = None,
    poll_seconds: float = 65.0,
    poll_count: int = 60,
    confirm_j2_on: bool = False,
    confirm_source_v3_clean_white: bool = False,
    confirm_no_intervening_visible_refresh: bool = False,
) -> dict[str, Any]:
    """Consume P1 once; all live confirmations precede GET/claim/POST."""

    # These gates intentionally precede artifact/source reads, diagnostic
    # replay, requester selection, permanent claim creation, and all device I/O.
    if confirm_j2_on is not True:
        raise base.runner.RecheckError("P1 run requires explicit J2-ON")
    if confirm_source_v3_clean_white is not True:
        raise base.runner.RecheckError(
            "P1 run requires the exact bound V3 clean-white source"
        )
    if confirm_no_intervening_visible_refresh is not True:
        raise base.runner.RecheckError(
            "P1 run requires live confirmation of no intervening visible refresh"
        )
    if ordinal != 1:
        raise base.runner.RecheckError("P1 ordinal must be exactly 1")

    origin = _private_origin(base_url)
    claims = _fixed_path(claims, base.runner.DEFAULT_CLAIMS, label="P1 claims root")
    output = _fixed_path(output, ACTION_OUTPUTS[1], label="P1 action output")
    source = validate_source_white_authority()
    artifacts = _verify_local_artifacts()
    address = validate_exact_ipv4_mac_binding(exact_ipv4_mac_binding, origin)
    diagnostic = _validate_diagnostic(DIAGNOSTIC_OUTPUT, origin, exact_ipv4_mac_binding)
    if poll_seconds < 65.0:
        raise base.runner.RecheckError("P1 run requires poll_seconds >= 65")
    if (
        not isinstance(poll_count, int)
        or isinstance(poll_count, bool)
        or poll_count < 1
    ):
        raise base.runner.RecheckError("P1 run requires poll_count >= 1")
    if output.exists():
        raise base.runner.RecheckError(f"refusing to overwrite {output}")
    claim = claims / f"{base.runner.ACTIONS[0]['action_id']}.json"
    if claim.exists():
        raise base.runner.RecheckError("P1 permanent action claim already exists")

    admission = base.runner._seal(  # noqa: SLF001
        {
            "schema_version": 1,
            "kind": "mf1750-p1-active-endpoint-atlas-4x8-v1-live-admission",
            "created_at": base.runner._now(),  # noqa: SLF001
            "campaign_id": pack.CAMPAIGN_ID,
            "contract_id": REPORT["contract_id"],
            "ordinal": 1,
            "action_id": base.runner.ACTIONS[0]["action_id"],
            "boot_nonce": diagnostic["boot_nonce"],
            "base_url": origin,
            "source_white_authority": source,
            "artifacts": artifacts,
            "exact_ipv4_mac_binding": address,
            "j2_confirmed_on_before_any_live_get_claim_or_post": True,
            "source_v3_clean_white_confirmed": True,
            "no_intervening_visible_refresh_confirmed": True,
            "no_retry": True,
            "no_recovery": True,
            "no_autochain": True,
            "output_write_contract": "O_EXCL",
        }
    )
    base.runner._write_new(RUN_ADMISSION_OUTPUT, admission)  # noqa: SLF001

    selected = requester or _direct_http_request
    selected = _same_boot_requester(str(diagnostic["boot_nonce"]), selected)
    return host.run_once(
        origin,
        1,
        claims=claims,
        output=output,
        requester=selected,
        poll_seconds=poll_seconds,
        poll_count=poll_count,
    )


def dry_validate(*, verify_artifacts: bool = True) -> dict[str, Any]:
    report = pack.build_report()
    contract = report["contract"]
    actions = report["actions"]
    source = validate_source_white_authority()
    artifacts = (
        _verify_local_artifacts()
        if verify_artifacts
        else {
            name: {
                "path": _repo_relative(Path(binding["path"])),
                "bytes": binding["bytes"],
                "sha256": binding["sha256"],
            }
            for name, binding in ARTIFACTS.items()
        }
    )
    flat = [code for row in pack.CODE_ROWS for code in row]
    if (
        report["contract_id"] != base.runner.CONTRACT_ID
        or len(actions) != 1
        or tuple(item["role"] for item in actions) != (pack.ROLE,)
        or tuple(item["action_id"] for item in actions) != base.runner.ACTION_IDS
        or contract["action_count"] != 1
        or contract["geometry"]["row_codes"] != [list(row) for row in pack.CODE_ROWS]
        or sorted(flat) != [code for code in range(8) for _ in range(4)]
        or contract["geometry"]["samples_per_code_per_controller_per_frame"] != 4
        or contract["geometry"]["same_layout_both_controllers"] is not True
        or contract["geometry"]["controller_dtm_byte_identical"] is not True
        or actions[0]["cs1_dtm"] != actions[0]["cs2_dtm"]
        or contract["fresh_one_shot"] is not True
        or contract["source_history_actions"] != 0
        or contract["middle_history_actions"] != 0
        or contract["identical_target_repeat_actions"] != 0
        or contract["one_visible_refresh_per_action"] is not True
        or contract["partial_refresh"] is not False
        or contract["local_hold_claimed"] is not False
        or contract["automatic_chaining"] is not False
        or contract["retry"] is not False
        or contract["recovery"] is not False
        or contract["qualified_colours"] != 0
        or contract["qualified_lightness_levels"] != 0
    ):
        raise base.runner.RecheckError("P1 offline one-shot/4x8 invariant differs")
    profile = contract["profile"]
    if (
        profile["complete_profile_tuple"] is not True
        or profile["cs1"] != profile["cs2"]
        or profile["controller_payloads_byte_identical"] is not True
        or profile["global_tuple_id"] != actions[0]["global_tuple_id"]
    ):
        raise base.runner.RecheckError(
            "P1 active/active complete-profile tuple differs"
        )
    return {
        "kind": "mf1750-p1-active-endpoint-atlas-4x8-v1-runner-validation",
        "result": "PASS",
        "offline_only": True,
        "network_requests": 0,
        "device_requests_made": 0,
        "hardware_accessed": False,
        "serial_or_com_accessed": False,
        "relay_accessed": False,
        "camera_accessed": False,
        "firmware_flashed": False,
        "display_refreshed": False,
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": report["contract_id"],
        "action_id": actions[0]["action_id"],
        "row_codes": [list(row) for row in pack.CODE_ROWS],
        "samples_per_code_per_controller": 4,
        "controller_dtm_byte_identical": True,
        "complete_active_profile_both_controllers": True,
        "visible_refreshes_per_action": 1,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "partial_refresh": False,
        "local_hold_claimed": False,
        "retry": False,
        "recovery": False,
        "autochain": False,
        "qualified_colours": 0,
        "qualified_lightness_levels": 0,
        "source_white_authority": source,
        "artifacts": artifacts,
        "artifacts_verified": verify_artifacts,
        "run_live_gates": [
            "confirm_j2_on",
            "confirm_source_v3_clean_white",
            "confirm_no_intervening_visible_refresh",
            "exact_ipv4_mac_binding",
            "same_boot_j2_off_diagnostic",
        ],
    }


def describe() -> dict[str, Any]:
    return {
        **dry_validate(verify_artifacts=True),
        "contract": deepcopy(REPORT["contract"]),
        "actions_table": deepcopy(base.runner.ACTIONS),
        "endpoints": deepcopy(base.runner.ENDPOINTS),
        "fixed_device_binding": {
            "base_url": f"http://{EXPECTED_DEVICE_IPV4}",
            "expected_mac": EXPECTED_DEVICE_MAC,
            "active_exact_binding_required_before_any_device_request": True,
        },
        "fixed_outputs": {
            "root": _repo_relative(base.runner.DEFAULT_OUTPUT),
            "diagnostic": _repo_relative(DIAGNOSTIC_OUTPUT),
            "live_admission": _repo_relative(RUN_ADMISSION_OUTPUT),
            "action_1": _repo_relative(ACTION_OUTPUTS[1]),
            "claims_root": _repo_relative(base.runner.DEFAULT_CLAIMS),
        },
        "diagnostic": {
            "j2_off_required": True,
            "get": 4,
            "post": 0,
            "claims": 0,
            "visible_refreshes": 0,
        },
        "independent_white_successor_required": True,
    }


def validate_terminal_evidence(path: Path) -> dict[str, Any]:
    """Deeply validate the immutable ordinal-1 COMPLETE result offline."""

    validate_source_white_authority()
    _verify_local_artifacts()
    resolved = Path(path).resolve()
    if resolved != ACTION_OUTPUTS[1].resolve():
        raise base.runner.RecheckError("P1 accepts only its fixed ordinal-1 output")
    value = _read_exact_json(resolved, label="P1 terminal evidence")
    body = deepcopy(value)
    integrity = body.pop("integrity", None)
    recorded = integrity.get("sha256") if isinstance(integrity, Mapping) else None
    if recorded != hashlib.sha256(_canonical(body)).hexdigest():
        raise base.runner.RecheckError(
            "P1 terminal evidence canonical integrity differs"
        )
    expected = base.runner.ACTIONS[0]
    action = value.get("action")
    terminal = value.get("terminal_report")
    transcript = value.get("transcript")
    boot_nonce = value.get("boot_nonce")
    if not isinstance(action, Mapping) or dict(action) != expected:
        raise base.runner.RecheckError("P1 terminal action identity differs")
    if not isinstance(terminal, Mapping):
        raise base.runner.RecheckError("P1 terminal report missing")
    if not isinstance(boot_nonce, str) or _NONCE.fullmatch(boot_nonce) is None:
        raise base.runner.RecheckError("P1 terminal boot nonce differs")
    _validate_complete_report(terminal, 1, boot_nonce)
    if (
        value.get("kind") != "mf1750-ec5-p1-active-endpoint-atlas-4x8-v1-result"
        or value.get("firmware_sha256") != base.runner.FIRMWARE_SHA256
        or value.get("outcome") != "complete_pass"
        or value.get("visible_refreshes") != 1
        or value.get("no_retry") is not True
        or value.get("no_recovery") is not True
        or value.get("no_autochain") is not True
        or terminal.get("campaign_id") != pack.CAMPAIGN_ID
        or terminal.get("contract_id") != REPORT["contract_id"]
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
    ):
        raise base.runner.RecheckError(
            "P1 terminal COMPLETE/one-refresh semantics differ"
        )
    if not isinstance(transcript, list) or len(transcript) < 7:
        raise base.runner.RecheckError("P1 terminal transcript missing")
    expected_prefix = [
        ("GET", "version"),
        ("GET", "manifest"),
        ("GET", "status"),
        ("GET", "report"),
        ("POST", "arm"),
        ("POST", "execute"),
    ]
    if (
        [(item.get("method"), item.get("endpoint")) for item in transcript[:6]]
        != expected_prefix
        or any(
            (item.get("method"), item.get("endpoint")) != ("GET", "report")
            for item in transcript[6:]
        )
        or any(
            item.get("path") != base.runner.ENDPOINTS.get(item.get("endpoint"))
            or not isinstance(item.get("status"), int)
            or not 200 <= item["status"] < 300
            or not isinstance(item.get("response"), Mapping)
            for item in transcript
        )
        or value.get("network")
        != {"get": 4 + len(transcript[6:]), "arm_post": 1, "execute_post": 1}
        or transcript[-1].get("response") != terminal
    ):
        raise base.runner.RecheckError("P1 terminal wire sequence differs")
    try:
        _validate_version(transcript[0]["response"])
        _validate_manifest(transcript[1]["response"])
        observed_boot = _validate_ready_status(
            transcript[2]["response"], 1, expected_busy=1
        )
        v1._validate_fresh_no_execute_report(  # noqa: SLF001
            transcript[3]["response"], observed_boot
        )
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError(
            "P1 terminal preflight transcript differs"
        ) from error
    if observed_boot != boot_nonce:
        raise base.runner.RecheckError("P1 terminal preflight/result boot differs")
    arm = transcript[4]
    execute = transcript[5]
    arm_response = arm["response"]
    execute_response = execute["response"]
    arm_nonce = arm_response.get("arm_nonce")
    arm_headers = base.runner._headers(expected, boot_nonce, base.runner.ARM_INTENT)  # noqa: SLF001
    execute_headers = base.runner._headers(  # noqa: SLF001
        expected, boot_nonce, base.runner.EXECUTE_INTENT
    )
    execute_headers["X-EC5-Arm-Nonce"] = arm_nonce
    if (
        arm.get("headers") != dict(sorted(arm_headers.items()))
        or execute.get("headers") != dict(sorted(execute_headers.items()))
        or arm_response.get("accepted") is not True
        or arm_response.get("armed") is not True
        or arm_response.get("ordinal") != 1
        or arm_response.get("action_id") != expected["action_id"]
        or arm_response.get("boot_nonce") != boot_nonce
        or not isinstance(arm_nonce, str)
        or _NONCE.fullmatch(arm_nonce) is None
        or execute_response.get("accepted") is not True
        or execute_response.get("execute_consumed") is not True
        or execute_response.get("ordinal") != 1
        or execute_response.get("action_id") != expected["action_id"]
        or execute_response.get("boot_nonce") != boot_nonce
    ):
        raise base.runner.RecheckError("P1 terminal ARM/EXECUTE evidence differs")
    expected_claim = (
        base.runner.DEFAULT_CLAIMS / f"{expected['action_id']}.json"
    ).resolve()
    claim_path = value.get("claim_file")
    if not isinstance(claim_path, str) or Path(claim_path).resolve() != expected_claim:
        raise base.runner.RecheckError("P1 terminal permanent claim path differs")
    try:
        claim, claim_file_sha256 = v1._load_permanent_claim(  # noqa: SLF001
            expected_claim, expected
        )
    except (KeyError, OSError, TypeError, ValueError, RuntimeError) as error:
        raise base.runner.RecheckError(
            "P1 permanent claim deep validation failed"
        ) from error
    if claim.get("boot_nonce") != boot_nonce:
        raise base.runner.RecheckError("P1 claim boot differs")
    return {
        "terminal_state": "COMPLETE",
        "campaign_id": pack.CAMPAIGN_ID,
        "contract_id": REPORT["contract_id"],
        "ordinal": 1,
        "descriptor_id": expected["descriptor_id"],
        "action_id": expected["action_id"],
        "role": expected["role"],
        "driver_call_count_for_action": 1,
        "total_driver_call_count": 1,
        "visible_refreshes": 1,
        "source_history_actions": 0,
        "middle_history_actions": 0,
        "identical_target_repeat_actions": 0,
        "retry": False,
        "recovery": False,
        "autochain": False,
        "boot_nonce": boot_nonce,
        "claim_path": _repo_relative(expected_claim),
        "claim_file_sha256": claim_file_sha256,
        "claim_canonical_integrity_sha256": claim["integrity"]["sha256"],
        "file_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
        "canonical_integrity_sha256": recorded,
    }


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("describe")
    sub.add_parser("prebuild-validate")
    sub.add_parser("dry-validate")
    terminal = sub.add_parser("validate-terminal-evidence", allow_abbrev=False)
    terminal.add_argument("--path", type=Path, default=ACTION_OUTPUTS[1])
    diagnostic = sub.add_parser("diagnose-j2-off", allow_abbrev=False)
    diagnostic.add_argument("--base-url", required=True)
    diagnostic.add_argument("--exact-ipv4-mac-binding", type=Path, required=True)
    diagnostic.add_argument("--confirm-j2-off", action="store_true", required=True)
    diagnostic.add_argument(
        "--confirm-source-v3-clean-white-retained",
        action="store_true",
        required=True,
    )
    run = sub.add_parser("run", allow_abbrev=False)
    run.add_argument("--base-url", required=True)
    run.add_argument("--ordinal", type=int, choices=(1,), required=True)
    run.add_argument("--exact-ipv4-mac-binding", type=Path, required=True)
    run.add_argument("--confirm-j2-on", action="store_true", required=True)
    run.add_argument(
        "--confirm-source-v3-clean-white", action="store_true", required=True
    )
    run.add_argument(
        "--confirm-no-intervening-visible-refresh",
        action="store_true",
        required=True,
    )
    run.add_argument("--poll-seconds", type=float, default=65.0)
    run.add_argument("--poll-count", type=int, default=60)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.command == "describe":
            value = describe()
        elif args.command == "prebuild-validate":
            value = dry_validate(verify_artifacts=False)
        elif args.command == "dry-validate":
            value = dry_validate(verify_artifacts=True)
        elif args.command == "validate-terminal-evidence":
            value = validate_terminal_evidence(args.path)
        elif args.command == "diagnose-j2-off":
            value = diagnose_j2_off(
                args.base_url,
                exact_ipv4_mac_binding=args.exact_ipv4_mac_binding,
                confirm_j2_off=args.confirm_j2_off,
                confirm_source_v3_clean_white_retained=(
                    args.confirm_source_v3_clean_white_retained
                ),
            )
        else:
            value = run_once(
                args.base_url,
                args.ordinal,
                claims=base.runner.DEFAULT_CLAIMS,
                output=ACTION_OUTPUTS[1],
                exact_ipv4_mac_binding=args.exact_ipv4_mac_binding,
                poll_seconds=args.poll_seconds,
                poll_count=args.poll_count,
                confirm_j2_on=args.confirm_j2_on,
                confirm_source_v3_clean_white=args.confirm_source_v3_clean_white,
                confirm_no_intervening_visible_refresh=(
                    args.confirm_no_intervening_visible_refresh
                ),
            )
    except (OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"P1 active endpoint atlas runner error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
