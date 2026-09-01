"""Offline comparison of two independent fresh-white colour constructions.

This is intentionally not the in-place G3/G4 repeat comparison.  The inputs
are the first campaign's G3 analysis and a future, independently bootstrapped
fresh-white reconstruction campaign's G3 analysis.  Their campaign and action
identities must differ while an explicit, sealed identity contract proves that
the packers emitted byte-identical G1/G2/G3 optical payloads.

The comparator only produces camera-relative review evidence.  It never opens
a camera or device and cannot create passed ``ControllerPaletteEvidence``.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import stat
from typing import Any, Mapping, Sequence

from .common import (
    StaticPhotoContractError,
    attach_integrity,
    canonical_sha256,
    require_exact_keys,
    require_sha256,
    require_text,
    verify_integrity,
)


SCHEMA_VERSION = 1
COMPARISON_KIND = "MF1750_FRESH_WHITE_RECONSTRUCTION_CAMERA_COMPARISON"
IDENTITY_CONTRACT_KIND = "MF1750_FRESH_WHITE_RECONSTRUCTION_EXPLICIT_IDENTITY_CONTRACT"
ANALYSIS_KIND = "mf1750-luma-gray-mechanism-position-balanced-v3-photo-analysis"
ANALYZER_INTEGRITY_ALGORITHM = "sha256-canonical-json-without-integrity"
PROJECT_CAMERA_USB_ID = "VID_32E4:PID_4801"
FIRST_LABEL = "F1_G3_FIRST_CONSTRUCTION"
RECONSTRUCTION_LABEL = "POSITION_BALANCED_GRAY_FRESH_RECONSTRUCTION_V1_G3"
CONTROLLERS = ("CS1", "CS2")
PACKER_PAYLOAD_FIELDS = ("frame", "cs1_dtm", "cs2_dtm")
CORE_ORDINALS = (1, 2, 3)
RECIPE_COUNT = 16
REPLICAS_PER_RECIPE = 4

DEFAULT_REVIEW_THRESHOLDS = {
    "maximum_controller_cell_centered_abs_delta_l_star_p95": 3.0,
    "maximum_controller_cell_centered_delta_e76_p95": 5.0,
    "maximum_recipe_median_abs_delta_l_star": 2.0,
    "maximum_recipe_median_delta_e76": 4.0,
    "maximum_within_recipe_position_delta_e76": 8.0,
}


class FreshReconstructionCompareError(ValueError):
    """Raised when reconstruction evidence is missing or not comparable."""


def _error_from_contract(
    error: StaticPhotoContractError,
) -> FreshReconstructionCompareError:
    return FreshReconstructionCompareError(str(error))


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FreshReconstructionCompareError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    try:
        return require_text(value, label)
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error


def _sha256(value: object, label: str) -> str:
    try:
        return require_sha256(value, label)
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error


def _integer(value: object, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        suffix = "" if minimum is None else f" >= {minimum}"
        raise FreshReconstructionCompareError(f"{label} must be an integer{suffix}")
    return value


def _finite(value: object, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FreshReconstructionCompareError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise FreshReconstructionCompareError(
            f"{label} must be finite" + (" and positive" if positive else "")
        )
    return result


def _lab(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise FreshReconstructionCompareError(f"{label} must contain three values")
    result = tuple(
        _finite(item, f"{label}[{index}]") for index, item in enumerate(value)
    )
    if not 0.0 <= result[0] <= 100.0:
        raise FreshReconstructionCompareError(f"{label} L* is outside 0..100")
    return result  # type: ignore[return-value]


def _median(values: Sequence[float]) -> float:
    ordered = sorted(float(item) for item in values)
    if not ordered:
        raise FreshReconstructionCompareError("cannot take median of empty values")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _p95(values: Sequence[float]) -> float:
    ordered = sorted(float(item) for item in values)
    if not ordered:
        raise FreshReconstructionCompareError("cannot take p95 of empty values")
    rank = 0.95 * (len(ordered) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _delta_e(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(
        sum((float(a) - float(b)) ** 2 for a, b in zip(left, right, strict=True))
    )


def _read_stable(path: Path, *, label: str) -> bytes:
    path = Path(path).resolve()
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise FreshReconstructionCompareError(
                f"{label} must be a regular non-symlink file"
            )
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise FreshReconstructionCompareError(f"cannot read {label}: {path}") from error
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity or after.st_size != len(payload):
        raise FreshReconstructionCompareError(f"{label} changed while read")
    return payload


def _json(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FreshReconstructionCompareError(f"{label} is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise FreshReconstructionCompareError(f"{label} root must be an object")
    return value


def _verify_analyzer_seal(
    value: Mapping[str, Any], label: str
) -> tuple[dict[str, Any], str]:
    body = deepcopy(dict(value))
    integrity = body.pop("integrity", None)
    if not isinstance(integrity, Mapping):
        raise FreshReconstructionCompareError(f"{label} integrity is missing")
    expected = canonical_sha256(body)
    if (
        integrity.get("algorithm") != ANALYZER_INTEGRITY_ALGORITHM
        or integrity.get("sha256") != expected
    ):
        raise FreshReconstructionCompareError(f"{label} canonical integrity differs")
    return body, expected


def _sealed_json_file(path: Path, *, label: str) -> tuple[bytes, dict[str, Any], str]:
    payload = _read_stable(path, label=label)
    value = _json(payload, label)
    _body, canonical = _verify_analyzer_seal(value, label)
    return payload, value, canonical


def _resolve_source_path(analysis_path: Path, value: object, *, label: str) -> Path:
    text = _text(value, f"{label}.path")
    candidate = Path(text)
    if not candidate.is_absolute():
        # Analyzer reports use repository-relative paths.  A relocated fixture
        # may instead place them beside the analysis report.
        repository = Path(__file__).resolve().parents[2]
        repository_candidate = (repository / candidate).resolve()
        local_candidate = (analysis_path.parent / candidate).resolve()
        candidate = (
            repository_candidate if repository_candidate.exists() else local_candidate
        )
    return candidate.resolve()


def _identity_payload(value: object, label: str) -> dict[str, Any]:
    item = _mapping(value, label)
    try:
        require_exact_keys(item, {"bytes", "sha256"}, label)
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    return {
        "bytes": _integer(item.get("bytes"), f"{label}.bytes", minimum=1),
        "sha256": _sha256(item.get("sha256"), f"{label}.sha256"),
    }


def _core_action(value: object, label: str, expected_ordinal: int) -> dict[str, Any]:
    item = _mapping(value, label)
    expected_keys = {
        "ordinal",
        "action_id",
        "descriptor_id",
        "role",
        *PACKER_PAYLOAD_FIELDS,
    }
    try:
        require_exact_keys(item, expected_keys, label)
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    ordinal = _integer(item.get("ordinal"), f"{label}.ordinal", minimum=1)
    if ordinal != expected_ordinal:
        raise FreshReconstructionCompareError(f"{label}.ordinal differs")
    return {
        "ordinal": ordinal,
        "action_id": _sha256(item.get("action_id"), f"{label}.action_id"),
        "descriptor_id": _sha256(item.get("descriptor_id"), f"{label}.descriptor_id"),
        "role": _text(item.get("role"), f"{label}.role"),
        **{
            field: _identity_payload(item.get(field), f"{label}.{field}")
            for field in PACKER_PAYLOAD_FIELDS
        },
    }


def _contract_construction(
    value: object, label: str, expected_label: str
) -> dict[str, Any]:
    item = _mapping(value, label)
    expected_keys = {
        "label",
        "campaign_id",
        "test_id",
        "contract_id",
        "stage",
        "analysis",
        "action",
        "capture_sidecar",
        "jpeg",
        "packer",
    }
    try:
        require_exact_keys(item, expected_keys, label)
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    if item.get("label") != expected_label or item.get("stage") != "G3":
        raise FreshReconstructionCompareError(f"{label} role/stage differs")

    analysis = _mapping(item.get("analysis"), f"{label}.analysis")
    action = _mapping(item.get("action"), f"{label}.action")
    sidecar = _mapping(item.get("capture_sidecar"), f"{label}.capture_sidecar")
    jpeg = _mapping(item.get("jpeg"), f"{label}.jpeg")
    packer = _mapping(item.get("packer"), f"{label}.packer")
    exact_keys = (
        (analysis, {"file_sha256", "canonical_integrity_sha256"}, "analysis"),
        (
            action,
            {
                "ordinal",
                "action_id",
                "descriptor_id",
                "role",
                "file_sha256",
                "canonical_integrity_sha256",
            },
            "action",
        ),
        (
            sidecar,
            {"file_sha256", "canonical_integrity_sha256", "capture_id"},
            "capture_sidecar",
        ),
        (jpeg, {"file_sha256"}, "jpeg"),
        (
            packer,
            {"report_canonical_sha256", "core_actions"},
            "packer",
        ),
    )
    for mapping, keys, suffix in exact_keys:
        try:
            require_exact_keys(mapping, keys, f"{label}.{suffix}")
        except StaticPhotoContractError as error:
            raise _error_from_contract(error) from error

    core_values = packer.get("core_actions")
    if not isinstance(core_values, list) or len(core_values) != len(CORE_ORDINALS):
        raise FreshReconstructionCompareError(
            f"{label}.packer.core_actions must contain G1/G2/G3"
        )
    core = [
        _core_action(value, f"{label}.packer.core_actions[{index}]", ordinal)
        for index, (ordinal, value) in enumerate(
            zip(CORE_ORDINALS, core_values, strict=True)
        )
    ]
    action_value = {
        "ordinal": _integer(action.get("ordinal"), f"{label}.action.ordinal"),
        "action_id": _sha256(action.get("action_id"), f"{label}.action.action_id"),
        "descriptor_id": _sha256(
            action.get("descriptor_id"), f"{label}.action.descriptor_id"
        ),
        "role": _text(action.get("role"), f"{label}.action.role"),
        "file_sha256": _sha256(
            action.get("file_sha256"), f"{label}.action.file_sha256"
        ),
        "canonical_integrity_sha256": _sha256(
            action.get("canonical_integrity_sha256"),
            f"{label}.action.canonical_integrity_sha256",
        ),
    }
    if action_value["ordinal"] != 3 or any(
        action_value[key] != core[2][key]
        for key in ("ordinal", "action_id", "descriptor_id", "role")
    ):
        raise FreshReconstructionCompareError(
            f"{label} G3 action does not match packer core action"
        )
    return {
        "label": expected_label,
        "campaign_id": _text(item.get("campaign_id"), f"{label}.campaign_id"),
        "test_id": _text(item.get("test_id"), f"{label}.test_id"),
        "contract_id": _sha256(item.get("contract_id"), f"{label}.contract_id"),
        "stage": "G3",
        "analysis": {
            key: _sha256(analysis.get(key), f"{label}.analysis.{key}")
            for key in ("file_sha256", "canonical_integrity_sha256")
        },
        "action": action_value,
        "capture_sidecar": {
            "file_sha256": _sha256(
                sidecar.get("file_sha256"), f"{label}.capture_sidecar.file_sha256"
            ),
            "canonical_integrity_sha256": _sha256(
                sidecar.get("canonical_integrity_sha256"),
                f"{label}.capture_sidecar.canonical_integrity_sha256",
            ),
            "capture_id": _sha256(
                sidecar.get("capture_id"), f"{label}.capture_sidecar.capture_id"
            ),
        },
        "jpeg": {
            "file_sha256": _sha256(jpeg.get("file_sha256"), f"{label}.jpeg.file_sha256")
        },
        "packer": {
            "report_canonical_sha256": _sha256(
                packer.get("report_canonical_sha256"),
                f"{label}.packer.report_canonical_sha256",
            ),
            "core_actions": core,
        },
    }


def _validate_identity_contract(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    expected_keys = {
        "schema_version",
        "kind",
        "comparison_id",
        "first_construction",
        "fresh_reconstruction",
        "packer_isomorphism",
        "review_thresholds",
        "qualification_boundary",
    }
    try:
        require_exact_keys(unsigned, expected_keys, "identity contract")
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    if unsigned.get("schema_version") != SCHEMA_VERSION:
        raise FreshReconstructionCompareError("identity contract schema differs")
    if unsigned.get("kind") != IDENTITY_CONTRACT_KIND:
        raise FreshReconstructionCompareError("identity contract kind differs")
    comparison_id = _text(unsigned.get("comparison_id"), "comparison_id")
    first = _contract_construction(
        unsigned.get("first_construction"), "first_construction", FIRST_LABEL
    )
    reconstruction = _contract_construction(
        unsigned.get("fresh_reconstruction"),
        "fresh_reconstruction",
        RECONSTRUCTION_LABEL,
    )
    if first["campaign_id"] == reconstruction["campaign_id"]:
        raise FreshReconstructionCompareError("the two campaigns must be different")
    for key in ("action_id", "descriptor_id", "file_sha256"):
        if first["action"][key] == reconstruction["action"][key]:
            raise FreshReconstructionCompareError(
                f"the two G3 actions must have different {key}"
            )
    if first["analysis"]["file_sha256"] == reconstruction["analysis"]["file_sha256"]:
        raise FreshReconstructionCompareError("the two analysis files must differ")
    if (
        first["capture_sidecar"]["capture_id"]
        == reconstruction["capture_sidecar"]["capture_id"]
    ):
        raise FreshReconstructionCompareError("the two capture IDs must differ")
    if (
        first["packer"]["report_canonical_sha256"]
        == reconstruction["packer"]["report_canonical_sha256"]
    ):
        raise FreshReconstructionCompareError("the two packer reports must differ")

    isomorphism = _mapping(unsigned.get("packer_isomorphism"), "packer_isomorphism")
    try:
        require_exact_keys(
            isomorphism,
            {
                "method",
                "required_ordinals",
                "payload_fields",
                "bytewise_identity_required",
                "spatial_dithering_allowed",
            },
            "packer_isomorphism",
        )
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    if (
        isomorphism.get("method") != "PACKER_THREE_FRAME_BYTE_IDENTITY"
        or isomorphism.get("required_ordinals") != list(CORE_ORDINALS)
        or isomorphism.get("payload_fields") != list(PACKER_PAYLOAD_FIELDS)
        or isomorphism.get("bytewise_identity_required") is not True
        or isomorphism.get("spatial_dithering_allowed") is not False
    ):
        raise FreshReconstructionCompareError("packer isomorphism contract differs")
    equality: list[dict[str, Any]] = []
    for index, ordinal in enumerate(CORE_ORDINALS):
        for field in PACKER_PAYLOAD_FIELDS:
            left = first["packer"]["core_actions"][index][field]
            right = reconstruction["packer"]["core_actions"][index][field]
            if left != right:
                raise FreshReconstructionCompareError(
                    f"packer optical payload differs at G{ordinal}.{field}"
                )
            equality.append(
                {
                    "ordinal": ordinal,
                    "field": field,
                    "bytes": left["bytes"],
                    "sha256": left["sha256"],
                    "bytewise_isomorphic": True,
                }
            )

    thresholds = _mapping(unsigned.get("review_thresholds"), "review_thresholds")
    try:
        require_exact_keys(
            thresholds, set(DEFAULT_REVIEW_THRESHOLDS), "review_thresholds"
        )
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    threshold_values = {
        key: _finite(thresholds.get(key), f"review_thresholds.{key}", positive=True)
        for key in DEFAULT_REVIEW_THRESHOLDS
    }

    boundary = _mapping(
        unsigned.get("qualification_boundary"), "qualification_boundary"
    )
    wanted_boundary = {
        "camera_relative_review_only": True,
        "controller_palette_evidence_pass_forbidden": True,
        "automatic_colour_or_gray_claim_forbidden": True,
        "qualified_colour_count": 0,
        "qualified_gray_levels": 0,
        "qualified_lightness_levels": 0,
    }
    if dict(boundary) != wanted_boundary:
        raise FreshReconstructionCompareError(
            "identity contract qualification boundary differs"
        )
    return {
        "comparison_id": comparison_id,
        "first": first,
        "reconstruction": reconstruction,
        "isomorphism_equality": equality,
        "thresholds": threshold_values,
    }


def seal_fresh_reconstruction_identity_contract(
    unsigned_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and canonically seal an explicit future identity contract."""

    if "integrity" in unsigned_contract:
        raise FreshReconstructionCompareError(
            "unsigned identity contract must not contain integrity"
        )
    _validate_identity_contract(unsigned_contract)
    try:
        return attach_integrity(unsigned_contract)
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error


def _verify_contract(
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        unsigned = verify_integrity(contract, "fresh reconstruction identity contract")
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    return unsigned, _validate_identity_contract(unsigned)


def _bound_source(
    analysis_path: Path,
    record: object,
    *,
    label: str,
    expected_sha256: str,
) -> tuple[Path, bytes, Mapping[str, Any]]:
    item = _mapping(record, label)
    path = _resolve_source_path(analysis_path, item.get("path"), label=label)
    payload = _read_stable(path, label=label)
    digest = hashlib.sha256(payload).hexdigest()
    if (
        item.get("bytes") != len(payload)
        or item.get("file_sha256") != digest
        or digest != expected_sha256
    ):
        raise FreshReconstructionCompareError(f"{label} byte/hash binding differs")
    return path, payload, item


def _camera_lock_from_sidecar(sidecar: Mapping[str, Any], label: str) -> dict[str, Any]:
    camera = _mapping(sidecar.get("camera"), f"{label}.camera")
    coverage = _mapping(sidecar.get("coverage"), f"{label}.coverage")
    requested = _mapping(
        camera.get("requested_settings"), f"{label}.camera.requested_settings"
    )
    before = _mapping(
        camera.get("effective_settings_before_frame"),
        f"{label}.camera.effective_settings_before_frame",
    )
    after = _mapping(
        camera.get("effective_settings_after_frame"),
        f"{label}.camera.effective_settings_after_frame",
    )
    set_results = _mapping(camera.get("set_results"), f"{label}.camera.set_results")
    instance = _text(camera.get("instance_id"), f"{label}.camera.instance_id")
    if (
        camera.get("camera_id") != "48MP USB Camera"
        or "vid_32e4&pid_4801" not in instance.casefold()
        or "vid_1bcf&pid_0b15" in instance.casefold()
        or str(camera.get("backend", "")).casefold() != "dshow"
        or type(camera.get("index")) is not int
    ):
        raise FreshReconstructionCompareError(f"{label} is not the project 48MP camera")
    for settings_label, settings in (
        ("requested", requested),
        ("effective_before", before),
        ("effective_after", after),
    ):
        if settings.get("frame_width") != 4000 or settings.get("frame_height") != 3000:
            raise FreshReconstructionCompareError(
                f"{label} {settings_label} dimensions are not 4000x3000"
            )
    required_writes = {key for key, value in requested.items() if value is not None}
    if not required_writes or any(
        set_results.get(key) is not True for key in required_writes
    ):
        raise FreshReconstructionCompareError(f"{label} camera setting writes differ")
    coverage_scope = coverage.get("scope")
    full_expected = coverage_scope == "full_panel"
    if (
        sidecar.get("capture_binding") != "live_synchronized"
        or sidecar.get("ordinal") != 3
        or coverage_scope not in {"full_panel", "partial_panel"}
        or coverage.get("full_panel_visible") is not full_expected
        or coverage.get("full_panel_uncropped") is not full_expected
    ):
        raise FreshReconstructionCompareError(
            f"{label} capture/coverage boundary differs"
        )
    return {
        "camera_id": camera["camera_id"],
        "camera_instance_id": camera["instance_id"],
        "camera_usb_identity": PROJECT_CAMERA_USB_ID,
        "camera_index": camera["index"],
        "backend": camera["backend"],
        "requested_settings": deepcopy(dict(requested)),
        "effective_settings_before_frame": deepcopy(dict(before)),
        "effective_settings_after_frame": deepcopy(dict(after)),
        "setting_write_results": deepcopy(dict(set_results)),
        "manual_focus_exposure_white_balance_gate": True,
        "mount_id": _text(coverage.get("mount_id"), f"{label}.coverage.mount_id"),
        "full_panel_visible": full_expected,
        "coverage_scope": coverage_scope,
    }


def _validate_deep_sources(
    analysis_path: Path,
    analysis: Mapping[str, Any],
    expected: Mapping[str, Any],
    label: str,
) -> tuple[dict[str, Any], dict[str, Path]]:
    source = _mapping(analysis.get("source_evidence"), f"{label}.source_evidence")
    paths: dict[str, Path] = {}
    path, action_payload, action_record = _bound_source(
        analysis_path,
        source.get("action"),
        label=f"{label} action",
        expected_sha256=expected["action"]["file_sha256"],
    )
    paths["action"] = path
    action_root = _json(action_payload, f"{label} action")
    _action_body, action_canonical = _verify_analyzer_seal(
        action_root, f"{label} action"
    )
    if (
        action_canonical != expected["action"]["canonical_integrity_sha256"]
        or action_record.get("canonical_integrity_sha256") != action_canonical
    ):
        raise FreshReconstructionCompareError(
            f"{label} action canonical binding differs"
        )
    action_identity = _mapping(action_root.get("action"), f"{label} action.action")
    if any(
        action_identity.get(key) != expected["action"][key]
        for key in ("ordinal", "action_id", "descriptor_id", "role")
    ):
        raise FreshReconstructionCompareError(f"{label} action identity differs")
    terminal = _mapping(action_root.get("terminal_report"), f"{label} terminal_report")
    if any(
        terminal.get(key) != expected[key]
        for key in ("campaign_id", "test_id", "contract_id")
    ):
        raise FreshReconstructionCompareError(
            f"{label} action campaign binding differs"
        )

    path, sidecar_payload, sidecar_record = _bound_source(
        analysis_path,
        source.get("capture_sidecar"),
        label=f"{label} capture sidecar",
        expected_sha256=expected["capture_sidecar"]["file_sha256"],
    )
    paths["capture_sidecar"] = path
    sidecar_root = _json(sidecar_payload, f"{label} capture sidecar")
    _sidecar_body, sidecar_canonical = _verify_analyzer_seal(
        sidecar_root, f"{label} capture sidecar"
    )
    if (
        sidecar_canonical != expected["capture_sidecar"]["canonical_integrity_sha256"]
        or sidecar_record.get("canonical_integrity_sha256") != sidecar_canonical
        or sidecar_root.get("capture_id") != expected["capture_sidecar"]["capture_id"]
        or sidecar_record.get("capture_id") != expected["capture_sidecar"]["capture_id"]
    ):
        raise FreshReconstructionCompareError(
            f"{label} sidecar canonical binding differs"
        )
    if any(
        sidecar_root.get(key) != expected[key]
        for key in ("campaign_id", "test_id", "contract_id")
    ) or any(
        sidecar_root.get(key) != expected["action"][key]
        for key in ("ordinal", "action_id", "descriptor_id", "role")
    ):
        raise FreshReconstructionCompareError(f"{label} sidecar identity differs")

    path, _photo_payload, photo_record = _bound_source(
        analysis_path,
        source.get("photo"),
        label=f"{label} JPEG",
        expected_sha256=expected["jpeg"]["file_sha256"],
    )
    paths["photo"] = path
    sidecar_action = _mapping(
        sidecar_root.get("action_result"), f"{label} sidecar.action_result"
    )
    sidecar_photo = _mapping(sidecar_root.get("photo"), f"{label} sidecar.photo")
    sidecar_path = paths["capture_sidecar"]
    if (
        _resolve_source_path(
            sidecar_path, sidecar_action.get("path"), label="action_result"
        )
        != paths["action"]
        or sidecar_action.get("file_sha256") != expected["action"]["file_sha256"]
        or sidecar_action.get("canonical_integrity_sha256")
        != expected["action"]["canonical_integrity_sha256"]
        or _resolve_source_path(sidecar_path, sidecar_photo.get("path"), label="photo")
        != paths["photo"]
        or sidecar_photo.get("sha256") != expected["jpeg"]["file_sha256"]
        or photo_record.get("file_sha256") != expected["jpeg"]["file_sha256"]
    ):
        raise FreshReconstructionCompareError(f"{label} sidecar source paths differ")
    lock = _camera_lock_from_sidecar(sidecar_root, f"{label} sidecar")
    legacy_lock = dict(lock)
    legacy_lock.pop("coverage_scope")
    if analysis.get("camera_lock") not in (lock, legacy_lock):
        raise FreshReconstructionCompareError(f"{label} analysis camera lock differs")
    return lock, paths


def _cell_identity(cell: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "sample_id",
        "controller",
        "recipe",
        "repeat_position",
        "row",
        "column",
        "local_roi",
        "panel_roi",
        "central_inset_fraction",
    )
    return {key: deepcopy(cell.get(key)) for key in keys}


def _measurements(analysis: Mapping[str, Any], label: str) -> dict[str, dict[str, Any]]:
    observation = _mapping(
        analysis.get("observation_document"), f"{label}.observation_document"
    )
    _observation_body, _observation_sha = _verify_analyzer_seal(
        observation, f"{label}.observation_document"
    )
    if (
        observation.get("stage") != "G3"
        or observation.get("controller_policy") != "CS1_AND_CS2_EVALUATED_SEPARATELY"
        or observation.get("spatial_dither") is not False
        or observation.get("qualified_colour_count") != 0
        or observation.get("qualified_gray_levels") != 0
        or observation.get("qualified_brightness_levels") != 0
        or observation.get("automatic_colour_qualification") is not False
    ):
        raise FreshReconstructionCompareError(f"{label} observation boundary differs")
    raw = observation.get("measurements")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 128:
        raise FreshReconstructionCompareError(
            f"{label} must contain between 1 and 128 visible cells"
        )
    result: dict[str, dict[str, Any]] = {}
    physical: set[tuple[str, int, int]] = set()
    counts = {
        (controller, recipe): 0 for controller in CONTROLLERS for recipe in range(16)
    }
    for index, value in enumerate(raw):
        cell = _mapping(value, f"{label}.measurements[{index}]")
        controller = cell.get("controller")
        recipe = cell.get("recipe")
        repeat = cell.get("repeat_position")
        row = cell.get("row")
        column = cell.get("column")
        if (
            controller not in CONTROLLERS
            or type(recipe) is not int
            or recipe not in range(RECIPE_COUNT)
            or type(repeat) is not int
            or repeat not in range(REPLICAS_PER_RECIPE)
            or type(row) is not int
            or row not in range(8)
            or type(column) is not int
            or column not in range(8)
        ):
            raise FreshReconstructionCompareError(f"{label} cell identity differs")
        sample_id = f"{controller}-R{recipe:02d}-P{repeat}"
        if cell.get("sample_id") != sample_id or sample_id in result:
            raise FreshReconstructionCompareError(f"{label} sample identity differs")
        position = (str(controller), row, column)
        if position in physical:
            raise FreshReconstructionCompareError(
                f"{label} physical cell is duplicated"
            )
        physical.add(position)
        flags = (
            "bottom_edge_clean",
            "horizontal_stripe_absent",
            "vertical_stripe_absent",
            "roi_visible",
        )
        if any(type(cell.get(flag)) is not bool for flag in flags):
            raise FreshReconstructionCompareError(f"{label} edge flag differs")
        result[sample_id] = {
            "identity": _cell_identity(cell),
            "lab": _lab(cell.get("lab"), f"{label}.{sample_id}.lab"),
            "boundary_clear": all(cell.get(flag) is True for flag in flags),
        }
        counts[(str(controller), recipe)] += 1
    if any(value > REPLICAS_PER_RECIPE for value in counts.values()):
        raise FreshReconstructionCompareError(f"{label} recipe replica count differs")
    return result


def _geometry_signature(
    analysis: Mapping[str, Any], cells: Mapping[str, Any], label: str
) -> dict[str, Any]:
    geometry = _mapping(analysis.get("geometry"), f"{label}.geometry")
    quality = _mapping(analysis.get("capture_quality"), f"{label}.capture_quality")
    for key in (
        "geometry_gate_pass",
        "manual_camera_lock_gate_pass",
        "exposure_gate_pass",
        "coarse_uniformity_gate_pass",
    ):
        if quality.get(key) is not True:
            raise FreshReconstructionCompareError(
                f"{label} capture quality {key} failed"
            )
    if geometry.get("gate_pass") is not True:
        raise FreshReconstructionCompareError(f"{label} geometry gate failed")
    method = _mapping(analysis.get("method"), f"{label}.method")
    if (
        method.get("controllers_pooled") is not False
        or method.get("spatial_dither") is not False
    ):
        raise FreshReconstructionCompareError(f"{label} method boundary differs")
    thresholds = _mapping(
        analysis.get("quality_thresholds"), f"{label}.quality_thresholds"
    )
    observation = _mapping(
        analysis.get("observation_document"), f"{label}.observation_document"
    )
    return {
        "sampling_method": geometry.get("method"),
        "method": deepcopy(dict(method)),
        "quality_thresholds": deepcopy(dict(thresholds)),
        "observation_thresholds": deepcopy(
            dict(_mapping(observation.get("thresholds"), f"{label}.thresholds"))
        ),
        "roi_manifest_sha256": _sha256(
            observation.get("roi_manifest_sha256"), f"{label}.roi_manifest_sha256"
        ),
        "reference_geometry_origin": geometry.get("reference_geometry_origin"),
        "reference_report_canonical_sha256": (
            geometry.get("reference_report", {}).get("canonical_integrity_sha256")
            if isinstance(geometry.get("reference_report"), Mapping)
            else None
        ),
        "logical_cells": [cells[sample_id]["identity"] for sample_id in sorted(cells)],
        "visible_cell_count": len(cells),
        "full_128_cell_coverage": len(cells) == 128,
    }


def _validate_analysis(
    path: Path, expected: Mapping[str, Any], label: str
) -> dict[str, Any]:
    path = Path(path).resolve()
    payload, analysis, canonical = _sealed_json_file(path, label=label)
    if (
        hashlib.sha256(payload).hexdigest() != expected["analysis"]["file_sha256"]
        or canonical != expected["analysis"]["canonical_integrity_sha256"]
    ):
        raise FreshReconstructionCompareError(f"{label} analysis hash binding differs")
    identity = {
        "schema_version": SCHEMA_VERSION,
        "kind": ANALYSIS_KIND,
        "campaign_id": expected["campaign_id"],
        "test_id": expected["test_id"],
        "contract_id": expected["contract_id"],
        "stage": "G3",
        "hardware_accessed": False,
        "camera_accessed": False,
        "network_requests": 0,
    }
    mismatch = [key for key, value in identity.items() if analysis.get(key) != value]
    if mismatch:
        raise FreshReconstructionCompareError(f"{label} identity differs: {mismatch}")
    qualification = _mapping(
        analysis.get("qualification_boundary"), f"{label}.qualification_boundary"
    )
    if (
        qualification.get("absolute_colour_claimed") is not False
        or qualification.get("cross_controller_equivalence_claimed") is not False
        or qualification.get("qualified_colour_count") != 0
        or qualification.get("qualified_gray_levels") != 0
        or qualification.get("qualified_brightness_levels") != 0
    ):
        raise FreshReconstructionCompareError(f"{label} qualification boundary differs")
    screen = _mapping(
        analysis.get("controller_local_screen"), f"{label}.controller_local_screen"
    )
    if (
        screen.get("controller_policy") != "CS1_AND_CS2_NEVER_POOLED"
        or screen.get("recipes_per_controller") != RECIPE_COUNT
        or screen.get("replicates_per_recipe") != REPLICAS_PER_RECIPE
        or screen.get("qualified_colour_count") != 0
        or screen.get("qualified_gray_levels") != 0
        or screen.get("qualified_brightness_levels") != 0
    ):
        raise FreshReconstructionCompareError(f"{label} controller screen differs")
    lock, source_paths = _validate_deep_sources(path, analysis, expected, label)
    cells = _measurements(analysis, label)
    visible_by_controller = {
        controller: sum(
            cell["identity"]["controller"] == controller for cell in cells.values()
        )
        for controller in CONTROLLERS
    }
    if lock["coverage_scope"] == "full_panel" and len(cells) != 128:
        raise FreshReconstructionCompareError(
            f"{label} full-panel capture must contain all 128 cells"
        )
    if lock["coverage_scope"] == "partial_panel" and (
        len(cells) < 24 or any(count < 8 for count in visible_by_controller.values())
    ):
        raise FreshReconstructionCompareError(
            f"{label} partial geometry support is below 24 total / 8 per controller"
        )
    geometry = _geometry_signature(analysis, cells, label)
    return {
        "path": path,
        "payload": payload,
        "analysis": analysis,
        "canonical_sha256": canonical,
        "camera_lock": lock,
        "source_paths": source_paths,
        "cells": cells,
        "geometry_signature": geometry,
    }


def _compare_camera_and_geometry(
    first: Mapping[str, Any], reconstruction: Mapping[str, Any]
) -> None:
    lock_fields = (
        "camera_id",
        "camera_instance_id",
        "camera_usb_identity",
        "camera_index",
        "backend",
        "requested_settings",
        "effective_settings_before_frame",
        "effective_settings_after_frame",
        "mount_id",
        "coverage_scope",
    )
    if any(
        first["camera_lock"][key] != reconstruction["camera_lock"][key]
        for key in lock_fields
    ):
        raise FreshReconstructionCompareError(
            "camera identity/index/backend/mount or requested/effective settings differ"
        )
    if first["camera_lock"]["camera_usb_identity"] != PROJECT_CAMERA_USB_ID:
        raise FreshReconstructionCompareError("project camera identity differs")
    if set(first["cells"]) != set(reconstruction["cells"]):
        raise FreshReconstructionCompareError(
            "fresh reconstruction visible sample IDs differ"
        )
    if any(
        first["cells"][sample_id]["identity"]
        != reconstruction["cells"][sample_id]["identity"]
        for sample_id in first["cells"]
    ):
        raise FreshReconstructionCompareError(
            "fresh reconstruction visible cell positions differ"
        )
    if first["geometry_signature"] != reconstruction["geometry_signature"]:
        raise FreshReconstructionCompareError("logical sampling geometry differs")
    if first["path"] == reconstruction["path"]:
        raise FreshReconstructionCompareError("analysis paths must be different")
    for source in ("action", "capture_sidecar", "photo"):
        if first["source_paths"][source] == reconstruction["source_paths"][source]:
            raise FreshReconstructionCompareError(
                f"the two constructions reuse the same {source} file"
            )


def _center_by_controller(
    cells: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[float, float, float]]:
    result = {}
    for controller in CONTROLLERS:
        labs = [
            cell["lab"]
            for cell in cells.values()
            if cell["identity"]["controller"] == controller
        ]
        if not labs:
            raise FreshReconstructionCompareError(
                f"{controller} has no visible measurements"
            )
        result[controller] = tuple(
            _median([lab[channel] for lab in labs]) for channel in range(3)
        )
    return result  # type: ignore[return-value]


def _comparison_results(
    first: Mapping[str, Any],
    reconstruction: Mapping[str, Any],
    thresholds: Mapping[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    first_cells = first["cells"]
    reconstruction_cells = reconstruction["cells"]
    if set(first_cells) != set(reconstruction_cells):
        raise FreshReconstructionCompareError("fresh reconstruction sample IDs differ")
    for sample_id in first_cells:
        if (
            first_cells[sample_id]["identity"]
            != reconstruction_cells[sample_id]["identity"]
        ):
            raise FreshReconstructionCompareError(
                f"fresh reconstruction position differs for {sample_id}"
            )

    first_center = _center_by_controller(first_cells)
    reconstruction_center = _center_by_controller(reconstruction_cells)
    cell_results: list[dict[str, Any]] = []
    for sample_id in sorted(first_cells):
        left = first_cells[sample_id]
        right = reconstruction_cells[sample_id]
        identity = left["identity"]
        controller = identity["controller"]
        left_centered = tuple(
            left["lab"][index] - first_center[controller][index] for index in range(3)
        )
        right_centered = tuple(
            right["lab"][index] - reconstruction_center[controller][index]
            for index in range(3)
        )
        delta = tuple(
            right_centered[index] - left_centered[index] for index in range(3)
        )
        cell_results.append(
            {
                **identity,
                "first_centered_lab": list(left_centered),
                "reconstruction_centered_lab": list(right_centered),
                "centered_delta_lab": list(delta),
                "centered_delta_l_star": delta[0],
                "absolute_centered_delta_l_star": abs(delta[0]),
                "centered_delta_e76": math.sqrt(sum(value * value for value in delta)),
                "first_boundary_clear": left["boundary_clear"],
                "reconstruction_boundary_clear": right["boundary_clear"],
                "position_matched": True,
                "qualified_level": False,
            }
        )

    recipe_results: list[dict[str, Any]] = []
    controller_results: dict[str, Any] = {}
    for controller in CONTROLLERS:
        controller_cells = [
            cell for cell in cell_results if cell["controller"] == controller
        ]
        for recipe in range(RECIPE_COUNT):
            cells = [cell for cell in controller_cells if cell["recipe"] == recipe]
            if len(cells) != REPLICAS_PER_RECIPE:
                recipe_results.append(
                    {
                        "controller": controller,
                        "controller_local_only": True,
                        "recipe": recipe,
                        "middle_code": recipe % 8,
                        "target_code": 3 if recipe < 8 else 7,
                        "sample_ids": sorted(cell["sample_id"] for cell in cells),
                        "replica_count": len(cells),
                        "required_replica_count": REPLICAS_PER_RECIPE,
                        "status": "UNTESTED_MISSING_REPLICAS",
                        "median_centered_delta_l_star": None,
                        "median_absolute_centered_delta_l_star": None,
                        "median_centered_delta_e76": None,
                        "first_maximum_position_delta_e76": None,
                        "reconstruction_maximum_position_delta_e76": None,
                        "boundary_gate_pass": False,
                        "single_pixel_purity_gate_pass": False,
                        "reconstruction_metric_gate_pass": False,
                        "fresh_reconstruction_review_gate_pass": False,
                        "qualified_level": False,
                        "controller_palette_evidence_passed": False,
                    }
                )
                continue
            if {cell["repeat_position"] for cell in cells} != set(
                range(REPLICAS_PER_RECIPE)
            ):
                raise FreshReconstructionCompareError(
                    f"{controller} recipe {recipe} replica positions differ"
                )
            sample_ids = [cell["sample_id"] for cell in cells]
            first_labs = [first_cells[sample_id]["lab"] for sample_id in sample_ids]
            reconstruction_labs = [
                reconstruction_cells[sample_id]["lab"] for sample_id in sample_ids
            ]
            first_position_de = max(
                _delta_e(left, right) for left in first_labs for right in first_labs
            )
            reconstruction_position_de = max(
                _delta_e(left, right)
                for left in reconstruction_labs
                for right in reconstruction_labs
            )
            boundary_pass = all(
                cell["first_boundary_clear"] and cell["reconstruction_boundary_clear"]
                for cell in cells
            )
            purity_pass = (
                first_position_de
                <= thresholds["maximum_within_recipe_position_delta_e76"]
                and reconstruction_position_de
                <= thresholds["maximum_within_recipe_position_delta_e76"]
            )
            median_signed_l = _median([cell["centered_delta_l_star"] for cell in cells])
            median_abs_l = _median(
                [cell["absolute_centered_delta_l_star"] for cell in cells]
            )
            median_de = _median([cell["centered_delta_e76"] for cell in cells])
            metric_pass = (
                median_abs_l <= thresholds["maximum_recipe_median_abs_delta_l_star"]
                and median_de <= thresholds["maximum_recipe_median_delta_e76"]
            )
            recipe_results.append(
                {
                    "controller": controller,
                    "controller_local_only": True,
                    "recipe": recipe,
                    "middle_code": recipe % 8,
                    "target_code": 3 if recipe < 8 else 7,
                    "sample_ids": sorted(sample_ids),
                    "replica_count": REPLICAS_PER_RECIPE,
                    "required_replica_count": REPLICAS_PER_RECIPE,
                    "status": "REVIEWED_COMPLETE_REPLICA_SET",
                    "median_centered_delta_l_star": median_signed_l,
                    "median_absolute_centered_delta_l_star": median_abs_l,
                    "median_centered_delta_e76": median_de,
                    "first_maximum_position_delta_e76": first_position_de,
                    "reconstruction_maximum_position_delta_e76": (
                        reconstruction_position_de
                    ),
                    "boundary_gate_pass": boundary_pass,
                    "single_pixel_purity_gate_pass": purity_pass,
                    "reconstruction_metric_gate_pass": metric_pass,
                    "fresh_reconstruction_review_gate_pass": (
                        boundary_pass and purity_pass and metric_pass
                    ),
                    "qualified_level": False,
                    "controller_palette_evidence_passed": False,
                }
            )
        recipes = [item for item in recipe_results if item["controller"] == controller]
        l_p95 = _p95(
            [cell["absolute_centered_delta_l_star"] for cell in controller_cells]
        )
        de_p95 = _p95([cell["centered_delta_e76"] for cell in controller_cells])
        aggregate_gate = (
            l_p95 <= thresholds["maximum_controller_cell_centered_abs_delta_l_star_p95"]
            and de_p95 <= thresholds["maximum_controller_cell_centered_delta_e76_p95"]
        )
        controller_results[controller] = {
            "controller": controller,
            "controller_local_only": True,
            "visible_cell_count": len(controller_cells),
            "recipe_count": RECIPE_COUNT,
            "reviewed_complete_recipe_count": sum(
                item["status"] == "REVIEWED_COMPLETE_REPLICA_SET" for item in recipes
            ),
            "untested_missing_replica_recipe_count": sum(
                item["status"] == "UNTESTED_MISSING_REPLICAS" for item in recipes
            ),
            "cell_centered_absolute_delta_l_star_p95": l_p95,
            "cell_centered_delta_e76_p95": de_p95,
            "aggregate_metric_gate_pass": aggregate_gate,
            "all_recipe_gates_pass": all(
                item["fresh_reconstruction_review_gate_pass"] for item in recipes
            ),
            "fresh_reconstruction_review_pass": (
                aggregate_gate
                and all(
                    item["status"] == "REVIEWED_COMPLETE_REPLICA_SET"
                    and item["fresh_reconstruction_review_gate_pass"]
                    for item in recipes
                )
            ),
            "qualified_level_count": 0,
        }
    return cell_results, recipe_results, controller_results


def compare_fresh_white_reconstruction(
    first_analysis_path: str | Path,
    reconstruction_analysis_path: str | Path,
    *,
    identity_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare two independently constructed, optically isomorphic G3 grids."""

    contract_unsigned, contract = _verify_contract(identity_contract)
    first = _validate_analysis(
        Path(first_analysis_path), contract["first"], "first construction G3"
    )
    reconstruction = _validate_analysis(
        Path(reconstruction_analysis_path),
        contract["reconstruction"],
        "fresh reconstruction G3",
    )
    _compare_camera_and_geometry(first, reconstruction)
    cell_results, recipe_results, controller_results = _comparison_results(
        first, reconstruction, contract["thresholds"]
    )
    review_pass = all(
        controller_results[controller]["fresh_reconstruction_review_pass"]
        for controller in CONTROLLERS
    )
    source_reports = {
        "first_construction_g3": {
            "path": str(first["path"]),
            "bytes": len(first["payload"]),
            "file_sha256": hashlib.sha256(first["payload"]).hexdigest(),
            "canonical_integrity_sha256": first["canonical_sha256"],
            "campaign_id": contract["first"]["campaign_id"],
            "action_id": contract["first"]["action"]["action_id"],
        },
        "fresh_reconstruction_g3": {
            "path": str(reconstruction["path"]),
            "bytes": len(reconstruction["payload"]),
            "file_sha256": hashlib.sha256(reconstruction["payload"]).hexdigest(),
            "canonical_integrity_sha256": reconstruction["canonical_sha256"],
            "campaign_id": contract["reconstruction"]["campaign_id"],
            "action_id": contract["reconstruction"]["action"]["action_id"],
        },
    }
    draft_input_binding = canonical_sha256(
        {
            "identity_contract_canonical_sha256": canonical_sha256(contract_unsigned),
            "source_reports": source_reports,
        }
    )
    draft_recipes = [
        {
            "controller": item["controller"],
            "recipe": item["recipe"],
            "middle_code": item["middle_code"],
            "target_code": item["target_code"],
            "comparison_input_binding_sha256": draft_input_binding,
            "review_gate_pass": item["fresh_reconstruction_review_gate_pass"],
            "proposed_evidence_role": "FRESH_WHITE_RECONSTRUCTION",
            "status": "DRAFT_REQUIRES_HUMAN_AND_CALIBRATION_GATE",
            "controller_palette_evidence_passed": False,
        }
        for item in recipe_results
    ]
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": COMPARISON_KIND,
        "comparison_id": contract["comparison_id"],
        "decision": (
            "FRESH_RECONSTRUCTION_REVIEW_PASS"
            if review_pass
            else "FRESH_RECONSTRUCTION_REVIEW_FAIL"
        ),
        "offline_only": True,
        "identity_contract": {
            "canonical_sha256": canonical_sha256(contract_unsigned),
            "comparison_id": contract["comparison_id"],
        },
        "source_reports": source_reports,
        "packer_isomorphism_proof": {
            "three_core_frames_proven": True,
            "different_campaigns": True,
            "different_g3_actions": True,
            "first_packer_report_canonical_sha256": contract["first"]["packer"][
                "report_canonical_sha256"
            ],
            "reconstruction_packer_report_canonical_sha256": contract["reconstruction"][
                "packer"
            ]["report_canonical_sha256"],
            "payload_equalities": contract["isomorphism_equality"],
        },
        "comparability": {
            "same_48mp_camera": True,
            "same_camera_instance": True,
            "same_camera_index": True,
            "same_backend": True,
            "same_mount": True,
            "image_dimensions": [4000, 3000],
            "coverage_scope": first["camera_lock"]["coverage_scope"],
            "full_128_cell_mode_preferred": True,
            "visible_cell_count": len(cell_results),
            "full_128_cell_coverage": len(cell_results) == 128,
            "requested_settings_exactly_equal": True,
            "effective_settings_before_frame_exactly_equal": True,
            "effective_settings_after_frame_exactly_equal": True,
            "logical_geometry_equivalent": True,
            "position_matched_four_replicas_per_recipe": True,
            "controllers_pooled": False,
            "cross_controller_comparison_used": False,
        },
        "review_thresholds": contract["thresholds"],
        "controller_results": controller_results,
        "recipe_results": recipe_results,
        "cell_results": cell_results,
        "evidence_draft": {
            "kind": "MF1750_FRESH_WHITE_RECONSTRUCTION_EVIDENCE_DRAFT",
            "status": "REVIEW_DRAFT_ONLY_NOT_QUALIFICATION_EVIDENCE",
            "recipes": draft_recipes,
            "direct_controller_palette_evidence_conversion_allowed": False,
            "required_next_gates": [
                "HUMAN_REVIEW",
                "CALIBRATED_COLOUR_OR_LIGHTNESS_MEASUREMENT",
                "CONTROLLER_LOCAL_INVENTORY_BINDING",
            ],
        },
        "qualification_boundary": {
            "review_pass_is_not_palette_qualification": True,
            "controller_palette_evidence_passed": False,
            "automatic_colour_claimed": False,
            "automatic_gray_claimed": False,
            "automatic_lightness_claimed": False,
            "qualified_colour_count": 0,
            "qualified_gray_levels": 0,
            "qualified_lightness_levels": 0,
            "spatial_dithering_used": False,
        },
        "execution_boundary": {
            "hardware_accessed": False,
            "camera_accessed": False,
            "network_accessed": False,
            "relay_or_j2_operated": False,
            "display_refresh_requested": False,
            "live_authorization_generated": False,
        },
    }
    return attach_integrity(unsigned)


def verify_fresh_reconstruction_comparison(
    mapping: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify canonical integrity and immutable qualification/execution limits."""

    try:
        unsigned = verify_integrity(mapping, "fresh reconstruction comparison")
    except StaticPhotoContractError as error:
        raise _error_from_contract(error) from error
    if (
        unsigned.get("schema_version") != SCHEMA_VERSION
        or unsigned.get("kind") != COMPARISON_KIND
        or unsigned.get("decision")
        not in {
            "FRESH_RECONSTRUCTION_REVIEW_PASS",
            "FRESH_RECONSTRUCTION_REVIEW_FAIL",
        }
    ):
        raise FreshReconstructionCompareError("comparison identity differs")
    qualification = _mapping(
        unsigned.get("qualification_boundary"), "qualification_boundary"
    )
    if (
        qualification.get("controller_palette_evidence_passed") is not False
        or qualification.get("qualified_colour_count") != 0
        or qualification.get("qualified_gray_levels") != 0
        or qualification.get("qualified_lightness_levels") != 0
        or qualification.get("spatial_dithering_used") is not False
    ):
        raise FreshReconstructionCompareError(
            "comparison qualification boundary differs"
        )
    execution = _mapping(unsigned.get("execution_boundary"), "execution_boundary")
    if any(value is not False for value in execution.values()):
        raise FreshReconstructionCompareError("comparison execution boundary differs")
    draft = _mapping(unsigned.get("evidence_draft"), "evidence_draft")
    if draft.get("direct_controller_palette_evidence_conversion_allowed") is not False:
        raise FreshReconstructionCompareError(
            "evidence draft conversion boundary differs"
        )
    return unsigned


def export_fresh_reconstruction_comparison(
    mapping: Mapping[str, Any],
    path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Export a verified comparison as deterministic review JSON."""

    verify_fresh_reconstruction_comparison(mapping)
    output = Path(path)
    if output.exists() and not overwrite:
        raise FreshReconstructionCompareError("output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            mapping,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


__all__ = [
    "ANALYSIS_KIND",
    "COMPARISON_KIND",
    "DEFAULT_REVIEW_THRESHOLDS",
    "FIRST_LABEL",
    "FreshReconstructionCompareError",
    "IDENTITY_CONTRACT_KIND",
    "RECONSTRUCTION_LABEL",
    "compare_fresh_white_reconstruction",
    "export_fresh_reconstruction_comparison",
    "seal_fresh_reconstruction_identity_contract",
    "verify_fresh_reconstruction_comparison",
]
