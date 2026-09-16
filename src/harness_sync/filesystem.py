"""Small POSIX filesystem boundary shared by the store and transaction engine."""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConflictError


def check_path(path: Path) -> None:
    if not path.is_absolute():
        raise ConflictError("Filesystem targets must be absolute")
    for item in [*reversed(path.parents), path]:
        if item.is_symlink():
            raise ConflictError("Refusing a symlink in a managed path")


def private_dir(path: Path) -> None:
    check_path(path)
    if not path.exists():
        private_dir(path.parent)
        path.mkdir(mode=0o700, exist_ok=True)
    if not path.is_dir():
        raise ConflictError("Expected a directory")


@dataclass(frozen=True)
class Snapshot:
    data: bytes | None = field(repr=False)
    mode: int | None = None


def snapshot(path: Path) -> Snapshot:
    check_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return Snapshot(None)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ConflictError("Refusing a non-regular configuration file")
        return Snapshot(stream.read(), stat.S_IMODE(info.st_mode))


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage(path: Path, data: bytes, mode: int = 0o600) -> Path:
    check_path(path)
    private_dir(path.parent)
    fd, temporary = tempfile.mkstemp(prefix=".harness-sync-", dir=path.parent)
    tmp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return tmp
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def replace(path: Path, data: bytes, mode: int = 0o600) -> None:
    temporary = stage(path, data, mode)
    try:
        check_path(path)
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)
