# DeepSeek Harness adapter specification

Status: **Draft; awaiting approval.** Adapter ID: `deepseek-harness`. Native command: `dsh`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

This adapter targets `deepseek-ai/deepseek-harness` and its `dsh` launcher. Named profiles and `--patch` layers compose configuration; a patch replaces a complete row config rather than deep-merging it. [CLI reference](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/reference/README.md).

The base bundle exposes `settings.yaml`, credential references, `llm-deepseek`, `llm-pi-ai`, and an `agent-default-model` row. [Base bundle source](https://raw.githubusercontent.com/deepseek-ai/deepseek-harness/master/packages/bundle/base/cordis.patch.yml).

## Adapter design

- Detect `dsh`, version, `DSH_HOME`, installed base bundle and chosen native profile. Do not confuse this product with a standalone DeepSeek API client.
- Use an isolated managed `DSH_HOME` per provider, a native profile manifest, provider `settings.yaml`, and one role-specific overlay patch. Preserve writable sessions separately from generated settings.
- `harnesses.deepseek-harness.base_profile` defaults to the shipped `web` template; explicit installed templates may be selected. `dsh-<alias>` preserves native entry/subcommand behavior. A web launch can open a browser; sync/detect never launches it.
- Map the catalog to supported `llm-pi-ai` provider entries (or native `llm-deepseek` for a verified native match); map roles to the default-model selection using the installed bundle's exact schema. API-key references use namespaced child variables (`apiKeyEnv` where supported).
- Snapshot complete existing row configs when constructing a permitted default overlay, then change only provider/model fields. No YAML `!!js` evaluation by this tool. Parse native tags as inert syntax; reject unsupported edits rather than execute code.
- Resolve/install only native bundled profile resources supported by the detected installation. Do not download plugins or use `dsh plugin add` during sync. If isolated resource resolution needs unsupported bootstrapping, fail with an actionable compatibility diagnostic.

## Authorized default writes

Merge only selected provider/model settings into the detected native settings document and the minimal required default-model patch. Never replace unrelated patch rows, plugin lists, sandbox policy or credentials. A default change applies to the configured native base profile/shared settings scope; the plan must show that scope. State/profiles for custom commands remain independent.

## Verification and release gates

Before adapter code is considered supported, capture the installed provider/settings schema, default-model precedence (including saved model selection), patch target identities, and safe isolated profile bootstrap in versioned fixtures. These details are not established by the general CLI documentation alone. Test whole-row replacement preservation, inert tags, environment credentials and all three role selections. Some dump commands initialize profiles; run verification only in temporary homes. Native web servers need separate explicit ports for simultaneous profiles; detect collisions and require distinct configured ports. No automatic daemon restart or profile dependency installation.

## Planned directory ownership

After approval, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
