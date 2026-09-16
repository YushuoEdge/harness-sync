# Harness Sync Config — specification

Status: **Shared framework implementation authorized and delivered; native adapters pending.**

This document describes the full target design. The current framework subset and deliberate API refinements are documented in [adapter development](docs/adapter-development.md). In particular: native options are under typed `options` objects; plans currently show metadata rather than native content diffs; prune/best-effort/adopt-changes are pending. No real native support is claimed yet.

## 1. Purpose and scope

One human-edited YAML configuration defines providers and three task roles per provider. One separate secrets file holds API keys. The tool translates these inputs into harness-specific profiles, provider-suffixed launch commands, and explicitly enabled default configuration updates.

The proposed executable is `harness-sync` (no short alias installed automatically). Initial platform scope: macOS and Linux, with Bash and Zsh integration. Implementation proposal: Python 3.11+, packaged for `uv tool install` / `pipx`; standard-library argparse, Pydantic and ruamel.yaml in the core; tomlkit and format-preserving JSON/JSONC/JSON5 editing as native adapters require. Dependency versions and JSON editing library will be selected and pinned during implementation. Native Windows, a GUI, protocol proxying, OAuth migration, and automatic task-complexity classification are outside v1.

All eight adapters are required for v1: Claude Code, Codex, Pi, DeepSeek Harness, Kimi Code, OpenCode, Hermes Agent, and OpenClaw. A draft adapter is not implemented support. Each adapter must pass its release gates before v1 can claim support; incompatible provider/harness pairs receive explicit diagnostics.

## 2. Requirements and decisions

| Requirement | Proposed behavior |
| --- | --- |
| Providers and models | Ordered provider list; exactly one entry for each role: simple, daily, complex |
| Automatic synchronization | Sync on explicit sync commands and immediately before managed harness launches; no background process |
| Ordinary and suffixed commands | Existing command stays intact; generate `<command>-<provider-alias>` wrappers |
| Two output groups | Always generate managed profiles and default-change previews; apply native default files only when enabled |
| Harness selection | Repeatable `--harness`, supporting comma-separated IDs and `all` |
| Unified credentials | Private `secrets.yaml`; generated shell exports and native secret fields where needed |
| Detection | Probe installed executables and paths; record results and sync ownership in a private state file |
| Concurrent use | No temporary swapping of global configs; child-scoped credentials and provider selection |

## 3. Canonical configuration

Location: `${XDG_CONFIG_HOME:-~/.config}/harness-sync/config.yaml`. `--config PATH` overrides it. Secrets paths resolve relative to this file; no automatic search in the current project. Unknown keys, YAML duplicate keys, arbitrary YAML tags, and executable interpolation are rejected.

Illustrative configuration only: `.invalid` endpoints and model names below are placeholders, not recommended or verified products.

```yaml
version: 1
secrets_file: secrets.yaml

providers:
  - name: team-proxy
    alias: tp
    type: anthropic
    base_url: https://anthropic.example.invalid
    api_key: { secret: team_proxy }
    models:
      - name: fast-model
        role: simple
      - name: everyday-model
        role: daily
      - name: reasoning-model
        role: complex

  - name: responses-proxy
    alias: rp
    type: openai-responses
    base_url: https://responses.example.invalid/v1
    api_key: { secret: responses_proxy }
    models:
      - name: fast-model
        role: simple
        context_window: 128000
      - name: everyday-model
        role: daily
        context_window: 128000
      - name: reasoning-model
        role: complex
        context_window: 128000
        reasoning_effort: high

harnesses:
  claude-code:
    providers: [team-proxy]
    default: { write: false, provider: team-proxy, role: daily }
  codex:
    providers: [responses-proxy]
    default: { write: false, provider: responses-proxy, role: daily }

commands:
  bin_dir: ~/.local/bin

```

### Field contract

- `version`: required integer; v1 accepts only `1`.
- Provider `name`: stable identifier, lowercase letters, digits and hyphens, starting with a letter. Unique across the file. Native IDs use a reserved `hs-` prefix.
- `alias`: same syntax, optional; defaults to `name`. Unique across providers and generated command names. Never infer `tp` from a brand name.
- `type`: protocol, not vendor. v1 values: `anthropic`, `openai-chat`, `openai-responses`, `google-genai`. Adapter support is explicit. Vendor-specific OAuth/cloud signing is deferred.
- `base_url`: required absolute HTTP(S) endpoint; reject embedded credentials, fragments, and secret-bearing query parameters. Preserve its path; adapters append only documented API suffixes. An adapter must never silently convert Chat Completions into Responses or Anthropic Messages.
- `api_key`: exactly `{secret: ID}` or `{none: true}` for a keyless endpoint. No literal key in the canonical config. IDs use the provider identifier syntax plus underscores.
- `models`: exactly three entries with roles `simple`, `daily`, `complex`, each once. `name` is a user-facing model label; optional `id` is the exact provider API model ID and defaults to `name`. Repeated IDs across roles are allowed. Ordering has no semantic meaning.
- Optional model fields: `context_window`, `max_output_tokens` (positive integers; output cannot exceed context), `reasoning` (boolean), `reasoning_effort` (string), `input` (list of text/image). Missing metadata is omitted unless the target requires it; required missing metadata is a validation error, never fabricated.
- Optional `headers`: map of literal non-secret strings or `{secret: ID}` references. Authentication headers must be declared as secret references. Auth mechanism conflicts are errors.
- Optional `overrides.<harness-id>` on a provider or model: typed adapter-specific fields, including an alternative `base_url` or protocol `type` for a multi-protocol gateway and native provider/model options under an `options` map. Override precedence is common fields, provider override, model override. Unsupported fields fail validation; overrides cannot modify safety, hooks, plugins, commands, or arbitrary destination paths.
- Provider-level endpoint overrides inherit the secret only because the user explicitly declared the alternative endpoint. Neither discovery nor fallback may redirect a key to a guessed endpoint.
- `harnesses`: optional adapter settings, not an enablement list. There is no `enabled` flag. `sync` without `--harness` targets all detected supported harnesses; `--harness` narrows this set. Managed launches target only their own harness/provider. `providers` omitted means all compatible configured providers; an explicit incompatible selection is an error. A harness with zero compatible providers is skipped with a reason. `commands.enabled` is also removed: sync creates missing selected wrappers by default; `sync --no-commands` suppresses wrapper creation/update for that invocation.
- Adapter settings may specify `executable` and `config_path` explicitly. These override detection, are validated, and are visible in the plan. Adapter-specific settings such as a DeepSeek base profile or OpenClaw gateway port live under `options` in this block and use the adapter's strict options schema.
- `default.write` defaults to false. `default.provider` is required whenever a default update is requested; no selection based on list order. `default.role` defaults to daily. Multi-provider adapters register the selected catalog and set one active default; single-provider adapters write only the chosen provider.
- Namespaced model aliases are `hs-<provider>-<role>` where native aliases exist. Otherwise the launcher maps the role to the exact model ID.

### Model identity and translation

Keep three concepts separate: `role` selects task size, `name` labels the entry for the user, and `id` identifies the model at the configured provider endpoint. If `id` is omitted, `name` is used unchanged. Provider-local IDs are authoritative; there is no global model-ID equivalence table in v1.

```yaml
# Entries within two different providers; remaining roles omitted for illustration.
# These IDs are illustrative, not real service claims.
# Provider A:
models:
  - name: shared-coder
    id: vendor/coder-v1
    role: daily
# Provider B could use the same label with id: coder-v1-20260901
```

Resolution is `(provider, role) -> model entry -> overrides.<harness-id>.id, if present -> id -> name`. Per-harness `id` overrides are explicit endpoint-specific exceptions, usually paired with an alternative gateway endpoint/protocol; they do not imply that every harness needs a different API model ID. `plan` displays label, role, resolved upstream ID, endpoint and emitted native selector. No lowercasing, punctuation conversion, prefix stripping, date removal or automatic alias expansion is allowed.

Adapters maintain **format mappings**, not guessed semantic equivalence: Pi's native `id`, Kimi's native `model`, and Codex/Claude's selected model receive the resolved upstream ID. OpenCode's selector adds the local provider prefix to the full ID; a slash already in that ID remains intact. Native local aliases must resolve to the same upstream ID; they are not substituted into API requests. Each adapter must prove this with a stub endpoint/request test, including custom IDs, slashes, dated IDs and two providers sharing one display label.

Provider catalogs can change independently, use deployment-specific names, or be unavailable. Normal sync performs local validation only and reports remote model availability as unverified. It neither queries inference endpoints nor silently changes a configured ID. A future opt-in catalog lookup may suggest IDs but cannot become the authority or overwrite user mappings. Unsupported native alias/remapping behavior must fail explicitly instead of routing to a similarly named model.

Evidence checked 2026-09-15: [Anthropic's model overview](https://platform.claude.com/docs/en/models/overview) distinguishes platform model IDs; [OpenRouter's Sonnet 4.5 page](https://openrouter.ai/anthropic/claude-sonnet-4.5) uses a vendor-prefixed ID; [OpenCode](https://opencode.ai/docs/models/) specifies `provider_id/model_id`; [Kimi](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/config-files) separates a local model alias from its server-facing `model`. These interfaces justify explicit provider-local IDs and adapter syntax conversion rather than a hardcoded universal name translator.

### Role semantics

All three roles are available through `harness-sync run HARNESS --provider ALIAS --role ROLE -- ...`. Suffixed commands use daily. Claude's native tier mapping and OpenCode's small-model slot are used where documented. Other adapters retain three selectable roles without claiming the harness will automatically classify task complexity. No quality-tier or cross-provider fallback is enabled implicitly.

## 4. Proposed commands

These are the target CLI commands. See README for the implemented framework subset; native operations require a completed adapter.

```sh
harness-sync init
harness-sync detect
harness-sync validate
harness-sync plan --harness claude-code,codex
harness-sync sync --harness claude-code --harness codex
harness-sync run claude-code --provider tp --role complex -- --help
claude-tp --help

# Explicit default updates; never implied by ordinary sync
harness-sync sync --harness claude-code --write-defaults --default-provider tp
harness-sync sync --harness all --profiles-only

harness-sync status --json
harness-sync doctor --harness all
harness-sync secrets set team_proxy
harness-sync secrets list
harness-sync secrets delete team_proxy
harness-sync rollback TRANSACTION_ID
harness-sync prune --harness pi
```

- `init` creates a starter config and empty secrets file only when absent. It neither installs harnesses nor changes their default files or shell startup files.
- `plan` is a read-only, redacted diff: includes paths, ownership conflicts, compatibility, skipped harnesses, wrappers, credentials destinations, and reload/restart expectations. `sync --dry-run` is equivalent.
- `sync` applies one validated plan; no confirmation is required for already-authorized scopes. `--write-defaults` grants permission only for selected harnesses in this invocation. `--default-provider` and `--role` override configured default selection for that invocation. `--profiles-only` overrides persisted default-write permission. Conflicting flags fail.
- `run` synchronizes the selected harness/provider immediately before launching it: reread inputs, refresh detection, validate, and apply changed managed artifacts. It loads current credentials even when profile bytes are unchanged. Suffixed commands invoke this same path; no watcher, polling interval, service or daemon exists.
- `run` also applies that harness's configured default update only if `default.write: true`; otherwise native defaults stay untouched. The configured default provider can differ from the launched provider. Validate both scopes before applying either; launch only after successful synchronization. `run --profiles-only` suppresses an authorized default update for that invocation. Wrapper arguments belong to the native harness; use explicit `run` for tool options.
- `harness-sync run HARNESS -- ...` without `--provider` synchronizes that harness, applies only authorized defaults, then starts the original command using its native default configuration. It does not select the first configured provider. Bare original commands such as `claude` cannot trigger synchronization unless intercepted; v1 deliberately leaves them intact. Use the managed launcher for automatic pre-launch sync, or run `sync` before the original command. No files change just because a config file was edited.
- Arguments after `--` and wrapper arguments are forwarded as an argument array, without shell evaluation. Provider/config/home-changing flags that defeat profile selection are rejected with a message directing the user to the original command. Explicit native model flags may override the role, within the pinned provider. Each adapter declares the relevant flags and validates subcommand syntax.
- `secrets set` uses a hidden prompt, or `--stdin`; no secret command-line value. `list` prints IDs only. Deletion refuses a referenced secret unless its references have been removed first.
- `prune` shows obsolete managed artifacts; `--apply` deletes only unchanged owned files/wrappers. It never deletes sessions, auth stores, or unrelated native settings. Provider removal disables future wrapper launches immediately; physical removal is explicit.
- Exit codes: 0 success/no change; 2 invalid input; 3 missing/unsupported harness; 4 ownership or concurrent-edit conflict; 5 I/O or transaction failure. Launched harnesses preserve their own exit code/signals. JSON mode separates machine-readable stdout from stderr diagnostics.

## 5. Output layout and default protection

```text
~/.config/harness-sync/
  config.yaml                       # user-owned, no secrets
  secrets.yaml                      # user-owned, mode 0600
  generated/
    profiles/<harness>/<alias>/      # native profile config and launch metadata
    default-previews/<harness>/      # redacted proposed default changes
    env.sh                          # export HS_<SECRET_ID>='...' statements
~/.local/state/harness-sync/
  state.json                        # detection, ownership, versions, transaction status
  lock
  transactions/<id>/                # protected journal and backups
  runtime/<harness>/<alias>/         # mutable native profile state if isolated home needed
~/.local/bin/<native-command>-<alias>
```

XDG config/state overrides apply to the tool; they do not arbitrarily relocate harness defaults. All paths become absolute in state. Adapter-native profile files may need placement beside a native config (Codex is one example); these are declared profile artifacts, distinct from the default file, and collision-checked.

Ordinary sync can create/update managed profile files and missing suffixed commands. It cannot write even a previously absent native default file without permission. Default previews contain field-level redacted changes, never a full secret-bearing copy.

Default updates preserve unrelated settings, comments where supported, ordering where feasible, native authentication, MCP, plugins, trust, permissions, and project settings. Use structural edits; never regex-rewrite whole config files. Invalid target files abort that target before any commit. If format-preserving editing cannot safely handle a file, report it instead of stripping content.

The first explicit default update may replace selected provider/model/auth fields after backing up their original values. Subsequent updates use a three-way comparison (last applied, current file, desired file). Manual changes to an owned field become conflicts. Unrelated user changes merge. An explicit `--adopt-changes` with default-write authorization may resolve these owned-field conflicts; it is never used by an automatic pre-launch refresh or as a blanket file overwrite. Turning off `default.write` stops future writes; it does not silently restore previous defaults.

## 6. Secrets and manual shell setup

```yaml
version: 1
keys:
  team_proxy: "replace-me"
  responses_proxy: "replace-me"
```

The secrets file is the only manually maintained key store. Generated exports, native literal-key fields, and protected backups are derived copies and must be treated as secrets. The tool does not promise encryption at rest or erase copies from running processes.

- Private directories: 0700. Secrets, native secret outputs, environment exports and backups: 0600. Wrappers: 0700, containing no literal keys. Enforce restrictive permissions before writing.
- Generated `env.sh` exports only namespaced `HS_<NORMALIZED_SECRET_ID>` names, preventing two providers from overwriting a common `OPENAI_API_KEY`. Normalization collisions fail validation.
- A launcher reads current secrets directly and assigns only the selected provider's required native variables in the child environment. It does not depend on the shell having sourced fresh exports. Clear adapter-known conflicting auth/provider variables in that child only; preserve unrelated environment.
- Default native config uses namespaced environment references where available. A plain native command then requires a new shell or re-sourcing `env.sh` after key rotation. Where literal credentials or native dotenv files are required, sync updates only the authorized fields. Explain this distinction in status.
- Generated shell values use correct single-quote escaping; no `eval`, command substitution, or source of user-provided arbitrary shell fragments. API keys containing NUL/newline are rejected in v1. Native dotenv formatting is distinct from shell-export formatting.
- Shell setup is documentation-only. The tool never edits shell startup files and provides no shell install/uninstall commands. The README explains how to add the configured bin directory to PATH when necessary and optionally source the generated export file for bare harness commands. Managed launchers load credentials directly and do not require sourced exports. Document custom paths and Bash login-shell behavior; users add or remove startup lines themselves.
- File-backed targets receive resolved values only at apply time. Logs, exception messages, plans, state, launch metadata, and command arguments never contain raw keys. State stores secret references and keyed fingerprints where change detection is needed, not plain secret hashes.
- Permission errors, missing keys, or unrepresentable credentials fail before writing. The next sync or managed launch propagates key rotation to its selected scope; an invalid edit retains the last successful generation. `run` refuses stale invalid inputs rather than silently using old credentials.
- Existing OAuth/keychain stores are neither imported nor overwritten. Selecting a managed API-key profile explicitly pins that profile's endpoint/auth; ordinary native login remains available through the unmodified command.

## 7. Detection and persisted state

`detect` checks PATH plus explicit executable paths, resolves symlinks, and probes supported `--version`/help entry points with timeouts. Probe adapters must account for CLIs that initialize files even for introspection; use temporary homes when needed. Never start an interactive harness, sign in, install packages, dump credentials, or invoke arbitrary commands from config during detection.

Record for each harness: ID, executable path/realpath, version, checked-at time, detected config paths, relevant home overrides, config existence, capabilities, and status (`installed`, `config-only`, `not-found`, `unsupported-version`, `probe-failed`). Config directories alone do not prove installation. Exclude the tool's wrappers from original-executable discovery. Multiple candidates are reported; explicit path wins, otherwise first original executable on PATH.

`state.json` also records schema version, last successful generation, input fingerprints, owned paths/keys, prior output fingerprints, wrapper ownership, transaction IDs, default-write scope used, and per-target result. It contains no credentials and is not a substitute for probing the machine. Refresh on detect/sync and each managed launch; executable or environment changes invalidate cached capability results. No support version range is claimed until tested.

Unknown versions may be detected, but writing requires a recognized capability/schema combination. Config-only installations are reported and skipped unless the user explicitly supplies a validated executable. Deleting state must not cause automatic adoption of files that happen to look generated; recover from a valid journal or require explicit adoption.

## 8. Command-triggered synchronization and concurrency

1. Resolve selection; parse both inputs from a stable snapshot.
2. Refresh detection and validate protocol/metadata/credentials for selected targets.
3. Build pure adapter plans; calculate redacted diffs and detect collisions.
4. Acquire a per-tool lock, recheck all input/output fingerprints and stage files beside destinations on their filesystems.
5. Write a protected transaction journal/backups, validate staged native syntax, then atomically replace each file. Publish generation/state last. Wrappers invoke the runner, which checks transaction consistency before launch.
6. On failure, restore files already changed if their contents still match this transaction; never overwrite intervening user edits. Mark any unresolved recovery explicitly. On restart, recover unfinished journals before a new apply.

Atomic rename is per-file; there is no claim of a filesystem-wide atomic transaction across harnesses. Stage and validate everything before committing. Default behavior aborts all selected changes if any selected target has a validation/conflict error. An optional `--best-effort` explicitly allows successful harnesses to commit separately and returns a nonzero code with per-harness results. Missing auto-detected harnesses are skipped; explicitly requested missing harnesses are errors.

Each sync/launch reads a stable snapshot of both input files and checks for concurrent replacement before committing. Retry a concurrently changing snapshot a bounded number of times, then fail clearly; do not start a persistent watcher. Identical output does not rewrite files or change mtime. Invalid or partially saved inputs abort the command and prevent launch. Output drift and managed-field conflicts are checked on every sync/launch. Other providers/harnesses refresh on their next selected sync or launch, not in the background.

Synchronization updates files; it does not guarantee that already-running harnesses reload them. Never terminate/restart sessions or gateways automatically. Show `applied`, `new-launch-required`, or `native-reload-possible` based on the adapter. A removed provider or key is not remotely revoked by deleting local files.

## 9. Command creation and isolation

Create `<native-command>-<alias>` only if the destination is absent and no same-name command is already found on PATH. Report collisions and retain the existing command; the explicit `harness-sync run` path remains usable. Existing tool-owned wrappers may be updated only if unchanged. Document that arbitrary parent-shell aliases/functions cannot be discovered reliably by a subprocess; users can inspect a conflicting name with `type -a <command>` in their shell. Never edit or replace `claude`, `codex`, `pi`, `dsh`, `kimi`, `opencode`, `hermes`, or `openclaw`.

Wrappers call the tool using a stable absolute entry point and provider/harness identifiers; the runner resolves the original executable without recursing. Preserve working directory, terminal interaction, arguments, signals, and exit status. Installation relocation should produce a repair hint, not a silently broken wrapper.

Prefer config overlays when they reliably pin endpoint/auth. When native config isolation requires a separate home, isolate the harness's state only, never the OS `HOME`. Do not copy credentials, sessions, skills, or plugin installations implicitly. Each adapter README must explain whether sessions and personal settings are shared or separate. Launcher environment setup must pair endpoint and credential changes and reject conflicting routing flags.

## 10. Architecture and repository layout

```text
README.md
SPEC.md
docs/compatibility.md
harnesses/
  claude-code/{README.md,SPEC.md}
  codex/{README.md,SPEC.md}
  pi/{README.md,SPEC.md}
  deepseek-harness/{README.md,SPEC.md}
  kimi-code/{README.md,SPEC.md}
  opencode/{README.md,SPEC.md}
  hermes-agent/{README.md,SPEC.md}
  openclaw/{README.md,SPEC.md}
# Shared framework exists; native implementations are separate:
# src/harness_sync/ — CLI, schema, secrets, planner, transactions, launcher
# harnesses/<id>/adapter.py, fixtures/, tests/ — all harness-specific behavior
# tests/ — shared contract, filesystem, subprocess and lifecycle tests
# pyproject.toml — packaging includes harness adapter resources explicitly
```

The adapter registry loads the eight bundled modules from their own directories; no downloaded plugins or config-selected Python imports. The shared core owns filesystem writes, secret resolution, locking, backups, and redaction.

Adapter contract (exact types in `src/harness_sync/contracts.py`):

- `detect(DetectionContext) -> Detection`: tested capabilities, executable and allowed native paths.
- `validate(Provider, RenderContext) -> None`: protocol, metadata and adapter-owned options schemas.
- `profiles(Provider, RenderContext) -> tuple[Artifact, ...]`: deferred native render/verify functions.
- `defaults(providers, selected, role, context) -> tuple[Artifact, ...]`: authorized structural native merges.
- `launch(provider, role, arguments, context, secrets) -> LaunchSpec`: argv plus private environment overlay.

Core snapshot reads and protected baselines are supplied through `RenderContext`; each `Artifact` has its own native verifier. See the development guide for implementation requirements.

No adapter writes files directly or invokes a shell to interpolate config values. Each declares field ownership, protocol support, minimum tested capabilities, precedence limits and reload behavior.

## 11. Acceptance criteria and implementation order

Framework approved; native adapter work may be implemented independently:

1. Implement canonical schema, secrets store, detector/state, pure planner and transaction engine.
2. Implement each adapter in its directory against pinned source/version fixtures; review the local spec before its code. No placeholder adapter counts as complete.
3. Implement wrappers/runner, default merge and command-triggered synchronization; document manual shell setup.
4. Run shared and adapter-specific acceptance tests; update README with actual installation commands and verified versions.

Required tests include:

- Three-role validation, repeated upstream IDs, missing metadata, protocol mismatch and unknown overrides.
- No default-file creation/modification during profile-only sync, including wrapper launch.
- Authorized default merges preserve unrelated config, comments, OAuth and permissions; repeated sync is byte/mtime stable.
- Two concurrent providers with the same native API-key variable receive different correct endpoints/keys in child processes; original command/config stays intact.
- Each role selects the correct model for all eight adapters. Native precedence cannot silently pair an old key with a new endpoint.
- Command collisions, edited wrappers, spaces and quotes in paths/arguments, signal forwarding and no recursion.
- Key rotation, invalid/partial edits, missing/removed keys, shell escaping and no secret leakage in any diagnostic/output.
- Fresh reads on every managed launch, unchanged-output idempotence, concurrent atomic saves, selection boundaries, default permission changes, missing installations and version changes; bare original commands remain unwrapped.
- Fault-injected write failure, crash recovery, cross-process locking, external edits, conservative rollback, symlink/path-target checks and permissions.
- Isolated native smoke checks on every claimed supported version; no paid inference unless explicitly enabled with test credentials.
- Documentation includes all eight adapters, source links, known limitations and verified-version evidence.

## 12. Implementation boundary

This draft proposes Python, the YAML schema above, three named roles, private API-key storage, profile-only writes by default, documented manual shell setup, and all eight adapters as v1 requirements. Approving implementation does not itself enable native default writes on this machine; that remains a separate runtime setting or command choice.

The user authorized the shared framework. Harness-specific implementations belong to subsequent adapter tasks. Review the [compatibility matrix](docs/compatibility.md) and each adapter spec before its implementation. Development and tests do not install personal wrappers or change real native harness configuration.
