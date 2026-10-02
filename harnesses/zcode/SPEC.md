# ZCode CLI adapter specification

Status: **Implemented for distribution 3.14.3 / Agent CLI 0.16.9.** Adapter ID and command: `zcode`.
Implementation was requested on 2026-10-02; native default writes remain unsupported.
The [overall specification](../../SPEC.md) governs ownership, transactions and secrets.

## Native source and installed distribution

This targets the official open-source `zai-org/ZCode`, revision
`29628c9acdb81b703bbd4080c207a0e7ce5e276e`. Its unified entry starts the TUI, forwards Agent options,
and also supplies Web mode. Detection requires both distribution version and Agent help identity,
using a temporary data root and clearing inherited provider-file settings. Help/version fixtures
record the installed source build. [Upstream build instructions](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/README.en.md).

The locked source build needed explicit transpilation of source-only `@zcode/shared` for the
packager's `dist` exports. `scripts/prepare_shared_dist.mjs` records the workaround. After the
ordinary `pnpm build:zcode --base-url <packaging-url>` build, run that script against the checkout,
then `node scripts/build-zcode.mjs --skip-build --base-url <packaging-url>` and extract the generated
archive. The URL is used for generated installer metadata; no hosted updater was deployed.
See README for this machine's installed path, Node requirement and tarball hash.

## Private schema and provider selection

The personal provider file uses `schemaVersion: 1` with:

| Field | Adapter behavior |
| --- | --- |
| `config.providerConfigRules.providerRules` | One enabled `hs-<name>` provider |
| Rule `config.group` | `standard-personal` |
| Rule `config.access` | `type: api-key`, private literal `apiKey` |
| Rule `config.api` | Explicit `type`, `baseUrl`, optional literal/secret headers |
| Rule `config.personalModelIds` | Exact provider-local upstream IDs |
| `config.modelConfigRules.providerModelRules` | Complete capabilities and option-map rules per model |
| `config.modelConfigRules.manualProviderModelRules` | Empty |
| `config.defaultModelSelection` | Structured provider/model ID and disabled reasoning |

The [file codec](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/provider-node/src/provider-config-file-codec.ts),
[rule schema](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/provider/src/config/rule-data-schema.ts)
and [capability schema](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/shared/src/model-config.ts)
define the versioned format. Generated JSON rejects duplicate keys and unknown schema versions.
The common ownership/transaction checks reject manual edits before replacement.

| Canonical protocol | Native API type |
| --- | --- |
| `anthropic` | `anthropic-messages` |
| `openai-chat` | `openai-chat-completions` |
| `openai-responses` | `openai-responses` |

Each model must specify positive context/output capacities. Text, optional images and tool calling
are declared explicitly. Output ceilings map to native API token parameters. Reasoning `true` or
any effort request is rejected because the canonical schema does not provide the necessary native
model-specific reasoning expression. Repeated exact IDs are deduplicated only with equal metadata.
Use `provider.endpoint_for("zcode")`, `protocol_for("zcode")` and `model.upstream_id("zcode")`;
never parse a display label or composite picker string to guess an ID.

## Isolation, fallback and launch grammar

Each provider/role owns `provider_config.json` and `builtin.json` in its managed runtime root.
The latter is a valid empty schema-version-1 built-in catalog. Files use mode 0600 and scoped
secrets. Sync stages both with shared backups, redaction, rotation and rollback support.

Child environment selects `ZCODE_PERSONAL_PROVIDER_CONFIG_FILE`, `ZCODE_BUILTIN_PROVIDER_CONFIG_FILE`
and `ZCODE_DATA_BASE_DIR`. OS `HOME` is preserved; ZCode's data and accounts live in the selected
root. No real account stores, sessions, plugin registries or credentials are copied. Clear inherited
provider/data variables, native gateway keys and `ZCODE_BUILTIN_PROVIDER_BUNDLED_CONFIG_FILE`.
The explicit personal/built-in pair skips bundled-provider preparation, and absence of the bundled
refresh source disables its remote synchronizer. [Provider preparation](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/apps/zcode-cli/packages/cli/src/provider-runtime-env.ts)
and [registry runtime](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/apps/zcode-cli/packages/bootstrap/src/app/process-provider-registry-runtime.ts).

The fresh-launch default is the selected role. The verified Agent parser has no `--model` startup
flag. Reject model overrides, resume/continue (including short forms), explicit goals/targets,
dynamic workflows, memory benchmark, Web/stdio/server surfaces and login/plugin administration.
Use the original `zcode` for those operations. Project instructions and native permission settings
are preserved; the adapter does not change permission mode.

Fresh launches are verified for primary requests. Interactive model/session commands, completed
inference, subagents, plugins, desktop/Web and long-lived sessions are outside this verification.
The catalog contains only the selected canonical provider; manually choosing another role model
inside the TUI changes the running session and does not change the next launch's default.

## Default writes and verification

`default.write: true` and `--write-defaults` fail explicitly. Managed `defaultModelSelection` applies
only inside the managed profile. Normal synchronization does not write shared `~/.zcode` files.

On 2026-10-02 native localhost checks proved all three protocols and roles, two providers with
shared display labels, slash/dollar IDs, per-harness ID overrides, exact credentials, secret headers,
rotation and clearing stale inherited provider sources. The opt-in `tests/smoke_native.py` reproduces
those checks with fake keys and HTTP errors. Unit/engine tests prove version gates, unsupported
metadata, private files, idempotence, default protection, identity separation and rollback.
No real credentials, paid inference, user default writes or account migration were used.
