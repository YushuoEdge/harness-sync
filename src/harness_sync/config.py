"""YAML input boundary: no custom tags, duplicate keys or value-bearing errors."""

from __future__ import annotations

import io
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML

from .errors import HarnessSyncError
from .schema import Config


def parse_yaml(data: bytes) -> object:
    yaml = YAML(typ="safe", pure=True)
    yaml.allow_duplicate_keys = False
    try:
        return yaml.load(data.decode("utf-8"))
    except Exception:
        raise HarnessSyncError("Invalid YAML (check syntax, duplicate keys and tags)") from None


def yaml_bytes(value: object) -> bytes:
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    out = io.StringIO()
    yaml.dump(value, out)
    return out.getvalue().encode()


def parse_config(data: bytes) -> Config:
    try:
        return Config.model_validate(parse_yaml(data))
    except ValidationError:
        # Pydantic error locations can themselves contain user-supplied secrets.
        raise HarnessSyncError("Invalid configuration; check the canonical schema") from None


def load_config(path: Path) -> Config:
    try:
        return parse_config(path.read_bytes())
    except OSError:
        raise HarnessSyncError("Cannot read configuration file") from None
