import importlib
import sys
from pathlib import Path

import pytest

from harness_sync.contracts import Detection, DetectionContext, RenderContext
from harness_sync.detection import ProbeResult
from harness_sync.errors import ConflictError, HarnessSyncError
from harness_sync.paths import Paths
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore

native = importlib.import_module("harnesses.openclaw.adapter")


def provider(name="one", protocol="openai-chat", port=None):
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
                for r in native.ROLES
            ],
            "overrides": {"openclaw": {"options": {"gateway_port_base": port}}} if port else {},
        }
    )


def context(tmp_path, current=None, baseline=None):
    return RenderContext(
        Paths(tmp_path / "config.yaml", tmp_path / "state"),
        Detection(
            "openclaw",
            "installed",
            Path(sys.executable),
            native.VERSION,
            default_paths=(tmp_path / "native/openclaw.json",),
            capabilities=("env-secret-ref",),
        ),
        HarnessSettings(),
        lambda _: current,
        lambda _: baseline,
    )


@pytest.mark.parametrize("protocol", native.APIS)
def test_native_roles_and_isolation(tmp_path, protocol):
    a, p, ctx = native.create_adapter(), provider(protocol=protocol), context(tmp_path)
    keys = SecretStore({"one": "test-one"})
    a.validate(p, ctx)
    for artifact in a.profiles(p, ctx):
        data = artifact.render(keys)
        artifact.verify(data)
        role = artifact.path.parent.name
        doc = native.parse(data)
        assert doc["agents"]["defaults"]["model"]["primary"] == f"hs-one/vendor/one-{role}"
        entry = doc["models"]["providers"]["hs-one"]
        assert entry["api"] == native.APIS[protocol]
        assert entry["auth"] == "api-key"
        assert entry["apiKey"] == {"source": "env", "provider": "default", "id": "HS_ONE"}
        assert b"test-one" not in data
        assert doc["agents"]["defaults"]["workspace"].startswith(str(artifact.path.parent))
        spec = a.launch(p, role, ("agent", "--local", "--message", "hello 'world'"), ctx, keys)
        assert spec.argv[:3] == ("agent", "--model", f"hs-one/vendor/one-{role}")
        assert spec.argv[-1] == "hello 'world'"
        assert spec.environment["OPENCLAW_CONFIG_PATH"] == str(artifact.path)
        assert spec.environment["HS_ONE"] == "test-one"
        assert "OPENCLAW_AGENT_DIR" in spec.unset
    other = a.profiles(provider("two", protocol), ctx)
    assert not {x.path for x in other} & {x.path for x in a.profiles(p, ctx)}


def test_gateway_ports_and_dispatch(tmp_path):
    a, ctx, keys = native.create_adapter(), context(tmp_path), SecretStore({"one": "key"})
    with pytest.raises(HarnessSyncError, match="gateway_port_base"):
        a.launch(provider(), "daily", ("gateway", "run"), ctx, keys)
    for role, expected in zip(native.ROLES, (23000, 23001, 23002), strict=True):
        p = provider(port=23000)
        spec = a.launch(p, role, ("gateway", "run", "--verbose"), ctx, keys)
        assert spec.argv == ("gateway", "run", "--verbose")
        assert spec.environment["OPENCLAW_GATEWAY_PORT"] == str(expected)
        token = spec.environment["HARNESS_SYNC_OPENCLAW_GATEWAY_TOKEN"]
        assert len(token) == 64 and token != "key"
        rotated = a.launch(p, role, ("gateway", "run"), ctx, SecretStore({"one": "rotated"}))
        assert rotated.environment["HARNESS_SYNC_OPENCLAW_GATEWAY_TOKEN"] != token
        doc = native.parse(a.profiles(p, ctx)[native.ROLES.index(role)].render(keys))
        assert doc["gateway"]["port"] == expected
        assert doc["gateway"]["auth"]["token"]["id"] == "HARNESS_SYNC_OPENCLAW_GATEWAY_TOKEN"
    for subcommand in ("install", "uninstall", "start", "restart", "stop"):
        with pytest.raises(HarnessSyncError):
            a.launch(provider(port=23000), "daily", ("gateway", subcommand), ctx, keys)
        with pytest.raises(HarnessSyncError):
            a.launch(
                provider(port=23000),
                "daily",
                ("--log-level", "debug", "gateway", subcommand),
                ctx,
                keys,
            )
    spec = a.launch(provider(), "daily", ("--log-level", "debug", "agent", "--local"), ctx, keys)
    assert spec.argv == (
        "--log-level",
        "debug",
        "agent",
        "--model",
        "hs-one/vendor/one-daily",
        "--local",
    )
    assert a.launch(provider(), "daily", (), ctx, keys).argv == ()
    assert a.launch(provider(), "daily", ("config", "validate"), ctx, keys).argv == (
        "config",
        "validate",
    )


@pytest.mark.parametrize("flag", ["--profile=x", "--container=x", "--model=x", "--dev", "--force"])
def test_routing_conflicts(tmp_path, flag):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", (flag,), context(tmp_path), SecretStore({"one": "key"})
        )


def test_defaults_preserve_native_policy_and_rotate_keys(tmp_path):
    current = b"""{
      // channel and gateway policy
      gateway: {port: 18789, auth: {mode: "token", token: "keep"}},
      agents: {defaults: {model: {fallbacks: ["existing/model"]}}},
      channels: {telegram: {enabled: false}},
    }"""
    a, p, keys = native.create_adapter(), provider(), SecretStore({"one": "test-one"})
    artifact = a.defaults((p,), p, "daily", context(tmp_path, current))[0]
    generated = artifact.render(keys)
    doc = native.parse(generated)
    assert b"// channel and gateway policy" in generated
    assert doc["gateway"] == native.parse(current)["gateway"]
    assert doc["channels"] == native.parse(current)["channels"]
    assert doc["agents"]["defaults"]["model"]["fallbacks"] == ["existing/model"]
    assert doc["models"]["providers"]["hs-one"]["apiKey"] == "test-one"
    rotated = a.defaults((p,), p, "daily", context(tmp_path, generated, generated))[0].render(
        SecretStore({"one": "rotated"})
    )
    assert native.parse(rotated)["models"]["providers"]["hs-one"]["apiKey"] == "rotated"
    with pytest.raises(ConflictError):
        a.defaults(
            (p,), p, "daily", context(tmp_path, generated.replace(b"test-one", b"edit"), generated)
        )[0].render(keys)
    with pytest.raises(ConflictError):
        a.defaults((p,), p, "daily", context(tmp_path, generated))
    with pytest.raises(HarnessSyncError, match="substitutions"):
        artifact.render(SecretStore({"one": "${OTHER_KEY}"}))


def test_duplicate_ids_and_override(tmp_path):
    a, p = native.create_adapter(), provider()
    data = p.model_dump(exclude_none=True)
    for model in data["models"]:
        model["overrides"] = {"openclaw": {"id": "vendor/repeated"}}
    repeated = Provider.model_validate(data)
    a.validate(repeated, context(tmp_path))
    assert len(native.catalog(repeated)["models"]) == 1
    assert len(native.aliases(repeated)) == 1
    assert native.selector(repeated, "complex") == "hs-one/vendor/repeated"
    data["models"][1]["context_window"] = 256000
    with pytest.raises(HarnessSyncError, match="conflicting metadata"):
        a.validate(Provider.model_validate(data), context(tmp_path))


def test_version_and_override_fixture(monkeypatch, tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures"
    version = (fixture / f"openclaw-{native.VERSION}-version.txt").read_text()
    help_text = (fixture / f"openclaw-{native.VERSION}-agent-help.txt").read_text()
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/openclaw"))
    for text, expected in (
        (version, "installed"),
        (version.replace(native.REVISION, "fffffff"), "unsupported-version"),
    ):
        values = iter([ProbeResult(0, text, ""), ProbeResult(0, help_text, "")])
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        ctx = DetectionContext(
            HarnessSettings(), {"OPENCLAW_CONFIG_PATH": str(tmp_path / "active")}
        )
        result = native.create_adapter().detect(ctx)
        assert result.status == expected
        assert result.default_paths == (tmp_path / "active",)


def test_engine_private_idempotent_profiles_default_protection(monkeypatch, tmp_path):
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
    files = [x.path for x in a.profiles(p, ctx)]
    times = [x.stat().st_mtime_ns for x in files]
    engine.sync(selection)
    assert times == [x.stat().st_mtime_ns for x in files]
    assert all(x.stat().st_mode & 0o777 == 0o600 for x in files)
    assert not ctx.detection.default_paths[0].exists()


def test_legacy_config_path_and_includes(monkeypatch, tmp_path):
    monkeypatch.setattr(native, "find_executable", lambda *a: None)
    legacy = tmp_path / ".clawdbot/clawdbot.json"
    legacy.parent.mkdir()
    legacy.write_text("{}")
    a = native.create_adapter()
    assert a.detect(DetectionContext(HarnessSettings(), {"HOME": str(tmp_path)})).default_paths == (
        legacy,
    )
    p = provider()
    with pytest.raises(HarnessSyncError, match="include-based"):
        a.defaults((p,), p, "daily", context(tmp_path, b'{"models":{"$include":"other.json"}}'))


def test_default_catalog_removal_preserves_other_providers(tmp_path):
    a, p, other = native.create_adapter(), provider(), provider("two")
    keys = SecretStore({"one": "test-one", "two": "test-two"})
    current = b'{"models":{"providers":{"existing":{"baseUrl":"https://keep.invalid"}}}}'
    data = a.defaults((p, other), p, "daily", context(tmp_path, current))[0].render(keys)
    generated = a.defaults((other,), other, "complex", context(tmp_path, data, data))[0].render(
        keys
    )
    doc = native.parse(generated)
    assert set(doc["models"]["providers"]) == {"existing", "hs-two"}
    assert set(doc["agents"]["defaults"]["models"]) == set(native.aliases(other))
