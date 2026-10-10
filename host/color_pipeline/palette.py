"""Six-colour palette configuration with explicit calibration provenance."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from host.epd_frame import PHYSICAL_COLOR_CODES

from .color import Lab, LinearRGB, lab_to_linear_rgb, lab_to_srgb8


class PaletteError(ValueError):
    """Raised when palette data is incomplete or internally inconsistent."""


PALETTE_SCHEMA_VERSION = 2
PALETTE_CANONICAL_HASH_SCOPE = (
    "effective normalized palette schema v2; UTF-8 JSON with sorted keys, "
    "no whitespace, ensure_ascii=false, allow_nan=false"
)
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")

# Render-path binding: which waveform/LUT path the measured Lab values belong
# to. "otp" is the production stock path (codes follow the physical frame
# contract below). "l535_r20" is the L535 runtime-LUT path whose measured
# nibble-to-colour mapping differs (PAL1 evidence, 2026-09-25): white is at
# code 7, blue at code 0, red at code 1, yellow at code 4, green at code 6,
# black at code 3 on this panel.
RENDER_PATH_OTP = "otp"
RENDER_PATH_L535_R20 = "l535_r20"
RENDER_PATHS = (RENDER_PATH_OTP, RENDER_PATH_L535_R20)


# These names are part of the physical frame contract, not editable display
# labels.  In particular, code 0 is black and code 1 is white; allowing a
# profile to exchange those names would make white protection drive black ink.
_PHYSICAL_COLOR_NAMES = {
    0x0: "black",
    0x1: "white",
    0x2: "yellow",
    0x3: "red",
    0x5: "blue",
    0x6: "green",
}


@dataclass(frozen=True)
class CalibrationProvenance:
    """Auditable measurement artifact reference for a calibrated palette."""

    measurement_id: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.measurement_id, str) or not self.measurement_id.strip():
            raise PaletteError("calibration measurement_id must be a non-empty string")
        if any(ord(character) < 0x20 for character in self.measurement_id):
            raise PaletteError("calibration measurement_id must not contain controls")
        if not isinstance(self.artifact_sha256, str) or not _SHA256_PATTERN.fullmatch(
            self.artifact_sha256
        ):
            raise PaletteError("calibration artifact_sha256 must be exactly 64 hex digits")
        object.__setattr__(self, "measurement_id", self.measurement_id.strip())
        object.__setattr__(self, "artifact_sha256", self.artifact_sha256.lower())


def _finite_triple(values: Sequence[Any], label: str) -> Tuple[float, float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise PaletteError(f"{label} must contain exactly three numbers")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ):
        raise PaletteError(f"{label} components must be numeric and not boolean")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise PaletteError(f"{label} must contain only finite numbers")
    return result  # type: ignore[return-value]


def _rgb_triple(values: Sequence[Any], label: str) -> Tuple[int, int, int]:
    if not isinstance(values, (list, tuple)) or len(values) != 3:
        raise PaletteError(f"{label} must contain exactly three integers")
    result = []
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
            raise PaletteError(f"{label} components must be integers in [0, 255]")
        result.append(value)
    return tuple(result)  # type: ignore[return-value]


@dataclass(frozen=True)
class PaletteEntry:
    code: int
    name: str
    lab: Lab
    preview_rgb: Tuple[int, int, int]

    def __post_init__(self) -> None:
        if not isinstance(self.code, int) or isinstance(self.code, bool):
            raise PaletteError("palette entry code must be an integer")
        if not isinstance(self.name, str) or not self.name.strip():
            raise PaletteError("palette entry name must be a non-empty string")
        lab = _finite_triple(self.lab, f"palette entry {self.code} Lab")
        if not 0.0 <= lab[0] <= 100.0:
            raise PaletteError("palette Lab lightness must be in [0, 100]")
        preview = _rgb_triple(self.preview_rgb, f"palette entry {self.code} preview_rgb")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "lab", lab)
        object.__setattr__(self, "preview_rgb", preview)

    @property
    def diffusion_rgb(self) -> LinearRGB:
        """Return the measured-Lab colour projected into clamped linear sRGB."""

        return lab_to_linear_rgb(self.lab, clamp=True)


@dataclass(frozen=True)
class Palette:
    palette_id: str
    entries: Tuple[PaletteEntry, ...]
    calibrated: bool
    source: str
    illuminant: str = "D65"
    observer: str = "2deg"
    notes: str = ""
    calibration: Optional[CalibrationProvenance] = None
    render_path: str = RENDER_PATH_OTP

    def __post_init__(self) -> None:
        if not isinstance(self.calibrated, bool):
            raise PaletteError("calibrated must be boolean")
        if not isinstance(self.entries, (tuple, list)):
            raise PaletteError("entries must be a sequence of PaletteEntry values")
        if not all(isinstance(entry, PaletteEntry) for entry in self.entries):
            raise PaletteError("entries must contain PaletteEntry values")
        if not isinstance(self.palette_id, str) or not self.palette_id.strip():
            raise PaletteError("palette_id must not be empty")
        if not isinstance(self.source, str) or not self.source.strip():
            raise PaletteError("palette source/provenance must not be empty")
        if not isinstance(self.illuminant, str) or not isinstance(self.observer, str):
            raise PaletteError("illuminant and observer must be strings")
        if not isinstance(self.notes, str):
            raise PaletteError("notes must be a string")
        if not isinstance(self.render_path, str) or self.render_path not in RENDER_PATHS:
            raise PaletteError(f"render_path must be one of {list(RENDER_PATHS)}")
        if self.calibrated:
            if type(self.calibration) is not CalibrationProvenance:
                raise PaletteError(
                    "calibrated palette requires structured calibration provenance"
                )
        elif self.calibration is not None:
            raise PaletteError("uncalibrated palette must use calibration=null")
        if self.illuminant != "D65" or self.observer != "2deg":
            raise PaletteError(
                "this pipeline requires Lab values measured or adapted to D65/2deg"
            )
        if len(self.entries) != len(PHYSICAL_COLOR_CODES):
            raise PaletteError("palette must contain exactly six physical colours")
        if self.render_path == RENDER_PATH_OTP:
            codes = [entry.code for entry in self.entries]
            if set(codes) != set(PHYSICAL_COLOR_CODES) or len(codes) != len(set(codes)):
                expected = sorted(PHYSICAL_COLOR_CODES)
                raise PaletteError(f"palette codes must be exactly {expected}")
            for entry in self.entries:
                expected_name = _PHYSICAL_COLOR_NAMES[entry.code]
                if entry.name != expected_name:
                    raise PaletteError(
                        f"physical colour code {entry.code} must be named "
                        f"'{expected_name}', not '{entry.name}'"
                    )
            entries_by_code = {entry.code: entry for entry in self.entries}
            if entries_by_code[0x0].lab[0] >= entries_by_code[0x1].lab[0]:
                raise PaletteError("black Lab L* must be lower than white Lab L*")
            if entries_by_code[0x3].lab[1] <= entries_by_code[0x6].lab[1]:
                raise PaletteError("red Lab a* must be greater than green Lab a*")
            if entries_by_code[0x2].lab[2] <= entries_by_code[0x5].lab[2]:
                raise PaletteError("yellow Lab b* must be greater than blue Lab b*")
        else:
            # L535 R20 path: entry codes are L535 drive nibbles (0..7), unique;
            # names keep the six physical role names, but the role-to-code
            # mapping is the measured one, not the stock frame contract.
            names = sorted(entry.name for entry in self.entries)
            if names != sorted(_PHYSICAL_COLOR_NAMES.values()):
                raise PaletteError(
                    "l535_r20 palette must keep the six physical role names"
                )
            codes = [entry.code for entry in self.entries]
            if any(type(c) is not int or not 0 <= c <= 7 for c in codes) or \
                    len(set(codes)) != 6:
                raise PaletteError("l535_r20 codes must be six unique drive nibbles 0..7")
            by_name = {entry.name: entry for entry in self.entries}
            white_l = by_name["white"].lab[0]
            black_l = by_name["black"].lab[0]
            others = [entry.lab[0] for entry in self.entries
                      if entry.name not in ("white", "black")]
            if not all(white_l > value for value in others + [black_l]):
                raise PaletteError("l535_r20 white entry must be the brightest measured")
            if not all(black_l < value for value in others + [white_l]):
                raise PaletteError("l535_r20 black entry must be the darkest measured")
            for name in ("yellow", "red", "blue", "green"):
                lab = by_name[name].lab
                if math.hypot(lab[1], lab[2]) <= 8.0:
                    raise PaletteError(
                        f"l535_r20 {name} entry must be a measured chromatic colour"
                    )
        # Keep tie-breaking and reports stable even when JSON entries are reordered.
        object.__setattr__(self, "palette_id", self.palette_id.strip())
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda entry: entry.code)))

    def entry(self, code: int) -> PaletteEntry:
        if type(code) is not int:
            raise PaletteError("physical colour code must be an integer and not boolean")
        for entry in self.entries:
            if entry.code == code:
                return entry
        raise PaletteError(f"unknown physical colour code 0x{code:X}")

    @property
    def by_code(self) -> Dict[int, PaletteEntry]:
        return {entry.code: entry for entry in self.entries}

    def canonical_mapping(self) -> Dict[str, Any]:
        """Return the complete normalized palette payload used for hashing."""

        return {
            "schema_version": PALETTE_SCHEMA_VERSION,
            "palette_id": self.palette_id,
            "calibrated": self.calibrated,
            "source": self.source,
            "illuminant": self.illuminant,
            "observer": self.observer,
            "notes": self.notes,
            "calibration": (
                None
                if self.calibration is None
                else {
                    "measurement_id": self.calibration.measurement_id,
                    "artifact_sha256": self.calibration.artifact_sha256,
                }
            ),
            **({"render_path": self.render_path}
               if self.render_path != RENDER_PATH_OTP else {}),
            "entries": [
                {
                    "code": entry.code,
                    "name": entry.name,
                    "lab": list(entry.lab),
                    "preview_rgb": list(entry.preview_rgb),
                }
                for entry in self.entries
            ],
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.canonical_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    @property
    def canonical_sha256(self) -> str:
        """Audit fingerprint; this is not a signature or trust-store result."""

        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def palette_from_mapping(data: Mapping[str, Any]) -> Palette:
    if not isinstance(data, Mapping):
        raise PaletteError("palette document must be an object")
    schema_version = data.get("schema_version")
    if type(schema_version) is not int or schema_version != PALETTE_SCHEMA_VERSION:
        raise PaletteError(
            f"palette schema_version must be integer {PALETTE_SCHEMA_VERSION}"
        )
    palette_id = data.get("palette_id")
    source = data.get("source")
    calibrated = data.get("calibrated")
    illuminant = data.get("illuminant")
    observer = data.get("observer")
    if not isinstance(palette_id, str):
        raise PaletteError("palette_id must be a string")
    if not isinstance(source, str):
        raise PaletteError("source must be a string")
    if not isinstance(calibrated, bool):
        raise PaletteError("calibrated must be an explicit boolean")
    if not isinstance(illuminant, str) or not isinstance(observer, str):
        raise PaletteError("illuminant and observer must be explicit strings")
    if "calibration" not in data:
        raise PaletteError("palette schema v2 requires an explicit calibration field")
    raw_calibration = data.get("calibration")
    calibration: Optional[CalibrationProvenance]
    if raw_calibration is None:
        calibration = None
    elif isinstance(raw_calibration, Mapping):
        expected_calibration_fields = {"measurement_id", "artifact_sha256"}
        if set(raw_calibration) != expected_calibration_fields:
            raise PaletteError(
                "calibration must contain exactly measurement_id and artifact_sha256"
            )
        calibration = CalibrationProvenance(
            raw_calibration.get("measurement_id"),  # type: ignore[arg-type]
            raw_calibration.get("artifact_sha256"),  # type: ignore[arg-type]
        )
    else:
        raise PaletteError("calibration must be an object or null")
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise PaletteError("entries must be a list")
    entries = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            raise PaletteError(f"entry {index} must be an object")
        code = raw.get("code")
        name = raw.get("name")
        if type(code) is not int:
            raise PaletteError(f"entry {index} code must be an integer")
        if not isinstance(name, str):
            raise PaletteError(f"entry {index} name must be a string")
        lab = _finite_triple(raw.get("lab"), f"entry {index} Lab")
        preview_value = raw.get("preview_rgb")
        preview_rgb = (
            lab_to_srgb8(lab)
            if preview_value is None
            else _rgb_triple(preview_value, f"entry {index} preview_rgb")
        )
        entries.append(PaletteEntry(code, name.strip(), lab, preview_rgb))
    render_path = data.get("render_path", RENDER_PATH_OTP)
    notes = data.get("notes", "")
    if not isinstance(notes, str):
        raise PaletteError("notes must be a string")
    return Palette(
        palette_id.strip(),
        tuple(entries),
        calibrated,
        source.strip(),
        illuminant.strip(),
        observer.strip(),
        notes,
        calibration,
        render_path,
    )


def load_palette(path: str | Path) -> Palette:
    palette_path = Path(path)
    try:
        data = json.loads(palette_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PaletteError(f"cannot load palette {palette_path}: {error}") from error
    if not isinstance(data, Mapping):
        raise PaletteError("palette document must be a JSON object")
    return palette_from_mapping(data)


@lru_cache(maxsize=1)
def reference_palette() -> Palette:
    """Load the bundled uncalibrated mathematical sRGB reference palette."""

    return load_palette(Path(__file__).with_name("palettes") / "reference_srgb_v1.json")
