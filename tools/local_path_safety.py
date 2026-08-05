"""Fail-closed lexical guards for local regular-file tooling on Windows.

These checks run before any path resolution or file open.  In particular,
Win32 DOS device names such as ``COM8`` remain devices even when an extension
is appended, and UNC/device namespaces may perform network or device I/O.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path, PureWindowsPath
import re


class LocalPathSafetyError(ValueError):
    """Raised when a path could address a device, stream, or network share."""


_RESERVED_WINDOWS_BASENAME = re.compile(
    r"(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])",
    re.IGNORECASE,
)
_DRIVE_REMOTE = 4


def require_local_regular_path_syntax(path: Path, *, label: str) -> None:
    """Reject non-local namespaces, DOS devices, ADS and ambiguous aliases."""

    if not isinstance(path, Path):
        raise LocalPathSafetyError(f"{label} must be a pathlib.Path")
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw:
        raise LocalPathSafetyError(f"{label} must be a non-empty text path")
    if any(ord(character) < 0x20 for character in raw):
        raise LocalPathSafetyError(f"{label} must not contain control characters")

    windows = PureWindowsPath(raw)
    normalized = raw.replace("/", "\\")
    if normalized.startswith("\\\\") or windows.drive.startswith("\\\\"):
        raise LocalPathSafetyError(
            f"{label} must not use a UNC or Windows device namespace"
        )
    # POSIX absolute paths such as /tmp/file look root-relative to
    # PureWindowsPath.  Drive/root ambiguity is therefore Windows-specific,
    # while device basenames, ADS text and aliasing components are rejected
    # portably so an artifact cannot later become hazardous when moved.
    if os.name == "nt":
        if windows.drive and not windows.root:
            raise LocalPathSafetyError(f"{label} must not use a drive-relative path")
        if windows.root and not windows.drive:
            raise LocalPathSafetyError(f"{label} must not use a root-relative path")

    for component in windows.parts:
        if component in (windows.anchor, windows.drive, windows.root, "\\", "/"):
            continue
        if ":" in component:
            raise LocalPathSafetyError(
                f"{label} must not use an NTFS alternate data stream"
            )
        if component.rstrip(" .") != component:
            raise LocalPathSafetyError(
                f"{label} components must not end in a space or dot"
            )
        # Win32 strips spaces/dots from the basename before resolving legacy
        # DOS devices, including aliases such as ``COM8 .txt``.
        basename = component.split(".", 1)[0].rstrip(" .")
        if _RESERVED_WINDOWS_BASENAME.fullmatch(basename) is not None:
            raise LocalPathSafetyError(
                f"{label} must not use a reserved Windows device name"
            )

    if os.name == "nt" and windows.drive and windows.root:
        drive_root = f"{windows.drive}\\"
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive_root)
        except (AttributeError, OSError) as error:
            raise LocalPathSafetyError(
                f"could not verify that {label} is on a local drive"
            ) from error
        if drive_type == _DRIVE_REMOTE:
            raise LocalPathSafetyError(f"{label} must not use a mapped network drive")
        if drive_type in (0, 1):
            raise LocalPathSafetyError(f"could not verify that {label} is on a local drive")
