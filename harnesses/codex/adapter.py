"""Codex CLI profile-v2 adapter."""

from __future__ import annotations

import re
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomlkit

from harness_sync.contracts import (
    Adapter,
    Artifact,
    Detection,
    DetectionContext,
    LaunchSpec,
    RenderContext,
)
from harness_sync.detection import find_executable, probe
from harness_sync.errors import ConflictError, HarnessSyncError, UnsupportedError
from harness_sync.merge import MISSING, get_field, merge_fields
from harness_sync.paths import absolute
from harness_sync.schema import Provider, Role, SecretRef, StrictModel, env_name
from harness_sync.secrets import SecretStore

_VERSION = re.compile(r"(?:codex-cli\s+)?(\d+)\.(\d+)\.(\d+)(?:[-+][^\s]+)?")
_SUPPORTED_VERSIONS = frozenset({(0, 154, 0)})
_PROFILE_HELP_MARKERS = ("--profile <CONFIG_PROFILE_V2>", "<name>.config.toml")
_REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh"})
_UNSET_ENV = frozenset(
    {
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_ORGANIZATION",
        "OPENAI_PROJECT",
        "CODEX_API_KEY",
    }
)


class CodexSettings(StrictModel):
    """Codex has no adapter-specific settings in API v1."""


class CodexProviderOptions(StrictModel):
    """Provider behavior is fully represented by canonical fields."""


class CodexModelOptions(StrictModel):
    """Model behavior is fully represented by canonical fields."""


def _native_locations(context: DetectionContext) -> tuple[Path, Path]:
    if context.settings.config_path:
        config = absolute(context.settings.config_path)
        return config.parent, config
    home_value = context.environment.get("CODEX_HOME")
    if home_value:
        home = absolute(home_value)
    else:
        home = absolute(Path(context.environment.get("HOME", str(Path.home()))) / ".codex")
    return home, home / "config.toml"


def _profile_name(provider: Provider, role: Role) -> str:
    return f"hs-{provider.command_alias}-{role}"


def _provider_name(provider: Provider) -> str:
    return f"hs-{provider.name}"


def _provider_fields(provider: Provider) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "name": f"harness-sync: {provider.name}",
        "base_url": provider.endpoint_for("codex"),
        "wire_api": "responses",
    }
    if isinstance(provider.api_key, SecretRef):
        fields["env_key"] = env_name(provider.api_key.secret)
    static_headers = {
        key: value for key, value in provider.headers.items() if isinstance(value, str)
    }
    secret_headers = {
        key: env_name(value.secret)
        for key, value in provider.headers.items()
        if isinstance(value, SecretRef)
    }
    if static_headers:
        fields["http_headers"] = static_headers
    if secret_headers:
        fields["env_http_headers"] = secret_headers
    return fields


def _profile_document(provider: Provider, role: Role) -> bytes:
    model = provider.model_for(role)
    document = tomlkit.document()
    document.add(tomlkit.comment("Managed by harness-sync. Do not edit this generated profile."))
    document["model"] = model.upstream_id("codex")
    document["model_provider"] = _provider_name(provider)
    if model.reasoning_effort is not None:
        document["model_reasoning_effort"] = model.reasoning_effort
    providers = tomlkit.table()
    providers[_provider_name(provider)] = _provider_fields(provider)
    document["model_providers"] = providers
    return tomlkit.dumps(document).encode()


def _parse_toml(data: bytes | None, description: str) -> dict[str, Any]:
    if data is None:
        return {}
    try:
        parsed = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise HarnessSyncError(f"Invalid Codex {description} TOML") from None
    if not isinstance(parsed, dict):
        raise HarnessSyncError(f"Invalid Codex {description} TOML")
    return parsed


def _verify_profile(data: bytes, provider: Provider, role: Role) -> None:
    parsed = _parse_toml(data, "profile")
    provider_id = _provider_name(provider)
    expected_provider = _provider_fields(provider)
    if (
        parsed.get("model") != provider.model_for(role).upstream_id("codex")
        or parsed.get("model_provider") != provider_id
        or get_field(parsed, ("model_providers", provider_id)) != expected_provider
    ):
        raise HarnessSyncError("Generated Codex profile failed semantic verification")


def _apply_toml_changes(document: Any, changes: Mapping[tuple[str, ...], Any]) -> None:
    for path, desired in changes.items():
        node = document
        for key in path[:-1]:
            if key not in node:
                if desired is MISSING:
                    node = None
                    break
                node[key] = tomlkit.table()
            node = node[key]
        if node is None:
            continue
        if desired is MISSING:
            if path[-1] in node:
                del node[path[-1]]
        else:
            node[path[-1]] = desired


def _render_default(
    current: bytes | None, baseline: bytes | None, changes: Mapping[tuple[str, ...], Any]
) -> bytes:
    current_plain = _parse_toml(current, "default configuration")
    baseline_plain = _parse_toml(baseline, "default baseline") if baseline is not None else None
    # This performs all three-way conflict and scalar-parent checks before the
    # format-preserving document is touched.
    merge_fields(current_plain, baseline_plain, changes)
    try:
        document = tomlkit.parse((current or b"").decode("utf-8"))
        _apply_toml_changes(document, changes)
        rendered = tomlkit.dumps(document).encode()
    except (UnicodeDecodeError, TypeError, ValueError):
        raise HarnessSyncError("Could not preserve the Codex default TOML") from None
    _parse_toml(rendered, "default configuration")
    return rendered


def _has_option(arguments: tuple[str, ...], short: str, long: str) -> bool:
    for argument in arguments:
        if argument == "--":
            return False
        if argument in {short, long} or argument.startswith(long + "="):
            return True
    return False


def _reject_routing_arguments(arguments: tuple[str, ...]) -> None:
    forbidden = {
        "-p",
        "--profile",
        "-c",
        "--config",
        "--oss",
        "--local-provider",
        "--ignore-user-config",
        "--remote",
    }
    for argument in arguments:
        if argument == "--":
            break
        if argument in forbidden or any(
            argument.startswith(name + "=") for name in forbidden if name.startswith("--")
        ):
            raise HarnessSyncError(
                "Native Codex routing flags conflict with the managed provider profile"
            )


class CodexAdapter(Adapter):
    id = "codex"
    command = "codex"
    protocols = frozenset({"openai-responses"})
    settings_schema = CodexSettings
    provider_options_schema = CodexProviderOptions
    model_options_schema = CodexModelOptions

    def detect(self, context: DetectionContext) -> Detection:
        executable = find_executable(self.command, context.environment, context.settings.executable)
        native_home, default_path = _native_locations(context)
        if executable is None:
            return Detection(self.id, "not-found", default_paths=(default_path,))
        try:
            with tempfile.TemporaryDirectory(prefix="harness-sync-codex-probe-") as probe_home:
                environment = dict(context.environment)
                environment["CODEX_HOME"] = probe_home
                version_result = probe(executable, ("--version",), environment)
                help_result = probe(executable, ("--help",), environment)
        except UnsupportedError:
            return Detection(
                self.id, "probe-failed", executable, default_paths=(default_path,)
            )
        version_text = "\n".join((version_result.stdout, version_result.stderr)).strip()
        match = _VERSION.search(version_text)
        version = match.group(0).removeprefix("codex-cli ") if match else None
        version_tuple = tuple(int(value) for value in match.groups()) if match else None
        help_text = "\n".join((help_result.stdout, help_result.stderr))
        supported = (
            version_result.returncode == 0
            and help_result.returncode == 0
            and version_tuple is not None
            and version_tuple in _SUPPORTED_VERSIONS
            and all(marker in help_text for marker in _PROFILE_HELP_MARKERS)
        )
        return Detection(
            self.id,
            "installed" if supported else "unsupported-version",
            executable,
            version,
            default_paths=(default_path,),
            profile_roots=(native_home,),
            capabilities=("profile-v2", "responses") if supported else (),
        )

    def validate(self, provider: Provider, context: RenderContext) -> None:
        super().validate(provider, context)
        if "profile-v2" not in context.detection.capabilities:
            raise HarnessSyncError("Codex profile-v2 capability was not verified")
        for model in provider.models:
            if (
                model.reasoning_effort is not None
                and model.reasoning_effort not in _REASONING_EFFORTS
            ):
                raise HarnessSyncError("Unsupported Codex reasoning effort")
            if not model.upstream_id(self.id).strip():
                raise HarnessSyncError("Codex model ID must not be blank")
    def profiles(self, provider: Provider, context: RenderContext) -> tuple[Artifact, ...]:
        if not context.detection.profile_roots:
            raise HarnessSyncError("Codex native profile root was not detected")
        native_home = context.detection.profile_roots[0]
        artifacts: list[Artifact] = []
        for role in ("simple", "daily", "complex"):
            name = _profile_name(provider, role)
            data = _profile_document(provider, role)

            def render(_: SecretStore, content: bytes = data) -> bytes:
                return content

            def verify(content: bytes, selected_role: Role = role) -> None:
                _verify_profile(content, provider, selected_role)

            for path in (
                context.paths.profile(self.id, provider.command_alias) / f"{name}.config.toml",
                native_home / f"{name}.config.toml",
            ):
                artifacts.append(
                    Artifact(path, "profile", f"codex/{provider.name}", render, verify)
                )
        return tuple(artifacts)

    def defaults(
        self,
        providers: tuple[Provider, ...],
        selected: Provider,
        role: Role,
        context: RenderContext,
    ) -> tuple[Artifact, ...]:
        if len(context.detection.default_paths) != 1:
            raise HarnessSyncError("Codex default configuration path was not detected")
        path = context.detection.default_paths[0]
        current = context.read(path)
        baseline = context.baseline(path)
        current_plain = _parse_toml(current, "default configuration")
        baseline_plain = _parse_toml(baseline, "default baseline") if baseline else {}
        provider_id = _provider_name(selected)
        model = selected.model_for(role)
        changes: dict[tuple[str, ...], Any] = {
            ("model",): model.upstream_id(self.id),
            ("model_provider",): provider_id,
            ("model_reasoning_effort",): model.reasoning_effort
            if model.reasoning_effort is not None
            else MISSING,
        }
        desired_provider_ids = set()
        for provider in providers:
            native_id = _provider_name(provider)
            desired_provider_ids.add(native_id)
            desired = _provider_fields(provider)
            existing = get_field(current_plain, ("model_providers", native_id))
            previous = get_field(baseline_plain, ("model_providers", native_id))
            if baseline is None and existing is not MISSING and existing != desired:
                raise ConflictError("Codex managed provider name already exists")
            if baseline is not None and previous is MISSING and existing is not MISSING:
                raise ConflictError("Codex managed provider name is not owned by harness-sync")
            changes[("model_providers", native_id)] = desired
        previous_providers = baseline_plain.get("model_providers", {})
        if isinstance(previous_providers, dict):
            for native_id in previous_providers:
                if native_id.startswith("hs-") and native_id not in desired_provider_ids:
                    changes[("model_providers", native_id)] = MISSING

        def render(_: SecretStore) -> bytes:
            return _render_default(current, baseline, changes)

        return (
            Artifact(
                path,
                "default",
                "codex/default",
                render,
                lambda data: _parse_toml(data, "default configuration"),
                merged=True,
            ),
        )

    def launch(
        self,
        provider: Provider,
        role: Role,
        arguments: tuple[str, ...],
        context: RenderContext,
        secrets: SecretStore,
    ) -> LaunchSpec:
        _reject_routing_arguments(arguments)
        selected_model = provider.model_for(role).upstream_id(self.id)
        prefix = ["--profile", _profile_name(provider, role)]
        if not _has_option(arguments, "-m", "--model"):
            prefix.extend(("--model", selected_model))
        environment = {
            env_name(identifier): secrets.get(identifier) for identifier in provider.secret_ids()
        }
        return LaunchSpec(tuple(prefix) + arguments, environment, _UNSET_ENV)


def create_adapter() -> Adapter:
    return CodexAdapter()
