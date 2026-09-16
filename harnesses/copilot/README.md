# GitHub Copilot CLI adapter

**Revised registry-based design; native adapter pending implementation and separate approval.**

This is an additional candidate outside the approved eight-adapter v1 implementation set. Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md). This adapter targets Copilot CLI; VS Code Copilot Chat configuration is outside its scope.

| Item | Planned behavior |
| --- | --- |
| Adapter ID / native executable | `copilot` / `copilot` |
| Provider command | `copilot-<alias>`; daily role by default |
| Role selection | `harness-sync run copilot --provider <alias> --role simple\|daily\|complex -- ...` |
| Managed configuration | One private `providers.json` per provider and role under the tool's generated profile directory |
| Profile selection | Child-scoped `COPILOT_PROVIDERS_CONFIG` plus verified `COPILOT_MODEL` selector |
| Credentials | Verified environment reference if supported; otherwise private derived registry credentials |
| Native default files | No writes in the initial adapter; default-write requests are rejected |
| Shared state | Existing Copilot home, login, sessions, agents, skills, plugins, permissions and MCP |
| Verified releases | None; 1.0.85 is an observed release candidate, not validated support |

## Proposed usage after implementation

```sh
harness-sync plan --harness copilot
harness-sync sync --harness copilot
copilot-<alias>
harness-sync run copilot --provider <alias> --role complex -- ...
```

Each managed launch refreshes its provider registries before selecting a role. It selects an absolute registry path in the child environment, clears conflicting legacy provider controls and pins a native model selector whose wire ID is the canonical upstream model ID. The original `copilot` command remains outside the synchronizer. No global registry swap, substitute Copilot home or shell startup-file edit is proposed.

## Native interface and unresolved details

GitHub's [configuration reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference#providersjson) and [command reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference) document a persistent BYOK registry at `~/.copilot/providers.json`, a `COPILOT_PROVIDERS_CONFIG` path override, and registry precedence over legacy `COPILOT_PROVIDER_*` variables. The [BYOK guide](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-byok-models) still describes the older environment workflow. Sources were reviewed on 2026-09-16.

The revised design replaces the earlier environment-only proposal. Exact registry entry fields, native selector syntax, credential references and missing/invalid-registry behavior remain release gates. Do not copy VS Code `chatLanguageModels.json` fields into a CLI registry or assume its secret-reference syntax applies. Anthropic and OpenAI Chat Completions are candidates for validation; Responses is conditional on exact native wire evidence, Azure needs explicit typed overrides, and Google GenAI has no direct mapping proposed.

The initial adapter will not modify the user's global `providers.json` or `settings.json`. A future global-default feature requires a separate merge, credential and model-selection design. Models need streaming and tool calling; the recommended context window is at least 128k. See the spec for precedence restrictions, internal/subagent routing checks and default policy.

## Implementation boundary

This directory remains documentation-only and is not advertised by the packaged registry. It has no manifest, `adapter.py`, fixtures or tests. No `copilot` executable was found on the current PATH, and no installed release has been validated. Installing/upgrading Copilot is not required to review this design and must never happen during adapter detection. Implementation requires separate approval, versioned native evidence and local stub tests without paid inference by default. Follow the [adapter development guide](../../docs/adapter-development.md).
