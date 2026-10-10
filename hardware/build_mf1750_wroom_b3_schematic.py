"""Build the MF1750 WROOM B3 R3 staging schematic, fail closed.

This generator deliberately does not edit the frozen B2 project or the B3
authoritative project during its default invocation.  It rebuilds the proven
B2 panel circuit from the project-owned structured S-expression helpers,
renames the former external ``3V3`` panel input to ``EPD_SW_3V3``, and adds the
WROOM, USB/charger, power-key, buck-boost, panel switch, guarded panel I/O, and
microSD circuits required by ``B3-WROOM-POWER-TF-R3-SCHEMATIC``.

The old DevKitC socket is retained as J2 but is DNP and connects only to the
MCU-side debug nets.  SI0 is not reduced to a one-way 74LVC125 channel: U6 is
the frozen SN74CB3Q3245PWR Ioff-rated eight-bit bilateral bus switch.  It is
powered by the actual post-R4 ``EPD_3V3`` rail, so all seven panel digital
lines are physically isolated whenever that rail is absent while SI0 remains
bidirectional for readback.  Q3 translates the SYS_3V3-domain GPIO38 control
into a ground-referenced pull-down on U6 /OE, so no MCU pin crosses directly
into the powered-down EPD domain.

Default output is a staging schematic.  ``--promote`` is the only path that
can replace the authoritative B3 schematic, and it is gated by the frozen B2
hashes, the expected current B3 hash, absence of KiCad lock files, successful
KiCad parse/netlist export, zero ERC errors, and zero ERC warnings.

This script performs no hardware, network, serial-port, relay, flashing, or
panel operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "hardware"
PROJECT = "mf1750_wroom_b3_power_tf"
REVISION = "B3-WROOM-POWER-TF-R3-SCHEMATIC"

B2_DIR = HARDWARE / "mf1750_devkitc_b2_pcba_margin"
B2_FROZEN_SHA256 = {
    "mf1750_devkitc_b2_pcba_margin.kicad_pro": (
        "fcd393069f22846615113f8296d6553c5ffeee8ba507b7475f81baae9fe4aa27"
    ),
    "mf1750_devkitc_b2_pcba_margin.kicad_sch": (
        "bc3116580b1e055db15e383569ad60db626e65aac225917c62b3a72120e703eb"
    ),
    "mf1750_devkitc_b2_pcba_margin.kicad_pcb": (
        "462e127279bacc894eab5e8cc242cd6d26e1d3ee87708ad398f8064b5a5c4238"
    ),
}

B3_DIR = HARDWARE / PROJECT
AUTHORITATIVE_SCHEMATIC = B3_DIR / f"{PROJECT}.kicad_sch"
EXPECTED_B3_PRE_PROMOTION_SHA256 = (
    "158e54c1b8e0301860239bd69d837215caf2a9f5d5a34687a32fee922b310bf0"
)
DEFAULT_STAGING = B3_DIR / "mf1750_wroom_b3_power_tf_r3_staging.kicad_sch"

KICAD_ROOT = Path(r"C:\Program Files\KiCad\10.0")
KICAD_CLI = KICAD_ROOT / "bin" / "kicad-cli.exe"
KICAD_SYMBOLS = KICAD_ROOT / "share" / "kicad" / "symbols"

# Empty by design: exact source-library definitions and instance property
# overrides reduce the KiCad 10.0.3 inventory to zero.  The partitioner retains
# reference-level support solely so any future reviewed exception would have to
# be explicit; in this revision every warning blocks promotion.
EXPECTED_ERC_LIBRARY_WARNING_REFS: dict[str, frozenset[str]] = {}

B3_LIBRARY_ASSERTIONS = {
    B3_DIR / "b3_wroom_symbols.kicad_sym": (
        "59e7a41e37d58a86fa76d99b4cf66d8f31a4d8f4d7f99df02519066406eee341"
    ),
    B3_DIR
    / "b3_wroom_footprints.pretty"
    / "TI_RNM0015A_VQFN-HR-15_2.5x3mm.kicad_mod": (
        "a2c9782e71aba23feef393fda5e2788016667d2993fa9b86fa36a81b4908bf9f"
    ),
    B3_DIR
    / "b3_wroom_footprints.pretty"
    / "TI_DDC0006A_SOT-23-6_2.9x1.6mm.kicad_mod": (
        "41a65892f60b7fa60e835da797037fdfaada4dda720cc239bb7c7dca9f74fd3a"
    ),
    B3_DIR / "b3_wroom_footprints.pretty" / "Coilcraft_XFL4020_4x4mm.kicad_mod": (
        "8e207fcbccd0e85e70b76de0a7e22a2c132a24e10b2ca1939ac88bc1dcdc95a5"
    ),
    B3_DIR / "b3_wroom_footprints.pretty" / "ALPS_SKSCLDE010_SidePush.kicad_mod": (
        "cc46c85f3300b3f2a6514da03fd75dd7f49d0d959438dd43db42fed5b63ae2f5"
    ),
}

sys.path.insert(0, str(HARDWARE))
import generate_mf1750_kicad_project as base  # noqa: E402
import generate_mf1750_production_v1 as a1  # noqa: E402


ROOT_SHEET_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{REVISION}/root-sheet"))
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, REVISION)

PANEL_FPC_FOOTPRINT = "MF1750_Production:XUNPU_FPC-05FB-50PH20_1x50_P0.5mm_DualContact"
DEBUG_SOCKET_FOOTPRINT = "MF1750_Compact:ESP32-S3-DevKitC-1_Socket"

R_0603 = "Resistor_SMD:R_0603_1608Metric"
R_0805 = "Resistor_SMD:R_0805_2012Metric"
R_1206 = "Resistor_SMD:R_1206_3216Metric"
C_0603 = "Capacitor_SMD:C_0603_1608Metric"
C_0805 = "Capacitor_SMD:C_0805_2012Metric"
C_1206 = "Capacitor_SMD:C_1206_3216Metric"
C_1210 = "Capacitor_SMD:C_1210_3225Metric"
SOT23_6 = "Package_TO_SOT_SMD:SOT-23-6"
TSSOP20 = "Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm"
TESTPOINT = "TestPoint:TestPoint_Pad_D1.0mm"
PTC_1206_SYMBOL = "B3_WROOM:PTC_BSMD1206_075_16V"

SN74CB3Q3245_PW_PIN_NAMES = {
    "1": "NC",
    "2": "A1",
    "3": "A2",
    "4": "A3",
    "5": "A4",
    "6": "A5",
    "7": "A6",
    "8": "A7",
    "9": "A8",
    "10": "GND",
    "11": "B8",
    "12": "B7",
    "13": "B6",
    "14": "B5",
    "15": "B4",
    "16": "B3",
    "17": "B2",
    "18": "B1",
    "19": "~{OE}",
    "20": "VCC",
}


HOLD_ITEMS = (
    "Battery pack MPN, capacity, discharge capability, connector mating order, "
    "and the real 10 kΩ NTC curve are not frozen.",
    "TPS63070 inductor saturation/current rating, capacitor DC-bias derating, "
    "and simultaneous Wi-Fi + TF-write + EPD-refresh thermal margin need review.",
    "TPS22950 1.50 kΩ ILIM setting must be checked against measured panel peak "
    "current and fault behaviour on a current-limited first article.",
    "R49 BAT-to-ADC divider top is DNP by default; fit only after shutdown leakage, "
    "ESP32 back-power, divider settling, and ADC calibration are verified.",
    "USB-C, battery, TF-card insertion, user-key, WROOM antenna, enclosure, and "
    "cable mechanics require physical/CAD review.",
    "The B3 PCB has not been synchronized to this schematic; parity, routing, "
    "DRC, unconnected-pad, SI, PI, thermal, EMC, and manufacturability gates are HOLD.",
)


@dataclass(frozen=True)
class PinSpec:
    number: str
    name: str
    electrical_type: str
    side: str = "left"


@dataclass(frozen=True)
class PinGeometry:
    x: float
    y: float
    rotation: int


@dataclass(frozen=True)
class SymbolSpec:
    lib_id: str
    value: str
    footprint: str
    datasheet: str
    description: str
    pins: tuple[PinSpec, ...]


@dataclass(frozen=True)
class TwoPinPlacement:
    ref: str
    value: str
    net1: str
    net2: str
    lib_id: str = "Local:R"
    footprint: str = R_0603
    dnp: bool = False


@dataclass(frozen=True)
class ValidationResult:
    kicad_version: str
    parse_returncode: int
    error_erc_returncode: int
    warning_erc_returncode: int
    error_report_sha256: str
    warning_report_sha256: str
    error_report: str
    warning_report: str
    error_counts: dict[str, int]
    allowed_warning_counts: dict[str, int]
    blocking_warning_counts: dict[str, int]
    allowed_warnings: tuple[tuple[str, str, str], ...]
    blocking_warnings: tuple[tuple[str, str, str], ...]

    @property
    def passed(self) -> bool:
        return (
            self.parse_returncode == 0
            and self.error_erc_returncode == 0
            and self.warning_erc_returncode == 0
            and not self.error_counts
            and not self.blocking_warnings
        )


class DeterministicUidStream:
    """Provide deterministic UUIDs to the repository's existing helpers."""

    def __init__(self) -> None:
        self.counter = 0

    def reset(self) -> None:
        self.counter = 0

    def __call__(self) -> str:
        self.counter += 1
        return str(uuid.uuid5(UUID_NAMESPACE, f"helper-object/{self.counter:06d}"))


UID_STREAM = DeterministicUidStream()
PLACED_REFS: set[str] = set()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_frozen_b2() -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, expected in B2_FROZEN_SHA256.items():
        path = B2_DIR / name
        if not path.is_file():
            raise RuntimeError(f"frozen B2 source missing: {path}")
        actual = sha256_file(path)
        observed[name] = actual
        if actual != expected:
            raise RuntimeError(
                f"frozen B2 hash mismatch for {path}: expected {expected}, got {actual}"
            )
    return observed


def assert_b3_custom_libraries() -> dict[str, str]:
    observed: dict[str, str] = {}
    for path, expected in B3_LIBRARY_ASSERTIONS.items():
        if not path.is_file():
            raise RuntimeError(f"required B3 custom library artifact missing: {path}")
        actual = sha256_file(path)
        observed[str(path.relative_to(ROOT))] = actual
        if actual != expected:
            raise RuntimeError(
                f"B3 custom library hash mismatch for {path}: "
                f"expected {expected}, got {actual}"
            )
    symbol_library = B3_DIR / "b3_wroom_symbols.kicad_sym"
    symbol_text = symbol_library.read_text(encoding="utf-8")
    switch_form = _find_symbol_form(symbol_text, "SN74CB3Q3245PWR")
    observed_pin_names = {
        pin.number: pin.name for pin in _pins_from_symbol_form(switch_form)
    }
    if observed_pin_names != SN74CB3Q3245_PW_PIN_NAMES:
        raise RuntimeError(
            "B3 custom SN74CB3Q3245PWR symbol does not match the TI PW0020A "
            f"physical pin map: expected {SN74CB3Q3245_PW_PIN_NAMES}, "
            f"got {observed_pin_names}"
        )
    tps63070_form = _find_symbol_form(symbol_text, "TPS63070RNMR")
    tps63070_pins = {pin.number: pin for pin in _pins_from_symbol_form(tps63070_form)}
    for number in ("7", "8"):
        pin = tps63070_pins.get(number)
        if pin is None or pin.name != "VOUT" or pin.electrical_type != "power_out":
            raise RuntimeError(
                "B3 custom TPS63070RNMR source pin contract changed: physical "
                f"pin {number} must remain VOUT/power_out before the documented "
                f"embedded ERC override, got {pin}"
            )
    ptc_form = _find_symbol_form(symbol_text, "PTC_BSMD1206_075_16V")
    ptc_pins = {pin.number: pin for pin in _pins_from_symbol_form(ptc_form)}
    if set(ptc_pins) != {"1", "2"} or any(
        pin.electrical_type != "passive" for pin in ptc_pins.values()
    ):
        raise RuntimeError(
            "B3 custom PTC_BSMD1206_075_16V must expose exactly two passive pins"
        )
    for required_fragment in (
        '(property "Footprint" "Resistor_SMD:R_1206_3216Metric"',
        '(property "ki_fp_filters" "R?1206*"',
        '(property "LCSC" "C883128"',
    ):
        if required_fragment not in ptc_form:
            raise RuntimeError(
                "B3 custom PTC_BSMD1206_075_16V contract is incomplete: "
                + required_fragment
            )
    return observed


def stable_uuid(key: str) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, key))


def sheet_grid(value: float) -> float:
    """Snap symbol centres to the inherited 2.54 mm schematic grid."""

    return base.grid(value)


def _extract_balanced_form(text: str, start: int) -> str:
    if start < 0 or start >= len(text) or text[start] != "(":
        raise ValueError("balanced-form start must point at '('")
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("unterminated S-expression form")


def _find_symbol_form(text: str, name: str) -> str:
    marker = f'(symbol "{name}"'
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"KiCad standard symbol not found: {name}")
    return _extract_balanced_form(text, start)


def _quoted_child(form: str, child: str) -> str:
    match = re.search(rf'\({re.escape(child)}\s+"((?:\\.|[^"\\])*)"', form)
    if not match:
        raise RuntimeError(f'missing ({child} "...") in symbol pin')
    return match.group(1).replace(r"\"", '"').replace(r"\\", "\\")


def _pins_from_symbol_form(form: str) -> list[PinSpec]:
    result: list[PinSpec] = []
    for match in re.finditer(r"\(pin\s+([a-z_]+)\s+([a-z_]+)", form):
        pin_form = _extract_balanced_form(form, match.start())
        number = _quoted_child(pin_form, "number")
        name = _quoted_child(pin_form, "name")
        at_match = re.search(
            r"\(at\s+[-+0-9.eE]+\s+[-+0-9.eE]+(?:\s+([-+0-9.eE]+))?\)",
            pin_form,
        )
        rotation = int(float(at_match.group(1) or 0)) if at_match else 0
        if rotation == 0:
            side = "left"
        elif rotation == 180:
            side = "right"
        elif match.group(1) in {"output", "power_out", "open_collector"}:
            side = "right"
        else:
            side = "left"
        result.append(PinSpec(number, name, match.group(1), side))
    return result


def _pin_geometries_from_symbol_form(form: str) -> dict[str, PinGeometry]:
    result: dict[str, PinGeometry] = {}
    for match in re.finditer(r"\(pin\s+[a-z_]+\s+[a-z_]+", form):
        pin_form = _extract_balanced_form(form, match.start())
        number = _quoted_child(pin_form, "number")
        at_match = re.search(
            r"\(at\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)"
            r"(?:\s+([-+0-9.eE]+))?\)",
            pin_form,
        )
        if not at_match:
            raise RuntimeError(f"symbol pin {number} has no parseable position")
        result[number] = PinGeometry(
            float(at_match.group(1)),
            float(at_match.group(2)),
            int(float(at_match.group(3) or 0)) % 360,
        )
    return result


def _symbol_library_path(lib_id: str) -> Path:
    library, _symbol_name = lib_id.split(":", 1)
    if library == "Local":
        return B3_DIR / "mf1750_local.kicad_sym"
    if library == "B3_WROOM":
        return B3_DIR / "b3_wroom_symbols.kicad_sym"
    return KICAD_SYMBOLS / f"{library}.kicad_sym"


def _source_symbol_form(lib_id: str) -> tuple[str, str, Path]:
    _library, symbol_name = lib_id.split(":", 1)
    path = _symbol_library_path(lib_id)
    if not path.is_file():
        raise RuntimeError(f"symbol source library missing for {lib_id}: {path}")
    text = path.read_text(encoding="utf-8")
    return _find_symbol_form(text, symbol_name), text, path


def exact_symbol_definition(lib_id: str) -> str:
    """Embed the exact source-library symbol while retaining its full lib ID."""

    form, _text, _path = _source_symbol_form(lib_id)
    _library, symbol_name = lib_id.split(":", 1)
    if re.search(r'\(extends\s+"', form):
        raise RuntimeError(
            f"exact embedded symbol must be non-inherited, got extends in {lib_id}"
        )
    form = form.replace(f'(symbol "{symbol_name}"', f'(symbol "{lib_id}"', 1)
    return "\n".join(f"\t\t{line}" for line in form.splitlines())


def _named_property_form(symbol_form: str, name: str) -> str:
    marker = f'(property "{name}"'
    start = symbol_form.find(marker)
    if start < 0:
        raise RuntimeError(f"symbol is missing required {name!r} property")
    return _extract_balanced_form(symbol_form, start)


def flattened_inherited_symbol_definition(lib_id: str) -> str:
    """Flatten one exact KiCad inherited symbol for deterministic embedding.

    KiCad's ``USBLC6-2SC6`` is an ``extends USBLC6-2P6`` symbol.  Embedded
    schematic libraries cannot retain that unresolved inheritance safely, so
    copy the parent's graphics/pins and apply every child identity/package
    property.  This keeps the source-library SC6 pin model and its SOT-23
    footprint filter instead of disguising an SC6 instance as the P6/SOT-666
    base symbol.
    """

    child_form, library_text, _path = _source_symbol_form(lib_id)
    _library, child_name = lib_id.split(":", 1)
    extends = re.search(r'\(extends\s+"([^"]+)"\)', child_form)
    if not extends:
        raise RuntimeError(f"flattening requires an inherited symbol: {lib_id}")
    parent_name = extends.group(1)
    parent_form = _find_symbol_form(library_text, parent_name)
    if re.search(r'\(extends\s+"', parent_form):
        raise RuntimeError(
            f"multi-level inherited symbol flattening is not reviewed: {lib_id}"
        )

    flattened = parent_form
    for property_name in (
        "Reference",
        "Value",
        "Footprint",
        "Datasheet",
        "Description",
        "ki_keywords",
        "ki_fp_filters",
    ):
        parent_property = _named_property_form(flattened, property_name)
        child_property = _named_property_form(child_form, property_name)
        flattened = flattened.replace(parent_property, child_property, 1)

    # Rename both the outer symbol and inherited nested drawing/unit forms.
    flattened = flattened.replace(
        f'(symbol "{parent_name}', f'(symbol "{child_name}'
    )
    flattened = flattened.replace(
        f'(symbol "{child_name}"', f'(symbol "{lib_id}"', 1
    )
    if re.search(r'\(extends\s+"', flattened):
        raise RuntimeError(f"flattened symbol still contains inheritance: {lib_id}")
    return "\n".join(f"\t\t{line}" for line in flattened.splitlines())


def symbol_definition_with_pin_type_overrides(
    lib_id: str, overrides: dict[str, tuple[str, str]]
) -> str:
    """Embed a source symbol with narrowly asserted ERC-type overrides."""

    form, _text, _path = _source_symbol_form(lib_id)
    _library, symbol_name = lib_id.split(":", 1)
    if re.search(r'\(extends\s+"', form):
        raise RuntimeError(f"pin type override cannot flatten inherited {lib_id}")
    observed: dict[str, str] = {}
    replacements: list[tuple[int, int, str]] = []
    for match in re.finditer(r"\(pin\s+([a-z_]+)\s+([a-z_]+)", form):
        pin_form = _extract_balanced_form(form, match.start())
        number = _quoted_child(pin_form, "number")
        if number not in overrides:
            continue
        observed[number] = match.group(1)
        replacements.append((match.start(1), match.end(1), overrides[number][1]))
    if set(observed) != set(overrides):
        raise RuntimeError(
            f"{lib_id} pin-type override mismatch: requested={sorted(overrides)}, "
            f"found={sorted(observed)}"
        )
    expected_original_types = {
        number: original_type
        for number, (original_type, _new_type) in overrides.items()
    }
    if observed != expected_original_types:
        raise RuntimeError(
            f"{lib_id} source pin types changed before ERC override: "
            f"expected={expected_original_types}, got={observed}"
        )
    for start, end, replacement in reversed(replacements):
        form = form[:start] + replacement + form[end:]
    form = form.replace(f'(symbol "{symbol_name}"', f'(symbol "{lib_id}"', 1)
    return "\n".join(f"\t\t{line}" for line in form.splitlines())


def source_pin_geometries(lib_id: str) -> dict[str, PinGeometry]:
    form, text, _path = _source_symbol_form(lib_id)
    chain: list[str] = []
    while True:
        chain.append(form)
        extends = re.search(r'\(extends\s+"([^"]+)"\)', form)
        if not extends:
            break
        form = _find_symbol_form(text, extends.group(1))
    result: dict[str, PinGeometry] = {}
    for inherited_form in reversed(chain):
        result.update(_pin_geometries_from_symbol_form(inherited_form))
    return result


def load_standard_pins(
    library: str,
    symbol_name: str,
    expected_names: dict[str, str],
) -> tuple[PinSpec, ...]:
    path = KICAD_SYMBOLS / library
    if not path.is_file():
        raise RuntimeError(f"KiCad standard symbol library missing: {path}")
    text = path.read_text(encoding="utf-8")
    form = _find_symbol_form(text, symbol_name)
    extends = re.search(r'\(extends\s+"([^"]+)"\)', form)
    pins: list[PinSpec] = []
    if extends:
        pins.extend(_pins_from_symbol_form(_find_symbol_form(text, extends.group(1))))
    pins.extend(_pins_from_symbol_form(form))
    by_number: dict[str, PinSpec] = {}
    for pin in pins:
        by_number[pin.number] = pin
    for number, expected_name in expected_names.items():
        if number not in by_number:
            raise RuntimeError(
                f"{library}:{symbol_name} missing expected physical pin {number}"
            )
        if by_number[number].name != expected_name:
            raise RuntimeError(
                f"{library}:{symbol_name} pin {number} changed: expected "
                f"{expected_name!r}, got {by_number[number].name!r}"
            )
    return tuple(by_number.values())


def standard_power_symbol_definition(name: str) -> str:
    path = KICAD_SYMBOLS / "power.kicad_sym"
    if not path.is_file():
        raise RuntimeError(f"KiCad standard power symbol library missing: {path}")
    form = _find_symbol_form(path.read_text(encoding="utf-8"), name)
    return form.replace(f'(symbol "{name}"', f'(symbol "power:{name}"', 1)


def _pin_geometry(spec: SymbolSpec) -> tuple[dict[str, tuple[float, float]], float]:
    left = [pin for pin in spec.pins if pin.side == "left"]
    right = [pin for pin in spec.pins if pin.side == "right"]
    count = max(len(left), len(right), 1)
    height = max(12.7, count * 2.54 + 5.08)
    top = (count - 1) * 1.27
    points: dict[str, tuple[float, float]] = {}
    for index, pin in enumerate(left):
        points[pin.number] = (-20.32, top - index * 2.54)
    for index, pin in enumerate(right):
        points[pin.number] = (20.32, top - index * 2.54)
    return points, height


def render_ic_symbol(spec: SymbolSpec) -> str:
    points, height = _pin_geometry(spec)
    local_name = spec.lib_id.split(":", 1)[-1]
    half_height = height / 2
    lines = [
        f'\t\t(symbol "{base.q(spec.lib_id)}"',
        "\t\t\t(pin_names (offset 1.016))",
        "\t\t\t(exclude_from_sim no)",
        "\t\t\t(in_bom yes)",
        "\t\t\t(on_board yes)",
        "\t\t\t(in_pos_files yes)",
        "\t\t\t(duplicate_pin_numbers_are_jumpers no)",
        base.prop("Reference", "U", 0, -half_height - 2.54),
        base.prop("Value", spec.value, 0, half_height + 2.54),
        base.prop("Footprint", spec.footprint, 0, 0, True),
        base.prop("Datasheet", spec.datasheet, 0, 0, True),
        base.prop("Description", spec.description, 0, 0, True),
        f'\t\t\t(symbol "{base.q(local_name)}_0_1"',
        f"\t\t\t\t(rectangle (start -17.78 {half_height:.2f}) "
        f"(end 17.78 {-half_height:.2f}) (stroke (width 0.254) "
        "(type default)) (fill (type background)))",
        "\t\t\t)",
        f'\t\t\t(symbol "{base.q(local_name)}_1_1"',
    ]
    for pin in spec.pins:
        x, y = points[pin.number]
        rotation = 0 if x < 0 else 180
        name = pin.name or pin.number
        lines.extend(
            [
                f"\t\t\t\t(pin {pin.electrical_type} line",
                f"\t\t\t\t\t(at {x:.2f} {y:.2f} {rotation})",
                "\t\t\t\t\t(length 2.54)",
                f'\t\t\t\t\t(name "{base.q(name)}" (effects (font (size 1.00 1.00))))',
                f'\t\t\t\t\t(number "{base.q(pin.number)}" '
                "(effects (font (size 1.00 1.00))))",
                "\t\t\t\t)",
            ]
        )
    lines.extend(["\t\t\t)", "\t\t\t(embedded_fonts no)", "\t\t)"])
    return "\n".join(lines)


def deterministic_symbol_instance(
    lib_id: str,
    ref: str,
    value: str,
    footprint: str,
    x: float,
    y: float,
    pins: list[str],
    dnp: bool = False,
) -> str:
    snapped_x = sheet_grid(x)
    snapped_y = sheet_grid(y)
    if abs(x - snapped_x) > 1e-9 or abs(y - snapped_y) > 1e-9:
        raise RuntimeError(
            f"{ref} symbol centre is off the 2.54 mm grid: "
            f"({x}, {y}) != ({snapped_x}, {snapped_y})"
        )
    if ref in PLACED_REFS:
        raise RuntimeError(f"duplicate schematic reference: {ref}")
    PLACED_REFS.add(ref)
    sid = stable_uuid(f"symbol/{ref}")
    virtual = ref.startswith("#")
    lines = [
        "\t(symbol",
        f'\t\t(lib_id "{base.q(lib_id)}")',
        f"\t\t(at {x:.2f} {y:.2f} 0)",
        "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)",
        f"\t\t(in_bom {'no' if ref.startswith('TP') or virtual else 'yes'})",
        f"\t\t(on_board {'no' if virtual else 'yes'})",
        f"\t\t(dnp {'yes' if dnp else 'no'})",
        f'\t\t(uuid "{sid}")',
        base.prop("Reference", ref, x, y - 4.0),
        base.prop("Value", value, x, y + 3.5),
        base.prop("Footprint", footprint, x, y, True),
        base.prop("Datasheet", "", x, y, True),
        base.prop("Description", "", x, y, True),
    ]
    for pin in pins:
        lines.extend(
            [
                f'\t\t(pin "{base.q(pin)}"',
                f'\t\t\t(uuid "{stable_uuid(f"symbol/{ref}/pin/{pin}")}")',
                "\t\t)",
            ]
        )
    lines.extend(
        [
            "\t\t(instances",
            f'\t\t\t(project "{PROJECT}"',
            f'\t\t\t\t(path "/{ROOT_SHEET_UUID}"',
            f'\t\t\t\t\t(reference "{ref}")',
            "\t\t\t\t\t(unit 1)",
            "\t\t\t\t)",
            "\t\t\t)",
            "\t\t)",
            "\t)",
        ]
    )
    return "\n".join(lines)


def connect_pin_to_label(
    lines: list[str], x: float, y: float, net: str, side: str
) -> None:
    label_x = x - 5.08 if side == "left" else x + 5.08
    rotation = 0 if side == "left" else 180
    justify = "left" if side == "left" else "right"
    lines.append(base.wire(x, y, label_x, y))
    lines.append(base.label(net, label_x, y, rotation, justify))


def _coordinate(value: float) -> str:
    rendered = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if rendered == "-0" else rendered


def _precise_wire(x1: float, y1: float, x2: float, y2: float) -> str:
    return (
        "\t(wire\n"
        "\t\t(pts\n"
        f"\t\t\t(xy {_coordinate(x1)} {_coordinate(y1)}) "
        f"(xy {_coordinate(x2)} {_coordinate(y2)})\n"
        "\t\t)\n"
        "\t\t(stroke (width 0) (type solid))\n"
        f'\t\t(uuid "{base.uid()}")\n'
        "\t)"
    )


def _precise_label(text: str, x: float, y: float, rotation: int, justify: str) -> str:
    return (
        f'\t(label "{base.q(text)}"\n'
        f"\t\t(at {_coordinate(x)} {_coordinate(y)} {rotation})\n"
        "\t\t(effects\n"
        "\t\t\t(font (size 0.9 0.9))\n"
        f"\t\t\t(justify {justify})\n"
        "\t\t)\n"
        f'\t\t(uuid "{base.uid()}")\n'
        "\t)"
    )


def _precise_no_connect(x: float, y: float) -> str:
    return (
        "\t(no_connect\n"
        f"\t\t(at {_coordinate(x)} {_coordinate(y)})\n"
        f'\t\t(uuid "{base.uid()}")\n'
        "\t)"
    )


def connect_exact_symbol_pins(
    lines: list[str],
    lib_id: str,
    x: float,
    y: float,
    pin_nets: dict[str, str | None],
) -> None:
    geometries = source_pin_geometries(lib_id)
    if set(geometries) != set(pin_nets):
        missing = sorted(set(pin_nets) - set(geometries))
        extra = sorted(set(geometries) - set(pin_nets))
        raise RuntimeError(
            f"{lib_id} source pin geometry mismatch: missing={missing}, extra={extra}"
        )
    outward = {
        0: (-5.08, 0.0, 0, "left"),
        90: (0.0, 5.08, 90, "left"),
        180: (5.08, 0.0, 180, "right"),
        270: (0.0, -5.08, 270, "right"),
    }
    for number, net in pin_nets.items():
        geometry = geometries[number]
        if geometry.rotation not in outward:
            raise RuntimeError(
                f"unsupported pin rotation {geometry.rotation} for {lib_id}.{number}"
            )
        pin_x = x + geometry.x
        pin_y = y - geometry.y
        if net is None:
            lines.append(_precise_no_connect(pin_x, pin_y))
            continue
        dx, dy, label_rotation, justify = outward[geometry.rotation]
        label_x = pin_x + dx
        label_y = pin_y + dy
        lines.append(_precise_wire(pin_x, pin_y, label_x, label_y))
        lines.append(_precise_label(net, label_x, label_y, label_rotation, justify))


def place_ic(
    lines: list[str],
    spec: SymbolSpec,
    ref: str,
    x: float,
    y: float,
    pin_nets: dict[str, str | None],
    *,
    dnp: bool = False,
) -> None:
    x = sheet_grid(x)
    y = sheet_grid(y)
    expected = {pin.number for pin in spec.pins}
    if set(pin_nets) != expected:
        missing = sorted(expected - set(pin_nets))
        extra = sorted(set(pin_nets) - expected)
        raise RuntimeError(f"{ref} pin map mismatch: missing={missing}, extra={extra}")
    lines.append(
        deterministic_symbol_instance(
            spec.lib_id,
            ref,
            spec.value,
            spec.footprint,
            x,
            y,
            [pin.number for pin in spec.pins],
            dnp,
        )
    )
    connect_exact_symbol_pins(lines, spec.lib_id, x, y, pin_nets)


def place_two_pin(lines: list[str], part: TwoPinPlacement, x: float, y: float) -> None:
    x = sheet_grid(x)
    y = sheet_grid(y)
    lines.append(
        deterministic_symbol_instance(
            part.lib_id,
            part.ref,
            part.value,
            part.footprint,
            x,
            y,
            ["1", "2"],
            part.dnp,
        )
    )
    connect_exact_symbol_pins(
        lines,
        part.lib_id,
        x,
        y,
        {"1": part.net1, "2": part.net2},
    )


def place_power_symbol(
    lines: list[str], ref: str, lib_id: str, value: str, net: str, x: float, y: float
) -> None:
    x = sheet_grid(x)
    y = sheet_grid(y)
    lines.append(deterministic_symbol_instance(lib_id, ref, value, "", x, y, ["1"]))
    connect_pin_to_label(lines, x, y, net, "left")


def _standard_symbol_specs() -> dict[str, SymbolSpec]:
    wroom_names = {
        "1": "GND",
        "2": "3V3",
        "3": "EN",
        "4": "IO4",
        "5": "IO5",
        "6": "IO6",
        "7": "IO7",
        "8": "IO15",
        "9": "IO16",
        "10": "IO17",
        "11": "IO18",
        "12": "IO8",
        "13": "USB_D-",
        "14": "USB_D+",
        "15": "IO3",
        "16": "IO46",
        "17": "IO9",
        "18": "IO10",
        "19": "IO11",
        "20": "IO12",
        "21": "IO13",
        "22": "IO14",
        "23": "IO21",
        "24": "IO47",
        "25": "IO48",
        "26": "IO45",
        "27": "IO0",
        "28": "IO35",
        "29": "IO36",
        "30": "IO37",
        "31": "IO38",
        "32": "IO39",
        "33": "IO40",
        "34": "IO41",
        "35": "IO42",
        "36": "RXD0",
        "37": "TXD0",
        "38": "IO2",
        "39": "IO1",
        "40": "GND",
        "41": "GND",
    }
    bq_names = {
        "1": "TS",
        "2": "BAT",
        "3": "BAT",
        "4": "~{CE}",
        "5": "EN2",
        "6": "EN1",
        "7": "~{PGOOD}",
        "8": "VSS",
        "9": "~{CHG}",
        "10": "OUT",
        "11": "OUT",
        "12": "ILIM",
        "13": "IN",
        "14": "TMR",
        "15": "ITERM",
        "16": "ISET",
        "17": "VSS",
    }
    stm_names = {
        "1": "Vcc",
        "2": "~{SR}",
        "3": "Vref",
        "4": "PS_HOLD",
        "5": "C_SRD",
        "6": "~{PB}",
        "7": "~{VCC}_LO",
        "8": "~{PB}_OUT",
        "9": "~{EN}/EN",
        "10": "~{RST}",
        "11": "~{INT}",
        "12": "GND",
    }
    usb_names = {
        "A1": "GND",
        "A4": "VBUS",
        "A5": "CC1",
        "A6": "D+",
        "A7": "D-",
        "A8": "SBU1",
        "A9": "VBUS",
        "A12": "GND",
        "B1": "GND",
        "B4": "VBUS",
        "B5": "CC2",
        "B6": "D+",
        "B7": "D-",
        "B8": "SBU2",
        "B9": "VBUS",
        "B12": "GND",
    }
    esd_names = {
        "1": "I/O1",
        "2": "GND",
        "3": "I/O2",
        "4": "I/O2",
        "5": "VBUS",
        "6": "I/O1",
    }
    battery_connector_names = {
        "1": "Pin_1",
        "2": "Pin_2",
        "3": "Pin_3",
    }
    return {
        "wroom": SymbolSpec(
            "RF_Module:ESP32-S3-WROOM-1",
            "ESP32-S3-WROOM-1-N16R8 / C2913202",
            "RF_Module:ESP32-S3-WROOM-1",
            "https://www.espressif.com/sites/default/files/documentation/"
            "esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf",
            "Pin map imported and asserted from KiCad 10 RF_Module library.",
            load_standard_pins("RF_Module.kicad_sym", "ESP32-S3-WROOM-1", wroom_names),
        ),
        "bq": SymbolSpec(
            "Battery_Management:BQ24074RGT",
            "BQ24074RGTR / C54313",
            "Package_DFN_QFN:VQFN-16-1EP_3x3mm_P0.5mm_EP1.6x1.6mm",
            "https://www.ti.com/lit/ds/symlink/bq24074.pdf",
            "USB-friendly charger and PowerPath; pin map asserted from KiCad 10.",
            load_standard_pins("Battery_Management.kicad_sym", "BQ24074RGT", bq_names),
        ),
        "stm": SymbolSpec(
            "Power_Management:STM6600",
            "STM6600CS25DM6F / C443976",
            "Package_DFN_QFN:TDFN-12_2x3mm_P0.5mm",
            "https://www.st.com/resource/en/datasheet/stm6600.pdf",
            "Smart push-button controller; CS25 polarity is recorded in notes.",
            load_standard_pins("Power_Management.kicad_sym", "STM6600", stm_names),
        ),
        "usb": SymbolSpec(
            "Connector:USB_C_Receptacle_USB2.0_16P",
            "TYPE-C-31-M-12 / C165948 CHARGE+USB",
            "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
            "https://www.usb.org/document-library/usb-type-cr-cable-and-connector-"
            "specification-release-24",
            "USB 2.0 Type-C sink; only VBUS, GND, CC1/2 and D+/D- are used.",
            load_standard_pins(
                "Connector.kicad_sym",
                "USB_C_Receptacle_USB2.0_16P",
                usb_names,
            ),
        ),
        "esd": SymbolSpec(
            "Power_Protection:USBLC6-2SC6",
            "USBLC6-2SC6 / C2827654",
            SOT23_6,
            "https://www.st.com/resource/en/datasheet/usblc6-2.pdf",
            "Exact KiCad USBLC6-2SC6 inherited symbol flattened with its SOT-23 identity and filter.",
            load_standard_pins("Power_Protection.kicad_sym", "USBLC6-2SC6", esd_names),
        ),
        "battery_connector": SymbolSpec(
            "Connector_Generic:Conn_01x03",
            "BAT+ BAT- 10kNTC / CONNECTOR+PACK HOLD",
            "Connector_JST:JST_PH_S3B-PH-K_1x03_P2.00mm_Horizontal",
            "",
            "Generic three-pin source-library symbol; exact battery and NTC contract is carried by instance properties.",
            load_standard_pins(
                "Connector_Generic.kicad_sym",
                "Conn_01x03",
                battery_connector_names,
            ),
        ),
    }


def _custom_symbol_specs() -> dict[str, SymbolSpec]:
    return {
        "tps63070": SymbolSpec(
            "B3_WROOM:TPS63070RNMR",
            "TPS63070RNMR / C109322",
            "B3_WROOM:TI_RNM0015A_VQFN-HR-15_2.5x3mm",
            "https://www.ti.com/lit/ds/symlink/tps63070.pdf",
            "RNM0015A pin map frozen from TI datasheet pages 38-40.",
            (
                PinSpec("1", "PS/SYNC", "input"),
                PinSpec("2", "PG", "open_collector", "right"),
                PinSpec("3", "VAUX", "power_out", "right"),
                PinSpec("4", "GND", "power_in"),
                PinSpec("5", "FB", "input"),
                PinSpec("6", "FB2", "output", "right"),
                PinSpec("7", "VOUT", "power_out", "right"),
                PinSpec("8", "VOUT", "passive", "right"),
                PinSpec("9", "L2", "passive", "right"),
                PinSpec("10", "PGND", "power_in"),
                PinSpec("11", "L1", "passive"),
                PinSpec("12", "VIN", "power_in"),
                PinSpec("13", "VIN", "power_in"),
                PinSpec("14", "EN", "input"),
                PinSpec("15", "VSEL", "input"),
            ),
        ),
        "tps22950": SymbolSpec(
            "B3_WROOM:TPS22950CQDDCRQ1",
            "TPS22950CQDDCRQ1 / C17349276",
            "B3_WROOM:TI_DDC0006A_SOT-23-6_2.9x1.6mm",
            "https://www.ti.com/lit/ds/symlink/tps22950-q1.pdf",
            "DDC0006A pin map frozen from TI datasheet pages 21-23.",
            (
                PinSpec("1", "ON", "input"),
                PinSpec("2", "VIN", "power_in"),
                PinSpec("3", "GND", "power_in"),
                PinSpec("4", "ILIM", "output", "right"),
                PinSpec("5", "VOUT", "power_out", "right"),
                PinSpec("6", "FLT", "open_collector", "right"),
            ),
        ),
        "bus_switch": SymbolSpec(
            "B3_WROOM:SN74CB3Q3245PWR",
            "SN74CB3Q3245PWR / C470961",
            TSSOP20,
            "https://www.ti.com/lit/ds/symlink/sn74cb3q3245.pdf",
            "PW0020A eight-bit Ioff bilateral bus switch; seven EPD lines plus one NC.",
            (
                PinSpec("1", "NC", "no_connect"),
                PinSpec("2", "A1", "bidirectional"),
                PinSpec("3", "A2", "bidirectional"),
                PinSpec("4", "A3", "bidirectional"),
                PinSpec("5", "A4", "bidirectional"),
                PinSpec("6", "A5", "bidirectional"),
                PinSpec("7", "A6", "bidirectional"),
                PinSpec("8", "A7", "bidirectional"),
                PinSpec("9", "A8", "bidirectional"),
                PinSpec("10", "GND", "power_in"),
                PinSpec("11", "B8", "bidirectional", "right"),
                PinSpec("12", "B7", "bidirectional", "right"),
                PinSpec("13", "B6", "bidirectional", "right"),
                PinSpec("14", "B5", "bidirectional", "right"),
                PinSpec("15", "B4", "bidirectional", "right"),
                PinSpec("16", "B3", "bidirectional", "right"),
                PinSpec("17", "B2", "bidirectional", "right"),
                PinSpec("18", "B1", "bidirectional", "right"),
                PinSpec("19", "~{OE}", "input", "right"),
                PinSpec("20", "VCC", "power_in", "right"),
            ),
        ),
        "sd": SymbolSpec(
            "Connector:Micro_SD_Card_Det2",
            "Molex 1040310811 / C585350",
            "Connector_Card:microSD_HC_Molex_104031-0811",
            "https://www.molex.com/en-us/products/part-detail/1040310811",
            "Exact standard Micro_SD_Card_Det2 pin model; Molex footprint and detector HOLD are instance contracts.",
            load_standard_pins(
                "Connector.kicad_sym",
                "Micro_SD_Card_Det2",
                {
                    "1": "DAT2",
                    "2": "DAT3/CD",
                    "3": "CMD",
                    "4": "VDD",
                    "5": "CLK",
                    "6": "VSS",
                    "7": "DAT0",
                    "8": "DAT1",
                    "9": "DET_B",
                    "10": "DET_A",
                    "SH": "SHIELD",
                },
            ),
        ),
    }


def all_symbol_specs() -> dict[str, SymbolSpec]:
    return {**_standard_symbol_specs(), **_custom_symbol_specs()}


def _rename_panel_supply(net: str | None) -> str | None:
    return "EPD_SW_3V3" if net == "3V3" else net


def panel_parts() -> list[base.Part2]:
    result: list[base.Part2] = []
    for part in a1.PARTS_2PIN:
        revised = replace(
            part,
            net1=_rename_panel_supply(part.net1),
            net2=_rename_panel_supply(part.net2),
        )
        if part.ref == "R4":
            revised = replace(
                revised,
                value="0R",
                note="FIT: TPS22950 EPD_SW_3V3 to proven panel EPD_3V3 branch",
            )
        elif part.ref == "R8":
            revised = replace(
                revised,
                value="0R",
                note="FIT: TPS22950 EPD_SW_3V3 to proven V_B branch",
            )
        elif part.ref == "R15":
            revised = replace(
                revised,
                value="0R DNP",
                note="DNP: independent CS configuration verified on real panel",
            )
        elif part.ref == "R16":
            revised = replace(
                revised,
                value="0R",
                note="FIT: CS2 to SL_CSB; real-panel verified configuration",
            )
        result.append(revised)
    return result


DEBUG_PINS: list[base.Pin] = [
    base.Pin(1, "J1-1 3V3 isolated", None),
    base.Pin(2, "J1-2 3V3 isolated", None),
    base.Pin(3, "J1-3 EN isolated", None),
    base.Pin(4, "J1-4 GPIO4 / MCU_BUSY_N", "MCU_BUSY_N"),
    base.Pin(5, "J1-5 GPIO5 / MCU_RST_N", "MCU_RST_N"),
    base.Pin(6, "J1-6 GPIO6 / MCU_DC", "MCU_DC"),
    base.Pin(7, "J1-7 GPIO7 / MCU_CSB", "MCU_CSB"),
    base.Pin(8, "J1-8 GPIO15", None),
    base.Pin(9, "J1-9 GPIO16", None),
    base.Pin(10, "J1-10 GPIO17", None),
    base.Pin(11, "J1-11 GPIO18", None),
    base.Pin(12, "J1-12 GPIO8", None),
    base.Pin(13, "J1-13 GPIO3 strap", None),
    base.Pin(14, "J1-14 GPIO46 strap", None),
    base.Pin(15, "J1-15 GPIO9", None),
    base.Pin(16, "J1-16 GPIO10 / MCU_CS2", "MCU_CS2"),
    base.Pin(17, "J1-17 GPIO11 / MCU_SI0", "MCU_SI0"),
    base.Pin(18, "J1-18 GPIO12 / MCU_SCL", "MCU_SCL"),
    base.Pin(19, "J1-19 GPIO13", None),
    base.Pin(20, "J1-20 GPIO14", None),
    base.Pin(21, "J1-21 5V isolated", None),
    base.Pin(22, "J1-22 GND", "GND"),
    base.Pin(23, "J3-22 GND", "GND"),
    base.Pin(24, "J3-21 GND", "GND"),
    base.Pin(25, "J3-20 USB_D-", None),
    base.Pin(26, "J3-19 USB_D+", None),
    base.Pin(27, "J3-18 GPIO21", None),
    base.Pin(28, "J3-17 GPIO47", None),
    base.Pin(29, "J3-16 GPIO48", None),
    base.Pin(30, "J3-15 GPIO45 strap", None),
    base.Pin(31, "J3-14 GPIO0", None),
    base.Pin(32, "J3-13 GPIO35 PSRAM", None),
    base.Pin(33, "J3-12 GPIO36 PSRAM", None),
    base.Pin(34, "J3-11 GPIO37 PSRAM", None),
    base.Pin(35, "J3-10 GPIO38", None),
    base.Pin(36, "J3-9 GPIO39", None),
    base.Pin(37, "J3-8 GPIO40", None),
    base.Pin(38, "J3-7 GPIO41", None),
    base.Pin(39, "J3-6 GPIO42", None),
    base.Pin(40, "J3-5 GPIO2", None),
    base.Pin(41, "J3-4 GPIO1", None),
    base.Pin(42, "J3-3 GPIO44/RX", None),
    base.Pin(43, "J3-2 GPIO43/TX", None),
    base.Pin(44, "J3-1 GND", "GND"),
]

BATTERY_PINS = [
    base.Pin(1, "BAT+", "BAT_POS"),
    base.Pin(2, "BAT-", "GND"),
    base.Pin(3, "10k NTC", "BAT_NTC"),
]


def _patch_base_helpers() -> None:
    base.PROJECT = PROJECT
    base.uid = UID_STREAM
    base.symbol_instance = deterministic_symbol_instance
    base.FPC_PINS = a1.FPC_PINS
    base.MCU_PINS = DEBUG_PINS
    base.FPC_FOOTPRINT_NAME = PANEL_FPC_FOOTPRINT
    base.MCU_FOOTPRINT_NAME = DEBUG_SOCKET_FOOTPRINT
    base.PARTS_2PIN = panel_parts()
    base.PARTS_3PIN = a1.PARTS_3PIN
    base.footprint_name_for_part2 = a1.footprint_name_for_part2
    base.footprint_name_for_part3 = a1.footprint_name_for_part3
    base.place_part3 = a1.place_part3


def _place_connector(
    lines: list[str],
    lib_id: str,
    ref: str,
    value: str,
    footprint: str,
    x: float,
    y: float,
    pins: list[base.Pin],
    left_count: int,
    *,
    dnp: bool = False,
) -> None:
    x = sheet_grid(x)
    y = sheet_grid(y)
    lines.append(
        deterministic_symbol_instance(
            lib_id,
            ref,
            value,
            footprint,
            x,
            y,
            [str(pin.number) for pin in pins],
            dnp,
        )
    )
    for index, pin in enumerate(pins):
        if index < left_count:
            py = y - (left_count - 1 - index) * 2.54
            px = x - 15.24
            side = "left"
        else:
            py = y - (len(pins) - index - 1) * 2.54
            px = x + 15.24
            side = "right"
        if pin.net is None:
            lines.append(base.no_connect(px, py))
        else:
            connect_pin_to_label(lines, px, py, pin.net, side)


def _place_panel(lines: list[str]) -> None:
    parts = {part.ref: part for part in panel_parts()}
    part3 = {part.ref: part for part in a1.PARTS_3PIN}
    groups = [
        ("DNP debug socket / MCU-side nets", 25, 25, 112, 112, (50, 95, 170)),
        (
            "EPD_SW_3V3 distribution, pullups, and 4-wire mode",
            122,
            25,
            318,
            118,
            (70, 120, 80),
        ),
        (
            "Preserved B2 HV boost and negative gate pump",
            25,
            126,
            264,
            226,
            (180, 90, 35),
        ),
        ("Preserved B2 VPC positive pump", 25, 236, 264, 300, (180, 90, 35)),
        ("Preserved B2 panel FPC and signals", 338, 25, 542, 118, (50, 95, 170)),
        (
            "Preserved B2 panel capacitors and references",
            276,
            126,
            542,
            300,
            (120, 90, 150),
        ),
        ("Preserved B2 bring-up test points", 25, 312, 542, 387, (95, 95, 95)),
    ]
    for title, x1, y1, x2, y2, color in groups:
        lines.append(base.graphic_rect(x1, y1, x2, y2, color))
        lines.append(base.text_note(title, x1 + 3, y1 + 5, 1.05))

    _place_connector(
        lines,
        "Local:MF1750_FPC50",
        "J1",
        "MF-1750 50pin FPC",
        PANEL_FPC_FOOTPRINT,
        460.0,
        80.0,
        a1.FPC_PINS,
        25,
    )
    _place_connector(
        lines,
        "Local:ESP32_SPI_10PIN",
        "J2",
        "DEVKITC DEBUG SOCKET - DNP WITH U1",
        DEBUG_SOCKET_FOOTPRINT,
        70.0,
        60.0,
        DEBUG_PINS,
        22,
        dnp=True,
    )

    power_positions = {
        "R4": (145, 45),
        "R8": (145, 58),
        "R6": (195, 45),
        "R7": (195, 58),
        "C3": (195, 72),
        "C23": (145, 72),
        "R9": (145, 91),
        "R10": (195, 91),
        "R12": (250, 58),
        "R13": (292, 58),
        "R15": (250, 91),
        "R16": (292, 91),
    }
    for ref, pos in power_positions.items():
        base.place_part2(lines, parts[ref], *pos)
    lines.append(
        base.text_note(
            "R15 DNP / R16 FIT remains the real-panel-verified independent-CS population.",
            126,
            114,
            0.85,
        )
    )

    hv_positions = {
        "C0": (45, 148),
        "L1": (85, 148),
        "D1": (126, 148),
        "C2": (168, 148),
        "R5": (215, 148),
        "C4": (85, 169),
        "D2": (126, 169),
        "D3": (168, 169),
        "C5": (215, 169),
        "Q1": (85, 200),
        "R1": (168, 200),
    }
    for ref in ("C0", "L1", "D1", "C2", "R5", "C4", "D2", "D3", "C5", "R1"):
        base.place_part2(lines, parts[ref], *hv_positions[ref])
    base.place_part3(lines, part3["Q1"], *hv_positions["Q1"])

    vpc_positions = {
        "C22": (45, 256),
        "Q2": (85, 274),
        "L2": (132, 274),
        "D4": (176, 274),
        "C6": (220, 274),
        "R3": (132, 291),
    }
    for ref in ("C22", "L2", "D4", "C6", "R3"):
        base.place_part2(lines, parts[ref], *vpc_positions[ref])
    base.place_part3(lines, part3["Q2"], *vpc_positions["Q2"])

    cap_positions = {
        "C13": (300, 148),
        "C14": (365, 148),
        "R2": (430, 148),
        "C7": (300, 173),
        "C8": (365, 173),
        "C9": (430, 173),
        "C10": (495, 173),
        "C11": (300, 198),
        "C12": (365, 198),
        "C21": (430, 198),
        "C20": (495, 198),
        "C1": (300, 223),
        "C19": (365, 223),
        "C18": (430, 223),
        "C17": (495, 223),
        "C16": (365, 248),
        "C15": (430, 248),
    }
    for ref, pos in cap_positions.items():
        base.place_part2(lines, parts[ref], *pos)

    panel_test_nets = [
        "EPD_SW_3V3",
        "GND",
        "VPH",
        "PREVGH",
        "PREVGL",
        "VPC",
        "VDDIO",
        "CSB",
        "SL_CSB",
        "BUSY_N",
    ]
    for index, net in enumerate(panel_test_nets, start=1):
        x = sheet_grid(45 + ((index - 1) % 9) * 55)
        y = sheet_grid(330 + ((index - 1) // 9) * 18)
        ref = f"TP{index}"
        lines.append(
            deterministic_symbol_instance("Local:TP", ref, net, TESTPOINT, x, y, ["1"])
        )
        connect_pin_to_label(lines, x - 5.08, y, net, "left")


def _wroom_pin_nets(spec: SymbolSpec) -> dict[str, str | None]:
    mapping: dict[str, str | None] = {pin.number: None for pin in spec.pins}
    mapping.update(
        {
            "1": "GND",
            "2": "SYS_3V3",
            "3": "MCU_EN",
            "4": "MCU_BUSY_N",
            "5": "MCU_RST_N",
            "6": "MCU_DC",
            "7": "MCU_CSB",
            "8": "TF_SCLK",
            "9": "TF_MOSI",
            "10": "TF_MISO",
            "11": "TF_CS_N",
            "12": "USER_KEY_1_N",
            "13": "USB_D-",
            "14": "USB_D+",
            "17": "USER_KEY_2_N",
            "18": "MCU_CS2",
            "19": "MCU_SI0",
            "20": "MCU_SCL",
            "21": "EPD_PWR_EN",
            "22": "TF_CD_N",
            "23": "PWR_INT_N",
            "24": "USB_INPUT_VALID_N",
            "25": "EPD_FAULT_N",
            "27": "BOOT_N",
            "31": "EPD_BUF_CONNECT",
            "32": "JTAG_GPIO39",
            "33": "JTAG_GPIO40",
            "34": "JTAG_GPIO41",
            "35": "JTAG_GPIO42",
            "36": "UART0_RX",
            "37": "UART0_TX",
            "38": "PS_HOLD",
            "39": "BAT_ADC",
            "40": "GND",
            "41": "GND",
        }
    )
    return mapping


def _new_two_pin_parts() -> list[TwoPinPlacement]:
    p = TwoPinPlacement
    return [
        p(
            "F1",
            "750mA PTC / C883128",
            "USB_VBUS",
            "USB_5V_FUSED",
            PTC_1206_SYMBOL,
            R_1206,
        ),
        p(
            "D5",
            "SMF5.0A / C908213",
            "USB_5V_FUSED",
            "GND",
            "Local:D_SCH",
            "Diode_SMD:D_SOD-123",
        ),
        p(
            "L3",
            "1.5uH >=4.5A LOW-DCR / MAGNETICS HOLD",
            "DCDC_L1",
            "DCDC_L2",
            "Local:L",
            "B3_WROOM:Coilcraft_XFL4020_4x4mm",
        ),
        p("R17", "5.1k 1% CC1 Rd", "USB_CC1", "GND"),
        p("R18", "5.1k 1% CC2 Rd", "USB_CC2", "GND"),
        p("R19", "22R USB D-", "USB_DN_ESD", "USB_D-"),
        p("R20", "22R USB D+", "USB_DP_ESD", "USB_D+"),
        p("R21", "1.78k 1% BQ ISET ~500mA", "BQ_ISET", "GND"),
        p("R22", "3.16k 1% BQ ILIM", "BQ_ILIM", "GND"),
        p("R24", "46.4k 1% BQ TMR ~6.25h", "BQ_TMR", "GND"),
        p("R25", "100k BQ PGOOD pullup", "SYS_3V3", "USB_INPUT_VALID_N"),
        p("R26", "100k BQ CHG pullup", "SYS_3V3", "BQ_CHG_N"),
        p("R27", "10k MCU EN pullup", "SYS_3V3", "MCU_EN"),
        p("R28", "10k STM INT pullup", "SYS_3V3", "PWR_INT_N"),
        p("R29", "10k TPS63070 PS/SYNC VIN series", "VSYS_RAW", "DCDC_PS_SYNC"),
        p("R30", "100k DCDC PG pullup", "SYS_3V3", "DCDC_PG"),
        p("R31", "470k 1% FB top", "SYS_3V3", "DCDC_FB"),
        p("R32", "150k 1% FB bottom", "DCDC_FB", "GND"),
        p("R33", "1.50k 1% TPS22950 ILIM", "EPD_ILIM", "GND"),
        p("R34", "10k EPD FLT pullup", "SYS_3V3", "EPD_FAULT_N"),
        p("R35", "100k EPD ON hardware pulldown", "EPD_PWR_EN", "GND"),
        p("R36", "10k U6 OE_N pullup", "EPD_3V3", "EPD_BUF_OE_N"),
        p("R39", "10k TF DAT2 pullup", "SYS_3V3", "TF_DAT2_CARD"),
        p("R40", "10k TF DAT3/CS pullup", "SYS_3V3", "TF_DAT3_CARD"),
        p("R41", "10k TF CMD/MOSI pullup", "SYS_3V3", "TF_CMD_CARD"),
        p("R42", "10k TF DAT0/MISO pullup", "SYS_3V3", "TF_DAT0_CARD"),
        p("R43", "10k TF DAT1 pullup", "SYS_3V3", "TF_DAT1_CARD"),
        p("R44", "10k TF CD pullup", "SYS_3V3", "TF_CD_N"),
        p("R45", "22R TF SCLK", "TF_SCLK", "TF_CLK_ESD"),
        p("R46", "22R TF MOSI", "TF_MOSI", "TF_CMD_ESD"),
        p("R47", "22R TF MISO", "TF_MISO", "TF_DAT0_ESD"),
        p("R48", "22R TF CS", "TF_CS_N", "TF_DAT3_ESD"),
        p(
            "R49",
            "220k/1% BAT ADC top - DNP OPTIONAL",
            "BAT_POS",
            "BAT_ADC",
            dnp=True,
        ),
        p("R50", "100k/1% BAT ADC bottom", "BAT_ADC", "GND"),
        p("R51", "10k USER1 pullup", "SYS_3V3", "USER_KEY_1_N"),
        p("R52", "10k USER2 pullup", "SYS_3V3", "USER_KEY_2_N"),
        p("R53", "10k BOOT pullup", "SYS_3V3", "BOOT_N"),
        p("R54", "100k CSB panel-safe pullup", "EPD_3V3", "CSB"),
        p("R55", "100k CS2 panel-safe pullup", "EPD_3V3", "CS2"),
        p("R56", "100k RST_N panel-safe pulldown", "RST_N", "GND"),
        p("R57", "100k DC panel-safe pulldown", "DC", "GND"),
        p("R58", "100k SCL panel-safe pulldown", "SCL", "GND"),
        p("R59", "100k SI0 panel-safe pulldown", "SI0", "GND"),
        p("R60", "100k PS_HOLD startup pulldown", "PS_HOLD", "GND"),
        p("R61", "100k DCDC EN startup pulldown", "DCDC_EN", "GND"),
        p("R62", "100k BUSY idle-high MCU pullup", "SYS_3V3", "MCU_BUSY_N"),
        p("R63", "100k U6-connect gate pulldown", "EPD_BUF_CONNECT", "GND"),
        p("R64", "0R USB shield bond - FIT", "USB_SHIELD", "GND"),
        p(
            "R65",
            "1M USB shield EMC option - DNP",
            "USB_SHIELD",
            "GND",
            dnp=True,
        ),
        p("C24", "1uF USB fused input", "USB_5V_FUSED", "GND", "Local:C", C_0805),
        p("C25", "1uF BQ IN", "USB_5V_FUSED", "GND", "Local:C", C_0805),
        p("C26", "10uF BQ BAT", "BAT_POS", "GND", "Local:C", C_0805),
        p("C27", "10uF BQ OUT", "VSYS_RAW", "GND", "Local:C", C_0805),
        p("C28", "0.1uF STM VCC", "VSYS_RAW", "GND", "Local:C", C_0603),
        p("C29", "1uF STM VREF", "STM_VREF", "GND", "Local:C", C_0805),
        p("C30", "1uF STM CSRD ~10s", "STM_CSRD", "GND", "Local:C", C_0805),
        p("C31", "10uF DCDC VIN 1", "VSYS_RAW", "GND", "Local:C", C_0805),
        p("C32", "10uF DCDC VIN 2", "VSYS_RAW", "GND", "Local:C", C_0805),
        p("C33", "10uF DCDC VIN 3", "VSYS_RAW", "GND", "Local:C", C_0805),
        p("C34", "22uF DCDC VOUT 1", "SYS_3V3", "GND", "Local:C", C_1206),
        p("C35", "22uF DCDC VOUT 2", "SYS_3V3", "GND", "Local:C", C_1206),
        p("C36", "22uF DCDC VOUT 3", "SYS_3V3", "GND", "Local:C", C_1206),
        p("C37", "10uF DCDC VOUT", "SYS_3V3", "GND", "Local:C", C_0805),
        p("C38", "0.1uF DCDC VAUX", "DCDC_VAUX", "GND", "Local:C", C_0603),
        p("C39", "1uF TPS22950 VIN", "SYS_3V3", "GND", "Local:C", C_0805),
        p("C40", "10uF EPD switched rail", "EPD_SW_3V3", "GND", "Local:C", C_0805),
        p("C41", "10uF WROOM bulk", "SYS_3V3", "GND", "Local:C", C_0805),
        p("C42", "0.1uF WROOM local", "SYS_3V3", "GND", "Local:C", C_0603),
        p("C43", "0.1uF TF", "SYS_3V3", "GND", "Local:C", C_0603),
        p("C44", "10uF TF", "SYS_3V3", "GND", "Local:C", C_0805),
        p("C45", "0.1uF U6", "EPD_3V3", "GND", "Local:C", C_0603),
        p(
            "C46",
            "10uF DCDC VIN local HF / TI 11.1",
            "VSYS_RAW",
            "GND",
            "Local:C",
            C_0603,
        ),
        p(
            "C47",
            "10uF DCDC VOUT local HF / TI 11.1",
            "SYS_3V3",
            "GND",
            "Local:C",
            C_0603,
        ),
        p("C48", "0.1uF MCU EN", "MCU_EN", "GND", "Local:C", C_0603),
        p("C49", "0.1uF BAT ADC", "BAT_ADC", "GND", "Local:C", C_0603),
        p(
            "C50",
            "1nF USB shield EMC option - DNP",
            "USB_SHIELD",
            "GND",
            "Local:C",
            C_0603,
            True,
        ),
        p(
            "SW1",
            "POWER / SKSCLDE010",
            "PWR_BUTTON_N",
            "GND",
            "Switch:SW_Push",
            "B3_WROOM:ALPS_SKSCLDE010_SidePush",
        ),
        p(
            "SW2",
            "USER1 / SKSCLDE010",
            "USER_KEY_1_N",
            "GND",
            "Switch:SW_Push",
            "B3_WROOM:ALPS_SKSCLDE010_SidePush",
        ),
        p(
            "SW3",
            "USER2 / SKSCLDE010",
            "USER_KEY_2_N",
            "GND",
            "Switch:SW_Push",
            "B3_WROOM:ALPS_SKSCLDE010_SidePush",
        ),
        p(
            "SW4",
            "BOOT SERVICE / SKSCLDE010",
            "BOOT_N",
            "GND",
            "Switch:SW_Push",
            "B3_WROOM:ALPS_SKSCLDE010_SidePush",
        ),
        p(
            "SW5",
            "RESET SERVICE / SKSCLDE010",
            "MCU_EN",
            "GND",
            "Switch:SW_Push",
            "B3_WROOM:ALPS_SKSCLDE010_SidePush",
        ),
    ]


def _place_b3_expansion(lines: list[str], specs: dict[str, SymbolSpec]) -> None:
    groups = [
        ("USB-C / ESD / BQ24074 PowerPath", 565, 25, 825, 285, (45, 105, 160)),
        ("STM6600 / TPS63070 / TPS22950 power tree", 835, 25, 1160, 285, (80, 125, 70)),
        ("B3 passives and hardware-safe defaults", 565, 295, 1160, 455, (105, 90, 125)),
        ("ESP32-S3-WROOM-1-N16R8 and service I/O", 25, 410, 365, 790, (45, 105, 160)),
        (
            "EPD guarded interface; SI0 remains bidirectional",
            375,
            410,
            745,
            790,
            (150, 80, 35),
        ),
        (
            "microSD SPI, card-side pullups, and six-line ESD",
            755,
            410,
            1160,
            790,
            (110, 85, 145),
        ),
    ]
    for title, x1, y1, x2, y2, color in groups:
        lines.append(base.graphic_rect(x1, y1, x2, y2, color))
        lines.append(base.text_note(title, x1 + 3, y1 + 5, 1.05))

    place_ic(
        lines,
        specs["usb"],
        "J5",
        625,
        100,
        {
            "A1": "GND",
            "A4": "USB_VBUS",
            "A5": "USB_CC1",
            "A6": "USB_DP_CONN",
            "A7": "USB_DN_CONN",
            "A8": None,
            "A9": "USB_VBUS",
            "A12": "GND",
            "B1": "GND",
            "B4": "USB_VBUS",
            "B5": "USB_CC2",
            "B6": "USB_DP_CONN",
            "B7": "USB_DN_CONN",
            "B8": None,
            "B9": "USB_VBUS",
            "B12": "GND",
            "SH": "USB_SHIELD",
        },
    )
    place_ic(
        lines,
        specs["esd"],
        "U8",
        625,
        225,
        {
            "1": "USB_DN_CONN",
            "2": "GND",
            "3": "USB_DP_CONN",
            "4": "USB_DP_ESD",
            "5": "USB_5V_FUSED",
            "6": "USB_DN_ESD",
        },
    )
    place_ic(
        lines,
        specs["bq"],
        "U2",
        755,
        110,
        {
            "1": "BAT_NTC",
            "2": "BAT_POS",
            "3": "BAT_POS",
            "4": "GND",
            "5": "GND",
            "6": "USB_5V_FUSED",
            "7": "USB_INPUT_VALID_N",
            "8": "GND",
            "9": "BQ_CHG_N",
            "10": "VSYS_RAW",
            "11": "VSYS_RAW",
            "12": "BQ_ILIM",
            "13": "USB_5V_FUSED",
            "14": "BQ_TMR",
            "15": None,
            "16": "BQ_ISET",
            "17": "GND",
        },
    )
    place_ic(
        lines,
        specs["battery_connector"],
        "J6",
        755,
        245,
        {"1": "BAT_POS", "2": "GND", "3": "BAT_NTC"},
    )
    place_ic(
        lines,
        specs["stm"],
        "U3",
        900,
        105,
        {
            "1": "VSYS_RAW",
            "2": "PWR_BUTTON_N",
            "3": "STM_VREF",
            "4": "PS_HOLD",
            "5": "STM_CSRD",
            "6": "PWR_BUTTON_N",
            "7": None,
            "8": None,
            "9": "DCDC_EN",
            "10": "MCU_EN",
            "11": "PWR_INT_N",
            "12": "GND",
        },
    )
    place_ic(
        lines,
        specs["tps63070"],
        "U4",
        1040,
        105,
        {
            "1": "DCDC_PS_SYNC",
            "2": "DCDC_PG",
            "3": "DCDC_VAUX",
            "4": "GND",
            "5": "DCDC_FB",
            "6": None,
            "7": "SYS_3V3",
            "8": "SYS_3V3",
            "9": "DCDC_L2",
            "10": "GND",
            "11": "DCDC_L1",
            "12": "VSYS_RAW",
            "13": "VSYS_RAW",
            "14": "DCDC_EN",
            "15": "GND",
        },
    )
    place_ic(
        lines,
        specs["tps22950"],
        "U5",
        1040,
        235,
        {
            "1": "EPD_PWR_EN",
            "2": "SYS_3V3",
            "3": "GND",
            "4": "EPD_ILIM",
            "5": "EPD_SW_3V3",
            "6": "EPD_FAULT_N",
        },
    )
    for ref, x, net in (
        ("#FLG01", 610, "USB_5V_FUSED"),
        ("#FLG02", 680, "EPD_3V3"),
        ("#FLG03", 750, "GND"),
    ):
        place_power_symbol(lines, ref, "power:PWR_FLAG", "PWR_FLAG", net, x, 270)
    place_power_symbol(lines, "#PWR01", "power:GND", "GND", "GND", 820, 270)

    new_parts = _new_two_pin_parts()
    for index, part in enumerate(new_parts):
        x = 590 + (index % 9) * 62
        y = 315 + (index // 9) * 16
        place_two_pin(lines, part, x, y)

    place_ic(lines, specs["wroom"], "U1", 190, 600, _wroom_pin_nets(specs["wroom"]))
    place_ic(
        lines,
        specs["bus_switch"],
        "U6",
        560,
        610,
        {
            "1": None,
            "2": "MCU_RST_N",
            "3": "MCU_DC",
            "4": "MCU_CSB",
            "5": "MCU_CS2",
            "6": "MCU_SCL",
            "7": "MCU_SI0",
            "8": "MCU_BUSY_N",
            "9": None,
            "10": "GND",
            "11": None,
            "12": "BUSY_N",
            "13": "SI0",
            "14": "SCL",
            "15": "CS2",
            "16": "CSB",
            "17": "DC",
            "18": "RST_N",
            "19": "EPD_BUF_OE_N",
            "20": "EPD_3V3",
        },
    )
    base.place_part3(
        lines,
        base.Part3(
            "Q3",
            "NMOS",
            "2N7002 / C8545",
            (
                ("1", "G", "EPD_BUF_CONNECT"),
                ("2", "S", "GND"),
                ("3", "D", "EPD_BUF_OE_N"),
            ),
            footprint="Package_TO_SOT_SMD:SOT-23-3",
            note=(
                "SYS_3V3-domain GPIO38 isolation: high connects U6; reset/low "
                "lets R36 isolate."
            ),
        ),
        700,
        610,
    )
    lines.append(
        base.text_note(
            "U6 is an Ioff bilateral switch and preserves SI0 readback. Q3 isolates "
            "GPIO38 from EPD_3V3: GPIO38 high connects; reset/low isolates through R36.",
            395,
            775,
            0.9,
        )
    )

    place_ic(
        lines,
        specs["sd"],
        "J4",
        835,
        600,
        {
            "1": "TF_DAT2_CARD",
            "2": "TF_DAT3_CARD",
            "3": "TF_CMD_CARD",
            "4": "SYS_3V3",
            "5": "TF_CLK_CARD",
            "6": "GND",
            "7": "TF_DAT0_CARD",
            "8": "TF_DAT1_CARD",
            "9": "TF_CD_N",
            "10": "GND",
            "SH": "GND",
        },
    )
    for ref, y, nets in (
        (
            "U9",
            500,
            {
                "1": "TF_CLK_CARD",
                "2": "GND",
                "3": "TF_CMD_CARD",
                "4": "TF_CMD_ESD",
                "5": "SYS_3V3",
                "6": "TF_CLK_ESD",
            },
        ),
        (
            "U10",
            605,
            {
                "1": "TF_DAT0_CARD",
                "2": "GND",
                "3": "TF_DAT3_CARD",
                "4": "TF_DAT3_ESD",
                "5": "SYS_3V3",
                "6": "TF_DAT0_ESD",
            },
        ),
        (
            "U11",
            710,
            {
                "1": "TF_DAT1_CARD",
                "2": "GND",
                "3": "TF_DAT2_CARD",
                "4": None,
                "5": "SYS_3V3",
                "6": None,
            },
        ),
    ):
        place_ic(lines, specs["esd"], ref, 1030, y, nets)

    test_nets = [
        "USB_5V_FUSED",
        "BAT_POS",
        "VSYS_RAW",
        "SYS_3V3",
        "DCDC_EN",
        "DCDC_PG",
        "EPD_SW_3V3",
        "EPD_3V3",
        "EPD_FAULT_N",
        "MCU_SI0",
        "SI0",
        "TF_SCLK",
        "TF_MOSI",
        "TF_MISO",
        "TF_CS_N",
        "USB_D-",
        "USB_D+",
        "UART0_TX",
        "UART0_RX",
        "JTAG_GPIO39",
        "JTAG_GPIO40",
        "JTAG_GPIO41",
        "JTAG_GPIO42",
    ]
    for index, net in enumerate(test_nets, start=11):
        x = sheet_grid(35 + ((index - 11) % 12) * 92)
        y = sheet_grid(812 + ((index - 11) // 12) * 13)
        ref = f"TP{index}"
        lines.append(
            deterministic_symbol_instance("Local:TP", ref, net, TESTPOINT, x, y, ["1"])
        )
        connect_pin_to_label(lines, x - 5.08, y, net, "left")


def make_schematic() -> str:
    assert_frozen_b2()
    assert_b3_custom_libraries()
    if not KICAD_CLI.is_file():
        raise RuntimeError(f"KiCad 10 CLI missing: {KICAD_CLI}")
    UID_STREAM.reset()
    PLACED_REFS.clear()
    _patch_base_helpers()
    specs = all_symbol_specs()

    local_defs = [
        base.symbol_lib_connector("MF1750_FPC50", a1.FPC_PINS, 25, PANEL_FPC_FOOTPRINT),
        base.symbol_lib_connector(
            "ESP32_SPI_10PIN", DEBUG_PINS, 22, DEBUG_SOCKET_FOOTPRINT
        ),
        base.symbol_lib_two_pin("R", "R", R_0603),
        base.symbol_lib_two_pin("C", "C", C_0603),
        exact_symbol_definition("Local:L"),
        base.symbol_lib_two_pin("D_SCH", "D", "Diode_SMD:D_SOD-123", "K", "A"),
        exact_symbol_definition(PTC_1206_SYMBOL),
        exact_symbol_definition("Switch:SW_Push"),
        a1.fet_symbol("NMOS", a1.SC70_FOOTPRINT_NAME),
        a1.fet_symbol("PMOS", a1.SOT23_FOOTPRINT_NAME),
        base.symbol_lib_testpoint(),
        standard_power_symbol_definition("GND"),
        standard_power_symbol_definition("PWR_FLAG"),
        *(
            symbol_definition_with_pin_type_overrides(
                spec.lib_id, {"8": ("power_out", "passive")}
            )
            if name == "tps63070"
            else flattened_inherited_symbol_definition(spec.lib_id)
            if name == "esd"
            else exact_symbol_definition(spec.lib_id)
            for name, spec in specs.items()
        ),
    ]
    lines: list[str] = [
        "(kicad_sch",
        "\t(version 20250114)",
        '\t(generator "eeschema")',
        '\t(generator_version "10.0")',
        f'\t(uuid "{ROOT_SHEET_UUID}")',
        '\t(paper "A0")',
        "\t(title_block",
        f'\t\t(title "MF1750 WROOM B3 — {REVISION}")',
        '\t\t(company "B2 panel preserved; WROOM power/USB/TF staging candidate")',
        '\t\t(comment 1 "DRAFT / HOLD — NOT PCB PARITY — NOT MANUFACTURING RELEASE")',
        "\t)",
        "\t(lib_symbols",
        *local_defs,
        "\t)",
    ]
    _place_panel(lines)
    _place_b3_expansion(lines, specs)
    notes = [
        "B2 frozen source hashes are asserted before generation; source files are never rewritten.",
        "Former B2 3V3 semantics are EPD_SW_3V3; R4/R8 preserve the proven downstream EPD_3V3/V_B distribution.",
        "J2 is DNP debug only and uses MCU-side nets. Never populate J2 with U1 or drive panel nets around the buffers.",
        "Panel-side defaults: CSB/CS2 pull high to EPD_3V3; RST/DC/SCL/SI0 pull low. MCU_BUSY_N pulls high.",
        "Power defaults: EPD ON and EPD_BUF_CONNECT pull low; R36 pulls U6 OE_N high to EPD_3V3.",
        "Enable order: GPIO38 low -> enable TPS22950 -> wait for EPD rail -> GPIO38 high. Disable in reverse.",
        "U6 SN74CB3Q3245PWR preserves SI0 bidirectional readback and provides Ioff isolation when EPD_3V3 is absent.",
        "TPS63070 Rev.B 11.1: R29 is 10k to VIN; C46 VIN-GND and C47 VOUT-GND are 10uF 0603 local HF capacitors; C31-C37 remain bulk.",
        "STM6600CS25 minimum start blanking/press behaviour and all listed engineering HOLD items remain release blockers.",
    ]
    for index, note in enumerate(notes):
        lines.append(base.text_note(note, 30, 396 + index * 4.5, 0.85))
    lines.extend(["\t(sheet_instances", '\t\t(path "/" (page "1"))', "\t)", ")"])
    return "\n".join(lines) + "\n"


def assert_deterministic() -> str:
    first = make_schematic()
    second = make_schematic()
    if first != second:
        raise RuntimeError("deterministic UUID/content check failed")
    return first


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
    )


def _erc_violation_counts(report: str) -> dict[str, int]:
    counts = Counter(re.findall(r"^\[([a-z0-9_]+)\]:", report, re.MULTILINE))
    return dict(sorted(counts.items()))


def _erc_violations(report: str) -> tuple[tuple[str, str, str], ...]:
    """Return ``(category, reference, description)`` for every ERC block.

    KiCad localizes the human-readable prose, so promotion is gated on the
    stable violation category plus the exact symbol reference.  The emitted
    description is nevertheless preserved verbatim in the manifest for
    review.  Multi-symbol or reference-free blocks can never match the narrow
    library-warning fingerprints below and therefore fail closed.
    """

    violations: list[tuple[str, str, str]] = []
    block_pattern = re.compile(
        r"^\[([a-z0-9_]+)\]:[ \t]*(.*?)(?=^\[[a-z0-9_]+\]:|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    reference_pattern = re.compile(r"\bSymbol\s+([^\s\[]+)\s+\[")
    for match in block_pattern.finditer(report):
        code = match.group(1)
        body = match.group(2)
        description = body.splitlines()[0].strip() if body else ""
        references = tuple(dict.fromkeys(reference_pattern.findall(body)))
        reference = references[0] if len(references) == 1 else ",".join(references)
        violations.append((code, reference, description))
    return tuple(violations)


def _partition_warning_inventory(
    report: str,
) -> tuple[
    tuple[tuple[str, str, str], ...],
    tuple[tuple[str, str, str], ...],
]:
    warnings = _erc_violations(report)
    fingerprints = Counter((code, reference) for code, reference, _ in warnings)
    allowed: list[tuple[str, str, str]] = []
    blocking: list[tuple[str, str, str]] = []
    for warning in warnings:
        code, reference, _ = warning
        expected_references = EXPECTED_ERC_LIBRARY_WARNING_REFS.get(code, frozenset())
        if reference in expected_references and fingerprints[(code, reference)] == 1:
            allowed.append(warning)
        else:
            blocking.append(warning)
    return tuple(allowed), tuple(blocking)


def _prepare_validation_bundle(path: Path, temp_dir: Path) -> Path:
    """Copy the candidate and its project-local libraries into a temp project."""

    candidate = temp_dir / f"{PROJECT}.kicad_sch"
    shutil.copy2(path, candidate)
    for filename in (
        f"{PROJECT}.kicad_pro",
        "sym-lib-table",
        "fp-lib-table",
        "mf1750_local.kicad_sym",
        "b3_wroom_symbols.kicad_sym",
    ):
        source = B3_DIR / filename
        if not source.is_file():
            raise RuntimeError(f"validation bundle input missing: {source}")
        shutil.copy2(source, temp_dir / filename)
    for dirname in (
        "MF1750_Compact.pretty",
        "MF1750_Production.pretty",
        "b3_wroom_footprints.pretty",
    ):
        source = B3_DIR / dirname
        if not source.is_dir():
            raise RuntimeError(f"validation footprint library missing: {source}")
        shutil.copytree(source, temp_dir / dirname)
    return candidate


def validate_schematic(path: Path) -> ValidationResult:
    version = _run([str(KICAD_CLI), "--version"], cwd=path.parent)
    if version.returncode != 0:
        raise RuntimeError(f"KiCad version probe failed: {version.stderr}")
    with tempfile.TemporaryDirectory(prefix="mf1750-b3-sch-verify-") as temp_name:
        temp_dir = Path(temp_name)
        candidate = _prepare_validation_bundle(path, temp_dir)
        netlist = temp_dir / "candidate.xml"
        error_report = temp_dir / "erc-errors.rpt"
        warning_report = temp_dir / "erc-warnings.rpt"
        parse = _run(
            [
                str(KICAD_CLI),
                "sch",
                "export",
                "netlist",
                "--output",
                str(netlist),
                str(candidate),
            ],
            cwd=temp_dir,
        )
        error_erc = _run(
            [
                str(KICAD_CLI),
                "sch",
                "erc",
                "--exit-code-violations",
                "--severity-error",
                "--output",
                str(error_report),
                str(candidate),
            ],
            cwd=temp_dir,
        )
        warning_erc = _run(
            [
                str(KICAD_CLI),
                "sch",
                "erc",
                "--severity-warning",
                "--output",
                str(warning_report),
                str(candidate),
            ],
            cwd=temp_dir,
        )
        error_text = (
            error_report.read_text(encoding="utf-8", errors="replace")
            if error_report.is_file()
            else error_erc.stdout + error_erc.stderr
        )
        warning_text = (
            warning_report.read_text(encoding="utf-8", errors="replace")
            if warning_report.is_file()
            else warning_erc.stdout + warning_erc.stderr
        )
        error_counts = _erc_violation_counts(error_text)
        allowed_warnings, blocking_warnings = _partition_warning_inventory(warning_text)
        allowed_warning_counts = dict(
            sorted(Counter(code for code, _, _ in allowed_warnings).items())
        )
        blocking_warning_counts = dict(
            sorted(Counter(code for code, _, _ in blocking_warnings).items())
        )
        return ValidationResult(
            kicad_version=version.stdout.strip(),
            parse_returncode=parse.returncode,
            error_erc_returncode=error_erc.returncode,
            warning_erc_returncode=warning_erc.returncode,
            error_report_sha256=sha256_text(error_text),
            warning_report_sha256=sha256_text(warning_text),
            error_report=error_text,
            warning_report=warning_text,
            error_counts=error_counts,
            allowed_warning_counts=allowed_warning_counts,
            blocking_warning_counts=blocking_warning_counts,
            allowed_warnings=allowed_warnings,
            blocking_warnings=blocking_warnings,
        )


def _lock_candidates() -> list[Path]:
    patterns = (
        f"~{PROJECT}.kicad_sch.lck",
        f"~{PROJECT}.kicad_pcb.lck",
        f"{PROJECT}.kicad_sch.lck",
        f"{PROJECT}.kicad_pcb.lck",
    )
    return [B3_DIR / name for name in patterns if (B3_DIR / name).exists()]


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def promote(staging: Path, validation: ValidationResult) -> None:
    if not validation.passed:
        raise RuntimeError(
            "promotion refused: KiCad parse or zero-error/zero-warning ERC gate failed"
        )
    locks = _lock_candidates()
    if locks:
        raise RuntimeError(
            "promotion refused: close KiCad editors first; lock files: "
            + ", ".join(str(path) for path in locks)
        )
    if not AUTHORITATIVE_SCHEMATIC.is_file():
        raise RuntimeError(
            f"authoritative B3 schematic missing: {AUTHORITATIVE_SCHEMATIC}"
        )
    current_hash = sha256_file(AUTHORITATIVE_SCHEMATIC)
    if current_hash != EXPECTED_B3_PRE_PROMOTION_SHA256:
        raise RuntimeError(
            "promotion refused: authoritative B3 pre-edit hash changed: "
            f"expected {EXPECTED_B3_PRE_PROMOTION_SHA256}, got {current_hash}"
        )
    temporary = AUTHORITATIVE_SCHEMATIC.with_name(
        f".{AUTHORITATIVE_SCHEMATIC.name}.{os.getpid()}.promote.tmp"
    )
    try:
        shutil.copyfile(staging, temporary)
        os.replace(temporary, AUTHORITATIVE_SCHEMATIC)
    finally:
        if temporary.exists():
            temporary.unlink()


def make_manifest(
    schematic: str,
    staging: Path | None,
    validation: ValidationResult | None,
    promoted: bool,
) -> dict[str, object]:
    return {
        "schema": 1,
        "project": PROJECT,
        "revision": REVISION,
        "design_state": "HOLD",
        "manufacturing_release": False,
        "authoritative_b3_schematic": str(AUTHORITATIVE_SCHEMATIC),
        "default_write_scope": "staging_only",
        "staging_path": str(staging) if staging else None,
        "promoted": promoted,
        "frozen_b2_sha256": assert_frozen_b2(),
        "b3_custom_library_sha256": assert_b3_custom_libraries(),
        "schematic": {
            "bytes": len(schematic.encode("utf-8")),
            "sha256": sha256_text(schematic),
            "deterministic_uuid_v5": True,
        },
        "library_binding": {
            "expected_erc_warnings": 0,
            "embedded_definitions": "exact KiCad/project source forms",
            "instance_property_overrides": "value, footprint, datasheet, description",
            "generic_source_symbols": {
                "F1": PTC_1206_SYMBOL,
                "J4": "Connector:Micro_SD_Card_Det2",
                "J6": "Connector_Generic:Conn_01x03",
                "SW1-SW5": "Switch:SW_Push",
                "U8-U11": "Power_Protection:USBLC6-2SC6 (flattened inherited source)",
            },
            "u4_vout_erc_model": (
                "physical pins 7 and 8 both remain named VOUT and connected to "
                "SYS_3V3; embedded pin 8 electrical type is passive to avoid a "
                "false power-output-to-power-output ERC conflict"
            ),
        },
        "si0": {
            "bidirectional_readback_preserved": True,
            "device": "SN74CB3Q3245PWR",
            "lcsc": "C470961",
            "channel": "A6 pin7 <-> B6 pin13",
            "supply": "EPD_3V3",
            "oe": (
                "pin19 EPD_BUF_OE_N; 10k pullup to EPD_3V3; Q3 2N7002/C8545 "
                "pulls low when GPIO38 EPD_BUF_CONNECT is high"
            ),
            "gpio38_directly_crosses_power_domain": False,
            "one_way_buffer_simplification": False,
        },
        "battery_adc": {
            "gpio": 1,
            "r49_bat_pos_to_adc": "220k 1% DNP by default",
            "r50_adc_to_ground": "100k 1% FIT",
            "c49_adc_to_ground": "0.1uF FIT",
            "fit_gate": "shutdown leakage, back-power, settling, and ADC calibration",
        },
        "tps63070_layout_contract": {
            "authority": "TI TPS63070 Rev.B datasheet, section 11.1",
            "r29": "10k series from VSYS_RAW (VIN) to DCDC_PS_SYNC",
            "c46": "10uF 0603 local HF capacitor from VSYS_RAW (VIN) to GND",
            "c47": "10uF 0603 local HF capacitor from SYS_3V3 (VOUT) to GND",
            "bulk_preserved": "C31-C33 input; C34-C37 output",
            "pcb_gate": "C46/C47 must be placed as close as possible to U4 VIN/VOUT and GND pins",
        },
        "usb_shield": {
            "net": "USB_SHIELD",
            "r64": "0R to GND FIT",
            "c50": "1nF to GND DNP EMC option",
            "r65": "1M to GND DNP EMC option",
        },
        "validation": (
            {
                "kicad_version": validation.kicad_version,
                "parse_returncode": validation.parse_returncode,
                "error_erc": {
                    "returncode": validation.error_erc_returncode,
                    "report_sha256": validation.error_report_sha256,
                    "counts": validation.error_counts,
                },
                "warning_inventory": {
                    "command_returncode": validation.warning_erc_returncode,
                    "report_sha256": validation.warning_report_sha256,
                    "gate": "zero warnings; reviewed fingerprint set is empty",
                    "expected_library_warning_refs": {
                        code: sorted(references)
                        for code, references in sorted(
                            EXPECTED_ERC_LIBRARY_WARNING_REFS.items()
                        )
                    },
                    "allowed_counts": validation.allowed_warning_counts,
                    "allowed": [
                        {
                            "category": category,
                            "reference": reference,
                            "description": description,
                        }
                        for category, reference, description in validation.allowed_warnings
                    ],
                    "blocking_unexpected_counts": validation.blocking_warning_counts,
                    "blocking_unexpected": [
                        {
                            "category": category,
                            "reference": reference,
                            "description": description,
                        }
                        for category, reference, description in validation.blocking_warnings
                    ],
                },
                "passed": validation.passed,
            }
            if validation
            else None
        ),
        "holds": list(HOLD_ITEMS),
        "hardware_accessed": False,
        "network_accessed": False,
        "serial_or_com_accessed": False,
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the deterministic MF1750 WROOM B3 R3 staging schematic. "
            "Default writes staging only; --promote is parse/ERC/hash/lock gated."
        )
    )
    parser.add_argument(
        "--staging",
        type=Path,
        default=DEFAULT_STAGING,
        help="staging .kicad_sch path (default is a non-authoritative file in B3 root)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build and check determinism without writing or invoking KiCad",
    )
    parser.add_argument(
        "--promote",
        action="store_true",
        help="replace the authoritative B3 schematic only after all promotion gates pass",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.promote and args.dry_run:
        raise SystemExit("--promote and --dry-run are mutually exclusive")
    staging = args.staging.resolve()
    if staging.suffix.lower() != ".kicad_sch":
        raise SystemExit("--staging must end in .kicad_sch")
    if staging == AUTHORITATIVE_SCHEMATIC.resolve():
        raise SystemExit(
            "--staging must not name the authoritative B3 schematic; use a distinct "
            "candidate path and --promote"
        )
    try:
        staging.relative_to(B2_DIR.resolve())
    except ValueError:
        pass
    else:
        raise SystemExit("--staging may not write anywhere inside the frozen B2 source")

    schematic = assert_deterministic()
    if args.dry_run:
        print(json.dumps(make_manifest(schematic, None, None, False), indent=2))
        return 0

    write_atomic(staging, schematic)
    validation = validate_schematic(staging)
    promoted = False
    if args.promote:
        promote(staging, validation)
        promoted = True
    manifest = make_manifest(schematic, staging, validation, promoted)
    print(json.dumps(manifest, indent=2))
    if not validation.passed:
        if validation.error_counts or validation.error_erc_returncode != 0:
            print(validation.error_report, file=sys.stderr)
        if validation.blocking_warning_counts or validation.warning_erc_returncode != 0:
            print(validation.warning_report, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
