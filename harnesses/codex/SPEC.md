# Codex adapter specification

Status: **Implemented and locally verified with Codex CLI 0.154.0.** Adapter ID: `codex`. Native command: `codex`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York). Codex CLI 0.154.0 profile parsing was smoke-checked locally on 2026-09-15 without inference.

## Native interface and evidence

Codex stores configuration under `CODEX_HOME`, normally `~/.codex`. Current documentation describes separate `<profile>.config.toml` overlays selected by `--profile`; it identifies 0.134.0 as the transition from inline profile tables. Providers have `base_url` and `env_key`, and Responses uses `wire_api = "responses"`. [Advanced configuration](https://developers.openai.com/codex/config-advanced).

## Adapter design

- Detect `codex` and its actual profile capability. The initial implementation targets verified separate-file profiles. Older inline-profile versions must use a separately tested isolated-home strategy or be marked unsupported; never edit the default TOML merely to install a profile.
- Render one native TOML profile per provider/role, named `hs-<alias>-<role>.config.toml`. Keep a canonical managed copy and install an owned native profile artifact beside `config.toml` as required. Refuse an existing unowned file of that name.
- Each file selects `model`, `model_provider = "hs-<name>"`, and a matching provider table with endpoint, namespaced `env_key`, and supported wire API. Map optional reasoning effort only after validation.
- Launch `codex-<alias>` with `--profile hs-<alias>-daily`; `run --role` selects another file. Supply the referenced environment variable privately, and use explicit routing/model CLI overrides where needed to keep inherited layers from changing the requested selection. Reject conflicting profile/provider flags.
- v1 guaranteed protocol target is `openai-responses`. Enable `openai-chat` only on a separately verified native wire capability. Anthropic/Google endpoints are incompatible without a declared compatible gateway.
- Retain normal sessions, skills and authentication because the native home is shared. Profile provider credentials are independent of ChatGPT login; no auth-store edits.

## Authorized default writes

Merge namespaced `model_providers` entries and chosen top-level `model`, `model_provider`, and mapped reasoning fields into `config.toml`. Environment-key references use generated exports for ordinary `codex` launches. Preserve unrelated TOML/comments and built-in provider IDs. Remove obsolete tool-owned optional fields only with three-way conflict checks.

## Verification and limitations

Test profile resolution against the detected release, no default changes during installation, CLI precedence, all three roles, key rotation and two providers. Capture versioned native parsing fixtures; documentation alone does not qualify a version as tested. Do not promise that custom models appear in every Codex model picker, or that Desktop/IDE clients honor CLI profiles; v1 scope is the local CLI. Unknown profile format fails before writing.

## Command-triggered sync and model identity

Every generated provider command uses the common pre-launch sync contract: refresh this harness/provider, apply native defaults only when independently authorized, then launch. There is no background watcher or harness enablement flag. A bare original executable remains unchanged and does not invoke the sync tool.

Consume the core's resolved provider-local model `id` (falling back to `name`), never infer an ID from the display label. Native role/model aliases are local selectors and must resolve to that exact upstream ID. Test two providers using the same label but different API IDs, explicit per-harness ID overrides, slash-containing IDs, repeated IDs and unsupported remapping. Model-ID conversion must not change endpoint or credentials.

## Directory ownership

This directory contains `adapter.py`, a 0.154.0 native capability fixture and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
