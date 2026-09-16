from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def absolute(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base or Path.cwd()) / path
    # Do not resolve symlinks: the filesystem boundary must see and reject them.
    return Path(os.path.abspath(path))


@dataclass(frozen=True)
class Paths:
    config: Path
    state: Path

    @classmethod
    def discover(cls, config: str | None = None, state: str | None = None) -> Paths:
        conf_root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        state_root = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        return cls(
            absolute(config or conf_root / "harness-sync/config.yaml"),
            absolute(state or state_root / "harness-sync"),
        )

    @property
    def generated(self) -> Path:
        return self.config.parent / "generated"

    def profile(self, harness: str, alias: str) -> Path:
        return self.generated / "profiles" / harness / alias

    def runtime(self, harness: str, alias: str) -> Path:
        return self.state / "runtime" / harness / alias
