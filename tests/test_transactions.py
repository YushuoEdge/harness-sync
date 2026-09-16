import json
from pathlib import Path

import pytest

from harness_sync.errors import ConflictError
from harness_sync.filesystem import Snapshot, replace, snapshot
from harness_sync.transactions import StateStore, Write


def test_late_input_change_aborts(project):
    engine, _, _ = project
    with engine.store.locked():
        plan = engine.plan()
        replace(engine.paths.config, b"version: 1\nproviders: []\n")
        with pytest.raises(ConflictError):
            engine._apply(plan)
    assert not engine.paths.generated.exists()


def test_commit_failure_rolls_back_every_written_file(project, monkeypatch):
    engine, _, _ = project
    import harness_sync.transactions as tx

    original = tx.os.replace
    outputs = 0

    def fail_second_output(source, target):
        nonlocal outputs
        if Path(target).is_relative_to(engine.paths.generated) or Path(target).parent.name == "bin":
            outputs += 1
            if outputs == 2:
                raise OSError("injected I/O error")
        return original(source, target)

    monkeypatch.setattr(tx.os, "replace", fail_second_output)
    with pytest.raises(OSError):
        engine.sync()
    assert not (engine.paths.profile("fake", "one") / "profile.json").exists()
    assert not engine.store.pending()
    assert engine.store.read()["owned"] == {}


def test_rollback_and_external_edit_protection(project):
    engine, _, _ = project
    plan, ident = engine.sync()
    profile = engine.paths.profile("fake", "one") / "profile.json"
    original = profile.read_bytes()
    replace(profile, b"manual edit")
    with engine.store.locked(), pytest.raises(ConflictError):
        engine.store.rollback(ident)
    assert profile.read_bytes() == b"manual edit"
    replace(profile, original)
    with engine.store.locked():
        engine.store.rollback(ident)
    assert not profile.exists()
    assert all(not artifact.path.exists() for artifact, _ in plan.artifacts)
    assert engine.store.read()["owned"] == {}


def test_crash_journal_recovers_partial_commit(tmp_path):
    store = StateStore(tmp_path / "state")
    output = tmp_path / "target"
    replace(output, b"old")
    with store.locked():
        ident = store.apply(
            (Write(output, b"new", snapshot(output), "test", "default", merged=True),), {}, {}
        )
        journal = store.root / "transactions" / ident / "journal.json"
        obj = json.loads(journal.read_bytes())
        obj["status"] = "pending"  # simulate crash after final rename, before commit marker
        replace(journal, json.dumps(obj).encode())
        store.recover()
    assert output.read_bytes() == b"old"
    assert not store.pending()


def test_state_loss_does_not_adopt_existing_outputs(project):
    engine, _, _ = project
    engine.sync()
    engine.store.path.unlink()
    with pytest.raises(ConflictError):
        engine.sync()


def test_duplicate_outputs_are_rejected(tmp_path):
    store = StateStore(tmp_path / "state")
    path = tmp_path / "file"
    write = Write(path, b"value", Snapshot(None), "test", "profile")
    with store.locked(), pytest.raises(ConflictError):
        store.apply((write, write), {}, {})


def test_process_lock_blocks_other_process(tmp_path):
    import subprocess
    import sys

    store = StateStore(tmp_path / "state")
    script = """
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_RDWR)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit(7)
sys.exit(0)
"""
    with store.locked():
        result = subprocess.run([sys.executable, "-c", script, str(store.root / "lock")])
        assert result.returncode == 7
    result = subprocess.run([sys.executable, "-c", script, str(store.root / "lock")])
    assert result.returncode == 0


def test_corrupt_backup_prevents_partial_restore(tmp_path):
    store = StateStore(tmp_path / "state")
    first, second = tmp_path / "a", tmp_path / "b"
    replace(first, b"old-a")
    replace(second, b"old-b")
    with store.locked():
        writes = tuple(
            Write(p, b"new", snapshot(p), "test", "default", merged=True) for p in (first, second)
        )
        ident = store.apply(writes, {}, {})
        replace(store.root / "transactions" / ident / "before-0", b"corrupt")
        from harness_sync.errors import TransactionError

        with pytest.raises(TransactionError):
            store.rollback(ident)
    assert first.read_bytes() == second.read_bytes() == b"new"


def test_identical_default_is_owned_without_rewrite(tmp_path):
    store = StateStore(tmp_path / "state")
    target = tmp_path / "native"
    replace(target, b"already desired")
    timestamp = target.stat().st_mtime_ns
    with store.locked():
        store.apply(
            (
                Write(
                    target,
                    b"already desired",
                    snapshot(target),
                    "test/default",
                    "default",
                    merged=True,
                ),
            ),
            {},
            {},
        )
        assert store.baseline(target, store.read()) == b"already desired"
    assert target.stat().st_mtime_ns == timestamp
