# Kimi Code adapter

Implemented for the installed **Kimi CLI 1.49.0 legacy format**. It uses `KIMI_SHARE_DIR`,
`~/.kimi/config.toml` and verified `--config-file` support. Newer `KIMI_CODE_HOME` releases are
not claimed; unknown versions fail closed and no home/config migration is performed.

Supports Anthropic, OpenAI Chat (`openai_legacy`), Responses (`openai_responses`) and Google
(`google_genai`) for this release. These identifiers differ from newer Kimi documentation.

```sh
harness-sync sync --harness kimi-code
harness-sync run kimi-code --provider <alias> --role complex -- --prompt "your task"
```

Every model requires `context_window`. It must exceed Kimi's native 50,000-token reserved budget,
or configure `harnesses.kimi-code.options.reserved_context_size` explicitly (minimum 1,000).
Output-token limits and reasoning effort are rejected because this release cannot map them per
model. Reasoning/image capabilities are mapped where supplied.

Profiles contain a private literal key and three role aliases in a persistent isolated home.
The runner supplies the explicit config and role alias and clears conflicting environment
credentials/endpoints/model overrides. Additional config/model/custom-agent flags are rejected.
Personal sessions, skills, plugins and OAuth are not copied. Authorized default writes preserve
TOML comments, unrelated providers/models and native OAuth entries; literal keys rotate on sync.

Version/help fixtures and adapter tests cover schema, roles, budgets, key rotation, preservation
and conflicts. On 2026-10-01 native localhost checks verified all four protocols and roles with
exact upstream IDs and fake keys. No paid inference or personal-config changes were used.
See [spec](SPEC.md) and [pinned native configuration source](https://github.com/MoonshotAI/kimi-cli/blob/1.49.0/src/kimi_cli/config.py).
