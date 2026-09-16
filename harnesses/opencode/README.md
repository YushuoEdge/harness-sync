# OpenCode adapter

**Documentation only; not implemented.**

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Planned behavior |
| --- | --- |
| Adapter ID | `opencode` |
| Native executable | `opencode` |
| Provider command | `opencode-<alias>` |
| Role selection | `harness-sync run opencode --provider <alias> --role simple\|daily\|complex -- ...` |
| Default files | Written only with explicit runtime authorization |
| Verified releases | None yet; versioned native tests required |

## Proposed usage after implementation

```sh
harness-sync plan --harness opencode
harness-sync sync --harness opencode
harness-sync run opencode --provider <alias> --role daily -- ...
```

Each managed launch refreshes its selected configuration before starting the harness. No background watcher or enablement flag is needed. These examples generate/manage profiles; ordinary commands remain available. See the spec for exact native paths, credential strategy, shared versus isolated session behavior, default merge fields, and release gates. Protocol support depends on the installed native version and configured endpoint. No key or real native configuration belongs in this source directory.

## Implementation boundary

This directory owns the adapter and its tests after approval. No implementation, wrapper installation or native configuration changes have been performed. Final installation instructions, supported-version ranges and smoke-test evidence will be added when implemented.
