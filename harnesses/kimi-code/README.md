# Kimi Code adapter

Implemented for **Kimi Code 2.1.1** (`@moonshot-ai/kimi-code`), the supported successor to
Python `kimi-cli`. Other versions fail closed. Supports Anthropic Messages, OpenAI Chat,
OpenAI Responses and Google GenAI.

```sh
harness-sync sync --harness kimi-code
harness-sync run kimi-code --provider <alias> --role complex -- -p "your task"
```

Profiles render private TOML with explicit static provider catalogs and literal keys under a
stable isolated `KIMI_CODE_HOME`. Launch uses `--model` with a role alias; the successor has no
`--config-file` flag. Native user defaults, old Python sessions and OAuth are not migrated.
Routing environment variables, custom agent files and resume/continue overrides are rejected
or cleared. `context_window` is required; output limits and effort remain explicitly unsupported.
The optional `reserved_context_size` setting allows smaller context windows.

Authorized default writes preserve comments and unrelated provider/model entries using the
shared three-way merge. Normal profile-only sync leaves native defaults untouched.

On 2026-10-02 all four protocols and all roles passed localhost routing checks with exact
slash-containing IDs and fake keys. Native fixtures and unit tests cover home selection,
rotation, unsupported releases/flags, default preservation and idempotence. No paid inference
or personal configuration migration was used. See [spec](SPEC.md).
