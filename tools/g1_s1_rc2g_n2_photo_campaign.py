#!/usr/bin/env python3
"""Compile the frozen natural-photo G1/S1 RC2G N2 four-cell campaign.

This module is deliberately an offline compiler.  It deeply validates the
four reviewed V2 candidate directories, recomputes the Q3/Q4 cross-model loss
gate, and emits P0 fixed-action declarations for four disconnected sessions.
It has no refresh runner, authorization generator, claim writer, HTTP client,
serial/GPIO path, firmware uploader, retry path, or recovery path.

Each future session is controller-fresh-boot -> its own MAP primer -> its own
target.  Compiling or describing this campaign does not make it executable.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Optional, Sequence
import uuid

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.color_pipeline.pipeline import RasterImage  # noqa: E402
from host.epd_frame import (  # noqa: E402
    CONTROLLER_FRAME_BYTES,
    FRAME_BYTES,
    HEIGHT,
    WIDTH,
    controller_stream,
    fnv1a,
    generate_fixture,
    unpack_pixels,
    validate_frame,
)
from host.halftone_optimization import (  # noqa: E402
    ALLOWED_CODES,
    DBSOptions,
    OverlapObservationModel,
    SpatialKernel,
    evaluate_halftone_loss,
)
from host.visible_refresh_campaign import (  # noqa: E402
    CAMPAIGN_KIND,
    CampaignContractError,
    build_fixed_action_declaration,
    build_session_contract,
    seal_campaign_contract,
    validate_campaign_contract,
    validate_fixed_action_declaration,
)
from tools.g1_s1_panel_candidate import (  # noqa: E402
    CandidateError,
    validate_candidate_directory,
)
from tools.g1_s1_rc2g_quality_refresh_once import (  # noqa: E402
    EXPECTED_BUILD_TAG,
    EXPECTED_DRIVER_API,
    FIXED_CONTROLLER_MAPPINGS,
)
from tools.local_path_safety import (  # noqa: E402
    LocalPathSafetyError,
    require_local_regular_path_syntax,
)


SCHEMA_VERSION = 1
MANIFEST_KIND = "mf1750-g1-s1-rc2g-n2-photo-campaign-offline-manifest"
DESCRIPTION_KIND = "mf1750-g1-s1-rc2g-n2-photo-campaign-offline-description"
CAMPAIGN_ID = "g1-s1-rc2g-n2-photo-four-independent-cells-v1"
MANIFEST_HASH_SCOPE = (
    "entire manifest excluding manifest_integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
DESCRIPTION_HASH_SCOPE = (
    "entire description excluding integrity; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
EXPECTED_CANDIDATE_KIND = "mf1750-g1-s1-experimental-panel-candidate"
HARDWARE_DIR = REPO_ROOT / ".test-output" / "hardware"
# The PlatformIO output is mutable and is overwritten by later clean builds.
# Bind legacy N2/N3/N8 evidence to the exact RC2G bytes verified on the panel.
FIRMWARE_BINARY = (
    HARDWARE_DIR
    / "RC2G_N2_PHYSICAL_SESSION_20260808_2132"
    / "q1-map-primer-result"
    / "FIRMWARE.bin"
)

SOURCE_COMMIT = "172840c091bd963633860b5dfde6f327d30ab665"
FIRMWARE_BINARY_BYTES = 815_664
FIRMWARE_BINARY_SHA256 = "9df89715385f98892549d24b57a6b139fb0844e9cea52ef4fd2c961d6b0cd772"
PANEL_CONTRACT = {
    "model": "MF1750-C73",
    "serial": "UNBOUND-N2P-OFFLINE",
    "board_id": "ESP32-C73",
    "pcb_revision": "rev-a1",
}
FIRMWARE_CONTRACT = {
    "source_commit": SOURCE_COMMIT,
    "build_tag": EXPECTED_BUILD_TAG,
    "binary_sha256": FIRMWARE_BINARY_SHA256,
    "driver_api": EXPECTED_DRIVER_API,
}

MAP_FIXTURE = "map-orient-v1"
MAP_FRAME_SHA256 = "1deedf924e40c676c2080fec08dfe5da10a8c1bb53b699ec4a85b0b6101b5c36"
MAP_FRAME_FNV1A = 0x9D04142D
MAP_CS1_DTM_SHA256 = "d1ce843dca5ec7a615329f6a118dc9bd03498f686f1b5bfe55d51a97556eccaa"
MAP_CS1_DTM_FNV1A = 0xF26832DD
MAP_CS2_DTM_SHA256 = "ae0bc93cc2cf736fc2f9c209865c93443e90271b992647a8d8c7a5761e08c791"
MAP_CS2_DTM_FNV1A = 0xFE199FF5

SHARED_SEED = 1_296_445_751
SHARED_SOURCE = {
    "source_kind": "decoded-normalized-image-v2",
    "input": {
        "file": "source.input",
        "bytes": 687_568,
        "sha256": "04034fbc1836791e0d1370d70d1871f174407b877ca24563f6cb0cf97a63eb07",
        "media_type": "image/jpeg",
        "label": "IMG_20140831_185019.JPG",
        "rights": "user-owned-private-test-photo",
    },
    "normalization": {
        "declared_media_type": "image/jpeg",
        "decoded_format": "JPEG",
        "decoder": "Pillow",
        "decoder_version": "12.2.0",
        "embedded_icc_sha256": None,
        "exif_orientation": 1,
        "exif_transposed": False,
        "explicit_rotation_degrees": 0,
        "fit": "cover",
        "formal_colour_eligible": False,
        "formal_ineligibility_reason": (
            "source decode provenance alone cannot qualify an unmeasured panel gamut"
        ),
        "hardware_tested": False,
        "icc_handling": "untagged_explicit_srgb_assumption",
        "littlecms_version": "2.18",
        "path_version": 2,
        "resampler": "Pillow-LANCZOS",
        "source_height": 1707,
        "source_profile": "assumed-iec-srgb",
        "source_width": 1280,
        "srgb_assumption": True,
        "target_height": 600,
        "target_width": 1024,
        "working_space": "IEC 61966-2-1 sRGB RGB8/RGBA8",
    },
    "width": WIDTH,
    "height": HEIGHT,
    "mode": "RGB",
    "pixels_bytes": WIDTH * HEIGHT * 3,
    "pixels_sha256": "5ae10a75e21e55bb0a540620da57140a2b9776c1e63cbbd747fb40d1eb12415c",
}
SHARED_MAPPED = {
    "rgb8_sha256": "1bbaf839595ca972c8e04efb01dd228a6c92cde32d9f11c16cccb6d88ce4fe69",
    "mapping_report_sha256": "2d0ef90ead6341268ab47959154593501fa308c515f345883f87a00c43381f3b",
}
SHARED_PROFILE = {
    "profile_id": "synthetic-reference-linear-xyz-v1",
    "canonical_sha256": "34d8b88386b19ad3717b2e7d54b1c3e072b424f186413c994eb175d1989ca2ee",
    "characterization_level": "reference",
    "model_kind": "linear_xyz_convex_v1",
    "palette_id": "reference-srgb-v1",
    "palette_canonical_sha256": "181770a2de3bb23bcc31666573279c8cde8225d2f4c27a24c9c1345dba54965e",
}
SHARED_PROTECTION = {
    "white": True,
    "edge": True,
    "text": False,
    "contract": "canonical-C2-protection-constraints-v1",
    "unconstrained_sentinel": 255,
    "constraint_mask_sha256": "52abbdbfff1208b369f80c6b656b4926a744ddd4cead5d4c4f06c51ef1ceeb52",
    "locked_pixels": 79_415,
    "locked_code_counts": {
        "0": 15_611,
        "1": 36_218,
        "2": 50,
        "3": 2_630,
        "5": 24_733,
        "6": 173,
    },
}
SHARED_PREVIEWS = {
    "source": {
        "file": "source.png",
        "bytes": 1_291_967,
        "sha256": "5402038a5972892cb2838718b4b5ee923795f667ae290ea490ee10b9470f8ed6",
    },
    "mapped": {
        "file": "mapped.png",
        "bytes": 1_285_253,
        "sha256": "971ee73e52f3f03026f0efa4bbd9cd1e4451f86381488bcab28b749feddc8b18",
    },
}
SHARED_DBS_BUDGET = {
    "kind": "deterministic-work-v1",
    "max_evaluations": 262_144,
    "max_accepted_moves": 65_536,
    "stagnation_evaluations": 131_072,
    "wall_clock_deadline_used": False,
}
SHARED_INITIALIZER = {
    "present": True,
    "frame_sha256": "627422e143412425d60ea4a5e0529f80e7bb61a75e264fc783597ccb58c13f3c",
    "frame_fnv1a": "0xC629D96B",
    "codes_sha256": "a2989868e3b27e2972890ca24c37ed8afd6ea837abad7a5f199975ae472bf5ca",
    "report_canonical_sha256": "f532668ef6f46d65f15aaabfe97b05c23a3a6802b3ab99cec671fccd64d0207a",
}
PROPOSAL_TRACE_SHA256 = "cd83980959a3ee5ed815ae91cc0c96c9c9adfc738f291dfa716089cecf8468cb"
COVERAGE_CANONICAL_SHA256 = "56239c02a66944528a09a4e3b5b8f669576704ada8f216e5d39b7e1a38d7e69a"
TILE_COUNTS_CANONICAL_SHA256 = "0decc34bb3b79d1cab065b644a25a01637931c2f6618a477001e0163c004a2f7"
Q3_Q4_DIFFERING_PIXELS = 6_530

EXPECTED_CROSS_LOSSES = {
    "Q3_under_overlap_model": {
        "total": 0.014088430140269625,
        "multiscale_3x3": 0.014828856955802282,
        "multiscale_7x7": 0.011699222426047512,
        "multiscale_15x15": 0.01041592543813988,
        "edge": 0.0014960333464770306,
        "direction": 0.001385681197206533,
        "periodic": 0.035932756814043516,
        "cluster": 0.018507775205354807,
    },
    "Q4_under_identity_model": {
        "total": 0.017727477929818176,
        "multiscale_3x3": 0.020190879915104067,
        "multiscale_7x7": 0.012170104115653219,
        "multiscale_15x15": 0.010474401821736812,
        "edge": 0.00976400554985212,
        "direction": 0.0012102164715232337,
        "periodic": 0.03536735820060046,
        "cluster": 0.017817432479512358,
    },
}

# Checked at compile time so a later field or byte change cannot drift silently.
EXPECTED_MANIFEST_CANONICAL_SHA256: Optional[str] = (
    "976ab0ae891ae8dae13da2b2db67b59ff7aaf4fa1fd89322ec3d12f6555c825b"
)
EXPECTED_MANIFEST_FILE_SHA256: Optional[str] = (
    "d7d55f62f6e2392d42dd8d65ea5cd5d7c0c5179b4cd51b9109666b420a21d687"
)


class N2PhotoCampaignError(RuntimeError):
    """A frozen input or offline campaign contract failed validation."""


@dataclass(frozen=True)
class _CellSpec:
    cell_id: str
    ordinal: int
    algorithm: str
    artifact_id: str
    manifest_file_sha256: str
    manifest_canonical_sha256: str
    frame_sha256: str
    frame_fnv1a: int
    codes_sha256: str
    options_canonical_sha256: str
    simulation_report_sha256: str
    final_preview_bytes: int
    final_preview_sha256: str
    model_preview_bytes: int
    model_preview_sha256: str
    cs1_dtm_sha256: str
    cs1_dtm_fnv1a: int
    cs2_dtm_sha256: str
    cs2_dtm_fnv1a: int
    own_loss_sha256: Optional[str] = None
    own_initial_total: Optional[float] = None
    own_final_total: Optional[float] = None

    @property
    def directory(self) -> Path:
        return HARDWARE_DIR / self.artifact_id


CELL_SPECS = (
    _CellSpec(
        "Q1", 1, "atkinson", "G1S1_N2P_WINDMILL_ATKINSON_OFFLINE_20260807_V2",
        "7d4ccd683f0be4d0c32d4692bc2d9beab88526c36a7624d2c3a1d0865e9eb6ff",
        "b4db35f2d1318a7bba352b0e501f443db530f8d4137ab9e46930561d8060d584",
        "7aa33f337903b93ba094265e212909f5986ab48eebb0a2dd352b7571a6ea7c96",
        0x1110A359,
        "6ccede4b69bfac0697af32755576403f6e73a64ec2455517e703b3c12e7b3fe3",
        "45922b01634de0ff2b74e5079fb4b0772b3d474f56fdb2236ad752f890310766",
        "bdc265c6dc969e0744ec468b0d79c16ffe688da197e283344056d3738a9ca561",
        156_873, "5960506add9e75beb622a2c84d56e34966514d7b01c051ced00e6f83191a3551",
        682_570, "d5a2efc4c9dd8ea08a158064edeed33284721423016b846c7b558b30b020b0ed",
        "17c1dc335823c189ef8c1643c42bfdabcfbb0e2497fbc224964c028da3400c6f", 0xD7515CF6,
        "6762d6f6c548e19be87fb04aae51d01ebb2028476bf5dacf8bfee591bc3ae415", 0x6E725B02,
    ),
    _CellSpec(
        "Q2", 2, "area-weighted-blue-noise", "G1S1_N2P_WINDMILL_BLUE_NOISE_OFFLINE_20260807_V2",
        "e43b049d5b73e33563e98180ad3295173b549b048cadd0460cf6fdf0ecafcdcb",
        "95243d261338bddd6b718b39a2bbc8f112d8b26a74309f15095542db30f8f151",
        "cdd3abf625f09ba759351b80ed358fdf8515fe3d776bdd862ac2e0433ceea4e3",
        0x03D758D9,
        "b76d5c96f3674616999f38f80f78f504b9190f7da71096700ecbae1cba0145cb",
        "feea53e3166d68bebe77c4c215f039479420e6182675af3bc85509c922592875",
        "0c261d3bff75e052c54c3caa811fab6d18d8a0068d0f7b2f7e545c562466f52f",
        125_277, "9457f1a77b2e499f9bc000e3d14a487581797b86aa42ac7f09a76c45b3a3937d",
        569_497, "ecf99f1114768f3c999a1a770047336b9d68d65dfdd2d69ea81530cd7fd66628",
        "dffb6b759875315a50a75ad7cc5b916c3e92aa4a1ce5975cf5880bf35e2dd6a4", 0xDAEED0AB,
        "4122e120428f9781e11f81d6e7edefc916178862352f4446d7da37427935e14b", 0x86E75513,
    ),
    _CellSpec(
        "Q3", 3, "multicolor-dbs", "G1S1_N2P_WINDMILL_MULTICOLOR_DBS_262K_OFFLINE_20260807_V2",
        "2a429eee18396fbd7a36b27be049fe18686914d1496b7ade4a64c08599548f0a",
        "f8535120a430b2b672c968f5a335744a8b5e9c9e02a8d8e96eecbff617021ce1",
        "0a9e2da80ced18ad7f7345906a78c53e7b720468c254365a5fc44502576b1a77",
        0x2647DA34,
        "ed868a70e2fde94f1ab3c3bc08c8383f9ec6da5c1fdeeb2ccff32c93f8fb5c1e",
        "f8e8d7970c67cdc2c4c1f99aa2e888a2a0b883aebfc738193b5b338586625b90",
        "72995d5176b66d1ebdf70ca6cf27726555ffb4e51718c2cbffd8f10871563f5e",
        185_823, "2be45e01cef4ad09aacad187868d954bbd2617666b3a3fc89f57c6aa8b3ccbab",
        185_823, "2be45e01cef4ad09aacad187868d954bbd2617666b3a3fc89f57c6aa8b3ccbab",
        "063e09ecca1f7d24ae85f58ded7d5e9ed1871aa3c5f795c694226775c4480fe3", 0xF08B0419,
        "bd6cd530b9af86e2d9256a1691f8cac28d88597fcfcd313b11752d994f7611fa", 0xE948A160,
        "093be9ab81feba2c44264b7461ea45b865e05693b7e1623aa9c0d3f34e95c1f8",
        0.019197218813359042, 0.017670189051822,
    ),
    _CellSpec(
        "Q4", 4, "overlap-aware-dbs", "G1S1_N2P_WINDMILL_OVERLAP_DBS_262K_OFFLINE_20260807_V2",
        "9b4ce4a73457c34d09e9fddfcc0272e3c0f0d472cd4d46a0faa712ba4dfb9505",
        "7d2af4ca143f8c3d1dfefa0b9b7845852ef53498706e228b5a8acdc57fa35b5f",
        "4183b84b40578589938531076eb92845aa53f533c6e29ee5a54986903c7e8f86",
        0x1F67D22D,
        "3fd3d0f37cc0f11186d9204d01edc94fddbceebdb0560d3be79fc53a2562be9a",
        "eb011f13b0d949675a7f82a85de40938ea60e1f942b183fc56559f2c7bf20979",
        "c0d1539856b34d3aa925d7062a7dce7979fa3cbba8bd5cfaecfb2eed558e4b57",
        186_734, "c76a3969b1935a5f10b9a48b8ba47b5642454af1124847e9eb43364b407f1ff5",
        857_451, "37573a3b670eaef2c8d7d01e77714a2a4262a1dfd17e31f6e3eef206980e2493",
        "5bf0c536c906ab62227e24c7331a773c86552d0feb699e7f3266909d160af23d", 0x20E59B49,
        "651276fcc323cf20cb22a7382234122c0736842cc7238d1ab6a432e2cd5168a2", 0x549DCBBD,
        "ca89c9f139fcc780223ff5dbed8bbe706440620d0899bc771472a780abfbeccb",
        0.01560596837744703, 0.014062116440489943,
    ),
)


@dataclass(frozen=True)
class _LoadedCell:
    spec: _CellSpec
    manifest: Mapping[str, Any]
    record: Mapping[str, Any]
    frame: bytes
    codes: bytes
    mapped_image: RasterImage
    optimizer_report: Optional[Mapping[str, Any]]


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
        raise N2PhotoCampaignError(f"canonical JSON encoding failed: {error}") from error


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _mapping_record(mapping: object) -> dict[str, Any]:
    return {
        "source_half": mapping.source_half,
        "flip_x": mapping.flip_x,
        "flip_y": mapping.flip_y,
        "nibble_swap": mapping.nibble_swap,
    }


def _strict_json_object(payload: bytes, *, label: str) -> Mapping[str, Any]:
    def reject_constant(token: str) -> None:
        raise N2PhotoCampaignError(f"{label} contains forbidden JSON constant {token}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise N2PhotoCampaignError(f"{label} contains duplicate key {key!r}")
            value[key] = item
        return value

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except N2PhotoCampaignError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise N2PhotoCampaignError(f"{label} is not strict UTF-8 JSON: {error}") from error
    if not isinstance(value, Mapping):
        raise N2PhotoCampaignError(f"{label} root must be an object")
    return value


def _expected_options(spec: _CellSpec) -> dict[str, Any]:
    return {
        "algorithm": spec.algorithm,
        "area_weight_lut_bits": 4,
        "budget": SHARED_DBS_BUDGET if spec.cell_id in {"Q3", "Q4"} else None,
        "mapping": {
            "cache_entries": 65_536,
            "intent": "perceptual",
            "mode": "gamut-map",
            "strength": 1.0,
        },
        "preserve_edges": True,
        "seed": SHARED_SEED,
        "text_mode": False,
        "white_protection": True,
    }


def _read_fixed_file(
    path: Path, *, size: Optional[int], sha256: str, label: str
) -> bytes:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise N2PhotoCampaignError(f"could not read {label}: {error}") from error
    if (size is not None and len(payload) != size) or _sha256(payload) != sha256:
        raise N2PhotoCampaignError(f"{label} byte identity changed")
    return payload


def _frame_record(frame: bytes) -> dict[str, Any]:
    validate_frame(frame)
    controllers = []
    for number, mapping in enumerate(FIXED_CONTROLLER_MAPPINGS, start=1):
        stream = controller_stream(frame, mapping)
        controllers.append(
            {
                "controller": f"CS{number}",
                "mapping": _mapping_record(mapping),
                "dtm_bytes": len(stream),
                "dtm_sha256": _sha256(stream),
                "dtm_fnv1a": f"0x{fnv1a(stream):08X}",
            }
        )
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "bits_per_pixel": 4,
        "bytes": len(frame),
        "sha256": _sha256(frame),
        "fnv1a": f"0x{fnv1a(frame):08X}",
        "controllers": controllers,
    }


def _validate_map_identity() -> tuple[bytes, Mapping[str, Any]]:
    frame = generate_fixture(MAP_FIXTURE)
    record = _frame_record(frame)
    expected = {
        "width": WIDTH,
        "height": HEIGHT,
        "bits_per_pixel": 4,
        "bytes": FRAME_BYTES,
        "sha256": MAP_FRAME_SHA256,
        "fnv1a": f"0x{MAP_FRAME_FNV1A:08X}",
        "controllers": [
            {
                "controller": "CS1",
                "mapping": _mapping_record(FIXED_CONTROLLER_MAPPINGS[0]),
                "dtm_bytes": CONTROLLER_FRAME_BYTES,
                "dtm_sha256": MAP_CS1_DTM_SHA256,
                "dtm_fnv1a": f"0x{MAP_CS1_DTM_FNV1A:08X}",
            },
            {
                "controller": "CS2",
                "mapping": _mapping_record(FIXED_CONTROLLER_MAPPINGS[1]),
                "dtm_bytes": CONTROLLER_FRAME_BYTES,
                "dtm_sha256": MAP_CS2_DTM_SHA256,
                "dtm_fnv1a": f"0x{MAP_CS2_DTM_FNV1A:08X}",
            },
        ],
    }
    if record != expected:
        raise N2PhotoCampaignError("frozen MAP primer identity changed")
    return frame, record


def _initializer_record(
    spec: _CellSpec,
    report: Mapping[str, Any],
    optimizer_report: Optional[Mapping[str, Any]],
) -> Mapping[str, Any]:
    halftone = report.get("halftone")
    initializer = halftone.get("initializer_report") if isinstance(halftone, Mapping) else None
    if spec.cell_id in {"Q1", "Q2"}:
        if initializer is not None or optimizer_report is not None:
            raise N2PhotoCampaignError(f"{spec.cell_id} unexpectedly gained a DBS initializer")
        return {"present": False}
    if not isinstance(initializer, Mapping) or not isinstance(optimizer_report, Mapping):
        raise N2PhotoCampaignError(f"{spec.cell_id} DBS initializer is missing")
    optimizer_input = optimizer_report.get("input")
    integrity = initializer.get("report_integrity")
    if not isinstance(optimizer_input, Mapping) or not isinstance(integrity, Mapping):
        raise N2PhotoCampaignError(f"{spec.cell_id} initializer binding is malformed")
    actual = {
        "present": True,
        "frame_sha256": initializer.get("frame_sha256"),
        "frame_fnv1a": initializer.get("frame_fnv1a"),
        "codes_sha256": optimizer_input.get("initial_codes_sha256"),
        "report_canonical_sha256": integrity.get("canonical_sha256"),
    }
    if actual != SHARED_INITIALIZER or optimizer_input.get(
        "initial_frame_sha256"
    ) != SHARED_INITIALIZER["frame_sha256"]:
        raise N2PhotoCampaignError(f"{spec.cell_id} frozen initializer identity changed")
    return actual


def _load_mapped_image(spec: _CellSpec) -> RasterImage:
    path = spec.directory / "mapped.png"
    try:
        with Image.open(path) as opened:
            opened.load()
            converted = opened.convert("RGB")
            width, height = converted.size
            pixels = converted.tobytes()
    except (OSError, ValueError) as error:
        raise N2PhotoCampaignError(f"{spec.cell_id} mapped preview decode failed: {error}") from error
    if (
        (width, height) != (WIDTH, HEIGHT)
        or len(pixels) != WIDTH * HEIGHT * 3
        or _sha256(pixels) != SHARED_MAPPED["rgb8_sha256"]
    ):
        raise N2PhotoCampaignError(f"{spec.cell_id} mapped RGB8 identity changed")
    return RasterImage(width, height, "RGB", pixels)


def _load_fixed_cell(spec: _CellSpec) -> _LoadedCell:
    """Deep-validate and re-bind every frozen byte identity for one cell."""

    try:
        manifest = validate_candidate_directory(spec.directory)
    except (CandidateError, OSError, ValueError) as error:
        raise N2PhotoCampaignError(
            f"{spec.cell_id} candidate directory validation failed: {error}"
        ) from error
    manifest_payload = _read_fixed_file(
        spec.directory / "manifest.json",
        size=None,
        sha256=spec.manifest_file_sha256,
        label=f"{spec.cell_id} manifest",
    )
    if manifest_payload != _canonical_json(manifest):
        raise N2PhotoCampaignError(f"{spec.cell_id} manifest is not canonical and bound")

    frame = _read_fixed_file(
        spec.directory / "frame.bin",
        size=FRAME_BYTES,
        sha256=spec.frame_sha256,
        label=f"{spec.cell_id} frame",
    )
    validate_frame(frame)
    codes = unpack_pixels(frame, WIDTH, HEIGHT)
    frame_record = _frame_record(frame)
    expected_frame = {
        "file": "frame.bin",
        "encoding": "canonical-row-major-two-4bit-codes-per-byte",
        "bytes": FRAME_BYTES,
        "sha256": spec.frame_sha256,
        "fnv1a": f"0x{spec.frame_fnv1a:08X}",
        "codes_sha256": spec.codes_sha256,
    }
    if manifest.get("frame") != expected_frame or _sha256(codes) != spec.codes_sha256:
        raise N2PhotoCampaignError(f"{spec.cell_id} frame/codes identity changed")
    expected_controllers = [
        {
            "controller": item["controller"],
            "mapping": item["mapping"],
            "dtm_bytes": item["dtm_bytes"],
            "dtm_fnv1a": item["dtm_fnv1a"],
        }
        for item in frame_record["controllers"]
    ]
    if manifest.get("controllers") != expected_controllers:
        raise N2PhotoCampaignError(f"{spec.cell_id} controller mapping/FNV identity changed")
    expected_dtm = (
        (spec.cs1_dtm_sha256, spec.cs1_dtm_fnv1a),
        (spec.cs2_dtm_sha256, spec.cs2_dtm_fnv1a),
    )
    for index, (actual, expected) in enumerate(
        zip(frame_record["controllers"], expected_dtm), start=1
    ):
        if actual["dtm_sha256"] != expected[0] or actual["dtm_fnv1a"] != f"0x{expected[1]:08X}":
            raise N2PhotoCampaignError(f"{spec.cell_id} CS{index} DTM SHA/FNV changed")

    previews = {
        **SHARED_PREVIEWS,
        "final": {
            "file": "final.png",
            "bytes": spec.final_preview_bytes,
            "sha256": spec.final_preview_sha256,
        },
        "model": {
            "file": "model.png",
            "bytes": spec.model_preview_bytes,
            "sha256": spec.model_preview_sha256,
        },
    }
    if manifest.get("previews") != previews:
        raise N2PhotoCampaignError(f"{spec.cell_id} frozen preview identities changed")

    simulation = manifest.get("simulation")
    report = simulation.get("report") if isinstance(simulation, Mapping) else None
    halftone = report.get("halftone") if isinstance(report, Mapping) else None
    optimizer_report = halftone.get("report") if isinstance(halftone, Mapping) else None
    if not isinstance(report, Mapping) or not isinstance(halftone, Mapping):
        raise N2PhotoCampaignError(f"{spec.cell_id} simulation report is missing")
    if spec.cell_id not in {"Q3", "Q4"}:
        optimizer_report = None
    if (
        simulation.get("report_canonical_sha256") != spec.simulation_report_sha256
        or report.get("report_integrity", {}).get("canonical_sha256")
        != spec.simulation_report_sha256
        or report.get("source_raster_sha256") != SHARED_SOURCE["pixels_sha256"]
    ):
        raise N2PhotoCampaignError(f"{spec.cell_id} simulation report identity changed")

    options_value = _expected_options(spec)
    expected_options = {
        "canonical_sha256": spec.options_canonical_sha256,
        "value": options_value,
    }
    if (
        manifest.get("source") != SHARED_SOURCE
        or manifest.get("mapped") != SHARED_MAPPED
        or manifest.get("profile") != SHARED_PROFILE
        or manifest.get("options") != expected_options
        or report.get("protections") != SHARED_PROTECTION
        or halftone.get("algorithm") != spec.algorithm
        or halftone.get("seed") != SHARED_SEED
        or halftone.get("budget") != options_value["budget"]
    ):
        raise N2PhotoCampaignError(f"{spec.cell_id} source/mapping/profile/options/protection changed")
    integrity = manifest.get("manifest_integrity")
    if (
        manifest.get("kind") != EXPECTED_CANDIDATE_KIND
        or not isinstance(integrity, Mapping)
        or integrity.get("canonical_sha256") != spec.manifest_canonical_sha256
    ):
        raise N2PhotoCampaignError(f"{spec.cell_id} candidate manifest identity changed")

    initializer = _initializer_record(spec, report, optimizer_report)
    own_loss: Optional[Mapping[str, Any]] = None
    if spec.cell_id in {"Q3", "Q4"}:
        assert isinstance(optimizer_report, Mapping)
        loss = optimizer_report.get("loss")
        search = optimizer_report.get("search")
        if not isinstance(loss, Mapping) or not isinstance(search, Mapping):
            raise N2PhotoCampaignError(f"{spec.cell_id} optimizer evidence is missing")
        if (
            _sha256(_canonical_json(loss)) != spec.own_loss_sha256
            or loss.get("initial", {}).get("total") != spec.own_initial_total
            or loss.get("final", {}).get("total") != spec.own_final_total
            or not spec.own_final_total < spec.own_initial_total
            or optimizer_report.get("budget", {}).get("stop_reason") != "evaluation_budget"
        ):
            raise N2PhotoCampaignError(f"{spec.cell_id} frozen loss/improvement evidence changed")
        own_loss = loss

    mapped_image = _load_mapped_image(spec)
    record = {
        "cell_id": spec.cell_id,
        "review_order": spec.ordinal,
        "algorithm": spec.algorithm,
        "artifact": {
            "artifact_id": spec.artifact_id,
            "workspace_relative_directory": f".test-output/hardware/{spec.artifact_id}",
            "manifest_file_sha256": spec.manifest_file_sha256,
            "manifest_canonical_sha256": spec.manifest_canonical_sha256,
        },
        "source": dict(SHARED_SOURCE),
        "mapped": {**SHARED_MAPPED, "preview": dict(SHARED_PREVIEWS["mapped"])},
        "profile": dict(SHARED_PROFILE),
        "options": expected_options,
        "protection": dict(SHARED_PROTECTION),
        "initializer": dict(initializer),
        "frame": {**frame_record, "codes_sha256": spec.codes_sha256},
        "previews": previews,
        "simulation_report_canonical_sha256": spec.simulation_report_sha256,
        "optimizer_loss": own_loss,
        "classification": {
            "natural_photo_input": True,
            "candidate_evidence_ready": True,
            "hardware_tested": False,
            "hardware_ready": False,
            "upload_authorized": False,
        },
    }
    return _LoadedCell(spec, manifest, record, frame, codes, mapped_image, optimizer_report)


def _validate_firmware_binary() -> Mapping[str, Any]:
    # `.pio` is a local build cache and is commonly absent in clean CI clones.
    # Absence therefore does not change the manifest or weaken its frozen P0
    # firmware identity.  If the cache artifact is present, however, it must be
    # a regular file and match byte-for-byte or compilation fails closed.
    if os.path.lexists(FIRMWARE_BINARY):
        if FIRMWARE_BINARY.is_symlink() or not FIRMWARE_BINARY.is_file():
            raise N2PhotoCampaignError("RC2G firmware binary path is not a regular file")
        _read_fixed_file(
            FIRMWARE_BINARY,
            size=FIRMWARE_BINARY_BYTES,
            sha256=FIRMWARE_BINARY_SHA256,
            label="RC2G firmware binary",
        )
    return {
        **FIRMWARE_CONTRACT,
        "bytes": FIRMWARE_BINARY_BYTES,
        "local_build_artifact_required_for_offline_compile": False,
        "if_present_must_match_frozen_identity": True,
    }


def _identity_observation_model() -> OverlapObservationModel:
    kernel = SpatialKernel(1, 1, (1.0,))
    return OverlapObservationModel(
        "s1-identity-1x1-simulation-v1",
        tuple((code, kernel) for code in ALLOWED_CODES),
    )


def _assert_frozen_loss(
    actual: Mapping[str, Any], expected: Mapping[str, float], *, label: str
) -> None:
    if set(actual) != set(expected):
        raise N2PhotoCampaignError(f"{label} loss components changed")
    for key, expected_value in expected.items():
        value = actual.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isclose(float(value), expected_value, rel_tol=0.0, abs_tol=2e-15)
        ):
            raise N2PhotoCampaignError(f"{label} frozen {key} loss changed")


def _scientific_gate(loaded: Mapping[str, _LoadedCell]) -> Mapping[str, Any]:
    q3 = loaded["Q3"]
    q4 = loaded["Q4"]
    if q3.mapped_image != q4.mapped_image:
        raise N2PhotoCampaignError("Q3/Q4 mapped raster bytes are not identical")
    if not isinstance(q3.optimizer_report, Mapping) or not isinstance(
        q4.optimizer_report, Mapping
    ):
        raise N2PhotoCampaignError("Q3/Q4 optimizer evidence is missing")

    q3_search = q3.optimizer_report.get("search")
    q4_search = q4.optimizer_report.get("search")
    if not isinstance(q3_search, Mapping) or not isinstance(q4_search, Mapping):
        raise N2PhotoCampaignError("Q3/Q4 search evidence is missing")
    q3_coverage = q3_search.get("coverage")
    q4_coverage = q4_search.get("coverage")
    if not isinstance(q3_coverage, Mapping) or not isinstance(q4_coverage, Mapping):
        raise N2PhotoCampaignError("Q3/Q4 coverage evidence is missing")
    if q3_coverage != q4_coverage:
        raise N2PhotoCampaignError("Q3/Q4 proposal coverage/trace is not common")
    if (
        _sha256(_canonical_json(q3_coverage)) != COVERAGE_CANONICAL_SHA256
        or q3_coverage.get("proposal_trace_sha256") != PROPOSAL_TRACE_SHA256
    ):
        raise N2PhotoCampaignError("Q3/Q4 frozen proposal coverage identity changed")

    tile_grid = q3_coverage.get("tile_grid")
    split = q3_coverage.get("horizontal_split")
    if not isinstance(tile_grid, Mapping) or not isinstance(split, Mapping):
        raise N2PhotoCampaignError("Q3/Q4 coverage geometry is missing")
    counts = tile_grid.get("proposal_counts")
    if (
        not isinstance(counts, list)
        or len(counts) != 160
        or _sha256(_canonical_json(counts)) != TILE_COUNTS_CANONICAL_SHA256
        or tile_grid.get("columns") != 16
        or tile_grid.get("rows") != 10
        or tile_grid.get("nonempty_tiles") != 160
        or tile_grid.get("empty_tiles") != 0
        or tile_grid.get("panel_1024x600_exact_64x60") is not True
        or tile_grid.get("exact_tile_width") != 64
        or tile_grid.get("exact_tile_height") != 60
        or tile_grid.get("minimum_proposals") != 193
        or tile_grid.get("maximum_proposals") != 533
    ):
        raise N2PhotoCampaignError("Q3/Q4 160-tile coverage contract changed")
    proposals = q3_search.get("proposals")
    left = split.get("left_proposals")
    right = split.get("right_proposals")
    ratio = q3_coverage.get("primary_coverage_ratio")
    if (
        proposals != 65_431
        or q3_search.get("evaluations") != 262_144
        or left != 32_967
        or right != 32_464
        or left + right != proposals
        or ratio != 0.11501070123461406
        or ratio < 0.10
        or not 0.45 <= left / proposals <= 0.55
        or not 0.45 <= right / proposals <= 0.55
        or q3_coverage.get("unlocked_pixels") != 534_985
        or q3_coverage.get("unique_primary_pixels") != 61_529
        or q3_coverage.get("unique_touched_pixels") != 75_701
    ):
        raise N2PhotoCampaignError("Q3/Q4 proposal coverage threshold/balance changed")

    expected_constraints = {
        "provided": True,
        "mask_sha256": SHARED_PROTECTION["constraint_mask_sha256"],
        "locked_pixels": SHARED_PROTECTION["locked_pixels"],
        "unconstrained_sentinel": SHARED_PROTECTION["unconstrained_sentinel"],
    }
    expected_input = {
        "initial_codes_sha256": SHARED_INITIALIZER["codes_sha256"],
        "initial_frame_sha256": SHARED_INITIALIZER["frame_sha256"],
        "raster_sha256": SHARED_MAPPED["rgb8_sha256"],
    }
    for cell_id, cell, search in (("Q3", q3, q3_search), ("Q4", q4, q4_search)):
        options = cell.manifest["options"]["value"]
        if (
            options.get("seed") != SHARED_SEED
            or options.get("budget") != SHARED_DBS_BUDGET
            or search.get("seed") != SHARED_SEED
            or search.get("code_constraints") != expected_constraints
            or cell.optimizer_report.get("input") != expected_input
            or cell.record["initializer"] != SHARED_INITIALIZER
        ):
            raise N2PhotoCampaignError(
                f"{cell_id} does not share the frozen seed/budget/mask/initializer"
            )

    difference = sum(left_code != right_code for left_code, right_code in zip(q3.codes, q4.codes))
    if len(q3.codes) != WIDTH * HEIGHT or len(q4.codes) != WIDTH * HEIGHT:
        raise N2PhotoCampaignError("Q3/Q4 code stream length changed")
    if difference != Q3_Q4_DIFFERING_PIXELS:
        raise N2PhotoCampaignError("Q3/Q4 frozen informational pixel difference changed")

    evaluation_options = DBSOptions(
        seed=SHARED_SEED,
        max_evaluations=SHARED_DBS_BUDGET["max_evaluations"],
        max_accepted_moves=SHARED_DBS_BUDGET["max_accepted_moves"],
        stagnation_evaluations=SHARED_DBS_BUDGET["stagnation_evaluations"],
    )
    q3_cross = evaluate_halftone_loss(
        q3.mapped_image,
        q3.codes,
        model=OverlapObservationModel.gaussian_simulation(),
        options=evaluation_options,
    ).to_dict()
    q4_cross = evaluate_halftone_loss(
        q4.mapped_image,
        q4.codes,
        model=_identity_observation_model(),
        options=evaluation_options,
    ).to_dict()
    _assert_frozen_loss(
        q3_cross,
        EXPECTED_CROSS_LOSSES["Q3_under_overlap_model"],
        label="Q3 under overlap model",
    )
    _assert_frozen_loss(
        q4_cross,
        EXPECTED_CROSS_LOSSES["Q4_under_identity_model"],
        label="Q4 under identity model",
    )

    assert q3.spec.own_initial_total is not None
    assert q3.spec.own_final_total is not None
    assert q4.spec.own_initial_total is not None
    assert q4.spec.own_final_total is not None
    identity_margin = q4_cross["total"] - q3.spec.own_final_total
    overlap_margin = q3_cross["total"] - q4.spec.own_final_total
    self_improvement = (
        q3.spec.own_final_total < q3.spec.own_initial_total
        and q4.spec.own_final_total < q4.spec.own_initial_total
    )
    diagonal_dominance = identity_margin > 0.0 and overlap_margin > 0.0
    coverage_pass = ratio >= 0.10 and tile_grid["nonempty_tiles"] == 160
    balance_pass = (
        0.45 <= left / proposals <= 0.55 and 0.45 <= right / proposals <= 0.55
    )
    gate_pass = self_improvement and diagonal_dominance and coverage_pass and balance_pass
    if not gate_pass:
        raise N2PhotoCampaignError("Q3/Q4 scientific separation gate did not pass")

    return {
        "gate_id": "n2p-q3-q4-model-specific-separation-v1",
        "scientific_gate_pass": True,
        "shared_schedule": {
            "seed": SHARED_SEED,
            "budget": dict(SHARED_DBS_BUDGET),
            "constraint_mask_sha256": SHARED_PROTECTION["constraint_mask_sha256"],
            "initializer": dict(SHARED_INITIALIZER),
            "proposal_trace_sha256": PROPOSAL_TRACE_SHA256,
            "coverage_canonical_sha256": COVERAGE_CANONICAL_SHA256,
        },
        "coverage": {
            "minimum_required_ratio": 0.10,
            "observed_primary_ratio": ratio,
            "unlocked_pixels": q3_coverage["unlocked_pixels"],
            "unique_primary_pixels": q3_coverage["unique_primary_pixels"],
            "unique_touched_pixels": q3_coverage["unique_touched_pixels"],
            "total_proposals": proposals,
            "left_proposals": left,
            "right_proposals": right,
            "left_ratio": left / proposals,
            "right_ratio": right / proposals,
            "required_side_ratio_range_inclusive": [0.45, 0.55],
            "tile_columns": 16,
            "tile_rows": 10,
            "nonempty_tiles": 160,
            "tile_count": 160,
            "tile_counts_canonical_sha256": TILE_COUNTS_CANONICAL_SHA256,
            "pass": coverage_pass and balance_pass,
        },
        "loss_matrix": {
            "identity_model": {
                "Q3_multicolor_dbs": q3.spec.own_final_total,
                "Q4_overlap_dbs": q4_cross["total"],
                "expected_winner": "Q3_multicolor_dbs",
                "diagonal_margin": identity_margin,
            },
            "overlap_model": {
                "Q3_multicolor_dbs": q3_cross["total"],
                "Q4_overlap_dbs": q4.spec.own_final_total,
                "expected_winner": "Q4_overlap_dbs",
                "diagonal_margin": overlap_margin,
            },
            "diagonal_dominance_pass": diagonal_dominance,
            "cross_loss_components": {
                "Q3_under_overlap_model": q3_cross,
                "Q4_under_identity_model": q4_cross,
            },
        },
        "initializer_improvement": {
            "Q3": {
                "initializer_total": q3.spec.own_initial_total,
                "final_total": q3.spec.own_final_total,
                "improvement": q3.spec.own_initial_total - q3.spec.own_final_total,
                "pass": True,
            },
            "Q4": {
                "initializer_total": q4.spec.own_initial_total,
                "final_total": q4.spec.own_final_total,
                "improvement": q4.spec.own_initial_total - q4.spec.own_final_total,
                "pass": True,
            },
        },
        "pixel_difference": {
            "differing_pixels": difference,
            "total_pixels": WIDTH * HEIGHT,
            "ratio": difference / (WIDTH * HEIGHT),
            "recorded": True,
            "required_as_sole_scientific_gate": False,
            "scientific_role": "informational corroboration, not the sole acceptance criterion",
        },
        "acceptance_basis": [
            "common deterministic seed/budget/mask/initializer/proposal trace",
            "proposal coverage at least 10 percent over all 160 tiles",
            "left/right proposal balance each within 45--55 percent",
            "each optimized output has lower own-model loss than its initializer",
            "cross-model loss matrix is diagonally dominant",
        ],
    }


def _compile_p0_campaign(
    loaded: Sequence[_LoadedCell], map_record: Mapping[str, Any]
) -> Mapping[str, Any]:
    actions: list[Mapping[str, Any]] = []
    sessions: list[Mapping[str, Any]] = []
    for item in loaded:
        spec = item.spec
        session_id = f"n2p-{spec.cell_id.lower()}-fresh-map-target"
        primer = build_fixed_action_declaration(
            campaign_id=CAMPAIGN_ID,
            session_id=session_id,
            cell_id=spec.cell_id,
            action_id=f"{spec.cell_id.lower()}-{spec.algorithm}-map-primer",
            phase="map-primer",
            frame=map_record,
        )
        target = build_fixed_action_declaration(
            campaign_id=CAMPAIGN_ID,
            session_id=session_id,
            cell_id=spec.cell_id,
            action_id=f"{spec.cell_id.lower()}-{spec.algorithm}-target",
            phase="target",
            frame=_frame_record(item.frame),
            prior_action_identity_sha256=primer["action_identity_sha256"],
            prior_scope="same_cell",
            minimum_interval_since_prior_seconds=0,
        )
        actions.extend((primer, target))
        sessions.append(
            build_session_contract(
                session_id=session_id,
                cell_id=spec.cell_id,
                power_mode="controller_fresh_boot",
                planned_cooldown_seconds=0,
                final_power_off_required=False,
                action_identity_sha256s=(
                    primer["action_identity_sha256"],
                    target["action_identity_sha256"],
                ),
            )
        )
    try:
        campaign = seal_campaign_contract(
            {
                "schema_version": 1,
                "kind": CAMPAIGN_KIND,
                "campaign_id": CAMPAIGN_ID,
                "panel": dict(PANEL_CONTRACT),
                "firmware": dict(FIRMWARE_CONTRACT),
                "actions": actions,
                "sessions": sessions,
                "classification": {
                    "offline_compiled": True,
                    "hardware_execution_authorized": False,
                    "automatic_execution": False,
                    "automatic_retry": False,
                    "automatic_recovery": False,
                    "network_io_performed": False,
                    "device_io_performed": False,
                },
            }
        )
    except CampaignContractError as error:
        raise N2PhotoCampaignError(f"P0 campaign contract failed: {error}") from error
    _validate_p0_campaign_shape(campaign)
    return campaign


def _validate_p0_campaign_shape(campaign: Mapping[str, Any]) -> None:
    try:
        validate_campaign_contract(campaign)
    except CampaignContractError as error:
        raise N2PhotoCampaignError(f"P0 campaign contract is invalid: {error}") from error
    actions = campaign["actions"]
    sessions = campaign["sessions"]
    if len(actions) != 8 or len(sessions) != 4:
        raise N2PhotoCampaignError("P0 campaign must contain eight actions in four sessions")
    action_ids: list[str] = []
    action_hashes: list[str] = []
    claim_filenames: list[str] = []
    for action in actions:
        validate_fixed_action_declaration(action)
        action_ids.append(action["identity"]["action_id"])
        action_hashes.append(action["action_identity_sha256"])
        claim_filenames.append(action["claim"]["filename"])
    for values in (action_ids, action_hashes, claim_filenames):
        if len(set(values)) != 8:
            raise N2PhotoCampaignError("P0 action/claim declarations are not all unique")
    if [session["cell_id"] for session in sessions] != ["Q1", "Q2", "Q3", "Q4"]:
        raise N2PhotoCampaignError("P0 session order or cell membership changed")
    for session in sessions:
        if (
            session["power_mode"] != "controller_fresh_boot"
            or session["requires_controller_fresh_boot"] is not True
            or session["requires_panel_power_cycle"] is not False
            or session["j2_may_remain_on_before_session"] is not True
            or session["automatic_advance"] is not False
            or len(session["action_identity_sha256s"]) != 2
        ):
            raise N2PhotoCampaignError("P0 session isolation/fresh-boot contract changed")


def _outer_cells(
    loaded: Sequence[_LoadedCell], p0_campaign: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    actions_by_cell: dict[str, list[Mapping[str, Any]]] = {}
    sessions_by_cell = {session["cell_id"]: session for session in p0_campaign["sessions"]}
    for action in p0_campaign["actions"]:
        actions_by_cell.setdefault(action["identity"]["cell_id"], []).append(action)
    cells = []
    for item in loaded:
        actions = actions_by_cell[item.spec.cell_id]
        if [action["identity"]["phase"] for action in actions] != ["map-primer", "target"]:
            raise N2PhotoCampaignError(f"{item.spec.cell_id} P0 action order changed")
        primer, target = actions
        session = sessions_by_cell[item.spec.cell_id]
        cells.append(
            {
                "cell_id": item.spec.cell_id,
                "review_order": item.spec.ordinal,
                "algorithm": item.spec.algorithm,
                "candidate": item.record,
                "session": {
                    "session_id": session["session_id"],
                    "session_canonical_sha256": session["integrity"]["canonical_sha256"],
                    "power_mode": session["power_mode"],
                    "requires_controller_fresh_boot": True,
                    "requires_panel_power_cycle": False,
                    "j2_may_remain_on_before_session": True,
                    "automatic_advance": False,
                    "sequence": ["fresh_boot", "own_map_primer", "own_target"],
                },
                "map_primer": {
                    "action_identity_sha256": primer["action_identity_sha256"],
                    "claim_declaration": primer["claim"],
                },
                "target": {
                    "action_identity_sha256": target["action_identity_sha256"],
                    "prior_action_identity_sha256": target["identity"]["prior"][
                        "action_identity_sha256"
                    ],
                    "prior_scope": "same_cell",
                    "claim_declaration": target["claim"],
                },
                "hardware_ready": False,
                "execution_authorized": False,
                "upload_authorized": False,
            }
        )
    return cells


def compile_campaign_manifest() -> Mapping[str, Any]:
    """Return the fixed, deeply validated, side-effect-free N2P manifest."""

    _map_frame, map_record = _validate_map_identity()
    firmware_evidence = _validate_firmware_binary()
    loaded_items = tuple(_load_fixed_cell(spec) for spec in CELL_SPECS)
    loaded = {item.spec.cell_id: item for item in loaded_items}
    scientific_gate = _scientific_gate(loaded)
    p0_campaign = _compile_p0_campaign(loaded_items, map_record)
    cells = _outer_cells(loaded_items, p0_campaign)
    unsigned: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "campaign_id": CAMPAIGN_ID,
        "phase": "N2P",
        "purpose": "natural-photo-four-algorithm-offline-campaign-compilation",
        "classification": {
            "experimental": True,
            "formal": False,
            "natural_photo_input": True,
            "candidate_set_ready": True,
            "algorithm_qualification": False,
            "hardware_tested": False,
            "hardware_ready": False,
            "hardware_execution_authorized": False,
            "upload_authorized": False,
            "offline_compiler_only": True,
        },
        "transport": {
            "mode": "offline-read-only-compile",
            "candidate_files_read": True,
            "output_files_written_by_compile": 0,
            "claims_created": 0,
            "authorizations_created": 0,
            "authorization_strings_issued": False,
            "network_io_performed": False,
            "device_io_performed": False,
            "serial_io_performed": False,
            "gpio_io_performed": False,
            "firmware_upload_performed": False,
            "visible_refreshes_performed": 0,
            "execution_authorized": False,
            "upload_authorized": False,
        },
        "shared_evidence": {
            "source": dict(SHARED_SOURCE),
            "mapped": dict(SHARED_MAPPED),
            "profile": dict(SHARED_PROFILE),
            "protection": dict(SHARED_PROTECTION),
            "map_primer": {"fixture": MAP_FIXTURE, "frame": map_record},
            "firmware": firmware_evidence,
        },
        "scientific_gate": scientific_gate,
        "p0_campaign_contract": p0_campaign,
        "execution_graph": {
            "disconnected_component_count": 4,
            "inter_cell_edges": [],
            "components": [
                {
                    "cell_id": cell["cell_id"],
                    "session_id": cell["session"]["session_id"],
                    "nodes": [
                        "controller_fresh_boot",
                        cell["map_primer"]["action_identity_sha256"],
                        cell["target"]["action_identity_sha256"],
                    ],
                    "edges": [
                        "controller_fresh_boot -> own_map_primer",
                        "own_map_primer_PASS -> own_target",
                    ],
                }
                for cell in cells
            ],
        },
        "cells": cells,
        "readiness": {
            "candidate_set_ready": True,
            "hardware_ready": False,
            "execution_runner_present": False,
            "reviewed_limit_profile_present": False,
            "scoring_contract_present": False,
            "camera_protocol_present": False,
            "panel_instance_bound": False,
            "prior_result_binding_implemented": False,
            "claim_consumption_implemented": False,
            "hardware_execution_authorized": False,
            "upload_authorized": False,
            "blockers": [
                "eight-action fixed runner is not implemented",
                "reviewed visible-refresh limit profile is not present",
                "visual scoring contract and camera protocol are not frozen",
                "physical panel instance is not bound to the offline placeholder",
                "per-cell MAP PASS result binding and claim consumption are not implemented",
            ],
        },
        "compiler_effects": {
            "fixed_action_declarations": 8,
            "unique_action_identity_sha256s": 8,
            "unique_claim_declarations": 8,
            "sessions": 4,
            "claims_created": 0,
            "authorizations_created": 0,
            "network_requests": 0,
            "device_operations": 0,
            "visible_refreshes": 0,
        },
    }
    canonical_sha = _sha256(_canonical_json(unsigned))
    manifest: dict[str, Any] = {
        **unsigned,
        "manifest_integrity": {
            "canonical_sha256": canonical_sha,
            "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
        },
    }
    validate_compiled_manifest(manifest)
    file_sha = _sha256(_canonical_json(manifest))
    if (
        EXPECTED_MANIFEST_CANONICAL_SHA256 is not None
        and canonical_sha != EXPECTED_MANIFEST_CANONICAL_SHA256
    ):
        raise N2PhotoCampaignError("frozen N2P manifest canonical identity changed")
    if EXPECTED_MANIFEST_FILE_SHA256 is not None and file_sha != EXPECTED_MANIFEST_FILE_SHA256:
        raise N2PhotoCampaignError("frozen N2P manifest file identity changed")
    return manifest


def validate_compiled_manifest(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate one in-memory outer manifest without creating claims or I/O."""

    expected_keys = {
        "schema_version",
        "kind",
        "campaign_id",
        "phase",
        "purpose",
        "classification",
        "transport",
        "shared_evidence",
        "scientific_gate",
        "p0_campaign_contract",
        "execution_graph",
        "cells",
        "readiness",
        "compiler_effects",
        "manifest_integrity",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != expected_keys:
        raise N2PhotoCampaignError("N2P manifest fields differ from the contract")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != MANIFEST_KIND
        or manifest.get("campaign_id") != CAMPAIGN_ID
        or manifest.get("phase") != "N2P"
    ):
        raise N2PhotoCampaignError("N2P manifest identity is invalid")
    integrity = manifest.get("manifest_integrity")
    unsigned = dict(manifest)
    unsigned.pop("manifest_integrity")
    expected_integrity = {
        "canonical_sha256": _sha256(_canonical_json(unsigned)),
        "canonical_sha256_scope": MANIFEST_HASH_SCOPE,
    }
    if integrity != expected_integrity:
        raise N2PhotoCampaignError("N2P manifest canonical integrity is invalid")

    classification = manifest.get("classification")
    if not isinstance(classification, Mapping) or (
        classification.get("candidate_set_ready") is not True
        or classification.get("natural_photo_input") is not True
        or classification.get("hardware_ready") is not False
        or classification.get("hardware_execution_authorized") is not False
        or classification.get("upload_authorized") is not False
        or classification.get("offline_compiler_only") is not True
    ):
        raise N2PhotoCampaignError("N2P classification is not fail-closed")
    transport = manifest.get("transport")
    zero_transport = (
        "output_files_written_by_compile",
        "claims_created",
        "authorizations_created",
        "network_io_performed",
        "device_io_performed",
        "serial_io_performed",
        "gpio_io_performed",
        "firmware_upload_performed",
        "visible_refreshes_performed",
    )
    if (
        not isinstance(transport, Mapping)
        or any(transport.get(field) not in {0, False} for field in zero_transport)
        or transport.get("execution_authorized") is not False
        or transport.get("upload_authorized") is not False
        or transport.get("authorization_strings_issued") is not False
    ):
        raise N2PhotoCampaignError("N2P transport is not zero-side-effect and unauthorized")

    shared = manifest.get("shared_evidence")
    if (
        not isinstance(shared, Mapping)
        or shared.get("source") != SHARED_SOURCE
        or shared.get("mapped") != SHARED_MAPPED
        or shared.get("profile") != SHARED_PROFILE
        or shared.get("protection") != SHARED_PROTECTION
        or shared.get("map_primer", {}).get("fixture") != MAP_FIXTURE
        or shared.get("map_primer", {}).get("frame", {}).get("sha256") != MAP_FRAME_SHA256
        or shared.get("firmware")
        != {
            **FIRMWARE_CONTRACT,
            "bytes": FIRMWARE_BINARY_BYTES,
            "local_build_artifact_required_for_offline_compile": False,
            "if_present_must_match_frozen_identity": True,
        }
    ):
        raise N2PhotoCampaignError("N2P shared frozen evidence changed")

    p0_campaign = manifest.get("p0_campaign_contract")
    if not isinstance(p0_campaign, Mapping):
        raise N2PhotoCampaignError("N2P P0 campaign is missing")
    _validate_p0_campaign_shape(p0_campaign)
    if p0_campaign.get("panel") != PANEL_CONTRACT or p0_campaign.get(
        "firmware"
    ) != FIRMWARE_CONTRACT:
        raise N2PhotoCampaignError("N2P P0 panel/firmware contract changed")

    cells = manifest.get("cells")
    if not isinstance(cells, list) or [cell.get("cell_id") for cell in cells] != [
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    ]:
        raise N2PhotoCampaignError("N2P cell order or membership changed")
    actions = {
        (action["identity"]["cell_id"], action["identity"]["phase"]): action
        for action in p0_campaign["actions"]
    }
    for spec, cell in zip(CELL_SPECS, cells):
        candidate = cell.get("candidate")
        if (
            cell.get("algorithm") != spec.algorithm
            or cell.get("review_order") != spec.ordinal
            or not isinstance(candidate, Mapping)
            or candidate.get("artifact", {}).get("artifact_id") != spec.artifact_id
            or candidate.get("artifact", {}).get("manifest_file_sha256")
            != spec.manifest_file_sha256
            or candidate.get("artifact", {}).get("manifest_canonical_sha256")
            != spec.manifest_canonical_sha256
            or candidate.get("frame", {}).get("sha256") != spec.frame_sha256
            or candidate.get("frame", {}).get("codes_sha256") != spec.codes_sha256
            or candidate.get("options", {}).get("canonical_sha256")
            != spec.options_canonical_sha256
            or candidate.get("previews", {}).get("final", {}).get("sha256")
            != spec.final_preview_sha256
            or candidate.get("previews", {}).get("model", {}).get("sha256")
            != spec.model_preview_sha256
            or cell.get("hardware_ready") is not False
            or cell.get("execution_authorized") is not False
            or cell.get("upload_authorized") is not False
        ):
            raise N2PhotoCampaignError(f"{spec.cell_id} outer candidate binding changed")
        primer = actions[(spec.cell_id, "map-primer")]
        target = actions[(spec.cell_id, "target")]
        if (
            cell.get("map_primer", {}).get("action_identity_sha256")
            != primer["action_identity_sha256"]
            or cell.get("map_primer", {}).get("claim_declaration") != primer["claim"]
            or cell.get("target", {}).get("action_identity_sha256")
            != target["action_identity_sha256"]
            or cell.get("target", {}).get("prior_action_identity_sha256")
            != primer["action_identity_sha256"]
            or cell.get("target", {}).get("claim_declaration") != target["claim"]
        ):
            raise N2PhotoCampaignError(f"{spec.cell_id} outer P0 action binding changed")

    graph = manifest.get("execution_graph")
    if (
        not isinstance(graph, Mapping)
        or graph.get("disconnected_component_count") != 4
        or graph.get("inter_cell_edges") != []
        or len(graph.get("components", [])) != 4
    ):
        raise N2PhotoCampaignError("N2P execution graph is not four disconnected cells")
    gate = manifest.get("scientific_gate")
    if (
        not isinstance(gate, Mapping)
        or gate.get("scientific_gate_pass") is not True
        or gate.get("coverage", {}).get("pass") is not True
        or gate.get("coverage", {}).get("tile_count") != 160
        or gate.get("loss_matrix", {}).get("diagonal_dominance_pass") is not True
        or gate.get("pixel_difference", {}).get("differing_pixels")
        != Q3_Q4_DIFFERING_PIXELS
        or gate.get("pixel_difference", {}).get("required_as_sole_scientific_gate")
        is not False
    ):
        raise N2PhotoCampaignError("N2P scientific gate record is invalid")
    readiness = manifest.get("readiness")
    if (
        not isinstance(readiness, Mapping)
        or readiness.get("candidate_set_ready") is not True
        or readiness.get("hardware_ready") is not False
        or readiness.get("execution_runner_present") is not False
        or readiness.get("reviewed_limit_profile_present") is not False
        or readiness.get("scoring_contract_present") is not False
        or readiness.get("hardware_execution_authorized") is not False
        or readiness.get("upload_authorized") is not False
        or not readiness.get("blockers")
    ):
        raise N2PhotoCampaignError("N2P readiness must remain hardware-blocked")
    effects = manifest.get("compiler_effects")
    if effects != {
        "fixed_action_declarations": 8,
        "unique_action_identity_sha256s": 8,
        "unique_claim_declarations": 8,
        "sessions": 4,
        "claims_created": 0,
        "authorizations_created": 0,
        "network_requests": 0,
        "device_operations": 0,
        "visible_refreshes": 0,
    }:
        raise N2PhotoCampaignError("N2P compiler side-effect accounting changed")
    return manifest


def campaign_manifest_bytes() -> bytes:
    return _canonical_json(compile_campaign_manifest())


def describe_campaign_offline(
    manifest: Optional[Mapping[str, Any]] = None,
) -> Mapping[str, Any]:
    """Describe declarations and blockers; never create a claim or authorization."""

    selected = compile_campaign_manifest() if manifest is None else manifest
    validate_compiled_manifest(selected)
    action_descriptions = []
    for action in selected["p0_campaign_contract"]["actions"]:
        action_descriptions.append(
            {
                "cell_id": action["identity"]["cell_id"],
                "phase": action["identity"]["phase"],
                "action_id": action["identity"]["action_id"],
                "action_identity_sha256": action["action_identity_sha256"],
                "claim_declaration": action["claim"],
                "maximum_future_post_requests": 1,
                "claim_created": False,
                "authorization_created": False,
                "hardware_ready": False,
                "execution_authorized": False,
            }
        )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "kind": DESCRIPTION_KIND,
        "mode": "describe-only",
        "campaign_id": CAMPAIGN_ID,
        "manifest_canonical_sha256": selected["manifest_integrity"]["canonical_sha256"],
        "p0_campaign_canonical_sha256": selected["p0_campaign_contract"]["integrity"][
            "canonical_sha256"
        ],
        "candidate_set_ready": True,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "upload_authorized": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
        "actions": action_descriptions,
        "blockers": list(selected["readiness"]["blockers"]),
    }
    return {
        **unsigned,
        "integrity": {
            "canonical_sha256": _sha256(_canonical_json(unsigned)),
            "canonical_sha256_scope": DESCRIPTION_HASH_SCOPE,
        },
    }


def _safe_manifest_path(path: Path, *, must_exist: bool) -> Path:
    try:
        require_local_regular_path_syntax(path, label="N2P campaign manifest file")
    except LocalPathSafetyError as error:
        raise N2PhotoCampaignError(str(error)) from error
    if path.suffix.lower() != ".json":
        raise N2PhotoCampaignError("N2P campaign manifest path must end in .json")
    if must_exist:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise N2PhotoCampaignError(f"N2P campaign manifest does not exist: {error}") from error
        if path.is_symlink() or not resolved.is_file():
            raise N2PhotoCampaignError("N2P campaign manifest must be a real regular file")
        return resolved
    if os.path.lexists(path):
        raise N2PhotoCampaignError("output manifest already exists; refusing overwrite")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise N2PhotoCampaignError(f"output parent does not exist: {error}") from error
    if not parent.is_dir() or parent.is_symlink():
        raise N2PhotoCampaignError("output parent must be a real local directory")
    destination = parent / path.name
    if os.path.lexists(destination):
        raise N2PhotoCampaignError("output manifest already exists; refusing overwrite")
    return destination


def write_campaign_manifest(output_file: Path) -> Mapping[str, Any]:
    """Explicitly write one new canonical manifest; refuse every overwrite."""

    if not isinstance(output_file, Path):
        raise N2PhotoCampaignError("output_file must be pathlib.Path")
    destination = _safe_manifest_path(output_file, must_exist=False)
    manifest = compile_campaign_manifest()
    payload = _canonical_json(manifest)
    temporary = destination.parent / f".{destination.name}.tmp-{uuid.uuid4().hex}"
    linked = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        linked = True
        temporary.unlink(missing_ok=True)
    except FileExistsError as error:
        raise N2PhotoCampaignError("output manifest appeared; refusing overwrite") from error
    except OSError as error:
        if linked:
            raise N2PhotoCampaignError("manifest committed but staging cleanup failed") from error
        raise N2PhotoCampaignError(f"could not atomically write N2P manifest: {error}") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return manifest


def validate_campaign_manifest(manifest_file: Path) -> Mapping[str, Any]:
    """Strictly parse and compare a file with a fresh deep recompilation."""

    if not isinstance(manifest_file, Path):
        raise N2PhotoCampaignError("manifest_file must be pathlib.Path")
    path = _safe_manifest_path(manifest_file, must_exist=True)
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise N2PhotoCampaignError(f"could not read N2P campaign manifest: {error}") from error
    parsed = _strict_json_object(payload, label="N2P campaign manifest")
    if payload != _canonical_json(parsed):
        raise N2PhotoCampaignError("N2P campaign manifest is not canonical JSON")
    validate_compiled_manifest(parsed)
    expected = compile_campaign_manifest()
    if parsed != expected or payload != _canonical_json(expected):
        raise N2PhotoCampaignError("N2P campaign manifest differs from fixed deep recompilation")
    return parsed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", action="store_true", dest="print_manifest")
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--output-file", type=Path)
    mode.add_argument("--validate-file", type=Path)
    return parser.parse_args(argv)


def _summary(manifest: Mapping[str, Any], *, mode: str) -> Mapping[str, Any]:
    return {
        "ok": True,
        "mode": mode,
        "kind": manifest["kind"],
        "campaign_id": manifest["campaign_id"],
        "manifest_canonical_sha256": manifest["manifest_integrity"]["canonical_sha256"],
        "manifest_file_sha256": _sha256(_canonical_json(manifest)),
        "cell_count": len(manifest["cells"]),
        "action_declaration_count": len(manifest["p0_campaign_contract"]["actions"]),
        "unique_claim_declaration_count": manifest["compiler_effects"][
            "unique_claim_declarations"
        ],
        "candidate_set_ready": True,
        "hardware_ready": False,
        "hardware_execution_authorized": False,
        "upload_authorized": False,
        "claim_created": False,
        "authorization_created": False,
        "network_io_performed": False,
        "device_io_performed": False,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        if args.output_file is not None:
            manifest = write_campaign_manifest(args.output_file)
            output = _summary(manifest, mode="written")
        elif args.validate_file is not None:
            manifest = validate_campaign_manifest(args.validate_file)
            output = _summary(manifest, mode="validated")
        else:
            manifest = compile_campaign_manifest()
            output = (
                describe_campaign_offline(manifest)
                if args.describe
                else manifest
            )
    except (N2PhotoCampaignError, CampaignContractError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(_canonical_json(output).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
