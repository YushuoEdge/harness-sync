import importlib
import json
import sys
from pathlib import Path

import pytest

from harness_sync.contracts import Detection, DetectionContext, RenderContext
from harness_sync.detection import ProbeResult
from harness_sync.errors import HarnessSyncError
from harness_sync.paths import Paths
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore

native = importlib.import_module("harnesses.zcode.adapter")


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
            "zcode",
            "installed",
            Path(sys.executable),
            native.VERSION,
            default_paths=(tmp_path / "native/provider_config.json",),
            capabilities=("provider-file-v1",),
        ),
        HarnessSettings(),
        lambda p: current,
        lambda p: baseline,
    )


@pytest.mark.parametrize("protocol", native.APIS)
def test_profiles_identity_roles_and_rotation(tmp_path, protocol):
    a, p, ctx = native.create_adapter(), provider(protocol=protocol), context(tmp_path)
    a.validate(p, ctx)
    artifacts = a.profiles(p, ctx)
    assert len(artifacts) == 6
    for role in ("simple", "daily", "complex"):
        artifact = next(
            x
            for x in artifacts
            if x.path.parent.name == role and x.path.name == "provider_config.json"
        )
        content = artifact.render(SecretStore({"one": "old-key"}))
        artifact.verify(content)
        config = json.loads(content)["config"]
        rule = config["providerConfigRules"]["providerRules"][0]
        assert rule["config"]["api"]["type"] == native.APIS[protocol]
        assert rule["config"]["access"]["apiKey"] == "old-key"
        assert config["defaultModelSelection"]["modelId"] == f"vendor/one-{role}"
        spec = a.launch(
            p, role, ("--prompt", "hello 'quoted'"), ctx, SecretStore({"one": "old-key"})
        )
        assert "old-key" not in str(spec.argv)
        assert spec.environment["ZCODE_DATA_BASE_DIR"].endswith("/" + role)
        assert "ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE" in spec.unset
        rotated = artifact.render(SecretStore({"one": "new-key"}))
        assert b"new-key" in rotated and b"old-key" not in rotated
    assert artifacts[0].mode == 0o600


def test_repeated_ids_and_metadata_validation(tmp_path):
    a, p, ctx = native.create_adapter(), provider(), context(tmp_path)
    repeated = p.model_copy(
        update={"models": [m.model_copy(update={"id": "slash/dollar$model"}) for m in p.models]}
    )
    assert len(native.model_rules(repeated)) == 1
    conflict = repeated.model_copy(
        update={
            "models": [
                repeated.models[0].model_copy(update={"context_window": 64000}),
                *repeated.models[1:],
            ]
        }
    )
    with pytest.raises(HarnessSyncError):
        a.validate(conflict, ctx)
    for changes in (
        {"context_window": None},
        {"max_output_tokens": None},
        {"reasoning": True},
        {"reasoning_effort": "high"},
    ):
        changed = p.model_copy(
            update={"models": [p.models[0].model_copy(update=changes), *p.models[1:]]}
        )
        with pytest.raises(HarnessSyncError):
            a.validate(changed, ctx)
    with pytest.raises(HarnessSyncError):
        a.defaults((p,), p, "daily", ctx)
    with pytest.raises(HarnessSyncError):
        native.parse(b'{"schemaVersion":1,"schemaVersion":1}')


def test_provider_and_harness_overrides_do_not_share_identity(tmp_path):
    a, ctx = native.create_adapter(), context(tmp_path)
    paths = set()
    for name in ("one", "two"):
        data = provider(name).model_dump(exclude_none=True)
        data["overrides"] = {"zcode": {"type": "anthropic", "base_url": "https://override.invalid"}}
        for model in data["models"]:
            model["overrides"] = {"zcode": {"id": f"native/{name}${model['role']}"}}
        p = Provider.model_validate(data)
        a.validate(p, ctx)
        artifacts = a.profiles(p, ctx)
        assert paths.isdisjoint(x.path for x in artifacts)
        paths.update(x.path for x in artifacts)
        doc = json.loads(artifacts[0].render(SecretStore({name: f"fake-{name}"})))
        rule = doc["config"]["providerConfigRules"]["providerRules"][0]
        assert rule["config"]["api"]["type"] == "anthropic-messages"
        assert rule["config"]["api"]["baseUrl"] == "https://override.invalid"
        assert rule["config"]["access"]["apiKey"] == f"fake-{name}"
        assert doc["config"]["defaultModelSelection"]["modelId"] == f"native/{name}$simple"


@pytest.mark.parametrize(
    "flag",
    [
        "--resume=x",
        "--continue",
        "--web",
        "--model=x",
        "--enable-workflow",
        "--surface=desktop",
        "app-server",
    ],
)
def test_routing_flags(tmp_path, flag):
    with pytest.raises(HarnessSyncError):
        native.create_adapter().launch(
            provider(), "daily", (flag,), context(tmp_path), SecretStore({"one": "key"})
        )


def test_version_fixtures_fail_closed(monkeypatch, tmp_path):
    fixtures = Path(__file__).parents[1] / "fixtures"
    monkeypatch.setattr(native, "find_executable", lambda *a: Path("/test/zcode"))
    help_text = (fixtures / f"zcode-{native.VERSION}-help.txt").read_text()
    for version, expected in [(native.VERSION, "installed"), ("9.9.9", "unsupported-version")]:
        values = iter([ProbeResult(0, version, ""), ProbeResult(0, help_text, "")])
        monkeypatch.setattr(native, "probe", lambda *a, values=values: next(values))
        detected = native.create_adapter().detect(
            DetectionContext(HarnessSettings(), {"HOME": str(tmp_path)})
        )
        assert detected.status == expected
        assert detected.default_paths == (tmp_path / ".zcode/v2/provider_config.json",)
    values = iter(
        [
            ProbeResult(0, native.VERSION, ""),
            ProbeResult(0, help_text.replace(native.AGENT_VERSION, "9.9.9"), ""),
        ]
    )
    monkeypatch.setattr(native, "probe", lambda *a: next(values))
    assert native.create_adapter().detect(DetectionContext(HarnessSettings(), {})).status == (
        "unsupported-version"
    )


def test_engine_default_protection_idempotence_rotation_and_rollback(monkeypatch, tmp_path):
    from harness_sync.config import yaml_bytes
    from harness_sync.engine import Engine, Selection
    from harness_sync.filesystem import replace
    from harness_sync.registry import Registry

    a, p, ctx = native.create_adapter(), provider(), context(tmp_path)
    monkeypatch.setattr(a, "detect", lambda _: ctx.detection)
    replace(
        ctx.paths.config, yaml_bytes({"version": 1, "providers": [p.model_dump(exclude_none=True)]})
    )
    keys = tmp_path / "secrets.yaml"
    replace(keys, yaml_bytes({"version": 1, "keys": {"one": "test-one"}}))
    default = ctx.detection.default_paths[0]
    replace(default, b'{"keep":"unchanged"}')
    engine = Engine(ctx.paths, Registry((a,)))
    selection = Selection((a.id,), profiles_only=True, commands=False)
    engine.sync(selection)
    files = [x.path for x in a.profiles(p, ctx)]
    times = [x.stat().st_mtime_ns for x in files]
    engine.sync(selection)
    assert times == [x.stat().st_mtime_ns for x in files]
    assert default.read_bytes() == b'{"keep":"unchanged"}'
    assert all(x.stat().st_mode & 0o777 == 0o600 for x in files)
    before = {f: f.read_bytes() for f in files}
    replace(keys, yaml_bytes({"version": 1, "keys": {"one": "rotated"}}))
    _, transaction = engine.sync(selection)
    assert any(b"rotated" in f.read_bytes() for f in files)
    with engine.store.locked():
        engine.store.rollback(transaction)
    assert before == {f: f.read_bytes() for f in files}
