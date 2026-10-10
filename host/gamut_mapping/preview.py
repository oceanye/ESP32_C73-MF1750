"""Three-stage monitor soft-proof artifacts for G1 -> C2 integration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from host.color_pipeline import QuantizationResult
from host.epd_frame import PHYSICAL_COLOR_CODES

from .mapper import GamutMappingError, GamutMappingResult, SOFT_PROOF_WARNING


THREE_STAGE_PREVIEW_SCHEMA_VERSION = 1
THREE_STAGE_PREVIEW_KIND = "mf1750-three-stage-soft-proof"
THREE_STAGE_PREVIEW_REPORT_HASH_SCOPE = (
    "entire three-stage preview report excluding report_integrity; UTF-8 JSON "
    "with sorted keys, no whitespace, ensure_ascii=false, allow_nan=false"
)


@dataclass(frozen=True)
class ThreeStagePreview:
    """Original, mapped-continuous and final-code monitor preview payloads."""

    width: int
    height: int
    original_rgb: bytes
    mapped_rgb: bytes
    final_rgb: bytes
    original_png: bytes
    mapped_png: bytes
    final_png: bytes
    _report_json: bytes

    @property
    def report(self) -> dict[str, Any]:
        return json.loads(self._report_json.decode("utf-8"))


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
        raise GamutMappingError(f"three-stage preview report is invalid: {error}") from error


def build_three_stage_preview(
    mapping: GamutMappingResult,
    quantization: QuantizationResult,
) -> ThreeStagePreview:
    """Bind three previews to the exact mapped raster and final C2 code stream."""

    if not isinstance(mapping, GamutMappingResult):
        raise GamutMappingError("mapping must be a GamutMappingResult")
    if not isinstance(quantization, QuantizationResult):
        raise GamutMappingError("quantization must be a QuantizationResult")
    dimensions = (mapping.mapped_image.width, mapping.mapped_image.height)
    if dimensions != (quantization.width, quantization.height):
        raise GamutMappingError("mapping and quantization dimensions differ")
    quantization_report = quantization.report.to_dict()
    expected_input_hash = hashlib.sha256(mapping.mapped_image.pixels).hexdigest()
    if quantization_report["input_raster"]["sha256"] != expected_input_hash:
        raise GamutMappingError(
            "final quantization is not bound to the mapped raster bytes"
        )
    if any(code not in PHYSICAL_COLOR_CODES for code in quantization.codes):
        raise GamutMappingError("final code stream contains an illegal physical colour")

    original_rgb = mapping.source_preview_rgb()
    mapped_rgb = mapping.mapped_preview_rgb()
    final_rgb = quantization.preview_rgb()
    original_png = mapping.source_preview_png()
    mapped_png = mapping.mapped_preview_png()
    final_png = quantization.preview_png()
    mapping_report = mapping.report.to_dict()
    report: dict[str, Any] = {
        "schema_version": THREE_STAGE_PREVIEW_SCHEMA_VERSION,
        "kind": THREE_STAGE_PREVIEW_KIND,
        "width": dimensions[0],
        "height": dimensions[1],
        "stages": [
            {
                "order": 1,
                "id": "original-normalized",
                "meaning": "decoded source monitor preview; no panel simulation claim",
                "raster_sha256": hashlib.sha256(mapping.source_image.pixels).hexdigest(),
                "rgb_sha256": hashlib.sha256(original_rgb).hexdigest(),
                "png_sha256": hashlib.sha256(original_png).hexdigest(),
            },
            {
                "order": 2,
                "id": "mapped-continuous",
                "meaning": "continuous G1 mapped target rendered as monitor sRGB soft proof",
                "raster_sha256": mapping_report["mapped_raster"]["canonical_sha256"],
                "rgb_sha256": hashlib.sha256(mapped_rgb).hexdigest(),
                "png_sha256": hashlib.sha256(mapped_png).hexdigest(),
            },
            {
                "order": 3,
                "id": "final-six-code",
                "meaning": "preview rendered strictly from the final C2 physical code stream",
                "codes_sha256": hashlib.sha256(quantization.codes).hexdigest(),
                "frame_sha256": hashlib.sha256(quantization.frame).hexdigest(),
                "rgb_sha256": hashlib.sha256(final_rgb).hexdigest(),
                "png_sha256": hashlib.sha256(final_png).hexdigest(),
            },
        ],
        "mapping_report_sha256": mapping_report["report_integrity"]["canonical_sha256"],
        "quantization_report_sha256": quantization_report["report_integrity"][
            "canonical_sha256"
        ],
        "simulation": True,
        "soft_proof_warning": SOFT_PROOF_WARNING,
        "hardware_tested": False,
        "device_io_performed": False,
    }
    canonical = _canonical_json(report)
    report["report_integrity"] = {
        "canonical_sha256": hashlib.sha256(canonical).hexdigest(),
        "canonical_sha256_scope": THREE_STAGE_PREVIEW_REPORT_HASH_SCOPE,
        "fingerprint_trust": (
            "audit fingerprint only; not a digital signature or trust-store decision"
        ),
    }
    return ThreeStagePreview(
        width=dimensions[0],
        height=dimensions[1],
        original_rgb=original_rgb,
        mapped_rgb=mapped_rgb,
        final_rgb=final_rgb,
        original_png=original_png,
        mapped_png=mapped_png,
        final_png=final_png,
        _report_json=_canonical_json(report),
    )


__all__ = [
    "THREE_STAGE_PREVIEW_KIND",
    "THREE_STAGE_PREVIEW_REPORT_HASH_SCOPE",
    "THREE_STAGE_PREVIEW_SCHEMA_VERSION",
    "ThreeStagePreview",
    "build_three_stage_preview",
]
