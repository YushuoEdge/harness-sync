"""Locked, journaled file replacement with conservative crash recovery.

There is no cross-file atomic rename. Readers/launchers use the same lock; native
processes outside this tool may observe intermediate files during a commit.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConflictError, TransactionError
from .filesystem import Snapshot, check_path, fsync_dir, private_dir, replace, snapshot, stage


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


@dataclass(frozen=True)
class Write:
    path: Path
    data: bytes = field(repr=False)
    expected: Snapshot = field(repr=False)
    owner: str
    scope: str
    mode: int = 0o600
    merged: bool = False


class StateStore:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "state.json"

    @contextmanager
    def locked(self) -> Iterator[None]:
        private_dir(self.root)
        os.chmod(self.root, 0o700)
        lock = self.root / "lock"
        check_path(lock)
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def read(self) -> dict[str, Any]:
        data = snapshot(self.path).data
        if data is None:
            return {"version": 1, "owned": {}, "detections": {}}
        try:
            state = json.loads(data)
            if state["version"] != 1 or not isinstance(state["owned"], dict):
                raise ValueError
            return state
        except (ValueError, KeyError, TypeError):
            raise TransactionError("Invalid state file; refusing to discard ownership") from None

    def key(self, create: bool = False) -> bytes:
        path = self.root / "fingerprint.key"
        source = snapshot(path)
        if source.data is None:
            if not create:
                raise TransactionError("Ownership fingerprint key is missing")
            data = secrets.token_bytes(32)
            replace(path, data)
            return data
        if len(source.data) != 32 or source.mode & 0o077:
            raise TransactionError("Invalid or insecure ownership fingerprint key")
        return source.data

    def digest(self, data: bytes | None) -> str | None:
        return hmac.new(self.key(), data, hashlib.sha256).hexdigest() if data is not None else None

    def baseline(self, path: Path, state: dict[str, Any]) -> bytes | None:
        record = state["owned"].get(str(path))
        if record is None:
            return None
        relative = Path(record["baseline"])
        if relative.is_absolute() or ".." in relative.parts:
            raise TransactionError("Invalid baseline path")
        data = snapshot(self.root / relative).data
        if data is None or self.digest(data) != record["digest"]:
            raise TransactionError("Managed baseline is missing or changed")
        return data

    def _journals(self) -> list[Path]:
        directory = self.root / "transactions"
        check_path(directory)
        if not directory.exists():
            return []
        return sorted(directory.glob("*/journal.json"))

    def pending(self) -> bool:
        return any(json.loads(snapshot(p).data)["status"] == "pending" for p in self._journals())

    def recover(self) -> None:
        for journal in self._journals():
            obj = json.loads(snapshot(journal).data)
            if obj["status"] == "pending":
                self._restore(journal, obj)

    def rollback(self, transaction_id: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
            raise TransactionError("Invalid transaction identifier")
        journal = self.root / "transactions" / transaction_id / "journal.json"
        data = snapshot(journal).data
        if data is None:
            raise TransactionError("Transaction does not exist")
        obj = json.loads(data)
        if obj["status"] != "committed" or self.read().get("transaction") != transaction_id:
            raise ConflictError("Only the latest committed transaction can be rolled back")
        self._restore(journal, obj)

    def _restore(self, journal: Path, obj: dict[str, Any]) -> None:
        # Check everything first; recovery itself may also be interrupted and retried.
        for entry in obj["entries"]:
            current = snapshot(Path(entry["path"]))
            signature = (self.digest(current.data), current.mode)
            old = (entry["before_digest"], entry["before_mode"])
            new = (entry["after_digest"], entry["after_mode"])
            if signature not in (old, new):
                raise ConflictError("Recovery blocked by an external edit; retained transaction")
        # Validate every backup before changing any output.
        for entry in obj["entries"]:
            if entry["before_digest"] is not None:
                backup = snapshot(journal.parent / entry["before_file"]).data
                if backup is None or self.digest(backup) != entry["before_digest"]:
                    raise TransactionError("Transaction backup is missing or changed")
        # A crash during manual rollback must also be recoverable on the next sync.
        obj["status"] = "pending"
        replace(journal, json_bytes(obj))
        for entry in reversed(obj["entries"]):
            path = Path(entry["path"])
            if entry["before_digest"] is None:
                path.unlink(missing_ok=True)
                fsync_dir(path.parent)
            else:
                backup = snapshot(journal.parent / entry["before_file"]).data
                if backup is None or self.digest(backup) != entry["before_digest"]:
                    raise TransactionError("Transaction backup is missing or changed")
                replace(path, backup, entry["before_mode"])
        obj["status"] = "rolled-back"
        replace(journal, json_bytes(obj))

    def apply(
        self,
        writes: tuple[Write, ...],
        guards: dict[Path, Snapshot],
        detections: dict[str, Any],
    ) -> str | None:
        """Caller holds locked(). All render/verify work must have completed first."""
        self.recover()
        previous_state = snapshot(self.path)
        state = self.read()
        self.key(create=previous_state.data is None and not self._journals())
        for path, before in guards.items():
            if snapshot(path) != before:
                raise ConflictError("An input or native config changed during planning")
        changed = []
        recorded = []
        seen = set()
        for write in writes:
            if write.path in seen:
                raise ConflictError("Two artifacts target the same file")
            seen.add(write.path)
            if snapshot(write.path) != write.expected:
                raise ConflictError("An output changed during planning")
            owned = state["owned"].get(str(write.path))
            if owned and owned["owner"] != write.owner:
                raise ConflictError("Artifact is owned by a different scope")
            if owned and not write.merged:
                if (
                    self.digest(write.expected.data) != owned["digest"]
                    or write.expected.mode != owned["mode"]
                ):
                    raise ConflictError("Managed artifact was edited outside harness-sync")
            if not owned and write.expected.data is not None and write.scope != "default":
                raise ConflictError("Refusing to overwrite an unowned profile or command")
            if write.merged and write.scope != "default":
                raise ConflictError("Only default files may use structural merge semantics")
            if write.expected != Snapshot(write.data, write.mode):
                changed.append(write)
            if write.expected != Snapshot(write.data, write.mode) or owned is None:
                recorded.append(write)
        state["detections"].update(detections)
        if not recorded and state == self.read():
            return None
        ident = uuid.uuid4().hex
        directory = self.root / "transactions" / ident
        private_dir(directory)
        entries = []
        staged: list[tuple[Write, Path]] = []
        try:
            for index, write in enumerate(recorded):
                baseline = directory / f"after-{index}"
                replace(baseline, write.data)
                state["owned"][str(write.path)] = {
                    "owner": write.owner,
                    "scope": write.scope,
                    "digest": self.digest(write.data),
                    "mode": write.mode,
                    "baseline": str(baseline.relative_to(self.root)),
                }
            state["transaction"] = ident
            state_write = Write(self.path, json_bytes(state), previous_state, "core", "state")
            for index, write in enumerate([*changed, state_write]):
                before_file = f"before-{index}"
                if write.expected.data is not None:
                    replace(directory / before_file, write.expected.data)
                temporary = stage(write.path, write.data, write.mode)
                staged.append((write, temporary))
                entries.append(
                    {
                        "path": str(write.path),
                        "before_file": before_file,
                        "before_digest": self.digest(write.expected.data),
                        "before_mode": write.expected.mode,
                        "after_digest": self.digest(write.data),
                        "after_mode": write.mode,
                    }
                )
            journal = directory / "journal.json"
            obj = {"version": 1, "status": "pending", "entries": entries}
            replace(journal, json_bytes(obj))
            for write, temporary in staged:
                if snapshot(write.path) != write.expected:
                    raise ConflictError("An output changed during commit")
                os.replace(temporary, write.path)
                fsync_dir(write.path.parent)
            obj["status"] = "committed"
            replace(journal, json_bytes(obj))
            return ident
        except BaseException:
            journal = directory / "journal.json"
            if journal.exists():
                self._restore(journal, json.loads(snapshot(journal).data))
            raise
        finally:
            for _, temporary in staged:
                temporary.unlink(missing_ok=True)
