"""Claude Code 2.1.278 settings overlays and explicit Anthropic routing."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from harness_sync.contracts import Adapter, Artifact, Detection, LaunchSpec
from harness_sync.detection import find_executable, probe
from harness_sync.errors import HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, merge_fields
from harness_sync.paths import absolute
from harness_sync.schema import SecretRef

VERSION = "2.1.278"
TIERS = {"simple": "HAIKU", "daily": "SONNET", "complex": "OPUS"}
CONFLICTING = frozenset(
    {
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN_FILE",
        "CLAUDE_CODE_API_KEY_HELPER_TTL_MS",
        "ANTHROPIC_CUSTOM_HEADERS",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_USE_FOUNDRY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_SMALL_FAST_MODEL",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        *(f"ANTHROPIC_DEFAULT_{tier}_MODEL" for tier in TIERS.values()),
    }
)


def parse(data):
    try:
        result = json.loads(data or b"{}")
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError):
        raise HarnessSyncError("Invalid Claude settings JSON") from None


def fields(provider, role, secrets):
    env = {name: "" for name in CONFLICTING}
    env.update(
        {
            "ANTHROPIC_BASE_URL": provider.endpoint_for("claude-code"),
            "ANTHROPIC_API_KEY": secrets.get(provider.api_key.secret),
            "ANTHROPIC_MODEL": provider.model_for(role).upstream_id("claude-code"),
            **{
                f"ANTHROPIC_DEFAULT_{tier}_MODEL": provider.model_for(r).upstream_id("claude-code")
                for r, tier in TIERS.items()
            },
        }
    )
    # The session layer overrides project/user env and disables inherited key helpers.
    return {
        "model": provider.model_for(role).upstream_id("claude-code"),
        "apiKeyHelper": "",
        "env": env,
    }


class ClaudeAdapter(Adapter):
    id = "claude-code"
    command = "claude"
    protocols = frozenset({"anthropic"})

    def detect(self, context):
        home = absolute(
            context.environment.get("CLAUDE_CONFIG_DIR")
            or Path(context.environment.get("HOME", str(Path.home()))) / ".claude"
        )
        path = (
            absolute(context.settings.config_path)
            if context.settings.config_path
            else (home / "settings.json")
        )
        executable = find_executable(self.command, context.environment, context.settings.executable)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=(path,))
        try:
            with tempfile.TemporaryDirectory(prefix="hs-claude-") as directory:
                env = dict(
                    context.environment, CLAUDE_CONFIG_DIR=directory, DISABLE_AUTOUPDATER="1"
                )
                version = probe(executable, ("--version",), env)
                help_result = probe(executable, ("--help",), env)
        except UnsupportedError:
            return Detection(self.id, "probe-failed", executable, default_paths=(path,))
        match = re.fullmatch(r"([\d.]+) \(Claude Code\)", version.stdout.strip())
        number = match[1] if match else None
        supported = (
            number == VERSION
            and version.returncode == help_result.returncode == 0
            and all(flag in help_result.stdout for flag in ("--settings", "--model"))
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            number,
            default_paths=(path,),
            capabilities=("settings-overlay",) if supported else (),
        )

    def validate(self, provider, context):
        super().validate(provider, context)
        if "settings-overlay" not in context.detection.capabilities:
            raise HarnessSyncError("Claude settings overlay capability was not verified")
        if not isinstance(provider.api_key, SecretRef) or provider.headers:
            raise HarnessSyncError("Claude requires an API key and does not support custom headers")
        if any(m.reasoning_effort is not None for m in provider.models):
            raise HarnessSyncError("Claude per-model reasoning effort is not supported")

    def profiles(self, provider, context):
        artifacts = []
        for role in TIERS:
            path = context.paths.profile(self.id, provider.command_alias) / f"{role}.json"

            def render(secrets, role=role):
                return (json.dumps(fields(provider, role, secrets), indent=2) + "\n").encode()

            artifacts.append(Artifact(path, "profile", f"{self.id}/{provider.name}", render, parse))
        return tuple(artifacts)

    def defaults(self, providers, selected, role, context):
        path = context.detection.default_paths[0]
        current, baseline = parse(context.read(path)), context.baseline(path)
        previous = parse(baseline) if baseline is not None else None

        def render(secrets):
            desired = fields(selected, role, secrets)
            changes = {("model",): desired["model"], ("apiKeyHelper",): MISSING}
            changes.update({("env", key): value for key, value in desired["env"].items()})
            return (json.dumps(merge_fields(current, previous, changes), indent=2) + "\n").encode()

        return (Artifact(path, "default", f"{self.id}/default", render, parse, merged=True),)

    def launch(self, provider, role, arguments, context, secrets):
        for arg in arguments:
            if arg == "--":
                break
            if arg.split("=", 1)[0] in {
                "--settings",
                "--setting-sources",
                "--cloud",
                "--teleport",
                "--environment",
                "--agent",
                "--agents",
                "--fallback-model",
                "--bare",
            }:
                raise HarnessSyncError("Claude routing flag conflicts with the managed profile")
        path = context.paths.profile(self.id, provider.command_alias) / f"{role}.json"
        has_model = any(
            a == "--model" or a.startswith("--model=")
            for a in arguments[: arguments.index("--") if "--" in arguments else len(arguments)]
        )
        prefix = ("--settings", str(path))
        if not has_model:
            prefix += ("--model", provider.model_for(role).upstream_id(self.id))
        return LaunchSpec(prefix + arguments, fields(provider, role, secrets)["env"], CONFLICTING)


def create_adapter():
    return ClaudeAdapter()
