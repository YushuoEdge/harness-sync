"""Application orchestration. Adapters never own the write/permission boundary."""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import parse_config
from .contracts import Artifact, Detection, DetectionContext, LaunchSpec, RenderContext
from .errors import ConflictError, HarnessSyncError, UnsupportedError
from .filesystem import Snapshot, snapshot
from .paths import Paths, absolute
from .registry import Registry
from .schema import Config, HarnessSettings, Provider, Role
from .secrets import SecretStore
from .transactions import StateStore, Write


@dataclass(frozen=True)
class Selection:
    harnesses: tuple[str, ...] = ()
    provider: str | None = None
    profiles_only: bool = False
    write_defaults: bool = False
    default_provider: str | None = None
    role: Role | None = None
    commands: bool = True


@dataclass
class Plan:
    artifacts: list[tuple[Artifact, frozenset[str]]] = field(default_factory=list, repr=False)
    guards: dict[Path, Snapshot] = field(default_factory=dict, repr=False)
    detections: dict[str, Detection] = field(default_factory=dict)
    contexts: dict[str, RenderContext] = field(default_factory=dict, repr=False)
    config: Config | None = field(default=None, repr=False)
    secrets: SecretStore | None = field(default=None, repr=False)
    notices: list[str] = field(default_factory=list)
    selections: list[dict[str, str]] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        # Do not serialize dataclass internals, closures, native files or secrets.
        return {
            "files": [
                {"path": str(a.path), "scope": a.scope, "owner": a.owner, "operation": "reconcile"}
                for a, _ in self.artifacts
            ],
            "detections": {key: detection_public(value) for key, value in self.detections.items()},
            "models": self.selections,
            "notices": self.notices,
            "preview": "Metadata only; native content and secrets are never printed",
        }


def detection_public(result: Detection) -> dict[str, Any]:
    return {
        "status": result.status,
        "executable": str(result.executable) if result.executable else None,
        "version": result.version,
        "default_paths": [str(p) for p in result.default_paths],
        "capabilities": list(result.capabilities),
    }


def verify_bytes(data: bytes) -> None:
    if not isinstance(data, bytes):
        raise HarnessSyncError("Artifact renderer must return bytes")


class Engine:
    def __init__(self, paths: Paths, registry: Registry | None = None):
        self.paths = paths
        if (
            paths.config.is_relative_to(paths.state)
            or paths.generated.is_relative_to(paths.state)
            or paths.state.is_relative_to(paths.generated)
        ):
            raise HarnessSyncError("Configuration, generated files and state must not overlap")
        self.registry = registry if registry is not None else Registry.bundled()
        self.store = StateStore(paths.state)

    def _read_inputs(self, plan: Plan) -> tuple[Config, SecretStore]:
        config_snapshot = snapshot(self.paths.config)
        if config_snapshot.data is None:
            raise HarnessSyncError("Configuration is missing; run init first")
        config = parse_config(config_snapshot.data)
        unknown = set(config.harnesses) - self.registry.catalog.keys()
        for provider in config.providers:
            unknown |= set(provider.overrides) - self.registry.catalog.keys()
            for model in provider.models:
                unknown |= set(model.overrides) - self.registry.catalog.keys()
        if unknown:
            raise HarnessSyncError("Configuration refers to an unknown harness")
        secret_path = absolute(config.secrets_file, self.paths.config.parent)
        source = snapshot(secret_path)
        secrets = SecretStore.from_snapshot(source)
        plan.guards.update({self.paths.config: config_snapshot, secret_path: source})
        plan.config, plan.secrets = config, secrets
        return config, secrets

    def validate(self) -> None:
        plan = Plan()
        config, secrets = self._read_inputs(plan)
        for provider in config.providers:
            secrets.require(provider.secret_ids())
        for ident, adapter in self.registry.adapters.items():
            settings = config.harnesses.get(ident, HarnessSettings())
            adapter.settings_schema.model_validate(settings.options)
            for provider in config.providers:
                override = provider.overrides.get(ident)
                adapter.provider_options_schema.model_validate(override.options if override else {})
                for model in provider.models:
                    mo = model.overrides.get(ident)
                    adapter.model_options_schema.model_validate(mo.options if mo else {})

    def detect(self, selections: tuple[str, ...] = ()) -> dict[str, Detection]:
        source = snapshot(self.paths.config)
        config = parse_config(source.data) if source.data is not None else None
        return {
            ident: self.registry.detect(
                ident,
                DetectionContext(
                    config.harnesses.get(ident, HarnessSettings()) if config else HarnessSettings(),
                    dict(os.environ),
                ),
            )
            for ident in self.registry.select(selections)
        }

    def plan(self, selection: Selection | None = None) -> Plan:
        selection = selection or Selection()
        if selection.profiles_only and selection.write_defaults:
            raise HarnessSyncError("Cannot combine profiles-only and write-defaults")
        if self.store.pending():
            raise ConflictError("Interrupted transaction; run sync to recover before planning")
        plan = Plan()
        config, secrets = self._read_inputs(plan)
        state = self.store.read()
        plan.guards[self.store.path] = snapshot(self.store.path)
        selected = self.registry.select(selection.harnesses)
        explicitly_selected = bool(selection.harnesses and selection.harnesses != ("all",))

        def read(path: Path) -> bytes | None:
            before = snapshot(path)
            if path in plan.guards and plan.guards[path] != before:
                raise ConflictError("File changed while building plan")
            plan.guards[path] = before
            return before.data

        for ident in selected:
            settings = config.harnesses.get(ident, HarnessSettings())
            detection = self.registry.detect(ident, DetectionContext(settings, dict(os.environ)))
            plan.detections[ident] = detection
            if detection.status != "installed":
                if explicitly_selected:
                    raise UnsupportedError("Selected harness has no verified installed adapter")
                plan.notices.append(f"{ident}: {detection.status}")
                continue
            adapter = self.registry.adapters[ident]
            if detection.executable is None or not detection.executable.is_absolute():
                raise HarnessSyncError("Adapter did not provide an absolute executable")
            context = RenderContext(
                self.paths, detection, settings, read, lambda path: self.store.baseline(path, state)
            )
            plan.contexts[ident] = context
            providers = (
                tuple(config.provider(key) for key in settings.providers)
                if (settings.providers is not None)
                else tuple(
                    p for p in config.providers if p.protocol_for(ident) in adapter.protocols
                )
            )
            if selection.provider:
                chosen = config.provider(selection.provider)
                if chosen.name not in {p.name for p in providers}:
                    raise HarnessSyncError(
                        "Provider is excluded or incompatible with selected harness"
                    )
                profiles = (chosen,)
            else:
                profiles = providers
            for provider in profiles:
                adapter.validate(provider, context)
                secrets.require(provider.secret_ids())
                for model in provider.models:
                    plan.selections.append(
                        {
                            "harness": ident,
                            "provider": provider.name,
                            "role": model.role,
                            "label": model.name,
                            "upstream_id": model.upstream_id(ident),
                            "endpoint": provider.endpoint_for(ident),
                        }
                    )
                for artifact in adapter.profiles(provider, context):
                    self._add(plan, artifact, provider.secret_ids(), context, provider)
                if selection.commands:
                    self._wrapper(plan, ident, adapter.command, provider, config, state)
            if not profiles:
                plan.notices.append(f"{ident}: no compatible providers")
            defaults_allowed = (settings.default.write or selection.write_defaults) and not (
                selection.profiles_only
            )
            if defaults_allowed:
                key = selection.default_provider or settings.default.provider
                if key is None:
                    raise HarnessSyncError("A default provider must be explicitly selected")
                default = config.provider(key)
                if default.name not in {p.name for p in providers}:
                    raise HarnessSyncError("Default provider is excluded or incompatible")
                for provider in providers:
                    adapter.validate(provider, context)
                    secrets.require(provider.secret_ids())
                secret_ids = set().union(*(p.secret_ids() for p in providers))
                for artifact in adapter.defaults(
                    providers, default, selection.role or settings.default.role, context
                ):
                    self._add(plan, artifact, secret_ids, context, None, default_allowed=True)
        if plan.artifacts:
            plan.artifacts.append(
                (
                    Artifact(
                        self.paths.generated / "env.sh",
                        "environment",
                        "core/environment",
                        lambda store: store.exports(),
                        verify_bytes,
                    ),
                    frozenset(secrets.identifiers()),
                )
            )
        for artifact, _ in plan.artifacts:
            read(artifact.path)
        # Avoid emitting secrets accidentally embedded in arbitrary labels/options.
        import json

        if secrets.contains_secret(json.dumps(plan.public())):
            raise HarnessSyncError("Plan metadata overlaps a secret; refusing to print it")
        return plan

    def _add(
        self,
        plan: Plan,
        artifact: Artifact,
        secret_ids: set[str],
        context: RenderContext,
        provider: Provider | None,
        default_allowed: bool = False,
    ) -> None:
        path = artifact.path
        if not path.is_absolute() or path != absolute(path):
            raise ConflictError("Adapter output must be an absolute normalized path")
        defaults = context.detection.default_paths
        if default_allowed:
            if artifact.scope != "default" or path not in defaults or not artifact.merged:
                raise ConflictError("Default artifact must be a declared structural merge")
        else:
            roots = (
                self.paths.profile(context.detection.harness, provider.command_alias),
                self.paths.runtime(context.detection.harness, provider.command_alias),
            )
            if (
                artifact.scope != "profile"
                or artifact.merged
                or path in defaults
                or not (
                    any(path.is_relative_to(root) for root in roots)
                    or path in context.detection.profile_paths
                )
            ):
                raise ConflictError("Profile artifact escapes its declared scope")
        if artifact.mode != 0o600 or not artifact.owner.startswith(context.detection.harness + "/"):
            raise ConflictError("Adapter artifact has an invalid mode or owner")
        if (
            path in (self.paths.config, self.store.path)
            or path in plan.guards
            and (path == absolute(plan.config.secrets_file, self.paths.config.parent))
        ):
            raise ConflictError("Adapter output collides with framework input/state")
        if any(a.path == path for a, _ in plan.artifacts):
            raise ConflictError("Adapter outputs collide")
        plan.artifacts.append((artifact, frozenset(secret_ids)))

    def _wrapper(
        self,
        plan: Plan,
        ident: str,
        command: str,
        provider: Provider,
        config: Config,
        state: dict[str, Any],
    ) -> None:
        target = absolute(config.commands.bin_dir, self.paths.config.parent) / (
            f"{command}-{provider.command_alias}"
        )
        existing = shutil.which(target.name)
        if (target.exists() and str(target) not in state["owned"]) or (
            existing and absolute(existing) != target
        ):
            plan.notices.append(
                f"{ident}/{provider.command_alias}: command collision; skipped wrapper"
            )
            return
        args = [
            sys.executable,
            "-m",
            "harness_sync",
            "--config",
            str(self.paths.config),
            "--state-dir",
            str(self.paths.state),
            "run",
            ident,
            "--provider",
            provider.command_alias,
            "--",
        ]
        data = (
            "#!/bin/sh\n# harness-sync managed wrapper\nexec " + shlex.join(args) + ' "$@"\n'
        ).encode()
        plan.artifacts.append(
            (
                Artifact(
                    target,
                    "wrapper",
                    f"{ident}/{provider.name}",
                    lambda _: data,
                    verify_bytes,
                    mode=0o700,
                ),
                frozenset(),
            )
        )

    def _apply(self, plan: Plan) -> str | None:
        writes = []
        for artifact, identifiers in plan.artifacts:
            data = artifact.render(plan.secrets.scoped(set(identifiers)))
            verify_bytes(data)
            artifact.verify(data)
            writes.append(
                Write(
                    artifact.path,
                    data,
                    plan.guards[artifact.path],
                    artifact.owner,
                    artifact.scope,
                    artifact.mode,
                    artifact.merged,
                )
            )
        return self.store.apply(
            tuple(writes), plan.guards, {k: detection_public(v) for k, v in plan.detections.items()}
        )

    def sync(self, selection: Selection | None = None) -> tuple[Plan, str | None]:
        selection = selection or Selection()
        with self.store.locked():
            self.store.recover()
            plan = self.plan(selection)
            if not plan.contexts:
                raise UnsupportedError("No selected harness has an implemented, verified adapter")
            return plan, self._apply(plan)

    def prepare_launch(
        self,
        harness: str,
        provider: str | None,
        role: Role,
        arguments: tuple[str, ...],
        profiles_only: bool = False,
    ) -> tuple[Path, LaunchSpec]:
        with self.store.locked():
            self.store.recover()
            plan = self.plan(Selection((harness,), provider, profiles_only, commands=False))
            context = plan.contexts[harness]
            adapter = self.registry.adapters[harness]
            if provider:
                chosen = plan.config.provider(provider)
                launch = adapter.launch(
                    chosen, role, arguments, context, plan.secrets.scoped(chosen.secret_ids())
                )
            else:
                launch = LaunchSpec(arguments)
            # Do not apply anything if argument/auth routing validation failed.
            if any(plan.secrets.contains_secret(arg) for arg in launch.argv):
                raise HarnessSyncError("Adapter placed a secret in process arguments")
            if any("\x00" in arg for arg in launch.argv):
                raise HarnessSyncError("Invalid launch argument")
            for key, value in launch.environment.items():
                if not key or "=" in key or "\x00" in key or "\x00" in value:
                    raise HarnessSyncError("Invalid launch environment")
            executable = context.detection.executable
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise UnsupportedError("Detected executable is no longer available")
            with executable.open("rb") as stream:
                if b"harness-sync managed wrapper" in stream.read(256):
                    raise ConflictError("Refusing recursive launch of a managed wrapper")
            self._apply(plan)
            return executable, launch

    def run(
        self,
        harness: str,
        provider: str | None,
        role: Role,
        arguments: tuple[str, ...],
        profiles_only: bool = False,
    ) -> None:
        executable, launch = self.prepare_launch(harness, provider, role, arguments, profiles_only)
        environment = dict(os.environ)
        for key in launch.unset:
            environment.pop(key, None)
        environment.update(launch.environment)
        # Replace the process: native TTY, current directory, signals and exit code are preserved.
        os.execve(executable, (str(executable), *launch.argv), environment)
