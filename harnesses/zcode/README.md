# ZCode CLI harness

**Selected harness; source-backed adapter candidate, pending native implementation and validation.**

This selection targets [Z.ai's official open-source ZCode](https://github.com/zai-org/ZCode), including its `zcode` terminal entry point and Agent runtime in `apps/zcode-cli/`.

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Selection and integration boundary |
| --- | --- |
| Proposed adapter ID | `zcode` |
| Native executable | `zcode`; official CLI/TUI distribution, also supporting Web mode |
| Provider command | Proposed `zcode-<alias>` after implementation and validation |
| Role selection | Proposed private provider file per role, with structured default model selection |
| Native provider configuration | `~/.zcode/v2/provider_config.json` by default |
| Managed file selection | Child-scoped `ZCODE_PERSONAL_PROVIDER_CONFIG_FILE` |
| Protocols in upstream source | Anthropic Messages, OpenAI Chat Completions and OpenAI Responses |
| Credentials | Literal `config.access.apiKey` in a private generated provider file |
| Personal state | Shared by default; changing the provider file alone does not isolate sessions |
| Verified releases | None; source revision checked, native runtime not smoke-tested |

Custom models are supported by the official source. A personal provider rule supplies its API protocol, base URL, API key and exact model IDs. The file also carries model rules and a default selection. See the spec for the versioned file shape and source references; older `provider.zai.options` examples belong to a legacy format.

This introduction remains documentation-only: no manifest, adapter, wrapper or native configuration change. `harness-sync plan --harness zcode` remains unsupported until a separately approved implementation passes its release gates.
