from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

import harnesses.codex.adapter as codex_module
from harness_sync.config import yaml_bytes
from harness_sync.contracts import Detection, DetectionContext, RenderContext
from harness_sync.detection import ProbeResult
from harness_sync.engine import Engine, Selection
from harness_sync.errors import ConflictError, HarnessSyncError
from harness_sync.filesystem import replace
from harness_sync.paths import Paths
from harness_sync.registry import Registry
from harness_sync.schema import HarnessSettings, Provider
from harness_sync.secrets import SecretStore
from harnesses.codex.adapter import CodexAdapter


def provider(name: str = "one", alias: str | None = "first") -> Provider:
    return Provider.model_validate(
        {
            "name": name,
            "alias": alias,
            "type": "openai-responses",
            "base_url": f"https://{name}.invalid/v1",
            "api_key": {"secret": f"{name}_key"},
            "headers": {
                "X-Static": "visible",
                "X-Secret": {"secret": f"{name}_header"},
            },
            "models": [
                {
                    "name": "same label",
                    "id": f"vendor/{name}-{role}",
                    "role": role,
                    "reasoning_effort": "high" if role == "complex" else None,
                }
                for role in ("simple", "daily", "complex")
            ],
        }
    )


def context(tmp_path: Path, current: bytes | None = None, baseline: bytes | None = None):
    native = tmp_path / "codex"
    default = native / "config.toml"
    detection = Detection(
        "codex",
        "installed",
        Path(sys.executable),
        "0.154.0",
        default_paths=(default,),
        profile_roots=(native,),
        capabilities=("profile-v2", "responses"),
    )
    return RenderContext(
        Paths(tmp_path / "config/config.yaml", tmp_path / "state"),
        detection,
        HarnessSettings(),
        lambda path: current if path == default else None,
        lambda path: baseline if path == default else None,
    )


def secrets(*providers: Provider) -> SecretStore:
    identifiers = set().union(*(item.secret_ids() for item in providers))
    return SecretStore({identifier: f"value-for-{identifier}" for identifier in identifiers})


def test_detects_profile_v2_fixture_and_isolates_probe(monkeypatch, tmp_path):
    fixture = Path(__file__).parents[1] / "fixtures"
    results = iter(
        (
            ProbeResult(0, (fixture / "codex-0.154.0-version.txt").read_text(), ""),
            ProbeResult(0, (fixture / "codex-0.154.0-help.txt").read_text(), ""),
        )
    )
    environments = []
    monkeypatch.setattr(codex_module, "find_executable", lambda *args: Path(sys.executable))

    def fake_probe(executable, arguments, environment):
        environments.append(environment)
        return next(results)

    monkeypatch.setattr(codex_module, "probe", fake_probe)
    settings = HarnessSettings(config_path=str(tmp_path / "native/config.toml"))
    result = CodexAdapter().detect(DetectionContext(settings, {"PATH": ""}))
    assert result.status == "installed"
    assert result.version == "0.154.0"
    assert result.profile_roots == (tmp_path / "native",)
    assert len({env["CODEX_HOME"] for env in environments}) == 1
    assert environments[0]["CODEX_HOME"] != str(tmp_path / "native")


def test_unknown_or_old_version_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_module, "find_executable", lambda *args: Path(sys.executable))
    results = iter(
        (
            ProbeResult(0, "codex-cli 0.133.9", ""),
            ProbeResult(
                0,
                "--profile <CONFIG_PROFILE_V2> Layer $CODEX_HOME/<name>.config.toml",
                "",
            ),
        )
    )
    monkeypatch.setattr(codex_module, "probe", lambda *args: next(results))
    result = CodexAdapter().detect(
        DetectionContext(HarnessSettings(config_path=str(tmp_path / "config.toml")), {})
    )
    assert result.status == "unsupported-version"
    assert not result.capabilities


def test_profiles_cover_roles_preserve_upstream_ids_and_contain_no_secrets(tmp_path):
    item = provider()
    adapter = CodexAdapter()
    render_context = context(tmp_path)
    adapter.validate(item, render_context)
    artifacts = adapter.profiles(item, render_context)
    assert len(artifacts) == 6
    assert {artifact.path.parent for artifact in artifacts} == {
        tmp_path / "codex",
        tmp_path / "config/generated/profiles/codex/first",
    }
    for artifact in artifacts:
        data = artifact.render(secrets(item))
        artifact.verify(data)
        parsed = tomllib.loads(data.decode())
        role = artifact.path.stem.removeprefix("hs-first-").removesuffix(".config")
        assert parsed["model"] == f"vendor/one-{role}"
        assert parsed["model_provider"] == "hs-one"
        assert parsed["model_providers"]["hs-one"]["env_key"] == "HS_ONE_KEY"
        assert parsed["model_providers"]["hs-one"]["env_http_headers"] == {
            "X-Secret": "HS_ONE_HEADER"
        }
        assert b"value-for" not in data


def test_default_merge_preserves_comments_and_unrelated_tables(tmp_path):
    item = provider()
    current = b"# user comment\ntheme = \"dark\"\n\n[mcp_servers.keep]\ncommand = \"tool\"\n"
    adapter = CodexAdapter()
    artifact = adapter.defaults((item,), item, "complex", context(tmp_path, current))[0]
    rendered = artifact.render(secrets(item))
    artifact.verify(rendered)
    assert b"# user comment" in rendered
    parsed = tomllib.loads(rendered.decode())
    assert parsed["theme"] == "dark"
    assert parsed["mcp_servers"]["keep"]["command"] == "tool"
    assert parsed["model"] == "vendor/one-complex"
    assert parsed["model_reasoning_effort"] == "high"
    assert parsed["model_providers"]["hs-one"]["base_url"] == "https://one.invalid/v1"


def test_default_merge_rejects_changed_owned_provider(tmp_path):
    item = provider()
    adapter = CodexAdapter()
    initial = adapter.defaults((item,), item, "daily", context(tmp_path))[0].render(secrets(item))
    changed = initial.replace(b"https://one.invalid/v1", b"https://changed.invalid/v1")
    artifact = adapter.defaults((item,), item, "daily", context(tmp_path, changed, initial))[0]
    with pytest.raises(ConflictError):
        artifact.render(secrets(item))


def test_launch_pins_profile_model_and_credentials(tmp_path):
    item = provider()
    launch = CodexAdapter().launch(
        item,
        "daily",
        ("exec", "prompt with spaces"),
        context(tmp_path),
        secrets(item),
    )
    assert launch.argv == (
        "--profile",
        "hs-first-daily",
        "--model",
        "vendor/one-daily",
        "exec",
        "prompt with spaces",
    )
    assert launch.environment == {
        "HS_ONE_HEADER": "value-for-one_header",
        "HS_ONE_KEY": "value-for-one_key",
    }
    assert "OPENAI_API_KEY" in launch.unset


@pytest.mark.parametrize(
    "arguments",
    [
        ("--profile", "other"),
        ("--config=model_provider=\"openai\"",),
        ("exec", "--oss"),
        ("--local-provider=ollama",),
        ("exec", "--ignore-user-config"),
    ],
)
def test_launch_rejects_native_routing_overrides(tmp_path, arguments):
    item = provider()
    with pytest.raises(HarnessSyncError):
        CodexAdapter().launch(item, "daily", arguments, context(tmp_path), secrets(item))


def test_native_model_override_is_allowed_but_profile_stays_pinned(tmp_path):
    item = provider()
    launch = CodexAdapter().launch(
        item,
        "simple",
        ("--model", "vendor/manual", "exec", "hello"),
        context(tmp_path),
        secrets(item),
    )
    assert launch.argv[:2] == ("--profile", "hs-first-simple")
    assert launch.argv.count("--model") == 1


def test_literal_flag_after_native_separator_is_not_treated_as_routing(tmp_path):
    item = provider()
    launch = CodexAdapter().launch(
        item,
        "simple",
        ("exec", "--", "--oss"),
        context(tmp_path),
        secrets(item),
    )
    assert launch.argv[-3:] == ("exec", "--", "--oss")


def test_engine_sync_writes_profiles_but_not_default(tmp_path, monkeypatch):
    item = provider()
    paths = Paths(tmp_path / "config/config.yaml", tmp_path / "state")
    native = tmp_path / "native"
    config = {
        "version": 1,
        "commands": {"bin_dir": str(tmp_path / "bin")},
        "providers": [item.model_dump(mode="json", exclude_none=True)],
        "harnesses": {"codex": {"config_path": str(native / "config.toml")}},
    }
    replace(paths.config, yaml_bytes(config))
    replace(
        paths.config.parent / "secrets.yaml",
        yaml_bytes(
            {
                "version": 1,
                "keys": {
                    "one_key": "key-value",
                    "one_header": "header-value",
                },
            }
        ),
    )
    adapter = CodexAdapter()
    detected = Detection(
        "codex",
        "installed",
        Path(sys.executable),
        "0.154.0",
        default_paths=(native / "config.toml",),
        capabilities=("profile-v2", "responses"),
        profile_roots=(native,),
    )
    monkeypatch.setattr(adapter, "detect", lambda _: detected)
    engine = Engine(paths, Registry((adapter,)))
    plan, transaction = engine.sync(Selection(("codex",), profiles_only=True))
    assert transaction is not None
    assert not (native / "config.toml").exists()
    assert sorted(path.name for path in native.glob("*.config.toml")) == [
        "hs-first-complex.config.toml",
        "hs-first-daily.config.toml",
        "hs-first-simple.config.toml",
    ]
    assert all(b"key-value" not in path.read_bytes() for path in native.glob("*.config.toml"))
    assert sum(artifact.scope == "profile" for artifact, _ in plan.artifacts) == 6
