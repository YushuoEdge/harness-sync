from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from harness_sync.config import yaml_bytes
from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.engine import Engine
from harness_sync.filesystem import replace
from harness_sync.merge import merge_fields
from harness_sync.paths import Paths
from harness_sync.registry import Registry
from harness_sync.schema import SecretRef


def document(alias="one", key="one"):
    return {
        "version": 1,
        "providers": [
            {
                "name": alias,
                "type": "openai-chat",
                "base_url": f"https://{alias}.invalid/v1",
                "api_key": {"secret": key},
                "models": [
                    {"name": "same-label", "id": f"vendor/{alias}-{role}", "role": role}
                    for role in ("simple", "daily", "complex")
                ],
            }
        ],
    }


class FakeAdapter(Adapter):
    """Only test fixture; never registered in the installed CLI."""

    id = "fake"
    command = "fake-agent"
    protocols = frozenset({"openai-chat"})

    def __init__(self, root: Path):
        self.root = root
        self.fail_verify = False
        self.escape = False
        self.bad_argv = False

    def detect(self, context):
        return Detection(
            self.id,
            "installed",
            Path(sys.executable),
            "test-1",
            default_paths=(self.root / "native.json",),
        )

    def profiles(self, provider, context):
        path = context.paths.profile(self.id, provider.command_alias) / "profile.json"
        if self.escape:
            path = context.detection.default_paths[0]

        def render(secrets):
            return json.dumps(
                {
                    "endpoint": provider.base_url,
                    "models": {m.role: m.upstream_id(self.id) for m in provider.models},
                    "key": secrets.get(provider.api_key.secret),
                }
            ).encode()

        def verify(data):
            json.loads(data)
            if self.fail_verify:
                raise ValueError("native syntax rejected")

        return (Artifact(path, "profile", f"fake/{provider.name}", render, verify),)

    def defaults(self, providers, selected, role, context):
        path = context.detection.default_paths[0]
        current = context.read(path)
        baseline = context.baseline(path)

        def render(secrets):
            merged = merge_fields(
                json.loads(current or b"{}"),
                json.loads(baseline) if baseline else None,
                {
                    ("model",): selected.model_for(role).upstream_id(self.id),
                    ("key",): secrets.get(selected.api_key.secret),
                },
            )
            return json.dumps(merged).encode()

        return (Artifact(path, "default", "fake/default", render, json.loads, merged=True),)

    def launch(self, provider, role, arguments, context, secrets):
        assert isinstance(provider.api_key, SecretRef)
        key = secrets.get(provider.api_key.secret)
        return LaunchSpec(
            arguments + ((key,) if self.bad_argv else ()),
            {
                "TEST_KEY": key,
                "TEST_MODEL": provider.model_for(role).upstream_id(self.id),
                "TEST_ENDPOINT": provider.endpoint_for(self.id),
            },
            frozenset({"STALE_KEY"}),
        )


@pytest.fixture
def project(tmp_path):
    paths = Paths(tmp_path / "config/config.yaml", tmp_path / "state")
    config = document()
    config["commands"] = {"bin_dir": str(tmp_path / "bin")}
    replace(paths.config, yaml_bytes(config))
    replace(
        paths.config.parent / "secrets.yaml",
        yaml_bytes(
            {
                "version": 1,
                "keys": {"one": "s3cr3t-one", "two": "s3cr3t-two"},
            }
        ),
    )
    adapter = FakeAdapter(tmp_path)
    engine = Engine(paths, Registry((adapter,)))
    return engine, adapter, config
