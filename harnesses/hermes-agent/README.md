# Hermes Agent adapter

Implemented for **Hermes v0.21.0, upstream 245e4800**. Other releases/revisions fail closed.
Supports Chat Completions, OpenAI Responses and Anthropic Messages; Google is not enabled.

```sh
harness-sync sync --harness hermes-agent
harness-sync run hermes-agent --provider <alias> --role complex -- chat -q "your task"
```

Profiles use persistent isolated homes per provider/role. Each contains native `config.yaml` and
private `.env`; sessions, memories, skills and auth are not copied. Named provider entries bind a
namespaced key variable, explicit transport, endpoint and model metadata. All role model IDs are
preserved exactly. The runner places provider/model flags correctly for chat or global options;
administrative commands retain their original grammar and run in the selected profile home.

Native dotenv loads can replace shell values, so both the file and child environment carry the
current selected key. Credentials containing `${` are rejected rather than interpolated. Quotes,
backslashes, dollar signs and hashes otherwise roundtrip through the native dotenv parser.
Additional model/provider/profile or user-config-bypass flags are rejected. Model output budgets,
context limits, reasoning capabilities and supported effort selections are mapped explicitly.

Authorized default writes merge owned YAML/provider/model fields and namespaced dotenv entries,
preserving comments, bot tokens, unrelated providers and native auth stores. No gateway is started
or restarted by synchronization. Active sessions may retain their selection until the next launch.

Version/help fixtures and tests cover role selection, native grammar, dotenv escaping, key rotation,
default protection and conflicts. On 2026-10-01 localhost checks verified all three transports and
roles with exact model IDs and fake keys, without paid inference or personal-config changes.
See [spec](SPEC.md) and [pinned native provider source](https://github.com/NousResearch/hermes-agent/blob/245e48008fa814b3251f50755eb656bd9fb86cb1/hermes_cli/runtime_provider_custom.py).
