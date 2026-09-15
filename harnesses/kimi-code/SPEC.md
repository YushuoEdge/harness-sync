# Kimi Code adapter specification

Status: **Draft; awaiting approval.** Adapter ID: `kimi-code`. Native command: `kimi`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

Current documentation places `config.toml` under `~/.kimi-code`, relocatable using `KIMI_CODE_HOME`. It defines provider/model tables, literal `api_key`, required model context size, and explicit credential behavior. [Configuration files](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/config-files). CLI model selection uses `--model`/`-m`. [Command reference](https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command).

## Adapter design

- Detect `kimi`, version, home/config capabilities and legacy config presence. Older `~/.kimi` installations must receive a version-specific mapping or a clear unsupported diagnostic; never migrate them automatically.
- Render a full managed `config.toml` in isolated `KIMI_CODE_HOME` per provider. Map protocol types to native `anthropic`, `openai`, `openai_responses`, or `google-genai`, subject to installed capability tests.
- Native provider table: namespaced provider ID, `type`, `base_url`, resolved `api_key`. Native model tables: `hs-<alias>-<role>`, `provider`, upstream `model`, and `max_context_size`. Require canonical `context_window` for every model when this native field is mandatory.
- Render `default_model` as daily; launch `kimi-<alias>` with the isolated home and requested `--model` alias. Maintain stable isolated sessions across launches, not ephemeral homes.
- Materialize a private API key in the profile config; do not assume shell `KIMI_API_KEY` supplies it. Clear temporary `KIMI_MODEL_*` overrides that could alter selection, subject to native tests.
- Ordinary user sessions, skills and OAuth remain in the original home and are not copied. Model capabilities/effort fields must be mapped to recognized native options; unsupported explicit values fail with a precise error.

## Authorized default writes

Merge owned `providers`/`models` entries and `default_model` in the detected native TOML. Preserve managed OAuth entries, unrelated provider keys, services, UI files and permissions. Resolve keys only for the managed API-key entries. A native provider's own refresh process must not silently overwrite the tool's model metadata; use recognized override fields if necessary and verify ownership conflicts.

## Verification and limitations

Test current and any explicitly supported legacy path/flag combinations, mandatory context sizes, literal-key rotation, role aliases and credential precedence. Assert no guessed `--config-file` flag is emitted for releases that lack it. Missing metadata is a config error, not a synthesized context limit. Config editing is separate from changing active sessions; new launches are the guaranteed activation boundary.

## Planned directory ownership

After approval, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
