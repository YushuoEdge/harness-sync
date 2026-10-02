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

native = importlib.import_module("harnesses.deepseek-harness.adapter")


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
            "deepseek-harness",
            "installed",
            Path(sys.executable),
            native.VERSION,
            default_paths=(tmp_path / "native/cordis.patch.yml",),
            capabilities=("bundled-profiles",),
        ),
        HarnessSettings(options={"base_profile": "headless"}),
        lambda p: current if p == tmp_path / "native/cordis.patch.yml" else None,
        lambda p: baseline if p == tmp_path / "native/cordis.patch.yml" else None,
    )


@pytest.mark.parametrize("protocol", native.APIS)
def test_profiles_and_roles(tmp_path, protocol):
    a, p, ctx = native.create_adapter(), provider(protocol=protocol), context(tmp_path)
    keys = SecretStore({"one": "test-one"})
    a.validate(p, ctx)
    artifacts = a.profiles(p, ctx)
    assert len(artifacts) == 6
    for artifact in artifacts:
        data = artifact.render(keys)
        artifact.verify(data)
        assert b"test-one" not in data
        assert artifact.mode == 0o600
        if artifact.path.name == "package.json":
            assert json.loads(data)["dsh"]["profile"]["bundles"][-1] == "@deepseek-ai/dsh-headless"
        if artifact.path.name == "cordis.patch.yml":
            settings = {row["id"]: row["config"] for row in native.parse_patch(data)}
            role = artifact.path.parents[2].name
            assert settings["agent-default-model"]["model"] == f"vendor/one-{role}"
            assert settings["llm-pi-ai"]["providers"]["hs-one"]["api"] == native.APIS[protocol]
    for role in ("simple", "daily", "complex"):
        spec = a.launch(p, role, ("prompt with 'quotes'",), ctx, keys)
        assert spec.argv == ("--profile", "headless", "prompt with 'quotes'")
        assert spec.environment["DSH_HOME"].endswith("one/" + role)
        assert spec.environment["HS_ONE"] == "test-one"


def test_defaults_comments_conflicts_and_inert_tags(tmp_path):
    a, p = native.create_adapter(), provider()
    data = a.defaults(
        (p,), p, "daily", context(tmp_path, b"# preserve\n- id: other\n  config: {value: keep}\n")
    )[0].render(SecretStore({"one": "test-one"}))
    assert b"# preserve" in data and native.parse_patch(data)[0]["config"]["value"] == "keep"
    changed = data.replace(b"vendor/one-daily", b"manual")
    with pytest.raises(ConflictError):
        a.defaults((p,), p, "daily", context(tmp_path, changed, data))[0].render(
            SecretStore({"one": "test-one"})
        )
    with pytest.raises(HarnessSyncError):
        native.parse(b"value: !!js process.exit()\n")


@pytest.mark.parametrize("args", [("--patch=x",), ("--profile", "other"), ("plugin",)])
def test_routing_flags(tmp_path, args):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", args, context(tmp_path), SecretStore({"one": "test-one"})
        )


def test_version_and_bundle_fixtures(monkeypatch):
    fixtures = Path(__file__).parents[1] / "fixtures"
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/dsh"))
    texts = [
        (fixtures / f"dsh-{native.VERSION}-{kind}.txt").read_text() for kind in ("version", "help")
    ]
    dump = (fixtures / f"dsh-{native.VERSION}-headless.yml").read_text()
    for number, expected in [(texts[0], "installed"), ("9.9.9", "unsupported-version")]:
        values = iter(ProbeResult(0, t, "") for t in (number, texts[1], dump))
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        assert (
            native.create_adapter().detect(DetectionContext(HarnessSettings(), {})).status
            == expected
        )


def test_engine_default_protection(monkeypatch, tmp_path):
    from harness_sync.config import yaml_bytes
    from harness_sync.engine import Engine, Selection
    from harness_sync.filesystem import replace
    from harness_sync.registry import Registry

    a, p, ctx = native.create_adapter(), provider(), context(tmp_path)
    monkeypatch.setattr(a, "detect", lambda _: ctx.detection)
    replace(
        ctx.paths.config,
        yaml_bytes(
            {
                "version": 1,
                "providers": [p.model_dump(exclude_none=True)],
                "harnesses": {a.id: {"options": {"base_profile": "headless"}}},
            }
        ),
    )
    replace(tmp_path / "secrets.yaml", yaml_bytes({"version": 1, "keys": {"one": "test-one"}}))
    engine = Engine(ctx.paths, Registry((a,)))
    selection = Selection((a.id,), profiles_only=True, commands=False)
    engine.sync(selection)
    paths = [x.path for x in a.profiles(p, ctx)]
    times = [x.stat().st_mtime_ns for x in paths]
    engine.sync(selection)
    assert times == [x.stat().st_mtime_ns for x in paths]
    assert not ctx.detection.default_paths[0].exists()


def test_home_override_and_patch_validation(tmp_path):
    from dataclasses import replace

    a, p, ctx = native.create_adapter(), provider(), context(tmp_path)
    for data in (b"- id: agent-default-model\n  config: {model: stale}\n", b"value: old\n"):
        overridden = replace(ctx, read=lambda _, data=data: data)
        with pytest.raises(HarnessSyncError):
            a.launch(p, "daily", ("hello",), overridden, SecretStore({"one": "key"}))
    for data in (
        b"- id: duplicate\n- id: duplicate\n",
        b"- id: unsafe\n  config: !!js process.exit()\n",
    ):
        with pytest.raises(HarnessSyncError):
            native.parse_patch(data)


def test_default_preserves_unrelated_rows_and_provider_fields(tmp_path):
    current = b"""# native patch
- id: llm-pi-ai
  config:
    timeout: 123
    providers:
      personal: {baseURL: https://keep.invalid}
- id: agent-default-model
  config: {provider: personal, model: old, other: keep}
- id: sandbox
  config: {policy: strict}
"""
    a, p = native.create_adapter(), provider()
    data = a.defaults((p,), p, "complex", context(tmp_path, current))[0].render(
        SecretStore({"one": "key"})
    )
    rows = {r["id"]: r["config"] for r in native.parse_patch(data)}
    assert b"# native patch" in data
    assert rows["llm-pi-ai"]["timeout"] == 123
    assert rows["llm-pi-ai"]["providers"]["personal"]["baseURL"] == "https://keep.invalid"
    assert rows["agent-default-model"]["other"] == "keep"
    assert rows["sandbox"] == {"policy": "strict"}
