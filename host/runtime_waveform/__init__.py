"""Fail-closed contracts for future SPD1657 runtime-waveform work."""

from .contracts import (
    BLOCKED_CLASSIFICATION,
    CANDIDATE_KIND,
    EVALUATION_KIND,
    GATE_NAMES,
    RuntimeWaveformContractError,
    build_reference_blocked_candidate,
    canonical_json_bytes,
    evaluate_candidate,
    sha256_hex,
    validate_candidate,
)
from .virtual_palette import (
    VirtualPaletteError,
    compile_virtual_palette,
    validate_virtual_color,
)
from .evidence import EvidenceBundleError, validate_evidence_bundle
from .format_registry import (
    BLOCKED_FORMAT_NOT_REGISTERED,
    FORMAT_REGISTRATION_KIND,
    L535_GEOMETRY_FORMAT_ID,
    REGISTERED_FORMATS,
    FormatRegistrationError,
    validate_format_registration,
)
from .l535_table_builder import (
    L535Table,
    L535TableError,
    build_table,
    canonical_manifest_bytes,
    from_reference,
    to_candidate_manifest,
    validate_table_bytes,
)
from .execution_plan import (
    ExecutionPlanError,
    compile_execution_plan,
    validate_execution_plan,
)
from .transport_state_machine import (
    FIRMWARE_COMPILE_GATE_ENABLED,
    MockOnlyRuntimeWaveformTransport,
    TransportStateError,
)
from .campaign import (
    PlaceholderCampaignError,
    build_placeholder_campaign,
    validate_placeholder_bundle_directory,
    write_placeholder_bundle,
)
from .seed_perturbation import (
    DECISION_BLOCKED,
    DECISION_METADATA_ONLY,
    SeedPerturbationError,
    build_report as build_seed_perturbation_report,
    build_seed_inventory,
    enumerate_m1_metadata,
    validate_report as validate_seed_perturbation_report,
    validate_seed_inventory,
    write_report as write_seed_perturbation_report,
)

__all__ = [
    "BLOCKED_CLASSIFICATION",
    "CANDIDATE_KIND",
    "EVALUATION_KIND",
    "GATE_NAMES",
    "RuntimeWaveformContractError",
    "build_reference_blocked_candidate",
    "canonical_json_bytes",
    "evaluate_candidate",
    "sha256_hex",
    "validate_candidate",
    "VirtualPaletteError",
    "compile_virtual_palette",
    "validate_virtual_color",
    "EvidenceBundleError",
    "validate_evidence_bundle",
    "BLOCKED_FORMAT_NOT_REGISTERED",
    "FORMAT_REGISTRATION_KIND",
    "L535_GEOMETRY_FORMAT_ID",
    "REGISTERED_FORMATS",
    "FormatRegistrationError",
    "validate_format_registration",
    "L535Table",
    "L535TableError",
    "build_table",
    "canonical_manifest_bytes",
    "from_reference",
    "to_candidate_manifest",
    "validate_table_bytes",
    "ExecutionPlanError",
    "compile_execution_plan",
    "validate_execution_plan",
    "FIRMWARE_COMPILE_GATE_ENABLED",
    "MockOnlyRuntimeWaveformTransport",
    "TransportStateError",
    "PlaceholderCampaignError",
    "build_placeholder_campaign",
    "validate_placeholder_bundle_directory",
    "write_placeholder_bundle",
    "DECISION_BLOCKED",
    "DECISION_METADATA_ONLY",
    "SeedPerturbationError",
    "build_seed_perturbation_report",
    "build_seed_inventory",
    "enumerate_m1_metadata",
    "validate_seed_perturbation_report",
    "validate_seed_inventory",
    "write_seed_perturbation_report",
]
