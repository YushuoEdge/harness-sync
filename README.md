# Harness Sync Config

Manage providers, three model roles, and API keys in one place, then synchronize them across coding harnesses.

**Status: specification draft. No application code has been implemented. All commands below describe the proposed interface.**

## Review first

1. [Overall specification](SPEC.md): configuration schema, CLI, secrets, automatic sync, default protection, architecture and acceptance criteria.
2. [Compatibility matrix](docs/compatibility.md): native configuration strategies and unresolved version checks.
3. Adapter specifications below: exact responsibilities and release gates.

| Harness | README | Specification |
| --- | --- | --- |
| Claude Code | [Overview](harnesses/claude-code/README.md) | [Spec](harnesses/claude-code/SPEC.md) |
| Codex | [Overview](harnesses/codex/README.md) | [Spec](harnesses/codex/SPEC.md) |
| Pi | [Overview](harnesses/pi/README.md) | [Spec](harnesses/pi/SPEC.md) |
| DeepSeek Harness | [Overview](harnesses/deepseek-harness/README.md) | [Spec](harnesses/deepseek-harness/SPEC.md) |
| Kimi Code | [Overview](harnesses/kimi-code/README.md) | [Spec](harnesses/kimi-code/SPEC.md) |
| OpenCode | [Overview](harnesses/opencode/README.md) | [Spec](harnesses/opencode/SPEC.md) |
| Hermes Agent | [Overview](harnesses/hermes-agent/README.md) | [Spec](harnesses/hermes-agent/SPEC.md) |
| OpenClaw | [Overview](harnesses/openclaw/README.md) | [Spec](harnesses/openclaw/SPEC.md) |

## Configuration concept

```yaml
version: 1
secrets_file: secrets.yaml
providers:
  - name: team-proxy
    alias: tp
    type: anthropic
    base_url: https://anthropic.example.invalid
    api_key: { secret: team_proxy }
    models:
      - { name: fast-model, role: simple }
      - { name: everyday-model, role: daily }
      - { name: reasoning-model, role: complex }
```

Replace placeholder endpoint/model IDs with your provider's values. This example selects an Anthropic protocol; other harnesses may require another protocol or explicit endpoint override. Three roles may point to the same upstream model. Additional metadata is required when a native harness needs it.

The private `secrets.yaml` holds key values. Generated shell exports use namespaced variables; launchers map them to native variable names in each child process. Harnesses that require file-based keys receive private derived files.

## Intended workflow

```sh
harness-sync init
harness-sync detect
# Edit config.yaml and add API keys using a hidden prompt.
harness-sync secrets set team_proxy
harness-sync plan --harness claude-code
harness-sync sync --harness claude-code
harness-sync watch --harness claude-code
```

The watcher runs in the foreground; service installation is explicit. In another shell, the generated `claude-tp` command selects that provider and the daily model. `harness-sync run claude-code --provider tp --role complex -- ...` selects complex. Bin-directory PATH setup is handled by explicit shell integration.

The original `claude` command remains intact. Native default files are updated only when `default.write: true` is set for that harness or `--write-defaults` is passed explicitly. Normal sync generates managed profiles and redacted default-change previews. Existing commands such as `claude-tp` are preserved and reported as collisions.

## Proposed implementation

Python 3.11+, a shared planning/transaction core, and one adapter directory per harness. Initial platforms: macOS and Linux; Bash/Zsh shell integration. No installation instructions are provided yet because there is no executable to install.

Approval is required before implementation, as requested. Approving the tool's code does not enable native default writes, install background services, or modify shell startup files by itself.
