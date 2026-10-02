import importlib
import sys
import tomllib
from pathlib import Path

import pytest

from harness_sync.contracts import Detection, DetectionContext, RenderContext
from harness_sync.detection import ProbeResult
from harness_sync.errors import ConflictError, HarnessSyncError
from harness_sync.paths import Paths
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore

native = importlib.import_module("harnesses.kimi-code.adapter")


def provider(name="one", protocol="openai-chat"):
    return Provider.model_validate(
        {
            "name": name,
            "type": protocol,
            "base_url": f"https://{name}.invalid/v1",
            "api_key": {"secret": name},
            "models": [
                {"name": "same", "id": f"vendor/{name}-{r}", "role": r, "context_window": 128000}
                for r in ("simple", "daily", "complex")
            ],
        }
    )


def context(tmp_path, current=None, baseline=None):
    return RenderContext(
        Paths(tmp_path / "config.yaml", tmp_path / "state"),
        Detection(
            "kimi-code",
            "installed",
            Path(sys.executable),
            native.VERSION,
            default_paths=(tmp_path / "native/config.toml",),
            capabilities=("code-home",),
        ),
        HarnessSettings(),
        lambda p: current,
        lambda p: baseline,
    )


@pytest.mark.parametrize("protocol", native.APIS)
def test_profiles_and_roles(tmp_path, protocol):
    a, p, ctx = native.create_adapter(), provider(protocol=protocol), context(tmp_path)
    keys = SecretStore({"one": "test-one"})
    a.validate(p, ctx)
    artifact = a.profiles(p, ctx)[0]
    data = artifact.render(keys)
    artifact.verify(data)
    doc = tomllib.loads(data.decode())
    assert doc["providers"]["hs-one"]["type"] == native.APIS[protocol]
    assert doc["providers"]["hs-one"]["api_key"] == "test-one"
    for role in ("simple", "daily", "complex"):
        assert doc["models"]["hs-one-" + role]["model"] == f"vendor/one-{role}"
        spec = a.launch(p, role, ("--prompt", "prompt with quotes'"), ctx, keys)
        assert spec.argv[1] == "hs-one-" + role
        assert spec.environment["KIMI_CODE_HOME"].endswith("kimi-code/one")
        assert "OPENAI_BASE_URL" in spec.unset and "OPENAI_API_KEY" in spec.unset
        assert "test-one" not in str(spec.argv)


def test_required_metadata_and_unsupported_options(tmp_path):
    p = provider()
    a = native.create_adapter()
    for updates in (
        {"context_window": None},
        {"max_output_tokens": 100},
        {"reasoning_effort": "high"},
    ):
        changed = p.model_copy(
            update={"models": [p.models[0].model_copy(update=updates), *p.models[1:]]}
        )
        with pytest.raises(HarnessSyncError):
            a.validate(changed, context(tmp_path))


def test_defaults_comments_rotation_and_conflicts(tmp_path):
    a, p = native.create_adapter(), provider()
    current = b'# preserve\ntheme="dark"\n[providers.keep]\napi_key="existing"\n'
    data = a.defaults((p,), p, "daily", context(tmp_path, current))[0].render(
        SecretStore({"one": "old-key"})
    )
    assert b"# preserve" in data
    assert tomllib.loads(data.decode())["providers"]["keep"]["api_key"] == "existing"
    rotated = a.defaults((p,), p, "daily", context(tmp_path, data, data))[0].render(
        SecretStore({"one": "new-key"})
    )
    assert b"new-key" in rotated and b"old-key" not in rotated
    changed = data.replace(b"vendor/one-daily", b"manual")
    with pytest.raises(ConflictError):
        a.defaults((p,), p, "daily", context(tmp_path, changed, data))[0].render(
            SecretStore({"one": "old-key"})
        )


@pytest.mark.parametrize(
    "flag", ["--config=x", "--config-file", "-mother", "--model=x", "--agent-file"]
)
def test_routing_flags(tmp_path, flag):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", (flag,), context(tmp_path), SecretStore({"one": "key"})
        )


def test_detect_code_home_and_unknown_version(monkeypatch, tmp_path):
    fixtures = Path(__file__).parents[1] / "fixtures"
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/kimi"))
    help_text = (fixtures / f"kimi-{native.VERSION}-help.txt").read_text()
    for number, expected in [(native.VERSION, "installed"), ("9.9.9", "unsupported-version")]:
        values = iter(
            [ProbeResult(0, number, ""), ProbeResult(0, help_text, "")]
        )
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        result = native.create_adapter().detect(
            DetectionContext(HarnessSettings(), {"HOME": str(tmp_path)})
        )
        assert result.status == expected
        assert result.default_paths == (tmp_path / ".kimi-code/config.toml",)


def test_engine_profile_only_rotation(monkeypatch, tmp_path):
    from harness_sync.config import yaml_bytes
    from harness_sync.engine import Engine, Selection
    from harness_sync.filesystem import replace
    from harness_sync.registry import Registry

    a, p, ctx = native.create_adapter(), provider(), context(tmp_path)
    monkeypatch.setattr(a, "detect", lambda _: ctx.detection)
    replace(
        ctx.paths.config, yaml_bytes({"version": 1, "providers": [p.model_dump(exclude_none=True)]})
    )
    replace(tmp_path / "secrets.yaml", yaml_bytes({"version": 1, "keys": {"one": "test-one"}}))
    engine = Engine(ctx.paths, Registry((a,)))
    selection = Selection((a.id,), profiles_only=True, commands=False)
    engine.sync(selection)
    file = a.profiles(p, ctx)[0].path
    time = file.stat().st_mtime_ns
    engine.sync(selection)
    assert file.stat().st_mtime_ns == time and file.stat().st_mode & 0o777 == 0o600
    assert not ctx.detection.default_paths[0].exists()
    replace(tmp_path / "secrets.yaml", yaml_bytes({"version": 1, "keys": {"one": "rotated-key"}}))
    engine.sync(selection)
    assert b"rotated-key" in file.read_bytes()


def test_small_context_requires_explicit_budget(tmp_path):
    from dataclasses import replace

    a, p, ctx = native.create_adapter(), provider(), context(tmp_path)
    small = p.model_copy(
        update={"models": [m.model_copy(update={"context_window": 32000}) for m in p.models]}
    )
    with pytest.raises(HarnessSyncError):
        a.validate(small, ctx)
    ctx = replace(ctx, settings=HarnessSettings(options={"reserved_context_size": 4096}))
    a.validate(small, ctx)
    doc = tomllib.loads(a.profiles(small, ctx)[0].render(SecretStore({"one": "key"})).decode())
    assert doc["loop_control"]["reserved_context_size"] == 4096
