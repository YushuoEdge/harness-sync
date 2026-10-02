# OpenClaw adapter

**Implemented for OpenClaw 2026.9.7 / c074824.** Other releases fail closed.

Supports Anthropic Messages, OpenAI Chat, OpenAI Responses and Google GenAI.
Each provider/role has a stable private state directory, workspace and
`openclaw.json`. Native environment SecretRefs deliver API keys and headers;
credentials do not appear in generated profile files. No channels, OAuth,
plugins or personal agents are copied. Native state isolation is not a sandbox.

```sh
harness-sync plan --harness openclaw
harness-sync sync --harness openclaw --profiles-only
harness-sync run openclaw --provider team --role complex -- agent --local --agent main --message 'Explain this code'
```

The runner refreshes profiles before launch and pins `agent --model` to the exact
provider-local ID. Repeated IDs share one catalog entry and the first role's
native alias; conflicting metadata is rejected. Model IDs can contain slashes.
Reasoning effort and no-auth providers are rejected because their native mapping
has not been validated. Reasoning capability, context/output limits and text/image
input metadata are supported.

Foreground gateway use requires an explicit provider override:

```yaml
overrides:
  openclaw:
    options:
      gateway_port_base: 23000
```

The simple/daily/complex ports are base/base+1/base+2. Choose distinct port ranges
for different providers, including room for OpenClaw's auxiliary listeners.
Native bind conflicts fail normally; the adapter rejects `--force`. Managed
gateways use loopback binding and a role-specific HMAC token derived from the
API key, supplied through a separate child environment variable. API-key rotation
also rotates gateway authentication; restart an existing foreground gateway to
activate it. Sync never starts or stops a service.

```sh
harness-sync run openclaw --provider team --role daily -- gateway run
harness-sync run openclaw --provider team --role daily -- gateway health --json
```

Gateway service installation/removal/start/restart/stop commands and routing overrides
are rejected. Agent turns without `--local`, and remote TUI clients, require the
configured gateway port. Messaging integrations are not provisioned automatically.

## Authorized defaults

Default writes require the shared core's separate runtime authorization. They
merge only managed providers, aliases and the selected primary model, preserving
fallbacks, channels, gateway settings, personal agents and unrelated providers.
Defaults use literal credentials in a private mode-0600 config so the original
CLI can run without the managed environment. `${...}` in literal values is
rejected to prevent native interpolation from changing their meaning.

Config detection honors explicit paths, native state/profile overrides and the
legacy `.clawdbot` / `clawdbot.json` candidates. JSON5 comments and trailing commas
are preserved by the conservative concrete-syntax editor shared with OpenCode.
Unsupported syntax, `$include` configs, scalar parents, managed-name collisions
and edits to previously managed fields fail before writes. The adapter does not
edit native auth databases or derived per-agent `models.json`.

## Verification

Fixtures pin native version and agent help. Automated tests cover role/model
identity, protocol maps, defaults preservation, key rotation, obsolete catalog
removal, flags, ports, private permissions and profile-only default protection.
Native localhost checks verified all four protocols across three roles against
an error-response stub, plus native config validation and authenticated isolated
gateway health. These checks prove request routing, not successful inference.

```sh
uv run pytest harnesses/openclaw
uv run python harnesses/openclaw/tests/smoke_native.py --executable /opt/homebrew/bin/openclaw --gateway
```

See the [adapter spec](SPEC.md), [CLI reference](https://docs.openclaw.ai/cli),
[custom-provider documentation](https://docs.openclaw.ai/gateway/config-tools/custom-providers)
and [overall specification](../../SPEC.md).

## 2026-10-02 release validation

Updated the installed OpenClaw to **2026.9.7 / c074824** and its required Node runtime to
**24.16.0** (the previous 22.23.1 binary was preserved). Refreshed version and agent-help fixtures.
All four protocols and all roles passed localhost request routing, fake-key rotation and native
config validation. An isolated foreground gateway passed authenticated health checks without
changing its managed config. Unit tests passed. Native default/auth/channel files were untouched.
