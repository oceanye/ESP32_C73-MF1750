#!/usr/bin/env python3
"""Freeze one explicitly selected vendor waveform as an empirical H3 include.

This is an offline build tool.  It identity-checks the selected local vendor
artifact, decrypts it only in memory, and writes a deterministic C++ include.
It never chooses a profile automatically and contains no hardware transport,
flash, refresh, recovery, or authorization path.

The emitted H3 construction (0x20 = decoded[0:799], 0x21 = 704 * 0xFF) is a
cross-generation empirical hypothesis.  Generating an include is not live
authorization and does not establish a safe SPD1657 initialization sequence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Final


KIND: Final = "mf1750-spd1657-vendor-profile-pack"
SCHEMA_VERSION: Final = 1
REPO_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_ROOT: Final = (
    REPO_ROOT / "参考资料" / "REG-API-oqc(1)(1)" / "REG-API-oqc"
)

_CIPHERTEXT_BYTES: Final = 800
_DECODED_BYTES: Final = 800
_HEADER_BYTES: Final = 7
_CATEGORY_COUNT: Final = 9
_CATEGORY_BYTES: Final = 8 * 11
_R20_BYTES: Final = 799
_R21_BYTES: Final = 704
_R21: Final = b"\xff" * _R21_BYTES
_R21_SHA256: Final = "24acee297a3397869e18899db60585b90d94ffef3435330424f67e752df7863f"


class ProfilePackError(RuntimeError):
    """Raised when frozen evidence or output invariants do not hold."""


@dataclass(frozen=True)
class ProfileSpec:
    profile_id: str
    namespace: str
    source_relative: Path
    source_sha256: str
    required_source_markers: tuple[str, ...]
    initializer_name: str
    wrapper_bytes: int
    wrapper_sha256: str
    wrapped_key_bytes: int
    recovered_key_sha256: str | None
    external_key_source_relative: Path | None
    external_key_source_sha256: str | None
    plaintext_sha256: str
    r20_sha256: str
    header_sha256: str
    temperature_min_c: int
    temperature_max_c: int


PROFILES: Final[dict[str, ProfileSpec]] = {
    "WF20_25": ProfileSpec(
        profile_id="WF20_25",
        namespace="wf20_25_empirical_h3",
        source_relative=Path("Sample Code/WF20_25.h"),
        source_sha256=(
            "0dd568cca1d18cdd475a9ef5c7b7b2b56f11dc5abeeeb5d478b28f7bcb65e821"
        ),
        required_source_markers=(
            "E5 2-bit DEvelopment Environment",
            "File Name : WF20_25.h",
            "Date : 2026.01.06,08:55",
            "#define SIZE 842",
        ),
        initializer_name="WF20_25",
        wrapper_bytes=842,
        wrapper_sha256=(
            "97efcac1cbc6604a52b942a00b13df349530e152fd28063ed9eda94a36e2dcc5"
        ),
        wrapped_key_bytes=40,
        recovered_key_sha256=None,
        external_key_source_relative=Path("Sample Code/E28xx.c"),
        external_key_source_sha256=(
            "7a7601f5baecdda5cfb8cd32780c878fff52c1bd44fe8551114e277976d6c2b3"
        ),
        plaintext_sha256=(
            "1591338095e153bd0c7381b096e0b2e73d35131a700aab7c6cfde6c4756a7a8f"
        ),
        r20_sha256=("3cab2e2915205400bfdb0c2749a3e1e606cb6f190b8f3638849c532449a0ca26"),
        header_sha256=(
            "2fc6ab4de405835d9a5ff93a19adb03e277d0dece9df87a88c467a07bcb801af"
        ),
        temperature_min_c=20,
        temperature_max_c=25,
    ),
    "WF23_25": ProfileSpec(
        profile_id="WF23_25",
        namespace="wf23_25_empirical_h3",
        source_relative=Path("Projects/MDK-ARM/12"),
        source_sha256=(
            "c75d23a0f290deb8416619028284c53726bd399921a2dc0ffe043bef7f227c5d"
        ),
        required_source_markers=(
            "E5 2-bit DEvelopment Environment",
            "File Name : WF23_25.h",
            "Date : 2025.12.26,14:48",
            "#define SIZE 876",
        ),
        initializer_name="WF23_25",
        wrapper_bytes=876,
        wrapper_sha256=(
            "d01caa5581b69ab82d7bb34175d21220e4c08582eb55ce5f9f6391700cd6ebb4"
        ),
        wrapped_key_bytes=74,
        recovered_key_sha256=(
            "ef1a0b1112267abc84050c3036ec5b627e13e1ef882753062124e5649c0338e2"
        ),
        external_key_source_relative=None,
        external_key_source_sha256=None,
        plaintext_sha256=(
            "95e5fef3dc2946afdabbb35dceef1f1e48b8917d181946a82d06724c0a1c09d8"
        ),
        r20_sha256=("2eeae0e8e6a936cfd55e0a215371c114c037dbb70e701d8b95a2f560387788fb"),
        header_sha256=(
            "082e520524ebe6c5667d778a1c51407a37d459cc34f8db76b54ba26e93732185"
        ),
        temperature_min_c=23,
        temperature_max_c=25,
    ),
}


@dataclass(frozen=True)
class ProfileMaterial:
    spec: ProfileSpec
    source_bytes: int
    wrapper_sha256: str
    plaintext: bytes

    @property
    def header(self) -> bytes:
        return self.plaintext[:_HEADER_BYTES]

    @property
    def power_payload(self) -> bytes:
        return b"\x0f" + self.plaintext[:5]

    @property
    def pll_payload(self) -> bytes:
        return self.plaintext[6:7]

    @property
    def r20(self) -> bytes:
        return self.plaintext[:_R20_BYTES]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfilePackError(message)


def _read_exact(path: Path, expected_sha256: str, label: str) -> bytes:
    if not path.is_file():
        raise ProfilePackError(f"required {label} is missing: {path}")
    payload = path.read_bytes()
    observed = _sha256(payload)
    if observed != expected_sha256:
        raise ProfilePackError(
            f"{label} identity mismatch: expected {expected_sha256}, "
            f"observed {observed}"
        )
    return payload


def _strip_c_comments(text: str) -> str:
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", without_blocks)


def _extract_braced_body(text: str, start: int, label: str) -> str:
    opening = text.find("{", start)
    if opening < 0:
        raise ProfilePackError(f"cannot find opening brace for {label}")
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise ProfilePackError(f"cannot find closing brace for {label}")


def _extract_initializer(payload: bytes, name: str) -> bytes:
    text = payload.decode("latin-1")
    match = re.search(
        rf"\b{re.escape(name)}\s*\[[^\]]*\]\s*=\s*\{{",
        text,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ProfilePackError(f"cannot locate {name} initializer")
    body = _strip_c_comments(_extract_braced_body(text, match.start(), name))
    values = [int(value, 16) for value in re.findall(r"\b0[xX]([0-9A-Fa-f]+)\b", body)]
    _require(all(0 <= value <= 0xFF for value in values), "initializer byte overflow")
    return bytes(values)


def _recover_wrapped_key(wrapper: bytes, expected_key_bytes: int) -> bytes:
    """Recover a vendor key only after explicit envelope bounds checks."""

    _require(expected_key_bytes > 0, "wrapped-key length must be positive")
    _require(
        expected_key_bytes <= _CIPHERTEXT_BYTES,
        "wrapped-key length exceeds the XOR source region",
    )
    _require(len(wrapper) >= _CIPHERTEXT_BYTES + 2, "wrapper has no key-length field")
    declared = int.from_bytes(wrapper[_CIPHERTEXT_BYTES : _CIPHERTEXT_BYTES + 2], "big")
    _require(declared == expected_key_bytes, "wrapped-key length field changed")
    expected_wrapper_bytes = _CIPHERTEXT_BYTES + 2 + expected_key_bytes
    _require(
        len(wrapper) == expected_wrapper_bytes,
        "wrapped-key envelope length changed",
    )
    return bytes(
        wrapper[index] ^ wrapper[_CIPHERTEXT_BYTES + 2 + index]
        for index in range(expected_key_bytes)
    )


def _external_source_key(spec: ProfileSpec, reference_root: Path) -> bytes | None:
    if spec.external_key_source_relative is None:
        _require(
            spec.external_key_source_sha256 is None,
            "external key source identity is inconsistent",
        )
        return None
    _require(
        spec.external_key_source_sha256 is not None,
        "external key source hash is missing",
    )
    source = _read_exact(
        reference_root / spec.external_key_source_relative,
        spec.external_key_source_sha256,
        f"{spec.profile_id} external key source",
    )
    match = re.search(rb'\bcustomer_key\s*\[\s*\]\s*=\s*"([^"\r\n]+)"', source)
    if match is None:
        raise ProfilePackError("cannot locate customer_key in its frozen source")
    try:
        return match.group(1).decode("ascii").encode("ascii")
    except UnicodeError as error:
        raise ProfilePackError("frozen customer_key is not ASCII") from error


def _decrypt(wrapper: bytes, recovered_key: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as error:
        raise ProfilePackError(
            "cryptography is required for offline vendor-profile packing"
        ) from error

    aes_key = hashlib.sha256(recovered_key).digest()
    aes_iv = hashlib.md5(recovered_key).digest()  # noqa: S324 - exact vendor ABI
    decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(aes_iv)).decryptor()
    return decryptor.update(wrapper[:_CIPHERTEXT_BYTES]) + decryptor.finalize()


def load_profile(
    profile_id: str, reference_root: Path = DEFAULT_REFERENCE_ROOT
) -> ProfileMaterial:
    """Load one explicitly named profile and enforce every frozen invariant."""

    if profile_id not in PROFILES:
        choices = ", ".join(sorted(PROFILES))
        raise ProfilePackError(f"profile must be selected explicitly from: {choices}")
    spec = PROFILES[profile_id]
    source = _read_exact(
        reference_root / spec.source_relative,
        spec.source_sha256,
        f"{profile_id} vendor source",
    )
    source_text = source.decode("latin-1")
    _require(
        all(marker in source_text for marker in spec.required_source_markers),
        f"{profile_id} source metadata changed",
    )
    wrapper = _extract_initializer(source, spec.initializer_name)
    _require(len(wrapper) == spec.wrapper_bytes, f"{profile_id} wrapper size changed")
    _require(
        _sha256(wrapper) == spec.wrapper_sha256,
        f"{profile_id} wrapper identity changed",
    )
    recovered_key = _recover_wrapped_key(wrapper, spec.wrapped_key_bytes)
    external_key = _external_source_key(spec, reference_root)
    if external_key is not None:
        _require(
            recovered_key == external_key,
            f"{profile_id} wrapper does not match its frozen key source",
        )
    else:
        _require(
            spec.recovered_key_sha256 is not None
            and _sha256(recovered_key) == spec.recovered_key_sha256,
            f"{profile_id} recovered-key identity changed",
        )
        _require(
            all(0x20 <= value < 0x7F for value in recovered_key),
            f"{profile_id} recovered key is no longer printable ASCII",
        )

    plaintext = _decrypt(wrapper, recovered_key)
    _require(len(plaintext) == _DECODED_BYTES, "decoded waveform size changed")
    _require(
        _sha256(plaintext) == spec.plaintext_sha256,
        f"{profile_id} decoded identity changed",
    )
    _require(
        plaintext[_R20_BYTES] == 0,
        f"{profile_id} decoded padding sentinel changed",
    )
    _require(
        _HEADER_BYTES + _CATEGORY_COUNT * _CATEGORY_BYTES + 1 == len(plaintext),
        f"{profile_id} decoded geometry changed",
    )
    _require(
        _sha256(plaintext[:_R20_BYTES]) == spec.r20_sha256,
        f"{profile_id} empirical H3 R20 identity changed",
    )
    header_sha256 = _sha256(plaintext[:_HEADER_BYTES])
    _require(
        header_sha256 == spec.header_sha256,
        f"{profile_id} decoded header identity changed",
    )
    _require(_sha256(_R21) == _R21_SHA256, "fixed H3 R21 identity changed")

    header = plaintext[:_HEADER_BYTES]
    _require(header[0] & 0xFC == 0, f"{profile_id} PWR VG range bits changed")
    _require(
        all(value <= 0x78 for value in header[1:5]),
        f"{profile_id} PWR level code is outside the public manual range",
    )
    _require(header[6] & 0xF8 == 0, f"{profile_id} PLL reserved bits changed")
    return ProfileMaterial(
        spec=spec,
        source_bytes=len(source),
        wrapper_sha256=_sha256(wrapper),
        plaintext=plaintext,
    )


def _format_cpp_bytes(name: str, payload: bytes) -> str:
    lines = [f"static constexpr std::uint8_t {name}[{len(payload)}] = {{"]
    for offset in range(0, len(payload), 16):
        chunk = payload[offset : offset + 16]
        lines.append("    " + ", ".join(f"0x{value:02X}" for value in chunk) + ",")
    lines.append("};")
    return "\n".join(lines)


def _electrical_metadata(header: bytes) -> dict[str, int]:
    gate_abs_v = (20, 17, 13, 10)[header[0] & 0x03]
    full_source_abs_v = (15, 15, 11, 8)[header[0] & 0x03]
    levels_mv = [3000 + 100 * value for value in header[1:5]]
    frame_rate_hz = (25, 32, 43, 50, 65, 75, 85, 100)[header[6]]
    return {
        "gate_positive_mv": gate_abs_v * 1000,
        "gate_negative_mv": -gate_abs_v * 1000,
        "full_source_positive_mv": full_source_abs_v * 1000,
        "full_source_negative_mv": -full_source_abs_v * 1000,
        "vsh_lv_mv": levels_mv[0],
        "vsl_lv_mv": -levels_mv[1],
        "vsh_lv2_mv": levels_mv[2],
        "vsl_lv2_mv": -levels_mv[3],
        "frame_rate_hz": frame_rate_hz,
    }


def render_include(material: ProfileMaterial) -> bytes:
    """Render a deterministic payload-bearing include without key material."""

    spec = material.spec
    header = material.header
    power_payload = material.power_payload
    pll_payload = material.pll_payload
    electrical = _electrical_metadata(header)
    lines = [
        "#pragma once",
        "",
        "// Generated by mf1750_spd1657_vendor_profile_pack.py.",
        "// EMPIRICAL H3 CROSS-GENERATION HYPOTHESIS; NOT LIVE AUTHORIZED.",
        "// This file performs no hardware I/O and does not select a profile.",
        "// Recovery and every visible refresh require separate authorization.",
        "",
        "#include <cstddef>",
        "#include <cstdint>",
        "",
        "namespace mf1750 {",
        "namespace runtime_lut {",
        f"namespace {spec.namespace} {{",
        "",
        "static constexpr bool kEmpiricalH3 = true;",
        "static constexpr bool kLiveAuthorized = false;",
        "static constexpr bool kProfileAutoSelected = false;",
        "static constexpr bool kContainsHardwareIo = false;",
        f'static constexpr char kProfileId[] = "{spec.profile_id}";',
        f'static constexpr char kSourceArtifact[] = "{spec.source_relative.as_posix()}";',
        f'static constexpr char kSourceArtifactSha256[] = "{spec.source_sha256}";',
        f'static constexpr char kWrapperSha256[] = "{material.wrapper_sha256}";',
        f'static constexpr char kDecodedPlaintextSha256[] = "{spec.plaintext_sha256}";',
        f'static constexpr char kDecodedHeaderSha256[] = "{_sha256(header)}";',
        f'static constexpr char kPowerPayloadSha256[] = "{_sha256(power_payload)}";',
        f'static constexpr char kPllPayloadSha256[] = "{_sha256(pll_payload)}";',
        f'static constexpr char kR20PayloadSha256[] = "{spec.r20_sha256}";',
        f'static constexpr char kR21PayloadSha256[] = "{_R21_SHA256}";',
        "",
        f"static constexpr int kApparentTemperatureMinC = {spec.temperature_min_c};",
        f"static constexpr int kApparentTemperatureMaxC = {spec.temperature_max_c};",
        f"static constexpr int kRequestedGatePositiveMv = {electrical['gate_positive_mv']};",
        f"static constexpr int kRequestedGateNegativeMv = {electrical['gate_negative_mv']};",
        f"static constexpr int kRequestedFullSourcePositiveMv = {electrical['full_source_positive_mv']};",
        f"static constexpr int kRequestedFullSourceNegativeMv = {electrical['full_source_negative_mv']};",
        f"static constexpr int kRequestedVshLvMv = {electrical['vsh_lv_mv']};",
        f"static constexpr int kRequestedVslLvMv = {electrical['vsl_lv_mv']};",
        f"static constexpr int kRequestedVshLv2Mv = {electrical['vsh_lv2_mv']};",
        f"static constexpr int kRequestedVslLv2Mv = {electrical['vsl_lv2_mv']};",
        f"static constexpr unsigned kRequestedFrameRateHz = {electrical['frame_rate_hz']};",
        "static constexpr bool kPanelOrFplLimitsProven = false;",
        "static constexpr bool kH3HeaderBindingProven = false;",
        "",
        "static constexpr std::uint8_t kPowerCommand = 0x01;",
        "static constexpr std::uint8_t kPllCommand = 0x30;",
        "static constexpr std::uint8_t kR20Command = 0x20;",
        "static constexpr std::uint8_t kR21Command = 0x21;",
        "static constexpr std::size_t kDecodedBytes = 800;",
        "static constexpr std::size_t kDecodedPaddingOffset = 799;",
        "static constexpr std::size_t kHeaderBytes = 7;",
        "static constexpr std::size_t kPowerPayloadBytes = 6;",
        "static constexpr std::size_t kPllPayloadBytes = 1;",
        "static constexpr std::size_t kR20PayloadBytes = 799;",
        "static constexpr std::size_t kR21PayloadBytes = 704;",
        "static constexpr bool kR21IsAllFf = true;",
        "static constexpr bool kDecodedPaddingSentinelWasZero = true;",
        "static constexpr bool kDecodedHeaderByte5IsLegacyVcomSlot = true;",
        "static constexpr bool kDecodedHeaderByte5WrittenByCurrentArmccLoader = false;",
        "",
        _format_cpp_bytes("kDecodedHeader", header),
        "",
        _format_cpp_bytes("kPowerPayload", power_payload),
        "",
        _format_cpp_bytes("kPllPayload", pll_payload),
        "",
        _format_cpp_bytes("kR20Payload", material.r20),
        "",
        _format_cpp_bytes("kR21Payload", _R21),
        "",
        'static_assert(sizeof(kDecodedHeader) == kHeaderBytes, "header length changed");',
        'static_assert(sizeof(kPowerPayload) == kPowerPayloadBytes, "PWR length changed");',
        'static_assert(sizeof(kPllPayload) == kPllPayloadBytes, "PLL length changed");',
        'static_assert(sizeof(kR20Payload) == kR20PayloadBytes, "R20 length changed");',
        'static_assert(sizeof(kR21Payload) == kR21PayloadBytes, "R21 length changed");',
        'static_assert(kR20PayloadBytes + 1 == kDecodedBytes, "H3 padding contract changed");',
        'static_assert(kDecodedPaddingOffset == kR20PayloadBytes, "sentinel offset changed");',
        "",
        f"}}  // namespace {spec.namespace}",
        "}  // namespace runtime_lut",
        "}  // namespace mf1750",
        "",
    ]
    return "\n".join(lines).encode("ascii")


def write_include(
    output: Path, rendered: bytes, source_paths: tuple[Path, ...]
) -> dict[str, object]:
    """Write exactly one requested include, refusing evidence-file aliases."""

    if output.suffix.lower() != ".inc":
        raise ProfilePackError("output must use the .inc suffix")
    if output.exists() and output.is_dir():
        raise ProfilePackError("output path names a directory")
    if output.is_symlink():
        raise ProfilePackError("output path must not be a symbolic link")
    resolved_output = output.resolve()
    if any(resolved_output == source.resolve() for source in source_paths):
        raise ProfilePackError("output must not overwrite frozen vendor evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rendered)
    return {
        "path": output.as_posix(),
        "bytes": len(rendered),
        "sha256": _sha256(rendered),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        required=True,
        choices=sorted(PROFILES),
        help="explicit vendor profile; there is intentionally no default",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REFERENCE_ROOT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        material = load_profile(args.profile, args.reference_root)
        rendered = render_include(material)
        source_paths = [args.reference_root / material.spec.source_relative]
        if material.spec.external_key_source_relative is not None:
            source_paths.append(
                args.reference_root / material.spec.external_key_source_relative
            )
        target = write_include(args.output, rendered, tuple(source_paths))
    except (OSError, ProfilePackError) as error:
        json.dump(
            {"kind": KIND, "schema_version": SCHEMA_VERSION, "error": str(error)},
            sys.stdout,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")
        return 2

    json.dump(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "profile_id": material.spec.profile_id,
            "empirical_h3": True,
            "live_authorized": False,
            "target_file": target,
        },
        sys.stdout,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
