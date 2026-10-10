"""Small exclusive-create helpers with file and parent-directory durability."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


class DurableWriteError(OSError):
    """A durable file could not be created before any bytes were committed."""


class DurableWriteOutcomeUnknown(DurableWriteError):
    """Exclusive creation occurred but file/directory durability is uncertain."""

    def __init__(self, detail: str, *, path: Path) -> None:
        super().__init__(detail)
        self.path = path


def ensure_directory_tree_durable(directory: Path, *, root: Path) -> Path:
    """Create a directory tree below ``root`` and sync every new parent entry.

    This is deliberately separate from a later exclusive file create: failure
    here is still pre-claim, while failure after the claim file is created has
    an unknown durable outcome and must be handled as terminal.
    """

    root_path = root.resolve(strict=True)
    if not root_path.is_dir() or root_path.is_symlink():
        raise OSError(f"durable directory root is not a regular directory: {root_path}")
    if not directory.is_absolute():
        raise OSError("durable directory target must be absolute")
    target = directory
    try:
        relative = target.relative_to(root_path)
    except ValueError as error:
        raise OSError(f"durable directory escapes its root: {target}") from error
    current = root_path
    for component in relative.parts:
        if component in {"", ".", ".."}:
            raise OSError(f"durable directory contains unsafe component: {component!r}")
        candidate = current / component
        if candidate.exists() or candidate.is_symlink():
            if candidate.is_symlink() or not candidate.is_dir():
                raise OSError(
                    f"durable directory component is not a regular directory: {candidate}"
                )
        else:
            try:
                os.mkdir(candidate, 0o700)
            except FileExistsError:
                if candidate.is_symlink() or not candidate.is_dir():
                    raise OSError(
                        "durable directory component was concurrently replaced: "
                        f"{candidate}"
                    )
            fsync_directory(current)
        current = candidate
    return current.resolve(strict=True)


def fsync_directory(directory: Path) -> None:
    """Flush one existing directory on POSIX or Windows."""

    root = directory.resolve(strict=True)
    if not root.is_dir():
        raise OSError(f"directory fsync target is not a directory: {root}")
    if os.name != "nt":
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        descriptor = os.open(root, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    create_file.restype = ctypes.c_void_p
    flush = kernel32.FlushFileBuffers
    flush.argtypes = [ctypes.c_void_p]
    flush.restype = ctypes.c_int
    close = kernel32.CloseHandle
    close.argtypes = [ctypes.c_void_p]
    close.restype = ctypes.c_int
    handle = create_file(
        str(root),
        0x40000000,  # GENERIC_WRITE
        0x00000001 | 0x00000002 | 0x00000004,  # share read/write/delete
        None,
        3,  # OPEN_EXISTING
        0x02000000,  # FILE_FLAG_BACKUP_SEMANTICS
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in {None, invalid}:
        code = ctypes.get_last_error()
        raise OSError(code, f"CreateFileW failed for directory {root}")
    try:
        if not flush(handle):
            code = ctypes.get_last_error()
            raise OSError(code, f"FlushFileBuffers failed for directory {root}")
    finally:
        close(handle)


def write_new_bytes_durable(path: Path, payload: bytes, *, mode: int = 0o600) -> str:
    """Create one file exclusively and durably commit its directory entry."""

    import hashlib

    if not isinstance(path, Path) or not path.name:
        raise DurableWriteError("durable output must be an explicit file path")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as error:
        raise DurableWriteError(f"durable output parent is unavailable: {error}") from error
    if not parent.is_dir():
        raise DurableWriteError("durable output parent must be a directory")
    destination = parent / path.name
    if destination.exists() or destination.is_symlink():
        raise DurableWriteError("durable output already exists; refusing overwrite")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        descriptor = os.open(destination, flags, mode)
    except FileExistsError as error:
        raise DurableWriteError(
            "durable output already exists; refusing overwrite"
        ) from error
    except OSError as error:
        raise DurableWriteError(f"cannot exclusively create durable output: {error}") from error
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        fsync_directory(parent)
    except OSError as error:
        raise DurableWriteOutcomeUnknown(
            f"durable output commit is uncertain: {error}", path=destination
        ) from error
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "DurableWriteError",
    "DurableWriteOutcomeUnknown",
    "ensure_directory_tree_durable",
    "fsync_directory",
    "write_new_bytes_durable",
]
