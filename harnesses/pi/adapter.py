"""Pi 1.0.0 provider catalogs in persistent isolated agent directories."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, get_field, merge_fields
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef, env_name

VERSION = "1.0.0"
APIS = {
    "anthropic": "anthropic-messages",
    "openai-chat": "openai-completions",
    "openai-responses": "openai-responses",
    "google-genai": "google-generative-ai",
}


def parse(data):
    try:
        value = json.loads(data or b"{}")
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError):
        raise HarnessSyncError("Invalid Pi JSON configuration") from None


def encode(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def catalog(provider):
    models = {}
    for model in provider.models:
        model_id = model.upstream_id("pi")
        entry = {"id": model_id, "name": model_id}
        for source, target in (
            ("context_window", "contextWindow"),
            ("max_output_tokens", "maxTokens"),
            ("reasoning", "reasoning"),
            ("input", "input"),
        ):
            if (value := getattr(model, source)) is not None:
                entry[target] = value
        if model_id in models and models[model_id] != entry:
            raise HarnessSyncError("Repeated Pi model IDs have conflicting metadata")
        models[model_id] = entry
    headers = {}
    for name, value in provider.headers.items():
        # Pi config values can execute !commands: escape static strings structurally.
        headers[name] = (
            "$" + env_name(value.secret)
            if isinstance(value, SecretRef)
            else value.replace("$", "$$").replace("!", "$!")
        )
    return {
        "baseUrl": provider.endpoint_for("pi"),
        "api": APIS[provider.protocol_for("pi")],
        "apiKey": "$" + env_name(provider.api_key.secret),
        "headers": headers,
        "models": list(models.values()),
    }


class PiAdapter(Adapter):
    id = "pi"
    command = "pi"
    protocols = frozenset(APIS)

    def detect(self, context):
        home = absolute(
            context.environment.get("PI_CODING_AGENT_DIR")
            or Path(context.environment.get("HOME", str(Path.home()))) / ".pi/agent"
        )
        models = (
            absolute(context.settings.config_path)
            if context.settings.config_path
            else (home / "models.json")
        )
        paths = (models, models.parent / "settings.json")
        executable = find_executable(self.command, context.environment, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=paths)
        try:
            with tempfile.TemporaryDirectory(prefix="hs-pi-") as directory:
                env = dict(context.environment, PI_CODING_AGENT_DIR=directory, PI_OFFLINE="1")
                version, help_result = (
                    probe(executable, (flag,), env) for flag in ("--version", "--help")
                )
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=paths)
        number = version.stdout.strip()
        supported = (
            number == VERSION
            and version.returncode == help_result.returncode == 0
            and all(
                flag in help_result.stdout
                for flag in ("pi - AI coding assistant", "PI_CODING_AGENT_DIR", "--provider")
            )
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=paths,
            capabilities=("custom-models",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "custom-models" not in context.detection.capabilities:
            raise HarnessSyncError("Pi custom-models capability was not verified")
        if not isinstance(provider.api_key, SecretRef):
            raise HarnessSyncError("Pi requires an explicit API-key reference")
        if any(
            m.reasoning_effort not in {None, "off", "minimal", "low", "medium", "high"}
            for m in provider.models
        ):
            raise HarnessSyncError("Unsupported Pi thinking level")
        # Pi's exact ID matching precedes pattern/thinking-suffix parsing.
        catalog(provider)
        auth = parse(
            context.read(context.paths.runtime(self.id, provider.command_alias) / "auth.json")
        )
        if f"hs-{provider.name}" in auth:
            raise ConflictError("Pi stored authentication overrides the managed provider key")

    def profiles(self, provider, context):
        root = context.paths.runtime(self.id, provider.command_alias)
        data = {"providers": {f"hs-{provider.name}": catalog(provider)}}
        settings = {
            "defaultProvider": f"hs-{provider.name}",
            "defaultModel": provider.model_for("daily").upstream_id(self.id),
        }
        return tuple(
            Artifact(
                root / name,
                "profile",
                f"{self.id}/{provider.name}",
                lambda _, value=value: encode(value),
                parse,
            )
            for name, value in (("models.json", data), ("settings.json", settings))
        )

    def defaults(self, providers, selected, role, context):
        result = []
        for index, path in enumerate(context.detection.default_paths):
            current, baseline = parse(context.read(path)), context.baseline(path)
            previous = parse(baseline) if baseline is not None else None
            changes = {}
            if index == 0:
                desired = {f"hs-{p.name}": catalog(p) for p in providers}
                for name, value in desired.items():
                    if get_field(current, ("providers", name)) is not MISSING and (
                        previous is None or get_field(previous, ("providers", name)) is MISSING
                    ):
                        raise ConflictError("Pi managed provider name already exists")
                    changes[("providers", name)] = value
                for name in (previous or {}).get("providers", {}):
                    if name.startswith("hs-") and name not in desired:
                        changes[("providers", name)] = MISSING
            else:
                changes = {
                    ("defaultProvider",): f"hs-{selected.name}",
                    ("defaultModel",): selected.model_for(role).upstream_id(self.id),
                }

            def render(_, current=current, previous=previous, changes=changes):
                return encode(merge_fields(current, previous, changes))

            result.append(Artifact(path, "default", "pi/default", render, parse, merged=True))
        return tuple(result)

    def launch(self, provider, role, arguments, context, secrets):
        for arg in arguments:
            if arg == "--":
                break
            if arg.split("=", 1)[0] in {
                "--provider",
                "--model",
                "--models",
                "--api-key",
                "--extension",
                "-e",
            } or arg.startswith("-e="):
                raise HarnessSyncError("Pi routing flag conflicts with the managed provider")
        prefix = (
            "--provider",
            f"hs-{provider.name}",
            "--model",
            provider.model_for(role).upstream_id(self.id),
            "--no-extensions",
        )
        effort = provider.model_for(role).reasoning_effort
        if effort is not None:
            prefix += ("--thinking", effort)
        environment = {env_name(key): secrets.get(key) for key in provider.secret_ids()}
        environment["PI_CODING_AGENT_DIR"] = str(
            context.paths.runtime(self.id, provider.command_alias)
        )
        return LaunchSpec(
            prefix + arguments,
            environment,
            frozenset(
                {
                    "PI_CODING_AGENT_DIR",
                    "PI_PACKAGE_DIR",
                    "ANTHROPIC_AUTH_TOKEN",
                    "ANTHROPIC_OAUTH_TOKEN",
                }
            ),
        )


def create_adapter():
    return PiAdapter()
