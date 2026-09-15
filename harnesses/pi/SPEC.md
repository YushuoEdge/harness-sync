# Pi adapter specification

Status: **Draft; awaiting approval.** Adapter ID: `pi`. Native command: `pi`.

The [overall specification](../../SPEC.md) governs secrets, ownership, transactions, selection and default-write permission. Native facts below were checked against linked public sources on 2026-09-14 (America/New_York); no installed release has been validated yet. Proposed behavior is not an implementation claim.

## Native interface and evidence

Pi supports custom providers in `~/.pi/agent/models.json`, with API, endpoint, key reference and model metadata. [Custom models](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md). `PI_CODING_AGENT_DIR` relocates agent configuration; CLI provider/model selection is available. [CLI and environment](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md).

## Adapter design

- Detect `pi` as the Pi coding agent, not merely another binary with that name; verify help/version/package identity.
- Render `models.json` and `settings.json` in an isolated agent directory per provider. Use stable runtime directories for writable native state; manage only the declared config files within them.
- Map `anthropic` → `anthropic-messages`, `openai-chat` → `openai-completions`, `openai-responses` → `openai-responses`, and Google only when the installed Pi API identifier is verified.
- Translate provider endpoint to `baseUrl`, API to `api`, secret reference to a namespaced environment variable via `apiKey`, and models to `id`, optional reasoning/input/context/output fields. Deduplicate repeated upstream IDs; conflicting metadata on the same native model is an error.
- Launch with child `PI_CODING_AGENT_DIR`, `--provider hs-<name>`, and `--model <role-model-id>`. Render daily selection into `defaultProvider` and `defaultModel` for the profile.
- User sessions, extensions, skills and OAuth from the usual agent directory are not copied. Report isolated state clearly. Never use API-key CLI arguments or executable key resolvers.

## Authorized default writes

Merge owned provider entries in `models.json`, and selected default provider/model in `settings.json`. Preserve unrelated providers and native `auth.json`. Namespaced shell exports support plain `pi`; the wrapper always loads current selected secrets itself. Do not rewrite existing built-in providers under their native names.

## Verification and limitations

Test API mapping, duplicate model IDs, same-name binary rejection, required model metadata, environment-key resolution, role selection, isolation and preservation of existing authentication. Test missing credentials and keyless endpoints against a local stub without inventing a real key. `--models` cycling is optional native behavior, not automatic complexity routing. Existing processes may retain provider catalogs or credentials until restarted.

## Planned directory ownership

After approval, this directory will contain `adapter.py`, versioned native fixtures and adapter tests. Harness-specific detection, rendering, merge paths, launch rules and compatibility checks stay here; shared I/O and secret handling remain in the core.
