#!/usr/bin/env python3
"""Audit a JLCPCB PCB/PCBA handoff without extracting any archive.

Normal audit execution writes exactly one JSON document to stdout; ``--help``
uses argparse's human-readable output. Exit status 0 means the package passed,
1 means one or more package invariants failed, and 2 means the invocation,
configuration, or auditor itself was invalid.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import stat
import sys
import zipfile
import zlib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterable


SCHEMA_VERSION = 1
FORBIDDEN_ZIP_SUFFIXES = frozenset({".kicad_prl", ".lck", ".bak", ".tmp", ".pyc"})

DEFAULT_CONFIG: dict[str, Any] = {
    "upload_dir": "upload",
    "gerber_zip": None,
    "bom_csv": None,
    "cpl_csv": None,
    "manifest": "MANIFEST.json",
    "sha256sums": "SHA256SUMS.txt",
    "package_hashes": "PACKAGE_HASHES.txt",
    "bom_headers": ["Comment", "Designator", "Footprint", "LCSC Part #"],
    "cpl_headers": ["Designator", "Mid X", "Mid Y", "Rotation", "Layer"],
    "designator_header": "Designator",
    "comment_header": "Comment",
    "footprint_header": "Footprint",
    "lcsc_header": "LCSC Part #",
    "lcsc_pattern": r"C[1-9][0-9]*",
    "designator_pattern": r"[A-Za-z][A-Za-z0-9_]*[0-9][A-Za-z0-9_]*",
    "cpl_x_header": "Mid X",
    "cpl_y_header": "Mid Y",
    "cpl_rotation_header": "Rotation",
    "cpl_side_header": "Layer",
    "allowed_cpl_sides": ["Top", "Bottom"],
    "gerber_required_patterns": [],
    "allow_extra_csv_columns": False,
    "audit_all_zip_files": True,
    "require_all_zips_in_package_hashes": True,
    "require_manifest_in_sha256sums": True,
    "require_manifest_files_in_sha256sums": True,
}

PATH_CONFIG_KEYS = {
    "upload_dir",
    "gerber_zip",
    "bom_csv",
    "cpl_csv",
    "manifest",
    "sha256sums",
    "package_hashes",
}
LIST_CONFIG_KEYS = {"bom_headers", "cpl_headers", "allowed_cpl_sides"}
OPTIONAL_LIST_CONFIG_KEYS = {"gerber_required_patterns"}
STRING_CONFIG_KEYS = {
    "designator_header",
    "comment_header",
    "footprint_header",
    "lcsc_header",
    "lcsc_pattern",
    "designator_pattern",
    "cpl_x_header",
    "cpl_y_header",
    "cpl_rotation_header",
    "cpl_side_header",
}
BOOL_CONFIG_KEYS = {
    "allow_extra_csv_columns",
    "audit_all_zip_files",
    "require_all_zips_in_package_hashes",
    "require_manifest_in_sha256sums",
    "require_manifest_files_in_sha256sums",
}


class ConfigurationError(ValueError):
    """Raised when command input or the optional configuration is invalid."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _normalise_relative(raw: str) -> tuple[str | None, str | None]:
    """Return (portable relative path, error) without touching the filesystem."""
    if not isinstance(raw, str) or not raw:
        return None, "path must be a non-empty string"
    if "\x00" in raw:
        return None, "path contains a NUL byte"

    portable = raw.replace("\\", "/")
    posix = PurePosixPath(portable)
    windows = PureWindowsPath(raw)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        return None, "absolute or drive-qualified path is forbidden"

    parts = portable.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None, "empty, dot, or parent path component is forbidden"
    return "/".join(parts), None


def _validated_config(supplied: dict[str, Any] | None) -> dict[str, Any]:
    supplied = supplied or {}
    unknown = sorted(set(supplied) - set(DEFAULT_CONFIG))
    if unknown:
        raise ConfigurationError("unknown config key(s): " + ", ".join(unknown))
    config = dict(DEFAULT_CONFIG)
    config.update(supplied)

    for key in PATH_CONFIG_KEYS:
        value = config[key]
        if value is None and key in {"gerber_zip", "bom_csv", "cpl_csv"}:
            continue
        if not isinstance(value, str) or not value:
            raise ConfigurationError(f"config key {key!r} must be a non-empty string")
        _, error = _normalise_relative(value)
        if error:
            raise ConfigurationError(f"config key {key!r}: {error}")

    for key in LIST_CONFIG_KEYS:
        value = config[key]
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item for item in value)
        ):
            raise ConfigurationError(
                f"config key {key!r} must be a non-empty string array"
            )
        if len(value) != len(set(value)):
            raise ConfigurationError(f"config key {key!r} contains duplicate values")

    for key in OPTIONAL_LIST_CONFIG_KEYS:
        value = config[key]
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item for item in value
        ):
            raise ConfigurationError(f"config key {key!r} must be a string array")
        if len(value) != len(set(value)):
            raise ConfigurationError(f"config key {key!r} contains duplicates")

    for key in STRING_CONFIG_KEYS:
        if not isinstance(config[key], str) or not config[key]:
            raise ConfigurationError(f"config key {key!r} must be a non-empty string")
    for key in BOOL_CONFIG_KEYS:
        if not isinstance(config[key], bool):
            raise ConfigurationError(f"config key {key!r} must be boolean")

    if config["designator_header"] not in config["bom_headers"]:
        raise ConfigurationError("designator_header is absent from bom_headers")
    if config["designator_header"] not in config["cpl_headers"]:
        raise ConfigurationError("designator_header is absent from cpl_headers")
    for key in ("comment_header", "footprint_header", "lcsc_header"):
        if config[key] not in config["bom_headers"]:
            raise ConfigurationError(f"{key} is absent from bom_headers")
    for key in (
        "cpl_x_header",
        "cpl_y_header",
        "cpl_rotation_header",
        "cpl_side_header",
    ):
        if config[key] not in config["cpl_headers"]:
            raise ConfigurationError(f"{key} is absent from cpl_headers")
    for key in ("lcsc_pattern", "designator_pattern"):
        try:
            re.compile(config[key])
        except re.error as exc:
            raise ConfigurationError(f"{key} is invalid: {exc}") from exc
    for index, pattern in enumerate(config["gerber_required_patterns"]):
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ConfigurationError(
                f"gerber_required_patterns[{index}] is invalid: {exc}"
            ) from exc
    return config


def _load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return _validated_config(None)
    try:
        supplied = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot read config JSON: {exc}") from exc
    if not isinstance(supplied, dict):
        raise ConfigurationError("config JSON must be an object")
    return _validated_config(supplied)


class Auditor:
    def __init__(
        self, root: Path, config: dict[str, Any], config_path: Path | None
    ) -> None:
        self.root = root.resolve()
        self.config = config
        self.config_path = config_path.resolve() if config_path else None
        self.errors: list[dict[str, Any]] = []
        self.checks: list[dict[str, Any]] = []
        self.inputs: dict[str, str | None] = {}
        self.hash_cache: dict[Path, str] = {}
        self.zip_paths: list[Path] = []
        self.manifest_entries: dict[str, str] = {}
        self.sha_entries: dict[str, str] = {}
        self.package_entries: dict[str, str] = {}

    def add_error(
        self,
        check: str,
        code: str,
        message: str,
        *,
        path: str | None = None,
        member: str | None = None,
        details: Any = None,
    ) -> None:
        item: dict[str, Any] = {"check": check, "code": code, "message": message}
        if path is not None:
            item["path"] = path
        if member is not None:
            item["member"] = member
        if details is not None:
            item["details"] = details
        self.errors.append(item)

    def run_check(self, check_id: str, function: Callable[[], dict[str, Any]]) -> None:
        before = len(self.errors)
        try:
            details = function()
            if details.get("skipped") and len(self.errors) == before:
                status_text = "SKIP"
            else:
                status_text = "PASS" if len(self.errors) == before else "FAIL"
        except (
            Exception
        ) as exc:  # A programming/runtime fault is distinct from bad input.
            self.add_error(
                check_id,
                "AUDITOR_EXCEPTION",
                f"unexpected auditor exception: {type(exc).__name__}: {exc}",
            )
            details = {}
            status_text = "ERROR"
        self.checks.append({"id": check_id, "status": status_text, "details": details})

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def path_from_relative(
        self, raw: str, check: str, *, canonical: bool = False
    ) -> tuple[Path | None, str | None]:
        normalised, error = _normalise_relative(raw)
        if error:
            self.add_error(check, "UNSAFE_PATH", error, path=str(raw))
            return None, None
        assert normalised is not None
        if canonical and raw != normalised:
            self.add_error(
                check,
                "NON_CANONICAL_PATH",
                "path must use canonical forward-slash relative form",
                path=raw,
                details={"canonical": normalised},
            )
            return None, None
        candidate = self.root.joinpath(*normalised.split("/"))
        try:
            resolved = candidate.resolve(strict=False)
        except OSError as exc:
            self.add_error(check, "PATH_RESOLUTION_ERROR", str(exc), path=normalised)
            return None, None
        if not _within(resolved, self.root):
            self.add_error(
                check,
                "UNSAFE_PATH",
                "path resolves outside the handoff root",
                path=normalised,
            )
            return None, None
        return candidate, normalised

    def _configured_path(self, key: str, check: str) -> tuple[Path | None, str | None]:
        raw = self.config[key]
        if raw is None:
            return None, None
        return self.path_from_relative(raw, check)

    def _discover_one(
        self,
        role: str,
        configured_key: str,
        candidates: Iterable[Path],
        check: str,
    ) -> Path | None:
        configured, configured_rel = self._configured_path(configured_key, check)
        if configured is not None:
            self.inputs[role] = configured_rel
            if not configured.is_file():
                self.add_error(
                    check,
                    "INPUT_FILE_MISSING",
                    f"configured {role} file does not exist",
                    path=configured_rel,
                )
                return None
            if configured.is_symlink():
                self.add_error(
                    check,
                    "INPUT_FILE_SYMLINK",
                    f"configured {role} must not be a symbolic link",
                    path=configured_rel,
                )
                return None
            return configured

        unique: dict[str, Path] = {}
        for candidate in candidates:
            if candidate.is_file():
                unique[str(candidate.resolve()).casefold()] = candidate
        found = sorted(unique.values(), key=lambda item: self.relative(item).casefold())
        if len(found) != 1:
            self.inputs[role] = None
            self.add_error(
                check,
                "INPUT_DISCOVERY_FAILED",
                f"expected exactly one {role} candidate, found {len(found)}",
                details={"candidates": [self.relative(path) for path in found]},
            )
            return None
        self.inputs[role] = self.relative(found[0])
        return found[0]

    def check_inputs(self) -> dict[str, Any]:
        upload_path, upload_rel = self._configured_path("upload_dir", "inputs")
        self.inputs["upload_dir"] = upload_rel
        if upload_path is None or not upload_path.is_dir():
            self.add_error(
                "inputs",
                "UPLOAD_DIRECTORY_MISSING",
                "upload directory does not exist",
                path=upload_rel,
            )
            upload_files: list[Path] = []
        else:
            upload_files = [path for path in upload_path.rglob("*") if path.is_file()]

        configured_gerber = self.config["gerber_zip"] is not None
        if configured_gerber:
            gerber_candidates: list[Path] = []
        else:
            upload_zips = [
                path for path in upload_files if path.suffix.casefold() == ".zip"
            ]
            preferred = [
                path
                for path in upload_zips
                if "gerber" in path.name.casefold() or "pcb" in path.name.casefold()
            ]
            gerber_candidates = preferred if preferred else upload_zips

        bom_candidates = [
            path
            for path in upload_files
            if path.suffix.casefold() == ".csv" and "bom" in path.name.casefold()
        ]
        cpl_candidates = [
            path
            for path in upload_files
            if path.suffix.casefold() == ".csv"
            and (
                "cpl" in path.name.casefold()
                or "placement" in path.name.casefold()
                or "pick-place" in path.name.casefold()
                or "pick_and_place" in path.name.casefold()
            )
        ]

        gerber = self._discover_one(
            "gerber_zip", "gerber_zip", gerber_candidates, "inputs"
        )
        bom = self._discover_one("bom_csv", "bom_csv", bom_candidates, "inputs")
        cpl = self._discover_one("cpl_csv", "cpl_csv", cpl_candidates, "inputs")

        for role, key in (
            ("manifest", "manifest"),
            ("sha256sums", "sha256sums"),
            ("package_hashes", "package_hashes"),
        ):
            path, relative = self._configured_path(key, "inputs")
            self.inputs[role] = relative
            if path is None or not path.is_file():
                self.add_error(
                    "inputs",
                    "INPUT_FILE_MISSING",
                    f"required {role} file does not exist",
                    path=relative,
                )
            elif path.is_symlink():
                self.add_error(
                    "inputs",
                    "INPUT_FILE_SYMLINK",
                    f"required {role} file must not be a symbolic link",
                    path=relative,
                )

        self._resolved_inputs = {"gerber_zip": gerber, "bom_csv": bom, "cpl_csv": cpl}
        return {"resolved": dict(self.inputs)}

    @staticmethod
    def _zip_member_path_error(name: str) -> str | None:
        if not name:
            return "member name is empty"
        if "\x00" in name:
            return "member name contains a NUL byte"
        if "\\" in name:
            return "backslash path separators are forbidden"
        path_without_trailing_slash = name[:-1] if name.endswith("/") else name
        if not path_without_trailing_slash:
            return "archive-root directory entry is forbidden"
        posix = PurePosixPath(path_without_trailing_slash)
        windows = PureWindowsPath(path_without_trailing_slash)
        if posix.is_absolute() or windows.is_absolute() or windows.drive:
            return "absolute or drive-qualified member path is forbidden"
        parts = path_without_trailing_slash.split("/")
        if any(part in ("", ".", "..") for part in parts):
            return "empty, dot, or parent member path component is forbidden"
        for part in parts:
            if any(ord(character) < 32 for character in part):
                return "control characters in member names are forbidden"
            if ":" in part:
                return "colon/NTFS alternate-stream member names are forbidden"
            if part.endswith((" ", ".")):
                return "member components ending in a space or dot are forbidden"
            if PureWindowsPath(part).is_reserved():
                return "Windows reserved-device member name is forbidden"
        return None

    @staticmethod
    def _zip_member_hygiene_violation(name: str) -> tuple[str, str] | None:
        portable = name.replace("\\", "/").rstrip("/")
        components = [component for component in portable.split("/") if component]
        if not components:
            return None
        if any(component.casefold() == "__pycache__" for component in components):
            return "python_cache_directory", "__pycache__ path components are forbidden"
        basename = components[-1]
        if basename.startswith("~"):
            return (
                "temporary_basename",
                "member basename starting with '~' is forbidden",
            )
        suffix = PurePosixPath(basename).suffix.casefold()
        if suffix in FORBIDDEN_ZIP_SUFFIXES:
            return "forbidden_suffix", f"member suffix {suffix!r} is forbidden"
        return None

    def _iter_zip_paths(self) -> list[Path]:
        gerber = self._resolved_inputs.get("gerber_zip")
        if self.config["audit_all_zip_files"]:
            found: list[Path] = []
            for directory, dirnames, filenames in os.walk(self.root, followlinks=False):
                directory_path = Path(directory)
                dirnames[:] = [
                    name
                    for name in dirnames
                    if not (directory_path / name).is_symlink()
                ]
                for filename in filenames:
                    candidate = directory_path / filename
                    if candidate.suffix.casefold() == ".zip":
                        found.append(candidate)
        else:
            found = [gerber] if gerber is not None else []
        if gerber is not None and gerber not in found:
            found.append(gerber)
        return sorted(set(found), key=lambda path: self.relative(path).casefold())

    def _audit_zip(self, path: Path) -> dict[str, Any]:
        relative = self.relative(path)
        report: dict[str, Any] = {
            "path": relative,
            "entries": 0,
            "uncompressed_bytes": 0,
        }
        if path.is_symlink() or not _within(path.resolve(strict=False), self.root):
            self.add_error(
                "zip_integrity",
                "ZIP_FILESYSTEM_PATH_UNSAFE",
                "ZIP file is a symlink or resolves outside the handoff root",
                path=relative,
            )
            return report
        try:
            with zipfile.ZipFile(path, "r") as archive:
                infos = archive.infolist()
                report["entries"] = len(infos)
                seen: dict[str, str] = {}
                for info in infos:
                    report["uncompressed_bytes"] += info.file_size
                    path_error = self._zip_member_path_error(info.filename)
                    if path_error:
                        self.add_error(
                            "zip_integrity",
                            "ZIP_UNSAFE_MEMBER_PATH",
                            path_error,
                            path=relative,
                            member=info.filename,
                        )
                    hygiene_violation = self._zip_member_hygiene_violation(
                        info.filename
                    )
                    if hygiene_violation is not None:
                        rule, reason = hygiene_violation
                        self.add_error(
                            "zip_integrity",
                            "ZIP_FORBIDDEN_PRIVATE_OR_TEMP_MEMBER",
                            reason,
                            path=relative,
                            member=info.filename,
                            details={"rule": rule},
                        )
                    collision_key = (
                        info.filename.replace("\\", "/").rstrip("/").casefold()
                    )
                    if collision_key in seen:
                        self.add_error(
                            "zip_integrity",
                            "ZIP_DUPLICATE_MEMBER",
                            "duplicate or case-colliding ZIP member",
                            path=relative,
                            member=info.filename,
                            details={"first": seen[collision_key]},
                        )
                    else:
                        seen[collision_key] = info.filename

                    unix_mode = (info.external_attr >> 16) & 0xFFFF
                    if unix_mode and stat.S_ISLNK(unix_mode):
                        self.add_error(
                            "zip_integrity",
                            "ZIP_SYMLINK_MEMBER",
                            "symbolic-link ZIP members are forbidden",
                            path=relative,
                            member=info.filename,
                        )
                    if info.is_dir() and (info.file_size != 0 or info.CRC != 0):
                        self.add_error(
                            "zip_integrity",
                            "ZIP_DIRECTORY_PAYLOAD",
                            "directory ZIP members must have zero size and CRC",
                            path=relative,
                            member=info.filename,
                        )
                    if info.flag_bits & 0x1:
                        self.add_error(
                            "zip_integrity",
                            "ZIP_ENCRYPTED_MEMBER",
                            "encrypted ZIP members cannot be audited",
                            path=relative,
                            member=info.filename,
                        )
                        continue

                    crc = 0
                    size = 0
                    try:
                        with archive.open(info, "r") as member_stream:
                            for chunk in iter(
                                lambda: member_stream.read(1024 * 1024), b""
                            ):
                                crc = zlib.crc32(chunk, crc)
                                size += len(chunk)
                    except (
                        OSError,
                        RuntimeError,
                        NotImplementedError,
                        zipfile.BadZipFile,
                    ) as exc:
                        error_code = (
                            "ZIP_CRC_MISMATCH"
                            if isinstance(exc, zipfile.BadZipFile)
                            and "crc" in str(exc).casefold()
                            else "ZIP_MEMBER_READ_ERROR"
                        )
                        self.add_error(
                            "zip_integrity",
                            error_code,
                            f"member cannot be read and CRC-checked: {exc}",
                            path=relative,
                            member=info.filename,
                        )
                        continue
                    crc &= 0xFFFFFFFF
                    if size != info.file_size or crc != info.CRC:
                        self.add_error(
                            "zip_integrity",
                            "ZIP_CRC_MISMATCH",
                            "member size or CRC does not match the central directory",
                            path=relative,
                            member=info.filename,
                            details={
                                "expected_crc32": f"{info.CRC:08x}",
                                "actual_crc32": f"{crc:08x}",
                                "expected_bytes": info.file_size,
                                "actual_bytes": size,
                            },
                        )
                for collision_key, member_name in seen.items():
                    components = collision_key.split("/")
                    for end in range(1, len(components)):
                        ancestor = "/".join(components[:end])
                        ancestor_name = seen.get(ancestor)
                        if ancestor_name is not None and not ancestor_name.endswith(
                            "/"
                        ):
                            self.add_error(
                                "zip_integrity",
                                "ZIP_FILE_ANCESTOR_COLLISION",
                                "a file member is also the ancestor of another member",
                                path=relative,
                                member=member_name,
                                details={"ancestor": ancestor_name},
                            )
                            break
        except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
            self.add_error(
                "zip_integrity",
                "ZIP_OPEN_ERROR",
                f"ZIP cannot be opened: {exc}",
                path=relative,
            )
        return report

    def check_zip_integrity(self) -> dict[str, Any]:
        self.zip_paths = self._iter_zip_paths()
        if not self.zip_paths:
            self.add_error(
                "zip_integrity",
                "ZIP_NOT_FOUND",
                "no ZIP archive was available to audit",
            )
        reports = [self._audit_zip(path) for path in self.zip_paths]
        return {"archives": reports, "archive_count": len(reports)}

    @staticmethod
    def _is_bottom_paste(name: str) -> bool:
        basename = PurePosixPath(name).name.casefold()
        if basename.endswith(".gbp"):
            return True
        compact = re.sub(r"[ ._-]+", "_", basename)
        return bool(re.search(r"(?:^|_)b(?:ottom)?_?paste(?:_|\.|$)", compact))

    @staticmethod
    def _gerber_has_drawing(data: bytes) -> bool:
        # Paste layers normally use flashes (D03); regions/traces use D01.
        text = data.decode("latin-1", errors="ignore")
        text = re.sub(r"G0?4.*?\*", "", text, flags=re.IGNORECASE | re.DOTALL)
        return re.search(r"D(?:0?1|0?3)\*", text, flags=re.IGNORECASE) is not None

    @staticmethod
    def _is_x2_bottom_paste(data: bytes) -> bool:
        text = data.decode("latin-1", errors="ignore")
        return (
            re.search(
                r"%TF\.FileFunction\s*,\s*Paste\s*,\s*(?:Bot|Bottom)\s*\*%",
                text,
                flags=re.IGNORECASE,
            )
            is not None
        )

    def check_gerber_archive(self) -> dict[str, Any]:
        path = self._resolved_inputs.get("gerber_zip")
        if path is None or not path.is_file():
            return {"skipped": True, "reason": "Gerber ZIP was not resolved"}
        relative = self.relative(path)
        result: dict[str, Any] = {
            "path": relative,
            "entry_count": 0,
            "bottom_paste_layers": [],
            "required_pattern_matches": [],
        }
        member_names: list[str] = []
        try:
            with zipfile.ZipFile(path, "r") as archive:
                for info in archive.infolist():
                    result["entry_count"] += 1
                    name = info.filename
                    if info.is_dir() or "/" in name or "\\" in name:
                        self.add_error(
                            "gerber_archive",
                            "GERBER_ZIP_NOT_FLAT",
                            "Gerber ZIP must contain files at archive root only",
                            path=relative,
                            member=name,
                        )
                    if name.casefold().endswith(".gbrjob"):
                        self.add_error(
                            "gerber_archive",
                            "GERBER_GBRJOB_FORBIDDEN",
                            ".gbrjob files must not be included in the upload ZIP",
                            path=relative,
                            member=name,
                        )
                    if info.is_dir():
                        continue
                    member_names.append(name)
                    try:
                        data = archive.read(info)
                    except (
                        OSError,
                        RuntimeError,
                        NotImplementedError,
                        zipfile.BadZipFile,
                    ):
                        # zip_integrity already emits the detailed read/CRC error.
                        continue
                    if self._is_bottom_paste(name) or self._is_x2_bottom_paste(data):
                        layer: dict[str, Any] = {
                            "member": name,
                            "bytes": info.file_size,
                        }
                        result["bottom_paste_layers"].append(layer)
                        layer["has_drawing_commands"] = self._gerber_has_drawing(data)
                        if not data or not layer["has_drawing_commands"]:
                            self.add_error(
                                "gerber_archive",
                                "GERBER_EMPTY_BOTTOM_PASTE",
                                "empty bottom-paste Gerber must be omitted",
                                path=relative,
                                member=name,
                            )
                for pattern in self.config["gerber_required_patterns"]:
                    matches = sorted(
                        name for name in member_names if re.search(pattern, name)
                    )
                    result["required_pattern_matches"].append(
                        {"pattern": pattern, "matches": matches}
                    )
                    if not matches:
                        self.add_error(
                            "gerber_archive",
                            "GERBER_REQUIRED_PATTERN_MISSING",
                            "no Gerber ZIP member matches a project-required pattern",
                            path=relative,
                            details={"pattern": pattern},
                        )
        except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
            self.add_error(
                "gerber_archive",
                "GERBER_ZIP_OPEN_ERROR",
                f"Gerber ZIP cannot be inspected: {exc}",
                path=relative,
            )
        if result["entry_count"] == 0:
            self.add_error(
                "gerber_archive",
                "GERBER_ZIP_EMPTY",
                "Gerber ZIP contains no entries",
                path=relative,
            )
        return result

    def _read_csv(
        self, path: Path, required_headers: list[str], role: str
    ) -> tuple[list[str], list[list[str]]]:
        relative = self.relative(path)
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
        except (OSError, UnicodeError, csv.Error) as exc:
            self.add_error(
                "bom_cpl",
                "CSV_READ_ERROR",
                f"{role} CSV cannot be read: {exc}",
                path=relative,
            )
            return [], []
        while rows and not any(cell.strip() for cell in rows[-1]):
            rows.pop()
        if not rows:
            self.add_error(
                "bom_cpl", "CSV_EMPTY", f"{role} CSV is empty", path=relative
            )
            return [], []

        header = rows[0]
        if any(not cell for cell in header) or len(header) != len(set(header)):
            self.add_error(
                "bom_cpl",
                "CSV_INVALID_HEADER",
                f"{role} header contains an empty or duplicate column",
                path=relative,
                details={"actual": header},
            )
        missing = sorted(set(required_headers) - set(header))
        unexpected = sorted(set(header) - set(required_headers))
        if missing or (unexpected and not self.config["allow_extra_csv_columns"]):
            self.add_error(
                "bom_cpl",
                "CSV_HEADER_MISMATCH",
                f"{role} CSV columns do not match the configured JLCPCB columns",
                path=relative,
                details={
                    "required": required_headers,
                    "actual": header,
                    "missing": missing,
                    "unexpected": unexpected,
                    "order_significant": False,
                },
            )

        data_rows: list[list[str]] = []
        for line_number, row in enumerate(rows[1:], start=2):
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                self.add_error(
                    "bom_cpl",
                    "CSV_ROW_WIDTH_MISMATCH",
                    f"{role} row has {len(row)} fields; header has {len(header)}",
                    path=relative,
                    details={"line": line_number},
                )
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            data_rows.append(row[: len(header)])
        if not data_rows:
            self.add_error(
                "bom_cpl",
                "CSV_NO_DATA_ROWS",
                f"{role} CSV has no data rows",
                path=relative,
            )
        return header, data_rows

    @staticmethod
    def _split_designators(value: str) -> list[str]:
        return [part for part in re.split(r"[,;\s]+", value.strip()) if part]

    @staticmethod
    def _finite_decimal(value: str, *, allow_mm: bool) -> bool:
        text = value.strip()
        if allow_mm and text.casefold().endswith("mm"):
            text = text[:-2].strip()
        if (
            re.fullmatch(
                r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?",
                text,
            )
            is None
        ):
            return False
        try:
            return math.isfinite(float(text))
        except ValueError:
            return False

    def check_bom_cpl(self) -> dict[str, Any]:
        bom_path = self._resolved_inputs.get("bom_csv")
        cpl_path = self._resolved_inputs.get("cpl_csv")
        if bom_path is None or cpl_path is None:
            return {"skipped": True, "reason": "BOM or CPL was not resolved"}

        bom_header, bom_rows = self._read_csv(
            bom_path, self.config["bom_headers"], "BOM"
        )
        cpl_header, cpl_rows = self._read_csv(
            cpl_path, self.config["cpl_headers"], "CPL"
        )
        designator_header = self.config["designator_header"]
        comment_header = self.config["comment_header"]
        footprint_header = self.config["footprint_header"]
        lcsc_header = self.config["lcsc_header"]
        bom_refs: set[str] = set()
        cpl_refs: set[str] = set()
        lcsc_values: set[str] = set()
        lcsc_regex = re.compile(self.config["lcsc_pattern"])
        designator_regex = re.compile(self.config["designator_pattern"])

        required_bom_fields = {
            designator_header,
            comment_header,
            footprint_header,
            lcsc_header,
        }
        if required_bom_fields.issubset(bom_header):
            designator_index = bom_header.index(designator_header)
            comment_index = bom_header.index(comment_header)
            footprint_index = bom_header.index(footprint_header)
            lcsc_index = bom_header.index(lcsc_header)
            for row_number, row in enumerate(bom_rows, start=2):
                refs = self._split_designators(row[designator_index])
                if not refs:
                    self.add_error(
                        "bom_cpl",
                        "BOM_EMPTY_DESIGNATOR",
                        "BOM row has no designator",
                        path=self.relative(bom_path),
                        details={"line": row_number},
                    )
                for reference in refs:
                    if designator_regex.fullmatch(reference) is None:
                        self.add_error(
                            "bom_cpl",
                            "BOM_INVALID_DESIGNATOR",
                            "expanded BOM designator does not match the configured format",
                            path=self.relative(bom_path),
                            details={"line": row_number, "designator": reference},
                        )
                    if reference in bom_refs:
                        self.add_error(
                            "bom_cpl",
                            "BOM_DUPLICATE_DESIGNATOR",
                            "BOM designator occurs more than once",
                            path=self.relative(bom_path),
                            details={"line": row_number, "designator": reference},
                        )
                    bom_refs.add(reference)

                if not row[comment_index].strip():
                    self.add_error(
                        "bom_cpl",
                        "BOM_EMPTY_COMMENT",
                        "BOM Comment must not be empty",
                        path=self.relative(bom_path),
                        details={"line": row_number},
                    )
                if not row[footprint_index].strip():
                    self.add_error(
                        "bom_cpl",
                        "BOM_EMPTY_FOOTPRINT",
                        "BOM Footprint must not be empty",
                        path=self.relative(bom_path),
                        details={"line": row_number},
                    )
                lcsc = row[lcsc_index].strip()
                if not lcsc:
                    self.add_error(
                        "bom_cpl",
                        "BOM_EMPTY_LCSC_PART",
                        "BOM LCSC part number must not be empty",
                        path=self.relative(bom_path),
                        details={"line": row_number},
                    )
                elif lcsc_regex.fullmatch(lcsc) is None:
                    self.add_error(
                        "bom_cpl",
                        "BOM_INVALID_LCSC_PART",
                        "LCSC part number does not match the configured format",
                        path=self.relative(bom_path),
                        details={"line": row_number, "value": lcsc},
                    )
                elif lcsc:
                    lcsc_values.add(lcsc)

        x_header = self.config["cpl_x_header"]
        y_header = self.config["cpl_y_header"]
        rotation_header = self.config["cpl_rotation_header"]
        side_header = self.config["cpl_side_header"]
        required_cpl_fields = {
            designator_header,
            x_header,
            y_header,
            rotation_header,
            side_header,
        }
        if required_cpl_fields.issubset(cpl_header):
            designator_index = cpl_header.index(designator_header)
            x_index = cpl_header.index(x_header)
            y_index = cpl_header.index(y_header)
            rotation_index = cpl_header.index(rotation_header)
            side_index = cpl_header.index(side_header)
            for row_number, row in enumerate(cpl_rows, start=2):
                refs = self._split_designators(row[designator_index])
                if not refs:
                    self.add_error(
                        "bom_cpl",
                        "CPL_EMPTY_DESIGNATOR",
                        "CPL row has no designator",
                        path=self.relative(cpl_path),
                        details={"line": row_number},
                    )
                if len(refs) > 1:
                    self.add_error(
                        "bom_cpl",
                        "CPL_GROUPED_DESIGNATOR",
                        "each CPL row must describe exactly one designator",
                        path=self.relative(cpl_path),
                        details={"line": row_number, "designators": refs},
                    )
                for reference in refs:
                    if designator_regex.fullmatch(reference) is None:
                        self.add_error(
                            "bom_cpl",
                            "CPL_INVALID_DESIGNATOR",
                            "CPL designator does not match the configured format",
                            path=self.relative(cpl_path),
                            details={"line": row_number, "designator": reference},
                        )
                    if reference in cpl_refs:
                        self.add_error(
                            "bom_cpl",
                            "CPL_DUPLICATE_DESIGNATOR",
                            "CPL designator occurs more than once",
                            path=self.relative(cpl_path),
                            details={"line": row_number, "designator": reference},
                        )
                    cpl_refs.add(reference)

                for field_name, field_index in (
                    (x_header, x_index),
                    (y_header, y_index),
                ):
                    value = row[field_index]
                    if not self._finite_decimal(value, allow_mm=True):
                        self.add_error(
                            "bom_cpl",
                            "CPL_INVALID_COORDINATE",
                            "CPL coordinate must be a finite decimal, optionally suffixed mm",
                            path=self.relative(cpl_path),
                            details={
                                "line": row_number,
                                "field": field_name,
                                "value": value,
                            },
                        )
                rotation = row[rotation_index]
                if not self._finite_decimal(rotation, allow_mm=False):
                    self.add_error(
                        "bom_cpl",
                        "CPL_INVALID_ROTATION",
                        "CPL rotation must be a finite decimal",
                        path=self.relative(cpl_path),
                        details={"line": row_number, "value": rotation},
                    )
                side = row[side_index].strip()
                if side not in self.config["allowed_cpl_sides"]:
                    self.add_error(
                        "bom_cpl",
                        "CPL_INVALID_SIDE",
                        "CPL side is not in the configured allowed set",
                        path=self.relative(cpl_path),
                        details={
                            "line": row_number,
                            "value": side,
                            "allowed": self.config["allowed_cpl_sides"],
                        },
                    )

        only_bom = sorted(bom_refs - cpl_refs)
        only_cpl = sorted(cpl_refs - bom_refs)
        if only_bom or only_cpl:
            self.add_error(
                "bom_cpl",
                "DESIGNATOR_SET_MISMATCH",
                "expanded BOM and CPL designator sets are not identical",
                details={"only_in_bom": only_bom, "only_in_cpl": only_cpl},
            )
        reference_digest = hashlib.sha256(
            "\n".join(sorted(bom_refs)).encode("utf-8")
        ).hexdigest()
        return {
            "bom_path": self.relative(bom_path),
            "cpl_path": self.relative(cpl_path),
            "bom_rows": len(bom_rows),
            "cpl_rows": len(cpl_rows),
            "designators": len(bom_refs),
            "unique_lcsc_parts": len(lcsc_values),
            "designator_set_sha256": reference_digest,
        }

    def cached_sha256(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved not in self.hash_cache:
            self.hash_cache[resolved] = _sha256(path)
        return self.hash_cache[resolved]

    def _validate_file_record(
        self,
        check: str,
        raw_path: str,
        expected_hash: str,
        *,
        expected_size: int | None = None,
    ) -> str | None:
        path, normalised = self.path_from_relative(raw_path, check, canonical=True)
        if path is None or normalised is None:
            return None
        if not path.is_file():
            self.add_error(
                check,
                "HASHED_FILE_MISSING",
                "listed file does not exist",
                path=normalised,
            )
            return normalised
        if path.is_symlink():
            self.add_error(
                check,
                "HASHED_FILE_SYMLINK",
                "listed file must not be a symbolic link",
                path=normalised,
            )
            return normalised
        try:
            actual_size = path.stat().st_size
            actual_hash = self.cached_sha256(path)
        except OSError as exc:
            self.add_error(check, "HASHED_FILE_READ_ERROR", str(exc), path=normalised)
            return normalised
        if expected_size is not None and actual_size != expected_size:
            self.add_error(
                check,
                "MANIFEST_SIZE_MISMATCH",
                "file size differs from MANIFEST",
                path=normalised,
                details={"expected": expected_size, "actual": actual_size},
            )
        if actual_hash.casefold() != expected_hash.casefold():
            code = {
                "manifest": "MANIFEST_HASH_MISMATCH",
                "sha256sums": "SHA256SUMS_HASH_MISMATCH",
                "package_hashes": "PACKAGE_HASHES_HASH_MISMATCH",
            }[check]
            self.add_error(
                check,
                code,
                "file SHA-256 differs from recorded value",
                path=normalised,
                details={"expected": expected_hash.casefold(), "actual": actual_hash},
            )
        return normalised

    def check_manifest(self) -> dict[str, Any]:
        raw_manifest = self.inputs.get("manifest")
        if raw_manifest is None:
            return {"skipped": True, "reason": "MANIFEST was not resolved"}
        manifest_path = self.root.joinpath(*raw_manifest.split("/"))
        if not manifest_path.is_file():
            return {"skipped": True, "reason": "MANIFEST was not resolved"}
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.add_error(
                "manifest",
                "MANIFEST_READ_ERROR",
                f"MANIFEST JSON cannot be read: {exc}",
                path=raw_manifest,
            )
            return {"path": raw_manifest, "entries": 0}
        if not isinstance(document, dict) or not isinstance(
            document.get("files"), dict
        ):
            self.add_error(
                "manifest",
                "MANIFEST_SCHEMA_ERROR",
                "MANIFEST must be an object containing a files object",
                path=raw_manifest,
            )
            return {"path": raw_manifest, "entries": 0}

        entries: dict[str, Any] = document["files"]
        if not entries:
            self.add_error(
                "manifest",
                "MANIFEST_EMPTY",
                "MANIFEST files object is empty",
                path=raw_manifest,
            )
        seen: dict[str, str] = {}
        for raw_path, record in entries.items():
            if not isinstance(raw_path, str) or not isinstance(record, dict):
                self.add_error(
                    "manifest",
                    "MANIFEST_SCHEMA_ERROR",
                    "each MANIFEST files entry must map a path string to an object",
                    path=str(raw_path),
                )
                continue
            size = record.get("bytes", record.get("size"))
            expected_hash = record.get("sha256", record.get("hash"))
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                self.add_error(
                    "manifest",
                    "MANIFEST_SCHEMA_ERROR",
                    "file record requires a non-negative integer bytes (or size)",
                    path=raw_path,
                )
                continue
            if (
                not isinstance(expected_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
            ):
                self.add_error(
                    "manifest",
                    "MANIFEST_SCHEMA_ERROR",
                    "file record requires a 64-hex sha256 (or hash)",
                    path=raw_path,
                )
                continue
            normalised, path_error = _normalise_relative(raw_path)
            if path_error or normalised is None:
                self.add_error(
                    "manifest",
                    "UNSAFE_PATH",
                    path_error or "invalid path",
                    path=raw_path,
                )
                continue
            collision_key = normalised.casefold()
            if collision_key in seen:
                self.add_error(
                    "manifest",
                    "MANIFEST_DUPLICATE_PATH",
                    "duplicate or case-colliding MANIFEST path",
                    path=raw_path,
                    details={"first": seen[collision_key]},
                )
                continue
            seen[collision_key] = raw_path
            validated = self._validate_file_record(
                "manifest", raw_path, expected_hash, expected_size=size
            )
            if validated is not None:
                self.manifest_entries[validated] = expected_hash.casefold()
        return {"path": raw_manifest, "entries": len(entries)}

    def _parse_checksum_file(self, role: str, input_key: str) -> dict[str, str]:
        raw_list_path = self.inputs.get(input_key)
        if raw_list_path is None:
            return {}
        list_path = self.root.joinpath(*raw_list_path.split("/"))
        if not list_path.is_file():
            return {}
        try:
            lines = list_path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            self.add_error(
                role,
                f"{role.upper()}_READ_ERROR",
                f"checksum file cannot be read: {exc}",
                path=raw_list_path,
            )
            return {}

        entries: dict[str, str] = {}
        case_paths: dict[str, str] = {}
        for line_number, line in enumerate(lines, start=1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
            if match is None:
                self.add_error(
                    role,
                    f"{role.upper()}_LINE_INVALID",
                    "checksum line must contain lowercase SHA-256, two spaces, and a relative path",
                    path=raw_list_path,
                    details={"line": line_number},
                )
                continue
            expected_hash, raw_path = match.groups()
            normalised, path_error = _normalise_relative(raw_path)
            if path_error or normalised is None or raw_path != normalised:
                self.add_error(
                    role,
                    "NON_CANONICAL_PATH" if not path_error else "UNSAFE_PATH",
                    path_error or "path must use canonical forward-slash relative form",
                    path=raw_path,
                    details={"line": line_number},
                )
                continue
            collision_key = normalised.casefold()
            if collision_key in case_paths:
                self.add_error(
                    role,
                    f"{role.upper()}_DUPLICATE_PATH",
                    "duplicate or case-colliding checksum path",
                    path=normalised,
                    details={"line": line_number, "first": case_paths[collision_key]},
                )
                continue
            case_paths[collision_key] = normalised
            validated = self._validate_file_record(role, normalised, expected_hash)
            if validated is not None:
                entries[validated] = expected_hash.casefold()
        if not entries:
            self.add_error(
                role,
                f"{role.upper()}_EMPTY",
                "checksum file contains no valid entries",
                path=raw_list_path,
            )
        return entries

    def check_sha256sums(self) -> dict[str, Any]:
        self.sha_entries = self._parse_checksum_file("sha256sums", "sha256sums")
        if self.config["require_manifest_files_in_sha256sums"]:
            missing = sorted(set(self.manifest_entries) - set(self.sha_entries))
            if missing:
                self.add_error(
                    "sha256sums",
                    "SHA256SUMS_MISSING_MANIFEST_ENTRY",
                    "SHA256SUMS does not cover every MANIFEST file",
                    details={"missing": missing},
                )
        if self.config["require_manifest_in_sha256sums"]:
            manifest_path = self.inputs.get("manifest")
            if manifest_path is not None and manifest_path not in self.sha_entries:
                self.add_error(
                    "sha256sums",
                    "SHA256SUMS_MISSING_MANIFEST",
                    "SHA256SUMS must include the MANIFEST itself",
                    path=manifest_path,
                )
        return {"path": self.inputs.get("sha256sums"), "entries": len(self.sha_entries)}

    def check_package_hashes(self) -> dict[str, Any]:
        self.package_entries = self._parse_checksum_file(
            "package_hashes", "package_hashes"
        )
        required = {
            value
            for key, value in self.inputs.items()
            if key in {"gerber_zip", "bom_csv", "cpl_csv"} and value is not None
        }
        if self.config["require_all_zips_in_package_hashes"]:
            required.update(self.relative(path) for path in self.zip_paths)
        missing = sorted(required - set(self.package_entries))
        if missing:
            self.add_error(
                "package_hashes",
                "PACKAGE_HASHES_MISSING_REQUIRED",
                "PACKAGE_HASHES does not cover every upload artifact and ZIP archive",
                details={"missing": missing},
            )
        return {
            "path": self.inputs.get("package_hashes"),
            "entries": len(self.package_entries),
            "required_entries": len(required),
        }

    def run(self) -> dict[str, Any]:
        self.run_check("inputs", self.check_inputs)
        self.run_check("zip_integrity", self.check_zip_integrity)
        self.run_check("gerber_archive", self.check_gerber_archive)
        self.run_check("bom_cpl", self.check_bom_cpl)
        self.run_check("manifest", self.check_manifest)
        self.run_check("sha256sums", self.check_sha256sums)
        self.run_check("package_hashes", self.check_package_hashes)

        has_internal_error = any(
            error["code"] == "AUDITOR_EXCEPTION" for error in self.errors
        )
        status_text = (
            "ERROR" if has_internal_error else ("FAIL" if self.errors else "PASS")
        )
        counts = {
            value: sum(check["status"] == value for check in self.checks)
            for value in ("PASS", "FAIL", "ERROR", "SKIP")
        }
        return {
            "schema": SCHEMA_VERSION,
            "status": status_text,
            "root": str(self.root),
            "config": str(self.config_path) if self.config_path else None,
            "inputs": self.inputs,
            "summary": {
                "checks": len(self.checks),
                **{key.casefold(): value for key, value in counts.items()},
                "errors": len(self.errors),
            },
            "checks": self.checks,
            "errors": self.errors,
        }


def audit_package(
    root: Path | str,
    config: dict[str, Any] | None = None,
    config_path: Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    if not root_path.exists() or not root_path.is_dir():
        raise ConfigurationError(f"handoff root is not a directory: {root_path}")
    return Auditor(root_path, _validated_config(config), config_path).run()


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ConfigurationError(message)


def _error_report(message: str) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "status": "ERROR",
        "summary": {
            "checks": 0,
            "pass": 0,
            "fail": 0,
            "error": 1,
            "skip": 0,
            "errors": 1,
        },
        "checks": [],
        "errors": [
            {"check": "invocation", "code": "INVOCATION_ERROR", "message": message}
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("handoff_root", help="root directory of the JLCPCB handoff")
    parser.add_argument("--config", type=Path, help="optional JSON configuration")
    parser.add_argument("--pretty", action="store_true", help="indent the JSON report")
    try:
        args = parser.parse_args(argv)
        config = _load_config(args.config)
        report = audit_package(args.handoff_root, config, args.config)
        exit_code = (
            2
            if report["status"] == "ERROR"
            else (1 if report["status"] == "FAIL" else 0)
        )
    except ConfigurationError as exc:
        report = _error_report(str(exc))
        exit_code = 2
        args = argparse.Namespace(
            pretty="--pretty" in (argv if argv is not None else sys.argv[1:])
        )
    except (
        Exception
    ) as exc:  # Keep stdout machine-readable even on an unexpected fault.
        report = _error_report(
            f"unexpected auditor failure: {type(exc).__name__}: {exc}"
        )
        report["errors"][0]["code"] = "AUDITOR_FATAL"
        exit_code = 2
        args = argparse.Namespace(
            pretty="--pretty" in (argv if argv is not None else sys.argv[1:])
        )

    json.dump(
        report,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        sort_keys=True,
    )
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
