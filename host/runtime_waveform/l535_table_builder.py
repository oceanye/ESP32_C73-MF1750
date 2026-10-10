"""Offline L535 R20 table builder: auditable 535-byte geometry, named header knobs.

The L535 table geometry is fully bound (7-byte header + 6 groups x 8 records
x 11 opaque record bytes = 535 transmitted bytes), while the 11-byte record
field semantics stay OPAQUE on purpose - this module never assigns meaning to
record bytes and never materializes a waveform plan.  What it does:

* load the sealed reference tables (active/commented) as auditable objects;
* rebuild them byte-exactly by default (hard fidelity contract);
* expose the measured lever as explicit named knobs - the 7 header bytes
  (voltage domain codes + PLL), whose active-vs-commented difference is the
  only difference between two panel-proven tables;
* emit contract candidates whose canonical manifest bytes flow into
  execution_plan's zero-I/O plan compiler (which still demands the complete
  P0 evidence bundle before any plan exists - fail-closed by design).

No hardware, network, relay or camera access anywhere below.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

from . import contracts, format_registry


FORMAT_ID = format_registry.L535_GEOMETRY_FORMAT_ID
TABLE_BYTES = 535
HEADER_BYTES = 7
RECORD_GROUPS = 6
RECORDS_PER_GROUP = 8
RECORD_BYTES = 11

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_INC = REPO_ROOT / "src/generated/spd1657_legacy_535_reference.inc"
REFERENCE_PREFIX_SHA256 = "716cc229f8b954c4c66c387d69e80d2eb26c9a5a99b4bdd653f1282ace56e44b"
FORMAT_DOCUMENT_PATH = (
    REPO_ROOT / "host/runtime_waveform/formats/SPD1657_R20_L535_GEOMETRY_V1.json"
)

# Header byte layout (format document binding):
#   [0] fixed 0x00
#   [1] vsh_lv_code    vsh_lv_mv    =  3000 + 100 * code
#   [2] vsl_lv_code    vsl_lv_mv    = -(3000 + 100 * code)
#   [3] vsh_lv2_code   vsh_lv2_mv   =  3000 + 100 * code
#   [4] vsl_lv2_code   vsl_lv2_mv   = -(3000 + 100 * code)
#   [5] gate_code      |gate_mv|    =  1000 * code
#   [6] pll_code       raw PLL payload byte (opaque scaling)
_REFERENCE_ACTIVE_KNOBS = {
    "vsh_lv_mv": 6000,    # 0x1E -> 3000 + 100 * 30
    "vsl_lv_mv": -15000,  # 0x78
    "vsh_lv2_mv": 6200,   # 0x20
    "vsl_lv2_mv": -6000,  # 0x1E
    "gate_mv": 20000,     # 0x14
    "pll_code": 0x02,
}
_REFERENCE_COMMENTED_KNOBS = {
    "vsh_lv_mv": 6600,    # 0x24
    "vsl_lv_mv": -15000,  # 0x78
    "vsh_lv2_mv": 6900,   # 0x27
    "vsl_lv2_mv": -6200,  # 0x20
    "gate_mv": 20000,     # 0x14
    "pll_code": 0x03,
}

_PANEL_SERIAL = "MF750M009T6420/1582643AGY44"
_PANEL_BATCH_ID = "mf1750-devkitc-b2"

# Gates this candidate can attest with sealed evidence; every other gate stays
# False (its proof obligation remains open, see the evaluation blockers).
ATTESTABLE_GATES = (
    "panel_and_batch_exact",
    "dual_controller_3bit_format_documented",
    "plaintext_decoded_payload_available",
    "register_sequence_reviewed",
)


class L535TableError(ValueError):
    """Raised when a table, knob set, or emitted document is malformed."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _extract_inc_array(chunk: str, name: str) -> list[int]:
    match = re.search(re.escape(name) + r"\[\d+\]\s*=\s*\{(.*?)\};", chunk, re.S)
    if match is None:
        raise L535TableError(f"reference include is missing {name}")
    return [int(value.strip(), 16) for value in match.group(1).split(",") if value.strip()]


def _encode_voltage_code(value_mv: int, *, label: str, positive: bool) -> int:
    magnitude = value_mv if positive else -value_mv
    if magnitude < 3000 or (magnitude - 3000) % 100 != 0:
        raise L535TableError(f"{label} must be 3000 + 100 * n mV")
    code = (magnitude - 3000) // 100
    if not 0 <= code <= 255:
        raise L535TableError(f"{label} code out of byte range")
    return code


def header_bytes_from_knobs(knobs: Mapping[str, Any]) -> bytes:
    """Encode the 7 header bytes from named knob values (validated)."""

    unknown = set(knobs) - set(_REFERENCE_ACTIVE_KNOBS)
    if unknown:
        raise L535TableError(f"unknown header knobs: {sorted(unknown)}")
    missing = set(_REFERENCE_ACTIVE_KNOBS) - set(knobs)
    if missing:
        raise L535TableError(f"missing header knobs: {sorted(missing)}")
    vsh = _encode_voltage_code(int(knobs["vsh_lv_mv"]), label="vsh_lv_mv", positive=True)
    vsl = _encode_voltage_code(int(knobs["vsl_lv_mv"]), label="vsl_lv_mv", positive=False)
    vsh2 = _encode_voltage_code(int(knobs["vsh_lv2_mv"]), label="vsh_lv2_mv", positive=True)
    vsl2 = _encode_voltage_code(int(knobs["vsl_lv2_mv"]), label="vsl_lv2_mv", positive=False)
    gate_mv = int(knobs["gate_mv"])
    if gate_mv <= 0 or gate_mv % 1000 != 0 or gate_mv // 1000 > 255:
        raise L535TableError("gate_mv must be 1000 * n mV within a byte")
    pll = knobs["pll_code"]
    if type(pll) is not int or isinstance(pll, bool) or not 0 <= pll <= 255:
        raise L535TableError("pll_code must be a byte")
    return bytes([0x00, vsh, vsl, vsh2, vsl2, gate_mv // 1000, pll])


def knobs_from_header_bytes(header: bytes) -> dict[str, int]:
    """Decode the named knobs back out of 7 header bytes (round-trip audit)."""

    if len(header) != HEADER_BYTES or header[0] != 0x00:
        raise L535TableError("header must be 7 bytes with a fixed 0x00 first byte")
    return {
        "vsh_lv_mv": 3000 + 100 * header[1],
        "vsl_lv_mv": -(3000 + 100 * header[2]),
        "vsh_lv2_mv": 3000 + 100 * header[3],
        "vsl_lv2_mv": -(3000 + 100 * header[4]),
        "gate_mv": 1000 * header[5],
        "pll_code": header[6],
    }


@dataclass(frozen=True)
class L535Table:
    """One auditable 535-byte L535 table: header + opaque record groups."""

    header: bytes
    groups: tuple[tuple[bytes, ...], ...]
    knobs: Mapping[str, int]
    source_role: str

    def to_bytes(self) -> bytes:
        payload = bytearray(self.header)
        for group in self.groups:
            for record in group:
                payload.extend(record)
        return bytes(payload)

    @property
    def sha256(self) -> str:
        return _sha256(self.to_bytes())


def validate_table_bytes(payload: bytes) -> None:
    """Structural validation only: geometry and header legality, never semantics."""

    if len(payload) != TABLE_BYTES:
        raise L535TableError(f"L535 table must be exactly {TABLE_BYTES} bytes")
    if payload[0] != 0x00:
        raise L535TableError("L535 header byte 0 must be 0x00")
    knobs_from_header_bytes(payload[:HEADER_BYTES])  # validates ranges
    record_region = payload[HEADER_BYTES:]
    if len(record_region) != RECORD_GROUPS * RECORDS_PER_GROUP * RECORD_BYTES:
        raise L535TableError("L535 record region geometry differs")


def _split_groups(record_region: bytes) -> tuple[tuple[bytes, ...], ...]:
    groups = []
    for group_index in range(RECORD_GROUPS):
        start = group_index * RECORDS_PER_GROUP * RECORD_BYTES
        records = tuple(
            record_region[start + i * RECORD_BYTES: start + (i + 1) * RECORD_BYTES]
            for i in range(RECORDS_PER_GROUP)
        )
        groups.append(records)
    return tuple(groups)


def from_reference(role: str = "active") -> L535Table:
    """Load a sealed reference table (active|commented) as an auditable object."""

    if role not in ("active", "commented"):
        raise L535TableError("reference role must be active or commented")
    text = REFERENCE_INC.read_text(encoding="utf-8")
    marker = f"namespace {role} {{"
    if marker not in text:
        raise L535TableError(f"reference include lacks the {role} namespace")
    chunk = text.split(marker, 1)[1]
    next_namespace = chunk.find("namespace commented {")
    if role == "active" and next_namespace > 0:
        chunk = chunk[:next_namespace]
    r20 = bytes(_extract_inc_array(chunk, "kR20Payload"))
    table_bytes = r20[:TABLE_BYTES]
    validate_table_bytes(table_bytes)
    if role == "active" and _sha256(table_bytes) != REFERENCE_PREFIX_SHA256:
        raise L535TableError("active reference prefix identity differs from the pin")
    knobs = _REFERENCE_ACTIVE_KNOBS if role == "active" else _REFERENCE_COMMENTED_KNOBS
    header = table_bytes[:HEADER_BYTES]
    if knobs_from_header_bytes(header) != knobs:
        raise L535TableError(f"{role} reference header knobs differ from the sealed constants")
    return L535Table(
        header=header,
        groups=_split_groups(table_bytes[HEADER_BYTES:]),
        knobs=dict(knobs),
        source_role=role,
    )


def build_table(
    knobs: Mapping[str, Any] | None = None,
    *,
    records_from: L535Table | None = None,
) -> L535Table:
    """Assemble a table: named header knobs + inherited opaque record groups.

    Default (no knobs) rebuilds the sealed active reference byte-exactly.
    """

    base = records_from if records_from is not None else from_reference("active")
    chosen = dict(base.knobs)
    if knobs:
        chosen.update(knobs)
    header = header_bytes_from_knobs(chosen)
    table = L535Table(
        header=header,
        groups=base.groups,
        knobs=knobs_from_header_bytes(header),
        source_role=f"{base.source_role}+knobs" if knobs else base.source_role,
    )
    validate_table_bytes(table.to_bytes())
    return table


def format_document_sha256() -> str:
    """Canonical identity of the frozen format document on disk."""

    import json

    raw = FORMAT_DOCUMENT_PATH.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    canonical = contracts.canonical_json_bytes(document)
    if raw.rstrip(b"\n") != canonical:
        raise L535TableError("format document is not canonical JSON on disk")
    return _sha256(canonical)


def to_candidate_manifest(
    table: L535Table,
    *,
    created_at: str,
    profile_id: str = "l535-geometry-v1-default",
    extra_gates: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Emit a contracts candidate for one table (immutable payload identities).

    Only ATTESTABLE_GATES are asserted; every other proof obligation stays
    False and therefore fail-closed in the evaluation report.
    """

    contracts._timestamp(created_at, label="created_at")  # noqa: SLF001
    registration = format_registry.trusted_registration_for(FORMAT_ID)
    if registration is None:
        raise L535TableError("L535 geometry format is not registered")
    document_sha = format_document_sha256()
    if document_sha != registration["format_document_sha256"]:
        raise L535TableError("format document identity differs from the registration")
    payload = table.to_bytes()
    table_sha = _sha256(payload)
    gates = {name: False for name in contracts.GATE_NAMES}
    for name in ATTESTABLE_GATES:
        gates[name] = True
    if extra_gates:
        for name, value in extra_gates.items():
            if name not in gates or type(value) is not bool:
                raise L535TableError(f"invalid extra gate {name!r}")
            gates[name] = value
    candidate = {
        "schema_version": contracts.SCHEMA_VERSION,
        "kind": contracts.CANDIDATE_KIND,
        "profile_id": profile_id,
        "created_at": created_at,
        "hardware_tested": False,
        "panel": {
            "model": contracts.PANEL_MODEL,
            "serial": _PANEL_SERIAL,
            "batch_id": _PANEL_BATCH_ID,
            "controller_model": contracts.CONTROLLER_MODEL,
            "controller_revision": None,
            "controller_count": 2,
            "cascade": True,
            "panel_width": contracts.PANEL_WIDTH,
            "panel_height": contracts.PANEL_HEIGHT,
            "controller_width": contracts.CONTROLLER_WIDTH,
            "controller_height": contracts.CONTROLLER_HEIGHT,
        },
        "encoding": {
            "bits_per_pixel": 3,
            "transport_codes": list(contracts.TRANSPORT_CODES),
            "formal_codes": list(contracts.FORMAL_CODES),
            "experimental_codes": list(contracts.EXPERIMENTAL_CODES),
            "channel_model": "indexed_particle_target_states_not_independent_rgb_channels",
        },
        "payload": {
            "representation": "plaintext_decoded_3bit_lut",
            "format_id": FORMAT_ID,
            "format_document_sha256": document_sha,
            "controller_payloads": [
                {"controller": "CS1", "bytes": len(payload), "sha256": table_sha},
                {"controller": "CS2", "bytes": len(payload), "sha256": table_sha},
            ],
        },
        "electrical": {
            "temperature_min_c": None,
            "temperature_max_c": None,
            "vcom_mv": None,
            "vgh_mv": float(abs(table.knobs["gate_mv"])),
            "vgl_mv": -float(abs(table.knobs["gate_mv"])),
            "vsh_mv": float(table.knobs["vsh_lv2_mv"]),
            "vsl_mv": float(table.knobs["vsl_lv2_mv"]),
            "frame_rate_hz": None,
            "phase_timing_documented": False,
        },
        "operation_contract": {
            "mode": "runtime_lut_ram_only",
            "commands": [
                {"name": "mcu_lut_mode_select", "opcode": 0xE9, "purpose": "ram_lut_mode"},
                {"name": "lut_ram_write", "opcode": 0x20, "purpose": "runtime_lut_data"},
            ],
            "otp_programming_allowed": False,
            "otp_erase_allowed": False,
            "startup_auto_apply": False,
            "network_raw_upload_allowed": False,
        },
        "provenance": {
            "reference_artifact_sha256": _sha256(REFERENCE_INC.read_bytes()),
            "source_payload_sha256": REFERENCE_PREFIX_SHA256,
            "loader_source_sha256": registration["loader_source_sha256"],
            "vendor_or_panel_owner_review_id": registration["reviewer_id"],
            "source_is_current_panel_3bit": True,
        },
        "recovery": {
            "known_good_profile_sha256": None,
            "white_recovery_contract_sha256": None,
            "restore_otp_mode_without_programming": False,
            "validated_on_sacrificial_panel": False,
        },
        "qualification_gates": gates,
    }
    return candidate


def canonical_manifest_bytes(candidate: Mapping[str, Any]) -> bytes:
    """Canonical manifest bytes for execution_plan.load_canonical_manifest_bytes."""

    contracts.validate_candidate(candidate)
    return contracts.canonical_json_bytes(candidate)
