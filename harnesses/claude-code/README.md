# Claude Code adapter

Implemented for **Claude Code 2.1.278**; other versions fail closed. Protocol: Anthropic Messages.

```sh
harness-sync plan --harness claude-code
harness-sync sync --harness claude-code
harness-sync run claude-code --provider <alias> --role complex -- -p "your prompt"
```

Ordinary sync creates three private settings overlays. Each pins the endpoint, literal API key,
Haiku/Sonnet/Opus tier mappings and active model. Managed launch loads fresh credentials and uses
`--settings`; sessions and personal state are shared. Profiles contain derived secrets (0600).
Native defaults remain untouched unless separately authorized. Authorized JSON merges preserve
unrelated fields and detect edits to owned fields. Authentication stores are never edited.

Custom headers, keyless providers and per-model reasoning effort are currently rejected.
Routing/config/cloud flags and custom agent definitions that can change routing are rejected.
An explicit `--model` may select another model within the managed provider. Organizational policy
remains authoritative; policy conflicts cannot be bypassed by this adapter.

Version/help fixtures and adapter tests cover roles, routing flags, key rotation and default
conflicts. A native localhost smoke test on 2026-10-01 confirmed `/v1/messages`, exact upstream ID
and the selected API key despite stale user settings/key helpers; original settings were unchanged.
No real credentials or paid inference were used. See [spec](SPEC.md).
