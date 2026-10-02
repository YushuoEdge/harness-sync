# DeepSeek Harness adapter specification

Status: **Implemented for dsh 0.2.0-rc.2.** Adapter ID: `deepseek-harness`. Native command: `dsh`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. The installed release, composed headless bundle and localhost routing were verified on 2026-10-02 (America/New_York).

## Native interface and evidence

This adapter targets `deepseek-ai/deepseek-harness` and its `dsh` launcher. Named profiles and `--patch` layers compose configuration; a patch replaces a complete row config rather than deep-merging it. [CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md).

The base bundle exposes credential references, `llm-deepseek`, `llm-pi-ai`, and an `agent-default-model` row. Native settings now persist in Cordis patches; `settings.yaml` is imported once and renamed `settings.yaml.imported`. [CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md).

## Adapter design

- Detect `dsh`, version, `DSH_HOME`, installed base bundle and chosen native profile. Do not confuse this product with a standalone DeepSeek API client.
- Use an isolated managed `DSH_HOME` per provider and role, a native profile manifest and profile `cordis.patch.yml`. Preserve writable sessions separately from generated configuration. Refuse legacy settings and nonempty home patches that could override the profile.
- `harnesses.deepseek-harness.options.base_profile` defaults to the shipped `web` template; explicit installed templates may be selected. `dsh-<alias>` preserves native entry/subcommand behavior. A web launch can open a browser; sync/detect never launches it.
- Map the catalog to supported `llm-pi-ai` provider entries (or native `llm-deepseek` for a verified native match); map roles to the default-model selection using the installed bundle's exact schema. API-key references use namespaced child variables (`apiKeyEnv` where supported).
- Snapshot complete existing row configs when constructing a permitted default overlay, then change only provider/model fields. No YAML `!!js` evaluation by this tool. Parse native tags as inert syntax; reject unsupported edits rather than execute code.
- Resolve/install only native bundled profile resources supported by the detected installation. Do not download plugins or use `dsh plugin add` during sync. If isolated resource resolution needs unsupported bootstrapping, fail with an actionable compatibility diagnostic.

## Authorized default writes

Merge provider catalog fields under the `llm-pi-ai` row and selected provider/model fields under `agent-default-model` in the detected native home `cordis.patch.yml`. Preserve unrelated row configuration, plugin lists, sandbox policy and credentials. `config_path`, when set, names this patch. Legacy default settings are not migrated by the tool. State/profiles for custom commands remain independent.

## Verification and release gates

Before adapter code is considered supported, capture the installed provider/settings schema, default-model precedence (including saved model selection), patch target identities, and safe isolated profile bootstrap in versioned fixtures. These details are not established by the general CLI documentation alone. Test whole-row replacement preservation, inert tags, environment credentials and all three role selections. Some dump commands initialize profiles; run verification only in temporary homes. Native web servers need separate explicit ports for simultaneous profiles; detect collisions and require distinct configured ports. No automatic daemon restart or profile dependency installation.

## Command-triggered sync and model identity

Every generated provider command uses the common pre-launch sync contract: refresh this harness/provider, apply native defaults only when independently authorized, then launch. There is no background watcher or harness enablement flag. A bare original executable remains unchanged and does not invoke the sync tool.

Consume the core's resolved provider-local model `id` (falling back to `name`), never infer an ID from the display label. Native role/model aliases are local selectors and must resolve to that exact upstream ID. Test two providers using the same label but different API IDs, explicit per-harness ID overrides, slash-containing IDs, repeated IDs and unsupported remapping. Model-ID conversion must not change endpoint or credentials.

## Directory ownership

This directory contains `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.

## Implemented release boundary

The installed build supports Chat, Responses and Anthropic through `llm-pi-ai`; Google is rejected.
Role-specific persistent homes prevent saved-selection races. Generated profile patches select both the
provider catalog and `agent-default-model`; no shared home patch edit is necessary for this
release. Only bundled web/headless/sdk/acp templates are allowed, and web requires an explicit port.
Executable tags in user settings and reasoning metadata without effort maps are rejected. Native
localhost headless checks verified all supported protocols/roles on 2026-10-02. Error stubs prove
request routing, exact model IDs and fake credentials; complete model responses were not tested.
