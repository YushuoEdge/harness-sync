# Claude Code adapter

**Documentation only; not implemented.**

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Planned behavior |
| --- | --- |
| Adapter ID | `claude-code` |
| Native executable | `claude` |
| Provider command | `claude-<alias>` |
| Role selection | `harness-sync run claude-code --provider <alias> --role simple\|daily\|complex -- ...` |
| Default files | Written only with explicit runtime authorization |
| Verified releases | None yet; versioned native tests required |

## Proposed usage after implementation

```sh
harness-sync plan --harness claude-code
harness-sync sync --harness claude-code
harness-sync watch --harness claude-code
```

These examples generate/manage profiles; ordinary commands remain available. See the spec for exact native paths, credential strategy, shared versus isolated session behavior, default merge fields, and release gates. Protocol support depends on the installed native version and configured endpoint. No key or real native configuration belongs in this source directory.

## Implementation boundary

This directory owns the adapter and its tests after approval. No implementation, wrapper installation or native configuration changes have been performed. Final installation instructions, supported-version ranges and smoke-test evidence will be added when implemented.
