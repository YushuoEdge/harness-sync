# OpenClaw adapter specification

Status: **Native design pending implementation; shared framework ready.** Adapter ID: `openclaw`. Native command: `openclaw`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

OpenClaw supports named state profiles and explicit `OPENCLAW_STATE_DIR` / `OPENCLAW_CONFIG_PATH`. [CLI reference](https://docs.openclaw.ai/cli). Custom catalogs use `models.providers` and protocol-specific `api` identifiers. [Custom providers](https://docs.openclaw.ai/gateway/config-tools/custom-providers).

## Adapter design

- Detect `openclaw`, version, explicit native state/config overrides and the usual `~/.openclaw/openclaw.json` candidate. Verify the actual path for the installed version before writes.
- Render native JSON/JSON5 config with `models.mode` preserving additive behavior, namespaced `models.providers`, endpoint, protocol, key reference and catalog. Map to verified `openai-completions`, `openai-responses`, `anthropic-messages` or `google-generative-ai` values.
- Map daily to `agents.defaults.model.primary` and define three model aliases using the installed schema. The runner's role selection chooses a role-specific config; do not configure simple/daily/complex as a failure fallback chain.
- Use isolated stable `OPENCLAW_STATE_DIR` per provider and explicit `OPENCLAW_CONFIG_PATH` for each role. Avoid conflicting named-profile flags; wrappers preserve subcommand dispatch. Separate roles under the same provider share state but must not concurrently control one gateway with conflicting configurations.
- Use verified native secret references when supported; otherwise resolve `apiKey` into a private config as an explicit adapter capability. State/diagnostics record which strategy is used. OAuth and derived per-agent catalogs are not edited directly.
- A provider profile has separate sessions, gateway configuration and credentials. It does not copy channels, plugins, bot identities, agents or scheduled work from the default instance.

## Authorized default writes

Merge only managed provider entries, aliases and selected primary model into native config. Preserve channel settings, gateway auth/ports, agents, policies, existing providers and fallback order. Do not rewrite generated per-agent `models.json` or native authentication databases; the harness owns their derivation.

## Verification and release gates

Verify config schema, key-reference syntax, alias/default paths and role activation against pinned native fixtures. Test JSON5 preservation, duplicate models, config/state precedence, credential isolation and unchanged native default settings. Concurrent gateway profiles require explicit distinct ports and matching client config; report conflicts and never start/stop services as a sync side effect. Updating files cannot guarantee that a connected gateway changes model immediately. The wrapper runs the CLI; it does not automatically provision a functioning gateway or messaging integration.

## Command-triggered sync and model identity

Every generated provider command uses the common pre-launch sync contract: refresh this harness/provider, apply native defaults only when independently authorized, then launch. There is no background watcher or harness enablement flag. A bare original executable remains unchanged and does not invoke the sync tool.

Consume the core's resolved provider-local model `id` (falling back to `name`), never infer an ID from the display label. Native role/model aliases are local selectors and must resolve to that exact upstream ID. Test two providers using the same label but different API IDs, explicit per-harness ID overrides, slash-containing IDs, repeated IDs and unsupported remapping. Model-ID conversion must not change endpoint or credentials.

## Planned directory ownership

When implemented, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
