"""OpenCode 1.18.34 bundled SDKs and highest local configuration overlay."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, get_field
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef, env_name
from harnesses.opencode.jsonc import edit, parse

VERSION = "1.18.34"
SDK = {
    "anthropic": "@ai-sdk/anthropic",
    "openai-chat": "@ai-sdk/openai-compatible",
    "openai-responses": "@ai-sdk/openai",
    "google-genai": "@ai-sdk/google",
}


def catalog(provider):
    models = {}
    for model in provider.models:
        entry = {
            "id": model.upstream_id("opencode"),
            "name": model.upstream_id("opencode"),
            "provider": {
                "npm": SDK[provider.protocol_for("opencode")],
                "api": provider.endpoint_for("opencode"),
            },
            "options": {
                "baseURL": provider.endpoint_for("opencode"),
                "apiKey": "{env:" + env_name(provider.api_key.secret) + "}",
            },
        }
        limit = {}
        if model.context_window is not None:
            limit["context"] = model.context_window
        if model.max_output_tokens is not None:
            limit["output"] = model.max_output_tokens
        if limit:
            entry["limit"] = limit
        if model.reasoning is not None:
            entry["reasoning"] = model.reasoning
        if model.input is not None:
            entry["modalities"] = {"input": model.input, "output": ["text"]}
        if entry["id"] in models and models[entry["id"]] != entry:
            raise HarnessSyncError("Repeated OpenCode model IDs have conflicting metadata")
        models[entry["id"]] = entry
    headers = {
        name: "{env:" + env_name(value.secret) + "}" if isinstance(value, SecretRef) else value
        for name, value in provider.headers.items()
    }
    return {
        "npm": SDK[provider.protocol_for("opencode")],
        "name": f"harness-sync {provider.name}",
        "options": {
            "baseURL": provider.endpoint_for("opencode"),
            "apiKey": "{env:" + env_name(provider.api_key.secret) + "}",
            "headers": headers,
        },
        "models": models,
    }


def document(provider, role):
    name = f"hs-{provider.name}"
    return {
        "provider": {name: catalog(provider)},
        "enabled_providers": [name],
        "model": f"{name}/{provider.model_for(role).upstream_id('opencode')}",
        "small_model": f"{name}/{provider.model_for('simple').upstream_id('opencode')}",
    }


class OpenCodeAdapter(Adapter):
    id = "opencode"
    command = "opencode"
    protocols = frozenset(SDK)

    def detect(self, context):
        root = absolute(
            context.environment.get("XDG_CONFIG_HOME")
            or Path(context.environment.get("HOME", str(Path.home()))) / ".config"
        )
        home = root / "opencode"
        # Native global loading merges JSON then JSONC; choose the last effective file.
        path = (
            absolute(context.settings.config_path)
            if context.settings.config_path
            else (
                home / "opencode.jsonc"
                if (home / "opencode.jsonc").exists()
                else home / "opencode.json"
                if (home / "opencode.json").exists()
                else home / "opencode.jsonc"
            )
        )
        executable = find_executable(self.command, context.environment, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=(path,))
        try:
            with tempfile.TemporaryDirectory(prefix="hs-opencode-") as directory:
                env = dict(
                    context.environment,
                    XDG_CONFIG_HOME=directory + "/config",
                    XDG_DATA_HOME=directory + "/data",
                    XDG_STATE_HOME=directory + "/state",
                    XDG_CACHE_HOME=directory + "/cache",
                    OPENCODE_DISABLE_MODELS_FETCH="1",
                )
                for key in ("OPENCODE_CONFIG", "OPENCODE_CONFIG_DIR", "OPENCODE_CONFIG_CONTENT"):
                    env.pop(key, None)
                version, help_result = (
                    probe(executable, (flag,), env) for flag in ("--version", "--help")
                )
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=(path,))
        number = version.stdout.strip()
        help_text = help_result.stdout + help_result.stderr
        supported = (
            number == VERSION
            and version.returncode == help_result.returncode == 0
            and "opencode run" in help_text
            and "--model" in help_text
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=(path,),
            capabilities=("inline-overlay",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "inline-overlay" not in context.detection.capabilities:
            raise HarnessSyncError("OpenCode inline-overlay capability was not verified")
        if not isinstance(provider.api_key, SecretRef):
            raise HarnessSyncError("OpenCode requires an API-key reference")
        if any(m.reasoning_effort is not None for m in provider.models):
            raise HarnessSyncError("OpenCode reasoning effort requires protocol-specific options")
        if any(
            isinstance(v, str) and ("{env:" in v or "{file:" in v)
            for v in provider.headers.values()
        ):
            raise HarnessSyncError("Static OpenCode headers cannot contain config substitutions")
        catalog(provider)

    def profiles(self, provider, context):
        return tuple(
            Artifact(
                context.paths.profile(self.id, provider.command_alias) / f"{role}.json",
                "profile",
                f"{self.id}/{provider.name}",
                lambda _, role=role: json.dumps(
                    document(provider, role), ensure_ascii=False, indent=2
                ).encode(),
                parse,
            )
            for role in ("simple", "daily", "complex")
        )

    def defaults(self, providers, selected, role, context):
        path = context.detection.default_paths[0]
        current, baseline = context.read(path), context.baseline(path)
        doc, previous = parse(current), parse(baseline) if baseline is not None else None
        changes = {
            ("model",): document(selected, role)["model"],
            ("small_model",): document(selected, role)["small_model"],
        }
        for provider in providers:
            name = f"hs-{provider.name}"
            if get_field(doc, ("provider", name)) is not MISSING and (
                previous is None or get_field(previous, ("provider", name)) is MISSING
            ):
                raise ConflictError("OpenCode managed provider name already exists")
            changes[("provider", name)] = catalog(provider)
        for name in (previous or {}).get("provider", {}):
            if name.startswith("hs-") and ("provider", name) not in changes:
                changes[("provider", name)] = MISSING
        return (
            Artifact(
                path,
                "default",
                "opencode/default",
                lambda _: edit(current, baseline, changes),
                parse,
                merged=True,
            ),
        )

    def launch(self, provider, role, arguments, context, secrets):
        for arg in arguments:
            if arg == "--":
                break
            if arg.split("=", 1)[0] in {"--model", "-m", "--agent", "--attach", "--config"} or (
                arg.startswith("-m") and not arg.startswith("--")
            ):
                raise HarnessSyncError("OpenCode routing flags conflict with the managed profile")
        if arguments and arguments[0] in {"attach", "github", "pr"}:
            raise HarnessSyncError("Remote OpenCode dispatch cannot use a local provider overlay")
        # Inline config pins the model for all subcommands, without inserting TUI flags into them.
        environment = {env_name(key): secrets.get(key) for key in provider.secret_ids()}
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            document(provider, role), ensure_ascii=False
        )
        return LaunchSpec(
            ("--pure", "--model", document(provider, role)["model"]) + arguments,
            environment,
            frozenset(
                {
                    "OPENCODE_CONFIG",
                    "OPENCODE_CONFIG_DIR",
                    "OPENCODE_CONFIG_CONTENT",
                    "OPENCODE_MODELS_PATH",
                }
            ),
        )


def create_adapter():
    return OpenCodeAdapter()
