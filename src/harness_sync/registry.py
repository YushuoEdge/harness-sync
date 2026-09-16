"""Load only packaged adapter modules; unimplemented slots are explicit."""

from __future__ import annotations

import importlib
import json
import shutil
from importlib.resources import files

from .contracts import Adapter, Detection, DetectionContext
from .errors import HarnessSyncError
from .paths import absolute


class Registry:
    def __init__(self, adapters: tuple[Adapter, ...] = (), catalog: dict[str, str] | None = None):
        self.adapters = {adapter.id: adapter for adapter in adapters}
        if len(self.adapters) != len(adapters):
            raise HarnessSyncError("Duplicate adapter registration")
        self.catalog = dict(catalog or {adapter.id: adapter.command for adapter in adapters})
        for adapter in adapters:
            if self.catalog.get(adapter.id) != adapter.command:
                raise HarnessSyncError("Adapter identity does not match its manifest")

    @classmethod
    def bundled(cls) -> Registry:
        catalog: dict[str, str] = {}
        adapters = []
        for directory in sorted(files("harnesses").iterdir(), key=lambda p: p.name):
            manifest = directory.joinpath("adapter.json")
            if not manifest.is_file():
                continue
            data = json.loads(manifest.read_text())
            ident, command = data["id"], data["command"]
            if ident != directory.name:
                raise HarnessSyncError("Adapter manifest directory mismatch")
            catalog[ident] = command
            if directory.joinpath("adapter.py").is_file():
                module = importlib.import_module(f"harnesses.{ident}.adapter")
                adapter = module.create_adapter()
                if not isinstance(adapter, Adapter):
                    raise HarnessSyncError("Bundled adapter does not implement the public contract")
                adapters.append(adapter)
        return cls(tuple(adapters), catalog)

    def detect(self, ident: str, context: DetectionContext) -> Detection:
        if ident not in self.catalog:
            raise HarnessSyncError("Unknown harness selection")
        adapter = self.adapters.get(ident)
        if adapter is not None:
            result = adapter.detect(context)
            if result.harness != ident:
                raise HarnessSyncError("Adapter detection identity mismatch")
            return result
        candidate = context.settings.executable or shutil.which(
            self.catalog[ident], path=context.environment.get("PATH", "")
        )
        # Finding a binary is not evidence that an adapter exists or a version works.
        return Detection(ident, "not-implemented", absolute(candidate) if candidate else None)

    def select(self, selections: tuple[str, ...]) -> tuple[str, ...]:
        tokens = [p for item in selections for p in item.split(",")]
        if not tokens or tokens == ["all"]:
            return tuple(sorted(self.catalog))
        if "all" in tokens or any(t not in self.catalog for t in tokens):
            raise HarnessSyncError("Invalid harness selection")
        return tuple(dict.fromkeys(tokens))
