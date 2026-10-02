import importlib
import json
import sys
from pathlib import Path

import pytest

from harness_sync.contracts import Detection, DetectionContext, RenderContext
from harness_sync.detection import ProbeResult
from harness_sync.errors import ConflictError, HarnessSyncError
from harness_sync.merge import MISSING
from harness_sync.paths import Paths
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore
from harnesses.opencode.jsonc import edit, parse

native = importlib.import_module("harnesses.opencode.adapter")


def provider(name="one", protocol="openai-chat"):
    return Provider.model_validate(
        {
            "name": name,
            "type": protocol,
            "base_url": f"https://{name}.invalid/v1",
            "api_key": {"secret": name},
            "models": [
                {
                    "name": "same",
                    "id": f"vendor/{name}-{r}",
                    "role": r,
                    "context_window": 128000,
                    "max_output_tokens": 1024,
                }
                for r in ("simple", "daily", "complex")
            ],
        }
    )


def context(tmp_path, current=None, baseline=None):
    return RenderContext(
        Paths(tmp_path / "config.yaml", tmp_path / "state"),
        Detection(
            "opencode",
            "installed",
            Path(sys.executable),
            native.VERSION,
            default_paths=(tmp_path / "native/opencode.jsonc",),
            capabilities=("inline-overlay",),
        ),
        HarnessSettings(),
        lambda p: current,
        lambda p: baseline,
    )


@pytest.mark.parametrize("protocol", native.SDK)
def test_catalog_roles_and_launch(tmp_path, protocol):
    a, p, ctx = native.create_adapter(), provider(protocol=protocol), context(tmp_path)
    keys = SecretStore({"one": "test-one"})
    a.validate(p, ctx)
    for artifact in a.profiles(p, ctx):
        data = artifact.render(keys)
        artifact.verify(data)
        assert b"test-one" not in data
        doc = json.loads(data)
        assert doc["provider"]["hs-one"]["npm"] == native.SDK[protocol]
        assert doc["small_model"] == "hs-one/vendor/one-simple"
    for role in ("simple", "daily", "complex"):
        spec = a.launch(p, role, ("run", "prompt with 'quotes'"), ctx, keys)
        assert spec.argv == (
            "--pure",
            "--model",
            f"hs-one/vendor/one-{role}",
            "run",
            "prompt with 'quotes'",
        )
        inline = json.loads(spec.environment["OPENCODE_CONFIG_CONTENT"])
        assert inline["model"] == f"hs-one/vendor/one-{role}"
        assert inline["enabled_providers"] == ["hs-one"]
        assert spec.environment["HS_ONE"] == "test-one"
        assert "test-one" not in str(spec.argv)


def test_default_jsonc_preservation_conflict_and_removal(tmp_path):
    a, p = native.create_adapter(), provider()
    current = b'// preserve\n{"theme":"dark", // inline\n"provider":{"keep":{"x":1}},}\n'
    data = a.defaults((p,), p, "daily", context(tmp_path, current))[0].render(
        SecretStore({"one": "key"})
    )
    assert b"// preserve" in data and b"// inline" in data
    assert parse(data)["provider"]["keep"] == {"x": 1}
    changed = data.replace(b"vendor/one-daily", b"manual")
    with pytest.raises(ConflictError):
        a.defaults((p,), p, "daily", context(tmp_path, changed, data))[0].render(
            SecretStore({"one": "key"})
        )
    result = edit(data, data, {("provider", "hs-one"): MISSING})
    assert "hs-one" not in parse(result)["provider"]
    assert b"// inline" in result


@pytest.mark.parametrize("data", [b'{"x":1,"x":2}', b'{"x":1 "y":2}', b'{/* block */"x":1}'])
def test_invalid_or_unpreservable_syntax_is_rejected(data):
    with pytest.raises(HarnessSyncError):
        edit(data, None, {("model",): "new"})


@pytest.mark.parametrize("flag", ["--model=x", "-mother", "--agent", "--attach=x"])
def test_routing_flags(tmp_path, flag):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", (flag,), context(tmp_path), SecretStore({"one": "key"})
        )


def test_version_and_global_path_precedence(monkeypatch, tmp_path):
    fixtures = Path(__file__).parents[1] / "fixtures"
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/opencode"))
    help_text = (fixtures / f"opencode-{native.VERSION}-help.txt").read_text()
    home = tmp_path / "opencode"
    home.mkdir()
    (home / "opencode.json").write_text("{}")
    (home / "opencode.jsonc").write_text("{}")
    for number, expected in [(native.VERSION, "installed"), ("9.9.9", "unsupported-version")]:
        values = iter([ProbeResult(0, number, ""), ProbeResult(0, help_text, "")])
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        result = native.create_adapter().detect(
            DetectionContext(HarnessSettings(), {"XDG_CONFIG_HOME": str(tmp_path)})
        )
        assert result.status == expected
        assert result.default_paths == (home / "opencode.jsonc",)


def test_engine_preserves_existing_defaults(monkeypatch, tmp_path):
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
    default = ctx.detection.default_paths[0]
    replace(default, b'// mine\n{"theme":"dark"}')
    engine = Engine(ctx.paths, Registry((a,)))
    selection = Selection((a.id,), profiles_only=True, commands=False)
    engine.sync(selection)
    files = [x.path for x in a.profiles(p, ctx)]
    times = [x.stat().st_mtime_ns for x in files]
    engine.sync(selection)
    assert times == [x.stat().st_mtime_ns for x in files]
    assert default.read_bytes() == b'// mine\n{"theme":"dark"}'
