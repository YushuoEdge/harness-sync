"""OpenClaw 2026.6.11 isolated role state and native environment secret references."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import tempfile
from pathlib import Path

from pydantic import Field

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, get_field
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef, StrictModel, env_name
from harnesses.opencode.jsonc import edit, parse

VERSION = "2026.6.11"
REVISION = "e085fa1"
ROLES = ("simple", "daily", "complex")
APIS = {
    "openai-chat": "openai-completions",
    "openai-responses": "openai-responses",
    "anthropic": "anthropic-messages",
    "google-genai": "google-generative-ai",
}
UNSET = frozenset(
    {
        "OPENCLAW_HOME",
        "OPENCLAW_STATE_DIR",
        "OPENCLAW_CONFIG_PATH",
        "OPENCLAW_PROFILE",
        "OPENCLAW_AGENT_DIR",
        "OPENCLAW_OAUTH_DIR",
        "OPENCLAW_INCLUDE_ROOTS",
        "OPENCLAW_GATEWAY_URL",
        "OPENCLAW_GATEWAY_PORT",
        "OPENCLAW_GATEWAY_TOKEN",
        "OPENCLAW_GATEWAY_PASSWORD",
        "OPENCLAW_CONTAINER",
        "OPENCLAW_TRAJECTORY_DIR",
    }
)


class ProviderOptions(StrictModel):
    # One distinct port per role; no implicit/default port is used by managed gateways.
    gateway_port_base: int | None = Field(default=None, ge=1024, le=65532)


def options(provider):
    override = provider.overrides.get("openclaw")
    return ProviderOptions.model_validate(override.options if override else {})


def selector(provider, role):
    return f"hs-{provider.name}/{provider.model_for(role).upstream_id('openclaw')}"


def command_index(arguments):
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        if arg in {"--version", "-V", "--help", "-h"}:
            return None
        if arg == "--no-color" or arg.startswith("--log-level="):
            index += 1
        elif arg == "--log-level" and index + 1 < len(arguments):
            index += 2
        elif arg.startswith("-"):
            raise HarnessSyncError("OpenClaw expects a native subcommand before its options")
        else:
            return index
    return None


def secret_value(value, secrets=None):
    if isinstance(value, SecretRef):
        if secrets is None:
            return {"source": "env", "provider": "default", "id": env_name(value.secret)}
        value = secrets.get(value.secret)
    if "${" in value:
        raise HarnessSyncError("OpenClaw literal values cannot contain environment substitutions")
    return value


def catalog(provider, secrets=None):
    models = {}
    for model in provider.models:
        model_id = model.upstream_id("openclaw")
        entry = {"id": model_id, "name": model_id}
        for source, target in (
            ("context_window", "contextWindow"),
            ("max_output_tokens", "maxTokens"),
            ("reasoning", "reasoning"),
            ("input", "input"),
        ):
            value = getattr(model, source)
            if value is not None:
                entry[target] = value
        if model_id in models and models[model_id] != entry:
            raise HarnessSyncError("Repeated OpenClaw model IDs have conflicting metadata")
        models[model_id] = entry
    return {
        "baseUrl": provider.endpoint_for("openclaw"),
        "api": APIS[provider.protocol_for("openclaw")],
        "auth": "api-key",
        "apiKey": secret_value(provider.api_key, secrets),
        "headers": {k: secret_value(v, secrets) for k, v in provider.headers.items()},
        "models": list(models.values()),
    }


def aliases(provider):
    result = {}
    for role in ROLES:
        # Native alias is singular. Repeated IDs retain the first role's alias.
        result.setdefault(
            selector(provider, role), {"alias": f"hs-{provider.command_alias}-{role}"}
        )
    return result


def document(provider, role, root):
    doc = {
        "models": {"mode": "merge", "providers": {f"hs-{provider.name}": catalog(provider)}},
        "agents": {
            "defaults": {
                "model": {"primary": selector(provider, role)},
                "models": aliases(provider),
                "workspace": str(root / "workspace"),
            }
        },
    }
    port = options(provider).gateway_port_base
    if port is not None:
        doc["gateway"] = {
            "mode": "local",
            "bind": "loopback",
            "port": port + ROLES.index(role),
            "auth": {
                "mode": "token",
                "token": {
                    "source": "env",
                    "provider": "default",
                    "id": "HARNESS_SYNC_OPENCLAW_GATEWAY_TOKEN",
                },
            },
        }
    return doc


class OpenClawAdapter(Adapter):
    id = "openclaw"
    command = "openclaw"
    protocols = frozenset(APIS)
    provider_options_schema = ProviderOptions

    def detect(self, context):
        env = context.environment
        home = absolute(env.get("OPENCLAW_HOME") or env.get("HOME", str(Path.home())))
        profile = env.get("OPENCLAW_PROFILE", "").strip()
        root = absolute(
            env.get("OPENCLAW_STATE_DIR")
            or home / (".openclaw-" + profile if profile and profile != "default" else ".openclaw")
        )
        explicit = context.settings.config_path or env.get("OPENCLAW_CONFIG_PATH")
        candidates = [root / name for name in ("openclaw.json", "clawdbot.json")]
        if not env.get("OPENCLAW_STATE_DIR") and not profile:
            candidates += [
                home / directory / name
                for directory in (".openclaw", ".clawdbot")
                for name in ("openclaw.json", "clawdbot.json")
            ]
        path = (
            absolute(explicit)
            if explicit
            else next((p for p in candidates if p.exists()), root / "openclaw.json")
        )
        executable = find_executable(self.command, env, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=(path,))
        try:
            with tempfile.TemporaryDirectory(prefix="hs-openclaw-") as directory:
                isolated = {k: v for k, v in env.items() if k not in UNSET}
                isolated.update(
                    OPENCLAW_STATE_DIR=directory, OPENCLAW_CONFIG_PATH=directory + "/openclaw.json"
                )
                version, help_result = (
                    probe(executable, args, isolated)
                    for args in (("--version",), ("agent", "--help"))
                )
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=(path,))
        match = re.search(r"OpenClaw ([\d.]+) \(([a-f0-9]+)\)", version.stdout)
        number = match[1] if match else None
        supported = (
            number == VERSION
            and match[2] == REVISION
            and version.returncode == help_result.returncode == 0
            and "--local" in help_result.stdout
            and "--model" in help_result.stdout
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=(path,),
            capabilities=("env-secret-ref",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "env-secret-ref" not in context.detection.capabilities:
            raise HarnessSyncError("OpenClaw native secret-reference capability was not verified")
        if not isinstance(provider.api_key, SecretRef):
            raise HarnessSyncError("OpenClaw requires an API-key reference")
        if any(m.reasoning_effort is not None for m in provider.models):
            raise HarnessSyncError("OpenClaw reasoning effort requires a model-specific mapping")
        if "${" in provider.endpoint_for(self.id) or any(
            "${" in m.upstream_id(self.id) for m in provider.models
        ):
            raise HarnessSyncError("OpenClaw endpoints and IDs cannot contain substitutions")
        catalog(provider)

    def profiles(self, provider, context):
        result = []
        for role in ROLES:
            root = context.paths.runtime(self.id, provider.command_alias) / role
            doc = document(provider, role, root)
            result.append(
                Artifact(
                    root / "openclaw.json",
                    "profile",
                    f"{self.id}/{provider.name}",
                    lambda _, doc=doc: json.dumps(doc, indent=2).encode(),
                    parse,
                )
            )
        return tuple(result)

    def defaults(self, providers, selected, role, context):
        path = context.detection.default_paths[0]
        current, baseline = context.read(path), context.baseline(path)
        doc, previous = parse(current), parse(baseline) if baseline is not None else None

        def includes(value):
            if isinstance(value, dict):
                return "$include" in value or any(includes(v) for v in value.values())
            return isinstance(value, list) and any(includes(v) for v in value)

        if includes(doc):
            raise HarnessSyncError(
                "OpenClaw include-based defaults require a self-contained config"
            )
        changes = {("agents", "defaults", "model", "primary"): selector(selected, role)}
        for provider in providers:
            fields = [("models", "providers", f"hs-{provider.name}")]
            fields += [("agents", "defaults", "models", key) for key in aliases(provider)]
            for keys in fields:
                if get_field(doc, keys) is not MISSING and (
                    previous is None or get_field(previous, keys) is MISSING
                ):
                    raise ConflictError("OpenClaw managed catalog or alias already exists")
            changes.update(
                {("agents", "defaults", "models", k): v for k, v in aliases(provider).items()}
            )
        for keys in (("models", "providers"), ("agents", "defaults", "models")):
            old = get_field(previous or {}, keys)
            if isinstance(old, dict):
                for key in old:
                    if key.startswith("hs-") and not any(
                        key == f"hs-{p.name}" if keys[0] == "models" else key in aliases(p)
                        for p in providers
                    ):
                        changes[(*keys, key)] = MISSING

        def render(secrets):
            values = dict(changes)
            for provider in providers:
                values[("models", "providers", f"hs-{provider.name}")] = catalog(provider, secrets)
            return edit(current, baseline, values)

        return (Artifact(path, "default", "openclaw/default", render, parse, merged=True),)

    def launch(self, provider, role, arguments, context, secrets):
        root = context.paths.runtime(self.id, provider.command_alias) / role
        for arg in arguments:
            if arg == "--":
                break
            if arg.split("=", 1)[0] in {
                "--profile",
                "--dev",
                "--container",
                "--model",
                "--url",
                "--force",
                "--reset",
                "--port",
                "--config",
                "--thinking",
                "--token",
                "--password",
                "--password-file",
            }:
                raise HarnessSyncError("OpenClaw routing flag conflicts with the managed profile")
        port = options(provider).gateway_port_base
        argv = arguments
        index = command_index(arguments)
        command = arguments[index:] if index is not None else ()
        if command and command[0] in {"gateway", "daemon"}:
            if len(command) > 1 and command[1] in {
                "install",
                "uninstall",
                "start",
                "restart",
                "stop",
            }:
                raise HarnessSyncError("Managed OpenClaw gateways require foreground gateway run")
            if len(command) == 1 or command[1] == "run":
                if port is None:
                    raise HarnessSyncError(
                        "OpenClaw gateway run requires explicit gateway_port_base"
                    )
        if command and command[0] == "agent":
            if "--local" not in command and port is None:
                raise HarnessSyncError("OpenClaw remote agent requires explicit gateway_port_base")
            argv = arguments[:index] + ("agent", "--model", selector(provider, role)) + command[1:]
        if command and command[0] in {"chat", "tui"} and "--local" not in command:
            if port is None:
                raise HarnessSyncError(
                    "OpenClaw gateway client requires explicit gateway_port_base"
                )
        environment = {env_name(k): secrets.get(k) for k in provider.secret_ids()}
        environment.update(
            OPENCLAW_STATE_DIR=str(root), OPENCLAW_CONFIG_PATH=str(root / "openclaw.json")
        )
        if port is not None:
            environment["OPENCLAW_GATEWAY_PORT"] = str(port + ROLES.index(role))
            environment["HARNESS_SYNC_OPENCLAW_GATEWAY_TOKEN"] = hmac.new(
                secrets.get(provider.api_key.secret).encode(),
                f"harness-sync/openclaw/gateway/{provider.name}/{role}".encode(),
                hashlib.sha256,
            ).hexdigest()
        return LaunchSpec(argv, environment, UNSET)


def create_adapter():
    return OpenClawAdapter()
