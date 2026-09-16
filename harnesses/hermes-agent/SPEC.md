# Hermes Agent adapter specification

Status: **Native design pending implementation; shared framework ready.** Adapter ID: `hermes-agent`. Native command: `hermes`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

Hermes uses `config.yaml` for settings and `.env` for keys under its home; `HERMES_HOME` selects profile state. [Configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration/). Named/custom providers and endpoint routing are described separately. [Providers](https://hermes-agent.nousresearch.com/docs/integrations/providers).

## Adapter design

- Detect `hermes`, version and native `HERMES_HOME`. Do not alter installation files or bundled runtimes.
- Render an isolated profile home containing `config.yaml` and native `.env`. These are persistent runtime profile directories; preserve sessions and other runtime files across syncs.
- Map provider/endpoint/model to the installed version's named custom-provider and active-model schema. The initial required custom transport is OpenAI Chat; Anthropic, Responses and Google are enabled only with verified native adapters.
- Store API keys as dotenv values in the profile `.env`, with native `${VAR}` references where the verified provider schema accepts them. The runner also supplies selected variables directly so inherited shell keys cannot take precedence accidentally. No `export` tokens inside native dotenv unless its parser explicitly supports them.
- `hermes-<alias>` keeps the native command/subcommand grammar and supplies the profile home plus role selection. If `chat --model` is needed for a requested role, assemble it only for compatible chat invocations; do not prepend chat to administrative subcommands.
- Daily is active by default; the runner makes simple and complex available. Preserve auxiliary/delegation/fallback settings; do not silently route them to a guessed tier or second provider.
- Profiles have separate memories, skills, sessions and OAuth; none are copied implicitly. OS `HOME` remains unchanged.

## Authorized default writes

Merge only owned model/provider fields into native YAML and corresponding key entries into `.env`. Preserve comments, other provider credentials, bot tokens and unrelated settings. Both files form one staged plan with recovery. Preserve `auth.json` and built-in OAuth providers. Scope inherited routing variables narrowly to avoid altering unrelated tool credentials.

## Verification and release gates

Capture current custom-provider schema, key-variable binding and CLI selection behavior before enabling the adapter. Test YAML interpolation and native dotenv parsing independently from shell export parsing. Verify two homes receive different keys despite a stale parent environment; test all role launches and unchanged global files. Unknown transport fields fail validation. Do not restart a gateway or synchronize its bot/channel identity, schedules or memories; existing long-lived processes may need a user-initiated restart.

## Command-triggered sync and model identity

Every generated provider command uses the common pre-launch sync contract: refresh this harness/provider, apply native defaults only when independently authorized, then launch. There is no background watcher or harness enablement flag. A bare original executable remains unchanged and does not invoke the sync tool.

Consume the core's resolved provider-local model `id` (falling back to `name`), never infer an ID from the display label. Native role/model aliases are local selectors and must resolve to that exact upstream ID. Test two providers using the same label but different API IDs, explicit per-harness ID overrides, slash-containing IDs, repeated IDs and unsupported remapping. Model-ID conversion must not change endpoint or credentials.

## Planned directory ownership

When implemented, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
