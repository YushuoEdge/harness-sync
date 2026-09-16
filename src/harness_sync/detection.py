"""Optional read-only discovery helpers for native adapters.

A located executable is not a supported installation. Adapters must independently
validate version/schema capabilities and isolate probes with native home overrides
when their CLI initializes files during --version/--help.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .errors import UnsupportedError
from .paths import absolute


@dataclass(frozen=True)
class ProbeResult:
    returncode: int
    stdout: str = field(repr=False)
    stderr: str = field(repr=False)


def find_executable(
    command: str, environment: Mapping[str, str], explicit: str | None = None
) -> Path | None:
    candidates = (
        [absolute(explicit)]
        if explicit
        else [
            absolute(directory) / command
            for directory in environment.get("PATH", "").split(os.pathsep)
            if directory
        ]
    )
    for path in candidates:
        if not path.is_file() or not os.access(path, os.X_OK):
            continue
        with path.open("rb") as stream:
            if b"harness-sync managed wrapper" in stream.read(256):
                continue
        return path.resolve()
    return None


def probe(
    executable: Path,
    arguments: tuple[str, ...],
    environment: Mapping[str, str],
    timeout: float = 5.0,
) -> ProbeResult:
    try:
        result = subprocess.run(
            (str(executable), *arguments),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise UnsupportedError("Native capability probe failed or timed out") from None
    return ProbeResult(result.returncode, result.stdout, result.stderr)
