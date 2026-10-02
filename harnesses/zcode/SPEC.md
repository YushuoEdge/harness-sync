# ZCode CLI adapter specification

Status: **Selected harness; source-backed adapter candidate, pending implementation and native validation.** Proposed adapter ID: `zcode`. Native command: `zcode`.

Selection targets the official open-source `zai-org/ZCode` repository outside the original eight-adapter v1 implementation set. It does not authorize native implementation or default writes. Source revision `29628c9acdb81b703bbd4080c207a0e7ce5e276e` was reviewed on 2026-10-01 (America/New_York); no installed release was validated and no manifest is included.

## Official CLI and provider configuration

The official repository includes desktop, Web and terminal applications. The unified `zcode` entry point starts the TUI by default, supports `--web`, and forwards other options to the Agent CLI. Its standalone source entry is under `apps/zcode-cli/packages/cli/`. [Upstream README](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/README.en.md).

The current CLI locates personal provider configuration at `~/.zcode/v2/provider_config.json`. `ZCODE_DATA_BASE_DIR` changes the application data base, and `ZCODE_PERSONAL_PROVIDER_CONFIG_FILE` selects a separate personal provider file. Built-in configuration is separately selected by `ZCODE_BUILTIN_PROVIDER_CONFIG_FILE`; the preparation layer normally resolves it from the distribution. [CLI provider environment](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/apps/zcode-cli/packages/cli/src/provider-runtime-env.ts) and [runtime path constants](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/provider-node/src/runtime-paths.ts).

The file is a versioned JSON document, not the older flat `provider`/`model` config:

| Native field | Purpose |
| --- | --- |
| `schemaVersion` | Currently `1` |
| `config.providerConfigRules.providerRules` | Personal provider rule array |
| Rule `providerId`, `providerName`, `enabled` | Local identity, display label and availability |
| Rule `config.group` | `standard-personal` for an independent custom provider |
| Rule `config.access` | `{ "type": "api-key", "apiKey": "<private literal>" }` |
| Rule `config.api` | Protocol `type`, `baseUrl` and optional `headers` |
| Rule `config.personalModelIds` | Exact upstream model IDs for this provider |
| `config.modelConfigRules` | `providerModelRules` and `manualProviderModelRules` arrays |
| `config.defaultModelSelection` | Structured `providerId`, `modelId`, optional `options.reasoningLevel` |

These fields are defined by the [file codec](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/provider-node/src/provider-config-file-codec.ts), [provider rule schema](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/provider/src/config/rule-data-schema.ts), [provider data schema](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/provider/src/config/provider-data-schema.ts) and [model selection schema](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/shared/src/model-selection.ts). Model availability additionally depends on resolved capabilities and supported reasoning levels; listing an arbitrary model ID alone does not prove it is runnable. Capture the installed release's smart/manual metadata behavior before rendering models.

## Protocol mappings and selection

| Canonical protocol | Native `config.api.type` | Status |
| --- | --- | --- |
| `anthropic` | `anthropic-messages` | Source-backed candidate |
| `openai-chat` | `openai-chat-completions` | Source-backed candidate |
| `openai-responses` | `openai-responses` | Source-backed candidate |
| `google-genai` | None in the reviewed enum | No direct mapping |

The native execution layer dispatches all three listed formats to their corresponding SDK adapters. [Model execution](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/apps/zcode-cli/packages/adapters/src/model/model-execution.ts). This proves an implementation path exists in source, not compatibility with an installed binary or every gateway.

The TUI supports `/model <provider/model>` and resolves exact catalog entries before parsing display syntax. The CLI parser supports `--prompt`, resume/continue and other modes, but does not define a `--model` startup flag at this revision. Prefer the structured default selection in the managed provider file. [Model command](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/apps/zcode-cli/packages/cli/src/command-center/handlers/model.ts) and [CLI arguments](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/apps/zcode-cli/packages/cli/src/arguments.ts).

## Proposed managed profiles and launches

- Generate one private `provider_config.json` per provider and role under the managed profile root. Include only that provider's secret and model catalog, explicit model rules, and the selected role's structured default. `zcode-<alias>` would select daily.
- Launch the verified original executable with child-scoped `ZCODE_PERSONAL_PROVIDER_CONFIG_FILE`. Preserve OS `HOME` and native session/plugin/settings locations. Provider-file separation alone means personal state remains shared; do not claim account or session isolation.
- Render scoped secrets as native literals in mode-0600 files. Environment interpolation of `access.apiKey` has not been established; do not substitute an environment variable name as if it were the credential. Apply the shared staging, backup and redaction rules to every generated secret copy.
- Consume `provider.endpoint_for("zcode")`, protocol and `model.upstream_id("zcode")`. Preserve IDs as structured fields, including slashes and dollar signs, rather than round-tripping through picker strings.
- Verify provider-file normalization, UI edits, inherited built-in/account configuration, legacy import and invalid-file recovery. The native repository can normalize files and recover with an empty overlay in memory, so prevalidation and failure-without-fallback tests are required. [Personal repository](https://github.com/zai-org/ZCode/blob/29628c9acdb81b703bbd4080c207a0e7ce5e276e/packages/provider-node/src/personal-provider-config-repository.ts).
- Verify resume/continue, explicit task targets, project settings, subagent profiles and interactive model changes. Reject modes that can escape the canonical tuple until native precedence is proven. Do not weaken enforced policy.
- Preserve account authentication stores; canonical API-key provider profiles must not depend on copying or replacing subscription-account tokens.

## Default writes

Initially reject native default-write requests. Managed files may have their own `defaultModelSelection`; this selects a role only within the managed provider profile. It does not authorize changes to the user's shared `~/.zcode/v2/provider_config.json`. Native default support needs separately specified owned-field merges and preservation tests.

## Release gates

1. Pin a supported CLI distribution and record sanitized help/version fixtures, versioned provider files and required model metadata. Source inspection alone does not pass a native smoke gate.
2. Prove all three claimed protocols against local stub endpoints: exact upstream ID, base URL, credentials and headers; test custom/slash/dollar IDs and two providers sharing a display label.
3. Prove role/default selection, metadata admission, reasoning levels, key rotation, invalid-file recovery and no built-in/account fallback.
4. Prove concurrent providers, shared-state preservation, interactive/native edits, resumed tasks and subagent routing. Verify idempotence, private credentials and rollback without normal-sync default writes.
5. Obtain implementation approval, then add the manifest, native adapter and tests. The original eight-adapter v1 set remains unchanged.
