# Harness Sync Config — specification

Status: **Draft for approval; no implementation authorized yet.**

## 1. Purpose and scope

One human-edited YAML configuration defines providers and three task roles per provider. One separate secrets file holds API keys. The tool translates these inputs into harness-specific profiles, provider-suffixed launch commands, and explicitly enabled default configuration updates.

The proposed executable is `harness-sync` (no short alias installed automatically). Initial platform scope: macOS and Linux, with Bash and Zsh integration. Implementation proposal: Python 3.11+, packaged for `uv tool install` / `pipx`; Typer, Pydantic, ruamel.yaml, tomlkit, format-preserving JSON/JSONC/JSON5 editing, and watchfiles. Dependency versions and JSON editing library will be selected and pinned during implementation. Native Windows, a GUI, protocol proxying, OAuth migration, and automatic task-complexity classification are outside v1.

All eight adapters are required for v1: Claude Code, Codex, Pi, DeepSeek Harness, Kimi Code, OpenCode, Hermes Agent, and OpenClaw. A draft adapter is not implemented support. Each adapter must pass its release gates before v1 can claim support; incompatible provider/harness pairs receive explicit diagnostics.

## 2. Requirements and decisions

| Requirement | Proposed behavior |
| --- | --- |
| Providers and models | Ordered provider list; exactly one entry for each role: simple, daily, complex |
| Automatic synchronization | Foreground watcher; optional per-user launchd/systemd service installed explicitly |
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
    enabled: true
    providers: [team-proxy]
    default: { write: false, provider: team-proxy, role: daily }
  codex:
    enabled: true
    providers: [responses-proxy]
    default: { write: false, provider: responses-proxy, role: daily }
  pi: { enabled: true }
  deepseek-harness: { enabled: true }
  kimi-code: { enabled: true }
  opencode: { enabled: true }
  hermes-agent: { enabled: true }
  openclaw: { enabled: true }

commands:
  enabled: true
  bin_dir: ~/.local/bin

watch:
  debounce_ms: 500
  reconcile_seconds: 30
```

### Field contract

- `version`: required integer; v1 accepts only `1`.
- Provider `name`: stable identifier, lowercase letters, digits and hyphens, starting with a letter. Unique across the file. Native IDs use a reserved `hs-` prefix.
- `alias`: same syntax, optional; defaults to `name`. Unique across providers and generated command names. Never infer `tp` from a brand name.
- `type`: protocol, not vendor. v1 values: `anthropic`, `openai-chat`, `openai-responses`, `google-genai`. Adapter support is explicit. Vendor-specific OAuth/cloud signing is deferred.
- `base_url`: required absolute HTTP(S) endpoint; reject embedded credentials, fragments, and secret-bearing query parameters. Preserve its path; adapters append only documented API suffixes. An adapter must never silently convert Chat Completions into Responses or Anthropic Messages.
- `api_key`: exactly `{secret: ID}` or `{none: true}` for a keyless endpoint. No literal key in the canonical config. IDs use the provider identifier syntax plus underscores.
- `models`: exactly three entries with roles `simple`, `daily`, `complex`, each once. `name` is the exact upstream model ID; repeated IDs across roles are allowed. Ordering has no semantic meaning.
- Optional model fields: `context_window`, `max_output_tokens` (positive integers; output cannot exceed context), `reasoning` (boolean), `reasoning_effort` (string), `input` (list of text/image). Missing metadata is omitted unless the target requires it; required missing metadata is a validation error, never fabricated.
- Optional `headers`: map of literal non-secret strings or `{secret: ID}` references. Authentication headers must be declared as secret references. Auth mechanism conflicts are errors.
- Optional `overrides.<harness-id>` on a provider or model: typed adapter-specific fields, including an alternative `base_url` or protocol `type` for a multi-protocol gateway and provider/model options. Override precedence is common fields, provider override, model override. Unsupported fields fail validation; overrides cannot modify safety, hooks, plugins, commands, or arbitrary destination paths.
- Provider-level endpoint overrides inherit the secret only because the user explicitly declared the alternative endpoint. Neither discovery nor fallback may redirect a key to a guessed endpoint.
- `harnesses`: omitted adapters are enabled for auto-detected installations. `providers` omitted means all compatible configured providers; an explicit incompatible selection is an error. A harness with zero compatible providers is skipped with a reason. `enabled: false` excludes it unless a CLI selection explicitly includes it.
- Adapter settings may specify `executable` and `config_path` explicitly. These override detection, are validated, and are visible in the plan. Adapter-specific settings such as a DeepSeek base profile or OpenClaw gateway port live in this block.
- `default.write` defaults to false. `default.provider` is required whenever a default update is requested; no selection based on list order. `default.role` defaults to daily. Multi-provider adapters register the selected catalog and set one active default; single-provider adapters write only the chosen provider.
- Namespaced model aliases are `hs-<provider>-<role>` where native aliases exist. Otherwise the launcher maps the role to the exact model ID.

### Role semantics

All three roles are available through `harness-sync run HARNESS --provider ALIAS --role ROLE -- ...`. Suffixed commands use daily. Claude's native tier mapping and OpenCode's small-model slot are used where documented. Other adapters retain three selectable roles without claiming the harness will automatically classify task complexity. No quality-tier or cross-provider fallback is enabled implicitly.

## 4. Proposed commands

These are the intended CLI contract, not runnable commands in this documentation-only repository.

```sh
harness-sync init
harness-sync detect
harness-sync validate
harness-sync plan --harness claude-code,codex
harness-sync sync --harness claude-code --harness codex
harness-sync watch --harness all
harness-sync run claude-code --provider tp --role complex -- --help
claude-tp --help

# Explicit default updates; never implied by ordinary sync
harness-sync sync --harness claude-code --write-defaults --default-provider tp
harness-sync sync --harness all --profiles-only

# Deliberately enable automatic operation and shell integration
harness-sync service install --harness all
harness-sync service status
harness-sync service uninstall
harness-sync shell install --shell zsh
harness-sync shell uninstall --shell zsh

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
- `sync` applies one validated plan; no confirmation is required for already-enabled scopes. `--write-defaults` grants permission only for selected harnesses in this invocation. `--default-provider` and `--role` override configured default selection for that invocation. `--profiles-only` overrides persisted default-write permission. Conflicting flags fail.
- `watch` uses the same scope rules as sync, performs an initial sync, then watches the canonical config and secrets file. A default-write flag grants permission for that watcher process's lifetime; it is not persisted.
- `service install` records an explicit absolute executable, input config and harness selection in a user service. Foreground sync/watch remains available without a service manager. The service obeys persisted `default.write`; one-shot default flags are not copied into service settings. Logs are bounded and redacted. Uninstall stops/removes only the tool's service.
- `run` refreshes the selected managed profile if stale, loads only its credentials, and launches the detected original executable. It never applies native defaults. A failed refresh prevents launch with mixed credentials. It resolves aliases and full provider names unambiguously.
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

The first explicit default update may replace selected provider/model/auth fields after backing up their original values. Subsequent updates use a three-way comparison (last applied, current file, desired file). Manual changes to an owned field become conflicts. Unrelated user changes merge. An explicit `--adopt-changes` with default-write authorization may resolve these owned-field conflicts; it is never used by a watcher or as a blanket file overwrite. Turning off `default.write` stops future writes; it does not silently restore previous defaults.

## 6. Secrets and shell integration

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
- `shell install` adds one marked, idempotent block to `.zshrc` or `.bashrc` sourcing the absolute export path and adding the configured bin directory once. It backs up the startup file and preserves existing content. A custom startup path is explicit; Bash login-shell caveats are documented. Uninstall removes only the unchanged marked block.
- File-backed targets receive resolved values only at apply time. Logs, exception messages, plans, state, launch metadata, and command arguments never contain raw keys. State stores secret references and keyed fingerprints where change detection is needed, not plain secret hashes.
- Permission errors, missing keys, or unrepresentable credentials fail before writing. Watcher rotation updates all selected derived outputs; an invalid edit retains the last successful generation. `run` refuses stale invalid inputs rather than silently using old credentials.
- Existing OAuth/keychain stores are neither imported nor overwritten. Selecting a managed API-key profile explicitly pins that profile's endpoint/auth; ordinary native login remains available through the unmodified command.

## 7. Detection and persisted state

`detect` checks PATH plus explicit executable paths, resolves symlinks, and probes supported `--version`/help entry points with timeouts. Probe adapters must account for CLIs that initialize files even for introspection; use temporary homes when needed. Never start an interactive harness, sign in, install packages, dump credentials, or invoke arbitrary commands from config during detection.

Record for each harness: ID, executable path/realpath, version, checked-at time, detected config paths, relevant home overrides, config existence, capabilities, and status (`installed`, `config-only`, `not-found`, `unsupported-version`, `probe-failed`). Config directories alone do not prove installation. Exclude the tool's wrappers from original-executable discovery. Multiple candidates are reported; explicit path wins, otherwise first original executable on PATH.

`state.json` also records schema version, last successful generation, input fingerprints, owned paths/keys, prior output fingerprints, wrapper ownership, transaction IDs, default-write scope used, and per-target result. It contains no credentials and is not a substitute for probing the machine. Refresh on detect/sync, watcher startup and every reconciliation interval; executable or environment changes invalidate cached capability results. No support version range is claimed until tested.

Unknown versions may be detected, but writing requires a recognized capability/schema combination. Config-only installations are reported and skipped unless the user explicitly supplies a validated executable. Deleting state must not cause automatic adoption of files that happen to look generated; recover from a valid journal or require explicit adoption.

## 8. Synchronization, watch behavior, and concurrency

1. Resolve selection; parse both inputs from a stable snapshot.
2. Refresh detection and validate protocol/metadata/credentials for selected targets.
3. Build pure adapter plans; calculate redacted diffs and detect collisions.
4. Acquire a per-tool lock, recheck all input/output fingerprints and stage files beside destinations on their filesystems.
5. Write a protected transaction journal/backups, validate staged native syntax, then atomically replace each file. Publish generation/state last. Wrappers invoke the runner, which checks transaction consistency before launch.
6. On failure, restore files already changed if their contents still match this transaction; never overwrite intervening user edits. Mark any unresolved recovery explicitly. On restart, recover unfinished journals before a new apply.

Atomic rename is per-file; there is no claim of a filesystem-wide atomic transaction across harnesses. Stage and validate everything before committing. Default behavior aborts all selected changes if any selected target has a validation/conflict error. An optional `--best-effort` explicitly allows successful harnesses to commit separately and returns a nonzero code with per-harness results. Missing auto-detected harnesses are skipped; explicitly requested missing harnesses are errors.

Watch parent directories as well as files to handle editor atomic saves. Debounce 500 ms, wait for a stable parseable snapshot, compare fingerprints, and reconcile every 30 seconds to recover missed events. Never watch generated files as source inputs. Identical output does not rewrite files or change mtime. Invalid edits produce one diagnostic per distinct failure and keep watching. State/output drift is checked during reconciliation; managed-field conflicts are reported without a repeated overwrite loop.

Synchronization updates files; it does not guarantee that already-running harnesses reload them. Never terminate/restart sessions or gateways automatically. Show `applied`, `new-launch-required`, or `native-reload-possible` based on the adapter. A removed provider or key is not remotely revoked by deleting local files.

## 9. Command creation and isolation

Create `<native-command>-<alias>` only if the destination is absent and no same-name command is already found on PATH. Report collisions and retain the existing command; the explicit `harness-sync run` path remains usable. Existing tool-owned wrappers may be updated only if unchanged. Detect shell aliases/functions when shell integration has a reliable view; otherwise document that arbitrary parent-shell aliases cannot be discovered by a subprocess. Never edit or replace `claude`, `codex`, `pi`, `dsh`, `kimi`, `opencode`, `hermes`, or `openclaw`.

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
# After approval only:
# src/harness_sync/ — CLI, schema, secrets, planner, transactions, watch, service, shell
# harnesses/<id>/adapter.py, fixtures/, tests/ — all harness-specific behavior
# tests/ — shared contract, filesystem, subprocess and lifecycle tests
# pyproject.toml — packaging includes harness adapter resources explicitly
```

The adapter registry loads the eight bundled modules from their own directories; no downloaded plugins or config-selected Python imports. The shared core owns filesystem writes, secret resolution, locking, backups, and redaction.

Adapter contract:

- `detect(context) -> Detection`: executable, version, paths, supported feature set.
- `validate(provider, models, detection) -> diagnostics`: protocol and native field requirements.
- `render_profile(...) -> ArtifactPlan`: native files, secret destinations/references, owned fields, profile placements.
- `plan_default(existing, ...) -> PatchPlan`: field-level edits and conflict metadata.
- `launch(profile, role, argv) -> LaunchPlan`: original executable, argv, child environment, state location; secret values are carried privately and never serialized into normal plan output.
- `verify(staged, detection) -> diagnostics`: offline native syntax/schema verification; optional native probe in isolated fixtures.

No adapter writes files directly or invokes a shell to interpolate config values. Each declares field ownership, protocol support, minimum tested capabilities, precedence limits and reload behavior.

## 11. Acceptance criteria and implementation order

After approval:

1. Implement canonical schema, secrets store, detector/state, pure planner and transaction engine.
2. Implement each adapter in its directory against pinned source/version fixtures; review the local spec before its code. No placeholder adapter counts as complete.
3. Implement wrappers/runner, default merge, shell integration, watcher and user service.
4. Run shared and adapter-specific acceptance tests; update README with actual installation commands and verified versions.

Required tests include:

- Three-role validation, repeated upstream IDs, missing metadata, protocol mismatch and unknown overrides.
- No default-file creation/modification during profile-only sync, including wrapper launch and watch.
- Authorized default merges preserve unrelated config, comments, OAuth and permissions; repeated sync is byte/mtime stable.
- Two concurrent providers with the same native API-key variable receive different correct endpoints/keys in child processes; original command/config stays intact.
- Each role selects the correct model for all eight adapters. Native precedence cannot silently pair an old key with a new endpoint.
- Command collisions, edited wrappers, spaces and quotes in paths/arguments, signal forwarding and no recursion.
- Key rotation, invalid/partial edits, missing/removed keys, shell escaping and no secret leakage in any diagnostic/output.
- Atomic-save watcher events, polling recovery, selection boundaries, default permission changes, missing installations and version changes.
- Fault-injected write failure, crash recovery, cross-process locking, external edits, conservative rollback, symlink/path-target checks and permissions.
- Isolated native smoke checks on every claimed supported version; no paid inference unless explicitly enabled with test credentials.
- Documentation includes all eight adapters, source links, known limitations and verified-version evidence.

## 12. Approval checkpoint

This draft proposes Python, the YAML schema above, three named roles, private API-key storage, profile-only writes by default, explicit service/shell installation, and all eight adapters as v1 requirements. Approving implementation does not itself enable native default writes on this machine; that remains a separate runtime setting or command choice.

Review this specification, the [compatibility matrix](docs/compatibility.md), and the linked adapter specifications before implementation. No application code, wrappers, credentials, services, or native harness configuration are created during this specification phase.
