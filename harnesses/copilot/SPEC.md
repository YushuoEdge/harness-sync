# GitHub Copilot CLI adapter specification

Status: **Revised registry-based design; native adapter pending implementation and separate approval.** Proposed adapter ID: `copilot`. Native command: `copilot`.

This is an additional candidate outside the approved eight-adapter v1 implementation set. The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. This revision authorizes documentation work only; there is no manifest, adapter code or packaged registry entry. VS Code Copilot Chat and its `chatLanguageModels.json` are a separate configuration surface and are outside this CLI adapter's scope.

## Native interface and evidence

Official sources were checked on 2026-09-16 (America/New_York):

| Source | Confirmed documentation | Remaining verification |
| --- | --- | --- |
| [CLI configuration directory](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference#providersjson) | `~/.copilot/providers.json` is a BYOK registry with top-level `providers` and `models` keys. `COPILOT_PROVIDERS_CONFIG` selects another file. A registry declaring any provider or model takes precedence over legacy provider environment variables. | Exact entry schema, credential references, selector grammar, duplicate handling and startup failure behavior in a pinned release |
| [CLI command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference) | Documents the registry path variable and legacy precedence. Also documents `COPILOT_PROVIDER_API_KEY_COMMAND`, which outranks the legacy API-key variable. | All inherited routing and credential controls, native overrides and registry-specific authentication behavior |
| [BYOK guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models) | Still describes environment-based BYOK for `openai`, `azure` and `anthropic`; models require streaming and tool calling. A context window of at least 128k is recommended. | Registry equivalents of those options; wire protocol support cannot be inferred from the environment examples |
| [Latest release observed: 1.0.85](https://github.com/github/copilot-cli/releases/tag/v1.0.85) | Published 2026-09-16 | Candidate for testing only; neither registry schema nor adapter compatibility is validated by the release number |

The references and BYOK guide are not yet aligned. This design uses the registry interface documented by the references, but does not invent native JSON fields or assume that an environment option has a registry equivalent. No runnable native registry example is supplied until the entry schema has been captured from a pinned release's official help, schema or package resources.

No `copilot` executable was found on the current PATH during this review. There is no locally verified release or minimum supported version. A future implementation may install or upgrade an explicitly authorized test installation, but adapter detection itself must never install or update software.

`~/.copilot/settings.json` contains global CLI preferences, including model selection; it is not the BYOK registry. Repository/local settings and native flags can also affect model selection. `COPILOT_HOME` changes the entire configuration/state directory. Keep that existing directory shared during managed launches. [CLI configuration reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference).

BYOK can run without GitHub authentication, while GitHub-hosted features may require it. Offline mode is an explicit choice and does not prevent traffic to a remote model provider. [Authentication](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up-copilot-cli/authenticate-copilot-cli) and [BYOK/offline guidance](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models#running-in-offline-mode).

## Managed provider registries

The proposed strategy is a separate registry for each provider and role, selected only for the launched child process. Never temporarily swap or edit the user's global registry to route a managed launch.

```text
<context.paths.profile("copilot", provider.command_alias)>/
  simple/providers.json
  daily/providers.json
  complex/providers.json
```

With default paths, this is `~/.config/harness-sync/generated/profiles/copilot/<alias>/<role>/providers.json`. These are proposed managed paths, not Copilot's default files. Each registry contains only the selected provider and the selected role's model. It does not import the user's global registry or unrelated provider credentials. Native built-in models may still exist; the selected model must resolve to the managed entry.

- `profiles(provider, context)` returns three `scope="profile"` artifacts under the managed root, mode `0600`, with stable ownership such as `copilot/<provider-name>/<role>`. The common transaction engine stages, verifies and commits them before launch.
- Use deterministic native provider/model selectors with reserved `hs-` identities, if the verified registry grammar supports them. A role selector is distinct from the upstream API model ID. The exact native selector and entry field names must come from release evidence.
- Resolve upstream identity through `model.upstream_id("copilot")`; preserve case, punctuation, slashes and dated IDs. Repeated upstream IDs across roles are valid. Registry selectors must not conflate models from different providers or replace the wire ID with a display label.
- Prefer a verified registry credential reference to the provider's namespaced `HS_...` child environment. Do not assume `${ENV}`, `${input:...}`, or VS Code secret-reference syntax works in Copilot CLI.
- If the pinned registry schema requires literal credentials, deferred rendering may place the selected provider's secret in the private managed registry. Plans, logs, argv and representations remain secret-free; staged files, backups and rollback copies follow the core's private-file rules. The README must state which credential method the supported release uses.
- Keyless local endpoints remain keyless. API-key versus bearer-token mode is a typed adapter option selecting the interpretation of the existing canonical secret reference. Do not accept a literal key or an arbitrary credential command in canonical options.
- Map canonical headers, metadata and typed options only when their registry meaning is verified. Unsupported supplied fields must fail explicitly rather than being dropped. Preserve base URL paths and append only release-verified API suffixes.
- Reject a registry that cannot encode the full endpoint/protocol/credential/model tuple. Unsupported registry schemas are `unsupported-version`; never fall back silently to legacy environment BYOK.

The top-level `providers` and `models` keys are documented, but their entry shapes are not specified in the reviewed references. Registry field mapping, auth representation and selector syntax are blocking release gates, not details that an implementer may guess.

## Protocol and option design

| Canonical protocol | Proposed mapping | Enablement gate |
| --- | --- | --- |
| `anthropic` | Native Anthropic provider and Messages requests | Registry type and wire behavior proved locally |
| `openai-chat` | Native OpenAI-compatible provider and Chat Completions requests | Registry type, endpoint path and wire behavior proved locally |
| `openai-responses` | Conditional candidate; no enabled mapping yet | Exact registry wire API value and Responses behavior proved for a pinned release |
| `google-genai` | No direct mapping proposed | Requires separate official interface evidence and revised design |

Azure requires an explicit Copilot provider override with typed options for native provider type, API version, capability model ID and wire deployment ID. Never infer Azure from a hostname. Native capability identity, registry selector and provider-facing wire ID are separate concepts; prove which fields determine each. Reject Azure fields on other provider types and conflicting wire options.

Harness/provider/model native options stay in adapter-owned Pydantic schemas under their existing `options` objects. Do not add Copilot field names to the shared schema. Context and output limits must reflect supplied canonical metadata; never manufacture model capacity. Warn below the documented 128k recommendation rather than treating a recommendation as a mandatory API limit.

## Launch and precedence boundary

Every managed provider command performs common pre-launch sync, then `launch()` selects the role registry through an absolute child-scoped `COPILOT_PROVIDERS_CONFIG` and sets `COPILOT_MODEL` to the verified managed selector. `daily` is the wrapper default; other roles use the core's explicit role selection.

```sh
# Proposed usage after adapter implementation and approval:
harness-sync plan --harness copilot
harness-sync sync --harness copilot
copilot-<alias>
harness-sync run copilot --provider <alias> --role complex -- ...
```

- Replace inherited `COPILOT_PROVIDERS_CONFIG` and `COPILOT_MODEL`. Remove adapter-owned legacy `COPILOT_PROVIDER_*` routing/authentication controls, including API-key commands, bearer tokens, custom headers and wire/model/token overrides, before applying the selected registry. Capture the exact controls in versioned fixtures. Do not execute inherited credential commands during probes or managed launches.
- Retain the user's existing `COPILOT_HOME`, GitHub authentication and normal sessions, plugins, skills, custom agents, permissions and MCP state. Never set OS `HOME` or create a replacement Copilot state directory merely to select a provider.
- Reject `--model`, initially reject `--agent`, and reject config-directory/provider-registry overrides that can escape the selected tuple. Recognize split and equals forms and native subcommand grammar. Policy and project settings must not silently reroute the managed model.
- Prove custom-agent and subagent model precedence, built-in utility/compaction model behavior and resumed-session routing. If a mode can bypass the selected tuple and cannot be constrained through an official interface, reject it and document the limitation before advertising support. Do not promise that all internal requests use the selected model without request-level evidence.
- A missing, malformed, empty or unresolvable managed registry must abort before any model request. Verify Copilot's native behavior and validate artifacts offline; a fallback to GitHub-hosted models or the user's global registry is unacceptable.
- Do not enable `COPILOT_OFFLINE` implicitly. An explicit typed harness option may request it; explain that a remote configured provider still receives network traffic and some GitHub features become unavailable.
- Registries take effect on a fresh launch. Key rotation refreshes managed artifacts and launch credentials; no live-session reload promise or background watcher is provided. The original bare `copilot` command remains outside the synchronizer.

## Default configuration policy

The initial adapter does not write `~/.copilot/providers.json`, `~/.copilot/settings.json`, repository/local Copilot settings or shell startup files. `defaults()` rejects `default.write: true` or `--write-defaults` with an explicit unsupported diagnostic. An inherited `COPILOT_PROVIDERS_CONFIG` path is also a native user default, never a managed write destination.

This restriction is a deliberate initial scope boundary, not a claim that Copilot lacks a persistent provider format. A future global-default feature needs separate design/approval for ownership of native provider/model entries, collision handling, credential delivery to bare launches, selector precedence, format-preserving merges, atomic registry/selection updates and rollback. Approval to edit `settings.json` alone does not activate the complete BYOK tuple.

## Verification and release gates

1. Pin exact supported CLI versions/capabilities. Capture sanitized `--version`, `--help`, `help providers`, `help config`, native registry schema/examples and selectors. Probe in a temporary native home if help has write side effects; disable update/login behavior with release-verified controls. Finding a binary or observing a latest release is insufficient.
2. Capture registry credential handling and API-key/bearer/keyless modes. Test environment references if supported, otherwise private literal serialization and rollback copies. Check that no credential command is executed, no key appears in argv/plans/logs, and only the selected provider's credentials are rendered/delivered.
3. Use local stubs with dummy keys to prove exact endpoint paths, protocol, authentication, upstream ID, streaming and tool-call exchange for all enabled protocols and roles. No paid inference is required. Test same labels with different IDs, slash-containing IDs, repeated IDs and explicit wire remapping.
4. Prove a managed registry outranks conflicting global registries and legacy variables. Test inherited path variables, API-key commands, headers, OAuth, user/project/local settings, policy and native flags. Verify unresolvable selectors and missing/invalid/empty registries cannot cause hosted or global fallback.
5. Test two concurrent providers and roles without global-file swapping, provider switching, key rotation, malformed endpoints, missing IDs, unsupported metadata, absent streaming/tool calling and inconsistent token limits. Model selection must never change endpoint or credentials independently.
6. Exercise the real shared planner/transaction/launcher with temporary paths. Verify offline artifact schema validation, private permissions, symlink rejection, manual-edit conflicts, rollback, wrapper collisions and rejection of overrides before sync commits.
7. Inspect fresh, resumed, custom-agent, subagent and internal utility/compaction behavior. Reject unverified modes that can defeat the tuple. Confirm normal sync does not change native user defaults, auth or existing sessions/plugins/MCP state. Distinguish ordinary CLI session writes during execution from adapter writes.
8. Keep the harness unregistered until the above gates pass. After separate implementation approval, add `adapter.json`, `adapter.py`, versioned fixtures and tests within this directory, following the [adapter development guide](../../docs/adapter-development.md). Shared I/O, wrappers, transactions and secrets remain in the core.
