import importlib
import json
import sys
from pathlib import Path

import pytest

from harness_sync.contracts import Detection, DetectionContext, RenderContext
from harness_sync.detection import ProbeResult
from harness_sync.errors import ConflictError, HarnessSyncError
from harness_sync.paths import Paths
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore

native = importlib.import_module("harnesses.claude-code.adapter")


def provider(name="one"):
    return Provider.model_validate(
        {
            "name": name,
            "type": "anthropic",
            "base_url": f"https://{name}.invalid",
            "api_key": {"secret": name},
            "models": [
                {"name": "label", "id": f"vendor/{name}-{r}", "role": r}
                for r in ("simple", "daily", "complex")
            ],
        }
    )


def context(tmp_path, current=None, baseline=None):
    return RenderContext(
        Paths(tmp_path / "config.yaml", tmp_path / "state"),
        Detection(
            "claude-code",
            "installed",
            executable=Path(sys.executable),
            version=native.VERSION,
            default_paths=(tmp_path / "native/settings.json",),
            capabilities=("settings-overlay",),
        ),
        HarnessSettings(),
        lambda p: current,
        lambda p: baseline,
    )


@pytest.mark.parametrize("role", ["simple", "daily", "complex"])
def test_roles_and_credentials(tmp_path, role):
    p = provider()
    adapter = native.create_adapter()
    ctx = context(tmp_path)
    keys = SecretStore({"one": "test-one", "two": "test-two"})
    adapter.validate(p, ctx)
    artifacts = adapter.profiles(p, ctx)
    assert len(artifacts) == 3
    for artifact in artifacts:
        artifact.verify(artifact.render(keys))
        assert artifact.scope == "profile" and artifact.mode == 0o600
        assert artifact.path != ctx.detection.default_paths[0]
    spec = adapter.launch(p, role, ("-p", "prompt with 'quotes'"), ctx, keys)
    assert spec.argv[-2:] == ("-p", "prompt with 'quotes'")
    assert spec.argv[3] == f"vendor/one-{role}"
    assert "test-one" not in " ".join(spec.argv)
    assert spec.environment["ANTHROPIC_API_KEY"] == "test-one"
    other = adapter.launch(provider("two"), role, (), ctx, keys)
    assert other.environment["ANTHROPIC_BASE_URL"] == "https://two.invalid"
    assert other.environment["ANTHROPIC_API_KEY"] == "test-two"
    assert "ANTHROPIC_AUTH_TOKEN" in spec.unset


def test_defaults_preservation_rotation_conflict(tmp_path):
    p, a = provider(), native.create_adapter()
    initial = a.defaults((p,), p, "daily", context(tmp_path, b'{"permissions":{"allow":[]}}'))[0]
    data = initial.render(SecretStore({"one": "old-key"}))
    assert json.loads(data)["permissions"] == {"allow": []}
    rotated = a.defaults((p,), p, "daily", context(tmp_path, data, data))[0].render(
        SecretStore({"one": "new-key"})
    )
    assert b"new-key" in rotated and b"old-key" not in rotated
    changed = data.replace(b"vendor/one-daily", b"manual-edit")
    with pytest.raises(ConflictError):
        a.defaults((p,), p, "daily", context(tmp_path, changed, data))[0].render(
            SecretStore({"one": "old-key"})
        )


@pytest.mark.parametrize("flag", ["--settings=x", "--settings", "--cloud", "--agent"])
def test_rejects_routing(tmp_path, flag):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", (flag,), context(tmp_path), SecretStore({"one": "test-key"})
        )


def test_version_fixtures_fail_closed(monkeypatch, tmp_path):
    fixtures = Path(__file__).parents[1] / "fixtures"
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/claude"))
    responses = [
        ProbeResult(0, (fixtures / f"claude-{native.VERSION}-{kind}.txt").read_text(), "")
        for kind in ("version", "help")
    ]
    for unknown in (False, True):
        values = iter(
            responses if not unknown else [ProbeResult(0, "9.0.0 (Claude Code)", ""), responses[1]]
        )
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        result = native.create_adapter().detect(DetectionContext(HarnessSettings(), {}))
        assert result.status == ("unsupported-version" if unknown else "installed")


def test_engine_profile_only_sync_and_rotation(monkeypatch, tmp_path):
    from harness_sync.config import yaml_bytes
    from harness_sync.engine import Engine, Selection
    from harness_sync.filesystem import replace
    from harness_sync.registry import Registry

    adapter = native.create_adapter()
    ctx = context(tmp_path)
    monkeypatch.setattr(adapter, "detect", lambda _: ctx.detection)
    replace(
        ctx.paths.config,
        yaml_bytes(
            {
                "version": 1,
                "providers": [provider().model_dump(exclude_none=True)],
                "commands": {"bin_dir": str(tmp_path / "bin")},
            }
        ),
    )
    replace(tmp_path / "secrets.yaml", yaml_bytes({"version": 1, "keys": {"one": "test-one"}}))
    default = ctx.detection.default_paths[0]
    replace(default, b'{"permissions":{"allow":[]}}')
    before = default.read_bytes()
    engine = Engine(ctx.paths, Registry((adapter,)))
    selection = Selection((adapter.id,), profiles_only=True, commands=False)
    engine.sync(selection)
    assert default.read_bytes() == before
    files = [a.path for a in adapter.profiles(provider(), ctx)]
    times = [p.stat().st_mtime_ns for p in files]
    engine.sync(selection)
    assert [p.stat().st_mtime_ns for p in files] == times
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in files)
    replace(tmp_path / "secrets.yaml", yaml_bytes({"version": 1, "keys": {"one": "rotated-key"}}))
    engine.sync(selection)
    assert all(b"rotated-key" in p.read_bytes() for p in files)
    assert default.read_bytes() == before
