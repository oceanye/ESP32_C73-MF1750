#!/usr/bin/env python3
"""Build a fail-closed G1/S1 experimental panel-candidate evidence bundle.

The default and normal mode is entirely offline.  Supplying ``--url`` adds
one non-displaying frame-ingress integrity check; it never authorizes a panel
operation.  Every output remains experimental, uncalibrated, and non-formal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import sys
from typing import Any, Callable, Mapping, Optional, Sequence
import urllib.error
import urllib.parse
import urllib.request
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.application.simulation import (  # noqa: E402
    SIMULATION_REPORT_HASH_SCOPE,
    SimulationAlgorithm,
    SimulationBudget,
    SimulationOptions,
    SimulationResult,
    simulate_panel,
    validate_simulation_report,
)
from host.application.images import (  # noqa: E402
    FitPolicy,
    ImageDecodeError,
    decode_normalized_source,
)
from host.color_pipeline import RasterImage, reference_palette  # noqa: E402
from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    ControllerMapping,
    controller_stream,
    fnv1a,
    unpack_pixels,
    validate_frame,
)
from host.gamut_mapping import (  # noqa: E402
    MappingOptions,
    build_synthetic_reference_profile,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


MANIFEST_SCHEMA_VERSION = 1
PHOTO_MANIFEST_SCHEMA_VERSION = 2
MANIFEST_KIND = "mf1750-g1-s1-experimental-panel-candidate"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
SOURCE_PATTERN_ID = "g1-s1-mix-gradient-edge-v1"
PHOTO_SOURCE_KIND = "decoded-normalized-image-v2"
SOURCE_INPUT_FILENAME = "source.input"
INGRESS_ENDPOINT = "/api/diagnostic/frame-ingress"
DEFAULT_SEED = 0x4D463137
DEFAULT_DBS_EVALUATIONS = 1024
MAX_DBS_EVALUATIONS = 1_000_000
PREVIEW_FILES = {
    "source": "source.png",
    "mapped": "mapped.png",
    "final": "final.png",
    "model": "model.png",
}
REQUIRED_FILES = frozenset({"frame.bin", "manifest.json", *PREVIEW_FILES.values()})
PHOTO_REQUIRED_FILES = frozenset({*REQUIRED_FILES, SOURCE_INPUT_FILENAME})
CONTROLLER_MAPPINGS = (ControllerMapping(0), ControllerMapping(1))
ALLOWED_ALGORITHMS = frozenset(
    {
        SimulationAlgorithm.ATKINSON,
        SimulationAlgorithm.AREA_WEIGHTED_ORDERED,
        SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
        SimulationAlgorithm.MULTICOLOR_DBS,
        SimulationAlgorithm.OVERLAP_AWARE_DBS,
    }
)
DBS_ALGORITHMS = frozenset(
    {SimulationAlgorithm.MULTICOLOR_DBS, SimulationAlgorithm.OVERLAP_AWARE_DBS}
)

HttpRequester = Callable[..., tuple[int, str]]


class CandidateError(RuntimeError):
    """Raised when candidate generation or evidence validation fails closed."""


class CandidateNetworkError(CandidateError):
    """Raised when the optional non-displaying ingress request fails."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CandidateError(f"value cannot be represented as canonical JSON: {error}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_descriptor(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > 256
        or any(ord(character) < 0x20 for character in value)
    ):
        raise CandidateError(f"{label} must be 1..256 visible characters without surrounding whitespace")
    return value


def _source_label(value: object) -> str:
    label = _source_descriptor(value, label="source label")
    windows = PureWindowsPath(label)
    if (
        Path(label).is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or bool(windows.root)
    ):
        raise CandidateError("source label must not be an absolute filesystem path")
    return label


def _reject_reparse_path_chain(path: Path, *, label: str) -> None:
    """Reject a leaf or ancestor that can redirect local evidence I/O."""

    try:
        lexical = path.absolute()
    except OSError as error:
        raise CandidateError(f"{label} cannot be made absolute: {error}") from error
    for component in [*reversed(lexical.parents), lexical]:
        try:
            status = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise CandidateError(
                f"{label} path component cannot be inspected: {error}"
            ) from error
        attributes = getattr(status, "st_file_attributes", 0)
        reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
        if stat.S_ISLNK(status.st_mode) or attributes & reparse_point:
            raise CandidateError(
                f"{label} must not contain symlinks; its leaf and ancestors must not be a symlink or reparse point"
            )


def _normalize_algorithm(value: SimulationAlgorithm | str) -> SimulationAlgorithm:
    try:
        algorithm = value if isinstance(value, SimulationAlgorithm) else SimulationAlgorithm(value)
    except (TypeError, ValueError) as error:
        raise CandidateError("algorithm is not recognized") from error
    if algorithm not in ALLOWED_ALGORITHMS:
        allowed = ", ".join(sorted(item.value for item in ALLOWED_ALGORITHMS))
        raise CandidateError(f"algorithm is outside the candidate allowlist: {allowed}")
    return algorithm


def generate_test_image() -> RasterImage:
    """Return the canonical 1024x600 mixed-colour, gradient, and edge target."""

    anchors = (
        (0, 0, 0),
        (255, 0, 0),
        (255, 255, 0),
        (255, 255, 255),
        (0, 255, 0),
        (0, 0, 255),
        (0, 0, 0),
    )
    physical = (
        (0, 0, 0),
        (255, 255, 255),
        (255, 224, 0),
        (220, 28, 32),
        (24, 62, 190),
        (0, 150, 72),
    )
    pixels = bytearray(WIDTH * HEIGHT * 3)
    position = 0
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if y < 360:
                scaled = x * (len(anchors) - 1) * 65536 // (WIDTH - 1)
                segment = min(len(anchors) - 2, scaled >> 16)
                fraction = scaled & 0xFFFF
                left, right = anchors[segment], anchors[segment + 1]
                base = tuple(
                    (left[channel] * (65536 - fraction) + right[channel] * fraction + 32768)
                    >> 16
                    for channel in range(3)
                )
                # The vertical axis moves from white through the hue ramp to black.
                if y < 180:
                    blend = y * 65535 // 179
                    rgb = tuple(
                        (255 * (65535 - blend) + value * blend + 32767) // 65535
                        for value in base
                    )
                else:
                    blend = (y - 180) * 65535 // 179
                    rgb = tuple(
                        (value * (65535 - blend) + 32767) // 65535 for value in base
                    )
            elif y < 450:
                gray = x * 255 // (WIDTH - 1)
                rgb = (gray, gray, gray)
                # Single-pixel and paired high-contrast edges at known coordinates.
                if x in (63, 64, 255, 511, 512, 767, 959, 960):
                    rgb = (255, 255, 255) if (x + y) & 1 else (0, 0, 0)
            else:
                column = min(5, x * 6 // WIDTH)
                rgb = physical[column]
                local_y = y - 450
                # Fine checks exercise isolated edges, diagonals, and mixed areas.
                if local_y >= 75:
                    if ((x // 4) + (local_y // 4)) & 1:
                        rgb = physical[(column + 1) % len(physical)]
                    if x % 97 == local_y % 97 or x % 113 == 112 - (local_y % 113):
                        rgb = (255, 255, 255) if column != 1 else (0, 0, 0)
            pixels[position : position + 3] = bytes(rgb)
            position += 3
    return RasterImage(WIDTH, HEIGHT, "RGB", bytes(pixels))


def _simulation_options(
    algorithm: SimulationAlgorithm,
    *,
    seed: int,
    dbs_evaluations: int,
) -> SimulationOptions:
    if type(seed) is not int or not 0 <= seed <= 0xFFFFFFFF:
        raise CandidateError("seed must be an unsigned 32-bit integer")
    if (
        type(dbs_evaluations) is not int
        or not 4 <= dbs_evaluations <= MAX_DBS_EVALUATIONS
    ):
        raise CandidateError(
            f"DBS evaluations must be an integer in [4, {MAX_DBS_EVALUATIONS}]"
        )
    budget = None
    if algorithm in DBS_ALGORITHMS:
        budget = SimulationBudget(
            max_evaluations=dbs_evaluations,
            max_accepted_moves=max(1, dbs_evaluations // 4),
            stagnation_evaluations=max(1, dbs_evaluations // 2),
        )
    return SimulationOptions(
        algorithm=algorithm,
        mapping=MappingOptions(mode="gamut-map", intent="perceptual", strength=1.0),
        seed=seed,
        budget=budget,
        white_protection=True,
        preserve_edges=True,
        text_mode=False,
        area_weight_lut_bits=4,
    )


def _options_mapping(options: SimulationOptions) -> dict[str, Any]:
    return {
        "algorithm": options.algorithm.value,
        "mapping": options.mapping.to_mapping(),
        "seed": options.seed,
        "budget": None if options.budget is None else options.budget.to_mapping(),
        "white_protection": options.white_protection,
        "preserve_edges": options.preserve_edges,
        "text_mode": options.text_mode,
        "area_weight_lut_bits": options.area_weight_lut_bits,
    }


def _mapping_record(mapping: ControllerMapping) -> dict[str, int | bool]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _controller_records(frame: bytes) -> list[dict[str, Any]]:
    return [
        {
            "controller": f"CS{index}",
            "mapping": _mapping_record(mapping),
            "dtm_bytes": CONTROLLER_FRAME_BYTES,
            "dtm_fnv1a": f"0x{fnv1a(controller_stream(frame, mapping)):08X}",
        }
        for index, mapping in enumerate(CONTROLLER_MAPPINGS, start=1)
    ]


def _normalize_base_url(base_url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(base_url)
        _ = parsed.port
    except (TypeError, ValueError) as error:
        raise CandidateError(f"--url is malformed: {error}") from error
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise CandidateError("--url must be an absolute HTTP(S) device-root URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise CandidateError("--url cannot contain credentials, a query, or a fragment")
    if parsed.path not in ("", "/"):
        raise CandidateError("--url must identify the device root")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _http_request(
    base_url: str,
    endpoint: str,
    *,
    method: str,
    data: bytes,
    timeout: float,
) -> tuple[int, str]:
    request = urllib.request.Request(
        _normalize_base_url(base_url) + endpoint,
        data=data,
        method=method,
        headers={"Content-Type": "application/octet-stream"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise CandidateNetworkError(f"ingress request failed: {error}") from error


def _strict_json_object(body: str) -> dict[str, Any]:
    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            body,
            object_pairs_hook=no_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise CandidateError(f"ingress response is not strict JSON: {error}") from error
    if not isinstance(value, dict):
        raise CandidateError("ingress response must be a JSON object")
    return value


def perform_ingress(
    base_url: str,
    frame: bytes,
    *,
    requester: Optional[HttpRequester] = None,
) -> dict[str, Any]:
    frame = bytes(validate_frame(frame))
    request = requester or _http_request
    status, body = request(
        _normalize_base_url(base_url),
        INGRESS_ENDPOINT,
        method="POST",
        data=frame,
        timeout=20.0,
    )
    if status != 200:
        raise CandidateError(f"ingress returned HTTP {status}, expected 200")
    response = _strict_json_object(body)
    expected_fnv = fnv1a(frame)
    if response.get("ok") is not True:
        raise CandidateError("ingress response ok must be true")
    if type(response.get("bytes")) is not int or response["bytes"] != FRAME_BYTES:
        raise CandidateError("ingress response byte count does not match")
    if type(response.get("fnv1a")) is not int or response["fnv1a"] != expected_fnv:
        raise CandidateError("ingress response FNV-1a does not match")
    if response.get("epd_action") != "none":
        raise CandidateError("ingress response epd_action must be none")
    if type(response.get("free_psram")) is not int or response["free_psram"] < 0:
        raise CandidateError("ingress response free_psram must be a non-negative integer")
    return {
        "mode": "ingress-only",
        "endpoint": INGRESS_ENDPOINT,
        "method": "POST",
        "bytes": FRAME_BYTES,
        "fnv1a": f"0x{expected_fnv:08X}",
        "epd_action": "none",
        "free_psram": response["free_psram"],
        "device_io_performed": True,
        "hardware_tested": False,
    }


def _build_candidate_from_source(
    selected: SimulationAlgorithm,
    source: RasterImage,
    source_record: Mapping[str, Any],
    *,
    seed: int,
    dbs_evaluations: int,
    schema_version: int = MANIFEST_SCHEMA_VERSION,
) -> tuple[dict[str, Any], SimulationResult]:
    if not isinstance(selected, SimulationAlgorithm) or selected not in ALLOWED_ALGORITHMS:
        raise CandidateError("algorithm is outside the candidate allowlist")
    if type(source) is not RasterImage or not isinstance(source_record, Mapping):
        raise CandidateError("candidate source and source record are required")
    if (
        source.width != WIDTH
        or source.height != HEIGHT
        or source.mode not in {"RGB", "RGBA"}
        or len(source.pixels) != WIDTH * HEIGHT * len(source.mode)
    ):
        raise CandidateError("candidate source must be canonical 1024x600 RGB/RGBA")
    palette = reference_palette()
    profile = build_synthetic_reference_profile(palette)
    options = _simulation_options(
        selected, seed=seed, dbs_evaluations=dbs_evaluations
    )
    result = simulate_panel(
        source,
        palette=palette,
        profile=profile,
        options=options,
    ).validated_snapshot()
    options_payload = _options_mapping(options)
    simulation_report = dict(result.report)
    transport = {
        "mode": "offline",
        "endpoint": None,
        "method": None,
        "device_io_performed": False,
        "hardware_tested": False,
    }
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "kind": MANIFEST_KIND,
        "classification": {
            "experimental": True,
            "uncalibrated": True,
            "formal": False,
            "hardware_tested": False,
            "upload_authorized": False,
        },
        "source": dict(source_record),
        "mapped": {
            "rgb8_sha256": simulation_report["mapping"]["mapped_rgb8_sha256"],
            "mapping_report_sha256": simulation_report["mapping"][
                "report_canonical_sha256"
            ],
        },
        "frame": {
            "file": "frame.bin",
            "encoding": "canonical-row-major-two-4bit-codes-per-byte",
            "bytes": len(result.frame),
            "sha256": _sha256(result.frame),
            "fnv1a": f"0x{fnv1a(result.frame):08X}",
            "codes_sha256": _sha256(result.codes),
        },
        "controllers": _controller_records(result.frame),
        "profile": {
            "profile_id": profile.profile_id,
            "canonical_sha256": profile.canonical_sha256,
            "characterization_level": profile.characterization_level,
            "model_kind": profile.model_kind,
            "palette_id": palette.palette_id,
            "palette_canonical_sha256": palette.canonical_sha256,
        },
        "options": {
            "value": options_payload,
            "canonical_sha256": _sha256(_canonical_json(options_payload)),
        },
        "previews": {
            stage: {
                "file": PREVIEW_FILES[stage],
                "bytes": len(payload),
                "sha256": _sha256(payload),
            }
            for stage, payload in result.previews.items()
        },
        "simulation": {
            "report_canonical_sha256": simulation_report["report_integrity"][
                "canonical_sha256"
            ],
            "report_hash_scope": SIMULATION_REPORT_HASH_SCOPE,
            "report": simulation_report,
        },
        "transport": transport,
    }
    unsigned = _canonical_json(manifest)
    manifest["manifest_integrity"] = {
        "canonical_sha256": _sha256(unsigned),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }
    return manifest, result


def build_candidate(
    algorithm: SimulationAlgorithm | str = SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
    *,
    seed: int = DEFAULT_SEED,
    dbs_evaluations: int = DEFAULT_DBS_EVALUATIONS,
) -> tuple[dict[str, Any], SimulationResult]:
    """Build the legacy deterministic synthetic test-card candidate."""

    selected = _normalize_algorithm(algorithm)
    source = generate_test_image()
    source_record = {
        "pattern_id": SOURCE_PATTERN_ID,
        "width": source.width,
        "height": source.height,
        "mode": source.mode,
        "pixels_bytes": len(source.pixels),
        "pixels_sha256": _sha256(source.pixels),
    }
    return _build_candidate_from_source(
        selected,
        source,
        source_record,
        seed=seed,
        dbs_evaluations=dbs_evaluations,
    )


def build_photo_candidate(
    source_input: bytes | bytearray | memoryview,
    media_type: str,
    fit: FitPolicy | str,
    *,
    rotation_degrees: int,
    source_label: str,
    source_rights: str,
    algorithm: SimulationAlgorithm | str = SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE,
    seed: int = DEFAULT_SEED,
    dbs_evaluations: int = DEFAULT_DBS_EVALUATIONS,
) -> tuple[dict[str, Any], SimulationResult, bytes]:
    """Build one reproducible natural-image candidate with frozen source bytes."""

    try:
        payload = bytes(memoryview(source_input).cast("B"))
    except (TypeError, ValueError) as error:
        raise CandidateError("source input must be contiguous bytes") from error
    try:
        decoded = decode_normalized_source(
            payload,
            media_type,
            fit,
            rotation_degrees=rotation_degrees,
            target_width=WIDTH,
            target_height=HEIGHT,
        )
    except ImageDecodeError as error:
        raise CandidateError(f"source image could not be normalized: {error}") from error
    source = decoded.raster
    source_record = {
        "source_kind": PHOTO_SOURCE_KIND,
        "input": {
            "file": SOURCE_INPUT_FILENAME,
            "bytes": len(payload),
            "sha256": decoded.source_sha256,
            "media_type": media_type,
            "label": _source_label(source_label),
            "rights": _source_descriptor(source_rights, label="source rights declaration"),
        },
        "normalization": dict(decoded.provenance),
        "width": source.width,
        "height": source.height,
        "mode": source.mode,
        "pixels_bytes": len(source.pixels),
        "pixels_sha256": _sha256(source.pixels),
    }
    manifest, result = _build_candidate_from_source(
        _normalize_algorithm(algorithm),
        source,
        source_record,
        seed=seed,
        dbs_evaluations=dbs_evaluations,
        schema_version=PHOTO_MANIFEST_SCHEMA_VERSION,
    )
    return manifest, result, payload


def _safe_new_output_directory(path: Path) -> Path:
    try:
        require_local_regular_path_syntax(path, label="output directory")
    except LocalPathSafetyError as error:
        raise CandidateError(str(error)) from error
    _reject_reparse_path_chain(path, label="output directory")
    if os.path.lexists(path):
        raise CandidateError("output directory already exists; refusing overwrite")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise CandidateError(f"output parent does not exist: {error}") from error
    try:
        require_local_regular_path_syntax(parent, label="resolved output parent")
    except LocalPathSafetyError as error:
        raise CandidateError(str(error)) from error
    if not parent.is_dir():
        raise CandidateError("output parent must be a directory")
    destination = parent / path.name
    if os.path.lexists(destination):
        raise CandidateError("output directory already exists; refusing overwrite")
    try:
        destination.mkdir()
    except FileExistsError as error:
        raise CandidateError("output directory appeared; refusing overwrite") from error
    except OSError as error:
        raise CandidateError(f"could not create output directory: {error}") from error
    return destination


def _atomic_new_file(directory: Path, name: str, payload: bytes) -> None:
    temporary = directory / f".{name}.tmp-{uuid.uuid4().hex}"
    destination = directory / name
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Linking is an atomic no-replace commit on the same local filesystem.
        os.link(temporary, destination)
        temporary.unlink()
    except FileExistsError as error:
        raise CandidateError(f"{name} already exists; refusing overwrite") from error
    except OSError as error:
        raise CandidateError(f"could not atomically write {name}: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def write_candidate_directory(
    output_dir: Path,
    manifest: Mapping[str, Any],
    result: SimulationResult,
    *,
    source_input: Optional[bytes] = None,
) -> Path:
    source_record = manifest.get("source")
    photo_source = (
        isinstance(source_record, Mapping)
        and source_record.get("source_kind") == PHOTO_SOURCE_KIND
    )
    if photo_source:
        if not isinstance(source_input, bytes):
            raise CandidateError("photo candidate requires frozen source input bytes")
        input_record = source_record.get("input")
        if (
            not isinstance(input_record, Mapping)
            or input_record.get("file") != SOURCE_INPUT_FILENAME
            or input_record.get("bytes") != len(source_input)
            or input_record.get("sha256") != _sha256(source_input)
        ):
            raise CandidateError("photo source input does not match its manifest record")
    elif source_input is not None:
        raise CandidateError("synthetic candidate must not carry source input bytes")
    directory = _safe_new_output_directory(output_dir)
    created: list[Path] = []
    try:
        payloads = {
            "frame.bin": bytes(result.frame),
            **{PREVIEW_FILES[stage]: bytes(payload) for stage, payload in result.previews.items()},
            # The manifest is the final commit marker for a complete bundle.
            "manifest.json": _canonical_json(manifest),
        }
        if photo_source:
            assert source_input is not None
            payloads[SOURCE_INPUT_FILENAME] = source_input
        ordered_names = [
            "frame.bin",
            *([SOURCE_INPUT_FILENAME] if photo_source else []),
            "source.png",
            "mapped.png",
            "final.png",
            "model.png",
            "manifest.json",
        ]
        for name in ordered_names:
            _atomic_new_file(directory, name, payloads[name])
            created.append(directory / name)
    except Exception:
        for path in reversed(created):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            directory.rmdir()
        except OSError:
            pass
        raise
    return directory


def _load_strict_manifest(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CandidateError("manifest is not UTF-8") from error

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            object_pairs_hook=no_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise CandidateError(f"manifest is not strict JSON: {error}") from error
    if not isinstance(value, dict) or _canonical_json(value) != payload:
        raise CandidateError("manifest bytes are not canonical JSON")
    return value


def validate_candidate_directory(output_dir: Path) -> dict[str, Any]:
    try:
        require_local_regular_path_syntax(output_dir, label="candidate directory")
    except LocalPathSafetyError as error:
        raise CandidateError(str(error)) from error
    _reject_reparse_path_chain(output_dir, label="candidate directory")
    try:
        directory = output_dir.resolve(strict=True)
    except OSError as error:
        raise CandidateError(f"candidate directory cannot be resolved: {error}") from error
    try:
        require_local_regular_path_syntax(directory, label="resolved candidate directory")
    except LocalPathSafetyError as error:
        raise CandidateError(str(error)) from error
    if not directory.is_dir():
        raise CandidateError("candidate path must be a directory")
    entries = list(directory.iterdir())
    for path in entries:
        _reject_reparse_path_chain(path, label="candidate files")
    actual = {path.name for path in entries if path.is_file()}
    if actual not in {REQUIRED_FILES, PHOTO_REQUIRED_FILES} or any(
        not path.is_file() for path in entries
    ):
        raise CandidateError("candidate directory file set differs from the contract")
    manifest_bytes = (directory / "manifest.json").read_bytes()
    manifest = _load_strict_manifest(manifest_bytes)
    expected_top = {
        "schema_version",
        "kind",
        "classification",
        "source",
        "mapped",
        "frame",
        "controllers",
        "profile",
        "options",
        "previews",
        "simulation",
        "transport",
        "manifest_integrity",
    }
    if set(manifest) != expected_top:
        raise CandidateError("manifest fields differ from the contract")
    schema_version = manifest.get("schema_version")
    if type(schema_version) is not int or schema_version not in {
        MANIFEST_SCHEMA_VERSION,
        PHOTO_MANIFEST_SCHEMA_VERSION,
    } or manifest.get("kind") != MANIFEST_KIND:
        raise CandidateError("manifest identity is invalid")
    classification = manifest.get("classification")
    if classification != {
        "experimental": True,
        "uncalibrated": True,
        "formal": False,
        "hardware_tested": False,
        "upload_authorized": False,
    }:
        raise CandidateError("manifest classification is not fail-closed")
    integrity = manifest.get("manifest_integrity")
    if not isinstance(integrity, Mapping) or integrity.get("canonical_sha256_scope") != MANIFEST_HASH_SCOPE:
        raise CandidateError("manifest integrity scope is invalid")
    unsigned = dict(manifest)
    del unsigned["manifest_integrity"]
    if integrity.get("canonical_sha256") != _sha256(_canonical_json(unsigned)):
        raise CandidateError("manifest integrity hash does not match")

    source_record = manifest.get("source")
    if not isinstance(source_record, Mapping):
        raise CandidateError("source identity is missing")
    if source_record.get("pattern_id") == SOURCE_PATTERN_ID:
        if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            raise CandidateError("synthetic candidate schema version is invalid")
        if actual != REQUIRED_FILES:
            raise CandidateError("synthetic candidate file set differs from the contract")
        source = generate_test_image()
        if source_record != {
            "pattern_id": SOURCE_PATTERN_ID,
            "width": WIDTH,
            "height": HEIGHT,
            "mode": "RGB",
            "pixels_bytes": len(source.pixels),
            "pixels_sha256": _sha256(source.pixels),
        }:
            raise CandidateError("source pattern identity does not match")
    elif source_record.get("source_kind") == PHOTO_SOURCE_KIND:
        if manifest.get("schema_version") != PHOTO_MANIFEST_SCHEMA_VERSION:
            raise CandidateError("photo candidate schema version is invalid")
        if actual != PHOTO_REQUIRED_FILES or set(source_record) != {
            "source_kind",
            "input",
            "normalization",
            "width",
            "height",
            "mode",
            "pixels_bytes",
            "pixels_sha256",
        }:
            raise CandidateError("photo candidate source contract differs")
        input_record = source_record.get("input")
        normalization = source_record.get("normalization")
        if not isinstance(input_record, Mapping) or set(input_record) != {
            "file",
            "bytes",
            "sha256",
            "media_type",
            "label",
            "rights",
        }:
            raise CandidateError("photo source input record differs")
        if (
            input_record.get("file") != SOURCE_INPUT_FILENAME
            or not isinstance(normalization, Mapping)
            or not isinstance(input_record.get("media_type"), str)
            or not isinstance(normalization.get("fit"), str)
            or type(normalization.get("explicit_rotation_degrees")) is not int
        ):
            raise CandidateError("photo source input or normalization is invalid")
        _source_label(input_record.get("label"))
        _source_descriptor(
            input_record.get("rights"), label="source rights declaration"
        )
        source_input = (directory / SOURCE_INPUT_FILENAME).read_bytes()
        if (
            input_record.get("bytes") != len(source_input)
            or input_record.get("sha256") != _sha256(source_input)
        ):
            raise CandidateError("photo source input identity does not match")
        try:
            decoded = decode_normalized_source(
                source_input,
                input_record.get("media_type"),
                normalization.get("fit"),
                rotation_degrees=normalization.get("explicit_rotation_degrees"),
                target_width=WIDTH,
                target_height=HEIGHT,
            )
        except ImageDecodeError as error:
            raise CandidateError(
                f"frozen photo source could not be revalidated: {error}"
            ) from error
        source = decoded.raster
        if (
            decoded.source_sha256 != input_record.get("sha256")
            or dict(decoded.provenance) != dict(normalization)
            or source_record.get("width") != source.width
            or source_record.get("height") != source.height
            or source_record.get("mode") != source.mode
            or source_record.get("pixels_bytes") != len(source.pixels)
            or source_record.get("pixels_sha256") != _sha256(source.pixels)
        ):
            raise CandidateError("photo source normalization identity does not match")
    else:
        raise CandidateError("source kind is outside the candidate contract")
    frame = (directory / "frame.bin").read_bytes()
    validate_frame(frame)
    frame_record = manifest.get("frame")
    if not isinstance(frame_record, Mapping) or frame_record != {
        "file": "frame.bin",
        "encoding": "canonical-row-major-two-4bit-codes-per-byte",
        "bytes": len(frame),
        "sha256": _sha256(frame),
        "fnv1a": f"0x{fnv1a(frame):08X}",
        "codes_sha256": _sha256(unpack_pixels(frame, WIDTH, HEIGHT)),
    }:
        raise CandidateError("frame identity does not match")
    if manifest.get("controllers") != _controller_records(frame):
        raise CandidateError("controller DTM identities or mappings do not match")
    previews = {stage: (directory / filename).read_bytes() for stage, filename in PREVIEW_FILES.items()}
    preview_records = manifest.get("previews")
    expected_previews = {
        stage: {"file": PREVIEW_FILES[stage], "bytes": len(payload), "sha256": _sha256(payload)}
        for stage, payload in previews.items()
    }
    if preview_records != expected_previews:
        raise CandidateError("preview identities do not match")
    simulation = manifest.get("simulation")
    if not isinstance(simulation, Mapping) or not isinstance(simulation.get("report"), Mapping):
        raise CandidateError("embedded simulation report is missing")
    report = simulation["report"]
    validate_simulation_report(report, frame=frame, previews=previews)
    if simulation.get("report_hash_scope") != SIMULATION_REPORT_HASH_SCOPE or simulation.get(
        "report_canonical_sha256"
    ) != report["report_integrity"]["canonical_sha256"]:
        raise CandidateError("simulation report identity does not match")
    if report.get("source_raster_sha256") != source_record["pixels_sha256"]:
        raise CandidateError("simulation source binding does not match")
    if manifest.get("mapped") != {
        "rgb8_sha256": report["mapping"]["mapped_rgb8_sha256"],
        "mapping_report_sha256": report["mapping"]["report_canonical_sha256"],
    }:
        raise CandidateError("mapped raster binding does not match")
    if report["output"]["frame_sha256"] != frame_record["sha256"] or report["output"][
        "codes_sha256"
    ] != frame_record["codes_sha256"]:
        raise CandidateError("simulation frame binding does not match")
    for stage in PREVIEW_FILES:
        if report["previews"][stage]["sha256"] != preview_records[stage]["sha256"]:
            raise CandidateError("simulation preview binding does not match")

    options = manifest.get("options")
    if not isinstance(options, Mapping) or options.get("canonical_sha256") != _sha256(
        _canonical_json(options.get("value"))
    ):
        raise CandidateError("options identity does not match")
    option_value = options["value"]
    if not isinstance(option_value, Mapping):
        raise CandidateError("options value must be an object")
    try:
        option_algorithm = _normalize_algorithm(option_value.get("algorithm"))
    except CandidateError as error:
        raise CandidateError("options algorithm is outside the allowlist") from error
    reported_budget = option_value.get("budget")
    if option_algorithm in DBS_ALGORITHMS:
        if not isinstance(reported_budget, Mapping):
            raise CandidateError("DBS options budget is missing")
        evaluations = reported_budget.get("max_evaluations")
    else:
        if reported_budget is not None:
            raise CandidateError("fixed-complexity options unexpectedly carry a budget")
        evaluations = DEFAULT_DBS_EVALUATIONS
    expected_options = _options_mapping(
        _simulation_options(
            option_algorithm,
            seed=option_value.get("seed"),
            dbs_evaluations=evaluations,
        )
    )
    if option_value != expected_options:
        raise CandidateError("options differ from the fixed experimental contract")
    if (
        option_value["algorithm"] != report["halftone"]["algorithm"]
        or option_value["seed"] != report["halftone"]["seed"]
        or option_value["budget"] != report["halftone"]["budget"]
        or any(
            report["mapping"]["report"]["options"].get(key) != value
            for key, value in option_value["mapping"].items()
        )
    ):
        raise CandidateError("options are not bound to the simulation report")
    profile = manifest.get("profile")
    mapping_profile = report["mapping"]["report"]["profile"]
    if not isinstance(profile, Mapping) or not isinstance(mapping_profile, Mapping):
        raise CandidateError("profile binding is missing")
    expected_palette = reference_palette()
    expected_profile = build_synthetic_reference_profile(expected_palette)
    expected_profile_record = {
        "profile_id": expected_profile.profile_id,
        "canonical_sha256": expected_profile.canonical_sha256,
        "characterization_level": expected_profile.characterization_level,
        "model_kind": expected_profile.model_kind,
        "palette_id": expected_palette.palette_id,
        "palette_canonical_sha256": expected_palette.canonical_sha256,
    }
    if profile != expected_profile_record or (
        profile.get("profile_id") != mapping_profile.get("id")
        or profile.get("canonical_sha256") != mapping_profile.get("canonical_sha256")
        or profile.get("palette_id") != report["palette"]["palette_id"]
        or profile.get("palette_canonical_sha256") != report["palette_canonical_sha256"]
    ):
        raise CandidateError("profile binding does not match")
    transport = manifest.get("transport")
    if not isinstance(transport, Mapping) or transport.get("hardware_tested") is not False:
        raise CandidateError("transport hardware_tested must remain false")
    if transport.get("mode") == "offline":
        if transport != {
            "mode": "offline",
            "endpoint": None,
            "method": None,
            "device_io_performed": False,
            "hardware_tested": False,
        }:
            raise CandidateError("offline transport record is invalid")
    elif transport.get("mode") == "ingress-only":
        if (
            transport.get("endpoint") != INGRESS_ENDPOINT
            or transport.get("method") != "POST"
            or transport.get("epd_action") != "none"
            or transport.get("device_io_performed") is not True
        ):
            raise CandidateError("ingress-only transport record is invalid")
    else:
        raise CandidateError("transport mode is invalid")
    return manifest


def _read_manifest_bound_frame(
    candidate_dir: Path,
    manifest: Mapping[str, Any],
) -> bytes:
    """Re-read and bind the exact in-memory ingress bytes after disk validation."""

    frame_record = manifest.get("frame")
    if not isinstance(frame_record, Mapping) or frame_record.get("file") != "frame.bin":
        raise CandidateError("validated manifest frame record is invalid")
    try:
        frame = (candidate_dir / "frame.bin").read_bytes()
    except OSError as error:
        raise CandidateError(f"could not re-read the validated frame: {error}") from error
    try:
        frame = bytes(validate_frame(frame))
    except Exception as error:
        raise CandidateError(f"re-read frame violates the canonical frame contract: {error}") from error
    expected = {
        "file": "frame.bin",
        "encoding": "canonical-row-major-two-4bit-codes-per-byte",
        "bytes": len(frame),
        "sha256": _sha256(frame),
        "fnv1a": f"0x{fnv1a(frame):08X}",
        "codes_sha256": _sha256(unpack_pixels(frame, WIDTH, HEIGHT)),
    }
    if frame_record != expected:
        raise CandidateError(
            "re-read frame bytes do not match the validated manifest; refusing ingress"
        )
    return frame


def _uint32(value: str) -> int:
    try:
        result = int(value, 0)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected an unsigned 32-bit integer") from error
    if not 0 <= result <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("expected an unsigned 32-bit integer")
    return result


def _dbs_evaluations(value: str) -> int:
    try:
        result = int(value, 10)
    except ValueError as error:
        raise argparse.ArgumentTypeError("DBS evaluations must be an integer") from error
    if not 4 <= result <= MAX_DBS_EVALUATIONS:
        raise argparse.ArgumentTypeError(
            f"DBS evaluations must be in [4, {MAX_DBS_EVALUATIONS}]"
        )
    return result


def _read_source_image(path: Path) -> bytes:
    try:
        require_local_regular_path_syntax(path, label="source image")
    except LocalPathSafetyError as error:
        raise CandidateError(str(error)) from error
    _reject_reparse_path_chain(path, label="source image")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise CandidateError(f"source image cannot be resolved: {error}") from error
    try:
        require_local_regular_path_syntax(resolved, label="resolved source image")
    except LocalPathSafetyError as error:
        raise CandidateError(str(error)) from error
    if not resolved.is_file():
        raise CandidateError("source image must be a regular file")
    try:
        payload = resolved.read_bytes()
    except OSError as error:
        raise CandidateError(f"source image could not be read: {error}") from error
    if not payload:
        raise CandidateError("source image must not be empty")
    return payload


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--output-dir",
        type=Path,
        help="create one new, offline candidate evidence directory",
    )
    mode.add_argument(
        "--validate-dir",
        type=Path,
        help="deep-validate an existing frozen candidate directory",
    )
    parser.add_argument(
        "--algorithm",
        choices=sorted(item.value for item in ALLOWED_ALGORITHMS),
        default=None,
    )
    parser.add_argument("--seed", type=_uint32, default=None)
    parser.add_argument(
        "--dbs-evaluations",
        type=_dbs_evaluations,
        default=None,
    )
    parser.add_argument(
        "--source-image",
        type=Path,
        help="freeze original natural-image bytes into a reproducible candidate bundle",
    )
    parser.add_argument(
        "--source-media-type",
        choices=("image/jpeg", "image/png", "image/webp"),
        help="required explicit MIME type for --source-image",
    )
    parser.add_argument(
        "--source-label",
        help="required stable source name without an absolute filesystem path",
    )
    parser.add_argument(
        "--source-rights",
        help="required source ownership/licence declaration",
    )
    parser.add_argument(
        "--fit",
        choices=tuple(item.value for item in FitPolicy),
        help="required explicit normalization geometry for --source-image",
    )
    parser.add_argument(
        "--rotation-degrees",
        type=int,
        choices=(0, 90, 180, 270),
        help="required explicit post-EXIF rotation for --source-image",
    )
    parser.add_argument(
        "--url",
        help="optional device-root URL for the non-displaying ingress integrity check",
    )
    args = parser.parse_args(argv)
    source_values = (
        args.source_image,
        args.source_media_type,
        args.source_label,
        args.source_rights,
        args.fit,
        args.rotation_degrees,
    )
    if args.validate_dir is not None:
        if any(value is not None for value in source_values):
            parser.error("source options are generation-only; validation uses frozen bundle bytes")
        if any(value is not None for value in (args.algorithm, args.seed, args.dbs_evaluations)):
            parser.error("algorithm, seed, and DBS options are generation-only")
    if args.output_dir is not None:
        if args.source_image is None and any(
            value is not None for value in source_values[1:]
        ):
            parser.error("source metadata requires --source-image")
        if args.source_image is not None and any(
            value is None for value in source_values[1:]
        ):
            parser.error(
                "--source-image requires --source-media-type, --source-label, "
                "--source-rights, --fit, and --rotation-degrees"
            )
        if args.algorithm is None:
            args.algorithm = SimulationAlgorithm.AREA_WEIGHTED_BLUE_NOISE.value
        if args.seed is None:
            args.seed = DEFAULT_SEED
        if args.dbs_evaluations is None:
            args.dbs_evaluations = DEFAULT_DBS_EVALUATIONS
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.validate_dir is not None:
            manifest = validate_candidate_directory(args.validate_dir)
            if args.url is None:
                rendered: Mapping[str, Any] = manifest
            else:
                frame = _read_manifest_bound_frame(args.validate_dir, manifest)
                rendered = {
                    "kind": "mf1750-g1-s1-candidate-ingress-validation",
                    "candidate_manifest_canonical_sha256": manifest[
                        "manifest_integrity"
                    ]["canonical_sha256"],
                    "classification": {
                        "experimental": True,
                        "formal": False,
                        "hardware_tested": False,
                    },
                    "ingress": perform_ingress(args.url, frame),
                }
        else:
            if args.url is not None:
                raise CandidateError(
                    "--url is valid only with --validate-dir so the evidence is frozen first"
                )
            assert args.output_dir is not None
            if os.path.lexists(args.output_dir):
                raise CandidateError("output directory already exists; refusing overwrite")
            source_input: Optional[bytes] = None
            if args.source_image is None:
                manifest, result = build_candidate(
                    args.algorithm,
                    seed=args.seed,
                    dbs_evaluations=args.dbs_evaluations,
                )
            else:
                assert args.source_media_type is not None
                assert args.source_label is not None
                assert args.source_rights is not None
                assert args.fit is not None
                assert args.rotation_degrees is not None
                source_input = _read_source_image(args.source_image)
                manifest, result, source_input = build_photo_candidate(
                    source_input,
                    args.source_media_type,
                    args.fit,
                    rotation_degrees=args.rotation_degrees,
                    source_label=args.source_label,
                    source_rights=args.source_rights,
                    algorithm=args.algorithm,
                    seed=args.seed,
                    dbs_evaluations=args.dbs_evaluations,
                )
            directory = write_candidate_directory(
                args.output_dir,
                manifest,
                result,
                source_input=source_input,
            )
            rendered = validate_candidate_directory(directory)
    except CandidateError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_json(rendered).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
