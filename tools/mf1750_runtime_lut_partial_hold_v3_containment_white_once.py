#!/usr/bin/env python3
"""Fresh factory-OTP white containment for the L535/PTLW V3 campaign."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_BASE_PATH = Path(__file__).with_name("mf1750_stage3_wf23_white_once.py")
_SPEC = importlib.util.spec_from_file_location(
    "_mf1750_rlph_v3_containment_white_private_base", _BASE_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load containment base: {_BASE_PATH}")
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)

base.FIRMWARE_BIN = Path(
    ".pio/build-runtime-lut-partial-hold-v3-containment-white/"
    "ec5_rlph_v3_containment_white/firmware.bin"
)
base.FIRMWARE_ELF = Path(
    ".pio/build-runtime-lut-partial-hold-v3-containment-white/"
    "ec5_rlph_v3_containment_white/firmware.elf"
)
base.FIRMWARE_BIN_SHA256 = (
    "33f7fb6cd330f30acd305067d08b11449c6dc921566e18466121c6518856a569"
)
base.FIRMWARE_ELF_SHA256 = (
    "224e5b57cdc5099c6ed7ce569d40b436ecd278ed49f958ae922cb5fd6ef1005d"
)
base.BUILD_TAG = (
    "MF1750_EC5_RUNTIME_LUT_PARTIAL_HOLD_V3_CONTAINMENT_WHITE_V1_2026-08-23"
)
base.CAMPAIGN_ID = "EC5_RUNTIME_LUT_PARTIAL_HOLD_V3_CONTAINMENT_20260823"
base.ENVIRONMENT = "ec5_rlph_v3_containment_white"
base.NVS_NAMESPACE = "rlphv3cw"
base.CONTRACT_ID = (
    "57257364eb00c4cd15faa294c456e6e87e3b8ba7368bf70a72fead1e28bf43ab"
)
base.DESCRIPTOR_ID = (
    "1b85ec877e780f45b30aa69f127472cc22535474b03a5fb7d0d19e87e5ca67d3"
)
base.ACTION_ID = (
    "c24baf700cf8ce45eedcdcde252728ef4d4fd016c3ceaa1dbef7d76699cfab02"
)
base.DESCRIPTOR_MARKER = (
    "MF1750_EC5_TX_DESCRIPTOR_V1|PROFILE=WF23_25|ROLE=OTP_WHITE|"
    f"SHA256={base.DESCRIPTOR_ID}"
)

PRIOR_RUNTIME_CLAIM = Path(
    ".test-output/hardware/"
    ".mf1750_runtime_lut_partial_hold_l535_active_v3_claims/"
    "92f8f0dae944bd554f64afb880ec588a8066cc3ce9d330384790e07e5f91abca.json"
)
PRIOR_RUNTIME_CLAIM_SHA256 = (
    "887489b7184deb5581fe1a44debdb767e16f730c9ae715296e08ed698c25f0fd"
)
PRIOR_RUNTIME_RESULT = Path(
    ".test-output/hardware/"
    "MF1750_RUNTIME_LUT_PARTIAL_HOLD_L535_ACTIVE_V3_20260823/"
    "ordinal1-code7-common-white-result.json"
)
PRIOR_RUNTIME_RESULT_SHA256 = (
    "d27e617f44b2654f1e6133a64c90e4feba644cc698fc6d4f2eb46b8dd5d0791f"
)
PRIOR_RUNTIME_FIRMWARE_SHA256 = (
    "52a46202c2897450f5356d026e64e647880e35a3f523f1bab9f9db61fda1649e"
)
PRIOR_RUNTIME_ACTION_ID = (
    "92f8f0dae944bd554f64afb880ec588a8066cc3ce9d330384790e07e5f91abca"
)
PRIOR_RUNTIME_DESCRIPTOR_ID = (
    "1574488d764bf79d01ba597b87a3584985b77e202d71d5813d1661e234ea4f1c"
)

_BASE_DESCRIBE = base.describe
_BASE_RUN = base._run  # noqa: SLF001


def _read_exact_sealed(
    path: Path, wanted_sha256: str, *, label: str
) -> Mapping[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise base.Stage3WhiteError(f"{label} is absent or unsafe")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != wanted_sha256:
        raise base.Stage3WhiteError(f"{label} file SHA-256 differs")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise base.Stage3WhiteError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, Mapping):
        raise base.Stage3WhiteError(f"{label} root is not an object")
    integrity = value.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("algorithm") != (
        "sha256-canonical-json-without-integrity"
    ):
        raise base.Stage3WhiteError(f"{label} integrity contract differs")
    body = dict(value)
    body.pop("integrity", None)
    canonical = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if integrity.get("sha256") != hashlib.sha256(canonical).hexdigest():
        raise base.Stage3WhiteError(f"{label} canonical seal differs")
    return value


def _validate_v3_runtime_evidence() -> None:
    claim = _read_exact_sealed(
        PRIOR_RUNTIME_CLAIM,
        PRIOR_RUNTIME_CLAIM_SHA256,
        label="V3 runtime permanent claim",
    )
    result = _read_exact_sealed(
        PRIOR_RUNTIME_RESULT,
        PRIOR_RUNTIME_RESULT_SHA256,
        label="V3 runtime terminal result",
    )
    claim_action = claim.get("action")
    result_action = result.get("action")
    if not isinstance(claim_action, Mapping) or not isinstance(result_action, Mapping):
        raise base.Stage3WhiteError("V3 runtime action evidence is absent")
    exact_claim = {
        "schema_version": 1,
        "kind": "mf1750-ec5-runtime-lut-partial-hold-l535-active-permanent-claim",
        "firmware_sha256": PRIOR_RUNTIME_FIRMWARE_SHA256,
        "state": "claimed_before_first_mutation",
        "no_retry": True,
        "no_recovery": True,
        "no_autochain": True,
    }
    for key, wanted in exact_claim.items():
        if claim.get(key) != wanted:
            raise base.Stage3WhiteError(f"V3 runtime claim {key} differs")
    for action, label in ((claim_action, "claim"), (result_action, "result")):
        if (
            action.get("ordinal") != 1
            or action.get("action_id") != PRIOR_RUNTIME_ACTION_ID
            or action.get("descriptor_id") != PRIOR_RUNTIME_DESCRIPTOR_ID
            or action.get("role") != "RUNTIME_LUT_WHITE_BASELINE"
        ):
            raise base.Stage3WhiteError(f"V3 runtime {label} action binding differs")
    terminal = result.get("terminal_report")
    network = result.get("network")
    if (
        result.get("kind")
        != "mf1750-ec5-runtime-lut-partial-hold-l535-active-result"
        or result.get("firmware_sha256") != PRIOR_RUNTIME_FIRMWARE_SHA256
        or result.get("outcome") != "complete_pass"
        or result.get("visible_refreshes") != 1
        or result.get("no_retry") is not True
        or result.get("no_recovery") is not True
        or result.get("no_autochain") is not True
        or not isinstance(terminal, Mapping)
        or terminal.get("ordinal") != 1
        or terminal.get("action_id") != PRIOR_RUNTIME_ACTION_ID
        or terminal.get("terminal_state") != "COMPLETE"
        or terminal.get("result") is not True
        or terminal.get("driver_called") is not True
        or terminal.get("driver_call_count_for_action") != 1
        or terminal.get("total_driver_call_count") != 1
        or terminal.get("next_ordinal") != 2
        or not isinstance(network, Mapping)
        or network.get("arm_post") != 1
        or network.get("execute_post") != 1
    ):
        raise base.Stage3WhiteError("V3 runtime terminal result binding differs")
    claimed_path = result.get("claim_file")
    if not isinstance(claimed_path, str) or Path(claimed_path).resolve() != (
        PRIOR_RUNTIME_CLAIM.resolve()
    ):
        raise base.Stage3WhiteError("V3 runtime result claim path differs")


@contextmanager
def _v3_runtime_claim_override():
    """Replace only the historical WF23 prior-claim gate with exact V3 evidence."""

    _validate_v3_runtime_evidence()
    original = base.physical._require_runtime_claim  # noqa: SLF001

    def validate_selected_v3_claim(_context, _registry) -> None:
        _validate_v3_runtime_evidence()

    base.physical._require_runtime_claim = validate_selected_v3_claim  # noqa: SLF001
    try:
        yield
    finally:
        base.physical._require_runtime_claim = original  # noqa: SLF001


def describe():
    value = _BASE_DESCRIBE()
    value["kind"] = "mf1750-runtime-lut-partial-hold-v3-containment-white"
    value["purpose"] = "independent_factory_otp_white_only_if_v3_needs_containment"
    value["requires_prior_runtime_claim"] = True
    value["prior_runtime_claim"] = str(PRIOR_RUNTIME_CLAIM)
    value["prior_runtime_claim_sha256"] = PRIOR_RUNTIME_CLAIM_SHA256
    value["prior_runtime_result"] = str(PRIOR_RUNTIME_RESULT)
    value["prior_runtime_result_sha256"] = PRIOR_RUNTIME_RESULT_SHA256
    value["automatic_execution"] = False
    return value


base.describe = describe


def _run(args):
    with _v3_runtime_claim_override():
        return _BASE_RUN(args)


base._run = _run  # noqa: SLF001


def main(argv: Sequence[str] | None = None) -> int:
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
