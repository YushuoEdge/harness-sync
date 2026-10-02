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

native = importlib.import_module("harnesses.pi.adapter")


def provider(name="one", protocol="openai-chat"):
    return Provider.model_validate(
        {
            "name": name,
            "type": protocol,
            "base_url": f"https://{name}.invalid/v1",
            "api_key": {"secret": name},
            "models": [
                {
                    "name": "label",
                    "id": f"vendor/{name}-{r}",
                    "role": r,
                    "context_window": 32000,
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
            "pi",
            "installed",
            Path(sys.executable),
            native.VERSION,
            default_paths=(tmp_path / "native/models.json", tmp_path / "native/settings.json"),
            capabilities=("custom-models",),
        ),
        HarnessSettings(),
        lambda p: current,
        lambda p: baseline,
    )


@pytest.mark.parametrize("protocol", native.APIS)
def test_catalog_protocol_roles_metadata(tmp_path, protocol):
    a, p, ctx = native.create_adapter(), provider(protocol=protocol), context(tmp_path)
    a.validate(p, ctx)
    artifacts = a.profiles(p, ctx)
    data = artifacts[0].render(SecretStore({"one": "test-one"}))
    artifacts[0].verify(data)
    catalog = json.loads(data)["providers"]["hs-one"]
    assert catalog["api"] == native.APIS[protocol]
    assert catalog["apiKey"] == "$HS_ONE"
    assert catalog["models"][2]["id"] == "vendor/one-complex"
    assert b"test-one" not in data
    for role in ("simple", "daily", "complex"):
        spec = a.launch(
            p, role, ("-p", "prompt with quotes'"), ctx, SecretStore({"one": "test-one"})
        )
        assert spec.argv[3] == f"vendor/one-{role}"
        assert spec.environment["HS_ONE"] == "test-one"
        assert "test-one" not in str(spec.argv)
        assert spec.environment["PI_CODING_AGENT_DIR"].endswith("pi/one")


def test_duplicate_metadata_and_auth_conflicts(tmp_path):
    p = provider()
    duplicate = p.model_copy(
        update={"models": [m.model_copy(update={"id": "same"}) for m in p.models]}
    )
    assert len(native.catalog(duplicate)["models"]) == 1
    changed = duplicate.model_copy(
        update={
            "models": [
                duplicate.models[0].model_copy(update={"context_window": 64000}),
                *duplicate.models[1:],
            ]
        }
    )
    with pytest.raises(HarnessSyncError):
        native.catalog(changed)
    with pytest.raises(ConflictError):
        native.create_adapter().validate(p, context(tmp_path, b'{"hs-one":{"type":"api_key"}}'))


def test_default_preservation_conflicts(tmp_path):
    a, p = native.create_adapter(), provider()
    current = b'{"providers":{"keep":{"apiKey":"existing"}},"theme":"dark"}'
    artifact = a.defaults((p,), p, "daily", context(tmp_path, current))[0]
    data = artifact.render(SecretStore({"one": "key"}))
    assert json.loads(data)["providers"]["keep"]["apiKey"] == "existing"
    changed = data.replace(b"https://one.invalid", b"https://changed.invalid")
    with pytest.raises(ConflictError):
        a.defaults((p,), p, "daily", context(tmp_path, changed, data))[0].render(
            SecretStore({"one": "key"})
        )


@pytest.mark.parametrize("flag", ["--model=x", "--provider", "--api-key", "-e"])
def test_routing_flags(tmp_path, flag):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", (flag,), context(tmp_path), SecretStore({"one": "key"})
        )


def test_version_identity_fixtures(monkeypatch):
    fixtures = Path(__file__).parents[1] / "fixtures"
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/pi"))
    help_text = (fixtures / f"pi-{native.VERSION}-help.txt").read_text()
    for version, expected in [(native.VERSION, "installed"), ("9.9.9", "unsupported-version")]:
        values = iter([ProbeResult(0, version, ""), ProbeResult(0, help_text, "")])
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        assert (
            native.create_adapter().detect(DetectionContext(HarnessSettings(), {})).status
            == expected
        )


def test_engine_protects_defaults_and_is_idempotent(monkeypatch, tmp_path):
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
    for path in ctx.detection.default_paths:
        replace(path, b'{"keep":"unchanged"}')
    engine = Engine(ctx.paths, Registry((a,)))
    selection = Selection((a.id,), profiles_only=True, commands=False)
    engine.sync(selection)
    files = [x.path for x in a.profiles(p, ctx)]
    times = [x.stat().st_mtime_ns for x in files]
    engine.sync(selection)
    assert times == [x.stat().st_mtime_ns for x in files]
    assert all(x.read_bytes() == b'{"keep":"unchanged"}' for x in ctx.detection.default_paths)
    for x in files:
        assert x.stat().st_mode & 0o777 == 0o600
