#!/usr/bin/env python3
"""Inspect fail-closed runtime-waveform candidates without hardware access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from host.runtime_waveform import contracts, evidence, virtual_palette  # noqa: E402


MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_PAYLOAD_BYTES = 1024 * 1024


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise contracts.RuntimeWaveformContractError(
                f"duplicate JSON key {key!r}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise contracts.RuntimeWaveformContractError(
        f"non-finite JSON constant {value!r} is forbidden"
    )


def _read_regular(path: Path, *, label: str, maximum: int) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file():
            raise contracts.RuntimeWaveformContractError(
                f"{label} must be a regular non-symlink file"
            )
        if before.st_size <= 0 or before.st_size > maximum:
            raise contracts.RuntimeWaveformContractError(f"{label} size is invalid")
        payload = path.read_bytes()
        after = path.lstat()
    except OSError as error:
        raise contracts.RuntimeWaveformContractError(
            f"could not read {label}: {error}"
        ) from error
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise contracts.RuntimeWaveformContractError(f"{label} changed while read")
    return payload


def _load_json(path: Path, *, label: str) -> Any:
    payload = _read_regular(path, label=label, maximum=MAX_MANIFEST_BYTES)
    try:
        decoded = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise contracts.RuntimeWaveformContractError(
            f"{label} must be UTF-8"
        ) from error
    try:
        value = json.loads(
            decoded,
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        raise contracts.RuntimeWaveformContractError(
            f"{label} is invalid JSON"
        ) from error
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    value = _load_json(path, label="waveform manifest")
    if not isinstance(value, dict):
        raise contracts.RuntimeWaveformContractError(
            "waveform manifest top level must be an object"
        )
    return value


def load_virtual_colors(path: Path) -> list[dict[str, Any]]:
    value = _load_json(path, label="virtual color list")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise contracts.RuntimeWaveformContractError(
            "virtual color list must be an array of objects"
        )
    return value


def _payloads(args: argparse.Namespace) -> dict[str, bytes] | None:
    if args.cs1_payload is None and args.cs2_payload is None:
        return None
    if args.cs1_payload is None or args.cs2_payload is None:
        raise contracts.RuntimeWaveformContractError(
            "CS1 and CS2 payload paths must be supplied together"
        )
    return {
        "CS1": _read_regular(
            args.cs1_payload, label="CS1 waveform payload", maximum=MAX_PAYLOAD_BYTES
        ),
        "CS2": _read_regular(
            args.cs2_payload, label="CS2 waveform payload", maximum=MAX_PAYLOAD_BYTES
        ),
    }


def _artifact_bytes(specifications: list[str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for specification in specifications:
        role, separator, raw_path = specification.partition("=")
        if not separator or not role or not raw_path:
            raise contracts.RuntimeWaveformContractError(
                "--artifact must use ROLE=PATH"
            )
        if role in result:
            raise contracts.RuntimeWaveformContractError(
                f"artifact role {role!r} was supplied more than once"
            )
        result[role] = _read_regular(
            Path(raw_path), label=f"evidence artifact {role}", maximum=16 * 1024 * 1024
        )
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template", allow_abbrev=False)
    template.add_argument("--created-at", required=True)

    for name in ("inspect", "require-ready"):
        item = sub.add_parser(name, allow_abbrev=False)
        item.add_argument("--manifest", type=Path, required=True)
        item.add_argument("--cs1-payload", type=Path)
        item.add_argument("--cs2-payload", type=Path)
    evidence_parser = sub.add_parser("validate-evidence", allow_abbrev=False)
    evidence_parser.add_argument("--manifest", type=Path, required=True)
    evidence_parser.add_argument("--evidence-bundle", type=Path, required=True)
    evidence_parser.add_argument("--cs1-payload", type=Path, required=True)
    evidence_parser.add_argument("--cs2-payload", type=Path, required=True)
    evidence_parser.add_argument("--artifact", action="append", default=[])
    palette = sub.add_parser("palette", allow_abbrev=False)
    palette.add_argument("--colors", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "template":
            report = contracts.build_reference_blocked_candidate(
                created_at=args.created_at
            )
        elif args.command == "palette":
            try:
                report = virtual_palette.compile_virtual_palette(
                    load_virtual_colors(args.colors)
                )
            except virtual_palette.VirtualPaletteError as error:
                raise contracts.RuntimeWaveformContractError(str(error)) from error
        elif args.command == "validate-evidence":
            candidate = load_manifest(args.manifest)
            bundle = _load_json(args.evidence_bundle, label="waveform evidence bundle")
            if not isinstance(bundle, dict):
                raise contracts.RuntimeWaveformContractError(
                    "waveform evidence bundle top level must be an object"
                )
            payloads = _payloads(args)
            assert payloads is not None
            try:
                report = evidence.validate_evidence_bundle(
                    candidate,
                    bundle,
                    controller_payload_bytes=payloads,
                    artifact_bytes=_artifact_bytes(args.artifact),
                )
            except evidence.EvidenceBundleError as error:
                raise contracts.RuntimeWaveformContractError(str(error)) from error
        else:
            candidate = load_manifest(args.manifest)
            report = contracts.evaluate_candidate(
                candidate, controller_payload_bytes=_payloads(args)
            )
            if args.command == "require-ready":
                # This CLI is an offline inspector, not a hardware execution
                # authority.  The command remains fail-closed even when every
                # offline document field is complete.
                if report.get("execution_ready") is not False:
                    raise contracts.RuntimeWaveformContractError(
                        "offline contract unexpectedly claimed execution readiness"
                    )
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
                return 2
    except contracts.RuntimeWaveformContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
