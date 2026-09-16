# Implementing a harness adapter

The shared framework and Codex adapter are implemented. The other seven approved v1 native adapters are deliberately absent, so they can be implemented without duplicating the core. GitHub Copilot CLI is a documentation-only candidate awaiting separate implementation approval; Cursor Agent CLI is a documentation-only blocked design. Start with the target directory's `SPEC.md`; it describes native behavior, scope and version-verification gates.

## Ownership and work boundary

Each adapter author owns only:

```text
harnesses/<harness-id>/
  adapter.json       # Existing identity and API version; do not rename these
  adapter.py         # Add create_adapter() -> Adapter
  __init__.py        # Optional; useful for sibling helper imports
  helpers.py        # Optional native parsing/formatting helpers
  fixtures/         # Sanitized versioned native files, never real credentials
  tests/            # Native rendering, precedence and smoke tests
  README.md
  SPEC.md
```

Do not add native field names, paths, flags or protocol quirks to the CLI/core. Do not implement locks, backups, wrappers, shell export generation, or secret storage in an adapter. If a shared interface needs changing, propose it explicitly and update its contract tests; avoid silently forking a private framework.

The registry discovers packaged `harnesses/*/adapter.json` manifests and imports an adjacent `adapter.py` only when present. The factory must return a subclass of `harness_sync.contracts.Adapter`. Configuration cannot name modules to import. Codex is the only registered native implementation; manifests without `adapter.py` report `not-implemented`. Documentation-only directories without manifests, currently Copilot and Cursor, are not registry entries. The fake adapter in [tests/conftest.py](../tests/conftest.py) demonstrates the entire contract and is never packaged as a production adapter.

## Core modules

| Module | Responsibility |
| --- | --- |
| `schema.py` | Canonical Pydantic models, roles, provider-local IDs, typed common overrides |
| `config.py` | Safe YAML boundary; reject duplicate keys/tags and sanitize validation failures |
| `paths.py` | Explicit config/state locations; no current-project discovery |
| `secrets.py` | Private secret file, limited provider views, namespaced shell exports |
| `contracts.py` | Adapter, contexts, detection, artifacts and launch specifications |
| `registry.py` | Bundled adapter loading and explicit unimplemented status |
| `detection.py` | Optional executable discovery and bounded native probe helpers |
| `merge.py` | Format-independent three-way conflict checking on owned leaf paths |
| `engine.py` | Selection, validation, deferred rendering, authorization and pre-launch sync |
| `transactions.py` | POSIX lock, keyed ownership fingerprints, protected baselines/journal, recovery |
| `filesystem.py` | Snapshot, symlink checks, private staging and atomic file replacement |
| `cli.py` | Argument parsing and JSON presentation; no native configuration knowledge |

The CLI uses standard-library `argparse`; adding Typer is unnecessary for this framework. Native format libraries belong in project dependencies when the first adapter needs them. Python requirement is 3.11+; the current local test run uses 3.14.

## Adapter API v1

Import from `harness_sync.contracts`. Required class attributes:

- `id`: exact manifest ID, e.g. `pi`.
- `command`: manifest's original executable name.
- `protocols`: a frozen set of canonical protocol names verified for this adapter.
- `settings_schema`, `provider_options_schema`, `model_options_schema`: Pydantic subclasses of `StrictModel`. The defaults accept no options. Native options are under `options`, not arbitrary keys mixed into the canonical schema.

Required methods:

### `detect(DetectionContext) -> Detection`

Context provides `HarnessSettings` and a snapshot of the current environment. Return executable, version, exact native `default_paths`, any native profile files outside managed roots in `profile_paths`, and verified capabilities. `installed` means the adapter recognizes and supports the native capabilities, not simply that a command exists.

Use `find_executable()` to skip tool-owned wrappers; resolve the original executable. Bounded `probe()` returns private stdout/stderr. Parse a version/capability result; never print raw probe output. Probe only documented noninteractive commands. If `--help` or `--version` can initialize native files, isolate the native home in a temporary directory. The generic helper cannot know these native side effects. Never install packages, invoke inference or modify user files during detection.

### `validate(Provider, RenderContext) -> None`

Call `super().validate()` first to check protocol and adapter option schemas. Then check required native metadata, version-specific protocols and field combinations. Unsupported explicit options must fail instead of silently disappearing.

Use `provider.protocol_for(id)`, `provider.endpoint_for(id)`, and `model.upstream_id(id)`. IDs are opaque: preserve slashes, punctuation, case, dates and deployment names. `name` is a label and is only the fallback ID when `id` is absent. Each provider always has exactly one model per role; two roles may reuse an upstream ID.

### `profiles(Provider, RenderContext) -> tuple[Artifact, ...]`

Return artifacts for all roles. Each artifact supplies:

- Absolute normalized `path`, `scope="profile"`, owner such as `pi/<provider-name>`, mode `0o600`.
- `render(scoped_secrets) -> bytes`, a deferred renderer. It gets only the secret references used by this provider.
- `verify(bytes) -> None`, an offline syntax/schema check; raise on invalid output.

The renderer must not read the filesystem, mutate anything or perform network calls. It may serialize native literals with secrets when required. The core calls all renderers and verifiers before changing any output. Artifact content, callbacks and secrets are omitted from representations and public plan JSON.

Paths must be beneath `context.paths.profile(id, alias)` or `context.paths.runtime(id, alias)`, or exactly declared in detection's external `profile_paths`. Native defaults cannot appear as profile artifacts. Managed runtime directories may contain native sessions; return only the files the tool owns, never an entire runtime directory snapshot.

Use `context.read(path)` whenever existing native content is needed. It records the snapshot as a transaction precondition. Do not call `Path.read_text()` yourself during planning, since the core then cannot detect intervening edits.

### `defaults(providers, selected, role, context) -> tuple[Artifact, ...]`

The engine calls this only when the selected harness has default-write permission. Return only paths in `Detection.default_paths`, with `scope="default"`, owner `<id>/default`, and `merged=True`. The core independently enforces this scope.

Read current bytes through `context.read(path)` and previous generated bytes through `context.baseline(path)`. A missing baseline means first adoption under explicit default-write authorization. Parse both with the native format-preserving parser. For every field this adapter manages, use `merge_fields(current, baseline, changes)` or equivalent strict three-way logic; do not replace whole user configs.

`changes` maps tuples of native keys to desired values. `MISSING` means delete a previously owned leaf. The helper preserves unrelated fields, rejects externally changed owned fields, and refuses to overwrite a scalar parent with a table. Preserve comments through the chosen native parser/serializer. Supply all managed fields, including removals of obsolete optional values. Once applied, the core keeps the generated bytes as the protected baseline for the next merge.

All selected providers are supplied for native catalogs, even when a launch selects only one provider. Defaults may select a different provider from the launched profile. Those paths share one validated transaction.

### `launch(provider, role, arguments, context, scoped_secrets) -> LaunchSpec`

Return an argument tuple **excluding the executable**, an environment overlay, and names to remove from the child environment. Use argv arrays only, never shell interpolation. Explicitly reject flags that escape the selected config/provider/home. Pair credentials with the selected endpoint. Preserve native subcommand grammar and respect enforced policy.

The core checks arguments for credential values, validates environment strings, syncs first, then uses `os.execve` on the detected original executable. TTY, working directory, signals and exit status are retained. Do not launch the harness yourself. Return necessary namespaced key values in the environment if your native profile references them; do not depend on a shell having sourced fresh exports. Do not modify OS `HOME`.

Native argument validation happens before synchronization commits. There is no live reload promise: profiles normally take effect on the new launch. A bare original native command remains outside the framework.

## Minimal factory shape

```python
from harness_sync.contracts import Adapter

class NativeAdapter(Adapter):
    # Implement all abstract methods above in this directory.
    ...

def create_adapter() -> Adapter:
    return NativeAdapter()
```

Do not add a placeholder subclass that reports support while raising `NotImplementedError`. Leave `adapter.py` absent until the adapter is functional. `Registry.bundled()` reports such manifests as `not-implemented`.

## Testing and acceptance

Run shared tests as well as your adapter's tests:

```sh
uv run pytest tests harnesses/<harness-id>/tests
uv run ruff check src tests harnesses
```

Use `Engine(Paths(temp_config, temp_state), Registry((your_adapter,)))` to exercise the real synchronization engine with temporary native homes. A config that selects an unregistered harness is invalid. Override executable/config paths in fixtures; never read or modify the developer's real native configuration or credentials.

Required adapter-specific cases:

1. Actual supported version/capability fixtures; unknown versions fail safely.
2. All three roles; same label with different provider IDs; IDs containing slashes; explicit model overrides; repeated IDs.
3. Exact outbound model ID and protocol verified with a local request stub where feasible. Native selectors are not API IDs.
4. Native auth and config precedence: old parent environment, OAuth, project layers, and explicit CLI flags cannot silently change endpoint/key pairing.
5. Profile-only sync leaves default files byte-identical, including missing defaults.
6. Authorized defaults preserve native comments, unrelated providers, permissions, plugins, OAuth and manually changed unowned fields.
7. Native field conflicts, malformed configs, required model metadata and unsupported options.
8. Concurrent providers and stable session paths, key rotation, launch arguments containing spaces/quotes and signal/exit preservation.
9. Secret-free plans/logs/argv and private literal-key files where native behavior requires them.
10. Wheel packaging includes adapter code/resources. Update README with tested versions and remaining limits.

Shared tests cover transaction recovery, collisions, private permissions and wrapper mechanics. Native parser/schema tests are still required; shared tests cannot prove compatibility with a real harness.

## Current framework limitations

- Public plans list targets, scopes and model resolution; native field-level diffs and persisted redacted default-preview files remain pending.
- `prune`, `--best-effort`, and `--adopt-changes` are not implemented. CLI rejects them. No automatic deletion/adoption is performed.
- Rollback supports only the latest committed transaction, refuses external edits, and retains private backups. Backup retention/pruning needs a future explicit policy.
- No hot reload, watcher, shell modification, external plugin loading or universal model equivalence catalog.
- Locks coordinate this tool's processes. Other programs can still edit files; checks catch ordinary drift, but this is not a security boundary against a malicious concurrent local process. Per-file atomic replacement does not give native readers cross-file atomicity.
- A plan materializes no native secret-bearing content. Read-only native previews therefore report intended reconciliation, not exact byte changes; actual native render/verify/conflict checks finish during apply before any write.
