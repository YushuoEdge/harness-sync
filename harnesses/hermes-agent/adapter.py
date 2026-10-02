"""Hermes v0.21.0 / 245e4800 named providers and isolated role homes."""

from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

from dotenv.parser import parse_stream
from ruamel.yaml import YAML

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, get_field, merge_fields
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef, env_name

VERSION = "0.21.0"
REVISION = "245e4800"
APIS = {
    "openai-chat": "chat_completions",
    "openai-responses": "codex_responses",
    "anthropic": "anthropic_messages",
}
UNSET = frozenset(
    {
        "HERMES_HOME",
        "HERMES_PROFILE",
        "HERMES_INFERENCE_PROVIDER",
        "HERMES_INFERENCE_MODEL",
        "HERMES_INFERENCE_BASE_URL",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENROUTER_BASE_URL",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
    }
)


def parse(data):
    try:
        doc = YAML(typ="safe").load((data or b"{}").decode())
        if not isinstance(doc, dict):
            raise ValueError
        return doc
    except Exception:
        raise HarnessSyncError("Invalid Hermes YAML configuration") from None


def encode(doc):
    stream = io.StringIO()
    YAML(typ="rt").dump(doc, stream)
    return stream.getvalue().encode()


def dotenv(data):
    try:
        bindings = list(parse_stream(io.StringIO((data or b"").decode())))
        doc = {}
        for binding in bindings:
            if binding.error or binding.key in doc:
                raise ValueError
            if binding.key is not None:
                doc[binding.key] = binding.value
        return doc, bindings
    except (ValueError, UnicodeError):
        raise HarnessSyncError("Invalid or duplicate Hermes dotenv entries") from None


def dotenv_line(key, value):
    if "${" in value:
        raise HarnessSyncError("Hermes dotenv cannot preserve credential interpolation syntax")
    quoted = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"{key}='{quoted}'\n"


def key_values(providers, secrets):
    return {env_name(key): secrets.get(key) for p in providers for key in p.secret_ids()}


def provider_fields(provider):
    models = {}
    for model in provider.models:
        entry = {}
        if model.context_window is not None:
            entry["context_length"] = model.context_window
        if model.reasoning is not None:
            entry["reasoning"] = model.reasoning
        if model.input is not None:
            entry["vision"] = "image" in model.input
        model_id = model.upstream_id("hermes-agent")
        if model_id in models and models[model_id] != entry:
            raise HarnessSyncError("Repeated Hermes model IDs have conflicting metadata")
        models[model_id] = entry
    return {
        "base_url": provider.endpoint_for("hermes-agent"),
        "key_env": env_name(provider.api_key.secret),
        "transport": APIS[provider.protocol_for("hermes-agent")],
        "models": models,
        "extra_headers": {
            name: "${" + env_name(value.secret) + "}" if isinstance(value, SecretRef) else value
            for name, value in provider.headers.items()
        },
    }


def model_fields(provider, role):
    result = {
        "provider": f"custom:hs-{provider.name}",
        "default": provider.model_for(role).upstream_id("hermes-agent"),
        "api_mode": APIS[provider.protocol_for("hermes-agent")],
    }
    if provider.model_for(role).max_output_tokens is not None:
        result["max_tokens"] = provider.model_for(role).max_output_tokens
    return result


class HermesAdapter(Adapter):
    id = "hermes-agent"
    command = "hermes"
    protocols = frozenset(APIS)

    def detect(self, context):
        home = absolute(
            context.environment.get("HERMES_HOME")
            or Path(context.environment.get("HOME", str(Path.home()))) / ".hermes"
        )
        config = (
            absolute(context.settings.config_path)
            if context.settings.config_path
            else (home / "config.yaml")
        )
        paths = (config, config.parent / ".env")
        executable = find_executable(self.command, context.environment, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=paths)
        try:
            with tempfile.TemporaryDirectory(prefix="hs-hermes-") as directory:
                env = dict(context.environment, HERMES_HOME=directory)
                env.pop("HERMES_PROFILE", None)
                version, help_result = (
                    probe(executable, (flag,), env) for flag in ("--version", "--help")
                )
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=paths)
        match = re.search(r"Hermes Agent v([\d.]+).*upstream ([a-f0-9]+)", version.stdout)
        number = match[1] if match else None
        supported = (
            number == VERSION
            and match[2] == REVISION
            and version.returncode == help_result.returncode == 0
            and "--provider" in help_result.stdout
            and "--model" in help_result.stdout
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=paths,
            capabilities=("named-providers",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "named-providers" not in context.detection.capabilities:
            raise HarnessSyncError("Hermes named-provider capability was not verified")
        if not isinstance(provider.api_key, SecretRef):
            raise HarnessSyncError("Hermes requires an API-key reference")
        for model in provider.models:
            if model.reasoning_effort not in {
                None,
                "none",
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
                "ultra",
            }:
                raise HarnessSyncError("Unsupported Hermes reasoning effort")
        if any(isinstance(v, str) and "${" in v for v in provider.headers.values()):
            raise HarnessSyncError("Static Hermes headers cannot contain substitutions")
        provider_fields(provider)

    def profiles(self, provider, context):
        result = []
        for role in ("simple", "daily", "complex"):
            root = context.paths.runtime(self.id, provider.command_alias) / role
            doc = {
                "model": model_fields(provider, role),
                "providers": {f"hs-{provider.name}": provider_fields(provider)},
            }
            effort = provider.model_for(role).reasoning_effort
            if effort is not None:
                doc["agent"] = {"reasoning_effort": effort}
            result.append(
                Artifact(
                    root / "config.yaml",
                    "profile",
                    f"{self.id}/{provider.name}",
                    lambda _, doc=doc: encode(doc),
                    parse,
                )
            )

            def render(secrets):
                return "".join(
                    dotenv_line(k, v) for k, v in sorted(key_values((provider,), secrets).items())
                ).encode()

            result.append(
                Artifact(root / ".env", "profile", f"{self.id}/{provider.name}", render, dotenv)
            )
        return tuple(result)

    def defaults(self, providers, selected, role, context):
        config, env_path = context.detection.default_paths
        current, baseline = context.read(config), context.baseline(config)
        doc, previous = parse(current), parse(baseline) if baseline is not None else None
        changes = {("model", k): v for k, v in model_fields(selected, role).items()}
        changes[("model", "max_tokens")] = selected.model_for(role).max_output_tokens or MISSING
        changes[("agent", "reasoning_effort")] = (
            selected.model_for(role).reasoning_effort or MISSING
        )
        for provider in providers:
            name = f"hs-{provider.name}"
            if get_field(doc, ("providers", name)) is not MISSING and (
                previous is None or get_field(previous, ("providers", name)) is MISSING
            ):
                raise ConflictError("Hermes managed provider name already exists")
            changes[("providers", name)] = provider_fields(provider)
        for name in (previous or {}).get("providers", {}):
            if name.startswith("hs-") and ("providers", name) not in changes:
                changes[("providers", name)] = MISSING

        def render_yaml(_):
            expected = merge_fields(doc, previous, changes)
            document = YAML(typ="rt").load((current or b"{}").decode())
            for keys, value in changes.items():
                node = document
                for key in keys[:-1]:
                    if key not in node:
                        if value is MISSING:
                            node = None
                            break
                        node[key] = {}
                    node = node[key]
                if node is not None:
                    if value is MISSING:
                        node.pop(keys[-1], None)
                    else:
                        node[keys[-1]] = value
            rendered = encode(document)
            if parse(rendered) != expected:
                raise HarnessSyncError(
                    "Hermes YAML aliases cannot be merged without unrelated changes"
                )
            return rendered

        env_current, env_baseline = context.read(env_path), context.baseline(env_path)
        env_doc, bindings = dotenv(env_current)
        env_previous = dotenv(env_baseline)[0] if env_baseline is not None else None

        def render_env(secrets):
            values = key_values(providers, secrets)
            env_changes = {(k,): v for k, v in values.items()}
            for key in env_previous or {}:
                if key.startswith("HS_") and key not in values:
                    env_changes[(key,)] = MISSING
            merge_fields(env_doc, env_previous, env_changes)
            output = ""
            for binding in bindings:
                if (binding.key,) in env_changes:
                    if binding.key in values:
                        output += dotenv_line(binding.key, values.pop(binding.key))
                else:
                    output += binding.original.string
            if output and not output.endswith("\n"):
                output += "\n"
            output += "".join(dotenv_line(k, v) for k, v in sorted(values.items()))
            return output.encode()

        return (
            Artifact(config, "default", "hermes-agent/default", render_yaml, parse, merged=True),
            Artifact(env_path, "default", "hermes-agent/default", render_env, dotenv, merged=True),
        )

    def launch(self, provider, role, arguments, context, secrets):
        for arg in arguments:
            if arg == "--":
                break
            if arg.split("=", 1)[0] in {
                "--model",
                "-m",
                "--provider",
                "--profile",
                "-P",
                "--ignore-user-config",
                "--safe-mode",
            } or (arg.startswith("-m") and not arg.startswith("--")):
                raise HarnessSyncError("Hermes routing flag conflicts with the managed profile")
        environment = key_values((provider,), secrets)
        environment["HERMES_HOME"] = str(
            context.paths.runtime(self.id, provider.command_alias) / role
        )
        selection = (
            "--provider",
            f"custom:hs-{provider.name}",
            "--model",
            provider.model_for(role).upstream_id(self.id),
        )
        if arguments and arguments[0] == "chat":
            argv = ("chat",) + selection + arguments[1:]
        elif not arguments or arguments[0].startswith("-"):
            argv = selection + arguments
        else:
            argv = arguments
        return LaunchSpec(argv, environment, UNSET)


def create_adapter():
    return HermesAdapter()
