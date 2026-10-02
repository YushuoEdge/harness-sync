# OpenClaw adapter specification

Status: **Implemented for OpenClaw 2026.6.11 / e085fa1.** Adapter ID: `openclaw`. Native command: `openclaw`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); The implementation was additionally checked against the installed pinned release on 2026-10-02. The boundary below supersedes earlier proposals.

## Native interface and evidence

OpenClaw supports named state profiles and explicit `OPENCLAW_STATE_DIR` / `OPENCLAW_CONFIG_PATH`. [CLI reference](https://docs.openclaw.ai/cli). Custom catalogs use `models.providers` and protocol-specific `api` identifiers. [Custom providers](https://docs.openclaw.ai/gateway/config-tools/custom-providers).

## Adapter design

- Detect `openclaw`, version, explicit native state/config overrides and the usual `~/.openclaw/openclaw.json` candidate. Verify the actual path for the installed version before writes.
- Render native JSON/JSON5 config with `models.mode` preserving additive behavior, namespaced `models.providers`, endpoint, protocol, key reference and catalog. Map to verified `openai-completions`, `openai-responses`, `anthropic-messages` or `google-generative-ai` values.
- Map daily to `agents.defaults.model.primary` and define three model aliases using the installed schema. The runner's role selection chooses a role-specific config; do not configure simple/daily/complex as a failure fallback chain.
- Use an isolated stable `OPENCLAW_STATE_DIR` and explicit config path per provider/role. Roles have separate state and workspaces to avoid concurrent gateway configuration conflicts. Wrappers preserve supported subcommand dispatch.
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

## Implemented boundary

Native protocol names, environment SecretRefs, model catalog/alias paths and the
agent model override were verified on 2026.6.11 / e085fa1. Profiles are secret-free;
explicitly authorized defaults contain mode-0600 literal credentials for bare
CLI use. Default merges preserve fallback order, gateway/channels/auth settings
and unrelated entries. Includes and unsupported concrete JSON5 syntax fail closed.
The parser/editor is shared with the OpenCode adapter, without native I/O.

Optional provider `options.gateway_port_base` assigns distinct role ports at
base/base+1/base+2. It also configures loopback/token auth using a domain-separated
HMAC-SHA256 credential derived from the provider key and role; launch supplies it
through `HARNESS_SYNC_OPENCLAW_GATEWAY_TOKEN`. Choose distinct ranges between
providers; auxiliary listeners are native-owned. No gateway starts during sync.
Service-control and routing overrides are rejected. Local embedded agent turns
need no gateway port. Existing gateways must restart after credential/config
changes; messaging integration setup remains outside the adapter.

No-auth and reasoning-effort mappings remain unsupported. Catalog metadata and
repeated exact IDs are supported; a repeated ID has one native alias (first role).
Native stub checks cover all four protocols across all roles, native config
validation and authenticated foreground gateway health, without paid inference.
The repeatable smoke script uses temporary state and fake credentials.
