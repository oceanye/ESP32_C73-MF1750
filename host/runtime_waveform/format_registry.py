"""Trusted, offline format registrations for future runtime waveform plans.

A registration freezes an exact, per-controller command sequence without
carrying command parameter or waveform payload bytes in logs.  Tests may pass
an explicit synthetic registry; callers must never treat a manifest-supplied
registration as trusted.

The first production registration (SPD1657_R20_L535_GEOMETRY_V1, 2026-10-09)
covers the L535 535-byte table geometry (7-byte header + 6 groups x 8 records
x 11 bytes; record fields stay opaque).  Its review basis is the sealed PAL1
chain strict native audit plus the panel-verified PAL1 render evidence.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Sequence

from . import contracts


FORMAT_REGISTRATION_SCHEMA_VERSION = 1
FORMAT_REGISTRATION_KIND = "mf1750-runtime-waveform-format-registration"
BLOCKED_FORMAT_NOT_REGISTERED = "BLOCKED_FORMAT_NOT_REGISTERED"

L535_GEOMETRY_FORMAT_ID = "SPD1657_R20_L535_GEOMETRY_V1"

# The L535 R20 table geometry: per controller, 0xE9 {0x01} mode-select then a
# 535-byte 0x20 LUT write.  Reviewed under the PAL1 chain strict native audit.
REGISTERED_FORMATS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        L535_GEOMETRY_FORMAT_ID: {
            "schema_version": FORMAT_REGISTRATION_SCHEMA_VERSION,
            "kind": FORMAT_REGISTRATION_KIND,
            "registration_id": "spd1657-r20-l535-geometry-v1-registration",
            "format_id": L535_GEOMETRY_FORMAT_ID,
            "format_document_sha256": "f45f161e164cbd3ff7852275d41c028e3ae065ce5370738fd6fa45a46d97f0cb",
            "loader_source_sha256": "1b6bbcf35cefc338f7ab9b76c04c869f9a82e800c4ccaa52d204d9fd6e53b7a5",
            "reviewer_id": "pal1-cal-chain-strict-native-audit-20260925",
            "review_artifact_sha256": "5b95aa0bcb27a4cb56cd06831668b8122b59478a1495e14c596c762a76267757",
            "steps": [
                {
                    "index": 0,
                    "controller_target": "CS1",
                    "opcode": 0xE9,
                    "parameter_source": "literal_parameter",
                    "parameter_length": 1,
                    "literal_parameter_sha256": "4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a",
                    "predecessor_index": None,
                },
                {
                    "index": 1,
                    "controller_target": "CS1",
                    "opcode": 0x20,
                    "parameter_source": "controller_payload",
                    "parameter_length": 535,
                    "literal_parameter_sha256": None,
                    "predecessor_index": 0,
                },
                {
                    "index": 2,
                    "controller_target": "CS2",
                    "opcode": 0xE9,
                    "parameter_source": "literal_parameter",
                    "parameter_length": 1,
                    "literal_parameter_sha256": "4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a",
                    "predecessor_index": 1,
                },
                {
                    "index": 3,
                    "controller_target": "CS2",
                    "opcode": 0x20,
                    "parameter_source": "controller_payload",
                    "parameter_length": 535,
                    "literal_parameter_sha256": None,
                    "predecessor_index": 2,
                },
            ],
        }
    }
)

_REGISTRATION_KEYS = {
    "schema_version",
    "kind",
    "registration_id",
    "format_id",
    "format_document_sha256",
    "loader_source_sha256",
    "reviewer_id",
    "review_artifact_sha256",
    "steps",
}
_STEP_KEYS = {
    "index",
    "controller_target",
    "opcode",
    "parameter_source",
    "parameter_length",
    "literal_parameter_sha256",
    "predecessor_index",
}
_CONTROLLERS = ("CS1", "CS2")
_PARAMETER_SOURCES = {"literal_parameter", "controller_payload"}


class FormatRegistrationError(ValueError):
    """Raised when a trusted format registration is ambiguous or unsafe."""


def registration_sha256(registration: Mapping[str, Any]) -> str:
    """Return the canonical identity of one validated registration."""

    validate_format_registration(registration)
    return contracts.sha256_hex(contracts.canonical_json_bytes(registration))


def _exact_mapping(value: Any, *, label: str, keys: set[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise FormatRegistrationError(f"{label} keys differ")
    return value


def _identifier(value: Any, *, label: str) -> str:
    try:
        result = contracts._identifier(value, label=label)  # noqa: SLF001
    except contracts.RuntimeWaveformContractError as error:
        raise FormatRegistrationError(str(error)) from error
    assert result is not None
    return result


def _hash(value: Any, *, label: str, nullable: bool = False) -> str | None:
    try:
        return contracts._hash(value, label=label, nullable=nullable)  # noqa: SLF001
    except contracts.RuntimeWaveformContractError as error:
        raise FormatRegistrationError(str(error)) from error


def _integer(
    value: Any,
    *,
    label: str,
    minimum: int,
    maximum: int,
    nullable: bool = False,
) -> int | None:
    try:
        return contracts._integer(  # noqa: SLF001
            value,
            label=label,
            minimum=minimum,
            maximum=maximum,
            nullable=nullable,
        )
    except contracts.RuntimeWaveformContractError as error:
        raise FormatRegistrationError(str(error)) from error


def validate_format_registration(
    registration: Mapping[str, Any],
    *,
    expected_format_id: str | None = None,
    expected_format_document_sha256: str | None = None,
    expected_loader_source_sha256: str | None = None,
    expected_reviewer_id: str | None = None,
    controller_payload_lengths: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Validate an exact E9/20 sequence without inferring unknown parameters."""

    root = _exact_mapping(
        registration,
        label="format registration",
        keys=_REGISTRATION_KEYS,
    )
    if (
        root["schema_version"] != FORMAT_REGISTRATION_SCHEMA_VERSION
        or root["kind"] != FORMAT_REGISTRATION_KIND
    ):
        raise FormatRegistrationError("format registration identity differs")
    registration_id = _identifier(root["registration_id"], label="registration_id")
    format_id = _identifier(root["format_id"], label="format_id")
    format_document_sha = _hash(
        root["format_document_sha256"], label="format_document_sha256"
    )
    loader_source_sha = _hash(
        root["loader_source_sha256"], label="loader_source_sha256"
    )
    reviewer_id = _identifier(root["reviewer_id"], label="reviewer_id")
    _hash(root["review_artifact_sha256"], label="review_artifact_sha256")

    expected_values = (
        (format_id, expected_format_id, "format_id"),
        (
            format_document_sha,
            expected_format_document_sha256,
            "format_document_sha256",
        ),
        (loader_source_sha, expected_loader_source_sha256, "loader_source_sha256"),
        (reviewer_id, expected_reviewer_id, "reviewer_id"),
    )
    for actual, expected, label in expected_values:
        if expected is not None and actual != expected:
            raise FormatRegistrationError(f"registered {label} differs")

    steps = root["steps"]
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)):
        raise FormatRegistrationError("format registration steps must be an array")
    if len(steps) != 4:
        raise FormatRegistrationError(
            "exactly four per-controller mode-select/LUT-write steps are required"
        )

    validated_steps: list[dict[str, Any]] = []
    per_controller: dict[str, list[int]] = {controller: [] for controller in _CONTROLLERS}
    for position, raw in enumerate(steps):
        step = _exact_mapping(raw, label=f"registration step {position}", keys=_STEP_KEYS)
        index = _integer(
            step["index"], label=f"step {position} index", minimum=0, maximum=255
        )
        assert index is not None
        if index != position:
            raise FormatRegistrationError("registration step indexes must be contiguous")
        predecessor = _integer(
            step["predecessor_index"],
            label=f"step {position} predecessor_index",
            minimum=0,
            maximum=254,
            nullable=True,
        )
        expected_predecessor = None if position == 0 else position - 1
        if predecessor != expected_predecessor:
            raise FormatRegistrationError("registration predecessor chain differs")
        target = step["controller_target"]
        if target not in _CONTROLLERS:
            raise FormatRegistrationError(
                "runtime waveform registration must target CS1 or CS2 explicitly"
            )
        opcode = _integer(
            step["opcode"], label=f"step {position} opcode", minimum=0, maximum=255
        )
        assert opcode is not None
        if opcode not in contracts.ALLOWED_RUNTIME_COMMANDS:
            raise FormatRegistrationError(
                f"step {position} opcode 0x{opcode:02x} is not allowlisted"
            )
        parameter_source = step["parameter_source"]
        if parameter_source not in _PARAMETER_SOURCES:
            raise FormatRegistrationError(f"step {position} parameter source differs")
        parameter_length = _integer(
            step["parameter_length"],
            label=f"step {position} parameter_length",
            minimum=1,
            maximum=1_048_576,
        )
        assert parameter_length is not None
        literal_sha = _hash(
            step["literal_parameter_sha256"],
            label=f"step {position} literal_parameter_sha256",
            nullable=True,
        )

        if opcode == 0xE9:
            if parameter_source != "literal_parameter" or literal_sha is None:
                raise FormatRegistrationError(
                    "mode-select steps require an exact literal parameter identity"
                )
        elif opcode == 0x20:
            if parameter_source != "controller_payload" or literal_sha is not None:
                raise FormatRegistrationError(
                    "LUT-write steps require the matching controller payload"
                )
            if controller_payload_lengths is not None:
                if set(controller_payload_lengths) != set(_CONTROLLERS):
                    raise FormatRegistrationError(
                        "controller payload lengths must contain exact CS1/CS2 keys"
                    )
                if parameter_length != controller_payload_lengths[target]:
                    raise FormatRegistrationError(
                        f"{target} LUT-write parameter length differs from its payload"
                    )
        per_controller[target].append(opcode)
        validated_steps.append(
            {
                "index": index,
                "predecessor_index": predecessor,
                "controller_target": target,
                "opcode": opcode,
                "parameter_source": parameter_source,
                "parameter_length": parameter_length,
                "literal_parameter_sha256": literal_sha,
            }
        )

    for controller in _CONTROLLERS:
        if per_controller[controller] != [0xE9, 0x20]:
            raise FormatRegistrationError(
                f"{controller} exact sequence must be mode-select then LUT-write"
            )
    return {
        "registration_id": registration_id,
        "format_id": format_id,
        "format_document_sha256": format_document_sha,
        "loader_source_sha256": loader_source_sha,
        "reviewer_id": reviewer_id,
        "steps": validated_steps,
        "canonical_sha256": contracts.sha256_hex(
            contracts.canonical_json_bytes(registration)
        ),
    }


def trusted_registration_for(
    format_id: str,
    *,
    registry: Mapping[str, Mapping[str, Any]] = REGISTERED_FORMATS,
) -> Mapping[str, Any] | None:
    """Return a trusted registration only when the registry key and body agree."""

    registration = registry.get(format_id)
    if registration is None:
        return None
    validated = validate_format_registration(registration, expected_format_id=format_id)
    if validated["format_id"] != format_id:
        raise FormatRegistrationError("trusted format registry key differs from its body")
    return registration
