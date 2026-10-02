# OpenCode adapter

Implemented for **OpenCode 1.17.13**. Four verified bundled SDK mappings: Anthropic Messages,
OpenAI Chat, OpenAI Responses and Google Generative AI. Unknown versions fail closed.

```sh
harness-sync sync --harness opencode
harness-sync run opencode --provider <alias> --role complex -- run "your task"
```

Three secret-free profiles describe provider/model catalogs and the selected role. Launch passes
an inline overlay, explicit native model selector and fresh namespaced credentials. Endpoint/key
settings are pinned at both provider and model level. Only the selected provider is enabled; native
OAuth/auth stores and sessions remain shared. `small_model` points to simple for auxiliary work.
Managed policy retains higher precedence; conflicting policy can prevent a launch.

Managed launch uses `--pure` to disable external plugins that can replace routing. Extra
model/agent/attach/config flags and remote attach/GitHub/PR dispatch are rejected. Custom headers
support environment secret references; static config substitution directives are rejected.
Per-model reasoning effort is rejected pending a protocol-specific option contract.

Authorized global merges preserve unrelated providers/settings and supported JSONC comments.
Duplicate keys and malformed configs fail. The concrete-syntax editor supports line comments and
trailing commas; block comments, unsupported escapes or other unsupported syntax are refused
without rewriting the file. Native project settings can still override bare-command defaults.

Version/help fixtures and tests cover roles, protocols, conflict detection and preservation.
On 2026-10-01 localhost checks verified all four protocols/roles with fake keys, including stale
project provider/model endpoints, keys, SDK mappings and agent model selection. No paid inference
or personal-config changes were used. See [spec](SPEC.md) and
[pinned native provider source](https://github.com/anomalyco/opencode/blob/v1.17.13/packages/opencode/src/provider/provider.ts).
