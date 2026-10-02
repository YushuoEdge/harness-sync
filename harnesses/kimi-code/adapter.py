"""Kimi Code 2.1.1 TOML/home mapping; no legacy data migration."""

from __future__ import annotations

import re
import tempfile
import tomllib
from pathlib import Path

import tomlkit
from pydantic import Field

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, get_field, merge_fields
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef, StrictModel

VERSION = "2.1.1"
APIS = {
    "anthropic": "anthropic",
    "openai-chat": "openai",
    "openai-responses": "openai_responses",
    "google-genai": "google-genai",
}
UNSET = frozenset(
    {
        "KIMI_CODE_HOME",
        "KIMI_SHARE_DIR",
        "KIMI_BASE_URL",
        "KIMI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "KIMI_MODEL_NAME",
        "KIMI_MODEL_API_KEY",
        "KIMI_MODEL_PROVIDER_TYPE",
        "KIMI_MODEL_BASE_URL",
        "KIMI_MODEL",
        "KIMI_DEFAULT_MODEL",
        "KIMI_MODEL_MAX_CONTEXT_SIZE",
        "KIMI_MODEL_CAPABILITIES",
        "KIMI_MODEL_TEMPERATURE",
        "KIMI_MODEL_TOP_P",
        "KIMI_MODEL_MAX_TOKENS",
        "KIMI_MODEL_MAX_COMPLETION_TOKENS",
        "KIMI_MODEL_THINKING_KEEP",
    }
)


class Settings(StrictModel):
    reserved_context_size: int | None = Field(default=None, ge=1000)


def parse(data):
    try:
        return tomllib.loads((data or b"").decode())
    except (ValueError, UnicodeError):
        raise HarnessSyncError("Invalid Kimi TOML configuration") from None


def provider_fields(provider, secrets):
    return {
        "type": APIS[provider.protocol_for("kimi-code")],
        "base_url": provider.endpoint_for("kimi-code"),
        "api_key": secrets.get(provider.api_key.secret),
        "model_source": "static",
        "custom_headers": {
            key: secrets.get(value.secret) if isinstance(value, SecretRef) else value
            for key, value in provider.headers.items()
        },
    }


def model_fields(provider):
    result = {}
    for model in provider.models:
        caps = []
        if model.reasoning:
            caps.append("thinking")
        if model.input and "image" in model.input:
            caps.append("image_in")
        result[f"hs-{provider.command_alias}-{model.role}"] = {
            "provider": f"hs-{provider.name}",
            "model": model.upstream_id("kimi-code"),
            "max_context_size": model.context_window,
            "capabilities": caps,
        }
    return result


def merge_toml(current, baseline, changes):
    merge_fields(parse(current), parse(baseline) if baseline is not None else None, changes)
    try:
        doc = tomlkit.parse((current or b"").decode())
        for keys, value in changes.items():
            node = doc
            for key in keys[:-1]:
                if key not in node:
                    if value is MISSING:
                        node = None
                        break
                    node[key] = tomlkit.table()
                node = node[key]
            if node is not None:
                if value is MISSING:
                    node.pop(keys[-1], None)
                else:
                    node[keys[-1]] = value
        return tomlkit.dumps(doc).encode()
    except (ValueError, TypeError):
        raise HarnessSyncError("Could not preserve Kimi default TOML") from None


class KimiAdapter(Adapter):
    id = "kimi-code"
    command = "kimi"
    protocols = frozenset(APIS)
    settings_schema = Settings

    def detect(self, context):
        home = absolute(
            context.environment.get("KIMI_CODE_HOME")
            or Path(context.environment.get("HOME", str(Path.home()))) / ".kimi-code"
        )
        path = (
            absolute(context.settings.config_path)
            if context.settings.config_path
            else (home / "config.toml")
        )
        executable = find_executable(self.command, context.environment, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=(path,))
        try:
            with tempfile.TemporaryDirectory(prefix="hs-kimi-") as directory:
                env = dict(
                    context.environment,
                    KIMI_SHARE_DIR=directory,
                    KIMI_CODE_HOME=directory,
                    COLUMNS="180",
                )
                version, help_result = (
                    probe(executable, (flag,), env) for flag in ("--version", "--help")
                )
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=(path,))
        match = re.fullmatch(r"([\d.]+)", version.stdout.strip())
        number = match[1] if match else None
        supported = (
            number == VERSION
            and version.returncode == help_result.returncode == 0
            and "provider" in help_result.stdout
            and "--model" in help_result.stdout
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=(path,),
            capabilities=("code-home",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "code-home" not in context.detection.capabilities:
            raise HarnessSyncError("Kimi Code home/config capability was not verified")
        if not isinstance(provider.api_key, SecretRef):
            raise HarnessSyncError("Kimi requires an API-key reference")
        budget = Settings.model_validate(context.settings.options).reserved_context_size or 50000
        for model in provider.models:
            if model.context_window is None:
                raise HarnessSyncError("Kimi requires context_window for every model")
            if model.context_window <= budget:
                raise HarnessSyncError(
                    "Kimi context_window must exceed reserved_context_size (native default: 50000)"
                )
            if model.max_output_tokens is not None or model.reasoning_effort is not None:
                raise HarnessSyncError(
                    "Kimi Code 2.1.1 cannot map output limits or reasoning effort"
                )

    def profiles(self, provider, context):
        path = context.paths.runtime(self.id, provider.command_alias) / "config.toml"

        def render(secrets):
            budget = Settings.model_validate(context.settings.options).reserved_context_size
            extra = {"loop_control": {"reserved_context_size": budget}} if budget else {}
            return tomlkit.dumps(
                {
                    "default_model": f"hs-{provider.command_alias}-daily",
                    **extra,
                    "providers": {f"hs-{provider.name}": provider_fields(provider, secrets)},
                    "models": model_fields(provider),
                }
            ).encode()

        return (Artifact(path, "profile", f"{self.id}/{provider.name}", render, parse),)

    def defaults(self, providers, selected, role, context):
        path = context.detection.default_paths[0]
        current, baseline = context.read(path), context.baseline(path)
        doc, previous = parse(current), parse(baseline) if baseline is not None else None
        for provider in providers:
            for section, names in (
                ("providers", [f"hs-{provider.name}"]),
                ("models", model_fields(provider)),
            ):
                for name in names:
                    if get_field(doc, (section, name)) is not MISSING and (
                        previous is None or get_field(previous, (section, name)) is MISSING
                    ):
                        raise ConflictError("Kimi managed catalog name already exists")

        def render(secrets):
            changes = {("default_model",): f"hs-{selected.command_alias}-{role}"}
            budget = Settings.model_validate(context.settings.options).reserved_context_size
            if budget is not None:
                changes[("loop_control", "reserved_context_size")] = budget
            for provider in providers:
                changes[("providers", f"hs-{provider.name}")] = provider_fields(provider, secrets)
                changes.update(
                    {("models", name): value for name, value in model_fields(provider).items()}
                )
            for section in ("providers", "models"):
                for name in (previous or {}).get(section, {}):
                    if name.startswith("hs-") and (section, name) not in changes:
                        changes[(section, name)] = MISSING
            return merge_toml(current, baseline, changes)

        return (Artifact(path, "default", "kimi-code/default", render, parse, merged=True),)

    def launch(self, provider, role, arguments, context, secrets):
        for arg in arguments:
            if arg == "--":
                break
            if arg.split("=", 1)[0] in {
                "--config",
                "--config-file",
                "--model",
                "-m",
                "--agent",
                "--agent-file",
                "--session",
                "-S",
                "--continue",
                "-c",
            } or (arg.startswith("-m") and not arg.startswith("--")):
                raise HarnessSyncError("Kimi routing flags conflict with the managed profile")
        root = context.paths.runtime(self.id, provider.command_alias)
        prefix = (
            "--model",
            f"hs-{provider.command_alias}-{role}",
        )
        return LaunchSpec(prefix + arguments, {"KIMI_CODE_HOME": str(root)}, UNSET)


def create_adapter():
    return KimiAdapter()
