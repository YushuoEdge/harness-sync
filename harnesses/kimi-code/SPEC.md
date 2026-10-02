# Kimi Code adapter specification

Status: **Implemented for Kimi Code 2.1.1.** Adapter ID: `kimi-code`. Native command: `kimi`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

Current documentation places `config.toml` under `~/.kimi-code`, relocatable using `KIMI_CODE_HOME`. It defines provider/model tables, literal `api_key`, required model context size, and explicit credential behavior. [Configuration files](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/config-files). CLI model selection uses `--model`/`-m`. [Command reference](https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command).

## Adapter design

- Detect `kimi`, version, home/config capabilities and legacy config presence. Legacy Python installations are unsupported by this adapter; never migrate their data automatically.
- Render a full managed `config.toml` in isolated `KIMI_CODE_HOME` per provider. Map protocol types to native `anthropic`, `openai`, `openai_responses`, or `google-genai`, subject to installed capability tests.
- Native provider table: namespaced provider ID, `type`, `base_url`, resolved `api_key`. Native model tables: `hs-<alias>-<role>`, `provider`, upstream `model`, and `max_context_size`. Require canonical `context_window` for every model when this native field is mandatory.
- Render `default_model` as daily; launch `kimi-<alias>` with the isolated home and requested `--model` alias. Maintain stable isolated sessions across launches, not ephemeral homes.
- Materialize a private API key in the profile config; do not assume shell `KIMI_API_KEY` supplies it. Clear temporary `KIMI_MODEL_*` overrides that could alter selection, subject to native tests.
- Ordinary user sessions, skills and OAuth remain in the original home and are not copied. Model capabilities/effort fields must be mapped to recognized native options; unsupported explicit values fail with a precise error.

## Authorized default writes

Merge owned `providers`/`models` entries and `default_model` in the detected native TOML. Preserve managed OAuth entries, unrelated provider keys, services, UI files and permissions. Resolve keys only for the managed API-key entries. A native provider's own refresh process must not silently overwrite the tool's model metadata; use recognized override fields if necessary and verify ownership conflicts.

## Verification and limitations

Test current and any explicitly supported legacy path/flag combinations, mandatory context sizes, literal-key rotation, role aliases and credential precedence. Assert no guessed `--config-file` flag is emitted for releases that lack it. Missing metadata is a config error, not a synthesized context limit. Config editing is separate from changing active sessions; new launches are the guaranteed activation boundary.

## Command-triggered sync and model identity

Every generated provider command uses the common pre-launch sync contract: refresh this harness/provider, apply native defaults only when independently authorized, then launch. There is no background watcher or harness enablement flag. A bare original executable remains unchanged and does not invoke the sync tool.

Consume the core's resolved provider-local model `id` (falling back to `name`), never infer an ID from the display label. Native role/model aliases are local selectors and must resolve to that exact upstream ID. Test two providers using the same label but different API IDs, explicit per-harness ID overrides, slash-containing IDs, repeated IDs and unsupported remapping. Model-ID conversion must not change endpoint or credentials.

## Planned directory ownership

When implemented, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.

## Implemented release boundary (2026-10-02)

The installed Python CLI was upgraded to 1.52.0, which only prints a deprecation notice.
Installed its official successor `@moonshot-ai/kimi-code` **2.1.1**; the uv installation is retained.
This adapter now targets the successor only, with `KIMI_CODE_HOME`, `~/.kimi-code/config.toml`,
`--model`, and protocol types `anthropic`, `openai`, `openai_responses`, `google-genai`.
It no longer emits `--config-file`, `--thinking` or `KIMI_SHARE_DIR`.
Provider entries use `model_source = "static"`; no provider discovery or account login is needed.
Output limits and reasoning effort remain rejected. Existing user defaults and sessions are
not migrated; generated profiles retain the shared ownership/conflict protections.
All transports and roles passed localhost checks with exact IDs and fake credentials.
Native home/version/help fixtures and adapter tests verify the new contract.
