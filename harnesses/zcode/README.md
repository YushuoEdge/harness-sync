# ZCode CLI adapter

Implemented for the official [zai-org/ZCode](https://github.com/zai-org/ZCode) distribution
**3.14.3**, containing Agent CLI **0.16.9**. Unknown distribution/Agent versions fail closed.
Supports Anthropic Messages, OpenAI Chat Completions and OpenAI Responses. Google is rejected.

```sh
harness-sync sync --harness zcode
harness-sync run zcode --provider <alias> --role complex -- --prompt "your task" --mode plan
# With no native arguments, open the TUI in the selected role profile.
harness-sync run zcode --provider <alias> --role daily
```

Models require explicit `context_window` and `max_output_tokens`. Exact IDs are stored as JSON
fields, including slashes and dollar signs; per-harness endpoint, protocol and ID overrides work.
Reasoning capabilities and effort maps are rejected until model-specific native maps are supported.
A repeated model ID must have identical metadata.

Each provider/role has a private provider file and an empty built-in catalog under a persistent
managed data root. Child-scoped `ZCODE_DATA_BASE_DIR` isolates ZCode sessions, settings and account
state while preserving OS `HOME`. The selected role uses structured `defaultModelSelection`.
No personal accounts, sessions or plugins are copied. API keys and secret headers are literal
values in mode-0600 JSON and are refreshed by normal pre-launch sync. They never appear on argv.
The empty built-in catalog and removal of its inherited refresh source prevent account/catalog
fallback. Project instructions and native permissions retain their ordinary behavior.

Managed startup rejects resume/continue, explicit targets, dynamic workflow mode, Web/server modes,
and login/plugin administration. Interactive `/model`, `/resume` and other native commands can
change an already running session; only fresh-launch primary-request selection is verified.
Native default writes are unsupported. Normal sync does not change shared `~/.zcode` files.

## Installation and evidence

On 2026-10-02 the official source at revision
`29628c9acdb81b703bbd4080c207a0e7ce5e276e` was downloaded and built using its locked pnpm dependencies.
The unified distribution is installed at `~/.local/share/zcode/runtime-3.14.3/zcode`, with
`~/.local/bin/zcode` pointing to its entry point. The upstream build required a packaging workaround:
transpile source-only `@zcode/shared` into `dist` and redirect its exports before packaging.
[build workaround](scripts/prepare_shared_dist.mjs) records that step; it does not run during sync.
The resulting local tarball SHA-256 is
`6b7852e91f923c16bf86cdee222d3c5c1ff2cdf5f1cd1e812456b88e1556907e`.
This is a local source build, with no published installer/CDN or auto-updater configured.
Node 24.14+ is required by the distribution; this machine uses Node 24.16.0.

Sanitized version/help fixtures and unit tests are included. The opt-in native check covers all
three protocols and roles, two providers sharing labels, slash/dollar IDs, per-harness IDs,
secret headers, key rotation and stale inherited configuration:

```sh
PYTHONPATH=.:src uv run python harnesses/zcode/tests/smoke_native.py
```

It uses temporary data, localhost HTTP error responses and fake keys. It proves endpoint, model,
credential and header delivery, not successful inference, interactive UI behavior or delegation.
See [spec](SPEC.md) for the exact native schema and boundaries.
