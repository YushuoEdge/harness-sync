"""Version 1 adapter API: pure rendering plans, centralized I/O and launch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .errors import HarnessSyncError
from .paths import Paths
from .schema import HarnessSettings, Protocol, Provider, Role, StrictModel
from .secrets import SecretStore

DetectionStatus = Literal[
    "installed", "not-found", "unsupported-version", "probe-failed", "not-implemented"
]
Scope = Literal["profile", "default", "wrapper", "environment"]


@dataclass(frozen=True)
class Detection:
    harness: str
    status: DetectionStatus
    executable: Path | None = None
    version: str | None = None
    # Exact native destinations; the core enforces these against default/profile plans.
    default_paths: tuple[Path, ...] = ()
    profile_paths: tuple[Path, ...] = ()
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class DetectionContext:
    settings: HarnessSettings
    environment: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class RenderContext:
    paths: Paths
    detection: Detection
    settings: HarnessSettings
    # Snapshot reads are tracked as transaction preconditions. Baselines are private
    # previous generated versions, never part of plan JSON.
    read: Callable[[Path], bytes | None] = field(repr=False)
    baseline: Callable[[Path], bytes | None] = field(repr=False)


@dataclass(frozen=True)
class Artifact:
    path: Path
    scope: Scope
    owner: str
    render: Callable[[SecretStore], bytes] = field(repr=False)
    verify: Callable[[bytes], None] = field(repr=False)
    mode: int = 0o600
    # True for native default files merged structurally from current snapshots.
    # Only allowed for default scope; adapter must use three-way field conflict checks.
    merged: bool = False


@dataclass(frozen=True)
class LaunchSpec:
    argv: tuple[str, ...]
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    unset: frozenset[str] = frozenset()


class EmptyOptions(StrictModel):
    """Default adapter options schema: accepts no extra fields."""


class Adapter(ABC):
    """Implementations must not mutate files, install packages or call inference APIs.

    Instances are registered only from bundled, trusted modules. Rendering is deferred
    until apply, where only the appropriate provider secrets are supplied. Native
    syntax parsers/format-preserving default edits belong to the adapter.
    """

    id: str
    command: str
    protocols: frozenset[Protocol] = frozenset()
    settings_schema: type[StrictModel] = EmptyOptions
    provider_options_schema: type[StrictModel] = EmptyOptions
    model_options_schema: type[StrictModel] = EmptyOptions

    @abstractmethod
    def detect(self, context: DetectionContext) -> Detection:
        """Read-only bounded probes; report installed only for tested capabilities."""

    def validate(self, provider: Provider, context: RenderContext) -> None:
        if provider.protocol_for(self.id) not in self.protocols:
            raise HarnessSyncError("Provider protocol is incompatible with selected adapter")
        self.settings_schema.model_validate(context.settings.options)
        override = provider.overrides.get(self.id)
        self.provider_options_schema.model_validate(override.options if override else {})
        for model in provider.models:
            model_override = model.overrides.get(self.id)
            self.model_options_schema.model_validate(
                model_override.options if model_override else {}
            )

    @abstractmethod
    def profiles(self, provider: Provider, context: RenderContext) -> tuple[Artifact, ...]:
        """Describe files for all three roles; no secret values available here."""

    @abstractmethod
    def defaults(
        self,
        providers: tuple[Provider, ...],
        selected: Provider,
        role: Role,
        context: RenderContext,
    ) -> tuple[Artifact, ...]:
        """Describe structural native default edits. Called only with authorization."""

    @abstractmethod
    def launch(
        self,
        provider: Provider,
        role: Role,
        arguments: tuple[str, ...],
        context: RenderContext,
        secrets: SecretStore,
    ) -> LaunchSpec:
        """Pin routing; reject conflicting flags; return argv (excluding executable)."""
