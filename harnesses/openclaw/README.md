# OpenClaw adapter

**Native adapter pending; shared framework available.**

Read the [adapter specification](SPEC.md) and [overall specification](../../SPEC.md).

| Item | Planned behavior |
| --- | --- |
| Adapter ID | `openclaw` |
| Native executable | `openclaw` |
| Provider command | `openclaw-<alias>` |
| Role selection | `harness-sync run openclaw --provider <alias> --role simple\|daily\|complex -- ...` |
| Default files | Written only with explicit runtime authorization |
| Verified releases | None yet; versioned native tests required |

## Proposed usage after implementation

```sh
harness-sync plan --harness openclaw
harness-sync sync --harness openclaw
harness-sync run openclaw --provider <alias> --role daily -- ...
```

Each managed launch refreshes its selected configuration before starting the harness. No background watcher or enablement flag is needed. After this adapter is implemented, these examples generate/manage profiles; ordinary commands remain available. See the spec for exact native paths, credential strategy, shared versus isolated session behavior, default merge fields, and release gates. Protocol support depends on the installed native version and configured endpoint. No key or real native configuration belongs in this source directory.

## Implementation boundary

This directory owns the native adapter and its tests. Follow the [adapter development guide](../../docs/adapter-development.md); its API is implemented in the shared core. Add `adapter.py` exporting `create_adapter()` when ready. This directory currently contains only documentation and its adapter manifest. No native implementation, personal wrapper installation or native configuration changes have been performed. Final installation instructions, supported-version ranges and smoke-test evidence will be added when implemented.
