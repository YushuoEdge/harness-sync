"""DeepSeek Harness 0.1.2-rc.1 native settings and bundled profiles."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import Literal

from ruamel.yaml import YAML

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, get_field, merge_fields
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef, StrictModel, env_name

VERSION = "0.1.2-rc.1"
APIS = {
    "anthropic": "anthropic-messages",
    "openai-chat": "openai-completions",
    "openai-responses": "openai-responses",
}
BUNDLES = {
    "web": "@deepseek-ai/dsh-web-app",
    "headless": "@deepseek-ai/dsh-headless",
    "sdk": "@deepseek-ai/dsh-sdk-app",
    "acp": "@deepseek-ai/dsh-acp-app",
}


class Settings(StrictModel):
    base_profile: Literal["web", "headless", "sdk", "acp"] = "web"


def parse(data):
    try:
        value = YAML(typ="rt").load((data or b"{}").decode())
        if not isinstance(value, dict):
            raise ValueError

        # Settings documents are data. Never accept executable/custom YAML tags.
        def check(node):
            if getattr(node, "tag", None) and str(node.tag) not in {
                "None",
                "tag:yaml.org,2002:map",
                "tag:yaml.org,2002:seq",
            }:
                raise ValueError
            if isinstance(node, dict):
                for child in node.values():
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)

        check(value)
        return value
    except Exception:
        raise HarnessSyncError("Invalid or tagged DeepSeek settings YAML") from None


def encode(value):
    stream = io.StringIO()
    YAML(typ="rt").dump(value, stream)
    return stream.getvalue().encode()


def catalog(provider, secrets=None):
    models = {}
    for model in provider.models:
        entry = {"id": model.upstream_id("deepseek-harness")}
        for source, target in (
            ("context_window", "contextWindow"),
            ("max_output_tokens", "maxTokens"),
            ("input", "input"),
        ):
            if (value := getattr(model, source)) is not None:
                entry[target] = value
        if model.reasoning is False:
            entry["reasoningEfforts"] = False
        if entry["id"] in models and models[entry["id"]] != entry:
            raise HarnessSyncError("Repeated DeepSeek IDs have conflicting metadata")
        models[entry["id"]] = entry
    headers = {
        key: (
            secrets.get(value.secret)
            if isinstance(value, SecretRef) and secrets
            else value
            if isinstance(value, str)
            else "<deferred>"
        )
        for key, value in provider.headers.items()
    }
    return {
        "api": APIS[provider.protocol_for("deepseek-harness")],
        "baseURL": provider.endpoint_for("deepseek-harness"),
        "apiKeyEnv": env_name(provider.api_key.secret),
        "models": list(models.values()),
        "headers": headers,
    }


def selection(provider, role):
    return {
        "provider": f"hs-{provider.name}",
        "model": provider.model_for(role).upstream_id("deepseek-harness"),
    }


class DeepSeekAdapter(Adapter):
    id = "deepseek-harness"
    command = "dsh"
    protocols = frozenset(APIS)
    settings_schema = Settings

    def detect(self, context):
        home = absolute(
            context.environment.get("DSH_HOME")
            or Path(context.environment.get("HOME", str(Path.home()))) / ".dsh"
        )
        path = (
            absolute(context.settings.config_path)
            if context.settings.config_path
            else (home / "settings.yaml")
        )
        executable = find_executable(self.command, context.environment, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=(path,))
        try:
            with tempfile.TemporaryDirectory(prefix="hs-dsh-") as directory:
                env = dict(context.environment, DSH_HOME=directory)
                version = probe(executable, ("--version",), env)
                help_result = probe(executable, ("--help",), env)
                dump = probe(executable, ("--profile", "headless", "--dump-default-config"), env)
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=(path,))
        number = version.stdout.strip()
        supported = (
            number == VERSION
            and version.returncode == help_result.returncode == dump.returncode == 0
            and "DeepSeek Harness" in help_result.stdout
            and all(
                f"id: {row}" in dump.stdout
                for row in ("llm-pi-ai", "agent-default-model", "settings")
            )
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=(path,),
            capabilities=("bundled-profiles",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "bundled-profiles" not in context.detection.capabilities:
            raise HarnessSyncError("DeepSeek bundled-profile capability was not verified")
        if not isinstance(provider.api_key, SecretRef):
            raise HarnessSyncError("DeepSeek requires an API-key reference")
        if any(m.reasoning is True or m.reasoning_effort is not None for m in provider.models):
            raise HarnessSyncError("DeepSeek reasoning metadata requires a native effort map")
        catalog(provider)

    def profiles(self, provider, context):
        template = Settings.model_validate(context.settings.options).base_profile
        result = []
        for role in ("simple", "daily", "complex"):
            root = context.paths.runtime(self.id, provider.command_alias) / role
            profile = root / "profiles" / template
            manifest = {
                "name": f"hs-{provider.command_alias}-{role}",
                "private": True,
                "dependencies": {},
                "dsh": {
                    "profile": {
                        "bundles": ["@deepseek-ai/dsh-base", BUNDLES[template]],
                        "patchReload": "startup",
                    }
                },
            }

            def render(secrets, role=role):
                return encode(
                    {
                        "llm-pi-ai": {
                            "providers": {f"hs-{provider.name}": catalog(provider, secrets)}
                        },
                        "agent-default-model": selection(provider, role),
                    }
                )

            owner = f"{self.id}/{provider.name}"
            result.append(Artifact(root / "settings.yaml", "profile", owner, render, parse))
            result.append(
                Artifact(
                    profile / "package.json",
                    "profile",
                    owner,
                    lambda _, value=manifest: json.dumps(value, indent=2).encode(),
                    json.loads,
                )
            )
            result.append(
                Artifact(
                    profile / "cordis.patch.yml",
                    "profile",
                    owner,
                    lambda _: b"[]\n",
                    lambda data: YAML(typ="safe").load(data),
                )
            )
        return tuple(result)

    def defaults(self, providers, selected, role, context):
        path = context.detection.default_paths[0]
        current, baseline = parse(context.read(path)), context.baseline(path)
        previous = parse(baseline) if baseline is not None else None
        for provider in providers:
            name = f"hs-{provider.name}"
            owned_path = ("llm-pi-ai", "providers", name)
            if get_field(current, owned_path) is not MISSING and (
                previous is None or get_field(previous, owned_path) is MISSING
            ):
                raise ConflictError("DeepSeek managed provider name already exists")

        def render(secrets):
            changes = {
                ("llm-pi-ai", "providers", f"hs-{p.name}"): catalog(p, secrets) for p in providers
            }
            previous_providers = (previous or {}).get("llm-pi-ai", {}).get("providers", {})
            desired_names = {f"hs-{p.name}" for p in providers}
            for name in previous_providers:
                if name.startswith("hs-") and name not in desired_names:
                    changes[("llm-pi-ai", "providers", name)] = MISSING
            changes.update(
                {("agent-default-model", k): v for k, v in selection(selected, role).items()}
            )
            changes[("agent-default-model", "reasoningEffort")] = MISSING
            merge_fields(current, previous, changes)
            document = parse(encode(current))
            for keys, value in changes.items():
                node = document
                for key in keys[:-1]:
                    if key not in node:
                        node[key] = {}
                    node = node[key]
                if value is MISSING:
                    node.pop(keys[-1], None)
                else:
                    node[keys[-1]] = value
            return encode(document)

        return (Artifact(path, "default", f"{self.id}/default", render, parse, merged=True),)

    def launch(self, provider, role, arguments, context, secrets):
        template = Settings.model_validate(context.settings.options).base_profile
        if arguments and arguments[0] == "web":
            if template != "web":
                raise HarnessSyncError(
                    "DeepSeek web dispatch conflicts with the configured template"
                )
            arguments = arguments[1:]
        for arg in arguments:
            if arg.split("=", 1)[0] in {"--profile", "--patch", "--from-default-profile"}:
                raise HarnessSyncError("DeepSeek routing flags conflict with the managed profile")
        if arguments and arguments[0] == "plugin":
            raise HarnessSyncError("Use the original dsh command for plugin administration")
        if template == "web" and not any(
            a == "--port" or a.startswith("--port=") for a in arguments
        ):
            raise HarnessSyncError("Managed DeepSeek web launches require an explicit --port")
        environment = {env_name(key): secrets.get(key) for key in provider.secret_ids()}
        environment["DSH_HOME"] = str(context.paths.runtime(self.id, provider.command_alias) / role)
        return LaunchSpec(
            ("--profile", template) + arguments,
            environment,
            frozenset({"DSH_HOME", "DSH_SNAPSHOT"}),
        )


def create_adapter():
    return DeepSeekAdapter()
