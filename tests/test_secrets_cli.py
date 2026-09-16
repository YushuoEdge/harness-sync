import json
import os
import subprocess
import sys

import pytest

from harness_sync.cli import main
from harness_sync.errors import HarnessSyncError
from harness_sync.filesystem import Snapshot
from harness_sync.secrets import SecretStore


def test_shell_export_does_not_execute_value(tmp_path):
    marker = tmp_path / "must-not-exist"
    value = f"quotes'\"; $(touch {marker}); `touch {marker}`"
    store = SecretStore({"provider-key": value})
    script = store.exports().decode() + '\nprintf "%s" "$HS_PROVIDER_KEY"\n'
    result = subprocess.run(["/bin/sh"], input=script, text=True, capture_output=True)
    assert result.stdout == value
    assert not marker.exists()


def test_secret_permissions_and_multiline_values():
    with pytest.raises(HarnessSyncError):
        SecretStore.from_snapshot(Snapshot(b"version: 1\nkeys: {}", 0o644))
    with pytest.raises(HarnessSyncError):
        SecretStore.from_snapshot(Snapshot(b'version: 1\nkeys: {a: "a\\nb"}', 0o600))


def test_cli_initialization_and_secret_lifecycle(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config/config.yaml"
    state = tmp_path / "state"
    prefix = ["--config", str(config), "--state-dir", str(state)]
    main(prefix + ["init"])
    assert config.exists()
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("private-new-key\n"))
    main(prefix + ["secrets", "set", "example", "--stdin"])
    main(prefix + ["secrets", "list"])
    assert "private-new-key" not in capsys.readouterr().out
    main(prefix + ["validate"])
    main(prefix + ["secrets", "delete", "example"])
    assert "example" not in (config.parent / "secrets.yaml").read_text()
    with pytest.raises(SystemExit) as error:
        main(prefix + ["init"])
    assert error.value.code == 2


def test_installed_cli_detect_without_native_execution(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "harness_sync",
            "--config",
            str(tmp_path / "absent.yaml"),
            "--state-dir",
            str(tmp_path / "state"),
            "detect",
            "--json",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": ""},
    )
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)) == 8
    assert all(d["status"] == "not-implemented" for d in json.loads(result.stdout).values())
