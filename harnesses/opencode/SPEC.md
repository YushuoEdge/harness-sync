# OpenCode adapter specification

Status: **Draft; awaiting approval.** Adapter ID: `opencode`. Native command: `opencode`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

OpenCode merges global, custom, project and inline config layers; `OPENCODE_CONFIG_CONTENT` supplies runtime overrides. [Configuration](https://opencode.ai/docs/config/). Provider definitions can specify an SDK, models and options including endpoint and credential; native login storage is separate. [Providers](https://opencode.ai/docs/providers).

## Adapter design

- Detect `opencode` and the active global JSON/JSONC path, honoring native config-directory conventions. Refuse ambiguity if both candidate files are active but their precedence cannot be verified.
- Render managed `opencode.json` with namespaced provider definitions, native SDK `npm` selection, `options.baseURL`, `options.apiKey` as `{env:HS_<SECRET>}`, model catalog, active `model`, and `small_model` for simple.
- Map daily to the primary model; simple to `small_model`; complex remains selectable through the runner/model picker. Do not repurpose build/plan agents as complexity roles or change their permissions.
- `opencode-<alias>` supplies the generated config through child-scoped `OPENCODE_CONFIG_CONTENT`, pins the role with native model selection, and supplies the matching key. Using only `OPENCODE_CONFIG` is insufficient to promise precedence over project files.
- Pin endpoint/auth and provider availability where supported so inherited catalogs cannot silently select a different credential. Managed policy remains authoritative; report enforced conflicts. Reject additional inline config/provider-selection flags through the wrapper.
- Shared sessions, native auth and unrelated settings remain available. Provider overlays do not isolate the entire OpenCode home. Clear inherited custom config content before assigning the generated content.

## Authorized default writes

Merge owned provider catalog entries and selected `model`/`small_model` in the native global file, preserving JSONC comments and unrelated config. Use environment references; leave native OAuth/auth.json untouched. Native project config can override ordinary default model selection; status explains the default is global, not enforced in every project.

## Verification and release gates

Pin and test the SDK mapping for each supported protocol (Anthropic, OpenAI Chat, Responses, Google). A package name alone does not prove which wire API an SDK uses. Test exact request paths with local stubs and reject unverified mappings. Test project/inline/CLI precedence, duplicate IDs, small-model selection, preserved native auth and invalid JSONC. Never install arbitrary SDKs from canonical overrides; use a fixed adapter allowlist. Exposing three roles does not restrict every internal auxiliary model unless native configuration supports it.

## Planned directory ownership

After approval, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
