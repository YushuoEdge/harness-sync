# Codex adapter

**Native adapter implemented for Codex CLI 0.154.0.**

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Behavior |
| --- | --- |
| Adapter ID | `codex` |
| Native executable | `codex` |
| Provider command | `codex-<alias>` |
| Role selection | `harness-sync run codex --provider <alias> --role simple\|daily\|complex -- ...` |
| Default files | Written only with explicit runtime authorization |
| Verified releases | 0.154.0; other versions fail closed |

## Usage

```sh
harness-sync plan --harness codex
harness-sync sync --harness codex
harness-sync run codex --provider <alias> --role daily -- ...
```

Each managed launch refreshes its selected configuration before starting the harness. No background watcher or enablement flag is needed. These commands generate one native profile per role under `CODEX_HOME` and retain a managed copy. Ordinary Codex commands remain available. See the spec for exact native paths, credential strategy, shared session behavior, default merge fields, and release gates. Only `openai-responses` is supported. No key or real native configuration belongs in this source directory.

## Implementation boundary

This directory owns the native adapter, fixtures and tests. The adapter exports `create_adapter()`, detects the profile-v2 help signature, renders secret-free TOML references, rejects routing overrides, and uses format-preserving three-way merges for explicitly authorized default writes. The implementation does not install personal wrappers or modify native configuration merely by being imported or detected.
