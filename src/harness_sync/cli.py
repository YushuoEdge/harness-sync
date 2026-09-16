"""Thin CLI; application behavior is available independently through Engine."""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys

from pydantic import ValidationError

from .config import load_config, yaml_bytes
from .engine import Engine, Selection, detection_public
from .errors import HarnessSyncError
from .filesystem import Snapshot, replace, snapshot
from .paths import Paths, absolute
from .secrets import SecretStore


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="harness-sync")
    root.add_argument("--config", help="Canonical YAML path (global option)")
    root.add_argument("--state-dir", help="State directory (global option)")
    root.add_argument("--version", action="version", version="%(prog)s 0.1.0a1")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create empty private configuration and secrets files")
    commands.add_parser("validate", help="Validate canonical configuration and secret references")
    for name in ("detect", "plan", "sync", "doctor"):
        sub = commands.add_parser(name)
        sub.add_argument("--harness", action="append", default=[])
        sub.add_argument("--json", action="store_true", help="Output is JSON (also the default)")
        if name in {"plan", "sync"}:
            sub.add_argument("--profiles-only", action="store_true")
            sub.add_argument("--write-defaults", action="store_true")
            sub.add_argument("--default-provider")
            sub.add_argument("--role", choices=["simple", "daily", "complex"])
            sub.add_argument("--no-commands", action="store_true")
        if name == "sync":
            sub.add_argument("--dry-run", action="store_true")
    run = commands.add_parser("run", help="Sync then replace this process with the harness")
    run.add_argument("harness")
    run.add_argument("--provider")
    run.add_argument("--role", choices=["simple", "daily", "complex"], default="daily")
    run.add_argument("--profiles-only", action="store_true")
    status = commands.add_parser("status")
    status.add_argument("--json", action="store_true")
    rollback = commands.add_parser("rollback")
    rollback.add_argument("transaction")
    secrets = commands.add_parser("secrets").add_subparsers(dest="secret_command", required=True)
    secrets.add_parser("list")
    setter = secrets.add_parser("set")
    setter.add_argument("identifier")
    setter.add_argument("--stdin", action="store_true")
    delete = secrets.add_parser("delete")
    delete.add_argument("identifier")
    return root


def output(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def initialize(paths: Paths) -> None:
    with Engine(paths).store.locked():
        secrets = paths.config.parent / "secrets.yaml"
        if paths.config == secrets or paths.config.is_relative_to(paths.state):
            raise HarnessSyncError("Configuration must not collide with secrets or state")
        if snapshot(paths.config).data is not None or snapshot(secrets).data is not None:
            raise HarnessSyncError("Init refuses to overwrite existing configuration or secrets")
        replace(secrets, yaml_bytes({"version": 1, "keys": {}}))
        replace(
            paths.config,
            yaml_bytes({"version": 1, "providers": [], "secrets_file": "secrets.yaml"}),
        )
    output({"config": str(paths.config), "secrets": str(secrets)})


def secret_command(engine: Engine, args: argparse.Namespace) -> None:
    with engine.store.locked():
        config = load_config(engine.paths.config)
        path = absolute(config.secrets_file, engine.paths.config.parent)
        before = snapshot(path)
        store = SecretStore.from_snapshot(before)
        if args.secret_command == "list":
            output({"keys": store.identifiers()})
            return
        ident = args.identifier
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", ident):
            raise HarnessSyncError("Invalid secret identifier")
        values = {key: store.get(key) for key in store.identifiers()}
        if args.secret_command == "set":
            value = (
                sys.stdin.read().removesuffix("\n") if args.stdin else getpass.getpass("API key: ")
            )
            values[ident] = value
        else:
            if any(ident in p.secret_ids() for p in config.providers):
                raise HarnessSyncError("Remove configuration references before deleting a secret")
            if ident not in values:
                raise HarnessSyncError("Secret does not exist")
            del values[ident]
        data = yaml_bytes({"version": 1, "keys": values})
        SecretStore.from_snapshot(Snapshot(data, 0o600))
        if snapshot(path) != before:
            raise HarnessSyncError("Secrets changed during editing; retry")
        replace(path, data)
    output({"status": "updated"})


def main(argv: list[str] | None = None) -> None:
    raw = list(sys.argv[1:] if argv is None else argv)
    forwarded: tuple[str, ...] = ()
    if "--" in raw:
        index = raw.index("--")
        forwarded, raw = tuple(raw[index + 1 :]), raw[:index]
    args = parser().parse_args(raw)
    if forwarded and args.command != "run":
        parser().error("Arguments after -- are supported only by run")
    try:
        paths = Paths.discover(args.config, args.state_dir)
        engine = Engine(paths)
        if args.command == "init":
            initialize(paths)
        elif args.command == "validate":
            engine.validate()
            output(
                {"status": "valid", "native_adapters": "Only implemented options schemas checked"}
            )
        elif args.command in {"detect", "doctor"}:
            results = engine.detect(tuple(args.harness))
            report = {k: detection_public(v) for k, v in results.items()}
            if args.command == "detect":
                with engine.store.locked():
                    engine.store.recover()
                    engine.store.apply((), {}, report)
            output(report)
        elif args.command in {"plan", "sync"}:
            selection = Selection(
                tuple(args.harness),
                profiles_only=args.profiles_only,
                write_defaults=args.write_defaults,
                default_provider=args.default_provider,
                role=args.role,
                commands=not args.no_commands,
            )
            if args.command == "plan" or args.dry_run:
                output(engine.plan(selection).public())
            else:
                plan, transaction = engine.sync(selection)
                output({**plan.public(), "transaction": transaction, "status": "synced"})
        elif args.command == "status":
            # Baselines and fingerprints are private implementation details.
            state = engine.store.read()
            output(
                {
                    "transaction": state.get("transaction"),
                    "detections": state["detections"],
                    "managed_files": len(state["owned"]),
                    "recovery_required": engine.store.pending(),
                }
            )
        elif args.command == "run":
            engine.run(args.harness, args.provider, args.role, forwarded, args.profiles_only)
        elif args.command == "rollback":
            with engine.store.locked():
                engine.store.recover()
                engine.store.rollback(args.transaction)
            output({"status": "rolled-back"})
        elif args.command == "secrets":
            secret_command(engine, args)
    except HarnessSyncError as exc:
        print(f"harness-sync: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code) from None
    except ValidationError:
        print("harness-sync: Invalid adapter options", file=sys.stderr)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception:
        # Native parser/subprocess exceptions can carry secret values or source snippets.
        print(
            "harness-sync: Operation failed; no exception payload printed to protect secrets",
            file=sys.stderr,
        )
        raise SystemExit(5) from None
