"""Canonical, strict schema. Native options are validated by adapter-owned schemas."""

from __future__ import annotations

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["simple", "daily", "complex"]
Protocol = Literal["anthropic", "openai-chat", "openai-responses", "google-genai"]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]*$")]
SecretID = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]*$")]
NonEmpty = Annotated[str, Field(min_length=1)]
Positive = Annotated[int, Field(gt=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


def check_text(value: str) -> str:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("control characters are not allowed")
    return value


def check_url(value: str) -> str:
    check_text(value)
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise ValueError("endpoint must be HTTP(S), without userinfo, query or fragment")
    return value


def env_name(secret_id: str) -> str:
    return "HS_" + secret_id.upper().replace("-", "_")


class SecretRef(StrictModel):
    secret: SecretID


class NoAuth(StrictModel):
    none: Literal[True]


class ModelOverride(StrictModel):
    id: NonEmpty | None = None
    options: dict[str, object] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str | None) -> str | None:
        return check_text(value) if value is not None else None


class ProviderOverride(StrictModel):
    base_url: str | None = None
    type: Protocol | None = None
    options: dict[str, object] = Field(default_factory=dict)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        return check_url(value) if value is not None else None


class Model(StrictModel):
    name: NonEmpty
    id: NonEmpty | None = None
    role: Role
    context_window: Positive | None = None
    max_output_tokens: Positive | None = None
    reasoning: bool | None = None
    reasoning_effort: NonEmpty | None = None
    input: list[Literal["text", "image"]] | None = None
    overrides: dict[Identifier, ModelOverride] = Field(default_factory=dict)

    @field_validator("name", "id", "reasoning_effort")
    @classmethod
    def valid_text(cls, value: str | None) -> str | None:
        return check_text(value) if value is not None else None

    @model_validator(mode="after")
    def limits(self) -> Model:
        if (
            self.context_window
            and self.max_output_tokens
            and self.max_output_tokens > self.context_window
        ):
            raise ValueError("output tokens exceed context window")
        return self

    def upstream_id(self, harness: str) -> str:
        override = self.overrides.get(harness)
        return (override.id if override else None) or self.id or self.name


class Provider(StrictModel):
    name: Identifier
    alias: Identifier | None = None
    type: Protocol
    base_url: str
    api_key: SecretRef | NoAuth
    models: list[Model]
    headers: dict[str, str | SecretRef] = Field(default_factory=dict)
    overrides: dict[Identifier, ProviderOverride] = Field(default_factory=dict)

    _valid_url = field_validator("base_url")(check_url)

    @model_validator(mode="after")
    def validate_provider(self) -> Provider:
        if len(self.models) != 3 or {m.role for m in self.models} != {"simple", "daily", "complex"}:
            raise ValueError("exactly one model per role is required")
        for key, value in self.headers.items():
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", key):
                raise ValueError("invalid header name")
            if isinstance(value, str):
                check_text(value)
                if any(part in key.lower() for part in ("auth", "key", "token", "secret")):
                    raise ValueError("authentication headers require a secret reference")
        return self

    @property
    def command_alias(self) -> str:
        return self.alias or self.name

    def model_for(self, role: Role) -> Model:
        return next(m for m in self.models if m.role == role)

    def protocol_for(self, harness: str) -> Protocol:
        override = self.overrides.get(harness)
        return (override.type if override else None) or self.type

    def endpoint_for(self, harness: str) -> str:
        override = self.overrides.get(harness)
        return (override.base_url if override else None) or self.base_url

    def secret_ids(self) -> set[str]:
        values = [self.api_key, *self.headers.values()]
        return {v.secret for v in values if isinstance(v, SecretRef)}


class DefaultSettings(StrictModel):
    write: bool = False
    provider: str | None = None
    role: Role = "daily"

    @model_validator(mode="after")
    def selection(self) -> DefaultSettings:
        if self.write and self.provider is None:
            raise ValueError("default.write requires a provider")
        return self


class HarnessSettings(StrictModel):
    providers: list[str] | None = None
    default: DefaultSettings = Field(default_factory=DefaultSettings)
    executable: str | None = None
    config_path: str | None = None
    options: dict[str, object] = Field(default_factory=dict)


class CommandSettings(StrictModel):
    bin_dir: str = "~/.local/bin"


class Config(StrictModel):
    version: Literal[1]
    secrets_file: str = "secrets.yaml"
    providers: list[Provider]
    harnesses: dict[Identifier, HarnessSettings] = Field(default_factory=dict)
    commands: CommandSettings = Field(default_factory=CommandSettings)

    @model_validator(mode="after")
    def references(self) -> Config:
        names: dict[str, str] = {}
        for provider in self.providers:
            for key in {provider.name, provider.command_alias}:
                if key in names:
                    raise ValueError("provider names and aliases must be unambiguous")
                names[key] = provider.name
        normalized: dict[str, str] = {}
        for provider in self.providers:
            for key in provider.secret_ids():
                env = env_name(key)
                if env in normalized and normalized[env] != key:
                    raise ValueError("secret identifiers collide after environment normalization")
                normalized[env] = key
        for settings in self.harnesses.values():
            refs = (settings.providers or []) + (
                [settings.default.provider] if settings.default.provider else []
            )
            if any(ref not in names for ref in refs):
                raise ValueError("unknown provider reference")
        return self

    def provider(self, key: str) -> Provider:
        for provider in self.providers:
            if key in {provider.name, provider.command_alias}:
                return provider
        from .errors import HarnessSyncError

        raise HarnessSyncError("Unknown provider name or alias")
