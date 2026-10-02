"""ZCode 3.14.3 distribution (Agent CLI 0.16.9), private provider files."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import HarnessSyncError, UnsupportedError
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef

VERSION = "3.14.3"
AGENT_VERSION = "0.16.9"
APIS = {
    "anthropic": "anthropic-messages",
    "openai-chat": "openai-chat-completions",
    "openai-responses": "openai-responses",
}
UNSET = frozenset(
    {
        "ZCODE_DATA_BASE_DIR",
        "ZCODE_PERSONAL_PROVIDER_CONFIG_FILE",
        "ZCODE_BUILTIN_PROVIDER_CONFIG_FILE",
        "ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ZAI_API_KEY",
        "ZHIPU_API_KEY",
    }
)
BUILTIN = {
    "schemaVersion": 1,
    "revision": 0,
    "config": {
        "providerConfigRules": {"templateRules": [], "providerRules": []},
        "modelConfigRules": {
            "modelRules": [],
            "modelApiRules": [],
            "providerSiteRules": [],
            "templateModelRules": [],
            "builtinProviderModelRules": [],
        },
    },
}


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def parse(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    try:
        value = json.loads(data, object_pairs_hook=unique)
        if not isinstance(value, dict) or value.get("schemaVersion") != 1:
            raise ValueError
        return value
    except (ValueError, UnicodeError, TypeError):
        raise HarnessSyncError("Invalid ZCode provider JSON") from None


def model_rules(provider):
    rules = {}
    api = provider.protocol_for("zcode")
    token_map = {
        "anthropic": "{'max_tokens': maxOutputTokens}",
        "openai-chat": "{'max_completion_tokens': maxOutputTokens}",
        "openai-responses": "{'max_output_tokens': maxOutputTokens}",
    }[api]
    for model in provider.models:
        entry = {
            "providerId": f"hs-{provider.name}",
            "modelId": model.upstream_id("zcode"),
            "config": {
                "enabled": True,
                "properties": {
                    "requiresMfjsToolSchema": False,
                    "contextWindow": model.context_window,
                    "inputFormat": {
                        "supportsText": True,
                        "supportsImage": bool(model.input and "image" in model.input),
                        "supportsVideo": False,
                        "supportsAudio": False,
                        "supportsPdf": False,
                    },
                    "outputFormat": {"supportsText": True},
                    "supportsToolCall": True,
                    "supportsJsonSchemaOutput": False,
                    "supportsNativeWebSearch": False,
                    "supportsMidConversationSystem": False,
                },
                "optionSpecs": {
                    "reasoningLevel": {"values": ["disabled"], "map": "{}"},
                    "maxOutputTokens": {"max": model.max_output_tokens, "map": token_map},
                },
            },
        }
        key = entry["modelId"]
        if key in rules and rules[key] != entry:
            raise HarnessSyncError("Repeated ZCode model IDs have conflicting metadata")
        rules[key] = entry
    return list(rules.values())


def document(provider, role, secrets):
    name = f"hs-{provider.name}"
    return {
        "schemaVersion": 1,
        "config": {
            "providerConfigRules": {
                "providerRules": [
                    {
                        "providerId": name,
                        "providerName": provider.name,
                        "enabled": True,
                        "config": {
                            "group": "standard-personal",
                            "access": {
                                "type": "api-key",
                                "apiKey": secrets.get(provider.api_key.secret),
                            },
                            "api": {
                                "type": APIS[provider.protocol_for("zcode")],
                                "baseUrl": provider.endpoint_for("zcode"),
                                "headers": {
                                    k: secrets.get(v.secret) if isinstance(v, SecretRef) else v
                                    for k, v in provider.headers.items()
                                },
                            },
                            "personalModelIds": [r["modelId"] for r in model_rules(provider)],
                        },
                    }
                ]
            },
            "modelConfigRules": {
                "providerModelRules": model_rules(provider),
                "manualProviderModelRules": [],
            },
            "defaultModelSelection": {
                "providerId": name,
                "modelId": provider.model_for(role).upstream_id("zcode"),
                "options": {"reasoningLevel": "disabled"},
            },
        },
    }


class ZCodeAdapter(Adapter):
    id = "zcode"
    command = "zcode"
    protocols = frozenset(APIS)

    def detect(self, context):
        home = absolute(
            context.environment.get("ZCODE_DATA_BASE_DIR")
            or context.environment.get("HOME", str(Path.home()))
        )
        path = absolute(
            context.settings.config_path
            or context.environment.get("ZCODE_PERSONAL_PROVIDER_CONFIG_FILE")
            or home / ".zcode/v2/provider_config.json"
        )
        executable = find_executable(self.command, context.environment, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=(path,))
        try:
            with tempfile.TemporaryDirectory(prefix="hs-zcode-") as directory:
                env = {k: v for k, v in context.environment.items() if k not in UNSET}
                env["ZCODE_DATA_BASE_DIR"] = directory
                version = probe(executable, ("--version",), env)
                help_result = probe(executable, ("--help",), env)
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=(path,))
        number = version.stdout.strip()
        supported = (
            number == VERSION
            and version.returncode == help_result.returncode == 0
            and all(
                s in help_result.stdout
                for s in ("--prompt", "--resume", "ZCode", f"zcode {AGENT_VERSION}")
            )
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=(path,),
            capabilities=("provider-file-v1",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "provider-file-v1" not in context.detection.capabilities:
            raise HarnessSyncError("ZCode provider file capability was not verified")
        if not isinstance(provider.api_key, SecretRef):
            raise HarnessSyncError("ZCode requires an API-key reference")
        for model in provider.models:
            if model.context_window is None or model.max_output_tokens is None:
                raise HarnessSyncError("ZCode requires context_window and max_output_tokens")
            if model.reasoning is True or model.reasoning_effort is not None:
                raise HarnessSyncError("ZCode reasoning requires a model-specific native map")
        model_rules(provider)

    def profiles(self, provider, context):
        artifacts = []
        for role in ("simple", "daily", "complex"):
            root = context.paths.runtime(self.id, provider.command_alias) / role

            def render(secrets, role=role):
                return encode(document(provider, role, secrets))

            artifacts.extend(
                (
                    Artifact(
                        root / "provider_config.json",
                        "profile",
                        f"zcode/{provider.name}",
                        render,
                        parse,
                    ),
                    Artifact(
                        root / "builtin.json",
                        "profile",
                        f"zcode/{provider.name}",
                        lambda _: encode(BUILTIN),
                        parse,
                    ),
                )
            )
        return tuple(artifacts)

    def defaults(self, providers, selected, role, context):
        raise HarnessSyncError("ZCode native default writes are not supported")

    def launch(self, provider, role, arguments, context, secrets):
        blocked = {
            "--web",
            "--model",
            "--resume",
            "--continue",
            "--target",
            "--target-replace",
            "--enable-workflow",
            "--memory-bench",
            "--surface",
            "--stdio",
            "-c",
        }
        for arg in arguments:
            if arg == "--":
                break
            if (
                (arg.startswith(("-c", "-m")) and not arg.startswith("--"))
                or arg.split("=", 1)[0] in blocked
                or arg
                in {
                    "app-server",
                    "agent-server",
                    "login",
                    "logout",
                    "plugins",
                    "plugin",
                }
            ):
                raise HarnessSyncError(
                    "ZCode routing or administrative mode conflicts with profile"
                )
        root = context.paths.runtime(self.id, provider.command_alias) / role
        return LaunchSpec(
            arguments,
            {
                "ZCODE_DATA_BASE_DIR": str(root),
                "ZCODE_PERSONAL_PROVIDER_CONFIG_FILE": str(root / "provider_config.json"),
                "ZCODE_BUILTIN_PROVIDER_CONFIG_FILE": str(root / "builtin.json"),
            },
            UNSET,
        )


def create_adapter():
    return ZCodeAdapter()
