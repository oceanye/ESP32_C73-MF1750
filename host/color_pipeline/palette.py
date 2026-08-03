"""Six-colour palette configuration with explicit calibration provenance."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from host.epd_frame import PHYSICAL_COLOR_CODES

from .color import Lab, LinearRGB, lab_to_linear_rgb, lab_to_srgb8


class PaletteError(ValueError):
    """Raised when palette data is incomplete or internally inconsistent."""


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
        if self.illuminant != "D65" or self.observer != "2deg":
            raise PaletteError(
                "this pipeline requires Lab values measured or adapted to D65/2deg"
            )
        if len(self.entries) != len(PHYSICAL_COLOR_CODES):
            raise PaletteError("palette must contain exactly six physical colours")
        codes = [entry.code for entry in self.entries]
        if set(codes) != set(PHYSICAL_COLOR_CODES) or len(codes) != len(set(codes)):
            expected = sorted(PHYSICAL_COLOR_CODES)
            raise PaletteError(f"palette codes must be exactly {expected}")
        names = [entry.name.casefold() for entry in self.entries]
        if any(not name for name in names) or len(names) != len(set(names)):
            raise PaletteError("palette entry names must be non-empty and unique")
        # Keep tie-breaking and reports stable even when JSON entries are reordered.
        object.__setattr__(self, "palette_id", self.palette_id.strip())
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda entry: entry.code)))

    def entry(self, code: int) -> PaletteEntry:
        for entry in self.entries:
            if entry.code == code:
                return entry
        raise PaletteError(f"unknown physical colour code 0x{code:X}")

    @property
    def by_code(self) -> Dict[int, PaletteEntry]:
        return {entry.code: entry for entry in self.entries}


def palette_from_mapping(data: Mapping[str, Any]) -> Palette:
    if data.get("schema_version") != 1:
        raise PaletteError("palette schema_version must be 1")
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
    raw_entries = data.get("entries")
    if not isinstance(raw_entries, list):
        raise PaletteError("entries must be a list")
    entries = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, Mapping):
            raise PaletteError(f"entry {index} must be an object")
        code = raw.get("code")
        name = raw.get("name")
        if not isinstance(code, int) or isinstance(code, bool):
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
