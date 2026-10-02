import hashlib
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

native = importlib.import_module("harnesses.hermes-agent.adapter")


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


def context(tmp_path, current=None, baseline=None, env=None, env_baseline=None):
    config = tmp_path / "native/config.yaml"
    return RenderContext(
        Paths(tmp_path / "config.yaml", tmp_path / "state"),
        Detection(
            "hermes-agent",
            "installed",
            Path(sys.executable),
            native.VERSION,
            default_paths=(config, config.parent / ".env"),
            capabilities=("named-providers",),
        ),
        HarnessSettings(),
        lambda p: current if p == config else env,
        lambda p: baseline if p == config else env_baseline,
    )


@pytest.mark.parametrize("protocol", native.APIS)
def test_roles_protocol_and_grammar(tmp_path, protocol):
    a, p, ctx = native.create_adapter(), provider(protocol=protocol), context(tmp_path)
    keys = SecretStore({"one": "test-one"})
    a.validate(p, ctx)
    artifacts = a.profiles(p, ctx)
    assert len(artifacts) == 6
    for artifact in artifacts:
        data = artifact.render(keys)
        artifact.verify(data)
        if artifact.path.name == "config.yaml":
            doc = native.parse(data)
            role = artifact.path.parent.name
            assert doc["model"]["default"] == f"vendor/one-{role}"
            assert doc["model"]["api_mode"] == native.APIS[protocol]
            assert doc["providers"]["hs-one"]["key_env"] == "HS_ONE"
            assert b"test-one" not in data
    for role in ("simple", "daily", "complex"):
        spec = a.launch(p, role, ("chat", "-q", "prompt with 'quotes'"), ctx, keys)
        assert spec.argv[:5] == (
            "chat",
            "--provider",
            "custom:hs-one",
            "--model",
            f"vendor/one-{role}",
        )
        assert spec.environment["HERMES_HOME"].endswith("one/" + role)
        assert spec.environment["HS_ONE"] == "test-one"
    admin = a.launch(p, "daily", ("sessions", "list"), ctx, keys)
    assert admin.argv == ("sessions", "list")


def test_dotenv_roundtrip_and_interpolation_rejection():
    key = "value'with\\slashes $literal #hash"
    data = native.dotenv_line("HS_ONE", key).encode()
    assert native.dotenv(data)[0] == {"HS_ONE": key}
    with pytest.raises(HarnessSyncError):
        native.dotenv_line("HS_ONE", "${BAD}")
    with pytest.raises(HarnessSyncError):
        native.dotenv(b"HS_ONE=a\nHS_ONE=b\n")


def test_default_yaml_and_dotenv_preservation_rotation_conflicts(tmp_path):
    a, p = native.create_adapter(), provider()
    ctx = context(tmp_path, b"# preserve\nother: keep\n", env=b'# token\nBOT_TOKEN="keep"\n')
    artifacts = a.defaults((p,), p, "daily", ctx)
    yaml_data, env_data = [x.render(SecretStore({"one": "old-key"})) for x in artifacts]
    assert b"# preserve" in yaml_data and native.parse(yaml_data)["other"] == "keep"
    assert b'# token\nBOT_TOKEN="keep"' in env_data
    new = a.defaults((p,), p, "daily", context(tmp_path, yaml_data, yaml_data, env_data, env_data))
    rotated = new[1].render(SecretStore({"one": "new-key"}))
    assert native.dotenv(rotated)[0] == {"BOT_TOKEN": "keep", "HS_ONE": "new-key"}
    changed = env_data.replace(b"old-key", b"manual-edit")
    with pytest.raises(ConflictError):
        a.defaults((p,), p, "daily", context(tmp_path, yaml_data, yaml_data, changed, env_data))[
            1
        ].render(SecretStore({"one": "new-key"}))


@pytest.mark.parametrize("flag", ["--provider=x", "--profile", "--model=x", "--safe-mode"])
def test_routing_flags(tmp_path, flag):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", (flag,), context(tmp_path), SecretStore({"one": "key"})
        )


def test_version_revision_fixture(monkeypatch):
    fixture = Path(__file__).parents[1] / "fixtures"
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/hermes"))
    version = (fixture / f"hermes-{native.VERSION}-version.txt").read_text()
    help_text = (fixture / f"hermes-{native.VERSION}-help.txt").read_text()
    for text, expected in [
        (version, "installed"),
        (version.replace(native.REVISION[:7], "fffffff"), "unsupported-version"),
    ]:
        values = iter([ProbeResult(0, text, ""), ProbeResult(0, help_text, "")])
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        assert (
            native.create_adapter().detect(DetectionContext(HarnessSettings(), {})).status
            == expected
        )


def test_engine_private_profiles_rotation_and_default_protection(monkeypatch, tmp_path):
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
    assert not any(x.exists() for x in ctx.detection.default_paths)
    replace(tmp_path / "secrets.yaml", yaml_bytes({"version": 1, "keys": {"one": "rotated-key"}}))
    engine.sync(selection)
    assert all(b"rotated-key" in x.read_bytes() for x in files if x.name == ".env")


def test_committed_source_runtime_and_launch(monkeypatch, tmp_path):
    from dataclasses import replace

    source = tmp_path / "source checkout"
    source.mkdir()
    home = tmp_path / ".hermes"
    identity = hashlib.sha256(str(source.resolve()).encode()).hexdigest()[:16]
    state = home / "installs" / identity
    venv = state / "environments" / "generation" / "venv"
    python = venv / "bin/python3"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    python.chmod(0o700)
    facts = state / "facts.json"
    facts.write_text(json.dumps({"packages": {"venv": {"environment": str(venv)}}}))
    text = (
        f"Hermes Agent v{native.VERSION}+5635.g{native.REVISION[:7]}\nInstall directory: {source}\n"
    )
    assert native.installed_venv_python(text, {"HOME": str(tmp_path)}) == (python, source)
    fixtures = Path(__file__).parents[1] / "fixtures"
    help_text = (fixtures / f"hermes-{native.VERSION}-help.txt").read_text()
    probes = iter(
        [
            ProbeResult(0, text, ""),
            ProbeResult(1, "", "isolated runtime not installed"),
            ProbeResult(0, text, ""),
            ProbeResult(0, help_text, ""),
        ]
    )
    monkeypatch.setattr(native, "find_executable", lambda *a: tmp_path / "hermes")
    monkeypatch.setattr(native, "probe", lambda *a: next(probes))
    detected = native.create_adapter().detect(
        DetectionContext(HarnessSettings(), {"HOME": str(tmp_path)})
    )
    assert detected.status == "installed" and detected.executable == python
    ctx = replace(context(tmp_path), detection=detected)
    spec = native.create_adapter().launch(
        provider(), "daily", ("chat", "-q", "hello"), ctx, SecretStore({"one": "key"})
    )
    assert spec.argv[:3] == native.source_driver(source)
    assert spec.argv[3:8] == ("chat", "--provider", "custom:hs-one", "--model", "vendor/one-daily")
    assert spec.environment["HERMES_DISABLE_LAZY_INSTALLS"] == "1"
    facts.write_text(json.dumps({"packages": {"venv": {"environment": str(tmp_path)}}}))
    assert native.installed_venv_python(text, {"HOME": str(tmp_path)}) is None
