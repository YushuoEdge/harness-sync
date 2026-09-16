import json
import os
import stat
import subprocess
from pathlib import Path

import pytest
from conftest import document

from harness_sync.config import yaml_bytes
from harness_sync.engine import Engine, Selection
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.filesystem import replace
from harness_sync.registry import Registry


def save(engine, config):
    replace(engine.paths.config, yaml_bytes(config))


def test_plan_read_only_and_no_secrets(project):
    engine, _, _ = project
    plan = engine.plan()
    serialized = json.dumps(plan.public()) + repr(plan)
    assert "s3cr3t" not in serialized
    assert not engine.paths.state.exists()
    assert not engine.paths.generated.exists()
    assert "vendor/one-daily" in serialized


def test_sync_is_idempotent_and_does_not_touch_defaults(project):
    engine, adapter, _ = project
    default = adapter.root / "native.json"
    replace(default, b'{"user_setting": 123}')
    plan, ident = engine.sync()
    assert ident
    assert default.read_bytes() == b'{"user_setting": 123}'
    paths = [a.path for a, _ in plan.artifacts] + [engine.store.path]
    stats = {p: p.stat().st_mtime_ns for p in paths}
    assert engine.sync()[1] is None
    assert stats == {p: p.stat().st_mtime_ns for p in paths}
    assert all(stat.S_IMODE(p.stat().st_mode) in (0o600, 0o700) for p in paths)
    assert "s3cr3t" not in engine.store.path.read_text()


def test_default_merges_unrelated_changes_and_rejects_owned_edits(project):
    engine, adapter, config = project
    native = adapter.root / "native.json"
    replace(native, b'{"unrelated": 1, "model": "old"}')
    selection = Selection(write_defaults=True, default_provider="one")
    engine.sync(selection)
    data = json.loads(native.read_bytes())
    assert data["model"] == "vendor/one-daily"
    data["unrelated"] = 2
    replace(native, json.dumps(data).encode())
    engine.sync(selection)
    assert json.loads(native.read_bytes())["unrelated"] == 2
    data["model"] = "manual-edit"
    replace(native, json.dumps(data).encode())
    with pytest.raises(ConflictError):
        engine.sync(selection)
    assert json.loads(native.read_bytes())["model"] == "manual-edit"
    assert config["providers"]


def test_profiles_only_overrides_persisted_default_authorization(project):
    engine, adapter, config = project
    config["harnesses"] = {"fake": {"default": {"write": True, "provider": "one"}}}
    save(engine, config)
    engine.sync(Selection(profiles_only=True))
    assert not (adapter.root / "native.json").exists()
    engine.prepare_launch("fake", "one", "daily", ())
    assert (adapter.root / "native.json").exists()


def test_unowned_profile_and_edited_owned_profile_blocked(project):
    engine, _, _ = project
    path = engine.paths.profile("fake", "one") / "profile.json"
    replace(path, b"user-owned")
    with pytest.raises(ConflictError):
        engine.sync()
    path.unlink()
    engine.sync()
    replace(path, b"user-edited")
    with pytest.raises(ConflictError):
        engine.sync()
    assert path.read_bytes() == b"user-edited"


def test_adapter_cannot_sneak_default_file_into_profile_sync(project):
    engine, adapter, _ = project
    adapter.escape = True
    with pytest.raises(ConflictError):
        engine.sync()
    assert not (adapter.root / "native.json").exists()


def test_verify_failure_happens_before_any_output_write(project):
    engine, adapter, _ = project
    adapter.fail_verify = True
    with pytest.raises(ValueError):
        engine.sync()
    assert not engine.paths.generated.exists()


def test_fresh_launch_reads_rotated_keys_and_model_ids(project):
    engine, _, config = project
    config["providers"].extend(document("two", "two")["providers"])
    save(engine, config)
    _, first = engine.prepare_launch("fake", "one", "complex", ("space arg",))
    _, second = engine.prepare_launch("fake", "two", "simple", ())
    assert first.environment["TEST_KEY"] == "s3cr3t-one"
    assert second.environment["TEST_KEY"] == "s3cr3t-two"
    assert first.environment["TEST_MODEL"] == "vendor/one-complex"
    assert second.environment["TEST_MODEL"] == "vendor/two-simple"
    assert first.argv == ("space arg",)
    replace(
        engine.paths.config.parent / "secrets.yaml",
        yaml_bytes(
            {
                "version": 1,
                "keys": {"one": "rotated-key", "two": "s3cr3t-two"},
            }
        ),
    )
    _, rotated = engine.prepare_launch("fake", "one", "daily", ())
    assert rotated.environment["TEST_KEY"] == "rotated-key"
    assert os.environ.get("TEST_KEY") is None


def test_invalid_input_or_secret_in_argv_prevents_launch(project):
    engine, adapter, _ = project
    adapter.bad_argv = True
    with pytest.raises(HarnessSyncError):
        engine.prepare_launch("fake", "one", "daily", ())
    assert not engine.paths.generated.exists()
    replace(engine.paths.config, b"version: [")
    with pytest.raises(HarnessSyncError):
        engine.prepare_launch("fake", "one", "daily", ())


def test_command_collision_preserved(project):
    engine, _, config = project
    command = Path(config["commands"]["bin_dir"]) / "fake-agent-one"
    replace(command, b"existing command", 0o700)
    plan, _ = engine.sync()
    assert command.read_bytes() == b"existing command"
    assert any("collision" in message for message in plan.notices)


def test_symlink_output_rejected(project):
    engine, adapter, _ = project
    target = adapter.root / "innocent"
    target.write_bytes(b"do not touch")
    output = engine.paths.profile("fake", "one") / "profile.json"
    output.parent.mkdir(parents=True)
    output.symlink_to(target)
    with pytest.raises(ConflictError):
        engine.sync()
    assert target.read_bytes() == b"do not touch"


def test_bundled_slots_report_implementation_status(project):
    base, _, _ = project
    registry = Registry.bundled()
    assert len(registry.catalog) == 8
    assert set(registry.adapters) == {"codex"}
    engine = Engine(base.paths, registry)
    detections = engine.detect()
    assert detections["codex"].status != "not-implemented"
    assert all(
        detection.status == "not-implemented"
        for name, detection in detections.items()
        if name != "codex"
    )
    with pytest.raises(UnsupportedError):
        engine.sync(Selection(("pi",)))


def test_wrapper_quoting_and_forwarding(project):
    engine, _, config = project
    plan = engine.plan()
    artifact = next(a for a, _ in plan.artifacts if a.scope == "wrapper")
    data = artifact.render(plan.secrets.scoped(set())).decode()
    assert '"$@"' in data
    assert "s3cr3t" not in data
    result = subprocess.run(["/bin/sh", "-n"], input=data, text=True, capture_output=True)
    assert result.returncode == 0


def test_exec_preserves_environment_and_arguments(project, monkeypatch):
    engine, _, _ = project
    monkeypatch.setenv("STALE_KEY", "wrong")
    monkeypatch.setenv("UNRELATED_VAR", "keep")
    captured = {}

    def fake_exec(executable, argv, env):
        captured.update(executable=executable, argv=argv, env=env)

    monkeypatch.setattr(os, "execve", fake_exec)
    engine.run("fake", "one", "daily", ("a b", "$(literal)"))
    assert captured["argv"][1:] == ("a b", "$(literal)")
    assert "STALE_KEY" not in captured["env"]
    assert captured["env"]["UNRELATED_VAR"] == "keep"
    assert captured["env"]["TEST_KEY"] == "s3cr3t-one"


def test_bare_managed_launch_does_not_select_a_provider(project):
    engine, adapter, _ = project
    _, launch = engine.prepare_launch("fake", None, "daily", ("--help",))
    assert launch.environment == {}
    assert launch.argv == ("--help",)
    assert not (adapter.root / "native.json").exists()


def test_missing_secret_prevents_all_writes(project):
    engine, _, _ = project
    replace(engine.paths.config.parent / "secrets.yaml", yaml_bytes({"version": 1, "keys": {}}))
    with pytest.raises(HarnessSyncError):
        engine.sync()
    assert not engine.paths.generated.exists()


def test_unknown_adapter_options_fail(project):
    engine, _, config = project
    config["providers"][0]["overrides"] = {"fake": {"options": {"unknown": True}}}
    save(engine, config)
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        engine.plan()
    assert not engine.paths.generated.exists()


def test_wrapper_exec_preserves_literal_arguments(project, monkeypatch):
    import sys

    engine, adapter, _ = project
    interpreter = adapter.root / "python path with spaces"
    # Use a stand-in interpreter to observe exactly what the wrapper would execute.
    replace(interpreter, b'#!/bin/sh\nprintf "%s\\n" "$@"\n', 0o700)
    monkeypatch.setattr(sys, "executable", str(interpreter))
    plan, _ = engine.sync()
    wrapper = next(a.path for a, _ in plan.artifacts if a.scope == "wrapper")
    arguments = ["two words", "$(literal)", "quote'and\"double", "--native-flag"]
    result = subprocess.run([str(wrapper), *arguments], capture_output=True, text=True)
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    assert lines[-4:] == arguments
    assert lines[:2] == ["-m", "harness_sync"]
    assert "--provider" in lines
