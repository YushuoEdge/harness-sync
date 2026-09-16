# GitHub Copilot CLI adapter

**Native adapter pending; shared framework available.**

This is an additional candidate outside the currently approved eight-adapter v1 implementation set. Its implementation requires separate approval.

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Planned behavior |
| --- | --- |
| Adapter ID | `copilot` |
| Native executable | `copilot` |
| Provider command | `copilot-<alias>` |
| Role selection | `harness-sync run copilot --provider <alias> --role simple\|daily\|complex -- ...` |
| Provider configuration | Child-scoped `COPILOT_PROVIDER_*` environment variables |
| Default files | No provider/default writes in the initial adapter |
| Verified releases | None yet; capability and versioned native tests required |

## Proposed usage after implementation

```sh
harness-sync plan --harness copilot
harness-sync sync --harness copilot
harness-sync run copilot --provider <alias> --role daily -- ...
```

Each managed launch will refresh its selected provider configuration before starting GitHub Copilot CLI. The original `copilot` command, GitHub authentication, settings, sessions, custom agents, plugins and MCP configuration remain untouched. Provider endpoint, credential and model selection are passed only to the launched child process. The initial adapter will not support native default writes because the documented BYOK interface is environment-based rather than a persistent provider-profile format.

GitHub documents direct BYOK support for Anthropic and OpenAI Chat Completions-compatible endpoints. Azure OpenAI and optional wire-level controls require explicit adapter options and separate validation. Models must support streaming and tool calling. See the spec for protocol mappings, precedence hazards and release gates.

## Implementation boundary

This directory is documentation-only and is not advertised by the packaged registry. No adapter manifest, `adapter.py`, personal wrapper installation or native configuration change has been added. After this design is approved, implementation should follow the [adapter development guide](../../docs/adapter-development.md), add versioned fixtures and tests, and prove behavior against an installed release without using paid inference by default.
